
# -- NOVA GUI Reusable Widgets -- #

'''

Small widget helpers shared across the tabs:

    Tooltip            hover help bound to any widget, on a rounded window where Windows allows
    ScrollableFrame    vertically scrolling container with a themed scrollbar
    CollapsibleSection a rounded card whose title row opens and closes its body, marked by a
                       nozzle drawn sideways when closed and flowing down when open; nested, the
                       Advanced settings fold inside a card
    FieldRow           label, help marker and editor for one configSchema.Field, with typed get/set
    SelectorRow        option dropdown, value and unit for one configSchema.Selector, which stands
                       for several alternative config keys
    MaterialInfoPanel  sampled properties of the selected wall alloy
    ConsolePane        read-only monospace log with autoscroll

Every widget names a theme style for its colors rather than setting them, so a change of theme
mode reaches it. The classic Tk widgets among them, which ttk does not style, recolor themselves
through a theme listener.

Author: Sean Bowman
Date:   08/28/2026

'''

import tkinter as tk
from tkinter import ttk

from . import theme
from . import units
from . import backend

def fieldHelpText(fieldSpec, maximumOptions: int = 12) -> str:

    '''

    The hover text for a field: its help, then for a choice field the options it offers.

    Parameters:
    -----------
    fieldSpec : configSchema.Field
        The field.
    maximumOptions : int
        Options listed before the rest are counted rather than named.

    Returns:
    --------
    str : the text, empty when the field has neither help nor options

    '''

    parts = [fieldSpec.help.strip()] if fieldSpec.help else []
    if fieldSpec.kind == 'choice' and fieldSpec.choices:
        labels = fieldSpec.choiceLabels()
        listed = labels[:maximumOptions]
        options = 'Options: ' + ', '.join(listed)
        if len(labels) > maximumOptions:
            options += f', and {len(labels) - maximumOptions} more'
        if fieldSpec.editable:
            options += '. Other values can be typed in.'
        parts.append(options)

    return '\n\n'.join(parts)

class Tooltip:

    '''

    Lightweight hover tooltip. Attach one per widget; it shows after a short delay and hides on
    leave or click. Its colors are read as it opens, so it always matches the current mode.

    '''

    def __init__(self, widget, textProvider, delayMs: int = 450):

        self._widget = widget
        self._textProvider = textProvider if callable(textProvider) else (lambda: textProvider)
        self._delayMs = delayMs
        self._after = None
        self._window = None

        widget.bind('<Enter>', self._schedule, add = '+')
        widget.bind('<Leave>', self._hide, add = '+')
        widget.bind('<ButtonPress>', self._hide, add = '+')

    def _schedule(self, _event = None) -> None:

        self._cancel()
        self._after = self._widget.after(self._delayMs, self._show)

    def _cancel(self) -> None:

        if self._after is not None:
            try:
                self._widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _show(self) -> None:

        self._after = None
        text = self._textProvider()
        if not text or self._window is not None or not self._widget.winfo_exists():
            return

        x = self._widget.winfo_rootx() + theme.scaled(16)
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + theme.scaled(6)

        self._window = tk.Toplevel(self._widget)
        self._window.wm_overrideredirect(True)
        self._window.wm_geometry(f'+{x}+{y}')
        self._window.configure(bg = theme.surface2)
        self._window.update_idletasks()

        # Rounded with a palette border where Windows draws one; a one pixel square border elsewhere
        rounded = theme.roundWindow(self._window)
        if not rounded:
            self._window.configure(bg = theme.border)

        label = tk.Label(
            self._window,
            text = text,
            justify = 'left',
            wraplength = theme.scaled(380),
            bg = theme.surface2,
            fg = theme.text,
            font = theme.fontBodySm,
            padx = theme.scaled(10),
            pady = theme.scaled(7),
        )
        label.pack(padx = 0 if rounded else 1, pady = 0 if rounded else 1)

    def _hide(self, _event = None) -> None:

        self._cancel()
        if self._window is not None:
            self._window.destroy()
            self._window = None

