
# -- NOVA GUI Run Store -- #

'''

The finished runs the GUI keeps between launches.

Each run has a folder of its own, `<store>/run<id>/`, and the worker writes into it directly: the
outputs in `<runName>Outputs/`, the config the run was given beside them as
`<runName>RunConfig.json`, and the pickled Nozzle as `novaGuiResult.pkl`. Once the run finishes,
`run.json` joins them: the run as the run list shows it (its name and note, the config it ran,
the headline of its result table, its warnings, its run time and its size on disk), with paths
relative to the folder, so the store can move. A folder without `run.json` is a run in progress,
or one that never finished because its server closed; `collect` removes those older than
`staleHours` at launch.

Run ids count up across launches and are never given out twice, so a run keeps its number for as
long as it is kept, and the server's figure and table caches, which key on the id, never answer
for another run. `store.json` holds the highest id given out and the baseline. A run's id is
claimed by creating its folder, which only one process can do, so two servers on the same store
never share a number; each reads the store when it starts, and does not list the runs another one
adds after that.

The store keeps every named run and the baseline. Unnamed runs go oldest first once there are
more than `unnamedRuns` of them, or once the store holds more than `storeBytes`; the run that has
just finished always stays (`pruned`). A run's outputs take 8 to 17 MB.

A trade sweep (novaGui.sweeps) is kept as `sweeps/sweep<id>.json`: its name, the config it starts
from, the fields it sweeps and each point's state and run. Sweep ids count up across launches the
way run ids do, held in `store.json` as `lastSweepId`; creating the sweep's file claims its id.

A plume sweep (novaGui.plumeSweeps) belongs to one run and is kept in that run's folder, as
`plumeSweeps/plume<n>.json`, numbered within the run; it goes when the run's folder goes, and its
size counts in the run's.

The run queue is kept as `queue.json`, which the session writes at each change to it: every run
queued on its own and the one going, each with its label, config, figure mode and the time it was
queued, and the runs a closed window left unrun, with why. A sweep's points are its own file's to
keep. The file is one window's queue: a second server on the same store writes over it.

The store lives in `%LOCALAPPDATA%\\NOVA\\runs` on Windows and `~/.local/share/NOVA/runs`
elsewhere; NOVA_RUN_STORE names another folder. It is the user's own folder, and the server
unpickles the Nozzle each run saved there, as it does a run of its own.

Author: Sean Bowman
Date:   11/19/2026

'''

# Standard library imports
import json
import os
import re
import shutil
import sys
import time

unnamedRuns = 24                 # unnamed runs kept, besides the named ones and the baseline
storeBytes = 2 * 2 ** 30         # [B] the store's size past which unnamed runs go
staleHours = 12.0                # [h] age at which an unfinished run's folder is collected
recordName = 'run.json'
indexName = 'store.json'
queueName = 'queue.json'
queueStates = ('queued', 'running', 'notRun')
sweepFolderName = 'sweeps'
plumeFolderName = 'plumeSweeps'
recordVersion = 1
_runFolder = re.compile(r'^run(\d+)$')
_sweepFile = re.compile(r'^sweep(\d+)\.json$')
_plumeFile = re.compile(r'^plume(\d+)\.json$')

def storeRoot() -> str:

    '''The store's folder on this machine: NOVA_RUN_STORE, else the user's local application data.'''

    named = os.environ.get('NOVA_RUN_STORE', '').strip()
    if named:
        return os.path.abspath(os.path.expanduser(named))
    if sys.platform == 'win32' and os.environ.get('LOCALAPPDATA'):
        return os.path.join(os.environ['LOCALAPPDATA'], 'NOVA', 'runs')

    return os.path.join(os.path.expanduser('~'), '.local', 'share', 'NOVA', 'runs')

def folderBytes(folder: str) -> int:

    '''[B] the size of every file under a folder, its run record aside.'''

    total = 0
    for parent, _, names in os.walk(folder):
        for name in names:
            if parent == folder and name == recordName:
                continue
            try:
                total += os.path.getsize(os.path.join(parent, name))
            except OSError:
                continue

    return total

