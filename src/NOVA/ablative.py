# -- NOVA: Charring Ablator Material Response -- #

'''

The thermal response of an ablative nozzle liner, and the surface thermochemistry that sets how
fast it recedes.

An ablative liner is not a wall with a temperature. Heat drives a decomposition front into the
resin, the gas that front releases percolates out through the char and cools it on the way, and
the char face itself is consumed by the exhaust. Three coupled problems, and the answer a designer
wants -- how much throat did I lose, and how hot did the back of the liner get -- depends on all
three.

The model here is the CMA formulation (Moyer and Rindal, NASA CR-1061, 1968): one-dimensional
transient conduction in a coordinate system attached to the receding surface, Arrhenius
decomposition of the resin, pyrolysis gas in instantaneous thermal equilibrium with the solid it
passes through, and a surface energy balance closed by a transfer-coefficient boundary condition.
In the taxonomy the Ablation Workshop uses, that is a type 1 code.

Three surface closures are available and they answer different questions:

    temperature       The surface temperature is imposed and nothing recedes. This is the
                      in-depth problem on its own, which is how the workshop test cases isolate
                      conduction and pyrolysis from the boundary layer.
    bPrimeTable       Char removal and wall enthalpy are read from a tabulated equilibrium
                      surface thermochemistry solution, B'c and h_w against pressure, pyrolysis
                      gas blowing and wall temperature. NOVA packages one such table, for TACOT
                      in air.
    diffusionLimited  Char removal is the closed-form diffusion-limited carbon oxidation rate,
                      which needs only the elemental composition of the edge gas. This is the
                      closure that reaches rocket conditions, because it does not depend on
                      pressure and so is not capped by the range of a table. It is an upper
                      bound rather than a prediction: see below.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**The solver is verified, not validated.** Verification here means the discretisation is shown to
reproduce solutions that are known exactly. tests/testAblative.py carries the comparisons and
quantifies every error:

    - Semi-infinite solid, step surface temperature, against the erf solution.
    - Semi-infinite solid, constant surface flux, against the closed-form surface temperature.
    - Steady-state ablation, against the exponential profile T(y) = T_inf + (T_w - T_inf)
      exp(-s_dot y / alpha) that the moving-frame equation admits when the recession rate is
      constant.
    - Arrhenius decomposition at fixed temperature, against the closed form the reaction order
      of three admits.
    - Spatial and temporal convergence, with the observed order reported.
    - Discrete energy conservation over a full transient.

**The surface thermochemistry is validated in its two asymptotic limits.** The closed-form
diffusion-limited carbon B' reproduces the packaged TACOT equilibrium table to 0.002 per cent in
the carbon dioxide limit and 0.003 per cent in the carbon monoxide limit. Those tables were
generated independently, with CEA thermodynamic data and a 25 species mixture, by the Ablation
Workshop. Between those limits the closed form is not a model of the equilibrium result and does
not claim to be; that region is what the table is for.

**The nozzle application is not validated.** No open source gives measured throat recession
against a defined firing condition in enough detail to set a model against, and the material whose
response data is public -- TACOT -- is a low-density entry heatshield, not a nozzle liner. The
station march is therefore a verified solver driven by an unvalidated combination of a correlated
gas-side coefficient and a transport-limited recession rate. Treat its numbers as a comparison
between design options, not as a prediction of recession.

**The diffusion-limited rate is an upper bound on recession, not a prediction of it.** It
assumes two things that are both optimiztic about how fast the char goes away. Surface kinetics are
taken to be infinitely fast, which holds above roughly 2000 K and fails below it. And every oxygen
atom reaching the wall is taken to leave as carbon monoxide, which over-consumes carbon whenever
the exhaust carries hydrogen, because in equilibrium the hydrogen competes for that oxygen and some
of it leaves as water instead. Both errors run the same way. For a hydrocarbon or hydrogen
propellant the bound sits well above measured motor recession, by a factor that depends on the
combination and the wall temperature, and `charRemovalEfficiency` exists so that factor can be set
from firing data. Calibrating it against a measured recession is calibration and not validation,
and the value that comes out holds only over the conditions it was fitted to.

**Surface chemical heat release is not modeled by default.** The diffusion-limited closure
returns a mass removal rate and leaves the reaction enthalpy to the caller through
`surfaceHeatOfAblation`. Zero is not the physical value. In a rocket exhaust the char-consuming
reactions are dominated by C + CO2 -> 2 CO and C + H2O -> CO + H2, which are endothermic at
14.4 and 10.9 MJ per kg of carbon, so omitting them overpredicts wall temperature rather than
underpredicting it. Pure oxidation, C + 1/2 O2 -> CO, runs the other way at 9.2 MJ/kg released.

All units are mass base SI:
    - Length      [m]
    - Temperature [K]
    - Pressure    [Pa]
    - Enthalpy    [J/kg]
    - Mass flux   [kg/m^2 s]
    - Heat flux   [W/m^2]

Author: Sean Bowman

'''

import os
from dataclasses import dataclass

import numpy as np
from scipy.linalg import solve_banded

from . import materials
from .utils import ConvergenceFailureError, InvalidInputError

__all__ = [
    'AblationEnvironment', 'AblativeLinerResult', 'BPrimeTable', 'CharringMaterial',
    'MaterialResponseResult', 'ablativeNozzleLiner', 'blowingCorrection',
    'diffusionLimitedCharBPrime', 'elementMassFractionsFromMoles',
    'packagedBPrimeTablePath', 'propellantElementMassFractions', 'solveMaterialResponse',
    'STEFANBOLTZMANN',
]

STEFANBOLTZMANN = 5.670374419e-8        # [W/m^2 K^4], CODATA 2018, exact by definition of k_B

# Atomic masses, CEA's values, for the elemental balances at an ablating surface.
_ATOMICMASS = {
    'C': 12.0107, 'H': 1.00794, 'O': 15.9994, 'N': 14.0067, 'F': 18.9984032,
    'CL': 35.453, 'AL': 26.981538, 'S': 32.065, 'B': 10.811, 'SI': 28.0855,
}

def packagedBPrimeTablePath(tableName: str) -> str:

    '''

    Filesystem path of a surface thermochemistry table shipped inside the package.

    Parameters:
    -----------
    tableName : str
        Table name as a material's 'surfaceThermochemistry' entry gives it, without extension.

    Returns:
    --------
    str
        Absolute path to the .npz holding the table.

    '''

    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', tableName + '.npz')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Surface Thermochemistry -- #
#--------------------------------------------------------------------------------------------------------------------------#

def blowingCorrection(totalBPrime: float, blowingFactor: float = 0.5) -> float:

    '''

    Factor by which mass injection at the wall reduces the convective transfer coefficient.

    Gas leaving an ablating surface thickens the boundary layer and pushes the temperature
    gradient away from the wall. The correlation is the one CMA uses,

        CH / CH0 = ln(1 + 2 lambda B') / (2 lambda B')

    with B' the total non-dimensional blowing rate, char plus pyrolysis gas, and lambda an
    empirical factor near 0.5 for a turbulent boundary layer and 0.4 for a laminar one. The
    Ablation Workshop test cases fix lambda at 0.5, which is why that is the default.

    This is the single largest self-limiting effect in an ablation problem. At B' = 1 the
    coefficient is already down to 55 per cent of its unblown value, so a liner that starts to run
    away partly protects itself.

    Parameters:
    -----------
    totalBPrime : float
        Sum of the char and pyrolysis gas blowing rates [-]. Must not be negative.
    blowingFactor : float
        Lambda in the correlation [-].

    Returns:
    --------
    float
        Multiplier on the unblown transfer coefficient [-]. Exactly 1 at zero blowing.

    Raises:
    -------
    InvalidInputError
        If the blowing rate is negative, which has no physical meaning here: the correlation
        describes mass leaving the surface, not entering it.

    '''

    if totalBPrime < 0.0:
        raise InvalidInputError(
            message = 'A negative total B-prime describes mass entering the wall, which the '
                      'blowing correction does not model.',
            parameterName = 'totalBPrime',
            value = totalBPrime,
            validRange = 'zero or greater')

    argument = 2.0 * blowingFactor * totalBPrime

    # The limit is 1 as the argument goes to zero. Taking the ratio directly there is 0/0, and
    # near there it loses precision, so switch to the series below a threshold well inside
    # double precision.
    if argument < 1.0e-6:
        return 1.0 - argument / 2.0 + argument**2 / 6.0

    return np.log1p(argument) / argument

def elementMassFractionsFromMoles(moleFractions: dict) -> dict:

    '''

    Convert elemental mole fractions to elemental mass fractions.

    Material data states pyrolysis gas composition in mole fractions of the elements, while every
    surface mass balance is written in mass fractions. This is the conversion between them.

    Parameters:
    -----------
    moleFractions : dict
        Element symbol to mole fraction. Need not be normalized; symbols are case insensitive.

    Returns:
    --------
    dict
        Element symbol to mass fraction, summing to one.

    Raises:
    -------
    InvalidInputError
        If an element is not in the atomic mass table, or the fractions sum to zero.

    '''

    weighted = {}
    for symbol, fraction in moleFractions.items():
        key = symbol.strip().upper()
        if key not in _ATOMICMASS:
            raise InvalidInputError(
                message = 'No atomic mass carried for element {!r}.'.format(symbol),
                parameterName = 'moleFractions',
                value = symbol,
                validRange = 'one of ' + ', '.join(sorted(_ATOMICMASS)))
        weighted[key] = fraction * _ATOMICMASS[key]

    total = sum(weighted.values())
    if total <= 0.0:
        raise InvalidInputError(
            message = 'Elemental mole fractions sum to zero, so no mass fractions exist.',
            parameterName = 'moleFractions',
            value = total,
            validRange = 'greater than zero')

    return {symbol: value / total for symbol, value in weighted.items()}

