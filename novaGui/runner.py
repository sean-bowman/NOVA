
# -- NOVA Pipeline Runner -- #

'''

Runs Nozzle.generateNozzle() on a background thread so the caller stays responsive during
a multi-minute solve. NOVA's printed output and its progress events (NOVA.progress) are
forwarded to a queue the caller drains; the front end folds the events into its run bar
with novaGui.progress.RunProgress. The web front end runs it inside a worker process
(novaGui.worker), the legacy Tkinter front end on a thread of its window.

Before the first run the loader:

  - forces the Matplotlib Agg backend and applies the GUI palette (themeColors) so
    NOVA's saved figures match the rest of the window,
  - stops plotly.offline.plot from opening a browser tab,
  - sends the outputs to the session's staging folder rather than to wherever NOVA
    would put them.

While a run reports its progress as events, NOVA draws no tqdm bars, so none reach the log.

A warning the run raises through Python's warnings module (NOVA's own, and numpy's or scipy's) is
written to the log as Python would print it, and sent as a message of its own, so a front end can
count and list a run's warnings rather than leave them in the log.

Every run writes all of NOVA's outputs, figures and data files alike, into the
staging folder, where the front end's views read them. An export copies the ones chosen
to the output folder. A staging folder belongs to one session of a front end and is
removed when it closes; `clearStaging` removes any a crashed session left behind.

Author: Sean Bowman
Date:   08/28/2026

'''

import os
import sys
import json
import time
import shutil
import tempfile
import warnings
import importlib
import threading
import traceback

# Set before NOVA is imported anywhere. While it is set NOVA writes every figure and opens none
# of them: plotly writes its HTML without opening a browser tab per figure, and NOVA.figures
# selects a non-interactive matplotlib backend at import, while that choice is still free.
# Exporting NOVA_HEADLESS=0 before launching puts the windows back.
os.environ.setdefault('NOVA_HEADLESS', '1')

from . import themeColors
from . import configSchema

# NOVA is installed as a package, so no path handling is needed here.

# Files NOVA writes into <name>Outputs/. Names are fixed except the contour and
# geometry text/STL files, which are prefixed with the run's `filename`.
figureFiles = {
    'contour':      'contourSegmentsVisualization.png',
    'mach':         'machContours.png',
    'pressure':     'pressureContours.png',
    'temperature':  'temperatureContours.png',
    'nearWall':     'nearWallProperties.png',
}
htmlFiles = {
    'channelMesh':  'threeChannelMeshViewInterfaced.html',
    'volute':       'VoluteView.html',
    'heatTransfer': 'heatTransferModelOutput.html',
    # Plotly companions written by figures.exportInteractiveFigures.
    'revolved':     'revolvedContourView.html',
    'contour':      'contourInteractive.html',
    'nearWall':     'nearWallInteractive.html',
    'machField':    'machFieldInteractive.html',
    'pressureField': 'pressureFieldInteractive.html',
    'temperatureField': 'temperatureFieldInteractive.html',
    'plume':          'plumeStructureInteractive.html',
}

def warningRelay(messageQueue):

    '''

    A `warnings.showwarning` that puts each warning on the queue twice: as the log line Python
    would print, and as ('warning', {'category', 'message', 'where'}), `where` the file name and
    line that raised it.

    '''

    def show(message, category, filename, lineno, file = None, line = None):
        text = str(message)
        messageQueue.put(('log', warnings.formatwarning(text, category, filename, lineno, line).rstrip()))
        messageQueue.put(('warning', {'category': getattr(category, '__name__', str(category)), 'message': text,
                                      'where': f'{os.path.basename(str(filename))}:{lineno}'}))

    return show

def stagingFolder() -> str:

    '''

    The folder this session's runs write into: one per window process, under the system's
    temporary directory.

    '''

    return os.path.join(tempfile.gettempdir(), 'NOVA', f'session{os.getpid()}')

def clearStaging(maxAgeHours: float = 12.0) -> None:

    '''

    Remove other sessions' staging folders older than `maxAgeHours`. A window that closes removes
    its own; one that crashed leaves it behind, and this is what collects it.

    '''

    parent = os.path.dirname(stagingFolder())
    if not os.path.isdir(parent):
        return

    cutoff = time.time() - 3600.0 * maxAgeHours
    for entry in os.listdir(parent):
        path = os.path.join(parent, entry)
        if path != stagingFolder() and os.path.isdir(path) and os.path.getmtime(path) < cutoff:
            shutil.rmtree(path, ignore_errors = True)

