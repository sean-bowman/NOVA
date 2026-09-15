'''

Tests for the contour generators and the reference contours they are compared against.

Nothing here runs the full characteristics solve, which is slow and is exercised end to end by the
showcase. What is tested is the geometry the solve is judged by: the scaling that carries a
non-dimensional contour into meters, the conical length reference, and the Rao parabolic
construction that most published bells are drawn from.

The Rao tests matter beyond this module. A generated contour is compared against the parabolic
construction wall angle for wall angle, so a construction that is wrong would make a correct
contour look wrong.

'''
import os
import sys

import numpy as np
import pytest

from NOVA.characteristics import CharacteristicGas
from NOVA.contourKernel import ThroatGeometry
from NOVA.contour import (ContourSolution, contourSolutionOutputs, throatScalingFactor,
                     conicalContour, raoWallAngles, raoParabolicContour, wallAnglesFromContour,
                     raoChartExtrapolatedAbove)
from NOVA.gasDynamics import conicalLength, radiusMachRelation

GAMMA, GAS_CONSTANT, STAGNATION_TEMPERATURE = 1.1475421191138746, 692.0, 3512.0

@pytest.fixture
def gas():
    return CharacteristicGas(GAMMA, GAS_CONSTANT, STAGNATION_TEMPERATURE)

@pytest.fixture
def throat():
    return ThroatGeometry(GAMMA)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Scaling into real units -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testThroatRadiusPassesTheRequestedMassFlow():
    '''
    The scaling factor is the throat radius that chokes at the requested mass flow. Recomputing
    the choked flow from it has to give the mass flow back, apart from the empirical correction
    the function applies.
    '''
    massFlow, chamberPressure, throatGamma = 23.91, 6894757.0, 1.1502
    radius = throatScalingFactor(massFlow, chamberPressure, throatGamma, GAS_CONSTANT,
                                 STAGNATION_TEMPERATURE)
    area = np.pi * radius ** 2
    chokedFlow = chamberPressure * area * np.sqrt(
        throatGamma / (GAS_CONSTANT * STAGNATION_TEMPERATURE)
        * (2 / (throatGamma + 1)) ** ((throatGamma + 1) / (throatGamma - 1)))

    correction = 1 - (throatGamma - 1) / 96 * (1 / 1.5) ** 2
    assert chokedFlow == pytest.approx(massFlow * correction, rel = 1e-12)

def testTheEmpiricalThroatCorrectionIsSmallAndItsSizeIsRecorded():
    '''
    The unsourced correction 1 - (gamma - 1) / 96 * (1 / 1.5)^2 shrinks the throat area by 0.070
    per cent and the throat radius by 0.035 per cent at this gamma.

    Recorded because it is applied to every dimension the tool produces and has no reference
    behind it. A discharge coefficient of the kind it appears to stand in for is nearer 1 per
    cent, so whatever it is, it does not reproduce one.
    '''
    throatGamma = 1.1502
    correction = 1 - (throatGamma - 1) / 96 * (1 / 1.5) ** 2
    assert 100.0 * (1.0 - correction) == pytest.approx(0.0695, abs = 1e-3)
    assert 100.0 * (1.0 - np.sqrt(correction)) == pytest.approx(0.0348, abs = 1e-3)

