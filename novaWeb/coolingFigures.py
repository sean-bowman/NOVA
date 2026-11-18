# -- NOVA Web Cooling Figures -- #

'''

Plotly renderings of the View tab's nine cooling views, for the browser.

Each builder draws the same quantities as its Matplotlib counterpart in novaGui.thermalPlots, from
the same arrays on the Nozzle and with the same titles, colors and annotations, and reads them
through that module's own accessors (`thermalResults`, `filmSolved`, `extensionSolved`, the metal
wall under a barrier coating). What plotly adds is reading values by hovering, and zoom and pan.

    circuit             the coolant's paths on the half section: families, manifolds, turnaround,
                        split, extension circuit, radiation-cooled shell and film slots
    passes              each pass's coolant and hot wall
    wallMap             the jacket on the wall, hot wall and coolant colored by temperature
    jacketTemperatures  the hot wall against its limit and the gas driving it; the coolant warming
    coolantFlow         coolant pressure, velocity and Mach number
    coolantProperties   coolant density, viscosity and specific heat
    heatFlux            heat flux with its radiative share, both film coefficients, Re and Nu
    film                the film map, its effectiveness and the temperatures it sets
    extension           the whole wall on one temperature scale, the extension's wall and its
                        heat balance

Two drawing choices differ from Matplotlib's. A line colored station by station (the wall and
coolant bands) is drawn as closely spaced markers resampled along the arc, because a plotly line
takes one color; a transparent marker at each solver station carries the hover, so the values
read are the solver's own. The film map's curvilinear core and film band are resampled onto a
rectangular grid for a heatmap, blank outside the wall, as NOVA's plume field is. On the
extension's heat balance the conducted flux is drawn in orange where Matplotlib reuses the gas
radiation's pewter, so the two series stay apart.

Builders take `(figuresModule, nozzle)`, the signature of novaGui.plotting.interactiveBuilders,
and draw in the palette mode NOVA.palette holds; the caller sets it. Each returns None when the run
lacks the view's data.

Author: Sean Bowman
Date:   11/17/2026

'''

# Third-party imports
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Local imports
from novaGui import thermalPlots

_fontFamily = 'Segoe UI, Inter, sans-serif'

#--------------------------------------------------------------------------------------------------------------------------#
# -- Shared -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _rgba(color: str, alpha: float) -> str:

    '''A '#RRGGBB' color at an opacity, as plotly's rgba() text.'''

    color = color.lstrip('#')
    red, green, blue = (int(color[index:index + 2], 16) for index in (0, 2, 4))

    return f'rgba({red},{green},{blue},{alpha})'

def _style(figure: go.Figure, colors: dict, title: str, hovermode: str = 'x unified') -> None:

    '''

    The layout every cooling figure shares: NOVA's figure backgrounds and font, themed axes, hover
    labels and legends, and the subplot titles in the muted text color.

    '''

    for annotation in figure.layout.annotations:
        annotation.font = dict(color = colors['textMuted'], size = 12)
    figure.update_layout(
        title = dict(text = title, font = dict(color = colors['text'], size = 15)),
        paper_bgcolor = colors['surface'],
        plot_bgcolor = colors['bg'],
        font = dict(color = colors['text'], family = _fontFamily, size = 12),
        margin = dict(l = 72, r = 30, t = 64, b = 56),
        hovermode = hovermode,
        hoverlabel = dict(bgcolor = colors['surface2'], bordercolor = colors['border'],
                          font = dict(color = colors['text'], family = _fontFamily)),
        legend = _legendStyle(colors),
        showlegend = True,
    )
    # No zero lines: Matplotlib draws none, and a zero line on a map reads as a station
    axis = dict(gridcolor = colors['border'], linecolor = colors['border'], zeroline = False, tickcolor = colors['border'])
    figure.update_xaxes(hoverformat = '.4f', **axis)
    figure.update_yaxes(**axis)

def _legendStyle(colors: dict) -> dict:

    return dict(bgcolor = _rgba(colors['surface2'], 0.92), bordercolor = colors['border'], borderwidth = 1,
                font = dict(size = 11, color = colors['text']), traceorder = 'normal')

def _legendIn(figure: go.Figure, name: str, row: int, col: int, corner: str, colors: dict) -> None:

    '''

    Place a legend inside one panel, at a corner of its domain, as Matplotlib's per-axes legends sit.
    A row of None places it in a figure without panels.

    Parameters:
    -----------
    name : str
        'legend', 'legend2', ...; traces name it in their `legend` property.
    corner : str
        'upper left', 'upper right', 'lower left', 'lower right' or 'lower center'.

    '''

    if row is None:
        (x0, x1), (y0, y1) = (0.0, 1.0), (0.0, 1.0)
    else:
        subplot = figure.get_subplot(row, col)
        (x0, x1), (y0, y1) = subplot.xaxis.domain, subplot.yaxis.domain
    vertical, horizontal = corner.split()
    xPosition = {'left': x0 + 0.01, 'right': x1 - 0.01, 'center': 0.5 * (x0 + x1)}[horizontal]
    yPosition = y1 - 0.01 if vertical == 'upper' else y0 + 0.02
    figure.update_layout({name: dict(x = xPosition, y = yPosition, xanchor = horizontal,
                                     yanchor = 'top' if vertical == 'upper' else 'bottom', **_legendStyle(colors))})

def _line(x, y, name: str, color: str, width: float = 1.7, dash: str = None, unit: str = 'K', valueFormat: str = '.0f',
          legend: str = 'legend', showlegend: bool = True) -> go.Scatter:

    '''A series along the axis, its hover reading `name value unit`.'''

    return go.Scatter(x = np.asarray(x, dtype = float), y = np.asarray(y, dtype = float), mode = 'lines', name = name,
                      line = dict(color = color, width = width, dash = dash), legend = legend, showlegend = showlegend,
                      hovertemplate = f'{name} %{{y:{valueFormat}}} {unit}<extra></extra>')

def _level(x, value: float, name: str, color: str, legend: str = 'legend', showlegend: bool = True) -> go.Scatter:

    '''A dashed horizontal level across the axis span, with a legend entry: a limit or a threshold.'''

    x = np.asarray(x, dtype = float)

    return go.Scatter(x = [float(np.min(x)), float(np.max(x))], y = [value, value], mode = 'lines', name = name,
                      line = dict(color = color, width = 1.2, dash = 'dash'), legend = legend, showlegend = showlegend,
                      hovertemplate = f'{name}<extra></extra>')

