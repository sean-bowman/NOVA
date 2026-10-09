# -- NOVA: Figure Palette -- #

'''

The colors every NOVA figure is drawn in: the Engineering Flat Metal palette, in a dark and a
light mode.

The palette names seventeen colors per mode. Four are backgrounds (`bg`, `surface`, `surface2`,
`border`), three are text weights, three carry the accent (matte aged copper), and seven are status
colors whose meaning is fixed in both modes: `green` is pass and complete only, `red` error, `yellow`
warning, `blue` information, `orange` attention, `purple` analysis outputs, `cyan` code and paths.
Plots draw categories from `categories`, which starts on green by the palette's own rule, and
draw the nozzle wall in the accent.

Three continuous colormaps go with each mode, one per field the solver produces:

    mach          a steel ramp, gunmetal to brushed steel: one cool hue whose lightness rises
                  monotonically, so the copper wall and a brass plume boundary stand apart from
                  it by hue as well as by value
    pressure      blued steel through neutral steel to rust, diverging
    temperature   gunmetal through bronze to brass

Each ramp's light end is held clear of its own mode's background, so the fastest flow never
vanishes into the page.

Figures are drawn in one mode at a time. It is dark unless `setFigureMode('light')` is called or
the environment variable `NOVA_FIGURE_MODE` is `light`; the GUI sets it to match its own theme
before every run. Matplotlib and plotly are imported only by the helpers that need them.

Author: Sean Bowman

'''

import os

modes = ('dark', 'light')

palettes = {
    'dark': {
        'bg':          '#1C1E22',   # gunmetal
        'surface':     '#24272C',
        'surface2':    '#2D3136',
        'border':      '#3D4148',
        'text':        '#DCE1E6',   # brushed steel
        'textMuted':   '#9098A0',
        'textDim':     '#5C636B',
        'accent':      '#B5722E',   # matte aged copper
        'accentDim':   '#8F5A22',
        'accentMuted': '#3A2E1E',
        'green':       '#6E9B85',   # verdigris
        'red':         '#B5493D',   # rust oxide
        'yellow':      '#C2A05A',   # brass
        'blue':        '#6E88A3',   # blued steel
        'orange':      '#C08040',   # bronze
        'purple':      '#8C7A96',   # pewter
        'cyan':        '#6E9B95',   # weathered teal-steel
    },
    'light': {
        'bg':          '#E8E9EA',   # brushed aluminum
        'surface':     '#F5F5F6',
        'surface2':    '#DADDDF',
        'border':      '#C2C6C9',
        'text':        '#24272B',
        'textMuted':   '#5B6167',
        'textDim':     '#868C91',
        'accent':      '#8A4E1F',   # darkened matte copper
        'accentDim':   '#6E3E18',
        'accentMuted': '#F0DFC9',
        'green':       '#4F7A65',
        'red':         '#8E362C',
        'yellow':      '#8A6B25',
        'blue':        '#4C6478',
        'orange':      '#8F5426',
        'purple':      '#6B5A72',
        'cyan':        '#4C726C',
    },
}

# Color stops for each field's colormap, low value first
colormapStops = {
    'dark': {
        'mach':        ('#2A2F37', '#3A4552', '#536780', '#7C91A8', '#AAB8C6', '#DCE1E6'),
        'pressure':    ('#3C5266', '#6E88A3', '#9098A0', '#C08040', '#B5493D'),
        'temperature': ('#2E2B28', '#5A3F2A', '#8F5A22', '#C08040', '#C2A05A', '#E2CC96'),
    },
    'light': {
        'mach':        ('#24272B', '#33404D', '#4C6478', '#6E88A3', '#93A5B8', '#B9C5D1'),
        'pressure':    ('#34485A', '#4C6478', '#868C91', '#8F5426', '#8E362C'),
        'temperature': ('#3A2A1E', '#6E3E18', '#8F5426', '#B07A3A', '#C9A066', '#DCC79C'),
    },
}

_figureMode = os.environ.get('NOVA_FIGURE_MODE', 'dark').strip().lower()
if _figureMode not in modes:
    _figureMode = 'dark'

def setFigureMode(mode: str) -> None:

    '''

    Choose the mode every figure drawn after this call uses.

    Parameters:
    -----------
    mode : str
        'dark' or 'light'

    '''

    global _figureMode

    if mode not in modes:
        raise ValueError(f"Figure mode must be one of {', '.join(modes)}, not {mode!r}.")
    _figureMode = mode

def figureMode() -> str:

    '''The mode figures are drawn in.'''

    return _figureMode

def colors(mode: str = None) -> dict:

    '''

    The seventeen named colors of a mode, the active figure mode by default.

    '''

    return palettes[mode or _figureMode]

def categories(mode: str = None) -> list:

    '''The categorical color sequence plots draw series from, in the palette's order.'''

    named = colors(mode)

    return [named[key] for key in ('green', 'accent', 'red', 'yellow', 'blue', 'orange', 'purple', 'cyan')]

def colormap(name: str, mode: str = None):

    '''

    A field's colormap as a Matplotlib colormap.

    Parameters:
    -----------
    name : str
        'mach', 'pressure' or 'temperature'
    mode : str
        'dark' or 'light'; the active figure mode by default

    Returns:
    --------
    matplotlib.colors.LinearSegmentedColormap

    '''

    from matplotlib.colors import LinearSegmentedColormap

    mode = mode or _figureMode

    return LinearSegmentedColormap.from_list(f'nova{name.capitalize()}{mode.capitalize()}',
                                             list(colormapStops[mode][name]))

def plotlyColorscale(name: str, mode: str = None) -> list:

    '''

    A field's colormap as a plotly colorscale, `[[position, color], ...]`.

    A name that is not one of the palette's fields is handed back unchanged, so a plotly
    colorscale name still works where one is passed.

    '''

    mode = mode or _figureMode
    if name not in colormapStops[mode]:
        return name
    stops = colormapStops[mode][name]

    return [[index / (len(stops) - 1), color] for index, color in enumerate(stops)]

def matplotlibStyle(mode: str = None) -> dict:

    '''

    Matplotlib rcParams for a mode: page and panel backgrounds, text, edges, grid and the
    categorical cycle. Flat, so no grid shading beyond a hairline.

    '''

    from cycler import cycler

    named = colors(mode)

    return {
        'figure.facecolor':  named['bg'],
        'savefig.facecolor': named['bg'],
        'axes.facecolor':    named['surface'],
        'axes.edgecolor':    named['border'],
        'axes.labelcolor':   named['text'],
        'axes.titlecolor':   named['text'],
        'text.color':        named['text'],
        'xtick.color':       named['textMuted'],
        'ytick.color':       named['textMuted'],
        'grid.color':        named['border'],
        'legend.facecolor':  named['surface2'],
        'legend.edgecolor':  named['border'],
        'axes.prop_cycle':   cycler(color = categories(mode)),
    }

def plotlyLayout(mode: str = None) -> dict:

    '''

    Keyword arguments for a plotly `update_layout` call in a mode: backgrounds, font, grid and
    the categorical colorway.

    '''

    named = colors(mode)
    axis = {'gridcolor': named['border'], 'linecolor': named['border'], 'zerolinecolor': named['border']}

    return {
        'paper_bgcolor': named['bg'],
        'plot_bgcolor':  named['surface'],
        'font':          {'color': named['text']},
        'colorway':      categories(mode),
        'xaxis':         axis,
        'yaxis':         dict(axis),
    }
