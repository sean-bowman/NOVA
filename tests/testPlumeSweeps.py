# -- NOVA: Plume Sweeps -- #

'''

A plume sweep over a finished run (novaGui.plumeSweeps, novaGui.plumeQueue): the run's own plume
solved at each of a list of ambients, kept with the run.

    the request: two to maxPoints distinct ambients above zero, a pressure unit, a reach of two to
    six lip radii
    the delivered performance at an ambient is the run's own: at a back pressure the run named, it
    reproduces the run's performance summary to rounding
    each point is the march's: an ambient the march refuses is a refused point with its reason,
    the lip pressure ratio is the march's own, and a sweep drawn past two lip radii keeps the mass
    continuity error at both reaches
    the table marks an error past the trusted bound, and the figure draws one boundary per solved
    point, dashed past that bound, against the nozzle wall
    the run store keeps a run's sweeps in its folder, reads them back with the points that never
    solved cancelled, and the session keeps a run with a plume sweep as it keeps a named run
    the server solves a sweep in a worker process on the run's pickled nozzle, draws it, and
    deletes it
    a throttle sweep holds the ambient and varies the power level: its performance follows the
    frozen gas relation F = f F_vac - p_a A_e, a power level solves the same field as the ambient
    scaled by it, the separation limit is f_sep = 0.40 p_a / p_e and the march refuses below it,
    and the table and figures name each point by its power level with the limit and its bias

The contour the march runs on is a stand-in with a real exit profile, so the tests need no run.
The end-to-end test starts a worker process and solves one point, about ten seconds.

Author: Sean Bowman

'''

import os
import pickle
import sys
import time
import types

import numpy as np
import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

from novaGui import plumeSweeps, runStore
from novaGui.plumeQueue import PlumeQueue
from novaGui.runStore import RunStore

GAMMA = 1.4
CHAMBERPRESSURE = 4.0e6        # [Pa]

def _marchable(exitMach = 3.0, wallAngleDeg = 9.0, performance = None):

    '''
    A nozzle the station march can run on, as tests/testPlumeField.py builds one: a real exit
    profile across the radius, with the near-wall state the correlated structure reads.
    '''

    from NOVA.gasDynamics import areaMachRelation
    lipRadius = 0.30                                                          # [m]
    radii = np.linspace(0.0, lipRadius, 60)
    fraction = radii / lipRadius
    axisMach = exitMach + 0.4
    throatRadius = lipRadius / np.sqrt(areaMachRelation(exitMach, GAMMA))   # [m]
    wallMach = np.array([1.0, exitMach])
    return types.SimpleNamespace(
        nozzleScalingFactor = throatRadius, chamberGamma = GAMMA, chamberRGasConstant = 320.0,
        chamberStagnationTemperature = 3000.0, chamberPressure = CHAMBERPRESSURE,
        allXPoints = [np.full_like(radii, 1.0) / throatRadius], allRPoints = [radii / throatRadius],
        allMachNumbers = [axisMach + (exitMach - axisMach) * fraction],
        allFlowAngles = [np.radians(wallAngleDeg) * fraction],
        xNozzleWall = np.array([0.0, 1.0]), rNozzleWall = np.array([throatRadius, lipRadius]),
        nozzleNearWallMachNumber = wallMach,
        nozzleNearWallPressure = CHAMBERPRESSURE * (1.0 + 0.5 * (GAMMA - 1.0) * wallMach ** 2) ** (-GAMMA / (GAMMA - 1.0)),
        performance = performance)

@pytest.fixture(scope = 'module')
def nozzle():
    return _marchable()

@pytest.fixture(scope = 'module')
def lip(nozzle):
    return plumeSweeps.lipState(nozzle)

@pytest.fixture(scope = 'module')
def expanded(nozzle, lip):
    '''The stand-in's plume at a lip pressure ratio of 1.5, marched two lip radii: (ambient, outcome).'''
    ambient = lip['pressure'] / 1.5
    return ambient, plumeSweeps.solvePoint(nozzle, ambient, 2.0, lip)