def propellantElementMassFractions(fuelElements: dict, oxidiserElements: dict,
                                   mixtureRatio: float) -> dict:

    '''

    Elemental mass fractions of the combustion products of a propellant pair.

    Combustion rearranges molecules and conserves elements, so the elemental composition of the
    exhaust is the elemental composition of what went in. No equilibrium solve is needed and none
    is done here: the result is exact given the reactant formulae and the mixture ratio.

    That matters because the diffusion-limited char removal rate depends on the edge gas only
    through its elemental oxygen and carbon, so this function is the whole of what
    `diffusionLimitedCharBPrime` needs from a propellant combination.

    Parameters:
    -----------
    fuelElements : dict
        Element symbol to mass fraction within the fuel. RP-1 as CH1.95 is
        {'C': 0.8600, 'H': 0.1400}; methane is {'C': 0.7487, 'H': 0.2513}.
    oxidiserElements : dict
        Element symbol to mass fraction within the oxidiser. Liquid oxygen is {'O': 1.0}.
    mixtureRatio : float
        Oxidiser to fuel mass ratio [-].

    Returns:
    --------
    dict
        Element symbol to mass fraction in the products, summing to one.

    Raises:
    -------
    InvalidInputError
        If the mixture ratio is not positive.

    '''

    if mixtureRatio <= 0.0:
        raise InvalidInputError(
            message = 'A mixture ratio of zero or less describes no combustion.',
            parameterName = 'mixtureRatio',
            value = mixtureRatio,
            validRange = 'greater than zero')

    fuelMass = 1.0 / (1.0 + mixtureRatio)
    oxidiserMass = mixtureRatio / (1.0 + mixtureRatio)

    combined = {}
    for source, mass in ((fuelElements, fuelMass), (oxidiserElements, oxidiserMass)):
        scale = sum(source.values())
        if scale <= 0.0:
            raise InvalidInputError(
                message = 'A propellant whose element mass fractions sum to zero has no mass.',
                parameterName = 'fuelElements/oxidiserElements',
                value = scale,
                validRange = 'greater than zero')
        for symbol, fraction in source.items():
            key = symbol.strip().upper()
            combined[key] = combined.get(key, 0.0) + mass * fraction / scale

    return combined

def diffusionLimitedCharBPrime(edgeElements: dict, gasBPrime: float = 0.0,
                               pyrolysisGasElements: dict = None,
                               product: str = 'CO') -> float:

    '''

    Non-dimensional char removal rate in the diffusion-limited carbon oxidation regime.

    Above roughly 2000 K the surface kinetics of carbon oxidation are fast enough that the removal
    rate is set by how quickly oxygen can be carried to the wall, not by how quickly it reacts
    once there. In that regime the answer follows from an elemental balance alone.

    Writing the surface balance for element k with equal diffusion coefficients,

        (Z_k,e - Z_k,w) + B'c (Z_k,c - Z_k,w) + B'g (Z_k,g - Z_k,w) = 0

    and imposing that every oxygen atom at the wall leaves as carbon monoxide, so that
    Z_C,w = (M_C / M_O) Z_O,w with no carbon left over, closes it:

        B'c = (M_C / M_O) (Z_O,e + B'g Z_O,g) - Z_C,e - B'g Z_C,g

    The carbon dioxide branch, which is what equilibrium gives below about 900 K, carries a factor
    of one half on the mass ratio because each carbon then takes two oxygens.

    Both branches are validated against the packaged TACOT equilibrium table in
    tests/testAblative.py, where they agree with it to better than 0.003 per cent in the
    asymptotic regions the branch is the limit of. Between those regions the equilibrium result
    lies between the two branches and neither closed form describes it; use `BPrimeTable` there.

    The result is an upper bound on char removal. Requiring every wall oxygen atom to leave as
    carbon monoxide over-consumes carbon whenever the edge gas carries hydrogen, since in
    equilibrium some of that oxygen leaves as water instead, and assuming transport control
    over-consumes it again wherever the wall is too cool for the surface kinetics to keep up.
    Air carries no hydrogen and an ablating heatshield runs hot, which is why the bound is tight
    against the TACOT table and loose against a hydrocarbon rocket exhaust.

    Parameters:
    -----------
    edgeElements : dict
        Elemental mass fractions of the boundary layer edge gas. For a rocket, that is
        `propellantElementMassFractions`.
    gasBPrime : float
        Pyrolysis gas blowing rate [-]. Zero for a non-charring material such as bulk graphite.
    pyrolysisGasElements : dict | None
        Elemental mass fractions of the pyrolysis gas. Required when gasBPrime is non-zero.
    product : str
        'CO' for the high-temperature branch, 'CO2' for the low-temperature branch.

    Returns:
    --------
    float
        Char blowing rate B'c [-], floored at zero. Zero means the edge gas carries too little
        oxygen relative to its carbon to consume any char.

    Raises:
    -------
    InvalidInputError
        If the product branch is not one of the two, or pyrolysis gas blowing is asked for
        without a pyrolysis gas composition.

    '''

    if product.strip().upper() not in ('CO', 'CO2'):
        raise InvalidInputError(
            message = 'Only the carbon monoxide and carbon dioxide branches are closed forms.',
            parameterName = 'product',
            value = product,
            validRange = "'CO' or 'CO2'")

    if gasBPrime > 0.0 and not pyrolysisGasElements:
        raise InvalidInputError(
            message = 'Pyrolysis gas blowing carries its own carbon and oxygen into the balance, '
                      'so its composition is needed to close it.',
            parameterName = 'pyrolysisGasElements',
            value = pyrolysisGasElements,
            validRange = 'elemental mass fractions of the pyrolysis gas')

    def fraction(source, symbol):
        if not source:
            return 0.0
        return sum(value for key, value in source.items() if key.strip().upper() == symbol)

    oxygenPerCarbon = _ATOMICMASS['C'] / _ATOMICMASS['O']
    if product.strip().upper() == 'CO2':
        oxygenPerCarbon *= 0.5

    edgeOxygen = fraction(edgeElements, 'O')
    edgeCarbon = fraction(edgeElements, 'C')
    gasOxygen = fraction(pyrolysisGasElements, 'O')
    gasCarbon = fraction(pyrolysisGasElements, 'C')

    charBPrime = (oxygenPerCarbon * (edgeOxygen + gasBPrime * gasOxygen)
                  - edgeCarbon - gasBPrime * gasCarbon)

    return max(charBPrime, 0.0)

class BPrimeTable:

    '''

    Tabulated equilibrium surface thermochemistry: char blowing rate and wall enthalpy.

    A B-prime table is the output of an equilibrium solve run once over a grid and stored, so that
    a material response does not have to call a thermochemistry solver at every timestep of every
    node. It answers two questions at a given wall pressure, wall temperature and pyrolysis gas
    blowing rate: how fast is char removed, and what is the enthalpy of the gas mixture sitting on
    the wall.

    Interpolation is linear in the logarithm of pressure and in the other two axes. Requests
    outside the grid are clamped to its edge rather than extrapolated, because both quantities
    turn over sharply at the sublimation onset and a linear extrapolation past it is nonsense.
    `clampedRequests` counts how often that happened so a caller can tell whether a run stayed
    inside the data.

    The packaged table is for air. Its pressure axis stops at one atmosphere, which is two to
    three orders of magnitude below a rocket chamber, and its edge gas is oxidising rather than
    the reducing mixture a rocket exhaust actually is. It closes an arc-jet or an entry problem.
    It does not close a nozzle, and `clampedRequests` will say so loudly if it is asked to.

    '''

    def __init__(self, pressure, gasBPrime, temperature, charBPrime, wallEnthalpy,
                 sourceName: str = 'unnamed'):

        '''

        Build a table from its grid axes and the two quantities defined on them.

        Parameters:
        -----------
        pressure : array_like
            Pressure axis [Pa], ascending.
        gasBPrime : array_like
            Pyrolysis gas blowing axis [-], ascending.
        temperature : array_like
            Wall temperature axis [K], ascending.
        charBPrime : array_like
            Char blowing rate [-] on the (pressure, gasBPrime, temperature) grid.
        wallEnthalpy : array_like
            Enthalpy of the gas mixture at the wall [J/kg] on the same grid.
        sourceName : str
            Name carried into error messages and diagnostics.

        '''

        self.pressure = np.asarray(pressure, dtype = float)
        self.gasBPrime = np.asarray(gasBPrime, dtype = float)
        self.temperature = np.asarray(temperature, dtype = float)
        self.sourceName = sourceName
        self.clampedRequests = 0

        self._charBPrime = np.asarray(charBPrime, dtype = float)
        self._wallEnthalpy = np.asarray(wallEnthalpy, dtype = float)
        self._logPressure = np.log(self.pressure)

        # The solver asks for the same pressure many thousands of times in a row while the
        # temperature and blowing move, so the pressure interpolation is done once and the two
        # remaining axes are read bilinearly off the cached slice.
        self._slicePressure = None
        self._charBPrimeSlice = None
        self._wallEnthalpySlice = None

    @classmethod
    def fromPackagedTable(cls, tableName: str) -> 'BPrimeTable':

        '''

        Load one of the tables shipped inside the package.

        Parameters:
        -----------
        tableName : str
            Table name as a material's 'surfaceThermochemistry' entry gives it.

        Returns:
        --------
        BPrimeTable

        Raises:
        -------
        InvalidInputError
            If no table of that name is packaged.

        '''

        path = packagedBPrimeTablePath(tableName)
        if not os.path.isfile(path):
            raise InvalidInputError(
                message = 'No packaged surface thermochemistry table named {!r}.'.format(
                    tableName),
                parameterName = 'tableName',
                value = tableName,
                validRange = 'a .npz in src/NOVA/assets/')

        with np.load(path) as data:
            return cls(data['pressure'], data['gasBPrime'], data['temperature'],
                       data['charBPrime'], data['wallEnthalpy'], sourceName = tableName)

    def _slicesAt(self, pressure: float):

        '''The two tables reduced to one pressure, cached between requests at that pressure.'''

        if pressure != self._slicePressure:
            weight = np.interp(np.log(pressure), self._logPressure,
                               np.arange(self.pressure.size, dtype = float))
            lower = int(np.floor(weight))
            upper = min(lower + 1, self.pressure.size - 1)
            blend = weight - lower
            self._charBPrimeSlice = ((1.0 - blend) * self._charBPrime[lower]
                                     + blend * self._charBPrime[upper])
            self._wallEnthalpySlice = ((1.0 - blend) * self._wallEnthalpy[lower]
                                       + blend * self._wallEnthalpy[upper])
            self._slicePressure = pressure

        return self._charBPrimeSlice, self._wallEnthalpySlice

    def _clampedPoint(self, pressure, gasBPrime, temperature):

        '''The request point, pulled back onto the grid, counting any clamp that was needed.'''

        clampedPressure = min(max(pressure, self.pressure[0]), self.pressure[-1])
        clampedGas = min(max(gasBPrime, self.gasBPrime[0]), self.gasBPrime[-1])
        clampedTemperature = min(max(temperature, self.temperature[0]), self.temperature[-1])

        if (clampedPressure != pressure or clampedGas != gasBPrime
                or clampedTemperature != temperature):
            self.clampedRequests += 1

        return clampedPressure, clampedGas, clampedTemperature

    def _bilinear(self, values, gasBPrime, temperature):

        '''One bilinear read off a pressure slice.'''

        column = np.interp(gasBPrime, self.gasBPrime,
                           np.arange(self.gasBPrime.size, dtype = float))
        row = np.interp(temperature, self.temperature,
                        np.arange(self.temperature.size, dtype = float))
        columnLower = min(int(column), self.gasBPrime.size - 2)
        rowLower = min(int(row), self.temperature.size - 2)
        columnBlend = column - columnLower
        rowBlend = row - rowLower

        return ((1.0 - columnBlend) * ((1.0 - rowBlend) * values[columnLower, rowLower]
                                       + rowBlend * values[columnLower, rowLower + 1])
                + columnBlend * ((1.0 - rowBlend) * values[columnLower + 1, rowLower]
                                 + rowBlend * values[columnLower + 1, rowLower + 1]))

    def charBPrime(self, pressure: float, gasBPrime: float, temperature: float) -> float:

        '''

        Char blowing rate at one condition.

        Parameters:
        -----------
        pressure : float
            Wall pressure [Pa].
        gasBPrime : float
            Pyrolysis gas blowing rate [-].
        temperature : float
            Wall temperature [K].

        Returns:
        --------
        float
            Char blowing rate B'c [-].

        '''

        pressure, gasBPrime, temperature = self._clampedPoint(
            pressure, gasBPrime, temperature)
        charBPrime, _ = self._slicesAt(pressure)

        return float(self._bilinear(charBPrime, gasBPrime, temperature))

    def wallEnthalpy(self, pressure: float, gasBPrime: float, temperature: float) -> float:

        '''

        Enthalpy of the gas mixture at the wall at one condition.

        Parameters:
        -----------
        pressure : float
            Wall pressure [Pa].
        gasBPrime : float
            Pyrolysis gas blowing rate [-].
        temperature : float
            Wall temperature [K].

        Returns:
        --------
        float
            Wall enthalpy [J/kg], on the same datum as the material enthalpy curves.

        '''

        pressure, gasBPrime, temperature = self._clampedPoint(
            pressure, gasBPrime, temperature)
        _, wallEnthalpy = self._slicesAt(pressure)

        return float(self._bilinear(wallEnthalpy, gasBPrime, temperature))