def _filled(x, y, color: str, base: float = None) -> list:

    '''

    A translucent fill under a series, down to `base`, or to zero without one. A base below the
    data keeps a double-click autorange off zero, which a fill to zero would pull it to.

    '''

    x, y = np.asarray(x, dtype = float), np.asarray(y, dtype = float)
    if base is None:
        return [go.Scatter(x = x, y = y, mode = 'lines', line = dict(width = 0), fill = 'tozeroy',
                           fillcolor = _rgba(color, 0.22), hoverinfo = 'skip', showlegend = False)]

    return [go.Scatter(x = x, y = np.full_like(y, base), mode = 'lines', line = dict(width = 0), hoverinfo = 'skip',
                       showlegend = False),
            go.Scatter(x = x, y = y, mode = 'lines', line = dict(width = 0), fill = 'tonexty',
                       fillcolor = _rgba(color, 0.15), hoverinfo = 'skip', showlegend = False)]

def _throatX(nozzle) -> float | None:

    '''The throat's axial position, where the jacket's hardest station is, or None.'''

    wallX, wallR = thermalPlots._array(nozzle, 'xNozzleWall'), thermalPlots._array(nozzle, 'rNozzleWall')
    if wallX.size < 2 or wallR.size != wallX.size:
        return None

    return float(wallX[int(np.argmin(wallR))])

def _throat(figure: go.Figure, nozzle, cells, colors: dict) -> None:

    '''Mark the throat on each axial panel, given as (row, col) pairs.'''

    throatX = _throatX(nozzle)
    if throatX is None:
        return
    for row, col in cells:
        figure.add_vline(x = throatX, line = dict(color = colors['textDim'], width = 1, dash = 'dot'), layer = 'below',
                         row = row, col = col)

def _flowDirection(figure: go.Figure, x, pressure, row: int, col: int, color: str) -> None:

    '''Name the coolant's inlet and outlet ends, which the pressure falling along the flow gives away.'''

    x, pressure = np.asarray(x, dtype = float), np.asarray(pressure, dtype = float)
    inlet, outlet = int(np.argmax(pressure)), int(np.argmin(pressure))
    if inlet == outlet:
        return
    for index, word in ((inlet, 'coolant in'), (outlet, 'out')):
        figure.add_annotation(x = float(x[index]), y = 1.0, yref = 'y domain', text = word, showarrow = False,
                              xanchor = 'left' if index < len(x) // 2 else 'right', yanchor = 'top', yshift = -4,
                              font = dict(color = color, size = 11), row = row, col = col)

def _note(figure: go.Figure, text: str, row: int, col: int, color: str) -> None:

    '''A small italic note in a panel's lower right corner: what is drawn not to scale.'''

    figure.add_annotation(x = 0.995, y = 0.03, xref = 'x domain', yref = 'y domain', text = f'<i>{text}</i>',
                          showarrow = False, xanchor = 'right', yanchor = 'bottom', font = dict(color = color, size = 10),
                          row = row, col = col)

def _niceStep(span: float) -> float:

    '''A tick step of 1, 2 or 5 times a power of ten giving about five ticks over a span.'''

    if span <= 0.0:
        return 1.0
    raw = span / 5.0
    power = 10.0 ** np.floor(np.log10(raw))

    return float(next(factor for factor in (1.0, 2.0, 5.0, 10.0) if factor * power >= raw) * power)

def _scaleWithLimit(low: float, high: float, limit, colors: dict) -> dict:

    '''

    Color bar ticks with the temperature limit marked in red, as the Matplotlib scale draws a red
    line at it. Ordinary ticks too close to the limit to read beside it are dropped.

    '''

    step = _niceStep(high - low)
    values = np.arange(np.ceil(low / step) * step, high + 1e-9, step)
    if not limit:
        return {}
    limit = float(limit)
    kept = [float(value) for value in values if abs(value - limit) > 0.08 * (high - low)]

    return dict(tickmode = 'array', tickvals = kept + [limit],
                ticktext = [f'{value:.0f}' for value in kept] + [f'<b><span style="color:{colors["red"]}">limit {limit:.0f}'
                                                                f'</span></b>'])

def _band(x, r, values, colorscale, low: float, high: float, size: float, label: str, colorbar: dict = None) -> list:

    '''

    A line along (x, r) colored by `values`, drawn as markers spaced closely enough to join, and a
    transparent marker at each station that carries the hover.

    Parameters:
    -----------
    size : float
        The band's width [px].
    label : str
        What the hover names the value.
    colorbar : dict, optional
        The color bar to show for this band; none without it.

    '''

    x, r, values = (np.asarray(array, dtype = float) for array in (x, r, values))
    arc = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(r)))])
    dense = np.linspace(0.0, arc[-1], max(900, 4 * x.size))
    marker = dict(size = size, color = np.interp(dense, arc, values), colorscale = colorscale, cmin = low, cmax = high,
                  line = dict(width = 0), showscale = colorbar is not None)
    if colorbar is not None:
        marker['colorbar'] = colorbar

    return [go.Scatter(x = np.interp(dense, arc, x), y = np.interp(dense, arc, r), mode = 'markers', marker = marker,
                       hoverinfo = 'skip', showlegend = False),
            go.Scatter(x = x, y = r, mode = 'markers', marker = dict(size = size, color = 'rgba(0,0,0,0)'),
                       customdata = values, showlegend = False,
                       hovertemplate = f'x %{{x:.4f}} m<br>r %{{y:.4f}} m<br>{label} %{{customdata:.0f}} K<extra></extra>')]

def _colorbar(colors: dict, title: str, **placement) -> dict:

    return dict(title = dict(text = title, side = 'right' if placement.get('orientation', 'v') == 'v' else 'bottom',
                             font = dict(color = colors['text'])),
                thickness = 12, outlinecolor = colors['border'], tickfont = dict(color = colors['textMuted']),
                **placement)

def _contourUnder(figure: go.Figure, nozzle, colors: dict, row: int = None, col: int = None) -> np.ndarray:

    '''The whole wall contour for context, with the gas side shaded. Returns its axial positions.'''

    wallX, wallR = thermalPlots._array(nozzle, 'xNozzleWall'), thermalPlots._array(nozzle, 'rNozzleWall')
    if wallX.size == wallR.size and wallX.size:
        figure.add_trace(go.Scatter(x = wallX, y = wallR, mode = 'lines', line = dict(color = colors['textDim'], width = 1),
                                    fill = 'tozeroy', fillcolor = _rgba(colors['surface2'], 0.35), hoverinfo = 'skip',
                                    showlegend = False), row = row, col = col)

    return wallX

