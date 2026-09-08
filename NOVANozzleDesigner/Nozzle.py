
# -- NOVA: Nozzle Class Definition -- #

r'''

NOVA:

- Nozzle
- Optimization for
- Variable
- Applications

      / \__
     (    @\___
     /         O
    /   (_____/
   /_____/   U

You heard the man, make da nozzle!

This class definition structures the generation of nozzle geometry.

----------------------------------------------------------------------
                Geometry Generation Conventions
----------------------------------------------------------------------

> To maintain geometric conventions across geometry generators, and to
enforce a cartesian axis convention onto the otherwise radially
symmetric nozzle, the coordinate axes are defined as follows:

For nozzle contour generation (2D Axisymmetric):
    - X (i_hat) is the direction of the outgoing plume along the
      nozzle axis.
    - Y/R (j_hat) is the orthogonal direction to the nozzle axis
      and represents the radial direction away from the nozzle axis

For cooling channel generation (3D):
    - X (i_hat) is the direction of the outgoing fluid from
      the inlet/outlet of the nozzle volute
    - Y (j_hat) is the direction orthogonal to X (i_hat) in the plane
      of the scroll of the nozzle volute
    - Z (k_hat) completes orthogonality, and is the direction of the
      nozzle axis

> To that end, when planar cooling channel cross sections are drawn
they are created in the YZ plane. This geometry convention aligns with
the conventions of traditional CAD softwares such that importing nozzle
geometry from this generator will line up with expectations and
conventions for typical CAD softwares.

> All units are in Mass Base SI
    - Length      [m]
    - Area        [m^2]
    - Volume      [m^3]
    - Temperature [K]
    - Pressure    [Pa]
    - Mass Flow   [kg/s]

Author: Sean Bowman

'''

# Global imports for Nozzle class
import os
import warnings
import copy
from typing import Any
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
# Global imports for GUI
try:
    from utils import *
    # Explicit re-imports so static analysis (Pylance) can resolve names the
    # wildcard hides; runtime behavior is unchanged.
    from utils import (RegenGeometryError, InvalidInputError,
                       NumericalInstabilityError, PressureDropError,
                       ConvergenceFailureError, ThermalConstraintError,
                       GeometricConstraintError, VoluteGenerationError,
                       chunkInterpolate, arcSpline, plotLine, parallelOffset,
                       isentropicValues, fluidProps, createErrorContext,
                       writeFile, readExcel, lineIntersection, revolveContour,
                       intersection, pickleObject, DCM, py2cad)
    from ceaInterface import *
    from ceaInterface import CEA
    from Volute import *
    from Volute import Volute
    from materials import wallMaterialCurves, sampleWallMaterial, availableWallMaterials, resolveWallMaterialName
    from figures import exportInteractiveFigures
    from keepOut import KeepOutEnvelope, keepOutEnvelope, revolveKeepOut, packingClearance
    from channelSizing import (ChannelSizingState, channelSizingOutputs, solveChannelRadii)
    from regenChannels import (RegenChannelState, regenChannelOutputs, solveRegenChannels,
                               validateRegenChannelInputs)
    from volutes import RegenVoluteState, regenVoluteOutputs, solveRegenVolutes
    from chamber import (ConvergingSectionState, convergingSectionOutputs,
                         solveConvergingSection)
    from regenStations import RegenStationState, regenStationOutputs, solveRegenStations
    from config import setInputs as readConfiguration
    from exports import (exportData as writeExportData,
                         exportExhaustPropertiesFEA as writeExhaustPropertiesFEA,
                         pickleNozzle as writePickledNozzle)
    from channelGeometry import (ChannelGeometryInputs,
                                 generateCrossSections as buildCrossSections,
                                 getMaxChannelRadius as maxChannelRadius)
    from regenThermal import (RegenThermalContext, flutedHeatTransferStudyPath,
                              validateRegenHeatTransferInputs,
                              regenHeatTransferModel as solveRegenHeatTransfer,
                              regenHeatTransferModelPlots as drawRegenHeatTransfer)
    from gasDynamics import (prandtlMeyerAngle, machFromPrandtlMeyerAngle, machAngle,
                             machFromPressureRatio, stagnationRatio, staticPressureRatio,
                             staticTemperatureRatio, areaMachRelation, radiusMachRelation,
                             machFromAreaRatio, conicalLength, divergenceLossFactor)
    from characteristics import (CharacteristicGas, axisymmetricMethodOfCharacteristics,
                                 wallCharacteristicProjection)
    from contourKernel import (ThroatGeometry, sauerLimitingCharacteristic,
                               limitingCharacteristicIntersection, throatIntersection)
    from contour import (ContourSolution, contourSolutionOutputs, throatScalingFactor,
                         conicalContour, raoParabolicContour, raoWallAngles,
                         wallAnglesFromContour,
                         truncatedIdealContour as solveTruncatedIdealContour,
                         solveDesignPoint)
# Relative imports for API-based Class calls
except ImportError as e:
    try:
        from .utils import *
        from .utils import (RegenGeometryError, InvalidInputError,
                            NumericalInstabilityError, PressureDropError,
                            ConvergenceFailureError, ThermalConstraintError,
                            GeometricConstraintError, VoluteGenerationError,
                            chunkInterpolate, arcSpline, plotLine, parallelOffset,
                            isentropicValues, fluidProps, createErrorContext,
                            writeFile, readExcel, lineIntersection, revolveContour,
                            intersection, pickleObject, DCM, py2cad)
        from .ceaInterface import *
        from .ceaInterface import CEA
        from .Volute import *
        from .Volute import Volute
        from .materials import wallMaterialCurves, sampleWallMaterial, availableWallMaterials, resolveWallMaterialName
        from .figures import exportInteractiveFigures
        from .keepOut import KeepOutEnvelope, keepOutEnvelope, revolveKeepOut, packingClearance
        from .channelSizing import (ChannelSizingState, channelSizingOutputs, solveChannelRadii)
        from .regenChannels import (RegenChannelState, regenChannelOutputs, solveRegenChannels,
                                    validateRegenChannelInputs)
        from .volutes import RegenVoluteState, regenVoluteOutputs, solveRegenVolutes
        from .chamber import (ConvergingSectionState, convergingSectionOutputs,
                              solveConvergingSection)
        from .regenStations import RegenStationState, regenStationOutputs, solveRegenStations
        from .config import setInputs as readConfiguration
        from .exports import (exportData as writeExportData,
                              exportExhaustPropertiesFEA as writeExhaustPropertiesFEA,
                              pickleNozzle as writePickledNozzle)
        from .channelGeometry import (ChannelGeometryInputs,
                                      generateCrossSections as buildCrossSections,
                                      getMaxChannelRadius as maxChannelRadius)
        from .regenThermal import (RegenThermalContext, flutedHeatTransferStudyPath,
                                   validateRegenHeatTransferInputs,
                                   regenHeatTransferModel as solveRegenHeatTransfer,
                                   regenHeatTransferModelPlots as drawRegenHeatTransfer)
        from .gasDynamics import (prandtlMeyerAngle, machFromPrandtlMeyerAngle, machAngle,
                                  machFromPressureRatio, stagnationRatio, staticPressureRatio,
                                  staticTemperatureRatio, areaMachRelation, radiusMachRelation,
                                  machFromAreaRatio, conicalLength, divergenceLossFactor)
        from .characteristics import (CharacteristicGas, axisymmetricMethodOfCharacteristics,
                                      wallCharacteristicProjection)
        from .contourKernel import (ThroatGeometry, sauerLimitingCharacteristic,
                                    limitingCharacteristicIntersection, throatIntersection)
        from .contour import (ContourSolution, contourSolutionOutputs, throatScalingFactor,
                              conicalContour, raoParabolicContour, raoWallAngles,
                              wallAnglesFromContour,
                              truncatedIdealContour as solveTruncatedIdealContour,
                         solveDesignPoint)
    except ImportError:
        # If both fail, raise the original error with more context
        raise ImportError(f'Could not import required modules. Original error: {e}. If the CEA interface is the problem, install its backend with "pip install rocketcea".')

