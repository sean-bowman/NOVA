'''

Tests for Ievlev's gas-side heat transfer, as RPA gives it.

The method is implemented from published equations, so most of what can be checked is that the
equations are read correctly: their closed forms, the one exact solution the quadrature has, and
the two choices the paper leaves open. The wall gas enthalpy, which the method's driving potential
rests on, is checked against NIST-JANAF.

'''

import math

import numpy as np
import pytest

import calorimeter40kCase as case
from NOVA.ievlevHeatTransfer import (densityRatio, ievlevGasProperties, ievlevHeatFlux,
                                     ievlevQuadratureExponent, stantonNumber,
                                     thicknessGroupRatio, viscosityRatio)

@pytest.fixture(scope = 'module')
def gas():
    point = case.operatingPoints['measured']
    return ievlevGasProperties(case._ceaSolve('measured'), point['chamberPressure'], point['mixtureRatio'])

#--------------------------------------------------------------------------------------------------------------------------#
# -- The closed forms -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheGroupRatioAtRestOnAColdWallIsThePublishedConstant():
    '''With no flow and a wall at zero, Eq. 1.1 is the constant 1.769 raised to 0.54.'''
    assert float(thicknessGroupRatio(0.0, 0.0)) == pytest.approx(1.769**0.54, rel = 1e-14)

def testTheGroupRatioStaysNearOneAndAHalfOnARocketWall():
    '''
    The algebraic ratio is what stands in for the momentum layer, and over the velocity and wall
    temperature ratios of a rocket chamber it barely moves. That is the main structural difference
    from the marched layer, whose thickness ratio reaches 8 to 10 through a throat.
    '''
    beta = np.linspace(0.0, 0.6, 61)
    for wall in (0.1, 0.15, 0.25):
        ratios = thicknessGroupRatio(beta, wall)
        assert np.all((ratios > 1.3) & (ratios < 1.75))

def testThePropertyRatiosAreUnityAtTheStagnationState():
    '''
    At rest, at the stagnation pressure and with the wall at the effective stagnation temperature,
    the defining state is the stagnation state, so both ratios have to be one.
    '''
    assert float(densityRatio(1.0, 0.0, 1.0)) == pytest.approx(1.0, rel = 1e-14)
    assert float(viscosityRatio(0.0, 1.0)) == pytest.approx(1.0, rel = 1e-14)

def testTheStantonNumberIsUndefinedBelowTheCorrelationsRange():
    '''Eq. 1.3's denominator crosses zero at small z, and a layer that thin returns NaN, not a number.'''
    assert math.isnan(float(stantonNumber(10.0, 1.5, 0.7, 0.1, 0.15)))
    assert float(stantonNumber(1.0e7, 1.5, 0.7, 0.1, 0.15)) > 0.0

def testTheQuadratureIsExactInAStraightDuct():
    '''
    In a duct of constant area at a constant state, every factor in the integrand of Eq. 1.2 is
    constant and z_T grows linearly along it: z_T(l) = z_T(0) + Re0 (rho_x/rho0)(mu0/mu_x) beta
    l / (1 - g). The implementation has to return that line.
    '''
    length = np.linspace(0.0, 0.5, 201)
    radius = np.full_like(length, 0.05)
    velocity, pressure, wallTemperature = 200.0, 5.0e6, 500.0
    gasState = {'stagnationTemperature': 3000.0, 'stagnationPressure': 5.2e6, 'gasConstant': 500.0,
                'gasConstant1500': 480.0, 'gamma': 1.2, 'stagnationViscosity': 1.0e-4,
                'prandtlNumber': 0.7, 'stagnationEnthalpy': 0.0, 'wallEnthalpy': lambda t: -1.0e7}
    initial = 2.0e6
    result = ievlevHeatFlux(length, radius, np.full_like(length, velocity), np.full_like(length, pressure),
                            wallTemperature, gasState, initialEnergyGroup = initial)

    maximumVelocity = math.sqrt(2.0 * 1.2 / 0.2 * 500.0 * 3000.0)
    beta = velocity / maximumVelocity
    wall = wallTemperature / (500.0 * 3000.0 / 480.0)
    reynolds = 5.2e6 / (500.0 * 3000.0) * maximumVelocity * 0.1 / 1.0e-4
    slope = reynolds * float(densityRatio(pressure / 5.2e6, beta, wall)) * float(viscosityRatio(beta, wall)) \
            * beta / (1.0 - ievlevQuadratureExponent)
    expected = initial + slope * length / 0.1
    assert result['energyGroup'] == pytest.approx(expected, rel = 1e-10)

