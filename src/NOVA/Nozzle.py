
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

# The facade holds configuration, delegates each stage to the module that owns it, and stores
# what comes back. Numerics, plotting and dataframes belong to those modules, so the only
# third-party name this file needs is numpy.
import os
from typing import Any
import numpy as np
# The CEA interface needs rocketcea, which is the one dependency here that is
# commonly missing, so the failure names it.
# The state objects and solvers each stage delegates to. Nothing arrives by wildcard, so this
# block is the whole of what the module binds for its own use.
try:
    from .figures import exportInteractiveFigures
    from .channelSizing import ChannelSizingState
    from .regenChannels import RegenChannelState, regenChannelOutputs, solveRegenChannels, valueOrDefault
    from .nozzleVolutes import RegenVoluteState, regenVoluteOutputs, solveRegenVolutes
    from .chamber import (ConvergingSectionState, convergingSectionOutputs,
                          solveConvergingSection)
    from .regenStations import RegenStationState, regenStationOutputs, solveRegenStations
    from .radiativeCooling import (RadiativeShell, radiativeExtensionOutputs,
                                   radiativeNozzleExtension)
    from .config import setInputs as readConfiguration
    from .exports import (exportData as writeExportData,
                          exportExhaustPropertiesFEA as writeExhaustPropertiesFEA,
                          pickleNozzle as writePickledNozzle)
    from .channelGeometry import ChannelGeometryInputs
    from .regenThermal import (RegenThermalContext,
                               regenHeatTransferModel as solveRegenHeatTransfer,
                               regenHeatTransferModelPlots as drawRegenHeatTransfer)
    from .characteristics import CharacteristicGas
    from .contourKernel import ThroatGeometry
    from .contour import (ContourSolution, contourSolutionOutputs, throatScalingFactor,
                          conicalContour, divergingSectionFamily,
                          truncatedIdealContour as solveTruncatedIdealContour,
                          thrustOptimizedParabolicContour as solveThrustOptimizedParabolicContour,
                          thrustOptimizedContour as solveThrustOptimizedContourWall,
                          solveDesignPoint)

    # The gas dynamics relations are re-exported rather than used here. The plume tests, the
    # showcase scripts and the studies in experimental/ reach for them through this module.
    from .gasDynamics import (prandtlMeyerAngle, machFromPrandtlMeyerAngle, machAngle,
                              machFromPressureRatio, stagnationRatio, staticPressureRatio,
                              staticTemperatureRatio, areaMachRelation, radiusMachRelation,
                              machFromAreaRatio, conicalLength, divergenceLossFactor)
except ImportError as error:
    raise ImportError('Could not import NOVA\'s modules: {}. If the CEA interface is the problem, install its backend with "pip install rocketcea".'.format(error)) from error

#--------------------------------------------------------------------------------------------------------------------------#
# -- Exhaust Plume -- #
#--------------------------------------------------------------------------------------------------------------------------#

# The plume correlations, the TN D-2327 free-jet lattice and the characteristics march that
# continues the nozzle solution past the lip live in plume.py and are re-exported here. The
# studies in experimental/, the showcase scripts and the test suite all reach for them through
# this module, and Nozzle.plumeStructure and Nozzle.plumeField below are their product face.

