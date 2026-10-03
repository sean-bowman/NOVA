'''

Tests for the regenerative cooling channel build in regenChannels.py.

The build is orchestration, not physics: it decides the order things happen in and threads
geometry between the modules that compute it. So these tests check the things orchestration can
get wrong, which are different from the things a correlation can get wrong.

**The state is the contract.** Every field the build touches must be declared on it, and the
Nozzle must seed every field it declares. A field reached by name rather than by attribute is
the case that slips past a static read: a rule table names its fields as strings, and a missing
declaration there surfaces only when a run reaches that rule. Both directions are checked here.

**The validator is a rule table.** What it enforces is data, so what is checked here is that
the table names fields the state actually has, and that it rejects what it says it rejects. The
checker behind it is tested in testValidation.py rather than through this module.

**A failure has to survive being reported.** The wall temperature limit is one temperature for
the whole jacket, and a limit that is not a usable number stops the sizing search from running
at all rather than sizing anything conservatively, so it is checked before the solve reads it.
The error a station raises when it will not converge is built from scalars here, because a
handler that raises while reporting a failure loses the failure.

Author: Sean Bowman

'''

import ast
import io
import os
import sys

import numpy as np
import pytest

repositoryRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
packageDirectory = os.path.join(repositoryRoot, 'src', 'NOVA')
from NOVA.regenChannels import (RegenChannelState, regenChannelOutputs, regenChannelRules,
                           validateRegenChannelInputs)
from NOVA.validation import fieldsCovered

def workingInputs():

    '''A channel definition the validator accepts.'''

    stations = 60

    return RegenChannelState(
        nChannel                  = 60,
        minChannelRadius          = 0.75e-3,
        hotWallThickness          = 1.0e-3,
        infillThickness           = 1.0e-3,
        channelType               = 'circle',
        maxWallTemperature        = 800.0,
        coolant                   = 'Hydrogen',
        coolantMassFlow           = 3.4,
        coolantInitialPressure    = 1.2e7,
        coolantInitialTemperature = 30.0,
        numCrossSections          = stations,
        xRegenNozzle              = np.linspace(0.0, 0.3, stations),
        rRegenNozzle              = np.linspace(0.09, 0.05, stations))

class TestStateContract:

    '''Every field the build reaches must be declared, and every declared field must be seeded.'''

    def stringAddressedFields(self):

        '''Field names the rule table addresses, which are strings rather than attributes.'''

        return fieldsCovered(regenChannelRules)

    def attributeAddressedFields(self):

        '''Field names the module reaches as state.something.'''

        source = io.open(os.path.join(packageDirectory, 'regenChannels.py'),
                         encoding = 'utf-8').read()

        return {node.attr for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == 'state'}

    def testEveryStringAddressedFieldIsDeclared(self):

        # This is the one a static read of the module cannot catch: a rule names its field as
        # a string, so a missing declaration surfaces only when a run reaches that rule.
        declared = set(RegenChannelState.__dataclass_fields__)
        reached = self.stringAddressedFields()

        assert reached, 'no string-addressed fields found, so this test is not checking anything'
        assert reached <= declared, sorted(reached - declared)

    def testEveryAttributeAddressedFieldIsDeclared(self):

        declared = set(RegenChannelState.__dataclass_fields__)
        reached = self.attributeAddressedFields()

        assert reached <= declared, sorted(reached - declared)

    def testEveryOutputIsADeclaredField(self):

        declared = set(RegenChannelState.__dataclass_fields__)

        assert set(regenChannelOutputs) <= declared, sorted(set(regenChannelOutputs) - declared)

    def testEverySizingOutputIsCarriedThrough(self):

        # The build copies the sizing solve's outputs onto its own state by name, which a static
        # read of the module cannot see. Anything the sizing solve produces and the build does
        # not hand on is silently lost, and the loss shows up far downstream as an empty array.
        from NOVA.channelSizing import channelSizingOutputs

        dropped = [name for name in channelSizingOutputs if name not in regenChannelOutputs]

        assert dropped == []

    def testTheNozzleSeedsEveryField(self):

        # The state is filled by name rather than one line at a time, so the check that it stays
        # complete is that a fresh Nozzle can seed all of it.
        import matplotlib
        matplotlib.use('Agg', force = True)
        from NOVA.Nozzle import Nozzle

        state = Nozzle().regenChannelState()
        missing = [name for name in RegenChannelState.__dataclass_fields__
                   if not hasattr(state, name)]

        assert missing == []

    def testEveryFieldStartsUnset(self):

        # An output still None after a build is a step that was not reached, which is only
        # readable if every field starts None.
        state = RegenChannelState()
        filled = [name for name in RegenChannelState.__dataclass_fields__
                  if getattr(state, name) is not None]

        assert filled == []

