
# -- NOVA: Equilibrium Expansion Properties -- #

'''

Local gas properties along an equilibrium expansion, and the characteristics relations built on
them.

A calorically perfect gas has one ratio of specific heats, and every relation a characteristics
solve needs follows from it in closed form. A real exhaust does not: it recombines as it expands,
so the isentropic exponent climbs along the nozzle, and a solve carrying one value has to choose
which part of the expansion to be right about. On the LOX/LH2 reference engine the equilibrium
exponent runs 1.156 at an area ratio of 1.2 and 1.257 by 40, a spread of nine per cent.

This module builds the alternative the standard method uses. `expansionTable` samples the
thermochemistry along the chamber isentrope and returns the local state at each station.
`EquilibriumGas` wraps that table in the same four relations `characteristics.CharacteristicGas`
provides, so a net can be solved in it without the unit process knowing which gas it holds.

The relation that does not survive a variable exponent is the Prandtl-Meyer function. Its closed
form is an integration of

    d(nu) = sqrt(M^2 - 1) dV / V

carried out at constant gamma. The integral itself is general, so `generalizedPrandtlMeyerAngle`
evaluates it along the tabulated expansion instead, which reduces to the closed form when the
table is generated at constant gamma and departs from it exactly as much as the real gas does.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**The generalized Prandtl-Meyer integral is checked against its own closed form.** Generated
from a constant-gamma table at the sampling this module defaults to, `generalizedPrandtlMeyerAngle`
reproduces `gasDynamics.prandtlMeyerAngle` to within 0.022 degrees of turning at gamma 1.15, 1.2
and 1.4, over area ratios to 100. That is the only check available that does not come from the
thermochemistry it is meant to replace, and it is what fixes the sampling: from an area ratio of
1.05 upward the same integral lands a full degree low everywhere downstream.

**The table is CEA's.** Every state in it is an equilibrium solve at one area ratio, so the
thermochemistry carries whatever validation `tests/testCeaInterface.py` establishes against
CEARun, and no more. What is not established is that an equilibrium expansion is the right model:
a real nozzle recombines at a finite rate and freezes somewhere in the diverging section, which
neither this nor the frozen limit describes. The two bracket it.

**Nothing here is wired into the contour solve yet.** The module is the gas; using it is a change
to `characteristics`, which holds one gamma deliberately.

All units are mass base SI:
    - Temperature [K]
    - Pressure    [Pa]
    - Velocity    [m/s]
    - Angle       [rad]

Author: Sean Bowman

'''

from dataclasses import dataclass

import numpy as np

from .ceaInterface import CEA

@dataclass
class ExpansionTable:

    '''

    The local state along an equilibrium expansion, one row per sampled area ratio.

    Attributes:
    -----------
    areaRatio : numpy.ndarray
        Local area over throat area [-], ascending from 1.
    mach : numpy.ndarray
        Local Mach number [-].
    temperature : numpy.ndarray
        Local static temperature [K].
    velocity : numpy.ndarray
        Local velocity [m/s].
    sonicVelocity : numpy.ndarray
        Local speed of sound [m/s].
    gamma : numpy.ndarray
        Local ratio of specific heats [-].
    pressure : numpy.ndarray
        Local static pressure [Pa].
    gasConstant : float
        Specific gas constant of the exhaust at the exit [J/kg-K].
    prandtlMeyer : numpy.ndarray
        Prandtl-Meyer angle [rad], integrated along this expansion from the throat.
    stagnationTemperature : float
        Chamber stagnation temperature [K].

    '''

    areaRatio:     np.ndarray
    mach:          np.ndarray
    temperature:   np.ndarray
    velocity:      np.ndarray
    sonicVelocity: np.ndarray
    gamma:         np.ndarray
    pressure:      np.ndarray
    prandtlMeyer:  np.ndarray
    gasConstant:   float
    stagnationTemperature: float

