
# -- Renderer-Independent Figure Data -- #

'''

Every plotting concern outside the GUI, in one place: what a figure shows, and how both
backends draw it.

NOVA draws every result figure twice. Matplotlib renders the PNGs written beside a run, since
those are meant to be viewed as a static image or embedded in a document. Plotly renders the
interactive HTML companion opened in a browser, since it pans, zooms and reads values off a mesh
far better than a static image can. Both are required dependencies.

Rather than write each figure twice, the extractors pull the arrays and labels off a Nozzle into
a plain dataclass that neither library appears in, and each backend's renderers draw from that
one description. A figure is described once, and the two renderings cannot drift. The GUI is the
one exception: its panes are embedded in a live Tk canvas rather than saved or exported, which
`novaGui.plotting` draws with its own renderers against these same descriptions, styled from the
GUI's own theme rather than this module's.

Every figure a run can produce is built here, including the 3D assembly views that have no
Matplotlib counterpart: the volute assembly, the channel mesh and jacket, and the regen heat
transfer dashboard. Those skip the two-stage extractor-then-renderer split, since there is only
one renderer to keep in step with, and build the plotly figure directly off a Nozzle or a
solve's own state object. The modules that generate the geometry those figures describe call in
here rather than building a figure themselves, so what a module computes and what it draws stay
in two different files.

Author: Sean Bowman
Date:   08/28/2026

'''

import os
from dataclasses import dataclass, field

import numpy as np
import matplotlib

def headlessPlots() -> bool:

    '''

    Whether figures should be written and left alone rather than put in front of somebody.

    A design run draws a lot of figures, and every one of them opens a window or a browser tab
    that has to be closed by hand before the next run. That is fine once and intolerable in a
    loop, which is what running tests or iterating on a feature is. Setting the environment
    variable `NOVA_HEADLESS` suppresses the display of all of them without suppressing the
    figures themselves: matplotlib windows never open, plotly writes its HTML and does not
    launch a browser, and every file that would have been produced is still produced.

    This is deliberately not a configuration field. It is a property of where NOVA is running
    rather than of the engine being designed, so it belongs to the shell or the harness that
    started the run, not to the JSON that describes the nozzle.

    Returns:
    --------
    bool
        True when figures should not be displayed.

    '''

    return os.environ.get('NOVA_HEADLESS', '').strip().lower() not in ('', '0', 'false', 'off')

# Selected before pyplot is imported, so the choice sticks rather than having to be forced back
# afterwards. This covers matplotlib only; a plotly figure ignores the matplotlib backend and
# opens a browser tab of its own, which is what `showFigure` below is for.
if headlessPlots():
    matplotlib.use('Agg', force = True)

import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
import plotly.colors
import plotly.graph_objects as go
from plotly.express.colors import sample_colorscale
from plotly.offline import plot as _writePlotlyFigure

from .geometryTools import DCM, revolveContour

def showFigure(figure) -> None:

    '''

    Put a figure in front of somebody, unless NOVA is running headless.

    Every display of a figure goes through here rather than calling `.show()` directly, and
    `tests/testPlotSuppression.py` fails the build if a new one does not. That is worth a test
    because the failure is silent and cumulative: a call that opens a browser tab costs nothing
    the first time and buries a developer on the twentieth, and there is no error to notice.

    A plotly figure is the case that matters. It ignores the matplotlib backend entirely, and its
    browser renderer starts a local web server and opens a tab against it, which is why
    suppressing it is a separate problem from selecting a non-interactive backend.

    Parameters:
    -----------
    figure : plotly.graph_objects.Figure | matplotlib.figure.Figure
        Anything with a `show` method.

    Returns:
    --------
    None

    '''

    if headlessPlots():
        return

    figure.show()

# Palette shared with the GUI theme. Duplicated rather than imported because this module belongs
# to the solver package and must not depend on the front end; both derive from the same style
# guide, so a change to one belongs in the other.
palette = {
    'background': '#1a1e2a',
    'surface':    '#22273a',
    'border':     '#3a4055',
    'text':       '#d8e0ec',
    'muted':      '#8a95a8',
    'accent':     '#E0975A',
    'green':      '#86C06C',
    'blue':       '#7baee8',
}

# Palette for the Matplotlib PNGs, kept separate from the plotly palette above since the two
# renderings are tuned independently against their own backgrounds.
mplPalette = {
    'background': '#1a1e2a',
    'panel':      '#222735',
    'copper':     '#E0975A',
    'green':      '#86C06C',
    'ink':        '#E8E6E1',
    'muted':      '#8B93A7',
    'blue':       '#6BA3D6',
}

#--------------------------------------------------------------------------------------------------------------------------#
# -- Figure descriptions -- #
#--------------------------------------------------------------------------------------------------------------------------#

@dataclass
class ContourFigure:

    '''

    Axisymmetric wall contour, mirrored about the axis.

    '''

    x: np.ndarray                                                        # [m]
    r: np.ndarray                                                        # [m]
    xRegen: np.ndarray = field(default_factory = lambda: np.array([]))   # [m]
    rRegen: np.ndarray = field(default_factory = lambda: np.array([]))   # [m]
    throatX: float = 0.0                                                 # [m]
    throatRadius: float = 0.0                                            # [m]
    exitRadius: float = 0.0                                              # [m]
    length: float = 0.0                                                  # [m]
    title: str = 'Nozzle contour'

@dataclass
class NearWallFigure:

    '''

    Near-wall exhaust state along the axis: static temperature, static pressure, Mach number.

    '''

    axis: np.ndarray                               # [m]
    temperature: np.ndarray                        # [K]
    pressure: np.ndarray                           # [Pa]
    mach: np.ndarray                               # [-]
    velocity: np.ndarray = field(default_factory = lambda: np.array([]))   # [m/s]
    title: str = 'Near-wall exhaust state'

@dataclass
class RevolvedFigure:

    '''

    Surface of revolution of the wall contour, with cooling channel centerlines when a jacket
    was generated.

    '''

    x: np.ndarray                                                          # [m]
    r: np.ndarray                                                          # [m]
    sweepDeg: float = 300.0                                                # [deg]
    channelX: np.ndarray = field(default_factory = lambda: np.array([]))   # [m]
    channelY: np.ndarray = field(default_factory = lambda: np.array([]))   # [m]
    channelZ: np.ndarray = field(default_factory = lambda: np.array([]))   # [m]
    title: str = 'Revolved contour'

@dataclass
class FieldFigure:

    '''

    A scalar field over the method-of-characteristics mesh.

    The mesh is curvilinear and arrives as a list of 2-D blocks with NaN padding, which is why
    the values travel alongside the coordinates rather than on a regular grid.

    '''

    xBlocks: list                                  # [m], list of 2-D arrays
    rBlocks: list                                  # [m]
    valueBlocks: list                              # field units
    wallX: np.ndarray                              # [m]
    wallR: np.ndarray                              # [m]
    label: str = ''
    colorscale: str = 'Viridis'
    title: str = ''

