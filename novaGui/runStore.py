
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
recordVersion = 1
_runFolder = re.compile(r'^run(\d+)$')

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
        lastRunId = index.get('lastRunId')
        baseline = index.get('baseline')
        return {'lastRunId': lastRunId if isinstance(lastRunId, int) and not isinstance(lastRunId, bool) else 0,
                'baseline': baseline if isinstance(baseline, int) and not isinstance(baseline, bool) else None}

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

    @property
    def baseline(self) -> int | None:

        return self._index()['baseline']

    def setBaseline(self, runId: int | None) -> None:

        self._updateIndex(baseline = runId)
