
# -- NOVA GUI Palette State -- #

'''

The Engineering Flat Metal palette in its dark and light modes, the active mode, and the
Matplotlib styling that follows it.

The active mode's colors are bound as module attributes (`themeColors.surface`,
`themeColors.accent`, ...), which the Matplotlib drawers read at draw time. `bindPalette` switches
the mode. The web front end's palette stylesheet is written from `palettes`
(novaGui.paletteCss), and src/NOVA/palette.py holds the same values for NOVA's own figures;
tests/testGuiTheme.py keeps the two equal. The values are kept here rather than read from
NOVA.palette because importing NOVA loads the whole scientific stack, which the GUI opens without.

Author: Sean Bowman
Date:   08/28/2026

'''

import sys

# The Engineering Flat Metal palette (NOVA.palette), plus two roles a GUI needs: the text drawn on
# an accent fill, and the text of a selected tab or view, which accent on accent-muted is too
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

# The names every palette defines, bound as module attributes for the active mode by bindPalette
mode = 'dark'
bg = surface = surface2 = border = text = textMuted = textDim = ''
accent = accentDim = accentMuted = ''
green = red = yellow = blue = orange = purple = cyan = onAccent = selectedText = ''

def bindPalette(newMode: str) -> None:

    '''

    Make `newMode` the active mode and bind its colors as module attributes.

    Raises:
    -------
    ValueError : If `newMode` is not a palette's name.

    '''

    global mode

    if newMode not in palettes:
        raise ValueError(f"Theme mode must be one of {', '.join(palettes)}, not {newMode!r}.")
    mode = newMode
    globals().update(palettes[newMode])

bindPalette('dark')

def matplotlibRcParams() -> dict:

    '''

    An rcParams overlay that renders Matplotlib figures in the active mode. Applied when the
    drawers load, on every mode change, and by the runner before NOVA draws.

    '''

    # Imported here rather than at module load so a GUI can start without the scientific stack;
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

def applyMatplotlib() -> None:

    '''Carry the active mode into Matplotlib's rcParams, if Matplotlib has been imported.'''

    module = sys.modules.get('matplotlib')
    if module is not None:
        module.rcParams.update(matplotlibRcParams())

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
