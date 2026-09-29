# -- The ambient pressures the station marcher can and cannot take -- #

'''

The shipped nozzle's plume marched across a range of back pressures, to find where the scheme works
and where it stops working.

Two limits bound it and they are different in kind.

The lower limit is a refusal. `solveStationMarch` sets its free boundary from the ambient pressure,
and if the boundary Mach number does not exceed the lip Mach number it returns `notUnderexpanded`
without marching a single station. Physically that is right: below a lip ratio of one the jet has to
be compressed to reach ambient, which means an oblique shock off the lip, and an isentropic scheme
has no way to write one down. The refusal is loud and immediate.

The upper limit is not a refusal, and that is the problem with it. Past a lip ratio somewhere above
1.5 the march still runs to its requested length and still reports `maxLength`, while losing most of
the mass flow. Nothing in the return value says the answer is worthless. Only the conservation check
does.

The band between them is narrow. Everything outside it either refuses or lies, and the figure marks
which is which.

Note which pressure ratio is meant throughout. The march's boundary condition is applied at the lip,
so the lip ratio is what governs it. The one-dimensional ratio the correlations use is a different
number on a truncated contour, smaller here by a factor of 1.76, and both are printed.

Run it from the NOVA root, after `python featureShowcase/runBaseCase.py` has written the pickle:

    python experimental/stationMarchAmbientSweep.py

Author: Sean Bowman

'''

import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'src'))
sys.path.insert(0, here)

from NOVA.plume import (PlumeFlow, plumeCharacteristicSeed, plumeExitLine, solvePlumeStructure,
                        separationPressureRatio)
from stationMarch import lipShockLossLimit, solveStationMarch, stationFromLine
from stationMarchNozzleField import copper, green, ink, muted, panel, warn

REACH = 12.0               # [-], axial distance marched, in lip radii
RADIALPOINTS = 121         # [-], points across each station
MAXSTATIONS = 300000       # [-], ceiling before a march is abandoned
PANELRATIOS = (0.60, 0.75, 1.30, 1.60, 1.90, 4.93)   # [-], lip ratios drawn as fields
SAMPLES = (2.0, 6.0, 12.0)  # [-], reaches the drift is reported at
SWEEPRATIOS = (0.55, 0.60, 0.65, 0.704, 0.75, 0.85, 0.95, 1.02, 1.10, 1.30, 1.50,
               1.60, 1.70, 1.80, 1.90, 2.00, 2.50, 3.00, 4.00, 4.93)
TOLERABLE = 2.0            # [%], mass drift a result is called usable below
def setUp(nozzle):

    '''The flow, the exit station and the two reference pressures, solved once.'''

    seed = plumeCharacteristicSeed(nozzle.plumeContour())
    flow = PlumeFlow(seed['gamma'], seed['gasConstant'], seed['stagnationTemperature'],
                     seed['stagnationPressure'])
    station = stationFromLine(plumeExitLine(flow, seed, numPoints = 400), RADIALPOINTS)
    lipPressure = flow.staticPressure(float(station.mach[-1]))
    oneDimensional = solvePlumeStructure(nozzle.plumeContour(), lipPressure).exitPressure

    return flow, station, lipPressure, oneDimensional

def marchAt(flow, station, lipPressure, ratio):

    '''One march at a lip ratio, with the numbers the figure needs.'''

    ambient = lipPressure/ratio
    result = solveStationMarch(flow, station, ambient, maxLength = REACH,
                               maxStations = MAXSTATIONS)
    stations = result['stations']
    axial = (np.array([one.x for one in stations]) - station.x)/station.boundaryRadius
    drift = np.array(result['massDrift'])
    refused = len(stations) <= 1

    radius = np.array([one.radius for one in stations])/station.boundaryRadius
    axisMach = np.array([float(one.mach[0]) for one in stations])
    sampled = {target: (float(np.interp(target, axial, drift))
                        if axial[-1] >= target - 1e-6 else np.nan)
               for target in SAMPLES}

    # The minimum jet radius is the tell for the first of the two high-ratio failures. A real jet
    # necks between cells; a boundary that collapses onto the axis has come apart, and once it does
    # the axisymmetric source term carries a 1/r that finishes the march off.
    return {'ratio': ratio, 'ambient': ambient, 'stop': result['stop'], 'refused': refused,
            'reach': float(axial[-1]), 'axial': axial, 'drift': drift, 'sampled': sampled,
            'worst': float(drift[np.argmax(np.abs(drift))]),
            'lipShockLoss': float(result.get('lipShockLoss', 0.0)),
            'minBoundary': float(radius[:, -1].min()),
            'axisTouched': bool(axisMach.min() < 0.98*axisMach[0]),
            'radius': radius, 'mach': np.array([one.mach for one in stations]),
            'boundaryMach': result['boundaryMach']}

