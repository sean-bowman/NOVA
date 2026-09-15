
# -- NASA CEA Interface for the NOVA Nozzle Design Tool -- #

'''

Thin, drop-in replacement for the legacy f2py CEAWrapper, backed by the
pip-installable `rocketcea` package (Charlie Taylor / sonofeft).

The public surface intentionally mirrors the old wrapper: construct a CEA
object and read `ceaResults` / `nozzlePerformance`. All returned values are
SI (Pa, K, m/s, J/kg-K, W/m-K, Pa-s, kg/m^3), matching what Nozzle.py expects.

THREAD SAFETY: rocketcea is NOT thread-safe. It carries module-level state
(`_last_called`, `_CacheObjDict`) and reads results out of process-global
FORTRAN COMMON blocks. Two threads interleaving calls silently return each
other's numbers with no error raised. Every solve here is serialized behind
_CEAOBJLOCK. Do NOT wrap CEA calls in joblib.Parallel with a threading
backend; use processes if parallelism is ever needed.

Sean Bowman

'''

import functools
import os
import threading
import warnings

import numpy as np

from . import units

# rocketcea's find_mingw_lib.add_mingw_lib() walks PATH and calls
# os.add_dll_directory() on every entry matching *mingw64*bin, with no
# existence check. A single stale or typo'd PATH entry therefore raises
# FileNotFoundError at import time. Drop non-existent entries first.
os.environ['PATH'] = ';'.join(
    entry for entry in os.environ.get('PATH', '').split(';')
    if entry and os.path.isdir(entry)
)

from rocketcea.cea_obj import CEA_Obj, add_new_fuel, add_new_oxidizer
from rocketcea.input_cards import oxCards, fuelCards

__all__ = ['CEA', 'getAvailableFuels', 'getAvailableOxidizers']

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- Unit conversions -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

# rocketcea runs CEA with `output='calories'` and returns English/CGS units,
# whereas the legacy wrapper ran `output siunits` and read SI directly out of
# the COMMON blocks. Every property therefore passes through a conversion here.
# These factors were verified empirically against rocketcea 1.2.3: recomputing
# Prandtl as (Cp * mu / k) reproduces CEA's own reported Pr exactly, and
# rho * R * T recovers the input chamber pressure exactly.

# The definitional ones come from the package registry, so there is one place a factor is
# defined and none where it is retyped.
PA_PER_PSIA       = units.PA_PER_PSIA                     # psia    -> Pa
DEGR_TO_K         = units.K_PER_DEGR                      # degR    -> K
FTPS_TO_MPS       = units.M_PER_S_PER_FT_PER_S            # ft/s    -> m/s
LBMPFT3_TO_KGPM3  = units.KG_PER_M3_PER_LBM_PER_FT3       # lbm/ft3 -> kg/m3
BTUPLBM_TO_JPKG   = units.J_PER_KG_PER_BTU_PER_LBM        # BTU/lbm -> J/kg      (enthalpies)
CALPGK_TO_JPKGK   = units.J_PER_KG_K_PER_CAL_PER_GK       # cal/g-K -> J/kg-K    (Cp, entropies)
MILLIPOISE_TO_PAS = units.PA_S_PER_MILLIPOISE             # millipoise  -> Pa-s
MCALCMKS_TO_WMK   = units.W_PER_M_K_PER_MCAL_CM_S_K       # mcal/cm-K-s -> W/m-K
GRAVITY           = units.GRAVITY                         # m/s2, standard gravity
SEA_LEVEL_PA      = units.PA_PER_ATM                      # Pa

# This one is deliberately NOT the registry's molar gas constant. It is the value CEA itself
# works in, and it is here because the empirical check above depends on it: rho * R * T recovers
# the input chamber pressure exactly with 8314.46 and not with the CODATA 8314.462618. Matching
# the tool being wrapped matters more here than matching the current best measurement.
R_UNIVERSAL       = 8314.46            # J/(kmol-K), as CEA uses it

# NOTE the asymmetry that makes this easy to get wrong: BTU/(lbm-degR) and
# cal/(g-K) are numerically identical, but BTU/lbm (2326) and cal/g (4184)
# differ by a factor of 1.8. Enthalpies are BTU/lbm; heat capacities and
# entropies are cal-based. A validation discrepancy near 1.8, 4.184 or 9.81
# is a unit bug here, not a physics difference.

# Placeholder expansion ratio used when the caller only specifies a contraction
# ratio. eps participates in rocketcea's internal run cache, so holding this
# constant lets an entire converging-section sweep reuse one solve per
# contraction ratio. eps has no effect on chamber or throat station values.
DUMMY_EPS = 2.0

# Below this area ratio the supersonic branch is degenerate and CEA either
# fails or returns the subsonic root.
MIN_SUPERSONIC_EPS = 1.0 + 1.0e-6

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- Propellant name normalization -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

# NOVA's Fuel/Oxidizer fields are free text from a JSON config or a spreadsheet
# cell, so they are normalized aggressively (case folded, punctuation stripped)
# and then mapped onto rocketcea's exact card keys. rocketcea's own keys ARE
# case sensitive and are not always what you would guess: it uses 'RP_1', and
# a hyphenated 'RP-1' is not a valid key.

FUELALIASES = {
    'LH2'            : 'LH2',
    'H2'             : 'LH2',
    'HYDROGEN'       : 'LH2',
    'LIQUIDHYDROGEN' : 'LH2',
    'GH2'            : 'GH2',
    'GASEOUSHYDROGEN': 'GH2',
    'CH4'            : 'CH4',
    'METHANE'        : 'CH4',
    'LCH4'           : 'CH4',
    'LIQUIDMETHANE'  : 'CH4',
    'GCH4'           : 'GCH4',
    'GASEOUSMETHANE' : 'GCH4',
    'RP1'            : 'RP_1',
    'RP'             : 'RP_1',
    'KEROSENE'       : 'RP_1',
    'JETA'           : 'JetA',
    'JP10'           : 'JP10',
    'ETHANOL'        : 'C2H5OH',
    'C2H5OH'         : 'C2H5OH',
    'METHANOL'       : 'CH3OH',
    'CH3OH'          : 'CH3OH',
    'MMH'            : 'MMH',
    'N2H4'           : 'N2H4',
    'HYDRAZINE'      : 'N2H4',
    'UDMH'           : 'UDMH',
    'A50'            : 'A50',
    'AEROZINE50'     : 'A50',
    'NH3'            : 'NH3',
    'AMMONIA'        : 'NH3',
    'PROPANE'        : 'Propane',
    'C3H8'           : 'Propane',
    'PROPYLENE'      : 'Propylene',
    'HTPB'           : 'HTPB',
    'HDPE'           : 'HDPE',
    'PE'             : 'HDPE',
    'POLYETHYLENE'   : 'HDPE',
}

