
# -- NOVA: Regenerative Cooling Channel Build -- #

'''

Assembling a regeneratively cooled jacket from a contour and a coolant.

This is the orchestration of the channel build rather than the physics. The
physics lives in three modules it calls: channelGeometry draws a cross section and sweeps it,
channelSizing converges the radius at each station against a wall temperature, and regenThermal
solves the heat balance those two are converged against.

What happens here is the sequence, and the sequence matters:

    1. Volute interfaces. The jacket runs the whole regen section, from the injector face over
       the chamber barrel to the regen truncation. At each end a fillet turns the channel off the
       wall into a straight flare the volute attaches to: the inlet at the aft end, the outlet at
       the injector face, the one the mirror image of the other. The wall is trimmed back to where
       each fillet leaves it, and everything downstream works on the trimmed section.
    2. Channel radii. The sizing solve, station by station, which also produces the 2D centerline
       the channel follows and the coolant exit condition.
    3. Channel centerline. The 2D centerline is wrapped into three dimensions around the nozzle,
       and the hot wall and shell surfaces are built from it.
    4. Three-dimensional channels. The cross sections are swept along the wrapped centerline into
       the surfaces that get exported, and the cold wall surface is built.
    5. Cooling jacket. Optionally, all channels merged into one volume rather than kept separate.

Every array the build produces is carried on a RegenChannelState rather than being set on an
object as it goes, so what the build reads and what it produces are both stated in one place.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Nothing here computes a physical result, so nothing here is validated.** The build is
geometry: it decides where a channel runs and what surfaces come out of it. The numbers that
carry physical meaning come from the three modules it calls, and each of those carries its own
validation status, which this inherits unchanged.

What the geometry can be held to is consistency, and the tests do that: a channel that fits
between its neighbors, a centerline that stays on the wall it was offset from, and surfaces
that close.

----------------------------------------------------------------------
                        Geometry conventions
----------------------------------------------------------------------

Three-dimensional cooling channel geometry follows the convention of the rest of the tool:

    - X is the direction of the outgoing fluid at the volute interface
    - Y is orthogonal to X in the plane of the volute scroll
    - Z completes the set and is the nozzle axis

All units are mass base SI:
    - Length      [m]
    - Temperature [K]
    - Pressure    [Pa]
    - Angle       [rad] internally, [deg] where a configuration names one

Author: Sean Bowman

'''

from dataclasses import dataclass
from typing import Any

import numpy as np
from tqdm import tqdm

from .geometryTools import DCM, arcSpline, chunkInterpolate, intersection, parallelOffset
from .channelProfile import CHANNELSIZINGMODES, PROFILEKEYS
from .channelSections import (SECTIONFAMILIES, depthLimitedHalfExtent, helicalSpacing,
                              loxodromeWrap, maxHalfExtent, rectangularWidth)
from .channelGeometry import (ChannelGeometryInputs,
                              generateCrossSections as buildCrossSections,
                              getMaxChannelRadius as maxChannelRadius)
from .channelSizing import ChannelSizingState, channelSizingOutputs, solveChannelRadii
from .validation import (applyRules, arrayRule, choiceRule, integerRule, numericRule,
                         presentRule, read, textRule)

@dataclass
class RegenChannelState:

    '''

    Everything the channel build reads, and everything it produces.

    The fields are grouped by how the build uses them. The first group is the configuration and
    the contour it works from and does not change. The second is worked on in place as the build
    proceeds, so a field there is both an input to a later step and an output of an earlier one.
    The third is produced outright.

    Every field starts as None. One still None after a build is a step that was not reached,
    which is worth keeping rather than hiding behind an empty array.

    '''

    # -- What the build reads -- #
    channelType:                               Any = None
    channelSizingMode:                         Any = None
    manualChannelProfile:                      Any = None
    manualChannelProfileKey:                   Any = None
    gasSideAxialModel:                         Any = None
    coolantGeometryCorrections:                Any = None
    coolantRoughnessModel:                     Any = None
    channelSurfaceRoughness:                   Any = None
    channelAspectRatio:                        Any = None
    channelCornerRadius:                       Any = None
    channelHelixAngle:                         Any = None
    maxChannelAspectRatio:                     Any = None
    maxChannelDepth:                           Any = None
    minChannelWidth:                           Any = None
    gammaRegenSection:                         Any = None
    gasConstantRegenSection:                   Any = None
    hotWallThickness:                          Any = None
    infillThickness:                           Any = None
    inletVoluteAxialOffset:                    Any = None
    inletVoluteFlareLength:                    Any = None
    inletVoluteFlareRoverD:                    Any = None
    inletVoluteTilt:                           Any = None
    makeCoolingChannels:                       Any = None
    makeInletVolute:                           Any = None
    makeOutletVolute:                          Any = None
    molecularWeightRegenSection:               Any = None
    nChannel:                                  Any = None
    numCSPointsChannel:                        Any = None
    numCrossSections:                          Any = None
    rRegenNozzle:                              Any = None
    regenSectionNearWallMachNumber:            Any = None
    regenSectionNearWallPressure:              Any = None
    regenSectionNearWallRecoveryTemperature:   Any = None
    regenSectionNearWallTemperature:           Any = None
    regenSectionFilmDrivingTemperature:        Any = None
    outletVoluteAxialOffset:                   Any = None
    outletVoluteFlareLength:                      Any = None
    outletVoluteFlareRoverD:                   Any = None
    outletVoluteTilt:                          Any = None
    shellThickness:                            Any = None
    xRegenNozzle:                              Any = None

    chamberPressure:                           Any = None
    dcrData:                                   Any = None
    material:                                  Any = None
    maxWallTemperature:                        Any = None
    nozzleScalingFactor:                       Any = None
    theoreticalCharacteristicVelocity:         Any = None
    throatInletCurvatureNonDimensional:        Any = None
    throatOutletCurvatureNonDimensional:       Any = None
    coolant:                                   Any = None
    coolantInitialPressure:                    Any = None
    coolantInitialTemperature:                 Any = None
    coolantMassFlow:                           Any = None
    minCoolantExitPressure:                    Any = None
    minCoolantExitTemperature:                 Any = None
    minChannelRadius:                          Any = None

    # -- Read and written as the build proceeds -- #
    channelRadius:                             Any = None
    channelRibThickness:                       Any = None
    channelWidth:                              Any = None
    channelWallTemperature:                    Any = None
    channelProfilePoints:                      Any = None
    gammaRegenSectionTrimmed:                  Any = None
    gasConstantRegenSectionTrimmed:            Any = None
    molecularWeightRegenSectionTrimmed:        Any = None
    numInletInterfaceCS:                       Any = None
    numOutletInterfaceCS:                      Any = None
    rChannelCenterline2D:                      Any = None
    rInletInterface:                           Any = None
    rRegenNozzleInterfaced:                    Any = None
    rRegenNozzleTrimmed:                       Any = None
    rOutletInterface:                          Any = None
    regenSectionNearWallMachNumberTrimmed:     Any = None
    regenSectionNearWallPressureTrimmed:       Any = None
    regenSectionNearWallRecoveryTemperatureTrimmed: Any = None
    regenSectionFilmDrivingTemperatureTrimmed: Any = None
    regenSectionNearWallTemperatureTrimmed:    Any = None
    wrapAngles:                                Any = None
    xChannel:                                  Any = None
    xChannelCenterline2D:                      Any = None
    xChannelCenterline3D:                      Any = None
    xInletInterface:                           Any = None
    xNozzleColdWallMesh:                       Any = None
    xRegenNozzleInterfaced:                    Any = None
    xRegenNozzleTrimmed:                       Any = None
    xOutletInterface:                          Any = None
    yChannel:                                  Any = None
    yChannelCenterline3D:                      Any = None
    yNozzleColdWallMesh:                       Any = None
    zChannel:                                  Any = None
    zChannelCenterline3D:                      Any = None
    zNozzleColdWallMesh:                       Any = None

    # -- Produced by the sizing solve and carried through -- #
    coolantExitPressure:                       Any = None
    coolantExitTemperature:                    Any = None
    wallMaterialResolved:                      Any = None
    tempRangeKelvin:                           Any = None
    wallThermalConductivityData:               Any = None
    wallThermalConductivityInterpolator:       Any = None
    wallCTEInterpolator:                       Any = None
    wallYieldStrengthInterpolator:             Any = None
    wallFractureStrainInterpolator:            Any = None

    # -- Produced by the build -- #
    channelDepth:                              Any = None
    channelSizingSolution:                     Any = None
    rChannelCenterline3D:                      Any = None
    rNozzleShell:                              Any = None
    xNozzleHotWallMesh:                        Any = None
    xNozzleShell:                              Any = None
    xNozzleShellMesh:                          Any = None
    yNozzleHotWallMesh:                        Any = None
    yNozzleShellMesh:                          Any = None
    zNozzleHotWallMesh:                        Any = None
    zNozzleShellMesh:                          Any = None