#--------------------------------------------------------------------------------------------------------------------------#
# -- Material -- #
#--------------------------------------------------------------------------------------------------------------------------#

class CharringMaterial:

    '''

    Property curves and decomposition kinetics of one charring ablator.

    Between the virgin and char states every property is blended on the CMA resin fraction

        tau = (1 - rho_c / rho) / (1 - rho_c / rho_v)

    which is one in the virgin material and zero in fully formed char. Note that tau is not linear
    in density: it weights by the mass of resin still undecomposed, which is what the property
    actually tracks.

    Enthalpy is absolute and carries the heat of formation, so the heat of pyrolysis is the
    virgin-to-char enthalpy difference rather than a separate number. That is why a material can
    be described completely by its two end-state enthalpy curves and its kinetics.

    '''

    def __init__(self, name, virginDensity, charDensity, temperature, virgin, char, components,
                 resinVolumeFraction, porosity, pyrolysisGasElements = None,
                 charElements = None, surfaceThermochemistry = None,
                 pyrolysisGasProperties = None):

        '''

        Build a material from its curves and kinetics.

        Parameters:
        -----------
        name : str
            Material name, carried into diagnostics.
        virginDensity, charDensity : float
            Bulk density of the two end states [kg/m^3].
        temperature : array_like
            Temperature grid the curves are defined on [K].
        virgin, char : dict
            'specificHeat' [J/kg-K], 'thermalConductivity' [W/m-K], 'enthalpy' [J/kg] on that
            grid, and a scalar 'emissivity'.
        components : sequence of dict
            One entry per decomposing phase, with 'virginDensity', 'charDensity',
            'preExponentialFactor' [1/s], 'activationTemperature' [K], 'reactionOrder' and
            'onsetTemperature' [K].
        resinVolumeFraction, porosity : float
            The two mixing-rule constants that turn component densities into bulk density.
        pyrolysisGasElements, charElements : dict | None
            Elemental mole fractions, converted to mass fractions on construction.
        surfaceThermochemistry : str | None
            Name of the packaged B-prime table that goes with this material, if any.
        pyrolysisGasProperties : str | tuple | None
            Where the pyrolysis gas enthalpy comes from: the name of a packaged table, or a
            (temperatures, enthalpies) pair for a pressure-independent curve. A material with
            decomposing components must have one, because the heat of pyrolysis is the gap
            between the solid enthalpy that leaves and the gas enthalpy that replaces it, and
            the solid curves alone do not contain it.

        Raises:
        -------
        InvalidInputError
            If the material decomposes and no pyrolysis gas enthalpy source is given.

        '''

        self.name = name
        self.virginDensity = float(virginDensity)
        self.charDensity = float(charDensity)
        self.resinVolumeFraction = float(resinVolumeFraction)
        self.porosity = float(porosity)
        self.surfaceThermochemistry = surfaceThermochemistry

        self.temperature = np.asarray(temperature, dtype = float)
        self.virginEmissivity = float(virgin['emissivity'])
        self.charEmissivity = float(char['emissivity'])

        # The solver samples every curve at every node on every Newton iteration, tens of
        # thousands of times in a run, so the curves are held as plain arrays and read with
        # np.interp rather than through an interpolator object. Outside the grid they hold flat,
        # which np.interp does by default: the curves already reach 3333 K, past any temperature
        # a surviving liner sees.
        def curve(values):
            return np.asarray(values, dtype = float)

        self._virginSpecificHeat = curve(virgin['specificHeat'])
        self._charSpecificHeat = curve(char['specificHeat'])
        self._virginConductivity = curve(virgin['thermalConductivity'])
        self._charConductivity = curve(char['thermalConductivity'])
        self._virginEnthalpy = curve(virgin['enthalpy'])
        self._charEnthalpy = curve(char['enthalpy'])

        self.componentVirginDensity = np.array(
            [c['virginDensity'] for c in components], dtype = float)
        self.componentCharDensity = np.array(
            [c['charDensity'] for c in components], dtype = float)
        self.preExponentialFactor = np.array(
            [c['preExponentialFactor'] for c in components], dtype = float)
        self.activationTemperature = np.array(
            [c['activationTemperature'] for c in components], dtype = float)
        self.reactionOrder = np.array([c['reactionOrder'] for c in components], dtype = float)
        self.onsetTemperature = np.array([c['onsetTemperature'] for c in components], dtype = float)

        # The mixing rule weights the resin phases together and the reinforcement separately.
        # Component C in the TACOT layout is the reinforcement, and is identified by not
        # decomposing rather than by its position.
        decomposes = self.preExponentialFactor > 0.0
        self._componentWeight = np.where(
            decomposes,
            (1.0 - self.porosity) * self.resinVolumeFraction,
            (1.0 - self.porosity) * (1.0 - self.resinVolumeFraction))

        self.pyrolysisGasElements = (elementMassFractionsFromMoles(pyrolysisGasElements)
                                     if pyrolysisGasElements else None)
        self.charElements = (elementMassFractionsFromMoles(charElements)
                             if charElements else None)

        self.decomposes = bool(np.any(decomposes))
        self._gasEnthalpy = None
        self._gasEnthalpyCurve = None
        self._gasCurveCache = None

        if isinstance(pyrolysisGasProperties, str):
            path = packagedBPrimeTablePath(pyrolysisGasProperties)
            if not os.path.isfile(path):
                raise InvalidInputError(
                    message = 'No packaged pyrolysis gas table named {!r}.'.format(
                        pyrolysisGasProperties),
                    parameterName = 'pyrolysisGasProperties',
                    value = pyrolysisGasProperties,
                    validRange = 'a .npz in src/NOVA/assets/')
            with np.load(path) as data:
                self._gasPressure = np.asarray(data['pressure'], dtype = float)
                self._gasTemperature = np.asarray(data['temperature'], dtype = float)
                self._gasEnthalpy = np.asarray(data['enthalpy'], dtype = float)
        elif pyrolysisGasProperties is not None:
            gasTemperature, gasEnthalpy = pyrolysisGasProperties
            self._gasEnthalpyCurve = (np.asarray(gasTemperature, dtype = float),
                                      np.asarray(gasEnthalpy, dtype = float))
        elif self.decomposes:
            raise InvalidInputError(
                message = 'This material decomposes, so its heat of pyrolysis is the '
                          'difference between the solid enthalpy leaving and the gas enthalpy '
                          'replacing it. Without a pyrolysis gas enthalpy curve that '
                          'difference is zero, which is not a property of any resin.',
                parameterName = 'pyrolysisGasProperties',
                value = None,
                validRange = 'a packaged table name, or a (temperature, enthalpy) pair')

    @classmethod
    def fromStore(cls, material: str) -> 'CharringMaterial':

        '''

        Build a material from the ablative response store in `NOVA.materials`.

        Parameters:
        -----------
        material : str
            A name from `materials.availableAblativeMaterials()`.

        Returns:
        --------
        CharringMaterial

        '''

        entry = materials.ablativeResponseData(material)
        name = next(key for key in materials.availableAblativeMaterials()
                    if key.lower() == material.strip().lower())

        return cls(name = name,
                   virginDensity = entry['virginDensity'],
                   charDensity = entry['charDensity'],
                   temperature = entry['temperature'],
                   virgin = entry['virgin'],
                   char = entry['char'],
                   components = entry['pyrolysis']['components'],
                   resinVolumeFraction = entry['pyrolysis']['resinVolumeFraction'],
                   porosity = entry['pyrolysis']['porosity'],
                   pyrolysisGasElements = entry.get('pyrolysisGasElements'),
                   charElements = entry.get('charElements'),
                   surfaceThermochemistry = entry.get('surfaceThermochemistry'),
                   pyrolysisGasProperties = entry.get('pyrolysisGasProperties'))

    def bulkDensity(self, componentDensities) -> np.ndarray:

        '''

        Bulk density from the component densities, through the CMA mixing rule.

        Parameters:
        -----------
        componentDensities : array_like
            Component densities [kg/m^3], components on the last axis.

        Returns:
        --------
        numpy.ndarray
            Bulk density [kg/m^3].

        '''

        return np.tensordot(np.asarray(componentDensities, dtype = float),
                            self._componentWeight, axes = ([-1], [0]))

    def resinFraction(self, density) -> np.ndarray:

        '''

        The CMA blending variable tau at a given bulk density.

        Parameters:
        -----------
        density : array_like
            Bulk density [kg/m^3].

        Returns:
        --------
        numpy.ndarray
            tau [-], clamped to the physical range zero to one. A material whose char and virgin
            densities are equal loses no mass, so there is nothing to blend and tau is one
            everywhere: its virgin curves are its only curves.

        '''

        density = np.asarray(density, dtype = float)
        denominator = 1.0 - self.charDensity / self.virginDensity

        if abs(denominator) < 1.0e-12:
            return np.ones_like(density)

        numerator = 1.0 - self.charDensity / density

        return np.clip(numerator / denominator, 0.0, 1.0)

    def specificHeat(self, temperature, density) -> np.ndarray:

        '''

        Blended specific heat.

        Parameters:
        -----------
        temperature : array_like
            Temperature [K].
        density : array_like
            Bulk density [kg/m^3].

        Returns:
        --------
        numpy.ndarray
            Specific heat [J/kg-K].

        '''

        tau = self.resinFraction(density)

        return tau * np.interp(temperature, self.temperature, self._virginSpecificHeat) + \
               (1.0 - tau) * np.interp(temperature, self.temperature, self._charSpecificHeat)

    def thermalConductivity(self, temperature, density) -> np.ndarray:

        '''

        Blended thermal conductivity.

        Parameters:
        -----------
        temperature : array_like
            Temperature [K].
        density : array_like
            Bulk density [kg/m^3].

        Returns:
        --------
        numpy.ndarray
            Thermal conductivity [W/m-K].

        '''

        tau = self.resinFraction(density)

        return tau * np.interp(temperature, self.temperature, self._virginConductivity) + \
               (1.0 - tau) * np.interp(temperature, self.temperature, self._charConductivity)

    def enthalpy(self, temperature, density) -> np.ndarray:

        '''

        Blended absolute enthalpy, including the heat of formation.

        Parameters:
        -----------
        temperature : array_like
            Temperature [K].
        density : array_like
            Bulk density [kg/m^3].

        Returns:
        --------
        numpy.ndarray
            Enthalpy [J/kg], on the datum the material's curves use.

        '''

        tau = self.resinFraction(density)

        return tau * np.interp(temperature, self.temperature, self._virginEnthalpy) + \
               (1.0 - tau) * np.interp(temperature, self.temperature, self._charEnthalpy)

    def pyrolysisGasEnthalpy(self, temperature, pressure: float = 101325.0) -> np.ndarray:

        '''

        Absolute enthalpy of the pyrolysis gas.

        Evaluated at the temperature of the solid the gas is passing through, which is the
        thermal equilibrium assumption a type 1 model rests on, and at the local pressure,
        because the equilibrium composition of the gas shifts with it.

        This curve is what carries the heat of pyrolysis. The solid enthalpy curves say what
        the virgin and char states hold; the gap between the solid mass that leaves and the
        gas that replaces it is the reaction enthalpy, and it is not a constant: for TACOT the
        decomposition is mildly exothermic below about 700 K and endothermic above it.

        Parameters:
        -----------
        temperature : array_like
            Temperature [K].
        pressure : float
            Local pressure [Pa]. Ignored for a pressure-independent curve, and clamped to the
            table range otherwise.

        Returns:
        --------
        numpy.ndarray
            Pyrolysis gas enthalpy [J/kg], on the same datum as the solid curves.

        Raises:
        -------
        InvalidInputError
            If the material carries no pyrolysis gas enthalpy source.

        '''

        temperature = np.asarray(temperature, dtype = float)

        if self._gasEnthalpyCurve is not None:
            grid, values = self._gasEnthalpyCurve
            return np.interp(temperature, grid, values)

        if self._gasEnthalpy is None:
            raise InvalidInputError(
                message = 'This material carries no pyrolysis gas enthalpy.',
                parameterName = 'pyrolysisGasProperties',
                value = None,
                validRange = 'set on construction')

        return np.interp(temperature, self._gasTemperature,
                         self._gasEnthalpyAtPressure(pressure))

    def _gasEnthalpyAtPressure(self, pressure: float) -> np.ndarray:

        '''

        The pyrolysis gas enthalpy curve at one pressure, interpolated between table pressures.

        Held separately and cached because the pressure changes once per timestep while the
        temperature changes at every node on every iteration.

        Parameters:
        -----------
        pressure : float
            Local pressure [Pa]. Clamped to the range the table covers.

        Returns:
        --------
        numpy.ndarray
            Enthalpy on the table's own temperature grid [J/kg].

        '''

        clamped = min(max(pressure, self._gasPressure[0]), self._gasPressure[-1])

        if self._gasCurveCache is not None and self._gasCurveCache[0] == clamped:
            return self._gasCurveCache[1]

        logarithms = np.log(self._gasPressure)
        weight = np.interp(np.log(clamped), logarithms,
                           np.arange(self._gasPressure.size, dtype = float))
        lower = int(np.floor(weight))
        upper = min(lower + 1, self._gasPressure.size - 1)
        blend = weight - lower
        curve = (1.0 - blend) * self._gasEnthalpy[lower] + blend * self._gasEnthalpy[upper]
        self._gasCurveCache = (clamped, curve)

        return curve

    def emissivity(self, density) -> np.ndarray:

        '''

        Blended surface emissivity.

        Parameters:
        -----------
        density : array_like
            Bulk density at the surface [kg/m^3].

        Returns:
        --------
        numpy.ndarray
            Emissivity [-].

        '''

        tau = self.resinFraction(density)

        return tau * self.virginEmissivity + (1.0 - tau) * self.charEmissivity

    def decompositionRate(self, componentDensities, temperature) -> np.ndarray:

        '''

        Mass of each component decomposing per unit volume per unit time.

        The rate law is Goldstein's, in the form CMA takes it:

            -d(rho_i)/dt = A_i rho_i_v ((rho_i - rho_i_c) / rho_i_v)^psi_i exp(-E_i / (R T))

        and it is zero below the component's onset temperature and once the component has fully
        charred.

        Parameters:
        -----------
        componentDensities : array_like
            Component densities [kg/m^3], components on the last axis.
        temperature : array_like
            Temperature [K].

        Returns:
        --------
        numpy.ndarray
            Positive decomposition rate of each component [kg/m^3 s], same shape as the input
            densities.

        '''

        densities = np.asarray(componentDensities, dtype = float)
        temperature = np.asarray(temperature, dtype = float)[..., None]

        remaining = np.clip(
            (densities - self.componentCharDensity) / self.componentVirginDensity, 0.0, None)

        with np.errstate(over = 'ignore', divide = 'ignore', invalid = 'ignore'):
            arrhenius = np.exp(-self.activationTemperature
                               / np.maximum(temperature, 1.0e-30))
            rate = (self.preExponentialFactor * self.componentVirginDensity
                    * remaining**self.reactionOrder * arrhenius)

        active = (temperature >= self.onsetTemperature) & (self.preExponentialFactor > 0.0)

        return np.where(active, np.nan_to_num(rate), 0.0)

    def advanceDecomposition(self, componentDensities, temperature, timeStep) -> np.ndarray:

        '''

        Integrate the decomposition over one timestep, exactly, holding temperature fixed.

        For a reaction order other than one the rate law separates and integrates in closed form,

            u(t) = [u_0^(1 - psi) + (psi - 1) A exp(-E / R T) t]^(1 / (1 - psi))

        with u the fraction of the component left to decompose. Using that rather than a stepped
        integration removes the stiffness entirely: the decomposition can never overshoot its char
        density and the timestep is set by the conduction alone.

        Parameters:
        -----------
        componentDensities : array_like
            Component densities at the start of the step [kg/m^3], components on the last axis.
        temperature : array_like
            Temperature held over the step [K].
        timeStep : float
            Step length [s].

        Returns:
        --------
        numpy.ndarray
            Component densities at the end of the step [kg/m^3].

        '''

        densities = np.asarray(componentDensities, dtype = float)
        temperature = np.asarray(temperature, dtype = float)[..., None]

        remaining = np.clip(
            (densities - self.componentCharDensity) / self.componentVirginDensity, 0.0, None)

        with np.errstate(over = 'ignore', divide = 'ignore', invalid = 'ignore'):
            rateConstant = self.preExponentialFactor * np.exp(
                -self.activationTemperature / np.maximum(temperature, 1.0e-30))
            rateConstant = np.nan_to_num(rateConstant)

            order = self.reactionOrder
            firstOrder = np.isclose(order, 1.0)

            # The order-one case is the exception the closed form above does not cover.
            decayed = np.where(
                firstOrder,
                remaining * np.exp(-rateConstant * timeStep),
                np.where(remaining > 0.0,
                         (np.maximum(remaining, 1.0e-300)**(1.0 - order)
                          + (order - 1.0) * rateConstant * timeStep)**(1.0 / (1.0 - order)),
                         0.0))
            decayed = np.nan_to_num(decayed)

        active = (temperature >= self.onsetTemperature) & (self.preExponentialFactor > 0.0)
        remaining = np.where(active, np.clip(decayed, 0.0, remaining), remaining)

        return self.componentCharDensity + remaining * self.componentVirginDensity

