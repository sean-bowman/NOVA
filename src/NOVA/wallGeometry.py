
# -- Prescribed Wall Geometry -- #

'''

A diverging wall given as analytic pieces, for the families whose wall is drawn before the flow
is solved.

A truncated ideal contour never needs this. Its wall is a streamline traced through a mesh, so
the wall is an output and the only geometry the solve knows in advance is the throat arc. A
thrust-optimized parabola and a thrust-optimized contour invert that: the wall is an input, and
the characteristics net has to be marched against it. Marching against a wall means asking the
same two questions at every step, thousands of times over a solve, so both have exact answers
here rather than numerical ones.

**Where does a straight characteristic meet the wall.** For every segment type below this is the
root of a polynomial: linear for a line, quadratic for a circular arc and a quadratic Bezier,
cubic for a cubic Bezier. `contourKernel.throatIntersection` spends an `fsolve` per wall point on
the circular-arc case, which is the quadratic solved here in closed form.

**What angle is the wall at that point.** The tangent of a parametric curve is its derivative, so
this is exact too. Nothing is finite-differenced. That matters more than it sounds: the wall is
where the compression waves that coalesce into a bell's internal shock are generated, so an error
in the wall angle is an error in where the shock forms, not just in the wall.

Sampled points with an interpolated slope were the obvious alternative and are the wrong tool.
They put interpolation error exactly at the boundary that generates the waves, and `utils.arcSpline`
in particular is a resampler whose arc-length inverse is itself numerical. `arcSpline` keeps its
existing job, resampling a finished wall onto even spacing, and stays out of the march.

Segments are parameterised on t in [0, 1] and a wall reports position along itself as
`segmentIndex + t`, which is monotone from throat to exit and is all the march needs to refuse a
ray that lands on a segment it has already passed. It is a station, not an arc length; the true
arc length is available separately and is not on the hot path.

Lengths are non-dimensional against the throat radius. Angles are in radians, measured from the
axis, positive where the wall opens outward.

Validation status
-----------------

Checked against closed-form geometry and against the construction it replaces. The Rao parabolic
wall built here reproduces `contour.raoParabolicContour` point for point, which is covered by the
existing tests of that construction. Ray intersections are checked against a brute-force scan of
the same segment, and tangent angles against a central difference of the parametric point, both
to tolerances far tighter than the mesh. The endpoints and end angles reproduce what was
requested, by construction and by test.

Nothing here is a physical model, so there is nothing to validate against experiment. What can be
wrong is the arithmetic, and that is what the tests above bound.

Author: Sean Bowman

'''

import numpy as np

class WallSegment:

    '''

    One analytic piece of a prescribed wall, parameterised on t in [0, 1].

    Subclasses supply `point`, `tangentAngle` and `_rayParameters`. Everything else is shared.

    '''

    def point(self, parameter: float) -> tuple:

        '''

        Position on the segment [-].

        Parameters:
        -----------
        parameter : float
            Curve parameter in [0, 1], 0 at the upstream end.

        Returns:
        --------
        tuple : (x, r), non-dimensional

        '''

        raise NotImplementedError

    def tangentAngle(self, parameter: float) -> float:

        '''

        Wall angle at a parameter, measured from the axis [rad].

        '''

        raise NotImplementedError

    def _rayParameters(self, slope: float, intercept: float) -> list:

        '''

        Parameters where the segment meets the line r = slope * x + intercept.

        Returns every real root in [0, 1], unordered. The caller decides which one it wants.

        '''

        raise NotImplementedError

    def arcLength(self, numPoints: int = 200) -> float:

        '''

        Length along the segment [-], by trapezoidal quadrature of the parametric speed.

        Reporting only. The march orders itself by the curve parameter, which is exact and free,
        rather than by arc length, which is neither.

        '''

        parameters = np.linspace(0.0, 1.0, numPoints)
        points     = np.array([self.point(parameter) for parameter in parameters])
        steps      = np.diff(points, axis = 0)
        return float(np.sum(np.hypot(steps[:, 0], steps[:, 1])))

