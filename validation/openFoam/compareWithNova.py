# -- NOVA Nozzle: OpenFOAM Against NOVA -- #

'''

Compare a converged OpenFOAM solution of the NOVA nozzle with NOVA's method of characteristics,
judge it against the acceptance criteria, and draw the comparison.

Both solutions are of the same problem: the Euler equations for a calorically perfect gas at
NOVA's chamber ratio of specific heats, from the same stagnation state, inside the same wall. The
comparison is a cross-check between two methods. Neither solution is a validated reference, so
agreement shows the two are consistent; it does not show either is right.

What is compared:

    - The exit plane: mass flow, vacuum thrust coefficient, thrust per unit mass flow, and the
      mass-averaged Mach number, each integrated from the plane on both sides; and the radial
      profiles of Mach number, pressure and flow angle.
    - The centerline Mach number, at every node of NOVA's characteristic mesh on the axis.
    - The wall pressure and Mach number against NOVA's near-wall state: the characteristic wall
      in the diverging section, and both converging-wall models ahead of the throat.
    - The Mach number and flow angle at every node of the characteristic mesh inside the nozzle.
    - Steadiness: the mass through each end and the force on the exit plane, averaged over the
      window the fields are averaged over.

Every comparison reads the fields averaged over the second half of the run. The chamber's radial
acoustic modes are not damped by an inviscid solution, so they ring for the whole run at a few
tenths of a percent of the inlet mass flow; the mean flow is steady, and an instant of it is not.

The criteria limits are listed in `criteria` below and in README.md.

Run from the case folder after `reconstructPar -latestTime`; Allrun does this:

    python3 scripts/compareWithNova.py <case>

Writes `<case>/comparison/comparison.json` and the figures beside it. Needs NumPy and Matplotlib.

Author: Sean Bowman

'''

import glob
import json
import math
import os
import re
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import tri
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

# Acceptance criteria, as relative errors of OpenFOAM against NOVA unless the unit says otherwise
criteria = {
    'vacuumThrustCoefficient': 0.010,
    'massFlow':                0.010,
    'thrustPerMassFlow':       0.005,
    'exitMassAveragedMach':    0.010,
    'centerlineMachMax':       0.020,
    'divergingWallPressureMax': 0.050,
    'fieldMach95':             0.020,
    'massImbalance':           0.001,
    'meanDrift':               0.0005,
}

# Fields stored as three columns in a sample file; everything else is one
vectorFields = ('U', 'UMean')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Reading the case -- #
#--------------------------------------------------------------------------------------------------------------------------#

def readInternalField(path: str) -> np.ndarray:

    '''

    The internal field of an ASCII volume field.

    Returns:
    --------
    np.ndarray : (cells,) for a scalar, (cells, 3) for a vector

    '''

    with open(path, encoding = 'utf-8') as handle:
        text = handle.read()
    match = re.search(r'internalField\s+nonuniform\s+List<(scalar|vector)>\s*(\d+)\s*\((.*?)\n\)\s*;', text, re.DOTALL)
    if match is None:
        raise ValueError(f'{path} carries no ASCII list for its internal field.')
    values = np.array(match.group(3).replace('(', ' ').replace(')', ' ').split(), dtype = float)

    return values.reshape(-1, 3) if match.group(1) == 'vector' else values

def timeDirectories(folder: str) -> list:

    '''The numeric subfolders of a folder, as (time, path), earliest first.'''

    times = []
    for path in glob.glob(os.path.join(folder, '*')):
        try:
            times.append((float(os.path.basename(path)), path))
        except ValueError:
            continue

    return sorted(times)

def machNumber(velocity: np.ndarray, temperature: np.ndarray, gas: dict) -> np.ndarray:

    '''Mach number from velocity [m/s] and temperature [K] in the case's gas.'''

    return np.linalg.norm(velocity, axis = 1) / np.sqrt(gas['gamma'] * gas['gasConstant'] * temperature)

def readPatch(case: str, time: str, patch: str, toRadius: float, gas: dict) -> dict:

    '''

    The time-averaged face values of one sampled patch, with the radius mapped back to the contour.

    Parameters:
    -----------
    toRadius : float
        Mesh height on the wedge's mid-plane over contour radius

    '''

    folder = os.path.join(case, 'postProcessing', 'patches', time)
    data = {}
    for field in ('p', 'T', 'U'):
        values = np.loadtxt(os.path.join(folder, f'{field}Mean_{patch}.raw'), comments = '#', ndmin = 2)
        data['x'], data['r'] = values[:, 0], np.hypot(values[:, 1], values[:, 2]) / toRadius
        data[field] = values[:, 3:6] if field == 'U' else values[:, 3]
    data['Ma'] = machNumber(data['U'], data['T'], gas)

    return data

