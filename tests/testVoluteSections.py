'''

Tests for the volute cross section properties in voluteSections.py.

Every quantity has a closed form and is held to it.

**A circle is a circle.** Area `pi r^2`, hydraulic diameter `2 r`, and the two invert.

**A squircle is a square of side `2 L` with quarter-round corners.** Area `(1 + 0.75 pi) L^2`,
perimeter `(2 + 1.5 pi) L`, so `4 A / P` is `2 L` and its hydraulic diameter matches a circle of
radius `L`. The characteristic length a hydraulic diameter implies is half of it.

**The area law is linear in wrap angle**, and its endpoints are the two areas it was given.

**The constant velocity law is Huzel and Huang eq. 6-69.** The area at wrap angle `theta` carries
`theta/360` of the throat flow, so the tongue area of a scroll feeding `N` ports is `A_throat/N`
and the velocity ratio from throat to tongue is one. A tongue larger than that decelerates the
flow toward the tongue in proportion.

**A ring serves half its ports on each run.** So its throat is half a cutwater's for the same
tongue, its area law is symmetric about the feed with the tongue half a turn away, and it sweeps a
full turn. A cutwater sweeps short of one by the angle its tongue wall occupies at the scroll
radius, floored at one section step.

**A specification that does not determine both ends is refused**, as is one that grows the wrong
way, and so is a family the module does not describe.

**Placement puts the tongue on the port.** The scroll radius and axial offset a port implies
are whatever puts the tongue section's centre back on that port, for every family and every
anchor, which is an exact round trip through the section centre offset.

**An anchor is an offset of the section half extent**, zero for the centre, one radius for the
four compass points and one radius over root two for the four diagonals, with an unrecognized
anchor centring the section.

Author: Sean Bowman

'''

import numpy as np
import pytest

from NOVA.voluteSections import (SCROLLTYPES, VOLUTESECTIONS, anchorOffset,
                                 characteristicLengthFromArea,
                                 characteristicLengthFromDiameter, checkFamily, checkScrollType,
                                 constantVelocityThroatArea, constantVelocityTongueArea,
                                 portsPerScroll, resolveScrollAreas, scrollAreaDistribution,
                                 scrollPlacement, scrollVelocityRatio, sectionArea,
                                 sectionCentreOffset, sectionHydraulicDiameter, tongueGapAngle)

radius = np.array([2.0e-3, 4.08e-3, 12.7e-3])

class TestCircle:

    def testAreaIsPiRSquared(self):

        assert np.allclose(sectionArea('circle', characteristicLength = radius),
                           np.pi*radius**2, rtol = 1e-15)

    def testHydraulicDiameterIsTheDiameter(self):

        area = np.pi*radius**2

        assert np.allclose(sectionHydraulicDiameter('circle', area), 2*radius, rtol = 1e-15)

    def testAreaFromHydraulicDiameterInverts(self):

        diameter = 2*radius
        area = sectionArea('circle', hydraulicDiameter = diameter)

        assert np.allclose(area, np.pi*radius**2, rtol = 1e-15)
        assert np.allclose(sectionHydraulicDiameter('circle', area), diameter, rtol = 1e-15)

    def testTheCharacteristicLengthIsTheRadius(self):

        assert np.allclose(characteristicLengthFromArea('circle', np.pi*radius**2), radius,
                           rtol = 1e-15)
        assert np.allclose(characteristicLengthFromDiameter('circle', 2*radius), radius,
                           rtol = 1e-15)

class TestSquircle:

    length = np.array([2.5e-3, 5.0e-3, 12.0e-3])
    areaFactor = 1 + 0.75*np.pi
    perimeterFactor = 2 + 1.5*np.pi

    def testAreaFollowsTheShapeFactor(self):

        assert np.allclose(sectionArea('squarc', characteristicLength = self.length),
                           self.areaFactor*self.length**2, rtol = 1e-15)

    def testHydraulicDiameterIsTwiceTheCharacteristicLength(self):

        area = self.areaFactor*self.length**2

        assert np.allclose(sectionHydraulicDiameter('squarc', area), 2*self.length, rtol = 1e-14)

    def testTheHydraulicDiameterIsFourAreaOverPerimeter(self):

        area = self.areaFactor*self.length**2
        perimeter = self.perimeterFactor*self.length

        assert np.allclose(sectionHydraulicDiameter('squarc', area), 4*area/perimeter,
                           rtol = 1e-14)

    def testACharacteristicLengthIsHalfTheHydraulicDiameter(self):

        diameter = 2*self.length

        assert np.allclose(characteristicLengthFromDiameter('squarc', diameter), self.length,
                           rtol = 1e-15)

    def testASquircleCarriesMoreAreaThanACircleOfTheSameHydraulicDiameter(self):

        diameter = 0.0254
        circle = sectionArea('circle', hydraulicDiameter = diameter)
        squircle = sectionArea('squarc', hydraulicDiameter = diameter)

        assert squircle > circle
        assert squircle/circle == pytest.approx(self.areaFactor/np.pi, rel = 1e-14)