class ScrollableFrame(ttk.Frame):

    '''

    A frame whose content scrolls vertically. Add children to `.body`.

    '''

    # Lines one wheel notch moves, as Windows sets by default, and the height of a line [px]
    wheelLines = 3
    lineHeight = 20

    def __init__(self, master, **kwargs):

        super().__init__(master, **kwargs)

        self._canvas = tk.Canvas(self, bg = theme.bg, highlightthickness = 0, bd = 0,
                                 yscrollincrement = theme.scaled(self.lineHeight))
        self._scroll = ttk.Scrollbar(self, orient = 'vertical', command = self._onScrollbar)
        self._canvas.configure(yscrollcommand = self._scroll.set)

        # Every scroll redraws the whole visible form, so input that arrives faster than the form
        # redraws is gathered and applied once the event queue is empty, rather than queuing a
        # redraw per event
        self._wheelRemainder = 0.0
        self._pendingLines = 0
        self._pendingMove = None
        self._scrollAfter = None

        # A combobox under the pointer would otherwise take the wheel and step through its options,
        # changing a value the user only meant to scroll past
        self.unbind_class('TCombobox', '<MouseWheel>')

        self._scroll.pack(side = 'right', fill = 'y')
        self._canvas.pack(side = 'left', fill = 'both', expand = True)

        self.body = ttk.Frame(self._canvas, style = 'TFrame')
        self._windowId = self._canvas.create_window((0, 0), window = self.body, anchor = 'nw')

        self.body.bind('<Configure>', self._onBodyConfigure)
        self._canvas.bind('<Configure>', self._onCanvasConfigure)
        # Wheel binding is activated only while the pointer is over this canvas so nested scroll
        # regions do not fight for the wheel.
        self._canvas.bind('<Enter>', lambda _e: self._bindWheel(True))
        self._canvas.bind('<Leave>', lambda _e: self._bindWheel(False))

        theme.addListener(self._restyle)

    def _restyle(self) -> None:

        self._canvas.configure(bg = theme.bg)

    def _onBodyConfigure(self, _event) -> None:

        self._canvas.configure(scrollregion = self._canvas.bbox('all'))

    def _onCanvasConfigure(self, event) -> None:

        self._canvas.itemconfigure(self._windowId, width = event.width)

    def _bindWheel(self, active: bool) -> None:

        if active:
            self._canvas.bind_all('<MouseWheel>', self._onWheel)
        else:
            self._canvas.unbind_all('<MouseWheel>')

    def _onWheel(self, event) -> None:

        # Windows reports 120 per notch; a precision touchpad reports a fraction of that many
        # times a second, so the remainder is kept until it adds up to a line
        self._wheelRemainder += -event.delta / 120 * self.wheelLines
        lines = int(self._wheelRemainder)
        if lines:
            self._wheelRemainder -= lines
            self._pendingLines += lines
            self._scheduleScroll()

    def _onScrollbar(self, *arguments) -> None:

        # A drag on the thumb sends a position per pointer motion; only the latest one matters.
        # Clicks on the trough come one at a time and are applied as they come.
        if arguments and arguments[0] == 'moveto':
            self._pendingMove = arguments
            self._pendingLines = 0
            self._scheduleScroll()
        else:
            self._canvas.yview(*arguments)

    def _scheduleScroll(self) -> None:

        if self._scrollAfter is None:
            self._scrollAfter = self.after_idle(self._applyScroll)

    def _applyScroll(self) -> None:

        self._scrollAfter = None
        if self._pendingMove is not None:
            self._canvas.yview(*self._pendingMove)
            self._pendingMove = None
        if self._pendingLines:
            self._canvas.yview_scroll(self._pendingLines, 'units')
            self._pendingLines = 0

