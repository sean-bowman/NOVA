'''

Tests for what a rough channel wall is allowed to do to the coolant-side heat transfer.

Roughness raises the friction factor, and the pressure drop with it, under every model here. What
differs is the heat transfer. `fullCredit` puts the rough-wall friction factor into Gnielinski's
smooth-tube form, so the Nusselt number rises in proportion to the friction; no measurement
supports that, and two comparisons against hardware say it runs the wall too cool.
`frictionOnly` takes the heat transfer on the smooth-wall friction factor, which is what NASA
TN D-7207 did. `dippreySabersky` takes the rough-wall heat transfer those authors measured, which
rises with roughness but by less than the friction does.

The three therefore bracket the answer, and these tests hold that ordering, the reduction of each
to the smooth-wall result, and the friction factor's independence from the choice.

Author: Sean Bowman

'''

import numpy as np
import pytest

from NOVA.regenThermal import (COOLANTROUGHNESSMODELS, coolantFrictionAndNusselt,
                               dippreySaberskyNusselt, gnielinskiNusselt, swameeJainFriction)

reynolds, prandtl, diameter = 1.0e6, 1.0, 0.003

class TestTheModelsBracket:

    '''Roughness buys nothing, something, or everything, in that order.'''

    def testTheOrderingHolds(self):

        nusselt = {model: coolantFrictionAndNusselt(reynolds, prandtl, diameter, 35e-6, model)[1]
                   for model in COOLANTROUGHNESSMODELS}

        assert nusselt['frictionOnly'] < nusselt['dippreySabersky'] < nusselt['fullCredit']

    @pytest.mark.parametrize('roughness', [5e-6, 20e-6, 35e-6, 100e-6])
    def testTheOrderingHoldsAtEveryRoughness(self, roughness):

        nusselt = {model: coolantFrictionAndNusselt(reynolds, prandtl, diameter, roughness, model)[1]
                   for model in COOLANTROUGHNESSMODELS}

        assert nusselt['frictionOnly'] <= nusselt['dippreySabersky'] <= nusselt['fullCredit']

    def testTheFrictionFactorDoesNotDependOnTheChoice(self):

        factors = [coolantFrictionAndNusselt(reynolds, prandtl, diameter, 35e-6, model)[0]
                   for model in COOLANTROUGHNESSMODELS]

        assert factors[0] == pytest.approx(factors[1], rel = 1e-12)
        assert factors[0] == pytest.approx(factors[2], rel = 1e-12)

    def testASmoothWallCollapsesTheChoice(self):

        nusselt = [coolantFrictionAndNusselt(reynolds, prandtl, diameter, 0.0, model)[1]
                   for model in COOLANTROUGHNESSMODELS]

        assert nusselt[0] == pytest.approx(nusselt[1], rel = 1e-9)
        assert nusselt[0] == pytest.approx(nusselt[2], rel = 1e-12)

class TestFrictionOnly:

    '''The heat transfer is the smooth-wall answer whatever the wall is.'''

    @pytest.mark.parametrize('roughness', [0.0, 35e-6, 200e-6])
    def testItIsTheSmoothWallNusselt(self, roughness):

        _, nusselt = coolantFrictionAndNusselt(reynolds, prandtl, diameter, roughness, 'frictionOnly')
        smooth = gnielinskiNusselt(swameeJainFriction(reynolds, 0.0), reynolds, prandtl)

        assert nusselt == pytest.approx(smooth, rel = 1e-12)

    def testTheFrictionFactorStillCarriesTheRoughness(self):

        rough, _  = coolantFrictionAndNusselt(reynolds, prandtl, diameter, 35e-6, 'frictionOnly')
        smooth, _ = coolantFrictionAndNusselt(reynolds, prandtl, diameter, 0.0, 'frictionOnly')

        assert rough > 3*smooth

