# -- Non-metallic and refractory material tests -- #

'''

Checks on the material store that is not wall alloys: throat inserts, nozzle extensions,
ablative liners, thermal barrier coatings and the polymers in the feed system.

What is worth testing here is different from the wall alloys. That store holds curves the heat
transfer model integrates, so its tests check numbers against the sources they came from. This
one holds selection-grade data, so its tests check that the store cannot mislead: that nothing
in it can be selected as a cooled wall, that every value says what grade of source it came from,
that a missing property raises rather than returning zero, and that the temperature limits carry
the atmosphere they apply in.

That last one is the point of the store. Bare 2D carbon-carbon is good past 2500 degC inert and
oxidises from about 400 degC in air. A single maximum use temperature would be a lie whichever
number it held.

'''

import numpy as np
import pytest

from NOVA import materials
from NOVA.materials import (availableMaterialClasses, availableMaterials, availableWallMaterials,
                            materialProfile, materialProperty, materialPropertyProvenance,
                            maxUseTemperature, surfaceEmissivity)

# --------------------------------------------------------------------------------------------- #
# -- The two stores stay apart -- #
# --------------------------------------------------------------------------------------------- #

def testNoNonMetalCanBeSelectedAsACooledWall():

    '''

    The reason for a separate store. Carbon phenolic is meant to be consumed, graphite cannot be
    brazed into a jacket and PTFE is a seal; none of them can be a regeneratively cooled wall,
    and `wallMaterialCurves` must not offer them.

    '''

    wallAlloys = {name.lower() for name in availableWallMaterials()}

    for name in availableMaterials():
        assert name.lower() not in wallAlloys, name

def testAskingForANonMetalAsAWallFallsBackLoudly():

    '''

    `wallMaterialCurves` falls back to GRCop-42 with a warning for anything it does not know.
    A non-metal has to take that path rather than silently resolving to something.

    '''

    with pytest.warns(UserWarning):
        curves = materials.wallMaterialCurves('Carbon Phenolic')

    assert curves['fallback'] is True
    assert curves['material'] == 'GRCop-42'

def testTheWallStoreIsUnaffected():

    '''Adding the second store must not have changed the first.'''

    assert len(availableWallMaterials()) == 10
    assert 'GRCop-42' in availableWallMaterials()

# --------------------------------------------------------------------------------------------- #
# -- Structure -- #
# --------------------------------------------------------------------------------------------- #

def testEveryMaterialIsInAKnownClass():

    '''Each entry declares a class, and the class list is derived from the entries themselves.'''

    classes = set(availableMaterialClasses())

    for name in availableMaterials():
        assert materialProfile(name)['class'] in classes, name

def testEveryClassHasAtLeastOneMaterial():

    for materialClass in availableMaterialClasses():
        assert availableMaterials(materialClass), materialClass

def testTheClassFilterPartitionsTheStore():

    '''Filtering by class covers everything exactly once.'''

    filtered = []
    for materialClass in availableMaterialClasses():
        filtered.extend(availableMaterials(materialClass))

    assert sorted(filtered) == availableMaterials()

def testAnUnknownClassIsRefusedByName():

    with pytest.raises(KeyError, match = 'material class'):
        availableMaterials('ablatives')

def testEveryMaterialCarriesTheRequiredFields():

    '''

    A material without a form, an application or a source is not usable for selection, which is
    the only thing this store is for.

    '''

    for name in availableMaterials():
        entry = materialProfile(name)

        for field in ('class', 'form', 'application', 'density', 'properties',
                      'maxUseTemperatureC', 'basis', 'provenance'):
            assert field in entry, (name, field)

        assert entry['density'] > 0, name
        assert entry['properties'], name

def testMaterialLookupIsCaseInsensitive():

    assert materialProfile('ptfe') is materialProfile('PTFE')
    assert materialProfile('  c103  ') is materialProfile('C103')

