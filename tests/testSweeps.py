# -- NOVA: GUI Run Queue and Trade Sweep Tests -- #

'''

The GUI's run queue and trade sweeps: a sweep laid out from the fields it varies and refused when
the form could not run it, runs that queue and start in turn, cancelling one run or the whole
queue, a sweep that runs its points and goes on past a failed one, its table and its plot, a sweep
that outlasts its window in the run store and queues its unrun points again, a run whose sweep is
gone, and deleting a sweep.

The session tests stand a scripted worker in for NOVA's (`_ScriptedSession`): a thread that reports
a result for its config after a short hold, fails a config marked to fail, and stops when
terminated, so the queue's logic runs in seconds without a NOVA run. tests/testWebServer.py starts
real workers.

Author: Sean Bowman

'''

import json
import os
import queue
import sys
import threading
import time

import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from novaGui import configSchema, sweeps
from novaGui import session as sessionModule
from novaGui.runStore import RunStore
from novaGui.server import createApp
from novaGui.session import RunSession

failingPressure = 7.0e6         # [Pa] the scripted worker fails a run at this chamber pressure

class _ScriptedProcess:
    '''A worker stand-in on a thread: a result after `holdSec`, none when terminated first.'''

    def __init__(self, config: dict, outputDir: str, eventQueue, holdSec: float):
        self.config = config
        self.outputDir = outputDir
        self.eventQueue = eventQueue
        self.holdSec = holdSec
        self.exitcode = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target = self._run, daemon = True)

    def _run(self):
        if self._stop.wait(self.holdSec):
            self.exitcode = -15
            return
        pressure = float(self.config.get('chamberPressure') or 0.0)
        if pressure == failingPressure:
            result = {'ok': False, 'runName': self.config.get('filename', ''), 'error': 'the scripted run failed',
                      'elapsedSec': self.holdSec}
        else:
            result = {'ok': True, 'runName': self.config.get('filename', ''), 'outputDir': self.outputDir,
                      'elapsedSec': self.holdSec, 'headline': f'Isp {pressure / 2e4:.1f} s',
                      'numbers': [{'key': 'isp', 'label': 'Delivered Isp', 'value': f'{pressure / 2e4:.1f}',
                                   'unit': 's', 'tone': ''}]}
        self.eventQueue.put(('result', result))
        self.exitcode = 0

    def start(self):
        self._thread.start()

    def is_alive(self):
        return self._thread.is_alive()

    def join(self, timeout = None):
        self._thread.join(timeout)

    def terminate(self):
        self._stop.set()

class _ScriptedSession(RunSession):
    '''A session whose runs are scripted; `holdSec` is how long each takes.'''
    holdSec = 0.05

    def _spawn(self, config, outputDir, mode, runId):
        events = queue.Queue()
        return _ScriptedProcess(config, outputDir, events, self.holdSec), events

def _scripted(store = None, holdSec = 0.05) -> _ScriptedSession:
    session = _ScriptedSession(store = store)
    session.holdSec = holdSec
    session.events = []
    publish = session._publish
    session._publish = lambda event: session.events.append(dict(event)) or publish(event)
    return session

def _settled(session: RunSession, timeoutSec: float = 20.0) -> None:
    '''Wait until no run is going and none is queued.'''
    deadline = time.time() + timeoutSec
    while not session.idle and time.time() < deadline:
        time.sleep(0.02)
    assert session.idle, 'the queue did not empty in time'

def _waitFor(test, timeoutSec: float = 10.0) -> None:
    deadline = time.time() + timeoutSec
    while not test() and time.time() < deadline:
        time.sleep(0.02)
    assert test(), 'the session did not get there in time'

def _sweep(*fields, name = '', config = None) -> dict:
    return sweeps.build({'name': name, 'config': config or {'filename': 'trade', 'chamberPressure': 6.0e6},
                         'fields': [{'key': key, 'unit': unit, 'values': values} for key, unit, values in fields]})

