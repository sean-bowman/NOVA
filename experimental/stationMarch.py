
# -- Station marching for the plume interior -- #

'''

The plume solved station by station, on a data line that cannot become a characteristic.

`NOVA.plume.solvePlumeMarch` marches the characteristics themselves: each new line is traced from
a start point out to the free boundary, and the mesh goes wherever the waves take it. That is
accurate and uncontrolled. Measured at the point it stalls on a mildly underexpanded jet, the data
line has rotated to within 0.00 degrees of the first-family characteristic direction over part of
its length, the spacing along it spans 114 to 1, and the center line has advanced a tenth of a lip
radius while the boundary has run two. A data line lying on a characteristic carries no
information across itself, which is what ends the march.

This module prescribes the data line instead and solves for the flow on it. Stations are planes
normal to the axis, so the line can never rotate into a characteristic, and the points on it sit
at fixed fractions of the local jet radius, so resolution is held as the plume opens out. The
price is an interpolation at every station, which the characteristic march does not pay.

What it buys, beyond surviving:

    the boundary      one point per station, so the jet boundary is an output rather than a
                      reconstruction from scattered nodes
    the interior      a structured grid, station by radial fraction, which contours directly
    a divergent exit  no longer a special case, since a station is normal to the axis whatever
                      angle the flow leaves the lip at

The compatibility relations, the axisymmetric source terms and the velocity formulation are
`NOVA.plume`'s own, imported rather than transcribed, so this solver and the characteristic march
cannot drift apart on the physics. What differs is only which quantities are known at a point:
the march knows the parents and solves for the position, this knows the position and solves for
the parents.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Unproven. Nothing in the package reads this.** It is staged against the same references the
characteristic march was held to, and it is promoted only when it passes them:

    1. uniform parallel exit, Pe/Pa 1.05 to 2, against mass conservation and Prandtl's cell length
    2. the worked cases of NASA TN D-2327, lip fan and leading characteristic
    3. a divergent exit, against TR R-6's measurement that divergence angle has a small effect on
       wavelength over 0 to 20 degrees, which the characteristic march contradicts by -25 per cent
       at 5 degrees and -34 at 11
    4. the interior field and boundary shape of TR R-6, whose table II is not yet transcribed

Above a jet static pressure ratio of about 2 no isentropic net is defensible, by Prandtl's cell
length and by TR R-6 independently, because the compression waves reflected from the boundary
have coalesced into a shock the net does not carry. That ceiling belongs to the physics rather
than to the scheme, and it applies here unchanged.

All units are mass base SI, angles in radians.

Author: Sean Bowman

'''

import math
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator

from NOVA.plume import (PlumeFlow, PlumePoint, _leftRunningTerm, _reciprocalVelocitySlope,
                        _rightRunningTerm)

@dataclass
class Station:

    '''

    The flow across one plane normal to the axis.

    Attributes:
    -----------
    x : float
        Axial position of the plane [m].
    radius : numpy.ndarray
        Radial position of each point [m], ascending, axis first and boundary last.
    mach : numpy.ndarray
        Mach number at each point [-].
    flowAngle : numpy.ndarray
        Flow angle at each point [rad].

    '''

    x:         float
    radius:    np.ndarray
    mach:      np.ndarray
    flowAngle: np.ndarray

    @property
    def boundaryRadius(self) -> float:
        return float(self.radius[-1])

def stationMassFlux(flow: PlumeFlow, station: Station) -> float:

    '''

    Axial mass flow through a station, which every station must carry equally.

    The integral is rho V cos(theta) over the area, taken by trapezoid on the station's own
    points. It is the only quality measure available at an operating point with no reference to
    compare against, and it is sensitive to exactly what the scheme risks: interpolation error at
    each step accumulates in it.

    '''

    density  = np.array([flow.density(mach) for mach in station.mach])
    velocity = np.array([flow.velocity(mach) for mach in station.mach])
    integrand = density * velocity * np.cos(station.flowAngle) * station.radius

    return float(2.0 * math.pi * np.trapezoid(integrand, station.radius))