class TestValidator:

    '''The validator rejects what it says it rejects.'''

    def testAWorkingDefinitionPasses(self):

        validateRegenChannelInputs(workingInputs())

    @pytest.mark.parametrize('field', ['nChannel', 'minChannelRadius', 'hotWallThickness',
                                       'coolant', 'coolantMassFlow', 'coolantInitialPressure',
                                       'coolantInitialTemperature', 'numCrossSections'])
    def testAnUnsetFieldIsRejected(self, field):

        state = workingInputs()
        setattr(state, field, None)

        with pytest.raises(Exception, match = field):
            validateRegenChannelInputs(state)

    def testTooFewChannelsIsRejected(self):

        state = workingInputs()
        state.nChannel = 4

        with pytest.raises(Exception, match = 'nChannel'):
            validateRegenChannelInputs(state)

    def testAChannelBelowTheProcessMinimumIsRejected(self):

        state = workingInputs()
        state.minChannelRadius = 0.1e-3

        with pytest.raises(Exception, match = 'minChannelRadius'):
            validateRegenChannelInputs(state)

    def testAWallThinnerThanTheProcessCanBuildIsRejected(self):

        state = workingInputs()
        state.hotWallThickness = 0.1e-3

        with pytest.raises(Exception, match = 'hotWallThickness'):
            validateRegenChannelInputs(state)

    @pytest.mark.parametrize('flow', [0.0, -1.0])
    def testANonPositiveCoolantFlowIsRejected(self, flow):

        state = workingInputs()
        state.coolantMassFlow = flow

        with pytest.raises(Exception, match = 'coolantMassFlow'):
            validateRegenChannelInputs(state)

    def testMismatchedContourArraysAreRejected(self):

        state = workingInputs()
        state.rRegenNozzle = state.rRegenNozzle[:-5]

        with pytest.raises(Exception):
            validateRegenChannelInputs(state)

    def testARibThinnerThanTheProcessCanBuildIsRejected(self):

        state = workingInputs()
        state.infillThickness = 0.2e-3

        with pytest.raises(Exception, match = 'infillThickness'):
            validateRegenChannelInputs(state)

    def testARectangleNeedsItsWidthAndAspectLimits(self):

        state = workingInputs()
        state.channelType = 'rectangular'

        with pytest.raises(Exception, match = 'minChannelWidth'):
            validateRegenChannelInputs(state)

        state.minChannelWidth, state.maxChannelAspectRatio = 1.0e-3, 8.0
        validateRegenChannelInputs(state)

    @pytest.mark.parametrize('aspectRatio', [0.0, 25.0])
    def testAnAspectRatioOutsideItsRangeIsRejected(self, aspectRatio):

        state = workingInputs()
        state.channelType = 'rectangular'
        state.minChannelWidth, state.maxChannelAspectRatio = 1.0e-3, aspectRatio

        with pytest.raises(Exception, match = 'maxChannelAspectRatio'):
            validateRegenChannelInputs(state)

    def helical(self, **overrides):

        state = workingInputs()
        state.channelType, state.minChannelWidth = 'helical', 1.0e-3
        state.channelHelixAngle, state.channelAspectRatio = 45.0, 1.0
        for name, value in overrides.items():
            setattr(state, name, value)
        return state

    def testAHelixMayHaveFewStarts(self):

        # The ten-channel process minimum is for straight channels; a helix of one start is one
        # continuous passage around the whole chamber
        validateRegenChannelInputs(self.helical(nChannel = 1))

        with pytest.raises(Exception, match = 'nChannel'):
            validateRegenChannelInputs(self.helical(nChannel = 0))

    @pytest.mark.parametrize('helixAngle', [0.0, 86.0, None])
    def testAHelixAngleOutsideItsRangeIsRejected(self, helixAngle):

        with pytest.raises(Exception, match = 'channelHelixAngle'):
            validateRegenChannelInputs(self.helical(channelHelixAngle = helixAngle))

    @pytest.mark.parametrize('aspectRatio', [0.0, 21.0])
    def testAHelicalAspectRatioOutsideItsRangeIsRejected(self, aspectRatio):

        with pytest.raises(Exception, match = 'channelAspectRatio'):
            validateRegenChannelInputs(self.helical(channelAspectRatio = aspectRatio))

    @pytest.mark.parametrize('channelType', ['fluted', 'hexagon'])
    def testAFamilyThePackageDoesNotBuildIsRejected(self, channelType):

        state = workingInputs()
        state.channelType = channelType

        with pytest.raises(Exception, match = 'channelType'):
            validateRegenChannelInputs(state)

    def testAnUnsetSizingModeIsTheSearch(self):

        # Every configuration written before the manual mode leaves the field out
        validateRegenChannelInputs(workingInputs())

    @pytest.mark.parametrize('mode', ['converge', 'auto', 'Manual'])
    def testASizingModeTheSolveDoesNotBuildIsRejected(self, mode):

        state = workingInputs()
        state.channelSizingMode = mode

        with pytest.raises(Exception, match = 'channelSizingMode'):
            validateRegenChannelInputs(state)

    def testManualSizingNeedsAProfile(self):

        state = workingInputs()
        state.channelSizingMode = 'manual'

        with pytest.raises(Exception, match = 'manualChannelProfile'):
            validateRegenChannelInputs(state)

        state.manualChannelProfile = 1.5e-3
        validateRegenChannelInputs(state)

    def testAProfileKeyThePackageDoesNotBuildIsRejected(self):

        state = workingInputs()
        state.channelSizingMode = 'manual'
        state.manualChannelProfile = 1.5e-3
        state.manualChannelProfileKey = 'stationIndex'

        with pytest.raises(Exception, match = 'manualChannelProfileKey'):
            validateRegenChannelInputs(state)

    @pytest.mark.parametrize('limit', [None, float('nan'), 0.0, -300.0])
    def testAWallTemperatureLimitTheSolveCannotUseIsRejected(self, limit):

        state = workingInputs()
        state.maxWallTemperature = limit

        with pytest.raises(Exception, match = 'maxWallTemperature'):
            validateRegenChannelInputs(state)

    def testAProfileIsOnlyAskedForInTheManualMode(self):

        # A thermal run carrying no profile is the normal case and must not be stopped by one
        state = workingInputs()
        state.channelSizingMode = 'thermal'
        state.manualChannelProfileKey = 'stationIndex'

        validateRegenChannelInputs(state)

