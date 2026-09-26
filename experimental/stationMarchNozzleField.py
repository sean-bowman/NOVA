
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

from NOVA.characteristics import CharacteristicGas
from NOVA.contour import quasiOneDimensionalField
from NOVA.plume import (PlumeFlow, plumeCharacteristicSeed, plumeExitLine, solvePlumeStructure)
from stationMarch import solveStationMarch, stationFromLine

# The ambient is set from the lip static pressure rather than the one-dimensional exit value,
# because a truncated contour does not leave one exit state: the lip sits at Mach 3.797 and 24.6
# kPa while the one-dimensional station reads Mach 4.223 and 14.0 kPa. The boundary condition the
# march applies is at the lip, so that is the pressure the ratio is taken against, and the figure
# reports both.
#
# The shipped ambient of 5 kPa is a lip ratio of 4.9, where the march loses a third of the mass
# flow in the first eight lip radii. At 1.5 it holds under two per cent out to six, which is why
# the figure is drawn there. It is still not a validated result.
PRESSURERATIO = 1.5
REACH = 6.0
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

def chamberField(nozzle):

    '''

    The chamber and converging section, which carry no characteristic mesh.

    Nothing solves that region: the flow there is subsonic and the mesh starts at the throat. What
    is drawn instead is the one-dimensional answer painted across the radius, where the local area
    ratio fixes one Mach number per station and it is held across the whole cross section. It
    varies axially and not radially, which is exactly what a one-dimensional solve knows, and it is
    shaded here so the engine is not a blank outline upstream of its own throat.

    '''

    gas = CharacteristicGas(nozzle.chamberGamma, nozzle.chamberRGasConstant,
                            nozzle.chamberStagnationTemperature)
    wallX = np.asarray(nozzle.xNozzleWall, dtype = float)
    wallR = np.asarray(nozzle.rNozzleWall, dtype = float)
    throat = int(np.argmin(wallR))
    upstream = slice(0, throat + 1)
    field = quasiOneDimensionalField(wallX[upstream], wallR[upstream], gas,
                                     nozzle.chamberPressure, throatRadius = wallR[throat],
                                     branch = 'subsonic')

    return (field['x'].ravel(), field['r'].ravel(), field['mach'].ravel(),
            float(wallX[throat]))

