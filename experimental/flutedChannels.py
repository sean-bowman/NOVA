# -- NOVA (experimental): Spirally Fluted Cooling Channels -- #

'''

A cooling channel whose wall carries helical flutes, with the correlation that rated it.

A fluted channel is a circle modulated by `numFlutes` sine waves of amplitude
`fluteAmplitudeCoef * r`, rolled about the path tangent as it advances so the flutes run as a
helix at `fluteHelixAngle`. The modulation is then compressed toward the circle on the side
facing the hot wall by a Gaussian centered on the wall-facing point, so the wall between the
coolant and the exhaust stays at its design thickness. At each volute interface the channel is
drawn circular for `interfaceLength` and blends into full amplitude over the next 10 mm, which
is what lets a round volute port meet it.

The coolant side was rated with a blend of Gnielinski and the spirally fluted tube correlation
in Webb and Kim, Principles of Enhanced Heat Transfer (p. 271), with the fluted term multiplied
by the roughness amplification Gnielinski sees between a rough and a smooth tube:

    f  = 0.5 f_G  + 0.5 f_PoEHT  (f_G / f_G,smooth)
    Nu = 0.5 Nu_G + 0.5 Nu_PoEHT (Nu_G / Nu_G,smooth)

each weighted back toward plain Gnielinski by the circular fraction of the interface blend.

----------------------------------------------------------------------
                        Status
----------------------------------------------------------------------

This builds and solves. It is here because nothing establishes that the correlation it is rated
with describes a printed rocket channel, not because the geometry cannot be drawn.

  - **The blend has no source.** Webb and Kim give the fluted correlation for drawn tubes over
    their own range of pitch, depth and helix angle. No reference states the fifty-fifty blend
    with Gnielinski or the roughness amplification applied to the second term, and no
    measurement is available to set either against. The documentation that described the model
    gave the weights as 25/75 while the code ran 50/50, and neither was ever checked.
  - **The area bases differ.** A circular section reports pi r^2 exactly, while a fluted
    section integrates its own polygon with the trapezoidal rule, which under-reports by 0.19
    percent at 60 points around the section. The thermal performance factor compares the two
    at the same radius, so that deficit is a systematic offset set by resolution.
  - **The last recorded baseline predates two wall corrections.** The package's per-channel
    conduction resistance and its hot-wall area were both corrected after this module left it,
    so any fluted result recorded before then carries a wall conduction drop understated by a
    factor of `nChannel` and a hot-wall area overstated by 1/cos(wrap angle).

  - **The helix needs stations.** The flute pitch is 2 pi r / (n tan(phi)): 5.9 mm for eight
    flutes at 15 degrees on a 2 mm channel. A swept surface with stations further apart than
    about half that pitch aliases the helix, so `numCrossSections` has to be set by the flutes
    rather than by the thermal march.

The functions below reproduce the package implementation. On a 60 station channel with both
interface blends active, `flutedProfile` with `interfaceBlend` and `compressionIndices` returned
cross-sectional areas identical to the package's `generateCrossSections(..., 'fluted')`, wetted
areas within 7e-16 relative and identical circular fractions; the single-station path matched
to 3e-20 m^2. On a straight channel the drawn flute pattern turned at 1.0000 of the requested
roll rate. The correlation is a transcription.

----------------------------------------------------------------------
                        Wiring it back in
----------------------------------------------------------------------

The package builds circular, rectangular and helical channels with one section family per run.
A caller reinstating the fluted family needs to:

  - restore the four keys in `flutedConfigurationKeys` on the Nozzle, in `config.py`, in the
    GUI schema and in `assets/NOVANozzle.json`, add `'fluted'` back to the `channelType`
    choice, and add `flutedRules` to `regenChannels.regenChannelRules`,
  - build the cold-wall point cloud with `nozzleWallCloud` in `regenChannels.generate3DChannels`
    and pass it through `ChannelGeometryInputs`,
  - in `channelGeometry.generateCrossSections`, sweep the circle with the roll from
    `crossSectionRoll` in place of the zero roll a circle takes, run `compressionIndices` on it,
    build each station with `flutedProfile`, and orient the flutes on the frames the circle
    sweep left behind. `orientCrossSections` rotates the frames in place, so the flutes are
    rolled twice on the frames and once more in `flutedProfile`; that combination is what
    turns them at the requested rate,
  - size with `maxFlutedChannelRadius`, `flutedChannelDiameter` in the kineos projection, and
    `flutedThroatChannelCount` in the throat check; offset the shell with `flutedShellOffset`,
  - compute the coolant side with `flutedCoolantSide` in `regenThermal`, using
    `np.sqrt(4 A / pi)` as the hydraulic diameter the package used for this family,
  - add `flutedHarnessOverrides` back to `tests/regressionHarness.py` as a case, and record a
    fresh baseline rather than restoring the old one.

Author: Sean Bowman

'''

