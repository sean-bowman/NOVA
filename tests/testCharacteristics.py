'''

Tests for the method-of-characteristics unit processes.

The interior point is the routine everything else in NOVA rests on: the nozzle mesh, the wall
streamline that becomes the contour, and the plume march past the lip. Three things are checked
here and they are different in kind.

The compatibility relations are written out again as a fixture, and the plume's copy of the same
relations is required to reproduce them exactly. That catches a change to the arithmetic.

The scheme is then checked against exact planar theory. Far from the axis the axisymmetric term
vanishes and the Riemann invariants must be conserved along their characteristics, and the
departure must fall as the square of the state jump. That is a property of the equations rather
than of this implementation, so it catches a scheme that is self-consistent and wrong.

Finally the nozzle unit process and the plume unit process are compared. They share the relations
but not the iteration, and the size of what that costs is recorded rather than assumed.

'''
import math
import os
import sys

import numpy as np
import pytest

from NOVA.characteristics import (CharacteristicGas, axisymmetricMethodOfCharacteristics,
                             wallCharacteristicProjection)
from NOVA.gasDynamics import prandtlMeyerAngle
from NOVA.plume import PlumeFlow, PlumePoint, plumeInteriorPoint

GAMMA, GAS_CONSTANT, STAGNATION_TEMPERATURE = 1.22, 480.0, 3500.0
CHAMBER = (1.1475421191138746, 692.0, 3512.0)

@pytest.fixture
def gas():
    return CharacteristicGas(GAMMA, GAS_CONSTANT, STAGNATION_TEMPERATURE)

def interiorRelations(gas, machOne, angleOne, xOne, rOne, machTwo, angleTwo, xTwo, rTwo):
    '''
    One pass of the axisymmetric interior point, written out independently of the solver.

    Kept in the arithmetic style of the compatibility equations rather than tidied, so a reader
    comparing this against `axisymmetricMethodOfCharacteristics` can do it line by line. The
    limiting velocity is written the way the plume writes it, which differs from the nozzle's
    grouping by about one unit in the last place; that difference has its own test below.
    '''
    muOne, muTwo = np.arcsin(1 / machOne), np.arcsin(1 / machTwo)
    temperatureOne = gas.stagnationTemperature / (1 + (gas.gamma - 1) / 2 * machOne ** 2)
    temperatureTwo = gas.stagnationTemperature / (1 + (gas.gamma - 1) / 2 * machTwo ** 2)
    velocityOne = np.sqrt(gas.gamma * gas.gasConstant * temperatureOne) * machOne
    velocityTwo = np.sqrt(gas.gamma * gas.gasConstant * temperatureTwo) * machTwo
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
    maxVelocity = math.sqrt(2 * gas.gamma * gas.gasConstant * gas.stagnationTemperature
                            / (gas.gamma - 1))
    mach = np.sqrt((2 / (gas.gamma - 1))
                   * ((velocity / maxVelocity) ** 2 / (1 - (velocity / maxVelocity) ** 2)))
    return mach, angle, xIntersection, rIntersection

#--------------------------------------------------------------------------------------------------------------------------#
# -- The gas -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testVelocityAndMachInvertEachOther(gas):
    for mach in [1.2, 2.5, 4.0, 6.0]:
        assert gas.machFromVelocity(gas.localVelocity(mach)) == pytest.approx(mach, rel = 1e-12)

def testMaximumAdiabaticVelocityIsTheLimitOfTheVelocityRelation(gas):
    '''
    The velocity a streamline would reach expanding to zero temperature. Nothing may exceed it,
    and a very high Mach number must approach it.
    '''
    assert gas.localVelocity(1e4) < gas.maxAdiabaticVelocity
    assert gas.localVelocity(1e4) / gas.maxAdiabaticVelocity == pytest.approx(1.0, abs = 1e-6)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The relations, as an identity -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.mark.parametrize('kernel', [
    (2.50, np.radians(6.0),  0.30, 0.10, 2.70, np.radians(11.0), 0.31, 0.14),
    (3.80, np.radians(2.0),  0.80, 0.05, 4.10, np.radians(9.0),  0.82, 0.20),
    (4.50, np.radians(0.5),  0.90, 0.02, 4.60, np.radians(13.0), 0.91, 0.40),
    (1.60, np.radians(12.0), 0.05, 0.04, 1.75, np.radians(15.0), 0.06, 0.07),
])
def testPlumeReproducesTheCompatibilityRelationsExactly(gas, kernel):
    '''
    The plume unit process, stopped after one pass, against the relations written out. These are
    the same equations, so the only acceptable difference is none. This is what establishes that
    the fixture above is a faithful statement of the shared relations, which the tests below then
    measure the solvers against.
    '''
    reference = interiorRelations(gas, *kernel)
    flow = PlumeFlow(gas.gamma, gas.gasConstant, gas.stagnationTemperature, 1.0e7)
    first = PlumePoint(kernel[2], kernel[3], kernel[0], kernel[1], flow)
    second = PlumePoint(kernel[6], kernel[7], kernel[4], kernel[5], flow)
    computed = plumeInteriorPoint(flow, first, second, maxIterations = 1)

    assert computed is not None
    assert computed.mach == reference[0]
    assert computed.flowAngle == reference[1]
    assert computed.x == reference[2]
    assert computed.r == reference[3]

