
# -- NOVA GUI Matplotlib Drawers -- #

'''

The Matplotlib drawers for the views: contour, near-wall state, the Mach, pressure and temperature
fields, the revolved contour and the plume, and the table of plotly builders for the same views
and the 3D assemblies, which draw only in plotly.

The drawers take figure descriptions from NOVA.figures, which also carries a plotly renderer for
the same descriptions, so the static and interactive renderings of a view cannot drift apart.
Colors come from the active palette mode (themeColors), and fields use NOVA.palette's colormaps in
the same mode.

A drawer draws into a pane: any object with `figure` (a Matplotlib Figure), `axes`, `_projection`,
`clear(projection)`, `message(text)` and `redraw()`. The static renderer's pane renders to PNG with
no window (novaGui.views.HeadlessPane).

Author: Sean Bowman
Date:   08/28/2026

'''

import numpy as np

import matplotlib

from . import themeColors
from . import backend

matplotlib.rcParams.update(themeColors.matplotlibRcParams())

def _palette():

    '''NOVA.palette, set to the GUI's mode, for the field colormaps.'''

    palette = backend.figuresModule().figurePalette
    palette.setFigureMode(themeColors.mode)

    return palette

def _legend(ax, **options) -> None:

    ax.legend(facecolor = themeColors.surface2, edgecolor = themeColors.border, labelcolor = themeColors.text,
              fontsize = 8, **options)

def _colorbar(pane, mappable, ax, label: str) -> None:

    '''A horizontal color bar under a wide axisymmetric plot, styled for the mode.'''

    from matplotlib.ticker import MaxNLocator

    bar = pane.figure.colorbar(mappable, ax = ax, orientation = 'horizontal', fraction = 0.05, pad = 0.10)
    bar.set_label(label, color = themeColors.text)
    bar.outline.set_edgecolor(themeColors.border)
    bar.ax.tick_params(colors = themeColors.textMuted)
    # Round ticks rather than the contour levels, which land on unreadable values
    low, high = mappable.norm.vmin, mappable.norm.vmax
    if low is not None and high is not None and high > low:
        ticks = MaxNLocator(7).tick_values(low, high)
        bar.set_ticks(ticks[(ticks >= low) & (ticks <= high)])

#--------------------------------------------------------------------------------------------------------------------------#
# -- Matplotlib renderers -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawContour(pane, nozzle) -> None:

    '''

    Full nozzle contour: converging section, throat, diverging wall, and the regen / extension
    split when the contour was truncated. Mirrored about the axis with key radii and the overall
    length annotated.

    '''

    data = backend.figuresModule().contourFigure(nozzle)
    if data is None:
        pane.message('No contour was generated.')
        return

    pane.clear(projection = None)
    ax = pane.axes

    ax.plot(data.x, data.r, color = themeColors.accent, linewidth = 1.8, label = 'Wall contour')
    ax.plot(data.x, -data.r, color = themeColors.accent, linewidth = 1.8)
    ax.fill_between(data.x, data.r, -data.r, color = themeColors.accent, alpha = 0.06)

    if data.xRegen.size:
        ax.plot(data.xRegen, data.rRegen, color = themeColors.blue, linewidth = 2.2,
                label = 'Regen-cooled portion')
        ax.plot(data.xRegen, -data.rRegen, color = themeColors.blue, linewidth = 2.2)

    ax.axvline(data.throatX, color = themeColors.textDim, linewidth = 0.8, linestyle = '--')
    ax.annotate(f'throat r = {data.throatRadius * 1e3:.1f} mm',
                xy = (data.throatX, data.throatRadius),
                xytext = (10, 16), textcoords = 'offset points',
                color = themeColors.textMuted, fontsize = 8)
    ax.annotate(f'exit r = {data.exitRadius * 1e3:.1f} mm',
                xy = (data.x[-1], data.exitRadius),
                xytext = (-40, 12), textcoords = 'offset points',
                color = themeColors.textMuted, fontsize = 8)

    ax.set_title(f'{data.title}   (length {data.length * 1e3:.0f} mm)', color = themeColors.text)
    ax.set_xlabel('Nozzle axis [m]')
    ax.set_ylabel('Radius [m]')
    ax.set_aspect('equal', adjustable = 'datalim')
    _legend(ax)
    pane.redraw()

