
# -- Throat Geometry and the Characteristic Mesh Kernel -- #

'''

The throat, the transonic starting line, and the intersections that seed a characteristics net.

A characteristics march cannot start at the throat, because the flow there is sonic and the
characteristics are degenerate. It starts on a line a short distance downstream where the flow is
already supersonic and where its state is known from a transonic solution rather than from the
march. Everything in this module exists to produce that line and the first few points off it.

The transonic solution is Sauer's. It is the leading term of a series that Hall, and Kliegel and
Quan, later extended; their first-order throat conditions are identical to his, and the solutions
separate away from the throat plane, which is exactly where the starting line is drawn. NASA
SP-8120 recommends a 29-term series at the throat curvature ratio used here, so the choice of
Sauer alone is a real and measurable simplification rather than a matter of taste. See
`docs/NozzleContourMethods.md` for the size of the omitted term.

The throat wall is Rao's: a circular entrant arc of 1.5 throat radii meeting a circular exit arc
of 0.382 throat radii at the throat plane. Those two numbers are the same ones the thrust-optimised
parabolic construction uses, so a contour built here and a published bell start from the same
throat.

Lengths are non-dimensional against the throat radius. Angles are in radians.

Author: Sean Bowman
Date:   09/06/2026

'''

import numpy as np
from scipy.optimize import fsolve

try:
    from characteristics import CharacteristicGas
    from gasDynamics import prandtlMeyerAngle
except ImportError:
    from .characteristics import CharacteristicGas
    from .gasDynamics import prandtlMeyerAngle

class ThroatGeometry:

    '''

    The Rao throat: two circular arcs meeting at the throat plane, plus the two Sauer constants
    that follow from them.

    The entrant curvature sets the transonic solution, because the sonic line shape is fixed by the
    wall curvature approaching the throat. The exit curvature sets how fast the flow is turned once
    it is supersonic, and therefore where the characteristics net starts to spread.

    Parameters:
    -----------
    gamma : float
        Ratio of specific heats [-]
    throatRadius : float
        Throat radius, non-dimensional, conventionally 1 [-]
    inletCurvature : float
        Entrant arc radius as a multiple of the throat radius [-]
    outletCurvature : float
        Exit arc radius as a multiple of the throat radius [-]

    '''

    def __init__(self, gamma: float, throatRadius: float = 1.0, inletCurvature: float = 1.5,
                 outletCurvature: float = 0.382):
        self.gamma           = gamma
        self.throatRadius    = throatRadius
        self.inletCurvature  = inletCurvature
        self.outletCurvature = outletCurvature
        # Sauer's two constants: the axial offset of the sonic point on the axis ahead of the
        # geometric throat, and the flow parameter that scales the transonic velocity perturbation.
        self.sauerEpsilon       = (throatRadius / 8) * np.sqrt(2 * (gamma + 1) * throatRadius / inletCurvature)
        self.sauerFlowParameter = np.sqrt(2 / ((gamma + 1) * throatRadius * inletCurvature))

    def __repr__(self):
        return (f'ThroatGeometry(gamma = {self.gamma:.6f}, throatRadius = {self.throatRadius}, '
                f'inletCurvature = {self.inletCurvature}, '
                f'outletCurvature = {self.outletCurvature})')

    @property
    def exitArcRadius(self) -> float:

        '''

        Radius of the downstream throat arc in non-dimensional length, not as a multiple.

        '''

        return self.outletCurvature * self.throatRadius

    @property
    def exitArcCentreRadius(self) -> float:

        '''

        Radial position of the centre of the downstream throat arc.

        '''

        return self.throatRadius + self.outletCurvature * self.throatRadius

    def wallPoints(self, wallAngles: np.ndarray) -> tuple:

        '''

        Points on the downstream throat arc at a set of wall angles.

        The arc runs from the throat plane, where the wall is parallel to the axis, to the
        inflection point where the contoured wall takes over. Rao puts that inflection at one
        quarter of the Prandtl-Meyer angle of the design exit Mach number.

        Parameters:
        -----------
        wallAngles : np.ndarray
            Wall angles measured from the axis [rad], ascending from zero.

        Returns:
        --------
        tuple : (x, r) arrays on the arc, non-dimensional

        '''

        x = self.throatRadius * self.outletCurvature * np.sin(wallAngles)
        r = self.throatRadius * (1 + self.outletCurvature) - \
            self.throatRadius * self.outletCurvature * np.cos(wallAngles)
        return x, r