def _summary(ambient: float):

    '''A performance summary from NOVA.performance on a solved exit plane stood in by its scalars.'''

    from NOVA.performance import summarizePerformance
    areaRatio = 4.2346
    source = types.SimpleNamespace(
        chamberPressure = CHAMBERPRESSURE, throatArea = 0.0213, exitPlaneAreaRatio = areaRatio,
        ceaOutput = types.SimpleNamespace(
            ceaResults = {'expansionRatio': areaRatio, 'characteristicVelocity': 1712.0, 'exitMach': 3.0,
                          'exitPressure': 1.1e5, 'exitTemperature': 1600.0, 'exitVelocity': 2900.0},
            nozzlePerformance = {'vacuumThrustCoef': 1.79}),
        targetExitPressure = 1.1e5, plumeAmbientPressure = ambient, chamberGamma = GAMMA,
        chamberRGasConstant = 320.0, chamberStagnationTemperature = 3000.0, vacuumThrustCoef = 1.74,
        exitVacuumSpecificImpulse = 302.5, frictionDragForce = None, engineMassFlow = 51.0,
        exitPlanePressure = None, exitPlaneMach = None, exitMassAveragedPressure = 1.12e5,
        exitAreaAveragedPressure = 1.1e5, exitMassAveragedMach = 2.98, exitMassAveragedTemperature = 1610.0,
        exitMassAveragedVelocity = 2890.0, exitMassClosure = 0.998, thrust = 150000.0,
        extensionFilmSolution = None, extensionCircuitSolution = None,
        turbineExhaust = None)
    return summarizePerformance(source)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The request -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testARequestLaysOutOnePointPerAmbient():
    sweep = plumeSweeps.build({'ambients': [40000, 25000.0, 10000], 'unit': 'kPa', 'reach': 2})
    assert [point['ambient'] for point in sweep['points']] == [40000.0, 25000.0, 10000.0]
    assert all(point['state'] == 'queued' and point['result'] is None for point in sweep['points'])
    assert sweep['reach'] == 2.0 and sweep['unit'] == 'kPa'
    assert sweep['name'] == 'Plume, 10 to 40 kPa'

@pytest.mark.parametrize('request_, reason', [
    ({'ambients': [40000]}, 'at least two'),
    ({'ambients': [40000, 0.0]}, 'above zero'),
    ({'ambients': [40000, -5.0]}, 'above zero'),
    ({'ambients': [40000, float('nan')]}, 'above zero'),
    ({'ambients': [40000, True]}, 'above zero'),
    ({'ambients': [40000, 40000]}, 'given twice'),
    ({'ambients': list(range(1, plumeSweeps.maxPoints + 2))}, f'at most {plumeSweeps.maxPoints}'),
    ({'ambients': [40000, 30000], 'unit': 'm'}, 'not a unit of pressure'),
    ({'ambients': [40000, 30000], 'reach': 1.0}, 'lip radii'),
    ({'ambients': [40000, 30000], 'reach': 6.5}, 'lip radii'),
    ({'ambients': [40000, 30000], 'name': 'x' * 81}, 'at most 80'),
])
def testARequestOutsideTheLimitsIsRefusedWithTheReason(request_, reason):
    with pytest.raises(ValueError, match = reason):
        plumeSweeps.build(request_)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The solve -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.mark.parametrize('ambient', [20000.0, 101325.0])
def testThePerformanceAtAnAmbientIsTheRunsOwn(ambient):
    '''
    NOVA.performance gives the delivered numbers at each back pressure the run names. At the same
    pressure, performanceAt reads the same numbers from the vacuum ones.
    '''
    summary = _summary(ambient)
    named = next(name for name, pressure in summary.backPressures.items() if name != 'vacuum' and pressure == ambient)
    at = plumeSweeps.performanceAt(types.SimpleNamespace(performance = summary, chamberPressure = CHAMBERPRESSURE), ambient)
    assert at['thrustCoef'] == pytest.approx(summary.thrustCoefDelivered[named], rel = 1e-12)
    assert at['specificImpulse'] == pytest.approx(summary.specificImpulseDelivered[named], rel = 1e-12)
    assert at['thrust'] == pytest.approx(summary.thrustDelivered[named], rel = 1e-12)

def testARunWithoutAPerformanceSummaryHasNoPerformanceToSweep():
    assert plumeSweeps.performanceAt(types.SimpleNamespace(performance = None, chamberPressure = 1.0), 1.0) is None

def testTheLipIsTheMarchsOwnAndTheWallIsDrawnFromIt(nozzle, lip):
    assert lip['radius'] == pytest.approx(0.30) and lip['x'] == pytest.approx(1.0)
    assert lip['wall']['x'][-1] == pytest.approx(0.0) and lip['wall']['r'][-1] == pytest.approx(1.0)
    assert lip['pressure'] > 0.0

def testAContourWithoutACharacteristicMeshSaysWhyItCannotBeSwept():
    bare = types.SimpleNamespace(xNozzleWall = np.array([0.0, 1.0]), rNozzleWall = np.array([0.1, 0.3]))
    assert 'characteristic mesh' in plumeSweeps.lipState(bare)['reason']

