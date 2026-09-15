'''
Verification of the three contoured diverging sections against each other and against references
that do not come from NOVA.

The truncated ideal contour has its own study in buildContourValidation.py. This is the one that
compares it with the two thrust-optimized families, and the comparison needs more care than the
single-family checks did, for a reason worth stating before any number appears.

  What a family delivers   Checkable against arithmetic and nothing else. A thrust-optimized
                           parabola places its exit point before it solves anything, so its area
                           ratio and length are exact rather than converged, and a miss would be
                           a defect rather than a discretisation.

  Rao wall angles          For the parabola the chart is the construction, so agreement measures
                           the resample and not the physics. For the truncated ideal contour it is
                           a different family and the difference is expected. For the searched
                           contour it is the same family the chart approximates, which makes it
                           the one genuine external check on a contour SHAPE in this set.

  Thrust ordering          The headline comparison, and the one that misleads if taken raw. The
                           exit plane samples less mass than the throat passes, the momentum term
                           scales with what it samples, and the two families do not sample equally.
                           On the first run of this study that artefact was larger than the
                           difference being looked for and reversed its sign. Every thrust
                           coefficient below is therefore quoted with its mass closure beside it,
                           and the ordering is read off the ratio.

  Grid convergence         How much of each answer is physics and how much is mesh, per family.

  Internal shock           Whether the net folds, which a truncated ideal contour cannot do by
                           construction and both thrust-optimized families should.

Each study runs the solver. Results cache to contourFamilies.npz; pass --draw to redraw the figure
from the cache without re-running.

    python featureShowcase/buildContourFamilies.py
    python featureShowcase/buildContourFamilies.py --draw
'''
import json
import os
import sys
import time

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
from NOVA.contour import raoWallAngles, raoChartExtrapolatedAbove
from NOVA.contourKernel import ThroatGeometry
from NOVA.gasDynamics import conicalLength
from NOVA.Nozzle import Nozzle
from NOVA.contourOptimization import parabolaDesignVector

background = '#1a1e2a'
panel      = '#222735'
copper     = '#E0975A'
green      = '#86C06C'
ink        = '#E8E6E1'
muted      = '#8B93A7'
warn       = '#E8A0A0'
blue       = '#6BA3D6'

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': '#333A4D',
    'axes.grid': False, 'font.size': 9,
    'axes.titlesize': 11, 'axes.titleweight': 'bold', 'legend.framealpha': 0.0,
})

cachePath = os.path.join(here, 'contourFamilies.npz')

familyColors = {'truncatedIdeal': copper, 'thrustOptimizedParabola': green,
                'thrustOptimizedContour': blue}
familyLabels = {'truncatedIdeal': 'truncated ideal', 'thrustOptimizedParabola': 'Rao parabola',
                'thrustOptimizedContour': 'searched optimum'}

#--------------------------------------------------------------------------------------------------------------------------#
# -- Running the solver -- #
#--------------------------------------------------------------------------------------------------------------------------#

# Optimizer settings for the study. Deliberately below the driver's own defaults: a full search
# is roughly twenty minutes and this sweep wants seven of them, so the searches here are shorter
# and the study records the perturbation margin that says whether each one actually converged.
# No coarse mesh: the search runs at the mesh its answer is read off, which is the whole point of
# the driver default. Searching coarse and reporting fine was what made the previous run of this
# study report one converged search out of seven. The evaluation budget is cut instead, and the
# perturbation margin in the table below says which searches that was too tight for.
studyOptimizerSettings = {'maximumEvaluations': 60, 'maximumRestarts': 1}

# How much harder than the chart parabola to turn the wall, in degrees of inflection angle. The
# range is deliberately past anything a converged search would choose: the point is to drive the
# detector through a regime where it must respond, not to propose these as contours.
shockSweepOffsetsDegrees = (4.0, 8.0, 14.0)

# The design vector is a property of the throat and the design point, not of the gas the case is
# eventually solved in, but `ThroatGeometry` needs a gamma to construct. This is the worked
# example's chamber value, and it reaches nothing but the arc geometry the vector is read off.
GAMMA_FOR_DESIGN_VECTOR = 1.1475421191138746

