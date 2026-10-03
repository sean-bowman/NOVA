'''

Tests for the manual channel profile in channelProfile.py.

A profile is a coordinate and an interpolation, so everything here has a closed form.

**The signed area ratio is the area ratio.** On a wall built from prescribed area ratios it
returns them exactly, negative upstream of the throat and positive from the throat on, so the
key increases monotonically along the jacket. It holds one value along a constant radius barrel,
which is the reason a recorded profile is not written in it.

**The jacket fraction is the arc length.** It is 0 at the first station and 1 at the last, and on
a wall whose stations are equally spaced along the meridian it is equally spaced too.

**The reader takes four forms and refuses the rest.** A number, a list of pairs, that list
written as text, and a path to a recorded document. Keys that do not increase, a half-extent that
is not a positive length, a shape that is not a table of pairs, a missing file, a file that is
not a profile, a key the package does not build, and a recording of a different channel family
are each refused by name.

**The interpolation is exact at its nodes and flat outside them.** A profile with a point at
every station returns those half-extents bit for bit, which is what lets a recorded profile
rebuild the jacket it came from; between points it is linear in the key, and beyond the first and
last point it holds their values rather than extrapolating.

Author: Sean Bowman

'''

import io
import json

import numpy as np
import pytest

from NOVA.channelProfile import (CHANNELSIZINGMODES, PROFILEKEYS, ChannelProfile, evaluateProfile,
                                 jacketFraction, profileConfigurationBlock, profileDocument,
                                 readProfile, signedAreaRatio, stationKeys)
from NOVA.errors import InvalidInputError

def wallFromAreaRatios(areaRatios, throatRadius = 0.05):

    '''

    A wall whose stations sit at prescribed area ratios, converging then diverging.

    A negative entry is upstream of the throat. The axial coordinate is the station index, which
    is enough for the area ratio key and is not what it reads.

    '''

    radius = throatRadius*np.sqrt(np.abs(np.asarray(areaRatios, dtype = float)))

    return np.arange(len(radius), dtype = float), radius

class TestSignedAreaRatio:

    '''The area ratio key against the ratios the wall was built from.'''

    ratios = [-4.0, -2.25, -1.21, 1.0, 2.25, 4.0, 9.0]

    def testItReturnsTheAreaRatiosTheWallWasBuiltFrom(self):

        _, radius = wallFromAreaRatios(self.ratios)

        assert np.allclose(signedAreaRatio(radius), self.ratios, rtol = 1e-14)

    def testTheThroatStationReadsPlusOne(self):

        _, radius = wallFromAreaRatios(self.ratios)
        key = signedAreaRatio(radius)

        assert key[int(np.argmin(radius))] == pytest.approx(+1.0, rel = 1e-14)
        assert key[int(np.argmin(radius)) - 1] < -1.0

    def testItIncreasesMonotonicallyAlongTheJacket(self):

        _, radius = wallFromAreaRatios(self.ratios)

        assert np.all(np.diff(signedAreaRatio(radius)) > 0.0)

    def testAFlatThroatReadsPlusOneFromItsFirstStationOn(self):

        # Four stations at the same smallest radius, which keeps the key non-decreasing
        radius = np.concatenate([np.linspace(0.1, 0.05, 3), np.full(4, 0.05),
                                 np.linspace(0.06, 0.1, 3)])
        key = signedAreaRatio(radius)

        assert np.allclose(key[2:6], 1.0, rtol = 1e-14)
        assert np.all(np.diff(key) >= 0.0)

    def testItHoldsOneValueAlongABarrel(self):

        # A barrel of five stations at a contraction ratio of 3.2, then a converging run
        radius = np.concatenate([np.full(5, 0.05*np.sqrt(3.2)), np.linspace(0.08, 0.05, 4)])
        key    = signedAreaRatio(radius)

        assert np.allclose(key[:5], -3.2, rtol = 1e-14)
        assert np.all(np.diff(key[:5]) == 0.0)

    def testAWallWithNoThroatUpstreamIsAllPositive(self):

        radius = np.linspace(0.05, 0.15, 6)

        assert np.all(signedAreaRatio(radius) > 0.0)

    @pytest.mark.parametrize('radius', ([0.05], [[0.05, 0.06]], [0.05, 0.0], [0.05, np.nan],
                                        [0.05, -0.06]))
    def testItRefusesAWallItCannotBuildAKeyFrom(self, radius):

        with pytest.raises(InvalidInputError):
            signedAreaRatio(radius)