def testAnAmbientThatSeparatesTheNozzleIsRefusedWithTheMarchsReason(nozzle, lip):
    outcome = plumeSweeps.solvePoint(nozzle, lip['pressure'] / 0.3, 2.0, lip)
    assert outcome['state'] == 'refused' and outcome['result'] is None
    assert 'Summerfield' in outcome['error']

def testASolvedPointCarriesTheMarchsRatioErrorAndBoundary(nozzle, expanded):
    from NOVA.stationMarch import solveStationField
    ambient, outcome = expanded
    result = outcome['result']
    assert outcome['state'] == 'done' and outcome['error'] == ''
    field = solveStationField(plumeSweeps.plumeContour(nozzle), ambientPressure = ambient)
    assert result['lipRatio'] == pytest.approx(field.lipPressureRatio, rel = 1e-9)
    assert result['nearDrift'] == result['drift'] == pytest.approx(field.massDriftWorst)
    assert result['trustworthy'] is True and result['jetType'] == 'underexpanded'
    # The boundary leaves the lip, in lip radii from the exit plane
    assert result['boundary']['x'][0] == pytest.approx(0.0, abs = 1e-6)
    assert result['boundary']['r'][0] == pytest.approx(1.0, abs = 1e-3)
    assert result['boundary']['x'][-1] == pytest.approx(2.0, abs = 0.05)
    assert len(result['boundary']['x']) <= plumeSweeps.boundaryPoints
    assert result['thrustCoef'] is None                      # the stand-in carries no performance summary

def testASweepDrawnFartherKeepsTheErrorAtBothReaches(nozzle, lip, expanded):
    ambient, near = expanded
    result = plumeSweeps.solvePoint(nozzle, ambient, 2.5, lip)['result']
    assert result['nearDrift'] == pytest.approx(near['result']['drift'])
    assert abs(result['drift']) > abs(result['nearDrift'])
    assert result['boundary']['x'][-1] == pytest.approx(2.5, abs = 0.05)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The table and the figure -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _solvedSweep(reach = 2.0, drift = 0.3, tolerance = 1.0):

    sweep = plumeSweeps.build({'ambients': [40000.0, 20000.0, 10000.0], 'unit': 'kPa', 'reach': reach})
    lipPressure = 30000.0
    sweep.update(runId = 7, number = 1, lip = {'pressure': lipPressure, 'x': 1.0, 'radius': 0.3,
                                               'wall': {'x': [-3.0, 0.0], 'r': [0.5, 1.0]}})
    first, second, third = sweep['points']
    first.update(state = 'refused', error = 'Pe/Pa is 0.300, below the Summerfield separation criterion')
    for point, error in ((second, drift), (third, 3.0 * tolerance)):
        point.update(state = 'done', result = {
            'lipRatio': lipPressure / point['ambient'], 'jetType': 'underexpanded', 'thrustCoef': 1.71,
            'specificImpulse': 298.4, 'thrust': 152300.0, 'jetDiameter': 0.71, 'shockCellLength': 1.2,
            'axisShockKind': 'regular reflection', 'axisShockAt': 4.2, 'nearDrift': drift, 'drift': error,
            'trustworthy': abs(error) <= tolerance, 'tolerance': tolerance, 'boundaryMach': 3.4, 'notes': ['marched'],
            'boundary': {'x': [0.0, 1.0, 2.0], 'r': [1.0, 1.1, 1.15]}})
    return sweep

def testTheTableNamesEachPointsNumbersAndMarksAnErrorPastTheBound():
    shown = plumeSweeps.table(_solvedSweep(reach = 4.0))
    keys = [column['key'] for column in shown['columns']]
    assert keys[-2:] == ['nearDrift', 'drift']
    refused, kept, loose = shown['points']
    assert refused['state'] == 'refused' and refused['cells'] == {} and 'Summerfield' in refused['error']
    assert kept['cells']['thrust']['text'] == '152.3' and kept['cells']['jetDiameter']['text'] == '710.0'
    assert kept['cells']['specificImpulse']['text'] == '298.4' and kept['cells']['thrustCoef']['text'] == '1.7100'
    assert kept['cells']['axisShock']['text'] == '4.2, regular reflection'
    assert kept['cells']['drift']['tone'] == '' and loose['cells']['drift']['tone'] == 'warn'
    assert shown['counts']['done'] == 2 and shown['counts']['refused'] == 1
    assert shown['lip']['pressureText'] == '30 kPa' and kept['label'] == '20 kPa'

def testASweepDrawnAtTwoLipRadiiHasOneErrorColumn():
    keys = [column['key'] for column in plumeSweeps.table(_solvedSweep(reach = 2.0))['columns']]
    assert 'nearDrift' in keys and 'drift' not in keys