OXIDIZERALIASES = {
    'LOX'            : 'LOX',
    'O2'             : 'LOX',
    'LO2'            : 'LOX',
    'OXYGEN'         : 'LOX',
    'LIQUIDOXYGEN'   : 'LOX',
    'GOX'            : 'GOX',
    'GO2'            : 'GOX',
    'GASEOUSOXYGEN'  : 'GOX',
    'N2O'            : 'N2O',
    'NITROUS'        : 'N2O',
    'NITROUSOXIDE'   : 'N2O',
    'N2O4'           : 'N2O4',
    'NTO'            : 'N2O4',
    'MON3'           : 'MON3',
    'MON15'          : 'MON15',
    'MON25'          : 'MON25',
    'H2O2'           : 'H2O2',
    'HTP'            : 'H2O2',
    'PEROXIDE'       : 'H2O2',
    'IRFNA'          : 'IRFNA',
    'HNO3'           : 'HNO3',
    'AIR'            : 'AIR',
    'F2'             : 'F2',
    'CLF5'           : 'CLF5',
}

# Propellants absent from rocketcea's built-in card set. Both are lifted
# verbatim from propulsionDesign/CEAWrapper/input_cards.py rather than
# re-derived, because hand-deriving a heat of formation is a reliable way to
# produce confidently wrong hybrid performance.
CUSTOMFUELCARDS = {
    # t(k)=1010 is deliberate: it is the HDPE pyrolysis surface temperature
    # used for hybrid grain analysis, NOT a typo for the 298.15 K standard
    # state. Do not "correct" it.
    'HDPE' : 'fuel HDPE    C 2.0 H 4.0    wt%=100.00    h,cal=-13409.4    t(k)=1010   rho.kg/m^3=980',
}

CUSTOMOXIDIZERCARDS = {}

# add_new_fuel / add_new_oxidizer mutate rocketcea's global card tables and
# invalidate its run cache, so each card is registered at most once per
# process. Registering inside a per-station loop would be a silent ~100x
# slowdown rather than an error.
_REGISTEREDPROPELLANTS = set()

# rocketcea is not thread-safe; every solve is serialized behind this lock.
_CEAOBJLOCK = threading.RLock()

# Cache of resolved max-Isp mixture ratios, keyed on (fuel, ox, Pc, eps).
_MAXISPCACHE = {}

def normalizeName(rawName: str) -> str:
    '''
    Fold a free-text propellant name to an alias-table key: upper case with all
    non-alphanumeric characters removed, so 'RP-1', 'rp 1' and 'RP_1' collapse
    to the same lookup.
    '''
    return ''.join(character for character in str(rawName).upper() if character.isalnum())

def resolvePropellantName(rawName: str, aliasTable: dict, customCards: dict,
                          builtinCards: dict, kindLabel: str) -> str:
    '''
    Map a free-text propellant name onto a rocketcea card key, registering a
    custom card if one is needed. Raises ValueError listing the accepted names
    when the input is not recognized, so a bad spreadsheet cell is diagnosable
    without reading source.
    '''
    normalized = normalizeName(rawName)
    if normalized in aliasTable:
        canonicalName = aliasTable[normalized]
    elif rawName in builtinCards:
        # Allow an exact rocketcea key straight through, so the full card set
        # stays reachable without every name being aliased above.
        canonicalName = rawName
    else:
        validNames = ', '.join(sorted(set(aliasTable.values())))
        raise ValueError(
            f'Unrecognized {kindLabel} name {rawName!r}. ceaInterface accepts '
            f'(case- and punctuation-insensitive): {validNames}. Any exact '
            f'rocketcea card key is also accepted. To add a propellant, put a '
            f'CEA card in CUSTOM{kindLabel.upper()}CARDS in ceaInterface.py.'
        )
    _registerCustomCard(canonicalName, customCards, kindLabel)
    return canonicalName

def _registerCustomCard(canonicalName: str, customCards: dict, kindLabel: str) -> None:
    '''
    Register a custom propellant card with rocketcea exactly once per process.
    '''
    if canonicalName not in customCards:
        return
    if canonicalName in _REGISTEREDPROPELLANTS:
        return
    with _CEAOBJLOCK:
        # Re-check inside the lock so concurrent callers cannot double register.
        if canonicalName in _REGISTEREDPROPELLANTS:
            return
        if kindLabel == 'fuel':
            add_new_fuel(canonicalName, customCards[canonicalName])
        else:
            add_new_oxidizer(canonicalName, customCards[canonicalName])
        _REGISTEREDPROPELLANTS.add(canonicalName)

def getAvailableFuels() -> list:
    '''
    Return every fuel name this interface accepts, including custom cards.
    '''
    return sorted(set(FUELALIASES.values()) | set(fuelCards.keys()))

def getAvailableOxidizers() -> list:
    '''
    Return every oxidizer name this interface accepts, including custom cards.
    '''
    return sorted(set(OXIDIZERALIASES.values()) | set(oxCards.keys()))

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- Oxidizer temperature handling -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

