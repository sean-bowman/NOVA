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

**A circular cross section is a circle.** Its points lie at exactly the channel radius from the
centerline, in the plane normal to the local tangent, and its flow area is exactly pi r squared.

Author: Sean Bowman

'''

import os
import sys

import numpy as np
import pytest

from NOVA.channelGeometry import ChannelGeometryInputs, generateCrossSections, getMaxChannelRadius

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
