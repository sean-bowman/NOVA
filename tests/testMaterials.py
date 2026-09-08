# -- Tests for the Wall Material Property Module -- #

'''

Validation and behaviour tests for src/NOVA/materials.py.

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

from NOVA.materials import (propertyIsMeasured, wallMaterialCurves, sampleWallMaterial, availableWallMaterials,
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

def testLegacyKeysResolve():

    '''

    The keys the earlier heat transfer model used still map to a curve.

    '''

    assert resolveWallMaterialName('cu') == 'GRCop-42'
    assert resolveWallMaterialName('al') == 'AlSi10Mg'
    assert resolveWallMaterialName('in') == 'Inconel 718'
    assert wallMaterialCurves('cu')['fallback'] is False
    assert wallMaterialCurves('in')['fallback'] is False

def testLegacyCopperCurveUnchanged():

    '''

    The 'cu' path still returns exactly the NASA GRCop-42 data the model shipped with, so a
    pre-existing copper run does not move.

    '''

    curves = wallMaterialCurves('cu')
    expected = np.array([289, 301, 310, 313, 312, 308, 301, 293, 284, 274], dtype = float)
    assert np.array_equal(curves['thermalConductivity'], expected)

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

def testOnlyGrcopCarriesMeasuredStrengthAndExpansion():

    '''

    The state of the data, recorded so it is visible rather than assumed. Yield strength,
    expansion and elongation are room-temperature values held flat for every alloy but GRCop-42.
    Adding a real curve for one of them should fail this test and be accompanied by a source and
    a reference check, in the manner of _CONDUCTIVITY_REFERENCES above.

    See src/NOVA/docs/materialsDatabaseRoadmap.md.

    '''

    withCurves = {name for name in availableWallMaterials()
                  if propertyIsMeasured(name, 'yieldStrength')}

    assert withCurves == {'GRCop-42'}

    for name in availableWallMaterials():
        if name == 'GRCop-42':
            continue
        for propertyName in ('yieldStrength', 'cte', 'elongation'):
            assert not propertyIsMeasured(name, propertyName), (name, propertyName)

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

def testNoMaterialCarriesCryogenicData():

    '''

    Every grid starts at or above 20 degC while regen coolant inlets are at liquid hydrogen
    temperature, so the cold end of a jacket is sized on a clamped room-temperature conductivity.
    This records that gap; extending a grid downward should fail here.

    See step 1 of src/NOVA/docs/materialsDatabaseRoadmap.md.

    '''

    for name in availableWallMaterials():
        grid = wallMaterialCurves(name)['temperatureK']
        assert grid[0] > 273.0, (name, grid[0])

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
