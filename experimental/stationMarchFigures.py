
# -- Figures for the station marching plume solver -- #

'''

What the station marcher gives that the characteristic march does not.

Five panels, each answering one question about the scheme:

    the boundary      the jet boundary from both solvers on the same weakly underexpanded case,
                      against Prandtl's cell length, which is the like-for-like check
    the pattern       the boundary over the pressure ratios the scheme is staged against, showing
                      where the reach ends and how the amplitude grows
    conservation      mass drift along the axis for each ratio, which is where the accuracy of the
                      scheme is read
    the interior      the Mach field as a filled contour, which is the output the scheme exists for
                      and which a scattered characteristic net cannot draw directly
    the divergence    cell period against exit divergence angle, which TR R-6 measures as a small
                      effect and the characteristic march makes a dominant one

Run it from the NOVA root:

    python experimental/stationMarchFigures.py

It writes `stationMarchBoundary.png`, `stationMarchField.png` and `stationMarchDivergence.png`
beside itself.

Author: Sean Bowman

'''

import math
import os
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(here), 'src'))
sys.path.insert(0, here)

from NOVA.plume import (PlumeFlow, PlumePoint, fullyExpandedDiameter, prandtlCellCoefficient,
                        shockCellLength, solvePlumeMarch)
from stationMarch import conicalStation, solveStationMarch, uniformStation

GAMMA = 1.2
GASCONSTANT = 320.0
STAGNATIONTEMPERATURE = 3000.0
STAGNATIONPRESSURE = 2.0e6
EXITMACH = 3.0
RADIALPOINTS = 81
REACH = 26.0
RATIOS = (1.05, 1.2, 1.5, 2.0)

# First zero of the Bessel function of the first kind of order zero, which sets the linear cell.
BESSELFIRSTZERO = 2.404825557695773

background = '#1a1e2a'
panel      = '#222735'
copper     = '#E0975A'
green      = '#86C06C'
ink        = '#E8E6E1'
muted      = '#8B93A7'
warn       = '#E8A0A0'
blue       = '#6BA3D6'

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': '#333A4D',
    'axes.grid': False, 'font.size': 9,
    'axes.titlesize': 12, 'axes.titleweight': 'bold', 'legend.framealpha': 0.0,
})

def referenceFlow() -> PlumeFlow:

    '''The gas every panel runs in.'''

    return PlumeFlow(GAMMA, GASCONSTANT, STAGNATIONTEMPERATURE, STAGNATIONPRESSURE)

def linearCellLength(mach: float, radius: float = 1.0) -> float:

    '''

    Cell length of the linearized axisymmetric jet, `2 pi sqrt(M^2 - 1) r / j1`.

    The small-disturbance solution of a slightly underexpanded jet is periodic in the axial
    coordinate with this period, independent of the pressure ratio. It is the limit the measured
    period has to approach as the jet is made weaker, which is what makes it usable as a reference.

    '''

    return 2.0*math.pi*math.sqrt(mach**2 - 1.0)*radius/BESSELFIRSTZERO

def prandtlCellLength(flow: PlumeFlow, ratio: float, lipRadius: float = 1.0) -> float:

    '''

    Prandtl's cell length at this operating point, on the fully expanded jet.

    This is the reference the characteristic march was held to, so measuring against it keeps the
    two comparable. Both arguments to the correlation have to be fully expanded values, which is
    why the jet Mach number is taken from the ambient pressure rather than from the exit.

    '''

    jetMach = flow.machFromStaticPressure(flow.staticPressure(EXITMACH)/ratio)
    diameter = fullyExpandedDiameter(2.0*lipRadius, EXITMACH, jetMach, flow.gamma)

    return shockCellLength(diameter, jetMach, prandtlCellCoefficient)

def crests(x, radius) -> list:

    '''Interior maxima of a boundary trace.'''

    return [(x[index], radius[index]) for index in range(1, len(radius) - 1)
            if radius[index] >= radius[index - 1] and radius[index] > radius[index + 1]]

def stationSolution(flow: PlumeFlow, ratio: float, reach: float = REACH) -> dict:

    '''The station march at one pressure ratio.'''

    station = uniformStation(flow, EXITMACH, 1.0, RADIALPOINTS)
    result = solveStationMarch(flow, station, flow.staticPressure(EXITMACH)/ratio,
                               maxLength = reach, maxStations = 40000)
    result['boundaryTrace'] = np.array(result['boundary'])

    return result

