'''
Figures for the plume march: the nozzle characteristics solution carried past the lip.

Each figure covers one thing the solver can be asked to do, and the last two cover where it stops
being able to. Reproduce with:

    python featureShowcase/runBaseCase.py       # writes showcaseBase.pkl
    python featureShowcase/buildPlumeMarch.py
'''
import os
import pickle
import sys
import time

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np

import showcasePalette
from matplotlib.patches import Polygon

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
from NOVA.Nozzle import (PlumeFlow, PlumePoint, plumeExitLine, solvePlumeMarch,          # noqa: E402
                    freeJetLeadingCharacteristic, PlumeGas, shockCellLength,
                    fullyExpandedDiameter, machFromPressureRatio, prandtlCellCoefficient)
from NOVA import figures as figureModule                                                       # noqa: E402

background = showcasePalette.background
panel      = showcasePalette.panel
copper     = showcasePalette.copper
green      = showcasePalette.green
ink        = showcasePalette.ink
muted      = showcasePalette.muted
warn       = showcasePalette.warn
blue       = showcasePalette.blue

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': showcasePalette.gridColor,
    'axes.grid': False, 'font.size': 9,
    'axes.titlesize': 12, 'axes.titleweight': 'bold', 'legend.framealpha': 0.0,
})

GAMMA = 1.4

def save(figure, name):
    path = os.path.join(here, name)
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print(f'  wrote {name}')
    return path

def prandtlPeriod(exitMach, ratio, lipRadius = 1.0):
    '''Prandtl's first cell length for this operating point, in the same units as the march.'''
    stagnationOverStatic = (1.0 + 0.5 * (GAMMA - 1.0) * exitMach ** 2) ** (GAMMA / (GAMMA - 1.0))
    jetMach = machFromPressureRatio(stagnationOverStatic * ratio, GAMMA)
    return shockCellLength(fullyExpandedDiameter(2.0 * lipRadius, exitMach, jetMach, GAMMA),
                           jetMach, prandtlCellCoefficient)