def pruned(runs: list, baseline: int | None, newest: int | None,
           countLimit: int | None = None, byteLimit: int | None = None) -> list:

    '''

    The runs to drop, oldest first, so the store keeps within its limits.

    Parameters:
    -----------
    runs : list
        (runId, named, bytes) for every kept run, oldest first.
    baseline : int or None
        The baseline, which stays.
    newest : int or None
        The run that has just finished, which stays.
    countLimit : int, optional
        Unnamed runs kept; `unnamedRuns` by default.
    byteLimit : int, optional
        [B] the size the store keeps within, as far as dropping unnamed runs can; `storeBytes` by
        default.

    Returns:
    --------
    list : run ids, oldest first

    '''

    countLimit = unnamedRuns if countLimit is None else countLimit
    byteLimit = storeBytes if byteLimit is None else byteLimit
    candidates = [runId for runId, named, _ in runs if not named and runId not in (baseline, newest)]
    unnamed = sum(1 for runId, named, _ in runs if not named and runId != baseline)
    total = sum(size for _, _, size in runs)
    sizes = {runId: size for runId, _, size in runs}
    dropped = []
    for runId in candidates:
        if unnamed <= countLimit and total <= byteLimit:
            break
        dropped.append(runId)
        unnamed -= 1
        total -= sizes[runId]

    return dropped

