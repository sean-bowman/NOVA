# -- Verification Figures: Bifurcated Cooling Channels -- #

'''

Figures that show a channel split behaving as intended, thermally and in three dimensions.

1. **The fork.** The parent channel and its two daughters through the transition, with the
   neighboring forks either side, drawn on the jacket of the shipped nozzle.
2. **The section through the split.** The union outline at stations through the transition, from
   one circle to two, at the channel size the sizing march chose.
3. **The split along the jacket.** The shipped LOX/LH2 jacket carried to the exit, sized with sixty
   channels throughout and with the sixty splitting to 120 at an area ratio of 3: channel
   half-extent, flow area per parent channel, coolant velocity, coolant-side coefficient, hot wall
   temperature and coolant pressure.

These are verification figures, not validations: the section geometry is held to closed form in
tests/testChannelSplit.py, and the heat transfer through a split is unvalidated (channelSplit.py).

Run from the NOVA root:

    python validation/coolingCircuits/phase3Verification.py [--reuse]

Author: Sean Bowman

'''

import json
import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(here))
sys.path.insert(0, os.path.join(root, 'src'))

from NOVA import Nozzle, palette
from NOVA.channelSplit import circleUnion, circleUnionOutline, splitSeparation

outputFolder = os.path.join(here, 'phase3')
colors = palette.colors('dark')
plt.rcParams.update(palette.matplotlibStyle('dark'))
plt.rcParams.update({'font.size': 9, 'axes.grid': True, 'grid.alpha': 0.4})

JACKETTOEXIT = {'regenTruncationType': 'none', 'makeRadiativeExtension': False, 'filmCooling': False,
                'numCrossSections': 120, 'plumeAmbientPressure': None, 'plumeFieldReach': None,
                'makeInletVolute': False, 'makeOutletVolute': False}
SPLIT = {**JACKETTOEXIT, 'channelSplitAreaRatio': 3.0, 'channelSplitLength': 6.0}

def solve(name: str, overrides: dict):

    '''Run the shipped configuration with overrides, or load the pickle a previous run left.'''

    picklePath = os.path.join(outputFolder, f'{name}.pkl')
    if '--reuse' in sys.argv and os.path.isfile(picklePath):
        with open(picklePath, 'rb') as handle:
            return pickle.load(handle)

    with open(os.path.join(root, 'src', 'NOVA', 'assets', 'NOVANozzle.json'), encoding = 'utf-8') as handle:
        config = json.load(handle)
    config.update({'plotsEnabled': False, 'export': False, 'filename': name})
    config.update(overrides)
    configPath = os.path.join(outputFolder, f'{name}.json')
    with open(configPath, 'w', encoding = 'utf-8', newline = '\n') as handle:
        json.dump(config, handle, indent = 2)

    original = Nozzle._getOutputRoot
    Nozzle._getOutputRoot = lambda self: outputFolder
    try:
        nozzle = Nozzle()
        nozzle.generateNozzle(configPath = configPath)
    finally:
        Nozzle._getOutputRoot = original

    with open(picklePath, 'wb') as handle:
        pickle.dump(nozzle, handle)
    return nozzle

def sectionSeparation(nozzle) -> np.ndarray:

    '''The daughters' center separation across the section at each station of the built wall.'''

    radius = np.asarray(nozzle.rChannelCenterline2D)
    return splitSeparation(nozzle.channelSplitBlend, radius, nozzle.nChannel)

def transitionWindow(nozzle, margin: int = 4) -> slice:

    '''Stations from a few before the split to a few past it.'''

    blend = np.asarray(nozzle.channelSplitBlend)
    inside = np.flatnonzero((blend > 0.0) & (blend < 1.0))
    return slice(max(inside[0] - margin, 0), min(inside[-1] + margin + 2, len(blend)))

