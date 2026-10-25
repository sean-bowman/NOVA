
# -- View Tab -- #

'''

Every view of a run in one place: the contour, the flow fields, the plume, the cooling jacket, the
film, the radiative extension and the 3D assemblies. A sidebar groups them and scrolls when the
window is too short for all of them; the pane beside it draws the selected one inline with
Matplotlib, and "Open interactive" renders the same view with plotly in the browser, where it can
be rotated and probed. Views a run did not produce stay listed and greyed, so the list reads the
same from run to run.

The 3D assemblies are drawn inline from their plotly figures, because Tk cannot host plotly. The
cooling views draw from `thermalPlots`.

Author: Sean Bowman

'''

import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk, messagebox

import numpy as np

from .. import backend
from .. import runner
from .. import theme
from ..widgets import ScrollableFrame, Tooltip, card
from ..plotting import (MplPane, drawContour, drawField, drawNearWall, drawPlotly3d, drawPlume,
                        drawRevolvedContour, openFile, openInteractive)
from .. import thermalPlots

@dataclass(frozen = True)
class ViewSpec:

    '''

    One entry in the sidebar.

    key          the view's own name
    group        the sidebar heading it sits under
    label        what the sidebar shows
    source       a line under the title saying where the picture comes from
    builderKey   plotting.interactiveBuilders key that renders it with plotly, or None
    htmlKey      runner.htmlFiles key of an HTML file the run writes for it, or None

    '''

    key: str
    group: str
    label: str
    source: str
    builderKey: str = None
    htmlKey: str = None

fieldSource = 'one-dimensional chamber, characteristic mesh to the exit plane'
jacketSource = 'drawn from the jacket solve'

views = (
    ViewSpec('contour', 'Contour', 'Computed contour', 'drawn from the run', 'contour'),
    ViewSpec('nearWall', 'Flow', 'Near-wall state', 'drawn from the run', 'nearWall'),
    ViewSpec('mach', 'Flow', 'Mach field', fieldSource, 'mach', 'machField'),
    ViewSpec('pressure', 'Flow', 'Pressure field', fieldSource, 'pressure', 'pressureField'),
    ViewSpec('temperature', 'Flow', 'Temperature field', fieldSource, 'temperature', 'temperatureField'),
    ViewSpec('plume', 'Plume', 'Plume', 'chamber, nozzle and marched plume as one field', 'plume', 'plume'),
    ViewSpec('wallMap', 'Cooling', 'Jacket on the wall', jacketSource, None, 'heatTransfer'),
    ViewSpec('jacketTemperatures', 'Cooling', 'Temperatures', jacketSource, None, 'heatTransfer'),
    ViewSpec('coolantFlow', 'Cooling', 'Coolant flow', jacketSource, None, 'heatTransfer'),
    ViewSpec('coolantProperties', 'Cooling', 'Coolant properties', jacketSource, None, 'heatTransfer'),
    ViewSpec('heatFlux', 'Cooling', 'Heat flux', jacketSource, None, 'heatTransfer'),
    ViewSpec('film', 'Cooling', 'Film cooling', 'drawn from the film solve'),
    ViewSpec('extension', 'Cooling', 'Radiative extension', 'drawn from the extension solve'),
    ViewSpec('channelMesh', 'Cooling', 'Channel mesh', '3D assembly, decimated for the inline view',
             'channelMesh', 'channelMesh'),
    ViewSpec('revolved', '3D', 'Revolved contour', 'drawn from the run', 'revolved'),
    ViewSpec('volute', '3D', 'Volutes', '3D assembly, decimated for the inline view', 'volute', 'volute'),
)

def _attributeSize(nozzle, name: str) -> int:

    value = getattr(nozzle, name, None)
    try:
        return int(np.size(value)) if value is not None else 0
    except Exception:                                      # noqa: BLE001
        return 0