def testScalingGrowsWithMassFlowAndShrinksWithChamberPressure():
    base = throatScalingFactor(20.0, 7.0e6, 1.15, GAS_CONSTANT, STAGNATION_TEMPERATURE)
    heavier = throatScalingFactor(40.0, 7.0e6, 1.15, GAS_CONSTANT, STAGNATION_TEMPERATURE)
    tighter = throatScalingFactor(20.0, 14.0e6, 1.15, GAS_CONSTANT, STAGNATION_TEMPERATURE)
    assert heavier == pytest.approx(base * np.sqrt(2.0), rel = 1e-12)
    assert tighter == pytest.approx(base / np.sqrt(2.0), rel = 1e-12)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The conical reference -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testConicalContourDeliversTheRequestedAreaRatioExactly(throat):
    '''
    A cone has no free parameters beyond its half angle, so there is no excuse for it to miss the
    area ratio it was asked for. Sizing it from a one-dimensional Mach number instead lands on
    whatever ratio that Mach number corresponds to, which at this operating point is 48.5 rather
    than 40.
    '''
    areaRatio, scale = 40.0, 0.05
    x, r = conicalContour(throat, areaRatio, scale, numPoints = 60)
    assert (r[-1] / r[0]) ** 2 == pytest.approx(areaRatio, rel = 1e-12)
    assert r[0] / scale == pytest.approx(throat.throatRadius, rel = 1e-12)

def testConicalContourLengthMatchesTheLengthReference(throat):
    areaRatio, scale = 40.0, 0.05
    x, r = conicalContour(throat, areaRatio, scale, numPoints = 60)
    assert x[-1] == pytest.approx(conicalLength(areaRatio, throat.throatRadius) * scale,
                                  rel = 1e-12)

def testConicalContourIsAStraightLine(throat):
    x, r = conicalContour(throat, 40.0, 0.05, numPoints = 60)
    angles = np.arctan2(np.diff(r), np.diff(x))
    assert np.allclose(angles, np.radians(15.0), atol = 1e-12)

def testASteeperConeIsShorter(throat):
    shallow = conicalContour(throat, 40.0, 0.05, conicalHalfAngle = 15.0)[0][-1]
    steep = conicalContour(throat, 40.0, 0.05, conicalHalfAngle = 25.0)[0][-1]
    assert steep < shallow

#--------------------------------------------------------------------------------------------------------------------------#
# -- The Rao chart -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testChartReproducesThePublishedWorkedPoint():
    '''
    The single point quoted in the literature for this chart: an 80 per cent bell at an area ratio
    of 70 has an inflection angle near 33 degrees and an exit angle near 7 degrees.

    The lookup gives 32.5 and 7.3, within half a degree of both. That is the resolution a chart
    read by eye supports, and it is the accuracy any comparison against this reference inherits.
    '''
    inflection, exitAngle, extrapolated = raoWallAngles(70.0, 0.80)
    assert np.degrees(inflection) == pytest.approx(33.0, abs = 0.6)
    assert np.degrees(exitAngle) == pytest.approx(7.0, abs = 0.4)
    assert extrapolated is True

def testChartFlagsTheExtrapolatedRegion():
    '''
    NASA SP-8120 states that the wall-angle chart is extrapolated above an area ratio of about 50.
    Anything read above that is not a measurement and has to say so, because the area ratios that
    matter most for upper stages are all in that region.
    '''
    assert raoChartExtrapolatedAbove == 50.0
    assert raoWallAngles(40.0, 0.80)[2] is False
    assert raoWallAngles(80.0, 0.80)[2] is True

def testChartValuesAtTheTabulatedNodes():
    '''
    Exact node values, so an interpolation change cannot quietly move the table underneath it.
    '''
    inflection, exitAngle, _ = raoWallAngles(40.0, 0.80)
    assert np.degrees(inflection) == pytest.approx(31.0, abs = 1e-9)
    assert np.degrees(exitAngle) == pytest.approx(8.0, abs = 1e-9)

    inflection, exitAngle, _ = raoWallAngles(20.0, 0.90)
    assert np.degrees(inflection) == pytest.approx(27.0, abs = 1e-9)
    assert np.degrees(exitAngle) == pytest.approx(7.0, abs = 1e-9)

def testAShorterBellTurnsHarderAtTheThroatAndLeavesSteeper():
    '''
    The physical content of the chart: a shorter nozzle has to open faster and cannot straighten
    the flow as well, so both angles rise as the bell shortens.
    '''
    shortInflection, shortExit, _ = raoWallAngles(40.0, 0.60)
    longInflection, longExit, _ = raoWallAngles(40.0, 0.90)
    assert shortInflection > longInflection
    assert shortExit > longExit