#--------------------------------------------------------------------------------------------------------------------------#
# -- Boundary Condition -- #
#--------------------------------------------------------------------------------------------------------------------------#

@dataclass
class AblationEnvironment:

    '''

    What the boundary layer does to the surface, as a function of time.

    Every field that varies may be given as a scalar, as a callable of time, or as a
    (times, values) pair that is interpolated linearly. That covers a constant arc-jet condition,
    a shaped heat pulse and a nozzle station whose chamber pressure decays, without three
    different interfaces.

    Attributes:
    -----------
    surfaceClosure : str
        'temperature' imposes the surface temperature and forbids recession. 'bPrimeTable' reads
        char removal and wall enthalpy from `bPrimeTable`. 'diffusionLimited' computes char
        removal from `edgeElements` in closed form and drives the wall with a temperature
        potential.
    transferCoefficient : float | callable | tuple
        Unblown mass transfer coefficient rho_e u_e C_H [kg/m^2 s]. For a nozzle this is the
        Bartz heat transfer coefficient divided by the exhaust specific heat. May be a callable
        of (time, wallTemperature) when the gas-side coefficient depends on wall temperature, as
        Bartz does.
    edgeEnthalpy : float | callable | tuple
        Recovery enthalpy of the edge gas [J/kg], on the same datum as the material curves. Used
        by the 'bPrimeTable' closure.
    recoveryTemperature : float | callable | tuple
        Recovery temperature [K]. Used by the 'diffusionLimited' closure, whose convective flux
        is written as a temperature potential.
    edgeSpecificHeat : float | callable | tuple
        Specific heat of the edge gas [J/kg-K], used by 'diffusionLimited' to turn the
        temperature potential back into a heat flux.
    pressure : float | callable | tuple
        Wall static pressure [Pa].
    surfaceTemperature : float | callable | tuple
        Imposed surface temperature [K], used by the 'temperature' closure only.
    radiationInput : float | callable | tuple
        Incident radiative flux absorbed at the surface [W/m^2].
    ambientTemperature : float
        Sink temperature for re-radiation [K].
    viewFactor : float
        Fraction of the re-radiated flux that leaves [-]. One for a flat exposed surface; less
        inside a nozzle, where the surface sees itself.
    blowingFactor : float
        Lambda in the blowing correction [-].
    edgeElements : dict | None
        Elemental mass fractions of the edge gas, for the 'diffusionLimited' closure.
    oxidationProduct : str
        'CO' or 'CO2' branch for the 'diffusionLimited' closure.
    charRemovalEfficiency : float
        Multiplier on the diffusion-limited char blowing rate [-]. One is the transport-limited
        bound. Anything below it is a calibration against measured recession and carries only as
        far as the conditions it was fitted to.
    surfaceHeatOfAblation : float
        Energy absorbed at the surface per unit mass of char removed [J/kg], positive for an
        endothermic reaction. Zero by default and zero is not the physical value; see the module
        validation note.
    bPrimeTable : BPrimeTable | None
        Table backing the 'bPrimeTable' closure.
    backFaceCondition : str
        'adiabatic' or 'temperature'.
    backFaceTemperature : float | callable | tuple
        Imposed back face temperature [K] when that condition is chosen.
    suppressRecession : bool
        Force the char removal rate to zero while leaving the rest of the surface balance intact.
        Physically inconsistent, since the wall enthalpy of a surface that is not ablating is not
        the wall enthalpy of one that is, and it exists for one reason: it separates the boundary
        condition from the moving mesh, which is how the Ablation Workshop's test case 2.1
        isolates the two.

    '''

    surfaceClosure:        str = 'temperature'
    transferCoefficient:   object = 0.0
    edgeEnthalpy:          object = 0.0
    recoveryTemperature:   object = 0.0
    edgeSpecificHeat:      object = 0.0
    pressure:              object = 101325.0
    surfaceTemperature:    object = 300.0
    radiationInput:        object = 0.0
    ambientTemperature:    float = 300.0
    viewFactor:            float = 1.0
    blowingFactor:         float = 0.5
    edgeElements:          dict = None
    oxidationProduct:      str = 'CO'
    charRemovalEfficiency: float = 1.0
    surfaceHeatOfAblation: float = 0.0
    bPrimeTable:           object = None
    backFaceCondition:     str = 'adiabatic'
    backFaceTemperature:   object = 300.0
    suppressRecession:     bool = False

    def sample(self, name: str, time: float, wallTemperature: float = None) -> float:

        '''

        One scheduled quantity at one instant.

        Parameters:
        -----------
        name : str
            Attribute name to sample.
        time : float
            Time since the start of the run [s].
        wallTemperature : float | None
            Current wall temperature [K], passed to two-argument callables.

        Returns:
        --------
        float
            The value at that instant.

        '''

        value = getattr(self, name)

        if callable(value):
            try:
                return float(value(time, wallTemperature))
            except TypeError:
                return float(value(time))

        if isinstance(value, tuple) and len(value) == 2 and np.ndim(value[0]) == 1:
            times, values = value
            return float(np.interp(time, np.asarray(times, dtype = float),
                                   np.asarray(values, dtype = float)))

        return float(value)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Material Response Solver -- #
