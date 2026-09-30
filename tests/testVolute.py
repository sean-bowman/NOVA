'''

Tests for the volute scroll generator in Volute.py.

Every quantity here is held against a closed form evaluated on the surface the generator wrote,
not against the inputs it was given, so a section that reports one area and draws another fails.

**A section reports the ideal shape and draws a polygon.** A circle of `N` chords inscribed in
radius `r` encloses `(N/2 pi) sin(2 pi/N)` of the circle and carries `(N/pi) sin(pi/N)` of its
perimeter, so its hydraulic diameter is `2 r cos(pi/N)`. At the 40 points the shipped
configuration uses that is 0.432 per cent of area and 0.324 per cent of hydraulic diameter, and
both fall as the square of the point count. The reported figures are the ideal circle.

**A squircle is a square of side `2L` with quarter-round corners.** Its area is
`(1 + 0.75 pi) L^2`, its perimeter `2 (1 + 0.75 pi) L`, so its hydraulic diameter is `2L`, the
same as a circle of radius `L`. The characteristic length that a hydraulic diameter implies is
`D (2 + 1.5 pi)/(4 + 3 pi)`, which is `D/2`.

**The area law is linear in wrap angle.** The scroll runs from the interface area to the expanded
area over one full turn, and an orifice count divides the expanded area rather than multiplying
the interface area. Nothing in the generator produces any other distribution.

**An anchor is a tangency.** `c` centres the section on the scroll radius, `o` puts its outermost
point there and `i` its innermost, `n` and `s` put its extreme axial point on the axial offset,
and the four diagonals offset by the section radius over root two in each. An unrecognized anchor
centres the section, which is what the method docstring says it does.

**The sweep is a rotation about the axis.** Every point of a section shares one meridional plane,
consecutive sections are evenly spaced in angle, the sense follows the scroll direction, and the
axial offset is added to the axis coordinate and nothing else.

**A ring wraps a full turn and a cutwater stops short of one.** A ring closes on itself, so its
first and last sections share a wrap angle and carry the same area, with the tongue half a turn
away. A cutwater leaves the angle its tongue wall occupies between its two ends, and its area
rises once from the tongue to the throat.

**A section reports the ideal and draws the polygon.** `drawnArea` is what the swept surface
encloses and `flowArea` is that less any support inside the duct, so a reader is never handed the
nominal circle as the area the coolant sees.

**The wall is a hoop stress and an offset.** The thickness follows `t = p D / 2 sigma` on the local
hydraulic diameter, times the factor a torus carries at its inner crotch,
`(2R - a)/(2(R - a))`, which tends to one as the bend radius grows. The relation inverts, a
printable minimum floors it, and the shell stands off the inner section by that thickness
everywhere except the closure point each section is stitched at.

Author: Sean Bowman

'''

import contextlib
import io

import numpy as np
import pytest

from NOVA.Volute import (VOLUTESECTIONS, Volute, hoopStressCalculator,
                         toroidalCrotchFactor)
from NOVA.voluteSections import SCROLLTYPES, anchorOffset, tongueGapAngle

interfaceDiameter = 0.008
expandedDiameter = 0.0254
scrollRadius = 0.105

def buildVolute(**options):

    '''Build a volute with the progress output discarded, returning the object.'''

    settings = dict(voluteScrollRadius = scrollRadius, numCrossSections = 8,
                    crossSectionResolution = 40,
                    interfaceHydraulicDiameter = interfaceDiameter,
                    expandedHydraulicDiameter = expandedDiameter, export = 'off')
    settings.update(options)
    volute = Volute(**settings)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        volute.generateVolute()
    return volute

def sectionArea(volute, index):

    '''Area of one drawn section, by Newell's method, which needs no projection.'''

    points = np.column_stack([volute.xVolute[index], volute.yVolute[index], volute.zVolute[index]])
    return 0.5*np.linalg.norm(np.sum(np.cross(points, np.roll(points, -1, axis = 0)), axis = 0))

def sectionPerimeter(volute, index):
    points = np.column_stack([volute.xVolute[index], volute.yVolute[index], volute.zVolute[index]])
    return float(np.sum(np.linalg.norm(np.diff(points, axis = 0), axis = 1)))

def sectionRadius(volute, index):
    return np.sqrt(volute.xVolute[index]**2 + volute.yVolute[index]**2)

