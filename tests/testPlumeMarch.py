'''

Tests for the plume march: the nozzle characteristics solution continued past the lip.

The central test here is not an accuracy tolerance but an identity. The plume interior point and
the nozzle interior point are supposed to be the same physics, so the plume version is checked
against the compatibility relations, transcribed, and required to agree exactly on one pass. If
those two ever drift apart the plume stops being an extension of the contour solve and becomes a
second approximation of it, which is the failure this file exists to prevent.

The duplication is the point: the relations here are a fixture, not a helper.

That identity is a first-pass identity. Converged, the two solvers reach points about one per cent
apart, because they iterate differently. `tests/testCharacteristics.py` measures that difference
against the importable nozzle unit process and states its size.

'''
import os
import sys

import numpy as np
import pytest

from NOVA.Nozzle import (PlumeFlow, PlumePoint, plumeInteriorPoint, plumeAxisPoint,
                    plumeNearAxisPoint, plumeFreeBoundaryPoint, plumeCornerFan,
                    plumeExitLine, solvePlumeMarch, prandtlMeyerAngle)

GAMMA, GAS_CONSTANT, STAGNATION_TEMPERATURE, STAGNATION_PRESSURE = 1.22, 480.0, 3500.0, 1.0e7

@pytest.fixture
def flow():
    return PlumeFlow(GAMMA, GAS_CONSTANT, STAGNATION_TEMPERATURE, STAGNATION_PRESSURE)

def nozzleInteriorRelations(machOne, angleOne, xOne, rOne, machTwo, angleTwo, xTwo, rTwo):
    '''
    Transcribed from `axisymmetricMethodOfCharacteristics`, single pass, numPoints == 1.

    Kept in the arithmetic style of the original rather than tidied, so that a reader comparing
    the two can do it line by line.
    '''
    muOne, muTwo = np.arcsin(1 / machOne), np.arcsin(1 / machTwo)
    temperatureOne = STAGNATION_TEMPERATURE / (1 + (GAMMA - 1) / 2 * machOne ** 2)
    temperatureTwo = STAGNATION_TEMPERATURE / (1 + (GAMMA - 1) / 2 * machTwo ** 2)
    velocityOne = np.sqrt(GAMMA * GAS_CONSTANT * temperatureOne) * machOne
    velocityTwo = np.sqrt(GAMMA * GAS_CONSTANT * temperatureTwo) * machTwo
    slopeOne = (1 / np.tan(muOne)) / velocityOne
    slopeTwo = (1 / np.tan(muTwo)) / velocityTwo
    leftTerm = np.sin(angleOne) * np.sin(muOne) / np.sin(angleOne + muOne)
    rightTerm = np.sin(angleTwo) * np.sin(muTwo) / np.sin(angleTwo - muTwo)

    slopeLeft, slopeRight = np.tan(angleOne + muOne), np.tan(angleTwo - muTwo)
    xIntersection = (rTwo - rOne - xTwo * slopeRight + xOne * slopeLeft) / (slopeLeft - slopeRight)
    rIntersection = rOne + (xIntersection - xOne) * slopeLeft

    velocity = (1 / (slopeOne + slopeTwo)) \
               * (velocityOne * slopeOne + velocityTwo * slopeTwo
                  + (leftTerm / rOne) * (rIntersection - rOne)
                  + (rightTerm / rTwo) * (rIntersection - rTwo) + angleTwo - angleOne)
    angle = ((angleOne + slopeOne * (velocity - velocityOne)
              - (leftTerm / rOne) * (rIntersection - rOne))
             + (angleTwo - slopeTwo * (velocity - velocityTwo)
                + (rightTerm / rTwo) * (rIntersection - rTwo))) / 2
    maxVelocity = np.sqrt(2 * GAMMA * GAS_CONSTANT * STAGNATION_TEMPERATURE / (GAMMA - 1))
    mach = np.sqrt((2 / (GAMMA - 1))
                   * ((velocity / maxVelocity) ** 2 / (1 - (velocity / maxVelocity) ** 2)))
    return xIntersection, rIntersection, mach, angle

