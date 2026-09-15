# -- NOVA: Units and Physical Constants -- #

'''

One unit registry, and every conversion factor in NOVA derived from it.

Everything inside NOVA is mass-base SI: meters, kilograms, seconds, kelvin, pascals, and degrees
for angles. Conversion belongs at the boundary, where a catalogue figure in psi or a MIL spec in
Btu/lbm is read, and not in the solvers. This module is that boundary.

The constants below are not transcribed. Each is computed from `ureg` at import, so a factor
cannot drift from its definition or be typed wrong, and the unit each one converts between is
written in the expression rather than in a comment beside it. Deriving them this way found two
places where a hand-entered value was ambiguous rather than wrong, both recorded below.

----------------------------------------------------------------------
                        Quantities versus magnitudes
----------------------------------------------------------------------

The solvers take and return plain floats, not `pint.Quantity` objects. A characteristic mesh runs
to hundreds of thousands of point evaluations, and unit objects in that loop buy nothing: the
arrays are all in one unit system by construction. What Pint is for here is the edge, where a
number arrives carrying a unit that is not NOVA's.

`toSI` and `fromSI` are that edge for the GUI, which stores every field in SI and displays it in
whatever the field's dropdown is set to.

----------------------------------------------------------------------
                        Validation status
----------------------------------------------------------------------

Every derived constant was checked against the literal it replaced. All agree to machine
precision except three, and each disagreement is a definition rather than an error:

  - `BTU_IT` is pinned to the International Table Btu, 1055.05585262 J, which is the definition
    NASA CEA's tables use. Pint's unqualified `Btu` is the ISO 1055.056 J, which would have moved
    Btu/lbm by 1.4e-7 relative. The ceaInterface factor this replaces was the IT value.
  - `KG_PER_M3_PER_LBM_PER_FT3` was carried as 16.018463374; the exact value is 16.0184633739601,
    a rounding difference of 2.5e-12 relative.
  - `PA_PER_INH2O` was carried as 249.0889 for water at 4 degC. The registry's 39.2 degF entry,
    the same reference temperature, gives 249.081936, a difference of 2.8e-5 relative. Nothing in
    NOVA reads this constant.

The US Standard Atmosphere model below was checked against the tabulated pressures of
NASA-TM-X-74335 at 0, 5000, 11000, 20000, 32000, 47000 and 71000 m (101325, 54019.9, 22632.06,
5474.889, 868.0187, 110.9063 and 3.956420 Pa). Worst error 2.2e-5 per cent, at 5000 m; the layer
bases are exact because they are the model's own table entries.

`utils.py` carried a second implementation of the same two functions, and the package exported
whichever import ran last. It was the less accurate of the two, drifting to 0.018 per cent by
71 km against this one's 2.2e-5, so this is the implementation that survives.

Author: Sean Bowman

'''

import numpy as np
from pint import UnitRegistry

# One registry for the whole package. Pint quantities from different registries do not
# interoperate, so anything needing a Quantity should take this one rather than build its own.
ureg = UnitRegistry()
Quantity = ureg.Quantity

def _factor(fromUnit: str, toUnit: str) -> float:

    '''Magnitude of one `fromUnit` expressed in `toUnit`.'''

    return Quantity(1.0, fromUnit).to(toUnit).magnitude

# --------------------------------------------------------------------------------------------- #
# -- Conversion factors -- #
# --------------------------------------------------------------------------------------------- #

# -- Pressure -- #
PA_PER_PSIA  = _factor('psi', 'Pa')
PA_PER_BAR   = _factor('bar', 'Pa')
PA_PER_ATM   = _factor('atm', 'Pa')
PA_PER_TORR  = _factor('torr', 'Pa')
PA_PER_MBAR  = _factor('mbar', 'Pa')
PA_PER_INH2O = _factor('inch_H2O_39F', 'Pa')   # water at 39.2 degF, which is 4 degC

# -- Length, area, volume -- #
M_PER_IN     = _factor('inch', 'm')
M_PER_FT     = _factor('foot', 'm')
M_PER_MIL    = _factor('thou', 'm')
M_PER_MICRON = _factor('micron', 'm')
M3_PER_FT3   = _factor('foot ** 3', 'm ** 3')
M3_PER_L     = _factor('liter', 'm ** 3')
M3_PER_GAL   = _factor('gallon', 'm ** 3')

# -- Mass, force, torque -- #
KG_PER_LBM   = _factor('pound', 'kg')
N_PER_LBF    = _factor('force_pound', 'N')
NM_PER_INLBF = _factor('force_pound * inch', 'N * m')
NM_PER_FTLBF = _factor('force_pound * foot', 'N * m')