def runCase(family: str, areaRatio: float, lengthFraction: float, mesh: int = 50,
            designVariables: tuple = None) -> dict:
    '''
    One contour of one family, returned as a flat dictionary of what it delivered. Returns None if
    the solve fails, so a sweep reports a hole rather than stopping at one.
    '''
    config = json.load(open(os.path.join(root, 'src', 'NOVA', 'assets', 'loxLh2Example.json')))
    config.update({'targetExitPressure': None, 'expansionRatio': areaRatio,
                   'lengthFraction': lengthFraction, 'Lstar': None,
                   'plumeAmbientPressure': None, 'plotsBasic': False, 'plotsAdv': False,
                   'export': False, 'visualizeContour': False, 'makeCoolingChannels': 'off',
                   'filename': 'contourFamilies'})
    configPath = os.path.join(here, 'familiesConfig.json')
    json.dump(config, open(configPath, 'w'), indent = 2)

    Nozzle._getOutputRoot = lambda self, _base = here: _base
    nozzle = Nozzle()
    try:
        nozzle.setInputs(inputsPath = configPath)
        nozzle.numCharacteristicsRequested = mesh
        if family == 'truncatedIdeal':
            nozzle.pressureMatchTruncatedIdealContour(float(lengthFraction))
        elif family == 'thrustOptimizedParabola':
            nozzle.thrustOptimizedParabolicContour(float(lengthFraction))
        elif family == 'thrustOptimizedContour':
            nozzle.thrustOptimizedContour(float(lengthFraction),
                                          designVariables = designVariables,
                                          **({} if designVariables is not None
                                             else studyOptimizerSettings))
        else:
            raise ValueError(f'No family called {family}')
    except (TypeError, AttributeError, KeyError, NameError, ImportError):
        # A bad call is not a failed solve. These say the study is wired wrong, and swallowing
        # them once already cost a whole sweep: every searched-contour case came back empty
        # because a keyword the facade did not accept looked exactly like a nozzle that would
        # not converge.
        raise
    except Exception as error:                                          # noqa: BLE001
        print(f'    FAILED {family} eps {areaRatio} bell {lengthFraction} mesh {mesh}: {error}')
        return None

    solution = nozzle.nozzleContourSolution
    record = getattr(nozzle, 'nozzleContourOptimization', None)
    shock = solution.internalShock
    return {
        'family': family,
        'requestedAreaRatio': float(areaRatio),
        'requestedLengthFraction': float(lengthFraction),
        'mesh': float(mesh),
        'deliveredAreaRatio': float(solution.deliveredAreaRatio),
        'deliveredLengthFraction': float(solution.deliveredLengthFraction),
        'inflectionWallAngle': float(np.degrees(solution.inflectionWallAngle)),
        'exitWallAngle': float(np.degrees(solution.exitWallAngle)),
        'thrustCoef': float(solution.thrustCoef),
        'exitMassClosure': float(solution.exitMassClosure),
        # The comparable figure of merit. The raw coefficient carries the exit plane's mass
        # deficit, which differs between families and swamps the difference between them.
        'normalizedThrustCoef': float(solution.thrustCoef / solution.exitMassClosure),
        'exitPlaneSampledFraction': float(solution.exitPlaneSampledFraction),
        'shockDetected': bool(shock is not None),
        # The summary the solution carries, not the front itself: onset station, the total wall
        # turning the front has to absorb, and the stagnation pressure that survives it. A debit
        # of nan means no shock was found, which is not the same number as a debit of zero.
        'shockOnsetX': float(shock['onsetX']) if shock else float('nan'),
        'shockPeakDeflection': float(shock['peakDeflection']) if shock else float('nan'),
        'shockStagnationRatio': float(shock['minimumStagnationRatio']) if shock else float('nan'),
        'shockIsWeak': bool(shock['isWeak']) if shock else False,
        'shockThrustDebit': (float(solution.shockThrustDebit)
                             if getattr(solution, 'shockThrustDebit', None) is not None
                             else float('nan')),
        'perturbationMargin': float(record['perturbationMargin']) if record else float('nan'),
        'objectiveNoiseFloor': float(record['objectiveNoiseFloor']) if record else float('nan'),
        'isLocalOptimum': bool(record['isLocalOptimum']) if record else False,
        'gainOverParabola': float(record['gainOverParabola']) if record else float('nan'),
        'normalizedGainOverParabola': (float(record['normalizedGainOverParabola'])
                                       if record else float('nan')),
        'admissibleNeighbours': int(record['admissibleNeighbours']) if record else 0,
        'designVariables': (tuple(record['designVariables']) if record else
                            (tuple(designVariables) if designVariables is not None else None)),
        'wallX': np.asarray(solution.xNozzleWallDivergingNonDimensional, dtype = float),
        'wallR': np.asarray(solution.rNozzleWallDivergingNonDimensional, dtype = float),
    }

