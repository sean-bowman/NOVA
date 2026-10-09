
# -- NOVA GUI Application -- #

'''

Main window: a header with the NOVA mark, the configuration loader and the theme switch; a four-tab
notebook (Design, View, Analyze, Export); and a shared run bar with a collapsible log. The run bar
hands the Design form to a background PipelineRunner and fans the result out to every tab.

Author: Sean Bowman
Date:   08/28/2026

'''

import re
import queue
import tkinter as tk
from tkinter import ttk, messagebox

from . import branding, settings, theme
from .widgets import ConsolePane, Tooltip
from .runner import PipelineRunner
from .tabs import ConfigTab, ViewTab, AnalysisTab, ExportTab

class NovaApp(tk.Tk):

    '''

    The NOVA nozzle designer front end.

    '''

    def __init__(self):

        # Must precede the Tk root: Windows decides how to composite the window at
        # creation, and a root built without awareness is upscaled from 96 dpi and blurry.
        theme.enableDpiAwareness()
        # Also before the root: the taskbar button takes its identity from the first window
        branding.setAppUserModelId()

        super().__init__()

        # applyTheme reads the real screen DPI and sets theme.uiScale, so the window
        # geometry below has to come after it.
        self._settings = settings.load()
        theme.applyTheme(self, self._settings['themeMode'])
        self._pendingMatplotlib = False
        # Combobox drop-downs are windows Tk builds itself; round each as it opens
        self.bind_class('ComboboxPopdown', '<Map>', lambda event: theme.popdownMapped(self, str(event.widget)), add = '+')

        self.title('NOVA Nozzle Designer')
        self._iconImages = branding.applyWindowIcon(self)
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

        # The title bar takes the theme's colors only once the window has a frame to paint
        self.after(80, lambda: theme.styleTitleBar(self))

        self.bind('<Control-r>', lambda _e: self._generate())
        self.bind('<Control-o>', lambda _e: self.configTab.loadConfig())
        self.bind('<Control-s>', lambda _e: self.configTab.saveConfig())
        self.protocol('WM_DELETE_WINDOW', self._onClose)

        self.after(120, self._drain)

    # -- Layout -- #

    def _buildHeader(self) -> None:

        header = ttk.Frame(self, style = 'Header.TFrame', padding = (theme.scaled(16), theme.scaled(10)))
        header.pack(side = 'top', fill = 'x')

        # The plume mark ahead of the wordmark; the header stands without it if it is missing
        self._bannerImage = branding.bannerImage(self, theme.scaled(30), theme.mode)
        self._banner = ttk.Label(header, image = self._bannerImage, style = 'Header.TLabel')
        if self._bannerImage is not None:
            self._banner.pack(side = 'left', padx = (0, theme.scaled(10)))
        theme.addListener(self._refreshBanner)
        ttk.Label(header, text = 'NOVA', style = 'Wordmark.Header.TLabel').pack(side = 'left')
        ttk.Label(header, text = 'Nozzle Optimization for Variable Applications',
                  style = 'Muted.Header.TLabel').pack(side = 'left', padx = theme.scaled(12))

        about = ttk.Button(header, text = 'About', style = 'Small.Header.TButton', command = self._about)
        about.pack(side = 'right')
        self._themeButton = ttk.Button(header, style = 'Toggle.Header.TButton', command = self._toggleTheme)
        self._themeButton.pack(side = 'right', padx = theme.scaled(8))
        Tooltip(self._themeButton, lambda: 'Switch to the light theme' if theme.mode == 'dark'
                else 'Switch to the dark theme')
        load = ttk.Button(header, text = 'Load config', style = 'Header.TButton',
                          command = lambda: self.configTab.loadConfig())
        load.pack(side = 'right')
        Tooltip(load, 'Load a JSON configuration into the Design tab.  Ctrl+O')

    def _buildBottom(self) -> None:

        bottom = ttk.Frame(self, style = 'TFrame')
        bottom.pack(side = 'bottom', fill = 'x')

        runBar = ttk.Frame(bottom, style = 'TFrame', padding = (theme.scaled(14), theme.scaled(10)))
        runBar.pack(side = 'top', fill = 'x')

        self._runButton = ttk.Button(runBar, text = 'Generate Nozzle', style = 'Accent.TButton',
                                     command = self._generate)
        self._runButton.pack(side = 'left')
        Tooltip(self._runButton, 'Run the design on the Design tab.  Ctrl+R')

        self._logButton = ttk.Button(runBar, text = 'Show log', command = self._toggleConsole, width = 10)
        self._logButton.pack(side = 'right')

        self._progress = ttk.Progressbar(runBar, mode = 'determinate', maximum = 1000,
                                         length = theme.scaled(160))
        self._progress.pack(side = 'right', padx = theme.scaled(12))

        self._status = ttk.Label(runBar, text = 'Idle', style = 'Muted.TLabel')
        self._status.pack(side = 'right')

        # The pipeline's own output, one line at a time, so the run is legible without opening the
        # log. Packed last on the left so it takes the remaining width.
        self._activity = ttk.Label(runBar, text = '', style = 'Activity.TLabel', anchor = 'w')
        self._activity.pack(side = 'left', fill = 'x', expand = True, padx = theme.scaled(14))

        self._console = ConsolePane(bottom, height = 11)
        # Packed on demand by _toggleConsole.

    def _buildNotebook(self) -> None:

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(side = 'top', fill = 'both', expand = True, padx = theme.scaled(6),
                           pady = (theme.scaled(4), 0))

        self.configTab = ConfigTab(self.notebook, self)
        self.viewTab = ViewTab(self.notebook, self)
        self.analysisTab = AnalysisTab(self.notebook, self)
        self.exportTab = ExportTab(self.notebook, self)

        self.notebook.add(self.configTab, text = 'Design')
        self.notebook.add(self.viewTab, text = 'View')
        self.notebook.add(self.analysisTab, text = 'Analyze')
        self.notebook.add(self.exportTab, text = 'Export')

        self._tabs = (self.configTab, self.viewTab, self.analysisTab, self.exportTab)

    # -- Theme -- #

    def _refreshBanner(self) -> None:

        '''Swap the header mark for the one drawn for the new mode.'''

        image = branding.bannerImage(self, theme.scaled(30), theme.mode)
        if image is not None:
            self._bannerImage = image
            self._banner.configure(image = image)

    def _toggleTheme(self) -> None:

        '''

        Switch between the dark and light modes and remember the choice. While a run is drawing
        its figures on the worker thread, Matplotlib's global settings are left alone until it
        finishes.

        '''

        newMode = 'light' if theme.mode == 'dark' else 'dark'
        busy = self.runner.busy
        self.configure(cursor = 'watch')
        self.update_idletasks()
        try:
            theme.setMode(self, newMode, matplotlib = not busy)
        finally:
            self.configure(cursor = '')
        self._pendingMatplotlib = busy
        self._settings['themeMode'] = newMode
        settings.save(self._settings)

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
            self.runner.start(config, self.exportTab.outputBaseDir)
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
        self._activity.configure(text = text, style = 'ActivityError.TLabel' if isError else 'Activity.TLabel')

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
        if self._pendingMatplotlib:
            theme.applyMatplotlib()
            self._pendingMatplotlib = False

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
        self.notebook.select(self.viewTab)

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
            'Tkinter front end for the NOVA suite: designs a nozzle on the Design tab, runs the '
            'contour, cooling, heat transfer and plume pipeline on a background thread, and shows '
            'the result on the View and Analyze tabs.\n\n'
            'Shortcuts: Ctrl+R generate, Ctrl+O load a configuration, Ctrl+S save one.\n\n'
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
