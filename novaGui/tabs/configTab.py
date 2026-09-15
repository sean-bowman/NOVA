# -- Config Tab -- #

'''

The configuration form. Renders every field in configSchema as a labeled
editor inside collapsible sections, round-trips the values to and from JSON in
the nozzleConfig schema, and runs light cross-field checks before a solve.

Author: Sean Bowman
Date:   08/28/2026

'''

import re
import json
from tkinter import ttk, filedialog, messagebox

from .. import configSchema
from .. import theme
from ..widgets import ScrollableFrame, CollapsibleSection, FieldRow, MaterialInfoPanel

class ConfigTab(ttk.Frame):

    '''

    Editable NOVA configuration with load / save / reset and pre-run validation.

    '''

    def __init__(self, master, app):

        super().__init__(master, style = 'TFrame')

        self._app = app
        self._rows = {}                       # key -> FieldRow
        self._sections = {}                   # group title -> CollapsibleSection
        self._orderedSections = []            # [(Group, CollapsibleSection)] in form order
        self._groupVisible = {}               # group title -> bool
        self._expandFired = {}                # group title -> last expandWhen state
        self._suspendDynamics = False
        self._materialPanel = None            # sampled-property panel in the cooling section

        toolbar = ttk.Frame(self, style = 'TFrame', padding = (10, 8))
        toolbar.pack(fill = 'x')
        ttk.Label(toolbar, text = 'CONFIGURATION', style = 'Eyebrow.TLabel').pack(side = 'left')
        ttk.Button(toolbar, text = 'Load JSON', command = self._loadJson).pack(side = 'right', padx = 3)
        ttk.Button(toolbar, text = 'Save JSON', command = self._saveJson).pack(side = 'right', padx = 3)
        ttk.Button(toolbar, text = 'Reset to example', command = self._resetToExample).pack(side = 'right', padx = 3)

        self._warning = ttk.Label(self, text = '', style = 'Warn.TLabel', wraplength = theme.scaled(900),
                                  padding = (12, 0, 12, 4))
        self._warning.pack(fill = 'x')

        scroller = ScrollableFrame(self)
        scroller.pack(fill = 'both', expand = True)

        for group in configSchema.groups:
            section = CollapsibleSection(scroller.body, group.title, group.collapsed, group.note)
            section.pack(fill = 'x', pady = (0, 6))
            self._sections[group.title] = section
            self._orderedSections.append((group, section))
            self._groupVisible[group.title] = True

            grid = ttk.Frame(section.body, style = 'TFrame')
            grid.pack(fill = 'x')
            grid.columnconfigure(1, weight = 1)
            for rowIndex, fieldSpec in enumerate(group.fields):
                self._rows[fieldSpec.key] = FieldRow(grid, fieldSpec, rowIndex)

            if group.title == 'Cooling Channels':
                self._materialPanel = MaterialInfoPanel(section.body)
                self._materialPanel.pack(fill = 'x', pady = (8, 0))

        # React to every edit: re-run dependency visibility and the cross-field checks.
        for row in self._rows.values():
            row._var.trace_add('write', lambda *_: self._onChange())
        self._applyDynamics()
        self._refreshWarnings()

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
        return result

    def _applyDynamics(self) -> None:

        '''

        Hide fields and whole sections whose dependency predicate is not met, and
        auto-open a section the first time its trigger turns on.

        '''

        config = self._safeConfig()

        for row in self._rows.values():
            predicate = row.spec.showWhen
            row.setVisible(predicate is None or bool(predicate(config)))

        if self._materialPanel is not None:
            if configSchema._coolingOn(config):
                if not self._materialPanel.winfo_manager():
                    self._materialPanel.pack(fill = 'x', pady = (8, 0))
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
        for group, section in self._orderedSections:
            if self._groupVisible[group.title]:
                section.pack(fill = 'x', pady = (0, 6))

    # -- Public API -- #

    def getConfig(self) -> dict:

        '''

        Current form contents as a complete config dictionary in the backend
        schema. Synthetic helper fields are folded into their real key. Raises
        ValueError with a field-qualified message if a numeric entry cannot be
        parsed.

        '''

        raw = {key: row.get() for key, row in self._rows.items()}
        raw = self._composeTruncation(raw)
        # Drop any synthetic helper the compose step did not already consume.
        for fieldSpec in configSchema.allFields():
            if fieldSpec.synthetic:
                raw.pop(fieldSpec.key, None)
        return raw

    def setConfig(self, config: dict) -> None:

        '''

        Populate the form from a config dictionary in the backend schema. Unknown
        keys are ignored; missing keys fall back to the schema default. The
        backend 'truncationMethod' string is unpacked into the mode selector and
        its value field.

        '''

        config = dict(config)
        mode, temperature, areaRatio = self._decomposeTruncation(config.get('truncationMethod'))
        config['truncationMethod'] = mode
        config['truncationTemperature'] = temperature
        config['truncationAreaRatio'] = areaRatio

        defaults = configSchema.defaultConfig()
        self._suspendDynamics = True
        try:
            for key, row in self._rows.items():
                if key in config:
                    row.set(config[key])
                else:
                    row.set(defaults.get(key, row.spec.default))
        finally:
            self._suspendDynamics = False
        # A freshly loaded config may switch on a section that was collapsed;
        # let it settle, then re-evaluate expand triggers from the new state.
        self._expandFired.clear()
        self._applyDynamics()
        self._refreshWarnings()

    def _composeTruncation(self, raw: dict) -> dict:

        '''

        Replace the mode selector and its value field with the single string the
        backend parses: 'none', 'temp <K>' or 'er <ratio>'. The space after the
        prefix is required -- Nozzle.truncateForRegen reads the number from a
        fixed offset (index 5 for temp, 3 for er).

        '''

        mode = raw.pop('truncationMethod', 'none')
        temperature = raw.pop('truncationTemperature', None)
        areaRatio = raw.pop('truncationAreaRatio', None)

        if mode == 'temp' and temperature is not None:
            raw['truncationMethod'] = f'temp {float(temperature):g}'
        elif mode == 'er' and areaRatio is not None:
            raw['truncationMethod'] = f'er {float(areaRatio):g}'
        else:
            raw['truncationMethod'] = 'none'
        return raw

    def _decomposeTruncation(self, value) -> tuple:

        '''

        Split a backend 'truncationMethod' string into (mode, temperature,
        areaRatio). Anything unrecognized reads as no truncation.

        '''

        if not isinstance(value, str) or not value.strip():
            return 'none', None, None
        text = value.strip()
        head = text[0].lower()
        match = re.search(r'[-+]?\d*\.?\d+', text)
        number = float(match.group()) if match else None
        if head == 't':
            return 'temp', number, None
        if head == 'e':
            return 'er', None, number
        return 'none', None, None

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

        if isSet('thrust') == isSet('engineMassFlow'):
            problems.append("Specify exactly one of 'Thrust' or 'Engine mass flow'.")
        if isSet('expansionRatio') == isSet('targetExitPressure'):
            problems.append("Specify exactly one of 'Expansion ratio' or 'Target exit pressure'.")

        if isSet('Lstar') and isSet('chamberLength'):
            problems.append("Specify at most one of 'Characteristic length L*' or 'Chamber barrel length'.")
        if isSet('Lstar') and float(config['Lstar']) <= 0:
            problems.append("'Characteristic length L*' must be positive.")

        if isSet('raoThroatAngle') and isSet('chamberInterfaceAngle'):
            if abs(float(config['raoThroatAngle']) - float(config['chamberInterfaceAngle'])) < 1e-6:
                problems.append('Converging wall angles at the throat and chamber must differ.')

        if config.get('divergingSectionType') == 'Conical' and not isSet('conicalHalfAngle'):
            problems.append("Conical diverging section needs a 'Conical half angle'.")

        truncationMode = self._rows['truncationMethod'].get()
        if truncationMode == 'temp' and self._rows['truncationTemperature'].get() is None:
            problems.append("Wall-temperature truncation needs a 'Truncation wall temperature'.")
        if truncationMode == 'er' and self._rows['truncationAreaRatio'].get() is None:
            problems.append("Area-ratio truncation needs a 'Truncation area ratio'.")

        if config.get('makeCoolingChannels') in (True, 'on'):
            needed = ['hotWallThickness', 'shellThickness', 'coolantInitialTemperature', 'coolantInitialPressure']
            missing = [k for k in needed if not isSet(k)]
            if missing:
                problems.append('Cooling channels need: ' + ', '.join(missing) + '.')

        if config.get('makeInletVolute') in (True, 'on') or config.get('makeReturnVolute') in (True, 'on'):
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

        for key, row in self._rows.items():
            row.highlight(False)
        flagged = ' '.join(problems).lower()
        for key, row in self._rows.items():
            if row.spec.label.lower() in flagged:
                row.highlight(True)

    def _loadJson(self) -> None:

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

    def _saveJson(self) -> None:

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

        if not messagebox.askokcancel('Reset form', 'Replace the current form with the schema defaults?'):
            return
        self.setConfig(configSchema.defaultConfig())
