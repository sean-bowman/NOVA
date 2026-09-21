
# -- Elementary Gas Dynamics -- #

'''

Perfect-gas relations for steady isentropic flow of a calorically perfect gas.

These are the closed-form relations every other NOVA module builds on: the isentropic ratios and
the station state they resolve to, the Prandtl-Meyer function and its inverse, and the area-Mach
relation and its two branches. They are gathered here so that one expression serves the contour
solver, the plume march, the converging section and the validation scripts, rather than each
carrying its own copy to drift out of step with the others.

Every function takes gamma explicitly. Nothing here reads state off a Nozzle object. Nothing
here knows which gamma is the right one for a given station; that choice belongs to the caller
and is a real one, because a characteristics mesh built on the chamber gamma cannot be read
back under the exit gamma without breaking continuity at the plane where the two meet.

All angles are in radians. Mach numbers, pressure ratios and area ratios are dimensionless.

Author: Sean Bowman
Date:   09/06/2026

'''

import numpy as np
from scipy.optimize import brentq, fsolve

# -- Isentropic ratios -- #

def stagnationRatio(mach: float, gamma: float) -> float:

    '''

    The grouping 1 + (gamma - 1) / 2 * M^2 that every isentropic ratio is a power of.

    Parameters:
    -----------
    mach : float
        Local Mach number [-]
    gamma : float
        Ratio of specific heats [-]

    Returns:
    --------
    float : T0 / T [-]

    '''

    return 1.0 + 0.5 * (gamma - 1.0) * mach ** 2

def staticTemperatureRatio(mach: float, gamma: float) -> float:

    '''

    Static to stagnation temperature ratio T / T0 for isentropic flow.

    '''

    return 1.0 / stagnationRatio(mach, gamma)

def staticPressureRatio(mach: float, gamma: float) -> float:

    '''

    Static to stagnation pressure ratio P / P0 for isentropic flow.

    '''

    return stagnationRatio(mach, gamma) ** (-gamma / (gamma - 1.0))

def isentropicValues(mach: float, stagnationTemperature: float, stagnationPressure: float,
                     gamma: float, gasConstant: float) -> tuple:

    '''

    Static temperature, static pressure and velocity at a station from its Mach number and the
    stagnation state feeding it.

    Parameters:
    -----------
    mach : float
        Local Mach number [-]
    stagnationTemperature : float
        Stagnation temperature [K]
    stagnationPressure : float
        Stagnation pressure [Pa]
    gamma : float
        Ratio of specific heats [-]
    gasConstant : float
        Specific gas constant [J/(kg*K)]

    Returns:
    --------
    tuple : (temperature [K], pressure [Pa], velocity [m/s])

    '''

    temperature = stagnationTemperature / (1.0 + ((gamma - 1.0) / 2.0) * mach**2)
    pressure = stagnationPressure / (1.0 + ((gamma - 1.0) / 2.0) * mach**2)**(gamma / (gamma - 1.0))
    velocity = np.sqrt(gamma * gasConstant * temperature) * mach

    return temperature, pressure, velocity

def machFromPressureRatio(stagnationOverStatic: float, gamma: float) -> float:

    '''

    Mach number that isentropic expansion from a stagnation state reaches at a given
    stagnation-to-static pressure ratio.

    Parameters:
    -----------
    stagnationOverStatic : float
        P0 / P, must be >= 1
    gamma : float
        Ratio of specific heats

    Returns:
    --------
    float : Mach number, 0 when the ratio is at or below 1

    '''

    if stagnationOverStatic <= 1.0:
        return 0.0
    return float(np.sqrt(2.0 / (gamma - 1.0)
                         * (stagnationOverStatic**((gamma - 1.0) / gamma) - 1.0)))

# -- Choosing the one gamma a constant-gamma solve is run in -- #

