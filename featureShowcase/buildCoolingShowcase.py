# -- The cooling architectures, one engine each -- #

'''

The shipped engine and each example in src/NOVA/assets/examples, run through the cooling solve,
with a figure per engine and a matrix of which cooling features each one uses.

Each engine's figure carries four panels: the coolant circuit drawn on the half section, each
pass's coolant and hot wall (or the jacket's, for a single pass), the hot wall along the whole
nozzle from the injector face to the exit against each section's limit, and the extension's drive
and shell (or the chamber film, where there is no extension). The first two and the last are the
GUI's own views, drawn headless in its dark theme, so the figures are what the View tab shows for
the same run. Engines with a channel split or a multi-pass jacket get a three-dimensional render
of that feature beside it.

Every engine is run with plots, exports and the plume off, because the figures read only the
solved arrays the run keeps. The solved nozzles are cached beside this script under coolingRuns/,
which is gitignored; `--draw` redraws from that cache.

Run it from the NOVA root:

    python featureShowcase/buildCoolingShowcase.py                    # solves every engine, then draws
    python featureShowcase/buildCoolingShowcase.py --engine keroloxF1 # solves one engine, then draws it
    python featureShowcase/buildCoolingShowcase.py --draw             # redraws from the cache

Engines are solved one after another in one process; separate processes with `--engine` can run
side by side, and their CEA calls queue on the machine-wide lock.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

Nothing here is validated by being run. Each solver carries its own validation statement, and the
cooling circuits in particular are verified against identities rather than validated against
hardware (coolantCircuit.py, extensionCircuit.py, extensionFilm.py, turbineExhaust.py). The
example engines borrow the architecture of the engines they are named after, not their published
dimensions or flows; each example's `_comment` says where it departs.

Author: Sean Bowman

'''

import json
import os
import pickle
import sys
import time

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
for path in (root, os.path.join(root, 'src')):
    if path not in sys.path:
        sys.path.insert(0, path)

from NOVA import Nozzle                                     # noqa: E402
from novaGui import theme, thermalPlots                     # noqa: E402

assets = os.path.join(root, 'src', 'NOVA', 'assets')
runFolder = os.path.join(here, 'coolingRuns')

# Engine key, short label, configuration file
ENGINES = (
    ('NOVANozzle', 'NOVA (B)', os.path.join(assets, 'NOVANozzle.json')),
    ('novaSinglePass', 'NOVA single pass (A)', os.path.join(assets, 'examples', 'novaSinglePass.json')),
    ('methaloxBooster', 'Methalox booster', os.path.join(assets, 'examples', 'methaloxBooster.json')),
    ('keroloxF1', 'F-1-like', os.path.join(assets, 'examples', 'keroloxF1.json')),
    ('hydroloxVulcain', 'Vulcain 2-like', os.path.join(assets, 'examples', 'hydroloxVulcain.json')),
    ('ssmeNozzle', 'SSME-like', os.path.join(assets, 'examples', 'ssmeNozzle.json')),
)

PANEL = (7.5, 4.6)         # [in], each panel's figure size
DPI = 110

#--------------------------------------------------------------------------------------------------------------------------#
# -- Solving -- #
#--------------------------------------------------------------------------------------------------------------------------#

def solve(name: str, configPath: str):

    '''Run one engine with plots, exports and the plume off, and cache the solved nozzle.'''

    with open(configPath, encoding = 'utf-8') as handle:
        config = json.load(handle)
    config.update({'plotsEnabled': False, 'export': False, 'plumeAmbientPressure': None,
                   'plumeFieldReach': None, 'filename': name})
    os.makedirs(runFolder, exist_ok = True)
    path = os.path.join(runFolder, f'{name}.json')
    with open(path, 'w', encoding = 'utf-8', newline = '\n') as handle:
        json.dump(config, handle, indent = 2)

    original = Nozzle._getOutputRoot
    Nozzle._getOutputRoot = lambda self: runFolder
    start = time.time()
    try:
        nozzle = Nozzle()
        nozzle.generateNozzle(configPath = path)
    finally:
        Nozzle._getOutputRoot = original
    print(f'== {name} solved in {time.time() - start:.0f} s')

    with open(os.path.join(runFolder, f'{name}.pkl'), 'wb') as handle:
        pickle.dump(nozzle, handle)
    return nozzle

