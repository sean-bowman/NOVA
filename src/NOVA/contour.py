
# -- Nozzle Wall Contour Generation -- #

'''

Generating the diverging wall and measuring what it delivers.

Three families are produced here. They are not interchangeable.

`truncatedIdealContour` solves the characteristics net from a transonic starting line, traces the
wall as the streamline that turns the flow back to axial, and truncates. This is the method
NASA SP-8120 attributes to Ahlberg et al.: design an ideal nozzle to a higher area ratio than
required, then truncate to the area ratio wanted, and the length follows. The interior is shock
free by construction, because it is a piece of an ideal nozzle.

`conicalContour` is a straight wall at a chosen half angle. It has no interior solution and no
free parameters beyond the angle. `solveConicalContour` wraps it so a cone finishes the same way
the contoured families do, supplying the near-wall state from the one-dimensional area-Mach
relation and the thrust coefficient from a source-flow exit plane.

`raoParabolicContour` draws a skewed parabola between two prescribed wall angles. It solves
nothing; it exists so that a generated contour can be compared against the construction most
published bells actually use. It is not a design path.

The solve reads a `ContourSolution` as its own workspace and returns it filled in. That is
deliberate: the algorithm is one long march whose intermediate arrays are also its outputs, and
pretending otherwise would mean copying the whole characteristic mesh twice. What matters for
testing is that nothing here reads or writes a Nozzle: every input arrives through the
workspace, so the solve can be driven from a test with a gas, a throat and four numbers.

Lengths inside the solve are non-dimensional against the throat radius and are scaled to meters
only at the end. Angles are in radians.

Author: Sean Bowman
Date:   09/06/2026

'''

import copy

import numpy as np
from scipy.interpolate import UnivariateSpline
from scipy.optimize import fsolve, minimize_scalar

from .characteristics import (CharacteristicGas, axisymmetricMethodOfCharacteristics,
                              wallCharacteristicProjection)
from .contourKernel import (ThroatGeometry, sauerLimitingCharacteristic,
                            limitingCharacteristicIntersection, throatIntersection)
from .directCharacteristics import (marchPrescribedWall, shockFromWallEnvelope,
                                    stagnationPressureField)
from .gasDynamics import (prandtlMeyerAngle, radiusMachRelation, conicalLength,
                          machFromAreaRatio, staticPressureRatio, staticTemperatureRatio,
                          isentropicValues)
from .wallGeometry import bezierBellWall, thrustOptimizedParabolaWall
from .geometryTools import arcSpline, lineIntersection

def throatScalingFactor(engineMassFlow: float, chamberPressure: float, throatGamma: float,
                        gasConstant: float, stagnationTemperature: float) -> float:

    '''

    Throat radius in meters, from the choked mass flow the engine has to pass.

    The whole contour is solved non-dimensionally against a unit throat radius, so this one number
    carries it into real units. It is the radius of the throat that passes the requested mass flow
    at the chamber state, times an empirical correction.

    That correction, 1 - (gamma - 1) / 96 * (1 / 1.5)^2, reduces the throat area by about 0.07 per
    cent at a gamma of 1.15. It is UNSOURCED: no reference for it has been found. It is understood
    as a discharge-coefficient allowance for the boundary layer and the initial expansion near the
    throat, which is a real effect, but that reading is inference rather than a citation. Published
    discharge coefficients for a throat of this curvature at high Reynolds number sit near 0.99, an
    order of magnitude further from unity, so the correction as written does not reproduce them.

    Parameters:
    -----------
    engineMassFlow : float
        Mass flow the throat must pass [kg/s]
    chamberPressure : float
        Chamber stagnation pressure [Pa]
    throatGamma : float
        Ratio of specific heats at the throat [-]
    gasConstant : float
        Specific gas constant [J/kg-K]
    stagnationTemperature : float
        Chamber stagnation temperature [K]

    Returns:
    --------
    float : Throat radius [m]

    '''

    nozzleThroatArea       = engineMassFlow/((chamberPressure * np.sqrt(throatGamma / \
                                            (gasConstant * stagnationTemperature) * \
                                            ((2 / (throatGamma + 1))**((throatGamma + 1) / (throatGamma - 1))))))
    throatCorrectionFactor = 1 - (throatGamma - 1) / 96 * (1 / 1.5)**2
    return np.sqrt(nozzleThroatArea * throatCorrectionFactor / np.pi)

class ContourSolution:

    '''

    Everything a contour solve reads, and everything it produces.

    The constructor takes the chamber state and the geometric constants the solve needs. Every
    other attribute starts as None and is filled in by the solve, so an attribute that is still
    None afterwards means that branch of the algorithm was never reached, which is information
    worth keeping rather than hiding behind a zero.

    Parameters:
    -----------
    gas : CharacteristicGas
        The gas the net is solved in. Its gamma is the gamma of the mesh, and reading the mesh
        back under any other gamma breaks continuity at the plane where the two meet.
    throat : ThroatGeometry
        Rao throat arcs and the Sauer constants that follow from them.
    chamberPressure : float
        Chamber stagnation pressure [Pa]
    engineMassFlow : float
        Engine mass flow [kg/s]
    throatGamma : float
        Ratio of specific heats at the throat, used only for the choked mass flow that sets scale
    idealMachNumber : float
        Exit Mach number of a one-dimensional expansion to the target exit pressure [-]
    targetExitPressure : float
        Exit static pressure the design is aimed at [Pa]
    numContourPoints : int
        Points in the returned, evenly spaced wall
    initialWallAngleFraction : float
        Fraction of the design-exit Prandtl-Meyer angle at which the diverging throat arc ends,
        which sets where the truncated ideal contour's kernel stops turning the wall. Rao's
        assumption is one quarter and is the default. Read only by the truncated ideal contour:
        the prescribed-wall families end their arc at the inflection angle their wall was drawn to.
    ambientSpecificImpulse : float
        Ambient specific impulse from the thermochemistry, used for the delivered c-star [s]

    '''

    def __init__(self, gas: CharacteristicGas, throat: ThroatGeometry, chamberPressure: float,
                 engineMassFlow: float, throatGamma: float, idealMachNumber: float,
                 targetExitPressure: float, numContourPoints: int,
                 requestedAreaRatio: float = float('nan'),
                 numCharacteristicsRequested: int = 50, initialWallAngleFraction: float = 0.25,
                 ambientSpecificImpulse: float = float('nan')):

        # -- What the solve reads -- #
        self.gas                                 = gas
        self.throat                              = throat
        self.chamberGamma                        = gas.gamma
        self.chamberRGasConstant                 = gas.gasConstant
        self.chamberStagnationTemperature        = gas.stagnationTemperature
        self.chamberPressure                     = chamberPressure
        self.engineMassFlow                      = engineMassFlow
        self.throatGamma                         = throatGamma
        self.idealMachNumber                     = idealMachNumber
        self.targetExitPressure                  = targetExitPressure
        self.numContourPoints                    = numContourPoints
        self.requestedAreaRatio                  = requestedAreaRatio
        self.numCharacteristicsRequested         = numCharacteristicsRequested
        self.initialWallAngleFraction            = initialWallAngleFraction
        self.ambientSpecificImpulse              = ambientSpecificImpulse
        self.throatRadiusNonDimensional          = throat.throatRadius
        self.throatInletCurvatureNonDimensional  = throat.inletCurvature
        self.throatOutletCurvatureNonDimensional = throat.outletCurvature

        # -- Figures of merit -- #
        self.thrustCoef                          = None   # [-]
        self.velocityTermThrustCoef              = None   # [-]
        self.pressureTermThrustCoef              = None   # [-]
        self.pressureError                       = None   # [Pa], wall exit pressure against target

        # -- What the contour actually delivered, as opposed to what was asked for -- #
        self.deliveredAreaRatio                  = None   # [-]
        self.deliveredLengthFraction             = None   # [-], of the 15 degree cone of that area ratio
        self.referenceConeLength                 = None   # [-], the cone the fraction is against
        self.exitWallAngle                       = None   # [rad]
        self.inflectionWallAngle                 = None   # [rad]

        # -- The exit plane, ordered from the wall inward to the axis -- #
        self.exitPlaneRadius                     = None   # [-]
        self.exitPlaneMach                       = None   # [-]
        self.exitPlaneFlowAngle                  = None   # [rad]
        self.exitPlanePressure                   = None   # [Pa]
        self.exitAreaAveragedPressure            = None   # [Pa]
        self.exitMassAveragedPressure            = None   # [Pa]
        self.exitMassFlux                        = None   # [kg/s], non-dimensional radius squared
        self.exitMassClosure                     = None   # [-], exit flux over choked throat flux
        self.exitPlaneSampledFraction            = None   # [-], of the exit area the mesh supplied

        # -- What a prescribed-wall family reports about its own solve -- #
        self.chartExtrapolated                   = None   # [bool], Rao chart read above eps 50
        self.marchTerminatedOn                   = None   # [str], why the wall march stopped
        self.marchFoldedLines                    = None   # [-], lines the march ended on a fold
        self.internalShock                       = None   # [dict], where the net folded, or None
        self.shockFront                          = None   # [dict], the captured front and its loss
        self.thrustCoefWithoutShock              = None   # [-], the same plane with no loss applied
        self.shockThrustDebit                    = None   # [-], what the shock cost

        # -- Wall geometry -- #
        self.xNozzleWall                         = None   # [m]
        self.rNozzleWall                         = None   # [m]
        self.xNozzleWallDivergingNonDimensional  = None   # [-]
        self.rNozzleWallDivergingNonDimensional  = None   # [-]
        self.throatWallX                         = None   # [-]
        self.throatWallR                         = None   # [-]
        self.throatWallAngles                    = None   # [rad]
        self.throatEndAngle                      = None   # [rad]

        # -- Near-wall state along the diverging section -- #
        self.nozzleNearWallTemperature           = None   # [K]
        self.nozzleNearWallPressure              = None   # [Pa]
        self.nozzleNearWallVelocity              = None   # [m/s]
        self.nozzleNearWallMachNumber            = None   # [-]

        # -- The characteristic mesh, in three blocks -- #
        self.limitingCharacteristicX             = None   # [-]
        self.limitingCharacteristicR             = None   # [-]
        self.throatKernelX                       = None   # [-]
        self.throatKernelR                       = None   # [-]
        self.throatKernelMach                    = None   # [-]
        self.expansionKernelX                    = None   # [-]
        self.expansionKernelR                    = None   # [-]
        self.expansionKernelMach                 = None   # [-]
        self.flowStraighteningX                  = None   # [-]
        self.flowStraighteningR                  = None   # [-]
        self.flowStraighteningMachNumber         = None   # [-]
        self.allXPoints                          = None   # [-], the three blocks together
        self.allRPoints                          = None   # [-]
        self.allMachNumbers                      = None   # [-]
        self.allFlowAngles                       = None   # [rad]
        self.allPressures                        = None   # [Pa]
        self.allTemperatures                     = None   # [K]

        # -- Scale and derived performance -- #
        self.numCharacteristics                  = None   # [-]
        self.nozzleScalingFactor                 = None   # [m], throat radius in real units
        self.throatArea                          = None   # [m^2]
        self.calculatedExitMach                  = None   # [-], at the end of the untruncated mesh
        self.calculatedExitRadius                = None   # [-]
        self.theoreticalCharacteristicVelocity   = None   # [m/s]
        self.deliveredCharacteristicVelocity     = None   # [m/s]

    def __repr__(self):
        if self.rNozzleWall is None:
            return 'ContourSolution(unsolved)'
        delivered = (max(self.rNozzleWall) / min(self.rNozzleWall)) ** 2
        return f'ContourSolution(areaRatio = {delivered:.3f}, thrustCoef = {self.thrustCoef:.5f})'

# The outputs a solve hands back to a Nozzle. Kept beside the class so that adding a field to
# ContourSolution and forgetting to surface it is a one-line fix rather than a silent drop.
contourSolutionOutputs = (
    'thrustCoef', 'pressureError', 'xNozzleWall', 'rNozzleWall',
    'xNozzleWallDivergingNonDimensional', 'rNozzleWallDivergingNonDimensional', 'throatWallX',
    'throatWallR', 'throatWallAngles', 'throatEndAngle', 'nozzleNearWallTemperature',
    'nozzleNearWallPressure', 'nozzleNearWallVelocity', 'nozzleNearWallMachNumber',
    'limitingCharacteristicX', 'limitingCharacteristicR', 'throatKernelX', 'throatKernelR',
    'throatKernelMach', 'expansionKernelX', 'expansionKernelR', 'expansionKernelMach',
    'flowStraighteningX', 'flowStraighteningR', 'flowStraighteningMachNumber', 'allXPoints',
    'allRPoints', 'allMachNumbers', 'allFlowAngles', 'allPressures', 'allTemperatures',
    'numCharacteristics', 'nozzleScalingFactor', 'throatArea', 'calculatedExitMach',
    'calculatedExitRadius', 'theoreticalCharacteristicVelocity',
    'deliveredCharacteristicVelocity', 'velocityTermThrustCoef', 'pressureTermThrustCoef',
    'exitPlaneRadius', 'exitPlaneMach', 'exitPlaneFlowAngle', 'exitPlanePressure',
    'exitAreaAveragedPressure', 'exitMassAveragedPressure', 'exitMassFlux', 'exitMassClosure',
    'exitPlaneSampledFraction',
    'chartExtrapolated', 'marchTerminatedOn', 'marchFoldedLines', 'internalShock', 'shockFront',
    'thrustCoefWithoutShock', 'shockThrustDebit',
    'deliveredAreaRatio', 'deliveredLengthFraction', 'referenceConeLength', 'exitWallAngle',
    'inflectionWallAngle')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Shared across every contour family -- #
#--------------------------------------------------------------------------------------------------------------------------#

'''

What follows belongs to no single family.

A contour family is defined by how its wall is arrived at: traced as a streamline through a mesh,
drawn from two angles, or found by an optimizer. Once a wall exists and a mesh has been solved
around it, everything after that is the same work whichever family produced it. Deriving pressure
and temperature from the Mach field, resampling the wall, measuring what the contour actually
delivered: none of it can tell which family it is looking at, and none of it should have to.

These functions were extracted from the truncated ideal solve, where they were the last three
hundred lines. The extraction moved code and changed no arithmetic, which is what the regression
harness holds.

'''

# Every spelling of a diverging section family that a configuration may use, against the one name
# the code decides on. Two of these are the values NOVA has always taken: 'rao' for the truncated
# ideal contour and 'Conical' for a cone. They are kept rather than renamed because
# `divergingSectionType` is a public attribute of a Nozzle, so the regression harness compares it
# as a string, and renaming a token would fail a bit-identity gate for no gain.
divergingSectionSpellings = {
    'conical':                  'conical',
    'cone':                     'conical',
    'tic':                      'truncatedIdeal',
    'rao':                      'truncatedIdeal',
    'truncatedideal':           'truncatedIdeal',
    'truncatedidealcontour':    'truncatedIdeal',
    'top':                      'thrustOptimizedParabola',
    'thrustoptimizedparabola':  'thrustOptimizedParabola',
    'toc':                      'thrustOptimizedContour',
    'thrustoptimizedcontour':   'thrustOptimizedContour',
}

