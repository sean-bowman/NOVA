'''

Did the searched contour beat the Rao family, or beat NOVA's reading of the Rao chart.

The cross-family study compares a searched cubic wall against a parabola whose two angles are read
off a digitized chart. That chart carries a recorded transcription error and is extrapolated above
an area ratio of fifty, so a gain measured against it answers two questions at once and separates
neither: the searched wall may be better than the parabola family, or merely better than the
chart's reading of it.

Three walls at one design point separate them, and the cubic family containing the quadratic one
exactly is what makes the middle wall constructible:

    chart parabola        angles read from the chart
    optimized quadratic   angles searched, tensions derived so the wall is still a parabola
    optimized cubic       angles and tensions all searched

Quadratic above chart is what the chart costs. Cubic above quadratic is what the extra freedom
buys. Their sum is the only thing the cross-family study can currently report.

Every search here runs at the driver's full settings rather than the throttled ones the seven
point sweep uses. Re-running an ambiguous experiment more cheaply answers nothing, and the
throttled settings are what made the original answer ambiguous.

Run: python featureShowcase/buildSubfamilyStudy.py
     python featureShowcase/buildSubfamilyStudy.py --draw     # redraw from the cache

Author: Sean Bowman

'''
import json
import os
import sys
import time

import matplotlib
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'src'))

os.environ.setdefault('NOVA_HEADLESS', '1')
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt                                         # noqa: E402

from NOVA.Nozzle import Nozzle                                          # noqa: E402
from NOVA.contourOptimization import solveThrustOptimizedContour        # noqa: E402

cachePath = os.path.join(here, 'subfamilyStudy.npz')

# The worked design point, and the one point in the seven point sweep where the cubic showed a
# gain. Two rather than seven because each search is a full run rather than a throttled one.
designPoints = ((40.0, 0.80), (70.0, 0.80))
searchFamilies = ('quadratic', 'cubic')
familyLabels = {'quadratic': 'optimized quadratic', 'cubic': 'optimized cubic'}

#--------------------------------------------------------------------------------------------------------------------------#
# -- Running one search -- #
#--------------------------------------------------------------------------------------------------------------------------#

def buildNozzle(areaRatio: float, lengthFraction: float):

    '''A nozzle at one design point, set up but with no diverging section solved yet.'''

    config = json.load(open(os.path.join(root, 'src', 'NOVA', 'assets', 'NOVANozzle.json')))
    config.update({'targetExitPressure': None, 'expansionRatio': areaRatio,
                   'lengthFraction': lengthFraction, 'Lstar': None,
                   'plumeAmbientPressure': None, 'plotsEnabled': False,
                   'export': False, 'makeCoolingChannels': 'off',
                   'filename': 'subfamilyStudy'})
    configPath = os.path.join(here, 'subfamilyConfig.json')
    json.dump(config, open(configPath, 'w'), indent = 2)

    Nozzle._getOutputRoot = lambda self, _base = here: _base
    nozzle = Nozzle()
    nozzle.setInputs(inputsPath = configPath)
    return nozzle

def runSearch(areaRatio: float, lengthFraction: float, searchFamily: str) -> dict:

    '''One full search, returned as the driver's own record. None if it raised.'''

    nozzle = buildNozzle(areaRatio, lengthFraction)
    try:
        return solveThrustOptimizedContour(nozzle, float(lengthFraction),
                                           searchFamily = searchFamily)
    except (TypeError, AttributeError, KeyError, NameError, ImportError):
        # A bad call is not a failed search. Swallowing these once already cost a whole sweep.
        raise
    except Exception as error:                                          # noqa: BLE001
        print(f'    FAILED {searchFamily} eps {areaRatio} bell {lengthFraction}: {error}')
        return None

def build() -> dict:

    started = time.time()
    payload = {}

    for areaRatio, lengthFraction in designPoints:
        for searchFamily in searchFamilies:
            print(f'  eps {areaRatio:5.1f} bell {lengthFraction:4.2f}  {searchFamily}',
                  flush = True)
            record = runSearch(areaRatio, lengthFraction, searchFamily)
            tag = f'{int(areaRatio)}_{int(100 * lengthFraction)}_{searchFamily}'
            if record is None:
                payload[f'{tag}_usable'] = np.array([0])
                continue
            payload[f'{tag}_usable'] = np.array([1])
            # The incumbent is the chart parabola solved through the same path as the searched
            # wall, so the comparison is between walls rather than between code paths.
            for key in ('thrustCoef', 'exitMassClosure', 'incumbentThrustCoef', 'incumbentClosure',
                        'normalizedGainOverParabola', 'objectiveNoiseFloor', 'perturbationMargin',
                        'admissibleNeighbours', 'isLocalOptimum', 'improvedOnIncumbent',
                        'evaluations', 'restarts'):
                value = record.get(key)
                payload[f'{tag}_{key}'] = np.array([np.nan if value is None else float(value)])
            payload[f'{tag}_designVariables'] = np.asarray(record['designVariables'], dtype = float)

    payload['elapsedMinutes'] = np.array([(time.time() - started) / 60.0])
    np.savez(cachePath, **payload)
    return payload

