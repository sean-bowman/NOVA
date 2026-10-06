'''

Tests for the throat geometry and the transonic starting line.

The starting line is the one place in a contour generator where the accuracy is fixed before any
characteristic is drawn, so most of what is here is about establishing what NOVA's choice actually
is rather than only that it runs. Two tests record quantities that the documentation makes claims
about, so that a claim and the code cannot drift apart silently.

'''
import os
import sys

import numpy as np
import pytest

from NOVA.characteristics import CharacteristicGas
from NOVA.contourKernel import (ThroatGeometry, sauerLimitingCharacteristic,
                           limitingCharacteristicIntersection, throatIntersection,
                           transonicConvergingWallMach, transonicModels, transonicThroatVelocity,
                           transonicWallMach)

GAMMA, GAS_CONSTANT, STAGNATION_TEMPERATURE = 1.1475421191138746, 692.0, 3512.0

@pytest.fixture
def gas():
    return CharacteristicGas(GAMMA, GAS_CONSTANT, STAGNATION_TEMPERATURE)

@pytest.fixture
def throat():
    return ThroatGeometry(GAMMA)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Throat geometry -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testDefaultsAreTheRaoThroat(throat):
    '''
    A 1.5 throat-radius entrant arc and a 0.382 throat-radius exit arc. These are Rao's preferred
    throat geometry and the same two numbers the thrust-optimized parabolic construction uses, so
    a contour built here and a published bell start from the same throat.
    '''
    assert throat.inletCurvature == 1.5
    assert throat.outletCurvature == 0.382
    assert throat.throatRadius == 1.0

def testSauerConstantsMatchTheirDefinitions(throat):
    '''
    The two constants Sauer's solution is written in terms of, checked against the arithmetic
    written out rather than against a stored value.
    '''
    expectedEpsilon = (1.0 / 8) * np.sqrt(2 * (GAMMA + 1) * 1.0 / 1.5)
    expectedFlowParameter = np.sqrt(2 / ((GAMMA + 1) * 1.0 * 1.5))
    assert throat.sauerEpsilon == pytest.approx(expectedEpsilon, rel = 1e-14)
    assert throat.sauerFlowParameter == pytest.approx(expectedFlowParameter, rel = 1e-14)

def testThroatArcPointsLieOnTheirCircle(throat):
    '''
    Geometry, checkable exactly: every point of the downstream arc sits at the arc radius from the
    arc center, and the arc starts at the throat plane with the wall parallel to the axis.
    '''
    angles = np.linspace(0.0, np.radians(35.0), 40)
    x, r = throat.wallPoints(angles)

    assert x[0] == pytest.approx(0.0, abs = 1e-15)
    assert r[0] == pytest.approx(throat.throatRadius, rel = 1e-14)
    distance = np.hypot(x, r - throat.exitArcCenterRadius)
    assert np.allclose(distance, throat.exitArcRadius, atol = 1e-14)

def testThroatArcTurnsTheWallByTheRequestedAngle(throat):
    '''
    The wall angle at a point of the arc has to be the angle that point was placed at, which is
    what lets the inflection be specified as an angle rather than a position.
    '''
    requested = np.radians(28.0)
    x, r = throat.wallPoints(np.linspace(0.0, requested, 400))
    measured = np.arctan2(np.gradient(r), np.gradient(x))[-1]
    assert measured == pytest.approx(requested, rel = 2e-3)

def testCurvatureRatioCarriesIntoTheSauerConstants():
    '''
    A blunter throat gives a flatter transonic profile. Both constants have to move with the
    entrant curvature, or the transonic solution is not seeing the geometry at all.
    '''
    sharp = ThroatGeometry(GAMMA, inletCurvature = 0.5)
    blunt = ThroatGeometry(GAMMA, inletCurvature = 5.0)
    assert sharp.sauerFlowParameter > blunt.sauerFlowParameter
    assert sharp.sauerEpsilon > blunt.sauerEpsilon

#--------------------------------------------------------------------------------------------------------------------------#
# -- The transonic starting line -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testStartingLineIsSonicOnTheAxisAndSupersonicAtTheWall(gas, throat):
    '''
    Sauer's line reaches Mach 1 exactly on the axis and about 1.18 at the wall for this throat.

    The axis value is the reason the march cannot be started there: at Mach 1 the characteristics
    are degenerate, the Mach angle is 90 degrees and its tangent is unbounded. The kernel is
    started at the wall instead, and how much that matters is a question for the contour
    validation rather than for this test.
    '''
    assert sauerLimitingCharacteristic(gas, throat, 0.0) == pytest.approx(1.0, abs = 1e-9)
    assert sauerLimitingCharacteristic(gas, throat, 1.0) == pytest.approx(1.1825, abs = 1e-3)

