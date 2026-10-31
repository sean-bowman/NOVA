# -- NOVA Plume: OpenFOAM Against NOVA -- #

'''

Compare a converged OpenFOAM solution of the NOVA plume with NOVA's station march and its
correlated plume structure, judge it against the acceptance criteria, and draw the comparison.

The case and the march solve the same initial-value problem: the Euler equations for a calorically
perfect gas at NOVA's chamber ratio of specific heats, from NOVA's exit station, into a still
ambient at the shipped pressure. The march is isentropic and carries no shock; the case captures
them. The correlations are fits to measured jets and solve nothing. Neither NOVA output nor the
case is a validated reference, so every comparison here is a cross-check.

What is compared:

    - Against the march, over the reach it was solved to: the jet boundary radius at every
      station, its mean angle over the first half station radius, and the Mach number, pressure
      and flow angle at every node inside nine tenths of the boundary radius. The march run to a
      longer reach is set against the case to show where it parts from it.
    - Against the correlations: where the first shock meets the axis, a Mach disk or a regular
      reflection, its distance from the exit plane and the disk's diameter, the first shock cell's
      length and the boundary's widest radius. Each correlation is evaluated at
      the case's gas, the chamber gas the march and NOVA's correlations both solve in.
    - Steadiness: the mass through every open boundary over the averaging window.

The jet boundary is the contact surface between the jet and the ambient. Total temperature is
conserved along streamlines of an inviscid adiabatic flow, so it is the jet's chamber value inside
the boundary and the ambient's static temperature outside it. The case smears the contact over a
few cells; the boundary is taken where total temperature is halfway between the two, and the
radii where it is a tenth and nine tenths of the way give the smeared layer's width.

Every comparison reads the fields averaged over the second half of the run.

Run from the case folder after `reconstructPar -latestTime`; Allrun does this:

    python3 scripts/comparePlume.py <case>

Writes `<case>/comparison/comparison.json` and the figures beside it. Needs NumPy and Matplotlib.

Author: Sean Bowman

'''

import glob
import json
import math
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import tri
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from mpl_toolkits.axes_grid1 import make_axes_locatable

from compareWithNova import applyStyle, machNumber, readHistory, readInternalField, statistics, timeDirectories

# Acceptance criteria. Relative differences of NOVA against OpenFOAM unless the unit says otherwise.
criteria = {
    'boundaryRadiusMax':  0.020,    # worst march station
    'fieldMach95':        0.020,    # 95th percentile over nodes inside 0.9 of the boundary radius
    'lipBoundaryAngle':   1.0,      # [deg], mean angle over the first half station radius
    'axisShockLocation':  0.10,     # where the first shock meets the axis, from the exit plane
    'machDiskDiameter':   0.25,     # against Smith and Richards' fit; zero against zero passes
    'shockCellLength':    0.10,     # exit plane to the first neck of the boundary, against Prandtl
    'massImbalance':      0.002,    # inflow against outflow, window means
    'meanDrift':          0.001,    # outlet mass flow, second half of the window against the first
}
absoluteCriteria = ('lipBoundaryAngle',)

# The boundary's angle at the lip is fitted over this many station radii
lipFitLength = 0.5

#--------------------------------------------------------------------------------------------------------------------------#
# -- Reading the case -- #
#--------------------------------------------------------------------------------------------------------------------------#

def readAxis(path: str) -> dict:

    '''Every column of an axis sample, named from the file name, vectors as (n, 3).'''

    values = np.loadtxt(path)
    columns, start = {'x': values[:, 0]}, 3
    for name in os.path.basename(path)[len('axis_'):-len('.xy')].split('_'):
        width = 3 if name.startswith('U') else 1
        columns[name] = values[:, start:start + width] if width == 3 else values[:, start]
        start += width

    return columns

#--------------------------------------------------------------------------------------------------------------------------#
# -- Measurements -- #
#--------------------------------------------------------------------------------------------------------------------------#

def columns(cellX: np.ndarray, tolerance: float = 1e-6) -> list:

    '''

    The cells of each axial column of the structured mesh, ordered outward, the columns downstream.

    A column ends where the sorted cell centers jump by more than `tolerance` [m]. Rounding the
    centers to the tolerance instead splits a column whose centers straddle a rounding boundary.

    '''

    order = np.argsort(cellX, kind = 'stable')
    breaks = np.flatnonzero(np.diff(cellX[order]) > tolerance) + 1

    # blockMesh numbers a column's cells outward, so the cell index restores that order
    return [np.sort(members) for members in np.split(order, breaks)]

