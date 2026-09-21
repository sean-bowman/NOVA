# -- Tests for the Wall Material Property Module -- #

'''

Validation and behavior tests for src/NOVA/materials.py.

The thermal conductivity curves are checked at reference temperatures against the values in
their cited sources, and the error is quantified. Room-temperature pure-copper and austenitic
stainless conductivities are textbook quantities; the copper alloys (GRCop-42, CuCrZr) are held
to a wider band because published values scatter with heat treatment and measurement method.

Author: Sean Bowman
Date:   08/28/2026

'''

import os
import sys
import warnings

import numpy as np
import pytest

from NOVA.materials import (propertyIsMeasured, propertyProvenance, wallMaterialCurves, sampleWallMaterial, availableWallMaterials,
                       resolveWallMaterialName, materialProperties, roughnessTable)

def _conductivityAt(material: str, temperatureKelvin: float) -> float:

    '''

    Thermal conductivity [W/m-K] of a wall alloy at a temperature, by linear interpolation on
    its published grid.

    '''

    curves = wallMaterialCurves(material)
    return float(np.interp(temperatureKelvin, curves['temperatureK'], curves['thermalConductivity']))

# -- Reference points: (material, temperature [K], expected k [W/m-K], tolerance [fraction]) -- #

_CONDUCTIVITY_REFERENCES = [
    # Pure copper, Touloukian TPRC / CRC Handbook. Well established.
    ('OFHC Copper', 293.15, 391.0, 0.03),
    ('OFHC Copper', 573.15, 377.0, 0.04),
    ('OFHC Copper', 873.15, 350.0, 0.05),
    # Austenitic stainless, ASM Handbook Vol 1 / Touloukian.
    ('316L', 293.15, 14.6, 0.10),
    ('316L', 773.15, 20.9, 0.10),
    # Ti-6Al-4V annealed, ASM Handbook Vol 2 / MMPDS.
    ('Ti-6Al-4V', 293.15, 6.7, 0.08),
    ('Ti-6Al-4V', 773.15, 12.6, 0.15),
    # Inconel 625, Special Metals datasheet (grid nodes at 70, 1000, 1400 degF).
    ('Inconel 625', 294.15, 9.8, 0.06),
    ('Inconel 625', 811.15, 17.5, 0.08),
    ('Inconel 625', 1033.15, 20.8, 0.08),
    # Inconel 718, Special Metals datasheet.
    ('Inconel 718', 298.15, 11.4, 0.10),
    ('Inconel 718', 1073.15, 24.0, 0.10),
    # GRCop-42, NASA typical average summary. Wider band: published copper-alloy k scatters.
    ('GRCop-42', 298.15, 290.0, 0.08),
    ('GRCop-42', 773.15, 300.0, 0.10),
    # CuCrZr solution treated and aged, ITER Material Properties Handbook.
    ('CuCrZr', 293.15, 320.0, 0.10),
]

@pytest.mark.parametrize('material, temperature, expected, tolerance', _CONDUCTIVITY_REFERENCES)
def testConductivityAgainstReference(material, temperature, expected, tolerance):

    '''

    Each conductivity curve reproduces its cited source within the stated tolerance.

    '''

    actual = _conductivityAt(material, temperature)
    relativeError = abs(actual - expected) / expected
    assert relativeError <= tolerance, (
        f'{material} k({temperature:.0f} K) = {actual:.1f} W/m-K, '
        f'expected {expected:.1f} +/- {tolerance * 100:.0f}% (error {relativeError * 100:.1f}%)'
    )

def testAliasAndCaseInsensitivity():

    for alias in ('GRCop-42', 'grcop42', 'GRCOP 42', 'copper'):
        assert resolveWallMaterialName(alias) == 'GRCop-42'
    for alias in ('cucrzr', 'C18150', 'Cu-Cr-Zr'):
        assert resolveWallMaterialName(alias) == 'CuCrZr'

def testUnknownMaterialFallsBackWithWarning():

    with pytest.warns(UserWarning):
        curves = wallMaterialCurves('vibranium')
    assert curves['material'] == 'GRCop-42'
    assert curves['fallback'] is True

