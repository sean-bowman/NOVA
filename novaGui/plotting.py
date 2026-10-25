
# -- NOVA GUI Embedded Matplotlib Helpers -- #

'''

A themed Matplotlib figure embedded in a Tk frame, plus the draw routines the View tab uses.
Matplotlib is imported here rather than in widgets.py so the main window can open before the
scientific stack is touched.

The renderers take figure descriptions from NOVA.figures, which also carries a plotly renderer for
the same descriptions. Matplotlib draws the inline pane because it draws into a Tk canvas; plotly
draws the interactive companion opened in a browser, which it does far better and which Tk cannot
host. Neither view can drift from the other, because both read one description.

Colors come from the active theme mode, and fields use NOVA.palette's colormaps in the same mode,
so the inline pane, the saved figures and the interactive views are one palette. A pane remembers
the last thing it drew and draws it again when the mode changes.

Author: Sean Bowman
Date:   08/28/2026

'''

import numpy as np
import tkinter as tk
from tkinter import ttk

import matplotlib
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from . import theme
from . import backend

matplotlib.rcParams.update(theme.matplotlibRcParams())

class _Toolbar(NavigationToolbar2Tk):

    '''

    Matplotlib's navigation toolbar without the history arrows. Tk draws a disabled image button
    under a stipple that shows as a checkered square on the dark theme, and an inline pane that is
    redrawn whole on every view change has little history to step through.

    '''

    toolitems = tuple(item for item in NavigationToolbar2Tk.toolitems
                      if item[0] in ('Home', None, 'Pan', 'Zoom', 'Save'))

def _palette():

    '''NOVA.palette, set to the GUI's mode, for the field colormaps.'''

    palette = backend.figuresModule().figurePalette
    palette.setFigureMode(theme.mode)

    return palette

class MplPane(ttk.Frame):

    '''

    A Matplotlib figure on a themed Tk canvas with an optional navigation toolbar. Draw through
    `render(drawFunction, *arguments)`, which also records the call so a change of theme mode can
    repeat it in the new colors.

    '''

    def __init__(self, master, toolbar: bool = True, projection: str = None):

        super().__init__(master, style = 'Surface.TFrame')

        # Render at the display DPI so embedded text and lines are crisp rather than a 96 dpi
        # bitmap stretched by the compositor.
        self.figure = Figure(figsize = (7.5, 5.0), dpi = theme.scaled(100))
        self._projection = projection
        self.axes = self.figure.add_subplot(111, projection = projection)
        self._lastDraw = None
        self._rendering = False

        self._canvas = FigureCanvasTkAgg(self.figure, master = self)
        self._canvas.get_tk_widget().configure(highlightthickness = 0)
        self._canvas.get_tk_widget().pack(side = 'top', fill = 'both', expand = True)

        self._toolbar = None
        if toolbar:
            self._toolbar = _Toolbar(self._canvas, self, pack_toolbar = False)
            self._toolbar.pack(side = 'bottom', fill = 'x')

        self._restyle(redrawLast = False)
        theme.addListener(self._restyle)
        self.clear()

    def _restyle(self, redrawLast: bool = True) -> None:

        '''Recolor the figure, canvas and toolbar for the active mode, then repeat the last draw.'''

        self.figure.patch.set_facecolor(theme.surface)
        self._canvas.get_tk_widget().configure(bg = theme.surface)
        if self._toolbar is not None:
            self._toolbar.configure(bg = theme.surface)
            for child in self._toolbar.winfo_children():
                for option, value in (('bg', theme.surface), ('fg', theme.textMuted),
                                      ('activebackground', theme.surface2), ('highlightbackground', theme.surface),
                                      ('selectcolor', theme.surface2)):
                    try:
                        child.configure(**{option: value})
                    except tk.TclError:
                        pass
            # The toolbar picks dark or light icons from its background when it builds them
            try:
                self._toolbar._rescale()
            except Exception:                              # noqa: BLE001 -- a private hook; cosmetic only
                pass

        if redrawLast and self._lastDraw is not None:
            function, arguments = self._lastDraw
            self.render(function, *arguments)
        else:
            for axes in self.figure.get_axes():
                theme.styleAxes(axes)
            self.redraw()

    def render(self, function, *arguments) -> None:

        '''

        Draw `function(self, *arguments)` and remember it, so a change of mode can draw it again.

        '''

        self._lastDraw = (function, arguments)
        self._rendering = True
        try:
            function(self, *arguments)
        finally:
            self._rendering = False

    def clear(self, projection: str = 'keep') -> None:

        '''

        Reset to a single empty themed axes. Pass a projection to switch between 2D and 3D without
        rebuilding the pane.

        '''

        if projection != 'keep' and projection != self._projection:
            self._projection = projection
        self.figure.clear()
        self.figure.set_layout_engine('constrained')
        self.axes = self.figure.add_subplot(111, projection = self._projection)
        theme.styleAxes(self.axes)
        if self._projection == '3d':
            self._style3d()

    def _style3d(self) -> None:

        from matplotlib.colors import to_rgba

        ax = self.axes
        try:
            ax.set_facecolor(theme.surface)
            for pane in (ax.xaxis, ax.yaxis, ax.zaxis):
                pane.set_pane_color(to_rgba(theme.bg))
                pane.line.set_color(theme.border)
            ax.zaxis.label.set_color(theme.text)
            ax.tick_params(colors = theme.textMuted)
        except Exception:
            pass

    def message(self, text: str) -> None:

        '''

        Replace the plot with a centered note.

        '''

        if not self._rendering:
            self._lastDraw = None
        self.clear(projection = None)
        self.axes.set_axis_off()
        self.axes.text(0.5, 0.5, text, ha = 'center', va = 'center',
                       color = theme.textMuted, fontsize = 11, wrap = True,
                       transform = self.axes.transAxes)
        self.redraw()

    def showImage(self, imagePath: str, title: str = '') -> None:

        '''

        Display a saved figure file, scaled to fit, with pan and zoom.

        '''

        import matplotlib.image as mpimg

        self.clear(projection = None)
        self.figure.set_layout_engine('none')
        self.axes.set_axis_off()
        self.axes.imshow(mpimg.imread(imagePath))
        # The exported figure already carries its own title and margins, so give it the whole
        # canvas instead of nesting it inside a second set of axes margins.
        self.axes.set_position([0.0, 0.0, 1.0, 1.0])
        self.figure.subplots_adjust(left = 0.0, right = 1.0, bottom = 0.0, top = 1.0)
        self.redraw()

    def redraw(self) -> None:

        self._canvas.draw_idle()

