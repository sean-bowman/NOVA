# -- NOVA: Cooling Channel Sizing -- #

'''

Sizing a cooling channel so the wall it protects runs at the temperature it is allowed to.

The channel radius at a station is not a free choice. Too small and the coolant chokes, the
pressure drop runs away and the wall overheats; too large and the channel will not fit between
its neighbours, or will not print. What sets it is the hot wall temperature, and that is not
known until the channel is drawn, the coolant marched through it and the heat balance solved.
So the radius is solved for, station by station, marching from the coolant inlet.

At each station the loop proposes a radius, rebuilds the cross section, runs the thermal model,
reads the hot wall temperature back, and steps again. It is a one-dimensional root find on a
monotone function: a wider channel runs cooler. It is written as an adaptive secant with
backtracking, overshoot damping and a step fraction that ramps with the distance from target.

Three things bound the answer. The channel may not exceed the largest that fits between its
neighbours at that station, it may not fall below the minimum the process can build, and where
it is bounded the wall temperature is whatever it comes out as.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Not validated, and there is nothing available to validate it against.** The result is a
converged fixed point of a geometry model and a thermal model, and no published case states a
channel radius distribution alongside the conditions that produced it. What can be said is
internal: the loop converges to the requested wall temperature within its stated tolerance where
the bounds allow, and reports the bound it hit where they do not.

The thermal model it converges against carries its own disclosures, which this inherits in full.
In particular the coolant-side correlation is unvalidated, so a channel sized against it is sized
against an unvalidated number, however tightly the loop converges.

The convergence is a hand-rolled search rather than a bracketed method. It has a fixed iteration
ceiling and a tolerance of one part in ten thousand of the target wall temperature, and where it
exhausts its iterations it says so rather than returning the last iterate silently.

All units are mass base SI:
    - Length      [m]
    - Temperature [K]
    - Pressure    [Pa]
    - Mass flow   [kg/s]

Author: Sean Bowman

'''

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.interpolate import interp1d
from tqdm import tqdm

from .utils import (DCM, parallelOffset, ConvergenceFailureError, createErrorContext,
                    InvalidInputError)
from .materials import wallMaterialCurves
from .channelGeometry import generateCrossSections as buildCrossSections
from .regenThermal import (regenHeatTransferModel as solveRegenHeatTransfer,
                           regenHeatTransferModelPlots as drawRegenHeatTransfer)

# The quantities the thermal model returns per station and the sizing loop carries through to the
# comparison figure. Held once because the per-station loop and the full-contour pass both fill
# the same dictionary, and a key present in one and not the other reads as a silent zero.
def drivingTemperatureArray(state):

    """

    The gas temperature the heat flux is driven by, at every trimmed station.

    Convection into a wall is driven by the adiabatic wall temperature, which for a turbulent
    boundary layer is the static temperature raised by the recovery factor times the dynamic rise.
    Driving it with the static temperature instead understates the flux by the whole of that rise,
    which is negligible in the chamber and approaches a factor of two by the end of a supersonic
    jacket.

    Parameters:
    -----------
    state : ChannelSizingState
        Carries both arrays and the choice between them.

    Returns:
    --------
    numpy.ndarray
        Driving temperature at each trimmed station [K].

    Raises:
    -------
    InvalidInputError
        If the model is not one of the two, or if the recovery temperature was asked for and the
        run did not produce one.

    """

    # Unset means the physical choice. The dataclass starts every field at None, so the
    # default is resolved here rather than declared there.
    model = state.drivingTemperatureModel or 'recovery'

    if model == 'static':
        return state.regenSectionNearWallTemperatureTrimmed

    if model != 'recovery':
        raise InvalidInputError(
            message = 'Unknown driving temperature model.',
            parameterName = 'drivingTemperatureModel',
            value = model,
            validRange = "'recovery' or 'static'")

    if state.regenSectionNearWallRecoveryTemperatureTrimmed is None:
        raise InvalidInputError(
            message = 'The recovery temperature was asked for and the run did not produce one. '
                      'It is built alongside the other near-wall properties, so a run that '
                      'reached the jacket should carry it.',
            parameterName = 'regenSectionNearWallRecoveryTemperatureTrimmed',
            value = None,
            validRange = 'one value per trimmed station')

    return state.regenSectionNearWallRecoveryTemperatureTrimmed

THERMALPLOTKEYS = ('temperature', 'pressure', 'wallTemperature', 'velocity', 'machNumber',
                   'heatTransfer', 'density', 'viscosity', 'specificHeat', 'nusseltNumber',
                   'exhaustConvectiveHeatTransferCoef', 'coolantConvectiveHeatTransferCoef',
                   'reynoldsNumber', 'radiativeHeatTransfer', 'drivingTemperature')