class TestJacketFraction:

    '''The fraction key against the arc length it is built from.'''

    def testItRunsFromZeroToOne(self):

        axial, radius = wallFromAreaRatios([-4.0, -1.0, 1.0, 4.0])
        fraction = jacketFraction(axial, radius)

        assert fraction[0] == 0.0
        assert fraction[-1] == 1.0

    def testEquallySpacedStationsGiveEquallySpacedFractions(self):

        # A straight cone, so equal axial steps are equal meridional steps
        axial  = np.linspace(0.0, 0.4, 9)
        radius = np.linspace(0.05, 0.15, 9)

        assert np.allclose(jacketFraction(axial, radius), np.linspace(0.0, 1.0, 9), rtol = 1e-14)

    def testItIsTheCumulativeArcLengthOverTheTotal(self):

        axial  = np.array([0.0, 0.3, 0.3, 0.6])
        radius = np.array([0.05, 0.05, 0.45, 0.45])
        # Three segments of 0.3, 0.4 and 0.3, total 1.0
        assert np.allclose(jacketFraction(axial, radius), [0.0, 0.3, 0.7, 1.0], rtol = 1e-14)

    def testItRefusesAWallWithNoLength(self):

        with pytest.raises(InvalidInputError):
            jacketFraction(np.zeros(4), np.full(4, 0.05))

    def testItRefusesMismatchedCoordinates(self):

        with pytest.raises(InvalidInputError):
            jacketFraction(np.linspace(0.0, 1.0, 5), np.linspace(0.05, 0.1, 6))

class TestStationKeys:

    '''The dispatch from a key name to the key.'''

    def testEachKeyNameReturnsItsOwnKey(self):

        axial, radius = wallFromAreaRatios([-4.0, -1.0, 1.0, 4.0])

        assert np.array_equal(stationKeys('areaRatio', axial, radius), signedAreaRatio(radius))
        assert np.array_equal(stationKeys('jacketFraction', axial, radius),
                              jacketFraction(axial, radius))

    def testEveryDeclaredKeyIsBuilt(self):

        axial, radius = wallFromAreaRatios([-4.0, -1.0, 1.0, 4.0])

        for name in PROFILEKEYS:
            assert len(stationKeys(name, axial, radius)) == len(radius)

    def testItRefusesAKeyItDoesNotBuild(self):

        axial, radius = wallFromAreaRatios([-4.0, -1.0, 1.0, 4.0])

        with pytest.raises(InvalidInputError):
            stationKeys('axialPosition', axial, radius)