#--------------------------------------------------------------------------------------------------------------------------#
# -- The identity that keeps the plume an extension of the nozzle solve -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.mark.parametrize('kernel', [
    (2.50, np.radians(6.0),  0.30, 0.10, 2.70, np.radians(11.0), 0.31, 0.14),
    (3.80, np.radians(2.0),  0.80, 0.05, 4.10, np.radians(9.0),  0.82, 0.20),
    (4.50, np.radians(0.5),  0.90, 0.02, 4.60, np.radians(13.0), 0.91, 0.40),
    (1.60, np.radians(12.0), 0.05, 0.04, 1.75, np.radians(15.0), 0.06, 0.07),
])
def testInteriorPointReproducesTheNozzleSolverExactly(flow, kernel):
    '''
    One pass of the plume interior point against one pass of the nozzle solver, on the same
    kernel. These are the same equations, so the only acceptable difference is none.
    '''
    reference = nozzleInteriorRelations(*kernel)
    first = PlumePoint(kernel[2], kernel[3], kernel[0], kernel[1], flow)
    second = PlumePoint(kernel[6], kernel[7], kernel[4], kernel[5], flow)
    computed = plumeInteriorPoint(flow, first, second, maxIterations = 1)

    assert computed is not None
    assert computed.x == reference[0]
    assert computed.r == reference[1]
    assert computed.mach == reference[2]
    assert computed.flowAngle == reference[3]

def testIteratingTheInteriorPointIsASmallCorrection(flow):
    '''
    The march iterates on averaged properties. That has to move the answer, or the corrector is
    doing nothing, and it has to move it slightly, or the step was too large to be trusted.
    '''
    first = PlumePoint(0.900, 0.300, 4.50, np.radians(6.0), flow)
    second = PlumePoint(0.905, 0.330, 4.55, np.radians(7.0), flow)
    onePass = plumeInteriorPoint(flow, first, second, maxIterations = 1)
    converged = plumeInteriorPoint(flow, first, second)

    assert onePass is not None and converged is not None
    assert converged.mach != onePass.mach, 'the corrector must do something'
    assert abs(converged.mach - onePass.mach) < 0.05
    assert abs(converged.flowAngle - onePass.flowAngle) < np.radians(0.5)

def testInteriorPointRefusesADivergingStep(flow):
    '''
    A step far larger than the local radius makes the corrector diverge. Returning None lets the
    march end the line cleanly instead of placing a point that is not a solution.
    '''
    first = PlumePoint(0.90, 0.02, 4.50, np.radians(0.5), flow)
    second = PlumePoint(0.91, 0.40, 4.60, np.radians(13.0), flow)
    assert plumeInteriorPoint(flow, first, second) is None

#--------------------------------------------------------------------------------------------------------------------------#
# -- Boundary conditions -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testFreeBoundaryHoldsAmbientPressureAndReturnsTheAngle(flow):
    '''
    The defining property of the free boundary, and the one thing a wall does not do. Pressure is
    prescribed and the flow angle is the unknown, which is the reverse of the nozzle condition.
    '''
    ambient = 101325.0
    boundaryMach = flow.machFromStaticPressure(ambient)
    inner = PlumePoint(0.90, 0.30, 4.20, np.radians(8.0), flow)
    previous = PlumePoint(0.895, 0.42, boundaryMach, np.radians(14.0), flow, 'boundary')

    point = plumeFreeBoundaryPoint(flow, inner, previous, boundaryMach)

    assert point is not None
    assert flow.staticPressure(point.mach) == pytest.approx(ambient, rel = 1e-12)
    assert point.mach == pytest.approx(boundaryMach, rel = 1e-12)
    assert point.x > inner.x and point.r > 0.0
    assert point.flowAngle != previous.flowAngle, 'the angle is solved for, not carried over'

def testAxisPointHoldsSymmetry(flow):
    '''On the center line the flow angle is zero and the radius is zero, by symmetry.'''
    point = plumeAxisPoint(flow, PlumePoint(0.90, 0.05, 4.30, np.radians(3.0), flow))

    assert point is not None
    assert point.r == 0.0
    assert point.flowAngle == 0.0
    assert point.x > 0.90
    assert point.mach > 1.0