def _cardTemperature(cardEntry) -> float:
    '''
    Pull the t(k)= assigned-state temperature out of a CEA propellant card.
    Returns np.nan when the card carries no explicit temperature.
    '''
    cardText = cardEntry if isinstance(cardEntry, str) else ' '.join(cardEntry)
    for token in cardText.split():
        if token.startswith('t(k)='):
            try:
                return float(token[5:])
            except ValueError:
                return np.nan
    return np.nan

def _resolveOxidizerCard(canonicalName: str, oxidizerTemperature, chamberPressure: float) -> str:
    '''
    Return the rocketcea oxidizer key to use for a requested initial
    temperature.

    Fast path (the overwhelmingly common case): when no temperature is given,
    or it already matches the card's assigned state, the built-in card is used
    unchanged. This matters for performance as much as correctness, since
    registering a card invalidates rocketcea's run cache.

    Slow path: a temperature-shifted card is registered once under a derived
    name. The enthalpy correction follows the legacy wrapper's formula
    (h_formation + h(T) * molarMass). Note this mixes CEA's assigned-state
    reference with CoolProp/REFPROP's reference state, so it is approximate;
    it is preserved for continuity with prior NOVA results. If no property
    backend is available the default card is used with a warning rather than
    failing the run: a few kelvin of oxidizer temperature error is worth far
    less than a crashed design sweep.
    '''
    if oxidizerTemperature is None or not np.isfinite(oxidizerTemperature):
        return canonicalName
    baseCard = oxCards.get(canonicalName)
    if baseCard is None:
        return canonicalName
    cardTemperature = _cardTemperature(baseCard)
    if np.isfinite(cardTemperature) and abs(cardTemperature - oxidizerTemperature) <= 0.5:
        return canonicalName
    derivedName = f'{canonicalName}_T{int(round(oxidizerTemperature))}'
    if derivedName in _REGISTEREDPROPELLANTS:
        return derivedName
    # fluidProps is NOVA's own unified REFPROP/CoolProp accessor; import lazily
    # so this module stays importable when neither backend is installed.
    try:
        from .utils import fluidProps
        enthalpy, molarMass = fluidProps(
            canonicalName, 'TP', 'H M', oxidizerTemperature, chamberPressure)
    except Exception as error:
        warnings.warn(
            f'Could not correct the {canonicalName} card to '
            f'{oxidizerTemperature} K ({error}). Falling back to the default '
            f'card at {cardTemperature} K.'
        )
        return canonicalName
    cardText = baseCard if isinstance(baseCard, str) else ''.join(baseCard)
    cardTokens = cardText.split()
    formationEnthalpy = 0.0
    temperatureIndex, heatIndex = None, None
    for index, token in enumerate(cardTokens):
        if token.startswith('t(k)='):
            temperatureIndex = index
        elif token.startswith('h,cal=') or token.startswith('h,j='):
            heatIndex = index
            try:
                formationEnthalpy = float(token.split('=', 1)[1])
            except ValueError:
                formationEnthalpy = 0.0
    if temperatureIndex is None or heatIndex is None:
        warnings.warn(
            f'The {canonicalName} card has no editable t(k)/h field; using it '
            f'unchanged at {cardTemperature} K.'
        )
        return canonicalName
    cardTokens[temperatureIndex] = f't(k)={oxidizerTemperature}'
    cardTokens[heatIndex] = f'h,j={formationEnthalpy + enthalpy * molarMass}'
    with _CEAOBJLOCK:
        if derivedName not in _REGISTEREDPROPELLANTS:
            add_new_oxidizer(derivedName, (' ' * 4).join(cardTokens))
            _REGISTEREDPROPELLANTS.add(derivedName)
    return derivedName

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- CEA_Obj cache -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

@functools.lru_cache(maxsize = 512)
def _makeCeaObj(fuelName: str, oxidizerName: str, contractionRatioKey) -> CEA_Obj:
    '''
    Build (or return a cached) rocketcea CEA_Obj.

    Keyed only on the CEA_Obj *constructor* arguments. Pc, MR and eps are
    per-call arguments, so they deliberately do not appear here. A converging
    section sweep legitimately produces hundreds of distinct contraction
    ratios, hence the generous maxsize.
    '''
    return CEA_Obj(oxName = oxidizerName, fuelName = fuelName, fac_CR = contractionRatioKey)

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- Lazy result groups -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

# Every rocketcea getter unconditionally re-runs the CEA FORTRAN solve; there
# is no "cards unchanged, skip it" path. Worse, any getter requesting transport
# properties forces makeOutput=True, so CEA writes and re-reads an output file,
# costing ~26 ms against ~1.7 ms for a plain solve. Assembling all ~50 result
# keys eagerly therefore costs ~140 ms per station, and Nozzle.py calls this
# once per contour station.
#
# Two measures bring that down. First, the three transport stations are filled
# by a single solve (verified bit-identical to calling all three getters), so
# only one transport run is issued. Second, results are grouped and each group
# is computed on first access. Nozzle.py's converging and diverging sweeps read
# only transport and molecular-weight keys, so they never pay for thermodynamic
# state, species concentrations, performance or injector-face properties.

_KEYGROUPS = {

    'transport' : [
        'combustionChamberHeatCapacity', 'throatHeatCapacity', 'exitHeatCapacity',
        'combustionChamberThermalConductivity', 'throatThermalConductivity',
        'exitThermalConductivity',
        'combustionChamberPrandtlNumber', 'throatPrandtlNumber', 'exitPrandtlNumber',
        'combustionChamberViscosity', 'throatViscosity', 'exitViscosity',
    ],

    'molecularWeight' : [
        'combustionChamberMolecularWeight', 'throatMolecularWeight', 'exitMolecularWeight',
        'combustionChamberGasConstant', 'throatGasConstant', 'exitGasConstant',
        'combustionChamberGamma', 'throatGamma', 'exitGamma',
    ],

    'thermodynamic' : [
        'combustionChamberTemperature', 'throatTemperature', 'exitTemperature',
        'combustionChamberDensity', 'throatDensity', 'exitDensity',
        'combustionChamberSonicVelocity', 'throatSonicVelocity', 'exitSonicVelocity',
        'combustionChamberEnthalpy', 'throatEnthalpy', 'exitEnthalpy',
        'combustionChamberEntropy', 'throatEntropy', 'exitEntropy',
        'exitVelocity',
    ],

    'pressure' : [
        'injectionPressure', 'combustionChamberPressure', 'throatPressure',
        'exitPressure', 'exitMach', 'throatMach', 'expansionRatio', 'contractionRatio',
        'O/F Ratio',
    ],

    'performance' : [
        'characteristicVelocity', 'nozzlePerformance',
    ],

    'species' : [
        'massFractions', 'molFractions', 'molWeights',
    ],

    'injector' : [
        'injectionTemperature', 'injectorMolecularWeight', 'injectonGamma',
        'injectionHeatCapacity', 'injectionEnthalpy', 'injectorEntropy',
        'injectorSonicVelocity',
    ],

}