def divergingSectionFamily(name: str) -> str:

    '''

    The family a configured diverging section type names.

    One resolver behind every place that has to decide what to build, so that the decision cannot
    be spelled three different ways in three different modules and drift apart. It already had:
    `Nozzle.generateNozzle` tested one literal, `chamber` tested another, and a third site tested
    a bound method against a string and so was always true.

    Both spellings of "optimized" are accepted, and so are the bare acronyms, because the
    literature uses all of them and a configuration file is not the place to have that argument.

    Parameters:
    -----------
    name : str
        Whatever the configuration said.

    Returns:
    --------
    str : 'conical', 'truncatedIdeal', 'thrustOptimizedParabola' or 'thrustOptimizedContour'

    Raises:
    -------
    ValueError
        On a spelling that is not in the table, rather than silently falling through to a default.
        An unrecognized value used to build a truncated ideal contour and say nothing.

    '''

    try:
        return divergingSectionSpellings[str(name).strip().lower()]
    except KeyError:
        raise ValueError(
            f"No diverging section family is spelled '{name}'. Accepted spellings are "
            f"{sorted(divergingSectionSpellings)}.") from None

def fillIsentropicField(state: ContourSolution) -> None:

    '''

    Static pressure and temperature everywhere the mesh carries a Mach number.

    Both follow from the Mach number alone at fixed stagnation conditions, so they are derived
    rather than solved for. Deriving them keeps all three arrays consistent with the relation they
    came from at every node, which interpolating them separately would not.

    The blocks are written in place on the workspace. NaN padding passes through untouched,
    because an isentropic relation evaluated at NaN returns NaN.

    Parameters:
    -----------
    state : ContourSolution
        Workspace carrying `allMachNumbers` and the chamber state. `allPressures` and
        `allTemperatures` are filled in.

    '''

    # Same shape and the same block count as the Mach field, whatever the family put there.
    state.allPressures    = copy.deepcopy(state.allMachNumbers)
    state.allTemperatures = copy.deepcopy(state.allMachNumbers)

    for i in range(len(state.allMachNumbers)):
        for j in range(state.allMachNumbers[i].shape[0]):
            for k in range(state.allMachNumbers[i].shape[1]):
                state.allTemperatures[i][j,k], state.allPressures[i][j,k], _ \
                = isentropicValues(state.allMachNumbers[i][j,k], state.chamberStagnationTemperature,
                                   state.chamberPressure, state.chamberGamma, state.chamberRGasConstant)

def solveKernel(gas: CharacteristicGas, throat: ThroatGeometry, numCharacteristics: int,
                inflectionAngle: float, chamberPressure: float) -> dict:

    '''

    The characteristic net from the transonic starting line out to the wall inflection point.

    This is the part of a contour solve that does not know which family is being built. Every
    diverging section NOVA generates begins with the same Rao throat arc turned to some angle,
    and the net inside that arc's region of influence is fixed by the angle alone. What differs
    between families is only what happens downstream of the last right-running characteristic
    this returns.

    A truncated ideal contour passes one quarter of the Prandtl-Meyer angle at its design exit
    Mach number, which is the Rao throat assumption. A thrust-optimized parabola passes the
    inflection angle its chart gives. A thrust-optimized contour passes whatever the optimizer is
    currently trying. None of that is visible from here.

    Three pieces, in order. Sauer's transonic solution draws the limiting characteristic, because
    a march cannot begin at the throat where the characteristics are degenerate. The near-throat
    kernel is built out to the wall. The inner expansion kernel is then marched down to the axis
    and reflected across it.

    Parameters:
    -----------
    gas : CharacteristicGas
        The gas the net is solved in.
    throat : ThroatGeometry
        Rao throat arcs and the Sauer constants that follow from them.
    numCharacteristics : int
        Characteristics launched from the throat arc. This is the mesh resolution of the solve.
    inflectionAngle : float
        Wall angle the downstream throat arc is turned to before the contoured wall takes over
        [rad].
    chamberPressure : float
        Chamber stagnation pressure, for the throat wall state [Pa].

    Returns:
    --------
    dict
        The two mesh blocks as (mach, flowAngle, x, r), the limiting characteristic, the throat
        wall and its state, and the two mesh sizes the caller needs to size what comes next.

    '''
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    # -- Generate Initial Characteristic (Sauer's Solution) -- #
    #-----------------------------------------------------------------------------------------------------------------------------------------#

    # print(f'Generating Initial Characteristic via Sauer\'s Solution')

    # Define throat curvature using Rao throat assumption
    # Rao diverging throat ends, by definition, at an angle equal to (1/4) of the prandtl-meyer angle at the exit mach number
    throatWallAngles  = np.linspace(np.deg2rad(1e-5), inflectionAngle, numCharacteristics - 1)
    throatWallAngles  = np.insert(throatWallAngles, 0, 0)
    throatWallX       = throat.throatRadius * throat.outletCurvature * np.sin(throatWallAngles)
    throatWallR       = throat.throatRadius * (1 + throat.outletCurvature) - \
                        throat.throatRadius * throat.outletCurvature * np.cos(throatWallAngles)

    # Generate initial node in mach net
    rLimitingCharacteristicIntersection, xLimitingCharacteristicIntersection, machLimitingCharacteristicIntersection \
    = limitingCharacteristicIntersection(gas, throat, 1, 0, throatWallX[1], throatWallR[1], isInitialNode = True)

    # Verify that the limiting characteristic intersects the throat of the nozzle
    machThroatIntersection, wallAngleThroatIntersection, xThroatIntersection, rThroatIntersection \
    = throatIntersection(gas, throat, machLimitingCharacteristicIntersection, 1e-16, xLimitingCharacteristicIntersection, rLimitingCharacteristicIntersection)

    # Initialize Arrays
    throatKernelMach, throatKernelFlowAngle, \
    throatKernelX, throatKernelR \
    = [np.zeros((numCharacteristics, numCharacteristics)) for _ in range(4)]

    # Store initial value for throat point
    throatKernelMach[0,0], throatKernelFlowAngle[0,0], \
    throatKernelX[0,0], throatKernelR[0,0] \
    = sauerLimitingCharacteristic(gas, throat, 1), 0, 0, 1

    limitingCharacteristicR = np.linspace(throat.throatRadius, 0, numCharacteristics)
    limitingCharacteristicX = np.zeros(numCharacteristics)
    for i in range(numCharacteristics):
        limitingCharacteristicX[i] = sauerLimitingCharacteristic(gas, throat, limitingCharacteristicR[i], returnAxialLocation = True)

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    # -- Generate Near-Throat Kernel -- #
    #-----------------------------------------------------------------------------------------------------------------------------------------#

    # print(f'Generating Near-Throat Kernel')

    # Store initial values at first intersection on Limiting Characteristic
    throatKernelMach[1,0], throatKernelFlowAngle[1,0], \
    throatKernelX[1,0], throatKernelR[1,0] \
    = machLimitingCharacteristicIntersection, 0, xLimitingCharacteristicIntersection, rLimitingCharacteristicIntersection

    # Store initial values at first intersection on throat wall
    throatKernelMach[1,1], throatKernelFlowAngle[1,1], \
    throatKernelX[1,1], throatKernelR[1,1] \
    = machThroatIntersection, wallAngleThroatIntersection, xThroatIntersection, rThroatIntersection

    # Main throat kernel loop
    for i in np.arange(2, numCharacteristics):

        throatKernelX[i,i] = throatWallX[i]
        throatKernelR[i,i] = throatWallR[i]
        throatKernelFlowAngle[i,i] = throatWallAngles[i]

        # Predictor Step
        characteristicProjectionGeometry = [throatKernelFlowAngle[i-1,i-1], throatKernelX[i-1,i-1], throatKernelR[i-1,i-1], \
                                            throatKernelFlowAngle[i,i],     throatKernelX[i,i],     throatKernelR[i,i]]
        throatKernelMach[i,i], throatKernelMach[i, i-1], throatKernelFlowAngle[i, i-1], throatKernelX[i, i-1], throatKernelR[i, i-1] \
        = wallCharacteristicProjection(gas, throatKernelMach[i-1,i-1], characteristicProjectionGeometry)

        for j in reversed(np.arange(2,i)):
            axMOCKernel = [throatKernelMach[i,j],     throatKernelFlowAngle[i,j],     throatKernelX[i,j],     throatKernelR[i,j], \
                           throatKernelMach[i-1,j-1], throatKernelFlowAngle[i-1,j-1], throatKernelX[i-1,j-1], throatKernelR[i-1,j-1]]
            throatKernelMach[i,j-1], throatKernelFlowAngle[i, j-1], throatKernelX[i, j-1], throatKernelR[i, j-1] \
            = axisymmetricMethodOfCharacteristics(gas, axMOCKernel)

        throatKernelR[i,0], throatKernelX[i,0], throatKernelMach[i,0] \
        = limitingCharacteristicIntersection(gas, throat, throatKernelMach[i,1], throatKernelFlowAngle[i,1], throatKernelX[i,1], throatKernelR[i,1])

        # Corrector Step
        for k in range(i-1):
            axMOCKernel = [throatKernelMach[i,k],     throatKernelFlowAngle[i,k],     throatKernelX[i,k],     throatKernelR[i,k], \
                           throatKernelMach[i-1,k+1], throatKernelFlowAngle[i-1,k+1], throatKernelX[i-1,k+1], throatKernelR[i-1,k+1]]
            throatKernelMach[i,k+1], throatKernelFlowAngle[i,k+1], throatKernelX[i,k+1], throatKernelR[i,k+1] \
            = axisymmetricMethodOfCharacteristics(gas, axMOCKernel)

        throatKernelMach[i,i], throatKernelFlowAngle[i,i], throatKernelX[i,i], throatKernelR[i,i] \
        = throatIntersection(gas, throat, throatKernelMach[i,i-1], throatKernelFlowAngle[i,i-1], throatKernelX[i,i-1], throatKernelR[i,i-1])

    # Calculate wall properties in the throat region with isentropic relations
    throatWallMach, throatWallTemperature, \
    throatWallPressure, throatWallVelocity \
    = [np.zeros(numCharacteristics) for _ in range(4)]

    for i in range(numCharacteristics):
        throatWallMach[i] = throatKernelMach[i,i]
        throatWallTemperature[i], throatWallPressure[i], throatWallVelocity[i] \
        = isentropicValues(throatWallMach[i], gas.stagnationTemperature, chamberPressure, \
                            gas.gamma, gas.gasConstant)

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    # -- Generate Inner Expansion Kernel -- #
    #-----------------------------------------------------------------------------------------------------------------------------------------#

    # print(f'Generating Inner Expansion Kernel')

    # Determine spacing between inner mesh elements by determining intersection
    # spacing with respect to the right running characteristic C-

    throatAngle1 = throatKernelFlowAngle[-1,1] - np.arcsin(1 / throatKernelMach[-1,1])
    throatAngle2 = throatKernelFlowAngle[-1,2] - np.arcsin(1 / throatKernelMach[-1,2])
    throatIntersection1 = lineIntersection([throatKernelX[-1,1], throatKernelR[-1,1]], throatAngle1, [0, 0], 0)[0]
    throatIntersection2 = lineIntersection([throatKernelX[-1,2], throatKernelR[-1,2]], throatAngle2, [0, 0], 0)[0]
    reflectedIntersectionX, reflectedIntersectionR = lineIntersection([throatIntersection1, 0], -throatAngle1, \
                                                                        [throatIntersection2, 0],  throatAngle2)

    lengthAlongThroatCharacteristic = np.sqrt((throatKernelX[-1,1] - throatIntersection1)**2 + throatKernelR[-1,1]**2)
    lengthToIntersectionFromCharacteristic = np.sqrt((reflectedIntersectionX - throatIntersection2)**2 + reflectedIntersectionR**2)
    idealMeshSpacing = int(np.ceil(lengthAlongThroatCharacteristic / lengthToIntersectionFromCharacteristic))

    # Number of rows needed for the MoC kernel
    numRows = int(2 * numCharacteristics + idealMeshSpacing - 2)

    # Initialize arrays for kernel
    expansionKernelMach, expansionKernelFlowAngle, \
    expansionKernelX, expansionKernelR \
    = [np.zeros((numRows, numCharacteristics)) for _ in range(4)]

    # Insert Sauer Compatibility initial values
    expansionKernelMach[:numCharacteristics, :numCharacteristics], expansionKernelFlowAngle[:numCharacteristics, :numCharacteristics], \
    expansionKernelX[:numCharacteristics, :numCharacteristics], expansionKernelR[:numCharacteristics, :numCharacteristics] \
    = [sauerStuff for sauerStuff in [throatKernelMach, throatKernelFlowAngle, throatKernelX, throatKernelR]]

    # Create initial right running characteristic
    axMOCKernel = [throatKernelMach[-1,1], -throatKernelFlowAngle[-1,1], throatKernelX[-1,1], -throatKernelR[-1,1], \
                    throatKernelMach[-1,1],  throatKernelFlowAngle[-1,1], throatKernelX[-1,1],  throatKernelR[-1,1]]
    initialRightRunningMach, initialRightRunningFlowAngle, initialRightRunningX, initialRightRunningR, *_ = \
    axisymmetricMethodOfCharacteristics(gas, axMOCKernel, numPoints = idealMeshSpacing)

    # Insert stuff from initial right running characteristic
    expansionKernelMach[numCharacteristics:numCharacteristics+idealMeshSpacing, 1], expansionKernelFlowAngle[numCharacteristics:numCharacteristics+idealMeshSpacing, 1], \
    expansionKernelX[numCharacteristics:numCharacteristics+idealMeshSpacing, 1], expansionKernelR[numCharacteristics:numCharacteristics+idealMeshSpacing, 1] \
    = [rightStuff for rightStuff in [initialRightRunningMach, initialRightRunningFlowAngle, initialRightRunningX, initialRightRunningR]]

    # First loop: make points until the end of the right running characteristic
    for i in np.arange(numCharacteristics, numCharacteristics+idealMeshSpacing):
        for j in np.arange(1, numCharacteristics-1):
            axMOCKernel = [expansionKernelMach[i,j],     expansionKernelFlowAngle[i,j],     expansionKernelX[i,j],     expansionKernelR[i,j], \
                            expansionKernelMach[i-1,j+1], expansionKernelFlowAngle[i-1,j+1], expansionKernelX[i-1,j+1], expansionKernelR[i-1,j+1]]
            expansionKernelMach[i, j+1], expansionKernelFlowAngle[i, j+1], expansionKernelX[i, j+1], expansionKernelR[i, j+1] = \
            axisymmetricMethodOfCharacteristics(gas, axMOCKernel)

    # Second loop: complete the rest of the points from the end of the C- characteristic down to the nozzle axis
    for i in np.arange(numCharacteristics+idealMeshSpacing, numRows):
        j = 2 - (numCharacteristics + idealMeshSpacing) + i
        axMOCKernel = [expansionKernelMach[i-1,j], -expansionKernelFlowAngle[i-1,j], expansionKernelX[i-1,j], -expansionKernelR[i-1,j], \
                        expansionKernelMach[i-1,j],  expansionKernelFlowAngle[i-1,j], expansionKernelX[i-1,j],  expansionKernelR[i-1,j]]
        expansionKernelMach[i, j], expansionKernelFlowAngle[i, j], expansionKernelX[i, j], expansionKernelR[i, j] = \
        axisymmetricMethodOfCharacteristics(gas, axMOCKernel)

        for j in np.arange(2 - (numCharacteristics + idealMeshSpacing) + i, numCharacteristics-1):
            axMOCKernel = [expansionKernelMach[i,j],     expansionKernelFlowAngle[i,j],     expansionKernelX[i,j],     expansionKernelR[i,j], \
                            expansionKernelMach[i-1,j+1], expansionKernelFlowAngle[i-1,j+1], expansionKernelX[i-1,j+1], expansionKernelR[i-1,j+1]]
            expansionKernelMach[i, j+1], expansionKernelFlowAngle[i, j+1], expansionKernelX[i, j+1], expansionKernelR[i, j+1] = \
            axisymmetricMethodOfCharacteristics(gas, axMOCKernel)

    return {
        'throatKernelMach':          throatKernelMach,
        'throatKernelFlowAngle':     throatKernelFlowAngle,
        'throatKernelX':             throatKernelX,
        'throatKernelR':             throatKernelR,
        'expansionKernelMach':       expansionKernelMach,
        'expansionKernelFlowAngle':  expansionKernelFlowAngle,
        'expansionKernelX':          expansionKernelX,
        'expansionKernelR':          expansionKernelR,
        'limitingCharacteristicX':   limitingCharacteristicX,
        'limitingCharacteristicR':   limitingCharacteristicR,
        'throatWallX':               throatWallX,
        'throatWallR':               throatWallR,
        'throatWallAngles':          throatWallAngles,
        'throatWallMach':            throatWallMach,
        'throatWallTemperature':     throatWallTemperature,
        'throatWallPressure':        throatWallPressure,
        'throatWallVelocity':        throatWallVelocity,
        'numRows':                   numRows,
        'idealMeshSpacing':          idealMeshSpacing,
    }

