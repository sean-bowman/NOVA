
# -- NOVA Web Run Session -- #

'''

One window's runs: starting a worker process, relaying its messages to the browser, cancelling
it, and keeping the finished runs the result pane can show and compare.

A run is a child process (novaGui.worker). A pump thread drains its queue and turns each message
into an event dictionary; every event is kept in the session's state (status, progress, recent
log lines) and handed to each subscriber, which is an asyncio queue behind one Server-Sent Events
stream. A browser that connects mid-run first receives a snapshot of the state, then the live
events.

The worker forwards NOVA's progress events (NOVA.progress). The session folds them with
novaGui.progress.RunProgress, the model the legacy Tkinter window uses too, and sends the browser the
result: the bar's fraction and ceiling, a short label, the open stages as one detail line, and
the stage tree with its states, times and iterations. The last finished run's stage times share
out the next run's bar and stand as its expected times, and its tree lists the sub-stages the
next run has yet to reach.

The session keeps the last `keptRuns` finished runs, each with the config it ran and the headline
of its result table, so the browser can list them, show any of them, and name the fields that differ
between two of them or between one and the form. One kept run can be the baseline the others are
compared against; it stays however many runs follow it. A run that drops out of the list takes its
staging folder with it. A kept run unpickles its Nozzle on first use, and only the `keptNozzles`
runs drawn from most recently keep theirs in memory.

The warnings a run raises (novaGui.runner.warningRelay) are collected as it goes, one entry per
distinct warning with the number of times it came, and kept with the run, so the browser can count
them in the run bar and list them for whichever run it shows.

When a run's contour stage ends, the worker sends the figure descriptions that stage settles (the
contour, the near-wall state, the three flow fields and the revolved wall). The session keeps them
as the running run's partial result, so the browser can draw them while cooling and the plume
still run. They are dropped when the run ends; a finished run draws from its Nozzle.

Runs write into a staging folder for the server process, `<temp>/NOVA/web<pid>/run<n>`. Each run
gets its own folder, so a cancelled run's partial files never mix with a finished one. The staging
folder is removed when the server exits; novaGui.runner.clearStaging collects one a crashed server
left behind after twelve hours, together with the legacy Tkinter front end's.

Events, as JSON objects:

    {'type': 'log', 'line': str}
    {'type': 'status', 'state': 'idle'|'running'|'done'|'error'|'cancelled', 'detail': str,
     'runId': int | None}
    {'type': 'progress', 'runId': int, 't': float, 'expectedRun': int | None, 'fraction': float,
     'ceiling': float, 'label': str, 'stageDetail': str, 'stages': [...]}
        `t` is the run's own clock [s] at its latest event; `stages` is RunProgress.stageList, whose
        expected times come from run `expectedRun`
    {'type': 'partial', 'runId': int, 'views': [view keys]}
    {'type': 'warning', 'runId': int, 'warnings': [{'category', 'message', 'where', 'count'}]}
        every warning of the run so far
    {'type': 'result', 'runId': int, 'ok': bool, 'runName': str, 'elapsedSec': float, 'error': str}
    {'type': 'runs', 'baseline': int | None}      the kept runs or the baseline changed
    {'type': 'settings', ...}                       saved preferences changed (novaGui.settings)
    {'type': 'snapshot', ...}                       sent once on connect: the whole state

Author: Sean Bowman
Date:   11/16/2026

'''

# Standard library imports
import asyncio
import atexit
import collections
import multiprocessing
import os
import pickle
import queue
import shutil
import tempfile
import threading
import time

# Local imports
from .progress import RunProgress
from . import worker

keptRuns = 8         # finished runs the session keeps, besides the baseline
keptNozzles = 3      # kept runs whose unpickled Nozzle stays in memory

def stagingRoot() -> str:

    '''

    This server's staging folder, beside the Tkinter front end's session folders.

    '''

    return os.path.join(tempfile.gettempdir(), 'NOVA', f'web{os.getpid()}')

