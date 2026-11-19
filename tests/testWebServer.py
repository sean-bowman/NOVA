# -- NOVA: GUI Server Tests -- #

'''

The GUI's server: the Design form schema it serializes, the dependency predicates it
evaluates, the unit table it hands the browser, the routes that read files, the cross-field checks
and the material routes, the result table with its headline numbers and its comparison against a
baseline run, the export routes and file previews, the kept runs and the baseline, the run store
that keeps them between launches with their names and notes, the cooling figures, the overlay of a
second run, the filled flow field, the palette stylesheet, and a run session's error, cancel and
mid-run contour paths.

The schema, unit, route, design, result table, export and palette tests need neither a run nor a
display; the result table and export tests stand a finished run in with a Nozzle stand-in and files
in a temporary folder. The cooling figure tests read the showcase cooling runs under
featureShowcase/coolingRuns, which are local outputs and not in the repository; without them they
skip. They cross-check each plotly builder against the Matplotlib drawer it ports. The session
tests start real worker processes: one on a config NOVA rejects, one cancelled during the contour
solve, and one that sends its contour figures when the contour stage ends and is then cancelled;
the first two run on a run store in a temporary folder and leave nothing in it. Together they take
about two minutes.

Author: Sean Bowman

'''

import json
import math
import os
import pickle
import struct
import sys
import time
import types

import numpy as np
import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

fastapi = pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from NOVA import units as novaUnits
from novaGui import configSchema
from novaGui import analysis, outputs, paletteCss, runStore, schemaJson
from novaGui.runStore import RunStore
from novaGui.server import createApp
from novaGui import session as sessionModule
from novaGui.session import RunRecord, RunSession

@pytest.fixture(scope = 'module')
def client():
    session = RunSession()
    app = createApp(session = session, warm = False)
    with TestClient(app) as testClient:
        yield testClient
    session.shutdown()

#--------------------------------------------------------------------------------------------------------------------------#
# -- The schema -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testEveryConfigKeyReachesTheBrowserOnce():
    '''
    The browser builds its config from the serialized schema, so every key the Tkinter form writes
    has to be in it exactly once, as a field or as a selector member.
    '''
    schema = schemaJson.serializeSchema()
    keys = []
    for group in schema['groups']:
        for item in group['items']:
            keys += [member['key'] for member in item['members']] if item['type'] == 'selector' else [item['key']]
    expected = [spec.key for spec in configSchema.allFields()]
    assert sorted(keys) == sorted(expected)
    assert len(keys) == len(set(keys))

def testTheDefaultsAreTheShippedNozzle():
    '''
    A fresh web form is the same nozzle a fresh Tkinter form is.
    '''
    assert schemaJson.serializeSchema()['defaults'] == configSchema.defaultConfig()

def testEveryPredicateIsFlaggedConditional():
    '''
    The browser asks the server about a row only through formState; the flag tells it which rows
    can change. A row with a predicate the flag missed would never hide.
    '''
    schema = schemaJson.serializeSchema()
    flagged = {item['id'] for group in schema['groups'] for item in group['items'] if item['conditional']}
    for group in configSchema.groups:
        for item in group.fields:
            if item.showWhen is not None:
                itemId = 'selector:' + item.name if isinstance(item, configSchema.Selector) else item.key
                assert itemId in flagged

def testTurningCoolingOffHidesTheJacketRows():
    '''
    The dependency predicates run on the server against the browser's config.
    '''
    config = configSchema.defaultConfig()
    config['makeCoolingChannels'] = True
    shown = schemaJson.formState(config)['hidden']
    config['makeCoolingChannels'] = False
    hidden = schemaJson.formState(config)['hidden']
    assert 'nChannel' not in shown
    assert 'nChannel' in hidden

def testAPredicateThatRaisesShowsTheRow():
    '''
    A half-typed config can make a predicate raise; the row stays visible rather than vanishing.
    '''
    assert schemaJson._test(lambda config: config['missing'] > 0, {}) is True

#--------------------------------------------------------------------------------------------------------------------------#
# -- Units -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.mark.parametrize('displayed', [-40.0, 0.0, 1.0, 273.15, 1234.5])
def testTheAffineUnitTableReproducesNovasRegistry(displayed):
    '''
    The browser converts with si = scale * shown + offset, taken from NOVA.units at two points.
    Every display unit NOVA offers must convert to the same SI value the registry gives, to a
    relative 1e-12, including the affine temperature units.
    '''
    table = schemaJson.serializeSchema()['units']
    for dimension, entry in table.items():
        for row in entry['units']:
            expected = novaUnits.toSI(displayed, dimension, row['unit'])
            assert row['scale'] * displayed + row['offset'] == pytest.approx(expected, rel = 1e-12, abs = 1e-12), \
                (dimension, row['unit'])

#--------------------------------------------------------------------------------------------------------------------------#
# -- Routes -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testAnExampleLoadsOverTheDefaults(client):
    '''
    An example route returns a complete config: the example's keys over the shipped defaults.
    '''
    examples = client.get('/api/schema').json()['examples']
    assert examples
    loaded = client.get(f"/api/examples/{examples[0]['name']}").json()
    assert set(configSchema.defaultConfig()) <= set(loaded)

@pytest.mark.parametrize('name', ['..%2F..%2FREADME', 'NOVANozzle', 'nothing'])
def testOnlyListedExamplesAreServed(client, name):
    '''
    The example route reads files by name, so it accepts only the names the examples folder lists.
    '''
    assert client.get(f'/api/examples/{name}').status_code == 404

def testViewsBeforeAnyRunAreAllUnavailable(client):
    '''
    With no finished run, the view list is complete and nothing in it is available.
    '''
    from novaGui import viewCatalog

    index = client.get('/api/views').json()
    assert [view['key'] for view in index['views']] == [spec.key for spec in viewCatalog.views]
    assert index['available'] == []
    assert index['runId'] is None
    assert client.get('/api/views/contour/interactive').status_code == 404

def testABadModeIsRefused(client):
    assert client.post('/api/runs', json = {'config': {}, 'mode': 'sepia'}).status_code == 400

#--------------------------------------------------------------------------------------------------------------------------#
# -- Result table -- #
#--------------------------------------------------------------------------------------------------------------------------#

class _PerformanceStandIn:

    '''The parts of a NozzlePerformance summary the result table reads.'''

    nozzleEfficiency = 0.9808
    frictionThrustCoef = 0.0388
    requestedThrust = 1.0e5
    thrustDelivered = {'design': 101707.0}
    thrustDeliveredFrictionCorrected = {'design': 99547.0}
    exitMassClosure = 0.9857
    extraMassFlows = {}
    specificImpulseDelivered = {'design': 441.8}

    def rows(self):
        return [('Exit Mach number', '-', 4.223, 3.954, 3.945),
                ('Specific impulse, vacuum', 's', 453.8, 464.2, None)]

def _nozzleStandIn():
    return types.SimpleNamespace(thrust = 1.0e5, engineMassFlow = 23.474, throatArea = math.pi * 0.05 ** 2,
                                 rNozzleWall = [0.09, 0.05, 0.3], xNozzleWall = [-0.2, 0.0, 1.0],
                                 performance = _PerformanceStandIn(), Fuel = 'LH2', Oxidizer = 'LOX',
                                 makeCoolingChannels = 'off')