#--------------------------------------------------------------------------------------------------------------------------#
# -- On the 40k calorimeter chamber -- #
#--------------------------------------------------------------------------------------------------------------------------#

def calorimeterFlux(gas, wallTemperature = 550.0, **options):
    location, radius = case.rpaContour()
    _, _, pressure, velocity = case.oneDimensionalEdgeState(location, radius, case.gasState('measured'))
    return location, radius, ievlevHeatFlux(location, radius, velocity, pressure, wallTemperature, gas, **options)

def testTheStantonNumberIsTheSizeARocketWallCarries(gas):
    '''
    The logarithm in Eq. 1.3 is not given a base. Base ten puts the Stanton number between 1e-3 and
    3e-3 along the chamber, where correlations and measurements sit; the natural logarithm would put
    it near a quarter of that.
    '''
    location, radius, result = calorimeterFlux(gas)
    inside = location > 0.05
    assert np.all((result['stantonNumber'][inside] > 1.0e-3) & (result['stantonNumber'][inside] < 3.0e-3))

def testTheThroatForgetsTheStartingValue(gas):
    '''
    Across two decades of the starting value of z_T the throat flux moves by under 2 percent. The
    constant of Eq. 1.2 is an assumption about the start of the layer, and the chamber is long
    enough to wash it out.
    '''
    throats = []
    for initial in (1.0e4, 1.0e5, 1.0e6):
        location, radius, result = calorimeterFlux(gas, initialEnergyGroup = initial)
        throats.append(float(result['heatFlux'][np.argmin(radius)]))
    assert max(throats) / min(throats) - 1.0 < 0.02

def testTheWallGasEnthalpyAgreesWithJanaf(gas):
    '''
    Fully recombined, the products of hydrogen and oxygen at the test's mixture ratio are water
    and the excess hydrogen. NIST-JANAF (Chase, 1998) gives water vapour a formation enthalpy of
    -241.826 kJ/mol and sensible enthalpies above 298.15 K of 6.925 and 10.501 kJ/mol at 500 and
    600 K, and hydrogen 5.882 and 8.811. Interpolated to 550 K that fixes the wall gas enthalpy,
    which the CEA expansion route has to return.
    '''
    mixtureRatio = case.operatingPoints['measured']['mixtureRatio']
    fuel = 1.0 / (1.0 + mixtureRatio)                         # [kg] per kg of propellant
    hydrogen = 1000.0 * fuel / 2.01588                        # [mol]
    oxygen = 1000.0 * (1.0 - fuel) / 31.9988                  # [mol]
    water, excess = 2.0 * oxygen, hydrogen - 2.0 * oxygen
    janaf = water * (-241.826 + 0.5 * (6.925 + 10.501)) + excess * 0.5 * (5.882 + 8.811)   # [kJ]
    assert gas['wallEnthalpy'](550.0) == pytest.approx(1e3 * janaf, rel = 2e-3)

def testTheEffectiveTemperatureCarriesTheRecombination(gas):
    '''
    The gas constant at 1500 K is the recombined gas's, which is heavier than the chamber's, so the
    effective temperature R0 T0 / R_1500 sits above the chamber temperature.
    '''
    assert gas['gasConstant1500'] < gas['gasConstant']
    assert 1.0 < gas['gasConstant'] / gas['gasConstant1500'] < 1.15
