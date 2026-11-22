
# -- NOVA GUI Server -- #

'''

The HTTP interface between the React front end and NOVA.

Routes, all under /api:

    GET  /health                    liveness, whether the view machinery has loaded, and what is running:
                                    the version, the build and a checkout's revision (novaGui.runningBuild)
    GET  /brand/{name}              the plume mark (bannerDark, bannerLight) and the icon
    GET  /settings                  saved preferences (novaGui.settings: theme mode, form width)
    PUT  /settings                  save preferences
    GET  /schema                    the Design form (novaGui.schemaJson.serializeSchema)
    POST /schema/state              rows and sections a config hides, sections it opens, and its
                                    cross-field problems and the rows they name (novaGui.design)
    GET  /examples/{name}           a shipped example engine's config, merged over the defaults
    GET  /materials/wall            a wall alloy's sampled properties, ?name=&temperatureK=
    GET  /materials/extension       an extension material's store entry: the note and the fill, ?name=
    GET  /runs                      the kept runs, newest first, the baseline, the run in progress, and
                                    the run store's folder and limits
    POST /runs                      queue a run, which starts now if none is going: {'config': {...},
                                    'mode': 'dark'|'light'}
    PUT  /runs/baseline             make a kept run the baseline: {'runId': int | None}
    PATCH /runs/{runId}             name a kept run or write its note: {'title': str, 'note': str}, either
    DELETE /runs/{runId}            delete a kept run and its files
    POST /runs/cancel               terminate the running worker; {'all': true} empties the queue first
    DELETE /queue/{queueId}         take a run out of the queue
    GET  /sweeps                    the trade sweeps, newest first, each point with its run's headline
                                    numbers (novaGui.sweeps)
    POST /sweeps                    queue a sweep: {'name', 'config', 'mode', 'fields': [{'key', 'unit', 'values'}]}
    POST /sweeps/{sweepId}/resume   queue a sweep's cancelled points again
    DELETE /sweeps/{sweepId}        delete a sweep, its queued points and its runs, except named runs and
                                    the baseline
    GET  /sweeps/{sweepId}/figure   one headline number against the swept field, ?number=&mode=
    GET  /sweeps/{sweepId}/report   the sweep's report as one HTML file (novaGui.report)
    GET  /report                    a run's report as one HTML file, ?run=&baseline= (novaGui.report)
    GET  /runs/state                the session snapshot
    GET  /runs/events               Server-Sent Events: a snapshot, then every run event
    GET  /views                     the view list, the keys a run produced, and that run's id, name,
                                    time and config, or why its saved result does not load, ?run=
    GET  /views/{key}/interactive   a view's plotly figure JSON, ?mode=&run=&compare=
    GET  /views/{key}/static        a view's Matplotlib PNG, ?mode=&run=&width=&height=&ratio=
    GET  /analysis                  a run's result table (novaGui.analysis), ?run=&baseline=, each headline
                                    number and section with its validation status (novaGui.validationStatus)
    GET  /validation/{model}        a model's validation status and the passages of its records that
                                    carry it
    GET  /export                    the output categories, the default output folder, a run's files,
                                    ?run=
    GET  /export/target             the folder an export writes to, ?base=&name=
    GET  /export/file               one of a run's files, for a preview, ?run=&name=
    GET  /export/mesh               one of a run's STL files as vertices and triangles, ?run=&name=
    POST /export                    copy files: {'runId': int, 'baseDir': str, 'files': [base names]}
    POST /export/open               open {'what': 'file', 'runId', 'name'} or {'what': 'folder', 'baseDir'}

`run` names a kept run (novaGui.session); without it a route answers for the latest good run. The
GUI's session keeps its runs in the run store (novaGui.runStore), so they outlast the window, and
a run's id stays its own across launches. The run in progress answers /views and
/views/{key}/interactive with the figures its contour stage settled, once the worker has sent them. `compare` draws a second kept run over a line plot, and
`baseline` sets a second run's table beside the first (novaGui.analysis.compareTables).

A view's figure is built once per run, view, palette mode and compared run, and kept while its run
is kept (`keptFigureBytes` of them, the least recently drawn going first), compressed as well as
whole, so switching views, the grid and a popped-out window draw from memory after the first
time. Every other response is compressed as it goes out when the browser accepts it. A filled flow
field is 1.5 to 2.5 MB of JSON and goes out at about a third of that; the event stream and the PNGs
are sent as they are.

Everything else is the built front end (novaGui/frontend/dist), with index.html for any path
that is not a file, so a reload on a client route still opens the app. index.html goes out with
the saved theme mode already on its root element, so the first paint is in the right palette.

Preferences are kept in `%APPDATA%/NOVA/guiSettings.json` (novaGui.settings), so the next launch
opens in the theme mode and form width last chosen. A save is sent to every window on the event
stream, so a figure popped out into a second window follows the
theme mode of the first.

The server binds to 127.0.0.1 only. It runs NOVA on whatever config it is sent, unpickles its
own run results, copies a run's outputs into whatever folder it is given and opens a run's files
in the desktop's applications; it is not meant to face a network.

Author: Sean Bowman
Date:   11/16/2026

'''