#--------------------------------------------------------------------------------------------------------------------------#
# -- The report -- #
#--------------------------------------------------------------------------------------------------------------------------#

def normalized(payload, tag, incumbent = False) -> float:
    '''Thrust coefficient over its own exit-plane mass closure, which is the comparable figure.'''
    thrustKey = f'{tag}_incumbentThrustCoef' if incumbent else f'{tag}_thrustCoef'
    closureKey = f'{tag}_incumbentClosure' if incumbent else f'{tag}_exitMassClosure'
    thrust, closure = payload.get(thrustKey), payload.get(closureKey)
    if thrust is None or closure is None:
        return float('nan')
    thrust, closure = float(thrust[0]), float(closure[0])
    return thrust / closure if closure else float('nan')

def report(payload) -> None:

    print()
    print('=' * 108)
    print('DID THE SEARCH BEAT THE FAMILY, OR THE CHART')
    print('=' * 108)
    print('Every coefficient is divided by its own exit-plane mass closure. Two walls need not')
    print('sample the same fraction of their exit planes, and the difference between two closures')
    print('is routinely larger than the difference between two contours.')
    print()
    print('The chart parabola is the incumbent each search was started from and is solved through')
    print('the same path, so the three rows differ by wall and not by code path.')
    print()

    for areaRatio, lengthFraction in designPoints:
        quadraticTag = f'{int(areaRatio)}_{int(100 * lengthFraction)}_quadratic'
        cubicTag = f'{int(areaRatio)}_{int(100 * lengthFraction)}_cubic'
        if not int(payload.get(f'{quadraticTag}_usable', [0])[0]):
            print(f'  eps {areaRatio}, bell {lengthFraction}: quadratic search did not run')
            continue

        chart = normalized(payload, quadraticTag, incumbent = True)
        quadratic = normalized(payload, quadraticTag)
        cubic = normalized(payload, cubicTag)

        print(f'  Area ratio {areaRatio:.0f}, {100 * lengthFraction:.0f} per cent bell')
        print(f'    {"wall":<22} {"Cf/closure":>11} {"closure %":>10} {"vs chart":>10} '
              f'{"seen":>5} {"margin":>12} {"noise":>12} {"optimum":>8}')
        chartClosure = 100.0 * float(payload[f'{quadraticTag}_incumbentClosure'][0])
        print(f'    {"chart parabola":<22} {chart:11.5f} {chartClosure:10.2f} '
              f'{"-":>10} {"-":>5} {"-":>12} {"-":>12} {"-":>8}')

        for tag, label in ((quadraticTag, familyLabels['quadratic']),
                           (cubicTag, familyLabels['cubic'])):
            if not int(payload.get(f'{tag}_usable', [0])[0]):
                print(f'    {label:<22} search did not run')
                continue
            value = normalized(payload, tag)
            closure = 100.0 * float(payload[f'{tag}_exitMassClosure'][0])
            gain = 100.0 * float(payload[f'{tag}_normalizedGainOverParabola'][0])
            seen = int(payload[f'{tag}_admissibleNeighbours'][0])
            margin = float(payload[f'{tag}_perturbationMargin'][0])
            noise = float(payload[f'{tag}_objectiveNoiseFloor'][0])
            optimum = bool(payload[f'{tag}_isLocalOptimum'][0])
            marginText = f'{margin:12.3e}' if np.isfinite(margin) else f'{"none scored":>12}'
            print(f'    {label:<22} {value:11.5f} {closure:10.2f} {gain:9.3f}% {seen:5d} '
                  f'{marginText} {noise:12.3e} {str(optimum):>8}')

        # The two differences the whole study exists to separate.
        chartCost = 100.0 * (quadratic / chart - 1.0) if np.isfinite(chart) and chart else np.nan
        freedomBuys = (100.0 * (cubic / quadratic - 1.0)
                       if np.isfinite(quadratic) and quadratic else np.nan)
        noiseFloor = max(float(payload[f'{quadraticTag}_objectiveNoiseFloor'][0]),
                         float(payload.get(f'{cubicTag}_objectiveNoiseFloor', [np.nan])[0]))
        # The noise floor is a merit difference; expressed against the incumbent it becomes the
        # smallest percentage this comparison can resolve at all.
        resolvable = 100.0 * noiseFloor / chart if np.isfinite(chart) and chart else np.nan

        print()
        print(f'    what the chart reading costs   {chartCost:+.3f} %   '
              f'(optimized quadratic over chart parabola)')
        print(f'    what the cubic freedom buys    {freedomBuys:+.3f} %   '
              f'(optimized cubic over optimized quadratic)')
        print(f'    smallest difference resolvable {resolvable:.3f} %   '
              f'(the larger noise floor of the two searches)')
        # A search that returned its own incumbent did not fail to resolve a difference; it found
        # no difference to resolve. Reporting the two the same way would hide which happened.
        improved = bool(payload.get(f'{quadraticTag}_improvedOnIncumbent', [0])[0])
        if not improved:
            print('    The quadratic search returned the chart vector unchanged, so the chart')
            print('    reading is already the best wall in the parabola family at this point.')
        elif np.isfinite(chartCost) and np.isfinite(resolvable) and abs(chartCost) < resolvable:
            print('    NOT RESOLVED: the chart reading difference is below the noise floor')
        if (np.isfinite(freedomBuys) and np.isfinite(resolvable)
                and abs(freedomBuys) < resolvable):
            print('    NOT RESOLVED: the cubic freedom difference is below the noise floor')
        print()

    print('  Published expectation, stated before the run so it cannot be fitted afterwards:')
    print('  Allman and Hoffman optimized a second-degree wall against Rao contours at thirteen')
    print('  matched lengths and landed 0.05 to 0.21 per cent BELOW Rao at every one, because a')
    print('  parametrized family cannot beat an unconstrained variational optimum. They put their')
    print('  own characteristics precision at 0.2 per cent. So an optimized quadratic at or just')
    print('  below a correct Rao parabola is the expected result, and a large gain over the chart')
    print('  is most likely the chart rather than the family.')
    if 'elapsedMinutes' in payload:
        print(f'\n  ran in {float(payload["elapsedMinutes"][0]):.1f} minutes')