def testEveryNumberColumnCarriesTheStatusOfItsModels():
    shown = plumeSweeps.table(_solvedSweep())
    badges = {column['key']: column['validation'] for column in shown['columns']}
    if badges['nearDrift'] is None:
        pytest.skip('docs/validationStatus.json is not readable here')
    assert badges['lipRatio'] is None
    assert badges['nearDrift']['status'] == 'unvalidated' and badges['jetDiameter']['status'] == 'unvalidated'
    assert {model['id'] for model in badges['thrustCoef']['models']} == {'contour', 'deliveredPerformance'}
    assert shown['badge']['status'] == 'unvalidated'

def testTheFigureDrawsEachSolvedBoundaryAgainstTheWall():
    import json
    figure = json.loads(plumeSweeps.figure(_solvedSweep(), 'dark'))
    wall, *lines = figure['data']
    assert wall['name'] == 'nozzle wall' and wall['x'] == [-3.0, 0.0]
    # Ordered by lip ratio, the refused point left out, the one past the bound dashed
    assert [line['name'].split(',')[0] for line in lines] == ['1.500', '3.000']
    assert [line['line']['dash'] for line in lines] == ['solid', 'dash']
    assert lines[0]['customdata'][0] == 1
    assert 'trusted bound' in figure['layout']['title']['text']
    assert figure['layout']['yaxis']['scaleanchor'] == 'x'
    # Opened on the end of the nozzle as long as the reach, the wall's start a zoom out away
    assert figure['layout']['xaxis']['range'] == [-2.0, 2.0]

def testNoFigureBeforeAPointIsSolved():
    sweep = plumeSweeps.build({'ambients': [40000.0, 20000.0]})
    sweep.update(runId = 7, number = 1, lip = None)
    assert plumeSweeps.figure(sweep, 'light') is None

#--------------------------------------------------------------------------------------------------------------------------#
# -- Throttle sweeps -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testAThrottleRequestLaysOutOnePointPerPowerLevelAtOneAmbient():
    sweep = plumeSweeps.build({'kind': 'throttle', 'ambient': 8850.0, 'fractions': [1.0, 0.5, 0.25], 'unit': 'kPa'})
    assert sweep['kind'] == 'throttle' and sweep['ambient'] == 8850.0
    assert [point['fraction'] for point in sweep['points']] == [1.0, 0.5, 0.25]
    assert all('ambient' not in point and point['state'] == 'queued' for point in sweep['points'])
    assert sweep['name'] == 'Throttle, 100 to 25 % at 8.85 kPa'
    assert plumeSweeps.pointConditions(sweep, sweep['points'][1]) == (8850.0, 0.5)

def testASweepSavedWithoutAKindIsAnAmbientSweepAtRatedPower():
    sweep = plumeSweeps.build({'ambients': [40000.0, 20000.0]})
    del sweep['kind']
    assert plumeSweeps.pointConditions(sweep, sweep['points'][1]) == (20000.0, 1.0)
    sweep.update(runId = 7, number = 1, lip = None)
    shown = plumeSweeps.table(sweep)
    assert shown['kind'] == 'ambient' and shown['separation'] is None and shown['ambient'] is None

@pytest.mark.parametrize('request_, reason', [
    ({'kind': 'sideways', 'ambients': [1.0, 2.0]}, 'not a kind of plume sweep'),
    ({'kind': 'throttle', 'fractions': [1.0, 0.5]}, 'not an ambient pressure'),
    ({'kind': 'throttle', 'ambient': 0.0, 'fractions': [1.0, 0.5]}, 'not an ambient pressure'),
    ({'kind': 'throttle', 'ambient': 9000.0, 'fractions': [1.0]}, 'at least two power levels'),
    ({'kind': 'throttle', 'ambient': 9000.0, 'fractions': [1.0, 0.0]}, 'fraction of rated'),
    ({'kind': 'throttle', 'ambient': 9000.0, 'fractions': [1.0, 80.0]}, 'at most 1.5'),
    ({'kind': 'throttle', 'ambient': 9000.0, 'fractions': [1.0, 1.0]}, 'a power level is given twice'),
])
def testAThrottleRequestOutsideTheLimitsIsRefusedWithTheReason(request_, reason):
    with pytest.raises(ValueError, match = reason):
        plumeSweeps.build(request_)

