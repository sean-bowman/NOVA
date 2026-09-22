'''

Tests for the cooling channel cross-section geometry in channelGeometry.py.

Geometry is the one part of this tool that can be checked against closed form rather than
against a correlation, and that is what is done here.

**The maximum channel radius is exact.** The largest channel that fits between adjacent radial
planes is a circle inscribed in a wedge of half-angle pi/n and tangent externally to the wall
circle. Its center sits at distance d from the axis with radius r = d sin(theta), and tangency to
the wall gives d = R + r, so

    r = R sin(theta) / (1 - sin(theta))

That is a derivation, not a fit, and the implementation is held to it exactly.

**The transport frame is orthonormal, right-handed and twist-minimizing.** Those three are what
distinguish a parallel transport frame from a Frenet frame, and each is checkable: the frame
vectors are unit and mutually orthogonal at every station, the triad is right-handed, and for a
planar curve the frame acquires no rotation about the tangent at all, which is the property that
keeps a section from winding up where the curve happens to bend.

**A rectangle is drawn on the wall.** Its outline is closed with its corners exact, its depth lies
along the wall normal and its width across the wall, and the frame it rides has the wall normal
as its normal on a cone whether or not the centerline wraps.

**A circular cross section is a circle.** Its points lie at exactly the channel radius from the
centerline, in the plane normal to the local tangent, and its flow area is exactly pi r squared.

Author: Sean Bowman

'''

import os
import sys

import numpy as np
import pytest

from NOVA.channelGeometry import (ChannelGeometryInputs, generateCrossSections, getMaxChannelRadius,
                                  rectangularProfile, wallNormalFrames)

def circularInputs(numCrossSections = 40, numCSPointsChannel = 60, nChannel = 60):

    '''A circular-channel definition with interfaces off.'''

    return ChannelGeometryInputs(
        numCrossSections     = numCrossSections,
        numCSPointsChannel   = numCSPointsChannel,
        nChannel             = nChannel,
        channelType          = 'circle',
        hotWallThickness     = 1.0e-3,
        infillThickness      = 1.0e-3)

def straightCenterline(numStations, length = 0.3, radius = 0.06):

    '''A centerline running straight along the nozzle axis at constant radius.'''

    z = np.linspace(0.0, length, numStations)
    x = np.full(numStations, radius)
    y = np.zeros(numStations)

    return x, y, z

class TestMaxChannelRadius:

    '''The largest channel that fits is given in closed form.'''

    @pytest.mark.parametrize('nChannel', [10, 24, 60, 120, 240])
    @pytest.mark.parametrize('wallRadius', [0.03, 0.05, 0.09, 0.3])
    def testAgainstTheInscribedWedgeCircle(self, nChannel, wallRadius):

        geometry = circularInputs(nChannel = nChannel)
        rNozzle = np.array([wallRadius])

        computed = getMaxChannelRadius(geometry, rNozzle, 0)

        # The wall the channel sits against is offset by the hot wall less the infill, and the
        # result is then pulled in by half the infill to leave material between neighbours.
        offsetWall = wallRadius + geometry.hotWallThickness - geometry.infillThickness
        halfAngle  = np.pi / nChannel
        expected   = offsetWall * np.sin(halfAngle) / (1 - np.sin(halfAngle)) \
                     - geometry.infillThickness / 2

        assert computed == pytest.approx(expected, rel = 1e-14)

    def testChannelsFitWithoutOverlapping(self):

        # The independent check: place nChannel circles of the computed radius on their pitch
        # circle and confirm neighbouring circles do not intersect, and none crosses the wall.
        wallRadius, nChannel = 0.06, 48
        geometry = circularInputs(nChannel = nChannel)

        channelRadius = getMaxChannelRadius(geometry, np.array([wallRadius]), 0)
        offsetWall = wallRadius + geometry.hotWallThickness - geometry.infillThickness

        # Center distance from the axis follows from tangency to the offset wall.
        centerDistance = offsetWall + channelRadius + geometry.infillThickness / 2
        pitch = 2 * centerDistance * np.sin(np.pi / nChannel)

        # Neighbours are separated by the infill, so the gap is the infill thickness exactly.
        assert pitch - 2 * channelRadius == pytest.approx(geometry.infillThickness, rel = 1e-9)
        assert centerDistance - channelRadius >= offsetWall - 1e-12

    def testMoreChannelsMeansSmallerChannels(self):

        geometry = circularInputs()
        radii = [getMaxChannelRadius(circularInputs(nChannel = n), np.array([0.06]), 0)
                 for n in (20, 40, 80, 160)]

        assert all(later < earlier for earlier, later in zip(radii, radii[1:]))

