
# -- NOVA: Gas-Side Heat Transfer -- #

'''

The exhaust-side film coefficient, which every wall model reads.

What the exhaust does to the wall does not depend on how the wall is cooled. The jacket, the
ablative liner and the radiation-cooled extension all need the same coefficient at the same
station, so it lives here rather than inside any one of them.

Two pieces. `bartzHeatTransferCoefficient` is the correlation itself, referenced to the throat and
carrying one constant along the whole wall. `measuredAxialFactor` is the axial distribution taken
from measured correlation constants, which that single constant does not have; a caller selects
between them with `gasSideAxialModel`, `uniform` or `measured`.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Checked against a published source.** The correlation is Bartz as given in Huzel and Huang,
NASA SP-125:

    h_g = (0.026 / D_t^0.2) (mu_0^0.2 c_p0 / Pr_0^0.6) (P_c / c*)^0.8 (D_t / R_c)^0.1 (A_t / A)^0.9 sigma

with the stagnation Prandtl number from 4 gamma / (9 gamma - 5), the stagnation viscosity from the
fit mu_0 = 1.184e-7 M^0.5 T_0^0.6, and sigma the boundary layer correction. That viscosity constant
is the SI form of SP-125's 46.6e-10 M^0.5 T^0.6 in lbm/(in s) with T in Rankine, which converts to
1.18408e-7 in SI. tests/testRegenThermal.py carries the comparison against a worked example.

**The throat coefficient is high against measured constants.** Written as St* Pr*^0.7 = C Re*_d^-0.2
with properties at Eckert's reference enthalpy, the Bartz form carries C = 0.026 everywhere.
Measured constants do not: on a LOX/GH2 chamber at 150 to 1000 psia (NASA TN D-2832) C is 0.0257 in
the cylindrical barrel, 0.0240 through the converging section, 0.0148 at the throat and 0.0153 to
0.0188 downstream of it, and four other configurations reduced the same way give throat constants of
0.017 to 0.023. On that evidence a uniform constant is 20 to 40 percent high at the throat and about
right over the barrel. A high coefficient drives a sizing march to a smaller channel, so the wall
lands below its limit and the pressure drop is paid for margin that is already there.
docs/references_gasSideHeatTransfer_2026-09-22.md carries the sources.

**The measured distribution is a shape, not a level.** `measuredAxialFactor` normalizes on the
barrel station, so the absolute level stays Bartz's and only the axial variation comes from the
measurement. That is the part that survives a change of property model: TN D-2832 records that
changing transport data moved every C by about 30 percent together. Adopting the measured constants
outright would import the property evaluation they were reduced with.

**Over a chamber barrel it is used outside its checked range.** The correlation is referenced to the
throat and nothing here checks it in a subsonic barrel. On a straight barrel its coefficient varies
only through the wall temperature, with no injector near field and no boundary layer start.

**The gas state a caller supplies is its own problem.** Nothing here forms a gas state. Where NOVA
supplies one it comes from CEA at a one-dimensional station, while the near-wall Mach number the
method of characteristics returns departs from the one-dimensional value by up to 42 percent near
the throat; the two are inconsistent, and the throat is where the heat flux is highest.

All units are mass base SI.

Author: Sean Bowman

'''

import numpy as np

# How the gas-side correlation constant is allowed to vary along the wall.
#
#   'uniform'   one constant everywhere, which is what the Bartz form carries.
#   'measured'  scaled by the constants measured along a LOX/GH2 chamber, which takes about
#               40 percent off at the throat and leaves the barrel alone.
GASSIDEAXIALMODELS = ('uniform', 'measured')

# Correlation constants measured at five stations of a LOX/GH2 chamber, NASA TN D-2832 table on
# p. 17, for St* Pr*^0.7 = C Re*_d^-0.2 with properties at Eckert's reference enthalpy. C is not a
# constant along the wall: it is largest in the cylindrical barrel, falls through the converging
# section to a minimum at the throat and rises again downstream. Area ratio alone does not place a
# station, since each value occurs once on either side of the throat, so the two branches are kept
# apart. The percentages are the standard deviation of the data about C at that station.
MEASUREDAXIALCONSTANTS = {
    # (area ratio, C, sigma/C)
    'subsonic':   ((4.64, 0.0257, 0.109), (1.78, 0.0240, 0.163), (1.00, 0.0151, 0.132)),
    'supersonic': ((1.00, 0.0151, 0.132), (1.27, 0.0153, 0.104), (3.33, 0.0188, 0.079)),
}

# The barrel station, where the measured constant matches the 0.026 the Bartz form carries to
# within 1 percent. Normalizing by it leaves the absolute level of the coefficient to Bartz and
# takes only the shape from the measurement, which is the part that survives a change of property
# model: the report notes that changing transport data moved every C by about 30 percent together.
MEASUREDBARRELCONSTANT = 0.0257