def boundaryCrests(xs, rs, minimumGap):
    '''Axial stations of the boundary crests, smoothed so numerical jitter is not counted.'''
    window = max(5, rs.size // 200)
    smoothed = np.convolve(rs, np.ones(window) / window, mode = 'same')
    found = []
    for index in range(window, smoothed.size - window - 1):
        if smoothed[index] >= smoothed[index - window:index].max() \
                and smoothed[index] > smoothed[index + 1:index + 1 + window].max():
            if not found or xs[index] - xs[found[-1]] > minimumGap:
                found.append(index)
    return found

def uniformExitLine(flow, exitMach, wallAngleDeg, lipRadius = 1.0, count = 140):
    '''A uniform exit at a prescribed divergence, for the cases that are not a real contour.'''
    angle = np.radians(wallAngleDeg)
    radii = np.linspace(lipRadius, 0.0, count)
    line = [PlumePoint(0.0, radius, exitMach, angle * radius / lipRadius, flow, 'exit')
            for radius in radii]
    line[-1] = PlumePoint(0.0, 0.0, exitMach, 0.0, flow, 'exit')
    return line

def clipToSolved(axes, field, boundaryX, boundaryR, lastLine):
    '''Hold the shading inside the solved region, which the boundary and last line enclose.'''
    lastX = np.array([point.x for point in lastLine])
    lastR = np.array([point.r for point in lastLine])
    outline = np.vstack([np.column_stack([boundaryX, boundaryR]),
                         np.column_stack([lastX[::-1], lastR[::-1]]),
                         np.column_stack([lastX, -lastR]),
                         np.column_stack([boundaryX[::-1], -boundaryR[::-1]])])
    clip = Polygon(outline, closed = True, transform = axes.transData,
                   facecolor = 'none', edgecolor = 'none')
    axes.add_patch(clip)
    field.set_clip_path(clip)

#--------------------------------------------------------------------------------------------------------------------------#

def drawContinuousField(nozzle):
    '''
    The nozzle interior and the plume as one field.

    This is what the march is for. The contour solve ends at the exit plane and the plume march
    starts from it, so the two halves are one solution rather than a solution and a picture.
    '''
    seed = nozzle.plumeCharacteristicSeed()
    structure = nozzle.plumeStructure(ambientPressure = 101325.0)
    exitPressure = structure.exitPressureRatio * 101325.0
    # The mesh's own gamma, not the exit gamma the correlations prefer: reading mesh Mach numbers
    # under a different ratio of specific heats makes the state discontinuous at the exit plane.
    flow = PlumeFlow(seed['gamma'], seed['gasConstant'], seed['stagnationTemperature'],
                     seed['stagnationPressure'])
    line = plumeExitLine(flow, seed, numPoints = 140)
    started = time.time()
    net = solvePlumeMarch(flow, line, exitPressure / 1.5, numRays = 40, maxLines = 2500,
                          lineLimit = 250)
    nodes = net['nodes']

    interior = figureModule.fieldFigure(nozzle, 'mach')
    xs, rs, values = [], [], []
    for xBlock, rBlock, valueBlock in zip(interior.xBlocks, interior.rBlocks,
                                          interior.valueBlocks):
        x = np.asarray(xBlock, dtype = float).ravel()
        r = np.asarray(rBlock, dtype = float).ravel()
        value = np.asarray(valueBlock, dtype = float).ravel()
        keep = np.isfinite(x) & np.isfinite(r) & np.isfinite(value) & (x <= seed['exitX'])
        xs.append(x[keep]); rs.append(r[keep]); values.append(value[keep])
    innerX = np.concatenate(xs) * 1e3
    innerR = np.concatenate(rs) * 1e3
    innerMach = np.concatenate(values)

    plumeX = np.array([point.x for point in nodes]) * 1e3
    plumeR = np.array([point.r for point in nodes]) * 1e3
    plumeMach = np.array([point.mach for point in nodes])
    boundaryX = np.array([point.x for point in net['boundary']]) * 1e3
    boundaryR = np.array([point.r for point in net['boundary']]) * 1e3
    wallX = np.asarray(nozzle.xNozzleWall) * 1e3
    wallR = np.asarray(nozzle.rNozzleWall) * 1e3

    figure, axes = plt.subplots(figsize = (14, 6.2))
    # Two fields on one scale rather than one field over both regions, because each is bounded by
    # something different: the interior by the wall that was built, the plume by the solved part
    # of the free boundary. Clipping them together would hide whichever outline came second.
    levels = np.linspace(min(innerMach.min(), plumeMach.min()),
                         max(innerMach.max(), plumeMach.max()), 120)
    interiorField = axes.tricontourf(np.concatenate([innerX, innerX]),
                                     np.concatenate([innerR, -innerR]),
                                     np.concatenate([innerMach, innerMach]),
                                     levels = levels, cmap = showcasePalette.machMap)
    wallOutline = np.vstack([np.column_stack([wallX, wallR]),
                             np.column_stack([wallX[::-1], -wallR[::-1]])])
    wallClip = Polygon(wallOutline, closed = True, transform = axes.transData,
                       facecolor = 'none', edgecolor = 'none')
    axes.add_patch(wallClip)
    interiorField.set_clip_path(wallClip)

    field = axes.tricontourf(np.concatenate([plumeX, plumeX]),
                             np.concatenate([plumeR, -plumeR]),
                             np.concatenate([plumeMach, plumeMach]),
                             levels = levels, cmap = showcasePalette.machMap)
    lastLine = net['lines'][-1]
    scaled = [PlumePoint(point.x * 1e3, point.r * 1e3, point.mach, point.flowAngle, flow)
              for point in lastLine]
    clipToSolved(axes, field, boundaryX, boundaryR, scaled)

    axes.plot(wallX, wallR, color = copper, lw = 2.2, label = 'nozzle wall')
    axes.plot(wallX, -wallR, color = copper, lw = 2.2)
    axes.plot(boundaryX, boundaryR, color = ink, lw = 1.5, label = 'jet boundary, solved')
    axes.plot(boundaryX, -boundaryR, color = ink, lw = 1.5)
    axes.axvline(seed['exitX'] * 1e3, color = green, lw = 1.2, ls = '--',
                 label = 'exit plane, where the boundary condition changes')

    drift = net['massDriftWorst']
    axes.set_title('One continuous characteristics solution: nozzle interior and plume    '
                   f'Pe/Pa 1.5    Mb {net["boundaryMach"]:.2f}    '
                   f'{len(net["lines"])} plume lines    mass drift {drift:+.1f} %')
    axes.set_xlabel('Axial station [mm]')
    axes.set_ylabel('Radius [mm]')
    axes.set_aspect('equal', adjustable = 'box')
    axes.legend(loc = 'upper left', fontsize = 8, labelcolor = ink)
    bar = figure.colorbar(field, ax = axes, orientation = 'vertical', pad = 0.02,
                          fraction = 0.030)
    bar.set_label('Mach number [-]')
    figure.text(0.012, -0.02,
                'Inside the nozzle the outer boundary is a wall and the contour sets the flow '
                'angle. Past the lip it is a free streamline at ambient pressure, the angle falls '
                'out of the solution,\nand nothing else changes. The interior, near-axis and axis '
                'points carry the same relations on both sides of the exit plane.',
                fontsize = 8.5, color = muted, va = 'top')
    figure.text(0.012, -0.09,
                f'DO NOT TRUST THIS FIELD. Every characteristic line spans the jet and so must '
                f'carry the same mass flow; these differ by {drift:+.1f} per cent, against 0.03 at '
                f'a parallel exit.\nThe shape is what the march currently produces on a contoured '
                f'nozzle, shown for that reason and not as a result. The case that conserves is '
                f'plumeCellTrain.png.',
                fontsize = 8.5, color = warn, va = 'top')
    print(f'  continuous field: {len(nodes)} plume nodes, mass drift {drift:+.1f} %, '
          f'in {time.time() - started:.0f}s')
    return save(figure, 'plumeContinuousField.png')

def drawCellTrain():
    '''
    The validated case: a near on design jet from a parallel exit, carried over many cells.

    Prandtl's cell length is a linearised result for an almost perfectly expanded jet, so this is
    the one operating point where the solver and the correlation are comparable.
    '''
    flow = PlumeFlow(GAMMA, 287.0, 300.0, 1.0e6)
    exitMach, ratio = 3.0, 1.05
    started = time.time()
    net = solvePlumeMarch(flow, uniformExitLine(flow, exitMach, 0.0),
                          flow.staticPressure(exitMach) / ratio,
                          numRays = 40, maxLines = 8000, lineLimit = 250)
    nodes = net['nodes']
    boundaryX = np.array([point.x for point in net['boundary']])
    boundaryR = np.array([point.r for point in net['boundary']])
    expected = prandtlPeriod(exitMach, ratio)
    crests = boundaryCrests(boundaryX, boundaryR, 0.4 * expected)
    period = float(np.diff(boundaryX[crests]).mean())
    error = 100.0 * (period - expected) / expected

    figure, axes = plt.subplots(2, 1, figsize = (14, 7.0), height_ratios = [2.0, 1.0],
                                sharex = True)
    x = np.array([point.x for point in nodes])
    r = np.array([point.r for point in nodes])
    mach = np.array([point.mach for point in nodes])
    keep = x <= boundaryX[-1]
    field = axes[0].tricontourf(np.concatenate([x[keep], x[keep]]),
                                np.concatenate([r[keep], -r[keep]]),
                                np.concatenate([mach[keep], mach[keep]]),
                                levels = 120, cmap = showcasePalette.machMap)
    clipToSolved(axes[0], field, boundaryX, boundaryR, net['lines'][-1])
    axes[0].plot(boundaryX, boundaryR, color = ink, lw = 1.0)
    axes[0].plot(boundaryX, -boundaryR, color = ink, lw = 1.0)
    axes[0].plot([-1.5, 0.0], [1.0, 1.0], color = copper, lw = 3.0, label = 'nozzle lip')
    axes[0].plot([-1.5, 0.0], [-1.0, -1.0], color = copper, lw = 3.0)
    for index, crest in enumerate(crests):
        axes[0].axvline(boundaryX[crest], color = green, lw = 0.7, ls = ':',
                        label = 'solved crest' if index == 0 else None)
    axes[0].set_ylabel('Radius  r / r_j')
    axes[0].set_title(f'Shock cell train, parallel exit    Mj {exitMach}    Pe/Pa {ratio}    '
                      f'{len(crests)} cells resolved    '
                      f'period {period:.3f} against Prandtl {expected:.3f} r_j '
                      f'({error:+.1f} %)    mass drift {net["massDriftWorst"]:+.3f} %')
    axes[0].legend(loc = 'upper right', fontsize = 8, labelcolor = ink)
    bar = figure.colorbar(field, ax = axes[0], orientation = 'vertical', pad = 0.01,
                          fraction = 0.020)
    bar.set_label('Mach number [-]')

    axes[1].plot(boundaryX, boundaryR, color = green, lw = 1.4, label = 'jet boundary radius')
    for crest in crests:
        axes[1].axvline(boundaryX[crest], color = muted, lw = 0.6, ls = ':')
    axes[1].axhline(1.0, color = copper, lw = 0.8, ls = '--', label = 'lip radius')
    axes[1].set_xlabel('Axial distance from the lip  x / r_j')
    axes[1].set_ylabel('r / r_j')
    axes[1].grid(True, alpha = 0.25)
    axes[1].legend(loc = 'upper right', fontsize = 8, labelcolor = ink)
    figure.subplots_adjust(hspace = 0.08)
    figure.text(0.012, 0.02,
                'The primary wavelength is the period between successive crests, not twice the '
                f'distance to the first one. Those differ: the first crest sits at '
                f'{boundaryX[crests[0]]:.2f} r_j,\nso the naive measure gives '
                f'{2 * boundaryX[crests[0]]:.2f} against a true period of {period:.2f}, an '
                'overstatement of about ten per cent.',
                fontsize = 8.5, color = muted, va = 'top')
    print(f'  cell train: {len(crests)} crests, period {period:.3f} vs {expected:.3f} '
          f'({error:+.1f} %) in {time.time() - started:.0f}s')
    return save(figure, 'plumeCellTrain.png')

def drawExitHandover(nozzle):
    '''
    What the march starts from, and what it would have started from without the contour solve.

    Appendix A of TN D-2327 builds its leading characteristic from a source flow at the wall
    angle. A contoured nozzle is built to straighten the flow instead, so the two are nowhere
    near each other and every line of the march inherits the difference.
    '''
    seed = nozzle.plumeCharacteristicSeed()
    structure = nozzle.plumeStructure(ambientPressure = 101325.0)
    # The mesh's own gamma, not the exit gamma the correlations prefer: reading mesh Mach numbers
    # under a different ratio of specific heats makes the state discontinuous at the exit plane.
    flow = PlumeFlow(seed['gamma'], seed['gasConstant'], seed['stagnationTemperature'],
                     seed['stagnationPressure'])
    line = plumeExitLine(flow, seed, numPoints = 140)
    gas = PlumeGas(seed['gamma'])
    sourceFlow = freeJetLeadingCharacteristic(gas, structure.exitMach, structure.lipWallAngle,
                                              1.0, numPoints = 1200)

    figure, axes = plt.subplots(1, 2, figsize = (13, 4.8))
    meshRadius = np.array([point.r for point in line]) / structure.lipRadius
    meshMach = np.array([point.mach for point in line])
    meshAngle = np.degrees([point.flowAngle for point in line])
    sourceRadius = np.array([abs(point.y) for point in sourceFlow])
    sourceMach = np.array([point.mach for point in sourceFlow])

    axes[0].plot(meshMach, meshRadius, color = green, lw = 2.0,
                 label = 'exit plane of the contour solve')
    axes[0].plot(sourceMach, sourceRadius, color = warn, lw = 2.0, ls = '--',
                 label = 'source flow assumed by Appendix A')
    axes[0].set_xlabel('Mach number [-]')
    axes[0].set_ylabel('Radius  r / r_lip')
    axes[0].set_title('Initial data the march starts from')
    axes[0].grid(True, alpha = 0.25)
    axes[0].legend(loc = 'lower left', fontsize = 8, labelcolor = ink)
    axes[0].annotate(f'{sourceMach[-1]:.2f} on the axis',
                     xy = (sourceMach[-1], 0.0), xytext = (sourceMach[-1] - 2.6, 0.16),
                     color = warn, fontsize = 8,
                     arrowprops = dict(arrowstyle = '->', color = warn, lw = 1.0))
    axes[0].annotate(f'{meshMach[-1]:.2f} on the axis',
                     xy = (meshMach[-1], 0.0), xytext = (meshMach[-1] - 2.2, 0.36),
                     color = green, fontsize = 8,
                     arrowprops = dict(arrowstyle = '->', color = green, lw = 1.0))

    axes[1].plot(meshAngle, meshRadius, color = green, lw = 2.0)
    axes[1].axvline(np.degrees(structure.lipWallAngle), color = warn, lw = 2.0, ls = '--',
                    label = 'the single wall angle a scalar handover would pass')
    axes[1].set_xlabel('Flow angle [deg]')
    axes[1].set_ylabel('Radius  r / r_lip')
    axes[1].set_title('The exit plane is not uniform')
    axes[1].grid(True, alpha = 0.25)
    axes[1].legend(loc = 'lower right', fontsize = 8, labelcolor = ink)

    figure.suptitle('The handover at the exit plane', fontsize = 12, fontweight = 'bold')
    figure.text(0.012, -0.03,
                f'The contour leaves the exit at {meshAngle[-1]:.1f} degrees and Mach '
                f'{meshMach[-1]:.2f} on the axis and {meshAngle[0]:.1f} degrees and Mach '
                f'{meshMach[0]:.2f} at the wall. Assuming a source flow at the wall angle instead '
                f'puts\nMach {sourceMach[-1]:.2f} on the axis, {100 * (sourceMach[-1] / meshMach[-1] - 1):.0f} '
                'per cent high, and every line of the march inherits that.',
                fontsize = 8.5, color = muted, va = 'top')
    print(f'  handover: mesh axis M {meshMach[-1]:.3f}, source flow M {sourceMach[-1]:.3f}')
    return save(figure, 'plumeExitHandover.png')

def drawOperatingRange():
    '''
    The range the march now covers, from overexpanded through to underexpanded.

    Overexpanded jets used to be refused outright, which excluded sea-level operation of any
    vacuum-optimized nozzle. The lip turns inward there through what is really an oblique shock,
    taken here as an isentropic compression, and the size of that approximation is drawn beside
    the plumes rather than described.
    '''
    from NOVA.Nozzle import obliqueShockState, plumeMachDisk, prandtlMeyerAngle
    flow = PlumeFlow(GAMMA, 287.0, 300.0, 1.0e6)
    exitMach = 3.0
    exitPressure = flow.staticPressure(exitMach)
    cases = [(0.5, 'overexpanded'), (0.8, 'overexpanded'),
             (1.3, 'underexpanded'), (2.0, 'underexpanded')]

    figure, axes = plt.subplots(len(cases) + 1, 1, figsize = (12.5, 10.5),
                                height_ratios = [1.0] * len(cases) + [1.25])
    started = time.time()
    for index, (ratio, kind) in enumerate(cases):
        net = solvePlumeMarch(flow, uniformExitLine(flow, exitMach, 0.0),
                              exitPressure / ratio, numRays = 40, maxLines = 1500,
                              lineLimit = 250)
        panel = axes[index]
        nodes = net['nodes']
        x = np.array([point.x for point in nodes])
        r = np.array([point.r for point in nodes])
        mach = np.array([point.mach for point in nodes])
        boundaryX = np.array([point.x for point in net['boundary']])
        boundaryR = np.array([point.r for point in net['boundary']])
        field = panel.tricontourf(np.concatenate([x, x]), np.concatenate([r, -r]),
                                  np.concatenate([mach, mach]), levels = 90, cmap = showcasePalette.machMap)
        clipToSolved(panel, field, boundaryX, boundaryR, net['lines'][-1])
        panel.plot(boundaryX, boundaryR, color = ink, lw = 1.0)
        panel.plot(boundaryX, -boundaryR, color = ink, lw = 1.0)
        panel.plot([-0.8, 0.0], [1.0, 1.0], color = copper, lw = 2.5)
        panel.plot([-0.8, 0.0], [-1.0, -1.0], color = copper, lw = 2.5)

        disk = plumeMachDisk(flow, net)
        stagnation = net.get('lipStagnationRatio', 1.0)
        turn = np.degrees(net.get('lipShockDeflection', 0.0))
        detail = (f'lip shock {turn:.2f} deg, stagnation kept {100 * stagnation:.2f} %'
                  if kind == 'overexpanded' else 'lip expansion fan')
        panel.set_title(f'Pe/Pa {ratio}   {kind}   Mb {net["boundaryMach"]:.3f}   {detail}   '
                        f'mass drift {net["massDriftWorst"]:+.3f} %   '
                        f'Mach disk: {"yes" if disk["present"] else "none"}',
                        fontsize = 10)
        panel.set_ylabel('r / r_j')
        panel.set_xlim(-0.8, max(12.0, boundaryX[-1]))
        panel.set_ylim(-1.9, 1.9)
        if index < len(cases) - 1:
            panel.set_xticklabels([])
    axes[len(cases) - 1].set_xlabel('Axial distance from the lip  x / r_j')

    # How good the isentropic lip is, against the shock it stands in for.
    ratios = np.linspace(0.4, 0.99, 40)
    turnError, stagnationLoss = [], []
    for ratio in ratios:
        deflection, _, stagnation = obliqueShockState(exitMach, GAMMA, 1.0 / ratio)
        compressed = machFromPressureRatio(
            (1.0 + 0.5 * (GAMMA - 1.0) * exitMach ** 2) ** (GAMMA / (GAMMA - 1.0)) * ratio, GAMMA)
        isentropic = (prandtlMeyerAngle(exitMach, GAMMA)
                      - prandtlMeyerAngle(compressed, GAMMA)) if compressed > 1.0 else np.nan
        turnError.append(100.0 * (isentropic - deflection) / deflection
                         if deflection > 0 else np.nan)
        stagnationLoss.append(100.0 * (1.0 - stagnation))

    lower = axes[-1]
    lower.plot(ratios, turnError, color = green, lw = 2.0,
               label = 'turning angle error of the isentropic lip')
    lower.plot(ratios, stagnationLoss, color = warn, lw = 2.0,
               label = 'stagnation pressure the shock would cost')
    lower.axvline(0.4, color = muted, lw = 1.2, ls = '--',
                  label = 'Summerfield separation, below which no attached plume exists')
    lower.set_xlabel('Pe / Pa')
    lower.set_ylabel('per cent')
    lower.set_title('How much the isentropic lip costs, against the oblique shock it replaces',
                    fontsize = 10)
    lower.grid(True, alpha = 0.25)
    lower.legend(loc = 'upper right', fontsize = 8, labelcolor = ink)

    figure.subplots_adjust(hspace = 0.55)
    figure.text(0.012, 0.045,
                'Overexpanded jets were refused outright until now, which excluded sea-level '
                'operation of any vacuum-optimized nozzle. They are solved here, but not far: an '
                'inward-turning lip\ncarries only a fraction of a cell before the march stalls, and '
                'too few lines span the jet for it to report its own conservation, which is what '
                'the missing drift figures mean.\nNo Mach disk is found in any of these, and that '
                'is correct rather than a miss: a disk is a shock, this net carries none, and one '
                'appears only above a nozzle pressure ratio near 3.5.',
                fontsize = 8.5, color = warn, va = 'top')
    print(f'  operating range in {time.time() - started:.0f}s')
    return save(figure, 'plumeOperatingRange.png')

def drawOperatingEnvelope():
    '''
    Where the march runs and where it stops, over exit divergence and pressure ratio.

    An honest map matters more than a flattering one: the solver carries a parallel exit for tens
    of cells and stops a divergent one after about one, and that is the shape of what it can
    currently be asked for.
    '''
    flow = PlumeFlow(GAMMA, 287.0, 300.0, 1.0e6)
    angles = [0.0, 2.0, 5.0, 8.0, 11.0, 14.0]
    ratios = [1.05, 1.2, 1.5, 2.0]
    reach = np.full((len(ratios), len(angles)), np.nan)
    budgeted = np.zeros_like(reach, dtype = bool)
    started = time.time()
    for row, ratio in enumerate(ratios):
        for column, angle in enumerate(angles):
            net = solvePlumeMarch(flow, uniformExitLine(flow, 3.0, angle),
                                  flow.staticPressure(3.0) / ratio,
                                  numRays = 30, maxLines = 2500, lineLimit = 200)
            boundary = net['boundary']
            if len(boundary) > 3:
                reach[row, column] = boundary[-1].x / prandtlPeriod(3.0, ratio)
            # A case that ran out of line budget has not found a limit, only the ceiling set here.
            budgeted[row, column] = net['stop'] == 'maxLines'

    figure, axes = plt.subplots(figsize = (9.5, 4.6))
    mesh = axes.imshow(reach, origin = 'lower', aspect = 'auto', cmap = showcasePalette.temperatureMap,
                       extent = [-0.5, len(angles) - 0.5, -0.5, len(ratios) - 0.5])
    axes.set_xticks(range(len(angles)))
    axes.set_xticklabels([f'{a:.0f}' for a in angles])
    axes.set_yticks(range(len(ratios)))
    axes.set_yticklabels([f'{r:.2f}' for r in ratios])
    bright = np.nanmax(reach) if np.isfinite(reach).any() else 1.0
    for row in range(len(ratios)):
        for column in range(len(angles)):
            value = reach[row, column]
            if not np.isfinite(value):
                label, dark = '-', False
            else:
                label = f'{value:.1f}' + ('+' if budgeted[row, column] else '')
                dark = value > 0.55 * bright
            axes.text(column, row, label, ha = 'center', va = 'center', fontsize = 9,
                      color = showcasePalette.background if dark else ink, fontweight = 'bold')
    axes.set_xlabel('Exit wall angle [deg]')
    axes.set_ylabel('Pe / Pa')
    axes.set_title('How far the march carries, in shock cell lengths')
    bar = figure.colorbar(mesh, ax = axes, pad = 0.02, fraction = 0.04)
    bar.set_label('cells reached')
    figure.text(0.012, -0.06,
                'A plus sign marks a case that reached the line budget rather than a limit, so it '
                'was still running when it was stopped. Near on design and near parallel the march '
                'carries as far as it is\nasked to, and that is where it is validated against '
                'Prandtl. Any real exit divergence stops it after about one cell: the line stops '
                'reaching the boundary and the boundary point\nlands on the one before it. A bell '
                'contour leaves the lip at eight to fifteen degrees, so it sits in the part of '
                'this map that does not yet run far.',
                fontsize = 8.5, color = warn, va = 'top')
    print(f'  envelope map in {time.time() - started:.0f}s')
    return save(figure, 'plumeOperatingEnvelope.png')

def main():
    with open(os.path.join(here, 'showcaseBase.pkl'), 'rb') as handle:
        nozzle = pickle.load(handle)
    print('Rendering plume march figures')
    drawExitHandover(nozzle)
    drawContinuousField(nozzle)
    drawCellTrain()
    drawOperatingRange()
    drawOperatingEnvelope()

if __name__ == '__main__':
    main()