class TestModuleIndependence:

    '''The module must stand on its own.'''

    def testItDoesNotImportNozzle(self):

        source = io.open(os.path.join(packageDirectory, 'regenChannels.py'),
                         encoding = 'utf-8').read()

        assert 'import Nozzle' not in source
        assert 'from Nozzle' not in source

    def testNothingReachesThroughSelf(self):

        # A leftover self is a reference to an object the module no longer has.
        source = io.open(os.path.join(packageDirectory, 'regenChannels.py'),
                         encoding = 'utf-8').read()
        offenders = [node.value.id for node in ast.walk(ast.parse(source))
                     if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                     and node.value.id == 'self']

        assert offenders == []

class TestDrivingTemperatureChoice:

    '''

    Which gas temperature the jacket is driven by.

    Convection into a wall is driven by the adiabatic wall temperature, not by the static
    temperature. NOVA computes the recovery temperature in `chamber` and used to drop it before
    the solve, which understated the flux by the whole recovery rise: negligible in the chamber,
    a factor of 1.83 at the supersonic end of the shipped example's jacket. The static path was
    removed once the recovery temperature was carried through: it was never the physical answer.

    '''

    def state(self, **overrides):

        '''A sizing state carrying the recovery array.'''

        from NOVA.channelSizing import ChannelSizingState

        arguments = dict(
            regenSectionNearWallTemperatureTrimmed = np.array([1000.0, 1500.0, 2000.0]),
            regenSectionNearWallRecoveryTemperatureTrimmed = np.array([1100.0, 1900.0, 3200.0]))
        arguments.update(overrides)

        return ChannelSizingState(**arguments)

    def testTheDrivingTemperatureIsTheRecoveryTemperature(self):

        from NOVA.channelSizing import drivingTemperatureArray

        chosen = drivingTemperatureArray(self.state())

        assert np.array_equal(chosen, np.array([1100.0, 1900.0, 3200.0]))

    def testAMissingRecoveryArraySaysSoRatherThanFallingBack(self):

        from NOVA.channelSizing import drivingTemperatureArray
        from NOVA.errors import InvalidInputError

        # Quietly falling back to the static array would reintroduce the whole defect without
        # anything in the output saying it had happened.
        with pytest.raises(InvalidInputError):
            drivingTemperatureArray(
                self.state(regenSectionNearWallRecoveryTemperatureTrimmed = None))

    def testTheStateCarriesTheRecoveryArrayThroughToSizing(self):

        from NOVA.channelSizing import ChannelSizingState

        # The trimmed recovery array has to be a declared field, or _sizingState cannot pass it
        # and the solve silently runs on None.
        assert 'regenSectionNearWallRecoveryTemperatureTrimmed' in \
               ChannelSizingState.__dataclass_fields__
        assert 'regenSectionNearWallRecoveryTemperatureTrimmed' in \
               RegenChannelState.__dataclass_fields__