def _equalAspect(figure: go.Figure, row: int, col: int, xRange, yRange) -> None:

    '''One meter on the radius as long as one on the axis, the panel shrinking to keep it.'''

    figure.update_xaxes(range = list(xRange), constrain = 'domain', showgrid = False, row = row, col = col)
    figure.update_yaxes(range = list(yRange), constrain = 'domain', showgrid = False, scaleanchor = _axisName(figure, row, col, 'x'),
                        scaleratio = 1, row = row, col = col)

def _axisName(figure: go.Figure, row: int, col: int, which: str) -> str:

    '''An axis's reference name ('x', 'x2', ...) for the panel at (row, col); 'x' or 'y' without panels.'''

    if row is None:
        return which
    subplot = figure.get_subplot(row, col)
    axis = subplot.xaxis if which == 'x' else subplot.yaxis

    return axis.plotly_name.replace('axis', '')

def _colors(figures) -> dict:

    return figures.figurePalette.colors()

#--------------------------------------------------------------------------------------------------------------------------#
# -- The jacket -- #
#--------------------------------------------------------------------------------------------------------------------------#

def wallMap(figures, nozzle):

    '''

    The jacket on the nozzle wall: the hot wall colored by its temperature, and outside it the
    coolant channel colored by the coolant's, with the wall limit marked on the wall's scale.

    '''

    results = thermalPlots.thermalResults(nozzle)
    if results is None:
        return None
    colors, palette = _colors(figures), figures.figurePalette

    x, r = np.asarray(results['xHotWall3D'], dtype = float), np.asarray(results['rHotWall3D'], dtype = float)
    wall, coolant = thermalPlots._metalWall(results), np.asarray(results['temperature'], dtype = float)
    limit = getattr(nozzle, 'maxWallTemperature', None)
    # The channel sits millimetres outside the wall, closer than two readable bands can be drawn, so
    # its band is set out by a fixed fraction of the chamber radius and labelled as such
    offset = 0.12 * float(np.max(r))

    figure = go.Figure()
    _contourUnder(figure, nozzle, colors)
    top = max(float(np.max(wall)), float(limit) if limit else 0.0)
    wallScale = _colorbar(colors, 'Hot wall temperature [K]', orientation = 'h', x = 0.24, xanchor = 'center',
                          len = 0.46, y = -0.16, yanchor = 'top', **_scaleWithLimit(float(np.min(wall)), top, limit, colors))
    coolantScale = _colorbar(colors, 'Coolant temperature [K]', orientation = 'h', x = 0.76, xanchor = 'center',
                             len = 0.46, y = -0.16, yanchor = 'top')
    for trace in _band(x, r + offset, coolant, palette.plotlyColorscale('mach'), float(np.min(coolant)),
                       float(np.max(coolant)), 6.0, 'Coolant', coolantScale):
        figure.add_trace(trace)
    for trace in _band(x, r, wall, palette.plotlyColorscale('temperature'), float(np.min(wall)), top, 8.0, 'Hot wall',
                       wallScale):
        figure.add_trace(trace)

    figure.add_annotation(x = float(np.mean(x)), y = 0.45 * float(np.min(r)), text = '<i>exhaust</i>', showarrow = False,
                          font = dict(color = colors['textMuted'], size = 12))
    _flowDirection(figure, x, results['pressure'], None, None, colors['textMuted'])
    _note(figure, 'coolant band drawn outside the wall, not to scale', None, None, colors['textMuted'])

    channels = int(getattr(nozzle, 'nChannel', 0) or 0)
    total = float(np.sum(results['heatTransfer'])) * float(channels or 1)
    _style(figure, colors, f'The jacket on the wall: {channels} channels, {total / 1e6:.2f} MW into the coolant',
           hovermode = 'closest')
    span = float(np.max(x) - np.min(x))
    _equalAspect(figure, None, None, (float(np.min(x)) - 0.04 * span, float(np.max(x)) + 0.04 * span),
                 (0.0, 1.3 * float(np.max(r + offset))))
    figure.update_xaxes(title_text = 'Nozzle axis [m]')
    figure.update_yaxes(title_text = 'Radius [m]')
    figure.update_layout(margin = dict(b = 120), showlegend = False)

    return figure

def jacketTemperatures(figures, nozzle):

    '''The hot wall against its limit, with the gas driving it on its own scale, and the coolant warming.'''

    results = thermalPlots.thermalResults(nozzle)
    if results is None:
        return None
    colors = _colors(figures)

    x = np.asarray(results['xHotWall3D'], dtype = float)
    coolant = np.asarray(results['temperature'], dtype = float)
    rise = float(np.max(coolant) - np.min(coolant))
    figure = make_subplots(rows = 2, cols = 1, shared_xaxes = True, vertical_spacing = 0.09, row_heights = [0.58, 0.42],
                           specs = [[{'secondary_y': True}], [{}]],
                           subplot_titles = ('', f'Coolant warms {rise:.0f} K, from {float(np.min(coolant)):.0f} to '
                                                 f'{float(np.max(coolant)):.0f} K'))

    metal, surface = thermalPlots._metalWall(results), np.asarray(results['wallTemperature'], dtype = float)
    figure.add_trace(_line(x, metal, 'Hot wall', colors['accent'], 1.8), row = 1, col = 1)
    if not np.array_equal(metal, surface):
        figure.add_trace(_line(x, surface, 'Coating surface', colors['accent'], 1.2, 'dot'), row = 1, col = 1)
    limit = getattr(nozzle, 'maxWallTemperature', None)
    if limit:
        figure.add_trace(_level(x, float(limit), f'Wall limit {float(limit):.0f} K', colors['red']), row = 1, col = 1)
    figure.add_trace(_line(x, results['drivingTemperature'], 'Gas driving the wall', colors['blue'], 1.2), row = 1, col = 1,
                     secondary_y = True)

    for trace in _filled(x, coolant, colors['cyan'], float(np.min(coolant))):
        figure.add_trace(trace, row = 2, col = 1)
    figure.add_trace(_line(x, coolant, 'Coolant', colors['cyan'], 1.8, showlegend = False), row = 2, col = 1)
    _flowDirection(figure, x, results['pressure'], 2, 1, colors['textMuted'])

    _style(figure, colors, 'Wall and coolant temperatures')
    figure.update_yaxes(title_text = 'Hot wall temperature [K]', row = 1, col = 1, secondary_y = False)
    figure.update_yaxes(title_text = 'Gas driving temperature [K]', title_font_color = colors['blue'],
                        tickfont_color = colors['blue'], showgrid = False, row = 1, col = 1, secondary_y = True)
    figure.update_yaxes(title_text = 'Coolant temperature [K]', row = 2, col = 1)
    figure.update_xaxes(title_text = 'Nozzle axis [m]', row = 2, col = 1)
    _legendIn(figure, 'legend', 1, 1, 'lower center', colors)
    figure.update_layout(legend_orientation = 'h')
    _throat(figure, nozzle, ((1, 1), (2, 1)), colors)

    return figure

