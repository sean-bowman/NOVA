# -- NOVA: Web Front End Server Tests -- #

'''

The web front end's server: the Design form schema it serializes, the dependency predicates it
evaluates, the unit table it hands the browser, the routes that read files, the result table, the
export routes, the palette stylesheet, and a run session's error and cancel paths.

The schema, unit, route, result table, export and palette tests need neither a run nor a display;
the result table and export tests stand a finished run in with a Nozzle stand-in and files in a
temporary folder. The session tests
start real worker processes: one on a config NOVA rejects, one cancelled during the contour
solve. Together they take about half a minute.

Author: Sean Bowman

'''

import math
import os
import sys
import time
import types

import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

fastapi = pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from NOVA import units as novaUnits
from novaGui import configSchema
from novaWeb import analysis, outputs, paletteCss, schemaJson
from novaWeb.server import createApp
from novaWeb.session import RunRecord, RunSession

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
    from novaGui.tabs import viewTab

    index = client.get('/api/views').json()
    assert [view['key'] for view in index['views']] == [spec.key for spec in viewTab.views]
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

_outputBytes = {
    'machContours.png':          b'p' * 2048,
    'contourInteractive.html':   b'<html></html>',
    'testEngineHotWall.txt':     b'0.0 0.05\n',
    'testEngine.pkl':            b'\x80\x04N.',
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
    session.result = record
    yield record
    session.result = None

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
        'testEngineHotWall.txt': 'contours', 'testEngine.pkl': 'nozzle', 'testEngineRunConfig.json': 'config'}
    assert files['machContours.png']['bytes'] == 2048

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
# -- Palette -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testThePaletteStylesheetMatchesThePythonPalette():
    '''
    The front end reads the palette from a committed stylesheet. It must be what
    `python -m novaWeb.paletteCss` writes from novaGui.theme.palettes today.
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

def testARejectedConfigEndsTheRunWithItsError():
    '''
    A config NOVA refuses ends the run as an error, carries NOVA's message, and logs the traceback.
    '''
    session = RunSession()
    try:
        config = configSchema.defaultConfig()
        config['divergingSectionType'] = 'notAContour'
        session.start(config, 'dark')
        _waitForEnd(session, 120.0)
        assert session.state['state'] == 'error'
        assert session.result is not None and not session.result.ok
        assert session.result.error
        assert any('Traceback' in line for line in session.log)
    finally:
        session.shutdown()

def testACancelledRunEndsCancelledAndFreesTheSession():
    '''
    Cancel terminates the worker mid-solve; the session reports it cancelled and takes another run.
    '''
    session = RunSession()
    try:
        session.start(configSchema.defaultConfig(), 'dark')
        deadline = time.time() + 90.0
        while session.state['fraction'] < 0.08 and time.time() < deadline:
            time.sleep(0.25)
        assert session.state['fraction'] >= 0.08, 'the run never reached the contour solve'
        with pytest.raises(RuntimeError):
            session.start(configSchema.defaultConfig(), 'dark')
        assert session.cancel()
        _waitForEnd(session, 30.0)
        assert session.state['state'] == 'cancelled'
        assert not session.cancel()
    finally:
        session.shutdown()