def _legend(ax, **options) -> None:

    ax.legend(facecolor = theme.surface2, edgecolor = theme.border, labelcolor = theme.text,
              fontsize = 8, **options)

def _colorbar(pane: MplPane, mappable, ax, label: str) -> None:

    '''A horizontal color bar under a wide axisymmetric plot, styled for the mode.'''

    from matplotlib.ticker import MaxNLocator

    bar = pane.figure.colorbar(mappable, ax = ax, orientation = 'horizontal', fraction = 0.05, pad = 0.10)
    bar.set_label(label, color = theme.text)
    bar.outline.set_edgecolor(theme.border)
    bar.ax.tick_params(colors = theme.textMuted)
    # Round ticks rather than the contour levels, which land on unreadable values
    low, high = mappable.norm.vmin, mappable.norm.vmax
    if low is not None and high is not None and high > low:
        ticks = MaxNLocator(7).tick_values(low, high)
        bar.set_ticks(ticks[(ticks >= low) & (ticks <= high)])

#--------------------------------------------------------------------------------------------------------------------------#
# -- Matplotlib renderers -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawContour(pane: MplPane, nozzle) -> None:

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

    ax.plot(data.x, data.r, color = theme.accent, linewidth = 1.8, label = 'Wall contour')
    ax.plot(data.x, -data.r, color = theme.accent, linewidth = 1.8)
    ax.fill_between(data.x, data.r, -data.r, color = theme.accent, alpha = 0.06)

    if data.xRegen.size:
        ax.plot(data.xRegen, data.rRegen, color = theme.blue, linewidth = 2.2,
                label = 'Regen-cooled portion')
        ax.plot(data.xRegen, -data.rRegen, color = theme.blue, linewidth = 2.2)

    ax.axvline(data.throatX, color = theme.textDim, linewidth = 0.8, linestyle = '--')
    ax.annotate(f'throat r = {data.throatRadius * 1e3:.1f} mm',
                xy = (data.throatX, data.throatRadius),
                xytext = (10, 16), textcoords = 'offset points',
                color = theme.textMuted, fontsize = 8)
    ax.annotate(f'exit r = {data.exitRadius * 1e3:.1f} mm',
                xy = (data.x[-1], data.exitRadius),
                xytext = (-40, 12), textcoords = 'offset points',
                color = theme.textMuted, fontsize = 8)

    ax.set_title(f'{data.title}   (length {data.length * 1e3:.0f} mm)', color = theme.text)
    ax.set_xlabel('Nozzle axis [m]')
    ax.set_ylabel('Radius [m]')
    ax.set_aspect('equal', adjustable = 'datalim')
    _legend(ax)
    pane.redraw()