def drawNearWall(pane, nozzle) -> None:

    '''

    Near-wall exhaust state along the axis: static temperature, static pressure and Mach number
    on a shared axis.

    '''

    data = backend.figuresModule().nearWallFigure(nozzle)
    if data is None:
        pane.message('Near-wall exhaust properties were not computed for this run.')
        return

    pane.figure.clear()
    pane.figure.set_layout_engine('constrained')
    pane._projection = None
    grid = pane.figure.add_gridspec(3, 1, hspace = 0.06)
    axT = pane.figure.add_subplot(grid[0])
    axP = pane.figure.add_subplot(grid[1], sharex = axT)
    axM = pane.figure.add_subplot(grid[2], sharex = axT)

    for ax in (axT, axP, axM):
        themeColors.styleAxes(ax)

    axT.plot(data.axis, data.temperature, color = themeColors.accent)
    axT.set_ylabel('T [K]')
    axT.set_title(data.title, color = themeColors.text)

    axP.plot(data.axis, data.pressure / 1e5, color = themeColors.blue)
    axP.set_ylabel('P [bar]')

    axM.plot(data.axis, data.mach, color = themeColors.cyan)
    axM.set_ylabel('Mach [-]')
    axM.set_xlabel('Nozzle axis [m]')

    for ax in (axT, axP):
        ax.tick_params(labelbottom = False)

    pane.axes = axM
    pane.redraw()

def _outline(wallX, wallR):

    '''The closed outline of an axisymmetric wall, upper side then lower, as (x, y) vertices.'''

    wallX, wallR = np.asarray(wallX, dtype = float), np.asarray(wallR, dtype = float)

    return np.column_stack([np.concatenate([wallX, wallX[::-1]]), np.concatenate([wallR, -wallR[::-1]])])

def _clipTo(ax, artist, vertices) -> None:

    '''Clip a filled contour to a closed outline, so a triangulation cannot spill past a wall.'''

    from matplotlib.patches import Polygon

    clip = Polygon(vertices, closed = True, transform = ax.transData, facecolor = 'none', edgecolor = 'none')
    ax.add_patch(clip)
    artist.set_clip_path(clip)

def _mirrored(x, r, values):

    '''A structured half field mirrored about the axis, keeping the radial coordinate monotone.'''

    return (np.concatenate([x[:, ::-1], x], axis = 1), np.concatenate([-r[:, ::-1], r], axis = 1),
            np.concatenate([values[:, ::-1], values], axis = 1))