#--------------------------------------------------------------------------------------------------------------------------#
# -- Laying a sweep out -- #
#--------------------------------------------------------------------------------------------------------------------------#
def testASweepLaysOutItsPointsWithTheFirstFieldFastest():
    '''Two fields make a grid, the first field varying fastest; each value reads in the unit it was entered in.'''
    sweep = _sweep(('chamberPressure', 'MPa', [6.0e6, 8.0e6, 1.0e7]), ('OFRatio', '', [5.0, 6.0]))
    assert sweep['name'] == 'Chamber pressure by O/F ratio'
    assert [point['at'] for point in sweep['points']] == [[0, 0], [1, 0], [2, 0], [0, 1], [1, 1], [2, 1]]
    assert sweep['fields'][0]['texts'] == ['6 MPa', '8 MPa', '10 MPa'] and sweep['fields'][1]['texts'] == ['5', '6']
    point = sweep['points'][4]
    assert point['values'] == {'chamberPressure': 8.0e6, 'OFRatio': 6.0} and point['state'] == 'queued'
    assert sweeps.pointConfig(sweep, point) == {'filename': 'trade', 'chamberPressure': 8.0e6, 'OFRatio': 6.0}
    assert sweeps.pointLabel(sweep, point) == 'Chamber pressure by O/F ratio, 5 of 6: Chamber pressure 8 MPa, O/F ratio 6'

def testAChoiceAndASwitchSweepByTheirLabels():
    sweep = _sweep(('Fuel', '', ['CH4', 'RP-1']), ('filmCooling', '', [True, False]), name = '  Fuel   and film ')
    assert sweep['name'] == 'Fuel and film'
    assert sweep['fields'][0]['texts'] == ['CH4', 'RP-1'] and sweep['fields'][1]['texts'] == ['on', 'off']

@pytest.mark.parametrize('fields, reason', [
    ([('notAField', '', [1.0, 2.0])], 'is not a field a sweep can vary'),
    ([('chamberPressure', 'MPa', [6.0e6])], 'give at least two values'),
    ([('chamberPressure', 'MPa', [6.0e6, 6.0e6])], 'a value is given twice'),
    ([('chamberPressure', 'm', [6.0e6, 7.0e6])], 'is not a unit of pressure'),
    ([('chamberPressure', 'MPa', [6.0e6, 'high'])], 'is not a number'),
    ([('divergingSectionType', '', ['tic', 'bell'])], 'is not one of its choices'),
    ([('filmCooling', '', [True, 'off'])], 'is not on or off'),
    ([('chamberPressure', 'MPa', [6.0e6, 7.0e6]), ('chamberPressure', 'MPa', [6.0e6, 7.0e6])], 'is swept twice'),
    ([('chamberPressure', 'MPa', [1.0e6 * value for value in range(1, sweeps.maxPoints + 2)])], 'queues at most'),
    ([('chamberPressure', 'MPa', [6.0e6, 7.0e6]), ('OFRatio', '', [float(value) for value in range(1, sweeps.maxSeries + 2)])],
     'a second field takes at most'),
])
def testASweepTheFormCouldNotRunIsRefused(fields, reason):
    with pytest.raises(ValueError, match = reason):
        _sweep(*fields)

def testOnlyFieldsWithARowSweep():
    fields = sweeps.sweepableFields()
    assert {'chamberPressure', 'OFRatio', 'Fuel', 'filmCooling', 'thrust'} <= set(fields)
    assert not {'plotsEnabled', 'export', 'filename'} & set(fields)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The run queue -- #
#--------------------------------------------------------------------------------------------------------------------------#
def testRunsQueueAndStartInTurn():
    '''
    A run asked for during another queues; each starts once the one before has told its end, so its
    events follow that run's result.
    '''
    session = _scripted(holdSec = 2.0)
    try:
        placed = [session.submit({'filename': f'engine{index}', 'chamberPressure': 6.0e6 + index}) for index in range(3)]
        assert [entry['position'] for entry in placed] == [0, 1, 2]
        assert placed[0]['runId'] is not None and placed[1]['runId'] is None
        assert [entry['label'] for entry in session.snapshot()['queue']] == ['engine1', 'engine2']
        _settled(session)
        assert [record.runName for record in session.runs.values()] == ['engine0', 'engine1', 'engine2']
        kinds = [(event['type'], event.get('state')) for event in session.events if event['type'] in ('status', 'result')]
        assert kinds == [('status', 'running'), ('status', 'done'), ('result', None)] * 3
        assert session.snapshot()['queue'] == []
    finally:
        session.shutdown()

