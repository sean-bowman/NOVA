
# -- Method of Characteristics Unit Processes -- #

'''

The unit processes of the axisymmetric method of characteristics.

A characteristics solution is built from a small number of point calculations, repeated. Given the
state at two upstream points, find the state where their characteristics cross. Given one upstream
point and a wall, find where the characteristic meets the wall. Everything larger, a kernel, a
contour, a plume, is those calculations driven in a particular order over a particular boundary.

This module holds the calculations. It holds no meshes, no geometry and no design intent, and it
reads nothing off a Nozzle object: the gas is passed in explicitly as a `CharacteristicGas`, so the
same function serves the nozzle interior and the plume beyond the lip. That matters more than it
sounds. A plume march that continues a nozzle solution has to reproduce the nozzle's own arithmetic
exactly, or it stops being one solution and becomes a second approximation of the first, and the
only way to guarantee that is for both to call the same function.

The axisymmetric compatibility relations do not reduce to algebra the way the planar ones do,
because of the term in the radial coordinate. They are solved here in the velocity formulation,
iterated with characteristic properties averaged along each characteristic rather than taken at the
upstream point, which is what makes the scheme second order.

Angles are in radians, lengths are non-dimensional against the throat radius, velocities are in
metres per second, and Mach numbers are dimensionless.

Author: Sean Bowman
Date:   09/06/2026

'''

import numpy as np
import sympy as sym
from scipy.optimize import fsolve, least_squares

try:
    from gasDynamics import prandtlMeyerAngle
except ImportError:
    from .gasDynamics import prandtlMeyerAngle

class CharacteristicGas:

    '''

    The gas a characteristics net is solved in.

    Holds the four quantities every unit process needs and nothing else. Constructed once per
    solve and passed down, so that a net can never be built with one gamma and read back with
    another.

    Parameters:
    -----------
    gamma : float
        Ratio of specific heats [-]
    gasConstant : float
        Specific gas constant [J/kg-K]
    stagnationTemperature : float
        Chamber stagnation temperature [K]

    '''

    def __init__(self, gamma: float, gasConstant: float, stagnationTemperature: float):
        self.gamma                 = gamma
        self.gasConstant           = gasConstant
        self.stagnationTemperature = stagnationTemperature
        # Velocity a streamline would reach expanding to zero temperature. The velocity
        # formulation is written against this, so it is carried rather than recomputed.
        self.maxAdiabaticVelocity  = np.sqrt(gamma * gasConstant) * \
                                     np.sqrt(2 * stagnationTemperature / (gamma - 1))

    def __repr__(self):
        return (f'CharacteristicGas(gamma = {self.gamma:.6f}, '
                f'gasConstant = {self.gasConstant:.2f}, '
                f'stagnationTemperature = {self.stagnationTemperature:.1f})')

    def prandtlMeyerAngle(self, mach: float) -> float:

        '''

        Prandtl-Meyer angle at this gas's ratio of specific heats [rad].

        '''

        return prandtlMeyerAngle(mach, self.gamma)

    def localTemperature(self, mach: float) -> float:

        '''

        Static temperature at a Mach number, from the isentropic relation [K].

        '''

        return self.stagnationTemperature / (1 + (self.gamma - 1) / 2 * mach**2)

    def localVelocity(self, mach: float) -> float:

        '''

        Local flow speed at a Mach number [m/s].

        '''

        return np.sqrt(self.gamma * self.gasConstant * self.localTemperature(mach)) * mach

    def machFromVelocity(self, velocity: float) -> float:

        '''

        Mach number corresponding to a flow speed, through the maximum adiabatic velocity [-].

        '''

        ratio = (velocity / self.maxAdiabaticVelocity)**2
        return np.sqrt((2 / (self.gamma - 1)) * (ratio / (1 - ratio)))

