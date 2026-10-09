
# -- NOVA GUI Theme -- #

'''

The Engineering Flat Metal theme for the NOVA GUI, in a dark mode (gunmetal, the default) and a
light mode (brushed aluminum), with matte aged copper as the one accent. Status colors keep a
fixed meaning in both: green is pass and complete only, red error, yellow warning.

Each mode is its own ttk theme, built once on top of 'clam' and switched with `theme_use`, which
restyles every ttk widget in place. Buttons, fields, check indicators, tabs, cards, the progress
bar and scrollbar thumbs are image elements drawn by `themeImages`, which is how they get rounded
corners. A transparent corner shows the style's own background rather than whatever is behind the
widget, so every style is named for the container it sits on:

    (no prefix)   the page, `bg`               TButton, TEntry, TLabel ...
    Card.         a card, `surface`            Card.TButton, Card.TEntry, Muted.Card.TLabel ...
    Header.       the header strip, `surface2` Header.TButton, Wordmark.Header.TLabel ...

No widget sets a color of its own; it names a style, so a mode change reaches it. The few classic
Tk widgets that ttk does not style (the scrolling canvas, the run log, the plot panes) register a
listener with `addListener` and recolor themselves when the mode changes.

`matplotlibRcParams`, `styleFigure` and `styleAxes` carry the same palette into embedded figures.
The palette is the same one `NOVA.palette` gives NOVA's own figures; `tests/testGuiSchema.py` holds
the two in step, because the GUI opens without importing NOVA.

Author: Sean Bowman
Date:   08/28/2026

'''

import sys
import weakref

from tkinter import ttk

# -- Display scaling -- #

# Set by applyTheme() from the real screen DPI. Other modules read it to size things Tk does not
# scale: Matplotlib figure DPI, wrap lengths, image sizes, the default window geometry.
uiScale = 1.0

# -- Palettes -- #

# The Engineering Flat Metal palette (NOVA.palette), plus two roles the GUI needs: the text drawn
# on an accent fill, and the text of a selected tab or view, which accent on accent-muted is too
# faint to carry in dark mode.
palettes = {
    'dark': {
        'bg': '#1C1E22', 'surface': '#24272C', 'surface2': '#2D3136', 'border': '#3D4148',
        'text': '#DCE1E6', 'textMuted': '#9098A0', 'textDim': '#5C636B',
        'accent': '#B5722E', 'accentDim': '#8F5A22', 'accentMuted': '#3A2E1E',
        'green': '#6E9B85', 'red': '#B5493D', 'yellow': '#C2A05A', 'blue': '#6E88A3',
        'orange': '#C08040', 'purple': '#8C7A96', 'cyan': '#6E9B95',
        'onAccent': '#111111', 'selectedText': '#DCE1E6',
    },
    'light': {
        'bg': '#E8E9EA', 'surface': '#F5F5F6', 'surface2': '#DADDDF', 'border': '#C2C6C9',
        'text': '#24272B', 'textMuted': '#5B6167', 'textDim': '#868C91',
        'accent': '#8A4E1F', 'accentDim': '#6E3E18', 'accentMuted': '#F0DFC9',
        'green': '#4F7A65', 'red': '#8E362C', 'yellow': '#8A6B25', 'blue': '#4C6478',
        'orange': '#8F5426', 'purple': '#6B5A72', 'cyan': '#4C726C',
        'onAccent': '#F5F5F6', 'selectedText': '#8A4E1F',
    },
}

# The names every palette defines, bound as module attributes for the active mode by _bindPalette
mode = 'dark'
bg = surface = surface2 = border = text = textMuted = textDim = ''
accent = accentDim = accentMuted = accentBg = ''
green = red = yellow = blue = orange = purple = cyan = onAccent = selectedText = ''

def _bindPalette(newMode: str) -> None:

    global mode, accentBg

    if newMode not in palettes:
        raise ValueError(f"Theme mode must be one of {', '.join(palettes)}, not {newMode!r}.")
    mode = newMode
    globals().update(palettes[newMode])
    accentBg = palettes[newMode]['accentMuted']

_bindPalette('dark')