def effectiveGamma(stagnationOverStatic: float, areaRatio: float,
                   lowerBound: float = 1.01, upperBound: float = 1.99) -> float:

    '''

    The gamma at which a calorically perfect gas reaches a given pressure ratio and area ratio
    together.

    A real exhaust has no single gamma. It recombines as it expands, so the isentropic exponent
    climbs along the nozzle, and a constant-gamma solve has to pick one value to stand for all of
    them. Taking the chamber value is the obvious choice and the worst one, because the chamber is
    where the gas is hottest and most dissociated and least like the gas doing the expanding.

    What this returns instead is the value that makes the two relations the contour is built from
    agree with each other at the design point. Given the chamber-to-exit pressure ratio and the
    area ratio that thermochemistry says produces it, there is one gamma for which

        areaMachRelation(machFromPressureRatio(pressureRatio, gamma), gamma) = areaRatio

    and it is bracketed by the chamber and exit values. Below the root the implied area ratio is
    too large, above it too small, so the function is monotone and the root is unique.

    **This is calibration, not physics.** The gas is still treated as calorically perfect and the
    characteristics mesh is still built on one exponent. What changes is that the exponent is
    chosen to reproduce an answer from the thermochemistry rather than lifted from one end of the
    expansion. It closes the design point exactly and says nothing about any other operating
    point; a contour run far from the pressure ratio it was calibrated at inherits the same error
    the chamber value carried.

    **It buys pressure and does not buy temperature, which is why it is not the default.** One
    exponent cannot reproduce both the pressure-area relation and the specific heat, and this one
    is fitted to the first. Measured against CEA on the LOX/LH2 reference engine over area ratios
    2 to 40, one-dimensionally so the comparison is like for like:

        static pressure       12.8 % mean absolute error at the chamber gamma, 4.2 % here
        static temperature    10.1 % at the chamber gamma, 11.0 % here

    Temperature is a wash in magnitude and not in sign. The chamber value runs the gas hot as it
    expands and this one runs it cold, and NOVA's thermal model reads its driving temperature off
    this same solve, so a cold bias undersizes a cooling jacket. Selecting it through
    `gammaModel` is therefore a decision about which answer is being asked for: it is the better
    exponent for contour geometry and performance, and the worse one for a jacket. Both are
    recorded on every run whichever is selected. Removing the choice means giving the
    characteristics solve local properties rather than one exponent, which is a different solver.

    Parameters:
    -----------
    stagnationOverStatic : float
        Chamber stagnation pressure over exit static pressure [-].
    areaRatio : float
        Exit area over throat area that the thermochemistry pairs with that pressure ratio [-].
    lowerBound, upperBound : float
        Bracket for the root find [-]. The defaults span every gas; narrowing them is only
        useful to catch a design point that has gone wrong somewhere earlier.

    Returns:
    --------
    float
        Ratio of specific heats reproducing both the pressure ratio and the area ratio [-].

    Raises:
    -------
    ValueError
        If the pressure ratio or area ratio is not supersonic, or if no gamma in the bracket
        reproduces the pair, which means the two did not come from the same expansion.

    '''

    if stagnationOverStatic <= 1.0 or areaRatio <= 1.0:
        raise ValueError('An effective gamma is defined by a supersonic expansion. A pressure '
                         'ratio of {:.4f} and an area ratio of {:.4f} do not describe '
                         'one.'.format(stagnationOverStatic, areaRatio))

    def mismatch(gamma):

        '''Area ratio the pressure ratio implies at this gamma, less the one asked for.'''

        return areaMachRelation(machFromPressureRatio(stagnationOverStatic, gamma),
                                gamma) - areaRatio

    lower, upper = mismatch(lowerBound), mismatch(upperBound)
    if lower * upper > 0.0:
        raise ValueError('No ratio of specific heats between {:.2f} and {:.2f} reaches an area '
                         'ratio of {:.4f} at a pressure ratio of {:.1f}. The two did not come '
                         'from the same expansion.'.format(lowerBound, upperBound, areaRatio,
                                                           stagnationOverStatic))

    return float(brentq(mismatch, lowerBound, upperBound, xtol = 1.0e-14, rtol = 1.0e-15))