@dataclass
class PlumeFigure:

    '''

    Exhaust plume structure drawn against the nozzle contour.

    The boundary, cell spacing and Mach disk are correlations; the plume interior is not
    solved, so nothing here is a field. `notes` carries the caveats that belong beside the
    numbers.

    '''

    wallX: np.ndarray                              # [m], nozzle contour
    wallR: np.ndarray                              # [m]
    boundaryX: np.ndarray                          # [m], plume boundary
    boundaryR: np.ndarray                          # [m]
    cellX: np.ndarray                              # [m], shock cell node positions
    machDiskX: float = 0.0                         # [m]
    machDiskDiameter: float = 0.0                  # [m]
    machDiskPresent: bool = False
    jetType: str = ''
    summary: str = ''
    notes: list = field(default_factory = list)
    title: str = 'Exhaust plume structure'

#--------------------------------------------------------------------------------------------------------------------------#
# -- Extractors -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _asArray(value) -> np.ndarray:

    '''

    Coerce a Nozzle attribute to a float array, tolerating the empty-list placeholders the
    class uses before a stage has run.

    '''

    try:
        return np.asarray(value, dtype = float)
    except (TypeError, ValueError):
        return np.array([])

def contourFigure(nozzle):

    '''

    Wall contour description, or None when no contour has been generated.

    '''

    x = _asArray(getattr(nozzle, 'xNozzleWall', []))
    r = _asArray(getattr(nozzle, 'rNozzleWall', []))
    if x.size == 0 or r.size != x.size:
        return None

    xRegen = _asArray(getattr(nozzle, 'xRegenNozzle', []))
    rRegen = _asArray(getattr(nozzle, 'rRegenNozzle', []))
    if xRegen.size == x.size or rRegen.size != xRegen.size:
        # A regen split spanning the whole contour is not a split worth drawing.
        xRegen = rRegen = np.array([])

    throatIndex = int(np.argmin(r))
    return ContourFigure(
        x = x, r = r, xRegen = xRegen, rRegen = rRegen,
        throatX = float(x[throatIndex]), throatRadius = float(r[throatIndex]),
        exitRadius = float(r[-1]), length = float(x[-1] - x[0]),
    )

def nearWallFigure(nozzle):

    '''

    Near-wall exhaust state description, or None when the flow solve did not run.

    '''

    x = _asArray(getattr(nozzle, 'xNozzleWall', []))
    temperature = _asArray(getattr(nozzle, 'nozzleNearWallTemperature', []))
    pressure = _asArray(getattr(nozzle, 'nozzleNearWallPressure', []))
    mach = _asArray(getattr(nozzle, 'nozzleNearWallMachNumber', []))
    velocity = _asArray(getattr(nozzle, 'nozzleNearWallVelocity', []))
    if x.size == 0 or temperature.size == 0:
        return None

    axis = np.linspace(x[0], x[-1], temperature.size)
    if pressure.size != temperature.size:
        pressure = np.full(temperature.size, np.nan)
    if mach.size != temperature.size:
        mach = np.full(temperature.size, np.nan)
    if velocity.size != temperature.size:
        velocity = np.full(temperature.size, np.nan)
    return NearWallFigure(axis = axis, temperature = temperature, pressure = pressure,
                          mach = mach, velocity = velocity)

def revolvedFigure(nozzle, sweepDeg: float = 300.0):

    '''

    Surface-of-revolution description, or None when no contour has been generated.

    '''

    x = _asArray(getattr(nozzle, 'xNozzleWall', []))
    r = _asArray(getattr(nozzle, 'rNozzleWall', []))
    if x.size == 0 or r.size != x.size:
        return None

    channelX = _asArray(getattr(nozzle, 'xChannelCenterline3D', []))
    channelY = _asArray(getattr(nozzle, 'yChannelCenterline3D', []))
    channelZ = _asArray(getattr(nozzle, 'zChannelCenterline3D', []))
    if not (channelX.size and channelX.shape == channelY.shape == channelZ.shape):
        channelX = channelY = channelZ = np.array([])

    return RevolvedFigure(x = x, r = r, sweepDeg = sweepDeg,
                          channelX = channelX, channelY = channelY, channelZ = channelZ)

def plumeFigure(nozzle):

    '''

    Plume structure description, or None when no plume was computed (no ambient pressure was
    given, or the contour is unavailable).

    '''

    structure = getattr(nozzle, 'nozzlePlumeStructure', None)
    if structure is None:
        return None

    wallX = _asArray(getattr(nozzle, 'xNozzleWall', []))
    wallR = _asArray(getattr(nozzle, 'rNozzleWall', []))

    summary = (f"{structure.jetType}   Pe/Pa {structure.exitPressureRatio:.2f}   "
               f"NPR {structure.nozzlePressureRatio:.1f}   Mj {structure.fullyExpandedMach:.2f}   "
               f"cell {structure.shockCellLength * 1e3:.0f} mm")

    return PlumeFigure(
        wallX = wallX, wallR = wallR,
        boundaryX = structure.boundaryX, boundaryR = structure.boundaryR,
        cellX = structure.cellX,
        machDiskX = structure.machDiskX,
        machDiskDiameter = structure.machDiskDiameter,
        machDiskPresent = structure.machDiskPresent,
        jetType = structure.jetType,
        summary = summary,
        notes = list(structure.notes),
    )

# Quantity key -> (Nozzle attribute, color bar label, plotly colorscale, figure title)
fieldDefinitions = {
    'mach':        ('allMachNumbers',  'Mach number [-]',  'Viridis', 'Mach contours'),
    'pressure':    ('allPressures',    'Pressure [Pa]',    'RdBu_r',  'Pressure contours'),
    'temperature': ('allTemperatures', 'Temperature [K]',  'Plasma',  'Temperature contours'),
}

def fieldFigure(nozzle, quantity: str):

    '''

    Scalar field over the characteristic mesh, or None when the mesh was not retained (a
    conical diverging section never builds one).

    Parameters:
    -----------
    quantity : str
        One of 'mach', 'pressure', 'temperature'

    '''

    if quantity not in fieldDefinitions:
        raise KeyError(f'fieldFigure has no definition for {quantity!r}. '
                       f'Available: {sorted(fieldDefinitions)}')
    attribute, label, colorscale, title = fieldDefinitions[quantity]

    xPoints = getattr(nozzle, 'allXPoints', None)
    rPoints = getattr(nozzle, 'allRPoints', None)
    values = getattr(nozzle, attribute, None)
    if xPoints is None or rPoints is None or values is None:
        return None

    scale = float(getattr(nozzle, 'nozzleScalingFactor', 1.0) or 1.0)
    xBlocks, rBlocks, valueBlocks = [], [], []
    for index in range(min(len(xPoints), len(rPoints), len(values))):
        blockX = np.asarray(xPoints[index], dtype = float) * scale
        blockR = np.asarray(rPoints[index], dtype = float) * scale
        blockValue = np.asarray(values[index], dtype = float)
        if blockX.size and blockX.shape == blockR.shape == blockValue.shape:
            xBlocks.append(blockX)
            rBlocks.append(blockR)
            valueBlocks.append(blockValue)
    if not xBlocks:
        return None

    return FieldFigure(
        xBlocks = xBlocks, rBlocks = rBlocks, valueBlocks = valueBlocks,
        wallX = _asArray(getattr(nozzle, 'xNozzleWall', [])),
        wallR = _asArray(getattr(nozzle, 'rNozzleWall', [])),
        label = label, colorscale = colorscale, title = title,
    )