#--------------------------------------------------------------------------------------------------------------------------#

@dataclass
class MaterialResponseResult:

    '''

    Everything one material response run produced.

    Attributes:
    -----------
    time : numpy.ndarray
        Output times [s].
    depth : numpy.ndarray
        Node depths below the instantaneous surface at the final time [m].
    normalizedPosition : numpy.ndarray
        Node positions on zero to one, which is the mesh the solve actually ran on. Multiplying
        by the instantaneous thickness gives the depths at any output time.
    initialThickness : float
        Liner thickness at ignition [m].
    temperature : numpy.ndarray
        Temperature at every output time and node [K], time on the first axis.
    density : numpy.ndarray
        Bulk density on the same grid [kg/m^3].
    surfaceTemperature : numpy.ndarray
        Temperature of the receding surface [K].
    backFaceTemperature : numpy.ndarray
        Temperature of the back face [K].
    recession : numpy.ndarray
        Surface recession measured from the original surface [m].
    charMassFlux : numpy.ndarray
        Char removal rate at the surface [kg/m^2 s].
    pyrolysisGasMassFlux : numpy.ndarray
        Pyrolysis gas leaving the surface [kg/m^2 s].
    charBPrime, gasBPrime : numpy.ndarray
        The two blowing rates [-].
    blowingReduction : numpy.ndarray
        Blowing correction factor actually applied [-].
    charDepth : numpy.ndarray
        Depth below the original surface at which the material has charred to within two per cent
        of char density [m].
    pyrolysisDepth : numpy.ndarray
        Depth below the original surface at which the material has lost two per cent of the
        virgin-to-char density difference [m].
    surfaceHeatFlux : numpy.ndarray
        Net heat conducted into the solid at the surface [W/m^2].
    energyImbalance : float
        Worst closure error of the discrete energy balance over the run, relative to the largest
        single term in that balance [-]. A diagnostic on the solve, not on the physics. With a
        fixed surface it sits at machine precision. With recession it is first order in the
        surface cell size, because the surface node carries no volume and so cannot account for
        the material passing out through it; halving the first cell halves the error, and the
        recession and wall temperature are converged long before it does.
    tableClamps : int
        Number of B-prime table requests that fell outside the table and were clamped.
    material : str
        Material name.

    '''

    time:                 np.ndarray
    depth:                np.ndarray
    normalizedPosition:   np.ndarray
    initialThickness:     float
    temperature:          np.ndarray
    density:              np.ndarray
    surfaceTemperature:   np.ndarray
    backFaceTemperature:  np.ndarray
    recession:            np.ndarray
    charMassFlux:         np.ndarray
    pyrolysisGasMassFlux: np.ndarray
    charBPrime:           np.ndarray
    gasBPrime:            np.ndarray
    blowingReduction:     np.ndarray
    charDepth:            np.ndarray
    pyrolysisDepth:       np.ndarray
    surfaceHeatFlux:      np.ndarray
    energyImbalance:      float
    tableClamps:          int
    material:             str

    def temperatureAtDepth(self, depth: float) -> np.ndarray:

        '''

        History of the temperature at one fixed depth below the original surface.

        This is what a thermocouple reads. It is not a node history: the mesh moves with the
        receding surface, so a fixed material depth sits between different nodes as the run goes
        on, and the value is interpolated onto it at every output time.

        Parameters:
        -----------
        depth : float
            Depth below the original surface [m].

        Returns:
        --------
        numpy.ndarray
            Temperature at that depth at every output time [K]. Points that the surface has
            already receded past return the surface temperature.

        '''

        history = np.empty(self.time.size)

        for index in range(self.time.size):
            belowSurface = depth - self.recession[index]
            if belowSurface <= 0.0:
                history[index] = self.surfaceTemperature[index]
                continue
            currentDepth = self.normalizedPosition * (
                self.initialThickness - self.recession[index])
            history[index] = np.interp(belowSurface, currentDepth, self.temperature[index])

        return history

def _gradedNodes(numberOfNodes: int, growthRatio: float) -> np.ndarray:

    '''

    Normalized node positions, clustered at the surface.

    The gradients that matter in an ablation problem are all within a millimeter or two of the
    surface while the sample is centimeters deep, so a uniform mesh spends its nodes where nothing
    happens. Spacing grows geometrically from the surface by `growthRatio` per interval.

    Parameters:
    -----------
    numberOfNodes : int
        Node count, surface and back face included.
    growthRatio : float
        Ratio of one interval to the previous. One gives a uniform mesh.

    Returns:
    --------
    numpy.ndarray
        Node positions on zero to one, ascending, starting at exactly zero and ending at exactly
        one.

    '''

    intervals = np.array([growthRatio**index for index in range(numberOfNodes - 1)])
    positions = np.concatenate(([0.0], np.cumsum(intervals)))

    return positions / positions[-1]