# -- Temperature -- #
# Rankine to kelvin is a ratio of interval sizes, so it applies to differences and to absolute
# temperatures alike. Fahrenheit and Celsius are affine and are handled by `toSI` instead.
K_PER_DEGR  = _factor('rankine', 'kelvin')
DEGC_OFFSET = Quantity(0.0, 'degC').to('kelvin').magnitude

# -- Thermochemistry, as CEA reports it -- #
# CEA output is imperial. Btu/lbm and cal/g differ by a factor of 1.8 while Btu/(lbm-degR) and
# cal/(g-K) are numerically identical, which is the classic way to be wrong here by exactly that
# factor. A validation discrepancy near 1.8, 4.184 or 9.81 is a unit error in this block.
BTU_IT                    = _factor('Btu_it', 'J')
J_PER_KG_PER_BTU_PER_LBM  = _factor('Btu_it / pound', 'J / kg')
J_PER_KG_K_PER_CAL_PER_GK = _factor('cal / (gram * kelvin)', 'J / (kg * kelvin)')
KG_PER_M3_PER_LBM_PER_FT3 = _factor('pound / foot ** 3', 'kg / m ** 3')
PA_S_PER_MILLIPOISE       = _factor('millipoise', 'Pa * s')
W_PER_M_K_PER_MCAL_CM_S_K = _factor('millical / (cm * s * kelvin)', 'W / (m * kelvin)')
M_PER_S_PER_FT_PER_S      = _factor('foot / s', 'm / s')

# --------------------------------------------------------------------------------------------- #
# -- Physical constants -- #
# --------------------------------------------------------------------------------------------- #

GRAVITY          = _factor('standard_gravity', 'm / s ** 2')
STEFAN_BOLTZMANN = _factor('stefan_boltzmann_constant', 'W / (m ** 2 * kelvin ** 4)')
SECONDS_PER_YEAR = _factor('julian_year', 's')

# The universal gas constant appears in NOVA on two mole bases, and carrying one name for both is
# how they get mixed. CEA reports molecular weight in g/mol and gas constants per kilomole, while
# everything else here is per mole.
R_UNIVERSAL_MOLAR = _factor('molar_gas_constant', 'J / (mol * kelvin)')
R_UNIVERSAL_KMOL  = _factor('molar_gas_constant', 'J / (kmol * kelvin)')

# The 1976 standard atmosphere is a defined model, not a measurement, and it is defined with the
# gas constant of its day: R* = 8.31432 J/(mol-K), against today's 8.314462618. Rebuilding the air
# constant from the current value instead shifts the profile by about 1e-5 relative, which is
# enough to stop the model reproducing its own published table. The 1976 value is therefore used
# here, and only here.
R_UNIVERSAL_USSA76 = 8.31432                                # J/mol-K, as USSA76 defines it
MOLAR_MASS_AIR     = 28.9644e-3                             # kg/mol, as USSA76 defines it
GAS_CONSTANT_AIR   = R_UNIVERSAL_USSA76 / MOLAR_MASS_AIR    # J/kg-K, 287.05287

# -- Standard reference states -- #
# Two different 'standard' states are in circulation and mixing them is a classic sizing error.
# Leak rates and sccm/sccs use the vacuum-industry standard (0 degC, 1 atm). SCFM in the US gas
# industry uses 60 degF, 1 atm. Both are carried explicitly so neither is assumed by accident.
LEAK_STD_TEMPERATURE = Quantity(0.0, 'degC').to('kelvin').magnitude
LEAK_STD_PRESSURE    = PA_PER_ATM
SCFM_STD_TEMPERATURE = Quantity(60.0, 'degF').to('kelvin').magnitude
SCFM_STD_PRESSURE    = PA_PER_ATM

# Cv (US, gpm water at 1 psi) to Kv (metric, m3/h water at 1 bar). This one is a flow coefficient
# convention rather than a unit conversion, so it stays a literal.
KV_PER_CV = 0.8646
CV_PER_KV = 1.0 / KV_PER_CV

# --------------------------------------------------------------------------------------------- #
# -- The display boundary -- #
# --------------------------------------------------------------------------------------------- #

