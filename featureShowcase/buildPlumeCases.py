'''
Individual plume figures, one operating regime per file, drawn at equal aspect ratio.

The boundary, shock cell spacing and Mach disk are correlations from
docs/references_plumeStructure_2026-09-04.md. The plume interior is not a
solved flowfield and is not shaded as one.
'''
import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np

import showcasePalette

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
background = showcasePalette.background
panel      = showcasePalette.panel
copper     = showcasePalette.copper
green      = showcasePalette.green
ink        = showcasePalette.ink
muted      = showcasePalette.muted
blue       = showcasePalette.blue

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': showcasePalette.gridColor,
    'axes.grid': True, 'grid.alpha': 0.35, 'font.size': 9,
    'axes.titlesize': 12, 'axes.titleweight': 'bold', 'legend.framealpha': 0.0,
})

# Pe/Pa for each regime. Separation follows the Summerfield criterion, Pe/Pa < 0.4.
regimes = [('highlyUnderexpanded', 'Highly underexpanded', 10.0),
           ('ideallyExpanded',     'Ideally expanded',      1.0),
           ('overexpanded',        'Overexpanded',          0.6),
           ('separated',           'Separated',             0.3)]

def drawCase(nozzle, slug, label, pressureRatio, exitPressure):
    '''One regime, equal aspect, figure sized to the plume it is drawing.'''
    structure = nozzle.plumeStructure(ambientPressure = exitPressure / pressureRatio)
    if structure is None:
        print(f'  skipped {slug}: no plume structure')
        return None

    wallX = np.asarray(nozzle.xNozzleWall) * 1e3
    wallR = np.asarray(nozzle.rNozzleWall) * 1e3
    boundaryX = np.asarray(structure.boundaryX) * 1e3
    boundaryR = np.asarray(structure.boundaryR) * 1e3

    # Equal aspect on a long thin plume needs a wide canvas, or the axes collapse to a line.
    axialSpan = boundaryX.max() - wallX.min()
    radialSpan = 2.2 * max(boundaryR.max(), wallR.max())
    aspect = float(np.clip(axialSpan / max(radialSpan, 1e-9), 1.0, 9.0))
    figure, axes = plt.subplots(figsize = (min(3.0 + 1.55 * aspect, 17.0), 4.6))

    axes.plot(wallX, wallR, color = copper, lw = 1.8, label = 'nozzle wall', zorder = 4)
    axes.plot(wallX, -wallR, color = copper, lw = 1.8, zorder = 4)

    axes.plot(boundaryX, boundaryR, color = green, lw = 1.8, label = 'jet boundary')
    axes.plot(boundaryX, -boundaryR, color = green, lw = 1.8)
    axes.fill_between(boundaryX, boundaryR, -boundaryR, color = green, alpha = 0.10)

    cells = np.asarray(structure.cellX) * 1e3
    for index, cell in enumerate(cells):
        if cell > boundaryX.max():
            continue
        axes.axvline(cell, color = muted, lw = 0.7, ls = ':',
                     label = 'shock cell node' if index == 0 else None)

    if structure.machDiskPresent:
        half = structure.machDiskDiameter * 0.5e3
        axes.plot([structure.machDiskX * 1e3] * 2, [-half, half], color = blue, lw = 2.6,
                  label = 'Mach disk', zorder = 5)

    axes.set_title(f'{label}    Pe/Pa {structure.exitPressureRatio:.2f}    '
                   f'NPR {structure.nozzlePressureRatio:.0f}    '
                   f'Mj {structure.fullyExpandedMach:.2f}    '
                   f'cell {structure.shockCellLength * 1e3:.0f} mm')
    axes.set_xlabel('Axial station [mm]')
    axes.set_ylabel('Radius [mm]')
    if getattr(structure, 'boundaryAmplitudeLimited', False):
        axes.text(0.015, 0.04,
                  'Correlation out of range: the cell amplitude implies a swell wider than the '
                  'lip radius, so the drawn\nboundary understates the plume width. Cell spacing '
                  'and Mach disk location remain valid.',
                  transform = axes.transAxes, fontsize = 7.5, color = showcasePalette.warn, va = 'bottom')

    axes.set_xlim(wallX.min(), boundaryX.max())
    axes.set_aspect('equal', adjustable = 'box')
    axes.legend(loc = 'upper right', fontsize = 8, labelcolor = ink)

    path = os.path.join(here, f'plume_{slug}.png')
    figure.savefig(path, dpi = 160, bbox_inches = 'tight')
    plt.close(figure)
    print(f'  wrote plume_{slug}.png   (aspect {aspect:.1f}:1)')
    return path

def main():
    '''Render every regime from the pickled base run.'''
    with open(os.path.join(here, 'showcaseBase.pkl'), 'rb') as handle:
        nozzle = pickle.load(handle)

    reference = nozzle.plumeStructure(ambientPressure = 101325.0)
    exitPressure = reference.exitPressureRatio * 101325.0

    print('Rendering plume regimes')
    for slug, label, pressureRatio in regimes:
        drawCase(nozzle, slug, label, pressureRatio, exitPressure)

if __name__ == '__main__':
    main()