class LineSegment(WallSegment):

    '''

    A straight wall run between two points, which is what a conical section is.

    Parameters:
    -----------
    start, end : tuple
        (x, r) at each end, non-dimensional.

    '''

    def __init__(self, start: tuple, end: tuple):
        self.start = (float(start[0]), float(start[1]))
        self.end   = (float(end[0]), float(end[1]))

    def __repr__(self):
        return f'LineSegment(start = {self.start}, end = {self.end})'

    def point(self, parameter: float) -> tuple:
        return (self.start[0] + parameter * (self.end[0] - self.start[0]),
                self.start[1] + parameter * (self.end[1] - self.start[1]))

    def tangentAngle(self, parameter: float = 0.0) -> float:
        return float(np.arctan2(self.end[1] - self.start[1], self.end[0] - self.start[0]))

    def _rayParameters(self, slope: float, intercept: float) -> list:
        # r(t) - slope * x(t) - intercept = 0, linear in t.
        deltaX, deltaR = self.end[0] - self.start[0], self.end[1] - self.start[1]
        denominator    = deltaR - slope * deltaX
        if abs(denominator) < 1e-15:
            return []
        parameter = (slope * self.start[0] + intercept - self.start[1]) / denominator
        return [parameter]

class CircularArcSegment(WallSegment):

    '''

    A circular arc, which is what both throat arcs are.

    The parameter runs linearly in wall angle from `startAngle` to `endAngle`, so t and the wall
    angle are the same thing up to an affine map. That is the natural parameter for a throat arc,
    because the mesh launches its characteristics at equal increments of wall angle.

    Parameters:
    -----------
    center : tuple
        (x, r) of the arc center, non-dimensional.
    radius : float
        Arc radius, non-dimensional.
    startAngle, endAngle : float
        Wall angles at each end [rad], measured from the axis.

    '''

    def __init__(self, center: tuple, radius: float, startAngle: float, endAngle: float):
        self.center     = (float(center[0]), float(center[1]))
        self.radius     = float(radius)
        self.startAngle = float(startAngle)
        self.endAngle   = float(endAngle)

    def __repr__(self):
        return (f'CircularArcSegment(center = {self.center}, radius = {self.radius:.6f}, '
                f'startAngle = {np.degrees(self.startAngle):.3f} deg, '
                f'endAngle = {np.degrees(self.endAngle):.3f} deg)')

    def wallAngle(self, parameter: float) -> float:

        '''

        Wall angle at a parameter [rad]. The parameter is affine in this angle by construction.

        '''

        return self.startAngle + parameter * (self.endAngle - self.startAngle)

    def point(self, parameter: float) -> tuple:
        angle = self.wallAngle(parameter)
        # The wall turns outward as the angle grows, so the center sits above the arc.
        return (self.center[0] + self.radius * np.sin(angle),
                self.center[1] - self.radius * np.cos(angle))

    def tangentAngle(self, parameter: float) -> float:
        return self.wallAngle(parameter)

    def _rayParameters(self, slope: float, intercept: float) -> list:
        # Solved in Cartesian rather than in the angle: a line meeting a circle is a quadratic in
        # x, whereas the same condition written in the arc's own angle is transcendental.
        centerX, centerR = self.center
        a = 1.0 + slope**2
        b = 2.0 * (slope * (intercept - centerR) - centerX)
        c = centerX**2 + (intercept - centerR)**2 - self.radius**2
        discriminant = b**2 - 4.0 * a * c
        if discriminant < 0.0:
            return []
        rootDiscriminant = np.sqrt(discriminant)

        parameters, sweep = [], self.endAngle - self.startAngle
        if abs(sweep) < 1e-15:
            return []
        for x in ((-b + rootDiscriminant) / (2.0 * a), (-b - rootDiscriminant) / (2.0 * a)):
            r     = slope * x + intercept
            # Recover the wall angle from the position on the circle, then the parameter from it.
            angle = np.arctan2(x - centerX, centerR - r)
            parameters.append((angle - self.startAngle) / sweep)
        return parameters

