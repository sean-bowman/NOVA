
# -- NOVA: Cooling Channel Cross Sections -- #

'''

The three-dimensional shape of a cooling channel, built one cross section at a time.

A channel is a curve wrapped around the nozzle wall and a profile swept along it. This module
builds the profile and orients it. The curve itself is built elsewhere; what arrives here is a
centerline in three dimensions, a channel radius at each station, and the family of profile the
channel is drawn from.

A frame is constructed at every station from the local tangent, and the profile is drawn in the
plane normal to it. A circular profile is rotationally symmetric, so it is not rolled.

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

from .channelSections import SECTIONFAMILIES, sectionProperties

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
        Cross-section family: 'circle'.
    hotWallThickness : float
        Wall between the coolant and the exhaust [m].
    infillThickness : float
        Material left between adjacent channels [m].

    '''

    numCrossSections:     int   = 0
    numCSPointsChannel:   int   = 0
    nChannel:             int   = 0
    channelType:          str   = 'circle'
    hotWallThickness:     float = 0.0
    infillThickness:      float = 0.0

def generateCrossSections(geometry, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D,
                          channelRadius, crossSectionStyle, i: int = None):

    '''

    (x,y,z)ChannelCenterline3D and channelRadius inputs are expected to be length of numCrossSections even when only
    generating a single station

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
        tangent    /= np.linalg.norm(tangent, axis=1)[:, None]
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

        for i, rollAngle in enumerate(crossSectionRoll):
            rollAngle  += np.pi
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
    section      = sectionProperties(crossSectionStyle, channelRadius[stationIndex])
    pathLength   = differentialPathLength[stationIndex]

    heatTransferDict = {}
    heatTransferDict["flowArea"]               = section.flowArea
    heatTransferDict["wettedArea"]             = section.wettedPerimeter * pathLength
    heatTransferDict["heatedArea"]             = section.heatedPerimeter * pathLength
    heatTransferDict["hydraulicDiameter"]      = section.hydraulicDiameter
    heatTransferDict["finHeight"]              = section.finHeight
    heatTransferDict["finThickness"]           = section.finThickness
    heatTransferDict["differentialPathLength"] = pathLength
    heatTransferDict["turnAngle"]              = turnAngle
    heatTransferDict["radiusOfCurvature"]      = radiusOfCurvature

    if fullSweep:

        return xChannel, yChannel, zChannel, heatTransferDict

    else:

        return heatTransferDict

def getMaxChannelRadius(geometry, rNozzle, i):

    '''

    Returns the maximum circular channel radius at station i along rNozzle

    Author: Isabella Duprey-Churn
    Date:   4/28/2026

    '''

    offsetHotWallThickness = geometry.hotWallThickness - geometry.infillThickness
    arcAngle = 2*np.pi / geometry.nChannel
    theta = arcAngle/2
    R = rNozzle[i] + offsetHotWallThickness
    r = R*np.sin(theta) / (1 - np.sin(theta))
    maxCircleChannelRadius = r - geometry.infillThickness / 2

    return maxCircleChannelRadius
