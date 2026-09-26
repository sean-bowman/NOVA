
# -- The shipped nozzle and its plume as one picture -- #

'''

The chamber, the contour and the plume drawn continuously, for the nozzle NOVA ships.

The interior comes from the contour solve's own characteristic mesh. The plume comes from the
station marcher, which spans the jet from the center line to the free boundary at every station and
so contours directly, where the characteristic march on this nozzle solves a wedge near the
boundary and never reaches the axis.

----------------------------------------------------------------------
                            What this is not
----------------------------------------------------------------------

**The plume half is not a result.** It is drawn because the shape is worth seeing, and the numbers
on it are reported so nobody mistakes it for one.

This engine's jet carries a Mach disk, a normal shock across the core, which the correlations place
at 7.9 lip radii past the lip and 4.6 lip radii across. The station marcher has no entropy in it:
every relation it solves assumes one stagnation pressure for the whole field. A shock destroys
stagnation pressure, and destroys different amounts on different streamlines, so downstream of the
disk the equations being solved are not the equations governing the flow.

Upstream of the disk it is still wrong, and by a measured amount. Mass flow through a station must
equal mass flow through the exit plane, and it does not: the figure reports the worst departure. A
uniform exit at the same gas and Mach number holds a tenth of a per cent, so what the loss measures
is this scheme meeting a contoured exit rather than anything about the engine.

The correlated boundary and Mach disk are drawn alongside, from
`docs/references_plumeStructure_2026-09-04.md`. Those are fits to measurement and are the numbers to
use for this nozzle's plume scale; the shaded field is not.

Run it from the NOVA root, after `python featureShowcase/runBaseCase.py` has written the pickle:

    python experimental/stationMarchNozzleField.py

Author: Sean Bowman

'''

import math
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

from NOVA.plume import (PlumeFlow, plumeCharacteristicSeed, plumeExitLine, solvePlumeStructure)
from stationMarch import solveStationMarch, stationFromLine

AMBIENT = 5000.0
RADIALPOINTS = 121
MILLIMETRES = 1e3

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
    'axes.titlesize': 12, 'axes.titleweight': 'bold', 'legend.framealpha': 0.0,
})

def interiorField(nozzle, exitX):

    '''Every mesh node the contour solve kept, upstream of the lip.'''

    scale = float(getattr(nozzle, 'nozzleScalingFactor', 1.0) or 1.0)
    x, r, mach = [], [], []
    for xBlock, rBlock, machBlock in zip(nozzle.allXPoints, nozzle.allRPoints,
                                         nozzle.allMachNumbers):
        blockX = np.asarray(xBlock, dtype = float).ravel()*scale
        blockR = np.asarray(rBlock, dtype = float).ravel()*scale
        blockMach = np.asarray(machBlock, dtype = float).ravel()
        if blockX.shape != blockR.shape or blockX.shape != blockMach.shape:
            continue
        keep = (np.isfinite(blockX) & np.isfinite(blockR) & np.isfinite(blockMach)
                & (blockX <= exitX))
        x.append(blockX[keep]); r.append(blockR[keep]); mach.append(blockMach[keep])

    return np.concatenate(x), np.concatenate(r), np.concatenate(mach)

def plumeField(flow, seed, reach):

    '''The station march from the exit plane, as a structured grid.'''

    line = plumeExitLine(flow, seed, numPoints = 400)
    station = stationFromLine(line, RADIALPOINTS)
    result = solveStationMarch(flow, station, AMBIENT, maxLength = reach, maxStations = 200000)

    stations = result['stations']
    x = np.array([[one.x]*one.radius.size for one in stations])
    r = np.array([one.radius for one in stations])
    mach = np.array([one.mach for one in stations])
    drift = np.array(result['massDrift'])

    return x, r, mach, float(drift[np.argmax(np.abs(drift))]), result, station