class TestAreaLaw:

    interface = 52.209178062411876e-6
    expanded = 506.7074790974977e-6

    def testTheDistributionIsLinearBetweenItsEnds(self):

        sections = 60
        area = scrollAreaDistribution(self.interface, self.expanded, sections)

        assert area.size == sections
        assert area[0] == pytest.approx(self.interface, rel = 1e-15)
        assert area[-1] == pytest.approx(self.expanded, rel = 1e-15)
        assert np.allclose(np.diff(area), (self.expanded - self.interface)/(sections - 1),
                           rtol = 1e-12)

    def testTheConstantVelocityTongueIsTheThroatOverThePortCount(self):

        assert constantVelocityTongueArea(self.expanded, 60) == pytest.approx(self.expanded/60,
                                                                             rel = 1e-15)

    def testTheConstantVelocityLawHoldsAUnityVelocityRatio(self):

        tongue = constantVelocityTongueArea(self.expanded, 60)

        assert scrollVelocityRatio(tongue, self.expanded, 60) == pytest.approx(1.0, rel = 1e-14)

    def testAWiderTongueDeceleratesTowardIt(self):

        # The shipped inlet volute: a tongue area set by the channel port rather than by the
        # port count, which is 6.18 times what the law asks for.
        ratio = scrollVelocityRatio(self.interface, self.expanded, 60)

        assert ratio == pytest.approx(6.182, rel = 1e-3)
        assert ratio == pytest.approx(
            self.interface/constantVelocityTongueArea(self.expanded, 60), rel = 1e-12)

class TestResolution:

    diameter = 0.008
    expandedDiameter = 0.0254

    def testTwoDiametersDetermineBothEnds(self):

        scroll = resolveScrollAreas('circle', interfaceHydraulicDiameter = self.diameter,
                                    expandedHydraulicDiameter = self.expandedDiameter)

        assert scroll['interfaceArea'] == pytest.approx(np.pi*(self.diameter/2)**2, rel = 1e-15)
        assert scroll['expandedArea'] == pytest.approx(np.pi*(self.expandedDiameter/2)**2,
                                                       rel = 1e-15)
        assert scroll['numOrifices'] == pytest.approx(
            scroll['expandedArea']/scroll['interfaceArea'], rel = 1e-15)

    def testAnOrificeCountDividesTheExpandedEnd(self):

        scroll = resolveScrollAreas('circle', expandedHydraulicDiameter = self.expandedDiameter,
                                    numOrifices = 60)

        assert scroll['interfaceArea'] == pytest.approx(scroll['expandedArea']/60, rel = 1e-15)
        assert scroll['numOrifices'] == 60

    def testAnOrificeCountMultipliesTheInterfaceEnd(self):

        scroll = resolveScrollAreas('circle', interfaceHydraulicDiameter = self.diameter,
                                    numOrifices = 60)

        assert scroll['expandedArea'] == pytest.approx(scroll['interfaceArea']*60, rel = 1e-15)

    def testACharacteristicLengthDeterminesASquircleEnd(self):

        scroll = resolveScrollAreas('squarc', interfaceCharacteristicLength = 0.005,
                                    expandedCharacteristicLength = 0.012)

        assert scroll['interfaceArea'] == pytest.approx((1 + 0.75*np.pi)*0.005**2, rel = 1e-15)
        assert scroll['expandedArea'] == pytest.approx((1 + 0.75*np.pi)*0.012**2, rel = 1e-15)

    def testEveryFamilyResolvesTheSameSpecification(self):

        for family in VOLUTESECTIONS:
            scroll = resolveScrollAreas(family, interfaceHydraulicDiameter = self.diameter,
                                        expandedHydraulicDiameter = self.expandedDiameter)
            assert scroll['expandedArea'] > scroll['interfaceArea']

    @pytest.mark.parametrize('specification', [
        {},
        {'interfaceHydraulicDiameter': 0.008},
        {'expandedHydraulicDiameter': 0.0254},
        {'numOrifices': 60},
    ])
    def testAnUnderdeterminedSpecificationIsRefused(self, specification):

        with pytest.raises(ValueError, match = 'both of its end areas'):
            resolveScrollAreas('circle', **specification)

    def testAScrollThatNarrowsTowardTheThroatIsRefused(self):

        with pytest.raises(ValueError, match = 'must exceed the interface area'):
            resolveScrollAreas('circle', interfaceHydraulicDiameter = 0.03,
                               expandedHydraulicDiameter = 0.0254)

