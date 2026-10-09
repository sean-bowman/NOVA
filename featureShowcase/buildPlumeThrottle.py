# -- The shipped nozzle's plume across its throttle range at one altitude -- #

'''

An animation of `Nozzle.throttledPlumeField` walking the engine down from rated power.

This is the counterpart of `buildPlumeSweep.py`. That one holds the engine and varies the
altitude; this one holds the altitude and varies the engine. The two are not independent: the
march carries one stagnation pressure and its relations are homogeneous in pressure, so the field
at a given exit pressure ratio is the same field whichever way the ratio was reached. What this
sweep answers that the other cannot is how far this engine can be throttled at a given altitude
before its own nozzle separates.

The ambient is chosen so that rated power sits at the top of the march's envelope, which puts the
whole attached range of the engine inside one animation. Below the Summerfield separation
criterion the march refuses, and the sweep stops there rather than drawing a plume for a nozzle
that is not flowing full.

The gas state is held at its rated value. Over a 5:1 throttle on this propellant combination the
chamber ratio of specific heats moves 1.0 per cent and the one-dimensional exit Mach number 1.6
per cent, which is inside the march's own mass drift, while the exit static pressure ratio moves
4.9 per cent, which biases where separation is reported by about the same amount. That bias is the
size of the spread in the separation criterion itself, and `docs/plumeThrottleModel.md` records
both.

Performance is the analytic consequence of the same frozen gas state: mass flow and exit pressure
scale with the chamber, exit velocity does not. It is drawn only over the attached range, because
below separation the jet leaves from somewhere inside the nozzle and the geometric exit area is
no longer the area that matters.

**The specific impulse here is one dimensional and ideal.** It is the exit momentum at the
chamber's ratio of specific heats plus the pressure term at this ambient, with no divergence
loss, no boundary layer and no kinetic loss, so it sits above the ideal figure the contour solve
reports for the same engine, which is computed at the design expansion by a different route. What
it is for is the shape of the curve against power level, not the level of it.

Run it from the NOVA root, after `python featureShowcase/runBaseCase.py` has written the pickle:

    python featureShowcase/buildPlumeThrottle.py

Author: Sean Bowman

'''

import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np

import showcasePalette
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Polygon

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'src'))

from NOVA.characteristics import CharacteristicGas
from NOVA.contour import quasiOneDimensionalField
from NOVA.plume import (plumeCharacteristicSeed, plumeFieldMaxPressureRatio,
                        separationPressureRatio, solvePlumeStructure, throttledContour)
from NOVA.stationMarch import solveStationField

THROTTLESTEP = 0.05        # [-], power level step
REACH = 6.0                # [-], lip radii drawn
NEARREACH = 2.0            # [-], the reach the solver defaults to, reported alongside
RADIALPOINTS = 121         # [-], points across each station
FRAMEMS = 170              # [ms], frame duration
GRAVITY = 9.80665          # [m/s^2], standard gravity, for specific impulse

background = showcasePalette.background
panel      = showcasePalette.panel
copper     = showcasePalette.copper
green      = showcasePalette.green
ink        = showcasePalette.ink
muted      = showcasePalette.muted
warn       = showcasePalette.warn

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': showcasePalette.gridColor,
    'axes.grid': False, 'font.size': 9,
})

def ambientForFullThrottle(nozzle) -> float:

    '''

    The ambient that puts rated power at the top of the march's envelope.

    Any lower and rated power is refused for being too underexpanded; any higher and the engine
    gives up attached-flow throttle range for nothing. Taking it from the solved structure rather
    than from a constant keeps the sweep pointed at whatever contour the base run produced.

    '''

    rated = solvePlumeStructure(nozzle.plumeContour(), ambientPressure = 101325.0)

    return float(rated.exitPressure)/plumeFieldMaxPressureRatio

def separationThrottle(nozzle, ambientPressure: float) -> float:

    '''

    The power level at which the exit pressure ratio reaches the Summerfield criterion.

    At a frozen gas state the exit pressure scales with the chamber, so this is exact within the
    model rather than a search. It is where the sweep stops.

    '''

    rated = solvePlumeStructure(nozzle.plumeContour(), ambientPressure = ambientPressure)

    return separationPressureRatio/float(rated.exitPressureRatio)

def performanceCurve(nozzle, ambientPressure: float, fractions):

    '''

    Thrust and specific impulse against power level, at the frozen gas state.

    Mass flow and every static pressure scale with the chamber while the exit velocity does not,
    because the exit Mach number is set by the area ratio. So thrust is the momentum term scaled
    by the power level plus a pressure term that goes negative as the engine throttles into
    overexpansion, which is most of what a throttle curve has to say.

    '''

    gamma = float(nozzle.chamberGamma)
    gasConstant = float(nozzle.chamberRGasConstant)
    exitMach = float(nozzle.exitMachNumber)
    exitTemperature = float(nozzle.chamberStagnationTemperature) \
                      / (1.0 + 0.5*(gamma - 1.0)*exitMach**2)
    exitVelocity = exitMach*np.sqrt(gamma*gasConstant*exitTemperature)

    structure = solvePlumeStructure(nozzle.plumeContour(), ambientPressure = ambientPressure)
    exitArea = np.pi*float(structure.lipRadius)**2
    ratedExitPressure = float(structure.exitPressure)
    ratedMassFlow = float(nozzle.engineMassFlow)

    fractions = np.asarray(fractions, dtype = float)
    massFlow = ratedMassFlow*fractions
    thrust = massFlow*exitVelocity + (ratedExitPressure*fractions - ambientPressure)*exitArea

    return {'fraction': fractions, 'thrust': thrust, 'massFlow': massFlow,
            'specificImpulse': thrust/(massFlow*GRAVITY),
            'exitVelocity': exitVelocity, 'exitArea': exitArea}