def card(master, **packOptions) -> ttk.Frame:

    '''

    A rounded card frame, padded so its children sit inside the rounded border. Children use the
    `Card.` styles, or `Surface.TFrame` for frames of their own.

    '''

    frame = ttk.Frame(master, style = 'Card.TFrame', padding = theme.scaled(10))
    if packOptions:
        frame.pack(**packOptions)

    return frame

class CollapsibleSection(ttk.Frame):

    '''

    A rounded card with a clickable title row that shows and hides its body. The marker is a
    nozzle silhouette: on its side when the section is closed, flowing down when it is open.

    A nested section is the fold inside a card that holds a group's advanced settings: no card of
    its own, a quieter title, and a body that lines up with the card's own rows.

    '''

    def __init__(self, master, title: str, collapsed: bool = False, note: str = '', nested: bool = False):

        if nested:
            super().__init__(master, style = 'Surface.TFrame')
        else:
            super().__init__(master, style = 'Card.TFrame', padding = (theme.scaled(10), theme.scaled(6)))

        self._open = tk.BooleanVar(value = not collapsed)
        self._nested = nested

        self._header = ttk.Frame(self, style = 'Surface.TFrame', cursor = 'hand2')
        self._header.pack(fill = 'x')

        self._glyph = ttk.Label(self._header, style = 'Glyph.Card.TLabel', cursor = 'hand2')
        self._glyph.pack(side = 'left', padx = (theme.scaled(2), theme.scaled(8)), pady = theme.scaled(4))

        self._title = ttk.Label(self._header, text = title, cursor = 'hand2',
                                style = 'Muted.Card.TLabel' if nested else 'Heading.Card.TLabel')
        self._title.pack(side = 'left', pady = theme.scaled(4))

        for widget in (self._header, self._glyph, self._title):
            widget.bind('<Button-1>', self._toggle)

        self._rule = ttk.Separator(self, orient = 'horizontal', style = 'Card.TSeparator')
        padding = (0, theme.scaled(4), 0, 0) if nested else (theme.scaled(4), theme.scaled(8),
                                                             theme.scaled(4), theme.scaled(6))
        self.body = ttk.Frame(self, style = 'Surface.TFrame', padding = padding)

        if note:
            ttk.Label(self.body, text = note, style = 'Muted.Card.TLabel', wraplength = theme.scaled(620)).pack(
                anchor = 'w', pady = (0, theme.scaled(8)))

        self._applyOpen()

    def _applyOpen(self) -> None:

        isOpen = self._open.get()
        self._glyph.state(['selected' if isOpen else '!selected'])
        if isOpen:
            if not self._nested:
                self._rule.pack(fill = 'x', pady = (theme.scaled(4), 0))
            self.body.pack(fill = 'x')
        else:
            self._rule.pack_forget()
            self.body.pack_forget()

    def _toggle(self, _event = None) -> None:

        self._open.set(not self._open.get())
        self._applyOpen()

    def setOpen(self, isOpen: bool) -> None:

        if isOpen != self._open.get():
            self._toggle()

    @property
    def isOpen(self) -> bool:

        return self._open.get()