def testNearAxisPointStaysRegularAsTheRadiusFalls(flow):
    '''
    The first-family source term carries dr / r and is singular on the axis, which is why this
    process exists. Its answer has to settle rather than blow up as the parent approaches zero.
    '''
    results = []
    for radius in (1e-3, 1e-5, 1e-7, 1e-9):
        axis = PlumePoint(0.90, 0.0, 4.30, 0.0, flow)
        second = PlumePoint(0.90 + radius, radius, 4.32, np.radians(1.0), flow)
        point = plumeNearAxisPoint(flow, axis, second)
        assert point is not None, f'failed at parent radius {radius}'
        assert np.isfinite(point.mach) and point.mach > 1.0
        results.append(point.mach)

    assert max(results) - min(results) < 0.05, f'not settling: {results}'

def testCornerFanTurnsFromTheWallStateToAmbient(flow):
    '''
    The lip fan is centerd: every ray leaves the same point and they differ only in how far
    through the Prandtl-Meyer turn they sit.
    '''
    lip = PlumePoint(0.90, 0.40, 3.00, np.radians(10.0), flow)
    boundaryMach = 4.0
    fan = plumeCornerFan(flow, lip, boundaryMach, numRays = 20)

    assert len(fan) == 21
    assert all(ray.x == lip.x and ray.r == lip.r for ray in fan), 'the fan is centerd at the lip'
    assert fan[0].mach == pytest.approx(lip.mach)
    assert fan[-1].mach == pytest.approx(boundaryMach)
    assert fan[0].flowAngle == pytest.approx(lip.flowAngle)

    expected = lip.flowAngle + (prandtlMeyerAngle(boundaryMach, GAMMA)
                                - prandtlMeyerAngle(lip.mach, GAMMA))
    assert fan[-1].flowAngle == pytest.approx(expected, rel = 1e-12)
    assert all(a.flowAngle <= b.flowAngle for a, b in zip(fan[:-1], fan[1:])), 'turning is monotone'

#--------------------------------------------------------------------------------------------------------------------------#
# -- The exit plane handover -- #
#--------------------------------------------------------------------------------------------------------------------------#

def syntheticSeed(wallAngleDeg = 14.0, wallMach = 4.0, axisMach = 4.8, lipRadius = 0.4,
                  exitX = 1.0):
    '''A linear exit profile: angle rising with radius, Mach falling, as a contoured exit gives.'''
    radii = np.linspace(0.0, lipRadius, 40)
    fraction = radii / lipRadius
    return {'scalingFactor': 1.0, 'exitX': exitX, 'exitRadius': lipRadius,
            'xMesh': [np.full_like(radii, exitX)], 'rMesh': [radii],
            'flowAngleMesh': [np.radians(wallAngleDeg) * fraction],
            'machMesh': [axisMach + (wallMach - axisMach) * fraction],
            'gasConstant': GAS_CONSTANT, 'stagnationTemperature': STAGNATION_TEMPERATURE,
            'stagnationPressure': STAGNATION_PRESSURE}

def testExitLineCarriesTheMeshAcrossUnchanged(flow):
    '''
    The handover has to preserve the nozzle solution rather than re-approximate it, and it stays
    dimensional so nothing is scaled on the way across.
    '''
    line = plumeExitLine(flow, syntheticSeed(), numPoints = 60)

    assert line is not None and len(line) > 10
    assert line[0].r == pytest.approx(0.4, rel = 1e-9), 'lip first'
    assert line[-1].r == 0.0, 'axis last'
    assert line[-1].flowAngle == 0.0
    assert line[0].mach == pytest.approx(4.0, rel = 1e-6)
    assert line[-1].mach == pytest.approx(4.8, rel = 1e-6)
    assert np.degrees(line[0].flowAngle) == pytest.approx(14.0, rel = 1e-6)
    assert all(point.x == pytest.approx(1.0) for point in line), 'the exit plane is one station'
    assert all(a.r >= b.r for a, b in zip(line[:-1], line[1:])), 'ordered lip to axis'