def flatten(records, key):
    return np.array([record[key] if record is not None else np.nan for record in records])

def storeWalls(payload, records, prefix):
    '''Each case's wall under its own key: stacking them makes a ragged array as soon as one
    case fails or runs at a different contour resolution.'''
    for index, record in enumerate(records):
        if record is None:
            continue
        payload[f'{prefix}_wallX_{index}'] = record['wallX']
        payload[f'{prefix}_wallR_{index}'] = record['wallR']

#--------------------------------------------------------------------------------------------------------------------------#
# -- The studies -- #
#--------------------------------------------------------------------------------------------------------------------------#

families = ('truncatedIdeal', 'thrustOptimizedParabola', 'thrustOptimizedContour')
designPoints = ((10.0, 0.80), (20.0, 0.80), (40.0, 0.80), (70.0, 0.80),
                (40.0, 0.60), (40.0, 0.70), (40.0, 0.90))
meshes = (25, 35, 50, 70, 100)

def build() -> dict:
    payload, started = {}, time.time()

    # -- Delivered design point and wall angles, per family, across the design space -- #
    meshSweepVectors = {}
    print('Design points, three families:', flush = True)
    for family in families:
        records = []
        for areaRatio, lengthFraction in designPoints:
            print(f'  {familyLabels[family]:20s} eps {areaRatio:5.1f} bell {lengthFraction:.2f}',
                  flush = True)
            record = runCase(family, areaRatio, lengthFraction)
            records.append(record)
            # The wall the mesh sweep will hold fixed, from the worked design point.
            if (record is not None and (areaRatio, lengthFraction) == (40.0, 0.80)
                    and record.get('designVariables') is not None):
                meshSweepVectors[family] = record['designVariables']
        for key in ('requestedAreaRatio', 'requestedLengthFraction', 'deliveredAreaRatio',
                    'deliveredLengthFraction', 'inflectionWallAngle', 'exitWallAngle',
                    'thrustCoef', 'exitMassClosure', 'normalizedThrustCoef',
                    'exitPlaneSampledFraction', 'shockDetected', 'shockOnsetX',
                    'shockPeakDeflection', 'shockStagnationRatio', 'shockThrustDebit',
                    'perturbationMargin', 'objectiveNoiseFloor', 'isLocalOptimum',
                    'gainOverParabola', 'normalizedGainOverParabola', 'admissibleNeighbours'):
            payload[f'design_{family}_{key}'] = flatten(records, key)
        storeWalls(payload, records, f'design_{family}')

    # -- Grid convergence, per family, at the worked design point -- #
    # Grid convergence holds the GEOMETRY fixed and varies only the mesh. For the searched
    # contour that means reusing the wall the search converged on rather than searching again at
    # every resolution: re-optimizing per mesh would measure how much the optimizer moves, which
    # is a different question and would hide the one being asked.
    print('Grid convergence, three families:', flush = True)
    for family in families:
        records = []
        for mesh in meshes:
            print(f'  {familyLabels[family]:20s} mesh {mesh}', flush = True)
            records.append(runCase(family, 40.0, 0.80, mesh = mesh,
                                   designVariables = meshSweepVectors.get(family)))
        for key in ('mesh', 'thrustCoef', 'exitMassClosure', 'normalizedThrustCoef',
                    'deliveredAreaRatio', 'deliveredLengthFraction', 'inflectionWallAngle',
                    'exitWallAngle'):
            payload[f'mesh_{family}_{key}'] = flatten(records, key)

    # -- Shock response against wall turning -- #
    # A sweep that reports no shocks says nothing about the detector. This turns one wall harder
    # and harder from the chart parabola and records what comes back, so the detector is measured
    # on walls that must compress rather than only on walls that need not. The first row is the
    # parabola expressed as a cubic, which is the containment property stated as a number: if the
    # cubic at the parabola's own design vector does not reproduce the parabola's solve, the
    # searched family does not contain the charted one and no comparison between them means
    # anything.
    print('Shock response against wall turning:', flush = True)
    throat = ThroatGeometry(GAMMA_FOR_DESIGN_VECTOR, 1.0, 1.5, 0.382)
    parabolaVector = parabolaDesignVector(throat, 40.0, 0.80)
    inflection, exitAngle, inflectionTension, exitTension = parabolaVector
    turningRecords = [runCase('thrustOptimizedParabola', 40.0, 0.80, mesh = 50)]
    turningOffsets = [0.0] + list(shockSweepOffsetsDegrees)
    for offset in shockSweepOffsetsDegrees:
        print(f'  inflection +{offset:.0f} deg', flush = True)
        turningRecords.append(runCase(
            'thrustOptimizedContour', 40.0, 0.80, mesh = 50,
            designVariables = (inflection + np.deg2rad(offset), exitAngle,
                               inflectionTension, exitTension)))
    turningRecords.insert(1, runCase('thrustOptimizedContour', 40.0, 0.80, mesh = 50,
                                     designVariables = parabolaVector))
    turningOffsets.insert(1, 0.0)
    payload['turningOffsets'] = np.array(turningOffsets, dtype = float)
    payload['turningIsCubic'] = np.array([0] + [1] * (len(turningRecords) - 1))
    for key in ('thrustCoef', 'exitMassClosure', 'shockDetected', 'shockOnsetX',
                'shockPeakDeflection', 'shockStagnationRatio', 'shockThrustDebit'):
        payload[f'turning_{key}'] = flatten(turningRecords, key)

    payload['designPoints'] = np.array(designPoints)
    payload['meshes'] = np.array(meshes)
    payload['elapsedMinutes'] = np.array([(time.time() - started) / 60.0])
    np.savez(cachePath, **payload)
    return payload