from .plume import (PlumeContour, PlumeStructure, PlumeField, PlumeGas, PlumeNode,
                    PlumeFlow, PlumePoint, solvePlumeStructure, solvePlumeField,
                    plumeCharacteristicSeed,
                    fullyExpandedDiameter, shockCellLength, machDiskLocation, machDiskDiameter,
                    obliqueShockDeflection, obliqueShockState,
                    freeJetRefineLine, freeJetGeneralPoint, freeJetSameFamilyPoint,
                    freeJetBoundaryPoint, freeJetNearAxisPoint, freeJetCenterLineTarget,
                    freeJetCenterLinePoint, freeJetCrossing, freeJetLeadingCharacteristic,
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

    A nozzle: its wall, its cooling jacket, and the exhaust that leaves it.

    The class carries one engine's configuration and delegates each stage of a run to the module
    that owns it. It holds state and sequences the work; the physics lives in `contour`,
    `chamber`, `regenChannels`, `channelSizing`, `regenThermal`, `nozzleVolutes`,
    `radiativeCooling` and `plume`.

    ----------------------------------------------------------------------
                                What it builds
    ----------------------------------------------------------------------

    Diverging wall, in four families selected by `divergingSectionType`: a cone, a truncated
    ideal contour solved by the axisymmetric method of characteristics, a thrust-optimized
    parabola read off the Rao chart, and a thrust-optimized contour searched over a cubic Bezier
    bell.

    Converging section and combustion chamber, sized from `Lstar` or `chamberLength`.

    Regenerative cooling jacket: circular, rectangular or helical channels, sized station by
    station against a wall temperature limit, with the coolant marched from inlet to outlet. Film
    cooling and an uncooled radiation-cooled extension attach to the same solve.

    Inlet and return volutes, the inlet at the aft end of the jacket and the return at the
    injector face.

    Exhaust plume, either from correlations or by continuing the characteristics march past the
    lip.

    ----------------------------------------------------------------------
                                    Units
    ----------------------------------------------------------------------

    Every quantity crossing a public method boundary is mass-base SI: meters, square and cubic
    meters, kilograms, seconds, kelvin, pascals and kilograms per second. Angles are degrees, as
    configurations name them. Conversions belong at the edge, in `units`.

    ----------------------------------------------------------------------
                                Primary inputs
    ----------------------------------------------------------------------

    Set by `setInputs` from a configuration, or assigned directly.

    Fuel, Oxidizer : str
        CEA propellant names, case sensitive.
    OFRatio : float
        Oxidizer to fuel mass ratio [-], or 'maxisp' to let CEA pick it.
    chamberPressure : float
        Chamber stagnation pressure [Pa].
    thrust : float
        Target thrust [N]. Specify this or `engineMassFlow`, not both.
    engineMassFlow : float
        Engine mass flow [kg/s]. Specify this or `thrust`, not both.
    expansionRatio : float
        Exit area ratio [-]. Specify this or `targetExitPressure`, not both.
    targetExitPressure : float
        Target exit static pressure [Pa]. Specify this or `expansionRatio`, not both.
    divergingSectionType : str
        'cone', 'tic' (truncated ideal contour), 'top' (thrust-optimized parabola) or 'toc'
        (thrust-optimized contour, searched).
    lengthFraction : float
        Length as a fraction of the equivalent 15 degree cone [-].

    Cooling jacket:

    material : str
        Wall alloy, resolved against the materials store.
    coolant : str
        REFPROP fluid name, case sensitive.
    coolantInitialTemperature, coolantInitialPressure, coolantMassFlow : float
        Coolant state at the jacket inlet [K], [Pa], [kg/s].
    channelType : str
        Cross-section family: 'circle', 'rectangular' or 'helical'. A rectangle's width fills the
        pitch at the cold wall less the rib, and its depth is sized. A helix runs at a constant
        angle to the meridian with a fixed aspect ratio, its size is sized, and its rib varies.
    channelHelixAngle, channelAspectRatio : float
        A helix's angle from the meridian [deg] and its depth as a multiple of its width [-].
    minChannelWidth, channelCornerRadius, maxChannelAspectRatio, maxChannelDepth : float
        A rectangle's narrowest width [m], corner radius [m], and the depth it may reach as a
        multiple of its width [-] and outright [m].
    nChannel : int
        Channels around the circumference [-].
    hotWallThickness, shellThickness, infillThickness : float
        Wall between coolant and exhaust, outer shell, and material left between neighboring
        channels [m].
    maxWallTemperature : float
        Hot wall temperature the sizing loop solves each station to [K].

    ----------------------------------------------------------------------
                                Primary outputs
    ----------------------------------------------------------------------

    xNozzleWall, rNozzleWall : numpy.ndarray
        Wall coordinates, axial and radial [m].
    thrustCoef : float
        Thrust coefficient of the generated contour [-].
    exitExpansionRatio : float
        Area ratio the contour actually reaches [-].
    nozzleNearWallTemperature, nozzleNearWallPressure : numpy.ndarray
        Exhaust state along the wall [K], [Pa].
    channelRadius : numpy.ndarray
        Solved channel radius at each station [m].

    An output still None after a run means that branch was never reached, which is kept rather
    than hidden behind a zero.

    ----------------------------------------------------------------------
                                    Methods
    ----------------------------------------------------------------------

    Contour:

        truncatedIdealContour               characteristics wall, returns its figure of merit
        thrustOptimizedParabolicContour     Rao chart parabola
        thrustOptimizedContour              searched cubic Bezier bell
        solveTruncatedIdealDesignPoint      solves the design Mach for a requested design point
        conicalNozzle                       straight-walled cone
        convergingSection                   chamber and converging wall onto the diverging contour
        truncateForRegen                    splits the contour into jacket and extension

    Cooling:

        generateRegenChannels               channels and the jacket around them
        regenHeatTransferModel              coolant and wall thermal state along the jacket
        regenHeatTransferModelPlots         draws that result
        generateRegenVolutes                inlet and return volutes
        generateRadiativeExtension          wall temperature of the uncooled extension

    Plume:

        plumeContour                        characteristics net a plume is seeded from
        plumeStructure                      correlated jet boundary, shock cells and Mach disk
        plumeCharacteristicSeed             mesh and gas state the march starts from
        plumeField                          plume interior, continuing the march past the lip

    Configuration, export and the whole run:

        setInputs                           read a configuration and close the design point
        exportData                          contours, geometry, exhaust properties and the pickle
        exportExhaustPropertiesFEA          near-wall exhaust properties for a structural analysis
        pickleNozzle                        pickle the object
        generateNozzle                      the full pipeline, from configuration to export

    Each solver is fed by a state builder of the same name: `convergingSectionState`,
    `regenStationState`, `regenChannelState`, `channelSizingState`, `channelGeometryInputs`,
    `regenThermalContext`, `regenVoluteState` and `radiativeExtensionInputs`. They gather what
    the solver reads off this object, so the solver itself never touches a `Nozzle`.

    ----------------------------------------------------------------------
                                     Use
    ----------------------------------------------------------------------

    The whole pipeline from a configuration:

    >>> nozzle = Nozzle()
    >>> nozzle.generateNozzle()                                # the shipped reference nozzle
    >>> nozzle.generateNozzle(configPath = 'myEngine.json')    # or one of your own

    Or a stage at a time, setting the inputs directly:

    >>> nozzle = Nozzle()
    >>> nozzle.Fuel = 'HDPE'
    >>> nozzle.Oxidizer = 'O2'
    >>> nozzle.chamberPressure = 15e6
    >>> nozzle.thrust = 150e3
    >>> nozzle.OFRatio = 2.7
    >>> nozzle.targetExitPressure = 101325
    >>> nozzle.solveTruncatedIdealDesignPoint(lengthFraction = 0.8)

    Requires rocketcea for the thermochemistry and ctREFPROP for coolant properties.

    '''

    # ------------------------------------------------------------------------------------------------------------------------------------- #
    # -- Default values for nozzle object -- #
    # ------------------------------------------------------------------------------------------------------------------------------------- #

    def __init__(self):

        '''

        Declare every attribute a run will touch.

        Little of this is a default in the useful sense. Six of the attributes below are read
        while still empty; every other one is overwritten by the configuration reader, or by
        the solver that owns it, before anything looks at it. What the block provides is a
        single declaration point: the state builders copy fields off the Nozzle by name, so
        an attribute missing from here is dropped silently rather than raising, and the unit
        of each one is recorded beside it.

        None is the placeholder throughout. The exceptions are the channel point clouds,
        which are concatenated into while still empty and so have to be arrays.

        '''

        # -- Nozzle Contour Properties -- #

        # Primary Parameters

        self.Fuel                                     = None     # [case sensitive string of CEA propellant name]
        self.Oxidizer                                 = None     # [case sensitive string of CEA propellant name]
        self.chamberPressure: float | None            = None     # [Pa]

        # Specify one - Calculate other: Engine Design Constraints
        # Set 1:
        self.thrust                                   = None     # [N]
        self.engineMassFlow: float | None             = None     # [kg/s]
        # Set 2:
        self.targetExitPressure: float | None         = None     # [Pa]
        self.plumeAmbientPressure                     = None     # [Pa] ambient the plume is drawn against
        self.expansionRatio                           = None     # [-]

        # Additional optional properties
        self.lengthFraction                           = None     # [float]
        self.OFRatio: float | str | None              = None     # [-]
        self.fuelInitialTemperature                   = None     # [K]
        self.oxidizerInitialTemperature               = None     # [K]
        self.numContourPoints: int | None             = None     # [int]
        self.regenTruncationType                      = None     # [str] 'none', 'temp' or 'er'
        self.regenTruncationValue                     = None     # [K] or [-], by regenTruncationType
        self.convergingSectionAngle                   = None     # [deg]
        self.chamberDiameter: float | None            = None     # [m]

        # Combustion chamber sizing. Specify one; leave the other unset.
        self.Lstar                                    = None     # [m] characteristic length, Vc / At
        self.chamberLength                            = None     # [m] cylindrical barrel length

        # Chamber outputs, filled by _prependCombustionChamber()
        self.chamberBarrelLength: float | None        = None     # [m]
        self.chamberVolume: float | None              = None     # [m^3]
        self.chamberLstarActual: float | None         = None     # [m]
        self.chamberContractionRatio: float | None    = None     # [-]

        # # Non-dimensional parameters (From Rao Nozzle)
        self.throatRadiusNonDimensional               = 1        # [-] Non-dimensional
        self.throatInletCurvatureNonDimensional       = 1.5      # [-] Non-dimensional
        self.throatOutletCurvatureNonDimensional      = 0.382    # [-] Non-dimensional
        self.transonicModel                           = 'sauer'  # [str] starting-line solution
        self.initialWallAngleFraction                 = 0.25     # [-] of the design Prandtl-Meyer angle
        self.divergingSectionDesignVariables          = None     # [tuple] pins the searched wall
        self.nozzleScalingFactor: float | None        = None     # [-] Non-dimensional

        # Calculated Properties

        # CEA
        self.ceaOutput: Any                           = None     # CEA object; set once CEA runs, guarded by hasattr
        self.chamberRGasConstant: float | None        = None     # [-]
        self.gammaModel                               = 'chamber' # [str]
        self.combustionChamberGamma                   = None     # [-]
        self.effectiveGamma                           = None     # [-]
        self.chamberGamma: float | None               = None     # [-]
        self.throatGamma: float | None                = None     # [-]
        self.chamberStagnationTemperature: float | None = None   # [K]
        self.maxAdiabaticVelocity: float | None       = None     # [m/s]
        self.exitMachNumber                           = None     # [-]
        self.idealMachNumber: float | None            = None     # [-]

        # Truncated Ideal Contour/Converging Section
        self.numCharacteristics                       = None     # [int]
        self.throatArea                               = None     # [m^2]
        self.theoreticalCharacteristicVelocity        = None     # [m/s]
        self.deliveredCharacteristicVelocity          = None     # [m/s]
        self.xNozzleWallDivergingNonDimensional       = None     # [-]
        self.rNozzleWallDivergingNonDimensional       = None     # [-]
        self.xNozzleWall: np.ndarray | None           = None     # [m]
        self.rNozzleWall: np.ndarray | None           = None     # [m]
        self.nozzleNearWallTemperature                = None     # [K]
        self.nozzleNearWallPressure                   = None     # [Pa]
        self.nozzleNearWallVelocity                   = None     # [m/s]
        self.nozzleNearWallMachNumber                 = None     # [-]
        self.thrustCoef                               = None     # [-]

        self.xRegenNozzle: np.ndarray | None          = None     # [m]
        self.rRegenNozzle: np.ndarray | None          = None     # [m]
        self.regenSectionNearWallTemperature: np.ndarray | None = None # [K]
        self.regenSectionNearWallRecoveryTemperature: np.ndarray | None = None # [K]
        self.regenSectionNearWallPressure: np.ndarray | None = None # [Pa]
        self.regenSectionNearWallVelocity             = None     # [m/s]
        self.regenSectionNearWallMachNumber: np.ndarray | None = None # [-]

        self.xExtension                               = None     # [m]
        self.rExtension                               = None     # [m]

        self.thermalConductivityRegenSection          = None     # [W/m-K]
        self.viscosityRegenSection                    = None     # [Pa-s]
        self.prandtlNumberRegenSection                = None     # [-]
        self.gammaRegenSection: np.ndarray | None     = None     # [-]
        self.gasConstantRegenSection: np.ndarray | None = None   # [J/K]
        self.specificHeatRegenSection                 = None     # [J/kg-K]
        self.densityRegenSection                      = None     # [kg/m^3]
        self.reynoldsNumberRegenSection               = None     # [-]
        self.molecularWeightRegenSection: np.ndarray | None = None # [kg/mol]

        self.exitExpansionRatio                       = None     # [-]
        self.inletContractionRatio                    = None     # [-]
        self.areaRatioArray                           = None     # [-]

        # -- Regenerative Cooling Jacket Properties -- #

        # Geometric Inputs
        self.hotWallThickness: float | None           = None     # [m]
        self.shellThickness: float | None             = None     # [m]
        self.numCSPointsChannel: int | None           = None     # [int]
        self.numCrossSections: int | None             = None     # [int]f
        self.infillThickness                          = None     # [m]

        # dynamicChannelRadii
        self.dcrData                                  = {}
        self.channelType                              = None     # [str]
        self.gasSideAxialModel                        = None     # [str]
        self.minChannelRadius                         = 0.00075  # [m], half the depth of a rectangle
        self.minChannelWidth: float | None            = None     # [m], rectangles
        self.channelCornerRadius: float | None        = None     # [m], rectangles
        self.maxChannelAspectRatio: float | None      = None     # [-], rectangles
        self.maxChannelDepth: float | None            = None     # [m], rectangles
        self.channelHelixAngle: float | None          = None     # [deg], helices
        self.channelAspectRatio: float | None         = None     # [-], helices
        self.channelRibThickness: np.ndarray | None   = None     # [m]
        self.channelWidth: np.ndarray | None          = None     # [m]
        self.channelDepth: np.ndarray | None          = None     # [m]
        self.maxChannelRadius                         = None     # [m]
        self.coolantExitPressure                      = None     # Pa
        self.coolantExitTemperature                   = None     # K

        # Regen Outputs
        self.nChannel: int | None                     = None     # [int]
        self.channelRadius: np.ndarray | None         = None     # [m]
        self.xChannelCenterline2D                     = None     # [m]
        self.rChannelCenterline2D                     = None     # [m]
        self.wrapAngles                               = None     # [m]
        self.xChannelCenterline3D: np.ndarray | None  = None     # [m]
        self.yChannelCenterline3D                     = None     # [m]
        self.zChannelCenterline3D                     = None     # [m]
        self.rChannelCenterline3D                     = None     # [m]
        self.xNozzleShell: np.ndarray | None          = None     # [m]
        self.rNozzleShell: np.ndarray | None          = None     # [m]

        self.xRegenNozzleTrimmed                      = None     # [m]
        self.rRegenNozzleTrimmed: np.ndarray | None   = None     # [m]
        self.gammaRegenSectionTrimmed: np.ndarray | None = None  # [-]
        self.molecularWeightRegenSectionTrimmed: np.ndarray | None = None # [kg/mol]
        self.gasConstantRegenSectionTrimmed: np.ndarray | None = None # [J/K]
        self.regenSectionNearWallTemperatureTrimmed: np.ndarray | None = None # [K]
        self.regenSectionNearWallRecoveryTemperatureTrimmed: np.ndarray | None = None # [K]
        self.regenSectionNearWallMachNumberTrimmed: np.ndarray | None = None # [-]
        self.regenSectionNearWallPressureTrimmed: np.ndarray | None = None # [Pa]

        self.xRegenNozzleInterfaced: np.ndarray | None = None    # [m]
        self.rRegenNozzleInterfaced                   = None     # [m]
        self.numReturnInterfaceCS                     = None     # [int]
        self.numInletInterfaceCS                      = None     # [int]
        self.xReturnInterface                         = None     # [m]
        self.rReturnInterface                         = None     # [m]
        self.xInletInterface                          = None     # [m]
        self.rInletInterface                          = None     # [m]

        self.xNozzleHotWallMesh                       = None     # [m]
        self.yNozzleHotWallMesh                       = None     # [m]
        self.zNozzleHotWallMesh                       = None     # [m]

        self.xNozzleColdWallMesh                      = None     # [m]
        self.yNozzleColdWallMesh                      = None     # [m]
        self.zNozzleColdWallMesh                      = None     # [m]

        self.xNozzleShellMesh                         = None     # [m]
        self.yNozzleShellMesh                         = None     # [m]
        self.zNozzleShellMesh                         = None     # [m]

        self.yChannel: np.ndarray                     = np.array([]) # [m]
        self.xChannel: np.ndarray                     = np.array([]) # [m]
        self.zChannel: np.ndarray                     = np.array([]) # [m]


        # Volute Inputs
        self.makeInletVolute                          = None     # 'on' , 'off'
        self.makeReturnVolute                         = None     # 'on' , 'off'
        self.numCSPointsVolute                        = None     # [int]
        self.voluteRelativeRoll                       = None     # [deg]
        self.voluteFOS                                = 1        # []


        self.inletVoluteCrossSection                  = None     # 'circle' , 'egg' , 'squarc'
        self.inletVoluteAlignment                     = None     # 'n' , 's' , 'o' , 'i' , 'no' , 'ni' , 'so' , 'si' , 'c'
        self.inletVolutePrintability                  = None     # 'off' , 'thick' , 'thin
        self.inletVoluteTilt                          = None     # [deg]
        self.inletGraylocDiameter: float | None       = None     # [in]
        self.inletVoluteAxialOffset                   = None     # [m]

        self.returnVoluteCrossSection                 = None     # 'circle' , 'egg' , 'squarc'
        self.returnVoluteAlignment                    = None     # 'n' , 's' , 'o' , 'i' , 'no' , 'ni' , 'so' , 'si' , 'c'
        self.returnVolutePrintability                 = None     # 'off' , 'thick' , 'thin
        self.returnVoluteTilt                         = None     # [deg]
        self.returnGraylocDiameter: float | None      = None     # [in]
        self.returnVoluteAxialOffset                  = None     # [m]
        self.returnVoluteFlareRoverD                  = None     # [-]
        self.returnVoluteFlareLen                     = None     # [m]

        # Volute Outputs
        self.inletVolute: Any                         = None     # Volute object; set when volute is built
        self.xInletVolute                             = None     # [m]
        self.yInletVolute                             = None     # [m]
        self.zInletVolute                             = None     # [m]
        self.xInletVoluteShell                        = None     # [m]
        self.yInletVoluteShell                        = None     # [m]
        self.zInletVoluteShell                        = None     # [m]
        self.xInletVoluteSupportWall                  = None     # [m]
        self.yInletVoluteSupportWall                  = None     # [m]
        self.zInletVoluteSupportWall                  = None     # [m]
        self.xInletVoluteSupportUpper                 = None     # [m]
        self.yInletVoluteSupportUpper                 = None     # [m]
        self.zInletVoluteSupportUpper                 = None     # [m]
        self.xInletVoluteSupportLower                 = None     # [m]
        self.yInletVoluteSupportLower                 = None     # [m]
        self.zInletVoluteSupportLower                 = None     # [m]

        self.returnVolute: Any                        = None     # Volute object; set when volute is built
        self.xReturnVolute                            = None     # [m]
        self.yReturnVolute                            = None     # [m]
        self.zReturnVolute                            = None     # [m]
        self.xReturnVoluteShell                       = None     # [m]
        self.yReturnVoluteShell                       = None     # [m]
        self.zReturnVoluteShell                       = None     # [m]
        self.xReturnVoluteSupportWall                 = None     # [m]
        self.yReturnVoluteSupportWall                 = None     # [m]
        self.zReturnVoluteSupportWall                 = None     # [m]
        self.xReturnVoluteSupportUpper                = None     # [m]
        self.yReturnVoluteSupportUpper                = None     # [m]
        self.zReturnVoluteSupportUpper                = None     # [m]
        self.xReturnVoluteSupportLower                = None     # [m]
        self.yReturnVoluteSupportLower                = None     # [m]
        self.zReturnVoluteSupportLower                = None     # [m]

        # -- Heat Transfer Model -- #

        # Inputs
        self.filmCooling                              = 'off'    # [str]
        self.filmCoolant                              = None     # [fluid name]
        self.filmMassFlow                             = None     # [kg/s]
        self.filmInletTemperature                     = None     # [K]
        self.filmInjectionAxialPosition               = None     # [m]
        self.filmSlotHeight                           = None     # [m]
        self.regenSectionFilmDrivingTemperature       = None     # [K]
        self.regenSectionFilmDrivingTemperatureTrimmed = None    # [K]
        self.regenSectionFilmEffectiveness            = None     # [-]
        self.regenSectionFilmPropertyCorrection       = None     # [-]
        self.filmCoolingModel                         = 'hatchPapell' # [str]
        self.filmCoolantMixtureRatio                  = 0.0      # [-]
        self.filmEntrainmentMultiplier                = 3.5      # [-]
        self.regenSectionFilmEntrainmentFlowRatio     = None     # [-]
        self.regenSectionFilmWallMixtureRatio         = None     # [-]
        self.regenSectionFilmEntrainmentMultiplier    = None     # [-]

        self.makeRadiativeExtension                   = 'off'    # [str]
        self.extensionMaterial                        = None     # [material name]
        self.extensionThickness                       = None     # [m]
        self.extensionThermalConductivity             = None     # [W/m-K]
        self.extensionInnerEmissivity                 = None     # [-]
        self.extensionOuterEmissivity                 = None     # [-]
        self.extensionOuterViewFactor                 = 1.0      # [-]
        self.extensionSinkTemperature                 = 0.0      # [K]
        self.extensionGasEmissivity                   = 0.0      # [-]
        self.extensionAtmosphere                      = 'inert'  # [str]
        self.extensionJointTemperature                = None     # [K]
        self.radiativeExtensionSolution               = None     # [RadiativeExtensionResult]
        self.extensionWallTemperature                 = None     # [K]
        self.extensionEquilibriumTemperature          = None     # [K]
        self.extensionConvectiveCoefficient           = None     # [W/m^2 K]
        self.extensionConvectiveFlux                  = None     # [W/m^2]
        self.extensionGasRadiativeFlux                = None     # [W/m^2]
        self.extensionEmittedFlux                     = None     # [W/m^2]
        self.extensionConductionFlux                  = None     # [W/m^2]
        self.extensionThroughThicknessDrop            = None     # [K]
        self.extensionPeakWallTemperature             = None     # [K]
        self.extensionTemperatureLimit                = None     # [K]
        self.extensionTemperatureMargin               = None     # [K]
        self.extensionEnergyBalanceResidual           = None     # [-]
        self.filmCoolantVelocity                      = None     # [m/s]
        self.filmSurvivalLength                       = None     # [m]
        self.coolant                                  = None     # [case sensitive string of RefProp fluid name]
        self.coolantInitialTemperature: float | None  = None     # [K]
        self.coolantInitialPressure: float | None     = None     # [Pa]
        self.coolantMassFlow: float | None            = None     # [kg/s]
        self.swirlPercent                             = None     # [-]

        # -- Plume -- #

        self.nozzlePlumeStructure: Any                = None     # PlumeStructure, set by plumeStructure()
        self.nozzlePlumeField: Any                    = None     # PlumeField, set by plumeField()

        # -- Program Options -- #

        # Plot Options
        self.plotsEnabled                             = None     # 'on' , 'off'

        # Export Options
        self.export                                   = None     # 'on' , 'off'
        self.filename                                 = None     # 'on' , 'off'

        self.dataFolder                               = None
        self.topLevelDirectory                        = None

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

    def setInputs(self, inputsPath: str | dict) -> None:

        '''

        Read a configuration onto this object and run the thermochemistry for its design point.

        The reader is `config.setInputs`, which handles a JSON path or a dictionary and
        normalizes the difference between them.

        Parameters:
        -----------
        inputsPath : str | dict
            Path to a .json configuration, or the fields already loaded.

        Raises:
        -------
        InvalidInputError
            If the configuration cannot be read, or its design point cannot be closed.

        '''

        readConfiguration(self, inputsPath)

    # -- Method of Characteristics and Nozzle Contour Generation/Optimization Methods -- #

    def truncatedIdealContour(self, targetExitMach: float, lengthFraction: float,
                              truncate: bool = False, assignOutputsToObject: bool = False) -> float:

        '''

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
        truncate : bool
            True cuts the wall at the requested area ratio and returns the length-fraction
            residual, which is what the design Mach number search drives to zero. False runs the
            wall to the end of the mesh.
        assignOutputsToObject : bool
            True computes and stores the mesh, the near-wall arrays and the derived performance.

        Returns:
        --------
        float
            Length-fraction residual while searching without assignment, thrust coefficient
            otherwise. The full solution is on the object when assignOutputsToObject is set.

        '''

        gas = CharacteristicGas(self.chamberGamma, self.chamberRGasConstant,
                                self.chamberStagnationTemperature)
        throat = ThroatGeometry(self.chamberGamma, self.throatRadiusNonDimensional,
                                self.throatInletCurvatureNonDimensional,
                                self.throatOutletCurvatureNonDimensional,
                                transonicModel = getattr(self, 'transonicModel', 'sauer'))

        solution = ContourSolution(
            gas = gas, throat = throat,
            chamberPressure = self.chamberPressure,
            engineMassFlow = self.engineMassFlow,
            throatGamma = self.throatGamma,
            idealMachNumber = self.idealMachNumber,
            targetExitPressure = self.targetExitPressure,
            numContourPoints = self.numContourPoints,
            requestedAreaRatio = float(self.expansionRatio),
            numCharacteristicsRequested = int(getattr(self, 'numCharacteristicsRequested', 50)),
            ambientSpecificImpulse = self.ceaOutput.nozzlePerformance['ambientISP[s]'])

        solution = solveTruncatedIdealContour(solution, targetExitMach, lengthFraction,
                                              truncate = truncate,
                                              assignOutputsToObject = assignOutputsToObject)

        # Anything the solve left as None is a branch it did not reach, so it is not copied and a
        # value from an earlier call survives rather than being overwritten with nothing.
        for name in contourSolutionOutputs:
            value = getattr(solution, name)
            if value is not None:
                setattr(self, name, value)

        self.nozzleContourSolution = solution

        if truncate and not assignOutputsToObject:
            # The wall is cut at the requested area ratio, so the length is what is left; the
            # design Mach number search drives this residual to zero.
            return solution.deliveredLengthFraction - lengthFraction
        else:
            return solution.thrustCoef

    def thrustOptimizedParabolicContour(self, lengthFraction: float, wallAngles: tuple = None,
                                        assignOutputsToObject: bool = True) -> float:

        '''

        Build a thrust-optimized parabolic diverging section, the family most flight bells are.

        The solve is `contour.thrustOptimizedParabolicContour`. Unlike the truncated ideal contour
        this needs no design-point iteration: the area ratio and the length are properties of a
        wall drawn before the flow is touched, so both are delivered exactly and there is nothing
        to converge.

        Parameters:
        -----------
        lengthFraction : float
            Length as a fraction of the 15 degree cone of the same area ratio [-].
        wallAngles : tuple
            (thetaInflection, thetaExit) in radians, overriding the Rao chart.
        assignOutputsToObject : bool
            True fills in the mesh, the near-wall arrays and the derived performance.

        Returns:
        --------
        float
            Thrust coefficient. The full solution is on the object.

        '''

        gas = CharacteristicGas(self.chamberGamma, self.chamberRGasConstant,
                                self.chamberStagnationTemperature)
        throat = ThroatGeometry(self.chamberGamma, self.throatRadiusNonDimensional,
                                self.throatInletCurvatureNonDimensional,
                                self.throatOutletCurvatureNonDimensional,
                                transonicModel = getattr(self, 'transonicModel', 'sauer'))

        solution = ContourSolution(
            gas = gas, throat = throat,
            chamberPressure = self.chamberPressure,
            engineMassFlow = self.engineMassFlow,
            throatGamma = self.throatGamma,
            idealMachNumber = self.idealMachNumber,
            targetExitPressure = self.targetExitPressure,
            numContourPoints = self.numContourPoints,
            requestedAreaRatio = float(self.expansionRatio),
            numCharacteristicsRequested = int(getattr(self, 'numCharacteristicsRequested', 50)),
            ambientSpecificImpulse = self.ceaOutput.nozzlePerformance['ambientISP[s]'])

        solution = solveThrustOptimizedParabolicContour(
            solution, lengthFraction, wallAngles = wallAngles,
            assignOutputsToObject = assignOutputsToObject)

        for name in contourSolutionOutputs:
            value = getattr(solution, name)
            if value is not None:
                setattr(self, name, value)

        self.nozzleContourSolution = solution
        return solution.thrustCoef

    def thrustOptimizedContour(self, lengthFraction: float, designVariables: tuple = None,
                               **optimizerSettings) -> float:

        '''

        Build a thrust-optimized diverging section by searching the cubic-Bezier bell family.

        The search is `contourOptimization.solveThrustOptimizedContour`, which starts from the
        chart parabola and can therefore only improve on it. Passing `designVariables` skips the
        search and solves that one wall, which is what the optimizer's own objective does and what
        a study sweeping the design space wants.

        `searchFamily = 'quadratic'`, forwarded through `optimizerSettings`, confines the search
        to the parabola surface inside the cubic box: the two wall angles are varied and the
        tensions follow from them. Running both families at one design point is what separates
        what the chart reading costs from what the cubic's extra freedom buys, which a search
        against the chart parabola alone cannot do.

        The optimization record is kept on `nozzleContourOptimization`: the noise floor, the
        perturbation margin and the gain over the parabola. An optimizer that stops is not an
        optimum, and those three are what say whether this one is.

        Parameters:
        -----------
        lengthFraction : float
            Length as a fraction of the 15 degree cone of the same area ratio [-].
        designVariables : tuple
            (inflectionAngle, exitAngle, inflectionTension, exitTension). None runs the search.
        optimizerSettings : dict
            Passed through to `contourOptimization.solveThrustOptimizedContour`. Forwarded rather
            than re-declared here, so a setting added to the driver does not have to be added to
            this signature as well and cannot go missing from it.

        Returns:
        --------
        float
            Thrust coefficient. The full solution is on the object.

        '''

        from .contourOptimization import solveThrustOptimizedContour

        if designVariables is None:
            record = solveThrustOptimizedContour(self, lengthFraction, **optimizerSettings)
            designVariables = record['designVariables']
        else:
            record = None

        gas = CharacteristicGas(self.chamberGamma, self.chamberRGasConstant,
                                self.chamberStagnationTemperature)
        throat = ThroatGeometry(self.chamberGamma, self.throatRadiusNonDimensional,
                                self.throatInletCurvatureNonDimensional,
                                self.throatOutletCurvatureNonDimensional,
                                transonicModel = getattr(self, 'transonicModel', 'sauer'))

        solution = ContourSolution(
            gas = gas, throat = throat,
            chamberPressure = self.chamberPressure,
            engineMassFlow = self.engineMassFlow,
            throatGamma = self.throatGamma,
            idealMachNumber = self.idealMachNumber,
            targetExitPressure = self.targetExitPressure,
            numContourPoints = self.numContourPoints,
            requestedAreaRatio = float(self.expansionRatio),
            numCharacteristicsRequested = int(getattr(self, 'numCharacteristicsRequested', 50)),
            ambientSpecificImpulse = self.ceaOutput.nozzlePerformance['ambientISP[s]'])

        solution = solveThrustOptimizedContourWall(solution, lengthFraction, designVariables,
                                                   assignOutputsToObject = True)

        for name in contourSolutionOutputs:
            value = getattr(solution, name)
            if value is not None:
                setattr(self, name, value)

        self.nozzleContourSolution = solution
        self.nozzleContourOptimization = record
        return solution.thrustCoef

    def solveTruncatedIdealDesignPoint(self, lengthFraction: float | str,
                                       lowerBound: float = 0.65, upperBound: float = 0.9):

        '''

        Solve for the design Mach number that makes the contour deliver its requested design point.

        The solve is `contour.solveDesignPoint`. A truncated ideal contour has two design numbers,
        an area ratio and a length, and one free parameter: the exit Mach number the underlying
        ideal nozzle is designed to. The wall is cut at the requested area ratio, and the solve
        varies the design Mach number until the length is delivered too.

        Parameters:
        -----------
        lengthFraction : float | str
            Requested length as a fraction of the 15 degree cone of the same area ratio. A string
            instead sweeps for the fraction that maximizes the thrust coefficient.
        lowerBound, upperBound : float
            Bounds on the length fraction for that sweep.

        '''

        return solveDesignPoint(self, lengthFraction,
                                lowerBound = lowerBound, upperBound = upperBound)

    def convergingSectionState(self):

        '''

        The chamber state and diverging contour the converging section is built from.

        Returns:
        --------
        ConvergingSectionState
            Inputs seeded, outputs left for the build to fill.

        '''

        state = ConvergingSectionState()
        for name in ConvergingSectionState.__dataclass_fields__:
            setattr(state, name, getattr(self, name, None))

        return state

    def convergingSection(self, convergingSectionAngle: float = 'default',
                          chamberDiameter: float = 'default', inletVolute: bool = 'default',
                          outletVolute: bool = 'default', geometryOnly: bool = False) -> None:

        '''

        Build the combustion chamber and converging section onto the diverging contour.

        The build itself is `chamber.solveConvergingSection`, which takes the chamber state and
        the diverging contour explicitly. This method supplies them and copies the result back.

        Parameters:
        -----------
        convergingSectionAngle : float
            Wall angle at the throat inlet [deg]. 'default' works it out from the contour.
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

        '''

        state = solveConvergingSection(self.convergingSectionState(),
                                       convergingSectionAngle = convergingSectionAngle,
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

        '''

        The contour and propellants the regen split is made from.

        Returns:
        --------
        RegenStationState
            Inputs seeded, outputs left for the split to fill.

        '''

        state = RegenStationState()
        for name in RegenStationState.__dataclass_fields__:
            setattr(state, name, getattr(self, name, None))

        return state

    def truncateForRegen(self):

        '''

        Split the contour into the regen section and the extension beyond it, and sample the
        exhaust state at every station of both.

        The split itself is `regenStations.solveRegenStations`, which takes the contour and the
        propellants explicitly. Where the cut falls is set by `regenTruncationType` and
        `regenTruncationValue`.

        Raises:
        -------
        ThermalConstraintError
            If the requested truncation temperature is never reached along the contour.

        '''

        state = solveRegenStations(self.regenStationState())

        # Anything the split left as None is a branch it did not reach, so it is not copied and a
        # value from an earlier call survives rather than being overwritten with nothing.
        for name in regenStationOutputs:
            value = getattr(state, name)
            if value is not None:
                setattr(self, name, value)

        self.regenStationSolution = state

    def exportExhaustPropertiesFEA(self) -> None:

        '''

        Write the near-wall exhaust properties a structural or thermal analysis reads.

        These are the one-dimensional station properties, which are not the near-wall state the
        characteristics solve returns; see `regenStations` for the size of that difference.

        '''

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
                                self.throatOutletCurvatureNonDimensional,
                                transonicModel = getattr(self, 'transonicModel', 'sauer'))

        self.nozzleScalingFactor = throatScalingFactor(
            self.engineMassFlow, self.chamberPressure, self.throatGamma,
            self.chamberRGasConstant, self.chamberStagnationTemperature)

        self.xNozzleWall, self.rNozzleWall = conicalContour(
            throat, float(self.expansionRatio), self.nozzleScalingFactor,
            numPoints = self.numContourPoints, conicalHalfAngle = conicalHalfAngle)

    def plumeContour(self):

        '''

        The characteristics net and gas state a plume is seeded from.

        Returns:
        --------
        PlumeContour
            The nineteen fields the plume solve reads, and nothing else about this nozzle.

        '''

        contour = PlumeContour()
        for name in PlumeContour.__dataclass_fields__:
            setattr(contour, name, getattr(self, name, None))

        return contour

    def plumeStructure(self, ambientPressure: float, plumeLength: float = None,
                       numBoundaryPoints: int = 400):

        '''

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
            Cell train, Mach disk and boundary, with its own notes on what is and is not modeled.

        '''

        self.nozzlePlumeStructure = solvePlumeStructure(
            self.plumeContour(), ambientPressure = ambientPressure,
            plumeLength = plumeLength, numBoundaryPoints = numBoundaryPoints)

        return self.nozzlePlumeStructure

    def plumeCharacteristicSeed(self) -> dict:

        '''

        The mesh and gas state the plume march starts from.

        Returns:
        --------
        dict
            Exit line, mesh and gas properties, as `plume.plumeCharacteristicSeed` returns them.

        '''

        return plumeCharacteristicSeed(self.plumeContour())

    def plumeField(self, ambientPressure: float, numRays: int = 40, exitPoints: int = 140,
                   maxLines: int = 2000, lineLimit: int = 250) -> 'PlumeField':

        '''

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

        '''

        self.nozzlePlumeField = solvePlumeField(
            self.plumeContour(), ambientPressure = ambientPressure, numRays = numRays,
            exitPoints = exitPoints, maxLines = maxLines, lineLimit = lineLimit)

        return self.nozzlePlumeField

    def generateRegenChannels(self):

        '''

        Build the regenerative cooling channels and the jacket around them.

        The build itself is `regenChannels.solveRegenChannels`, which takes the contour, the
        coolant and the channel definition explicitly and reaches the geometry, sizing and
        thermal modules directly. This method supplies the state it works on and copies the
        result back.

        The geometry and sizing inputs are derived inside the build rather than passed in,
        because both depend on arrays the build itself produces: the sizing solve works on the
        regen section after the volute interfaces have trimmed it, and the cross-section builder
        reads the wall point cloud as it is filled in.

        Raises:
        -------
        InvalidInputError
            If the channel definition is incomplete or out of range.
        RegenGeometryError
            If the channels cannot be laid out on the contour as specified.

        '''

        state = solveRegenChannels(self.regenChannelState(), self.regenThermalContext())

        # Anything the build left as None is a step it did not reach, so it is not copied and a
        # value from an earlier call survives rather than being overwritten with nothing.
        for name in regenChannelOutputs:
            value = getattr(state, name)
            if value is not None:
                setattr(self, name, value)

        self.regenChannelSolution = state

    def radiativeExtensionInputs(self):

        '''

        The shell an uncooled extension is made of, and the exhaust running past it.

        Returns:
        --------
        tuple
            The `RadiativeShell` and a dict of the solver's remaining arguments.

        '''

        # The joint is adiabatic unless a temperature is given for it. The jacket solve does not
        # surface a per-station hot wall temperature onto the Nozzle, so there is nothing to read
        # it from automatically; an adiabatic flange lets no heat out and is the conservative
        # reading of an unknown one.
        shell = RadiativeShell(
            thermalConductivity = self.extensionThermalConductivity,
            thickness           = self.extensionThickness,
            innerEmissivity     = self.extensionInnerEmissivity,
            outerEmissivity     = self.extensionOuterEmissivity,
            outerViewFactor     = self.extensionOuterViewFactor,
            sinkTemperature     = self.extensionSinkTemperature,
            gasEmissivity       = self.extensionGasEmissivity,
            upstreamTemperature = self.extensionJointTemperature,
            material            = self.extensionMaterial,
            atmosphere          = self.extensionAtmosphere)

        return shell, dict(
            axialPosition          = self.xExtension,
            radius                 = self.rExtension,
            machNumber             = self.extensionNearWallMachNumber,
            staticTemperature      = self.extensionNearWallTemperature,
            recoveryTemperature    = self.extensionNearWallRecoveryTemperature,
            chamberPressure        = self.chamberPressure,
            characteristicVelocity = self.theoreticalCharacteristicVelocity,
            exhaustGamma           = self.gammaExtension,
            exhaustGasConstant     = self.gasConstantExtension,
            exhaustMolecularWeight = self.molecularWeightExtension,
            throatRadius           = float(np.min(self.rNozzleWall)),
            throatRadiusOfCurvature = 0.5 * self.nozzleScalingFactor
                                      * (self.throatInletCurvatureNonDimensional
                                         + self.throatOutletCurvatureNonDimensional))

    def generateRadiativeExtension(self):

        '''

        Solve the wall temperature of the uncooled extension beyond the jacket.

        The solve itself is `radiativeCooling.radiativeNozzleExtension`, a damped Newton on the
        nonlinear balance between convection in, conduction along the shell, and radiation out.
        This method supplies the shell and the station state and copies the result back.

        The extension arrays come from `truncateForRegen`, so a configuration with no truncation
        has no extension and nothing is solved.

        Raises:
        -------
        InvalidInputError
            If the shell is incompletely specified or radiates nothing.
        ConvergenceFailureError
            If the balance does not settle.

        '''

        shell, arguments = self.radiativeExtensionInputs()
        result = radiativeNozzleExtension(shell, **arguments)

        for name in radiativeExtensionOutputs:
            setattr(self, name, getattr(result, name))

        self.radiativeExtensionSolution = result

    def regenVoluteState(self):

        '''

        The channel ends and volute definition the volute build reads off this object.

        Filled by name rather than one line at a time, as the channel build state is, and for the
        same reason: the state carries eighty fields and a loop cannot fall out of step with them.

        Returns:
        --------
        RegenVoluteState
            Inputs seeded, outputs left for the build to fill.

        '''

        state = RegenVoluteState()
        for name in RegenVoluteState.__dataclass_fields__:
            setattr(state, name, getattr(self, name, None))

        return state

    def generateRegenVolutes(self):

        '''

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

        '''

        state = solveRegenVolutes(self.regenVoluteState())

        # Anything the build left as None is a volute that was not asked for, so it is not copied
        # and a value from an earlier call survives rather than being overwritten with nothing.
        for name in regenVoluteOutputs:
            value = getattr(state, name)
            if value is not None:
                setattr(self, name, value)

        self.regenVoluteSolution = state

    def regenChannelState(self):

        '''

        The contour, coolant and channel definition the jacket build reads off this object.

        The state carries close to a hundred fields, so it is filled by name rather than one line
        at a time. Every field is seeded from the attribute of the same name, and one this object does
        not carry arrives as None, which is what the build treated an absent attribute as when it
        read them directly.

        Returns:
        --------
        RegenChannelState
            Inputs seeded, outputs left for the build to fill.

        '''

        state = RegenChannelState()
        for name in RegenChannelState.__dataclass_fields__:
            setattr(state, name, getattr(self, name, None))

        return state

    def channelSizingState(self):

        '''

        The engine, coolant and regen section the sizing solve reads off this object.

        Filled by name rather than one line at a time, as the other state builders are. Written
        out explicitly it read `self.maxWallTemperature` and eight other fields that only exist
        once a configuration has been loaded, so it raised on a fresh object rather than handing
        back a state with them unset.

        Returns:
        --------
        ChannelSizingState
            Inputs seeded, outputs left for the solve to fill.

        '''

        state = ChannelSizingState()
        for name in ChannelSizingState.__dataclass_fields__:
            setattr(state, name, getattr(self, name, None))

        return state

    def channelGeometryInputs(self):

        '''

        The channel definition the cross-section builder reads off this object.

        Returns:
        --------
        ChannelGeometryInputs
            Resolution, channel family and wall thicknesses.

        '''

        return ChannelGeometryInputs(
            numCrossSections     = self.numCrossSections,
            numCSPointsChannel   = self.numCSPointsChannel,
            nChannel             = self.nChannel,
            channelType          = self.channelType,
            hotWallThickness     = self.hotWallThickness,
            infillThickness      = self.infillThickness,
            channelCornerRadius  = valueOrDefault(self.channelCornerRadius, 0.0),
            maxChannelAspectRatio = valueOrDefault(self.maxChannelAspectRatio, 8.0),
            maxChannelDepth      = valueOrDefault(self.maxChannelDepth, float('inf')),
            channelHelixAngle    = valueOrDefault(self.channelHelixAngle, 0.0),
            channelAspectRatio   = valueOrDefault(self.channelAspectRatio, 1.0))

    def regenThermalContext(self):

        '''

        The run-level settings the thermal model reads off this object.

        Returns:
        --------
        RegenThermalContext
            Wall alloy, output location and figure flags. Nothing that changes a computed number.

        '''

        return RegenThermalContext(material     = self.material,
                                   dataFolder   = self.dataFolder,
                                   plotsEnabled = self.plotsEnabled,
                                   export       = self.export)

    def regenHeatTransferModel(self, inputsDict: dict, constantColdWallTemperature: float = None,
                               returnDict: bool = False, plots: bool = True,
                               titleFlare: str = '', xReference = [], rReference = []):

        '''

        Solve the coolant and wall thermal state along the jacket.

        The model itself is `regenThermal.regenHeatTransferModel`, which takes its geometry and gas
        state through `inputsDict` and knows nothing about a Nozzle. This method supplies the few
        run-level settings it needs.

        Parameters:
        -----------
        inputsDict : dict
            Geometry, gas state and coolant state, one entry per station. See
            `regenThermal.regenThermalRules` for the keys it requires.
        constantColdWallTemperature : float
            Fixes the cold wall temperature rather than solving for it, which runs the adiabatic
            comparison case [K].
        returnDict : bool
            Return the per-station results rather than only drawing them.
        plots : bool
            Draw the interactive view, subject to plotsEnabled.
        titleFlare : str
            Appended to figure titles.
        xReference, rReference : array_like
            Wall contour drawn beneath the results for reference [m].

        Returns:
        --------
        tuple
            (heatTransferOutputs, plotOutputs) when `returnDict` is set: the coolant and wall
            states, and every per-station quantity the figure draws.

        '''

        return solveRegenHeatTransfer(self.regenThermalContext(), inputsDict,
                                      constantColdWallTemperature = constantColdWallTemperature,
                                      returnDict = returnDict,
                                      plots = plots, titleFlare = titleFlare,
                                      xReference = xReference, rReference = rReference)

    def regenHeatTransferModelPlots(self, coolant, nChannel, results: dict = None,
                                    adiabatic = False, titleFlare: str = '',
                                    xReference = [], rReference = []):

        '''

        Draw the thermal results, one panel per quantity, for this nozzle's channel family.

        The figure itself is `regenThermal.regenHeatTransferModelPlots`. This method supplies
        where it is written and whether it is written at all.

        Parameters:
        -----------
        coolant : str
            Coolant species.
        nChannel : int
            Channel count, reported in the titles.
        results : dict
            Plotting dictionary from the model.
        adiabatic : bool
            Draw the adiabatic cold wall comparison rather than the solved case.
        titleFlare : str
            Appended to figure titles.
        xReference, rReference : array_like
            Wall contour drawn beneath the results for reference [m].

        '''

        return drawRegenHeatTransfer(self.regenThermalContext(), coolant, nChannel,
                                     results = results, family = self.channelType,
                                     adiabatic = adiabatic, titleFlare = titleFlare,
                                     xReference = xReference, rReference = rReference,
                                     wallTemperatureLimit = self.maxWallTemperature)

    # -- Data Exporting Methods -- #

    def exportData(self, filename: str = 'default'):

        '''

        Write the contours, geometry, exhaust properties and pickled run to the output directory.

        The writers are in `exports`. Contour and geometry files are written in millimeters,
        which is what a CAD package expects; the object itself is meter-based.

        Parameters:
        -----------
        filename : str
            Base name for the written files. 'default' takes the run's configured name.

        '''

        return writeExportData(self, filename = filename)

    def pickleNozzle(self, filename: str):

        '''

        Pickle this object so a later session can reopen the result without re-solving.

        Parameters:
        -----------
        filename : str
            Destination path. A missing .pkl extension is added.

        '''

        return writePickledNozzle(self, filename)

    # -- Wrapper for running multiple public methods in series -- #

    def generateNozzle(self, configPath: str = None):

        '''

        Run the whole pipeline, from a configuration to the exported result.

        The stages run in the order each one's inputs become available: diverging contour,
        converging section and chamber, regen truncation, cooling channels, volutes, the
        radiation-cooled extension, the correlated plume, then the figures and the export. Every
        stage after the contour is gated by its own configuration flag, so a run does as much as
        the configuration asks for and no more.

        Parameters:
        -----------
        configPath : str
            Path to a .json configuration. Left unset, the shipped reference nozzle in
            `assets/NOVANozzle.json` is read.

        Raises:
        -------
        InvalidInputError
            If the configuration cannot be read, or its design point cannot be closed.
        NotImplementedError
            If `divergingSectionType` names a contour family that is not built.

        '''

        import os

        if configPath is None:
            # No configuration given runs the shipped reference nozzle, resolved relative to this
            # module so it works from an installed package as well as from a checkout.
            configPath = os.path.join(os.path.dirname(__file__), 'assets', 'NOVANozzle.json')

        # Read inputs
        self.setInputs(inputsPath = configPath)

        # -- Nozzle Contour -- #

        # Generate the diverging section. One resolver decides which family was asked for, so an
        # unrecognized value raises rather than quietly building a truncated ideal contour.
        match divergingSectionFamily(self.divergingSectionType):
            case 'conical':
                self.conicalNozzle()
            case 'truncatedIdeal':
                self.solveTruncatedIdealDesignPoint(self.lengthFraction)
            case 'thrustOptimizedParabola':
                self.thrustOptimizedParabolicContour(self.lengthFraction)
            case 'thrustOptimizedContour':
                # A pinned vector skips the search. Absent, this searches as it always has.
                self.thrustOptimizedContour(
                    self.lengthFraction,
                    designVariables = getattr(self, 'divergingSectionDesignVariables', None))
            case family:
                raise NotImplementedError(
                    f'The {family} diverging section is not built yet. The contour families that '
                    f'run today are the truncated ideal contour and the cone.')

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

        # -- Radiation-Cooled Extension -- #

        if self.makeRadiativeExtension == 'on':
            self.generateRadiativeExtension()

        # -- Exhaust Plume -- #

        # Correlated structure only; see plumeStructure() for what is and is not modeled.
        if not np.isnan(np.float64(self.plumeAmbientPressure if self.plumeAmbientPressure not in ([], None) else np.nan)):
            self.plumeStructure(float(self.plumeAmbientPressure))

        # -- Export -- #

        if self.export == 'on':

            # Every run of this name writes into one directory under the output root.
            topLevelDirectory = self._getOutputRoot()
            self.dataFolder = os.path.join(topLevelDirectory, f'{self.filename}Outputs')

            os.makedirs(self.dataFolder, exist_ok = True)

            self.exportData()

            # Interactive plotly companions for the figures Matplotlib just wrote as PNGs, plus
            # the 3D assembly views that have no static twin.
            exportInteractiveFigures(self, self.dataFolder)

            # Inside the outputs directory, named for the run. Passing the directory itself put the
            # pickle beside it as '<filename>Outputs.pkl', which escapes the *Outputs/ ignore rule
            # and leaves a stray several hundred kilobytes in the parent.
            self.pickleNozzle(os.path.join(self.dataFolder, self.filename))