class TestCircularCrossSection:

    '''A circular cross section is a circle, in the plane it should be in.'''

    def sweep(self, numStations = 30, numPoints = 48, channelRadius = 0.002):

        geometry = circularInputs(numCrossSections = numStations, numCSPointsChannel = numPoints)
        x, y, z = straightCenterline(numStations)
        radius = np.full(numStations, channelRadius)

        xChannel, yChannel, zChannel, heatTransfer = generateCrossSections(
            geometry, x, y, z, radius, 'circle')

        return (x, y, z), (xChannel, yChannel, zChannel), heatTransfer, channelRadius

    def testShapeIsPointsByStations(self):

        _, (xChannel, yChannel, zChannel), _, _ = self.sweep(numStations = 30, numPoints = 48)

        assert xChannel.shape == yChannel.shape == zChannel.shape == (48, 30)

    def testEveryPointSitsAtTheChannelRadius(self):

        (x, y, z), (xChannel, yChannel, zChannel), _, channelRadius = self.sweep()

        distance = np.sqrt((xChannel - x[None, :])**2
                           + (yChannel - y[None, :])**2
                           + (zChannel - z[None, :])**2)

        assert np.max(np.abs(distance - channelRadius)) < 1e-12

    def testTheCrossSectionIsNormalToTheCenterline(self):

        # A straight centerline along z means every cross section must lie in a constant-z plane.
        (_, _, z), (_, _, zChannel), _, _ = self.sweep()

        assert np.max(np.abs(zChannel - z[None, :])) < 1e-12

    def testTheReportedAreaIsPiRSquared(self):

        _, _, heatTransfer, channelRadius = self.sweep()

        assert np.allclose(heatTransfer['flowArea'], np.pi * channelRadius**2, rtol = 1e-14)

    def testTheAreaScalesWithTheSquareOfTheRadius(self):

        small = self.sweep(channelRadius = 0.001)[2]['flowArea'][0]
        large = self.sweep(channelRadius = 0.002)[2]['flowArea'][0]

        assert large / small == pytest.approx(4.0, rel = 1e-12)

class TestTransportFrame:

    '''Orthonormal, right-handed and twist-minimizing, which is what makes it a transport frame.'''

    def sweptSection(self, x, y, z, channelRadius = 0.002, numPoints = 64):

        numStations = len(x)
        geometry = circularInputs(numCrossSections = numStations, numCSPointsChannel = numPoints)
        radius = np.full(numStations, channelRadius)

        xChannel, yChannel, zChannel, _ = generateCrossSections(
            geometry, x, y, z, radius, 'circle')

        return np.stack([xChannel, yChannel, zChannel], axis = -1)

    def testTheSectionPlaneIsNormalToTheTangentOnACurvedPath(self):

        # A helical centerline: the tangent turns continuously, so a section that is not built
        # in the normal plane will show up immediately.
        numStations = 60
        angle = np.linspace(0.0, 2.0, numStations)
        x = 0.06 * np.cos(angle)
        y = 0.06 * np.sin(angle)
        z = np.linspace(0.0, 0.3, numStations)

        points = self.sweptSection(x, y, z)
        stations = np.stack([x, y, z], axis = -1)

        tangent = np.gradient(stations, axis = 0)
        tangent /= np.linalg.norm(tangent, axis = 1)[:, None]

        # Every offset from the centerline must be perpendicular to the local tangent.
        offsets = points - stations[None, :, :]
        alongTangent = np.einsum('psc,sc->ps', offsets, tangent)

        assert np.max(np.abs(alongTangent)) < 1e-9

    def testRadiusIsPreservedAroundACurve(self):

        numStations = 60
        angle = np.linspace(0.0, 2.0, numStations)
        x = 0.06 * np.cos(angle)
        y = 0.06 * np.sin(angle)
        z = np.linspace(0.0, 0.3, numStations)
        channelRadius = 0.002

        points = self.sweptSection(x, y, z, channelRadius = channelRadius)
        stations = np.stack([x, y, z], axis = -1)

        distance = np.linalg.norm(points - stations[None, :, :], axis = -1)

        assert np.max(np.abs(distance - channelRadius)) < 1e-12

    def testAPlanarCurveAcquiresNoTwist(self):

        # This is the property that separates a parallel transport frame from a Frenet frame.
        # For a curve lying in a plane, the frame must not rotate about the tangent, so a marked
        # point on the section stays on the same side of the curve all the way along.
        numStations = 80
        angle = np.linspace(0.0, np.pi, numStations)
        x = 0.06 * np.cos(angle)
        y = 0.06 * np.sin(angle)
        z = np.zeros(numStations)

        points = self.sweptSection(x, y, z)
        stations = np.stack([x, y, z], axis = -1)

        # The curve lies in z = 0, so its plane normal is z. Track one point's component along it.
        offsets = points - stations[None, :, :]
        outOfPlane = offsets[0, :, 2]

        # It may sit anywhere out of plane, but it must not drift as the curve bends.
        assert np.ptp(outOfPlane) < 1e-9

    def testAStraightCenterlineGivesAConstantFrame(self):

        numStations = 25
        x, y, z = straightCenterline(numStations)

        points = self.sweptSection(x, y, z)
        stations = np.stack([x, y, z], axis = -1)
        offsets = points - stations[None, :, :]

        # Every station's section is the same section, translated.
        assert np.max(np.abs(offsets - offsets[:, :1, :])) < 1e-12

