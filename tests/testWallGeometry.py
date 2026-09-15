'''

Tests for the prescribed wall geometry the thrust-optimized families are marched against.

Nothing here is a physical model, so there is nothing to check against experiment. What can be
wrong is the arithmetic, and these bound it three ways: against the construction this module
replaces, against brute force, and against the closed forms the module claims to be exact.

The containment test is the one that matters most beyond this file. A thrust-optimized contour is
only worth generating if it can beat a thrust-optimized parabola, and that question has an answer
only because every parabola is a member of the cubic family the optimizer searches. If that stops
being true the optimization becomes a race between two search procedures rather than a comparison
of two contour families.

'''
import numpy as np
import pytest

from NOVA.contour import raoParabolicContour, raoWallAngles
from NOVA.contourKernel import ThroatGeometry
from NOVA.gasDynamics import conicalLength
from NOVA.wallGeometry import (CircularArcSegment, CubicBezierSegment, LineSegment,
                               PrescribedWall, QuadraticBezierSegment, bezierBellWall,
                               parabolaAsCubicTensions, raoThroatArc,
                               thrustOptimizedParabolaWall)

GAMMA = 1.1475421191138746

@pytest.fixture
def throat():
    return ThroatGeometry(GAMMA)

@pytest.fixture
def designPoint(throat):
    '''The worked LOX/LH2 design point: area ratio 40 at an 80 per cent bell.'''
    areaRatio, lengthFraction = 40.0, 0.80
    inflectionAngle, exitAngle, _ = raoWallAngles(areaRatio, lengthFraction)
    nozzleLength = lengthFraction * conicalLength(areaRatio, throat.throatRadius)
    return areaRatio, lengthFraction, nozzleLength, inflectionAngle, exitAngle

@pytest.fixture
def parabolicWall(throat, designPoint):
    areaRatio, _, nozzleLength, inflectionAngle, exitAngle = designPoint
    return thrustOptimizedParabolaWall(throat.throatRadius, throat.outletCurvature, areaRatio,
                                       nozzleLength, inflectionAngle, exitAngle)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Against the construction it replaces -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testParabolicWallReproducesTheExistingConstruction(throat, designPoint, parabolicWall):
    '''
    The same Rao canted parabola, built two ways. `contour.raoParabolicContour` is the existing
    construction and is covered by its own tests, so agreement here means the wall this module
    hands the marcher is the wall the rest of NOVA already compares against.

    The two are compared by radius at common axial stations rather than point for point, because
    they distribute their points along the curve differently on purpose.
    '''
    areaRatio, lengthFraction, _, _, _ = designPoint
    xNew, rNew = parabolicWall.sample(400)
    xOld, rOld = raoParabolicContour(throat, areaRatio, lengthFraction, 1.0, numPoints = 400)

    stations = np.linspace(max(xNew[0], xOld[0]), min(xNew[-1], xOld[-1]), 500)
    difference = np.abs(np.interp(stations, xNew, rNew) - np.interp(stations, xOld, rOld))
    assert np.max(difference) < 5e-5

def testParabolicWallDeliversItsDesignPointExactly(designPoint, parabolicWall):
    '''
    The exit point is an input to the construction rather than an outcome of it, so the delivered
    area ratio and length are exact rather than converged. This is the property that lets the
    optimizer treat both design constraints as absorbed and search an unconstrained box.
    '''
    areaRatio, _, nozzleLength, _, exitAngle = designPoint
    exitX, exitR = parabolicWall.exitPoint

    assert exitX == pytest.approx(nozzleLength, rel = 1e-15)
    assert exitR ** 2 == pytest.approx(areaRatio, rel = 1e-15)
    assert parabolicWall.exitAngle == pytest.approx(exitAngle, abs = 1e-12)

def testTheWallLeavesTheThroatArcAtTheRequestedInflectionAngle(designPoint, parabolicWall):
    _, _, _, inflectionAngle, _ = designPoint
    arc = parabolicWall.segments[0]
    assert arc.tangentAngle(1.0) == pytest.approx(inflectionAngle, abs = 1e-12)
    # The Bezier has to leave at the same angle, or the wall has a corner the mesh would see.
    assert parabolicWall.segments[1].tangentAngle(0.0) == pytest.approx(inflectionAngle, abs = 1e-9)

def testTheThroatArcStartsParallelToTheAxis(throat):
    '''At the throat plane the wall is parallel to the axis, which is what makes it the throat.'''
    arc = raoThroatArc(throat.throatRadius, throat.outletCurvature, np.radians(30.0))
    x, r = arc.point(0.0)
    assert x == pytest.approx(0.0, abs = 1e-15)
    assert r == pytest.approx(throat.throatRadius, rel = 1e-15)
    assert arc.tangentAngle(0.0) == pytest.approx(0.0, abs = 1e-15)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The two questions the march asks, answered exactly -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTangentAngleMatchesADifferenceOfThePoint(parabolicWall):
    '''
    The tangent is claimed to be exact rather than differenced. Differencing it anyway has to
    agree, and the agreement bounds any error in the derivative expressions.
    '''
    worst = 0.0
    for station in np.linspace(0.02, parabolicWall.endStation - 0.02, 200):
        step = 1e-6
        aheadX, aheadR = parabolicWall.point(station + step)
        behindX, behindR = parabolicWall.point(station - step)
        differenced = np.arctan2(aheadR - behindR, aheadX - behindX)
        worst = max(worst, abs(differenced - parabolicWall.angle(station)))
    assert np.degrees(worst) < 1e-5

