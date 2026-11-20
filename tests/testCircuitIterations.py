# -- NOVA: Circuit Iteration View Tests -- #

'''

The circuit iteration view: each pass of a multi-pass coolant circuit's outer iteration, the hot
wall and the coolant of both legs along the wall, the latest solid and the earlier ones fading.
While a run goes on it draws from the passes the session keeps as the worker sends them; once the
run finishes, from the passes its circuit solutions keep.

A finished run is stood in for by an object carrying only what the view reads, and a running one
by a worker the test feeds message by message, so the session and the routes can be read between
two passes and no run is made. NOVA's side, the passes a circuit sends and keeps, is held in
tests/testCoolantCircuit.py.

Author: Sean Bowman

'''

import os
import queue
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from novaGui import thermalPlots, viewCatalog, views
from novaGui.server import createApp
from novaGui.session import RunSession, iterationView

#--------------------------------------------------------------------------------------------------------------------------#
# -- Passes -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _leg(leg: str, x, offset: float) -> dict:

    '''One leg along the wall: a wall and a coolant profile shifted by `offset` [K].'''

    x = np.asarray(x, dtype = float)
    return {'leg': leg, 'x': x, 'wall': 600.0 + offset + 100.0 * x, 'coolant': 100.0 + offset + 200.0 * x}

def _pass(index: int, change, x) -> dict:

    '''A pass of the outer iteration as a circuit solution keeps it.'''

    return {'index': index, 'change': change, 'legs': [_leg('down', x[1:], 10.0 / index), _leg('up', x, 20.0 / index)]}

def _sent(path: str, index: int, change = None) -> dict:

    '''A pass as NOVA.progress sends it: lists of floats, the change among the metrics.'''

    entry = _pass(index, change, [0.0, 0.1, 0.2, 0.3])
    return {'type': 'profiles', 't': float(index), 'path': path, 'name': 'pass', 'index': index,
            'metrics': {'change': change, 'tolerance': 0.05},
            'profiles': [{key: (value.tolist() if isinstance(value, np.ndarray) else value) for key, value in leg.items()}
                         for leg in entry['legs']]}

def _finished(jacketPasses: int = 3, extensionPasses: int = 2, kept: bool = True):

    '''

    What a finished run with a multi-pass jacket and a two-pass extension circuit carries for the
    view: the circuit solutions' passes, the wall limit and the wall the throat is found on.

    '''

    jacket = [_pass(index, None if index == 1 else 4.0 / index, [-0.2, 0.0, 0.2, 0.4]) for index in range(1, jacketPasses + 1)]
    extension = [_pass(index, None if index == 1 else 2.0 / index, [0.5, 0.6, 0.7]) for index in range(1, extensionPasses + 1)]
    chamber = SimpleNamespace(iterationProfiles = jacket) if kept else SimpleNamespace()
    return SimpleNamespace(coolantCircuitSolution = chamber,
                           extensionCircuitSolution = SimpleNamespace(circuit = SimpleNamespace(iterationProfiles = extension)),
                           maxWallTemperature = 800.0,
                           xNozzleWall = np.linspace(-0.3, 0.7, 11), rNozzleWall = 0.1 + np.abs(np.linspace(-0.3, 0.7, 11)))

#--------------------------------------------------------------------------------------------------------------------------#
# -- A finished run -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testAFinishedRunDescribesEachCircuitsPassesInDrawingOrder():

    nozzle = _finished()
    description = thermalPlots.iterationDescription(nozzle)

    assert [(loop['key'], loop['label'], len(loop['iterations'])) for loop in description['loops']] == [
        ('jacket', 'jacket', 3), ('extension', 'extension circuit', 2)]
    assert description['limit'] == 800.0 and description['throatX'] == pytest.approx(0.0)
    assert thermalPlots.iterationThroat(description) == pytest.approx(0.0)
    assert thermalPlots.iterationSummary(description) == (
        'jacket, 3 passes, last change 1.33 K; extension circuit, 2 passes, last change 1 K')
    assert 'circuitIterations' in viewCatalog.availableViews(nozzle, {})