class RunStore:

    '''

    The run folders under one store root, and its index.

    '''

    # -- Constructor -- #
    def __init__(self, root: str | None = None):

        self.root = os.path.abspath(root or storeRoot())
        os.makedirs(self.root, exist_ok = True)

    # -- Private Helper Methods -- #
    def _index(self) -> dict:

        try:
            with open(os.path.join(self.root, indexName), encoding = 'utf-8') as handle:
                index = json.load(handle)
        except (OSError, ValueError):
            index = {}
        if not isinstance(index, dict):
            index = {}
        def whole(value) -> bool:
            return isinstance(value, int) and not isinstance(value, bool)

        lastRunId, lastSweepId, baseline = index.get('lastRunId'), index.get('lastSweepId'), index.get('baseline')
        return {'lastRunId': lastRunId if whole(lastRunId) else 0, 'lastSweepId': lastSweepId if whole(lastSweepId) else 0,
                'baseline': baseline if whole(baseline) else None}

    def _writeJson(self, path: str, content: dict) -> None:

        '''Write through a temporary file, so a crash cannot leave half of one.'''

        temporary = path + '.part'
        with open(temporary, 'w', encoding = 'utf-8', newline = '\n') as handle:
            json.dump(content, handle, indent = 1)
        os.replace(temporary, path)

    def _updateIndex(self, **changes) -> None:

        try:
            self._writeJson(os.path.join(self.root, indexName), {**self._index(), **changes})
        except OSError:
            pass

    def _folderIds(self) -> list:

        '''The ids of every run folder under the root, finished or not, in order.'''

        try:
            entries = os.listdir(self.root)
        except OSError:
            return []
        matches = [_runFolder.match(entry) for entry in entries]
        return sorted(int(match.group(1)) for match in matches
                      if match and os.path.isdir(os.path.join(self.root, match.group(0))))

    def _sweepIds(self) -> list:

        '''The ids of every sweep file, in order.'''

        try:
            entries = os.listdir(os.path.join(self.root, sweepFolderName))
        except OSError:
            return []
        matches = [_sweepFile.match(entry) for entry in entries]
        return sorted(int(match.group(1)) for match in matches if match)

    def _sweepPath(self, sweepId: int) -> str:

        return os.path.join(self.root, sweepFolderName, f'sweep{int(sweepId)}.json')

    def _inside(self, folder: str, relative) -> str:

        '''A path the record names relative to its folder, or '' if it is blank or leads outside it.'''

        if not isinstance(relative, str) or not relative:
            return ''
        path = os.path.normpath(os.path.join(folder, relative))
        return path if path.startswith(folder + os.sep) else ''

    # -- Public Methods -- #
    def folder(self, runId: int) -> str:

        return os.path.join(self.root, f'run{int(runId)}')

    def claim(self) -> tuple:

        '''

        The next run id and its new, empty folder. The id is past every id given out before, and
        creating its folder claims it.

        Returns:
        --------
        tuple : (runId, folder)

        '''

        folders = self._folderIds()
        runId = max([self._index()['lastRunId']] + folders[-1:]) + 1
        while True:
            folder = self.folder(runId)
            try:
                os.mkdir(folder)
                break
            except FileExistsError:
                runId += 1
        self._updateIndex(lastRunId = max(runId, self._index()['lastRunId']))

        return runId, folder

    def save(self, runId: int, content: dict) -> int:

        '''

        Write a finished run's record into its folder. Paths in `content` (outputDir, picklePath)
        are stored relative to the folder.

        Returns:
        --------
        int : [B] the size of the run's files

        '''

        folder = self.folder(runId)
        stored = dict(content)
        for key in ('outputDir', 'picklePath'):
            path = str(stored.get(key) or '')
            stored[key] = os.path.relpath(path, folder) if path and os.path.isabs(path) else path
        stored['bytes'] = folderBytes(folder)
        stored['version'] = recordVersion
        self._writeJson(os.path.join(folder, recordName), stored)

        return stored['bytes']

    def records(self) -> list:

        '''

        Every finished run in the store, oldest first, as saved, with its paths made absolute again.
        A record that does not read is passed over and its folder left alone.

        Returns:
        --------
        list : [dict] each with 'runId' and 'folder'

        '''

        found = []
        for runId in self._folderIds():
            folder = self.folder(runId)
            try:
                with open(os.path.join(folder, recordName), encoding = 'utf-8') as handle:
                    content = json.load(handle)
            except (OSError, ValueError):
                continue
            if not isinstance(content, dict):
                continue
            content.update(runId = runId, folder = folder,
                           outputDir = self._inside(folder, content.get('outputDir')),
                           picklePath = self._inside(folder, content.get('picklePath')))
            found.append(content)

        return found

    def remove(self, runId: int) -> None:

        '''Delete a run's folder.'''

        shutil.rmtree(self.folder(runId), ignore_errors = True)

    def collect(self, maxAgeHours: float = staleHours) -> list:

        '''

        Remove the folders of runs that never finished, older than `maxAgeHours`.

        Returns:
        --------
        list : the run ids removed

        '''

        cutoff = time.time() - 3600.0 * maxAgeHours
        removed = []
        for runId in self._folderIds():
            folder = self.folder(runId)
            try:
                stale = not os.path.isfile(os.path.join(folder, recordName)) and os.path.getmtime(folder) < cutoff
            except OSError:
                continue
            if stale:
                shutil.rmtree(folder, ignore_errors = True)
                removed.append(runId)

        return removed

    def claimSweep(self) -> int:

        '''

        The next sweep id, past every id given out before. Creating its file claims it; `saveSweep`
        fills it.

        '''

        os.makedirs(os.path.join(self.root, sweepFolderName), exist_ok = True)
        sweepId = max([self._index()['lastSweepId']] + self._sweepIds()[-1:]) + 1
        while True:
            try:
                with open(self._sweepPath(sweepId), 'x', encoding = 'utf-8'):
                    pass
                break
            except FileExistsError:
                sweepId += 1
        self._updateIndex(lastSweepId = max(sweepId, self._index()['lastSweepId']))

        return sweepId

    def saveSweep(self, sweep: dict) -> None:

        '''Write a sweep to its file.'''

        os.makedirs(os.path.join(self.root, sweepFolderName), exist_ok = True)
        self._writeJson(self._sweepPath(sweep['sweepId']), {**sweep, 'version': recordVersion})

    def sweeps(self) -> list:

        '''

        Every sweep in the store, oldest first. A file that does not read, or that a server has
        claimed and not yet written, is passed over.

        '''

        found = []
        for sweepId in self._sweepIds():
            try:
                with open(self._sweepPath(sweepId), encoding = 'utf-8') as handle:
                    content = json.load(handle)
            except (OSError, ValueError):
                continue
            if isinstance(content, dict) and isinstance(content.get('points'), list) and isinstance(content.get('fields'), list):
                content['sweepId'] = sweepId
                found.append(content)

        return found

    def removeSweep(self, sweepId: int) -> None:

        '''Delete a sweep's file; its runs are the session's to remove.'''

        try:
            os.remove(self._sweepPath(sweepId))
        except OSError:
            pass

    def saveQueue(self, runs: list) -> None:

        '''

        Write the run queue, in order.

        Parameters:
        -----------
        runs : list
            {'label', 'config', 'mode', 'queuedAt', 'state', 'reason'} for each run: `state` is
            'queued', 'running', or 'notRun' for one a closed window left unrun, which `reason`
            explains; `queuedAt` [s] is epoch time.

        '''

        self._writeJson(os.path.join(self.root, queueName), {'runs': list(runs), 'version': recordVersion})

    def queuedRuns(self) -> list:

        '''

        The run queue as last saved, in order, each entry as `saveQueue` takes it. An entry without
        a config is passed over, and a file that is missing or does not read is an empty queue.

        '''

        try:
            with open(os.path.join(self.root, queueName), encoding = 'utf-8') as handle:
                content = json.load(handle)
        except (OSError, ValueError):
            return []
        runs = content.get('runs') if isinstance(content, dict) else None
        if not isinstance(runs, list):
            return []

        found = []
        for entry in runs:
            if not isinstance(entry, dict) or not isinstance(entry.get('config'), dict):
                continue
            config = entry['config']
            queuedAt = entry.get('queuedAt')
            found.append({
                'label': str(entry.get('label') or config.get('filename') or 'the form'),
                'config': config,
                'mode': entry['mode'] if entry.get('mode') in ('dark', 'light') else 'dark',
                'queuedAt': float(queuedAt) if isinstance(queuedAt, (int, float)) and not isinstance(queuedAt, bool) else 0.0,
                'state': entry['state'] if entry.get('state') in queueStates else 'queued',
                'reason': str(entry.get('reason') or ''),
            })

        return found

    def _plumePath(self, runId: int, number: int) -> str:

        return os.path.join(self.folder(runId), plumeFolderName, f'plume{int(number)}.json')

    def savePlumeSweep(self, runId: int, sweep: dict) -> None:

        '''

        Write a run's plume sweep to its file. A run whose folder is gone, deleted while the sweep
        ran, is not made again.

        Raises:
        -------
        FileNotFoundError : if the run's folder is gone

        '''

        if not os.path.isdir(self.folder(runId)):
            raise FileNotFoundError(f'run {runId} has no folder in the store')
        os.makedirs(os.path.join(self.folder(runId), plumeFolderName), exist_ok = True)
        self._writeJson(self._plumePath(runId, sweep['number']), {**sweep, 'version': recordVersion})

    def plumeSweeps(self, runId: int) -> list:

        '''

        A run's plume sweeps, in the order of their numbers. A file that does not read is passed
        over.

        '''

        try:
            entries = os.listdir(os.path.join(self.folder(runId), plumeFolderName))
        except OSError:
            return []
        matches = [_plumeFile.match(entry) for entry in entries]
        found = []
        for number in sorted(int(match.group(1)) for match in matches if match):
            try:
                with open(self._plumePath(runId, number), encoding = 'utf-8') as handle:
                    content = json.load(handle)
            except (OSError, ValueError):
                continue
            if isinstance(content, dict) and isinstance(content.get('points'), list):
                content.update(runId = int(runId), number = number)
                found.append(content)
        return found

    def removePlumeSweep(self, runId: int, number: int) -> None:

        '''Delete one of a run's plume sweeps.'''

        try:
            os.remove(self._plumePath(runId, number))
        except OSError:
            pass

    @property
    def baseline(self) -> int | None:

        return self._index()['baseline']

    def setBaseline(self, runId: int | None) -> None:

        self._updateIndex(baseline = runId)