def cached(name: str):

    path = os.path.join(runFolder, f'{name}.pkl')
    if not os.path.isfile(path):
        return None
    with open(path, 'rb') as handle:
        return pickle.load(handle)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Panels -- #
#--------------------------------------------------------------------------------------------------------------------------#

class HeadlessPane:

    '''The part of the GUI's plot pane the cooling views draw on, without a window.'''

    def __init__(self):

        self.figure = Figure(figsize = PANEL, dpi = DPI)
        self.figure.patch.set_facecolor(theme.surface)
        self.axes = None
        self._projection = None

    def message(self, text: str) -> None:

        self.figure.clear()
        axis = self.figure.add_subplot(111)
        theme.styleAxes(axis)
        axis.set_axis_off()
        axis.text(0.5, 0.5, text, ha = 'center', va = 'center', color = theme.textMuted, transform = axis.transAxes)

    def redraw(self) -> None:

        pass

    def image(self) -> np.ndarray:

        from matplotlib.backends.backend_agg import FigureCanvasAgg
        canvas = FigureCanvasAgg(self.figure)
        canvas.draw()
        return np.asarray(canvas.buffer_rgba())[:, :, :3].copy()

def guiPanel(view, nozzle) -> np.ndarray:

    pane = HeadlessPane()
    view(pane, nozzle)
    return pane.image()

def _metal(results: dict) -> np.ndarray:

    return np.asarray(results.get('metalWallTemperature', results['wallTemperature']), dtype = float)

def wallAlongTheNozzle(nozzle) -> np.ndarray:

    '''The hot wall from the injector face to the exit, each section against its own limit.'''

    pane = HeadlessPane()
    figure = pane.figure
    figure.set_layout_engine('constrained')
    wallAxes, coolantAxes = figure.subplots(2, 1, sharex = True)
    for axis in (wallAxes, coolantAxes):
        theme.styleAxes(axis)

    results = nozzle.channelThermalResults
    x = np.asarray(results['xHotWall3D'])
    circuit = getattr(nozzle, 'coolantCircuitSolution', None)
    if circuit is None:
        wallAxes.plot(x, _metal(results), color = theme.accent, linewidth = 1.8, label = 'Chamber jacket')
        coolantAxes.plot(x, results['temperature'], color = theme.accent, linewidth = 1.8, label = 'Chamber jacket')
    else:
        for passSolution, color in ((circuit.down, theme.blue), (circuit.up, theme.accent)):
            xPass = np.asarray(passSolution.results['xHotWall3D'])
            wallAxes.plot(xPass, _metal(passSolution.results), color = color, linewidth = 1.8,
                          label = f'{passSolution.name.capitalize()} family')
            coolantAxes.plot(xPass, passSolution.results['temperature'], color = color, linewidth = 1.8,
                             label = f'{passSolution.name.capitalize()} pass')
    wallAxes.axhline(float(nozzle.maxWallTemperature), color = theme.red, linewidth = 1.0, linestyle = '--',
                     label = f'Jacket limit {float(nozzle.maxWallTemperature):.0f} K')
    ceiling = getattr(nozzle, 'maxColdWallTemperature', None)
    if ceiling is not None and np.isfinite(float(ceiling)):
        wallAxes.plot(x, results['coldWallTemperature'], color = theme.accent, linewidth = 1.0, linestyle = ':',
                      label = 'Coolant-side wall')
        wallAxes.axhline(float(ceiling), color = theme.textMuted, linewidth = 1.0, linestyle = '--',
                         label = f'Coking ceiling {float(ceiling):.0f} K')

    extension = getattr(nozzle, 'extensionCircuitSolution', None)
    xExtension = getattr(nozzle, 'xExtension', None)
    if extension is not None:
        xCircuit = np.asarray(xExtension)[extension.stations]
        wallAxes.plot(xCircuit, extension.metalWallTemperature, color = theme.purple, linewidth = 1.8,
                      label = 'Extension circuit')
        if extension.circuit is None:
            coolantAxes.plot(xCircuit, extension.sizing.channelThermalResults['temperature'], color = theme.purple,
                             linewidth = 1.8, label = 'Extension circuit')
        else:
            for passSolution, style in ((extension.circuit.down, '--'), (extension.circuit.up, '-')):
                coolantAxes.plot(passSolution.results['xHotWall3D'], passSolution.results['temperature'],
                                 color = theme.purple, linewidth = 1.8, linestyle = style,
                                 label = f'Extension {passSolution.name} pass')
    shell = getattr(nozzle, 'extensionWallTemperature', None)
    if shell is not None and xExtension is not None:
        start = len(xExtension) - len(shell)
        wallAxes.plot(np.asarray(xExtension)[start:], shell, color = theme.cyan, linewidth = 1.8,
                      label = f'Radiation-cooled shell, peak {float(np.max(shell)):.0f} K')
        limit = getattr(nozzle, 'extensionTemperatureLimit', None)
        if limit is not None:
            wallAxes.axhline(float(limit), color = theme.cyan, linewidth = 1.0, linestyle = '--',
                             label = f'Shell limit {float(limit):.0f} K')

    wallAxes.set_ylabel('Hot wall [K]')
    coolantAxes.set_ylabel('Coolant [K]')
    coolantAxes.set_xlabel('Nozzle axis [m]')
    wallAxes.set_title('Hot wall along the whole nozzle; metal behind any coating', color = theme.text)
    for axis in (wallAxes, coolantAxes):
        axis.axvline(0.0, color = theme.textDim, linewidth = 0.8, linestyle = ':')
        axis.legend(facecolor = theme.surface2, edgecolor = theme.border, labelcolor = theme.text, fontsize = 7,
                    framealpha = 0.95)
    return pane.image()

