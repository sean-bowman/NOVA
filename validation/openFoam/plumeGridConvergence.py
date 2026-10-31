# -- NOVA Plume: Grid Convergence of the OpenFOAM Case -- #

'''

Richardson extrapolation and grid convergence index across the coarse, medium and fine plume cases.

Each grid has twice the cells of the last in each direction, so the refinement ratio is 2. The
estimate is `gridConvergence.richardson`, the one the nozzle case uses. The quantities are the jet
boundary's radius where NOVA's march ends, its angle at the lip, and the plume structure the
correlations predict: the Mach disk's distance from the exit plane and its diameter, the first
shock cell's length and the boundary's widest radius.

Run after `comparePlume.py` has run on each case:

    python3 plumeGridConvergence.py <coarse case> <medium case> <fine case> [--output <folder>]

Writes `plumeGridConvergence.json` and `plumeGridConvergence.png` to the output folder, the fine
case's `comparison` folder by default. Needs NumPy and Matplotlib.

Author: Sean Bowman

'''

import argparse
import json
import os

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from compareWithNova import applyStyle
from gridConvergence import richardson

# What each quantity is read from in a case's comparison, its label, and NOVA's value beside it
quantities = {
    'boundaryRadiusAtEndOfMarch': (lambda c: c['boundary']['endOfMarch']['openFoam'],
                                   'boundary radius at the march end\n/ station radius',
                                   lambda c: c['boundary']['endOfMarch']['march']),
    'lipBoundaryAngle': (lambda c: c['boundary']['angleDegrees']['openFoam'], 'boundary angle at the lip [deg]',
                         lambda c: c['boundary']['angleDegrees']['march']),
    'axisShockLocation': (lambda c: c['machDisk']['xFromExit'], 'first axis shock from the exit plane / station radius',
                          lambda c: c['structure']['axisShockLocation']['correlation'] / c['stationRadius']),
    'machDiskDiameter': (lambda c: 2.0 * c['machDisk']['radiusOverStation'], 'Mach disk diameter / station radius',
                         lambda c: c['structure']['machDiskDiameter']['correlation'] / c['stationRadius']),
    'shockCellLength': (lambda c: c['firstCell']['neckX'], 'first shock cell length / station radius',
                        lambda c: c['structure']['shockCellLength']['correlation'] / c['stationRadius']),
    'maximumBoundaryRadius': (lambda c: c['firstCell']['maxRadius'], 'widest boundary radius / station radius',
                              lambda c: c['structure']['maximumBoundaryRadius']['correlation'] / c['stationRadius']),
}

# The medium grid within these fractions of the fine grid
mediumToFineLimits = {'boundaryRadiusAtEndOfMarch': 0.005, 'axisShockLocation': 0.02}

def main() -> None:

    parser = argparse.ArgumentParser(description = 'Grid convergence of the OpenFOAM NOVA plume cases.')
    parser.add_argument('cases', nargs = 3, help = 'coarse, medium and fine case folders')
    parser.add_argument('--output', default = None)
    arguments = parser.parse_args()

    results = []
    for case in arguments.cases:
        with open(os.path.join(case, 'comparison', 'comparison.json'), encoding = 'utf-8') as handle:
            results.append(json.load(handle))
    with open(os.path.join(arguments.cases[0], 'reference', 'style.json'), encoding = 'utf-8') as handle:
        style = json.load(handle)
    applyStyle(style)
    output = arguments.output or os.path.join(arguments.cases[2], 'comparison')
    os.makedirs(output, exist_ok = True)

    # A quantity zero on every grid, the disk of a regular reflection, has nothing to converge
    summary = {'cells': [result['cells'] for result in results], 'quantities': {}, 'criteria': {}, 'absent': []}
    for key, (read, _, nova) in quantities.items():
        values = [read(result) for result in results]
        if not any(values):
            summary['absent'].append(key)
            continue
        entry = richardson(*values)
        entry['nova'] = nova(results[2])
        entry['novaAgainstExtrapolated'] = entry['nova'] / entry['extrapolated'] - 1.0
        entry['novaAgainstFine'] = entry['nova'] / entry['fine'] - 1.0
        summary['quantities'][key] = entry
    for key, limit in mediumToFineLimits.items():
        change = summary['quantities'][key]['mediumToFine']
        summary['criteria'][key] = {'value': change, 'limit': limit, 'pass': bool(abs(change) <= limit)}
    with open(os.path.join(output, 'plumeGridConvergence.json'), 'w', encoding = 'utf-8') as handle:
        json.dump(summary, handle, indent = 2)

    spacing = np.array([4.0, 2.0, 1.0])
    figure, panels = plt.subplots(2, 3, figsize = (12.0, 6.4))
    for axes, (key, entry) in zip(panels.ravel(), summary['quantities'].items()):
        label = quantities[key][1]
        axes.plot(spacing, [entry['coarse'], entry['medium'], entry['fine']], 'o-', label = 'OpenFOAM')
        if np.isfinite(entry['extrapolated']):
            axes.plot([0.0], [entry['extrapolated']], 's', label = f"extrapolated, order {entry['order']:.2f}")
        axes.axhline(entry['nova'], linestyle = '--', color = 'C2', label = 'NOVA')
        axes.set_xlim(-0.2, 4.4); axes.set_xlabel('cell size / fine cell size'); axes.set_ylabel(label, fontsize = 8)
        axes.legend(fontsize = 7)
    for axes in panels.ravel()[len(summary['quantities']):]:
        axes.set_visible(False)
    figure.tight_layout(); figure.savefig(os.path.join(output, 'plumeGridConvergence.png')); plt.close(figure)

    print(f"{'quantity':28s} {'coarse':>9s} {'medium':>9s} {'fine':>9s} {'order':>6s} {'extrap.':>9s} {'GCI':>7s} "
          f"{'NOVA':>9s} {'NOVA/ext':>9s}")
    for key, entry in summary['quantities'].items():
        print(f"{key:28s} {entry['coarse']:9.5g} {entry['medium']:9.5g} {entry['fine']:9.5g} {entry['order']:6.2f} "
              f"{entry['extrapolated']:9.5g} {entry['gridConvergenceIndex'] * 100:6.3f}% {entry['nova']:9.5g} "
              f"{entry['novaAgainstExtrapolated'] * 100:8.2f}%")
    for key in summary['absent']:
        print(f'{key}: zero on every grid')
    for key, criterion in summary['criteria'].items():
        print(f"medium to fine, {key}: {criterion['value'] * 100:.3f}% (limit {criterion['limit'] * 100:.1f}%) "
              f"{'pass' if criterion['pass'] else 'FAIL'}")

if __name__ == '__main__':
    main()