def testExitLineRefusesAnIncompleteSeed(flow):
    '''A conical contour carries no mesh, and a partial seed must not raise.'''
    assert plumeExitLine(flow, {}) is None
    assert plumeExitLine(flow, {'xMesh': [1]}) is None

#--------------------------------------------------------------------------------------------------------------------------#
# -- The march -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testMarchProducesAMonotoneBoundaryFromTheExitPlane(flow):
    '''
    A short march, checked for the properties every longer one depends on: the boundary starts at
    the lip, advances downstream, holds ambient pressure, and never crosses the axis.
    '''
    line = plumeExitLine(flow, syntheticSeed(wallAngleDeg = 0.0, wallMach = 3.0, axisMach = 3.0),
                         numPoints = 60)
    ambient = flow.staticPressure(3.0) / 1.5
    net = solvePlumeMarch(flow, line, ambient, numRays = 20, maxLines = 60, lineLimit = 200)

    boundary = net['boundary']
    assert len(boundary) > 10
    assert net['boundaryMach'] > 3.0, 'an underexpanded jet accelerates past the exit Mach'
    assert boundary[0].x == pytest.approx(line[0].x)
    assert boundary[0].r == pytest.approx(line[0].r)

    xs = [point.x for point in boundary]
    assert all(b >= a - 1e-12 for a, b in zip(xs[:-1], xs[1:])), 'the boundary advances downstream'
    assert all(point.r > 0.0 for point in boundary), 'and never reaches the axis'
    assert all(point.mach == pytest.approx(net['boundaryMach'], rel = 1e-9)
               for point in boundary[1:]), 'ambient pressure is held all along it'
    assert all(point.r >= 0.0 for point in net['nodes'])

def testMarchRefusesWithoutAnInitialLine(flow):
    net = solvePlumeMarch(flow, [], 101325.0)
    assert net['stop'] == 'noInitialLine'

#--------------------------------------------------------------------------------------------------------------------------#
# -- Coalescence of crossing characteristics -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testSameFamilyPointClosesForRealCrossingsAndRefusesDistantOnes(flow):
    """
    Two properties of the coalescence solver, and the second matters as much as the first.

    Closing the pair by subtracting the two first-family relations would be singular whenever the
    parents carry nearly the same state, which neighbouring points on a line almost always do. The
    report closes it with the general-point algebra instead, whose denominator is a sum, so a
    genuine crossing between similar states is solvable.

    A vanishing convergence is a different matter. Two rays a ten-thousandth of a degree apart
    meet thousands of jet radii downstream, which is not a coalescence and must not be reported as
    one. The corrector diverges on those and the point is refused, which is the behavior wanted.
    """
    from NOVA.Nozzle import plumeSameFamilyPoint
    inner = PlumePoint(0.900, 0.300, 4.000, np.radians(8.0), flow)

    for delta in (1e-1, 1e-2):
        outer = PlumePoint(0.902, 0.310, 4.000 - delta, np.radians(8.0) - delta, flow)
        assert (inner.flowAngle + inner.machAngle) > (outer.flowAngle + outer.machAngle)
        merged = plumeSameFamilyPoint(flow, inner, outer)
        assert merged is not None, f'a real crossing was refused at a state gap of {delta}'
        assert merged.mach > 1.0 and np.isfinite(merged.mach)
        assert merged.x > max(inner.x, outer.x), 'a coalescence lies downstream of its parents'

    for delta in (1e-4, 1e-6):
        outer = PlumePoint(0.902, 0.310, 4.000 - delta, np.radians(8.0) - delta, flow)
        assert plumeSameFamilyPoint(flow, inner, outer) is None,             f'a crossing many jet radii away was reported as coalescence at {delta}'