def jetBoundary(cellX: np.ndarray, cellR: np.ndarray, fraction: np.ndarray, levels: tuple = (0.1, 0.5, 0.9)) -> dict:

    '''

    Radius of the outermost crossing of each level of the jet fraction, column by column.

    Returns:
    --------
    dict : 'x' [m], and one radius array [m] per level

    '''

    found = {'x': []}
    found.update({level: [] for level in levels})
    for members in columns(cellX):
        members = members[np.argsort(cellR[members])]
        radius, value = cellR[members], fraction[members]
        found['x'].append(float(cellX[members[0]]))
        for level in levels:
            inside = np.flatnonzero(value >= level)
            if inside.size == 0:
                found[level].append(0.0)
                continue
            k = inside[-1]
            if k == len(radius) - 1:
                found[level].append(float(radius[k]))
                continue
            weight = (level - value[k]) / (value[k + 1] - value[k])
            found[level].append(float(radius[k] + weight * (radius[k + 1] - radius[k])))

    return {key: np.asarray(value) for key, value in found.items()}

def machDisk(axisX: np.ndarray, axisMach: np.ndarray) -> dict:

    '''

    The first normal shock on the axis: the steepest fall in Mach number ahead of the first subsonic
    stretch. With no subsonic stretch, the reflection off the axis is regular and the steepest fall
    ahead of the first minimum is reported instead.

    '''

    subsonic = np.flatnonzero(axisMach < 1.0)
    present = subsonic.size > 0
    if present:
        end = subsonic[0]
    else:
        peak = int(np.argmax(axisMach))
        end = peak + int(np.argmin(axisMach[peak:]))
    peak = int(np.argmax(axisMach[:end + 1]))
    gradient = np.gradient(axisMach, axisX)
    shock = peak + int(np.argmin(gradient[peak:end + 1]))

    return {'present': bool(present), 'x': float(axisX[shock]), 'peakMach': float(axisMach[peak]),
            'peakX': float(axisX[peak]), 'downstreamMach': float(axisMach[end])}

def diskRadius(cellX: np.ndarray, cellR: np.ndarray, cellMach: np.ndarray, diskX: float, unit: float) -> float:

    '''

    Radius of the subsonic region behind the Mach disk, in the column a tenth of a station radius
    downstream of it: where the Mach number, walking out from the axis, first rises through one.

    '''

    groups = columns(cellX)
    centers = np.array([cellX[members[0]] for members in groups])
    members = groups[int(np.argmin(np.abs(centers - (diskX + 0.1 * unit))))]
    members = members[np.argsort(cellR[members])]
    radius, mach = cellR[members], cellMach[members]
    supersonic = np.flatnonzero(mach >= 1.0)
    if mach[0] >= 1.0 or supersonic.size == 0:
        return float('nan')
    k = supersonic[0]

    return float(radius[k - 1] + (1.0 - mach[k - 1]) / (mach[k] - mach[k - 1]) * (radius[k] - radius[k - 1]))

def firstCell(x: np.ndarray, radius: np.ndarray, unit: float) -> dict:

    '''

    The boundary's first maximum and the neck after it, found on the boundary smoothed over half a
    station radius and placed on the unsmoothed one.

    '''

    # Resampled evenly first, so the smoothing spans the same length where the cells grow
    spacing = float(np.min(np.diff(x)))
    even = np.arange(x[0], x[-1], spacing)
    width = max(1, int(round(0.25 * unit / spacing)))
    kernel = np.ones(2 * width + 1) / (2 * width + 1)
    smooth = np.convolve(np.pad(np.interp(even, x, radius), width, mode = 'edge'), kernel, mode = 'valid')
    slope = np.diff(smooth)

    falling = np.flatnonzero((slope[:-1] > 0.0) & (slope[1:] <= 0.0))
    if falling.size == 0:
        return {'maxX': float('nan'), 'maxRadius': float('nan'), 'neckX': float('nan'), 'neckRadius': float('nan')}
    top = falling[0] + 1
    rising = np.flatnonzero((slope[top:-1] < 0.0) & (slope[top + 1:] >= 0.0))

    def refine(index: int, pick) -> int:
        window = np.flatnonzero(np.abs(x - even[index]) <= 0.5 * unit)
        return int(window[pick(radius[window])])

    peak = refine(top, np.argmax)
    result = {'maxX': float(x[peak]), 'maxRadius': float(radius[peak]), 'neckX': float('nan'), 'neckRadius': float('nan')}
    if rising.size:
        neck = refine(top + rising[0] + 1, np.argmin)
        result.update(neckX = float(x[neck]), neckRadius = float(radius[neck]))

    return result

def lipAngle(x: np.ndarray, radius: np.ndarray, startX: float, unit: float) -> float:

    '''The boundary's mean angle over the first `lipFitLength` station radii [deg].'''

    near = (x > startX) & (x <= startX + lipFitLength * unit)

    return float(np.degrees(np.arctan(np.polyfit(x[near], radius[near], 1)[0])))

