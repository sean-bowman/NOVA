
# -- NOVA GUI Dark Theme -- #

'''

Copper-amber dark theme for the NOVA GUI, matching the personal style system:
a soft deep blue-grey base (#1a1e2a) with a single warm metallic accent
(#E0975A) carrying links, active tabs, focus states and calls to action. Green
is reserved for status (pass / healthy) and never used as a brand color.

applyTheme() restyles every ttk widget class the GUI uses and registers option
defaults for the classic Tk widgets (Text, Canvas, Menu, Listbox). styleFigure()
and styleAxes() apply the same palette to embedded Matplotlib figures so the
plots read as part of the same surface rather than bright white cut-outs.

Author: Sean Bowman
Date:   08/28/2026

'''

import sys

from tkinter import ttk

# -- Display scaling -- #

# Set by applyTheme() from the real screen DPI. Other modules read it to size
# things Tk does not scale for us: Matplotlib figure DPI, wrap lengths, the
# default window geometry.
uiScale = 1.0

# -- Palette -- #

# Backgrounds
bg        = '#1a1e2a'   # window background, plot interiors
surface   = '#22273a'   # panels, cards, figure face
surface2  = '#292f42'   # elevated surface: tab strip, table headers, hover
border    = '#3a4055'   # every border and divider

# Text
text      = '#d8e0ec'   # primary
textMuted = '#8a95a8'   # secondary / descriptive
textDim   = '#5c6575'   # tertiary / metadata

# Signature accent
accent    = '#E0975A'   # brand, links, active tab, CTA, focus, highlights
accentDim = '#C97E45'   # hover / pressed accent
accentBg  = '#2A2018'   # subtle accent-tinted panel fill

# Semantic (pastel on dark). Each keeps a fixed meaning.
green     = '#86C06C'   # pass / complete / healthy / in-band  -- status only
red       = '#e08080'   # error / failure
yellow    = '#d4b86a'   # warning / at-risk
blue      = '#7baee8'   # info / in-progress
purple    = '#aa84d8'   # analysis outputs
cyan      = '#6ad4c8'   # code, file paths

# Typography. These are the 96 dpi base sizes; applyTheme() rebinds each name to
# the DPI-scaled tuple before any widget is styled.
fontBody     = ('Segoe UI', 10)
fontBodySm   = ('Segoe UI', 9)
fontHeading  = ('Segoe UI Semibold', 11)
fontEyebrow  = ('Segoe UI', 8)
fontMono     = ('Consolas', 9)
fontWordmark = ('Share Tech Mono', 15, 'bold')   # falls back to Consolas if absent

_baseFonts = {
    'fontBody':     fontBody,
    'fontBodySm':   fontBodySm,
    'fontHeading':  fontHeading,
    'fontEyebrow':  fontEyebrow,
    'fontMono':     fontMono,
    'fontWordmark': fontWordmark,
}

def enableDpiAwareness() -> None:

    '''

    Opt the process into per-monitor DPI awareness. Must be called BEFORE the Tk root is
    constructed, otherwise Windows composites the window from a 96 dpi bitmap and every
    widget and plot is blurry on a high-DPI display.

    Awareness alone does not resize anything: Tk keeps reporting logical pixels, so the
    window comes out physically small. applyTheme() does the compensating scaling.

    '''

    if sys.platform != 'win32':
        return

    import ctypes

    # Per-monitor v2 where available (correct behavior when dragged between monitors),
    # falling back through per-monitor v1 to the system-wide call on older Windows.
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

    Screen DPI as a multiple of the 96 dpi the base sizes assume. Clamped so a bad
    reading cannot produce an unusable window.

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

