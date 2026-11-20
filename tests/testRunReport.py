# -- NOVA: GUI Report Tests -- #

'''

The reports the GUI writes (novaGui.report): a config value in words, the inputs that differ from
the shipped nozzle, a run's report alone and against a baseline, a sweep's report and its plot.

A report is sent to someone without the GUI, so the tests hold it to standing alone: every image
is written into the file, nothing loads from the network, and no folder of the machine that wrote
it appears. The run reports read the showcase cooling runs under featureShowcase/coolingRuns,
which are local outputs that git ignores, and skip without them; the sweep report of scripted runs
(tests/testSweeps.py) needs no run at all.

Author: Sean Bowman

'''

import json
import os
import pickle
import re
import sys
import time

import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for folder in (root, os.path.join(root, 'tests')):
    if folder not in sys.path:
        sys.path.insert(0, folder)

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from novaGui import analysis, configSchema, report, sweeps
from novaGui.server import createApp
from novaGui.session import RunRecord, RunSession
from novaGui.worker import headlineNumbers
from testSweeps import _scripted, _settled, failingPressure

showcaseFolder = os.path.join(root, 'featureShowcase', 'coolingRuns')
showcaseRuns = ['novaSinglePass', 'hydroloxVulcain', 'NOVANozzle']     # kept as runs 1, 2, 3
keptWarning = {'category': 'UserWarning', 'message': 'The LOX card has no editable t(k)/h field.',
               'where': 'ceaInterface.py:429', 'count': 2}

def _standsAlone(page: str) -> None:

    '''Every image is in the file, nothing loads from the network, and no local folder is named.'''

    sources = re.findall(r'<img[^>]+src="([^"]*)"', page)
    assert all(source.startswith('data:image/png;base64,') for source in sources)
    assert not re.search(r'(src|href)="(https?:)?//', page) and '<script' not in page
    home = os.path.expanduser('~')
    for marker in (home, home.replace('\\', '/'), 'AppData', root):
        assert marker not in page, marker

#--------------------------------------------------------------------------------------------------------------------------#
# -- Values in words -- #
#--------------------------------------------------------------------------------------------------------------------------#
@pytest.mark.parametrize('value, dimension, unit, text', [
    (6894757.0, 'pressure', 'Pa', '6894.8 kPa'),
    (8.0e6, 'pressure', 'Pa', '8000 kPa'),
    (0.18, 'length', 'm', '0.18 m'),
    (1.0e5, 'force', 'N', '100 kN'),
    (0.0, 'pressure', 'Pa', '0 Pa'),
    (5.5, None, '', '5.5'),
    (40.0, None, 'deg', '40 deg'),
])
def testANumberReadsInTheFirstUnitItFitsAsTheGuiWritesIt(value, dimension, unit, text):
    assert report.numberText(value, dimension, unit) == text

def testAConfigValueReadsAsTheFormShowsIt():
    specs = {spec.key: spec for spec in configSchema.allFields()}
    assert report.valueText(specs['filmCooling'], True) == 'on'
    assert report.valueText(specs['filmCooling'], 'off') == 'off'
    assert report.valueText(specs['divergingSectionType'], 'tic') == 'Truncated ideal contour (tic)'
    assert report.valueText(specs['plumeAmbientPressure'], None) == 'blank'

def testTheInputsAreTheFieldsThatDifferInFormOrder():
    shipped = configSchema.defaultConfig()
    assert report.inputRows(shipped, [shipped]) == []
    changed = {**shipped, 'chamberPressure': 8.0e6, 'Fuel': 'CH4', 'filename': 'other', 'plotsEnabled': False}
    rows = report.inputRows(changed, [shipped])
    assert [(row['label'], row['values']) for row in rows] == [('Fuel', ['CH4', 'LH2']),
                                                               ('Chamber pressure', ['8000 kPa', '6894.8 kPa'])]
    baseline = {**shipped, 'chamberPressure': 8.0e6}
    rows = report.inputRows(changed, [shipped, baseline])
    assert [row['values'] for row in rows] == [['CH4', 'LH2', 'LH2'], ['8000 kPa', '6894.8 kPa', '8000 kPa']]

#--------------------------------------------------------------------------------------------------------------------------#
# -- A sweep's report with no run behind it -- #
#--------------------------------------------------------------------------------------------------------------------------#
def testASweepOfScriptedRunsReportsItsPointsAndPlot():
    '''
    A sweep's report needs only the numbers its runs recorded: the ranges, the plot with a gap at
    the failed point, the points in order with the failed point's reason, and the swept field among
    the inputs.
    '''
    session = _scripted()
    try:
        sweep = session.addSweep(sweeps.build({'name': 'Pressure trade', 'config': configSchema.defaultConfig(),
                                               'fields': [{'key': 'chamberPressure', 'unit': 'MPa',
                                                           'values': [6.0e6, failingPressure, 8.0e6]}]}))
        _settled(session)
        with TestClient(createApp(session = session, warm = False)) as client:
            response = client.get(f'/api/sweeps/{sweep["sweepId"]}/report')
            assert client.get('/api/sweeps/99/report').status_code == 404
        page = response.text
        assert response.status_code == 200 and response.headers['content-type'].startswith('text/html')
        _standsAlone(page)
        assert '<h1 class="hero-title">Pressure trade</h1>' in page
        assert 'Chamber pressure over 6 MPa, 7 MPa, 8 MPa' in page
        assert '300.0 to 400.0' in page and 'across 2 of 3 points' in page
        assert page.count('<img class="figure-dark"') == 1 and page.count('<img class="figure-light"') == 1
        assert 'the scripted run failed' in page and '2 of 3 done, 1 failed' in page
        assert re.search(r'<td class="muted">Swept</td><td>Chamber pressure</td><td class="value">6 MPa, 7 MPa, 8 MPa</td>', page)
    finally:
        session.shutdown()

