# -- Unit registry and standard atmosphere tests -- #

'''

Checks on NOVA's conversion factors and its US Standard Atmosphere model.

The factors are derived from a Pint registry rather than typed, so what is worth testing is not
arithmetic but definition: that each constant is the unit it claims to be, that the ambiguous
ones are pinned to the convention NOVA's sources use, and that the display boundary round-trips.

The atmosphere is validated against the tabulated pressures of the US Standard Atmosphere 1976,
NASA-TM-X-74335, which is an independent reference rather than another implementation.

'''

import os
import sys

import numpy as np
import pytest

from NOVA import units

# --------------------------------------------------------------------------------------------- #
# -- Conversion factors against their definitions -- #
# --------------------------------------------------------------------------------------------- #

# Each factor and the exact value its definition gives. These are definitions, not measurements,
# so they are checked to machine precision.
exactFactors = (
    ('PA_PER_PSIA',   units.PA_PER_PSIA,   6894.757293168361),
    ('PA_PER_BAR',    units.PA_PER_BAR,    1.0e5),
    ('PA_PER_ATM',    units.PA_PER_ATM,    101325.0),
    ('PA_PER_TORR',   units.PA_PER_TORR,   133.32236842105263),
    ('M_PER_IN',      units.M_PER_IN,      0.0254),
    ('M_PER_FT',      units.M_PER_FT,      0.3048),
    ('M_PER_MIL',     units.M_PER_MIL,     2.54e-5),
    ('M3_PER_FT3',    units.M3_PER_FT3,    0.028316846592),
    ('M3_PER_GAL',    units.M3_PER_GAL,    3.785411784e-3),
    ('KG_PER_LBM',    units.KG_PER_LBM,    0.45359237),
    ('N_PER_LBF',     units.N_PER_LBF,     4.4482216152605),
    ('NM_PER_INLBF',  units.NM_PER_INLBF,  0.1129848290276167),
    ('NM_PER_FTLBF',  units.NM_PER_FTLBF,  1.3558179483314004),
    ('K_PER_DEGR',    units.K_PER_DEGR,    5.0 / 9.0),
    ('DEGC_OFFSET',   units.DEGC_OFFSET,   273.15),
    ('GRAVITY',       units.GRAVITY,       9.80665),
)

@pytest.mark.parametrize('name, derived, defined', exactFactors)
def testFactorMatchesItsDefinition(name, derived, defined):

    '''Every factor is the exact ratio its two units define.'''

    assert derived == pytest.approx(defined, rel = 1e-12), name

def testBtuIsTheInternationalTableDefinition():

    '''

    CEA's tables use the International Table Btu, 1055.05585262 J. Pint's unqualified `Btu` is
    the ISO 1055.056 J, which differs by 1.4e-7 relative. Btu/lbm therefore has to come out at
    exactly 2326 J/kg, which is the IT definition and the value ceaInterface converts enthalpies
    with.

    '''

    assert units.BTU_IT == pytest.approx(1055.05585262, rel = 1e-12)
    assert units.J_PER_KG_PER_BTU_PER_LBM == pytest.approx(2326.0, rel = 1e-12)

def testTheCalorieBasedFactorsAreNotTheBtuOnes():

    '''

    The trap this block exists to avoid: Btu/(lbm-degR) and cal/(g-K) are near enough identical
    to look interchangeable, while Btu/lbm and cal/g differ by about 1.8. Enthalpies are
    Btu-based, heat capacities cal-based, and confusing them shows up as an error of roughly that
    factor.

    The ratio is 1.7988 rather than 1.8 because the two constants are on different definitions:
    the calorie here is the thermochemical one, 4.184 J, while the Btu is the International Table
    one. That is what CEA reports and what the original hand-entered factors carried, so it is
    kept rather than made self-consistent.

    '''

    assert units.J_PER_KG_K_PER_CAL_PER_GK == pytest.approx(4184.0, rel = 1e-12)

    ratio = units.J_PER_KG_K_PER_CAL_PER_GK / units.J_PER_KG_PER_BTU_PER_LBM
    assert ratio == pytest.approx(1.7988, abs = 1e-4)
    assert units.J_PER_KG_K_PER_CAL_PER_GK != units.J_PER_KG_PER_BTU_PER_LBM

def testTheTwoGasConstantsAreOnDifferentMoleBases():

    '''

    Both were once exported as R_UNIVERSAL, one per mole and one per kilomole, and which one a
    caller got depended on import order. They now have distinct names and differ by exactly 1000.

    '''

    assert units.R_UNIVERSAL_KMOL / units.R_UNIVERSAL_MOLAR == pytest.approx(1000.0, rel = 1e-12)
    assert units.R_UNIVERSAL_MOLAR == pytest.approx(8.314462618, rel = 1e-10)

