'''

Tests for the multi-pass coolant circuits in coolantCircuit.py.

The two passes are each the single-pass sizing march; what is held here is the coupling: the
passes' spans and counts, the turnaround between them, the heat they take on together, and the
rib heat one hands the other.

Author: Sean Bowman

'''

import copy

import numpy as np
import pytest

from NOVA.channelGeometry import ChannelGeometryInputs
from NOVA.coolantCircuit import passCounts, passStations, solveCoolantCircuit
from NOVA.errors import InvalidInputError
from NOVA.fluidProperties import fluidProps
from NOVA.regenThermal import RegenThermalContext, ribExchangeConductance

class TestTheCounts:

    def testOneToOneAlternatesEveryChannel(self):

        assert passCounts(60, 1.0) == (60, 60, 2.0, 2.0)

    def testOneDownToTwoUpIsTheJ2(self):

        # 180 down to 360 up: each down channel between two up, each up beside one down
        assert passCounts(360, 0.5) == (180, 360, 2.0, 1.0)

    @pytest.mark.parametrize('count, ratio', [(61, 0.5), (60, 0.25)])
    def testAnUnbuildableAlternationIsRefused(self, count, ratio):

        with pytest.raises(InvalidInputError):
            passCounts(count, ratio)

class TestTheSpans:

    x = np.linspace(-0.2, 0.6, 81)
    r = 0.05 + np.where(x < 0.0, 0.5 * x**2, 0.25 * x)

    def testTwoPassesRunTheWholeJacket(self):

        down, up = passStations('twoPass', self.x, self.r, None)
        assert np.array_equal(down, up) and len(up) == 81

    def testAOneAndAHalfPassStartsDownAtItsInlet(self):

        down, up = passStations('oneAndHalfPass', self.x, self.r, None, inletAreaRatio = 3.0)
        throatRadius = self.r.min()
        assert (self.r[down[0]] / throatRadius)**2 >= 3.0 > (self.r[down[0] - 1] / throatRadius)**2
        assert down[-1] == 80 and len(up) == 81

    def testAnInletPastTheJacketIsRefused(self):

        with pytest.raises(InvalidInputError):
            passStations('oneAndHalfPass', self.x, self.r, None, inletAreaRatio = 50.0)

class TestTheRibConductance:

    def testItIsThreeResistancesInSeries(self):

        conductance = ribExchangeConductance(2.0e4, 3.0e4, 1.0e-4, 2.0e-4, 1.0e-3, 300.0)
        expected = 1.0 / (1.0 / (2.0e4 * 1.0e-4) + 1.0e-3 / (300.0 * 1.5e-4) + 1.0 / (3.0e4 * 2.0e-4))
        assert conductance == pytest.approx(expected, rel = 1e-14)

    def testItIsTheSameFromEitherSide(self):

        assert ribExchangeConductance(2.0e4, 3.0e4, 1.0e-4, 2.0e-4, 1.0e-3, 300.0) == pytest.approx(
            ribExchangeConductance(3.0e4, 2.0e4, 2.0e-4, 1.0e-4, 1.0e-3, 300.0), rel = 1e-14)

    def testNoFaceOrNoCoolantExchangesNothing(self):

        assert ribExchangeConductance(0.0, 3.0e4, 1.0e-4, 1.0e-4, 1.0e-3, 300.0) == 0.0
        assert ribExchangeConductance(2.0e4, 3.0e4, 0.0, 1.0e-4, 1.0e-3, 300.0) == 0.0

# -- Solved circuits on the reference jacket -- #

@pytest.fixture(scope = 'module')
def jacket(tmp_path_factory):

    from testDefectGuards import runConfiguration

    nozzle = runConfiguration(tmp_path_factory.mktemp('circuitBase'), regenTruncationType = 'er',
                              regenTruncationValue = 10.0, makeRadiativeExtension = False,
                              makeInletVolute = False, makeOutletVolute = False, filmCooling = False,
                              numCrossSections = 30, nChannel = 30)
    folder = str(tmp_path_factory.mktemp('circuitThermal'))
    geometry = ChannelGeometryInputs(numCrossSections = 30, numCSPointsChannel = 24,
                                     nChannel = nozzle.nChannel, channelType = 'circle',
                                     hotWallThickness = nozzle.hotWallThickness,
                                     infillThickness = nozzle.infillThickness)
    thermal = RegenThermalContext(material = nozzle.material, dataFolder = folder,
                                  plotsEnabled = 'off', export = 'off')
    return nozzle, copy.deepcopy(nozzle.channelSizingSolution), geometry, thermal