#--------------------------------------------------------------------------------------------------------------------------#
# -- Plotly renderers -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _baseLayout(title: str, xLabel: str, yLabel: str) -> dict:

    '''

    Dark layout matching the GUI, with the color bar laid horizontally under the plot so a
    wide axisymmetric figure keeps the full figure width.

    '''

    return dict(
        title = dict(text = title, font = dict(color = palette['text'], size = 16)),
        paper_bgcolor = palette['surface'],
        plot_bgcolor = palette['background'],
        font = dict(color = palette['text'], family = 'Segoe UI, Inter, sans-serif'),
        xaxis = dict(title = xLabel, gridcolor = palette['border'], zerolinecolor = palette['border'],
                     linecolor = palette['border']),
        yaxis = dict(title = yLabel, gridcolor = palette['border'], zerolinecolor = palette['border'],
                     linecolor = palette['border']),
        margin = dict(l = 70, r = 30, t = 60, b = 60),
    )

def plotlyContour(data: ContourFigure):

    '''

    Interactive wall contour, or None without plotly.

    '''

    if data is None:
        return None

    figure = go.Figure()
    figure.add_trace(go.Scatter(x = data.x, y = data.r, mode = 'lines', name = 'Wall contour',
                                line = dict(color = palette['accent'], width = 2),
                                hovertemplate = 'x %{x:.4f} m<br>r %{y:.4f} m<extra></extra>'))
    figure.add_trace(go.Scatter(x = data.x, y = -data.r, mode = 'lines', showlegend = False,
                                line = dict(color = palette['accent'], width = 2),
                                hoverinfo = 'skip'))
    if data.xRegen.size:
        figure.add_trace(go.Scatter(x = data.xRegen, y = data.rRegen, mode = 'lines',
                                    name = 'Regen-cooled portion',
                                    line = dict(color = palette['green'], width = 3)))
        figure.add_trace(go.Scatter(x = data.xRegen, y = -data.rRegen, mode = 'lines',
                                    showlegend = False, hoverinfo = 'skip',
                                    line = dict(color = palette['green'], width = 3)))

    figure.add_vline(x = data.throatX, line = dict(color = palette['muted'], width = 1, dash = 'dash'))
    figure.add_annotation(x = data.throatX, y = data.throatRadius,
                          text = f'throat r = {data.throatRadius * 1e3:.1f} mm',
                          showarrow = False, yshift = 18, font = dict(color = palette['muted'], size = 11))
    figure.add_annotation(x = data.x[-1], y = data.exitRadius,
                          text = f'exit r = {data.exitRadius * 1e3:.1f} mm',
                          showarrow = False, yshift = 18, xanchor = 'right',
                          font = dict(color = palette['muted'], size = 11))

    layout = _baseLayout(f'{data.title}   (length {data.length * 1e3:.0f} mm)',
                         'Nozzle axis [m]', 'Radius [m]')
    layout['yaxis']['scaleanchor'] = 'x'
    layout['yaxis']['scaleratio'] = 1
    layout['legend'] = dict(bgcolor = palette['surface'], bordercolor = palette['border'], borderwidth = 1)
    figure.update_layout(**layout)
    return figure

def plotlyNearWall(data: NearWallFigure):

    '''

    Interactive three-panel near-wall state, or None without plotly.

    '''

    if data is None:
        return None

    from plotly.subplots import make_subplots

    figure = make_subplots(rows = 3, cols = 1, shared_xaxes = True, vertical_spacing = 0.05,
                           subplot_titles = ('Static temperature', 'Static pressure', 'Mach number'))
    figure.add_trace(go.Scatter(x = data.axis, y = data.temperature, mode = 'lines', name = 'T',
                                line = dict(color = palette['accent'])), row = 1, col = 1)
    figure.add_trace(go.Scatter(x = data.axis, y = data.pressure / 1e5, mode = 'lines', name = 'P',
                                line = dict(color = palette['blue'])), row = 2, col = 1)
    figure.add_trace(go.Scatter(x = data.axis, y = data.mach, mode = 'lines', name = 'M',
                                line = dict(color = palette['green'])), row = 3, col = 1)

    figure.update_yaxes(title_text = 'T [K]', row = 1, col = 1)
    figure.update_yaxes(title_text = 'P [bar]', row = 2, col = 1)
    figure.update_yaxes(title_text = 'Mach [-]', row = 3, col = 1)
    figure.update_xaxes(title_text = 'Nozzle axis [m]', row = 3, col = 1)
    figure.update_xaxes(gridcolor = palette['border'], linecolor = palette['border'])
    figure.update_yaxes(gridcolor = palette['border'], linecolor = palette['border'])
    figure.update_layout(
        title = dict(text = data.title, font = dict(color = palette['text'], size = 16)),
        paper_bgcolor = palette['surface'], plot_bgcolor = palette['background'],
        font = dict(color = palette['text'], family = 'Segoe UI, Inter, sans-serif'),
        showlegend = False, margin = dict(l = 70, r = 30, t = 70, b = 60), height = 780,
    )
    for annotation in figure.layout.annotations:
        annotation.font.color = palette['text']
    return figure

def plotlyRevolved(data: RevolvedFigure):

    '''

    Interactive surface of revolution, or None without plotly.

    '''

    if data is None:
        return None

    theta = np.linspace(0.0, np.radians(data.sweepDeg), 80)
    thetaGrid, xGrid = np.meshgrid(theta, data.x)
    rGrid = np.tile(data.r.reshape(-1, 1), (1, theta.size))

    figure = go.Figure()
    figure.add_trace(go.Surface(
        x = xGrid, y = rGrid * np.cos(thetaGrid), z = rGrid * np.sin(thetaGrid),
        surfacecolor = rGrid, colorscale = [[0.0, palette['accent']], [1.0, palette['blue']]],
        showscale = False, opacity = 0.85, name = 'Wall',
        hovertemplate = 'x %{x:.3f} m<extra></extra>',
    ))

    if data.channelX.size:
        lines = data.channelX.reshape(data.channelX.shape[0], -1) if data.channelX.ndim > 1 \
            else data.channelX.reshape(1, -1)
        yLines = data.channelY.reshape(lines.shape)
        zLines = data.channelZ.reshape(lines.shape)
        for index in range(lines.shape[0]):
            figure.add_trace(go.Scatter3d(
                x = np.abs(lines[index]), y = yLines[index], z = zLines[index],
                mode = 'lines', line = dict(color = palette['green'], width = 3),
                showlegend = index == 0, name = 'Channel centerlines',
            ))

    figure.update_layout(
        title = dict(text = data.title, font = dict(color = palette['text'], size = 16)),
        paper_bgcolor = palette['surface'],
        font = dict(color = palette['text'], family = 'Segoe UI, Inter, sans-serif'),
        scene = dict(
            xaxis = dict(title = 'Axis [m]', backgroundcolor = palette['background'],
                         gridcolor = palette['border'], color = palette['text']),
            yaxis = dict(title = 'Y [m]', backgroundcolor = palette['background'],
                         gridcolor = palette['border'], color = palette['text']),
            zaxis = dict(title = 'Z [m]', backgroundcolor = palette['background'],
                         gridcolor = palette['border'], color = palette['text']),
            aspectmode = 'data',
        ),
        margin = dict(l = 0, r = 0, t = 60, b = 0),
    )
    return figure