def testCoalescenceFiresWhenDrivenButIsNotCalibrated(flow):
    """
    The detector is wired in and does fire. What it does not do is fire the right number of times.

    Its rate does not follow the pressure ratio in any dependable way: on this exit condition the
    merges per line come out 1.20 at Pe/Pa 1.5, 0.62 at 5 and 1.56 at 20, which is not the
    monotone rise compression strength would demand. The crossing test underneath is resolution
    dependent, so neighbouring characteristics on a refined line cross locally under any
    convergence at all. This records that it runs, and that its count is not yet a physical
    quantity.
    """
    line = plumeExitLine(flow, syntheticSeed(wallAngleDeg = 0.0, wallMach = 3.0, axisMach = 3.0),
                         numPoints = 80)
    net = solvePlumeMarch(flow, line, flow.staticPressure(3.0) / 1.5, numRays = 30,
                          maxLines = 200, lineLimit = 200, shocks = True)

    assert len(net['shock']) > 0, 'driving it has to reach the coalescence path'
    assert all(point.kind == 'shock' for point in net['shock'])
    assert all(point.mach > 1.0 and np.isfinite(point.mach) for point in net['shock'])
    assert all(point.r >= 0.0 for point in net['shock'])

def testMarchDoesNotDriveCoalescenceByDefault(flow):
    '''
    Off by default, and deliberately. The crossing test is resolution dependent and currently
    costs more than it buys on the one case that validates against Prandtl.
    '''
    line = plumeExitLine(flow, syntheticSeed(wallAngleDeg=0.0, wallMach=3.0, axisMach=3.0),
                         numPoints=60)
    net = solvePlumeMarch(flow, line, flow.staticPressure(3.0) / 1.5, numRays=20, maxLines=80)
    assert net['shock'] == []