def drawField(axes, case, machLimits):

    '''One plume, or the reason there is not one.'''

    if case['refused']:
        axes.set_facecolor(panel)
        axes.text(0.5, 0.56, 'REFUSED', transform = axes.transAxes, ha = 'center',
                  va = 'center', fontsize = 15, color = warn, fontweight = 'bold')
        reasons = {
            'lipShockTooStrong':
                f'lipShockTooStrong\nthe lip shock this stands in for would destroy'
                f' {100.0*case["lipShockLoss"]:.1f} per cent\nof the stagnation pressure, past the {100.0*lipShockLossLimit:.0f} per cent\nan isentropic turn may be'
                f' substituted for',
            'lipShockDetached':
                'lipShockDetached\nthe turn the lip demands is past an attached oblique '
                'shock',
            'boundaryNotSupersonic':
                'boundaryNotSupersonic\nambient puts the free boundary at or below Mach 1'}
        axes.text(0.5, 0.32, reasons.get(case['stop'], case['stop']),
                  transform = axes.transAxes, ha = 'center', va = 'center', fontsize = 8,
                  color = muted)
    else:
        grid = np.repeat(case['axial'][:, None], case['radius'].shape[1], axis = 1)
        levels = np.linspace(machLimits[0], machLimits[1], 120)
        for sign in (1.0, -1.0):
            axes.contourf(grid, sign*case['radius'], case['mach'], levels = levels,
                          cmap = 'viridis', extend = 'both')
            axes.plot(case['axial'], sign*case['radius'][:, -1], color = ink, lw = 1.1)
        axes.axhline(0.0, color = muted, lw = 0.6, ls = '-.')

    axes.set_xlim(0.0, REACH)
    axes.set_ylim(-2.6, 2.6)
    axes.set_xticks(np.arange(0.0, REACH + 0.1, 2.0))
    axes.set_yticks([-2, 0, 2])
    axes.tick_params(labelsize = 8)