def _stack(figures, nozzle, title: str, series) -> go.Figure:

    '''

    Three panels along the channel, one series each, with the flow direction on the first.

    Parameters:
    -----------
    series : sequence of (values, label, color, unit, format)

    '''

    results = thermalPlots.thermalResults(nozzle)
    colors = _colors(figures)
    x = np.asarray(results['xHotWall3D'], dtype = float)

    figure = make_subplots(rows = 3, cols = 1, shared_xaxes = True, vertical_spacing = 0.05)
    for row, (values, label, color, unit, valueFormat) in enumerate(series, start = 1):
        name = label.split(' [')[0]
        figure.add_trace(_line(x, values, name, colors[color], 1.7, unit = unit, valueFormat = valueFormat,
                               showlegend = False), row = row, col = 1)
        figure.update_yaxes(title_text = label, row = row, col = 1)
    _flowDirection(figure, x, results['pressure'], 1, 1, colors['textMuted'])
    _style(figure, colors, title)
    figure.update_xaxes(title_text = 'Nozzle axis [m]', row = 3, col = 1)
    _throat(figure, nozzle, ((1, 1), (2, 1), (3, 1)), colors)

    return figure

def coolantFlow(figures, nozzle):

    '''Coolant pressure, velocity and Mach number along the channel.'''

    results = thermalPlots.thermalResults(nozzle)
    if results is None:
        return None

    pressure = np.asarray(results['pressure'], dtype = float)
    drop = float(np.max(pressure) - np.min(pressure))

    return _stack(figures, nozzle,
                  f'Coolant flow: {drop / 1e3:.0f} kPa pressure drop, exit at {float(np.min(pressure)) / 1e6:.2f} MPa',
                  ((pressure / 1e6, 'Pressure [MPa]', 'accent', 'MPa', '.4f'),
                   (results['velocity'], 'Velocity [m/s]', 'blue', 'm/s', '.2f'),
                   (results['machNumber'], 'Mach number [-]', 'cyan', '', '.4f')))

def coolantProperties(figures, nozzle):

    '''The coolant's density, viscosity and specific heat along the channel, from its equation of state.'''

    results = thermalPlots.thermalResults(nozzle)
    if results is None:
        return None

    coolant = getattr(nozzle, 'coolant', None) or 'coolant'

    return _stack(figures, nozzle, f'Thermophysical properties of the {coolant} along the channel',
                  ((results['density'], 'Density [kg/m³]', 'accent', 'kg/m³', '.1f'),
                   (np.asarray(results['viscosity'], dtype = float) * 1e6, 'Viscosity [µPa·s]', 'purple', 'µPa·s', '.2f'),
                   (np.asarray(results['specificHeat'], dtype = float) * 1e-3, 'Specific heat [kJ/kg·K]', 'green',
                    'kJ/kg·K', '.3f')))

def heatFlux(figures, nozzle):

    '''

    The heat flux through the hot wall with its radiative share, the gas-side and coolant-side film
    coefficients, and the coolant's Reynolds and Nusselt numbers.

    '''

    results = thermalPlots.thermalResults(nozzle)
    if results is None:
        return None
    colors = _colors(figures)

    x = np.asarray(results['xHotWall3D'], dtype = float)
    flux = np.asarray(results['heatFlux'], dtype = float) / 1e6
    figure = make_subplots(rows = 3, cols = 1, shared_xaxes = True, vertical_spacing = 0.05,
                           specs = [[{}], [{}], [{'secondary_y': True}]])

    for trace in _filled(x, flux, colors['accent']):
        figure.add_trace(trace, row = 1, col = 1)
    heat = np.asarray(results['heatTransfer'], dtype = float)
    radiative = np.asarray(results.get('radiativeHeatTransfer', np.zeros_like(heat)), dtype = float)
    hasRadiative = bool(np.any(radiative))
    figure.add_trace(_line(x, flux, 'Total', colors['accent'], 1.7, unit = 'MW/m²', valueFormat = '.2f',
                           showlegend = hasRadiative), row = 1, col = 1)
    if hasRadiative:
        share = np.divide(radiative, heat, out = np.zeros_like(heat), where = heat != 0.0)
        figure.add_trace(_line(x, flux * share, 'Radiative share', colors['purple'], 1.2, unit = 'MW/m²',
                               valueFormat = '.3f'), row = 1, col = 1)
        _legendIn(figure, 'legend', 1, 1, 'upper left', colors)

    figure.add_trace(_line(x, np.asarray(results['exhaustConvectiveHeatTransferCoef'], dtype = float) / 1e3, 'Gas side',
                           colors['red'], 1.6, unit = 'kW/m²·K', valueFormat = '.2f', legend = 'legend2'), row = 2, col = 1)
    figure.add_trace(_line(x, np.asarray(results['coolantConvectiveHeatTransferCoef'], dtype = float) / 1e3, 'Coolant side',
                           colors['cyan'], 1.6, unit = 'kW/m²·K', valueFormat = '.2f', legend = 'legend2'), row = 2, col = 1)
    _legendIn(figure, 'legend2', 2, 1, 'upper left', colors)

    figure.add_trace(_line(x, np.asarray(results['reynoldsNumber'], dtype = float) / 1e6, 'Reynolds number', colors['blue'],
                           1.6, unit = '× 10⁶', valueFormat = '.3f', showlegend = False), row = 3, col = 1)
    figure.add_trace(_line(x, results['nusseltNumber'], 'Nusselt number', colors['green'], 1.4, unit = '', valueFormat = '.0f',
                           showlegend = False), row = 3, col = 1, secondary_y = True)

    _style(figure, colors, f'Heat flux peaks at {float(np.max(flux)):.1f} MW/m²')
    figure.update_yaxes(title_text = 'Heat flux [MW/m²]', row = 1, col = 1)
    figure.update_yaxes(title_text = 'Film coefficient [kW/m²·K]', row = 2, col = 1)
    figure.update_yaxes(title_text = 'Reynolds number [10⁶]', title_font_color = colors['blue'],
                        tickfont_color = colors['blue'], row = 3, col = 1, secondary_y = False)
    figure.update_yaxes(title_text = 'Nusselt number [-]', title_font_color = colors['green'],
                        tickfont_color = colors['green'], showgrid = False, row = 3, col = 1, secondary_y = True)
    figure.update_xaxes(title_text = 'Nozzle axis [m]', row = 3, col = 1)
    _throat(figure, nozzle, ((1, 1), (2, 1), (3, 1)), colors)

    return figure