def sampleExitPlaneByWalk(state: ContourSolution, xExitPlane: float, wallRadius: float,
                          wallMach: float, straighteningBlocks: tuple,
                          expansionBlocks: tuple, entryIndices: tuple,
                          numContourElements: int) -> tuple:

    '''

    The flow across the exit plane, read off the mesh by descending through it from the wall.

    A staircase. It starts in the mesh cell the wall march finished in and steps inward, taking
    each cell edge that straddles the exit station and interpolating the state along it, first
    through the flow-straightening block and then through the expansion kernel behind it.

    The walk runs out of columns before it reaches the axis, typically around a quarter of the
    exit radius. That leaves a core carrying roughly eight percent of the exit AREA unsampled,
    and because the thrust integral weights by area over the FULL exit area, an unsampled core
    subtracts directly from the thrust coefficient rather than showing up as a gap. The plane is
    closed on the axis instead, where the flow angle is zero by symmetry and the Mach number is
    extrapolated from the two innermost sampled points, and `exitPlaneSampledFraction` records
    how much of the plane the mesh actually supplied.

    This is the truncated ideal contour's own sampler, and it encodes that solve's traversal: the
    staircase steps inward because the TIC builds its wall outward against a prescribed exit line.
    A family whose wall is prescribed marches the other way, so it samples its exit plane by
    scanning the cell edges that straddle the station rather than by walking indices, and its
    plane needs no closure because every characteristic reaches the axis.

    Parameters:
    -----------
    state : ContourSolution
        Workspace. `exitPlaneSampledFraction` is written to it.
    xExitPlane : float
        Axial station of the exit plane, non-dimensional.
    wallRadius, wallMach : float
        Radius and Mach number at the wall end of the plane.
    straighteningBlocks, expansionBlocks : tuple
        (x, r, mach, flowAngle) for each block, in the order the walk descends through them.
    entryIndices : tuple
        (i, j) of the cell the wall march finished in.
    numContourElements : int
        Bound on the walk, from the mesh the solve built.

    Returns:
    --------
    tuple : (radius, mach, flowAngle) ordered from the wall inward to the axis

    '''

    straighteningX, straighteningR, straighteningMach, straighteningFlowAngle = straighteningBlocks
    expansionX, expansionR, expansionMach, expansionFlowAngle = expansionBlocks
    iExit, jExit = entryIndices
    terminated = False

    # The exit station and the wall end of the plane are handed in, not re-derived.
    rExitPlane, flowAngleExitPlane, machNumberExitPlane \
    = [np.zeros(4 * (numContourElements - 1)) for _ in range(3)]

    rExitPlane[0], machNumberExitPlane[0], flowAngleExitPlane[0] = wallRadius, wallMach, straighteningFlowAngle[iExit,jExit]

    index = 0

    while iExit < (numContourElements - 2) and jExit > 0:

        index += 1

        if straighteningX[iExit+1,jExit] >= xExitPlane:
            characteristicSlope = (straighteningR[iExit+1,jExit] - straighteningR[iExit,jExit]) / (straighteningX[iExit+1,jExit] - straighteningX[iExit,jExit])
            characteristicYIntercept = straighteningR[iExit,jExit] - characteristicSlope * straighteningX[iExit,jExit]
            rExitPlane[index] = characteristicSlope * xExitPlane + characteristicYIntercept
            machNumberExitPlane[index] = straighteningMach[iExit,jExit] + (straighteningMach[iExit+1,jExit] - straighteningMach[iExit,jExit]) / \
                                            (straighteningX[iExit+1,jExit] - straighteningX[iExit,jExit]) * (xExitPlane - straighteningX[iExit,jExit])
            flowAngleExitPlane[index] = straighteningFlowAngle[iExit,jExit] + (straighteningFlowAngle[iExit+1,jExit]-straighteningFlowAngle[iExit,jExit]) / \
                                        (straighteningX[iExit+1,jExit] - straighteningX[iExit,jExit]) * (xExitPlane - straighteningX[iExit,jExit])
            jExit -= 1
        else:
            characteristicSlope = (straighteningR[iExit+1,jExit+1] - straighteningR[iExit+1,jExit]) / (straighteningX[iExit+1,jExit+1] - straighteningX[iExit+1,jExit])
            characteristicYIntercept = straighteningR[iExit+1,jExit] - characteristicSlope * straighteningX[iExit+1,jExit]
            rExitPlane[index] = characteristicSlope * xExitPlane + characteristicYIntercept
            machNumberExitPlane[index] = straighteningMach[iExit+1,jExit] + (straighteningMach[iExit+1,jExit+1] - straighteningMach[iExit+1,jExit]) / \
                                            (straighteningX[iExit+1,jExit+1] - straighteningX[iExit+1,jExit]) * (xExitPlane - straighteningX[iExit+1,jExit])
            flowAngleExitPlane[index] = straighteningFlowAngle[iExit+1,jExit] + (straighteningFlowAngle[iExit+1,jExit+1] - straighteningFlowAngle[iExit+1,jExit]) / \
                                        (straighteningX[iExit+1,jExit+1] - straighteningX[iExit+1,jExit]) * (xExitPlane - straighteningX[iExit+1,jExit])
            iExit += 1

    if expansionX[-1,-1] >= xExitPlane:
        offset = (numContourElements - 1) - iExit
        kernelRows, kernelCols = expansionX.shape
        iExit = kernelRows - offset - 1
        jExit = kernelCols - 2

        while not terminated:

            index += 1

            # Check for centerline intercept
            if abs(expansionR[iExit+1,jExit]) < 1e-3:
                terminated = True

            if expansionX[iExit+1,jExit] >= xExitPlane:
                characteristicSlope = (expansionR[iExit+1,jExit]-expansionR[iExit,jExit]) / (expansionX[iExit+1,jExit] - expansionX[iExit,jExit])
                characteristicYIntercept = expansionR[iExit,jExit] - characteristicSlope * expansionX[iExit,jExit]
                rExitPlane[index] = characteristicSlope * xExitPlane + characteristicYIntercept
                machNumberExitPlane[index] = expansionMach[iExit,jExit] + (expansionMach[iExit+1,jExit] - expansionMach[iExit,jExit]) / \
                                                (expansionX[iExit+1,jExit] - expansionX[iExit,jExit]) * (xExitPlane - expansionX[iExit,jExit])
                flowAngleExitPlane[index] = expansionFlowAngle[iExit,jExit] + (expansionFlowAngle[iExit+1,jExit] - expansionFlowAngle[iExit,jExit]) / \
                                            (expansionX[iExit+1,jExit] - expansionX[iExit,jExit]) * (xExitPlane - expansionX[iExit,jExit])
                jExit -= 1
            else:
                characteristicSlope = (expansionR[iExit+1,jExit+1] - expansionR[iExit+1,jExit]) / (expansionX[iExit+1,jExit+1] - expansionX[iExit+1,jExit])
                characteristicYIntercept = expansionR[iExit+1,jExit] - characteristicSlope * expansionX[iExit+1,jExit]
                rExitPlane[index] = characteristicSlope * xExitPlane + characteristicYIntercept
                machNumberExitPlane[index] = expansionMach[iExit+1,jExit] + (expansionMach[iExit+1,jExit+1] - expansionMach[iExit+1,jExit]) / \
                                                (expansionX[iExit+1,jExit+1] - expansionX[iExit+1,jExit]) * (xExitPlane - expansionX[iExit+1,jExit])
                flowAngleExitPlane[index] = expansionFlowAngle[iExit+1,jExit] + (expansionFlowAngle[iExit+1,jExit+1] - expansionFlowAngle[iExit+1,jExit]) / \
                                            (expansionX[iExit+1,jExit+1] - expansionX[iExit+1,jExit]) * (xExitPlane - expansionX[iExit+1,jExit])
                iExit += 1

    # Truncate unused elements
    rExitPlane = rExitPlane[:index]
    machNumberExitPlane = machNumberExitPlane[:index]
    flowAngleExitPlane = flowAngleExitPlane[:index]

    # The walk descends through the mesh from the wall and runs out of columns before it
    # reaches the axis, typically around a quarter of the exit radius. That leaves a core
    # carrying roughly eight percent of the exit AREA unsampled, and because the thrust
    # integral below weights by area over the FULL exit area, an unsampled core subtracts
    # directly from the thrust coefficient rather than showing up as a gap.
    #
    # The plane is closed on the axis instead. Flow angle is zero there by symmetry, and the
    # Mach number is extrapolated from the two innermost sampled points, which sit in the part
    # of the plane where the profile is flattest. `exitPlaneSampledFraction` records how much
    # of the plane the mesh actually supplied, so the size of the closure stays visible.
    state.exitPlaneSampledFraction = float(1.0 - (rExitPlane[-1] / rExitPlane[0]) ** 2)
    if rExitPlane[-1] > 1e-12 and len(rExitPlane) >= 2:
        slope = ((machNumberExitPlane[-1] - machNumberExitPlane[-2])
                 / (rExitPlane[-1] - rExitPlane[-2]))
        axisMach = machNumberExitPlane[-1] - slope * rExitPlane[-1]
        rExitPlane = np.append(rExitPlane, 0.0)
        machNumberExitPlane = np.append(machNumberExitPlane, axisMach)
        flowAngleExitPlane = np.append(flowAngleExitPlane, 0.0)
        index += 1

    return rExitPlane, machNumberExitPlane, flowAngleExitPlane

def sampleExitPlaneByScan(state: ContourSolution, blocks: list, xExitPlane: float) -> tuple:

    '''

    The flow across the exit plane, read off the mesh by scanning cell edges rather than walking
    indices.

    Every edge of every cell is tested for straddling the exit station, and the state is
    interpolated along the ones that do. It knows nothing about how the mesh was built, which is
    the point: `sampleExitPlaneByWalk` encodes the truncated ideal contour's own traversal in its
    staircase, and a family that marches the other way needs a sampler that does not care.

    It also samples the plane about twice as densely, because a cell that straddles the station
    usually does so on two of its edges, and it needs no closure on the axis. The walk needs one
    because it runs out of columns partway down; a wall-bounded march carries every line from the
    wall to the axis, so the plane is covered.

    Parameters:
    -----------
    state : ContourSolution
        Workspace. `exitPlaneSampledFraction` is written to it.
    blocks : list
        (x, r, mach, flowAngle) for each mesh block. NaN padding is skipped.
    xExitPlane : float
        Axial station of the exit plane, non-dimensional.

    Returns:
    --------
    tuple : (radius, mach, flowAngle) ordered from the wall inward to the axis

    '''

    radius, mach, flowAngle = [], [], []

    for blockX, blockR, blockMach, blockAngle in blocks:

        # Along a line, then between lines. Together these are every edge of every cell.
        for first, second in ((np.s_[:-1, :], np.s_[1:, :]), (np.s_[:, :-1], np.s_[:, 1:])):

            xStart, xEnd = blockX[first], blockX[second]
            usable = np.isfinite(xStart) & np.isfinite(xEnd) & \
                     np.isfinite(blockR[first]) & np.isfinite(blockR[second])

            aheadOfPlane = xStart - xExitPlane
            behindPlane  = xEnd - xExitPlane
            straddles = usable & (np.sign(aheadOfPlane) != np.sign(behindPlane))

            span = xEnd - xStart
            straddles &= np.abs(span) > 1e-15
            if not np.any(straddles):
                continue

            fraction = np.zeros_like(xStart)
            fraction[straddles] = (aheadOfPlane[straddles] / (aheadOfPlane - behindPlane)[straddles])

            interpolate = lambda array: (array[first] + fraction * (array[second] - array[first]))[straddles]
            radius.append(interpolate(blockR))
            mach.append(interpolate(blockMach))
            flowAngle.append(interpolate(blockAngle))

    if not radius:
        raise ValueError(f'No part of the mesh reaches the exit plane at x = {xExitPlane}.')

    radius    = np.concatenate(radius)
    mach      = np.concatenate(mach)
    flowAngle = np.concatenate(flowAngle)

    # Ordered from the wall inward, which is the convention the thrust integral reads.
    order = np.argsort(-radius)
    radius, mach, flowAngle = radius[order], mach[order], flowAngle[order]

    # A cell that straddles the plane on two edges contributes the same point twice.
    keep = np.concatenate([[True], np.abs(np.diff(radius)) > 1e-12])
    radius, mach, flowAngle = radius[keep], mach[keep], flowAngle[keep]

    state.exitPlaneSampledFraction = float(1.0 - (radius[-1] / radius[0]) ** 2)
    return radius, mach, flowAngle

