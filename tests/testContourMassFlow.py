'''

Tests for the mass a contour solve passes: the throat's discharge coefficient, the characteristic
that carries the starting line into the inner kernel, and the exit plane the mass is counted on.

The reference for all three is the transonic starting line itself. It is the only place the solve
is told how much mass the throat passes, so a solve that loses mass downstream of it, beyond the
march's first-order discretization, is losing it by construction. The validation figures quoted
here come from an inviscid finite-volume solution of the shipped throat (validation/openFoam) and
from Kliegel and Levine's transonic series.

'''
import numpy as np
import pytest

from NOVA.characteristics import CharacteristicGas
from NOVA.contour import ContourSolution, solveKernel, truncatedIdealContour
from NOVA.contourKernel import (ThroatGeometry, sauerLimitingCharacteristic, startLineCharacteristic,
                                throatDischargeCoefficient)
from NOVA.gasDynamics import prandtlMeyerAngle

GAMMA, GAS_CONSTANT, STAGNATION_TEMPERATURE = 1.1475421191138746, 656.5957199546061, 3398.3656102220107
CHAMBER_PRESSURE = 6894757.0

def _startLineMass(gas, throat, points = 4001) -> float:
    '''Mass through the Sauer starting line over the one-dimensional choked flow.'''
    radii = np.linspace(0.0, 1.0, points)
    mach = np.array([sauerLimitingCharacteristic(gas, throat, radius) for radius in radii])
    flux = (1.0 + 0.5 * (GAMMA - 1.0) * mach**2)**(-1.0 / (GAMMA - 1.0) - 0.5) * mach
    sonic = (1.0 + 0.5 * (GAMMA - 1.0))**(-1.0 / (GAMMA - 1.0) - 0.5)
    return float(np.trapezoid(2.0 * flux / sonic * radii, radii))

@pytest.fixture(scope = 'module')
def gas():
    return CharacteristicGas(GAMMA, GAS_CONSTANT, STAGNATION_TEMPERATURE)

@pytest.fixture(scope = 'module')
def throat():
    return ThroatGeometry(GAMMA, 1.0, 1.5, 0.382)

@pytest.fixture(scope = 'module')
def shippedContour(gas, throat):
    '''The shipped throat cut at an area ratio of 40, on a coarse mesh of 25 characteristics.'''
    state = ContourSolution(gas, throat, CHAMBER_PRESSURE, 23.4664, GAMMA, 4.2, 13993.28, 100,
                            requestedAreaRatio = 40.0, numCharacteristicsRequested = 25)
    return truncatedIdealContour(state, 4.2, 0.8, truncate = True, assignOutputsToObject = True)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The throat's discharge coefficient -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheDischargeCoefficientReproducesThePrintedSeries():
    '''
    Kliegel and Levine's series in 1/(R + 1), evaluated by hand from its printed coefficients at
    the shipped gamma: 0.99461 at the Rao entrant arc and 0.97399 at its exit arc. An inviscid
    finite-volume solution of the shipped throat converges to 0.9947.
    '''
    assert throatDischargeCoefficient(GAMMA, 1.5) == pytest.approx(0.99461, abs = 1e-5)
    assert throatDischargeCoefficient(GAMMA, 0.382) == pytest.approx(0.97399, abs = 1e-5)

def testTheDischargeCoefficientTendsToSauersAtAGentleThroat():
    '''The series' leading term is Sauer's, (gamma + 1) / 96 R^2, and dominates as R grows.'''
    for curvature in (20.0, 50.0, 200.0):
        deficit = 1.0 - throatDischargeCoefficient(GAMMA, curvature)
        assert deficit == pytest.approx((GAMMA + 1.0) / (96.0 * curvature**2), rel = 3.0 / curvature)

def testTheDischargeCoefficientRefusesAFlatThroat():
    with pytest.raises(ValueError):
        throatDischargeCoefficient(GAMMA, 0.0)

def testTheCharacteristicVelocityIsTheThermochemistrysNotTheGeometricThroats(shippedContour):
    '''
    The throat is larger than the one-dimensional choked area by its discharge coefficient, and
    the characteristic velocity the heat transfer reads belongs to the one-dimensional area: it is
    the closed-form perfect-gas value, not chamber pressure times the geometric throat area over
    the mass flow, which is 0.54 percent higher.
    '''
    closedForm = (np.sqrt(GAS_CONSTANT * STAGNATION_TEMPERATURE / GAMMA)
                  / (2.0 / (GAMMA + 1.0))**((GAMMA + 1.0) / (2.0 * (GAMMA - 1.0))))
    assert shippedContour.theoreticalCharacteristicVelocity == pytest.approx(closedForm, rel = 1e-9)
    geometric = CHAMBER_PRESSURE * shippedContour.throatArea / shippedContour.engineMassFlow
    assert geometric / closedForm - 1.0 == pytest.approx(1.0 / throatDischargeCoefficient(GAMMA, 1.5) - 1.0, rel = 1e-6)