#--------------------------------------------------------------------------------------------------------------------------#
# -- The film -- #
#--------------------------------------------------------------------------------------------------------------------------#

def film(figures, nozzle):

    '''

    The film along the wall: a map of the film against the core gas, the effectiveness falling away
    from the slot, and the temperature the film holds the wall to against what the gas would drive it
    to without one. The entrainment model's own arrays are added when it ran.

    '''

    if not thermalPlots.filmSolved(nozzle):
        return None
    colors, palette = _colors(figures), figures.figurePalette

    array = lambda name: thermalPlots._array(nozzle, name)
    x, r = array('xRegenNozzle'), array('rRegenNozzle')
    effectiveness = array('regenSectionFilmEffectiveness')
    driving = array('regenSectionFilmDrivingTemperature')
    recovery = array('regenSectionNearWallRecoveryTemperature')
    entrained = array('regenSectionFilmEntrainmentFlowRatio')
    mixture = array('regenSectionFilmWallMixtureRatio')
    hasEntrainment = entrained.size == x.size and mixture.size == x.size
    slot = int(np.argmax(effectiveness > 0.0))
    survival = float(getattr(nozzle, 'filmSurvivalLength', 0.0) or 0.0)

    columns = 3 if hasEntrainment else 2
    lower = [{} for _ in range(columns)]
    if hasEntrainment:
        lower[-1] = {'secondary_y': True}
    figure = make_subplots(rows = 2, cols = columns, row_heights = [0.55, 0.45], vertical_spacing = 0.14,
                           horizontal_spacing = 0.09 if hasEntrainment else 0.08,
                           specs = [[{'colspan': columns}] + [None] * (columns - 1), lower])

    # -- The map: the core at its recovery temperature, the film as a band on the wall -- #
    # The core and band follow the contour, which is not a rectangular grid, so both are resampled
    # onto one for the heatmap and left blank outside the wall
    thickness = 0.07 * float(np.max(r))
    top = 1.3 * float(np.max(r))
    gridX = np.linspace(float(np.min(x)), float(np.max(x)), 400)
    gridR = np.linspace(0.0, top, 180)
    wallR = np.interp(gridX, x, r)
    radius = gridR[:, None]
    field = np.where(radius < (wallR - thickness)[None, :], np.interp(gridX, x, recovery)[None, :],
                     np.where(radius <= wallR[None, :], np.interp(gridX, x, driving)[None, :], np.nan))
    # Single precision halves what the browser downloads, and a tenth of a kelvin is far below
    # what the colors resolve
    field = field.astype(np.float32)
    figure.add_trace(go.Heatmap(x = gridX, y = gridR, z = field, colorscale = palette.plotlyColorscale('temperature'),
                                zmin = float(np.min(driving)), zmax = float(np.max(recovery)), zsmooth = False,
                                hovertemplate = 'x %{x:.4f} m<br>r %{y:.4f} m<br>gas at the wall %{z:.0f} K<extra></extra>',
                                colorbar = _colorbar(colors, 'Gas temperature at the wall [K]', x = 1.0, xanchor = 'left',
                                                     y = 0.5 * sum(figure.get_subplot(1, 1).yaxis.domain), yanchor = 'middle',
                                                     len = 0.5)),
                     row = 1, col = 1)
    figure.add_trace(go.Scatter(x = x, y = r, mode = 'lines', line = dict(color = colors['accent'], width = 2.0),
                                name = 'Wall', showlegend = False, hovertemplate = 'Wall r %{y:.4f} m<extra></extra>'),
                     row = 1, col = 1)
    figure.add_annotation(x = float(x[slot]), y = float(r[slot]), ax = float(x[slot]), ay = 1.18 * float(np.max(r)),
                          axref = _axisName(figure, 1, 1, 'x'), ayref = _axisName(figure, 1, 1, 'y'), text = 'slot',
                          showarrow = True, arrowhead = 2, arrowwidth = 1, arrowcolor = colors['textMuted'],
                          font = dict(color = colors['text'], size = 11), row = 1, col = 1)
    if survival > 0.0:
        end = float(x[slot]) + survival
        figure.add_vline(x = end, line = dict(color = colors['textMuted'], width = 1, dash = 'dash'), row = 1, col = 1)
        figure.add_annotation(x = end, y = 1.08 * float(np.max(r)), text = 'effectiveness 0.3', showarrow = False,
                              xanchor = 'left', xshift = 4, font = dict(color = colors['textMuted'], size = 11),
                              row = 1, col = 1)
    _note(figure, 'film band drawn at a fixed thickness: the film model resolves the film along the wall, not across it',
          1, 1, colors['textMuted'])

    # -- Effectiveness -- #
    for trace in _filled(x, effectiveness, colors['cyan']):
        figure.add_trace(trace, row = 2, col = 1)
    figure.add_trace(_line(x, effectiveness, 'Effectiveness', colors['cyan'], 1.7, unit = '', valueFormat = '.3f',
                           showlegend = False), row = 2, col = 1)
    figure.add_trace(_level(x, 0.3, 'Effectiveness 0.3', colors['textMuted'], showlegend = False), row = 2, col = 1)

    # -- What the wall is driven by, with and without the film -- #
    figure.add_trace(_line(x, recovery, 'Without the film', colors['red'], 1.4, legend = 'legend2'), row = 2, col = 2)
    figure.add_trace(_line(x, driving, 'Under the film', colors['cyan'], 1.7, legend = 'legend2'), row = 2, col = 2)
    results = thermalPlots.thermalResults(nozzle)
    if results is not None:
        figure.add_trace(_line(results['xHotWall3D'], results['wallTemperature'], 'Hot wall', colors['accent'], 1.4,
                               legend = 'legend2'), row = 2, col = 2)

    if hasEntrainment:
        figure.add_trace(_line(x, entrained, 'Entrained over film flow', colors['purple'], 1.6, unit = '',
                               valueFormat = '.3f', showlegend = False), row = 2, col = 3)
        figure.add_trace(_line(x, mixture, 'Wall mixture ratio', colors['green'], 1.4, unit = '', valueFormat = '.3f',
                               showlegend = False), row = 2, col = 3, secondary_y = True)

    model = {'hatchPapell': 'Hatch and Papell', 'sp8124Entrainment': 'SP-8124 entrainment'}.get(
        getattr(nozzle, 'filmCoolingModel', ''), str(getattr(nozzle, 'filmCoolingModel', '')))
    coolant = getattr(nozzle, 'filmCoolant', None) or 'coolant'
    flow = float(getattr(nozzle, 'filmMassFlow', 0.0) or 0.0)
    slotHeight = 1e3 * float(getattr(nozzle, 'filmSlotHeight', 0.0) or 0.0)
    _style(figure, colors, f'{coolant} film, {flow:.3f} kg/s through a {slotHeight:.1f} mm slot ({model}): '
                           f'useful for {1e3 * survival:.0f} mm')
    _equalAspect(figure, 1, 1, (float(np.min(x)), float(np.max(x))), (0.0, top))
    figure.update_yaxes(title_text = 'Radius [m]', row = 1, col = 1)
    figure.update_yaxes(title_text = 'Film effectiveness [-]', range = [0.0, 1.05], row = 2, col = 1)
    figure.update_yaxes(title_text = 'Temperature [K]', row = 2, col = 2)
    if hasEntrainment:
        figure.update_yaxes(title_text = 'Entrained over film flow [-]', title_font_color = colors['purple'],
                            tickfont_color = colors['purple'], row = 2, col = 3, secondary_y = False)
        figure.update_yaxes(title_text = 'Wall mixture ratio [-]', title_font_color = colors['green'],
                            tickfont_color = colors['green'], showgrid = False, row = 2, col = 3, secondary_y = True)
    for col in range(1, columns + 1):
        figure.update_xaxes(title_text = 'Nozzle axis [m]', row = 2, col = col)
        if col > 1:
            figure.update_xaxes(matches = _axisName(figure, 2, 1, 'x'), row = 2, col = col)
    _legendIn(figure, 'legend2', 2, 2, 'lower right', colors)
    figure.update_layout(margin = dict(r = 90))
    _throat(figure, nozzle, [(1, 1)] + [(2, col) for col in range(1, columns + 1)], colors)

    return figure