def drawField(pane, nozzle, quantity: str) -> None:

    '''

    A flow field from the injector face to the exit plane, mirrored about the axis: the quasi
    one-dimensional answer upstream of the throat, the characteristic mesh from the throat to the
    exit plane of the wall that is built, and the seam between them marked, because the two are
    different kinds of answer. Pressure falls three orders of magnitude, so its scale is logarithmic.

    '''

    from matplotlib.colors import LogNorm

    data = backend.figuresModule().stitchedFieldFigure(nozzle, quantity)
    if data is None:
        pane.message('This run kept no characteristic mesh, so there is no field to draw. '
                     'A conical diverging section never builds one.')
        return

    scale, label = {'mach': (1.0, 'Mach number [-]'), 'pressure': (1e-5, 'Static pressure [bar], logarithmic'),
                    'temperature': (1.0, 'Static temperature [K]')}[quantity]
    upstream = np.asarray(data.upstreamValues, dtype = float) * scale
    mesh = np.asarray(data.meshValues, dtype = float) * scale
    pieces = [mesh] + ([upstream.ravel()] if upstream.size else [])
    lowest = min(float(np.nanmin(piece)) for piece in pieces)
    highest = max(float(np.nanmax(piece)) for piece in pieces)
    if data.logarithmic:
        levels = np.geomspace(max(lowest, highest * 1e-4), highest, 80)
        norm = LogNorm(vmin = levels[0], vmax = levels[-1])
    else:
        levels, norm = np.linspace(lowest, highest, 80), None
    cmap = _palette().colormap(data.colorscale, themeColors.mode)

    pane.clear(projection = None)
    ax = pane.axes
    ax.grid(False)
    outline = _outline(data.wallX, data.wallR)
    shading = None
    if upstream.size:
        shading = ax.contourf(*_mirrored(data.upstreamX, data.upstreamR, upstream), levels = levels, cmap = cmap,
                              norm = norm, extend = 'both')
        _clipTo(ax, shading, outline)
    if mesh.size > 3:
        shading = ax.tricontourf(np.concatenate([data.meshX, data.meshX]), np.concatenate([data.meshR, -data.meshR]),
                                 np.concatenate([mesh, mesh]), levels = levels, cmap = cmap, norm = norm,
                                 extend = 'both')
        _clipTo(ax, shading, outline)

    for sign in (1.0, -1.0):
        ax.plot(data.wallX, sign * np.asarray(data.wallR), color = themeColors.accent, linewidth = 1.6)

    # The seam, marked rather than blended
    span = float(np.max(data.wallR))
    ax.axvline(data.throatX, color = themeColors.text, linewidth = 0.9, linestyle = '--', alpha = 0.6)
    offset = 0.012 * (data.exitX - float(np.min(data.wallX)))
    ax.text(data.throatX - offset, 0.88 * span, 'one dimensional', color = themeColors.textMuted, fontsize = 8,
            ha = 'right', style = 'italic')
    ax.text(data.throatX + offset, 0.88 * span, 'characteristics', color = themeColors.textMuted, fontsize = 8,
            ha = 'left', style = 'italic')

    ax.set_xlim(float(np.min(data.wallX)), data.exitX)
    ax.set_ylim(-1.08 * span, 1.08 * span)
    ax.set_title(data.title, color = themeColors.text)
    ax.set_xlabel('Nozzle axis [m]')
    ax.set_ylabel('Radius [m]')
    ax.set_aspect('equal', adjustable = 'box')
    if shading is not None:
        bar = pane.figure.colorbar(shading, ax = ax, orientation = 'horizontal', fraction = 0.05, pad = 0.10)
        bar.set_label(label, color = themeColors.text)
        bar.outline.set_edgecolor(themeColors.border)
        bar.ax.tick_params(colors = themeColors.textMuted)
        if not data.logarithmic:
            from matplotlib.ticker import MaxNLocator
            ticks = MaxNLocator(7).tick_values(levels[0], levels[-1])
            bar.set_ticks(ticks[(ticks >= levels[0]) & (ticks <= levels[-1])])
        if data.logarithmic:
            # Decade ticks; the level values themselves read as six-figure mantissas
            decades = 10.0 ** np.arange(np.floor(np.log10(levels[0])), np.ceil(np.log10(levels[-1])) + 1)
            decades = decades[(decades >= levels[0]) & (decades <= levels[-1])]
            bar.set_ticks(decades)
            bar.set_ticklabels([f'{value:g}' for value in decades])
    pane.redraw()

def drawRevolvedContour(pane, nozzle, sweepDeg: float = 300.0) -> None:

    '''

    Surface-of-revolution view of the wall contour, with the cooling channel centerlines overlaid
    when a jacket was generated. This is a fast orientation view; the interactive export carries
    the full meshes.

    '''

    data = backend.figuresModule().revolvedFigure(nozzle, sweepDeg = sweepDeg)
    if data is None:
        pane.message('No contour was generated.')
        return

    pane.clear(projection = '3d')
    ax = pane.axes

    theta = np.linspace(0.0, np.radians(data.sweepDeg), 60)
    thetaGrid, xGrid = np.meshgrid(theta, data.x)
    rGrid = np.tile(data.r.reshape(-1, 1), (1, theta.size))

    ax.plot_surface(xGrid, rGrid * np.cos(thetaGrid), rGrid * np.sin(thetaGrid),
                    color = themeColors.accent, alpha = 0.28, linewidth = 0,
                    antialiased = True, shade = True)

    if data.channelX.size:
        lines = data.channelX.reshape(data.channelX.shape[0], -1) if data.channelX.ndim > 1 \
            else data.channelX.reshape(1, -1)
        yLines = data.channelY.reshape(lines.shape)
        zLines = data.channelZ.reshape(lines.shape)
        for index in range(lines.shape[0]):
            ax.plot(lines[index], yLines[index], zLines[index],
                    color = themeColors.blue, linewidth = 0.8)

    ax.set_xlabel('Axis [m]')
    ax.set_ylabel('Y [m]')
    ax.set_zlabel('Z [m]')
    ax.set_title(data.title, color = themeColors.text)
    try:
        ax.set_box_aspect((np.ptp(data.x) or 1.0, 2 * data.r.max(), 2 * data.r.max()))
    except Exception:
        pass
    pane.redraw()