# What a field of each dimension is stored as, and what it may be displayed in. The SI slot is the
# unit the solvers expect; it is listed first in a dropdown.
#
# 'lengthInch' is the one place NOVA's SI-internally rule is deliberately broken. Grayloc seal
# diameters reach the volute solver in inches, so inches is the storage unit for those two fields.
DIMENSIONS = {
    'length':      {'si': 'm',    'units': ('m', 'mm', 'cm', 'in', 'ft')},
    'lengthInch':  {'si': 'in',   'units': ('in', 'mm', 'cm')},
    'pressure':    {'si': 'Pa',   'units': ('Pa', 'kPa', 'MPa', 'bar', 'psi', 'atm', 'torr')},
    'force':       {'si': 'N',    'units': ('N', 'kN', 'MN', 'lbf')},
    'temperature': {'si': 'K',    'units': ('K', 'degC', 'degR', 'degF')},
    'angle':       {'si': 'deg',  'units': ('deg', 'rad')},
    'massFlow':    {'si': 'kg/s', 'units': ('kg/s', 'g/s', 'lbm/s', 't/h')},
}

# The schema writes a field's unit as a short string; this is what each one means.
UNIT_TO_DIMENSION = {
    'm':    'length',
    'in':   'lengthInch',
    'Pa':   'pressure',
    'N':    'force',
    'K':    'temperature',
    'deg':  'angle',
    'kg/s': 'massFlow',
}

# Display names as the registry spells them. Only the entries that differ need to appear.
_registryName = {
    'lbf':   'force_pound',
    'lbm/s': 'pound / s',
    't/h':   'metric_ton / hour',
    'psi':   'psi',
    'in':    'inch',
    'ft':    'foot',
    'deg':   'degree',
    'rad':   'radian',
}

def _asRegistryUnit(unit: str) -> str:

    '''The registry's name for a display unit.'''

    return _registryName.get(unit, unit)

def dimensionForUnit(unitString: str):

    '''

    Dimension name for a schema field's declared unit, or None if the field is dimensionless.

    '''

    return UNIT_TO_DIMENSION.get(unitString)

def unitsFor(dimension: str) -> list:

    '''

    Ordered list of display-unit names for a dimension, SI unit first.

    '''

    return list(DIMENSIONS[dimension]['units'])

def siUnit(dimension: str) -> str:

    '''

    The unit a dimension is stored and handed to the solvers in.

    '''

    return DIMENSIONS[dimension]['si']

def toSI(value: float, dimension: str, unit: str) -> float:

    '''

    Convert a displayed value to the unit the solvers expect.

    Temperature is affine, so this is a conversion rather than a scaling; the registry handles
    both without the caller having to know which it is dealing with.

    Parameters:
    -----------
    value : float
        The number as displayed.
    dimension : str
        A key of DIMENSIONS.
    unit : str
        A display unit listed for that dimension.

    Returns:
    --------
    float
        The same physical quantity in the dimension's SI unit.

    '''

    target = DIMENSIONS[dimension]['si']
    if unit == target:
        return value

    return Quantity(value, _asRegistryUnit(unit)).to(_asRegistryUnit(target)).magnitude

def fromSI(value: float, dimension: str, unit: str) -> float:

    '''

    Convert a stored SI value to a chosen display unit. The inverse of `toSI`.

    '''

    source = DIMENSIONS[dimension]['si']
    if unit == source:
        return value

    return Quantity(value, _asRegistryUnit(source)).to(_asRegistryUnit(unit)).magnitude

# --------------------------------------------------------------------------------------------- #
# -- Standard Atmosphere -- #
# --------------------------------------------------------------------------------------------- #

# US Standard Atmosphere 1976 layer bases: geopotential altitude [m], temperature [K],
# pressure [Pa], lapse rate [K/m]. Seven layers, sea level to 84.852 km.
_BASE_ALTITUDE    = np.array([0.0, 11000.0, 20000.0, 32000.0, 47000.0, 51000.0, 71000.0])
_BASE_TEMPERATURE = np.array([288.15, 216.65, 216.65, 228.65, 270.65, 270.65, 214.65])
_BASE_PRESSURE    = np.array([101325.0, 22632.06, 5474.889, 868.0187, 110.9063, 66.93887, 3.956420])
_LAPSE_RATE       = np.array([-0.0065, 0.0, 0.001, 0.0028, 0.0, -0.0028, -0.002])