def testASweepPlotDrawsEveryNumberAndNoneWithoutResults():
    table = {'fields': [{'key': 'chamberPressure', 'label': 'Chamber pressure', 'kind': 'float', 'dimension': 'pressure',
                         'unit': 'MPa', 'values': [6.0e6, 7.0e6, 8.0e6], 'texts': ['6 MPa', '7 MPa', '8 MPa']}],
             'numbers': [], 'points': []}
    assert report.sweepFigurePng(table, 'dark') is None
    numbers = [{'key': 'isp', 'label': 'Delivered Isp', 'unit': 's'}, {'key': 'thrust', 'label': 'Delivered thrust', 'unit': 'kN'}]
    points = [{'at': [index], 'numbers': {} if index == 1 else {'isp': {'value': 440.0 + index}, 'thrust': {'value': 100.0}}}
              for index in range(3)]
    for mode in ('dark', 'light'):
        assert report.sweepFigurePng({**table, 'numbers': numbers, 'points': points}, mode)[:8] == b'\x89PNG\r\n\x1a\n'

#--------------------------------------------------------------------------------------------------------------------------#
# -- Reports of the showcase runs -- #
#--------------------------------------------------------------------------------------------------------------------------#
@pytest.fixture(scope = 'module')
def showcase():
    '''A server keeping the three showcase runs, the newest named with a note and a warning, all three a sweep's points.'''
    for name in showcaseRuns:
        if not os.path.isfile(os.path.join(showcaseFolder, name + '.pkl')):
            pytest.skip(f'{name}.pkl is a local showcase run and is not in this checkout')
    session = RunSession()
    shipped = configSchema.defaultConfig()
    for runId, name in enumerate(showcaseRuns, 1):
        with open(os.path.join(showcaseFolder, name + '.json'), encoding = 'utf-8') as handle:
            config = {**shipped, **json.load(handle)}
        picklePath = os.path.join(showcaseFolder, name + '.pkl')
        with open(picklePath, 'rb') as handle:
            nozzle = pickle.load(handle)
        session.adopt(RunRecord(runId, {'ok': True, 'runName': name, 'picklePath': picklePath, 'elapsedSec': 240.0 + 30.0 * runId,
                                        'headline': analysis.resultRows(nozzle)[0], 'numbers': headlineNumbers(nozzle)},
                                config = config, warnings = [keptWarning] if runId == 3 else None,
                                sweep = {'sweepId': 1, 'index': runId - 1}))
    session.describe(3, title = 'Shipped nozzle', note = 'The one-and-a-half pass jacket as shipped.')
    sweep = sweeps.build({'name': '', 'config': shipped, 'fields': [
        {'key': 'chamberPressure', 'unit': 'MPa', 'values': [5.0e6, 6.0e6, 7.0e6]}]})
    sweep = {**sweep, 'sweepId': 1, 'mode': 'dark'}
    for runId in (1, 2, 3):
        sweep['points'][runId - 1].update(state = 'done', runId = runId)
    session.sweeps[1] = sweep
    with TestClient(createApp(session = session, warm = False)) as client:
        yield client
    session.shutdown()

def testARunsReportStandsAloneWithItsNumbersFiguresAndValidation(showcase):
    started = time.time()
    response = showcase.get('/api/report', params = {'run': 3})
    elapsed = time.time() - started
    page = response.text
    assert response.status_code == 200 and response.headers['content-type'].startswith('text/html')
    _standsAlone(page)
    assert elapsed < 30.0 and len(page) < 4e6
    for section in ('summary', 'inputs', 'results', 'figures', 'warnings', 'validation', 'config'):
        assert f'<section id="{section}">' in page
    assert '<h1 class="hero-title">Shipped nozzle</h1>' in page and 'The one-and-a-half pass jacket as shipped.' in page
    assert 'Delivered Isp' in page and 'Unvalidated' in page and 'Cross-checked' in page
    # The figures the run has, each in both modes
    assert page.count('<img class="figure-dark"') == page.count('<img class="figure-light"') >= 3
    assert 'The LOX card has no editable t(k)/h field.' in page and '2 times' in page
    assert 'not a check of these particular numbers' in page
    assert '<summary>NOVANozzleRunConfig.json</summary>' in page

def testAReportAgainstTheBaselineSetsItBeside(showcase):
    page = showcase.get('/api/report', params = {'run': 3, 'baseline': 1}).text
    assert 'against run 1 (novaSinglePass) as the baseline' in page
    assert '<th>Run 3</th><th>Shipped nozzle</th><th>Run 1</th>' in page
    assert '<th class="num">Run 3</th><th class="num">Run 1</th><th class="num">Change</th>' in page
    assert 'against run 1' in page and 'not in run 1' in page
    assert re.search(r'Coolant circuit</td><td class="value">B\. One and a half pass</td>.*?A\. Single pass', page)

def testAReportOfARunNotKeptIsRefused(showcase):
    assert showcase.get('/api/report', params = {'run': 99}).status_code == 404

def testAShowcaseSweepsReportCarriesEveryNumbersStatus(showcase):
    page = showcase.get('/api/sweeps/1/report').text
    _standsAlone(page)
    cards = re.findall(r'<div class="summary-card".*?</div></div>', page)
    assert len(cards) >= 5 and all('status-badge' in card for card in cards)
    assert '3 of 3 done' in page and 'Chamber pressure over 5 MPa, 6 MPa, 7 MPa' in page
