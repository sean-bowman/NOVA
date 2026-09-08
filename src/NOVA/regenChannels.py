# -- NOVA: Regenerative Cooling Channel Build -- #

'''

Assembling a regeneratively cooled jacket from a contour and a coolant.

This is the orchestration of the channel build, and it is orchestration rather than physics. The
physics lives in three modules it calls: channelGeometry draws a cross section and sweeps it,
channelSizing converges the radius at each station against a wall temperature, and regenThermal
solves the heat balance those two are converged against.

What happens here is the sequence, and the sequence matters:

    1. Volute interfaces. The regen section is trimmed back at each end to leave a straight
       circular run where a volute attaches, and the turnaround geometry the return volute routes
       around is laid out. Everything downstream works on the trimmed section.
    2. Channel radii. The sizing solve, station by station, which also produces the 2D centreline
       the channel follows and the coolant exit condition.
    3. Channel centreline. The 2D centreline is wrapped into three dimensions around the nozzle,
       and the hot wall, cold wall and shell surfaces are built from it.
    4. Printability audit. Where the channel would print unsupported, those stations are recorded
       so the cross-section builder can compress the flutes toward a circle across them.
    5. Three-dimensional channels. The cross sections are swept along the wrapped centreline into
       the surfaces that get exported, and the nozzle wall point cloud is built.
    6. Cooling jacket. Optionally, all channels merged into one volume rather than kept separate.

Every array the build produces is carried on a RegenChannelState rather than being set on an
object as it goes, so what the build reads and what it produces are both stated in one place.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Nothing here is validated, and nothing here computes a physical result.** The build is
geometry: it decides where a channel runs and what surfaces come out of it. The numbers that
carry physical meaning come from the three modules it calls, and each of those carries its own
validation status, which this inherits unchanged.

What the geometry can be held to is consistency, and the tests do that: a channel that fits
between its neighbours, a centreline that stays on the wall it was offset from, and surfaces that
close.

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
import matplotlib.pyplot as plt
from tqdm import tqdm

from .utils import (DCM, arcSpline, chunkInterpolate, intersection, parallelOffset, plotLine,
                    revolveContour, GeometricConstraintError, InvalidInputError)
from .channelGeometry import (ChannelGeometryInputs,
                              generateCrossSections as buildCrossSections,
                              getMaxChannelRadius as maxChannelRadius)
from .channelSizing import ChannelSizingState, channelSizingOutputs, solveChannelRadii
from .validation import applyRules, arrayRule, integerRule, numericRule, read, textRule

# Plotly backs the interactive channel views only. A plotly-free install loses the .html figures
# and nothing else.
try:
    import plotly
    import plotly.colors
    import plotly.graph_objects as go
    from plotly.offline import plot
    from plotly.express.colors import sample_colorscale
    plotlyAvailable = True
except ImportError:
    plotly = go = plot = sample_colorscale = None
    plotlyAvailable = False

_plotlyNotices = set()

def _plotlyGate(featureName: str) -> bool:

    '''

    True when plotly is importable. Otherwise note once that an interactive view is being
    skipped and return False, so the caller can carry on without it.

    '''

    if plotlyAvailable:
        return True
    if featureName not in _plotlyNotices:
        _plotlyNotices.add(featureName)
        print(f'plotly is not installed; skipping {featureName}. Install it with "pip install plotly".')
    return False

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
    chamberDiameter:                           Any = None
    channelType:                               Any = None
    contourType:                               Any = None
    dataFolder:                                Any = None
    export:                                    Any = None
    fluteAmplitudeCoef:                        Any = None
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
    makeReturnVolute:                          Any = None
    maxOverhangAngle:                          Any = None
    molecularWeightRegenSection:               Any = None
    nChannel:                                  Any = None
    numCSPointsChannel:                        Any = None
    numContourPoints:                          Any = None
    numCrossSections:                          Any = None
    plotJacket:                                Any = None
    plotsAdv:                                  Any = None
    printDirection:                            Any = None
    printabilityCheck:                         Any = None
    rRegenNozzle:                              Any = None
    regenSectionNearWallMachNumber:            Any = None
    regenSectionNearWallPressure:              Any = None
    regenSectionNearWallTemperature:           Any = None
    returnVoluteAxialOffset:                   Any = None
    returnVoluteFlareLen:                      Any = None
    returnVoluteRadialOffset:                  Any = None
    returnVoluteReturnAngle:                   Any = None
    shellThickness:                            Any = None
    xNozzleMesh:                               Any = None
    xRegenNozzle:                              Any = None
    yNozzleMesh:                               Any = None
    zNozzleMesh:                               Any = None

    chamberPressure:                           Any = None
    dcrData:                                   Any = None
    debugMode:                                 Any = None
    interfaceLength:                           Any = None
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
    fluteHelixAngle:                           Any = None
    minChannelRadius:                          Any = None
    numFlutes:                                 Any = None

    # -- Read and written as the build proceeds -- #
    channelRadius:                             Any = None
    gammaRegenSectionTrimmed:                  Any = None
    gasConstantRegenSectionTrimmed:            Any = None
    molecularWeightRegenSectionTrimmed:        Any = None
    nonPrintableIndices:                       Any = None
    numInletInterfaceCS:                       Any = None
    numReturnInterfaceCS:                      Any = None
    rChannelCenterline2D:                      Any = None
    rInletInterface:                           Any = None
    rRegenNozzleInterfaced:                    Any = None
    rRegenNozzleTrimmed:                       Any = None
    rReturnInterface:                          Any = None
    regenSectionNearWallMachNumberTrimmed:     Any = None
    regenSectionNearWallPressureTrimmed:       Any = None
    regenSectionNearWallTemperatureTrimmed:    Any = None
    wrapAngles:                                Any = None
    xAllChannels:                              Any = None
    xChannel:                                  Any = None
    xChannelCenterline2D:                      Any = None
    xChannelCenterline3D:                      Any = None
    xInletInterface:                           Any = None
    xNozzleColdWallMesh:                       Any = None
    xRegenNozzleInterfaced:                    Any = None
    xRegenNozzleTrimmed:                       Any = None
    xReturnInterface:                          Any = None
    yAllChannels:                              Any = None
    yChannel:                                  Any = None
    yChannelCenterline3D:                      Any = None
    yNozzleColdWallMesh:                       Any = None
    zAllChannels:                              Any = None
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
    allNozzlePoints:                           Any = None
    channelSizingSolution:                     Any = None
    rChannelCenterline3D:                      Any = None
    rNozzleShell:                              Any = None
    returnVoluteFlareRad:                      Any = None
    xChannelDefeatured:                        Any = None
    xNozzleHotWallMesh:                        Any = None
    xNozzleShell:                              Any = None
    xNozzleShellMesh:                          Any = None
    yChannelDefeatured:                        Any = None
    yNozzleHotWallMesh:                        Any = None
    yNozzleShellMesh:                          Any = None
    zChannelDefeatured:                        Any = None
    zNozzleHotWallMesh:                        Any = None
    zNozzleShellMesh:                          Any = None

# The fields a build hands back to a Nozzle. Kept beside the class so that adding a field and
# forgetting to surface it is a one-line fix rather than a silent drop. The sizing solve's own
# outputs are appended rather than restated, because the build copies them onto its state by name
# and a static read of this module cannot see that it does.
_buildOutputs = (
    'allNozzlePoints', 'channelRadius', 'channelSizingSolution', 'gammaRegenSectionTrimmed',
    'gasConstantRegenSectionTrimmed', 'molecularWeightRegenSectionTrimmed', 'nonPrintableIndices',
    'numInletInterfaceCS', 'numReturnInterfaceCS', 'rChannelCenterline2D', 'rChannelCenterline3D',
    'rInletInterface', 'rNozzleShell', 'rRegenNozzleInterfaced', 'rRegenNozzleTrimmed',
    'rReturnInterface', 'regenSectionNearWallMachNumberTrimmed',
    'regenSectionNearWallPressureTrimmed', 'regenSectionNearWallTemperatureTrimmed',
    'returnVoluteFlareRad', 'wrapAngles', 'xAllChannels', 'xChannel', 'xChannelCenterline2D',
    'xChannelCenterline3D', 'xChannelDefeatured', 'xInletInterface', 'xNozzleColdWallMesh',
    'xNozzleHotWallMesh', 'xNozzleShell', 'xNozzleShellMesh', 'xRegenNozzleInterfaced',
    'xRegenNozzleTrimmed', 'xReturnInterface', 'yAllChannels', 'yChannel', 'yChannelCenterline3D',
    'yChannelDefeatured', 'yNozzleColdWallMesh', 'yNozzleHotWallMesh', 'yNozzleShellMesh',
    'zAllChannels', 'zChannel', 'zChannelCenterline3D', 'zChannelDefeatured',
    'zNozzleColdWallMesh', 'zNozzleHotWallMesh', 'zNozzleShellMesh')

regenChannelOutputs = tuple(sorted(set(_buildOutputs) | set(channelSizingOutputs)))



# What a channel definition has to say before the jacket can be laid out. Written as a table
# rather than as branches: see validation.py.
#
# Checked in order, so the table runs from the contour the channels sit on, through the channel
# definition itself, to the flute geometry only a fluted channel carries.

def _isFluted(source):

    '''True for a channel whose cross section carries flutes.'''

    return read(source, 'channelType') in ('fluted', 'dataMap')

regenChannelRules = (

    # -- The regen section the channels run along -- #
    arrayRule('xRegenNozzle', 'Regen section axial coordinate', units = 'm'),
    arrayRule('rRegenNozzle', 'Regen section radius', units = 'm',
              positive = True, sameLengthAs = 'xRegenNozzle'),
    integerRule('numCrossSections', 'Cross sections', minimum = 3, exclusiveMinimum = False),

    # -- The channels themselves -- #
    integerRule('nChannel', 'Number of channels', minimum = 10, exclusiveMinimum = False),
    numericRule('minChannelRadius', 'Minimum channel radius', units = 'm',
                minimum = 0.5e-3, exclusiveMinimum = False),
    numericRule('hotWallThickness', 'Hot wall thickness', units = 'm',
                minimum = 0.5e-3, exclusiveMinimum = False),

    # -- The coolant they carry -- #
    textRule('coolant', 'Coolant species',
             note = 'A REFPROP or CoolProp fluid name, such as Hydrogen, O2 or Methane'),
    numericRule('coolantMassFlow', 'Coolant mass flow', units = 'kg/s', minimum = 0),
    numericRule('coolantInitialPressure', 'Coolant inlet pressure', units = 'Pa', minimum = 0),
    numericRule('coolantInitialTemperature', 'Coolant inlet temperature', units = 'K', minimum = 0),

    # -- Flute geometry, which only a fluted cross section carries -- #
    numericRule('fluteHelixAngle', 'Flute helix angle', units = 'deg',
                minimum = -90, maximum = 90, when = _isFluted),
    integerRule('numFlutes', 'Number of flutes', minimum = 3, exclusiveMinimum = False,
                when = _isFluted),
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

def _geometryInputs(state) -> 'ChannelGeometryInputs':

    '''

    The channel definition the cross-section builder reads, taken from the build state.

    Derived at each call rather than once, because two of its fields are filled in as the build
    proceeds: the stations the printability audit marks, and the nozzle wall point cloud the
    compression search queries.

    '''

    return ChannelGeometryInputs(
        numCrossSections     = state.numCrossSections,
        numCSPointsChannel   = state.numCSPointsChannel,
        nChannel             = state.nChannel,
        channelType          = state.channelType,
        hotWallThickness     = state.hotWallThickness,
        infillThickness      = state.infillThickness,
        numFlutes            = state.numFlutes,
        fluteAmplitudeCoef   = state.fluteAmplitudeCoef,
        fluteHelixAngle      = state.fluteHelixAngle,
        interfaceLength      = state.interfaceLength,
        numInletInterfaceCS  = state.numInletInterfaceCS,
        numReturnInterfaceCS = state.numReturnInterfaceCS,
        printabilityCheck    = state.printabilityCheck,
        nonPrintableIndices  = state.nonPrintableIndices,
        allNozzlePoints      = state.allNozzlePoints)

def _sizingState(state) -> 'ChannelSizingState':

    '''

    The engine, coolant and regen section the sizing solve reads, taken from the build state.

    Derived at the point of use rather than up front, because the sizing solve works on the
    trimmed regen section, and the trim is done by the volute interface step that runs before it.

    '''

    return ChannelSizingState(
        channelType                        = state.channelType,
        nChannel                           = state.nChannel,
        numCrossSections                   = state.numCrossSections,
        minChannelRadius                   = state.minChannelRadius,
        maxWallTemperature                 = state.maxWallTemperature,
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
        fluteAmplitudeCoef                 = state.fluteAmplitudeCoef,
        fluteHelixAngle                    = state.fluteHelixAngle,
        xRegenNozzle                       = state.xRegenNozzle,
        rRegenNozzle                       = state.rRegenNozzle,
        xRegenNozzleTrimmed                = state.xRegenNozzleTrimmed,
        rRegenNozzleTrimmed                = state.rRegenNozzleTrimmed,
        gammaRegenSectionTrimmed           = state.gammaRegenSectionTrimmed,
        molecularWeightRegenSectionTrimmed = state.molecularWeightRegenSectionTrimmed,
        gasConstantRegenSectionTrimmed     = state.gasConstantRegenSectionTrimmed,
        regenSectionNearWallTemperatureTrimmed = state.regenSectionNearWallTemperatureTrimmed,
        regenSectionNearWallMachNumberTrimmed  = state.regenSectionNearWallMachNumberTrimmed,
        regenSectionNearWallPressureTrimmed    = state.regenSectionNearWallPressureTrimmed,
        dcrData                            = state.dcrData,
        debugMode                          = state.debugMode)


def solveRegenChannels(state, thermal):

    '''

    This method generates regenerative cooling jacket geometry for the nozzle. Using the inputs from the nozzle config file,
    this method uses a stepwise (or marching) convergence algorithm to find the radius of the cooling channels at each discrete
    point along the length of the nozzle that ensures the nozzle hot wall does not exceed a certain temperature. After this
    initial channel radius distribution and channel pathline are found, volute turnaround paths are generated to interface the
    channel with the inlet and return volutes. Then, the 3D geometry (spirally fluted or circular) of the channels are generated
    for rendering with plotly, for use in regenHeatTransferModel() to predict performance, and for exporting to .stl for CAD.

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
    # definition explicitly and knows nothing about a Nozzle. These two wrappers supply it,
    # rebuilding the inputs on each call because the printability stations and the nozzle
    # point cloud are filled in as this method runs.

    def generateCrossSections(xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D,
                              channelRadius, crossSectionStyle, i: int = None):

        return buildCrossSections(_geometryInputs(state),
                                  xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D,
                                  channelRadius, crossSectionStyle, i = i)

    def getMaxChannelRadius(rNozzle, i):

        return maxChannelRadius(_geometryInputs(state), rNozzle, i)

    # ------------------------------------------------------------------------------------------------------------------------------------ #
    # -- Generate volute interfaces -- #
    # ------------------------------------------------------------------------------------------------------------------------------------ #

    def generateVoluteInterfaces():

        '''

        docustring

        Author: Isabella Duprey-Churn
        Date:   4/28/2026

        '''

        # ------------------------------------------------------------------------------------------------------------------------------------ #
        # -- Helper Methods -- #      
        # ------------------------------------------------------------------------------------------------------------------------------------ #

        def interfaceToInlet():

            # Scope inputs
            flareAngle     = -np.deg2rad(state.inletVoluteTilt) # enforce perpendicularity by using volute tilt angle as flare angle
            flareLength    = state.inletVoluteFlareLength # length of linear extension
            numFlarePoints = 20 # number of points in the linear region, must be >1 to maintain linearity
            if state.channelType == 'circle':
                maxChannelRadiusAtInlet,_ = getMaxChannelRadius(state.rRegenNozzleTrimmed,len(state.xRegenNozzleTrimmed)-1)
            else:
                _,maxChannelRadiusAtInlet = getMaxChannelRadius(state.rRegenNozzleTrimmed,len(state.xRegenNozzleTrimmed)-1)
            filletRadius = state.inletVoluteFlareRoverD * (state.shellThickness + maxChannelRadiusAtInlet*2 + state.hotWallThickness) # radius of curvature for turn

            # Draw the exit plane w/ axial offset
            xExitPlane = np.array([state.xRegenNozzleTrimmed[-1],  state.xRegenNozzleTrimmed[-1]]) - state.inletVoluteAxialOffset
            rExitPlane = np.array([0,                           2*state.rRegenNozzleTrimmed[-1]])
            xExitPlaneOff = xExitPlane - filletRadius
            rExitPlaneOff = rExitPlane

            # Draw the centerline
            xHotWall, rHotWall = parallelOffset(state.xRegenNozzleTrimmed,state.rRegenNozzleTrimmed,filletRadius)

            # Fillet circle
            filletCenter  = intersection(xHotWall,rHotWall,xExitPlaneOff,rExitPlaneOff)
            xFilletCenter = filletCenter[0][0][0]
            rFilletCenter = filletCenter[1][0][0]
            xFilletCircle = 1.0005*filletRadius * np.cos(np.linspace(0,2*np.pi,300)) + xFilletCenter
            rFilletCircle = 1.0005*filletRadius * np.sin(np.linspace(0,2*np.pi,300)) + rFilletCenter
            # Intersect pathline
            hotWallIntersection  = intersection(state.xRegenNozzleTrimmed,state.rRegenNozzleTrimmed,xFilletCircle,rFilletCircle)
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

            # Trim pathline
            trimIndeces = np.where(state.xRegenNozzleTrimmed < xHotWallIntersection)
            state.xRegenNozzleTrimmed = state.xRegenNozzleTrimmed[trimIndeces]
            state.rRegenNozzleTrimmed = state.rRegenNozzleTrimmed[trimIndeces]

            # Append the linear flare to the filleted centerline
            # place several points along flare to maintain linearity through later arcSplines
            xFlare = np.concatenate([xFillet,np.linspace(xFillet[-1],xFlareEnd,numFlarePoints+2)[1:]]) 
            rFlare = np.concatenate([rFillet,np.linspace(rFillet[-1],rFlareEnd,numFlarePoints+2)[1:]])

            state.gammaRegenSectionTrimmed               = state.gammaRegenSection[trimIndeces]
            state.molecularWeightRegenSectionTrimmed     = state.molecularWeightRegenSection[trimIndeces]
            state.gasConstantRegenSectionTrimmed         = state.gasConstantRegenSection[trimIndeces]
            state.regenSectionNearWallTemperatureTrimmed = state.regenSectionNearWallTemperature[trimIndeces]
            state.regenSectionNearWallMachNumberTrimmed  = state.regenSectionNearWallMachNumber[trimIndeces]
            state.regenSectionNearWallPressureTrimmed    = state.regenSectionNearWallPressure[trimIndeces]

            return xFlare, rFlare

        def interfaceToReturn() -> tuple:

            if state.contourType == 'trad':

                trimmedThroatIndex = state.rRegenNozzleTrimmed.argmin()

                turnaroundReturnAngle = np.deg2rad(90 - state.returnVoluteReturnAngle)

                ## Locate the turnaround relative to the existing nozzle converging section
                # The axial and radial offsets are two ways of naming the same station, so
                # exactly one of them is a well-posed request. Giving both leaves the station
                # ambiguous and giving neither leaves it undefined.
                hasAxialOffset  = not np.isnan(state.returnVoluteAxialOffset)
                hasRadialOffset = not np.isnan(state.returnVoluteRadialOffset)

                if hasAxialOffset == hasRadialOffset:
                    raise InvalidInputError(
                        message = ('The return volute turnaround is located by exactly one of '
                                   'returnVoluteAxialOffset or returnVoluteRadialOffset; '
                                   f'{"both were" if hasAxialOffset else "neither was"} specified'),
                        parameterName = 'returnVoluteAxialOffset, returnVoluteRadialOffset',
                        value = (state.returnVoluteAxialOffset, state.returnVoluteRadialOffset),
                        validRange = 'Exactly one specified, the other left unset')

                # Axial offset option
                if hasAxialOffset:
                    xHotWallConverging   = state.xRegenNozzleTrimmed[:trimmedThroatIndex]
                    # Find the point on the contour that aligns most closely with the axial offset requested
                    returnTurnaroundIndex = np.abs(xHotWallConverging - (xHotWallConverging[0] + state.returnVoluteAxialOffset)).argmin()

                # Radial offset option
                else:
                    returnTurnaroundIndex = np.abs(state.rRegenNozzleTrimmed[:trimmedThroatIndex] - (0.5*state.chamberDiameter-state.returnVoluteRadialOffset)).argmin()

                # The index is reused as the point count of the resampled turnaround curve, so
                # a station at the very start of the contour leaves nothing to resample onto.
                if returnTurnaroundIndex < 2:
                    raise GeometricConstraintError(
                        message = ('The requested return volute turnaround sits at the start of the '
                                   'converging section, leaving no contour to interface to'),
                        constraintType = 'returnVoluteTurnaroundStation',
                        value = returnTurnaroundIndex,
                        limit = 2)

                # Create the turnaround turn
                if state.channelType == 'circle':
                    maxChannelRadiusAtReturn,_ = getMaxChannelRadius(state.rRegenNozzleTrimmed,0)
                else:
                    _,maxChannelRadiusAtReturn = getMaxChannelRadius(state.rRegenNozzleTrimmed,0)
                turnaroundRadius = state.inletVoluteFlareRoverD * (state.shellThickness + maxChannelRadiusAtReturn*2 + state.hotWallThickness)
                turnaroundLength = state.returnVoluteFlareLen
                state.returnVoluteFlareRad = turnaroundRadius

                # Calculate angle of the nozzle contour at the interface location between the two curves to guarantee tangency
                angleAtTurnaroundStart = np.arctan2(abs(state.rRegenNozzleTrimmed[returnTurnaroundIndex] - state.rRegenNozzleTrimmed[returnTurnaroundIndex - 1]),
                                                    abs(state.xRegenNozzleTrimmed[returnTurnaroundIndex] - state.xRegenNozzleTrimmed[returnTurnaroundIndex - 1]))
                turnaroundAngles       = np.linspace(3*np.pi/2 - angleAtTurnaroundStart, turnaroundReturnAngle, int(np.floor(state.numContourPoints / 4)))

                turnaroundCenterX = state.xRegenNozzleTrimmed[returnTurnaroundIndex] + turnaroundRadius * np.cos(np.pi/2 - angleAtTurnaroundStart)
                turnaroundCenterR = state.rRegenNozzleTrimmed[returnTurnaroundIndex] + turnaroundRadius * np.sin(np.pi/2 - angleAtTurnaroundStart)

                turnaroundX = turnaroundRadius * np.cos(turnaroundAngles) + turnaroundCenterX
                turnaroundR = turnaroundRadius * np.sin(turnaroundAngles) + turnaroundCenterR

                fluidReturnX = turnaroundX[-1] + turnaroundLength * np.sin(turnaroundReturnAngle)
                fluidReturnR = turnaroundR[-1] - turnaroundLength * np.cos(turnaroundReturnAngle)

                fullReturnX = np.concatenate([turnaroundX, np.linspace(turnaroundX[-1], fluidReturnX,100)[1:]])
                fullReturnR = np.concatenate([turnaroundR, np.linspace(turnaroundR[-1], fluidReturnR,100)[1:]])

                state.xRegenNozzleTrimmed    = state.xRegenNozzleTrimmed[returnTurnaroundIndex:]
                state.rRegenNozzleTrimmed    = state.rRegenNozzleTrimmed[returnTurnaroundIndex:]

                xReturnTurnaround, rReturnTurnaround = fullReturnX[1:-1], fullReturnR[1:-1]
                xReturnTurnaround, rReturnTurnaround = arcSpline(xReturnTurnaround, rReturnTurnaround, newNumPoints = returnTurnaroundIndex)

                state.gammaRegenSectionTrimmed               = state.gammaRegenSectionTrimmed[returnTurnaroundIndex:]
                state.molecularWeightRegenSectionTrimmed     = state.molecularWeightRegenSectionTrimmed[returnTurnaroundIndex:]
                state.gasConstantRegenSectionTrimmed         = state.gasConstantRegenSectionTrimmed[returnTurnaroundIndex:]
                state.regenSectionNearWallTemperatureTrimmed = state.regenSectionNearWallTemperatureTrimmed[returnTurnaroundIndex:]
                state.regenSectionNearWallMachNumberTrimmed  = state.regenSectionNearWallMachNumberTrimmed[returnTurnaroundIndex:]
                state.regenSectionNearWallPressureTrimmed    = state.regenSectionNearWallPressureTrimmed[returnTurnaroundIndex:]

                return np.flip(xReturnTurnaround), np.flip(rReturnTurnaround)
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
        state.regenSectionNearWallMachNumberTrimmed  = state.regenSectionNearWallMachNumber.copy()
        state.regenSectionNearWallPressureTrimmed    = state.regenSectionNearWallPressure.copy()

        # Call helpers
        if state.makeInletVolute == 'on':
            state.xInletInterface, state.rInletInterface = interfaceToInlet()
        else:
            state.xInletInterface, state.rInletInterface = [], []
        if state.makeReturnVolute == 'on':
            state.xReturnInterface, state.rReturnInterface = interfaceToReturn()
        else:
            state.xReturnInterface, state.rReturnInterface = [], []

        # Resize arrays to correct lengths
        if state.makeInletVolute == 'on' or state.makeReturnVolute == 'on':

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
            state.regenSectionNearWallMachNumberTrimmed = \
                chunkInterpolate(xOld, state.regenSectionNearWallMachNumberTrimmed,  state.xRegenNozzleTrimmed)  
            state.regenSectionNearWallPressureTrimmed = \
                chunkInterpolate(xOld, state.regenSectionNearWallPressureTrimmed,    state.xRegenNozzleTrimmed)  

        state.numInletInterfaceCS  = len(state.xInletInterface)
        state.numReturnInterfaceCS = len(state.xReturnInterface)
        state.xRegenNozzleInterfaced = np.concatenate([state.xReturnInterface,state.xRegenNozzleTrimmed,state.xInletInterface])
        state.rRegenNozzleInterfaced = np.concatenate([state.rReturnInterface,state.rRegenNozzleTrimmed,state.rInletInterface])

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
                    infillThickness (float)     : Thickness of the infill material berween channels.
                    fluteAmplitudeCoef (float)  : Coefficient for the flute amplitude.
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

            # Calculate the diameter of each channel perpendicular to the pathline,
            # including the flute amplitude.
            if state.channelType == 'fluted':
                channelDiameter = (2*channelRadius + state.fluteAmplitudeCoef*channelRadius)
            elif state.channelType == 'circle':
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

        shellOffset = state.hotWallThickness + 2.*state.channelRadius + state.fluteAmplitudeCoef*state.channelRadius + state.shellThickness
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
        state.channelRadius = np.concatenate([np.ones(state.numReturnInterfaceCS)*state.channelRadius[0],
                                             state.channelRadius,
                                             np.ones(state.numInletInterfaceCS)*state.channelRadius[-1]])
        for i in range(len(state.channelRadius)):
            if state.channelType == 'fluted':
                _, maxChannelRadius = getMaxChannelRadius(state.rRegenNozzleInterfaced,i)
            else:
                maxChannelRadius, _ = getMaxChannelRadius(state.rRegenNozzleInterfaced,i)
            if state.channelRadius[i] > maxChannelRadius:
                state.channelRadius[i] = maxChannelRadius
        xOld = state.xRegenNozzleInterfaced
        state.xRegenNozzleInterfaced, state.rRegenNozzleInterfaced = arcSpline(state.xRegenNozzleInterfaced, state.rRegenNozzleInterfaced,
                                                                            newNumPoints=state.numCrossSections)
        state.channelRadius = chunkInterpolate(xOld,state.channelRadius,state.xRegenNozzleInterfaced)
        offset = np.ones(state.numCrossSections)*state.hotWallThickness + state.channelRadius
        state.xChannelCenterline2D,state.rChannelCenterline2D = parallelOffset(state.xRegenNozzleInterfaced, state.rRegenNozzleInterfaced, offset)

        # -- Get wrap angles -- #
        state.wrapAngles = kineosAlgorithm(state.xChannelCenterline2D,state.rChannelCenterline2D,state.channelRadius)

        # -- Wrap -- #
        state.xChannelCenterline3D = state.xChannelCenterline2D.copy()
        state.yChannelCenterline3D = state.rChannelCenterline2D * np.cos(state.wrapAngles)
        state.zChannelCenterline3D = state.rChannelCenterline2D * np.sin(state.wrapAngles)
        state.rChannelCenterline3D = np.sqrt(state.yChannelCenterline3D**2 + state.zChannelCenterline3D**2)

    generateChannelCenterline()

    if state.printabilityCheck == 'on':

        def printabilityAudit():

            '''

            Check for regions of channel geometry that will exceed the defined maximum overhang angle for printing

            '''

            # Check for print direction and locally scope variables
            if state.printDirection == 'FEU':
                xChannelCenterline3D = state.xChannelCenterline3D
                yChannelCenterline3D = state.yChannelCenterline3D
                zChannelCenterline3D = state.zChannelCenterline3D
            elif state.printDirection == 'FED':
                xChannelCenterline3D = -state.xChannelCenterline3D
                yChannelCenterline3D = state.yChannelCenterline3D
                zChannelCenterline3D = state.zChannelCenterline3D

            pathAnglesY, pathAnglesZ = [np.zeros(len(xChannelCenterline3D)) for _ in range(2)]
            # Calculate angles with respect to print direction
            for i in range(1, len(xChannelCenterline3D)-1):
                pathAnglesY[i] = np.rad2deg(np.arctan((xChannelCenterline3D[i+1] - xChannelCenterline3D[i-1]) / (yChannelCenterline3D[i+1] - yChannelCenterline3D[i-1])))
                pathAnglesZ[i] = np.rad2deg(np.arctan((xChannelCenterline3D[i+1] - xChannelCenterline3D[i-1]) / (zChannelCenterline3D[i+1] - zChannelCenterline3D[i-1])))

            # Calculate first and last angles with forward/backward differencing
            pathAnglesY[0] = np.rad2deg(np.arctan((xChannelCenterline3D[1] - xChannelCenterline3D[0]) / (yChannelCenterline3D[1] - yChannelCenterline3D[0])))
            pathAnglesY[-1] = np.rad2deg(np.arctan((xChannelCenterline3D[-1] - xChannelCenterline3D[-2]) / (yChannelCenterline3D[-1] - yChannelCenterline3D[-2])))

            pathAnglesZ[0] = np.rad2deg(np.arctan((xChannelCenterline3D[1] - xChannelCenterline3D[0]) / (zChannelCenterline3D[1] - zChannelCenterline3D[0])))
            pathAnglesZ[-1] = np.rad2deg(np.arctan((xChannelCenterline3D[-1] - xChannelCenterline3D[-2]) / (zChannelCenterline3D[-1] - zChannelCenterline3D[-2])))

            # Assign ranges for printability
            printableRangeY = abs(pathAnglesY) < state.maxOverhangAngle
            printableRangeZ = abs(pathAnglesZ) < state.maxOverhangAngle

            printableRange = np.logical_or(printableRangeY, printableRangeZ)
            nonPrintableIndices = [index for index, value in enumerate(printableRange) if value]

            printableY    = yChannelCenterline3D.copy()
            notPrintableY = yChannelCenterline3D.copy()
            printableZ    = zChannelCenterline3D.copy()
            notPrintableZ = zChannelCenterline3D.copy()

            printableY[printableRangeY]     = 'NaN'
            notPrintableY[~printableRangeY] = 'NaN'
            printableZ[printableRangeZ]     = 'NaN'
            notPrintableZ[~printableRangeZ] = 'NaN'

            state.nonPrintableIndices = nonPrintableIndices

            if state.nonPrintableIndices:
                indexGap = 5
                numCompressions = len([val for val in np.diff(state.nonPrintableIndices) if val > indexGap]) + 1
                print(f'{numCompressions} areas located that exceed {state.maxOverhangAngle} degree overhang angle')

            if state.plotsAdv == 'on' and _plotlyGate('advanced 3D channel views'):
                plotLine(xChannelCenterline3D[nonPrintableIndices], yChannelCenterline3D[nonPrintableIndices], zChannelCenterline3D[nonPrintableIndices],
                            lineStyle = '', markerStyle = '*', color = 'red')
                plt.plot(xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, 'g')
                plt.gca().plot_surface(state.xNozzleMesh, state.yNozzleMesh, state.zNozzleMesh, alpha = 0.5)
                plt.gca().set_aspect('equal')

        print(f'Running printability audit')

        printabilityAudit()      

    # ------------------------------------------------------------------------------------------------------------------------------------ #
    # -- Generate channel cross sections and 3D geometry -- #      
    # ------------------------------------------------------------------------------------------------------------------------------------ #       

    def generate3DChannels():

        # Concatenated cold wall mesh for gaussian compression search
        xNozzleColdWall, rNozzleColdWall    = parallelOffset(state.xRegenNozzleInterfaced,state.rRegenNozzleInterfaced,state.hotWallThickness)
        zNozzleColdWallMesh, yNozzleColdWallMesh, xNozzleColdWallMesh   \
            = [np.zeros((state.numCrossSections, state.numCrossSections)) for _ in range(3)]
        contourAngles = np.linspace(0, 2*np.pi, state.numCrossSections)
        for i in range(state.numCrossSections):            
            zNozzleColdWallMesh[i,:] = rNozzleColdWall[i] * np.cos(contourAngles)
            yNozzleColdWallMesh[i,:] = rNozzleColdWall[i] * np.sin(contourAngles)
            xNozzleColdWallMesh[:,i] = xNozzleColdWall
        allNozzlePoints, nozzlePoints = [np.zeros((state.numCrossSections,3)) for _ in range(2)]
        allNozzlePoints[:,0] = zNozzleColdWallMesh[0,:]
        allNozzlePoints[:,1] = xNozzleColdWallMesh[0,:]
        allNozzlePoints[:,2] = yNozzleColdWallMesh[0,:]
        for i in range(state.numCrossSections-1):
            nozzlePoints[:,0] = zNozzleColdWallMesh[i+1,:]
            nozzlePoints[:,1] = xNozzleColdWallMesh[i+1,:]
            nozzlePoints[:,2] = yNozzleColdWallMesh[i+1,:]
            allNozzlePoints   = np.append(allNozzlePoints,nozzlePoints,0)
        state.xNozzleColdWallMesh = xNozzleColdWallMesh
        state.yNozzleColdWallMesh = yNozzleColdWallMesh
        state.zNozzleColdWallMesh = zNozzleColdWallMesh
        state.allNozzlePoints = allNozzlePoints        

        # Get update interface lengths
        xInletTrim  = state.xRegenNozzleTrimmed[-1]
        xReturnTrim = state.xRegenNozzleTrimmed[ 0]

        PoI = np.where(np.diff(np.sign(np.diff(state.xRegenNozzleInterfaced))) != 0)[0]

        if state.makeInletVolute == 'on':
            try:
                inletValidRange = range(PoI[-2],PoI[-1])
                state.numInletInterfaceCS   = state.numCrossSections - np.argmin(np.abs(state.xRegenNozzleInterfaced[inletValidRange]  - xInletTrim))
                state.numInletInterfaceCS  -= PoI[-2]
            except:
                inletValidRange = range(0,PoI[0])
                state.numInletInterfaceCS   = state.numCrossSections - np.argmin(np.abs(state.xRegenNozzleInterfaced[inletValidRange]  - xInletTrim))
        if state.makeReturnVolute == 'on':
            try:
                returnValidRange = range(PoI[0],PoI[1])
                state.numReturnInterfaceCS  = np.argmin(np.abs(state.xRegenNozzleInterfaced[returnValidRange] - xReturnTrim))
                state.numReturnInterfaceCS += PoI[0]
            except:
                returnValidRange = range(PoI[0],state.numCrossSections)
                state.numReturnInterfaceCS  = np.argmin(np.abs(state.xRegenNozzleInterfaced[returnValidRange] - xReturnTrim))
                state.numReturnInterfaceCS += PoI[0]

        # Create standard (user-specified) channel
        state.xChannel, state.yChannel, state.zChannel, _ = \
            generateCrossSections(state.xChannelCenterline3D,state.yChannelCenterline3D,state.zChannelCenterline3D,state.channelRadius,state.channelType)

        # Create defeatured (circle) channel along pre-established 3D centerline for full 3D analysis
        if state.channelType == 'fluted' and state.export == 'on':
            state.xChannelDefeatured, state.yChannelDefeatured, state.zChannelDefeatured, _ = \
                generateCrossSections(state.xChannelCenterline3D,state.yChannelCenterline3D,state.zChannelCenterline3D,state.channelRadius,'circle')

    generate3DChannels()

    # ------------------------------------------------------------------------------------------------------------------------------------ #
    # -- Generate cooling jacket -- #      
    # ------------------------------------------------------------------------------------------------------------------------------------ #

    # Rotate copies of channel around nozzle to generate full jacket
    def generateCoolingJacket(xChannel,yChannel,zChannel):

        '''

        Private method to wrap the code that generates the cooling jacket.

        '''

        xAllChannels,  yAllChannels, zAllChannels = \
        [np.zeros((state.numCSPointsChannel,state.numCrossSections,state.nChannel)) for _ in range(3)]

        for m in tqdm(range(state.nChannel), desc="Generating Jacket Geometry", colour="#ABD038"):

            for p in range(state.numCrossSections):

                valueMatrix = [xChannel[:,p], yChannel[:,p], zChannel[:,p]]
                eulerAngles = [2*m*np.pi/state.nChannel, 0, 0]
                xAllChannels[:,p,m], yAllChannels[:,p,m], zAllChannels[:,p,m] \
                = DCM(eulerAngles, valueMatrix, transpose = False, rotationOrder = 'xyz')
                xAllChannels[:,p,m] = xAllChannels[:,p,m].T
                yAllChannels[:,p,m] = yAllChannels[:,p,m].T
                zAllChannels[:,p,m] = zAllChannels[:,p,m].T

        return xAllChannels, yAllChannels, zAllChannels

    if  state.makeCoolingChannels == 'jacket':

        state.xAllChannels, state.yAllChannels, state.zAllChannels = generateCoolingJacket(state.xChannel, state.yChannel, state.zChannel)

    # ------------------------------------------------------------------------------------------------------------------------------------ #
    # -- Plots -- #      
    # ------------------------------------------------------------------------------------------------------------------------------------ #

    if state.plotsAdv == 'on' and _plotlyGate('advanced 3D channel views'):

        xPrint, yPrint, zPrint = revolveContour([min(state.xRegenNozzle),max(state.xRegenNozzle)],[0.5*state.chamberDiameter,0.5*state.chamberDiameter])

        colori = sample_colorscale(plotly.colors.cyclical.HSV,
                        list(np.linspace(0,1,int(np.ceil(state.numCrossSections/5)))))
        colorii = colori.copy()
        for i in range(5):
            colorii = np.append(colorii,colori)

        if state.makeCoolingChannels == 'jacket':

            # -- Three Channel Mesh View -- #
            fig = go.Figure()
            # Print volume reference
            fig.add_trace(go.Surface(x = yPrint , y = zPrint , z = xPrint,
                                colorscale = [[0,'darkgrey'],[1,'darkgrey']],
                                opacity = 0.3,
                                showscale = False))
            # Nozzle wall reference
            fig.add_trace(go.Surface(x = state.zNozzleColdWallMesh , y = state.xNozzleColdWallMesh , z = state.yNozzleColdWallMesh,
                                colorscale = [[0,'darkgrey'],[1,'darkgrey']],
                                opacity = 0.8,
                                showscale = False))
            # Interfaced channels
            fig.add_trace(go.Surface(x = state.zAllChannels[:,:,2], y = state.xAllChannels[:,:,2], z = state.yAllChannels[:,:,2], 
                                    colorscale = [[0, 'yellow'], [1,'yellow']],
                                    opacity = .999,
                                    showscale = False))
            fig.add_trace(go.Surface(x = state.zAllChannels[:,:,1], y = state.xAllChannels[:,:,1], z = state.yAllChannels[:,:,1], 
                                    colorscale = [[0, 'cyan'], [1,'cyan']],
                                    opacity = 1,
                                    showscale = False))
            fig.add_trace(go.Surface(x = state.zAllChannels[:,:,3], y = state.xAllChannels[:,:,3], z = state.yAllChannels[:,:,3], 
                                    colorscale = [[0, 'magenta'], [1,'magenta']],
                                    opacity = 1,
                                    showscale = False))
            # Centerline
            fig.add_trace(go.Scatter3d(x = state.zChannelCenterline3D, y = state.xChannelCenterline3D, z = state.yChannelCenterline3D,
                                        mode = 'lines',
                                        line = dict(color = 'red',
                                                width = 10)))
            # Cross section traces
            for i in range(state.numCrossSections):
                fig.add_trace(go.Scatter3d(x = state.zAllChannels[:,i,2], y = state.xAllChannels[:,i,2],z = state.yAllChannels[:,i,2],
                                        mode = 'lines',
                                        opacity = 0.8,
                                        line = dict(color = colorii[i],
                                                    width = 10),
                                        name = f'CS {i}'))
            # Finish
            fig.update_layout(scene = dict(xaxis_title = 'Nozzle Radius [m]',
                                    yaxis_title = 'Nozzle Axis [m]',
                                    zaxis_title = 'Nozzle Radius [m]'),
                                    title = {'text': 'Three Channel Mesh View',
                                                'x': 0.5,
                                                'xanchor': 'center',
                                                'y': 0.9,
                                                'yanchor': 'top'},
                                    scene_aspectmode = 'data',
                                    template = 'plotly_dark',
                                    showlegend = False)
            if state.export == 'on':
                print(f'Saving Three Channel Mesh View to .html')
                plot(fig, filename = state.dataFolder + '\\threeChannelMeshViewInterfaced.html')
            else:
                fig.show()

            if state.plotJacket == 'on' and _plotlyGate('the full regen jacket view'):

                colori = sample_colorscale(plotly.colors.cyclical.HSV,
                                        list(np.linspace(0,1,state.nChannel)))

                fig = go.Figure()
                fig.add_trace(go.Surface(x = state.zNozzleColdWallMesh, y = state.xNozzleColdWallMesh, z = state.yNozzleColdWallMesh, 
                                        colorscale = [[0, 'cyan'], [1,'cyan']],
                                        opacity = 0.5,
                                        showscale = False))
                for i in range(state.nChannel):
                    fig.add_trace(go.Surface(x = state.zAllChannels[:,:,i], y = state.xAllChannels[:,:,i], z = state.yAllChannels[:,:,i], 
                                        colorscale = [[0, colori[i]], [1,colori[i]]],
                                        opacity = 1,
                                        showscale = False))
                fig.update_layout(scene = dict(xaxis_title = 'Nozzle Radius [m]',
                                        yaxis_title = 'Nozzle Axis [m]',
                                        zaxis_title = 'Nozzle Radius [m]'),
                                        title = {'text': 'Regen Jacket',
                                                    'x': 0.5,
                                                    'xanchor': 'center',
                                                    'y': 0.9,
                                                    'yanchor': 'top'},
                                        scene_aspectmode = 'data',
                                        template = 'plotly_dark')
                                #   scene_camera = dict(eye = dict(x = 0, y = 2, z = 0))) # good for comparing wrap angles
                if state.export == 'on':
                    print(f'Saving Full Regen Jacket View to .html')
                    plot(fig, filename = state.dataFolder + '\\regenJacketView.html')
                else:
                    fig.show()
        else:

            # -- One Channel Mesh View -- #
            fig = go.Figure()
            # Print volume reference
            fig.add_trace(go.Surface(x = yPrint , y = zPrint , z = xPrint,
                                colorscale = [[0,'darkgrey'],[1,'darkgrey']],
                                opacity = 0.3,
                                showscale = False))
            # Nozzle wall reference
            fig.add_trace(go.Surface(x = state.zNozzleColdWallMesh , y = state.xNozzleColdWallMesh , z = state.yNozzleColdWallMesh,
                                colorscale = [[0,'darkgrey'],[1,'darkgrey']],
                                opacity = 0.8,
                                showscale = False))
            # Interfaced channels
            fig.add_trace(go.Surface(x = state.zChannel, y = state.xChannel, z = state.yChannel, 
                                    colorscale = [[0, 'yellow'], [1,'yellow']],
                                    opacity = .975,
                                    showscale = False))
            fig.add_trace(go.Scatter3d(x = state.zChannelCenterline3D, y = state.xChannelCenterline3D, z = state.yChannelCenterline3D,
                                        mode = 'lines',
                                        line = dict(color = 'red',
                                                width = 10)))
            # Cross section traces
            for i in range(state.numCrossSections):
                fig.add_trace(go.Scatter3d(x = state.zChannel[:,i], y = state.xChannel[:,i],z = state.yChannel[:,i],
                                    mode = 'lines',
                                    opacity = 0.8,
                                    line = dict(color = colorii[i],
                                                width = 10),
                                    name = f'CS {i}'))
            # Finish
            fig.update_layout(scene = dict(xaxis_title = 'Nozzle Radius [m]',
                                    yaxis_title = 'Nozzle Axis [m]',
                                    zaxis_title = 'Nozzle Radius [m]'),
                                    title = {'text': 'Channel Mesh View',
                                                'x': 0.5,
                                                'xanchor': 'center',
                                                'y': 0.9,
                                                'yanchor': 'top'},
                                    scene_aspectmode = 'data',
                                    template = 'plotly_dark',
                                    showlegend = False)
            if state.export == 'on':
                print(f'Saving Three Channel Mesh View to .html')
                plot(fig, filename = state.dataFolder + '\\threeChannelMeshViewInterfaced.html')
            else:
                fig.show()

    return state