def plotlyField(data: FieldFigure):

    '''

    Interactive field over the characteristic mesh, or None without plotly.

    The mesh is curvilinear, so the field is drawn as a colored point cloud rather than a
    filled contour: plotly's contour trace needs a regular grid, and hovering a point to read
    its exact value is more useful for inspection than banded fill anyway.

    '''

    if data is None:
        return None

    x = np.concatenate([block.ravel() for block in data.xBlocks])
    r = np.concatenate([block.ravel() for block in data.rBlocks])
    values = np.concatenate([block.ravel() for block in data.valueBlocks])

    finite = np.isfinite(x) & np.isfinite(r) & np.isfinite(values)
    x, r, values = x[finite], r[finite], values[finite]
    if x.size == 0:
        return None

    figure = go.Figure()
    for sign in (1.0, -1.0):
        figure.add_trace(go.Scattergl(
            x = x, y = sign * r, mode = 'markers',
            marker = dict(size = 3, color = values, colorscale = data.colorscale,
                          showscale = sign > 0,
                          colorbar = dict(title = dict(text = data.label, side = 'bottom'),
                                          orientation = 'h', y = -0.22, thickness = 14,
                                          outlinecolor = palette['border'])),
            hovertemplate = 'x %{x:.4f} m<br>r %{y:.4f} m<br>' + data.label
                            + ' %{marker.color:.4g}<extra></extra>',
            showlegend = False,
        ))

    if data.wallX.size:
        for sign in (1.0, -1.0):
            figure.add_trace(go.Scatter(x = data.wallX, y = sign * data.wallR, mode = 'lines',
                                        line = dict(color = palette['text'], width = 2),
                                        hoverinfo = 'skip', showlegend = False))

    layout = _baseLayout(data.title, 'Nozzle axis [m]', 'Nozzle radius [m]')
    layout['yaxis']['scaleanchor'] = 'x'
    layout['yaxis']['scaleratio'] = 1
    layout['margin']['b'] = 110
    figure.update_layout(**layout)
    return figure

def plotlyPlume(data):

    '''

    Interactive plume structure, or None without plotly.

    '''

    if data is None:
        return None

    figure = go.Figure()

    if data.wallX.size:
        for sign in (1.0, -1.0):
            figure.add_trace(go.Scatter(x = data.wallX, y = sign * data.wallR, mode = 'lines',
                                        line = dict(color = palette['accent'], width = 2),
                                        name = 'Nozzle wall', showlegend = sign > 0,
                                        hoverinfo = 'skip'))

    for sign in (1.0, -1.0):
        figure.add_trace(go.Scatter(
            x = data.boundaryX, y = sign * data.boundaryR, mode = 'lines',
            line = dict(color = palette['blue'], width = 2, dash = 'dot'),
            name = 'Plume boundary', showlegend = sign > 0,
            hovertemplate = 'x %{x:.3f} m<br>r %{y:.3f} m<extra></extra>'))

    for index, cellPosition in enumerate(np.asarray(data.cellX, dtype = float)):
        figure.add_vline(x = float(cellPosition),
                         line = dict(color = palette['muted'], width = 1, dash = 'dash'),
                         annotation_text = 'shock cells' if index == 0 else None,
                         annotation_font = dict(color = palette['muted'], size = 10))

    if data.machDiskPresent and data.machDiskDiameter > 0.0:
        halfHeight = data.machDiskDiameter / 2.0
        figure.add_trace(go.Scatter(
            x = [data.machDiskX, data.machDiskX], y = [-halfHeight, halfHeight],
            mode = 'lines', line = dict(color = palette['green'], width = 6),
            name = f'Mach disk ({data.machDiskDiameter * 1e3:.0f} mm)',
            hovertemplate = 'Mach disk<br>x %{x:.3f} m<extra></extra>'))

    layout = _baseLayout(f'{data.title}   --   {data.summary}', 'Nozzle axis [m]', 'Radius [m]')
    layout['yaxis']['scaleanchor'] = 'x'
    layout['yaxis']['scaleratio'] = 1
    layout['legend'] = dict(bgcolor = palette['surface'], bordercolor = palette['border'], borderwidth = 1)
    figure.update_layout(**layout)

    if data.notes:
        figure.add_annotation(
            text = '<br>'.join(f'- {note}' for note in data.notes),
            xref = 'paper', yref = 'paper', x = 0.0, y = -0.30, showarrow = False,
            align = 'left', xanchor = 'left', font = dict(color = palette['muted'], size = 10))
        figure.update_layout(margin = dict(l = 70, r = 30, t = 60, b = 190))

    return figure

#--------------------------------------------------------------------------------------------------------------------------#
# -- Matplotlib renderers -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _applyMplStyle() -> None:

    '''Themed rcParams for every Matplotlib figure this module draws.'''

    plt.rcParams.update({
        'figure.facecolor': mplPalette['background'], 'axes.facecolor': mplPalette['panel'],
        'savefig.facecolor': mplPalette['background'], 'text.color': mplPalette['ink'],
        'axes.labelcolor': mplPalette['ink'], 'axes.edgecolor': mplPalette['muted'],
        'xtick.color': mplPalette['muted'], 'ytick.color': mplPalette['muted'],
        'grid.color': '#333A4D', 'axes.grid': True, 'grid.alpha': 0.4, 'font.size': 9,
        'axes.titlesize': 11, 'axes.titleweight': 'bold', 'legend.framealpha': 0.0,
    })

def drawContourFigure(nozzle):

    '''

    Wall contour with the generated combustion chamber called out.

    Returns:
    --------
    matplotlib.figure.Figure or None
        None when the run has no contour to draw.

    '''

    data = contourFigure(nozzle)
    if data is None:
        return None

    _applyMplStyle()
    figure, axes = plt.subplots(figsize = (11, 4.2))
    x, r = np.asarray(data.x) * 1e3, np.asarray(data.r) * 1e3
    axes.plot(x, r, color = mplPalette['copper'], lw = 1.8)
    axes.plot(x, -r, color = mplPalette['copper'], lw = 1.8)
    axes.fill_between(x, r, -r, color = mplPalette['copper'], alpha = 0.08)

    if len(data.xRegen):
        xRegen, rRegen = np.asarray(data.xRegen) * 1e3, np.asarray(data.rRegen) * 1e3
        axes.plot(xRegen, rRegen, color = mplPalette['green'], lw = 1.2, label = 'regen jacket')
        axes.plot(xRegen, -rRegen, color = mplPalette['green'], lw = 1.2)

    axes.axvline(data.throatX * 1e3, color = mplPalette['muted'], ls = '--', lw = 0.9)
    axes.annotate(f'throat  r = {data.throatRadius * 1e3:.1f} mm',
                  (data.throatX * 1e3, 0.0), textcoords = 'offset points',
                  xytext = (6, 6), color = mplPalette['muted'], fontsize = 8)

    chamberDiameter = getattr(nozzle, 'chamberDiameter', None)
    if chamberDiameter:
        axes.annotate(f'chamber D = {chamberDiameter * 1e3:.0f} mm',
                      (x[0], chamberDiameter * 0.5e3), textcoords = 'offset points',
                      xytext = (8, 6), color = mplPalette['blue'], fontsize = 8)

    axes.set_xlabel('Axial station [mm]')
    axes.set_ylabel('Radius [mm]')
    axes.set_title('Nozzle and chamber contour')
    axes.set_aspect('equal', adjustable = 'box')
    return figure

