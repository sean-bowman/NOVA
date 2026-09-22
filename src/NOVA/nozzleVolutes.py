
# -- NOVA: Regenerative Cooling Volutes -- #

'''

The manifolds that feed the cooling channels and collect them again.

A regeneratively cooled jacket has to get coolant in and out. Sixty channels cannot each have
their own feedline, so they are gathered into a scroll that wraps the nozzle once: the inlet
volute distributes flow from a single interface into every channel, and the return volute
collects it back. Each is a duct whose cross section grows around the scroll in proportion to
the flow it is carrying, which is what keeps the velocity, and so the distribution between
channels, roughly even.

The scroll geometry itself lives in Volute.py, which draws one from a scroll radius, a cross
section family and an area distribution. What happens here is everything around it: reading the
channel ends the volute has to attach to, sizing its wall against the pressure and temperature
the coolant is at, and growing the print supports an unsupported scroll needs.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**The wall thickness is a hoop stress calculation against manufacturer data.** It is as good as
that data. The thickness follows from the pressure differential, the local radius and an
allowable stress read from the alloy's yield curve at the coolant temperature. The curves are
manufacturer figures interpolated on a cubic spline, and the spline extrapolates outside the
data it was given without saying so. That is worth knowing: a lookup below the lowest datum
returns a number that no measurement supports.

**Nothing else here is validated.** The scroll area distribution, the flare into the interface
and the print supports are geometry, and the claim made for them is that they close and that
they clear what they are meant to clear.

----------------------------------------------------------------------
                        Geometry conventions
----------------------------------------------------------------------

Volute geometry follows the cooling channel convention:

    - X is the direction of the outgoing fluid at the volute interface
    - Y is orthogonal to X in the plane of the volute scroll
    - Z completes the set and is the nozzle axis

All units are mass base SI, except the Grayloc interface diameters, which are named in inches
because that is how the fittings are specified:
    - Length      [m]
    - Pressure    [Pa]
    - Temperature [K]
    - Stress      [Pa]
    - Angle       [deg] where a configuration names one

Author: Sean Bowman

'''

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.interpolate import CubicSpline

from . import units
from .geometryTools import DCM
from .errors import InvalidInputError, VoluteGenerationError, createErrorContext
from .Volute import Volute
from .validation import applyRules, arrayRule, presentRule

# What a volute needs from the channel build it attaches to. The volute is grown onto the ends of
# the channels, so what it reads is geometry the sizing solve produced rather than configuration.

regenVoluteRules = (
    arrayRule('channelRadius', 'Channel radius distribution', units = 'm', positive = True),
    presentRule('xChannelCenterline2D', 'Channel centerline axial coordinate'),
    presentRule('rChannelCenterline2D', 'Channel centerline radius'),
)

def validateRegenVoluteInputs(state) -> None:

    '''

    Check that the channels a volute attaches to have been built.

    The rules are the table above, checked by `validation.applyRules`.

    Parameters:
    -----------
    state : RegenVoluteState
        The configuration to check.

    Raises:
    -------
    InvalidInputError
        On the first rule the configuration fails.

    '''

    applyRules(state, regenVoluteRules)

