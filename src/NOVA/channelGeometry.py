# -- NOVA: Cooling Channel Cross Sections -- #

'''

The three-dimensional shape of a cooling channel, built one cross section at a time.

A channel is a curve wrapped around the nozzle wall and a profile swept along it. This module
builds the profile and orients it. The curve itself is built elsewhere; what arrives here is a
centreline in three dimensions, a channel radius at each station, and the family of profile the
channel is drawn from.

A frame is constructed at every station from the local tangent, and the profile is drawn in the
plane normal to it. A fluted profile is additionally rolled about the tangent as it advances,
which is what makes the flutes helical. A circular profile is rotationally symmetric, so it is
not rolled.

Where a channel would otherwise print unsupported, the flutes are locally compressed toward a
circle. That blend is what `conditionalGaussian` applies, and the stations it applies to come
from the printability audit that runs before this module is called.

Two things are returned. The swept surface, as (x, y, z) arrays of shape
(numCSPointsChannel, numCrossSections), is the geometry. The cross-sectional area, wetted
surface area, turn angle and radius of curvature at each station are what the thermal model
needs, and are returned as a dictionary keyed the way that model reads them.

----------------------------------------------------------------------
                        Geometry conventions
----------------------------------------------------------------------

Cooling channel geometry is three-dimensional and follows the convention of the rest of the
tool:

    - X is the direction of the outgoing fluid at the volute interface
    - Y is orthogonal to X in the plane of the volute scroll
    - Z completes the set and is the nozzle axis

Planar cross sections are therefore drawn in the YZ plane, which is what makes geometry exported
from here line up with the conventions of a CAD package.

All units are mass base SI:
    - Length [m]
    - Area   [m^2]
    - Angle  [rad] internally, [deg] where a configuration names one

Author: Sean Bowman

'''

import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from joblib import Parallel, delayed, cpu_count
from scipy.spatial import KDTree
from tqdm import tqdm

from .utils import DCM

@dataclass
class ChannelGeometryInputs:

    '''

    Everything the cross-section builder reads that is not passed to it directly.

    These are the channel definition and the resolution it is drawn at, plus two arrays that the
    surrounding run fills in and this module only reads: the nozzle wall point cloud the
    compression search queries, and the stations the printability audit marked unsupported.

    Attributes:
    -----------
    numCrossSections : int
        Stations along the channel.
    numCSPointsChannel : int
        Points around one cross section.
    nChannel : int
        Channels around the nozzle, which sets how much of the annulus each one may occupy.
    channelType : str
        'circle' or 'fluted'. 'dataMap' is treated as fluted, since it differs only in how the
        coolant side is correlated.
    hotWallThickness : float
        Wall between the coolant and the exhaust [m].
    infillThickness : float
        Material left between adjacent channels [m].
    numFlutes : int
        Flutes around a fluted cross section.
    fluteAmplitudeCoef : float
        Flute amplitude as a fraction of the channel radius [-].
    fluteHelixAngle : float
        Helix angle the flutes are rolled through [deg]. NaN for a channel with no flutes.
    interfaceLength : float
        Length of the circular run at each volute interface [m].
    numInletInterfaceCS : int
        Stations in the inlet interface.
    numReturnInterfaceCS : int
        Stations in the return interface.
    printabilityCheck : str
        'on' compresses flutes toward a circle where the channel would print unsupported.
    nonPrintableIndices : Any
        Stations the printability audit marked, which the compression blends across.
    allNozzlePoints : Any
        Nozzle wall point cloud the compression search queries for the nearest wall point.

    '''

    numCrossSections:     int   = 0
    numCSPointsChannel:   int   = 0
    nChannel:             int   = 0
    channelType:          str   = 'circle'
    hotWallThickness:     float = 0.0
    infillThickness:      float = 0.0
    numFlutes:            float = float('nan')
    fluteAmplitudeCoef:   float = float('nan')
    fluteHelixAngle:      float = float('nan')
    interfaceLength:      float = 0.0
    numInletInterfaceCS:  int   = 0
    numReturnInterfaceCS: int   = 0
    printabilityCheck:    str   = 'off'
    nonPrintableIndices:  Any   = field(default_factory = list)
    allNozzlePoints:      Any   = None


