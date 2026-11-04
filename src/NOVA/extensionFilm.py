# -- NOVA: Film Cooling of the Nozzle Extension -- #

'''

The wall temperature that drives an uncooled extension, with the films that run over it.

An extension beyond the jacket survives by radiating, and on a high-pressure engine it cannot
radiate enough: the recovery temperature of the core gas is 3000 K and more, and Bartz scales with
chamber pressure to the 0.8. A film laid along the wall drives the wall with its own adiabatic
temperature instead. Three sources feed one in service:

- **The chamber film**, drawn by the injector, which persists past the jacket joint and decays
  along the bell.
- **Turbine exhaust**, from a gas generator cycle (F-1, J-2X, Vulcain 2), at 600 to 1000 K.
- **Dumped coolant**, a coolant circuit's outlet injected rather than returned (Vulcain 2 dumps
  its upper-nozzle hydrogen into the lower nozzle).

**Method.** The jacket and extension station arrays are joined into one wall, so each film is
marched from its own slot over real stations with the real throat. Each film is solved alone, by
the closure the chamber film uses (Hatch and Papell, or SP-8124's entrainment model), and its
effectiveness is read off its own drive against the recovery temperature,

    eta_n = (T_r - T_aw,n) / (T_r - T_c,n)

The films are then stacked in the order the gas meets them by Sellers' superposition: each sees
the wall the films upstream of it have already made, in place of the recovery temperature,

    T_aw,n = T_aw,n-1 - eta_n (T_aw,n-1 - T_c,n),   T_aw,0 = T_r

With one film this returns that film's drive; with none it returns the recovery temperature to the
bit. The configured closure drives the extension; the other closure is solved beside it and
reported, because the two disagree by hundreds of kelvin on an extension and neither is validated
there.

**Thrust.** A slot film is a flow that leaves the engine without passing through the chamber, so
it is an extra draw on the tanks, and it produces thrust of its own. Two bounds are reported. Kept
apart from the core, the film expands from its slot total state to the exit static pressure,
which gives the lower estimate m_f u_e,f. Mixed into the core at injection, the mixture shares the
core's expansion, and with the exit velocity scaling as the square root of the total enthalpy the
film adds (m_c + m_f) u_mix - m_c u_c. The truth lies between: a film stays attached and largely
unmixed over its survival length, which is why it cools at all.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Unvalidated on an extension.** Neither closure is validated at rocket conditions (filmCooling.py
states their own status), and no source available here gives a measured extension wall temperature
under a turbine exhaust or dumped hydrogen film with the inputs these closures need. The DLR
supersonic hydrogen film data, which would close this for a dumped hydrogen film, could not be
retrieved. What is held, in tests/testExtensionFilm.py, are the identities the method rests on:
no film returns the recovery temperature exactly, one film returns its own drive, two films with
constant effectiveness return the closed-form superposition, the chamber film re-marched over the
joined wall reproduces the jacket section's film on every jacket station, and the film expansion
velocity reproduces the isentropic closed form.

All units are mass base SI:
    - Length [m]
    - Pressure [Pa]
    - Temperature [K]
    - Mass flow [kg/s]
    - Velocity [m/s]
    - Force [N]

Author: Sean Bowman

'''

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .errors import InvalidInputError
from .filmCooling import (SP8124INJECTIONBAND, FilmCoolantState, FilmCoolingResult,
                          entrainmentFilmArrays, filmCoolantState, filmCoolingArrays)
from .geometryTools import sizedThroatRadius
from .validation import specified

__all__ = ['ExtensionFilmState', 'ExtensionFilmSlot', 'FilmLayer', 'ExtensionFilmResult',
           'FILMSOURCES', 'FILMCLOSURES', 'readFilmSlots', 'joinedWall', 'superposeFilms',
           'filmExpansionVelocity', 'mixedFilmThrust', 'solveExtensionFilm']

FILMSOURCES = ('species', 'turbineExhaust', 'extensionCircuitOutlet')
FILMCLOSURES = ('hatchPapell', 'sp8124Entrainment')