def drawNearWall(pane: MplPane, nozzle) -> None:

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
        theme.styleAxes(ax)

    axT.plot(data.axis, data.temperature, color = theme.accent)
    axT.set_ylabel('T [K]')
    axT.set_title(data.title, color = theme.text)

    axP.plot(data.axis, data.pressure / 1e5, color = theme.blue)
    axP.set_ylabel('P [bar]')

    axM.plot(data.axis, data.mach, color = theme.cyan)
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

def drawField(pane: MplPane, nozzle, quantity: str) -> None:

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
    cmap = _palette().colormap(data.colorscale, theme.mode)

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
        ax.plot(data.wallX, sign * np.asarray(data.wallR), color = theme.accent, linewidth = 1.6)

    # The seam, marked rather than blended
    span = float(np.max(data.wallR))
    ax.axvline(data.throatX, color = theme.text, linewidth = 0.9, linestyle = '--', alpha = 0.6)
    offset = 0.012 * (data.exitX - float(np.min(data.wallX)))
    ax.text(data.throatX - offset, 0.88 * span, 'one dimensional', color = theme.textMuted, fontsize = 8,
            ha = 'right', style = 'italic')
    ax.text(data.throatX + offset, 0.88 * span, 'characteristics', color = theme.textMuted, fontsize = 8,
            ha = 'left', style = 'italic')

    ax.set_xlim(float(np.min(data.wallX)), data.exitX)
    ax.set_ylim(-1.08 * span, 1.08 * span)
    ax.set_title(data.title, color = theme.text)
    ax.set_xlabel('Nozzle axis [m]')
    ax.set_ylabel('Radius [m]')
    ax.set_aspect('equal', adjustable = 'box')
    if shading is not None:
        bar = pane.figure.colorbar(shading, ax = ax, orientation = 'horizontal', fraction = 0.05, pad = 0.10)
        bar.set_label(label, color = theme.text)
        bar.outline.set_edgecolor(theme.border)
        bar.ax.tick_params(colors = theme.textMuted)
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

def drawRevolvedContour(pane: MplPane, nozzle, sweepDeg: float = 300.0) -> None:

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
                    color = theme.accent, alpha = 0.28, linewidth = 0,
                    antialiased = True, shade = True)

    if data.channelX.size:
        lines = data.channelX.reshape(data.channelX.shape[0], -1) if data.channelX.ndim > 1 \
            else data.channelX.reshape(1, -1)
        yLines = data.channelY.reshape(lines.shape)
        zLines = data.channelZ.reshape(lines.shape)
        for index in range(lines.shape[0]):
            ax.plot(lines[index], yLines[index], zLines[index],
                    color = theme.blue, linewidth = 0.8)

    ax.set_xlabel('Axis [m]')
    ax.set_ylabel('Y [m]')
    ax.set_zlabel('Z [m]')
    ax.set_title(data.title, color = theme.text)
    try:
        ax.set_box_aspect((np.ptp(data.x) or 1.0, 2 * data.r.max(), 2 * data.r.max()))
    except Exception:
        pass
    pane.redraw()

def drawPlume(pane: MplPane, nozzle) -> None:

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

