
# -- NOVA Pipeline Runner -- #

'''

Runs Nozzle.generateNozzle() on a background thread so the Tk event loop stays
responsive during a multi-minute solve. Progress printed by NOVA is captured and
forwarded to a queue the GUI drains on its main thread.

Before the first run the loader:

  - forces the Matplotlib Agg backend and applies the GUI palette so NOVA's
    saved figures match the rest of the window,
  - stops plotly.offline.plot from opening a browser tab,
  - silences the tqdm progress bars (tqdm 4.65 predates TQDM_DISABLE),
  - redirects the output folder to the location chosen in the export tab.

Author: Sean Bowman
Date:   08/28/2026

'''

import os
import sys
import json
import time
import functools
import importlib
import threading
import traceback

# Set before NOVA is imported anywhere. While it is set NOVA writes every figure and opens none
# of them: plotly writes its HTML without opening a browser tab per figure, and NOVA.figures
# selects a non-interactive matplotlib backend at import, while that choice is still free.
# Exporting NOVA_HEADLESS=0 before launching puts the windows back.
os.environ.setdefault('NOVA_HEADLESS', '1')

from . import theme
from . import configSchema
from .progress import StageTracker

# NOVA is installed as a package, so no path handling is needed here.

# Files NOVA writes into <name>Outputs/. Names are fixed except the contour and
# geometry text/STL files, which are prefixed with the run's `filename`.
figureFiles = {
    'contour':      'contourSegmentsVisualization.png',
    'mach':         'machContours.png',
    'pressure':     'pressureContours.png',
    'temperature':  'temperatureContours.png',
    'nearWall':     'nearWallProperties.png',
    'heatTransfer': 'heatTransferModelOutput.png',
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

class RunResult:

    '''

    Outcome of one pipeline run, delivered to the GUI as ('result', RunResult).

    '''

    def __init__(self):

        self.ok = False
        self.nozzle = None            # the populated Nozzle instance on success
        self.outputDir = ''           # <name>Outputs/ directory
        self.configPath = ''          # the JSON handed to setInputs
        self.elapsedSec = 0.0
        self.error = ''               # short one-line message
        self.traceback = ''           # full traceback on failure

class _StreamToQueue:

    '''

    Minimal write-only text sink that splits input into lines and pushes them to
    a queue. Carriage returns from progress bars are treated as line breaks.
    Deliberately not an io.TextIOBase subclass: print() needs only write() and
    flush(), and the extra attributes below satisfy libraries that probe stdout.

    '''

    encoding = 'utf-8'
    errors = 'replace'

    def __init__(self, messageQueue, tracker = None):

        self._queue = messageQueue
        self._tracker = tracker
        self._buffer = ''

    def _emit(self, line: str) -> None:

        self._queue.put(('log', line))
        if self._tracker is not None:
            advance = self._tracker.match(line)
            if advance is not None:
                self._queue.put(('progress', advance))

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
        ('progress', (fraction, ceiling, label))  0-1 run progress and its stage
        ('result', RunResult)               terminal, always the last message

    '''

    def __init__(self, messageQueue):

        self._queue = messageQueue
        self._thread = None
        self._busy = False

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
            tracker = StageTracker(configDict)
            self._queue.put(('progress', (0.0, 0.02, 'loading NOVA')))
            self._queue.put(('status', ('running', 'loading NOVA')))
            nozzleModule, nozzleClass = self._loadNova(outputBaseDir)

            forced = self._applyForcedFlags(configDict)
            os.makedirs(outputBaseDir, exist_ok = True)

            runName = str(configDict.get('filename') or 'novaRun')
            configPath = os.path.join(outputBaseDir, runName + 'RunConfig.json')
            with open(configPath, 'w') as handle:
                json.dump(configDict, handle, indent = 4)
            result.configPath = configPath

            self._queue.put(('log', f'run config written to {configPath}'))
            advance = tracker.match('run config written')
            if advance is not None:
                self._queue.put(('progress', advance))
            if forced:
                self._queue.put(('log', 'program flags forced on for the GUI: ' + ', '.join(forced)))
            self._queue.put(('status', ('running', 'generating nozzle')))

            sys.stdout = _StreamToQueue(self._queue, tracker)
            sys.stderr = _StreamToQueue(self._queue, tracker)

            nozzle = nozzleClass()
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
        plt.rcParams.update(theme.matplotlibRcParams())

        # NOVA.Nozzle names both the module and the class it exports, and the
        # package binds the class. The patches below need the module, so it is
        # fetched by name rather than read off the package.
        nozzleModule = importlib.import_module('NOVA.Nozzle')
        from NOVA import Nozzle as nozzleClass

        # Silence progress bars in every NOVA module that binds tqdm by name.
        for moduleName in ('NOVA.Nozzle', 'NOVA.Volute'):
            module = sys.modules.get(moduleName)
            if module is None or not hasattr(module, 'tqdm'):
                continue
            if not getattr(module, '_novaGuiTqdmPatched', False):
                realTqdm = module.tqdm
                module.tqdm = functools.partial(realTqdm, disable = True)
                module._novaGuiTqdmPatched = True

        # Send outputs to the folder chosen in the export tab rather than to
        # wherever the nearest .git happens to be.
        nozzleClass._getOutputRoot = lambda self, _base = outputBaseDir: _base

        return nozzleModule, nozzleClass

    def _applyForcedFlags(self, configDict: dict) -> list:

        '''

        Override program-option flags so the geometry and analysis tabs have the
        files they read. Returns the list of keys that were changed.

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