@pytest.mark.parametrize('fraction', [0.25, 0.6, 1.2])
def testThePerformanceAtAPowerLevelFollowsTheFrozenGasRelation(fraction):
    '''
    At a frozen gas state the exit plane's vacuum thrust scales with the power level while its
    vacuum coefficient and impulse hold, so F(f, p_a) = f F_vac - p_a A_e. The same relation makes
    a power level and an ambient interchangeable in the coefficient and the impulse: f at p_a reads
    as rated power at p_a / f, with the thrust scaled by f.
    '''
    ambient = 20000.0                                                         # [Pa]
    summary = _summary(ambient)
    run = types.SimpleNamespace(performance = summary, chamberPressure = CHAMBERPRESSURE)
    at = plumeSweeps.performanceAt(run, ambient, fraction)
    vacuumThrust = summary.thrustDelivered['vacuum']                          # [N]
    throatArea = vacuumThrust / (CHAMBERPRESSURE * summary.thrustCoefDelivered['vacuum'])  # [m^2]
    exitArea = summary.areaRatio * throatArea                                 # [m^2]
    assert at['thrust'] == pytest.approx(fraction * vacuumThrust - ambient * exitArea, rel = 1e-12)
    rated = plumeSweeps.performanceAt(run, ambient / fraction)
    assert at['thrustCoef'] == pytest.approx(rated['thrustCoef'], rel = 1e-12)
    assert at['specificImpulse'] == pytest.approx(rated['specificImpulse'], rel = 1e-12)
    assert at['thrust'] == pytest.approx(fraction * rated['thrust'], rel = 1e-12)

def testAPowerLevelSolvesTheSameFieldAsTheAmbientScaledByIt(nozzle, lip, expanded):
    '''
    The march carries one stagnation pressure and its relations are homogeneous in pressure, so
    half power against an ambient is rated power against half that ambient: the same ratios, the
    same mass error and the same boundary.
    '''
    ambient, rated = expanded
    throttled = plumeSweeps.solvePoint(nozzle, 0.5 * ambient, 2.0, lip, fraction = 0.5)
    assert throttled['state'] == 'done'
    result, reference = throttled['result'], rated['result']
    assert result['fraction'] == 0.5
    assert result['lipRatio'] == pytest.approx(reference['lipRatio'], rel = 1e-12)
    assert result['exitRatio'] == pytest.approx(reference['exitRatio'], rel = 1e-12)
    assert result['nearDrift'] == pytest.approx(reference['nearDrift'], rel = 1e-9)
    assert result['boundary'] == reference['boundary']

def testThePowerLevelBelowTheSeparationLimitIsRefusedOnTheCriterion(nozzle, lip):
    '''
    At a frozen gas state the exit pressure scales with the chamber, so the power level at which
    the exit pressure ratio reaches the Summerfield criterion is exact: f_sep = 0.40 p_a / p_e. Just
    below it the march refuses as separated; well above it the plume solves.
    '''
    from NOVA.plume import separationPressureRatio
    ambient = 0.5 * lip['exitPressure']                                       # [Pa] full power at an exit ratio of 2
    sweep = plumeSweeps.build({'kind': 'throttle', 'ambient': ambient, 'fractions': [1.0, 0.19], 'unit': 'kPa'})
    sweep.update(runId = 7, number = 1, lip = lip)
    limit = plumeSweeps.separation(sweep)
    assert limit['fraction'] == pytest.approx(separationPressureRatio * ambient / lip['exitPressure'], rel = 1e-12)
    assert limit['fraction'] == pytest.approx(0.2, rel = 1e-12) and limit['lowFraction'] == pytest.approx(0.175, rel = 1e-12)
    below = plumeSweeps.solvePoint(nozzle, ambient, 2.0, lip, fraction = 0.19)
    assert below['state'] == 'refused' and 'Summerfield' in below['error']
    full = plumeSweeps.solvePoint(nozzle, ambient, 2.0, lip, fraction = 1.0)
    assert full['state'] == 'done' and full['result']['exitRatio'] == pytest.approx(2.0, rel = 1e-9)

def _throttleSweep():

    sweep = plumeSweeps.build({'kind': 'throttle', 'ambient': 10000.0, 'fractions': [1.0, 0.5, 0.2], 'unit': 'kPa'})
    lipPressure = 30000.0
    sweep.update(runId = 7, number = 2, lip = {'pressure': lipPressure, 'exitPressure': 20000.0, 'x': 1.0, 'radius': 0.3,
                                               'wall': {'x': [-3.0, 0.0], 'r': [0.5, 1.0]}})
    full, half, low = sweep['points']
    low.update(state = 'refused', error = 'Pe/Pa is 0.400, below the Summerfield separation criterion')
    for point in (full, half):
        fraction = point['fraction']
        point.update(state = 'done', result = {
            'fraction': fraction, 'lipRatio': fraction * lipPressure / 10000.0, 'exitRatio': fraction * 2.0,
            'jetType': 'underexpanded', 'thrustCoef': 1.8, 'specificImpulse': 440.0 * fraction ** 0.05,
            'thrust': 100000.0 * fraction - 3000.0, 'jetDiameter': 0.71, 'shockCellLength': 1.2,
            'axisShockKind': '', 'axisShockAt': None, 'nearDrift': 0.3, 'drift': 0.3, 'trustworthy': True,
            'tolerance': 1.0, 'boundaryMach': 3.4, 'notes': [], 'boundary': {'x': [0.0, 1.0], 'r': [1.0, 1.1]}})
    return sweep