class FieldRow:

    '''

    Label, help marker and editor for a single configSchema.Field, laid on a card. Reads and
    writes typed values: blank numeric or text entries resolve to None, and choice fields show
    friendly labels while get() returns the backend value.

    '''

    def __init__(self, master, fieldSpec, row: int):

        self.spec = fieldSpec
        self._dimension = fieldSpec.dimension

        # The unit dropdown replaces the [unit] label suffix for dimensioned fields.
        showSuffix = fieldSpec.unit and self._dimension is None
        labelText = fieldSpec.label + (f'  [{fieldSpec.unit}]' if showSuffix else '')

        # The label and its help marker share one cell, so hiding the row hides both
        self._labelCell = ttk.Frame(master, style = 'Surface.TFrame')
        self._labelCell.grid(row = row, column = 0, sticky = 'w', padx = (0, theme.scaled(12)), pady = theme.scaled(3))
        self._label = ttk.Label(self._labelCell, text = labelText, style = 'Card.TLabel')
        self._label.pack(side = 'left')
        helpText = fieldHelpText(fieldSpec)
        self.tooltip = None
        if helpText:
            self._info = ttk.Label(self._labelCell, style = 'Info.Card.TLabel', cursor = 'question_arrow')
            self._info.pack(side = 'left')
            self.tooltip = Tooltip(self._info, helpText, delayMs = 250)

        if fieldSpec.kind == 'bool':
            self._var = tk.BooleanVar(value = self._asBool(fieldSpec.default))
            self._widget = ttk.Checkbutton(master, variable = self._var, takefocus = True, style = 'Card.TCheckbutton')
        elif fieldSpec.kind == 'choice':
            self._var = tk.StringVar(value = fieldSpec.valueToLabel(fieldSpec.default))
            self._widget = ttk.Combobox(
                master, textvariable = self._var, values = fieldSpec.choiceLabels(),
                state = 'normal' if fieldSpec.editable else 'readonly', width = 34, style = 'Card.TCombobox',
            )
        else:
            self._var = tk.StringVar(value = '' if fieldSpec.default is None else str(fieldSpec.default))
            self._widget = ttk.Entry(master, textvariable = self._var, width = 36, style = 'Card.TEntry')

        # Editors keep their own width rather than stretching across the card, so the unit box
        # sits beside the number it describes
        self._widget.grid(row = row, column = 1, sticky = 'w' if fieldSpec.kind == 'bool' else 'we',
                          pady = theme.scaled(3))
        self._visible = True

        # -- Unit selector -- #
        self._unitVar = None
        self._unitWidget = None
        if self._dimension is not None:
            self._currentUnit = units.siUnit(self._dimension)
            self._unitVar = tk.StringVar(value = self._currentUnit)
            self._unitWidget = ttk.Combobox(
                master, textvariable = self._unitVar, values = units.unitsFor(self._dimension),
                state = 'readonly', width = 12, style = 'Card.TCombobox',
            )
            self._unitWidget.grid(row = row, column = 2, sticky = 'w', padx = (theme.scaled(6), 0), pady = theme.scaled(3))
            self._unitWidget.bind('<<ComboboxSelected>>', self._onUnitChange)
            # The stored value is always SI; the entry holds it converted to _currentUnit.
            if fieldSpec.default is not None:
                self._var.set(self._formatNumber(units.fromSI(float(fieldSpec.default),
                                                              self._dimension, self._currentUnit)))

    @staticmethod
    def _asBool(value) -> bool:

        '''

        A config value as a bool. NOVA's own files write switches as 'on' and 'off', and bool()
        reads every non-empty string as True, so strings are read by their meaning.

        '''

        if isinstance(value, str):
            return value.strip().lower() in ('on', 'true', 'yes', '1')
        return bool(value)

    @staticmethod
    def _formatNumber(value) -> str:

        '''

        Compact text for a numeric value: an integer when it is one, otherwise up to ten
        significant figures.

        '''

        if value is None:
            return ''
        if abs(value - round(value)) < 1e-9 * max(1.0, abs(value)):
            return str(int(round(value)))
        return f'{value:.10g}'

    def _onUnitChange(self, _event = None) -> None:

        '''

        Convert the shown value from the previous unit to the newly selected one so the
        physical quantity is preserved.

        '''

        newUnit = self._unitVar.get()
        raw = self._var.get().strip()
        if raw not in ('', '-', '+', '.'):
            try:
                siValue = units.toSI(float(raw), self._dimension, self._currentUnit)
                self._var.set(self._formatNumber(units.fromSI(siValue, self._dimension, newUnit)))
            except ValueError:
                pass
        self._currentUnit = newUnit

    def get(self):

        '''

        Return the field value coerced to its declared kind. Blank entries for numeric and text
        fields return None so they serialize to JSON null.

        '''

        if self.spec.kind == 'bool':
            return bool(self._var.get())

        raw = self._var.get().strip()

        if self.spec.kind == 'choice':
            return None if raw == '' else self.spec.labelToValue(raw)

        if raw == '':
            return None

        if self.spec.kind == 'int':
            try:
                parsed = int(float(raw))
            except ValueError:
                raise ValueError(f"{self.spec.label}: '{raw}' is not an integer")
            return int(round(self._toSI(parsed)))
        if self.spec.kind == 'float':
            try:
                parsed = float(raw)
            except ValueError:
                raise ValueError(f"{self.spec.label}: '{raw}' is not a number")
            return self._toSI(parsed)
        if self.spec.kind == 'floatText':
            try:
                return self._toSI(float(raw))
            except ValueError:
                return raw
        return raw

    def _toSI(self, value: float) -> float:

        '''

        Convert a parsed entry value from the selected unit to the backend SI unit.

        '''

        if self._dimension is None:
            return value
        return units.toSI(value, self._dimension, self._currentUnit)

    def set(self, value) -> None:

        '''

        Populate the editor from a config value.

        '''

        if self.spec.kind == 'bool':
            self._var.set(self._asBool(value))
            return
        if self.spec.kind == 'choice':
            self._var.set(self.spec.valueToLabel(value))
            return
        if value is None:
            self._var.set('')
            return
        if self._dimension is not None:
            self._var.set(self._formatNumber(units.fromSI(float(value), self._dimension, self._currentUnit)))
            return
        if isinstance(value, float) and value.is_integer():
            self._var.set(str(int(value)))
        else:
            self._var.set(str(value))

    def highlight(self, on: bool) -> None:

        '''

        Flag or clear a validation problem on the label.

        '''

        self._label.configure(style = 'FieldError.Card.TLabel' if on else 'Card.TLabel')

    def setVisible(self, visible: bool) -> None:

        '''

        Show or hide the row. A hidden row collapses to zero height but keeps its value, so it
        round-trips through getConfig() unchanged.

        '''

        if visible == self._visible:
            return
        self._visible = visible
        for widget in (self._labelCell, self._widget, self._unitWidget):
            if widget is None:
                continue
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    @property
    def visible(self) -> bool:

        return self._visible

    @property
    def variables(self) -> tuple:

        '''The Tk variables whose writes are edits to the row.'''

        return (self._var,)

    @property
    def labelWidth(self) -> int:

        '''Width the label and its help marker ask for [px], with the gap before the editor.'''

        return self._labelCell.winfo_reqwidth() + theme.scaled(12)

    @property
    def editorWidth(self) -> int:

        '''Width the editor asks for [px]; a check box sits at the left of the column and asks for none.'''

        return 0 if self.spec.kind == 'bool' else self._widget.winfo_reqwidth()

