
# -- NOVA: Regen Section Split and Station Properties -- #

'''

Deciding how far down the nozzle the cooling jacket runs.

A regeneratively cooled nozzle is not cooled all the way to the exit. Past some station the
wall is cool enough to survive uncooled, and carrying the jacket further costs mass and
pressure drop for nothing. This module makes that cut and hands back two sections: the regen
section the jacket is built on, and the extension beyond it.

Where to cut is set by `regenTruncationType` and `regenTruncationValue`:

    'none'      No cut. The jacket runs the whole contour. The value is ignored.
    'temp'      Cut where the near-wall recovery temperature falls to the value, in kelvin.
    'er'        Cut at the value, an area ratio.

Both sections then get a full set of exhaust properties at every station. Those come from the
thermochemistry rather than from the flowfield: CEA is called at each station's area ratio, and
returns the gas composition, transport properties and near-wall state there.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**The station properties are CEA's.** The thermochemistry is validated in
`tests/testCeaInterface.py` against CEARun for the worked LOX/LH2 case. What is not validated is
the assumption that a one-dimensional station property describes the gas at the wall.

**That assumption is the largest disclosed approximation in the cooling model.** The near-wall
Mach number the method of characteristics returns departs from the one-dimensional value at the
same area ratio by up to 42 percent near the throat. Every gas-side transport property the
thermal model reads comes from here, one-dimensionally, while the geometry it is applied to
came from the characteristics solve. The two are inconsistent with each other, and the throat
is where the heat flux is highest.

Closing that gap means sampling the flowfield rather than a one-dimensional station, which is a
change to what is modeled rather than to how it is computed.

**The split itself is arithmetic**: an interpolation onto a temperature or an area ratio, and
the tests hold it to the station it names.

All units are mass base SI:
    - Length      [m]
    - Temperature [K]
    - Pressure    [Pa]
    - Density     [kg/m^3]
    - Viscosity   [Pa s]

Author: Sean Bowman

'''

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.interpolate import interp1d

from .geometryTools import arcSpline, chunkInterpolate
from .errors import ThermalConstraintError, createErrorContext, InvalidInputError
from .figures import showFigure, drawContourFigure, drawNearWallFigure, drawFieldFigure
from .filmCooling import filmCoolantState, filmCoolingArrays, entrainmentFilmArrays
from .ceaInterface import CEA
from .contour import divergingSectionFamily

@dataclass
class RegenStationState:

    '''

    Everything the split reads, and the two sections it produces.

    Every field starts as None. One still None afterwards is a branch that was not reached, which
    is worth keeping rather than hiding behind an empty array.

    '''

    # -- The contour and the propellants the stations are sampled from -- #
    Fuel:                                        Any = None
    chamberGamma:                                Any = None
    engineMassFlow:                              Any = None
    filmCooling:                                 Any = None
    filmCoolant:                                 Any = None
    filmCoolantMixtureRatio:                     Any = None
    filmCoolingModel:                            Any = None
    filmEntrainmentMultiplier:                   Any = None
    filmInjectionAxialPosition:                  Any = None
    filmInletTemperature:                        Any = None
    filmMassFlow:                                Any = None
    filmSlotHeight:                              Any = None
    OFRatio:                                     Any = None
    Oxidizer:                                    Any = None
    allMachNumbers:                              Any = None
    allPressures:                                Any = None
    allRPoints:                                  Any = None
    allTemperatures:                             Any = None
    allXPoints:                                  Any = None
    chamberPressure:                             Any = None
    dataFolder:                                  Any = None
    divergingSectionType:                        Any = None
    export:                                      Any = None
    idealMachNumber:                             Any = None
    nozzleNearWallMachNumber:                    Any = None
    nozzleNearWallPressure:                      Any = None
    nozzleNearWallRecoveryTemperature:           Any = None
    nozzleNearWallTemperature:                   Any = None
    nozzleNearWallVelocity:                      Any = None
    nozzleScalingFactor:                         Any = None
    numContourPoints:                            Any = None
    numCrossSections:                            Any = None
    oxidizerInitialTemperature:                  Any = None
    rNozzleWall:                                 Any = None
    targetExitPressure:                          Any = None
    regenTruncationType:                         Any = None
    regenTruncationValue:                        Any = None
    plotsEnabled:                                Any = None
    xNozzleWall:                                 Any = None

    # -- The two sections and their station properties -- #
    areaRatioArray:                              Any = None
    densityExtension:                            Any = None
    densityRegenSection:                         Any = None
    exitExpansionRatio:                          Any = None
    extensionNearWallMachNumber:                 Any = None
    extensionNearWallPressure:                   Any = None
    extensionNearWallRecoveryTemperature:        Any = None
    extensionNearWallTemperature:                Any = None
    extensionNearWallVelocity:                   Any = None
    gammaExtension:                              Any = None
    gammaRegenSection:                           Any = None
    gasConstantExtension:                        Any = None
    gasConstantRegenSection:                     Any = None
    inletContractionRatio:                       Any = None
    molecularWeightExtension:                    Any = None
    molecularWeightRegenSection:                 Any = None
    prandtlExtension:                            Any = None
    prandtlNumberRegenSection:                   Any = None
    rExtension:                                  Any = None
    rRegenNozzle:                                Any = None
    regenSectionNearWallMachNumber:              Any = None
    regenSectionNearWallPressure:                Any = None
    regenSectionNearWallRecoveryTemperature:     Any = None
    regenSectionNearWallTemperature:             Any = None
    regenSectionNearWallVelocity:                Any = None
    reynoldsExtension:                           Any = None
    reynoldsNumberRegenSection:                  Any = None
    specificHeatExtension:                       Any = None
    specificHeatRegenSection:                    Any = None
    thermalCondExtension:                        Any = None
    thermalConductivityRegenSection:             Any = None
    viscosityExtension:                          Any = None
    viscosityRegenSection:                       Any = None
    xExtension:                                  Any = None
    xRegenNozzle:                                Any = None
    regenSectionFilmDrivingTemperature:          Any = None
    regenSectionFilmEffectiveness:               Any = None
    regenSectionFilmPropertyCorrection:          Any = None
    regenSectionFilmEntrainmentFlowRatio:        Any = None
    regenSectionFilmWallMixtureRatio:            Any = None
    regenSectionFilmEntrainmentMultiplier:       Any = None
    filmCoolantVelocity:                         Any = None
    filmSurvivalLength:                          Any = None