_KEYTOGROUP = {key: group for group, keys in _KEYGROUPS.items() for key in keys}

# Keys that only exist when the case actually defines an exit station, matching
# the legacy wrapper's behavior.
_EXITONLYKEYS = frozenset([
    'exitMach', 'exitTemperature', 'exitPressure', 'exitMolecularWeight',
    'exitGasConstant', 'exitGamma', 'exitHeatCapacity', 'exitThermalConductivity',
    'exitEnthalpy', 'exitEntropy', 'exitPrandtlNumber', 'exitViscosity',
    'expansionRatio',
])

class LazyResults(dict):

    '''
    Dictionary of CEA results whose values are computed on first access.

    Behaves like an ordinary dict for every access pattern Nozzle.py uses:
    subscripting triggers the owning group's solve, `in` reports whether a key
    is valid for the case, and any operation that enumerates the mapping
    (keys, values, items, iteration, len, copy) materializes everything first
    so callers never observe a partially populated result.
    '''

    def __init__(self, owner) -> None:
        super().__init__()
        self._owner = owner

    def __missing__(self, key: str):
        group = _KEYTOGROUP.get(key)
        if group is None or key not in self._owner.availableKeys:
            raise KeyError(key)
        self._owner.materialize(group)
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        raise KeyError(key)

    def __contains__(self, key) -> bool:
        return dict.__contains__(self, key) or key in self._owner.availableKeys

    def materializeAll(self) -> None:
        '''
        Force every group to be computed.
        '''
        for group in _KEYGROUPS:
            self._owner.materialize(group)

    def keys(self):
        self.materializeAll()
        return dict.keys(self)

    def values(self):
        self.materializeAll()
        return dict.values(self)

    def items(self):
        self.materializeAll()
        return dict.items(self)

    def __iter__(self):
        self.materializeAll()
        return dict.__iter__(self)

    def __len__(self) -> int:
        self.materializeAll()
        return dict.__len__(self)

    def get(self, key, default = None):
        try:
            return self[key]
        except KeyError:
            return default

    def copy(self) -> dict:
        self.materializeAll()
        return dict(self)

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- Main interface -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