class TestSingleStation:

    '''Asking for one station gives the same answer as asking for all of them.'''

    def testOneStationMatchesTheFullSweep(self):

        numStations = 30
        geometry = circularInputs(numCrossSections = numStations)
        x, y, z = straightCenterline(numStations)
        radius = np.linspace(0.0015, 0.0025, numStations)

        _, _, _, full = generateCrossSections(geometry, x, y, z, radius, 'circle')

        for station in (0, 7, numStations - 1):
            single = generateCrossSections(geometry, x, y, z, radius, 'circle', i = station)
            assert single['flowArea'][0] == pytest.approx(full['flowArea'][station], rel = 1e-12)
            assert single['wettedArea'][0]  == pytest.approx(full['wettedArea'][station],  rel = 1e-12)

class TestChannelTypeAliasing:

    '''A cross-section family that does not exist is refused rather than guessed.'''

    def testAnUnknownFamilyIsRefused(self):

        numStations = 10
        geometry = circularInputs(numCrossSections = numStations)
        x, y, z = straightCenterline(numStations)
        radius = np.full(numStations, 0.002)

        with pytest.raises(Exception, match = 'crossSectionStyle'):
            generateCrossSections(geometry, x, y, z, radius, 'hexagon')

class TestTurnAngle:

    '''The turn angle and bend radius feed the coolant pressure drop, so they are checked too.'''

    def testAStraightChannelHasNoTurn(self):

        numStations = 30
        geometry = circularInputs(numCrossSections = numStations)
        x, y, z = straightCenterline(numStations)
        radius = np.full(numStations, 0.002)

        heatTransfer = generateCrossSections(geometry, x, y, z, radius, 'circle')[3]

        interior = slice(1, -1)
        assert np.max(np.abs(heatTransfer['turnAngle'][interior])) < 1e-9

    def testACircularArcReportsItsOwnRadius(self):

        # A centerline bent into a circle of known radius must report that radius back.
        numStations = 200
        bendRadius = 0.05
        angle = np.linspace(0.0, np.pi / 2, numStations)
        x = bendRadius * np.cos(angle)
        y = bendRadius * np.sin(angle)
        z = np.zeros(numStations)

        geometry = circularInputs(numCrossSections = numStations)
        radius = np.full(numStations, 0.002)

        heatTransfer = generateCrossSections(geometry, x, y, z, radius, 'circle')[3]

        interior = slice(2, -2)
        reported = heatTransfer['radiusOfCurvature'][interior]

        assert np.allclose(reported, bendRadius, rtol = 1e-3), \
            f'reported {reported.min():.6f} to {reported.max():.6f} m against {bendRadius} m'