class QuadraticBezierSegment(WallSegment):

    '''

    A quadratic Bezier, which is the curve Rao's canted parabola actually is.

    Parameters:
    -----------
    start, control, end : tuple
        The three control points as (x, r), non-dimensional.

    '''

    def __init__(self, start: tuple, control: tuple, end: tuple):
        self.points = np.array([start, control, end], dtype = float)

    def __repr__(self):
        return (f'QuadraticBezierSegment(start = {tuple(self.points[0])}, '
                f'control = {tuple(self.points[1])}, end = {tuple(self.points[2])})')

    def point(self, parameter: float) -> tuple:
        p0, p1, p2 = self.points
        complement = 1.0 - parameter
        value = complement**2 * p0 + 2.0 * complement * parameter * p1 + parameter**2 * p2
        return (float(value[0]), float(value[1]))

    def derivative(self, parameter: float) -> tuple:

        '''

        dx/dt and dr/dt at a parameter. Exact, which is why nothing here is differenced.

        '''

        p0, p1, p2 = self.points
        value = 2.0 * (1.0 - parameter) * (p1 - p0) + 2.0 * parameter * (p2 - p1)
        return (float(value[0]), float(value[1]))

    def tangentAngle(self, parameter: float) -> float:
        derivativeX, derivativeR = self.derivative(parameter)
        return float(np.arctan2(derivativeR, derivativeX))

    def _rayParameters(self, slope: float, intercept: float) -> list:
        # r(t) - slope * x(t) - intercept, quadratic in t.
        p0, p1, p2 = self.points
        residual   = p2[1] - slope * p2[0], p1[1] - slope * p1[0], p0[1] - slope * p0[0]
        endTerm, controlTerm, startTerm = residual
        quadratic = endTerm - 2.0 * controlTerm + startTerm
        linear    = 2.0 * (controlTerm - startTerm)
        constant  = startTerm - intercept
        return _realRoots([quadratic, linear, constant])

class CubicBezierSegment(WallSegment):

    '''

    A cubic Bezier, which is the wall a thrust-optimized contour is searched over.

    The family matters as much as the curve. A quadratic Bezier is exactly the cubic with
    `P1 = Q0 + (2/3)(Q1 - Q0)` and `P2 = Q2 + (2/3)(Q1 - Q2)`, so every Rao parabola is a member of
    this family. An optimizer searching here therefore starts from the parabola as its incumbent
    and can only improve on it, which is what makes "does the optimum beat the parabola" a
    question with an answer rather than a race between two search procedures.

    Parameters:
    -----------
    start, firstControl, secondControl, end : tuple
        The four control points as (x, r), non-dimensional.

    '''

    def __init__(self, start: tuple, firstControl: tuple, secondControl: tuple, end: tuple):
        self.points = np.array([start, firstControl, secondControl, end], dtype = float)

    def __repr__(self):
        return f'CubicBezierSegment(points = {self.points.tolist()})'

    def point(self, parameter: float) -> tuple:
        p0, p1, p2, p3 = self.points
        complement = 1.0 - parameter
        value = (complement**3 * p0 + 3.0 * complement**2 * parameter * p1
                 + 3.0 * complement * parameter**2 * p2 + parameter**3 * p3)
        return (float(value[0]), float(value[1]))

    def derivative(self, parameter: float) -> tuple:

        '''

        dx/dt and dr/dt at a parameter.

        '''

        p0, p1, p2, p3 = self.points
        complement = 1.0 - parameter
        value = (3.0 * complement**2 * (p1 - p0) + 6.0 * complement * parameter * (p2 - p1)
                 + 3.0 * parameter**2 * (p3 - p2))
        return (float(value[0]), float(value[1]))

    def tangentAngle(self, parameter: float) -> float:
        derivativeX, derivativeR = self.derivative(parameter)
        return float(np.arctan2(derivativeR, derivativeX))

    def _rayParameters(self, slope: float, intercept: float) -> list:
        # r(t) - slope * x(t) - intercept, cubic in t, in the Bernstein basis expanded to powers.
        terms = [point[1] - slope * point[0] for point in self.points]
        b0, b1, b2, b3 = terms
        cubic     = -b0 + 3.0 * b1 - 3.0 * b2 + b3
        quadratic = 3.0 * b0 - 6.0 * b1 + 3.0 * b2
        linear    = -3.0 * b0 + 3.0 * b1
        constant  = b0 - intercept
        return _realRoots([cubic, quadratic, linear, constant])