class TestReadProfile:

    '''The four forms a configuration may carry, and what is refused.'''

    points = [[-2.0, 0.0015], [1.0, 0.0012], [3.0, 0.004]]

    def testANumberIsAConstantChannel(self):

        profile = readProfile(0.0015)

        assert profile.points.shape == (1, 2)
        assert profile.points[0, 1] == 0.0015

    def testAListOfPairsIsTheControlPoints(self):

        profile = readProfile(self.points)

        assert np.array_equal(profile.points, np.asarray(self.points))

    def testThatListWrittenAsTextReadsTheSame(self):

        assert np.array_equal(readProfile(json.dumps(self.points)).points,
                              readProfile(self.points).points)

    def testANumberWrittenAsTextReadsTheSame(self):

        assert np.array_equal(readProfile('0.0015').points, readProfile(0.0015).points)

    def testTheConfiguredKeyIsCarried(self):

        assert readProfile(self.points, 'jacketFraction').keyName == 'jacketFraction'

    def testARecordedProfileReplaysOnItsOwnKey(self, tmp_path):

        document = profileDocument('circle', 'jacketFraction', [0.0, 0.5, 1.0],
                                   [0.001, 0.002, 0.003])
        path = tmp_path / 'profile.json'
        with io.open(path, 'w', encoding = 'utf-8') as handle:
            json.dump(document, handle)

        # The configuration asks for area ratio and the recording overrules it
        profile = readProfile(str(path), 'areaRatio', 'circle')

        assert profile.keyName == 'jacketFraction'
        assert profile.channelType == 'circle'
        assert profile.source == str(path)
        assert np.array_equal(profile.points, np.asarray(document['points']))

    def testARecordingOfAnotherFamilyIsRefused(self, tmp_path):

        document = profileDocument('rectangular', 'jacketFraction', [0.0, 1.0], [0.001, 0.002])
        path = tmp_path / 'profile.json'
        with io.open(path, 'w', encoding = 'utf-8') as handle:
            json.dump(document, handle)

        with pytest.raises(InvalidInputError):
            readProfile(str(path), 'jacketFraction', 'circle')

    def testARecordingOnAnUnknownKeyIsRefused(self, tmp_path):

        path = tmp_path / 'profile.json'
        with io.open(path, 'w', encoding = 'utf-8') as handle:
            json.dump({'key': 'stationIndex', 'points': [[0.0, 0.001]]}, handle)

        with pytest.raises(InvalidInputError):
            readProfile(str(path))

    def testAMissingFileIsRefused(self):

        with pytest.raises(InvalidInputError):
            readProfile('nowhere/noSuchProfile.json')

    def testAFileThatIsNotAProfileIsRefused(self, tmp_path):

        path = tmp_path / 'notAProfile.json'
        with io.open(path, 'w', encoding = 'utf-8') as handle:
            json.dump({'channelRadius': [0.001, 0.002]}, handle)

        with pytest.raises(InvalidInputError):
            readProfile(str(path))

    @pytest.mark.parametrize('entry', (
        [[3.0, 0.002], [-2.0, 0.001]],                 # keys that do not increase
        [[1.0, 0.002], [1.0, 0.001]],                  # a repeated key
        [[1.0, 0.0], [2.0, 0.001]],                    # a half-extent of nothing
        [[1.0, -0.001], [2.0, 0.001]],                 # a negative half-extent
        [[1.0, np.nan]],                               # a half-extent that is not a number
        [[1.0, 0.001, 0.002]],                         # a row that is not a pair
        [0.001, 0.002, 0.003],                         # half-extents with no keys
        [],                                            # nothing at all
        'not a profile at all',                        # neither a list nor a file
    ))
    def testWhatIsRefused(self, entry):

        with pytest.raises(InvalidInputError):
            readProfile(entry)

    def testTextThatIsNotAListIsRefused(self):

        with pytest.raises(InvalidInputError):
            readProfile('[[1.0, 0.001], ')

class TestEvaluateProfile:

    '''The interpolation, at its nodes, between them and beyond them.'''

    def testASinglePointIsAConstantChannel(self):

        profile = readProfile(0.0015)

        assert np.all(evaluateProfile(profile, [-3.0, -1.0, 1.0, 5.0]) == 0.0015)

    def testItIsExactAtItsNodes(self):

        keys        = np.linspace(0.0, 1.0, 17)
        halfExtents = 0.001 + 0.002*keys**2
        profile     = readProfile(np.column_stack([keys, halfExtents]).tolist(), 'jacketFraction')

        # Bit for bit, which is what lets a recorded profile rebuild its own jacket
        assert np.array_equal(evaluateProfile(profile, keys), halfExtents)

    def testItIsLinearBetweenItsNodes(self):

        profile = readProfile([[0.0, 0.001], [1.0, 0.003]], 'jacketFraction')

        assert evaluateProfile(profile, [0.25]) == pytest.approx(0.0015, rel = 1e-15)
        assert evaluateProfile(profile, [0.5]) == pytest.approx(0.002, rel = 1e-15)

    def testItHoldsItsEndValuesBeyondItsRange(self):

        profile = readProfile([[-1.0, 0.001], [1.0, 0.003]])

        assert evaluateProfile(profile, [-9.0]) == pytest.approx(0.001, rel = 1e-15)
        assert evaluateProfile(profile, [40.0]) == pytest.approx(0.003, rel = 1e-15)

