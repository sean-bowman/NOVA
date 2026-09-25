
# -- Verification of the station marcher against an exact axisymmetric solution -- #

'''

The station marcher held against a spherical source flow, which it must reproduce exactly.

A radial source flow is an exact solution of the steady, isentropic, irrotational axisymmetric
equations: the velocity is purely radial, it depends only on the distance from the origin, and
`rho V R^2` is constant along it. That makes it the one case where every unit process of
`stationMarch` can be handed known data and its own error measured, rather than inferred from a
conservation residual that says a solve is wrong without saying where.

It is a verification, not a validation. It establishes that the discretization solves the equations
it claims to solve and at what order; it says nothing about whether those equations describe a real
plume. The references that do are staged in `stationMarchState.md`.

Three things are measured:

    one point       the error in a single interior or center-line solve against the exact state at
                    the same position, halving the step to recover the order
    a reflected foot
                    the same, for a near-axis point whose first-family foot crosses the center line
                    and is read by symmetry
    a march         interior and axis points marched together with the boundary taken from the
                    exact solution, so the free boundary condition is out of the loop and the
                    remaining drift belongs to the interior scheme

Run it from the NOVA root:

    python experimental/stationMarchVerification.py

All units are mass base SI, angles in radians.

Author: Sean Bowman

'''

import math
import os
import sys

import numpy as np
from scipy.optimize import brentq

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from NOVA.plume import PlumeFlow
from stationMarch import (Station, _axisPoint, _interiorPoint, _samplers, stationMassFlux)

GAMMA = 1.2
GASCONSTANT = 320.0
STAGNATIONTEMPERATURE = 3000.0
STAGNATIONPRESSURE = 2.0e6
REFERENCEMACH = 3.0

def areaMachRatio(mach: float, gamma: float = GAMMA) -> float:

    '''Isentropic area ratio at a Mach number.'''

    return (1.0/mach)*((2.0/(gamma + 1.0))*(1.0 + 0.5*(gamma - 1.0)*mach**2)) \
           ** ((gamma + 1.0)/(2.0*(gamma - 1.0)))

def machFromAreaRatio(ratio: float, gamma: float = GAMMA) -> float:

    '''Supersonic branch of the area-Mach relation.'''

    return brentq(lambda mach: areaMachRatio(mach, gamma) - ratio, 1.0 + 1e-12, 40.0, xtol = 1e-14)

class SourceFlow:

    '''

    Exact radial source flow from the origin, symmetric about the axis.

    The area a streamtube sees grows as the square of the distance from the origin, so the Mach
    number at a point follows from the area-Mach relation at `(R / R*)^2`, and the flow angle is the
    polar angle of the point. Reflection through the axis is exact: the state at a negative radius
    is the state at its magnitude with the flow angle reversed.

    '''

    def __init__(self, machAtUnitRadius: float = REFERENCEMACH):
        self.sonicRadius = 1.0/math.sqrt(areaMachRatio(machAtUnitRadius))

    def mach(self, x: float, radius: float) -> float:
        '''Mach number at a point.'''
        return machFromAreaRatio((math.hypot(x, radius)/self.sonicRadius)**2)

    def flowAngle(self, x: float, radius: float) -> float:
        '''Flow angle at a point, which is its polar angle.'''
        return math.atan2(radius, x)

def referenceFlow() -> PlumeFlow:

    '''The gas the checks run in.'''

    return PlumeFlow(GAMMA, GASCONSTANT, STAGNATIONTEMPERATURE, STAGNATIONPRESSURE)

def exactStation(source: SourceFlow, x: float, radii) -> Station:

    '''A station carrying the exact solution at each radius.'''

    radii = np.asarray(radii, dtype = float)

    return Station(x = x, radius = radii,
                   mach = np.array([source.mach(x, radius) for radius in radii]),
                   flowAngle = np.array([source.flowAngle(x, radius) for radius in radii]))

def exactSamplers(source: SourceFlow, x: float):

    '''Samplers reading the exact solution, so a unit process is measured without interpolation.'''

    return (lambda radius: source.mach(x, abs(float(radius))),
            lambda radius: source.flowAngle(x, abs(float(radius))))

def _order(previous: float, current: float) -> str:

    '''Observed order of accuracy between two successive halvings.'''

    if previous is None or current == 0.0:
        return ''

    return f'{math.log2(abs(previous/current)):9.2f}'

def interiorPointOrder(steps = (0.08, 0.04, 0.02, 0.01, 0.005), stationX: float = 2.0,
                       radius: float = 0.6) -> list:

    '''Error in one interior solve against the exact state, as the step is halved.'''

    source, flow = SourceFlow(), referenceFlow()
    station = exactStation(source, stationX, np.linspace(0.0, 1.2, 201))
    machAt, angleAt = exactSamplers(source, stationX)

    rows = []
    for step in steps:
        newRadius = radius + step*math.tan(source.flowAngle(stationX, radius))
        solved = _interiorPoint(flow, station, machAt, angleAt, stationX + step, newRadius,
                                source.mach(stationX, radius),
                                source.flowAngle(stationX, radius))
        rows.append((step, solved[0] - source.mach(stationX + step, newRadius),
                     solved[1] - source.flowAngle(stationX + step, newRadius)))

    return rows

def axisPointOrder(steps = (0.08, 0.04, 0.02, 0.01, 0.005), stationX: float = 2.0) -> list:

    '''Error in one center-line solve against the exact state, as the step is halved.'''

    source, flow = SourceFlow(), referenceFlow()
    station = exactStation(source, stationX, np.linspace(0.0, 1.2, 201))
    machAt, angleAt = exactSamplers(source, stationX)

    rows = []
    for step in steps:
        solved = _axisPoint(flow, station, machAt, angleAt, stationX + step,
                            source.mach(stationX, 0.0))
        rows.append((step, solved[0] - source.mach(stationX + step, 0.0), 0.0))

    return rows