class TestFamilies:

    def testTheFamiliesAreCircleAndSquircle(self):

        assert VOLUTESECTIONS == ('circle', 'squarc')

    def testAnUnknownFamilyIsRefused(self):

        with pytest.raises(ValueError, match = 'crossSectionType must be one of'):
            checkFamily('triangle')

    def testTheEggPointsAtExperimental(self):

        with pytest.raises(ValueError, match = 'experimental/eggVolute.py'):
            checkFamily('egg')

class TestAnchor:

    halfExtent = 12.7e-3

    def testTheCentreDoesNotMove(self):

        assert anchorOffset('c', self.halfExtent) == (0.0, 0.0)

    @pytest.mark.parametrize('anchor, expected', [
        ('n', (0.0, -1.0)), ('s', (0.0, +1.0)), ('o', (-1.0, 0.0)), ('i', (+1.0, 0.0))])
    def testTheCompassPointsOffsetByOneHalfExtent(self, anchor, expected):

        radial, axial = anchorOffset(anchor, self.halfExtent)

        assert radial == pytest.approx(expected[0]*self.halfExtent, abs = 1e-18)
        assert axial == pytest.approx(expected[1]*self.halfExtent, abs = 1e-18)

    @pytest.mark.parametrize('anchor, radialSign, axialSign',
                             [('ni', +1, -1), ('si', +1, +1), ('no', -1, -1), ('so', -1, +1)])
    def testTheDiagonalsOffsetByTheHalfExtentOverRootTwo(self, anchor, radialSign, axialSign):

        radial, axial = anchorOffset(anchor, self.halfExtent)
        expected = self.halfExtent/np.sqrt(2)

        assert radial == pytest.approx(radialSign*expected, rel = 1e-15)
        assert axial == pytest.approx(axialSign*expected, rel = 1e-15)

    def testCaseDoesNotMatter(self):

        assert anchorOffset('NO', self.halfExtent) == anchorOffset('no', self.halfExtent)

    def testAnUnrecognizedAnchorCentres(self):

        assert anchorOffset('q', self.halfExtent) == (0.0, 0.0)
        assert anchorOffset('', self.halfExtent) == (0.0, 0.0)

class TestPlacement:

    '''The scroll radius and axial offset a port implies.'''

    portAxial = 0.055945
    portRadius = 0.121794
    tongueDiameter = 0.008158

    @pytest.mark.parametrize('family', VOLUTESECTIONS)
    @pytest.mark.parametrize('anchor', ['c', 'n', 's', 'i', 'o', 'ni', 'si', 'no', 'so'])
    def testPlacementPutsTheTongueCentreOnThePort(self, family, anchor):

        scrollRadius, axialOffset = scrollPlacement(family, self.tongueDiameter, anchor,
                                                    self.portAxial, self.portRadius)
        halfExtent = characteristicLengthFromDiameter(family, self.tongueDiameter)
        radial, axial = sectionCentreOffset(family, halfExtent, anchor)

        assert scrollRadius + radial == pytest.approx(self.portRadius, rel = 1e-15)
        assert axialOffset + axial == pytest.approx(self.portAxial, rel = 1e-15)

    def testACircleCentreIsItsAnchorOffset(self):

        halfExtent = 0.0127

        for anchor in ('c', 'n', 's', 'i', 'o', 'ni', 'si', 'no', 'so'):
            assert sectionCentreOffset('circle', halfExtent, anchor) == anchorOffset(anchor,
                                                                                    halfExtent)

    def testASquircleCentreSitsOffItsCorner(self):

        halfExtent = 0.005

        assert sectionCentreOffset('squarc', halfExtent) == (+halfExtent, -halfExtent)

    def testASquircleIgnoresTheAnchor(self):

        halfExtent = 0.005
        corner = sectionCentreOffset('squarc', halfExtent, 'c')

        for anchor in ('n', 's', 'i', 'o', 'ni', 'si', 'no', 'so'):
            assert sectionCentreOffset('squarc', halfExtent, anchor) == corner

    def testTheTongueIsCentredWhateverTheAnchor(self):

        placements = {anchor: scrollPlacement('circle', self.tongueDiameter, anchor,
                                              self.portAxial, self.portRadius)
                      for anchor in ('c', 'i', 'o', 'n', 's')}

        # Every anchor puts the tongue in the same place and differs only in which way the growing
        # sections reach, so the scroll radii differ by the section half extent.
        halfExtent = self.tongueDiameter/2
        assert placements['i'][0] == pytest.approx(placements['c'][0] - halfExtent, rel = 1e-14)
        assert placements['o'][0] == pytest.approx(placements['c'][0] + halfExtent, rel = 1e-14)
        assert placements['n'][1] == pytest.approx(placements['c'][1] + halfExtent, rel = 1e-14)
        assert placements['s'][1] == pytest.approx(placements['c'][1] - halfExtent, rel = 1e-14)

