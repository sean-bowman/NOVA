
# -- NOVA Run Worker Process -- #

'''

Entry point of the child process that runs one NOVA pipeline.

Each run gets a fresh process, started with the 'spawn' method so nothing from the server's
interpreter leaks into it. Inside, novaGui.runner.PipelineRunner does the run exactly as the
Tkinter front end does it (forced program flags, staging output root, headless figures,
silenced tqdm), and its messages are forwarded to the server through a multiprocessing queue.

A separate process is what makes a run cancellable: the server terminates it. RocketCEA's
machine-wide lock (`nova.lock`, held through msvcrt.locking) is released by the operating
system when the process ends, so a cancelled run does not block the next one.

On success the worker pickles the Nozzle to `novaWebResult.pkl` in the run's output folder,
after generateNozzle has returned, so the pickle carries every attribute the run set. The
server unpickles it to draw the views.

Messages put on the queue:

    ('log', str)
    ('status', (state, detail))
    ('progress', (fraction, ceiling, label))
    ('result', dict)        terminal: ok, runName, outputDir, picklePath, elapsedSec, error, traceback

Author: Sean Bowman
Date:   11/16/2026

'''

# Standard library imports
import os
import queue

resultPickleName = 'novaWebResult.pkl'

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
        # The runner reads the palette mode from novaGui.theme. Binding it needs no Tk root.
        from novaGui import theme
        theme._bindPalette(mode)
        from novaGui.runner import PipelineRunner
    except BaseException as exc:                           # noqa: BLE001 -- report every failure
        import traceback
        eventQueue.put(('result', {'ok': False, 'runName': '', 'outputDir': '', 'picklePath': '',
                                   'elapsedSec': 0.0, 'error': f'{type(exc).__name__}: {exc}',
                                   'traceback': traceback.format_exc()}))
        return

    local = queue.Queue()
    runner = PipelineRunner(local)
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
            'error':      payload.error,
            'traceback':  payload.traceback,
        }
        if payload.ok:
            summary['picklePath'] = _pickleNozzle(payload.nozzle, outputDir, eventQueue)
        eventQueue.put(('result', summary))
        break

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