def readAxis(case: str, time: str, gas: dict) -> dict:

    '''The time-averaged state along the axis line.'''

    path = glob.glob(os.path.join(case, 'postProcessing', 'axis', time, 'axis_*.xy'))[0]
    values = np.loadtxt(path)
    # The file is named for its fields in column order, after the three coordinates
    columns, start = {}, 3
    for name in os.path.basename(path)[len('axis_'):-len('.xy')].split('_'):
        width = 3 if name in vectorFields else 1
        columns[name] = values[:, start:start + width] if width == 3 else values[:, start]
        start += width

    return {'x': values[:, 0], 'mach': machNumber(columns['UMean'], columns['TMean'], gas)}

def readHistory(case: str, name: str) -> tuple:

    '''

    One surface-integral history over the run, from every restart of it.

    Returns:
    --------
    tuple : (times [s], values), a vector history as (samples, 3)

    '''

    times, values = [], []
    for _, folder in timeDirectories(os.path.join(case, 'postProcessing', name)):
        with open(os.path.join(folder, 'surfaceFieldValue.dat'), encoding = 'utf-8') as handle:
            for line in handle:
                if line.startswith('#') or not line.strip():
                    continue
                numbers = [float(number) for number in line.replace('(', ' ').replace(')', ' ').split()]
                times.append(numbers[0]); values.append(numbers[1:])
    values = np.asarray(values)

    return np.asarray(times), (values[:, 0] if values.shape[1] == 1 else values)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Integrals and errors -- #
#--------------------------------------------------------------------------------------------------------------------------#

def exitIntegrals(outlet: dict, gas: dict, exitRadius: float, throatRadius: float) -> dict:

    '''

    Mass flow, vacuum thrust and the plane's averages from the outlet face values.

    The outlet faces are equal radial divisions of the exit radius, each face carrying the value of
    the cell behind it (zero gradient), so the mass flow is the one the solver passes.

    '''

    order = np.argsort(outlet['r'])
    edges = np.linspace(0.0, exitRadius, len(order) + 1)
    area = math.pi * (edges[1:]**2 - edges[:-1]**2)                              # [m^2]
    pressure, temperature, mach = outlet['p'][order], outlet['T'][order], outlet['Ma'][order]
    axialVelocity = outlet['U'][order, 0]
    density = pressure / (gas['gasConstant'] * temperature)

    massFlow = float(np.sum(density * axialVelocity * area))                     # [kg/s]
    thrust = float(np.sum((density * axialVelocity**2 + pressure) * area))       # [N], vacuum
    weight = density * axialVelocity * area

    return {
        'massFlow': massFlow,
        'vacuumThrust': thrust,
        'vacuumThrustCoefficient': thrust / (gas['chamberPressure'] * math.pi * throatRadius**2),
        'thrustPerMassFlow': thrust / massFlow,
        'exitMassAveragedMach': float(np.sum(mach * weight) / massFlow),
        'exitAreaAveragedPressure': float(np.sum(pressure * area) / np.sum(area)),
        'exitMassAveragedPressure': float(np.sum(pressure * weight) / massFlow),
    }

def novaExitIntegrals(reference: dict) -> dict:

    '''

    NOVA's exit plane integrated the way NOVA integrates it: strips between neighboring
    stations, each carrying the mean of its two stations.

    '''

    gas, plane, performance = reference['gas'], reference['exitPlane'], reference['performance']
    gamma, gasConstant, stagnationTemperature = gas['gamma'], gas['gasConstant'], gas['stagnationTemperature']
    radius, mach = np.asarray(plane['r']), np.asarray(plane['mach'])
    angle, pressure = np.asarray(plane['flowAngle']), np.asarray(plane['pressure'])

    area = math.pi * (radius[:-1]**2 - radius[1:]**2)
    meanMach, meanPressure = 0.5 * (mach[:-1] + mach[1:]), 0.5 * (pressure[:-1] + pressure[1:])
    meanAngle = 0.5 * (angle[:-1] + angle[1:])
    temperature = stagnationTemperature / (1.0 + 0.5 * (gamma - 1.0) * meanMach**2)
    massFlux = meanPressure / (gasConstant * temperature) * meanMach * np.sqrt(gamma * gasConstant * temperature) \
               * np.cos(meanAngle)
    thrust = performance['vacuumThrustCoefficient'] * gas['chamberPressure'] * math.pi \
             * reference['geometry']['throatRadius']**2

    return {
        'massFlow': performance['massFlow'],
        'vacuumThrust': thrust,
        'vacuumThrustCoefficient': performance['vacuumThrustCoefficient'],
        'thrustPerMassFlow': thrust / performance['massFlow'],
        'exitMassAveragedMach': float(np.sum(meanMach * massFlux * area) / np.sum(massFlux * area)),
        'exitAreaAveragedPressure': performance['exitAreaAveragedPressure'],
        'exitMassAveragedPressure': performance['exitMassAveragedPressure'],
    }