def testAThrottleTableNamesEachPowerLevelAndGivesTheSeparationLimitWithItsBias():
    shown = plumeSweeps.table(_throttleSweep())
    assert shown['kind'] == 'throttle' and shown['ambientText'] == '10 kPa'
    assert [column['key'] for column in shown['columns']][:2] == ['exitRatio', 'lipRatio']
    assert [point['label'] for point in shown['points']] == ['100 %', '50 %', '20 %']
    assert shown['points'][1]['cells']['exitRatio']['text'] == '1.000'
    assert [point['fraction'] for point in shown['points']] == [1.0, 0.5, 0.2]
    separation = shown['separation']
    assert separation['fraction'] == pytest.approx(0.2) and separation['lowFraction'] == pytest.approx(0.175)
    assert 'below 20 % power at 10 kPa' in separation['limit'] and '17.5 %' in separation['limit']
    assert f'{plumeSweeps.frozenGasBias:g} % high' in separation['bias'] and 'safe side' in separation['bias']

def testAThrottleSweepDrawsItsPerformanceAgainstPowerLevelWithTheLimitMarked():
    import json
    sweep = _throttleSweep()
    figure = json.loads(plumeSweeps.performanceFigure(sweep, 'dark'))
    thrust, impulse = figure['data']
    assert thrust['x'] == [50.0, 100.0] and thrust['y'] == [47.0, 97.0]
    assert impulse['yaxis'] == 'y2' and impulse['x'] == thrust['x']
    band, line = figure['layout']['shapes']
    assert line['x0'] == line['x1'] == pytest.approx(20.0)
    assert band['x0'] == pytest.approx(17.5) and band['x1'] == pytest.approx(20.0)
    assert 'separates below 20 %' in figure['layout']['annotations'][0]['text']
    # The boundaries name each line by its power level
    boundaries = json.loads(plumeSweeps.figure(sweep, 'dark'))
    assert [trace['name'] for trace in boundaries['data'][1:]] == ['50 %, 1.500', '100 %, 3.000']
    assert '10 kPa held' in boundaries['layout']['title']['text']
    # An ambient sweep draws no performance against power level
    assert plumeSweeps.performanceFigure(_solvedSweep(), 'dark') is None

#--------------------------------------------------------------------------------------------------------------------------#
# -- Kept with the run -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _storedRun(store: RunStore, title: str = '') -> int:

    runId, folder = store.claim()
    store.save(runId, {'runName': 'standIn', 'title': title, 'elapsedSec': 1.0, 'headline': '', 'numbers': [],
                       'sweep': None, 'finishedAt': time.time(), 'config': {}, 'warnings': [],
                       'outputDir': folder, 'picklePath': ''})
    return runId

def testTheStoreKeepsARunsSweepsInItsFolderAndNeverMakesOneAgain(tmp_path):
    store = RunStore(str(tmp_path))
    runId = _storedRun(store)
    sweep = {**_solvedSweep(), 'runId': runId, 'number': 2}
    store.savePlumeSweep(runId, sweep)
    assert os.path.isfile(os.path.join(store.folder(runId), runStore.plumeFolderName, 'plume2.json'))
    [read] = store.plumeSweeps(runId)
    assert read['number'] == 2 and read['points'][1]['result']['thrust'] == 152300.0
    store.remove(runId)
    with pytest.raises(FileNotFoundError):
        store.savePlumeSweep(runId, sweep)
    assert not os.path.isdir(store.folder(runId)) and store.plumeSweeps(runId) == []

