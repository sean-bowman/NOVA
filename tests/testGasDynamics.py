'''

Tests for the elementary perfect-gas relations.

These are closed-form expressions, so almost everything here is checked against a published value
or against an exact analytic property rather than against a tolerance pulled from a previous run.
Where a published number is used, its source is named in the test.

'''
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'NOVANozzleDesigner'))

from gasDynamics import (stagnationRatio, staticTemperatureRatio, staticPressureRatio,
                         machFromPressureRatio, machAngle, prandtlMeyerAngle,
                         machFromPrandtlMeyerAngle, areaMachRelation, radiusMachRelation,
                         machFromAreaRatio, conicalLength, divergenceLossFactor)

AIR = 1.4

#--------------------------------------------------------------------------------------------------------------------------#
# -- Isentropic ratios -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testSonicRatiosMatchTheStandardValues():
    '''
    The critical ratios for air, which appear in every compressible flow table: T*/T0 = 0.8333,
    P*/P0 = 0.5283.
    '''
    assert staticTemperatureRatio(1.0, AIR) == pytest.approx(0.83333, abs = 1e-5)
    assert staticPressureRatio(1.0, AIR) == pytest.approx(0.52828, abs = 1e-5)

@pytest.mark.parametrize('mach', [0.3, 0.8, 1.0, 2.0, 3.5, 6.0])
@pytest.mark.parametrize('gamma', [1.15, 1.25, 1.4, 1.667])
def testPressureRatioInvertsExactly(mach, gamma):
    '''
    machFromPressureRatio is the algebraic inverse of staticPressureRatio, so the round trip is an
    identity rather than an approximation.
    '''
    ratio = 1.0 / staticPressureRatio(mach, gamma)
    assert machFromPressureRatio(ratio, gamma) == pytest.approx(mach, rel = 1e-12)

def testStagnationRatioIsTheGroupingTheOthersArePowersOf():
    '''
    T0/T is the base of both other ratios. Checking the relation between them catches a sign or
    exponent slip that a spot value would not.
    '''
    for mach in [0.5, 1.0, 2.7, 5.0]:
        base = stagnationRatio(mach, AIR)
        assert staticTemperatureRatio(mach, AIR) == pytest.approx(1.0 / base, rel = 1e-14)
        assert staticPressureRatio(mach, AIR) == pytest.approx(base ** (-AIR / (AIR - 1.0)),
                                                               rel = 1e-14)

def testSubsonicPressureRatioBelowUnityReturnsZero():
    '''
    A stagnation-to-static ratio at or below one has no expansion in it. Returning zero rather
    than a complex number keeps callers from having to guard.
    '''
    assert machFromPressureRatio(1.0, AIR) == 0.0
    assert machFromPressureRatio(0.5, AIR) == 0.0

#--------------------------------------------------------------------------------------------------------------------------#
# -- Prandtl-Meyer -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testPrandtlMeyerMatchesPublishedTableValues():
    '''
    Standard gas tables for air: nu(2) = 26.380 deg, nu(3) = 49.757 deg, nu(4) = 65.785 deg.
    '''
    assert np.degrees(prandtlMeyerAngle(2.0, AIR)) == pytest.approx(26.380, abs = 0.01)
    assert np.degrees(prandtlMeyerAngle(3.0, AIR)) == pytest.approx(49.757, abs = 0.01)
    assert np.degrees(prandtlMeyerAngle(4.0, AIR)) == pytest.approx(65.785, abs = 0.01)

def testPrandtlMeyerIsZeroAtAndBelowSonic():
    assert prandtlMeyerAngle(1.0, AIR) == 0.0
    assert prandtlMeyerAngle(0.4, AIR) == 0.0

def testPrandtlMeyerIsMonotone():
    angles = [prandtlMeyerAngle(mach, AIR) for mach in np.linspace(1.01, 8.0, 200)]
    assert all(later > earlier for earlier, later in zip(angles, angles[1:]))

@pytest.mark.parametrize('gamma', [1.15, 1.25, 1.4])
@pytest.mark.parametrize('mach', [1.2, 2.0, 3.5, 6.0])
def testPrandtlMeyerInvertsToTheSameMachNumber(gamma, mach):
    angle = prandtlMeyerAngle(mach, gamma)
    assert machFromPrandtlMeyerAngle(angle, gamma) == pytest.approx(mach, rel = 1e-9)

def testPrandtlMeyerLimitingAngleIsRefusedRatherThanGuessed():
    '''
    The turning angle asymptotes as Mach goes to infinity. Asking for an angle at or beyond that
    limit has no answer, and returning a large finite Mach number would be a fabricated one.
    '''
    limit = 0.5 * np.pi * (np.sqrt((AIR + 1.0) / (AIR - 1.0)) - 1.0)
    assert np.degrees(limit) == pytest.approx(130.45, abs = 0.01)
    with pytest.raises(ValueError):
        machFromPrandtlMeyerAngle(limit, AIR)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Area-Mach relation -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testAreaRatioIsUnityAtTheThroat():
    for gamma in [1.15, 1.25, 1.4, 1.667]:
        assert areaMachRelation(1.0, gamma) == pytest.approx(1.0, rel = 1e-14)