class SelectorRow:

    '''

    A configSchema.Selector laid on a card: the option dropdown and its help marker in the label
    column, the value entry, and the unit dropdown when the chosen option's value has a unit. Each
    option keeps its own entry text and unit while another is chosen, so switching back loses
    nothing. get() returns every key the row holds, with None for the options not chosen.

    '''

    def __init__(self, master, selector, row: int):

        self.spec = selector
        self._options = {option.label: option for option in selector.options}
        labels = list(self._options)

        # What each option shows while it is not chosen: its entry text, and the unit that text is in
        self._dimensions, self._units, self._texts = {}, {}, {}
        for option in selector.options:
            unit = selector.unitFor(option)
            dimension = units.dimensionForUnit(unit) if unit else None
            self._dimensions[option.label] = dimension
            self._units[option.label] = units.siUnit(dimension) if dimension is not None else None
            self._texts[option.label] = ''

        # The dropdown fills the label column, so its options read in full
        self._cell = ttk.Frame(master, style = 'Surface.TFrame')
        self._cell.grid(row = row, column = 0, sticky = 'we', padx = (0, theme.scaled(12)), pady = theme.scaled(3))
        self._choice = tk.StringVar(value = labels[0])
        self._picker = ttk.Combobox(self._cell, textvariable = self._choice, values = labels, state = 'readonly',
                                    width = 1, style = 'Card.TCombobox')
        self._picker.pack(side = 'left', fill = 'x', expand = True)
        self._picker.bind('<<ComboboxSelected>>', self._onChoice)
        self._info = ttk.Label(self._cell, style = 'Info.Card.TLabel', cursor = 'question_arrow')
        self._info.pack(side = 'left')
        self.tooltip = Tooltip(self._info, self._helpText, delayMs = 250)

        self._var = tk.StringVar(value = '')
        self._widget = ttk.Entry(master, textvariable = self._var, width = 36, style = 'Card.TEntry')
        self._widget.grid(row = row, column = 1, sticky = 'we', pady = theme.scaled(3))

        self._unitVar = tk.StringVar(value = '')
        self._unitWidget = ttk.Combobox(master, textvariable = self._unitVar, state = 'readonly', width = 12,
                                        style = 'Card.TCombobox')
        self._unitWidget.grid(row = row, column = 2, sticky = 'w', padx = (theme.scaled(6), 0), pady = theme.scaled(3))
        self._unitWidget.bind('<<ComboboxSelected>>', self._onUnitChange)

        self._visible = True
        self._shown = labels[0]
        self.set({spec.key: spec.default for spec in selector.members})

    # -- Internals -- #

    def _helpText(self) -> str:

        '''The row's help, then the chosen option's own.'''

        parts = [self.spec.help.strip()] if self.spec.help else []
        option = self._options[self._shown]
        if option.key is not None and self.spec.member(option.key).help:
            parts.append(f'{option.label}: {self.spec.member(option.key).help.strip()}')

        return '\n\n'.join(parts)

    def _format(self, value, label: str) -> str:

        '''A config value as entry text in the unit the option shows.'''

        dimension = self._dimensions[label]
        if dimension is not None:
            value = units.fromSI(float(value), dimension, self._units[label])

        return FieldRow._formatNumber(float(value))

    def _show(self, label: str) -> None:

        '''Put an option's entry text and unit in the row.'''

        option = self._options[label]
        self._shown = label
        self._choice.set(label)
        self._var.set(self._texts[label])
        self._widget.state(['!disabled'] if option.key is not None else ['disabled'])

        dimension = self._dimensions[label]
        if dimension is not None:
            self._unitWidget.configure(values = units.unitsFor(dimension))
            self._unitVar.set(self._units[label])
        self._placeUnit()

    def _placeUnit(self) -> None:

        if self._visible and self._dimensions[self._shown] is not None:
            self._unitWidget.grid()
        else:
            self._unitWidget.grid_remove()

    def _onChoice(self, _event = None) -> None:

        self._texts[self._shown] = self._var.get()
        self._show(self._choice.get())

    def _onUnitChange(self, _event = None) -> None:

        '''Convert the shown value to the newly chosen unit, so the quantity is kept.'''

        label, dimension = self._shown, self._dimensions[self._shown]
        newUnit = self._unitVar.get()
        raw = self._var.get().strip()
        if raw not in ('', '-', '+', '.'):
            try:
                siValue = units.toSI(float(raw), dimension, self._units[label])
                self._var.set(FieldRow._formatNumber(units.fromSI(siValue, dimension, newUnit)))
            except ValueError:
                pass
        self._units[label] = newUnit

    # -- Public API -- #

    @property
    def selectedLabel(self) -> str:

        return self._shown

    def get(self) -> dict:

        '''

        Every key the row holds: the chosen option's value in SI and the constants it fixes, and
        None for the rest. A blank entry is None. Raises ValueError for an entry that is not a number.

        '''

        option = self._options[self._shown]
        values = {key: None for key in self.spec.keys()}
        values.update(option.sets)

        raw = self._var.get().strip()
        if option.key is not None and raw:
            try:
                number = float(raw)
            except ValueError:
                raise ValueError(f"{option.label}: '{raw}' is not a number")
            dimension = self._dimensions[option.label]
            if dimension is not None:
                number = units.toSI(number, dimension, self._units[option.label])
            values[option.key] = int(round(number)) if self.spec.member(option.key).kind == 'int' else number

        return values

    def set(self, config: dict) -> None:

        '''

        Choose the option a config describes and fill every option's entry from it. The option
        chosen is the first whose constants the config matches and whose value it sets; then the
        first whose constants it matches (a mode given without its value); then the row's blank one.

        '''

        def matches(option) -> bool:
            return all(config.get(key) == value for key, value in option.sets.items())

        options = self.spec.options
        chosen = next((option for option in options
                       if matches(option) and (option.key is None or config.get(option.key) is not None)), None)
        if chosen is None:
            chosen = next((option for option in options if option.sets and matches(option)), None)
        if chosen is None:
            chosen = self._options.get(self.spec.blank, options[0])

        for option in options:
            value = config.get(option.key) if option.key is not None and matches(option) else None
            self._texts[option.label] = '' if value is None else self._format(value, option.label)
        self._show(chosen.label)

    def highlight(self, on: bool) -> None:

        '''Flag or clear a validation problem on the chosen option.'''

        self._picker.configure(style = 'FieldError.Card.TCombobox' if on else 'Card.TCombobox')

    def setVisible(self, visible: bool) -> None:

        '''Show or hide the row, keeping its values.'''

        if visible == self._visible:
            return
        self._visible = visible
        for widget in (self._cell, self._widget):
            if visible:
                widget.grid()
            else:
                widget.grid_remove()
        self._placeUnit()

    @property
    def visible(self) -> bool:

        return self._visible

    @property
    def variables(self) -> tuple:

        '''The Tk variables whose writes are edits to the row.'''

        return (self._var, self._choice)

    @property
    def labelWidth(self) -> int:

        '''The dropdown takes whatever width the label column has, so it asks for none.'''

        return 0

    @property
    def editorWidth(self) -> int:

        '''Width the value entry asks for [px].'''

        return self._widget.winfo_reqwidth()