def measuredAxialFactor(areaRatio: float, subsonic: bool) -> float:

    '''

    Axial factor on the gas-side coefficient, from the measured correlation constants.

    The factor is the constant measured at this station over the constant measured in the
    cylindrical barrel, so it is 1 over the barrel and 0.59 at the throat. Applied to a
    coefficient that already carries the barrel level, it reproduces the measured shape without
    adopting the absolute constant, which is only meaningful alongside the property evaluation it
    was reduced with.

    Between stations the constant is interpolated linearly in area ratio, and outside the measured
    range it is held at the end value rather than extrapolated.

    Parameters:
    -----------
    areaRatio : float
        Local area over throat area [-].
    subsonic : bool
        True upstream of the throat, where the chamber and converging section are, and False
        downstream of it. The measured constant differs between the two at the same area ratio.

    Returns:
    --------
    float
        Multiplier on the gas-side coefficient [-].

    '''

    branch = MEASUREDAXIALCONSTANTS['subsonic' if subsonic else 'supersonic']
    ratios = np.array([station[0] for station in branch], dtype = float)
    constants = np.array([station[1] for station in branch], dtype = float)

    order = np.argsort(ratios)

    return float(np.interp(areaRatio, ratios[order], constants[order]) / MEASUREDBARRELCONSTANT)

def bartzHeatTransferCoefficient(nearWallTemperature: float, nearWallMachNumber: float,
                                 exhaustGamma: float, exhaustGasConstant: float,
                                 exhaustMolecularWeight: float, hotWallTemperature: float,
                                 chamberPressure: float, characteristicVelocity: float,
                                 throatDiameter: float, throatRadiusOfCurvature: float,
                                 throatArea: float, localArea: float) -> float:

    '''

    Gas-side convective heat transfer coefficient from the Bartz correlation.

    The form is the one given in Huzel and Huang, NASA SP-125:

        h_g = (0.026 / D_t^0.2) (mu_0^0.2 c_p0 / Pr_0^0.6) (P_c / c*)^0.8
              (D_t / R_c)^0.1 (A_t / A)^0.9 sigma

    The stagnation Prandtl number comes from 4 gamma / (9 gamma - 5) and the stagnation viscosity
    from the fit mu_0 = 1.184e-7 M^0.5 T_0^0.6. That constant is the SI form of SP-125's
    46.6e-10 M^0.5 T^0.6 in lbm/(in s) with T in Rankine.

    The exact conversion is 1.1840811e-7: 46.6e-10 lbm/(in s) is 8.3218128e-8 kg/(m s), and the
    Rankine-to-kelvin change of variable multiplies it by (9/5)^0.6. The coefficient used here is
    that value rounded to four figures, which is 6.8e-5 low. Through mu^0.2 in the Bartz
    expression that reaches the gas-side coefficient as 1.4e-5, well inside the correlation's own
    accuracy, so it is left as the number every recorded result was produced with rather than
    changed for a correction nothing can measure.

    Sigma is the boundary layer correction, which carries the whole dependence on wall
    temperature and is why the caller has to converge the wall rather than solve it directly.

    A near-wall temperature of exactly 300 K is a sentinel for a station that sees no exhaust,
    such as one out on a volute interface, and returns a free-convection estimate for stagnant
    air instead. Nothing in NOVA currently sets that value, so the branch is not reached; it is
    kept because a caller supplying its own station properties may still use it. Being an
    equality test against a float it would also be missed by 300.0000001, which is a reason not
    to rely on it.

    Parameters:
    -----------
    nearWallTemperature : float
        Static gas temperature at the wall [K]
    nearWallMachNumber : float
        Local Mach number [-]
    exhaustGamma : float
        Ratio of specific heats [-]
    exhaustGasConstant : float
        Specific gas constant [J/kg K]
    exhaustMolecularWeight : float
        Molecular weight [kg/kmol]
    hotWallTemperature : float
        Current guess at the gas-side wall temperature [K]
    chamberPressure : float
        Chamber stagnation pressure [Pa]
    characteristicVelocity : float
        Characteristic velocity [m/s]
    throatDiameter : float
        Throat diameter [m]
    throatRadiusOfCurvature : float
        Wall radius of curvature at the throat [m]
    throatArea : float
        Throat area [m^2]
    localArea : float
        Flow area at this station [m^2]

    Returns:
    --------
    float
        Gas-side convective heat transfer coefficient [W/m^2 K]

    '''

    if nearWallTemperature == 300:
        # estimate for HTC for stagnant air
        return 5

    totalTemperature        = nearWallTemperature * (1 + (exhaustGamma - 1)/2 * nearWallMachNumber**2)
    stagnationHeatCapacity  = (exhaustGamma / (exhaustGamma - 1)) * exhaustGasConstant
    stagnationPrandtl       = 4 * exhaustGamma / (9 * exhaustGamma - 5)
    stagnationViscosity     = 1.184e-7 * exhaustMolecularWeight**0.5 * totalTemperature**0.6

    boundaryLayerCorrectionFactor        = (0.5 * (hotWallTemperature / totalTemperature) *                                         (1 + (exhaustGamma - 1)/2 * nearWallMachNumber**2) + 0.5)**-0.68 *                                         ((1 + (exhaustGamma - 1)/2 * nearWallMachNumber**2))**-0.12
    constantBartzPart                    = (0.026 / (throatDiameter**0.2)) *                                         (stagnationViscosity**0.2 * stagnationHeatCapacity / (stagnationPrandtl**0.6)) *                                         (chamberPressure / characteristicVelocity)**0.8 *                                         (throatDiameter / throatRadiusOfCurvature)**0.1

    return (constantBartzPart *             (throatArea / localArea)**0.9 *             boundaryLayerCorrectionFactor)