# Typography. These are the 96 dpi base sizes; applyTheme() rebinds each name to the DPI-scaled
# tuple before any widget is styled.
fontBody     = ('Segoe UI', 10)
fontBodySm   = ('Segoe UI', 9)
fontHeading  = ('Segoe UI Semibold', 11)
fontEyebrow  = ('Segoe UI', 8)
fontMono     = ('Consolas', 9)
fontStrong   = ('Segoe UI Semibold', 10)
fontWordmark = ('Share Tech Mono', 15, 'bold')   # falls back to Consolas if absent

_baseFonts = {
    'fontBody':     fontBody,
    'fontBodySm':   fontBodySm,
    'fontHeading':  fontHeading,
    'fontEyebrow':  fontEyebrow,
    'fontMono':     fontMono,
    'fontStrong':   fontStrong,
    'fontWordmark': fontWordmark,
}

# -- Change listeners -- #

_listeners = []

def addListener(callback) -> None:

    '''

    Call `callback()` after every mode change. Bound methods are held weakly, so a destroyed
    widget's listener lapses by itself; a callback raising TclError is dropped the same way.

    '''

    if hasattr(callback, '__self__'):
        _listeners.append(weakref.WeakMethod(callback))
    else:
        _listeners.append(lambda: callback)

def _notifyListeners() -> None:

    alive = []
    for reference in _listeners:
        callback = reference()
        if callback is None:
            continue
        try:
            callback()
        except Exception:                                  # noqa: BLE001 -- a dead widget must not stop the rest
            continue
        alive.append(reference)
    _listeners[:] = alive

#----------------------------------------------------------------------#
# -- Display -- #
#----------------------------------------------------------------------#

def enableDpiAwareness() -> None:

    '''

    Opt the process into per-monitor DPI awareness. Must be called BEFORE the Tk root is
    constructed, otherwise Windows composites the window from a 96 dpi bitmap and every widget
    and plot is blurry on a high-DPI display.

    Awareness alone does not resize anything: Tk keeps reporting logical pixels, so the window
    comes out physically small. applyTheme() does the compensating scaling.

    '''

    if sys.platform != 'win32':
        return

    import ctypes

    # Per-monitor v2 where available (correct behavior when dragged between monitors), falling
    # back through per-monitor v1 to the system-wide call on older Windows.
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass

def _resolveScale(root) -> float:

    '''

    Screen DPI as a multiple of the 96 dpi the base sizes assume. Clamped so a bad reading cannot
    produce an unusable window.

    '''

    try:
        dotsPerInch = float(root.winfo_fpixels('1i'))
    except Exception:
        return 1.0
    if not 48.0 < dotsPerInch < 600.0:
        return 1.0
    return min(3.0, max(1.0, dotsPerInch / 96.0))

def scaled(value: float) -> int:

    '''

    A pixel dimension scaled to the current display, rounded to whole pixels.

    '''

    return int(round(value * uiScale))

def _dwmSetHandle(handle: int, attribute: int, value: int) -> bool:

    '''Set one DWM attribute on a native window handle; False where DWM is unavailable.'''

    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        data = ctypes.c_int(value)
        return ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, attribute, ctypes.byref(data),
                                                          ctypes.sizeof(data)) == 0
    except Exception:                                      # noqa: BLE001 -- cosmetic only
        return False

def _dwmSet(window, attribute: int, value: int) -> bool:

    '''Set one DWM window attribute on a Tk toplevel's frame.'''

    try:
        return _dwmSetHandle(int(window.wm_frame(), 16), attribute, value)
    except Exception:                                      # noqa: BLE001
        return False

def _colorRef(color: str) -> int:

    color = color.lstrip('#')

    return int(color[4:6], 16) << 16 | int(color[2:4], 16) << 8 | int(color[0:2], 16)

def styleTitleBar(window) -> None:

    '''Draw the window's own title bar dark in dark mode and light in light mode (Windows 10 and 11).'''

    if not _dwmSet(window, 20, 1 if mode == 'dark' else 0):
        return
    # The caption itself in the header color, over whatever accent Windows would paint it
    _dwmSet(window, 35, _colorRef(surface2))
    _dwmSet(window, 36, _colorRef(text))
    # Windows repaints the frame only when told it changed
    try:
        import ctypes
        flags = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020   # no size, move, z-order or activation; frame changed
        ctypes.windll.user32.SetWindowPos(int(window.wm_frame(), 16), 0, 0, 0, 0, 0, flags)
    except Exception:                                      # noqa: BLE001 -- cosmetic only
        pass