def testCurveArraysAreConsistentLength():

    for material in availableWallMaterials():
        curves = wallMaterialCurves(material)
        n = curves['temperatureK'].size
        assert n >= 4
        for key in ('thermalConductivity', 'yieldStrength', 'cte', 'elongation'):
            assert curves[key].size == n, f'{material}.{key} length {curves[key].size} != grid {n}'
        assert np.all(np.diff(curves['temperatureK']) > 0), f'{material} temperature grid not increasing'
        assert np.all(curves['thermalConductivity'] > 0)

def testConductivityMonotoneWhereExpected():

    '''

    Pure copper conductivity falls with temperature; the nickel superalloys and stainless rise.

    '''

    assert _conductivityAt('OFHC Copper', 873.15) < _conductivityAt('OFHC Copper', 298.15)
    assert _conductivityAt('Inconel 718', 1073.15) > _conductivityAt('Inconel 718', 298.15)
    assert _conductivityAt('316L', 773.15) > _conductivityAt('316L', 298.15)

def testSampleClampsOutsideGrid():

    '''

    sampleWallMaterial clamps rather than extrapolating, so conductivity stays physical far
    outside the data range.

    '''

    low = sampleWallMaterial('GRCop-42', 50.0)
    high = sampleWallMaterial('GRCop-42', 5000.0)
    curves = wallMaterialCurves('GRCop-42')
    assert low['thermalConductivity'] == pytest.approx(curves['thermalConductivity'][0])
    assert high['thermalConductivity'] == pytest.approx(curves['thermalConductivity'][-1])
    assert high['thermalConductivity'] > 0

def testScalarMaterialPropertiesStillWork():

    '''

    The copied scalar lookup from the shared library is intact.

    '''

    entry = materialProperties('316L', temperature = 293.15)
    assert 7500.0 < entry['density'] < 8100.0
    assert entry['yieldStrength'] > 0
    assert entry['allowableStress'] <= entry['yieldStrength']
    assert roughnessTable('lpbf as-built') > roughnessTable('drawn tube')

def testColdConductivityGainForStainless():

    '''

    Austenitic stainless conductivity drops toward cryogenic temperature; the curve should not
    invert when clamped there.

    '''

    with warnings.catch_warnings():
        warnings.simplefilter('error')
        value = sampleWallMaterial('316L', 90.0)['thermalConductivity']
    assert 5.0 < value < 20.0

# ------------------------------------------------------------------------------------------- #
# -- Provenance: which properties are measured, and which are held flat -- #
# ------------------------------------------------------------------------------------------- #

# A scalar in the table is broadcast across the temperature grid, so it comes back the same shape
# as a measured curve and an interpolator built on it behaves identically. These tests fix what
# the current data actually supports, so filling a gap has to be a deliberate edit here as well.

def testEveryMaterialReportsWhichPropertiesAreMeasured():

    '''The measured map covers all four properties, for every material in the table.'''

    for name in availableWallMaterials():
        measured = wallMaterialCurves(name)['measured']

        assert set(measured) == {'thermalConductivity', 'yieldStrength', 'cte', 'elongation'}
        assert all(isinstance(flag, bool) for flag in measured.values())

def testConductivityIsMeasuredForEveryMaterial():

    '''

    Conductivity is what the heat transfer model reads, and it is the one property the table
    carries as a real curve throughout.

    '''

    for name in availableWallMaterials():
        assert propertyIsMeasured(name, 'thermalConductivity'), name

def testWhichMaterialsCarryMeasuredStrength():

    '''

    The state of the data, recorded so it is visible rather than assumed. GRCop-42 and Inconel 718
    carry measured yield strength and elongation across their whole grids; the other eight are
    room-temperature values held flat, because no openly available source tabulates them on a
    single product form. Adding one should fail this test and be accompanied by a citation and a
    reference check.

    See docs/materialsDatabaseRoadmap.md.

    '''

    withYieldCurves = {name for name in availableWallMaterials()
                       if propertyIsMeasured(name, 'yieldStrength')}

    assert withYieldCurves == {'GRCop-42', 'Inconel 718'}

def testWhichMaterialsCarryMeasuredExpansion():

    '''

    Expansion is measured for seven of the ten, but for four of those only below room temperature,
    where the NIST cryogenic fits reach. propertyProvenance says which part of each curve is data.

    '''

    withExpansionCurves = {name for name in availableWallMaterials()
                           if propertyIsMeasured(name, 'cte')}

    assert withExpansionCurves == {'GRCop-42', 'CuCrZr', 'OFHC Copper', 'Al 6061-T6',
                                   'Inconel 718', '316L', 'Ti-6Al-4V'}