def testTheResultTableSplitsThePerformanceColumns():
    '''
    The Tkinter table packs the three performance columns into one cell; the web table carries them
    as cells under the column heads, with a blank column kept as '--'.
    '''
    table = analysis.resultTable(_nozzleStandIn())
    sections = {section['title']: section for section in table['sections']}
    performance = sections['Performance: 1D estimate and delivered']
    assert performance['columns'] == ['equilibrium 1D', 'chamber gas 1D', 'delivered']
    rows = {row['label']: row for row in performance['rows']}
    assert rows['Exit Mach number']['cells'] == ['4.223', '3.954', '3.945']
    assert rows['Specific impulse, vacuum [s]']['cells'] == ['453.8', '464.2', '--']
    assert rows['Nozzle efficiency, vacuum']['cells'] == ['0.9808']

def testTheResultTableCarriesTheTkinterRowsAndSummary():
    '''
    The rows are the Tkinter Analyze tab's own: a 50 mm throat from its area, a contour 1200 mm
    long, and the header's thrust, delivered Isp and propellants.
    '''
    table = analysis.resultTable(_nozzleStandIn())
    sizing = {row['label']: row for row in table['sections'][0]['rows']}
    assert table['sections'][0]['title'] == 'Sizing'
    assert (sizing['Thrust']['cells'], sizing['Thrust']['unit']) == (['100000'], 'N')
    assert (sizing['Throat radius']['cells'], sizing['Throat radius']['unit']) == (['50.00'], 'mm')
    assert (sizing['Exit radius']['cells'], sizing['Contour length']['cells']) == (['300.00'], ['1200.0'])
    assert sizing['Expansion ratio (1D)']['cells'] == ['--']
    assert table['summary'] == '100 kN   Isp 442 s   LOX/LH2'

@pytest.mark.parametrize('text, split', [
    ('1234 N', ('1234', 'N')),
    ('+0.12 %', ('+0.12', '%')),
    ('8006.2 cm3', ('8006.2', 'cm3')),
    ('1.5 lip radii downstream', ('1.5', 'lip radii downstream')),
    ('12 channels, 1.2 g/s each', ('12 channels, 1.2 g/s each', '')),
    ('30.0 to 94.9 K', ('30.0 to 94.9 K', '')),
    ('Separated', ('Separated', '')),
])
def testAValueSplitsFromItsUnitOnlyWhenTheRestIsAUnit(text, split):
    assert analysis._splitUnit(text) == split

#--------------------------------------------------------------------------------------------------------------------------#
# -- Export -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _stl(triangles: list) -> bytes:
    '''A binary STL of the given triangles, each three (x, y, z) corners.'''
    body = b''.join(struct.pack('<12fH', 0.0, 0.0, 1.0, *[value for corner in corners for value in corner], 0)
                    for corners in triangles)
    return b'x' * 80 + struct.pack('<I', len(triangles)) + body

_outputBytes = {
    'machContours.png':          b'p' * 2048,
    'contourInteractive.html':   b'<html></html>',
    'testEngineHotWall.txt':     b'0.0 0.05\n',
    'testEngine.pkl':            b'\x80\x04N.',
    'testEngineWall.stl':        _stl([((0, 0, 0), (1, 0, 0), (0, 1, 0)), ((1, 0, 0), (1, 1, 0), (0, 1, 0))]),
}
_runIds = iter(range(700, 800))

@pytest.fixture
def finishedRun(client, tmp_path):
    '''A finished run of 'testEngine' in a temporary staging folder, standing in the session.'''
    runFolder = tmp_path / 'run7'
    outputFolder = runFolder / 'testEngineOutputs'
    outputFolder.mkdir(parents = True)
    for name, content in _outputBytes.items():
        (outputFolder / name).write_bytes(content)
    (runFolder / 'testEngineRunConfig.json').write_text('{}')
    # A fresh run id each time, so the server's table cache never answers for another test's run
    record = RunRecord(next(_runIds), {'ok': True, 'runName': 'testEngine', 'outputDir': str(outputFolder),
                                       'picklePath': 'held in memory', 'elapsedSec': 1.0})
    record._nozzle = _nozzleStandIn()
    session = client.app.state.session
    session.adopt(record)
    yield record
    session.forget(record.runId)

def testTheViewIndexCarriesTheConfigItsRunRan(client):
    '''The result pane compares the form with the config of the run it shows.'''
    session = client.app.state.session
    record = RunRecord(next(_runIds), {'ok': True, 'runName': 'testEngine', 'elapsedSec': 12.5},
                       config = {'chamberPressure': 6.9e6, 'ambientPressure': 5000.0})
    session.adopt(record)
    try:
        index = client.get('/api/views').json()
        assert index['runId'] == record.runId and index['runName'] == 'testEngine'
        assert index['elapsedSec'] == 12.5
        assert index['config'] == {'chamberPressure': 6.9e6, 'ambientPressure': 5000.0}
        assert client.get(f'/api/views?run={record.runId}').json()['runId'] == record.runId
    finally:
        session.forget(record.runId)
    assert client.get('/api/views').json()['config'] is None

def testTheFormWidthIsSavedApartFromTheThemeMode(client, tmp_path, monkeypatch):
    from novaGui import settings as guiSettings
    monkeypatch.setattr(guiSettings, 'settingsPath', lambda: str(tmp_path / 'guiSettings.json'))
    assert client.put('/api/settings', json = {'formWidth': 610}).json() == {'themeMode': 'dark', 'formWidth': 610}
    assert client.put('/api/settings', json = {'themeMode': 'light'}).json() == {'themeMode': 'light', 'formWidth': 610}
    assert client.put('/api/settings', json = {'formWidth': 'wide'}).json()['formWidth'] == 610

def testNoRunMeansAnEmptyTableAndNoOutputs(client):
    assert client.get('/api/analysis').json()['runId'] is None
    index = client.get('/api/export').json()
    assert index['files'] == [] and index['runId'] is None
    assert [category['key'] for category in index['categories']][0] == 'figures'
    assert index['defaultBaseDir'] == os.path.join(root, 'runs')

def testTheAnalysisRouteServesTheRunsTable(client, finishedRun):
    table = client.get('/api/analysis').json()
    assert table['runId'] == finishedRun.runId
    assert table['summary'] == '100 kN   Isp 442 s   LOX/LH2'

def testTheExportListingFilesEachOutputByCategory(client, finishedRun):
    '''
    The listing is the outputs folder plus the run config beside it, each filed by the Tkinter
    Export tab's rule.
    '''
    files = {entry['name']: entry for entry in client.get('/api/export').json()['files']}
    assert {name: entry['category'] for name, entry in files.items()} == {
        'machContours.png': 'figures', 'contourInteractive.html': 'interactive',
        'testEngineHotWall.txt': 'contours', 'testEngine.pkl': 'nozzle', 'testEngineRunConfig.json': 'config',
        'testEngineWall.stl': 'geometry'}
    assert files['machContours.png']['bytes'] == 2048
    assert {name: entry['preview'] for name, entry in files.items()} == {
        'machContours.png': 'image', 'contourInteractive.html': None, 'testEngineHotWall.txt': 'text',
        'testEngine.pkl': None, 'testEngineRunConfig.json': 'text', 'testEngineWall.stl': 'mesh'}