# Optional GPU acceleration via CuPy. Absent on machines without a CUDA build,
# so import defensively and fall back to CPU. Defines the module-level names the
# GPU nearest-neighbor search paths reference (cp, GPU_AVAILABLE).
try:
    import cupy as cp  # type: ignore[import]  # optional; not installed on CPU-only machines
    GPU_AVAILABLE = True
except ImportError:
    cp = None
    GPU_AVAILABLE = False

# Progress tracking
from tqdm import tqdm

# Visualization imports
import bisect
import math
import matplotlib.pyplot as plt
import matplotlib.tri as tri
# Plotly is optional. It backs the interactive HTML views only; every figure it draws also
# has a Matplotlib equivalent, so a plotly-free install loses the .html files and nothing else.
try:
    import plotly
    import plotly.graph_objects as go
    import plotly.colors
    from plotly.subplots import make_subplots
    from plotly.offline import plot
    from plotly.express.colors import sample_colorscale
    plotlyAvailable = True
except ImportError:
    plotly = go = make_subplots = plot = sample_colorscale = None
    plotlyAvailable = False

# Features already reported as skipped, so the notice prints once per process rather than once
# per cross section.
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


# Scientific computing imports
from scipy.interpolate import UnivariateSpline, interp1d, CubicSpline, griddata
from scipy.optimize import fsolve, least_squares, minimize_scalar
from scipy.spatial import KDTree
from joblib import Parallel, delayed, cpu_count
import sympy as sym

# Data handling
from pandas import read_csv
from datetime import datetime
    

#--------------------------------------------------------------------------------------------------------------------------#
# -- Exhaust Plume -- #
#--------------------------------------------------------------------------------------------------------------------------#

# The plume correlations, the TN D-2327 free-jet lattice and the characteristics march that
# continues the nozzle solution past the lip live in plume.py and are re-exported here. The
# studies in experimental/, the showcase scripts and the test suite all reach for them through
# this module, and Nozzle.plumeStructure and Nozzle.plumeField below are their product face.

try:
    from plume import *
    from plume import (PlumeContour, PlumeStructure, PlumeField, PlumeGas, PlumeNode,
                       PlumeFlow, PlumePoint, solvePlumeStructure, solvePlumeField,
                       plumeCharacteristicSeed,
                       fullyExpandedDiameter, shockCellLength, machDiskLocation, machDiskDiameter,
                       obliqueShockDeflection, obliqueShockState, _exitWallAngle,
                       freeJetRefineLine, freeJetGeneralPoint, freeJetSameFamilyPoint,
                       freeJetBoundaryPoint, freeJetNearAxisPoint, freeJetCentreLineTarget,
                       freeJetCentreLinePoint, freeJetCrossing, freeJetLeadingCharacteristic,
                       freeJetCornerRays, solveFreeJetNet, freeJetInitialLine,
                       plumeInteriorPoint, plumeAxisPoint, plumeNearAxisPoint,
                       plumeFreeBoundaryPoint, plumeSameFamilyPoint, plumeShockCrossing,
                       plumeMassFlux, plumeMachDisk, plumeExitLine, plumeCornerFan,
                       solvePlumeMarch, advancePlumeFront, solvePlumeFront,
                       prandtlCellCoefficient, packCellCoefficient, machDiskLocationCoefficient,
                       machDiskOnsetPressureRatio, separationPressureRatio,
                       plumeFieldMinPressureRatio, plumeFieldMaxPressureRatio,
                       plumeFieldMinExitMach, plumeFieldMaxExitMach, plumeFieldMaxWallAngle)
except ImportError:
    from .plume import *
    from .plume import (PlumeContour, PlumeStructure, PlumeField, PlumeGas, PlumeNode,
                       PlumeFlow, PlumePoint, solvePlumeStructure, solvePlumeField,
                       plumeCharacteristicSeed,
                        fullyExpandedDiameter, shockCellLength, machDiskLocation, machDiskDiameter,
                        obliqueShockDeflection, obliqueShockState, _exitWallAngle,
                        freeJetRefineLine, freeJetGeneralPoint, freeJetSameFamilyPoint,
                        freeJetBoundaryPoint, freeJetNearAxisPoint, freeJetCentreLineTarget,
                        freeJetCentreLinePoint, freeJetCrossing, freeJetLeadingCharacteristic,
                        freeJetCornerRays, solveFreeJetNet, freeJetInitialLine,
                        plumeInteriorPoint, plumeAxisPoint, plumeNearAxisPoint,
                        plumeFreeBoundaryPoint, plumeSameFamilyPoint, plumeShockCrossing,
                        plumeMassFlux, plumeMachDisk, plumeExitLine, plumeCornerFan,
                        solvePlumeMarch, advancePlumeFront, solvePlumeFront,
                        prandtlCellCoefficient, packCellCoefficient, machDiskLocationCoefficient,
                        machDiskOnsetPressureRatio, separationPressureRatio,
                        plumeFieldMinPressureRatio, plumeFieldMaxPressureRatio,
                        plumeFieldMinExitMach, plumeFieldMaxExitMach, plumeFieldMaxWallAngle)