def drawPlume(pane, nozzle) -> None:

    '''

    The nozzle and its plume as one Mach field, the picture the GUI's icon is drawn from: the
    chamber's one-dimensional answer, the characteristic mesh to the exit plane and the station
    march past it, shaded on the steel ramp inside the wall and the solved plume boundary, the plume
    fading out where the march ends. The scale spans the supersonic flow, so the chamber sits at its
    bottom color. Where the march did not solve, the correlated plume structure is drawn instead.

    '''

    scene = backend.figuresModule().plumeSceneFigure(nozzle)
    if scene is not None:
        _drawPlumeScene(pane, scene)
        return
    _drawCorrelatedPlume(pane, nozzle)

def _drawPlumeScene(pane, scene) -> None:

    '''The solved scene: one field from the injector face to the end of the march.'''

    from matplotlib.colors import to_rgba

    pane.clear(projection = None)
    ax = pane.axes
    ax.grid(False)

    # The wall and the boundary as one closed outline, injector face to the end of the march
    upperX = np.concatenate([scene.wallX, scene.boundaryX])
    upperR = np.concatenate([scene.wallR, scene.boundaryR])
    outline = np.column_stack([np.concatenate([upperX, upperX[::-1]]), np.concatenate([upperR, -upperR[::-1]])])

    levels = np.linspace(scene.machRange[0], scene.machRange[1], 120)
    shading = ax.tricontourf(np.concatenate([scene.nodeX, scene.nodeX]), np.concatenate([scene.nodeR, -scene.nodeR]),
                             np.concatenate([scene.nodeMach, scene.nodeMach]), levels = levels,
                             cmap = _palette().colormap('mach', themeColors.mode), extend = 'both')
    _clipTo(ax, shading, outline)

    for sign in (1.0, -1.0):
        ax.plot(scene.boundaryX, sign * scene.boundaryR, color = themeColors.yellow, linewidth = 1.4, alpha = 0.9,
                label = 'Plume boundary, solved' if sign > 0 else None)
        ax.plot(scene.wallX, sign * scene.wallR, color = themeColors.accent, linewidth = 2.0, solid_capstyle = 'round',
                label = 'Nozzle wall' if sign > 0 else None)

    # Framed on the nozzle and the march, and faded out over the last half lip radius of it, so no
    # edge is left standing where the solve stops
    start = float(np.min(scene.wallX))
    end = scene.lipX + scene.reach * scene.lipRadius
    halfHeight = 1.12 * max(float(np.max(np.abs(scene.boundaryR))), float(np.max(scene.wallR)))
    fadeStart = end - 0.5 * scene.lipRadius
    ramp = np.linspace(0.0, 1.0, 64)
    ramp = ramp * ramp * (3.0 - 2.0 * ramp)
    fade = np.zeros((1, ramp.size, 4))
    fade[..., :3] = to_rgba(ax.get_facecolor())[:3]
    fade[..., 3] = ramp
    ax.imshow(fade, extent = (fadeStart, end, -halfHeight, halfHeight), aspect = 'auto', zorder = 5,
              interpolation = 'bilinear')

    ax.set_xlim(start, end)
    ax.set_ylim(-halfHeight, halfHeight)
    ax.set_aspect('equal', adjustable = 'box')
    ax.set_xlabel('Nozzle axis [m]')
    ax.set_ylabel('Radius [m]')

    # The drift belongs on the figure whatever its value: it separates a plume worth reading from one
    # that is merely drawn
    verdict = 'conserves mass' if scene.trustworthy else 'does not conserve mass; shorten the reach'
    heading = (f'Nozzle and plume at {scene.ambientPressure / 1e3:.2f} kPa ambient, lip pressure ratio '
               f'{scene.lipPressureRatio:.2f}\nmarched {scene.reach:.1f} lip radii, mass continuity error '
               f'{scene.massDriftWorst:+.2f} %: {verdict}')
    beyond = []
    if scene.machDiskPresent and scene.machDiskX > end:
        beyond.append(f'Mach disk (x = {scene.machDiskX:.2f} m)')
    if np.size(scene.cellX) and float(np.max(scene.cellX)) > end:
        beyond.append('shock cells')
    if beyond:
        heading += '\nThe correlated ' + ' and '.join(beyond) + ' lie beyond the march; the interactive view shows them'
    ax.set_title(heading, color = themeColors.text, fontsize = 10)
    _colorbar(pane, shading, ax, 'Mach number [-]')
    _legend(ax, loc = 'upper left')
    pane.redraw()

