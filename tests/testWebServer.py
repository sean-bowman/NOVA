# -- NOVA: Web Front End Server Tests -- #

'''

The web front end's server: the Design form schema it serializes, the dependency predicates it
evaluates, the unit table it hands the browser, the routes that read files, the cross-field checks
and the material routes, the result table, the export routes, the cooling figures, the palette
stylesheet, and a run session's error and cancel paths.

The schema, unit, route, design, result table, export and palette tests need neither a run nor a
display; the result table and export tests stand a finished run in with a Nozzle stand-in and files
in a temporary folder. The cooling figure tests read the showcase cooling runs under
featureShowcase/coolingRuns, which are local outputs and not in the repository; without them they
skip. They cross-check each plotly builder against the Matplotlib drawer it ports. The session
tests start real worker processes: one on a config NOVA rejects, one cancelled during the contour
solve. Together they take about a minute.

Author: Sean Bowman

'''

import math
import os
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
    ({'makeCoolingChannels': False, 'makeInletVolute': True}, 'Volute generation requires cooling channels to be enabled.',
     None),
])
def testTheCrossFieldChecksAreTheTkinterForms(client, changes, problem, flagged):
    '''The problems are ConfigTab.validate's own words, and the row a problem quotes is flagged.'''
    state = client.post('/api/schema/state', json = _withDefaults(**changes)).json()
    assert problem in state['problems']
    if flagged is not None:
        assert flagged in state['flagged']

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
    from novaWeb import views
    cooling = [spec for spec in views.viewList() if spec['group'] == 'Cooling']
    assert all(spec['interactive'] for spec in cooling)
    assert {spec['key'] for spec in cooling if spec['static']} == set(views._module('coolingFigures').builders)

def _matplotlibSeries(key: str, nozzle) -> list:
    '''The labelled lines of a view's Matplotlib drawing: [(label, x, y)], single points and levels left out.'''
    from novaWeb import views
    function, *arguments = views._staticDrawers()[key]
    with views.renderLock:
        views._module('theme')._bindPalette('dark')
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
    from novaWeb import views
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
    from novaWeb import views
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

def testThePlumeTitleNamesTheInteractiveRendering():
    '''The reworded drawer text is still in the drawers, and rewording keeps the title's style.'''
    import inspect
    from matplotlib.figure import Figure
    from novaWeb import views
    plotting = views._module('plotting')
    source = inspect.getsource(plotting._drawPlumeScene) + inspect.getsource(plotting._drawCorrelatedPlume)
    for old in views.staticTextOverrides:
        assert old in source
    figure = Figure()
    ax = figure.add_subplot()
    ax.set_title('Mach disk lies beyond the march; Open interactive shows them', color = '#123456', fontsize = 10)
    views._overrideText(figure)
    assert ax.get_title() == 'Mach disk lies beyond the march; the Interactive rendering shows them'
    assert ax.title.get_fontsize() == 10 and ax.title.get_color() == '#123456'

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

def _contourRunning(session) -> bool:
    '''Whether the session's run has reported its contour stage open.'''
    return any(stage['key'] == 'contour' and stage['state'] == 'running' for stage in session.state['stages'])

def testACancelledRunEndsCancelledAndFreesTheSession():
    '''
    Cancel terminates the worker mid-solve; the session reports it cancelled and takes another run.
    '''
    session = RunSession()
    try:
        session.start(configSchema.defaultConfig(), 'dark')
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
    finally:
        session.shutdown()