@dataclass
class ExtensionFilmState:

    '''

    The wall, the gas along it and the films, seeded by name from the Nozzle.

    The jacket section arrays (`*RegenSection`, `regenSection*`) and the extension arrays
    (`*Extension`, `extension*`) are the station properties `regenStations` writes. The chamber
    film fields are the configuration's; `extensionFilmSlots` is a list of slot definitions (see
    `readFilmSlots`), and `turbineExhaust` the solved `TurbineExhaustState` when a gas generator is
    specified.

    '''

    xRegenNozzle:                            Any = None
    rRegenNozzle:                            Any = None
    regenSectionNearWallVelocity:            Any = None
    densityRegenSection:                     Any = None
    regenSectionNearWallTemperature:         Any = None
    regenSectionNearWallMachNumber:          Any = None
    regenSectionNearWallRecoveryTemperature: Any = None
    regenSectionNearWallPressure:            Any = None
    specificHeatRegenSection:                Any = None
    thermalConductivityRegenSection:         Any = None
    viscosityRegenSection:                   Any = None
    prandtlNumberRegenSection:               Any = None
    xExtension:                              Any = None
    rExtension:                              Any = None
    extensionNearWallVelocity:               Any = None
    densityExtension:                        Any = None
    extensionNearWallTemperature:            Any = None
    extensionNearWallMachNumber:             Any = None
    extensionNearWallRecoveryTemperature:    Any = None
    extensionNearWallPressure:               Any = None
    specificHeatExtension:                   Any = None
    thermalCondExtension:                    Any = None
    viscosityExtension:                      Any = None
    prandtlExtension:                        Any = None
    chamberGamma:                            Any = None
    engineMassFlow:                          Any = None
    OFRatio:                                 Any = None
    nozzleScalingFactor:                     Any = None
    filmCooling:                             Any = None
    filmCoolant:                             Any = None
    filmCoolantMixtureRatio:                 Any = None
    filmCoolingModel:                        Any = None
    filmEntrainmentMultiplier:               Any = None
    filmInjectionAxialPosition:              Any = None
    filmInletTemperature:                    Any = None
    filmMassFlow:                            Any = None
    filmSlotHeight:                          Any = None
    extensionFilmSlots:                      Any = None
    extensionFilmModel:                      Any = None
    turbineExhaust:                          Any = None
    extensionCircuitSolution:                Any = None

@dataclass
class ExtensionFilmSlot:

    '''

    One slot injecting a film onto the extension.

    Attributes:
    -----------
    areaRatio : float
        Local area ratio of the wall at the slot [-]. On the extension.
    slotHeight : float
        Radial height of the annular slot [m].
    source : str
        'species', a named coolant at a given temperature; 'turbineExhaust', the gas generator's
        exhaust; or 'extensionCircuitOutlet', a coolant circuit's outlet.
    massFlow : float | None
        Flow through the slot [kg/s]. For turbine exhaust, the whole exhaust when unset.
    species : str | None
        Coolant name for a 'species' slot, as `utils.fluidProps` takes it.
    temperature : float | None
        Coolant temperature at the slot for a 'species' slot [K].
    mixtureRatio : float
        Oxidizer over fuel of the coolant [-]: zero for a fuel, the gas generator's for turbine
        exhaust. The entrainment closure carries it into the wall mixture ratio.

    '''

    areaRatio:    float
    slotHeight:   float
    source:       str
    massFlow:     Any = None
    species:      Any = None
    temperature:  Any = None
    mixtureRatio: float = 0.0

@dataclass
class FilmLayer:

    '''

    One film solved alone along the joined wall.

    Attributes:
    -----------
    name : str
        'chamber film', or the slot's source and area ratio.
    source : str
        'chamber', or the slot's source.
    injectionIndex : int
        Joined-wall station of the slot.
    injectionAreaRatio : float
        Area ratio at the slot [-].
    massFlow : float
        Film flow [kg/s].
    coolantTemperature : float
        Coolant temperature at the slot [K].
    slotPressure : float
        Wall static pressure at the slot [Pa].
    coolant : FilmCoolantState
        Coolant state leaving the slot.
    coolantGasConstant, coolantSpecificHeat : float
        Coolant gas constant [J/kg-K] and specific heat [J/kg-K], for its expansion.
    result : FilmCoolingResult
        The film under the configured closure.
    alternate : FilmCoolingResult
        The film under the other closure.
    velocityRatio : float
        Coolant over core velocity at the slot [-].
    extraDraw : bool
        True for a flow that leaves the engine without passing through the chamber.
    supplyPressureMargin : float | None
        Turbine exhaust pressure over the slot pressure, less one [-]; None for other sources.

    '''

    name:                 str
    source:               str
    injectionIndex:       int
    injectionAreaRatio:   float
    massFlow:             float
    coolantTemperature:   float
    slotPressure:         float
    coolant:              FilmCoolantState
    coolantGasConstant:   float
    coolantSpecificHeat:  float
    result:               FilmCoolingResult
    alternate:            FilmCoolingResult
    velocityRatio:        float
    extraDraw:            bool
    supplyPressureMargin: Any = None

    @property
    def withinInjectionBand(self) -> bool:

        '''True when the slot velocity ratio lies in SP-8124's recommended 0.9 to 1.15.'''

        return SP8124INJECTIONBAND[0] <= self.velocityRatio <= SP8124INJECTIONBAND[1]