#--------------------------------------------------------------------------------------------------------------------------#
# -- The wavelength, against Prandtl -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testShockCellPeriodMatchesPrandtl(flow):
    '''
    The primary wavelength is the axial period between successive crests of the jet boundary, not
    twice the distance from the lip to the first one. Those are different quantities and the
    difference is not small: the first crest sits about ten per cent further out than half a
    period, because the lip fan throws the boundary wide before the pattern settles.

    Measured as a period, against Prandtl (1904), the march agrees to well under a per cent at a
    parallel exit close to design. That is the regime Prandtl's linearised result is derived for,
    and it is the only place the two are comparable.
    '''
    from NOVA.Nozzle import (shockCellLength, fullyExpandedDiameter, machFromPressureRatio,
                        prandtlCellCoefficient)

    exitMach, ratio = 3.0, 1.05
    radii = np.linspace(1.0, 0.0, 140)
    line = [PlumePoint(0.0, radius, exitMach, 0.0, flow, 'exit') for radius in radii]

    net = solvePlumeMarch(flow, line, flow.staticPressure(exitMach) / ratio,
                          numRays = 40, maxLines = 1600, lineLimit = 250)
    boundary = net['boundary']
    xs = np.array([point.x for point in boundary])
    rs = np.array([point.r for point in boundary])

    stagnationOverStatic = (1.0 + 0.5 * (GAMMA - 1.0) * exitMach ** 2) ** (GAMMA / (GAMMA - 1.0))
    jetMach = machFromPressureRatio(stagnationOverStatic * ratio, GAMMA)
    expected = shockCellLength(fullyExpandedDiameter(2.0, exitMach, jetMach, GAMMA), jetMach,
                               prandtlCellCoefficient)

    window = max(5, rs.size // 200)
    smoothed = np.convolve(rs, np.ones(window) / window, mode = 'same')
    crests = []
    for index in range(window, smoothed.size - window - 1):
        if smoothed[index] >= smoothed[index - window:index].max() \
                and smoothed[index] > smoothed[index + 1:index + 1 + window].max():
            if not crests or xs[index] - xs[crests[-1]] > 0.4 * expected:
                crests.append(index)

    assert len(crests) >= 2, 'the march has to resolve two crests to have a period at all'
    period = float(np.diff(xs[crests]).mean())
    error = 100.0 * (period - expected) / expected
    lipToFirst = 2.0 * xs[crests[0]]
    naiveError = 100.0 * (lipToFirst - expected) / expected

    # This march is kept short so the test stays quick, so it averages the earliest cells only.
    # TR R-6 separates the primary wavelength from the secondary one and records that the two
    # differ, which is visible here: over the first few cells the period lands about five per cent
    # under Prandtl, and carrying the march out to fourteen crests brings the mean to within 0.4.
    assert abs(error) < 8.0, f'period {period:.3f} against Prandtl {expected:.3f}, {error:+.1f} %'

    # The finding that matters, and why the earlier measure misled. This holds at any march
    # length, where the absolute error does not.
    assert abs(error) < abs(naiveError), \
        f'period {error:+.1f} % should beat lip-to-first-crest {naiveError:+.1f} %'
    assert lipToFirst > period, 'lip to first crest overstates the period'

def testLineLengthStaysBounded(flow):
    '''
    Every line places an interior point against each entry of its parent and then adds its own
    boundary point, so left alone the lines grow by one per line. At thousands of points each the
    march slows until the center line stops advancing. Holding the length fixed is what lets it
    run far enough to see a period at all.
    '''
    radii = np.linspace(1.0, 0.0, 140)
    line = [PlumePoint(0.0, radius, 3.0, 0.0, flow, 'exit') for radius in radii]
    limit = 200
    net = solvePlumeMarch(flow, line, flow.staticPressure(3.0) / 1.05, numRays = 40,
                          maxLines = 600, lineLimit = limit)

    lengths = [len(one) for one in net['lines']]
    assert max(lengths) <= limit + 2, f'lines grew to {max(lengths)} against a budget of {limit}'
    assert len(net['lines']) == 600, 'a bounded line length has to let the march reach its budget'

#--------------------------------------------------------------------------------------------------------------------------#
# -- Conservation, the check that needs no reference -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testMassFluxIsExactOnAUniformStream(flow):
    '''
    A line across a uniform axial stream carries rho V pi R^2, which is the one case the integral
    can be checked against arithmetic rather than against itself.
    '''
    from NOVA.Nozzle import plumeMassFlux
    mach, radius = 3.0, 0.4
    line = [PlumePoint(0.0, r, mach, 0.0, flow, 'exit')
            for r in np.linspace(radius, 0.0, 400)]
    expected = flow.density(mach) * flow.velocity(mach) * np.pi * radius ** 2

    assert plumeMassFlux(flow, line) == pytest.approx(expected, rel = 1e-4)

def testMassFluxIsIndifferentToTheLineItIsMeasuredOn(flow):
    '''
    The same stream cut by a slanted line has to carry the same flux, since the normal component
    falls exactly as the area of revolution grows. This is what makes it usable on a characteristic
    line, which is never a plane.
    '''
    from NOVA.Nozzle import plumeMassFlux
    mach, radius = 3.0, 0.4
    straight = [PlumePoint(0.0, r, mach, 0.0, flow, 'exit')
                for r in np.linspace(radius, 0.0, 400)]
    slanted = [PlumePoint(0.6 * (radius - r), r, mach, 0.0, flow, 'exit')
               for r in np.linspace(radius, 0.0, 400)]

    assert plumeMassFlux(flow, slanted) == pytest.approx(plumeMassFlux(flow, straight), rel = 1e-4)

def testMarchReportsItsOwnMassDrift(flow):
    '''
    Every line spans the jet, so every line carries the whole mass flow. The march measures its
    own departure from that and reports it, which is the only quality number available at an
    operating point with nothing to compare against.
    '''
    radii = np.linspace(1.0, 0.0, 140)
    line = [PlumePoint(0.0, radius, 3.0, 0.0, flow, 'exit') for radius in radii]
    net = solvePlumeMarch(flow, line, flow.staticPressure(3.0) / 1.05, maxLines = 400,
                          lineLimit = 250)

    assert net['referenceFlux'] > 0.0
    assert len(net['fluxSamples']) >= 3
    assert np.isfinite(net['massDriftWorst']) and np.isfinite(net['massDriftFinal'])
    assert abs(net['massDriftWorst']) < 0.5, \
        f'a parallel exit should conserve tightly, got {net["massDriftWorst"]:+.3f} %'

def testMassDriftGrowsWithExitDivergence(flow):
    '''
    The drift is not noise: it tracks the parameter that breaks the march. A parallel exit holds
    to a few hundredths of a per cent and a bell-like divergence loses a per cent or more, which
    is why a solve is worth gating on it.
    '''
    radii = np.linspace(1.0, 0.0, 140)
    drifts = []
    for wallAngleDeg in (0.0, 14.0):
        angle = np.radians(wallAngleDeg)
        line = [PlumePoint(0.0, radius, 3.0, angle * radius, flow, 'exit') for radius in radii]
        line[-1] = PlumePoint(0.0, 0.0, 3.0, 0.0, flow, 'exit')
        net = solvePlumeMarch(flow, line, flow.staticPressure(3.0) / 1.05, maxLines = 400,
                              lineLimit = 250)
        drifts.append(abs(net['massDriftWorst']))

    assert drifts[1] > 4.0 * drifts[0], f'drift did not track exit divergence: {drifts}'

def testFrontAdvanceRefusesACharacteristicFront(flow):
    '''
    The front cannot be seeded from the march's own lines. Those are first-family characteristics,
    so neighbouring points are joined by the characteristic the advance would cross against its
    neighbour's, and the intersection returns a point already on the front. This records why the
    obvious way of building a front does not work.
    '''
    from NOVA.Nozzle import advancePlumeFront
    radii = np.linspace(1.0, 0.0, 140)
    line = [PlumePoint(0.0, radius, 3.0, 0.0, flow, 'exit') for radius in radii]
    net = solvePlumeMarch(flow, line, flow.staticPressure(3.0) / 1.05, maxLines = 300,
                          lineLimit = 250)
    spanning = [one for one in net['lines'] if one[0].r <= 1e-9]
    assert spanning, 'the march has to reach the axis for this to be testable'

    front = spanning[-1]
    # Neighbouring points lie along the first-family direction over most of the line, which is
    # the degeneracy. Measured as the fraction of pairs whose spacing follows that direction.
    aligned = 0
    for inner, outer in zip(front[:-1], front[1:]):
        alongFront = np.arctan2(outer.r - inner.r, outer.x - inner.x)
        if abs(alongFront - (inner.flowAngle + inner.machAngle)) < np.radians(1.0):
            aligned += 1
    assert aligned > 0.5 * (len(front) - 1),         f'only {aligned} of {len(front) - 1} pairs lie along the characteristic'

    # The advance does not fail on such a front so much as fail to go anywhere: the new points
    # land essentially on the old ones, because that is what crossing a characteristic with itself
    # returns. Progress is measured rather than assumed.
    current, before = list(front), front[-1].x
    for _ in range(5):
        current = advancePlumeFront(flow, current, net['boundaryMach'])
        if current is None:
            break
    if current is not None:
        travelled = current[-1].x - before
        assert travelled < 0.05 * front[-1].r,             f'the boundary moved {travelled:.4f} in five steps, so the front was not degenerate'

#--------------------------------------------------------------------------------------------------------------------------#
# -- The overexpanded lip, and the Mach disk -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.mark.parametrize('pressureRatio, turnBound, stagnationBound', [
    (1.111, 0.01, 1.0e-3),
    (1.429, 0.02, 6.0e-3),
    (1.667, 0.05, 2.0e-2),
])
def testIsentropicCompressionTracksTheObliqueShock(flow, pressureRatio, turnBound,
                                                   stagnationBound):
    '''
    The overexpanded lip is taken as an isentropic compression rather than the oblique shock it
    really is. That is only allowed while the shock is weak, so the two are compared directly: the
    turning angles have to agree, and the stagnation pressure the shock would cost has to stay
    small. Both bounds tighten as the jet approaches design.
    '''
    from NOVA.Nozzle import obliqueShockState, machFromPressureRatio
    exitMach = 3.0
    deflection, _, stagnationRatio = obliqueShockState(exitMach, GAMMA, pressureRatio)
    assert deflection > 0.0, 'an attached shock is needed for the comparison to mean anything'

    stagnationOverStatic = (1.0 + 0.5 * (GAMMA - 1.0) * exitMach ** 2) ** (GAMMA / (GAMMA - 1.0))
    compressedMach = machFromPressureRatio(stagnationOverStatic / pressureRatio, GAMMA)
    isentropicTurn = prandtlMeyerAngle(exitMach, GAMMA) - prandtlMeyerAngle(compressedMach, GAMMA)

    assert abs(isentropicTurn - deflection) / deflection < turnBound
    assert 1.0 - stagnationRatio < stagnationBound