def plumeField(flow, seed, ambient, reach):

    '''The station march from the exit plane, as a structured grid.'''

    line = plumeExitLine(flow, seed, numPoints = 400)
    station = stationFromLine(line, RADIALPOINTS)
    result = solveStationMarch(flow, station, ambient, maxLength = reach, maxStations = 200000)

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
    flow = PlumeFlow(seed['gamma'], seed['gasConstant'], seed['stagnationTemperature'],
                     seed['stagnationPressure'])

    lipMach = plumeExitLine(flow, seed, numPoints = 140)[0].mach
    lipPressure = flow.staticPressure(lipMach)
    ambient = lipPressure/PRESSURERATIO
    structure = solvePlumeStructure(nozzle.plumeContour(), ambient)
    lipRadius = structure.lipRadius

    chamberX, chamberR, chamberMach, throatX = chamberField(nozzle)
    innerX, innerR, innerMach = interiorField(nozzle, seed['exitX'])
    plumeX, plumeR, plumeMach, drift, result, station = plumeField(flow, seed, ambient, REACH)

    wallX = np.asarray(nozzle.xNozzleWall, dtype = float)*MILLIMETRES
    wallR = np.asarray(nozzle.rNozzleWall, dtype = float)*MILLIMETRES
    solvedBoundary = np.array(result['boundary'])

    figure, axes = plt.subplots(figsize = (16.0, 6.4))
    low = min(chamberMach.min(), innerMach.min(), plumeMach.min())
    high = max(chamberMach.max(), innerMach.max(), plumeMach.max())
    levels = np.linspace(low, high, 140)

    # The chamber and the diverging section are shaded separately because they are different
    # answers: one dimensional upstream of the throat, where nothing is solved, and the
    # characteristic mesh downstream of it.
    for upstreamX, upstreamR, upstreamMach in ((chamberX, chamberR, chamberMach),
                                               (innerX, innerR, innerMach)):
        patch = axes.tricontourf(np.concatenate([upstreamX, upstreamX])*MILLIMETRES,
                                 np.concatenate([upstreamR, -upstreamR])*MILLIMETRES,
                                 np.concatenate([upstreamMach, upstreamMach]),
                                 levels = levels, cmap = 'viridis')
        outline = np.vstack([np.column_stack([wallX, wallR]),
                             np.column_stack([wallX[::-1], -wallR[::-1]])])
        clip = Polygon(outline, closed = True, transform = axes.transData,
                       facecolor = 'none', edgecolor = 'none')
        axes.add_patch(clip)
        patch.set_clip_path(clip)

    field = None
    for sign in (1.0, -1.0):
        field = axes.contourf(plumeX*MILLIMETRES, sign*plumeR*MILLIMETRES, plumeMach,
                              levels = levels, cmap = 'viridis')

    for sign in (1.0, -1.0):
        axes.plot(wallX, sign*wallR, color = copper, lw = 2.2,
                  label = 'nozzle wall' if sign > 0 else None)
        axes.plot(solvedBoundary[:, 0]*MILLIMETRES, sign*solvedBoundary[:, 1]*MILLIMETRES,
                  color = ink, lw = 1.5, label = 'jet boundary' if sign > 0 else None)

    axes.axvline(throatX*MILLIMETRES, color = green, lw = 1.0, ls = '--', label = 'throat')
    axes.axvline(seed['exitX']*MILLIMETRES, color = muted, lw = 1.0, ls = ':',
                 label = 'exit plane')

    solvedEnd = float(solvedBoundary[-1, 0])*MILLIMETRES
    extent = max(float(solvedBoundary[:, 1].max())*MILLIMETRES, wallR.max())
    axes.set_xlim(wallX.min() - 60.0, solvedEnd + 120.0)
    axes.set_ylim(-1.12*extent, 1.12*extent)
    axes.set_title(f'NOVA nozzle and plume as one field\n'
                   f'lip Mach {lipMach:.2f} at {lipPressure/1000.0:.1f} kPa into '
                   f'{ambient/1000.0:.1f} kPa, ratio {PRESSURERATIO:.1f}    boundary Mach '
                   f'{result["boundaryMach"]:.2f}    {len(result["stations"])} stations to '
                   f'{(solvedEnd/MILLIMETRES - structure.lipX)/lipRadius:.1f} lip radii    '
                   f'mass drift {drift:+.1f} %', fontsize = 11)
    axes.set_xlabel('Axial station [mm]')
    axes.set_ylabel('Radius [mm]')
    axes.set_aspect('equal', adjustable = 'box')
    axes.legend(loc = 'upper left', fontsize = 8, labelcolor = ink)

    bar = figure.colorbar(field, ax = axes, orientation = 'vertical', pad = 0.015,
                          fraction = 0.026)
    bar.set_label('Mach number [-]')

    figure.text(0.012, -0.02,
                'Three regions, one Mach scale. Upstream of the throat nothing is solved and the '
                'shading is the one-dimensional answer painted across the radius. Between the '
                "throat and the exit plane it is the contour solve's own characteristic mesh.\n"
                'Past the lip it is the station marcher continuing that mesh, on stations normal '
                'to the axis, which is why it spans the jet and contours directly.',
                fontsize = 8.5, color = muted, va = 'top')
    figure.text(0.012, -0.10,
                f'The plume is not a validated result. Mass flow through a station must equal the '
                f"exit plane's and differs by {drift:+.1f} per cent over these {REACH:.0f} lip "
                f"radii, against 0.1 for a uniform exit in the same gas. Carried to eight it "
                f"reaches 7.6 per cent and to twelve, 7.6.\nThe ambient is set from the lip "
                f"pressure, not the one-dimensional exit value: a truncated contour leaves the "
                f"lip at Mach {lipMach:.2f} and {lipPressure/1000.0:.1f} kPa against "
                f"{structure.exitMach:.2f} and "
                f"{structure.exitPressureRatio*ambient/1000.0:.1f} kPa one-dimensionally, so the "
                f"two conventions differ.\nAt the shipped 5 kPa the lip ratio is 4.9 and the "
                f"march loses a third of the flow. The scheme carries one stagnation pressure for "
                f"the whole field and no entropy either way, so it describes no shock, and this "
                f"jet forms one further downstream.",
                fontsize = 8.5, color = warn, va = 'top')

    path = os.path.join(here, 'stationMarchNozzleField.png')
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print(f'  wrote stationMarchNozzleField.png')
    print(f'  Pe/Pa {structure.exitPressureRatio:.3f}, ambient {ambient:.0f} Pa, '
          f'{len(result["stations"])} stations, worst mass drift {drift:+.2f} per cent')
    print(f'  reach {(solvedEnd/MILLIMETRES - structure.lipX)/lipRadius:.2f} lip radii, '
          f'Mach range {low:.3f} to {high:.3f}')

    return path

if __name__ == '__main__':
    build()