def exitPlaneThrustCoefficient(state: ContourSolution, rExitPlane: np.ndarray,
                               machNumberExitPlane: np.ndarray, flowAngleExitPlane: np.ndarray,
                               stagnationPressure = None) -> tuple:

    '''

    Thrust coefficient from a sampled exit plane, and the plane's own averages.

    The momentum theorem over a control volume whose downstream face is the exit plane. The plane
    is not uniform on any contour NOVA builds, so it is integrated station by station rather than
    collapsed to a single exit state, and the averages that collapse fall out of the same integral.

    `stagnationPressure` is an array rather than a number so that a contour carrying an internal
    shock can hand over a per-node stagnation pressure, the streamlines that crossed the shock
    having lost some. None takes the chamber value everywhere, which is every shock-free family.

    Parameters:
    -----------
    state : ContourSolution
        Workspace supplying the chamber state and the throat. The exit-plane fields and the mass
        closure are written to it.
    rExitPlane, machNumberExitPlane, flowAngleExitPlane : np.ndarray
        The plane, ordered from the wall inward to the axis.
    stagnationPressure : ArrayLike | None
        Stagnation pressure at each station of the plane [Pa]. None uses the chamber value.

    Returns:
    --------
    tuple : (velocityTermThrustCoef, pressureTermThrustCoef)

    '''

    if stagnationPressure is None:
        stagnationPressure = state.chamberPressure

    numStations  = len(rExitPlane)
    exitPressure = np.zeros(numStations)
    _, exitPressure[0], _ = isentropicValues(machNumberExitPlane[0], state.chamberStagnationTemperature,
                                             np.asarray(stagnationPressure).flat[0]
                                             if np.ndim(stagnationPressure) else stagnationPressure,
                                             state.chamberGamma, state.chamberRGasConstant)

    velocityTermThrustCoef, pressureTermThrustCoef = 0, 0

    for i in range(numStations - 1):

        differentialCSArea = np.pi * (rExitPlane[i]**2 - rExitPlane[i+1]**2)
        stationStagnation  = (stagnationPressure[i+1] if np.ndim(stagnationPressure)
                              else stagnationPressure)
        _, exitPressure[i+1], _ = isentropicValues(machNumberExitPlane[i+1], state.chamberStagnationTemperature,
                                                   stationStagnation, state.chamberGamma, state.chamberRGasConstant)
        averagePressureBetweenNodes  = (exitPressure[i+1] + exitPressure[i]) / 2
        averageFlowAngleBetweenNodes = (flowAngleExitPlane[i+1] + flowAngleExitPlane[i]) / 2

        # Axial momentum flux through the strip, as the momentum theorem writes it:
        #
        #     integral of rho u^2 cos^2(theta) dA
        #
        # Two cosines, and both are needed. One resolves the mass actually crossing the plane,
        # since only the axial component of the velocity carries flow through it; the other
        # takes the axial component of the momentum that mass carries. Using a single cosine
        # over-credits a diverging strip, and because the exit angle falls as a contour is
        # truncated further out, that error grows with truncation and moves the apparent
        # optimum. On the worked contour it put the peak thrust coefficient at an area ratio
        # of 14.0 against a true 12.6.
        averageMachBetweenNodes = 0.5 * (machNumberExitPlane[i] + machNumberExitPlane[i+1])
        localTemperature = state.chamberStagnationTemperature \
            / (1 + 0.5 * (state.chamberGamma - 1) * averageMachBetweenNodes**2)
        localDensity = averagePressureBetweenNodes / (state.chamberRGasConstant * localTemperature)
        localVelocity = averageMachBetweenNodes * np.sqrt(state.chamberGamma
                                                          * state.chamberRGasConstant
                                                          * localTemperature)
        velocityTermThrustCoef += (localDensity * localVelocity**2
                                   * np.cos(averageFlowAngleBetweenNodes)**2
                                   * differentialCSArea) \
                                  / (state.chamberPressure * np.pi * state.throatRadiusNonDimensional**2)

        # Take summation of pressure term in thrust coefficient
        # The thrust coefficient normalizes by the throat AREA, pi rt^2, which is where the
        # exponent belongs. Written as rt * 2 this divided by 2 pi rt instead and halved the
        # pressure term, since the non-dimensional throat radius is 1.
        pressureTermThrustCoef += (averagePressureBetweenNodes - state.targetExitPressure) * differentialCSArea / \
                (state.chamberPressure * np.pi * state.throatRadiusNonDimensional**2)

    # The exit plane is the only place the solve knows what the whole flow is doing rather
    # than what the wall is doing, so it is kept. The area average is what the thrust
    # coefficient is built from; the mass average is what an exit pressure ought to be matched
    # against, since matching the wall alone drives one station of a non-uniform plane.
    state.exitPlaneRadius    = rExitPlane
    state.exitPlaneMach      = machNumberExitPlane
    state.exitPlaneFlowAngle = flowAngleExitPlane
    state.exitPlanePressure  = exitPressure
    state.exitAreaAveragedPressure = float(
        np.trapezoid(exitPressure[::-1] * rExitPlane[::-1], rExitPlane[::-1])
        / np.trapezoid(rExitPlane[::-1], rExitPlane[::-1]))
    massFlux = (exitPressure / (state.chamberRGasConstant
                                * (state.chamberStagnationTemperature
                                   / (1 + 0.5 * (state.chamberGamma - 1) * machNumberExitPlane**2)))
                * machNumberExitPlane
                * np.sqrt(state.chamberGamma * state.chamberRGasConstant
                          * state.chamberStagnationTemperature
                          / (1 + 0.5 * (state.chamberGamma - 1) * machNumberExitPlane**2))
                * np.cos(flowAngleExitPlane))
    weight = massFlux[::-1] * rExitPlane[::-1]
    state.exitMassAveragedPressure = float(
        np.trapezoid(exitPressure[::-1] * weight, rExitPlane[::-1])
        / np.trapezoid(weight, rExitPlane[::-1]))
    state.exitMassFlux = float(2.0 * np.pi * np.trapezoid(weight, rExitPlane[::-1]))

    # Mass through the exit plane against the one-dimensional choked throat flow.
    #
    # This does NOT converge to one, and reading a departure from one as solver error is wrong.
    # `chokedFlow` below assumes a flat sonic line. The real one is curved by the throat, the
    # solve carries that curvature from its transonic start line, and the flow it delivers is
    # correspondingly less: this is the throat discharge coefficient, and it is physics rather
    # than discretization.
    #
    # Measured on the kernel's own downstream boundary, which reaches the axis and so is not
    # truncated, the deficit is 2.04 per cent at the shipped outlet curvature of 0.382 throat
    # radii, 1.55 at 0.75 and 0.92 at 1.5. It falls monotonically as the throat flattens, which
    # is the signature. All three contoured families carry it identically, 0.9787 to 0.9798,
    # because they share the kernel.
    #
    # What is left after it IS a quality measure, and it is the part that differs by family: a
    # further 0.5 per cent for the truncated ideal contour, whose sampler leaves eight per cent
    # of the exit area to a linear closure, against 1.5 to 1.8 for the optimized families, whose
    # exit plane is fully sampled and whose loss is in the forward march and its sampling.
    chokedFlow = (state.chamberPressure * np.pi * state.throatRadiusNonDimensional ** 2
                  * np.sqrt(state.throatGamma
                            / (state.chamberRGasConstant * state.chamberStagnationTemperature)
                            * (2 / (state.throatGamma + 1))
                            ** ((state.throatGamma + 1) / (state.throatGamma - 1))))
    state.exitMassClosure = float(state.exitMassFlux / chokedFlow)

    return velocityTermThrustCoef, pressureTermThrustCoef

def finishContourSolution(state: ContourSolution, xNozzleWall: np.ndarray,
                          rNozzleWall: np.ndarray, machNumberNozzleWall: np.ndarray,
                          wallExitPressure: float, thrustCoef: float,
                          assignOutputsToObject: bool = False,
                          splineMethod: str = 'curvatureContinuous') -> None:

    '''

    Resample a solved wall, derive the near-wall state on it, and measure what it delivered.

    The last step of every family. It takes the raw wall the solve produced, at whatever spacing
    the mesh happened to land on, and returns an evenly spaced contour in meters with the four
    near-wall arrays beside it and the delivered design point measured off the result.

    Only the Mach number is interpolated onto the resampled wall. Temperature, pressure and
    velocity are isentropic functions of it at fixed stagnation conditions, so deriving them here
    makes the four arrays consistent with each other by construction. Interpolating all four
    independently leaves them satisfying the relation they came from only where it happens to be
    linear, and near the throat it is not.

    `s = 0` makes the near-wall spline interpolate. Without it `UnivariateSpline` smooths, and its
    default smoothing factor is an absolute residual budget of one per data point, so what happens
    to an array depends on the magnitude of its values rather than on its shape. Pressure in
    pascals comes through untouched; Mach number, being of order one, is fitted by a single
    straight line through the whole wall.

    Parameters:
    -----------
    state : ContourSolution
        Workspace. The wall, the near-wall arrays and the delivered quantities are written to it.
    xNozzleWall, rNozzleWall : np.ndarray
        The raw wall as the solve produced it, non-dimensional against the throat radius.
    machNumberNozzleWall : np.ndarray
        Near-wall Mach number at those same raw stations [-].
    wallExitPressure : float
        Wall static pressure at the last station, for the pressure residual [Pa].
    thrustCoef : float
        Thrust coefficient the exit-plane integral produced [-].
    assignOutputsToObject : bool
        True also computes the characteristic velocities and writes the wall and near-wall arrays.
        False computes only what a design-point residual needs.
    splineMethod : str
        Passed to `arcSpline`. A truncated ideal wall is smooth by construction and takes
        `'curvatureContinuous'`. A wall with a curvature discontinuity in it, which is every wall
        built from an arc joined to a curve, takes `'shapePreserving'`: a C2 cubic through a corner
        must overshoot, and on a stitched contour that overshoot is geometry the solve never
        produced. See `docs/reports/arcSplineOvershoot_2026-09-08.md`.

    '''

    # Spline over the non-dimensional wall and make the points evenly spaced along its arc length.
    xNozzleWallOld, rNozzleWallOld = xNozzleWall, rNozzleWall
    xNozzleWall, rNozzleWall = arcSpline(xNozzleWallOld, rNozzleWallOld,
                                         newNumPoints = state.numContourPoints,
                                         method = splineMethod)

    # Scale the nozzle coordinates into real space
    xNozzleWallScaled, rNozzleWallScaled = xNozzleWall * state.nozzleScalingFactor, rNozzleWall * state.nozzleScalingFactor

    nozzleNearWallMachNumber  = UnivariateSpline(xNozzleWallOld, machNumberNozzleWall,  k = 1, s = 0)(xNozzleWall)
    nozzleNearWallTemperature, nozzleNearWallPressure, nozzleNearWallVelocity \
        = isentropicValues(nozzleNearWallMachNumber, state.chamberStagnationTemperature,
                           state.chamberPressure, state.chamberGamma, state.chamberRGasConstant)

    if assignOutputsToObject:

        # Calculate delivered characteristic velocity and theoretical characteristic velocity
        state.throatArea                        = np.pi * min(rNozzleWallScaled)**2
        state.theoreticalCharacteristicVelocity = state.chamberPressure * state.throatArea / state.engineMassFlow
        state.deliveredCharacteristicVelocity   = state.ambientSpecificImpulse * 9.81 / thrustCoef

        # Assign calculated properties to object
        state.xNozzleWallDivergingNonDimensional = xNozzleWall
        state.rNozzleWallDivergingNonDimensional = rNozzleWall
        state.xNozzleWall                        = xNozzleWallScaled
        state.rNozzleWall                        = rNozzleWallScaled
        state.nozzleNearWallTemperature          = nozzleNearWallTemperature
        state.nozzleNearWallPressure             = nozzleNearWallPressure
        state.nozzleNearWallVelocity             = nozzleNearWallVelocity
        state.nozzleNearWallMachNumber           = nozzleNearWallMachNumber
        state.thrustCoef                         = thrustCoef

    # Every figure of merit is always reported. Which one the caller is steering on is the
    # caller's business, and returning only one of them is what made the two hard to compare.
    state.thrustCoef    = thrustCoef
    state.pressureError = abs(wallExitPressure - state.targetExitPressure)

    # What the contour delivered. These are measured off the wall that was built, so a design that
    # misses what it was asked for says so rather than reporting the request back.
    throatIndex = int(np.argmin(rNozzleWall))
    state.deliveredAreaRatio = float((rNozzleWall[-1] / rNozzleWall[throatIndex]) ** 2)
    state.deliveredLengthFraction = float((xNozzleWall[-1] - xNozzleWall[throatIndex])
                                          / conicalLength(state.deliveredAreaRatio,
                                                          rNozzleWall[throatIndex]))
    state.inflectionWallAngle, state.exitWallAngle, _ = wallAnglesFromContour(
        xNozzleWall[throatIndex:], rNozzleWall[throatIndex:])