def testAnUnknownMaterialRaisesRatherThanSubstituting():

    '''

    The wall alloys fall back to GRCop-42 for an unknown name. This store must not: there is no
    sensible default throat insert, and quietly returning one would be worse than refusing.

    '''

    with pytest.raises(KeyError, match = 'Unknown material'):
        materialProfile('Unobtainium')

# --------------------------------------------------------------------------------------------- #
# -- Provenance and grade -- #
# --------------------------------------------------------------------------------------------- #

recognizedBases = {'producerDatasheet', 'literatureReview', 'literatureRepresentative'}

def testEveryMaterialDeclaresItsGrade():

    for name in availableMaterials():
        assert materialProfile(name)['basis'] in recognizedBases, name

def testEveryStoredPropertyHasProvenance():

    '''

    A number without a source is not usable for selection either. Every property, plus density
    and the temperature limits, has to say where it came from.

    '''

    for name in availableMaterials():
        entry = materialProfile(name)

        for propertyName in entry['properties']:
            source, basis = materialPropertyProvenance(name, propertyName)

            assert isinstance(source, str) and len(source) > 20, (name, propertyName)
            assert basis in recognizedBases, (name, propertyName, basis)

def testTheTemperatureLimitsCarryProvenance():

    '''The governing property of this store cannot be the one without a source.'''

    for name in availableMaterials():
        source, basis = materialPropertyProvenance(name, 'maxUseTemperatureC')

        assert isinstance(source, str) and len(source) > 20, name
        assert basis in recognizedBases, name

def testAskingForProvenanceOfAnAbsentPropertyRaises():

    with pytest.raises(KeyError, match = 'records no provenance'):
        materialPropertyProvenance('PTFE', 'fractureToughness')

# --------------------------------------------------------------------------------------------- #
# -- Temperature limits -- #
# --------------------------------------------------------------------------------------------- #

def testEveryMaterialDefinesAtLeastOneLimit():

    for name in availableMaterials():
        assert materialProfile(name)['maxUseTemperatureC'], name

def testTheCarbonMaterialsSeparateInertFromOxidising():

    '''

    The distinction the store exists to make. Carbon is good to thousands of degrees in an inert
    atmosphere and oxidises in air at a small fraction of that, so a single number would be
    wrong whichever end it held.

    '''

    for name in ('ATJ Graphite', 'Carbon-Carbon (2D)'):
        limits = materialProfile(name)['maxUseTemperatureC']

        assert 'inert' in limits and 'oxidising' in limits, name
        assert limits['inert'] > 4.0 * limits['oxidising'], name

def testCoatedCarbonCarbonIsRecordedSeparatelyFromBare():

    '''

    The 1750 degC figure quoted for C/C in air is for coated material. Bare C/C oxidises from
    about 400 degC. Both are stored so the first cannot be read as the second.

    '''

    limits = materialProfile('Carbon-Carbon (2D)')['maxUseTemperatureC']

    assert limits['oxidising'] == pytest.approx(400.0)
    assert limits['oxidisingCoated'] == pytest.approx(1750.0)
    assert limits['oxidisingCoated'] > 4.0 * limits['oxidising']

def testTheCeramicCompositesSurviveAirBetterThanCarbon():

    '''

    The trade the ceramic matrix buys: C/SiC and SiC/SiC hold up in air without a separate
    oxidation coating, at the cost of density.

    '''

    bareCarbon = maxUseTemperature('Carbon-Carbon (2D)', 'oxidising')

    for name in ('C/SiC', 'SiC/SiC'):
        assert maxUseTemperature(name, 'oxidising') > 3.0 * bareCarbon, name
        assert materialProfile(name)['density'] > materialProfile('Carbon-Carbon (2D)')['density']

def testAskingForAnUndefinedAtmosphereRaises():

    with pytest.raises(KeyError, match = 'atmosphere'):
        maxUseTemperature('PTFE', 'inert')

@pytest.mark.parametrize('material', ['PTFE', 'PCTFE', 'PEEK'])
def testThePolymersAreLimitedFarBelowTheCeramics(material):

    '''A sanity check on the ordering: no polymer belongs anywhere near a throat.'''

    assert maxUseTemperature(material, 'continuous') < 300.0