class SampledSegment(WallSegment):

    '''

    A wall given as points rather than as a formula, carried on a shape-preserving interpolant.

    The fallback, and it is deliberately not the default. Two things use it: a contour imported
    from somewhere else, and the check that marches this module's solver over a truncated ideal
    contour's own wall, which is the strongest verification available for the forward march and
    is unavailable if only analytic walls can be represented.

    It is the fallback because it gives up what the analytic segments are for. The slope is the
    interpolant's slope rather than the curve's, and the ray intersection becomes a bracketed root
    search rather than a closed form. PCHIP is used rather than a C2 cubic for the same reason
    `utils.arcSpline` defaults to it: a spline through a wall with a corner in it must overshoot,
    and an overshoot here is a wall the march would faithfully generate waves from.

    Parameters:
    -----------
    x, r : np.ndarray
        Wall points, strictly increasing in x.

    '''

    def __init__(self, x, r):
        from scipy.interpolate import PchipInterpolator

        self.x = np.asarray(x, dtype = float)
        self.r = np.asarray(r, dtype = float)
        if np.any(np.diff(self.x) <= 0.0):
            raise ValueError('A sampled wall segment needs points strictly increasing in x.')

        self._radius = PchipInterpolator(self.x, self.r)
        self._slope  = self._radius.derivative()

    def __repr__(self):
        return (f'SampledSegment({len(self.x)} points, '
                f'x {self.x[0]:.6f} to {self.x[-1]:.6f})')

    def _axial(self, parameter: float) -> float:
        return self.x[0] + parameter * (self.x[-1] - self.x[0])

    def point(self, parameter: float) -> tuple:
        x = self._axial(parameter)
        return (float(x), float(self._radius(x)))

    def tangentAngle(self, parameter: float) -> float:
        return float(np.arctan(self._slope(self._axial(parameter))))

    def _rayParameters(self, slope: float, intercept: float) -> list:
        from scipy.optimize import brentq

        residual = self.r - (slope * self.x + intercept)
        span     = self.x[-1] - self.x[0]
        roots    = []

        for index in np.where(np.sign(residual[:-1]) != np.sign(residual[1:]))[0]:
            left, right = self.x[index], self.x[index + 1]
            function = lambda x: float(self._radius(x)) - (slope * x + intercept)
            try:
                root = brentq(function, left, right, xtol = 1e-14)
            except ValueError:
                continue
            roots.append((root - self.x[0]) / span)

        # A point that sits exactly on the ray is a root the sign change cannot see.
        for index in np.where(np.abs(residual) < 1e-14)[0]:
            roots.append((self.x[index] - self.x[0]) / span)

        return roots

def _realRoots(coefficients: list, tolerance: float = 1e-12) -> list:

    '''

    Real roots of a polynomial given highest power first, with leading zeros dropped.

    Dropping the leading zeros matters: a cubic Bezier that happens to be a quadratic, which is
    every Rao parabola expressed in the cubic family, has a vanishing leading coefficient, and
    `np.roots` on a degenerate polynomial returns nonsense rather than the lower-order answer.

    '''

    coefficients = list(coefficients)
    while coefficients and abs(coefficients[0]) < tolerance:
        coefficients.pop(0)
    if len(coefficients) < 2:
        return []
    roots = np.roots(coefficients)
    return [float(root.real) for root in roots if abs(root.imag) < tolerance]

