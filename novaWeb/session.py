
# -- NOVA Web Run Session -- #

'''

One window's runs: starting a worker process, relaying its messages to the browser, cancelling
it, and holding the last finished result.

A run is a child process (novaWeb.worker). A pump thread drains its queue and turns each message
into an event dictionary; every event is kept in the session's state (status, progress, recent
log lines) and handed to each subscriber, which is an asyncio queue behind one Server-Sent Events
stream. A browser that connects mid-run first receives a snapshot of the state, then the live
events.

Runs write into a staging folder for the server process, `<temp>/NOVA/web<pid>/run<n>`. Each run
gets its own folder, so a cancelled run's partial files never mix with a finished one. The staging
folder is removed when the server exits; novaGui.runner.clearStaging collects one a crashed server
left behind after twelve hours, together with the Tkinter front end's.

Events, as JSON objects:

    {'type': 'log', 'line': str}
    {'type': 'status', 'state': 'idle'|'running'|'done'|'error'|'cancelled', 'detail': str}
    {'type': 'progress', 'fraction': float, 'ceiling': float, 'label': str}
    {'type': 'result', 'runId': int, 'ok': bool, 'runName': str, 'elapsedSec': float, 'error': str}
    {'type': 'snapshot', ...}       sent once on connect: the whole state

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
from . import worker

def stagingRoot() -> str:

    '''

    This server's staging folder, beside the Tkinter front end's session folders.

    '''

    return os.path.join(tempfile.gettempdir(), 'NOVA', f'web{os.getpid()}')

class RunRecord:

    '''

    A finished run: its summary from the worker, and the Nozzle once something asks for it.

    '''

    def __init__(self, runId: int, summary: dict):

        self.runId = runId
        self.ok = bool(summary.get('ok'))
        self.runName = summary.get('runName', '')
        self.outputDir = summary.get('outputDir', '')
        self.picklePath = summary.get('picklePath', '')
        self.elapsedSec = float(summary.get('elapsedSec', 0.0))
        self.error = summary.get('error', '')
        self.traceback = summary.get('traceback', '')
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

    def summary(self) -> dict:

        return {'runId': self.runId, 'ok': self.ok, 'runName': self.runName,
                'elapsedSec': self.elapsedSec, 'error': self.error}

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
                      'runId': None, 'startedAt': None}
        self.log = collections.deque(maxlen = logLines)
        self.result = None                     # the last RunRecord, finished or failed

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
        elif kind == 'progress':
            self.state.update(fraction = event['fraction'], ceiling = event['ceiling'], label = event['label'])

        with self._subscriberLock:
            subscribers = list(self._subscribers)
        for loop, target in subscribers:
            try:
                loop.call_soon_threadsafe(target.put_nowait, event)
            except RuntimeError:                           # the subscriber's loop has closed
                self.unsubscribe(target)

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
            elif kind == 'progress':
                fraction, ceiling, label = payload
                self._publish({'type': 'progress', 'fraction': float(fraction), 'ceiling': float(ceiling),
                               'label': str(label)})
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

        record = RunRecord(runId, summary)
        with self._lock:
            # A cancelled or failed run leaves the last good result in place for the views
            if record.ok or self.result is None or not self.result.ok:
                self.result = record
            self._process = None
            self._queue = None

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
            self.state.update(runId = runId, startedAt = time.time())
            self._publish({'type': 'status', 'state': 'running', 'detail': 'starting worker'})
            self._publish({'type': 'progress', 'fraction': 0.0, 'ceiling': 0.02, 'label': 'starting worker'})
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

    def snapshot(self) -> dict:

        '''

        The whole state, for a browser that has just connected.

        '''

        return {'type': 'snapshot', **self.state, 'log': list(self.log),
                'result': self.result.summary() if self.result is not None else None}

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
