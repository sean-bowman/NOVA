'''

Tests for the channel section properties in channelSections.py.

Every quantity here has a closed form, and each is held to it.

**A circle is a circle.** Its flow area is pi r^2, its hydraulic diameter 2r, and the perimeter
the heat enters through is the half that faces the wall, pi r. It has no fin.

**The throat channel count is the packing inverted.** The count it returns is the largest at
which the channel that fits at the throat is still no smaller than the process minimum, checked
against the packing formula in channelGeometry at that count and the next.

**The fin is a straight fin with an adiabatic tip.** Its efficiency tanh(mH)/(mH) goes to one as
the rib conducts perfectly or the coolant stops drawing heat, equals tanh(1) at mH = 1, and a rib
of no height leaves the station solve exactly as it is without one.

Author: Sean Bowman

'''

import numpy as np
import pytest

from NOVA.channelSections import (SECTIONFAMILIES, SECTIONLABELS, equivalentDiameter,
                                  finEfficiency, sectionProperties, throatChannelCount)

class TestCircle:

    '''The circular section in closed form.'''

    radius = np.array([0.5e-3, 1.0e-3, 2.5e-3])

    def testFlowAreaIsPiRSquared(self):

        section = sectionProperties('circle', self.radius)

        assert np.allclose(section.flowArea, np.pi * self.radius**2, rtol = 1e-15)

    def testHydraulicDiameterIsTheDiameter(self):

        section = sectionProperties('circle', self.radius)

        assert np.allclose(section.hydraulicDiameter, 2 * self.radius, rtol = 1e-15)
        assert np.allclose(4 * section.flowArea / section.wettedPerimeter, 2 * self.radius,
                           rtol = 1e-15)

    def testTheHeatedPerimeterIsTheHalfFacingTheWall(self):

        section = sectionProperties('circle', self.radius)

        assert np.allclose(section.heatedPerimeter, 0.5 * section.wettedPerimeter, rtol = 1e-15)

    def testThereIsNoFin(self):

        section = sectionProperties('circle', self.radius)

        assert np.all(section.finHeight == 0.0)
        assert np.all(section.finThickness == 0.0)

    def testTheEquivalentDiameterIsTheDiameter(self):

        assert np.array_equal(equivalentDiameter('circle', self.radius), self.radius * 2)

class TestFamilies:

    '''Only the families the package builds are accepted.'''

    def testEveryFamilyHasALabel(self):

        assert set(SECTIONFAMILIES) <= set(SECTIONLABELS)

    @pytest.mark.parametrize('family', ['fluted', 'hexagon'])
    def testAnUnknownFamilyIsRefused(self, family):

        with pytest.raises(ValueError, match = family):
            sectionProperties(family, np.array([1e-3]))

class TestFinEfficiency:

    '''tanh(mH) / (mH), m = sqrt(2 h / (k t)).'''

    def testAtMHOfOneItIsTanhOfOne(self):

        # Choose h so that mH = 1 exactly: m = 1 / H, h = k t m^2 / 2
        height, thickness, conductivity = 2.0e-3, 1.0e-3, 320.0
        coefficient = conductivity * thickness / height**2 / 2

        assert finEfficiency(coefficient, conductivity, thickness, height) == \
               pytest.approx(np.tanh(1.0), rel = 1e-14)

    @pytest.mark.parametrize('scale', [1e-2, 1e-4, 1e-6])
    def testAPerfectConductorOrAWeakCoolantGivesOne(self, scale):

        # eta = 1 - (mH)^2 / 3 + ..., so the departure from one goes as the square of mH
        height, thickness = 2.0e-3, 1.0e-3
        efficiency = finEfficiency(scale, 320.0, thickness, height)
        mH = np.sqrt(2 * scale / (320.0 * thickness)) * height

        assert 1 - efficiency == pytest.approx(mH**2 / 3, rel = 1e-3)

    def testItFallsAsTheFinGrows(self):

        heights = [0.5e-3, 1e-3, 2e-3, 4e-3, 8e-3]
        efficiencies = [finEfficiency(5.0e4, 320.0, 1.0e-3, height) for height in heights]

        assert all(later < earlier for earlier, later in zip(efficiencies, efficiencies[1:]))

    def testNoFinIsExactlyOne(self):

        assert finEfficiency(5.0e4, 320.0, 1.0e-3, 0.0) == 1.0

class TestFinInTheStationSolve:

    '''A rib of no height changes nothing; a rib with height adds area and cools the wall.'''

    def station(self, **overrides):

        from testRegenThermal import TestStationSolveIdentities

        return TestStationSolveIdentities().station(**overrides)

    def testNoHeightIsTheFinFreeSolveToTheBit(self):

        bare   = self.station()
        zeroed = self.station(finHeight = 0.0, finThickness = 1.0e-3)

        for field in bare.__dataclass_fields__:
            assert getattr(bare, field) == getattr(zeroed, field), field
        assert bare.finEfficiency == 1.0

    def testAFinCoolsTheWall(self):

        bare   = self.station()
        finned = self.station(finHeight = 2.0e-3, finThickness = 1.0e-3)

        assert 0.0 < finned.finEfficiency < 1.0
        assert finned.heatTransfer > bare.heatTransfer
        assert finned.hotWallTemperature < bare.hotWallTemperature
        assert finned.converged

class TestThroatChannelCount:

    '''The channel count is the largest whose throat section still fits the process minimum.'''

    @pytest.mark.parametrize('throatRadius', [0.02, 0.05, 0.12])
    @pytest.mark.parametrize('minimum', [0.5e-3, 0.75e-3, 1.5e-3])
    def testItIsTheLargestCountThatStillFits(self, throatRadius, minimum):

        from NOVA.channelGeometry import ChannelGeometryInputs, getMaxChannelRadius

        count = throatChannelCount('circle', throatRadius, 1.0e-3, 1.0e-3, minimum)

        def largestAt(nChannel):
            geometry = ChannelGeometryInputs(nChannel = nChannel, channelType = 'circle',
                                             hotWallThickness = 1.0e-3, infillThickness = 1.0e-3)
            return getMaxChannelRadius(geometry, np.array([throatRadius]), 0)

        assert largestAt(count) >= minimum * (1 - 1e-12)
        assert largestAt(count + 1) < minimum