# The fields a split hands back to a Nozzle. Kept beside the class so that adding a field
# and forgetting to surface it is a one-line fix rather than a silent drop.
regenStationOutputs = (
    'areaRatioArray', 'densityExtension', 'densityRegenSection', 'exitExpansionRatio',
    'extensionNearWallMachNumber', 'extensionNearWallPressure',
    'extensionNearWallRecoveryTemperature', 'extensionNearWallTemperature',
    'extensionNearWallVelocity', 'gammaExtension', 'gammaRegenSection', 'gasConstantExtension',
    'gasConstantRegenSection', 'inletContractionRatio', 'molecularWeightExtension',
    'molecularWeightRegenSection', 'prandtlExtension', 'prandtlNumberRegenSection', 'rExtension',
    'rRegenNozzle', 'regenSectionNearWallMachNumber', 'regenSectionNearWallPressure',
    'regenSectionNearWallRecoveryTemperature', 'regenSectionNearWallTemperature',
    'regenSectionNearWallVelocity', 'reynoldsExtension', 'reynoldsNumberRegenSection',
    'regenSectionFilmDrivingTemperature', 'regenSectionFilmEffectiveness',
    'regenSectionFilmPropertyCorrection', 'regenSectionFilmEntrainmentFlowRatio',
    'regenSectionFilmWallMixtureRatio', 'regenSectionFilmEntrainmentMultiplier',
    'filmCoolantVelocity', 'filmSurvivalLength',
    'specificHeatExtension', 'specificHeatRegenSection', 'thermalCondExtension',
    'thermalConductivityRegenSection', 'viscosityExtension', 'viscosityRegenSection',
    'xExtension', 'xRegenNozzle')