def testASweepThatNeverFinishedReadsCancelledAndCanBeQueuedAgain(tmp_path):
    store = RunStore(str(tmp_path))
    runId = _storedRun(store)
    sweep = {**_solvedSweep(), 'runId': runId, 'number': 1}
    sweep['points'][2].update(state = 'running', result = None)
    store.savePlumeSweep(runId, sweep)
    events = []
    plumes = PlumeQueue(store, events.append)
    plumes.load([runId])
    [shown] = plumes.sweepsOf(runId)
    assert [point['state'] for point in shown['points']] == ['refused', 'done', 'cancelled']
    assert shown['points'][2]['error'] == 'NOVA closed before it was solved'
    assert store.plumeSweeps(runId)[0]['points'][2]['state'] == 'cancelled'
    # Queued again and deleted before its worker gets far: the file goes, and nothing writes it back
    assert plumes.resume(runId, 1, os.path.join(str(tmp_path), 'missing.pkl')) == 1
    plumes.delete(runId, 1)
    assert store.plumeSweeps(runId) == [] and plumes.sweepsOf(runId) == []
    _settle(plumes)
    assert store.plumeSweeps(runId) == []
    assert {'type': 'plumeSweeps', 'runId': runId} in events

def testARunWithAPlumeSweepStaysAsANamedRunDoes(tmp_path, monkeypatch):
    from novaGui.session import RunRecord, RunSession
    store = RunStore(str(tmp_path))
    swept, loose = _storedRun(store), _storedRun(store)
    store.savePlumeSweep(swept, {**_solvedSweep(), 'runId': swept, 'number': 1})
    monkeypatch.setattr(runStore, 'unnamedRuns', 1)
    session = RunSession(store = store)
    try:
        assert session.plumeSweeps.holds(swept) and not session.plumeSweeps.holds(loose)
        newest, folder = store.claim()
        session.adopt(RunRecord(newest, {'ok': True, 'runName': 'standIn', 'outputDir': folder}, folder = folder))
        assert swept in session.runs and loose not in session.runs and newest in session.runs
        # Deleting the run takes its plume sweeps
        session.delete(swept)
        assert not session.plumeSweeps.holds(swept) and not os.path.isdir(store.folder(swept))
    finally:
        session.shutdown()

def _settle(plumes: PlumeQueue, timeoutSec: float = 60.0) -> None:

    '''Wait for the queue's worker to end.'''

    ends = time.time() + timeoutSec
    while plumes.busy and time.time() < ends:
        time.sleep(0.1)
    assert not plumes.busy, 'the plume worker did not end'

#--------------------------------------------------------------------------------------------------------------------------#
# -- Through the server -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheViewIsThereForAContourTheMarchCanContinue(nozzle):
    from novaGui import viewCatalog
    assert 'plumeSweep' in viewCatalog.availableViews(nozzle, {})
    bare = types.SimpleNamespace(xNozzleWall = np.array([0.0, 1.0]), rNozzleWall = np.array([0.1, 0.3]))
    assert 'plumeSweep' not in viewCatalog.availableViews(bare, {})

def testTheServerSolvesASweepOnTheRunsNozzleDrawsItAndDeletesIt(tmp_path, nozzle, lip):
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from novaGui.server import createApp
    from novaGui.session import RunRecord, RunSession

    picklePath = tmp_path / 'novaGuiResult.pkl'
    with open(picklePath, 'wb') as handle:
        # The stand-in with a performance summary, so the throttle sweep has thrust to draw
        pickle.dump(_marchable(performance = _summary(20000.0)), handle)
    session = RunSession()
    record = RunRecord(41, {'ok': True, 'runName': 'standIn', 'picklePath': str(picklePath), 'elapsedSec': 1.0})
    session.adopt(record)
    try:
        with TestClient(createApp(session = session, warm = False)) as client:
            assert client.get('/api/runs/99/plume-sweeps').status_code == 404
            assert client.get('/api/runs/41/plume-lip').json() == {'pressure': pytest.approx(lip['pressure']),
                                                                   'exitPressure': pytest.approx(lip['exitPressure']), 'reason': ''}
            refused = client.post('/api/runs/41/plume-sweeps', json = {'ambients': [20000.0]})
            assert refused.status_code == 400 and 'at least two' in refused.json()['detail']

            # One ambient the march refuses, one it solves
            ambients = [lip['pressure'] / 0.3, lip['pressure'] / 1.5]
            added = client.post('/api/runs/41/plume-sweeps', json = {'ambients': ambients, 'unit': 'kPa'}).json()
            assert added['number'] == 1 and added['runId'] == 41
            _settle(session.plumeSweeps, 120.0)
            [shown] = client.get('/api/runs/41/plume-sweeps').json()['sweeps']
            assert [point['state'] for point in shown['points']] == ['refused', 'done']
            assert shown['points'][1]['cells']['lipRatio']['text'] == '1.500'
            figure = client.get('/api/runs/41/plume-sweeps/1/figure', params = {'mode': 'light'}).json()
            assert len(figure['data']) == 2

            assert client.get('/api/runs/41/plume-sweeps/1/figure', params = {'plot': 'performance'}).status_code == 404
            assert client.get('/api/runs/41/plume-sweeps/1/figure', params = {'plot': 'sideways'}).status_code == 400

            assert client.post('/api/runs/41/plume-sweeps/1/resume').json() == {'queued': 0}
            assert client.delete('/api/runs/41/plume-sweeps/1').json() == {'deleted': 1}
            assert client.get('/api/runs/41/plume-sweeps/1/figure').status_code == 404
            assert client.delete('/api/runs/41/plume-sweeps/1').status_code == 404

            # A throttle sweep at the ambient that puts full power at an exit pressure ratio of 2:
            # full power solves, and below the separation limit at a fifth of it the march refuses
            ambient = 0.5 * lip['exitPressure']
            throttled = client.post('/api/runs/41/plume-sweeps', json = {'kind': 'throttle', 'ambient': ambient,
                                                                         'fractions': [1.0, 0.19]}).json()
            assert throttled['number'] == 1 and throttled['kind'] == 'throttle'
            _settle(session.plumeSweeps, 120.0)
            listed = client.get('/api/runs/41/plume-sweeps').json()
            assert listed['maxFraction'] == plumeSweeps.maxFraction and listed['separationRatio'] == 0.4
            [shown] = listed['sweeps']
            assert [point['state'] for point in shown['points']] == ['done', 'refused']
            assert shown['separation']['fraction'] == pytest.approx(0.2)
            performance = client.get('/api/runs/41/plume-sweeps/1/figure', params = {'plot': 'performance'}).json()
            assert performance['data'][0]['x'] == [100.0]
    finally:
        session.shutdown()

