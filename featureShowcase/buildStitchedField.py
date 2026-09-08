'''
Chamber to exit in one frame: the converging section and the diverging section on one colour scale.

The two halves are not the same kind of result and the figure says so. Upstream of the throat there
is no characteristics mesh and nothing solves the flow; what is drawn is the quasi one-dimensional
answer, one Mach number per station held across the cross section. Downstream of the throat the
field is the solved characteristics mesh, with a state at every node.

Putting them on one colour scale is what makes the figure useful and also what makes it easy to
misread, so the seam is marked and captioned rather than blended away.

Run after runBaseCase.py:

    python featureShowcase/buildStitchedField.py
'''
import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.gridspec import GridSpec
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'NOVANozzleDesigner'))

from characteristics import CharacteristicGas
from contour import quasiOneDimensionalField

background = '#1a1e2a'
panel      = '#222735'
copper     = '#E0975A'
green      = '#86C06C'
ink        = '#E8E6E1'
muted      = '#8B93A7'
warn       = '#E8A0A0'

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': '#333A4D',
    'axes.grid': False, 'font.size': 9,
    'axes.titlesize': 11, 'axes.titleweight': 'bold', 'legend.framealpha': 0.0,
})

# Field name on the Nozzle object, label, unit, scale factor, colour map, and whether the scale is
# logarithmic. Pressure falls by three orders of magnitude between the chamber and the exit, so a
# linear scale renders the entire diverging section as one flat black and says nothing about it.
quantities = {
    'mach':        ('allMachNumbers',  'Mach number',        '[-]',   1.0,  'viridis', False),
    'pressure':    ('allPressures',    'Static pressure',    '[MPa]', 1e-6, 'magma',   True),
    'temperature': ('allTemperatures', 'Static temperature', '[K]',   1.0,  'inferno', False),
}

def mirrored(x, r, values):
    '''
    Mirror a half field about the axis, keeping the radial coordinate monotone.

    Concatenating the half onto its own negative leaves the grid doubling back on itself, and
    contourf then fills only one side of it.
    '''
    return (np.concatenate([x[:, ::-1], x], axis = 1),
            np.concatenate([-r[:, ::-1], r], axis = 1),
            np.concatenate([values[:, ::-1], values], axis = 1))

def solvedPoints(nozzle, attribute, scale):
    '''
    The characteristics mesh as scattered points.

    The mesh is curvilinear and padded with NaN, so it is drawn from its finite nodes rather than
    as a structured grid, which is the same treatment the other field figures use.
    '''
    xs, rs, vs = [], [], []
    for xBlock, rBlock, valueBlock in zip(nozzle.allXPoints, nozzle.allRPoints,
                                          getattr(nozzle, attribute)):
        xBlock = np.asarray(xBlock, dtype = float).ravel() * nozzle.nozzleScalingFactor
        rBlock = np.asarray(rBlock, dtype = float).ravel() * nozzle.nozzleScalingFactor
        valueBlock = np.asarray(valueBlock, dtype = float).ravel() * scale
        keep = np.isfinite(xBlock) & np.isfinite(rBlock) & np.isfinite(valueBlock)
        xs.append(xBlock[keep])
        rs.append(rBlock[keep])
        vs.append(valueBlock[keep])
    return np.concatenate(xs), np.concatenate(rs), np.concatenate(vs)