@dataclass
class ExtensionFilmResult:

    '''

    The films on the joined wall, stacked.

    Attributes:
    -----------
    closure, alternateClosure : str
        The closure that drives the extension and the one reported beside it.
    x, areaRatio : numpy.ndarray
        Joined-wall axial position [m] and area ratio [-].
    jointIndex : int
        First extension station on the joined wall.
    recoveryTemperature : numpy.ndarray
        Near-wall recovery temperature along the joined wall [K].
    drivingTemperature, alternateDrivingTemperature : numpy.ndarray
        Superposed film drive along the joined wall under each closure [K].
    layers : list
        The `FilmLayer`s, in the order the gas meets them.

    '''

    closure:                     str
    alternateClosure:            str
    x:                           np.ndarray
    areaRatio:                   np.ndarray
    jointIndex:                  int
    recoveryTemperature:         np.ndarray
    drivingTemperature:          np.ndarray
    alternateDrivingTemperature: np.ndarray
    layers:                      list = field(default_factory = list)

    @property
    def extensionDrivingTemperature(self) -> np.ndarray:

        '''The configured drive on the extension's own stations [K].'''

        return self.drivingTemperature[self.jointIndex:]

    @property
    def extensionAlternateDrivingTemperature(self) -> np.ndarray:

        '''The other closure's drive on the extension's own stations [K].'''

        return self.alternateDrivingTemperature[self.jointIndex:]

    @property
    def extraMassFlow(self) -> float:

        '''Film flow that does not pass through the chamber [kg/s].'''

        return float(sum(layer.massFlow for layer in self.layers if layer.extraDraw))

    def report(self) -> str:

        '''A text summary of each film and the drive it leaves on the extension.'''

        lines = [f'Extension film, {self.closure} (other closure: {self.alternateClosure})']
        for layer in self.layers:
            band = 'inside' if layer.withinInjectionBand else 'outside'
            line = (f'  {layer.name}: {layer.massFlow:.3g} kg/s at {layer.coolantTemperature:.0f} K, '
                    f'area ratio {layer.injectionAreaRatio:.2f}, slot pressure '
                    f'{1e-3 * layer.slotPressure:.1f} kPa, velocity ratio {layer.velocityRatio:.2f} '
                    f'({band} SP-8124\'s 0.9 to 1.15)')
            if layer.supplyPressureMargin is not None:
                line += f', exhaust pressure margin {100.0 * layer.supplyPressureMargin:.0f} %'
            lines.append(line)
        if self.layers:
            drive = self.extensionDrivingTemperature
            other = self.extensionAlternateDrivingTemperature
            recovery = self.recoveryTemperature[self.jointIndex:]
            lines.append(f'  extension drive {drive.min():.0f} to {drive.max():.0f} K '
                         f'({self.alternateClosure}: {other.min():.0f} to {other.max():.0f} K) against '
                         f'a recovery temperature of {recovery.min():.0f} to {recovery.max():.0f} K')
        return '\n'.join(lines)

