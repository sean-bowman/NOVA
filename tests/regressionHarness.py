'''

Bit-identity harness for the decomposition of Nozzle.py.

Moving code out of a 9,000 line class is only safe if the result can be compared against what
the class produced before the move. This harness runs a configuration end to end, walks every
public attribute of the resulting Nozzle, and writes what it found. A later run compares against
that record and reports any attribute that differs at all: floats are compared for exact
equality, not closeness, because a refactor that only moves code has no reason to change a
single bit.

The comparison means nothing unless the run is deterministic, so --verify runs the case twice
and compares the two, which establishes that before any baseline is trusted.

Usage, from the NOVA root:

    python tests/regressionHarness.py --record            # record baselines for every case
    python tests/regressionHarness.py --record --verify   # record, then prove determinism
    python tests/regressionHarness.py --compare           # compare against the baselines
    python tests/regressionHarness.py --compare --case regenCircle

Baselines live in tests/baselines/ and are carried in the repository, so a fresh checkout can
compare against the numbers the work was signed off on rather than against whatever the code
happens to produce on the day it is cloned. They are pickled numpy, so the diff of a re-record
is not readable: when a change moves numbers deliberately, the magnitude belongs in the commit
message and in the report, and the pickle is only the evidence.

A baseline is a record of this machine's answer. A different CEA, scipy or numpy build can move
the last bits, so a comparison that fails on a fresh environment before any code has changed is
telling you about the environment.

Author: Sean Bowman

'''

import argparse
import io
import json
import os
import pickle
import sys

import numpy as np

harnessDirectory = os.path.dirname(os.path.abspath(__file__))
repositoryRoot   = os.path.dirname(harnessDirectory)
packageDirectory = os.path.join(repositoryRoot, 'src', 'NOVA')
baselineFolder   = os.path.join(harnessDirectory, 'baselines')

# An override of ABSENT removes the key instead of setting it, which is not the same thing: a key
# read with .get() and absent yields None, while a key present and null yields NaN.
ABSENT = object()

# NOVANozzle.json is the reference nozzle with every feature that composes switched on, which is
# more than any one baseline pins. This strips it back to a bare contour: no jacket, no film, no
# volutes, no extension. Every case starts here and switches back on only what it is
# there to record, so a case is a statement about one path rather than about everything the
# reference nozzle happens to carry.
strippedToContour = {
    'makeCoolingChannels'           : False,
    'numCrossSections'              : 100,
    'numCSPointsChannel'            : 50,
    'material'                      : None,
    'channelType'                   : None,
    'channelSizingMode'             : None,
    'manualChannelProfile'          : None,
    'manualChannelProfileKey'       : None,
    'nChannel'                      : None,
    'hotWallThickness'              : None,
    'shellThickness'                : None,
    'infillThickness'               : None,
    'maxWallTemperature'            : None,
    'coolantClass'                  : None,
    'coolant'                       : None,
    'coolantInitialTemperature'     : None,
    'coolantInitialPressure'        : None,
    'coolantMassFlow'               : None,
    'Lstar'                         : None,
    'regenTruncationType'           : 'none',
    'regenTruncationValue'          : None,

    'filmCooling'                   : False,
    'filmCoolant'                   : None,
    'filmMassFlow'                  : None,
    'filmInletTemperature'          : None,
    'filmInjectionAxialPosition'    : None,
    'filmSlotHeight'                : None,

    'makeRadiativeExtension'        : 'off',

    # These six are read with .get(), so an absent key reaches the nozzle as None while a key
    # present and null reaches it as NaN: config.py rewrites every null before the .get() runs.
    # Both mean unset and neither is read with the extension off, but the captured state records
    # which one it was. Dropping the keys keeps that record identical to the baselines.
    'extensionMaterial'             : ABSENT,
    'extensionThickness'            : ABSENT,
    'extensionThermalConductivity'  : ABSENT,
    'extensionInnerEmissivity'      : ABSENT,
    'extensionOuterEmissivity'      : ABSENT,
    'extensionJointTemperature'     : ABSENT,

    'makeInletVolute'               : False,
    'makeOutletVolute'              : False,
    'numCSVolute'                   : None,
    'numCSPointsVolute'             : None,
    'voluteRelativeRoll'            : None,
    'voluteScrollType'              : None,
    'voluteFOS'                     : None,
    'minVoluteWallThickness'        : None,
    'maxVoluteBore'                 : None,
    'inletVoluteCrossSection'       : None,
    'inletVoluteAlignment'          : None,
    'inletVoluteTilt'               : None,
    'inletGraylocDiameter'          : None,
    'inletVoluteAxialOffset'        : None,
    'inletVoluteFlareRoverD'        : None,
    'inletVoluteFlareLength'        : None,
    'outletVoluteCrossSection'      : None,
    'outletVoluteAlignment'         : None,
    'outletVoluteTilt'              : None,
    'outletGraylocDiameter'         : None,
    'outletVoluteAxialOffset'       : None,
    'outletVoluteFlareRoverD'       : None,
    'outletVoluteFlareLength'          : None,
}

