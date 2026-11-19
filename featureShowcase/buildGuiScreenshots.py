# -- Screenshots of the NOVA GUI -- #

'''

Run the shipped nozzle through the NOVA GUI (novaGui) and photograph the window.

The GUI's server starts in this process on a free port, and Playwright's Chromium opens the built
front end at the desktop window's size. The script presses Generate on the form the window opens
with, which is the shipped nozzle, photographs the stage stepper and the stage list while the
coolant circuit iterates, with the run's contour already in the result pane, and once the run ends
steps the result pane through its views, the results table and the export dialog with a preview.
It then makes that run the baseline, raises the chamber pressure and runs again, for the pictures
of a run drawn over its baseline, the table beside it, and the grid of views along the nozzle axis
in a popped-out window. The light-mode pictures use the theme switch, which saves the theme
preference; the preferences found at the start, the form's width among them, are written back at
the end.

It needs the web extra, the built front end and Playwright with its Chromium:

    pip install -e .[web,screenshots]
    python -m playwright install chromium
    cd novaGui/frontend && npm install && npm run build && cd ../..

Run it from the NOVA root. Each of the two runs takes about five minutes, because the shipped
nozzle builds a full cooling jacket, its outlet volute and the marched plume:

    python featureShowcase/buildGuiScreenshots.py

The images are written to docs/images/novaGui/.

Author: Sean Bowman

'''

# Standard library imports
import os
import re
import sys
import threading

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, root)

# Before anything imports NOVA: figures are written to files, and no window or browser tab opens
os.environ.setdefault('NOVA_HEADLESS', '1')

# Third-party imports
from playwright.sync_api import Page, sync_playwright

# Local imports
from novaGui import runner
from novaGui import settings as guiSettings
from novaGui.__main__ import _freePort, _serve, _waitUntilStarted
from novaGui.server import createApp, frontendDist

outputFolder = os.path.join(root, 'docs', 'images', 'novaGui')
viewport = {'width': 1480, 'height': 940}      # [px] the desktop window's opening size
popoutViewport = {'width': 1920, 'height': 1080}   # [px] a popped-out window on a second monitor
comparedPressure = '8000000'                   # [Pa] the second run's chamber pressure
runTimeoutMs = 20 * 60 * 1000                  # [ms] longest wait for the run to finish
figureTimeoutMs = 120 * 1000                   # [ms] longest wait for one view to draw

# The export dialog's output folder in the pictures, in place of the folder of whoever runs this
exportFolderShown = r'C:\NOVA\runs'

# Views photographed after the run: (view key, image name, settle time [ms]). The settle time
# covers what Playwright cannot wait on: WebGL scenes finish drawing after the plot's SVG exists.
viewShots = [
    ('mach', 'viewMach', 1500),
    ('plume', 'viewPlume', 1500),
    ('wallMap', 'viewJacket', 1500),
    ('film', 'viewFilm', 1500),
    ('circuit', 'viewCircuit', 1500),
    ('channelMesh', 'viewChannelMesh', 6000),
    ('revolved', 'viewRevolved', 3000),
]

def capture(page: Page, name: str) -> None:

    '''The whole window, as it stands.'''

    path = os.path.join(outputFolder, f'{name}.png')
    page.screenshot(path = path)
    print(f'  wrote {os.path.relpath(path, root)}')

def captureSection(page: Page, title: str, name: str, margin: int = 10) -> None:

    '''

    The Design form's section titled `title` alone, with `margin` px of the page around it. The
    picture is cut from the page, so a tooltip drawn over the section is in it.

    '''

    section = page.locator('section.section', has = page.locator('.section-title', has_text = title)).first
    box = section.bounding_box()
    left = max(box['x'] - margin, 0)
    top = max(box['y'] - margin, 0)
    clip = {'x': left, 'y': top, 'width': min(box['x'] + box['width'] + margin, viewport['width']) - left,
            'height': min(box['y'] + box['height'] + margin, viewport['height']) - top}
    path = os.path.join(outputFolder, f'{name}.png')
    page.screenshot(path = path, clip = clip)
    print(f'  wrote {os.path.relpath(path, root)}')

def formRow(page: Page, label: str):

    '''The Design form row whose label reads `label`.'''

    return page.locator('.form-row', has = page.locator('.form-label label', has_text = label)).first