def characteristicSolution(flow: PlumeFlow, ratio: float) -> dict:

    '''The characteristic march on the same case, for the boundary comparison.'''

    radii = np.linspace(1.0, 0.0, 41)
    line = [PlumePoint(0.0, float(radius), EXITMACH, 0.0, flow, 'exit') for radius in radii]
    result = solvePlumeMarch(flow, line, flow.staticPressure(EXITMACH)/ratio,
                             numRays = 120, maxLines = 4000)
    result['boundaryTrace'] = np.array([(point.x, point.r) for point in result['boundary']])

    return result

def fieldGrid(result: dict):

    '''The solved stations as a structured grid, station by radial fraction.'''

    stations = result['stations']
    fractions = stations[0].radius/stations[0].boundaryRadius
    x = np.array([[station.x]*fractions.size for station in stations])
    radius = np.array([station.radius for station in stations])
    mach = np.array([station.mach for station in stations])

    return x, radius, mach

def boundaryFigure(flow: PlumeFlow, solutions: dict, characteristic: dict):

    '''The boundary comparison, the pressure ratio family and the conservation trace.'''

    figure, axes = plt.subplots(3, 1, figsize = (9.0, 10.5))
    prandtl = prandtlCellLength(flow, 1.05)

    reference = solutions[1.05]
    trace = reference['boundaryTrace']
    axes[0].plot(trace[:, 0], trace[:, 1], color = copper, linewidth = 2.0,
                 label = 'station march')
    axes[0].plot(characteristic['boundaryTrace'][:, 0], characteristic['boundaryTrace'][:, 1],
                 color = blue, linewidth = 1.2, linestyle = '--',
                 label = 'characteristic march')
    stationCrests = crests(trace[:, 0], trace[:, 1])
    for index, (crestX, crestRadius) in enumerate(stationCrests[:3]):
        axes[0].plot([crestX], [crestRadius], marker = 'o', markersize = 4, color = ink)
        axes[0].annotate(f'{crestX:.2f}', (crestX, crestRadius), textcoords = 'offset points',
                         xytext = (0, 8), ha = 'center', color = muted, fontsize = 8)
    if len(stationCrests) >= 2:
        period = stationCrests[1][0] - stationCrests[0][0]
        axes[0].set_title(f'Jet boundary at Pe/Pa 1.05: period {period:.3f} lip radii, '
                          f'{100.0*(period/prandtl - 1.0):+.2f} per cent on Prandtl '
                          f'({prandtl:.3f})')
    axes[0].set_xlabel('axial distance [lip radii]')
    axes[0].set_ylabel('boundary radius [lip radii]')
    axes[0].legend(loc = 'lower left')

    colors = (green, copper, blue, warn)
    for ratio, color in zip(RATIOS, colors):
        trace = solutions[ratio]['boundaryTrace']
        axes[1].plot(trace[:, 0], trace[:, 1], color = color, linewidth = 1.6,
                     label = f'Pe/Pa {ratio}')
    axes[1].set_title('Boundary against jet static pressure ratio')
    axes[1].set_xlabel('axial distance [lip radii]')
    axes[1].set_ylabel('boundary radius [lip radii]')
    axes[1].legend(loc = 'upper left', bbox_to_anchor = (1.01, 1.0))

    for ratio, color in zip(RATIOS, colors):
        result = solutions[ratio]
        x = np.array([station.x for station in result['stations']])
        axes[2].plot(x, np.array(result['massDrift']), color = color, linewidth = 1.4,
                     label = f'Pe/Pa {ratio}')
    axes[2].axhline(0.0, color = muted, linewidth = 0.8)
    axes[2].set_title('Axial mass flow departure from the exit plane')
    axes[2].set_xlabel('axial distance [lip radii]')
    axes[2].set_ylabel('mass drift [per cent]')
    axes[2].legend(loc = 'upper left', bbox_to_anchor = (1.01, 1.0))

    figure.tight_layout()

    return figure

def fieldFigure(solutions: dict):

    '''The interior Mach field at two pressure ratios, mirrored about the axis.'''

    figure, axes = plt.subplots(2, 1, figsize = (13.0, 5.6))

    for axis, ratio in zip(axes, (1.05, 1.5)):
        x, radius, mach = fieldGrid(solutions[ratio])
        levels = np.linspace(mach.min(), mach.max(), 40)
        filled = None
        for sign in (1.0, -1.0):
            filled = axis.contourf(x, sign*radius, mach, levels = levels, cmap = 'magma')
        boundary = solutions[ratio]['boundaryTrace']
        for sign in (1.0, -1.0):
            axis.plot(boundary[:, 0], sign*boundary[:, 1], color = ink, linewidth = 1.0)
        axis.set_title(f'Mach number in the plume interior, Pe/Pa {ratio}')
        axis.set_xlabel('axial distance [lip radii]')
        axis.set_ylabel('radius [lip radii]')
        axis.set_aspect('equal')
        bar = figure.colorbar(filled, ax = axis, pad = 0.015, fraction = 0.02)
        bar.set_ticks(np.linspace(mach.min(), mach.max(), 5))
        bar.ax.tick_params(labelsize = 8)

    figure.tight_layout()

    return figure