def testCancelGoesOnToTheNextRunOrEmptiesTheQueue():
    session = _scripted(holdSec = 30.0)
    try:
        first = session.submit({'filename': 'first'})['runId']
        session.submit({'filename': 'second'})
        third = session.submit({'filename': 'third'})['queueId']
        assert session.cancel()
        _waitFor(lambda: session.state['runId'] != first and session.busy)
        assert [entry['queueId'] for entry in session.snapshot()['queue']] == [third]
        assert session.cancel(everything = True)
        _settled(session)
        assert session.state['state'] == 'cancelled' and session.runs == {}
        assert not session.cancel() and not session.cancel(everything = True)
    finally:
        session.shutdown()

def testARunTakenOutOfTheQueueNeverStarts():
    session = _scripted(holdSec = 2.0)
    try:
        session.submit({'filename': 'first'})
        dropped = session.submit({'filename': 'dropped'})['queueId']
        session.submit({'filename': 'last'})
        assert session.unqueue(dropped) and not session.unqueue(dropped)
        _settled(session)
        assert [record.runName for record in session.runs.values()] == ['first', 'last']
    finally:
        session.shutdown()

#--------------------------------------------------------------------------------------------------------------------------#
# -- Sweeps in the session -- #
#--------------------------------------------------------------------------------------------------------------------------#
def testASweepRunsItsPointsAndGoesOnPastAFailure(monkeypatch):
    '''
    Each point runs in turn and is marked with its run; a failed point keeps its reason and the
    sweep goes on. The sweep's runs stay past the session's limit, and its table and plot read
    their headline numbers, the failed point a gap.
    '''
    monkeypatch.setattr(sessionModule, 'keptRuns', 1)
    session = _scripted()
    try:
        for index in range(2):
            session.submit({'filename': f'loose{index}'})
        sweep = session.addSweep(_sweep(('chamberPressure', 'MPa', [6.0e6, failingPressure, 8.0e6])))
        _settled(session)
        points = sweep['points']
        assert [point['state'] for point in points] == ['done', 'failed', 'done']
        assert points[1]['error'] == 'the scripted run failed' and points[1]['runId'] is None
        kept = [record for record in session.runs.values() if record.sweep is not None]
        assert [record.sweep['index'] for record in kept] == [0, 2]
        assert [record.runName for record in session.runs.values() if record.sweep is None] == ['loose1']

        table = session.sweepList()['sweeps'][0]
        assert table['counts'] == {'queued': 0, 'running': 0, 'done': 2, 'failed': 1, 'cancelled': 0}
        assert table['numbers'] == [{'key': 'isp', 'label': 'Delivered Isp', 'unit': 's'}]
        assert [point['numbers'].get('isp', {}).get('value') for point in table['points']] == [300.0, None, 400.0]
        assert [point['texts'] for point in table['points']] == [['6 MPa'], ['7 MPa'], ['8 MPa']]

        figure = json.loads(session.sweepFigure(sweep['sweepId'], 'isp', 'dark'))
        assert len(figure['data']) == 1 and figure['data'][0]['x'] == [6.0, 7.0, 8.0]
        assert figure['data'][0]['y'] == [300.0, None, 400.0]
        assert figure['layout']['xaxis']['title']['text'] == 'Chamber pressure [MPa]'
        assert figure['layout']['yaxis']['title']['text'] == 'Delivered Isp [s]'
        assert session.sweepFigure(sweep['sweepId'], 'thrust', 'dark') is None
    finally:
        session.shutdown()