def testHeldFlatPropertiesAreActuallyFlat():

    '''

    A property reported as not measured must be constant across its grid. If one ever varies
    while reporting False, the map is lying about the data.

    '''

    for name in availableWallMaterials():
        curves = wallMaterialCurves(name)
        for propertyName, measured in curves['measured'].items():
            if measured:
                continue
            values = curves[propertyName]
            assert np.all(values == values[0]), (name, propertyName)

def testMeasuredPropertiesActuallyVary():

    '''The converse: a property reported as measured has to change somewhere across its grid.'''

    for name in availableWallMaterials():
        curves = wallMaterialCurves(name)
        for propertyName, measured in curves['measured'].items():
            if not measured:
                continue
            values = curves[propertyName]
            assert not np.all(values == values[0]), (name, propertyName)

# --------------------------------------------------------------------------------------------- #
# -- Provenance: what each property is, and over what range -- #
# --------------------------------------------------------------------------------------------- #

def testEveryPropertyCarriesProvenance():

    '''Every property of every material names a source and the range over which it is data.'''

    for name in availableWallMaterials():
        for propertyName in ('thermalConductivity', 'yieldStrength', 'cte', 'elongation'):
            source, (low, high) = propertyProvenance(name, propertyName)

            assert isinstance(source, str) and len(source) > 20, (name, propertyName)
            assert low <= high, (name, propertyName)

def testProvenanceRangeAgreesWithTheData():

    '''

    A property whose provenance says it is measured at a single point must be flat, and one
    measured over a span must vary. This keeps the two descriptions from drifting apart.

    '''

    for name in availableWallMaterials():
        curves = wallMaterialCurves(name)
        for propertyName, measured in curves['measured'].items():
            _, (low, high) = propertyProvenance(name, propertyName)
            assert measured == (high > low), (name, propertyName, measured, low, high)

def testAProvenanceRangeLiesInsideItsGrid():

    '''A source cannot be cited over temperatures the grid does not reach.'''

    for name in availableWallMaterials():
        grid = wallMaterialCurves(name)['temperatureK'] - 273.15
        for propertyName in ('thermalConductivity', 'yieldStrength', 'cte', 'elongation'):
            _, (low, high) = propertyProvenance(name, propertyName)

            assert low >= grid.min() - 1.0, (name, propertyName)
            assert high <= grid.max() + 1.0, (name, propertyName)

# --------------------------------------------------------------------------------------------- #
# -- Cryogenic conductivity, against the NIST fits it was built from -- #
# --------------------------------------------------------------------------------------------- #

# Conductivity at 20 K as a fraction of its room-temperature value, from the NIST curve fits.
# These are the numbers that matter for a jacket running liquid hydrogen, and NOVA used to clamp
# every one of them to 1.0.
cryogenicRatios = (
    ('OFHC Copper', 3.485),
    ('316L',        0.142),
    ('Al 6061-T6',  0.183),
    ('Ti-6Al-4V',   0.114),
    ('Inconel 718', 0.303),
)

@pytest.mark.parametrize('material, expectedRatio', cryogenicRatios)
def testCryogenicConductivityRatio(material, expectedRatio):

    '''

    Conductivity at 20 K against its room-temperature value. Copper rises steeply as it cools;
    the alloys fall. Getting the direction wrong is the kind of error this pins.

    '''

    cold = sampleWallMaterial(material, 20.0)['thermalConductivity']
    room = sampleWallMaterial(material, 298.15)['thermalConductivity']

    assert cold / room == pytest.approx(expectedRatio, rel = 0.05)

def testTheAlloysLoseConductivityWhenCold():

    '''

    Every alloy in the table except pure copper conducts worse at liquid hydrogen temperature
    than at room temperature, by a factor of three or more. Clamping to the room-temperature
    value, which is what happened before the grids were extended, overstates the cold end.

    '''

    for material in ('316L', 'Al 6061-T6', 'Ti-6Al-4V', 'Inconel 718'):
        cold = sampleWallMaterial(material, 20.0)['thermalConductivity']
        room = sampleWallMaterial(material, 298.15)['thermalConductivity']

        assert cold < room / 3.0, material