class TestProfileDocument:

    '''What a run records, and what reads it back.'''

    def testItRoundTripsExactly(self):

        keys        = np.linspace(0.0, 1.0, 11)
        halfExtents = np.array([0.0012345678901234, 0.002, 0.0031, 0.0042, 0.0053, 0.0064,
                                0.0075, 0.0086, 0.0097, 0.0108, 0.0119])
        document = profileDocument('circle', 'jacketFraction', keys, halfExtents)

        replayed = readProfile(document['points'], document['key'], 'circle')

        assert np.array_equal(replayed.points[:, 0], keys)
        assert np.array_equal(replayed.points[:, 1], halfExtents)

    def testItCarriesTheFamilyTheKeyAndAnyNotes(self):

        document = profileDocument('helical', 'areaRatio', [-2.0, 2.0], [0.001, 0.002],
                                   notes = {'nChannel': 40})

        assert document['channelType'] == 'helical'
        assert document['key'] == 'areaRatio'
        assert document['notes'] == {'nChannel': 40}

    def testNotesAreLeftOutWhenThereAreNone(self):

        assert 'notes' not in profileDocument('circle', 'areaRatio', [1.0], [0.001])

    def testItRefusesMismatchedKeysAndHalfExtents(self):

        with pytest.raises(InvalidInputError):
            profileDocument('circle', 'areaRatio', [0.0, 1.0], [0.001])

    def testItRefusesADistributionItCouldNotReadBack(self):

        with pytest.raises(InvalidInputError):
            profileDocument('circle', 'areaRatio', [1.0, 0.0], [0.001, 0.002])

class TestConfigurationBlock:

    '''The recorded profile as the configuration that replays it.'''

    document = profileDocument('circle', 'jacketFraction', [0.0, 0.5, 1.0],
                               [0.0012345678901234, 0.002, 0.003])

    def testItNamesTheModeAndTheKey(self):

        block = profileConfigurationBlock(self.document)

        assert '"channelSizingMode": "manual"' in block
        assert '"manualChannelProfileKey": "jacketFraction"' in block

    def testItsPointsReadBackAtFullPrecision(self):

        block  = profileConfigurationBlock(self.document)
        entry  = block.split('"manualChannelProfile": ')[1]

        assert np.array_equal(readProfile(json.loads(entry)).points,
                              np.asarray(self.document['points']))

    def testItIsOneLinePerEntry(self):

        assert len(profileConfigurationBlock(self.document).splitlines()) == 3

class TestRecordedFile:

    '''The file a run writes beside its geometry, and reading it back.'''

    def nozzle(self):

        '''The attributes the writer reads off a generated nozzle.'''

        from types import SimpleNamespace

        keys = np.linspace(0.0, 1.0, 9)

        return SimpleNamespace(
            channelType            = 'circle',
            channelSizingMode      = 'thermal',
            channelProfilePoints   = np.column_stack([keys, 0.001 + 0.002*keys]),
            channelWallTemperature = np.full(9, 800.0),
            maxWallTemperature     = 800.0,
            nChannel               = 60,
            numCrossSections       = 9,
            coolantExitTemperature = 252.7,
            coolantExitPressure    = 1.18e7)

    def testWhatIsWrittenReadsBackAsTheSameProfile(self, tmp_path):

        from NOVA.exports import writeChannelProfile

        nozzle = self.nozzle()
        path = tmp_path / 'runChannelProfile.json'
        writeChannelProfile(str(path), nozzle)

        profile = readProfile(str(path), 'areaRatio', 'circle')

        assert profile.keyName == 'jacketFraction'
        assert np.array_equal(profile.points, nozzle.channelProfilePoints)

    def testItRecordsWhatEngineItCameFrom(self, tmp_path):

        from NOVA.exports import writeChannelProfile

        path = tmp_path / 'runChannelProfile.json'
        writeChannelProfile(str(path), self.nozzle())

        with io.open(path, encoding = 'utf-8') as handle:
            document = json.load(handle)

        assert document['notes']['nChannel'] == 60
        assert document['notes']['channelSizingMode'] == 'thermal'
        assert document['notes']['peakWallTemperature'] == 800.0

class TestDeclaredVocabulary:

    '''The names the configuration is checked against.'''

    def testTheSizingModesAreTheTwoTheSolveBuilds(self):

        assert CHANNELSIZINGMODES == ('thermal', 'manual')

    def testTheProfileIsADataclassCarryingItsOwnKey(self):

        profile = readProfile([[0.0, 0.001]], 'jacketFraction')

        assert isinstance(profile, ChannelProfile)
        assert profile.keyName in PROFILEKEYS
        assert profile.source is None