class TestFilmSupersedesTheDrivingTemperature:

    '''

    A film between the wall and the exhaust replaces the potential, it does not correct it.

    Effectiveness is defined against the adiabatic wall temperature, so the film array is built
    from the recovery temperature and then supersedes it.

    '''

    def state(self, **overrides):

        from NOVA.channelSizing import ChannelSizingState

        arguments = dict(
            regenSectionNearWallTemperatureTrimmed = np.array([1000.0, 1500.0, 2000.0]),
            regenSectionNearWallRecoveryTemperatureTrimmed = np.array([1100.0, 1900.0, 3200.0]),
            regenSectionFilmDrivingTemperatureTrimmed = np.array([400.0, 900.0, 2600.0]))
        arguments.update(overrides)

        return ChannelSizingState(**arguments)

    def testTheFilmArrayIsUsedWhenPresent(self):

        from NOVA.channelSizing import drivingTemperatureArray

        chosen = drivingTemperatureArray(self.state())

        assert np.array_equal(chosen, np.array([400.0, 900.0, 2600.0]))

    def testWithoutAFilmTheRecoveryTemperatureIsBack(self):

        from NOVA.channelSizing import drivingTemperatureArray

        chosen = drivingTemperatureArray(
            self.state(regenSectionFilmDrivingTemperatureTrimmed = None))

        assert np.array_equal(chosen, np.array([1100.0, 1900.0, 3200.0]))

    def testTheFilmNeverDrivesTheWallHarderThanNoFilmWould(self):

        from NOVA.channelSizing import drivingTemperatureArray

        state = self.state()
        withFilm = drivingTemperatureArray(state)
        withoutFilm = drivingTemperatureArray(
            self.state(regenSectionFilmDrivingTemperatureTrimmed = None))

        assert np.all(withFilm <= withoutFilm)

class TestIncompleteFilmDefinition:

    '''A film switched on with pieces missing says which pieces, rather than failing deeper in.'''

    def state(self, **overrides):

        from NOVA.regenStations import RegenStationState

        arguments = dict(filmCooling = 'on', filmCoolant = 'Hydrogen', filmMassFlow = 0.3,
                         filmInletTemperature = 250.0, filmInjectionAxialPosition = -1.0,
                         filmSlotHeight = 0.0015)
        arguments.update(overrides)

        return RegenStationState(**arguments)

    @pytest.mark.parametrize('missing', ['filmCoolant', 'filmMassFlow', 'filmInletTemperature',
                                         'filmInjectionAxialPosition', 'filmSlotHeight'])
    def testEachMissingPieceIsNamed(self, missing):

        from NOVA.regenStations import solveRegenSectionFilm
        from NOVA.errors import InvalidInputError

        with pytest.raises(InvalidInputError) as raised:
            solveRegenSectionFilm(self.state(**{missing: None}))

        assert missing in str(raised.value)

    def testANaNCountsAsMissing(self):

        # config.setInputs rewrites every null to NaN, so a film key left null in a JSON file
        # arrives as NaN rather than None and has to be caught the same way.
        from NOVA.regenStations import solveRegenSectionFilm
        from NOVA.errors import InvalidInputError

        with pytest.raises(InvalidInputError):
            solveRegenSectionFilm(self.state(filmMassFlow = float('nan')))

    def testAFilmSwitchedOffDoesNothingAtAll(self):

        from NOVA.regenStations import solveRegenSectionFilm

        state = self.state(filmCooling = 'off', filmCoolant = None, filmMassFlow = None)
        solveRegenSectionFilm(state)

        assert state.regenSectionFilmDrivingTemperature is None
        assert state.regenSectionFilmEffectiveness is None

