
# -- 3D Geometry Tab -- #

'''

Three-dimensional views of the nozzle. A revolved surface of the wall contour is
drawn inline and always available; the channel-mesh and volute views are
the interactive plotly HTML files NOVA writes, rendered in an embedded browser
frame with a system-browser fallback.

Author: Sean Bowman
Date:   08/28/2026

'''

import os
import webbrowser
import tkinter as tk
from tkinter import ttk

from .. import theme
from .. import runner
from ..plotting import MplPane, drawRevolvedContour, openInteractive

try:
    from tkinterweb import HtmlFrame
    _htmlAvailable = True
except Exception:                                   # noqa: BLE001 -- optional dependency
    HtmlFrame = None
    _htmlAvailable = False

class Geometry3DTab(ttk.Frame):

    '''

    Revolved-contour preview plus the interactive HTML geometry views.

    '''

    _htmlViews = {
        'Channel mesh (interactive)': 'channelMesh',
        'Volute (interactive)': 'volute',
    }

    def __init__(self, master, app):

        super().__init__(master, style = 'TFrame')

        self._app = app
        self._result = None
        self._outputs = {}
        self._htmlPath = None

        toolbar = ttk.Frame(self, style = 'TFrame', padding = (10, 8))
        toolbar.pack(fill = 'x')
        ttk.Label(toolbar, text = 'VIEW', style = 'Eyebrow.TLabel').pack(side = 'left', padx = (0, 8))
        self._view = tk.StringVar(value = 'Revolved contour')
        self._selector = ttk.Combobox(toolbar, textvariable = self._view, state = 'readonly',
                                      width = 32, values = ['Revolved contour'])
        self._selector.pack(side = 'left')
        self._selector.bind('<<ComboboxSelected>>', lambda _e: self._render())
        self._browserButton = ttk.Button(toolbar, text = 'Open in browser', command = self._openInBrowser,
                                         state = 'disabled')
        self._browserButton.pack(side = 'right')

        self._content = ttk.Frame(self, style = 'Surface.TFrame')
        self._content.pack(fill = 'both', expand = True, padx = 8, pady = (0, 8))

        self._pane = MplPane(self._content, projection = '3d')
        if _htmlAvailable:
            self._html = HtmlFrame(self._content, messages_enabled = False)
        else:
            self._html = ttk.Label(
                self._content, style = 'SurfaceMuted.TLabel', anchor = 'center', wraplength = 520,
                text = ('tkinterweb is not installed, so the interactive HTML views cannot be '
                        'embedded. Install it with  pip install tkinterweb  or use "Open in browser".'),
            )

        self._showWidget(self._pane)
        self._pane.message('Generate a nozzle to populate this view.')

    def refresh(self, runResult) -> None:

        self._result = runResult
        runName = ''
        if runResult and runResult.nozzle is not None:
            runName = str(getattr(runResult.nozzle, 'filename', '') or '')
        self._outputs = runner.findOutputs(getattr(runResult, 'outputDir', ''), runName)

        available = ['Revolved contour']
        for label, key in self._htmlViews.items():
            if key in self._outputs.get('html', {}):
                available.append(label)
        self._selector.configure(values = available)
        if self._view.get() not in available:
            self._view.set('Revolved contour')
        self._render()

    def _render(self) -> None:

        label = self._view.get()
        nozzle = getattr(self._result, 'nozzle', None)

        if label == 'Revolved contour':
            # The inline pane is Matplotlib; the browser button renders the same description
            # with plotly, which handles a rotatable surface far better than Tk can.
            self._htmlPath = None
            self._browserButton.configure(
                state = 'normal' if nozzle is not None else 'disabled')
            self._showWidget(self._pane)
            if nozzle is None:
                self._pane.message('Generate a nozzle to populate this view.')
            else:
                drawRevolvedContour(self._pane, nozzle)
            return

        key = self._htmlViews.get(label)
        path = self._outputs.get('html', {}).get(key)
        self._htmlPath = path
        self._browserButton.configure(state = 'normal' if path else 'disabled')
        self._showWidget(self._html)

        if not _htmlAvailable:
            return
        if path and os.path.isfile(path):
            try:
                self._html.load_file(path, force = True)
            except TypeError:
                self._html.load_file(path)
            except Exception:                        # noqa: BLE001 -- fall back to the browser button
                self._html.load_html(
                    f'<body style="background:{theme.surface};color:{theme.textMuted};'
                    f'font-family:sans-serif;padding:24px">Could not embed this view. '
                    f'Use <b>Open in browser</b>.</body>')
        else:
            self._html.load_html(
                f'<body style="background:{theme.surface};color:{theme.textMuted};'
                f'font-family:sans-serif;padding:24px">This view was not written for the current run.</body>')

    def _showWidget(self, widget) -> None:

        for child in self._content.winfo_children():
            child.pack_forget()
        widget.pack(fill = 'both', expand = True)

    def _openInBrowser(self) -> None:

        # The revolved view has no pre-written HTML: render it with plotly on demand.
        if self._view.get() == 'Revolved contour':
            nozzle = getattr(self._result, 'nozzle', None)
            folder = getattr(self._result, 'outputDir', '') or '.'
            if nozzle is not None:
                openInteractive(nozzle, 'revolved', folder)
            return

        if self._htmlPath and os.path.isfile(self._htmlPath):
            webbrowser.open(f'file:///{os.path.abspath(self._htmlPath).replace(os.sep, "/")}')
