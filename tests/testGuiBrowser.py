# -- NOVA: GUI Browser Tests -- #

'''

The GUI's front end in a browser: the run menu, a run's name and note, putting a run's config back
into the form, deleting a run, the baseline drawn under a line plot, the grid's shared cursor and
zoom along the nozzle axis, the headline numbers and a row that opens its figure, the section
outline, a problem written under its field, the warnings of a run, the export previews, a figure
popped out into its own window, compressed figure responses, a trade sweep's plot and table, the
sweep dialog's request, and the run queue.

The sweep view reads the showcase runs as the points of a sweep the test lays out; the sweep
dialog's request is caught before it reaches the server, and the queue holds runs that never
start, so no test makes a run.

The GUI's server starts in this process, keeping three showcase cooling runs as if they had just
run, so no run is made; Playwright's Chromium drives the built front end. The tests read the
showcase runs under featureShowcase/coolingRuns and their outputs under
featureShowcase/showcaseBaseOutputs, which are local outputs that git ignores, and skip without
them, without Playwright and its Chromium, or without the built front end
(`npm run build` in novaGui/frontend). They take about a minute.

Every test fails on a console error in the page.

Author: Sean Bowman

'''

import json
import os
import pickle
import sys
import threading

import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

pytest.importorskip('fastapi')
syncApi = pytest.importorskip('playwright.sync_api')

from novaGui import analysis, configSchema, sweeps
from novaGui.__main__ import _freePort, _serve, _waitUntilStarted
from novaGui.server import createApp, frontendDist
from novaGui.session import QueuedRun, RunRecord, RunSession
from novaGui.worker import headlineNumbers

showcaseFolder = os.path.join(root, 'featureShowcase', 'coolingRuns')
outputsFolder = os.path.join(root, 'featureShowcase', 'showcaseBaseOutputs')
showcaseRuns = ['novaSinglePass', 'hydroloxVulcain', 'NOVANozzle']     # kept as runs 1, 2, 3
keptWarning = {'category': 'UserWarning', 'message': 'The LOX card has no editable t(k)/h field; using it unchanged at 90.17 K.',
               'where': 'ceaInterface.py:429', 'count': 2}
viewport = {'width': 1600, 'height': 960}       # [px]
largeViewport = {'width': 1920, 'height': 1080} # [px] a second monitor, where the grid holds two views a row
drawMs = 60000                                  # [ms] longest wait for a figure

def _skipWithout() -> None:
    for name in showcaseRuns:
        if not os.path.isfile(os.path.join(showcaseFolder, name + '.pkl')):
            pytest.skip(f'{name}.pkl is a local showcase run and is not in this checkout')
    if not os.path.isdir(outputsFolder):
        pytest.skip('the showcase outputs are local and not in this checkout')
    if not os.path.isfile(os.path.join(frontendDist, 'index.html')):
        pytest.skip('the front end is not built')

@pytest.fixture(scope = 'module')
def served():
    '''The GUI's server with the showcase runs kept, the newest carrying a warning; its URL.'''
    _skipWithout()
    session = RunSession()
    for runId, name in enumerate(showcaseRuns, 1):
        with open(os.path.join(showcaseFolder, name + '.json'), encoding = 'utf-8') as handle:
            config = {**configSchema.defaultConfig(), **json.load(handle)}
        picklePath = os.path.join(showcaseFolder, name + '.pkl')
        with open(picklePath, 'rb') as handle:
            nozzle = pickle.load(handle)
        record = RunRecord(runId, {'ok': True, 'runName': name, 'picklePath': picklePath, 'outputDir': outputsFolder,
                                   'elapsedSec': 240.0 + 30.0 * runId, 'headline': analysis.resultRows(nozzle)[0],
                                   'numbers': headlineNumbers(nozzle)},
                           config = config, warnings = [keptWarning] if runId == len(showcaseRuns) else None)
        session.adopt(record)
    app = createApp(session = session)
    server = _serve(app, _freePort())
    thread = threading.Thread(target = server.run, name = 'novaTestServer', daemon = True)
    thread.start()
    try:
        assert _waitUntilStarted(server), 'the GUI server did not start'
        yield app, f'http://127.0.0.1:{server.config.port}/'
    finally:
        server.should_exit = True
        thread.join(timeout = 5.0)
        session.shutdown()