def forkFigure(nozzle) -> str:

    '''Figure 1: three forks in three dimensions, around the transition.'''

    window = transitionWindow(nozzle, margin = 10)
    start = nozzle.xChannel.shape[1] - 1
    figure = plt.figure(figsize = (11.0, 6.0), constrained_layout = True)
    axis = figure.add_subplot(projection = '3d')
    pitch = 2.0 * np.pi / nozzle.nChannel

    def draw(x, y, z, color, roll):
        cosine, sine = np.cos(roll), np.sin(roll)
        axis.plot_surface(1000.0 * x, 1000.0 * (y * cosine - z * sine), 1000.0 * (y * sine + z * cosine),
                          color = color, linewidth = 0.0, antialiased = True, shade = True, alpha = 0.95)

    for roll in (-pitch, 0.0, pitch):
        parent = slice(max(window.start, 0), start + 1)
        draw(nozzle.xChannel[:, parent], nozzle.yChannel[:, parent], nozzle.zChannel[:, parent],
             colors['accent'], roll)
        daughter = slice(0, window.stop - start)
        draw(nozzle.xChannelSplitA[:, daughter], nozzle.yChannelSplitA[:, daughter],
             nozzle.zChannelSplitA[:, daughter], colors['blue'], roll)
        draw(nozzle.xChannelSplitB[:, daughter], nozzle.yChannelSplitB[:, daughter],
             nozzle.zChannelSplitB[:, daughter], colors['green'], roll)
    axis.set_xlabel('Axial position [mm]')
    axis.set_ylabel('y [mm]')
    axis.set_zlabel('z [mm]')
    axis.view_init(elev = 62, azim = -70)
    axis.set_box_aspect((2.5, 1.0, 1.0))
    axis.set_title(f'Three of the {nozzle.nChannel} parent channels splitting to two at an area ratio of '
                   f'{nozzle.channelSplitAreaRatio:.3g}: parent, first and second daughter')
    path = os.path.join(outputFolder, 'channelFork.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def sectionFigure(nozzle) -> str:

    '''Figure 2: the union outline at stations through the transition.'''

    blend = np.asarray(nozzle.channelSplitBlend)
    # The circumferential separation; where the channels lean the section sees it shortened by
    # the cosine of the lean, which the sizing march applies and this drawing does not
    separation = sectionSeparation(nozzle)
    radius = np.asarray(nozzle.channelRadius)
    stations = np.flatnonzero((blend > 0.0) & (blend < 1.0))
    stations = np.concatenate([[stations[0] - 1], stations, [stations[-1] + 1]])
    figure, axes = plt.subplots(1, len(stations), figsize = (1.6 * len(stations) + 1.0, 2.8),
                                constrained_layout = True, sharey = True)
    for axis, station in zip(np.atleast_1d(axes), stations):
        for loop in circleUnionOutline(radius[station], separation[station], 400):
            closed = np.vstack([loop, loop[:1]])
            axis.fill(1000.0 * closed[:, 0], 1000.0 * closed[:, 1], color = colors['accent'], alpha = 0.85)
        union = circleUnion(radius[station], separation[station])
        axis.set_title(f'beta {blend[station]:.2f}\n{1e6 * float(union["flowArea"]):.1f} mm2, '
                       f'Dh {1e3 * float(union["hydraulicDiameter"]):.2f} mm', fontsize = 7)
        axis.set_aspect('equal')
        axis.set_xlabel('[mm]', fontsize = 7)
    figure.suptitle('One parent channel through the split, injector side to aft side')
    path = os.path.join(outputFolder, 'splitSections.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def transitionFigure(single, split) -> str:

    '''Figure 3: the jacket with and without the split.'''

    figure, axes = plt.subplots(2, 3, figsize = (13.0, 6.6), constrained_layout = True)
    axes = axes.ravel()
    for nozzle, color, name in ((single, colors['textMuted'], f'{single.nChannel} channels'),
                                (split, colors['accent'], f'{split.nChannel} splitting to {2*split.nChannel}')):
        x = 1000.0 * np.asarray(nozzle.xRegenNozzleTrimmed)
        results = nozzle.channelThermalResults
        radius = np.asarray(nozzle.channelSizingSolution.channelRadius) if hasattr(
            nozzle.channelSizingSolution, 'channelRadius') else np.asarray(nozzle.channelRadius)
        blend = (np.asarray(nozzle.channelSizingSolution.channelSplitBlend)
                 if getattr(nozzle.channelSizingSolution, 'channelSplitBlend', None) is not None
                 else np.zeros(len(x)))
        pathRadius = np.asarray(nozzle.rRegenNozzleTrimmed) + nozzle.hotWallThickness + radius
        area = circleUnion(radius, splitSeparation(blend, pathRadius, nozzle.nChannel))['flowArea']
        series = ((1e3 * radius, 'Channel half-extent [mm]'),
                  (1e6 * area, 'Flow area per parent channel [mm2]'),
                  (np.asarray(results['velocity']), 'Coolant velocity [m/s]'),
                  (1e-3 * np.asarray(results['coolantConvectiveHeatTransferCoef']), 'Coolant coefficient [kW/m2 K]'),
                  (np.asarray(results['wallTemperature']), 'Hot wall temperature [K]'),
                  (1e-6 * np.asarray(results['pressure']), 'Coolant pressure [MPa]'))
        for axis, (values, label) in zip(axes, series):
            axis.plot(x, values, color = color, label = name)
            axis.set_ylabel(label)
            axis.set_xlabel('Axial position [mm]')
    window = transitionWindow(split, margin = 0)
    xSplit = 1000.0 * np.asarray(split.xRegenNozzleInterfaced)[[window.start, window.stop - 1]]
    for axis in axes:
        axis.axvspan(xSplit[0], xSplit[1], color = colors['blue'], alpha = 0.15)
    axes[0].legend(fontsize = 8)
    figure.suptitle('Shipped LOX/LH2 jacket carried to the exit: one channel count against a split at '
                    'area ratio 3 (shaded)')
    path = os.path.join(outputFolder, 'splitAlongJacket.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def main():

    os.makedirs(outputFolder, exist_ok = True)
    single = solve('jacketToExit', JACKETTOEXIT)
    split = solve('jacketToExitSplit', SPLIT)
    print('  wrote', forkFigure(split))
    print('  wrote', sectionFigure(split))
    print('  wrote', transitionFigure(single, split))

if __name__ == '__main__':
    main()