def scrollToSection(page: Page, title: str) -> None:

    '''Open the Design form's section titled `title` and scroll it to the top.'''

    # The cooling sections start folded even when the shipped nozzle turns cooling on: a section
    # opens itself only when its predicate turns true during an edit
    header = page.locator('.section-header', has = page.locator('.section-title', has_text = title)).first
    if header.get_attribute('aria-expanded') != 'true':
        header.click()
    header.evaluate('element => element.scrollIntoView({block: "start"})')
    page.wait_for_timeout(400)

def scrollFormToTop(page: Page) -> None:

    '''Scroll the Design form back to its first section.'''

    page.locator('section.section').first.evaluate('''element => {
        let node = element.parentElement;
        while (node && node.scrollHeight <= node.clientHeight) {
            node = node.parentElement;
        }
        if (node) {
            node.scrollTop = 0;
        }
    }''')
    page.wait_for_timeout(300)

def figuresDrawn(page: Page, count: int, settleMs: int) -> None:

    '''Wait until `count` figures have drawn and none is still loading.'''

    page.wait_for_function(f'document.querySelectorAll(".plotly-host .main-svg").length >= {count}',
                           timeout = figureTimeoutMs)
    page.wait_for_selector('.figure-overlay', state = 'detached', timeout = figureTimeoutMs)
    page.wait_for_timeout(settleMs)

def showView(page: Page, key: str, settleMs: int) -> None:

    '''Pick a view from the result pane's menu, one at a time, and wait for it to draw.'''

    page.locator('.result-head .segmented button', has_text = 'Figure').click()
    page.locator('.figure-toolbar .segmented button', has_text = 'One').click()
    page.select_option('.figure-toolbar > .view-select', key)
    # The previous view's figure stays until the next one starts loading; give the load time to begin
    page.wait_for_timeout(300)
    figuresDrawn(page, 1, settleMs)

def hoverPlot(page: Page, cell: int) -> None:

    '''Rest the mouse in the middle of the plot area of the `cell`th figure (from 0), moving the axial cursor there.'''

    host = page.locator('.plotly-host').nth(cell)
    box = host.bounding_box()
    left, width, top, height = host.evaluate('element => { const f = element._fullLayout; '
                                             'return [f.xaxis._offset, f.xaxis._length, f.yaxis._offset, f.yaxis._length]; }')
    for share in (0.30, 0.34):
        page.mouse.move(box['x'] + left + share * width, box['y'] + top + 0.5 * height)
        page.wait_for_timeout(300)
    page.wait_for_timeout(500)

def generate(page: Page) -> None:

    '''Press Generate, accept any configuration warning, and wait for the run to end.'''

    page.locator('.run-bar .button-primary', has_text = 'Generate').click()
    page.wait_for_timeout(500)
    if page.locator('[role="alertdialog"]').count():
        print('  the form raised configuration warnings; running anyway')
        page.get_by_role('button', name = 'Run anyway').click()

def finished(page: Page) -> None:

    '''Wait for the run to end, then close the stage list and the run's notices.'''

    page.wait_for_selector('.run-bar.state-done, .run-bar.state-error', timeout = runTimeoutMs)
    if page.locator('.run-bar.state-error').count():
        raise RuntimeError(f'the run failed: {page.locator(".toast-error").all_inner_texts()}')
    print(f'  {page.locator(".run-clock").inner_text()}')
    # The stage list and the run's notice would sit over the form and the corner of every figure
    page.keyboard.press('Escape')
    for close in page.locator('.toast-close').all():
        close.click()