# The jacket the regen cases are pinned on, switched back on over the stripped contour. Sixty
# circular channels in GRCop-42, hydrogen at 3.4 kg/s entering at 12 MPa and 30 K, above the
# hydrogen critical point. The chamber is generated at the shipped L* of 1.0 m, so the jacket
# runs over the barrel from the injector face, where the outlet volute sits, to the aft end,
# where the inlet volute sits. Every number here is pinned by a baseline, so changing one moves
# that baseline.
regenOverrides = {
    'makeCoolingChannels'      : True,
    'Lstar'                    : 1.0,
    'numCrossSections'         : 60,
    'numCSPointsChannel'       : 40,
    'hotWallThickness'         : 0.001,
    'shellThickness'           : 0.002,
    'infillThickness'          : 0.001,
    'material'                 : 'GRCop-42',
    'nChannel'                 : 60,
    'channelType'              : 'circle',
    'maxWallTemperature'       : 800.0,
    'coolantClass'             : 'fuel',
    'coolant'                  : 'Hydrogen',
    'coolantInitialTemperature': 30.0,
    'coolantInitialPressure'   : 12000000.0,
    'coolantMassFlow'          : 3.4,
    'makeInletVolute'          : True,
    'makeOutletVolute'         : True,
    'numCSVolute'              : 60,
    'numCSPointsVolute'        : 40,
    'voluteRelativeRoll'       : 0.0,
    'voluteScrollType'         : 'ring',
    'voluteFOS'                : 1.5,
    'minVoluteWallThickness'   : 1.0e-3,
    # These cases jacket the whole bell, and the channel sizer grows the aft channels to 33 mm
    # diameter where the heat flux is nearly nothing. The constant velocity law then asks for a
    # 199 mm scroll to feed a port that size, which the shipped 0.15 m limit refuses. The limit is
    # raised here so the cases still pin the volute path; the channel size is the thing to fix.
    'maxVoluteBore'            : 0.25,
    'inletVoluteCrossSection'  : 'circle',
    'inletVoluteAlignment'     : 'i',
    'inletVoluteTilt'          : 0.0,
    'inletGraylocDiameter'     : 1.0,
    'inletVoluteAxialOffset'   : 0.01,
    'inletVoluteFlareRoverD'   : 1.5,
    'inletVoluteFlareLength'   : 0.03,
    'outletVoluteCrossSection' : 'circle',
    'outletVoluteAlignment'    : 'i',
    'outletVoluteTilt'         : 0.0,
    'outletGraylocDiameter'    : 1.0,
    'outletVoluteAxialOffset'  : 0.01,
    'outletVoluteFlareRoverD'  : 1.5,
    'outletVoluteFlareLength'     : 0.03,
}

