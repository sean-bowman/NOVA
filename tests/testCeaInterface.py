
# -- Tests for the NOVA CEA Interface -- #

'''

Validation suite for ceaInterface.py, the rocketcea-backed replacement for the
legacy f2py CEAWrapper.

Run with:  python -m pytest tests/testCeaInterface.py -v
      or:  python tests/testCeaInterface.py

The reference case throughout is LOX/LH2 at Pc = 1000 psia, MR = 5.5, eps = 40,
shifting equilibrium, infinite-area chamber. It is chosen because it is heavily
published and cross-checkable against the NASA CEARun web tool.

Sean Bowman

'''

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'NOVANozzleDesigner'))

from ceaInterface import (CEA, PA_PER_PSIA, DEGR_TO_K, FTPS_TO_MPS,
                          LBMPFT3_TO_KGPM3, BTUPLBM_TO_JPKG, CALPGK_TO_JPKGK,
                          MILLIPOISE_TO_PAS, MCALCMKS_TO_WMK, R_UNIVERSAL)

# Reference case
CHAMBERPRESSURE = 1000.0 * PA_PER_PSIA  # 6.8948 MPa
MIXTURERATIO    = 5.5
EXPANSIONRATIO  = 40.0

@pytest.fixture(scope = 'module')
def referenceCase() -> CEA:
    '''
    The LOX/LH2 reference case, solved once and shared across tests.
    '''
    return CEA(fuelName = 'LH2', oxidizerName = 'LOX',
               chamberPressure = CHAMBERPRESSURE, expansionRatio = EXPANSIONRATIO,
               OFRatio = MIXTURERATIO, pressureUnits = 'Pa')

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- Tier 1: unit conversion constants, no CEA involved -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

def testUnitConstants():
    '''
    Guard the conversion factors against hand-computed values.

    The trap this exists to catch: BTU/(lbm-degR) and cal/(g-K) are numerically
    identical (4184), but BTU/lbm (2326) and cal/g (4184) differ by a factor of
    1.8. Enthalpies are BTU-based while heat capacities and entropies are
    cal-based, so confusing the two is the single most likely silent defect in
    this module.
    '''
    assert PA_PER_PSIA       == pytest.approx(101325.0 / 14.6959488, rel = 1e-6)
    assert DEGR_TO_K         == pytest.approx(1.0 / 1.8, rel = 1e-12)
    assert FTPS_TO_MPS       == pytest.approx(0.3048, rel = 1e-12)
    assert LBMPFT3_TO_KGPM3  == pytest.approx(0.45359237 / 0.3048**3, rel = 1e-6)
    assert BTUPLBM_TO_JPKG   == pytest.approx(1055.05585 / 0.45359237, rel = 1e-4)
    assert CALPGK_TO_JPKGK   == pytest.approx(4.184 * 1000.0, rel = 1e-12)
    assert MILLIPOISE_TO_PAS == pytest.approx(1.0e-4, rel = 1e-12)
    assert MCALCMKS_TO_WMK   == pytest.approx(4.184 * 1.0e-3 * 100.0, rel = 1e-12)
    # The BTU/lbm to cal/g ratio must be 1.8, not 1.0
    assert CALPGK_TO_JPKGK / BTUPLBM_TO_JPKG == pytest.approx(1.8, rel = 1e-3)

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- Tier 2: reference case against CEARun -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

@pytest.mark.parametrize('key, low, high', [
    ('combustionChamberTemperature',         3380.0,   3420.0),   # K
    ('combustionChamberMolecularWeight',       12.6,     12.8),   # g/mol
    ('combustionChamberGamma',                 1.13,     1.16),
    ('characteristicVelocity',               2320.0,   2360.0),   # m/s
    ('combustionChamberHeatCapacity',        7000.0,   8500.0),   # J/kg-K
    ('combustionChamberThermalConductivity',    1.4,      1.7),   # W/m-K
    ('combustionChamberPrandtlNumber',         0.48,     0.56),
    ('exitMach',                                4.0,      4.4),
])
def testReferenceCaseAgainstCEARun(referenceCase, key, low, high):
    '''
    Thermodynamic quantities should sit well inside these windows; they come
    from the same FORTRAN CEARun uses, so any real disagreement indicates a unit
    error rather than a physics difference.

    A discrepancy near a factor of 1.8, 4.184 or 9.81 is a unit-constant bug.
    '''
    value = referenceCase.ceaResults[key]
    assert low <= value <= high, (
        f'{key} = {value}, expected {low}..{high}. A ratio near 1.8, 4.184 or '
        f'9.81 against the expected range indicates a unit conversion bug.')

def testReferenceViscosity(referenceCase):
    '''
    Chamber viscosity, checked separately because of its scale.
    '''
    assert 0.9e-4 <= referenceCase.ceaResults['combustionChamberViscosity'] <= 1.2e-4

