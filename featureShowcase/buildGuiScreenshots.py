# -- Screenshots of the GUI for the README -- #

'''

Run the shipped nozzle through the GUI and photograph each tab, for the README's walkthrough.

The window opens at a fixed size, runs Generate on the form it starts with, which is the shipped
nozzle, and then steps through the tabs and views, capturing the window from the screen after
each one has drawn. It needs a visible desktop: the window is raised and held on top while it is
photographed, and the screen is read with Pillow's ImageGrab, so this runs on Windows. The theme
mode is set for the captures without touching the saved preference.

Run it from the NOVA root. The run itself takes a few minutes, because the shipped nozzle builds a
full cooling jacket and both volutes:

    python featureShowcase/buildGuiScreenshots.py

The images are written to docs/images/gui/.

Author: Sean Bowman

'''

import ctypes
import os
import sys
import tkinter as tk
from ctypes import wintypes

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, root)

from PIL import ImageGrab

from novaGui import theme
from novaGui.app import NovaApp

outputFolder = os.path.join(root, 'docs', 'images', 'gui')
windowGeometry = '1440x920+30+30'

class Photographer:

    '''

    Drives the window through a list of steps, each one arranging the window and then, after a
    pause long enough for it to draw, capturing it.

    '''

    def __init__(self):

        self.app = NovaApp()
        self.app.geometry(windowGeometry)
        theme.setMode(self.app, 'dark')
        self.written = []
        self.steps = []

        realResult = self.app._onResult

        def onResult(result):
            realResult(result)
            if not result.ok:
                print(f'run failed: {result.error}')
                self.app.after(200, self.app.destroy)
                return
            print(f'run complete in {result.elapsedSec:.0f} s; capturing')
            self.app.after(1500, self._next)

        self.app._onResult = onResult

    def capture(self, name: str) -> None:

        '''The window, title bar included, as it stands on the screen.'''

        self.app.lift()
        self.app.attributes('-topmost', True)
        # A tooltip is its own window, and the main window held on top would cover it
        for overlay in self._overlays(self.app):
            overlay.attributes('-topmost', True)
            overlay.lift()
        self.app.update()
        handle = ctypes.windll.user32.GetParent(self.app.winfo_id())
        # The frame Windows draws, without the invisible resize border GetWindowRect includes
        rect = wintypes.RECT()
        extendedFrameBounds = 9
        ctypes.windll.dwmapi.DwmGetWindowAttribute(handle, extendedFrameBounds, ctypes.byref(rect),
                                                   ctypes.sizeof(rect))
        path = os.path.join(outputFolder, f'{name}.png')
        ImageGrab.grab((rect.left, rect.top, rect.right, rect.bottom), all_screens = True).save(path, optimize = True)
        self.written.append(path)
        print(f'  wrote {os.path.relpath(path, root)}')

    @classmethod
    def _overlays(cls, widget) -> list:

        '''Every borderless top-level window open under `widget`, such as a tooltip.'''

        found = []
        for child in widget.winfo_children():
            if isinstance(child, tk.Toplevel) and child.winfo_ismapped() and child.wm_overrideredirect():
                found.append(child)
            found += cls._overlays(child)
        return found

    def step(self, arrange, name: str, pause: int = 900) -> None:

        '''Queue one picture: `arrange()`, wait `pause` ms, capture as `name`.'''

        self.steps.append((arrange, name, pause))

    def _next(self) -> None:

        if not self.steps:
            self.app.attributes('-topmost', False)
            self.app.after(200, self.app.destroy)
            return
        arrange, name, pause = self.steps.pop(0)
        arrange()
        self.app.after(pause, lambda: (self.capture(name), self.app.after(150, self._next)))

    def run(self) -> list:

        os.makedirs(outputFolder, exist_ok = True)
        self.app.after(1500, self.app._generate)
        self.app.mainloop()
        return self.written

def build() -> list:

    photographer = Photographer()
    app = photographer.app

    def tab(widget):
        return lambda: app.notebook.select(widget)

    def view(key):
        return lambda: (app.notebook.select(app.viewTab), app.viewTab.select(key))

    def tooltip():
        app.notebook.select(app.configTab)
        app.update()
        app.configTab._rows['divergingSectionType'].tooltip._show()

    def closeTooltip():
        app.configTab._rows['divergingSectionType'].tooltip._hide()

    def light():
        theme.setMode(app, 'light')
        app.notebook.select(app.configTab)

    def lightView():
        app.notebook.select(app.viewTab)
        app.viewTab.select('plume')

    photographer.step(tab(app.configTab), 'designDark')
    photographer.step(tooltip, 'designHelp', pause = 900)
    photographer.step(lambda: (closeTooltip(), view('mach')()), 'viewMach', pause = 2500)
    photographer.step(view('plume'), 'viewPlume', pause = 2500)
    photographer.step(view('heatTransfer'), 'viewHeatTransfer', pause = 2000)
    photographer.step(view('channelMesh'), 'viewChannelMesh', pause = 6000)
    photographer.step(view('revolved'), 'viewRevolved', pause = 3000)
    photographer.step(tab(app.analysisTab), 'analyze')
    photographer.step(tab(app.exportTab), 'export')
    photographer.step(light, 'designLight', pause = 2000)
    photographer.step(lightView, 'viewPlumeLight', pause = 3000)

    return photographer.run()

if __name__ == '__main__':
    build()