def uniformStation(flow: PlumeFlow, exitMach: float, exitRadius: float, count: int,
                   x: float = 0.0, flowAngle: float = 0.0) -> Station:

    '''A uniform exit plane, which is the case the scheme is proved on first.'''

    radius = np.linspace(0.0, exitRadius, count)

    return Station(x = x, radius = radius, mach = np.full(count, float(exitMach)),
                   flowAngle = np.full(count, float(flowAngle)))

def stationFromLine(line, count: int, x: float = None) -> Station:

    '''

    A station built from the nozzle exit plane the contour solve hands over.

    The exit plane of a contoured nozzle is not uniform: the flow leaves along the axis and turns
    through the wall angle at the lip, and both the Mach number and the angle vary across it. The
    points are taken as given and redistributed onto the station's own radial grid.

    '''

    radii  = np.array([point.r for point in line], dtype = float)
    machs  = np.array([point.mach for point in line], dtype = float)
    angles = np.array([point.flowAngle for point in line], dtype = float)
    order  = np.argsort(radii)
    radii, machs, angles = radii[order], machs[order], angles[order]

    keep = np.concatenate(([True], np.diff(radii) > 0))
    radii, machs, angles = radii[keep], machs[keep], angles[keep]

    grid = np.linspace(radii[0], radii[-1], count)

    return Station(x = float(np.mean([point.x for point in line])) if x is None else float(x),
                   radius = grid,
                   mach = PchipInterpolator(radii, machs)(grid),
                   flowAngle = PchipInterpolator(radii, angles)(grid))

def _samplers(station: Station):

    '''Monotone interpolants for the station, so a foot between points reads a physical state.'''

    return (PchipInterpolator(station.radius, station.mach),
            PchipInterpolator(station.radius, station.flowAngle))

def _pointAt(flow: PlumeFlow, station: Station, radius: float, machAt, angleAt) -> PlumePoint:

    '''The state at one radius of a station, as a point the relations can read.'''

    clamped = min(max(float(radius), float(station.radius[0])), float(station.radius[-1]))
    mach = float(machAt(clamped))
    if not math.isfinite(mach) or mach <= 1.0:
        return None

    return PlumePoint(station.x, clamped, mach, float(angleAt(clamped)), flow, 'foot')

def stepLimit(flow: PlumeFlow, station: Station, safety: float = 0.5) -> float:

    '''

    The largest axial step whose characteristics still reach back within a point spacing.

    A foot that lands further than its neighbors puts the solve on an interpolation over a wide
    interval, which is where the accuracy goes. Holding the step to a fraction of the spacing over
    the steepest characteristic keeps every foot local.

    '''

    spacing = np.diff(station.radius)
    if spacing.size == 0:
        return 0.0

    machAngle = np.arcsin(1.0 / np.maximum(station.mach, 1.0 + 1e-12))
    steepest = np.max(np.abs(np.tan(station.flowAngle + machAngle)))
    steepest = max(steepest, np.max(np.abs(np.tan(station.flowAngle - machAngle))), 1e-6)

    return float(safety * np.min(spacing) / steepest)