def testAreaRatioMatchesPublishedTableValues():
    '''
    Standard isentropic flow tables for air: A/A* is 1.6875 at M = 2, 4.2346 at M = 3, and
    10.719 at M = 4.
    '''
    assert areaMachRelation(2.0, AIR) == pytest.approx(1.6875, abs = 1e-4)
    assert areaMachRelation(3.0, AIR) == pytest.approx(4.2346, abs = 1e-4)
    assert areaMachRelation(4.0, AIR) == pytest.approx(10.719, abs = 1e-3)

def testRadiusRelationIsTheSquareRootOfTheAreaRelation():
    for mach in [1.5, 3.0, 5.0]:
        assert radiusMachRelation(mach, AIR) ** 2 == pytest.approx(areaMachRelation(mach, AIR),
                                                                   rel = 1e-14)

@pytest.mark.parametrize('gamma', [1.15, 1.25, 1.4])
@pytest.mark.parametrize('mach', [1.5, 2.5, 4.0, 6.0])
def testSupersonicBranchInvertsTheAreaRelation(gamma, mach):
    ratio = areaMachRelation(mach, gamma)
    assert machFromAreaRatio(ratio, gamma, 'supersonic') == pytest.approx(mach, rel = 1e-8)

@pytest.mark.parametrize('gamma', [1.15, 1.4])
@pytest.mark.parametrize('mach', [0.10, 0.35, 0.70, 0.95])
def testSubsonicBranchInvertsTheAreaRelation(gamma, mach):
    ratio = areaMachRelation(mach, gamma)
    assert machFromAreaRatio(ratio, gamma, 'subsonic') == pytest.approx(mach, rel = 1e-5)

def testTheTwoBranchesAreDistinctAtTheSameArea():
    '''
    The whole reason a converging-diverging nozzle works: one area, two solutions.
    '''
    subsonic = machFromAreaRatio(4.0, AIR, 'subsonic')
    supersonic = machFromAreaRatio(4.0, AIR, 'supersonic')
    assert subsonic < 1.0 < supersonic

def testUnknownBranchIsRefused():
    with pytest.raises(ValueError):
        machFromAreaRatio(4.0, AIR, 'transonic')

def testSupersonicBranchRefusesAnAreaRatioBelowUnity():
    with pytest.raises(ValueError):
        machFromAreaRatio(0.8, AIR, 'supersonic')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Reference lengths -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testConicalLengthMatchesTheDefinition():
    '''
    NASA SP-8120 defines percent bell against a 15 degree half-angle cone of the same area ratio,
    whose length is (sqrt(eps) - 1) Rt / tan(15 deg). Checked here against the arithmetic written
    out, so a change to the convention cannot pass unnoticed.
    '''
    areaRatio, throatRadius = 40.0, 0.05
    expected = (np.sqrt(areaRatio) - 1.0) * throatRadius / np.tan(np.radians(15.0))
    assert conicalLength(areaRatio, throatRadius) == pytest.approx(expected, rel = 1e-14)
    assert conicalLength(1.0, throatRadius) == pytest.approx(0.0, abs = 1e-15)

def testConicalLengthOfTheRs25MatchesItsPublishedEightyPercentBell():
    '''
    The RS-25 is described as an 80 percent bell. Its published dimensions give a throat radius of
    5.15 in and an exit radius of 45.35 in, so the 15 degree cone to that exit radius is 150.05 in
    against a quoted nozzle length of 121 in, which is 80.6 percent.

    This is a check on the length convention, not on the solver. It is here because a tool that
    defines percent bell differently from the reference will disagree with every published bell,
    and that disagreement is easy to mistake for a contour error.
    '''
    throatRadius, exitRadius, quotedLength = 5.15, 45.35, 121.0
    areaRatio = (exitRadius / throatRadius) ** 2
    cone = conicalLength(areaRatio, throatRadius)
    assert cone == pytest.approx(150.05, abs = 0.5)
    assert quotedLength / cone == pytest.approx(0.806, abs = 0.005)

def testDivergenceLossFactorAtFifteenDegrees():
    '''
    lambda = (1 + cos alpha) / 2, the classical conical correction, is 0.983 at 15 degrees and
    exactly 1 for an axial exit.
    '''
    assert divergenceLossFactor(np.radians(15.0)) == pytest.approx(0.9830, abs = 1e-4)
    assert divergenceLossFactor(0.0) == pytest.approx(1.0, rel = 1e-14)