#--------------------------------------------------------------------------------------------------------------------------#
# -- The figure -- #
#--------------------------------------------------------------------------------------------------------------------------#

def draw(payload) -> None:

    figure, axes = plt.subplots(1, len(designPoints), figsize = (6.5 * len(designPoints), 4.6))
    axes = np.atleast_1d(axes)

    for panel, (areaRatio, lengthFraction) in zip(axes, designPoints):
        quadraticTag = f'{int(areaRatio)}_{int(100 * lengthFraction)}_quadratic'
        cubicTag = f'{int(areaRatio)}_{int(100 * lengthFraction)}_cubic'
        if not int(payload.get(f'{quadraticTag}_usable', [0])[0]):
            panel.set_title(f'area ratio {areaRatio:.0f}: no data')
            continue

        labels = ['chart\nparabola', 'optimized\nquadratic', 'optimized\ncubic']
        values = [normalized(payload, quadraticTag, incumbent = True),
                  normalized(payload, quadraticTag),
                  normalized(payload, cubicTag)]
        panel.bar(labels, values, color = ['#8a8a8a', '#E0975A', '#86C06C'], alpha = 0.9)
        finite = [v for v in values if np.isfinite(v)]
        if finite:
            span = max(finite) - min(finite)
            panel.set_ylim(min(finite) - 4.0 * span - 1e-6, max(finite) + 2.0 * span + 1e-6)
        panel.set_ylabel('thrust coefficient over mass closure')
        panel.set_title(f'area ratio {areaRatio:.0f}, {100 * lengthFraction:.0f} per cent bell')
        panel.grid(axis = 'y', alpha = 0.3)

    figure.tight_layout()
    path = os.path.join(here, 'subfamilyStudy.png')
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print(f'wrote {os.path.basename(path)}')

def main():
    if '--draw' in sys.argv:
        payload = dict(np.load(cachePath, allow_pickle = False))
    else:
        payload = build()
    report(payload)
    draw(payload)

if __name__ == '__main__':
    main()
