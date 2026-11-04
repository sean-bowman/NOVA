'''

Tests for the films over the nozzle extension in extensionFilm.py, and the thrust they add.

The closures are tested in testFilmCooling.py. What is held here is what this module adds: the
superposition and its limits, the joined wall, the slot rules, and the film expansion.

Author: Sean Bowman

'''

import copy

import numpy as np
import pytest

from NOVA.errors import InvalidInputError
from NOVA.extensionFilm import (ExtensionFilmState, filmExpansionVelocity, mixedFilmThrust,
                                readFilmSlots, solveExtensionFilm, superposeFilms)

class TestTheSuperposition:

    recovery = np.array([3000.0, 2900.0, 2800.0, 2700.0, 2600.0])

    def testNoFilmIsTheRecoveryTemperature(self):

        assert np.array_equal(superposeFilms(self.recovery, [], []), self.recovery)

    def testOneFilmIsItsOwnDrive(self):

        drive = np.array([3000.0, 2900.0, 400.0, 900.0, 1500.0])
        assert superposeFilms(self.recovery, [drive], [300.0]) == pytest.approx(drive, rel = 1e-14)

    def testTwoFilmsOfConstantEffectivenessStackInClosedForm(self):

        # eta 0.5 of a 300 K film everywhere, then eta 0.4 of a 900 K film from the third station
        first = self.recovery - 0.5 * (self.recovery - 300.0)
        second = np.where(np.arange(5) >= 2, self.recovery - 0.4 * (self.recovery - 900.0), self.recovery)
        afterFirst = self.recovery - 0.5 * (self.recovery - 300.0)
        expected = np.where(np.arange(5) >= 2, afterFirst - 0.4 * (afterFirst - 900.0), afterFirst)

        stacked = superposeFilms(self.recovery, [first, second], [300.0, 900.0])
        assert stacked == pytest.approx(expected, rel = 1e-14)

class TestTheFilmThrust:

    def testTheExpansionIsTheIsentropicClosedForm(self):

        # Air at rest at 300 K and 100 kPa expanded to 10 kPa: the exit Mach number from the
        # pressure ratio, then u = M a at the static temperature
        cp, gasConstant, gamma = 1004.5, 287.0, 1004.5 / (1004.5 - 287.0)
        mach = np.sqrt(2.0 / (gamma - 1.0) * (10.0**((gamma - 1.0) / gamma) - 1.0))
        exitTemperature = 300.0 / (1.0 + 0.5 * (gamma - 1.0) * mach**2)
        expected = mach * np.sqrt(gamma * gasConstant * exitTemperature)

        assert filmExpansionVelocity(300.0, 0.0, 100.0e3, 10.0e3, cp, gasConstant) == pytest.approx(expected, rel = 1e-12)

    def testAFilmThatCannotExpandKeepsItsSlotVelocity(self):

        assert filmExpansionVelocity(300.0, 50.0, 10.0e3, 20.0e3, 1004.5, 287.0) == 50.0

    def testNoFilmAddsNothingMixed(self):

        assert mixedFilmThrust(100.0, 4000.0, 1.2e7, [], []) == 0.0

    def testAFilmAtTheCoreEnthalpyAddsItsFlowAtTheCoreVelocity(self):

        assert mixedFilmThrust(100.0, 4000.0, 1.2e7, [5.0], [1.2e7]) == pytest.approx(5.0 * 4000.0, rel = 1e-12)

class TestTheSlotDefinitions:

    def testNothingIsNoSlot(self):

        assert readFilmSlots(None) == [] and readFilmSlots(float('nan')) == [] and readFilmSlots([]) == []

    def testATurbineExhaustSlotNeedsOnlyItsPlace(self):

        slot = readFilmSlots([{'areaRatio': 10.0, 'slotHeight': 0.005, 'source': 'turbineExhaust'}])[0]
        assert slot.massFlow is None and slot.mixtureRatio == 0.0

    @pytest.mark.parametrize('raw', [
        [{'areaRatio': 10.0, 'slotHeight': 0.005, 'source': 'exhaust'}],
        [{'areaRatio': 10.0, 'slotHeight': 0.005, 'source': 'species', 'massFlow': 1.0}],
        [{'slotHeight': 0.005, 'source': 'turbineExhaust'}],
        ['turbineExhaust'],
        {'areaRatio': 10.0}])
    def testAnIncompleteSlotIsRefused(self, raw):

        with pytest.raises(InvalidInputError):
            readFilmSlots(raw)

# -- A solved nozzle -- #

GASGENERATOR = {'gasGeneratorMixtureRatio': 0.9, 'gasGeneratorPressure': 8.0e6,
                'turbinePressureRatio': 16.0, 'turbineEfficiency': 0.6,
                'turbineExhaustMassFlow': 0.7}

