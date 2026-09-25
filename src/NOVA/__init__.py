
# -- NOVA: Nozzle Optimization for Variable Applications -- #

'''

Rocket nozzle design suite.

The package is a facade over a set of single-purpose modules. `Nozzle` carries a configuration
and delegates each stage of a run to the respective module.

A minimal run reads a configuration and generates everything from it:

    from NOVA import Nozzle

    nozzle = Nozzle()
    nozzle.generateNozzle(configPath = 'myNozzle.json')

The individual solvers are usable on their own, without a `Nozzle` object, and the physics
modules are importable directly as well:

    from NOVA import machFromAreaRatio, prandtlMeyerAngle, wallMaterialCurves
    from NOVA import gasDynamics, materials

Names re-exported here are the supported surface. Everything else is reachable through its own
module, which is where the implementation detail is documented.

----------------------------------------------------------------------
                        Units
----------------------------------------------------------------------

Every quantity crossing a public method boundary is SI: meters, kilograms, seconds, kelvin,
pascals, and degrees for angles. Conversions belong at the edge, in `units`, not in the
solvers.

'''

__version__ = '0.1.0'

# Import order runs from the modules with no siblings of their own outward to the facade, so a
# circular import should surface here

from . import (ablative, ceaInterface, chamber, channelGeometry, channelSizing,
               characteristics, config, contour, contourKernel, errors, exports, figures,
               filmCooling, fluidProperties, gasDynamics, gasSideHeatTransfer, geometryTools,
               materials, nozzleVolutes, plume, radiativeCooling,
               regenChannels, regenStations, regenThermal, units, validation)

# -- Gas dynamics -- #

from .gasDynamics import (areaMachRelation, conicalLength, divergenceLossFactor, isentropicValues,
                          machAngle, machFromAreaRatio, machFromPrandtlMeyerAngle,
                          machFromPressureRatio, prandtlMeyerAngle, radiusMachRelation,
                          stagnationRatio, staticPressureRatio, staticTemperatureRatio)

# -- Materials -- #

from .materials import (ablativeResponseData, ablativeResponseProvenance,
                        availableAblativeMaterials, availableMaterialClasses,
                        availableMaterials, availableWallMaterials, materialProfile,
                        materialProperties, materialProperty, materialPropertyProvenance,
                        maxUseTemperature, propertyIsMeasured, propertyProvenance,
                        resolveWallMaterialName, roughnessTable, sampleWallMaterial,
                        surfaceEmissivity, wallMaterialCurves)

# -- Ablative material response -- #

from .ablative import (AblationEnvironment, AblativeLinerResult, BPrimeTable,
                       CharringMaterial, MaterialResponseResult, ablativeNozzleLiner,
                       blowingCorrection, diffusionLimitedCharBPrime,
                       elementMassFractionsFromMoles, propellantElementMassFractions,
                       solveMaterialResponse)

# -- Film cooling -- #

from .filmCooling import (FilmCoolingResult, entrainmentAdiabaticWallTemperature,
                          entrainmentEffectiveness, entrainmentFilmArrays,
                          entrainmentMultiplier, filmCoolingArrays, filmDrivingTemperature,
                          filmTransferCoefficient, hatchPapellEffectiveness,
                          referenceEntrainmentFraction, referenceTemperatureCorrection,
                          velocityRatioCorrection, velocityRatioFunction, wallMixtureRatio)

# -- Radiative heat transfer -- #

from .radiativeCooling import (RadiativeExtensionResult, RadiativeShell,
                               cylinderMeanBeamLength, effectiveGasSideDriving,
                               meanBeamLength, netWallRadiativeFlux,
                               radiationEquilibriumTemperature, radiativeNozzleExtension,
                               wallRadiationCoefficient)

# -- Thermochemistry -- #

from .ceaInterface import CEA, getAvailableFuels, getAvailableOxidizers

# -- Fluid properties and the standard atmosphere -- #

from .units import (Quantity, convert, convertAltitudeToPressure, convertPressureToAltitude,
                    fromSI, toSI, ureg)
from .fluidProperties import fluidProps, fluidView

# -- Geometry -- #

from .Volute import Volute

# -- Plume -- #