def drawStitched(nozzle, quantity):
    '''One quantity from the chamber to the exit, on a single colour scale.'''
    attribute, label, unit, scale, colourMap, logarithmic = quantities[quantity]

    gas = CharacteristicGas(nozzle.chamberGamma, nozzle.chamberRGasConstant,
                            nozzle.chamberStagnationTemperature)
    wallX = np.asarray(nozzle.xNozzleWall, dtype = float)
    wallR = np.asarray(nozzle.rNozzleWall, dtype = float)
    throatIndex = int(np.argmin(wallR))
    throatX = wallX[throatIndex]

    # -- Upstream: quasi one-dimensional, nothing solved -- #
    upstream = quasiOneDimensionalField(wallX[:throatIndex + 1], wallR[:throatIndex + 1], gas,
                                        nozzle.chamberPressure,
                                        throatRadius = wallR[throatIndex], branch = 'subsonic')
    upstreamX, upstreamR, upstreamValues = mirrored(upstream['x'], upstream['r'],
                                                    upstream[quantity] * scale)

    # -- Downstream: the characteristics mesh, clipped to the wall that is actually built -- #
    meshX, meshR, meshValues = solvedPoints(nozzle, attribute, scale)
    inside = (meshX >= throatX) & (meshX <= wallX[-1])
    meshX, meshR, meshValues = meshX[inside], meshR[inside], meshValues[inside]

    lowest = min(float(np.nanmin(upstreamValues)), float(np.nanmin(meshValues)))
    highest = max(float(np.nanmax(upstreamValues)), float(np.nanmax(meshValues)))
    if logarithmic:
        levels = np.geomspace(max(lowest, highest * 1e-4), highest, 80)
        normalisation = LogNorm(vmin = levels[0], vmax = levels[-1])
    else:
        levels = np.linspace(lowest, highest, 80)
        normalisation = None

    figure = plt.figure(figsize = (13.5, 5.4))
    grid = GridSpec(2, 1, height_ratios = [1.0, 0.045], hspace = 0.42, figure = figure)
    axes = figure.add_subplot(grid[0])

    axes.contourf(upstreamX * 1e3, upstreamR * 1e3, upstreamValues,
                  levels = levels, cmap = colourMap, extend = 'both', norm = normalisation)
    mesh = axes.tricontourf(np.concatenate([meshX, meshX]) * 1e3,
                            np.concatenate([meshR, -meshR]) * 1e3,
                            np.concatenate([meshValues, meshValues]),
                            levels = levels, cmap = colourMap, extend = 'both',
                            norm = normalisation)

    axes.plot(wallX * 1e3, wallR * 1e3, color = copper, lw = 1.7)
    axes.plot(wallX * 1e3, -wallR * 1e3, color = copper, lw = 1.7)

    # The seam. Marked rather than blended, because the two sides are different kinds of answer.
    axes.axvline(throatX * 1e3, color = ink, lw = 1.1, ls = '--', alpha = 0.75)
    span = abs(wallR).max() * 1e3
    axes.text(throatX * 1e3 - 0.012 * (wallX[-1] - wallX[0]) * 1e3, 0.86 * span,
              'one dimensional', color = ink, fontsize = 8, ha = 'right', style = 'italic')
    axes.text(throatX * 1e3 + 0.012 * (wallX[-1] - wallX[0]) * 1e3, 0.86 * span,
              'solved', color = ink, fontsize = 8, ha = 'left', style = 'italic')

    axes.set_xlim(wallX.min() * 1e3, wallX.max() * 1e3)
    axes.set_ylim(-1.1 * span, 1.1 * span)
    axes.set_xlabel('Axial station [mm]')
    axes.set_ylabel('Radius [mm]')
    axes.set_title(f'{label} from the chamber to the exit')
    axes.set_aspect('equal', adjustable = 'box')
    axes.grid(False)

    bar = figure.colorbar(mesh, cax = figure.add_subplot(grid[1]), orientation = 'horizontal',
                          label = f'{label} {unit}' + (', logarithmic' if logarithmic else ''))
    if logarithmic:
        # Decade ticks. The default picks the level values themselves, which on a geometric
        # sequence come out as unreadable six-figure mantissas.
        decades = 10.0 ** np.arange(np.floor(np.log10(levels[0])), np.ceil(np.log10(levels[-1])) + 1)
        decades = decades[(decades >= levels[0]) & (decades <= levels[-1])]
        bar.set_ticks(decades)
        bar.set_ticklabels([f'{value:g}' for value in decades])
    figure.text(0.012, 0.005,
                'One colour scale spans both halves, and they are not the same kind of result. '
                'Upstream of the throat nothing is solved: the local area ratio fixes one Mach '
                'number per station and it is held across the section. Downstream the field is the '
                'characteristics solution, with a state at every node.',
                fontsize = 8, color = warn, va = 'bottom')

    path = os.path.join(here, f'stitchedField{quantity.capitalize()}.png')
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print(f'  wrote {os.path.basename(path)}')
    return path

def main():
    with open(os.path.join(here, 'showcaseBase.pkl'), 'rb') as handle:
        nozzle = pickle.load(handle)

    print('Rendering stitched chamber-to-exit fields')
    for quantity in quantities:
        drawStitched(nozzle, quantity)

if __name__ == '__main__':
    main()