def drawNearWallFigure(nozzle):

    '''

    Near-wall exhaust state along the axis: velocity, static temperature, static pressure and
    Mach number.

    Returns:
    --------
    matplotlib.figure.Figure or None
        None when the flow solve did not run.

    '''

    data = nearWallFigure(nozzle)
    if data is None:
        return None

    _applyMplStyle()
    figure, axesList = plt.subplots(4, 1, figsize = (9, 9), sharex = True)
    axis = np.asarray(data.axis) * 1e3

    panels = ((axesList[0], data.velocity, 'Velocity [m/s]', mplPalette['blue'], 1.0),
              (axesList[1], data.temperature, 'Static temperature [K]', mplPalette['copper'], 1.0),
              (axesList[2], data.pressure, 'Static pressure [MPa]', mplPalette['green'], 1e-6),
              (axesList[3], data.mach, 'Mach number [-]', mplPalette['blue'], 1.0))
    for axes, values, label, color, scale in panels:
        axes.plot(axis, np.asarray(values) * scale, color = color, lw = 1.6)
        axes.set_ylabel(label)

    axesList[0].set_title(data.title)
    axesList[-1].set_xlabel('Axial station [mm]')
    return figure

def drawFieldFigure(nozzle, quantity: str):

    '''

    Method-of-characteristics field over the curvilinear mesh, one quantity per call.

    Parameters:
    -----------
    quantity : str
        One of 'mach', 'pressure', 'temperature'.

    Returns:
    --------
    matplotlib.figure.Figure or None
        None when the run built no characteristics mesh (a conical diverging section never
        builds one).

    '''

    data = fieldFigure(nozzle, quantity)
    if data is None:
        return None

    _applyMplStyle()
    figure, axes = plt.subplots(figsize = (11, 4.6))

    # The mesh is curvilinear and padded with NaN, so the field is drawn from its finite nodes
    # directly rather than as a structured grid.
    xs, rs, vs = [], [], []
    for xBlock, rBlock, valueBlock in zip(data.xBlocks, data.rBlocks, data.valueBlocks):
        xBlock = np.asarray(xBlock, dtype = float).ravel()
        rBlock = np.asarray(rBlock, dtype = float).ravel()
        valueBlock = np.asarray(valueBlock, dtype = float).ravel()
        keep = np.isfinite(xBlock) & np.isfinite(rBlock) & np.isfinite(valueBlock)
        xs.append(xBlock[keep])
        rs.append(rBlock[keep])
        vs.append(valueBlock[keep])

    scale = 1e-6 if quantity == 'pressure' else 1.0
    xs = np.concatenate(xs) * 1e3
    rs = np.concatenate(rs) * 1e3
    vs = np.concatenate(vs) * scale

    mesh = axes.tricontourf(np.concatenate([xs, xs]), np.concatenate([rs, -rs]),
                            np.concatenate([vs, vs]), levels = 80, cmap = 'viridis')
    wallX, wallR = np.asarray(data.wallX) * 1e3, np.asarray(data.wallR) * 1e3
    axes.plot(wallX, wallR, color = mplPalette['copper'], lw = 1.4)
    axes.plot(wallX, -wallR, color = mplPalette['copper'], lw = 1.4)
    # The contour is a truncated ideal nozzle, so the characteristics mesh extends past the
    # delivered wall to the full ideal exit. Clip to the wall that is actually built.
    axes.set_xlim(wallX.min(), wallX.max())
    axes.set_ylim(-1.08 * abs(wallR).max(), 1.08 * abs(wallR).max())
    axes.set_xlabel('Axial station [mm]')
    axes.set_ylabel('Radius [mm]')
    axes.set_title(data.title)
    axes.set_aspect('equal', adjustable = 'box')
    axes.grid(False)

    # A colorbar axis matched to the nozzle axes' own rendered width, which the equal aspect
    # ratio shrinks well below the figure width. A colorbar spanning the full figure instead
    # would leave the nozzle sitting in dead space on both sides once the figure is saved tight.
    label = data.label.replace('[Pa]', '[MPa]') if quantity == 'pressure' else data.label
    cax = make_axes_locatable(axes).append_axes('bottom', size = '5%', pad = 0.5)
    figure.colorbar(mesh, cax = cax, orientation = 'horizontal', label = label)
    return figure

#--------------------------------------------------------------------------------------------------------------------------#
# -- 3D assembly renderers, plotly only -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _cyclicHSVColors(count: int):

    '''Per-station wireframe colors around the HSV wheel, cycled every 5 stations.'''

    base = sample_colorscale(plotly.colors.cyclical.HSV, list(np.linspace(0, 1, int(np.ceil(count / 5)))))
    colors = np.array(base)
    for _ in range(5):
        colors = np.append(colors, base)
    return colors

def _addVoluteBranch(figure, nozzle, arrayPrefix: str, voluteName: str, colors) -> None:

    '''

    One volute branch: its surface and wireframe, then its shell and print supports if the
    branch built them.

    Parameters:
    -----------
    arrayPrefix : str
        'Inlet' or 'Return', matching the x{arrayPrefix}Volute-style attribute names.
    voluteName : str
        'inletVolute' or 'returnVolute', the Volute instance carrying wallThickness and
        circlePrintability.

    '''

    numCS = nozzle.numCSVolute
    volute = getattr(nozzle, voluteName)

    def addSurface(part: str, color: str, opacity: float) -> None:

        x = getattr(nozzle, f'x{arrayPrefix}Volute{part}')
        y = getattr(nozzle, f'y{arrayPrefix}Volute{part}')
        z = getattr(nozzle, f'z{arrayPrefix}Volute{part}')
        figure.add_trace(go.Surface(x = x, y = y, z = z, colorscale = [[0, color], [1, color]],
                                    opacity = opacity, showscale = False))
        for i in range(numCS):
            figure.add_trace(go.Scatter3d(x = x[i, :], y = y[i, :], z = z[i, :], mode = 'lines',
                                          line = dict(color = colors[i], width = 5)))

    addSurface('', 'cyan', 0.8)

    if volute.wallThickness is not None:
        addSurface('Shell', 'yellow', 0.35)

    if volute.circlePrintability in ('thin', 'thick'):
        addSurface('SupportWall', 'magenta', 0.35)
        addSurface('SupportUpper', 'magenta', 0.35)
    if volute.circlePrintability == 'thick':
        addSurface('SupportLower', 'magenta', 0.35)