def truncatedIdealContour(state: ContourSolution, targetExitMach: float, lengthFraction: float,
                          truncate: bool = False,
                          assignOutputsToObject: bool = False) -> ContourSolution:

    '''

    Solve a truncated ideal contour and the performance that follows from it.

    The algorithm:

    - Place the Rao throat arc and take the design inflection angle as a quarter of the
      Prandtl-Meyer angle at the target exit Mach number.
    - Draw the limiting characteristic from Sauer's transonic solution and use it as the starting
      line, because a march cannot begin at the throat where the characteristics are degenerate.
    - Build the throat kernel out to the wall, then the inner expansion kernel down to the axis.
    - Build the flow-straightening kernel against a uniform, axial exit line.
    - Trace the wall as the streamline that carries the flow from the kernel to that exit, and
      truncate it at the requested area ratio.
    - Integrate the exit plane for the thrust coefficient, accounting for the flow angle and the
      pressure at every station rather than assuming a uniform exit.

    Parameters:
    -----------
    state : ContourSolution
        Workspace carrying the chamber state and geometry. Filled in and returned.
    targetExitMach : float
        Exit Mach number the ideal nozzle is designed to before truncation [-].
    lengthFraction : float
        Truncation length as a fraction of the 15 degree conical reference [-].
    truncate : bool
        True cuts the wall at the requested area ratio. False runs the wall out to the end of
        the mesh, which is the untruncated ideal contour.
    assignOutputsToObject : bool
        True computes the mesh blocks, the near-wall arrays and the derived performance. False
        computes only what the figures of merit need, which is what the design Mach number
        search iterates on.

    Returns:
    --------
    ContourSolution
        The same workspace, with `thrustCoef` and `pressureError` always set.

    '''

    gas, throat = state.gas, state.throat

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    # -- TIC Helper functions -- #
    #-----------------------------------------------------------------------------------------------------------------------------------------#

    def calculateWallPoints(upstreamPoints: tuple, machNumber: np.ndarray, flowAngle: np.ndarray, xPoints: np.ndarray, rPoints: np.ndarray, iteratorContour: int, jteratorContour: int) -> tuple:

        '''
        
        This function takes in the arrays of required MoC kernel properties and calculates the wall point
        for the given contour (i, j) iterators.

        The math that determines the wall point location is not well understood, but current working theory is that
        the wall point is calculated based on characteristic continuity which defines the term 'eta' and the subsequent
        quadratic expression that is solved for the wall query points (only one of which is ever a valid solution).

        The valid solution is assumed to be a valid streamline through the supersonic expanding flow.
        
        '''

        # Initialize booleans
        reachedEndOfMachNet, terminated = False, False

        # Unpack initial point values
        upstreamX, upstreamR, upstreamFlowAngle = [stuff for stuff in upstreamPoints]

        # Define characteristic mesh points that will create bounding boxes for wall point
        downstreamX, downstreamR, downstreamFlowAngle, downstreamMachNumber \
        = [w for w in [xPoints[iteratorContour+1,jteratorContour+1], rPoints[iteratorContour+1,jteratorContour+1], \
                        flowAngle[iteratorContour+1,jteratorContour+1], machNumber[iteratorContour+1,jteratorContour+1]]]

        leftRunningX, leftRunningR, leftRunningFlowAngle, leftRunningMachNumber \
        = [v1 for v1 in [xPoints[iteratorContour,jteratorContour+1], rPoints[iteratorContour,jteratorContour+1], \
                            flowAngle[iteratorContour,jteratorContour+1], machNumber[iteratorContour,jteratorContour+1]]]

        rightRunningX, rightRunningR, rightRunningFlowAngle, rightRunningMachNumber \
        = [v2 for v2 in [xPoints[iteratorContour+1,jteratorContour], rPoints[iteratorContour+1,jteratorContour], \
                            flowAngle[iteratorContour+1,jteratorContour], machNumber[iteratorContour+1,jteratorContour]]]

        # Find potential wall points using left running characteristic mesh point
        etaLeftRunning1 = (upstreamX + downstreamX) + (2 * (leftRunningR - downstreamR) - (leftRunningX - downstreamX) * \
                           (np.tan(upstreamFlowAngle) + np.tan(downstreamFlowAngle))) / \
                           (np.tan(leftRunningFlowAngle) - np.tan(downstreamFlowAngle))
        etaLeftRunning2 = (upstreamX * downstreamX) + (2 * (leftRunningX - downstreamX) * (upstreamR - downstreamR) + 2 * \
                           (leftRunningR - downstreamR) * downstreamX - upstreamX * (leftRunningX - downstreamX) * \
                           (np.tan(upstreamFlowAngle) + np.tan(downstreamFlowAngle))) / (np.tan(leftRunningFlowAngle) - np.tan(downstreamFlowAngle))

        xQueryLeftRunning1 = (etaLeftRunning1 + np.sqrt(etaLeftRunning1**2 - 4 * etaLeftRunning2)) / 2
        xQueryLeftRunning2 = (etaLeftRunning1 - np.sqrt(etaLeftRunning1**2 - 4 * etaLeftRunning2)) / 2
        rQueryLeftRunning1 = downstreamR + (leftRunningR - downstreamR) * (xQueryLeftRunning1 - downstreamX) / (leftRunningX - downstreamX)
        rQueryLeftRunning2 = downstreamR + (leftRunningR - downstreamR) * (xQueryLeftRunning2 - downstreamX) / (leftRunningX - downstreamX)

        # Find potential wall points using right running characteristic mesh point
        etaRightRunning1 = (upstreamX + downstreamX) + (2 * (rightRunningR - downstreamR) - (rightRunningX - downstreamX) * \
                                            (np.tan(upstreamFlowAngle) + np.tan(downstreamFlowAngle))) / \
                                            (np.tan(rightRunningFlowAngle) - np.tan(downstreamFlowAngle))
        etaRightRunning2 = upstreamX * downstreamX + (2 * (rightRunningX - downstreamX) * (upstreamR - downstreamR) + 2 * (rightRunningR - downstreamR) * \
                    downstreamX - upstreamX * (rightRunningX - downstreamX) * (np.tan(upstreamFlowAngle) + np.tan(downstreamFlowAngle))) / \
                    (np.tan(rightRunningFlowAngle) - np.tan(downstreamFlowAngle))
        xQueryRightRunning1 = (etaRightRunning1 + np.sqrt(etaRightRunning1**2 - 4 * etaRightRunning2)) / 2
        xQueryRightRunning2 = (etaRightRunning1 - np.sqrt(etaRightRunning1**2 - 4 * etaRightRunning2)) / 2
        rQueryRightRunning1 = downstreamR + (rightRunningR - downstreamR) * (xQueryRightRunning1 - downstreamX) / (rightRunningX - downstreamX)
        rQueryRightRunning2 = downstreamR + (rightRunningR - downstreamR) * (xQueryRightRunning2 - downstreamX) / (rightRunningX - downstreamX)

        # Check if any query points fall within the bounding boxes
        # Point 1:
        if (xQueryLeftRunning1 >= min(downstreamX, leftRunningX)) and (xQueryLeftRunning1 <= max(downstreamX, leftRunningX)) and \
            (rQueryLeftRunning1 >= min(downstreamR, leftRunningR)) and (rQueryLeftRunning1 <= max(downstreamR, leftRunningR)):
            xQuery, rQuery, newUpstreamR, newUpstreamFlowAngle, newUpstreamMachNumber = \
            xQueryLeftRunning1, rQueryLeftRunning1, leftRunningR, leftRunningFlowAngle, leftRunningMachNumber
            jteratorContour += 1
        # Point 2
        elif (xQueryLeftRunning2 >= min(downstreamX, leftRunningX)) and (xQueryLeftRunning2 <= max(downstreamX, leftRunningX)) and \
                (rQueryLeftRunning2 >= min(downstreamR, leftRunningR)) and (rQueryLeftRunning2 <= max(downstreamR, leftRunningR)):
            xQuery, rQuery, newUpstreamR, newUpstreamFlowAngle, newUpstreamMachNumber = \
            xQueryLeftRunning2, rQueryLeftRunning2, leftRunningR, leftRunningFlowAngle, leftRunningMachNumber
            jteratorContour += 1
        # Point 3
        elif (xQueryRightRunning1 >= min(downstreamX, rightRunningX)) and (xQueryRightRunning1 <= max(downstreamX, rightRunningX)) and \
                (rQueryRightRunning1 >= min(downstreamR, rightRunningR)) and (rQueryRightRunning1 <= max(downstreamR, rightRunningR)):
            xQuery, rQuery, newUpstreamR, newUpstreamFlowAngle, newUpstreamMachNumber = \
            xQueryRightRunning1, rQueryRightRunning1, rightRunningR, rightRunningFlowAngle, rightRunningMachNumber
            iteratorContour += 1
        # Point 4
        elif (xQueryRightRunning2 >= min(downstreamX, rightRunningX)) and (xQueryRightRunning2 <= max(downstreamX, rightRunningX)) and \
                (rQueryRightRunning2 >= min(downstreamR, rightRunningR)) and (rQueryRightRunning2 <= max(downstreamR, rightRunningR)):
            xQuery, rQuery, newUpstreamR, newUpstreamFlowAngle, newUpstreamMachNumber = \
            xQueryRightRunning2, rQueryRightRunning2, rightRunningR, rightRunningFlowAngle, rightRunningMachNumber
            iteratorContour += 1
        # Otherwise, assume that we’ve reached the end of the mesh before reaching the design envelope
        else:
            xQuery, rQuery = 0, 0
            newUpstreamR, newUpstreamFlowAngle, newUpstreamMachNumber = downstreamR, downstreamFlowAngle, downstreamMachNumber
            reachedEndOfMachNet = True
            terminated = True

        downstreamPoint  = [downstreamR, downstreamFlowAngle, downstreamMachNumber]
        newUpstreamPoint = [newUpstreamR, newUpstreamFlowAngle, newUpstreamMachNumber]

        return xQuery, rQuery, downstreamPoint, newUpstreamPoint, iteratorContour, jteratorContour, reachedEndOfMachNet, terminated

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    # -- TIC Algorithm Setup -- #
    #-----------------------------------------------------------------------------------------------------------------------------------------#

    # Initially for looping we need to increment the desired number of characteristics by 1
    # Characteristics launched from the throat arc. This is the mesh resolution of the whole solve,
    # and until it is swept the delivered contour has no claim on its own digits.
    state.numCharacteristics   = state.numCharacteristicsRequested + 1

    # Isentropic relation for ideally expanded mach number
    # Where the wall is cut: at the requested area ratio, which is the method NASA SP-8120
    # attributes to Ahlberg. A requested exit pressure reaches this the same way, having already
    # become an equivalent area ratio through the one-dimensional CEA relation before the contour
    # is drawn.
    targetWallRadius = np.sqrt(state.requestedAreaRatio) * state.throatRadiusNonDimensional

    # The length reference: a 15 degree half-angle cone of the SAME AREA RATIO, which is how NASA
    # SP-8120 defines percent bell. Taking it from the requested area ratio rather than from a
    # one-dimensional Mach number matters: at this operating point the two differ by 12 percent in
    # length, because the ideal Mach number is a perfect-gas inverse of a pressure that CEA
    # computed with equilibrium chemistry, and the area ratio it corresponds to is 48.5 rather than
    # the 40 that was asked for.
    referenceConeLength    = conicalLength(state.requestedAreaRatio, state.throatRadiusNonDimensional)
    state.referenceConeLength = referenceConeLength

    # Calculate scaling factor (to revert back to real units after the non-dimensional design process)
    state.nozzleScalingFactor = throatScalingFactor(state.engineMassFlow, state.chamberPressure,
                                                   state.throatGamma, state.chamberRGasConstant,
                                                   state.chamberStagnationTemperature)

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    # -- Starting Line and Kernel -- #
    #-----------------------------------------------------------------------------------------------------------------------------------------#

    # Rao's throat assumption: the diverging throat arc ends at a fixed fraction of the
    # Prandtl-Meyer angle at the design exit Mach number, and that fraction is one quarter. It is
    # the truncated ideal contour's choice, and it is the only thing about the kernel that is this
    # family's rather than every family's, which is why it is the one kernel input a caller can
    # move. The prescribed-wall families do not read it: their arc ends at the inflection angle
    # their own wall was drawn to.
    angleOfInflection = state.initialWallAngleFraction * prandtlMeyerAngle(targetExitMach,
                                                                           state.chamberGamma)

    kernel = solveKernel(gas, throat, state.numCharacteristics, angleOfInflection,
                         state.chamberPressure)

    throatKernelMach, throatKernelFlowAngle    = kernel['throatKernelMach'], kernel['throatKernelFlowAngle']
    throatKernelX, throatKernelR               = kernel['throatKernelX'], kernel['throatKernelR']
    expansionKernelMach, expansionKernelFlowAngle = kernel['expansionKernelMach'], kernel['expansionKernelFlowAngle']
    expansionKernelX, expansionKernelR         = kernel['expansionKernelX'], kernel['expansionKernelR']
    limitingCharacteristicX                    = kernel['limitingCharacteristicX']
    limitingCharacteristicR                    = kernel['limitingCharacteristicR']
    throatWallX, throatWallR                   = kernel['throatWallX'], kernel['throatWallR']
    throatWallMach, throatWallTemperature      = kernel['throatWallMach'], kernel['throatWallTemperature']
    throatWallPressure, throatWallVelocity     = kernel['throatWallPressure'], kernel['throatWallVelocity']
    numRows, idealMeshSpacing                  = kernel['numRows'], kernel['idealMeshSpacing']

    state.throatWallX, state.throatWallR = throatWallX, throatWallR
    state.throatWallAngles = kernel['throatWallAngles']
    state.throatEndAngle = kernel['throatWallAngles'][-1]

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    # -- Calculate Wall Points using Flow Straightening Section Kernel -- #
    #-----------------------------------------------------------------------------------------------------------------------------------------#

    # print(f'Generating Flow Straightening Kernel and Calculating Wall Points')

    numContourElements = state.numCharacteristics + idealMeshSpacing

    calculatedExitMach = expansionKernelMach[-1,-1]
    exitCharacteristicSlope = np.tan(np.arcsin(1 / calculatedExitMach))

    # Calculate resultant exit radius based on quasi 1D compressible flow theory
    calculatedExitRadius = radiusMachRelation(calculatedExitMach, state.chamberGamma)
    calculatedExitLength = calculatedExitRadius / exitCharacteristicSlope + expansionKernelX[-1,-1]

    # Store for animation data export
    state.calculatedExitRadius = calculatedExitRadius
    state.calculatedExitMach = calculatedExitMach

    exitRadiusArray = np.linspace(calculatedExitRadius / numRows, calculatedExitRadius, numContourElements - 2)
    exitAxisArray   = np.linspace((calculatedExitRadius / exitCharacteristicSlope) / numRows + expansionKernelX[-1,-1], calculatedExitLength, numContourElements - 2)

    # Initialize arrays for MoC contour generation and arrays to hold nozzle wall values
    flowStraighteningMachNumber, flowStraighteningFlowAngle, \
    flowStraighteningX, flowStraighteningR \
    = [np.zeros((numContourElements - 1, numContourElements - 1)) for _ in range(4)]
    xNozzleWall, rNozzleWall, \
    temperatureNozzleWall, pressureNozzleWall, \
    velocityNozzleWall, machNumberNozzleWall \
    = [np.zeros(4 * numContourElements) for _ in range(6)]

    # Fill in kernel and exit conditions
    flowStraighteningMachNumber[:,0], flowStraighteningFlowAngle[:,0], flowStraighteningX[:,0], flowStraighteningR[:,0] \
    = [kernelStuff for kernelStuff in [expansionKernelMach[numRows - numContourElements + 1:,-1], expansionKernelFlowAngle[numRows - numContourElements + 1:,-1], \
                                        expansionKernelX[numRows - numContourElements + 1:,-1], expansionKernelR[numRows - numContourElements + 1:,-1]]]

    flowStraighteningMachNumber[-1, 1:] = calculatedExitMach * np.ones(numContourElements - 2)
    flowStraighteningX[-1, 1:], flowStraighteningR[-1, 1:] \
    = [stuff for stuff in [exitAxisArray, exitRadiusArray]]

    # Fill in initial points for wall arrays
    xNozzleWall[0], rNozzleWall[0] = flowStraighteningX[0,0], flowStraighteningR[0,0]

    # -- Calculate wall points -- #

    # Store initial values
    upstreamMachNumber, upstreamFlowAngle, \
    upstreamX, upstreamR \
    = flowStraighteningMachNumber[0,0], flowStraighteningFlowAngle[0,0], flowStraighteningX[0,0], flowStraighteningR[0,0]

    # Store information needed for loop
    iContour, jContour, iContourPrevious, jContourPrevious, jMesh = 0, 0, 0, 0, 0
    index = 0
    terminated = False

    # Main flow straightening mesh and wall point calculation loop
    while iContour <= 2 * numContourElements - 2 and jContour <= 2 * numContourElements - 2 and not terminated:

        if jMesh <= jContour:

            for i in reversed(np.arange(iContour, numContourElements - 2)):
                axMOCKernel = [flowStraighteningMachNumber[i,jMesh],     flowStraighteningFlowAngle[i,jMesh],     flowStraighteningX[i,jMesh],     flowStraighteningR[i,jMesh], \
                                flowStraighteningMachNumber[i+1,jMesh+1], flowStraighteningFlowAngle[i+1,jMesh+1], flowStraighteningX[i+1,jMesh+1], flowStraighteningR[i+1,jMesh+1]]
                flowStraighteningMachNumber[i, jMesh+1], flowStraighteningFlowAngle[i, jMesh+1], flowStraighteningX[i, jMesh+1], flowStraighteningR[i, jMesh+1] \
                = axisymmetricMethodOfCharacteristics(gas, axMOCKernel, numPoints = 1)

            jMesh += 1

        upstreamPoints = [upstreamX, upstreamR, upstreamFlowAngle]
        newWallPointX, newWallPointR, downstreamPoint, newUpstreamPoint, iContour, jContour, reachedEndOfMachNet, terminated \
        = calculateWallPoints(upstreamPoints,
                              flowStraighteningMachNumber, flowStraighteningFlowAngle, flowStraighteningX, flowStraighteningR,
                              iContour, jContour)

        iContourPrevious, jContourPrevious = iContour, jContour
        downstreamR, downstreamFlowAngle, downstreamMachNumber    = [stuff for stuff in downstreamPoint]
        newUpstreamR, newUpstreamFlowAngle, newUpstreamMachNumber = [stuff for stuff in newUpstreamPoint]

        if not terminated:

            # Update values
            upstreamMachNumber   = downstreamMachNumber + (newUpstreamMachNumber - downstreamMachNumber) * (newWallPointR - downstreamR) / (newUpstreamR - downstreamR)
            upstreamFlowAngle    = newUpstreamFlowAngle - (newUpstreamFlowAngle - downstreamFlowAngle) * (newUpstreamR - newWallPointR) / (newUpstreamR - downstreamR)
            upstreamX, upstreamR = newWallPointX, newWallPointR

            xNozzleWall[index] = newWallPointX
            rNozzleWall[index] = newWallPointR
            machNumberNozzleWall[index] = upstreamMachNumber
            temperatureNozzleWall[index], pressureNozzleWall[index], velocityNozzleWall[index] \
            = isentropicValues(machNumberNozzleWall[index], state.chamberStagnationTemperature, state.chamberPressure, \
                                state.chamberGamma, state.chamberRGasConstant)

            # Only truncate when asked to. Otherwise the wall runs out to the end of the mach net,
            # which is the full-length ideal contour.
            if truncate:

                # Cut at the requested area ratio, which delivers it exactly and leaves the length
                # as the result the design Mach number search below is driving to a target.
                reached = rNozzleWall[index] >= targetWallRadius
                if reached:
                    fraction = ((targetWallRadius - rNozzleWall[index-1])
                                / (rNozzleWall[index] - rNozzleWall[index-1]))
                    rTruncate = targetWallRadius
                    xTruncate = xNozzleWall[index-1] + fraction * (xNozzleWall[index] - xNozzleWall[index-1])

                if reached:

                    terminated = True

                    machNumberNozzleWall[index] = machNumberNozzleWall[index-1] \
                        + fraction * (machNumberNozzleWall[index] - machNumberNozzleWall[index-1])
                    temperatureNozzleWall[index], pressureNozzleWall[index], velocityNozzleWall[index] \
                    = isentropicValues(machNumberNozzleWall[index], state.chamberStagnationTemperature, state.chamberPressure, \
                                        state.chamberGamma, state.chamberRGasConstant)
                    xNozzleWall[index], rNozzleWall[index] = xTruncate, rTruncate

        # Update wall contour index
        index += 1

    if reachedEndOfMachNet:
        xNozzleWall           = xNozzleWall[:index-1]
        rNozzleWall           = rNozzleWall[:index-1]
        temperatureNozzleWall = temperatureNozzleWall[:index-1]
        pressureNozzleWall    = pressureNozzleWall[:index-1]
        velocityNozzleWall    = velocityNozzleWall[:index-1]
        machNumberNozzleWall  = machNumberNozzleWall[:index-1]
    else:
        xNozzleWall           = xNozzleWall[:index]
        rNozzleWall           = rNozzleWall[:index]
        temperatureNozzleWall = temperatureNozzleWall[:index]
        pressureNozzleWall    = pressureNozzleWall[:index]
        velocityNozzleWall    = velocityNozzleWall[:index]
        machNumberNozzleWall  = machNumberNozzleWall[:index]

    # Append throat section to wall array
    xNozzleWall = np.append(throatWallX, xNozzleWall)
    rNozzleWall = np.append(throatWallR, rNozzleWall)
    temperatureNozzleWall = np.append(throatWallTemperature, temperatureNozzleWall)
    pressureNozzleWall = np.append(throatWallPressure, pressureNozzleWall)
    velocityNozzleWall = np.append(throatWallVelocity, velocityNozzleWall)
    machNumberNozzleWall = np.append(throatWallMach, machNumberNozzleWall)

    xNozzleWallScaled = state.nozzleScalingFactor * xNozzleWall
    rNozzleWallScaled = state.nozzleScalingFactor * rNozzleWall

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    # -- Calculate Thrust Coefficient -- #
    #-----------------------------------------------------------------------------------------------------------------------------------------#

    if reachedEndOfMachNet:

        # Assume all flow comes out straight and calculate Cf

        exitArea     = np.pi * rNozzleWall[-1]**2
        exitPressure = state.chamberPressure / ((1 + ((state.chamberGamma - 1) / 2) * \
                        flowStraighteningMachNumber[-1,-1]**2)**(state.chamberGamma / (state.chamberGamma - 1)))

        velocityTermThrustCoef = np.sqrt(((2 * state.chamberGamma**2) / (state.chamberGamma - 1)) * \
                                    ((2 / (state.chamberGamma + 1))**((state.chamberGamma + 1) / (state.chamberGamma - 1))) * \
                                    (1 - (exitPressure / state.chamberPressure)**((state.chamberGamma - 1) / state.chamberGamma)))
        pressureTermThrustCoef = (exitPressure - state.targetExitPressure) * exitArea / \
                                    (state.chamberPressure * np.pi * state.throatRadiusNonDimensional**2)

    else:

        # Integrate from the nozzle truncation point (x, r) down to the nozzle axis,
        # calculating Cf and other relevant flow properties along the way

        xExitPlane = xNozzleWall[-1]
        rExitPlane, machNumberExitPlane, flowAngleExitPlane = sampleExitPlaneByWalk(
            state, xExitPlane, rNozzleWall[-1], machNumberNozzleWall[-1],
            (flowStraighteningX, flowStraighteningR, flowStraighteningMachNumber,
             flowStraighteningFlowAngle),
            (expansionKernelX, expansionKernelR, expansionKernelMach,
             expansionKernelFlowAngle),
            (iContourPrevious, jContourPrevious), numContourElements)

        velocityTermThrustCoef, pressureTermThrustCoef = exitPlaneThrustCoefficient(
            state, rExitPlane, machNumberExitPlane, flowAngleExitPlane)

    state.velocityTermThrustCoef = velocityTermThrustCoef
    state.pressureTermThrustCoef = pressureTermThrustCoef
    thrustCoef = velocityTermThrustCoef + pressureTermThrustCoef

    if assignOutputsToObject:

        # Store individual kernel arrays for animation/visualization access
        state.throatKernelX                  = throatKernelX
        state.throatKernelR                  = throatKernelR
        state.throatKernelMach               = throatKernelMach
        state.expansionKernelX               = expansionKernelX
        state.expansionKernelR               = expansionKernelR
        state.expansionKernelMach            = expansionKernelMach
        state.flowStraighteningX             = flowStraighteningX
        state.flowStraighteningR             = flowStraighteningR
        state.flowStraighteningMachNumber    = flowStraighteningMachNumber
        state.limitingCharacteristicX         = limitingCharacteristicX
        state.limitingCharacteristicR         = limitingCharacteristicR

        # Concatenate nozzle mesh arrays into a single array
        state.allMachNumbers = [throatKernelMach, expansionKernelMach, flowStraighteningMachNumber]
        state.allFlowAngles  = [throatKernelFlowAngle, expansionKernelFlowAngle, flowStraighteningFlowAngle]
        state.allXPoints     = [throatKernelX, expansionKernelX, flowStraighteningX]
        state.allRPoints     = [throatKernelR, expansionKernelR, flowStraighteningR]

        for i in range(3):
            removeElements                    = np.nonzero(state.allXPoints[i] <= 0.0)
            state.allXPoints[i][removeElements]     = float('nan')
            state.allRPoints[i][removeElements]     = float('nan')
            state.allFlowAngles[i][removeElements]  = float('nan')
            state.allMachNumbers[i][removeElements] = float('nan')

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    # -- Calculate Pressure and Temperature everywhere based on Mach Number -- #
    #-----------------------------------------------------------------------------------------------------------------------------------------#

    if assignOutputsToObject:

        fillIsentropicField(state)

    # A truncated ideal contour is the one wall NOVA builds that is smooth by construction: it
    # comes off the characteristic mesh as a single streamline with no join in it, so the
    # curvature-continuous fit is both safe and the more accurate of the two. Every family whose
    # wall is stitched from an arc and a curve has a corner there and takes the shape-preserving
    # default instead.
    finishContourSolution(state, xNozzleWall, rNozzleWall, machNumberNozzleWall,
                          wallExitPressure = pressureNozzleWall[-1], thrustCoef = thrustCoef,
                          assignOutputsToObject = assignOutputsToObject,
                          splineMethod = 'curvatureContinuous')

    return state