import numpy as np
from scipy.spatial import KDTree

from NOVA.geometryTools import DCM
from NOVA.validation import integerRule, numericRule, read

# The configuration keys that exist only for this channel family. They were removed from Nozzle,
# config.py, the GUI schema and the shipped configuration when the family moved here.
flutedConfigurationKeys = ('numFlutes', 'fluteAmplitudeCoef', 'fluteHelixAngle', 'interfaceLength')

def _isFluted(source) -> bool:

    '''True for a channel whose cross section carries flutes.'''

    return read(source, 'channelType') == 'fluted'

# The validation rules that guarded those keys, lifted out of regenChannels.regenChannelRules and
# validation.py.
flutedRules = (
    numericRule('fluteHelixAngle', 'Flute helix angle', units = 'deg',
                minimum = -90, maximum = 90, when = _isFluted),
    integerRule('numFlutes', 'Number of flutes', minimum = 3, exclusiveMinimum = False,
                when = _isFluted),
    numericRule('fluteAmplitudeCoef', 'Flute amplitude coefficient', minimum = 0, maximum = 1,
                when = _isFluted),
)

# The regression case the family was pinned on: the harness regen jacket with the section
# swapped. Merge it over the harness `regenOverrides`.
flutedHarnessOverrides = {
    'channelType'       : 'fluted',
    'numFlutes'         : 8,
    'fluteAmplitudeCoef': 0.3,
    'fluteHelixAngle'   : 15.0,
    'interfaceLength'   : 0.02,
}

# Surface roughness the coolant-side friction factor is built on [m]. Velo3D GRCop-42 datasheet.
surfaceRoughness = 35e-6

# -------------------------------------------------------------------------------------------- #
# -- Geometry -- #
# -------------------------------------------------------------------------------------------- #

def fluteAmplitudeAndPitch(channelRadius: np.ndarray, fluteAmplitudeCoef: float,
                           fluteHelixAngle: float, numFlutes: int) -> tuple:

    '''

    Flute amplitude and axial pitch at each station.

    Parameters:
    -----------
    channelRadius : np.ndarray
        Channel radius at each station [m].
    fluteAmplitudeCoef : float
        Flute amplitude as a fraction of the channel radius [-].
    fluteHelixAngle : float
        Helix angle of the flutes [deg].
    numFlutes : int
        Flutes around one section [-].

    Returns:
    --------
    tuple
        (fluteAmplitude [m], flutePitch [m]), one entry per station. The pitch is signed with
        the helix angle; the thermal model reads its magnitude.

    '''

    fluteAmplitude = fluteAmplitudeCoef * channelRadius
    flutePitch     = 2*np.pi * channelRadius / (np.tan(np.deg2rad(fluteHelixAngle)) * numFlutes)

    return fluteAmplitude, flutePitch

def crossSectionRoll(differentialPathLength: np.ndarray, channelRadius: np.ndarray,
                     fluteHelixAngle: float) -> np.ndarray:

    '''

    Roll of each section about the path tangent, which is what turns a flute into a helix.

    The total roll is the helix angle's advance over the whole path at each station's radius,
    distributed along the path in proportion to segment length.

    Parameters:
    -----------
    differentialPathLength : np.ndarray
        Path length of each segment, padded to one entry per station [m].
    channelRadius : np.ndarray
        Channel radius at each station [m].
    fluteHelixAngle : float
        Helix angle of the flutes [deg].

    Returns:
    --------
    np.ndarray
        Roll at each station [rad], zero at the first.

    '''

    totalPathLength         = np.sum(differentialPathLength)
    roll                    = np.zeros(len(differentialPathLength))
    rollTotal               = np.tan(np.deg2rad(fluteHelixAngle)) * totalPathLength / channelRadius
    differentialRollPercent = differentialPathLength / totalPathLength
    differentialRoll        = rollTotal * differentialRollPercent
    roll[1:]                = np.cumsum(differentialRoll[:-1])

    return roll