def testPureCopperGainsConductivityWhenCold():

    '''

    The opposite case, and the reason the sign cannot be assumed. Electron scattering falls away
    in a pure metal, so OFHC copper conducts several times better at 20 K. The size of that peak
    is set by residual resistivity ratio, which is why the stored curve names the RRR it assumes.

    '''

    cold = sampleWallMaterial('OFHC Copper', 20.0)['thermalConductivity']
    room = sampleWallMaterial('OFHC Copper', 298.15)['thermalConductivity']

    assert cold > 3.0 * room

    source, _ = propertyProvenance('OFHC Copper', 'thermalConductivity')
    assert 'RRR' in source

@pytest.mark.parametrize('material', ['OFHC Copper', '316L', 'Al 6061-T6', 'Ti-6Al-4V',
                                      'Inconel 718'])
def testTheCryogenicGridReachesLiquidHydrogen(material):

    '''

    The grids used to start at room temperature while regen coolant inlets sit near 20 K, so the
    cold end of a jacket was sized on a clamped room-temperature conductivity.

    '''

    grid = wallMaterialCurves(material)['temperatureK']

    assert grid.min() <= 25.0, material

def testMaterialsWithoutCryogenicDataStillClamp():

    '''

    The five with no cryogenic source keep the old behavior and say so through their provenance.
    Nothing here pretends to know what it does not.

    '''

    for material in ('GRCop-42', 'CuCrZr', 'NARloy-Z', 'AlSi10Mg', 'Inconel 625'):
        grid = wallMaterialCurves(material)['temperatureK']
        assert grid.min() > 273.0, material

# --------------------------------------------------------------------------------------------- #
# -- Inconel 718 strength, against the Special Metals bulletin -- #
# --------------------------------------------------------------------------------------------- #

# Temperature [K] and 0.2 % offset yield [MPa] from Special Metals INCONEL alloy 718, Tables 21
# and 19, converted from ksi at 6.894757 MPa/ksi.
inconelYieldReferences = (
    (20.35,  1343.8),    # -423 F, liquid hydrogen
    (77.6,   1287.9),    # -320 F, liquid nitrogen
    (294.3,  1123.8),    #   70 F
    (588.7,  1075.6),    #  600 F
    (922.0,   965.3),    # 1200 F
    (1033.2,  799.8),    # 1400 F
)

@pytest.mark.parametrize('kelvin, expectedMPa', inconelYieldReferences)
def testInconelYieldAgainstTheBulletin(kelvin, expectedMPa):

    '''Sampled yield strength against the tabulated Special Metals values, within 2 per cent.'''

    sampled = sampleWallMaterial('Inconel 718', kelvin)['yieldStrength'] / 1e6

    assert sampled == pytest.approx(expectedMPa, rel = 0.02)

def testInconelGainsStrengthWhenCold():

    '''

    Inconel 718 is about 20 per cent stronger at liquid hydrogen temperature than at room
    temperature. A held-flat room-temperature value understates the cold end, which is
    conservative for a pressure margin and wrong for a thermal stress calculation.

    '''

    cold = sampleWallMaterial('Inconel 718', 20.35)['yieldStrength']
    room = sampleWallMaterial('Inconel 718', 294.3)['yieldStrength']

    assert cold / room == pytest.approx(1.196, rel = 0.02)

def testInconelElongationIsNotMonotone():

    '''

    Elongation falls to 5 per cent near 760 degC and recovers above it. That is the alloy, not a
    transcription error, and it is pinned here so nobody smooths it out.

    '''

    elongation = wallMaterialCurves('Inconel 718')['elongation']

    assert float(np.min(elongation)) == pytest.approx(5.0, abs = 0.1)
    assert float(elongation[-1]) > float(np.min(elongation))

# --------------------------------------------------------------------------------------------- #
# -- CuCrZr expansion, against the NASA quadratic it was built from -- #
# --------------------------------------------------------------------------------------------- #

