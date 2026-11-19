# -- Screenshots of the NOVA GUI -- #

'''

Run the shipped nozzle through the NOVA GUI (novaGui) and photograph each tab.

The GUI's server starts in this process on a free port, and Playwright's Chromium opens the built
front end at the desktop window's size. The script presses Generate on the form the window opens
with, which is the shipped nozzle, photographs the run bar while the coolant circuit iterates, and
once the run ends steps through the tabs and views. The light-mode pictures use the theme switch,
which saves the theme preference; the preference found at the start is written back at the end.

It needs the web extra, the built front end and Playwright with its Chromium:

    pip install -e .[web,screenshots]
    python -m playwright install chromium
    cd novaGui/frontend && npm install && npm run build && cd ../..

Run it from the NOVA root. The run itself takes about five minutes, because the shipped nozzle
builds a full cooling jacket, its outlet volute and the marched plume:

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
runTimeoutMs = 20 * 60 * 1000                  # [ms] longest wait for the run to finish
figureTimeoutMs = 120 * 1000                   # [ms] longest wait for one view to draw

# The Export tab's output folder in the pictures, in place of the folder of whoever runs this
exportFolderShown = r'C:\NOVA\runs'

# Views photographed after the run: (sidebar label, image name, rendering, settle time [ms]). The
# Mach field and the plume are drawn static: the Matplotlib drawing shades one continuous field,
# where the interactive field is the solve's nodes as points, and the interactive plume is framed
# to take in every correlated shock cell, many lip radii past the march. The settle time covers
# what Playwright cannot wait on: WebGL scenes finish drawing after the plot's SVG exists.
viewShots = [
    ('Mach field', 'viewMach', 'static', 1000),
    ('Plume', 'viewPlume', 'static', 1000),
    ('Jacket on the wall', 'viewJacket', 'interactive', 1500),
    ('Film cooling', 'viewFilm', 'interactive', 1500),
    ('Coolant circuit', 'viewCircuit', 'interactive', 1500),
    ('Channel mesh', 'viewChannelMesh', 'interactive', 6000),
    ('Revolved contour', 'viewRevolved', 'interactive', 3000),
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

def showView(page: Page, label: str, rendering: str, settleMs: int) -> None:

    '''Pick a view from the sidebar in `rendering` ('interactive' or 'static'), and wait for it to draw.'''

    page.locator('.nav-item').filter(has_text = re.compile(f'^{re.escape(label)}$')).first.click()
    # A 3D assembly has no switch: it draws interactive only
    switch = page.locator('.segmented button', has_text = rendering.capitalize())
    if switch.count() and 'is-selected' not in (switch.get_attribute('class') or ''):
        switch.click()
    drawn = '.static-image' if switch.count() and rendering == 'static' else '.plotly-host .main-svg'
    # The previous view's figure stays until the next one starts loading; give the load time to begin
    page.wait_for_timeout(300)
    page.wait_for_selector(drawn, timeout = figureTimeoutMs)
    page.wait_for_selector('.figure-overlay', state = 'detached', timeout = figureTimeoutMs)
    page.wait_for_timeout(settleMs)

def photograph(page: Page, base: str) -> None:

    '''Drive the window through the run and every picture.'''

    errors = []
    page.on('console', lambda message: message.type == 'error' and errors.append(message.text))
    page.on('pageerror', lambda error: errors.append(str(error)))

    # -- Design -- #
    page.goto(base)
    page.wait_for_selector('.section-header')
    page.wait_for_timeout(1000)
    capture(page, 'designDark')

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
    page.locator('.run-bar .button-primary', has_text = 'Generate').click()
    page.wait_for_timeout(500)
    if page.locator('.modal').count():
        print('  the shipped nozzle raised configuration warnings; running anyway')
        page.get_by_role('button', name = 'Run anyway').click()
    page.get_by_role('button', name = 'Show log').click()

    # The run bar while the coolant circuit iterates: the stage label carries the pass number
    page.wait_for_function("(document.querySelector('.run-stage')?.textContent ?? '').includes('pass 2')",
                           timeout = runTimeoutMs)
    page.wait_for_timeout(1500)
    capture(page, 'generate')

    page.wait_for_selector('.run-bar.state-done, .run-bar.state-error', timeout = runTimeoutMs)
    if page.locator('.run-bar.state-error').count():
        raise RuntimeError(f'the run failed: {page.locator(".run-latest").inner_text()}')
    print(f'  {page.locator(".run-stage").inner_text()}')
    page.get_by_role('button', name = 'Hide log').click()
    # The run's notice would sit over the corner of every figure
    for close in page.locator('.toast-close').all():
        close.click()

    # -- View: the window turns to it when the run finishes -- #
    page.wait_for_selector('.view-sidebar')
    for label, name, rendering, settleMs in viewShots:
        showView(page, label, rendering, settleMs)
        capture(page, name)

    # -- Analyze and Export -- #
    page.get_by_role('tab', name = 'Analyze').click()
    page.wait_for_selector('.result-table')
    page.wait_for_timeout(800)
    capture(page, 'analyze')

    page.get_by_role('tab', name = 'Export').click()
    page.wait_for_selector('.export-list')
    page.fill('#export-base', exportFolderShown)
    page.wait_for_timeout(1000)
    capture(page, 'export')

    # -- Light mode -- #
    page.get_by_role('button', name = re.compile('Switch to the light theme')).click()
    page.get_by_role('tab', name = 'Design').click()
    scrollFormToTop(page)
    page.wait_for_timeout(1000)
    capture(page, 'designLight')

    page.get_by_role('tab', name = 'View').click()
    showView(page, 'Plume', 'static', 1000)
    capture(page, 'viewPlumeLight')

    print(f'  console errors: {errors or "none"}')

def build() -> None:

    '''Serve the GUI, photograph it, and leave the saved theme preference as it was found.'''

    if not os.path.isfile(os.path.join(frontendDist, 'index.html')):
        raise SystemExit('The front end is not built: run `npm install` and `npm run build` in novaGui/frontend.')
    os.makedirs(outputFolder, exist_ok = True)

    savedSettings = guiSettings.load()
    guiSettings.save({**savedSettings, 'themeMode': 'dark'})

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
            page = browser.new_page(viewport = viewport, device_scale_factor = 1)
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
