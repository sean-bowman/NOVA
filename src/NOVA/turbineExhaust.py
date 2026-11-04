# -- NOVA: Gas Generator and Turbine Exhaust -- #

'''

The state of a gas generator's turbine exhaust, for use as a film coolant on a nozzle extension.

A gas generator cycle burns a small fuel-rich flow to drive its turbines and then has to put the
exhaust somewhere. Ducted into the nozzle extension and injected along the wall through a slot,
the same gas becomes a film: the F-1 fed its turbine exhaust between a shingled inner wall and a
continuous outer wall of the extension, the J-2X injected it through a manifold at the extension
joint, and the Vulcain 2 re-injects about 10 kg/s of it into the lower nozzle. The film's job is to
keep the extension wall at the turbine exhaust temperature, roughly 600 to 1000 K, rather than at
the core gas recovery temperature of 3000 K and more.

The gas generator is specified rather than solved: its mixture ratio, pressure and flow, and the
turbine's pressure ratio and efficiency, are inputs. No power balance with the pumps is carried.

**Method.**

1. The gas generator is an equilibrium CEA combustion at its pressure and mixture ratio. Its
   chamber state is the turbine inlet.
2. The composition is frozen there. A fuel-rich gas leaves the generator in a few milliseconds,
   so its species do not shift as it expands through the turbine.
3. The ideal expansion through the turbine's pressure ratio is CEA's frozen isentropic expansion
   to p_gg/PR, which gives the isentropic enthalpy h_is.
4. The turbine extracts a fraction of the ideal work, h_te = h_gg - eta_t (h_gg - h_is).
5. With the composition frozen, the gas is an ideal mixture whose enthalpy, specific heat,
   conductivity and viscosity depend on temperature alone. The exhaust therefore has the
   temperature and properties of the point on the same frozen expansion whose enthalpy is h_te;
   it is found by a root find on CEA's frozen exit enthalpy over the pressure ratio. Its density is
   p/(R T) at the real exhaust pressure p_gg/PR.

Where h_te lies above the frozen throat enthalpy, which happens only for a poor turbine on a low
pressure ratio, the matching point is in the subsonic part of the expansion, which CEA's rocket
problem does not report. There the temperature and properties are interpolated linearly in
enthalpy between the chamber and the throat. Over that span the frozen specific heat changes by a
few percent, so the interpolation is close; `propertySource` records which path was taken.

**Condensed carbon.** At the mixture ratios a hydrocarbon gas generator runs, CEA's equilibrium
forms graphite and methane: 35 percent graphite by mass for LOX/RP-1 at 0.416, 11 percent for
LOX/CH4 at 0.3. A real gas generator holds its gas for milliseconds and forms soot and heavy
hydrocarbons instead, far from that equilibrium. The condensed species and their mass fractions
are reported on the state so the result is not mistaken for a clean gas.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**CEA is the validated part.** The combustion and the frozen expansion are CEA's, validated in
tests/testCeaInterface.py against NASA CEA output. What this module adds is the frozen-composition
reading of a non-ideal turbine and the interpolation above the throat, and both are held to
identities in tests/testTurbineExhaust.py: a turbine efficiency of one reproduces CEA's frozen exit
state at the pressure ratio exactly, the turbine work equals the efficiency times the ideal work to
round-off, and the interpolated branch meets the CEA branch at the throat.

**Against hardware: one partial comparison, unfavorable for hydrocarbons.** The F-1 gas generator
burned 49 lb/s of LOX with 118 lb/s of RP-1, a mixture ratio of 0.416, at about 1453 F (1063 K)
[heroicrelics.org, F-1 gas generator]. Its pressure is not sourced. CEA at 6.65 MPa gives 1252 K,
17.8 percent high, and the temperature is insensitive to the pressure over the plausible range.
The excess is the heat of forming graphite and methane, which the real gas generator did not
form. **Fuel-rich hydrocarbon gas generator states are unvalidated and run hot.** Hydrogen-oxygen
gas generators form only water and hydrogen and are not subject to that error; no published
hydrogen gas generator gives mixture ratio, pressure and temperature together (the J-2's AEDC
altitude tests report outlet temperatures of 1180 to 1590 F without a mixture ratio), so they too
are unvalidated against hardware. What would close the gap is a gas generator test with all three
recorded, or a kinetically limited composition for the hydrocarbon case.

All units are mass base SI:
    - Pressure [Pa]
    - Temperature [K]
    - Enthalpy [J/kg]
    - Mass flow [kg/s]
    - Power [W]

Author: Sean Bowman

'''