def sauerLimitingCharacteristic(gas: CharacteristicGas, throat: ThroatGeometry,
                                radiusOfInterest: float,
                                returnAxialLocation: bool = False) -> float:

    '''

    Sauer's transonic solution evaluated on the limiting characteristic.

    The limiting characteristic is the line downstream of the sonic line beyond which no
    disturbance can travel back upstream to the throat. It is where a supersonic march can validly
    begin. Sauer gives the axial velocity perturbation as a function of position near the throat;
    inverting it for Mach number at a given radius gives the starting state.

    Parameters:
    -----------
    gas : CharacteristicGas
        The gas the net is solved in.
    throat : ThroatGeometry
        Throat arcs and the Sauer constants derived from them.
    radiusOfInterest : float
        Radial station on the limiting characteristic [-].
    returnAxialLocation : bool
        True returns the axial position of the limiting characteristic at that radius instead of
        the Mach number, which is what drawing the line requires.

    Returns:
    --------
    float : Mach number at the station, or its axial position when returnAxialLocation is set

    '''

    sonicTemperature = gas.stagnationTemperature / (1 + (gas.gamma - 1)/2)
    sonicVelocity    = np.sqrt(gas.gamma * gas.gasConstant * sonicTemperature)

    axialLocationOfInterest = -((gas.gamma + 1) / 8) * throat.sauerFlowParameter * radiusOfInterest**2 + throat.sauerEpsilon
    axialVelocity           = sonicVelocity * (1 + (throat.sauerFlowParameter * (axialLocationOfInterest - throat.sauerEpsilon) + \
                                              ((gas.gamma + 1) / 4) * (throat.sauerFlowParameter * radiusOfInterest)**2))
    machNumberFunction      = lambda machNumber: np.sqrt(gas.gamma * gas.gasConstant * gas.stagnationTemperature / \
                                                 (1 + ((gas.gamma - 1) / 2) * machNumber**2)) * machNumber - axialVelocity
    # A small perturbation is added (1e-15) to ensure that the value 0 is never returned
    machNumberOfInterest    = fsolve(machNumberFunction, axialVelocity/sonicVelocity)[0] + 1e-15

    if returnAxialLocation:
        return axialLocationOfInterest
    else:
        return machNumberOfInterest

def limitingCharacteristicIntersection(gas: CharacteristicGas, throat: ThroatGeometry,
                                       machNumber: float, flowAngle: float,
                                       axialLocationOfInterest: float,
                                       radialLocationOfInterest: float,
                                       isInitialNode: bool = False) -> tuple:

    '''

    Where a right-running characteristic meets the limiting characteristic.

    Both curves are known: the characteristic from its origin point and local slope, the limiting
    characteristic from Sauer's solution. The intersection is solved in the radial coordinate
    because the limiting characteristic is single valued in radius and not in axial position.

    Parameters:
    -----------
    gas : CharacteristicGas
        The gas the net is solved in.
    throat : ThroatGeometry
        Throat arcs and the Sauer constants.
    machNumber : float
        Mach number at the origin of the characteristic [-].
    flowAngle : float
        Flow angle at the origin [rad].
    axialLocationOfInterest, radialLocationOfInterest : float
        Origin of the characteristic [-].
    isInitialNode : bool
        True for the very first node of the net, where the characteristic is drawn from the wall
        rather than from an interior point and the geometry is written the other way round.

    Returns:
    --------
    tuple : (radius, axialLocation, machNumber) at the intersection

    '''

    machAngle = np.arcsin(1 / machNumber)

    # Create anonymous function to find intersection point as a function of radius
    if isInitialNode is False:
        intersectionFunction = lambda radius: np.tan(0.5 * (flowAngle + machAngle + \
                                              np.arcsin(1 / sauerLimitingCharacteristic(gas, throat, radius)))) * \
                                              (throat.sauerEpsilon - axialLocationOfInterest - ((gas.gamma + 1) / 8) * throat.sauerFlowParameter * radius**2) + \
                                              radialLocationOfInterest - radius
    else:
        intersectionFunction = lambda radius: -((gas.gamma + 1) / 8) * throat.sauerFlowParameter * radius**2 + \
                                                throat.sauerEpsilon - (radius - (radialLocationOfInterest - \
                                                axialLocationOfInterest * np.tan(np.arcsin(1 / sauerLimitingCharacteristic(gas, throat, radius)))))/ \
                                                (np.tan(np.arcsin(1 / sauerLimitingCharacteristic(gas, throat, radius))))

    radiusOfIntersection        = fsolve(intersectionFunction, 1)[0]
    axialLocationOfIntersection = throat.sauerEpsilon - ((gas.gamma + 1) / 8) * throat.sauerFlowParameter * radiusOfIntersection**2
    machNumberAtIntersection    = sauerLimitingCharacteristic(gas, throat, radiusOfIntersection)

    return radiusOfIntersection, axialLocationOfIntersection, machNumberAtIntersection