@pytest.fixture(scope = 'module')
def browser():
    with syncApi.sync_playwright() as playwright:
        try:
            launched = playwright.chromium.launch()
        except Exception as exc:                           # noqa: BLE001 -- no browser installed
            pytest.skip(f'Playwright has no Chromium: {exc}')
        yield launched
        launched.close()

@pytest.fixture
def window(browser, served):
    '''A fresh page on the GUI, with the baseline cleared after; fails the test on a console error.'''
    app, url = served
    context = browser.new_context(viewport = viewport)
    page = context.new_page()
    errors = []
    page.on('console', lambda message: message.type == 'error' and errors.append(message.text))
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(url)
    page.wait_for_selector('.run-select:not([disabled])')
    _drawn(page, 1)
    yield page
    app.state.session.setBaseline(None)
    context.close()
    assert errors == [], errors

def _drawn(page, count: int) -> None:
    '''Wait until `count` figures have drawn and none is loading.'''
    page.wait_for_function(f'document.querySelectorAll(".plotly-host .main-svg").length >= {count}', timeout = drawMs)
    page.wait_for_function('!document.querySelector(".figure-overlay .spinner")', timeout = drawMs)
    page.wait_for_timeout(500)

def _plotArea(page, index: int) -> tuple:
    '''The middle of the first subplot of the `index`th figure, in page coordinates.'''
    host = page.locator('.plotly-host').nth(index)
    box = host.bounding_box()
    left, width, top, height = host.evaluate('element => { const f = element._fullLayout; '
                                             'return [f.xaxis._offset, f.xaxis._length, f.yaxis._offset, f.yaxis._length]; }')
    return box['x'] + left, width, box['y'] + top, height

def _grid(page) -> None:
    page.set_viewport_size(largeViewport)
    page.locator('.figure-toolbar .segmented button', has_text = 'Grid').click()
    page.wait_for_function('document.querySelectorAll(".figure-cell").length === 4')
    _drawn(page, 4)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Kept runs and the baseline -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheRunMenuListsTheKeptRunsNewestFirst(window):
    options = window.eval_on_selector_all('.run-select option', 'options => options.map(o => o.textContent)')
    assert options[0].startswith('Latest: run 3') and '100 kN' in options[0]
    assert [option.split(' ')[1] for option in options[1:]] == ['3', '2', '1']
    assert 'NOVANozzle' in options[1] and '5:30' in options[1]

def _details(page) -> None:
    '''Open the shown run's details.'''
    page.locator('.result-head .icon-button[aria-label^="Details of run"]').click()
    page.wait_for_selector('.run-details')

def testARunTakesANameAndANote(window, served):
    '''The name shows in the run menu and the note in its tooltip; both hold when the details open again.'''
    app, _ = served
    try:
        _details(window)
        assert window.input_value('.run-details input') == '' and window.inner_text('.run-details h2') == 'Run 3'
        window.fill('.run-details input', '  Shipped   nozzle ')
        window.fill('.run-details textarea', 'The single pass jacket for comparison.')
        window.keyboard.press('Escape')
        window.wait_for_selector('.run-details', state = 'detached')
        window.wait_for_function('document.querySelector(".run-select option[value=\'3\']").textContent.includes("Shipped nozzle")')
        assert window.locator('.run-select option[value="3"]').inner_text().startswith('Run 3 · Shipped nozzle · 100 kN')
        assert window.get_attribute('.run-select', 'title').endswith('The single pass jacket for comparison.')
        assert (app.state.session.record(3).title, app.state.session.record(3).note) == \
            ('Shipped nozzle', 'The single pass jacket for comparison.')
        _details(window)
        assert window.input_value('.run-details input') == 'Shipped nozzle'
    finally:
        app.state.session.describe(3, title = '', note = '')

def testEditFromARunPutsItsConfigInTheForm(window):
    '''
    Showing a run whose config differs from the form offers to put it back; afterwards the form
    reads as that run did, so the strip names no changes.
    '''
    window.select_option('.run-select', '1')
    strip = window.locator('.result-status.is-warn')
    strip.wait_for()
    assert 'changed since it ran' in strip.inner_text()
    strip.get_by_role('button', name = 'Edit from run 1').click()
    window.wait_for_selector('.result-status.is-warn', state = 'detached')
    assert "Run 1's config is in the form" in window.inner_text('.toasts')