def lastPanel(nozzle) -> np.ndarray:

    if thermalPlots.extensionSolved(nozzle):
        return guiPanel(thermalPlots.drawExtension, nozzle)
    if thermalPlots.filmSolved(nozzle):
        return guiPanel(thermalPlots.drawFilm, nozzle)
    return guiPanel(thermalPlots.drawWallMap, nozzle)

def titleStrip(text: str, width: int) -> np.ndarray:

    figure = Figure(figsize = (width / DPI, 0.5), dpi = DPI)
    figure.patch.set_facecolor(theme.surface)
    figure.text(0.01, 0.5, text, color = theme.text, fontsize = 12, va = 'center', ha = 'left')
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    return np.asarray(canvas.buffer_rgba())[:, :, :3].copy()

def engineFigure(name: str, title: str, nozzle) -> str:

    multiPass = getattr(nozzle, 'coolantCircuitSolution', None) is not None
    hasExtensionCircuit = getattr(nozzle, 'extensionCircuitSolution', None) is not None
    second = (guiPanel(thermalPlots.drawPasses, nozzle) if multiPass or hasExtensionCircuit
              else guiPanel(thermalPlots.drawJacketTemperatures, nozzle))
    panels = [guiPanel(thermalPlots.drawCircuit, nozzle), second, wallAlongTheNozzle(nozzle), lastPanel(nozzle)]
    grid = np.concatenate([np.concatenate(panels[:2], axis = 1), np.concatenate(panels[2:], axis = 1)], axis = 0)
    image = np.concatenate([titleStrip(title, grid.shape[1]), grid], axis = 0)
    path = os.path.join(here, f'coolingShowcase_{name}.png')
    plt.imsave(path, image)
    return path

