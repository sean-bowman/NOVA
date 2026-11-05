'''

Tests for guards that keep a configuration or a solve from carrying a wrong value forward.

Each of these was a defect: a null configuration value read as NaN past a default, a throat read
off the smallest station of a resampled wall, a friction march handed jacket temperatures
stretched over the bell by index, a coolant entrance length measured from the wrong end, a volute
wall sized on one alloy whatever the jacket was made of, a CEA lock that held only within one
process. The pipeline tests at the end run the solve itself, because the failures they guard
against only appeared in a full run.

The runs start from the single-pass NOVA reference in assets/examples/novaSinglePass.json, the
jacket these guards were written against, rather than the shipped configuration, so a change to
the shipped engine's cooling architecture does not change what any of them tests. Other test
modules build their full runs on the same helper.

Author: Sean Bowman

'''

import copy
import json
import os
import threading

import numpy as np
import pytest

from NOVA.boundaryLayer import wallTemperatureProfile
from NOVA.ceaInterface import _CEAOBJLOCK
from NOVA.channelGeometry import ChannelGeometryInputs, generateCrossSections
from NOVA.errors import InvalidInputError, VoluteGenerationError
from NOVA.geometryTools import sizedThroatRadius
from NOVA.materials import wallMaterialCurves
from NOVA.nozzleVolutes import solveRegenVolutes, voluteYieldStrength
from NOVA.radiativeCooling import RadiativeShell, radiativeNozzleExtension

repositoryRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
referencePath = os.path.join(repositoryRoot, 'src', 'NOVA', 'assets', 'examples', 'novaSinglePass.json')

def reference() -> dict:

    '''The single-pass NOVA reference configuration, read fresh.'''

    with open(referencePath, encoding = 'utf-8') as handle:
        return json.load(handle)

class TestTheThroatOfASampledWall:

    def testTheSizedRadiusWinsOverAStationAboveIt(self):

        assert sizedThroatRadius([0.0508, 0.06, 0.08], 0.0505) == 0.0505

    def testAStationBelowTheSizedRadiusIsTheThroat(self):

        assert sizedThroatRadius([0.0500, 0.06], 0.0505) == 0.0500

    @pytest.mark.parametrize('scalingFactor', [None, float('nan'), 0.0])
    def testWithoutASizedRadiusTheSmallestStationIsTheThroat(self, scalingFactor):

        assert sizedThroatRadius([0.0508, 0.06], scalingFactor) == 0.0508

class TestTheFrictionWallTemperature:

    def testTheJacketIsPlacedByAxialPositionNotByIndex(self):

        # A jacket over the first quarter of the wall, at a temperature that rises with x
        wallX = np.linspace(0.0, 1.0, 101)
        jacketX = np.linspace(0.0, 0.25, 11)
        jacketTemperature = 500.0 + 1000.0 * jacketX

        profile = wallTemperatureProfile(wallX, jacketX, jacketTemperature)

        inside = wallX <= 0.25
        assert np.allclose(profile[inside], 500.0 + 1000.0 * wallX[inside])
        # Past the jacket with no extension solution the last jacket value holds
        assert np.all(profile[~inside] == jacketTemperature[-1])

    def testTheExtensionCarriesItsOwnSolvedTemperature(self):

        wallX = np.linspace(0.0, 1.0, 101)
        jacketX = np.linspace(0.0, 0.25, 11)
        extensionX = np.linspace(0.25, 1.0, 31)
        extensionTemperature = np.full(31, 2200.0)

        profile = wallTemperatureProfile(wallX, jacketX, np.full(11, 600.0), extensionX,
                                         extensionTemperature)

        assert np.all(profile[wallX >= 0.25] == 2200.0)
        assert np.all(profile[wallX < 0.25] == 600.0)

    def testTheJacketHoldsUntilTheExtensionBegins(self):

        # The jacket's stations stop short of the joint, where the inlet interface turns the
        # channels off the wall; that stretch is still the jacket's wall
        wallX = np.linspace(0.0, 1.0, 101)
        jacketX = np.linspace(0.0, 0.20, 11)
        extensionX = np.linspace(0.25, 1.0, 31)

        profile = wallTemperatureProfile(wallX, jacketX, np.full(11, 600.0), extensionX,
                                         np.full(31, 2200.0))

        between = (wallX > 0.20) & (wallX < 0.25)
        assert between.any()
        assert np.all(profile[between] == 600.0)