def readFilmSlots(rawSlots) -> list:

    '''

    The configuration's slot list as `ExtensionFilmSlot`s, refused where a slot is incomplete.

    Parameters:
    -----------
    rawSlots : list | None
        A list of dicts with keys 'areaRatio', 'slotHeight', 'source' and, by source, 'massFlow',
        'species', 'temperature' and 'mixtureRatio'. None, NaN or an empty list is no slot.

    Returns:
    --------
    list
        The slots, in the order given.

    Raises:
    -------
    InvalidInputError
        If an entry is not a dict, names an unknown source, or lacks what its source needs.

    '''

    if rawSlots is None or (isinstance(rawSlots, float) and np.isnan(rawSlots)):
        return []
    if not isinstance(rawSlots, (list, tuple)):
        raise InvalidInputError(
            message = 'extensionFilmSlots is a list of slot definitions, each a dict.',
            parameterName = 'extensionFilmSlots', value = rawSlots, validRange = 'a list of dicts')

    slots = []
    for number, raw in enumerate(rawSlots):
        if not isinstance(raw, dict):
            raise InvalidInputError(
                message = f'Extension film slot {number} is not a dict.',
                parameterName = 'extensionFilmSlots', value = raw, validRange = 'a dict')
        source = raw.get('source')
        if source not in FILMSOURCES:
            raise InvalidInputError(
                message = f'Extension film slot {number} names no source this solver knows.',
                parameterName = 'extensionFilmSlots[].source', value = source,
                validRange = ' or '.join(repr(name) for name in FILMSOURCES))
        needed = ['areaRatio', 'slotHeight'] + {'species': ['species', 'massFlow', 'temperature'],
                                                 'turbineExhaust': [],
                                                 'extensionCircuitOutlet': []}[source]
        missing = [key for key in needed if raw.get(key) is None]
        if missing:
            raise InvalidInputError(
                message = (f'Extension film slot {number} ({source}) is missing '
                           f'{", ".join(missing)}.'),
                parameterName = 'extensionFilmSlots[]', value = raw,
                validRange = ', '.join(needed))
        mixtureRatio = raw.get('mixtureRatio')
        slots.append(ExtensionFilmSlot(
            areaRatio    = float(raw['areaRatio']),
            slotHeight   = float(raw['slotHeight']),
            source       = source,
            massFlow     = None if raw.get('massFlow') is None else float(raw['massFlow']),
            species      = raw.get('species'),
            temperature  = None if raw.get('temperature') is None else float(raw['temperature']),
            mixtureRatio = 0.0 if mixtureRatio is None else float(mixtureRatio)))
    return slots

def joinedWall(state: ExtensionFilmState) -> dict:

    '''

    The jacket section and extension station arrays joined into one wall.

    The jacket section's stations run to the joint and the extension's start at it, so the jacket
    stations at and past the joint are dropped. Without an extension the wall is the jacket
    section alone.

    Returns:
    --------
    dict
        Station arrays 'x', 'r', 'u', 'rho', 'T', 'M', 'recovery', 'p', 'cp', 'k', 'mu', 'Pr',
        'total' (built from the chamber gamma, as the recovery temperature was), 'areaRatio',
        'massFluxRatio', and 'jointIndex', 'throatRadius'.

    '''

    pairs = (('x', 'xRegenNozzle', 'xExtension'), ('r', 'rRegenNozzle', 'rExtension'),
             ('u', 'regenSectionNearWallVelocity', 'extensionNearWallVelocity'),
             ('rho', 'densityRegenSection', 'densityExtension'),
             ('T', 'regenSectionNearWallTemperature', 'extensionNearWallTemperature'),
             ('M', 'regenSectionNearWallMachNumber', 'extensionNearWallMachNumber'),
             ('recovery', 'regenSectionNearWallRecoveryTemperature', 'extensionNearWallRecoveryTemperature'),
             ('p', 'regenSectionNearWallPressure', 'extensionNearWallPressure'),
             ('cp', 'specificHeatRegenSection', 'specificHeatExtension'),
             ('k', 'thermalConductivityRegenSection', 'thermalCondExtension'),
             ('mu', 'viscosityRegenSection', 'viscosityExtension'),
             ('Pr', 'prandtlNumberRegenSection', 'prandtlExtension'))

    hasExtension = state.xExtension is not None and len(state.xExtension) > 0
    xRegen = np.asarray(state.xRegenNozzle, dtype = float)
    keep = xRegen < float(state.xExtension[0]) - 1.0e-9 if hasExtension else np.ones(len(xRegen), bool)

    wall = {}
    for key, regenName, extensionName in pairs:
        regen = np.asarray(getattr(state, regenName), dtype = float)[keep]
        extension = (np.asarray(getattr(state, extensionName), dtype = float) if hasExtension
                     else np.zeros(0))
        wall[key] = np.concatenate([regen, extension])

    wall['jointIndex'] = int(keep.sum()) if hasExtension else len(wall['x'])
    wall['throatRadius'] = sizedThroatRadius(wall['r'], state.nozzleScalingFactor)
    wall['areaRatio'] = (wall['r'] / wall['throatRadius'])**2
    wall['total'] = wall['T'] * (1.0 + 0.5 * (float(state.chamberGamma) - 1.0) * wall['M']**2)
    wall['massFluxRatio'] = (wall['rho'] * wall['u']) / (float(state.engineMassFlow)
                                                          / (np.pi * wall['r']**2))
    return wall