def availableViews(nozzle, outputs: dict) -> set:

    '''

    The keys of the views a run produced. Each test reads only what the view itself draws from,
    and any test that fails reads as unavailable rather than as an error.

    Parameters:
    -----------
    nozzle : Nozzle or None
        The run's nozzle.
    outputs : dict
        runner.findOutputs for the run's folder.

    Returns:
    --------
    set : view keys

    '''

    if nozzle is None:
        return set()

    def has(name, minimum = 2):
        return _attributeSize(nozzle, name) >= minimum

    def on(name):
        return str(getattr(nozzle, name, 'off')) in ('on', 'True', 'true')

    def jacket():
        return thermalPlots.thermalResults(nozzle) is not None

    tests = {
        'contour':            lambda: has('xNozzleWall'),
        'nearWall':           lambda: has('nozzleNearWallMachNumber'),
        'mach':               lambda: len(getattr(nozzle, 'allXPoints', []) or []) > 0,
        'pressure':           lambda: len(getattr(nozzle, 'allXPoints', []) or []) > 0,
        'temperature':        lambda: len(getattr(nozzle, 'allXPoints', []) or []) > 0,
        'plume':              lambda: getattr(nozzle, 'nozzlePlumeStructure', None) is not None,
        'wallMap':            jacket,
        'jacketTemperatures': jacket,
        'coolantFlow':        jacket,
        'coolantProperties':  jacket,
        'heatFlux':           jacket,
        'film':               lambda: on('filmCooling') and thermalPlots.filmSolved(nozzle),
        'extension':          lambda: thermalPlots.extensionSolved(nozzle),
        'channelMesh':        lambda: np.ndim(getattr(nozzle, 'xChannel', None)) == 2 and has('xChannel'),
        'revolved':     lambda: has('xNozzleWall'),
        'volute':       lambda: on('makeInletVolute') or on('makeOutletVolute'),
    }

    available = set()
    for key, test in tests.items():
        try:
            if test():
                available.add(key)
        except Exception:                                  # noqa: BLE001 -- unavailable, not broken
            continue

    return available