class Nozzle:

    '''

    Rocket nozzle design and analysis class.

    This class provides a comprehensive framework for designing rocket nozzle geometry,
    regenerative cooling systems, and performing thermo-fluid analysis. It implements
    the Axisymmetric Method of Characteristics (AxMoC) for optimized nozzle contour
    generation and includes tools for manufacturing-ready geometry export.

    Core Capabilities:
    ------------------
    1. Nozzle Contour Generation
       - Truncated Ideal Contour (TIC) via Method of Characteristics
       - Pressure-matched contour optimization
       - Conical nozzle alternative
       - Multiple converging section types: traditional, sunken

    2. Regenerative Cooling System Design
       - Helical/fluted cooling channel generation
       - Dynamic channel radius optimization
       - Inlet and return volute generation
       - 3D mesh generation for manufacturing

    3. Thermo-Fluid Analysis
       - Exhaust-side heat transfer (Bartz correlation)
       - Coolant-side convective heat transfer
       - Wall temperature distribution
       - Pressure drop calculations
       - Steady-state operation modeling

    4. Additional Features
       - Correlated exhaust plume structure
       - FEA property export for structural analysis
       - CEA (Chemical Equilibrium with Applications) integration

    Primary Input Attributes:
    -------------------------
    Fuel : str
        CEA propellant name for fuel (case sensitive)
    Oxidizer : str
        CEA propellant name for oxidizer (case sensitive)
    chamberPressure : float
        Chamber stagnation pressure [Pa]
    thrust : float
        Target thrust [N] (specify this OR engineMassFlow)
    engineMassFlow : float
        Engine mass flow rate [kg/s] (specify this OR thrust)
    targetExitPressure : float
        Target nozzle exit pressure [Pa] (specify this OR expansionRatio)
    expansionRatio : float
        Nozzle area expansion ratio [-] (specify this OR targetExitPressure)
    OFRatio : float
        Oxidizer to fuel mass ratio [-]
    lengthFraction : float
        Nozzle length as fraction of equivalent 15-deg conical nozzle [-]
    contourType : str
        Converging section type: 'trad' or 'sunk'

    Regenerative Cooling Attributes:
    --------------------------------
    coolant : str
        REFPROP fluid name for coolant (case sensitive)
    coolantInitialTemperature : float
        Coolant inlet temperature [K]
    coolantInitialPressure : float
        Coolant inlet pressure [Pa]
    coolantMassFlow : float
        Coolant mass flow rate [kg/s]
    hotWallThickness : float
        Hot wall (combustion side) thickness [m]
    shellThickness : float
        Outer shell thickness [m]
    numFlutes : int
        Number of cooling channels

    Key Output Attributes:
    ----------------------
    xNozzleWall : np.ndarray
        Axial coordinates of nozzle wall [m]
    rNozzleWall : np.ndarray
        Radial coordinates of nozzle wall [m]
    thrustCoef : float
        Thrust coefficient [-]
    exitExpansionRatio : float
        Calculated exit expansion ratio [-]
    nozzleNearWallTemperature : np.ndarray
        Hot gas temperature near wall [K]
    nozzleNearWallPressure : np.ndarray
        Hot gas pressure near wall [Pa]

    Public Methods:
    ---------------
    setInputs(inputsPath, debugMode)
        Load configuration from CSV file or dictionary
    truncatedIdealContour(targetExitMach, lengthFraction, ...)
        Generate optimized diverging section via MOC
    pressureMatchTruncatedIdealContour(lengthFraction, ...)
        Generate pressure-matched nozzle contour
    convergingSection(raoThroatAngle, sunkenAngle, ...)
        Generate converging section geometry
    conicalNozzle(conicalHalfAngle)
        Generate simple conical nozzle
    truncateForRegen()
        Prepare geometry for regenerative cooling section
    generateRegenChannels()
        Generate 3D cooling channel geometry
    regenHeatTransferModel()
        Run transient heat transfer analysis
    regenHeatTransferSteadyState(...)
        Run steady-state thermal analysis
    generateRegenVolutes()
        Generate inlet and return manifold volutes
    generateTVCGeometry(...)
        Generate thrust vector control geometry
    steadyStateOperationNozzle(...)
        Analyze steady-state nozzle operation with flowfield
    plumeStructure(ambientPressure, ...)
        Correlated exhaust plume structure: jet boundary, shock cells, Mach disk
    exportData(filename)
        Export geometry and analysis data
    generateNozzle(debugMode, configPath)
        High-level wrapper to run full nozzle generation pipeline
    pickleNozzle(filename)
        Serialize nozzle object for later use

    Typical Workflow:
    -----------------
    1. Instantiate: nozzle = Nozzle()
    2. Set inputs: nozzle.setInputs(configPath) or set attributes directly
    3. Generate contour: nozzle.pressureMatchTruncatedIdealContour(lengthFraction)
    4. Generate converging: nozzle.convergingSection()
    5. Prepare for regen: nozzle.truncateForRegen()
    6. Generate channels: nozzle.generateRegenChannels()
    7. Run heat transfer: nozzle.regenHeatTransferModel()
    8. Generate volutes: nozzle.generateRegenVolutes()
    9. Export: nozzle.exportData(filename)

    Or use the high-level wrapper:
        nozzle = Nozzle()
        nozzle.generateNozzle(configPath='path/to/config.xlsx')

    Examples:
    ---------
    Basic nozzle generation from config file:

    >>> nozzle = Nozzle()
    >>> nozzle.generateNozzle(configPath='config.xlsx')

    Manual attribute-based setup:

    >>> nozzle = Nozzle()
    >>> nozzle.Fuel = 'HDPE'
    >>> nozzle.Oxidizer = 'O2'
    >>> nozzle.chamberPressure = 15e6
    >>> nozzle.thrust = 150e3
    >>> nozzle.OFRatio = 2.7
    >>> nozzle.targetExitPressure = 101325
    >>> nozzle.pressureMatchTruncatedIdealContour(lengthFraction=0.8)

    Notes:
    ------
    - Requires CEA (Chemical Equilibrium with Applications) for combustion analysis
    - Requires REFPROP via ctREFPROP for coolant property evaluation
    - All geometric outputs in SI units (meters)
    - All thermodynamic outputs in SI units (Pa, K, kg/s, etc.)

    See Also:
    ---------
    Volute : Class for generating inlet and return volute geometries
    utils  : Utility functions for fluid properties and geometry

    Author: Sean Bowman

    '''

    # ------------------------------------------------------------------------------------------------------------------------------------- #
    # -- Default values for nozzle object -- # 
    # ------------------------------------------------------------------------------------------------------------------------------------- #

    def __init__(self):

        # -- Nozzle Contour Properties -- #

        # Primary Parameters
        self.Fuel               = [] # [case sensitive string of CEA propellant name]
        self.Oxidizer           = [] # [case sensitive string of CEA propellant name]
        self.chamberPressure: float = 0.0 # [Pa]

        # Specify one - Calculate other: Engine Design Constraints
        # Set 1:
        self.thrust             = [] # [N]
        self.engineMassFlow: float = 0.0 # [kg/s]
        # Set 2:
        self.targetExitPressure: float = 0.0 # [Pa]
        self.plumeAmbientPressure       = [] # [Pa] ambient the plume is drawn against
        self.expansionRatio     = [] # [-]

        # Additional optional properties
        self.visualizeContour           = [] # [bool]
        self.lengthFraction             = [] # [float]
        self.OFRatio: float | str = 0.0 # [-]
        self.fuelInitialTemperature     = [] # [K]
        self.oxidizerInitialTemperature = [] # [K]
        self.numContourPoints: int = 0 # [int]
        self.contourType                = [] # [str]
        self.truncationMethod           = [] # [str]
        self.raoThroatAngle             = [] # [deg]
        self.chamberInterfaceAngle        = [] # [deg]
        self.chamberDiameter: float = 0.0 # [m]

        # Combustion chamber sizing. Specify one; leave the other unset.
        self.Lstar                      = [] # [m] characteristic length, Vc / At
        self.chamberLength              = [] # [m] cylindrical barrel length

        # Chamber outputs, filled by _prependCombustionChamber()
        self.chamberBarrelLength: float     = 0.0 # [m]
        self.chamberVolume: float           = 0.0 # [m^3]
        self.chamberLstarActual: float      = 0.0 # [m]
        self.chamberContractionRatio: float = 0.0 # [-]

        # New sunken nozzle properties
        self.throatEntryLength: float = 0.0 # [m]
        self.throatEccentricity: float = 0.0 # [-] 
        self.throatBackWallPitch: float = 0.0 # [deg]
        self.throatGapThickness: float = 0.0 # [m]
        self.conicDepthModifier: float = 0.0 # [-]
        self.conicPinchModifier: float = 0.0 # [-]

        # # Non-dimensional parameters (From Rao Nozzle)
        self.throatRadiusNonDimensional          = 1     # [-] Non-dimensional
        self.throatInletCurvatureNonDimensional  = 1.5   # [-] Non-dimensional
        self.throatOutletCurvatureNonDimensional = 0.382 # [-] Non-dimensional
        self.nozzleScalingFactor: float = 0.0    # [-] Non-dimensional

        # Calculated Properties

        # CEA
        self.ceaOutput: Any                     = None # CEA object; set once CEA runs, guarded by hasattr
        self.chamberRGasConstant: float = 0.0 # [-]
        self.chamberGamma: float = 0.0 # [-]
        self.throatGamma: float = 0.0 # [-]
        self.chamberStagnationTemperature: float = 0.0 # [K]
        self.maxAdiabaticVelocity: float = 0.0 # [m/s]
        self.exitMachNumber                     = [] # [-]
        self.idealMachNumber: float = 0.0 # [-]
        self.epsilonSauer: float = 0.0 # [-]
        self.epsilonSauerScaled                 = [] # [m]
        self.flowParameterSauer: float = 0.0 # [-]

        # Truncated Ideal Contour/Converging Section
        self.numCharacteristics                 = [] # [int]
        self.throatArea                         = [] # [m^2]
        self.theoreticalCharacteristicVelocity  = [] # [m/s]
        self.deliveredCharacteristicVelocity    = [] # [m/s]
        self.xNozzleWallDivergingNonDimensional = [] # [-]
        self.rNozzleWallDivergingNonDimensional = [] # [-]
        self.xNozzleWall: np.ndarray = np.array([]) # [m]
        self.rNozzleWall: np.ndarray = np.array([]) # [m]
        self.xSunkTurnaround2D                  = [] # [m]
        self.rSunkTurnaround2D                  = [] # [m]
        self.nozzleNearWallTemperature          = np.array([]) # [K]
        self.nozzleNearWallPressure             = [] # [Pa]
        self.nozzleNearWallVelocity             = [] # [m/s]
        self.nozzleNearWallMachNumber           = [] # [-]
        self.thrustCoef                         = [] # [-]
        
        self.xRegenNozzle: np.ndarray = np.array([]) # [m]
        self.rRegenNozzle: np.ndarray = np.array([]) # [m]
        self.regenSectionNearWallTemperature: np.ndarray = np.array([]) # [K]
        self.regenSectionNearWallPressure: np.ndarray    = np.array([]) # [Pa]
        self.regenSectionNearWallVelocity       = [] # [m/s]
        self.regenSectionNearWallMachNumber: np.ndarray  = np.array([]) # [-]

        self.xExtension                         = [] # [m]
        self.rExtension                         = [] # [m]
        self.extensionWallTemperature           = [] # [K]
        self.extensionWallPressure              = [] # [Pa]
        self.extensionWallVelocity              = [] # [m/s]
        self.extensionWallMachNumber            = [] # [-]

        self.thermalConductivityRegenSection   = [] # [W/m-K]
        self.viscosityRegenSection             = [] # [Pa-s]
        self.prandtlNumberRegenSection         = [] # [-]
        self.gammaRegenSection: np.ndarray     = np.array([]) # [-]
        self.gasConstantRegenSection: np.ndarray = np.array([]) # [J/K]
        self.specificHeatRegenSection          = [] # [J/kg-K]
        self.densityRegenSection               = [] # [kg/m^3]
        self.reynoldsNumberRegenSection        = [] # [-]
        self.molecularWeightRegenSection: np.ndarray = np.array([]) # [kg/mol]

        self.exitExpansionRatio                = [] # [-]
        self.inletContractionRatio             = [] # [-]
        self.areaRatioArray                    = [] # [-]

        # -- Regenerative Cooling Jacket Properties -- #

        # Geometric Inputs
        self.hotWallThickness: float = 0.0 # [m]
        self.shellThickness: float = 0.0 # [m]
        self.numCSPointsChannel: int = 0 # [int]
        self.numCrossSections: int = 0 # [int]f
        self.infillThickness          = np.array([]) # [m]
        self.numFlutes                = [] # [int]
        self.fluteAmplitudeCoef: float = 0.0 # [frac of 1]
        self.fluteHelixAngle: float = 0.0 # [deg]
        self.interfaceLength          = [] # [m]

        # Printability options
        self.printabilityCheck = [] # [bool]
        self.printDirection    = [] # [str]
        self.maxOverhangAngle  = [] # [deg]

        # dynamicChannelRadii
        self.dcrData                        = {}
        self.channelType                    = [] # [str]
        self.minChannelRadius               = 0.75e-3 # [m]
        self.maxChannelRadius               = [] # [m]
        self.coolantExitPressure            = [] # Pa
        self.coolantExitTemperature         = [] # K

        # Regen Outputs
        self.nChannel: int = 0 # [int]
        self.channelRadius: np.ndarray = np.array([]) # [m]
        self.xChannelCenterline2D           = [] # [m]
        self.rChannelCenterline2D           = [] # [m]
        self.wrapAngles                     = [] # [m]
        self.xChannelCenterline3D: np.ndarray = np.array([]) # [m]
        self.yChannelCenterline3D           = [] # [m]
        self.zChannelCenterline3D           = [] # [m]
        self.rChannelCenterline3D           = [] # [m]
        self.xNozzleShell: np.ndarray = np.array([]) # [m]
        self.rNozzleShell: np.ndarray = np.array([]) # [m]
        
        self.xRegenNozzleTrimmed                    = [] # [m]
        self.rRegenNozzleTrimmed: np.ndarray = np.array([]) # [m]
        self.gammaRegenSectionTrimmed: np.ndarray = np.array([]) # [-]
        self.molecularWeightRegenSectionTrimmed: np.ndarray = np.array([]) # [kg/mol]
        self.gasConstantRegenSectionTrimmed: np.ndarray = np.array([]) # [J/K]
        self.regenSectionNearWallTemperatureTrimmed: np.ndarray = np.array([]) # [K]
        self.regenSectionNearWallMachNumberTrimmed: np.ndarray = np.array([]) # [-]
        self.regenSectionNearWallPressureTrimmed: np.ndarray = np.array([]) # [Pa]

        self.xRegenNozzleInterfaced: np.ndarray = np.array([]) # [m]
        self.rRegenNozzleInterfaced         = [] # [m]
        self.numReturnInterfaceCS           = 0  # [int]
        self.numInletInterfaceCS            = 0  # [int]
        self.xReturnInterface               = [] # [m]
        self.rReturnInterface               = [] # [m]
        self.xInletInterface                = [] # [m]
        self.rInletInterface                = [] # [m]
        
        self.xNozzleHotWallMesh             = [] # [m]
        self.yNozzleHotWallMesh             = [] # [m]
        self.zNozzleHotWallMesh             = [] # [m]

        self.xNozzleColdWallMesh            = [] # [m]
        self.yNozzleColdWallMesh            = [] # [m]
        self.zNozzleColdWallMesh            = [] # [m]

        self.xNozzleShellMesh               = [] # [m]
        self.yNozzleShellMesh               = [] # [m]
        self.zNozzleShellMesh               = [] # [m]

        self.allNozzlePoints                = [] # [m]
        # Stations the printability audit marked as unsupported. Empty until that audit runs,
        # and read by the cross-section builder whether or not it has.
        self.nonPrintableIndices            = [] # [int]
        # 'on' attempts the CuPy nearest-neighbour search in the cross-section builder before
        # falling back to the CPU. No configuration sets it, so the CPU path is what runs.
        self.useGPU                         = 'off' # 'on' , 'off'

        self.yChannel: np.ndarray = np.array([]) # [m]
        self.xChannel: np.ndarray = np.array([]) # [m]
        self.zChannel: np.ndarray = np.array([]) # [m]

        self.yAllChannels                   = [] # [m]
        self.xAllChannels                   = [] # [m]
        self.zAllChannels                   = [] # [m]
       
        self.xChannelDefeatured: np.ndarray = np.array([]) # [m]
        self.yChannelDefeatured: np.ndarray = np.array([]) # [m]
        self.zChannelDefeatured: np.ndarray = np.array([]) # [m]   

        # Volute Inputs
        self.makeInletVolute         = '' # 'on' , 'off'
        self.makeReturnVolute        = '' # 'on' , 'off'
        self.numCSPointsVolute       = [] # [int]
        self.voluteRelativeRoll      = 0  # [deg]
        self.voluteFOS               = 1  # []
        
        self.plotKeepOut             = '' # 'on' , 'off'
        self.keepOutAxialOffset      = 0.0  # [m]
        self.keepOutRadius           = None # [m], None takes the chamber radius
        self.keepOutDepth            = None # [m], None takes half the keep-out radius
        self.keepOutHubRadius        = None # [m], None takes a quarter of the keep-out radius
        self.nozzleKeepOut: Any = None      # KeepOutEnvelope; built when a volute or sunk contour needs it
        self.xKeepOut3D              = [] # [m]
        self.yKeepOut3D              = [] # [m]
        self.zKeepOut3D              = [] # [m]

        self.inletVoluteCrossSection = '' # 'circle' , 'egg' , 'squarc'
        self.inletVoluteAlignment    = '' # 'n' , 's' , 'o' , 'i' , 'no' , 'ni' , 'so' , 'si' , 'c'
        self.inletVolutePrintability = '' # 'off' , 'thick' , 'thin
        self.inletVoluteTilt         = [] # [deg]
        self.inletGraylocDiameter: float = 0.0 # [in]
        self.inletVoluteAxialOffset  = [] # [m]
        self.inletVoluteFlareRad     = [] # [m]
        self.inletVoluteFlareLen     = [] # [m]
        
        self.returnVoluteCrossSection = '' # 'circle' , 'egg' , 'squarc'
        self.returnVoluteAlignment    = '' # 'n' , 's' , 'o' , 'i' , 'no' , 'ni' , 'so' , 'si' , 'c'
        self.returnVolutePrintability = '' # 'off' , 'thick' , 'thin
        self.returnVoluteTilt         = [] # [deg]
        self.returnGraylocDiameter: float = 0.0 # [in]
        self.returnVoluteAxialOffset  = [] # [m]
        self.returnVoluteRadialOffset: float = 0.0 # [m]
        self.returnVoluteFlareRad     = [] # [m]
        self.returnVoluteFlareAngle   = [] # [deg]
        self.returnVoluteFlareLen     = [] # [m]

        # Volute Outputs
        self.inletVolute: Any          = None # Volute object; set when volute is built
        self.xInletVolute              = [] # [m]
        self.yInletVolute              = [] # [m]
        self.zInletVolute              = [] # [m]
        self.xInletVoluteShell         = [] # [m]
        self.yInletVoluteShell         = [] # [m]
        self.zInletVoluteShell         = [] # [m]
        self.xInletVoluteSupportWall   = [] # [m]
        self.yInletVoluteSupportWall   = [] # [m]
        self.zInletVoluteSupportWall   = [] # [m]
        self.xInletVoluteSupportUpper  = [] # [m]
        self.yInletVoluteSupportUpper  = [] # [m]
        self.zInletVoluteSupportUpper  = [] # [m]
        self.xInletVoluteSupportLower  = [] # [m]
        self.yInletVoluteSupportLower  = [] # [m]
        self.zInletVoluteSupportLower  = [] # [m]
        
        self.returnVolute: Any         = None # Volute object; set when volute is built
        self.xReturnVolute             = [] # [m]
        self.yReturnVolute             = [] # [m]
        self.zReturnVolute             = [] # [m]
        self.xReturnVoluteShell        = [] # [m]
        self.yReturnVoluteShell        = [] # [m]
        self.zReturnVoluteShell        = [] # [m]
        self.xReturnVoluteSupportWall  = [] # [m]
        self.yReturnVoluteSupportWall  = [] # [m]
        self.zReturnVoluteSupportWall  = [] # [m]
        self.xReturnVoluteSupportUpper = [] # [m]
        self.yReturnVoluteSupportUpper = [] # [m]
        self.zReturnVoluteSupportUpper = [] # [m]
        self.xReturnVoluteSupportLower = [] # [m]
        self.yReturnVoluteSupportLower = [] # [m]
        self.zReturnVoluteSupportLower = [] # [m]
        
        # -- Heat Transfer Model -- #

        # Inputs
        self.coolant                   = [] # [case sensitive string of RefProp fluid name]
        self.coolantInitialTemperature: float = 0.0 # [K]
        self.coolantInitialPressure: float = 0.0 # [Pa]
        self.coolantMassFlow: float = 0.0 # [kg/s]
        self.swirlPercent              = [] # [-]
        
        # Outputs
        self.coolantFinalTemperature    = [] # [K]
        self.coolantFinalPressure       = [] # [Pa]
        self.flutedHeatTransferOutputs  = [] # [dict]
        self.circleHeatTransferOutputs  = [] # [dict]
        self.dataMapHeatTransferOutputs = [] # [dict]

        # -- Plume -- #

        self.nozzlePlumeStructure: Any = None # PlumeStructure, set by plumeStructure()
        self.nozzlePlumeField: Any = None     # PlumeField, set by plumeField()

        # -- TVC Properties -- #

        # Geometry
        self.xExtensionMesh      = []
        self.yExtensionMesh      = []
        self.zExtensionMesh      = []
        self.xSealMesh           = []
        self.ySealMesh           = []
        self.zSealMesh           = []
        self.xNozzleMesh         = []
        self.yNozzleMesh         = []
        self.zNozzleMesh         = []
        self.xExtensionActuation = []
        self.rExtensionActuation = []

        # -- Program Options -- #

        self.debugMode = False

        # Plot Options
        self.plotsBasic  = '' # 'on' , 'off'
        self.plotsAdv    = '' # 'on' , 'off'
        self.plotJacket  = '' # 'on', 'off'
        self.plotsDebug  = '' # 'on' , 'off'

        # Export Options
        self.export      = '' # 'on' , 'off'
        self.filename    = '' # 'on' , 'off'

        self.dataFolder        = ''
        self.topLevelDirectory = ''

        # Hidden Options
        self.plotsDocs              = 'off'
        self.inputValidityCheck     = True # [bool]
    
    # ------------------------------------------------------------------------------------------------------------------------------------- #
    # -- Helper Methods -- #
    # ------------------------------------------------------------------------------------------------------------------------------------- #
    
    def _getRepositoryRoot(self) -> str:

        '''

        Find the repository root by walking up the directory tree looking for .git folder.
        
        Raises:
            FileNotFoundError: If no .git directory is found up to the filesystem root.

        Returns:
            str: Absolute path to the repository root directory
            
        '''

        current_dir = os.path.dirname(os.path.abspath(__file__))

        # Walk up the directory tree
        while True:
            # Check if .git folder exists in current directory
            if os.path.exists(os.path.join(current_dir, '.git')):
                return current_dir

            # Get parent directory
            parent_dir = os.path.dirname(current_dir)

            # If we've reached the root of the filesystem, stop. NOVA is usable
            # outside a git checkout (unpacked archive, site-packages install),
            # so fall back to the package's parent directory rather than
            # failing the run purely over where outputs should be written.
            if parent_dir == current_dir:
                return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            current_dir = parent_dir

    def _getOutputRoot(self) -> str:

        '''

        Directory that run outputs are written under. Each run creates
        '<filename>Outputs/' inside it.

        Kept separate from the repository root so that generated artefacts collect in one
        place instead of accumulating beside the source. Callers that manage their own
        output location, such as the GUI and the showcase scripts, override this method.

        Returns:
        --------
        str
            Absolute path to the output root directory.

        '''

        return os.path.join(self._getRepositoryRoot(), 'runs')

    



    # ------------------------------------------------------------------------------------------------------------------------------------- #
    # -- Public Methods (Methods accessible by users) -- #
    # ------------------------------------------------------------------------------------------------------------------------------------- #

    # -- Input Handling Methods -- #

    def setInputs(self, inputsPath: str | dict, debugMode: bool = False) -> None:

        """

        Read a configuration onto this object and run the thermochemistry for its design point.

        The reader is `config.setInputs`, which handles a JSON path, a dictionary or a workbook
        path and normalises the differences between them.

        Parameters:
        -----------
        inputsPath : str | dict
            Path to a .json or .xlsx configuration, or the fields already loaded.
        debugMode : bool
            True dumps the local state of a failed station during later solves.

        Raises:
        -------
        InvalidInputError
            If the configuration cannot be read, or its design point cannot be closed.

        """

        readConfiguration(self, inputsPath, debugMode = debugMode)
        
    # -- Method of Characteristics and Nozzle Contour Generation/Optimization Methods -- #

    def truncatedIdealContour(self, targetExitMach: float, lengthFraction: float,
                              isPressureMatching: bool = False, assignOutputsToObject: bool = False) -> float:

        """

        Generate a truncated ideal contour for this nozzle and return its figure of merit.

        The solve itself is `contour.truncatedIdealContour`, which takes a gas, a throat and the
        design numbers and knows nothing about a Nozzle. This method supplies those, and copies
        back whatever the solve produced.

        Parameters:
        -----------
        targetExitMach : float
            Exit Mach number the ideal nozzle is designed to before truncation [-].
        lengthFraction : float
            Truncation length as a fraction of the 15 degree conical reference [-].
        isPressureMatching : bool
            True truncates at the target length and returns the exit pressure residual, which is
            what the pressure match drives to zero. False runs the wall to the end of the mesh.
        assignOutputsToObject : bool
            True computes and stores the mesh, the near-wall arrays and the derived performance.

        Returns:
        --------
        float
            Exit pressure residual while pressure matching without assignment, thrust coefficient
            otherwise. The full solution is on the object when assignOutputsToObject is set.

        """

        gas = CharacteristicGas(self.chamberGamma, self.chamberRGasConstant,
                                self.chamberStagnationTemperature)
        throat = ThroatGeometry(self.chamberGamma, self.throatRadiusNonDimensional,
                                self.throatInletCurvatureNonDimensional,
                                self.throatOutletCurvatureNonDimensional)

        solution = ContourSolution(
            gas = gas, throat = throat,
            chamberPressure = self.chamberPressure,
            engineMassFlow = self.engineMassFlow,
            throatGamma = self.throatGamma,
            idealMachNumber = self.idealMachNumber,
            targetExitPressure = self.targetExitPressure,
            numContourPoints = self.numContourPoints,
            requestedAreaRatio = float(self.expansionRatio),
            truncateOn = self.truncateOn,
            numCharacteristicsRequested = int(getattr(self, 'numCharacteristicsRequested', 50)),
            ambientSpecificImpulse = self.ceaOutput.nozzlePerformance['ambientISP[s]'],
            plotsDocs = self.plotsDocs)

        solution = solveTruncatedIdealContour(solution, targetExitMach, lengthFraction,
                                              isPressureMatching = isPressureMatching,
                                              assignOutputsToObject = assignOutputsToObject)

        # Anything the solve left as None is a branch it did not reach, so it is not copied and a
        # value from an earlier call survives rather than being overwritten with nothing.
        for name in contourSolutionOutputs:
            value = getattr(solution, name)
            if value is not None:
                setattr(self, name, value)

        self.nozzleContourSolution = solution

        if isPressureMatching and not assignOutputsToObject:
            # The residual the design Mach number is solved on, which is whichever requested
            # number the cut itself does not already satisfy.
            #
            # 'areaRatio' cuts at the requested expansion ratio, so the length is left.
            # 'wallPressure' cuts where the wall reaches the target pressure, so the length is
            # again what is left, and the area ratio falls out of both.
            # 'length' cuts at the requested length, so the residual is the exit pressure, and
            # neither the area ratio nor the pressure is guaranteed. That mode is legacy.
            if self.truncateOn in ('areaRatio', 'wallPressure'):
                return solution.deliveredLengthFraction - lengthFraction
            return solution.pressureError
        else:
            return solution.thrustCoef


    def pressureMatchTruncatedIdealContour(self, lengthFraction: float | str,
                                           lowerBound: float = 0.65, upperBound: float = 0.9):

        """

        Solve for the design Mach number that makes the contour deliver its requested design point.

        The solve is `contour.solveDesignPoint`. A truncated ideal contour has two design numbers,
        an area ratio and a length, and one free parameter: the exit Mach number the underlying
        ideal nozzle is designed to. Which of the two numbers binds is set by `truncateOn`; the
        solve varies the design Mach number until the other one is delivered too.

        Parameters:
        -----------
        lengthFraction : float | str
            Requested length as a fraction of the 15 degree cone of the same area ratio. A string
            instead sweeps for the fraction that maximises the thrust coefficient.
        lowerBound, upperBound : float
            Bounds on the length fraction for that sweep.

        """

        return solveDesignPoint(self, lengthFraction,
                                lowerBound = lowerBound, upperBound = upperBound)


    def convergingSectionState(self):

        """

        The chamber state and diverging contour the converging section is built from.

        Returns:
        --------
        ConvergingSectionState
            Inputs seeded, outputs left for the build to fill.

        """

        state = ConvergingSectionState()
        for name in ConvergingSectionState.__dataclass_fields__:
            setattr(state, name, getattr(self, name, None))

        return state

    def convergingSection(self, raoThroatAngle: float = 'default',
                          chamberInterfaceAngle: float = 'default',
                          chamberDiameter: float = 'default', inletVolute: bool = 'default',
                          outletVolute: bool = 'default', geometryOnly: bool = False) -> None:

        """

        Build the combustion chamber and converging section onto the diverging contour.

        The build itself is `chamber.solveConvergingSection`, which takes the chamber state and
        the diverging contour explicitly. This method supplies them and copies the result back.

        Parameters:
        -----------
        raoThroatAngle : float
            Wall angle at the throat inlet [deg]. 'default' works it out from the contour.
        chamberInterfaceAngle : float
            Wall angle where the converging run meets the chamber [deg]. 'default' as above.
        chamberDiameter : float
            Chamber barrel diameter [m]. 'default' takes the configured value.
        inletVolute, outletVolute : bool
            Whether room is left for each volute. 'default' takes the configured flags.
        geometryOnly : bool
            True draws the wall without solving the flow along it.

        Raises:
        -------
        InvalidInputError
            If the chamber state or the diverging contour is incomplete.
        GeometricConstraintError
            If the wall cannot be closed onto the throat as specified.

        """

        state = solveConvergingSection(self.convergingSectionState(),
                                       raoThroatAngle        = raoThroatAngle,
                                       chamberInterfaceAngle = chamberInterfaceAngle,
                                       chamberDiameter       = chamberDiameter,
                                       inletVolute           = inletVolute,
                                       outletVolute          = outletVolute,
                                       geometryOnly          = geometryOnly)

        # Anything the build left as None is a branch it did not reach, so it is not copied and a
        # value from an earlier call survives rather than being overwritten with nothing.
        for name in convergingSectionOutputs:
            value = getattr(state, name)
            if value is not None:
                setattr(self, name, value)

        self.convergingSectionSolution = state

    def regenStationState(self):

        """

        The contour and propellants the regen split is made from.

        Returns:
        --------
        RegenStationState
            Inputs seeded, outputs left for the split to fill.

        """

        state = RegenStationState()
        for name in RegenStationState.__dataclass_fields__:
            setattr(state, name, getattr(self, name, None))

        return state

    def truncateForRegen(self):

        """

        Split the contour into the regen section and the extension beyond it, and sample the
        exhaust state at every station of both.

        The split itself is `regenStations.solveRegenStations`, which takes the contour and the
        propellants explicitly. Where the cut falls is set by `truncationMethod`.

        Raises:
        -------
        ThermalConstraintError
            If the requested truncation temperature is never reached along the contour.

        """

        state = solveRegenStations(self.regenStationState())

        # Anything the split left as None is a branch it did not reach, so it is not copied and a
        # value from an earlier call survives rather than being overwritten with nothing.
        for name in regenStationOutputs:
            value = getattr(state, name)
            if value is not None:
                setattr(self, name, value)

        self.regenStationSolution = state

    def exportExhaustPropertiesFEA(self) -> None:

        """

        Write the near-wall exhaust properties a structural or thermal analysis reads.

        These are the one-dimensional station properties, which are not the near-wall state the
        characteristics solve returns; see `regenStations` for the size of that difference.

        """

        return writeExhaustPropertiesFEA(self)

    def conicalNozzle(self, conicalHalfAngle: float = 15) -> None:

        '''

        Generate a straight-walled conical diverging section for this nozzle.

        A cone has no characteristic mesh, so no near-wall state is produced here and the plume
        march, which continues that mesh, refuses a conical contour.

        Parameters:
        -----------
        conicalHalfAngle : float
            Cone half angle [deg].

        Author: Cam'ron Valliere
        Date:   11/19/2025

        '''

        throat = ThroatGeometry(self.chamberGamma, self.throatRadiusNonDimensional,
                                self.throatInletCurvatureNonDimensional,
                                self.throatOutletCurvatureNonDimensional)

        self.nozzleScalingFactor = throatScalingFactor(
            self.engineMassFlow, self.chamberPressure, self.throatGamma,
            self.chamberRGasConstant, self.chamberStagnationTemperature)

        self.xNozzleWall, self.rNozzleWall = conicalContour(
            throat, float(self.expansionRatio), self.nozzleScalingFactor,
            numPoints = self.numContourPoints, conicalHalfAngle = conicalHalfAngle)

    def plumeContour(self):

        """

        The characteristics net and gas state a plume is seeded from.

        Returns:
        --------
        PlumeContour
            The nineteen fields the plume solve reads, and nothing else about this nozzle.

        """

        contour = PlumeContour()
        for name in PlumeContour.__dataclass_fields__:
            setattr(contour, name, getattr(self, name, None))

        return contour

    def plumeStructure(self, ambientPressure: float, plumeLength: float = None,
                       numBoundaryPoints: int = 400):

        """

        Correlated structure of the exhaust plume at a given ambient pressure.

        The correlations are `plume.solvePlumeStructure`. This method supplies the contour and
        keeps the result, so a later field solve at the same ambient can reuse it.

        Parameters:
        -----------
        ambientPressure : float
            Pressure the plume expands into [Pa].
        plumeLength : float
            Length of plume to describe [m]. None takes several shock cells.
        numBoundaryPoints : int
            Points along the plume boundary.

        Returns:
        --------
        PlumeStructure
            Cell train, Mach disk and boundary, with its own notes on what is and is not modelled.

        """

        self.nozzlePlumeStructure = solvePlumeStructure(
            self.plumeContour(), ambientPressure = ambientPressure,
            plumeLength = plumeLength, numBoundaryPoints = numBoundaryPoints)

        return self.nozzlePlumeStructure

    def plumeCharacteristicSeed(self) -> dict:

        """

        The mesh and gas state the plume march starts from.

        Returns:
        --------
        dict
            Exit line, mesh and gas properties, as `plume.plumeCharacteristicSeed` returns them.

        """

        return plumeCharacteristicSeed(self.plumeContour())

    def plumeField(self, ambientPressure: float, numRays: int = 40, exitPoints: int = 140,
                   maxLines: int = 2000, lineLimit: int = 250) -> 'PlumeField':

        """

        Solve the plume interior by continuing the nozzle characteristics march past the lip.

        The march is `plume.solvePlumeField`. This method supplies the contour and keeps the
        result.

        Parameters:
        -----------
        ambientPressure : float
            Pressure the plume expands into [Pa].
        numRays : int
            Rays in the corner expansion fan at the lip.
        exitPoints : int
            Points along the exit line the march starts from.
        maxLines, lineLimit : int
            Ceilings on the march, so a net that will not close stops rather than running away.

        Returns:
        --------
        PlumeField
            The solved interior, with its own notes on where it stopped and why.

        """

        self.nozzlePlumeField = solvePlumeField(
            self.plumeContour(), ambientPressure = ambientPressure, numRays = numRays,
            exitPoints = exitPoints, maxLines = maxLines, lineLimit = lineLimit)

        return self.nozzlePlumeField

    def generateRegenChannels(self):

        """

        Build the regenerative cooling channels and the jacket around them.

        The build itself is `regenChannels.solveRegenChannels`, which takes the contour, the
        coolant and the channel definition explicitly and reaches the geometry, sizing and
        thermal modules directly. This method supplies the state it works on and copies the
        result back.

        The geometry and sizing inputs are derived inside the build rather than passed in,
        because both depend on arrays the build itself produces: the sizing solve works on the
        regen section after the volute interfaces have trimmed it, and the cross-section builder
        reads the printability stations and the wall point cloud as they are filled in.

        Raises:
        -------
        InvalidInputError
            If the channel definition is incomplete or out of range.
        RegenGeometryError
            If the channels cannot be laid out on the contour as specified.

        """

        state = solveRegenChannels(self.regenChannelState(), self.regenThermalContext())

        # Anything the build left as None is a step it did not reach, so it is not copied and a
        # value from an earlier call survives rather than being overwritten with nothing.
        for name in regenChannelOutputs:
            value = getattr(state, name)
            if value is not None:
                setattr(self, name, value)

        self.regenChannelSolution = state
            
    def regenVoluteState(self):

        """

        The channel ends and volute definition the volute build reads off this object.

        Filled by name rather than one line at a time, as the channel build state is, and for the
        same reason: the state carries eighty fields and a loop cannot fall out of step with them.

        Returns:
        --------
        RegenVoluteState
            Inputs seeded, outputs left for the build to fill.

        """

        state = RegenVoluteState()
        for name in RegenVoluteState.__dataclass_fields__:
            setattr(state, name, getattr(self, name, None))

        return state

    def generateRegenVolutes(self):

        """

        Build the inlet and return volutes onto the cooling channels.

        The build itself is `volutes.solveRegenVolutes`, which takes the channel ends and the
        volute definition explicitly. This method supplies them and copies the result back.
        `generateRegenChannels` has to have run first, since a volute is grown onto the channel
        ends it collects.

        Raises:
        -------
        InvalidInputError
            If the channels the volutes attach to have not been built.
        VoluteGenerationError
            If a volute cannot be grown on the geometry as specified.

        """

        state = solveRegenVolutes(self.regenVoluteState())

        # Anything the build left as None is a volute that was not asked for, so it is not copied
        # and a value from an earlier call survives rather than being overwritten with nothing.
        for name in regenVoluteOutputs:
            value = getattr(state, name)
            if value is not None:
                setattr(self, name, value)

        self.regenVoluteSolution = state
    
    def regenChannelState(self):

        """

        The contour, coolant and channel definition the jacket build reads off this object.

        The state carries ninety-six fields, so it is filled by name rather than one line at a
        time. Every field is seeded from the attribute of the same name, and one this object does
        not carry arrives as None, which is what the build treated an absent attribute as when it
        read them directly.

        Returns:
        --------
        RegenChannelState
            Inputs seeded, outputs left for the build to fill.

        """

        state = RegenChannelState()
        for name in RegenChannelState.__dataclass_fields__:
            setattr(state, name, getattr(self, name, None))

        return state

    def channelSizingState(self):

        """

        The engine, coolant and regen section the sizing solve reads off this object.

        Filled by name rather than one line at a time, as the other state builders are. Written
        out explicitly it read `self.maxWallTemperature` and eight other fields that only exist
        once a configuration has been loaded, so it raised on a fresh object rather than handing
        back a state with them unset.

        Returns:
        --------
        ChannelSizingState
            Inputs seeded, outputs left for the solve to fill.

        """

        state = ChannelSizingState()
        for name in ChannelSizingState.__dataclass_fields__:
            setattr(state, name, getattr(self, name, None))

        return state

    def channelGeometryInputs(self):

        """

        The channel definition the cross-section builder reads off this object.

        Returns:
        --------
        ChannelGeometryInputs
            Resolution, channel family, wall thicknesses, flute definition and the two arrays the
            surrounding run fills in: the nozzle wall point cloud and the unsupported stations.

        """

        return ChannelGeometryInputs(
            numCrossSections     = self.numCrossSections,
            numCSPointsChannel   = self.numCSPointsChannel,
            nChannel             = self.nChannel,
            channelType          = self.channelType,
            hotWallThickness     = self.hotWallThickness,
            infillThickness      = self.infillThickness,
            numFlutes            = self.numFlutes,
            fluteAmplitudeCoef   = self.fluteAmplitudeCoef,
            fluteHelixAngle      = self.fluteHelixAngle,
            interfaceLength      = self.interfaceLength,
            numInletInterfaceCS  = self.numInletInterfaceCS,
            numReturnInterfaceCS = self.numReturnInterfaceCS,
            printabilityCheck    = self.printabilityCheck,
            nonPrintableIndices  = self.nonPrintableIndices,
            allNozzlePoints      = self.allNozzlePoints,
            useGPU               = self.useGPU)

    def regenThermalContext(self):

        """

        The run-level settings the thermal model reads off this object.

        Returns:
        --------
        RegenThermalContext
            Wall alloy, output location and figure flags. Nothing that changes a computed number.

        """

        return RegenThermalContext(material   = self.material,
                                   dataFolder = self.dataFolder,
                                   plotsAdv   = self.plotsAdv,
                                   plotsDocs  = self.plotsDocs,
                                   export     = self.export,
                                   debugMode  = self.debugMode)

    def regenHeatTransferModel(self, inputsDict: dict, constantColdWallTemperature: float = None,
                               showDataMap: bool = False, returnDict: bool = False, plots: bool = True,
                               titleFlare: str = '', xReference = [], rReference = []):

        """

        Solve the coolant and wall thermal state along the jacket.

        The model itself is `regenThermal.regenHeatTransferModel`, which takes its geometry and gas
        state through `inputsDict` and knows nothing about a Nozzle. This method supplies the few
        run-level settings it needs.

        Parameters:
        -----------
        inputsDict : dict
            Geometry, gas state and coolant state, one entry per station. See the module for the
            keys each channel family requires.
        constantColdWallTemperature : float
            Fixes the cold wall temperature rather than solving for it, which runs the adiabatic
            comparison case [K].
        showDataMap : bool
            Also solve the data-map fluted channel, which needs the flute heat transfer study.
        returnDict : bool
            Return the per-station results rather than only drawing them.
        plots : bool
            Draw the interactive view, subject to plotsAdv.
        titleFlare : str
            Appended to figure titles.
        xReference, rReference : array_like
            Wall contour drawn beneath the results for reference [m].

        Returns:
        --------
        tuple
            Fluted, circular and data-map results, each as an outputs dictionary and a plotting
            dictionary. A family that was not solved returns empty dictionaries.

        """

        return solveRegenHeatTransfer(self.regenThermalContext(), inputsDict,
                                      constantColdWallTemperature = constantColdWallTemperature,
                                      showDataMap = showDataMap, returnDict = returnDict,
                                      plots = plots, titleFlare = titleFlare,
                                      xReference = xReference, rReference = rReference)

    def regenHeatTransferModelPlots(self, coolant, nChannel, adiabatic = False,
                                    flutedResults: dict = None, circleResults: dict = None,
                                    dataMapResults: dict = None, titleFlare: str = '',
                                    xReference = [], rReference = []):

        """

        Draw the thermal results, one panel per quantity, with as many channel families overlaid
        as were solved.

        The figure itself is `regenThermal.regenHeatTransferModelPlots`. This method supplies
        where it is written and whether it is written at all.

        Parameters:
        -----------
        coolant : str
            Coolant species, used for the critical temperature the plot marks.
        nChannel : int
            Channel count, reported in the titles.
        adiabatic : bool
            Draw the adiabatic cold wall comparison rather than the solved case.
        flutedResults, circleResults, dataMapResults : dict
            Plotting dictionaries from the model. A family left as None is not drawn.
        titleFlare : str
            Appended to figure titles.
        xReference, rReference : array_like
            Wall contour drawn beneath the results for reference [m].

        """

        return drawRegenHeatTransfer(self.regenThermalContext(), coolant, nChannel,
                                     adiabatic = adiabatic, flutedResults = flutedResults,
                                     circleResults = circleResults, dataMapResults = dataMapResults,
                                     titleFlare = titleFlare,
                                     xReference = xReference, rReference = rReference)

    # -- Data Exporting Methods -- #

    def exportData(self, filename: str = 'default'):

        """

        Write the contours, geometry, exhaust properties and pickled run to the output directory.

        The writers are in `exports`. Contour and geometry files are written in millimetres,
        which is what a CAD package expects; the object itself is metre-based.

        Parameters:
        -----------
        filename : str
            Base name for the written files. 'default' takes the run's configured name.

        """

        return writeExportData(self, filename = filename)

    def pickleNozzle(self, filename: str):

        """

        Pickle this object so a later session can reopen the result without re-solving.

        Parameters:
        -----------
        filename : str
            Destination path. A missing .pkl extension is added.

        """

        return writePickledNozzle(self, filename)

    # -- Wrapper for running multiple public methods in series -- #

    def generateNozzle(self, configPath: str = None):

        '''
        
        Wrapper around public methods that perform nozzle generation from contour to regen jacket to heat transfer.
        
        '''

        import os

        if configPath is None:
            # Point program to the local config file (relative to Nozzle.py location)
            nozzleModuleDirectory = os.path.dirname(__file__)
            configPath = nozzleModuleDirectory + '\\assets\\nozzleConfig.json'

        # Read inputs
        self.setInputs(inputsPath = configPath)

        # -- Nozzle Contour -- #

        # Generate the diverging section 
        if self.divergingSectionType == 'Conical':
            # Generate a conical diverging section
            self.conicalNozzle(conicalHalfAngle = self.conicalHalfAngle)
        else:
            # Generate a pressure-matched truncated ideal contour diverging section
            self.pressureMatchTruncatedIdealContour(self.lengthFraction)

        # Generate the converging section
        self.convergingSection()

        # Truncate the regen section
        self.truncateForRegen()

        # -- Regenerative Cooling Architecture -- #

        if self.makeCoolingChannels != 'off':
            
            # Generate channel(s)
            self.generateRegenChannels()

            # Generate volute(s)
            if self.makeInletVolute == 'on' or self.makeReturnVolute == 'on':
                self.generateRegenVolutes()
 
        # -- Exhaust Plume -- #

        # Correlated structure only; see plumeStructure() for what is and is not modelled.
        if not np.isnan(np.float64(self.plumeAmbientPressure if self.plumeAmbientPressure not in ([], None) else np.nan)):
            self.plumeStructure(float(self.plumeAmbientPressure))

        # -- Export -- #

        if self.export == 'on':

            # Every run of this name writes into one directory under the output root.
            topLevelDirectory = self._getOutputRoot()
            self.dataFolder = os.path.join(topLevelDirectory, f'{self.filename}Outputs')

            os.makedirs(self.dataFolder, exist_ok = True)

            self.exportData()

            # Interactive plotly companions for the figures Matplotlib just wrote as PNGs.
            # Silently skipped when plotly is not installed.
            exportInteractiveFigures(self, self.dataFolder)

            # Check if excel instance is attached to the object, which is not serializable and
            # therefore must be removed before pickling
            if hasattr(self, 'excelInstance'):
                del self.excelInstance
            # Inside the outputs directory, named for the run. Passing the directory itself put the
            # pickle beside it as '<filename>Outputs.pkl', which escapes the *Outputs/ ignore rule
            # and leaves a stray several hundred kilobytes in the parent.
            self.pickleNozzle(os.path.join(self.dataFolder, self.filename))
   