#--------------------------------------------------------------------------------------------------------------------------#
# -- The radiative extension -- #
#--------------------------------------------------------------------------------------------------------------------------#

def extension(figures, nozzle):

    '''

    The radiation-cooled extension: the whole wall colored by its temperature, the jacket's and the
    extension's on one scale with the extension material's limit marked; the extension's wall
    against its radiative equilibrium and its limit; and the heat balance that sets it.

    '''

    if not thermalPlots.extensionSolved(nozzle):
        return None
    colors, palette = _colors(figures), figures.figurePalette

    solution = nozzle.radiativeExtensionSolution
    x, r = np.asarray(solution.axialPosition, dtype = float), np.asarray(solution.radius, dtype = float)
    wall = np.asarray(solution.extensionWallTemperature, dtype = float)
    limit = solution.extensionTemperatureLimit
    residual = float(solution.extensionEnergyBalanceResidual)

    figure = make_subplots(rows = 2, cols = 2, row_heights = [0.52, 0.48], vertical_spacing = 0.14,
                           horizontal_spacing = 0.09, specs = [[{'colspan': 2}, None], [{}, {}]],
                           subplot_titles = ('', '', f'Energy balance closes to {residual:.1e}'))

    # -- The whole wall on one temperature scale -- #
    results = thermalPlots.thermalResults(nozzle)
    # The jacket's metal, as the shell's is: under a barrier coating the gas-side surface runs far
    # hotter and would set the scale for a temperature no limit applies to
    pieces = [wall] + ([thermalPlots._metalWall(results)] if results is not None else [])
    low = min(float(np.min(piece)) for piece in pieces)
    top = max(float(np.max(piece)) for piece in pieces)
    if limit:
        top = max(top, float(limit))
    scale = palette.plotlyColorscale('temperature')
    wallX = _contourUnder(figure, nozzle, colors, 1, 1)
    bar = _colorbar(colors, 'Wall temperature [K]: jacket and extension', x = 1.0, xanchor = 'left',
                    y = 0.5 * sum(figure.get_subplot(1, 1).yaxis.domain), yanchor = 'middle', len = 0.5,
                    **_scaleWithLimit(low, top, limit, colors))
    for trace in _band(x, r, wall, scale, low, top, 8.0, 'Extension wall', bar):
        figure.add_trace(trace, row = 1, col = 1)
    if results is not None:
        for trace in _band(results['xHotWall3D'], results['rHotWall3D'], thermalPlots._metalWall(results), scale, low, top,
                           8.0, 'Jacket hot wall'):
            figure.add_trace(trace, row = 1, col = 1)

    material = getattr(nozzle, 'extensionMaterial', None) or 'shell'
    atmosphere = str(getattr(nozzle, 'extensionAtmosphere', '') or '').replace('oxidisingCoated', 'oxidising, coated')
    heading = f'{material} extension in an {atmosphere} atmosphere: peak wall {float(solution.extensionPeakWallTemperature):.0f} K'
    if limit:
        margin = float(solution.extensionTemperatureMargin)
        heading += f', {abs(margin):.0f} K {"under" if margin >= 0 else "over"} its {float(limit):.0f} K limit'

    # -- The extension's wall against its equilibrium and its limit -- #
    figure.add_trace(_line(x, wall, 'Wall', colors['accent'], 1.8), row = 2, col = 1)
    figure.add_trace(_line(x, solution.extensionEquilibriumTemperature, 'Radiative equilibrium', colors['blue'], 1.2,
                           'dash'), row = 2, col = 1)
    if limit:
        figure.add_trace(_level(x, float(limit), f'{material} limit', colors['red']), row = 2, col = 1)
    _legendIn(figure, 'legend', 2, 1, 'upper right', colors)

    # -- The heat balance: what the gas puts in, what the shell radiates and conducts away -- #
    for name, label, color, sign in (('extensionConvectiveFlux', 'Convection in', 'red', 1.0),
                                     ('extensionGasRadiativeFlux', 'Gas radiation in', 'purple', 1.0),
                                     ('extensionEmittedFlux', 'Emitted out', 'cyan', -1.0),
                                     ('extensionConductionFlux', 'Conducted along', 'orange', 1.0)):
        values = np.asarray(getattr(solution, name), dtype = float)
        if values.size == x.size and np.any(values):
            figure.add_trace(_line(x, sign * values / 1e3, label, colors[color], 1.4, unit = 'kW/m²', valueFormat = '.1f',
                                   legend = 'legend2'), row = 2, col = 2)
    figure.add_hline(y = 0.0, line = dict(color = colors['textDim'], width = 1), row = 2, col = 2)
    _legendIn(figure, 'legend2', 2, 2, 'upper right', colors)

    _style(figure, colors, heading)
    start = float(np.min(wallX)) if wallX.size else float(np.min(x))
    _equalAspect(figure, 1, 1, (start, float(np.max(x))), (0.0, 1.2 * float(np.max(r))))
    figure.update_yaxes(title_text = 'Radius [m]', row = 1, col = 1)
    figure.update_yaxes(title_text = 'Temperature [K]', row = 2, col = 1)
    figure.update_yaxes(title_text = 'Heat flux [kW/m²]', row = 2, col = 2)
    figure.update_xaxes(title_text = 'Nozzle axis [m]', row = 2, col = 1)
    figure.update_xaxes(title_text = 'Nozzle axis [m]', matches = _axisName(figure, 2, 1, 'x'), row = 2, col = 2)
    figure.update_layout(margin = dict(r = 90))

    return figure