def build():

    with open(os.path.join(root, 'featureShowcase', 'showcaseBase.pkl'), 'rb') as handle:
        nozzle = pickle.load(handle)

    seed = plumeCharacteristicSeed(nozzle.plumeContour())
    structure = solvePlumeStructure(nozzle.plumeContour(), AMBIENT)
    flow = PlumeFlow(seed['gamma'], seed['gasConstant'], seed['stagnationTemperature'],
                     seed['stagnationPressure'])

    lipRadius = structure.lipRadius
    diskAt = (structure.machDiskX - structure.lipX)/lipRadius if structure.machDiskPresent else 8.0
    reach = max(2.0, diskAt)

    innerX, innerR, innerMach = interiorField(nozzle, seed['exitX'])
    plumeX, plumeR, plumeMach, drift, result, station = plumeField(flow, seed, reach)

    wallX = np.asarray(nozzle.xNozzleWall, dtype = float)*MILLIMETRES
    wallR = np.asarray(nozzle.rNozzleWall, dtype = float)*MILLIMETRES

    # Two panels because the two things worth seeing are three orders of magnitude apart in scale:
    # the engine is 1.15 m long and the correlated plume runs past 12 m, so at equal aspect on one
    # axis the nozzle is a sliver.
    figure, axesPair = plt.subplots(2, 1, figsize = (15.0, 9.0), height_ratios = [1.55, 1.0])
    axes, wide = axesPair
    low = min(innerMach.min(), plumeMach.min())
    high = max(innerMach.max(), plumeMach.max())
    levels = np.linspace(low, high, 120)

    interior = axes.tricontourf(np.concatenate([innerX, innerX])*MILLIMETRES,
                                np.concatenate([innerR, -innerR])*MILLIMETRES,
                                np.concatenate([innerMach, innerMach]),
                                levels = levels, cmap = 'viridis')
    outline = np.vstack([np.column_stack([wallX, wallR]),
                         np.column_stack([wallX[::-1], -wallR[::-1]])])
    clip = Polygon(outline, closed = True, transform = axes.transData,
                   facecolor = 'none', edgecolor = 'none')
    axes.add_patch(clip)
    interior.set_clip_path(clip)

    field = None
    for sign in (1.0, -1.0):
        field = axes.contourf(plumeX*MILLIMETRES, sign*plumeR*MILLIMETRES, plumeMach,
                              levels = levels, cmap = 'viridis')

    solvedBoundary = np.array(result['boundary'])
    for sign in (1.0, -1.0):
        axes.plot(solvedBoundary[:, 0]*MILLIMETRES, sign*solvedBoundary[:, 1]*MILLIMETRES,
                  color = ink, lw = 1.4,
                  label = 'jet boundary, station march' if sign > 0 else None)
        axes.plot(wallX, sign*wallR, color = copper, lw = 2.2,
                  label = 'nozzle wall' if sign > 0 else None)

    if structure.boundaryX.size:
        for sign in (1.0, -1.0):
            axes.plot(structure.boundaryX*MILLIMETRES, sign*structure.boundaryR*MILLIMETRES,
                      color = green, lw = 1.4, ls = '--',
                      label = 'jet boundary, correlated' if sign > 0 else None)

    solvedEnd = float(solvedBoundary[-1, 0])*MILLIMETRES
    extent = max(float(solvedBoundary[:, 1].max())*MILLIMETRES, wallR.max())

    if structure.machDiskPresent:
        half = min(0.5*structure.machDiskDiameter*MILLIMETRES, 1.12*extent)
        axes.plot([structure.machDiskX*MILLIMETRES]*2, [-half, half], color = warn, lw = 2.6,
                  label = 'Mach disk, correlated')

    axes.axvline(seed['exitX']*MILLIMETRES, color = muted, lw = 1.0, ls = ':',
                 label = 'exit plane')

    axes.set_xlim(wallX.min() - 60.0, solvedEnd + 120.0)
    axes.set_ylim(-1.15*extent, 1.15*extent)
    axes.set_title(f'NOVA nozzle and plume, ambient {AMBIENT/1000:.0f} kPa    '
                   f'Pe/Pa {structure.exitPressureRatio:.2f}    '
                   f'Mj {structure.fullyExpandedMach:.2f}    '
                   f'{len(result["stations"])} stations to {reach:.1f} lip radii')
    axes.set_ylabel('Radius [mm]')
    axes.set_aspect('equal', adjustable = 'box')
    axes.legend(loc = 'upper left', fontsize = 8, labelcolor = ink)

    bar = figure.colorbar(field, ax = axes, orientation = 'vertical', pad = 0.015,
                          fraction = 0.026)
    bar.set_label('Mach number [-]')

    # The same jet at the scale the correlations describe it on, so the solved part can be seen
    # for the fraction of the plume it is.
    if structure.boundaryX.size:
        for sign in (1.0, -1.0):
            wide.plot(structure.boundaryX*MILLIMETRES, sign*structure.boundaryR*MILLIMETRES,
                      color = green, lw = 1.5, ls = '--',
                      label = 'jet boundary, correlated' if sign > 0 else None)
            wide.plot(solvedBoundary[:, 0]*MILLIMETRES, sign*solvedBoundary[:, 1]*MILLIMETRES,
                      color = ink, lw = 1.8,
                      label = 'solved by the station march' if sign > 0 else None)
            wide.plot(wallX, sign*wallR, color = copper, lw = 1.8)
    if structure.machDiskPresent:
        half = 0.5*structure.machDiskDiameter*MILLIMETRES
        wide.plot([structure.machDiskX*MILLIMETRES]*2, [-half, half], color = warn, lw = 2.6,
                  label = 'Mach disk, correlated')
    plumeEnd = (structure.lipX + structure.plumeLength)*MILLIMETRES
    for cell in structure.cellX:
        if cell*MILLIMETRES <= plumeEnd:
            wide.axvline(cell*MILLIMETRES, color = muted, lw = 0.7, ls = ':')
    wide.set_xlim(wallX.min() - 60.0, plumeEnd + 200.0)
    wideExtent = max(float(np.abs(structure.boundaryR).max())*MILLIMETRES, extent)
    wide.set_ylim(-1.15*wideExtent, 1.15*wideExtent)
    wide.set_title(f'The same jet at its own scale: cell length '
                   f'{structure.shockCellLength/lipRadius:.1f} lip radii, plume length '
                   f'{structure.plumeLength*MILLIMETRES:.0f} mm, solved fraction '
                   f'{100.0*(solvedEnd/MILLIMETRES - structure.lipX)/structure.plumeLength:.0f} '
                   f'per cent')
    wide.set_xlabel('Axial station [mm]')
    wide.set_ylabel('Radius [mm]')
    wide.set_aspect('equal', adjustable = 'box')
    wide.legend(loc = 'upper left', fontsize = 8, labelcolor = ink)

    figure.text(0.012, -0.015,
                'The interior is the contour solve\'s own characteristic mesh. The plume is the '
                'station marcher continuing it past the lip, on stations normal to the axis, which '
                'is why it spans the jet\nand contours directly. The correlated boundary and Mach '
                'disk are fits to measurement and are the numbers to use for this plume\'s scale.',
                fontsize = 8.5, color = muted, va = 'top')
    figure.text(0.012, -0.085,
                f'DO NOT TRUST THE SHADED PLUME. Mass flow through a station must equal the exit '
                f'plane\'s and differs by {drift:+.1f} per cent here, against 0.1 for a uniform '
                f'exit in the same gas.\nThe correlations put a Mach disk at '
                f'{diskAt:.1f} lip radii: a normal shock, across which stagnation pressure falls '
                f'by a different amount on every streamline. This scheme carries one stagnation '
                f'pressure for the whole field\nand no entropy at all, so nothing it draws at or '
                f'past that station describes the flow. The shape is shown because it is worth '
                f'seeing, not because it is right.',
                fontsize = 8.5, color = warn, va = 'top')

    path = os.path.join(here, 'stationMarchNozzleField.png')
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print(f'  wrote stationMarchNozzleField.png')
    print(f'  Pe/Pa {structure.exitPressureRatio:.3f}, {len(result["stations"])} stations, '
          f'reach {reach:.2f} lip radii, worst mass drift {drift:+.2f} per cent')
    print(f'  Mach disk correlated at {diskAt:.2f} lip radii, '
          f'{structure.machDiskDiameter/(2*lipRadius):.2f} lip radii across')

    return path

if __name__ == '__main__':
    build()