def novaProfileIntegrals(reference: dict, samples: int = 200001) -> dict:

    '''

    NOVA's exit plane integrated exactly as a piecewise-linear profile in radius, with one rule for
    every quantity.

    NOVA integrates its thrust by strips carrying the mean of their two stations and its mass flow
    by the trapezoidal rule on mass flux times radius. On most of the plane the two agree, but the
    core NOVA closes linearly is a single segment from about a quarter of the exit radius to the
    axis, and over it the two rules err in opposite directions. This integral separates what NOVA's
    flow field says from what its quadrature does to it. Stations outside the wall are dropped.

    '''

    gas, plane = reference['gas'], reference['exitPlane']
    gamma, gasConstant, stagnationTemperature = gas['gamma'], gas['gasConstant'], gas['stagnationTemperature']
    radius = np.asarray(plane['r'])
    # The wall station carries the exit radius to the reference's nine significant figures
    inside = radius <= reference['geometry']['exitRadius'] * (1.0 + 1e-6)
    order = np.argsort(radius[inside])
    stations = radius[inside][order]
    profile = {key: np.asarray(plane[key])[inside][order] for key in ('mach', 'flowAngle', 'pressure')}

    fine = np.linspace(0.0, stations[-1], samples)
    mach, angle, pressure = (np.interp(fine, stations, profile[key]) for key in ('mach', 'flowAngle', 'pressure'))
    temperature = stagnationTemperature / (1.0 + 0.5 * (gamma - 1.0) * mach**2)
    axialVelocity = mach * np.sqrt(gamma * gasConstant * temperature) * np.cos(angle)
    density = pressure / (gasConstant * temperature)

    def integral(values: np.ndarray) -> float:
        weighted = values * fine
        return float(2.0 * math.pi * np.sum(0.5 * (weighted[1:] + weighted[:-1]) * np.diff(fine)))

    massFlow = integral(density * axialVelocity)
    thrust = integral(density * axialVelocity**2 + pressure)
    throatArea = math.pi * reference['geometry']['throatRadius']**2

    return {
        'massFlow': massFlow,
        'vacuumThrust': thrust,
        'vacuumThrustCoefficient': thrust / (gas['chamberPressure'] * throatArea),
        'thrustPerMassFlow': thrust / massFlow,
        'exitMassAveragedMach': integral(mach * density * axialVelocity) / massFlow,
        'exitAreaAveragedPressure': integral(pressure) / (math.pi * stations[-1]**2),
        'exitMassAveragedPressure': integral(pressure * density * axialVelocity) / massFlow,
    }

def throatDischargeCoefficients(gamma: float, curvature: float) -> dict:

    '''

    Inviscid discharge coefficient of an axisymmetric throat from the transonic series, for a
    throat wall radius of curvature `curvature` times the throat radius.

    Hall's series, as Kliegel and Levine corrected it, in inverse powers of R; and Kliegel and
    Levine's recast in inverse powers of R + 1, which stays physical at small R. Both are taken
    from Cao, Wang, Li and Ding, FLOMEKO 2019, equations 2 and 3. Both assume a symmetric throat;
    this one has a 1.5 entrant arc and a 0.382 exit arc, so each is evaluated at both.

    '''

    def series(radius: float, second: float, third: float) -> float:
        return 1.0 - (gamma + 1.0) / radius**2 * (1.0 / 96.0 - second / radius + third / radius**2)

    hall = series(curvature, (8.0 * gamma + 21.0) / 2304.0, (754.0 * gamma**2 + 2123.0 * gamma + 2553.0) / 552960.0)
    shifted = curvature + 1.0
    kliegelLevine = series(shifted, (8.0 * gamma - 27.0) / 2304.0, (754.0 * gamma**2 - 757.0 * gamma + 3633.0) / 276480.0)

    return {'hall': hall, 'kliegelLevine': kliegelLevine}

def statistics(error: np.ndarray) -> dict:

    '''Mean, RMS, 95th percentile and maximum of the magnitude of an error.'''

    magnitude = np.abs(error[np.isfinite(error)])

    return {'mean': float(np.mean(magnitude)), 'rms': float(np.sqrt(np.mean(magnitude**2))),
            'p95': float(np.percentile(magnitude, 95)), 'max': float(np.max(magnitude)), 'count': int(magnitude.size)}

def fieldInterpolator(x: np.ndarray, r: np.ndarray, wallX: np.ndarray, wallR: np.ndarray):

    '''

    Linear interpolation over scattered points inside the nozzle. Triangles whose centroid lies
    outside the wall are masked, so nothing is interpolated across the outside of the throat.
    A point outside every triangle takes its nearest point's value.

    '''

    triangulation = tri.Triangulation(x, r)
    corners = triangulation.triangles
    centroidX, centroidR = x[corners].mean(axis = 1), r[corners].mean(axis = 1)
    triangulation.set_mask(centroidR > np.interp(centroidX, wallX, wallR))

    def interpolate(values: np.ndarray, atX: np.ndarray, atR: np.ndarray) -> np.ndarray:
        result = np.asarray(tri.LinearTriInterpolator(triangulation, values)(atX, atR).filled(np.nan))
        for index in np.flatnonzero(~np.isfinite(result)):
            result[index] = values[np.argmin((x - atX[index])**2 + (r - atR[index])**2)]
        return result

    return triangulation, interpolate