import re
import warnings
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

from .ceaInterface import CEA
from .errors import ConvergenceFailureError, InvalidInputError, createErrorContext
from .filmCooling import FilmCoolantState

__all__ = ['TurbineExhaustState', 'turbineExhaustState', 'condensedSpecies']

# CEA's universal gas constant, per kilomole [J/kmol-K]
UNIVERSALGASCONSTANT = 8314.462618

# CEA marks a condensed phase with its phase in parentheses: C(gr), H2O(L), Al2O3(a)
CONDENSEDPHASE = re.compile(r'\((?:gr|cr|L|l|s|a|b|c|I|II|III)\)$')

@dataclass
class TurbineExhaustState:

    '''

    A gas generator's turbine inlet and exhaust, and the turbine between them.

    Attributes:
    -----------
    fuel, oxidizer : str
        Propellant names as CEA was given them.
    mixtureRatio : float
        Gas generator oxidizer over fuel [-].
    gasGeneratorPressure : float
        Gas generator chamber pressure, the turbine inlet [Pa].
    pressureRatio : float
        Turbine inlet over exhaust pressure [-].
    efficiency : float
        Turbine total-to-static efficiency, actual over isentropic enthalpy drop [-].
    massFlow : float
        Turbine exhaust flow [kg/s].
    gasGeneratorTemperature, gasGeneratorEnthalpy : float
        Turbine inlet state [K], [J/kg].
    isentropicTemperature, isentropicEnthalpy : float
        End of the ideal frozen expansion through the pressure ratio [K], [J/kg].
    pressure : float
        Exhaust static pressure, p_gg/PR [Pa].
    temperature, enthalpy : float
        Exhaust state [K], [J/kg].
    specificHeat, thermalConductivity, viscosity : float
        Frozen exhaust properties [J/kg-K], [W/m-K], [Pa s].
    molecularWeight, gamma : float
        Frozen exhaust molecular weight [kg/kmol] and specific heat ratio [-].
    density : float
        p/(R T) at the exhaust pressure [kg/m^3].
    propertySource : str
        'frozenExpansion' where the exhaust lies on CEA's supersonic frozen expansion,
        'chamberThroatInterpolation' where it lies above the throat enthalpy.
    condensedSpecies : dict
        Condensed species at the turbine inlet and their mass fractions [-].

    '''

    fuel:                    str
    oxidizer:                str
    mixtureRatio:            float
    gasGeneratorPressure:    float
    pressureRatio:           float
    efficiency:              float
    massFlow:                float
    gasGeneratorTemperature: float
    gasGeneratorEnthalpy:    float
    isentropicTemperature:   float
    isentropicEnthalpy:      float
    pressure:                float
    temperature:             float
    enthalpy:                float
    specificHeat:            float
    thermalConductivity:     float
    viscosity:               float
    molecularWeight:         float
    gamma:                   float
    density:                 float
    propertySource:          str
    condensedSpecies:        dict = field(default_factory = dict)

    @property
    def gasConstant(self) -> float:

        '''Specific gas constant [J/kg-K].'''

        return UNIVERSALGASCONSTANT / self.molecularWeight

    @property
    def thermalDiffusivity(self) -> float:

        '''Thermal diffusivity at the exhaust pressure [m^2/s].'''

        return self.thermalConductivity / (self.density * self.specificHeat)

    @property
    def turbineSpecificWork(self) -> float:

        '''Enthalpy the turbine extracts per kilogram [J/kg].'''

        return self.gasGeneratorEnthalpy - self.enthalpy

    @property
    def turbinePower(self) -> float:

        '''Shaft power of the turbine [W].'''

        return self.massFlow * self.turbineSpecificWork

    @property
    def condensedMassFraction(self) -> float:

        '''Total condensed mass fraction at the turbine inlet [-].'''

        return float(sum(self.condensedSpecies.values()))

    def filmState(self, slotPressure: float, slotHeight: float, slotRadius: float,
                  massFlow: float = None) -> FilmCoolantState:

        '''

        The exhaust as a film coolant leaving an annular slot.

        The gas leaves the slot at the local wall static pressure, so its density is taken there
        rather than at the turbine exit. The transport properties do not depend on pressure.

        Parameters:
        -----------
        slotPressure : float
            Wall static pressure at the slot [Pa].
        slotHeight, slotRadius : float
            Radial height of the slot and wall radius there [m].
        massFlow : float | None
            Flow through this slot [kg/s], the whole exhaust when unset.

        Returns:
        --------
        FilmCoolantState

        '''

        flow = self.massFlow if massFlow is None else float(massFlow)
        if slotHeight <= 0.0 or slotRadius <= 0.0 or flow <= 0.0 or slotPressure <= 0.0:
            raise InvalidInputError(
                message = 'A turbine exhaust slot needs a height, a radius, a flow and a static '
                          'pressure to leave into.',
                parameterName = 'slotHeight/slotRadius/massFlow/slotPressure',
                value = (slotHeight, slotRadius, flow, slotPressure),
                validRange = 'all greater than zero')

        density = slotPressure / (self.gasConstant * self.temperature)
        slotArea = 2.0 * np.pi * slotRadius * slotHeight
        return FilmCoolantState(
            density             = density,
            specificHeat        = self.specificHeat,
            thermalConductivity = self.thermalConductivity,
            viscosity           = self.viscosity,
            thermalDiffusivity  = self.thermalConductivity / (density * self.specificHeat),
            velocity            = flow / (density * slotArea),
            slotArea            = slotArea)

    def report(self) -> str:

        '''A short text summary of the gas generator, the turbine and the exhaust.'''

        lines = [
            f'Gas generator {self.fuel}/{self.oxidizer} at a mixture ratio of {self.mixtureRatio:.3g}, '
            f'{1e-6 * self.gasGeneratorPressure:.2f} MPa: {self.gasGeneratorTemperature:.0f} K',
            f'  turbine pressure ratio {self.pressureRatio:.3g}, efficiency {self.efficiency:.2f}: '
            f'{1e-3 * self.turbineSpecificWork:.0f} kJ/kg, {1e-6 * self.turbinePower:.2f} MW at '
            f'{self.massFlow:.3g} kg/s',
            f'  exhaust {self.temperature:.0f} K at {1e-3 * self.pressure:.0f} kPa (isentropic '
            f'{self.isentropicTemperature:.0f} K), molecular weight {self.molecularWeight:.2f}, '
            f'gamma {self.gamma:.3f}, cp {self.specificHeat:.0f} J/kg-K']
        if self.condensedSpecies:
            listed = ', '.join(f'{name} {100.0 * fraction:.1f} %'
                               for name, fraction in sorted(self.condensedSpecies.items(),
                                                            key = lambda item: -item[1]))
            lines.append(f'  condensed at equilibrium: {listed} by mass. A real gas generator does '
                         f'not reach this equilibrium; its temperature is overstated.')
        return '\n'.join(lines)

