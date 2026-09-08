# -- NOVA GUI Reusable Widgets -- #

'''

Small widget helpers shared across the tabs:

    Tooltip            hover help bound to any widget
    ScrollableFrame    vertically scrolling container with a themed scrollbar
    CollapsibleSection titled block that expands and collapses on click
    FieldRow           label + editor for one configSchema.Field, with typed get/set
    ConsolePane        read-only monospace log with autoscroll

Author: Sean Bowman
Date:   08/28/2026

'''

import tkinter as tk
from tkinter import ttk

from . import theme
from . import units
from . import backend

class Tooltip:

    '''

    Lightweight hover tooltip. Attach one per widget; it shows after a short
    delay and hides on leave or click.

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
            self._widget.after_cancel(self._after)
            self._after = None

    def _show(self) -> None:

        text = self._textProvider()
        if not text or self._window is not None:
            return

        x = self._widget.winfo_rootx() + 16
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 6

        self._window = tk.Toplevel(self._widget)
        self._window.wm_overrideredirect(True)
        self._window.wm_geometry(f'+{x}+{y}')
        self._window.configure(bg = theme.border)

        label = tk.Label(
            self._window,
            text = text,
            justify = 'left',
            wraplength = theme.scaled(360),
            bg = theme.surface2,
            fg = theme.text,
            font = theme.fontBodySm,
            padx = 8,
            pady = 5,
        )
        label.pack(padx = 1, pady = 1)

    def _hide(self, _event = None) -> None:

        self._cancel()
        if self._window is not None:
            self._window.destroy()
            self._window = None

class ScrollableFrame(ttk.Frame):

    '''

    A frame whose content scrolls vertically. Add children to `.body`.

    '''

    def __init__(self, master, **kwargs):

        super().__init__(master, **kwargs)

        self._canvas = tk.Canvas(self, bg = theme.bg, highlightthickness = 0, bd = 0)
        self._scroll = ttk.Scrollbar(self, orient = 'vertical', command = self._canvas.yview)
        self._canvas.configure(yscrollcommand = self._scroll.set)

        self._scroll.pack(side = 'right', fill = 'y')
        self._canvas.pack(side = 'left', fill = 'both', expand = True)

        self.body = ttk.Frame(self._canvas, style = 'TFrame')
        self._windowId = self._canvas.create_window((0, 0), window = self.body, anchor = 'nw')

        self.body.bind('<Configure>', self._onBodyConfigure)
        self._canvas.bind('<Configure>', self._onCanvasConfigure)
        # Wheel binding is activated only while the pointer is over this canvas
        # so nested scroll regions do not fight for the wheel.
        self._canvas.bind('<Enter>', lambda _e: self._bindWheel(True))
        self._canvas.bind('<Leave>', lambda _e: self._bindWheel(False))

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

        self._canvas.yview_scroll(int(-event.delta / 120), 'units')

class CollapsibleSection(ttk.Frame):

    '''

    A titled section with a clickable header that toggles its body.

    '''

    def __init__(self, master, title: str, collapsed: bool = False, note: str = ''):

        super().__init__(master, style = 'TFrame')

        self._open = tk.BooleanVar(value = not collapsed)

        self._header = ttk.Frame(self, style = 'Elevated.TFrame')
        self._header.pack(fill = 'x')

        self._arrow = ttk.Label(self._header, text = self._glyph(), style = 'Heading.TLabel',
                                background = theme.surface2, foreground = theme.accent)
        self._arrow.pack(side = 'left', padx = (10, 6), pady = 6)

        self._title = ttk.Label(self._header, text = title, style = 'Heading.TLabel',
                                background = theme.surface2)
        self._title.pack(side = 'left', pady = 6)

        for widget in (self._header, self._arrow, self._title):
            widget.bind('<Button-1>', self._toggle)

        self.body = ttk.Frame(self, style = 'TFrame', padding = (14, 8, 8, 12))

        if note:
            ttk.Label(self.body, text = note, style = 'Muted.TLabel', wraplength = theme.scaled(620)).pack(
                anchor = 'w', pady = (0, 8))

        if self._open.get():
            self.body.pack(fill = 'x')

    def _glyph(self) -> str:

        return '▼' if self._open.get() else '▶'

    def _toggle(self, _event = None) -> None:

        self._open.set(not self._open.get())
        self._arrow.configure(text = self._glyph())
        if self._open.get():
            self.body.pack(fill = 'x')
        else:
            self.body.forget()

    def setOpen(self, isOpen: bool) -> None:

        if isOpen != self._open.get():
            self._toggle()

class FieldRow:

    '''

    Label plus editor for a single configSchema.Field. Reads and writes typed
    values: blank numeric or text entries resolve to None, and choice fields
    show friendly labels while get() returns the backend value.

    '''

    def __init__(self, master, fieldSpec, row: int):

        self.spec = fieldSpec
        self._dimension = fieldSpec.dimension

        # The unit dropdown replaces the [unit] label suffix for dimensioned fields.
        showSuffix = fieldSpec.unit and self._dimension is None
        labelText = fieldSpec.label + (f'  [{fieldSpec.unit}]' if showSuffix else '')

        self._label = ttk.Label(master, text = labelText, style = 'TLabel')
        self._label.grid(row = row, column = 0, sticky = 'w', padx = (0, 12), pady = 3)

        if fieldSpec.kind == 'bool':
            self._var = tk.BooleanVar(value = bool(fieldSpec.default))
            self._widget = ttk.Checkbutton(master, variable = self._var, takefocus = True)
        elif fieldSpec.kind == 'choice':
            self._var = tk.StringVar(value = fieldSpec.valueToLabel(fieldSpec.default))
            self._widget = ttk.Combobox(
                master, textvariable = self._var, values = fieldSpec.choiceLabels(),
                state = 'normal' if fieldSpec.editable else 'readonly', width = 26,
            )
        else:
            self._var = tk.StringVar(value = '' if fieldSpec.default is None else str(fieldSpec.default))
            self._widget = ttk.Entry(master, textvariable = self._var, width = 24)

        self._widget.grid(row = row, column = 1, sticky = 'ew', pady = 3)
        self._visible = True

        # -- Unit selector -- #
        self._unitVar = None
        self._unitWidget = None
        if self._dimension is not None:
            self._currentUnit = units.siUnit(self._dimension)
            self._unitVar = tk.StringVar(value = self._currentUnit)
            self._unitWidget = ttk.Combobox(
                master, textvariable = self._unitVar, values = units.unitsFor(self._dimension),
                state = 'readonly', width = 6,
            )
            self._unitWidget.grid(row = row, column = 2, sticky = 'w', padx = (6, 0), pady = 3)
            self._unitWidget.bind('<<ComboboxSelected>>', self._onUnitChange)
            # The stored value is always SI; the entry holds it converted to _currentUnit.
            if fieldSpec.default is not None:
                self._var.set(self._formatNumber(units.fromSI(float(fieldSpec.default),
                                                              self._dimension, self._currentUnit)))

        if fieldSpec.help:
            Tooltip(self._label, fieldSpec.help)
            Tooltip(self._widget, fieldSpec.help)

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

        Return the field value coerced to its declared kind. Blank entries for
        numeric and text fields return None so they serialize to JSON null.

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
            self._var.set(bool(value) if value is not None else False)
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

        self._label.configure(foreground = theme.red if on else theme.text)

    def setVisible(self, visible: bool) -> None:

        '''

        Show or hide the row. A hidden row collapses to zero height but keeps its
        value, so it round-trips through getConfig() unchanged.

        '''

        if visible == self._visible:
            return
        self._visible = visible
        if visible:
            self._label.grid()
            self._widget.grid()
            if self._unitWidget is not None:
                self._unitWidget.grid()
        else:
            self._label.grid_remove()
            self._widget.grid_remove()
            if self._unitWidget is not None:
                self._unitWidget.grid_remove()

    @property
    def visible(self) -> bool:

        return self._visible

class MaterialInfoPanel(ttk.Frame):

    '''

    Sampled wall-alloy properties for the currently selected material, from
    materials.sampleWallMaterial. Shows thermal conductivity, density, modulus, yield and CTE
    at a chosen reference temperature, plus the data source. Refreshes on material change and
    on its own temperature control.

    '''

    def __init__(self, master):

        super().__init__(master, style = 'Surface.TFrame', padding = (10, 8))

        self._materialName = 'GRCop-42'

        header = ttk.Frame(self, style = 'Surface.TFrame')
        header.pack(fill = 'x')
        ttk.Label(header, text = 'SAMPLED PROPERTIES', style = 'Eyebrow.TLabel',
                  background = theme.surface).pack(side = 'left')
        ttk.Label(header, text = '   at', style = 'SurfaceMuted.TLabel').pack(side = 'left')
        self._temperatureVar = tk.StringVar(value = '300')
        temperatureEntry = ttk.Entry(header, textvariable = self._temperatureVar, width = 6)
        temperatureEntry.pack(side = 'left', padx = 4)
        self._temperatureUnit = tk.StringVar(value = 'K')
        unitBox = ttk.Combobox(header, textvariable = self._temperatureUnit, width = 5, state = 'readonly',
                               values = units.unitsFor('temperature'))
        unitBox.pack(side = 'left')
        temperatureEntry.bind('<KeyRelease>', lambda _e: self.refresh())
        temperatureEntry.bind('<Return>', lambda _e: self.refresh())
        unitBox.bind('<<ComboboxSelected>>', lambda _e: self.refresh())

        self._body = ttk.Label(self, style = 'Value.TLabel', justify = 'left', anchor = 'w')
        self._body.pack(fill = 'x', pady = (6, 0))
        self._note = ttk.Label(self, style = 'SurfaceMuted.TLabel', justify = 'left',
                               wraplength = theme.scaled(560), anchor = 'w')
        self._note.pack(fill = 'x', pady = (4, 0))

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
            self._note.configure(text = f'Material data unavailable: {error}')
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
        self._note.configure(text = note, foreground = theme.yellow if sample['fallback'] else theme.textMuted)

class ConsolePane(ttk.Frame):

    '''

    Read-only monospace log surface with autoscroll and a clear action.

    '''

    def __init__(self, master, height: int = 10):

        super().__init__(master, style = 'TFrame')

        bar = ttk.Frame(self, style = 'Elevated.TFrame')
        bar.pack(fill = 'x')
        ttk.Label(bar, text = 'RUN LOG', style = 'Eyebrow.TLabel', background = theme.surface2).pack(
            side = 'left', padx = 10, pady = 4)
        ttk.Button(bar, text = 'Clear', command = self.clear, width = 7).pack(
            side = 'right', padx = 6, pady = 3)

        self._text = tk.Text(self, height = height, wrap = 'none', state = 'disabled')
        yscroll = ttk.Scrollbar(self, orient = 'vertical', command = self._text.yview)
        self._text.configure(yscrollcommand = yscroll.set)
        yscroll.pack(side = 'right', fill = 'y')
        self._text.pack(side = 'left', fill = 'both', expand = True)

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
