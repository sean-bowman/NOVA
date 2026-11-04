'''

Tests for the extension's own coolant circuit in extensionCircuit.py.

Author: Sean Bowman

'''

import copy

import numpy as np
import pytest

from NOVA.channelGeometry import ChannelGeometryInputs
from NOVA.channelSizing import solveChannelRadii
from NOVA.errors import InvalidInputError
from NOVA.extensionCircuit import _sizingState, extensionCircuitSpan

CIRCUIT = dict(regenTruncationType = 'er', regenTruncationValue = 3.0, makeRadiativeExtension = True,
               makeInletVolute = False, makeOutletVolute = False, filmCooling = False,
               extensionCircuit = True, extensionCircuitEndAreaRatio = 12.0, extensionCoolant = 'Hydrogen',
               extensionCoolantMassFlow = 0.5, extensionCoolantInitialTemperature = 40.0,
               extensionCoolantInitialPressure = 8.0e6, extensionChannelCount = 90,
               extensionCircuitDirection = 'coflow', extensionCircuitOutlet = 'film',
               extensionFilmSlots = [{'areaRatio': 12.0, 'slotHeight': 0.012,
                                      'source': 'extensionCircuitOutlet'}])

@pytest.fixture(scope = 'module')
def dumpCooled(tmp_path_factory):

    from testDefectGuards import runConfiguration

    return runConfiguration(tmp_path_factory.mktemp('extensionCircuit'), **CIRCUIT)

class TestADumpCooledExtension:

    def testTheCircuitIsTheChamberMarchOnTheExtensionsStations(self, dumpCooled, tmp_path):

        from NOVA.regenThermal import RegenThermalContext

        solution = dumpCooled.extensionCircuitSolution
        state = dumpCooled.extensionCircuitState()
        # The circuit was solved before its own outlet film was laid, and with no chamber film the
        # extension it saw was driven by the recovery temperature; the drive kept on the nozzle
        # includes the outlet film, so it is set aside here
        state.extensionFilmDrivingTemperature = None
        geometry = ChannelGeometryInputs(numCrossSections = len(solution.stations),
                                         numCSPointsChannel = int(dumpCooled.numCSPointsChannel),
                                         nChannel = 90, channelType = 'circle',
                                         hotWallThickness = dumpCooled.hotWallThickness,
                                         infillThickness = dumpCooled.infillThickness)
        thermal = RegenThermalContext(material = dumpCooled.material, dataFolder = str(tmp_path),
                                      plotsEnabled = 'off', export = 'off')
        standalone = solveChannelRadii(_sizingState(state, solution.stations, 'coflow'), geometry, thermal)

        assert np.array_equal(standalone.channelThermalResults['temperature'],
                              solution.sizing.channelThermalResults['temperature'])

    def testTheCircuitSpansTheJointToItsFarEnd(self, dumpCooled):

        solution = dumpCooled.extensionCircuitSolution
        assert solution.stations[0] == 0
        assert solution.outletAreaRatio == pytest.approx(12.0, rel = 0.05)

    def testTheFilmStartsAtTheCircuitsOutlet(self, dumpCooled):

        solution = dumpCooled.extensionCircuitSolution
        layer = [layer for layer in dumpCooled.extensionFilmSolution.layers
                 if layer.source == 'extensionCircuitOutlet'][0]
        assert layer.coolantTemperature == solution.outletTemperature
        assert layer.massFlow == solution.massFlow

    def testTheShellStartsWhereTheCircuitEnds(self, dumpCooled):

        solution = dumpCooled.extensionCircuitSolution
        assert len(dumpCooled.extensionWallTemperature) == len(dumpCooled.xExtension) - solution.stations[-1]
        assert dumpCooled.frictionDragForce is not None

    def testTheDumpedCoolantIsADrawBesideTheChamber(self, dumpCooled):

        performance = dumpCooled.performance
        assert sum(performance.extraMassFlows.values()) == pytest.approx(0.5, rel = 1e-12)
        assert performance.engineTotalMassFlow == pytest.approx(dumpCooled.engineMassFlow + 0.5, rel = 1e-12)

class TestTheCircuitRefusals:

    def testAFarEndOffTheExtensionIsRefused(self):

        r = np.linspace(0.087, 0.32, 40)
        with pytest.raises(InvalidInputError):
            extensionCircuitSpan(np.linspace(0.0, 1.0, 40), r, 0.05, 80.0)

    def testAReturnedCircuitTheFeedCannotSupplyIsRefused(self, tmp_path):

        from testDefectGuards import runConfiguration

        with pytest.raises(InvalidInputError, match = 'carries no more'):
            runConfiguration(tmp_path, **{**CIRCUIT, 'extensionCircuitOutlet': 'return',
                                          'extensionCoolantMassFlow': 1.0, 'extensionFilmSlots': []})