def solveRegenSectionFilm(state):

    """

    Solve the film along the regen section, if one was asked for.

    The film marches forward from its slot with the gas, while the jacket marches backward from
    the coolant inlet, so it cannot be solved inside the jacket loop. It does not need to be: the
    film state depends on the core flow and on its own mass flow, not on the wall temperature, so
    it is solved once here from the station properties and handed on as a driving temperature.

    The one coupling this misses is a wall hot enough to dry the film early. That is second order
    and is recorded as a limitation rather than modeled.

    Parameters:
    -----------
    state : RegenStationState
        Carries the station properties and the film definition. Modified in place.

    Returns:
    --------
    None

    Raises:
    -------
    InvalidInputError
        Through the film solve, if the definition is not usable.

    """

    if state.filmCooling != 'on':
        return

    required = ('filmCoolant', 'filmMassFlow', 'filmInletTemperature',
                'filmInjectionAxialPosition', 'filmSlotHeight')
    absent = [name for name in required
              if getattr(state, name) is None
              or (isinstance(getattr(state, name), float) and np.isnan(getattr(state, name)))]
    if absent:
        raise InvalidInputError(
            message = 'Film cooling is switched on and the definition is incomplete. A film needs '
                      'a coolant, a flow, a temperature, somewhere to enter and a slot to enter '
                      'through.',
            parameterName = ', '.join(absent),
            value = None,
            validRange = 'all of ' + ', '.join(required))

    slotIndex = int(np.argmin(np.abs(state.xRegenNozzle - state.filmInjectionAxialPosition)))

    coolant = filmCoolantState(
        species     = state.filmCoolant,
        temperature = state.filmInletTemperature,
        pressure    = float(state.regenSectionNearWallPressure[slotIndex]),
        massFlow    = state.filmMassFlow,
        slotHeight  = state.filmSlotHeight,
        slotRadius  = float(state.rRegenNozzle[slotIndex]))

    model = state.filmCoolingModel or 'hatchPapell'

    if model == 'hatchPapell':

        # The correlation wants gas properties at the mean of the gas and coolant temperatures.
        # These arrays carry them at the gas temperature, so the static temperature goes in
        # alongside them and the closure applies the property ratio itself. What remains
        # outstanding is that the conductivity here is the equilibrium value; the
        # filmCoolingArrays docstring says what that costs and why it is left.
        film = filmCoolingArrays(
            axialPosition             = state.xRegenNozzle,
            radius                    = state.rRegenNozzle,
            gasVelocity               = state.regenSectionNearWallVelocity,
            gasStaticTemperature      = state.regenSectionNearWallTemperature,
            recoveryTemperature       = state.regenSectionNearWallRecoveryTemperature,
            gasThermalConductivity    = state.thermalConductivityRegenSection,
            gasDensity                = state.densityRegenSection,
            gasViscosity              = state.viscosityRegenSection,
            gasPrandtlNumber          = state.prandtlNumberRegenSection,
            injectionPosition         = state.filmInjectionAxialPosition,
            slotHeight                = state.filmSlotHeight,
            coolantMassFlow           = state.filmMassFlow,
            coolantSpecificHeat       = coolant.specificHeat,
            coolantTemperature        = state.filmInletTemperature,
            coolantThermalDiffusivity = coolant.thermalDiffusivity,
            coolantVelocity           = coolant.velocity)

    elif model == 'sp8124Entrainment':

        # The local total temperature has to be built the way the recovery temperature was, from
        # the same chamber gamma and the same Mach array, or the zero-effectiveness limit of the
        # entrainment model stops reproducing the film-free answer exactly.
        totalTemperature = state.regenSectionNearWallTemperature * (
            1.0 + 0.5 * (state.chamberGamma - 1.0) * state.regenSectionNearWallMachNumber**2)

        # SP-8124 writes the entrainment on the real near-wall mass flux rather than the nominal
        # one-dimensional value, and on a nozzle those differ by tens of percent.
        massFluxRatio = (state.densityRegenSection * state.regenSectionNearWallVelocity) / (
            state.engineMassFlow / (np.pi * state.rRegenNozzle**2))

        film = entrainmentFilmArrays(
            axialPosition           = state.xRegenNozzle,
            radius                  = state.rRegenNozzle,
            gasVelocity             = state.regenSectionNearWallVelocity,
            gasDensity              = state.densityRegenSection,
            totalTemperature        = totalTemperature,
            recoveryTemperature     = state.regenSectionNearWallRecoveryTemperature,
            coreSpecificHeat        = state.specificHeatRegenSection,
            massFluxRatio           = massFluxRatio,
            injectionPosition       = state.filmInjectionAxialPosition,
            slotHeight              = state.filmSlotHeight,
            coreMassFlow            = state.engineMassFlow,
            coolantMassFlow         = state.filmMassFlow,
            coolantDensity          = coolant.density,
            coolantVelocity         = coolant.velocity,
            coolantViscosity        = coolant.viscosity,
            coolantSpecificHeat     = coolant.specificHeat,
            coolantTotalTemperature = state.filmInletTemperature,
            coreMixtureRatio        = state.OFRatio,
            coolantMixtureRatio     = state.filmCoolantMixtureRatio or 0.0,
            injectionMultiplier     = state.filmEntrainmentMultiplier or 3.5)

    else:
        raise InvalidInputError(
            message = 'No film cooling closure by that name. Hatch and Papell is the correlation '
                      'with a stated accuracy from its own source; the SP-8124 entrainment model '
                      'is the one whose empirical multiplier accounts for acceleration and flow '
                      'turning, at the cost of being calibrated rather than validated.',
            parameterName = 'filmCoolingModel',
            value = model,
            validRange = "'hatchPapell' or 'sp8124Entrainment'")

    state.regenSectionFilmEffectiveness         = film.effectiveness
    state.regenSectionFilmPropertyCorrection    = film.propertyCorrection
    state.regenSectionFilmDrivingTemperature    = film.drivingTemperature
    state.regenSectionFilmEntrainmentFlowRatio  = film.entrainmentFlowRatio
    state.regenSectionFilmWallMixtureRatio      = film.wallMixtureRatio
    state.regenSectionFilmEntrainmentMultiplier = film.entrainmentMultiplier
    state.filmCoolantVelocity                   = coolant.velocity
    state.filmSurvivalLength                    = film.survivalLength

