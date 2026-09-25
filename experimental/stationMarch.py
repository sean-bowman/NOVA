
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

The compatibility relations and the velocity formulation are `NOVA.plume`'s own, imported rather
than transcribed, so this solver and the characteristic march cannot drift apart on the physics.
What differs is only which quantities are known at a point: the march knows the parents and solves
for the position, this knows the position and solves for the parents. The axisymmetric source term
is the one exception, written here in the cancelled form its own docstring gives, which is the same
quantity conditioned differently.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Verified, partly validated, and read by nothing in the package.**

`stationMarchVerification.py` holds the scheme against a spherical source flow, an exact solution
of the equations it solves. Every unit process runs at second order, 1.94 to 2.00 observed, and the
accumulated mass drift over a marched length at first, which is what a second-order step over a
step count rising as its inverse gives. That is verification: it establishes that the
discretization solves the equations it claims to and says nothing about the physics.

Four staged references settle the physics, and promotion follows the first three:

    1. uniform parallel exit, Pe/Pa 1.05 to 2, against mass conservation and Prandtl's cell length.
       PASSED at 1.05: conservation grid converges at -0.292, -0.169 and -0.095 per cent over 41,
       81 and 161 points across the jet, and the period measured crest to crest over three cells
       and 26 lip radii lands 2.45 per cent under Prandtl, whose own docstring records that it runs
       long. The characteristic march puts the same three crests within 0.03 lip radii and the same
       period within 0.01 per cent, on a different mesh with different unit processes. OPEN from
       1.2 to 2: the period holds to 3.4 per cent, conservation stalls near one per cent, and the
       cause is the formulation rather than the discretization, below.
    2. the worked cases of NASA TN D-2327, lip fan and leading characteristic. NOT STARTED.
    3. a divergent exit, against TR R-6's measurement that divergence angle has a small effect on
       wavelength over 0 to 20 degrees, which the characteristic march contradicts by -24.6 per
       cent at 5 degrees and -34.3 at 11. PASSED at 5 degrees, on a conical source exit at Pe/Pa
       1.05: the period runs +6.04 per cent on the parallel case with conservation at 0.42, and
       the spread over 0 to 20 degrees is +0 to +6. OPEN above it: conservation runs 8 to 12 per
       cent from 11 degrees and the march fails at 20.
    4. the interior field of TR R-6's table II, a dense characteristic net for a near-sonic exit at
       a jet static pressure ratio of 2. FAILED. The center-line wave is over-predicted by 7.8 per
       cent of its own amplitude rms, climbing from nothing at the leading characteristic to 10.9
       at the downstream end of the tabulated range, and it is one-signed throughout. Four times
       the radial resolution moves it by one part in ninety, so it is a modelling error rather than
       a discretization one. Mass conservation on the same runs is 0.10 to 0.20 per cent and the
       boundary is unaffected, exactly as that report predicts: it computed table II to establish
       that errors near the axis may have negligibly small effects on the boundary shape. Stages 1
       and 3 cannot see this.

**Do not promote on stages 1 and 3.** They measure the boundary and a conservation residual, and
stage 4 establishes that both are blind to an interior that is wrong. What the failure costs is not
yet bounded: a sonic exit turns through its whole Prandtl-Meyer angle at one point, which is the
widest fan a station normal to the axis can be asked to hold, and no reference exists at a higher
exit Mach number to say whether a narrower one behaves better.

A constant flow angle across the exit is not an initial condition here. It sets a nonzero angle on
the center line, which symmetry forbids, and the first station is rejected. The characteristic
march accepts such a line because it never applies the axis condition to it.

Above a jet static pressure ratio of about 2 no isentropic net is defensible, by Prandtl's cell
length and by TR R-6 independently, because the compression waves reflected from the boundary have
coalesced into a shock the net does not carry. This solver measures the same ceiling from its own
gradients: at Pe/Pa 1.5 the steepest radial Mach gradient, taken in units of the local jet radius,
sits at 5.22 lip radii and runs 15.7, 44.3 and 102.4 over those three resolutions, which is a
gradient with no converged value. At 1.05 nothing downstream exceeds 1.7. The ceiling therefore
belongs to the physics rather than to the scheme, and it applies here unchanged.