def applyTheme(root) -> None:

    '''

    Apply the dark theme to a Tk root and every ttk widget class the GUI uses.

    Parameters:
    -----------
    root : tk.Tk
        The application root window.

    '''

    global uiScale, fontBody, fontBodySm, fontHeading, fontEyebrow, fontMono, fontWordmark

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

    fontBody, fontBodySm = globals()['fontBody'], globals()['fontBodySm']
    fontHeading, fontEyebrow = globals()['fontHeading'], globals()['fontEyebrow']
    fontMono, fontWordmark = globals()['fontMono'], globals()['fontWordmark']

    root.configure(bg = bg)

    style = ttk.Style(root)

    # 'clam' is the only bundled ttk theme that honours background/foreground
    # overrides on every element, so it is the base for all restyling below.
    style.theme_use('clam')

    # -- Containers -- #

    style.configure('TFrame', background = bg)
    style.configure('Surface.TFrame', background = surface)
    style.configure('Elevated.TFrame', background = surface2)

    style.configure('TLabel', background = bg, foreground = text, font = fontBody)
    style.configure('Surface.TLabel', background = surface, foreground = text, font = fontBody)
    style.configure('Muted.TLabel', background = bg, foreground = textMuted, font = fontBodySm)
    style.configure('SurfaceMuted.TLabel', background = surface, foreground = textMuted, font = fontBodySm)
    style.configure('Heading.TLabel', background = bg, foreground = text, font = fontHeading)
    style.configure('Eyebrow.TLabel', background = bg, foreground = textDim, font = fontEyebrow)
    style.configure('Wordmark.TLabel', background = bg, foreground = accent, font = fontWordmark)
    style.configure('Value.TLabel', background = surface, foreground = accent, font = fontMono)
    style.configure('Ok.TLabel', background = bg, foreground = green, font = fontBodySm)
    style.configure('Warn.TLabel', background = bg, foreground = yellow, font = fontBodySm)
    style.configure('Error.TLabel', background = bg, foreground = red, font = fontBodySm)

    # -- LabelFrame (used by the collapsible sections' fallback) -- #

    style.configure('TLabelframe', background = bg, bordercolor = border, relief = 'solid')
    style.configure('TLabelframe.Label', background = bg, foreground = accent, font = fontHeading)

    # -- Notebook -- #

    style.configure('TNotebook', background = bg, bordercolor = border, tabmargins = (2, 4, 2, 0))
    style.configure(
        'TNotebook.Tab',
        background = surface,
        foreground = textMuted,
        bordercolor = border,
        padding = (16, 8),
        font = fontBody,
    )
    style.map(
        'TNotebook.Tab',
        background = [('selected', bg), ('active', surface2)],
        foreground = [('selected', accent), ('active', text)],
    )

    # -- Buttons -- #

    style.configure(
        'TButton',
        background = surface2,
        foreground = text,
        bordercolor = border,
        focuscolor = accent,
        font = fontBody,
        padding = (12, 6),
        relief = 'flat',
    )
    style.map(
        'TButton',
        background = [('active', border), ('pressed', border), ('disabled', surface)],
        foreground = [('disabled', textDim)],
    )

    # Primary call to action: filled copper with dark text, per the palette rule
    # that dark text reads cleanly on a copper fill.
    style.configure(
        'Accent.TButton',
        background = accent,
        foreground = '#111111',
        bordercolor = accentDim,
        font = ('Segoe UI Semibold', 10),
        padding = (16, 7),
        relief = 'flat',
    )
    style.map(
        'Accent.TButton',
        background = [('active', accentDim), ('pressed', accentDim), ('disabled', surface2)],
        foreground = [('disabled', textDim)],
    )

    # -- Entry / Combobox / Spinbox -- #

    for element in ('TEntry', 'TCombobox', 'TSpinbox'):
        style.configure(
            element,
            fieldbackground = surface2,
            background = surface2,
            foreground = text,
            bordercolor = border,
            insertcolor = accent,
            arrowcolor = textMuted,
            selectbackground = accentDim,
            selectforeground = '#111111',
            padding = 4,
        )
        style.map(
            element,
            fieldbackground = [('readonly', surface2), ('disabled', surface)],
            foreground = [('disabled', textDim)],
            bordercolor = [('focus', accent)],
        )

    # -- Checkbutton / Radiobutton -- #

    for element in ('TCheckbutton', 'TRadiobutton'):
        style.configure(
            element,
            background = bg,
            foreground = text,
            focuscolor = accent,
            indicatorbackground = surface2,
            indicatorforeground = accent,
            font = fontBody,
        )
        style.map(
            element,
            background = [('active', bg)],
            indicatorbackground = [('selected', accent), ('pressed', accentDim)],
        )
        style.configure(
            f'Surface.{element}',
            background = surface,
            foreground = text,
            focuscolor = accent,
            indicatorbackground = bg,
            indicatorforeground = accent,
            font = fontBody,
        )
        style.map(
            f'Surface.{element}',
            background = [('active', surface)],
            indicatorbackground = [('selected', accent), ('pressed', accentDim)],
        )

    # -- Progressbar -- #

    style.configure(
        'TProgressbar',
        background = accent,
        troughcolor = surface2,
        bordercolor = border,
        lightcolor = accent,
        darkcolor = accent,
    )

    # -- Scrollbars -- #

    for element in ('Vertical.TScrollbar', 'Horizontal.TScrollbar'):
        style.configure(
            element,
            background = surface2,
            troughcolor = bg,
            bordercolor = bg,
            arrowcolor = textMuted,
        )
        style.map(element, background = [('active', border)])

    # -- Treeview (analysis + export file tables) -- #

    style.configure(
        'Treeview',
        background = surface,
        fieldbackground = surface,
        foreground = text,
        bordercolor = border,
        font = fontBodySm,
        rowheight = 24,
    )
    style.configure(
        'Treeview.Heading',
        background = surface2,
        foreground = textMuted,
        font = ('Segoe UI Semibold', 9),
        relief = 'flat',
    )
    style.map(
        'Treeview',
        background = [('selected', accentBg)],
        foreground = [('selected', accent)],
    )
    style.map('Treeview.Heading', background = [('active', border)])

    # -- PanedWindow -- #

    style.configure('TPanedwindow', background = bg)
    style.configure('Sash', sashthickness = 6, gripcount = 0, background = border, bordercolor = border)

    # -- Classic Tk widget defaults -- #

    root.option_add('*Text.background', surface)
    root.option_add('*Text.foreground', text)
    root.option_add('*Text.insertBackground', accent)
    root.option_add('*Text.selectBackground', accentDim)
    root.option_add('*Text.selectForeground', '#111111')
    root.option_add('*Text.font', fontMono)
    root.option_add('*Text.relief', 'flat')
    root.option_add('*Text.borderWidth', 0)

    root.option_add('*Canvas.background', bg)
    root.option_add('*Canvas.highlightThickness', 0)

    root.option_add('*Listbox.background', surface)
    root.option_add('*Listbox.foreground', text)
    root.option_add('*Listbox.selectBackground', accentBg)
    root.option_add('*Listbox.selectForeground', accent)
    root.option_add('*Listbox.font', fontMono)
    root.option_add('*Listbox.relief', 'flat')
    root.option_add('*Listbox.borderWidth', 0)

    root.option_add('*Menu.background', surface2)
    root.option_add('*Menu.foreground', text)
    root.option_add('*Menu.activeBackground', accent)
    root.option_add('*Menu.activeForeground', '#111111')
    root.option_add('*Menu.relief', 'flat')
    root.option_add('*Menu.font', fontBody)

    # Tooltip toplevels styled in widgets.Tooltip; nothing to register here.

