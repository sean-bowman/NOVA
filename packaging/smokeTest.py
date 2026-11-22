# -- NOVA: Smoke Test of the Standalone Build -- #

'''

Runs the built NOVA.exe from a working folder outside the checkout and drives it through its API,
as the window would:

    the server starts (--api, on a free port) and its views are ready
    it names what runs, the standalone build at the checkout's version, in its health route and as
    the first line of its log
    its update check reaches GitHub, so the frozen TLS stack works; this check needs the network
    the Design form's schema loads, with the shipped configuration behind it
    every validation model's passages, read from the bundled records, match the checkout's
    the shipped nozzle runs to the end in a worker process (NOVA.exe started again by spawn)
    the finished run draws an interactive (plotly) and a static (Matplotlib) figure
    the run's report renders
    exports default to a folder outside the build, the user's Documents

Usage:

    python packaging/smokeTest.py [path to NOVA.exe]    (default dist/NOVA/NOVA.exe)

Exits 0 when every check passes. The exe keeps its runs in a run store of its own, in a temporary
folder removed after (NOVA_RUN_STORE), so the user's stored runs are left alone. The exe's output
is in <temp>/NOVA/novaGui.log.

Author: Sean Bowman
Date:   11/21/2026

'''

# Standard library imports
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root)

import novaGui
from novaGui import validationStatus

runTimeoutSec = 900.0

def _freePort() -> int:

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]

class Client:

    '''Requests to the exe's API on 127.0.0.1.'''

    def __init__(self, port: int):

        self.base = f'http://127.0.0.1:{port}/api'

    def get(self, path: str, timeoutSec: float = 120.0) -> tuple:

        '''(content type, body bytes) of a GET.'''

        with urllib.request.urlopen(self.base + path, timeout = timeoutSec) as response:
            return response.headers.get('Content-Type', ''), response.read()

    def json(self, path: str, body: dict | None = None) -> dict:

        data = None if body is None else json.dumps(body).encode('utf-8')
        request = urllib.request.Request(self.base + path, data = data, method = 'GET' if body is None else 'POST',
                                         headers = {'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout = 120) as response:
            return json.loads(response.read())

def _check(condition: bool, message: str) -> None:

    '''Print the check; on a failure, print the end of the exe's log, where its traceback is, and stop.'''

    print(('ok    ' if condition else 'FAIL  ') + message, flush = True)
    if not condition:
        log = os.path.join(tempfile.gettempdir(), 'NOVA', 'novaGui.log')
        if os.path.isfile(log):
            with open(log, encoding = 'utf-8', errors = 'replace') as handle:
                print(f'--- end of {log} ---', *handle.readlines()[-40:], sep = '', flush = True)
        raise SystemExit(1)

def _firstLogLine() -> str:

    log = os.path.join(tempfile.gettempdir(), 'NOVA', 'novaGui.log')
    if not os.path.isfile(log):
        return ''
    with open(log, encoding = 'utf-8', errors = 'replace') as handle:
        return handle.readline().rstrip('\n')

def _waitForServer(client: Client, process: subprocess.Popen, timeoutSec: float = 180.0) -> dict:

    deadline = time.monotonic() + timeoutSec
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            health = client.json('/health')
            if health.get('viewsReady'):
                return health
        except OSError:
            pass
        time.sleep(0.5)
    return {}

def _runShippedNozzle(client: Client) -> dict:

    with open(os.path.join(root, 'src', 'NOVA', 'assets', 'NOVANozzle.json'), encoding = 'utf-8') as handle:
        config = json.load(handle)
    submitted = client.json('/runs', {'config': config, 'mode': 'dark'})
    started = time.monotonic()
    while time.monotonic() - started < runTimeoutSec:
        result = client.json('/runs/state').get('result') or {}
        if result.get('runId') == submitted['runId']:
            return {**result, 'wallSec': time.monotonic() - started}
        time.sleep(2.0)
    return {'runId': submitted['runId'], 'ok': False, 'error': f'no result in {runTimeoutSec:.0f} s'}

def _figures(client: Client, runId: int) -> tuple:

    '''The first available view that draws interactively, and the first that draws as a PNG.'''

    available = client.json(f'/views?run={runId}')['available']
    interactive = static = None
    for key in available:
        if interactive is None:
            try:
                kind, body = client.get(f'/views/{key}/interactive?run={runId}')
                if 'json' in kind and 'data' in json.loads(body):
                    interactive = key
            except urllib.error.HTTPError:
                pass
        if static is None:
            kind, body = client.get(f'/views/{key}/static?run={runId}')
            if kind.startswith('image/png') and body[:8] == b'\x89PNG\r\n\x1a\n':
                static = key
        if interactive and static:
            break
    return available, interactive, static

def main(argv: list) -> int:

    exe = os.path.abspath(argv[0] if argv else os.path.join(root, 'dist', 'NOVA', 'NOVA.exe'))
    _check(os.path.isfile(exe), f'the build is at {exe}')
    port = _freePort()
    client = Client(port)
    store = tempfile.mkdtemp(prefix = 'novaSmokeStore')
    process = subprocess.Popen([exe, '--api', '--port', str(port)], cwd = tempfile.gettempdir(),
                               env = {**os.environ, 'NOVA_RUN_STORE': store})
    try:
        started = time.monotonic()
        health = _waitForServer(client, process)
        _check(bool(health), f'the server starts ({time.monotonic() - started:.1f} s)')

        named = (health.get('build') == 'standalone' and health.get('version') == novaGui.__version__
                 and _firstLogLine() == health.get('label'))
        _check(named, f'the exe names what runs, in its health route and first log line: {health.get("label")}')

        # Any answer from GitHub, its hourly limit included, shows the frozen TLS stack works
        update = client.json('/updates')
        status = update.get('status', 'unreachable')
        _check(status != 'unreachable', f'the update check reaches GitHub ({status}) {update.get("detail", "")}')

        schema = client.json('/schema')
        _check(bool(schema), 'the Design form schema loads')

        summary = validationStatus.load()
        models = list(summary['models'])
        mismatched = [model for model in models
                      if client.json(f'/validation/{model}')['passages'] != validationStatus.passages(model, summary)]
        _check(mismatched == [], f'the {len(models)} validation models read their records as the checkout does '
                                 f'{mismatched or ""}')

        result = _runShippedNozzle(client)
        runId, wallSec, error = result['runId'], result.get('wallSec', 0.0), result.get('error') or ''
        _check(bool(result.get('ok')), f'the shipped nozzle runs ({wallSec:.0f} s) {error}')

        available, interactive, static = _figures(client, runId)
        _check(interactive is not None, f'an interactive figure draws ({interactive}; {len(available)} views)')
        _check(static is not None, f'a static figure draws ({static})')

        kind, page = client.get(f'/report?run={runId}', timeoutSec = 300.0)
        _check('html' in kind and len(page) > 10000, f'the report renders ({len(page) / 1e6:.1f} MB)')

        exports = os.path.normcase(client.json(f'/export?run={runId}')['defaultBaseDir'])
        inside = exports.startswith(os.path.normcase(os.path.dirname(exe)) + os.sep)
        _check(not inside and os.path.basename(exports) == 'nova', f'exports go to {exports}')
    finally:
        # The worker processes are the exe's children: take the whole tree down
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(process.pid)], capture_output = True)
        process.wait(timeout = 30)
        shutil.rmtree(store, ignore_errors = True)
    print('smoke test passed')
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