@dataclass
class ChannelSizingState:

    '''

    Everything the sizing loop reads, and everything it produces.

    The constructor takes the engine, the coolant and the regen section the channels run along.
    Every output starts as None and is filled in by the solve, so an output still None afterwards
    means that branch was never reached, which is worth keeping rather than hiding behind a zero.

    Parameters:
    -----------
    channelType : str
        'circle' or 'fluted'.
    nChannel : int
        Channels around the nozzle.
    numCrossSections : int
        Stations along the channel.
    minChannelRadius : float
        Smallest channel the process can build [m].
    maxWallTemperature : float
        Hot wall temperature the loop converges to [K].
    hotWallThickness, infillThickness : float
        Wall between coolant and exhaust, and material left between neighbours [m].
    material : str
        Wall alloy, resolved by materials.wallMaterialCurves.
    coolant : str
        Coolant species.
    coolantMassFlow : float
        Total coolant flow through the jacket [kg/s].
    coolantInitialTemperature, coolantInitialPressure : float
        Coolant state at the jacket inlet [K], [Pa].
    chamberPressure : float
        Chamber stagnation pressure [Pa].
    theoreticalCharacteristicVelocity : float
        Characteristic velocity from the thermochemistry [m/s].
    nozzleScalingFactor : float
        Throat radius in real units [m].
    throatInletCurvatureNonDimensional, throatOutletCurvatureNonDimensional : float
        Throat arc radii, as multiples of the throat radius [-].
    fluteAmplitudeCoef, fluteHelixAngle : float
        Flute definition, NaN for a circular channel.
    xRegenNozzle, rRegenNozzle : Any
        Regen section wall, full [m].
    xRegenNozzleTrimmed, rRegenNozzleTrimmed : Any
        Regen section wall between the volute interfaces [m].
    gammaRegenSectionTrimmed, molecularWeightRegenSectionTrimmed : Any
        Exhaust gas properties at each trimmed station.
    gasConstantRegenSectionTrimmed : Any
        Specific gas constant at each trimmed station [J/kg K].
    regenSectionNearWallTemperatureTrimmed : Any
        Near-wall static exhaust temperature at each trimmed station [K].
    regenSectionNearWallRecoveryTemperatureTrimmed : Any
        Near-wall recovery temperature at each trimmed station [K]. This is the adiabatic
        wall temperature, and it is what the heat flux is actually driven by.
    drivingTemperatureModel : str
        'recovery' or 'static'. Which of the two above drives the solve. 'static' exists to
        reproduce results recorded before the recovery temperature was carried through, and
        it understates the flux by the whole recovery rise.
    regenSectionNearWallMachNumberTrimmed : Any
        Near-wall Mach number at each trimmed station [-].
    regenSectionNearWallPressureTrimmed : Any
        Near-wall exhaust pressure at each trimmed station [Pa].
    dcrData : dict
        Working store the loop fills as it goes.
    debugMode : bool
        True dumps the local state of a failed station.

    '''

    # -- What the solve reads -- #
    channelType:                            str   = 'circle'
    nChannel:                               int   = 0
    numCrossSections:                       int   = 0
    minChannelRadius:                       float = 0.0
    maxWallTemperature:                     float = float('nan')
    hotWallThickness:                       float = 0.0
    infillThickness:                        float = 0.0
    material:                               str   = 'GRCop-42'
    coolant:                                str   = ''
    coolantMassFlow:                        float = float('nan')
    coolantInitialTemperature:              float = float('nan')
    coolantInitialPressure:                 float = float('nan')
    chamberPressure:                        float = float('nan')
    theoreticalCharacteristicVelocity:      float = float('nan')
    nozzleScalingFactor:                    float = float('nan')
    throatInletCurvatureNonDimensional:     float = float('nan')
    throatOutletCurvatureNonDimensional:    float = float('nan')
    fluteAmplitudeCoef:                     float = float('nan')
    fluteHelixAngle:                        float = float('nan')
    xRegenNozzle:                           Any   = None
    rRegenNozzle:                           Any   = None
    xRegenNozzleTrimmed:                    Any   = None
    rRegenNozzleTrimmed:                    Any   = None
    gammaRegenSectionTrimmed:               Any   = None
    molecularWeightRegenSectionTrimmed:     Any   = None
    gasConstantRegenSectionTrimmed:         Any   = None
    regenSectionNearWallTemperatureTrimmed: Any   = None
    regenSectionNearWallRecoveryTemperatureTrimmed: Any = None
    drivingTemperatureModel:                Any   = None
    regenSectionNearWallMachNumberTrimmed:  Any   = None
    regenSectionNearWallPressureTrimmed:    Any   = None
    dcrData:                                dict  = field(default_factory = dict)
    debugMode:                              bool  = False

    # -- What the solve produces -- #
    channelRadius:                          Any   = None   # [m], one per station
    coolantExitPressure:                    Any   = None   # [Pa]
    coolantExitTemperature:                 Any   = None   # [K]
    wallMaterialResolved:                   Any   = None   # the alloy actually used
    tempRangeKelvin:                        Any   = None   # [K], the grid the curves are sampled on
    wallThermalConductivityData:            Any   = None   # [W/m K]
    wallThermalConductivityInterpolator:    Any   = None
    wallCTEInterpolator:                    Any   = None
    wallYieldStrengthInterpolator:          Any   = None
    wallFractureStrainInterpolator:         Any   = None

# The outputs a solve hands back. Kept beside the class so that adding a field and forgetting to
# surface it is a one-line fix rather than a silent drop.
channelSizingOutputs = (
    'channelRadius', 'nChannel', 'coolantExitPressure', 'coolantExitTemperature',
    'wallMaterialResolved', 'tempRangeKelvin', 'wallThermalConductivityData',
    'wallThermalConductivityInterpolator', 'wallCTEInterpolator',
    'wallYieldStrengthInterpolator', 'wallFractureStrainInterpolator')