class MaterialInfoPanel(ttk.Frame):

    '''

    Sampled wall-alloy properties for the currently selected material, from
    materials.sampleWallMaterial: thermal conductivity, density, modulus, yield and CTE at a chosen
    reference temperature, plus the data source. An inset panel inside the cooling card. Refreshes
    on material change and on its own temperature control.

    '''

    def __init__(self, master):

        super().__init__(master, style = 'Inset.TFrame', padding = (theme.scaled(12), theme.scaled(10)))

        self._materialName = 'GRCop-42'

        header = ttk.Frame(self, style = 'TFrame')
        header.pack(fill = 'x')
        ttk.Label(header, text = 'SAMPLED PROPERTIES', style = 'Eyebrow.TLabel').pack(side = 'left')
        ttk.Label(header, text = '   at', style = 'Muted.TLabel').pack(side = 'left')
        self._temperatureVar = tk.StringVar(value = '300')
        temperatureEntry = ttk.Entry(header, textvariable = self._temperatureVar, width = 6)
        temperatureEntry.pack(side = 'left', padx = theme.scaled(4))
        self._temperatureUnit = tk.StringVar(value = 'K')
        unitBox = ttk.Combobox(header, textvariable = self._temperatureUnit, width = 6, state = 'readonly',
                               values = units.unitsFor('temperature'))
        unitBox.pack(side = 'left')
        temperatureEntry.bind('<KeyRelease>', lambda _e: self.refresh())
        temperatureEntry.bind('<Return>', lambda _e: self.refresh())
        unitBox.bind('<<ComboboxSelected>>', lambda _e: self.refresh())

        self._body = ttk.Label(self, style = 'Value.TLabel', justify = 'left', anchor = 'w')
        self._body.pack(fill = 'x', pady = (theme.scaled(6), 0))
        self._note = ttk.Label(self, style = 'Muted.TLabel', justify = 'left',
                               wraplength = theme.scaled(560), anchor = 'w')
        self._note.pack(fill = 'x', pady = (theme.scaled(4), 0))

        self.refresh()

    def setMaterial(self, materialName: str) -> None:

        '''

        Point the panel at a new material and re-sample.

        '''

        if materialName and materialName != self._materialName:
            self._materialName = materialName
            self.refresh()

    def refresh(self) -> None:

        try:
            temperature = float(self._temperatureVar.get())
            temperatureKelvin = units.toSI(temperature, 'temperature', self._temperatureUnit.get())
        except ValueError:
            temperatureKelvin = 300.0

        try:
            materials = backend.materialsModule()
            sample = materials.sampleWallMaterial(self._materialName, temperatureKelvin)
        except Exception as error:                          # noqa: BLE001 -- optional panel
            self._body.configure(text = '')
            self._note.configure(text = f'Material data unavailable: {error}', style = 'Warn.TLabel')
            return

        self._body.configure(text = (
            f"k  {sample['thermalConductivity']:.0f} W/m-K       "
            f"rho  {sample['density']:.0f} kg/m3       "
            f"E  {sample['elasticModulus'] / 1e9:.0f} GPa\n"
            f"yield  {sample['yieldStrength'] / 1e6:.0f} MPa       "
            f"CTE  {sample['cte'] * 1e6:.1f} 1e-6/K       "
            f"elong  {sample['elongation']:.0f} %"
        ))

        note = f"resolved as {sample['material']} @ {sample['temperatureK']:.0f} K  --  {sample['source']}"
        if sample['fallback']:
            note = f"'{self._materialName}' not in the database; showing GRCop-42.  {sample['source']}"
        self._note.configure(text = note, style = 'Warn.TLabel' if sample['fallback'] else 'Muted.TLabel')

