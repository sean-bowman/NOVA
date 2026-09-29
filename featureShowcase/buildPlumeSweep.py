# -- The shipped nozzle's plume across its usable back pressures -- #

'''

An animation of `Nozzle.plumeField` cycling through lip pressure ratios from 0.75 to 1.8.

The range is the band the station march covers on this contour. Its lower end is a compressed lip,
where the flow is turned isentropically in place of the weak oblique shock it would really take,
and its upper end is the last ratio before the free boundary starts collapsing onto the axis. Below
0.75 the march refuses; above about 1.8 it returns a plume that no longer conserves mass.

Every frame carries its own mass continuity error, because the reach drawn here is six lip radii
rather than the two the solver defaults to. Six is a good length to look at and a poor length to
trust: the error is a few tenths of a per cent at two radii across this whole range and runs to
tens of a per cent at six. The frames are drawn at the reach that shows the shape and labelled with
what that costs.

Run it from the NOVA root, after `python featureShowcase/runBaseCase.py` has written the pickle:

    python featureShowcase/buildPlumeSweep.py

Author: Sean Bowman

'''

import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Polygon

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'src'))

from NOVA.characteristics import CharacteristicGas
from NOVA.contour import quasiOneDimensionalField
from NOVA.plume import PlumeFlow, plumeCharacteristicSeed, plumeExitLine
from NOVA.stationMarch import solveStationField, stationFromLine

LIPRATIOS = np.round(np.arange(0.75, 1.801, 0.05), 3)   # [-], lip static over ambient
REACH = 6.0                # [-], lip radii drawn
NEARREACH = 2.0            # [-], the reach the solver defaults to, reported alongside
RADIALPOINTS = 121         # [-], points across each station
FRAMEMS = 170              # [ms], frame duration

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
})

def lipPressureOf(nozzle) -> float:

    '''The static pressure at the lip, which is the pressure the lip ratio is taken against.'''

    seed = plumeCharacteristicSeed(nozzle.plumeContour())
    flow = PlumeFlow(seed['gamma'], seed['gasConstant'], seed['stagnationTemperature'],
                     seed['stagnationPressure'])
    station = stationFromLine(plumeExitLine(flow, seed, numPoints = 400), RADIALPOINTS)

    return flow.staticPressure(float(station.mach[-1]))

def interiorField(nozzle, exitX):

    '''

    Every characteristic mesh node the contour solve kept, upstream of the lip.

    The mesh is stored in the solve's own normalized coordinates, so it is scaled back to metres
    before being handed out. The nodes are unstructured, which `tricontourf` takes directly.

    '''

    scale = float(getattr(nozzle, 'nozzleScalingFactor', 1.0) or 1.0)
    axial, radial, mach = [], [], []
    for xBlock, rBlock, machBlock in zip(nozzle.allXPoints, nozzle.allRPoints,
                                         nozzle.allMachNumbers):
        blockX = np.asarray(xBlock, dtype = float).ravel()*scale
        blockR = np.asarray(rBlock, dtype = float).ravel()*scale
        blockMach = np.asarray(machBlock, dtype = float).ravel()
        if blockX.shape != blockR.shape or blockX.shape != blockMach.shape:
            continue
        keep = (np.isfinite(blockX) & np.isfinite(blockR) & np.isfinite(blockMach)
                & (blockX <= exitX))
        axial.append(blockX[keep]); radial.append(blockR[keep]); mach.append(blockMach[keep])

    return np.concatenate(axial), np.concatenate(radial), np.concatenate(mach)