def superposeFilms(recoveryTemperature, drives, coolantTemperatures) -> np.ndarray:

    '''

    Stack films by Sellers' superposition, in the order given.

    Parameters:
    -----------
    recoveryTemperature : array_like
        The wall's drive with no film [K].
    drives : list
        Each film's drive solved alone, on the same stations [K].
    coolantTemperatures : list
        Each film's coolant temperature at its slot [K].

    Returns:
    --------
    numpy.ndarray
        The stacked adiabatic wall temperature [K].

    '''

    recovery = np.asarray(recoveryTemperature, dtype = float)
    stacked = recovery.copy()
    for drive, coolant in zip(drives, coolantTemperatures):
        span = recovery - float(coolant)
        # A film's effectiveness against the recovery temperature; zero upstream of its slot,
        # where its own drive is the recovery temperature to the bit
        safe = np.abs(span) > 1.0e-9
        effectiveness = np.where(safe, (recovery - np.asarray(drive, dtype = float))
                                 / np.where(safe, span, 1.0), 0.0)
        stacked = stacked - effectiveness * (stacked - float(coolant))
    return stacked

def filmExpansionVelocity(staticTemperature: float, velocity: float, staticPressure: float,
                          exitPressure: float, specificHeat: float, gasConstant: float) -> float:

    '''

    Velocity a film reaches expanding unmixed from its slot to the exit static pressure.

    The film's total state at the slot is built from its static state and velocity as an ideal gas
    of constant specific heat, and it expands isentropically to the exit pressure.

    Parameters:
    -----------
    staticTemperature, velocity, staticPressure : float
        Film state leaving the slot [K], [m/s], [Pa].
    exitPressure : float
        Static pressure of the exit plane [Pa].
    specificHeat, gasConstant : float
        Film specific heat and gas constant [J/kg-K].

    Returns:
    --------
    float
        Exit velocity [m/s]; the slot velocity where the exit pressure is not below the slot's
        total pressure.

    '''

    gamma = specificHeat / (specificHeat - gasConstant)
    totalTemperature = staticTemperature + velocity**2 / (2.0 * specificHeat)
    totalPressure = staticPressure * (totalTemperature / staticTemperature)**(gamma / (gamma - 1.0))
    if exitPressure >= totalPressure:
        return float(velocity)
    return float(np.sqrt(2.0 * specificHeat * totalTemperature
                         * (1.0 - (exitPressure / totalPressure)**((gamma - 1.0) / gamma))))

def mixedFilmThrust(coreMassFlow: float, coreExitVelocity: float, coreTotalEnthalpy: float,
                    filmMassFlows, filmTotalEnthalpies) -> float:

    '''

    Thrust the films add if they mix fully into the core at injection.

    The mixture shares the core's expansion, and an ideal gas expanding through a fixed pressure
    ratio leaves at a velocity proportional to the square root of its total enthalpy.

    Parameters:
    -----------
    coreMassFlow, coreExitVelocity, coreTotalEnthalpy : float
        Core flow [kg/s], exit velocity [m/s] and total enthalpy above 0 K [J/kg].
    filmMassFlows, filmTotalEnthalpies : array_like
        Each film's flow [kg/s] and total enthalpy above 0 K [J/kg].

    Returns:
    --------
    float
        (m_c + m_f) u_mix - m_c u_c [N].

    '''

    flows = np.asarray(filmMassFlows, dtype = float)
    enthalpies = np.asarray(filmTotalEnthalpies, dtype = float)
    total = coreMassFlow + flows.sum()
    mixedEnthalpy = (coreMassFlow * coreTotalEnthalpy + np.sum(flows * enthalpies)) / total
    mixedVelocity = coreExitVelocity * np.sqrt(mixedEnthalpy / coreTotalEnthalpy)
    return float(total * mixedVelocity - coreMassFlow * coreExitVelocity)

def _closureOf(name, fallback: str) -> str:

    closure = name if isinstance(name, str) else fallback
    if closure not in FILMCLOSURES:
        raise InvalidInputError(
            message = 'No film cooling closure by that name.',
            parameterName = 'extensionFilmModel', value = closure,
            validRange = ' or '.join(repr(item) for item in FILMCLOSURES))
    return closure

