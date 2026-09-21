'''

Tests for the input validation engine in validation.py.

A rule table is only worth having if the checker behind it is right, and the checker is small
enough to test exhaustively. That is the point of moving the rules into data: 124 hand-written
branches could only be tested by exercising each branch, whereas one checker can be tested
against every kind of rule and every way a value can be wrong.

Three things get particular attention here, because each was a defect in the validators this
replaced:

  - **Unset means three things.** Absent, None, and the NaN that setInputs produces from a null
    configuration entry. A guard that only tested one of them checked almost nothing.
  - **Zero is a value.** An offset of zero is specified; treating it as absent would reject a
    legitimate configuration.
  - **A string cannot be NaN-tested.** The naive implementation of 'is this unset' raises on a
    coolant name.

Author: Sean Bowman

'''

import os
import sys

import numpy as np
import pytest

from NOVA.validation import (Rule, applyRules, arrayRule, choiceRule, fieldsCovered, integerRule,
                        numericRule, presentRule, read, specified, textRule)

class Configuration:

    '''A stand-in for whatever object a rule table is pointed at.'''

    def __init__(self, **fields):
        for name, value in fields.items():
            setattr(self, name, value)

class TestRead:

    '''A rule table has to work against an object or a dictionary.'''

    def testReadsAnObject(self):

        assert read(Configuration(chamberPressure = 6.9e6), 'chamberPressure') == 6.9e6

    def testReadsAMapping(self):

        assert read({'chamberPressure': 6.9e6}, 'chamberPressure') == 6.9e6

    def testAbsentGivesTheFallback(self):

        assert read(Configuration(), 'missing', 'fallback') == 'fallback'
        assert read({}, 'missing', 'fallback') == 'fallback'

class TestSpecified:

    '''Three ways a configuration says nothing, and they all mean the same thing.'''

    def testAbsentIsUnset(self):

        assert not specified(Configuration(), 'chamberPressure')
        assert not specified({}, 'chamberPressure')

    def testNoneIsUnset(self):

        assert not specified(Configuration(chamberPressure = None), 'chamberPressure')

    def testNanIsUnset(self):

        assert not specified(Configuration(chamberPressure = np.nan), 'chamberPressure')

    def testZeroIsSet(self):

        # An offset of zero is a specified offset, not a missing one.
        assert specified(Configuration(axialOffset = 0.0), 'axialOffset')
        assert specified(Configuration(axialOffset = 0), 'axialOffset')

    def testFalseIsSet(self):

        assert specified(Configuration(makeInletVolute = False), 'makeInletVolute')

    def testAStringIsSet(self):

        assert specified(Configuration(coolant = 'Hydrogen'), 'coolant')

    def testAnArrayIsSet(self):

        assert specified(Configuration(wall = np.array([1.0, 2.0])), 'wall')

    def testAnEmptyArrayIsSet(self):

        # Empty is a shape problem for the array rule to report, not an absence.
        assert specified(Configuration(wall = np.array([])), 'wall')

class TestRequired:

    '''Required means required, and optional means the value checks are skipped.'''

    def testAMissingRequiredFieldIsRejected(self):

        rules = [numericRule('chamberPressure', 'Chamber pressure', units = 'Pa', minimum = 0)]

        with pytest.raises(Exception, match = 'Chamber pressure'):
            applyRules(Configuration(), rules)

    def testAMissingOptionalFieldPasses(self):

        rules = [numericRule('lengthFraction', 'Length fraction', required = False,
                             minimum = 0, maximum = 1)]

        applyRules(Configuration(), rules)
        applyRules(Configuration(lengthFraction = np.nan), rules)

    def testAnOptionalFieldIsStillCheckedWhenPresent(self):

        rules = [numericRule('lengthFraction', 'Length fraction', required = False,
                             minimum = 0, maximum = 1)]

        with pytest.raises(Exception, match = 'Length fraction'):
            applyRules(Configuration(lengthFraction = 1.5), rules)