# Standard library imports
import asyncio
import collections
import contextlib
import gzip
import json
import os
import threading

# Third-party imports
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Local imports
from . import analysis
from . import assetFolder
from . import design
from . import outputs
from . import report
from . import runningBuild
from . import schemaJson
from . import sweeps
from . import validationStatus
from . import views
from . import settings as guiSettings
from .runStore import RunStore
from .session import RunSession, iterationView

frontendDist = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend', 'dist')

# The plume mark in each mode and the window icon. Only these names are served.
brandFiles = {
    'bannerDark':  os.path.join(assetFolder, 'plumeBanner.png'),
    'bannerLight': os.path.join(assetFolder, 'plumeBannerLight.png'),
    'icon':        os.path.join(assetFolder, 'icon', 'icon64.png'),
}

modes = ('dark', 'light')
keptFigureBytes = 160 * 2 ** 20     # [B] the figure JSON kept for drawing again

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
        The session to serve; by default a new one on the run store (novaGui.runStore).
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
    app.state.session = session if session is not None else RunSession(store = RunStore())
    # Level 5 compresses a field figure to about a quarter in a few tens of milliseconds; level 9
    # takes several times as long for a few percent more
    app.add_middleware(GZipMiddleware, minimum_size = 1000, compresslevel = 5)

    schemaCache = {}

    # -- Health -- #
    @app.get('/api/health')
    def health() -> dict:

        return {'ok': True, 'viewsReady': views.ready(), **runningBuild()}

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

    # -- Brand images, from novaGui/assets -- #
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

    @app.patch('/api/runs/{runId}')
    async def describeRun(runId: int, request: Request) -> dict:

        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, 'the body must be an object')
        fields = {key: body[key] for key in ('title', 'note') if key in body}
        if not fields or any(not isinstance(value, str) for value in fields.values()):
            raise HTTPException(400, 'give a title, a note or both, as text')
        try:
            record = app.state.session.describe(runId, **fields)
        except KeyError as exc:
            raise HTTPException(404, f'run {runId} is not kept') from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return record.entry()

    def _forgetDrawn(runIds: list) -> None:

        '''Drop deleted runs' figures and tables, and the figures they were drawn over.'''

        gone = set(runIds)
        with figureLock:
            for stale in [entry for entry in figureCache if entry[0] in gone or entry[4] in gone]:
                del figureCache[stale]
        for runId in gone:
            tables.pop(runId, None)

    @app.delete('/api/runs/{runId}')
    def deleteRun(runId: int) -> dict:

        try:
            app.state.session.delete(runId)
        except KeyError as exc:
            raise HTTPException(404, f'run {runId} is not kept') from exc
        _forgetDrawn([runId])
        return {'deleted': runId}

    @app.post('/api/runs')
    async def startRun(request: Request) -> dict:

        body = await request.json()
        config = body.get('config') if isinstance(body, dict) else None
        if not isinstance(config, dict):
            raise HTTPException(400, 'the body must carry a config object')
        mode = _mode(body.get('mode', 'dark'))
        return app.state.session.submit(config, mode)

    @app.post('/api/runs/cancel')
    async def cancelRun(request: Request) -> dict:

        body = await request.body()
        try:
            loaded = json.loads(body) if body else {}
        except ValueError as exc:
            raise HTTPException(400, 'the body must be JSON') from exc
        everything = isinstance(loaded, dict) and loaded.get('all') is True
        return {'cancelled': app.state.session.cancel(everything)}

    @app.delete('/api/queue/{queueId}')
    def unqueue(queueId: int) -> dict:

        if not app.state.session.unqueue(queueId):
            raise HTTPException(404, f'nothing queued as {queueId}')
        return {'unqueued': queueId}

    # -- Trade sweeps -- #
    @app.get('/api/sweeps')
    def sweepList() -> dict:

        return app.state.session.sweepList()

    @app.post('/api/sweeps')
    async def addSweep(request: Request) -> dict:

        body = await request.json()
        mode = _mode(body.get('mode', 'dark') if isinstance(body, dict) else 'dark')
        try:
            sweep = sweeps.build(body)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        added = app.state.session.addSweep(sweep, mode)
        return next(entry for entry in app.state.session.sweepList()['sweeps'] if entry['sweepId'] == added['sweepId'])

    @app.post('/api/sweeps/{sweepId}/resume')
    def resumeSweep(sweepId: int) -> dict:

        try:
            return {'queued': app.state.session.resumeSweep(sweepId)}
        except KeyError as exc:
            raise HTTPException(404, f'sweep {sweepId} is not kept') from exc

    @app.delete('/api/sweeps/{sweepId}')
    def deleteSweep(sweepId: int) -> dict:

        try:
            deleted = app.state.session.deleteSweep(sweepId)
        except KeyError as exc:
            raise HTTPException(404, f'sweep {sweepId} is not kept') from exc
        _forgetDrawn(deleted)
        return {'deleted': sweepId, 'runs': deleted}

    @app.get('/api/sweeps/{sweepId}/figure')
    def sweepFigure(sweepId: int, number: str, mode: str = 'dark') -> Response:

        try:
            figure = app.state.session.sweepFigure(sweepId, number, _mode(mode))
        except KeyError as exc:
            raise HTTPException(404, f'sweep {sweepId} is not kept') from exc
        if figure is None:
            raise HTTPException(404, f'no run of sweep {sweepId} has reported {number!r} yet')
        return Response(figure, media_type = 'application/json')

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
            raise HTTPException(404, f'run {record.runId} cannot be drawn: {record.loadError}' if record.loadError
                                else 'no finished run to draw')
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
                    'elapsedSec': None, 'config': partial['config'], 'partial': True, 'loadError': ''}
        record = session.record(run)
        finished = record is not None and record.ok
        return {'views': listed, 'available': views.availableViews(record) if finished else [],
                'runId': record.runId if finished else None,
                'runName': record.runName if finished else '',
                'elapsedSec': record.elapsedSec if finished else None,
                'config': record.config if finished else None, 'partial': False,
                'loadError': record.loadError if finished else ''}

    # (runId, partial, key, mode, compare, baseline): (figure JSON as bytes, the same gzipped)
    figureCache = collections.OrderedDict()
    figureLock = threading.Lock()
    app.state.figureCache = figureCache

    def _drawnFigure(cacheKey: tuple, build):

        '''

        A figure's JSON and its gzipped bytes from the cache, or built, compressed and kept. Figures
        of runs no longer kept, and a run's partial figures once it has ended, are dropped as others
        are kept.

        '''

        with figureLock:
            if cacheKey in figureCache:
                figureCache.move_to_end(cacheKey)
                return figureCache[cacheKey]
        figure = build()
        if figure is None:
            return None
        whole = figure.encode('utf-8')
        drawn = (whole, gzip.compress(whole, compresslevel = 5))
        session = app.state.session
        running = session.state['runId'] if session.busy else None
        with figureLock:
            figureCache[cacheKey] = drawn
            kept = set(session.runs)
            for stale in [entry for entry in figureCache
                          if (entry[1] and entry[0] != running) or (not entry[1] and entry[0] not in kept)
                          or (entry[4] is not None and entry[4] not in kept)]:
                if stale != cacheKey:
                    del figureCache[stale]
            while len(figureCache) > 1 and sum(len(a) + len(b) for a, b in figureCache.values()) > keptFigureBytes:
                figureCache.popitem(last = False)
        return drawn

    def _figureResponse(request: Request, drawn: tuple) -> Response:

        '''The figure gzipped for a browser that accepts it, which the compression middleware leaves as it is.'''

        whole, packed = drawn
        if 'gzip' in request.headers.get('accept-encoding', '').lower():
            return Response(packed, media_type = 'application/json',
                            headers = {'Content-Encoding': 'gzip', 'Vary': 'Accept-Encoding'})
        return Response(whole, media_type = 'application/json', headers = {'Vary': 'Accept-Encoding'})

    @app.get('/api/views/{key}/interactive')
    def interactiveView(request: Request, key: str, mode: str = 'dark', run: int | None = None,
                        compare: int | None = None) -> Response:

        mode = _mode(mode)
        if _running(run):
            session = app.state.session
            description = session.partialFigure(run, key)
            # The circuit view grows a pass at a time, so each pass's figure is kept under its own name
            drawnKey = f'{key}@{session.partialRevision(run)}' if key == iterationView else key
            figure = _drawnFigure((run, True, drawnKey, mode, None, None),
                                  lambda: views.partialFigure(description, key, mode)) if description is not None else None
            if figure is None:
                raise HTTPException(404, f'{key} is not drawn until run {run} finishes')
            return _figureResponse(request, figure)

        record = _record(run)
        against = compare if compare is not None and compare != record.runId else None

        def build():
            nozzle = _nozzle(record.runId)
            other = None
            labels = (f'run {record.runId}', 'the compared run')
            if against is not None:
                other = _nozzle(against)
                baseline = app.state.session.baseline
                labels = (f'run {record.runId}', f'run {against}, baseline' if against == baseline else f'run {against}')
            return views.interactiveFigure(nozzle, key, mode, compare = other, labels = labels)

        # The compared run's label names it the baseline or not, so the baseline is part of the key
        baseline = app.state.session.baseline if against is not None else None
        figure = _drawnFigure((record.runId, False, key, mode, against, baseline), build)
        if figure is None:
            raise HTTPException(404, f'{key} has no interactive rendering for this run')
        return _figureResponse(request, figure)

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
                nozzle = _nozzle(record.runId)
                table = validationStatus.annotate(analysis.resultTable(nozzle), nozzle)
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

    # -- Reports -- #
    @app.get('/api/report')
    def runReport(run: int | None = None, baseline: int | None = None) -> HTMLResponse:

        record = _finishedRun(run)
        nozzle = _nozzle(record.runId)
        table = {**_table(record), 'runId': record.runId, 'baselineRun': None}
        other = None
        if baseline is not None and baseline != record.runId:
            other = _record(baseline)
            table = {**analysis.compareTables(table, _table(other)), 'runId': record.runId, 'baselineRun': other.runId}
        page = report.runReport(record, nozzle, table, views.availableViews(record), baseline = other)
        return HTMLResponse(page, headers = {'Cache-Control': 'no-store'})

    @app.get('/api/sweeps/{sweepId}/report')
    def sweepReport(sweepId: int) -> HTMLResponse:

        session = app.state.session
        table = next((entry for entry in session.sweepList()['sweeps'] if entry['sweepId'] == sweepId), None)
        if table is None:
            raise HTTPException(404, f'sweep {sweepId} is not kept')
        # One finished run of the sweep says which models its numbers come from
        sampleTable, sampleNozzle = None, None
        sample = next((point['runId'] for point in table['points'] if point['kept']), None)
        if sample is not None:
            try:
                sampleTable, sampleNozzle = _table(_record(sample)), _nozzle(sample)
            except HTTPException:
                pass
        page = report.sweepReport(table, dict(session.runs), sampleTable, sampleNozzle)
        return HTMLResponse(page, headers = {'Cache-Control': 'no-store'})

    # -- Validation status -- #
    @app.get('/api/validation/{model}')
    def validationModel(model: str) -> dict:

        summary = validationStatus.load()
        found = validationStatus.passages(model, summary)
        if found is None:
            raise HTTPException(404, f'no validation status for {model!r}')
        return {**validationStatus.badge([model], summary)['models'][0], 'passages': found}

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