def testTheExitAngleFallsAsAreaRatioGrows():
    angles = [np.degrees(raoWallAngles(ratio, 0.80)[1]) for ratio in [5.0, 10.0, 20.0, 40.0]]
    assert all(later < earlier for earlier, later in zip(angles, angles[1:]))

def testChartIsHeldAtItsEdgesRatherThanExtrapolatedFurther():
    '''
    The chart already ends in an extrapolated region. Running off it is answered by holding the
    edge value, not by continuing the trend, because there is nothing behind the trend.
    '''
    assert raoWallAngles(1.5, 0.80)[0] == raoWallAngles(4.0, 0.80)[0]
    assert raoWallAngles(500.0, 0.80)[0] == raoWallAngles(100.0, 0.80)[0]
    assert raoWallAngles(40.0, 0.40)[0] == raoWallAngles(40.0, 0.60)[0]

#--------------------------------------------------------------------------------------------------------------------------#
# -- The Rao parabolic contour -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testParabolicContourEndsAtExactlyTheRequestedAreaRatioAndLength(throat):
    '''
    The two things the construction fixes by definition, so both are exact rather than converged:
    the exit radius is sqrt(eps) times the throat radius, and the length is the requested fraction
    of the 15 degree cone of that area ratio.

    A generated contour that misses either of these is not the nozzle that was asked for, which is
    the comparison this reference exists to make.
    '''
    areaRatio, lengthFraction, scale = 40.0, 0.80, 0.05
    x, r = raoParabolicContour(throat, areaRatio, lengthFraction, scale, numPoints = 400)

    assert r[-1] == pytest.approx(np.sqrt(areaRatio) * throat.throatRadius * scale, rel = 1e-12)
    assert x[-1] == pytest.approx(
        lengthFraction * conicalLength(areaRatio, throat.throatRadius) * scale, rel = 1e-12)

def testParabolicContourStartsAtTheThroat(throat):
    x, r = raoParabolicContour(throat, 40.0, 0.80, 0.05, numPoints = 400)
    assert x[0] == pytest.approx(0.0, abs = 1e-15)
    assert r[0] == pytest.approx(throat.throatRadius * 0.05, rel = 1e-12)

def testParabolicContourIsMonotoneInBothCoordinates(throat):
    x, r = raoParabolicContour(throat, 40.0, 0.80, 0.05, numPoints = 400)
    assert np.all(np.diff(x) > 0.0)
    assert np.all(np.diff(r) > 0.0)

@pytest.mark.parametrize('numPoints', [200, 400, 1600])
def testMeasuredWallAnglesRecoverTheRequestedOnes(throat, numPoints):
    '''
    The round trip that makes the comparison meaningful: build a contour from two angles, measure
    the angles back off the geometry, and get the same two numbers. The residual is discretisation
    and falls as the contour is resolved more finely.
    '''
    areaRatio, lengthFraction = 40.0, 0.80
    requestedInflection, requestedExit, _ = raoWallAngles(areaRatio, lengthFraction)
    x, r = raoParabolicContour(throat, areaRatio, lengthFraction, 0.05, numPoints = numPoints)
    measuredInflection, measuredExit, index = wallAnglesFromContour(x, r)

    tolerance = np.radians(0.15) * (400.0 / numPoints)
    assert measuredInflection == pytest.approx(requestedInflection, abs = tolerance)
    assert measuredExit == pytest.approx(requestedExit, abs = tolerance)
    assert 0 < index < len(x) - 1, 'the inflection must be inside the contour, not at an end'

