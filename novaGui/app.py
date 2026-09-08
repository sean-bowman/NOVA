# -- NOVA GUI Application -- #

'''

Main window: a five-tab notebook (config, 2D geometry, 3D geometry, analysis,
export) over a shared run bar and collapsible log. The run bar hands the config
form to a background PipelineRunner and fans the result out to every tab.

Author: Sean Bowman
Date:   08/28/2026

'''

import re
import queue
import tkinter as tk
from tkinter import ttk, messagebox

from . import theme
from .widgets import ConsolePane, Tooltip
from .runner import PipelineRunner
from .tabs import ConfigTab, Geometry2DTab, Geometry3DTab, AnalysisTab, ExportTab

class NovaApp(tk.Tk):

    '''

    The NOVA nozzle designer front end.

    '''

    def __init__(self):

        # Must precede the Tk root: Windows decides how to composite the window at
        # creation, and a root built without awareness is upscaled from 96 dpi and blurry.
        theme.enableDpiAwareness()

        super().__init__()

        # applyTheme reads the real screen DPI and sets theme.uiScale, so the window
        # geometry below has to come after it.
        theme.applyTheme(self)

        self.title('NOVA Nozzle Designer')
        self.geometry(f'{theme.scaled(1180)}x{theme.scaled(820)}')
        self.minsize(theme.scaled(960), theme.scaled(680))

        self._queue = queue.Queue()
        self.runner = PipelineRunner(self._queue)
        self.runResult = None
        self._consoleVisible = False
        self._progressCeiling = 0.0
        self._creepJob = None

        self._buildHeader()
        self._buildBottom()
        self._buildNotebook()
        self._buildMenu()

        self.bind('<Control-r>', lambda _e: self._generate())
        self.protocol('WM_DELETE_WINDOW', self._onClose)

        self.after(120, self._drain)

    # -- Layout -- #

    def _buildHeader(self) -> None:

        header = ttk.Frame(self, style = 'Elevated.TFrame', padding = (16, 10))
        header.pack(side = 'top', fill = 'x')

        ttk.Label(header, text = 'NOVA', style = 'Wordmark.TLabel',
                  background = theme.surface2).pack(side = 'left')
        ttk.Label(header, text = 'Nozzle Optimization for Variable Applications',
                  style = 'SurfaceMuted.TLabel').pack(side = 'left', padx = 12)

    def _buildBottom(self) -> None:

        bottom = ttk.Frame(self, style = 'TFrame')
        bottom.pack(side = 'bottom', fill = 'x')

        runBar = ttk.Frame(bottom, style = 'TFrame', padding = (14, 10))
        runBar.pack(side = 'top', fill = 'x')

        self._runButton = ttk.Button(runBar, text = '  Generate Nozzle  ', style = 'Accent.TButton',
                                     command = self._generate)
        self._runButton.pack(side = 'left')

        self._generateAllFigures = tk.BooleanVar(value = True)
        figureToggle = ttk.Checkbutton(runBar, text = 'Interactive 3D views',
                                       variable = self._generateAllFigures)
        figureToggle.pack(side = 'left', padx = 14)
        Tooltip(figureToggle, 'Also write the plotly channel-mesh and jacket HTML views when '
                              'cooling channels are enabled. Adds time to the run.')

        self._logButton = ttk.Button(runBar, text = 'Show log', command = self._toggleConsole, width = 10)
        self._logButton.pack(side = 'right')

        self._progress = ttk.Progressbar(runBar, mode = 'determinate', maximum = 1000,
                                         length = theme.scaled(160))
        self._progress.pack(side = 'right', padx = 12)

        self._status = ttk.Label(runBar, text = 'Idle', style = 'Muted.TLabel')
        self._status.pack(side = 'right')

        # The pipeline's own output, one line at a time, so the run is legible without
        # opening the log. Packed last on the left so it takes the remaining width.
        self._activity = ttk.Label(runBar, text = '', style = 'Muted.TLabel', anchor = 'w')
        self._activity.configure(font = theme.fontMono, foreground = theme.textDim)
        self._activity.pack(side = 'left', fill = 'x', expand = True, padx = 14)

        self._console = ConsolePane(bottom, height = 11)
        # Packed on demand by _toggleConsole.

    def _buildNotebook(self) -> None:

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(side = 'top', fill = 'both', expand = True, padx = 6, pady = 6)

        self.configTab = ConfigTab(self.notebook, self)
        self.geometry2dTab = Geometry2DTab(self.notebook, self)
        self.geometry3dTab = Geometry3DTab(self.notebook, self)
        self.analysisTab = AnalysisTab(self.notebook, self)
        self.exportTab = ExportTab(self.notebook, self)

        self.notebook.add(self.configTab, text = '  Config  ')
        self.notebook.add(self.geometry2dTab, text = '  2D Geometry  ')
        self.notebook.add(self.geometry3dTab, text = '  3D Geometry  ')
        self.notebook.add(self.analysisTab, text = '  Analysis  ')
        self.notebook.add(self.exportTab, text = '  Export  ')

        self._tabs = (self.configTab, self.geometry2dTab, self.geometry3dTab,
                      self.analysisTab, self.exportTab)

    def _buildMenu(self) -> None:

        menubar = tk.Menu(self)

        fileMenu = tk.Menu(menubar, tearoff = 0)
        fileMenu.add_command(label = 'Load config...', command = self.configTab._loadJson)
        fileMenu.add_command(label = 'Save config...', command = self.configTab._saveJson)
        fileMenu.add_separator()
        fileMenu.add_command(label = 'Open output folder', command = self.exportTab._openFolder)
        fileMenu.add_separator()
        fileMenu.add_command(label = 'Exit', command = self._onClose)
        menubar.add_cascade(label = 'File', menu = fileMenu)

        runMenu = tk.Menu(menubar, tearoff = 0)
        runMenu.add_command(label = 'Generate Nozzle\tCtrl+R', command = self._generate)
        menubar.add_cascade(label = 'Run', menu = runMenu)

        viewMenu = tk.Menu(menubar, tearoff = 0)
        viewMenu.add_command(label = 'Toggle run log', command = self._toggleConsole)
        menubar.add_cascade(label = 'View', menu = viewMenu)

        helpMenu = tk.Menu(menubar, tearoff = 0)
        helpMenu.add_command(label = 'About', command = self._about)
        menubar.add_cascade(label = 'Help', menu = helpMenu)

        self.config(menu = menubar)

    # -- Run control -- #

    def _generate(self) -> None:

        if self.runner.busy:
            return

        try:
            config = self.configTab.getConfig()
        except ValueError as exc:
            messagebox.showerror('Invalid input', str(exc))
            return

        problems = self.configTab.validate()
        if problems:
            proceed = messagebox.askyesno(
                'Configuration warnings',
                'The form has unresolved issues:\n\n  -  ' + '\n  -  '.join(problems)
                + '\n\nRun anyway?',
            )
            if not proceed:
                return

        self._console.append('', None)
        self._console.append('starting run', 'info')
        self._setRunningState(True)

        try:
            self.runner.start(config, self.exportTab.outputBaseDir, self._generateAllFigures.get())
        except RuntimeError as exc:
            self._setRunningState(False)
            messagebox.showerror('Cannot start', str(exc))

    def _setRunningState(self, running: bool) -> None:

        if running:
            self._runButton.configure(state = 'disabled')
            self._progress.configure(value = 0)
            self._progressCeiling = 0.0
            self._status.configure(text = 'Running...', style = 'Warn.TLabel')
            self._scheduleCreep()
        else:
            self._runButton.configure(state = 'normal')
            self._cancelCreep()

    def _drain(self) -> None:

        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == 'log':
                    tag = 'err' if self._looksLikeError(payload) else None
                    self._console.append(payload, tag)
                    self._showActivity(payload, tag == 'err')
                elif kind == 'progress':
                    self._applyProgress(*payload)
                elif kind == 'status':
                    self._applyStatus(*payload)
                elif kind == 'result':
                    self._onResult(payload)
        except queue.Empty:
            pass
        self.after(120, self._drain)

    def _showActivity(self, line: str, isError: bool = False) -> None:

        '''

        Mirror the most recent output line beside the progress bar. tqdm redraws are
        collapsed to their percentage so the bar area does not fill with hash marks.

        '''

        text = line.strip()
        if not text:
            return
        bar = re.match(r'\s*(\d{1,3})%\|.*?\|\s*(.*)', line)
        if bar:
            text = f'{bar.group(1)}%  {bar.group(2).strip()}'
        if len(text) > 110:
            text = text[:107] + '...'
        self._activity.configure(text = text,
                                 foreground = theme.red if isError else theme.textDim)

    def _applyProgress(self, fraction: float, ceiling: float, label: str) -> None:

        '''

        Snap the run bar to a stage boundary reported by the tracker.

        '''

        self._progressCeiling = max(0.0, min(1.0, float(ceiling)))
        target = max(0.0, min(1.0, float(fraction)))
        if target * 1000 > self._progress['value']:
            self._progress.configure(value = target * 1000)
        self._status.configure(text = label, style = 'Warn.TLabel')

    def _scheduleCreep(self) -> None:

        '''

        Ease the bar toward the current stage ceiling while the stage is silent. The
        method-of-characteristics solve prints nothing for tens of seconds, and a bar that
        does not move reads as a hang.

        '''

        self._cancelCreep()

        def step():
            ceiling = self._progressCeiling * 1000
            value = float(self._progress['value'])
            if value < ceiling:
                # Asymptotic: fast at the start of a stage, never reaches the boundary.
                self._progress.configure(value = value + (ceiling - value) * 0.04)
            self._creepJob = self.after(300, step)

        self._creepJob = self.after(300, step)

    def _cancelCreep(self) -> None:

        if self._creepJob is not None:
            self.after_cancel(self._creepJob)
            self._creepJob = None

    def _looksLikeError(self, line: str) -> bool:

        lowered = line.lower()
        return lowered.startswith(('traceback', 'error', '  file "')) or 'error:' in lowered

    def _applyStatus(self, state: str, detail: str) -> None:

        if state == 'running':
            self._status.configure(text = detail, style = 'Warn.TLabel')
        elif state == 'done':
            self._status.configure(text = f'Done in {detail}', style = 'Ok.TLabel')
            self._progressCeiling = 1.0
            self._progress.configure(value = 1000)
        elif state == 'error':
            self._status.configure(text = 'Failed', style = 'Error.TLabel')
            self._progressCeiling = 0.0

    def _onResult(self, result) -> None:

        self._setRunningState(False)
        self.runResult = result

        if not result.ok:
            self._console.append(f'run failed: {result.error}', 'err')
            messagebox.showerror('Run failed', f'{result.error}\n\nSee the run log for the full traceback.')
            return

        self._console.append(f'run complete in {result.elapsedSec:.1f} s  ->  {result.outputDir}', 'ok')
        for tab in self._tabs:
            try:
                tab.refresh(result)
            except Exception as exc:                     # noqa: BLE001 -- one bad tab must not sink the rest
                self._console.append(f'{type(tab).__name__}.refresh failed: {exc}', 'err')
        self.notebook.select(self.geometry2dTab)

    # -- Misc -- #

    def _toggleConsole(self) -> None:

        self._consoleVisible = not self._consoleVisible
        if self._consoleVisible:
            self._console.pack(side = 'top', fill = 'both')
            self._logButton.configure(text = 'Hide log')
        else:
            self._console.pack_forget()
            self._logButton.configure(text = 'Show log')

    def _about(self) -> None:

        messagebox.showinfo(
            'About NOVA Nozzle Designer',
            'NOVA -- Nozzle Optimization for Variable Applications\n\n'
            'Tkinter front end for the NOVA suite: builds a config, runs the '
            'contour, cooling and heat transfer pipeline on a background thread, and shows the '
            'resulting geometry and analysis.\n\n'
            f'GUI version {__import__("novaGui").__version__}',
        )

    def _onClose(self) -> None:

        if self.runner.busy:
            if not messagebox.askokcancel('Quit', 'A run is in progress. Quit anyway?'):
                return
        self.destroy()

def main() -> None:

    '''

    Launch the application.

    '''

    NovaApp().mainloop()

if __name__ == '__main__':
    main()
