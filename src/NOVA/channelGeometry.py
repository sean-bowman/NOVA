
# -- NOVA: Cooling Channel Cross Sections -- #

'''

The three-dimensional shape of a cooling channel, built one cross section at a time.

A channel is a curve wrapped around the nozzle wall and a profile swept along it. This module
builds the profile and orients it. The curve itself is built elsewhere; what arrives here is a
centerline in three dimensions, a channel radius at each station, and the family of profile the
channel is drawn from.

A frame is constructed at every station from the local tangent, and the profile is drawn in the
plane normal to it. A circular profile is rotationally symmetric, so it rides a parallel transport
frame and is not rolled. A rectangular profile is not symmetric: its depth has to point along the
wall normal and its width across the wall, at every station, so it rides a frame built from the
wall normal instead (`wallNormalFrames`). A parallel transport frame drifts off the wall normal
wherever the centerline wraps.

Spirally fluted channels, a profile rolled about the tangent so its flutes run helically and
compressed toward a circle on the hot-wall side, are kept in `experimental/flutedChannels.py`
with the correlation they were rated by.

Two things are returned. The swept surface, as (x, y, z) arrays of shape (numCSPointsChannel,
numCrossSections), is the geometry. The section properties from `channelSections`, the areas
they make over each station's path length, and the turn angle and radius of curvature at each
station are what the thermal model needs. They are returned as a dictionary keyed the way that
model reads them.

----------------------------------------------------------------------
                        Geometry conventions
----------------------------------------------------------------------

Cooling channel geometry is three-dimensional and follows the convention of the rest of the
tool:

    - X is the direction of the outgoing fluid at the volute interface
    - Y is orthogonal to X in the plane of the volute scroll
    - Z completes the set and is the nozzle axis

Planar cross sections are therefore drawn in the YZ plane, which is what makes geometry
exported from here line up with the conventions of a CAD package.

All units are mass base SI:
    - Length [m]
    - Area   [m^2]
    - Angle  [rad] internally, [deg] where a configuration names one

Author: Sean Bowman

'''

from dataclasses import dataclass

import numpy as np

from .channelSections import (SECTIONFAMILIES, helicalSpacing, maxHalfExtent, rectangularWidth,
                              sectionProperties)
from .errors import GeometricConstraintError

@dataclass
class ChannelGeometryInputs:

    '''

    Everything the cross-section builder reads that is not passed to it directly.

    These are the channel definition and the resolution it is drawn at.

    Attributes:
    -----------
    numCrossSections : int
        Stations along the channel.
    numCSPointsChannel : int
        Points around one cross section.
    nChannel : int
        Channels around the nozzle, which sets how much of the annulus each one may occupy.
    channelType : str
        Cross-section family, one of channelSections.SECTIONFAMILIES.
    hotWallThickness : float
        Wall between the coolant and the exhaust [m].
    infillThickness : float
        Material left between adjacent channels [m]: the rib.
    channelCornerRadius : float
        Corner radius of a rectangular section [m]. Zero is a sharp corner.
    maxChannelAspectRatio : float
        Depth a rectangular section may reach, as a multiple of its width [-].
    maxChannelDepth : float
        Depth a rectangular or helical section may reach [m]. Infinite leaves the aspect ratio,
        or for a helix the rib, to limit it.
    channelHelixAngle : float
        Angle a helical channel runs at from the meridian [deg].
    channelAspectRatio : float
        Depth of a helical section as a multiple of its width [-].

    '''

    numCrossSections:     int   = 0
    numCSPointsChannel:   int   = 0
    nChannel:             int   = 0
    channelType:          str   = 'circle'
    hotWallThickness:     float = 0.0
    infillThickness:      float = 0.0
    channelCornerRadius:  float = 0.0
    maxChannelAspectRatio: float = 8.0
    maxChannelDepth:      float = float('inf')
    channelHelixAngle:    float = 0.0
    channelAspectRatio:   float = 1.0