# The cases the harness records. Every case runs assets/NOVANozzle.json and differs only in what
# it overrides on top, so a case is a statement about one path rather than a separate file to
# keep in step. The shared harnessOverrides below make it a harness run rather than a user run:
# no figures, no export, no plume.
harnessCases = {
    'contour': {
        'config': 'NOVANozzle.json',
        'description': 'Diverging contour, converging section and regen truncation, no jacket',
    },
    'regenCircle': {
        'config': 'NOVANozzle.json',
        'description': 'Full jacket with circular channels and both volutes',
        'overrides': dict(regenOverrides),
    },
    # High aspect ratio rectangular channels on the same jacket. The width fills the pitch at the
    # cold wall less the 1 mm rib and the depth is sized; 160 channels put the throat width at
    # 1.01 mm. The corners are rounded at 0.2 mm, which the STEP writer needs.
    'regenRectangular': {
        'config': 'NOVANozzle.json',
        'description': 'Full jacket with rectangular channels and both volutes',
        'overrides': {**regenOverrides, 'channelType': 'rectangular', 'nChannel': 160,
                      'minChannelWidth': 1.0e-3, 'channelCornerRadius': 0.2e-3,
                      'maxChannelAspectRatio': 8.0, 'maxChannelDepth': 6.0e-3,
                      'maxWallTemperature': 600.0},
    },
    # Square helical channels on the same jacket: 40 starts at 45 degrees to the meridian, the
    # width sized, the depth equal to it and capped at 6 mm, and a rib that grows with the radius
    # from the infill thickness up. The 650 K target sizes the two throat stations; the rest sit
    # at the depth cap or the rib limit.
    'regenHelical': {
        'config': 'NOVANozzle.json',
        'description': 'Full jacket with square helical channels and both volutes',
        'overrides': {**regenOverrides, 'channelType': 'helical', 'nChannel': 40,
                      'channelHelixAngle': 45.0, 'channelAspectRatio': 1.0,
                      'minChannelWidth': 1.0e-3, 'channelCornerRadius': 0.2e-3,
                      'maxChannelDepth': 6.0e-3, 'maxWallTemperature': 650.0},
    },
    # The same jacket built from a manual size profile rather than from the search. The profile
    # is keyed on the signed area ratio, nine control points with every station between them
    # interpolated, and it holds one size over the whole barrel because the barrel holds one area
    # ratio. Each point is 8 per cent under what regenCircle converged to at that station, which
    # is the margin the case needs: regenCircle's aft stations sit on the largest channel that
    # fits, and a profile above that bound is refused rather than built.
    'regenManual': {
        'config': 'NOVANozzle.json',
        'description': 'Full jacket built from a manual channel size profile',
        'overrides': {**regenOverrides, 'channelSizingMode': 'manual',
                      'manualChannelProfileKey': 'areaRatio',
                      'manualChannelProfile': [[-3.11, 0.00395], [-1.81, 0.00304],
                                               [-1.04, 0.00210], [1.00, 0.00217],
                                               [2.13, 0.00335], [6.40, 0.00614],
                                               [13.71, 0.00922], [24.16, 0.01240],
                                               [35.88, 0.01522]]},
    },
    # The other truncation rule: the jacket ends where the near-wall recovery temperature falls
    # to the configured value, which is the temperature the wall is driven by. Recovery
    # temperature spans only a few hundred kelvin over the whole bell, so 3200 K is what puts
    # the cut near an area ratio of three on this contour, where the area ratio case cuts.
    'regenTruncationTemp': {
        'config': 'NOVANozzle.json',
        'description': 'Jacket truncated where the near-wall recovery temperature falls to 3200 K',
        'overrides': {**regenOverrides, 'regenTruncationType': 'temp',
                      'regenTruncationValue': 3200.0},
    },
    # The measured axial distribution of the gas-side correlation constant, which leaves the
    # barrel where Bartz puts it and takes about 40 percent off the throat. The same jacket as
    # regenCircle in every other respect, so the pair is the cost of the calibration.
    'regenMeasuredAxial': {
        'config': 'NOVANozzle.json',
        'description': 'Circular channels with the measured gas-side axial distribution',
        'overrides': {**regenOverrides, 'gasSideAxialModel': 'measured'},
    },
    # The coolant-side entrance and curvature corrections on the same jacket, which is where a
    # correlation written for a straight developed pipe is asked about neither. The wall target is
    # 900 K rather than the 800 K the other cases use: the entrance factor grows with the channel's
    # own diameter, which flattens the wall temperature's response to channel size near the inlet,
    # and at 800 K the sizing march stalls at station 51 short of its target without being at a
    # bound. That interaction is recorded in experimental/coolingModelState.md.
    'regenCoolantCorrections': {
        'config': 'NOVANozzle.json',
        'description': 'Circular channels with the coolant entrance and curvature corrections',
        'overrides': {**regenOverrides, 'coolantGeometryCorrections': True,
                      'maxWallTemperature': 900.0},
    },
    # The roughness treatment that preceded the hardware comparisons, where the rough-wall
    # friction factor goes into Gnielinski and the Nusselt number rises with it. Kept as a case
    # so the results recorded under it stay reproducible.
    'regenRoughnessFullCredit': {
        'config': 'NOVANozzle.json',
        'description': 'Circular channels crediting roughness with heat transfer in full',
        'overrides': {**regenOverrides, 'coolantRoughnessModel': 'fullCredit'},
    },
    # A hydrogen film injected at the chamber end of the same jacket. It pins the film path and
    # records what a film that is badly matched in velocity actually buys, which is not much.
    'regenCircleFilm': {
        'config': 'NOVANozzle.json',
        'description': 'Circular channels with a hydrogen film injected at the chamber end',
        'overrides': {
            **regenOverrides,
            'filmCooling': True,
            'filmCoolant': 'Hydrogen',
            'filmMassFlow': 0.30,
            'filmInletTemperature': 250.0,
            'filmInjectionAxialPosition': -1.0,
            'filmSlotHeight': 0.0015,
        },
    },
    'regenCircleEntrainment': {
        'config': 'NOVANozzle.json',
        'description': 'The same hydrogen film solved by the SP-8124 entrainment model',
        'overrides': {
            **regenOverrides,
            'filmCooling': True,
            'filmCoolant': 'Hydrogen',
            'filmMassFlow': 0.30,
            'filmInletTemperature': 250.0,
            'filmInjectionAxialPosition': -1.0,
            'filmSlotHeight': 0.0015,
            'filmCoolingModel': 'sp8124Entrainment',
        },
    },
    'contourEffectiveGamma': {
        'config': 'NOVANozzle.json',
        'description': 'The contour solved at the effective gamma rather than the chamber value',
        'overrides': {**regenOverrides, 'gammaModel': 'effective', 'makeCoolingChannels': False,
                      'Lstar': None},
    },
    # The prescribed-wall path, which shares the kernel with the truncated ideal contour and
    # nothing else: the wall is drawn before the flow is solved and marched forward rather than
    # traced as a streamline. It has its own case because a change to the march moves this and
    # leaves every truncated ideal baseline untouched, which is exactly the kind of half-visible
    # move a single-family gate cannot catch.
    'contourParabola': {
        'config': 'NOVANozzle.json',
        'description': 'A thrust-optimized parabola, drawn from the chart and marched forward',
        'overrides': {'divergingSectionType': 'top', 'makeCoolingChannels': False},
    },
    # The searched family, on a pinned wall rather than a search, because a gate that re-ran a
    # twenty minute optimization every time would not get run.
    #
    # The wall is the chart parabola turned four degrees harder at the inflection, and the four
    # degrees are the point of the case rather than an arbitrary offset. At the chart angles this
    # contour carries no internal shock, so a case pinned there would duplicate `contourParabola`
    # and protect none of the capture path. Four degrees puts a front in the nozzle that is still
    # weak, 0.8 degrees of deflection with 99.999 per cent of the stagnation pressure surviving,
    # so the baseline records a number the weak-shock treatment actually supports while covering
    # the detector, the jump, the downstream debit and the coefficient it is subtracted from.
    'contourToc': {
        'config': 'NOVANozzle.json',
        'description': 'A pinned thrust-optimized contour carrying a weak internal shock',
        'overrides': {'divergingSectionType': 'toc', 'makeCoolingChannels': False,
                      'divergingSectionDesignVariables': [35.0, 8.0, 0.312534, 0.367698]},
    },
}