#--------------------------------------------------------------------------------------------------------------------------#
# -- Figures -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawField(path: str, points: dict, march: dict, boundary: dict, lines: dict, style: dict, unit: float,
              startX: float, view: tuple, markers: dict = None) -> None:

    '''

    Mach number on one scale, in station radii, OpenFOAM above the axis. Below it, the march's own
    field when `march` is given, and otherwise OpenFOAM's again with NOVA's boundaries drawn over it.

    '''

    named = style['colors']
    machMap = LinearSegmentedColormap.from_list('novaMach', style['colormaps']['mach'])
    length, height = view
    shown = (points['x'] <= startX + 1.05 * length * unit) & (points['r'] <= 1.05 * height * unit)
    x, r, mach = (points['x'][shown] - startX) / unit, points['r'][shown] / unit, points['mach'][shown]
    top = max(np.percentile(mach, 99.9), np.max(march['mach']) if march else 0.0)
    levels = np.linspace(0.0, math.ceil(top * 2.0) / 2.0, 41)
    mach = np.clip(mach, 0.0, levels[-1])

    figure, axes = plt.subplots(figsize = (9.0, min(9.0, 9.0 * 2.0 * height / length + (1.0 if march else 1.8))))
    filled = axes.tricontourf(tri.Triangulation(x, r), mach, levels = levels, cmap = machMap)
    if march:
        marchX, marchR = (march['x'] - startX) / unit, march['r'] / unit
        axes.tricontourf(tri.Triangulation(marchX.ravel(), -marchR.ravel()), march['mach'].ravel(), levels = levels,
                         cmap = machMap)
    else:
        axes.tricontourf(tri.Triangulation(x, -r), mach, levels = levels, cmap = machMap)
    axes.plot((boundary['x'] - startX) / unit, boundary[0.5] / unit, color = named['yellow'], linewidth = 1.0,
              label = 'OpenFOAM boundary')
    for lineX, lineR, kind, color, label in lines.values():
        axes.plot((lineX - startX) / unit, -lineR / unit, kind, color = named[color], linewidth = 1.2, label = label)
    for (markerX, markerR), (kind, color, label) in (markers or {}).items():
        axes.plot([(markerX - startX) / unit], [markerR / unit], kind, color = named[color], label = label)
    axes.axhline(0.0, color = named['textMuted'], linewidth = 0.6)
    axes.text(0.01, 0.97, 'OpenFOAM, rhoCentralFoam', transform = axes.transAxes, va = 'top')
    axes.text(0.01, 0.03, 'NOVA, station march' if march else 'OpenFOAM, with NOVA\'s boundaries',
              transform = axes.transAxes, va = 'bottom')
    axes.set_xlim(0.0, length); axes.set_ylim(-height, height)
    axes.set_aspect('equal'); axes.grid(False)
    axes.set_xlabel('distance from the exit plane / station radius'); axes.set_ylabel('r / station radius')
    if march:
        axes.legend(loc = 'upper right', fontsize = 7)
    else:
        axes.legend(loc = 'upper center', bbox_to_anchor = (0.5, -0.22), ncol = 3, fontsize = 7)
    # A divided axis keeps the colorbar the height of the equal-aspect plot
    colorAxes = make_axes_locatable(axes).append_axes('right', size = 0.15, pad = 0.15)
    colorAxes.grid(False)
    figure.colorbar(filled, cax = colorAxes, label = 'Mach number', ticks = levels[::8])
    figure.savefig(path, bbox_inches = 'tight', pad_inches = 0.15); plt.close(figure)

def drawFieldError(path: str, nodes: dict, error: np.ndarray, style: dict, unit: float, startX: float) -> None:

    errorMap = LinearSegmentedColormap.from_list('novaError', style['colormaps']['pressure'])
    limit = max(float(np.percentile(np.abs(error), 99)), 1e-4) * 100.0

    figure, axes = plt.subplots(figsize = (8.0, 4.8))
    points = axes.scatter((nodes['x'] - startX) / unit, nodes['r'] / unit, c = error * 100.0, s = 2, cmap = errorMap,
                          norm = TwoSlopeNorm(0.0, -limit, limit), linewidths = 0)
    axes.set_aspect('equal'); axes.grid(False)
    axes.set_xlabel('distance from the exit plane / station radius'); axes.set_ylabel('r / station radius')
    figure.colorbar(points, ax = axes, label = 'Mach number, NOVA march against OpenFOAM [%]', shrink = 0.9)
    figure.tight_layout(); figure.savefig(path); plt.close(figure)