def divergenceFigure(flow: PlumeFlow, angles = (0.0, 5.0, 11.0, 14.0, 20.0)):

    '''

    Cell period against exit divergence angle, which TR R-6 measures as a small effect.

    The exit is a conical source flow at Pe/Pa 1.05 with the lip held at the reference Mach number,
    so the divergence angle is the only thing that changes. The characteristic march reads -24.6
    per cent at 5 degrees and -34.3 at 11 on the same question, measured lip to first crest, and
    the left panel shows why the two measures disagree: divergence throws the first crest forward
    without moving the period.

    '''

    figure, axes = plt.subplots(1, 2, figsize = (12.0, 4.4))
    colors = (green, copper, blue, warn, muted)

    periods, firstCrests, drifts, solved = [], [], [], []
    for degrees in angles:
        station = conicalStation(flow, EXITMACH, math.radians(degrees), 1.0, RADIALPOINTS)
        ambient = flow.staticPressure(float(station.mach[-1]))/1.05
        result = solveStationMarch(flow, station, ambient, maxLength = REACH,
                                   maxStations = 40000)
        trace = np.array(result['boundary'])
        found = crests(trace[:, 0], trace[:, 1])
        drift = np.array(result['massDrift'])
        periods.append(found[1][0] - found[0][0] if len(found) >= 2 else float('nan'))
        firstCrests.append(found[0][0] if found else float('nan'))
        drifts.append(abs(drift[np.argmax(np.abs(drift))]))
        solved.append((degrees, trace))

    for (degrees, trace), color in zip(solved, colors):
        axes[0].plot(trace[:, 0], trace[:, 1], color = color, linewidth = 1.5,
                     label = f'{degrees:.0f} deg')
    axes[0].set_title('Jet boundary against exit divergence')
    axes[0].set_xlabel('axial distance [lip radii]')
    axes[0].set_ylabel('boundary radius [lip radii]')
    # The 20 degree march collapses at 15.8 lip radii, which would otherwise set the scale.
    axes[0].set_ylim(0.75, 1.45)
    axes[0].legend(loc = 'lower right', fontsize = 8, ncol = 5, columnspacing = 0.8,
                   handlelength = 1.2)

    reference = periods[0]
    shift = [100.0*(period/reference - 1.0) for period in periods]
    crestShift = [100.0*(crest/firstCrests[0] - 1.0) for crest in firstCrests]
    axes[1].plot(angles, shift, color = copper, marker = 'o', linewidth = 1.6,
                 label = 'period, crest to crest')
    axes[1].plot(angles, crestShift, color = muted, marker = 's', linewidth = 1.2,
                 linestyle = '--', label = 'lip to first crest')
    axes[1].plot([5.0, 11.0], [-24.6, -34.3], color = blue, marker = '^', linewidth = 1.2,
                 linestyle = ':', label = 'characteristic march')
    axes[1].axhline(0.0, color = muted, linewidth = 0.8)
    for degrees, value, drift in zip(angles, shift, drifts):
        if drift > 1.0:
            axes[1].annotate(f'{drift:.0f}% drift', (degrees, value),
                             textcoords = 'offset points', xytext = (0, -16), ha = 'center',
                             color = warn, fontsize = 8)
    axes[1].set_title('Shock cell length against exit divergence')
    axes[1].set_xlabel('exit divergence [deg]')
    axes[1].set_ylabel('change from a parallel exit [per cent]')
    axes[1].legend(loc = 'lower left', fontsize = 8)

    figure.tight_layout()

    return figure

def save(figure, name: str) -> str:

    '''Write a figure beside this module.'''

    path = os.path.join(here, name)
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print(f'  wrote {name}')

    return path

def build() -> None:

    '''Solve every case and write both figures.'''

    flow = referenceFlow()

    solutions = {}
    for ratio in RATIOS:
        print(f'  solving Pe/Pa {ratio}')
        solutions[ratio] = stationSolution(flow, ratio)

    print('  solving the characteristic march at Pe/Pa 1.05')
    characteristic = characteristicSolution(flow, 1.05)

    save(boundaryFigure(flow, solutions, characteristic), 'stationMarchBoundary.png')
    save(fieldFigure(solutions), 'stationMarchField.png')

    print('  solving the divergence sweep')
    save(divergenceFigure(flow), 'stationMarchDivergence.png')

if __name__ == '__main__':
    build()
