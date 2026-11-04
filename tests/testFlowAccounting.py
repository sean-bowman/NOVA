'''

Tests for the propellant flow accounting in flowAccounting.py.

The split is the mixture ratio's definition, and a jacket returned to the injector, or a film the
injector draws, cannot carry more of a propellant than the chamber burns.

Author: Sean Bowman

'''

import pytest

from NOVA.errors import InvalidInputError
from NOVA.flowAccounting import accountForFlows, propellantFlows

ENGINEFLOW = 23.466      # [kg/s]
MIXTURERATIO = 5.5       # [-]

def testTheSplitIsTheMixtureRatio():

    fuel, oxidizer = propellantFlows(ENGINEFLOW, MIXTURERATIO)

    assert fuel + oxidizer == pytest.approx(ENGINEFLOW, rel = 1e-15)
    assert oxidizer / fuel == pytest.approx(MIXTURERATIO, rel = 1e-14)

def testAGivenJacketFlowReportsItsBypass():

    account = accountForFlows(ENGINEFLOW, MIXTURERATIO, 'fuel', coolantMassFlow = 3.4)
    fuel = ENGINEFLOW / (1.0 + MIXTURERATIO)

    assert account.coolantMassFlow == 3.4
    assert account.coolantBypassFraction == pytest.approx(1.0 - 3.4 / fuel, rel = 1e-14)

def testAnUnsetJacketFlowIsThePropellantLessItsBypass():

    account = accountForFlows(ENGINEFLOW, MIXTURERATIO, 'fuel', coolantBypassFraction = 0.3)

    assert account.coolantMassFlow == pytest.approx(0.7 * ENGINEFLOW / (1.0 + MIXTURERATIO), rel = 1e-14)

def testAnUnsetJacketFlowWithNoBypassTakesTheWholeStream():

    account = accountForFlows(ENGINEFLOW, MIXTURERATIO, 'oxidizer')

    assert account.coolantMassFlow == pytest.approx(account.oxidizerMassFlow, rel = 1e-15)
    assert account.coolantBypassFraction == 0.0

def testAJacketDrawingMoreThanTheChamberBurnsIsRefused():

    with pytest.raises(InvalidInputError, match = 'carries no more than the injector takes'):
        accountForFlows(ENGINEFLOW, MIXTURERATIO, 'fuel', coolantMassFlow = 3.7)

def testAFilmDrawingMoreThanTheInjectorReceivesIsRefused():

    with pytest.raises(InvalidInputError, match = 'chamber film'):
        accountForFlows(ENGINEFLOW, MIXTURERATIO, 'fuel', coolantMassFlow = 3.4, filmMassFlow = 4.0)

def testTheShippedJacketAndFilmFit():

    account = accountForFlows(ENGINEFLOW, MIXTURERATIO, 'fuel', coolantMassFlow = 3.4,
                              filmMassFlow = 0.3)

    assert account.coolantMassFlow == 3.4

def testGivingBothTheFlowAndTheBypassIsRefused():

    with pytest.raises(InvalidInputError, match = 'say the same thing'):
        accountForFlows(ENGINEFLOW, MIXTURERATIO, 'fuel', coolantMassFlow = 3.0,
                        coolantBypassFraction = 0.2)

@pytest.mark.parametrize('bypass', [-0.1, 1.0])
def testABypassOutsideZeroToOneIsRefused(bypass):

    with pytest.raises(InvalidInputError):
        accountForFlows(ENGINEFLOW, MIXTURERATIO, 'fuel', coolantBypassFraction = bypass)

def testACoolantClassThatIsNotAStreamIsRefused():

    with pytest.raises(InvalidInputError):
        accountForFlows(ENGINEFLOW, MIXTURERATIO, 'water')
