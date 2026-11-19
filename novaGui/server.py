
# -- NOVA GUI Server -- #

'''

The HTTP interface between the React front end and NOVA.

Routes, all under /api:

    GET  /health                    liveness, and whether the view machinery has loaded
    GET  /brand/{name}              the plume mark (bannerDark, bannerLight) and the icon
    GET  /settings                  saved preferences (novaGui.settings: theme mode, form width)
    PUT  /settings                  save preferences
    GET  /schema                    the Design form (novaGui.schemaJson.serializeSchema)
    POST /schema/state              rows and sections a config hides, sections it opens, and its
                                    cross-field problems and the rows they name (novaGui.design)
    GET  /examples/{name}           a shipped example engine's config, merged over the defaults
    GET  /materials/wall            a wall alloy's sampled properties, ?name=&temperatureK=
    GET  /materials/extension       an extension material's store entry: the note and the fill, ?name=
    GET  /runs                      the kept runs, newest first, the baseline, and the run in progress
    POST /runs                      start a run: {'config': {...}, 'mode': 'dark'|'light'}
    PUT  /runs/baseline             make a kept run the baseline: {'runId': int | None}
    POST /runs/cancel               terminate the running worker
    GET  /runs/state                the session snapshot
    GET  /runs/events               Server-Sent Events: a snapshot, then every run event
    GET  /views                     the view list, the keys a run produced, and that run's id, name,
                                    time and config, ?run=
    GET  /views/{key}/interactive   a view's plotly figure JSON, ?mode=&run=&compare=
    GET  /views/{key}/static        a view's Matplotlib PNG, ?mode=&run=&width=&height=&ratio=
    GET  /analysis                  a run's result table (novaGui.analysis), ?run=&baseline=
    GET  /export                    the output categories, the default output folder, a run's files,
                                    ?run=
    GET  /export/target             the folder an export writes to, ?base=&name=
    GET  /export/file               one of a run's files, for a preview, ?run=&name=
    GET  /export/mesh               one of a run's STL files as vertices and triangles, ?run=&name=
    POST /export                    copy files: {'runId': int, 'baseDir': str, 'files': [base names]}
    POST /export/open               open {'what': 'file', 'runId', 'name'} or {'what': 'folder', 'baseDir'}

`run` names a kept run (novaGui.session); without it a route answers for the latest good run. The
run in progress answers /views and /views/{key}/interactive with the figures its contour stage
settled, once the worker has sent them. `compare` draws a second kept run over a line plot, and
`baseline` sets a second run's table beside the first (novaGui.analysis.compareTables).

Everything else is the built front end (novaGui/frontend/dist), with index.html for any path
that is not a file, so a reload on a client route still opens the app. index.html goes out with
the saved theme mode already on its root element, so the first paint is in the right palette.

Preferences are kept in `%APPDATA%/NOVA/guiSettings.json` (novaGui.settings), the file the legacy
Tkinter front end reads too, so a mode chosen in either front end opens the other in it. A save is
sent to every window on the event stream, so a figure popped out into a second window follows the
theme mode of the first.

The server binds to 127.0.0.1 only. It runs NOVA on whatever config it is sent, unpickles its
own run results, copies a run's outputs into whatever folder it is given and opens a run's files
in the desktop's applications; it is not meant to face a network.

Author: Sean Bowman
Date:   11/16/2026

'''

# Standard library imports
import asyncio
import contextlib
import json
import os

# Third-party imports
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Local imports
from . import analysis
from . import assetFolder
from . import design
from . import outputs
from . import schemaJson
from . import views
from . import settings as guiSettings
from .session import RunSession

frontendDist = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend', 'dist')

# The plume mark in each mode and the window icon. Only these names are served.
brandFiles = {
    'bannerDark':  os.path.join(assetFolder, 'plumeBanner.png'),
    'bannerLight': os.path.join(assetFolder, 'plumeBannerLight.png'),
    'icon':        os.path.join(assetFolder, 'icon', 'icon64.png'),
}

modes = ('dark', 'light')

def _mode(value: str) -> str:

    if value not in modes:
        raise HTTPException(400, f'mode must be one of {", ".join(modes)}')
    return value

