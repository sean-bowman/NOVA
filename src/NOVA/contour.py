
# -- Nozzle Wall Contour Generation -- #

'''

Contour generators: the wall itself, and the performance that follows from it.

Three families are produced here, and they are not interchangeable.

`truncatedIdealContour` solves the characteristics net from a transonic starting line, traces the
wall as the streamline that turns the flow back to axial, and truncates. This is the method NASA
SP-8120 attributes to Ahlberg et al.: design an ideal nozzle to a higher area ratio than required,
then truncate to the area ratio wanted, and the length follows. The interior is shock free by
construction, because it is a piece of an ideal nozzle.

`conicalContour` is a straight wall at a chosen half angle. It has no interior solution and no
free parameters beyond the angle.

`raoParabolicContour` draws a skewed parabola between two prescribed wall angles. It solves
nothing; it exists so that a generated contour can be compared against the construction most
published bells actually use, and it is not a design path.

The solve reads a `ContourSolution` as its own workspace and returns it filled in. That is
deliberate: the algorithm is one long march whose intermediate arrays are also its outputs, and
pretending otherwise would mean copying the whole characteristic mesh twice. What matters for
testing is that nothing here reads or writes a Nozzle: every input arrives through the workspace,
so the solve can be driven from a test with a gas, a throat and four numbers.

Lengths inside the solve are non-dimensional against the throat radius and are scaled to metres
only at the end. Angles are in radians.

Author: Sean Bowman
Date:   09/06/2026

'''

import copy
import warnings

import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import UnivariateSpline
from scipy.optimize import fsolve, minimize_scalar

from .characteristics import (CharacteristicGas, axisymmetricMethodOfCharacteristics,
                              wallCharacteristicProjection)
from .contourKernel import (ThroatGeometry, sauerLimitingCharacteristic,
                            limitingCharacteristicIntersection, throatIntersection)
from .gasDynamics import (prandtlMeyerAngle, radiusMachRelation, conicalLength,
                          machFromAreaRatio, staticPressureRatio, staticTemperatureRatio)
from .utils import arcSpline, plotLine, isentropicValues, lineIntersection

def throatScalingFactor(engineMassFlow: float, chamberPressure: float, throatGamma: float,
                        gasConstant: float, stagnationTemperature: float) -> float:

    '''

    Throat radius in metres, from the choked mass flow the engine has to pass.

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
    ambientSpecificImpulse : float
        Ambient specific impulse from the thermochemistry, used for the delivered c-star [s]
    plotsDocs : str
        'on' draws the step-by-step construction figures the documentation uses

    '''

    def __init__(self, gas: CharacteristicGas, throat: ThroatGeometry, chamberPressure: float,
                 engineMassFlow: float, throatGamma: float, idealMachNumber: float,
                 targetExitPressure: float, numContourPoints: int,
                 requestedAreaRatio: float = float('nan'), truncateOn: str = 'areaRatio',
                 numCharacteristicsRequested: int = 50,
                 ambientSpecificImpulse: float = float('nan'), plotsDocs: str = 'off'):

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
        self.truncateOn                          = truncateOn
        self.numCharacteristicsRequested         = numCharacteristicsRequested
        self.ambientSpecificImpulse              = ambientSpecificImpulse
        self.plotsDocs                           = plotsDocs
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
    'deliveredAreaRatio', 'deliveredLengthFraction', 'referenceConeLength', 'exitWallAngle',
    'inflectionWallAngle')

