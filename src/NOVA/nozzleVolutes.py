
# -- NOVA: Regenerative Cooling Volutes -- #

'''

The manifolds that feed the cooling channels and collect them again.

A regeneratively cooled jacket has to get coolant in and out. Sixty channels cannot each have
their own feedline, so they are gathered into a scroll that wraps the nozzle: the inlet volute
distributes flow from a single fitting into every channel, and the return volute collects it back.

Each scroll carries a cross section that grows in proportion to the flow passing it, which is what
holds its velocity constant around the wrap and so keeps the static pressure the channels see
uniform. The flow passing a station is linear in the ports it has already served, so the area is
linear in wrap angle, and the throat that closes the law is the tongue area times the ports one
run serves: Huzel and Huang, Design of Liquid Propellant Rocket Engines, eq. 6-69. A `cutwater`
scroll serves every port on one run; a `ring` is fed from both directions and serves half on each.
The tongue itself is fixed by the channel port it opens onto, so the throat is what the law sets,
and the Grayloc fitting is what the throat then transitions into rather than the throat itself.

The scroll geometry lives in Volute.py, which draws one from a scroll radius, a cross section
family and an area distribution, and the section algebra in voluteSections.py. What happens here
is everything around it: placing the scroll on the channel port it gathers, sizing its wall
against the pressure and temperature the coolant is at, checking it clears the gas-side wall, and
growing the print supports an unsupported scroll needs.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**The wall thickness is a hoop stress calculation against manufacturer data.** It is as good as
that data. The thickness follows from the pressure differential, the local radius and an
allowable stress read from the alloy's yield curve at the coolant temperature. The curves are
manufacturer figures interpolated on a cubic spline, and the spline extrapolates outside the
data it was given without saying so. That is worth knowing: a lookup below the lowest datum
returns a number that no measurement supports.

**The area law is a published design rule, not a validated model.** The constant velocity law is
standard practice for a scroll that sheds or gathers evenly around its wrap, and following it is a
statement about practice rather than a prediction checked against data. What the law is for, an
even split between the channels, is not measured anywhere: no flow distribution test, no CFD of
the built surface with its branches resolved. The scroll velocity, its velocity head and that head
against the jacket pressure drop are reported at build time, because the ratio of the two is what
the distribution literature says governs the split, and on a jacket whose channels carry little
pressure drop that ratio can sit the wrong side of one.

**The rest is geometry.** The flare into the interface and the print supports close and clear what
they are meant to clear, which is the whole claim. Placement and wall clearance are checked: the
tongue section is centred on the channel port, and a scroll reaching inside the gas-side wall is
refused rather than drawn.

**The wall carries no toroidal correction.** The hoop relation is the straight cylinder one
evaluated on the section hydraulic diameter, and a scroll is a torus, whose membrane stress peaks
at the inner crotch. On the shipped engine that is 6 to 7 per cent of thickness, measured in
docs/reports/voluteAudit_2026-09-29.md.

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
from .channelSections import equivalentDiameter
from .fluidProperties import fluidProps
from .voluteSections import (constantVelocityThroatArea, portsPerScroll,
                             scrollPlacement, sectionArea, sectionHydraulicDiameter)
from .validation import applyRules, arrayRule, presentRule

# How much wider the tongue section is drawn than the port it meets, so the port opens into the
# scroll rather than meeting its wall tangentially.
tongueOverPort = 1.1

# Manufacturer 0.2 per cent yield and ultimate tensile data for the GRCop alloys, in degrees
# Fahrenheit and ksi as published. The tables are the whole basis of the wall thickness, so the
# lookup below refuses to read outside them rather than letting a spline invent a number.
grcopStrengthData = {
    (42, 'yield'):    ([-320, 70, 392, 752, 1112, 1472], [33.5, 25.8, 24, 20.4, 15.1, 7.4]),
    (42, 'ultimate'): ([-320, 70, 392, 752, 1112, 1472], [76.6, 52.3, 37, 28.3, 16.3, 8.9]),
    (84, 'yield'):    ([-423.4, -315.4, 70, 392, 752, 1112, 1472], [37, 37, 30, 28, 24, 16, 7]),
    (84, 'ultimate'): ([-423.4, -315.4, 70, 392, 752, 1112, 1472],
                       [103, 90, 57, 38, 29, 17, 8]),
}

# A pressurized part is proof tested and leak checked at room temperature, where a copper alloy is
# weaker than it is at coolant temperature, so that is the case the wall has to carry.
ambientProofTemperature = 293.15

def grcopStrength(stressType: str = 'yield', temperature: float = 298.0, alloy: int = 42) -> float:

    '''

    0.2 per cent yield or ultimate tensile strength of a GRCop alloy [Pa].

    Manufacturer data on a cubic spline. Outside the data the nearest measured temperature is used
    rather than the spline's continuation, because a spline extrapolates without saying so and the
    values it returns below the lowest datum are not supported by any measurement: on GRCop-42 the
    lowest yield datum is 77.6 K, and a hydrogen inlet at 30 K sits 48 K below it.

    Parameters:
    -----------
    stressType : str
        `yield` or `ultimate`.
    temperature : float
        Metal temperature [K].
    alloy : int
        42 or 84.

    Returns:
    --------
    float
        Strength [Pa].

    Raises:
    -------
    InvalidInputError
        On an unrecognized alloy or stress type.

    '''

    key = (int(alloy), str(stressType).lower())

    if key[1] not in ('yield', 'ultimate'):
        raise InvalidInputError(
            message = 'Unrecognized stress type',
            parameterName = 'stressType',
            value = stressType,
            validRange = 'yield or ultimate')

    if key not in grcopStrengthData:
        raise InvalidInputError(
            message = f'Unrecognized GRCopper alloy for {key[1]} strength',
            parameterName = 'alloy',
            value = alloy,
            validRange = '42 or 84')

    temperatureF, strengthKSI = grcopStrengthData[key]
    temperatureK = units.toSI(np.asarray(temperatureF, dtype = float), 'temperature', 'degF')
    strengthPa = np.asarray(strengthKSI, dtype = float)*6.895e6

    held = float(np.clip(temperature, temperatureK.min(), temperatureK.max()))

    return float(CubicSpline(temperatureK, strengthPa)(held))

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
    channelCornerRadius:                   Any = None
    channelRadius:                         Any = None
    channelType:                           Any = None
    channelWidth:                          Any = None
    coolant:                               Any = None
    coolantExitPressure:                   Any = None
    coolantExitTemperature:                Any = None
    coolantInitialPressure:                Any = None
    coolantInitialTemperature:             Any = None
    coolantMassFlow:                       Any = None
    dataFolder:                            Any = None
    export:                                Any = None
    inletGraylocDiameter:                  Any = None
    inletVoluteAlignment:                  Any = None
    inletVoluteCrossSection:               Any = None
    inletVolutePrintability:               Any = None
    inletVoluteTilt:                       Any = None
    makeInletVolute:                       Any = None
    makeReturnVolute:                      Any = None
    maxVoluteBore:                         Any = None
    minVoluteWallThickness:                Any = None
    nChannel:                              Any = None
    numCSPointsVolute:                     Any = None
    numCSVolute:                           Any = None
    rChannelCenterline2D:                  Any = None
    rNozzleWall:                           Any = None
    returnGraylocDiameter:                 Any = None
    returnVoluteAlignment:                 Any = None
    returnVoluteCrossSection:              Any = None
    returnVolutePrintability:              Any = None
    returnVoluteTilt:                      Any = None
    voluteFOS:                             Any = None
    voluteRelativeRoll:                    Any = None
    voluteScrollType:                      Any = None
    xChannelCenterline2D:                  Any = None
    xNozzleWall:                           Any = None

    # -- Read and written as the volutes are grown -- #
    inletVoluteThroatArea:                 Any = None
    inletVoluteWallClearance:              Any = None
    inletVoluteVelocity:                   Any = None
    inletVoluteVelocityHead:               Any = None
    returnVoluteThroatArea:                Any = None
    returnVoluteWallClearance:             Any = None
    returnVoluteVelocity:                  Any = None
    returnVoluteVelocityHead:              Any = None
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
    'inletVoluteThroatArea', 'inletVoluteVelocity', 'inletVoluteVelocityHead',
    'inletVoluteWallClearance', 'returnVoluteThroatArea', 'returnVoluteVelocity',
    'returnVoluteVelocityHead', 'returnVoluteWallClearance',
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

    def portDiameter(station: int) -> float:

        '''The diameter of the round port matching the channel at one end [m].'''

        corner = state.channelCornerRadius
        corner = 0.0 if corner is None or not np.isfinite(corner) else corner

        return float(equivalentDiameter(state.channelType, state.channelRadius[station],
                                        width = state.channelWidth[station], cornerRadius = corner))

    # ------------- #
    # -- METHODS -- #
    # ------------- #

    def wallClearance(side: str, volute, alignment: str) -> float:

        '''

        Smallest radial gap between the built scroll and the gas-side wall [m].

        The scroll is placed on the channel port, and the alignment then decides which way its
        growing sections reach. An alignment that reaches inward puts the largest sections into
        the nozzle, which is a clash rather than a packaging preference, so it is refused here
        rather than drawn.

        Parameters:
        -----------
        side : str
            `inlet` or `return`, for the message a refusal carries.
        volute : Volute
            The built scroll, whose own axis is the nozzle axis.
        alignment : str
            The anchor the sections were aligned by.

        Returns:
        --------
        float
            Minimum clearance [m], negative where the scroll is inside the wall.

        Raises:
        -------
        VoluteGenerationError
            When any part of the scroll or its shell sits inside the wall.

        '''

        if state.xNozzleWall is None or state.rNozzleWall is None:
            return None

        order = np.argsort(np.asarray(state.xNozzleWall, dtype = float))
        wallX = np.asarray(state.xNozzleWall, dtype = float)[order]
        wallR = np.asarray(state.rNozzleWall, dtype = float)[order]

        clearance = np.inf
        for axial, first, second in ((volute.zVolute, volute.xVolute, volute.yVolute),
                                     (volute.zShell, volute.xShell, volute.yShell)):
            if np.size(axial) == 0:
                continue
            x = np.asarray(axial, dtype = float).ravel()
            r = np.sqrt(np.asarray(first, dtype = float).ravel()**2
                        + np.asarray(second, dtype = float).ravel()**2)
            wall = np.interp(x, wallX, wallR, left = np.nan, right = np.nan)
            gap = np.nanmin(r - wall)
            clearance = min(clearance, float(gap)) if np.isfinite(gap) else clearance

        if np.isfinite(clearance) and clearance < 0.0:
            raise VoluteGenerationError(
                message = (f'The {side} scroll reaches {abs(clearance)*1e3:.2f} mm inside the '
                           f'gas-side wall. The scroll is placed on the channel port it meets, so '
                           f'the alignment decides which way its sections grow from there: '
                           f'{alignment!r} grows them toward the nozzle. An alignment that grows '
                           f'them outward clears it.'),
                context = createErrorContext(
                    clearance = clearance,
                    alignment = alignment,
                    scrollRadius = volute.voluteScrollRadius,
                    throatArea = float(np.max(volute.crossSectionalArea))),
                voluteType = side,
                failureMode = 'scrollInsideWall')

        return clearance if np.isfinite(clearance) else None

    def scrollThroat(side: str, station: int, tongueDiameter: float, fittingDiameter: float,
                     temperature: float, pressure: float) -> tuple:

        '''

        Throat area the constant velocity law asks for, and what the scroll runs at.

        The tongue is fixed by the port it meets, so the throat is what the law sets: the flow a
        run carries is linear in the ports it has passed, which holds the velocity constant only
        when the throat is the tongue times the ports that run serves. A ring serves half of them
        each way, a cutwater all of them.

        Parameters:
        -----------
        side : str
            `inlet` or `return`, for the message a refusal carries.
        station : int
            Channel station the volute attaches to.
        tongueDiameter : float
            Hydraulic diameter of the tongue section [m].
        fittingDiameter : float
            Bore of the fitting the scroll transitions into [m].
        temperature, pressure : float
            Coolant state in the scroll, for the density the velocity is read at.

        Returns:
        --------
        tuple
            Throat area [m^2], velocity [m/s] and velocity head [Pa]. Velocity and head are None
            when no coolant is named.

        Raises:
        -------
        VoluteGenerationError
            When the law asks for a throat wider than `maxVoluteBore`.

        '''

        family = str(state.inletVoluteCrossSection if side == 'inlet'
                     else state.returnVoluteCrossSection).lower()
        scrollType = str(state.voluteScrollType).lower()

        tongueArea = sectionArea(family, hydraulicDiameter = tongueDiameter)
        throatArea = constantVelocityThroatArea(tongueArea, state.nChannel, scrollType)
        bore = 2.0*np.sqrt(throatArea/np.pi)

        if state.maxVoluteBore is not None and np.isfinite(state.maxVoluteBore) \
                and bore > state.maxVoluteBore:
            raise VoluteGenerationError(
                message = (f'The constant velocity law asks for a {side} scroll throat of '
                           f'{bore*1e3:.1f} mm bore, past the {state.maxVoluteBore*1e3:.1f} mm '
                           f'limit. The throat is the tongue times the ports one run serves, and '
                           f'the tongue is set by the channel port it meets: '
                           f'{portDiameter(station)*1e3:.2f} mm at station {station}. A port that '
                           f'size cannot be fed at constant velocity by a scroll that fits. '
                           f'Reduce the channel size at that end, or raise maxVoluteBore and '
                           f'accept the scroll it asks for.'),
                context = createErrorContext(
                    throatBore = bore,
                    maxVoluteBore = state.maxVoluteBore,
                    channelPortDiameter = portDiameter(station),
                    portsPerRun = portsPerScroll(state.nChannel, scrollType),
                    scrollType = scrollType),
                voluteType = side,
                failureMode = 'throatBeyondLimit')

        velocity, head = None, None
        if state.coolant is not None and state.coolantMassFlow is not None:
            density = float(fluidProps(state.coolant, 'TP', 'D', temperature, pressure))
            runFlow = state.coolantMassFlow*portsPerScroll(state.nChannel, scrollType) \
                / state.nChannel
            velocity = runFlow/(density*throatArea)
            head = 0.5*density*velocity**2
            drop = float(state.coolantInitialPressure - state.coolantExitPressure)
            print(f'  {side} scroll: throat {throatArea*1e6:.0f} mm2 ({bore*1e3:.1f} mm bore), '
                  f'{velocity:.1f} m/s, velocity head {head/1e3:.0f} kPa, '
                  f'{head/drop:.2f} times the jacket pressure drop')
            print(f'  {side} fitting: {fittingDiameter*1e3:.1f} mm bore, so the scroll transitions '
                  f'through an area ratio of {throatArea/(np.pi*(fittingDiameter/2)**2):.2f}')

        return throatArea, velocity, head

    def generateRegenInletVolute():

        print(f'Generating Inlet Volute:')

        # wall thickness sizing. The wall is proof tested at room temperature, where the alloy
        # is weaker than it is at hydrogen temperature, so it is sized on the warmer of the two.
        sizingTemperature = max(float(state.coolantInitialTemperature), ambientProofTemperature)
        hoopStressTarget = grcopStrength('yield', sizingTemperature, 42)/state.voluteFOS

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
        # area distribution properties
        inletVolute.scrollType                     = state.voluteScrollType
        inletVolute.interfaceHydraulicDiameter     = portDiameter(-1)*tongueOverPort
        state.inletVoluteThroatArea, state.inletVoluteVelocity, state.inletVoluteVelocityHead = \
            scrollThroat('inlet', -1, inletVolute.interfaceHydraulicDiameter,
                         units.toSI(state.inletGraylocDiameter, 'length', 'in'),
                         state.coolantInitialTemperature, state.coolantInitialPressure)
        inletVolute.expandedArea                   = state.inletVoluteThroatArea
        # The scroll is placed on the channel port it gathers, at the end of the flare rather than
        # at a station part way along it.
        inletVolute.voluteScrollRadius, inletVolute.axialOffset = scrollPlacement(
            state.inletVoluteCrossSection, inletVolute.interfaceHydraulicDiameter,
            state.inletVoluteAlignment, state.xChannelCenterline2D[-1],
            state.rChannelCenterline2D[-1], portDiameter(-1))
        # wall properties
        inletVolute.wallHoopStress                 = hoopStressTarget
        inletVolute.minWallThickness               = state.minVoluteWallThickness or 0.0
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

        state.inletVoluteWallClearance = wallClearance('inlet', inletVolute,
                                                       state.inletVoluteAlignment)

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

        # wall thickness sizing, on the warmer of the coolant and the ambient proof case
        sizingTemperature = max(float(state.coolantExitTemperature), ambientProofTemperature)
        hoopStressTarget = grcopStrength('yield', sizingTemperature, 42)/state.voluteFOS

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
        # area distribution properties
        returnVolute.scrollType                 = state.voluteScrollType
        returnVolute.interfaceHydraulicDiameter = portDiameter(0)*tongueOverPort
        state.returnVoluteThroatArea, state.returnVoluteVelocity, state.returnVoluteVelocityHead = \
            scrollThroat('return', 0, returnVolute.interfaceHydraulicDiameter,
                         units.toSI(state.returnGraylocDiameter, 'length', 'in'),
                         state.coolantExitTemperature, state.coolantExitPressure)
        returnVolute.expandedArea               = state.returnVoluteThroatArea
        # The return flare leaves the injector face as the mirror image of the inlet flare, so its
        # scroll is placed the same way on the port at the other end of the centerline.
        returnVolute.voluteScrollRadius, returnVolute.axialOffset = scrollPlacement(
            state.returnVoluteCrossSection, returnVolute.interfaceHydraulicDiameter,
            state.returnVoluteAlignment, state.xChannelCenterline2D[0],
            state.rChannelCenterline2D[0], portDiameter(0))
        # wall properties
        returnVolute.wallHoopStress             = hoopStressTarget
        returnVolute.minWallThickness           = state.minVoluteWallThickness or 0.0
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

        state.returnVoluteWallClearance = wallClearance('return', returnVolute,
                                                        state.returnVoluteAlignment)

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