def solveRegenStations(state):

    '''

    This method locates the supersonic splitline and separates the regen section from the extension.
    The exhaust flow properties arrays are also split and interpolated accordingly.

    Stations outside the chamber carry no exhaust flow solution, so they are captured when
    indexing but must not be trimmed from the array.

    '''

    regenTruncationType = state.regenTruncationType
    if regenTruncationType == 'temp':
        truncationTemperature = float(state.regenTruncationValue)
    elif regenTruncationType == 'er':
        truncationExpansionRatio = float(state.regenTruncationValue)

    xNozzle = state.xNozzleWall.copy()
    rNozzle = state.rNozzleWall.copy()

    throatIndex = rNozzle.argmin()

    throatArea =  np.pi * rNozzle[throatIndex]**2
    areaRatios = (np.pi * rNozzle**2) / throatArea

    print(f'Truncating Nozzle Regen Section.')

    # Find truncation location
    match regenTruncationType:

        case 'temp':

            # The value is the near-wall recovery temperature, which is what drives the wall and
            # what the jacket is sized against, rather than the static temperature of the gas
            recoveryTemperature = state.nozzleNearWallRecoveryTemperature

            # Recovery temperature falls only a few hundred kelvin from the throat to the exit,
            # so a value taken from the static temperature of the gas cuts nowhere at all
            belowTarget = np.where(recoveryTemperature[throatIndex:] - truncationTemperature < 0)[0]
            if belowTarget.size == 0:
                raise InvalidInputError(
                    message = (f'The near-wall recovery temperature never falls to '
                               f'{truncationTemperature:.1f} K downstream of the throat, where it '
                               f'runs {float(recoveryTemperature[throatIndex]):.1f} K at the throat '
                               f'and {float(recoveryTemperature[-1]):.1f} K at the exit. Recovery '
                               f'temperature stays near the stagnation temperature along a nozzle, '
                               f'so truncate by area ratio to end the jacket further down the bell.'),
                    parameterName = 'regenTruncationValue', value = truncationTemperature,
                    validRange = f'{float(recoveryTemperature[-1]):.1f} to '
                                 f'{float(recoveryTemperature[throatIndex]):.1f} K for this contour')

            truncationIndex = belowTarget[0] + throatIndex

            truncationLocation = interp1d(recoveryTemperature[throatIndex:],xNozzle[throatIndex:])(truncationTemperature)
            truncationRadius   = interp1d(recoveryTemperature[throatIndex:],rNozzle[throatIndex:])(truncationTemperature)

        case 'er':

            truncationIndex = np.where(areaRatios[throatIndex:] - truncationExpansionRatio > 0)[0][0] + throatIndex

            truncationLocation = interp1d(areaRatios[throatIndex:],xNozzle[throatIndex:])(truncationExpansionRatio)
            truncationRadius   = interp1d(areaRatios[throatIndex:],rNozzle[throatIndex:])(truncationExpansionRatio)

    # Separate the regen section and extension
    if regenTruncationType != 'none':

        xRegenNozzle = np.concatenate([state.xNozzleWall[:truncationIndex-1],[truncationLocation]])
        rRegenNozzle = np.concatenate([state.rNozzleWall[:truncationIndex-1],[truncationRadius]])

        xExtension = np.concatenate([[truncationLocation],xNozzle[truncationIndex+1:]])
        rExtension = np.concatenate([[truncationRadius],  rNozzle[truncationIndex+1:]])

        # -- Flow properties -- #

        # MoC outputs
        temperatureNearWallRegen         = state.nozzleNearWallTemperature[:truncationIndex]
        pressureNearWallRegen            = state.nozzleNearWallPressure[:truncationIndex]
        velocityNearWallRegen            = state.nozzleNearWallVelocity[:truncationIndex]
        machNumberNearWallRegen          = state.nozzleNearWallMachNumber[:truncationIndex]
        recoveryTemperatureNearWallRegen = state.nozzleNearWallRecoveryTemperature[:truncationIndex]

        temperatureNearWallExtension         = state.nozzleNearWallTemperature[truncationIndex:]
        pressureNearWallExtension            = state.nozzleNearWallPressure[truncationIndex:]
        velocityNearWallExtension            = state.nozzleNearWallVelocity[truncationIndex:]
        machNumberNearWallExtension          = state.nozzleNearWallMachNumber[truncationIndex:]
        recoveryTemperatureNearWallExtension = state.nozzleNearWallRecoveryTemperature[truncationIndex:]

        # derived values, converging
        contractionRatios = areaRatios[:throatIndex]

        thermalCondConverging, viscosityConverging, prandtlConverging, \
        gammaConverging, gasConstantConverging, specificHeatConverging, molecularWeightConverging \
        = [np.zeros(len(contractionRatios)) for _ in range(7)]

        for i, contractionRatio in enumerate(contractionRatios):

            # Call CEA at each contraction ratio and expansion ratio to build a distribuion of transport properties
            ceaOutput = CEA(fuelName = state.Fuel,
                            oxidizerName = state.Oxidizer, oxidizerInitialTemperature = state.oxidizerInitialTemperature,
                            chamberPressure = state.chamberPressure, contractionRatio = contractionRatio,
                            pressureUnits = 'Pa', OFRatio = state.OFRatio)
            thermalCondConverging[i]     = ceaOutput.ceaResults['combustionChamberThermalConductivity']
            viscosityConverging[i]       = ceaOutput.ceaResults['combustionChamberViscosity']
            prandtlConverging[i]         = ceaOutput.ceaResults['combustionChamberPrandtlNumber']
            gammaConverging[i]           = ceaOutput.ceaResults['combustionChamberGamma']
            gasConstantConverging[i]     = ceaOutput.ceaResults['combustionChamberGasConstant']
            specificHeatConverging[i]    = ceaOutput.ceaResults['combustionChamberHeatCapacity']
            molecularWeightConverging[i] = ceaOutput.ceaResults['combustionChamberMolecularWeight']

        # derived values, diverging
        expansionRatios = areaRatios[throatIndex:truncationIndex]

        extensionExpansionRatios = areaRatios[truncationIndex:]

        thermalCondDiverging, viscosityDiverging, prandtlDiverging, \
        gammaDiverging, gasConstantDiverging, specificHeatDiverging, molecularWeightDiverging \
        = [np.zeros(len(expansionRatios)) for _ in range(7)]

        thermalCondExtension, viscosityExtension, prandtlExtension, \
        gammaExtension, gasConstantExtension, specificHeatExtension, molecularWeightExtension \
        = [np.zeros(len(extensionExpansionRatios)) for _ in range(7)]

        for i, expansionRatio in enumerate(expansionRatios):

            # Call CEA at each contraction ratio and expansion ratio to build a distribuion of transport properties
            ceaOutput = CEA(fuelName = state.Fuel,
                            oxidizerName = state.Oxidizer, oxidizerInitialTemperature = state.oxidizerInitialTemperature,
                            chamberPressure = state.chamberPressure, expansionRatio = expansionRatio,
                            pressureUnits = 'Pa', OFRatio = state.OFRatio)
            thermalCondDiverging[i]     = ceaOutput.ceaResults['exitThermalConductivity']
            viscosityDiverging[i]       = ceaOutput.ceaResults['exitViscosity']
            prandtlDiverging[i]         = ceaOutput.ceaResults['exitPrandtlNumber']
            gammaDiverging[i]           = ceaOutput.ceaResults['exitGamma']
            gasConstantDiverging[i]     = ceaOutput.ceaResults['exitGasConstant']
            specificHeatDiverging[i]    = ceaOutput.ceaResults['exitHeatCapacity']
            molecularWeightDiverging[i] = ceaOutput.ceaResults['exitMolecularWeight']

        for i, extensionExpansionRatio in enumerate(extensionExpansionRatios):

            # Call CEA at each contraction ratio and expansion ratio to build a distribuion of transport properties
            ceaOutput = CEA(fuelName = state.Fuel,
                            oxidizerName = state.Oxidizer, oxidizerInitialTemperature = state.oxidizerInitialTemperature,
                            chamberPressure = state.chamberPressure, expansionRatio = extensionExpansionRatio,
                            pressureUnits = 'Pa', OFRatio = state.OFRatio)
            thermalCondExtension[i]     = ceaOutput.ceaResults['exitThermalConductivity']
            viscosityExtension[i]       = ceaOutput.ceaResults['exitViscosity']
            prandtlExtension[i]         = ceaOutput.ceaResults['exitPrandtlNumber']
            gammaExtension[i]           = ceaOutput.ceaResults['exitGamma']
            gasConstantExtension[i]     = ceaOutput.ceaResults['exitGasConstant']
            specificHeatExtension[i]    = ceaOutput.ceaResults['exitHeatCapacity']
            molecularWeightExtension[i] = ceaOutput.ceaResults['exitMolecularWeight']

        thermalCondRegen     = np.concatenate([thermalCondConverging, thermalCondDiverging])
        viscosityRegen       = np.concatenate([viscosityConverging, viscosityDiverging])
        prandtlRegen         = np.concatenate([prandtlConverging, prandtlDiverging])
        gammaRegen           = np.concatenate([gammaConverging, gammaDiverging])
        gasConstantRegen     = np.concatenate([gasConstantConverging, gasConstantDiverging])
        specificHeatRegen    = np.concatenate([specificHeatConverging, specificHeatDiverging])
        molecularWeightRegen = np.concatenate([molecularWeightConverging, molecularWeightDiverging])

        densityRegen  = pressureNearWallRegen / (gasConstantRegen * temperatureNearWallRegen)
        reynoldsRegen = densityRegen * velocityNearWallRegen * 2 * rNozzle[:truncationIndex] / viscosityRegen

        densityExtension  = pressureNearWallExtension / (gasConstantExtension * temperatureNearWallExtension)
        reynoldsExtension = densityExtension * velocityNearWallExtension * 2 * rNozzle[truncationIndex:] / viscosityExtension

        # arcSpline and interpolate

        xRegenRough = xRegenNozzle.copy()
        xRegenNozzle, rRegenNozzle = arcSpline(xRegenNozzle,rRegenNozzle,newNumPoints=state.numCrossSections)

        temperatureNearWallRegen         = chunkInterpolate(xRegenRough, temperatureNearWallRegen, xRegenNozzle)
        pressureNearWallRegen            = chunkInterpolate(xRegenRough, pressureNearWallRegen, xRegenNozzle)
        velocityNearWallRegen            = chunkInterpolate(xRegenRough, velocityNearWallRegen, xRegenNozzle)
        machNumberNearWallRegen          = chunkInterpolate(xRegenRough, machNumberNearWallRegen, xRegenNozzle)
        recoveryTemperatureNearWallRegen = chunkInterpolate(xRegenRough, recoveryTemperatureNearWallRegen, xRegenNozzle)
        thermalCondRegen                 = chunkInterpolate(xRegenRough, thermalCondRegen, xRegenNozzle)
        viscosityRegen                   = chunkInterpolate(xRegenRough, viscosityRegen, xRegenNozzle)
        prandtlRegen                     = chunkInterpolate(xRegenRough, prandtlRegen, xRegenNozzle)
        gammaRegen                       = chunkInterpolate(xRegenRough, gammaRegen, xRegenNozzle)
        gasConstantRegen                 = chunkInterpolate(xRegenRough, gasConstantRegen, xRegenNozzle)
        specificHeatRegen                = chunkInterpolate(xRegenRough, specificHeatRegen, xRegenNozzle)
        densityRegen                     = chunkInterpolate(xRegenRough, densityRegen, xRegenNozzle)
        reynoldsRegen                    = chunkInterpolate(xRegenRough, reynoldsRegen, xRegenNozzle)
        molecularWeightRegen             = chunkInterpolate(xRegenRough, molecularWeightRegen, xRegenNozzle)

        xExtensionRough = xExtension
        xExtension, rExtension = arcSpline(xExtension,rExtension,newNumPoints=state.numContourPoints)

        temperatureNearWallExtension         = interp1d(xExtensionRough, temperatureNearWallExtension,fill_value='extrapolate')(xExtension)
        pressureNearWallExtension            = interp1d(xExtensionRough, pressureNearWallExtension,fill_value='extrapolate')(xExtension)
        velocityNearWallExtension            = interp1d(xExtensionRough, velocityNearWallExtension,fill_value='extrapolate')(xExtension)
        machNumberNearWallExtension          = interp1d(xExtensionRough, machNumberNearWallExtension,fill_value='extrapolate')(xExtension)
        recoveryTemperatureNearWallExtension = interp1d(xExtensionRough, recoveryTemperatureNearWallExtension,fill_value='extrapolate')(xExtension)
        thermalCondExtension                 = interp1d(xExtensionRough, thermalCondExtension,fill_value='extrapolate')(xExtension)
        viscosityExtension                   = interp1d(xExtensionRough, viscosityExtension,fill_value='extrapolate')(xExtension)
        prandtlExtension                     = interp1d(xExtensionRough, prandtlExtension,fill_value='extrapolate')(xExtension)
        gammaExtension                       = interp1d(xExtensionRough, gammaExtension,fill_value='extrapolate')(xExtension)
        gasConstantExtension                 = interp1d(xExtensionRough, gasConstantExtension,fill_value='extrapolate')(xExtension)
        specificHeatExtension                = interp1d(xExtensionRough, specificHeatExtension,fill_value='extrapolate')(xExtension)
        densityExtension                     = interp1d(xExtensionRough, densityExtension,fill_value='extrapolate')(xExtension)
        reynoldsExtension                    = interp1d(xExtensionRough, reynoldsExtension,fill_value='extrapolate')(xExtension)
        molecularWeightExtension             = interp1d(xExtensionRough, molecularWeightExtension,fill_value='extrapolate')(xExtension)

    elif regenTruncationType == 'none' and divergingSectionFamily(state.divergingSectionType) != 'conical':

        xRegenNozzle = state.xNozzleWall.copy()
        rRegenNozzle = state.rNozzleWall.copy()

        xExtension = []
        rExtension = []

        # -- Flow properties -- #

        # MoC outputs
        temperatureNearWallRegen         = state.nozzleNearWallTemperature.copy()
        pressureNearWallRegen            = state.nozzleNearWallPressure.copy()
        velocityNearWallRegen            = state.nozzleNearWallVelocity.copy()
        machNumberNearWallRegen          = state.nozzleNearWallMachNumber.copy()
        recoveryTemperatureNearWallRegen = state.nozzleNearWallRecoveryTemperature.copy()

        temperatureNearWallExtension         = []
        pressureNearWallExtension            = []
        velocityNearWallExtension            = []
        machNumberNearWallExtension          = []
        recoveryTemperatureNearWallExtension = []

        # derived values, converging
        contractionRatios = areaRatios[:throatIndex]

        thermalCondConverging, viscosityConverging, prandtlConverging, \
        gammaConverging, gasConstantConverging, specificHeatConverging, molecularWeightConverging \
        = [np.zeros(len(contractionRatios)) for _ in range(7)]

        for i, contractionRatio in enumerate(contractionRatios):

            # Call CEA at each contraction ratio and expansion ratio to build a distribuion of transport properties
            ceaOutput = CEA(fuelName = state.Fuel,
                            oxidizerName = state.Oxidizer, oxidizerInitialTemperature = state.oxidizerInitialTemperature,
                            chamberPressure = state.chamberPressure, contractionRatio = contractionRatio,
                            pressureUnits = 'Pa', OFRatio = state.OFRatio)

            neededKeys = ['combustionChamberThermalConductivity',
                          'combustionChamberViscosity',
                          'combustionChamberPrandtlNumber',
                          'combustionChamberGamma',
                          'combustionChamberGasConstant',
                          'combustionChamberHeatCapacity',
                          'combustionChamberMolecularWeight']

            for k in neededKeys:
                if np.isnan(ceaOutput.ceaResults[k]):
                    raise ThermalConstraintError(
                        message=f"CEA calculation failed for converging section properties at contraction ratio {contractionRatio}",
                        context=createErrorContext(
                            fuelName=state.Fuel,
                            oxidizerName=state.Oxidizer,
                            oxidizerInitialTemperature=state.oxidizerInitialTemperature,
                            chamberPressure=state.chamberPressure,
                            contractionRatio=contractionRatio,
                            pressureUnits='Pa',
                            OFRatio=state.OFRatio
                        ),
                        thermalProperty=k,
                        value=ceaOutput.ceaResults[k]
                    )

            thermalCondConverging[i]     = ceaOutput.ceaResults['combustionChamberThermalConductivity']
            viscosityConverging[i]       = ceaOutput.ceaResults['combustionChamberViscosity']
            prandtlConverging[i]         = ceaOutput.ceaResults['combustionChamberPrandtlNumber']
            gammaConverging[i]           = ceaOutput.ceaResults['combustionChamberGamma']
            gasConstantConverging[i]     = ceaOutput.ceaResults['combustionChamberGasConstant']
            specificHeatConverging[i]    = ceaOutput.ceaResults['combustionChamberHeatCapacity']
            molecularWeightConverging[i] = ceaOutput.ceaResults['combustionChamberMolecularWeight']

        # derived values, diverging
        expansionRatios = areaRatios[throatIndex:]

        thermalCondDiverging, viscosityDiverging, prandtlDiverging, \
        gammaDiverging, gasConstantDiverging, specificHeatDiverging, molecularWeightDiverging \
        = [np.zeros(len(expansionRatios)) for _ in range(7)]

        for i, expansionRatio in enumerate(expansionRatios):

            # Call CEA at each contraction ratio and expansion ratio to build a distribuion of transport properties
            ceaOutput = CEA(fuelName = state.Fuel,
                            oxidizerName = state.Oxidizer, oxidizerInitialTemperature = state.oxidizerInitialTemperature,
                            chamberPressure = state.chamberPressure, expansionRatio = expansionRatio,
                            pressureUnits = 'Pa', OFRatio = state.OFRatio)

            neededKeys = ['exitThermalConductivity',
                          'exitViscosity',
                          'exitPrandtlNumber',
                          'exitGamma',
                          'exitGasConstant',
                          'exitHeatCapacity',
                          'exitMolecularWeight']

            for k in neededKeys:
                if np.isnan(ceaOutput.ceaResults[k]):
                    raise ThermalConstraintError(
                        message=f"CEA calculation failed for diverging section properties at expansion ratio {expansionRatio}",
                        context=createErrorContext(
                            fuelName=state.Fuel,
                            oxidizerName=state.Oxidizer,
                            oxidizerInitialTemperature=state.oxidizerInitialTemperature,
                            chamberPressure=state.chamberPressure,
                            expansionRatio=expansionRatio,
                            pressureUnits='Pa',
                            OFRatio=state.OFRatio
                        ),
                        thermalProperty=k,
                        value=ceaOutput.ceaResults[k]
                    )

            # if at throat use throat quantities
            if expansionRatio == 1.0:
                thermalCondDiverging[i]     = ceaOutput.ceaResults['throatThermalConductivity']
                viscosityDiverging[i]       = ceaOutput.ceaResults['throatViscosity']
                prandtlDiverging[i]         = ceaOutput.ceaResults['throatPrandtlNumber']
                gammaDiverging[i]           = ceaOutput.ceaResults['throatGamma']
                gasConstantDiverging[i]     = ceaOutput.ceaResults['throatGasConstant']
                specificHeatDiverging[i]    = ceaOutput.ceaResults['throatHeatCapacity']
                molecularWeightDiverging[i] = ceaOutput.ceaResults['throatMolecularWeight']
            else:
                thermalCondDiverging[i]     = ceaOutput.ceaResults['exitThermalConductivity']
                viscosityDiverging[i]       = ceaOutput.ceaResults['exitViscosity']
                prandtlDiverging[i]         = ceaOutput.ceaResults['exitPrandtlNumber']
                gammaDiverging[i]           = ceaOutput.ceaResults['exitGamma']
                gasConstantDiverging[i]     = ceaOutput.ceaResults['exitGasConstant']
                specificHeatDiverging[i]    = ceaOutput.ceaResults['exitHeatCapacity']
                molecularWeightDiverging[i] = ceaOutput.ceaResults['exitMolecularWeight']

        thermalCondRegen     = np.concatenate([thermalCondConverging, thermalCondDiverging])
        viscosityRegen       = np.concatenate([viscosityConverging, viscosityDiverging])
        prandtlRegen         = np.concatenate([prandtlConverging, prandtlDiverging])
        gammaRegen           = np.concatenate([gammaConverging, gammaDiverging])
        gasConstantRegen     = np.concatenate([gasConstantConverging, gasConstantDiverging])
        specificHeatRegen    = np.concatenate([specificHeatConverging, specificHeatDiverging])
        molecularWeightRegen = np.concatenate([molecularWeightConverging, molecularWeightDiverging])

        densityRegen  = pressureNearWallRegen / (gasConstantRegen * temperatureNearWallRegen)
        reynoldsRegen = densityRegen * velocityNearWallRegen * 2 * rNozzle / viscosityRegen

        # arcSpline and interpolate

        xRegenRough = xRegenNozzle.copy()
        xRegenNozzle, rRegenNozzle = arcSpline(xRegenNozzle,rRegenNozzle,newNumPoints=state.numCrossSections)

        temperatureNearWallRegen         = chunkInterpolate(xRegenRough, temperatureNearWallRegen, xRegenNozzle)
        pressureNearWallRegen            = chunkInterpolate(xRegenRough, pressureNearWallRegen, xRegenNozzle)
        velocityNearWallRegen            = chunkInterpolate(xRegenRough, velocityNearWallRegen, xRegenNozzle)
        machNumberNearWallRegen          = chunkInterpolate(xRegenRough, machNumberNearWallRegen, xRegenNozzle)
        recoveryTemperatureNearWallRegen = chunkInterpolate(xRegenRough, recoveryTemperatureNearWallRegen, xRegenNozzle)
        thermalCondRegen                 = chunkInterpolate(xRegenRough, thermalCondRegen, xRegenNozzle)
        viscosityRegen                   = chunkInterpolate(xRegenRough, viscosityRegen, xRegenNozzle)
        prandtlRegen                     = chunkInterpolate(xRegenRough, prandtlRegen, xRegenNozzle)
        gammaRegen                       = chunkInterpolate(xRegenRough, gammaRegen, xRegenNozzle)
        gasConstantRegen                 = chunkInterpolate(xRegenRough, gasConstantRegen, xRegenNozzle)
        specificHeatRegen                = chunkInterpolate(xRegenRough, specificHeatRegen, xRegenNozzle)
        densityRegen                     = chunkInterpolate(xRegenRough, densityRegen, xRegenNozzle)
        reynoldsRegen                    = chunkInterpolate(xRegenRough, reynoldsRegen, xRegenNozzle)
        molecularWeightRegen             = chunkInterpolate(xRegenRough, molecularWeightRegen, xRegenNozzle)

    # Assign properties to object

    state.xRegenNozzle                            = xRegenNozzle
    state.rRegenNozzle                            = rRegenNozzle

    state.exitExpansionRatio                      = areaRatios[-1]
    state.inletContractionRatio                   = areaRatios[0]
    state.areaRatioArray                          = areaRatios

    state.regenSectionNearWallTemperature         = temperatureNearWallRegen
    state.regenSectionNearWallPressure            = pressureNearWallRegen
    state.regenSectionNearWallVelocity            = velocityNearWallRegen
    state.regenSectionNearWallMachNumber          = machNumberNearWallRegen
    state.regenSectionNearWallRecoveryTemperature = recoveryTemperatureNearWallRegen

    state.thermalConductivityRegenSection         = thermalCondRegen
    state.viscosityRegenSection                   = viscosityRegen
    state.prandtlNumberRegenSection               = prandtlRegen
    state.gammaRegenSection                       = gammaRegen
    state.gasConstantRegenSection                 = gasConstantRegen
    state.specificHeatRegenSection                = specificHeatRegen
    state.densityRegenSection                     = densityRegen
    state.reynoldsNumberRegenSection              = reynoldsRegen
    state.molecularWeightRegenSection             = molecularWeightRegen

    # The film is solved here rather than in the jacket because it marches the other way:
    # forward from its slot with the gas, while the jacket marches back from the coolant
    # inlet. Everything it needs is in the station properties just assigned.
    solveRegenSectionFilm(state)

    if state.regenTruncationType != 'none':

        state.xExtension                              = xExtension
        state.rExtension                              = rExtension

        state.extensionNearWallTemperature                = temperatureNearWallExtension
        state.extensionNearWallPressure                   = pressureNearWallExtension
        state.extensionNearWallVelocity                   = velocityNearWallExtension
        state.extensionNearWallMachNumber                 = machNumberNearWallExtension
        state.extensionNearWallRecoveryTemperature        = recoveryTemperatureNearWallExtension

        state.thermalCondExtension                    = thermalCondExtension
        state.viscosityExtension                      = viscosityExtension
        state.prandtlExtension                        = prandtlExtension
        state.gammaExtension                          = gammaExtension
        state.gasConstantExtension                    = gasConstantExtension
        state.specificHeatExtension                   = specificHeatExtension
        state.densityExtension                        = densityExtension
        state.reynoldsExtension                       = reynoldsExtension
        state.molecularWeightExtension                = molecularWeightExtension

    if state.plotsEnabled == 'on':

        # The same styled renderer the feature showcase draws its documentation figures with,
        # so the PNGs written here and the ones in featureShowcase/ cannot drift apart.
        def showAndExport(figure, filename: str) -> None:

            if figure is None:
                return
            showFigure(figure)
            if state.export == 'on':
                figure.savefig(state.dataFolder + '\\' + filename, dpi = 160,
                               bbox_inches = 'tight')

        showAndExport(drawContourFigure(state), 'contourSegmentsVisualization.png')
        showAndExport(drawFieldFigure(state, 'mach'), 'machContours.png')
        showAndExport(drawFieldFigure(state, 'pressure'), 'pressureContours.png')
        showAndExport(drawFieldFigure(state, 'temperature'), 'temperatureContours.png')
        showAndExport(drawNearWallFigure(state), 'nearWallProperties.png')

    return state