#--------------------------------------------------------------------------------------------------------------------------#
# -- The coolant circuit -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _arrows(figure: go.Figure, x, r, color: str, forward: bool, count: int = 4) -> None:

    '''Arrowheads along a line, pointing the way the coolant runs.'''

    x, r = np.asarray(x, dtype = float), np.asarray(r, dtype = float)
    if x.size < 3:
        return
    for k in np.linspace(0, x.size - 2, count + 2)[1:-1].astype(int):
        start, end = (k, k + 1) if forward else (k + 1, k)
        figure.add_annotation(x = float(x[end]), y = float(r[end]), ax = float(x[start]), ay = float(r[start]),
                              axref = 'x', ayref = 'y', text = '', showarrow = True, arrowhead = 2, arrowsize = 1.3,
                              arrowwidth = 1.6, arrowcolor = color, standoff = 0)

def _marker(x: float, r: float, symbol: str, color: str, name: str, size: float = 11, showlegend: bool = True,
            open: bool = False) -> go.Scatter:

    '''One marker with a legend entry: a manifold, the turnaround ring, a film slot.'''

    marker = dict(symbol = symbol, size = size, color = color)
    if open:
        # An open symbol strokes in the marker color, at the line width
        marker['line'] = dict(color = color, width = 2.0)

    return go.Scatter(x = [float(x)], y = [float(r)], mode = 'markers', marker = marker, name = name, showlegend = showlegend,
                      hovertemplate = f'{name}<br>x %{{x:.4f}} m<extra></extra>')

def _path(x, r, name: str, color: str, width: float = 2.2, dash: str = None) -> go.Scatter:

    '''A line on the half section, its hover naming it and the axial position.'''

    return go.Scatter(x = np.asarray(x, dtype = float), y = np.asarray(r, dtype = float), mode = 'lines', name = name,
                      line = dict(color = color, width = width, dash = dash),
                      hovertemplate = f'{name}<br>x %{{x:.4f}} m<extra></extra>')

def circuit(figures, nozzle):

    '''

    The nozzle's half section with the coolant's paths drawn on it: each family of the chamber jacket
    with the way it runs, its manifolds, turnaround and split, the extension's own circuit and its
    outlet, the film slots and the radiation-cooled shell.

    '''

    results = thermalPlots.thermalResults(nozzle)
    if results is None:
        return None
    colors = _colors(figures)

    figure = go.Figure()
    xWall, rWall = np.asarray(nozzle.xNozzleWall, dtype = float), np.asarray(nozzle.rNozzleWall, dtype = float)
    figure.add_trace(_path(xWall, rWall, 'Hot wall', colors['textDim'], 1.2))
    step = 0.03 * float(np.max(rWall))

    x, r = np.asarray(results['xHotWall3D'], dtype = float), np.asarray(results['rHotWall3D'], dtype = float)
    solution = getattr(nozzle, 'coolantCircuitSolution', None)
    if solution is None:
        coflow = getattr(nozzle, 'jacketFlowDirection', 'counterflow') == 'coflow'
        figure.add_trace(_path(x, r + step, 'Chamber jacket', colors['accent']))
        _arrows(figure, x, r + step, colors['accent'], forward = coflow)
        inlet, outlet = (0, -1) if coflow else (-1, 0)
        figure.add_trace(_marker(x[inlet], r[inlet] + step, 'triangle-down', colors['accent'], 'Inlet manifold'))
        figure.add_trace(_marker(x[outlet], r[outlet] + step, 'triangle-up', colors['accent'], 'Outlet manifold'))
    else:
        down = np.asarray(solution.down.stations)
        figure.add_trace(_path(x, r + step, f'Up family, {solution.up.channelCount} channels', colors['accent']))
        _arrows(figure, x, r + step, colors['accent'], forward = False)
        figure.add_trace(_path(x[down], r[down] + 2 * step, f'Down family, {solution.down.channelCount} channels',
                               colors['blue']))
        _arrows(figure, x[down], r[down] + 2 * step, colors['blue'], forward = True)
        figure.add_trace(_marker(x[down[0]], r[down[0]] + 2 * step, 'triangle-down', colors['blue'], 'Inlet manifold'))
        figure.add_trace(_marker(x[-1], r[-1] + 1.5 * step, 'circle-open', colors['purple'], 'Turnaround ring', size = 14,
                                 open = True))
        figure.add_trace(_marker(x[0], r[0] + step, 'triangle-up', colors['accent'], 'Outlet manifold'))

    blend = getattr(nozzle, 'channelSplitBlend', None)
    xInterfaced = getattr(nozzle, 'xRegenNozzleInterfaced', None)
    if blend is not None and xInterfaced is not None:
        inside = np.flatnonzero((np.asarray(blend) > 0.0) & (np.asarray(blend) < 1.0))
        if inside.size:
            figure.add_vrect(x0 = float(np.asarray(xInterfaced)[inside[0]]), x1 = float(np.asarray(xInterfaced)[inside[-1]]),
                             fillcolor = colors['purple'], opacity = 0.18, line_width = 0, layer = 'below',
                             showlegend = True, name = 'Channel split')

    extensionCircuit = getattr(nozzle, 'extensionCircuitSolution', None)
    xExtension = getattr(nozzle, 'xExtension', None)
    if extensionCircuit is not None and xExtension is not None:
        stations = np.asarray(extensionCircuit.stations)
        xe = np.asarray(xExtension, dtype = float)[stations]
        re = np.asarray(nozzle.rExtension, dtype = float)[stations]
        figure.add_trace(_path(xe, re + step, f'Extension circuit, outlet {extensionCircuit.outlet}', colors['purple']))
        _arrows(figure, xe, re + step, colors['purple'], forward = extensionCircuit.direction == 'coflow')
    shell = getattr(nozzle, 'extensionWallTemperature', None)
    if shell is not None and xExtension is not None:
        start = len(xExtension) - len(shell)
        figure.add_trace(_path(np.asarray(xExtension, dtype = float)[start:],
                               np.asarray(nozzle.rExtension, dtype = float)[start:] + step, 'Radiation-cooled shell',
                               colors['textMuted'], 1.6, 'dash'))

    # Slots a few stations apart would print their names over each other, so each sits a line lower
    # than the one before
    layers = getattr(getattr(nozzle, 'extensionFilmSolution', None), 'layers', None)
    if layers:
        filmSolution = nozzle.extensionFilmSolution
        names = {'turbineExhaust': 'turbine exhaust', 'extensionCircuitOutlet': 'circuit outlet',
                 'chamber': 'chamber film'}
        for number, layer in enumerate(layers):
            xf = float(filmSolution.x[layer.injectionIndex])
            rf = float(np.interp(xf, xWall, rWall))
            source = layer.name.split(' slot')[0]
            figure.add_trace(_marker(xf, rf - step, 'triangle-right', colors['cyan'], f'Film slot: {layer.name}',
                                     showlegend = False))
            figure.add_annotation(x = xf, y = rf - step, text = names.get(source, source), showarrow = False,
                                  xanchor = 'left', yanchor = 'top', xshift = 4, yshift = -8 - 13 * number,
                                  font = dict(color = colors['cyan'], size = 11))

    title = 'Coolant circuit: ' + thermalPlots.circuitNames.get(getattr(nozzle, 'coolantCircuit', None), 'A, single pass')
    if extensionCircuit is not None:
        title += ', with an extension circuit (D)'
    _style(figure, colors, title, hovermode = 'closest')
    figure.update_xaxes(title_text = 'Nozzle axis [m]')
    figure.update_yaxes(title_text = 'Radius [m]', scaleanchor = 'x', scaleratio = 1)
    _legendIn(figure, 'legend', None, None, 'upper left', colors)

    return figure

