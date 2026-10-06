
# -- NOVA: Ievlev's Gas-Side Heat Transfer -- #

'''

The gas-side heat flux by Ievlev's method, as RPA implements it.

Ievlev's method comes from the integral boundary-layer equations closed with semi-empirical heat
transfer relations; the Russian integral school of Kutateladze and Leont'ev is its lineage. RPA
carries it as its default gas-side model, and A. Ponomarenko, "RPA: Tool for Rocket Propulsion
Analysis. Thermal Analysis of Thrust Chambers", 2012, Eqs. 1.1 to 1.6, gives it in full. The same
equations appear in his 2014 Space Propulsion paper. The derivations are in Vasiliev and
Kudryavtsev, *Basics of Theory and Analysis of Liquid-Propellant Rocket Engines*, 1993, in Russian,
which is not in NOVA's reference set.

What it carries, and how that differs from the marched layer
-----------------------------------------------------------

**One history, not two.** Only the energy integral is integrated along the wall, and it is
integrated in closed form (Eq. 1.2) rather than marched. The momentum layer is not carried at all:
the ratio of the two Reynolds-number groups is algebraic in the local velocity and wall
temperature (Eq. 1.1), and near 1.5 everywhere on a rocket wall. `boundaryLayer.solveBoundaryLayer`
marches both, and their ratio reaches 8 to 10 through a throat.

**An enthalpy potential.** The flux is a Stanton number times the stagnation enthalpy less the
wall gas enthalpy (Eq. 1.5), with the wall gas at the composition it has at 1500 K, below which
recombination is taken as frozen.

**A defining temperature for properties**, written in the velocity ratio and the wall temperature
over an effective stagnation temperature, rather than Eckert's reference temperature.

The equations
-------------

With beta the velocity over the maximum velocity sqrt(2 gamma R0 T0 / (gamma - 1)), T_w over
T_e = R0 T0 / R_1500 written Tw, D the local diameter over the throat diameter, and l the wall
length over the throat diameter:

    z_T / z = (1.769 (1 - b^2 + b^2 (1 - 0.08696 (1 - b^2) / (1 - Tw + 0.1 b^2))) / (1 - Tw + 0.1 b^2))^0.54   (1.1)

    z_T = Re0 / ((1 - g) (D dI)^(1/(1-g))) * integral (rho_x/rho0)(mu0/mu_x) (D dI)^(1/(1-g)) b dl + const   (1.2)

    alpha_T = (z/z_T)^(0.089 Pr^-0.56) (1 - 0.21 ((1 - Pr)/Pr^(4/3)) b^2/(1 - Tw))^0.9225
              / ((307.8 + 54.8 log10(Pr/19.5)^2) Pr^0.45 z^0.08 - 650)                            (1.3)

    alpha = 0.03327 z^-0.224 + 3.966e-4                                                           (1.4)

    q_w = alpha_T rho_x w (I0 - I_w),     tau_w = alpha rho_x w^2                                  (1.5, 1.6)

    rho_x / rho0 = (p / p0) ((1 + Tw)/2 - b^2/4)^-0.823 ((3 + Tw)/4 - 9 b^2/16)^-0.177
    mu0 / mu_x   = ((1 + Tw)/2 - b^2/4)^-0.7

Re0 is rho0 w_max D_t / mu0 on stagnation properties, z = Re**/alpha and z_T = Re**_T/alpha_T.

Two things the paper does not state, and how they are settled
-------------------------------------------------------------

**The exponent g in Eq. 1.2.** It is not the ratio of specific heats. Write the heat transfer law as
alpha_T = A z_T^-g and put it in the integral energy equation: Re**_T = A z_T^(1-g), the constant A
cancels between the two sides, and what remains integrates exactly to Eq. 1.2, with g the law's
exponent in z_T. Eq. 1.3 falls as z^-0.08 once its first term dominates the 650, so g is 0.08 and
1/(1 - g) is 1.087. With the ratio of specific heats in its place the exponents turn negative and
the integral has no meaning.

**The logarithm in Eq. 1.3 is base ten.** Base ten gives Stanton numbers near 2e-3 on a rocket
wall, which is where correlations and measurements sit. The natural logarithm gives a quarter of
that.

**The constant in Eq. 1.2** is the energy integral's starting value. The denominator of Eq. 1.3
passes through zero below z of a few thousand, so a layer cannot start from nothing; it starts
from `initialEnergyGroup`, the value of z_T at the first station. Like the marched layer's starting
thickness, the throat forgets it: see the validation status.

The wall gas enthalpy
---------------------

The paper's rule: the wall gas has the composition of the products at 1500 K and the wall
temperature. `ievlevGasProperties` takes the 1500 K gas constant from a CEA equilibrium expansion
to 1500 K, and the wall gas enthalpy from expansions to the wall temperature, which is the rule's
own answer wherever the composition has stopped changing by 1500 K. That holds for hydrogen and
oxygen and not for carbon-bearing products; the function's notes say what it costs.

Validation status
-----------------

**Implemented from the published equations and checked against them.** In a straight duct at a
constant state Eq. 1.2 has an exact solution, linear growth of z_T, and the quadrature returns it
to 1e-10. Eq. 1.1 returns its published constant at rest on a cold wall, the property ratios are
one at the stagnation state, and Eq. 1.3 returns no value where its denominator is not positive.

**The wall gas enthalpy is validated against NIST-JANAF.** For the fully recombined products of
LOX/LH2 at a mixture ratio of 6.0, at 550 K, the CEA route returns the JANAF value to 0.1 percent.

**The two settled ambiguities are checked by their consequences.** The Stanton number lands between
1e-3 and 3e-3 along the calorimeter chamber with the base-ten logarithm. The throat heat flux moves
by under 2 percent across two decades of the starting value of z_T.

**A code-to-code cross-check against RPA's own output, not a validation.** On RPA's wall for Test
024 of the MSFC 40k calorimeter chamber, on the hot-wall temperature the test's reduction used, the
implementation reproduces RPA's barrel flux to 0 percent, its peak to 3 percent and its peak over
barrel to 2.12 against 2.07. Past the throat it runs 16 to 26 percent above RPA, which a 900 K wall
brings to within 4 percent; RPA does not state its wall temperature.
`featureShowcase/buildCalorimeter40k.py` runs it and `docs/reports/calorimeter40k_2026-10-04.md`
reports it. Matching RPA shows the equations are read the way RPA reads them, not that either is
right.

**Against the measured profile on that chamber** it runs 7 percent low in the barrel and 20 percent
high in throat-to-barrel ratio; the same document reports it with the rest of NOVA's gas-side
models.

Author: Sean Bowman

'''

