'''

Tests for the section geometry of a bifurcated channel in channelSplit.py.

Author: Sean Bowman

'''

import numpy as np
import pytest

from NOVA.channelSplit import (circleUnion, circleUnionOutline, daughterCenterlines, splitBlend,
                               splitPitchShare,
                               splitSeparation)
from NOVA.errors import InvalidInputError

def shoelace(loop: np.ndarray) -> float:

    x, y = loop[:, 0], loop[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

def outlineLength(loop: np.ndarray) -> float:

    return float(np.sum(np.hypot(*(np.roll(loop, -1, axis = 0) - loop).T)))

class TestTheUnionOfTwoCircles:

    def testCoincidentCirclesAreOneCircle(self):

        union = circleUnion(0.002, 0.0)
        assert union['flowArea'] == pytest.approx(np.pi * 0.002**2, rel = 1e-14)
        assert union['wettedPerimeter'] == pytest.approx(2.0 * np.pi * 0.002, rel = 1e-14)
        assert union['hydraulicDiameter'] == pytest.approx(0.004, rel = 1e-14)
        assert union['heatedPerimeter'] == pytest.approx(np.pi * 0.002, rel = 1e-14)

    @pytest.mark.parametrize('separation', [0.004, 0.006])
    def testTouchingOrApartCirclesAreTwoCircles(self, separation):

        union = circleUnion(0.002, separation)
        assert union['flowArea'] == pytest.approx(2.0 * np.pi * 0.002**2, rel = 1e-14)
        assert union['wettedPerimeter'] == pytest.approx(4.0 * np.pi * 0.002, rel = 1e-14)

    def testThePairCarriesTheParentsMassFluxAndDiameterWhenItSeparates(self):

        # One parent's flow through two touching circles is the mass flux of half that flow
        # through one, and the hydraulic diameter of one
        union = circleUnion(0.002, 0.004)
        assert 1.0 / union['flowArea'] == pytest.approx(0.5 / (np.pi * 0.002**2), rel = 1e-14)
        assert union['hydraulicDiameter'] == pytest.approx(0.004, rel = 1e-14)

    @pytest.mark.parametrize('separation', [0.0005, 0.0015, 0.0031, 0.0039])
    def testTheClosedFormIsTheOutlinePolygon(self, separation):

        loop = circleUnionOutline(0.002, separation, 20000)[0]
        union = circleUnion(0.002, separation)
        assert shoelace(loop) == pytest.approx(float(union['flowArea']), rel = 1e-6)
        assert outlineLength(loop) == pytest.approx(float(union['wettedPerimeter']), rel = 1e-6)

    def testTheAreaGrowsAsTheyPartAndTheDiameterSwellsMidSplit(self):

        # Mid-split the waisted section gains area faster than perimeter, so its hydraulic
        # diameter swells above one circle's while its mass flux falls: the larger-area passage
        # whose dip in heat transfer Wadel's bifurcations show. It returns to one circle's when
        # the two touch.
        separations = np.linspace(0.0, 0.004, 41)
        union = circleUnion(0.002, separations)
        assert np.all(np.diff(union['flowArea']) > 0.0)
        assert union['hydraulicDiameter'][20] == pytest.approx(0.00483, abs = 1e-5)
        assert union['hydraulicDiameter'][-1] == pytest.approx(0.004, rel = 1e-14)

class TestTheTransition:

    def testTheBlendRunsFromZeroToOneSmoothly(self):

        position = np.linspace(0.0, 0.1, 101)
        blend = splitBlend(position, 0.02, 0.05)
        assert np.all(blend[position <= 0.02] == 0.0)
        assert np.all(blend[position >= 0.07] == 1.0)
        assert np.all(np.diff(blend) >= 0.0)
        assert blend[np.argmin(np.abs(position - 0.045))] == pytest.approx(0.5, abs = 1e-12)

    def testAZeroLengthSplitIsRefused(self):

        with pytest.raises(InvalidInputError):
            splitBlend([0.0, 1.0], 0.5, 0.0)

    def testTheDaughtersStartOnTheParentAndEndHalfAPitchApart(self):

        count = 60
        x = np.linspace(0.0, 0.3, 31)
        radius = 0.1 + 0.2 * x
        angle = 0.3 * x                                   # a parent that leans as it runs
        y, z = radius * np.cos(angle), radius * np.sin(angle)
        blend = splitBlend(x, 0.1, 0.1)
        (xa, ya, za), (xb, yb, zb) = daughterCenterlines(x, y, z, blend, count)

        start, end = np.flatnonzero(blend == 0.0), np.flatnonzero(blend == 1.0)
        assert np.allclose(ya[start], y[start]) and np.allclose(zb[start], z[start])
        apart = np.arctan2(za, ya) - np.arctan2(zb, yb)
        assert apart[end] == pytest.approx(np.full(len(end), np.pi / count), rel = 1e-12)
        assert np.hypot(ya, za) == pytest.approx(radius, rel = 1e-14)

    def testThePitchShareRunsFromTheParentToTheDaughter(self):

        radius, count = 0.2, 60
        parent = 2.0 * np.pi * radius / count
        start = splitPitchShare(radius, count, splitSeparation(0.0, radius, count))
        end = splitPitchShare(radius, count, splitSeparation(1.0, radius, count))
        assert start == pytest.approx(parent, rel = 1e-14)
        assert end == pytest.approx(0.5 * parent, rel = 1e-14)

# -- The split through a solved jacket -- #

SPLIT = dict(regenTruncationType = 'er', regenTruncationValue = 10.0, makeRadiativeExtension = False,
             numCrossSections = 60, channelSplitAreaRatio = 3.0, channelSplitLength = 6.0,
             makeInletVolute = True, makeOutletVolute = True, filmCooling = False)

@pytest.fixture(scope = 'module')
def splitJacket(tmp_path_factory):

    from testDefectGuards import runConfiguration

    return runConfiguration(tmp_path_factory.mktemp('channelSplit'), **SPLIT)

class TestASolvedSplit:

    def testTheJacketRunsFromOneChannelToTwo(self, splitJacket):

        blend = np.asarray(splitJacket.channelSplitBlend)
        assert blend[0] == 0.0 and blend[-1] == 1.0
        assert np.all(np.diff(blend) >= 0.0)
        assert np.count_nonzero((blend > 0.0) & (blend < 1.0)) >= 3

    def testTheCoolantWarmsSmoothlyThroughTheSplit(self, splitJacket):

        # The march carries one parent's flow straight through, so the enthalpy it gathers has no
        # jump at the transition: no station's rise is out of line with its neighbors'
        temperature = np.asarray(splitJacket.channelThermalResults['temperature'])
        rise = np.abs(np.diff(temperature))
        assert np.all(rise < 4.0 * np.median(rise) + 1.0)

    def testADaughterFitsItsOwnPitchPastTheSplit(self, splitJacket):

        blend = np.asarray(splitJacket.channelSplitBlend)
        past = blend >= 1.0
        pitch = np.pi * np.asarray(splitJacket.rChannelCenterline2D) / splitJacket.nChannel
        assert np.all(2.0 * np.asarray(splitJacket.channelRadius)[past]
                      <= pitch[past] - splitJacket.infillThickness + 1e-9)

    def testTheDaughtersEndHalfAParentPitchApart(self, splitJacket):

        angleA = np.arctan2(splitJacket.zChannelSplitA, splitJacket.yChannelSplitA).mean(axis = 0)
        angleB = np.arctan2(splitJacket.zChannelSplitB, splitJacket.yChannelSplitB).mean(axis = 0)
        apart = np.angle(np.exp(1j * (angleA - angleB)))
        assert abs(apart[-1]) == pytest.approx(np.pi / splitJacket.nChannel, rel = 0.02)
        assert splitJacket.xChannel.shape[1] + splitJacket.xChannelSplitA.shape[1] == splitJacket.numCrossSections + 1

    def testTheAftVoluteGathersTheDaughters(self, splitJacket):

        # Counterflow: the inlet scroll at the aft end feeds twice the parent count
        assert splitJacket.inletVolute is not None and splitJacket.outletVolute is not None

class TestTheSplitRefusals:

    def testASplitOnRectangularChannelsIsRefused(self, tmp_path):

        from testDefectGuards import runConfiguration

        with pytest.raises(InvalidInputError, match = 'circular channels'):
            runConfiguration(tmp_path, **{**SPLIT, 'channelType': 'rectangular', 'nChannel': 160,
                                          'makeInletVolute': False, 'makeOutletVolute': False})

    def testASplitPastTheJacketIsRefused(self, tmp_path):

        from testDefectGuards import runConfiguration

        with pytest.raises(InvalidInputError, match = 'past the'):
            runConfiguration(tmp_path, **{**SPLIT, 'channelSplitAreaRatio': 20.0,
                                          'makeInletVolute': False, 'makeOutletVolute': False})