#--------------------------------------------------------------------------------------------------------------------------#
# -- Figures -- #
#--------------------------------------------------------------------------------------------------------------------------#

def applyStyle(style: dict) -> None:

    '''NOVA's figure palette, from the style the case was written with.'''

    named = style['colors']
    plt.rcParams.update({
        'figure.facecolor': named['bg'], 'savefig.facecolor': named['bg'], 'axes.facecolor': named['surface'],
        'axes.edgecolor': named['border'], 'axes.labelcolor': named['text'], 'axes.titlecolor': named['text'],
        'text.color': named['text'], 'xtick.color': named['textMuted'], 'ytick.color': named['textMuted'],
        'grid.color': named['border'], 'legend.facecolor': named['surface2'], 'legend.edgecolor': named['border'],
        'axes.prop_cycle': plt.cycler(color = style['categories']), 'font.size': 9, 'axes.grid': True,
        'grid.linewidth': 0.5, 'savefig.dpi': 160,
    })

def drawFields(path: str, cells: dict, nodes: dict, wall: tuple, style: dict, triangulation) -> None:

    '''Mach number, OpenFOAM above the axis and NOVA below it, on one scale.'''

    wallX, wallR = wall
    named = style['colors']
    machMap = LinearSegmentedColormap.from_list('novaMach', style['colormaps']['mach'])
    levels = np.linspace(0.0, math.ceil(max(np.max(cells['mach']), np.max(nodes['mach'])) * 2.0) / 2.0, 41)

    novaTriangulation = tri.Triangulation(nodes['x'], -nodes['r'])
    corners = novaTriangulation.triangles
    centroidX, centroidR = nodes['x'][corners].mean(axis = 1), nodes['r'][corners].mean(axis = 1)
    novaTriangulation.set_mask(centroidR > np.interp(centroidX, wallX, wallR))

    figure, axes = plt.subplots(figsize = (10.0, 5.2))
    filled = axes.tricontourf(triangulation, cells['mach'], levels = levels, cmap = machMap)
    axes.tricontourf(novaTriangulation, nodes['mach'], levels = levels, cmap = machMap)
    axes.tricontour(triangulation, cells['mach'], levels = levels[::4], colors = named['bg'], linewidths = 0.4)
    axes.tricontour(novaTriangulation, nodes['mach'], levels = levels[::4], colors = named['bg'], linewidths = 0.4)
    for sign in (1.0, -1.0):
        axes.plot(wallX, sign * wallR, color = named['accent'], linewidth = 1.6)
    axes.axhline(0.0, color = named['textMuted'], linewidth = 0.6)
    axes.text(0.02, 0.95, 'OpenFOAM, rhoCentralFoam', transform = axes.transAxes, va = 'top')
    axes.text(0.02, 0.05, 'NOVA, method of characteristics', transform = axes.transAxes, va = 'bottom')
    axes.set_aspect('equal'); axes.grid(False)
    axes.set_xlabel('x [m]'); axes.set_ylabel('r [m]')
    figure.colorbar(filled, ax = axes, label = 'Mach number', shrink = 0.8, ticks = levels[::8])
    figure.tight_layout(); figure.savefig(path); plt.close(figure)

def drawFieldError(path: str, nodes: dict, error: np.ndarray, wall: tuple, style: dict) -> None:

    '''The Mach number difference at every characteristic node.'''

    wallX, wallR = wall
    named = style['colors']
    errorMap = LinearSegmentedColormap.from_list('novaError', style['colormaps']['pressure'])
    limit = max(float(np.percentile(np.abs(error), 99)), 1e-4) * 100.0

    figure, axes = plt.subplots(figsize = (10.0, 3.6))
    points = axes.scatter(nodes['x'], nodes['r'], c = error * 100.0, s = 3, cmap = errorMap,
                          norm = TwoSlopeNorm(0.0, -limit, limit), linewidths = 0)
    axes.plot(wallX, wallR, color = named['accent'], linewidth = 1.4)
    axes.set_xlim(-0.05 * wallX[-1], wallX[-1] * 1.02); axes.set_ylim(0.0, wallR[-1] * 1.05)
    axes.set_aspect('equal'); axes.grid(False)
    axes.set_xlabel('x [m]'); axes.set_ylabel('r [m]')
    figure.colorbar(points, ax = axes, label = 'Mach number, OpenFOAM against NOVA [%]', shrink = 0.9)
    figure.tight_layout(); figure.savefig(path); plt.close(figure)

def drawCenterline(path: str, axis: dict, nodes: dict, error: np.ndarray, throatRadius: float) -> None:

    figure, (upper, lower) = plt.subplots(2, 1, figsize = (8.0, 5.6), sharex = True, height_ratios = (3, 1))
    upper.plot(axis['x'] / throatRadius, axis['mach'], label = 'OpenFOAM')
    upper.plot(nodes['x'] / throatRadius, nodes['mach'], 'o', markersize = 3, label = 'NOVA, axis nodes')
    upper.set_ylabel('Mach number'); upper.legend()
    lower.plot(nodes['x'] / throatRadius, error * 100.0, 'o', markersize = 3, color = 'C1')
    lower.axhline(0.0, linewidth = 0.6)
    lower.set_xlabel('x / throat radius'); lower.set_ylabel('difference [%]')
    figure.tight_layout(); figure.savefig(path); plt.close(figure)

