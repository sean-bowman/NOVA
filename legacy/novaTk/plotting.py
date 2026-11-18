
# -- NOVA Tk GUI Embedded Matplotlib Pane -- #

'''

A themed Matplotlib figure embedded in a Tk frame, and the helpers that open a view in the
system browser. Matplotlib is imported here rather than in widgets.py so the main window can open
before the scientific stack is touched.

The drawers the View tab calls live in novaGui.plotting, shared with the current front end, and are
re-exported here. A pane remembers the last thing it drew and draws it again when the mode changes.

Author: Sean Bowman
Date:   08/28/2026

'''

import tkinter as tk
from tkinter import ttk

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from novaGui import backend
from novaGui.plotting import (_palette, drawContour, drawField, drawNearWall, drawPlotly3d,  # noqa: F401 -- re-exported
                              drawPlume, drawRevolvedContour, interactiveBuilders)

from . import theme

class _Toolbar(NavigationToolbar2Tk):

    '''

    Matplotlib's navigation toolbar without the history arrows. Tk draws a disabled image button
    under a stipple that shows as a checkered square on the dark theme, and an inline pane that is
    redrawn whole on every view change has little history to step through.

    '''

    toolitems = tuple(item for item in NavigationToolbar2Tk.toolitems
                      if item[0] in ('Home', None, 'Pan', 'Zoom', 'Save'))

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