def _solveLayer(wall: dict, closure: str, injectionPosition: float, slotHeight: float,
                coolant: FilmCoolantState, massFlow: float, coolantTemperature: float,
                coolantMixtureRatio: float, state: ExtensionFilmState) -> FilmCoolingResult:

    '''One film alone on the joined wall, by one closure, as `regenStations` solves the chamber film.'''

    if closure == 'hatchPapell':
        return filmCoolingArrays(
            axialPosition             = wall['x'],
            radius                    = wall['r'],
            gasVelocity               = wall['u'],
            gasStaticTemperature      = wall['T'],
            recoveryTemperature       = wall['recovery'],
            gasThermalConductivity    = wall['k'],
            gasDensity                = wall['rho'],
            gasViscosity              = wall['mu'],
            gasPrandtlNumber          = wall['Pr'],
            injectionPosition         = injectionPosition,
            slotHeight                = slotHeight,
            coolantMassFlow           = massFlow,
            coolantSpecificHeat       = coolant.specificHeat,
            coolantTemperature        = coolantTemperature,
            coolantThermalDiffusivity = coolant.thermalDiffusivity,
            coolantVelocity           = coolant.velocity)

    return entrainmentFilmArrays(
        axialPosition           = wall['x'],
        radius                  = wall['r'],
        gasVelocity             = wall['u'],
        gasDensity              = wall['rho'],
        totalTemperature        = wall['total'],
        recoveryTemperature     = wall['recovery'],
        coreSpecificHeat        = wall['cp'],
        massFluxRatio           = wall['massFluxRatio'],
        injectionPosition       = injectionPosition,
        slotHeight              = slotHeight,
        coreMassFlow            = float(state.engineMassFlow),
        coolantMassFlow         = massFlow,
        coolantDensity          = coolant.density,
        coolantVelocity         = coolant.velocity,
        coolantViscosity        = coolant.viscosity,
        coolantSpecificHeat     = coolant.specificHeat,
        coolantTotalTemperature = coolantTemperature,
        coreMixtureRatio        = float(state.OFRatio),
        coolantMixtureRatio     = coolantMixtureRatio,
        injectionMultiplier     = (float(state.filmEntrainmentMultiplier)
                                   if specified(state, 'filmEntrainmentMultiplier') else 3.5),
        throatRadius            = wall['throatRadius'])

def _slotIndex(wall: dict, areaRatio: float, number: int) -> int:

    '''The extension station at a slot's area ratio, refused off the extension.'''

    joint = wall['jointIndex']
    extensionRatios = wall['areaRatio'][joint:]
    if len(extensionRatios) == 0:
        raise InvalidInputError(
            message = 'An extension film slot needs an extension to lie on; this jacket runs to the exit.',
            parameterName = 'extensionFilmSlots[].areaRatio', value = areaRatio,
            validRange = 'an area ratio on the extension')
    low, high = float(extensionRatios[0]), float(extensionRatios[-1])
    if not low * (1.0 - 1.0e-6) <= areaRatio <= high * (1.0 + 1.0e-6):
        raise InvalidInputError(
            message = (f'Extension film slot {number} at an area ratio of {areaRatio:.3g} is off the '
                       f'extension, which runs from {low:.3g} to {high:.3g}. A slot inside the jacket '
                       f'section is the chamber film.'),
            parameterName = 'extensionFilmSlots[].areaRatio', value = areaRatio,
            validRange = f'{low:.3g} to {high:.3g}')
    return joint + int(np.argmin(np.abs(extensionRatios - areaRatio)))