def drawWall(path: str, wall: dict, nova: dict, chamberPressure: float, throatRadius: float) -> None:

    figure, (upper, lower) = plt.subplots(2, 1, figsize = (8.0, 6.4), sharex = True)
    novaX = nova['x'] / throatRadius
    upper.semilogy(wall['x'] / throatRadius, wall['p'] / chamberPressure, label = 'OpenFOAM, wall faces')
    upper.semilogy(novaX, nova['pressure'] / chamberPressure, '--', label = 'NOVA, one-dimensional converging wall')
    upper.semilogy(novaX, nova['transonicPressure'] / chamberPressure, ':', label = 'NOVA, transonic converging wall')
    upper.set_ylabel('wall pressure / chamber pressure'); upper.legend()
    lower.plot(wall['x'] / throatRadius, wall['Ma'], label = 'OpenFOAM')
    lower.plot(novaX, nova['mach'], '--', label = 'NOVA, one-dimensional')
    lower.plot(novaX, nova['transonicMach'], ':', label = 'NOVA, transonic')
    lower.set_xlabel('x / throat radius'); lower.set_ylabel('wall Mach number')
    figure.tight_layout(); figure.savefig(path); plt.close(figure)

def drawTotalPressure(path: str, x: np.ndarray, totalPressure: np.ndarray, rows: dict, throatRadius: float) -> None:

    '''Total pressure along the nozzle in the row of cells against the wall, the row behind it, and the interior.'''

    labels = {'wallRow': 'cells against the wall', 'secondRow': 'second row from the wall', 'interior': 'interior, r < 0.9 wall radius'}
    figure, axes = plt.subplots(figsize = (8.0, 3.8))
    for name, row in rows.items():
        order = np.argsort(x[row])
        style = '.' if name == 'interior' else '-'
        axes.plot(x[row][order] / throatRadius, totalPressure[row][order], style, markersize = 1.0, linewidth = 1.0,
                  label = labels[name])
    axes.set_xlabel('x / throat radius'); axes.set_ylabel('total pressure / chamber pressure')
    axes.set_ylim(0.8, 1.1); axes.legend()
    figure.tight_layout(); figure.savefig(path); plt.close(figure)

def drawExitPlane(path: str, outlet: dict, reference: dict) -> None:

    plane, exitRadius = reference['exitPlane'], reference['geometry']['exitRadius']
    chamberPressure = reference['gas']['chamberPressure']
    order = np.argsort(outlet['r'])
    radius = outlet['r'][order] / exitRadius
    angle = np.degrees(np.arctan2(outlet['U'][order, 1], outlet['U'][order, 0]))
    novaRadius = np.asarray(plane['r']) / exitRadius

    figure, panels = plt.subplots(1, 3, figsize = (11.0, 3.8), sharey = True)
    for axes, ours, theirs, label in (
            (panels[0], outlet['Ma'][order], plane['mach'], 'Mach number'),
            (panels[1], outlet['p'][order] / chamberPressure, np.asarray(plane['pressure']) / chamberPressure,
             'pressure / chamber pressure'),
            (panels[2], angle, np.degrees(plane['flowAngle']), 'flow angle [deg]')):
        axes.plot(ours, radius, label = 'OpenFOAM')
        axes.plot(theirs, novaRadius, 'o', markersize = 3, label = 'NOVA')
        axes.set_xlabel(label)
    panels[0].set_ylabel('r / exit radius'); panels[0].legend()
    figure.tight_layout(); figure.savefig(path); plt.close(figure)

def drawConvergence(path: str, inlet: tuple, outlet: tuple, novaMassFlow: float, averageStart: float) -> None:

    '''Mass flow through each end over the run, with the window the fields are averaged over shaded.'''

    figure, axes = plt.subplots(figsize = (8.0, 3.8))
    axes.axvspan(averageStart * 1e3, outlet[0][-1] * 1e3, color = 'C4', alpha = 0.12, linewidth = 0,
                 label = 'averaging window')
    axes.plot(inlet[0] * 1e3, inlet[1], linewidth = 0.8, label = 'inlet')
    axes.plot(outlet[0] * 1e3, outlet[1], linewidth = 0.8, label = 'outlet')
    axes.axhline(novaMassFlow, linestyle = '--', color = 'C2', label = 'NOVA, exit plane')
    axes.set_xlabel('time [ms]'); axes.set_ylabel('mass flow [kg/s]'); axes.legend()
    final = outlet[1][-1]
    axes.set_ylim(final * 0.97, final * 1.03)
    figure.tight_layout(); figure.savefig(path); plt.close(figure)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Comparison -- #
#--------------------------------------------------------------------------------------------------------------------------#