#--------------------------------------------------------------------------------------------------------------------------#
# -- Reporting -- #
#--------------------------------------------------------------------------------------------------------------------------#

def report(data):
    '''
    Print the numbers the write-up quotes, so they are computed rather than remembered.
    '''
    print()
    print('=' * 108)
    print('DELIVERED AGAINST REQUESTED')
    print('=' * 108)
    print('A parabola and a searched contour place their exit point before solving, so their')
    print('design point is exact by construction. A truncated ideal contour iterates for it.')
    print()
    print(f'{"":34s} {"area ratio":>22s}   {"length fraction":>22s}')
    print(f'{"family":24s} {"asked":>9s} {"got":>10s} {"err %":>10s}   {"got":>10s} {"err %":>10s}')
    for family in families:
        asked = data[f'design_{family}_requestedAreaRatio']
        got = data[f'design_{family}_deliveredAreaRatio']
        askedBell = data[f'design_{family}_requestedLengthFraction']
        gotBell = data[f'design_{family}_deliveredLengthFraction']
        for index in range(len(asked)):
            if not np.isfinite(got[index]):
                continue
            print(f'{familyLabels[family]:24s} {asked[index]:9.2f} {got[index]:10.5f} '
                  f'{100*(got[index]/asked[index]-1):10.4f}   {gotBell[index]:10.5f} '
                  f'{100*(gotBell[index]/askedBell[index]-1):10.4f}')
        print()

    print('=' * 108)
    print('WALL ANGLES AGAINST THE RAO CHART')
    print('=' * 108)
    print('The chart is a thrust-optimized parabola. For that family it IS the construction, so')
    print('agreement bounds the resample. For the searched contour it is the same family the')
    print('chart approximates, which makes it the one external check on a contour shape here.')
    print('For the truncated ideal contour the families differ and a difference is expected.')
    print()
    print(f'{"family":24s} {"eps":>6s} {"bell":>6s} {"inflect":>9s} {"chart":>8s} {"diff":>8s} '
          f'{"exit":>8s} {"chart":>8s} {"diff":>8s}')
    for family in families:
        eps = data[f'design_{family}_requestedAreaRatio']
        bell = data[f'design_{family}_requestedLengthFraction']
        inflect = data[f'design_{family}_inflectionWallAngle']
        exitAngle = data[f'design_{family}_exitWallAngle']
        for index in range(len(eps)):
            if not np.isfinite(inflect[index]):
                continue
            chartInflect, chartExit, extrapolated = raoWallAngles(eps[index], bell[index])
            chartInflect, chartExit = np.degrees(chartInflect), np.degrees(chartExit)
            flag = ' *' if extrapolated else ''
            print(f'{familyLabels[family]:24s} {eps[index]:6.1f} {bell[index]:6.2f} '
                  f'{inflect[index]:9.2f} {chartInflect:8.2f} {inflect[index]-chartInflect:8.2f} '
                  f'{exitAngle[index]:8.2f} {chartExit:8.2f} {exitAngle[index]-chartExit:8.2f}{flag}')
        print()
    print(f'  * read from the region of the chart SP-8120 marks extrapolated, above area ratio '
          f'{raoChartExtrapolatedAbove:.0f}')

    print()
    print('=' * 108)
    print('THRUST, WITH THE MASS CLOSURE IT DEPENDS ON')
    print('=' * 108)
    print('Read the last column. The raw coefficient carries the exit plane\'s mass deficit, and')
    print('the families do not sample their planes equally, so comparing raw coefficients')
    print('compares meshes as much as contours.')
    print()
    print(f'{"eps":>6s} {"bell":>6s} | ' + ' | '.join(f'{familyLabels[f][:18]:>18s}' for f in families))
    for pointIndex, (areaRatio, lengthFraction) in enumerate(designPoints):
        cells = []
        for family in families:
            raw = data[f'design_{family}_thrustCoef'][pointIndex]
            closure = data[f'design_{family}_exitMassClosure'][pointIndex]
            cells.append(f'{raw:7.5f} /{100*closure:6.2f}%' if np.isfinite(raw) else f'{"--":>18s}')
        print(f'{areaRatio:6.1f} {lengthFraction:6.2f} | ' + ' | '.join(cells))
    print()
    print('Normalized by mass closure, and as a percentage against the truncated ideal contour:')
    print(f'{"eps":>6s} {"bell":>6s} | ' + ' | '.join(f'{familyLabels[f][:18]:>18s}' for f in families))
    for pointIndex, (areaRatio, lengthFraction) in enumerate(designPoints):
        reference = data['design_truncatedIdeal_normalizedThrustCoef'][pointIndex]
        cells = []
        for family in families:
            value = data[f'design_{family}_normalizedThrustCoef'][pointIndex]
            if not np.isfinite(value) or not np.isfinite(reference):
                cells.append(f'{"--":>18s}')
            else:
                cells.append(f'{value:8.5f} {100*(value/reference-1):+8.3f}%')
        print(f'{areaRatio:6.1f} {lengthFraction:6.2f} | ' + ' | '.join(cells))
    print()
    print('  Published expectation: the searched optimum highest, the parabola a fraction of a')
    print('  per cent behind it, the truncated ideal contour about a quarter of a per cent behind')
    print('  the optimum (SP-8120). Length-constrained optimization is reported at half to one')
    print('  per cent in thrust at equal length (Sadhana 2021).')

    print()
    print('=' * 108)
    print('DID EACH SEARCH ACTUALLY CONVERGE')
    print('=' * 108)
    print('Only the searched contour has anything to converge. A positive perturbation margin')
    print('means a neighbour was better than the point the search stopped at, so that row is')
    print('where the optimizer gave up rather than an optimum, and its thrust is not a result.')
    print('A margin below the noise floor is not evidence either way, and neither is a margin')
    print('with no admissible neighbour behind it: the "seen" column is how many of the eight')
    print('perturbations were scored rather than refused by the closure band. Zero there means')
    print('the neighbourhood was never measured, which is not the same as beating it.')
    print()
    print('The gain is normalized by mass closure, for the reason the thrust section gives. The')
    print('raw gain between two walls that sample different fractions of their exit planes is')
    print('mostly the difference between the fractions.')
    print()
    print(f'{"eps":>6s} {"bell":>6s} {"optimum":>9s} {"seen":>5s} {"margin":>12s} {"noise":>12s} '
          f'{"vs parabola":>12s} {"closure %":>10s}')
    margin = data['design_thrustOptimizedContour_perturbationMargin']
    noise = data['design_thrustOptimizedContour_objectiveNoiseFloor']
    local = data['design_thrustOptimizedContour_isLocalOptimum']
    gain = data['design_thrustOptimizedContour_normalizedGainOverParabola']
    seen = data['design_thrustOptimizedContour_admissibleNeighbours']
    closure = data['design_thrustOptimizedContour_exitMassClosure']
    converged = 0
    for index, (areaRatio, lengthFraction) in enumerate(designPoints):
        isOptimum = bool(local[index])
        converged += int(isOptimum)
        gainText = f'{100*gain[index]:11.3f}%' if np.isfinite(gain[index]) else f'{"rejected":>12s}'
        marginText = (f'{margin[index]:12.3e}' if np.isfinite(margin[index])
                      else f'{"none scored":>12s}')
        print(f'{areaRatio:6.1f} {lengthFraction:6.2f} {str(isOptimum):>9s} {int(seen[index]):5d} '
              f'{marginText} {noise[index]:12.3e} {gainText} {100*closure[index]:10.2f}')
    print()
    print(f'  {converged} of {len(designPoints)} searches converged at the settings this study '
          f'runs them at')
    print(f'  {studyOptimizerSettings}')
    print('  Those settings are well below the driver defaults, deliberately, because a full')
    print('  search is about twenty minutes and this sweep wants seven. Where a row says False,')
    print('  read the parabola column instead and re-run that point on its own.')
    print()
    print('  Two rows also show the searched contour closing mass several points worse than the')
    print('  parabola at the same design point. The closure band that guards the search runs at')
    print('  the coarse mesh; the reported solve is at the working mesh and is not re-checked')
    print('  against it, so a vector that was comparable during the search need not still be.')

    print()
    print('=' * 108)
    print('GRID CONVERGENCE, AND WHAT IT IS CONVERGENCE IN')
    print('=' * 108)
    print('At area ratio 40, 80 per cent bell. The raw coefficient and the mass closure move')
    print('together; the ratio is what settles. Each family is swept over its own wall held')
    print('fixed, so what moves is the flow solve rather than the geometry.')
    print()
    # When a search falls back to its incumbent, the wall it leaves behind IS the parabola, and
    # its sweep is then the parabola's sweep reprinted under another name. Saying so is the
    # difference between a third measurement and the same one twice.
    for family in families:
        mesh = data[f'mesh_{family}_mesh']
        raw = data[f'mesh_{family}_thrustCoef']
        closure = data[f'mesh_{family}_exitMassClosure']
        ratio = data[f'mesh_{family}_normalizedThrustCoef']
        finest = ratio[-1]
        rawFinest = raw[-1]
        label = familyLabels[family]
        if (family == 'thrustOptimizedContour'
                and np.allclose(raw, data['mesh_thrustOptimizedParabola_thrustCoef'],
                                rtol = 0.0, atol = 1e-12, equal_nan = True)):
            label += '  (the search returned its incumbent, so this is the parabola again)'
        print(f'  {label}')
        print(f'    {"mesh":>6s} {"Cf":>10s} {"err %":>9s} {"closure %":>10s} {"Cf/closure":>11s} {"err %":>9s}')
        for index in range(len(mesh)):
            if not np.isfinite(raw[index]):
                continue
            print(f'    {mesh[index]:6.0f} {raw[index]:10.5f} '
                  f'{100*(raw[index]/rawFinest-1):9.3f} {100*closure[index]:10.3f} '
                  f'{ratio[index]:11.5f} {100*(ratio[index]/finest-1):9.3f}')
        print()

    print('=' * 108)
    print('INTERNAL SHOCK')
    print('=' * 108)
    print('A truncated ideal contour is shock free by construction. The optimized families can')
    print('generate compression that coalesces, and at the length fractions swept here they')
    print('mostly do not: a chart parabola at 80 per cent bell turns gently enough that the wall')
    print('characteristics meet beyond the exit, which is no shock in the nozzle. Detection is a')
    print('property of the design point, not of the family.')
    print()
    print('Deflection is the total wall turning the front absorbs and the ratio is the stagnation')
    print('pressure surviving it. The capture is a weak-shock treatment, so it is only as good as')
    print('the weak column: a front turning the flow by more than a degree or two is reported')
    print('rather than trusted. A debit is blank where no shock was found, which is not zero.')
    print()
    header = (f'{"family":24s} {"cases":>7s} {"shocked":>8s} {"weak":>6s} '
              f'{"onset x":>9s} {"deflect":>9s} {"p0 ratio":>9s} {"debit %":>9s}')
    print(header)
    for family in families:
        detected = data[f'design_{family}_shockDetected']
        usable = np.isfinite(data[f'design_{family}_thrustCoef'])
        shocked = usable & (detected > 0)
        count = int(np.sum(shocked))
        if not count:
            print(f'{familyLabels[family]:24s} {int(np.sum(usable)):7d} {0:8d} '
                  f'{"":>6s} {"":>9s} {"":>9s} {"":>9s} {"":>9s}')
            continue
        onset = data[f'design_{family}_shockOnsetX'][shocked]
        deflection = data[f'design_{family}_shockPeakDeflection'][shocked]
        stagnation = data[f'design_{family}_shockStagnationRatio'][shocked]
        debit = data[f'design_{family}_shockThrustDebit'][shocked]
        weak = int(np.sum(stagnation > 0.99))
        print(f'{familyLabels[family]:24s} {int(np.sum(usable)):7d} {count:8d} {weak:6d} '
              f'{np.nanmin(onset):9.3f} {np.rad2deg(np.nanmax(deflection)):9.3f} '
              f'{np.nanmin(stagnation):9.5f} {100*np.nanmin(debit):9.4f}')

    # Whether the detector responds at all, which a table of zeros cannot say.
    if 'turningOffsets' in data:
        print()
        print('  Response against wall turning, at area ratio 40 and 80 per cent bell. The first')
        print('  two rows are the same wall written two ways: the charted parabola, and the cubic')
        print('  at the design vector that reproduces it. They have to agree, because the searched')
        print('  family contains the charted one, and every comparison between the two rests on it.')
        print()
        offsets = data['turningOffsets']
        isCubic = data['turningIsCubic']
        print(f'    {"wall":<30} {"shock":<6} {"onset x":>8} {"deflect":>8} '
              f'{"p0 ratio":>9} {"weak":<6} {"debit %":>9} {"Cf":>9} {"closure %":>9}')
        for index in range(len(offsets)):
            detected = bool(data['turning_shockDetected'][index])
            label = ('parabola, chart angles' if not isCubic[index] else
                     'cubic at the parabola vector' if offsets[index] == 0.0 else
                     f'cubic, inflection +{offsets[index]:.0f} deg')
            if detected:
                stagnation = float(data['turning_shockStagnationRatio'][index])
                onset = f'{data["turning_shockOnsetX"][index]:8.3f}'
                deflection = f'{np.rad2deg(data["turning_shockPeakDeflection"][index]):8.3f}'
                ratio = f'{stagnation:9.5f}'
                weak = str(stagnation > 0.99)
                debit = f'{100 * data["turning_shockThrustDebit"][index]:9.4f}'
            else:
                onset = deflection = f'{"-":>8}'
                ratio = f'{"-":>9}'
                weak = '-'
                debit = f'{"-":>9}'
            print(f'    {label:<30} {str(detected):<6} {onset} {deflection} {ratio} {weak:<6} '
                  f'{debit} {data["turning_thrustCoef"][index]:9.5f} '
                  f'{100 * data["turning_exitMassClosure"][index]:9.2f}')
        print()
        print('  Read the closure column beside the coefficient on the hardest-turned row. A wall')
        print('  that spills most of its mass out of the sampled plane can report a HIGHER raw')
        print('  coefficient than a good one, which is the failure mode the closure band in the')
        print('  optimizer exists to refuse.')