def interiorField(nozzle, exitX):

    '''Every characteristic mesh node the contour solve kept, upstream of the lip, in metres.'''

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

    The Mach field there is the one-dimensional answer painted across the radius, which varies
    axially and not radially. It does not move with power level at a frozen gas state, so it is
    solved once for the whole animation.

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

def solveFrames(nozzle, ambientPressure, fractions):

    '''

    Every field in the sweep, solved up front.

    Each power level is its own contour, built by `throttledContour` so that every absolute
    pressure moves together. Scaling the chamber alone would leave the separation check reading
    the rated engine, and at a fixed ambient it would then never trip at any power level.

    '''

    rated = nozzle.plumeContour()
    frames = []
    for fraction in fractions:
        contour = throttledContour(rated, fraction)
        field = solveStationField(contour, ambientPressure = ambientPressure, reach = REACH,
                                  radialPoints = RADIALPOINTS)
        if not field.solved:
            print(f'  {100*fraction:5.1f} % power refused: {field.notes[-1][:72]}')
            break

        near = solveStationField(throttledContour(rated, fraction),
                                 ambientPressure = ambientPressure, reach = NEARREACH,
                                 radialPoints = RADIALPOINTS)
        frames.append({'fraction': float(fraction), 'ratio': field.exitPressureRatio,
                       'x': field.nodeX, 'r': field.nodeR, 'mach': field.nodeMach,
                       'boundaryX': field.boundaryX, 'boundaryR': field.boundaryR,
                       'drift': field.massDriftWorst, 'nearDrift': near.massDriftWorst,
                       'trustworthy': bool(near.trustworthy),
                       'lipX': field.lipX, 'lipRadius': field.lipRadius})
        print(f'  {100*fraction:5.1f} % power   Pe/Pa {field.exitPressureRatio:5.3f}   '
              f'drift {near.massDriftWorst:+6.2f} % at {NEARREACH:.0f}, '
              f'{field.massDriftWorst:+7.2f} % at {REACH:.0f}', flush = True)

    return frames