class RunResult:

    '''

    Outcome of one pipeline run, delivered to the GUI as ('result', RunResult).

    '''

    def __init__(self):

        self.ok = False
        self.nozzle = None            # the populated Nozzle instance on success
        self.outputDir = ''           # <name>Outputs/ directory in the staging folder
        self.runName = ''             # the config's filename, which names the outputs
        self.configPath = ''          # the JSON handed to setInputs
        self.elapsedSec = 0.0
        self.error = ''               # short one-line message
        self.traceback = ''           # full traceback on failure

class _StreamToQueue:

    '''

    Minimal write-only text sink that splits input into lines and pushes them to
    a queue. Carriage returns are treated as line breaks.
    Deliberately not an io.TextIOBase subclass: print() needs only write() and
    flush(), and the extra attributes below satisfy libraries that probe stdout.

    '''

    encoding = 'utf-8'
    errors = 'replace'

    def __init__(self, messageQueue):

        self._queue = messageQueue
        self._buffer = ''

    def _emit(self, line: str) -> None:

        self._queue.put(('log', line))

    def write(self, chunk: str) -> int:

        if not chunk:
            return 0
        self._buffer += str(chunk).replace('\r', '\n')
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            if line.strip():
                self._emit(line.rstrip())
        return len(chunk)

    def flush(self) -> None:

        if self._buffer.strip():
            self._emit(self._buffer.rstrip())
        self._buffer = ''

    def writable(self) -> bool:

        return True

    def isatty(self) -> bool:

        return False

    def fileno(self):

        raise OSError('_StreamToQueue has no file descriptor')