def generalizedPrandtlMeyerAngle(mach, velocity):

    '''

    Prandtl-Meyer angle along a tabulated expansion, by integrating its defining differential.

    The Prandtl-Meyer function is the turning a supersonic stream does as it expands, and it is
    defined by

        d(nu) = sqrt(M^2 - 1) dV / V

    along the expansion. Carrying that out at constant gamma gives the closed form every perfect
    gas solve uses. Carried out along a tabulated expansion instead, it holds for a gas whose
    exponent varies, which is what an equilibrium exhaust is.

    The integral is taken in ln V, where the integrand is sqrt(M^2 - 1) and finite everywhere,
    rather than in V. It starts from the first tabulated station, which should be the throat.

    Parameters:
    -----------
    mach : array_like
        Local Mach number at each station [-], ascending.
    velocity : array_like
        Local velocity at each station [m/s], ascending.

    Returns:
    --------
    numpy.ndarray
        Prandtl-Meyer angle at each station [rad], zero at the first.

    '''

    mach     = np.asarray(mach, dtype = float)
    velocity = np.asarray(velocity, dtype = float)

    # Below Mach 1 the integrand is imaginary; the expansion starts at the sonic point
    integrand = np.sqrt(np.maximum(mach**2 - 1.0, 0.0))

    return np.concatenate(([0.0], np.cumsum(0.5*(integrand[1:] + integrand[:-1])
                                            * np.diff(np.log(velocity)))))

def expansionTable(fuelName: str, oxidizerName: str, mixtureRatio: float, chamberPressure: float,
                   areaRatios = None, frozen: bool = False,
                   frozenAtThroat: bool = False) -> ExpansionTable:

    '''

    Sample the thermochemistry along the expansion and build the table the gas reads.

    One equilibrium solve is run per area ratio. The throat is included as the first station, at
    Mach 1, because the Prandtl-Meyer integral starts there and because a solve at an area ratio
    of exactly 1 is degenerate.

    Parameters:
    -----------
    fuelName, oxidizerName : str
        Propellants, as ceaInterface resolves them.
    mixtureRatio : float
        Oxidizer to fuel mass ratio [-].
    chamberPressure : float
        Chamber stagnation pressure [Pa].
    areaRatios : array_like
        Supersonic area ratios to sample [-]. The default runs from just above the throat to 100,
        refined near the throat where the Prandtl-Meyer integrand turns fastest, which covers
        every nozzle NOVA builds.
    frozen, frozenAtThroat : bool
        Freeze the composition, in the chamber or at the throat. Both false is equilibrium.

    Returns:
    --------
    ExpansionTable

    '''

    if areaRatios is None:
        # The integrand of the Prandtl-Meyer function rises as sqrt(M^2 - 1) out of the sonic
        # point, so the first stretch above the throat carries a disproportionate share of the
        # turning and has to be resolved. Sampled from an area ratio of 1.05 upward, the integral
        # lands a full degree low at every station downstream, and refining further out does not
        # recover it, because the error is all in the first interval.
        areaRatios = np.concatenate((1.0 + np.geomspace(1e-5, 0.05, 60),
                                     np.geomspace(1.05, 100.0, 60)[1:]))
    areaRatios = np.atleast_1d(np.asarray(areaRatios, dtype = float))

    firstSolve = CEA(fuelName = fuelName, oxidizerName = oxidizerName,
                     chamberPressure = chamberPressure, OFRatio = mixtureRatio,
                     expansionRatio = float(areaRatios[0]), frozen = frozen,
                     frozenAtThroat = frozenAtThroat).ceaResults

    stagnationTemperature = float(firstSolve['combustionChamberTemperature'])
    throatTemperature     = float(firstSolve['throatTemperature'])
    throatGamma           = float(firstSolve['throatGamma'])

    mach          = [1.0]
    temperature   = [throatTemperature]
    gamma         = [throatGamma]
    sonicVelocity = [float(np.sqrt(throatGamma*firstSolve['exitGasConstant']*throatTemperature))]
    velocity      = [sonicVelocity[0]]
    pressure      = [float(firstSolve['combustionChamberPressure'])
                     if 'combustionChamberPressure' in firstSolve else chamberPressure]
    ratios        = [1.0]

    for ratio in areaRatios:
        solve = CEA(fuelName = fuelName, oxidizerName = oxidizerName,
                    chamberPressure = chamberPressure, OFRatio = mixtureRatio,
                    expansionRatio = float(ratio), frozen = frozen,
                    frozenAtThroat = frozenAtThroat).ceaResults
        ratios.append(float(ratio))
        mach.append(float(solve['exitMach']))
        temperature.append(float(solve['exitTemperature']))
        velocity.append(float(solve['exitVelocity']))
        sonicVelocity.append(float(solve['exitSonicVelocity']))
        gamma.append(float(solve['exitGamma']))
        pressure.append(float(solve['exitPressure']))

    mach, velocity = np.array(mach), np.array(velocity)

    # Two area ratios a part in ten thousand apart can come back with the same Mach number, or
    # with one a fraction lower, at the tolerance CEA converges its own iteration to. Every
    # relation here is an interpolation on Mach, which needs it strictly increasing, so a station
    # that does not advance is dropped rather than smoothed.
    advancing = np.concatenate(([True], np.diff(mach) > 0))
    ratios        = np.asarray(ratios)[advancing]
    temperature   = np.asarray(temperature)[advancing]
    sonicVelocity = np.asarray(sonicVelocity)[advancing]
    gamma         = np.asarray(gamma)[advancing]
    pressure      = np.asarray(pressure)[advancing]
    mach, velocity = mach[advancing], velocity[advancing]

    return ExpansionTable(areaRatio = ratios, mach = mach,
                          temperature = temperature, velocity = velocity,
                          sonicVelocity = sonicVelocity, gamma = gamma,
                          pressure = pressure,
                          prandtlMeyer = generalizedPrandtlMeyerAngle(mach, velocity),
                          gasConstant = float(solve['exitGasConstant']),
                          stagnationTemperature = stagnationTemperature)