def testVacuumIsp(referenceCase):
    '''
    Vacuum Isp for LOX/LH2 at this condition is ~450 s.
    '''
    assert 450.0 <= referenceCase.nozzlePerformance['vacuumISP[s]'] <= 458.0

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- Self-consistency, independent of any external reference -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

def testPrandtlIsConsistentWithTransport(referenceCase):
    '''
    Recomputing Pr as Cp*mu/k must reproduce CEA's own reported Prandtl number.

    This is the strongest single check in the suite: it validates the heat
    capacity, viscosity and thermal conductivity conversions simultaneously,
    since an error in any one of the three would break the identity.
    '''
    results = referenceCase.ceaResults
    for station in ('combustionChamber', 'throat', 'exit'):
        recomputed = (results[f'{station}Viscosity'] * results[f'{station}HeatCapacity']
                      / results[f'{station}ThermalConductivity'])
        assert recomputed == pytest.approx(results[f'{station}PrandtlNumber'], rel = 1e-6), \
            f'{station}: Cp*mu/k disagrees with the reported Prandtl number'

def testIdealGasLawRecoversChamberPressure(referenceCase):
    '''
    rho*R*T at the chamber station must recover the input chamber pressure.

    Validates the density, molecular weight and temperature conversions jointly,
    and confirms that CEA treats the input Pc as the chamber pressure when no
    finite area combustor is active.
    '''
    results = referenceCase.ceaResults
    recovered = (results['combustionChamberDensity']
                 * results['combustionChamberGasConstant']
                 * results['combustionChamberTemperature'])
    assert recovered == pytest.approx(CHAMBERPRESSURE, rel = 2e-3)

def testGasConstantMatchesMolecularWeight(referenceCase):
    '''
    The gas constant is a pure derivation from molecular weight.
    '''
    results = referenceCase.ceaResults
    for station in ('combustionChamber', 'throat', 'exit'):
        assert results[f'{station}GasConstant'] == pytest.approx(
            R_UNIVERSAL / results[f'{station}MolecularWeight'], rel = 1e-12)

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- Tier 3: pressure conventions -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

def testChamberPressureWithoutFiniteAreaCombustor(referenceCase):
    '''
    With an infinite-area chamber the injector face and chamber stations
    coincide, so both must equal the input pressure.
    '''
    results = referenceCase.ceaResults
    assert results['combustionChamberPressure'] == pytest.approx(CHAMBERPRESSURE, rel = 1e-9)
    assert results['injectionPressure']         == pytest.approx(CHAMBERPRESSURE, rel = 1e-9)

def testThroatPressureRatioIsNearIsentropic(referenceCase):
    '''
    P*/Pc should land near the isentropic (2/(g+1))^(g/(g-1)) value.
    '''
    results = referenceCase.ceaResults
    gamma = results['combustionChamberGamma']
    isentropic = (2.0 / (gamma + 1.0))**(gamma / (gamma - 1.0))
    assert results['throatPressure'] / CHAMBERPRESSURE == pytest.approx(isentropic, abs = 0.01)

def testFiniteAreaCombustorDropsChamberPressure():
    '''
    With a finite area combustor CEA treats the input Pc as the injector face
    pressure, so the chamber station sits a few percent lower.
    '''
    case = CEA(fuelName = 'LH2', oxidizerName = 'LOX', chamberPressure = CHAMBERPRESSURE,
               contractionRatio = 3.0, OFRatio = MIXTURERATIO, pressureUnits = 'Pa')
    results = case.ceaResults
    ratio = results['combustionChamberPressure'] / results['injectionPressure']
    assert 0.94 <= ratio <= 0.97
    assert results['contractionRatio'] == pytest.approx(3.0)
    # A contraction-ratio-only case defines no exit station
    assert not case.hasExitConditions
    assert 'exitGamma' not in results

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- Tier 4: endpoint guards and monotonicity -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

CONVERGINGKEYS = ['combustionChamberThermalConductivity', 'combustionChamberViscosity',
                  'combustionChamberPrandtlNumber', 'combustionChamberGamma',
                  'combustionChamberGasConstant', 'combustionChamberHeatCapacity',
                  'combustionChamberMolecularWeight']

DIVERGINGKEYS = ['exitThermalConductivity', 'exitViscosity', 'exitPrandtlNumber',
                 'exitGamma', 'exitGasConstant', 'exitHeatCapacity',
                 'exitMolecularWeight']

