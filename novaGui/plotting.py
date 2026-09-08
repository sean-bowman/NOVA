# -- NOVA GUI Embedded Matplotlib Helpers -- #

'''

Thin wrapper around a themed Matplotlib figure embedded in a Tk frame, plus the
draw routines the geometry and analysis tabs share. Matplotlib is imported here
rather than in widgets.py so the main window can open before the scientific
stack is touched.

The renderers take figure descriptions from NOVA.figures, which also
carries a plotly renderer for the same descriptions. Matplotlib draws the inline
pane because it is always installed and draws into a Tk canvas; plotly draws the
interactive companion opened in a browser, which it does far better and which Tk
cannot host. Neither view can drift from the other, because both read one
description.

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

class MplPane(ttk.Frame):

    '''

    A Matplotlib figure on a themed Tk canvas with an optional navigation
    toolbar. Call `.figure` to draw, then `.redraw()`.

    '''

    def __init__(self, master, toolbar: bool = True, projection: str = None):

        super().__init__(master, style = 'Surface.TFrame')

        # Render at the display DPI so embedded text and lines are crisp rather than
        # a 96 dpi bitmap stretched by the compositor.
        self.figure = Figure(figsize = (7.5, 5.0), dpi = theme.scaled(100))
        self.figure.patch.set_facecolor(theme.surface)
        self._projection = projection
        self.axes = self.figure.add_subplot(111, projection = projection)

        self._canvas = FigureCanvasTkAgg(self.figure, master = self)
        self._canvas.get_tk_widget().configure(bg = theme.surface, highlightthickness = 0)
        self._canvas.get_tk_widget().pack(side = 'top', fill = 'both', expand = True)

        if toolbar:
            bar = NavigationToolbar2Tk(self._canvas, self, pack_toolbar = False)
            bar.configure(bg = theme.surface2)
            for child in bar.winfo_children():
                try:
                    child.configure(bg = theme.surface2)
                except tk.TclError:
                    pass
            bar.update()
            bar.pack(side = 'bottom', fill = 'x')

        self.clear()

    def clear(self, projection: str = 'keep') -> None:

        '''

        Reset to a single empty themed axes. Pass a projection to switch between
        2D and 3D without rebuilding the pane.

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

        ax = self.axes
        try:
            ax.set_facecolor(theme.surface)
            for pane in (ax.xaxis, ax.yaxis, ax.zaxis):
                pane.set_pane_color((0.10, 0.12, 0.16, 1.0))
                pane.line.set_color(theme.border)
            ax.zaxis.label.set_color(theme.text)
            ax.tick_params(colors = theme.textMuted)
        except Exception:
            pass

    def message(self, text: str) -> None:

        '''

        Replace the plot with a centred note.

        '''

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