@pytest.fixture(scope = 'module')
def twoPass(jacket):

    _, base, geometry, thermal = jacket
    return solveCoolantCircuit(copy.deepcopy(base), geometry, thermal, 'twoPass', material = 'GRCop-42')

@pytest.fixture(scope = 'module')
def twoPassApart(jacket):

    _, base, geometry, thermal = jacket
    return solveCoolantCircuit(copy.deepcopy(base), geometry, thermal, 'twoPass', material = 'GRCop-42',
                               ribExchange = False)

def coolantEnthalpy(coolant, temperature, pressure):

    return float(np.atleast_1d(fluidProps(coolant, 'TP', 'H', temperature, pressure))[0])

class TestATwoPassJacket:

    def testTheFlowSplitsInTheRatioAskedFor(self, twoPass, jacket):

        _, base, _, _ = jacket
        assert twoPass.down.channelMassFlow * twoPass.down.channelCount == pytest.approx(base.coolantMassFlow, rel = 1e-14)
        assert twoPass.up.channelMassFlow * twoPass.up.channelCount == pytest.approx(base.coolantMassFlow, rel = 1e-14)

    def testTheTurnaroundIsChargedOnce(self, twoPass):

        down, up = twoPass.down.state, twoPass.up.state
        assert float(up.coolantInitialPressure) == pytest.approx(
            float(down.coolantExitPressure) - twoPass.turnaround.pressureDrop, rel = 1e-14)

    def testTheTurnKeepsTheCoolantsEnthalpy(self, twoPass, jacket):

        _, base, _, _ = jacket
        down, up = twoPass.down.state, twoPass.up.state
        before = coolantEnthalpy(base.coolant, float(down.coolantExitTemperature), float(down.coolantExitPressure))
        after = coolantEnthalpy(base.coolant, float(up.coolantInitialTemperature), float(up.coolantInitialPressure))
        assert after == pytest.approx(before, rel = 1e-6)

    def testTheCoolantTakesOnWhatTheWallPasses(self, twoPass, jacket):

        _, base, _, _ = jacket
        down, up = twoPass.down, twoPass.up
        wallHeat = (down.channelCount * np.sum(down.results['heatTransfer'])
                    + up.channelCount * np.sum(up.results['heatTransfer']))
        rise = base.coolantMassFlow * (
            coolantEnthalpy(base.coolant, twoPass.coolantExitTemperature, twoPass.coolantExitPressure)
            - coolantEnthalpy(base.coolant, float(base.coolantInitialTemperature), float(base.coolantInitialPressure)))
        downRib, upRib = twoPass.ribHeatBalance()
        assert rise == pytest.approx(wallHeat + downRib + upRib, rel = 2e-3)

    def testTheRibHeatOnePassGainsTheOtherLoses(self, twoPass):

        downRib, upRib = twoPass.ribHeatBalance()
        assert abs(downRib) > 0.0
        assert downRib + upRib == pytest.approx(0.0, abs = 0.02 * abs(downRib))

    def testWithoutTheRibThePassesExchangeNothing(self, twoPassApart):

        downRib, upRib = twoPassApart.ribHeatBalance()
        assert downRib == 0.0 and upRib == 0.0
        assert twoPassApart.iterations == 1

    def testTheDownPassWarmsTowardTheTurnAndTheUpPassTowardTheInjector(self, twoPass):

        downTemperature = np.asarray(twoPass.down.results['temperature'])
        upTemperature = np.asarray(twoPass.up.results['temperature'])
        assert int(np.argmax(downTemperature)) == len(downTemperature) - 1
        assert int(np.argmax(upTemperature)) == 0