def testExplicitWallAnglesOverrideTheChart(throat):
    angles = (np.radians(35.0), np.radians(5.0))
    x, r = raoParabolicContour(throat, 40.0, 0.80, 0.05, numPoints = 1600, wallAngles = angles)
    measuredInflection, measuredExit, _ = wallAnglesFromContour(x, r)
    assert measuredInflection == pytest.approx(angles[0], abs = np.radians(0.1))
    assert measuredExit == pytest.approx(angles[1], abs = np.radians(0.1))

#--------------------------------------------------------------------------------------------------------------------------#
# -- Resampling the near-wall arrays -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testNearWallResamplingInterpolatesRatherThanSmooths():
    '''
    The near-wall arrays are resampled onto an evenly spaced contour with UnivariateSpline. Its
    default smoothing factor is an absolute residual budget of one per data point, so whether it
    interpolates or fits depends on the magnitude of the values rather than on their shape. A
    pressure in pascals is untouched by it; a Mach number, being of order one, gets replaced by a
    single straight line through the whole wall.

    That is what used to happen. The wall Mach came out reading 4.81 at the exit against a true
    4.07, and 1.9 at the throat, while the pressure beside it stayed correct, so the two arrays
    disagreed by a factor of 4.7 on a relation they were both built from. The regenerative cooling
    model reads the Mach array for the recovery temperature, which moved by up to 600 K.

    This test builds an array with the shape of a real near-wall Mach distribution and requires the
    resampling to reproduce it.
    '''
    from scipy.interpolate import UnivariateSpline, interp1d

    knots = np.linspace(0.0, 17.8, 116)
    mach = 1.1825 + 2.883 * (1.0 - np.exp(-knots / 3.0))
    query = np.linspace(0.0, 17.8, 100)

    interpolating = UnivariateSpline(knots, mach, k = 1, s = 0)(query)
    assert np.allclose(interpolating, interp1d(knots, mach)(query), atol = 1e-12)
    assert interpolating.max() <= mach.max() + 1e-12, 'interpolation may not overshoot the data'

    smoothing = UnivariateSpline(knots, mach, k = 1)(query)
    assert abs(smoothing[-1] - mach[-1]) > 0.4, \
        'the default smoothing factor no longer destroys an array of order one; the guard on ' \
        'the resampling calls can be revisited'

def testTheSmoothingTrapDependsOnMagnitudeNotShape():
    '''
    The same distribution, scaled up, survives the default smoothing untouched. This is what made
    the defect hard to see: pressure and temperature came through the same call correctly and only
    the Mach number was wrong, which reads like a Mach-number bug rather than an interpolation one.
    '''
    from scipy.interpolate import UnivariateSpline

    knots = np.linspace(0.0, 17.8, 116)
    shape = 1.1825 + 2.883 * (1.0 - np.exp(-knots / 3.0))
    query = np.linspace(0.0, 17.8, 100)

    small = UnivariateSpline(knots, shape, k = 1)(query)
    large = UnivariateSpline(knots, shape * 1.0e6, k = 1)(query) / 1.0e6

    assert abs(small[-1] - shape[-1]) > 0.4
    assert abs(large[-1] - shape[-1]) < 1.0e-3

#--------------------------------------------------------------------------------------------------------------------------#
# -- The solution workspace -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testWorkspaceStartsUnsolvedAndCarriesItsInputs(gas, throat):
    '''
    Every output starts as None rather than zero, so a field that was never reached stays
    distinguishable from one that was computed and came out at zero.
    '''
    state = ContourSolution(gas = gas, throat = throat, chamberPressure = 6.9e6,
                            engineMassFlow = 23.9, throatGamma = 1.1502,
                            idealMachNumber = 4.0653, targetExitPressure = 13993.0,
                            numContourPoints = 100)
    assert state.chamberGamma == gas.gamma
    assert state.thrustCoef is None
    assert state.xNozzleWall is None
    assert repr(state) == 'ContourSolution(unsolved)'