class PrescribedWall:

    '''

    A diverging wall as an ordered run of analytic segments, from the throat plane outward.

    Position along the wall is reported as `segmentIndex + parameter`, which is monotone from the
    throat to the exit. The march uses it for one thing only: refusing an intersection that lands
    upstream of the last wall point it placed, which is how a ray that grazes the wall and re-meets
    an earlier segment is rejected rather than silently accepted.

    Parameters:
    -----------
    segments : list
        `WallSegment` instances in order, each starting where the previous one ended.

    '''

    def __init__(self, segments: list):
        if not segments:
            raise ValueError('A prescribed wall needs at least one segment.')
        self.segments = list(segments)

    def __repr__(self):
        return f'PrescribedWall({len(self.segments)} segments, exit = {self.exitPoint})'

    def point(self, station: float) -> tuple:

        '''

        Position at a station, where a station is `segmentIndex + parameter` [-].

        '''

        index, parameter = self._resolve(station)
        return self.segments[index].point(parameter)

    def angle(self, station: float) -> float:

        '''

        Wall angle at a station [rad].

        '''

        index, parameter = self._resolve(station)
        return self.segments[index].tangentAngle(parameter)

    def _resolve(self, station: float) -> tuple:
        index = int(np.clip(np.floor(station), 0, len(self.segments) - 1))
        return index, float(np.clip(station - index, 0.0, 1.0))

    def intersectRay(self, xOrigin: float, rOrigin: float, slope: float,
                     minimumStation: float = 0.0, tolerance: float = 1e-9) -> tuple:

        '''

        Where a straight characteristic leaving a point first meets the wall.

        The ray is `r = rOrigin + slope * (x - xOrigin)`, which is how a characteristic is drawn
        over one step: straight, at the mean of its end slopes. Every segment is asked for its
        roots in closed form and the first admissible one wins, admissible meaning on the segment,
        downstream of the origin, and past `minimumStation`.

        Parameters:
        -----------
        xOrigin, rOrigin : float
            Point the characteristic leaves from, non-dimensional.
        slope : float
            Slope of the ray, `tan(flowAngle + machAngle)` for a left-running characteristic.
        minimumStation : float
            Intersections at or before this station are rejected.
        tolerance : float
            Slack on the segment ends, so a ray landing exactly on a join is not lost between the
            two segments that share it.

        Returns:
        --------
        tuple : (x, r, wallAngle, station), or None when the ray misses the wall

        '''

        intercept = rOrigin - slope * xOrigin
        best      = None

        for index, segment in enumerate(self.segments):
            for parameter in segment._rayParameters(slope, intercept):
                if not (-tolerance <= parameter <= 1.0 + tolerance):
                    continue
                clamped = float(np.clip(parameter, 0.0, 1.0))
                station = index + clamped
                if station <= minimumStation + tolerance:
                    continue
                x, r = segment.point(clamped)
                if x < xOrigin - tolerance:
                    continue
                if best is None or station < best[3]:
                    best = (x, r, segment.tangentAngle(clamped), station)

        return best

    def sample(self, numPoints: int = 100) -> tuple:

        '''

        The wall as point arrays, for drawing it or handing it to a resampler.

        Points are spread so that each segment carries the same chord error, not so that each
        carries the same length. Those are very different allocations here, and the difference is
        not cosmetic: a throat arc is two per cent of a bell's length and turns through most of
        its total angle, so splitting by length alone gives the arc about five points out of four
        hundred and a straight-line reading of the wall there is off by nearly a thousandth of a
        throat radius. Splitting by length gives the wrong answer in exactly the region the
        characteristics are launched from.

        The error of a chord across a curve of curvature k at spacing h goes as k h^2, so equal
        error per segment wants h proportional to 1 / sqrt(k), which makes the point count
        proportional to `sqrt(arcLength * totalTurning)`. A straight run turns through nothing and
        needs two points, which is what that formula gives it once the floor is applied.

        Parameters:
        -----------
        numPoints : int
            Total points returned, including both ends. Treated as a budget rather than an exact
            count, since every segment gets at least two.

        Returns:
        --------
        tuple : (x, r) arrays, non-dimensional, from the throat plane to the exit

        '''

        lengths = np.array([segment.arcLength() for segment in self.segments])
        turning = np.array([abs(segment.tangentAngle(1.0) - segment.tangentAngle(0.0))
                            for segment in self.segments])
        weights = np.sqrt(lengths * turning)
        if weights.sum() <= 0.0:
            weights = lengths
        share   = weights / weights.sum()
        counts  = np.maximum(2, np.round(share * numPoints).astype(int))

        xPoints, rPoints = [], []
        for segment, count in zip(self.segments, counts):
            parameters = np.linspace(0.0, 1.0, count)
            points     = np.array([segment.point(parameter) for parameter in parameters])
            # Drop the first point of every segment after the first: it is the previous
            # segment's last point and the wall is continuous.
            start = 0 if not xPoints else 1
            xPoints.extend(points[start:, 0])
            rPoints.extend(points[start:, 1])

        return np.array(xPoints), np.array(rPoints)

    @property
    def exitPoint(self) -> tuple:

        '''

        (x, r) at the downstream end of the wall.

        '''

        return self.segments[-1].point(1.0)

    @property
    def exitAngle(self) -> float:

        '''

        Wall angle at the downstream end [rad].

        '''

        return self.segments[-1].tangentAngle(1.0)

    @property
    def endStation(self) -> float:

        '''

        Station of the downstream end, which is the number of segments.

        '''

        return float(len(self.segments))

