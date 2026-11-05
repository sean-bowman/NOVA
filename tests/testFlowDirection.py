'''

Tests for the direction the coolant runs through the jacket, and for the coolant ceilings.

The sizing march visits the stations in coolant order through `coolantMarchOrder`, so a coflow
jacket is the same march over the reversed order. On a uniform barrel, a constant radius wall under
a uniform gas state with a channel of fixed size, the two directions describe the same physical
problem mirrored about the barrel's midpoint, and the coflow solution must be the counterflow one
reflected, to round-off. That is the closed-form check on the march order.

Author: Sean Bowman

'''

import numpy as np
import pytest

from NOVA.channelGeometry import ChannelGeometryInputs
from NOVA.channelSizing import ChannelSizingState, coolantMarchOrder, solveChannelRadii
from NOVA.errors import InvalidInputError, ThermalConstraintError
from NOVA.regenThermal import RegenThermalContext

STATIONS = 24

def barrelState(direction: str, **overrides) -> ChannelSizingState:

    '''A 300 mm barrel at a 90 mm radius under a uniform hydrogen-oxygen gas, 60 fixed 2 mm channels.'''

    uniform = np.ones(STATIONS)
    arguments = dict(
        channelType = 'circle', channelSizingMode = 'manual', manualChannelProfile = 0.002,
        manualChannelProfileKey = 'jacketFraction', channelSurfaceRoughness = 3.5e-5,
        nChannel = 60, numCrossSections = STATIONS, minChannelRadius = 5.0e-4,
        maxWallTemperature = 1500.0, hotWallThickness = 1.0e-3, infillThickness = 1.0e-3,
        material = 'GRCop-42', coolant = 'Hydrogen', coolantMassFlow = 3.4,
        jacketFlowDirection = direction, coolantInitialTemperature = 40.0,
        coolantInitialPressure = 1.2e7, chamberPressure = 6.9e6,
        theoreticalCharacteristicVelocity = 2300.0, nozzleScalingFactor = 0.05,
        throatInletCurvatureNonDimensional = 1.5, throatOutletCurvatureNonDimensional = 0.382,
        xRegenNozzleTrimmed = np.linspace(0.0, 0.3, STATIONS), rRegenNozzleTrimmed = 0.09 * uniform,
        gammaRegenSectionTrimmed = 1.2 * uniform, molecularWeightRegenSectionTrimmed = 13.0 * uniform,
        gasConstantRegenSectionTrimmed = 640.0 * uniform,
        regenSectionNearWallTemperatureTrimmed = 3300.0 * uniform,
        regenSectionNearWallRecoveryTemperatureTrimmed = 3350.0 * uniform,
        regenSectionNearWallMachNumberTrimmed = 0.2 * uniform,
        regenSectionNearWallPressureTrimmed = 6.7e6 * uniform)
    arguments['xRegenNozzle'] = arguments['xRegenNozzleTrimmed']
    arguments['rRegenNozzle'] = arguments['rRegenNozzleTrimmed']
    arguments.update(overrides)
    return ChannelSizingState(**arguments)

def solveBarrel(direction: str, tmp_path, **overrides) -> ChannelSizingState:

    state = barrelState(direction, **overrides)
    geometry = ChannelGeometryInputs(numCrossSections = STATIONS, numCSPointsChannel = 24,
                                     nChannel = 60, channelType = 'circle',
                                     hotWallThickness = 1.0e-3, infillThickness = 1.0e-3)
    thermal = RegenThermalContext(material = 'GRCop-42', dataFolder = str(tmp_path),
                                  plotsEnabled = 'off', export = 'off')
    return solveChannelRadii(state, geometry, thermal)

class TestTheMarchOrder:

    def testCounterflowRunsTheWallBackwards(self):

        assert list(coolantMarchOrder(4)) == [3, 2, 1, 0]
        assert list(coolantMarchOrder(4, 'counterflow')) == [3, 2, 1, 0]

    def testCoflowRunsItForwards(self):

        assert list(coolantMarchOrder(4, 'coflow')) == [0, 1, 2, 3]

    def testAnyOtherDirectionIsRefused(self):

        with pytest.raises(InvalidInputError):
            coolantMarchOrder(4, 'sideways')

@pytest.fixture(scope = 'module')
def bothDirections(tmp_path_factory):

    folder = tmp_path_factory.mktemp('barrel')
    return solveBarrel('counterflow', folder), solveBarrel('coflow', folder)