class ViewTab(ttk.Frame):

    '''

    Sidebar of every view a run can produce, beside one pane that draws the selected view.

    '''

    def __init__(self, master, app):

        super().__init__(master, style = 'TFrame', padding = theme.scaled(8))

        self._app = app
        self._result = None
        self._outputs = {}
        self._available = set()
        self._key = tk.StringVar(value = 'contour')
        self._specs = {spec.key: spec for spec in views}
        self._buttons = {}

        self.columnconfigure(1, weight = 1)
        self.rowconfigure(0, weight = 1)

        # -- Sidebar: scrolls when the window is too short for every view -- #
        sidebarCard = card(self)
        sidebarCard.grid(row = 0, column = 0, sticky = 'nsw', padx = (0, theme.scaled(8)))
        scroller = ScrollableFrame(sidebarCard, onCard = True, fitWidth = True)
        scroller.pack(fill = 'both', expand = True)
        sidebar = scroller.body
        group = None
        for spec in views:
            if spec.group != group:
                group = spec.group
                ttk.Label(sidebar, text = group.upper(), style = 'Eyebrow.Card.TLabel').pack(
                    anchor = 'w', padx = theme.scaled(6), pady = (theme.scaled(10) if spec is not views[0] else 0,
                                                                  theme.scaled(2)))
            button = ttk.Radiobutton(sidebar, text = spec.label, value = spec.key, variable = self._key,
                                     style = 'Nav.Toolbutton', command = self._render, width = 22)
            button.pack(fill = 'x')
            button.state(['disabled'])
            self._buttons[spec.key] = button

        # -- Content -- #
        content = card(self)
        content.grid(row = 0, column = 1, sticky = 'nsew')

        heading = ttk.Frame(content, style = 'Surface.TFrame')
        heading.pack(fill = 'x')
        self._title = ttk.Label(heading, text = 'View', style = 'Heading.Card.TLabel')
        self._title.pack(side = 'left')
        self._source = ttk.Label(heading, text = '', style = 'Muted.Card.TLabel')
        self._source.pack(side = 'left', padx = theme.scaled(10))
        self._interactiveButton = ttk.Button(heading, text = 'Open interactive', style = 'Small.Card.TButton',
                                             command = self._openInteractive, state = 'disabled')
        self._interactiveButton.pack(side = 'right')
        Tooltip(self._interactiveButton, 'Render this view with plotly and open it in the browser, '
                                          'where it can be zoomed, rotated and probed point by point.')

        ttk.Separator(content, orient = 'horizontal', style = 'Card.TSeparator').pack(
            fill = 'x', pady = (theme.scaled(6), theme.scaled(4)))

        self._pane = MplPane(content)
        self._pane.pack(fill = 'both', expand = True)
        self._pane.message('Generate a nozzle to populate this view.')

    # -- Used by the app -- #

    def refresh(self, runResult) -> None:

        '''

        Mark which views the run produced and draw the selected one, or the first produced.

        '''

        self._result = runResult
        nozzle = getattr(runResult, 'nozzle', None)
        runName = str(getattr(nozzle, 'filename', '') or '') if nozzle is not None else ''
        self._outputs = runner.findOutputs(getattr(runResult, 'outputDir', ''), runName)
        self._available = availableViews(nozzle, self._outputs)

        for key, button in self._buttons.items():
            button.state(['!disabled'] if key in self._available else ['disabled'])

        if self._key.get() not in self._available:
            first = next((spec.key for spec in views if spec.key in self._available), 'contour')
            self._key.set(first)
        self._render()

    def select(self, key: str) -> None:

        '''Show a view by its key, when the run produced it.'''

        if key in self._available:
            self._key.set(key)
            self._render()

    # -- Internals -- #

    def _render(self) -> None:

        spec = self._specs.get(self._key.get())
        nozzle = getattr(self._result, 'nozzle', None)
        if spec is None:
            return

        self._title.configure(text = spec.label)
        self._source.configure(text = spec.source if spec.key in self._available else '')
        canInteract = spec.key in self._available and (spec.builderKey is not None
                                                       or spec.htmlKey in self._outputs.get('html', {}))
        self._interactiveButton.configure(state = 'normal' if canInteract else 'disabled')

        if nozzle is None:
            self._pane.message('Generate a nozzle to populate this view.')
            return
        if spec.key not in self._available:
            self._pane.message(f'{spec.label} was not produced by this run.')
            return

        drawers = {
            'contour':            (drawContour,),
            'nearWall':           (drawNearWall,),
            'mach':               (drawField, 'mach'),
            'pressure':           (drawField, 'pressure'),
            'temperature':        (drawField, 'temperature'),
            'plume':              (drawPlume,),
            'wallMap':            (thermalPlots.drawWallMap,),
            'jacketTemperatures': (thermalPlots.drawJacketTemperatures,),
            'coolantFlow':        (thermalPlots.drawCoolantFlow,),
            'coolantProperties':  (thermalPlots.drawCoolantProperties,),
            'heatFlux':           (thermalPlots.drawHeatFlux,),
            'film':               (thermalPlots.drawFilm,),
            'extension':          (thermalPlots.drawExtension,),
            'revolved':           (drawRevolvedContour,),
        }
        if spec.key in drawers:
            function, *arguments = drawers[spec.key]
            self._pane.render(function, nozzle, *arguments)
        elif spec.key in ('channelMesh', 'volute'):
            self._pane.render(_drawAssembly, nozzle, spec.key)

    def _openInteractive(self) -> None:

        spec = self._specs.get(self._key.get())
        nozzle = getattr(self._result, 'nozzle', None)
        if spec is None or nozzle is None:
            return

        # Rendered now where a builder exists, so it carries the theme mode in use; otherwise the
        # file the run wrote
        folder = getattr(self._result, 'outputDir', '') or '.'
        if spec.builderKey is not None:
            self.configure(cursor = 'watch')
            self.update_idletasks()
            try:
                written = openInteractive(nozzle, spec.builderKey, folder)
            finally:
                self.configure(cursor = '')
            if written is not None:
                return
        path = self._outputs.get('html', {}).get(spec.htmlKey)
        if path and os.path.isfile(path):
            openFile(path)
        else:
            messagebox.showinfo('Interactive view unavailable', 'This view has no data to render.')

def _drawAssembly(pane: MplPane, nozzle, key: str) -> None:

    '''Build a 3D assembly's plotly figure in the GUI's mode and draw it inline.'''

    figures = backend.figuresModule()
    figures.figurePalette.setFigureMode(theme.mode)
    builder = figures.channelMeshFigure if key == 'channelMesh' else figures.volutesFigure
    drawPlotly3d(pane, builder(nozzle))