class TestTopology:

    '''The two scroll topologies and what each asks of the throat.'''

    tongue = 52.209178062411876e-6
    throat = 506.7074790974977e-6

    def testTheTopologiesAreRingAndCutwater(self):

        assert SCROLLTYPES == ('ring', 'cutwater')

    def testAnUnknownTopologyIsRefused(self):

        with pytest.raises(ValueError, match = 'voluteScrollType must be one of'):
            checkScrollType('spiral')

    def testACutwaterServesEveryPortAndARingHalfOfThem(self):

        assert portsPerScroll(60, 'cutwater') == 60
        assert portsPerScroll(60, 'ring') == 30

    def testARingThroatIsHalfACutwaterThroat(self):

        cutwater = constantVelocityThroatArea(self.tongue, 60, 'cutwater')
        ring = constantVelocityThroatArea(self.tongue, 60, 'ring')

        assert cutwater == pytest.approx(self.tongue*60, rel = 1e-15)
        assert ring == pytest.approx(cutwater/2, rel = 1e-15)

    @pytest.mark.parametrize('scrollType', SCROLLTYPES)
    def testTheThroatLawInvertsTheTongueLaw(self, scrollType):

        throat = constantVelocityThroatArea(self.tongue, 60, scrollType)

        assert constantVelocityTongueArea(throat, 60, scrollType) == pytest.approx(self.tongue,
                                                                                  rel = 1e-14)
        assert scrollVelocityRatio(self.tongue, throat, 60, scrollType) == pytest.approx(1.0,
                                                                                        rel = 1e-14)

    def testACutwaterAreaRisesOnceAcrossTheWrap(self):

        area = scrollAreaDistribution(self.tongue, self.throat, 11, 'cutwater')

        assert np.all(np.diff(area) > 0.0)
        assert area[0] == pytest.approx(self.tongue, rel = 1e-15)
        assert area[-1] == pytest.approx(self.throat, rel = 1e-15)

    def testARingAreaIsSymmetricAboutItsFeed(self):

        area = scrollAreaDistribution(self.tongue, self.throat, 11, 'ring')

        assert np.allclose(area, area[::-1], rtol = 1e-15)
        assert area[0] == pytest.approx(self.throat, rel = 1e-15)
        assert area[-1] == pytest.approx(self.throat, rel = 1e-15)
        assert area[5] == pytest.approx(self.tongue, rel = 1e-15)
        assert np.all(np.diff(area[:6]) < 0.0)
        assert np.all(np.diff(area[5:]) > 0.0)

    def testBothLawsAreLinearInWrapAngleOnEachRun(self):

        for scrollType, run in (('cutwater', slice(0, 11)), ('ring', slice(0, 6))):
            area = scrollAreaDistribution(self.tongue, self.throat, 11, scrollType)[run]
            step = np.diff(area)
            assert np.allclose(step, step[0], rtol = 1e-12)

    def testTheTongueGapIsTheWallAngleFlooredAtASectionStep(self):

        radius, sections = 0.122, 60
        step = 2*np.pi/(sections - 1)

        # A thin wall subtends less than one section step, so the step is what is left.
        assert tongueGapAngle(radius, 6.0e-4, sections) == pytest.approx(step, rel = 1e-15)
        # A wall thick enough to subtend more than a step sets the gap itself.
        thick = 0.05
        assert tongueGapAngle(radius, thick, sections) == pytest.approx(
            2*np.arcsin(thick/(2*radius)), rel = 1e-14)
        assert tongueGapAngle(radius, None, sections) == pytest.approx(step, rel = 1e-15)
