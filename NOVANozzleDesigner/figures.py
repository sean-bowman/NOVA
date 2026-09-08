
# -- Renderer-Independent Figure Data -- #

'''

One description of each result figure, and a plotly renderer for it.

NOVA draws every figure twice. Matplotlib renders the panes embedded in the GUI and the PNGs
written beside a run, because it draws into a Tk canvas and is always installed. Plotly renders
the interactive HTML opened in a browser, because it pans, zooms and reads values off a mesh far
better than a static image, and it cannot be embedded in Tk at all.

Rather than write each figure twice, the extractors here pull the arrays and labels off a
Nozzle into a plain dataclass that neither library appears in. novaGui.plotting renders those
with Matplotlib; the plotly builders below render the same objects for export. A figure is
described once, and the two renderings cannot drift.

Plotly is optional. Every builder returns None when it is not installed, and
exportInteractiveFigures() then writes nothing and reports an empty list.

Author: Sean Bowman
Date:   08/28/2026

'''

import os
from dataclasses import dataclass, field

import numpy as np

try:
    import plotly.graph_objects as go
    from plotly.offline import plot as _writePlotlyFigure
    plotlyAvailable = True
except ImportError:
    go = _writePlotlyFigure = None
    plotlyAvailable = False

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
    title: str = 'Near-wall exhaust state'

@dataclass
class RevolvedFigure:

    '''

    Surface of revolution of the wall contour, with cooling channel centrelines when a jacket
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
    if x.size == 0 or temperature.size == 0:
        return None

    axis = np.linspace(x[0], x[-1], temperature.size)
    if pressure.size != temperature.size:
        pressure = np.full(temperature.size, np.nan)
    if mach.size != temperature.size:
        mach = np.full(temperature.size, np.nan)
    return NearWallFigure(axis = axis, temperature = temperature, pressure = pressure, mach = mach)

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

# Quantity key -> (Nozzle attribute, colour bar label, plotly colorscale, figure title)
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

    Dark layout matching the GUI, with the colour bar laid horizontally under the plot so a
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

    if not plotlyAvailable or data is None:
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

    if not plotlyAvailable or data is None:
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

    if not plotlyAvailable or data is None:
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
                showlegend = index == 0, name = 'Channel centrelines',
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

    The mesh is curvilinear, so the field is drawn as a coloured point cloud rather than a
    filled contour: plotly's contour trace needs a regular grid, and hovering a point to read
    its exact value is more useful for inspection than banded fill anyway.

    '''

    if not plotlyAvailable or data is None:
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

    if not plotlyAvailable or data is None:
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
# -- Export -- #
#--------------------------------------------------------------------------------------------------------------------------#

def writeInteractiveFigure(figure, path: str) -> str:

    '''

    Write a plotly figure to a standalone HTML file without opening a browser tab.

    Returns the path written, or None when there was no figure to write.

    '''

    if figure is None or not plotlyAvailable:
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
}

def exportInteractiveFigures(nozzle, folder: str) -> list:

    '''

    Write the interactive HTML companion for every result figure that has data.

    Silent no-op without plotly, so a run on a plotly-free install still produces its full set
    of PNGs. A builder that raises is skipped with a note rather than sinking the export.

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

    if not plotlyAvailable:
        return []

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