class RunRecord:

    '''

    A finished run: its summary from the worker, the config it ran, and the Nozzle once something
    asks for it.

    '''

    def __init__(self, runId: int, summary: dict, config: dict = None, warnings: list = None):

        self.runId = runId
        self.warnings = [dict(entry) for entry in warnings] if warnings else []
        self.config = dict(config) if config is not None else None
        self.ok = bool(summary.get('ok'))
        self.runName = summary.get('runName', '')
        self.outputDir = summary.get('outputDir', '')
        self.picklePath = summary.get('picklePath', '')
        self.elapsedSec = float(summary.get('elapsedSec', 0.0))
        self.headline = summary.get('headline', '')          # the result table's summary line
        self.error = summary.get('error', '')
        self.traceback = summary.get('traceback', '')
        self.finishedAt = time.time()                       # [s] epoch
        self._nozzle = None
        self._lock = threading.Lock()

    def nozzle(self):

        '''

        The run's Nozzle, unpickled on first use. The pickle is one this server's worker wrote
        into its own staging folder. Returns None for a failed run or a missing pickle.

        '''

        if not self.ok or not self.picklePath:
            return None
        with self._lock:
            if self._nozzle is None and os.path.isfile(self.picklePath):
                with open(self.picklePath, 'rb') as handle:
                    self._nozzle = pickle.load(handle)
        return self._nozzle

    def release(self) -> None:

        '''Drop the unpickled Nozzle; the next use reads the pickle again.'''

        if self.picklePath and os.path.isfile(self.picklePath):
            with self._lock:
                self._nozzle = None

    def summary(self) -> dict:

        return {'runId': self.runId, 'ok': self.ok, 'runName': self.runName,
                'elapsedSec': self.elapsedSec, 'error': self.error}

    def entry(self) -> dict:

        '''The run as the run list shows it.'''

        return {'runId': self.runId, 'runName': self.runName, 'elapsedSec': self.elapsedSec,
                'headline': self.headline, 'finishedAt': self.finishedAt, 'config': self.config,
                'warnings': self.warnings}