def testADeletedRunLeavesTheMenu(window, served):
    '''Delete asks once more, then the run leaves the menu and the pane goes back to the latest.'''
    app, _ = served
    session = app.state.session
    picklePath = os.path.join(showcaseFolder, showcaseRuns[0] + '.pkl')
    session.adopt(RunRecord(4, {'ok': True, 'runName': 'throwaway', 'picklePath': picklePath, 'elapsedSec': 60.0},
                            config = session.record(1).config))
    try:
        window.wait_for_selector('.run-select option[value="4"]', state = 'attached')
        window.select_option('.run-select', '4')
        _details(window)
        window.get_by_role('button', name = 'Delete run').click()
        assert window.inner_text('.run-details-confirm').startswith('Delete run 4 and its files?')
        window.locator('.run-details-confirm .button-danger').click()
        window.wait_for_selector('.run-details', state = 'detached')
        window.wait_for_selector('.run-select option[value="4"]', state = 'detached')
        assert session.record(4) is None and window.input_value('.run-select') == 'latest'
        assert window.locator('.run-select option').first.inner_text().startswith('Latest: run 3')
    finally:
        session.forget(4)

def testTheBaselineDrawsDashedUnderALinePlot(window):
    window.select_option('.baseline-select', '1')
    window.wait_for_selector('.result-status.is-baseline')
    assert window.inner_text('.result-status.is-baseline').startswith('Against run 1, the baseline:')
    window.select_option('.figure-toolbar > .view-select', 'jacketTemperatures')
    # The figure is replaced as the baseline arrives; the check waits for one that is drawn
    window.wait_for_function('(() => { const graph = document.querySelector(".js-plotly-plot"); '
                             'return !!(graph && graph.data && graph.data.some(t => (t.name || "").endsWith("run 1, baseline"))); })()',
                             timeout = drawMs)
    dashes = window.evaluate('''() => document.querySelector('.js-plotly-plot').data
                                    .filter(t => (t.name || '').endsWith('run 1, baseline')).map(t => t.line.dash)''')
    assert dashes and set(dashes) == {'dash'}

def testTheShownRunsWarningsAreListed(window):
    strip = window.locator('.result-status.is-caution')
    assert strip.inner_text().startswith('Run 3 raised a warning')
    assert 'ceaInterface.py:429, 2 times' in strip.locator('.warning-list').inner_text()
    window.select_option('.run-select', '2')
    window.wait_for_selector('.result-status.is-caution', state = 'detached')

#--------------------------------------------------------------------------------------------------------------------------#
# -- The grid along the nozzle axis -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheGridSharesOneCursorAndReadsTheContourToo(window):
    '''
    The mouse over one figure marks the same station on every figure of the grid, and the figures
    that hover along the axis, the contour among them, read their values there.
    '''
    _grid(window)
    left, width, top, height = _plotArea(window, 1)
    for share in (0.40, 0.45):
        window.mouse.move(left + share * width, top + 0.5 * height)
        window.wait_for_timeout(300)
    window.wait_for_timeout(500)
    lines = window.eval_on_selector_all('.figure-cell', 'cells => cells.map(c => c.querySelectorAll(".axial-cursor").length)')
    labels = window.eval_on_selector_all('.axial-cursor-label', 'labels => labels.map(l => l.textContent)')
    hovers = window.eval_on_selector_all('.figure-cell', 'cells => cells.map(c => c.querySelectorAll(".hoverlayer .legend, .hoverlayer .hovertext").length)')
    assert all(count > 0 for count in lines) and len(lines) == 4
    assert len(labels) == 4 and len(set(labels)) == 1
    assert window.input_value('.figure-cell .view-select') == 'contour' and hovers[0] > 0
    assert all(count > 0 for count in hovers[2:])