def solveExtensionFilm(state: ExtensionFilmState, circuitOutlet: dict = None) -> ExtensionFilmResult:

    '''

    Solve every film on the joined wall and stack them.

    Parameters:
    -----------
    state : ExtensionFilmState
        The wall, the gas, the chamber film and the slots.
    circuitOutlet : dict | None
        For an 'extensionCircuitOutlet' slot, the circuit's outlet state: 'species',
        'temperature', 'massFlow'. Its slot definition's own values are used when this is unset.

    Returns:
    --------
    ExtensionFilmResult

    Raises:
    -------
    InvalidInputError
        If a slot lies off the extension, a turbine exhaust slot has no gas generator, the slots
        draw more exhaust than the turbine passes, or the exhaust cannot enter against the wall
        pressure at its slot.

    '''

    wall = joinedWall(state)
    closure = _closureOf(state.extensionFilmModel, _closureOf(state.filmCoolingModel, 'hatchPapell'))
    alternateClosure = [item for item in FILMCLOSURES if item != closure][0]
    layers = []

    def addLayer(name, source, index, massFlow, coolantTemperature, slotHeight, coolant,
                 gasConstant, specificHeat, mixtureRatio, extraDraw, margin = None):
        # The closures take the film's static state at the wall pressure, which is a subsonic slot;
        # a slot too small for its flow there would have to run supersonic, which neither describes
        gamma = specificHeat / (specificHeat - gasConstant)
        slotMach = coolant.velocity / np.sqrt(gamma * gasConstant * coolantTemperature)
        if slotMach >= 1.0:
            raise InvalidInputError(
                message = (f'The {name} leaves its {1e3 * slotHeight:.1f} mm slot at Mach {slotMach:.1f}: '
                           f'at the {1e-3 * float(wall["p"][index]):.1f} kPa wall pressure there, '
                           f'{massFlow:.3g} kg/s needs a slot about {1e3 * slotHeight * slotMach / 0.6:.0f} mm '
                           f'tall to leave at Mach 0.6. A taller slot, or one where the wall pressure is '
                           f'higher, brings it subsonic.'),
                parameterName = 'slotHeight', value = slotHeight,
                validRange = 'a subsonic slot')
        position = float(wall['x'][index])
        result = _solveLayer(wall, closure, position, slotHeight, coolant, massFlow,
                             coolantTemperature, mixtureRatio, state)
        alternate = _solveLayer(wall, alternateClosure, position, slotHeight, coolant, massFlow,
                                coolantTemperature, mixtureRatio, state)
        layers.append(FilmLayer(
            name = name, source = source, injectionIndex = int(index),
            injectionAreaRatio = float(wall['areaRatio'][index]), massFlow = float(massFlow),
            coolantTemperature = float(coolantTemperature), slotPressure = float(wall['p'][index]),
            coolant = coolant, coolantGasConstant = float(gasConstant),
            coolantSpecificHeat = float(specificHeat), result = result, alternate = alternate,
            velocityRatio = float(coolant.velocity / wall['u'][index]), extraDraw = extraDraw,
            supplyPressureMargin = margin))

    # -- The chamber film, carried past the joint -- #
    if state.filmCooling == 'on':
        index = int(np.argmin(np.abs(wall['x'] - float(state.filmInjectionAxialPosition))))
        coolant = filmCoolantState(state.filmCoolant, float(state.filmInletTemperature),
                                   float(wall['p'][index]), float(state.filmMassFlow),
                                   float(state.filmSlotHeight), float(wall['r'][index]))
        gasConstant = float(wall['p'][index]) / (coolant.density * float(state.filmInletTemperature))
        mixtureRatio = (float(state.filmCoolantMixtureRatio)
                        if specified(state, 'filmCoolantMixtureRatio') else 0.0)
        # The chamber film is placed where the configuration put it, not snapped to a station, so
        # the jacket section reproduces the film regenStations solved
        position = float(state.filmInjectionAxialPosition)
        result = _solveLayer(wall, closure, position, float(state.filmSlotHeight), coolant,
                             float(state.filmMassFlow), float(state.filmInletTemperature),
                             mixtureRatio, state)
        alternate = _solveLayer(wall, alternateClosure, position, float(state.filmSlotHeight),
                                coolant, float(state.filmMassFlow),
                                float(state.filmInletTemperature), mixtureRatio, state)
        layers.append(FilmLayer(
            name = 'chamber film', source = 'chamber', injectionIndex = index,
            injectionAreaRatio = float(wall['areaRatio'][index]),
            massFlow = float(state.filmMassFlow),
            coolantTemperature = float(state.filmInletTemperature),
            slotPressure = float(wall['p'][index]), coolant = coolant,
            coolantGasConstant = gasConstant, coolantSpecificHeat = coolant.specificHeat,
            result = result, alternate = alternate,
            velocityRatio = float(coolant.velocity / wall['u'][index]), extraDraw = False))

    # -- The extension slots -- #
    slots = readFilmSlots(state.extensionFilmSlots)
    exhaust = state.turbineExhaust
    exhaustDrawn = 0.0
    for number, slot in enumerate(slots):
        index = _slotIndex(wall, slot.areaRatio, number)
        slotPressure = float(wall['p'][index])
        radius = float(wall['r'][index])
        name = f'{slot.source} slot at area ratio {slot.areaRatio:.3g}'

        if slot.source == 'turbineExhaust':
            if exhaust is None:
                raise InvalidInputError(
                    message = (f'Extension film slot {number} takes turbine exhaust, and no gas '
                               f'generator is specified. Give gasGeneratorMixtureRatio, '
                               f'gasGeneratorPressure, turbinePressureRatio, turbineEfficiency and '
                               f'turbineExhaustMassFlow.'),
                    parameterName = 'extensionFilmSlots[].source', value = slot.source,
                    validRange = 'a specified gas generator')
            flow = exhaust.massFlow if slot.massFlow is None else slot.massFlow
            exhaustDrawn += flow
            if exhaust.pressure < slotPressure:
                raise InvalidInputError(
                    message = (f'The turbine exhausts at {1e-3 * exhaust.pressure:.1f} kPa and the wall '
                               f'at slot {number}, area ratio {slot.areaRatio:.3g}, sits at '
                               f'{1e-3 * slotPressure:.1f} kPa, so the exhaust cannot enter there. Move '
                               f'the slot downstream or lower the turbine pressure ratio.'),
                    parameterName = 'extensionFilmSlots[].areaRatio', value = slot.areaRatio,
                    validRange = f'where the wall pressure is below {1e-3 * exhaust.pressure:.1f} kPa')
            coolant = exhaust.filmState(slotPressure, slot.slotHeight, radius, flow)
            addLayer(name, slot.source, index, flow, exhaust.temperature, slot.slotHeight, coolant,
                     exhaust.gasConstant, exhaust.specificHeat,
                     slot.mixtureRatio if slot.mixtureRatio else exhaust.mixtureRatio, True,
                     margin = exhaust.pressure / slotPressure - 1.0)
            continue

        outlet = {}
        if slot.source == 'extensionCircuitOutlet':
            # The circuit's outlet is known only once the circuit is solved, which happens after a
            # first pass of the films ahead of it; that pass leaves the slot out
            circuit = state.extensionCircuitSolution
            if circuitOutlet is None and circuit is None:
                continue
            if circuitOutlet is None:
                if circuit.outlet != 'film':
                    raise InvalidInputError(
                        message = (f'Extension film slot {number} takes the extension circuit\'s '
                                   f'outlet, and the circuit\'s outlet is {circuit.outlet}. Set '
                                   f'extensionCircuitOutlet to film.'),
                        parameterName = 'extensionFilmSlots[].source', value = slot.source,
                        validRange = 'a circuit whose outlet is film')
                circuitOutlet = {'species': circuit.coolant, 'temperature': circuit.outletTemperature,
                                 'massFlow': circuit.massFlow}
            outlet = dict(circuitOutlet)
        species = outlet.get('species', slot.species)
        temperature = float(outlet.get('temperature', slot.temperature))
        flow = float(outlet.get('massFlow', slot.massFlow))
        coolant = filmCoolantState(species, temperature, slotPressure, flow, slot.slotHeight, radius)
        gasConstant = slotPressure / (coolant.density * temperature)
        addLayer(name, slot.source, index, flow, temperature, slot.slotHeight, coolant,
                 gasConstant, coolant.specificHeat, slot.mixtureRatio, True)

    if exhaust is not None and exhaustDrawn > exhaust.massFlow * (1.0 + 1.0e-9):
        raise InvalidInputError(
            message = (f'The slots draw {exhaustDrawn:.4g} kg/s of turbine exhaust and the turbine '
                       f'passes {exhaust.massFlow:.4g} kg/s.'),
            parameterName = 'extensionFilmSlots[].massFlow', value = exhaustDrawn,
            validRange = f'at most {exhaust.massFlow:.4g} kg/s in all')

    # The gas meets the films in the order of their slots
    layers.sort(key = lambda layer: layer.injectionIndex)
    temperatures = [layer.coolantTemperature for layer in layers]
    drive = superposeFilms(wall['recovery'], [layer.result.drivingTemperature for layer in layers],
                           temperatures)
    alternateDrive = superposeFilms(wall['recovery'],
                                    [layer.alternate.drivingTemperature for layer in layers],
                                    temperatures)

    return ExtensionFilmResult(
        closure                     = closure,
        alternateClosure            = alternateClosure,
        x                           = wall['x'],
        areaRatio                   = wall['areaRatio'],
        jointIndex                  = wall['jointIndex'],
        recoveryTemperature         = wall['recovery'],
        drivingTemperature          = drive,
        alternateDrivingTemperature = alternateDrive,
        layers                      = layers)