def convertPressureToAltitude(pressure: float | np.ndarray) -> float | np.ndarray:

    '''

    Geopotential altitude [m] from ambient pressure [Pa] using the US Standard Atmosphere 1976.

    Used for setting the ambient back-pressure on vent and relief sizing, and for the altitude
    compensation term in nozzle performance.

    '''

    pressureArray = np.atleast_1d(np.asarray(pressure, dtype = float))
    altitude = np.zeros_like(pressureArray)

    for index, localPressure in enumerate(pressureArray):

        # Pressure decreases monotonically with altitude, so the layer is found on the negated
        # base pressures.
        layer = int(np.searchsorted(-_BASE_PRESSURE, -localPressure, side = 'right') - 1)
        layer = max(0, min(layer, len(_BASE_ALTITUDE) - 1))

        if _LAPSE_RATE[layer] == 0.0:
            # Isothermal layer: exponential pressure profile.
            altitude[index] = _BASE_ALTITUDE[layer] - (GAS_CONSTANT_AIR * _BASE_TEMPERATURE[layer]
                                                       / GRAVITY) \
                              * np.log(localPressure / _BASE_PRESSURE[layer])
        else:
            # Gradient layer: power-law pressure profile.
            exponent = -_LAPSE_RATE[layer] * GAS_CONSTANT_AIR / GRAVITY
            altitude[index] = _BASE_ALTITUDE[layer] + (_BASE_TEMPERATURE[layer]
                                                       / _LAPSE_RATE[layer]) \
                              * ((localPressure / _BASE_PRESSURE[layer])**exponent - 1.0)

    return altitude[0] if np.isscalar(pressure) or np.ndim(pressure) == 0 else altitude

def convertAltitudeToPressure(altitude: float | np.ndarray) -> float | np.ndarray:

    '''

    Ambient pressure [Pa] from geopotential altitude [m] using the US Standard Atmosphere 1976.

    The inverse of convertPressureToAltitude, over the same seven layers.

    '''

    altitudeArray = np.atleast_1d(np.asarray(altitude, dtype = float))
    pressure = np.zeros_like(altitudeArray)

    for index, localAltitude in enumerate(altitudeArray):

        layer = int(np.searchsorted(_BASE_ALTITUDE, localAltitude, side = 'right') - 1)
        layer = max(0, min(layer, len(_BASE_ALTITUDE) - 1))

        deltaAltitude = localAltitude - _BASE_ALTITUDE[layer]

        if _LAPSE_RATE[layer] == 0.0:
            pressure[index] = _BASE_PRESSURE[layer] * np.exp(-GRAVITY * deltaAltitude
                                                             / (GAS_CONSTANT_AIR
                                                                * _BASE_TEMPERATURE[layer]))
        else:
            localTemperature = _BASE_TEMPERATURE[layer] + _LAPSE_RATE[layer] * deltaAltitude
            exponent = -GRAVITY / (_LAPSE_RATE[layer] * GAS_CONSTANT_AIR)
            pressure[index] = _BASE_PRESSURE[layer] \
                              * (localTemperature / _BASE_TEMPERATURE[layer])**exponent

    return pressure[0] if np.isscalar(altitude) or np.ndim(altitude) == 0 else pressure

__all__ = [
    'ureg', 'Quantity',
    # Pressure
    'PA_PER_PSIA', 'PA_PER_BAR', 'PA_PER_ATM', 'PA_PER_TORR', 'PA_PER_MBAR', 'PA_PER_INH2O',
    # Length, area, volume
    'M_PER_IN', 'M_PER_FT', 'M_PER_MIL', 'M_PER_MICRON', 'M3_PER_FT3', 'M3_PER_L', 'M3_PER_GAL',
    # Mass, force, torque
    'KG_PER_LBM', 'N_PER_LBF', 'NM_PER_INLBF', 'NM_PER_FTLBF',
    # Temperature
    'K_PER_DEGR', 'DEGC_OFFSET',
    # Thermochemistry
    'BTU_IT', 'J_PER_KG_PER_BTU_PER_LBM', 'J_PER_KG_K_PER_CAL_PER_GK',
    'KG_PER_M3_PER_LBM_PER_FT3', 'PA_S_PER_MILLIPOISE', 'W_PER_M_K_PER_MCAL_CM_S_K',
    'M_PER_S_PER_FT_PER_S',
    # Constants
    'GRAVITY', 'STEFAN_BOLTZMANN', 'SECONDS_PER_YEAR', 'GAS_CONSTANT_AIR',
    'R_UNIVERSAL_USSA76', 'MOLAR_MASS_AIR',
    'R_UNIVERSAL_MOLAR', 'R_UNIVERSAL_KMOL',
    # Reference states and flow coefficients
    'LEAK_STD_TEMPERATURE', 'LEAK_STD_PRESSURE', 'SCFM_STD_TEMPERATURE', 'SCFM_STD_PRESSURE',
    'KV_PER_CV', 'CV_PER_KV',
    # Display boundary
    'DIMENSIONS', 'UNIT_TO_DIMENSION', 'dimensionForUnit', 'unitsFor', 'siUnit', 'toSI', 'fromSI',
    # Atmosphere
    'convertPressureToAltitude', 'convertAltitudeToPressure',
]