def testARunWithNoCircuitPassesHasNoView():

    '''No multi-pass circuit, or one solved before its passes were kept, draws nothing here.'''

    alone = SimpleNamespace(coolantCircuitSolution = None, extensionCircuitSolution = None)
    assert thermalPlots.iterationDescription(alone) is None
    earlier = _finished(kept = False)
    earlier.extensionCircuitSolution = None
    assert thermalPlots.iterationDescription(earlier) is None
    assert 'circuitIterations' not in viewCatalog.availableViews(earlier, {})

def testTheThroatIsMarkedOnlyWhereACircuitRuns():

    description = thermalPlots.iterationDescription(_finished())
    description['loops'] = description['loops'][1:]
    assert thermalPlots.iterationThroat(description) is None

def testBothRenderersDrawEveryPassTheLatestSolid():

    '''

    Each pass draws each leg on both panels; only the latest of each leg is in the legend, at full
    opacity, and the earlier ones fade with age. The Matplotlib drawing saves as a PNG.

    '''

    import json

    nozzle = _finished()
    figure = json.loads(views.interactiveFigure(nozzle, 'circuitIterations', 'dark'))
    lines = [trace for trace in figure['data'] if trace.get('legendgroup')]
    assert len(lines) == (3 + 2) * 2 * 2
    legend = [trace['name'] for trace in figure['data'] if trace.get('showlegend')]
    assert legend == ['jacket down, pass 3', 'jacket up, pass 3', 'extension circuit down, pass 2',
                      'extension circuit up, pass 2', 'Wall limit 800 K']

    def alpha(trace):
        return float(trace['line']['color'].rstrip(')').split(',')[-1])

    upWall = [trace for trace in lines if trace['legendgroup'] == 'jacket-up' and trace['yaxis'] == 'y']
    assert [alpha(trace) for trace in upWall] == sorted(alpha(trace) for trace in upWall)
    assert alpha(upWall[-1]) == 1.0 and alpha(upWall[0]) < 0.5
    assert figure['layout']['uirevision'] == 'circuitIterations'

    drawn = views.staticFigure(nozzle, 'circuitIterations', 'light', 800, 600, 1.0)
    assert drawn['png'][:8] == b'\x89PNG\r\n\x1a\n'

#--------------------------------------------------------------------------------------------------------------------------#
# -- A running run -- #
#--------------------------------------------------------------------------------------------------------------------------#

class _FedProcess:

    '''A worker stand-in on a thread: forwards each message the test feeds it, until a result or a stop.'''

    def __init__(self, eventQueue):
        self.eventQueue = eventQueue
        self.feed = queue.Queue()
        self.exitcode = None
        self._thread = threading.Thread(target = self._run, daemon = True)

    def _run(self):
        while True:
            kind, payload = self.feed.get()
            if kind == 'stop':
                self.exitcode = -15
                return
            self.eventQueue.put((kind, payload))
            if kind == 'result':
                self.exitcode = 0
                return

    def start(self):
        self._thread.start()

    def is_alive(self):
        return self._thread.is_alive()

    def join(self, timeout = None):
        self._thread.join(timeout)

    def terminate(self):
        self.feed.put(('stop', None))

class _FedSession(RunSession):

    '''A session whose run the test feeds; `process` is the run's worker stand-in.'''

    def _spawn(self, config, outputDir, mode, runId):
        events = queue.Queue()
        self.process = _FedProcess(events)
        return self.process, events

def _waitFor(test, timeoutSec: float = 10.0) -> None:
    deadline = time.time() + timeoutSec
    while not test() and time.time() < deadline:
        time.sleep(0.02)
    assert test(), 'the session did not get there in time'