def build():

    with open(os.path.join(root, 'featureShowcase', 'showcaseBase.pkl'), 'rb') as handle:
        nozzle = pickle.load(handle)

    flow, station, lipPressure, oneDimensional = setUp(nozzle)
    convention = lipPressure/oneDimensional
    separationAmbient = oneDimensional/separationPressureRatio

    print(f'  lip static {lipPressure:.0f} Pa, one-dimensional exit static {oneDimensional:.0f} Pa, '
          f'ratio {convention:.3f}')
    print(f'  a compressed lip is admitted while the shock it replaces costs under '
          f'{100.0*lipShockLossLimit:.0f} per cent of the stagnation pressure')
    print(f'  Summerfield separation at one-dimensional Pe/Pa {separationPressureRatio:.2f} is '
          f'{separationAmbient:.0f} Pa ambient')
    print()
    print('  lipRatio   ambient  1D Pe/Pa  stop                  loss%  drift@2  drift@6 drift@12   minR')

    sweep = []
    for ratio in sorted(set(SWEEPRATIOS) | set(PANELRATIOS)):
        case = marchAt(flow, station, lipPressure, ratio)
        sweep.append(case)
        print(f'  {ratio:8.2f}  {case["ambient"]:8.0f}  {oneDimensional/case["ambient"]:8.3f}  '
              f'{case["stop"]:<19s}  {100.0*case["lipShockLoss"]:5.2f}  '
              f'{case["sampled"][2.0]:+7.2f}  {case["sampled"][6.0]:+7.2f}  '
              f'{case["sampled"][12.0]:+7.2f}  {case["minBoundary"]:5.3f}', flush = True)

    panels = [next(c for c in sweep if abs(c['ratio'] - r) < 1e-9) for r in PANELRATIOS]
    solved = [c for c in panels if not c['refused']]
    machLimits = (min(float(c['mach'].min()) for c in solved),
                  max(float(c['mach'].max()) for c in solved))

    figure = plt.figure(figsize = (16.0, 12.0))
    grid = figure.add_gridspec(4, 3, height_ratios = [1.0, 1.0, 0.12, 1.25], hspace = 0.42,
                               wspace = 0.14)

    for index, case in enumerate(panels):
        axes = figure.add_subplot(grid[index//3, index % 3])
        drawField(axes, case, machLimits)
        headline = ('refused' if case['refused']
                    else f'drift {case["sampled"][2.0]:+.2f} % at 2 radii, '
                         f'{case["sampled"][12.0]:+.1f} % at 12')
        colour = (warn if case['refused'] or abs(case['sampled'][12.0]) > TOLERABLE
                  else green)
        axes.set_title(f'lip ratio {case["ratio"]:.2f}   ambient {case["ambient"]/1000.0:.1f} kPa   '
                       f'1-D Pe/Pa {oneDimensional/case["ambient"]:.2f}\n{headline}',
                       fontsize = 9.5, color = colour, pad = 6)
        if index % 3 == 0:
            axes.set_ylabel('Radius [lip radii]', fontsize = 8.5)
        if index//3 == 1:
            axes.set_xlabel('Lip radii downstream', fontsize = 8.5)

    summary = figure.add_subplot(grid[3, :])
    ratios = np.array([c['ratio'] for c in sweep])

    refusedRatios = [c['ratio'] for c in sweep if c['refused']]
    if refusedRatios:
        edge = max(refusedRatios)
        summary.axvspan(ratios.min(), edge, color = warn, alpha = 0.16)
        summary.text(0.5*(ratios.min() + edge), 16.0,
                     'refused:\nlip shock too strong', ha = 'center', va = 'top',
                     fontsize = 8.5, color = warn)
        summary.axvline(edge, color = warn, lw = 1.4)

    # The band is quoted per reach, because there is no single answer: how far the march can be
    # trusted and how hard the jet is driven trade against each other.
    bands = {}
    for target in SAMPLES:
        good = [c['ratio'] for c in sweep
                if not c['refused'] and abs(c['sampled'][target]) <= TOLERABLE]
        bands[target] = (min(good), max(good)) if good else None

    if bands[12.0]:
        summary.axvspan(bands[12.0][0], bands[12.0][1], color = green, alpha = 0.16)
    # The collapse is not one band. It happens on the compressed side and again well into the
    # underexpanded side with a healthy stretch between, so each run gets its own shading.
    healthy = {c['ratio'] for c in sweep if not c['refused'] and c['minBoundary'] >= 0.5}
    collapsed = [c['ratio'] for c in sweep if not c['refused'] and c['minBoundary'] < 0.5]
    runs = []
    for value in collapsed:
        if runs and not any(runs[-1][-1] < other < value for other in healthy):
            runs[-1].append(value)
        else:
            runs.append([value])
    for order, run in enumerate(runs):
        summary.axvspan(min(run), max(run), color = warn, alpha = 0.10)
        if order == len(runs) - 1:
            summary.text(0.5*(min(run) + max(run)), 16.0,
                         'jet boundary collapses\nonto the axis', ha = 'center',
                         va = 'top', fontsize = 8.5, color = warn)

    styles = ((2.0, ink, 's--'), (6.0, copper, '^-'), (12.0, warn, 'o-'))
    for target, colour, style in styles:
        values = np.array([c['sampled'][target] if not c['refused'] else np.nan for c in sweep])
        summary.plot(ratios, values, style, color = colour, lw = 1.7, ms = 4.5,
                     label = f'drift at {target:.0f} lip radii')
    summary.axhline(0.0, color = muted, lw = 0.8)
    for level in (-TOLERABLE, TOLERABLE):
        summary.axhline(level, color = green, lw = 0.9, ls = ':')
    summary.axvline(1.0, color = ink, lw = 1.0, ls = '--')
    summary.text(1.0, 16.0, ' lip ratio 1\n compressed | expanded', ha = 'left',
                 va = 'top', fontsize = 8, color = ink)
    summary.axvline(4.93, color = green, lw = 1.1, ls = '-.')
    summary.text(4.93, -125.0, ' design point', ha = 'left', va = 'bottom', fontsize = 8.5,
                 color = green)

    summary.set_yscale('symlog', linthresh = TOLERABLE, linscale = 0.9)
    summary.set_yticks([-100.0, -30.0, -10.0, -TOLERABLE, 0.0, TOLERABLE, 10.0])
    summary.set_yticklabels(['-100', '-30', '-10', f'-{TOLERABLE:.0f}', '0',
                             f'+{TOLERABLE:.0f}', '+10'])
    summary.set_xlim(ratios.min(), ratios.max())
    summary.set_ylim(-140.0, 22.0)
    summary.set_xlabel('Lip static pressure over ambient [-]')
    summary.set_ylabel('Mass continuity error\n[% of exit mass flow]')
    summary.set_title('How far the march can be trusted, against how hard the jet is driven',
                      fontsize = 11, pad = 6)
    summary.legend(loc = 'lower right', fontsize = 8.5, labelcolor = ink, ncol = 3)

    top = figure.add_axes([0.0, 0.0, 1.0, 1.0], zorder = -1)
    top.axis('off')
    figure.suptitle('The station marcher against ambient pressure, on the shipped NOVA contour',
                    fontsize = 13, y = 0.945)

    figure.text(0.012, 0.055,
                f'The lip ratio is the one that governs the march, because the free boundary is '
                f'applied at the lip. On this truncated contour the lip sits at '
                f'{lipPressure/1000.0:.1f} kPa against {oneDimensional/1000.0:.1f} kPa '
                f'one-dimensionally, a factor of {convention:.2f}, so each panel carries both.\n'
                f'Below a lip ratio of one the jet is compressed rather than expanded to reach '
                f'ambient, which physically means an oblique shock off the lip. The scheme turns '
                f'the flow isentropically instead\nand admits it while that substitution stays '
                f'bounded: the loss the real shock would cost is computed and refused past '
                f'{100.0*lipShockLossLimit:.0f} per cent of the stagnation pressure.\n'
                f'That bound never binds on this nozzle, because the nozzle separates internally '
                f'first. Separation at a one-dimensional Pe/Pa of {separationPressureRatio:.2f} '
                f'is {separationAmbient/1000.0:.1f} kPa ambient, a lip ratio of '
                f'{lipPressure/separationAmbient:.3f},\nwhere the shock would have cost '
                f'{100.0*next(c["lipShockLoss"] for c in sweep if abs(c["ratio"] - 0.704) < 5e-3):.2f} per cent. Every attached condition this engine can reach is therefore admitted.',
                fontsize = 8.5, color = muted, va = 'top')
    design = next(c for c in panels if abs(c['ratio'] - 4.93) < 1e-9)
    # Quoted for the underexpanded run alone, since the compressed side collapses too and
    # its number would otherwise be attributed to the band this sentence describes.
    underexpandedPinch = min(c['minBoundary'] for c in sweep
                             if not c['refused'] and c['ratio'] > 1.0)
    figure.text(0.012, -0.035,
                f'The upper limit is the dangerous one, because it is not a refusal. Past the band '
                f'the march still returns `maxLength`, fills every array and draws a plume, while\n'
                f'the mass flow through the last station bears no relation to the exit plane. '
                f'Nothing in the return value flags it. Two different failures hide behind that\n'
                f'same clean stop: from about 1.8 to 3 the free boundary collapses onto the axis, '
                f'pinching to {underexpandedPinch:.2f} of a '
                f'lip radius at its worst, and above that it does not\ncollapse but sheds mass '
                f'steadily through one long expansion. The design point sits in the second of '
                f'those: at the shipped 5 kPa, a lip ratio of 4.93, the march reports a\nclean '
                f'stop and loses {abs(design["sampled"][12.0]):.0f} per cent of the mass flow '
                f'within {REACH:.0f} lip radii.\n'
                f'The compressed side collapses sooner in reach, not later: at a lip ratio of 0.75 the boundary is down to 0.14 of a lip radius by twelve radii and the drift is\n'
                f'-98 per cent, and at 0.70 the march fails outright with the boundary on the axis. Admitting compression widens which ambients can be asked about. It does\nnot widen how far downstream any of them holds.'
                f'\nWhat survives everywhere is the near field. At two lip radii the drift stays under one per cent at every admitted ratio, compressed and expanded alike,\nso the usable product is a short plume rather than a whole one. Conservation is the only thing that separates the two, which is the argument for keeping it\nwired into the envelope gate rather than reported beside the answer.',
                fontsize = 8.5, color = warn, va = 'top')

    path = os.path.join(here, 'stationMarchAmbientSweep.png')
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print()
    print('  wrote stationMarchAmbientSweep.png')
    for target in SAMPLES:
        span = bands[target]
        print(f'  within {TOLERABLE:.0f} per cent at {target:.0f} lip radii: lip ratio '
              + (f'{span[0]:.2f} to {span[1]:.2f}' if span else 'nowhere'))
    if collapsed:
        print(f'  boundary collapses below half the lip radius at lip ratio '
              f'{min(collapsed):.2f} to {max(collapsed):.2f}')

    return path

if __name__ == '__main__':
    build()