def testAZoomAlongTheAxisZoomsEveryFigure(window):
    _grid(window)
    left, width, top, height = _plotArea(window, 1)
    window.mouse.move(left + 0.3 * width, top + 0.5 * height)
    window.mouse.down()
    window.mouse.move(left + 0.6 * width, top + 0.5 * height, steps = 8)
    window.mouse.up()
    window.wait_for_timeout(1200)
    ranges = window.eval_on_selector_all('.figure-cell .js-plotly-plot', '''graphs => graphs.map(g => {
        const f = g._fullLayout; const names = Object.keys(f).filter(n => /^xaxis\\d*$/.test(n));
        return names.map(n => f[n].range.map(v => v.toFixed(4)).join('..')); })''')
    zoomed = {span for figure in ranges for span in figure}
    assert len(zoomed) == 1, ranges

def testFigureResponsesAreCompressed(window):
    encodings = []
    window.on('response', lambda response: '/interactive' in response.url
              and encodings.append(response.headers.get('content-encoding')))
    window.select_option('.figure-toolbar > .view-select', 'mach')
    _drawn(window, 1)
    assert encodings and set(encodings) == {'gzip'}

#--------------------------------------------------------------------------------------------------------------------------#
# -- The table, the form, the export dialog, a popped-out window -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheHeadlineLeadsTheTableAndARowOpensItsFigure(window):
    window.locator('.result-head .segmented button', has_text = 'Table').click()
    window.wait_for_selector('.headline-number')
    labels = window.eval_on_selector_all('.headline-label', 'labels => labels.map(l => l.textContent)')
    assert labels[:4] == ['Delivered Isp', 'Delivered thrust', 'Contour length', 'Exit diameter'] and 'Peak hot wall' in labels
    window.locator('tr.is-link', has_text = 'Coolant exit temperature').click()
    window.wait_for_timeout(500)
    assert window.input_value('.figure-toolbar > .view-select') == 'coolantFlow'

def testAResultsValidationOpensItsRecords(window):
    '''
    Each headline number and section carries its validation status; a badge opens the models
    behind it, and a model's record shows the passage its status stands on, the quote marked.
    '''
    window.locator('.result-head .segmented button', has_text = 'Table').click()
    window.wait_for_selector('.headline-item .validation-badge')
    sections = window.eval_on_selector_all('.section-head-row', 'rows => rows.map(r => [r.querySelector(".section-title").textContent, '
                                                               '(r.querySelector(".validation-badge") || {}).textContent])')
    labels = dict(sections)
    assert labels['Chamber'] == 'Validated' and labels['Sizing'] == 'Cross-checked'
    assert labels['Combustion Chamber'] == 'By construction'
    window.locator('.headline-item', has_text = 'Contour length').locator('.validation-badge').click()
    dialog = window.locator('.validation-dialog')
    dialog.wait_for()
    assert dialog.locator('h2').inner_text() == 'Contour length'
    assert dialog.locator('.validation-model-name').all_inner_texts() == ['Contour and exit plane (method of characteristics)']
    dialog.get_by_role('button', name = 'Show the record').click()
    window.wait_for_selector('.validation-passage mark')
    assert window.inner_text('.validation-passage mark') == 'This is a cross-check, not a validation.'
    window.keyboard.press('Escape')
    window.wait_for_selector('.validation-dialog', state = 'detached')
    assert window.locator('.result-pane').is_visible()

def testTheOutlineJumpsAndAProblemIsWrittenUnderItsField(window):
    window.locator('.outline-item', has_text = 'Volutes').click()
    window.wait_for_timeout(900)
    assert window.inner_text('.outline-item.is-current').startswith('Volutes')
    window.fill('input[placeholder="Find a field"]', 'hot wall thickness')
    window.locator('.form-row:not([hidden]) .form-editor input').first.fill('')
    window.wait_for_selector('.form-note-warn')
    assert window.inner_text('.form-note-warn') == "Cooling channels need 'Hot wall thickness'."

def testTheExportDialogPreviewsAnImageAndASurface(window):
    window.locator('.result-head .button', has_text = 'Export').click()
    window.wait_for_selector('.export-dialog .output-category-row')
    # The dialog takes its own width, so the list keeps its names beside a preview
    assert window.locator('.export-dialog').bounding_box()['width'] > 900
    window.locator('.output-category-row', has = window.get_by_text('Figures', exact = True)).click()
    window.wait_for_selector('.output-thumb')
    window.locator('.output-file-row .output-preview-button').first.click()
    window.wait_for_selector('.preview-image')
    window.locator('.output-category-row', has_text = '3D geometry').click()
    window.locator('.output-file-row', has_text = '.stl').first.locator('.output-preview-button').click()
    window.wait_for_selector('.output-preview canvas', timeout = drawMs)
    assert window.inner_text('.preview-note').endswith('triangles')