def testTheStartingLineCarriesSauersDischargeCoefficient(gas, throat):
    '''
    The starting line passes Sauer's discharge coefficient, the leading term of the series, which
    at this throat is 0.42 percent below Kliegel and Levine's.
    '''
    assert _startLineMass(gas, throat) == pytest.approx(1.0 - (GAMMA + 1.0) / (96.0 * 1.5**2), abs = 5e-4)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The characteristic that opens the inner kernel -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.fixture(scope = 'module')
def lastRow(gas, throat):
    kernel = solveKernel(gas, throat, 26, 0.25 * prandtlMeyerAngle(4.2, GAMMA), CHAMBER_PRESSURE)
    blocks = [kernel[name] for name in ('throatKernelMach', 'throatKernelFlowAngle', 'throatKernelX', 'throatKernelR')]
    return tuple(block[-1, 0] for block in blocks), tuple(block[-1, 1] for block in blocks)

def testTheThroatArcCharacteristicsLeaveMostOfTheStartingLineUncovered(lastRow):
    '''
    The reason the characteristic is solved: on the Rao exit arc the throat arc's characteristics
    reach only the outer eighth of the starting line's radius.
    '''
    foot, _ = lastRow
    assert 0.8 < foot[3] < 0.9

def testTheCharacteristicRunsFromTheLastRowToTheAxis(gas, throat, lastRow):
    foot, first = lastRow
    mach, angle, x, r = startLineCharacteristic(gas, throat, foot, first, 20)
    assert len(r) == 20 and np.all(np.diff(r) < 0.0)
    assert r[0] < first[3] and r[-1] == pytest.approx(0.0, abs = 1e-12)
    assert np.all(np.diff(x) > 0.0) and np.all(mach > 1.0)
    assert angle[-1] == pytest.approx(0.0, abs = 1e-9)

def testTheAxisStateConvergesAndMatchesTheFiniteVolumeSolution(gas, throat, lastRow):
    '''
    The axis end of the characteristic is NOVA's first axis node. It settles to 0.05 percent as
    the starting line is resolved, and lands within half a percent of the Mach 1.321 an inviscid
    finite-volume solution of this throat gives at 0.64 throat radii.
    '''
    foot, first = lastRow
    axis = [startLineCharacteristic(gas, throat, foot, first, 20, numStartPoints = count)[0][-1]
            for count in (10, 20, 40)]
    assert abs(axis[2] - axis[1]) < abs(axis[1] - axis[0])
    assert axis[1] == pytest.approx(axis[2], rel = 5e-4)
    assert axis[2] == pytest.approx(1.321, rel = 5e-3)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The exit plane the mass is counted on -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheExitPlaneClosesOnTheDesignCore(shippedContour):
    '''
    Inside the left-running characteristic from the kernel's last axis point the flow is axial at
    the design Mach number, so the plane ends with that state, from where the characteristic
    crosses the plane to the axis, and nowhere carries a higher Mach number.
    '''
    state = shippedContour
    radius, mach, angle = state.exitPlaneRadius, state.exitPlaneMach, state.exitPlaneFlowAngle
    assert radius[-1] == 0.0
    assert mach[-1] == state.calculatedExitMach and mach[-2] == state.calculatedExitMach
    assert angle[-1] == 0.0 and angle[-2] == 0.0
    assert np.max(mach) <= state.calculatedExitMach * (1.0 + 1e-9)

def testNoExitStationLiesOutsideTheWall(shippedContour):
    radius = shippedContour.exitPlaneRadius
    assert np.all(radius[1:] <= radius[0]) and np.all(np.diff(radius) < 0.0)

def testThrustAndMassFlowShareOneQuadrature(shippedContour):
    '''
    Both are the trapezoidal rule on the integrand times radius over the same stations, so thrust
    per unit mass flow is the ratio of the two integrals with nothing left over.
    '''
    state = shippedContour
    radius, mach, angle = state.exitPlaneRadius, state.exitPlaneMach, state.exitPlaneFlowAngle
    temperature = STAGNATION_TEMPERATURE / (1.0 + 0.5 * (GAMMA - 1.0) * mach**2)
    velocity = mach * np.sqrt(GAMMA * GAS_CONSTANT * temperature)
    density = state.exitPlanePressure / (GAS_CONSTANT * temperature)
    integral = lambda values: 2.0 * np.pi * np.trapezoid(values[::-1] * radius[::-1], radius[::-1])
    assert state.exitMassFlux == pytest.approx(integral(density * velocity * np.cos(angle)), rel = 1e-12)
    momentum = state.velocityTermThrustCoef * CHAMBER_PRESSURE * np.pi
    assert momentum == pytest.approx(integral(density * velocity**2 * np.cos(angle)**2), rel = 1e-12)

def testTheMarchKeepsTheStartingLinesMass(shippedContour, gas, throat):
    '''
    The exit plane passes the starting line's mass less the march's first-order discretization:
    0.89 percent at 25 characteristics, 0.42 at 50 and 0.19 at 100, and 0.04 percent from the
    line once extrapolated. A kernel that opens without the starting line's inner stretch passes
    1.7 percent less than the line at 50 characteristics.
    '''
    closure = shippedContour.exitMassClosure
    line = _startLineMass(gas, throat)
    assert line - 0.010 < closure < line - 0.007
