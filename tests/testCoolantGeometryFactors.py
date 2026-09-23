'''

Tests for the entrance and curvature corrections on the coolant side.

Both come from NASA TN D-7207, where Schacht and Quentmeyer measured local coolant-side
coefficients in a liquid-hydrogen cooled LOX/GH2 thrust chamber and reported which corrections a
station correlation needs to match them. The entrance fit is Boelter, Young and Iversen's for a
90 degree entrance; the curvature factor is Ito's resistance ratio for turbulent flow in a curved
pipe, which the report found gives about the right magnitude through a throat.

The entrance factor is checked against the report's own tabulated column: Table III lists the
entrance coefficient used at each length-to-diameter ratio, so the implementation is held to the
numbers the source published rather than to a rearrangement of its formula.

Author: Sean Bowman

'''

import numpy as np
import pytest

from NOVA.regenThermal import entranceEnhancementFactor, itoCurvatureFactor

class TestEntranceFactor:

    '''

    The developing length after a channel inlet.

    Table III of TN D-7207 reports the entrance coefficient at four length-to-diameter ratios,
    rounded as published.

    '''

    @pytest.mark.parametrize('lengthToDiameter, published', [(7.5, 1.5), (25.0, 1.01),
                                                             (40.0, 1.0), (46.0, 1.0)])
    def testItMatchesThePublishedCoefficients(self, lengthToDiameter, published):

        factor = entranceEnhancementFactor(lengthToDiameter*0.003, 0.003)

        assert float(factor) == pytest.approx(published, abs = 0.005)

    def testItNeverFallsBelowOne(self):

        # Past S/d of about 33 the fit drops under 1, which would make a developed passage
        # transfer less than a developed passage
        ratios = np.array([1.0, 10.0, 33.0, 100.0, 1000.0])
        factors = entranceEnhancementFactor(ratios*0.002, 0.002)

        assert np.all(factors >= 1.0)
        assert factors[-1] == pytest.approx(1.0)

    def testItDecaysWithDistance(self):

        ratios = np.array([2.0, 5.0, 10.0, 20.0, 30.0])
        factors = entranceEnhancementFactor(ratios*0.002, 0.002)

        assert np.all(np.diff(factors) < 0)

    def testTheInletItselfIsFinite(self):

        # The fit is unbounded at S = 0, and a passage has no developing length before its inlet
        assert np.isfinite(entranceEnhancementFactor(0.0, 0.002))
        assert float(entranceEnhancementFactor(0.0, 0.002)) == pytest.approx(1.0)

class TestCurvatureFactor:

    '''Ito's resistance ratio, applied as a heat transfer enhancement through a bend.'''

    def testAStraightPassageIsUnchanged(self):

        assert float(itoCurvatureFactor(1.0e5, 0.0015, np.inf)) == pytest.approx(1.0)

    def testItMatchesItosForm(self):

        reynolds, sectionRadius, bendRadius = 2.0e5, 0.0016, 0.05
        expected = (reynolds*(sectionRadius/bendRadius)**2)**0.05

        assert float(itoCurvatureFactor(reynolds, sectionRadius, bendRadius)) \
               == pytest.approx(expected, rel = 1e-12)

    def testItIsOneBelowTheThreshold(self):

        # Ito's form holds for Re (R/r)^2 > 6, and below it the bend does nothing
        gentle = itoCurvatureFactor(1.0e4, 0.0005, 1.0)

        assert float(gentle) == pytest.approx(1.0)

    def testATighterBendEnhancesMore(self):

        # Above the threshold, where the bend is doing something at all
        radii = np.array([0.2, 0.1, 0.05, 0.02])
        factors = itoCurvatureFactor(2.0e5, 0.0016, radii)

        assert np.all(factors > 1.0)
        assert np.all(np.diff(factors) > 0)

    def testTheThroatMagnitudeIsWhatTheReportFound(self):

        # The report built its enhancement from station data and let it reach 1.52, which it
        # says is what Ito's equation predicts for that geometry. The throat passage there is
        # 0.318 by 0.267 cm on a 12.7 cm bore, and the run Reynolds numbers are of order 1e6.
        sectionRadius = 0.5*np.sqrt(0.00318*0.00267)
        factor = itoCurvatureFactor(3.0e6, sectionRadius, 0.0254)

        assert 1.3 < float(factor) < 1.7