from .plume import (PlumeField, PlumeStructure, machDiskDiameter, machDiskLocation,
                    obliqueShockDeflection, shockCellLength)

# -- Figures -- #

from .figures import exportInteractiveFigures

# -- Errors -- #

# Every failure NOVA raises deliberately is one of these

from .errors import (ConvergenceFailureError, GeometricConstraintError, InvalidInputError,
                     NumericalInstabilityError, PressureDropError, RegenGeometryError,
                     ThermalConstraintError, VoluteGenerationError)

# -- The facade -- #

from .Nozzle import Nozzle

__all__ = [
    # Facade
    'Nozzle',
    # Submodules
    'ablative', 'ceaInterface', 'chamber', 'channelGeometry', 'channelSizing',
    'characteristics', 'config', 'contour', 'contourKernel', 'exports', 'figures',
    'filmCooling', 'gasDynamics', 'gasSideHeatTransfer', 'materials', 'nozzleVolutes', 'plume',
    'radiativeCooling',
    'regenChannels', 'regenStations', 'regenThermal', 'units', 'validation',
    # Gas dynamics
    'areaMachRelation', 'conicalLength', 'divergenceLossFactor', 'machAngle', 'machFromAreaRatio',
    'machFromPrandtlMeyerAngle', 'machFromPressureRatio', 'prandtlMeyerAngle', 'radiusMachRelation',
    'stagnationRatio', 'staticPressureRatio', 'staticTemperatureRatio',
    # Materials
    'availableWallMaterials', 'materialProperties', 'propertyIsMeasured',
    'propertyProvenance', 'resolveWallMaterialName', 'roughnessTable', 'sampleWallMaterial',
    'wallMaterialCurves',
    # Non-metallic and refractory materials
    'availableMaterialClasses', 'availableMaterials', 'materialProfile', 'materialProperty',
    'materialPropertyProvenance', 'maxUseTemperature', 'surfaceEmissivity',
    # Ablative material response
    'AblationEnvironment', 'AblativeLinerResult', 'BPrimeTable', 'CharringMaterial',
    'MaterialResponseResult', 'ablativeNozzleLiner', 'ablativeResponseData',
    'ablativeResponseProvenance', 'availableAblativeMaterials', 'blowingCorrection',
    'diffusionLimitedCharBPrime', 'elementMassFractionsFromMoles',
    'propellantElementMassFractions', 'solveMaterialResponse',
    # Film cooling
    'FilmCoolingResult', 'entrainmentAdiabaticWallTemperature', 'entrainmentEffectiveness',
    'entrainmentFilmArrays', 'entrainmentMultiplier', 'filmCoolingArrays',
    'filmDrivingTemperature', 'filmTransferCoefficient', 'hatchPapellEffectiveness',
    'referenceEntrainmentFraction', 'referenceTemperatureCorrection',
    'velocityRatioCorrection', 'velocityRatioFunction', 'wallMixtureRatio',
    # Radiative heat transfer
    'RadiativeExtensionResult', 'RadiativeShell', 'cylinderMeanBeamLength',
    'effectiveGasSideDriving', 'meanBeamLength', 'netWallRadiativeFlux',
    'radiationEquilibriumTemperature', 'radiativeNozzleExtension',
    'wallRadiationCoefficient',
    # Thermochemistry
    'CEA', 'getAvailableFuels', 'getAvailableOxidizers',
    # Fluid properties, atmosphere and the unit registry
    'convertAltitudeToPressure', 'convertPressureToAltitude', 'fluidProps', 'fluidView',
    'isentropicValues', 'Quantity', 'ureg', 'convert', 'toSI', 'fromSI',
    # Geometry
    'Volute',
    # Plume
    'PlumeField', 'PlumeStructure', 'machDiskDiameter', 'machDiskLocation',
    'obliqueShockDeflection', 'shockCellLength',
    # Figures
    'exportInteractiveFigures',
    # Errors
    'ConvergenceFailureError', 'GeometricConstraintError', 'InvalidInputError',
    'NumericalInstabilityError', 'PressureDropError', 'RegenGeometryError',
    'ThermalConstraintError', 'VoluteGenerationError',
    # Metadata
    '__version__',
]
