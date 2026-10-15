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
import time
import tkinter as tk
from ctypes import wintypes

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, root)

import numpy as np
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
        handle = ctypes.windll.user32.GetParent(self.app.winfo_id())

        # The window never draws pure black, so a black row is screen the window has not painted
        # yet, or another window over it. The capture is taken again until no black row is left
        # inside the window. The frame bounds can run a row or two past the window's own drawing,
        # and black rows within that slack at an edge are trimmed.
        slack = 3
        for _ in range(12):
            self.app.update()
            rect = wintypes.RECT()
            extendedFrameBounds = 9    # the frame Windows draws, without the invisible resize border
            ctypes.windll.dwmapi.DwmGetWindowAttribute(handle, extendedFrameBounds, ctypes.byref(rect),
                                                       ctypes.sizeof(rect))
            image = ImageGrab.grab((rect.left, rect.top, rect.right, rect.bottom), all_screens = True)
            rowBrightest = np.asarray(image.convert('L')).max(axis = 1)
            black = np.nonzero(rowBrightest == 0)[0]
            inside = black[(black >= slack) & (black < len(rowBrightest) - slack)]
            if inside.size == 0:
                break
            time.sleep(0.25)

        top = 0
        while top < slack and rowBrightest[top] == 0:
            top += 1
        bottom = len(rowBrightest)
        while bottom > len(rowBrightest) - slack and rowBrightest[bottom - 1] == 0:
            bottom -= 1
        image = image.crop((0, top, image.size[0], bottom))

        path = os.path.join(outputFolder, f'{name}.png')
        image.save(path, optimize = True)
        self.written.append(path)
        print(f'  wrote {os.path.relpath(path, root)}')
        if inside.size:
            print(f'    {inside.size} rows of {name} stayed black: another window covered this one, '
                  f'or part of it is off screen')

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
        # The window is on screen through a run of a few minutes and may have been moved aside; a
        # part of it pushed past the edge of every monitor captures as black. It is put back before
        # the step is arranged, so a tooltip opened by the step is placed against the window where
        # it will be photographed.
        self.app.geometry(windowGeometry)
        self.app.update()
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