# The fields a build hands back to a Nozzle. Kept beside the class so that adding a field and
# forgetting to surface it is a one-line fix rather than a silent drop. The sizing solve's own
# outputs are appended rather than restated, because the build copies them onto its state by name
# and a static read of this module cannot see that it does.
_buildOutputs = (
    'channelDepth', 'channelRadius', 'channelRibThickness', 'channelWidth', 'channelSizingSolution', 'gammaRegenSectionTrimmed',
    'gasConstantRegenSectionTrimmed', 'molecularWeightRegenSectionTrimmed',
    'numInletInterfaceCS', 'numOutletInterfaceCS', 'rChannelCenterline2D', 'rChannelCenterline3D',
    'rInletInterface', 'rNozzleShell', 'rRegenNozzleInterfaced', 'rRegenNozzleTrimmed',
    'rOutletInterface', 'regenSectionNearWallMachNumberTrimmed',
    'regenSectionNearWallPressureTrimmed', 'regenSectionNearWallTemperatureTrimmed',
    'regenSectionNearWallRecoveryTemperatureTrimmed',
    'regenSectionFilmDrivingTemperatureTrimmed',
    'wrapAngles', 'xChannel', 'xChannelCenterline2D',
    'xChannelCenterline3D', 'xInletInterface', 'xNozzleColdWallMesh',
    'xNozzleHotWallMesh', 'xNozzleShell', 'xNozzleShellMesh', 'xRegenNozzleInterfaced',
    'xRegenNozzleTrimmed', 'xOutletInterface', 'yChannel', 'yChannelCenterline3D',
    'yNozzleColdWallMesh', 'yNozzleHotWallMesh', 'yNozzleShellMesh',
    'zChannel', 'zChannelCenterline3D',
    'zNozzleColdWallMesh', 'zNozzleHotWallMesh', 'zNozzleShellMesh')

regenChannelOutputs = tuple(sorted(set(_buildOutputs) | set(channelSizingOutputs)))

# What a channel definition has to say before the jacket can be laid out. Written as a table
# rather than as branches: see validation.py.
#
# Checked in order, so the table runs from the contour the channels sit on, through the channel
# definition itself and the coolant, to where the volutes leave the wall.

def _isRectangular(source):

    '''True for a rectangular channel.'''

    return read(source, 'channelType') == 'rectangular'

def _isHelical(source):

    '''True for a helical channel.'''

    return read(source, 'channelType') == 'helical'

def _isRectangularFamily(source):

    '''True for a channel drawn as a rounded rectangle: rectangular or helical.'''

    return read(source, 'channelType') in ('rectangular', 'helical')

def _isManualSizing(source):

    '''True when the channel size is read off a profile rather than converged.'''

    return read(source, 'channelSizingMode') == 'manual'

def _makesInletVolute(source):

    '''True when an inlet volute is asked for.'''

    return read(source, 'makeInletVolute') == 'on'

def _makesOutletVolute(source):

    '''True when a outlet volute is asked for.'''

    return read(source, 'makeOutletVolute') == 'on'

