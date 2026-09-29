# -- The shipped nozzle and thirty-six lip radii of its plume -- #

'''

The Mach field of the same case `stationMarchErrorField.py` contours the error on.

`stationMarchNozzleField.py` draws six lip radii, which is one shock cell and is the length the
march holds to a few per cent. This draws thirty-six, four cells, so the structure the error rides
on is visible next to the error itself. The two figures are the same solve at the same lip ratio and
differ only in reach and in what is contoured.

The interior comes from the contour solve's own characteristic mesh and the chamber from a
one-dimensional solve painted across the radius, as in the six-radius figure. Past the lip it is the
station marcher.

**The plume half is not a result.** The march loses 12.1 per cent of the exit mass flow over this
reach, spent at the axis foci, and `stationMarchErrorField.py` is the figure that shows where. The
scheme carries one stagnation pressure for the whole field, so it describes no shock. At this lip
ratio the correlations place no Mach disk, but real cells of this strength steepen into weak shocks
the scheme cannot represent, so the cell train drawn here is smoother than the physical one.

Run it from the NOVA root, after `python featureShowcase/runBaseCase.py` has written the pickle:

    python experimental/stationMarchLongField.py

Author: Sean Bowman

'''

import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'src'))
sys.path.insert(0, here)

from NOVA.plume import PlumeFlow, plumeCharacteristicSeed, plumeExitLine, solvePlumeStructure
from stationMarch import solveStationMarch, stationFromLine
from stationMarchErrorField import axisFoci
from stationMarchNozzleField import chamberField, copper, green, ink, interiorField, muted, panel