def testTheAtmosphereUsesItsOwnGasConstant():

    '''

    USSA76 is a defined model built on the gas constant of its day, 8.31432 J/(mol-K). Rebuilding
    the air constant from the current CODATA value shifts the pressure profile enough to stop the
    model reproducing its own published table.

    '''

    assert units.R_UNIVERSAL_USSA76 == 8.31432
    assert units.R_UNIVERSAL_USSA76 != units.R_UNIVERSAL_MOLAR
    assert units.GAS_CONSTANT_AIR == pytest.approx(287.053, abs = 0.001)

def testStandardReferenceStatesAreDistinct():

    '''

    Leak rates use 0 degC and SCFM uses 60 degF. Assuming one where the other applies is a sizing
    error of about 5 per cent in density.

    '''

    assert units.LEAK_STD_TEMPERATURE == pytest.approx(273.15, rel = 1e-12)
    assert units.SCFM_STD_TEMPERATURE == pytest.approx(288.7055556, rel = 1e-7)

# --------------------------------------------------------------------------------------------- #
# -- The general conversion -- #
# --------------------------------------------------------------------------------------------- #

# Pairs whose answer is fixed by a definition rather than by a measurement, so the expected value
# can be written down exactly. The tolerance is the width of the definition, not of the method.
definedConversions = (
    ('pressure, psi to Pa',       1.0,      'psi',   'Pa',    6894.757293168361),
    ('pressure, bar to Pa',       1.0,      'bar',   'Pa',    100000.0),
    ('pressure, MPa to Pa',       1.0,      'MPa',   'Pa',    1000000.0),
    ('length, inch to metre',     1.0,      'in',    'm',     0.0254),
    ('length, foot to metre',     1.0,      'ft',    'm',     0.3048),
    ('force, lbf to newton',      1.0,      'lbf',   'N',     4.4482216152605),
    ('mass flow, lbm/s to kg/s',  1.0,      'lbm/s', 'kg/s',  0.45359237),
    ('mass flow, t/h to kg/s',    3.6,      't/h',   'kg/s',  1.0),
    ('angle, degree to radian',   180.0,    'deg',   'rad',   np.pi),
    ('temperature, degC to K',    0.0,      'degC',  'K',     273.15),
    ('temperature, degF to K',    32.0,     'degF',  'K',     273.15),
    ('temperature, degR to K',    491.67,   'degR',  'K',     273.15),
)

@pytest.mark.parametrize('name, value, currentlyIs, shouldBe, expected', definedConversions)
def testConvertMatchesTheDefinition(name, value, currentlyIs, shouldBe, expected):

    '''Each pair is fixed by a definition, so the answer is exact to within the float.'''

    assert units.convert(value, currentlyIs, shouldBe) == pytest.approx(expected, rel = 1e-12), name

@pytest.mark.parametrize('name, value, currentlyIs, shouldBe, expected', definedConversions)
def testConvertInvertsItself(name, value, currentlyIs, shouldBe, expected):

    '''Converting back returns the value that went in, affine pairs included.'''

    there = units.convert(value, currentlyIs, shouldBe)
    back  = units.convert(there, shouldBe, currentlyIs)

    assert back == pytest.approx(value, abs = 1e-9), name

def testConvertReturnsTheSameObjectForANoOp():

    '''

    A conversion between one unit and itself has to be exact rather than reconstructed. Sending it
    through the registry would return an equal float built from a new computation, and would copy
    an array rather than hand back the one that was passed.

    '''

    assert units.convert(7.0, 'Pa', 'Pa') == 7.0

    array = np.array([1.0, 2.0, 3.0])
    assert units.convert(array, 'm', 'm') is array

def testConvertAcceptsNovaDisplaySpellings():

    '''

    The display names are NOVA's, not the registry's: 'lbf' is `force_pound`, 'lbm/s' is
    `pound / s`, 't/h' is `metric_ton / hour`, 'in' is `inch` and 'deg' is `degree`. A conversion
    that skipped the translation would raise on every one of them.

    '''

    for unit, dimension in (('lbf', 'force'), ('lbm/s', 'massFlow'), ('t/h', 'massFlow'),
                            ('in', 'length'), ('ft', 'length'), ('deg', 'angle'),
                            ('rad', 'angle')):
        si = units.siUnit(dimension)
        assert units.convert(units.convert(1.0, unit, si), si, unit) == pytest.approx(1.0,
                                                                                      rel = 1e-12)