def normalizeTangents(vectors: np.ndarray, quantity: str = 'channel tangent') -> np.ndarray:

    '''

    Unit vectors, with a zero-length one taking the direction of the nearest station that has one.

    Two stations that land on the same point leave a zero difference between them. The sizing
    march produces exactly that whenever it rebuilds one station's section from a two-point
    slice of the centerline, and dividing by that length gives a frame of NaN that carries into
    the section points. Taking the direction from the nearest station that has one keeps the
    frame finite and leaves every other station's direction untouched.

    Parameters:
    -----------
    vectors : numpy.ndarray
        Station directions, (N, k), before normalization.
    quantity : str
        What the vectors are, for the message if none of them has a length.

    Returns:
    --------
    numpy.ndarray
        Unit vectors, (N, k).

    Raises:
    -------
    GeometricConstraintError
        If every station sits on the same point, which leaves no direction to take.

    '''

    vectors = np.asarray(vectors, dtype = float).copy()
    lengths = np.linalg.norm(vectors, axis = 1)
    degenerate = np.flatnonzero(lengths == 0)

    if degenerate.size:
        valid = np.flatnonzero(lengths > 0)
        if valid.size == 0:
            raise GeometricConstraintError(
                message = f'Every station sits on the same point, so the {quantity} has no '
                          f'direction to take.',
                constraintType = 'degenerateCenterline', value = 0.0, limit = 0.0)
        nearest = valid[np.argmin(np.abs(valid[None, :] - degenerate[:, None]), axis = 1)]
        vectors[degenerate] = vectors[nearest]
        lengths = np.linalg.norm(vectors, axis = 1)

    return vectors / lengths[:, None]

def rectangularProfile(width: float, depth: float, cornerRadius: float, numPoints: int) -> tuple:

    '''

    Closed outline of a rectangle with rounded corners, centered on the origin.

    `u` runs across the depth, positive away from the hot wall, and `v` across the width. The
    outline starts and ends at the middle of the floor, u = -d/2, and runs counterclockwise with
    v to the right and u up. Points are spread over the perimeter in proportion to length, and
    every join between a straight run and a corner is a vertex, so a sharp corner is drawn exactly.

    Parameters:
    -----------
    width, depth : float
        Circumferential and radial extent [m].
    cornerRadius : float
        Corner radius [m], clamped to half the smaller side.
    numPoints : int
        Points in the outline, counting the repeated closing point.

    Returns:
    --------
    tuple
        (u, v) arrays of length numPoints [m].

    '''

    corner = min(float(cornerRadius), 0.5*min(width, depth))
    hw, hd = 0.5*width, 0.5*depth

    # Straight runs as (start, end) and corners as (center, first angle, last angle), in (v, u)
    pieces = [
        ('line', (0.0, -hd),               (hw - corner, -hd)),
        ('arc',  (hw - corner, -hd + corner), -0.5*np.pi, 0.0),
        ('line', (hw, -hd + corner),       (hw, hd - corner)),
        ('arc',  (hw - corner, hd - corner),  0.0, 0.5*np.pi),
        ('line', (hw - corner, hd),        (-hw + corner, hd)),
        ('arc',  (-hw + corner, hd - corner), 0.5*np.pi, np.pi),
        ('line', (-hw, hd - corner),       (-hw, -hd + corner)),
        ('arc',  (-hw + corner, -hd + corner), np.pi, 1.5*np.pi),
        ('line', (-hw + corner, -hd),      (0.0, -hd)),
    ]

    def length(piece):
        if piece[0] == 'line':
            return float(np.hypot(piece[2][0] - piece[1][0], piece[2][1] - piece[1][1]))
        return corner*(piece[3] - piece[2])

    pieces = [piece for piece in pieces if length(piece) > 0.0]
    lengths = np.array([length(piece) for piece in pieces])

    intervals = numPoints - 1
    if intervals < len(pieces):
        raise ValueError(f'A rectangular outline needs at least {len(pieces) + 1} points, got {numPoints}.')

    # One interval per piece, then the rest by largest remainder in proportion to length
    share = 1 + (intervals - len(pieces))*lengths/lengths.sum()
    counts = np.floor(share).astype(int)
    for k in np.argsort(counts - share)[:intervals - counts.sum()]:
        counts[k] += 1

    v, u = [], []
    for piece, count in zip(pieces, counts):
        fractions = np.arange(count)/count
        if piece[0] == 'line':
            (v0, u0), (v1, u1) = piece[1], piece[2]
            v.extend(v0 + (v1 - v0)*fractions)
            u.extend(u0 + (u1 - u0)*fractions)
        else:
            (vc, uc), first, last = piece[1], piece[2], piece[3]
            angles = first + (last - first)*fractions
            v.extend(vc + corner*np.cos(angles))
            u.extend(uc + corner*np.sin(angles))
    v.append(v[0])
    u.append(u[0])

    return np.array(u), np.array(v)

