'''
Grid convergence of the plume march.

Three discretisations set the solution and they are varied one at a time, because a sweep that
moves them together cannot say which one the answer depends on:

    numRays      how finely the centred fan at the lip is cut
    exitPoints   how finely the exit plane data line is sampled
    lineLimit    how many points a characteristic line is held to

Two quantities are reported. The shock cell period is what the solver is validated on, against
Prandtl (1904), and it is only meaningful at a parallel exit near design, which is the case run
here. Mass drift is the solver's own consistency: every line spans the jet, so every line carries
the same mass flow, and the departure from that needs no reference at all. A converged answer has
to hold both.
'''
import os
import sys
import time

import numpy as np

from NOVA.Nozzle import (PlumeFlow, PlumePoint, solvePlumeMarch, shockCellLength,   # noqa: E402
                    fullyExpandedDiameter, machFromPressureRatio, prandtlCellCoefficient)

GAMMA, GAS_CONSTANT, STAGNATION_TEMPERATURE, STAGNATION_PRESSURE = 1.4, 287.0, 300.0, 1.0e6
EXIT_MACH, PRESSURE_RATIO = 3.0, 1.05

flow = PlumeFlow(GAMMA, GAS_CONSTANT, STAGNATION_TEMPERATURE, STAGNATION_PRESSURE)

def exitLine(count):
    '''Uniform parallel exit, which is the case Prandtl's cell length is derived for.'''
    return [PlumePoint(0.0, radius, EXIT_MACH, 0.0, flow, 'exit')
            for radius in np.linspace(1.0, 0.0, count)]

def prandtlCell():
    stagnationOverStatic = (1.0 + 0.5 * (GAMMA - 1.0) * EXIT_MACH ** 2) ** (GAMMA / (GAMMA - 1.0))
    jetMach = machFromPressureRatio(stagnationOverStatic * PRESSURE_RATIO, GAMMA)
    return shockCellLength(fullyExpandedDiameter(2.0, EXIT_MACH, jetMach, GAMMA), jetMach,
                           prandtlCellCoefficient)

def measure(numRays, exitPoints, lineLimit, maxLines = 4000):
    '''Cell period and mass drift for one discretisation.'''
    started = time.time()
    net = solvePlumeMarch(flow, exitLine(exitPoints),
                          flow.staticPressure(EXIT_MACH) / PRESSURE_RATIO,
                          numRays = numRays, maxLines = maxLines, lineLimit = lineLimit)
    boundary = net['boundary']
    xs = np.array([point.x for point in boundary])
    rs = np.array([point.r for point in boundary])
    expected = prandtlCell()

    window = max(5, rs.size // 200)
    smoothed = np.convolve(rs, np.ones(window) / window, mode = 'same')
    crests = []
    for index in range(window, smoothed.size - window - 1):
        if smoothed[index] >= smoothed[index - window:index].max() \
                and smoothed[index] > smoothed[index + 1:index + 1 + window].max():
            if not crests or xs[index] - xs[crests[-1]] > 0.4 * expected:
                crests.append(index)
    period = float(np.diff(xs[crests]).mean()) if len(crests) >= 2 else float('nan')
    return {'period': period, 'cells': len(crests), 'reach': xs[-1],
            'drift': net['massDriftWorst'], 'stop': net['stop'],
            'seconds': time.time() - started}

def sweep(label, cases):
    print(f'\n== {label} ==', flush = True)
    print(f'{"rays":>6s} {"exitPts":>8s} {"limit":>6s} {"cells":>6s} {"reach":>8s} '
          f'{"period":>8s} {"vs Prandtl":>11s} {"massDrift%":>11s} {"stop":20s} {"s":>5s}',
          flush = True)
    expected = prandtlCell()
    for numRays, exitPoints, lineLimit in cases:
        result = measure(numRays, exitPoints, lineLimit)
        error = 100.0 * (result['period'] - expected) / expected
        print(f'{numRays:6d} {exitPoints:8d} {lineLimit:6d} {result["cells"]:6d} '
              f'{result["reach"]:8.2f} {result["period"]:8.4f} {error:+11.2f} '
              f'{result["drift"]:+11.3f} {result["stop"]:20s} {result["seconds"]:5.0f}',
              flush = True)

def main():
    print(f'Plume march grid convergence: Me {EXIT_MACH}, Pe/Pa {PRESSURE_RATIO}, parallel exit')
    print(f'Prandtl first cell {prandtlCell():.4f} lip radii')
    sweep('lip fan resolution', [(40, 140, 250), (80, 140, 250), (160, 140, 250),
                                 (320, 140, 250)])
    sweep('exit plane sampling', [(120, 70, 250), (120, 140, 250), (120, 280, 250),
                                  (120, 560, 250)])
    sweep('line budget', [(120, 140, 125), (120, 140, 250), (120, 140, 500),
                          (120, 140, 1000)])

if __name__ == '__main__':
    main()