def testConvertWorksBeyondTheDisplayDimensions():

    '''

    The reason for a unit-to-unit entry point rather than a dimension-driven one. Energy per mass,
    dynamic viscosity and thermal conductivity all reach NOVA from CEA in US customary units, and
    none of them has a DIMENSIONS entry to name.

    '''

    assert units.convert(1.0, 'Btu/lb', 'J/kg') == pytest.approx(units.J_PER_KG_PER_BTU_PER_LBM,
                                                                 rel = 1e-6)
    assert units.convert(1.0, 'millipoise', 'Pa*s') == pytest.approx(units.PA_S_PER_MILLIPOISE,
                                                                     rel = 1e-12)
    assert units.convert(1.0, 'lb/ft**3', 'kg/m**3') == pytest.approx(
        units.KG_PER_M3_PER_LBM_PER_FT3, rel = 1e-12)

def testConvertRefusesUnitsThatMeasureDifferentThings():

    '''A pressure is not a length, and asking for one in the other is an error, not a number.'''

    import pint

    with pytest.raises(pint.DimensionalityError):
        units.convert(1.0, 'Pa', 'm')

    with pytest.raises(pint.UndefinedUnitError):
        units.convert(1.0, 'Pa', 'notAUnit')

def testConvertCarriesArraysThrough():

    '''Conversion at the boundary is as likely to meet a column of numbers as a single one.'''

    psia = np.array([0.0, 14.6959487755, 1000.0])
    pascals = units.convert(psia, 'psi', 'Pa')

    assert isinstance(pascals, np.ndarray)
    assert pascals[0] == pytest.approx(0.0, abs = 1e-12)
    assert pascals[1] == pytest.approx(101325.0, rel = 1e-9)
    assert pascals[2] == pytest.approx(units.PA_PER_PSIA * 1000.0, rel = 1e-12)

# --------------------------------------------------------------------------------------------- #
# -- The display boundary -- #
# --------------------------------------------------------------------------------------------- #

everyDisplayUnit = [(dimension, unit)
                    for dimension, table in units.DIMENSIONS.items()
                    for unit in table['units']]

@pytest.mark.parametrize('dimension, unit', everyDisplayUnit)
def testDisplayConversionRoundTrips(dimension, unit):

    '''A value converted to SI and back is the value that went in, affine units included.'''

    for value in (0.0, 1.0, -3.5, 1234.5):
        stored = units.toSI(value, dimension, unit)
        assert units.fromSI(stored, dimension, unit) == pytest.approx(value, abs = 1e-9)

@pytest.mark.parametrize('dimension', sorted(units.DIMENSIONS))
def testTheSiUnitIsListedFirstAndConvertsToItself(dimension):

    '''The storage unit heads its own dropdown and is a no-op conversion.'''

    si = units.siUnit(dimension)

    assert units.unitsFor(dimension)[0] == si
    assert units.toSI(7.0, dimension, si) == 7.0

def testTemperatureIsAffineNotScaled():

    '''

    The one dimension where treating a conversion as a scale factor is wrong. 0 degC is 273.15 K,
    not 0 K.

    '''

    assert units.toSI(0.0, 'temperature', 'degC') == pytest.approx(273.15)
    assert units.toSI(0.0, 'temperature', 'degF') == pytest.approx(255.372222, abs = 1e-5)
    assert units.toSI(491.67, 'temperature', 'degR') == pytest.approx(273.15, abs = 1e-6)

def testGraylocFieldsAreStoredInInches():

    '''

    The one place the SI-internally rule is deliberately broken: the volute solver takes Grayloc
    seal diameters in inches, so inches is the storage unit for that dimension.

    '''

    assert units.siUnit('lengthInch') == 'in'
    assert units.dimensionForUnit('in') == 'lengthInch'
    assert units.toSI(25.4, 'lengthInch', 'mm') == pytest.approx(1.0, rel = 1e-12)

def testEverySchemaUnitResolvesToADimension():

    '''Each short unit string the config schema writes names a dimension that exists.'''

    for unitString, dimension in units.UNIT_TO_DIMENSION.items():
        assert dimension in units.DIMENSIONS, unitString
        assert unitString in units.DIMENSIONS[dimension]['units']