def throatIntersection(gas: CharacteristicGas, throat: ThroatGeometry, machNumber: float,
                       flowAngle: float, xOrigin: float, rOrigin: float):

    '''

    Where a left-running characteristic meets the downstream throat arc.

    This is the wall point of the throat kernel: the characteristic leaves an interior point,
    strikes the circular arc, and the state where it lands follows from the compatibility relation
    along it together with the wall angle the arc prescribes there.

    Parameters:
    -----------
    gas : CharacteristicGas
        The gas the net is solved in.
    throat : ThroatGeometry
        Throat arcs.
    machNumber : float
        Mach number at the origin of the characteristic [-].
    flowAngle : float
        Flow angle at the origin [rad].
    xOrigin, rOrigin : float
        Origin of the characteristic [-].

    Returns:
    --------
    tuple : (mach, wallAngle, x, r) at the intersection, or False when the characteristic misses
    the arc entirely

    '''

    machAngle                      = np.arcsin(1 / machNumber)
    slopeLeftRunningCharacteristic = np.tan(flowAngle + machAngle)
    yIntercept                     = rOrigin - slopeLeftRunningCharacteristic * xOrigin
    throatIntersectionFunction     = lambda x: (-np.sqrt((throat.outletCurvature * throat.throatRadius)**2 - x**2) + \
                                                throat.throatRadius + throat.outletCurvature * throat.throatRadius - \
                                                slopeLeftRunningCharacteristic * x - yIntercept)
    axialLocationOfIntersection    = fsolve(throatIntersectionFunction, throat.throatRadius * throat.outletCurvature / 2)[0]

    if np.isnan(axialLocationOfIntersection):
        return False
    else:
        wallAngleAtIntersection                         = np.arctan(axialLocationOfIntersection / np.sqrt((throat.outletCurvature * throat.throatRadius)**2 - \
                                                                                    axialLocationOfIntersection**2))
        radialLocationOfIntersection                    = -np.sqrt((throat.outletCurvature * throat.throatRadius)**2 - \
                                                            axialLocationOfIntersection**2) + throat.throatRadius + \
                                                            throat.outletCurvature * throat.throatRadius
        prandtlMeyerAngleAtIntersection                 = prandtlMeyerAngle(machNumber, gas.gamma)
        compatibilityRightRunningCharacteristicFunction = lambda mach: (-1 / (np.sqrt(mach**2 - 1) + (1/np.tan(flowAngle))))* \
                                                                        ((radialLocationOfIntersection - rOrigin) / radialLocationOfIntersection) - \
                                                                        ((wallAngleAtIntersection - prandtlMeyerAngle(mach, gas.gamma)) - (flowAngle - prandtlMeyerAngleAtIntersection))
        machNumberAtIntersection                        = fsolve(compatibilityRightRunningCharacteristicFunction, machNumber)[0]

        return machNumberAtIntersection, wallAngleAtIntersection, axialLocationOfIntersection, radialLocationOfIntersection