class PipelineRunner:

    '''

    One-run-at-a-time executor for the NOVA pipeline.

    Messages placed on the queue:

        ('log', str)                        a line of run output
        ('status', (state, detail))         state in {'running','done','error'}
        ('stage', dict)                     a NOVA.progress event
        ('warning', dict)                   a warning the run raised: category, message, where
        ('result', RunResult)               terminal, always the last message

    `stageHook`, when set, is called as `stageHook(nozzle, event)` with each progress event, on the
    run's own thread while NOVA waits on it, so it reads the Nozzle in a settled state: the web
    worker takes the contour figures there when the contour stage ends. A hook that raises is
    logged and the run goes on.

    '''

    def __init__(self, messageQueue):

        self._queue = messageQueue
        self._thread = None
        self._busy = False
        self.stageHook = None

    @property
    def busy(self) -> bool:

        return self._busy

    def start(self, configDict: dict, outputBaseDir: str) -> None:

        '''

        Launch a run. Raises RuntimeError if one is already in progress.

        '''

        if self._busy:
            raise RuntimeError('a run is already in progress')

        self._busy = True
        self._thread = threading.Thread(
            target = self._worker,
            args = (dict(configDict), outputBaseDir),
            daemon = True,
        )
        self._thread.start()

    # -- Worker -- #

    def _worker(self, configDict: dict, outputBaseDir: str) -> None:

        result = RunResult()
        started = time.perf_counter()
        savedStdout, savedStderr = sys.stdout, sys.stderr

        try:
            self._queue.put(('status', ('running', 'loading NOVA')))
            nozzleModule, nozzleClass = self._loadNova(outputBaseDir)
            from NOVA import progress as novaProgress

            forced = self._applyForcedFlags(configDict)
            os.makedirs(outputBaseDir, exist_ok = True)

            runName = str(configDict.get('filename') or 'novaRun')
            result.runName = runName
            # A run of the same name replaces the last one's outputs rather than mixing with them
            shutil.rmtree(os.path.join(outputBaseDir, runName + 'Outputs'), ignore_errors = True)
            configPath = os.path.join(outputBaseDir, runName + 'RunConfig.json')
            with open(configPath, 'w') as handle:
                json.dump(configDict, handle, indent = 4)
            result.configPath = configPath

            self._queue.put(('log', f'run config written to {configPath}'))
            if forced:
                self._queue.put(('log', 'program flags forced on for the GUI: ' + ', '.join(forced)))
            self._queue.put(('status', ('running', 'generating nozzle')))

            sys.stdout = _StreamToQueue(self._queue)
            sys.stderr = _StreamToQueue(self._queue)

            nozzle = nozzleClass()

            def report(event: dict) -> None:
                self._queue.put(('stage', event))
                if self.stageHook is not None:
                    try:
                        self.stageHook(nozzle, event)
                    except Exception as exc:               # noqa: BLE001 -- the run matters more than the hook
                        self._queue.put(('log', f'stage hook failed: {type(exc).__name__}: {exc}'))

            # The filters stay as they are; only where a shown warning goes changes
            with novaProgress.reporting(report), warnings.catch_warnings():
                warnings.showwarning = warningRelay(self._queue)
                nozzle.generateNozzle(configPath = configPath)

            sys.stdout.flush()
            sys.stderr.flush()
            sys.stdout, sys.stderr = savedStdout, savedStderr

            result.ok = True
            result.nozzle = nozzle
            result.outputDir = getattr(nozzle, 'dataFolder', '') or os.path.join(outputBaseDir, runName + 'Outputs')

        except BaseException as exc:                       # noqa: BLE001 -- surface every failure to the GUI
            sys.stdout, sys.stderr = savedStdout, savedStderr
            result.ok = False
            result.error = f'{type(exc).__name__}: {exc}'
            result.traceback = traceback.format_exc()

        finally:
            sys.stdout, sys.stderr = savedStdout, savedStderr
            self._closeFigures()
            result.elapsedSec = time.perf_counter() - started
            self._busy = False
            if result.ok:
                self._queue.put(('status', ('done', f'{result.elapsedSec:.1f} s')))
            else:
                self._queue.put(('status', ('error', result.error)))
                self._queue.put(('log', result.traceback))
            self._queue.put(('result', result))

    # -- Load and patch NOVA -- #

    def _loadNova(self, outputBaseDir: str):

        '''

        Import the Nozzle module and class, applying the GUI's patches. Safe to
        call once per run; each patch guards against being applied twice.

        '''

        import matplotlib
        matplotlib.use('Agg', force = True)
        import matplotlib.pyplot as plt
        plt.rcParams.update(themeColors.matplotlibRcParams())

        # NOVA.Nozzle names both the module and the class it exports, and the
        # package binds the class. The patches below need the module, so it is
        # fetched by name rather than read off the package.
        nozzleModule = importlib.import_module('NOVA.Nozzle')
        from NOVA import Nozzle as nozzleClass

        # The figures the run writes, saved and interactive, in the mode the window is showing
        from NOVA import palette as figurePalette
        figurePalette.setFigureMode(themeColors.mode)

        # Send outputs to the staging folder rather than to wherever the nearest .git
        # happens to be.
        nozzleClass._getOutputRoot = lambda self, _base = outputBaseDir: _base

        return nozzleModule, nozzleClass

    def _applyForcedFlags(self, configDict: dict) -> list:

        '''

        Set the program flags that make a run write every figure and data file, which
        the views read and an export offers. Returns the keys that were changed.

        '''

        forced = []

        if not configDict.get('filename'):
            configDict['filename'] = 'novaRun'

        def force(key: str) -> None:
            if configDict.get(key) not in (True, 'on'):
                configDict[key] = True
                forced.append(key)

        for key in configSchema.forcedFlags:
            force(key)

        return forced

    def _closeFigures(self) -> None:

        try:
            import matplotlib.pyplot as plt
            plt.close('all')
        except Exception:
            pass

def findOutputs(outputDir: str, runName: str) -> dict:

    '''

    Map the known NOVA output categories to absolute paths that exist in
    outputDir. Returns dicts under 'figures', 'html', 'data' plus a flat 'all'
    listing of every file in the folder.

    '''

    found = {'figures': {}, 'html': {}, 'data': {}, 'all': []}

    if not outputDir or not os.path.isdir(outputDir):
        return found

    for key, name in figureFiles.items():
        path = os.path.join(outputDir, name)
        if os.path.isfile(path):
            found['figures'][key] = path

    for key, name in htmlFiles.items():
        path = os.path.join(outputDir, name)
        if os.path.isfile(path):
            found['html'][key] = path

    for entry in sorted(os.listdir(outputDir)):
        path = os.path.join(outputDir, entry)
        if not os.path.isfile(path):
            continue
        found['all'].append(path)
        lower = entry.lower()
        if lower.endswith(('.txt', '.stl', '.pkl', '.csv')):
            found['data'].setdefault(entry, path)

    return found