import math

import numpy as np

# Eq. 1.2's exponent, which has to be the heat transfer law's exponent in z_T: see the module notes
ievlevQuadratureExponent = 0.08

# Starting value of z_T. The march forgets it within a few chamber diameters; see the tests.
defaultInitialEnergyGroup = 1.0e5

def definingTemperatureGroup(velocityRatio, wallTemperatureRatio):

    '''

    The group (1 + Tw)/2 - beta^2/4 the defining-state property ratios are written in.

    '''

    return (1.0 + wallTemperatureRatio) / 2.0 - velocityRatio**2 / 4.0

def densityRatio(pressureRatio, velocityRatio, wallTemperatureRatio):

    '''

    Density at the defining state over stagnation density, the paper's rho_x / rho0.

    '''

    first = definingTemperatureGroup(velocityRatio, wallTemperatureRatio)
    second = (3.0 + wallTemperatureRatio) / 4.0 - 9.0 * velocityRatio**2 / 16.0

    return pressureRatio * first**-0.823 * second**-0.177

def viscosityRatio(velocityRatio, wallTemperatureRatio):

    '''

    Stagnation viscosity over viscosity at the defining state, the paper's mu0 / mu_x.

    '''

    return definingTemperatureGroup(velocityRatio, wallTemperatureRatio)**-0.7

def thicknessGroupRatio(velocityRatio, wallTemperatureRatio):

    '''

    Eq. 1.1: z_T / z, algebraic in the local velocity ratio and wall temperature ratio.

    '''

    beta2 = np.asarray(velocityRatio, dtype = float)**2
    wall = np.asarray(wallTemperatureRatio, dtype = float)
    denominator = 1.0 - wall + 0.1 * beta2
    inner = 1.0 - beta2 + beta2 * (1.0 - 0.08696 * (1.0 - beta2) / denominator)

    return (1.769 * inner / denominator)**0.54

