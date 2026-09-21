
# -- Throat Geometry and the Characteristic Mesh Kernel -- #

'''

The throat, the transonic starting line, and the intersections that seed a characteristics net.

A characteristics march cannot start at the throat, because the flow there is sonic and the
characteristics are degenerate. It starts on a line a short distance downstream where the flow
is already supersonic and where its state is known from a transonic solution rather than from
the march. Everything in this module exists to produce that line and the first few points off
it.

The transonic solution is Sauer's. It is the leading term of a series that Hall, and Kliegel
and Quan, later extended; their first-order throat conditions are identical to his, and the
solutions separate away from the throat plane, which is exactly where the starting line is
drawn. NASA SP-8120's recommendation at this throat curvature ratio names a 29-term series, but
that count belongs to a reference-streamline inverse method in a proprietary program, where
terms buy a close fit to the requested wall rather than order of accuracy. It is not a target
for the asymptotic series below. The monograph's second permitted route is Kliegel and Levine,
which is this family, and whose series its authors found non-convergent at higher
approximations. So the choice of Sauer alone is a real and measurable simplification rather
than a matter of taste. See
`docs/NozzleContourMethods.md` for the size of the omitted term.

The throat wall is Rao's: a circular entrant arc of 1.5 throat radii meeting a circular exit
arc of 0.382 throat radii at the throat plane. Those two numbers are the same ones the
thrust-optimized parabolic construction uses, so a contour built here and a published bell
start from the same throat.

Lengths are non-dimensional against the throat radius. Angles are in radians.

Author: Sean Bowman
Date:   09/06/2026

'''

import numpy as np
from scipy.optimize import fsolve

from .characteristics import CharacteristicGas
from .gasDynamics import prandtlMeyerAngle

# Transonic models the starting line may be built on, in the order they refine each other.
transonicModels = ('sauer', 'secondOrder', 'smallRadius')

def transonicThroatVelocity(gamma: float, curvature: float, model: str = 'sauer') -> float:

    '''

    Axial velocity at the throat wall, normalized by the sonic speed.

    The one number every transonic solution in this family agrees on how to write. Kliegel and
    Quan give it as a series in inverse powers of the throat wall radius of curvature, normalized
    by the throat radius:

        u(0,1) = 1 + 1/(4R) + (14 gamma + 15)/(288 R^2) + O(R^-3)

    and state that the first-order term is identical to Sauer's and to Hall's, and the
    second-order term identical to Hall's. So the models below are not three different theories:
    they are the same series truncated in different places, and one rearrangement of it.

    NOVA's Sauer implementation reproduces the first term exactly rather than approximately, which
    is worth knowing because it means the higher orders can be carried into it by one number.
    Working its flow parameter through its own limiting characteristic gives a throat wall
    velocity of `1 + ((gamma + 1) / 8) * alpha^2`, and with Sauer's alpha that is `1 + 1/(4R)` to
    machine precision at every gamma and curvature tried.

    The models
    ----------

    `sauer` keeps the first term alone. It is what NOVA has always used and remains the default,
    so selecting nothing changes nothing.

    `secondOrder` adds the term Hall and Kliegel and Quan agree on. At the commonly used curvature
    of 1.5 it is 29 percent as large as the term it corrects, which is the number
    `docs/NozzleContourMethods.md` quotes as the size of the simplification.

    `smallRadius` is the same two terms rearranged into inverse powers of `R + 1` rather than of
    `R`. Written in `R` the series misbehaves as the throat sharpens: taken literally it maximizes
    near a curvature of 1 and returns a SUBSONIC throat wall below about 0.5, which is not a
    physical answer. The rearrangement matches the same asymptotic terms at large curvature and
    stays finite and supersonic at small. That is the correction Kliegel and Quan give in their
    Appendix B and Kliegel and Levine extend, and it is what SP-8120 points to at small radii.

    It is a rearrangement matching the published terms rather than a transcription of either
    paper: the coefficients of their own recast forms are not in the reference set. Where the two
    would differ is beyond the second order, and that difference is not represented here.

    Parameters:
    -----------
    gamma : float
        Ratio of specific heats [-].
    curvature : float
        Throat wall radius of curvature as a multiple of the throat radius [-]. The entrant arc.
    model : str
        One of `transonicModels`.

    Returns:
    --------
    float : u / a* at the throat wall

    Raises:
    -------
    ValueError
        On an unknown model, rather than silently returning Sauer.

    '''

    if curvature <= 0.0:
        raise ValueError(f'A throat curvature has to be positive, not {curvature}.')

    firstOrder  = 0.25
    secondOrder = (14.0 * gamma + 15.0) / 288.0

    if model == 'sauer':
        return 1.0 + firstOrder / curvature
    if model == 'secondOrder':
        return 1.0 + firstOrder / curvature + secondOrder / curvature**2
    if model == 'smallRadius':
        # Coefficients chosen so the expansion in 1/curvature reproduces the two terms above:
        # with s = R + 1, A/s contributes A/R - A/R^2 and B/s^2 contributes B/R^2, so A is the
        # first-order coefficient and B is the second-order one plus A.
        shifted = curvature + 1.0
        return 1.0 + firstOrder / shifted + (secondOrder + firstOrder) / shifted**2

    raise ValueError(f"No transonic model called '{model}'. Choose from {transonicModels}.")

