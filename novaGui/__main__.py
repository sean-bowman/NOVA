
# -- NOVA GUI Launcher -- #

'''

Start the NOVA GUI's server and open the front end.

    python -m novaGui               desktop window (pywebview hosting WebView2)
    python -m novaGui --browser     the system browser instead of a window
    python -m novaGui --api         the API alone on port 8765, for the Vite dev server

The server listens on 127.0.0.1 at a free port, except in --api mode, where the Vite dev
server's proxy expects 8765. Closing the window stops the server and terminates any run in
progress, removing its folder; the finished runs stay in the run store (novaGui.runStore) for the
next launch. In --browser and --api mode, Ctrl+C does.

Run results go to multiprocessing workers started with 'spawn', which re-import this module in
each child; the `__main__` guard keeps a child from starting a server of its own.

In the window, the page reaches two native calls through pywebview's JavaScript bridge:
`window.pywebview.api.browseFolder`, which opens the folder picker the Export dialog's Browse
button uses, and `openWindow`, which opens a figure in a window of its own for a second monitor.
Those windows close with the main one. A browser has no such bridge: the Export dialog then takes
a typed folder alone, and a figure pops out into a browser window instead.

Under pythonw (novaGui.bat) there is no console: sys.stdout and sys.stderr are None, and
uvicorn's log setup fails on them. The launcher then writes both to `<temp>/NOVA/novaGui.log`,
replaced at each launch, which also keeps the traceback of a failed start.

Author: Sean Bowman
Date:   11/16/2026

'''

# Standard library imports
import argparse
import os
import socket
import sys
import tempfile
import threading
import time
import webbrowser

devApiPort = 8765

def _consoleOrLogFile() -> None:

    '''Give a windowless process (pythonw) somewhere to write: a log file in place of the console.'''

    if sys.stdout is not None and sys.stderr is not None:
        return
    folder = os.path.join(tempfile.gettempdir(), 'NOVA')
    os.makedirs(folder, exist_ok = True)
    handle = open(os.path.join(folder, 'novaGui.log'), 'w', encoding = 'utf-8', buffering = 1)
    sys.stdout = sys.stdout or handle
    sys.stderr = sys.stderr or handle

def _freePort() -> int:

    '''A port on 127.0.0.1 nothing is listening on.'''

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]

def _serve(app, port: int):

    '''A uvicorn server for `app` on 127.0.0.1:`port`, not yet running.'''

    import uvicorn

    config = uvicorn.Config(app, host = '127.0.0.1', port = port, log_level = 'warning')
    return uvicorn.Server(config)

def _waitUntilStarted(server, timeoutSec: float = 20.0) -> bool:

    deadline = time.monotonic() + timeoutSec
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    return server.started

class WindowApi:

    '''

    The calls the page can make into the window through pywebview's bridge. pywebview exposes the
    public methods; the window is held privately so the bridge does not walk into it.

    '''

    def __init__(self):

        self._window = None
        self._base = ''

    def openWindow(self, path: str, title: str = 'NOVA') -> bool:

        '''

        Open a page of the app in a second window: a figure popped out of the result pane. `path` is
        the page's path and query on this server; anything else is refused.

        '''

        import webview

        if self._window is None or not isinstance(path, str) or not path.startswith('/') or path.startswith('//'):
            return False
        mode = guiSettingsMode()
        webview.create_window(str(title)[:120] or 'NOVA', self._base.rstrip('/') + path, width = 1100, height = 760,
                              min_size = (560, 420), background_color = _background(mode), text_select = True)
        return True

    def _closeOthers(self) -> None:

        '''Close every window but the main one, when the main one closes.'''

        import webview

        for window in list(webview.windows):
            if window is not self._window:
                try:
                    window.destroy()
                except Exception:                          # noqa: BLE001 -- it may be closing already
                    pass

    def browseFolder(self, initial: str = '') -> str:

        '''The folder the user picks in the native dialog, or '' when they cancel.'''

        import webview

        if self._window is None:
            return ''
        directory = initial if initial and os.path.isdir(initial) else ''
        chosen = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory = directory)
        if not chosen:
            return ''
        return str(chosen[0] if isinstance(chosen, (list, tuple)) else chosen)

def guiSettingsMode() -> str:

    '''The saved theme mode, for a new window's background before its page paints.'''

    from . import settings as guiSettings

    return guiSettings.load()['themeMode']

def _background(mode: str) -> str:

    return '#E8E9EA' if mode == 'light' else '#1C1E22'

def main(argv: list | None = None) -> int:

    '''

    Parse the command line, start the server and open the front end.

    Returns:
    --------
    int : process exit code

    '''

    parser = argparse.ArgumentParser(prog = 'python -m novaGui', description = 'NOVA nozzle designer')
    parser.add_argument('--browser', action = 'store_true', help = 'open in the system browser, not a window')
    parser.add_argument('--api', action = 'store_true', help = f'serve the API alone on port {devApiPort}')
    parser.add_argument('--port', type = int, default = None, help = 'port to listen on')
    _consoleOrLogFile()
    options = parser.parse_args(argv)

    # Before anything imports NOVA: write figures, open no windows or browser tabs
    os.environ.setdefault('NOVA_HEADLESS', '1')

    from . import settings as guiSettings
    from .server import createApp, frontendDist
    from .session import clearStaging

    clearStaging()
    app = createApp()
    session = app.state.session

    port = options.port or (devApiPort if options.api else _freePort())
    server = _serve(app, port)
    url = f'http://127.0.0.1:{port}/'

    if not options.api and not os.path.isfile(os.path.join(frontendDist, 'index.html')):
        print('The front end is not built. Run `npm install` and `npm run build` in novaGui/frontend, '
              'or start the API with --api and the Vite dev server with `npm run dev`.', file = sys.stderr)
        return 1

    if options.api or options.browser:
        if options.browser:
            threading.Thread(target = lambda: _waitUntilStarted(server) and webbrowser.open(url),
                             daemon = True).start()
        else:
            print(f'NOVA API on {url}api/ (Ctrl+C to stop)')
        try:
            server.run()
        finally:
            session.shutdown()
        return 0

    import webview

    thread = threading.Thread(target = server.run, name = 'novaServer', daemon = True)
    thread.start()
    if not _waitUntilStarted(server):
        print('The NOVA server did not start.', file = sys.stderr)
        session.shutdown()
        return 1

    # The window opens on the palette's background, so it does not flash white before the page paints
    mode = guiSettings.load()['themeMode']
    bridge = WindowApi()
    bridge._base = url
    bridge._window = webview.create_window('NOVA', url, width = 1480, height = 940, min_size = (1040, 680),
                                           background_color = _background(mode), text_select = True, js_api = bridge)
    bridge._window.events.closed += bridge._closeOthers
    # Downloads carry saved configs out of the window
    webview.settings['ALLOW_DOWNLOADS'] = True
    webview.start()

    server.should_exit = True
    thread.join(timeout = 5.0)
    session.shutdown()

    return 0

if __name__ == '__main__':
    sys.exit(main())