@dataclass
class RegenVoluteState:

    '''

    Everything the volute build reads, and everything it produces.

    The fields are grouped by how the build uses them: the channel ends and the volute definition
    it works from, and the scroll, shell and support surfaces it produces.

    Every field starts as None. One still None after a build is a volute that was not asked for,
    which is worth keeping rather than hiding behind an empty array.

    '''

    # -- What the volute build reads -- #
    channelRadius:                         Any = None
    coolantExitPressure:                   Any = None
    coolantExitTemperature:                Any = None
    coolantInitialPressure:                Any = None
    coolantInitialTemperature:             Any = None
    dataFolder:                            Any = None
    export:                                Any = None
    inletGraylocDiameter:                  Any = None
    inletVoluteAlignment:                  Any = None
    inletVoluteCrossSection:               Any = None
    inletVolutePrintability:               Any = None
    inletVoluteTilt:                       Any = None
    makeInletVolute:                       Any = None
    makeReturnVolute:                      Any = None
    numCSPointsVolute:                     Any = None
    numCSVolute:                           Any = None
    rChannelCenterline2D:                  Any = None
    returnGraylocDiameter:                 Any = None
    returnVoluteAlignment:                 Any = None
    returnVoluteCrossSection:              Any = None
    returnVolutePrintability:              Any = None
    returnVoluteTilt:                      Any = None
    voluteFOS:                             Any = None
    voluteRelativeRoll:                    Any = None
    xChannelCenterline2D:                  Any = None

    # -- Read and written as the volutes are grown -- #
    inletVolute:                           Any = None
    returnVolute:                          Any = None
    xInletVolute:                          Any = None
    xInletVoluteShell:                     Any = None
    xInletVoluteSupportLower:              Any = None
    xInletVoluteSupportUpper:              Any = None
    xInletVoluteSupportWall:               Any = None
    xReturnVolute:                         Any = None
    xReturnVoluteShell:                    Any = None
    xReturnVoluteSupportLower:             Any = None
    xReturnVoluteSupportUpper:             Any = None
    xReturnVoluteSupportWall:              Any = None
    yInletVolute:                          Any = None
    yInletVoluteShell:                     Any = None
    yInletVoluteSupportLower:              Any = None
    yInletVoluteSupportUpper:              Any = None
    yInletVoluteSupportWall:               Any = None
    yReturnVolute:                         Any = None
    yReturnVoluteShell:                    Any = None
    yReturnVoluteSupportLower:             Any = None
    yReturnVoluteSupportUpper:             Any = None
    yReturnVoluteSupportWall:              Any = None
    zInletVolute:                          Any = None
    zInletVoluteShell:                     Any = None
    zInletVoluteSupportLower:              Any = None
    zInletVoluteSupportUpper:              Any = None
    zInletVoluteSupportWall:               Any = None
    zReturnVolute:                         Any = None
    zReturnVoluteShell:                    Any = None
    zReturnVoluteSupportLower:             Any = None
    zReturnVoluteSupportUpper:             Any = None
    zReturnVoluteSupportWall:              Any = None

    # -- Produced by the build -- #

# The fields a build hands back to a Nozzle. Kept beside the class so that adding a field
# and forgetting to surface it is a one-line fix rather than a silent drop.
regenVoluteOutputs = (
    'inletVolute', 'returnVolute', 'xInletVolute', 'xInletVoluteShell',
    'xInletVoluteSupportLower', 'xInletVoluteSupportUpper', 'xInletVoluteSupportWall',
    'xReturnVolute', 'xReturnVoluteShell', 'xReturnVoluteSupportLower',
    'xReturnVoluteSupportUpper', 'xReturnVoluteSupportWall', 'yInletVolute', 'yInletVoluteShell',
    'yInletVoluteSupportLower', 'yInletVoluteSupportUpper', 'yInletVoluteSupportWall',
    'yReturnVolute', 'yReturnVoluteShell', 'yReturnVoluteSupportLower',
    'yReturnVoluteSupportUpper', 'yReturnVoluteSupportWall', 'zInletVolute', 'zInletVoluteShell',
    'zInletVoluteSupportLower', 'zInletVoluteSupportUpper', 'zInletVoluteSupportWall',
    'zReturnVolute', 'zReturnVoluteShell', 'zReturnVoluteSupportLower',
    'zReturnVoluteSupportUpper', 'zReturnVoluteSupportWall')