def _savedReport(page, scope) -> tuple:
    '''Press Save report inside `scope` and read the file it downloads: (file name, page text).'''
    with page.expect_download(timeout = drawMs) as saving:
        scope.get_by_role('button', name = 'Save report').click()
    download = saving.value
    with open(download.path(), encoding = 'utf-8') as handle:
        return download.suggested_filename, handle.read()

def testTheExportDialogSavesTheRunsReportAgainstTheBaseline(window):
    '''Save report in the Export dialog writes the shown run's report, beside the baseline when there is one.'''
    window.select_option('.baseline-select', '1')
    window.wait_for_selector('.result-status.is-baseline')
    window.locator('.result-head .button', has_text = 'Export').click()
    window.wait_for_selector('.export-dialog .output-category-row')
    name, page = _savedReport(window, window.locator('.export-dialog'))
    assert name == 'NOVANozzleRun3VsRun1Report.html'
    assert 'NOVA run report' in page and 'against run 1 (novaSinglePass) as the baseline' in page
    assert '<img class="figure-dark" src="data:image/png;base64,' in page
    assert window.locator('.toasts').inner_text().startswith('Report saved')

def testTheSweepViewSavesTheSweepsReport(window, sweptRuns):
    window.locator('.result-head .segmented button', has_text = 'Sweep').click()
    window.wait_for_selector('.sweep-plot .main-svg', timeout = drawMs)
    name, page = _savedReport(window, window.locator('.sweep-toolbar'))
    assert name == 'ChamberPressureSweep1Report.html'
    assert 'NOVA trade sweep report' in page and 'the contour solve did not converge' in page

def testAFigurePopsOutIntoItsOwnWindow(window):
    with window.context.expect_page() as popped:
        window.get_by_role('button', name = 'Pop out').click()
    popout = popped.value
    popout.wait_for_selector('.popout .run-select')
    _drawn(popout, 1)
    assert 'popout=figure' in popout.url and popout.title().startswith('NOVA -- Computed contour')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Trade sweeps and the run queue -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.fixture
def sweptRuns(served):
    '''The three showcase runs as the done points of a four-point chamber pressure sweep, the last failed.'''
    app, _ = served
    session = app.state.session
    sweep = sweeps.build({'name': '', 'config': session.record(1).config, 'fields': [
        {'key': 'chamberPressure', 'unit': 'MPa', 'values': [5.0e6, 6.0e6, 7.0e6, 8.0e6]}]})
    sweep = {**sweep, 'sweepId': 1, 'mode': 'dark'}
    for runId in (1, 2, 3):
        sweep['points'][runId - 1].update(state = 'done', runId = runId)
        session.record(runId).sweep = {'sweepId': 1, 'index': runId - 1}
    sweep['points'][3].update(state = 'failed', error = 'the contour solve did not converge')
    session.sweeps[1] = sweep
    session.publish({'type': 'sweeps'})
    session.publish({'type': 'runs', 'baseline': session.baseline})
    yield sweep
    session.sweeps.clear()
    for runId in (1, 2, 3):
        session.record(runId).sweep = None
    session.publish({'type': 'sweeps'})
    session.publish({'type': 'runs', 'baseline': session.baseline})