def testRayIntersectionMatchesABruteForceScan(parabolicWall):
    '''
    The closed-form intersection against a dense scan of the same wall for a sign change in the
    ray residual. The scan resolves the wall to 5e-5 of a station, so agreement at that level
    means the closed form is the more accurate of the two and the scan is what limits the check.
    '''
    generator = np.random.default_rng(7)
    stations = np.linspace(0.0, parabolicWall.endStation, 40000)
    points = np.array([parabolicWall.point(station) for station in stations])

    worst, checked = 0.0, 0
    for _ in range(120):
        xOrigin = generator.uniform(0.0, parabolicWall.exitPoint[0] * 0.8)
        rOrigin = generator.uniform(0.0, 0.5)
        slope = generator.uniform(0.05, 1.5)

        hit = parabolicWall.intersectRay(xOrigin, rOrigin, slope)
        if hit is None:
            continue

        residual = points[:, 1] - (rOrigin + slope * (points[:, 0] - xOrigin))
        crossings = np.where(np.sign(residual[:-1]) != np.sign(residual[1:]))[0]
        downstream = [index for index in crossings if points[index, 0] >= xOrigin - 1e-9]
        if not downstream:
            continue

        worst = max(worst, abs(stations[downstream[0]] - hit[3]))
        checked += 1

    assert checked > 40, f'only {checked} rays hit the wall, the test is not exercising anything'
    assert worst < 2e-4

def testAnIntersectionLandsOnTheWall(parabolicWall):
    '''Whatever the routine returns has to be a point of the wall, at the angle it reports.'''
    hit = parabolicWall.intersectRay(0.5, 0.3, 0.6)
    assert hit is not None
    x, r, angle, station = hit
    wallX, wallR = parabolicWall.point(station)
    assert (x, r) == pytest.approx((wallX, wallR), abs = 1e-12)
    assert angle == pytest.approx(parabolicWall.angle(station), abs = 1e-12)

def testARayIsRejectedBeforeTheStationItIsGiven(parabolicWall):
    '''
    The march refuses an intersection upstream of the last wall point it placed. Without it a ray
    that grazes the wall can land on a segment already passed and the mesh folds silently.
    '''
    hit = parabolicWall.intersectRay(0.5, 0.3, 0.6)
    assert hit is not None
    later = parabolicWall.intersectRay(0.5, 1.4, 0.6, minimumStation = hit[3] + 0.1)
    assert later is None or later[3] > hit[3]

def testARayPointedAwayFromTheWallMisses(parabolicWall):
    assert parabolicWall.intersectRay(0.5, 0.3, -0.1) is None

#--------------------------------------------------------------------------------------------------------------------------#
# -- Containment: every parabola is a cubic -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheCubicFamilyContainsTheParabolaExactly(throat, designPoint, parabolicWall):
    '''
    A quadratic Bezier with control point Q1 is the cubic with P1 = Q0 + (2/3)(Q1 - Q0) and
    P2 = Q2 + (2/3)(Q1 - Q2). Reproducing the parabola to machine precision is what makes the
    optimum over the cubic family at least as good as the parabola by construction, so that a
    thrust-optimized contour failing to beat a thrust-optimized parabola is a statement about the
    search rather than about the families.
    '''
    areaRatio, _, nozzleLength, inflectionAngle, exitAngle = designPoint
    quadratic = parabolicWall.segments[1]
    start, control, end = (tuple(point) for point in quadratic.points)
    inflectionTension, exitTension = parabolaAsCubicTensions(start, control, end)

    cubicWall = bezierBellWall(throat.throatRadius, throat.outletCurvature, areaRatio,
                               nozzleLength, inflectionAngle, exitAngle,
                               inflectionTension, exitTension)

    for station in np.linspace(1.0, 2.0, 200):
        assert cubicWall.point(station) == pytest.approx(parabolicWall.point(station), abs = 1e-12)

