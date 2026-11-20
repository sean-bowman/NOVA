
# -- NOVA Web Run Session -- #

'''

One window's runs: starting a worker process, relaying its messages to the browser, cancelling
it, queueing the runs that wait their turn, and keeping the finished runs the result pane can show
and compare, with the trade sweeps they belong to.

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

The session keeps finished runs, each with the config it ran and the headline of its result
table, so the browser can list them, show any of them, and name the fields that differ between two
of them or between one and the form. One kept run can be the baseline the others are compared
against; it stays however many runs follow it. A kept run can carry a name and a note, and can be
deleted. A kept run unpickles its Nozzle on first use, and only the `keptNozzles` runs drawn from
most recently keep theirs in memory.

With a run store (novaGui.runStore), as the GUI has, each run writes into a store folder of its
own, a finished run's record is saved beside its outputs, and the session starts with every run
the store holds, its baseline among them, so runs outlast the window. Run ids come from the store
and count up across launches. The store's limits decide which unnamed runs go as new ones finish;
a cancelled or failed run's folder goes as soon as the run ends. Without a store, runs write into
the staging folder below, the session keeps the last `keptRuns` of them, and a run that drops out
of the list takes its staging folder with it.

Runs go one at a time. A run asked for while another is going joins the queue and starts when the
runs before it end, whether they finish, fail or are cancelled; RocketCEA's machine-wide lock
serializes the CEA solves of concurrent runs anyway, so the queue costs no speed. Cancel stops the
run in progress and the queue goes on, or stops the run and empties the queue; a queued run can
also be taken out alone.

A trade sweep (novaGui.sweeps) queues one run per point. The session keeps each sweep with its
points' states and runs, in the run store when there is one, and a sweep's runs carry its id and
their point's index. They stay however many runs follow, as named runs do, until the sweep is
deleted; deleting a sweep takes its queued points and its runs, except the runs that were named or
are the baseline. A sweep whose window closed with points still to run lists them cancelled, and
can queue them again. The worker records each finished run's headline numbers
(novaGui.analysis.headline), so a sweep's table reads them without unpickling its runs.

The warnings a run raises (novaGui.runner.warningRelay) are collected as it goes, one entry per
distinct warning with the number of times it came, and kept with the run, so the browser can count
them in the run bar and list them for whichever run it shows.

When a run's contour stage ends, the worker sends the figure descriptions that stage settles (the
contour, the near-wall state, the three flow fields and the revolved wall). The session keeps them
as the running run's partial result, so the browser can draw them while cooling and the plume
still run. They are dropped when the run ends; a finished run draws from its Nozzle.

Without a store, runs write into a staging folder for the server process, `<temp>/NOVA/web<pid>/run<n>`.
Each run gets its own folder, so a cancelled run's partial files never mix with a finished one. The
staging folder is removed when the server exits; novaGui.runner.clearStaging collects one a crashed server
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
    {'type': 'runs', 'baseline': int | None}      the kept runs, a run's name or note, or the baseline
                                                    changed
    {'type': 'queue', 'queue': [{'queueId', 'label', 'runName', 'sweepId', 'point'}]}
                                                    the runs waiting their turn, in order
    {'type': 'sweeps'}                              a sweep was added or deleted, or a point's state moved
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
from . import runStore
from . import sweeps as sweepModel
from . import worker

keptRuns = 8         # finished runs a session without a store keeps, besides the baseline
keptNozzles = 3      # kept runs whose unpickled Nozzle stays in memory
titleLength = 80     # [characters] the longest name a run takes
noteLength = 4000    # [characters] the longest note a run takes

def stagingRoot() -> str:

    '''

    This server's staging folder, beside the Tkinter front end's session folders.

    '''

    return os.path.join(tempfile.gettempdir(), 'NOVA', f'web{os.getpid()}')

class RunRecord:

    '''

    A finished run: its summary from the worker, the config it ran, its name and note, its
    headline numbers, and the Nozzle once something asks for it. `folder` is its run store folder,
    or None for a run the store does not hold. `sweep` is {'sweepId', 'index'} for a sweep's run.

    '''

    def __init__(self, runId: int, summary: dict, config: dict = None, warnings: list = None,
                 folder: str | None = None, sweep: dict | None = None):

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
        self.finishedAt = float(summary.get('finishedAt') or time.time())     # [s] epoch
        self.title = str(summary.get('title') or '')        # the name given to the run, '' for none
        self.note = str(summary.get('note') or '')
        self.bytes = int(summary.get('bytes') or 0)         # [B] its files, in the store
        # The result pane's headline numbers, as text in display units: {'key', 'label', 'value', 'unit', 'tone'}
        numbers = summary.get('numbers')
        self.numbers = [dict(entry) for entry in numbers if isinstance(entry, dict)] if isinstance(numbers, list) else []
        sweep = sweep if sweep is not None else summary.get('sweep')
        self.sweep = ({'sweepId': int(sweep['sweepId']), 'index': int(sweep['index'])}
                      if isinstance(sweep, dict) and 'sweepId' in sweep and 'index' in sweep else None)
        self.folder = folder
        self.loadError = ''                                 # why its pickle did not load
        self._nozzle = None
        self._lock = threading.Lock()

    @classmethod
    def fromStored(cls, content: dict) -> 'RunRecord':

        '''A run as the store saved it (novaGui.runStore.RunStore.records).'''

        config = content.get('config')
        warnings = content.get('warnings')
        return cls(int(content['runId']), {**content, 'ok': True},
                   config = config if isinstance(config, dict) else None,
                   warnings = [entry for entry in warnings if isinstance(entry, dict)] if isinstance(warnings, list) else None,
                   folder = content.get('folder'))

    def stored(self) -> dict:

        '''The run as the store saves it.'''

        return {'runName': self.runName, 'title': self.title, 'note': self.note, 'elapsedSec': self.elapsedSec,
                'headline': self.headline, 'numbers': self.numbers, 'sweep': self.sweep, 'finishedAt': self.finishedAt,
                'config': self.config, 'warnings': self.warnings, 'outputDir': self.outputDir,
                'picklePath': self.picklePath}

    def nozzle(self):

        '''

        The run's Nozzle, unpickled on first use, from a pickle this server's worker wrote or the
        run store keeps. Returns None for a failed run, a missing pickle, or one that does not
        load, such as a run saved by a NOVA whose classes have since changed; `loadError` then says
        why.

        '''

        if not self.ok or not self.picklePath:
            return None
        with self._lock:
            if self._nozzle is None and os.path.isfile(self.picklePath):
                try:
                    with open(self.picklePath, 'rb') as handle:
                        self._nozzle = pickle.load(handle)
                    self.loadError = ''
                except Exception as exc:                   # noqa: BLE001 -- any unpickling failure
                    self.loadError = f'its saved result does not load in this NOVA ({type(exc).__name__}: {exc})'
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

        return {'runId': self.runId, 'runName': self.runName, 'title': self.title, 'note': self.note,
                'elapsedSec': self.elapsedSec, 'headline': self.headline, 'numbers': self.numbers,
                'sweep': self.sweep, 'finishedAt': self.finishedAt, 'config': self.config,
                'warnings': self.warnings, 'bytes': self.bytes, 'saved': self.folder is not None}

class QueuedRun:

    '''

    A run waiting its turn: the config it will run, the palette mode of its figures, the label the
    queue shows, and for a sweep's point (sweepId, point index).

    '''

    def __init__(self, queueId: int, config: dict, mode: str, label: str, sweep: tuple | None = None):

        self.queueId = queueId
        self.config = dict(config)
        self.mode = mode
        self.label = label
        self.sweep = sweep

    def entry(self) -> dict:

        return {'queueId': self.queueId, 'label': self.label, 'runName': str(self.config.get('filename') or ''),
                'sweepId': self.sweep[0] if self.sweep else None, 'point': self.sweep[1] if self.sweep else None}

class RunSession:

    '''

    Starts, relays and cancels runs, one at a time from a queue, and keeps the finished runs and
    the trade sweeps.

    '''

    # -- Constructor -- #
    def __init__(self, logLines: int = 4000, store: runStore.RunStore | None = None):

        self._lock = threading.Lock()
        self._storeLock = threading.Lock()     # one writer of sweep files at a time; taken before _lock
        self._context = multiprocessing.get_context('spawn')
        self._process = None
        self._queue = None
        self._pump = None
        self._cancelled = False
        self._closing = False
        self._runCount = 0
        self._queueCount = 0
        self._sweepCount = 0

        self.state = {'state': 'idle', 'detail': '', 'fraction': 0.0, 'ceiling': 0.0, 'label': '',
                      'stageDetail': '', 'stages': [], 'runId': None, 'startedAt': None, 't': 0.0,
                      'expectedRun': None, 'warnings': []}
        self._progress = RunProgress()        # the current run's stages, folded from its events
        self._stageHistory = {}               # [s] top-level stage times of the last finished run
        self._lastStages = []                 # the last finished run's stage tree
        self._lastRunId = None                # the run both of those come from
        self._runConfig = None                # the config of the run in progress
        self._runSweep = None                 # (sweepId, point index) of the run in progress, for a sweep's
        self.queue = collections.deque()       # QueuedRun, in the order they start
        self.sweeps = collections.OrderedDict()   # sweepId: sweep (novaGui.sweeps.build), oldest first
        self.log = collections.deque(maxlen = logLines)
        self.result = None                     # the last good RunRecord, else the last that ended
        self.runs = collections.OrderedDict()  # runId: RunRecord, the kept finished runs, oldest first
        self.baseline = None                   # the kept run the others are compared against
        self.partial = None                    # {'runId', 'figures'}: the running run's settled figures
        self._drawn = []                       # kept runs by last use, whose Nozzles stay loaded

        self._subscribers = set()              # (loop, asyncio.Queue) pairs
        self._subscriberLock = threading.Lock()

        # The runs the store kept from earlier launches, after the folders of runs that never finished
        self.store = store
        if store is not None:
            store.collect()
            for content in store.records():
                record = RunRecord.fromStored(content)
                self.runs[record.runId] = record
            self.result = next(reversed(self.runs.values()), None)
            self.baseline = store.baseline if store.baseline in self.runs else None
            for sweep in store.sweeps():
                self._restoreSweep(sweep)
            # A run whose sweep the store no longer holds is a run of its own, under the store's limits
            for record in self.runs.values():
                if record.sweep is not None and record.sweep['sweepId'] not in self.sweeps:
                    record.sweep = None

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

    def _restoreSweep(self, sweep: dict) -> None:

        '''

        Keep a sweep the store saved. Its points still queued or running when the last window
        closed did not run; they read cancelled, and can be queued again.

        '''

        stopped = False
        for point in sweep['points']:
            if point.get('state') in ('queued', 'running'):
                reason = 'NOVA closed while it ran' if point['state'] == 'running' else 'NOVA closed before it ran'
                point.update(state = 'cancelled', runId = None, error = reason)
                stopped = True
        self.sweeps[sweep['sweepId']] = sweep
        if stopped:
            self.store.saveSweep(sweep)

    def _queueEvent(self) -> None:

        with self._lock:
            entries = [item.entry() for item in self.queue]
        self._publish({'type': 'queue', 'queue': entries})

    def _settle(self, changes: list) -> None:

        '''

        Move sweep points to new states, save their sweeps and tell the browser.

        Parameters:
        -----------
        changes : list
            ((sweepId, index), state, runId, error) for each point; a point of a sweep since deleted
            is passed over.

        '''

        touched = {}
        with self._lock:
            for (sweepId, index), state, runId, error in changes:
                sweep = self.sweeps.get(sweepId)
                if sweep is None or not 0 <= index < len(sweep['points']):
                    continue
                sweep['points'][index].update(state = state, runId = runId, error = error)
                touched[sweepId] = sweep
        if not touched:
            return
        self._saveSweeps(list(touched.values()))
        self._publish({'type': 'sweeps'})

    def _spawn(self, config: dict, outputDir: str, mode: str, runId: int) -> tuple:

        '''A worker process for one run and the queue it reports on, not yet started.'''

        eventQueue = self._context.Queue()
        process = self._context.Process(target = worker.runPipeline, name = f'novaRun{runId}',
                                        args = (dict(config), outputDir, mode, eventQueue), daemon = True)
        return process, eventQueue

    def _startLocked(self, config: dict, mode: str, sweep: tuple | None) -> int:

        '''Start a run in a new worker process; the caller holds the lock and has checked none is running.'''

        if self.store is not None:
            runId, outputDir = self.store.claim()
        else:
            self._runCount += 1
            runId = self._runCount
            outputDir = os.path.join(stagingRoot(), f'run{runId}')
            shutil.rmtree(outputDir, ignore_errors = True)
            os.makedirs(outputDir, exist_ok = True)

        self._cancelled = False
        self._process, self._queue = self._spawn(config, outputDir, mode, runId)
        self.log.clear()
        self.partial = None
        self._runConfig = dict(config)
        self._runSweep = sweep
        self.state.update(runId = runId, startedAt = time.time(), warnings = [])
        self._publish({'type': 'status', 'state': 'running', 'detail': 'starting worker'})
        self._progress = RunProgress(self._stageHistory, label = 'starting worker', previous = self._lastStages)
        self._publishProgress()
        self._process.start()

        self._pump = threading.Thread(target = self._drain, args = (self._process, self._queue, runId),
                                      name = f'novaPump{runId}', daemon = True)
        self._pump.start()
        return runId

    def _advance(self) -> tuple | None:

        '''

        Start the next queued run when none is running.

        Returns:
        --------
        tuple or None : (queueId, runId) of the run started

        '''

        with self._lock:
            if self._process is not None or not self.queue or self._closing:
                return None
            item = self.queue.popleft()
            runId = self._startLocked(item.config, item.mode, item.sweep)
            # Marked under the lock, so a run that ends at once cannot be marked done first
            sweep = self.sweeps.get(item.sweep[0]) if item.sweep is not None else None
            if sweep is not None:
                sweep['points'][item.sweep[1]].update(state = 'running', runId = runId, error = '')
        self._queueEvent()
        if sweep is not None:
            self._saveSweeps([sweep])
            self._publish({'type': 'sweeps'})
        return item.queueId, runId

    def _saveSweeps(self, sweeps: list) -> None:

        '''

        Write sweeps to the store, one writer at a time, each as it stands. A sweep since deleted is
        passed over, and nothing is written once the session has shut down. A write that fails is
        logged, so the run's pump thread carries on.

        '''

        if self.store is None:
            return
        with self._storeLock:
            for sweep in sweeps:
                with self._lock:
                    if self._closing or self.sweeps.get(sweep['sweepId']) is not sweep:
                        continue
                    content = {**sweep, 'points': [dict(point) for point in sweep['points']]}
                try:
                    self.store.saveSweep(content)
                except OSError as exc:
                    self._publish({'type': 'log', 'line': f'sweep {sweep["sweepId"]} could not be saved: {exc}'})

    def _queuePoints(self, sweep: dict, indices: list) -> None:

        '''Queue a sweep's points, in order, and start the first if nothing is running.'''

        with self._lock:
            for index in indices:
                point = sweep['points'][index]
                point.update(state = 'queued', runId = None, error = '')
                self._queueCount += 1
                self.queue.append(QueuedRun(self._queueCount, sweepModel.pointConfig(sweep, point),
                                            sweep.get('mode', 'dark'), sweepModel.pointLabel(sweep, point),
                                            (sweep['sweepId'], index)))
        self._saveSweeps([sweep])
        self._publish({'type': 'sweeps'})
        if self._advance() is None:
            self._queueEvent()

    def _removeFiles(self, record: RunRecord) -> None:

        '''Delete a run's folder: its store folder, or without a store its staging folder.'''

        if record.folder is not None and self.store is not None:
            self.store.remove(record.runId)
        elif self.store is None:
            shutil.rmtree(os.path.join(stagingRoot(), f'run{record.runId}'), ignore_errors = True)

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

        folder = self.store.folder(runId) if self.store is not None else None
        sweep = self._runSweep
        record = RunRecord(runId, summary, self._runConfig, self.state['warnings'], folder = folder,
                           sweep = {'sweepId': sweep[0], 'index': sweep[1]} if sweep is not None else None)
        if not record.ok and folder is not None:
            self.store.remove(runId)
            record.folder = None
        if record.ok:
            self._stageHistory = self._progress.durations()
            self._lastStages = self._progress.stageList()
            self._lastRunId = runId
        self.partial = None
        with self._lock:
            # A cancelled or failed run leaves the last good result in place for the views
            if record.ok or self.result is None or not self.result.ok:
                self.result = record
        if record.ok:
            self.adopt(record)
        if sweep is not None:
            pointState = 'done' if record.ok else ('cancelled' if state == 'cancelled' else 'failed')
            self._settle([(sweep, pointState, runId if record.ok else None, '' if record.ok else record.error)])

        detail = f'{record.elapsedSec:.1f} s' if record.ok else record.error
        self._publish({'type': 'status', 'state': state, 'detail': detail})
        self._publish({'type': 'result', **record.summary()})

        # The run counts as going until its end is told, so the next run's events follow its own
        with self._lock:
            self._process = None
            self._queue = None
            self._runSweep = None
        self._advance()

    # -- Public Methods -- #
    @property
    def busy(self) -> bool:

        return self._process is not None

    @property
    def idle(self) -> bool:

        '''No run going and none queued, read together, so a run passing from the queue to its process never reads as neither.'''

        with self._lock:
            return self._process is None and not self.queue

    def start(self, config: dict, mode: str = 'dark') -> int:

        '''

        Start a run in a new worker process now, ahead of the queue.

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
            return self._startLocked(config, mode, None)

    def submit(self, config: dict, mode: str = 'dark', label: str = '') -> dict:

        '''

        Queue a run: it starts now when nothing is running, else when the runs before it end.

        Parameters:
        -----------
        config : dict
            The complete config, in backend values.
        mode : str
            'dark' or 'light', for the figures the run saves.
        label : str
            What the queue calls it; by default its config's filename.

        Returns:
        --------
        dict : {'queueId': int, 'runId': int | None, 'position': int}. A run that started has its
            id and position 0; a queued one has no id yet, and its place in the queue from 1.

        '''

        with self._lock:
            self._queueCount += 1
            item = QueuedRun(self._queueCount, config, mode, label or str(config.get('filename') or 'the form'))
            self.queue.append(item)
        started = self._advance()
        if started is not None and started[0] == item.queueId:
            return {'queueId': item.queueId, 'runId': started[1], 'position': 0}
        self._queueEvent()
        with self._lock:
            position = next((place for place, queued in enumerate(self.queue, 1) if queued is item), 0)
        return {'queueId': item.queueId, 'runId': None, 'position': position}

    def unqueue(self, queueId: int) -> bool:

        '''

        Take a run out of the queue before it starts; a sweep's point reads cancelled. Returns False
        when the run is not queued.

        '''

        with self._lock:
            item = next((queued for queued in self.queue if queued.queueId == queueId), None)
            if item is None:
                return False
            self.queue.remove(item)
        self._queueEvent()
        if item.sweep is not None:
            self._settle([(item.sweep, 'cancelled', None, 'taken out of the queue')])
        return True

    def cancel(self, everything: bool = False) -> bool:

        '''

        Terminate the running worker; the queue then starts its next run. With `everything`, the
        queue empties first, its sweep points reading cancelled. Returns False when there was
        nothing to stop.

        '''

        dropped = []
        with self._lock:
            if everything:
                dropped = list(self.queue)
                self.queue.clear()
            process = self._process
            if process is not None:
                self._cancelled = True

        if dropped:
            self._queueEvent()
            self._settle([(item.sweep, 'cancelled', None, 'cancelled before it ran') for item in dropped
                          if item.sweep is not None])
        if process is None:
            return bool(dropped)
        self._publish({'type': 'log', 'line': 'run cancelled'})
        process.terminate()
        return True

    # -- Sweeps -- #
    def addSweep(self, sweep: dict, mode: str = 'dark') -> dict:

        '''

        Keep a sweep that novaGui.sweeps.build laid out, and queue its points in order.

        Returns:
        --------
        dict : the sweep, with its id

        '''

        with self._lock:
            if self.store is not None:
                sweepId = self.store.claimSweep()
            else:
                self._sweepCount += 1
                sweepId = self._sweepCount
            sweep = {**sweep, 'sweepId': sweepId, 'mode': mode}
            self.sweeps[sweepId] = sweep
        self._queuePoints(sweep, [point['index'] for point in sweep['points']])
        return sweep

    def resumeSweep(self, sweepId: int) -> int:

        '''

        Queue a sweep's cancelled points again. Returns how many were queued.

        Raises:
        -------
        KeyError : if the sweep is not kept

        '''

        with self._lock:
            sweep = self.sweeps[sweepId]
            indices = [point['index'] for point in sweep['points'] if point['state'] == 'cancelled']
        if indices:
            self._queuePoints(sweep, indices)
        return len(indices)

    def deleteSweep(self, sweepId: int) -> list:

        '''

        Delete a sweep: its queued points leave the queue, its run in progress is cancelled, and its
        runs are deleted, except a named run or the baseline, which stays as a run of its own.

        Returns:
        --------
        list : the ids of the runs deleted

        Raises:
        -------
        KeyError : if the sweep is not kept

        '''

        with self._lock:
            self.sweeps.pop(sweepId)
            dropped = [item for item in self.queue if item.sweep is not None and item.sweep[0] == sweepId]
            for item in dropped:
                self.queue.remove(item)
            process = self._process if self._runSweep is not None and self._runSweep[0] == sweepId else None
            if process is not None:
                self._cancelled = True
            members = [record for record in self.runs.values()
                       if record.sweep is not None and record.sweep['sweepId'] == sweepId]
        if dropped:
            self._queueEvent()
        if process is not None:
            self._publish({'type': 'log', 'line': 'run cancelled: its sweep was deleted'})
            process.terminate()

        deleted = []
        for record in members:
            if record.title or record.runId == self.baseline:
                record.sweep = None
                if self.store is not None and record.folder is not None:
                    record.bytes = self.store.save(record.runId, record.stored())
                continue
            self.forget(record.runId)
            self._removeFiles(record)
            deleted.append(record.runId)
        if self.store is not None:
            with self._storeLock:
                self.store.removeSweep(sweepId)
        self._publish({'type': 'runs', 'baseline': self.baseline})
        self._publish({'type': 'sweeps'})
        return deleted

    def sweepList(self) -> dict:

        '''

        The kept sweeps, newest first, each with its points' states and their runs' headline
        numbers (novaGui.sweeps.table), and the limits on a new sweep.

        '''

        with self._lock:
            kept = [{**sweep, 'points': [dict(point) for point in sweep['points']]}
                    for sweep in reversed(self.sweeps.values())]
            records = dict(self.runs)
        return {'sweeps': [sweepModel.table(sweep, records) for sweep in kept],
                'maxPoints': sweepModel.maxPoints, 'maxSeries': sweepModel.maxSeries}

    def sweepFigure(self, sweepId: int, numberKey: str, mode: str) -> str | None:

        '''

        One headline number of a sweep against its first field (novaGui.sweeps.figure).

        Raises:
        -------
        KeyError : if the sweep is not kept

        '''

        with self._lock:
            sweep = self.sweeps[sweepId]
            sweep = {**sweep, 'points': [dict(point) for point in sweep['points']]}
            records = dict(self.runs)
        return sweepModel.figure(sweep, records, numberKey, mode)

    def adopt(self, record: RunRecord) -> None:

        '''

        Keep a finished run in the list, as the latest, and save it to the store when it is one of
        the store's. Runs then drop out, except the baseline: with a store, the unnamed runs past
        its limits (novaGui.runStore.pruned), oldest first; without one, the oldest past `keptRuns`.
        A run that drops out takes its folder with it. A sweep's runs stay, as named runs do, until
        the sweep is deleted.

        '''

        if self.store is not None and record.folder is not None:
            record.bytes = self.store.save(record.runId, record.stored())
        dropped = []
        with self._lock:
            self.runs.pop(record.runId, None)
            self.runs[record.runId] = record
            if self.result is None or not self.result.ok or self.result.runId <= record.runId:
                self.result = record
            if self.store is not None:
                kept = [(runId, bool(entry.title) or entry.sweep is not None, entry.bytes)
                        for runId, entry in self.runs.items()]
                for runId in runStore.pruned(kept, self.baseline, record.runId):
                    dropped.append(self.runs.pop(runId))
            else:
                loose = [runId for runId, entry in self.runs.items() if runId != self.baseline and entry.sweep is None]
                dropped += [self.runs.pop(runId) for runId in loose[:max(0, len(loose) - keptRuns)]]
            self._drawn = [kept for kept in self._drawn if kept not in dropped]
        for old in dropped:
            self._removeFiles(old)
        self._publish({'type': 'runs', 'baseline': self.baseline})

    def describe(self, runId: int, title: str | None = None, note: str | None = None) -> RunRecord:

        '''

        Give a kept run a name, a note, or both; None leaves one as it is and '' clears it. A
        named run stays in the store however many runs follow it.

        Raises:
        -------
        KeyError : if the run is not kept
        ValueError : if the name or the note is too long

        '''

        title = None if title is None else ' '.join(str(title).split())
        note = None if note is None else str(note).strip()
        if title is not None and len(title) > titleLength:
            raise ValueError(f'a run name takes at most {titleLength} characters')
        if note is not None and len(note) > noteLength:
            raise ValueError(f'a run note takes at most {noteLength} characters')
        with self._lock:
            record = self.runs.get(runId)
            if record is None:
                raise KeyError(runId)
            if title is not None:
                record.title = title
            if note is not None:
                record.note = note
        if self.store is not None and record.folder is not None:
            record.bytes = self.store.save(record.runId, record.stored())
        self._publish({'type': 'runs', 'baseline': self.baseline})
        return record

    def delete(self, runId: int) -> RunRecord:

        '''

        Delete a kept run and its files. Deleting the baseline clears it.

        Raises:
        -------
        KeyError : if the run is not kept

        '''

        with self._lock:
            record = self.runs.get(runId)
        if record is None:
            raise KeyError(runId)
        if self.baseline == runId:
            self.setBaseline(None)
        self.forget(runId)
        self._removeFiles(record)
        self._publish({'type': 'runs', 'baseline': self.baseline})
        return record

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
        if self.store is not None:
            self.store.setBaseline(runId)
        self._publish({'type': 'runs', 'baseline': runId})

    def runList(self) -> dict:

        '''

        The kept runs, newest first, with the baseline and the run in progress.

        Returns:
        --------
        dict : {'runs': [RunRecord.entry], 'baseline': int | None, 'latest': int | None,
            'running': {'runId', 'config', 'views', 'warnings'} | None,
            'store': {'folder', 'unnamedRuns', 'bytes', 'byteLimit'} | None}

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
        store = None
        if self.store is not None:
            store = {'folder': self.store.root, 'unnamedRuns': runStore.unnamedRuns,
                     'bytes': sum(entry['bytes'] for entry in runs), 'byteLimit': runStore.storeBytes}
        return {'runs': runs, 'baseline': baseline, 'latest': latest, 'running': running, 'store': store}

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
        with self._lock:
            queued = [item.entry() for item in self.queue]
        return {'type': 'snapshot', **self.state, 'log': list(self.log), 'queue': queued,
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

        Empty the queue, stop any run with its store folder, and remove this server's staging
        folder. A sweep's points still to run read cancelled when the store next opens. A sweep
        save in progress finishes first, and none starts after, so the store is left as it stands.

        '''

        with self._lock:
            self._closing = True
            self.queue.clear()
        with self._storeLock:
            pass
        process = self._process
        if process is not None and process.is_alive():
            self._cancelled = True
            process.terminate()
            process.join(timeout = 5.0)
            if self.store is not None and self.state['runId'] is not None:
                self.store.remove(self.state['runId'])
        shutil.rmtree(stagingRoot(), ignore_errors = True)