def photograph(page: Page, base: str) -> None:

    '''Drive the window through the run and every picture.'''

    errors = []
    page.on('console', lambda message: message.type == 'error' and errors.append(message.text))
    page.on('pageerror', lambda error: errors.append(str(error)))

    # -- Design -- #
    page.goto(base)
    page.wait_for_selector('.section-header')
    page.wait_for_timeout(1000)

    # Every field's help marker shows its meaning, and a choice field's options, on hover
    formRow(page, 'Diverging section type').locator('.help-marker').hover()
    page.wait_for_selector('.tooltip')
    page.wait_for_timeout(400)
    captureSection(page, 'Contour Definition', 'designHelp')
    page.mouse.move(viewport['width'] - 10, 60)
    page.wait_for_selector('.tooltip', state = 'detached')

    # The circuit choice, with the note on the circuit selected beneath it
    scrollToSection(page, 'Coolant Circuit')
    captureSection(page, 'Coolant Circuit', 'designCircuit')
    scrollFormToTop(page)

    # -- Generate -- #
    generate(page)

    # The stage stepper and the stage list, which opens as the run starts, while the coolant
    # circuit iterates: the circuit's segment carries the pass number and the list its passes, and
    # the result pane already draws the contour the run settled
    page.wait_for_function("[...document.querySelectorAll('.stage-step')]"
                           ".some((step) => step.textContent.includes('pass 3'))", timeout = runTimeoutMs)
    page.wait_for_selector('.run-select option:has-text("running")', state = 'attached', timeout = figureTimeoutMs)
    figuresDrawn(page, 1, 1500)
    capture(page, 'generate')
    finished(page)

    # -- The window with the run's contour beside the form, then the views -- #
    showView(page, 'contour', 1500)
    capture(page, 'designDark')
    for key, name, settleMs in viewShots:
        showView(page, key, settleMs)
        capture(page, name)

    # -- The results table, and the export dialog previewing the hot wall surface -- #
    page.locator('.result-head .segmented button', has_text = 'Table').click()
    page.wait_for_selector('.result-table')
    page.wait_for_timeout(800)
    capture(page, 'table')

    page.locator('.result-head .button', has_text = 'Export').click()
    page.wait_for_selector('.export-dialog .export-list')
    page.fill('#export-base', exportFolderShown)
    page.locator('.output-category-row', has_text = '3D geometry').click()
    page.locator('.output-file-row', has_text = '.stl').first.locator('.output-preview-button').click()
    page.wait_for_selector('.output-preview canvas', timeout = figureTimeoutMs)
    page.wait_for_timeout(2500)
    capture(page, 'export')
    page.keyboard.press('Escape')

    # -- A second run against the first as its baseline -- #
    page.select_option('.baseline-select', page.locator('.baseline-select option').nth(1).get_attribute('value'))
    formRow(page, 'Chamber pressure').locator('.form-editor input').fill(comparedPressure)
    page.wait_for_timeout(600)
    generate(page)
    finished(page)

    showView(page, 'jacketTemperatures', 1500)
    capture(page, 'compare')

    page.locator('.result-head .segmented button', has_text = 'Table').click()
    page.wait_for_selector('.result-table.is-compared')
    page.wait_for_timeout(800)
    capture(page, 'tableCompare')

    # The grid of views along the axis, popped out onto a second monitor, with the cursor on the throat region
    page.locator('.result-head .segmented button', has_text = 'Figure').click()
    page.locator('.figure-toolbar .segmented button', has_text = 'Grid').click()
    with page.context.expect_page() as popped:
        page.get_by_role('button', name = 'Pop out').click()
    window = popped.value
    window.set_viewport_size(popoutViewport)
    window.wait_for_selector('.popout .figure-cell')
    figuresDrawn(window, 4, 2000)
    hoverPlot(window, 1)
    capture(window, 'grid')
    window.close()
    page.locator('.figure-toolbar .segmented button', has_text = 'One').click()

    # -- Light mode -- #
    page.get_by_role('button', name = re.compile('Switch to the light theme')).click()
    scrollFormToTop(page)
    showView(page, 'contour', 1500)
    capture(page, 'designLight')

    showView(page, 'plume', 1500)
    capture(page, 'viewPlumeLight')

    print(f'  console errors: {errors or "none"}')

def build() -> None:

    '''Serve the GUI, photograph it, and leave the saved theme preference as it was found.'''

    if not os.path.isfile(os.path.join(frontendDist, 'index.html')):
        raise SystemExit('The front end is not built: run `npm install` and `npm run build` in novaGui/frontend.')
    os.makedirs(outputFolder, exist_ok = True)

    # The pictures use the dark mode and the form's default width
    savedSettings = guiSettings.load()
    guiSettings.save({**savedSettings, 'themeMode': 'dark', 'formWidth': None})

    runner.clearStaging()
    app = createApp()
    session = app.state.session
    port = _freePort()
    server = _serve(app, port)
    thread = threading.Thread(target = server.run, name = 'novaServer', daemon = True)
    thread.start()
    try:
        if not _waitUntilStarted(server):
            raise RuntimeError('the NOVA server did not start')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_context(viewport = viewport, device_scale_factor = 1).new_page()
            try:
                photograph(page, f'http://127.0.0.1:{port}/')
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout = 5.0)
        session.shutdown()
        guiSettings.save(savedSettings)

if __name__ == '__main__':
    build()