All units are mass base SI, angles in radians.

Author: Sean Bowman

'''

import math
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator

from NOVA.gasDynamics import areaMachRelation, machFromAreaRatio
from NOVA.plume import PlumeFlow, PlumePoint, _reciprocalVelocitySlope

def _axisymmetricSource(foot: PlumePoint, characteristicAngle: float, step: float) -> float:

    '''

    Axisymmetric term of a compatibility relation, integrated from a foot over one axial step.

    The relation carries `sin(theta) sin(mu) / sin(theta +/- mu) * dr / r`, which is the form
    `NOVA.plume` applies, and the increment in radius along the characteristic is
    `tan(theta +/- mu) dx`. Written that way the sine in the denominator and the tangent in the
    increment vanish together as the characteristic turns axis-parallel, which the second family
    does wherever the flow angle reaches the Mach angle. Both are then differences of angles near
    their own rounding, and the product they form is set by which state each was evaluated at
    rather than by the flow: at Mach 4 with 14.4 degrees of turning the coefficient reaches -1.6e4
    and the solve diverges within four iterations.

    Cancelling them analytically leaves `sin(theta) sin(mu) / cos(theta +/- mu) * dx / r`, the same
    quantity with nothing small in the denominator. The only singular direction left is a
    characteristic normal to the axis, which the second family cannot reach and the first
    approaches only at the sonic line.

    The characteristic march is left on the uncancelled form. It meets the same condition, but
    substituting this one moves its mass drift by a thousandth of a per cent on a parallel exit and
    does not change where it fails, so its bit-level agreement with the nozzle solver is worth more
    than the conditioning it does not need.

    '''

    return (math.sin(foot.flowAngle) * math.sin(foot.machAngle) * step
            / (foot.r * math.cos(characteristicAngle)))

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

def conicalStation(flow: PlumeFlow, lipMach: float, lipAngle: float, exitRadius: float,
                   count: int, x: float = 0.0) -> Station:

    '''

    The exit plane of a conical nozzle, which is a radial source flow.

    A conical nozzle carries purely radial flow from the apex, so a plane normal to the axis reads
    the state at each point's distance from that apex. It is an exact solution of the equations the
    scheme solves, which a uniform Mach number at a constant nonzero flow angle is not: that one
    sets a flow angle on the center line, which symmetry forbids, and the first station is
    rejected. TR R-6's hardware is conical, so this is also the right initial condition for the
    divergence sweep.

    `lipAngle` is the half angle of the cone in radians, and the Mach number is held at `lipMach`
    on the lip so that changing the angle changes only the divergence.

    '''

    if lipAngle <= 1e-9:
        return uniformStation(flow, lipMach, exitRadius, count, x = x)

    apex = exitRadius/math.tan(lipAngle)
    sonicRadius = math.hypot(apex, exitRadius)/math.sqrt(areaMachRelation(lipMach, flow.gamma))
    radius = np.linspace(0.0, exitRadius, count)
    mach = np.array([machFromAreaRatio((math.hypot(apex, value)/sonicRadius)**2, flow.gamma)
                     for value in radius])

    return Station(x = x, radius = radius, mach = mach, flowAngle = np.arctan2(radius, apex))

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

    '''

    The state at one radius of a station, as a point the relations can read.

    A foot below the axis is read by reflection rather than rejected. The jet is symmetric, so the
    state at a negative radius is the state at its magnitude with the flow angle reversed, and the
    first-family characteristic reaching a near-axis point from below is the mirror of a
    second-family characteristic in the lower half. Without it the near-axis points cap the step at
    a fraction of the radial spacing, which is what forces every characteristic foot to land inside
    one grid cell.

    '''

    signed = float(radius)
    magnitude = abs(signed)
    if magnitude > float(station.radius[-1]):
        magnitude = float(station.radius[-1])
        signed = math.copysign(magnitude, signed)

    mach = float(machAt(magnitude))
    if not math.isfinite(mach) or mach <= 1.0:
        return None

    angle = float(angleAt(magnitude))

    return PlumePoint(station.x, signed, mach, angle if signed >= 0.0 else -angle, flow, 'foot')

def stepLimit(flow: PlumeFlow, station: Station, safety: float = 1.0) -> float:

    '''

    The axial step that puts the steepest characteristic foot one radial spacing from its point.

    Shortening the step past this does not refine the solution, it degrades it. A foot inside its
    own grid cell reads the interpolant's slope rather than the station's data, and a monotone cubic
    carries only second order in its first derivative, so the error per step stops falling while the
    number of steps keeps rising. Measured on a parallel exit at a jet static pressure ratio of 2,
    mass drift runs 0.97 per cent at one spacing and 7.20 at half of one.

    `safety` scales the spacing the foot is allowed to span, so values above one read further across
    the station rather than less far.

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
        plusAngle  = flowAngle + machAngle
        minusAngle = flowAngle - machAngle

        below = _pointAt(flow, station, newRadius - step*math.tan(plusAngle), machAt, angleAt)
        above = _pointAt(flow, station, newRadius - step*math.tan(minusAngle), machAt, angleAt)
        if below is None or above is None or abs(below.r) < 1e-12 or abs(above.r) < 1e-12:
            return None

        # Average the slopes with the parents, which is what makes the step second order
        plusAngle  = 0.5*((below.flowAngle + below.machAngle) + (flowAngle + machAngle))
        minusAngle = 0.5*((above.flowAngle - above.machAngle) + (flowAngle - machAngle))
        below = _pointAt(flow, station, newRadius - step*math.tan(plusAngle), machAt, angleAt)
        above = _pointAt(flow, station, newRadius - step*math.tan(minusAngle), machAt, angleAt)
        if below is None or above is None or abs(below.r) < 1e-12 or abs(above.r) < 1e-12:
            return None

        slopeOne, slopeTwo = _reciprocalVelocitySlope(below), _reciprocalVelocitySlope(above)
        belowSource = _axisymmetricSource(below, plusAngle, step)
        aboveSource = _axisymmetricSource(above, minusAngle, step)

        velocity = (1.0 / (slopeOne + slopeTwo)) \
                   * (below.velocity*slopeOne + above.velocity*slopeTwo
                      + belowSource + aboveSource
                      + above.flowAngle - below.flowAngle)

        newMach = flow.machFromVelocity(velocity)
        if not math.isfinite(newMach) or newMach <= 1.0:
            return None

        fromBelow = below.flowAngle + slopeOne*(velocity - below.velocity) - belowSource
        fromAbove = above.flowAngle - slopeTwo*(velocity - above.velocity) + aboveSource
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
        minusAngle = -machAngle
        above = _pointAt(flow, station, -step*math.tan(minusAngle), machAt, angleAt)
        if above is None or above.r <= 0.0:
            return None

        minusAngle = 0.5*((above.flowAngle - above.machAngle) + (0.0 - machAngle))
        above = _pointAt(flow, station, -step*math.tan(minusAngle), machAt, angleAt)
        if above is None or above.r <= 0.0:
            return None

        slopeTwo = _reciprocalVelocitySlope(above)
        aboveSource = _axisymmetricSource(above, minusAngle, step)
        velocity = above.velocity + (above.flowAngle + aboveSource) / slopeTwo

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
        plusAngle = 0.5*((previousAngle + math.asin(1.0/float(station.mach[-1])))
                         + (flowAngle + machAngle))
        below = _pointAt(flow, station, radius - step*math.tan(plusAngle), machAt, angleAt)
        if below is None or below.r <= 0.0:
            return None

        slopeOne = _reciprocalVelocitySlope(below)
        newAngle = below.flowAngle + slopeOne*(velocity - below.velocity) \
                   - _axisymmetricSource(below, plusAngle, step)
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
                      safety: float = 1.0) -> dict:

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
        Radial spacings the steepest characteristic foot is allowed to span.

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