def testAGridDrawsOneLinePerValueOfItsSecondField():
    session = _scripted()
    try:
        sweep = session.addSweep(_sweep(('chamberPressure', 'MPa', [6.0e6, 8.0e6]), ('OFRatio', '', [5.0, 6.0, 7.0])))
        _settled(session)
        figure = json.loads(session.sweepFigure(sweep['sweepId'], 'isp', 'light'))
        assert [trace['name'] for trace in figure['data']] == ['5', '6', '7']
        assert len({trace['line']['color'] for trace in figure['data']}) == 3
        assert figure['layout']['showlegend'] and figure['layout']['legend']['title']['text'] == 'O/F ratio'
    finally:
        session.shutdown()

def testASweepOutlastsItsWindowAndQueuesItsUnrunPointsAgain(tmp_path):
    '''
    A sweep is saved in the run store as its points move. Points still to run when the window
    closes read cancelled in the next one, and resuming queues just those.
    '''
    store = RunStore(str(tmp_path))
    session = _scripted(store, holdSec = 30.0)
    try:
        sweep = session.addSweep(_sweep(('chamberPressure', 'MPa', [6.0e6, 8.0e6, 9.0e6])))
        _waitFor(lambda: sweep['points'][0]['state'] == 'running')
    finally:
        session.shutdown()

    later = _scripted(RunStore(str(tmp_path)))
    try:
        restored = later.sweeps[sweep['sweepId']]
        assert [point['state'] for point in restored['points']] == ['cancelled'] * 3
        assert [point['error'] for point in restored['points']] == \
            ['NOVA closed while it ran', 'NOVA closed before it ran', 'NOVA closed before it ran']
        assert later.resumeSweep(sweep['sweepId']) == 3
        _settled(later)
        assert [point['state'] for point in restored['points']] == ['done'] * 3
        assert later.resumeSweep(sweep['sweepId']) == 0
        runIds = [point['runId'] for point in restored['points']]
        assert all(os.path.isdir(store.folder(runId)) for runId in runIds)
    finally:
        later.shutdown()

    reopened = _scripted(RunStore(str(tmp_path)))
    try:
        assert [point['state'] for point in reopened.sweeps[sweep['sweepId']]['points']] == ['done'] * 3
        assert all(reopened.record(runId).sweep['sweepId'] == sweep['sweepId'] for runId in runIds)
        assert reopened.addSweep(_sweep(('OFRatio', '', [5.0, 6.0])))['sweepId'] == sweep['sweepId'] + 1
        _settled(reopened)
    finally:
        reopened.shutdown()

def testDeletingASweepKeepsItsNamedRunAndTheBaseline(tmp_path):
    store = RunStore(str(tmp_path))
    session = _scripted(store)
    try:
        sweep = session.addSweep(_sweep(('chamberPressure', 'MPa', [6.0e6, 8.0e6, 9.0e6])))
        _settled(session)
        named, baseline, plain = (point['runId'] for point in sweep['points'])
        session.describe(named, title = 'keep me')
        session.setBaseline(baseline)
        assert session.deleteSweep(sweep['sweepId']) == [plain]
        assert set(session.runs) == {named, baseline} and session.sweeps == {}
        assert session.record(named).sweep is None and session.record(baseline).sweep is None
        assert not os.path.isdir(store.folder(plain)) and store.sweeps() == []
        with pytest.raises(KeyError):
            session.deleteSweep(sweep['sweepId'])
    finally:
        session.shutdown()

def testARunWhoseSweepIsGoneIsARunOfItsOwn(tmp_path):
    '''A run tagged with a sweep the store no longer holds loads untagged, under the store's limits.'''
    store = RunStore(str(tmp_path))
    session = _scripted(store)
    try:
        sweep = session.addSweep(_sweep(('chamberPressure', 'MPa', [6.0e6, 8.0e6])))
        _settled(session)
    finally:
        session.shutdown()
    store.removeSweep(sweep['sweepId'])
    later = _scripted(RunStore(str(tmp_path)))
    try:
        assert later.sweeps == {} and len(later.runs) == 2
        assert all(record.sweep is None for record in later.runs.values())
    finally:
        later.shutdown()