#--------------------------------------------------------------------------------------------------------------------------#
# -- Matplotlib renderers -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawContour(pane: MplPane, nozzle) -> None:

    '''

    Full nozzle contour: converging section, throat, diverging wall, and the regen / extension
    split when the contour was truncated. Mirrored about the axis with key radii and the
    overall length annotated.

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
        ax.plot(data.xRegen, data.rRegen, color = theme.green, linewidth = 2.2,
                label = 'Regen-cooled portion')
        ax.plot(data.xRegen, -data.rRegen, color = theme.green, linewidth = 2.2)

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
    ax.legend(facecolor = theme.surface2, edgecolor = theme.border,
              labelcolor = theme.text, fontsize = 8)
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

    axM.plot(data.axis, data.mach, color = theme.green)
    axM.set_ylabel('Mach [-]')
    axM.set_xlabel('Nozzle axis [m]')

    for ax in (axT, axP):
        ax.tick_params(labelbottom = False)

    pane.axes = axM
    pane.redraw()

def drawRevolvedContour(pane: MplPane, nozzle, sweepDeg: float = 300.0) -> None:

    '''

    Surface-of-revolution view of the wall contour, with the cooling channel centrelines
    overlaid when a jacket was generated. This is a fast orientation view; the interactive
    export carries the full meshes.

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
            ax.plot(np.abs(lines[index]), yLines[index], zLines[index],
                    color = theme.green, linewidth = 0.8)

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

    Exhaust plume structure against the nozzle contour: correlated jet boundary, shock cell
    positions and the Mach disk when the pressure ratio produces one. The plume interior is not
    a field and is deliberately not shaded.

    '''

    data = backend.figuresModule().plumeFigure(nozzle)
    if data is None:
        pane.message('No plume was computed. Set a plume ambient pressure in the config and re-run.')
        return

    pane.clear(projection = None)
    ax = pane.axes

    if data.wallX.size:
        ax.plot(data.wallX, data.wallR, color = theme.accent, linewidth = 1.8, label = 'Nozzle wall')
        ax.plot(data.wallX, -data.wallR, color = theme.accent, linewidth = 1.8)

    ax.plot(data.boundaryX, data.boundaryR, color = theme.blue, linewidth = 1.6,
            linestyle = ':', label = 'Plume boundary')
    ax.plot(data.boundaryX, -data.boundaryR, color = theme.blue, linewidth = 1.6, linestyle = ':')
    ax.fill_between(data.boundaryX, data.boundaryR, -data.boundaryR,
                    color = theme.blue, alpha = 0.05)

    for index, cellPosition in enumerate(np.asarray(data.cellX, dtype = float)):
        ax.axvline(cellPosition, color = theme.textDim, linewidth = 0.7, linestyle = '--',
                   label = 'Shock cells' if index == 0 else None)

    if data.machDiskPresent and data.machDiskDiameter > 0.0:
        halfHeight = data.machDiskDiameter / 2.0
        ax.plot([data.machDiskX, data.machDiskX], [-halfHeight, halfHeight],
                color = theme.green, linewidth = 3.5,
                label = f'Mach disk ({data.machDiskDiameter * 1e3:.0f} mm)')

    ax.set_title(f'{data.title}' + '\n' + f'{data.summary}',
                 color = theme.text, fontsize = 10)
    ax.set_xlabel('Nozzle axis [m]')
    ax.set_ylabel('Radius [m]')
    ax.set_aspect('equal', adjustable = 'datalim')
    ax.legend(facecolor = theme.surface2, edgecolor = theme.border,
              labelcolor = theme.text, fontsize = 8, loc = 'upper left')
    pane.redraw()

#--------------------------------------------------------------------------------------------------------------------------#
# -- Interactive companion -- #
#--------------------------------------------------------------------------------------------------------------------------#

# GUI view name -> the figures.py builder that renders the same description with plotly.
interactiveBuilders = {
    'contour':     lambda module, nozzle: module.plotlyContour(module.contourFigure(nozzle)),
    'nearWall':    lambda module, nozzle: module.plotlyNearWall(module.nearWallFigure(nozzle)),
    'revolved':    lambda module, nozzle: module.plotlyRevolved(module.revolvedFigure(nozzle)),
    'mach':        lambda module, nozzle: module.plotlyField(module.fieldFigure(nozzle, 'mach')),
    'pressure':    lambda module, nozzle: module.plotlyField(module.fieldFigure(nozzle, 'pressure')),
    'temperature': lambda module, nozzle: module.plotlyField(module.fieldFigure(nozzle, 'temperature')),
    'plume':       lambda module, nozzle: module.plotlyPlume(module.plumeFigure(nozzle)),
}

def interactiveAvailable() -> bool:

    '''

    True when plotly is installed, so the interactive companion views can be produced.

    '''

    try:
        return bool(backend.figuresModule().plotlyAvailable)
    except Exception:
        return False

def openInteractive(nozzle, view: str, folder: str) -> str:

    '''

    Render a view with plotly, write it beside the run output and open it in the system
    browser.

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
    str : the path written, or None when plotly is unavailable or the view has no data

    '''

    import os
    import webbrowser

    figuresModule = backend.figuresModule()
    if not figuresModule.plotlyAvailable or view not in interactiveBuilders:
        return None

    figure = interactiveBuilders[view](figuresModule, nozzle)
    if figure is None:
        return None

    os.makedirs(folder, exist_ok = True)
    path = os.path.join(folder, f'{view}Interactive.html')
    figuresModule.writeInteractiveFigure(figure, path)
    webbrowser.open('file:///' + os.path.abspath(path).replace(os.sep, '/'))
    return path