class TestAUniformBarrel:

    def testCoflowIsCounterflowReflected(self, bothDirections):

        counterflow, coflow = bothDirections

        for key in ('wallTemperature', 'temperature', 'heatTransfer', 'pressure'):
            reflected = np.asarray(counterflow.channelThermalResults[key])[::-1]
            assert np.asarray(coflow.channelThermalResults[key]) == pytest.approx(reflected, rel = 1e-9), key

    def testTheExitIsAtTheOppositeEnd(self, bothDirections):

        counterflow, coflow = bothDirections

        # Counterflow enters at the aft end and leaves at the injector face; coflow the reverse
        assert counterflow.coolantExitTemperature == counterflow.channelThermalResults['temperature'][0]
        assert coflow.coolantExitTemperature == coflow.channelThermalResults['temperature'][-1]
        assert coflow.coolantExitTemperature == pytest.approx(counterflow.coolantExitTemperature, rel = 1e-9)

    def testTheCoolantWarmsInTheDirectionItRuns(self, bothDirections):

        counterflow, coflow = bothDirections

        assert np.all(np.diff(counterflow.channelThermalResults['temperature']) < 0.0)
        assert np.all(np.diff(coflow.channelThermalResults['temperature']) > 0.0)

class TestTheCoolantCeilings:

    def testABulkCeilingPassedIsRefused(self, tmp_path):

        with pytest.raises(ThermalConstraintError, match = 'bulk coolant'):
            solveBarrel('counterflow', tmp_path, maxCoolantTemperature = 50.0)

    def testAColdWallCeilingPassedInTheManualModeIsRefused(self, tmp_path):

        with pytest.raises(ThermalConstraintError, match = 'coolant-side wall'):
            solveBarrel('counterflow', tmp_path, maxColdWallTemperature = 100.0)

    def testTheThermalSizingHoldsTheColdWallAtItsCeiling(self, tmp_path):

        # Sized against an 800 K hot wall with a 200 K cold wall ceiling, the ceiling binds: the
        # channels shrink until the coolant face sits at it, and the hot wall is left below 800 K
        state = solveBarrel('counterflow', tmp_path, channelSizingMode = 'thermal',
                            maxWallTemperature = 800.0, maxColdWallTemperature = 200.0)

        coldWall = np.asarray(state.channelThermalResults['coldWallTemperature'])
        hotWall = np.asarray(state.channelWallTemperature)
        assert coldWall.max() == pytest.approx(200.0, abs = 0.5)
        assert hotWall.max() < 800.0

@pytest.fixture(scope = 'module')
def referenceBothWays(tmp_path_factory):

    from testDefectGuards import runConfiguration

    common = dict(makeRadiativeExtension = False, makeInletVolute = True, makeOutletVolute = True)
    return (runConfiguration(tmp_path_factory.mktemp('counterflow'), **common),
            runConfiguration(tmp_path_factory.mktemp('coflow'), jacketFlowDirection = 'coflow', **common))

class TestTheReferenceJacketRunCoflow:

    def testTheCoolantWarmsTowardTheExit(self, referenceBothWays):

        _, coflow = referenceBothWays
        temperature = np.asarray(coflow.channelThermalResults['temperature'])

        # Each station holds the coolant leaving it, so the injector station already reads a few
        # kelvin over the inlet; the coolant is coldest there and warmest at the exit
        assert coflow.coolantInitialTemperature < temperature[0] < coflow.coolantInitialTemperature + 10.0
        assert int(np.argmin(temperature)) == 0
        assert int(np.argmax(temperature)) == len(temperature) - 1
        assert coflow.coolantExitTemperature == temperature[-1]

    def testTheVolutesSwapEnds(self, referenceBothWays):

        counterflow, coflow = referenceBothWays

        # The inlet scroll sits at the aft end of a counterflow jacket and at the injector end of
        # a coflow one; the outlet takes the other end in each
        assert counterflow.inletVolute.axialOffset > counterflow.outletVolute.axialOffset
        assert coflow.inletVolute.axialOffset < coflow.outletVolute.axialOffset
        assert coflow.inletVolute.axialOffset == pytest.approx(counterflow.outletVolute.axialOffset, abs = 0.01)

    def testTheInletScrollHoldsTheInletPressure(self, referenceBothWays):

        _, coflow = referenceBothWays

        assert coflow.inletVolute.pressureDifferential == coflow.coolantInitialPressure

    def testTheInterfacedWallIsTheSameWallEitherWay(self, referenceBothWays):

        # The reference inlet and outlet flares match, so swapping which end carries which role
        # leaves the interfaced wall where it was, forward end first
        counterflow, coflow = referenceBothWays

        assert coflow.xRegenNozzleInterfaced == pytest.approx(counterflow.xRegenNozzleInterfaced, abs = 1.0e-9)
        assert coflow.rRegenNozzleInterfaced == pytest.approx(counterflow.rRegenNozzleInterfaced, abs = 1.0e-9)
        assert coflow.xRegenNozzleInterfaced[0] < coflow.xRegenNozzleInterfaced[-1]