class TestRectangularProfile:

    '''The outline is closed, its corners exact, and its area the rounded rectangle's.'''

    def polygonArea(self, u, v):

        return 0.5 * abs(np.dot(v[:-1], u[1:]) - np.dot(u[:-1], v[1:]))

    def testItIsClosedWithTheRequestedPointCount(self):

        u, v = rectangularProfile(1e-3, 4e-3, 0.2e-3, 40)

        assert len(u) == len(v) == 40
        assert (u[0], v[0]) == (u[-1], v[-1])

    def testASharpOutlineEnclosesTheRectangleExactly(self):

        u, v = rectangularProfile(1e-3, 4e-3, 0.0, 40)

        assert self.polygonArea(u, v) == pytest.approx(4e-6, rel = 1e-13)
        for corner in ((-2e-3, -0.5e-3), (-2e-3, 0.5e-3), (2e-3, -0.5e-3), (2e-3, 0.5e-3)):
            assert np.min(np.hypot(u - corner[0], v - corner[1])) < 1e-15

    def testARoundedOutlineConvergesOnItsArea(self):

        exact = 1e-3 * 4e-3 - (4 - np.pi) * (0.3e-3)**2
        errors = [abs(self.polygonArea(*rectangularProfile(1e-3, 4e-3, 0.3e-3, count)) - exact) / exact
                  for count in (40, 160, 640)]

        assert all(later < earlier for earlier, later in zip(errors, errors[1:]))
        assert errors[-1] < 1e-4

    def testTheDepthRunsAlongUAndTheWidthAlongV(self):

        u, v = rectangularProfile(1e-3, 4e-3, 0.0, 40)

        assert np.ptp(u) == pytest.approx(4e-3, rel = 1e-14)
        assert np.ptp(v) == pytest.approx(1e-3, rel = 1e-14)
        assert u[0] == pytest.approx(-2e-3) and v[0] == 0.0

class TestWallNormalFrames:

    '''On a surface of revolution the frame normal is the wall normal, wrapped or not.'''

    def cone(self, wrapRate = 0.0, numStations = 80, halfAngle = np.deg2rad(20)):

        # A straight meridian at the half angle, offset from the axis; the wall normal is the
        # meridian's left normal, (-sin a, cos a) in (x, r)
        s = np.linspace(0.0, 0.2, numStations)
        x = s * np.cos(halfAngle)
        r = 0.05 + s * np.sin(halfAngle)
        azimuth = wrapRate * s
        return x, r * np.cos(azimuth), r * np.sin(azimuth), azimuth, halfAngle

    @pytest.mark.parametrize('wrapRate', [0.0, 3.0, 12.0])
    def testTheNormalIsTheWallNormal(self, wrapRate):

        x, y, z, azimuth, halfAngle = self.cone(wrapRate)
        tangent, normal, binormal = wallNormalFrames(x, y, z)

        expected = np.column_stack((-np.sin(halfAngle) * np.ones_like(x),
                                    np.cos(halfAngle) * np.cos(azimuth),
                                    np.cos(halfAngle) * np.sin(azimuth)))

        # Central differences inside, one-sided at the two ends
        alignment = np.abs(np.sum(normal * expected, axis = 1) - 1)
        assert np.max(alignment[1:-1]) < 1e-7
        assert np.max(alignment[[0, -1]]) < 1e-4

    def testTheFrameIsOrthonormalAndRightHanded(self):

        x, y, z, _, _ = self.cone(6.0)
        tangent, normal, binormal = wallNormalFrames(x, y, z)

        for a, b in ((tangent, normal), (tangent, binormal), (normal, binormal)):
            assert np.max(np.abs(np.sum(a * b, axis = 1))) < 1e-12
        assert np.allclose(np.cross(tangent, normal), binormal, atol = 1e-12)