def passes(figures, nozzle):

    '''Each pass's coolant and hot wall: the chamber jacket's two families and the extension circuit.'''

    solution = getattr(nozzle, 'coolantCircuitSolution', None)
    extensionCircuit = getattr(nozzle, 'extensionCircuitSolution', None)
    if solution is None and extensionCircuit is None:
        return None
    colors = _colors(figures)

    figure = make_subplots(rows = 2, cols = 1, shared_xaxes = True, vertical_spacing = 0.07)
    if solution is not None:
        for passSolution, color in ((solution.down, colors['blue']), (solution.up, colors['accent'])):
            x = passSolution.results['xHotWall3D']
            figure.add_trace(_line(x, passSolution.results['temperature'], f'{passSolution.name} pass', color, 1.8),
                             row = 1, col = 1)
            figure.add_trace(_line(x, thermalPlots._metalWall(passSolution.results), f'{passSolution.name} family', color,
                                   1.6, legend = 'legend2'), row = 2, col = 1)
    if extensionCircuit is not None and extensionCircuit.circuit is None:
        x = np.asarray(nozzle.xExtension, dtype = float)[np.asarray(extensionCircuit.stations)]
        figure.add_trace(_line(x, extensionCircuit.sizing.channelThermalResults['temperature'], 'extension circuit',
                               colors['purple'], 1.8), row = 1, col = 1)
        figure.add_trace(_line(x, extensionCircuit.metalWallTemperature, 'extension circuit', colors['purple'], 1.6,
                               legend = 'legend2'), row = 2, col = 1)
    elif extensionCircuit is not None:
        # Two passes on the extension: the down pass dashed, the up pass solid
        for passSolution, dash in ((extensionCircuit.circuit.down, 'dash'), (extensionCircuit.circuit.up, None)):
            x = passSolution.results['xHotWall3D']
            figure.add_trace(_line(x, passSolution.results['temperature'], f'extension {passSolution.name} pass',
                                   colors['purple'], 1.8, dash), row = 1, col = 1)
            figure.add_trace(_line(x, thermalPlots._metalWall(passSolution.results), f'extension {passSolution.name} family',
                                   colors['purple'], 1.6, dash, legend = 'legend2'), row = 2, col = 1)
    limit = getattr(nozzle, 'maxWallTemperature', None)
    if limit:
        span = [trace.x for trace in figure.data if trace.yaxis == 'y2']
        figure.add_trace(_level(np.concatenate(span), float(limit), f'Wall limit {float(limit):.0f} K', colors['red'],
                                legend = 'legend2'), row = 2, col = 1)

    _style(figure, colors, 'Coolant and hot wall of each pass')
    figure.update_yaxes(title_text = 'Coolant temperature [K]', row = 1, col = 1)
    figure.update_yaxes(title_text = 'Hot wall temperature [K]', row = 2, col = 1)
    figure.update_xaxes(title_text = 'Nozzle axis [m]', row = 2, col = 1)
    _legendIn(figure, 'legend', 1, 1, 'upper right', colors)
    _legendIn(figure, 'legend2', 2, 1, 'upper right', colors)
    _throat(figure, nozzle, ((1, 1), (2, 1)), colors)

    return figure

# View key -> builder, the keys of novaGui.tabs.viewTab.views
builders = {
    'circuit':            circuit,
    'passes':             passes,
    'wallMap':            wallMap,
    'jacketTemperatures': jacketTemperatures,
    'coolantFlow':        coolantFlow,
    'coolantProperties':  coolantProperties,
    'heatFlux':           heatFlux,
    'film':               film,
    'extension':          extension,
}