class TestTheEntranceLengthInTheSizingMarch:

    def testOneStationInMarchOrderCountsFromTheInletAtTheFirstStation(self):

        # The sizing march hands its centerline over inlet first, filled to the station it is
        # solving and the one after it
        stations = 20
        geometry = ChannelGeometryInputs(numCrossSections = stations, numCSPointsChannel = 24,
                                         nChannel = 60, channelType = 'circle',
                                         hotWallThickness = 1.0e-3, infillThickness = 1.0e-3)
        z = np.linspace(0.0, 0.2, stations)
        x, y = np.full(stations, 0.06), np.zeros(stations)
        station = 7
        x[station + 2:], z[station + 2:] = 0.0, 0.0
        radius = np.full(stations, 0.002)

        single = generateCrossSections(geometry, x, y, z, radius, 'circle', i = station)

        spacing = 0.2 / (stations - 1)
        assert single['distanceFromInlet'][0] == pytest.approx((station + 1) * spacing, rel = 1e-12)

class TestTheVoluteWallStrength:

    @pytest.mark.parametrize('material', ['GRCop-42', 'Inconel 718', 'CuCrZr'])
    def testItIsTheJacketAlloysOwnYieldCurve(self, material):

        curves = wallMaterialCurves(material)
        expected = float(np.interp(400.0, curves['temperatureK'], curves['yieldStrength']))

        assert voluteYieldStrength(material, 400.0) == expected

    def testAStrongerAlloyAllowsAThinnerWall(self):

        assert voluteYieldStrength('Inconel 718', 293.15) > voluteYieldStrength('GRCop-42', 293.15)

class TestTheCeaLock:

    def testItIsReentrantInOneThread(self):

        with _CEAOBJLOCK:
            with _CEAOBJLOCK:
                assert _CEAOBJLOCK._depth == 2
        assert _CEAOBJLOCK._depth == 0

    def testItExcludesASecondThread(self):

        entered = []

        def other():
            with _CEAOBJLOCK:
                entered.append(True)

        with _CEAOBJLOCK:
            thread = threading.Thread(target = other)
            thread.start()
            thread.join(timeout = 0.3)
            assert entered == []
        thread.join(timeout = 5.0)
        assert entered == [True]

class TestTheExtensionDrive:

    def testAnUnphysicalDrivingTemperatureIsRefused(self):

        stations = 21
        recovery = np.linspace(2600.0, 1900.0, stations)
        recovery[3] = -164.0
        shell = RadiativeShell(thermalConductivity = 45.0, thickness = 5.0e-4,
                               innerEmissivity = 0.0, outerEmissivity = 0.8, gasEmissivity = 0.0)

        with pytest.raises(InvalidInputError, match = 'no gas can be'):
            radiativeNozzleExtension(
                shell, np.linspace(0.0, 0.6, stations), np.linspace(0.10, 0.32, stations),
                np.linspace(2.6, 3.8, stations), np.linspace(1500.0, 900.0, stations), recovery,
                chamberPressure = 6.895e6, characteristicVelocity = 2300.0, exhaustGamma = 1.20,
                exhaustGasConstant = 520.0, exhaustMolecularWeight = 16.0, throatRadius = 0.05,
                throatRadiusOfCurvature = 0.04)

class TestACoatedWallsMargin:

    '''The limit is on the metal; a barrier coating's surface runs hotter by design.'''

    @staticmethod
    def report(capsys, metal, surface):

        from types import SimpleNamespace
        from NOVA.channelSizing import reportSizingResult

        state = SimpleNamespace(channelRadius = np.full(4, 2.0e-3), maxWallTemperature = 900.0,
                                coolantInitialPressure = 13.8e6, coolantExitPressure = 13.0e6,
                                coolantExitTemperature = 330.0, channelSizingMode = 'manual',
                                channelSplitBlend = None, numCrossSections = 4, nChannel = 90)
        reportSizingResult(state, {'wallTemperature': surface, 'metalWallTemperature': metal})
        return capsys.readouterr().out

    def testTheMarginIsReadOffTheMetal(self, capsys):

        metal = np.array([600.0, 725.0, 700.0, 650.0])
        out = self.report(capsys, metal, metal + 1500.0)

        assert 'peak hot wall 725.0 K at station 1, -175.0 K against the 900.0 K limit' in out
        assert 'coating surface peaks at 2225.0 K' in out

    def testAnUncoatedWallPrintsNoCoatingLine(self, capsys):

        wall = np.array([600.0, 725.0, 700.0, 650.0])

        assert 'coating' not in self.report(capsys, wall, wall.copy())