def drawBoundary(path: str, boundary: dict, reference: dict, cell: dict, unit: float, startX: float,
                 length: float) -> None:

    '''The jet boundary: OpenFOAM's contact layer, both marches and the correlated shape.'''

    march, extended = reference['march'], reference['extendedMarch']
    structure = reference['structure']['reported']
    figure, (upper, lower) = plt.subplots(2, 1, figsize = (9.0, 6.4), sharex = True, height_ratios = (3, 1.3))
    x = (boundary['x'] - startX) / unit
    upper.fill_between(x, boundary[0.9] / unit, boundary[0.1] / unit, color = 'C0', alpha = 0.25, linewidth = 0,
                       label = 'OpenFOAM contact layer, 10 to 90 %')
    upper.plot(x, boundary[0.5] / unit, color = 'C0', label = 'OpenFOAM boundary, 50 %')
    upper.plot((np.asarray(extended['boundaryX']) - startX) / unit, np.asarray(extended['boundaryR']) / unit, '--',
               color = 'C1', label = f'NOVA march to {extended["reach"]:.0f} station radii')
    upper.plot((np.asarray(march['boundaryX']) - startX) / unit, np.asarray(march['boundaryR']) / unit,
               color = 'C1', linewidth = 2.2, label = f'NOVA march, shipped reach of {march["reach"]:.0f}')
    upper.plot((np.asarray(structure['boundaryX']) - startX) / unit, np.asarray(structure['boundaryR']) / unit, ':',
               color = 'C2', label = 'NOVA correlated boundary')
    if math.isfinite(cell['neckX']):
        upper.plot([(cell['neckX'] - startX) / unit], [cell['neckRadius'] / unit], 'v', color = 'C0',
                   label = 'OpenFOAM first neck')
    upper.set_ylabel('boundary radius / station radius'); upper.legend(fontsize = 7, loc = 'lower right')
    upper.set_xlim(0.0, length)

    marchX, marchR = np.asarray(march['boundaryX']), np.asarray(march['boundaryR'])
    lower.plot((marchX - startX) / unit, (marchR / np.interp(marchX, boundary['x'], boundary[0.5]) - 1.0) * 100.0,
               color = 'C1', linewidth = 2.2)
    extendedX, extendedR = np.asarray(extended['boundaryX']), np.asarray(extended['boundaryR'])
    lower.plot((extendedX - startX) / unit, (extendedR / np.interp(extendedX, boundary['x'], boundary[0.5]) - 1.0) * 100.0,
               '--', color = 'C1')
    lower.axhline(0.0, linewidth = 0.6)
    lower.set_ylim(-20.0, 20.0)
    lower.set_xlabel('distance from the exit plane / station radius'); lower.set_ylabel('march against\nOpenFOAM [%]')
    figure.tight_layout(); figure.savefig(path); plt.close(figure)

def drawAxis(path: str, axis: dict, reference: dict, disk: dict, unit: float, startX: float, length: float) -> None:

    '''Mach number and pressure on the axis, with the Mach disk OpenFOAM captures and the correlation's.'''

    march, extended, gas = reference['march'], reference['extendedMarch'], reference['gas']
    chamberGas = reference['structure']['chamberGas']
    correlated = chamberGas['axisShockX']
    correlatedLabel = ('Lewis and Carlson Mach disk' if chamberGas['machDiskPresent']
                       else 'Smith and Richards regular reflection')
    figure, (upper, lower) = plt.subplots(2, 1, figsize = (9.0, 6.0), sharex = True)
    x = (axis['x'] - startX) / unit
    upper.plot(x, axis['mach'], label = 'OpenFOAM')
    lower.semilogy(x, axis['p'] / gas['ambientPressure'], label = 'OpenFOAM')
    for data, kind, label in ((extended, '--', f'NOVA march to {extended["reach"]:.0f}'),
                              (march, '-', 'NOVA march, shipped reach')):
        stationX = (np.asarray(data['stationX']) - startX) / unit
        width = 2.2 if kind == '-' else 1.0
        upper.plot(stationX, data['axisMach'], kind, color = 'C1', linewidth = width, label = label)
        lower.semilogy(stationX, np.asarray(data['axisPressure']) / gas['ambientPressure'], kind, color = 'C1',
                       linewidth = width, label = label)
    for axes in (upper, lower):
        axes.axvline((correlated - startX) / unit, linestyle = ':', color = 'C2', label = correlatedLabel)
        axes.axvline((disk['x'] - startX) / unit, linestyle = '-', color = 'C0', linewidth = 0.6,
                     label = 'OpenFOAM Mach disk' if disk['present'] else 'OpenFOAM reflection')
    lower.axhline(1.0, color = 'C3', linewidth = 0.6, label = 'ambient')
    upper.set_ylabel('Mach number on the axis'); upper.legend(fontsize = 7)
    lower.set_ylabel('pressure / ambient'); lower.legend(fontsize = 7)
    lower.set_xlabel('distance from the exit plane / station radius'); lower.set_xlim(0.0, length)
    figure.tight_layout(); figure.savefig(path); plt.close(figure)

def drawMarchMass(path: str, reference: dict, unit: float, startX: float) -> None:

    '''The mass flow through each march station against the exit station's: NOVA's own continuity check.'''

    figure, axes = plt.subplots(figsize = (8.0, 3.6))
    for data, kind, label in ((reference['extendedMarch'], '--', 'march to 10 station radii'),
                              (reference['march'], '-', 'march, shipped reach')):
        flow = np.asarray(data['massFlow'])
        axes.plot((np.asarray(data['stationX']) - startX) / unit, (flow / flow[0] - 1.0) * 100.0, kind, color = 'C1',
                  linewidth = 2.2 if kind == '-' else 1.0, label = label)
    axes.axhline(-1.0, linestyle = ':', color = 'C3', label = 'NOVA\'s trust limit')
    axes.axhline(1.0, linestyle = ':', color = 'C3')
    axes.set_xlabel('distance from the exit plane / station radius'); axes.set_ylabel('station mass flow\nagainst the exit [%]')
    axes.legend(fontsize = 7)
    figure.tight_layout(); figure.savefig(path); plt.close(figure)

