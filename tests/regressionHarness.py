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

# The cases the harness records. Each names a configuration in assets/ and the overrides that
# make it a harness run rather than a user run: no figures, no export, no plume.
harnessCases = {
    'contour': {
        'config': 'loxLh2Example.json',
        'description': 'Diverging contour, converging section and regen truncation, no jacket',
    },
    'regenCircle': {
        'config': 'regenExample.json',
        'description': 'Full jacket with circular channels and both volutes',
    },
    'regenFluted': {
        'config': 'regenExampleFluted.json',
        'description': 'Full jacket with fluted channels and both volutes',
    },
}

harnessOverrides = {
    'plotsBasic'          : False,
    'plotsAdv'            : False,
    'plotJacket'          : False,
    'plotsDebug'          : False,
    'visualizeContour'    : False,
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

    Returns:
    --------
    Nozzle
        The generated object, with every attribute the run set.

    '''

    import matplotlib
    matplotlib.use('Agg', force = True)

    from NOVA.Nozzle import Nozzle

    case = harnessCases[caseName]
    configPath = os.path.join(packageDirectory, 'assets', case['config'])
    with io.open(configPath, encoding = 'utf-8') as handle:
        config = json.load(handle)
    config.update(harnessOverrides)
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