def sauerFlowParameterFor(gamma: float, throatRadius: float, throatVelocity: float) -> float:

    '''

    The Sauer flow parameter that puts a given velocity on the throat wall.

    Sauer's solution carries its throat condition entirely in one constant, so a higher-order
    throat velocity can be imposed on it by inverting for that constant rather than by rewriting
    the solution. From `u = 1 + ((gamma + 1) / 8) * alpha^2` at the wall,

        alpha = sqrt(8 (u - 1) / (gamma + 1))

    What this does and does not buy is worth being exact about. It makes the starting line carry
    the throat condition of whichever model was asked for, and the throat conditions are the part
    of the series that is independent of nozzle shape and therefore universally valid. It does NOT
    give the higher-order solution away from the throat plane, which is where the models genuinely
    differ and where a starting line is actually drawn. So this is the throat condition of a
    better solution wearing Sauer's spatial form, and the residual is the shape of the sonic line
    rather than its anchor.

    Parameters:
    -----------
    gamma : float
        Ratio of specific heats [-].
    throatRadius : float
        Throat radius, non-dimensional [-].
    throatVelocity : float
        Target `u / a*` at the throat wall, from `transonicThroatVelocity`.

    Returns:
    --------
    float : the flow parameter

    '''

    if throatVelocity <= 1.0:
        raise ValueError(f'A throat wall velocity has to be supersonic, not {throatVelocity}. '
                         f'A series that returns this has been taken outside its range.')
    return float(np.sqrt(8.0 * (throatVelocity - 1.0) / (gamma + 1.0)) / throatRadius**0)

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
                 outletCurvature: float = 0.382, transonicModel: str = 'sauer'):
        self.gamma           = gamma
        self.throatRadius    = throatRadius
        self.inletCurvature  = inletCurvature
        self.outletCurvature = outletCurvature
        self.transonicModel  = transonicModel

        # Sauer's two constants: the flow parameter that scales the transonic velocity
        # perturbation, and the axial offset of the sonic point on the axis ahead of the geometric
        # throat. The second follows from the first, as `epsilon = ((gamma + 1) / 8) alpha Rt^2`,
        # so they cannot be set independently and a model that moves one moves both.
        #
        # `sauer` reproduces the closed forms this class always used, to the bit. The other models
        # keep Sauer's spatial form and put a higher-order throat velocity on its wall; see
        # `sauerFlowParameterFor` for what that does and does not capture.
        self.throatWallVelocity = transonicThroatVelocity(gamma, inletCurvature, transonicModel)

        # Both closed forms are kept exactly as this class has always written them, rather than
        # deriving the second from the first. They are equal in exact arithmetic, and in floating
        # point they are not: `((gamma + 1) / 8) alpha Rt^2` agrees with the form below to the last
        # bit at some gamma and misses it by one unit at others, and one unit here moves a
        # converged contour by parts in a billion. Selecting the default therefore has to reproduce
        # the original expressions, not a rearrangement of them.
        if transonicModel == 'sauer':
            self.sauerFlowParameter = np.sqrt(2 / ((gamma + 1) * throatRadius * inletCurvature))
            self.sauerEpsilon       = (throatRadius / 8) * np.sqrt(2 * (gamma + 1) * throatRadius / inletCurvature)
        else:
            # A higher-order throat velocity has no closed form in the curvature, so here the
            # offset does follow from the flow parameter. These models have no baseline to hold.
            self.sauerFlowParameter = sauerFlowParameterFor(gamma, throatRadius,
                                                            self.throatWallVelocity)
            self.sauerEpsilon       = ((gamma + 1) / 8) * self.sauerFlowParameter * throatRadius**2

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
    def exitArcCenterRadius(self) -> float:

        '''

        Radial position of the center of the downstream throat arc.

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

def wallIntersection(gas: CharacteristicGas, wall, machNumber: float, flowAngle: float,
                     xOrigin: float, rOrigin: float, minimumStation: float = 0.0,
                     numIterations: int = 1):

    '''

    Where a left-running characteristic meets a prescribed wall, and the state it lands in.

    The general form of `throatIntersection`. That routine answers this question for the circular
    throat arc, which is the only wall a truncated ideal contour knows in advance; a family whose
    whole wall is prescribed asks it at every wall point instead. The compatibility relation is
    the same one, unchanged. What the wall supplies is where the characteristic lands and what
    angle the surface is at when it gets there, both of which `PrescribedWall` answers in closed
    form rather than by iteration.

    `numIterations` is worth setting above one for a wall-bounded march. At one, the ray is drawn
    at the Mach angle of the upstream point alone, which is what `throatIntersection` does and is
    first order, inside a scheme that is second order everywhere else because the interior point
    averages its coefficients along the characteristic. On a throat arc that error is confined to
    a few very short steps. In a march where every line ends on the wall it applies at every wall
    point, and the wall is where the compression waves that coalesce into a bell's internal shock
    are generated, so the error carries into where the shock is predicted to form rather than
    staying in the wall.

    Parameters:
    -----------
    gas : CharacteristicGas
        The gas the net is solved in.
    wall : PrescribedWall
        The wall, from `wallGeometry`.
    machNumber : float
        Mach number at the origin of the characteristic [-].
    flowAngle : float
        Flow angle at the origin [rad].
    xOrigin, rOrigin : float
        Origin of the characteristic, non-dimensional.
    minimumStation : float
        Reject intersections at or before this station along the wall, which is how a ray that
        doubles back onto a segment the march has already passed is refused.
    numIterations : int
        1 draws the ray at the upstream state. Above 1 redraws it at the mean of the upstream and
        wall states, which restores second order.

    Returns:
    --------
    tuple : (mach, wallAngle, x, r, station), or False when the characteristic misses the wall

    '''

    machAngleOrigin        = np.arcsin(1 / machNumber)
    prandtlMeyerAngleOrigin = prandtlMeyerAngle(machNumber, gas.gamma)

    hit = wall.intersectRay(xOrigin, rOrigin, np.tan(flowAngle + machAngleOrigin), minimumStation)
    if hit is None:
        return False

    machAtWall = machNumber
    for iteration in range(max(1, numIterations)):

        x, r, wallAngle, station = hit

        # The compatibility relation along the characteristic, with the axisymmetric source term.
        # Identical to the one `throatIntersection` solves; only the wall angle and the landing
        # point come from somewhere else.
        compatibility = lambda mach: (-1 / (np.sqrt(mach**2 - 1) + (1 / np.tan(flowAngle)))) * \
                                     ((r - rOrigin) / r) - \
                                     ((wallAngle - prandtlMeyerAngle(mach, gas.gamma)) -
                                      (flowAngle - prandtlMeyerAngleOrigin))
        machAtWall = fsolve(compatibility, machNumber)[0]

        if iteration + 1 >= max(1, numIterations) or not np.isfinite(machAtWall) or machAtWall <= 1:
            break

        # Redraw the ray at the mean of its two ends and let the landing point move with it.
        meanFlowAngle = 0.5 * (flowAngle + wallAngle)
        meanMachAngle = 0.5 * (machAngleOrigin + np.arcsin(1 / machAtWall))
        refined = wall.intersectRay(xOrigin, rOrigin, np.tan(meanFlowAngle + meanMachAngle),
                                    minimumStation)
        if refined is None:
            break
        hit = refined

    x, r, wallAngle, station = hit
    return machAtWall, wallAngle, x, r, station

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