# -- Characteristic angles -- #

def machAngle(mach: float) -> float:

    '''

    Mach angle mu = arcsin(1 / M) [rad]. The angle a characteristic makes with the local
    streamline, and therefore the reason a supersonic flow has characteristics at all.

    '''

    return float(np.arcsin(1.0 / mach))

def prandtlMeyerAngle(mach: float, gamma: float) -> float:

    '''

    Prandtl-Meyer function nu(M) [rad]. Zero at and below M = 1.

    Written in the textbook grouping, with (gamma - 1) / (gamma + 1) multiplying the Mach term
    rather than dividing it. The two groupings are algebraically the same and differ by a few units
    in the last place, which matters here: the contour's pressure match converges its target Mach
    number to a tolerance loose enough that a change of that size moves the delivered area ratio in
    the fourth decimal. One grouping, used everywhere, keeps that out of the results.

    '''

    if mach <= 1.0:
        return 0.0
    return (np.sqrt((gamma + 1.0) / (gamma - 1.0))
            * np.arctan(np.sqrt((gamma - 1.0) / (gamma + 1.0) * (mach**2 - 1.0)))
            - np.arctan(np.sqrt(mach**2 - 1.0)))

def machFromPrandtlMeyerAngle(angle: float, gamma: float, upperBound: float = 60.0) -> float:

    '''

    Invert the Prandtl-Meyer function.

    There is no closed form, so this brackets between sonic and `upperBound` and solves. The
    function is monotone above M = 1, so the bracket is guaranteed to hold as long as the target
    angle is below the limiting turning angle for the gas.

    Parameters:
    -----------
    angle : float
        Prandtl-Meyer angle [rad]
    gamma : float
        Ratio of specific heats [-]
    upperBound : float
        Highest Mach number to bracket against [-]

    Returns:
    --------
    float : Mach number [-], exactly 1 for a non-positive angle

    '''

    if angle <= 0.0:
        return 1.0
    limit = 0.5 * np.pi * (np.sqrt((gamma + 1.0) / (gamma - 1.0)) - 1.0)
    if angle >= limit:
        raise ValueError(f'A Prandtl-Meyer angle of {np.degrees(angle):.3f} deg is at or above the '
                         f'limiting turning angle of {np.degrees(limit):.3f} deg for gamma = '
                         f'{gamma:.4f}. No finite Mach number reaches it.')
    return float(brentq(lambda mach: prandtlMeyerAngle(mach, gamma) - angle,
                        1.0 + 1e-12, upperBound))

# -- Area-Mach relation -- #

def areaMachRelation(mach: float, gamma: float) -> float:

    '''

    Local area over sonic area, A / A*, for isentropic flow of a perfect gas.

    The relation every nozzle station satisfies, and the one a contour is checked against: a
    station of a given radius has exactly one subsonic and one supersonic Mach number consistent
    with it under quasi one-dimensional flow.

    Parameters:
    -----------
    mach : float
        Local Mach number [-]
    gamma : float
        Ratio of specific heats [-]

    Returns:
    --------
    float : A / A* [-]

    '''

    return (1 / mach) * ((2 / (gamma + 1)) * (1 + ((gamma - 1) / 2) * mach**2))\
           **((gamma + 1) / (2 * (gamma - 1)))

def radiusMachRelation(mach: float, gamma: float) -> float:

    '''

    Local radius over sonic radius for isentropic flow, the square root of the area relation.

    Useful directly because a contour is defined by radii, not areas.

    '''

    return float(np.sqrt(areaMachRelation(mach, gamma)))

