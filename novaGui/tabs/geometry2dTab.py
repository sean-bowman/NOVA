
# -- 2D Geometry Tab -- #

'''

Axisymmetric views of the generated nozzle. The computed contour and near-wall
state are drawn from the Nozzle object directly; the Mach, pressure and
temperature fields are the figures NOVA saved during the run.

Author: Sean Bowman
Date:   08/28/2026

'''

import os
import tkinter as tk
from tkinter import ttk, messagebox

from .. import runner
from ..widgets import Tooltip
from ..plotting import MplPane, drawContour, drawNearWall, drawPlume, openInteractive

class Geometry2DTab(ttk.Frame):

    '''

    View selector over the 2D geometry and flow-field figures.

    '''

    # label -> (source kind, key)
    _computed = {
        'Computed contour': ('draw', 'contour'),
        'Near-wall exhaust state': ('draw', 'nearWall'),
        'Exhaust plume structure': ('draw', 'plume'),
    }
    _figures = {
        'Contour segments': 'contour',
        'Mach field': 'mach',
        'Pressure field': 'pressure',
        'Temperature field': 'temperature',
        'Near-wall properties (saved)': 'nearWall',
    }

    def __init__(self, master, app):

        super().__init__(master, style = 'TFrame')

        self._app = app
        self._result = None
        self._outputs = {}

        toolbar = ttk.Frame(self, style = 'TFrame', padding = (10, 8))
        toolbar.pack(fill = 'x')
        ttk.Label(toolbar, text = 'VIEW', style = 'Eyebrow.TLabel').pack(side = 'left', padx = (0, 8))
        self._view = tk.StringVar(value = 'Computed contour')
        self._selector = ttk.Combobox(toolbar, textvariable = self._view, state = 'readonly',
                                      width = 32, values = list(self._computed))
        self._selector.pack(side = 'left')
        self._selector.bind('<<ComboboxSelected>>', lambda _e: self._render())

        # Plotly renders the same figure description far better than a static pane can, but it
        # cannot be embedded in Tk, so the interactive version opens in the system browser.
        self._interactiveButton = ttk.Button(toolbar, text = 'Open interactive',
                                             command = self._openInteractive, state = 'disabled')
        self._interactiveButton.pack(side = 'right')
        Tooltip(self._interactiveButton,
               'Render this view with plotly and open it in your browser.')

        self._pane = MplPane(self)
        self._pane.pack(fill = 'both', expand = True, padx = 8, pady = (0, 8))
        self._pane.message('Generate a nozzle to populate this view.')

    def refresh(self, runResult) -> None:

        '''

        Rebuild the view list from what the run produced and redraw.

        '''

        self._result = runResult
        runName = ''
        if runResult and runResult.nozzle is not None:
            runName = str(getattr(runResult.nozzle, 'filename', '') or '')
        self._outputs = runner.findOutputs(getattr(runResult, 'outputDir', ''), runName)

        available = list(self._computed)
        for label, key in self._figures.items():
            if key in self._outputs.get('figures', {}):
                available.append(label)
        self._selector.configure(values = available)
        if self._view.get() not in available:
            self._view.set(available[0])
        self._render()

    def _interactiveKey(self) -> str:

        '''

        The figures.py view key behind the label currently selected, computed or saved alike.

        '''

        label = self._view.get()
        if label in self._computed:
            return self._computed[label][1]
        return self._figures.get(label)

    def _openInteractive(self) -> None:

        nozzle = getattr(self._result, 'nozzle', None)
        key = self._interactiveKey()
        if nozzle is None or not key:
            return
        folder = getattr(self._result, 'outputDir', '') or '.'
        if openInteractive(nozzle, key, folder) is None:
            messagebox.showinfo('Interactive view unavailable',
                                'This view has no data to render.')

    def _render(self) -> None:

        label = self._view.get()
        nozzle = getattr(self._result, 'nozzle', None)

        canInteract = nozzle is not None and bool(self._interactiveKey())
        self._interactiveButton.configure(state = 'normal' if canInteract else 'disabled')

        if label in self._computed:
            if nozzle is None:
                self._pane.message('Generate a nozzle to populate this view.')
                return
            _, key = self._computed[label]
            if key == 'contour':
                drawContour(self._pane, nozzle)
            elif key == 'plume':
                drawPlume(self._pane, nozzle)
            else:
                drawNearWall(self._pane, nozzle)
            return

        key = self._figures.get(label)
        path = self._outputs.get('figures', {}).get(key)
        if path and os.path.isfile(path):
            self._pane.showImage(path, label)
        else:
            self._pane.message(f'{label} was not written for this run.')
