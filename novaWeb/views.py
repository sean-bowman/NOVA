
# -- NOVA Web Views -- #

'''

The View tab's figures, rendered for the browser.

The list of views and the test of which ones a run produced are the Tkinter front end's own
(novaGui.tabs.viewTab.views and availableViews), so the two front ends offer the same views for
the same run. Each view renders one or both of two ways:

    interactive   a plotly figure as JSON, drawn in the browser by plotly.js at full resolution,
                  from the builder novaGui.plotting.interactiveBuilders names for the view, or for
                  the nine cooling views from novaWeb.coolingFigures
    static        the Matplotlib drawing the Tkinter pane shows, rendered headless to PNG at the
                  browser pane's size and pixel ratio

The 3D assemblies render interactive only: their Matplotlib form is a decimated stand-in for the
WebGL view.

The Matplotlib plume title tells a Tkinter user that its "Open interactive" button shows the
correlated structure beyond the march. Here the same figure says the Interactive rendering does.

Figures are drawn in one palette mode at a time, and the mode lives in module globals
(NOVA.palette for both renderers, novaGui.theme and Matplotlib's rcParams for the static one), so
every render holds `renderLock`.

Importing novaGui.tabs.viewTab loads NOVA and the scientific stack, several seconds the first
time. `warmUp` does it on a background thread when the server starts.

Author: Sean Bowman
Date:   11/16/2026

'''

# Standard library imports
import io
import threading

renderLock = threading.Lock()
_ready = threading.Event()
_modules = {}

# The Tkinter pane decimates the 3D assemblies and says so; plotly.js draws the full mesh here
sourceOverrides = {
    'channelMesh': '3D assembly, full mesh',
    'volute':      '3D assembly, full mesh',
}

# Text in the shared Matplotlib drawers that names a Tkinter control, and what it reads here
staticTextOverrides = {
    'Open interactive shows them': 'the Interactive rendering shows them',
}

def warmUp() -> None:

    '''

    Import the view machinery and NOVA. Safe to call from several threads; the first does the work.

    '''

    if _ready.is_set():
        return
    with renderLock:
        if _ready.is_set():
            return
        import matplotlib
        matplotlib.use('Agg', force = True)
        from novaGui import plotting, runner, theme, thermalPlots, backend
        from novaGui.tabs import viewTab
        from . import coolingFigures
        _modules.update(plotting = plotting, runner = runner, theme = theme, thermalPlots = thermalPlots,
                        backend = backend, viewTab = viewTab, coolingFigures = coolingFigures)
        _ready.set()

def ready() -> bool:

    '''Whether the view machinery and NOVA have loaded.'''

    return _ready.is_set()

def _module(name: str):

    warmUp()
    return _modules[name]

def _staticDrawers() -> dict:

    '''

    The Matplotlib drawer and its extra arguments for each view the static renderer draws.

    '''

    plotting, thermal = _module('plotting'), _module('thermalPlots')

    return {
        'contour':            (plotting.drawContour,),
        'nearWall':           (plotting.drawNearWall,),
        'mach':               (plotting.drawField, 'mach'),
        'pressure':           (plotting.drawField, 'pressure'),
        'temperature':        (plotting.drawField, 'temperature'),
        'plume':              (plotting.drawPlume,),
        'circuit':            (thermal.drawCircuit,),
        'passes':             (thermal.drawPasses,),
        'wallMap':            (thermal.drawWallMap,),
        'jacketTemperatures': (thermal.drawJacketTemperatures,),
        'coolantFlow':        (thermal.drawCoolantFlow,),
        'coolantProperties':  (thermal.drawCoolantProperties,),
        'heatFlux':           (thermal.drawHeatFlux,),
        'film':               (thermal.drawFilm,),
        'extension':          (thermal.drawExtension,),
        'revolved':           (plotting.drawRevolvedContour,),
    }

def _interactiveBuilder(spec):

    '''The plotly builder for a view, `(figuresModule, nozzle) -> Figure or None`, or None.'''

    builders = _module('plotting').interactiveBuilders
    if spec.builderKey is not None and spec.builderKey in builders:
        return builders[spec.builderKey]

    return _module('coolingFigures').builders.get(spec.key)

def viewList() -> list:

    '''

    Every view in sidebar order, with the renderings it supports.

    Returns:
    --------
    list : [{'key', 'group', 'label', 'source', 'interactive', 'static'}]

    '''

    viewTab = _module('viewTab')
    drawers = _staticDrawers()

    return [{'key': spec.key, 'group': spec.group, 'label': spec.label,
             'source': sourceOverrides.get(spec.key, spec.source),
             'interactive': _interactiveBuilder(spec) is not None,
             'static': spec.key in drawers}
            for spec in viewTab.views]