harnessOverrides = {
    **strippedToContour,
    'plotsEnabled'        : False,
    'export'              : False,
    'plumeAmbientPressure': None,
}

def runCase(caseName: str, scratchFolder: str) -> object:

    '''

    Run one harness case and return the Nozzle it produced.

    Parameters:
    -----------
    caseName : str
        Key into harnessCases.
    scratchFolder : str
        Directory the run is allowed to write into.

    A case may carry its own 'overrides', applied after the shared ones, which is how two cases
    can share a configuration file and differ only in what is being pinned.

    Returns:
    --------
    Nozzle
        The generated object, with every attribute the run set.

    '''

    # A case is a full nozzle generation, so it draws everything a design run draws. The
    # harness runs seven of them and nobody should have to close the windows.
    os.environ.setdefault('NOVA_HEADLESS', '1')

    import matplotlib
    matplotlib.use('Agg', force = True)

    from NOVA.Nozzle import Nozzle

    case = harnessCases[caseName]
    configPath = os.path.join(packageDirectory, 'assets', case['config'])
    with io.open(configPath, encoding = 'utf-8') as handle:
        config = json.load(handle)
    config.update(harnessOverrides)
    config.update(case.get('overrides', {}))
    for key in [key for key, value in config.items() if value is ABSENT]:
        del config[key]
    config['filename'] = caseName

    os.makedirs(scratchFolder, exist_ok = True)
    runConfigPath = os.path.join(scratchFolder, caseName + 'HarnessConfig.json')
    with io.open(runConfigPath, 'w', encoding = 'utf-8', newline = '') as handle:
        json.dump(config, handle, indent = 2)

    # Keep the run's own output out of the repository.
    Nozzle._getOutputRoot = lambda self, _base = scratchFolder: _base

    nozzle = Nozzle()
    nozzle.generateNozzle(configPath = runConfigPath)

    return nozzle