def testCuCrZrExpansionAgainstTheQuadratic():

    '''

    Mean expansion from 20 degC, rebuilt from de Groh, Ellis and Loewenthal NASA/TM-2007-214663
    Table 5: alpha(T) = A T^2 + B T + C for Cu-1Cr-0.1Zr, stated accurate to 1 per cent.

    '''

    A, B, C = 4.947e-09, 1.559e-05, -8.019e-05
    strain = lambda T: A * T**2 + B * T + C

    for celsius in (100.0, 300.0, 600.0):
        expected = (strain(celsius) - strain(20.0)) / (celsius - 20.0)
        sampled = sampleWallMaterial('CuCrZr', celsius + 273.15)['cte']

        assert sampled == pytest.approx(expected, rel = 0.01), celsius

def testCuCrZrExpansionRisesWithTemperature():

    '''Copper expands faster as it heats; a flat value misses about 18 per cent by 600 degC.'''

    cold = sampleWallMaterial('CuCrZr', 293.15)['cte']
    hot = sampleWallMaterial('CuCrZr', 873.15)['cte']

    assert hot > cold
    assert hot / cold == pytest.approx(1.18, rel = 0.03)

def testTheTwoStoresDisagreeOn316L():

    '''

    materialProperties and wallMaterialCurves both carry 316L and give different conductivities,
    16.3 against 14.6 W/m-K. Only the second is validated against a cited source. The
    disagreement is recorded rather than silently tolerated; reconciling the two stores is step 3
    of the roadmap and should replace this test.

    '''

    scalar = materialProperties('316L')['thermalConductivity']
    curve = sampleWallMaterial('316L', 293.15)['thermalConductivity']

    assert scalar != pytest.approx(curve, rel = 0.05)

# ------------------------------------------------------------------------------------------- #
# -- Physical plausibility -- #
# ------------------------------------------------------------------------------------------- #

# Loose bounds on what a structural metal can do, as a guard against a transcription slip or a
# unit error. These are not design values; they are the range outside which a number is wrong.
plausibleExpansion = {
    'copper':    (14.0e-6, 22.0e-6),
    'aluminium': (17.0e-6, 28.0e-6),
    'nickel':    (10.0e-6, 18.0e-6),
    'steel':     (13.0e-6, 21.0e-6),
    'titanium':  (6.0e-6, 12.0e-6),
}

materialFamily = {
    'GRCop-42': 'copper', 'CuCrZr': 'copper', 'OFHC Copper': 'copper', 'NARloy-Z': 'copper',
    'AlSi10Mg': 'aluminium', 'Al 6061-T6': 'aluminium',
    'Inconel 718': 'nickel', 'Inconel 625': 'nickel',
    '316L': 'steel', 'Ti-6Al-4V': 'titanium',
}

# GRCop-42 below 300 degC is a known exception, recorded in its provenance: the source's two
# lowest expansion entries are not physical for a copper alloy and read as a fit artefact where
# a mean referenced to 293 K is ill conditioned. They are left as the source gives them.
expansionExceptions = {('GRCop-42', 25.0), ('GRCop-42', 100.0), ('GRCop-42', 200.0)}

@pytest.mark.parametrize('material', sorted(materialFamily))
def testExpansionIsPhysicallyPlausible(material):

    '''

    Every expansion value at and above room temperature sits inside the range its alloy family
    can occupy. A copper alloy reading 1.5e-6/K is an Invar, not a copper, and that is the kind
    of slip this catches.

    '''

    curves = wallMaterialCurves(material)
    celsius = curves['temperatureK'] - 273.15
    low, high = plausibleExpansion[materialFamily[material]]

    for temperature, value in zip(celsius, curves['cte']):
        if temperature < 20.0 or (material, round(float(temperature))) in expansionExceptions:
            continue
        assert low <= value <= high, (material, temperature, value)

def testTheGrcopExpansionAnomalyIsStillRecorded():

    '''

    The exception above is real data, not a bug to be quietly fixed, so the entry that documents
    it has to stay. If the source is ever superseded this test is the reminder to revisit it.

    '''

    curves = wallMaterialCurves('GRCop-42')

    assert float(curves['cte'][0]) < 5.0e-6

    source, _ = propertyProvenance('GRCop-42', 'cte')
    assert 'not physical' in source

@pytest.mark.parametrize('material', sorted(materialFamily))
def testConductivityIsPositiveAndFinite(material):

    '''No conductivity may be zero, negative or non-finite anywhere on its grid.'''

    values = wallMaterialCurves(material)['thermalConductivity']

    assert np.all(np.isfinite(values))
    assert np.all(values > 0.0)