# --------------------------------------------------------------------------------------------- #
# -- Property access -- #
# --------------------------------------------------------------------------------------------- #

def testAPropertyReturnsItsVariantMapWithoutAVariant():

    variants = materialProperty('7YSZ', 'thermalConductivity')

    assert set(variants) == {'denseSintered', 'sprayedCoating'}

def testAVariantSelectsOneValue():

    dense = materialProperty('7YSZ', 'thermalConductivity', 'denseSintered')
    sprayed = materialProperty('7YSZ', 'thermalConductivity', 'sprayedCoating')

    assert dense > sprayed
    assert sprayed == pytest.approx(1.0)

def testAnAbsentPropertyRaisesRatherThanReturningZero():

    '''

    A property missing from an entry means no source was found for it. Returning zero would be
    indistinguishable from a material with no strength.

    '''

    with pytest.raises(KeyError, match = 'no source was found'):
        materialProperty('7YSZ', 'tensileStrength')

def testAnAbsentVariantRaises():

    with pytest.raises(KeyError, match = 'no variant'):
        materialProperty('ATJ Graphite', 'thermalConductivity', 'acrossGrain')

def testEveryStoredValueIsPositiveAndFinite():

    '''No property may be zero, negative or non-finite anywhere in the store.'''

    for name in availableMaterials():
        entry = materialProfile(name)

        assert np.isfinite(entry['density']) and entry['density'] > 0, name

        for propertyName, variants in entry['properties'].items():
            for variant, value in variants.items():
                assert np.isfinite(value), (name, propertyName, variant)
                assert value > 0, (name, propertyName, variant)

# --------------------------------------------------------------------------------------------- #
# -- Physical plausibility -- #
# --------------------------------------------------------------------------------------------- #

def testDensitiesAreInTheRightOrder():

    '''

    The carbons are the light materials and the refractory metal is the heavy one, with an order
    of magnitude between them. A unit slip of a thousand would break this before it reached a
    mass budget.

    Note that the polymers do not sit at the bottom: PTFE at 2175 kg/m^3 is denser than 2D
    carbon-carbon at 1825, which is why a fluoropolymer seal is not the light choice it looks.

    '''

    density = lambda name: materialProfile(name)['density']

    assert density('PEEK') < density('Carbon Phenolic') < density('ATJ Graphite')
    assert density('ATJ Graphite') < density('Carbon-Carbon (2D)') < density('C/SiC')
    assert density('C/SiC') < density('SiC/SiC') < density('7YSZ') < density('C103')

    assert density('PTFE') > density('Carbon-Carbon (2D)')
    assert density('C103') > 4.0 * density('Carbon-Carbon (2D)')

def testTheThermalBarrierActuallyInsulates():

    '''

    A thermal barrier coating has to conduct far worse than what it is sprayed onto, or it is
    just mass. Against GRCop-42 at about 320 W/m-K the sprayed coating is more than two orders
    of magnitude lower.

    '''

    coating = materialProperty('7YSZ', 'thermalConductivity', 'sprayedCoating')
    wall = materials.sampleWallMaterial('GRCop-42', 800.0)['thermalConductivity']

    assert coating < wall / 100.0

def testTheExpansionMismatchThatSpallsACoatingIsVisible():

    '''

    What limits a thermal barrier is not its own expansion but the difference against the
    substrate. 7YSZ at about 11e-6/K against GRCop-42 near 17e-6/K is a mismatch of roughly a
    third, and the store has to carry enough to see that.

    '''

    coating = materialProperty('7YSZ', 'cte', 'isotropic')
    substrate = materials.sampleWallMaterial('GRCop-42', 800.0)['cte']

    assert substrate > coating
    assert (substrate - coating) / substrate > 0.2

def testGraphiteHasAVeryLowExpansion():

    '''

    Graphite's thermal shock resistance comes from low expansion with high conductivity and a low
    modulus. Its expansion is several times below any metal in the wall store.

    '''

    graphite = materialProperty('ATJ Graphite', 'cte', 'withGrain')
    copper = materials.sampleWallMaterial('OFHC Copper', 293.15)['cte']

    assert graphite < copper / 4.0