regenChannelRules = (

    # -- The regen section the channels run along -- #
    arrayRule('xRegenNozzle', 'Regen section axial coordinate', units = 'm'),
    arrayRule('rRegenNozzle', 'Regen section radius', units = 'm',
              positive = True, sameLengthAs = 'xRegenNozzle'),
    integerRule('numCrossSections', 'Cross sections', minimum = 3, exclusiveMinimum = False),

    # -- The channels themselves -- #
    choiceRule('channelType', 'Channel cross section', choices = SECTIONFAMILIES,
               note = 'Spirally fluted channels are kept in experimental/flutedChannels.py'),
    choiceRule('channelSizingMode', 'Channel sizing mode', choices = CHANNELSIZINGMODES,
               required = False,
               note = 'Absent is the search against the wall temperature limit'),
    choiceRule('manualChannelProfileKey', 'Manual channel profile key', choices = PROFILEKEYS,
               required = False, when = _isManualSizing),
    presentRule('manualChannelProfile', 'Manual channel profile', when = _isManualSizing,
                note = 'A half-extent [m], a list of [key, half-extent] pairs, or a path to a '
                       'recorded profile'),
    integerRule('nChannel', 'Number of channels', minimum = 10, exclusiveMinimum = False,
                when = lambda source: not _isHelical(source)),
    integerRule('nChannel', 'Number of helical starts', minimum = 1, exclusiveMinimum = False,
                when = _isHelical),
    numericRule('minChannelRadius', 'Minimum channel radius', units = 'm',
                minimum = 0.5e-3, exclusiveMinimum = False),
    numericRule('hotWallThickness', 'Hot wall thickness', units = 'm',
                minimum = 0.5e-3, exclusiveMinimum = False),
    numericRule('infillThickness', 'Rib thickness between channels', units = 'm',
                minimum = 0.5e-3, exclusiveMinimum = False),
    numericRule('maxWallTemperature', 'Maximum hot wall temperature', units = 'K', minimum = 0,
                note = 'One temperature for the whole jacket. The sizing search converges '
                       'against it and a manual profile is reported against it'),

    # -- A rectangle's and a helix's width, aspect ratio and depth limits -- #
    numericRule('minChannelWidth', 'Minimum channel width', units = 'm',
                minimum = 0.5e-3, exclusiveMinimum = False, when = _isRectangularFamily),
    numericRule('channelHelixAngle', 'Channel helix angle', units = 'deg',
                minimum = 0, maximum = 85, exclusiveMaximum = False, when = _isHelical,
                note = 'Measured from the meridian'),
    numericRule('channelAspectRatio', 'Channel aspect ratio',
                minimum = 0, maximum = 20, exclusiveMaximum = False, when = _isHelical),
    numericRule('maxChannelAspectRatio', 'Maximum channel aspect ratio',
                minimum = 0, maximum = 20, exclusiveMaximum = False, when = _isRectangular),
    numericRule('maxChannelDepth', 'Maximum channel depth', units = 'm', minimum = 0,
                required = False,
                note = 'How far a channel may reach out from the wall, a circle\'s diameter '
                       'included. Unset leaves a circle bounded only by its neighbors'),
    numericRule('channelCornerRadius', 'Channel corner radius', units = 'm', minimum = 0,
                exclusiveMinimum = False, when = _isRectangularFamily, required = False),

    # -- The coolant they carry -- #
    textRule('coolant', 'Coolant species',
             note = 'A REFPROP or CoolProp fluid name, such as Hydrogen, O2 or Methane'),
    numericRule('coolantMassFlow', 'Coolant mass flow', units = 'kg/s', minimum = 0),
    numericRule('coolantInitialPressure', 'Coolant inlet pressure', units = 'Pa', minimum = 0),
    numericRule('coolantInitialTemperature', 'Coolant inlet temperature', units = 'K', minimum = 0),
    numericRule('minCoolantExitPressure', 'Minimum coolant exit pressure', units = 'Pa',
                minimum = 0, required = False,
                note = 'Checked once the jacket is solved. Unset is no limit'),
    numericRule('minCoolantExitTemperature', 'Minimum coolant exit temperature', units = 'K',
                minimum = 0, required = False,
                note = 'Checked once the jacket is solved. Unset is no limit'),

    # -- Where each volute leaves the wall -- #
    numericRule('inletVoluteAxialOffset', 'Inlet volute axial offset', units = 'm', minimum = 0,
                when = _makesInletVolute,
                note = 'Measured upstream from the aft end of the regen section'),
    numericRule('outletVoluteAxialOffset', 'Outlet volute axial offset', units = 'm', minimum = 0,
                when = _makesOutletVolute,
                note = 'Measured downstream from the injector face'),
)

def validateRegenChannelInputs(state) -> None:

    '''

    Check that the channel definition can be laid out on the contour it was given.

    The rules are the table above, checked by `validation.applyRules`.

    Parameters:
    -----------
    state : RegenChannelState
        The configuration to check.

    Raises:
    -------
    InvalidInputError
        On the first rule the configuration fails.

    '''

    applyRules(state, regenChannelRules)

def voluteInterfaceCurve(xWall: np.ndarray, rWall: np.ndarray, axialOffset: float,
                         filletRadius: float, flareAngle: float, flareLength: float,
                         numFlarePoints: int = 20) -> tuple:

    '''

    The fillet and flare that turn a channel off the wall and out to its volute.

    Built at the downstream end of the wall as given, the last point of `xWall`. A plane is drawn
    `axialOffset` upstream of that point, normal to the axis, and a fillet of `filletRadius` is
    placed tangent to both the wall and the plane. The channel follows the wall to the fillet,
    turns through it, and leaves along a straight flare of `flareLength` at `flareAngle` from the
    radial, which is where the volute attaches. The wall past the fillet is not jacketed.

    The upstream end is the same construction reflected through a plane normal to the axis; see
    `upstreamVoluteInterfaceCurve`.

    Parameters:
    -----------
    xWall, rWall : np.ndarray
        Hot wall, increasing in x toward the end being interfaced [m].
    axialOffset : float
        Distance from the end of the wall to the plane the flare leaves along [m].
    filletRadius : float
        Radius of the turn off the wall [m].
    flareAngle : float
        Flare direction measured from the outward radial, positive toward the wall's end [rad].
    flareLength : float
        Length of the straight flare [m].
    numFlarePoints : int
        Points along the flare, more than one so later resampling keeps it straight.

    Returns:
    --------
    tuple
        (xInterface, rInterface, keep): the fillet and flare from the tangent point outward [m],
        and a mask selecting the wall points upstream of the tangent point.

    '''

    # Draw the exit plane w/ axial offset
    xExitPlane = np.array([xWall[-1], xWall[-1]]) - axialOffset
    rExitPlane = np.array([0, 2*rWall[-1]])
    xExitPlaneOff = xExitPlane - filletRadius
    rExitPlaneOff = rExitPlane

    # Draw the centerline
    xHotWall, rHotWall = parallelOffset(xWall, rWall, filletRadius)

    # Fillet circle
    filletCenter  = intersection(xHotWall, rHotWall, xExitPlaneOff, rExitPlaneOff)
    xFilletCenter = filletCenter[0][0][0]
    rFilletCenter = filletCenter[1][0][0]
    xFilletCircle = 1.0005*filletRadius * np.cos(np.linspace(0,2*np.pi,300)) + xFilletCenter
    rFilletCircle = 1.0005*filletRadius * np.sin(np.linspace(0,2*np.pi,300)) + rFilletCenter
    # Intersect pathline
    hotWallIntersection  = intersection(xWall, rWall, xFilletCircle, rFilletCircle)
    xHotWallIntersection = hotWallIntersection[0][0][0]
    rHotWallIntersection = hotWallIntersection[1][0][0]
    thetaHotWallIntersection = (3*np.pi/2) + np.arctan((xHotWallIntersection-xFilletCenter)/(rFilletCenter-rHotWallIntersection))
    # Fillet arc
    xFillet = 1.0005*filletRadius * np.cos(np.linspace(thetaHotWallIntersection,(2*np.pi)+flareAngle,300)) + xFilletCenter
    rFillet = 1.0005*filletRadius * np.sin(np.linspace(thetaHotWallIntersection,(2*np.pi)+flareAngle,300)) + rFilletCenter

    # Limit tilt
    xLimitTilt = filletRadius*np.cos(flareAngle) + xFilletCenter
    rLimitTilt = filletRadius*np.sin(flareAngle) + rFilletCenter
    # Find flare end
    xFlareEnd = xLimitTilt - (flareLength)*np.sin(flareAngle)
    rFlareEnd = rLimitTilt + (flareLength)*np.cos(flareAngle)

    # Append the linear flare to the filleted centerline
    # place several points along flare to maintain linearity through later arcSplines
    xFlare = np.concatenate([xFillet,np.linspace(xFillet[-1],xFlareEnd,numFlarePoints+2)[1:]])
    rFlare = np.concatenate([rFillet,np.linspace(rFillet[-1],rFlareEnd,numFlarePoints+2)[1:]])

    return xFlare, rFlare, xWall < xHotWallIntersection