def roundWindow(window) -> bool:

    '''

    Round a borderless toplevel's corners and draw its border in the palette, through DWM on
    Windows 11. Returns False where that is unavailable, so the caller can draw a square border.

    '''

    try:
        return roundHandle(int(window.wm_frame(), 16))
    except Exception:                                      # noqa: BLE001
        return False

def roundHandle(handle: int) -> bool:

    '''`roundWindow` for a native window handle, for toplevels Tk builds that Python never sees.'''

    rounded = _dwmSetHandle(handle, 33, 3)               # DWMWCP_ROUNDSMALL
    if rounded:
        _dwmSetHandle(handle, 34, _colorRef(border))
    return rounded

#----------------------------------------------------------------------#
# -- Building and switching the theme -- #
#----------------------------------------------------------------------#

def applyTheme(root, newMode: str = 'dark') -> None:

    '''

    Size the fonts for the display and apply a mode to a Tk root. Call once, before any widget is
    built; `setMode` switches afterwards.

    Parameters:
    -----------
    root : tk.Tk
        The application root window.
    newMode : str
        'dark' or 'light'.

    '''

    global uiScale

    uiScale = _resolveScale(root)

    # Tk sizes fonts in points against an assumed 72 dpi; tell it the real value so a
    # point-specified font comes out the right physical size.
    try:
        root.tk.call('tk', 'scaling', float(root.winfo_fpixels('1i')) / 72.0)
    except Exception:
        pass

    for name, base in _baseFonts.items():
        family, size = base[0], base[1]
        rest = tuple(base[2:])
        globals()[name] = (family, max(6, int(round(size * uiScale)))) + rest

    setMode(root, newMode, notify = False)

def setMode(root, newMode: str, notify: bool = True, matplotlib: bool = True) -> None:

    '''

    Switch every widget to a mode. ttk widgets restyle through `theme_use`; the classic widgets
    that registered a listener recolor themselves after it.

    Parameters:
    -----------
    root : tk.Tk
        The application root window.
    newMode : str
        'dark' or 'light'.
    notify : bool
        Call the registered listeners.
    matplotlib : bool
        Update Matplotlib's rcParams. A caller holds this back while a run is drawing figures on
        its worker thread, because those parameters are global.

    '''

    _bindPalette(newMode)

    style = ttk.Style(root)
    name = 'nova' + newMode.capitalize()
    images = None
    if name not in style.theme_names():
        style.theme_create(name, parent = 'clam')
        style.theme_use(name)
        from . import themeImages
        images = themeImages.buildImages(root, newMode, palettes[newMode], uiScale)
        _createElements(style, images)
    else:
        style.theme_use(name)
        from . import themeImages
        images = themeImages.buildImages(root, newMode, palettes[newMode], uiScale)

    _configureStyles(style, images)
    _applyOptionDefaults(root)
    _restylePopdowns(root)
    root.configure(bg = bg)
    styleTitleBar(root)

    if matplotlib:
        applyMatplotlib()
    if notify:
        _notifyListeners()

def applyMatplotlib() -> None:

    '''Carry the active mode into Matplotlib's rcParams, if Matplotlib has been imported.'''

    module = sys.modules.get('matplotlib')
    if module is not None:
        module.rcParams.update(matplotlibRcParams())