def renderFigure(name: str, nozzle) -> str:

    '''The channel split, or the alternating families and the turnaround ring, in three dimensions.'''

    circuit = getattr(nozzle, 'coolantCircuitSolution', None)
    blend = getattr(nozzle, 'channelSplitBlend', None)
    split = blend is not None and np.any(np.asarray(blend) > 0.0) and getattr(nozzle, 'xChannelSplitA', None) is not None
    if circuit is None and not split:
        return None

    figure = plt.figure(figsize = (10.0, 6.0), constrained_layout = True)
    figure.patch.set_facecolor(theme.surface)
    axis = figure.add_subplot(projection = '3d')
    axis.set_facecolor(theme.surface)

    def draw(x, y, z, color, roll, alpha = 0.95):
        cosine, sine = np.cos(roll), np.sin(roll)
        axis.plot_surface(1000.0 * x, 1000.0 * (y * cosine - z * sine), 1000.0 * (y * sine + z * cosine),
                          color = color, linewidth = 0.0, antialiased = True, shade = True, alpha = alpha)

    if circuit is not None:
        pitch = 2.0 * np.pi / circuit.up.channelCount
        window = slice(-12, None)
        for k in range(-2, 3):
            draw(nozzle.xChannel[:, window], nozzle.yChannel[:, window], nozzle.zChannel[:, window], theme.accent, k * pitch)
            draw(nozzle.xChannelDown[:, window], nozzle.yChannelDown[:, window], nozzle.zChannelDown[:, window],
                 theme.blue, k * pitch)
        around = np.abs(np.arctan2(nozzle.zTurnaround, nozzle.yTurnaround)) < 3.0 * pitch
        ring = [np.where(around, value, np.nan) for value in (nozzle.xTurnaround, nozzle.yTurnaround, nozzle.zTurnaround)]
        draw(*ring, theme.purple, 0.0, alpha = 0.5)
        title = (f'Up (copper) and down (blue) channels near the aft end, turning in a ring of '
                 f'{1e3 * circuit.turnaround.sectionRadius:.1f} mm section')
    else:
        inside = np.flatnonzero((np.asarray(blend) > 0.0) & (np.asarray(blend) < 1.0))
        stop = inside[-1] + 12
        start = nozzle.xChannel.shape[1] - 1
        pitch = 2.0 * np.pi / nozzle.nChannel
        for roll in (-pitch, 0.0, pitch):
            parent = slice(max(inside[0] - 10, 0), start + 1)
            draw(nozzle.xChannel[:, parent], nozzle.yChannel[:, parent], nozzle.zChannel[:, parent], theme.accent, roll)
            daughter = slice(0, stop - start)
            draw(nozzle.xChannelSplitA[:, daughter], nozzle.yChannelSplitA[:, daughter],
                 nozzle.zChannelSplitA[:, daughter], theme.blue, roll)
            draw(nozzle.xChannelSplitB[:, daughter], nozzle.yChannelSplitB[:, daughter],
                 nozzle.zChannelSplitB[:, daughter], theme.purple, roll)
        axis.set_box_aspect((2.5, 1.0, 1.0))
        title = (f'Three of the {nozzle.nChannel} parent channels splitting to two at an area ratio of '
                 f'{float(nozzle.channelSplitAreaRatio):.3g}')

    for label, setter in (('Axial position [mm]', axis.set_xlabel), ('y [mm]', axis.set_ylabel),
                          ('z [mm]', axis.set_zlabel)):
        setter(label, color = theme.textMuted)
    axis.tick_params(colors = theme.textMuted)
    for axisLine in (axis.xaxis, axis.yaxis, axis.zaxis):
        axisLine.set_pane_color(matplotlib.colors.to_rgba(theme.surface2))
        axisLine._axinfo['grid']['color'] = matplotlib.colors.to_rgba(theme.border)
    axis.view_init(elev = 35 if circuit is not None else 62, azim = -60 if circuit is not None else -70)
    axis.set_title(title, color = theme.text, fontsize = 10)
    path = os.path.join(here, f'coolingShowcase_{name}3D.png')
    figure.savefig(path, dpi = 150, facecolor = theme.surface)
    plt.close(figure)
    return path

#--------------------------------------------------------------------------------------------------------------------------#
# -- Capability matrix -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _on(nozzle, name: str) -> bool:

    return str(getattr(nozzle, name, 'off')) in ('on', 'True', 'true')

def _set(nozzle, name: str) -> bool:

    value = getattr(nozzle, name, None)
    if value is None:
        return False
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return bool(value)