class EquilibriumGas:

    '''

    The gas a characteristics net is solved in, with properties that vary along the expansion.

    It answers the same four questions `characteristics.CharacteristicGas` answers, by
    interpolating a tabulated expansion rather than by evaluating a closed form at one exponent.
    `gamma` is reported at the exit of the table, for callers that still want a single number to
    quote, and is not what any of the relations are built on.

    Parameters:
    -----------
    table : ExpansionTable
        The sampled expansion, from `expansionTable`.

    '''

    def __init__(self, table: ExpansionTable):

        self.table                 = table
        self.gasConstant           = table.gasConstant
        self.stagnationTemperature = table.stagnationTemperature
        self.gamma                 = float(table.gamma[-1])
        self.maxAdiabaticVelocity  = float(table.velocity[-1] * np.sqrt(
            1.0 + 2.0/((table.gamma[-1] - 1.0)*table.mach[-1]**2)))

    def __repr__(self):
        return (f'EquilibriumGas(stations = {self.table.mach.size}, '
                f'Mach {self.table.mach[0]:.2f} to {self.table.mach[-1]:.2f}, '
                f'gamma {self.table.gamma[0]:.4f} to {self.table.gamma[-1]:.4f})')

    def prandtlMeyerAngle(self, mach: float) -> float:

        '''Prandtl-Meyer angle at this Mach number along the tabulated expansion [rad].'''

        return float(np.interp(mach, self.table.mach, self.table.prandtlMeyer))

    def localTemperature(self, mach: float) -> float:

        '''Static temperature at this Mach number [K].'''

        return float(np.interp(mach, self.table.mach, self.table.temperature))

    def localVelocity(self, mach: float) -> float:

        '''Velocity at this Mach number [m/s].'''

        return float(np.interp(mach, self.table.mach, self.table.velocity))

    def machFromVelocity(self, velocity: float) -> float:

        '''Mach number at this velocity [-].'''

        return float(np.interp(velocity, self.table.velocity, self.table.mach))