def compare(case: str) -> dict:

    '''Run every comparison on one case and write the figures and the results.'''

    with open(os.path.join(case, 'reference', 'novaNozzle.json'), encoding = 'utf-8') as handle:
        reference = json.load(handle)
    with open(os.path.join(case, 'reference', 'case.json'), encoding = 'utf-8') as handle:
        settings = json.load(handle)
    with open(os.path.join(case, 'reference', 'style.json'), encoding = 'utf-8') as handle:
        style = json.load(handle)
    applyStyle(style)
    output = os.path.join(case, 'comparison')
    os.makedirs(output, exist_ok = True)

    gas, geometry = reference['gas'], reference['geometry']
    gamma, chamberPressure = gas['gamma'], gas['chamberPressure']
    throatRadius, exitRadius = geometry['throatRadius'], geometry['exitRadius']
    wallX, wallR = np.asarray(geometry['wallX']), np.asarray(geometry['wallR'])
    # Mesh height on the wedge's mid-plane over contour radius, and full turns over the wedge
    toRadius = settings['radialScale'] * math.cos(math.radians(settings['wedgeAngle'] / 2.0))
    sectors = 360.0 / settings['wedgeAngle']

    latest = os.path.basename(timeDirectories(os.path.join(case, 'postProcessing', 'patches'))[-1][1])

    # -- Exit plane -- #
    outlet = readPatch(case, latest, 'outlet', toRadius, gas)
    ours = exitIntegrals(outlet, gas, exitRadius, throatRadius)
    theirs = novaExitIntegrals(reference)
    profile = novaProfileIntegrals(reference)
    exitPlane = {key: {'openFoam': ours[key], 'nova': theirs[key], 'difference': ours[key] / theirs[key] - 1.0,
                       'novaProfile': profile[key], 'differenceFromProfile': ours[key] / profile[key] - 1.0}
                 for key in ours}

    # -- Steadiness, over the averaging window -- #
    inletTime, inletFlow = readHistory(case, 'inletFlow')
    outletTime, outletFlow = readHistory(case, 'outletFlow')
    momentumTime, momentum = readHistory(case, 'outletMomentum')
    pressureTime, pressureForce = readHistory(case, 'outletPressure')
    inletFlow, outletFlow = -inletFlow * sectors, outletFlow * sectors
    thrust = (momentum[:, 0] + np.interp(momentumTime, pressureTime, pressureForce)) * sectors
    histories = {'inletMassFlow': (inletTime, inletFlow), 'outletMassFlow': (outletTime, outletFlow),
                 'vacuumThrust': (momentumTime, thrust)}
    window = {}
    for key, (time, values) in histories.items():
        inside = time >= settings['averageStart']
        time, values = time[inside], values[inside]
        middle = 0.5 * (time[0] + time[-1])
        window[key] = {'mean': float(values.mean()), 'oscillation': float(values.std() / values.mean()),
                       'drift': float(values[time >= middle].mean() / values[time < middle].mean() - 1.0)}
    imbalance = window['outletMassFlow']['mean'] / window['inletMassFlow']['mean'] - 1.0
    meanDrift = max(abs(window[key]['drift']) for key in ('outletMassFlow', 'vacuumThrust'))

    # -- Centerline -- #
    axis = readAxis(case, latest, gas)
    characteristics = {key: np.asarray(value) for key, value in reference['characteristics'].items()}
    onAxis = characteristics['r'] < 1e-3 * throatRadius
    axisNodes = {key: value[onAxis] for key, value in characteristics.items()}
    order = np.argsort(axisNodes['x'])
    axisNodes = {key: value[order] for key, value in axisNodes.items()}
    centerlineError = np.interp(axisNodes['x'], axis['x'], axis['mach']) / axisNodes['mach'] - 1.0

    # -- Wall -- #
    wall = readPatch(case, latest, 'wall', toRadius, gas)
    order = np.argsort(wall['x'])
    wall = {key: value[order] for key, value in wall.items()}
    nearWall = {key: np.asarray(value) for key, value in reference['nearWall'].items()}
    wallPressure = np.interp(nearWall['x'], wall['x'], wall['p'])
    wallMach = np.interp(nearWall['x'], wall['x'], wall['Ma'])
    diverging = nearWall['x'] >= geometry['throatX'] + throatRadius
    converging = nearWall['x'] < geometry['throatX']
    wallComparison = {
        'divergingPressure': statistics(wallPressure[diverging] / nearWall['pressure'][diverging] - 1.0),
        'divergingMach': statistics(wallMach[diverging] / nearWall['mach'][diverging] - 1.0),
        'convergingPressureOneDimensional': statistics(wallPressure[converging] / nearWall['pressure'][converging] - 1.0),
        'convergingPressureTransonic': statistics(wallPressure[converging] / nearWall['transonicPressure'][converging] - 1.0),
        'convergingMachOneDimensional': statistics(wallMach[converging] / nearWall['mach'][converging] - 1.0),
        'convergingMachTransonic': statistics(wallMach[converging] / nearWall['transonicMach'][converging] - 1.0),
    }

    # -- Field -- #
    latestField = os.path.join(case, latest)
    centers = readInternalField(os.path.join(case, '0', 'C'))
    temperature = readInternalField(os.path.join(latestField, 'TMean'))
    velocity = readInternalField(os.path.join(latestField, 'UMean'))
    cellX, cellR = centers[:, 0], np.hypot(centers[:, 1], centers[:, 2]) / toRadius
    cellMach = machNumber(velocity, temperature, gas)
    radialVelocity = (velocity[:, 1] * centers[:, 1] + velocity[:, 2] * centers[:, 2]) / np.hypot(centers[:, 1], centers[:, 2])
    cellAngle = np.arctan2(radialVelocity, velocity[:, 0])

    # The wall faces, the exit faces and the axis line close the field out to the boundary. The
    # cells nearest the axis are prisms whose centers sit two thirds of a cell off it.
    order = np.argsort(outlet['r'])
    pointX = np.concatenate([cellX, wall['x'], outlet['x'][order], axis['x']])
    pointR = np.concatenate([cellR, wall['r'], outlet['r'][order], np.zeros_like(axis['x'])])
    pointMach = np.concatenate([cellMach, wall['Ma'], outlet['Ma'][order], axis['mach']])
    # Face centers sit on the mid-plane, where the radial velocity is the y component
    wallAngle = np.arctan2(wall['U'][:, 1], wall['U'][:, 0])
    outletAngle = np.arctan2(outlet['U'][order, 1], outlet['U'][order, 0])
    pointAngle = np.concatenate([cellAngle, wallAngle, outletAngle, np.zeros_like(axis['x'])])
    triangulation, interpolate = fieldInterpolator(pointX, pointR, wallX, wallR)
    fieldMachError = interpolate(pointMach, characteristics['x'], characteristics['r']) / characteristics['mach'] - 1.0
    fieldAngleError = np.degrees(interpolate(pointAngle, characteristics['x'], characteristics['r'])
                                 - characteristics['flowAngle'])
    nearThroat = characteristics['x'] <= geometry['throatX'] + throatRadius

    # -- Total pressure and temperature, which an inviscid adiabatic steady flow conserves -- #
    pressure = readInternalField(os.path.join(latestField, 'pMean'))
    stagnation = 1.0 + 0.5 * (gamma - 1.0) * cellMach**2
    totalPressure = pressure * stagnation**(gamma / (gamma - 1.0)) / chamberPressure
    totalTemperature = temperature * stagnation / gas['stagnationTemperature']
    height = cellR / np.interp(cellX, wallX, wallR)
    rows = {'wallRow': height > 1.0 - 1.0 / settings['radialCells'],
            'secondRow': (height > 1.0 - 2.0 / settings['radialCells']) & (height <= 1.0 - 1.0 / settings['radialCells']),
            'interior': height <= 0.9}
    behindThroat = cellX > geometry['throatX'] + throatRadius
    conservation = {name: {'totalPressureMean': float(totalPressure[row & behindThroat].mean()),
                           'totalPressureMin': float(totalPressure[row & behindThroat].min()),
                           'totalTemperatureMean': float(totalTemperature[row & behindThroat].mean())}
                    for name, row in rows.items()}

    # -- Judgement -- #
    measured = {
        'vacuumThrustCoefficient': exitPlane['vacuumThrustCoefficient']['difference'],
        'massFlow': exitPlane['massFlow']['difference'],
        'thrustPerMassFlow': exitPlane['thrustPerMassFlow']['difference'],
        'exitMassAveragedMach': exitPlane['exitMassAveragedMach']['difference'],
        'centerlineMachMax': statistics(centerlineError)['max'],
        'divergingWallPressureMax': wallComparison['divergingPressure']['max'],
        'fieldMach95': statistics(fieldMachError)['p95'],
        'massImbalance': imbalance,
        'meanDrift': meanDrift,
    }
    judged = {key: {'value': float(value), 'limit': criteria[key], 'pass': bool(abs(value) <= criteria[key])}
              for key, value in measured.items()}

    results = {
        'case': os.path.basename(os.path.abspath(case)), 'resolution': settings['resolution'], 'cells': settings['cells'],
        'time': float(latest), 'averageStart': settings['averageStart'],
        'exitPlane': exitPlane,
        'dischargeCoefficient': {'openFoam': ours['massFlow'] / reference['performance']['chokedMassFlow'],
                                 'nova': theirs['massFlow'] / reference['performance']['chokedMassFlow'],
                                 'chokedMassFlow': reference['performance']['chokedMassFlow'],
                                 'entrantArc': throatDischargeCoefficients(gamma, reference['config']['throatInletCurvature']),
                                 'exitArc': throatDischargeCoefficients(gamma, reference['config']['throatOutletCurvature'])},
        'designThrustCoefficient': {
            'openFoam': ours['vacuumThrustCoefficient'] - reference['performance']['designExitPressure']
                        * (exitRadius / throatRadius)**2 / chamberPressure,
            'nova': reference['performance']['thrustCoefficient']},
        'steadiness': {'massImbalance': imbalance, 'meanDrift': meanDrift, 'window': window},
        'centerlineMach': statistics(centerlineError),
        'wall': wallComparison,
        'fieldMach': statistics(fieldMachError),
        'fieldFlowAngleDegrees': statistics(fieldAngleError),
        # More than half the characteristic nodes lie within one throat radius of the throat, in
        # the transonic start, so the whole-field statistics are weighted toward it
        'fieldMachNearThroat': statistics(fieldMachError[nearThroat]),
        'fieldMachDownstream': statistics(fieldMachError[~nearThroat]),
        'fieldFlowAngleDegreesDownstream': statistics(fieldAngleError[~nearThroat]),
        'centerlineMachDownstream': statistics(centerlineError[axisNodes['x'] > geometry['throatX'] + throatRadius]),
        # Total pressure over chamber pressure and total temperature over the chamber's, in the
        # cells against the wall, the row behind them and the interior, from one throat radius past
        # the throat to the exit
        'conservation': conservation,
        'criteria': judged,
        'allPass': all(entry['pass'] for entry in judged.values()),
    }
    with open(os.path.join(output, 'comparison.json'), 'w', encoding = 'utf-8') as handle:
        json.dump(results, handle, indent = 2)

    # -- Figures -- #
    wallLine = (wallX, wallR)
    drawFields(os.path.join(output, 'machField.png'), {'mach': pointMach}, characteristics, wallLine, style, triangulation)
    drawFieldError(os.path.join(output, 'machFieldDifference.png'), characteristics, fieldMachError, wallLine, style)
    drawCenterline(os.path.join(output, 'centerline.png'), axis, axisNodes, centerlineError, throatRadius)
    drawWall(os.path.join(output, 'wall.png'), wall, nearWall, chamberPressure, throatRadius)
    drawTotalPressure(os.path.join(output, 'totalPressure.png'), cellX, totalPressure, rows, throatRadius)
    drawExitPlane(os.path.join(output, 'exitPlane.png'), outlet, reference)
    drawConvergence(os.path.join(output, 'massFlow.png'), histories['inletMassFlow'], histories['outletMassFlow'],
                    theirs['massFlow'], settings['averageStart'])

    return results