def upstreamVoluteInterfaceCurve(xWall: np.ndarray, rWall: np.ndarray, axialOffset: float,
                                 filletRadius: float, flareAngle: float, flareLength: float,
                                 numFlarePoints: int = 20) -> tuple:

    '''

    The fillet and flare at the upstream end of the wall, the first point of `xWall`.

    This is `voluteInterfaceCurve` built on the wall reflected through a plane normal to the axis
    and reversed, so the upstream end becomes the downstream end it works at, then reflected and
    reversed back. Negation is exact in floating point, so for the same offset, fillet, flare and
    tilt the two ends are exact mirror images. The plane the flare leaves along sits `axialOffset`
    downstream of the first wall point.

    Returns:
    --------
    tuple
        (xInterface, rInterface, keep): the flare and fillet from the flare end in to the tangent
        point [m], the order the interface is prepended to the wall in, and a mask selecting the
        wall points downstream of the tangent point.

    '''

    xMirror, rMirror, keepMirror = voluteInterfaceCurve(-np.flip(xWall), np.flip(rWall),
                                                        axialOffset, filletRadius, flareAngle,
                                                        flareLength, numFlarePoints)

    return -np.flip(xMirror), np.flip(rMirror), np.flip(keepMirror)

def _geometryInputs(state) -> 'ChannelGeometryInputs':

    '''

    The channel definition the cross-section builder reads, taken from the build state.

    '''

    return ChannelGeometryInputs(
        numCrossSections     = state.numCrossSections,
        numCSPointsChannel   = state.numCSPointsChannel,
        nChannel             = state.nChannel,
        channelType          = state.channelType,
        hotWallThickness     = state.hotWallThickness,
        infillThickness      = state.infillThickness,
        channelCornerRadius  = valueOrDefault(state.channelCornerRadius, 0.0),
        maxChannelAspectRatio = valueOrDefault(state.maxChannelAspectRatio, 8.0),
        maxChannelDepth      = valueOrDefault(state.maxChannelDepth, float('inf')),
        channelHelixAngle    = valueOrDefault(state.channelHelixAngle, 0.0),
        channelAspectRatio   = valueOrDefault(state.channelAspectRatio, 1.0))

def valueOrDefault(value, default: float) -> float:

    '''A configuration value, or the default where it was left unset as None or NaN.'''

    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default

    return float(value)

def _sizingState(state) -> 'ChannelSizingState':

    '''

    The engine, coolant and regen section the sizing solve reads, taken from the build state.

    Derived at the point of use rather than up front, because the sizing solve works on the
    trimmed regen section, and the trim is done by the volute interface step that runs before it.

    '''

    return ChannelSizingState(
        channelType                        = state.channelType,
        # Names and a profile rather than numbers, so none of the three goes through
        # valueOrDefault. An absent mode is the search, which is what every configuration
        # written before the manual mode existed asked for without saying so.
        channelSizingMode                  = state.channelSizingMode if isinstance(state.channelSizingMode, str) else 'thermal',
        manualChannelProfile               = state.manualChannelProfile,
        manualChannelProfileKey            = state.manualChannelProfileKey if isinstance(state.manualChannelProfileKey, str) else 'areaRatio',
        # A name rather than a number, so it does not go through valueOrDefault
        gasSideAxialModel                  = state.gasSideAxialModel if isinstance(state.gasSideAxialModel, str) else 'uniform',
        coolantGeometryCorrections         = bool(state.coolantGeometryCorrections),
        coolantRoughnessModel              = state.coolantRoughnessModel if isinstance(state.coolantRoughnessModel, str) else 'dippreySabersky',
        channelSurfaceRoughness            = valueOrDefault(state.channelSurfaceRoughness, float('nan')),
        nChannel                           = state.nChannel,
        numCrossSections                   = state.numCrossSections,
        minChannelRadius                   = state.minChannelRadius,
        minChannelWidth                    = valueOrDefault(state.minChannelWidth, 1.0e-3),
        channelCornerRadius                = valueOrDefault(state.channelCornerRadius, 0.0),
        maxChannelAspectRatio              = valueOrDefault(state.maxChannelAspectRatio, 8.0),
        maxChannelDepth                    = valueOrDefault(state.maxChannelDepth, float('inf')),
        channelHelixAngle                  = valueOrDefault(state.channelHelixAngle, float('nan')),
        channelAspectRatio                 = valueOrDefault(state.channelAspectRatio, 1.0),
        maxWallTemperature                 = state.maxWallTemperature,
        # Left as they arrived, because unset is a real value here: no limit to hold the
        # coolant exit condition to, rather than a limit of zero.
        minCoolantExitPressure             = state.minCoolantExitPressure,
        minCoolantExitTemperature          = state.minCoolantExitTemperature,
        hotWallThickness                   = state.hotWallThickness,
        infillThickness                    = state.infillThickness,
        material                           = state.material,
        coolant                            = state.coolant,
        coolantMassFlow                    = state.coolantMassFlow,
        coolantInitialTemperature          = state.coolantInitialTemperature,
        coolantInitialPressure             = state.coolantInitialPressure,
        chamberPressure                    = state.chamberPressure,
        theoreticalCharacteristicVelocity  = state.theoreticalCharacteristicVelocity,
        nozzleScalingFactor                = state.nozzleScalingFactor,
        throatInletCurvatureNonDimensional = state.throatInletCurvatureNonDimensional,
        throatOutletCurvatureNonDimensional = state.throatOutletCurvatureNonDimensional,
        xRegenNozzle                       = state.xRegenNozzle,
        rRegenNozzle                       = state.rRegenNozzle,
        xRegenNozzleTrimmed                = state.xRegenNozzleTrimmed,
        rRegenNozzleTrimmed                = state.rRegenNozzleTrimmed,
        gammaRegenSectionTrimmed           = state.gammaRegenSectionTrimmed,
        molecularWeightRegenSectionTrimmed = state.molecularWeightRegenSectionTrimmed,
        gasConstantRegenSectionTrimmed     = state.gasConstantRegenSectionTrimmed,
        regenSectionNearWallTemperatureTrimmed = state.regenSectionNearWallTemperatureTrimmed,
        regenSectionNearWallRecoveryTemperatureTrimmed = state.regenSectionNearWallRecoveryTemperatureTrimmed,
        regenSectionFilmDrivingTemperatureTrimmed = state.regenSectionFilmDrivingTemperatureTrimmed,
        regenSectionNearWallMachNumberTrimmed  = state.regenSectionNearWallMachNumberTrimmed,
        regenSectionNearWallPressureTrimmed    = state.regenSectionNearWallPressureTrimmed,
        dcrData                            = state.dcrData)