# -- A one-and-a-half-pass jacket through the whole build -- #

ONEANDAHALF = dict(regenTruncationType = 'er', regenTruncationValue = 10.0, makeRadiativeExtension = False,
                   makeInletVolute = False, makeOutletVolute = True, filmCooling = False,
                   numCrossSections = 30, nChannel = 30, coolantCircuit = 'oneAndHalfPass',
                   coolantInletAreaRatio = 3.0)

@pytest.fixture(scope = 'module')
def oneAndAHalf(tmp_path_factory):

    from testDefectGuards import runConfiguration

    return runConfiguration(tmp_path_factory.mktemp('oneAndAHalf'), **ONEANDAHALF)

class TestAOneAndAHalfPassJacket:

    def testTheDownPassStartsAtTheInletManifold(self, oneAndAHalf):

        circuit = oneAndAHalf.coolantCircuitSolution
        xWall = np.asarray(oneAndAHalf.channelSizingSolution.xRegenNozzleTrimmed)
        assert circuit.down.stations[0] > int(np.argmin(oneAndAHalf.channelSizingSolution.rRegenNozzleTrimmed))
        assert circuit.down.stations[-1] == len(xWall) - 1 and len(circuit.up.stations) == len(xWall)

    def testTheJacketReportsTheUpPassItDraws(self, oneAndAHalf):

        circuit = oneAndAHalf.coolantCircuitSolution
        assert oneAndAHalf.coolantExitTemperature == pytest.approx(circuit.coolantExitTemperature, rel = 1e-14)
        assert np.allclose(oneAndAHalf.channelThermalResults['temperature'], circuit.up.results['temperature'])

    def testForwardOfTheInletTheUpChannelsHaveThePitchToThemselves(self, oneAndAHalf):

        circuit = oneAndAHalf.coolantCircuitSolution
        pitch = np.asarray(circuit.up.state.pitchChannelCount)
        assert np.all(pitch[:circuit.down.stations[0]] == 30) and np.all(pitch[circuit.down.stations] == 60)

class TestTheCircuitRefusals:

    def testAnInletScrollOnAMultiPassJacketIsRefused(self, tmp_path):

        from testDefectGuards import runConfiguration

        with pytest.raises(InvalidInputError, match = 'no inlet scroll'):
            runConfiguration(tmp_path, **{**ONEANDAHALF, 'makeInletVolute': True})

    def testRectangularPassesAreRefused(self, tmp_path):

        from testDefectGuards import runConfiguration

        with pytest.raises(InvalidInputError, match = 'alternate circular'):
            runConfiguration(tmp_path, **{**ONEANDAHALF, 'channelType': 'rectangular', 'nChannel': 160})

class TestTheMultiPassGeometry:

    def testTheDownFamilySitsOneSlotFromTheUpChannel(self, oneAndAHalf):

        circuit = oneAndAHalf.coolantCircuitSolution
        slot = 2.0 * np.pi / (circuit.up.channelCount + circuit.down.channelCount)
        angle = np.arctan2(oneAndAHalf.zChannelDown, oneAndAHalf.yChannelDown).mean()
        assert angle == pytest.approx(slot, rel = 1e-2)
        assert oneAndAHalf.xChannelDown.shape[1] == len(circuit.down.stations)

    def testTheTurnaroundRingsTheAftEnd(self, oneAndAHalf):

        ring = oneAndAHalf.coolantCircuitSolution.turnaround
        radius = np.hypot(oneAndAHalf.yTurnaround, oneAndAHalf.zTurnaround)
        assert radius.min() == pytest.approx(ring.ringRadius - ring.sectionRadius, rel = 1e-3)
        assert ring.axialPosition == pytest.approx(float(oneAndAHalf.channelSizingSolution.xRegenNozzleTrimmed[-1]))

def testASplitInAMultiPassJacketIsRefused(tmp_path):

    from testDefectGuards import runConfiguration

    with pytest.raises(InvalidInputError, match = 'split is not built'):
        runConfiguration(tmp_path, **{**ONEANDAHALF, 'channelSplitAreaRatio': 5.0})