def testTheCorrectorIsASmallCorrectionToTheFirstPass(gas):
    '''
    The nozzle solver iterates on properties averaged along each characteristic and cannot be
    stopped after one pass, so it is measured against the first-pass relations rather than
    equated to them. The corrector has to move the answer, or it is doing nothing, and it has to
    move it by little, or the step was too large to be trusted.
    '''
    kernel = (2.50, np.radians(6.0), 0.30, 0.10, 2.70, np.radians(11.0), 0.31, 0.14)
    reference = interiorRelations(gas, *kernel)
    converged = axisymmetricMethodOfCharacteristics(gas, kernel, numPoints = 1)

    assert converged[0] != reference[0]
    assert converged[0] == pytest.approx(reference[0], rel = 0.02)
    assert converged[1] == pytest.approx(reference[1], rel = 0.05)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The scheme, against exact planar theory -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testFarFromTheAxisTheInvariantsAreNearlyConserved():
    '''
    The axisymmetric compatibility relations differ from the planar ones by a term in 1 / r. Far
    from the axis that term vanishes and the planar Riemann invariants must hold: theta - nu is
    constant along the C+ characteristic through point one, and theta + nu along the C- through
    point two.
    '''
    gas = CharacteristicGas(*CHAMBER)
    machOne, angleOne = 3.0, np.radians(4.0)
    machTwo, angleTwo = 3.2, np.radians(9.0)
    radius, step = 1.0e5, 0.02
    kernel = (machOne, angleOne, 0.0, radius,
              machTwo, angleTwo, step, radius + step * np.tan(angleTwo))

    mach, angle, _, _ = axisymmetricMethodOfCharacteristics(gas, kernel, numPoints = 1)
    nu = prandtlMeyerAngle(mach, gas.gamma)

    plusResidual = abs((angle - nu) - (angleOne - prandtlMeyerAngle(machOne, gas.gamma)))
    minusResidual = abs((angle + nu) - (angleTwo + prandtlMeyerAngle(machTwo, gas.gamma)))
    assert plusResidual < 1.0e-3
    assert minusResidual < 1.0e-4

def testTheAxisymmetricTermFallsAsTheRadiusGrows():
    '''
    Companion to the test above. The departure from the planar invariants must shrink as the axis
    recedes rather than sit at a fixed value, which is what distinguishes a physical term from an
    error in the relations.
    '''
    gas = CharacteristicGas(*CHAMBER)
    residuals = []
    for radius in [20.0, 200.0, 2000.0]:
        step = 0.02
        kernel = (3.0, np.radians(4.0), 0.0, radius,
                  3.2, np.radians(9.0), step, radius + step * np.tan(np.radians(9.0)))
        mach, angle, _, _ = axisymmetricMethodOfCharacteristics(gas, kernel, numPoints = 1)
        nu = prandtlMeyerAngle(mach, gas.gamma)
        residuals.append(abs((angle + nu)
                             - (np.radians(9.0) + prandtlMeyerAngle(3.2, gas.gamma))))
    assert residuals[1] < residuals[0]
    assert residuals[2] < residuals[1]

def testTheSchemeIsSecondOrderInTheStateJump():
    '''
    The strongest check available on the unit process, and the only one against an exact result.

    In the planar limit the exact answer is the Riemann invariant, so the residual against it is
    the discretisation error of the scheme. Halving the jump between the two upstream states must
    quarter that residual, because averaging the characteristic properties along each
    characteristic makes the scheme second order. A first-order scheme, which is what evaluating
    the coefficients at the upstream point alone would give, would halve it instead.

    Measured orders on this sequence run 1.88, 1.94, 1.97, 1.99, 1.99.
    '''
    gas = CharacteristicGas(*CHAMBER)
    radius = 1.0e6
    residuals = []
    for scale in [1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125]:
        machOne, angleOne = 3.0, np.radians(4.0)
        machTwo, angleTwo = 3.0 + 0.2 * scale, np.radians(4.0 + 5.0 * scale)
        step = 0.02 * scale
        kernel = (machOne, angleOne, 0.0, radius,
                  machTwo, angleTwo, step, radius + step * np.tan(angleTwo))
        mach, angle, _, _ = axisymmetricMethodOfCharacteristics(gas, kernel, numPoints = 1)
        residuals.append(abs((angle - prandtlMeyerAngle(mach, gas.gamma))
                             - (angleOne - prandtlMeyerAngle(machOne, gas.gamma))))

    orders = [np.log2(earlier / later) for earlier, later in zip(residuals, residuals[1:])]
    assert min(orders) > 1.8, f'observed orders {orders}'
    assert max(orders) < 2.2, f'observed orders {orders}'

