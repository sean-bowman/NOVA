# -- NOVA: Regen Section Split and Station Properties -- #

'''

Deciding how far down the nozzle the cooling jacket runs, and what the exhaust is doing there.

A regeneratively cooled nozzle is not cooled all the way to the exit. Past some station the wall
is cool enough to survive uncooled, and carrying the jacket further costs mass and pressure drop
for nothing. This module makes that cut and hands back two sections: the regen section the jacket
is built on, and the extension beyond it.

Where to cut is set by `truncationMethod`:

    none        No cut. The jacket runs the whole contour.
    temp<K>     Cut where the near-wall recovery temperature falls to the given value.
    er<ratio>   Cut at a given area ratio.

Both sections then get a full set of exhaust properties at every station. Those come from the
thermochemistry rather than from the flowfield: CEA is called at each station's area ratio, and
returns the gas composition, transport properties and near-wall state there.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**The station properties are CEA's, and are as good as CEA.** The thermochemistry is validated in
`tests/testCeaInterface.py` against CEARun for the worked LOX/LH2 case. What is not validated is
the assumption that a one-dimensional station property describes the gas at the wall.

**That assumption is the largest disclosed approximation in the cooling model.** The near-wall
Mach number the method of characteristics returns departs from the one-dimensional value at the
same area ratio by up to 42 per cent near the throat. Every gas-side transport property the
thermal model reads comes from here, one-dimensionally, while the geometry it is applied to came
from the characteristics solve. The two are inconsistent with each other, and the throat is where
the heat flux is highest.

Closing that gap means sampling the flowfield rather than a one-dimensional station, which is a
change to what is modelled rather than to how it is computed.

**The split itself is arithmetic**: an interpolation onto a temperature or an area ratio, and the
tests hold it to the station it names.

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
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d

from .utils import (arcSpline, chunkInterpolate, plotLine, ThermalConstraintError,
                    createErrorContext, InvalidInputError)
from .filmCooling import filmCoolantState, filmCoolingArrays
from .ceaInterface import CEA

@dataclass
class RegenStationState:

    '''

    Everything the split reads, and the two sections it produces.

    Every field starts as None. One still None afterwards is a branch that was not reached, which
    is worth keeping rather than hiding behind an empty array.

    '''

    # -- The contour and the propellants the stations are sampled from -- #
    Fuel:                                        Any = None
    filmCooling:                                 Any = None
    filmCoolant:                                 Any = None
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
    truncationMethod:                            Any = None
    visualizeContour:                            Any = None
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
    and is recorded as a limitation rather than modelled.

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

    # The correlation wants gas properties at the mean of the gas and coolant temperatures. What
    # NOVA carries is the gas temperature, which overstates the conductivity, overstates the
    # correlating group and so understates the effectiveness. That is the safe direction, and the
    # size of it has not been quantified.
    film = filmCoolingArrays(
        axialPosition             = state.xRegenNozzle,
        radius                    = state.rRegenNozzle,
        gasVelocity               = state.regenSectionNearWallVelocity,
        recoveryTemperature       = state.regenSectionNearWallRecoveryTemperature,
        meanThermalConductivity   = state.thermalConductivityRegenSection,
        meanDensity               = state.densityRegenSection,
        meanViscosity             = state.viscosityRegenSection,
        meanPrandtlNumber         = state.prandtlNumberRegenSection,
        injectionPosition         = state.filmInjectionAxialPosition,
        slotHeight                = state.filmSlotHeight,
        coolantMassFlow           = state.filmMassFlow,
        coolantSpecificHeat       = coolant.specificHeat,
        coolantTemperature        = state.filmInletTemperature,
        coolantThermalDiffusivity = coolant.thermalDiffusivity,
        coolantVelocity           = coolant.velocity)

    state.regenSectionFilmEffectiveness      = film.effectiveness
    state.regenSectionFilmDrivingTemperature = film.drivingTemperature
    state.filmCoolantVelocity                = coolant.velocity
    state.filmSurvivalLength                 = film.survivalLength

def solveRegenStations(state):

    '''

    This method locates the supersonic splitline and separates the regen section from the extension.
    The exhaust flow properties arrays are also split and interpolated accordingly.

    Stations outside the chamber carry no exhaust flow solution, so they are captured when
    indexing but must not be trimmed from the array.

    '''

    # Type is either 'temp' , 'er' , or 'none' so we can check the first letter
    firstLetter = state.truncationMethod[0]
    if firstLetter.lower() == 't':
        truncationMethod = 'temp'
        truncationTemperature = float(state.truncationMethod[5:])
    elif firstLetter.lower() == 'e':
        truncationMethod = 'er'
        truncationExpansionRatio = float(state.truncationMethod[3:])
    elif firstLetter.lower() == 'n':
        truncationMethod = 'none'

    xNozzle = state.xNozzleWall.copy()
    rNozzle = state.rNozzleWall.copy()

    throatIndex = rNozzle.argmin()

    throatArea =  np.pi * rNozzle[throatIndex]**2
    areaRatios = (np.pi * rNozzle**2) / throatArea

    print(f'Truncating Nozzle Regen Section.')

    # Find truncation location
    match truncationMethod:

        case 'temp':

            truncationIndex = np.where(state.nozzleNearWallTemperature[throatIndex:] - truncationTemperature < 0)[0][0] + throatIndex

            truncationLocation = interp1d(state.nozzleNearWallTemperature[throatIndex:],xNozzle[throatIndex:])(truncationTemperature)
            truncationRadius   = interp1d(state.nozzleNearWallTemperature[throatIndex:],rNozzle[throatIndex:])(truncationTemperature)

        case 'er':

            truncationIndex = np.where(areaRatios[throatIndex:] - truncationExpansionRatio > 0)[0][0] + throatIndex

            truncationLocation = interp1d(areaRatios[throatIndex:],xNozzle[throatIndex:])(truncationExpansionRatio)
            truncationRadius   = interp1d(areaRatios[throatIndex:],rNozzle[throatIndex:])(truncationExpansionRatio)

    # Separate the regen section and extension
    if truncationMethod != 'none':

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

    elif truncationMethod == 'none' and state.divergingSectionType != 'Conical':

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

    if state.divergingSectionType.lower != 'conical':

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

    if state.truncationMethod != 'none':

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

    if state.visualizeContour == 'on':

        plotLine(xRegenNozzle, rRegenNozzle, markerStyle = '*', lineStyle = '',
                 xLabel = 'Nozzle Axis [m]', yLabel = 'Nozzle Radius [m]',
                 title = 'Truncated Ideal Nozzle Contour',
                 label = 'Regen Nozzle Portion')
        plt.plot(xExtension, rExtension, '*r', label = 'Nozzle Extension')
        plt.legend()
        plt.gca().set_aspect('equal')

        if state.export == 'on':

            # Enlarge for the save at the aspect the figure was drawn at; resizing to a
            # portrait canvas is what used to leave the content floating in white space.
            figure = plt.gcf()
            figure.set_size_inches(16, 10)
            figure.tight_layout()

            # Save the final heat transfer figure to the data folder
            plt.savefig(state.dataFolder + '\\contourSegmentsVizualization.png', bbox_inches = 'tight')

        # Mach Contours
        fig = plt.figure(figsize=(12, 8))

        plt.plot(state.xNozzleWall, state.rNozzleWall, 'w', label = 'Nozzle Contour')
        plt.plot(state.xNozzleWall, -state.rNozzleWall, 'w')

        maskedX, maskedR, maskedMach = [], [], []
        for i in range(3):
            maskedX.append(np.ma.masked_where(np.isnan(state.allXPoints[i]), state.allXPoints[i]))
            maskedR.append(np.ma.masked_where(np.isnan(state.allRPoints[i]), state.allRPoints[i]))
            maskedMach.append(np.ma.masked_where(np.isnan(state.allMachNumbers[i]), state.allMachNumbers[i]))
        levels = np.arange(0.5, 1 + state.idealMachNumber, 0.1)
        for i in range(3):
            contour = plt.contourf(maskedX[i]*state.nozzleScalingFactor,
                         maskedR[i]*state.nozzleScalingFactor,
                         maskedMach[i],
                         levels = levels)
            plt.contourf(maskedX[i]*state.nozzleScalingFactor,
                         -maskedR[i]*state.nozzleScalingFactor,
                         maskedMach[i],
                         levels = levels)
        plt.colorbar(contour, label = 'Mach Number', orientation = 'horizontal', pad = 0.10, fraction = 0.05, aspect = 60)

        plt.gca().set_aspect('equal')
        plt.gca().set_title('Mach Contours')
        plt.gca().set_xlabel('Nozzle Axis [m]')
        plt.gca().set_ylabel('Nozzle Radius [m]')
        plt.show(block = False)

        if state.export == 'on':

            # Enlarge for the save at the aspect the figure was drawn at; resizing to a
            # portrait canvas is what used to leave the content floating in white space.
            figure = plt.gcf()
            figure.set_size_inches(16, 10)
            figure.tight_layout()

            # Save the final heat transfer figure to the data folder
            plt.savefig(state.dataFolder + '\\machContours.png', bbox_inches = 'tight')

        # Pressure Field
        fig = plt.figure(figsize=(12, 8))

        plt.plot(state.xNozzleWall, state.rNozzleWall, 'w', label = 'Nozzle Contour')
        plt.plot(state.xNozzleWall, -state.rNozzleWall, 'w')

        maskedPressure = []
        for i in range(3):
            maskedPressure.append(np.ma.masked_where(np.isnan(state.allPressures[i]), state.allPressures[i]))
        levels = np.arange(state.targetExitPressure, maskedPressure[0].max(), 1e4)
        cmap = plt.colormaps['coolwarm'].with_extremes(under = 'cyan', over = 'magenta')
        for i in range(3):
            contour = plt.contourf(maskedX[i]*state.nozzleScalingFactor,
                         maskedR[i]*state.nozzleScalingFactor,
                         maskedPressure[i],
                         levels = levels,
                         cmap = cmap,
                         extend = 'min')
            plt.contourf(maskedX[i]*state.nozzleScalingFactor,
                         -maskedR[i]*state.nozzleScalingFactor,
                         maskedPressure[i],
                         levels = levels,
                         cmap = cmap,
                         extend = 'min')
        plt.colorbar(contour, label = 'Pressure Field [Pa]', orientation = 'horizontal', pad = 0.10, fraction = 0.05, aspect = 60)

        plt.gca().set_aspect('equal')
        plt.gca().set_title('Pressure Contours')
        plt.gca().set_xlabel('Nozzle Axis [m]')
        plt.gca().set_ylabel('Nozzle Radius [m]')
        plt.show(block = False)

        if state.export == 'on':

            # Enlarge for the save at the aspect the figure was drawn at; resizing to a
            # portrait canvas is what used to leave the content floating in white space.
            figure = plt.gcf()
            figure.set_size_inches(16, 10)
            figure.tight_layout()

            # Save the final heat transfer figure to the data folder
            plt.savefig(state.dataFolder + '\\pressureContours.png', bbox_inches = 'tight')

        # Temperature Field
        fig = plt.figure(figsize=(12, 8))

        plt.plot(state.xNozzleWall, state.rNozzleWall, 'w', label = 'Nozzle Contour')
        plt.plot(state.xNozzleWall, -state.rNozzleWall, 'w')

        maskedTemperature = []
        for i in range(3):
            maskedTemperature.append(np.ma.masked_where(np.isnan(state.allTemperatures[i]), state.allTemperatures[i]))
        levels = np.arange(1000, maskedTemperature[0].max(), 100)
        cmap = plt.colormaps['plasma']
        for i in range(3):
            contour = plt.contourf(maskedX[i]*state.nozzleScalingFactor,
                         maskedR[i]*state.nozzleScalingFactor,
                         maskedTemperature[i],
                         levels = levels,
                         cmap = cmap)
            plt.contourf(maskedX[i]*state.nozzleScalingFactor,
                         -maskedR[i]*state.nozzleScalingFactor,
                         maskedTemperature[i],
                         levels = levels,
                         cmap = cmap)
        plt.colorbar(contour, label = 'Temperature Field [K]', orientation = 'horizontal', pad = 0.10, fraction = 0.05, aspect = 60)

        plt.gca().set_aspect('equal')
        plt.gca().set_title('Temperature Contours')
        plt.gca().set_xlabel('Nozzle Axis [m]')
        plt.gca().set_ylabel('Nozzle Radius [m]')
        plt.show(block = False)

        if state.export == 'on':

            # Enlarge for the save at the aspect the figure was drawn at; resizing to a
            # portrait canvas is what used to leave the content floating in white space.
            figure = plt.gcf()
            figure.set_size_inches(16, 10)
            figure.tight_layout()

            # Save the final heat transfer figure to the data folder
            plt.savefig(state.dataFolder + '\\temperatureContours.png', bbox_inches = 'tight')

        # Nozzle Full Output Plot
        fig = plt.figure(figsize=(12, 8))

        gs = fig.add_gridspec(2, 2)

        ax1 = fig.add_subplot(gs[0, 0])
        ax1.plot(state.xNozzleWall, state.rNozzleWall, 'w', label = 'Nozzle Contour')
        ax1.plot(     xNozzle    , state.nozzleNearWallVelocity, label = 'Velocity')
        ax1.set_title('Near-Wall Exhaust Velocity')
        ax1.set_xlabel('Nozzle Axis [m]')
        ax1.set_ylabel('Velocity [m/s]')
        ax1.grid(which = 'both')

        ax2 = fig.add_subplot(gs[0, 1])
        ax2.plot(     xNozzle    , state.nozzleNearWallMachNumber, label = 'Mach Number')
        ax2.set_title('Near-Wall Exhaust Mach Number')
        ax2.set_xlabel('Nozzle Axis [m]')
        ax2.set_ylabel('Mach Number [-]')
        ax2.grid(which = 'both')

        ax3 = fig.add_subplot(gs[1, 0])
        ax3.plot(     xNozzle    , state.nozzleNearWallTemperature, label = 'Static Temperature')
        ax3.set_title('Near-Wall Exhaust Static Temperature')
        ax3.set_xlabel('Nozzle Axis [m]')
        ax3.set_ylabel('Temperature [K]')
        ax3.grid(which = 'both')

        ax4 = fig.add_subplot(gs[1, 1])
        ax4.plot(     xNozzle    , state.nozzleNearWallPressure, label = 'Static Pressure')
        ax4.set_title('Near-Wall Exhaust Static Pressure')
        ax4.set_xlabel('Nozzle Axis [m]')
        ax4.set_ylabel('Pressure [Pa]')
        ax4.grid(which = 'both')

        plt.tight_layout()
        plt.show(block = False)

        if state.export == 'on':

            # Enlarge for the save at the aspect the figure was drawn at; resizing to a
            # portrait canvas is what used to leave the content floating in white space.
            figure = plt.gcf()
            figure.set_size_inches(16, 10)
            figure.tight_layout()

            # Save the final heat transfer figure to the data folder
            plt.savefig(state.dataFolder + '\\nearWallProperties.png', bbox_inches = 'tight')

    return state