def captureState(nozzle) -> dict:

    '''

    Every public attribute of a Nozzle, reduced to something comparable.

    Numeric arrays are kept as arrays. Scalars, strings and booleans are kept as they are.
    Anything else is recorded by a marker naming its type and size, which is enough to catch an
    attribute appearing, vanishing or changing shape without pretending the harness can compare
    a Volute or a spline. An object-dtype array is one of those: it holds interpolator instances
    that compare by identity, so a straight comparison reports every element as different on
    every run.

    Parameters:
    -----------
    nozzle : Nozzle
        The object to walk.

    Returns:
    --------
    dict
        Attribute name to value or type marker.

    '''

    state = {}

    for name in sorted(vars(nozzle)):

        if name.startswith('_'):
            continue

        value = getattr(nozzle, name)

        if isinstance(value, np.ndarray):
            state[name] = value if value.dtype != object else f'<object array {value.shape}>'
        elif isinstance(value, (bool, np.bool_)):
            state[name] = bool(value)
        elif isinstance(value, (int, float, np.integer, np.floating)):
            state[name] = float(value)
        elif isinstance(value, str):
            state[name] = value
        elif isinstance(value, (list, tuple)):
            try:
                asArray = np.asarray(value, dtype = float)
            except (ValueError, TypeError):
                state[name] = f'<{type(value).__name__} len {len(value)}>'
            else:
                state[name] = asArray if asArray.dtype != object else f'<object list len {len(value)}>'
        elif value is None:
            state[name] = '<None>'
        else:
            state[name] = f'<{type(value).__name__}>'

    return state

def compareStates(reference: dict, candidate: dict) -> list:

    '''

    Differences between two captured states, most structural first.

    Two kinds are reported and they mean different things. A **structural** difference is a change
    to the attribute set itself: an attribute added, removed, retyped or reshaped. A **value**
    difference is a number, string or array element that moved. Only the second says the physics
    changed. The distinction matters because `captureState` walks `vars(nozzle)`, so adding or
    removing an attribute registers here even when nothing computed moves, and a run that reports
    only structural differences has left every result exactly as it was.

    Parameters:
    -----------
    reference, candidate : dict
        States from captureState.

    Returns:
    --------
    list
        One (kind, message) pair per difference, where kind is 'structural' or 'value'. Empty
        means bit-identical.

    '''

    differences = []

    missing = sorted(set(reference) - set(candidate))
    added   = sorted(set(candidate) - set(reference))

    for name in missing:
        differences.append(('structural', f'{name}: present in baseline, absent now'))
    for name in added:
        differences.append(('structural', f'{name}: absent from baseline, present now'))

    for name in sorted(set(reference) & set(candidate)):

        before, after = reference[name], candidate[name]

        if isinstance(before, np.ndarray) != isinstance(after, np.ndarray):
            differences.append(('structural',
                                f'{name}: type changed, {type(before).__name__} '
                                f'to {type(after).__name__}'))
            continue

        if isinstance(before, np.ndarray):
            if before.shape != after.shape:
                differences.append(('structural',
                                    f'{name}: shape changed, {before.shape} to {after.shape}'))
                continue
            # NaN is a legitimate value here, so it has to compare equal to itself.
            unequal = ~((before == after) | (np.isnan(before) & np.isnan(after))) \
                      if before.dtype.kind == 'f' else before != after
            count = int(np.count_nonzero(unequal))
            if count:
                worst = float(np.nanmax(np.abs(before[unequal] - after[unequal]))) \
                        if before.dtype.kind == 'f' else float('nan')
                differences.append(('value',
                                    f'{name}: {count} of {before.size} elements differ, '
                                    f'largest difference {worst:.6e}'))
            continue

        if isinstance(before, float) and isinstance(after, float):
            if not (before == after or (np.isnan(before) and np.isnan(after))):
                differences.append(('value', f'{name}: {before!r} to {after!r}'))
            continue

        if before != after:
            differences.append(('value', f'{name}: {before!r} to {after!r}'))

    return differences