@pytest.fixture
def running():
    '''A session with a run going that has settled its contour, and every event the session published.'''
    session = _FedSession()
    session.events = []
    publish = session._publish
    session._publish = lambda event: session.events.append(dict(event)) or publish(event)
    runId = session.start({'filename': 'fed', 'maxWallTemperature': 780.0})
    session.process.feed.put(('partial', {'stage': 'contour', 'figures': {'contour': {'stand-in': True}}, 'throatX': 0.05}))
    _waitFor(lambda: session.partial is not None)
    try:
        yield session, runId
    finally:
        session.shutdown()

def _feed(session, runId: int, *events) -> None:
    before = session.partialRevision(runId)
    for event in events:
        session.process.feed.put(('stage', event))
    _waitFor(lambda: session.partialRevision(runId) == before + len(events))

def testARunningCircuitsPassesAreKeptAndAnnouncedOneByOne(running):

    '''

    The first pass adds the view to the running run's settled views, once; every pass is
    announced with the count kept so far; the jacket and the extension circuit are kept apart, by
    the stage they run in, in drawing order, with the run's wall limit and its throat.

    '''

    session, runId = running
    _feed(session, runId, _sent('cooling.circuit', 1), _sent('cooling.circuit', 2, 3.0), _sent('cooling.circuit', 3, 0.5),
          _sent('extension', 1), _sent('extension', 2, 0.02))

    partials = [event for event in session.events if event['type'] == 'partial' and iterationView in event['views']]
    assert len(partials) == 1 and partials[0]['views'] == ['contour', iterationView]
    assert [event['revision'] for event in session.events if event['type'] == 'iterations'] == [1, 2, 3, 4, 5]
    assert iterationView in session.runList()['running']['views']

    description = session.partialFigure(runId, iterationView)
    assert [(loop['key'], [entry['index'] for entry in loop['iterations']]) for loop in description['loops']] == [
        ('jacket', [1, 2, 3]), ('extension', [1, 2])]
    assert description['loops'][0]['iterations'][-1]['change'] == 0.5
    assert description['limit'] == 780.0 and description['throatX'] == 0.05
    assert thermalPlots.iterationSummary(description) == (
        'jacket, 3 passes, last change 0.5 K; extension circuit, 2 passes, last change 0.02 K')

def testACircuitSolvedAgainStartsItsPassesOver(running):

    '''A pass numbered 1 again, as under an outer gas-side iteration, starts that circuit over and leaves the other.'''

    session, runId = running
    _feed(session, runId, _sent('cooling.circuit', 1), _sent('cooling.circuit', 2, 3.0), _sent('extension', 1),
          _sent('cooling.ievlev.circuit', 1))

    description = session.partialFigure(runId, iterationView)
    assert [(loop['key'], len(loop['iterations'])) for loop in description['loops']] == [('jacket', 1), ('extension', 1)]

def testTheRoutesDrawEachPassAsItArrivesAndForgetThemWhenTheRunEnds(running):

    '''

    The view index offers the view while the run goes on, and the figure grows a pass at a time:
    each pass's figure is kept under its own name, so the one drawn before is never served again.
    When the run ends the passes go with its other partial figures.

    '''

    import json

    session, runId = running
    _feed(session, runId, _sent('cooling.circuit', 1), _sent('cooling.circuit', 2, 3.0))
    with TestClient(createApp(session = session, warm = False)) as client:
        index = client.get('/api/views', params = {'run': runId}).json()
        assert index['partial'] and iterationView in index['available']

        def lines():
            response = client.get(f'/api/views/{iterationView}/interactive', params = {'run': runId, 'mode': 'dark'})
            assert response.status_code == 200
            return len([trace for trace in json.loads(response.text)['data'] if trace.get('legendgroup')])

        assert lines() == 2 * 2 * 2
        _feed(session, runId, _sent('cooling.circuit', 3, 0.5))
        assert lines() == 3 * 2 * 2

        session.process.feed.put(('result', {'ok': False, 'error': 'the fed run ends here', 'elapsedSec': 1.0}))
        _waitFor(lambda: session.idle)
        assert session.partial is None and session.partialFigure(runId, iterationView) is None
        assert client.get(f'/api/views/{iterationView}/interactive', params = {'run': runId}).status_code == 404