class CEA:

    '''
    Equilibrium (or frozen) CEA solve for a propellant combination, exposed as
    the SI `ceaResults` dictionary that Nozzle.py consumes.

    Exactly one of expansionRatio, nozzleExitPressure or contractionRatio
    normally drives the case:

      expansionRatio     -- supersonic station at the given area ratio
      nozzleExitPressure -- area ratio solved to hit the given exit pressure
      contractionRatio   -- subsonic (finite area combustor) station only, in
                            which case no exit properties are produced

    Pressures in and out are Pa unless pressureUnits says otherwise. Results
    are computed lazily per group; see _KEYGROUPS.
    '''

    def __init__(self, fuelName: str = '', oxidizerName: str = '', monopropellantName: str = '',
                 oxidizerInitialTemperature: float = None,
                 chamberPressure: float = None, ambientPressure: float = 101325,
                 nozzleExitPressure: float = None, OFRatio = 'maxisp',
                 expansionRatio: float = None, contractionRatio: float = None,
                 pressureRatio: float = None,
                 frozen: bool = False, frozenAtThroat: bool = False,
                 pressureUnits: str = 'Pa', **legacyKwargs) -> None:

        # Legacy keyword arguments (equivalenceRatioOF, outputTransportProperties,
        # makeOutputFile, shortOutput, caseName, useCustomFuel, ...) are accepted
        # and ignored so the constructor stays drop-in compatible with call sites
        # written against the old wrapper.
        self.legacyKwargs = legacyKwargs

        self.fuelName                   = fuelName
        self.oxidizerName               = oxidizerName
        self.monopropellantName         = monopropellantName
        self.oxidizerInitialTemperature = oxidizerInitialTemperature
        self.expansionRatio             = expansionRatio
        self.contractionRatio           = contractionRatio
        self.pressureRatio              = pressureRatio
        self.pressureUnits              = pressureUnits
        self.gravity                    = GRAVITY
        self.universalGasConstant       = R_UNIVERSAL / 1.0e3  # J/(mol-K), legacy attribute
        self.ceaFailed                  = False

        self.frozen         = int(bool(frozen))
        self.frozenAtThroat = int(bool(frozenAtThroat))

        if chamberPressure is None:
            raise ValueError('chamberPressure is required.')

        # Normalize to Pa internally regardless of the caller's convention.
        self.pressureScale      = 1.0e5 if str(pressureUnits).lower() == 'bar' else 1.0
        self.chamberPressure    = chamberPressure * self.pressureScale
        self.ambientPressure    = ambientPressure * self.pressureScale
        self.nozzleExitPressure = None if nozzleExitPressure is None \
                                  else nozzleExitPressure * self.pressureScale

        self.fuelCanonical = resolvePropellantName(
            fuelName, FUELALIASES, CUSTOMFUELCARDS, fuelCards, 'fuel')
        oxidizerCanonical = resolvePropellantName(
            oxidizerName, OXIDIZERALIASES, CUSTOMOXIDIZERCARDS, oxCards, 'oxidizer')
        self.oxidizerCanonical = _resolveOxidizerCard(
            oxidizerCanonical, self.oxidizerInitialTemperature, self.chamberPressure)

        self.chamberPressurePsia = self.chamberPressure / PA_PER_PSIA

        self._resolveInputMode()
        self._resolveMixtureRatio(OFRatio)

        self.hasExitConditions = (expansionRatio is not None) or \
                                 (nozzleExitPressure is not None) or \
                                 (pressureRatio is not None)

        self.availableKeys = {key for key in _KEYTOGROUP
                              if self.hasExitConditions or key not in _EXITONLYKEYS}
        self.solvedGroups = set()
        self.ceaResults   = LazyResults(self)

    # -------------------------------------------------------------------------------------------------------------------------------- #
    # -- Case setup -- #
    # -------------------------------------------------------------------------------------------------------------------------------- #

    def _resolveInputMode(self) -> None:
        '''
        Translate the driving input into the finite-area-combustor contraction
        ratio that rocketcea needs, and build the solver objects.
        '''
        self.facCR = self.contractionRatio
        if self.facCR is not None and self.facCR <= 1.0 + 1.0e-6:
            # A contraction ratio of unity is the infinite-area-chamber limit,
            # where CEA's finite area combustor is degenerate.
            warnings.warn(
                f'contractionRatio={self.facCR} is at or below 1.0; falling back '
                f'to an infinite area chamber for this station.'
            )
            self.facCR = None
        self.ceaObject = _makeCeaObj(self.fuelCanonical, self.oxidizerCanonical, self.facCR)
        # Companion object with an infinite-area chamber. Without a finite
        # combustor, CEA's chamber station IS the zero-velocity stagnation state
        # at the reactant enthalpy, which is thermodynamically identical to the
        # injector face. This is how the injector-station keys are recovered,
        # since rocketcea exposes no injector-face accessor.
        self.injectorObject = _makeCeaObj(self.fuelCanonical, self.oxidizerCanonical, None)

    def _resolveMixtureRatio(self, OFRatio) -> None:
        '''
        Set self.OFRatio, running a bounded max-Isp search when the caller
        passed the string 'maxisp'.
        '''
        if not isinstance(OFRatio, str):
            self.OFRatio = float(OFRatio)
            self._resolveExpansionRatio()
            return
        if OFRatio.strip().lower() != 'maxisp':
            raise ValueError(
                f'OFRatio must be a number or the string "maxisp", got {OFRatio!r}.')
        # An expansion ratio is needed to evaluate Isp, so resolve a provisional
        # one first and fall back to a representative value when the case only
        # specifies a contraction ratio.
        self.OFRatio = 1.0
        self._resolveExpansionRatio()
        searchEps = self.epsEff if self.epsEff > MIN_SUPERSONIC_EPS else 40.0
        cacheKey = (self.fuelCanonical, self.oxidizerCanonical,
                    round(self.chamberPressurePsia, 6), round(searchEps, 6))
        if cacheKey in _MAXISPCACHE:
            self.OFRatio = _MAXISPCACHE[cacheKey]
        else:
            from scipy.optimize import minimize_scalar
            def negativeIsp(mixtureRatio: float) -> float:
                with _CEAOBJLOCK:
                    return -self.ceaObject.get_Isp(
                        Pc = self.chamberPressurePsia, MR = mixtureRatio, eps = searchEps,
                        frozen = self.frozen, frozenAtThroat = self.frozenAtThroat)
            # method='bounded' is required. The legacy wrapper omitted it, so
            # SciPy defaulted to unbounded Brent and its (0.1, 100) bounds were
            # ignored entirely. The narrower range here also avoids wasting
            # solves on mixture ratios where CEA does not converge.
            result = minimize_scalar(negativeIsp, bounds = (0.2, 15.0),
                                     method = 'bounded', options = {'xatol': 1.0e-3})
            self.OFRatio = float(result.x)
            _MAXISPCACHE[cacheKey] = self.OFRatio
        # An exit-pressure-driven area ratio depends on mixture ratio, so
        # re-solve it now that the optimum is known.
        if self.expansionRatio is None and self.nozzleExitPressure is not None:
            self._resolveExpansionRatio()

    def _resolveExpansionRatio(self) -> None:
        '''
        Determine the effective expansion ratio for this case.
        '''
        if self.expansionRatio is not None:
            self.epsEff = float(self.expansionRatio)
        elif self.nozzleExitPressure is not None or self.pressureRatio is not None:
            pressureRatio = self.pressureRatio if self.nozzleExitPressure is None \
                            else self.chamberPressure / self.nozzleExitPressure
            with _CEAOBJLOCK:
                self.epsEff = float(self.ceaObject.get_eps_at_PcOvPe(
                    Pc = self.chamberPressurePsia, MR = self.OFRatio,
                    PcOvPe = pressureRatio,
                    frozen = self.frozen, frozenAtThroat = self.frozenAtThroat))
        else:
            self.epsEff = DUMMY_EPS
        # NOVA's diverging sweep includes the throat itself, where the area
        # ratio is exactly 1.0 and the supersonic branch is undefined. Clamping
        # keeps the solve finite: the caller substitutes throat-station values
        # at that point anyway, but its NaN guard runs first, so the numbers
        # returned here must be real.
        self.atThroat = self.epsEff <= MIN_SUPERSONIC_EPS
        if self.atThroat:
            self.epsEff = MIN_SUPERSONIC_EPS

    # -------------------------------------------------------------------------------------------------------------------------------- #
    # -- Lazy group materialization -- #
    # -------------------------------------------------------------------------------------------------------------------------------- #

    def materialize(self, group: str) -> None:
        '''
        Compute one group of results, once. A failed group is filled with NaN
        rather than raising: Nozzle.py already inspects these values for NaN and
        raises a well-contexted ThermalConstraintError of its own, so failing
        softly keeps error reporting in one place and stops one bad group from
        destroying the others.
        '''
        if group in self.solvedGroups:
            return
        self.solvedGroups.add(group)
        try:
            values = getattr(self, f'_compute{group[0].upper()}{group[1:]}')()
        except Exception as error:
            warnings.warn(
                f'CEA {group} solve failed for {self.fuelCanonical}/'
                f'{self.oxidizerCanonical}: {error}')
            self.ceaFailed = True
            values = {key: np.nan for key in _KEYGROUPS[group]}
            for key in ('massFractions', 'molFractions', 'molWeights'):
                if key in values:
                    values[key] = {}
            if 'nozzlePerformance' in values:
                values['nozzlePerformance'] = None
                self._nozzlePerformance = None
        for key, value in values.items():
            if key in self.availableKeys:
                dict.__setitem__(self.ceaResults, key, value)

    def _computeTransport(self) -> dict:
        '''
        Chamber, throat and exit transport properties in SI.

        A single CEA run with transport enabled fills the trpts COMMON arrays at
        every station, so only one solve is issued and the other two stations
        are read directly by index. This was verified bit-identical to calling
        get_Chamber_Transport / get_Throat_Transport / get_Exit_Transport
        separately, at a quarter of the cost.
        '''
        import rocketcea.py_cea as py_cea
        with _CEAOBJLOCK:
            self.ceaObject.get_Exit_Transport(
                self.chamberPressurePsia, self.OFRatio, self.epsEff,
                self.frozen, self.frozenAtThroat)
            frozenFlow = bool(self.frozen)
            heatCapacityArray = py_cea.trpts.cpfro if frozenFlow else py_cea.trpts.cpeql
            conductivityArray = py_cea.trpts.confro if frozenFlow else py_cea.trpts.coneql
            prandtlArray      = py_cea.trpts.prfro if frozenFlow else py_cea.trpts.preql
            viscosityArray    = py_cea.trpts.vis
            stationIndices = (self.ceaObject.i_chm, self.ceaObject.i_thrt, self.ceaObject.i_exit)
            heatCapacity = [float(heatCapacityArray[i]) for i in stationIndices]
            conductivity = [float(conductivityArray[i]) for i in stationIndices]
            prandtl      = [float(prandtlArray[i]) for i in stationIndices]
            viscosity    = [float(viscosityArray[i]) for i in stationIndices]
        return {
            'combustionChamberHeatCapacity'        : heatCapacity[0] * CALPGK_TO_JPKGK,
            'throatHeatCapacity'                   : heatCapacity[1] * CALPGK_TO_JPKGK,
            'exitHeatCapacity'                     : heatCapacity[2] * CALPGK_TO_JPKGK,
            'combustionChamberThermalConductivity' : conductivity[0] * MCALCMKS_TO_WMK,
            'throatThermalConductivity'            : conductivity[1] * MCALCMKS_TO_WMK,
            'exitThermalConductivity'              : conductivity[2] * MCALCMKS_TO_WMK,
            'combustionChamberPrandtlNumber'       : prandtl[0],
            'throatPrandtlNumber'                  : prandtl[1],
            'exitPrandtlNumber'                    : prandtl[2],
            'combustionChamberViscosity'           : viscosity[0] * MILLIPOISE_TO_PAS,
            'throatViscosity'                      : viscosity[1] * MILLIPOISE_TO_PAS,
            'exitViscosity'                        : viscosity[2] * MILLIPOISE_TO_PAS,
        }

    def _computeMolecularWeight(self) -> dict:
        '''
        Molecular weight, gamma and the derived gas constant at each station.
        '''
        with _CEAOBJLOCK:
            chamberValues = self.ceaObject.get_Chamber_MolWt_gamma(
                self.chamberPressurePsia, self.OFRatio, self.epsEff)
            throatValues = self.ceaObject.get_Throat_MolWt_gamma(
                self.chamberPressurePsia, self.OFRatio, self.epsEff, self.frozen)
            exitValues = self.ceaObject.get_exit_MolWt_gamma(
                self.chamberPressurePsia, self.OFRatio, self.epsEff,
                self.frozen, self.frozenAtThroat)
        return {
            'combustionChamberMolecularWeight' : chamberValues[0],
            'throatMolecularWeight'            : throatValues[0],
            'exitMolecularWeight'              : exitValues[0],
            'combustionChamberGasConstant'     : R_UNIVERSAL / chamberValues[0],
            'throatGasConstant'                : R_UNIVERSAL / throatValues[0],
            'exitGasConstant'                  : R_UNIVERSAL / exitValues[0],
            'combustionChamberGamma'           : chamberValues[1],
            'throatGamma'                      : throatValues[1],
            'exitGamma'                        : exitValues[1],
        }

    def _computeThermodynamic(self) -> dict:
        '''
        Temperature, density, sonic velocity, enthalpy and entropy per station.
        '''
        pcPsia, mixtureRatio, eps = self.chamberPressurePsia, self.OFRatio, self.epsEff
        frozen, frozenAtThroat = self.frozen, self.frozenAtThroat
        with _CEAOBJLOCK:
            temperatures    = self.ceaObject.get_Temperatures(pcPsia, mixtureRatio, eps, frozen, frozenAtThroat)
            densities       = self.ceaObject.get_Densities(pcPsia, mixtureRatio, eps, frozen, frozenAtThroat)
            sonicVelocities = self.ceaObject.get_SonicVelocities(pcPsia, mixtureRatio, eps, frozen, frozenAtThroat)
            enthalpies      = self.ceaObject.get_Enthalpies(pcPsia, mixtureRatio, eps, frozen, frozenAtThroat)
            entropies       = self.ceaObject.get_Entropies(pcPsia, mixtureRatio, eps, frozen, frozenAtThroat)
            exitMach        = self.ceaObject.get_MachNumber(pcPsia, mixtureRatio, eps, frozen, frozenAtThroat)
        return {
            'combustionChamberTemperature'   : temperatures[0] * DEGR_TO_K,
            'throatTemperature'              : temperatures[1] * DEGR_TO_K,
            'exitTemperature'                : temperatures[2] * DEGR_TO_K,
            'combustionChamberDensity'       : densities[0] * LBMPFT3_TO_KGPM3,
            'throatDensity'                  : densities[1] * LBMPFT3_TO_KGPM3,
            'exitDensity'                    : densities[2] * LBMPFT3_TO_KGPM3,
            'combustionChamberSonicVelocity' : sonicVelocities[0] * FTPS_TO_MPS,
            'throatSonicVelocity'            : sonicVelocities[1] * FTPS_TO_MPS,
            'exitSonicVelocity'              : sonicVelocities[2] * FTPS_TO_MPS,
            'combustionChamberEnthalpy'      : enthalpies[0] * BTUPLBM_TO_JPKG,
            'throatEnthalpy'                 : enthalpies[1] * BTUPLBM_TO_JPKG,
            'exitEnthalpy'                   : enthalpies[2] * BTUPLBM_TO_JPKG,
            'combustionChamberEntropy'       : entropies[0] * CALPGK_TO_JPKGK,
            'throatEntropy'                  : entropies[1] * CALPGK_TO_JPKGK,
            'exitEntropy'                    : entropies[2] * CALPGK_TO_JPKGK,
            'exitVelocity'                   : sonicVelocities[2] * FTPS_TO_MPS * exitMach,
        }

    def _computePressure(self) -> dict:
        '''
        Station pressures, Mach numbers and area ratios.

        CEA's pressure ratios are all referenced to the input Pc, which it
        treats as the injector face pressure when a finite area combustor is
        active. Verified empirically: rho*R*T at the chamber station recovers
        Pc / Pinj_over_Pcomb exactly, and equals Pc exactly when facCR is None.
        '''
        pcPsia, mixtureRatio, eps = self.chamberPressurePsia, self.OFRatio, self.epsEff
        with _CEAOBJLOCK:
            throatPcOvPe = self.ceaObject.get_Throat_PcOvPe(pcPsia, mixtureRatio)
            exitPcOvPe   = self.ceaObject.get_PcOvPe(
                pcPsia, mixtureRatio, eps, self.frozen, self.frozenAtThroat)
            exitMach     = self.ceaObject.get_MachNumber(
                pcPsia, mixtureRatio, eps, self.frozen, self.frozenAtThroat)
            injectorOverChamber = self.ceaObject.get_Pinj_over_Pcomb(
                pcPsia, mixtureRatio) if self.facCR is not None else 1.0
        exitPressure = self.chamberPressure / exitPcOvPe
        if self.nozzleExitPressure is None:
            self.nozzleExitPressure = exitPressure
        if self.pressureRatio is None:
            self.pressureRatio = self.chamberPressure / self.nozzleExitPressure
        return {
            'injectionPressure'         : self.chamberPressure,
            'combustionChamberPressure' : self.chamberPressure / injectorOverChamber,
            'throatPressure'            : self.chamberPressure / throatPcOvPe,
            'exitPressure'              : exitPressure,
            'exitMach'                  : exitMach,
            # The throat is sonic by construction; CEA prints M=1.000 there and
            # get_MachNumber is branch-ambiguous at eps=1.
            'throatMach'                : 1.0,
            'expansionRatio'            : self.epsEff,
            'contractionRatio'          : float(self.facCR) if self.facCR is not None else np.nan,
            'O/F Ratio'                 : self.OFRatio,
        }

    def _computePerformance(self) -> dict:
        '''
        Characteristic velocity and the nozzle performance dictionary.
        '''
        with _CEAOBJLOCK:
            characteristicVelocity = self.ceaObject.get_Cstar(
                self.chamberPressurePsia, self.OFRatio) * FTPS_TO_MPS
        performance = self.calculateNozzlePerformance(characteristicVelocity) \
                      if self.hasExitConditions else None
        self._nozzlePerformance = performance
        return {
            'characteristicVelocity' : characteristicVelocity,
            'nozzlePerformance'      : performance,
        }

    def _computeSpecies(self) -> dict:
        '''
        Per-species mass fractions, mole fractions and molecular weights.
        '''
        massFractions, molFractions, molWeights = self.getSpeciesConcentrations(
            minFraction = 1.0e-6)
        return {
            'massFractions' : massFractions,
            'molFractions'  : molFractions,
            'molWeights'    : molWeights,
        }

    def _computeInjector(self) -> dict:
        '''
        Injector-face station properties, from the infinite-area companion
        object. Nozzle.py reads none of these, so they are only ever computed
        when a caller asks for them explicitly.
        '''
        import rocketcea.py_cea as py_cea
        pcPsia, mixtureRatio, eps = self.chamberPressurePsia, self.OFRatio, self.epsEff
        frozen, frozenAtThroat = self.frozen, self.frozenAtThroat
        with _CEAOBJLOCK:
            temperatures    = self.injectorObject.get_Temperatures(pcPsia, mixtureRatio, eps, frozen, frozenAtThroat)
            enthalpies      = self.injectorObject.get_Enthalpies(pcPsia, mixtureRatio, eps, frozen, frozenAtThroat)
            entropies       = self.injectorObject.get_Entropies(pcPsia, mixtureRatio, eps, frozen, frozenAtThroat)
            sonicVelocities = self.injectorObject.get_SonicVelocities(pcPsia, mixtureRatio, eps, frozen, frozenAtThroat)
            molWtGamma      = self.injectorObject.get_Chamber_MolWt_gamma(pcPsia, mixtureRatio, eps)
            self.injectorObject.get_Exit_Transport(pcPsia, mixtureRatio, eps, frozen, frozenAtThroat)
            heatCapacityArray = py_cea.trpts.cpfro if frozen else py_cea.trpts.cpeql
            heatCapacity = float(heatCapacityArray[self.injectorObject.i_chm])
        return {
            'injectionTemperature'    : temperatures[0] * DEGR_TO_K,
            'injectorMolecularWeight' : molWtGamma[0],
            # The 'injectonGamma' spelling is a typo carried over from the legacy
            # wrapper and preserved for drop-in compatibility.
            'injectonGamma'           : molWtGamma[1],
            'injectionHeatCapacity'   : heatCapacity * CALPGK_TO_JPKGK,
            'injectionEnthalpy'       : enthalpies[0] * BTUPLBM_TO_JPKG,
            'injectorEntropy'         : entropies[0] * CALPGK_TO_JPKGK,
            'injectorSonicVelocity'   : sonicVelocities[0] * FTPS_TO_MPS,
        }

    # -------------------------------------------------------------------------------------------------------------------------------- #
    # -- Derived quantities -- #
    # -------------------------------------------------------------------------------------------------------------------------------- #

    @property
    def nozzlePerformance(self):
        '''
        Nozzle performance dictionary, computed on first access.
        '''
        self.materialize('performance')
        return self._nozzlePerformance

    @property
    def massFractions(self) -> dict:
        self.materialize('species')
        return dict.__getitem__(self.ceaResults, 'massFractions')

    @property
    def molFractions(self) -> dict:
        self.materialize('species')
        return dict.__getitem__(self.ceaResults, 'molFractions')

    @property
    def molWeights(self) -> dict:
        self.materialize('species')
        return dict.__getitem__(self.ceaResults, 'molWeights')

    def calculateNozzlePerformance(self, characteristicVelocity: float = None) -> dict:

        '''

        Calculates nozzle performance parameters, including thrust coefficients,
        ISPs, and flow separation characteristics.

        '''

        with _CEAOBJLOCK:
            if characteristicVelocity is None:
                characteristicVelocity = self.ceaObject.get_Cstar(
                    self.chamberPressurePsia, self.OFRatio) * FTPS_TO_MPS
            vacuumIspSeconds = self.ceaObject.get_IvacCstrTc(
                Pc = self.chamberPressurePsia, MR = self.OFRatio, eps = self.epsEff,
                frozen = self.frozen, frozenAtThroat = self.frozenAtThroat)[0]
            exitMachNumber = self.ceaObject.get_MachNumber(
                self.chamberPressurePsia, self.OFRatio, self.epsEff,
                self.frozen, self.frozenAtThroat)
        # The exit pressure is resolved as a side effect of the pressure group,
        # so make sure that group has run before using it below.
        self.materialize('pressure')

        vacuumISP        = vacuumIspSeconds * GRAVITY  # m/s
        vacuumThrustCoef = vacuumISP / characteristicVelocity
        expansionRatio   = self.epsEff

        # Estimation of critical separation pressure from RPA docs
        # https://www.rocket-propulsion.com/downloads/pub/RPA_AssessmentOfDeliveredPerformance.pdf#page=16.42
        # Flow separation *may* occur if ambient pressure > critical separation pressure
        separationPressure = self.nozzleExitPressure / (1.88 * exitMachNumber - 1)**-0.64

        # Determine mode of nozzle operation
        if self.ambientPressure > separationPressure:
            mode = 'Separated'
        else:
            if self.nozzleExitPressure > self.ambientPressure * 1.05:
                mode = 'UnderExpanded'
            elif self.nozzleExitPressure < self.ambientPressure * 0.95:
                mode = 'OverExpanded'
            else:
                mode = 'Ideal'

        # NOTE every pressure below is Pa. The legacy wrapper read the exit
        # pressure out of a COMMON block in bar and subtracted it against Pa,
        # which collapsed idealThrustCoef onto vacuumThrustCoef and pinned
        # `mode` at 'UnderExpanded'. That is fixed here, so idealISP is slightly
        # lower and any thrust-driven mass flow slightly higher than before.
        seaLevelThrustCoef = vacuumThrustCoef - SEA_LEVEL_PA            * expansionRatio / self.chamberPressure
        ambientThrustCoef  = vacuumThrustCoef - self.ambientPressure    * expansionRatio / self.chamberPressure
        idealThrustCoef    = vacuumThrustCoef - self.nozzleExitPressure * expansionRatio / self.chamberPressure
        seaLevelISP        = characteristicVelocity * seaLevelThrustCoef
        ambientISP         = characteristicVelocity * ambientThrustCoef
        idealISP           = characteristicVelocity * idealThrustCoef

        return {
            'seaLevelISP[s]'      : seaLevelISP / self.gravity,
            'ambientISP[s]'       : ambientISP / self.gravity,
            'idealISP[s]'         : idealISP / self.gravity,
            'vacuumISP[s]'        : vacuumISP / self.gravity,
            'seaLevelThrustCoef'  : seaLevelThrustCoef,
            'ambientThrustCoef'   : ambientThrustCoef,
            'actualThrustCoef'    : idealThrustCoef,
            'vacuumThrustCoef'    : vacuumThrustCoef,
            'mode'                : mode
        }

    def getSpeciesConcentrations(self, minFraction: float = 5.0e-6) -> tuple:

        '''

        Returns per-species mass fractions, mole fractions and molecular weights,
        each keyed by species name and then by station.

        rocketcea reports four stations, [injector, chamber, throat, exit], which
        maps directly onto the legacy wrapper's dictionary shape. The exit entry
        is None when the case defines no exit station.

        '''

        try:
            with _CEAOBJLOCK:
                molWeights, massFracLists = self.ceaObject.get_SpeciesMassFractions(
                    self.chamberPressurePsia, self.OFRatio, self.epsEff,
                    self.frozen, self.frozenAtThroat, min_fraction = minFraction)
                _, moleFracLists = self.ceaObject.get_SpeciesMoleFractions(
                    self.chamberPressurePsia, self.OFRatio, self.epsEff,
                    self.frozen, self.frozenAtThroat, min_fraction = minFraction)
        except Exception as error:
            warnings.warn(f'Could not retrieve species concentrations: {error}')
            return {}, {}, {}

        stationNames = ['injector', 'chamber', 'throat', 'exit']

        def byStation(fractionList: list) -> dict:
            stationValues = dict(zip(stationNames, fractionList))
            if not self.hasExitConditions:
                stationValues['exit'] = None
            return stationValues

        massFractions = {species: byStation(values) for species, values in massFracLists.items()}
        molFractions  = {species: byStation(values) for species, values in moleFracLists.items()}
        return massFractions, molFractions, dict(molWeights)