def availableViews(record) -> list:

    '''

    The keys of the views a run produced, in sidebar order.

    '''

    if record is None:
        return []
    nozzle = record.nozzle()
    if nozzle is None:
        return []

    viewTab, runner = _module('viewTab'), _module('runner')
    outputs = runner.findOutputs(record.outputDir, record.runName)
    available = viewTab.availableViews(nozzle, outputs)

    return [spec.key for spec in viewTab.views if spec.key in available]

def interactiveFigure(nozzle, key: str, mode: str) -> str | None:

    '''

    A view's plotly figure as JSON in a palette mode, or None when the run has no data for it.

    Parameters:
    -----------
    nozzle : Nozzle
        The run's nozzle.
    key : str
        The view's key.
    mode : str
        'dark' or 'light'.

    '''

    viewTab, backend = _module('viewTab'), _module('backend')
    spec = next((spec for spec in viewTab.views if spec.key == key), None)
    builder = _interactiveBuilder(spec) if spec is not None else None
    if builder is None:
        return None

    with renderLock:
        figures = backend.figuresModule()
        figures.figurePalette.setFigureMode(mode)
        figure = builder(figures, nozzle)
        if figure is None:
            return None
        # The pane sizes the figure; a fixed size from the builder would stop it filling the pane
        figure.update_layout(width = None, height = None, autosize = True)
        return figure.to_json()

class HeadlessPane:

    '''

    The part of novaGui.plotting.MplPane the Matplotlib drawers use, on a figure with no canvas.

    A drawer calls `message(text)` instead of drawing when the run lacks its data; the text is
    kept and returned in place of an image.

    '''

    def __init__(self, widthPx: int, heightPx: int, pixelRatio: float):

        from matplotlib.figure import Figure

        theme = _module('theme')
        self.figure = Figure(figsize = (widthPx / 100.0, heightPx / 100.0), dpi = 100.0 * pixelRatio)
        self.figure.patch.set_facecolor(theme.surface)
        self._projection = None
        self.axes = None
        self.messageText = None
        self.clear()

    def clear(self, projection: str = 'keep') -> None:

        if projection != 'keep':
            self._projection = projection
        self.figure.clear()
        self.figure.set_layout_engine('constrained')
        self.axes = self.figure.add_subplot(111, projection = self._projection)
        _module('theme').styleAxes(self.axes)
        if self._projection == '3d':
            self._style3d()

    def _style3d(self) -> None:

        '''Panes and axis lines of a 3D axes in the palette, as MplPane draws them.'''

        from matplotlib.colors import to_rgba

        theme, ax = _module('theme'), self.axes
        ax.set_facecolor(theme.surface)
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            axis.set_pane_color(to_rgba(theme.bg))
            axis.line.set_color(theme.border)
        ax.zaxis.label.set_color(theme.text)
        ax.tick_params(colors = theme.textMuted)

    def message(self, text: str) -> None:

        self.messageText = text

    def redraw(self) -> None:

        pass

def _overrideText(figure) -> None:

    '''

    Reword the drawer text that names a Tkinter control (staticTextOverrides) in every axes title.
    The title's Text is edited in place, so it keeps the size and color the drawer gave it.

    '''

    for ax in figure.axes:
        title = ax.title.get_text()
        reworded = title
        for old, new in staticTextOverrides.items():
            reworded = reworded.replace(old, new)
        if reworded != title:
            ax.title.set_text(reworded)

def staticFigure(nozzle, key: str, mode: str, widthPx: int, heightPx: int, pixelRatio: float) -> dict:

    '''

    A view's Matplotlib drawing as PNG bytes, or the drawer's message when the run lacks its data.

    Parameters:
    -----------
    nozzle : Nozzle
        The run's nozzle.
    key : str
        The view's key.
    mode : str
        'dark' or 'light'.
    widthPx, heightPx : int
        The browser pane's size in CSS pixels.
    pixelRatio : float
        The display's device pixel ratio; the PNG has this many pixels per CSS pixel.

    Returns:
    --------
    dict : {'png': bytes} or {'message': str}; {'message'} also for a view with no static form

    '''

    drawers = _staticDrawers()
    if key not in drawers:
        return {'message': 'This view has no static rendering.'}

    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    theme = _module('theme')
    function, *arguments = drawers[key]

    with renderLock:
        theme._bindPalette(mode)
        plt.rcParams.update(theme.matplotlibRcParams())
        _module('backend').figuresModule().figurePalette.setFigureMode(mode)

        pane = HeadlessPane(max(widthPx, 200), max(heightPx, 150), max(pixelRatio, 1.0))
        function(pane, nozzle, *arguments)
        if pane.messageText is not None:
            return {'message': pane.messageText}
        _overrideText(pane.figure)

        FigureCanvasAgg(pane.figure)
        buffer = io.BytesIO()
        pane.figure.savefig(buffer, format = 'png', facecolor = theme.surface)

    return {'png': buffer.getvalue()}