#--------------------------------------------------------------------------------------------------------------------------#
# -- On the shipped nozzle -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheShippedNozzleHoldsMassAtTwoLipRadiiAndMatchesItsOwnPerformance():
    '''
    The shipped nozzle's run, a local output that is not in the repository. At a lip pressure ratio
    of one the march conserves mass within its tolerance at two lip radii, and at sea level the
    sweep's performance is the run's own at its named sea level back pressure.
    '''
    path = os.path.join(root, 'featureShowcase', 'showcaseBase.pkl')
    if not os.path.isfile(path):
        pytest.skip('showcaseBase.pkl is a local run and is not in this checkout')
    with open(path, 'rb') as handle:
        shipped = pickle.load(handle)
    lipShipped = plumeSweeps.lipState(shipped)
    outcome = plumeSweeps.solvePoint(shipped, lipShipped['pressure'], 2.0, lipShipped)
    assert outcome['state'] == 'done' and outcome['result']['trustworthy']
    summary = shipped.performance
    at = plumeSweeps.performanceAt(shipped, summary.backPressures['seaLevel'])
    assert at['thrustCoef'] == pytest.approx(summary.thrustCoefDelivered['seaLevel'], rel = 1e-12)
    assert at['specificImpulse'] == pytest.approx(summary.specificImpulseDelivered['seaLevel'], rel = 1e-12)

def testTheShippedNozzleThrottlesToAQuarterAtTheAmbientThatPutsFullPowerAtTheTopOfTheEnvelope():
    '''
    docs/plumeThrottleModel.md on the shipped nozzle: with the ambient chosen so that rated power
    sits at an exit pressure ratio of 2, a quarter of rated power solves within the march's
    tolerance at an exit pressure ratio of 0.5, and at a fifth, on the Summerfield floor itself,
    the march declines first on the strength of the lip shock.
    '''
    from NOVA.plume import plumeFieldMaxPressureRatio
    path = os.path.join(root, 'featureShowcase', 'showcaseBase.pkl')
    if not os.path.isfile(path):
        pytest.skip('showcaseBase.pkl is a local run and is not in this checkout')
    with open(path, 'rb') as handle:
        shipped = pickle.load(handle)
    lipShipped = plumeSweeps.lipState(shipped)
    ambient = lipShipped['exitPressure'] / plumeFieldMaxPressureRatio
    quarter = plumeSweeps.solvePoint(shipped, ambient, 2.0, lipShipped, fraction = 0.25)
    assert quarter['state'] == 'done' and quarter['result']['trustworthy']
    assert quarter['result']['exitRatio'] == pytest.approx(0.5, rel = 1e-9)
    fifth = plumeSweeps.solvePoint(shipped, ambient, 2.0, lipShipped, fraction = 0.20)
    assert fifth['state'] == 'refused' and 'oblique shock' in fifth['error']