def stantonNumber(group, groupRatio, prandtlNumber: float, velocityRatio, wallTemperatureRatio):

    '''

    Eq. 1.3: alpha_T, the Stanton number referred to the defining density.

    Parameters:
    -----------
    group : array_like
        z, the momentum-side group Re**/alpha [-].
    groupRatio : array_like
        z_T / z from Eq. 1.1 [-].
    prandtlNumber : float
        Prandtl number of the gas [-].
    velocityRatio, wallTemperatureRatio : array_like
        beta and T_w / T_e [-].

    Returns:
    --------
    numpy.ndarray : alpha_T [-]. NaN where the denominator is not positive, which is a layer too
        thin for the correlation.

    '''

    group = np.asarray(group, dtype = float)
    beta2 = np.asarray(velocityRatio, dtype = float)**2
    wall = np.asarray(wallTemperatureRatio, dtype = float)

    interaction = np.asarray(groupRatio, dtype = float)**-(0.089 * prandtlNumber**-0.56)
    compressibility = (1.0 - 0.21 * (1.0 - prandtlNumber) / prandtlNumber**(4.0 / 3.0) * beta2 / (1.0 - wall))**0.9225
    prandtlTerm = (307.8 + 54.8 * math.log10(prandtlNumber / 19.5)**2) * prandtlNumber**0.45
    denominator = prandtlTerm * group**0.08 - 650.0

    with np.errstate(invalid = 'ignore', divide = 'ignore'):
        return np.where(denominator > 0.0, interaction * compressibility / denominator, np.nan)

def frictionCoefficient(group):

    '''

    Eq. 1.4: alpha, the friction coefficient referred to the defining density.

    '''

    return 0.03327 * np.asarray(group, dtype = float)**-0.224 + 3.966e-4

def ievlevHeatFlux(axialPosition, radius, velocity, pressure, wallTemperature, gas: dict,
                   initialEnergyGroup: float = defaultInitialEnergyGroup,
                   quadratureExponent: float = ievlevQuadratureExponent) -> dict:

    '''

    Wall heat flux and shear along a wall by Ievlev's method.

    Parameters:
    -----------
    axialPosition, radius : array_like
        The wall from its first station [m]. The energy integral starts at the first station.
    velocity, pressure : array_like
        Edge velocity [m/s] and static pressure [Pa] at the stations.
    wallTemperature : float | array_like
        Hot-wall temperature [K].
    gas : dict
        From `ievlevGasProperties`: stagnation temperature, pressure and gas constant, the gas
        constant at 1500 K, gamma, stagnation viscosity, Prandtl number, stagnation enthalpy, and
        a callable for the wall gas enthalpy.
    initialEnergyGroup : float
        z_T at the first station [-], the constant of Eq. 1.2.
    quadratureExponent : float
        The exponent g of Eq. 1.2 [-].

    Returns:
    --------
    dict
        'heatFlux' [W/m^2], 'wallShear' [Pa], 'stantonNumber', 'frictionCoefficient',
        'energyGroup' (z_T), 'momentumGroup' (z), 'groupRatio', 'velocityRatio',
        'definingDensity' [kg/m^3], 'enthalpyDifference' [J/kg], and 'heatTransferCoefficient'
        [W/m^2-K] referred to the stagnation temperature less the wall, for callers that work
        in temperatures.

    '''

    axialPosition = np.asarray(axialPosition, dtype = float)
    radius = np.asarray(radius, dtype = float)
    velocity = np.asarray(velocity, dtype = float)
    pressure = np.asarray(pressure, dtype = float)
    wall = np.broadcast_to(np.asarray(wallTemperature, dtype = float), radius.shape).astype(float)

    stagnationTemperature = gas['stagnationTemperature']
    stagnationPressure = gas['stagnationPressure']
    gasConstant = gas['gasConstant']
    gamma = gas['gamma']

    maximumVelocity = math.sqrt(2.0 * gamma / (gamma - 1.0) * gasConstant * stagnationTemperature)
    effectiveTemperature = gasConstant * stagnationTemperature / gas['gasConstant1500']
    stagnationDensity = stagnationPressure / (gasConstant * stagnationTemperature)
    throatDiameter = 2.0 * radius.min()
    stagnationReynolds = stagnationDensity * maximumVelocity * throatDiameter / gas['stagnationViscosity']

    beta = np.clip(velocity / maximumVelocity, 0.0, 0.999)
    wallRatio = wall / effectiveTemperature
    rhoRatio = densityRatio(pressure / stagnationPressure, beta, wallRatio)
    muRatio = viscosityRatio(beta, wallRatio)
    enthalpyDifference = gas['stagnationEnthalpy'] - np.array([gas['wallEnthalpy'](value) for value in wall])

    # Eq. 1.2 by the trapezoid rule along the wall, which is the arc length over the throat
    # diameter: the paper's dl / cos(theta)
    power = 1.0 / (1.0 - quadratureExponent)
    diameterRatio = 2.0 * radius / throatDiameter
    weight = (diameterRatio * enthalpyDifference)**power
    integrand = rhoRatio * muRatio * weight * beta
    arc = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(axialPosition), np.diff(radius)))]) / throatDiameter
    integral = np.concatenate([[0.0], np.cumsum(0.5 * (integrand[1:] + integrand[:-1]) * np.diff(arc))])
    energyGroup = (power * stagnationReynolds * integral + initialEnergyGroup * weight[0]) / weight

    groupRatio = thicknessGroupRatio(beta, wallRatio)
    momentumGroup = energyGroup / groupRatio
    stanton = stantonNumber(momentumGroup, groupRatio, gas['prandtlNumber'], beta, wallRatio)
    friction = frictionCoefficient(momentumGroup)

    definingDensity = rhoRatio * stagnationDensity
    heatFlux = stanton * definingDensity * velocity * enthalpyDifference

    with np.errstate(invalid = 'ignore', divide = 'ignore'):
        coefficient = heatFlux / (stagnationTemperature - wall)

    return {
        'heatFlux':                heatFlux,
        'wallShear':               friction * definingDensity * velocity**2,
        'stantonNumber':           stanton,
        'frictionCoefficient':     friction,
        'energyGroup':             energyGroup,
        'momentumGroup':           momentumGroup,
        'groupRatio':              groupRatio,
        'velocityRatio':           beta,
        'definingDensity':         definingDensity,
        'enthalpyDifference':      enthalpyDifference,
        'heatTransferCoefficient': coefficient,
    }