def volutesFigure(nozzle):

    '''

    The nozzle wall and shell, the print bed, and both volutes with their shells and print
    supports, in one 3D assembly.

    A representative channel is highlighted in red so the return volute's smallest cross
    section can be checked by eye against the channel flare it attaches to.

    Returns:
    --------
    plotly.graph_objects.Figure or None
        None when neither volute was built.

    '''

    if nozzle.makeInletVolute != 'on' and nozzle.makeReturnVolute != 'on':
        return None

    # The representative channel, rolled a quarter turn to the orientation the return volute's
    # narrowest cross section is checked against. This is a display aid only; nothing downstream
    # reads it.
    numCSPointsChannel, numStations = nozzle.numCSPointsChannel, len(nozzle.xChannel[0, :])
    channelX, channelY, channelZ = [np.zeros((numCSPointsChannel, numStations)) for _ in range(3)]
    for i in range(numStations):
        valueMatrix = [nozzle.xChannel[:, i], nozzle.yChannel[:, i], nozzle.zChannel[:, i]]
        channelX[:, i], channelY[:, i], channelZ[:, i] = DCM(
            [np.pi / 2, 0, 0], valueMatrix, transpose = False, rotationOrder = 'xyz')

    printX, printY, printZ = revolveContour(
        [min(nozzle.xRegenNozzle), max(nozzle.xRegenNozzle)],
        [0.5 * nozzle.chamberDiameter, 0.5 * nozzle.chamberDiameter])

    figure = go.Figure()
    grey = [[0, 'darkgrey'], [1, 'darkgrey']]
    figure.add_trace(go.Surface(x = printZ, y = printX, z = printY, colorscale = grey,
                                opacity = 0.15, showscale = False))
    figure.add_trace(go.Surface(x = nozzle.xNozzleHotWallMesh, y = nozzle.yNozzleHotWallMesh,
                                z = nozzle.zNozzleHotWallMesh, colorscale = grey, opacity = 0.7,
                                showscale = False))
    figure.add_trace(go.Surface(x = nozzle.xNozzleShellMesh, y = nozzle.yNozzleShellMesh,
                                z = nozzle.zNozzleShellMesh, colorscale = grey, opacity = 0.7,
                                showscale = False))
    figure.add_trace(go.Surface(x = channelX, y = channelY, z = channelZ,
                                colorscale = [[0, 'red'], [1, 'red']], opacity = 1,
                                showscale = False))

    colors = _cyclicHSVColors(nozzle.numCSVolute)
    if nozzle.makeInletVolute == 'on':
        _addVoluteBranch(figure, nozzle, 'Inlet', 'inletVolute', colors)
    if nozzle.makeReturnVolute == 'on':
        _addVoluteBranch(figure, nozzle, 'Return', 'returnVolute', colors)

    figure.update_layout(
        scene = dict(xaxis_title = 'Nozzle Radius [m]', yaxis_title = 'Nozzle Axis [m]',
                    zaxis_title = 'Nozzle Radius [m]'),
        title = {'text': 'Volutes', 'x': 0.5, 'xanchor': 'center', 'y': 0.9, 'yanchor': 'top'},
        scene_aspectmode = 'data', template = 'plotly_dark', showlegend = False)
    return figure

def _printBedTrace(nozzle):

    '''The build volume's print bed as a flat disc at the chamber radius, spanning the regen section.'''

    x, y, z = revolveContour([min(nozzle.xRegenNozzle), max(nozzle.xRegenNozzle)],
                             [0.5 * nozzle.chamberDiameter, 0.5 * nozzle.chamberDiameter])
    return go.Surface(x = y, y = z, z = x, colorscale = [[0, 'darkgrey'], [1, 'darkgrey']],
                      opacity = 0.3, showscale = False)

def channelMeshFigure(nozzle):

    '''

    Three adjacent channels swept against the nozzle wall, with the centerline and every
    cross-section wireframe called out on the middle one.

    The neighbors are the middle channel rotated by plus and minus one channel pitch about the
    nozzle axis, which is what the jacket pattern does, so the rib between them is drawn to
    scale without an array of every channel being built to draw it.

    Returns:
    --------
    plotly.graph_objects.Figure or None
        None when no channel was generated.

    '''

    if getattr(nozzle, 'xChannel', None) is None:
        return None

    colors = _cyclicHSVColors(nozzle.numCrossSections)
    figure = go.Figure()
    figure.add_trace(_printBedTrace(nozzle))
    figure.add_trace(go.Surface(x = nozzle.zNozzleColdWallMesh, y = nozzle.xNozzleColdWallMesh,
                                z = nozzle.yNozzleColdWallMesh,
                                colorscale = [[0, 'darkgrey'], [1, 'darkgrey']], opacity = 0.8,
                                showscale = False))

    pitch = 2*np.pi / nozzle.nChannel
    for rollAngle, color in ((-pitch, 'cyan'), (pitch, 'magenta')):
        yNeighbor = nozzle.yChannel*np.cos(rollAngle) - nozzle.zChannel*np.sin(rollAngle)
        zNeighbor = nozzle.yChannel*np.sin(rollAngle) + nozzle.zChannel*np.cos(rollAngle)
        figure.add_trace(go.Surface(x = zNeighbor, y = nozzle.xChannel, z = yNeighbor,
                                    colorscale = [[0, color], [1, color]], opacity = 1,
                                    showscale = False))
    figure.add_trace(go.Surface(x = nozzle.zChannel, y = nozzle.xChannel, z = nozzle.yChannel,
                                colorscale = [[0, 'yellow'], [1, 'yellow']], opacity = 0.975,
                                showscale = False))
    figure.add_trace(go.Scatter3d(x = nozzle.zChannelCenterline3D, y = nozzle.xChannelCenterline3D,
                                  z = nozzle.yChannelCenterline3D, mode = 'lines',
                                  line = dict(color = 'red', width = 10)))
    for i in range(nozzle.numCrossSections):
        figure.add_trace(go.Scatter3d(x = nozzle.zChannel[:, i], y = nozzle.xChannel[:, i],
                                      z = nozzle.yChannel[:, i], mode = 'lines', opacity = 0.8,
                                      line = dict(color = colors[i], width = 10), name = f'CS {i}'))

    figure.update_layout(
        scene = dict(xaxis_title = 'Nozzle Radius [m]', yaxis_title = 'Nozzle Axis [m]',
                    zaxis_title = 'Nozzle Radius [m]'),
        title = {'text': 'Channel Mesh View', 'x': 0.5, 'xanchor': 'center', 'y': 0.9,
                'yanchor': 'top'},
        scene_aspectmode = 'data', template = 'plotly_dark', showlegend = False)
    return figure

