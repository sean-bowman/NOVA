'''

Tests for the channel section properties in channelSections.py.

Every quantity here has a closed form, and each is held to it.

**A circle is a circle.** Its flow area is pi r^2, its hydraulic diameter 2r, and the perimeter
the heat enters through is the half that faces the wall, pi r. It has no fin.

**A rectangle is a rounded rectangle.** Its flow area is w d - (4 - pi) r_c^2 and its perimeter
2(w + d) - (8 - 2 pi) r_c, exact for a sharp corner and a stadium when r_c is half the width. Its
hydraulic diameter is the side of a square and tends to twice the width of a thin slot. Its
floor, sides and roof tile the perimeter, and its width leaves exactly the rib at the cold wall.

**A helix is a loxodrome.** Its wrap is s tan(phi) / r on a cylinder and tan(phi) / sin(a) ln(r / r0)
on a cone, it holds still where it is switched off, its passes sit 2 pi r cos(phi) / N apart, and
its rib is what the spacing leaves the width.

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
                                  finEfficiency, helicalSpacing, loxodromeWrap, maxHalfExtent,
                                  rectangularWidth, sectionProperties, throatChannelCount)

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

class TestRectangle:

    '''The rounded rectangle in closed form, and the width that fills its pitch.'''

    width, depth = 1.2e-3, 4.8e-3

    def section(self, corner = 0.0, width = None, depth = None):

        width = self.width if width is None else width
        depth = self.depth if depth is None else depth

        return sectionProperties('rectangular', np.array([depth / 2]), width = np.array([width]),
                                 cornerRadius = corner, ribThickness = 1.0e-3)

    def testASharpRectangleIsExact(self):

        section = self.section()

        assert section.flowArea[0] == pytest.approx(self.width * self.depth, rel = 1e-15)
        assert section.wettedPerimeter[0] == pytest.approx(2 * (self.width + self.depth), rel = 1e-15)

    @pytest.mark.parametrize('corner', [0.1e-3, 0.3e-3, 0.6e-3])
    def testRoundedCornersRemoveTheirSquares(self, corner):

        section = self.section(corner)

        assert section.flowArea[0] == pytest.approx(
            self.width * self.depth - (4 - np.pi) * corner**2, rel = 1e-15)
        assert section.wettedPerimeter[0] == pytest.approx(
            2 * (self.width + self.depth) - (8 - 2 * np.pi) * corner, rel = 1e-15)

    def testAFullyRoundedEndIsAStadium(self):

        # A corner radius of half the width, or anything larger, clamps to it: a stadium of two
        # semicircles of diameter w closing a rectangle of w by d - w
        for corner in (self.width / 2, self.width):
            section = self.section(corner)
            straight = self.depth - self.width
            assert section.flowArea[0] == pytest.approx(straight * self.width + np.pi * self.width**2 / 4, rel = 1e-14)
            assert section.wettedPerimeter[0] == pytest.approx(2 * straight + np.pi * self.width, rel = 1e-14)

    def testASquareHasItsSideAsHydraulicDiameter(self):

        assert self.section(width = 2e-3, depth = 2e-3).hydraulicDiameter[0] == pytest.approx(2e-3, rel = 1e-15)

    def testAThinSlotTendsToTwiceItsWidth(self):

        # D_h = 2 w d / (w + d), so 2w / (1 + w/d)
        for ratio in (1e2, 1e4):
            section = self.section(width = 1e-3, depth = ratio * 1e-3)
            assert section.hydraulicDiameter[0] == pytest.approx(2e-3 / (1 + 1 / ratio), rel = 1e-14)

    def testTheFloorSidesAndRoofTileThePerimeter(self):

        for corner in (0.0, 0.2e-3, 0.6e-3):
            section = self.section(corner)
            assert 2 * section.heatedPerimeter[0] + 2 * section.finHeight[0] == \
                   pytest.approx(section.wettedPerimeter[0], rel = 1e-14)

    def testTheRibIsTheInfillAtTheColdWall(self):

        radius, count, rib = 0.0513, 160, 1.0e-3
        width = rectangularWidth(radius, count, rib)

        assert 2 * np.pi * radius / count - width == pytest.approx(rib, rel = 1e-12)

    def testTheDepthLimitIsTheSmallerOfItsTwo(self):

        width = np.array([1e-3, 2e-3, 4e-3])

        assert np.allclose(maxHalfExtent('rectangular', width, 8.0), 4 * width)
        assert np.allclose(maxHalfExtent('rectangular', width, 8.0, 10e-3), [4e-3, 5e-3, 5e-3])

    def testTheEquivalentPortCarriesTheFlowArea(self):

        diameter = equivalentDiameter('rectangular', self.depth / 2, width = self.width, cornerRadius = 0.2e-3)

        assert np.pi * diameter**2 / 4 == pytest.approx(self.section(0.2e-3).flowArea[0], rel = 1e-14)

    @pytest.mark.parametrize('throatRadius', [0.02, 0.05, 0.12])
    def testTheThroatCountIsTheMostThatHoldTheMinimumWidth(self, throatRadius):

        count = throatChannelCount('rectangular', throatRadius, 1.0e-3, 1.0e-3, 1.0e-3)
        coldWall = throatRadius + 1.0e-3

        assert rectangularWidth(coldWall, count, 1.0e-3) >= 1.0e-3
        assert rectangularWidth(coldWall, count + 1, 1.0e-3) < 1.0e-3

class TestHelix:

    '''The loxodrome, the pass spacing and the rib in closed form.'''

    def testTheWrapOnACylinderIsLinear(self):

        # r fixed, so d(theta)/ds is the constant tan(phi) / r
        length = np.linspace(0.0, 0.3, 50)
        wrap = loxodromeWrap(length, np.full(50, 0.06), 30.0)

        assert np.allclose(wrap, length * np.tan(np.deg2rad(30.0)) / 0.06, rtol = 1e-14, atol = 0)

    @pytest.mark.parametrize('helixAngle', [15.0, 45.0, 70.0])
    def testTheWrapOnAConeIsLogarithmicInRadius(self, helixAngle):

        # r = r0 + s sin(a), so theta = tan(phi) / sin(a) ln(r / r0)
        halfAngle, start = np.deg2rad(20.0), 0.05
        length = np.linspace(0.0, 0.2, 2001)
        radius = start + length * np.sin(halfAngle)

        wrap = loxodromeWrap(length, radius, helixAngle)
        exact = np.tan(np.deg2rad(helixAngle)) / np.sin(halfAngle) * np.log(radius / start)

        assert np.allclose(wrap[1:], exact[1:], rtol = 1e-6, atol = 0)

    def testAnInactiveStretchHoldsTheAngle(self):

        length = np.linspace(0.0, 0.3, 31)
        active = np.ones(31, dtype = bool)
        active[:5] = active[-5:] = False
        wrap = loxodromeWrap(length, np.full(31, 0.06), 45.0, active = active)

        assert np.all(wrap[:5] == 0.0)
        assert np.all(np.diff(wrap[-5:]) == 0.0)
        assert np.all(np.diff(wrap[5:26]) > 0.0)

    def testThePassSpacingNarrowsWithTheAngle(self):

        radius, count = 0.0513, 40
        for helixAngle in (0.0, 30.0, 60.0):
            assert helicalSpacing(radius, count, helixAngle) == pytest.approx(
                2 * np.pi * radius * np.cos(np.deg2rad(helixAngle)) / count, rel = 1e-14)

    def testTheRibIsWhatTheSpacingLeaves(self):

        spacing = helicalSpacing(np.array([0.0513, 0.091]), 40, 45.0)
        width   = np.array([4.0e-3, 5.0e-3])
        section = sectionProperties('helical', width / 2, width = width, ribThickness = spacing - width)

        assert np.allclose(section.finThickness, spacing - width, rtol = 1e-14)
        assert np.allclose(section.depth, width, rtol = 1e-14)

    def testTheLargestHelixLeavesTheMinimumRib(self):

        spacing = helicalSpacing(0.0513, 40, 45.0)
        largest = maxHalfExtent('helical', spacing - 1.0e-3, 1.5)

        assert largest == pytest.approx(1.5 * (spacing - 1.0e-3) / 2, rel = 1e-14)

    @pytest.mark.parametrize('helixAngle', [0.0, 45.0, 70.0])
    def testTheThroatStartsAreTheMostThatHoldTheMinimumWidth(self, helixAngle):

        count = throatChannelCount('helical', 0.0503, 1.0e-3, 1.0e-3, 1.0e-3, helixAngle = helixAngle)
        coldWall = 0.0503 + 1.0e-3

        assert helicalSpacing(coldWall, count, helixAngle) - 1.0e-3 >= 1.0e-3
        assert helicalSpacing(coldWall, count + 1, helixAngle) - 1.0e-3 < 1.0e-3

class TestDepthLimit:

    '''The one size bound every family shares.'''

    def testNoLimitIsNoLimit(self):

        from NOVA.channelSections import depthLimitedHalfExtent

        assert depthLimitedHalfExtent(None) == float('inf')
        assert depthLimitedHalfExtent(float('nan')) == float('inf')
        assert depthLimitedHalfExtent(float('inf')) == float('inf')

    def testItIsHalfTheDepth(self):

        from NOVA.channelSections import depthLimitedHalfExtent

        # A section's depth is twice its half-extent in every family, so a circle's depth is its
        # diameter and a 6 mm limit is a 3 mm radius
        assert depthLimitedHalfExtent(6.0e-3) == 3.0e-3

    def testItAgreesWithTheRectangularLimitWhereTheDepthBinds(self):

        from NOVA.channelSections import depthLimitedHalfExtent, maxHalfExtent

        # A wide rectangle whose aspect ratio allows more depth than the limit does
        width = np.array([4.0e-3])
        byDepth = maxHalfExtent('rectangular', width, maxAspectRatio = 8.0, maxDepth = 6.0e-3)

        assert np.allclose(byDepth, depthLimitedHalfExtent(6.0e-3), rtol = 1e-15)