def machFromAreaRatio(areaRatio: float, gamma: float, branch: str = 'supersonic',
                      upperBound: float = 60.0) -> float:

    '''

    Invert the area-Mach relation onto one of its two branches.

    Parameters:
    -----------
    areaRatio : float
        A / A*, must be >= 1
    gamma : float
        Ratio of specific heats [-]
    branch : str
        'supersonic' for the diverging branch, 'subsonic' for the converging branch
    upperBound : float
        Highest Mach number to bracket against on the supersonic branch [-]

    Returns:
    --------
    float : Mach number [-]

    '''

    residual = lambda mach: areaMachRelation(mach, gamma) - areaRatio

    if branch == 'supersonic':
        if areaRatio < 1.0:
            raise ValueError(f'An area ratio of {areaRatio:.6f} is below unity, so no supersonic '
                             f'solution exists.')
        if areaRatio == 1.0:
            return 1.0
        return float(brentq(residual, 1.0 + 1e-9, upperBound))

    if branch == 'subsonic':

        # An area ratio computed as a radius over the throat radius can land microscopically
        # below one at the throat itself, and below one this branch has no root for the solver
        # to find. Only that case is intercepted. An area ratio of exactly one still goes to the
        # solver on the guess and tolerances the converging section has always used, so every
        # station that already solved reaches the same answer to the bit.
        if areaRatio < 1.0:
            if areaRatio >= 1.0 - 1e-9:
                return 1.0
            raise ValueError(f'An area ratio of {areaRatio:.9f} is below the throat, so no '
                             f'subsonic solution exists.')

        result = fsolve(residual, 0.001, full_output = True, maxfev = 200, xtol = 1e-6)
        machNumber, exitFlag, message = result[0][0], result[2], result[3]

        # The area-Mach relation is flat at the sonic point, so fsolve reports a stalled
        # iteration there even when the root it holds is good to a part in ten million. The
        # residual is the thing worth trusting; the flag alone made whether a contour solved
        # depend on the propellant.
        if exitFlag != 1 and abs(residual(machNumber)) > 1e-6 * areaRatio:
            raise ValueError(f'Subsonic area-Mach solver did not converge at an area ratio of '
                             f'{areaRatio:.6f}: {message}')

        # The solver can also land just the other side of the sonic point. Overshooting by less
        # than its own tolerance is convergence rather than failure, so it is clamped instead of
        # rejected. A root below one is returned exactly as the solver found it.
        if 1.0 < machNumber <= 1.0 + 1e-6:
            machNumber = 1.0

        if machNumber <= 0 or machNumber > 1.0 or not np.isfinite(machNumber):
            raise ValueError(f'Subsonic area-Mach solver produced an invalid result at an area '
                             f'ratio of {areaRatio:.6f}: M = {machNumber}')
        return machNumber

    raise ValueError(f"branch must be 'supersonic' or 'subsonic', not '{branch}'")

# -- Reference lengths -- #

def conicalLength(areaRatio: float, throatRadius: float, halfAngle: float = np.radians(15.0)) -> float:

    '''

    Length from the throat plane to the exit of a straight-walled cone of the given area ratio.

    This is the yardstick every published bell length is quoted against. NASA SP-8120 defines
    percent bell as the length of the bell as a percent of the length of a 15 degree half-angle
    conical nozzle having the same expansion area ratio, so the area ratio here has to be the one
    the nozzle delivers rather than a separate design-point value.

    Parameters:
    -----------
    areaRatio : float
        Exit area over throat area [-]
    throatRadius : float
        Throat radius, in whatever length unit the answer is wanted [m] or [-]
    halfAngle : float
        Cone half angle [rad], 15 degrees by convention

    Returns:
    --------
    float : Length from the throat plane to the exit, in the units of throatRadius

    '''

    return (np.sqrt(areaRatio) - 1.0) * throatRadius / np.tan(halfAngle)

def divergenceLossFactor(halfAngle: float) -> float:

    '''

    Classical divergence correction lambda = (1 + cos(alpha)) / 2 for a conical nozzle.

    A point-source result: it becomes accurate as the area ratio grows and misstates the loss at
    low area ratio, where the measured divergence efficiency oscillates with area ratio rather
    than following the formula. 0.983 at the conventional 15 degrees.

    '''

    return 0.5 * (1.0 + np.cos(halfAngle))