def testEveryDeclaredOutputExistsOnTheWorkspace(gas, throat):
    '''
    The list of names a solve hands back to a Nozzle has to match the workspace it is copied from,
    or an output is silently dropped on the way out.
    '''
    state = ContourSolution(gas = gas, throat = throat, chamberPressure = 6.9e6,
                            engineMassFlow = 23.9, throatGamma = 1.1502,
                            idealMachNumber = 4.0653, targetExitPressure = 13993.0,
                            numContourPoints = 100)
    for name in contourSolutionOutputs:
        assert hasattr(state, name), f'{name} is declared as an output but is not on the workspace'

#--------------------------------------------------------------------------------------------------------------------------#
# -- Which quantity binds the truncation -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.mark.parametrize('mode', ['areaRatio', 'wallPressure', 'length'])
def testEveryTruncationModeIsAccepted(gas, throat, mode):
    state = ContourSolution(gas = gas, throat = throat, chamberPressure = 6.9e6,
                            engineMassFlow = 23.9, throatGamma = 1.1502,
                            idealMachNumber = 4.0653, targetExitPressure = 13993.0,
                            numContourPoints = 100, truncateOn = mode)
    assert state.truncateOn == mode

def testTheThrustOptimumIsWhereTheWALLPressureReachesAmbient():
    '''
    The criterion behind the wallPressure truncation mode, checked directly.

    Extending a nozzle by a ring of wall adds an axial force of (P_wall - ambient) times that
    ring's projected area, so the thrust integral along the wall is

        F(R) = integral from Rt to R of (P_wall(r) - P_ambient) 2 pi r dr

    and its maximum sits exactly where the integrand changes sign, which is where the WALL static
    pressure equals ambient. No average over the exit plane appears anywhere in that statement.
    The average describes the flow leaving the nozzle; the wall pressure describes the surface the
    force acts on, and only the second one sets whether more nozzle is worth having.

    This is the classical optimum-expansion result, in the form that survives a non-uniform exit.
    '''
    radius = np.linspace(1.0, 9.0, 4000)
    # A wall pressure falling monotonically with radius, as it does in any expanding nozzle.
    wallPressure = 6.9e6 * (radius / 1.0) ** -3.2
    ambient = 101325.0

    increments = (wallPressure - ambient) * 2 * np.pi * radius
    thrust = np.concatenate([[0.0], np.cumsum(0.5 * (increments[1:] + increments[:-1])
                                              * np.diff(radius))])

    peak = int(np.argmax(thrust))
    crossing = int(np.argmin(np.abs(wallPressure - ambient)))
    assert abs(peak - crossing) <= 2, 'the thrust maximum is the wall pressure crossing'
    assert wallPressure[peak] == pytest.approx(ambient, rel = 2e-3)

def testCuttingOnAPlaneAverageStopsShortOfTheThrustOptimum():
    '''
    The counterpart. On a truncated contour the mass-averaged exit pressure runs well below the
    wall value, so a criterion that drives the average to ambient cuts the nozzle before the wall
    pressure has fallen that far, and stops while thrust is still being gained.

    The ratio used here, 0.73, is the one measured on the worked LOX/LH2 case.
    '''
    radius = np.linspace(1.0, 9.0, 4000)
    wallPressure = 6.9e6 * (radius / 1.0) ** -3.2
    ambient = 101325.0
    averageOverWall = 0.729

    increments = (wallPressure - ambient) * 2 * np.pi * radius
    thrust = np.concatenate([[0.0], np.cumsum(0.5 * (increments[1:] + increments[:-1])
                                              * np.diff(radius))])

    optimum = int(np.argmax(thrust))
    # Where the plane average, rather than the wall, reaches ambient.
    onAverage = int(np.argmin(np.abs(wallPressure * averageOverWall - ambient)))

    assert onAverage < optimum, 'the average criterion cuts earlier'
    assert thrust[onAverage] < thrust[optimum]