def drawConvergence(path: str, histories: dict, averageStart: float) -> None:

    figure, axes = plt.subplots(figsize = (8.0, 3.8))
    end = max(time[-1] for time, _ in histories.values())
    axes.axvspan(averageStart * 1e3, end * 1e3, color = 'C4', alpha = 0.12, linewidth = 0, label = 'averaging window')
    for name, (time, values) in histories.items():
        axes.plot(time * 1e3, values, linewidth = 0.8, label = name)
    axes.set_xlabel('time [ms]'); axes.set_ylabel('mass flow [kg/s]'); axes.legend(fontsize = 7)
    figure.tight_layout(); figure.savefig(path); plt.close(figure)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Comparison -- #
#--------------------------------------------------------------------------------------------------------------------------#

def compare(case: str) -> dict:

    '''Run every comparison on one case and write the figures and the results.'''

    with open(os.path.join(case, 'reference', 'novaPlume.json'), encoding = 'utf-8') as handle:
        reference = json.load(handle)
    with open(os.path.join(case, 'reference', 'case.json'), encoding = 'utf-8') as handle:
        settings = json.load(handle)
    with open(os.path.join(case, 'reference', 'style.json'), encoding = 'utf-8') as handle:
        style = json.load(handle)
    applyStyle(style)
    output = os.path.join(case, 'comparison')
    os.makedirs(output, exist_ok = True)

    gas, station = reference['gas'], reference['station']
    gamma = gas['gamma']
    startX, unit = station['x'], station['radius']
    toRadius = settings['radialScale'] * math.cos(math.radians(settings['wedgeAngle'] / 2.0))
    sectors = 360.0 / settings['wedgeAngle']
    length = settings['domain']['length']

    # -- Fields, averaged -- #
    latest = timeDirectories(case)[-1][1]
    centers = readInternalField(os.path.join(case, '0', 'C'))
    pressure = readInternalField(os.path.join(latest, 'pMean'))
    temperature = readInternalField(os.path.join(latest, 'TMean'))
    velocity = readInternalField(os.path.join(latest, 'UMean'))
    height = np.hypot(centers[:, 1], centers[:, 2])
    cellX, cellR = centers[:, 0], height / toRadius
    cellMach = machNumber(velocity, temperature, gas)
    cellAngle = np.arctan2((velocity[:, 1] * centers[:, 1] + velocity[:, 2] * centers[:, 2]) / height, velocity[:, 0])
    totalTemperature = temperature + np.sum(velocity**2, axis = 1) / (2.0 * gas['specificHeat'])
    fraction = ((totalTemperature - gas['ambientTemperature'])
                / (gas['stagnationTemperature'] - gas['ambientTemperature']))

    axisPath = glob.glob(os.path.join(case, 'postProcessing', 'axis', os.path.basename(latest), 'axis_*.xy'))[0]
    axisSample = readAxis(axisPath)
    axis = {'x': axisSample['x'], 'p': axisSample['pMean'],
            'mach': machNumber(axisSample['UMean'], axisSample['TMean'], gas)}

    # -- Jet boundary -- #
    # The contact surface leaves the lip of the station by construction, which closes the boundary
    # at the exit plane, half a cell upstream of the first column of cells
    boundary = jetBoundary(cellX, cellR, fraction)
    boundary = {key: np.concatenate([[startX if key == 'x' else unit], value]) for key, value in boundary.items()}
    march = reference['march']
    marchBoundaryX, marchBoundaryR = np.asarray(march['boundaryX']), np.asarray(march['boundaryR'])
    boundaryError = marchBoundaryR[1:] / np.interp(marchBoundaryX[1:], boundary['x'], boundary[0.5]) - 1.0
    angles = {'openFoam': lipAngle(boundary['x'], boundary[0.5], startX, unit),
              'march': lipAngle(marchBoundaryX, marchBoundaryR, startX, unit),
              'marchFirstSegment': float(np.degrees(np.arctan2(marchBoundaryR[1] - marchBoundaryR[0],
                                                               marchBoundaryX[1] - marchBoundaryX[0]))),
              'prandtlMeyer': float(np.degrees(reference['structure']['chamberGas']['initialTurnAngle'])),
              'prandtlMeyerAtStationLip': float(np.degrees(station['flowAngle'][-1]
                                                           + reference['structure']['chamberGas']['initialTurnAngle']
                                                           - reference['structure']['reported']['lipWallAngle'])),
              'correlationReported': float(np.degrees(reference['structure']['reported']['initialTurnAngle']))}

    # The extended march against the case, every two station radii: its boundary radius against the
    # case's, and its own mass drift, NOVA's measure of whether to trust it
    extended = reference['extendedMarch']
    extendedX, extendedR = np.asarray(extended['boundaryX']), np.asarray(extended['boundaryR'])
    extendedFlow = np.asarray(extended['massFlow'])
    departure = []
    for distance in np.arange(2.0, extended['reach'] + 0.5, 2.0):
        atX = startX + distance * unit
        if atX > extendedX[-1]:
            break
        departure.append({'x': float(distance),
                          'boundaryRadius': float(np.interp(atX, extendedX, extendedR)
                                                  / np.interp(atX, boundary['x'], boundary[0.5]) - 1.0),
                          'massDrift': float(np.interp(atX, np.asarray(extended['stationX']),
                                                       extendedFlow / extendedFlow[0] - 1.0))})

    # -- Field against the march, inside nine tenths of its boundary -- #
    shape = march['gridShape']
    grid = {key: np.asarray(march[key]).reshape(shape) for key in ('r', 'mach', 'flowAngle')}
    grid['x'] = np.repeat(np.asarray(march['stationX'])[:, None], shape[1], axis = 1)
    grid['pressure'] = gas['chamberPressure'] * (1.0 + 0.5 * (gamma - 1.0) * grid['mach']**2)**(-gamma / (gamma - 1.0))
    interior = grid['r'] <= 0.9 * grid['r'][:, -1:]
    interior[0] = False        # the exit station is the inflow itself
    nodes = {key: value[interior] for key, value in grid.items()}
    near = (cellX <= march['solvedTo'] + 0.5 * unit) & (cellR <= 3.0 * unit)
    onAxis = axis['x'] <= march['solvedTo'] + 0.5 * unit
    pointX = np.concatenate([cellX[near], axis['x'][onAxis]])
    pointR = np.concatenate([cellR[near], np.zeros(int(onAxis.sum()))])
    triangulation = tri.Triangulation(pointX, pointR)

    def interpolate(values: np.ndarray, atX: np.ndarray, atR: np.ndarray) -> np.ndarray:
        return np.asarray(tri.LinearTriInterpolator(triangulation, values)(atX, atR).filled(np.nan))

    nearMach = np.concatenate([cellMach[near], axis['mach'][onAxis]])
    nearPressure = np.concatenate([pressure[near], axis['p'][onAxis]])
    nearAngle = np.concatenate([cellAngle[near], np.zeros(int(onAxis.sum()))])
    fieldMachError = nodes['mach'] / interpolate(nearMach, nodes['x'], nodes['r']) - 1.0
    fieldPressureError = nodes['pressure'] / interpolate(nearPressure, nodes['x'], nodes['r']) - 1.0
    fieldAngleError = np.degrees(nodes['flowAngle'] - interpolate(nearAngle, nodes['x'], nodes['r']))

    # The case's pressure along its own boundary, which should be the ambient's
    inReach = boundary['x'] <= march['solvedTo']
    onBoundary = interpolate(nearPressure, boundary['x'][inReach], boundary[0.5][inReach])

    # -- Structure against the correlations -- #
    disk = machDisk(axis['x'], axis['mach'])
    # A regular reflection leaves no subsonic region behind it, so no disk
    disk['radius'] = diskRadius(cellX, cellR, cellMach, disk['x'], unit) if disk['present'] else 0.0
    cell = firstCell(boundary['x'], boundary[0.5], unit)
    chamberGas, reported = reference['structure']['chamberGas'], reference['structure']['reported']
    lipX = reference['nozzle']['lipX']
    structure = {
        'axisShockLocation': {'openFoam': disk['x'] - startX, 'correlation': chamberGas['axisShockX'] - lipX,
                              'reported': reported['axisShockX'] - lipX},
        'machDiskDiameter': {'openFoam': 2.0 * disk['radius'], 'correlation': chamberGas['machDiskDiameter'],
                             'reported': reported['machDiskDiameter']},
        'shockCellLength': {'openFoam': cell['neckX'] - startX, 'correlation': chamberGas['shockCellLength'],
                            'reported': reported['shockCellLength'], 'pack': chamberGas['cellLengthPack']},
        'maximumBoundaryRadius': {'openFoam': cell['maxRadius'], 'correlation': float(np.max(reported['boundaryR'])),
                                  'reported': float(np.max(reported['boundaryR']))},
    }
    # A disk both solutions leave out agrees; one only one of them carries does not
    for entry in structure.values():
        if entry['openFoam']:
            entry['difference'] = entry['correlation'] / entry['openFoam'] - 1.0
        else:
            entry['difference'] = 0.0 if entry['correlation'] == 0.0 else float('nan')

    # -- Steadiness and mass balance, over the averaging window -- #
    histories, window = {}, {}
    for name in ('inlet', 'outlet', 'farField'):
        time, flow = readHistory(case, f'{name}Flow')
        histories[name] = (time, flow * sectors * (-1.0 if name == 'inlet' else 1.0))
    for name, (time, values) in histories.items():
        inside = time >= settings['averageStart']
        time, values = time[inside], values[inside]
        middle = 0.5 * (time[0] + time[-1])
        window[name] = {'mean': float(values.mean()), 'oscillation': float(values.std() / abs(values.mean())),
                        'drift': float(values[time >= middle].mean() / values[time < middle].mean() - 1.0)}
    inflow = window['inlet']['mean']
    imbalance = (window['outlet']['mean'] + window['farField']['mean']) / inflow - 1.0

    # The Mach disk at every write inside the window, from the instantaneous axis samples
    diskHistory = []
    for time, folder in timeDirectories(os.path.join(case, 'postProcessing', 'axis')):
        if time < settings['averageStart']:
            continue
        sample = readAxis(glob.glob(os.path.join(folder, 'axis_*.xy'))[0])
        diskHistory.append((time, machDisk(sample['x'], machNumber(sample['U'], sample['T'], gas))['x']))

    # -- Judgement -- #
    measured = {
        'boundaryRadiusMax': statistics(boundaryError)['max'],
        'fieldMach95': statistics(fieldMachError)['p95'],
        'lipBoundaryAngle': angles['march'] - angles['openFoam'],
        'axisShockLocation': structure['axisShockLocation']['difference'],
        'machDiskDiameter': structure['machDiskDiameter']['difference'],
        'shockCellLength': structure['shockCellLength']['difference'],
        'massImbalance': imbalance,
        'meanDrift': window['outlet']['drift'],
    }
    judged = {key: {'value': float(value), 'limit': criteria[key],
                    'pass': bool(math.isfinite(value) and abs(value) <= criteria[key])}
              for key, value in measured.items()}

    stationRadius = np.asarray(station['r'])
    results = {
        'case': os.path.basename(os.path.abspath(case)), 'resolution': settings['resolution'], 'cells': settings['cells'],
        'cellsPerRadius': settings['cellsPerRadius'], 'time': float(os.path.basename(latest)),
        'averageStart': settings['averageStart'], 'stationRadius': unit,
        'massFlow': {'openFoamInflow': inflow, 'marchStation': station['massFlow'],
                     'nozzleExit': reference['nozzle']['exitMassFlow'],
                     'stationAgainstNozzle': station['massFlow'] / reference['nozzle']['exitMassFlow'] - 1.0,
                     'stationAreaAgainstLip': (stationRadius[-1] / reference['nozzle']['lipRadius'])**2 - 1.0},
        'boundary': {'radius': statistics(boundaryError),
                     'endOfMarch': {'x': float((marchBoundaryX[-1] - startX) / unit),
                                    'openFoam': float(np.interp(marchBoundaryX[-1], boundary['x'], boundary[0.5]) / unit),
                                    'march': float(marchBoundaryR[-1] / unit)},
                     'layerWidthAtEndOfMarch': float(np.interp(marchBoundaryX[-1], boundary['x'],
                                                               boundary[0.1] - boundary[0.9]) / unit),
                     'pressureOverAmbient': statistics(onBoundary / gas['ambientPressure'] - 1.0),
                     'angleDegrees': angles},
        'extendedMarch': departure,
        'fieldMach': statistics(fieldMachError),
        'fieldPressure': statistics(fieldPressureError),
        'fieldFlowAngleDegrees': statistics(fieldAngleError),
        'machDisk': {**disk, 'xFromExit': (disk['x'] - startX) / unit, 'radiusOverStation': disk['radius'] / unit,
                     'history': diskHistory,
                     'oscillation': float(np.std([x for _, x in diskHistory]) / unit) if diskHistory else float('nan')},
        'firstCell': {key: (value - startX) / unit if key.endswith('X') else value / unit for key, value in cell.items()},
        'structure': structure,
        'steadiness': {'massImbalance': imbalance, 'window': window},
        'criteria': judged,
        'allPass': all(entry['pass'] for entry in judged.values()),
    }
    with open(os.path.join(output, 'comparison.json'), 'w', encoding = 'utf-8') as handle:
        json.dump(results, handle, indent = 2)

    # -- Figures -- #
    # The axis line, the inflow and the first column's values carried to the base close the field
    # out to the axis and the exit plane, half a cell beyond the outermost cell centers
    firstColumn = columns(cellX)[0]
    base = firstColumn[cellR[firstColumn] > unit]
    stationRadius = np.asarray(station['r'])
    points = {'x': np.concatenate([cellX, axis['x'], np.full(len(stationRadius) + len(base), startX)]),
              'r': np.concatenate([cellR, np.zeros_like(axis['x']), stationRadius, cellR[base]]),
              'mach': np.concatenate([cellMach, axis['mach'], station['mach'], cellMach[base]])}
    lines = {'march': (marchBoundaryX, marchBoundaryR, '-', 'accent', 'NOVA march boundary')}
    drawField(os.path.join(output, 'plumeNearField.png'), points, grid, boundary, lines, style, unit, startX,
              (march['reach'] * 1.25, 2.2))
    structureBoundary = reference['structure']['reported']
    lines = {'march': (marchBoundaryX, marchBoundaryR, '-', 'accent', 'NOVA march, shipped reach'),
             'extended': (extendedX, extendedR, '--', 'accent', f'NOVA march to {extended["reach"]:.0f}'),
             'correlated': (np.asarray(structureBoundary['boundaryX']), np.asarray(structureBoundary['boundaryR']), ':',
                            'red', 'NOVA correlated boundary')}
    markers = {(chamberGas['axisShockX'], 0.0): ('o', 'red', 'NOVA Mach disk, Lewis and Carlson' if chamberGas['machDiskPresent']
                                                 else 'NOVA regular reflection, Smith and Richards'),
               (disk['x'], 0.0): ('v', 'yellow', 'OpenFOAM Mach disk' if disk['present'] else 'OpenFOAM reflection')}
    drawField(os.path.join(output, 'plumeField.png'), points, None, boundary, lines, style, unit, startX,
              (min(length, 24.0), 3.0), markers)
    drawFieldError(os.path.join(output, 'plumeFieldDifference.png'), nodes, fieldMachError, style, unit, startX)
    drawBoundary(os.path.join(output, 'plumeBoundary.png'), boundary, reference, cell, unit, startX, min(length, 24.0))
    drawAxis(os.path.join(output, 'plumeAxis.png'), axis, reference, disk, unit, startX, min(length, 24.0))
    drawMarchMass(os.path.join(output, 'plumeMarchMass.png'), reference, unit, startX)
    drawConvergence(os.path.join(output, 'plumeMassFlow.png'), histories, settings['averageStart'])

    return results