def testDeletingASweepMidRunStopsItsRunAndItsQueue():
    session = _scripted(holdSec = 30.0)
    try:
        sweep = session.addSweep(_sweep(('chamberPressure', 'MPa', [6.0e6, 8.0e6, 9.0e6])))
        later = session.submit({'filename': 'after the sweep'})['queueId']
        _waitFor(lambda: session.busy)
        session.deleteSweep(sweep['sweepId'])
        assert [entry['queueId'] for entry in session.snapshot()['queue']] in ([later], [])
        _waitFor(lambda: session.state['runId'] is not None and session._runSweep is None and session.busy)
        session.cancel()
        _settled(session)
        assert session.runs == {}
    finally:
        session.shutdown()

#--------------------------------------------------------------------------------------------------------------------------#
# -- Routes -- #
#--------------------------------------------------------------------------------------------------------------------------#
@pytest.fixture
def client():
    session = _scripted(holdSec = 0.05)
    app = createApp(session = session, warm = False)
    with TestClient(app) as testClient:
        yield testClient
    session.shutdown()

def testTheSweepRoutes(client):
    session = client.app.state.session
    config = {**configSchema.defaultConfig(), 'filename': 'routeTrade'}
    body = {'config': config, 'mode': 'light', 'fields': [{'key': 'chamberPressure', 'unit': 'MPa', 'values': [6.0e6, 8.0e6]}]}
    assert client.post('/api/sweeps', json = {**body, 'fields': [{'key': 'nope', 'values': [1, 2]}]}).status_code == 400
    assert client.post('/api/sweeps', json = {**body, 'mode': 'sepia'}).status_code == 400
    added = client.post('/api/sweeps', json = body).json()
    assert added['name'] == 'Chamber pressure sweep' and len(added['points']) == 2
    _settled(session)

    listing = client.get('/api/sweeps').json()
    assert listing['maxPoints'] == sweeps.maxPoints and listing['sweeps'][0]['counts']['done'] == 2
    sweepId = added['sweepId']
    figure = client.get(f'/api/sweeps/{sweepId}/figure', params = {'number': 'isp', 'mode': 'light'})
    assert figure.status_code == 200 and figure.json()['data'][0]['y'] == [300.0, 400.0]
    assert client.get(f'/api/sweeps/{sweepId}/figure', params = {'number': 'thrust'}).status_code == 404
    assert client.get('/api/sweeps/999/figure', params = {'number': 'isp'}).status_code == 404
    assert client.post(f'/api/sweeps/{sweepId}/resume').json() == {'queued': 0}
    runIds = [point['runId'] for point in listing['sweeps'][0]['points']]
    assert sorted(client.delete(f'/api/sweeps/{sweepId}').json()['runs']) == sorted(runIds)
    assert client.delete(f'/api/sweeps/{sweepId}').status_code == 404
    assert client.get('/api/sweeps').json()['sweeps'] == []

def testTheQueueRoutes(client):
    session = client.app.state.session
    session.holdSec = 30.0
    config = {'filename': 'queued'}
    first = client.post('/api/runs', json = {'config': config}).json()
    second = client.post('/api/runs', json = {'config': config}).json()
    assert first['position'] == 0 and first['runId'] is not None
    assert second == {'queueId': second['queueId'], 'runId': None, 'position': 1}
    assert client.delete(f'/api/queue/{second["queueId"]}').json() == {'unqueued': second['queueId']}
    assert client.delete(f'/api/queue/{second["queueId"]}').status_code == 404
    client.post('/api/runs', json = {'config': config})
    assert client.post('/api/runs/cancel', content = b'not json').status_code == 400
    assert client.post('/api/runs/cancel', json = {'all': True}).json() == {'cancelled': True}
    _settled(session)
    assert client.post('/api/runs/cancel').json() == {'cancelled': False}