class TestDippreySabersky:

    '''The measured rough-wall heat transfer, bounded below the friction it costs.'''

    def testASmoothWallIsGnielinskiExactly(self):

        friction = swameeJainFriction(reynolds, 0.0)
        nusselt = dippreySaberskyNusselt(friction, reynolds, prandtl, 0.0)

        assert float(nusselt) == gnielinskiNusselt(friction, reynolds, prandtl)

    def testItApproachesSmoothAsTheRoughnessVanishes(self):

        # At e+ 0.13 the bounds are 0.7 percent apart, which is Colebrook's own friction excess
        fine = 1.0e-8
        friction = swameeJainFriction(reynolds, fine/diameter)
        nusselt = dippreySaberskyNusselt(friction, reynolds, prandtl, fine/diameter)
        smooth = gnielinskiNusselt(swameeJainFriction(reynolds, 0.0), reynolds, prandtl)

        assert float(nusselt) == pytest.approx(smooth, rel = 0.01)

    @pytest.mark.parametrize('prandtlNumber', [0.7, 2.5, 25.0])
    def testItIsContinuousAcrossTheOnsetOfRoughness(self, prandtlNumber):

        # A roughness that puts e+ at 5 at Re 1e5, stepped 0.1 percent either side of it. The
        # expression alone reads 1.25 to 3.3 times the smooth wall there, which a switch to the
        # smooth form below e+ = 5 turns into a step of that size.
        reynoldsNumber = 1.0e5
        nusselt = []
        for roughness in (2.8496e-6 * 0.999, 2.8496e-6 * 1.001):
            friction = swameeJainFriction(reynoldsNumber, roughness/diameter)
            nusselt.append(float(dippreySaberskyNusselt(friction, reynoldsNumber, prandtlNumber,
                                                        roughness/diameter)))
        onset = 2.8496e-6/diameter * reynoldsNumber * np.sqrt(swameeJainFriction(reynoldsNumber, 2.8496e-6/diameter)/8)

        assert onset == pytest.approx(5.0, rel = 1e-4)
        assert nusselt[1] == pytest.approx(nusselt[0], rel = 2e-3)

    @pytest.mark.parametrize('prandtlNumber', [0.7, 2.5, 25.0])
    @pytest.mark.parametrize('roughness', [1e-7, 1e-6, 1e-5, 35e-6, 1e-4])
    def testItStaysBetweenTheSmoothWallAndFullCredit(self, prandtlNumber, roughness):

        reynoldsNumber = 1.0e5
        friction = swameeJainFriction(reynoldsNumber, roughness/diameter)
        nusselt = float(dippreySaberskyNusselt(friction, reynoldsNumber, prandtlNumber, roughness/diameter))
        smooth = gnielinskiNusselt(swameeJainFriction(reynoldsNumber, 0.0), reynoldsNumber, prandtlNumber)

        assert smooth <= nusselt <= gnielinskiNusselt(friction, reynoldsNumber, prandtlNumber)

    def testHydrogenOnAPrintedWallIsTheMeasuredExpression(self):

        # Pr 0.7 at e+ of several hundred is inside both bounds, so they change nothing
        friction = swameeJainFriction(reynolds, 35e-6/diameter)
        groupRoot = np.sqrt(friction/8)
        roughnessReynolds = 35e-6/diameter * reynolds * groupRoot
        expression = groupRoot**2 / (1 + groupRoot*(5.19*roughnessReynolds**0.2*0.7**0.44 - 8.48)) * reynolds * 0.7

        assert float(dippreySaberskyNusselt(friction, reynolds, 0.7, 35e-6/diameter)) == expression

    def testItBuysLessThanTheFrictionItCosts(self):

        friction, nusselt = coolantFrictionAndNusselt(reynolds, prandtl, diameter, 35e-6,
                                                      'dippreySabersky')
        smoothFriction = swameeJainFriction(reynolds, 0.0)
        smoothNusselt = gnielinskiNusselt(smoothFriction, reynolds, prandtl)

        assert nusselt/smoothNusselt < friction/smoothFriction

    def testItRisesWithRoughness(self):

        nusselt = [coolantFrictionAndNusselt(reynolds, prandtl, diameter, e, 'dippreySabersky')[1]
                   for e in (5e-6, 20e-6, 35e-6, 100e-6)]

        assert np.all(np.diff(nusselt) > 0)

class TestFullCredit:

    '''The legacy treatment, kept so a result recorded under it can be reproduced.'''

    def testItIsGnielinskiOnTheRoughFrictionFactor(self):

        friction, nusselt = coolantFrictionAndNusselt(reynolds, prandtl, diameter, 35e-6, 'fullCredit')

        assert nusselt == pytest.approx(gnielinskiNusselt(friction, reynolds, prandtl), rel = 1e-12)