def _surfaceBalance(material, environment, table, time, wallTemperature, gasMassFlux,
                    surfaceDensity):

    '''

    Net heat flux into the solid at an ablating surface, and the blowing state that produced it.

    Solves the transfer-coefficient surface energy balance at a given wall temperature. The char
    blowing rate depends on the transfer coefficient through B'g, and the transfer coefficient
    depends on the char blowing rate through the blowing correction, so the two are iterated to a
    fixed point before the balance is evaluated.

    Parameters:
    -----------
    material : CharringMaterial
        Material, for surface emissivity.
    environment : AblationEnvironment
        Boundary condition schedule.
    table : BPrimeTable | None
        Table backing the 'bPrimeTable' closure.
    time : float
        Current time [s].
    wallTemperature : float
        Current wall temperature [K].
    gasMassFlux : float
        Pyrolysis gas arriving at the surface [kg/m^2 s].
    surfaceDensity : float
        Bulk density at the surface [kg/m^3].

    Returns:
    --------
    tuple
        (heatFluxIntoSolid [W/m^2], charMassFlux [kg/m^2 s], charBPrime, gasBPrime,
        blowingReduction).

    '''

    unblown = environment.sample('transferCoefficient', time, wallTemperature)
    pressure = environment.sample('pressure', time, wallTemperature)
    emissivity = float(material.emissivity(surfaceDensity))

    reradiated = (emissivity * environment.viewFactor * STEFANBOLTZMANN
                  * (wallTemperature**4 - environment.ambientTemperature**4))
    absorbed = environment.sample('radiationInput', time, wallTemperature)

    if unblown <= 0.0:
        return absorbed - reradiated, 0.0, 0.0, 0.0, 1.0

    # Fixed point on the transfer coefficient. Blowing reduces it, which raises B'g, which raises
    # the blowing further. Converges monotonically and fast; ten passes is generous.
    blowingReduction = 1.0
    charBPrime = 0.0
    gasBPrime = 0.0
    for _ in range(40):
        blown = unblown * blowingReduction
        gasBPrime = gasMassFlux / blown

        if environment.suppressRecession:
            charBPrime = 0.0
        elif environment.surfaceClosure == 'bPrimeTable':
            charBPrime = table.charBPrime(pressure, gasBPrime, wallTemperature)
        else:
            charBPrime = environment.charRemovalEfficiency * diffusionLimitedCharBPrime(
                environment.edgeElements, gasBPrime, material.pyrolysisGasElements,
                environment.oxidationProduct)

        updated = blowingCorrection(charBPrime + gasBPrime, environment.blowingFactor)
        if abs(updated - blowingReduction) < 1.0e-12:
            blowingReduction = updated
            break
        blowingReduction = updated

    blown = unblown * blowingReduction
    charMassFlux = blown * charBPrime

    if environment.surfaceClosure == 'bPrimeTable':
        edgeEnthalpy = environment.sample('edgeEnthalpy', time, wallTemperature)
        wallEnthalpy = table.wallEnthalpy(pressure, gasBPrime, wallTemperature)
        charEnthalpy = float(material.enthalpy(wallTemperature, material.charDensity))
        gasEnthalpy = float(material.pyrolysisGasEnthalpy(wallTemperature, pressure)) \
                      if material.decomposes and gasMassFlux > 0.0 else wallEnthalpy

        # The CMA surface balance. Every term is an absolute enthalpy on one datum, so the heat of
        # the surface reactions is carried by the wall enthalpy rather than added separately.
        convective = blown * (edgeEnthalpy - wallEnthalpy)
        ablationTerms = charMassFlux * (charEnthalpy - wallEnthalpy) \
                        + gasMassFlux * (gasEnthalpy - wallEnthalpy)
        conducted = convective + ablationTerms + absorbed - reradiated
    else:
        recovery = environment.sample('recoveryTemperature', time, wallTemperature)
        specificHeat = environment.sample('edgeSpecificHeat', time, wallTemperature)
        convective = blown * specificHeat * (recovery - wallTemperature)
        conducted = convective + absorbed - reradiated \
                    - charMassFlux * environment.surfaceHeatOfAblation

    return conducted, charMassFlux, charBPrime, gasBPrime, blowingReduction