def axisymmetricMethodOfCharacteristics(gas: CharacteristicGas, kernel: tuple,
                                        numPoints: int = 1) -> tuple:

    '''

    Solve for the state where the characteristics from two upstream points cross.

    Given the Mach number, flow angle and position of two upstream points, one carrying the
    left-running characteristic and one the right-running, return the state at their intersection.
    Because the flow is axisymmetric the compatibility equations carry a term in the radial
    coordinate and cannot be reduced to algebra, so the intersection is found by iteration: the
    characteristic slopes are re-evaluated from the new state, the intersection moves, and the
    cycle repeats until the axial position stops moving.

    With `numPoints` greater than one the routine also records the intermediate states it passed
    through on the way, which is how a run of points along a characteristic is generated from a
    single call.

    Parameters:
    -----------
    gas : CharacteristicGas
        The gas the net is solved in.
    kernel : tuple
        (mach1, flowAngle1, x1, r1, mach2, flowAngle2, x2, r2), point 1 carrying the left-running
        characteristic and point 2 the right-running.
    numPoints : int
        1 returns the intersection alone. Above 1, returns the run of intermediate points on each
        characteristic, ordered from the upstream point to the intersection.

    Returns:
    --------
    tuple
        numPoints == 1: (mach, flowAngle, x, r) at the intersection.
        numPoints > 1: the right-running run then the left-running run, each as
        (mach, flowAngle, x, r) arrays.

    '''

    # Unpack kernel input array
    machNumber1, flowAngle1, xPoint1, rPoint1, \
    machNumber2, flowAngle2, xPoint2, rPoint2 = [var for var in kernel]

    # Calculate mach angles and local temperature and velocity
    machAngle1        = np.arcsin(1 / machNumber1)
    machAngle2        = np.arcsin(1 / machNumber2)

    localTemperature1 = gas.stagnationTemperature / (1 + (gas.gamma - 1)/2 * machNumber1**2)
    localTemperature2 = gas.stagnationTemperature / (1 + (gas.gamma - 1)/2 * machNumber2**2)

    localVelocity1    = np.sqrt(gas.gamma * gas.gasConstant * localTemperature1) * machNumber1
    localVelocity2    = np.sqrt(gas.gamma * gas.gasConstant * localTemperature2) * machNumber2

    # Calculate non-dimensional velocity
    nonDimensionalVelocity1 = (1/np.tan(machAngle1))/localVelocity1
    nonDimensionalVelocity2 = (1/np.tan(machAngle2))/localVelocity2

    # Calculate long terms that are a part of the left and right compatibility equations
    leftRunningTerm  = np.sin(flowAngle1) * np.sin(machAngle1) / (np.sin(flowAngle1 + machAngle1))
    rightRunningTerm = np.sin(flowAngle2) * np.sin(machAngle2) / (np.sin(flowAngle2 - machAngle2))

    # Initialize arrays
    if numPoints != 1:
        numPreAllocatedArrays = 8
        machNumberLeftRunning, flowAngleLeftRunning, \
        xPointsLeftRunning, rPointsLeftRunning, \
        machNumberRightRunning, flowAngleRightRunning, \
        xPointsRightRunning, rPointsRightRunning \
        = [np.zeros(numPoints) for _ in range(numPreAllocatedArrays)]

        xPointsLeftRunning[-1],  rPointsLeftRunning[-1]  = xPoint1, rPoint1
        xPointsRightRunning[-1], rPointsRightRunning[-1] = xPoint2, rPoint2

    # Initialize iteration variables and convergence parameters
    iterator, jterator = 0, numPoints
    converged, tolerance = False, 1e-8
    xPrevious = 0
    if numPoints == 1:
        maxIterator = 20
    else:
        maxIterator = 4 * numPoints

    while not converged:

        # Left and right running characteristic slope
        slopeLeftRunning  = np.tan(flowAngle1 + machAngle1)
        slopeRightRunning = np.tan(flowAngle2 - machAngle2)

        # Find (x, r) coordinate of intersection
        xIntersection = (rPoint2 - rPoint1 - xPoint2*slopeRightRunning + xPoint1*slopeLeftRunning)/(slopeLeftRunning - slopeRightRunning)

        if numPoints == 1:

            rIntersection = rPoint1 + (xIntersection - xPoint1) * slopeLeftRunning

            # If kernel point 1 is near the centerline, we don't have reliable left-running properties and must update
            # flow angle and velocity using a different method:
            if np.abs(rPoint1) < 1e-10:
                intermediateParam = (1 / (nonDimensionalVelocity1 + nonDimensionalVelocity2)) * \
                                    (localVelocity1*nonDimensionalVelocity1 + localVelocity2*nonDimensionalVelocity2 + \
                                    (rightRunningTerm / rPoint2) * (rIntersection - rPoint2) + flowAngle2)
                A = sym.Matrix([[1, -nonDimensionalVelocity1/2,  -nonDimensionalVelocity1*localVelocity1/2], \
                                [ -1/(nonDimensionalVelocity1+ nonDimensionalVelocity2),  1, intermediateParam]])
                B = A.rref()
                flowAngleIntersection = float(B[0][2])
                velocityIntersection  = float(B[0][5])
            else:
                # Calculate flow properties at intersection
                velocityIntersection   = (1 / (nonDimensionalVelocity1 + nonDimensionalVelocity2)) * \
                                            (localVelocity1 * nonDimensionalVelocity1 + localVelocity2 * nonDimensionalVelocity2 + \
                                            (leftRunningTerm / rPoint1) * (rIntersection - rPoint1) + \
                                            (rightRunningTerm / rPoint2) * (rIntersection - rPoint2) + flowAngle2 - flowAngle1)
                flowAngleIntersection  = ((flowAngle1 + nonDimensionalVelocity1 * (velocityIntersection - localVelocity1) - \
                                            (leftRunningTerm / rPoint1) * (rIntersection - rPoint1)) + (flowAngle2 - nonDimensionalVelocity2 * \
                                            (velocityIntersection - localVelocity2) + (rightRunningTerm / rPoint2) * (rIntersection - rPoint2))) / 2
        else:

            rIntersection = max(1e-15, rPoint1 + (xIntersection - xPoint1) * slopeLeftRunning)

            # Calculate flow properties at intersection
            velocityIntersection   = (1 / (nonDimensionalVelocity1 + nonDimensionalVelocity2)) * \
                                    (localVelocity1 * nonDimensionalVelocity1 + localVelocity2 * nonDimensionalVelocity2 + \
                                    (leftRunningTerm / rPoint1) * (rIntersection - rPoint1) + (rightRunningTerm / rPoint2) * \
                                    (rIntersection - rPoint2) + flowAngle2 - flowAngle1)
            flowAngleIntersection  = ((flowAngle1 + nonDimensionalVelocity1 * (velocityIntersection - localVelocity1) - \
                                    (leftRunningTerm / rPoint1) * (rIntersection - rPoint1)) + (flowAngle2 - nonDimensionalVelocity2 * \
                                    (velocityIntersection - localVelocity2) + (rightRunningTerm / rPoint2) * (rIntersection - rPoint2))) / 2

        machNumberIntersection = np.sqrt((2/(gas.gamma - 1)) * (((velocityIntersection / gas.maxAdiabaticVelocity)**2) / \
                                                                        (1 - (velocityIntersection / gas.maxAdiabaticVelocity)**2)))
        machAngleIntersection  = np.arcsin(1 / machNumberIntersection)

        # Convergence check
        if ((np.abs(xIntersection - xPrevious) / xIntersection) < tolerance) or (iterator > maxIterator):
            converged = True
            break
        else:

            # Update jterator
            if jterator > 0 and numPoints > 1:
                weight = 1 / jterator
                jterator -= 1
            else:
                weight = 0.5

            # -- Update Left and Right Characteristic properties -- #

            # Weighted properties
            # Breaking each variable out because the list comprehension overhead is apparently high here
            flowAngle1 = weight * flowAngleIntersection + (1 - weight) * flowAngle1
            flowAngle2 = weight * flowAngleIntersection + (1 - weight) * flowAngle2

            machAngle1 = weight * machAngleIntersection + (1 - weight) * machAngle1
            machAngle2 = weight * machAngleIntersection + (1 - weight) * machAngle2

            xPoint1    = weight * xIntersection + (1 - weight) * xPoint1
            xPoint2    = weight * xIntersection + (1 - weight) * xPoint2

            rPoint1    = weight * rIntersection + (1 - weight) * rPoint1
            rPoint2    = weight * rIntersection + (1 - weight) * rPoint2

            # Derivative properties
            machNumber1       = 1 / np.sin(machAngle1)
            machNumber2       = 1 / np.sin(machAngle2)

            localTemperature1 = gas.stagnationTemperature / (1 + (gas.gamma - 1)/2 * machNumber1**2)
            localTemperature2 = gas.stagnationTemperature / (1 + (gas.gamma - 1)/2 * machNumber2**2)

            localVelocity1    = np.sqrt(gas.gamma * gas.gasConstant * localTemperature1) * machNumber1
            localVelocity2    = np.sqrt(gas.gamma * gas.gasConstant * localTemperature2) * machNumber2

            # Calculate non-dimensional velocity
            nonDimensionalVelocity1 = (1/np.tan(machAngle1))/localVelocity1
            nonDimensionalVelocity2 = (1/np.tan(machAngle2))/localVelocity2

            # Calculate long terms that are a part of the left and right compatibility equations
            leftRunningTerm  = np.sin(flowAngle1) * np.sin(machAngle1) / (np.sin(flowAngle1 + machAngle1))
            rightRunningTerm = np.sin(flowAngle2) * np.sin(machAngle2) / (np.sin(flowAngle2 - machAngle2))

            # If we still have a positive jterator, append properties to arrays
            if jterator > 0 and numPoints > 1:
                machNumberLeftRunning[jterator], machNumberRightRunning[jterator] = machNumber1, machNumber2
                flowAngleLeftRunning[jterator],  flowAngleRightRunning[jterator]  = flowAngle1, flowAngle2
                xPointsLeftRunning[jterator],    xPointsRightRunning[jterator]    = xPoint1, xPoint2
                rPointsLeftRunning[jterator],    rPointsRightRunning[jterator]    = rPoint1, rPoint2

            # Update convergence properties
            xPrevious = xIntersection
            iterator += 1

    if numPoints == 1:
        return machNumberIntersection, flowAngleIntersection, xIntersection, rIntersection
    else:
        # Append final calculated point to beginning of each array
        machNumberLeftRunning[0], machNumberRightRunning[0] = machNumberIntersection, machNumberIntersection
        flowAngleLeftRunning[0],  flowAngleRightRunning[0]  = flowAngleIntersection, flowAngleIntersection
        xPointsLeftRunning[0],    xPointsRightRunning[0]    = xIntersection, xIntersection
        rPointsLeftRunning[0],    rPointsRightRunning[0]    = rIntersection, rIntersection
        # Flip each array around back to front before returning
        machNumberLeftRunning, machNumberRightRunning = np.flip(machNumberLeftRunning), np.flip(machNumberRightRunning)
        flowAngleLeftRunning,  flowAngleRightRunning  = np.flip(flowAngleRightRunning), np.flip(flowAngleRightRunning)
        xPointsLeftRunning,    xPointsRightRunning    = np.flip(xPointsLeftRunning),    np.flip(xPointsRightRunning)
        rPointsLeftRunning,    rPointsRightRunning    = np.flip(rPointsLeftRunning),    np.flip(rPointsRightRunning)
        return machNumberRightRunning, flowAngleRightRunning, xPointsRightRunning, rPointsRightRunning, \
                machNumberLeftRunning, flowAngleLeftRunning, xPointsLeftRunning, rPointsLeftRunning