#--------------------------------------------------------------------------------------------------------------------------#
# -- Reference contours -- #
#--------------------------------------------------------------------------------------------------------------------------#

def solvePrescribedWallContour(state: ContourSolution, wall, inflectionAngle: float,
                               lengthFraction: float,
                               assignOutputsToObject: bool = False,
                               kernelCache: dict = None) -> ContourSolution:

    '''

    Solve the flow on a wall that was drawn before the flow was touched, and the performance that
    follows from it.

    The half of a prescribed-wall family that is not about which wall it is. A thrust-optimized
    parabola and a thrust-optimized contour differ in exactly one step, how their wall is arrived
    at: two angles read from a chart in one case, four numbers an optimizer is varying in the
    other. Everything after that is the same work, and it is here so that a difference measured
    between the two families is a difference between their walls rather than between two
    implementations of the same march.

    Parameters:
    -----------
    state : ContourSolution
        Workspace carrying the chamber state and geometry. Filled in and returned.
    wall : PrescribedWall
        The wall, whose first segment is the throat arc turned to `inflectionAngle`.
    inflectionAngle : float
        Wall angle at the end of the throat arc [rad]. The kernel is turned to it.
    lengthFraction : float
        Length as a fraction of the 15 degree cone of the same area ratio [-]. Recorded rather
        than used: the wall already carries the length.
    assignOutputsToObject : bool
        True computes the mesh blocks, the near-wall arrays and the derived performance.

    Returns:
    --------
    ContourSolution

    '''

    gas, throat = state.gas, state.throat
    areaRatio   = float(state.requestedAreaRatio)

    state.numCharacteristics = state.numCharacteristicsRequested + 1

    # The length reference is the 15 degree cone of the SAME area ratio, which is how NASA SP-8120
    # defines percent bell.
    state.referenceConeLength = conicalLength(areaRatio, throat.throatRadius)

    state.nozzleScalingFactor = throatScalingFactor(state.engineMassFlow, state.chamberPressure,
                                                    state.throatGamma, state.chamberRGasConstant,
                                                    state.chamberStagnationTemperature)

    # -- The kernel, turned to this family's inflection angle -- #
    #
    # The kernel depends on one of the four design variables and not the other three, so an
    # optimizer varying the exit angle or either tension re-solves an identical kernel. That is
    # 90 per cent of an objective evaluation thrown away: measured at 4.93 seconds against 0.57
    # for the march behind it, and a forty-evaluation search made 55 kernel solves at 29 distinct
    # inflection angles.
    #
    # `kernelCache` is supplied by the caller and scoped to one search, rather than being module
    # state, so nothing is shared between solves that should not be. The key carries everything
    # the kernel depends on by value: an entry is returned only when it would have been recomputed
    # identically.
    kernel = None
    cacheKey = None
    if kernelCache is not None:
        cacheKey = (int(state.numCharacteristics), float(inflectionAngle),
                    float(state.chamberPressure), float(gas.gamma), float(gas.gasConstant),
                    float(gas.stagnationTemperature), float(throat.throatRadius),
                    float(throat.outletCurvature))
        kernel = kernelCache.get(cacheKey)

    if kernel is None:
        kernel = solveKernel(gas, throat, state.numCharacteristics, inflectionAngle,
                             state.chamberPressure)
        if cacheKey is not None:
            kernelCache[cacheKey] = kernel

    state.throatWallX, state.throatWallR = kernel['throatWallX'], kernel['throatWallR']
    state.throatWallAngles = kernel['throatWallAngles']
    state.throatEndAngle   = kernel['throatWallAngles'][-1]

    # The starting line is the kernel's downstream boundary: the last right-running characteristic,
    # from the wall inflection point to the axis. The same slice the truncated ideal contour seeds
    # its flow-straightening block from.
    startSlice = slice(state.numCharacteristics - 1, None)
    startingLine = tuple(block[startSlice, -1] for block in
                         (kernel['expansionKernelMach'], kernel['expansionKernelFlowAngle'],
                          kernel['expansionKernelX'], kernel['expansionKernelR']))
    usable = np.isfinite(startingLine[0]) & (startingLine[0] > 1.0)
    startingLine = tuple(array[usable] for array in startingLine)

    march = marchPrescribedWall(gas, wall, startingLine)
    state.marchTerminatedOn = march['terminated']

    # How many lines ended on a fold, recorded whether or not the envelope test below finds a
    # shock. The two disagree: on the shipped parabola the march folds two lines at fifty
    # characteristics while `shockFront` comes back None, and the folded fraction rises with
    # resolution, 4.2 per cent of lines at thirty characteristics to 10.0 at a hundred and
    # twenty. A fold is same-family characteristics crossing, which is compression coalescing,
    # so a solution reporting no internal shock while folding lines is making a claim it
    # cannot support. This is the count that says so.
    state.marchFoldedLines = int(march.get('foldedLines', 0))
    # One authority on whether there is a shock, and it is the envelope. The march keeps its own
    # record of where its lines crossed, but that test was shown to be measuring drift near the
    # axis rather than compression, and the two disagree: it reports a crossing on walls the
    # envelope finds no coalescence on. Carrying both onto a solution would invite reading the
    # one that was wrong.
    state.internalShock     = None
    # From the wall envelope, not from crossings in the mesh: see shockFromWallEnvelope for why
    # the mesh-position test was measuring drift rather than compression.
    state.shockFront        = shockFromWallEnvelope(gas, march['wallX'], march['wallR'],
                                                    march['wallAngle'], march['wallMach'],
                                                    exitStation = float(march['wallX'][-1]))
    if state.shockFront is not None:
        # `frontResolved` is the difference between a loss that is negligible and a loss that was
        # never applied, and without it the two are indistinguishable in the output.
        #
        # The downstream stagnation field interpolates along the front, so it needs at least two
        # crossings to have a front to interpolate along. A single crossing carries a stagnation
        # ratio but no radial extent, so nothing is charged for it and the thrust debit comes back
        # exactly zero. Measured on the worked design point, the two conditions do not overlap:
        # four to six degrees past the chart parabola gives one crossing, a deflection under a
        # degree and a debit of exactly zero, while seven degrees gives thirteen degrees of
        # deflection and a front that is no longer weak. So a debit of zero beside `isWeak` true
        # means the front was too sparse to charge for, not that the charge was small.
        state.internalShock = {
            'onsetX':                 state.shockFront['onsetX'],
            'peakDeflection':         state.shockFront['peakDeflection'],
            'minimumStagnationRatio': state.shockFront['minimumStagnationRatio'],
            'isWeak':                 state.shockFront['isWeak'],
            'numCrossings':           state.shockFront['numCrossings'],
            'frontResolved':          bool(state.shockFront['numCrossings'] >= 2),
        }

    # -- The wall, throat arc then contoured run -- #
    xNozzleWall = np.append(kernel['throatWallX'], march['wallX'])
    rNozzleWall = np.append(kernel['throatWallR'], march['wallR'])
    machNumberNozzleWall = np.append(kernel['throatWallMach'], march['wallMach'])

    # -- The mesh, in the three blocks every downstream reader expects -- #
    state.throatKernelX, state.throatKernelR = kernel['throatKernelX'], kernel['throatKernelR']
    state.throatKernelMach = kernel['throatKernelMach']
    state.expansionKernelX, state.expansionKernelR = kernel['expansionKernelX'], kernel['expansionKernelR']
    state.expansionKernelMach = kernel['expansionKernelMach']
    state.flowStraighteningX, state.flowStraighteningR = march['x'], march['r']
    state.flowStraighteningMachNumber = march['mach']
    state.limitingCharacteristicX = kernel['limitingCharacteristicX']
    state.limitingCharacteristicR = kernel['limitingCharacteristicR']

    state.allMachNumbers = [kernel['throatKernelMach'], kernel['expansionKernelMach'], march['mach']]
    state.allFlowAngles  = [kernel['throatKernelFlowAngle'], kernel['expansionKernelFlowAngle'],
                            march['flowAngle']]
    state.allXPoints     = [kernel['throatKernelX'], kernel['expansionKernelX'], march['x']]
    state.allRPoints     = [kernel['throatKernelR'], kernel['expansionKernelR'], march['r']]

    for index in range(len(state.allXPoints)):
        unfilled = np.nonzero(state.allXPoints[index] <= 0.0)
        for block in (state.allXPoints, state.allRPoints, state.allFlowAngles, state.allMachNumbers):
            block[index][unfilled] = float('nan')

    # -- The exit plane and the thrust coefficient -- #
    xExitPlane = float(march['wallX'][-1])
    blocks = list(zip(state.allXPoints, state.allRPoints, state.allMachNumbers, state.allFlowAngles))
    rExitPlane, machExitPlane, flowAngleExitPlane = sampleExitPlaneByScan(state, blocks, xExitPlane)

    # -- The shock the wall paid for, charged to the exit plane -- #
    #
    # Streamlines that crossed the front arrive with less stagnation pressure than the chamber
    # gave them, so the plane is integrated against a stagnation pressure that varies across it
    # rather than one number. Without this the solve charges a wall nothing for turning, and a
    # search over wall shapes turns as hard as its bounds allow for a gain that is not real.
    exitStagnation = stagnationPressureField(state.chamberPressure, state.shockFront,
                                             rExitPlane, np.full_like(rExitPlane, xExitPlane))

    velocityTerm, pressureTerm = exitPlaneThrustCoefficient(
        state, rExitPlane, machExitPlane, flowAngleExitPlane,
        stagnationPressure = exitStagnation)
    state.velocityTermThrustCoef, state.pressureTermThrustCoef = velocityTerm, pressureTerm
    thrustCoef = velocityTerm + pressureTerm

    # What the shock cost, measured rather than asserted: the same plane integrated as though the
    # loss were not there. Reported so a reader can see the size of what the capture added.
    if state.shockFront is not None:
        inviscidTerms = exitPlaneThrustCoefficient(
            state, rExitPlane, machExitPlane, flowAngleExitPlane)
        state.thrustCoefWithoutShock = float(sum(inviscidTerms))
        state.shockThrustDebit = float(thrustCoef - state.thrustCoefWithoutShock)
        # exitPlaneThrustCoefficient writes the plane onto the state, so the shocked integral has
        # to be the one that lands there rather than the comparison that followed it.
        exitPlaneThrustCoefficient(state, rExitPlane, machExitPlane, flowAngleExitPlane,
                                   stagnationPressure = exitStagnation)

    state.calculatedExitMach   = float(machExitPlane[-1])
    state.calculatedExitRadius = float(rExitPlane[0])

    if assignOutputsToObject:
        fillIsentropicField(state)

    _, wallExitPressure, _ = isentropicValues(machNumberNozzleWall[-1],
                                              state.chamberStagnationTemperature,
                                              state.chamberPressure, state.chamberGamma,
                                              state.chamberRGasConstant)

    # A parabola is stitched from an arc and a curve, so its curvature jumps at the join. A C2
    # cubic through that join must overshoot, which would be geometry the solve never produced;
    # the shape-preserving fit cannot leave the range of the points it passes through.
    finishContourSolution(state, xNozzleWall, rNozzleWall, machNumberNozzleWall,
                          wallExitPressure = wallExitPressure, thrustCoef = thrustCoef,
                          assignOutputsToObject = assignOutputsToObject,
                          splineMethod = 'shapePreserving')

    return state

