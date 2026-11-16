# -- NOVA: Web Front End Server Tests -- #

'''

The web front end's server: the Design form schema it serializes, the dependency predicates it
evaluates, the unit table it hands the browser, the routes that read files, the palette
stylesheet, and a run session's error and cancel paths.

The schema, unit, route and palette tests need neither a run nor a display. The session tests
start real worker processes: one on a config NOVA rejects, one cancelled during the contour
solve. Together they take about half a minute.

Author: Sean Bowman

'''

import os
import sys
import time

import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

fastapi = pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from NOVA import units as novaUnits
from novaGui import configSchema
from novaWeb import paletteCss, schemaJson
from novaWeb.server import createApp
from novaWeb.session import RunSession

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