def testASweepPlotsItsPointsAndARowShowsItsRun(window, sweptRuns):
    '''
    The Sweep view plots a headline number against the swept field, a failed point a gap, and lists
    the points with their runs' numbers and the failed point's reason. A row shows its run, and the
    run menu groups the sweep's runs by point.
    '''
    window.locator('.result-head .segmented button', has_text = 'Sweep').click()
    window.wait_for_selector('.sweep-plot .main-svg', timeout = drawMs)
    plotted = window.evaluate('() => document.querySelector(".sweep-plot .js-plotly-plot").data[0]')
    assert plotted['x'] == [5, 6, 7, 8] and plotted['y'][3] is None and plotted['customdata'] == [1, 2, 3, None]
    assert window.inner_text('.sweep-progress') == '3 of 4 done, 1 failed'
    rows = window.locator('.sweep-point')
    assert rows.count() == 4 and rows.nth(3).locator('.sweep-state').inner_text() == 'failed'
    assert window.inner_text('.sweep-error-row .sweep-error') == 'the contour solve did not converge'
    window.wait_for_selector('.sweep-table th .validation-badge')
    assert window.locator('.sweep-table th.is-plotted').text_content().startswith('Delivered Isp [s]')

    rows.nth(1).click()
    window.wait_for_function('document.querySelector(".run-select").value === "2"')
    assert 'is-shown' in rows.nth(1).get_attribute('class')
    group = window.locator('.run-select optgroup')
    assert group.get_attribute('label') == 'Sweep: Chamber pressure sweep'
    assert [text.split(' · ')[:2] for text in group.locator('option').all_inner_texts()] == \
        [['Run 1', 'point 1, 5 MPa'], ['Run 2', 'point 2, 6 MPa'], ['Run 3', 'point 3, 7 MPa']]

def testTheSweepDialogSendsItsValuesInBackendUnits(window):
    '''
    The dialog spaces a range evenly in the unit shown and sends the values in SI; a second field
    with more values than the plot draws lines is refused before anything is sent.
    '''
    sent = []

    def catch(route):
        sent.append(json.loads(route.request.post_data))
        route.fulfill(status = 200, content_type = 'application/json',
                      body = json.dumps({'sweepId': 99, 'name': 'Chamber pressure sweep', 'points': [{}, {}, {}]}))

    window.route('**/api/sweeps', lambda route: catch(route) if route.request.method == 'POST' else route.continue_())
    window.locator('.run-bar button', has_text = 'Sweep').click()
    dialog = window.locator('.sweep-dialog')
    dialog.wait_for()
    assert dialog.locator('.sweep-field').first.input_value() == 'chamberPressure'
    window.fill('[aria-label="Chamber pressure from"]', '6')
    window.fill('[aria-label="Chamber pressure to"]', '8')
    window.fill('[aria-label="Chamber pressure count"]', '3')
    assert dialog.locator('.sweep-values').first.inner_text() == '6, 7, 8 MPa'

    dialog.get_by_role('button', name = 'Against a second field').click()
    window.fill('[aria-label="O/F ratio count"]', '7')
    assert 'takes at most 6 values' in dialog.locator('[role="alert"]').inner_text()
    assert dialog.get_by_role('button', name = 'Queue 21 runs').is_disabled()
    dialog.get_by_role('button', name = 'Remove').click()

    dialog.get_by_role('button', name = 'Queue 3 runs').click()
    window.wait_for_selector('.sweep-dialog', state = 'detached')
    assert len(sent) == 1
    assert sent[0]['fields'] == [{'key': 'chamberPressure', 'unit': 'MPa', 'values': [6.0e6, 7.0e6, 8.0e6]}]
    assert sent[0]['config']['filename'] and sent[0]['mode'] == 'dark'
    assert 'Chamber pressure sweep queued' in window.inner_text('.toasts')

def testAQueuedRunCanBeTakenOutOfTheQueue(window, served):
    '''The run bar counts the queued runs; the queue lists them and takes one out on request.'''
    app, _ = served
    session = app.state.session
    config = session.record(1).config
    session.queue.extend([QueuedRun(901, config, 'dark', 'first queued'), QueuedRun(902, config, 'dark', 'second queued')])
    session.publish({'type': 'queue', 'queue': [item.entry() for item in session.queue]})
    try:
        window.wait_for_selector('.run-queued')
        assert window.inner_text('.run-queued') == '2 queued'
        window.locator('.run-queued').click()
        assert window.locator('.queue-label').all_inner_texts() == ['first queued', 'second queued']
        window.get_by_role('button', name = 'Take first queued out of the queue').click()
        window.wait_for_function('document.querySelectorAll(".queue-row").length === 1')
        assert [item.queueId for item in session.queue] == [902]
        window.keyboard.press('Escape')
        window.wait_for_selector('.queue-panel', state = 'detached')
    finally:
        session.queue.clear()
        session.publish({'type': 'queue', 'queue': []})
