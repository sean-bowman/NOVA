# -- The feature showcase's palette -- #

'''

The Engineering Flat Metal palette, dark mode, under the names the showcase and report builders
draw with, so every figure in the README and the reports is one palette with NOVA's own figures
and the GUI.

The colors come from `NOVA.palette`; nothing here defines one. The names are the ones the builders
draw with: `background` and `panel` for the page and the plot, `copper` for the nozzle wall, `ink`
and `muted` for text, `warn` for a refusal or an untrustworthy result. The field colormaps are the
palette's: the steel ramp for Mach number, gunmetal through bronze to brass for temperature and
other warm magnitudes.

`restyleHtml` carries the same palette into an HTML report written against the report style's CSS
variables; the palette uses the same variable names, so only the values change.

Author: Sean Bowman

'''

import re

import matplotlib.pyplot as plt

from NOVA import palette

_colors = palette.colors('dark')

background = _colors['bg']
panel      = _colors['surface']
surface2   = _colors['surface2']
border     = _colors['border']
ink        = _colors['text']
muted      = _colors['textMuted']
dim        = _colors['textDim']
copper     = _colors['accent']
copperDim  = _colors['accentDim']
green      = _colors['green']
warn       = _colors['red']
red        = _colors['red']
yellow     = _colors['yellow']
blue       = _colors['blue']
orange     = _colors['orange']
purple     = _colors['purple']
cyan       = _colors['cyan']
gridColor  = _colors['border']

machMap        = palette.colormap('mach', 'dark')
pressureMap    = palette.colormap('pressure', 'dark')
temperatureMap = palette.colormap('temperature', 'dark')

def mix(color: str, other: str, fraction: float) -> str:

    '''

    `color` moved `fraction` of the way toward `other`, as a hex string. For a series that needs a
    lighter or darker step of a palette hue: the palette's flat metals sit close together, and a
    figure with ten series runs out of hues before it runs out of series.

    '''

    first = [int(color[index:index + 2], 16) for index in (1, 3, 5)]
    second = [int(other[index:index + 2], 16) for index in (1, 3, 5)]
    blended = [round(a + fraction * (b - a)) for a, b in zip(first, second)]
    return '#' + ''.join(f'{channel:02X}' for channel in blended)

def applyStyle(**extra) -> None:

    '''

    Matplotlib's rcParams in the palette's dark mode, plus anything a builder sets on top.

    '''

    plt.rcParams.update(palette.matplotlibStyle('dark'))
    plt.rcParams.update(extra)

# The report style's CSS variables, by the palette name each takes. A code block sits on the page
# color so it reads as recessed into the card around it.
cssVariables = {
    '--bg': 'bg', '--surface': 'surface', '--surface-2': 'surface2', '--border': 'border',
    '--text': 'text', '--text-muted': 'textMuted', '--text-dim': 'textDim',
    '--accent': 'accent', '--accent-dim': 'accentDim', '--accent-muted': 'accentMuted',
    '--green': 'green', '--red': 'red', '--yellow': 'yellow', '--blue': 'blue',
    '--orange': 'orange', '--purple': 'purple', '--cyan': 'cyan',
    '--code-bg': 'bg', '--code-text': 'text',
}

def restyleHtml(html: str) -> str:

    '''

    An HTML report in the palette's dark mode. The report's `:root` block says which color each
    report-style variable held; every occurrence of that color in the page changes to the palette's
    value for the variable, so the stylesheet, the mermaid theme and the code highlighting, which
    repeat the colors as literals, change with it. Colors the `:root` block does not name are left
    alone.

    '''

    root = re.search(r':root\s*\{(.*?)\}', html, flags = re.S)
    if root is None:
        return html

    replacements = {}
    for variable, value in re.findall(r'(--[\w-]+)\s*:\s*(#[0-9A-Fa-f]{6})', root.group(1)):
        if variable in cssVariables:
            replacements[value.lower()] = _colors[cssVariables[variable]]

    # One pass, so a replaced color is never matched again as another variable's old value
    return re.sub(r'#[0-9A-Fa-f]{6}', lambda match: replacements.get(match.group(0).lower(), match.group(0)), html)
