# -- Verification: The Accelerated Outer Iteration of a Multi-Pass Circuit -- #

'''

The accelerated outer iteration of a multi-pass coolant circuit against the plain one.

Three engines carry an outer iteration: the shipped nozzle (a one-and-a-half-pass jacket), the
F-1-like example (a two-pass jacket) and the methalox booster (a two-pass extension circuit). The
other three examples are single pass and have none. Each engine is run once to capture the inputs
its circuit is solved from, and the same circuit is then solved three ways:

1. Plain to 1e-4 K, the reference: the circuit settled well past the tolerance a run uses.
2. Plain to the 0.05 K a run uses.
3. Accelerated (Anderson, coolantCircuit._Accelerator) to 0.05 K.

and, to show the two iterations settle on one circuit, accelerated to 1e-4 K. Each is compared
with the reference station by station on both legs: coolant, metal hot wall and channel radius.

This is a verification of the iteration, not a validation of the circuit, whose status is that
of coolantCircuit.py: the reference is the same model solved further, not a measurement. Times
are wall clock on one desktop and move with load; pass counts do not.

Run from the NOVA root:

    python validation/coolingCircuits/circuitAcceleration.py

It takes about eleven minutes and writes circuitAcceleration/results.json.

Author: Sean Bowman

'''

import copy
import json
import os
import sys
import tempfile
import time

import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(here))
sys.path.insert(0, os.path.join(root, 'src'))
os.environ.setdefault('NOVA_HEADLESS', '1')

import NOVA.coolantCircuit as coolantCircuit
import NOVA.extensionCircuit as extensionCircuit
import NOVA.regenChannels as regenChannels
from NOVA import Nozzle

outputFolder = os.path.join(here, 'circuitAcceleration')
assets = os.path.join(root, 'src', 'NOVA', 'assets')
engines = {
    'shipped nozzle':   os.path.join(assets, 'NOVANozzle.json'),
    'keroloxF1':        os.path.join(assets, 'examples', 'keroloxF1.json'),
    'methaloxBooster':  os.path.join(assets, 'examples', 'methaloxBooster.json'),
}
runTolerance = 0.05         # [K] the outer iteration's tolerance in a run
referenceTolerance = 1e-4   # [K]
solves = {
    'reference':          {'accelerate': False, 'tolerance': referenceTolerance},
    'plain':              {'accelerate': False, 'tolerance': runTolerance},
    'accelerated':        {'accelerate': True,  'tolerance': runTolerance},
    'acceleratedSettled': {'accelerate': True,  'tolerance': referenceTolerance},
}

def captureCircuits(configPath: str) -> list:

    '''Run an engine with no outputs and return the (args, kwargs) of each circuit it solves.'''

    captured = []
    solve = coolantCircuit.solveCoolantCircuit

    def recorder(*args, **kwargs):
        captured.append((copy.deepcopy(args), copy.deepcopy(kwargs)))
        return solve(*args, **kwargs)

    with open(configPath, encoding = 'utf-8') as handle:
        config = json.load(handle)
    # No figures, files or plume: the circuit's inputs come before all three
    config.update({'plotsEnabled': False, 'export': False, 'filename': 'acceleration',
                   'plumeAmbientPressure': None, 'plumeFieldReach': None})
    work = tempfile.mkdtemp(prefix = 'novaAcceleration')
    path = os.path.join(work, 'acceleration.json')
    with open(path, 'w', encoding = 'utf-8', newline = '\n') as handle:
        json.dump(config, handle)

    # Both modules import the solve by name, so both names are swapped for the run
    original = Nozzle._getOutputRoot
    regenChannels.solveCoolantCircuit = extensionCircuit.solveCoolantCircuit = recorder
    Nozzle._getOutputRoot = lambda self: work
    try:
        Nozzle().generateNozzle(configPath = path)
    finally:
        regenChannels.solveCoolantCircuit = extensionCircuit.solveCoolantCircuit = solve
        Nozzle._getOutputRoot = original
    return captured

def legFields(solution) -> dict:

    '''Both legs' coolant [K], metal hot wall [K] and channel radius [m], by station.'''

    fields = {}
    for leg in (solution.down, solution.up):
        results = leg.results
        fields[f'{leg.name}Coolant'] = np.asarray(results['temperature'], dtype = float)
        fields[f'{leg.name}Wall'] = np.asarray(results.get('metalWallTemperature', results['wallTemperature']),
                                               dtype = float)
        fields[f'{leg.name}Radius'] = np.asarray(leg.state.channelRadius, dtype = float)
    return fields

def againstReference(fields: dict, reference: dict) -> dict:

    '''Largest difference from the reference over both legs: coolant and wall [K], radius relative [-].'''

    def largest(kind: str, relative: bool = False) -> float:
        worst = 0.0
        for leg in ('down', 'up'):
            difference = np.abs(fields[leg + kind] - reference[leg + kind])
            if relative:
                difference = difference / np.abs(reference[leg + kind])
            worst = max(worst, float(difference.max()))
        return worst

    return {'coolant': largest('Coolant'), 'wall': largest('Wall'), 'radius': largest('Radius', relative = True)}

def main() -> None:

    os.makedirs(outputFolder, exist_ok = True)
    report = {'runTolerance': runTolerance, 'referenceTolerance': referenceTolerance, 'engines': {}}
    for engine, configPath in engines.items():
        print(f'{engine}: capturing its circuits', flush = True)
        circuits = captureCircuits(configPath)
        report['engines'][engine] = []
        for args, kwargs in circuits:
            entry, reference = {'circuit': args[3]}, None
            for name, settings in solves.items():
                start = time.perf_counter()
                solution = coolantCircuit.solveCoolantCircuit(*copy.deepcopy(args),
                                                              **{**copy.deepcopy(kwargs), **settings,
                                                                 'maxIterations': 80})
                seconds = time.perf_counter() - start
                fields = legFields(solution)
                if reference is None:
                    reference = fields
                entry[name] = {'passes': solution.iterations, 'seconds': round(seconds, 1),
                               'lastChange': solution.history[-1],
                               'againstReference': againstReference(fields, reference)}
            report['engines'][engine].append(entry)

    print(f'\n{"engine":17} {"circuit":15} {"plain":>13} {"accelerated":>13} '
          f'{"plain error":>12} {"accel. error":>12} {"settled apart":>14}')
    for engine, entries in report['engines'].items():
        for entry in entries:
            plain, accelerated = entry['plain'], entry['accelerated']
            print(f'{engine:17} {entry["circuit"]:15} '
                  f'{plain["passes"]:>3} in {plain["seconds"]:5.1f} s {accelerated["passes"]:>3} in '
                  f'{accelerated["seconds"]:5.1f} s {plain["againstReference"]["coolant"]:10.4f} K '
                  f'{accelerated["againstReference"]["coolant"]:10.4f} K '
                  f'{entry["acceleratedSettled"]["againstReference"]["coolant"]:12.2e} K')

    with open(os.path.join(outputFolder, 'results.json'), 'w', encoding = 'utf-8', newline = '\n') as handle:
        json.dump(report, handle, indent = 1)
        handle.write('\n')

if __name__ == '__main__':
    main()