class TestNullConfigurationValues:

    def testANullReadsAsUnsetAndTakesTheDefault(self, tmp_path, monkeypatch):

        from NOVA import Nozzle
        monkeypatch.setattr(Nozzle, '_getOutputRoot', lambda self: str(tmp_path))

        config = reference()
        for key in ('filmCoolingModel', 'filmCoolantMixtureRatio', 'filmEntrainmentMultiplier',
                    'extensionSinkTemperature', 'extensionOuterViewFactor', 'extensionAtmosphere',
                    'gasSideAxialModel', 'coolantRoughnessModel', 'maxVoluteBore', 'gammaModel'):
            config[key] = None

        nozzle = Nozzle()
        nozzle.setInputs(inputsPath = config)

        assert nozzle.filmCoolingModel == 'hatchPapell'
        assert nozzle.filmCoolantMixtureRatio == 0.0
        assert nozzle.filmEntrainmentMultiplier == 3.5
        assert nozzle.extensionSinkTemperature == 0.0
        assert nozzle.extensionOuterViewFactor == 1.0
        assert nozzle.extensionAtmosphere == 'inert'
        assert nozzle.gasSideAxialModel == 'uniform'
        assert nozzle.coolantRoughnessModel == 'dippreySabersky'
        assert nozzle.maxVoluteBore == 0.15
        assert nozzle.gammaModel == 'chamber'

# -- Full runs -- #

def runConfiguration(directory, **overrides):

    '''Run the single-pass reference nozzle with overrides into a directory and return the solved Nozzle.'''

    from NOVA import Nozzle

    config = reference()
    config.update({'plotsEnabled': False, 'export': False, 'filename': 'guard',
                   'plumeAmbientPressure': None, 'plumeFieldReach': None,
                   'numCrossSections': 24, 'numCSPointsChannel': 24, 'numCSVolute': 24,
                   'numCSPointsVolute': 24})
    config.update(overrides)
    path = os.path.join(str(directory), 'guard.json')
    with open(path, 'w', encoding = 'utf-8', newline = '\n') as handle:
        json.dump(config, handle)

    # The output root is patched on the class for the length of the run rather than on a subclass,
    # because an export pickles the Nozzle and a class defined in here cannot be pickled
    original = Nozzle._getOutputRoot
    Nozzle._getOutputRoot = lambda self: str(directory)
    try:
        nozzle = Nozzle()
        nozzle.generateNozzle(configPath = path)
    finally:
        Nozzle._getOutputRoot = original
    return nozzle

@pytest.fixture(scope = 'module')
def outletOnly(tmp_path_factory):

    directory = tmp_path_factory.mktemp('outletOnly')
    return runConfiguration(directory, makeInletVolute = False, makeOutletVolute = True,
                            makeRadiativeExtension = False, export = True), directory

class TestTheOutletOnlyBuild:

    def testItExportsWithoutAnInletVolute(self, outletOnly):

        nozzle, directory = outletOnly
        written = os.listdir(nozzle.dataFolder)

        assert nozzle.inletVolute is None
        assert any(name.endswith('OutletVolute.stl') for name in written)
        assert any(name.endswith('Performance.json') for name in written)

    def testAScrollPastTheBoreLimitIsRefused(self, outletOnly):

        nozzle, _ = outletOnly
        state = copy.deepcopy(nozzle.regenVoluteState())
        state.makeInletVolute, state.maxVoluteBore = 'on', 0.005

        with pytest.raises(VoluteGenerationError) as refusal:
            solveRegenVolutes(state)
        assert refusal.value.context['failureMode'] == 'throatBeyondLimit'

    def testAScrollGrownIntoTheWallIsRefused(self, outletOnly):

        nozzle, _ = outletOnly
        state = copy.deepcopy(nozzle.regenVoluteState())
        state.makeInletVolute, state.inletVoluteAlignment = 'on', 'o'

        with pytest.raises(VoluteGenerationError) as refusal:
            solveRegenVolutes(state)
        assert refusal.value.context['failureMode'] == 'scrollInsideWall'

def testAConeRunsTheWholeContourWithoutAnExtension(tmp_path):

    nozzle = runConfiguration(tmp_path, divergingSectionType = 'cone', regenTruncationType = 'none',
                              makeCoolingChannels = False, makeInletVolute = False,
                              makeOutletVolute = False, makeRadiativeExtension = True,
                              filmCooling = False)

    assert len(nozzle.xRegenNozzle) == nozzle.numCrossSections
    assert nozzle.xExtension is None or len(nozzle.xExtension) == 0
    assert nozzle.performance is not None

def testAChamberTooNarrowForItsConvergingArcsIsRefused(tmp_path):

    # The chamber fillet and the throat arc would overlap and fold the wall back on itself
    with pytest.raises(InvalidInputError, match = 'too narrow'):
        runConfiguration(tmp_path, chamberDiameter = 0.105, makeCoolingChannels = False,
                         makeInletVolute = False, makeOutletVolute = False, makeRadiativeExtension = False,
                         filmCooling = False)
