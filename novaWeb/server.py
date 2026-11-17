
# -- NOVA Web Server -- #

'''

The HTTP interface between the React front end and NOVA.

Routes, all under /api:

    GET  /health                    liveness, and whether the view machinery has loaded
    GET  /brand/{name}              the plume mark (bannerDark, bannerLight) and the icon
    GET  /settings                  saved preferences (novaGui.settings: the theme mode)
    PUT  /settings                  save preferences
    GET  /schema                    the Design form (novaWeb.schemaJson.serializeSchema)
    POST /schema/state              rows and sections a config hides, sections it opens
    GET  /examples/{name}           a shipped example engine's config, merged over the defaults
    POST /runs                      start a run: {'config': {...}, 'mode': 'dark'|'light'}
    POST /runs/cancel               terminate the running worker
    GET  /runs/state                the session snapshot
    GET  /runs/events               Server-Sent Events: a snapshot, then every run event
    GET  /views                     the view list, and the keys the last good run produced
    GET  /views/{key}/interactive   a view's plotly figure JSON, ?mode=
    GET  /views/{key}/static        a view's Matplotlib PNG, ?mode=&width=&height=&ratio=
    GET  /analysis                  the last good run's result table (novaWeb.analysis)
    GET  /export                    the output categories, the default output folder, the run's files
    GET  /export/target             the folder an export writes to, ?base=&name=
    POST /export                    copy files: {'baseDir': str, 'files': [base names]}
    POST /export/open               open {'what': 'file', 'name'} or {'what': 'folder', 'baseDir'}

Everything else is the built front end (novaWeb/frontend/dist), with index.html for any path
that is not a file, so a reload on a client route still opens the app. index.html goes out with
the saved theme mode already on its root element, so the first paint is in the right palette.

Preferences are the Tkinter front end's own file (`%APPDATA%/NOVA/guiSettings.json`), so a mode
chosen in either front end opens the other in it.

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
from novaGui import settings as guiSettings
from . import analysis
from . import outputs
from . import schemaJson
from . import views
from .session import RunSession

frontendDist = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend', 'dist')

# The plume mark in each mode and the window icon. Only these names are served.
_assetFolder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'novaGui', 'assets')
brandFiles = {
    'bannerDark':  os.path.join(_assetFolder, 'plumeBanner.png'),
    'bannerLight': os.path.join(_assetFolder, 'plumeBannerLight.png'),
    'icon':        os.path.join(_assetFolder, 'icon', 'icon64.png'),
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
        if isinstance(body, dict) and body.get('themeMode') in guiSettings.themeModes:
            current['themeMode'] = body['themeMode']
            guiSettings.save(current)
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
        return schemaJson.formState(config)

    @app.get('/api/examples/{name}')
    def example(name: str) -> dict:

        path = schemaJson.examplePath(name)
        if path is None:
            raise HTTPException(404, f'no shipped example named {name!r}')
        with open(path, encoding = 'utf-8') as handle:
            loaded = json.load(handle)
        return {**schema()['defaults'], **loaded}

    # -- Runs -- #
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
    def _nozzle():

        record = app.state.session.result
        nozzle = record.nozzle() if record is not None else None
        if nozzle is None:
            raise HTTPException(404, 'no finished run to draw')
        return nozzle

    @app.get('/api/views')
    def viewIndex() -> dict:

        record = app.state.session.result
        return {'views': views.viewList(), 'available': views.availableViews(record),
                'runId': record.runId if record is not None and record.ok else None}

    @app.get('/api/views/{key}/interactive')
    def interactiveView(key: str, mode: str = 'dark') -> Response:

        figure = views.interactiveFigure(_nozzle(), key, _mode(mode))
        if figure is None:
            raise HTTPException(404, f'{key} has no interactive rendering for this run')
        return Response(figure, media_type = 'application/json')

    @app.get('/api/views/{key}/static')
    def staticView(key: str, mode: str = 'dark', width: int = Query(900, ge = 100, le = 8000),
                   height: int = Query(600, ge = 100, le = 8000),
                   ratio: float = Query(1.0, ge = 0.5, le = 4.0)) -> Response:

        drawn = views.staticFigure(_nozzle(), key, _mode(mode), width, height, ratio)
        if 'message' in drawn:
            return JSONResponse({'message': drawn['message']})
        return Response(drawn['png'], media_type = 'image/png', headers = {'Cache-Control': 'no-store'})

    # -- Analyze -- #
    analysisCache = {}

    @app.get('/api/analysis')
    def analysisTable() -> dict:

        record = app.state.session.result
        if record is None or not record.ok:
            return {'runId': None, 'runName': '', 'summary': '', 'sections': []}
        if analysisCache.get('runId') != record.runId:
            try:
                table = analysis.resultTable(_nozzle())
            except HTTPException:
                raise
            except Exception as exc:                       # noqa: BLE001 -- report the table's failure
                raise HTTPException(500, f'the result table failed: {type(exc).__name__}: {exc}') from exc
            analysisCache.clear()
            analysisCache.update(runId = record.runId, table = table)
        return {'runId': record.runId, 'runName': record.runName, **analysisCache['table']}

    # -- Export -- #
    def _finishedRun():

        record = app.state.session.result
        if record is None or not record.ok:
            raise HTTPException(404, 'no finished run to export')
        return record

    @app.get('/api/export')
    def exportIndex() -> dict:

        record = app.state.session.result
        finished = record is not None and record.ok
        return {'categories': outputs.categories(), 'defaultBaseDir': outputs.defaultBaseDir(),
                'runId': record.runId if finished else None, 'runName': record.runName if finished else '',
                'files': outputs.listing(record) if finished else []}

    @app.get('/api/export/target')
    def exportTarget(base: str = '', name: str = '') -> dict:

        target = outputs.targetFolder(base, name)
        return {'target': target, 'exists': os.path.isdir(target)}

    @app.post('/api/export')
    async def exportFiles(request: Request) -> dict:

        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get('files'), list):
            raise HTTPException(400, 'the body must carry a list of files')
        record = _finishedRun()
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
        if what == 'file':
            path = outputs.runFiles(_finishedRun()).get(str(body.get('name', '')))
        elif what == 'folder':
            record = app.state.session.result
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