def _interiorPoint(flow, station, machAt, angleAt, newX, newRadius, guessMach, guessAngle,
                   tolerance = 1e-10, maxIterations = 30):

    '''

    Solve one interior point of the new station from the two characteristics reaching it.

    Both feet are traced back to the previous station on averaged slopes, and the pair of
    compatibility relations is solved for the velocity and the flow angle at the prescribed
    position. The relations are the ones `NOVA.plume.plumeInteriorPoint` applies; only the
    unknowns change places.

    '''

    step = newX - station.x
    mach, flowAngle = float(guessMach), float(guessAngle)

    for _ in range(maxIterations):
        machAngle = math.asin(1.0 / mach)
        plusSlope  = math.tan(flowAngle + machAngle)
        minusSlope = math.tan(flowAngle - machAngle)

        below = _pointAt(flow, station, newRadius - step*plusSlope, machAt, angleAt)
        above = _pointAt(flow, station, newRadius - step*minusSlope, machAt, angleAt)
        if below is None or above is None or below.r <= 0.0 or above.r <= 0.0:
            return None

        # Average the slopes with the parents, which is what makes the step second order
        plusSlope  = math.tan(0.5*((below.flowAngle + below.machAngle) + (flowAngle + machAngle)))
        minusSlope = math.tan(0.5*((above.flowAngle - above.machAngle) + (flowAngle - machAngle)))
        below = _pointAt(flow, station, newRadius - step*plusSlope, machAt, angleAt)
        above = _pointAt(flow, station, newRadius - step*minusSlope, machAt, angleAt)
        if below is None or above is None or below.r <= 0.0 or above.r <= 0.0:
            return None

        slopeOne, slopeTwo = _reciprocalVelocitySlope(below), _reciprocalVelocitySlope(above)
        leftTerm, rightTerm = _leftRunningTerm(below), _rightRunningTerm(above)

        velocity = (1.0 / (slopeOne + slopeTwo)) \
                   * (below.velocity*slopeOne + above.velocity*slopeTwo
                      + (leftTerm / below.r)*(newRadius - below.r)
                      + (rightTerm / above.r)*(newRadius - above.r)
                      + above.flowAngle - below.flowAngle)

        newMach = flow.machFromVelocity(velocity)
        if not math.isfinite(newMach) or newMach <= 1.0:
            return None

        fromBelow = below.flowAngle + slopeOne*(velocity - below.velocity) \
                    - (leftTerm / below.r)*(newRadius - below.r)
        fromAbove = above.flowAngle - slopeTwo*(velocity - above.velocity) \
                    + (rightTerm / above.r)*(newRadius - above.r)
        newAngle = 0.5*(fromBelow + fromAbove)

        converged = abs(newMach - mach) <= tolerance*max(abs(newMach), 1.0) \
                    and abs(newAngle - flowAngle) <= tolerance
        mach, flowAngle = newMach, newAngle
        if converged:
            break

    return mach, flowAngle

def _axisPoint(flow, station, machAt, angleAt, newX, guessMach,
               tolerance = 1e-10, maxIterations = 30):

    '''

    Solve the center-line point, where symmetry fixes the flow angle at zero.

    Only the second-family characteristic reaches the axis from above, so one relation and the
    symmetry condition close the point.

    '''

    step = newX - station.x
    mach = float(guessMach)

    for _ in range(maxIterations):
        machAngle = math.asin(1.0 / mach)
        minusSlope = math.tan(-machAngle)
        above = _pointAt(flow, station, -step*minusSlope, machAt, angleAt)
        if above is None or above.r <= 0.0:
            return None

        minusSlope = math.tan(0.5*((above.flowAngle - above.machAngle) + (0.0 - machAngle)))
        above = _pointAt(flow, station, -step*minusSlope, machAt, angleAt)
        if above is None or above.r <= 0.0:
            return None

        slopeTwo, rightTerm = _reciprocalVelocitySlope(above), _rightRunningTerm(above)
        velocity = above.velocity + (above.flowAngle - rightTerm) / slopeTwo

        newMach = flow.machFromVelocity(velocity)
        if not math.isfinite(newMach) or newMach <= 1.0:
            return None

        converged = abs(newMach - mach) <= tolerance*max(abs(newMach), 1.0)
        mach = newMach
        if converged:
            break

    return mach, 0.0

def _boundaryPoint(flow, station, machAt, angleAt, newX, boundaryMach,
                   tolerance = 1e-12, maxIterations = 30):

    '''

    Solve the free boundary point, where ambient pressure fixes the Mach number.

    A free boundary is the reverse of a wall: the pressure is known and the angle is solved. The
    boundary is a streamline, so its radius advances on the mean of its own flow angle, and the
    first-family characteristic arriving from inside supplies the angle.

    '''

    step = newX - station.x
    velocity = flow.velocity(boundaryMach)
    machAngle = math.asin(1.0 / boundaryMach)
    previousAngle = float(station.flowAngle[-1])
    flowAngle = previousAngle
    radius = station.boundaryRadius + step*math.tan(previousAngle)

    for _ in range(maxIterations):
        plusSlope = math.tan(0.5*((previousAngle + math.asin(1.0/float(station.mach[-1])))
                                  + (flowAngle + machAngle)))
        below = _pointAt(flow, station, radius - step*plusSlope, machAt, angleAt)
        if below is None or below.r <= 0.0:
            return None

        slopeOne, leftTerm = _reciprocalVelocitySlope(below), _leftRunningTerm(below)
        newAngle = below.flowAngle + slopeOne*(velocity - below.velocity) \
                   - (leftTerm / below.r)*(radius - below.r)
        newRadius = station.boundaryRadius + step*math.tan(0.5*(previousAngle + newAngle))

        converged = abs(newAngle - flowAngle) <= tolerance \
                    and abs(newRadius - radius) <= tolerance*max(abs(newRadius), 1e-12)
        flowAngle, radius = newAngle, newRadius
        if converged:
            break

    return radius, flowAngle