def _drawPlumeScene(pane: MplPane, scene) -> None:

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
                             cmap = _palette().colormap('mach', theme.mode), extend = 'both')
    _clipTo(ax, shading, outline)

    for sign in (1.0, -1.0):
        ax.plot(scene.boundaryX, sign * scene.boundaryR, color = theme.yellow, linewidth = 1.4, alpha = 0.9,
                label = 'Plume boundary, solved' if sign > 0 else None)
        ax.plot(scene.wallX, sign * scene.wallR, color = theme.accent, linewidth = 2.0, solid_capstyle = 'round',
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
        heading += '\nThe correlated ' + ' and '.join(beyond) + ' lie beyond the march; Open interactive shows them'
    ax.set_title(heading, color = theme.text, fontsize = 10)
    _colorbar(pane, shading, ax, 'Mach number [-]')
    _legend(ax, loc = 'upper left')
    pane.redraw()

def _drawCorrelatedPlume(pane: MplPane, nozzle) -> None:

    '''

    The correlated plume structure against the nozzle contour, for a run whose march did not solve:
    the correlated boundary over its whole length, the shock cells and the Mach disk.

    '''

    data = backend.figuresModule().plumeFigure(nozzle)
    if data is None:
        pane.message('No plume was computed. Set a plume ambient pressure on the Design tab and re-run.')
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
                                 levels = 60, cmap = _palette().colormap('mach', theme.mode))
        _colorbar(pane, shading, ax, 'Mach number [-]')

    if data.wallX.size:
        ax.plot(data.wallX, data.wallR, color = theme.accent, linewidth = 1.8, label = 'Nozzle wall')
        ax.plot(data.wallX, -data.wallR, color = theme.accent, linewidth = 1.8)

    label = 'Plume boundary, solved' if solved else 'Plume boundary, correlated'
    for sign in (1.0, -1.0):
        ax.plot(data.boundaryX, sign * data.boundaryR, color = theme.yellow, linewidth = 1.6,
                linestyle = '-' if solved else ':', label = label if sign > 0 else None)

    for index, cellPosition in enumerate(np.asarray(data.cellX, dtype = float)):
        ax.axvline(cellPosition, color = theme.textDim, linewidth = 0.7, linestyle = '--',
                   label = 'Shock cells' if index == 0 else None)

    if data.machDiskPresent and data.machDiskDiameter > 0.0:
        halfHeight = data.machDiskDiameter / 2.0
        ax.plot([data.machDiskX, data.machDiskX], [-halfHeight, halfHeight],
                color = theme.orange, linewidth = 3.5,
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
            heading += '\n' + ' and '.join(beyond) + ' lie beyond the marched reach; Open interactive shows them'
        halfHeight = 1.25 * max(float(np.max(np.abs(data.boundaryR))) if np.size(data.boundaryR) else 0.0,
                                float(np.max(data.wallR)) if data.wallX.size else 0.0)
        ax.set_xlim(start, end)
        ax.set_ylim(-halfHeight, halfHeight)
        ax.set_aspect('equal', adjustable = 'box')
    else:
        ax.set_aspect('equal', adjustable = 'datalim')

    ax.set_title(heading, color = theme.text, fontsize = 10)
    ax.set_xlabel('Nozzle axis [m]')
    ax.set_ylabel('Radius [m]')
    _legend(ax, loc = 'upper left')
    pane.redraw()

def drawPlotly3d(pane: MplPane, figure, maximumGrid: int = 60) -> None:

    '''

    A plotly 3D figure redrawn in Matplotlib, for the views Tk cannot host: surfaces as flat
    shaded meshes, decimated to at most `maximumGrid` rows and columns so a dense channel mesh
    stays responsive, and line traces as lines.

    '''

    if figure is None:
        pane.message('This view was not built for this run.')
        return

    from matplotlib.colors import to_rgba

    def colorOf(value, fallback):
        if isinstance(value, str) and value.startswith('rgb'):
            numbers = [float(part) for part in value[value.index('(') + 1:value.index(')')].split(',')[:3]]
            return tuple(number / 255.0 for number in numbers)
        try:
            return to_rgba(value)
        except (TypeError, ValueError):
            return fallback

    pane.clear(projection = '3d')
    ax = pane.axes

    # Matplotlib sorts whole surfaces by mean depth rather than pixel by pixel, so a translucent
    # shell around a part (the cold wall around the channels) is often drawn over all of it.
    # Shells are drawn first and faded further, opaque parts over them, lines over both.
    ax.computed_zorder = False
    shellFade = 0.35
    spans = []
    for trace in figure.data:
        kind = getattr(trace, 'type', '')
        if kind == 'surface' and trace.x is not None:
            x, y, z = (np.asarray(value, dtype = float) for value in (trace.x, trace.y, trace.z))
            if x.ndim != 2:
                continue
            step = max(1, int(np.ceil(max(x.shape) / maximumGrid)))
            scale = trace.colorscale
            color = colorOf(scale[0][1], theme.textMuted) if scale else theme.textMuted
            opacity = float(trace.opacity if trace.opacity is not None else 1.0)
            shell = opacity < 0.95
            ax.plot_surface(x[::step, ::step], y[::step, ::step], z[::step, ::step], color = color,
                            alpha = shellFade * opacity if shell else opacity, zorder = 1 if shell else 2,
                            linewidth = 0, antialiased = True, shade = True)
            spans.append((x, y, z))
        elif kind == 'scatter3d' and trace.x is not None:
            line = getattr(trace, 'line', None)
            color = colorOf(getattr(line, 'color', None), theme.textMuted)
            ax.plot(np.asarray(trace.x, dtype = float), np.asarray(trace.y, dtype = float),
                    np.asarray(trace.z, dtype = float), color = color, linewidth = 0.8, zorder = 3)

    if spans:
        try:
            ranges = [max(np.nanmax(part[index]) for part in spans) - min(np.nanmin(part[index]) for part in spans)
                      for index in range(3)]
            ax.set_box_aspect(tuple(value or 1.0 for value in ranges))
        except Exception:                                  # noqa: BLE001 -- the default aspect still draws
            pass

    title = getattr(getattr(figure.layout, 'title', None), 'text', '') or ''
    ax.set_title(title, color = theme.text)
    pane.redraw()

#--------------------------------------------------------------------------------------------------------------------------#
# -- Interactive companion -- #
#--------------------------------------------------------------------------------------------------------------------------#

# View key -> the figures.py builder that renders the same description with plotly.
interactiveBuilders = {
    'contour':     lambda module, nozzle: module.plotlyContour(module.contourFigure(nozzle)),
    'nearWall':    lambda module, nozzle: module.plotlyNearWall(module.nearWallFigure(nozzle)),
    'revolved':    lambda module, nozzle: module.plotlyRevolved(module.revolvedFigure(nozzle)),
    'mach':        lambda module, nozzle: module.plotlyField(module.fieldFigure(nozzle, 'mach')),
    'pressure':    lambda module, nozzle: module.plotlyField(module.fieldFigure(nozzle, 'pressure')),
    'temperature': lambda module, nozzle: module.plotlyField(module.fieldFigure(nozzle, 'temperature')),
    'plume':       lambda module, nozzle: module.plotlyPlume(module.plumeFigure(nozzle)),
    'channelMesh': lambda module, nozzle: module.channelMeshFigure(nozzle),
    'volute':      lambda module, nozzle: module.volutesFigure(nozzle),
}

def openInteractive(nozzle, view: str, folder: str) -> str:

    '''

    Render a view with plotly in the GUI's mode, write it beside the run output and open it in the
    system browser.

    Parameters:
    -----------
    nozzle : Nozzle
        The generated nozzle
    view : str
        A key of interactiveBuilders
    folder : str
        Destination directory for the HTML file

    Returns:
    --------
    str : the path written, or None when the view has no data

    '''

    import os
    import webbrowser

    figuresModule = backend.figuresModule()
    if view not in interactiveBuilders:
        return None

    _palette()
    figure = interactiveBuilders[view](figuresModule, nozzle)
    if figure is None:
        return None

    os.makedirs(folder, exist_ok = True)
    path = os.path.join(folder, f'{view}Interactive.html')
    figuresModule.writeInteractiveFigure(figure, path)
    webbrowser.open('file:///' + os.path.abspath(path).replace(os.sep, '/'))
    return path

def openFile(path: str) -> None:

    '''Open a file the run already wrote in the system browser.'''

    import os
    import webbrowser

    webbrowser.open('file:///' + os.path.abspath(path).replace(os.sep, '/'))