def solveMaterialResponse(material, environment: AblationEnvironment, thickness: float,
                          duration: float, timeStep: float = 0.01,
                          numberOfNodes: int = 121, growthRatio: float = 1.04,
                          initialTemperature: float = 300.0,
                          outputInterval: float = None,
                          maximumIterations: int = 60,
                          temperatureTolerance: float = 1.0e-8) -> MaterialResponseResult:

    '''

    Transient response of a charring ablator to a boundary layer, in one dimension.

    The formulation is CMA's. In a coordinate attached to the receding surface, with y measured
    from that surface into the material and s_dot the recession rate, the energy equation is

        d(rho h)/dt = d/dy (k dT/dy) + s_dot d(rho h)/dy + d(m_g h_g)/dy

    where the second term is the material moving past the mesh and the third is the pyrolysis gas
    convecting its enthalpy toward the surface. Pyrolysis gas is taken to be in thermal
    equilibrium with the solid it passes through and to leave instantaneously, which is what makes
    this a type 1 model: there is no momentum equation for the gas and no pressure field inside
    the material.

    The mesh is normalized on the shrinking thickness, so nodes stay in proportion as the surface
    recedes and none is ever dropped. Decomposition is integrated in closed form over each step,
    then the energy equation is solved implicitly by Newton iteration on the nodal temperatures.
    The surface node carries no heat capacity and is an algebraic statement of the surface energy
    balance, which is the CMA convention and avoids having to define the mass of a cell that is
    being consumed.

    Parameters:
    -----------
    material : CharringMaterial | str
        The material, or a name in the ablative response store.
    environment : AblationEnvironment
        Boundary condition schedule and surface closure.
    thickness : float
        Initial thickness of the liner [m].
    duration : float
        Length of the run [s].
    timeStep : float
        Integration step [s].
    numberOfNodes : int
        Nodes through the thickness, surface and back face included.
    growthRatio : float
        Geometric mesh growth away from the surface [-].
    initialTemperature : float
        Uniform starting temperature [K].
    outputInterval : float | None
        Interval at which the state is recorded [s]. Defaults to the timestep.
    maximumIterations : int
        Newton iterations allowed per step.
    temperatureTolerance : float
        Convergence tolerance on the largest nodal temperature change [K].

    Returns:
    --------
    MaterialResponseResult

    Raises:
    -------
    InvalidInputError
        If the geometry, timing or closure request is not usable.
    ConvergenceFailureError
        If the Newton iteration fails to converge on a step.

    '''

    if isinstance(material, str):
        material = CharringMaterial.fromStore(material)

    if thickness <= 0.0 or duration <= 0.0 or timeStep <= 0.0:
        raise InvalidInputError(
            message = 'Thickness, duration and timestep must all be positive.',
            parameterName = 'thickness/duration/timeStep',
            value = (thickness, duration, timeStep),
            validRange = 'all greater than zero')

    if numberOfNodes < 5:
        raise InvalidInputError(
            message = 'A material response needs enough nodes to resolve the char layer, which '
                      'is a fraction of a millimeter deep at first.',
            parameterName = 'numberOfNodes',
            value = numberOfNodes,
            validRange = 'five or more')

    closure = environment.surfaceClosure
    if closure not in ('temperature', 'bPrimeTable', 'diffusionLimited'):
        raise InvalidInputError(
            message = 'Unknown surface closure.',
            parameterName = 'surfaceClosure',
            value = closure,
            validRange = "'temperature', 'bPrimeTable' or 'diffusionLimited'")

    table = environment.bPrimeTable
    if closure == 'bPrimeTable':
        if table is None:
            if not material.surfaceThermochemistry:
                raise InvalidInputError(
                    message = 'The bPrimeTable closure needs a table and the material names none.',
                    parameterName = 'bPrimeTable',
                    value = None,
                    validRange = 'a BPrimeTable instance')
            table = BPrimeTable.fromPackagedTable(material.surfaceThermochemistry)

    if closure == 'diffusionLimited' and not environment.edgeElements:
        raise InvalidInputError(
            message = 'The diffusion-limited closure is an elemental balance and needs the '
                      'elemental composition of the edge gas.',
            parameterName = 'edgeElements',
            value = environment.edgeElements,
            validRange = 'elemental mass fractions, from propellantElementMassFractions')

    # ---- mesh and initial state ----
    position = _gradedNodes(numberOfNodes, growthRatio)          # [-] normalized depth
    spacing = np.diff(position)
    cellWidth = np.empty(numberOfNodes)
    cellWidth[0] = 0.0                                           # the surface node has no volume
    cellWidth[1:-1] = 0.5 * (position[2:] - position[:-2])
    cellWidth[-1] = 0.5 * spacing[-1]

    componentDensity = np.tile(material.componentVirginDensity, (numberOfNodes, 1))
    temperature = np.full(numberOfNodes, float(initialTemperature))
    density = material.bulkDensity(componentDensity)
    currentThickness = float(thickness)
    recession = 0.0

    if closure == 'temperature':
        temperature[0] = environment.sample('surfaceTemperature', 0.0, temperature[0])
    if environment.backFaceCondition == 'temperature':
        temperature[-1] = environment.sample('backFaceTemperature', 0.0, temperature[-1])

    outputInterval = timeStep if outputInterval is None else outputInterval
    steps = int(round(duration / timeStep))
    record = {name: [] for name in (
        'time', 'surfaceTemperature', 'backFaceTemperature', 'recession', 'charMassFlux',
        'pyrolysisGasMassFlux', 'charBPrime', 'gasBPrime', 'blowingReduction', 'charDepth',
        'pyrolysisDepth', 'surfaceHeatFlux')}
    temperatureHistory = []
    densityHistory = []
    nextOutput = 0.0
    worstImbalance = 0.0

    charThreshold = material.charDensity + 0.02 * (material.virginDensity - material.charDensity)
    virginThreshold = material.charDensity + 0.98 * (material.virginDensity - material.charDensity)

    def frontDepth(profile, threshold, thicknessNow, offset):

        '''Depth below the original surface at which the density profile crosses a threshold.'''

        if profile[0] > threshold:
            return offset
        if profile[-1] < threshold:
            return offset + thicknessNow
        index = int(np.argmax(profile >= threshold))
        if index == 0:
            return offset
        lower, upper = profile[index - 1], profile[index]
        weight = 0.0 if upper == lower else (threshold - lower) / (upper - lower)

        return offset + thicknessNow * (position[index - 1] + weight * spacing[index - 1])

    charMassFlux = 0.0
    charBPrime = 0.0
    gasBPrime = 0.0
    blowingReduction = 1.0
    surfaceHeatFlux = 0.0
    gasMassFluxNode = np.zeros(numberOfNodes)

    for step in range(steps + 1):

        time = step * timeStep

        # ---- record ----
        if time + 0.5 * timeStep >= nextOutput or step == steps:
            record['time'].append(time)
            record['surfaceTemperature'].append(temperature[0])
            record['backFaceTemperature'].append(temperature[-1])
            record['recession'].append(recession)
            record['charMassFlux'].append(charMassFlux)
            record['pyrolysisGasMassFlux'].append(gasMassFluxNode[0])
            record['charBPrime'].append(charBPrime)
            record['gasBPrime'].append(gasBPrime)
            record['blowingReduction'].append(blowingReduction)
            record['charDepth'].append(
                frontDepth(density, charThreshold, currentThickness, recession))
            record['pyrolysisDepth'].append(
                frontDepth(density, virginThreshold, currentThickness, recession))
            record['surfaceHeatFlux'].append(surfaceHeatFlux)
            temperatureHistory.append(temperature.copy())
            densityHistory.append(density.copy())
            nextOutput += outputInterval

        if step == steps:
            break

        previousDensity = density.copy()
        previousEnthalpy = material.enthalpy(temperature, density)

        # ---- decomposition over the step, at the temperature entering it ----
        componentDensity = material.advanceDecomposition(
            componentDensity, temperature, timeStep)
        density = material.bulkDensity(componentDensity)
        generationRate = np.maximum((previousDensity - density) / timeStep, 0.0)

        # ---- pyrolysis gas mass flux, integrated up from the impermeable back face ----
        # Faces sit between nodes; face j lies between node j and node j+1. Everything generated
        # below a face must pass through it.
        faceGeneration = 0.5 * (generationRate[:-1] + generationRate[1:]) * spacing \
                         * currentThickness
        faceMassFlux = np.concatenate((np.cumsum(faceGeneration[::-1])[::-1], [0.0]))
        gasMassFluxNode = np.concatenate(([faceMassFlux[0]], faceMassFlux))[:numberOfNodes]

        wallPressure = environment.sample('pressure', time + timeStep, temperature[0])

        # ---- Newton iteration on the nodal temperatures ----
        recessionRate = 0.0
        converged = False
        for iteration in range(maximumIterations):

            conductivity = material.thermalConductivity(temperature, density)
            faceConductivity = 0.5 * (conductivity[:-1] + conductivity[1:])
            enthalpy = material.enthalpy(temperature, density)
            specificHeat = material.specificHeat(temperature, density)

            # Gas enthalpy is carried at the solid temperature: type 1 codes assume the
            # pyrolysis gas leaves in thermal equilibrium with the char it passes through.
            # Interior faces upwind from the deeper node, which is where the gas came from.
            # The surface face is an outflow and takes the surface value, so that the number
            # leaving the last cell and the number entering the surface balance are the same
            # one and the gas carries no energy across the boundary that nothing supplied.
            gasEnthalpy = material.pyrolysisGasEnthalpy(temperature, wallPressure) \
                          if material.decomposes else np.zeros(numberOfNodes)
            faceGasEnthalpy = gasEnthalpy[1:].copy()
            faceGasEnthalpy[0] = gasEnthalpy[0]

            lower = np.zeros(numberOfNodes)
            diagonal = np.zeros(numberOfNodes)
            upper = np.zeros(numberOfNodes)
            residual = np.zeros(numberOfNodes)

            # Interior and back-face cells, assembled as arrays. A face quantity indexed j lies
            # between node j and node j + 1; padding it with a zero at the back face states that
            # the back face is both adiabatic and impermeable, and removes the branch that would
            # otherwise be needed for the last cell.
            scale = currentThickness**2
            volumetricEnthalpy = density * enthalpy
            width = cellWidth[1:]

            faceHeatFlux = np.append(faceConductivity * np.diff(temperature) / spacing, 0.0)
            faceGasFlux = np.append(faceMassFlux[:-1] * faceGasEnthalpy, 0.0)

            storage = (volumetricEnthalpy[1:]
                       - previousDensity[1:] * previousEnthalpy[1:]) / timeStep
            diffusion = (faceHeatFlux[1:] - faceHeatFlux[:-1]) / (scale * width)

            # The gas enthalpy flux divergence. The deeper face carries gas in, the shallower
            # face carries it back out toward the surface, and because more gas passes the
            # shallower face than the deeper one the net is a sink: the cell pays for the
            # enthalpy of the gas it just made.
            gasTerm = (faceGasFlux[1:] - faceGasFlux[:-1]) / (currentThickness * width)

            # Material moving past the mesh. The coefficient vanishes at the back face, which is
            # fixed in the material, and reaches the full recession rate at the surface.
            meshTerm = np.zeros(numberOfNodes - 1)
            if recessionRate != 0.0:
                meshFlux = np.diff(volumetricEnthalpy) / spacing
                meshTerm[:-1] = ((1.0 - position[1:-1]) * recessionRate / currentThickness) \
                                * meshFlux[1:]

            residual[1:] = storage - diffusion - meshTerm - gasTerm

            conductanceDeeper = np.zeros(numberOfNodes - 1)
            conductanceDeeper[:-1] = faceConductivity[1:] / (spacing[1:] * scale * width[:-1])
            conductanceShallower = faceConductivity / (spacing * scale * width)

            diagonal[1:] = density[1:] * specificHeat[1:] / timeStep \
                           + conductanceDeeper + conductanceShallower
            upper[1:] = -conductanceDeeper
            lower[1:] = -conductanceShallower

            # Surface node: either imposed, or an algebraic energy balance with no storage.
            if closure == 'temperature':
                imposed = environment.sample('surfaceTemperature', time + timeStep,
                                             temperature[0])
                residual[0] = temperature[0] - imposed
                diagonal[0] = 1.0
                upper[0] = 0.0
                surfaceHeatFlux = faceConductivity[0] * (temperature[0] - temperature[1]) \
                                  / (spacing[0] * currentThickness)
            else:
                conducted, charMassFlux, charBPrime, gasBPrime, blowingReduction = \
                    _surfaceBalance(material, environment, table, time + timeStep,
                                    temperature[0], gasMassFluxNode[0], density[0])
                conductionAway = faceConductivity[0] * (temperature[0] - temperature[1]) \
                                 / (spacing[0] * currentThickness)
                residual[0] = conductionAway - conducted
                surfaceHeatFlux = conducted

                # Numerical derivative of the balance: the closure is a table lookup and a fixed
                # point, so an analytic derivative is not available and a one-sided difference is.
                delta = 1.0e-3 * max(temperature[0], 1.0)
                perturbed = _surfaceBalance(material, environment, table, time + timeStep,
                                            temperature[0] + delta, gasMassFluxNode[0],
                                            density[0])[0]
                conductance = faceConductivity[0] / (spacing[0] * currentThickness)
                diagonal[0] = conductance - (perturbed - conducted) / delta
                upper[0] = -conductance

            if environment.backFaceCondition == 'temperature':
                imposed = environment.sample('backFaceTemperature', time + timeStep,
                                             temperature[-1])
                residual[-1] = temperature[-1] - imposed
                diagonal[-1] = 1.0
                lower[-1] = 0.0

            banded = np.zeros((3, numberOfNodes))
            banded[0, 1:] = upper[:-1]
            banded[1, :] = diagonal
            banded[2, :-1] = lower[1:]

            correction = solve_banded((1, 1), banded, -residual)
            # A full Newton step can overshoot into a temperature the property curves do not
            # cover on the first pass of a fast transient. Limiting the step costs iterations and
            # buys robustness.
            correction = np.clip(correction, -500.0, 500.0)
            temperature = temperature + correction

            if closure != 'temperature':
                recessionRate = charMassFlux / max(density[0], 1.0e-6)

            if np.max(np.abs(correction)) < temperatureTolerance:
                converged = True
                break

        if not converged:
            raise ConvergenceFailureError(
                message = 'The material response did not converge at t = {:.4f} s. The largest '
                          'temperature correction was still {:.3e} K after {} iterations.'.format(
                              time + timeStep, float(np.max(np.abs(correction))),
                              maximumIterations),
                iterations = maximumIterations,
                residual = float(np.max(np.abs(correction))),
                tolerance = temperatureTolerance)

        # ---- recede ----
        increment = 0.0
        if closure != 'temperature':
            recessionRate = charMassFlux / max(density[0], 1.0e-6)
            increment = recessionRate * timeStep
            if increment >= currentThickness:
                raise ConvergenceFailureError(
                    message = 'The liner was consumed at t = {:.4f} s: recession reached the back '
                              'face. Increase the thickness or shorten the run.'.format(
                                  time + timeStep),
                    iterations = 0,
                    residual = float(increment),
                    tolerance = float(currentThickness))
            recession += increment
            currentThickness -= increment

        # ---- energy closure diagnostic ----
        # Energy held in the material that is still there, before and after the step, against what
        # crossed its two boundaries: heat conducted in at the surface, enthalpy carried out by the
        # pyrolysis gas, and enthalpy carried away by the char that receded. The back face is
        # adiabatic and impermeable, so it contributes nothing.
        heldBefore = np.sum(previousDensity * previousEnthalpy * cellWidth) \
                     * (currentThickness + increment)
        heldAfter = np.sum(density * material.enthalpy(temperature, density) * cellWidth) \
                    * currentThickness
        gasLeaving = gasMassFluxNode[0] * float(
            material.pyrolysisGasEnthalpy(temperature[0], wallPressure)) \
            if material.decomposes and gasMassFluxNode[0] > 0.0 else 0.0
        charLeaving = charMassFlux * float(material.enthalpy(temperature[0], density[0]))
        supplied = surfaceHeatFlux - gasLeaving - charLeaving
        accumulated = (heldAfter - heldBefore) / timeStep

        # Normalized on the largest single term rather than on their sum. The sum passes through
        # zero whenever the energy arriving at the surface balances the energy walking out of it
        # with the char, and a ratio taken there says nothing about the discretisation.
        scale = max(abs(surfaceHeatFlux), abs(gasLeaving), abs(charLeaving), abs(accumulated))
        if scale > 1.0:
            worstImbalance = max(worstImbalance, abs(accumulated - supplied) / scale)

    return MaterialResponseResult(
        time = np.array(record['time']),
        depth = position * currentThickness,
        normalizedPosition = position,
        initialThickness = float(thickness),
        temperature = np.array(temperatureHistory),
        density = np.array(densityHistory),
        surfaceTemperature = np.array(record['surfaceTemperature']),
        backFaceTemperature = np.array(record['backFaceTemperature']),
        recession = np.array(record['recession']),
        charMassFlux = np.array(record['charMassFlux']),
        pyrolysisGasMassFlux = np.array(record['pyrolysisGasMassFlux']),
        charBPrime = np.array(record['charBPrime']),
        gasBPrime = np.array(record['gasBPrime']),
        blowingReduction = np.array(record['blowingReduction']),
        charDepth = np.array(record['charDepth']),
        pyrolysisDepth = np.array(record['pyrolysisDepth']),
        surfaceHeatFlux = np.array(record['surfaceHeatFlux']),
        energyImbalance = float(worstImbalance),
        tableClamps = int(table.clampedRequests) if table is not None else 0,
        material = material.name)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Nozzle Application -- #
