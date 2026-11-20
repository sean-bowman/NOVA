
# -- NOVA GUI Views -- #

'''

The result pane's figures, rendered for the browser.

The list of views and the test of which ones a run produced are novaGui.viewCatalog, which the
legacy Tkinter front end reads too. Each view renders one or both of two ways:

    interactive   a plotly figure as JSON, drawn in the browser by plotly.js at full resolution,
                  from the builder novaGui.plotting.interactiveBuilders names for the view, or for
                  the ten cooling views from novaGui.coolingFigures
    static        the Matplotlib drawing (novaGui.plotting, novaGui.thermalPlots), rendered
                  headless to PNG at the browser pane's size and pixel ratio

The 3D assemblies render interactive only: their Matplotlib form is a decimated stand-in for the
WebGL view. The browser draws every view interactive and saves the static drawing as a PNG.

The line plots along the nozzle axis (`comparableViews`) can draw a second run over the first: its
lines dashed in the same colors, named for their run, and the title saying which run is which. The
second run's fills, markers, shapes and labels are left out, so the first run's picture reads as it
does alone.

While a run is going, the views its contour stage settles draw from the figure descriptions the
worker sent (`partialFigure`), through the same renderers as the finished run's. So does the circuit
iteration view, from the passes the session has kept so far (coolingFigures.describedBuilders).

The contour and the near-wall state hover along the axis here (`alongAxisHover`), as the cooling
plots do, so the browser's axial cursor reads the wall radius and the gas state at its station. In
NOVA's own HTML they hover to the nearest point.

The Matplotlib plume title tells a legacy Tkinter user that its "Open interactive" button shows
the correlated structure beyond the march. Here the same figure, saved as a PNG, says the interactive
view does.

Figures are drawn in one palette mode at a time, and the mode lives in module globals
(NOVA.palette for both renderers, novaGui.themeColors and Matplotlib's rcParams for the static one), so
every render holds `renderLock`.

Importing the drawers loads NOVA and the scientific stack, several seconds the first time. `warmUp` does it on a background thread when the server starts.

Author: Sean Bowman
Date:   11/16/2026

'''

# Standard library imports
import io
import threading

renderLock = threading.Lock()
_ready = threading.Event()
_modules = {}

# The view catalog's source line says the static 3D assemblies are decimated; plotly.js draws the
# full mesh here
sourceOverrides = {
    'channelMesh': '3D assembly, full mesh',
    'volute':      '3D assembly, full mesh',
}

# Views that hover along the axis in the browser, where NOVA's own figures hover to the nearest point
alongAxisHover = frozenset({'contour', 'nearWall'})

# Line plots along the nozzle axis, which can draw a second run over the first
comparableViews = frozenset({'contour', 'nearWall', 'passes', 'jacketTemperatures', 'coolantFlow', 'coolantProperties',
                             'heatFlux', 'film', 'extension'})