def report(results: dict) -> str:

    '''The comparison as a plain-text table.'''

    lines = [f"{results['resolution']} grid, {results['cells']} cells, t = {results['time']:g} s", '',
             f"{'quantity':28s} {'OpenFOAM':>14s} {'NOVA':>14s} {'difference':>11s} {'NOVA profile':>14s} {'difference':>11s}"]
    for key, entry in results['exitPlane'].items():
        lines.append(f"{key:28s} {entry['openFoam']:14.6g} {entry['nova']:14.6g} {entry['difference'] * 100:10.3f}% "
                     f"{entry['novaProfile']:14.6g} {entry['differenceFromProfile'] * 100:10.3f}%")
    discharge = results['dischargeCoefficient']
    lines.append(f"{'dischargeCoefficient':28s} {discharge['openFoam']:14.6g} {discharge['nova']:14.6g}")
    lines.append(f"  Kliegel-Levine, entrant arc {discharge['entrantArc']['kliegelLevine']:.5f}, "
                 f"exit arc {discharge['exitArc']['kliegelLevine']:.5f}; Hall, entrant arc {discharge['entrantArc']['hall']:.5f}")
    lines += ['', f"{'criterion':28s} {'value':>11s} {'limit':>11s}  result"]
    for key, entry in results['criteria'].items():
        lines.append(f"{key:28s} {entry['value'] * 100:10.3f}% {entry['limit'] * 100:10.3f}%  "
                     f"{'pass' if entry['pass'] else 'FAIL'}")
    window = results['steadiness']['window']
    lines += ['', 'oscillation over the averaging window, standard deviation over mean: '
              + ', '.join(f"{key} {entry['oscillation'] * 100:.3f}%" for key, entry in window.items())]
    for key in ('fieldMachNearThroat', 'fieldMachDownstream', 'centerlineMachDownstream'):
        entry = results[key]
        lines.append(f"{key:28s} mean {entry['mean'] * 100:.3f}%  p95 {entry['p95'] * 100:.3f}%  "
                     f"max {entry['max'] * 100:.3f}%  ({entry['count']} nodes)")
    wall = results['wall']['divergingPressure']
    lines.append(f"{'divergingWallPressure':28s} mean {wall['mean'] * 100:.3f}%  p95 {wall['p95'] * 100:.3f}%  "
                 f"max {wall['max'] * 100:.3f}%")
    for name, entry in results['conservation'].items():
        lines.append(f"{name:28s} total pressure mean {entry['totalPressureMean']:.4f} min {entry['totalPressureMin']:.4f}, "
                     f"total temperature mean {entry['totalTemperatureMean']:.5f}")

    return '\n'.join(lines)

if __name__ == '__main__':
    print(report(compare(sys.argv[1] if len(sys.argv) > 1 else '.')))
