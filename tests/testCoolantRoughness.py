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

    def testItReducesToSmoothWhenTheWallIsHydraulicallySmooth(self):

        # A roughness Reynolds number under about 5 leaves the sublayer intact
        fine = 1.0e-8
        friction = swameeJainFriction(reynolds, fine/diameter)
        nusselt = dippreySaberskyNusselt(friction, reynolds, prandtl, fine/diameter)
        smooth = gnielinskiNusselt(swameeJainFriction(reynolds, 0.0), reynolds, prandtl)

        assert float(nusselt) == pytest.approx(smooth, rel = 1e-9)

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
