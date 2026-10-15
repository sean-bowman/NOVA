
# -- Design Tab -- #

'''

The Design tab: the configuration form. Renders every field in configSchema as a labeled editor
inside collapsible section cards, round-trips the values to and from JSON in the NOVANozzle schema,
and runs light cross-field checks before a solve. A fresh form is the shipped nozzle.

Each section shows the fields a design is made from, then an Advanced settings fold, closed until
opened, holding the rest at the shipped nozzle's values. Alternative inputs (thrust or mass flow,
L* or barrel length) share one selector row, so only one of them can be set.

Author: Sean Bowman
Date:   08/28/2026

'''

import json
from tkinter import ttk, filedialog, messagebox

from .. import configSchema
from .. import theme
from ..widgets import ScrollableFrame, CollapsibleSection, FieldRow, SelectorRow, MaterialInfoPanel, Tooltip

def _designVector(entry) -> list | None:

    '''

    The thrust-optimized design vector as the backend reads it, from what the form holds.

    The form carries the four numbers as one comma-separated text entry, since the rest of the
    form is one widget per number. Blank means unset, which is what runs the search.

    Parameters:
    -----------
    entry : str or list or None
        Form text, or a value already in backend form.

    Returns:
    --------
    list or None
        The numbers in order, or None when the entry is blank.

    Raises:
    -------
    ValueError
        If the entry is not a list of numbers. The count and the bounds are the backend's to
        check, so that the GUI and a JSON run refuse the same vectors for the same reasons.

    '''

    if entry is None or isinstance(entry, (list, tuple)):
        return list(entry) if entry else None

    text = str(entry).replace(',', ' ').split()
    if not text:
        return None

    try:
        return [float(value) for value in text]
    except ValueError:
        raise ValueError("'Design vector' takes numbers separated by commas.")

def _designVectorText(value) -> str:

    '''

    The design vector as the form holds it, from what a config carries.

    Parameters:
    -----------
    value : list or None
        The numbers in order, or None.

    Returns:
    --------
    str
        Comma-separated numbers, empty when unset.

    '''

    if value is None or isinstance(value, str):
        return value or ''

    return ', '.join(f'{float(number):g}' for number in value)