def _drawCorrelatedPlume(pane, nozzle) -> None:

    '''

    The correlated plume structure against the nozzle contour, for a run whose march did not solve:
    the correlated boundary over its whole length, the shock cells and the Mach disk.

    '''

    data = backend.figuresModule().plumeFigure(nozzle)
    if data is None:
        pane.message('No plume was computed. Set a plume ambient pressure in the Design form and re-run.')
        return

    pane.clear(projection = None)
    ax = pane.axes

    solved = data.boundarySource == 'marched'

    # The station march leaves unstructured nodes, which tricontourf takes directly. The solve is
    # one half plane, so it is mirrored before contouring.
    if solved and data.fieldX.size > 3:
        ax.grid(False)
        shading = ax.tricontourf(np.concatenate([data.fieldX, data.fieldX]),
                                 np.concatenate([data.fieldR, -data.fieldR]),
                                 np.concatenate([data.fieldMach, data.fieldMach]),
                                 levels = 60, cmap = _palette().colormap('mach', themeColors.mode))
        _colorbar(pane, shading, ax, 'Mach number [-]')

    if data.wallX.size:
        ax.plot(data.wallX, data.wallR, color = themeColors.accent, linewidth = 1.8, label = 'Nozzle wall')
        ax.plot(data.wallX, -data.wallR, color = themeColors.accent, linewidth = 1.8)

    label = 'Plume boundary, solved' if solved else 'Plume boundary, correlated'
    for sign in (1.0, -1.0):
        ax.plot(data.boundaryX, sign * data.boundaryR, color = themeColors.yellow, linewidth = 1.6,
                linestyle = '-' if solved else ':', label = label if sign > 0 else None)

    for index, cellPosition in enumerate(np.asarray(data.cellX, dtype = float)):
        ax.axvline(cellPosition, color = themeColors.textDim, linewidth = 0.7, linestyle = '--',
                   label = 'Shock cells' if index == 0 else None)

    if data.machDiskPresent and data.machDiskDiameter > 0.0:
        halfHeight = data.machDiskDiameter / 2.0
        ax.plot([data.machDiskX, data.machDiskX], [-halfHeight, halfHeight],
                color = themeColors.orange, linewidth = 3.5,
                label = f'Mach disk, {data.machDiskDiameter * 1e3:.0f} mm across')

    # The drift belongs on the figure whatever its value, because it is what separates a plume
    # shape worth reading from one that is merely drawn.
    heading = f'{data.title}' + '\n' + f'{data.summary}'
    if solved and np.isfinite(data.massDriftWorst):
        verdict = ('conserves mass over this reach' if data.trustworthy
                   else 'does not conserve mass over this reach; shorten it')
        heading += (f'\nmass continuity error {data.massDriftWorst:+.2f} % over '
                    f'{data.reachMarched:.1f} lip radii  --  {verdict}')

    # Framed on the solved part: the correlated cells and Mach disk of a strongly underexpanded jet
    # lie many lip radii downstream, and fitting them in shrinks the solved field to a sliver
    if solved and data.fieldX.size > 3:
        start = float(np.min(data.wallX)) if data.wallX.size else float(np.min(data.fieldX))
        end = float(np.max(data.fieldX))
        end += 0.15 * (end - start)
        beyond = []
        if data.machDiskPresent and data.machDiskX > end:
            beyond.append(f'Mach disk at x = {data.machDiskX:.2f} m')
        if np.size(data.cellX) and float(np.max(data.cellX)) > end:
            beyond.append('shock cells')
        if beyond:
            heading += '\n' + ' and '.join(beyond) + ' lie beyond the marched reach; the interactive view shows them'
        halfHeight = 1.25 * max(float(np.max(np.abs(data.boundaryR))) if np.size(data.boundaryR) else 0.0,
                                float(np.max(data.wallR)) if data.wallX.size else 0.0)
        ax.set_xlim(start, end)
        ax.set_ylim(-halfHeight, halfHeight)
        ax.set_aspect('equal', adjustable = 'box')
    else:
        ax.set_aspect('equal', adjustable = 'datalim')

    ax.set_title(heading, color = themeColors.text, fontsize = 10)
    ax.set_xlabel('Nozzle axis [m]')
    ax.set_ylabel('Radius [m]')
    _legend(ax, loc = 'upper left')
    pane.redraw()