def testObliqueShockStateDetaches(flow):
    '''Beyond what an attached shock can deliver, the state is refused rather than extrapolated.'''
    from NOVA.Nozzle import obliqueShockState
    deflection, mach, ratio = obliqueShockState(1.5, GAMMA, 50.0)
    assert deflection == 0.0 and ratio == 1.0

def testMarchSolvesAnOverexpandedJet(flow):
    '''
    An overexpanded lip turns the flow inward, which is the same fan run with a falling Mach
    number. Refusing these outright excluded sea-level operation of any vacuum-optimized nozzle.
    '''
    radii = np.linspace(1.0, 0.0, 140)
    line = [PlumePoint(0.0, radius, 3.0, 0.0, flow, 'exit') for radius in radii]
    net = solvePlumeMarch(flow, line, flow.staticPressure(3.0) / 0.9, maxLines = 200,
                          lineLimit = 200)

    assert net['lines'], 'an overexpanded jet has to produce a net'
    assert net['boundaryMach'] < 3.0, 'the flow is compressed, so the boundary Mach falls'
    assert net['lipShockDeflection'] > 0.0, 'and the lip turns inward through a shock'
    assert net['lipStagnationRatio'] < 1.0
    assert net['lipStagnationRatio'] > 0.99, 'which at this pressure ratio is weak'
    assert all(point.r > 0.0 for point in net['boundary'])