class ConsolePane(ttk.Frame):

    '''

    Read-only monospace log surface with autoscroll and a clear action.

    '''

    def __init__(self, master, height: int = 10):

        super().__init__(master, style = 'TFrame')

        bar = ttk.Frame(self, style = 'Header.TFrame')
        bar.pack(fill = 'x')
        ttk.Label(bar, text = 'RUN LOG', style = 'Eyebrow.Header.TLabel').pack(
            side = 'left', padx = theme.scaled(10), pady = theme.scaled(4))
        ttk.Button(bar, text = 'Clear', command = self.clear, style = 'Small.Header.TButton').pack(
            side = 'right', padx = theme.scaled(6), pady = theme.scaled(3))

        self._text = tk.Text(self, height = height, wrap = 'none', state = 'disabled')
        yscroll = ttk.Scrollbar(self, orient = 'vertical', command = self._text.yview)
        self._text.configure(yscrollcommand = yscroll.set)
        yscroll.pack(side = 'right', fill = 'y')
        self._text.pack(side = 'left', fill = 'both', expand = True)

        self._restyle()
        theme.addListener(self._restyle)

    def _restyle(self) -> None:

        self._text.configure(bg = theme.surface, fg = theme.text, insertbackground = theme.accent,
                             selectbackground = theme.accentMuted, selectforeground = theme.selectedText,
                             padx = theme.scaled(8), pady = theme.scaled(4))
        self._text.tag_configure('err', foreground = theme.red)
        self._text.tag_configure('ok', foreground = theme.green)
        self._text.tag_configure('info', foreground = theme.accent)

    def append(self, line: str, tag: str = None) -> None:

        self._text.configure(state = 'normal')
        self._text.insert('end', line if line.endswith('\n') else line + '\n', tag or ())
        self._text.see('end')
        self._text.configure(state = 'disabled')

    def clear(self) -> None:

        self._text.configure(state = 'normal')
        self._text.delete('1.0', 'end')
        self._text.configure(state = 'disabled')

    def text(self) -> str:

        '''The log as it stands.'''

        return self._text.get('1.0', 'end-1c')