def chamberField(nozzle):

    '''

    The chamber and converging section, which carry no characteristic mesh.

    Nothing solves that region: the flow there is subsonic and the mesh starts at the throat. What
    is drawn instead is the one-dimensional answer painted across the radius, where the local area
    ratio fixes one Mach number per station and it is held across the whole cross section. It
    varies axially and not radially, which is exactly what a one-dimensional solve knows.

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

    return field['x'].ravel(), field['r'].ravel(), field['mach'].ravel()

def solveFrames(nozzle, lipPressure):

    '''

    Every field in the sweep, solved up front.

    Solving inside the draw callback would make the animation as slow as the physics; the frames
    are cheap to draw and expensive to compute, so they are computed once and kept.

    '''

    contour = nozzle.plumeContour()
    frames = []
    for ratio in LIPRATIOS:
        ambient = lipPressure/ratio
        field = solveStationField(contour, ambientPressure = ambient, reach = REACH,
                                  radialPoints = RADIALPOINTS)
        if not field.solved:
            print(f'  lip ratio {ratio:.2f} refused: {field.notes[-1][:70]}')
            continue

        # Solved again at the default reach, because the pair is the point. The near field holds
        # across this whole range and the long view does not, and a frame carrying only the second
        # number reads as a solver that never works.
        near = solveStationField(contour, ambientPressure = ambient, reach = NEARREACH,
                                 radialPoints = RADIALPOINTS)
        frames.append({'ratio': float(ratio), 'ambient': ambient,
                       'x': field.nodeX, 'r': field.nodeR, 'mach': field.nodeMach,
                       'boundaryX': field.boundaryX, 'boundaryR': field.boundaryR,
                       'drift': field.massDriftWorst, 'nearDrift': near.massDriftWorst,
                       'trustworthy': bool(near.trustworthy),
                       'lipX': field.lipX, 'lipRadius': field.lipRadius})
        print(f'  lip ratio {ratio:.2f}   ambient {ambient/1000.0:6.1f} kPa   '
              f'drift {near.massDriftWorst:+6.2f} % at {NEARREACH:.0f}, '
              f'{field.massDriftWorst:+7.2f} % at {REACH:.0f}', flush = True)

    return frames

def build():

    with open(os.path.join(here, 'showcaseBase.pkl'), 'rb') as handle:
        nozzle = pickle.load(handle)

    lipPressure = lipPressureOf(nozzle)
    print(f'  lip static pressure {lipPressure:.0f} Pa')
    frames = solveFrames(nozzle, lipPressure)
    if not frames:
        raise RuntimeError('no frame solved; the sweep has nothing to animate')

    lipX, lipRadius = frames[0]['lipX'], frames[0]['lipRadius']
    wallX = (np.asarray(nozzle.xNozzleWall, dtype = float) - lipX)/lipRadius
    wallR = np.asarray(nozzle.rNozzleWall, dtype = float)/lipRadius
    outline = np.vstack([np.column_stack([wallX, wallR]),
                         np.column_stack([wallX[::-1], -wallR[::-1]])])

    # The engine interior does not depend on the back pressure, so it is solved once and redrawn
    # rather than recomputed per frame.
    seed = plumeCharacteristicSeed(nozzle.plumeContour())
    innerX, innerR, innerMach = interiorField(nozzle, seed['exitX'])
    chamberX, chamberR, chamberMach = chamberField(nozzle)
    upstream = [((np.asarray(blockX) - lipX)/lipRadius, np.asarray(blockR)/lipRadius,
                 np.asarray(blockMach))
                for blockX, blockR, blockMach in ((chamberX, chamberR, chamberMach),
                                                  (innerX, innerR, innerMach))]

    # One scale and one set of limits for every frame, so the animation shows the plume changing
    # rather than the axes changing under it. The engine shares the scale, as it is the same Mach
    # number either side of the lip.
    #
    # The scale is set from the supersonic field alone. Letting the chamber into it drops the floor
    # to Mach 0.2 and squeezes the plume, which is the subject, into the top half of the colour
    # range. The chamber is still drawn and simply clips to the bottom colour, which reads correctly
    # for a region that is uniformly slow and carries no solved field anyway.
    supersonic = [block[2] for block in upstream[1:]]
    machLow = min([float(frame['mach'].min()) for frame in frames]
                  + [float(values.min()) for values in supersonic])
    machHigh = max([float(frame['mach'].max()) for frame in frames]
                   + [float(values.max()) for values in supersonic])
    levels = np.linspace(machLow, machHigh, 120)
    extent = max(float(np.abs(frame['boundaryR']).max())/lipRadius for frame in frames)
    extent = max(extent, float(wallR.max()))

    figure, axes = plt.subplots(figsize = (13.0, 5.0))
    figure.subplots_adjust(left = 0.06, right = 0.98, top = 0.80, bottom = 0.16)
    scalar = plt.cm.ScalarMappable(cmap = 'viridis',
                                   norm = plt.Normalize(vmin = machLow, vmax = machHigh))
    bar = figure.colorbar(scalar, ax = axes, pad = 0.01, fraction = 0.030)
    bar.set_label('Mach number [-]', fontsize = 9)

    def draw(index):
        frame = frames[index]
        axes.clear()
        axes.set_facecolor(panel)

        axial = (frame['x'] - lipX)/lipRadius
        radial = frame['r']/lipRadius
        axes.tricontourf(np.concatenate([axial, axial]),
                         np.concatenate([radial, -radial]),
                         np.concatenate([frame['mach'], frame['mach']]),
                         levels = levels, cmap = 'viridis', extend = 'both')

        # The chamber and the diverging section are shaded separately because they are different
        # answers: one dimensional upstream of the throat, where nothing is solved, and the
        # contour's own characteristic mesh downstream of it. Both are clipped to the wall, which
        # has to be re-added every frame because clearing the axes drops its patches.
        for blockX, blockR, blockMach in upstream:
            patch = axes.tricontourf(np.concatenate([blockX, blockX]),
                                     np.concatenate([blockR, -blockR]),
                                     np.concatenate([blockMach, blockMach]),
                                     levels = levels, cmap = 'viridis', extend = 'both')
            clip = Polygon(outline, closed = True, transform = axes.transData,
                           facecolor = 'none', edgecolor = 'none')
            axes.add_patch(clip)
            patch.set_clip_path(clip)

        boundaryX = (frame['boundaryX'] - lipX)/lipRadius
        boundaryR = frame['boundaryR']/lipRadius
        for sign in (1.0, -1.0):
            axes.plot(wallX, sign*wallR, color = copper, lw = 2.4, zorder = 4)
            axes.plot(boundaryX, sign*boundaryR, color = ink, lw = 1.4, zorder = 3)
        axes.axhline(0.0, color = muted, lw = 0.6, ls = '-.', zorder = 3)
        axes.axvline(0.0, color = muted, lw = 0.8, ls = ':', zorder = 3)

        axes.set_xlim(wallX.min(), REACH)
        axes.set_ylim(-1.18*extent, 1.18*extent)
        axes.set_aspect('equal', adjustable = 'box')
        axes.set_xlabel('Distance from the exit plane [lip radii]')
        axes.set_ylabel('Radius [lip radii]')

        axes.set_title(
            f'NOVA nozzle plume, lip ratio {frame["ratio"]:.2f}   '
            f'ambient {frame["ambient"]/1000.0:.1f} kPa\n'
            f'mass continuity error {frame["nearDrift"]:+.2f} % at {NEARREACH:.0f} lip radii, '
            f'{frame["drift"]:+.2f} % at {REACH:.0f}',
            fontsize = 10.5, color = green if frame['trustworthy'] else warn, pad = 10)

        return axes.collections

    animation = FuncAnimation(figure, draw, frames = len(frames), interval = FRAMEMS, blit = False)
    path = os.path.join(here, 'plumeSweep.gif')
    animation.save(path, writer = PillowWriter(fps = max(1, round(1000.0/FRAMEMS))))
    plt.close(figure)

    print()
    print(f'  wrote plumeSweep.gif, {len(frames)} frames, lip ratio '
          f'{frames[0]["ratio"]:.2f} to {frames[-1]["ratio"]:.2f}')
    print(f'  Mach {machLow:.2f} to {machHigh:.2f}')
    print(f'  drift {min(f["nearDrift"] for f in frames):+.2f} to '
          f'{max(f["nearDrift"] for f in frames):+.2f} per cent at {NEARREACH:.0f} lip radii, '
          f'{min(f["drift"] for f in frames):+.2f} to {max(f["drift"] for f in frames):+.2f} at '
          f'{REACH:.0f}')

    return path

if __name__ == '__main__':
    build()