def nozzleWallCloud(xColdWall: np.ndarray, rColdWall: np.ndarray, numCrossSections: int) -> np.ndarray:

    '''

    The cold-wall point cloud the compression search queries, ordered (z, x, y).

    Parameters:
    -----------
    xColdWall, rColdWall : np.ndarray
        Cold-wall contour, the hot wall offset by the hot wall thickness [m].
    numCrossSections : int
        Stations along the contour, which is also the number of points around each ring.

    Returns:
    --------
    np.ndarray
        (numCrossSections**2, 3) array of wall points.

    '''

    contourAngles = np.linspace(0, 2*np.pi, numCrossSections)
    points        = np.zeros((numCrossSections * numCrossSections, 3))

    for i in range(numCrossSections):
        ring = slice(i*numCrossSections, (i + 1)*numCrossSections)
        points[ring, 0] = rColdWall[i] * np.cos(contourAngles)
        points[ring, 1] = xColdWall[i]
        points[ring, 2] = rColdWall[i] * np.sin(contourAngles)

    return points

def compressionIndices(xCircle: np.ndarray, yCircle: np.ndarray, zCircle: np.ndarray,
                       xCenterline: np.ndarray, yCenterline: np.ndarray, zCenterline: np.ndarray,
                       wallCloud: np.ndarray) -> np.ndarray:

    '''

    The point on each circular section nearest the hot wall.

    The nearest wall point to each centerline station is found first, then the point on that
    station's swept circle nearest to it. The Gaussian compression is centered there.

    Parameters:
    -----------
    xCircle, yCircle, zCircle : np.ndarray
        Swept circular sections, (numCSPointsChannel, numCrossSections) [m], as the package
        returns them for a circular channel.
    xCenterline, yCenterline, zCenterline : np.ndarray
        Channel centerline [m].
    wallCloud : np.ndarray
        Cold-wall points from `nozzleWallCloud`.

    Returns:
    --------
    np.ndarray
        Index into each section of its wall-facing point.

    '''

    numCrossSections = len(xCenterline)
    wallTree         = KDTree(wallCloud)
    indices          = np.zeros(numCrossSections)

    for i in range(numCrossSections):
        nearestWall  = wallCloud[wallTree.query([zCenterline[i], xCenterline[i], yCenterline[i]])[1]]
        section      = np.column_stack((zCircle[:, i], xCircle[:, i], yCircle[:, i]))
        indices[i]   = KDTree(section).query(nearestWall)[1]

    return indices

def interfaceBlend(i: int, fluteAmplitude: np.ndarray, gaussianCurve: np.ndarray,
                   totalPathLength: float, numCrossSections: int, numCSPointsChannel: int,
                   interfaceLength: float, numInletInterfaceCS: int, numReturnInterfaceCS: int) -> tuple:

    '''

    Flute amplitude at one station: zero at the volute interfaces, blended up to full between.

    Parameters:
    -----------
    i : int
        Station index.
    fluteAmplitude : np.ndarray
        Full flute amplitude at each station [m].
    gaussianCurve : np.ndarray
        Compression curve around the section, already centered on the wall-facing point.
    totalPathLength : float
        Length of the whole channel [m].
    numCrossSections, numCSPointsChannel : int
        Stations along the channel and points around a section.
    interfaceLength : float
        Circular run at each volute interface [m].
    numInletInterfaceCS, numReturnInterfaceCS : int
        Stations in each volute interface.

    Returns:
    --------
    tuple
        (amplitude around the section [m], circular fraction [-]).

    '''

    stationLength                  = totalPathLength / numCrossSections
    numInterfaceCrossSections      = int(np.floor(interfaceLength / stationLength))
    numInterfaceBlendCrossSections = max(3, int(np.floor(10e-3 / stationLength)))
    blendUp                        = np.linspace(0, 1, numInterfaceBlendCrossSections + 1)
    blendDown                      = np.linspace(1, 0, numInterfaceBlendCrossSections + 1)

    returnEnd  = numReturnInterfaceCS + numInterfaceCrossSections
    inletStart = numCrossSections - numInterfaceCrossSections - numInletInterfaceCS

    # Circular return run
    if i <= returnEnd:
        return np.zeros(numCSPointsChannel), 1
    # Blend up out of the return run
    if i <= returnEnd + numInterfaceBlendCrossSections:
        return fluteAmplitude[i] * gaussianCurve * blendUp[i - returnEnd], 1 - blendUp[i - returnEnd]
    # Fully fluted
    if i <= inletStart - numInterfaceBlendCrossSections:
        return fluteAmplitude[i] * gaussianCurve, 0
    # Blend down into the inlet run
    if i <= inletStart:
        k = i - (inletStart - numInterfaceBlendCrossSections)
        return fluteAmplitude[i] * gaussianCurve * blendDown[k], 1 - blendDown[k]
    # Circular inlet run
    return np.zeros(numCSPointsChannel), 1