def thrustOptimizedParabolicContour(state: ContourSolution, lengthFraction: float,
                                    wallAngles: tuple = None,
                                    assignOutputsToObject: bool = False) -> ContourSolution:

    '''

    Solve a thrust-optimized parabola and the performance that follows from it.

    Rao's 1960 approximation to his own 1958 optimum: the throat exit arc turned to an inflection
    angle, then a skewed parabola to the exit at an exit angle, with both angles read from a chart
    against area ratio and percent bell. It is what most flight bells actually are.

    **There is no free parameter and no design-point solve.** A truncated ideal contour has one,
    the design exit Mach number, and has to iterate it until the delivered length matches the
    request. Here the area ratio and the length are both properties of a point on the wall that is
    placed before the solve starts, so both are delivered exactly and the exit pressure is a
    result. That makes this family several times cheaper than the truncated ideal one, which
    matters because the optimizer for the thrust-optimized contour calls this same path repeatedly.

    Parameters:
    -----------
    state : ContourSolution
        Workspace carrying the chamber state and geometry. Filled in and returned.
    lengthFraction : float
        Length as a fraction of the 15 degree cone of the same area ratio [-].
    wallAngles : tuple
        (thetaInflection, thetaExit) in radians, to override the chart lookup. The chart is a
        digitization carrying a known transcription error and is extrapolated above an area ratio
        of about 50, so a user with better numbers should be able to say so.
    assignOutputsToObject : bool
        True computes the mesh blocks, the near-wall arrays and the derived performance.

    Returns:
    --------
    ContourSolution
        The same workspace, with `thrustCoef` and `pressureError` always set.

    '''

    throat = state.throat
    areaRatio = float(state.requestedAreaRatio)

    if wallAngles is None:
        inflectionAngle, exitAngle, extrapolated = raoWallAngles(areaRatio, lengthFraction)
    else:
        inflectionAngle, exitAngle = wallAngles
        extrapolated = False

    nozzleLength = lengthFraction * conicalLength(areaRatio, throat.throatRadius)
    wall = thrustOptimizedParabolaWall(throat.throatRadius, throat.outletCurvature, areaRatio,
                                       nozzleLength, inflectionAngle, exitAngle)

    state = solvePrescribedWallContour(state, wall, inflectionAngle, lengthFraction,
                                       assignOutputsToObject = assignOutputsToObject)
    state.chartExtrapolated = extrapolated
    state.wallDesignVariables = {'inflectionAngle': float(inflectionAngle),
                                 'exitAngle': float(exitAngle)}
    state.divergingSectionFamily = 'thrustOptimizedParabola'
    return state

def thrustOptimizedContour(state: ContourSolution, lengthFraction: float,
                           designVariables: tuple,
                           assignOutputsToObject: bool = False,
                           kernelCache: dict = None) -> ContourSolution:

    '''

    Solve one candidate thrust-optimized contour: a cubic-Bezier bell at a given design vector.

    This is the objective an optimizer calls, not a design method on its own. Rao's 1958 optimum
    comes from a variational argument over a control surface; what is done here instead is
    Allman and Hoffman's 1981 alternative, which fixes the initial expansion and varies the
    coefficients of a low-order wall directly against the thrust the solve returns. The two
    approaches were shown to agree, and the direct one needs no equations that cannot be checked.

    The design vector is four numbers, and the two design constraints are absorbed by the
    construction rather than imposed on the search: the exit point is fixed by the area ratio and
    the length, so every candidate delivers the requested design point exactly and the optimizer
    sees a box rather than an equality-constrained problem.

    Parameters:
    -----------
    state : ContourSolution
        Workspace carrying the chamber state and geometry. Filled in and returned.
    lengthFraction : float
        Length as a fraction of the 15 degree cone of the same area ratio [-].
    designVariables : tuple
        (inflectionAngle, exitAngle, inflectionTension, exitTension). The angles are in radians;
        the tensions are control-point distances along each tangent as a fraction of the chord
        from the inflection point to the exit.
    assignOutputsToObject : bool
        True computes the mesh blocks, the near-wall arrays and the derived performance.

    Returns:
    --------
    ContourSolution

    '''

    throat = state.throat
    areaRatio = float(state.requestedAreaRatio)
    inflectionAngle, exitAngle, inflectionTension, exitTension = designVariables

    nozzleLength = lengthFraction * conicalLength(areaRatio, throat.throatRadius)
    wall = bezierBellWall(throat.throatRadius, throat.outletCurvature, areaRatio, nozzleLength,
                          inflectionAngle, exitAngle, inflectionTension, exitTension)

    state = solvePrescribedWallContour(state, wall, inflectionAngle, lengthFraction,
                                       assignOutputsToObject = assignOutputsToObject,
                                       kernelCache = kernelCache)
    state.wallDesignVariables = {'inflectionAngle': float(inflectionAngle),
                                 'exitAngle': float(exitAngle),
                                 'inflectionTension': float(inflectionTension),
                                 'exitTension': float(exitTension)}
    state.divergingSectionFamily = 'thrustOptimizedContour'
    return state

def conicalContour(throat: ThroatGeometry, areaRatio: float, scalingFactor: float,
                   numPoints: int = 100, conicalHalfAngle: float = 15.0) -> tuple:

    '''

    Straight-walled cone from the throat to the exit radius of a given area ratio.

    There is no interior solution here and nothing is iterated: the wall is a line, fixed by the
    area ratio and the half angle. The exit flow diverges at the half angle, which costs the
    classical divergence factor (1 + cos alpha) / 2, 0.983 at the conventional 15 degrees. SP-8120
    notes that at low area ratio the measured divergence efficiency oscillates with area ratio
    rather than following that formula, and that shocks can form where the arc meets the straight
    wall.

    The area ratio is taken as given rather than derived from a Mach number, so a cone asked for an
    expansion ratio delivers it exactly. Sizing it from a one-dimensional Mach number instead lands
    on whatever area ratio that Mach number happens to correspond to, which at this operating point
    is 48.5 against a requested 40, because the Mach number is a perfect-gas inverse of a pressure
    that came from an equilibrium calculation.

    Parameters:
    -----------
    throat : ThroatGeometry
        Supplies the throat radius the cone starts from.
    areaRatio : float
        Exit area over throat area [-].
    scalingFactor : float
        Throat radius in meters, from `throatScalingFactor` [m].
    numPoints : int
        Points along the wall.
    conicalHalfAngle : float
        Cone half angle [deg].

    Returns:
    --------
    tuple : (x, r) wall coordinates in meters

    '''

    exitRadius = np.sqrt(areaRatio) * throat.throatRadius
    coneLength = conicalLength(areaRatio, throat.throatRadius, np.radians(conicalHalfAngle))

    x = np.linspace(0, coneLength, numPoints) * scalingFactor
    r = np.linspace(throat.throatRadius, exitRadius, numPoints) * scalingFactor
    return x, r

def solveConicalContour(state: ContourSolution, conicalHalfAngle: float = 15.0,
                        assignOutputsToObject: bool = False) -> ContourSolution:

    '''

    Build a straight-walled cone and finish it the way every other family is finished.

    There is nothing to iterate. The wall is a line fixed by the area ratio and the half angle, so
    this exists to put the cone through the same last step as the contoured families rather than to
    search for anything.

    What it has to supply in place of a characteristic solve is the near-wall state and the thrust
    coefficient, and both come from the classical conical treatment:

        near-wall Mach      the one-dimensional area-Mach relation at the local wall radius. It
                            carries no radial structure and no wave reflections, so it misses the
                            overexpansion at the arc-to-cone junction that SP-8120 warns can stand
                            a shock.
        exit plane          a spherical source flow from the virtual apex, so the flow angle runs
                            from zero on the axis to the half angle at the wall and the Mach number
                            is held uniform across the plane. Integrating that plane is what
                            produces the divergence loss, so `divergenceLossFactor` is not applied
                            on top: doing both would count it twice.

    The same integral the contoured families use then returns the thrust coefficient, so a cone and
    a bell are compared on one measure rather than on two conventions.

    Parameters:
    -----------
    state : ContourSolution
        Workspace supplying the chamber state, the throat and the requested area ratio.
    conicalHalfAngle : float
        Cone half angle [deg].
    assignOutputsToObject : bool
        Whether to write the full output set onto the workspace.

    Returns:
    --------
    ContourSolution : the same workspace, with `thrustCoef` set.

    '''

    areaRatio = float(state.requestedAreaRatio)
    halfAngle = np.radians(float(conicalHalfAngle))
    scaling = throatScalingFactor(state.engineMassFlow, state.chamberPressure, state.throatGamma,
                                  state.chamberRGasConstant,
                                  state.chamberStagnationTemperature)

    state.nozzleScalingFactor = scaling

    # Built non-dimensional, in throat radii, because `finishContourSolution` scales what it is
    # handed. Passing a wall that is already in metres scales it twice.
    xNozzleWall, rNozzleWall = conicalContour(state.throat, areaRatio, 1.0,
                                              numPoints = state.numContourPoints,
                                              conicalHalfAngle = conicalHalfAngle)

    # The wall Mach number, station by station, from the local area ratio alone.
    throatRadius = float(np.min(rNozzleWall))
    localAreaRatio = np.maximum((np.asarray(rNozzleWall, dtype = float)/throatRadius)**2, 1.0)
    machNumberNozzleWall = np.array([machFromAreaRatio(float(ratio), state.chamberGamma,
                                                       branch = 'supersonic')
                                     for ratio in localAreaRatio])

    # The exit plane as a source flow from the virtual apex, ordered wall inward to the axis so it
    # matches what `exitPlaneThrustCoefficient` integrates for every other family.
    exitRadius = float(rNozzleWall[-1])
    apexDistance = exitRadius/np.tan(halfAngle)
    rExitPlane = np.linspace(exitRadius, 0.0, state.numContourPoints)
    flowAngleExitPlane = np.arctan2(rExitPlane, apexDistance)
    machNumberExitPlane = np.full_like(rExitPlane, machNumberNozzleWall[-1])

    velocityTerm, pressureTerm = exitPlaneThrustCoefficient(state, rExitPlane,
                                                            machNumberExitPlane,
                                                            flowAngleExitPlane)
    state.velocityTermThrustCoef = velocityTerm
    state.pressureTermThrustCoef = pressureTerm
    thrustCoef = velocityTerm + pressureTerm

    _, wallExitPressure, _ = isentropicValues(machNumberNozzleWall[-1],
                                              state.chamberStagnationTemperature,
                                              state.chamberPressure, state.chamberGamma,
                                              state.chamberRGasConstant)

    finishContourSolution(state, xNozzleWall, rNozzleWall, machNumberNozzleWall,
                          wallExitPressure = wallExitPressure, thrustCoef = thrustCoef,
                          assignOutputsToObject = assignOutputsToObject)

    return state