def testStartingLineMachRisesMonotonicallyWithRadius(gas, throat):
    machNumbers = [sauerLimitingCharacteristic(gas, throat, radius)
                   for radius in np.linspace(0.0, 1.0, 25)]
    assert all(later > earlier for earlier, later in zip(machNumbers, machNumbers[1:]))

def testStartingLineLeansUpstreamAsRadiusGrows(gas, throat):
    '''
    The wall goes supersonic ahead of the axis in a nozzle with a curved throat, so the starting
    line runs from the throat plane at the wall to a station downstream of it on the axis. A line
    leaning the other way would mean the transonic solution has its sign wrong.
    '''
    onAxis = sauerLimitingCharacteristic(gas, throat, 0.0, returnAxialLocation = True)
    atWall = sauerLimitingCharacteristic(gas, throat, 1.0, returnAxialLocation = True)
    assert atWall == pytest.approx(0.0, abs = 1e-14)
    assert onAxis == pytest.approx(throat.sauerEpsilon, rel = 1e-14)
    assert onAxis > atWall

def testTheNeglectedTransonicTermAtThisCurvature():
    '''
    Sauer's solution is the first-order term of the series Kliegel and Quan give as

        u(0,1) = 1 + 1 / (4R) + (14 gamma + 15) / (288 R^2) + O(R^-3)

    for the throat wall velocity, with R the throat wall radius of curvature over the throat
    radius. At NOVA's R of 1.5 the term Sauer retains contributes 0.1667 and the first term he
    drops contributes 0.0479, so the neglected term is 29 per cent of the retained correction.

    This test carries no assertion about the solver. It exists so that the number quoted in
    docs/NozzleContourMethods.md is computed rather than remembered.
    '''
    curvature = 1.5
    retained = 1.0 / (4.0 * curvature)
    neglected = (14.0 * GAMMA + 15.0) / (288.0 * curvature ** 2)
    assert retained == pytest.approx(0.16667, abs = 1e-5)
    assert neglected == pytest.approx(0.04794, abs = 1e-5)
    assert neglected / retained == pytest.approx(0.2876, abs = 1e-3)

def testTheSeriesMisbehavesAtSmallCurvatureWhichIsWhyItsRangeIsStated():
    '''
    Kliegel and Quan note that the series is ill-behaved for small R: taken literally the throat
    wall velocity maximizes near R = 1 and turns subsonic below about R = 0.5, which is
    impossible. Kliegel and Levine recast it in powers of R + 1 to fix that.

    NOVA runs at R = 1.5, above the range where the reformulation is needed, which is the reason
    the plain series is admissible here at all.
    '''
    def wallVelocity(curvature):
        return 1.0 + 1.0 / (4.0 * curvature) + (14.0 * GAMMA + 15.0) / (288.0 * curvature ** 2)

    assert wallVelocity(0.3) > wallVelocity(1.0), 'the series is not monotone at small curvature'
    assert wallVelocity(1.5) > 1.0
    assert wallVelocity(10.0) == pytest.approx(1.0, abs = 0.03)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Intersections -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testCharacteristicMeetsTheStartingLineOnTheStartingLine(gas, throat):
    '''
    Whatever radius the intersection is found at, the axial position returned has to be the
    starting line evaluated there. That is a consistency check the solve would otherwise never
    make on itself.
    '''
    radius, axial, mach = limitingCharacteristicIntersection(
        gas, throat, 1.4, np.radians(3.0), 0.05, 0.85)

    expectedAxial = sauerLimitingCharacteristic(gas, throat, radius, returnAxialLocation = True)
    assert axial == pytest.approx(expectedAxial, rel = 1e-12)
    assert mach == pytest.approx(sauerLimitingCharacteristic(gas, throat, radius), rel = 1e-12)
    assert 0.0 < radius <= 1.0

def testCharacteristicMeetsTheThroatArcOnTheThroatArc(gas, throat):
    '''
    Same idea at the wall: the point returned has to sit on the circle, and the wall angle
    returned has to be the arc's own angle there.
    '''
    result = throatIntersection(gas, throat, 1.30, np.radians(2.0), 0.02, 0.90)
    assert result is not False
    mach, wallAngle, x, r = result

    distance = np.hypot(x, r - throat.exitArcCenterRadius)
    assert distance == pytest.approx(throat.exitArcRadius, rel = 1e-9)
    assert wallAngle == pytest.approx(np.arcsin(x / throat.exitArcRadius), rel = 1e-9)
    assert mach > 1.0