class TestVoluteInterface:

    '''

    The fillet and flare that turn a channel off the wall and out to its volute.

    The construction places a fillet tangent to the wall and to a plane normal to the axis, then a
    straight flare along the plane. It draws the fillet at 1.0005 of its radius so the circle is
    certain to cut the wall, which leaves the join 1.8 degrees off tangent, acos(1/1.0005), with
    the arc dipping 0.0005 of the fillet radius into the wall before it rises, and it finds that
    cut against a 300 point polygon, which places it within the polygon's sagitta of the wall. The upstream end, where the outlet volute sits, is the same construction
    reflected, so on a barrel that is symmetric about its middle the two ends must be mirror
    images.

    '''

    radius, length, offset, fillet, flare = 0.09, 0.3, 0.01, 0.02, 0.03

    def sagitta(self):

        '''How far the 300 point fillet polygon sits inside its circle [m].'''

        return 1.0005 * self.fillet * (1 - np.cos(np.pi / 299))

    def barrel(self, numPoints = 200):

        return np.linspace(0.0, self.length, numPoints), np.full(numPoints, self.radius)

    def downstream(self, tilt = 0.0):

        from NOVA.regenChannels import voluteInterfaceCurve

        x, r = self.barrel()
        return voluteInterfaceCurve(x, r, self.offset, self.fillet, -np.deg2rad(tilt), self.flare)

    def upstream(self, tilt = 0.0):

        from NOVA.regenChannels import upstreamVoluteInterfaceCurve

        x, r = self.barrel()
        return upstreamVoluteInterfaceCurve(x, r, self.offset, self.fillet, -np.deg2rad(tilt),
                                            self.flare)

    def testTheFilletLeavesFromTheWall(self):

        xInterface, rInterface, _ = self.downstream()

        assert abs(rInterface[0] - self.radius) < self.sagitta()

        # Off tangent by the 1.0005 oversize and no more, and no deeper into the wall than it
        departure = np.degrees(np.arctan2(rInterface[1] - rInterface[0], xInterface[1] - xInterface[0]))
        assert abs(departure) < np.degrees(np.arccos(1 / 1.0005))
        assert self.radius - rInterface.min() < 5e-4 * self.fillet + self.sagitta()

    def testTheFlareLeavesAlongThePlane(self):

        xInterface, rInterface, _ = self.downstream()
        plane = self.length - self.offset

        # The last 21 points are the flare: radial for zero tilt, flareLength long, and on the
        # plane to within the 1.0005 oversize the fillet it leaves from is drawn at
        assert np.max(np.abs(xInterface[-21:] - plane)) <= 5e-4 * self.fillet * (1 + 1e-9)
        assert rInterface[-1] - rInterface[-22] == pytest.approx(self.flare, rel = 1e-12)

    def testOnlyTheWallBeforeTheFilletIsKept(self):

        xInterface, _, keep = self.downstream()
        x, _ = self.barrel()

        assert np.all(x[keep] < xInterface[0])
        assert np.all(x[~keep] >= xInterface[0])

    def testTheUpstreamEndIsTheMirrorImage(self):

        xDown, rDown, keepDown = self.downstream(tilt = 12.0)
        xUp,   rUp,   keepUp   = self.upstream(tilt = 12.0)

        # Reflected about the middle of the barrel and reversed, one end is the other
        assert np.allclose(self.length - np.flip(xDown), xUp, rtol = 0, atol = 1e-12)
        assert np.allclose(np.flip(rDown), rUp, rtol = 0, atol = 1e-12)
        assert np.array_equal(np.flip(keepDown), keepUp)

    def testTheUpstreamInterfaceRunsFromTheFlareInToTheWall(self):

        xUp, rUp, keep = self.upstream()
        x, _ = self.barrel()

        # Prepended to the wall, so it starts at the flare end and finishes on the wall
        assert rUp[0] == pytest.approx(rUp.max())
        assert abs(rUp[-1] - self.radius) < self.sagitta()
        assert np.all(x[keep] > xUp[-1])