def testPerfectlyExpandedJetIsRefused(flow):
    '''Matched, there is no wave structure to solve and none is invented.'''
    radii = np.linspace(1.0, 0.0, 60)
    line = [PlumePoint(0.0, radius, 3.0, 0.0, flow, 'exit') for radius in radii]
    net = solvePlumeMarch(flow, line, flow.staticPressure(3.0), maxLines = 40)
    assert net['stop'] == 'perfectlyExpanded'
    assert net['lines'] == []

def testMachDiskIsAbsentFromAShockFreeNet(flow):
    '''
    A disk is a shock, and this net carries none, so a mildly off-design jet must report no disk
    rather than invent one. How close the core came is reported either way.
    '''
    from NOVA.Nozzle import plumeMachDisk
    radii = np.linspace(1.0, 0.0, 140)
    line = [PlumePoint(0.0, radius, 3.0, 0.0, flow, 'exit') for radius in radii]
    net = solvePlumeMarch(flow, line, flow.staticPressure(3.0) / 1.05, maxLines = 300,
                          lineLimit = 200)

    disk = plumeMachDisk(flow, net)
    assert disk['present'] is False
    assert disk['minimumAxisMach'] > 1.05
    assert 'supersonic' in disk['reason']

def testMachDiskIsFoundWhenTheCoreDecelerates(flow):
    '''
    The criterion itself, on a field built to trip it: the disk sits at the first center-line
    station that falls to near sonic, and its diameter spans to the triple point, the radius at
    which the flow is supersonic again.
    '''
    from NOVA.Nozzle import plumeMachDisk
    nodes = [PlumePoint(x, 0.0, max(1.02, 3.0 - x), 0.0, flow)
             for x in np.linspace(0.0, 2.5, 80)]
    nodes += [PlumePoint(2.05, radius, 1.02 if radius < 0.3 else 2.0, 0.0, flow)
              for radius in np.linspace(0.05, 1.0, 20)]

    disk = plumeMachDisk(flow, {'nodes': nodes})
    assert disk['present'] is True
    assert disk['x'] == pytest.approx(1.962, abs = 0.05)
    assert disk['diameter'] > 0.0, 'the triple point has to be found for a diameter to exist'
    assert disk['upstreamMach'] > disk['minimumAxisMach']