def truncatedIdealContour(state: ContourSolution, targetExitMach: float, lengthFraction: float,
                          isPressureMatching: bool = False,
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
      truncate it.
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
    isPressureMatching : bool
        True truncates at the target length. False runs the wall out to the end of the mesh.
    assignOutputsToObject : bool
        True computes the mesh blocks, the near-wall arrays and the derived performance. False
        computes only what the figures of merit need, which is what the pressure match iterates on.

    Returns:
    --------
    ContourSolution
        The same workspace, with `thrustCoef` and `pressureError` always set.

    '''

    # Depending on the passed-in [mach, lengthFrac], np.sqrt may return a NaN and divide-by-zero
    # instances may occur. This is to be expected, and as such the warnings printed to the terminal
    # are suppressed to de-clutter the desirable outputs printed in the terminal.
    warnings.filterwarnings('ignore')

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

        if state.plotsDocs == 'on':
            # Display the query points for calculating wall points
            plt.plot(upstreamX, upstreamR, '*y', markersize = 16)
            plt.plot(downstreamX, downstreamR, '*y', markersize = 16)
            plt.plot(leftRunningX, leftRunningR, '*y', markersize = 16)
            plt.plot(rightRunningX, rightRunningR, '*y', markersize = 16)

            plt.plot(xQueryLeftRunning1, rQueryLeftRunning1, 'og', markersize = 16)
            plt.plot(xQueryLeftRunning2, rQueryLeftRunning2, 'or', markersize = 16)
            plt.plot(xQueryRightRunning1, rQueryRightRunning1, 'or', markersize = 16)
            plt.plot(xQueryRightRunning2, rQueryRightRunning2, 'or', markersize = 16)

            stop = 1

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
    # Where the wall is cut, and therefore which requested number is delivered and which is a
    # result. Radius gives the requested area ratio, which is the method NASA SP-8120 describes.
    # Wall pressure gives a nozzle expanded exactly to its operating ambient, which is the
    # maximum-thrust condition. Length gives the requested length.
    truncateOn = state.truncateOn
    targetWallRadius = np.sqrt(state.requestedAreaRatio) * state.throatRadiusNonDimensional
    targetWallPressure = state.targetExitPressure

    # The length reference: a 15 degree half-angle cone of the SAME AREA RATIO, which is how NASA
    # SP-8120 defines percent bell. Taking it from the requested area ratio rather than from a
    # one-dimensional Mach number matters: at this operating point the two differ by 12 per cent in
    # length, because the ideal Mach number is a perfect-gas inverse of a pressure that CEA
    # computed with equilibrium chemistry, and the area ratio it corresponds to is 48.5 rather than
    # the 40 that was asked for.
    referenceConeLength    = conicalLength(state.requestedAreaRatio, state.throatRadiusNonDimensional)
    targetNozzleLength     = referenceConeLength * lengthFraction
    state.referenceConeLength = referenceConeLength

    # Calculate scaling factor (to revert back to real units after the non-dimensional design process)
    state.nozzleScalingFactor = throatScalingFactor(state.engineMassFlow, state.chamberPressure,
                                                   state.throatGamma, state.chamberRGasConstant,
                                                   state.chamberStagnationTemperature)

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    # -- Generate Initial Characteristic (Sauer's Solution) -- #
    #-----------------------------------------------------------------------------------------------------------------------------------------#

    # print(f'Generating Initial Characteristic via Sauer\'s Solution')

    # Define throat curvature using Rao throat assumption
    # Rao diverging throat ends, by definition, at an angle equal to (1/4) of the prandtl-meyer angle at the exit mach number
    angleOfInflection = 0.25 * prandtlMeyerAngle(targetExitMach, state.chamberGamma)
    throatWallAngles  = np.linspace(np.deg2rad(1e-5), angleOfInflection, state.numCharacteristics - 1)
    throatWallAngles  = np.insert(throatWallAngles, 0, 0)
    throatWallX       = state.throatRadiusNonDimensional * state.throatOutletCurvatureNonDimensional * np.sin(throatWallAngles)
    throatWallR       = state.throatRadiusNonDimensional * (1 + state.throatOutletCurvatureNonDimensional) - \
                        state.throatRadiusNonDimensional * state.throatOutletCurvatureNonDimensional * np.cos(throatWallAngles)

    state.throatWallX, state.throatWallR = throatWallX, throatWallR
    state.throatWallAngles = throatWallAngles
    state.throatEndAngle = throatWallAngles[-1]

    # Generate initial node in mach net
    rLimitingCharacteristicIntersection, xLimitingCharacteristicIntersection, machLimitingCharacteristicIntersection \
    = limitingCharacteristicIntersection(gas, throat, 1, 0, throatWallX[1], throatWallR[1], isInitialNode = True)

    # Verify that the limiting characteristic intersects the throat of the nozzle
    machThroatIntersection, wallAngleThroatIntersection, xThroatIntersection, rThroatIntersection \
    = throatIntersection(gas, throat, machLimitingCharacteristicIntersection, 1e-16, xLimitingCharacteristicIntersection, rLimitingCharacteristicIntersection)

    # Initialize Arrays
    throatKernelMach, throatKernelFlowAngle, \
    throatKernelX, throatKernelR \
    = [np.zeros((state.numCharacteristics, state.numCharacteristics)) for _ in range(4)]

    # Store initial value for throat point
    throatKernelMach[0,0], throatKernelFlowAngle[0,0], \
    throatKernelX[0,0], throatKernelR[0,0] \
    = sauerLimitingCharacteristic(gas, throat, 1), 0, 0, 1

    limitingCharacteristicR = np.linspace(state.throatRadiusNonDimensional, 0, state.numCharacteristics)
    limitingCharacteristicX = np.zeros(state.numCharacteristics)
    for i in range(state.numCharacteristics):
        limitingCharacteristicX[i] = sauerLimitingCharacteristic(gas, throat, limitingCharacteristicR[i], returnAxialLocation = True)
        
    if state.plotsDocs.lower() == 'on':
        # Plot initial conditions
        plotLine(throatWallX, throatWallR, \
                    title = 'Characteristic Mesh Generation: Initial Conditions', \
                    xLabel = 'Non-Dimensional X', yLabel = 'Non-Dimensional R', \
                    lineStyle = '-', lineWidth = 2, markerStyle = '', color = 'w', fontSize = 22, \
                    label = 'Mesh Kernel')
        plt.gca().set_aspect('equal')
        plt.plot(limitingCharacteristicX, limitingCharacteristicR, \
                'y', linewidth = 2, label = 'Limiting Characteristic')
        plt.axhline(y = 0, color = 'w', linestyle = '--', linewidth = 2)
        plt.axvline(x = 0, color = 'w', linestyle = '--', linewidth = 2)
    
    if state.plotsDocs.lower() == 'on':
        # Plot to visualize throat wall and limiting characteristic intersection
        plotLine(throatWallX, throatWallR, \
                    title = 'Characteristic Mesh Generation: Throat Region', \
                    xLabel = 'Non-Dimensional X', yLabel = 'Non-Dimensional R', \
                    lineStyle = '-', lineWidth = 2, markerStyle = '', color = 'w', fontSize = 22, \
                    label = 'Throat Wall')
        plt.gca().set_aspect('equal')
        plt.gca().set_xlim([-0.01, 0.03])
        plt.gca().set_ylim([0.98, 1.01])
        plt.plot(xLimitingCharacteristicIntersection, rLimitingCharacteristicIntersection, \
                '*g', markersize = 12, label = 'Limiting Characteristic Intersection Location')
        plt.plot(xThroatIntersection, rThroatIntersection, \
                '*m', markersize = 6, label = 'Throat Wall Intersection Location')
        plt.plot(limitingCharacteristicX, limitingCharacteristicR, \
                'y', linewidth = 2, label = 'Limiting Characteristic')

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

    if state.plotsDocs.lower() == 'on':
        # Plot the throat kernel generation section
        plt.plot(throatKernelX[1,:2], throatKernelR[1,:2], \
                '*w', markersize = 22, label = 'Characteristic Mesh Start')
        arrowSize = 0.0001

    # Main throat kernel loop
    for i in np.arange(2, state.numCharacteristics):

        throatKernelX[i,i] = throatWallX[i]
        throatKernelR[i,i] = throatWallR[i]
        throatKernelFlowAngle[i,i] = throatWallAngles[i]

        # Predictor Step
        characteristicProjectionGeometry = [throatKernelFlowAngle[i-1,i-1], throatKernelX[i-1,i-1], throatKernelR[i-1,i-1], \
                                            throatKernelFlowAngle[i,i],     throatKernelX[i,i],     throatKernelR[i,i]]
        throatKernelMach[i,i], throatKernelMach[i, i-1], throatKernelFlowAngle[i, i-1], throatKernelX[i, i-1], throatKernelR[i, i-1] \
        = wallCharacteristicProjection(gas, throatKernelMach[i-1,i-1], characteristicProjectionGeometry)

        if state.plotsDocs.lower() == 'on':
            # Update throat kernel plot (Wall Characteristic Projection Point)
            plt.plot(throatKernelX[i,i-1], throatKernelR[i,i-1], '*r', markersize = 12)
            stop = 1

        for j in reversed(np.arange(2,i)):
            axMOCKernel = [throatKernelMach[i,j],     throatKernelFlowAngle[i,j],     throatKernelX[i,j],     throatKernelR[i,j], \
                           throatKernelMach[i-1,j-1], throatKernelFlowAngle[i-1,j-1], throatKernelX[i-1,j-1], throatKernelR[i-1,j-1]]
            throatKernelMach[i,j-1], throatKernelFlowAngle[i, j-1], throatKernelX[i, j-1], throatKernelR[i, j-1] \
            = axisymmetricMethodOfCharacteristics(gas, axMOCKernel)
            if state.plotsDocs.lower() == 'on':
                # Update throat kernel plot (Axisymmetrix Method of Characteristics for interior points PREDICTOR STEP)
                plt.plot(throatKernelX[i-1,j-1], throatKernelR[i-1,j-1], '*c', markersize = 12)
                plt.plot(throatKernelX[i,j], throatKernelR[i,j], '*m', markersize = 12)
                plt.plot(throatKernelX[i,j-1], throatKernelR[i,j-1], '*y', markersize = 12)
                plt.arrow(throatKernelX[i-1,j-1], throatKernelR[i-1,j-1],\
                        throatKernelX[i,j-1]-throatKernelX[i-1,j-1], throatKernelR[i,j-1]-throatKernelR[i-1,j-1], \
                        edgecolor = 'w', facecolor = 'c', width = arrowSize, length_includes_head = True)
                plt.arrow(throatKernelX[i,j], throatKernelR[i,j], \
                        throatKernelX[i,j-1]-throatKernelX[i,j], throatKernelR[i,j-1]-throatKernelR[i,j], \
                        edgecolor = 'w', facecolor = 'm', width = arrowSize, length_includes_head = True)
                stop = 1

        throatKernelR[i,0], throatKernelX[i,0], throatKernelMach[i,0] \
        = limitingCharacteristicIntersection(gas, throat, throatKernelMach[i,1], throatKernelFlowAngle[i,1], throatKernelX[i,1], throatKernelR[i,1])

        if state.plotsDocs.lower() == 'on':
            # Update throat kernel plot (Mesh intersection with Limiting characteristic)
            plt.plot(throatKernelX[i,0], throatKernelR[i,0], '*g', markersize = 12)
            stop = 1

        # Corrector Step
        for k in range(i-1):
            axMOCKernel = [throatKernelMach[i,k],     throatKernelFlowAngle[i,k],     throatKernelX[i,k],     throatKernelR[i,k], \
                           throatKernelMach[i-1,k+1], throatKernelFlowAngle[i-1,k+1], throatKernelX[i-1,k+1], throatKernelR[i-1,k+1]]
            throatKernelMach[i,k+1], throatKernelFlowAngle[i,k+1], throatKernelX[i,k+1], throatKernelR[i,k+1] \
            = axisymmetricMethodOfCharacteristics(gas, axMOCKernel)
            
            if state.plotsDocs.lower() == 'on':
                # Update throat kernel plot (Axisymmetrix Method of Characteristics for interior points CORRECTOR STEP)
                plt.plot(throatKernelX[i-1,k+1], throatKernelR[i-1,k+1], '*', color = 'tab:orange', markersize = 12)
                plt.plot(throatKernelX[i,k], throatKernelR[i,k], '*', color = 'tab:purple', markersize = 12)
                plt.plot(throatKernelX[i,k+1], throatKernelR[i,k+1], '*b', markersize = 12)
                plt.arrow(throatKernelX[i-1,k+1], throatKernelR[i-1,k+1],\
                        throatKernelX[i,k+1]-throatKernelX[i-1,k+1], throatKernelR[i,k+1]-throatKernelR[i-1,k+1], \
                        edgecolor = 'w', facecolor = 'tab:orange', width = arrowSize, length_includes_head = True)
                plt.arrow(throatKernelX[i,k], throatKernelR[i,k], \
                        throatKernelX[i,k+1]-throatKernelX[i,k], throatKernelR[i,k+1]-throatKernelR[i,k], \
                        edgecolor = 'w', facecolor = 'tab:purple', width = arrowSize, length_includes_head = True)
                stop = 1

        throatKernelMach[i,i], throatKernelFlowAngle[i,i], throatKernelX[i,i], throatKernelR[i,i] \
        = throatIntersection(gas, throat, throatKernelMach[i,i-1], throatKernelFlowAngle[i,i-1], throatKernelX[i,i-1], throatKernelR[i,i-1])

        if state.plotsDocs.lower() == 'on':
            # Update throat kernel plot (Mesh intersection with nozzle throat)
            plt.plot(throatKernelX[i,i], throatKernelR[i,i], '*g', markersize = 12)
            # Update the view window of the final plot to show entire throat kernel
            plt.gca().set_xlim([-0.01, 0.08])
            plt.gca().set_ylim([0.94, 1.01])
            stop = 1

    # Calculate wall properties in the throat region with isentropic relations
    throatWallMach, throatWallTemperature, \
    throatWallPressure, throatWallVelocity \
    = [np.zeros(state.numCharacteristics) for _ in range(4)]

    for i in range(state.numCharacteristics):
        throatWallMach[i] = throatKernelMach[i,i]
        throatWallTemperature[i], throatWallPressure[i], throatWallVelocity[i] \
        = isentropicValues(throatWallMach[i], state.chamberStagnationTemperature, state.chamberPressure, \
                            state.chamberGamma, state.chamberRGasConstant)

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
    numRows = int(2 * state.numCharacteristics + idealMeshSpacing - 2)

    # Initialize arrays for kernel
    expansionKernelMach, expansionKernelFlowAngle, \
    expansionKernelX, expansionKernelR \
    = [np.zeros((numRows, state.numCharacteristics)) for _ in range(4)]

    # Insert Sauer Compatibility initial values
    expansionKernelMach[:state.numCharacteristics, :state.numCharacteristics], expansionKernelFlowAngle[:state.numCharacteristics, :state.numCharacteristics], \
    expansionKernelX[:state.numCharacteristics, :state.numCharacteristics], expansionKernelR[:state.numCharacteristics, :state.numCharacteristics] \
    = [sauerStuff for sauerStuff in [throatKernelMach, throatKernelFlowAngle, throatKernelX, throatKernelR]]

    # Create initial right running characteristic
    axMOCKernel = [throatKernelMach[-1,1], -throatKernelFlowAngle[-1,1], throatKernelX[-1,1], -throatKernelR[-1,1], \
                    throatKernelMach[-1,1],  throatKernelFlowAngle[-1,1], throatKernelX[-1,1],  throatKernelR[-1,1]]
    initialRightRunningMach, initialRightRunningFlowAngle, initialRightRunningX, initialRightRunningR, *_ = \
    axisymmetricMethodOfCharacteristics(gas, axMOCKernel, numPoints = idealMeshSpacing)

    if state.plotsDocs.lower() == 'on':
        # Create a new plot to show the generation of the inner expansion mesh
        plotLine(expansionKernelX, expansionKernelR, \
                    title = 'Characteristic Mesh Generation: Inner Expansion Mesh', \
                    xLabel = 'Non-Dimensional X', yLabel = 'Non-Dimensional R', \
                    lineStyle = '', lineWidth = 2, markerStyle = '*', color = 'w', fontSize = 22, \
                    label = 'Mesh Kernel')
        plt.gca().set_aspect('equal')
        plt.plot(limitingCharacteristicX, limitingCharacteristicR, \
                'y', linewidth = 2, label = 'Limiting Characteristic')
        plt.axhline(y = 0, color = 'w', linestyle = '--', linewidth = 2)
        plt.plot(initialRightRunningX, initialRightRunningR, '*g', markersize = 12)
        # Update the view window of the plot to show zoomed region of interest
        plt.gca().set_xlim([-0.01, 0.10])
        plt.gca().set_ylim([0.88, 1.01])
        arrowSize = 0.0005

    # Insert stuff from initial right running characteristic
    expansionKernelMach[state.numCharacteristics:state.numCharacteristics+idealMeshSpacing, 1], expansionKernelFlowAngle[state.numCharacteristics:state.numCharacteristics+idealMeshSpacing, 1], \
    expansionKernelX[state.numCharacteristics:state.numCharacteristics+idealMeshSpacing, 1], expansionKernelR[state.numCharacteristics:state.numCharacteristics+idealMeshSpacing, 1] \
    = [rightStuff for rightStuff in [initialRightRunningMach, initialRightRunningFlowAngle, initialRightRunningX, initialRightRunningR]]

    # First loop: make points until the end of the right running characteristic
    for i in np.arange(state.numCharacteristics, state.numCharacteristics+idealMeshSpacing):
        for j in np.arange(1, state.numCharacteristics-1):
            axMOCKernel = [expansionKernelMach[i,j],     expansionKernelFlowAngle[i,j],     expansionKernelX[i,j],     expansionKernelR[i,j], \
                            expansionKernelMach[i-1,j+1], expansionKernelFlowAngle[i-1,j+1], expansionKernelX[i-1,j+1], expansionKernelR[i-1,j+1]]
            expansionKernelMach[i, j+1], expansionKernelFlowAngle[i, j+1], expansionKernelX[i, j+1], expansionKernelR[i, j+1] = \
            axisymmetricMethodOfCharacteristics(gas, axMOCKernel)
            
            if state.plotsDocs.lower() == 'on':
                # Update throat kernel plot (Axisymmetrix Method of Characteristics for Expansion Mesh down to axis)
                plt.plot(expansionKernelX[i-1,j+1], expansionKernelR[i-1,j+1], '*c', markersize = 12)
                plt.plot(expansionKernelX[i,j], expansionKernelR[i,j], '*m', markersize = 12)
                plt.plot(expansionKernelX[i,j+1], expansionKernelR[i,j+1], '*y', markersize = 12)
                plt.arrow(expansionKernelX[i-1,j+1], expansionKernelR[i-1,j+1],\
                        expansionKernelX[i,j+1]-expansionKernelX[i-1,j+1], expansionKernelR[i,j+1]-expansionKernelR[i-1,j+1], \
                        edgecolor = 'w', facecolor = 'c', width = arrowSize, length_includes_head = True)
                plt.arrow(expansionKernelX[i,j], expansionKernelR[i,j], \
                        expansionKernelX[i,j+1]-expansionKernelX[i,j], expansionKernelR[i,j+1]-expansionKernelR[i,j], \
                        edgecolor = 'w', facecolor = 'm', width = arrowSize, length_includes_head = True)
                stop = 1

    # Second loop: complete the rest of the points from the end of the C- characteristic down to the nozzle axis
    for i in np.arange(state.numCharacteristics+idealMeshSpacing, numRows):
        j = 2 - (state.numCharacteristics + idealMeshSpacing) + i
        axMOCKernel = [expansionKernelMach[i-1,j], -expansionKernelFlowAngle[i-1,j], expansionKernelX[i-1,j], -expansionKernelR[i-1,j], \
                        expansionKernelMach[i-1,j],  expansionKernelFlowAngle[i-1,j], expansionKernelX[i-1,j],  expansionKernelR[i-1,j]]
        expansionKernelMach[i, j], expansionKernelFlowAngle[i, j], expansionKernelX[i, j], expansionKernelR[i, j] = \
        axisymmetricMethodOfCharacteristics(gas, axMOCKernel)
        
        if state.plotsDocs.lower() == 'on':
            # Update throat kernel plot (Axisymmetrix Method of Characteristics for Expansion Mesh across axis)
            plt.plot(expansionKernelX[i-1,j], expansionKernelR[i-1,j],  '*', color = 'tab:orange', markersize = 12)
            plt.plot(expansionKernelX[i-1,j], -expansionKernelR[i-1,j],  '*', color = 'tab:purple', markersize = 12)
            plt.plot(expansionKernelX[i,j], expansionKernelR[i,j], '*b', markersize = 12)
            plt.arrow(expansionKernelX[i-1,j], expansionKernelR[i-1,j],\
                        expansionKernelX[i,j]-expansionKernelX[i-1,j], expansionKernelR[i,j]-expansionKernelR[i-1,j], \
                        edgecolor = 'w', facecolor = 'tab:orange', width = arrowSize, length_includes_head = True)
            plt.arrow(expansionKernelX[i-1,j], -expansionKernelR[i-1,j], \
                        expansionKernelX[i,j]-expansionKernelX[i-1,j], expansionKernelR[i,j]+expansionKernelR[i-1,j], \
                        edgecolor = 'w', facecolor = 'tab:purple', width = arrowSize, length_includes_head = True)
            stop = 1

        for j in np.arange(2 - (state.numCharacteristics + idealMeshSpacing) + i, state.numCharacteristics-1):
            axMOCKernel = [expansionKernelMach[i,j],     expansionKernelFlowAngle[i,j],     expansionKernelX[i,j],     expansionKernelR[i,j], \
                            expansionKernelMach[i-1,j+1], expansionKernelFlowAngle[i-1,j+1], expansionKernelX[i-1,j+1], expansionKernelR[i-1,j+1]]
            expansionKernelMach[i, j+1], expansionKernelFlowAngle[i, j+1], expansionKernelX[i, j+1], expansionKernelR[i, j+1] = \
            axisymmetricMethodOfCharacteristics(gas, axMOCKernel)
            
            if state.plotsDocs.lower() == 'on':
                # Update throat kernel plot (Axisymmetrix Method of Characteristics for expansion mesh inside axis)
                plt.plot(expansionKernelX[i,j], expansionKernelR[i,j],  '*', color = 'tab:orange', markersize = 12)
                plt.plot(expansionKernelX[i-1,j+1], expansionKernelR[i-1,j+1],  '*', color = 'tab:purple', markersize = 12)
                plt.plot(expansionKernelX[i,j+1], expansionKernelR[i,j+1], '*b', markersize = 12)
                plt.arrow(expansionKernelX[i,j], expansionKernelR[i,j],\
                            expansionKernelX[i,j+1]-expansionKernelX[i,j], expansionKernelR[i,j+1]-expansionKernelR[i,j], \
                            edgecolor = 'w', facecolor = 'tab:orange', width = arrowSize, length_includes_head = True)
                plt.arrow(expansionKernelX[i-1,j+1], expansionKernelR[i-1,j+1], \
                            expansionKernelX[i,j+1]-expansionKernelX[i-1,j+1], expansionKernelR[i,j+1]-expansionKernelR[i-1,j+1], \
                            edgecolor = 'w', facecolor = 'tab:purple', width = arrowSize, length_includes_head = True)
                stop = 1
    
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

    if state.plotsDocs.lower() == 'on':
        # Create a new plot to show the generation of the inner expansion mesh
        plotLine(expansionKernelX, expansionKernelR, \
                       title = 'Characteristic Mesh Generation: Flow Straightening Section', \
                       xLabel = 'Non-Dimensional X', yLabel = 'Non-Dimensional R', \
                       lineStyle = '', lineWidth = 2, markerStyle = '*', color = 'w', fontSize = 22, \
                       label = 'Mesh Kernel')
        plt.gca().set_aspect('equal')
        plt.plot(exitAxisArray, exitRadiusArray, \
                '-*y', linewidth = 2, label = 'Exit Line')
        arrowSize = 0.0005

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

                if state.plotsDocs.lower() == 'on':
                    # Update throat kernel plot (Axisymmetrix Method of Characteristics for Flow Straightening Section)
                    plt.plot(flowStraighteningX[i,jMesh], flowStraighteningR[i,jMesh], '*c', markersize = 12)
                    plt.plot(flowStraighteningX[i+1,jMesh+1], flowStraighteningR[i+1,jMesh+1], '*m', markersize = 12)
                    plt.plot(flowStraighteningX[i,jMesh+1], flowStraighteningR[i,jMesh+1], '*y', markersize = 12)
                    plt.arrow(flowStraighteningX[i,jMesh], flowStraighteningR[i,jMesh],\
                            flowStraighteningX[i,jMesh+1]-flowStraighteningX[i,jMesh], flowStraighteningR[i,jMesh+1]-flowStraighteningR[i,jMesh], \
                            edgecolor = 'w', facecolor = 'c', width = arrowSize, length_includes_head = True)
                    plt.arrow(flowStraighteningX[i+1,jMesh+1], flowStraighteningR[i+1,jMesh+1], \
                            flowStraighteningX[i,jMesh+1]-flowStraighteningX[i+1,jMesh+1], flowStraighteningR[i,jMesh+1]-flowStraighteningR[i+1,jMesh+1], \
                            edgecolor = 'w', facecolor = 'm', width = arrowSize, length_includes_head = True)
                    stop = 1
            
            jMesh += 1

        if state.plotsDocs.lower() == 'on':
            # Change view for plot to view wall point calculations
            plt.gca().set_xlim([0, 0.125])
            plt.gca().set_ylim([0.975, 1.02])
            
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
            
            # Only truncate when a truncation criterion has been given. Otherwise the wall runs out
            # to the end of the mach net, which is the full-length ideal contour.
            if isPressureMatching:

                # Which quantity binds decides which of the requested design numbers is delivered
                # and which is a result. Truncating on radius delivers the requested area ratio and
                # reports the length; truncating on length delivers the requested length and
                # reports whatever area ratio it lands on.
                if truncateOn == 'areaRatio':
                    reached = rNozzleWall[index] >= targetWallRadius
                    if reached:
                        fraction = ((targetWallRadius - rNozzleWall[index-1])
                                    / (rNozzleWall[index] - rNozzleWall[index-1]))
                        rTruncate = targetWallRadius
                        xTruncate = xNozzleWall[index-1] + fraction * (xNozzleWall[index] - xNozzleWall[index-1])
                elif truncateOn == 'wallPressure':
                    # Cut where the wall static pressure falls to the ambient the engine runs at.
                    #
                    # This is the maximum-thrust criterion, and the wall is the right station for
                    # it rather than any average over the exit plane. Extending the wall by a ring
                    # adds an axial force of (P_wall - ambient) times the ring's projected area, so
                    # the nozzle gains thrust exactly while the wall pressure exceeds ambient and
                    # loses it after. Nothing about the plane average enters that statement; the
                    # average describes the flow leaving, the wall pressure describes the surface
                    # the force acts on.
                    reached = pressureNozzleWall[index] <= targetWallPressure
                    if reached:
                        fraction = ((pressureNozzleWall[index-1] - targetWallPressure)
                                    / (pressureNozzleWall[index-1] - pressureNozzleWall[index]))
                        xTruncate = xNozzleWall[index-1] + fraction * (xNozzleWall[index] - xNozzleWall[index-1])
                        rTruncate = rNozzleWall[index-1] + fraction * (rNozzleWall[index] - rNozzleWall[index-1])
                else:
                    reached = xNozzleWall[index] >= targetNozzleLength
                    if reached:
                        fraction = ((targetNozzleLength - xNozzleWall[index-1])
                                    / (xNozzleWall[index] - xNozzleWall[index-1]))
                        xTruncate = targetNozzleLength
                        wallSlope = (rNozzleWall[index] - rNozzleWall[index-1]) / (xNozzleWall[index] - xNozzleWall[index-1])
                        wallIntercept = rNozzleWall[index] - xNozzleWall[index] * wallSlope
                        rTruncate = wallSlope * targetNozzleLength + wallIntercept

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

    if state.plotsDocs.lower() == 'on':
        # Create a new plot to show the generation of the inner expansion mesh
        plotLine(expansionKernelX, expansionKernelR, \
                       title = 'Characteristic Mesh Generation: Wall Contour Definition', \
                       xLabel = 'Non-Dimensional X', yLabel = 'Non-Dimensional R', \
                       lineStyle = '', lineWidth = 2, markerStyle = '*', color = 'w', fontSize = 22, \
                       label = 'Mesh Kernel')
        plt.gca().set_aspect('equal')
        plt.plot(exitAxisArray, exitRadiusArray, \
                '-*y', linewidth = 2, label = 'Exit Line')
        plt.plot(flowStraighteningX, flowStraighteningR, '*c')
        plt.plot(xNozzleWall, rNozzleWall, 'g', linewidth = 4)

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

        iExit, jExit = iContourPrevious, jContourPrevious
        terminated = False

        xExitPlane = xNozzleWall[-1]
        rExitPlane, flowAngleExitPlane, machNumberExitPlane \
        = [np.zeros(4 * (numContourElements - 1)) for _ in range(3)]

        rExitPlane[0], machNumberExitPlane[0], flowAngleExitPlane[0] \
        = rNozzleWall[-1], machNumberNozzleWall[-1], flowStraighteningFlowAngle[iExit,jExit]

        index = 0

        while iExit < (numContourElements - 2) and jExit > 0:

            index += 1

            if flowStraighteningX[iExit+1,jExit] >= xExitPlane:
                characteristicSlope = (flowStraighteningR[iExit+1,jExit] - flowStraighteningR[iExit,jExit]) / (flowStraighteningX[iExit+1,jExit] - flowStraighteningX[iExit,jExit])
                characteristicYIntercept = flowStraighteningR[iExit,jExit] - characteristicSlope * flowStraighteningX[iExit,jExit]
                rExitPlane[index] = characteristicSlope * xExitPlane + characteristicYIntercept
                machNumberExitPlane[index] = flowStraighteningMachNumber[iExit,jExit] + (flowStraighteningMachNumber[iExit+1,jExit] - flowStraighteningMachNumber[iExit,jExit]) / \
                                                (flowStraighteningX[iExit+1,jExit] - flowStraighteningX[iExit,jExit]) * (xExitPlane - flowStraighteningX[iExit,jExit])
                flowAngleExitPlane[index] = flowStraighteningFlowAngle[iExit,jExit] + (flowStraighteningFlowAngle[iExit+1,jExit]-flowStraighteningFlowAngle[iExit,jExit]) / \
                                            (flowStraighteningX[iExit+1,jExit] - flowStraighteningX[iExit,jExit]) * (xExitPlane - flowStraighteningX[iExit,jExit])
                jExit -= 1
            else:
                characteristicSlope = (flowStraighteningR[iExit+1,jExit+1] - flowStraighteningR[iExit+1,jExit]) / (flowStraighteningX[iExit+1,jExit+1] - flowStraighteningX[iExit+1,jExit])
                characteristicYIntercept = flowStraighteningR[iExit+1,jExit] - characteristicSlope * flowStraighteningX[iExit+1,jExit]
                rExitPlane[index] = characteristicSlope * xExitPlane + characteristicYIntercept
                machNumberExitPlane[index] = flowStraighteningMachNumber[iExit+1,jExit] + (flowStraighteningMachNumber[iExit+1,jExit+1] - flowStraighteningMachNumber[iExit+1,jExit]) / \
                                                (flowStraighteningX[iExit+1,jExit+1] - flowStraighteningX[iExit+1,jExit]) * (xExitPlane - flowStraighteningX[iExit+1,jExit])
                flowAngleExitPlane[index] = flowStraighteningFlowAngle[iExit+1,jExit] + (flowStraighteningFlowAngle[iExit+1,jExit+1] - flowStraighteningFlowAngle[iExit+1,jExit]) / \
                                            (flowStraighteningX[iExit+1,jExit+1] - flowStraighteningX[iExit+1,jExit]) * (xExitPlane - flowStraighteningX[iExit+1,jExit])
                iExit += 1

        if expansionKernelX[-1,-1] >= xExitPlane:
            offset = (numContourElements - 1) - iExit
            kernelRows, kernelCols = expansionKernelX.shape
            iExit = kernelRows - offset - 1
            jExit = kernelCols - 2
        
            while not terminated:

                index += 1
        
                # Check for centerline intercept
                if abs(expansionKernelR[iExit+1,jExit]) < 1e-3:
                    terminated = True 
        
                if expansionKernelX[iExit+1,jExit] >= xExitPlane:
                    characteristicSlope = (expansionKernelR[iExit+1,jExit]-expansionKernelR[iExit,jExit]) / (expansionKernelX[iExit+1,jExit] - expansionKernelX[iExit,jExit])
                    characteristicYIntercept = expansionKernelR[iExit,jExit] - characteristicSlope * expansionKernelX[iExit,jExit]
                    rExitPlane[index] = characteristicSlope * xExitPlane + characteristicYIntercept
                    machNumberExitPlane[index] = expansionKernelMach[iExit,jExit] + (expansionKernelMach[iExit+1,jExit] - expansionKernelMach[iExit,jExit]) / \
                                                    (expansionKernelX[iExit+1,jExit] - expansionKernelX[iExit,jExit]) * (xExitPlane - expansionKernelX[iExit,jExit]) 
                    flowAngleExitPlane[index] = expansionKernelFlowAngle[iExit,jExit] + (expansionKernelFlowAngle[iExit+1,jExit] - expansionKernelFlowAngle[iExit,jExit]) / \
                                                (expansionKernelX[iExit+1,jExit] - expansionKernelX[iExit,jExit]) * (xExitPlane - expansionKernelX[iExit,jExit])
                    jExit -= 1
                else:
                    characteristicSlope = (expansionKernelR[iExit+1,jExit+1] - expansionKernelR[iExit+1,jExit]) / (expansionKernelX[iExit+1,jExit+1] - expansionKernelX[iExit+1,jExit]) 
                    characteristicYIntercept = expansionKernelR[iExit+1,jExit] - characteristicSlope * expansionKernelX[iExit+1,jExit]
                    rExitPlane[index] = characteristicSlope * xExitPlane + characteristicYIntercept 
                    machNumberExitPlane[index] = expansionKernelMach[iExit+1,jExit] + (expansionKernelMach[iExit+1,jExit+1] - expansionKernelMach[iExit+1,jExit]) / \
                                                    (expansionKernelX[iExit+1,jExit+1] - expansionKernelX[iExit+1,jExit]) * (xExitPlane - expansionKernelX[iExit+1,jExit]) 
                    flowAngleExitPlane[index] = expansionKernelFlowAngle[iExit+1,jExit] + (expansionKernelFlowAngle[iExit+1,jExit+1] - expansionKernelFlowAngle[iExit+1,jExit]) / \
                                                (expansionKernelX[iExit+1,jExit+1] - expansionKernelX[iExit+1,jExit]) * (xExitPlane - expansionKernelX[iExit+1,jExit])
                    iExit += 1

        # Truncate unused elements
        rExitPlane = rExitPlane[:index]
        machNumberExitPlane = machNumberExitPlane[:index]
        flowAngleExitPlane = flowAngleExitPlane[:index]

        # The walk descends through the mesh from the wall and runs out of columns before it
        # reaches the axis, typically around a quarter of the exit radius. That leaves a core
        # carrying roughly eight per cent of the exit AREA unsampled, and because the thrust
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

        # Thrust Coefficient Integration
        exitArea = np.pi * rNozzleWall[-1]**2
        exitPressure = np.zeros(len(rExitPlane))
        _, exitPressure[0], _ = isentropicValues(machNumberExitPlane[0], state.chamberStagnationTemperature, state.chamberPressure, state.chamberGamma, state.chamberRGasConstant)

        velocityTermThrustCoef, pressureTermThrustCoef = 0, 0

        for i in range(index-1):

            differentialCSArea = np.pi * (rExitPlane[i]**2 - rExitPlane[i+1]**2)
            _, exitPressure[i+1], _ = isentropicValues(machNumberExitPlane[i+1], state.chamberStagnationTemperature, state.chamberPressure, state.chamberGamma, state.chamberRGasConstant)
            averagePressureBetweenNodes = (exitPressure[i+1] + exitPressure[i]) / 2
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
            # The thrust coefficient normalises by the throat AREA, pi rt^2, which is where the
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

        # Mass through the exit plane against mass through the choked throat. The two must agree:
        # the same flow passes both, and nothing is added or removed between them. Any departure is
        # discretisation, in the mesh or in this integration, and it is the only measure of the
        # solution's quality that needs nothing outside it.
        chokedFlow = (state.chamberPressure * np.pi * state.throatRadiusNonDimensional ** 2
                      * np.sqrt(state.throatGamma
                                / (state.chamberRGasConstant * state.chamberStagnationTemperature)
                                * (2 / (state.throatGamma + 1))
                                ** ((state.throatGamma + 1) / (state.throatGamma - 1))))
        state.exitMassClosure = float(state.exitMassFlux / chokedFlow)

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

        # Initialize arrays to be the same size as the mach field
        state.allPressures    = copy.deepcopy(state.allMachNumbers)
        state.allTemperatures = copy.deepcopy(state.allMachNumbers)

        for i in range(3):
            for j in range(state.allMachNumbers[i].shape[0]):
                for k in range(state.allMachNumbers[i].shape[1]):
                    state.allTemperatures[i][j,k], state.allPressures[i][j,k], _ = isentropicValues(state.allMachNumbers[i][j,k],
                                                                                state.chamberStagnationTemperature, state.chamberPressure, state.chamberGamma, state.chamberRGasConstant)

    if state.plotsDocs.lower() == 'on':
        # Plot the exit plane properties
        plotLine(xNozzleWall, rNozzleWall, \
                        title = 'Exit Plane Integration: Calculating Thrust Coefficient', \
                        xLabel = 'Non-Dimensional X', yLabel = 'Non-Dimensional R', \
                        lineStyle = '-', lineWidth = 2, markerStyle = '', color = 'w', fontSize = 22, \
                        label = 'Nozzle Contour')
        plt.axvline(xExitPlane, ymin = rExitPlane[-1], ymax = rExitPlane[0], color = 'w', linestyle = '--', linewidth = 2)
        plt.axhline(0, color = 'w', linestyle = '--', linewidth = 2)
        plt.plot(limitingCharacteristicX, limitingCharacteristicR, \
            'y', linewidth = 2, label = 'Limiting Characteristic')
        for i in range(3):
            plt.contourf(state.allXPoints[i], state.allRPoints[i], state.allMachNumbers[i], levels = np.arange(0.5, 1 + state.idealMachNumber, 0.1).tolist())
            # plt.quiver(state.allXPoints[i], state.allRPoints[i], np.cos(state.allFlowAngles[i]), np.sin(state.allFlowAngles[i]), color = 'r')
        for i, _ in enumerate(rExitPlane):
            plt.arrow(xExitPlane, rExitPlane[i], \
                        0.1 * (machNumberExitPlane[i]/calculatedExitMach)*np.cos(flowAngleExitPlane[i]), \
                        0.1 * (machNumberExitPlane[i]/calculatedExitMach)*np.sin(flowAngleExitPlane[i]), \
                        edgecolor = 'w', facecolor = 'r', width = 0.005, length_includes_head = True)
        plt.gca().set_aspect('equal')

    # Spline over non-dimensional nozzle arrays and make the points evenly spaced
    xNozzleWallOld, rNozzleWallOld = xNozzleWall, rNozzleWall
    xNozzleWall, rNozzleWall = arcSpline(xNozzleWallOld, rNozzleWallOld, newNumPoints = state.numContourPoints)

    # Scale the nozzle coordinates into real space
    xNozzleWallScaled, rNozzleWallScaled = xNozzleWall * state.nozzleScalingFactor, rNozzleWall * state.nozzleScalingFactor

    # Resample the near-wall state onto the evenly spaced contour.
    #
    # Only the Mach number is interpolated. The other three are isentropic functions of it at fixed
    # stagnation conditions, so deriving them here rather than interpolating each separately makes
    # the four arrays consistent with each other by construction. Interpolating all four
    # independently leaves them satisfying the relation they came from only where the relation
    # happens to be linear, which near the throat it is not.
    #
    # s = 0 makes the spline interpolate. Without it UnivariateSpline smooths, and its default
    # smoothing factor is an absolute residual budget of one per data point, so what happens to an
    # array depends on the magnitude of its values rather than on its shape. Pressure in pascals
    # is untouched; Mach number, being of order one, is fitted by a single straight line through
    # the whole wall and comes out reading 18 per cent high at the exit and 1.9 at the throat.
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
    state.pressureError = abs(pressureNozzleWall[-1] - state.targetExitPressure)

    # What the contour delivered. These are measured off the wall that was built, so a design that
    # misses what it was asked for says so rather than reporting the request back.
    throatIndex = int(np.argmin(rNozzleWall))
    state.deliveredAreaRatio = float((rNozzleWall[-1] / rNozzleWall[throatIndex]) ** 2)
    state.deliveredLengthFraction = float((xNozzleWall[-1] - xNozzleWall[throatIndex])
                                          / conicalLength(state.deliveredAreaRatio,
                                                          rNozzleWall[throatIndex]))
    state.inflectionWallAngle, state.exitWallAngle, _ = wallAnglesFromContour(
        xNozzleWall[throatIndex:], rNozzleWall[throatIndex:])

    return state

#--------------------------------------------------------------------------------------------------------------------------#
# -- Reference contours -- #
#--------------------------------------------------------------------------------------------------------------------------#

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
        Throat radius in metres, from `throatScalingFactor` [m].
    numPoints : int
        Points along the wall.
    conicalHalfAngle : float
        Cone half angle [deg].

    Returns:
    --------
    tuple : (x, r) wall coordinates in metres

    '''

    exitRadius = np.sqrt(areaRatio) * throat.throatRadius
    coneLength = conicalLength(areaRatio, throat.throatRadius, np.radians(conicalHalfAngle))

    x = np.linspace(0, coneLength, numPoints) * scalingFactor
    r = np.linspace(throat.throatRadius, exitRadius, numPoints) * scalingFactor
    return x, r

# Initial and final wall angles for the Rao canted-parabola contour, in degrees, against area ratio
# and percent bell. This is a DIGITISATION of figure 5(b) of NASA SP-8120, which itself reproduces
# Rao (1960); it is not the primary source and carries at least one transcription error, the
# non-monotone theta_n between area ratios 40 and 50 at 60 per cent bell. SP-8120 further states
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

    Inflection and exit wall angles for a thrust-optimised parabolic contour.

    Read from the digitised chart above, bilinearly in log area ratio and linearly in percent bell.
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

    Rao's canted-parabola approximation to the thrust-optimised contour.

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
        Throat radius in metres [m]
    numPoints : int
        Points along the returned wall
    wallAngles : tuple
        (thetaInflection, thetaExit) in radians, to override the chart lookup

    Returns:
    --------
    tuple : (x, r) wall coordinates in metres, from the throat plane to the exit

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
    arcR      = throat.exitArcRadius * np.sin(arcAngles) + throat.exitArcCentreRadius

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

    Both come from `np.gradient`, which is a centred second-order difference in the interior and a
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
        Wall coordinates, in metres, running from the chamber through the throat.
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

    Which quantity binds is set by `truncateOn`.

    With `areaRatio`, the wall is cut at the requested expansion ratio and the design Mach
    number is varied until the length that falls out is the requested fraction of the 15 degree
    conical reference. Both requested numbers are then delivered, and the exit pressure is a
    result.

    With `length`, the wall is cut at the requested length instead, and the design Mach number
    is varied until the wall static pressure at that cut equals the target exit pressure. Note
    what that residual is: a single station, at the wall, compared against a one-dimensional
    value. The exit plane of a truncated contour is not uniform, and the wall is its extreme
    point rather than its average, so this mode delivers neither the requested area ratio nor
    an exit plane at the target pressure. It is kept because it is what earlier designs were
    built with.

    Parameters:
    -----------
    lengthFraction : float | str
        Requested length as a fraction of the 15 degree cone of the same area ratio. A string
        instead sweeps for the fraction that maximises the thrust coefficient.
    lowerBound, upperBound : float
        Bounds on the length fraction for the sweep.

    '''

    warnings.filterwarnings('ignore')

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
        thrustCoefficient = nozzle.truncatedIdealContour(optimizedTargetMach, lengthFraction, isPressureMatching = True, assignOutputsToObject = True)

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
        if nozzle.plotsDebug == 'on':
            plt.style.use('dark_background')

            # Mach Contours
            fig = plt.figure(figsize=(12, 8))

            plt.plot(nozzle.xNozzleWall, nozzle.rNozzleWall, 'w', label = 'Nozzle Contour')
            plt.plot(nozzle.xNozzleWall, -nozzle.rNozzleWall, 'w')

            maskedX, maskedR, maskedMach = [], [], []
            for i in range(3):
                maskedX.append(np.ma.masked_where(np.isnan(nozzle.allXPoints[i]), nozzle.allXPoints[i]))
                maskedR.append(np.ma.masked_where(np.isnan(nozzle.allRPoints[i]), nozzle.allRPoints[i]))
                maskedMach.append(np.ma.masked_where(np.isnan(nozzle.allMachNumbers[i]), nozzle.allMachNumbers[i]))
            levels = np.arange(0.5, nozzle.idealMachNumber, 0.1)
            cmap = plt.colormaps['plasma'].with_extremes(under = 'magenta', over = 'cyan')
            for i in range(3):                
                contour = plt.contourf(maskedX[i]*nozzle.nozzleScalingFactor, 
                            maskedR[i]*nozzle.nozzleScalingFactor, 
                            maskedMach[i], 
                            levels = levels,
                            cmap = cmap,
                            extend = 'max')
                plt.contourf(maskedX[i]*nozzle.nozzleScalingFactor, 
                            -maskedR[i]*nozzle.nozzleScalingFactor, 
                            maskedMach[i], 
                            levels = levels,
                            cmap = cmap,
                            extend = 'max')
            plt.colorbar(contour, label = 'Mach Number', orientation = 'horizontal', pad = 0.10, fraction = 0.05, aspect = 60)

            plt.gca().set_aspect('equal')
            plt.gca().set_title('Mach Contours')
            plt.gca().set_xlabel('Nozzle Axis [m]')
            plt.gca().set_ylabel('Nozzle Radius [m]')
            plt.show(block = False)

            # Pressure Field
            fig = plt.figure(figsize=(12, 8))

            plt.plot(nozzle.xNozzleWall, nozzle.rNozzleWall, 'w', label = 'Nozzle Contour')
            plt.plot(nozzle.xNozzleWall, -nozzle.rNozzleWall, 'w')

            maskedPressure = []
            for i in range(3):
                maskedPressure.append(np.ma.masked_where(np.isnan(nozzle.allPressures[i]), nozzle.allPressures[i]))
            levels = np.arange(nozzle.targetExitPressure, maskedPressure[0].max(), 1e4)
            cmap = plt.colormaps['coolwarm'].with_extremes(under = 'cyan', over = 'magenta')
            for i in range(3):                
                contour = plt.contourf(maskedX[i]*nozzle.nozzleScalingFactor, 
                            maskedR[i]*nozzle.nozzleScalingFactor, 
                            maskedPressure[i], 
                            levels = levels,
                            cmap = cmap,
                            extend = 'min')
                plt.contourf(maskedX[i]*nozzle.nozzleScalingFactor, 
                            -maskedR[i]*nozzle.nozzleScalingFactor, 
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

            debug = 1

    # User has requested to find the ideal length fraction that maximizes thrust coefficient
    elif isinstance(lengthFraction, str):

            print(f'Optimizing nozzle length fraction to maximize thrust coefficient at a target exit pressure of {nozzle.targetExitPressure:.2f} [Pa]:')

            optimizedLengthFraction = minimize_scalar(convergeToExitPressure,
                                                      args = (True),
                                                      bounds = (lowerBound, upperBound)).x

            # Run the objective function with the optimized values and plot the result
            convergeToExitPressure(optimizedLengthFraction)

            # Hide the plots
            if nozzle.plotsDebug == 'on':

                plt.style.use('dark_background')

                # Mach Contours
                fig = plt.figure(figsize=(12, 8))

                plt.plot(nozzle.xNozzleWall, nozzle.rNozzleWall, 'w', label = 'Nozzle Contour')
                plt.plot(nozzle.xNozzleWall, -nozzle.rNozzleWall, 'w')

                maskedX, maskedR, maskedMach = [], [], []
                for i in range(3):
                    maskedX.append(np.ma.masked_where(np.isnan(nozzle.allXPoints[i]), nozzle.allXPoints[i]))
                    maskedR.append(np.ma.masked_where(np.isnan(nozzle.allRPoints[i]), nozzle.allRPoints[i]))
                    maskedMach.append(np.ma.masked_where(np.isnan(nozzle.allMachNumbers[i]), nozzle.allMachNumbers[i]))
                levels = np.arange(0.5, nozzle.idealMachNumber, 0.1)
                cmap = plt.colormaps['plasma'].with_extremes(under = 'magenta', over = 'cyan')
                for i in range(3):                
                    contour = plt.contourf(maskedX[i]*nozzle.nozzleScalingFactor, 
                                maskedR[i]*nozzle.nozzleScalingFactor, 
                                maskedMach[i], 
                                levels = levels,
                                cmap = cmap,
                                extend = 'max')
                    plt.contourf(maskedX[i]*nozzle.nozzleScalingFactor, 
                                -maskedR[i]*nozzle.nozzleScalingFactor, 
                                maskedMach[i], 
                                levels = levels,
                                cmap = cmap,
                                extend = 'max')
                plt.colorbar(contour, label = 'Mach Number', orientation = 'horizontal', pad = 0.10, fraction = 0.05, aspect = 60)

                plt.gca().set_aspect('equal')
                plt.gca().set_title('Mach Contours')
                plt.gca().set_xlabel('Nozzle Axis [m]')
                plt.gca().set_ylabel('Nozzle Radius [m]')
                plt.show(block = False)

                # Pressure Field
                fig = plt.figure(figsize=(12, 8))

                plt.plot(nozzle.xNozzleWall, nozzle.rNozzleWall, 'w', label = 'Nozzle Contour')
                plt.plot(nozzle.xNozzleWall, -nozzle.rNozzleWall, 'w')

                maskedPressure = []
                for i in range(3):
                    maskedPressure.append(np.ma.masked_where(np.isnan(nozzle.allPressures[i]), nozzle.allPressures[i]))
                levels = np.arange(nozzle.targetExitPressure, maskedPressure[0].max(), 1e4)
                cmap = plt.colormaps['coolwarm'].with_extremes(under = 'cyan', over = 'magenta')
                for i in range(3):                
                    contour = plt.contourf(maskedX[i]*nozzle.nozzleScalingFactor, 
                                maskedR[i]*nozzle.nozzleScalingFactor, 
                                maskedPressure[i], 
                                levels = levels,
                                cmap = cmap,
                                extend = 'min')
                    plt.contourf(maskedX[i]*nozzle.nozzleScalingFactor, 
                                -maskedR[i]*nozzle.nozzleScalingFactor, 
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

                debug = 1