class TestCircleSection:

    '''The circular section against the inscribed polygon.'''

    def testReportedAreaIsTheIdealCircle(self):

        volute = buildVolute()
        radius = np.asarray(volute.hydraulicDiameter)/2.0

        assert np.allclose(volute.crossSectionalArea, np.pi*radius**2, rtol = 1e-14)

    def testTheScrollRunsBetweenTheRequestedAreas(self):

        volute = buildVolute()

        assert volute.crossSectionalArea[0] == pytest.approx(np.pi*(interfaceDiameter/2)**2,
                                                            rel = 1e-14)
        assert volute.crossSectionalArea[-1] == pytest.approx(np.pi*(expandedDiameter/2)**2,
                                                              rel = 1e-14)

    @pytest.mark.parametrize('points', [40, 80, 160])
    def testDrawnAreaIsTheInscribedPolygon(self, points):

        volute = buildVolute(crossSectionResolution = points)
        chords = points - 1
        expected = (chords/(2*np.pi))*np.sin(2*np.pi/chords)

        for index in range(volute.numCrossSections):
            ratio = sectionArea(volute, index)/volute.crossSectionalArea[index]
            assert ratio == pytest.approx(expected, rel = 1e-12)

    @pytest.mark.parametrize('points', [40, 80])
    def testDrawnPerimeterIsTheInscribedPolygon(self, points):

        volute = buildVolute(crossSectionResolution = points)
        chords = points - 1
        expected = (chords/np.pi)*np.sin(np.pi/chords)

        for index in range(volute.numCrossSections):
            ideal = np.pi*volute.hydraulicDiameter[index]
            assert sectionPerimeter(volute, index)/ideal == pytest.approx(expected, rel = 1e-12)

    def testDrawnHydraulicDiameterIsTwoRadiusCosine(self):

        points = 40
        volute = buildVolute(crossSectionResolution = points)
        chords = points - 1

        for index in range(volute.numCrossSections):
            drawn = 4*sectionArea(volute, index)/sectionPerimeter(volute, index)
            expected = volute.hydraulicDiameter[index]*np.cos(np.pi/chords)
            assert drawn == pytest.approx(expected, rel = 1e-12)

    def testTheDiscretizationBiasFallsAsTheSquareOfThePointCount(self):

        coarse = buildVolute(crossSectionResolution = 40)
        fine = buildVolute(crossSectionResolution = 80)
        coarseError = 1.0 - sectionArea(coarse, 0)/coarse.crossSectionalArea[0]
        fineError = 1.0 - sectionArea(fine, 0)/fine.crossSectionalArea[0]
        # The chords are one fewer than the points, since the profile closes on its first vertex.
        expected = (79/39)**2

        assert coarseError/fineError == pytest.approx(expected, rel = 0.01)
        assert coarseError == pytest.approx(0.00432, rel = 0.01)

class TestAreaLaw:

    '''The distribution the scroll is built on.'''

    def testAreaIsLinearInWrapAngle(self):

        volute = buildVolute(numCrossSections = 12)
        area = np.asarray(volute.crossSectionalArea)

        assert np.allclose(area, np.linspace(area[0], area[-1], area.size), rtol = 1e-15)

    def testAnOrificeCountDividesTheExpandedArea(self):

        volute = buildVolute(interfaceHydraulicDiameter = None, numOrifices = 60)
        expanded = np.pi*(expandedDiameter/2)**2

        assert volute.crossSectionalArea[0] == pytest.approx(expanded/60, rel = 1e-14)
        assert volute.crossSectionalArea[-1] == pytest.approx(expanded, rel = 1e-14)

    def testAreaAndDiameterRoundTrip(self):

        volute = buildVolute(interfaceHydraulicDiameter = None, expandedHydraulicDiameter = None,
                             interfaceArea = 5.0e-5, expandedArea = 5.0e-4)

        assert volute.interfaceHydraulicDiameter == pytest.approx(2*np.sqrt(5.0e-5/np.pi),
                                                                  rel = 1e-14)
        assert volute.expandedHydraulicDiameter == pytest.approx(2*np.sqrt(5.0e-4/np.pi),
                                                                 rel = 1e-14)

    def testHydraulicDiameterFollowsTheArea(self):

        volute = buildVolute()
        area = np.asarray(volute.crossSectionalArea)

        assert np.allclose(volute.hydraulicDiameter, 2*np.sqrt(area/np.pi), rtol = 1e-14)