@pytest.fixture(scope = 'module')
def filmedNozzle(tmp_path_factory):

    from testDefectGuards import runConfiguration

    slots = [{'areaRatio': 10.0, 'slotHeight': 0.004, 'source': 'turbineExhaust'}]
    return runConfiguration(tmp_path_factory.mktemp('extensionFilm'), makeRadiativeExtension = True,
                            makeInletVolute = False, makeOutletVolute = False,
                            extensionFilmSlots = slots, **GASGENERATOR)

def seededState(nozzle) -> ExtensionFilmState:

    state = ExtensionFilmState()
    for name in ExtensionFilmState.__dataclass_fields__:
        setattr(state, name, copy.deepcopy(getattr(nozzle, name, None)))
    return state

class TestTheShippedNozzleFilmed:

    def testTheChamberFilmReproducesTheJacketSectionsFilm(self, filmedNozzle):

        film = filmedNozzle.extensionFilmSolution
        chamber = [layer for layer in film.layers if layer.source == 'chamber'][0]
        joint = film.jointIndex

        assert chamber.result.drivingTemperature[:joint] == pytest.approx(
            np.asarray(filmedNozzle.regenSectionFilmDrivingTemperature)[:joint], rel = 1e-12)

    def testTheExtensionIsDrivenByTheStackedFilms(self, filmedNozzle):

        film = filmedNozzle.extensionFilmSolution
        recovery = film.recoveryTemperature[film.jointIndex:]

        assert [layer.source for layer in film.layers] == ['chamber', 'turbineExhaust']
        assert np.all(film.extensionDrivingTemperature <= recovery + 1e-9)
        assert np.array_equal(filmedNozzle.extensionFilmDrivingTemperature, film.extensionDrivingTemperature)
        slot = film.layers[1].injectionIndex
        assert film.drivingTemperature[slot] == pytest.approx(filmedNozzle.turbineExhaust.temperature, abs = 1.0)

    def testTheExtensionRunsCoolerThanWithoutTheExhaust(self, filmedNozzle):

        film = filmedNozzle.extensionFilmSolution
        chamberOnly = film.layers[0].result.drivingTemperature[film.jointIndex:]
        slot = film.layers[1].injectionIndex - film.jointIndex

        assert np.all(film.extensionDrivingTemperature[slot:] < chamberOnly[slot:])

    def testTheExhaustIsAnExtraDrawWithThrust(self, filmedNozzle):

        performance = filmedNozzle.performance
        name = filmedNozzle.extensionFilmSolution.layers[1].name

        assert performance.extraMassFlows == {name: pytest.approx(0.7)}
        assert performance.engineTotalMassFlow == pytest.approx(filmedNozzle.engineMassFlow + 0.7, rel = 1e-14)
        assert 0.0 < performance.filmThrustUnmixed < performance.filmThrustMixed

    def testTheEngineImpulseIsTheEngineThrustOverTheEngineFlow(self, filmedNozzle):

        performance = filmedNozzle.performance
        chamberThrust = performance.thrustDeliveredFrictionCorrected['design']
        expected = (chamberThrust + performance.filmThrustUnmixed) / (performance.engineTotalMassFlow * 9.80665)

        assert performance.engineSpecificImpulse['design'] == pytest.approx(expected, rel = 1e-12)

    def testASlotAboveTheExhaustPressureIsRefused(self, filmedNozzle):

        state = seededState(filmedNozzle)
        state.turbineExhaust = copy.deepcopy(filmedNozzle.turbineExhaust)
        state.turbineExhaust.pressure = 1000.0

        with pytest.raises(InvalidInputError, match = 'cannot enter'):
            solveExtensionFilm(state)

    def testATurbineSlotWithoutAGasGeneratorIsRefused(self, filmedNozzle):

        state = seededState(filmedNozzle)
        state.turbineExhaust = None

        with pytest.raises(InvalidInputError, match = 'no gas'):
            solveExtensionFilm(state)

    def testASlotOffTheExtensionIsRefused(self, filmedNozzle):

        state = seededState(filmedNozzle)
        state.extensionFilmSlots = [{'areaRatio': 1.5, 'slotHeight': 0.004, 'source': 'turbineExhaust'}]

        with pytest.raises(InvalidInputError, match = 'off the'):
            solveExtensionFilm(state)

    def testSlotsDrawingMoreExhaustThanTheTurbinePassesAreRefused(self, filmedNozzle):

        state = seededState(filmedNozzle)
        state.extensionFilmSlots = [{'areaRatio': 10.0, 'slotHeight': 0.004, 'source': 'turbineExhaust'},
                                    {'areaRatio': 20.0, 'slotHeight': 0.004, 'source': 'turbineExhaust'}]

        with pytest.raises(InvalidInputError, match = 'draw'):
            solveExtensionFilm(state)