def reflectedFootOrder(steps = (0.16, 0.08, 0.04, 0.02), stationX: float = 2.0,
                       radius: float = 0.01) -> list:

    '''Error in a near-axis solve whose first-family foot lies below the center line.'''

    source, flow = SourceFlow(), referenceFlow()
    station = exactStation(source, stationX, np.linspace(0.0, 1.2, 201))
    machAt, angleAt = exactSamplers(source, stationX)

    rows = []
    for step in steps:
        angle = source.flowAngle(stationX, radius)
        mach = source.mach(stationX, radius)
        newRadius = radius + step*math.tan(angle)
        foot = newRadius - step*math.tan(angle + math.asin(1.0/mach))
        solved = _interiorPoint(flow, station, machAt, angleAt, stationX + step, newRadius,
                                mach, angle)
        rows.append((step, solved[0] - source.mach(stationX + step, newRadius),
                     solved[1] - source.flowAngle(stationX + step, newRadius), foot))

    return rows

def marchWithExactBoundary(count: int, step: float, length: float = 0.4,
                           stationX: float = 2.0, boundaryRadius: float = 0.6) -> dict:

    '''

    March interior and axis points with the boundary prescribed from the exact solution.

    The grid follows the source flow's own streamlines, which spread linearly from the origin, so
    the exact answer conserves mass through every station and any drift belongs to the scheme. The
    free boundary condition takes no part, which is what separates the interior scheme from it.

    '''

    source, flow = SourceFlow(), referenceFlow()
    fractions = np.linspace(0.0, 1.0, count)
    station = exactStation(source, stationX, fractions*boundaryRadius)
    reference = stationMassFlux(flow, station)
    worstDrift = 0.0

    for _ in range(int(round(length/step))):
        machAt, angleAt = _samplers(station)
        newX = station.x + step
        radii = fractions*boundaryRadius*newX/stationX

        mach = np.empty(count)
        flowAngle = np.empty(count)
        solved = _axisPoint(flow, station, machAt, angleAt, newX, station.mach[0])
        if solved is None:
            return {'failed': 'axis', 'x': newX}
        mach[0], flowAngle[0] = solved

        for index in range(1, count - 1):
            solved = _interiorPoint(flow, station, machAt, angleAt, newX, float(radii[index]),
                                    station.mach[index], station.flowAngle[index])
            if solved is None:
                return {'failed': f'interior point {index}', 'x': newX}
            mach[index], flowAngle[index] = solved

        mach[-1] = source.mach(newX, radii[-1])
        flowAngle[-1] = source.flowAngle(newX, radii[-1])
        station = Station(x = newX, radius = radii, mach = mach, flowAngle = flowAngle)

        drift = stationMassFlux(flow, station)/reference - 1.0
        worstDrift = drift if abs(drift) > abs(worstDrift) else worstDrift

    exact = exactStation(source, station.x, station.radius)

    return {'failed': None, 'x': station.x, 'massDrift': 100.0*worstDrift,
            'machError': float(np.abs(station.mach - exact.mach).max()),
            'angleError': float(np.degrees(np.abs(station.flowAngle - exact.flowAngle)).max())}

def report() -> None:

    '''Print every check with its observed order.'''

    print('Station marching against an exact spherical source flow')
    print(f'gamma {GAMMA}, Mach {REFERENCEMACH} at unit distance from the origin')
    print()

    for title, rows in (('interior point', interiorPointOrder()),
                        ('center-line point', axisPointOrder())):
        print(f'{title}, exact station data')
        print(f'{"step":>8} {"dMach":>12} {"dAngle deg":>12} {"machOrder":>9} {"angleOrder":>10}')
        previous = None
        for step, machError, angleError in rows:
            machOrder = _order(None if previous is None else previous[0], machError)
            angleOrder = _order(None if previous is None else previous[1], angleError)
            print(f'{step:8.4f} {machError:12.3e} {math.degrees(angleError):12.3e} '
                  f'{machOrder} {angleOrder}')
            previous = (machError, angleError)
        print()

    print('interior point with the first-family foot below the axis')
    print(f'{"step":>8} {"foot":>10} {"dMach":>12} {"dAngle deg":>12} {"machOrder":>9}')
    previous = None
    for step, machError, angleError, foot in reflectedFootOrder():
        print(f'{step:8.4f} {foot:10.5f} {machError:12.3e} {math.degrees(angleError):12.3e} '
              f'{_order(previous, machError)}')
        previous = machError
    print()

    print('march with the boundary prescribed, interior scheme under test')
    print(f'{"points":>8} {"step":>8} {"massDrift %":>12} {"dMach":>11} {"dAngle deg":>11} '
          f'{"driftOrder":>10}')
    previous = None
    for count, step in ((41, 0.02), (81, 0.01), (161, 0.005), (321, 0.0025)):
        result = marchWithExactBoundary(count, step)
        if result['failed'] is not None:
            print(f'{count:8d} {step:8.4f} failed at {result["failed"]} '
                  f'x {result["x"]:.4f}')
            continue
        print(f'{count:8d} {step:8.4f} {result["massDrift"]:12.4f} {result["machError"]:11.3e} '
              f'{result["angleError"]:11.3e} {_order(previous, result["massDrift"])}')
        previous = result['massDrift']

if __name__ == '__main__':
    report()