class TestAnchor:

    '''Each anchor as a tangency on the built section.'''

    # A resolution of 61 points puts vertices exactly on the four compass directions, so the
    # extreme of the drawn polygon is the extreme of the circle rather than a chord short of it.
    points = 61
    offset = 0.05

    def extents(self, anchor):
        volute = buildVolute(crossSectionResolution = self.points, anchorBy = anchor,
                            axialOffset = self.offset, numCrossSections = 4)
        radius = np.asarray(volute.hydraulicDiameter)/2.0
        built = []
        for index in range(volute.numCrossSections):
            r = sectionRadius(volute, index)
            z = volute.zVolute[index]
            built.append((r.min(), r.max(), z.min(), z.max(), radius[index]))
        return built

    def testCentreAnchorCentresOnTheScrollRadius(self):

        for rMin, rMax, zMin, zMax, _ in self.extents('c'):
            assert 0.5*(rMin + rMax) == pytest.approx(scrollRadius, rel = 1e-12)
            assert 0.5*(zMin + zMax) == pytest.approx(self.offset, rel = 1e-12)

    def testOuterAnchorPutsTheOutermostPointOnTheScrollRadius(self):

        for _, rMax, _, _, _ in self.extents('o'):
            assert rMax == pytest.approx(scrollRadius, rel = 1e-12)

    def testInnerAnchorPutsTheInnermostPointOnTheScrollRadius(self):

        for rMin, _, _, _, _ in self.extents('i'):
            assert rMin == pytest.approx(scrollRadius, rel = 1e-12)

    def testNorthAndSouthAnchorOnTheAxialOffset(self):

        for _, _, _, zMax, _ in self.extents('n'):
            assert zMax == pytest.approx(self.offset, abs = 1e-15)
        for _, _, zMin, _, _ in self.extents('s'):
            assert zMin == pytest.approx(self.offset, abs = 1e-15)

    @pytest.mark.parametrize('anchor, radialSign, axialSign',
                             [('ni', +1, -1), ('si', +1, +1), ('no', -1, -1), ('so', -1, +1)])
    def testDiagonalAnchorsOffsetByTheRadiusOverRootTwo(self, anchor, radialSign, axialSign):

        for rMin, rMax, zMin, zMax, radius in self.extents(anchor):
            expected = radius/np.sqrt(2.0)
            assert 0.5*(rMin + rMax) - scrollRadius == pytest.approx(radialSign*expected,
                                                                     rel = 1e-12)
            assert 0.5*(zMin + zMax) - self.offset == pytest.approx(axialSign*expected,
                                                                    rel = 1e-9)

    def testAnUnrecognizedAnchorCentresTheSection(self):

        unrecognized = self.extents('q')
        centred = self.extents('c')

        for (aMin, aMax, _, _, _), (bMin, bMax, _, _, _) in zip(unrecognized, centred):
            assert aMin == pytest.approx(bMin, rel = 1e-15)
            assert aMax == pytest.approx(bMax, rel = 1e-15)