def condensedSpecies(massFractions: dict, station: str = 'chamber', floor: float = 1.0e-4) -> dict:

    '''

    Condensed species and their mass fractions at one CEA station.

    Parameters:
    -----------
    massFractions : dict
        CEA's species mass fractions, keyed by species and then by station.
    station : str
        'injector', 'chamber', 'throat' or 'exit'.
    floor : float
        Smallest mass fraction reported [-].

    Returns:
    --------
    dict
        {species: mass fraction}.

    '''

    found = {}
    for name, stations in massFractions.items():
        value = (stations or {}).get(station)
        if value is not None and CONDENSEDPHASE.search(name) and float(value) >= floor:
            found[name] = float(value)
    return found

def _frozenCase(fuel: str, oxidizer: str, mixtureRatio: float, pressure: float,
                pressureRatio: float, oxidizerInitialTemperature) -> dict:

    '''One frozen CEA expansion to a pressure ratio, with every result group read.'''

    with warnings.catch_warnings():
        # A fuel-rich case with condensed carbon draws CEA warnings that say nothing the
        # condensed species report does not; the NaN check below catches a failed solve
        warnings.simplefilter('ignore')
        case = CEA(fuel, oxidizer, chamberPressure = pressure, OFRatio = mixtureRatio,
                   pressureRatio = pressureRatio, frozen = True,
                   oxidizerInitialTemperature = oxidizerInitialTemperature)
        results = {key: case.ceaResults[key] for key in (
            'combustionChamberTemperature', 'combustionChamberEnthalpy',
            'combustionChamberHeatCapacity', 'combustionChamberThermalConductivity',
            'combustionChamberViscosity', 'combustionChamberMolecularWeight',
            'combustionChamberGamma', 'throatTemperature', 'throatEnthalpy', 'throatPressure',
            'throatHeatCapacity', 'throatThermalConductivity', 'throatViscosity', 'throatGamma',
            'exitTemperature', 'exitEnthalpy', 'exitPressure', 'exitHeatCapacity',
            'exitThermalConductivity', 'exitViscosity', 'exitMolecularWeight', 'exitGamma',
            'massFractions')}

    unusable = [key for key, value in results.items()
                if key != 'massFractions' and not np.isfinite(float(value))]
    if unusable:
        raise ConvergenceFailureError(
            message = (f'CEA returned no usable state for {fuel}/{oxidizer} at a mixture ratio of '
                       f'{mixtureRatio:.3g} and {1e-6 * pressure:.2f} MPa through a pressure ratio '
                       f'of {pressureRatio:.4g}: {", ".join(unusable)} not finite. CEA warns rather '
                       f'than failing; a mixture ratio far outside the propellants\' combustion '
                       f'range is the usual cause.'),
            context = createErrorContext(fuel = fuel, oxidizer = oxidizer,
                                         mixtureRatio = mixtureRatio, pressure = pressure,
                                         pressureRatio = pressureRatio))

    # CEA's frozen expansion of a gas carrying much graphite can fail to find the area ratio and
    # hand back the throat state without a warning: LOX/CH4 at a mixture ratio of 0.25 and below
    # does. The exit pressure says whether the expansion reached the ratio asked for. Within ten
    # percent of the throat pressure it is not asked: CEA resolves no area ratio closer to one
    # than 1 + 1e-6, which alone moves the exit pressure there by a few percent.
    requested = pressure / pressureRatio
    farFromThroat = requested < 0.9 * float(results['throatPressure'])
    if farFromThroat and abs(float(results['exitPressure']) / requested - 1.0) > 0.01:
        raise ConvergenceFailureError(
            message = (f'CEA\'s frozen expansion of the {fuel}/{oxidizer} gas generator gas at a '
                       f'mixture ratio of {mixtureRatio:.3g} did not reach a pressure ratio of '
                       f'{pressureRatio:.4g}: it returned {1e-3 * float(results["exitPressure"]):.0f} kPa '
                       f'against {1e-3 * requested:.0f} kPa. CEA fails this way on gases carrying '
                       f'much condensed carbon; a richer-in-oxidizer gas generator avoids it.'),
            context = createErrorContext(fuel = fuel, oxidizer = oxidizer,
                                         mixtureRatio = mixtureRatio, pressure = pressure,
                                         pressureRatio = pressureRatio))
    return results

