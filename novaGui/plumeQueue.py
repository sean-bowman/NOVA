
# -- NOVA GUI Plume Sweep Queue -- #

'''

The plume sweeps of a session's kept runs: keeping them, solving them one at a time in a worker
process, and telling the browser as each point ends.

A plume sweep (novaGui.plumeSweeps) belongs to the run whose nozzle it solves on, and is numbered
within that run. With a run store, each is saved in its run's folder (novaGui.runStore) as it
changes and read back when the session starts; a sweep whose window closed with points still to
solve lists them cancelled, and they can be queued again. Without a store, the sweeps live as long
as the session. A run that drops out of the session takes its plume sweeps with it, its sweep in
progress cancelled.

Sweeps solve one at a time, in the order they were asked for, each in a process of its own
(novaGui.plumeSweeps.runSweep) that loads the run's pickled Nozzle. The queue is the plume's own,
apart from the run queue: the plume makes no CEA call, so a plume sweep need not wait for a run.
Deleting a sweep in progress cancels it.

Events, through the session's stream:

    {'type': 'plumeSweeps', 'runId': int}       a run's plume sweep was added or deleted, or a
                                                point's state moved

Author: Sean Bowman
Date:   11/22/2026

'''

# Standard library imports
import collections
import multiprocessing
import queue
import threading

# Local imports
from . import plumeSweeps as plumeModel

