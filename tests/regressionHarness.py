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

Baselines are written to tests/baselines/ and are not carried in the repository, so a fresh
checkout records its own before it starts moving code.

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
packageDirectory = os.path.join(repositoryRoot, 'NOVANozzleDesigner')
baselineFolder   = os.path.join(harnessDirectory, 'baselines')

sys.path.insert(0, packageDirectory)

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

    from Nozzle import Nozzle

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

    Parameters:
    -----------
    reference, candidate : dict
        States from captureState.

    Returns:
    --------
    list
        One string per difference. Empty means bit-identical.

    '''

    differences = []

    missing = sorted(set(reference) - set(candidate))
    added   = sorted(set(candidate) - set(reference))

    for name in missing:
        differences.append(f'{name}: present in baseline, absent now')
    for name in added:
        differences.append(f'{name}: absent from baseline, present now')

    for name in sorted(set(reference) & set(candidate)):

        before, after = reference[name], candidate[name]

        if isinstance(before, np.ndarray) != isinstance(after, np.ndarray):
            differences.append(f'{name}: type changed, {type(before).__name__} to {type(after).__name__}')
            continue

        if isinstance(before, np.ndarray):
            if before.shape != after.shape:
                differences.append(f'{name}: shape changed, {before.shape} to {after.shape}')
                continue
            # NaN is a legitimate value here, so it has to compare equal to itself.
            unequal = ~((before == after) | (np.isnan(before) & np.isnan(after))) \
                      if before.dtype.kind == 'f' else before != after
            count = int(np.count_nonzero(unequal))
            if count:
                worst = float(np.nanmax(np.abs(before[unequal] - after[unequal]))) \
                        if before.dtype.kind == 'f' else float('nan')
                differences.append(f'{name}: {count} of {before.size} elements differ, '
                                   f'largest difference {worst:.6e}')
            continue

        if isinstance(before, float) and isinstance(after, float):
            if not (before == after or (np.isnan(before) and np.isnan(after))):
                differences.append(f'{name}: {before!r} to {after!r}')
            continue

        if before != after:
            differences.append(f'{name}: {before!r} to {after!r}')

    return differences

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
            differences = compareStates(state, repeat)
            if differences:
                failures += 1
                print(f'   NOT DETERMINISTIC: {len(differences)} differences between two runs')
                for line in differences[:20]:
                    print(f'      {line}')
            else:
                print('   deterministic: two runs identical to the bit')

        if arguments.record:
            writeBaseline(caseName, state)
            print(f'   baseline written to {baselinePath(caseName)}')

        if arguments.compare:
            differences = compareStates(readBaseline(caseName), state)
            if differences:
                failures += 1
                print(f'   CHANGED: {len(differences)} differences against the baseline')
                for line in differences[:40]:
                    print(f'      {line}')
            else:
                print('   identical to the baseline')

    print()
    print('all cases clean' if failures == 0 else f'{failures} case(s) reported differences')

    return 1 if failures else 0

if __name__ == '__main__':
    raise SystemExit(main())