def wallNormalFrames(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> tuple:

    '''

    Frames whose normal is the wall normal, along a centerline riding a surface of revolution.

    The centerline is taken with x along the nozzle axis and (y, z) across it, as the channel
    build lays it out. The meridian it traces, (x, r) with r the distance from the axis, gives
    the wall normal in its own plane; rotated to the station's azimuth it is the wall normal in
    three dimensions. It is made orthogonal to the path tangent, which it already is for a
    centerline on a surface parallel to the wall, and the binormal completes the right-handed set.

    Parameters:
    -----------
    x, y, z : np.ndarray
        Centerline [m].

    Returns:
    --------
    tuple
        (tangent, normal, binormal), each (N, 3), unit length.

    '''

    stations = np.column_stack((x, y, z))
    tangent  = normalizeTangents(np.gradient(stations, axis = 0))

    radius  = np.hypot(y, z)
    azimuth = np.arctan2(z, y)
    meridian = normalizeTangents(np.column_stack((np.gradient(x), np.gradient(radius))),
                                 quantity = 'wall meridian')

    # The left normal of the meridian as it is traversed, which is the side the centerline was
    # offset to from the wall, rotated to the station's azimuth
    normalAxial, normalRadial = -meridian[:, 1], meridian[:, 0]
    normal = np.column_stack((normalAxial, normalRadial*np.cos(azimuth), normalRadial*np.sin(azimuth)))

    normal  -= np.sum(normal*tangent, axis = 1)[:, None]*tangent
    normal  /= np.linalg.norm(normal, axis = 1)[:, None]
    binormal = np.cross(tangent, normal)

    return tangent, normal, binormal

def generateCrossSections(geometry, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D,
                          channelRadius, crossSectionStyle, i: int = None, channelWidth = None,
                          ribThickness = None):

    '''

    (x,y,z)ChannelCenterline3D, channelRadius and channelWidth inputs are expected to be length of numCrossSections even
    when only generating a single station. channelRadius is the section's radial half-extent: a circle's radius, half a
    rectangle's depth. channelWidth is a rectangle's width and is not read for a circle. ribThickness is the rib at each
    station where it varies, as a helix's does; left out, the rib is the infill thickness.

    If i is specified, one cross section is generated at that station along (x,y,z)ChannelCenterline3D with the local
    channel radius, and only the heat transfer dictionary is returned.

    If i is not specified, the entire channel is generated, and the (x,y,z)Channel arrays are returned as well as the
    heat transfer dictionary.

    '''

    def findTurnAngleAndRadiusOfCurvature(i):

        '''

        Discretized momentum loss coefficient equation based on effective bend radius and turn angle:

        - turnAngle : angle between the two vectors defined by the three points in focus [rad]
        - L         : total length of segment in focus; distance between point 1 and 2 plus distance between 2 and 3 [m]
        - R         : effective bend radius; radius of circle that passes through the three points in focus [m]

        R = L / (2 * sin(turnAngle / 2))

        - D     : diameter of channel [m]
        - K_90  : K-factor for a 90 deg bend

        K_90 = 0.085 + 0.14 * (R / D)**-3

        0.085 represents a baseline loss for a very long-radius 90deg bend.
        The second term captures the sharp increase in losses as the bend becomes tighter (R/D gets smaller).
        Now we scale for the actual bend angle to get real K-factor:

        K_bend  : K-factor for any turn angle and effective bend radius

        K_bend = K_90 * (2 * turnAngle / pi)

        Expanded out:

        K_bend = (0.085 + 0.14 * (R / D)**-3) * (2 * turnAngle / pi)

        '''

        if i < 2:
            turnAngle = 0
            radiusOfCurvature = 1e12
        else:
            p1 = np.array([xChannelCenterline3D[i-2], yChannelCenterline3D[i-2], zChannelCenterline3D[i-2]])
            p2 = np.array([xChannelCenterline3D[i-1], yChannelCenterline3D[i-1], zChannelCenterline3D[i-1]])
            p3 = np.array([xChannelCenterline3D[i],   yChannelCenterline3D[i],   zChannelCenterline3D[i]])

            v1 = p2 - p1
            v2 = p3 - p2

            dotProduct = np.dot(v1, v2)
            norms      = np.linalg.norm(v1) * np.linalg.norm(v2)
            cosTheta   = np.clip(dotProduct / norms, -1, 1)

            turnAngle  = np.arccos(cosTheta)

            if turnAngle > 1e-12:
                radiusOfCurvature   = (differentialPathLength[i-2] + differentialPathLength[i-1]) / (2 * np.sin(turnAngle))
            else:
                radiusOfCurvature   = 1e12

        return turnAngle, radiusOfCurvature

    def buildFrames():

        '''

        Construct parallel transport frames along a 3D centerline curve.

        Computes tangent, normal, and binormal vectors at each station using the parallel
        transport algorithm. This provides a smooth, twist-minimizing coordinate frame that
        follows the curve without gimbal lock issues.

        N = number of stations
        M = number of points in a cross section

        Parameters:

            crossSectionPoints: (N,M,2) array
                Cross section coordinates in the yz plane (local +X is the cross section normal).

            xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D: (N,) arrays
                3D centerline coordinates, as passed to generateCrossSections.

            crossSectionRoll: (N,) array
                Roll angle (radians) to rotate about the local tangent at each station.

        Returns:

            sweptPoints: (N,M,3) array
                3D coordinates of all cross section points after sweeping and rolling.

        No gimbal lock this time hopefully. Rotations are done using quaternions conceptually
        but written in the Rodrigues' vector form. The orientiation results are stored as DCMs.
        Even though there are DCMs present, there should be no risk of gimbal lock because we
        are not storing any euler angles nor composing rotations by adding angles about fixed
        axes. Each rotation is done as a direct axis-angle rotation, which is the Rodrigues' form.

        This method is broken into two parts:
        1. build frames with buildFrames()
        2. place then roll cross sections with orientCrossSections()

        Author: Sean Bowman

        '''

        # Create tangent vectors for all stations
        stations    = np.column_stack((xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D))
        tangent     = np.gradient(stations, axis=0)
        tangent     = normalizeTangents(tangent)
        t0          = tangent[0]

        # Initialize parallel transport frame
        normal      = np.zeros((geometry.numCrossSections, 3))
        binormal    = np.zeros((geometry.numCrossSections, 3))
        up          = np.array([0.0, 1.0, 0.0])
        if abs(np.dot(t0, up)) > 0.95:
            up = np.array([0.0, 0.0, 1.0])
        b0          = np.cross(t0, up); b0 /= np.linalg.norm(b0)
        n0          = np.cross(b0, t0); n0 /= np.linalg.norm(n0)
        normal[0]   = n0
        binormal[0] = b0

        # Use the parallel transport algorithm to propogate rotation frames along the channel centerline
        for i in range(1, arrLen):
            rotationAxis            = np.cross(tangent[i-1], tangent[i]) # axis of rotation between two consecutive tangents
            rotationAxisMagnitude   = np.linalg.norm(rotationAxis) # magnitude of that axis
            if rotationAxisMagnitude < 1e-12: # if consectuve tangents are almost identical, reuse previous frame
                normal[i]   = normal[i-1]
                binormal[i] = binormal[i-1]
            else:
                rotationAxis       /= rotationAxisMagnitude
                rotationAngleCosine = np.clip(np.dot(tangent[i-1], tangent[i]), -1.0, 1.0) # cosine of the rotation angle
                rotationAngle       = np.arctan2(rotationAxisMagnitude, rotationAngleCosine) # actual rotation angle between consecutive tangents
                # Rogrigues notation for normal and binormal
                normal[i]   = (normal[i-1]*np.cos(rotationAngle)
                            + np.cross(rotationAxis, normal[i-1])*np.sin(rotationAngle)
                            + rotationAxis*np.dot(rotationAxis, normal[i-1])*(1-np.cos(rotationAngle)))
                binormal[i] = (binormal[i-1]*np.cos(rotationAngle)
                            + np.cross(rotationAxis, binormal[i-1])*np.sin(rotationAngle)
                            + rotationAxis*np.dot(rotationAxis, binormal[i-1])*(1-np.cos(rotationAngle)))
            # re-orthonormalize to prevent round off drift
            binormal[i] = np.cross(tangent[i], normal[i]); binormal[i] /= np.linalg.norm(binormal[i])
            normal[i]   = np.cross(binormal[i], tangent[i]); normal[i] /= np.linalg.norm(normal[i])

            # prevent 180 flips
            if np.dot(normal[i], normal[i-1]) < 0:
                binormal[i] = -binormal[i]
                normal[i]   = -normal[i]

        return stations, tangent, normal, binormal

    def orientCrossSections(stations: np.ndarray, crossSectionPoints: np.ndarray, crossSectionRoll: np.ndarray) -> np.ndarray:

        '''

        Sweep 2D cross sections along a 3D centerline, applying roll and placing in 3D space.

        Takes parallel transport frames from `buildFrames()`, applies roll rotation about each
        tangent vector, then transforms 2D cross section points (defined in local yz plane)
        into global 3D coordinates at each station.

        - N = number of stations
        - M = number of points in a cross section

        ### Parameters

            crossSectionPoints: (N,M,2) array
                Cross section coordinates in the yz plane (local +X is the cross section normal).

            xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D: (N,) arrays
                3D centerline coordinates, as passed to generateCrossSections.

            crossSectionRoll: (N,) array
                Roll angle (radians) to rotate about the local tangent at each station.

        Returns:

        `sweptPoints`: `(N,M,3) array` - 3D coordinates of all cross section points after sweeping and rolling

        ### Notes

        - Uses closure variables `tangent`, `normal`, and `binormal` from `buildFrames()`.
        - Applies roll using Rodrigues' rotation formula about the tangent axis.
        - Adds pi to each roll angle to orient cross sections correctly.
        - Constructs local-to-global rotation matrix R = [tangent, normal, binormal] at each station.
        - Cross section points are embedded as (0, y, z) in local coordinates before transformation.

        ---

        Author: Cam'ron Valliere
        Date:   2025

        '''

        # Apply roll angles about the tanget vectors
        def rollAboutAxis(v, axis, angle):
            axis /= np.linalg.norm(axis) + 1e-15
            return (v*np.cos(angle)
                    + np.cross(axis, v)*np.sin(angle)
                    + axis*np.dot(axis, v)*(1-np.cos(angle)))

        # Only the stations this call builds carry a frame: the sizing march asks for one station
        # at a time while the roll array is the whole channel's, and rolling a frame that was
        # never built leaves a zero vector to re-orthonormalize
        for i in range(arrLen):
            rollAngle   = crossSectionRoll[i] + np.pi
            normal[i]   = rollAboutAxis(normal[i], tangent[i], rollAngle)
            binormal[i] = rollAboutAxis(binormal[i], tangent[i], rollAngle)

            # re-orthonormalize to prevent round off drift
            b = np.cross(tangent[i], normal[i]); b /= np.linalg.norm(b)
            n = np.cross(b, tangent[i]);         n /= np.linalg.norm(n)
            normal[i], binormal[i] = n, b

        # Sweep cross sections along the centerline
        sweptPoints = np.empty((arrLen, geometry.numCSPointsChannel, 3))
        for i in range(arrLen):
            crossSection = crossSectionPoints[i] # current station's cross section's 2D coordinates
            xyzLocal = np.column_stack([np.zeros(geometry.numCSPointsChannel), crossSection[:, 0], crossSection[:, 1]]) # current station's cross section's 3D coordinates
            # Local to global rotation matrix for this station
            R = np.column_stack([tangent[i], normal[i], binormal[i]])
            sweptPoints[i] = xyzLocal @ R.T + stations[i]

        return sweptPoints

    # Input validation
    if crossSectionStyle not in SECTIONFAMILIES:
        raise ValueError(f"Unknown crossSectionStyle '{crossSectionStyle}'; the package builds "
                         f"{SECTIONFAMILIES}.")

    # Parse input mode: the whole channel, or the one station the sizing march asks for
    if i is None:
        fullSweep = True
        arrLen = geometry.numCrossSections
    else:
        fullSweep = False
        arrLen = 1
        j = i

    # Initialize
    xCircle, yCircle                                                                            \
        = [np.zeros((geometry.numCSPointsChannel, arrLen)) for _ in range(2)]
    turnAngle, radiusOfCurvature                                                                \
        = [np.zeros((arrLen))                          for _ in range(2)]

    differentialPathLength  = np.sqrt(np.diff(xChannelCenterline3D)**2 + np.diff(yChannelCenterline3D)**2 + np.diff(zChannelCenterline3D)**2)
    differentialPathLength  = np.append(differentialPathLength, differentialPathLength[-1])

    # The coolant enters at the last station and marches toward the first, so its distance along
    # the channel from the inlet manifold accumulates backwards. The entrance correction on the
    # coolant side reads it, and the sizing march cannot work it out from one station.
    distanceFromInlet       = np.flip(np.cumsum(np.flip(differentialPathLength)))

    # A circular section is rotationally symmetric, so it takes no roll about the path tangent.
    crossSectionRoll        = np.zeros(geometry.numCrossSections)

    crossSectionAngles      = np.linspace(0,      2*np.pi, geometry.numCSPointsChannel)

    for i in range(arrLen):

        if fullSweep:

            j = i

        turnAngle[i], radiusOfCurvature[i] = findTurnAngleAndRadiusOfCurvature(j)

    stations, tangent, normal, binormal = buildFrames()

    # -- circles -- #

    for i in range(arrLen):

        if fullSweep:

            j = i

        xCircle[:,i] = channelRadius[j] * np.sin(crossSectionAngles) # z coords in 3d
        yCircle[:,i] = channelRadius[j] * np.cos(crossSectionAngles) # y coords in 3d

    # Sweep the circular sections along the centerline
    allCircleChannelPoints = orientCrossSections(stations, np.stack((yCircle, xCircle), axis=-1).transpose(1, 0, 2), crossSectionRoll)
    xChannel = allCircleChannelPoints[:, :, 0].T
    yChannel = allCircleChannelPoints[:, :, 1].T
    zChannel = allCircleChannelPoints[:, :, 2].T

    # -- Finish -- #

    # The section at the stations drawn, and the areas it makes over each station's path
    stationIndex = np.arange(arrLen) if fullSweep else np.array([j])
    if crossSectionStyle == 'circle':
        section = sectionProperties(crossSectionStyle, channelRadius[stationIndex])
    else:
        if channelWidth is None:
            raise ValueError(f"A '{crossSectionStyle}' section needs channelWidth at every station.")
        rib = geometry.infillThickness if ribThickness is None else np.asarray(ribThickness)[stationIndex]
        section = sectionProperties(crossSectionStyle, channelRadius[stationIndex],
                                    width = np.asarray(channelWidth)[stationIndex],
                                    cornerRadius = geometry.channelCornerRadius,
                                    ribThickness = rib)
    pathLength   = differentialPathLength[stationIndex]

    # A rectangle or a helix is drawn on the wall normal, depth outward and width across the wall
    if fullSweep and crossSectionStyle != 'circle':
        _, wallNormal, wallBinormal = wallNormalFrames(xChannelCenterline3D, yChannelCenterline3D,
                                                       zChannelCenterline3D)
        xChannel, yChannel, zChannel = [np.zeros((geometry.numCSPointsChannel, arrLen)) for _ in range(3)]
        for k in range(arrLen):
            u, v = rectangularProfile(section.width[k], section.depth[k], section.cornerRadius[k],
                                      geometry.numCSPointsChannel)
            xChannel[:, k] = xChannelCenterline3D[k] + u*wallNormal[k, 0] + v*wallBinormal[k, 0]
            yChannel[:, k] = yChannelCenterline3D[k] + u*wallNormal[k, 1] + v*wallBinormal[k, 1]
            zChannel[:, k] = zChannelCenterline3D[k] + u*wallNormal[k, 2] + v*wallBinormal[k, 2]

    heatTransferDict = {}
    heatTransferDict["flowArea"]               = section.flowArea
    heatTransferDict["wettedArea"]             = section.wettedPerimeter * pathLength
    heatTransferDict["heatedArea"]             = section.heatedPerimeter * pathLength
    heatTransferDict["hydraulicDiameter"]      = section.hydraulicDiameter
    heatTransferDict["finHeight"]              = section.finHeight
    heatTransferDict["finThickness"]           = section.finThickness
    heatTransferDict["differentialPathLength"] = pathLength
    heatTransferDict["distanceFromInlet"]      = distanceFromInlet if fullSweep                                                  else distanceFromInlet[stationIndex]
    heatTransferDict["turnAngle"]              = turnAngle
    heatTransferDict["radiusOfCurvature"]      = radiusOfCurvature

    if fullSweep:

        return xChannel, yChannel, zChannel, heatTransferDict

    else:

        return heatTransferDict

def getMaxChannelRadius(geometry, rNozzle, i):

    '''

    Returns the largest radial half-extent a channel may take at station i along rNozzle: the
    radius of the largest circle that packs between its neighbors, half the deepest rectangle the
    aspect ratio and depth limits allow, or half the depth of the widest helical channel that
    leaves the minimum rib. A rectangle's width is taken here at the hot wall
    radius plus the wall thickness, which is within t(1 - cos a) of the offset cold wall on a wall
    at angle a; the sizing solve itself takes it at the offset cold wall.

    Author: Isabella Duprey-Churn
    Date:   4/28/2026

    '''

    if geometry.channelType == 'rectangular':
        width = rectangularWidth(rNozzle[i] + geometry.hotWallThickness, geometry.nChannel,
                                 geometry.infillThickness)
        return float(maxHalfExtent('rectangular', width, geometry.maxChannelAspectRatio,
                                   geometry.maxChannelDepth))

    if geometry.channelType == 'helical':
        spacing = helicalSpacing(rNozzle[i] + geometry.hotWallThickness, geometry.nChannel,
                                 geometry.channelHelixAngle)
        return float(maxHalfExtent('helical', spacing - geometry.infillThickness,
                                   geometry.channelAspectRatio, geometry.maxChannelDepth))

    offsetHotWallThickness = geometry.hotWallThickness - geometry.infillThickness
    arcAngle = 2*np.pi / geometry.nChannel
    theta = arcAngle/2
    R = rNozzle[i] + offsetHotWallThickness
    r = R*np.sin(theta) / (1 - np.sin(theta))
    maxCircleChannelRadius = r - geometry.infillThickness / 2

    return maxCircleChannelRadius