class RunSession:

    '''

    Starts, relays and cancels runs, one at a time.

    '''

    # -- Constructor -- #
    def __init__(self, logLines: int = 4000):

        self._lock = threading.Lock()
        self._context = multiprocessing.get_context('spawn')
        self._process = None
        self._queue = None
        self._pump = None
        self._cancelled = False
        self._runCount = 0

        self.state = {'state': 'idle', 'detail': '', 'fraction': 0.0, 'ceiling': 0.0, 'label': '',
                      'stageDetail': '', 'stages': [], 'runId': None, 'startedAt': None, 't': 0.0,
                      'expectedRun': None, 'warnings': []}
        self._progress = RunProgress()        # the current run's stages, folded from its events
        self._stageHistory = {}               # [s] top-level stage times of the last finished run
        self._lastStages = []                 # the last finished run's stage tree
        self._lastRunId = None                # the run both of those come from
        self._runConfig = None                # the config of the run in progress
        self.log = collections.deque(maxlen = logLines)
        self.result = None                     # the last good RunRecord, else the last that ended
        self.runs = collections.OrderedDict()  # runId: RunRecord, the kept finished runs, oldest first
        self.baseline = None                   # the kept run the others are compared against
        self.partial = None                    # {'runId', 'figures'}: the running run's settled figures
        self._drawn = []                       # kept runs by last use, whose Nozzles stay loaded

        self._subscribers = set()              # (loop, asyncio.Queue) pairs
        self._subscriberLock = threading.Lock()

        os.makedirs(stagingRoot(), exist_ok = True)
        atexit.register(self.shutdown)

    # -- Private Helper Methods -- #
    def _publish(self, event: dict) -> None:

        '''

        Fold an event into the state and hand it to every subscriber.

        '''

        kind = event['type']
        if kind == 'log':
            self.log.append(event['line'])
        elif kind == 'status':
            self.state['state'], self.state['detail'] = event['state'], event['detail']
            event['runId'] = self.state['runId']
        elif kind == 'progress':
            self.state.update(fraction = event['fraction'], ceiling = event['ceiling'], label = event['label'],
                              stageDetail = event['stageDetail'], stages = event['stages'], t = event['t'],
                              expectedRun = event['expectedRun'])

        with self._subscriberLock:
            subscribers = list(self._subscribers)
        for loop, target in subscribers:
            try:
                loop.call_soon_threadsafe(target.put_nowait, event)
            except RuntimeError:                           # the subscriber's loop has closed
                self.unsubscribe(target)

    def _publishProgress(self) -> None:

        fraction, ceiling, label = self._progress.summary()
        self._publish({'type': 'progress', 'runId': self.state['runId'], 't': float(self._progress.t),
                       'expectedRun': self._lastRunId, 'fraction': float(fraction),
                       'ceiling': float(ceiling), 'label': label, 'stageDetail': self._progress.detail,
                       'stages': self._progress.stageList()})

    def _addWarning(self, payload: dict, runId: int) -> None:

        '''Count a warning against the run, once per category and message, and send the run's list.'''

        warning = {'category': str(payload.get('category', 'Warning')), 'message': str(payload.get('message', '')),
                   'where': str(payload.get('where', ''))}
        found = self.state['warnings']
        same = next((entry for entry in found
                     if (entry['category'], entry['message']) == (warning['category'], warning['message'])), None)
        if same is not None:
            same['count'] += 1
        else:
            found = found + [{**warning, 'count': 1}]
            self.state['warnings'] = found
        self._publish({'type': 'warning', 'runId': runId, 'warnings': [dict(entry) for entry in found]})

    def _drain(self, process, eventQueue, runId: int) -> None:

        '''

        Pump thread: turn the worker's messages into events until it reports a result or dies.

        '''

        summary = None
        while summary is None:
            try:
                kind, payload = eventQueue.get(timeout = 0.25)
            except queue.Empty:
                if process.is_alive():
                    continue
                # The process ended without a result: cancelled, or it died outright
                try:
                    kind, payload = eventQueue.get(timeout = 0.5)
                except (queue.Empty, EOFError, OSError):
                    break
            except (EOFError, OSError):
                break

            if kind == 'log':
                self._publish({'type': 'log', 'line': str(payload)})
            elif kind == 'status':
                state, detail = payload
                # The runner reports 'done' before the worker pickles; the result event closes the run
                if state == 'running':
                    self._publish({'type': 'status', 'state': state, 'detail': str(detail)})
            elif kind == 'stage':
                if self._progress.apply(payload):
                    self._publishProgress()
            elif kind == 'warning':
                self._addWarning(payload, runId)
            elif kind == 'partial':
                figures = dict(payload.get('figures') or {})
                if figures:
                    self.partial = {'runId': runId, 'figures': figures}
                    self._publish({'type': 'partial', 'runId': runId, 'views': list(figures)})
            elif kind == 'result':
                summary = payload

        process.join(timeout = 5.0)

        if summary is None:
            cancelled = self._cancelled
            summary = {'ok': False, 'error': 'run cancelled' if cancelled else
                       f'run process ended with exit code {process.exitcode}'}
            state = 'cancelled' if cancelled else 'error'
        else:
            state = 'done' if summary.get('ok') else 'error'
            if summary.get('traceback'):
                self._publish({'type': 'log', 'line': summary['traceback']})

        record = RunRecord(runId, summary, self._runConfig, self.state['warnings'])
        if record.ok:
            self._stageHistory = self._progress.durations()
            self._lastStages = self._progress.stageList()
            self._lastRunId = runId
        self.partial = None
        with self._lock:
            # A cancelled or failed run leaves the last good result in place for the views
            if record.ok or self.result is None or not self.result.ok:
                self.result = record
            self._process = None
            self._queue = None
        if record.ok:
            self.adopt(record)

        detail = f'{record.elapsedSec:.1f} s' if record.ok else record.error
        self._publish({'type': 'status', 'state': state, 'detail': detail})
        self._publish({'type': 'result', **record.summary()})

    # -- Public Methods -- #
    @property
    def busy(self) -> bool:

        return self._process is not None

    def start(self, config: dict, mode: str = 'dark') -> int:

        '''

        Start a run in a new worker process.

        Parameters:
        -----------
        config : dict
            The complete config, in backend values.
        mode : str
            'dark' or 'light', for the figures the run saves.

        Returns:
        --------
        int : the run's id

        Raises:
        -------
        RuntimeError : if a run is already in progress

        '''

        with self._lock:
            if self._process is not None:
                raise RuntimeError('a run is already in progress')

            self._runCount += 1
            runId = self._runCount
            outputDir = os.path.join(stagingRoot(), f'run{runId}')
            shutil.rmtree(outputDir, ignore_errors = True)
            os.makedirs(outputDir, exist_ok = True)

            self._cancelled = False
            self._queue = self._context.Queue()
            self._process = self._context.Process(target = worker.runPipeline, name = f'novaRun{runId}',
                                                  args = (dict(config), outputDir, mode, self._queue),
                                                  daemon = True)
            self.log.clear()
            self.partial = None
            self._runConfig = dict(config)
            self.state.update(runId = runId, startedAt = time.time(), warnings = [])
            self._publish({'type': 'status', 'state': 'running', 'detail': 'starting worker'})
            self._progress = RunProgress(self._stageHistory, label = 'starting worker', previous = self._lastStages)
            self._publishProgress()
            self._process.start()

            self._pump = threading.Thread(target = self._drain, args = (self._process, self._queue, runId),
                                          name = f'novaPump{runId}', daemon = True)
            self._pump.start()

        return runId

    def cancel(self) -> bool:

        '''

        Terminate the running worker. Returns False when nothing is running.

        '''

        with self._lock:
            process = self._process
            if process is None:
                return False
            self._cancelled = True

        self._publish({'type': 'log', 'line': 'run cancelled'})
        process.terminate()
        return True

    def adopt(self, record: RunRecord) -> None:

        '''

        Keep a finished run in the list, as the latest. The oldest runs beyond `keptRuns` drop out,
        except the baseline, and their staging folders go with them.

        '''

        dropped = []
        with self._lock:
            self.runs.pop(record.runId, None)
            self.runs[record.runId] = record
            if self.result is None or not self.result.ok or self.result.runId <= record.runId:
                self.result = record
            while sum(1 for runId in self.runs if runId != self.baseline) > keptRuns:
                oldest = next(runId for runId in self.runs if runId != self.baseline)
                dropped.append(self.runs.pop(oldest))
            self._drawn = [kept for kept in self._drawn if kept not in dropped]
        for old in dropped:
            shutil.rmtree(os.path.join(stagingRoot(), f'run{old.runId}'), ignore_errors = True)
        self._publish({'type': 'runs', 'baseline': self.baseline})

    def forget(self, runId: int) -> None:

        '''Drop a run from the list without touching its files.'''

        with self._lock:
            record = self.runs.pop(runId, None)
            if self.baseline == runId:
                self.baseline = None
            if self.result is not None and self.result.runId == runId:
                self.result = next(reversed(self.runs.values()), None)
            self._drawn = [kept for kept in self._drawn if kept is not record]

    def record(self, runId: int | None = None) -> RunRecord | None:

        '''

        A kept run by its id, or with no id the latest good run; None when there is no such run.

        '''

        with self._lock:
            if runId is None:
                return self.result if self.result is not None and self.result.ok else None
            return self.runs.get(runId)

    def nozzle(self, record: RunRecord):

        '''

        A kept run's Nozzle. The runs drawn from most recently keep theirs loaded; older ones
        release theirs and read their pickle again when next asked.

        '''

        nozzle = record.nozzle()
        with self._lock:
            self._drawn = [kept for kept in self._drawn if kept is not record] + [record]
            released, self._drawn = self._drawn[:-keptNozzles], self._drawn[-keptNozzles:]
        for old in released:
            old.release()
        return nozzle

    def setBaseline(self, runId: int | None) -> None:

        '''

        Make a kept run the baseline, or clear it with None.

        Raises:
        -------
        KeyError : if the run is not kept

        '''

        with self._lock:
            if runId is not None and runId not in self.runs:
                raise KeyError(runId)
            self.baseline = runId
        self._publish({'type': 'runs', 'baseline': runId})

    def runList(self) -> dict:

        '''

        The kept runs, newest first, with the baseline and the run in progress.

        Returns:
        --------
        dict : {'runs': [RunRecord.entry], 'baseline': int | None, 'latest': int | None,
            'running': {'runId', 'config', 'views', 'warnings'} | None}

        '''

        with self._lock:
            runs = [record.entry() for record in reversed(self.runs.values())]
            latest = self.result.runId if self.result is not None and self.result.ok else None
            baseline = self.baseline
        running = None
        runId = self.state['runId']
        if self.busy and runId is not None:
            partial = self.partial
            views = list(partial['figures']) if partial and partial['runId'] == runId else []
            running = {'runId': runId, 'config': self._runConfig, 'views': views,
                       'warnings': [dict(entry) for entry in self.state['warnings']]}
        return {'runs': runs, 'baseline': baseline, 'latest': latest, 'running': running}

    def partialFigure(self, runId: int, key: str):

        '''The running run's settled figure description for a view, or None.'''

        partial = self.partial
        if partial is None or partial['runId'] != runId:
            return None
        return partial['figures'].get(key)

    def publish(self, event: dict) -> None:

        '''Hand an event to every subscriber: a change a route makes, such as saved preferences.'''

        self._publish(event)

    def snapshot(self) -> dict:

        '''

        The whole state, for a browser that has just connected.

        '''

        partial = self.partial
        return {'type': 'snapshot', **self.state, 'log': list(self.log),
                'result': self.result.summary() if self.result is not None else None,
                'partial': {'runId': partial['runId'], 'views': list(partial['figures'])} if partial else None,
                'baseline': self.baseline}

    def subscribe(self) -> asyncio.Queue:

        '''

        A queue that receives every event from now on. Call from the event loop that reads it.

        '''

        target = asyncio.Queue()
        with self._subscriberLock:
            self._subscribers.add((asyncio.get_running_loop(), target))
        return target

    def unsubscribe(self, target: asyncio.Queue) -> None:

        with self._subscriberLock:
            self._subscribers = {pair for pair in self._subscribers if pair[1] is not target}

    def shutdown(self) -> None:

        '''

        Stop any run and remove this server's staging folder.

        '''

        process = self._process
        if process is not None and process.is_alive():
            self._cancelled = True
            process.terminate()
            process.join(timeout = 5.0)
        shutil.rmtree(stagingRoot(), ignore_errors = True)