#--------------------------------------------------------------------------------------------------------------------------#
# -- The walls the families are built on -- #
#--------------------------------------------------------------------------------------------------------------------------#

'''

Constructors take plain numbers rather than a `ThroatGeometry` or a `ContourSolution`, and take a
nozzle length rather than a length fraction. That is deliberate: this module has no NOVA imports
at all, so it cannot participate in an import cycle and can be tested with four floats. Resolving
a length fraction against the conical reference is the caller's job, because the conical reference
is thermodynamics-adjacent bookkeeping and this is geometry.

'''

def raoThroatArc(throatRadius: float, outletCurvature: float, endAngle: float,
                 startAngle: float = 0.0) -> CircularArcSegment:

    '''

    The downstream throat arc, turned from the throat plane to a wall angle.

    Rao's throat is a 1.5 throat-radius entrant arc meeting a 0.382 throat-radius exit arc at the
    throat plane. This is the exit arc, and it is the same one the truncated ideal contour's
    kernel is launched from, so a contour built here and a published bell start from the same
    throat.

    Parameters:
    -----------
    throatRadius : float
        Throat radius, non-dimensional, conventionally 1 [-].
    outletCurvature : float
        Exit arc radius as a multiple of the throat radius [-].
    endAngle : float
        Wall angle the arc is turned to [rad].
    startAngle : float
        Wall angle the arc starts at [rad]. Zero is the throat plane.

    Returns:
    --------
    CircularArcSegment

    '''

    arcRadius = outletCurvature * throatRadius
    return CircularArcSegment(center = (0.0, throatRadius + arcRadius), radius = arcRadius,
                              startAngle = startAngle, endAngle = endAngle)

def thrustOptimizedParabolaWall(throatRadius: float, outletCurvature: float, areaRatio: float,
                                nozzleLength: float, inflectionAngle: float,
                                exitAngle: float) -> PrescribedWall:

    '''

    Rao's canted parabola as a prescribed wall.

    The throat exit arc turned to the inflection angle, then a quadratic Bezier running to the
    exit at the exit angle, with its control point where the two tangents meet. Rao's 1960 point
    is that this shape sits close enough to the true optimum that the difference does not matter
    for performance, which is why most flight bells are drawn this way.

    Parameters:
    -----------
    throatRadius, outletCurvature : float
        Throat geometry, non-dimensional [-].
    areaRatio : float
        Exit area over throat area, which fixes the exit radius [-].
    nozzleLength : float
        Axial distance from the throat plane to the exit, non-dimensional [-].
    inflectionAngle, exitAngle : float
        Wall angles at the inflection point and at the exit [rad].

    Returns:
    --------
    PrescribedWall : the arc and the Bezier, in that order

    '''

    arc = raoThroatArc(throatRadius, outletCurvature, inflectionAngle)
    start = arc.point(1.0)
    end   = (nozzleLength, np.sqrt(areaRatio) * throatRadius)
    return PrescribedWall([arc, QuadraticBezierSegment(start, _tangentIntersection(
        start, inflectionAngle, end, exitAngle), end)])