def testIntersectionLiesOnTheLeftRunningCharacteristic(gas):
    '''
    Geometry, independent of the flow solution: the returned point sits on the characteristic
    through point one, at its initial slope to within the correction the corrector applies, and
    downstream of both upstream points.
    '''
    machOne, angleOne, xOne, rOne = 2.50, np.radians(6.0), 0.30, 0.10
    machTwo, angleTwo, xTwo, rTwo = 2.70, np.radians(11.0), 0.31, 0.14
    _, _, x, r = axisymmetricMethodOfCharacteristics(
        gas, (machOne, angleOne, xOne, rOne, machTwo, angleTwo, xTwo, rTwo), numPoints = 1)

    slopeLeft = np.tan(angleOne + np.arcsin(1 / machOne))
    assert r == pytest.approx(rOne + (x - xOne) * slopeLeft, rel = 0.05)
    assert x > max(xOne, xTwo)
    assert rOne < r < rTwo + 0.05

#--------------------------------------------------------------------------------------------------------------------------#
# -- The nozzle unit process against the plume's -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.mark.parametrize('kernel', [
    (2.50, np.radians(6.0),  0.30, 0.10, 2.70, np.radians(11.0), 0.31, 0.14),
    (3.80, np.radians(2.0),  0.80, 0.05, 4.10, np.radians(9.0),  0.82, 0.20),
    (1.60, np.radians(12.0), 0.05, 0.04, 1.75, np.radians(15.0), 0.06, 0.07),
])
def testNozzleAndPlumeConvergeToNearlyTheSamePoint(kernel):
    '''
    The plume march is a continuation of the nozzle solution rather than a second approximation of
    it, and the two agree exactly on the first pass, which the identity test above establishes.

    Converged they do not agree exactly, because they iterate differently: the nozzle moves both
    upstream points toward the intersection under a fixed weight and re-evaluates, while the plume
    holds the upstream points and averages the characteristic properties. On these kernels the two
    end up within 1.1 per cent in Mach number and 1.3 per cent in position.

    That is the real relationship between them, and it is asserted here so that it stays a known
    quantity. It is larger than a rounding difference and smaller than a difference in physics.
    '''
    gas = CharacteristicGas(*CHAMBER)
    flow = PlumeFlow(gas.gamma, gas.gasConstant, gas.stagnationTemperature, 6.9e6)

    nozzleMach, nozzleAngle, nozzleX, nozzleR = axisymmetricMethodOfCharacteristics(
        gas, kernel, numPoints = 1)
    first = PlumePoint(kernel[2], kernel[3], kernel[0], kernel[1], flow)
    second = PlumePoint(kernel[6], kernel[7], kernel[4], kernel[5], flow)
    plumePoint = plumeInteriorPoint(flow, first, second)

    assert plumePoint is not None
    assert plumePoint.mach == pytest.approx(nozzleMach, rel = 0.011)
    assert plumePoint.x == pytest.approx(nozzleX, rel = 0.013)
    assert plumePoint.r == pytest.approx(nozzleR, rel = 0.006)
    assert plumePoint.flowAngle == pytest.approx(nozzleAngle, abs = np.radians(0.7))

def testTheTwoLimitingVelocityExpressionsDifferByOneUlp():
    '''
    Records a discrepancy that would otherwise have to be rediscovered. The nozzle carries the
    limiting velocity as sqrt(gamma R) sqrt(2 T0 / (gamma - 1)) and the plume as
    sqrt(2 gamma R T0 / (gamma - 1)). Those are the same number in exact arithmetic and differ by
    about one unit in the last place in floating point.

    It is not the reason the two solvers disagree when converged, which is the iteration, but it
    does mean an exact identity between them is unreachable until one of the two is rewritten.
    '''
    gamma, gasConstant, stagnationTemperature = CHAMBER
    nozzleForm = np.sqrt(gamma * gasConstant) * np.sqrt(2 * stagnationTemperature / (gamma - 1))
    plumeForm = math.sqrt(2.0 * gamma * gasConstant * stagnationTemperature / (gamma - 1.0))
    assert nozzleForm != plumeForm
    assert abs(nozzleForm - plumeForm) / plumeForm < 1e-15

#--------------------------------------------------------------------------------------------------------------------------#
# -- The wall point -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testWallProjectionReturnsAPhysicalState(gas):
    '''
    The wall projection solves for a state whose position is fixed by geometry rather than by the
    characteristics, so the check is that what comes back is supersonic, finite, and at a
    positive radius.
    '''
    geometry = (np.radians(8.0), 0.30, 0.100, np.radians(12.0), 0.31, 0.140)
    mach, optimisedMach, optimisedAngle, x, r = wallCharacteristicProjection(gas, 2.6, geometry)

    assert np.isfinite(mach) and mach > 1.0
    assert np.isfinite(x) and np.isfinite(r) and r > 0.0
    assert optimisedMach > 1.0
    assert np.radians(0.0) < optimisedAngle < np.radians(30.0)