#--------------------------------------------------------------------------------------------------------------------------#

@dataclass
class AblativeLinerResult:

    '''

    An ablative liner solved at every station along a nozzle.

    Attributes:
    -----------
    axialPosition : numpy.ndarray
        Station axial coordinates [m].
    radius : numpy.ndarray
        Initial wall radius at each station [m].
    recession : numpy.ndarray
        Recession at the end of the firing [m].
    finalRadius : numpy.ndarray
        Wall radius at the end of the firing [m].
    surfaceTemperature : numpy.ndarray
        Final surface temperature at each station [K].
    backFaceTemperature : numpy.ndarray
        Final back face temperature at each station [K].
    charDepth : numpy.ndarray
        Final char depth below the original surface at each station [m].
    heatTransferCoefficient : numpy.ndarray
        Unblown gas-side coefficient at the final wall temperature [W/m^2 K].
    throatRecession : float
        Recession at the minimum-radius station [m].
    throatAreaRatio : float
        Final throat area divided by initial throat area [-].
    stations : list
        The MaterialResponseResult for each station, in order.
    charBPrime : numpy.ndarray
        Final char blowing rate at each station [-].

    '''

    axialPosition:           np.ndarray
    radius:                  np.ndarray
    recession:               np.ndarray
    finalRadius:             np.ndarray
    surfaceTemperature:      np.ndarray
    backFaceTemperature:     np.ndarray
    charDepth:               np.ndarray
    heatTransferCoefficient: np.ndarray
    throatRecession:         float
    throatAreaRatio:         float
    stations:                list
    charBPrime:              np.ndarray

def ablativeNozzleLiner(material, axialPosition, radius, machNumber, staticTemperature,
                        edgeElements: dict, chamberPressure: float, chamberTemperature: float,
                        characteristicVelocity: float, exhaustGamma: float,
                        exhaustGasConstant: float, exhaustMolecularWeight: float,
                        throatRadiusOfCurvature: float, burnTime: float,
                        linerThickness: float, initialTemperature: float = 300.0,
                        timeStep: float = 0.05, numberOfNodes: int = 81,
                        surfaceHeatOfAblation: float = 0.0,
                        charRemovalEfficiency: float = 1.0,
                        viewFactor: float = 0.6,
                        backFaceCondition: str = 'adiabatic',
                        oxidationProduct: str = 'CO') -> AblativeLinerResult:

    '''

    Recession and thermal response of an ablative liner along a nozzle contour.

    Each station is solved as an independent one-dimensional problem. That is the standard
    engineering treatment and it is right where the liner is thin against the local radius and the
    axial gradients are gentle, which holds everywhere in a nozzle except across the throat, where
    the flux changes by a factor of several over a few liner thicknesses. Axial conduction is not
    modeled, so the throat runs slightly hot and slightly deep against a two-dimensional solve.

    The gas-side coefficient is Bartz, taken from the regenerative cooling model so that an
    ablative and a regeneratively cooled version of the same contour are driven by the same
    correlation. It is converted to a mass transfer coefficient by dividing through the exhaust
    specific heat, which is the Lewis number one assumption the whole transfer-coefficient
    formulation already rests on.

    Char removal uses the diffusion-limited closure, so the answer depends on the exhaust only
    through its elemental carbon and oxygen. That is deliberate: the packaged equilibrium table
    stops at one atmosphere and is for air, and neither restriction applies to an elemental
    balance. It is also an upper bound on oxidation-driven recession, since it assumes surface
    kinetics are infinitely fast. Below about 2000 K of wall temperature they are not, and the
    real rate falls away from this one.

    Parameters:
    -----------
    material : CharringMaterial | str
        The liner material, or a name in the ablative response store.
    axialPosition : array_like
        Station axial coordinates [m].
    radius : array_like
        Wall radius at each station [m].
    machNumber : array_like
        Local Mach number at each station [-].
    staticTemperature : array_like
        Local static gas temperature at each station [K].
    edgeElements : dict
        Elemental mass fractions of the exhaust, from `propellantElementMassFractions`.
    chamberPressure : float
        Chamber stagnation pressure [Pa].
    chamberTemperature : float
        Chamber stagnation temperature [K].
    characteristicVelocity : float
        Characteristic velocity [m/s].
    exhaustGamma : float
        Ratio of specific heats [-].
    exhaustGasConstant : float
        Specific gas constant of the exhaust [J/kg-K].
    exhaustMolecularWeight : float
        Exhaust molecular weight [kg/kmol].
    throatRadiusOfCurvature : float
        Wall radius of curvature at the throat [m].
    burnTime : float
        Firing duration [s].
    linerThickness : float
        Initial liner thickness [m].
    initialTemperature : float
        Liner temperature at ignition [K].
    timeStep : float
        Integration step [s].
    numberOfNodes : int
        Nodes through the liner.
    surfaceHeatOfAblation : float
        Energy absorbed per unit mass of char removed [J/kg]. See the module validation note:
        the default of zero is not the physical value.
    charRemovalEfficiency : float
        Multiplier on the transport-limited char removal rate [-]. One returns the bound. A
        value fitted to measured recession makes the result a calibrated estimate rather than a
        bound, and it is then valid only over the conditions of that fit.
    viewFactor : float
        Re-radiation view factor [-]. Inside a nozzle the surface sees mostly itself, so this is
        well below one.
    backFaceCondition : str
        'adiabatic' or 'temperature'.
    oxidationProduct : str
        'CO' or 'CO2' branch of the diffusion-limited closure.

    Returns:
    --------
    AblativeLinerResult

    Raises:
    -------
    InvalidInputError
        If the station arrays disagree in length or the contour has no throat.

    '''

    from .regenThermal import bartzHeatTransferCoefficient

    axialPosition = np.asarray(axialPosition, dtype = float)
    radius = np.asarray(radius, dtype = float)
    machNumber = np.asarray(machNumber, dtype = float)
    staticTemperature = np.asarray(staticTemperature, dtype = float)

    if not (axialPosition.size == radius.size == machNumber.size == staticTemperature.size):
        raise InvalidInputError(
            message = 'Every station array must describe the same stations.',
            parameterName = 'axialPosition/radius/machNumber/staticTemperature',
            value = (axialPosition.size, radius.size, machNumber.size, staticTemperature.size),
            validRange = 'four arrays of equal length')

    if axialPosition.size < 2:
        raise InvalidInputError(
            message = 'A liner needs more than one station to describe a contour.',
            parameterName = 'axialPosition',
            value = axialPosition.size,
            validRange = 'two or more')

    if isinstance(material, str):
        material = CharringMaterial.fromStore(material)

    throatIndex = int(np.argmin(radius))
    throatRadius = radius[throatIndex]
    throatArea = np.pi * throatRadius**2
    throatDiameter = 2.0 * throatRadius
    localArea = np.pi * radius**2

    # Stagnation specific heat of the exhaust, the same expression Bartz itself uses, so the mass
    # transfer coefficient and the heat transfer coefficient stay consistent with each other.
    specificHeat = (exhaustGamma / (exhaustGamma - 1.0)) * exhaustGasConstant

    # Recovery temperature with the turbulent recovery factor. The Prandtl number is Bartz's own
    # stagnation expression rather than a separate correlation.
    prandtl = 4.0 * exhaustGamma / (9.0 * exhaustGamma - 5.0)
    recoveryFactor = prandtl**(1.0 / 3.0)
    recoveryTemperature = staticTemperature * (
        1.0 + recoveryFactor * 0.5 * (exhaustGamma - 1.0) * machNumber**2)

    staticPressure = chamberPressure * (
        1.0 + 0.5 * (exhaustGamma - 1.0) * machNumber**2)**(-exhaustGamma / (exhaustGamma - 1.0))

    results = []
    coefficients = []
    for index in range(axialPosition.size):

        def transferCoefficient(time, wallTemperature, index = index):

            '''Bartz coefficient at this station, divided through the exhaust specific heat.'''

            wall = chamberTemperature * 0.6 if wallTemperature is None else wallTemperature
            coefficient = bartzHeatTransferCoefficient(
                nearWallTemperature = staticTemperature[index],
                nearWallMachNumber = machNumber[index],
                exhaustGamma = exhaustGamma,
                exhaustGasConstant = exhaustGasConstant,
                exhaustMolecularWeight = exhaustMolecularWeight,
                hotWallTemperature = wall,
                chamberPressure = chamberPressure,
                characteristicVelocity = characteristicVelocity,
                throatDiameter = throatDiameter,
                throatRadiusOfCurvature = throatRadiusOfCurvature,
                throatArea = throatArea,
                localArea = localArea[index])

            return coefficient / specificHeat

        environment = AblationEnvironment(
            surfaceClosure = 'diffusionLimited',
            transferCoefficient = transferCoefficient,
            recoveryTemperature = float(recoveryTemperature[index]),
            edgeSpecificHeat = specificHeat,
            pressure = float(staticPressure[index]),
            ambientTemperature = float(initialTemperature),
            viewFactor = viewFactor,
            edgeElements = edgeElements,
            oxidationProduct = oxidationProduct,
            charRemovalEfficiency = charRemovalEfficiency,
            surfaceHeatOfAblation = surfaceHeatOfAblation,
            backFaceCondition = backFaceCondition,
            backFaceTemperature = float(initialTemperature))

        results.append(solveMaterialResponse(
            material, environment, linerThickness, burnTime,
            timeStep = timeStep, numberOfNodes = numberOfNodes,
            initialTemperature = initialTemperature,
            outputInterval = max(burnTime / 20.0, timeStep)))

        coefficients.append(transferCoefficient(burnTime, results[-1].surfaceTemperature[-1])
                            * specificHeat)

    recession = np.array([result.recession[-1] for result in results])
    finalRadius = radius + recession

    return AblativeLinerResult(
        axialPosition = axialPosition,
        radius = radius,
        recession = recession,
        finalRadius = finalRadius,
        surfaceTemperature = np.array([r.surfaceTemperature[-1] for r in results]),
        backFaceTemperature = np.array([r.backFaceTemperature[-1] for r in results]),
        charDepth = np.array([r.charDepth[-1] for r in results]),
        heatTransferCoefficient = np.array(coefficients, dtype = float),
        throatRecession = float(recession[throatIndex]),
        throatAreaRatio = float((finalRadius[throatIndex] / throatRadius)**2),
        stations = results,
        charBPrime = np.array([r.charBPrime[-1] for r in results]))
