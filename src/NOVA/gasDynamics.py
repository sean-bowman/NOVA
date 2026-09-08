
# -- Elementary Gas Dynamics -- #

'''

Perfect-gas relations for steady isentropic flow of a calorically perfect gas.

These are the closed-form relations every other NOVA module builds on: the isentropic ratios, the
Prandtl-Meyer function and its inverse, and the area-Mach relation and its two branches. They are
gathered here so that one expression serves the contour solver, the plume march, the converging
section and the validation scripts, rather than each carrying its own copy to drift out of step
with the others.

Every function takes gamma explicitly. Nothing here reads state off a Nozzle object, and nothing
here knows which gamma is the right one for a given station; that choice belongs to the caller and
is a real one, because a characteristics mesh built on the chamber gamma cannot be read back under
the exit gamma without breaking continuity at the plane where the two meet.

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
        # Deliberately unguarded ahead of the solve, and on the same initial guess and tolerances
        # the converging section has always used. A station whose radius rounds to the throat
        # radius has to reach the same answer it reached before this function existed.
        result = fsolve(residual, 0.001, full_output = True, maxfev = 200, xtol = 1e-6)
        machNumber, exitFlag, message = result[0][0], result[2], result[3]
        if exitFlag != 1:
            raise ValueError(f'Subsonic area-Mach solver did not converge at an area ratio of '
                             f'{areaRatio:.6f}: {message}')
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