def _createElements(style, img: dict) -> None:

    '''

    The rounded image elements, created once inside each mode's theme. Element names end in the
    stock element's name, because ttk's own bindings find a combobox arrow or a scrollbar thumb
    by that suffix.

    '''

    from . import themeImages

    borders = themeImages.elementBorders(uiScale)
    corner, minimum = borders['control'], borders['controlMinimum']

    def element(name, base, *states, border = corner, width = minimum, height = minimum):
        style.element_create(name, 'image', img[base], *states, border = border, sticky = 'nsew',
                             width = width, height = height)

    element('Nova.Button.border', 'button',
            ('disabled', img['button.disabled']), ('pressed', '!disabled', img['button.pressed']),
            ('active', '!disabled', img['button.active']))
    element('NovaHeader.Button.border', 'headerButton',
            ('pressed', '!disabled', img['headerButton.pressed']), ('active', '!disabled', img['headerButton.active']))
    element('NovaAccent.Button.border', 'accent',
            ('disabled', img['accent.disabled']), ('pressed', '!disabled', img['accent.active']),
            ('active', '!disabled', img['accent.active']))

    for prefix, base in (('Nova', 'field'), ('NovaCard', 'cardField')):
        for widget in ('Entry', 'Combobox'):
            element(f'{prefix}.{widget}.field', base,
                    ('disabled', img[f'{base}.disabled']), ('focus', img[f'{base}.focus']),
                    ('hover', img[f'{base}.hover']))

    style.element_create('Nova.Combobox.downarrow', 'image', img['arrow'],
                         ('pressed', img['arrow.active']), ('active', img['arrow.active']), sticky = '')

    element('Nova.Card.border', 'card', border = borders['card'],
            width = borders['cardMinimum'], height = borders['cardMinimum'])
    element('Nova.Inset.border', 'inset', border = borders['card'],
            width = borders['cardMinimum'], height = borders['cardMinimum'])

    element('Nova.Notebook.tab', 'tab', ('selected', img['tab.selected']), ('active', img['tab.active']),
            border = borders['tab'], width = borders['tabMinimum'][0], height = borders['tabMinimum'][1])
    element('Nova.Nav.border', 'nav', ('selected', img['nav.selected']), ('active', '!disabled', img['nav.active']))

    style.element_create('Nova.Horizontal.Progressbar.trough', 'image', img['trough'],
                         border = borders['bar'], sticky = 'nsew')
    style.element_create('Nova.Horizontal.Progressbar.pbar', 'image', img['bar'],
                         border = borders['bar'], sticky = 'nsew')
    style.element_create('Nova.Vertical.Scrollbar.thumb', 'image', img['thumb'],
                         ('pressed', img['thumb.active']), ('active', img['thumb.active']),
                         border = borders['thumb'], sticky = 'nsew')
    style.element_create('Nova.Horizontal.Scrollbar.thumb', 'image', img['hthumb'],
                         ('pressed', img['hthumb.active']), ('active', img['hthumb.active']),
                         border = borders['thumb'], sticky = 'nsew')

    style.element_create('Nova.Checkbutton.indicator', 'image', img['check'],
                         ('disabled', img['check.disabled']), ('selected', img['check.selected']),
                         ('alternate', img['check.alternate']), ('active', img['check.active']), sticky = '')

    # -- Layouts -- #

    def buttonLayout(border):
        return [(border, {'sticky': 'nswe', 'children': [
            ('Button.padding', {'sticky': 'nswe', 'children': [('Button.label', {'sticky': 'nswe'})]})]})]

    style.layout('TButton', buttonLayout('Nova.Button.border'))
    style.layout('Header.TButton', buttonLayout('NovaHeader.Button.border'))
    style.layout('Accent.TButton', buttonLayout('NovaAccent.Button.border'))

    for prefix, stylePrefix in (('Nova', ''), ('NovaCard', 'Card.')):
        style.layout(f'{stylePrefix}TEntry', [(f'{prefix}.Entry.field', {'sticky': 'nswe', 'children': [
            ('Entry.padding', {'sticky': 'nswe', 'children': [('Entry.textarea', {'sticky': 'nswe'})]})]})])
        style.layout(f'{stylePrefix}TCombobox', [(f'{prefix}.Combobox.field', {'sticky': 'nswe', 'children': [
            ('Nova.Combobox.downarrow', {'side': 'right', 'sticky': 'ns'}),
            ('Combobox.padding', {'sticky': 'nswe', 'children': [('Combobox.textarea', {'sticky': 'nswe'})]})]})])

    style.layout('Card.TFrame', [('Nova.Card.border', {'sticky': 'nswe'})])
    style.layout('Inset.TFrame', [('Nova.Inset.border', {'sticky': 'nswe'})])

    style.layout('TNotebook.Tab', [('Nova.Notebook.tab', {'sticky': 'nswe', 'children': [
        ('Notebook.padding', {'side': 'top', 'sticky': 'nswe', 'children': [
            ('Notebook.label', {'side': 'top', 'sticky': ''})]})]})])
    style.layout('Nav.Toolbutton', [('Nova.Nav.border', {'sticky': 'nswe', 'children': [
        ('Toolbutton.padding', {'sticky': 'nswe', 'children': [('Toolbutton.label', {'sticky': 'w'})]})]})])

    style.layout('Horizontal.TProgressbar', [('Nova.Horizontal.Progressbar.trough', {'sticky': 'nswe', 'children': [
        ('Nova.Horizontal.Progressbar.pbar', {'side': 'left', 'sticky': 'ns'})]})])

    for prefix in ('', 'Card.'):
        style.layout(f'{prefix}Vertical.TScrollbar', [('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children': [
            ('Nova.Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
        style.layout(f'{prefix}Horizontal.TScrollbar', [('Horizontal.Scrollbar.trough', {'sticky': 'ew', 'children': [
            ('Nova.Horizontal.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])

    for prefix in ('', 'Card.', 'Header.'):
        style.layout(f'{prefix}TCheckbutton', [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
            ('Nova.Checkbutton.indicator', {'side': 'left', 'sticky': ''}),
            ('Checkbutton.label', {'side': 'left', 'sticky': 'nswe'})]})])

def _configureStyles(style, img: dict) -> None:

    '''

    Every style's colors, fonts and padding for the active mode. Runs on each switch, so it reads
    the module palette as it stands.

    '''

    containers = {'': bg, 'Card.': surface, 'Header.': surface2}

    style.configure('.', background = bg, foreground = text, bordercolor = border, troughcolor = bg,
                    selectbackground = accentMuted, selectforeground = selectedText, font = fontBody,
                    focuscolor = accent, insertcolor = accent)

    # -- Frames -- #

    style.configure('TFrame', background = bg)
    style.configure('Card.TFrame', background = bg)
    style.configure('Inset.TFrame', background = surface)
    style.configure('Surface.TFrame', background = surface)
    style.configure('Header.TFrame', background = surface2)
    style.configure('TSeparator', background = border)
    style.configure('Card.TSeparator', background = border)

    # -- Labels: a role for each kind of text, on each container -- #

    roles = {
        '':              (text, fontBody),
        'Muted.':        (textMuted, fontBodySm),
        'Heading.':      (text, fontHeading),
        'Eyebrow.':      (textDim, fontEyebrow),
        'Wordmark.':     (accent, fontWordmark),
        'Value.':        (accent, fontMono),
        'Ok.':           (green, fontBodySm),
        'Warn.':         (yellow, fontBodySm),
        'Error.':        (red, fontBodySm),
        'Activity.':     (textDim, fontMono),
        'ActivityError.': (red, fontMono),
        'FieldError.':   (red, fontBody),
    }
    for container, color in containers.items():
        for role, (foreground, font) in roles.items():
            style.configure(f'{role}{container}TLabel', background = color, foreground = foreground, font = font)

    # Icons carried by the style, so a mode change swaps them with no code of its own
    style.configure('Info.Card.TLabel', background = surface, image = img['info'], padding = (scaled(4), 0))
    style.map('Info.Card.TLabel', image = [('hover', img['info.hover'])])
    style.configure('Glyph.Card.TLabel', background = surface, image = img['glyph.closed'])
    style.map('Glyph.Card.TLabel', image = [('selected', img['glyph.open'])])

    # -- Buttons -- #

    buttonPadding = (scaled(12), scaled(5))
    smallPadding = (scaled(8), scaled(2))
    for container, color in containers.items():
        style.configure(f'{container}TButton', background = color, foreground = text, font = fontBody,
                        padding = buttonPadding, anchor = 'center')
        style.map(f'{container}TButton', foreground = [('disabled', textDim)])
        style.configure(f'Small.{container}TButton', background = color, foreground = textMuted,
                        font = fontBodySm, padding = smallPadding)
        style.map(f'Small.{container}TButton', foreground = [('disabled', textDim), ('active', text)])

    style.configure('Accent.TButton', background = bg, foreground = onAccent, font = fontStrong,
                    padding = (scaled(16), scaled(6)))
    style.map('Accent.TButton', foreground = [('disabled', textDim)])
    style.configure('Toggle.Header.TButton', background = surface2, image = img['sun' if mode == 'dark' else 'moon'],
                    padding = (scaled(6), scaled(3)))

    # -- Fields -- #

    for container, color in (('', bg), ('Card.', surface)):
        for widget in ('TEntry', 'TCombobox'):
            style.configure(f'{container}{widget}', background = color, foreground = text,
                            selectbackground = accentMuted, selectforeground = selectedText,
                            insertcolor = accent, padding = (scaled(6), scaled(3)))
            style.map(f'{container}{widget}', foreground = [('disabled', textDim)],
                      selectbackground = [('readonly', 'focus', accentMuted)],
                      selectforeground = [('readonly', 'focus', selectedText)])

    style.configure('TSpinbox', fieldbackground = surface, background = bg, foreground = text,
                    bordercolor = border, arrowcolor = textMuted)

    # -- Check indicators -- #

    for container, color in containers.items():
        style.configure(f'{container}TCheckbutton', background = color, foreground = text, font = fontBody,
                        padding = (0, scaled(2)))
        style.map(f'{container}TCheckbutton', background = [('active', color)],
                  foreground = [('disabled', textDim)])

    # -- Notebook and the View tab's navigation -- #

    style.configure('TNotebook', background = bg, borderwidth = 0, bordercolor = bg, lightcolor = bg,
                    darkcolor = bg, tabmargins = (scaled(4), scaled(4), scaled(4), 0))
    style.configure('TNotebook.Tab', background = bg, foreground = textMuted, font = fontBody,
                    padding = (scaled(16), scaled(7)), borderwidth = 0)
    style.map('TNotebook.Tab', foreground = [('selected', selectedText), ('active', text)],
              expand = [('selected', (0, 0, 0, 0))], padding = [('selected', (scaled(16), scaled(7)))])

    style.configure('Nav.Toolbutton', background = surface, foreground = textMuted, font = fontBody,
                    padding = (scaled(10), scaled(5)), anchor = 'w')
    style.map('Nav.Toolbutton', foreground = [('disabled', textDim), ('selected', selectedText), ('active', text)],
              background = [('active', surface)])

    # -- Progress bar and scrollbars -- #

    style.configure('Horizontal.TProgressbar', background = bg, troughcolor = bg, thickness = scaled(8),
                    borderwidth = 0)
    for container, color in (('', bg), ('Card.', surface)):
        for orient in ('Vertical', 'Horizontal'):
            style.configure(f'{container}{orient}.TScrollbar', background = color, troughcolor = color,
                            bordercolor = color, lightcolor = color, darkcolor = color, arrowsize = scaled(10),
                            gripcount = 0)

    # -- Tables -- #

    style.configure('Treeview', background = surface, fieldbackground = surface, foreground = text,
                    bordercolor = surface, lightcolor = surface, darkcolor = surface, font = fontBodySm,
                    rowheight = scaled(24), borderwidth = 0)
    style.configure('Treeview.Heading', background = surface2, foreground = textMuted, font = fontStrong,
                    relief = 'flat', borderwidth = 0, padding = (scaled(6), scaled(4)))
    style.map('Treeview', background = [('selected', accentMuted)], foreground = [('selected', selectedText)])
    style.map('Treeview.Heading', background = [('active', border)])

    # -- Panes -- #

    style.configure('TPanedwindow', background = bg)
    style.configure('Sash', sashthickness = scaled(6), gripcount = 0, background = bg, bordercolor = bg,
                    lightcolor = bg, darkcolor = bg)

def _applyOptionDefaults(root) -> None:

    '''Option-database colors for the classic Tk widgets ttk does not style.'''

    root.option_add('*Text.background', surface)
    root.option_add('*Text.foreground', text)
    root.option_add('*Text.insertBackground', accent)
    root.option_add('*Text.selectBackground', accentMuted)
    root.option_add('*Text.selectForeground', selectedText)
    root.option_add('*Text.font', fontMono)
    root.option_add('*Text.relief', 'flat')
    root.option_add('*Text.borderWidth', 0)

    root.option_add('*Canvas.background', bg)
    root.option_add('*Canvas.highlightThickness', 0)

    for pattern in ('*Listbox', '*TCombobox*Listbox'):
        root.option_add(f'{pattern}.background', surface)
        root.option_add(f'{pattern}.foreground', text)
        root.option_add(f'{pattern}.selectBackground', accentMuted)
        root.option_add(f'{pattern}.selectForeground', selectedText)
        root.option_add(f'{pattern}.font', fontBody)
        root.option_add(f'{pattern}.relief', 'flat')
        root.option_add(f'{pattern}.borderWidth', 0)

    root.option_add('*Menu.background', surface2)
    root.option_add('*Menu.foreground', text)
    root.option_add('*Menu.activeBackground', accent)
    root.option_add('*Menu.activeForeground', onAccent)
    root.option_add('*Menu.relief', 'flat')
    root.option_add('*Menu.font', fontBody)

def _restylePopdowns(root) -> None:

    '''

    Recolor the combobox drop-down lists already built. Each is a classic listbox Tk creates the
    first time its combobox opens, taking its colors from the option database at that moment, and
    Python's widget tree does not list it, so they are found by walking Tk's own.

    '''

    def walk(path: str) -> None:
        try:
            children = root.tk.splitlist(root.tk.call('winfo', 'children', path))
        except Exception:                                  # noqa: BLE001
            return
        for child in children:
            child = str(child)
            if child.endswith('.popdown.f.l'):
                try:
                    root.tk.call(child, 'configure', '-background', surface, '-foreground', text,
                                 '-selectbackground', accentMuted, '-selectforeground', selectedText)
                except Exception:                          # noqa: BLE001
                    pass
            walk(child)

    walk('.')

def popdownMapped(root, path: str) -> None:

    '''Round a combobox drop-down as it opens, so it matches the field it hangs from.'''

    try:
        roundHandle(int(root.tk.call('wm', 'frame', path), 16))
    except Exception:                                      # noqa: BLE001 -- cosmetic only
        pass

#----------------------------------------------------------------------#
# -- Matplotlib -- #
#----------------------------------------------------------------------#

def matplotlibRcParams() -> dict:

    '''

    An rcParams overlay that renders embedded Matplotlib figures in the active mode. Applied when
    the plotting module loads, on every mode change, and by the runner before NOVA draws.

    '''

    # Imported here rather than at module load so the GUI can start without the scientific stack;
    # cycler ships with Matplotlib.
    from cycler import cycler

    return {
        'figure.facecolor':  surface,
        'figure.edgecolor':  surface,
        'savefig.facecolor': surface,
        'axes.facecolor':    bg,
        'axes.edgecolor':    border,
        'axes.labelcolor':   text,
        'axes.titlecolor':   text,
        'axes.grid':         True,
        'grid.color':        border,
        'grid.alpha':        0.6,
        'grid.linewidth':    0.6,
        'text.color':        text,
        'xtick.color':       textMuted,
        'ytick.color':       textMuted,
        'legend.facecolor':  surface2,
        'legend.edgecolor':  border,
        # Layout is driven per figure by a constrained engine; autolayout would run tight_layout on
        # top of it and warn.
        'figure.autolayout': False,
        'axes.prop_cycle':   cycler(color = [green, accent, red, yellow, blue, orange, purple, cyan]),
        'font.size':         9,
    }

def styleFigure(fig) -> None:

    '''

    Recolor an existing Matplotlib figure and all of its axes to the active mode.

    '''

    fig.patch.set_facecolor(surface)
    for ax in fig.get_axes():
        styleAxes(ax)

def styleAxes(ax) -> None:

    '''

    Recolor a single Matplotlib Axes to the active mode.

    '''

    ax.set_facecolor(bg)
    for spine in ax.spines.values():
        spine.set_color(border)
    ax.tick_params(colors = textMuted)
    ax.xaxis.label.set_color(text)
    ax.yaxis.label.set_color(text)
    ax.title.set_color(text)
    ax.grid(True, color = border, alpha = 0.6, linewidth = 0.6)