def ievlevGasProperties(ceaOutput, chamberPressure: float, mixtureRatio: float,
                        prandtlModel: str = 'frozen') -> dict:

    '''

    The stagnation and wall gas Ievlev's method reads, from a NOVA CEA solve.

    An ideal-gas mixture's enthalpy depends only on its temperature and composition, so CEA gives
    the gas at any temperature below the chamber's by expanding the chamber gas in equilibrium until
    it reaches that temperature; the pressure the expansion ends at does not enter. The 1500 K
    state, whose gas constant sets the effective temperature T_e, comes from one such expansion,
    and the wall gas enthalpy from others on a 50 K grid that is interpolated.

    **The wall gas is taken at equilibrium below 1500 K rather than frozen there.** The paper freezes
    the composition at 1500 K. For hydrogen and oxygen the two are the same gas, because
    recombination has finished by 1500 K. For carbon-bearing products the water-gas shift goes on
    below 1500 K, and the equilibrium wall gas carries its heat of reaction, which the paper's rule
    leaves out. Freezing instead at the 1500 K state's frozen specific heat is the other way to
    write it, and on the LOX/LH2 calorimeter chamber it overstates the enthalpy drop by 1 percent
    on a 900 K wall and 4 percent on a 300 K one, because that specific heat is higher than its mean
    down to the wall.

    Parameters:
    -----------
    ceaOutput : NOVA.ceaInterface.CEA
        The run's CEA solve.
    chamberPressure : float
        Chamber pressure [Pa].
    mixtureRatio : float
        Oxidizer to fuel mass ratio [-].
    prandtlModel : str
        'frozen' or 'equilibrium': which of CEA's chamber Prandtl numbers Eq. 1.3 reads. The paper
        does not say. Frozen is the default because the Prandtl terms of Eq. 1.3 are written for a
        non-reacting gas, and because with it this reading of the equations reproduces RPA's own
        barrel and peak flux on the 40k calorimeter chamber to 0 and 3 percent on the test's own
        wall temperature, where the equilibrium value runs both 17 percent high.

    Returns:
    --------
    dict : the `gas` argument of `ievlevHeatFlux`

    '''

    from scipy.optimize import brentq

    results = ceaOutput.ceaResults
    cea = ceaOutput.ceaObject
    pressurePsia = chamberPressure / 6894.757

    def exitTemperature(ratio):
        return cea.get_Temperatures(Pc = pressurePsia, MR = mixtureRatio, eps = ratio, frozen = 0)[2] * 5.0 / 9.0

    def expandedTo(temperature):
        # The area ratio at which the equilibrium expansion reaches a temperature. The bracket
        # stops short of the ratios at which CEA's expansion no longer converges.
        return brentq(lambda ratio: exitTemperature(ratio) - temperature, 1.5, 2.0e4, xtol = 1e-8)

    def enthalpyAt(ratio):
        return cea.get_Enthalpies(Pc = pressurePsia, MR = mixtureRatio, eps = ratio, frozen = 0)[2] * 2326.0

    ratio1500 = expandedTo(1500.0)
    molecularWeight1500 = cea.get_exit_MolWt_gamma(Pc = pressurePsia, MR = mixtureRatio, eps = ratio1500, frozen = 0)[0]

    grid = np.append(np.arange(300.0, 1500.0, 50.0), 1500.0)
    gridEnthalpy = np.array([enthalpyAt(expandedTo(temperature)) for temperature in grid])
    # Above 1500 K the composition is the 1500 K one, carried at the grid's last slope
    slope = (gridEnthalpy[-1] - gridEnthalpy[-2]) / (grid[-1] - grid[-2])

    def wallEnthalpy(wallTemperature: float) -> float:
        if wallTemperature > grid[-1]:
            return float(gridEnthalpy[-1] + slope * (wallTemperature - grid[-1]))
        return float(np.interp(wallTemperature, grid, gridEnthalpy))

    if prandtlModel == 'frozen':
        # The chamber state does not depend on the area ratio the call names
        prandtl = float(cea.get_Chamber_Transport(Pc = pressurePsia, MR = mixtureRatio, eps = 2.0, frozen = 1)[3])
    elif prandtlModel == 'equilibrium':
        prandtl = float(results['combustionChamberPrandtlNumber'])
    else:
        raise ValueError(f"No Prandtl model '{prandtlModel}'. Choose 'frozen' or 'equilibrium'.")

    return {
        'stagnationTemperature': float(results['combustionChamberTemperature']),
        'stagnationPressure':    chamberPressure,
        'gasConstant':           8314.46 / float(results['combustionChamberMolecularWeight']),
        'gasConstant1500':       8314.46 / float(molecularWeight1500),
        'gamma':                 float(results['combustionChamberGamma']),
        'stagnationViscosity':   float(results['combustionChamberViscosity']),
        'prandtlNumber':         prandtl,
        'stagnationEnthalpy':    float(results['combustionChamberEnthalpy']),
        'wallEnthalpy':          wallEnthalpy,
    }

