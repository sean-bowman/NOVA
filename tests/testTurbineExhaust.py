'''

Tests for the gas generator and turbine exhaust state in turbineExhaust.py.

CEA is validated elsewhere; what is held here are the identities the turbine reading rests on, and
the one comparison against hardware, which the equilibrium fails for a fuel-rich hydrocarbon.

Author: Sean Bowman

'''

import numpy as np
import pytest

from NOVA.errors import ConvergenceFailureError, InvalidInputError
from NOVA.turbineExhaust import UNIVERSALGASCONSTANT, _frozenCase, turbineExhaustState

HYDROGEN = dict(fuel = 'LH2', oxidizer = 'LOX', mixtureRatio = 0.9, gasGeneratorPressure = 10.0e6,
                pressureRatio = 16.0, massFlow = 10.0)

@pytest.fixture(scope = 'module')
def ideal():

    return turbineExhaustState(efficiency = 1.0, **HYDROGEN)

@pytest.fixture(scope = 'module')
def real():

    return turbineExhaustState(efficiency = 0.6, **HYDROGEN)

class TestTheTurbineIdentities:

    def testAPerfectTurbineIsCeasFrozenExpansion(self, ideal):

        cea = _frozenCase('LH2', 'LOX', 0.9, 10.0e6, 16.0, None)

        assert ideal.temperature == cea['exitTemperature']
        assert ideal.specificHeat == cea['exitHeatCapacity']
        assert ideal.thermalConductivity == cea['exitThermalConductivity']
        assert ideal.viscosity == cea['exitViscosity']
        # CEA reaches the pressure ratio through the area ratio it implies, a round trip good to a
        # few parts in ten million
        assert ideal.pressure == pytest.approx(cea['exitPressure'], rel = 1e-6)

    def testTheTurbineTakesItsEfficiencyOfTheIdealWork(self, real):

        idealWork = real.gasGeneratorEnthalpy - real.isentropicEnthalpy
        assert real.turbineSpecificWork == pytest.approx(0.6 * idealWork, rel = 1e-12)
        assert real.turbinePower == pytest.approx(10.0 * 0.6 * idealWork, rel = 1e-12)

    def testTheExhaustSitsOnTheFrozenExpansionAtItsEnthalpy(self, real):

        # The matched point's own CEA enthalpy is the exhaust enthalpy, to the root find's tolerance
        assert real.propertySource == 'frozenExpansion'
        assert real.isentropicTemperature < real.temperature < real.gasGeneratorTemperature

    def testTheDensityIsTheIdealGasAtTheExhaustPressure(self, real):

        expected = real.pressure * real.molecularWeight / (UNIVERSALGASCONSTANT * real.temperature)
        assert real.density == pytest.approx(expected, rel = 1e-14)
        assert real.pressure == pytest.approx(10.0e6 / 16.0, rel = 1e-14)

    def testTheBranchesMeetAtTheThroat(self, real):

        # The efficiency that puts the exhaust exactly at the throat enthalpy, approached from
        # either side: both interpolations land on CEA's throat state
        cea = _frozenCase('LH2', 'LOX', 0.9, 10.0e6, 16.0, None)
        atThroat = ((cea['combustionChamberEnthalpy'] - cea['throatEnthalpy'])
                    / (cea['combustionChamberEnthalpy'] - cea['exitEnthalpy']))
        below = turbineExhaustState(efficiency = atThroat * (1.0 - 1e-7), **HYDROGEN)
        above = turbineExhaustState(efficiency = atThroat * (1.0 + 1e-7), **HYDROGEN)

        for state in (below, above):
            assert state.propertySource == 'chamberThroatInterpolation'
            assert state.temperature == pytest.approx(cea['throatTemperature'], abs = 0.01)
            assert state.specificHeat == pytest.approx(cea['throatHeatCapacity'], rel = 1e-5)

    def testTheRootFindTakesOverJustPastTheThroat(self):

        # Two percent more work than the throat leaves the exhaust on the supersonic expansion,
        # and the temperature it is found at is the throat's less the enthalpy over cp
        cea = _frozenCase('LH2', 'LOX', 0.9, 10.0e6, 16.0, None)
        atThroat = ((cea['combustionChamberEnthalpy'] - cea['throatEnthalpy'])
                    / (cea['combustionChamberEnthalpy'] - cea['exitEnthalpy']))
        past = turbineExhaustState(efficiency = 1.02 * atThroat, **HYDROGEN)
        expected = cea['throatTemperature'] - (cea['throatEnthalpy'] - past.enthalpy) / cea['throatHeatCapacity']

        assert past.propertySource == 'frozenExpansion'
        assert past.temperature == pytest.approx(expected, abs = 0.5)

class TestTheFilmState:

    def testTheSlotStateIsTakenAtTheWallPressure(self, real):

        slotPressure, slotHeight, slotRadius = 30.0e3, 0.01, 0.5
        film = real.filmState(slotPressure, slotHeight, slotRadius)
        density = slotPressure / (real.gasConstant * real.temperature)

        assert film.density == pytest.approx(density, rel = 1e-14)
        assert film.velocity == pytest.approx(10.0 / (density * 2.0 * np.pi * slotRadius * slotHeight), rel = 1e-14)
        assert film.specificHeat == real.specificHeat

    def testAShareOfTheExhaustCanBeSlotted(self, real):

        whole = real.filmState(30.0e3, 0.01, 0.5)
        half = real.filmState(30.0e3, 0.01, 0.5, massFlow = 5.0)

        assert half.velocity == pytest.approx(0.5 * whole.velocity, rel = 1e-14)

class TestTheCondensedPhase:

    def testHydrogenFormsNone(self, real):

        assert real.condensedSpecies == {}

    def testTheF1GasGeneratorFormsGraphiteAndRunsHot(self):

        # 49 lb/s of LOX with 118 lb/s of RP-1 at about 1453 F (1063 K), per the F-1 gas generator
        # page at heroicrelics.org; the pressure is not sourced. Equilibrium forms a third of the
        # mass as graphite, whose heat the real gas generator never released. The disagreement is
        # held here so a change to it is seen.
        state = turbineExhaustState('RP-1', 'LOX', 0.416, 6.65e6, 16.0, 0.6, 75.7)

        assert state.condensedSpecies['C(gr)'] == pytest.approx(0.354, abs = 0.01)
        assert 1.15 < state.gasGeneratorTemperature / 1063.0 < 1.20

class TestTheRefusals:

    @pytest.mark.parametrize('name, value', [('efficiency', 0.0), ('efficiency', 1.2),
                                             ('massFlow', -1.0), ('pressureRatio', 1.0)])
    def testAnInputOutsideItsRangeIsRefused(self, name, value):

        arguments = dict(HYDROGEN, efficiency = 0.6)
        arguments[name] = value
        with pytest.raises(InvalidInputError):
            turbineExhaustState(**arguments)

    def testAFrozenExpansionCeaCannotCloseIsRefused(self):

        # CEA returns the throat state for this gas rather than the expansion asked for
        with pytest.raises(ConvergenceFailureError, match = 'did not reach'):
            turbineExhaustState('CH4', 'LOX', 0.2, 8.0e6, 16.0, 0.6, 1.0)

    def testAPressureRatioBelowSonicIsRefused(self):

        arguments = dict(HYDROGEN, efficiency = 0.6, pressureRatio = 1.5)
        with pytest.raises(InvalidInputError, match = 'sonic ratio'):
            turbineExhaustState(**arguments)