def testAPreviewReadsOnlyTheRunsListedFiles(client, finishedRun):
    '''
    An image previews as itself, a text file as its text, an STL as shared vertices and triangles;
    a name outside the run's listing, or a file with no preview, is refused.
    '''
    image = client.get('/api/export/file', params = {'name': 'machContours.png'})
    assert image.status_code == 200 and image.content == _outputBytes['machContours.png']
    text = client.get('/api/export/file', params = {'name': 'testEngineHotWall.txt', 'run': finishedRun.runId}).json()
    assert text == {'text': '0.0 0.05\n', 'bytes': 9, 'cut': False}
    mesh = client.get('/api/export/mesh', params = {'name': 'testEngineWall.stl'}).json()
    assert (mesh['triangles'], mesh['shown'], len(mesh['x'])) == (2, 2, 4)
    corners = {tuple(round(mesh[axis][index], 9) for axis in 'xyz') for index in mesh['i'] + mesh['j'] + mesh['k']}
    assert corners == {(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)}
    assert client.get('/api/export/file', params = {'name': '..\\..\\secret.txt'}).status_code == 404
    assert client.get('/api/export/file', params = {'name': 'testEngine.pkl'}).status_code == 400
    assert client.get('/api/export/mesh', params = {'name': 'machContours.png'}).status_code == 400

def testAThinnedMeshStaysUnderItsCap(tmp_path):
    '''A surface over the cap is thinned by clustering its corners, and says how far.'''
    grid = 60
    triangles = []
    for row in range(grid):
        for column in range(grid):
            a, b = (row / grid, column / grid, 0.0), ((row + 1) / grid, column / grid, 0.0)
            c, d = (row / grid, (column + 1) / grid, 0.0), ((row + 1) / grid, (column + 1) / grid, 0.0)
            triangles += [(a, b, d), (a, d, c)]
    path = tmp_path / 'sheet.stl'
    path.write_bytes(_stl(triangles))
    whole = outputs.stlMesh(str(path))
    assert (whole['triangles'], whole['shown'], len(whole['x'])) == (7200, 7200, 61 * 61)
    thinned = outputs.stlMesh(str(path), maxTriangles = 2000)
    assert thinned['triangles'] == 7200 and thinned['shown'] <= 2000
    assert min(thinned['x']) == pytest.approx(0.0, abs = 0.02) and max(thinned['x']) == pytest.approx(1.0, abs = 0.02)
def testAnExportCopiesTheChosenFilesUnderTheRunName(client, finishedRun, tmp_path):
    base = tmp_path / 'exports'
    reply = client.post('/api/export', json = {'baseDir': str(base),
                                                'files': ['machContours.png', 'testEngineRunConfig.json']}).json()
    target = base / 'testEngineOutputs'
    assert reply == {'target': str(target), 'written': 2, 'bytes': 2050}
    assert sorted(os.listdir(target)) == ['machContours.png', 'testEngineRunConfig.json']
    assert (target / 'machContours.png').read_bytes() == _outputBytes['machContours.png']
    assert client.get('/api/export/target', params = {'base': str(base), 'name': 'testEngine'}).json() == {
        'target': str(target), 'exists': True}

@pytest.mark.parametrize('names', [[], ['..\\..\\secret.txt'], ['testEngineOutputs'], ['machContours.png', 'other.png']])
def testAnExportTakesOnlyTheRunsListedFiles(client, finishedRun, tmp_path, names):
    '''
    Files are named by base name and checked against the run's listing, so nothing outside the
    run's staging folder can be copied, and a bad request copies nothing.
    '''
    base = tmp_path / 'exports'
    assert client.post('/api/export', json = {'baseDir': str(base), 'files': names}).status_code == 400
    assert not base.exists()

@pytest.mark.parametrize('name', ['a/b', '..', 'x:y', ''])
def testAnUnsafeRunNameFallsBackToNovaRun(name):
    assert os.path.basename(outputs.targetFolder('C:\\base', name)) == 'novaRunOutputs'