class TestSweep:

    '''The roll about the scroll axis.'''

    def testEverySectionLiesInOneMeridionalPlane(self):

        volute = buildVolute()

        for index in range(volute.numCrossSections):
            angle = np.arctan2(volute.yVolute[index], volute.xVolute[index])
            assert np.ptp(np.unwrap(angle)) == pytest.approx(0.0, abs = 1e-12)

    @pytest.mark.parametrize('direction, sign', [('cw', +1), ('ccw', -1)])
    @pytest.mark.parametrize('scrollType', SCROLLTYPES)
    def testSectionsAreEvenlySpacedInTheDirectionAsked(self, direction, sign, scrollType):

        sections = 9
        volute = buildVolute(scrollDirection = direction, numCrossSections = sections,
                            scrollType = scrollType)
        angle = np.array([np.arctan2(volute.yVolute[i, 0], volute.xVolute[i, 0])
                          for i in range(sections)])
        step = np.diff(np.unwrap(angle))
        sweep = 2*np.pi - volute.tongueGap()

        assert np.allclose(step, sign*sweep/(sections - 1), rtol = 1e-12)

    def testARingClosesOnItself(self):

        volute = buildVolute(scrollType = 'ring')
        first = np.arctan2(volute.yVolute[0, 0], volute.xVolute[0, 0])
        last = np.arctan2(volute.yVolute[-1, 0], volute.xVolute[-1, 0])

        assert volute.tongueGap() == 0.0
        assert first == pytest.approx(last, abs = 1e-12)
        assert volute.crossSectionalArea[0] == pytest.approx(volute.crossSectionalArea[-1],
                                                             rel = 1e-15)

    def testACutwaterLeavesItsTongueWallAnAngle(self):

        sections = 60
        volute = buildVolute(scrollType = 'cutwater', numCrossSections = sections,
                            wallThickness = 6.0e-4)
        gap = volute.tongueGap()
        angle = np.unwrap([np.arctan2(volute.yVolute[i, 0], volute.xVolute[i, 0])
                           for i in range(sections)])
        # The two ends sit in different meridional planes, the tongue wall between them.
        ends = np.ptp(np.unwrap([angle[0], angle[-1]]))

        assert gap == pytest.approx(tongueGapAngle(scrollRadius, volute.wallThickness, sections),
                                    rel = 1e-14)
        assert gap > 0.0
        assert ends == pytest.approx(gap, rel = 1e-12)
        assert np.ptp(angle) == pytest.approx(2*np.pi - gap, rel = 1e-12)

    @pytest.mark.parametrize('scrollType, expected',
                             [('cutwater', 'monotone'), ('ring', 'symmetric')])
    def testTheAreaLawFollowsTheTopology(self, scrollType, expected):

        volute = buildVolute(scrollType = scrollType, numCrossSections = 11)
        area = np.asarray(volute.crossSectionalArea)

        if expected == 'monotone':
            assert np.all(np.diff(area) > 0.0)
            return

        # A ring falls to the tongue at half a turn and rises back, symmetric about it.
        assert np.allclose(area, area[::-1], rtol = 1e-15)
        assert area.argmin() == (area.size - 1)//2
        assert np.all(np.diff(area[:area.size//2 + 1]) < 0.0)

    def testTheAxialOffsetShiftsTheAxisCoordinateAlone(self):

        plain = buildVolute()
        shifted = buildVolute(axialOffset = 0.05)

        assert np.allclose(shifted.zVolute - plain.zVolute, 0.05, rtol = 1e-12)
        assert np.allclose(shifted.xVolute, plain.xVolute, rtol = 1e-15)
        assert np.allclose(shifted.yVolute, plain.yVolute, rtol = 1e-15)

    def testTheSweepPreservesTheScrollRadius(self):

        volute = buildVolute(anchorBy = 'o', crossSectionResolution = 61)

        for index in range(volute.numCrossSections):
            assert sectionRadius(volute, index).max() == pytest.approx(scrollRadius, rel = 1e-12)

class TestWall:

    '''Thickness from hoop stress, and the offset that carries it.'''

    def testHoopStressRelationInvertsExactly(self):

        pressure, diameter, stress = 1.2e7, 0.0254, 2.0e8
        thickness = hoopStressCalculator(pressureDifferential = pressure, diameter = diameter,
                                        hoopStress = stress)

        assert thickness == pytest.approx(pressure*diameter/(2*stress), rel = 1e-15)
        assert hoopStressCalculator(pressureDifferential = pressure, diameter = diameter,
                                    thickness = thickness) == pytest.approx(stress, rel = 1e-14)

    def testThicknessFollowsTheLocalHydraulicDiameter(self):

        pressure, stress = 1.2e7, 2.0e8
        volute = buildVolute(wallHoopStress = stress, pressureDifferential = pressure)
        diameter = np.asarray(volute.hydraulicDiameter)
        bend = scrollRadius + np.array([anchorOffset(volute.anchorBy, d/2)[0] for d in diameter])
        expected = (pressure*diameter*toroidalCrotchFactor(diameter, bend))/(2*stress)

        assert np.allclose(volute.wallThickness, expected, rtol = 1e-14)

    def testTheCrotchFactorRecoversAStraightTube(self):

        diameter = 0.0254

        assert toroidalCrotchFactor(diameter, None) == 1.0
        assert toroidalCrotchFactor(diameter, 1.0e6) == pytest.approx(1.0, abs = 1e-7)
        # Closed form at the inner crotch, from the membrane solution.
        for bend in (0.1, 0.122, 0.35):
            a = diameter/2
            assert toroidalCrotchFactor(diameter, bend) == pytest.approx(
                (2*bend - a)/(2*(bend - a)), rel = 1e-15)

    def testTheCrotchFactorGrowsAsTheBendTightens(self):

        diameter = 0.0254
        factors = [toroidalCrotchFactor(diameter, bend) for bend in (0.4, 0.2, 0.1, 0.05)]

        assert all(np.diff(factors) > 0.0)
        assert all(factor > 1.0 for factor in factors)

    def testAPrintableMinimumFloorsTheSizedWall(self):

        pressure, stress = 1.2e7, 2.0e8
        floor = 1.0e-3
        volute = buildVolute(wallHoopStress = stress, pressureDifferential = pressure,
                            minWallThickness = floor)
        unfloored = buildVolute(wallHoopStress = stress, pressureDifferential = pressure)

        assert np.all(np.asarray(volute.wallThickness) >= floor)
        assert np.allclose(volute.wallThickness,
                           np.maximum(np.asarray(unfloored.wallThickness), floor), rtol = 1e-15)

    def testTheHoopRelationNeedsExactlyOneUnknown(self):

        with pytest.raises(ValueError, match = 'exactly one of thickness and hoopStress'):
            hoopStressCalculator(pressureDifferential = 1.2e7, diameter = 0.0254)
        with pytest.raises(ValueError, match = 'exactly one of thickness and hoopStress'):
            hoopStressCalculator(pressureDifferential = 1.2e7, diameter = 0.0254,
                                 thickness = 5.0e-4, hoopStress = 2.0e8)

    def testAWrongLengthThicknessArrayIsRefused(self):

        with pytest.raises(ValueError, match = 'one value per cross section'):
            buildVolute(wallThickness = np.full(5, 5.0e-4), numCrossSections = 8)

    def testANumpyScalarThicknessIsAccepted(self):

        volute = buildVolute(wallThickness = np.float64(5.0e-4))

        assert np.allclose(volute.wallThickness, 5.0e-4, rtol = 1e-15)

    def testTheShellStandsOffByTheRequestedThickness(self):

        thickness = 5.0e-4
        volute = buildVolute(wallThickness = thickness)

        for index in range(volute.numCrossSections):
            inner = np.column_stack([volute.xVolute[index], volute.yVolute[index],
                                     volute.zVolute[index]])
            outer = np.column_stack([volute.xShell[index], volute.yShell[index],
                                     volute.zShell[index]])
            gap = np.linalg.norm(outer[:, None, :] - inner[None, :, :], axis = 2).min(axis = 1)
            # The first and last point of a section are the closure the shell is stitched at.
            assert np.allclose(gap[1:-1], thickness, rtol = 2e-3)

    def testTheShellEnclosesTheSection(self):

        volute = buildVolute(wallThickness = 5.0e-4)

        for index in range(volute.numCrossSections):
            innerRadius = sectionRadius(volute, index)
            shellRadius = np.sqrt(volute.xShell[index]**2 + volute.yShell[index]**2)
            assert shellRadius.max() > innerRadius.max()
            assert shellRadius.min() < innerRadius.min()

class TestSquircleSection:

    '''The squircle against its own closed form.'''

    characteristicLength = 0.005
    expandedLength = 0.012

    def squircle(self, **options):
        settings = dict(crossSectionType = 'squarc', numCrossSections = 4,
                        crossSectionResolution = 200, interfaceHydraulicDiameter = None,
                        expandedHydraulicDiameter = None,
                        interfaceCharLen = self.characteristicLength,
                        expandedCharLen = self.expandedLength)
        settings.update(options)
        return buildVolute(**settings)

    def testAreaFollowsTheCharacteristicLength(self):

        volute = self.squircle()
        shapeFactor = 1.0 + 0.75*np.pi

        assert volute.crossSectionalArea[0] == pytest.approx(
            shapeFactor*self.characteristicLength**2, rel = 1e-14)
        assert volute.crossSectionalArea[-1] == pytest.approx(
            shapeFactor*self.expandedLength**2, rel = 1e-14)

    def testHydraulicDiameterIsTwiceTheCharacteristicLength(self):

        volute = self.squircle()
        length = np.sqrt(np.asarray(volute.crossSectionalArea)/(1.0 + 0.75*np.pi))

        assert np.allclose(volute.hydraulicDiameter, 2*length, rtol = 1e-12)

    def testACharacteristicLengthFollowsFromAHydraulicDiameter(self):

        diameter = 0.010
        volute = self.squircle(interfaceCharLen = None, interfaceHydraulicDiameter = diameter)
        shapeFactor = 1.0 + 0.75*np.pi
        length = diameter*(2 + 1.5*np.pi)/(4 + 3*np.pi)

        assert length == pytest.approx(diameter/2, rel = 1e-15)
        assert volute.crossSectionalArea[0] == pytest.approx(shapeFactor*length**2, rel = 1e-14)

    def testTheDrawnSectionCarriesTheReportedArea(self):

        volute = self.squircle()

        for index in range(volute.numCrossSections):
            ratio = sectionArea(volute, index)/volute.crossSectionalArea[index]
            assert ratio == pytest.approx(1.0, rel = 2e-4)

class TestSectionFamilies:

    '''What the package builds.'''

    def testTheFamiliesAreTheOnesTheGeneratorDispatches(self):

        assert VOLUTESECTIONS == ('circle', 'squarc')

    @pytest.mark.parametrize('section', VOLUTESECTIONS)
    def testEveryNamedFamilyProducesFiniteGeometry(self, section):

        options = dict(crossSectionType = section)
        if section == 'squarc':
            options.update(crossSectionResolution = 60)
        volute = buildVolute(**options)

        assert np.size(volute.xVolute) > 0
        assert np.isfinite(volute.xVolute).all()
        assert np.isfinite(volute.yVolute).all()
        assert np.isfinite(volute.zVolute).all()

class TestBuiltArea:

    '''What the swept surface encloses, as against what the area law asked for.'''

    def testTheDrawnAreaIsTheInscribedPolygonOfTheRequestedArea(self):

        points = 40
        volute = buildVolute(crossSectionResolution = points)
        chords = points - 1
        expected = (chords/(2*np.pi))*np.sin(2*np.pi/chords)

        assert np.allclose(volute.drawnArea/np.asarray(volute.crossSectionalArea), expected,
                           rtol = 1e-12)

    def testTheDrawnAreaIsWhatTheSectionsMeasure(self):

        volute = buildVolute()

        for index in range(volute.numCrossSections):
            assert volute.drawnArea[index] == pytest.approx(sectionArea(volute, index),
                                                            rel = 1e-14)

    def testWithNoSupportTheFlowAreaIsTheDrawnArea(self):

        volute = buildVolute()

        assert np.allclose(volute.flowArea, volute.drawnArea, rtol = 1e-15)

    def testASupportTakesAreaOutOfTheDuct(self):

        volute = buildVolute(circlePrintability = 'thick')

        assert np.size(volute.supportArea) == volute.numCrossSections
        assert np.all(np.asarray(volute.supportArea) > 0.0)
        assert np.all(volute.flowArea < volute.drawnArea)
        assert np.allclose(volute.flowArea, volute.drawnArea - np.asarray(volute.supportArea),
                           rtol = 1e-15)

    def testTheSupportIsSizedToHoldTheRequestedFlowArea(self):

        volute = buildVolute(circlePrintability = 'thick')
        requested = np.asarray(volute.crossSectionalArea)

        # The section is grown until what is left after the support covers the requested area, so
        # the nominal circle reported ends up above it.
        assert np.all(requested >= volute.flowArea)

class TestRefusals:

    '''The combinations that used to raise from inside, or do nothing quietly.'''

    def testAnUnrecognizedSupportNameIsRefused(self):

        with pytest.raises(ValueError, match = 'circlePrintability must be one of'):
            buildVolute(circlePrintability = 'on')

    @pytest.mark.parametrize('support', ['thick', 'thin'])
    def testASquircleTakesNoSupport(self, support):

        with pytest.raises(ValueError, match = 'circular cross section only'):
            buildVolute(crossSectionType = 'squarc', circlePrintability = support)

    @pytest.mark.parametrize('support', ['thick', 'thin'])
    def testASupportSurvivesOuterWallAlignment(self, support):

        volute = buildVolute(circlePrintability = support, wallThickness = 5.0e-4,
                            alignWallBy = 'outer')

        assert np.size(volute.xInternalSupportWall) > 0
        assert np.isfinite(volute.xInternalSupportWall).all()
        assert np.isfinite(volute.xVolute).all()

    def testAnUnrecognizedScrollTypeIsRefused(self):

        with pytest.raises(ValueError, match = 'voluteScrollType must be one of'):
            buildVolute(scrollType = 'spiral')

    def testAnUnrecognizedCrossSectionIsRefused(self):

        with pytest.raises(ValueError, match = 'crossSectionType must be one of'):
            buildVolute(crossSectionType = 'triangle')

    def testAScaledByOtherThanLinearIsRefused(self):

        with pytest.raises(ValueError, match = "scaledBy must be 'linear'"):
            buildVolute(scaledBy = 'momentum')
