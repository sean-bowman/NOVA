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
        channelType               = 'circle',
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

    def testAFlutedChannelNeedsItsFluteDefinition(self):

        state = workingInputs()
        state.channelType = 'fluted'

        with pytest.raises(Exception, match = 'flute'):
            validateRegenChannelInputs(state)

    def testAFlutedChannelWithItsDefinitionPasses(self):

        state = workingInputs()
        state.channelType = 'fluted'
        state.fluteHelixAngle = 15.0
        state.numFlutes = 8

        validateRegenChannelInputs(state)

    @pytest.mark.parametrize('helixAngle', [-90.0, 90.0, 120.0])
    def testAnOutOfRangeHelixAngleIsRejected(self, helixAngle):

        state = workingInputs()
        state.channelType = 'fluted'
        state.fluteHelixAngle = helixAngle
        state.numFlutes = 8

        with pytest.raises(Exception, match = 'fluteHelixAngle'):
            validateRegenChannelInputs(state)

    def testTooFewFlutesIsRejected(self):

        state = workingInputs()
        state.channelType = 'fluted'
        state.fluteHelixAngle = 15.0
        state.numFlutes = 2

        with pytest.raises(Exception, match = 'numFlutes'):
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

    Which gas temperature the jacket is driven by, and the default being the physical one.

    Convection into a wall is driven by the adiabatic wall temperature, not by the static
    temperature. NOVA computes the recovery temperature in `chamber` and used to drop it before
    the solve, which understated the flux by the whole recovery rise: negligible in the chamber,
    a factor of 1.83 at the supersonic end of the shipped example's jacket.

    The static model is kept so the earlier answer stays reachable and recorded rather than only
    described. It is not a default anybody should choose.

    '''

    def state(self, **overrides):

        '''A sizing state carrying both arrays and whichever model the caller wants.'''

        from NOVA.channelSizing import ChannelSizingState

        arguments = dict(
            regenSectionNearWallTemperatureTrimmed = np.array([1000.0, 1500.0, 2000.0]),
            regenSectionNearWallRecoveryTemperatureTrimmed = np.array([1100.0, 1900.0, 3200.0]))
        arguments.update(overrides)

        return ChannelSizingState(**arguments)

    def testTheDefaultIsTheRecoveryTemperature(self):

        from NOVA.channelSizing import drivingTemperatureArray

        # Unset means the physical choice, not the historical one.
        chosen = drivingTemperatureArray(self.state())

        assert np.array_equal(chosen, np.array([1100.0, 1900.0, 3200.0]))

    def testTheRecoveryModelIsSelectableByName(self):

        from NOVA.channelSizing import drivingTemperatureArray

        chosen = drivingTemperatureArray(self.state(drivingTemperatureModel = 'recovery'))

        assert np.array_equal(chosen, np.array([1100.0, 1900.0, 3200.0]))

    def testTheStaticModelIsStillReachable(self):

        from NOVA.channelSizing import drivingTemperatureArray

        chosen = drivingTemperatureArray(self.state(drivingTemperatureModel = 'static'))

        assert np.array_equal(chosen, np.array([1000.0, 1500.0, 2000.0]))

    def testTheRecoveryTemperatureIsNeverBelowTheStaticOne(self):

        from NOVA.channelSizing import drivingTemperatureArray

        state = self.state()
        recovery = drivingTemperatureArray(state)
        static = drivingTemperatureArray(self.state(drivingTemperatureModel = 'static'))

        assert np.all(recovery >= static)

    def testAnUnknownModelIsRefused(self):

        from NOVA.channelSizing import drivingTemperatureArray
        from NOVA.utils import InvalidInputError

        with pytest.raises(InvalidInputError):
            drivingTemperatureArray(self.state(drivingTemperatureModel = 'stagnation'))

    def testAMissingRecoveryArraySaysSoRatherThanFallingBack(self):

        from NOVA.channelSizing import drivingTemperatureArray
        from NOVA.utils import InvalidInputError

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