def solveChannelRadii(state, geometry, thermal):

    '''

    Solve the channel radius distribution along the regen section.

    Marches from the coolant inlet, converging the radius at each station so the hot wall reaches
    the requested temperature, subject to the largest channel that fits there and the smallest the
    process can build.

    Parameters:
    -----------
    state : ChannelSizingState
        Engine, coolant and regen section. Its outputs are filled in and returned.
    geometry : ChannelGeometryInputs
        Channel definition the cross sections are rebuilt from at each proposed radius.
    thermal : RegenThermalContext
        Run-level settings the thermal model reads.

    Returns:
    --------
    ChannelSizingState
        The same state, with the radius distribution, the coolant exit condition and the wall
        property curves filled in. An output still None was never reached.

    '''

    # ------------------------------------------------------------------------------------------------------------------------------------ #
    # -- Private Methods -- #
    # ------------------------------------------------------------------------------------------------------------------------------------ #

    def findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i):

        '''

        This method uses the current station's guess for channel radius to find current station's channel centerline's 2D coordinates.
        Returns the current station's 2D channel centerline point (as an (x, r) pair), as well as the previous station's 2D channel
        centerline point (if i > 0) and a guess for the next station's 2D channel centerline point (if i < state.numCrossSections).

        '''

        channelOffsetDistance = state.hotWallThickness + channelRadius[i]

        match i:
            case 0:
                xChannelCenterline2D[:2], rChannelCenterline2D[:2] = parallelOffset(np.flip(xNozzle)[:2], np.flip(rNozzle)[:2], -channelOffsetDistance)
                return xChannelCenterline2D[:2], rChannelCenterline2D[:2]
            case _ if i == state.numCrossSections - 1:
                xChannelCenterline2D_temp, rChannelCenterline2D_temp = parallelOffset(np.flip(xNozzle)[:i+1], np.flip(rNozzle)[:i+1], -channelOffsetDistance)
                xChannelCenterline2D[-1], rChannelCenterline2D[-1] = xChannelCenterline2D_temp[-1], rChannelCenterline2D_temp[-1]
                return xChannelCenterline2D[i-1:i+1], rChannelCenterline2D[i-1:i+1]
            case _:
                xChannelCenterline2D_temp, rChannelCenterline2D_temp = parallelOffset(np.flip(xNozzle)[:i+2], np.flip(rNozzle)[:i+2], -channelOffsetDistance)
                xChannelCenterline2D[i:i+2], rChannelCenterline2D[i:i+2] = xChannelCenterline2D_temp[i:i+2], rChannelCenterline2D_temp[i:i+2]
                return xChannelCenterline2D[i-1:i+2], rChannelCenterline2D[i-1:i+2]

    def kineosAlgorithm_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, i,  findMaxRadius=False):

        '''

        This method generates the pathline angles for wrapping cooling channels around a rocket nozzle. Based on the current
        radius of the channel at the current station compared to the maximum radius the channel could be and still fit given
        an infill thickness and number of channel, a projection angle is calculated which represents the angle the channel
        would have to turn to ensure the circumferential space around the nozzle is filled. If the current channel radius is
        larger than the maximum radius of the channel that would fit, the radius is reduced so that it fits perfectly with no
        projection angle (straight channel).

        '''

        def tryMakeFit(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, xPathline2D, rPathline2D, i, nozzleArcSlice):
            # use current arc slice to solve for max channel radius that fits here
            channelArcLength = nozzleArcSlice
            channelDiameter = 8*rPathline2D[1] * np.sin(channelArcLength / (8*rPathline2D[1]))
            if state.channelType == 'fluted':
                channelRadius[i] = channelDiameter / (2 + state.fluteAmplitudeCoef)
            elif state.channelType == 'circle':
                channelRadius[i] = channelDiameter / 2
            # recalculate channel 2D centerline point here with new channel radius guess
            xPathline2D, rPathline2D = findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i)
            # rerun first half of the algo
            if i in (0, state.numCrossSections - 1):
                xPathline2D, rPathline2D = [np.concatenate(([0], arr)) for arr in (xPathline2D, rPathline2D)]

            # Calculate the distance between slices along the nozzle axis.
            xNozzleStep = xPathline2D[2] - xPathline2D[1]
            # Calculate the radial distance between slices from the nozzle axis.
            rNozzleStep = rPathline2D[2] - rPathline2D[1]

            # Calculate the arc length of the nozzle region allocated to each channel.
            nozzleArcSlice = 2*np.pi*rPathline2D[1]/nChannel - state.infillThickness

            # Calculate the arc length of the channel.
            channelArcLength = 4* rPathline2D[1] * np.arccos((2 * rPathline2D[1]**2 - (channelDiameter/4)**2) / (2 * rPathline2D[1]**2))

            return xNozzleStep, rNozzleStep, channelRadius[i], nozzleArcSlice, channelArcLength, xPathline2D, rPathline2D

        xPathline2D, rPathline2D = findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i)

        if i in (0, state.numCrossSections - 1):
            xPathline2D, rPathline2D = [np.concatenate(([0], arr)) for arr in (xPathline2D, rPathline2D)]

        # Calculate the distance between slices along the nozzle axis.
        xNozzleStep = xPathline2D[2] - xPathline2D[1]
        # Calculate the radial distance between slices from the nozzle axis.
        rNozzleStep = rPathline2D[2] - rPathline2D[1]

        # Calculate the arc length of the nozzle region allocated to each channel.
        nozzleArcSlice = 2*np.pi*rPathline2D[1]/nChannel - state.infillThickness

        # Calculate the diameter of each channel perpendicular to the pathline,
        # including the flute amplitude.
        if state.channelType == 'fluted':
            channelDiameter = (2*channelRadius[i] + state.fluteAmplitudeCoef*channelRadius[i])
        elif state.channelType == 'circle':
            channelDiameter = 2 * channelRadius[i]

        # Calculate the arc length of the channel.
        channelArcLength = 4* rPathline2D[1] * np.arccos((2 * rPathline2D[1]**2 - (channelDiameter/4)**2) / (2 * rPathline2D[1]**2))

        # smartRadii
        if findMaxRadius or channelArcLength > nozzleArcSlice:
            tolerance = 1e-9
            negativeTolerance = -1e-10
            maxIter = 50
            iteration = 0

            while True:
                diff = nozzleArcSlice - channelArcLength
                if diff < 0 and diff > negativeTolerance:
                    channelArcLength = nozzleArcSlice
                    diff = 0.0
                if diff < 0 or diff > tolerance:
                    xNozzleStep, rNozzleStep, channelRadius[i], nozzleArcSlice, channelArcLength, xPathline2D, rPathline2D = \
                        tryMakeFit(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, xPathline2D, rPathline2D, i, nozzleArcSlice)
                else:
                    if findMaxRadius:
                        return channelRadius[i]
                    else:
                        break
                iteration += 1
                if iteration > maxIter:
                    raise ValueError(
                        f"Convergence failed after {maxIter} iterations: "
                        f"nozzleArcSlice = {nozzleArcSlice:.9e}, "
                        f"channelArcLength = {channelArcLength:.9e}, "
                        f"diff = {diff:.3e}"
                    )

        # Calculate the projection angle required to make the channel cross-section
        # equivalent to the region of the nozzle allocated to it.
        projectionAngle = np.real(np.arccos(channelArcLength/nozzleArcSlice))
        state.dcrData['projectionAngle'][i] = projectionAngle

        # Calculate the arc length of channel movement in the x direction projected on the pathline.
        xArc = 2 * rPathline2D[1] * np.arccos((2*rPathline2D[1]**2 - ((xNozzleStep*np.tan(projectionAngle))/2)**2)/ (2 * rPathline2D[1]**2))

        # Calculate the arc length of channel movement in the r direction projected on the pathline.
        rArc = 2 * rPathline2D[1] * np.arccos((2*rPathline2D[1]**2 - ((rNozzleStep/np.tan(np.pi/2-projectionAngle))/2)**2)/ (2 * rPathline2D[1]**2))

        # Calculate the position of each pathline point projected on the nozzle wall in degrees.
        # Project the point from the previous axial slice to the next slice and then add
        # the arc length required to position the channel.

        if i == 0:
            helixPath[i] = 0
        elif i == state.numCrossSections - 1:
            helixPath[i] = ((helixPath[i-1] * rPathline2D[2]) - np.sqrt(xArc**2 + rArc**2)) / rPathline2D[2]
        else:
            helixPath[i] = ((helixPath[i-1] * rPathline2D[0]) - np.sqrt(xArc**2 + rArc**2)) / rPathline2D[0]

        # if 0 < i < state.numCrossSections - 1:
            helixPath[i+1] = ((helixPath[i] * rPathline2D[1]) - np.sqrt(xArc**2 + rArc**2)) / rPathline2D[1]

        state.dcrData['helixPath'][i] = helixPath[i]

        return helixPath, channelRadius

    def wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i):

        '''

        Uses kineosAlgorithm_oneStation() to wrap channel centerline around nozzle.
        Outputs the current station's 3D centerline point and a guess for the next station's 3D centerline point (if i < state.numCrossSections).

        '''

        helixPath, channelRadius = kineosAlgorithm_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, i)
        wrapAngle = helixPath[i]
        valueMatrix = [xChannelCenterline2D[i], rChannelCenterline2D[i], 0]
        eulerAngles = [wrapAngle, 0, 0]
        xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i] = DCM(eulerAngles, valueMatrix)

        state.dcrData['wrapAngles'][i] = wrapAngle

        if i < state.numCrossSections - 1:
            wrapAngle = helixPath[i+1]
            valueMatrix = [xChannelCenterline2D[i+1], rChannelCenterline2D[i+1], 0]
            eulerAngles = [wrapAngle, 0, 0]
            xChannelCenterline3D[i+1], yChannelCenterline3D[i+1], zChannelCenterline3D[i+1] = DCM(eulerAngles, valueMatrix)

            state.dcrData['wrapAngles'][i] = wrapAngle

            return xChannelCenterline3D[i:i+2], yChannelCenterline3D[i:i+2], zChannelCenterline3D[i:i+2], channelRadius

        return xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i], channelRadius

    def dcrGambit(heatTransferDict_i, heatTransferPlots, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, channelRadius, channelType, i):

        '''

        This wrapper functinalizes the process of generating the cross section and running regen heat transfer analysis at one station

        The heat transfer inputs and plots dictionary are taken in and returned updated.
        The hot wall temperature result is also returned as a scalar.

        '''

        # get local combustion properties
        heatTransferDict_i["xHotWall3D"]          = np.array([xNozzle                                     [state.numCrossSections - 1 - i]])
        heatTransferDict_i["rHotWall3D"]          = np.array([rNozzle                                     [state.numCrossSections - 1 - i]])
        heatTransferDict_i["gamma"]               = np.array([state.gammaRegenSectionTrimmed               [state.numCrossSections - 1 - i]])
        heatTransferDict_i["molecularWeight"]     = np.array([state.molecularWeightRegenSectionTrimmed     [state.numCrossSections - 1 - i]])
        heatTransferDict_i["gasConstant"]         = np.array([state.gasConstantRegenSectionTrimmed         [state.numCrossSections - 1 - i]])
        heatTransferDict_i["nearWallMachNumber"]  = np.array([state.regenSectionNearWallMachNumberTrimmed  [state.numCrossSections - 1 - i]])
        heatTransferDict_i["nearWallTemperature"] = np.array([state.regenSectionNearWallTemperatureTrimmed [state.numCrossSections - 1 - i]])
        heatTransferDict_i["drivingTemperature"]  = np.array([drivingTemperatureArray(state)      [state.numCrossSections - 1 - i]])
        heatTransferDict_i["nearWallPressure"]    = np.array([state.regenSectionNearWallPressureTrimmed    [state.numCrossSections - 1 - i]])

        # get geometry properties for heat transfer
        heatTransferDict_iUpdate = \
            buildCrossSections(geometry, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D,
                                       channelRadius, channelType, i)

        # update local heat transfer dictionary
        heatTransferDict_i = heatTransferDict_i | heatTransferDict_iUpdate

        # run single station regen heat transfer model
        if channelType == 'fluted':
            heatTransferOutputs, plotOutputs, _, _ \
                = solveRegenHeatTransfer(thermal, heatTransferDict_i,returnDict=True)
        elif channelType == 'circle':
            _, _, heatTransferOutputs, plotOutputs \
                = solveRegenHeatTransfer(thermal, heatTransferDict_i,returnDict=True)
        # update local heat transfer dictionary
        hotWallTemperature                          = heatTransferOutputs['hotWallTemperature']
        heatTransferDict_i['newCoolantTemperature'] = heatTransferOutputs['coolantTemperature'][0]
        heatTransferDict_i['newCoolantPressure']    = heatTransferOutputs['coolantPressure'][0]
        # update global plot outputs
        for key in THERMALPLOTKEYS:
            heatTransferPlots[key][state.numCrossSections - 1 - i] = plotOutputs[key][0]

        return heatTransferDict_i, heatTransferPlots, hotWallTemperature

    # ------------------------------------------------------------------------------------------------------------------------------------ #
    # -- Do The Thing -- #
    # ------------------------------------------------------------------------------------------------------------------------------------ #

    state.dcrData['projectionAngle'], state.dcrData['helixPath'], state.dcrData['wrapAngles'], \
    state.dcrData['minorLoss'], state.dcrData['frictionLoss'], state.dcrData['Kfactor'], state.dcrData['isCircle'] = \
        [np.zeros((state.numCrossSections)) for _ in range(7)]

    # Locally scope nozzle wall values
    xNozzle, rNozzle = state.xRegenNozzleTrimmed, state.rRegenNozzleTrimmed

    # Temperature-dependent wall alloy properties, sampled from
    # materials.wallMaterialCurves so the model is not tied to one alloy. The legacy
    # 'cu' / 'al' / 'in' keys still resolve, to GRCop-42 / AlSi10Mg / Inconel 718.
    # Conductivity and CTE are on the thermal-strain solution path; yield strength and
    # elongation are carried for downstream margin checks. Values are clamped at the
    # ends of each property's temperature grid rather than extrapolated.
    if True:
        state.wallThermalConductivityInterpolator = np.empty(state.numCrossSections, dtype=object)

        wallCurves                = wallMaterialCurves(state.material)
        state.wallMaterialResolved = wallCurves['material']
        wallTemperatureGrid       = wallCurves['temperatureK']

        def _clampedCurve(propertyArray):
            return interp1d(wallTemperatureGrid, propertyArray, kind='linear',
                            bounds_error=False, fill_value=(propertyArray[0], propertyArray[-1]))

        state.wallThermalConductivityInterpolator.fill(_clampedCurve(wallCurves['thermalConductivity']))
        state.wallYieldStrengthInterpolator  = _clampedCurve(wallCurves['yieldStrength'])
        state.wallFractureStrainInterpolator = _clampedCurve(wallCurves['elongation'])
        state.wallCTEInterpolator            = _clampedCurve(wallCurves['cte'])

        # Raw arrays retained for callers that plotted them directly.
        state.tempRangeKelvin           = wallTemperatureGrid
        state.wallThermalConductivityData = wallCurves['thermalConductivity']

    # Create channel radii based on heat transfer
    def dynamicChannelRadii(maxWallTemperature, nChannel):

        '''

        Generate cooling channel radius distribution via heat transfer convergence.

        Marches along the nozzle in the direction of coolant flow, solving for the channel
        radius at each station that achieves the target wall temperature. At each station,
        an iterative convergence loop adjusts channel radius until wall temperature is within
        0.01% of the specified maximum. This approach simultaneously prevents wall overheating
        while minimizing pressure drop by using the largest channel radius that meets thermal
        constraints.

        ### Parameters

        | Parameter | Type | Description |
        |-----------|------|-------------|
        | `maxWallTemperature` | `np.ndarray` | Maximum allowable wall temperature at each station [K] |
        | `nChannel` | `int` | Number of cooling channels |

        ### Returns

        `tuple` - Six-element tuple of arrays (all flipped to nozzle coordinate convention):

        | Element | Type | Description |
        |---------|------|-------------|
        | `channelRadius` | `np.ndarray` | Channel radius at each station [m] |
        | `xChannelCenterline2D` | `np.ndarray` | X coordinates of 2D centerline [m] |
        | `rChannelCenterline2D` | `np.ndarray` | Radial coordinates of 2D centerline [m] |
        | `xChannelCenterline3D` | `np.ndarray` | X coordinates of 3D centerline [m] |
        | `yChannelCenterline3D` | `np.ndarray` | Y coordinates of 3D centerline [m] |
        | `zChannelCenterline3D` | `np.ndarray` | Z coordinates of 3D centerline [m] |

        ### Notes

        - Validates nChannel against throat geometry; reduces automatically in normal mode.
        - Calls `dynamicConvergenceLoop_channelRadius()` at each station for radius optimization.
        - Uses `findChannelCenterline_oneStation()`, `kineosAlgorithm_oneStation()`, and
          `heatTransferModel_oneStation()` for stepwise geometry and thermal calculations.
        - Updates `state.dcrData` with channel heat transfer inputs and centerline coordinates.
        - Sets `state.coolantExitPressure` and `state.coolantExitTemperature`.
        - Generates diagnostic plots when `thermal.plotsAdv == 'on'`.

        ---

        Author: Cam'ron Valliere
        Date:   2025

        '''

        # first check if nChannel is too high and reduce if so
        if True:
            throatRadius = min(rNozzle)
            offsetHotWallThickness = state.hotWallThickness - state.infillThickness
            arcAngle = 2*np.pi / nChannel
            theta = arcAngle/2
            R = throatRadius + offsetHotWallThickness
            r = R*np.sin(theta) / (1 - np.sin(theta))
            circleChannelThroatRadius = r - state.infillThickness / 2
            flutedChannelThroatRadius = circleChannelThroatRadius / (1 + state.fluteAmplitudeCoef/2)
            if state.channelType == 'fluted':
                if flutedChannelThroatRadius < state.minChannelRadius:
                    print(f'\nnChannel too high; channel radius at throat will be too small.')
                    flutedChannelThroatRadius = state.minChannelRadius
                    nChannel = int(np.pi / (np.arcsin((flutedChannelThroatRadius * (1 + state.fluteAmplitudeCoef / 2) + \
                                    state.infillThickness[0] / 2)/(flutedChannelThroatRadius * (1 + state.fluteAmplitudeCoef / 2) + \
                                        state.infillThickness[0] / 2 + throatRadius + state.hotWallThickness - state.infillThickness[0]))))
                    state.nChannel = nChannel
                    print(f'\nnChannel reduced to {nChannel}.')
            elif state.channelType == 'circle':
                if circleChannelThroatRadius < state.minChannelRadius:
                    print(f'\nnChannel too high; channel radius at throat will be too small.')
                    circleChannelThroatRadius = state.minChannelRadius
                    nChannel = int(np.pi / (np.arcsin((circleChannelThroatRadius + state.infillThickness[0]/2) / \
                                (circleChannelThroatRadius + state.infillThickness[0]/2 + throatRadius + state.hotWallThickness - state.infillThickness[0]))))
                    state.nChannel = nChannel
                    print(f'\nnChannel reduced to {nChannel}.')

        # initialize arrays and values
        channelRadius = np.zeros(state.numCrossSections)
        xChannelCenterline2D, rChannelCenterline2D = [np.zeros((state.numCrossSections)) for _ in range(2)]
        helixPath = np.zeros(state.numCrossSections)
        xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D = [np.zeros((state.numCrossSections)) for _ in range(3)]

        # --------------------- Dynamic convergence loop for channelRadius --------------------- #
        def dynamicConvergenceLoop_channelRadius(channelRadius, nChannel, minChannelRadius, maxChannelRadius, i, heatTransferDict_i, heatTransferPlots, hotWallTemperature):

            '''

            Iteratively solve for channel radius that achieves target wall temperature at a station.

            Uses an adaptive step-sizing algorithm to find the channel radius that brings wall
            temperature within 0.01% of the target. Step size scales with error magnitude (larger
            steps when far from target, smaller when close). Includes backtracking for non-improving
            moves, overshoot damping when error sign flips, and a confirmation nudge at convergence
            to fine-tune the final value.

            ### Parameters

            | Parameter | Type | Description |
            |-----------|------|-------------|
            | `channelRadius` | `np.ndarray` | Channel radius array (modified in place) [m] |
            | `nChannel` | `int` | Number of cooling channels |
            | `minChannelRadius` | `float` | Minimum allowable channel radius [m] |
            | `maxChannelRadius` | `float` | Maximum allowable channel radius at this station [m] |
            | `i` | `int` | Station index to solve |

            ### Returns

            `int` - Convergence status:

            - Returns 1 on successful convergence (wall temp within 0.01% of target).
            - Returns 0 on failure due to excessive pressure drop, minimum radius reached,
              or iteration limit exceeded.

            ### Notes

            - Modifies `channelRadius[i]` and associated centerline coordinate arrays in place.
            - Updates `channelHeatTransferInputs[i]` with geometry for the converged radius.
            - Direction logic: if too hot, decrease radius; if too cold, increase radius.
            - Step fraction ramps from 0.01% (near target) to 40% (far from target).
            - Backtracking halves step size up to 6 times if error doesn't improve.
            - Overshoot damping halves next step when error sign flips.
            - Confirmation nudge (25% of last step) attempts to fine-tune within tolerance.

            ### Raises

            - `ConvergenceFailureError` - If minimum radius reached without convergence (debugMode=False).
            - `ConvergenceFailureError` - If iteration limit exceeded without convergence (debugMode=False).

            ---

            Author: Cam'ron Valliere
            Date:   2025

            '''

            # ---------- Dynamic step-sizing settings ---------- #
            targetToleranceFraction = 0.0001    # 0.01%
            tempTolerance = targetToleranceFraction * maxWallTemperature

            # Smooth ramp for step fraction; maps normalized error to change fraction
            minChangeFraction = 0.0001          # 0.01% step when very close to target
            maxChangeFraction = 0.40            # up to 40% when far from target
            maxNormalizedError = 100.0          # >100× tolerance : use max fraction

            # Backtracking & jitter control
            backtrackShrinkFactor = 0.5         # halve step if error did not improve
            maxBacktrackTries = 10
            lastStepConfirmationFraction = 0.25 # extra confirmation nudge size

            # For overshoot damping (reduce next step size after sign-flip)
            nextIterationStepFractionScale = 0.25
            nextIterationOvershootShrinkFactor = 0.25
            lastErrorSign = 0

            iterationsUsed = 0
            maxSolverIterations = 50

            # Start from current values
            currentRadius = channelRadius[i]
            currentWallTemp = hotWallTemperature
            currentError = currentWallTemp - maxWallTemperature

            while abs(currentError) > tempTolerance and iterationsUsed < maxSolverIterations:
                # Compute how many tolerances away we are, then smoothly map to a step fraction
                normalizedErrorMagnitude = abs(currentError) / max(tempTolerance, 1e-12)
                # smooth ramp clamp 0-1
                ramp = max(0.0, min(1.0, normalizedErrorMagnitude / maxNormalizedError))
                baseStepFraction = minChangeFraction + ramp * (maxChangeFraction - minChangeFraction)
                proposedStepFraction = baseStepFraction * nextIterationStepFractionScale

                # Decide direction: if too hot, decrease radius, if too cold, increase radius
                if currentError > 0.0:  # too hot
                    stepSign = -1
                else:  # too cold
                    stepSign = +1

                proposedStep = stepSign * proposedStepFraction * currentRadius
                proposedRadius = currentRadius + proposedStep

                # bounds
                minMaxed = False
                if proposedRadius > maxChannelRadius:
                    proposedRadius = maxChannelRadius
                    minMaxed = True
                if proposedRadius < minChannelRadius:
                    proposedRadius = minChannelRadius
                    minMaxed = True

                channelRadius[i] = proposedRadius

                # Wrap
                if i < state.numCrossSections - 1:
                    xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[0] if i == 0 else arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                    xChannelCenterline3D[i:i+2], yChannelCenterline3D[i:i+2], zChannelCenterline3D[i:i+2], channelRadius = \
                        wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)
                else:
                    xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                    xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i], channelRadius = \
                        wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)

                # if channelRadius was changed by smartRadii, make that the new max
                if channelRadius[i] != proposedRadius:
                    maxChannelRadius = channelRadius[i]
                    proposedRadius = maxChannelRadius

                heatTransferDict_i, heatTransferPlots, hotWallTemperature = \
                    dcrGambit(heatTransferDict_i, heatTransferPlots, \
                              xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, channelRadius, state.channelType, i)

                # Backtracking: if we didn’t improve error, shrink the step and retry from the previous radius
                backtrackCounter = 0
                newWallTemp = hotWallTemperature
                newError = newWallTemp - maxWallTemperature
                while abs(newError) >= abs(currentError) and backtrackCounter < maxBacktrackTries:
                    currentError = newError
                    proposedStep *= backtrackShrinkFactor
                    proposedRadius = currentRadius + proposedStep
                    # bounds
                    minMaxed = False
                    if proposedRadius > maxChannelRadius:
                        proposedRadius = maxChannelRadius
                        minMaxed = True
                    if proposedRadius < minChannelRadius:
                        proposedRadius = minChannelRadius
                        minMaxed = True

                    channelRadius[i] = proposedRadius

                    # Wrap
                    if i < state.numCrossSections - 1:
                        xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[0] if i == 0 else arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                        xChannelCenterline3D[i:i+2], yChannelCenterline3D[i:i+2], zChannelCenterline3D[i:i+2], channelRadius = \
                            wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)
                    else:
                        xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                        xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i], channelRadius = \
                            wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)

                    # if channelRadius was changed by smartRadii, make that the new max
                    if channelRadius[i] != proposedRadius:
                        maxChannelRadius = channelRadius[i]
                        proposedRadius = maxChannelRadius

                    heatTransferDict_i, heatTransferPlots, hotWallTemperature = \
                        dcrGambit(heatTransferDict_i, heatTransferPlots, \
                                  xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, channelRadius, state.channelType, i)

                    newWallTemp = hotWallTemperature
                    newError = newWallTemp - maxWallTemperature
                    backtrackCounter += 1

                    if minMaxed:
                        newError = 0

                # Overshoot / jitter damping: if error sign flipped, shrink next step size
                newErrorSign = np.sign(newError)
                if lastErrorSign != 0 and newErrorSign != 0 and newErrorSign != lastErrorSign:
                    nextIterationStepFractionScale *= nextIterationOvershootShrinkFactor
                lastErrorSign = newErrorSign

                # Accept the move
                currentRadius = proposedRadius
                currentWallTemp = newWallTemp
                currentError = newError
                iterationsUsed += 1

                # Early stop if we’re inside tolerance; do the extra confirmation nudge
                if abs(currentError) <= tempTolerance:
                    # Try a tiny additional move in the same helpful direction; keep it only if it improves error
                    confirmationStep = lastStepConfirmationFraction * proposedStep
                    trialRadius = currentRadius + confirmationStep
                    # bounds
                    minMaxed = False
                    if trialRadius > maxChannelRadius:
                        trialRadius = maxChannelRadius
                        minMaxed = True
                    if trialRadius < minChannelRadius:
                        trialRadius = minChannelRadius
                        minMaxed = True

                    channelRadius[i] = trialRadius

                    if i < state.numCrossSections - 1:
                        xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[0] if i == 0 else arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                        xChannelCenterline3D[i:i+2], yChannelCenterline3D[i:i+2], zChannelCenterline3D[i:i+2], channelRadius = \
                            wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)
                    else:
                        xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                        xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i], channelRadius = \
                            wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)

                    # if channelRadius was changed by smartRadii, make that the new max
                    if channelRadius[i] != trialRadius:
                        maxChannelRadius = channelRadius[i]
                        trialRadius = maxChannelRadius

                    heatTransferDict_i, heatTransferPlots, hotWallTemperature = \
                        dcrGambit(heatTransferDict_i, heatTransferPlots, \
                                  xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, channelRadius, state.channelType, i)

                    confirmationError = hotWallTemperature - maxWallTemperature

                    # Keep confirmation move only if it improved error
                    if abs(confirmationError) < abs(currentError):
                        currentRadius = channelRadius[i]
                        currentError = confirmationError
                    else:

                        channelRadius[i] = currentRadius  # revert

                        # rerun algos to get back old geometries and properties
                        if i < state.numCrossSections - 1:
                            xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[0] if i == 0 else arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                            xChannelCenterline3D[i:i+2], yChannelCenterline3D[i:i+2], zChannelCenterline3D[i:i+2], channelRadius = \
                                wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)
                        else:
                            xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                            xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i], channelRadius = \
                                wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)

                        heatTransferDict_i, heatTransferPlots, hotWallTemperature = \
                            dcrGambit(heatTransferDict_i, heatTransferPlots, \
                                      xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, channelRadius, state.channelType, i)

                        break  # done at this station

            # If we exited due to iteration cap and radius is at minimum, terminate with fail state
            if iterationsUsed >= maxSolverIterations and currentRadius <= minChannelRadius:
                if not state.debugMode:
                    raise ConvergenceFailureError(
                        message=f"Minimum channel radius reached at station {i} without achieving temperature convergence",
                        context=createErrorContext(
                            stationIndex=i,
                            iterationCount=iterationsUsed,
                            channelRadius=currentRadius,
                            minChannelRadius=minChannelRadius,
                            wallTemperature=hotWallTemperature,
                            targetTemperature=maxWallTemperature[i],
                            temperatureError=abs(hotWallTemperature - maxWallTemperature[i]),
                            tempTolerance=tempTolerance
                        ),
                        iterations=iterationsUsed,
                        tolerance=tempTolerance,
                        residual=abs(hotWallTemperature - maxWallTemperature)
                    )
                print(f"\nWarning: Minimum channel radius reached at station {i}. Wall temp = {hotWallTemperature:.1f} K")
                return 0

            # If we exited due to iteration cap without convergence, terminate with fail state
            if abs(hotWallTemperature - maxWallTemperature) > tempTolerance and iterationsUsed >= maxSolverIterations and not minMaxed:
                if not state.debugMode:
                    raise ConvergenceFailureError(
                        message=f"Temperature convergence failed at station {i} after {maxSolverIterations} iterations",
                        context=createErrorContext(
                            stationIndex=i,
                            iterationCount=iterationsUsed,
                            channelRadius=currentRadius,
                            wallTemperature=hotWallTemperature,
                            targetTemperature=maxWallTemperature,
                            temperatureError=abs(hotWallTemperature - maxWallTemperature),
                            tempTolerance=tempTolerance,
                            coolantPressure=heatTransferDict_i['coolantInitialPressure'],
                            coolantTemperature=heatTransferDict_i['coolantInitialTemperature']
                        ),
                        iterations=iterationsUsed,
                        tolerance=tempTolerance,
                        residual=abs(hotWallTemperature - maxWallTemperature)
                    )
                print(f"\nWarning: station {i} did not converge within {maxSolverIterations} iterations."
                      f"\nFinal wall temp at station {i} = {hotWallTemperature:.2f} K")
                return 0

            # Accept new coolant temperature and pressure as next station initial conditions
            heatTransferDict_i['coolantInitialTemperature'] = heatTransferDict_i['newCoolantTemperature']
            heatTransferDict_i['coolantInitialPressure']    = heatTransferDict_i['newCoolantPressure']

            return heatTransferDict_i
        # -------------------------------------------------------------------------------------- #

        # collapse dictionary instantiation
        if True:

            # instantiate base dictionary
            heatTransferDict_i = {}
            # the local dictionary constains scalars and arrays of length 1
            heatTransferDict_i["numCrossSections"]                = 1
            heatTransferDict_i["nChannel"]                        = state.nChannel
            heatTransferDict_i["hotWallThickness"]                = state.hotWallThickness
            heatTransferDict_i["throatRadiusOfCurvature"]         = (state.throatInletCurvatureNonDimensional*state.nozzleScalingFactor + \
                                                                     state.throatOutletCurvatureNonDimensional*state.nozzleScalingFactor) / 2
            heatTransferDict_i["throatDiameter"]                  = 2 * min(rNozzle)
            heatTransferDict_i["throatArea"]                      = np.pi * (min(rNozzle)**2)
            heatTransferDict_i["fluteAmplitudeCoef"]              = state.fluteAmplitudeCoef
            heatTransferDict_i["fluteHelixAngle"]                 = abs(state.fluteHelixAngle)
            heatTransferDict_i["coolant"]                         = state.coolant
            heatTransferDict_i["mdot"]                            = state.coolantMassFlow / state.nChannel
            heatTransferDict_i["chamberPressure"]                 = state.chamberPressure
            heatTransferDict_i["coolantInitialTemperature"]       = state.coolantInitialTemperature
            heatTransferDict_i["coolantInitialPressure"]          = state.coolantInitialPressure
            heatTransferDict_i["theoreticalCharVel"]              = state.theoreticalCharacteristicVelocity

            baseHeatTransferDict = heatTransferDict_i.copy()

            # instantiate plot outputs dictionary
            heatTransferPlots = {}
            heatTransferPlots["xHotWall3D"] = xNozzle
            heatTransferPlots["rHotWall3D"] = rNozzle
            for key in THERMALPLOTKEYS:
                heatTransferPlots[key] = np.zeros(state.numCrossSections)

        # find max channel radius at each station
        for i in tqdm(range(state.numCrossSections), desc="Solving for channel radii", colour="#ABD038"):

            if state.channelType == 'fluted':
                maxFlutedChannelRadius = kineosAlgorithm_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, i, findMaxRadius=True)
                maxChannelRadius = maxFlutedChannelRadius
            elif state.channelType == 'circle':
                maxCircleChannelRadius = kineosAlgorithm_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, i, findMaxRadius=True)
                maxChannelRadius = maxCircleChannelRadius

            # next station will always start at last station's converged radius
            if i == 0:
                channelRadius[i] = maxChannelRadius
            else:
                channelRadius[i] = channelRadius[i-1]
            if channelRadius[i] > maxChannelRadius:
                channelRadius[i] = maxChannelRadius
            if channelRadius[i] < state.minChannelRadius:
                channelRadius[i] = state.minChannelRadius

            # Wrap
            if i < state.numCrossSections - 1:
                xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[0] if i == 0 else arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                xChannelCenterline3D[i:i+2], yChannelCenterline3D[i:i+2], zChannelCenterline3D[i:i+2], channelRadius = \
                    wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)
            else:
                xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i], channelRadius = \
                    wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)

            heatTransferDict_i, heatTransferPlots, hotWallTemperature = \
                dcrGambit(heatTransferDict_i, heatTransferPlots, \
                        xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, channelRadius, state.channelType, i)

            heatTransferDict_i = dynamicConvergenceLoop_channelRadius(channelRadius, nChannel, state.minChannelRadius, maxChannelRadius, i, heatTransferDict_i, heatTransferPlots, hotWallTemperature)

        # The station loop marches from the coolant inlet, and each station is written
        # into heatTransferPlots reversed, at N - 1 - i. That puts the inlet at the last
        # index and the exit at the first, which is the convention the model's own
        # summary uses when it reports a pressure drop. Reading the last index instead
        # returned the inlet state under the name of the exit state, and the return
        # volute is sized from it: the wall thickness comes from the GRCop yield strength
        # at that temperature, and a cryogenic inlet temperature reports a far higher
        # yield strength than the warm exit the volute actually sees.
        state.coolantExitPressure    = heatTransferPlots['pressure'][0]
        state.coolantExitTemperature = heatTransferPlots['temperature'][0]

        return np.flip(channelRadius), np.flip(xChannelCenterline3D), np.flip(yChannelCenterline3D), np.flip(zChannelCenterline3D), \
            heatTransferPlots, baseHeatTransferDict

    channelRadius, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, heatTransferPlots, heatTransferDict \
        = dynamicChannelRadii(state.maxWallTemperature, state.nChannel)

    state.channelRadius = channelRadius.copy()

    # Heat transfer plots
    if state.channelType == 'fluted':

        # Get comparison
        heatTransferDict["numCrossSections"]    = state.numCrossSections
        heatTransferDict["xHotWall3D"]          = state.xRegenNozzleTrimmed
        heatTransferDict["rHotWall3D"]          = state.rRegenNozzleTrimmed
        heatTransferDict["gamma"]               = state.gammaRegenSectionTrimmed
        heatTransferDict["molecularWeight"]     = state.molecularWeightRegenSectionTrimmed
        heatTransferDict["gasConstant"]         = state.gasConstantRegenSectionTrimmed
        heatTransferDict["nearWallMachNumber"]  = state.regenSectionNearWallMachNumberTrimmed
        heatTransferDict["nearWallTemperature"] = state.regenSectionNearWallTemperatureTrimmed
        heatTransferDict["drivingTemperature"]  = drivingTemperatureArray(state)
        heatTransferDict["nearWallPressure"]    = state.regenSectionNearWallPressureTrimmed
        keysHX = ["gausFlutedCSA","gausFlutedSA","circleCSA","circleSA","differentialPathLength","fluteAmplitudeGauss","flutePitch","turnAngle","radiusOfCurvature","isCircle"]
        for key in keysHX:
            heatTransferDict[key] = np.zeros(state.numCrossSections)
        for i in tqdm(range(state.numCrossSections), desc="Verifying Heat Transfer:", colour="#ABD038"):
            heatTransferDict_Update = buildCrossSections(geometry, xChannelCenterline3D, yChannelCenterline3D,
                                                            zChannelCenterline3D, channelRadius, 'fluted', i = i)
            for key in keysHX:
                heatTransferDict[key][i] = heatTransferDict_Update[key][0]

        # The circular result is solved alongside the fluted one so the two can be drawn
        # against each other, which is what the fluted channel was adopted on.
        _, _, _, circleHeatTransferPlots = \
            solveRegenHeatTransfer(thermal, heatTransferDict,returnDict=True,plots=False)

        drawRegenHeatTransfer(thermal, coolant=state.coolant,nChannel=state.nChannel,
                                         flutedResults=heatTransferPlots, circleResults=circleHeatTransferPlots,
                                         titleFlare=', dcr( ) results',xReference = state.xRegenNozzle, rReference = state.rRegenNozzle)

    if state.channelType == 'circle':
        drawRegenHeatTransfer(thermal, coolant=state.coolant,nChannel=state.nChannel,
                                         circleResults=heatTransferPlots,
                                         titleFlare=', dcr( ) results',xReference = state.xRegenNozzle, rReference = state.rRegenNozzle)

    return state