def advanceStation(flow: PlumeFlow, station: Station, boundaryMach: float,
                   step: float) -> Station:

    '''

    Step the whole station one increment downstream.

    The boundary is solved first, because its radius sets where the interior points go: they sit
    at the same fractions of the jet radius they occupied on the station behind, which is what
    holds the resolution as the plume opens out.

    Returns None where any point of the new station cannot be solved.

    '''

    machAt, angleAt = _samplers(station)
    newX = station.x + step

    edge = _boundaryPoint(flow, station, machAt, angleAt, newX, boundaryMach)
    if edge is None:
        return None
    boundaryRadius, boundaryAngle = edge
    if boundaryRadius <= 0.0:
        return None

    fractions = station.radius / station.boundaryRadius
    newRadius = fractions * boundaryRadius

    mach = np.empty_like(newRadius)
    flowAngle = np.empty_like(newRadius)

    solved = _axisPoint(flow, station, machAt, angleAt, newX, station.mach[0])
    if solved is None:
        return None
    mach[0], flowAngle[0] = solved

    for index in range(1, newRadius.size - 1):
        solved = _interiorPoint(flow, station, machAt, angleAt, newX, float(newRadius[index]),
                                station.mach[index], station.flowAngle[index])
        if solved is None:
            return None
        mach[index], flowAngle[index] = solved

    mach[-1], flowAngle[-1] = boundaryMach, boundaryAngle

    return Station(x = newX, radius = newRadius, mach = mach, flowAngle = flowAngle)

def solveStationMarch(flow: PlumeFlow, station: Station, ambientPressure: float,
                      maxLength: float = 20.0, maxStations: int = 20000,
                      safety: float = 0.5) -> dict:

    '''

    March the plume downstream from a station until it runs out of length or fails.

    Parameters:
    -----------
    flow : PlumeFlow
        The gas the jet is solved in.
    station : Station
        The exit plane, uniform or taken from the contour solve.
    ambientPressure : float
        Back pressure the free boundary expands to [Pa].
    maxLength : float
        Axial distance to march, in units of the starting jet radius [-].
    maxStations : int
        Ceiling on the number of steps.
    safety : float
        Fraction of the step limit each step takes.

    Returns:
    --------
    dict
        `stations`, the solved stations; `boundary`, the (x, r) of the jet boundary; `massDrift`,
        the per-station departure from the first station's mass flow in per cent; `stop`, why the
        march ended.

    '''

    boundaryMach = flow.machFromStaticPressure(ambientPressure)
    if boundaryMach <= float(station.mach[-1]):
        return {'stations': [station], 'boundary': [(station.x, station.boundaryRadius)],
                'massDrift': [0.0], 'stop': 'notUnderexpanded', 'boundaryMach': boundaryMach}

    reference = stationMassFlux(flow, station)
    stations = [station]
    boundary = [(station.x, station.boundaryRadius)]
    massDrift = [0.0]
    stop = 'maxLength'
    endX = station.x + maxLength*station.boundaryRadius

    while stations[-1].x < endX and len(stations) < maxStations:
        current = stations[-1]
        step = stepLimit(flow, current, safety)
        if step <= 0.0:
            stop = 'stepCollapsed'
            break

        advanced = advanceStation(flow, current, boundaryMach, min(step, endX - current.x))
        if advanced is None:
            stop = 'stationFailed'
            break

        stations.append(advanced)
        boundary.append((advanced.x, advanced.boundaryRadius))
        massDrift.append(100.0*(stationMassFlux(flow, advanced) - reference)/reference)

    return {'stations': stations, 'boundary': boundary, 'massDrift': massDrift, 'stop': stop,
            'boundaryMach': boundaryMach, 'referenceFlux': reference}