def build():

    with open(os.path.join(here, 'showcaseBase.pkl'), 'rb') as handle:
        nozzle = pickle.load(handle)

    ambient = ambientForFullThrottle(nozzle)
    separating = separationThrottle(nozzle, ambient)
    floor = THROTTLESTEP*np.floor(separating/THROTTLESTEP)
    fractions = np.round(np.arange(1.0, floor - 0.5*THROTTLESTEP, -THROTTLESTEP), 3)

    print('Rendering the throttle sweep')
    print(f'  ambient {ambient/1000.0:.2f} kPa, held for every frame')
    print(f'  nozzle separates below {100*separating:.1f} % power')
    frames = solveFrames(nozzle, ambient, fractions)
    if not frames:
        raise RuntimeError('no frame solved; the sweep has nothing to animate')

    performance = performanceCurve(nozzle, ambient, [frame['fraction'] for frame in frames])

    lipX, lipRadius = frames[0]['lipX'], frames[0]['lipRadius']
    wallX = (np.asarray(nozzle.xNozzleWall, dtype = float) - lipX)/lipRadius
    wallR = np.asarray(nozzle.rNozzleWall, dtype = float)/lipRadius
    outline = np.vstack([np.column_stack([wallX, wallR]),
                         np.column_stack([wallX[::-1], -wallR[::-1]])])

    seed = plumeCharacteristicSeed(nozzle.plumeContour())
    innerX, innerR, innerMach = interiorField(nozzle, seed['exitX'])
    chamberX, chamberR, chamberMach = chamberField(nozzle)
    upstream = [((np.asarray(blockX) - lipX)/lipRadius, np.asarray(blockR)/lipRadius,
                 np.asarray(blockMach))
                for blockX, blockR, blockMach in ((chamberX, chamberR, chamberMach),
                                                  (innerX, innerR, innerMach))]

    # One scale and one set of limits for every frame, so the animation shows the plume changing
    # rather than the axes changing under it. The scale is set from the supersonic field alone,
    # for the reason buildPlumeSweep.py gives: letting the chamber in squeezes the plume into the
    # top of the colour range.
    supersonic = [block[2] for block in upstream[1:]]
    machLow = min([float(frame['mach'].min()) for frame in frames]
                  + [float(values.min()) for values in supersonic])
    machHigh = max([float(frame['mach'].max()) for frame in frames]
                   + [float(values.max()) for values in supersonic])
    levels = np.linspace(machLow, machHigh, 120)
    extent = max(float(np.abs(frame['boundaryR']).max())/lipRadius for frame in frames)
    extent = max(extent, float(wallR.max()))

    figure, (axes, curve) = plt.subplots(
        1, 2, figsize = (16.0, 5.0), gridspec_kw = {'width_ratios': [3.1, 1.0]})
    figure.subplots_adjust(left = 0.05, right = 0.945, top = 0.80, bottom = 0.16, wspace = 0.30)
    scalar = plt.cm.ScalarMappable(cmap = showcasePalette.machMap,
                                   norm = plt.Normalize(vmin = machLow, vmax = machHigh))
    bar = figure.colorbar(scalar, ax = axes, pad = 0.01, fraction = 0.030)
    bar.set_label('Mach number [-]', fontsize = 9)

    # Thrust is tens of kilonewtons and specific impulse is hundreds of seconds, so one axis puts
    # the thrust curve in the bottom quarter of the panel. The twin is built once: creating it
    # inside the frame callback would stack a new axes on the figure every frame.
    impulse = curve.twinx()

    def draw(index):
        frame = frames[index]
        axes.clear()
        axes.set_facecolor(panel)

        axial = (frame['x'] - lipX)/lipRadius
        radial = frame['r']/lipRadius
        axes.tricontourf(np.concatenate([axial, axial]),
                         np.concatenate([radial, -radial]),
                         np.concatenate([frame['mach'], frame['mach']]),
                         levels = levels, cmap = showcasePalette.machMap, extend = 'both')

        for blockX, blockR, blockMach in upstream:
            patch = axes.tricontourf(np.concatenate([blockX, blockX]),
                                     np.concatenate([blockR, -blockR]),
                                     np.concatenate([blockMach, blockMach]),
                                     levels = levels, cmap = showcasePalette.machMap, extend = 'both')
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

        # The performance panel is static except for the marker, so it is redrawn rather than
        # cleared and rebuilt, which keeps the axis limits identical across frames.
        curve.clear()
        impulse.clear()
        curve.set_facecolor(panel)
        powerAxis = 100.0*performance['fraction']
        curve.plot(powerAxis, performance['thrust']/1000.0, color = copper, lw = 1.8)
        curve.plot(100.0*frame['fraction'], performance['thrust'][index]/1000.0, 'o',
                   color = copper, ms = 6, zorder = 5)
        impulse.plot(powerAxis, performance['specificImpulse'], color = green, lw = 1.8)
        impulse.plot(100.0*frame['fraction'], performance['specificImpulse'][index], 'o',
                     color = green, ms = 6, zorder = 5)

        curve.axvline(100.0*separating, color = warn, lw = 1.0, ls = '--')
        curve.text(100.0*separating, 0.98*curve.get_ylim()[1], ' separates', color = warn,
                   fontsize = 8, va = 'top', ha = 'left')
        curve.set_xlabel('Power level [% of rated]')
        curve.set_ylabel('Thrust [kN]', color = copper)
        # clear() puts the twin's label back on the left, over the thrust label, so the side is
        # set per frame rather than once when the twin is built.
        impulse.yaxis.set_label_position('right')
        impulse.set_ylabel('Ideal Isp [s]', color = green)
        curve.tick_params(axis = 'y', colors = copper)
        impulse.tick_params(axis = 'y', colors = green)
        impulse.set_facecolor('none')
        curve.set_xlim(0.0, 105.0)
        curve.grid(True, alpha = 0.35)

        axes.set_title(
            f'NOVA nozzle plume at {100*frame["fraction"]:.0f} % power   '
            f'ambient {ambient/1000.0:.1f} kPa held   Pe/Pa {frame["ratio"]:.2f}\n'
            f'mass continuity error {frame["nearDrift"]:+.2f} % at {NEARREACH:.0f} lip radii, '
            f'{frame["drift"]:+.2f} % at {REACH:.0f}',
            fontsize = 10.5, color = green if frame['trustworthy'] else warn, pad = 10)

        return axes.collections

    animation = FuncAnimation(figure, draw, frames = len(frames), interval = FRAMEMS, blit = False)
    path = os.path.join(here, 'plumeThrottle.gif')
    animation.save(path, writer = PillowWriter(fps = max(1, round(1000.0/FRAMEMS))))
    plt.close(figure)

    print()
    print(f'  wrote plumeThrottle.gif, {len(frames)} frames, '
          f'{100*frames[0]["fraction"]:.0f} to {100*frames[-1]["fraction"]:.0f} per cent power')
    print(f'  ambient {ambient/1000.0:.2f} kPa, separation below {100*separating:.1f} % power')
    print(f'  thrust {performance["thrust"][0]/1000.0:.1f} to '
          f'{performance["thrust"][-1]/1000.0:.1f} kN, Isp '
          f'{performance["specificImpulse"][0]:.1f} to '
          f'{performance["specificImpulse"][-1]:.1f} s')

if __name__ == '__main__':
    build()