# Text in the shared Matplotlib drawers that names a legacy Tkinter control, and what it reads here
staticTextOverrides = {
    'Open interactive shows them': 'the interactive view shows them',
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
        from . import backend, coolingFigures, plotting, runner, themeColors, thermalPlots, viewCatalog
        _modules.update(plotting = plotting, runner = runner, themeColors = themeColors, thermalPlots = thermalPlots,
                        backend = backend, viewCatalog = viewCatalog, coolingFigures = coolingFigures)
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
        'circuitIterations':  (thermal.drawCircuitIterations,),
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
    list : [{'key', 'group', 'label', 'source', 'interactive', 'static', 'comparable'}]

    '''

    catalog = _module('viewCatalog')
    drawers = _staticDrawers()

    return [{'key': spec.key, 'group': spec.group, 'label': spec.label,
             'source': sourceOverrides.get(spec.key, spec.source),
             'interactive': _interactiveBuilder(spec) is not None,
             'static': spec.key in drawers,
             'comparable': spec.key in comparableViews}
            for spec in catalog.views]

def availableViews(record) -> list:

    '''

    The keys of the views a run produced, in sidebar order.

    '''

    if record is None:
        return []
    nozzle = record.nozzle()
    if nozzle is None:
        return []

    catalog, runner = _module('viewCatalog'), _module('runner')
    outputs = runner.findOutputs(record.outputDir, record.runName)
    available = catalog.availableViews(nozzle, outputs)

    return [spec.key for spec in catalog.views if spec.key in available]

def _overlay(figure, other, runLabel: str, otherLabel: str) -> None:

    '''

    Draw a second run's lines over a figure: each line trace of `other` dashed in its own color,
    named and hovered for its run, on the same axes. The title says which run is which.

    '''

    for trace in other.data:
        if trace.type not in ('scatter', 'scattergl') or 'lines' not in (trace.mode or 'lines'):
            continue
        if trace.fill not in (None, 'none'):
            continue
        copy = trace.to_plotly_json()
        copy.pop('type', None)
        copy.pop('uid', None)
        line = dict(copy.get('line') or {})
        line['dash'] = 'dash'
        copy.update(line = line, legendgroup = 'compared', opacity = 0.9,
                    name = f"{copy.get('name') or 'line'}, {otherLabel}")
        template = copy.get('hovertemplate')
        if isinstance(template, str) and '<extra>' in template:
            copy['hovertemplate'] = template[:template.index('<extra>')] + f'<extra>{otherLabel}</extra>'
        figure.add_trace(type(trace)(copy))

    title = figure.layout.title.text or ''
    figure.update_layout(title_text = f'{title}<br><sup>solid: {runLabel}, dashed: {otherLabel}</sup>')
    margin = figure.layout.margin.t
    figure.update_layout(margin_t = (margin if margin is not None else 80) + 18)

def _render(builder, figures, nozzle, mode: str):

    figures.figurePalette.setFigureMode(mode)
    return builder(figures, nozzle)

def interactiveFigure(nozzle, key: str, mode: str, compare = None, labels: tuple = ('this run', 'the other run')) -> str | None:

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
    compare : Nozzle, optional
        A second run to draw over the first; only for `comparableViews`, and ignored otherwise.
    labels : tuple
        What the title and the legend call the two runs: (this run, the compared run).

    '''

    catalog, backend = _module('viewCatalog'), _module('backend')
    spec = next((spec for spec in catalog.views if spec.key == key), None)
    builder = _interactiveBuilder(spec) if spec is not None else None
    if builder is None:
        return None

    with renderLock:
        figures = backend.figuresModule()
        figure = _render(builder, figures, nozzle, mode)
        if figure is None:
            return None
        if compare is not None and key in comparableViews:
            other = _render(builder, figures, compare, mode)
            if other is not None:
                _overlay(figure, other, *labels)
        _forBrowser(figure, key)
        return figure.to_json()

def _forBrowser(figure, key: str) -> None:

    '''

    Size a figure to its pane, and hover along the axis where `alongAxisHover` names the view: the
    pane sizes the figure, so a fixed size from the builder would stop it filling the pane.

    '''

    figure.update_layout(width = None, height = None, autosize = True)
    if key in alongAxisHover:
        figure.update_layout(hovermode = 'x unified')

def partialFigure(description, key: str, mode: str) -> str | None:

    '''

    A view of a run still going, as plotly JSON, drawn from the figure description its contour stage
    settled (novaGui.plotting.figureDescriptions) or from the circuit's passes so far
    (novaGui.coolingFigures.describedBuilders), or None.

    '''

    plotting, backend, cooling = _module('plotting'), _module('backend'), _module('coolingFigures')
    if description is None:
        return None
    if key in plotting.figureDescriptions:
        _, render = plotting.figureDescriptions[key]
    elif key in cooling.describedBuilders:
        render = cooling.describedBuilders[key]
    else:
        return None

    with renderLock:
        figures = backend.figuresModule()
        figures.figurePalette.setFigureMode(mode)
        figure = render(figures, description)
        if figure is None:
            return None
        _forBrowser(figure, key)
        return figure.to_json()

class HeadlessPane:

    '''

    The pane the Matplotlib drawers draw into (see novaGui.plotting), on a figure with no canvas.

    A drawer calls `message(text)` instead of drawing when the run lacks its data; the text is
    kept and returned in place of an image.

    '''

    def __init__(self, widthPx: int, heightPx: int, pixelRatio: float):

        from matplotlib.figure import Figure

        theme = _module('themeColors')
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
        _module('themeColors').styleAxes(self.axes)
        if self._projection == '3d':
            self._style3d()

    def _style3d(self) -> None:

        '''Panes and axis lines of a 3D axes in the palette.'''

        from matplotlib.colors import to_rgba

        theme, ax = _module('themeColors'), self.axes
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

    Reword the drawer text that names a legacy Tkinter control (staticTextOverrides) in every axes title.
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

    theme = _module('themeColors')
    function, *arguments = drawers[key]

    with renderLock:
        theme.bindPalette(mode)
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