def testACubicBellDeliversItsDesignPointForAnyTension(throat, designPoint):
    '''
    The area ratio and the length are fixed by the exit control point, so no interior control
    point can move them. This is why the optimizer sees a box rather than an equality-constrained
    problem, and it has to hold across the whole box rather than at the incumbent.
    '''
    areaRatio, _, nozzleLength, inflectionAngle, exitAngle = designPoint

    for inflectionTension in (0.15, 0.4, 0.85):
        for exitTension in (0.15, 0.4, 0.85):
            wall = bezierBellWall(throat.throatRadius, throat.outletCurvature, areaRatio,
                                  nozzleLength, inflectionAngle, exitAngle,
                                  inflectionTension, exitTension)
            exitX, exitR = wall.exitPoint
            assert exitX == pytest.approx(nozzleLength, rel = 1e-15)
            assert exitR ** 2 == pytest.approx(areaRatio, rel = 1e-15)
            assert wall.exitAngle == pytest.approx(exitAngle, abs = 1e-12)

def testADegenerateCubicStillIntersects(throat, designPoint, parabolicWall):
    '''
    A cubic reproducing a parabola has a vanishing leading coefficient, and `np.roots` on a
    polynomial whose leading coefficient is zero returns nonsense rather than the lower-order
    answer. The root finder drops leading zeros for exactly this case, which is not an edge case
    here: it is the optimizer's starting point.
    '''
    areaRatio, _, nozzleLength, inflectionAngle, exitAngle = designPoint
    quadratic = parabolicWall.segments[1]
    start, control, end = (tuple(point) for point in quadratic.points)
    tensions = parabolaAsCubicTensions(start, control, end)
    cubicWall = bezierBellWall(throat.throatRadius, throat.outletCurvature, areaRatio,
                               nozzleLength, inflectionAngle, exitAngle, *tensions)

    onParabola = parabolicWall.intersectRay(0.5, 0.3, 0.6)
    onCubic = cubicWall.intersectRay(0.5, 0.3, 0.6)
    assert onCubic is not None
    assert onCubic[0] == pytest.approx(onParabola[0], abs = 1e-9)
    assert onCubic[1] == pytest.approx(onParabola[1], abs = 1e-9)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Sampling -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testSamplingGivesTheThroatArcPointsInProportionToItsTurningNotItsLength(parabolicWall):
    '''
    The arc is about two per cent of the wall's length and carries more than half its turning.
    Splitting points by length alone leaves it with a handful, and a chord across it then misreads
    the wall by nearly a thousandth of a throat radius in the region the characteristics are
    launched from.
    '''
    arc, bell = parabolicWall.segments
    assert arc.arcLength() / bell.arcLength() < 0.05

    x, _ = parabolicWall.sample(400)
    inArc = int(np.sum(x <= arc.point(1.0)[0] + 1e-12))
    assert inArc > 20, f'only {inArc} of 400 points landed on the throat arc'

def testSamplingIsMonotoneAndClosedAtBothEnds(parabolicWall):
    x, r = parabolicWall.sample(200)
    assert np.all(np.diff(x) > 0)
    assert np.all(np.diff(r) > 0)
    assert (x[0], r[0]) == pytest.approx(parabolicWall.point(0.0), abs = 1e-12)
    assert (x[-1], r[-1]) == pytest.approx(parabolicWall.exitPoint, abs = 1e-12)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The segment primitives on their own -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testALineIsIntersectedWhereItShouldBe():
    wall = PrescribedWall([LineSegment((0.0, 1.0), (4.0, 3.0))])
    # A ray from the axis at 45 degrees meets r = 1 + x/2 at x = 2.
    hit = wall.intersectRay(0.0, 0.0, 1.0)
    assert hit is not None
    assert hit[0] == pytest.approx(2.0, rel = 1e-12)
    assert hit[1] == pytest.approx(2.0, rel = 1e-12)
    assert hit[2] == pytest.approx(np.arctan2(2.0, 4.0), rel = 1e-12)

def testAnArcIsIntersectedWhereItShouldBe():
    # Unit circle centerd at (0, 2): a horizontal ray at r = 2 meets it at x = 1.
    wall = PrescribedWall([CircularArcSegment(center = (0.0, 2.0), radius = 1.0,
                                              startAngle = 0.0, endAngle = np.pi / 2)])
    hit = wall.intersectRay(-1.0, 2.0, 0.0)
    assert hit is not None
    assert hit[0] == pytest.approx(1.0, abs = 1e-12)
    assert hit[1] == pytest.approx(2.0, abs = 1e-12)
    assert hit[2] == pytest.approx(np.pi / 2, abs = 1e-12)

@pytest.mark.parametrize('segment', [
    QuadraticBezierSegment((0.0, 1.0), (1.0, 1.6), (2.0, 1.7)),
    CubicBezierSegment((0.0, 1.0), (0.7, 1.4), (1.4, 1.65), (2.0, 1.7)),
])
def testBezierEndpointsAreItsOuterControlPoints(segment):
    assert segment.point(0.0) == pytest.approx((0.0, 1.0), abs = 1e-15)
    assert segment.point(1.0) == pytest.approx((2.0, 1.7), abs = 1e-15)

def testAWallNeedsAtLeastOneSegment():
    with pytest.raises(ValueError):
        PrescribedWall([])