def createApp(session: RunSession | None = None, warm: bool = True) -> FastAPI:

    '''

    Build the application around one run session.

    Parameters:
    -----------
    session : RunSession, optional
        The session to serve; a new one by default.
    warm : bool
        Load NOVA and the view machinery on a background thread at startup, so the first figure
        does not wait on the imports.

    Returns:
    --------
    FastAPI : the application

    '''

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        if warm:
            asyncio.get_running_loop().run_in_executor(None, views.warmUp)
        yield

    app = FastAPI(title = 'NOVA', docs_url = '/api/docs', openapi_url = '/api/openapi.json', lifespan = lifespan)
    app.state.session = session if session is not None else RunSession()

    schemaCache = {}

    # -- Health -- #
    @app.get('/api/health')
    def health() -> dict:

        return {'ok': True, 'viewsReady': views.ready()}

    # -- Settings -- #
    @app.get('/api/settings')
    def getSettings() -> dict:

        return guiSettings.load()

    @app.put('/api/settings')
    async def putSettings(request: Request) -> dict:

        body = await request.json()
        current = guiSettings.load()
        changes = guiSettings.clean(body)
        if changes:
            current.update(changes)
            guiSettings.save(current)
            app.state.session.publish({'type': 'settings', **current})
        return current

    # -- Brand images, from the Tkinter front end's assets -- #
    @app.get('/api/brand/{name}')
    def brand(name: str) -> FileResponse:

        path = brandFiles.get(name)
        if path is None or not os.path.isfile(path):
            raise HTTPException(404)
        return FileResponse(path, headers = {'Cache-Control': 'max-age=86400'})

    # -- Schema -- #
    @app.get('/api/schema')
    def schema() -> dict:

        if 'schema' not in schemaCache:
            schemaCache['schema'] = schemaJson.serializeSchema()
        return schemaCache['schema']

    @app.post('/api/schema/state')
    async def schemaState(request: Request) -> dict:

        config = await request.json()
        if not isinstance(config, dict):
            raise HTTPException(400, 'the body must be a config object')
        # The checks read the material store, a file read the first time, so they run off the loop
        checks = await asyncio.get_running_loop().run_in_executor(None, design.checks, config)
        return {**schemaJson.formState(config), **checks}

    @app.get('/api/examples/{name}')
    def example(name: str) -> dict:

        path = schemaJson.examplePath(name)
        if path is None:
            raise HTTPException(404, f'no shipped example named {name!r}')
        with open(path, encoding = 'utf-8') as handle:
            loaded = json.load(handle)
        return {**schema()['defaults'], **loaded}

    # -- Materials -- #
    @app.get('/api/materials/wall')
    def wallMaterial(name: str = 'GRCop-42', temperatureK: float = Query(300.0, gt = 0.0, le = 5000.0)) -> dict:

        try:
            return design.wallSample(name, temperatureK)
        except Exception as exc:                           # noqa: BLE001 -- the panel shows the reason
            raise HTTPException(500, f'material data unavailable: {exc}') from exc

    @app.get('/api/materials/extension')
    def extensionMaterial(name: str) -> dict:

        return design.extensionEntry(name)

    # -- Runs -- #
    @app.get('/api/runs')
    def runList() -> dict:

        return app.state.session.runList()

    @app.put('/api/runs/baseline')
    async def setBaseline(request: Request) -> dict:

        body = await request.json()
        runId = body.get('runId') if isinstance(body, dict) else None
        if runId is not None and (isinstance(runId, bool) or not isinstance(runId, int)):
            raise HTTPException(400, 'runId must be a run id or null')
        try:
            app.state.session.setBaseline(runId)
        except KeyError as exc:
            raise HTTPException(404, f'run {runId} is not kept') from exc
        return {'baseline': runId}

    @app.post('/api/runs')
    async def startRun(request: Request) -> dict:

        body = await request.json()
        config = body.get('config') if isinstance(body, dict) else None
        if not isinstance(config, dict):
            raise HTTPException(400, 'the body must carry a config object')
        mode = _mode(body.get('mode', 'dark'))
        try:
            runId = app.state.session.start(config, mode)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {'runId': runId}

    @app.post('/api/runs/cancel')
    def cancelRun() -> dict:

        return {'cancelled': app.state.session.cancel()}

    @app.get('/api/runs/state')
    def runState() -> dict:

        return app.state.session.snapshot()

    @app.get('/api/runs/events')
    async def runEvents(request: Request) -> StreamingResponse:

        session = app.state.session
        target = session.subscribe()

        async def stream():
            try:
                yield f'data: {json.dumps(session.snapshot())}\n\n'
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(target.get(), timeout = 15.0)
                    except asyncio.TimeoutError:
                        # A comment line keeps the connection open through idle stretches
                        yield ': keep-alive\n\n'
                        continue
                    yield f'data: {json.dumps(event)}\n\n'
            finally:
                session.unsubscribe(target)

        return StreamingResponse(stream(), media_type = 'text/event-stream',
                                 headers = {'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    # -- Views -- #
    def _record(run: int | None):

        '''A kept run by id, else the latest good run; 404 when there is none.'''

        record = app.state.session.record(run)
        if record is None:
            raise HTTPException(404, f'run {run} is not kept' if run is not None else 'no finished run to draw')
        return record

    def _nozzle(run: int | None):

        record = _record(run)
        nozzle = app.state.session.nozzle(record)
        if nozzle is None:
            raise HTTPException(404, 'no finished run to draw')
        return nozzle

    def _running(run: int | None) -> bool:

        '''Whether `run` is the run in progress.'''

        session = app.state.session
        return run is not None and session.busy and session.state['runId'] == run

    @app.get('/api/views')
    def viewIndex(run: int | None = None) -> dict:

        session = app.state.session
        listed = views.viewList()
        if _running(run):
            partial = session.runList()['running']
            available = [spec['key'] for spec in listed if spec['key'] in partial['views']]
            config = partial['config'] or {}
            return {'views': listed, 'available': available, 'runId': run, 'runName': str(config.get('filename') or ''),
                    'elapsedSec': None, 'config': partial['config'], 'partial': True}
        record = session.record(run)
        finished = record is not None and record.ok
        return {'views': listed, 'available': views.availableViews(record) if finished else [],
                'runId': record.runId if finished else None,
                'runName': record.runName if finished else '',
                'elapsedSec': record.elapsedSec if finished else None,
                'config': record.config if finished else None, 'partial': False}

    @app.get('/api/views/{key}/interactive')
    def interactiveView(key: str, mode: str = 'dark', run: int | None = None, compare: int | None = None) -> Response:

        mode = _mode(mode)
        if _running(run):
            figure = views.partialFigure(app.state.session.partialFigure(run, key), key, mode)
            if figure is None:
                raise HTTPException(404, f'{key} is not drawn until run {run} finishes')
            return Response(figure, media_type = 'application/json')

        record = _record(run)
        nozzle = _nozzle(record.runId)
        other = None
        labels = (f'run {record.runId}', 'the compared run')
        if compare is not None and compare != record.runId:
            other = _nozzle(compare)
            baseline = app.state.session.baseline
            labels = (f'run {record.runId}', f'run {compare}, baseline' if compare == baseline else f'run {compare}')
        figure = views.interactiveFigure(nozzle, key, mode, compare = other, labels = labels)
        if figure is None:
            raise HTTPException(404, f'{key} has no interactive rendering for this run')
        return Response(figure, media_type = 'application/json')

    @app.get('/api/views/{key}/static')
    def staticView(key: str, mode: str = 'dark', run: int | None = None, width: int = Query(900, ge = 100, le = 8000),
                   height: int = Query(600, ge = 100, le = 8000),
                   ratio: float = Query(1.0, ge = 0.5, le = 4.0)) -> Response:

        drawn = views.staticFigure(_nozzle(run), key, _mode(mode), width, height, ratio)
        if 'message' in drawn:
            return JSONResponse({'message': drawn['message']})
        return Response(drawn['png'], media_type = 'image/png', headers = {'Cache-Control': 'no-store'})

    # -- Result table -- #
    tables = {}                     # runId: result table, for the kept runs drawn from lately

    def _table(record) -> dict:

        if record.runId not in tables:
            try:
                table = analysis.resultTable(_nozzle(record.runId))
            except HTTPException:
                raise
            except Exception as exc:                       # noqa: BLE001 -- report the table's failure
                raise HTTPException(500, f'the result table failed: {type(exc).__name__}: {exc}') from exc
            kept = set(app.state.session.runs)
            for runId in [runId for runId in tables if runId not in kept]:
                del tables[runId]
            tables[record.runId] = table
        return tables[record.runId]

    @app.get('/api/analysis')
    def analysisTable(run: int | None = None, baseline: int | None = None) -> dict:

        record = app.state.session.record(run)
        if record is None or not record.ok:
            if run is not None:
                raise HTTPException(404, f'run {run} is not kept')
            return {'runId': None, 'runName': '', 'summary': '', 'headline': [], 'sections': [], 'baselineRun': None}
        table = _table(record)
        if baseline is not None and baseline != record.runId:
            table = analysis.compareTables(table, _table(_record(baseline)))
        return {'runId': record.runId, 'runName': record.runName,
                'baselineRun': baseline if baseline is not None and baseline != record.runId else None, **table}

    # -- Export -- #
    def _finishedRun(run: int | None):

        record = app.state.session.record(run)
        if record is None or not record.ok:
            raise HTTPException(404, 'no finished run to export')
        return record

    def _runFile(run: int | None, name: str) -> str:

        '''The path of one of a run's listed files, by base name; 404 for any other name.'''

        path = outputs.runFiles(_finishedRun(run)).get(str(name))
        if path is None or not os.path.isfile(path):
            raise HTTPException(404, f'{name} is not one of the run\'s files')
        return path

    @app.get('/api/export')
    def exportIndex(run: int | None = None) -> dict:

        record = app.state.session.record(run)
        finished = record is not None and record.ok
        files = outputs.listing(record) if finished else []
        for entry in files:
            entry['preview'] = outputs.previewKind(entry['name'])
        return {'categories': outputs.categories(), 'defaultBaseDir': outputs.defaultBaseDir(),
                'runId': record.runId if finished else None, 'runName': record.runName if finished else '',
                'files': files}

    @app.get('/api/export/target')
    def exportTarget(base: str = '', name: str = '') -> dict:

        target = outputs.targetFolder(base, name)
        return {'target': target, 'exists': os.path.isdir(target)}

    @app.get('/api/export/file')
    def exportFile(name: str, run: int | None = None) -> Response:

        path = _runFile(run, name)
        kind = outputs.previewKind(name)
        if kind == 'image':
            return FileResponse(path, headers = {'Cache-Control': 'no-store'})
        if kind == 'text':
            with open(path, 'rb') as handle:
                head = handle.read(outputs.previewTextBytes)
            return JSONResponse({'text': head.decode('utf-8', errors = 'replace'),
                                 'bytes': os.path.getsize(path), 'cut': os.path.getsize(path) > len(head)})
        raise HTTPException(400, f'{name} has no preview')

    @app.get('/api/export/mesh')
    async def exportMesh(name: str, run: int | None = None) -> dict:

        path = _runFile(run, name)
        if outputs.previewKind(name) != 'mesh':
            raise HTTPException(400, f'{name} is not an STL surface')
        try:
            return await asyncio.get_running_loop().run_in_executor(None, outputs.stlMesh, path)
        except (OSError, ValueError) as exc:
            raise HTTPException(400, f'{name} could not be read: {exc}') from exc

    @app.post('/api/export')
    async def exportFiles(request: Request) -> dict:

        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get('files'), list):
            raise HTTPException(400, 'the body must carry a list of files')
        runId = body.get('runId')
        record = _finishedRun(runId if isinstance(runId, int) and not isinstance(runId, bool) else None)
        names = [str(name) for name in body['files']]
        try:
            return await asyncio.get_running_loop().run_in_executor(
                None, outputs.export, record, str(body.get('baseDir') or ''), names)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError as exc:
            target = outputs.targetFolder(body.get('baseDir') or '', record.runName)
            raise HTTPException(400, f'could not write to {target}: {exc}') from exc

    @app.post('/api/export/open')
    async def exportOpen(request: Request) -> dict:

        body = await request.json()
        what = body.get('what') if isinstance(body, dict) else None
        runId = body.get('runId') if isinstance(body, dict) else None
        run = runId if isinstance(runId, int) and not isinstance(runId, bool) else None
        if what == 'file':
            path = outputs.runFiles(_finishedRun(run)).get(str(body.get('name', '')))
        elif what == 'folder':
            record = app.state.session.record(run)
            name = record.runName if record is not None and record.ok else str(body.get('name', ''))
            path = outputs.targetFolder(str(body.get('baseDir') or ''), name)
            if not os.path.isdir(path):
                path = None
        else:
            raise HTTPException(400, "what must be 'file' or 'folder'")
        if path is None or not os.path.exists(path):
            raise HTTPException(404, 'nothing there to open')
        try:
            outputs.openPath(path)
        except OSError as exc:
            raise HTTPException(400, f'could not open {path}: {exc}') from exc
        return {'opened': path}

    # -- Front end -- #
    if os.path.isdir(frontendDist):
        assets = os.path.join(frontendDist, 'assets')
        if os.path.isdir(assets):
            app.mount('/assets', StaticFiles(directory = assets), name = 'assets')

        @app.get('/{path:path}', include_in_schema = False)
        def frontend(path: str) -> FileResponse:

            if path.startswith('api/'):
                raise HTTPException(404)
            candidate = os.path.realpath(os.path.join(frontendDist, path))
            inside = candidate.startswith(os.path.realpath(frontendDist) + os.sep)
            if path and inside and os.path.isfile(candidate):
                return FileResponse(candidate)
            return _index()

    def _index() -> HTMLResponse:

        '''index.html with the saved theme mode on the root element.'''

        with open(os.path.join(frontendDist, 'index.html'), encoding = 'utf-8') as handle:
            page = handle.read()
        mode = guiSettings.load()['themeMode']
        page = page.replace('data-theme="dark"', f'data-theme="{mode}"', 1)
        return HTMLResponse(page, headers = {'Cache-Control': 'no-store'})

    return app