@pytest.mark.parametrize('contractionRatio', [1.0, 1.5, 2.0, 3.0, 5.0, 10.0])
def testConvergingStationsAreFinite(contractionRatio):
    '''
    Nozzle.py's converging sweep drives the contraction ratio down toward 1.0,
    where CEA's finite area combustor is degenerate. Every station must still
    return real numbers, because Nozzle.py raises on NaN.
    '''
    results = CEA(fuelName = 'LH2', oxidizerName = 'LOX',
                  chamberPressure = CHAMBERPRESSURE, contractionRatio = contractionRatio,
                  OFRatio = MIXTURERATIO, pressureUnits = 'Pa').ceaResults
    for key in CONVERGINGKEYS:
        assert np.isfinite(results[key]), f'{key} not finite at contractionRatio={contractionRatio}'

@pytest.mark.parametrize('expansionRatio', [1.0, 1.0000001, 2.0, 10.0, 40.0, 100.0])
def testDivergingStationsAreFiniteAndMonotonic(expansionRatio):
    '''
    Nozzle.py's diverging sweep includes exactly 1.0, where the supersonic
    branch is undefined and must be clamped. Temperature must also fall
    monotonically from chamber to exit.
    '''
    results = CEA(fuelName = 'LH2', oxidizerName = 'LOX',
                  chamberPressure = CHAMBERPRESSURE, expansionRatio = expansionRatio,
                  OFRatio = MIXTURERATIO, pressureUnits = 'Pa').ceaResults
    for key in DIVERGINGKEYS:
        assert np.isfinite(results[key]), f'{key} not finite at expansionRatio={expansionRatio}'
    assert (results['combustionChamberTemperature'] >= results['throatTemperature']
            >= results['exitTemperature'])

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- Input modes -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

def testExitPressureInputModeRoundTrips():
    '''
    Given a target exit pressure, the solved area ratio must reproduce that
    pressure. This is the round trip Nozzle.py depends on for its
    targetExitPressure input path.
    '''
    targetExitPressure = 101325.0
    case = CEA(fuelName = 'LH2', oxidizerName = 'LOX', chamberPressure = CHAMBERPRESSURE,
               nozzleExitPressure = targetExitPressure, OFRatio = MIXTURERATIO,
               pressureUnits = 'Pa')
    assert case.ceaResults['exitPressure'] == pytest.approx(targetExitPressure, rel = 1e-3)
    assert case.ceaResults['expansionRatio'] > 1.0

def testSeaLevelCaseIsNotUnderExpanded():
    '''
    A nozzle expanded to exactly one atmosphere should report 'Ideal'.

    This is the regression test for the legacy bar/Pa bug: the old wrapper read
    the exit pressure in bar and compared it against ambient in Pa, which made
    the exit pressure look ~1e5 times too small and pinned `mode` at
    'UnderExpanded' for essentially every case.
    '''
    case = CEA(fuelName = 'LH2', oxidizerName = 'LOX', chamberPressure = CHAMBERPRESSURE,
               nozzleExitPressure = 101325.0, OFRatio = MIXTURERATIO, pressureUnits = 'Pa')
    assert case.nozzlePerformance['mode'] == 'Ideal'

def testIdealIspIsBelowVacuumIsp(referenceCase):
    '''
    Ideal Isp must be strictly below vacuum Isp by the pressure-thrust term.
    Under the legacy bar/Pa bug these two collapsed onto each other.
    '''
    performance = referenceCase.nozzlePerformance
    assert performance['idealISP[s]'] < performance['vacuumISP[s]']
    assert performance['seaLevelISP[s]'] < performance['idealISP[s]']

def testMaxIspOptimizerFindsReasonableMixtureRatio():
    '''
    Peak-Isp O/F for LOX/LH2 is well below the stoichiometric 7.94, because
    hydrogen-rich operation lowers the exhaust molecular weight.
    '''
    case = CEA(fuelName = 'LH2', oxidizerName = 'LOX', chamberPressure = CHAMBERPRESSURE,
               expansionRatio = EXPANSIONRATIO, OFRatio = 'maxisp', pressureUnits = 'Pa')
    assert 3.5 <= case.OFRatio <= 5.5

def testBarPressureUnitsMatchPascals():
    '''
    pressureUnits='Bar' must give the same physical answer as Pa.
    '''
    inPascals = CEA(fuelName = 'LH2', oxidizerName = 'LOX',
                    chamberPressure = CHAMBERPRESSURE, expansionRatio = EXPANSIONRATIO,
                    OFRatio = MIXTURERATIO, pressureUnits = 'Pa')
    inBar = CEA(fuelName = 'LH2', oxidizerName = 'LOX',
                chamberPressure = CHAMBERPRESSURE / 1.0e5, expansionRatio = EXPANSIONRATIO,
                OFRatio = MIXTURERATIO, pressureUnits = 'Bar')
    assert inBar.ceaResults['combustionChamberTemperature'] == pytest.approx(
        inPascals.ceaResults['combustionChamberTemperature'], rel = 1e-9)

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- Propellant naming -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