def testOpeningReachesOnlyTheRunsFilesAndTheTargetFolder(client, finishedRun, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(outputs, 'openPath', opened.append)
    assert client.post('/api/export/open', json = {'what': 'file', 'name': '..\\..\\secret.txt'}).status_code == 404
    assert client.post('/api/export/open', json = {'what': 'folder', 'baseDir': str(tmp_path / 'none')}).status_code == 404
    assert client.post('/api/export/open', json = {'what': 'drive'}).status_code == 400
    assert client.post('/api/export/open', json = {'what': 'file', 'name': 'testEngine.pkl'}).status_code == 200
    assert opened == [os.path.join(finishedRun.outputDir, 'testEngine.pkl')]

#--------------------------------------------------------------------------------------------------------------------------#
# -- Kept runs, the baseline and the comparison -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _record(runId: int, **summary) -> RunRecord:
    return RunRecord(runId, {'ok': True, 'runName': f'engine{runId}', 'elapsedSec': 10.0, **summary},
                     config = {'chamberPressure': 6.9e6 + runId})

def testTheSessionKeepsTheLatestRunsAndTheBaseline():
    '''
    The session keeps the last keptRuns finished runs and the baseline however many follow it; a
    run that drops out takes its staging folder with it.
    '''
    session = RunSession()
    try:
        for runId in (1, 2):
            session.adopt(_record(runId))
        session.setBaseline(1)
        dropped = os.path.join(sessionModule.stagingRoot(), 'run2')
        os.makedirs(dropped, exist_ok = True)
        last = sessionModule.keptRuns + 3
        for runId in range(3, last + 1):
            session.adopt(_record(runId))
        kept = list(session.runs)
        assert kept[0] == 1 and len(kept) == sessionModule.keptRuns + 1
        assert kept[1:] == list(range(last - sessionModule.keptRuns + 1, last + 1))
        assert not os.path.isdir(dropped)
        assert session.record().runId == last and session.record(1).runId == 1 and session.record(2) is None
        listing = session.runList()
        assert [entry['runId'] for entry in listing['runs']][:2] == [last, last - 1]
        assert (listing['baseline'], listing['latest'], listing['running']) == (1, last, None)
        with pytest.raises(KeyError):
            session.setBaseline(2)
    finally:
        session.shutdown()

def testOnlyTheRunsDrawnFromLatelyKeepTheirNozzle(tmp_path):
    '''A kept run past the last keptNozzles drawn from releases its Nozzle and reads its pickle again.'''
    session = RunSession()
    try:
        records = []
        for runId in range(1, sessionModule.keptNozzles + 2):
            path = tmp_path / f'run{runId}.pkl'
            path.write_bytes(pickle.dumps({'runId': runId}))
            records.append(_record(runId, picklePath = str(path)))
            session.adopt(records[-1])
        for record in records:
            assert session.nozzle(record) == {'runId': record.runId}
        assert records[0]._nozzle is None
        assert all(record._nozzle is not None for record in records[1:])
        assert session.nozzle(records[0]) == {'runId': 1}
    finally:
        session.shutdown()

def testTheRunListAndBaselineRoutes(client):
    session = client.app.state.session
    first, second = _record(next(_runIds)), _record(next(_runIds))
    session.adopt(first)
    session.adopt(second)
    try:
        listing = client.get('/api/runs').json()
        assert [entry['runId'] for entry in listing['runs']][:2] == [second.runId, first.runId]
        assert listing['runs'][0]['config'] == second.config
        assert client.put('/api/runs/baseline', json = {'runId': first.runId}).json() == {'baseline': first.runId}
        assert client.get('/api/runs').json()['baseline'] == first.runId
        assert client.put('/api/runs/baseline', json = {'runId': 99999}).status_code == 404
        assert client.put('/api/runs/baseline', json = {'runId': True}).status_code == 400
        assert client.put('/api/runs/baseline', json = {'runId': None}).json() == {'baseline': None}
        assert client.get(f'/api/views?run=99999').status_code == 200
        assert client.get(f'/api/analysis?run=99999').status_code == 404
    finally:
        session.forget(first.runId)
        session.forget(second.runId)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The run store -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheStoreNeverGivesAnIdOutTwice(tmp_path):
    '''
    Run ids count up across launches: a deleted run's id is not given out again, and a folder
    another server claimed is stepped over.
    '''
    store = RunStore(str(tmp_path))
    assert [store.claim()[0] for _ in range(2)] == [1, 2]
    store.remove(2)
    again = RunStore(str(tmp_path))
    assert again.claim() == (3, again.folder(3))
    os.mkdir(again.folder(4))
    assert again.claim()[0] == 5 and os.path.isdir(again.folder(5))

@pytest.mark.parametrize('runs, countLimit, byteLimit, dropped', [
    # Three unnamed runs count against a limit of two, the baseline (3) not among them
    ([(1, False, 10), (2, True, 10), (3, False, 10), (4, False, 10), (5, False, 10)], 2, 1000, [1]),
    # Past the size, unnamed runs go oldest first; the named run, the baseline and the newest stay
    ([(1, False, 10), (2, True, 10), (3, False, 10), (4, False, 10), (5, False, 10)], 10, 25, [1, 4]),
    ([(1, False, 10), (2, False, 10)], 2, 1000, []),
])
def testTheStoreDropsTheOldestUnnamedRunsFirst(runs, countLimit, byteLimit, dropped):
    assert runStore.pruned(runs, baseline = 3, newest = 5, countLimit = countLimit, byteLimit = byteLimit) == dropped

def _storedRun(store, session, title: str = '', **summary) -> RunRecord:
    '''A finished run written into a store folder, with outputs and a pickled stand-in, adopted by the session.'''
    runId, folder = store.claim()
    outputFolder = os.path.join(folder, 'testEngineOutputs')
    os.makedirs(outputFolder)
    with open(os.path.join(outputFolder, 'testEngineContour.txt'), 'w') as handle:
        handle.write('0 1\n' * 100)
    picklePath = os.path.join(folder, 'novaGuiResult.pkl')
    with open(picklePath, 'wb') as handle:
        pickle.dump({'runId': runId}, handle)
    record = RunRecord(runId, {'ok': True, 'runName': 'testEngine', 'outputDir': outputFolder, 'picklePath': picklePath,
                               'elapsedSec': 12.5, 'headline': '100 kN  Isp 440 s', **summary},
                       config = {'chamberPressure': 6.9e6 + runId}, folder = folder,
                       warnings = [{'category': 'UserWarning', 'message': 'one', 'where': 'a.py:1', 'count': 2}])
    if title:
        record.title = title
    session.adopt(record)
    return record

def testARunOnTheStoreOutlastsItsSession(tmp_path):
    '''
    A session on the store saves each finished run beside its outputs; the next session starts
    with it, its name, note, config, warnings and headline, and the baseline.
    '''
    store = RunStore(str(tmp_path))
    session = RunSession(store = store)
    try:
        record = _storedRun(store, session)
        session.describe(record.runId, title = '  Baseline   design ', note = 'first try\n')
        session.setBaseline(record.runId)
        entry = session.runList()['runs'][0]
        assert (entry['title'], entry['note'], entry['saved']) == ('Baseline design', 'first try', True)
        assert entry['bytes'] > 400
        assert session.runList()['store']['folder'] == store.root
    finally:
        session.shutdown()

    later = RunSession(store = RunStore(str(tmp_path)))
    try:
        kept = later.record(record.runId)
        assert later.baseline == record.runId and later.record().runId == record.runId
        for name in ('runName', 'title', 'note', 'elapsedSec', 'headline', 'finishedAt', 'config', 'warnings',
                     'outputDir', 'picklePath', 'bytes'):
            assert getattr(kept, name) == getattr(record, name), name
        assert later.nozzle(kept) == {'runId': record.runId}
        with open(os.path.join(store.folder(record.runId), runStore.recordName), encoding = 'utf-8') as handle:
            saved = json.load(handle)
        assert saved['outputDir'] == 'testEngineOutputs' and saved['picklePath'] == 'novaGuiResult.pkl'
    finally:
        later.shutdown()

def testTheStoreKeepsNamedRunsAndTheBaselinePastItsLimit(tmp_path, monkeypatch):
    '''
    Past the store's limit the oldest unnamed run goes with its folder; a named run and the baseline
    stay. A deleted run takes its folder, and deleting the baseline clears it.
    '''
    monkeypatch.setattr(runStore, 'unnamedRuns', 2)
    store = RunStore(str(tmp_path))
    session = RunSession(store = store)
    try:
        named = _storedRun(store, session, title = 'keep me')
        records = [_storedRun(store, session) for _ in range(2)]
        session.setBaseline(records[0].runId)
        records += [_storedRun(store, session) for _ in range(2)]
        assert list(session.runs) == [named.runId, records[0].runId, records[2].runId, records[3].runId]
        assert not os.path.isdir(records[1].folder) and os.path.isdir(named.folder)

        session.delete(records[0].runId)
        assert session.baseline is None and store.baseline is None
        assert not os.path.isdir(records[0].folder) and records[0].runId not in session.runs
        with pytest.raises(KeyError):
            session.delete(records[0].runId)
        with pytest.raises(ValueError):
            session.describe(named.runId, title = 'x' * (sessionModule.titleLength + 1))
    finally:
        session.shutdown()

def testTheStoreCollectsRunsThatNeverFinished(tmp_path):
    '''A folder with no record, left by a server that closed mid-run, goes once it is stale; a fresh one stays.'''
    store = RunStore(str(tmp_path))
    staleId, stale = store.claim()
    freshId, fresh = store.claim()
    old = time.time() - 3600.0 * (runStore.staleHours + 1.0)
    os.utime(stale, (old, old))
    RunSession(store = RunStore(str(tmp_path))).shutdown()
    assert not os.path.isdir(stale) and os.path.isdir(fresh)
    assert store.claim()[0] == freshId + 1

def testARunWhosePickleNoLongerLoadsSaysWhy(client, tmp_path):
    '''
    A saved run whose Nozzle no longer unpickles still lists, with its config; its views and table
    answer with the reason.
    '''
    broken = tmp_path / 'novaGuiResult.pkl'
    broken.write_bytes(b'not a pickle')
    session = client.app.state.session
    record = RunRecord(next(_runIds), {'ok': True, 'runName': 'oldEngine', 'picklePath': str(broken)},
                       config = {'chamberPressure': 5e6})
    session.adopt(record)
    try:
        index = client.get('/api/views', params = {'run': record.runId}).json()
        assert index['available'] == [] and index['config'] == {'chamberPressure': 5e6}
        assert 'does not load in this NOVA' in index['loadError']
        table = client.get('/api/analysis', params = {'run': record.runId})
        assert table.status_code == 404 and 'cannot be drawn' in table.json()['detail']
    finally:
        session.forget(record.runId)

def testTheRunNameNoteAndDeleteRoutes(client):
    session = client.app.state.session
    record = _record(next(_runIds))
    session.adopt(record)
    try:
        named = client.patch(f'/api/runs/{record.runId}', json = {'title': '8 MPa', 'note': 'higher pc'})
        assert named.status_code == 200 and (named.json()['title'], named.json()['note']) == ('8 MPa', 'higher pc')
        assert client.patch(f'/api/runs/{record.runId}', json = {'note': ''}).json()['title'] == '8 MPa'
        assert client.get('/api/runs').json()['runs'][0]['note'] == ''
        assert client.patch(f'/api/runs/{record.runId}', json = {}).status_code == 400
        assert client.patch(f'/api/runs/{record.runId}', json = {'title': 5}).status_code == 400
        assert client.patch(f'/api/runs/{record.runId}', json = {'title': 'x' * 200}).status_code == 400
        assert client.patch('/api/runs/99999', json = {'title': 'a'}).status_code == 404

        session.setBaseline(record.runId)
        cache = client.app.state.figureCache
        cache[(record.runId, False, 'contour', 'dark', None, None)] = (b'{}', b'')
        assert client.delete(f'/api/runs/{record.runId}').json() == {'deleted': record.runId}
        assert all(entry[0] != record.runId for entry in cache)
        listing = client.get('/api/runs').json()
        assert listing['baseline'] is None and record.runId not in [entry['runId'] for entry in listing['runs']]
        assert client.delete(f'/api/runs/{record.runId}').status_code == 404
    finally:
        session.forget(record.runId)

@pytest.mark.parametrize('shown, baseline, text', [
    ('441.8', '440.3', '+1.5 (+0.34 %)'),
    ('1156.8', '1000.0', '+156.8 (+16 %)'),
    ('800.0', '758.2', '+41.8 (+5.5 %)'),
    ('100000', '100000', ''),
    ('0.365', '0', '+0.365'),
    ('1.2e+05', '1e+05', '+2e+04 (+20 %)'),
    ('B, one and a half pass', 'A, single pass', 'differs'),
    ('--', '12.0', ''),
])
def testAChangeIsWrittenToTheShownDecimals(shown, baseline, text):
    assert analysis.change(shown, baseline) == text

def testTheComparisonMatchesRowsAndKeepsTheBaselinesOwn():
    '''
    Rows match by section and label, a repeated label by its place among its namesakes; rows and
    sections only the baseline has follow with blank cells, and a row whose shape differs is not
    compared.
    '''
    def table(sections, numbers = ()):
        return {'summary': '', 'headline': list(numbers),
                'sections': [{'title': title, 'columns': None,
                              'rows': [{'label': label, 'cells': cells, 'unit': unit, 'indent': False, 'view': None}
                                       for label, cells, unit in rows]} for title, rows in sections]}
    shown = table([('Sizing', [('Thrust', ['100000'], 'N'), ('  coolant', ['96.0 to 257.0 K'], ''),
                               ('  coolant', ['257.0 to 300.0 K'], ''), ('Exit radius', ['319.28'], 'mm')])],
                  [{'key': 'isp', 'label': 'Delivered Isp', 'value': '441.8', 'unit': 's'}])
    baseline = table([('Sizing', [('Thrust', ['90000'], 'N'), ('  coolant', ['96.0 to 160.0 K'], ''),
                                  ('Exit radius', ['319.28'], 'cm'), ('Split area ratio', ['2.5'], '')]),
                      ('Plume', [('Ambient pressure', ['5000'], 'Pa')])],
                     [{'key': 'isp', 'label': 'Delivered Isp', 'value': '440.3', 'unit': 's'}])
    compared = analysis.compareTables(shown, baseline)
    rows = compared['sections'][0]['rows']
    assert [(row['label'], row['baseline'], row['change']) for row in rows] == [
        ('Thrust', ['90000'], ['+10000 (+11 %)']),
        ('  coolant', ['96.0 to 160.0 K'], ['differs']),
        ('  coolant', None, None),
        ('Exit radius', ['319.28'], None),
        ('Split area ratio', ['2.5'], None),
    ]
    assert rows[-1]['cells'] == ['--'] and rows[-1]['baselineOnly']
    assert compared['sections'][1]['title'] == 'Plume' and compared['sections'][1]['baselineOnly']
    assert compared['headline'][0]['change'] == '+1.5 (+0.34 %)'

def testPressureDropsEitherSideOfOneBarStillCompare():
    '''A pass's pressure drop reads in one unit for every run, so 55.6 kPa against 0.114 MPa compares.'''
    shown, baseline = analysis._pressureText(1.14e5), analysis._pressureText(5.56e4)
    assert shown[1] == baseline[1] == 'MPa'
    numbers = [{'key': 'dropDown', 'label': 'Down pass pressure drop', 'value': shown[0], 'unit': shown[1]}]
    olds = [{'key': 'dropDown', 'label': 'Down pass pressure drop', 'value': baseline[0], 'unit': baseline[1]}]
    compared = analysis.compareTables({'headline': numbers, 'sections': []}, {'headline': olds, 'sections': []})
    assert compared['headline'][0]['baseline'] == '0.0556' and compared['headline'][0]['change'] == '+0.058 (+105 %)'

def testTheAnalysisRouteSetsTheBaselineBeside(client, finishedRun):
    other = RunRecord(next(_runIds), {'ok': True, 'runName': 'otherEngine', 'elapsedSec': 1.0,
                                      'picklePath': 'held in memory'})
    stand = _nozzleStandIn()
    stand.thrust = 9.0e4
    other._nozzle = stand
    client.app.state.session.adopt(other)
    try:
        table = client.get('/api/analysis', params = {'run': finishedRun.runId, 'baseline': other.runId}).json()
        assert (table['runId'], table['baselineRun']) == (finishedRun.runId, other.runId)
        thrust = next(row for row in table['sections'][0]['rows'] if row['label'] == 'Thrust')
        assert (thrust['cells'], thrust['baseline'], thrust['change']) == (['100000'], ['90000'], ['+10000 (+11 %)'])
        alone = client.get('/api/analysis', params = {'run': finishedRun.runId}).json()
        assert alone['baselineRun'] is None and 'baseline' not in alone['sections'][0]['rows'][0]
    finally:
        client.app.state.session.forget(other.runId)

def testEveryRowNamesAFigureOnlyWhereOneShowsIt():
    table = analysis.resultTable(_nozzleStandIn())
    views = {(section['title'], row['label']): row['view'] for section in table['sections'] for row in section['rows']}
    assert views[('Sizing', 'Throat radius')] == 'contour'
    assert views[('Performance: 1D estimate and delivered', 'Exit Mach number')] == 'mach'
    assert views[('Performance: 1D estimate and delivered', 'Nozzle efficiency, vacuum')] is None
    from novaGui import viewCatalog
    keys = {spec.key for spec in viewCatalog.views}
    assert {view for view in analysis.sectionViews.values()} | {view for view in analysis.rowViews.values()} <= keys

def testTheHeadlineRepeatsTheTablesNumbers():
    '''The headline numbers are the table's own, in display units, and say which figure shows each.'''
    numbers = {number['key']: number for number in analysis.resultTable(_nozzleStandIn())['headline']}
    assert (numbers['isp']['value'], numbers['isp']['unit']) == ('441.8', 's')
    assert (numbers['thrust']['value'], numbers['thrust']['unit']) == ('101.7', 'kN')
    assert (numbers['length']['value'], numbers['exitDiameter']['value']) == ('1200.0', '600.0')
    assert numbers['length']['view'] == 'contour' and 'peakWall' not in numbers

def testAShowcaseJacketsHeadlineReadsItsLimitAndPasses():
    nozzle = _showcase('NOVANozzle')
    table = analysis.resultTable(nozzle)
    numbers = {number['key']: number for number in table['headline']}
    cooling = {row['label']: row for section in table['sections'] if section['title'] == 'Cooling' for row in section['rows']}
    assert numbers['peakWall']['value'] == cooling['Peak hot wall temperature']['cells'][0]
    # A jacket sized to its limit reads at it, and is not over it
    assert numbers['peakWall']['tone'] == '' and 'margin 0 K' in numbers['peakWall']['detail']
    circuit = nozzle.coolantCircuitSolution
    drop = float(circuit.up.state.coolantInitialPressure) - float(circuit.up.state.coolantExitPressure)
    assert float(numbers['dropUp']['value']) * {'MPa': 1e6, 'kPa': 1e3}[numbers['dropUp']['unit']] == pytest.approx(drop, rel = 2e-3)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Warnings, the figure cache and compression -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheRunnerRelaysAWarningToTheLogAndAsItsOwnMessage():
    import queue as queueModule
    import warnings
    from novaGui.runner import warningRelay
    messages = queueModule.Queue()
    with warnings.catch_warnings():
        warnings.simplefilter('always')
        warnings.showwarning = warningRelay(messages)
        warnings.warn('the card has no editable field', UserWarning)
    (logKind, line), (kind, warning) = messages.get_nowait(), messages.get_nowait()
    assert logKind == 'log' and 'UserWarning' in line and 'the card has no editable field' in line
    assert kind == 'warning' and warning['category'] == 'UserWarning'
    assert warning['message'] == 'the card has no editable field' and warning['where'].startswith('testWebServer.py:')

class _EndedProcess:
    '''A worker that has already ended, for driving the session's pump by hand.'''
    exitcode = 0
    def is_alive(self):
        return False
    def join(self, timeout = None):
        return None

def testTheSessionCountsEachWarningOnceAndKeepsThemWithTheRun():
    '''
    A run's warnings are kept once per category and message with how many times each came, sent
    as they arrive, and kept with the finished run for the run list.
    '''
    import queue as queueModule
    session = RunSession()
    events = []
    session._publish = lambda event: events.append(event) or RunSession._publish(session, event)
    try:
        messages = queueModule.Queue()
        repeated = {'category': 'RuntimeWarning', 'message': 'invalid value in divide', 'where': 'chamber.py:420'}
        for payload in (repeated, {'category': 'UserWarning', 'message': 'card unchanged', 'where': 'ceaInterface.py:429'},
                        repeated):
            messages.put(('warning', payload))
        messages.put(('result', {'ok': True, 'runName': 'warned', 'elapsedSec': 1.0}))
        session.state['runId'] = 31
        session._drain(_EndedProcess(), messages, 31)
        expected = [{**repeated, 'count': 2},
                    {'category': 'UserWarning', 'message': 'card unchanged', 'where': 'ceaInterface.py:429', 'count': 1}]
        assert session.record(31).warnings == expected
        assert session.runList()['runs'][0]['warnings'] == expected
        sent = [event for event in events if event['type'] == 'warning']
        assert len(sent) == 3 and sent[-1] == {'type': 'warning', 'runId': 31, 'warnings': expected}
    finally:
        session.shutdown()

def testAFigureIsBuiltOnceAndSentCompressed(client, finishedRun, monkeypatch):
    '''
    A view's figure is built once per run, view and mode and drawn from memory after; a figure of a
    run that is no longer kept is dropped; the response is gzipped for a browser that accepts it.
    '''
    from novaGui import views
    built = []
    def interactiveFigure(nozzle, key, mode, compare = None, labels = ()):
        built.append((key, mode))
        return '{"data": [], "layout": {"title": "' + 'x' * 4000 + '"}}'
    monkeypatch.setattr(views, 'interactiveFigure', interactiveFigure)
    route = '/api/views/contour/interactive'
    first = client.get(route, params = {'run': finishedRun.runId, 'mode': 'dark'}, headers = {'Accept-Encoding': 'gzip'})
    assert first.status_code == 200 and first.headers.get('content-encoding') == 'gzip'
    assert first.json()['layout']['title'] == 'x' * 4000
    client.get(route, params = {'run': finishedRun.runId, 'mode': 'dark'})
    client.get(route, params = {'run': finishedRun.runId, 'mode': 'light'})
    assert built == [('contour', 'dark'), ('contour', 'light')]
    cache = client.app.state.figureCache
    assert {entry[0] for entry in cache} == {finishedRun.runId}

    other = RunRecord(next(_runIds), {'ok': True, 'runName': 'otherEngine', 'elapsedSec': 1.0, 'picklePath': 'held in memory'})
    other._nozzle = _nozzleStandIn()
    session = client.app.state.session
    session.adopt(other)
    session.forget(finishedRun.runId)
    try:
        client.get(route, params = {'run': other.runId, 'mode': 'dark'})
        assert {entry[0] for entry in cache} == {other.runId}
    finally:
        session.forget(other.runId)
        session.adopt(finishedRun)

def testTheContourAndNearWallHoverAlongTheAxis():
    '''The browser's axial cursor reads the contour's radius at its station: those views hover along x.'''
    import json
    from NOVA import figures
    from novaGui import views
    contour = json.loads(views.interactiveFigure(_nozzleStandIn(), 'contour', 'dark'))
    assert contour['layout']['hovermode'] == 'x unified'
    description = figures.ContourFigure(x = np.linspace(-0.2, 1.0, 40), r = np.linspace(0.09, 0.3, 40), throatX = 0.0,
                                        throatRadius = 0.05, exitRadius = 0.3, length = 1.2)
    assert json.loads(views.partialFigure(description, 'contour', 'light'))['layout']['hovermode'] == 'x unified'
    assert 'contour' in views.alongAxisHover and 'mach' not in views.alongAxisHover

#--------------------------------------------------------------------------------------------------------------------------#
# -- A run still going -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testARunInProgressServesTheFiguresItsContourSettled(client):
    '''
    While a run is going, the views and their figures come from the descriptions its contour stage
    settled; the views it has yet to settle are refused.
    '''
    from NOVA import figures
    session = client.app.state.session
    contour = figures.ContourFigure(x = np.linspace(-0.2, 1.0, 40), r = np.linspace(0.09, 0.3, 40), throatX = 0.0,
                                    throatRadius = 0.05, exitRadius = 0.3, length = 1.2)
    saved = (session._process, session.state['runId'], session._runConfig, session.partial)
    session._process, session.state['runId'], session._runConfig = object(), 4242, {'filename': 'liveEngine'}
    session.partial = {'runId': 4242, 'figures': {'contour': contour}}
    try:
        index = client.get('/api/views', params = {'run': 4242}).json()
        assert (index['partial'], index['available'], index['runName']) == (True, ['contour'], 'liveEngine')
        figure = client.get('/api/views/contour/interactive', params = {'run': 4242, 'mode': 'light'})
        assert figure.status_code == 200 and figure.json()['data'][0]['name'] == 'Wall contour'
        assert client.get('/api/views/mach/interactive', params = {'run': 4242}).status_code == 404
        assert session.runList()['running'] == {'runId': 4242, 'config': {'filename': 'liveEngine'}, 'views': ['contour'],
                                                'warnings': []}
    finally:
        session._process, session.state['runId'], session._runConfig, session.partial = saved

#--------------------------------------------------------------------------------------------------------------------------#
# -- Design aids -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _withDefaults(**changes) -> dict:
    return {**configSchema.defaultConfig(), **changes}

def testTheShippedNozzleRaisesNoProblem(client):
    state = client.post('/api/schema/state', json = configSchema.defaultConfig()).json()
    assert state['problems'] == [] and state['flagged'] == []
    assert isinstance(state['hidden'], list) and isinstance(state['expand'], list)

@pytest.mark.parametrize('changes, problem, flagged', [
    ({'Lstar': -1.0}, "'Characteristic length L*' must be positive.", 'selector:Chamber length'),
    ({'makeRadiativeExtension': True, 'extensionMaterial': 'C/SiC', 'extensionAtmosphere': 'oxidisingCoated'},
     "'Service atmosphere' has no limit for C/SiC, which has one for inert, oxidising.", 'extensionAtmosphere'),
    ({'channelType': 'helical', 'channelHelixAngle': None}, "Helical channels need a 'Channel helix angle'.",
     'channelHelixAngle'),
    ({'makeCoolingChannels': False, 'makeInletVolute': True}, "Volutes need 'Generate cooling channels' on.",
     'makeCoolingChannels'),
    ({'hotWallThickness': None}, "Cooling channels need 'Hot wall thickness'.", 'hotWallThickness'),
])
def testTheCrossFieldChecksAreTheTkinterForms(client, changes, problem, flagged):
    '''
    The problems are the words both forms show, the row a problem quotes is flagged, and the row
    carries that problem for the browser to write under it.
    '''
    state = client.post('/api/schema/state', json = _withDefaults(**changes)).json()
    assert problem in state['problems']
    assert flagged in state['flagged']
    assert problem in state['notes'][flagged]

def testTheRequiredSelectorCheckIsLeftToTheBrowserRow(client):
    '''The browser's selector row blocks a blank required option itself; the server does not repeat it.'''
    selector = next(item for group in configSchema.groups for item in group.fields
                    if isinstance(item, configSchema.Selector) and item.required)
    state = client.post('/api/schema/state', json = _withDefaults(**{key: None for key in selector.keys()})).json()
    assert not any('needs a value' in problem for problem in state['problems'])

def testTheWallMaterialRouteIsTheStoresSample(client):
    from NOVA import materials
    served = client.get('/api/materials/wall', params = {'name': 'Inconel 718', 'temperatureK': 900}).json()
    expected = materials.sampleWallMaterial('Inconel 718', 900.0)
    for key in ('temperatureK', 'thermalConductivity', 'density', 'elasticModulus', 'yieldStrength', 'cte', 'elongation'):
        assert served[key] == pytest.approx(expected[key], rel = 1e-12)
    assert served['material'] == 'Inconel 718' and served['fallback'] is False
    unknown = client.get('/api/materials/wall', params = {'name': 'Unobtainium', 'temperatureK': 300}).json()
    assert unknown['fallback'] is True and unknown['material'] == 'GRCop-42'
    assert client.get('/api/materials/wall', params = {'name': 'GRCop-42', 'temperatureK': 0}).status_code == 422

@pytest.mark.parametrize('name, filled', [
    ('ATJ Graphite', {'extensionThermalConductivity': 'thermalConductivity'}),
    ('C103', {'extensionInnerEmissivity': 'emissivity', 'extensionOuterEmissivity': 'emissivity'}),
    ('Carbon-Carbon (2D)', {}),
    ('Unobtainium', {}),
])
def testTheExtensionMaterialRouteFillsWhatTheStoreCarries(client, name, filled):
    '''Each filled field holds the store's first entry for the property; nothing else is filled.'''
    from NOVA import materials
    entry = client.get('/api/materials/extension', params = {'name': name}).json()
    expected = {}
    for key, source in filled.items():
        values = materials.surfaceEmissivity(name) if source == 'emissivity' else materials.materialProperty(name, source)
        expected[key] = float(next(iter(values.values())))
    assert entry['fill'] == pytest.approx(expected)
    if name == 'Unobtainium':
        assert 'not in the material store' in entry['note']
    else:
        assert entry['note'].startswith('Limit ')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Cooling figures -- #
#--------------------------------------------------------------------------------------------------------------------------#

_coolingRuns = os.path.join(root, 'featureShowcase', 'coolingRuns')

def _showcase(name: str):
    '''A showcase cooling run's Nozzle. The runs are local outputs, not in the repository.'''
    import pickle
    path = os.path.join(_coolingRuns, name + '.pkl')
    if not os.path.isfile(path):
        pytest.skip(f'{name}.pkl is a local showcase run and is not in this checkout')
    with open(path, 'rb') as handle:
        return pickle.load(handle)

def testEveryCoolingViewDrawsInteractive():
    from novaGui import views
    cooling = [spec for spec in views.viewList() if spec['group'] == 'Cooling']
    assert all(spec['interactive'] for spec in cooling)
    assert {spec['key'] for spec in cooling if spec['static']} == set(views._module('coolingFigures').builders)

def _matplotlibSeries(key: str, nozzle) -> list:
    '''The labelled lines of a view's Matplotlib drawing: [(label, x, y)], single points and levels left out.'''
    from novaGui import views
    function, *arguments = views._staticDrawers()[key]
    with views.renderLock:
        views._module('themeColors').bindPalette('dark')
        pane = views.HeadlessPane(900, 600, 1.0)
        function(pane, nozzle, *arguments)
    series = []
    for ax in pane.figure.axes:
        for line in ax.get_lines():
            label = str(line.get_label())
            if not label.startswith('_') and len(line.get_xdata()) >= 3:
                series.append((label, np.asarray(line.get_xdata(), dtype = float),
                               np.asarray(line.get_ydata(), dtype = float)))
    return series

@pytest.mark.parametrize('run, key', [('keroloxF1', key) for key in ('circuit', 'passes', 'jacketTemperatures', 'heatFlux',
                                                                     'extension')]
                         + [('NOVANozzle', 'film'), ('NOVANozzle', 'passes'), ('methaloxBooster', 'circuit'),
                            ('methaloxBooster', 'passes'), ('novaSinglePass', 'circuit')])
def testTheCoolingFiguresDrawTheMatplotlibSeries(run, key):
    '''
    A cross-check of the plotly builders against the Matplotlib drawers they port: every labelled
    series the drawer plots appears in the plotly figure under the same name with the same values.
    '''
    from novaGui import views
    nozzle = _showcase(run)
    series = _matplotlibSeries(key, nozzle)
    assert series
    figures = views._module('backend').figuresModule()
    with views.renderLock:
        figures.figurePalette.setFigureMode('dark')
        figure = views._module('coolingFigures').builders[key](figures, nozzle)
    for label, x, y in series:
        candidates = [trace for trace in figure.data if trace.name == label]
        assert any(np.size(trace.x) == x.size and np.allclose(np.asarray(trace.x, dtype = float), x)
                   and np.allclose(np.asarray(trace.y, dtype = float), y, equal_nan = True) for trace in candidates), label

def testTheUnlabelledPanelsDrawTheJacketArrays():
    '''The panels Matplotlib leaves unlabelled: coolant flow and properties, and the wall map's hover values.'''
    from novaGui import thermalPlots
    from novaGui import views
    nozzle = _showcase('keroloxF1')
    results = thermalPlots.thermalResults(nozzle)
    figures, builders = views._module('backend').figuresModule(), views._module('coolingFigures').builders
    with views.renderLock:
        figures.figurePalette.setFigureMode('dark')
        drawn = {key: builders[key](figures, nozzle) for key in ('coolantFlow', 'coolantProperties', 'wallMap')}
    expected = {
        ('coolantFlow', 'Pressure'):              np.asarray(results['pressure']) / 1e6,
        ('coolantFlow', 'Velocity'):              results['velocity'],
        ('coolantFlow', 'Mach number'):           results['machNumber'],
        ('coolantProperties', 'Density'):         results['density'],
        ('coolantProperties', 'Viscosity'):       np.asarray(results['viscosity']) * 1e6,
        ('coolantProperties', 'Specific heat'):   np.asarray(results['specificHeat']) * 1e-3,
    }
    for (key, name), values in expected.items():
        (trace,) = [trace for trace in drawn[key].data if trace.name == name]
        assert np.allclose(np.asarray(trace.y, dtype = float), np.asarray(values, dtype = float)), (key, name)
    hover = {trace.hovertemplate.split('<br>')[2].split(' %')[0]: trace for trace in drawn['wallMap'].data
             if trace.customdata is not None}
    assert np.allclose(hover['Hot wall'].customdata, thermalPlots._metalWall(results))
    assert np.allclose(hover['Coolant'].customdata, results['temperature'])

def testThePlumeTitleNamesTheInteractiveView():
    '''The reworded drawer text is still in the drawers, and rewording keeps the title's style.'''
    import inspect
    from matplotlib.figure import Figure
    from novaGui import views
    plotting = views._module('plotting')
    source = inspect.getsource(plotting._drawPlumeScene) + inspect.getsource(plotting._drawCorrelatedPlume)
    for old in views.staticTextOverrides:
        assert old in source
    figure = Figure()
    ax = figure.add_subplot()
    ax.set_title('Mach disk lies beyond the march; Open interactive shows them', color = '#123456', fontsize = 10)
    views._overrideText(figure)
    assert ax.get_title() == 'Mach disk lies beyond the march; the interactive view shows them'
    assert ax.title.get_fontsize() == 10 and ax.title.get_color() == '#123456'

#--------------------------------------------------------------------------------------------------------------------------#
# -- Palette -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheLinePlotsDrawTheBaselineDashedOverTheShownRun():
    '''
    The second run's lines are added dashed in their own colors, named for it; its fills are not,
    and the title says which run is which. A field view is not overlaid.
    '''
    import json
    from novaGui import views
    shown, baseline = _showcase('NOVANozzle'), _showcase('novaSinglePass')
    alone = json.loads(views.interactiveFigure(shown, 'jacketTemperatures', 'dark'))
    other = json.loads(views.interactiveFigure(baseline, 'jacketTemperatures', 'dark'))
    both = json.loads(views.interactiveFigure(shown, 'jacketTemperatures', 'dark', compare = baseline,
                                              labels = ('run 3', 'run 1')))
    lines = [trace for trace in other['data'] if 'lines' in trace.get('mode', 'lines') and trace.get('fill') in (None, 'none')]
    added = both['data'][len(alone['data']):]
    assert len(added) == len(lines) and len(lines) < len(other['data'])
    assert all(trace['line']['dash'] == 'dash' and trace['name'].endswith(', run 1') for trace in added)
    assert [trace['line'].get('color') for trace in added] == [trace['line'].get('color') for trace in lines]
    assert 'solid: run 3, dashed: run 1' in both['layout']['title']['text']
    field = json.loads(views.interactiveFigure(shown, 'mach', 'dark', compare = baseline))
    assert len(field['data']) == len(json.loads(views.interactiveFigure(shown, 'mach', 'dark'))['data'])

def testTheFilledFieldShadesInsideTheWallOnly():
    '''
    The filled field is NaN outside the wall and inside it stays within the solved nodes' range,
    since linear interpolation over triangles and the nearest node cannot leave it.
    '''
    from NOVA import figures
    nozzle = _showcase('NOVANozzle')
    data = figures.stitchedFieldFigure(nozzle, 'mach')
    figure = figures.plotlyField(data, filled = True)
    heatmap = figure.data[0]
    x, r, z = np.asarray(heatmap.x), np.asarray(heatmap.y), np.asarray(heatmap.z, dtype = float)
    wallX, wallR = np.asarray(data.wallX), np.asarray(data.wallR)
    wall = np.interp(x, wallX[np.argsort(wallX)], wallR[np.argsort(wallX)])
    outside = np.abs(r)[:, None] > wall[None, :] * 1.0001
    assert np.all(np.isnan(z[outside]))
    inside = np.abs(r)[:, None] < wall[None, :] * 0.98
    assert np.isfinite(z[inside]).mean() > 0.999
    nodes = np.concatenate([np.ravel(data.meshValues), np.ravel(data.upstreamValues)])
    assert np.nanmin(z) >= np.nanmin(nodes) - 1e-6 and np.nanmax(z) <= np.nanmax(nodes) + 1e-6
    assert figure.data[1].name == 'Solution nodes' and figure.data[1].visible == 'legendonly'

def testThePaletteStylesheetMatchesThePythonPalette():
    '''
    The front end reads the palette from a committed stylesheet. It must be what
    `python -m novaGui.paletteCss` writes from novaGui.themeColors.palettes today.
    '''
    with open(paletteCss.cssPath, encoding = 'utf-8') as handle:
        assert handle.read() == paletteCss.cssText()

#--------------------------------------------------------------------------------------------------------------------------#
# -- Run sessions -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _waitForEnd(session: RunSession, timeoutSec: float) -> None:
    deadline = time.time() + timeoutSec
    while session.busy and time.time() < deadline:
        time.sleep(0.25)
    assert not session.busy, 'the run did not end in time'

def testARejectedConfigEndsTheRunWithItsError(tmp_path):
    '''
    A config NOVA refuses ends the run as an error, carries NOVA's message, and logs the traceback.
    The run's store folder goes with it.
    '''
    store = RunStore(str(tmp_path))
    session = RunSession(store = store)
    try:
        config = configSchema.defaultConfig()
        config['divergingSectionType'] = 'notAContour'
        runId = session.start(config, 'dark')
        assert os.path.isdir(store.folder(runId))
        _waitForEnd(session, 120.0)
        assert session.state['state'] == 'error'
        assert session.result is not None and not session.result.ok
        assert session.result.error
        assert any('Traceback' in line for line in session.log)
        assert not os.path.isdir(store.folder(runId)) and session.runList()['runs'] == []
    finally:
        session.shutdown()

def _contourRunning(session) -> bool:
    '''Whether the session's run has reported its contour stage open.'''
    return any(stage['key'] == 'contour' and stage['state'] == 'running' for stage in session.state['stages'])

def testACancelledRunEndsCancelledAndFreesTheSession(tmp_path):
    '''
    Cancel terminates the worker mid-solve; the session reports it cancelled, removes the run's store
    folder, and takes another run.
    '''
    store = RunStore(str(tmp_path))
    session = RunSession(store = store)
    try:
        runId = session.start(configSchema.defaultConfig(), 'dark')
        deadline = time.time() + 90.0
        while not _contourRunning(session) and time.time() < deadline:
            time.sleep(0.25)
        assert _contourRunning(session), 'the run never reached the contour solve'
        with pytest.raises(RuntimeError):
            session.start(configSchema.defaultConfig(), 'dark')
        assert session.cancel()
        _waitForEnd(session, 30.0)
        assert session.state['state'] == 'cancelled'
        assert not session.cancel()
        assert not os.path.isdir(store.folder(runId)) and os.listdir(store.root) == [runStore.indexName]
    finally:
        session.shutdown()

def testARunSendsItsContourFiguresBeforeItEnds():
    '''
    When the contour stage ends, the worker sends the contour, the near-wall state and the flow
    fields; the session keeps them as the run's partial result and draws them on request.
    '''
    from novaGui import views
    session = RunSession()
    try:
        runId = session.start(configSchema.defaultConfig(), 'dark')
        deadline = time.time() + 240.0
        while session.partial is None and session.busy and time.time() < deadline:
            time.sleep(0.5)
        assert session.partial is not None, 'the run never sent its contour figures'
        assert session.partial['runId'] == runId
        assert {'contour', 'nearWall', 'mach', 'pressure', 'temperature'} <= set(session.partial['figures'])
        assert session.runList()['running']['views'] == list(session.partial['figures'])
        figure = views.partialFigure(session.partialFigure(runId, 'mach'), 'mach', 'dark')
        assert figure is not None and '"heatmap"' in figure
        assert session.cancel()
        _waitForEnd(session, 30.0)
        assert session.partial is None and session.state['state'] == 'cancelled'
    finally:
        session.shutdown()