PRESSURERATIO = 1.5        # [-], lip static pressure over ambient
REACH = 36.0               # [-], axial distance marched, in lip radii
RADIALPOINTS = 161         # [-], points across each station
def build():

    with open(os.path.join(root, 'featureShowcase', 'showcaseBase.pkl'), 'rb') as handle:
        nozzle = pickle.load(handle)

    seed = plumeCharacteristicSeed(nozzle.plumeContour())
    flow = PlumeFlow(seed['gamma'], seed['gasConstant'], seed['stagnationTemperature'],
                     seed['stagnationPressure'])
    station = stationFromLine(plumeExitLine(flow, seed, numPoints = 400), RADIALPOINTS)
    lipPressure = flow.staticPressure(float(station.mach[-1]))
    ambient = lipPressure / PRESSURERATIO
    result = solveStationMarch(flow, station, ambient, maxLength = REACH, maxStations = 200000)
    structure = solvePlumeStructure(nozzle.plumeContour(), ambient)
    lipRadius, lipX = structure.lipRadius, structure.lipX

    # Everything is drawn in lip radii from the exit plane, so a position on this figure reads
    # straight across to the same position on the error field.
    def inRadii(values):
        return (np.asarray(values, dtype = float) - lipX) / lipRadius

    stations = result['stations']
    plumeX = inRadii([[one.x]*one.radius.size for one in stations])
    plumeR = np.array([one.radius for one in stations]) / lipRadius
    plumeMach = np.array([one.mach for one in stations])
    axisMach = plumeMach[:, 0]
    reach = inRadii([one.x for one in stations])
    foci = axisFoci(axisMach)

    chamberXm, chamberRm, chamberMach, throatXm = chamberField(nozzle)
    innerXm, innerRm, innerMach = interiorField(nozzle, seed['exitX'])
    wallX = inRadii(nozzle.xNozzleWall)
    wallR = np.asarray(nozzle.rNozzleWall, dtype = float) / lipRadius
    boundary = np.array(result['boundary'])
    boundaryX, boundaryR = inRadii(boundary[:, 0]), boundary[:, 1] / lipRadius

    figure, axes = plt.subplots(figsize = (26.0, 3.4))
    low = min(chamberMach.min(), innerMach.min(), plumeMach.min())
    high = max(chamberMach.max(), innerMach.max(), plumeMach.max())
    levels = np.linspace(low, high, 160)

    # The chamber and the diverging section are shaded separately because they are different
    # answers: one dimensional upstream of the throat, where nothing is solved, and the
    # characteristic mesh downstream of it. Both are clipped to the wall.
    outline = np.vstack([np.column_stack([wallX, wallR]),
                         np.column_stack([wallX[::-1], -wallR[::-1]])])
    for blockX, blockR, blockMach in ((chamberXm, chamberRm, chamberMach),
                                      (innerXm, innerRm, innerMach)):
        upstream = axes.tricontourf(inRadii(np.concatenate([blockX, blockX])),
                                    np.concatenate([blockR, -blockR]) / lipRadius,
                                    np.concatenate([blockMach, blockMach]),
                                    levels = levels, cmap = 'viridis')
        clip = Polygon(outline, closed = True, transform = axes.transData,
                       facecolor = 'none', edgecolor = 'none')
        axes.add_patch(clip)
        upstream.set_clip_path(clip)

    patch = None
    for sign in (1.0, -1.0):
        patch = axes.contourf(plumeX, sign * plumeR, plumeMach, levels = levels, cmap = 'viridis')

    for sign in (1.0, -1.0):
        axes.plot(wallX, sign * wallR, color = copper, lw = 2.0, zorder = 3,
                  label = 'nozzle wall' if sign > 0 else None)
        axes.plot(boundaryX, sign * boundaryR, color = ink, lw = 1.3, zorder = 3,
                  label = 'jet boundary' if sign > 0 else None)

    axes.axvline(inRadii(throatXm), color = green, lw = 1.0, ls = '--', zorder = 3,
                 label = 'throat')
    for order, index in enumerate(foci):
        axes.axvline(reach[index], color = ink, lw = 0.9, ls = ':', alpha = 0.7, zorder = 3,
                     label = 'axis foci' if order == 0 else None)

    axes.set_xlim(wallX.min(), reach[-1])
    axes.set_ylim(-1.35, 1.35)
    axes.set_aspect('equal', adjustable = 'box')
    axes.set_xlabel('Distance downstream of the exit plane [lip radii]')
    axes.set_ylabel('Radius [lip radii]')
    axes.set_title('NOVA nozzle and thirty-six lip radii of plume', fontsize = 13, pad = 26)
    axes.text(0.5, 1.02,
              f'lip Mach {float(station.mach[-1]):.2f} at {lipPressure/1000.0:.1f} kPa into '
              f'{ambient/1000.0:.1f} kPa, lip ratio {PRESSURERATIO:.1f}   |   '
              f'{len(stations)} stations to {reach[-1]:.1f} lip radii   |   {len(foci)} axis foci, '
              f'a cell every {np.mean(np.diff([reach[i] for i in foci])):.1f}   |   '
              f'center-line Mach {axisMach.min():.2f} to {axisMach.max():.2f}',
              transform = axes.transAxes, ha = 'center', va = 'bottom', fontsize = 9.5,
              color = muted)
    axes.legend(loc = 'lower left', fontsize = 8, labelcolor = ink, ncol = 4,
                bbox_to_anchor = (0.0, 1.06))

    # Equal aspect shrinks the axes box inside its gridspec cell, and the colorbar is sized from
    # the cell rather than the box, so it is shrunk by hand to match the panel.
    bar = figure.colorbar(patch, ax = axes, orientation = 'vertical', pad = 0.008,
                          fraction = 0.014, shrink = 0.62)
    bar.set_label('Mach number [-]', fontsize = 8.5)
    bar.ax.tick_params(labelsize = 8)

    figure.text(0.012, 0.02,
                'Three regions, one Mach scale. Upstream of the throat nothing is solved and the '
                'shading is the one-dimensional answer painted across the radius. Between the '
                'throat and the exit plane it is the contour solve\'s own characteristic mesh.\n'
                'Past the lip it is the station marcher, on stations normal to the axis, which is '
                'why it spans the jet and contours directly. The dotted lines are where the wave '
                'fronts converge on the center line.',
                fontsize = 8.5, color = muted, va = 'top')
    figure.text(0.012, -0.16,
                'The plume half is not a result. Mass flow through a station must equal the exit '
                'plane\'s and departs by 12.1 per cent over this reach, spent at the foci marked; '
                '`stationMarchErrorField.py` contours where it goes.\n'
                'The scheme carries one stagnation pressure for the whole field and so describes '
                'no shock. At this lip ratio the correlations place no Mach disk, but cells of '
                'this strength steepen into weak shocks, so this train is smoother than the real '
                'one.',
                fontsize = 8.5, color = '#E8A0A0', va = 'top')

    path = os.path.join(here, 'stationMarchLongField.png')
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print('  wrote stationMarchLongField.png')
    print(f'  {len(stations)} stations to {reach[-1]:.2f} lip radii, stop {result["stop"]}, '
          f'Mach range {low:.3f} to {high:.3f}')
    print('  axis foci at ' + ', '.join(f'{reach[i]:.2f}' for i in foci) + ' lip radii')

    return path

if __name__ == '__main__':
    build()