def report(results: dict) -> str:

    '''The comparison as a plain-text table.'''

    boundary, disk, flows = results['boundary'], results['machDisk'], results['massFlow']
    lines = [f"{results['resolution']} grid, {results['cells']} cells, {results['cellsPerRadius']} per station radius, "
             f"t = {results['time']:g} s", '',
             f"mass flow: OpenFOAM inflow {flows['openFoamInflow']:.5g} kg/s, march station {flows['marchStation']:.5g}, "
             f"nozzle exit {flows['nozzleExit']:.5g} (station against nozzle {flows['stationAgainstNozzle'] * 100:+.2f}%, "
             f"station area against the lip's {flows['stationAreaAgainstLip'] * 100:+.2f}%)",
             f"boundary at the end of the march, x = {boundary['endOfMarch']['x']:.3f}: OpenFOAM "
             f"{boundary['endOfMarch']['openFoam']:.4f}, march {boundary['endOfMarch']['march']:.4f} station radii; "
             f"contact layer {boundary['layerWidthAtEndOfMarch']:.3f} wide",
             'boundary angle over the first half station radius [deg]: '
             + ', '.join(f"{key} {value:.2f}" for key, value in boundary['angleDegrees'].items()),
             f"Mach disk: {'present' if disk['present'] else 'regular reflection'} at {disk['xFromExit']:.3f} station radii, "
             f"radius {disk['radiusOverStation']:.3f}, peak Mach {disk['peakMach']:.3f}, "
             f"oscillation {disk['oscillation']:.4f} station radii over the window",
             'extended march, boundary radius against OpenFOAM and its own mass drift: '
             + ', '.join(f"x = {entry['x']:.0f}: {entry['boundaryRadius'] * 100:+.1f}% / {entry['massDrift'] * 100:+.1f}%"
                         for entry in results['extendedMarch']), '',
             f"{'structure':24s} {'OpenFOAM':>12s} {'correlation':>12s} {'difference':>11s} {'NOVA reported':>14s}"]
    for key, entry in results['structure'].items():
        lines.append(f"{key:24s} {entry['openFoam']:12.5g} {entry['correlation']:12.5g} {entry['difference'] * 100:10.2f}% "
                     f"{entry['reported']:14.5g}")
    lines += ['', f"{'criterion':24s} {'value':>11s} {'limit':>11s}  result"]
    for key, entry in results['criteria'].items():
        scale, unitLabel = (1.0, ' deg') if key in absoluteCriteria else (100.0, '%')
        lines.append(f"{key:24s} {entry['value'] * scale:10.3f}{unitLabel} {entry['limit'] * scale:10.3f}{unitLabel}  "
                     f"{'pass' if entry['pass'] else 'FAIL'}")
    for key in ('fieldMach', 'fieldPressure', 'fieldFlowAngleDegrees'):
        entry, scale = results[key], (1.0 if key.endswith('Degrees') else 100.0)
        lines.append(f"{key:24s} mean {entry['mean'] * scale:.3f}  p95 {entry['p95'] * scale:.3f}  "
                     f"max {entry['max'] * scale:.3f}  ({entry['count']} nodes)")
    entry = boundary['pressureOverAmbient']
    lines.append(f"{'boundary pressure':24s} mean {entry['mean'] * 100:.2f}%  max {entry['max'] * 100:.2f}% from ambient")
    window = results['steadiness']['window']
    lines.append('window means [kg/s]: ' + ', '.join(f"{key} {entry['mean']:.5g} (oscillation {entry['oscillation'] * 100:.3f}%, "
                                                     f"drift {entry['drift'] * 100:+.3f}%)" for key, entry in window.items()))

    return '\n'.join(lines)

if __name__ == '__main__':
    print(report(compare(sys.argv[1] if len(sys.argv) > 1 else '.')))