def flutedProfile(i: int, channelRadius: np.ndarray, fluteAmplitude: np.ndarray,
                  roll: np.ndarray, differentialPathLength: np.ndarray, numFlutes: int,
                  numCSPointsChannel: int, compressionIndex: np.ndarray = None,
                  blend: dict = None) -> tuple:

    '''

    One fluted section in its own plane, with its area and wetted area.

    The section is built as a fully fluted polar curve, rolled, then rescaled so the flute
    amplitude follows a Gaussian centered on the wall-facing point. Without a compression index
    the Gaussian sits at the section's own origin, which is what a single-station sizing call
    uses.

    Parameters:
    -----------
    i : int
        Station index.
    channelRadius, fluteAmplitude, roll, differentialPathLength : np.ndarray
        Per-station radius [m], amplitude [m], roll [rad] and segment length [m].
    numFlutes : int
        Flutes around the section.
    numCSPointsChannel : int
        Points around the section.
    compressionIndex : np.ndarray, optional
        Wall-facing point of each section, from `compressionIndices`.
    blend : dict, optional
        Keyword arguments for `interfaceBlend` other than the station, amplitude and curve.
        Applied only with a compression index.

    Returns:
    --------
    tuple
        (x [m], y [m], cross-sectional area [m^2], wetted area of the segment [m^2],
        circular fraction [-]).

    '''

    crossSectionAngles = np.linspace(0, 2*np.pi, numCSPointsChannel)
    gaussianCurveRange = np.linspace(-np.pi, np.pi, numCSPointsChannel)

    wave     = channelRadius[i] + fluteAmplitude[i] * np.sin(numFlutes * crossSectionAngles)
    xFluted  = -wave * np.sin(crossSectionAngles)
    yFluted  = -wave * np.cos(crossSectionAngles)
    _, yRolled, zRolled = DCM([roll[i], 0, 0], [np.zeros_like(xFluted), yFluted, xFluted],
                              transpose = True, rotationOrder = 'yzx')

    polarRadius = np.sqrt(zRolled**2 + yRolled**2)
    polarAngles = np.arctan2(zRolled, yRolled)

    if compressionIndex is not None:
        shifted       = np.roll(gaussianCurveRange, -(numCSPointsChannel - int(compressionIndex[i]) - 1))
        gaussianCurve = ((1/np.sqrt(2*np.pi)*np.exp(-(shifted)**2/(np.pi/2)))/.4)
        amplitude, isCircle = interfaceBlend(i, fluteAmplitude, gaussianCurve, **blend)
    else:
        gaussianCurve = ((1/np.sqrt(2*np.pi)*np.exp(-(gaussianCurveRange)**2/(np.pi/2)))/.4)
        amplitude, isCircle = fluteAmplitude[i] * gaussianCurve, 0

    scaled = (polarRadius - channelRadius[i]) / fluteAmplitude[i] * amplitude + channelRadius[i]
    x      = scaled * np.sin(polarAngles)
    y      = scaled * np.cos(polarAngles)
    area   = abs(np.trapz(y, x))

    circumference = np.sum(np.sqrt(np.diff(x)**2 + np.diff(y)**2))
    wettedArea    = circumference * differentialPathLength[i]

    return x, y, area, wettedArea, isCircle

# -------------------------------------------------------------------------------------------- #
# -- Sizing -- #
# -------------------------------------------------------------------------------------------- #

def maxFlutedChannelRadius(maxCircleChannelRadius: float, fluteAmplitudeCoef: float) -> float:

    '''Largest fluted radius that fits where a circle of the given radius fits [m].'''

    return maxCircleChannelRadius / (1 + 0.5*fluteAmplitudeCoef)

def flutedChannelDiameter(channelRadius, fluteAmplitudeCoef: float):

    '''Width a fluted channel occupies across the kineos projection [m].'''

    return 2*channelRadius + fluteAmplitudeCoef*channelRadius

def flutedRadiusFromDiameter(channelDiameter, fluteAmplitudeCoef: float):

    '''Inverse of `flutedChannelDiameter` [m].'''

    return channelDiameter / (2 + fluteAmplitudeCoef)

