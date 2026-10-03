'''

Tests for the REFPROP failure guard in fluidProperties.py.

REFPROP does not raise when it cannot answer a call. It sets an error code beside a message, and
it writes a marker into the output slot it could not fill: -9999990 where no value was
calculated, -9999970 where the calculation failed, -9999950 where the value lives in another
field. The markers are numbers near minus ten million, so anything that reads the output without
checking carries one through the physics as a property. A 300 K wall temperature limit on the
shipped nozzle used to surface as a complaint about a coolant inlet temperature of -9999990 K,
thirty stations and two modules away from the call that failed.

**The code is checked and so is every slot.** A positive code raises with REFPROP's own message,
which already names the routine and the reason. A negative code is a warning and is left alone. A
marker raises even where the code is zero, which is how a property that does not apply at the
state asked for comes back.

**A phase request is the exception.** REFPROP has no numeric phase, so -9999950 in the output is
its normal answer there and the descriptor is read from the units field. The marker check is
skipped for a phase request; the error code is not.

The guard is tested against a stand-in result object so it runs on a machine with no REFPROP
license, and then against REFPROP itself where one is installed.

Author: Sean Bowman

'''

import os

import pytest

from NOVA.errors import REFPROPError
from NOVA.fluidProperties import REFPROPMARKERS, checkREFPROPResult

class Result:

    '''What REFPROPdll hands back, reduced to the three fields the guard reads.'''

    def __init__(self, output, ierr = 0, herr = ''):

        self.Output = list(output)
        self.ierr   = ierr
        self.herr   = herr

def check(result, outputTypes = 'D VIS'):

    '''Run the guard on one stand-in result.'''

    return checkREFPROPResult(result, 'Hydrogen', 'TP', outputTypes, 100.0, 1.2e7)

class TestTheGuard:

    '''What passes and what is refused.'''

    def testAGoodResultPasses(self):

        check(Result([26.87, 5.41e-6]))

    def testTrailingSlotsAreNotChecked(self):

        # REFPROP fills a fixed length output array, so the slots past the ones asked for hold
        # whatever was left there and are none of the guard's business
        check(Result([26.87, 5.41e-6] + [-9999990.0]*18))

    def testAPositiveCodeIsRefusedWithREFPROPsOwnMessage(self):

        result = Result([-9999990.0, -9999990.0], ierr = 143,
                        herr = '[TPFLSH error 143] Input value equal to or less than zero.')

        with pytest.raises(REFPROPError) as raised:
            check(result)

        assert raised.value.context['errorCode'] == 143
        assert 'TPFLSH error 143' in str(raised.value)
        assert raised.value.context['species'] == 'Hydrogen'
        assert raised.value.context['requested'] == 'D VIS'

    def testTheMessageDoesNotEndInTwoPeriods(self):

        result = Result([-9999990.0], ierr = 143, herr = 'Input value equal to or less than zero.')

        with pytest.raises(REFPROPError) as raised:
            check(result, outputTypes = 'D')

        assert '..' not in str(raised.value)

    def testACodeWithNoMessageStillSaysSomething(self):

        with pytest.raises(REFPROPError, match = 'no message given'):
            check(Result([-9999990.0], ierr = 99, herr = ''))

    def testANegativeCodeIsAWarningAndPasses(self):

        # REFPROP signs its codes: positive is an error, negative is a warning
        check(Result([26.87, 5.41e-6], ierr = -102, herr = 'Warning: near the critical point'))

    @pytest.mark.parametrize('marker', sorted(REFPROPMARKERS))
    def testEveryMarkerIsRefusedEvenWithoutACode(self, marker):

        with pytest.raises(REFPROPError) as raised:
            check(Result([26.87, marker]))

        # Named by the property that came back empty, not by the slot number
        assert 'VIS' in str(raised.value)
        assert raised.value.context['errorCode'] == 0

    def testTheMarkerIsNamedInThePropertyThatFailed(self):

        with pytest.raises(REFPROPError, match = 'no value for D'):
            check(Result([-9999990.0, 5.41e-6]))

    def testAPhaseRequestKeepsItsMarker(self):

        # -9999950 in the output is REFPROP's normal answer for a phase, with the descriptor in
        # the units field, so refusing it would refuse every phase call
        check(Result([-9999950.0]), outputTypes = 'PHASE')

    def testAPhaseRequestStillAnswersToTheErrorCode(self):

        with pytest.raises(REFPROPError):
            check(Result([-9999950.0], ierr = 143, herr = 'bad state'), outputTypes = 'PHASE')

    def testTheMarkersAreTheThreeREFPROPDocuments(self):

        assert sorted(REFPROPMARKERS) == [-9999990.0, -9999970.0, -9999950.0]

class TestAgainstREFPROP:

    '''The same guard against the library, where the machine has one.'''

    installed = os.path.exists(os.path.join(os.path.expanduser('~'), 'REFPROP')) \
                or os.path.exists(os.path.join('C:\\', 'Program Files (x86)', 'REFPROP'))

    reason = 'no REFPROP installation on this machine'

    @pytest.mark.skipif(not installed, reason = reason)
    def testAGoodCallStillReturnsItsProperties(self):

        from NOVA.fluidProperties import refWrap

        density, viscosity = refWrap('Hydrogen', 'TP', 'D VIS', 100.0, 1.2e7)

        assert density > 0.0
        assert viscosity > 0.0

    @pytest.mark.skipif(not installed, reason = reason)
    def testAPhaseCallStillReturnsItsDescriptor(self):

        from NOVA.fluidProperties import refWrap

        assert isinstance(refWrap('Hydrogen', 'TP', 'PHASE', 100.0, 1.2e7), str)

    @pytest.mark.skipif(not installed, reason = reason)
    def testAStateREFPROPCannotEvaluateIsRefused(self):

        from NOVA.fluidProperties import refWrap

        # A negative temperature, which REFPROP answers with error 143 and two markers
        with pytest.raises(REFPROPError) as raised:
            refWrap('Hydrogen', 'TP', 'D VIS', -500.0, 1.2e7)

        assert raised.value.context['errorCode'] > 0