class TestWallTemperatureLimit:

    '''

    The limit the jacket is sized against, and what happens when it is not a number.

    The search compares the wall against the limit every iteration and takes its tolerance from
    it, so with a NaN limit every comparison reads false. The loop leaves before its first
    iteration, every station keeps the largest channel that fits, and the run reports a jacket
    that was never checked against anything. Nothing in the output says so, so the limit is
    checked before the solve reads it.

    '''

    def state(self, limit):

        from NOVA.channelSizing import ChannelSizingState

        return ChannelSizingState(maxWallTemperature = limit)

    def testAUsableLimitComesBackAsAFloat(self):

        from NOVA.channelSizing import wallTemperatureLimit

        assert wallTemperatureLimit(self.state(800.0)) == 800.0
        assert isinstance(wallTemperatureLimit(self.state(np.float64(650.0))), float)

    @pytest.mark.parametrize('limit', [None, float('nan'), float('inf'), 0.0, -1.0, 'hot'])
    def testALimitTheSolveCannotUseIsRejected(self, limit):

        from NOVA.channelSizing import wallTemperatureLimit
        from NOVA.errors import InvalidInputError

        with pytest.raises(InvalidInputError, match = 'maxWallTemperature'):
            wallTemperatureLimit(self.state(limit))

    def testAnArrayOfLimitsIsRejected(self):

        from NOVA.channelSizing import wallTemperatureLimit
        from NOVA.errors import InvalidInputError

        # One temperature for the whole jacket: the search's own comparisons are scalar, and an
        # array would make `abs(error) > tolerance` raise part way through the march instead
        with pytest.raises(InvalidInputError, match = 'maxWallTemperature'):
            wallTemperatureLimit(self.state(np.full(60, 800.0)))

class TestConvergenceFailureReport:

    '''

    The error a station raises when its size will not converge, built from scalars.

    A handler that raises while reporting a failure loses the failure. The limit is one
    temperature for the whole jacket, so every quantity in the context is a scalar and none of
    them is subscripted.

    '''

    def failure(self, **overrides):

        from NOVA.channelSizing import convergenceFailure

        arguments = dict(
            message           = 'Minimum channel radius reached at station 17',
            stationIndex      = 17,
            iterations        = 50,
            radius            = 0.75e-3,
            wallTemperature   = 912.5,
            targetTemperature = 800.0,
            tolerance         = 0.08)
        arguments.update(overrides)

        return convergenceFailure(**arguments)

    def testItBuildsFromAScalarLimit(self):

        from NOVA.errors import ConvergenceFailureError

        failure = self.failure()

        assert isinstance(failure, ConvergenceFailureError)
        assert failure.context['targetTemperature'] == 800.0
        assert failure.context['temperatureError'] == pytest.approx(112.5, rel = 1e-12)
        assert failure.context['stationIndex'] == 17

    def testTheResidualIsTheDistanceFromTheLimit(self):

        assert self.failure(wallTemperature = 700.0).context['temperatureError'] \
               == pytest.approx(100.0, rel = 1e-12)

    def testTheSiteMayAddItsOwnContext(self):

        failure = self.failure(minChannelRadius = 0.75e-3)

        assert failure.context['minChannelRadius'] == 0.75e-3

    def testTheMessageSurvivesRendering(self):

        # The report is what a failed run leaves behind, so it has to render without raising
        assert 'station 17' in str(self.failure())

class TestWallTemperatureRefusal:

    '''

    The station that cannot be cooled, and why it is refused rather than accepted.

    The wall temperature rises with channel size, so the smallest channel the process can build
    gives the coolest wall a station can have. A wall over its limit there is not a search that
    wants more iterations; it is a jacket that cannot be built as specified.

    '''

    def testItNamesTheStationTheWallAndTheLimit(self):

        from NOVA.channelSizing import wallTemperatureExceeded
        from NOVA.errors import ThermalConstraintError

        failure = wallTemperatureExceeded(stationIndex = 31, wallTemperature = 1180.0,
                                          limit = 800.0, halfExtent = 0.75e-3, tolerance = 0.08)

        assert isinstance(failure, ThermalConstraintError)
        assert failure.context['value'] == 1180.0
        assert failure.context['limit'] == 800.0
        assert failure.context['stationIndex'] == 31
        assert 'Station 31' in str(failure)

    def testItSaysWhatWouldFixIt(self):

        from NOVA.channelSizing import wallTemperatureExceeded

        # A message that only reports the violation leaves the reader with no next move
        message = str(wallTemperatureExceeded(0, 1180.0, 800.0, 0.75e-3, 0.08))

        assert 'more channels' in message
        assert 'film' in message