def testStartingLineIntersectionIsIndependentOfWhereTheCharacteristicStarted(gas, throat):
    '''
    Two characteristics leaving different points along the same line must not land on the same
    place. A solver that returned its initial guess regardless would pass every test above and
    fail this one.
    '''
    first = limitingCharacteristicIntersection(gas, throat, 1.4, np.radians(3.0), 0.05, 0.85)
    second = limitingCharacteristicIntersection(gas, throat, 1.4, np.radians(3.0), 0.05, 0.60)
    assert first[0] != second[0]

#--------------------------------------------------------------------------------------------------------------------------#
# -- The transonic near-wall state on the entrant arc -- #
#--------------------------------------------------------------------------------------------------------------------------#

def machFromSpeedRatio(speedRatio: float) -> float:
    return float(np.sqrt(2.0 * speedRatio**2 / ((GAMMA + 1.0) - (GAMMA - 1.0) * speedRatio**2)))

@pytest.mark.parametrize('model', transonicModels)
@pytest.mark.parametrize('curvature', [1.0, 1.5, 2.0])
def testTheWallMachAtTheThroatIsTheThroatWallVelocity(model, curvature):
    '''
    At the geometric throat the wall is parallel to the axis, so the radial velocity has to vanish
    and the speed has to be the throat-wall velocity every model writes down. Exactly, because the
    flow parameter is inverted from that velocity.
    '''
    mach = float(transonicWallMach(0.0, 1.0, GAMMA, curvature, model))
    assert mach == pytest.approx(machFromSpeedRatio(transonicThroatVelocity(GAMMA, curvature, model)),
                                 rel = 1e-12)

@pytest.mark.parametrize('curvature', [1.0, 1.5, 2.0])
def testTheWallGoesSonicAheadOfTheThroatWhereSauerPutsIt(curvature):
    '''
    Sauer puts the point where the axial velocity on the wall reaches the sonic speed
    sqrt((gamma + 1) / (32 R)) throat radii ahead of the geometric throat. The wall speed, which
    carries the radial component as well, has to be sonic slightly further upstream, and
    supersonic from there to the throat.
    '''
    throat = ThroatGeometry(GAMMA, 1.0, curvature)
    alpha, epsilon = throat.sauerFlowParameter, throat.sauerEpsilon
    offset = -np.sqrt((GAMMA + 1.0) / (32.0 * curvature))
    axialVelocity = 1.0 + alpha * (offset - epsilon) + ((GAMMA + 1.0) / 4.0) * alpha**2
    assert axialVelocity == pytest.approx(1.0, abs = 1e-12)

    axial = np.linspace(-0.6, 0.0, 6001)
    mach = transonicWallMach(axial, np.ones_like(axial), GAMMA, curvature)
    sonic = float(np.interp(1.0, mach, axial))
    assert offset - 0.1 < sonic < offset
    assert np.all(mach[axial > sonic] > 1.0)

def testTheBlendLeavesTheConeAndTheThroatPlaneAlone():
    '''
    Upstream of the arc the state stays one-dimensional, and the stations at and past the throat
    plane are not the converging section's to change.
    '''
    curvature, arcStart = 1.5, -0.75
    axial = np.array([-2.0, -1.0, arcStart, 0.0, 0.1])
    oneDimensional = np.array([0.3, 0.5, 0.6, 1.0, 1.2])
    blended = transonicConvergingWallMach(axial, np.ones_like(axial), oneDimensional, GAMMA,
                                          curvature, arcStart)
    assert blended == pytest.approx(oneDimensional, rel = 1e-14)

def testTheBlendTendsToTheTransonicStateAtTheThroat():
    '''
    Approaching the throat the taper weight goes to one, so the blended state meets the transonic
    one there: which is the starting line's throat-wall state, so the near-wall state is continuous
    into the characteristics net rather than jumping from a sonic one-dimensional value.
    '''
    curvature, arcStart = 1.5, -0.75
    near = np.array([-1e-6])
    blended = transonicConvergingWallMach(near, np.ones(1), np.array([0.99]), GAMMA, curvature, arcStart)
    throatWall = machFromSpeedRatio(transonicThroatVelocity(GAMMA, curvature, 'sauer'))
    assert float(blended[0]) == pytest.approx(throatWall, rel = 1e-5)
    assert throatWall > 1.15

def testTheBlendRefusesAnArcThatStartsDownstream():
    with pytest.raises(ValueError):
        transonicConvergingWallMach(np.array([-0.1]), np.ones(1), np.array([0.9]), GAMMA, 1.5, 0.2)