def testEachOuterPassIsReportedAndTheReportChangesNothing(jacket, twoPassApart):

    '''Under a progress reporter the down and up passes are stages and each outer pass an iteration.'''

    from NOVA import progress

    _, base, geometry, thermal = jacket
    events = []
    with progress.reporting(events.append):
        circuit = solveCoolantCircuit(copy.deepcopy(base), geometry, thermal, 'twoPass', material = 'GRCop-42',
                                      ribExchange = False)

    stages = [(event['type'], event['path']) for event in events if event['type'] in ('stageStart', 'stageEnd')]
    iterations = [event for event in events if event['type'] == 'iteration']
    assert stages == [('stageStart', 'down'), ('stageEnd', 'down'), ('stageStart', 'up'), ('stageEnd', 'up')]
    assert [event['index'] for event in iterations] == [1] and iterations[0]['name'] == 'pass'

    metrics = iterations[0]['metrics']
    assert metrics['change'] is None
    assert metrics['upOutletTemperature'] == circuit.coolantExitTemperature
    assert metrics['downOutletTemperature'] == float(circuit.down.state.coolantExitTemperature)
    assert circuit.coolantExitTemperature == twoPassApart.coolantExitTemperature
    assert circuit.coolantExitPressure == twoPassApart.coolantExitPressure

def testEachOuterPassSendsAndKeepsWhereItLeftEachLeg(jacket):

    '''

    Every outer pass sends a profiles event after its iteration event, the down and up legs each
    with its stations' axial positions, metal hot wall and coolant, and the solution keeps the same
    passes; the last is the solved legs themselves.

    '''

    from NOVA import progress

    _, base, geometry, thermal = jacket
    events = []
    with progress.reporting(events.append):
        circuit = solveCoolantCircuit(copy.deepcopy(base), geometry, thermal, 'twoPass', material = 'GRCop-42')

    loop = [event for event in events if event['type'] in ('iteration', 'profiles')]
    assert [(event['type'], event['index']) for event in loop] == [
        (kind, index) for index in range(1, circuit.iterations + 1) for kind in ('iteration', 'profiles')]
    sent = [event for event in loop if event['type'] == 'profiles']
    assert all(event['path'] == '' and event['name'] == 'pass' for event in sent)
    assert sent[0]['metrics']['change'] is None and sent[-1]['metrics']['change'] == circuit.history[-1]

    kept = circuit.iterationProfiles
    assert [entry['index'] for entry in kept] == list(range(1, circuit.iterations + 1))
    for event, entry in zip(sent, kept):
        for sentLeg, keptLeg in zip(event['profiles'], entry['legs']):
            assert sentLeg['leg'] == keptLeg['leg']
            for name in ('x', 'wall', 'coolant'):
                assert sentLeg[name] == [float(value) for value in keptLeg[name]]
    for leg, solved in zip(kept[-1]['legs'], (circuit.down, circuit.up)):
        assert leg['leg'] == solved.name and leg['x'].size == len(solved.stations)
        assert np.array_equal(leg['coolant'], solved.results['temperature'])
        assert np.array_equal(leg['wall'], solved.results.get('metalWallTemperature', solved.results['wallTemperature']))

def testAMultiPassJacketDrawsItsUpPassOnce(jacket, monkeypatch):

    '''Drawn in the loop, the figure would be written on every outer pass; it is drawn once, of the up pass.'''

    import dataclasses

    from NOVA import channelSizing

    _, base, geometry, thermal = jacket
    drawn = []
    monkeypatch.setattr(channelSizing, 'drawRegenHeatTransfer', lambda context, **kwargs: drawn.append(kwargs))
    circuit = solveCoolantCircuit(copy.deepcopy(base), geometry, dataclasses.replace(thermal, export = 'on'),
                                  'twoPass', material = 'GRCop-42')

    assert circuit.iterations > 1 and len(drawn) == 1
    assert drawn[0]['nChannel'] == circuit.up.channelCount and drawn[0]['results'] is circuit.up.results