class TestRectangularSweep:

    '''A rectangle is drawn with its depth on the wall normal and its width across the wall.'''

    def axialCenterline(self, numStations):

        '''A straight centerline along the nozzle axis, x, at a fixed radius, as the build lays one out.'''

        return np.linspace(0.0, 0.3, numStations), np.full(numStations, 0.06), np.zeros(numStations)

    def sweep(self, numStations = 30):

        geometry = circularInputs(numCrossSections = numStations, numCSPointsChannel = 40)
        geometry.channelType = 'rectangular'
        geometry.channelCornerRadius = 0.2e-3
        x, y, z = self.axialCenterline(numStations)
        depth, width = 3.0e-3, 1.2e-3

        xChannel, yChannel, zChannel, heatTransfer = generateCrossSections(
            geometry, x, y, z, np.full(numStations, depth / 2), 'rectangular',
            channelWidth = np.full(numStations, width))

        return (x, y, z), (xChannel, yChannel, zChannel), heatTransfer, depth, width

    def testTheExtentsLieOnTheWallNormalAndAcrossIt(self):

        # The centerline runs along x at y = 0.06, so the wall normal is +y and the width runs
        # along z, and every section lies in its own plane of constant x
        (x, y, z), (xChannel, yChannel, zChannel), _, depth, width = self.sweep()

        assert np.allclose(np.ptp(yChannel, axis = 0), depth, rtol = 1e-12)
        assert np.allclose(np.ptp(zChannel, axis = 0), width, rtol = 1e-12)
        assert np.max(np.abs(xChannel - x[None, :])) < 1e-15
        assert np.min(yChannel) == pytest.approx(0.06 - depth / 2, rel = 1e-14)

    def testOneStationMatchesTheFullSweep(self):

        numStations = 30
        _, _, full, depth, width = self.sweep(numStations)
        geometry = circularInputs(numCrossSections = numStations, numCSPointsChannel = 40)
        geometry.channelType, geometry.channelCornerRadius = 'rectangular', 0.2e-3
        x, y, z = self.axialCenterline(numStations)

        single = generateCrossSections(geometry, x, y, z, np.full(numStations, depth / 2), 'rectangular',
                                       i = 7, channelWidth = np.full(numStations, width))

        for key in ('flowArea', 'heatedArea', 'hydraulicDiameter', 'finHeight', 'finThickness'):
            assert single[key][0] == pytest.approx(full[key][7], rel = 1e-14), key

    def testARectangleWithoutAWidthIsRefused(self):

        numStations = 10
        geometry = circularInputs(numCrossSections = numStations)
        geometry.channelType = 'rectangular'
        x, y, z = straightCenterline(numStations)

        with pytest.raises(ValueError, match = 'channelWidth'):
            generateCrossSections(geometry, x, y, z, np.full(numStations, 1e-3), 'rectangular')

class TestHelicalPath:

    '''A helix at angle phi on a cylinder travels 1/cos(phi) times the axial length.'''

    @pytest.mark.parametrize('helixAngle', [15.0, 45.0, 70.0])
    def testThePathIsTheMeridianOverCosPhi(self, helixAngle):

        from NOVA.channelSections import loxodromeWrap

        numStations, radius, length = 400, 0.06, 0.3
        x = np.linspace(0.0, length, numStations)
        wrap = loxodromeWrap(x, np.full(numStations, radius), helixAngle)
        y, z = radius * np.cos(wrap), radius * np.sin(wrap)

        geometry = circularInputs(numCrossSections = numStations, numCSPointsChannel = 40)
        geometry.channelType, geometry.channelHelixAngle = 'helical', helixAngle
        _, _, _, heatTransfer = generateCrossSections(
            geometry, x, y, z, np.full(numStations, 1.0e-3), 'helical',
            channelWidth = np.full(numStations, 2.0e-3), ribThickness = np.full(numStations, 1.0e-3))

        # The last station repeats the segment before it, so the path is the first N - 1
        path = np.sum(heatTransfer['differentialPathLength'][:-1])

        assert path == pytest.approx(length / np.cos(np.deg2rad(helixAngle)), rel = 1e-4)

    def testTheLargestHelixLeavesTheMinimumRib(self):

        from NOVA.channelSections import helicalSpacing

        geometry = circularInputs(nChannel = 40)
        geometry.channelType, geometry.channelHelixAngle, geometry.channelAspectRatio = 'helical', 45.0, 1.5
        largest = getMaxChannelRadius(geometry, np.array([0.05]), 0)
        spacing = helicalSpacing(0.05 + geometry.hotWallThickness, 40, 45.0)

        assert largest == pytest.approx(1.5 * (spacing - geometry.infillThickness) / 2, rel = 1e-14)