def testCarbonCarbonIsStifferThanTheAblative():

    '''

    A structural composite against a material designed to be consumed. If these ever cross, a
    modulus has been entered in the wrong unit.

    '''

    structural = materialProperty('Carbon-Carbon (2D)', 'elasticModulus', 'inPlane')
    ablative = materialProperty('Carbon Phenolic', 'elasticModulus', 'virgin')

    assert structural > 3.0 * ablative

def testTheLpbfC103IsStrongerThanWrought():

    '''

    The finding the NASA additive manufacturing study reports, and the reason the store carries
    both conditions. It also guards the transposed columns in that report's table: if the two
    were ever read the wrong way round, yield would exceed ultimate.

    '''

    yieldStrength = materialProperty('C103', 'yieldStrength')
    tensileStrength = materialProperty('C103', 'tensileStrength')

    for condition in ('wrought', 'lpbfStressRelieved'):
        assert tensileStrength[condition] > yieldStrength[condition], condition

    assert yieldStrength['lpbfStressRelieved'] > yieldStrength['wrought']


# --------------------------------------------------------------------------------------------- #
# -- Surface emissivity -- #
# --------------------------------------------------------------------------------------------- #

class TestSurfaceEmissivity:

    '''

    Emissivity is a surface property, not an alloy property, and the store treats it that way.

    A radiation-cooled wall settles where its own emissivity puts it. The equilibrium temperature
    goes as the inverse fourth root, so the number is the design driver and a guess propagates
    straight into it. The store therefore carries one only where a source describes the surface,
    and refuses everywhere else rather than substituting.

    '''

    def testTheCoatedColumbiumValueIsCarried(self):

        assert surfaceEmissivity('C103', 'r512eCoatedOxidised') == 0.7

    def testItIsKeyedOnASurfaceConditionRatherThanOnTheAlloy(self):

        stored = surfaceEmissivity('C103')

        assert isinstance(stored, dict)
        assert all('coated' in key.lower() or 'bare' in key.lower() for key in stored), sorted(stored)

    def testTheValueIsPhysical(self):

        for value in surfaceEmissivity('C103').values():
            assert 0.0 < value <= 1.0

    def testTheSourceNamesItsCaveats(self):

        source, basis = materialPropertyProvenance('C103', 'emissivity')

        # Three things have to survive any edit of this entry: the substrates measured were not
        # C103, the environment was an oxidising arc rather than a vacuum extension, and no
        # beginning-of-life value is recorded.
        assert 'FS-85' in source
        assert 'torr' in source
        assert 'beginning-of-life' in source
        assert basis == 'literatureReview'

    def testNoBeginningOfLifeValueIsInvented(self):

        # The sourced value is the degraded one. Storing a fresh-surface number alongside it
        # without a source would make the aged value look like the pessimistic end of a measured
        # range rather than the only thing anybody measured.
        assert len(surfaceEmissivity('C103')) == 1

    @pytest.mark.parametrize('alloy', ['GRCop-42', 'OFHC Copper', 'Inconel 718'])
    def testTheWallAlloysCarryNone(self, alloy):

        # There is no published emissivity for these at the surface finish a printed chamber has.
        # The refusal is the honest answer and the configuration supplies the number instead.
        with pytest.raises(KeyError):
            surfaceEmissivity(alloy)

    def testAMaterialWithoutOneSaysSoRatherThanGuessing(self):

        with pytest.raises(KeyError) as raised:
            surfaceEmissivity('ATJ Graphite')

        assert 'surface property' in str(raised.value)

    def testAnUnknownMaterialIsDistinguishedFromAnUnsourcedOne(self):

        with pytest.raises(KeyError) as raised:
            surfaceEmissivity('NotAMaterial')

        assert 'Unknown material' in str(raised.value)

    def testAnUnknownSurfaceConditionIsRefused(self):

        with pytest.raises(KeyError):
            surfaceEmissivity('C103', 'polishedBare')