# Initial and final wall angles for the Rao canted-parabola contour, in degrees, against area ratio
# and percent bell. This is a DIGITIZATION of figure 5(b) of NASA SP-8120, which itself reproduces
# Rao (1960); it is not the primary source and carries at least one transcription error, the
# non-monotone theta_n between area ratios 40 and 50 at 60 percent bell. SP-8120 further states
# that the chart is EXTRAPOLATED above an area ratio of about 50, so values read there inherit that
# extrapolation and are not measurements.
raoChartAreaRatios   = np.array([4.0, 5.0, 10.0, 20.0, 30.0, 40.0, 50.0, 100.0])
raoChartLengths      = np.array([0.60, 0.80, 0.90])
raoChartInflection   = np.array([[26.5, 21.5, 20.0],
                                 [28.0, 23.0, 21.0],
                                 [32.0, 26.3, 24.0],
                                 [35.0, 28.8, 27.0],
                                 [36.2, 30.0, 28.5],
                                 [37.1, 31.0, 29.5],
                                 [35.0, 31.5, 30.2],
                                 [40.0, 33.5, 32.0]])
raoChartExit         = np.array([[20.5, 14.0, 11.5],
                                 [20.5, 13.0, 10.5],
                                 [16.0, 11.0,  8.0],
                                 [14.5,  9.0,  7.0],
                                 [14.0,  8.5,  6.5],
                                 [13.5,  8.0,  6.0],
                                 [13.0,  7.5,  6.0],
                                 [11.2,  7.0,  6.0]])
raoChartExtrapolatedAbove = 50.0

def raoWallAngles(areaRatio: float, lengthFraction: float) -> tuple:

    '''

    Inflection and exit wall angles for a thrust-optimized parabolic contour.

    Read from the digitized chart above, bilinearly in log area ratio and linearly in percent bell.
    Outside the tabulated range the nearest edge is held rather than extrapolated further, because
    the chart is already extrapolated at its upper end.

    Parameters:
    -----------
    areaRatio : float
        Exit area over throat area [-]
    lengthFraction : float
        Nozzle length as a fraction of the 15 degree cone of the same area ratio [-]

    Returns:
    --------
    tuple : (thetaInflection, thetaExit) in radians, and a bool that is True when the answer comes
    from the extrapolated region of the chart

    '''

    logRatio  = np.log(np.clip(areaRatio, raoChartAreaRatios[0], raoChartAreaRatios[-1]))
    logColumn = np.log(raoChartAreaRatios)
    fraction  = float(np.clip(lengthFraction, raoChartLengths[0], raoChartLengths[-1]))

    def interpolate(table):
        alongLength = [np.interp(fraction, raoChartLengths, row) for row in table]
        return float(np.interp(logRatio, logColumn, alongLength))

    return (np.radians(interpolate(raoChartInflection)),
            np.radians(interpolate(raoChartExit)),
            bool(areaRatio > raoChartExtrapolatedAbove))

def raoParabolicContour(throat: ThroatGeometry, areaRatio: float, lengthFraction: float,
                        scalingFactor: float, numPoints: int = 100,
                        wallAngles: tuple = None) -> tuple:

    '''

    Rao's canted-parabola approximation to the thrust-optimized contour.

    A reference contour, not a design path. It solves nothing: the throat exit arc is turned to the
    inflection angle, and a quadratic Bezier runs from there to the exit at the exit angle. Rao's
    point is that this shape sits close enough to the true optimum that the difference does not
    matter for performance, which is why most flight bells are drawn this way.

    Its value here is that it is the construction published bells are quoted against, so a
    generated contour can be compared to it wall angle for wall angle.

    Parameters:
    -----------
    throat : ThroatGeometry
        Supplies the throat radius and the 0.382 exit arc.
    areaRatio : float
        Exit area over throat area [-]
    lengthFraction : float
        Length as a fraction of the 15 degree cone of the same area ratio [-]
    scalingFactor : float
        Throat radius in meters [m]
    numPoints : int
        Points along the returned wall
    wallAngles : tuple
        (thetaInflection, thetaExit) in radians, to override the chart lookup

    Returns:
    --------
    tuple : (x, r) wall coordinates in meters, from the throat plane to the exit

    '''

    if wallAngles is None:
        thetaInflection, thetaExit, _ = raoWallAngles(areaRatio, lengthFraction)
    else:
        thetaInflection, thetaExit = wallAngles

    throatRadius = throat.throatRadius
    exitRadius   = np.sqrt(areaRatio) * throatRadius
    nozzleLength = lengthFraction * conicalLength(areaRatio, throatRadius)

    # Downstream throat arc, from the throat plane to the inflection point N.
    arcAngles = np.linspace(-0.5 * np.pi, thetaInflection - 0.5 * np.pi, max(2, numPoints // 4))
    arcX      = throat.exitArcRadius * np.cos(arcAngles)
    arcR      = throat.exitArcRadius * np.sin(arcAngles) + throat.exitArcCenterRadius

    # Quadratic Bezier from N to the exit E, with its control point where the two tangents meet.
    nX, nR = arcX[-1], arcR[-1]
    eX, eR = nozzleLength, exitRadius
    slopeInflection, slopeExit = np.tan(thetaInflection), np.tan(thetaExit)
    interceptInflection = nR - slopeInflection * nX
    interceptExit       = eR - slopeExit * eX
    controlX = (interceptExit - interceptInflection) / (slopeInflection - slopeExit)
    controlR = (slopeInflection * interceptExit - slopeExit * interceptInflection) \
               / (slopeInflection - slopeExit)

    t = np.linspace(0.0, 1.0, numPoints - len(arcX) + 1)
    bezierX = (1 - t)**2 * nX + 2 * (1 - t) * t * controlX + t**2 * eX
    bezierR = (1 - t)**2 * nR + 2 * (1 - t) * t * controlR + t**2 * eR

    x = np.concatenate([arcX, bezierX[1:]]) * scalingFactor
    r = np.concatenate([arcR, bezierR[1:]]) * scalingFactor
    return x, r

def wallAnglesFromContour(x: np.ndarray, r: np.ndarray) -> tuple:

    '''

    Inflection and exit wall angles measured off a generated contour.

    The inflection angle is the steepest wall angle anywhere downstream of the throat, which is
    where the expansion section hands over to the straightening section. The exit angle is the
    wall angle at the last point.

    Both come from `np.gradient`, which is a centerd second-order difference in the interior and a
    one-sided second-order difference at the ends. A plain backward difference over several points
    would read a curving wall steeper than it is at the exit, which on a Rao parabola is a third
    of a degree.

    Parameters:
    -----------
    x, r : np.ndarray
        Wall coordinates from the throat plane onward, in any consistent unit.

    Returns:
    --------
    tuple : (thetaInflection, thetaExit) in radians, and the index of the inflection point

    '''

    x, r = np.asarray(x, dtype = float), np.asarray(r, dtype = float)
    angles = np.arctan2(np.gradient(r), np.gradient(x))
    inflectionIndex = int(np.nanargmax(angles))
    return float(angles[inflectionIndex]), float(angles[-1]), inflectionIndex

#--------------------------------------------------------------------------------------------------------------------------#
# -- Quasi one-dimensional field -- #
#--------------------------------------------------------------------------------------------------------------------------#

def quasiOneDimensionalField(x, r, gas, chamberPressure: float, throatRadius: float = None,
                             numRadial: int = 48, branch: str = 'auto') -> dict:

    '''

    The flow state on a station-by-station one-dimensional solve, painted across the full radius.

    At each axial station the local area ratio fixes one subsonic and one supersonic Mach number.
    Taking the appropriate root and holding it across the whole cross section gives a field that
    varies axially and not radially. That is not a solution of the flow; it is the one-dimensional
    answer drawn as a field, and it is what the chamber and the converging section have, because
    nothing solves them.

    Its value is comparison. Drawn beside the characteristics mesh in the diverging section it
    shows directly how much of the real field the one-dimensional assumption misses, which is the
    entire reason the mesh exists.

    Parameters:
    -----------
    x, r : array-like
        Wall coordinates, in meters, running from the chamber through the throat.
    gas : CharacteristicGas
        Supplies the ratio of specific heats and the stagnation temperature.
    chamberPressure : float
        Chamber stagnation pressure [Pa].
    throatRadius : float
        Throat radius in the same units as r. Taken as the minimum of r when not given.
    numRadial : int
        Points across the radius at each station.
    branch : str
        'subsonic', 'supersonic', or 'auto' to take the subsonic root upstream of the throat and
        the supersonic root downstream of it.

    Returns:
    --------
    dict
        'x', 'r' as 2-D grids, and 'mach', 'pressure', 'temperature' on the same grid. Also 'wallX'
        and 'wallR' as given, and 'mach1D' as the station values.

    '''

    x, r = np.asarray(x, dtype = float), np.asarray(r, dtype = float)
    if throatRadius is None:
        throatRadius = float(np.min(r))
    throatIndex = int(np.argmin(r))

    stationMach = np.zeros(len(x))
    for index, radius in enumerate(r):
        areaRatio = max(1.0, (radius / throatRadius) ** 2)
        if branch == 'auto':
            side = 'subsonic' if index < throatIndex else 'supersonic'
        else:
            side = branch
        stationMach[index] = machFromAreaRatio(areaRatio, gas.gamma, side)

    fraction = np.linspace(0.0, 1.0, numRadial)
    grids = {
        'x': np.repeat(x[:, None], numRadial, axis = 1),
        'r': r[:, None] * fraction[None, :],
        'mach': np.repeat(stationMach[:, None], numRadial, axis = 1),
    }
    grids['temperature'] = gas.stagnationTemperature * staticTemperatureRatio(grids['mach'],
                                                                             gas.gamma)
    grids['pressure'] = chamberPressure * staticPressureRatio(grids['mach'], gas.gamma)
    grids['wallX'], grids['wallR'], grids['mach1D'] = x, r, stationMach
    grids['throatIndex'] = throatIndex
    return grids

# ----------------------------------------------------------------------
#                       The outer design solve
# ----------------------------------------------------------------------
#
# A truncated ideal contour has two design numbers, an area ratio and a length, and one free
# parameter: the exit Mach number the underlying ideal nozzle is designed to. A larger design
# Mach number opens the wall faster near the throat, so it reaches a given area ratio in less
# length and leaves a steeper exit. Solving for it is what makes the contour deliver both numbers
# rather than one.
#
# The solve drives `truncatedIdealContour` and is written against whatever object can run it, so
# it takes that object rather than reaching for one. That is the only reason it is not a free
# function over a ContourSolution: the residual needs a full solve per iterate, and a Nozzle is
# what assembles one.

def solveDesignPoint(nozzle, lengthFraction: float | str, lowerBound: float = 0.65, upperBound: float = 0.9):

    '''

    Generate a truncated ideal contour that delivers the requested design point.

    A truncated ideal contour has two design numbers, an area ratio and a length, and one free
    parameter: the exit Mach number the underlying ideal nozzle is designed to. A larger design
    Mach number opens the wall faster near the throat, so it reaches a given area ratio in less
    length and leaves a steeper exit. That is the trade this method solves.

    The wall is cut at the requested area ratio, and the design Mach number is varied until the
    length that falls out is the requested fraction of the 15 degree conical reference. Both
    requested numbers are then delivered exactly, and the exit pressure is a result rather than a
    target: a truncated contour's exit plane is strongly non-uniform, so no single station on it
    can be driven to a value and called a match.

    A requested exit pressure reaches the wall the same way a requested area ratio does. The two
    are mutually exclusive combustion inputs and config.py resolves whichever was not given from
    the other through the one-dimensional CEA relation before this solve ever runs, so by the
    time the area ratio reaches here it already reflects the exit pressure if that is what was
    asked for.

    Parameters:
    -----------
    lengthFraction : float | str
        Requested length as a fraction of the 15 degree cone of the same area ratio. A string
        instead sweeps for the fraction that maximizes the thrust coefficient.
    lowerBound, upperBound : float
        Bounds on the length fraction for the sweep.

    '''

    # -- Wrapper Helper Functions -- #

    def convergeDesignMach(lengthFraction: float, isOptimizing: bool = False) -> float | None:

        '''

        Vary the design exit Mach number until the binding residual is zero, then rerun at the
        converged value and keep the full solution.

        '''

        # A loose tolerance here is not free: the residual passes through a characteristics
        # solve, so a step that ends one iterate early leaves the delivered geometry sensitive
        # to changes as small as a unit in the last place of a Prandtl-Meyer evaluation.
        optimizedTargetMach = fsolve(nozzle.truncatedIdealContour,
                                     x0 = nozzle.idealMachNumber,
                                     args = (lengthFraction, True, False),
                                     xtol = 1e-8)[0]

        # Run optimized value of target exit mach
        thrustCoefficient = nozzle.truncatedIdealContour(optimizedTargetMach, lengthFraction, truncate = True, assignOutputsToObject = True)

        if isOptimizing:
            print(f'Current Length Fraction: {lengthFraction:.5f} | Current Thrust Coefficient: {thrustCoefficient:.5f}')
            return -thrustCoefficient

    convergeToExitPressure = convergeDesignMach

    # -- Two Cases: -- #

    # Single specific length fraction is requested
    if isinstance(lengthFraction, float):

        print(f'''Generating a pressure-matched truncated ideal nozzle contour to a target exit pressure of {nozzle.targetExitPressure:.2f} [Pa] at a length fraction of {lengthFraction:.5f}.''')

        convergeToExitPressure(lengthFraction)

        # Hide the plots underneath this if statement to collapse them in the editor

    # User has requested to find the ideal length fraction that maximizes thrust coefficient
    elif isinstance(lengthFraction, str):

            print(f'Optimizing nozzle length fraction to maximize thrust coefficient at a target exit pressure of {nozzle.targetExitPressure:.2f} [Pa]:')

            optimizedLengthFraction = minimize_scalar(convergeToExitPressure,
                                                      args = (True),
                                                      bounds = (lowerBound, upperBound)).x

            # Run the objective function with the optimized values and plot the result
            convergeToExitPressure(optimizedLengthFraction)

            # Hide the plots