class PlumeQueue:

    '''

    Keeps the plume sweeps of the kept runs and solves them one at a time.

    Parameters:
    -----------
    store : novaGui.runStore.RunStore or None
        Where each sweep is saved, in its run's folder; None keeps them in memory.
    publish : callable
        Hands an event to every browser (novaGui.session.RunSession.publish).
    onSettled : callable, optional
        Called with a run's id once one of its sweeps ends or is deleted, so the session can count
        the sweep's file in the run's size.

    '''

    # -- Constructor -- #
    def __init__(self, store, publish, onSettled = None):

        self.store = store
        self._publish = publish
        self._onSettled = onSettled
        self._lock = threading.Lock()
        self._context = multiprocessing.get_context('spawn')
        self._sweeps = {}                      # (runId, number): sweep
        self._lips = {}                        # runId: novaGui.plumeSweeps.lipState of the run's nozzle
        self._jobs = collections.deque()       # (runId, number, picklePath), in the order they solve
        self._process = None
        self._current = None                   # (runId, number) of the sweep solving
        self._cancelled = False
        self._closing = False

    # -- Private Helper Methods -- #
    def _save(self, sweep: dict) -> None:

        '''

        Write a sweep to its run's folder when the session has a store and the sweep is still
        kept. A run deleted meanwhile has no folder, and nothing is written.

        '''

        if self.store is None:
            return
        with self._lock:
            if self._closing or self._sweeps.get((sweep['runId'], sweep['number'])) is not sweep:
                return
            content = {**sweep, 'points': [dict(point) for point in sweep['points']]}
        try:
            self.store.savePlumeSweep(sweep['runId'], content)
        except OSError:
            pass

    def _changed(self, sweep: dict) -> None:

        self._save(sweep)
        self._publish({'type': 'plumeSweeps', 'runId': sweep['runId']})

    def _advance(self) -> None:

        '''Start the next queued sweep when none is solving.'''

        with self._lock:
            if self._process is not None or self._closing:
                return
            while self._jobs:
                runId, number, picklePath = self._jobs.popleft()
                sweep = self._sweeps.get((runId, number))
                if sweep is None:
                    continue
                points = [(point['index'], *plumeModel.pointConditions(sweep, point))
                          for point in sweep['points'] if point['state'] == 'queued']
                if points:
                    break
            else:
                return
            eventQueue = self._context.Queue()
            self._process = self._context.Process(target = plumeModel.runSweep, name = f'novaPlume{runId}.{number}',
                                                  args = (picklePath, points, sweep['reach'], eventQueue), daemon = True)
            self._current = (runId, number)
            self._cancelled = False
            process = self._process
            process.start()
        indices = {point[0] for point in points}
        threading.Thread(target = self._drain, args = (process, eventQueue, sweep, indices),
                         name = f'novaPlumePump{runId}.{number}', daemon = True).start()

    def _drain(self, process, eventQueue, sweep: dict, indices: set) -> None:

        '''

        Pump thread: fold the worker's messages into the sweep until it ends or dies. The points it
        was given and did not solve read cancelled or failed; points queued again meanwhile wait
        for their own turn.

        '''

        reason = None
        while reason is None:
            try:
                kind, payload = eventQueue.get(timeout = 0.25)
            except queue.Empty:
                if process.is_alive():
                    continue
                try:
                    kind, payload = eventQueue.get(timeout = 0.5)
                except (queue.Empty, EOFError, OSError):
                    break
            except (EOFError, OSError):
                break

            if kind == 'start':
                with self._lock:
                    sweep['lip'] = payload
                    self._lips.setdefault(sweep['runId'], payload)
                self._changed(sweep)
            elif kind == 'begin':
                with self._lock:
                    sweep['points'][payload].update(state = 'running', error = '')
                self._changed(sweep)
            elif kind == 'point':
                index, outcome = payload
                with self._lock:
                    sweep['points'][index].update(state = outcome['state'], error = outcome.get('error', ''),
                                                  result = outcome.get('result'))
                self._changed(sweep)
            elif kind == 'end':
                reason = str(payload)

        process.join(timeout = 5.0)
        with self._lock:
            cancelled = self._cancelled
            if reason is None:
                reason = 'cancelled' if cancelled else f'the plume worker ended with exit code {process.exitcode}'
            left = [point for point in sweep['points']
                    if point['index'] in indices and point['state'] in ('queued', 'running')]
            for point in left:
                point.update(state = 'cancelled' if cancelled else 'failed',
                             error = 'cancelled before it was solved' if cancelled else reason)
            self._process = None
            self._current = None
        self._changed(sweep)
        if self._onSettled is not None and (sweep['runId'], sweep['number']) in self._sweeps:
            self._onSettled(sweep['runId'])
        self._advance()

    def _restore(self, sweep: dict) -> None:

        '''

        Keep a sweep the store saved. Its points still queued or solving when the last window
        closed were not solved; they read cancelled, and can be queued again.

        '''

        stopped = False
        for point in sweep['points']:
            if point.get('state') in ('queued', 'running'):
                point.update(state = 'cancelled', error = 'NOVA closed before it was solved')
                stopped = True
        self._sweeps[(sweep['runId'], sweep['number'])] = sweep
        if stopped:
            self._save(sweep)

    # -- Public Methods -- #
    def load(self, runIds: list) -> None:

        '''Keep the plume sweeps the store holds for the given runs.'''

        if self.store is None:
            return
        for runId in runIds:
            for sweep in self.store.plumeSweeps(runId):
                self._restore(sweep)

    def holds(self, runId: int) -> bool:

        '''Whether a run has a plume sweep.'''

        with self._lock:
            return any(key[0] == runId for key in self._sweeps)

    def sweepsOf(self, runId: int) -> list:

        '''A run's plume sweeps as the browser reads them (novaGui.plumeSweeps.table), newest first.'''

        with self._lock:
            kept = [{**sweep, 'points': [dict(point) for point in sweep['points']]}
                    for key, sweep in sorted(self._sweeps.items(), reverse = True) if key[0] == runId]
        return [plumeModel.table(sweep) for sweep in kept]

    def sweep(self, runId: int, number: int) -> dict:

        '''

        One of a run's plume sweeps, copied, as kept.

        Raises:
        -------
        KeyError : if the run has no such sweep

        '''

        with self._lock:
            sweep = self._sweeps[(runId, number)]
            return {**sweep, 'points': [dict(point) for point in sweep['points']]}

    def lip(self, runId: int) -> dict | None:

        '''The lip state of a run's nozzle, once known (novaGui.plumeSweeps.lipState).'''

        with self._lock:
            return self._lips.get(runId)

    def setLip(self, runId: int, lip: dict) -> None:

        with self._lock:
            self._lips[runId] = lip

    def add(self, runId: int, picklePath: str, sweep: dict) -> dict:

        '''

        Keep a sweep that novaGui.plumeSweeps.build laid out for a run, and queue it.

        Returns:
        --------
        dict : the sweep as the browser reads it

        '''

        with self._lock:
            number = max([key[1] for key in self._sweeps if key[0] == runId] + [0]) + 1
            sweep = {**sweep, 'runId': runId, 'number': number, 'lip': self._lips.get(runId)}
            self._sweeps[(runId, number)] = sweep
            self._jobs.append((runId, number, picklePath))
        self._changed(sweep)
        self._advance()
        return plumeModel.table(self.sweep(runId, number))

    def resume(self, runId: int, number: int, picklePath: str) -> int:

        '''

        Queue a sweep's cancelled points again. Returns how many were queued.

        Raises:
        -------
        KeyError : if the run has no such sweep

        '''

        with self._lock:
            sweep = self._sweeps[(runId, number)]
            stopped = [point for point in sweep['points'] if point['state'] == 'cancelled']
            for point in stopped:
                point.update(state = 'queued', error = '', result = None)
            if stopped and not any(job[:2] == (runId, number) for job in self._jobs):
                self._jobs.append((runId, number, picklePath))
        if stopped:
            self._changed(sweep)
            self._advance()
        return len(stopped)

    def delete(self, runId: int, number: int) -> None:

        '''

        Delete one of a run's plume sweeps, cancelling it if it is solving.

        Raises:
        -------
        KeyError : if the run has no such sweep

        '''

        with self._lock:
            self._sweeps.pop((runId, number))
            process = self._process if self._current == (runId, number) else None
            if process is not None:
                self._cancelled = True
        if process is not None:
            process.terminate()
        if self.store is not None:
            self.store.removePlumeSweep(runId, number)
        self._publish({'type': 'plumeSweeps', 'runId': runId})
        if self._onSettled is not None:
            self._onSettled(runId)

    def dropRun(self, runId: int) -> None:

        '''

        Forget a run's plume sweeps, which go with its folder, cancelling the one solving. The
        files are the run's to remove.

        '''

        with self._lock:
            dropped = [key for key in self._sweeps if key[0] == runId]
            for key in dropped:
                del self._sweeps[key]
            self._lips.pop(runId, None)
            process = self._process if self._current is not None and self._current[0] == runId else None
            if process is not None:
                self._cancelled = True
        if process is not None:
            process.terminate()
        if dropped:
            self._publish({'type': 'plumeSweeps', 'runId': runId})

    @property
    def busy(self) -> bool:

        return self._process is not None

    def shutdown(self) -> None:

        '''Stop the sweep solving and queue nothing more; its points read cancelled at the next launch.'''

        with self._lock:
            self._closing = True
            self._jobs.clear()
            process = self._process
            if process is not None:
                self._cancelled = True
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout = 5.0)