#--------------------------------------------------------------------------------------------------------------------------#
# -- Interactive companion -- #
#--------------------------------------------------------------------------------------------------------------------------#

# View key -> (extractor, renderer): the figures.py extractor that describes the view from a Nozzle,
# and the renderer that draws that description with plotly. The flow fields are filled, as the
# static view shades them.
figureDescriptions = {
    'contour':     (lambda module, nozzle: module.contourFigure(nozzle), lambda module, data: module.plotlyContour(data)),
    'nearWall':    (lambda module, nozzle: module.nearWallFigure(nozzle), lambda module, data: module.plotlyNearWall(data)),
    'revolved':    (lambda module, nozzle: module.revolvedFigure(nozzle), lambda module, data: module.plotlyRevolved(data)),
    'mach':        (lambda module, nozzle: module.stitchedFieldFigure(nozzle, 'mach'),
                    lambda module, data: module.plotlyField(data, filled = True)),
    'pressure':    (lambda module, nozzle: module.stitchedFieldFigure(nozzle, 'pressure'),
                    lambda module, data: module.plotlyField(data, filled = True)),
    'temperature': (lambda module, nozzle: module.stitchedFieldFigure(nozzle, 'temperature'),
                    lambda module, data: module.plotlyField(data, filled = True)),
    'plume':       (lambda module, nozzle: module.plumeFigure(nozzle), lambda module, data: _framedPlume(module, data)),
}

def _framedPlume(module, data):

    '''

    The interactive plume, opened on the frame the static drawing uses: the nozzle and the marched
    plume. The figure itself takes in every correlated shock cell, many lip radii past the march;
    zooming out or a double click shows them.

    '''

    figure = module.plotlyPlume(data)
    stations = np.asarray(getattr(data, 'fieldX', []), dtype = float)
    wall = np.asarray(getattr(data, 'wallX', []), dtype = float)
    if figure is not None and stations.size and wall.size:
        figure.update_xaxes(range = [float(np.min(wall)), float(np.max(stations))])
    return figure

# The views whose description is settled once a run's contour stage ends: the web front end draws
# them from that description while cooling and the plume still run
contourStageViews = ('contour', 'nearWall', 'mach', 'pressure', 'temperature', 'revolved')

def _described(key: str):

    '''A builder `(figuresModule, nozzle) -> Figure or None` that renders the view's description.'''

    extract, render = figureDescriptions[key]

    def build(module, nozzle):
        data = extract(module, nozzle)
        return render(module, data) if data is not None else None

    return build

# View key -> the builder that renders it with plotly, `(figuresModule, nozzle) -> Figure or None`
interactiveBuilders = {key: _described(key) for key in figureDescriptions}
interactiveBuilders.update({
    'channelMesh': lambda module, nozzle: module.channelMeshFigure(nozzle),
    'volute':      lambda module, nozzle: module.volutesFigure(nozzle),
})