class ConfigTab(ttk.Frame):

    '''

    Editable NOVA configuration with load / save / reset and pre-run validation.

    '''

    def __init__(self, master, app):

        super().__init__(master, style = 'TFrame')

        self._app = app
        self._rows = {}                       # key -> FieldRow
        self._selectors = []                  # SelectorRow, in form order
        self._grids = []                      # every row grid, so their label columns match
        self._sections = {}                   # group title -> CollapsibleSection
        self._orderedSections = []            # [(Group, CollapsibleSection)] in form order
        self._groupVisible = {}               # group title -> bool
        self._expandFired = {}                # group title -> last expandWhen state
        self._suspendDynamics = False
        self._materialPanel = None            # sampled-property panel in the cooling section

        # A slim strip: loading lives in the header and saving at the foot of the form, so the
        # form starts close under the tabs
        strip = ttk.Frame(self, style = 'TFrame', padding = (theme.scaled(12), theme.scaled(4),
                                                             theme.scaled(12), theme.scaled(2)))
        strip.pack(fill = 'x')
        ttk.Label(strip, text = 'DESIGN', style = 'Eyebrow.TLabel').pack(side = 'left')
        resetButton = ttk.Button(strip, text = 'Reset to example', style = 'Small.TButton',
                                 command = self._resetToExample)
        resetButton.pack(side = 'right')
        Tooltip(resetButton, 'Replace the form with the shipped nozzle, the design NOVA builds '
                             'when it is given no configuration.')

        self._warning = ttk.Label(self, text = '', style = 'Warn.TLabel', wraplength = theme.scaled(900),
                                  padding = (theme.scaled(12), 0, theme.scaled(12), theme.scaled(4)))
        self._warning.pack(fill = 'x')

        scroller = ScrollableFrame(self)
        scroller.pack(fill = 'both', expand = True)
        self._scrollBody = scroller.body

        for group in configSchema.groups:
            section = CollapsibleSection(scroller.body, group.title, group.collapsed, group.note)
            self._sections[group.title] = section
            self._orderedSections.append((group, section))
            self._groupVisible[group.title] = True

            mainGrid = self._grid(section.body)
            advancedGrid = None
            if any(item.advanced for item in group.fields):
                fold = CollapsibleSection(section.body, 'Advanced settings', collapsed = True, nested = True)
                fold.pack(fill = 'x', pady = (theme.scaled(6), 0))
                advancedGrid = self._grid(fold.body)

            for item in group.fields:
                grid = advancedGrid if item.advanced else mainGrid
                rowIndex = grid.grid_size()[1]
                if isinstance(item, configSchema.Selector):
                    self._selectors.append(SelectorRow(grid, item, rowIndex))
                else:
                    self._rows[item.key] = FieldRow(grid, item, rowIndex)

            if group.title == 'Regenerative Cooling':
                self._materialPanel = MaterialInfoPanel(section.body)
                self._materialAnchor = mainGrid
                self._materialPanel.pack(fill = 'x', pady = (theme.scaled(8), 0), after = mainGrid)

        # Saving sits at the foot of the form, after the last section
        self._footer = ttk.Frame(scroller.body, style = 'TFrame', padding = (theme.scaled(10), theme.scaled(4),
                                                                            theme.scaled(10), theme.scaled(12)))
        saveButton = ttk.Button(self._footer, text = 'Save config', command = self.saveConfig)
        saveButton.pack(side = 'right')
        Tooltip(saveButton, 'Write the form to a JSON configuration NOVA can run directly.  Ctrl+S')
        self._relayoutSections()

        # One label column width and one editor width for every grid, the widest of each, so the
        # editors of every section and fold line up in one column and end at one edge
        self.update_idletasks()
        labelWidth = max([theme.scaled(280)] + [row.labelWidth for row in self._allRows()])
        editorWidth = max(row.editorWidth for row in self._allRows())
        for grid in self._grids:
            grid.columnconfigure(0, minsize = labelWidth)
            grid.columnconfigure(1, minsize = editorWidth)

        # React to every edit: re-run dependency visibility and the cross-field checks.
        for row in self._allRows():
            for variable in row.variables:
                variable.trace_add('write', lambda *_: self._onChange())
        self._applyDynamics()
        self._refreshWarnings()

    def _grid(self, master) -> ttk.Frame:

        '''

        A grid for a block of rows. The last column takes the slack, so the editors keep their own
        width rather than stretching across the card.

        '''

        grid = ttk.Frame(master, style = 'Surface.TFrame')
        grid.pack(fill = 'x')
        grid.columnconfigure(0, weight = 0, minsize = theme.scaled(280))
        grid.columnconfigure(3, weight = 1)
        self._grids.append(grid)

        return grid

    def _allRows(self) -> list:

        '''Every row in the form, field rows and selector rows alike.'''

        return list(self._rows.values()) + self._selectors

    # -- Dynamic form behavior -- #

    def _onChange(self) -> None:

        if self._suspendDynamics:
            return
        self._applyDynamics()
        self._refreshWarnings()

    def _safeConfig(self) -> dict:

        '''

        Current form contents, tolerant of half-typed numbers (a field that will
        not parse reads as None). Used to evaluate the dependency predicates.

        '''

        result = {}
        for key, row in self._rows.items():
            try:
                result[key] = row.get()
            except ValueError:
                result[key] = None
        for row in self._selectors:
            try:
                result.update(row.get())
            except ValueError:
                result.update({key: None for key in row.spec.keys()})
        return result

    def _applyDynamics(self) -> None:

        '''

        Hide fields and whole sections whose dependency predicate is not met, and
        auto-open a section the first time its trigger turns on.

        '''

        config = self._safeConfig()

        for row in self._allRows():
            predicate = row.spec.showWhen
            row.setVisible(predicate is None or bool(predicate(config)))

        if self._materialPanel is not None:
            if configSchema._coolingOn(config):
                if not self._materialPanel.winfo_manager():
                    self._materialPanel.pack(fill = 'x', pady = (theme.scaled(8), 0), after = self._materialAnchor)
                self._materialPanel.setMaterial(config.get('material') or 'GRCop-42')
            elif self._materialPanel.winfo_manager():
                self._materialPanel.pack_forget()

        layoutChanged = False
        for group, section in self._orderedSections:
            visible = group.showWhen is None or bool(group.showWhen(config))
            if visible != self._groupVisible[group.title]:
                self._groupVisible[group.title] = visible
                layoutChanged = True
                if visible:
                    section.setOpen(True)

            if group.expandWhen is not None:
                triggered = bool(group.expandWhen(config))
                if triggered and not self._expandFired.get(group.title):
                    section.setOpen(True)
                self._expandFired[group.title] = triggered

        if layoutChanged:
            self._relayoutSections()

    def _relayoutSections(self) -> None:

        for _, section in self._orderedSections:
            section.pack_forget()
        self._footer.pack_forget()
        for group, section in self._orderedSections:
            if self._groupVisible[group.title]:
                section.pack(fill = 'x', padx = theme.scaled(10), pady = (0, theme.scaled(8)))
        self._footer.pack(fill = 'x')

    # -- Public API -- #

    def getConfig(self) -> dict:

        '''

        Current form contents as a complete config dictionary in the backend
        schema. Synthetic helper fields are folded into their real key. Raises
        ValueError with a field-qualified message if a numeric entry cannot be
        parsed.

        '''

        values = {key: row.get() for key, row in self._rows.items()}
        for row in self._selectors:
            values.update(row.get())
        # In the schema's order, which is the shipped file's, and without any synthetic helper;
        # none are currently defined
        raw = {spec.key: values[spec.key] for spec in configSchema.allFields() if not spec.synthetic}
        # The design vector is one text entry in the form and a list of numbers in the config
        raw['divergingSectionDesignVariables'] = _designVector(raw.get('divergingSectionDesignVariables'))
        return raw

    def setConfig(self, config: dict) -> None:

        '''

        Populate the form from a config dictionary in the backend schema. Unknown
        keys are ignored; missing keys fall back to the schema default.

        '''

        config = dict(config)
        if 'divergingSectionDesignVariables' in config:
            config['divergingSectionDesignVariables'] = _designVectorText(
                config['divergingSectionDesignVariables'])

        defaults = configSchema.defaultConfig()
        merged = {**defaults, **config}
        self._suspendDynamics = True
        try:
            for key, row in self._rows.items():
                row.set(merged.get(key, row.spec.default))
            for row in self._selectors:
                row.set(merged)
        finally:
            self._suspendDynamics = False
        # A freshly loaded config may switch on a section that was collapsed;
        # let it settle, then re-evaluate expand triggers from the new state.
        self._expandFired.clear()
        self._applyDynamics()
        self._refreshWarnings()

    def validate(self) -> list:

        '''

        Return a list of human-readable problems that should block or warn
        before a run. An empty list means the form looks consistent.

        '''

        problems = []
        try:
            config = self.getConfig()
        except ValueError as exc:
            return [str(exc)]

        def isSet(key) -> bool:
            return config.get(key) not in (None, '')

        # A selector writes only the option chosen, so alternatives cannot both be set; what is
        # left to check is that a required one was given a value
        for row in self._selectors:
            option = next(option for option in row.spec.options if option.label == row.selectedLabel)
            if row.spec.required and row.visible and option.key is not None and not isSet(option.key):
                problems.append(f"'{option.label}' needs a value.")

        if isSet('Lstar') and float(config['Lstar']) <= 0:
            problems.append("'Characteristic length L*' must be positive.")

        if config.get('makeCoolingChannels') in (True, 'on'):
            needed = ['hotWallThickness', 'shellThickness', 'coolantInitialTemperature', 'coolantInitialPressure']
            missing = [k for k in needed if not isSet(k)]
            if missing:
                problems.append('Cooling channels need: ' + ', '.join(missing) + '.')
            # A helix has no default angle; the backend rejects the run without one
            if config.get('channelType') == 'helical' and not isSet('channelHelixAngle'):
                problems.append("Helical channels need a 'Channel helix angle'.")

        if config.get('makeInletVolute') in (True, 'on') or config.get('makeOutletVolute') in (True, 'on'):
            if config.get('makeCoolingChannels') not in (True, 'on'):
                problems.append('Volute generation requires cooling channels to be enabled.')

        return problems

    def refresh(self, runResult) -> None:

        '''

        The config tab does not change after a run.

        '''

        return

    # -- Internals -- #

    def _refreshWarnings(self) -> None:

        problems = self.validate()
        if problems:
            self._warning.configure(text = '  •  '.join(problems))
        else:
            self._warning.configure(text = '')

        flagged = ' '.join(problems).lower()
        for row in self._allRows():
            label = row.selectedLabel if isinstance(row, SelectorRow) else row.spec.label
            row.highlight(f"'{label.lower()}'" in flagged)

    def loadConfig(self) -> None:

        '''Ask for a JSON configuration and load it into the form.'''

        path = filedialog.askopenfilename(
            title = 'Load NOVA config',
            filetypes = [('JSON config', '*.json'), ('All files', '*.*')],
        )
        if not path:
            return
        try:
            with open(path, 'r') as handle:
                config = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror('Load failed', f'Could not read {path}\n\n{exc}')
            return
        self.setConfig(config)

    def saveConfig(self) -> None:

        '''Write the form to a JSON configuration chosen by the user.'''

        try:
            config = self.getConfig()
        except ValueError as exc:
            messagebox.showerror('Cannot save', str(exc))
            return
        path = filedialog.asksaveasfilename(
            title = 'Save NOVA config',
            defaultextension = '.json',
            initialfile = (config.get('filename') or 'novaRun') + 'Config.json',
            filetypes = [('JSON config', '*.json')],
        )
        if not path:
            return
        with open(path, 'w') as handle:
            json.dump(config, handle, indent = 4)

    def _resetToExample(self) -> None:

        if not messagebox.askokcancel('Reset form', 'Replace the current form with the shipped nozzle?'):
            return
        self.setConfig(configSchema.defaultConfig())