def bezierBellWall(throatRadius: float, outletCurvature: float, areaRatio: float,
                   nozzleLength: float, inflectionAngle: float, exitAngle: float,
                   inflectionTension: float, exitTension: float) -> PrescribedWall:

    '''

    A cubic-Bezier bell in tangent-magnitude form, which is the family a thrust-optimized contour
    is searched over.

    Four numbers describe the wall past the throat arc: the angle it leaves the arc at, the angle
    it arrives at the exit at, and how far along each of those tangents the two interior control
    points sit, as a fraction of the chord from the inflection point to the exit. The exit point
    itself is fixed by the area ratio and the length, so **every member of this family delivers the
    requested design point exactly** and an optimizer searching it never has to be told about the
    two constraints.

    Setting both tensions to two thirds of the corresponding parabola distances reproduces that
    parabola exactly, so the whole thrust-optimized parabola family lies inside this one.

    Parameters:
    -----------
    throatRadius, outletCurvature : float
        Throat geometry, non-dimensional [-].
    areaRatio : float
        Exit area over throat area [-].
    nozzleLength : float
        Axial distance from the throat plane to the exit, non-dimensional [-].
    inflectionAngle, exitAngle : float
        Wall angles at the inflection point and at the exit [rad].
    inflectionTension, exitTension : float
        Control point distances along each tangent, as a fraction of the inflection-to-exit chord.

    Returns:
    --------
    PrescribedWall : the arc and the cubic, in that order

    '''

    arc   = raoThroatArc(throatRadius, outletCurvature, inflectionAngle)
    start = arc.point(1.0)
    end   = (nozzleLength, np.sqrt(areaRatio) * throatRadius)
    chord = float(np.hypot(end[0] - start[0], end[1] - start[1]))

    firstControl  = (start[0] + inflectionTension * chord * np.cos(inflectionAngle),
                     start[1] + inflectionTension * chord * np.sin(inflectionAngle))
    secondControl = (end[0] - exitTension * chord * np.cos(exitAngle),
                     end[1] - exitTension * chord * np.sin(exitAngle))

    return PrescribedWall([arc, CubicBezierSegment(start, firstControl, secondControl, end)])

def _tangentIntersection(start: tuple, startAngle: float, end: tuple, endAngle: float) -> tuple:

    '''

    Where the tangent at one point meets the tangent at another, which is a quadratic Bezier's
    control point.

    '''

    startSlope, endSlope = np.tan(startAngle), np.tan(endAngle)
    startIntercept = start[1] - startSlope * start[0]
    endIntercept   = end[1] - endSlope * end[0]
    controlX = (endIntercept - startIntercept) / (startSlope - endSlope)
    controlR = (startSlope * endIntercept - endSlope * startIntercept) / (startSlope - endSlope)
    return (float(controlX), float(controlR))

def parabolaAsCubicTensions(start: tuple, control: tuple, end: tuple) -> tuple:

    '''

    The two tensions that make `bezierBellWall` reproduce a given quadratic Bezier exactly.

    A quadratic with control point Q1 is the cubic with `P1 = Q0 + (2/3)(Q1 - Q0)` and
    `P2 = Q2 + (2/3)(Q1 - Q2)`. Expressed as fractions of the chord, those two distances are what
    this returns, and they are where an optimizer over the cubic family should start: at the
    parabola it has to beat.

    Parameters:
    -----------
    start, control, end : tuple
        The quadratic's three control points as (x, r).

    Returns:
    --------
    tuple : (inflectionTension, exitTension)

    '''

    chord = float(np.hypot(end[0] - start[0], end[1] - start[1]))
    inflection = (2.0 / 3.0) * float(np.hypot(control[0] - start[0], control[1] - start[1]))
    exit       = (2.0 / 3.0) * float(np.hypot(control[0] - end[0], control[1] - end[1]))
    return (inflection / chord, exit / chord)