class TestNumeric:

    '''Bounds, inclusive and exclusive.'''

    def testExclusiveLowerBound(self):

        rules = [numericRule('shellThickness', 'Shell thickness', units = 'm', minimum = 0)]

        applyRules(Configuration(shellThickness = 1e-9), rules)
        with pytest.raises(Exception, match = 'greater than 0'):
            applyRules(Configuration(shellThickness = 0.0), rules)

    def testInclusiveLowerBound(self):

        rules = [numericRule('hotWallThickness', 'Hot wall thickness', units = 'm',
                             minimum = 0.5e-3, exclusiveMinimum = False)]

        applyRules(Configuration(hotWallThickness = 0.5e-3), rules)
        with pytest.raises(Exception, match = 'at least'):
            applyRules(Configuration(hotWallThickness = 0.4e-3), rules)

    def testATwoSidedRange(self):

        rules = [numericRule('throatEccentricity', 'Throat eccentricity', minimum = 0, maximum = 1)]

        applyRules(Configuration(throatEccentricity = 0.5), rules)
        for bad in (0.0, 1.0, -0.1, 1.1):
            with pytest.raises(Exception, match = 'Throat eccentricity'):
                applyRules(Configuration(throatEccentricity = bad), rules)

    def testANonNumberIsRejected(self):

        rules = [numericRule('chamberPressure', 'Chamber pressure', minimum = 0)]

        with pytest.raises(Exception, match = 'must be a number'):
            applyRules(Configuration(chamberPressure = 'lots'), rules)

    def testABooleanIsNotANumber(self):

        # True would otherwise pass as 1, which is never what a pressure means.
        rules = [numericRule('chamberPressure', 'Chamber pressure', minimum = 0)]

        with pytest.raises(Exception, match = 'must be a number'):
            applyRules(Configuration(chamberPressure = True), rules)

    def testInfinityIsRejected(self):

        rules = [numericRule('chamberPressure', 'Chamber pressure', minimum = 0)]

        with pytest.raises(Exception, match = 'finite'):
            applyRules(Configuration(chamberPressure = np.inf), rules)

class TestInteger:

    '''A count is a count.'''

    def testAWholeNumberPasses(self):

        rules = [integerRule('nChannel', 'Number of channels', minimum = 10,
                             exclusiveMinimum = False)]

        applyRules(Configuration(nChannel = 10), rules)
        applyRules(Configuration(nChannel = np.int64(60)), rules)

    def testAFloatIsRejected(self):

        rules = [integerRule('nChannel', 'Number of channels', minimum = 10,
                             exclusiveMinimum = False)]

        with pytest.raises(Exception, match = 'whole number'):
            applyRules(Configuration(nChannel = 60.5), rules)

    def testBelowTheMinimumIsRejected(self):

        rules = [integerRule('nChannel', 'Number of channels', minimum = 10,
                             exclusiveMinimum = False)]

        with pytest.raises(Exception, match = 'at least 10'):
            applyRules(Configuration(nChannel = 4), rules)

class TestChoice:

    '''One of a fixed set.'''

    def testAPermittedValuePasses(self):

        rules = [choiceRule('contourType', 'Converging section type', choices = ('trad', 'sunk'))]

        applyRules(Configuration(contourType = 'trad'), rules)
        applyRules(Configuration(contourType = 'sunk'), rules)

    def testAnythingElseIsRejected(self):

        rules = [choiceRule('contourType', 'Converging section type', choices = ('trad', 'sunk'))]

        # The capital-S spelling that made a whole validation section unreachable.
        with pytest.raises(Exception, match = 'Converging section type'):
            applyRules(Configuration(contourType = 'Sunk'), rules)

    def testTheMessageListsWhatIsAllowed(self):

        rules = [choiceRule('contourType', 'Converging section type', choices = ('trad', 'sunk'))]

        with pytest.raises(Exception) as failure:
            applyRules(Configuration(contourType = 'newSunk'), rules)

        assert "'trad'" in str(failure.value) and "'sunk'" in str(failure.value)

