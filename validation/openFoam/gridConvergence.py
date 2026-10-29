# -- NOVA Nozzle: Grid Convergence of the OpenFOAM Case -- #

'''

Richardson extrapolation and grid convergence index across the coarse, medium and fine cases.

Each grid has twice the cells of the last in each direction, so the refinement ratio is 2. For
each exit-plane quantity, the observed order of convergence comes from the three solutions, the
extrapolated value is the fine solution corrected by it, and the grid convergence index is
Roache's, with a safety factor of 1.25 on three grids. The extrapolated values are then set
against NOVA's, which removes OpenFOAM's discretization error from the comparison as far as three
grids can.

Run after `compareWithNova.py` has run on each case:

    python3 gridConvergence.py <coarse case> <medium case> <fine case> [--output <folder>]

Writes `gridConvergence.json` and `gridConvergence.png` to the output folder, the fine case's
`comparison` folder by default. Needs NumPy and Matplotlib.

Author: Sean Bowman

'''

import argparse
import json
import math
import os

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

quantities = ('massFlow', 'vacuumThrustCoefficient', 'thrustPerMassFlow', 'exitMassAveragedMach')
labels = {'massFlow': 'mass flow [kg/s]', 'vacuumThrustCoefficient': 'vacuum thrust coefficient',
          'thrustPerMassFlow': 'vacuum thrust / mass flow [m/s]', 'exitMassAveragedMach': 'mass-averaged exit Mach'}

# The medium grid's vacuum thrust coefficient within this fraction of the fine grid's
mediumToFineLimit = 0.002

def richardson(coarse: float, medium: float, fine: float, ratio: float = 2.0) -> dict:

    '''

    Observed order, extrapolated value and fine-grid convergence index from three solutions.

    Oscillatory convergence, where the two differences change sign, has no observed order. Nor does
    a solution whose change grows with refinement, where the observed order is negative and the grids
    are outside the asymptotic range. Either way the extrapolation is skipped and the index taken at
    a formal second order.

    '''

    fineChange, coarseChange = medium - fine, coarse - medium
    monotonic = fineChange * coarseChange > 0.0 and abs(fineChange) > 0.0
    order = math.log(abs(coarseChange / fineChange)) / math.log(ratio) if monotonic else float('nan')
    asymptotic = monotonic and order > 0.0
    usedOrder = order if asymptotic else 2.0
    extrapolated = fine + (fine - medium) / (ratio**usedOrder - 1.0) if asymptotic else float('nan')
    index = 1.25 * abs(fineChange / fine) / (ratio**usedOrder - 1.0)

    return {'coarse': coarse, 'medium': medium, 'fine': fine, 'monotonic': bool(monotonic), 'order': order,
            'extrapolated': extrapolated, 'gridConvergenceIndex': index, 'mediumToFine': fineChange / fine}

def main() -> None:

    parser = argparse.ArgumentParser(description = 'Grid convergence of the OpenFOAM NOVA nozzle cases.')
    parser.add_argument('cases', nargs = 3, help = 'coarse, medium and fine case folders')
    parser.add_argument('--output', default = None)
    arguments = parser.parse_args()

    results = []
    for case in arguments.cases:
        with open(os.path.join(case, 'comparison', 'comparison.json'), encoding = 'utf-8') as handle:
            results.append(json.load(handle))
    with open(os.path.join(arguments.cases[0], 'reference', 'style.json'), encoding = 'utf-8') as handle:
        style = json.load(handle)
    output = arguments.output or os.path.join(arguments.cases[2], 'comparison')
    os.makedirs(output, exist_ok = True)

    summary = {'cells': [result['cells'] for result in results], 'quantities': {}}
    for key in quantities:
        values = [result['exitPlane'][key]['openFoam'] for result in results]
        entry = richardson(*values)
        nova = results[0]['exitPlane'][key]['nova']
        entry['nova'] = nova
        entry['fineAgainstNova'] = values[2] / nova - 1.0
        entry['extrapolatedAgainstNova'] = entry['extrapolated'] / nova - 1.0
        summary['quantities'][key] = entry
    change = summary['quantities']['vacuumThrustCoefficient']['mediumToFine']
    summary['mediumToFineCriterion'] = {'value': change, 'limit': mediumToFineLimit,
                                        'pass': bool(abs(change) <= mediumToFineLimit)}
    with open(os.path.join(output, 'gridConvergence.json'), 'w', encoding = 'utf-8') as handle:
        json.dump(summary, handle, indent = 2)

    named = style['colors']
    plt.rcParams.update({
        'figure.facecolor': named['bg'], 'savefig.facecolor': named['bg'], 'axes.facecolor': named['surface'],
        'axes.edgecolor': named['border'], 'axes.labelcolor': named['text'], 'text.color': named['text'],
        'xtick.color': named['textMuted'], 'ytick.color': named['textMuted'], 'grid.color': named['border'],
        'legend.facecolor': named['surface2'], 'legend.edgecolor': named['border'], 'font.size': 9,
        'axes.prop_cycle': plt.cycler(color = style['categories']), 'axes.grid': True, 'grid.linewidth': 0.5,
        'savefig.dpi': 160,
    })
    # Spacing relative to the fine grid's, so the extrapolated value sits at zero
    spacing = np.array([4.0, 2.0, 1.0])
    figure, panels = plt.subplots(2, 2, figsize = (9.0, 6.4))
    for axes, key in zip(panels.ravel(), quantities):
        entry = summary['quantities'][key]
        axes.plot(spacing, [entry['coarse'], entry['medium'], entry['fine']], 'o-', label = 'OpenFOAM')
        if math.isfinite(entry['extrapolated']):
            axes.plot([0.0], [entry['extrapolated']], 's', label = f"extrapolated, order {entry['order']:.2f}")
        axes.axhline(entry['nova'], linestyle = '--', color = 'C2', label = 'NOVA')
        axes.set_xlim(-0.2, 4.4); axes.set_xlabel('cell size / fine cell size'); axes.set_ylabel(labels[key])
        axes.legend(fontsize = 7)
    figure.tight_layout(); figure.savefig(os.path.join(output, 'gridConvergence.png')); plt.close(figure)

    print(f"{'quantity':26s} {'coarse':>11s} {'medium':>11s} {'fine':>11s} {'order':>6s} {'extrap.':>11s} "
          f"{'GCI':>7s} {'NOVA':>11s} {'ext/NOVA':>9s}")
    for key, entry in summary['quantities'].items():
        print(f"{key:26s} {entry['coarse']:11.6g} {entry['medium']:11.6g} {entry['fine']:11.6g} {entry['order']:6.2f} "
              f"{entry['extrapolated']:11.6g} {entry['gridConvergenceIndex'] * 100:6.3f}% {entry['nova']:11.6g} "
              f"{entry['extrapolatedAgainstNova'] * 100:8.3f}%")
    criterion = summary['mediumToFineCriterion']
    print(f"medium to fine, vacuum thrust coefficient: {criterion['value'] * 100:.3f}% "
          f"(limit {criterion['limit'] * 100:.1f}%) {'pass' if criterion['pass'] else 'FAIL'}")

if __name__ == '__main__':
    main()
