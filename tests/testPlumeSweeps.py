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
    assert shown['lip']['pressureText'] == '30 kPa' and kept['ambientText'] == '20 kPa'

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
        pickle.dump(nozzle, handle)
    session = RunSession()
    record = RunRecord(41, {'ok': True, 'runName': 'standIn', 'picklePath': str(picklePath), 'elapsedSec': 1.0})
    session.adopt(record)
    try:
        with TestClient(createApp(session = session, warm = False)) as client:
            assert client.get('/api/runs/99/plume-sweeps').status_code == 404
            assert client.get('/api/runs/41/plume-lip').json() == {'pressure': pytest.approx(lip['pressure']), 'reason': ''}
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

            assert client.post('/api/runs/41/plume-sweeps/1/resume').json() == {'queued': 0}
            assert client.delete('/api/runs/41/plume-sweeps/1').json() == {'deleted': 1}
            assert client.get('/api/runs/41/plume-sweeps/1/figure').status_code == 404
            assert client.delete('/api/runs/41/plume-sweeps/1').status_code == 404
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