def regenHeatTransferModelPlots(context, coolant, nChannel, results: dict = None,
                                family: str = 'circle', adiabatic = False, titleFlare: str = '',
                                xReference = [], rReference = [], wallTemperatureLimit = None):

    '''

    The regen channel property dashboard: pressure, temperature, wall temperature, velocity,
    Mach number, heat transfer, density, viscosity, heat capacity, Nusselt number, heat transfer
    coefficient and Reynolds number along the channel.

    Draws the one channel family it is handed, `results` from the thermal model, labelled with
    `family`. It solves nothing itself, since the channel sizing solve has already computed these
    station-by-station arrays by the time a dashboard is worth drawing. The wall temperature
    limit is drawn when one is given. Written to `context.dataFolder` when `context.export` is
    'on', shown inline otherwise.

    '''

    from plotly.subplots import make_subplots

    from .channelSections import SECTIONLABELS

    if not results:
        return

    label = SECTIONLABELS.get(family, str(family))

    # Helper function to add a trace
    def add_trace(row, col, x, y, name, color=None, showlegend=False, dash='solid', secondary_y=False, legendgroup=None, **kwargs):
        '''
        Adds a trace to the specified subplot with optional legend grouping.

        Args:
            row (int): Row number of the subplot.
            col (int): Column number of the subplot.
            x (array-like): x-axis data.
            y (array-like): y-axis data.
            name (str): Name of the trace.
            color (str, optional): Color of the trace. Defaults to None.
            showlegend (bool, optional): Whether to show the legend. Defaults to False.
            dash (str, optional): Line dash style. Defaults to 'solid'.
            secondary_y (bool, optional): Whether to plot on secondary y-axis. Defaults to False.
            legendgroup (str, optional): Legend group for the trace. Defaults to None.
            **kwargs: Additional keyword arguments for go.Scatter.
        '''
        fig.add_trace(
            go.Scatter(x=x, y=y, name=name, line=dict(color=color, dash=dash), showlegend=showlegend, legendgroup=legendgroup, **kwargs),
            row=row, col=col, secondary_y=secondary_y
            )

    xHotWall3D        = results["xHotWall3D"]
    rHotWall3D        = results["rHotWall3D"]
    coolantPressure   = results["pressure"]
    finalPressure     = coolantPressure[0]
    totalPressureDrop = coolantPressure[-1] - finalPressure

    print(f'Total pressure drop: {totalPressureDrop/1e6:.4f}(MPa) | Exit Pressure: {finalPressure/1e6:.4f}(MPa)')

    if not adiabatic:

        # -- Plotly implementation -- #

        # Instantiate Figure
        fig = make_subplots(rows=4, cols=3, subplot_titles=(
            'Pressure', 'Temperature', 'Wall Temperature',
            'Streamwise Velocity', 'Mach Number', 'Heat Transfer',
            'Density', 'Viscosity', 'Heat Capacity',
            'Nusselt Number', 'Heat Transfer Coef', 'Reynolds Number'),
        horizontal_spacing = 0.05,   #setting spaceing between plots
        vertical_spacing = 0.05,
        specs=[[{"secondary_y": True}, {"secondary_y": True}, {"secondary_y": True}],
            [{"secondary_y": True}, {"secondary_y": True}, {"secondary_y": True}],
            [{"secondary_y": True}, {"secondary_y": True}, {"secondary_y": True}],
            [{"secondary_y": True}, {"secondary_y": True}, {"secondary_y": True}]
            ]
        )

        # Legend
        colors = {
                label: 'magenta',
                'Wall temperature limit': 'red',
                'Nozzle': 'grey'
        }
        if wallTemperatureLimit is None:
            del colors['Wall temperature limit']
        for name, color in colors.items():
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=color), name=name, showlegend=True))

        # Nozzle Contours
        for i in [1,2,3]:
            for j in [1,2,3,4]:
                if len(xReference)==0 or len(rReference)==0:
                    add_trace(j, i, xHotWall3D, rHotWall3D, 'Nozzle Radius', color=colors['Nozzle'], dash='dot', showlegend=False, secondary_y=True)
                else:
                    add_trace(j, i, xReference, rReference, 'Nozzle Radius', color=colors['Nozzle'], dash='dot', showlegend=False, secondary_y=True)

        # -- Titles -- #

        # Coolant Pressure
        fig.update_yaxes(title_text=r'$\text {Pressure [MPa]}$', row=1, col=1, secondary_y=False, gridcolor='#4a4a4a')
        # Coolant Temperature
        fig.update_yaxes(title_text=r'$\text {Temperature [K]}$', row=1, col=2, secondary_y=False, gridcolor='#4a4a4a')
        # Wall Temperature
        if wallTemperatureLimit is not None:
            add_trace(1, 3, xHotWall3D, wallTemperatureLimit * np.ones(len(xHotWall3D)), 'Wall temperature limit', colors['Wall temperature limit'], dash='solid')
        fig.update_yaxes(title_text=r'$\text {Temperature [K]}$', row=1, col=3, secondary_y=False, gridcolor='#4a4a4a')
        # Velocity
        fig.update_yaxes(title_text=r'$\text {Velocity [m/s]}$', row=2, col=1, secondary_y=False, gridcolor='#4a4a4a')
        # Mach
        fig.update_yaxes(title_text=r'$\text {Mach Number [-]}$', row=2, col=2, secondary_y=False, gridcolor='#4a4a4a')
        # Heat Transfer
        fig.update_yaxes(title_text=r'$\text {Heat Transfer [W]}$', row=2, col=3, secondary_y=False, gridcolor='#4a4a4a')
        # Density
        fig.update_yaxes(title_text=r'$\rho \text{ [kg/m}^{3} \text{]}$', row=3, col=1, secondary_y=False, gridcolor='#4a4a4a')
        # Viscosity
        fig.update_yaxes(title_text=r'$\mu \text{ [Pa*s]}$', row=3, col=2, secondary_y=False, gridcolor='#4a4a4a')
        # Specific Heat
        fig.update_yaxes(title_text=r'$\text {C_P [J/kg*K]}$', row=3, col=3, secondary_y=False, gridcolor='#4a4a4a')
        # Nusselt
        fig.update_yaxes(title_text=r'$\text {Nu [-]}$', row=4, col=1, secondary_y=False, gridcolor='#4a4a4a')
        # Heat Transfer Coef
        fig.update_yaxes(title_text=r'$\text{ h [W/(m}^{2}\text{*K)]}$', row=4, col=2, secondary_y=False, gridcolor='#4a4a4a')
        # Reynolds
        fig.update_yaxes(title_text=r'$\text {Re [-]}$', row=4, col=3, secondary_y=False, gridcolor='#4a4a4a')

        # -- Data -- #

        add_trace(1, 1, xHotWall3D, coolantPressure/1e6, label, colors[label])
        add_trace(1, 2, xHotWall3D, results['temperature'], label, colors[label])
        add_trace(1, 3, xHotWall3D, results['wallTemperature'], label, colors[label])
        add_trace(2, 1, xHotWall3D, results['velocity'], label, colors[label])
        add_trace(2, 2, xHotWall3D, results['machNumber'], label, colors[label])
        add_trace(2, 3, xHotWall3D, results['heatTransfer'], label, colors[label])
        add_trace(3, 1, xHotWall3D, results['density'], label, colors[label])
        add_trace(3, 2, xHotWall3D, results['viscosity'], label, colors[label])
        add_trace(3, 3, xHotWall3D, results['specificHeat'], label, colors[label])
        add_trace(4, 1, xHotWall3D, results['nusseltNumber'], label, colors[label])
        add_trace(4, 2, xHotWall3D, results['coolantConvectiveHeatTransferCoef'], f'Coolant - {label}', colors[label])
        add_trace(4, 2, xHotWall3D, results['exhaustConvectiveHeatTransferCoef'], f'Exhaust - {label}', colors[label], dash='dot')
        add_trace(4, 3, xHotWall3D, results['reynoldsNumber'], label, colors[label])
        # The gas-side driving temperature belongs beside the wall it drives, and the radiative
        # share beside the total it is part of. Neither earns a panel of its own.
        add_trace(1, 3, xHotWall3D, results['drivingTemperature'], f'Driving gas - {label}',
                  colors[label], dash = 'dash')
        if np.any(results['radiativeHeatTransfer']):
            add_trace(2, 3, xHotWall3D, results['radiativeHeatTransfer'], f'Radiative - {label}',
                      colors[label], dash = 'dot')

        # Update layout for all subplots
        for i in range(1, 13):

            row = (i - 1) // 3 + 1
            col = (i - 1) % 3 + 1

            fig.update_xaxes(title_text=r'$\text {Nozzle Axis [m]}$' if row == 4 else '', row=row, col=col, gridcolor='#4a4a4a', tickfont=dict(color='white' if row == 4 else 'rgba(0,0,0,0)'))

            # Add secondary y-axis for Nozzle Radius only on rightmost plots - OUTSIDE the loop
            fig.update_yaxes(title_text=r'$\text {Nozzle Radius [m]}$' if col == 3 else '', row = row, col = col, secondary_y=True, title_font=dict(color=colors['Nozzle'] if col == 3 else 'rgba(0,0,0,0)'), tickfont=dict(color=colors['Nozzle'] if col == 3 else 'rgba(0,0,0,0)'), showgrid=False)

        # Update overall layout
        fig.update_layout(
            #height=1200,
            #width=1800,
            title_text=f'Regen Channel Properties: {int(nChannel)} Channels{titleFlare}',
            title_x=0.5,  # Center the main title
            autosize=True,
            title_font=dict(size=24),
            plot_bgcolor='black',
            paper_bgcolor='black',
            font=dict(color='white', family = "Computer Modern"),
            legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(size=12))
        )

        if context.export == 'on':

            print('Saving Heat Transfer Outputs to .html')

            _writePlotlyFigure(fig, filename = context.dataFolder + '\\heatTransferModelOutput.html', auto_open = not headlessPlots())

        else:

            showFigure(fig)

    if adiabatic:

        # -- Plotly implementation -- #

        # Instantiate Figure
        fig = make_subplots(rows=2, cols=2, subplot_titles=(
            'Pressure', 'Temperature',
            'Heat Capacity', 'Heat Transfer Coef'),
        horizontal_spacing = 0.05,   #setting spaceing between plots
        vertical_spacing = 0.05,
        specs=[[{"secondary_y": True}, {"secondary_y": True}],
            [{"secondary_y": True}, {"secondary_y": True}],
            ]
        )

        # Legend
        colors = {
                label: 'magenta',
                'Nozzle': 'grey'
        }
        for name, color in colors.items():
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=color), name=name, showlegend=True))

        # Nozzle Contours
        for i in [1,2]:
            for j in [1,2]:
                add_trace(j, i, xHotWall3D, rHotWall3D, 'Nozzle Radius', color=colors['Nozzle'], dash='dot', showlegend=False, secondary_y=True)

        # -- Titles -- #

        # Coolant Pressure
        fig.update_yaxes(title_text=r'$\text {Pressure [MPa]}$', row=1, col=1, secondary_y=False, gridcolor='#4a4a4a')
        # Coolant Temperature
        fig.update_yaxes(title_text=r'$\text {Temperature [K]}$', row=1, col=2, secondary_y=False, gridcolor='#4a4a4a')
        # Specific Heat
        fig.update_yaxes(title_text=r'$\text {C_P [J/kg*K]}$', row=2, col=1, secondary_y=False, gridcolor='#4a4a4a')
        # Heat Transfer Coef
        fig.update_yaxes(title_text=r'$\text{ h [W/(m}^{2}\text{*K)]}$', row=2, col=2, secondary_y=False, gridcolor='#4a4a4a')

        # -- Data -- #

        add_trace(1, 1, xHotWall3D, coolantPressure/1e6, label, colors[label])
        add_trace(1, 2, xHotWall3D, results['temperature'], label, colors[label])
        add_trace(2, 1, xHotWall3D, results['specificHeat'], label, colors[label])
        add_trace(2, 2, xHotWall3D, results['adiabaticConvectiveHeatTransferCoef'], label, colors[label])

        # Update layout for all subplots
        for i in [1,2]:

            fig.update_xaxes(title_text=r'$\text {Nozzle Axis [m]}$', row=2, col=i, gridcolor='#4a4a4a', tickfont=dict(color='white'))
            fig.update_xaxes(title_text= '',                          row=1, col=i, gridcolor='#4a4a4a', tickfont=dict(color='rgba(0,0,0,0)'))

            # Add secondary y-axis for Nozzle Radius only on rightmost plots - OUTSIDE the loop
            fig.update_yaxes(title_text=r'$\text {Nozzle Radius [m]}$', row = i, col = 2, secondary_y=True, title_font=dict(color=colors['Nozzle']), tickfont=dict(color=colors['Nozzle']), showgrid=False)
            fig.update_yaxes(title_text= '',                            row = i, col = 1, secondary_y=True, title_font=dict(color=colors['Nozzle']), tickfont=dict(color='rgba(0,0,0,0)'), showgrid=False)

        # Update overall layout
        fig.update_layout(
            #height=1200,
            #width=1800,
            title_text=f'Regen Channel Properties: {int(nChannel)} Channels{titleFlare}',
            title_x=0.5,  # Center the main title
            autosize=True,
            title_font=dict(size=24),
            plot_bgcolor='black',
            paper_bgcolor='black',
            font=dict(color='white', family = "Computer Modern"),
            legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(size=12))
        )

        if context.export == 'on':

            print('Saving Heat Transfer Outputs to .html')

            _writePlotlyFigure(fig, filename = context.dataFolder + '\\heatTransferModelOutput.html', auto_open = not headlessPlots())

        else:

            showFigure(fig)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Export -- #