def turbineExhaustState(fuel: str, oxidizer: str, mixtureRatio: float,
                        gasGeneratorPressure: float, pressureRatio: float,
                        efficiency: float, massFlow: float,
                        oxidizerInitialTemperature: float = None) -> TurbineExhaustState:

    '''

    The turbine exhaust of a specified gas generator and turbine.

    Parameters:
    -----------
    fuel, oxidizer : str
        Propellant names, as `ceaInterface.CEA` takes them.
    mixtureRatio : float
        Gas generator oxidizer over fuel [-].
    gasGeneratorPressure : float
        Gas generator chamber pressure [Pa].
    pressureRatio : float
        Turbine inlet over exhaust static pressure [-]. At least the sonic ratio of the gas.
    efficiency : float
        Turbine efficiency, actual over isentropic enthalpy drop, in (0, 1] [-].
    massFlow : float
        Exhaust flow [kg/s].
    oxidizerInitialTemperature : float | None
        Oxidizer temperature at the gas generator injector [K]; CEA's default card when unset.

    Returns:
    --------
    TurbineExhaustState

    Raises:
    -------
    InvalidInputError
        If an input is outside its range, or the pressure ratio is below the sonic ratio.
    ConvergenceFailureError
        If CEA returns a non-finite state, or the exhaust enthalpy cannot be bracketed.

    '''

    for name, value, valid in (('gasGeneratorMixtureRatio', mixtureRatio, mixtureRatio > 0.0),
                               ('gasGeneratorPressure', gasGeneratorPressure, gasGeneratorPressure > 0.0),
                               ('turbinePressureRatio', pressureRatio, pressureRatio > 1.0),
                               ('turbineEfficiency', efficiency, 0.0 < efficiency <= 1.0),
                               ('turbineExhaustMassFlow', massFlow, massFlow > 0.0)):
        if not (np.isfinite(value) and valid):
            raise InvalidInputError(
                message = 'A gas generator and turbine need a positive mixture ratio, pressure '
                          'and flow, a pressure ratio above one and an efficiency between zero '
                          'and one.',
                parameterName = name, value = value,
                validRange = {'turbinePressureRatio': 'above 1',
                              'turbineEfficiency': '(0, 1]'}.get(name, 'above 0'))

    ideal = _frozenCase(fuel, oxidizer, mixtureRatio, gasGeneratorPressure, pressureRatio,
                        oxidizerInitialTemperature)
    sonicRatio = gasGeneratorPressure / float(ideal['throatPressure'])
    if pressureRatio < sonicRatio:
        raise InvalidInputError(
            message = (f'A turbine pressure ratio of {pressureRatio:.3g} is below the sonic ratio of '
                       f'this gas, {sonicRatio:.3g}, and CEA\'s rocket expansion reports no state '
                       f'there. Gas generator turbines run pressure ratios of 5 to 30.'),
            parameterName = 'turbinePressureRatio', value = pressureRatio,
            validRange = f'at least {sonicRatio:.3g}')

    inletEnthalpy = float(ideal['combustionChamberEnthalpy'])
    isentropicEnthalpy = float(ideal['exitEnthalpy'])
    exhaustEnthalpy = inletEnthalpy - efficiency * (inletEnthalpy - isentropicEnthalpy)
    throatEnthalpy = float(ideal['throatEnthalpy'])

    properties = ('Temperature', 'HeatCapacity', 'ThermalConductivity', 'Viscosity', 'Gamma')

    def interpolated(upper: tuple, lower: tuple) -> dict:

        '''Properties linear in enthalpy between two (enthalpy, results, station prefix) points.'''

        weight = (upper[0] - exhaustEnthalpy) / (upper[0] - lower[0])
        return {name: (1.0 - weight) * float(upper[1][upper[2] + name])
                      + weight * float(lower[1][lower[2] + name]) for name in properties}

    chamberPoint = (inletEnthalpy, ideal, 'combustionChamber')
    throatPoint = (throatEnthalpy, ideal, 'throat')

    if efficiency == 1.0:
        exhaust = {name: float(ideal['exit' + name]) for name in properties}
        source = 'frozenExpansion'
    elif exhaustEnthalpy > throatEnthalpy:
        # Subsonic: between the chamber and the throat, which CEA's rocket problem does not report
        exhaust = interpolated(chamberPoint, throatPoint)
        source = 'chamberThroatInterpolation'
    else:
        # CEA resolves no area ratio closer to one than 1 + 1e-6, so the first supersonic state it
        # reports sits a little below the throat enthalpy. An exhaust in that sliver is interpolated
        # from the throat; below it, the root find runs on the frozen expansion.
        firstRatio = sonicRatio * (1.0 + 1.0e-6)
        first = _frozenCase(fuel, oxidizer, mixtureRatio, gasGeneratorPressure, firstRatio,
                            oxidizerInitialTemperature)
        if float(first['exitEnthalpy']) < exhaustEnthalpy:
            exhaust = interpolated(throatPoint, (float(first['exitEnthalpy']), first, 'exit'))
            source = 'chamberThroatInterpolation'
        else:
            def residual(ratio: float) -> float:
                return float(_frozenCase(fuel, oxidizer, mixtureRatio, gasGeneratorPressure, ratio,
                                         oxidizerInitialTemperature)['exitEnthalpy']) - exhaustEnthalpy
            try:
                matched = brentq(residual, firstRatio, pressureRatio, xtol = 1.0e-10, rtol = 1.0e-12)
            except ValueError as error:
                raise ConvergenceFailureError(
                    message = (f'The exhaust enthalpy {exhaustEnthalpy:.6g} J/kg could not be '
                               f'bracketed on the frozen expansion between the pressure ratios '
                               f'{firstRatio:.4g} and {pressureRatio:.4g}.'),
                    context = createErrorContext(efficiency = efficiency,
                                                 pressureRatio = pressureRatio)) from error
            state = _frozenCase(fuel, oxidizer, mixtureRatio, gasGeneratorPressure, matched,
                                oxidizerInitialTemperature)
            exhaust = {name: float(state['exit' + name]) for name in properties}
            source = 'frozenExpansion'

    temperature = exhaust['Temperature']
    specificHeat = exhaust['HeatCapacity']
    conductivity = exhaust['ThermalConductivity']
    viscosity = exhaust['Viscosity']
    gamma = exhaust['Gamma']

    # Frozen composition: one molecular weight from the turbine inlet to the exhaust
    molecularWeight = float(ideal['combustionChamberMolecularWeight'])
    exhaustPressure = gasGeneratorPressure / pressureRatio
    density = exhaustPressure * molecularWeight / (UNIVERSALGASCONSTANT * temperature)

    return TurbineExhaustState(
        fuel                    = fuel,
        oxidizer                = oxidizer,
        mixtureRatio            = float(mixtureRatio),
        gasGeneratorPressure    = float(gasGeneratorPressure),
        pressureRatio           = float(pressureRatio),
        efficiency              = float(efficiency),
        massFlow                = float(massFlow),
        gasGeneratorTemperature = float(ideal['combustionChamberTemperature']),
        gasGeneratorEnthalpy    = inletEnthalpy,
        isentropicTemperature   = float(ideal['exitTemperature']),
        isentropicEnthalpy      = isentropicEnthalpy,
        pressure                = exhaustPressure,
        temperature             = temperature,
        enthalpy                = exhaustEnthalpy,
        specificHeat            = specificHeat,
        thermalConductivity     = conductivity,
        viscosity               = viscosity,
        molecularWeight         = molecularWeight,
        gamma                   = gamma,
        density                 = density,
        propertySource          = source,
        condensedSpecies        = condensedSpecies(ideal['massFractions']))