def generateCrossSections(geometry, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D,
                          channelRadius, crossSectionStyle, i: int = None):

    '''

    (x,y,z)ChannelCenterline3D and channelRadius inputs are expected to be length of numCrossSections even when only
    generating a single station

    If i is specified, one cross section in generated at that station along (x,y,z)ChannelCenterline3D with local channel
    radius. Gaussian compression of flutes is applied ambiguously i.e. there is no searching for the closest point.
    Only the heat transfer dictionary is returned.

    If i is not specified, the entire channel is generated. Nozzle search is used for the gaussian compression index,
    which expects geometry.allNozzlePoints to exist. The (x,y,z)Channel arrays are returned as well as the heat transfer
    dictionary.

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

    def conditionalGaussian(iterator: int, gaussianCurve):

        '''

        Wrapper around the Gaussian curve cross section compression logic for individualized debugging.

        '''

        numInterfaceCrossSections      = int(np.floor(geometry.interfaceLength / (totalPathLength / geometry.numCrossSections)))
        numInterfaceBlendCrossSections = max(3, int(np.floor(10e-3 / (totalPathLength / geometry.numCrossSections))))
        ampInterfaceBlendUp            = np.linspace(0, 1, numInterfaceBlendCrossSections + 1)
        ampInterfaceBlendDown          = np.linspace(1, 0, numInterfaceBlendCrossSections + 1)

        i = iterator
        currentCompression = 0

        match geometry.printabilityCheck:

            case 'on':

                # -- Find non-printable indices -- #

                # Figure out how many different places need to be un-fluted for printability
                indexGap = 5
                splitIndex = []
                numCompressions = len([val for val in np.diff(geometry.nonPrintableIndices) if val > indexGap]) + 1
                compressionGroups = []

                # Split the non-printable indices into groups for each section of un-fluted channel
                for i in range(len(geometry.nonPrintableIndices)-1):
                    currentGap = geometry.nonPrintableIndices[i+1] - geometry.nonPrintableIndices[i]
                    if currentGap > indexGap:
                        # Store each split identifier
                        splitIndex.append(i+1)

                # Separate the split groups into elements of a list
                # First section
                compressionGroups.append(geometry.nonPrintableIndices[:splitIndex[0]])
                # Middle sections
                for i in range(numCompressions-2):
                    compressionGroups.append(geometry.nonPrintableIndices[splitIndex[i]:splitIndex[i+1]])
                # Final section
                compressionGroups.append(geometry.nonPrintableIndices[splitIndex[-1]:])

                # Check for case where printability compression goes to the boundary of a channel
                if any(numInterfaceCrossSections + numInterfaceBlendCrossSections > index for index in geometry.nonPrintableIndices):
                    numInterfaceCrossSections = compressionGroups[0][-1]
                    # This compression is handled now at the channel boundary, remove a counter for the number of compressions
                    numCompressions -= 1
                    # Remove the reference to the first region that is already used
                    compressionGroups = compressionGroups[1:]

                # -- Apply circle blends to problem areas -- #

                # Check for which (if any) compression regions for printability we are in
                for j in range(numCompressions):

                    if any(i >= index for index in compressionGroups[j]):

                        currentCompression = j

                # -- Handle inlet and outlet of channels -- #

                # Circular outlet region
                if i <= geometry.numReturnInterfaceCS + numInterfaceCrossSections:

                    amplitudeGausFluted = np.zeros((geometry.numCSPointsChannel))

                # Blend from circular outlet region to beginning of fluted region
                elif (i > geometry.numReturnInterfaceCS + numInterfaceCrossSections) and (i <= geometry.numReturnInterfaceCS + numInterfaceCrossSections + numInterfaceBlendCrossSections):

                    amplitudeGausFluted = fluteAmplitude[i] * gaussianCurve * ampInterfaceBlendUp[i - int(geometry.numReturnInterfaceCS + numInterfaceCrossSections)]

                # Blend from end of fluted region to beginning of circular outlet region
                elif (i > geometry.numCrossSections - numInterfaceCrossSections - geometry.numInletInterfaceCS - numInterfaceBlendCrossSections) and (i <= geometry.numCrossSections - numInterfaceCrossSections - geometry.numInletInterfaceCS):

                    amplitudeGausFluted = fluteAmplitude[i] * gaussianCurve * ampInterfaceBlendDown[i - int(geometry.numCrossSections - numInterfaceCrossSections - geometry.numInletInterfaceCS - numInterfaceBlendCrossSections)]

                # Circular inlet region
                elif i > geometry.numCrossSections - numInterfaceCrossSections - geometry.numInletInterfaceCS:

                    amplitudeGausFluted = np.zeros((geometry.numCSPointsChannel))

                # -- Compress to circles where applicable for printability and blend between flutes and circles accordingly -- #

                # In between circular inlet and oulet regions
                elif (i > geometry.numReturnInterfaceCS + numInterfaceCrossSections + numInterfaceBlendCrossSections) and (i <= geometry.numCrossSections - numInterfaceCrossSections - geometry.numInletInterfaceCS - numInterfaceBlendCrossSections):

                        # Un-fluted region identified by printability audit
                        if (i > compressionGroups[currentCompression][0]) and (i < compressionGroups[currentCompression][-1]):

                            amplitudeGausFluted = np.zeros((geometry.numCSPointsChannel))

                        # Blending region associated with the inlet of current compression
                        elif (i > compressionGroups[currentCompression][0] - numInterfaceBlendCrossSections) and (i <= compressionGroups[currentCompression][0]):

                            amplitudeGausFluted = fluteAmplitude[i] * gaussianCurve * ampInterfaceBlendDown[i - (compressionGroups[currentCompression][0] - numInterfaceBlendCrossSections)]

                        # Blending region associated with the outlet of current compression
                        elif (i >= compressionGroups[currentCompression][-1]) and (i < compressionGroups[currentCompression][-1] + numInterfaceBlendCrossSections):

                            amplitudeGausFluted = fluteAmplitude[i] * gaussianCurve * ampInterfaceBlendUp[i - (compressionGroups[currentCompression][-1] + numInterfaceBlendCrossSections)]

                        # Otherwise, it's fluted
                        else:

                            amplitudeGausFluted = fluteAmplitude[i] * gaussianCurve

            case 'off':

                # Circlular outlet region
                if i <= geometry.numReturnInterfaceCS + numInterfaceCrossSections:
                    amplitudeGausFluted = np.zeros((geometry.numCSPointsChannel))
                    isCircle = 1
                # Blend from end of circular outelt region to beginning of fluted region
                elif (i > geometry.numReturnInterfaceCS + numInterfaceCrossSections) and (i <= geometry.numReturnInterfaceCS + numInterfaceCrossSections + numInterfaceBlendCrossSections):
                    amplitudeGausFluted = fluteAmplitude[i] * gaussianCurve * ampInterfaceBlendUp[i - int(geometry.numReturnInterfaceCS + numInterfaceCrossSections)]
                    isCircle = 1 - ampInterfaceBlendUp[i-int(geometry.numReturnInterfaceCS + numInterfaceCrossSections)]
                # From beginning to end of fluted region
                elif (i > geometry.numReturnInterfaceCS + numInterfaceCrossSections + numInterfaceBlendCrossSections) and (i <= geometry.numCrossSections - numInterfaceCrossSections - geometry.numInletInterfaceCS - numInterfaceBlendCrossSections):
                    amplitudeGausFluted = fluteAmplitude[i] * gaussianCurve
                    isCircle = 0
                # Blend from end of fluted region to beginning of circular inlet region
                elif (i > geometry.numCrossSections - numInterfaceCrossSections - geometry.numInletInterfaceCS - numInterfaceBlendCrossSections) and (i <= geometry.numCrossSections - numInterfaceCrossSections - geometry.numInletInterfaceCS):
                    amplitudeGausFluted = fluteAmplitude[i] * gaussianCurve * ampInterfaceBlendDown[i - int(geometry.numCrossSections - numInterfaceCrossSections - geometry.numInletInterfaceCS - numInterfaceBlendCrossSections)]
                    isCircle = 1 - ampInterfaceBlendDown[i - int(geometry.numCrossSections - numInterfaceCrossSections - numInterfaceBlendCrossSections - geometry.numInletInterfaceCS)]
                # Cirlular inlet region
                elif i > geometry.numCrossSections - numInterfaceCrossSections - geometry.numInletInterfaceCS:
                        amplitudeGausFluted = np.zeros((geometry.numCSPointsChannel))
                        isCircle = 1

        return amplitudeGausFluted, isCircle

    def flutedCrossSection(i):

        '''
        Names:
            > Wave         - Unwrapped cross sections plotted in the (x, y) plane as (theta, r)
            > Fully Fluted - Polar cross sections that are fluted around the entire circumference
            > Gaus Fluted  - Polar cross sections that are fluted on one side and flattened on the other side by a Gaussian curve
        '''

        amplitudeFullyFluted   = np.ones((1,geometry.numCSPointsChannel)) * fluteAmplitude[i]
        waveFullyFluted        = np.ones((1,geometry.numCSPointsChannel)) * channelRadius[i] \
                                        + amplitudeFullyFluted * np.sin(geometry.numFlutes * crossSectionAngles)
        xFullyFluted           = -(waveFullyFluted) * np.sin(crossSectionAngles)
        yFullyFluted           = -(waveFullyFluted) * np.cos(crossSectionAngles)
        zAllZeros              = np.zeros_like(xFullyFluted)

        valueMatrix = [zAllZeros[0], yFullyFluted[0], xFullyFluted[0]]
        eulerAngles = [crossSectionRoll[i], 0, 0]
        _, yFullyFlutedRolled, zFullyFlutedRolled \
            = DCM(eulerAngles, valueMatrix, transpose = True, rotationOrder = 'yzx')

        # Define cross sections in polar coordinates
        polarRadius        = np.sqrt(zFullyFlutedRolled**2 + yFullyFlutedRolled**2)
        polarAngles        = np.arctan2(zFullyFlutedRolled, yFullyFlutedRolled)

        if compressionSearch == 'on':
            shiftedPolarAngles = np.roll(gaussianCurveRange, -(geometry.numCSPointsChannel - int(compressianIndex[i]) - 1))
            gaussianCurve = ((1/np.sqrt(2*np.pi)*np.exp(-(shiftedPolarAngles)**2/(np.pi/2)))/.4)
        else:
            gaussianCurve = ((1/np.sqrt(2*np.pi)*np.exp(-(gaussianCurveRange)**2/(np.pi/2)))/.4)

        amplitudeGausFluted    = fluteAmplitude[i] * gaussianCurve
        waveRadiusScaled       = (polarRadius - channelRadius[i]) / fluteAmplitude[i]
        waveGausFluted         = waveRadiusScaled * amplitudeGausFluted + channelRadius[i]
        xGausFluted            = waveGausFluted * np.sin(polarAngles)
        yGausFluted            = waveGausFluted * np.cos(polarAngles)

        if compressionSearch == 'on':
            amplitudeGausFluted, isCircle = conditionalGaussian(i,gaussianCurve)
        else:
            isCircle = 0

        waveRadiusScaled = (polarRadius - channelRadius[i]) / fluteAmplitude[i]
        waveGausFluted   = waveRadiusScaled * amplitudeGausFluted + channelRadius[i]
        xGausFluted      = waveGausFluted * np.sin(polarAngles)
        yGausFluted      = waveGausFluted * np.cos(polarAngles)
        gausFlutedCSA    = abs(np.trapz(yGausFluted, xGausFluted))

        differentialCircumference = np.zeros(geometry.numCSPointsChannel)
        for k in range(geometry.numCSPointsChannel-1):
            differentialCircumference[k] = np.sqrt((xGausFluted[k+1] - xGausFluted[k])**2 + (yGausFluted[k+1] - yGausFluted[k])**2)
        gausFlutedCircumference = sum(differentialCircumference)
        gausFlutedSA = gausFlutedCircumference * differentialPathLength[i]

        return xGausFluted, yGausFluted, gausFlutedCSA, gausFlutedSA, isCircle

    # Input validation
    if crossSectionStyle == 'dataMap':
        crossSectionStyle = 'fluted'
    if crossSectionStyle.lower() != 'fluted' and crossSectionStyle != 'circle':
        raise Exception("Please specify crossSectionStyle 'circle', 'fluted', or 'dataMap'.")

    if crossSectionStyle.lower() == 'fluted':
        # The flute profile is built by scaling a wave by its amplitude and normalising by the
        # same amplitude, which is singular at zero. A section of no amplitude is a circle, so
        # ask for one rather than for a flute that has none.
        if not np.isfinite(geometry.fluteAmplitudeCoef) or geometry.fluteAmplitudeCoef <= 0:
            raise ValueError(
                f'fluteAmplitudeCoef must be positive for a fluted cross section, got '
                f'{geometry.fluteAmplitudeCoef}. Use crossSectionStyle "circle" for an unfluted channel.')
        if not np.isfinite(geometry.numFlutes) or geometry.numFlutes < 3:
            raise ValueError(
                f'numFlutes must be at least 3 for a fluted cross section, got {geometry.numFlutes}')

    # Parse input mode
    if i == None:
        compressionSearch = 'on'
        arrLen = geometry.numCrossSections
    else:
        compressionSearch = 'off'
        arrLen = 1
        j = i

    # Initialize
    xCircle, yCircle, xGausFluted, yGausFluted                                                  \
        = [np.zeros((geometry.numCSPointsChannel, arrLen)) for _ in range(4)]       
    circleCSA, circleSA, gausFlutedCSA, gausFlutedSA,                                           \
    isCircle, turnAngle, radiusOfCurvature                                                      \
        = [np.zeros((arrLen))                          for _ in range(7)]

    fluteAmplitude          = geometry.fluteAmplitudeCoef * channelRadius
    flutePitch              = 2*np.pi * channelRadius / (np.tan(np.deg2rad(geometry.fluteHelixAngle)) * geometry.numFlutes)

    differentialPathLength  = np.sqrt(np.diff(xChannelCenterline3D)**2 + np.diff(yChannelCenterline3D)**2 + np.diff(zChannelCenterline3D)**2)
    differentialPathLength  = np.append(differentialPathLength, differentialPathLength[-1])
    totalPathLength         = np.sum(differentialPathLength)

    # Roll of the cross section about the path tangent. It is what turns a flute into a
    # helix, so it is defined only where there is a helix angle to turn it through. A
    # circular section is rotationally symmetric and a roll leaves it unchanged, and its
    # configuration carries no helix angle, so the angle arrives as NaN and the roll is
    # taken as zero rather than propagating that NaN into every oriented point.
    crossSectionRoll        = np.zeros(geometry.numCrossSections)
    if np.isfinite(geometry.fluteHelixAngle):
        rollTotal               = np.tan(np.deg2rad(geometry.fluteHelixAngle)) * totalPathLength / channelRadius
        differentialRollPercent = differentialPathLength / totalPathLength
        differentialRoll        = rollTotal * differentialRollPercent
        crossSectionRoll[1:]    = np.cumsum(differentialRoll[:-1])

    crossSectionAngles      = np.linspace(0,      2*np.pi, geometry.numCSPointsChannel)
    gaussianCurveRange      = np.linspace(-np.pi, np.pi,   geometry.numCSPointsChannel)

    for i in range(arrLen):

        if compressionSearch == 'on':

            j = i

        turnAngle[i], radiusOfCurvature[i] = findTurnAngleAndRadiusOfCurvature(j)

    stations, tangent, normal, binormal = buildFrames()

    # -- circles -- #

    for i in range(arrLen):

        if compressionSearch == 'on':

            j = i

        xCircle[:,i] = channelRadius[j] * np.sin(crossSectionAngles) # z coords in 3d
        yCircle[:,i] = channelRadius[j] * np.cos(crossSectionAngles) # y coords in 3d

        circleCSA[i] = np.pi*channelRadius[j]**2
        circleSA[i]  = np.pi*2*channelRadius[j] * differentialPathLength[j]

    # Create circular cross sections to select nearest channel point to wall

    allCircleChannelPoints = orientCrossSections(stations, np.stack((yCircle, xCircle), axis=-1).transpose(1, 0, 2), crossSectionRoll)
    xChannelCirc = allCircleChannelPoints[:, :, 0].T
    yChannelCirc = allCircleChannelPoints[:, :, 1].T
    zChannelCirc = allCircleChannelPoints[:, :, 2].T

    # -- Nozzle Search -- #

    if compressionSearch == 'on':

        # -- find nozzle index -- #

        if geometry.numCrossSections >= 500: # parallelize nozzle search

            def parallelNozzleSearch(pointQuery, allNozzlePoints):

                nozzleIndex = KDTree(allNozzlePoints).query(pointQuery)[1]

                return nozzleIndex

            nozzleIndex = Parallel(n_jobs = int(cpu_count()/2-1))(delayed(parallelNozzleSearch)([zChannelCenterline3D[i],
                                                                                                 xChannelCenterline3D[i],
                                                                                                 yChannelCenterline3D[i]],
                                                                                                 geometry.allNozzlePoints)
                                    for i in tqdm(range(geometry.numCrossSections), desc="Scanning Nozzle Wall", colour="#ABD038"))

        else:

            nozzleIndex = np.zeros((geometry.numCrossSections))
            for i in tqdm(range(geometry.numCrossSections), desc="Scanning Nozzle Wall", colour="#ABD038"):

                pointQuery     = [zChannelCenterline3D[i], xChannelCenterline3D[i], yChannelCenterline3D[i]]
                nozzleIndex[i] = KDTree(geometry.allNozzlePoints).query(pointQuery)[1]

        # -- find compression index -- #

        compressianIndex         = np.zeros((geometry.numCrossSections))
        circleCrossSectionPoints = np.zeros((geometry.numCSPointsChannel,3)) 
        for i in tqdm(range(geometry.numCrossSections), desc="Scanning Cross Sections", colour="#ABD038"):

            pointQuery = [geometry.allNozzlePoints[int(nozzleIndex[i]),0], geometry.allNozzlePoints[int(nozzleIndex[i]),1], geometry.allNozzlePoints[int(nozzleIndex[i]),2]]
            circleCrossSectionPoints[:,0] = zChannelCirc[:,i]
            circleCrossSectionPoints[:,1] = xChannelCirc[:,i]
            circleCrossSectionPoints[:,2] = yChannelCirc[:,i]

            compressianIndex[i] = KDTree(circleCrossSectionPoints).query(pointQuery)[1]

    # -- Fluting and Compression -- #

    if crossSectionStyle.lower() == 'fluted':

        for i in range(arrLen):

            if compressionSearch == 'on':

                j = i

            xGausFluted[:,i],yGausFluted[:,i],gausFlutedCSA[i],gausFlutedSA[i], isCircle[i] = flutedCrossSection(j)

        # -- Create Final Channel Cross Sections and Build Channel Geometry -- #

        allFlutedChannelPoints = orientCrossSections(stations, np.stack((yGausFluted, xGausFluted), axis=-1).transpose(1, 0, 2), crossSectionRoll)
        xGausFlutedChannel = allFlutedChannelPoints[:, :, 0].T
        yGausFlutedChannel = allFlutedChannelPoints[:, :, 1].T
        zGausFlutedChannel = allFlutedChannelPoints[:, :, 2].T

        # identify correct arrays to return
        xChannel, yChannel, zChannel = xGausFlutedChannel, yGausFlutedChannel, zGausFlutedChannel

    else: # crossSectionStyle.lower() == 'circle':

        # identify correct arrays to return
        xChannel, yChannel, zChannel = xChannelCirc, yChannelCirc, zChannelCirc

    # -- Finish -- #            

    heatTransferDict = {}

    if compressionSearch == 'off':
        # make arrays length 1
        differentialPathLength = np.array([differentialPathLength[j]])
        fluteAmplitude         = np.array([fluteAmplitude[j]])
        flutePitch             = np.array([flutePitch[j]])

    if crossSectionStyle == 'fluted':
        heatTransferDict["gausFlutedCSA"]      = gausFlutedCSA
        heatTransferDict["gausFlutedSA"]       = gausFlutedSA
    else:
        heatTransferDict["gausFlutedCSA"]      = None
        heatTransferDict["gausFlutedSA"]       = None
    heatTransferDict["circleCSA"]              = circleCSA
    heatTransferDict["circleSA"]               = circleSA
    heatTransferDict["differentialPathLength"] = differentialPathLength
    heatTransferDict["fluteAmplitudeGauss"]    = fluteAmplitude
    heatTransferDict["flutePitch"]             = abs(flutePitch)
    heatTransferDict["turnAngle"]              = turnAngle
    heatTransferDict["radiusOfCurvature"]      = radiusOfCurvature
    heatTransferDict["isCircle"]               = isCircle

    if compressionSearch == 'on':

        return xChannel, yChannel, zChannel, heatTransferDict

    else: # compressionSearch == 'off'

        return heatTransferDict

def getMaxChannelRadius(geometry, rNozzle, i):

    '''

    Returns the maximum circular and fluted channel radii at station i along rNozzle

    Author: Isabella Duprey-Churn
    Date:   4/28/2026

    '''

    offsetHotWallThickness = geometry.hotWallThickness - geometry.infillThickness
    arcAngle = 2*np.pi / geometry.nChannel
    theta = arcAngle/2
    R = rNozzle[i] + offsetHotWallThickness
    r = R*np.sin(theta) / (1 - np.sin(theta))
    maxCircleChannelRadius = r - geometry.infillThickness / 2

    # find the maximum fluted channel radius

    if geometry.channelType == 'fluted':
        maxFlutedChannelRadius = maxCircleChannelRadius / (1 + 0.5*geometry.fluteAmplitudeCoef)
        return maxCircleChannelRadius, maxFlutedChannelRadius
    else:
        return maxCircleChannelRadius, 0