def capabilities(nozzle, config: dict) -> dict:

    '''

    Which cooling features one solved engine uses, as short text cells (empty where not used). The
    bypass is read from the configuration, because the solved nozzle carries the bypass the flow
    accounting derives whether or not one was asked for.

    '''

    bypass = config.get('coolantBypassFraction')

    circuit = str(getattr(nozzle, 'coolantCircuit', 'singlePass'))
    extension = getattr(nozzle, 'extensionCircuitSolution', None)
    sources = [layer.source for layer in getattr(getattr(nozzle, 'extensionFilmSolution', None), 'layers', [])]
    cells = {
        'Coolant': str(nozzle.coolant),
        'A. Single pass': 'yes' if circuit == 'singlePass' else '',
        'B. One and a half pass': 'yes' if circuit == 'oneAndHalfPass' else '',
        'C. Two pass': 'yes' if circuit == 'twoPass' else '',
        'D. Extension circuit': '' if extension is None else
            f'{extension.passes} pass{"es" if extension.passes > 1 else ""}, {extension.outlet}',
        'Channel split': f'at {float(nozzle.channelSplitAreaRatio):.3g}' if _set(nozzle, 'channelSplitAreaRatio') else '',
        'Rectangular channels': 'yes' if str(nozzle.channelType) == 'rectangular' else '',
        'Coolant bypass': f'{float(bypass):.0%}' if bypass is not None else '',
        'Coking ceiling': f'{float(nozzle.maxColdWallTemperature):.0f} K' if _set(nozzle, 'maxColdWallTemperature') else '',
        'Thermal barrier': 'yes' if _set(nozzle, 'thermalBarrierThickness') else '',
        'Chamber film': 'yes' if _on(nozzle, 'filmCooling') else '',
        'Dumped coolant film': 'yes' if 'extensionCircuitOutlet' in sources else '',
        'Turbine exhaust film': 'yes' if 'turbineExhaust' in sources else '',
        'Radiation-cooled shell': 'yes' if thermalPlots.extensionSolved(nozzle) else '',
    }
    return cells

def configuration(name: str) -> dict:

    with open(dict((key, path) for key, _, path in ENGINES)[name], encoding = 'utf-8') as handle:
        return json.load(handle)

def capabilityFigure(solved: list) -> str:

    labels = [label for _, label, _ in solved]
    cells = [capabilities(nozzle, configuration(name)) for name, _, nozzle in solved]
    rows = list(cells[0].keys())
    table = [[engine[row] for engine in cells] for row in rows]

    figure = plt.figure(figsize = (12.0, 0.42 * len(rows) + 1.0))
    figure.patch.set_facecolor(theme.surface)
    axis = figure.add_subplot(111)
    axis.set_axis_off()
    cellTable = axis.table(cellText = table, rowLabels = rows, colLabels = labels, loc = 'center', cellLoc = 'center')
    cellTable.auto_set_font_size(False)
    cellTable.set_fontsize(9)
    cellTable.scale(1.0, 1.5)
    for (row, column), cell in cellTable.get_celld().items():
        cell.set_edgecolor(theme.border)
        header = row == 0 or column == -1
        cell.set_facecolor(theme.surface2 if header else theme.surface)
        filled = not header and cell.get_text().get_text() not in ('',)
        cell.get_text().set_color(theme.text if header else (theme.accent if filled else theme.textMuted))
    path = os.path.join(here, 'coolingCapabilities.png')
    figure.savefig(path, dpi = 150, facecolor = theme.surface, bbox_inches = 'tight')
    plt.close(figure)

    print('\n| Feature | ' + ' | '.join(labels) + ' |')
    print('|---|' + '---|' * len(labels))
    for row, cells in zip(rows, table):
        print(f'| {row} | ' + ' | '.join(cells) + ' |')
    return path

#--------------------------------------------------------------------------------------------------------------------------#
# -- Entry -- #
#--------------------------------------------------------------------------------------------------------------------------#

def draw(names = None) -> None:

    theme.applyMatplotlib()
    solved = []
    for name, label, _ in ENGINES:
        nozzle = cached(name)
        if nozzle is None:
            print(f'  {name}: no cached run, skipped')
            continue
        solved.append((name, label, nozzle))
        if names is not None and name not in names:
            continue
        title = configuration(name).get('_title') or 'NOVA nozzle, one-and-a-half pass (B) to the exit'
        print('  wrote', engineFigure(name, title, nozzle))
        render = renderFigure(name, nozzle)
        if render:
            print('  wrote', render)
    if solved:
        print('  wrote', capabilityFigure(solved))

if __name__ == '__main__':
    if '--draw' in sys.argv:
        draw()
    elif '--engine' in sys.argv:
        name = sys.argv[sys.argv.index('--engine') + 1]
        solve(name, dict((key, path) for key, _, path in ENGINES)[name])
        draw([name])
    else:
        for name, _, path in ENGINES:
            solve(name, path)
        draw()