#--------------------------------------------------------------------------------------------------------------------------#

def writeInteractiveFigure(figure, path: str) -> str:

    '''

    Write a plotly figure to a standalone HTML file without opening a browser tab.

    Returns the path written, or None when there was no figure to write.

    '''

    if figure is None:
        return None
    # 'directory' drops one shared plotly.min.js beside the HTML instead of inlining a 4.5 MB
    # copy into every file, which turns a six-figure export from ~30 MB into ~5 MB and still
    # views offline. The files are only portable as a folder, which is how a run is written.
    _writePlotlyFigure(figure, filename = path, auto_open = False, include_plotlyjs = 'directory')
    return path

# Output file name -> builder taking a Nozzle and returning a plotly figure or None.
interactiveFigureBuilders = {
    'contourInteractive.html':      lambda nozzle: plotlyContour(contourFigure(nozzle)),
    'nearWallInteractive.html':     lambda nozzle: plotlyNearWall(nearWallFigure(nozzle)),
    'revolvedContourView.html':     lambda nozzle: plotlyRevolved(revolvedFigure(nozzle)),
    'machFieldInteractive.html':    lambda nozzle: plotlyField(fieldFigure(nozzle, 'mach')),
    'pressureFieldInteractive.html': lambda nozzle: plotlyField(fieldFigure(nozzle, 'pressure')),
    'temperatureFieldInteractive.html': lambda nozzle: plotlyField(fieldFigure(nozzle, 'temperature')),
    'plumeStructureInteractive.html': lambda nozzle: plotlyPlume(plumeFigure(nozzle)),
    'VoluteView.html':               lambda nozzle: volutesFigure(nozzle),
    'threeChannelMeshViewInterfaced.html': lambda nozzle: channelMeshFigure(nozzle),
}

def exportInteractiveFigures(nozzle, folder: str) -> list:

    '''

    Write the interactive HTML companion for every result figure that has data.

    A builder that raises is skipped with a note rather than sinking the export.

    Parameters:
    -----------
    nozzle : Nozzle
        A generated nozzle
    folder : str
        Destination directory, created if absent

    Returns:
    --------
    list : absolute paths of the files written

    '''

    os.makedirs(folder, exist_ok = True)
    written = []
    for name, builder in interactiveFigureBuilders.items():
        try:
            figure = builder(nozzle)
        except Exception as error:                  # noqa: BLE001 -- one bad figure must not sink the export
            print(f'Skipping interactive view {name}: {type(error).__name__}: {error}')
            continue
        path = writeInteractiveFigure(figure, os.path.join(folder, name))
        if path is not None:
            written.append(path)
    if written:
        print(f'Saving {len(written)} interactive figure(s) to .html')
    return written