class TestArray:

    '''Shape and contents.'''

    def testAGoodArrayPasses(self):

        rules = [arrayRule('rNozzleWall', 'Nozzle wall radius', units = 'm', positive = True)]

        applyRules(Configuration(rNozzleWall = np.linspace(0.05, 0.3, 40)), rules)

    def testAnEmptyArrayIsRejected(self):

        rules = [arrayRule('rNozzleWall', 'Nozzle wall radius')]

        with pytest.raises(Exception, match = 'at least 1'):
            applyRules(Configuration(rNozzleWall = np.array([])), rules)

    def testNonFiniteValuesAreRejected(self):

        rules = [arrayRule('rNozzleWall', 'Nozzle wall radius')]

        with pytest.raises(Exception, match = 'not finite'):
            applyRules(Configuration(rNozzleWall = np.array([1.0, np.nan, 3.0])), rules)

    def testNonPositiveValuesAreRejectedWhenAsked(self):

        rules = [arrayRule('rNozzleWall', 'Nozzle wall radius', positive = True)]

        with pytest.raises(Exception, match = 'greater than zero'):
            applyRules(Configuration(rNozzleWall = np.array([1.0, 0.0, 3.0])), rules)

    def testMismatchedLengthsAreRejected(self):

        rules = [arrayRule('rNozzleWall', 'Nozzle wall radius', sameLengthAs = 'xNozzleWall')]

        good = Configuration(xNozzleWall = np.zeros(40), rNozzleWall = np.ones(40))
        bad  = Configuration(xNozzleWall = np.zeros(40), rNozzleWall = np.ones(39))

        applyRules(good, rules)
        with pytest.raises(Exception, match = 'same length'):
            applyRules(bad, rules)

    def testAListIsAcceptedAsAnArray(self):

        rules = [arrayRule('rNozzleWall', 'Nozzle wall radius', positive = True)]

        applyRules(Configuration(rNozzleWall = [1.0, 2.0, 3.0]), rules)

    def testAMinimumLengthIsEnforced(self):

        rules = [arrayRule('rNozzleWall', 'Nozzle wall radius', minimumLength = 3)]

        with pytest.raises(Exception, match = 'at least 3'):
            applyRules(Configuration(rNozzleWall = np.array([1.0, 2.0])), rules)

class TestText:

    '''A name is a non-empty string.'''

    def testANamePasses(self):

        applyRules(Configuration(coolant = 'Hydrogen'), [textRule('coolant', 'Coolant')])

    @pytest.mark.parametrize('bad', ['', '   ', 42])
    def testAnEmptyOrNonStringIsRejected(self, bad):

        with pytest.raises(Exception, match = 'Coolant'):
            applyRules(Configuration(coolant = bad), [textRule('coolant', 'Coolant')])

class TestConditionalRules:

    '''A rule that only applies sometimes.'''

    def testItIsSkippedWhenThePredicateIsFalse(self):

        rules = [numericRule('throatEccentricity', 'Throat eccentricity', minimum = 0, maximum = 1,
                             when = lambda source: read(source, 'contourType') == 'sunk')]

        # A traditional contour carries no throat eccentricity, and must not be asked for one.
        applyRules(Configuration(contourType = 'trad'), rules)

    def testItAppliesWhenThePredicateIsTrue(self):

        rules = [numericRule('throatEccentricity', 'Throat eccentricity', minimum = 0, maximum = 1,
                             when = lambda source: read(source, 'contourType') == 'sunk')]

        with pytest.raises(Exception, match = 'Throat eccentricity'):
            applyRules(Configuration(contourType = 'sunk'), rules)

        applyRules(Configuration(contourType = 'sunk', throatEccentricity = 0.95), rules)