def solveRegenVolutes(state):

    '''

    Generate inlet and return volute geometries for regenerative cooling channels.

    This method creates the manifold geometry that interfaces the cooling channels
    with external feedlines. It requires generateRegenChannels() to be called first.

    Raises:
        InvalidInputError: If prerequisites are not met or inputs are invalid
        RegenGeometryError: If required channel geometry data is missing
        NumericalInstabilityError: If channel geometry contains non-finite values
        VoluteGenerationError: If volute generation fails

    '''

    from scipy.interpolate import CubicSpline

    # Validate inputs before volute generation
    validateRegenVoluteInputs(state)

    def getGRCopStrength(stressType: str = 'yield', temperature: float = 298, alloy: float = 42):

        '''

        Returns 0.20% yield strength or ultimate tensile strength [Pa] 
        of specified GRCopper alloy (42 or 84) at specified temperature [K].

        Interpolates manufacturer data.

        '''

        if stressType.lower() == 'ultimate':

            if alloy == 84:

                TdataF     = np.array([-423.4,-315.4,70,392,752,1112,1472])
                TdataK     = units.toSI(TdataF, 'temperature', 'degF')
                UTSdataKSI = np.array([103,90,57,38,29,17,8])
                UTSdataPA  = UTSdataKSI*6.895e6

                UTS = CubicSpline(TdataK,UTSdataPA)(temperature)

                return UTS

            elif alloy == 42:

                TdataF     = np.array([-320,70,392,752,1112,1472])
                TdataK     = units.toSI(TdataF, 'temperature', 'degF')
                UTSdataKSI = np.array([76.6,52.3,37,28.3,16.3,8.9])
                UTSdataPA  = UTSdataKSI*6.895e6

                UTS = CubicSpline(TdataK,UTSdataPA)(temperature)

                return UTS

            else:
                raise InvalidInputError(
                    message='Unrecognized GRCopper alloy for ultimate tensile strength',
                    parameterName='alloy',
                    value=alloy,
                    validRange='42 or 84'
                )

        elif stressType.lower() == 'yield':

            if alloy == 84:

                TdataF     = np.array([-423.4,-315.4,70,392,752,1112,1472])
                TdataK     = units.toSI(TdataF, 'temperature', 'degF')
                YSdataKSI  = np.array([37,37,30,28,24,16,7])
                YSdataPA   = YSdataKSI*6.895e6

                YS = CubicSpline(TdataK,YSdataPA)(temperature)

                return YS

            elif alloy == 42:

                TdataF     = np.array([-320,70,392,752,1112,1472])
                TdataK     = units.toSI(TdataF, 'temperature', 'degF')
                YSdataKSI  = np.array([33.5,25.8,24,20.4,15.1,7.4])
                YSdataPA   = YSdataKSI*6.895e6

                YS = CubicSpline(TdataK,YSdataPA)(temperature)

                return YS

            else:
                raise InvalidInputError(
                    message='Unrecognized GRCopper alloy for yield strength',
                    parameterName='alloy',
                    value=alloy,
                    validRange='42 or 84'
                )

        else:
            raise InvalidInputError(
                message='Unrecognized stress type',
                parameterName='stressType',
                value=stressType,
                validRange='yield or ultimate'
            )

    # ------------- #
    # -- METHODS -- #
    # ------------- #

    def generateRegenInletVolute():

        print(f'Generating Inlet Volute:')

        # wall thickness sizing
        hoopStressTarget = getGRCopStrength('yield', state.coolantInitialTemperature, 42)
        FOS = state.voluteFOS
        hoopStressTarget *= 1/FOS

        ## Create volute object
        # instantiate
        inletVolute = Volute()
        # cross section properties
        inletVolute.crossSectionType               = state.inletVoluteCrossSection
        inletVolute.circlePrintability             = state.inletVolutePrintability
        inletVolute.anchorBy                       = state.inletVoluteAlignment
        inletVolute.printabilityAngle              = state.inletVoluteTilt # [deg]
        inletVolute.crossSectionResolution         = state.numCSPointsVolute
        inletVolute.numCrossSections               = state.numCSVolute
        # scroll properties
        inletVolute.scrollDirection                = 'ccw'
        if state.inletVoluteCrossSection == 'squarc':

            xFlareEndCAD = state.xChannelCenterline2D[-1] - np.sin(np.deg2rad(state.inletVoluteTilt))*0.003
            rFlareEndCAD = state.rChannelCenterline2D[-1] - np.cos(np.deg2rad(state.inletVoluteTilt))*0.003
            xSquarcCorner = xFlareEndCAD + np.cos(np.deg2rad(state.inletVoluteTilt))*state.channelRadius[-1]*1.05
            rSquarcCorner = rFlareEndCAD - np.sin(np.deg2rad(state.inletVoluteTilt))*state.channelRadius[-1]*1.05

            inletVolute.voluteScrollRadius         = rSquarcCorner
            inletVolute.axialOffset                = xSquarcCorner

        else:
            inletVolute.voluteScrollRadius         = state.rChannelCenterline2D[-3]
            inletVolute.axialOffset                = state.xChannelCenterline2D[-3]
        # area distribution properties
        if state.inletVoluteCrossSection == 'squarc':
            inletVolute.interfaceCharLen           = state.channelRadius[-1]*2*1.1
        else:
            inletVolute.interfaceHydraulicDiameter = state.channelRadius[-1]*2*1.1
        inletVolute.expandedHydraulicDiameter      = units.toSI(state.inletGraylocDiameter, 'length', 'in')  # grayloc interface hydraulic diameter
        # wall properties
        inletVolute.wallHoopStress                 = hoopStressTarget
        inletVolute.pressureDifferential           = state.coolantInitialPressure
        inletVolute.alignWallBy                    = 'inner'
        # options
        inletVolute.export                         = 'off'

        # make geometry with error handling
        try:
            inletVolute.generateVolute()
        except Exception as e:
            raise VoluteGenerationError(
                message=f"Failed to generate inlet volute geometry: {str(e)}",
                context=createErrorContext(
                    scrollRadius=inletVolute.voluteScrollRadius,
                    axialOffset=inletVolute.axialOffset,
                    channelRadius=state.channelRadius[-1],
                    coolantPressure=state.coolantInitialPressure,
                    coolantTemperature=state.coolantInitialTemperature
                ),
                voluteType='inlet',
                failureMode=type(e).__name__
            ) from e

        # relative roll
        for i in range(state.numCSVolute):
            inletVolute.xVolute[i,:], inletVolute.yVolute[i,:], inletVolute.zVolute[i,:] = DCM(eulerAngles = [0,0,np.deg2rad(state.voluteRelativeRoll)],
                                                                                            valueMatrix = [inletVolute.xVolute[i,:],
                                                                                                           inletVolute.yVolute[i,:],
                                                                                                           inletVolute.zVolute[i,:]])
            inletVolute.xShell[i,:],  inletVolute.yShell[i,:],  inletVolute.zShell[i,:]  = DCM(eulerAngles = [0,0,np.deg2rad(state.voluteRelativeRoll)],
                                                                                            valueMatrix = [inletVolute.xShell[i,:],
                                                                                                           inletVolute.yShell[i,:],
                                                                                                           inletVolute.zShell[i,:]])
            if inletVolute.circlePrintability == 'thick':
                inletVolute.xInternalSupportWall[i,:], inletVolute.yInternalSupportWall[i,:], inletVolute.zInternalSupportWall[i,:] = DCM(eulerAngles = [0,0,np.deg2rad(state.voluteRelativeRoll)],
                                                                                                valueMatrix = [inletVolute.xInternalSupportWall[i,:],
                                                                                                               inletVolute.yInternalSupportWall[i,:],
                                                                                                               inletVolute.zInternalSupportWall[i,:]])
                inletVolute.xInternalSupportFilletUpper[i,:], inletVolute.yInternalSupportFilletUpper[i,:], inletVolute.zInternalSupportFilletUpper[i,:] = DCM(eulerAngles = [0,0,np.deg2rad(state.voluteRelativeRoll)],
                                                                                                valueMatrix = [inletVolute.xInternalSupportFilletUpper[i,:],
                                                                                                               inletVolute.yInternalSupportFilletUpper[i,:],
                                                                                                               inletVolute.zInternalSupportFilletUpper[i,:]])
                inletVolute.xInternalSupportFilletLower[i,:], inletVolute.yInternalSupportFilletLower[i,:], inletVolute.zInternalSupportFilletLower[i,:] = DCM(eulerAngles = [0,0,np.deg2rad(state.voluteRelativeRoll)],
                                                                                                valueMatrix = [inletVolute.xInternalSupportFilletLower[i,:],
                                                                                                               inletVolute.yInternalSupportFilletLower[i,:],
                                                                                                               inletVolute.zInternalSupportFilletLower[i,:]])
            if inletVolute.circlePrintability == 'thin':
                inletVolute.xInternalSupportWall[i,:], inletVolute.yInternalSupportWall[i,:], inletVolute.zInternalSupportWall[i,:] = DCM(eulerAngles = [0,0,np.deg2rad(state.voluteRelativeRoll)],
                                                                                                valueMatrix = [inletVolute.xInternalSupportWall[i,:],
                                                                                                               inletVolute.yInternalSupportWall[i,:],
                                                                                                               inletVolute.zInternalSupportWall[i,:]])
                inletVolute.xInternalSupportFilletUpper[i,:], inletVolute.yInternalSupportFilletUpper[i,:], inletVolute.zInternalSupportFilletUpper[i,:] = DCM(eulerAngles = [0,0,np.deg2rad(state.voluteRelativeRoll)],
                                                                                                valueMatrix = [inletVolute.xInternalSupportFilletUpper[i,:],
                                                                                                               inletVolute.yInternalSupportFilletUpper[i,:],
                                                                                                               inletVolute.zInternalSupportFilletUpper[i,:]])

        ## gather results
        # save object
        state.inletVolute              = inletVolute
        # copy geometry arrays
        state.xInletVolute             = inletVolute.zVolute
        state.yInletVolute             = inletVolute.xVolute
        state.zInletVolute             = inletVolute.yVolute
        state.xInletVoluteShell        = inletVolute.zShell
        state.yInletVoluteShell        = inletVolute.xShell
        state.zInletVoluteShell        = inletVolute.yShell
        state.xInletVoluteSupportWall  = inletVolute.zInternalSupportWall
        state.yInletVoluteSupportWall  = inletVolute.xInternalSupportWall
        state.zInletVoluteSupportWall  = inletVolute.yInternalSupportWall
        state.xInletVoluteSupportUpper = inletVolute.zInternalSupportFilletUpper
        state.yInletVoluteSupportUpper = inletVolute.xInternalSupportFilletUpper
        state.zInletVoluteSupportUpper = inletVolute.yInternalSupportFilletUpper
        state.xInletVoluteSupportLower = inletVolute.zInternalSupportFilletLower
        state.yInletVoluteSupportLower = inletVolute.xInternalSupportFilletLower
        state.zInletVoluteSupportLower = inletVolute.yInternalSupportFilletLower

    def generateRegenReturnVolute():

        print(f'Generating Return Volute:')

        # wall thickness sizing
        hoopStressTarget = getGRCopStrength('yield', state.coolantExitTemperature, 42)
        FOS = state.voluteFOS
        hoopStressTarget *= 1/FOS

        ## Create volute object
        # instantiate
        returnVolute = Volute()
        # cross section properties
        returnVolute.crossSectionType           = state.returnVoluteCrossSection
        returnVolute.circlePrintability         = state.returnVolutePrintability
        returnVolute.anchorBy                   = state.returnVoluteAlignment
        returnVolute.printabilityAngle          = state.returnVoluteTilt
        returnVolute.crossSectionResolution     = state.numCSPointsVolute
        returnVolute.numCrossSections           = state.numCSVolute
        # scroll properties
        returnVolute.scrollDirection            = 'cw'
        # The return flare leaves the injector face as the mirror image of the inlet flare, so
        # the scroll is placed the inlet's way from the other end of the centerline.
        returnVolute.voluteScrollRadius         = state.rChannelCenterline2D[2]
        returnVolute.axialOffset                = state.xChannelCenterline2D[2]
        # area distribution properties
        returnVolute.interfaceHydraulicDiameter = state.channelRadius[0]*2*1.2
        returnVolute.expandedHydraulicDiameter  = units.toSI(state.returnGraylocDiameter, 'length', 'in')  # grayloc interface hydraulic diameter
        # wall properties
        returnVolute.wallHoopStress             = hoopStressTarget
        returnVolute.pressureDifferential       = state.coolantExitPressure
        returnVolute.alignWallBy                = 'inner'
        # options
        returnVolute.export                     = 'off'

        # make geometry with error handling
        try:
            returnVolute.generateVolute()
        except Exception as e:
            raise VoluteGenerationError(
                message=f"Failed to generate return volute geometry: {str(e)}",
                context=createErrorContext(
                    scrollRadius=returnVolute.voluteScrollRadius,
                    axialOffset=returnVolute.axialOffset,
                    channelRadius=state.channelRadius[0],
                    coolantPressure=state.coolantExitPressure,
                    coolantTemperature=state.coolantExitTemperature
                ),
                voluteType='return',
                failureMode=type(e).__name__
            ) from e

        ## gather results
        # save object
        state.returnVolute              = returnVolute
        # copy geometry arrays
        state.xReturnVolute             = returnVolute.zVolute
        state.yReturnVolute             = returnVolute.xVolute
        state.zReturnVolute             = returnVolute.yVolute
        state.xReturnVoluteShell        = returnVolute.zShell
        state.yReturnVoluteShell        = returnVolute.xShell
        state.zReturnVoluteShell        = returnVolute.yShell
        state.xReturnVoluteSupportWall  = returnVolute.zInternalSupportWall
        state.yReturnVoluteSupportWall  = returnVolute.xInternalSupportWall
        state.zReturnVoluteSupportWall  = returnVolute.yInternalSupportWall
        state.xReturnVoluteSupportUpper = returnVolute.zInternalSupportFilletUpper
        state.yReturnVoluteSupportUpper = returnVolute.xInternalSupportFilletUpper
        state.zReturnVoluteSupportUpper = returnVolute.yInternalSupportFilletUpper
        state.xReturnVoluteSupportLower = returnVolute.zInternalSupportFilletLower
        state.yReturnVoluteSupportLower = returnVolute.xInternalSupportFilletLower
        state.zReturnVoluteSupportLower = returnVolute.yInternalSupportFilletLower
        state.returnVolute              = returnVolute

    # ------------------ #
    # -- DO THE THING -- #
    # ------------------ #

    if state.makeInletVolute == 'on':

        generateRegenInletVolute()

    if state.makeReturnVolute == 'on':

        generateRegenReturnVolute()

    return state