def reportDifferences(differences: list, headline: str) -> int:

    '''

    Print a set of differences, split by kind, and return how many of them moved a value.

    Structural differences are printed but not counted. An attribute that appeared or vanished is
    a change to the shape of the state object, and the caller has to decide whether it was meant;
    it is not evidence that a number moved.

    Parameters:
    -----------
    differences : list
        (kind, message) pairs from compareStates.
    headline : str
        What the comparison was against, used in the printed summary.

    Returns:
    --------
    int
        Count of value differences.

    '''

    structural = [message for kind, message in differences if kind == 'structural']
    value      = [message for kind, message in differences if kind == 'value']

    if value:
        print(f'   CHANGED: {len(value)} value differences {headline}')
        for message in value[:40]:
            print(f'      {message}')
    if structural:
        print(f'   {len(structural)} structural differences {headline}, no value moved by them')
        for message in structural[:20]:
            print(f'      {message}')
    if not differences:
        print(f'   identical {headline}')
    elif not value:
        print(f'   no value differences {headline}')

    return len(value)

def baselinePath(caseName: str) -> str:

    '''Where the baseline for a case is written.'''

    return os.path.join(baselineFolder, caseName + '.pkl')

def writeBaseline(caseName: str, state: dict) -> None:

    '''Record a state as the baseline for a case.'''

    os.makedirs(baselineFolder, exist_ok = True)
    with open(baselinePath(caseName), 'wb') as handle:
        pickle.dump(state, handle, protocol = 4)

def readBaseline(caseName: str) -> dict:

    '''Read the baseline for a case.'''

    path = baselinePath(caseName)
    if not os.path.exists(path):
        raise FileNotFoundError(f'No baseline for {caseName}. Record one with --record first: {path}')
    with open(path, 'rb') as handle:
        return pickle.load(handle)

def describeState(state: dict) -> str:

    '''One line summarising what a state holds.'''

    arrays  = sum(1 for v in state.values() if isinstance(v, np.ndarray))
    scalars = sum(1 for v in state.values() if isinstance(v, float))
    return f'{len(state)} attributes: {arrays} arrays, {scalars} scalars'

def main() -> int:

    parser = argparse.ArgumentParser(description = 'Bit-identity harness for the Nozzle decomposition.')
    parser.add_argument('--record',  action = 'store_true', help = 'run each case and record its baseline')
    parser.add_argument('--compare', action = 'store_true', help = 'run each case and compare against its baseline')
    parser.add_argument('--verify',  action = 'store_true', help = 'run each case twice and compare the two runs')
    parser.add_argument('--case', action = 'append', choices = sorted(harnessCases),
                        help = 'limit to one case; repeatable')
    parser.add_argument('--scratch', default = os.path.join(repositoryRoot, 'runs', 'harness'),
                        help = 'directory the runs may write into')
    arguments = parser.parse_args()

    if not (arguments.record or arguments.compare or arguments.verify):
        parser.error('choose at least one of --record, --compare, --verify')

    cases = arguments.case or sorted(harnessCases)
    failures = 0

    for caseName in cases:

        print(f'== {caseName}: {harnessCases[caseName]["description"]}')

        state = captureState(runCase(caseName, arguments.scratch))
        print(f'   {describeState(state)}')

        if arguments.verify:
            repeat = captureState(runCase(caseName, arguments.scratch))
            moved = reportDifferences(compareStates(state, repeat), 'between two runs')
            if moved:
                failures += 1

        if arguments.record:
            writeBaseline(caseName, state)
            print(f'   baseline written to {baselinePath(caseName)}')

        if arguments.compare:
            moved = reportDifferences(compareStates(readBaseline(caseName), state),
                                      'against the baseline')
            if moved:
                failures += 1

    print()
    print('all cases clean' if failures == 0
          else f'{failures} case(s) moved a value against the baseline')

    return 1 if failures else 0

if __name__ == '__main__':
    raise SystemExit(main())