@pytest.mark.parametrize('oxidizerName', ['LOX', 'lox', 'Oxygen', 'O2', 'LO2', 'liquid oxygen'])
def testOxidizerAliasesResolve(oxidizerName):
    '''
    Free-text oxidizer names from a config or spreadsheet cell must normalize.
    '''
    case = CEA(fuelName = 'LH2', oxidizerName = oxidizerName,
               chamberPressure = CHAMBERPRESSURE, expansionRatio = EXPANSIONRATIO,
               OFRatio = MIXTURERATIO, pressureUnits = 'Pa')
    assert case.ceaResults['combustionChamberTemperature'] == pytest.approx(3398.0, abs = 5.0)

@pytest.mark.parametrize('fuelName', ['LH2', 'H2', 'hydrogen', 'Liquid Hydrogen'])
def testFuelAliasesResolve(fuelName):
    '''
    Same for fuels.
    '''
    case = CEA(fuelName = fuelName, oxidizerName = 'LOX',
               chamberPressure = CHAMBERPRESSURE, expansionRatio = EXPANSIONRATIO,
               OFRatio = MIXTURERATIO, pressureUnits = 'Pa')
    assert case.ceaResults['combustionChamberTemperature'] == pytest.approx(3398.0, abs = 5.0)

def testUnknownPropellantRaisesWithGuidance():
    '''
    An unrecognized name must fail loudly and list the accepted alternatives, so
    a bad config value is diagnosable without reading source.
    '''
    with pytest.raises(ValueError, match = 'Unrecognized oxidizer'):
        CEA(fuelName = 'LH2', oxidizerName = 'unobtainium',
            chamberPressure = CHAMBERPRESSURE, expansionRatio = EXPANSIONRATIO,
            OFRatio = MIXTURERATIO)

def testCustomHdpeCardIsRegistered():
    '''
    HDPE is not in rocketcea's built-in card set and is registered from a card
    lifted verbatim from the legacy wrapper. This exercises the hybrid path.
    '''
    case = CEA(fuelName = 'HDPE', oxidizerName = 'LOX', chamberPressure = 3.0e6,
               expansionRatio = 10.0, OFRatio = 2.2, pressureUnits = 'Pa')
    # LOX/HDPE runs cooler than LOX/LH2 and produces a heavier exhaust
    assert 3000.0 <= case.ceaResults['combustionChamberTemperature'] <= 3800.0
    assert 20.0 <= case.ceaResults['combustionChamberMolecularWeight'] <= 30.0

# ------------------------------------------------------------------------------------------------------------------------------------ #
# -- Lazy result dictionary semantics -- #
# ------------------------------------------------------------------------------------------------------------------------------------ #

def testLazyResultsBehaveLikeADict(referenceCase):
    '''
    Results are computed per group on first access, so the mapping must still
    honour `in`, .get(), .keys() and iteration the way Nozzle.py expects.
    '''
    results = referenceCase.ceaResults
    assert 'combustionChamberGamma' in results
    assert 'notARealKey' not in results
    assert results.get('notARealKey') is None
    assert results.get('combustionChamberGamma') is not None
    # Enumerating must materialize everything
    assert len(list(results.keys())) > 40
    assert 'injectionTemperature' in dict(results.items())

def testExitKeysAbsentWithoutExitConditions():
    '''
    A contraction-ratio-only case must not advertise exit keys.
    '''
    case = CEA(fuelName = 'LH2', oxidizerName = 'LOX', chamberPressure = CHAMBERPRESSURE,
               contractionRatio = 3.0, OFRatio = MIXTURERATIO, pressureUnits = 'Pa')
    assert 'exitTemperature' not in case.ceaResults
    with pytest.raises(KeyError):
        case.ceaResults['exitTemperature']

def testInjectorStationMatchesInfiniteAreaChamber(referenceCase):
    '''
    With no finite area combustor, the injector face and chamber stations are
    the same thermodynamic state.
    '''
    results = referenceCase.ceaResults
    assert results['injectionTemperature'] == pytest.approx(
        results['combustionChamberTemperature'], rel = 1e-6)
    assert results['injectorMolecularWeight'] == pytest.approx(
        results['combustionChamberMolecularWeight'], rel = 1e-6)

def testSpeciesConcentrationsHaveStationStructure(referenceCase):
    '''
    Species fractions are keyed by species and then by station.
    '''
    massFractions = referenceCase.massFractions
    assert 'H2O' in massFractions
    assert set(massFractions['H2O']) == {'injector', 'chamber', 'throat', 'exit'}
    # Water is the dominant LOX/LH2 product
    assert massFractions['H2O']['chamber'] > 0.5

if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