def wallCharacteristicProjection(gas: CharacteristicGas, machNumber1: float,
                                 characteristicLinesGeometry: tuple) -> tuple:

    '''

    Solve for the state at a characteristic intersection whose geometry is known but whose Mach
    number is known at only one of the two upstream points.

    This is the situation on a wall. The wall position is prescribed, so the intersection is fixed
    by geometry, but the state there has to satisfy both compatibility relations at once. The two
    residuals are driven to zero together in the Mach number and flow angle at the new point.

    Parameters:
    -----------
    gas : CharacteristicGas
        The gas the net is solved in.
    machNumber1 : float
        Mach number at the first upstream point [-].
    characteristicLinesGeometry : tuple
        (flowAngle1, x1, r1, flowAngle2, x2, r2).

    Returns:
    --------
    tuple
        (machAtIntersection, optimisedMach, optimisedFlowAngle, xIntersection, rIntersection)

    '''

    def wallCompatibilityEquations(controlVariables: tuple, machNumber1: float,
                                   characteristicLinesGeometry: tuple,
                                   isZeroing: bool = False):

        '''

        Residual of the two compatibility relations at a trial state, or the state itself.

        '''

        # Unpack geometry inputs
        machGuess, flowAngleGuess                                            = [x for x in controlVariables]
        flowAnglePoint1, xPoint1, rPoint1, flowAnglePoint2, xPoint2, rPoint2 = [x for x in characteristicLinesGeometry]

        # Find characteristic intersection location
        machAngle1, machAngleGuess                 = np.arcsin(1 / machNumber1), np.arcsin(1 / machGuess)
        prandtlMeyerAngle1, prandtlMeyerAngleGuess = gas.prandtlMeyerAngle(machNumber1), gas.prandtlMeyerAngle(machGuess)

        averageFlowAngle, averageMachAngle = (flowAnglePoint1 + flowAngleGuess) / 2, \
                                             (machAngle1 + machAngleGuess) / 2

        slopeRightRunningCharacteristic, slopeLeftRunningCharacteristic = np.tan(averageFlowAngle - averageMachAngle), \
                                                                          np.tan(flowAngleGuess + machAngleGuess)

        interceptRightRunningCharacteristic, interceptLeftRunningCharacteristic = rPoint1 - slopeRightRunningCharacteristic * xPoint1, \
                                                                                  rPoint2 - slopeLeftRunningCharacteristic  * xPoint2

        xPointIntersection = (interceptRightRunningCharacteristic - interceptLeftRunningCharacteristic) / \
                             (slopeLeftRunningCharacteristic - slopeRightRunningCharacteristic)
        rPointIntersection = (slopeLeftRunningCharacteristic * xPointIntersection + interceptLeftRunningCharacteristic + \
                              slopeRightRunningCharacteristic * xPointIntersection + interceptRightRunningCharacteristic) / 2

        # Calculate mach number at new point
        machNumberFunction     = lambda machNumber: (-1 / (np.sqrt(machNumber**2 - 1) + (1/np.tan(flowAnglePoint2))))* \
                                                    ((rPoint2 - rPointIntersection) / rPoint2) - ((flowAnglePoint2 - \
                                                    gas.prandtlMeyerAngle(machNumber)) - (flowAngleGuess - prandtlMeyerAngleGuess))
        machNumberIntersection = fsolve(machNumberFunction, machNumber1)[0]

        # Solve compatibility equations to compute residuals to be minimized
        prandtlMeyerAngleIntersection = gas.prandtlMeyerAngle(machNumberIntersection)

        # Compatibility equation on Right Running Characteristic (C-)
        residualRightRunning = (1 / (np.sqrt(machGuess**2 - 1) - (1/np.tan(flowAngleGuess))))* \
                               ((rPointIntersection - rPoint1) / rPointIntersection) - ((flowAngleGuess + prandtlMeyerAngleGuess) - \
                               (flowAnglePoint1 + prandtlMeyerAngle1))
        # Compatibility equation on Left Running Characteristic (C+)
        residualLeftRunning  = (-1 / (np.sqrt(machGuess**2 - 1) + (1/np.tan(flowAngleGuess))))* \
                               ((rPointIntersection - rPoint2) / rPointIntersection) - ((flowAngleGuess - prandtlMeyerAngleGuess) - \
                               (flowAnglePoint2 - prandtlMeyerAngleIntersection))

        residual             = np.sqrt(residualRightRunning**2 + residualLeftRunning**2)

        if isZeroing:
            return residual
        else:
            return machNumberIntersection, xPointIntersection, rPointIntersection

    # Unpack geometry inputs
    flowAnglePoint1, xPoint1, rPoint1, flowAnglePoint2, xPoint2, rPoint2 = [x for x in characteristicLinesGeometry]

    guessControlVariables      = [machNumber1, (flowAnglePoint1 + flowAnglePoint2)/2]

    # Define anonymous function to calculate projection point and Mach number
    wallCompatibilityObjective = lambda controlVariables: wallCompatibilityEquations(controlVariables, machNumber1, characteristicLinesGeometry, isZeroing = True)

    optimizedControlVariables  = least_squares(wallCompatibilityObjective, x0 = guessControlVariables, method = 'trf').x

    # Calculate and return final residual-minimized wall point and mach number
    machNumberIntersection, xPointIntersection, rPointIntersection = wallCompatibilityEquations(optimizedControlVariables, machNumber1, characteristicLinesGeometry)

    return machNumberIntersection, optimizedControlVariables[0], optimizedControlVariables[1], xPointIntersection, rPointIntersection
