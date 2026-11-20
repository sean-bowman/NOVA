
# -- NOVA Run Worker Process -- #

'''

Entry point of the child process that runs one NOVA pipeline.

Each run gets a fresh process, started with the 'spawn' method so nothing from the server's
interpreter leaks into it. Inside, novaGui.runner.PipelineRunner does the run exactly as the
legacy Tkinter front end does it (forced program flags, staging output root, headless figures,
progress reported as events), and its messages are forwarded to the server through a
multiprocessing queue.

A separate process is what makes a run cancellable: the server terminates it. RocketCEA's
machine-wide lock (`nova.lock`, held through msvcrt.locking) is released by the operating
system when the process ends, so a cancelled run does not block the next one.

On success the worker pickles the Nozzle to `novaGuiResult.pkl` in the run's output folder,
after generateNozzle has returned, so the pickle carries every attribute the run set. The
server unpickles it to draw the views. The result also carries the summary line of the run's result
table and its headline numbers (novaGui.analysis), so the server can list the run, and set it in a
trade sweep's table, without unpickling it.

When the contour stage ends, the worker takes the figure descriptions that stage settles
(novaGui.plotting.contourStageViews) off the Nozzle, on the run's own thread while NOVA waits, and
sends them ahead of the result. A description is plain arrays and labels in no palette, so the
server draws it in whichever mode the browser asks for.

Messages put on the queue:

    ('log', str)
    ('status', (state, detail))
    ('stage', dict)         a NOVA.progress event
    ('partial', dict)       {'stage': 'contour', 'figures': {view key: figure description},
                            'throatX': the throat's axial position [m] or None}
    ('result', dict)        terminal: ok, runName, outputDir, picklePath, elapsedSec, headline, numbers,
                            error, traceback; `numbers` is [{'key', 'label', 'value', 'unit', 'tone'}]

Author: Sean Bowman
Date:   11/16/2026

'''

# Standard library imports
import os
import queue

resultPickleName = 'novaGuiResult.pkl'

def runPipeline(config: dict, outputDir: str, mode: str, eventQueue) -> None:

    '''

    Run NOVA on one config and report through `eventQueue`. Called in the child process.

    Parameters:
    -----------
    config : dict
        The complete config, in backend values.
    outputDir : str
        Folder the run writes into; NOVA puts its outputs in `<filename>Outputs/` beneath it.
    mode : str
        'dark' or 'light': the palette NOVA's saved figures are drawn in.
    eventQueue : multiprocessing.Queue
        Where messages go.

    '''

    # Before anything imports NOVA: write figures, open no windows or browser tabs
    os.environ['NOVA_HEADLESS'] = '1'

    try:
        # The runner reads the palette mode from novaGui.themeColors
        from novaGui import themeColors
        themeColors.bindPalette(mode)
        from novaGui.runner import PipelineRunner
    except BaseException as exc:                           # noqa: BLE001 -- report every failure
        import traceback
        eventQueue.put(('result', {'ok': False, 'runName': '', 'outputDir': '', 'picklePath': '',
                                   'elapsedSec': 0.0, 'error': f'{type(exc).__name__}: {exc}',
                                   'traceback': traceback.format_exc()}))
        return

    local = queue.Queue()
    runner = PipelineRunner(local)
    runner.stageHook = _contourHook(eventQueue)
    runner.start(config, outputDir)

    # The runner's last message is always its result
    while True:
        kind, payload = local.get()
        if kind != 'result':
            eventQueue.put((kind, payload))
            continue

        summary = {
            'ok':         payload.ok,
            'runName':    payload.runName,
            'outputDir':  payload.outputDir,
            'picklePath': '',
            'elapsedSec': payload.elapsedSec,
            'headline':   '',
            'numbers':    [],
            'error':      payload.error,
            'traceback':  payload.traceback,
        }
        if payload.ok:
            summary['headline'] = _headline(payload.nozzle)
            summary['numbers'] = headlineNumbers(payload.nozzle)
            summary['picklePath'] = _pickleNozzle(payload.nozzle, outputDir, eventQueue)
        eventQueue.put(('result', summary))
        break

def _contourHook(eventQueue):

    '''

    The runner's stage hook: when the top-level contour stage ends, send the views it settled.

    '''

    def hook(nozzle, event: dict) -> None:
        if event.get('type') != 'stageEnd' or event.get('path') != 'contour' or not event.get('ok'):
            return
        from novaGui import backend, plotting
        module = backend.figuresModule()
        figures = {}
        for key in plotting.contourStageViews:
            extract, _ = plotting.figureDescriptions[key]
            try:
                data = extract(module, nozzle)
            except Exception:                              # noqa: BLE001 -- the finished run draws it
                continue
            if data is not None:
                figures[key] = data
        if figures:
            eventQueue.put(('partial', {'stage': 'contour', 'figures': figures, 'throatX': _throatX(nozzle)}))

    return hook

def _throatX(nozzle) -> float | None:

    '''The throat's axial position [m], where the circuit view marks it while the run goes on, or None.'''

    try:
        import numpy as np
        wallX = np.asarray(nozzle.xNozzleWall, dtype = float)
        wallR = np.asarray(nozzle.rNozzleWall, dtype = float)
        return float(wallX[int(np.argmin(wallR))]) if wallX.size >= 2 and wallR.size == wallX.size else None
    except Exception:                                      # noqa: BLE001 -- the view draws without it
        return None

def _headline(nozzle) -> str:

    '''The result table's summary line (thrust, delivered Isp, propellants), or '' if it fails.'''

    try:
        from novaGui.analysis import resultRows
        return resultRows(nozzle)[0]
    except Exception:                                      # noqa: BLE001 -- the list shows the run without it
        return ''

def headlineNumbers(nozzle) -> list:

    '''

    The result pane's headline numbers (novaGui.analysis.headline) as text in display units,
    without the parts only the pane draws, or [] if they fail.

    '''

    try:
        from novaGui.analysis import headline
        return [{key: item[key] for key in ('key', 'label', 'value', 'unit', 'tone')} for item in headline(nozzle)]
    except Exception:                                      # noqa: BLE001 -- the run stands without them
        return []

def _pickleNozzle(nozzle, outputDir: str, eventQueue) -> str:

    '''

    Pickle the finished Nozzle beside the run's outputs with NOVA's own writer. Returns the path,
    or '' when the object will not pickle; the run still counts, with no views to draw.

    '''

    path = os.path.join(outputDir, resultPickleName)
    try:
        from NOVA.exports import pickleObject
        pickleObject(nozzle, path)
    except Exception as exc:                               # noqa: BLE001 -- the run itself succeeded
        eventQueue.put(('log', f'result could not be pickled for the views: {type(exc).__name__}: {exc}'))
        return ''

    return path