@pytest.mark.parametrize('dimension, unit', everyDisplayUnit)
def testTheDisplayBoundaryAgreesWithTheGeneralConversion(dimension, unit):

    '''

    `toSI` and `fromSI` delegate to `convert`, so they cannot answer differently. This is the
    guard on that delegation: if one of them grows an implementation of its own, the two drift
    and this fails.

    '''

    si = units.siUnit(dimension)

    for value in (0.0, 1.0, -3.5, 1234.5):
        assert units.toSI(value, dimension, unit) == units.convert(value, unit, si)
        assert units.fromSI(value, dimension, unit) == units.convert(value, si, unit)

# --------------------------------------------------------------------------------------------- #
# -- US Standard Atmosphere 1976 -- #
# --------------------------------------------------------------------------------------------- #

# Tabulated geopotential altitude [m] and pressure [Pa] from NASA-TM-X-74335. The six layer bases
# plus one interior point, so the test covers both gradient and isothermal layers.
atmosphereReference = (
    (0.0,     101325.0),
    (5000.0,  54019.9),
    (11000.0, 22632.06),
    (20000.0, 5474.889),
    (32000.0, 868.0187),
    (47000.0, 110.9063),
    (71000.0, 3.956420),
)

@pytest.mark.parametrize('altitude, pressure', atmosphereReference)
def testAtmospherePressureMatchesTheStandardTable(altitude, pressure):

    '''Pressure at altitude against the published table, to 0.001 per cent.'''

    assert units.convertAltitudeToPressure(altitude) == pytest.approx(pressure, rel = 1e-5)

@pytest.mark.parametrize('altitude, pressure', atmosphereReference)
def testAtmosphereAltitudeMatchesTheStandardTable(altitude, pressure):

    '''The inverse, altitude from pressure, against the same table.'''

    assert units.convertPressureToAltitude(pressure) == pytest.approx(altitude, abs = 1.0)

@pytest.mark.parametrize('altitude', [0.0, 500.0, 8000.0, 15000.0, 25000.0, 40000.0, 60000.0])
def testAtmosphereRoundTrips(altitude):

    '''Altitude to pressure and back, including inside every layer rather than only at bases.'''

    pressure = units.convertAltitudeToPressure(altitude)
    assert units.convertPressureToAltitude(pressure) == pytest.approx(altitude, abs = 1e-6)

def testAtmosphereAcceptsArrays():

    '''Both directions are vectorised, because the plume sweeps a range of back-pressures.'''

    altitudes = np.array([0.0, 10000.0, 30000.0])
    pressures = units.convertAltitudeToPressure(altitudes)

    assert isinstance(pressures, np.ndarray)
    assert pressures.shape == altitudes.shape
    assert np.all(np.diff(pressures) < 0)

def testAtmosphereIsMonotonic():

    '''Pressure falls with altitude everywhere, across every layer boundary.'''

    altitudes = np.linspace(0.0, 80000.0, 400)
    pressures = units.convertAltitudeToPressure(altitudes)

    assert np.all(np.diff(pressures) < 0)

# --------------------------------------------------------------------------------------------- #
# -- The registry is shared -- #
# --------------------------------------------------------------------------------------------- #

def testOneRegistryForThePackage():

    '''

    Pint quantities from different registries do not interoperate, so anything building a
    Quantity has to use the package's registry rather than its own.

    '''

    from NOVA import ureg, Quantity

    assert ureg is units.ureg
    assert Quantity(1.0, 'm').to('mm').magnitude == pytest.approx(1000.0)

def testCeaInterfaceFactorsComeFromTheRegistry():

    '''

    ceaInterface carried its own copy of these, and one of them, R_UNIVERSAL, was defined twice
    across the package on different mole bases. The conversions now come from one place.

    '''

    from NOVA import ceaInterface

    assert ceaInterface.PA_PER_PSIA is units.PA_PER_PSIA
    assert ceaInterface.DEGR_TO_K is units.K_PER_DEGR
    assert ceaInterface.MILLIPOISE_TO_PAS is units.PA_S_PER_MILLIPOISE
    assert ceaInterface.SEA_LEVEL_PA is units.PA_PER_ATM

def testCeaGasConstantStaysMatchedToCea():

    '''

    ceaInterface's R_UNIVERSAL is deliberately not the registry's. It is the value CEA itself
    works in, chosen so that rho * R * T recovers the input chamber pressure exactly against
    rocketcea's own output. Matching the wrapped tool matters more here than matching CODATA.

    '''

    from NOVA import ceaInterface

    assert ceaInterface.R_UNIVERSAL == 8314.46
    assert ceaInterface.R_UNIVERSAL != units.R_UNIVERSAL_KMOL