#--------------------------------------------------------------------------------------------------------------------------#
# -- The figure -- #
#--------------------------------------------------------------------------------------------------------------------------#

def draw(data):
    figure, axes = plt.subplots(2, 2, figsize = (14.0, 9.0))

    # -- The three walls at the worked design point -- #
    wallPanel = axes[0][0]
    pointIndex = designPoints.index((40.0, 0.80))
    for family in families:
        key = f'design_{family}_wallX_{pointIndex}'
        if key not in data:
            continue
        wallPanel.plot(data[key], data[f'design_{family}_wallR_{pointIndex}'],
                       color = familyColors[family], lw = 2.0, label = familyLabels[family])
    throatRadius = 1.0
    coneLength = conicalLength(40.0, throatRadius)
    wallPanel.plot([0.0, coneLength], [throatRadius, np.sqrt(40.0)], color = muted, lw = 1.2,
                   ls = '--', label = '15 deg cone, same area ratio')
    wallPanel.set_xlabel('Axial distance from the throat / throat radius')
    wallPanel.set_ylabel('Radius / throat radius')
    wallPanel.set_title('Three families, one design point: area ratio 40, 80 per cent bell')
    wallPanel.grid(True, alpha = 0.25)
    wallPanel.legend(loc = 'lower right', fontsize = 8, labelcolor = ink)

    # -- Wall angles against the chart -- #
    anglePanel = axes[0][1]
    eps = data['design_truncatedIdeal_requestedAreaRatio']
    bell = data['design_truncatedIdeal_requestedLengthFraction']
    chart = np.array([np.degrees(raoWallAngles(e, b)[0]) for e, b in zip(eps, bell)])
    for family in families:
        measured = data[f'design_{family}_inflectionWallAngle']
        anglePanel.plot(chart, measured - chart, 'o', color = familyColors[family], ms = 7,
                        label = familyLabels[family])
    anglePanel.axhline(0.0, color = muted, lw = 1.2, ls = '--')
    anglePanel.set_xlabel('Rao chart inflection angle [deg]')
    anglePanel.set_ylabel('Measured minus chart [deg]')
    anglePanel.set_title('Inflection angle against the chart\n'
                         'the chart is a parabola, so only that family should sit on zero')
    anglePanel.grid(True, alpha = 0.25)
    anglePanel.legend(loc = 'best', fontsize = 8, labelcolor = ink)

    # -- Grid convergence, raw against normalized -- #
    meshPanel = axes[1][0]
    for family in families:
        mesh = data[f'mesh_{family}_mesh']
        raw = data[f'mesh_{family}_thrustCoef']
        ratio = data[f'mesh_{family}_normalizedThrustCoef']
        meshPanel.plot(mesh, 100 * (raw / raw[-1] - 1), 'o--', color = familyColors[family],
                       ms = 5, lw = 1.2, alpha = 0.55,
                       label = f'{familyLabels[family]}, raw')
        meshPanel.plot(mesh, 100 * (ratio / ratio[-1] - 1), 'o-', color = familyColors[family],
                       ms = 6, lw = 2.0, label = f'{familyLabels[family]}, over closure')
    meshPanel.axhline(0.0, color = muted, lw = 1.0, ls = ':')
    meshPanel.set_xlabel('Characteristics launched from the throat arc')
    meshPanel.set_ylabel('Departure from the finest mesh [%]')
    meshPanel.set_title('Grid convergence: the raw coefficient carries the mass deficit,\n'
                        'the ratio does not')
    meshPanel.grid(True, alpha = 0.25)
    meshPanel.legend(loc = 'best', fontsize = 7, labelcolor = ink, ncol = 1)

    # -- The ordering, normalized -- #
    orderPanel = axes[1][1]
    reference = data['design_truncatedIdeal_normalizedThrustCoef']
    positions = np.arange(len(designPoints))
    width = 0.26
    for offset, family in enumerate(families):
        value = data[f'design_{family}_normalizedThrustCoef']
        orderPanel.bar(positions + (offset - 1) * width, 100 * (value / reference - 1),
                       width = width, color = familyColors[family], label = familyLabels[family])
    orderPanel.axhline(0.0, color = muted, lw = 1.2)
    orderPanel.set_xticks(positions)
    orderPanel.set_xticklabels([f'{int(e)}\n{b:.2f}' for e, b in designPoints], fontsize = 8)
    orderPanel.set_xlabel('Area ratio and percent bell')
    orderPanel.set_ylabel('Against the truncated ideal contour [%]')
    orderPanel.set_title('Thrust ordering, normalized by exit mass closure')
    orderPanel.grid(True, alpha = 0.25, axis = 'y')
    orderPanel.legend(loc = 'best', fontsize = 8, labelcolor = ink)

    figure.suptitle('Contour families: truncated ideal, Rao parabola, searched optimum',
                    fontsize = 13, fontweight = 'bold')
    figure.tight_layout(rect = [0, 0.055, 1, 0.965])
    figure.text(0.012, 0.045,
                'Every thrust coefficient is quoted over its exit-plane mass closure. The exit '
                'plane samples less mass than the throat passes and the momentum term scales with '
                'what it samples, so a raw comparison between families\ncompares their meshes as '
                'much as their walls: on the first run of this study that artefact was larger '
                'than the difference being looked for and reversed its sign. The normalization is '
                'a correction and not a fix.',
                fontsize = 8.5, color = ink, va = 'top')

    path = os.path.join(here, 'contourFamilies.png')
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print(f'wrote {os.path.basename(path)}')

def main():
    if '--draw' in sys.argv:
        data = dict(np.load(cachePath, allow_pickle = False))
    else:
        data = build()
    report(data)
    draw(data)

if __name__ == '__main__':
    main()