class TestDefaultSentinel:

    '''Some fields accept a request to work it out rather than a value.'''

    def testTheSentinelPasses(self):

        rules = [numericRule('convergingSectionAngle', 'Converging section angle', units = 'deg',
                             minimum = 0, maximum = 90, allowDefault = True)]

        applyRules(Configuration(convergingSectionAngle = 'default'), rules)

    def testAValueIsStillChecked(self):

        rules = [numericRule('convergingSectionAngle', 'Converging section angle', units = 'deg',
                             minimum = 0, maximum = 90, allowDefault = True)]

        applyRules(Configuration(convergingSectionAngle = 30.0), rules)
        with pytest.raises(Exception, match = 'Converging section angle'):
            applyRules(Configuration(convergingSectionAngle = 95.0), rules)

    def testAnyOtherStringIsRejected(self):

        rules = [numericRule('convergingSectionAngle', 'Converging section angle',
                             minimum = 0, maximum = 90, allowDefault = True)]

        with pytest.raises(Exception, match = 'must be a number'):
            applyRules(Configuration(convergingSectionAngle = 'automatic'), rules)

class TestOrdering:

    '''The first failure is the one reported.'''

    def testTheEarliestProblemIsNamed(self):

        rules = [numericRule('chamberPressure', 'Chamber pressure', units = 'Pa', minimum = 0),
                 integerRule('nChannel', 'Number of channels', minimum = 10,
                             exclusiveMinimum = False)]

        # Both are wrong; the message must name the first, so a table reads from the most basic
        # requirement to the most specific.
        with pytest.raises(Exception, match = 'Chamber pressure'):
            applyRules(Configuration(chamberPressure = -1.0, nChannel = 2), rules)

class TestRangeText:

    '''The range in the message is built from the rule rather than written twice.'''

    def testItDescribesBounds(self):

        assert numericRule('x', minimum = 0).rangeText() == 'Float > 0'
        assert numericRule('x', minimum = 0, units = 'Pa').rangeText() == 'Float > 0 [Pa]'
        assert numericRule('x', minimum = 0, exclusiveMinimum = False).rangeText() == 'Float >= 0'
        assert numericRule('x', minimum = 0, maximum = 90).rangeText() == 'Float in (0, 90)'
        assert integerRule('x', minimum = 3, exclusiveMinimum = False).rangeText() == 'Integer >= 3'

    def testItDescribesChoicesAndArrays(self):

        assert choiceRule('x', choices = ('a', 'b')).rangeText() == "One of 'a', 'b'"
        assert 'all finite' in arrayRule('x').rangeText()
        assert 'all greater than zero' in arrayRule('x', positive = True).rangeText()

    def testItMentionsTheDefaultSentinel(self):

        assert 'default' in numericRule('x', minimum = 0, allowDefault = True).rangeText()

class TestFieldsCovered:

    '''A table can be held against the state it guards.'''

    def testItListsTheFields(self):

        rules = [numericRule('chamberPressure'), integerRule('nChannel'), arrayRule('rNozzleWall')]

        assert fieldsCovered(rules) == {'chamberPressure', 'nChannel', 'rNozzleWall'}

class TestAgainstADictionary:

    '''The same table guards an object or the heat transfer input dictionary.'''

    def testADictionaryIsCheckedTheSameWay(self):

        rules = [numericRule('chamberPressure', 'Chamber pressure', units = 'Pa', minimum = 0),
                 arrayRule('nearWallTemperature', 'Near wall temperature', units = 'K',
                           positive = True)]

        applyRules({'chamberPressure': 6.9e6,
                    'nearWallTemperature': np.full(10, 2000.0)}, rules)

        with pytest.raises(Exception, match = 'Chamber pressure'):
            applyRules({'nearWallTemperature': np.full(10, 2000.0)}, rules)