def matplotlibRcParams() -> dict:

    '''

    Return an rcParams overlay that renders embedded Matplotlib figures in the
    GUI palette. Applied by the runner before NOVA generates any figure, and by
    the geometry tabs for their own inline plots.

    '''

    # Imported here rather than at module load so the GUI can start without the
    # scientific stack present; cycler ships with Matplotlib.
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
        'grid.alpha':        0.5,
        'grid.linewidth':    0.6,
        'text.color':        text,
        'xtick.color':       textMuted,
        'ytick.color':       textMuted,
        # Layout is driven per-figure by a constrained engine; autolayout would run
        # tight_layout on top of it and warn.
        'figure.autolayout': False,
        'axes.prop_cycle':   cycler(color = [accent, blue, green, purple, yellow, cyan, red]),
        'font.size':         9,
    }

def styleFigure(fig) -> None:

    '''

    Recolor an existing Matplotlib figure and all of its axes to the GUI
    palette. Used when displaying figures the GUI did not create with the rc
    overlay in force.

    '''

    fig.patch.set_facecolor(surface)
    for ax in fig.get_axes():
        styleAxes(ax)

def styleAxes(ax) -> None:

    '''

    Recolor a single Matplotlib Axes to the GUI palette.

    '''

    ax.set_facecolor(bg)
    for spine in ax.spines.values():
        spine.set_color(border)
    ax.tick_params(colors = textMuted)
    ax.xaxis.label.set_color(text)
    ax.yaxis.label.set_color(text)
    ax.title.set_color(text)
    ax.grid(True, color = border, alpha = 0.5, linewidth = 0.6)