def solveRegenChannels(state, thermal):

    '''

    This method generates the regenerative cooling jacket geometry for the nozzle. The regen section is trimmed at each end
    where a fillet and flare turn the channel out to its volute. A stepwise (marching) convergence then finds the channel
    radius at each station that holds the hot wall at its temperature limit. The resulting 2D centerline is wrapped in three
    dimensions and the channel geometry is swept along it for rendering with plotly, for use in regenHeatTransferModel() to
    predict performance, and for exporting to .stl for CAD.

    Raises:
        InvalidInputError: If input parameters are invalid or missing
        GeometricConstraintError: If geometric constraints cannot be satisfied
        ThermalConstraintError: If thermal requirements cannot be met
        ConvergenceFailureError: If iterative solvers fail to converge
        PressureDropError: If pressure drop exceeds allowable limits
        NumericalInstabilityError: If calculations produce non-finite values

    '''

    # Validate inputs before expensive calculations
    validateRegenChannelInputs(state)

    # ------------------------------------------------------------------------------------------------------------------------------------ #
    # -- Helper Functions -- #
    # ------------------------------------------------------------------------------------------------------------------------------------ #

    # The cross-section geometry lives in channelGeometry.py, which takes the channel
    # definition explicitly and knows nothing about a Nozzle. These two wrappers supply it.

    def generateCrossSections(xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D,
                              channelRadius, crossSectionStyle, i: int = None, channelWidth = None,
                              ribThickness = None):

        return buildCrossSections(_geometryInputs(state),
                                  xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D,
                                  channelRadius, crossSectionStyle, i = i, channelWidth = channelWidth,
                                  ribThickness = ribThickness)

    def getMaxChannelRadius(rNozzle, i):

        return maxChannelRadius(_geometryInputs(state), rNozzle, i)

    # ------------------------------------------------------------------------------------------------------------------------------------ #
    # -- Generate volute interfaces -- #
    # ------------------------------------------------------------------------------------------------------------------------------------ #

    def generateVoluteInterfaces():

        '''

        Trim the regen section at each end and build the fillet and flare to each volute.

        The inlet volute sits at the aft end of the regen section and the outlet volute at the
        injector face. The outlet interface is `upstreamVoluteInterfaceCurve`, the inlet one
        reflected through a plane normal to the axis, so the outlet is the mirror image of the
        inlet for the same offset, fillet, flare and tilt.

        Author: Isabella Duprey-Churn
        Date:   4/28/2026

        '''

        # ------------------------------------------------------------------------------------------------------------------------------------ #
        # -- Helper Methods -- #
        # ------------------------------------------------------------------------------------------------------------------------------------ #

        def keepStations(keep):

            '''Trim the wall and the gas state on it to the stations the jacket covers.'''

            state.xRegenNozzleTrimmed                    = state.xRegenNozzleTrimmed[keep]
            state.rRegenNozzleTrimmed                    = state.rRegenNozzleTrimmed[keep]
            state.gammaRegenSectionTrimmed               = state.gammaRegenSectionTrimmed[keep]
            state.molecularWeightRegenSectionTrimmed     = state.molecularWeightRegenSectionTrimmed[keep]
            state.gasConstantRegenSectionTrimmed         = state.gasConstantRegenSectionTrimmed[keep]
            state.regenSectionNearWallTemperatureTrimmed = state.regenSectionNearWallTemperatureTrimmed[keep]
            state.regenSectionNearWallRecoveryTemperatureTrimmed = state.regenSectionNearWallRecoveryTemperatureTrimmed[keep]
            if state.regenSectionFilmDrivingTemperatureTrimmed is not None:
                state.regenSectionFilmDrivingTemperatureTrimmed = state.regenSectionFilmDrivingTemperatureTrimmed[keep]
            state.regenSectionNearWallMachNumberTrimmed  = state.regenSectionNearWallMachNumberTrimmed[keep]
            state.regenSectionNearWallPressureTrimmed    = state.regenSectionNearWallPressureTrimmed[keep]

        def filletRadiusAt(flareRoverD, station):

            '''The turn is scaled on the jacket's full radial depth at the station it leaves.'''

            maxChannelRadius = getMaxChannelRadius(state.rRegenNozzleTrimmed, station)

            return flareRoverD * (state.shellThickness + maxChannelRadius*2 + state.hotWallThickness)

        def interfaceToInlet():

            filletRadius = filletRadiusAt(state.inletVoluteFlareRoverD, len(state.xRegenNozzleTrimmed)-1)

            # The volute tilt is the flare angle, which keeps the flare normal to the volute face
            xInterface, rInterface, keep = voluteInterfaceCurve(
                state.xRegenNozzleTrimmed, state.rRegenNozzleTrimmed, state.inletVoluteAxialOffset,
                filletRadius, -np.deg2rad(state.inletVoluteTilt), state.inletVoluteFlareLength)
            keepStations(keep)

            return xInterface, rInterface

        def interfaceToOutlet():

            filletRadius = filletRadiusAt(state.outletVoluteFlareRoverD, 0)

            # The mirror image of the inlet construction, at the injector face
            xInterface, rInterface, keep = upstreamVoluteInterfaceCurve(
                state.xRegenNozzleTrimmed, state.rRegenNozzleTrimmed, state.outletVoluteAxialOffset,
                filletRadius, -np.deg2rad(state.outletVoluteTilt), state.outletVoluteFlareLength)
            keepStations(keep)

            return xInterface, rInterface

        # ------------------------------------------------------------------------------------------------------------------------------------ #
        # -- Generate interfaces -- #
        # ------------------------------------------------------------------------------------------------------------------------------------ #

        # Instantiate trimmed arrays
        # Nozzle wall
        state.xRegenNozzleTrimmed = state.xRegenNozzle.copy()
        state.rRegenNozzleTrimmed = state.rRegenNozzle.copy()
        # Exhaust properties
        state.gammaRegenSectionTrimmed               = state.gammaRegenSection.copy()
        state.molecularWeightRegenSectionTrimmed     = state.molecularWeightRegenSection.copy()
        state.gasConstantRegenSectionTrimmed         = state.gasConstantRegenSection.copy()
        state.regenSectionNearWallTemperatureTrimmed = state.regenSectionNearWallTemperature.copy()
        state.regenSectionNearWallRecoveryTemperatureTrimmed = state.regenSectionNearWallRecoveryTemperature.copy()
        if state.regenSectionFilmDrivingTemperature is not None:
            state.regenSectionFilmDrivingTemperatureTrimmed = state.regenSectionFilmDrivingTemperature.copy()
        state.regenSectionNearWallMachNumberTrimmed  = state.regenSectionNearWallMachNumber.copy()
        state.regenSectionNearWallPressureTrimmed    = state.regenSectionNearWallPressure.copy()

        # Call helpers
        if state.makeInletVolute == 'on':
            state.xInletInterface, state.rInletInterface = interfaceToInlet()
        else:
            state.xInletInterface, state.rInletInterface = [], []
        if state.makeOutletVolute == 'on':
            state.xOutletInterface, state.rOutletInterface = interfaceToOutlet()
        else:
            state.xOutletInterface, state.rOutletInterface = [], []

        # Resize arrays to correct lengths
        if state.makeInletVolute == 'on' or state.makeOutletVolute == 'on':

            xOld = state.xRegenNozzleTrimmed.copy()

            state.xRegenNozzleTrimmed, state.rRegenNozzleTrimmed = \
                arcSpline(state.xRegenNozzleTrimmed,state.rRegenNozzleTrimmed,newNumPoints=state.numCrossSections)

            state.gammaRegenSectionTrimmed = \
                chunkInterpolate(xOld, state.gammaRegenSectionTrimmed,               state.xRegenNozzleTrimmed)
            state.molecularWeightRegenSectionTrimmed = \
                chunkInterpolate(xOld, state.molecularWeightRegenSectionTrimmed,     state.xRegenNozzleTrimmed)
            state.gasConstantRegenSectionTrimmed = \
                chunkInterpolate(xOld, state.gasConstantRegenSectionTrimmed,         state.xRegenNozzleTrimmed)
            state.regenSectionNearWallTemperatureTrimmed = \
                chunkInterpolate(xOld, state.regenSectionNearWallTemperatureTrimmed, state.xRegenNozzleTrimmed)
            state.regenSectionNearWallRecoveryTemperatureTrimmed = \
                chunkInterpolate(xOld, state.regenSectionNearWallRecoveryTemperatureTrimmed, state.xRegenNozzleTrimmed)
            if state.regenSectionFilmDrivingTemperatureTrimmed is not None:
                state.regenSectionFilmDrivingTemperatureTrimmed = \
                    chunkInterpolate(xOld, state.regenSectionFilmDrivingTemperatureTrimmed, state.xRegenNozzleTrimmed)
            state.regenSectionNearWallMachNumberTrimmed = \
                chunkInterpolate(xOld, state.regenSectionNearWallMachNumberTrimmed,  state.xRegenNozzleTrimmed)
            state.regenSectionNearWallPressureTrimmed = \
                chunkInterpolate(xOld, state.regenSectionNearWallPressureTrimmed,    state.xRegenNozzleTrimmed)

        state.numInletInterfaceCS  = len(state.xInletInterface)
        state.numOutletInterfaceCS = len(state.xOutletInterface)
        state.xRegenNozzleInterfaced = np.concatenate([state.xOutletInterface,state.xRegenNozzleTrimmed,state.xInletInterface])
        state.rRegenNozzleInterfaced = np.concatenate([state.rOutletInterface,state.rRegenNozzleTrimmed,state.rInletInterface])

    generateVoluteInterfaces()

    # ------------------------------------------------------------------------------------------------------------------------------------ #
    # -- Generate channel radius distribution -- #
    # ------------------------------------------------------------------------------------------------------------------------------------ #

    # Create channel radius distribution and 2D centerline using dynamic channel radii (DCR) algorithm
    def generateChannelRadii():

        # The sizing loop lives in channelSizing.py, which takes the engine, the coolant and
        # the regen section explicitly and reaches the geometry and thermal modules directly.
        sizingSolution = solveChannelRadii(_sizingState(state), _geometryInputs(state), thermal)

        # Anything the solve left as None is a branch it did not reach, so it is not copied
        # and a value from an earlier step survives rather than being overwritten.
        for name in channelSizingOutputs:
            value = getattr(sizingSolution, name)
            if value is not None:
                setattr(state, name, value)

        state.channelSizingSolution = sizingSolution

    generateChannelRadii()

    # ------------------------------------------------------------------------------------------------------------------------------------ #
    # -- Generate channel centerline  -- #
    # ------------------------------------------------------------------------------------------------------------------------------------ #

    #  Create 3D channel centerline with volute interfacing
    def generateChannelCenterline():

        # ------------------------------------------------------------------------------------------------------------------------------------ #
        # -- Helper Methods -- #
        # ------------------------------------------------------------------------------------------------------------------------------------ #

        def kineosAlgorithm(xCenterline2D, rCenterline2D, channelRadius):

            '''
                Generates the pathline angles for wrapping cooling channels around a rocket nozzle.

                This function implements Kineo's algorithm to maintain equal spacing between channels
                even with varying nozzle diameters.

                Args:
                    xCenterline2D (array)       : Distance of slices along the nozzle axis.
                    rCenterline2D (array)       : Radial distance of slices from the nozzle axis.
                    channelRadius (array)       : Radii of channel cross sections.

                Expected nozzle object properties:
                    nChannel (int)              : Number of cooling channels.
                    infillThickness (float)     : Thickness of the infill material between channels.
                    numCrossSections (int)      : Number of cross-sections along the nozzle.

                Returns:
                    helixPath (array)           : An array of pathline angles in radians.                        

            '''

            # Calculate the distance between slices along the nozzle axis.
            xCenterline2DStep = (np.diff(xCenterline2D))
            # Calculate the radial distance between slices from the nozzle axis.
            rCenterline2DStep = (np.diff(rCenterline2D))

            # Add a zero to the first element of each array to maintain consistent size.
            xCenterline2DStep = np.insert(xCenterline2DStep, 0, 0)
            rCenterline2DStep = np.insert(rCenterline2DStep, 0, 0)

            # Calculate the arc length of the nozzle region allocated to each channel.
            nozzleArcSlice = 2*np.pi*rCenterline2D/state.nChannel - state.infillThickness

            # Calculate the diameter of each channel perpendicular to the pathline.
            channelDiameter = 2 * channelRadius

            # Calculate the arc length of the channel.
            channelArcLength = 4* rCenterline2D * np.arccos((2 * rCenterline2D**2 - (channelDiameter/4)**2) / (2 * rCenterline2D**2))

            # Set the projection angles to 0 if the channels overlap
            indeces = np.where(channelArcLength > nozzleArcSlice)[0]
            channelArcLength[indeces] = nozzleArcSlice[indeces]

            # Calculate the projection angle required to make the channel cross-section
            # equivalent to the region of the nozzle allocated to it.
            projectionAngle = np.real(np.arccos(channelArcLength/nozzleArcSlice))

            # Calculate the arc length of channel movement in the x direction projected on the pathline.
            xArc = 2 * rCenterline2D * np.arccos((2*rCenterline2D**2 - ((xCenterline2DStep*np.tan(projectionAngle))/2)**2)/ (2 * rCenterline2D**2))

            # Calculate the arc length of channel movement in the r direction projected on the pathline.
            rArc = 2 * rCenterline2D * np.arccos((2*rCenterline2D**2 - ((rCenterline2DStep/np.tan(np.pi/2-projectionAngle))/2)**2)/ (2 * rCenterline2D**2))

            # Initialize an array to store the helix path angles.
            helixPath = np.zeros(len(xCenterline2D)) # state.numCrossSections

            # Calculate the position of each pathline point projected on the nozzle wall in degrees.
            # Project the point from the previous axial slice to the next slice and then add
            # the arc length required to position the channel.
            for n in range(len(xCenterline2D)-1):

                helixPath[n+1] = ((helixPath[n] * rCenterline2D[n+1]) - np.sqrt(xArc[n+1]**2 + rArc[n+1]**2)) / rCenterline2D[n+1]

            return helixPath

        # ------------------------------------------------------------------------------------------------------------------------------------ #
        # -- Define Nozzle Contours -- #
        # ------------------------------------------------------------------------------------------------------------------------------------ #

        # Copies and offsets
        xNozzleHotWall, rNozzleHotWall      = state.xRegenNozzle.copy(), state.rRegenNozzle.copy()
        zNozzleHotWallMesh, yNozzleHotWallMesh, xNozzleHotWallMesh      \
            = [np.zeros((state.numCrossSections, state.numCrossSections)) for _ in range(3)]

        shellOffset = state.hotWallThickness + 2.*state.channelRadius + state.shellThickness
        xNozzleShell, rNozzleShell          = parallelOffset(state.xRegenNozzleTrimmed,state.rRegenNozzleTrimmed,shellOffset)
        zNozzleShellMesh, yNozzleShellMesh, xNozzleShellMesh            \
            = [np.zeros((state.numCrossSections, state.numCrossSections)) for _ in range(3)]

        # Rotate
        contourAngles = np.linspace(0, 2*np.pi, state.numCrossSections)
        for i in range(state.numCrossSections):

            zNozzleHotWallMesh[i,:] = rNozzleHotWall[i]   * np.cos(contourAngles)
            yNozzleHotWallMesh[i,:] = rNozzleHotWall[i]   * np.sin(contourAngles)
            xNozzleHotWallMesh[:,i] = xNozzleHotWall

            zNozzleShellMesh[i,:]    = rNozzleShell[i]    * np.cos(contourAngles)
            yNozzleShellMesh[i,:]    = rNozzleShell[i]    * np.sin(contourAngles)
            xNozzleShellMesh[:,i]    = xNozzleShell

        # Assign things to object for reference
        state.xNozzleShell        = xNozzleShell
        state.rNozzleShell        = rNozzleShell

        state.xNozzleHotWallMesh  = xNozzleHotWallMesh
        state.yNozzleHotWallMesh  = yNozzleHotWallMesh
        state.zNozzleHotWallMesh  = zNozzleHotWallMesh

        state.xNozzleShellMesh    = xNozzleShellMesh
        state.yNozzleShellMesh    = yNozzleShellMesh
        state.zNozzleShellMesh    = zNozzleShellMesh

        # ------------------------------------------------------------------------------------------------------------------------------------ #
        # -- 3D Wrapping -- #
        # ------------------------------------------------------------------------------------------------------------------------------------ #

        # -- Get Centerline -- #
        state.channelRadius = np.concatenate([np.ones(state.numOutletInterfaceCS)*state.channelRadius[0],
                                             state.channelRadius,
                                             np.ones(state.numInletInterfaceCS)*state.channelRadius[-1]])
        if state.channelType in ('rectangular', 'helical'):
            # The width, or for a helix the pass spacing, is set at the cold wall along the whole
            # interfaced line, flares included, and the depth may not pass its limits there.
            _, rColdWall = parallelOffset(state.xRegenNozzleInterfaced, state.rRegenNozzleInterfaced, state.hotWallThickness)
            geometry  = _geometryInputs(state)
            if state.channelType == 'rectangular':
                halfLimit = maxHalfExtent('rectangular', rectangularWidth(rColdWall, state.nChannel, state.infillThickness),
                                          geometry.maxChannelAspectRatio, geometry.maxChannelDepth)
            else:
                spacing   = helicalSpacing(rColdWall, state.nChannel, geometry.channelHelixAngle)
                halfLimit = maxHalfExtent('helical', spacing - state.infillThickness, geometry.channelAspectRatio,
                                          geometry.maxChannelDepth)
            state.channelRadius = np.minimum(state.channelRadius, halfLimit)
        else:
            # A circle answers to the room between its neighbors and to the depth limit every
            # family shares, which is the only thing bounding it on a wide bell.
            for i in range(len(state.channelRadius)):
                maxChannelRadius = min(getMaxChannelRadius(state.rRegenNozzleInterfaced, i),
                                       depthLimitedHalfExtent(state.maxChannelDepth))
                if state.channelRadius[i] > maxChannelRadius:
                    state.channelRadius[i] = maxChannelRadius

        # The interfaced line is resampled evenly in arc length, so a station's arc length
        # fraction is its index over the station count. The radius and the two interface
        # boundaries are carried across by that fraction rather than by x, which is not monotonic
        # through a flare.
        xOld, rOld = state.xRegenNozzleInterfaced, state.rRegenNozzleInterfaced
        segmentOld  = np.hypot(np.diff(xOld), np.diff(rOld))
        fractionOld = np.insert(np.cumsum(segmentOld), 0, 0.0) / segmentOld.sum()
        fractionNew = np.linspace(0.0, 1.0, state.numCrossSections)

        state.xRegenNozzleInterfaced, state.rRegenNozzleInterfaced = arcSpline(xOld, rOld, newNumPoints=state.numCrossSections)
        state.channelRadius = np.interp(fractionNew, fractionOld, state.channelRadius)

        # Interpolated onto new stations, a size held at its limit on either side can pass the
        # limit at the station between, so every family is held to its limit again there
        if state.channelType in ('rectangular', 'helical'):
            _, rColdWall = parallelOffset(state.xRegenNozzleInterfaced, state.rRegenNozzleInterfaced, state.hotWallThickness)
            geometry = _geometryInputs(state)
            if state.channelType == 'rectangular':
                halfLimit = maxHalfExtent('rectangular', rectangularWidth(rColdWall, state.nChannel, state.infillThickness),
                                          geometry.maxChannelAspectRatio, geometry.maxChannelDepth)
            else:
                halfLimit = maxHalfExtent('helical', helicalSpacing(rColdWall, state.nChannel, geometry.channelHelixAngle)
                                          - state.infillThickness, geometry.channelAspectRatio, geometry.maxChannelDepth)
            state.channelRadius = np.minimum(state.channelRadius, halfLimit)
        else:
            for i in range(len(state.channelRadius)):
                maxChannelRadius = min(getMaxChannelRadius(state.rRegenNozzleInterfaced, i),
                                       depthLimitedHalfExtent(state.maxChannelDepth))
                if state.channelRadius[i] > maxChannelRadius:
                    state.channelRadius[i] = maxChannelRadius

        if state.numOutletInterfaceCS > 0:
            wallStart = fractionOld[state.numOutletInterfaceCS]
            state.numOutletInterfaceCS = int(np.sum(fractionNew < wallStart))
        if state.numInletInterfaceCS > 0:
            wallEnd = fractionOld[len(xOld) - state.numInletInterfaceCS - 1]
            state.numInletInterfaceCS = int(np.sum(fractionNew > wallEnd))

        offset = np.ones(state.numCrossSections)*state.hotWallThickness + state.channelRadius
        state.xChannelCenterline2D,state.rChannelCenterline2D = parallelOffset(state.xRegenNozzleInterfaced, state.rRegenNozzleInterfaced, offset)

        # The width, depth and rib along the whole line. A circle's width and depth are its
        # diameter; a helix's rib is what its pass spacing leaves.
        xColdWall, rColdWall = parallelOffset(state.xRegenNozzleInterfaced, state.rRegenNozzleInterfaced, state.hotWallThickness)
        if state.channelType == 'rectangular':
            state.channelWidth        = rectangularWidth(rColdWall, state.nChannel, state.infillThickness)
            state.channelRibThickness = np.full(state.numCrossSections, float(state.infillThickness))
        elif state.channelType == 'helical':
            state.channelWidth        = 2*state.channelRadius/valueOrDefault(state.channelAspectRatio, 1.0)
            state.channelRibThickness = helicalSpacing(rColdWall, state.nChannel, state.channelHelixAngle) - state.channelWidth
        else:
            state.channelWidth = 2*state.channelRadius
        state.channelDepth = 2*state.channelRadius

        # -- Get wrap angles -- #
        # A rectangle fills its pitch, so it runs straight. A helix follows its loxodrome over the
        # jacketed wall and runs straight through the volute interfaces.
        if state.channelType == 'rectangular':
            state.wrapAngles = np.zeros(state.numCrossSections)
        elif state.channelType == 'helical':
            meridional = np.insert(np.cumsum(np.hypot(np.diff(xColdWall), np.diff(rColdWall))), 0, 0.0)
            onWall = np.ones(state.numCrossSections, dtype = bool)
            onWall[:state.numOutletInterfaceCS] = False
            onWall[state.numCrossSections - state.numInletInterfaceCS:] = False
            state.wrapAngles = loxodromeWrap(meridional, rColdWall, state.channelHelixAngle, active = onWall)
        else:
            state.wrapAngles = kineosAlgorithm(state.xChannelCenterline2D,state.rChannelCenterline2D,state.channelRadius)

        # -- Wrap -- #
        state.xChannelCenterline3D = state.xChannelCenterline2D.copy()
        state.yChannelCenterline3D = state.rChannelCenterline2D * np.cos(state.wrapAngles)
        state.zChannelCenterline3D = state.rChannelCenterline2D * np.sin(state.wrapAngles)
        state.rChannelCenterline3D = np.sqrt(state.yChannelCenterline3D**2 + state.zChannelCenterline3D**2)

    generateChannelCenterline()

    # ------------------------------------------------------------------------------------------------------------------------------------ #
    # -- Generate channel cross sections and 3D geometry -- #
    # ------------------------------------------------------------------------------------------------------------------------------------ #

    def generate3DChannels():

        # Cold wall mesh
        xNozzleColdWall, rNozzleColdWall    = parallelOffset(state.xRegenNozzleInterfaced,state.rRegenNozzleInterfaced,state.hotWallThickness)
        zNozzleColdWallMesh, yNozzleColdWallMesh, xNozzleColdWallMesh   \
            = [np.zeros((state.numCrossSections, state.numCrossSections)) for _ in range(3)]
        contourAngles = np.linspace(0, 2*np.pi, state.numCrossSections)
        for i in range(state.numCrossSections):
            zNozzleColdWallMesh[i,:] = rNozzleColdWall[i] * np.cos(contourAngles)
            yNozzleColdWallMesh[i,:] = rNozzleColdWall[i] * np.sin(contourAngles)
            xNozzleColdWallMesh[:,i] = xNozzleColdWall
        state.xNozzleColdWallMesh = xNozzleColdWallMesh
        state.yNozzleColdWallMesh = yNozzleColdWallMesh
        state.zNozzleColdWallMesh = zNozzleColdWallMesh

        # Sweep the channel
        state.xChannel, state.yChannel, state.zChannel, _ = \
            generateCrossSections(state.xChannelCenterline3D,state.yChannelCenterline3D,state.zChannelCenterline3D,state.channelRadius,state.channelType,
                                  channelWidth = state.channelWidth, ribThickness = state.channelRibThickness)

    generate3DChannels()

    return state