def ievlevJacketCoefficient(wallAxial, wallRadius, nearWallMach, nearWallTemperature, nearWallPressure,
                            gamma, gasConstant, gas: dict, stationAxial, stationWallTemperature,
                            stationDrivingTemperature) -> np.ndarray:

    '''

    Ievlev's flux as the convective coefficient a jacket's station solve reads.

    The energy integral runs over the whole wall from its first station, which is the injector
    face, while a jacket solves only its own stations. So the flux is solved on the wall, with the
    wall temperature carried from the jacket's stations and held at their end values beyond them,
    and handed back at the stations as h = q / (T_drive - T_w): the coefficient that, applied to
    the station's own driving temperature at that wall, returns Ievlev's flux. A jacket that
    converges its wall temperature then converges on Ievlev's flux.

    Parameters:
    -----------
    wallAxial, wallRadius : array_like
        The wall from the injector face [m].
    nearWallMach, nearWallTemperature, nearWallPressure : array_like
        The near-wall state on the wall [-], [K], [Pa].
    gamma, gasConstant : array_like
        Ratio of specific heats and gas constant on the wall [-], [J/kg-K], for the velocity.
    gas : dict
        From `ievlevGasProperties`.
    stationAxial : array_like
        The jacket's stations [m], ascending.
    stationWallTemperature, stationDrivingTemperature : array_like
        The jacket's hot-wall temperature and its driving temperature at its stations [K].

    Returns:
    --------
    numpy.ndarray : the gas-side coefficient at each station [W/m^2 K]

    '''

    wallAxial = np.asarray(wallAxial, dtype = float)
    stationAxial = np.asarray(stationAxial, dtype = float)
    stationWallTemperature = np.asarray(stationWallTemperature, dtype = float)
    velocity = np.asarray(nearWallMach, dtype = float) * np.sqrt(
        np.asarray(gamma, dtype = float) * np.asarray(gasConstant, dtype = float)
        * np.asarray(nearWallTemperature, dtype = float))

    wallTemperature = np.interp(wallAxial, stationAxial, stationWallTemperature)
    result = ievlevHeatFlux(wallAxial, wallRadius, velocity, nearWallPressure, wallTemperature, gas)
    heatFlux = np.interp(stationAxial, wallAxial, result['heatFlux'])

    return heatFlux / (np.asarray(stationDrivingTemperature, dtype = float) - stationWallTemperature)