class TestCoolantExitState:

    '''What the coolant leaving the jacket has to be worth to the rest of the engine.'''

    def state(self, **overrides):

        from NOVA.channelSizing import ChannelSizingState

        arguments = dict(coolantInitialPressure    = 1.2e7,
                         coolantExitPressure       = 1.18e7,
                         coolantExitTemperature    = 252.7)
        arguments.update(overrides)

        return ChannelSizingState(**arguments)

    def testNoLimitsPassAnything(self):

        from NOVA.channelSizing import checkCoolantExitState

        # Every configuration written before these were enforced leaves both unset
        checkCoolantExitState(self.state())
        checkCoolantExitState(self.state(minCoolantExitPressure = None,
                                         minCoolantExitTemperature = float('nan')))

    def testAMetPressureLimitPasses(self):

        from NOVA.channelSizing import checkCoolantExitState

        checkCoolantExitState(self.state(minCoolantExitPressure = 1.0e7))

    def testAMissedPressureLimitIsRefused(self):

        from NOVA.channelSizing import checkCoolantExitState
        from NOVA.errors import PressureDropError

        with pytest.raises(PressureDropError) as raised:
            checkCoolantExitState(self.state(coolantExitPressure = 2.211e6,
                                             minCoolantExitPressure = 8.0e6))

        assert raised.value.context['exitPressure'] == 2.211e6
        assert raised.value.context['minExitPressure'] == 8.0e6
        assert raised.value.context['pressureDrop'] == pytest.approx(9.789e6, rel = 1e-9)

    def testAMissedTemperatureLimitIsRefused(self):

        from NOVA.channelSizing import checkCoolantExitState
        from NOVA.errors import ThermalConstraintError

        with pytest.raises(ThermalConstraintError) as raised:
            checkCoolantExitState(self.state(minCoolantExitTemperature = 300.0))

        assert raised.value.context['value'] == 252.7
        assert raised.value.context['limit'] == 300.0

    def testThePressureLimitIsCheckedBeforeTheTemperature(self):

        from NOVA.channelSizing import checkCoolantExitState
        from NOVA.errors import PressureDropError

        # Both violated: the pressure is the one that makes the jacket unusable
        with pytest.raises(PressureDropError):
            checkCoolantExitState(self.state(coolantExitPressure = 1.0e6,
                                             minCoolantExitPressure = 8.0e6,
                                             minCoolantExitTemperature = 300.0))

    def testBothLimitsAreDeclaredOnBothStates(self):

        from NOVA.channelSizing import ChannelSizingState

        # Reached by name from the rule table and from _sizingState, so a missing declaration
        # surfaces only when a run gets there
        for name in ('minCoolantExitPressure', 'minCoolantExitTemperature'):
            assert name in ChannelSizingState.__dataclass_fields__
            assert name in RegenChannelState.__dataclass_fields__

class TestCoolantPastWallLimit:

    '''

    The other way a jacket fails the wall temperature limit.

    The wall sits between the exhaust and the coolant, so it is hotter than the coolant behind
    it. Coolant that has reached the wall's limit puts the wall over it whatever the channel
    size is, and nothing downstream can be cooled either. Carried on unchecked, the station
    solve balances with heat running from the coolant into the wall and the coolant cools,
    station after station, off the end of every property range.

    '''

    def testItNamesTheStationAndBothTemperatures(self):

        from NOVA.channelSizing import coolantPastWallLimit
        from NOVA.errors import ThermalConstraintError

        failure = coolantPastWallLimit(stationIndex = 24, coolantTemperature = 214.8,
                                       limit = 200.0)

        assert isinstance(failure, ThermalConstraintError)
        assert failure.context['value'] == 214.8
        assert failure.context['limit'] == 200.0
        assert failure.context['stationIndex'] == 24
        assert 'station 24' in str(failure)

    def testItSaysWhyNoChannelSizeCanFixIt(self):

        from NOVA.channelSizing import coolantPastWallLimit

        message = str(coolantPastWallLimit(0, 214.8, 200.0))

        assert 'no channel size' in message
        assert 'downstream' in message