def flutedShellOffset(channelRadius, hotWallThickness: float, shellThickness: float,
                      fluteAmplitudeCoef: float):

    '''Hot wall to outer shell distance, which the flute amplitude extends past the channel [m].'''

    return hotWallThickness + 2.*channelRadius + fluteAmplitudeCoef*channelRadius + shellThickness

def flutedThroatChannelCount(throatRadius: float, hotWallThickness: float, infillThickness: float,
                             minChannelRadius: float, fluteAmplitudeCoef: float, nChannel: int) -> int:

    '''

    Channel count that keeps the fluted throat radius at or above the process minimum.

    Returns `nChannel` unchanged when the throat already fits.

    '''

    offsetWall     = throatRadius + hotWallThickness - infillThickness
    halfAngle      = np.pi / nChannel
    circleAtThroat = offsetWall*np.sin(halfAngle) / (1 - np.sin(halfAngle)) - infillThickness / 2

    if maxFlutedChannelRadius(circleAtThroat, fluteAmplitudeCoef) >= minChannelRadius:
        return nChannel

    reach = minChannelRadius * (1 + fluteAmplitudeCoef / 2) + infillThickness / 2

    return int(np.pi / np.arcsin(reach / (reach + throatRadius + hotWallThickness - infillThickness)))

# -------------------------------------------------------------------------------------------- #
# -- Coolant side -- #
# -------------------------------------------------------------------------------------------- #

def flutedCoolantSide(reynoldsNumber: float, prandtlNumber: float, hydraulicDiameter: float,
                      fluteAmplitude: float, flutePitch: float, fluteHelixAngle: float,
                      isCircle: float) -> tuple:

    '''

    Darcy friction factor and Nusselt number for a fluted section.

    Parameters:
    -----------
    reynoldsNumber, prandtlNumber : float
        Coolant bulk Reynolds and Prandtl numbers [-].
    hydraulicDiameter : float
        sqrt(4 A / pi) of the fluted section [m].
    fluteAmplitude, flutePitch : float
        Local flute amplitude and pitch magnitude [m].
    fluteHelixAngle : float
        Helix angle magnitude [deg].
    isCircle : float
        Circular fraction from the interface blend [-].

    Returns:
    --------
    tuple
        (fluted friction factor, fluted Nusselt number, Gnielinski rough friction factor).

    '''

    e = fluteAmplitude / hydraulicDiameter
    p = flutePitch / hydraulicDiameter

    frictionGnielinski       = 0.25 / (np.log10((surfaceRoughness / hydraulicDiameter)/3.7 + 5.74/reynoldsNumber**0.9))**2
    frictionGnielinskiSmooth = (0.79 * np.log(reynoldsNumber) - 1.64)**-2
    frictionPoEHT            = (1.209 * reynoldsNumber**-0.261 * e**(1.26 - 0.05*p) * p**(-1.66 + 2.033*e)
                                * (fluteHelixAngle / 90)**(-2.669 + 3.67*e))

    def gnielinski(friction):
        return ((friction / 8) * (reynoldsNumber - 1000) * prandtlNumber) / \
               (1 + 12.7 * (friction / 8)**(1/2) * (prandtlNumber**(2/3) - 1))

    nusseltGnielinski       = gnielinski(frictionGnielinski)
    nusseltGnielinskiSmooth = gnielinski(frictionGnielinskiSmooth)
    nusseltPoEHT            = (0.064 * reynoldsNumber**0.773 * prandtlNumber**0.4 * e**-0.242 * p**-0.108
                               * (fluteHelixAngle / 90)**0.599)

    frictionAmplification = frictionGnielinski / frictionGnielinskiSmooth
    nusseltAmplification  = nusseltGnielinski / nusseltGnielinskiSmooth

    frictionFactor = (0.5*frictionGnielinski + 0.5*frictionPoEHT*frictionAmplification) * (1 - isCircle) \
                     + frictionGnielinski*isCircle
    nusseltNumber  = (0.5*nusseltGnielinski + 0.5*nusseltPoEHT*nusseltAmplification) * (1 - isCircle) \
                     + nusseltGnielinski*isCircle

    return frictionFactor, nusseltNumber, frictionGnielinski

def thermalPerformanceFactor(flutedNusselt: float, circleNusselt: float,
                             flutedFriction: float, circleFriction: float) -> float:

    '''Nusselt gain over friction gain to the one-third power, fluted against circular [-].'''

    return (flutedNusselt / circleNusselt) / (flutedFriction / circleFriction)**(1/3)
