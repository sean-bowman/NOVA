
# -- Export Tab -- #

'''

Chooses where run outputs are written and lists what the last run produced.
NOVA writes into <output location>/<output name>Outputs/: contour and shell text
files, STL geometry when a jacket exists, the saved figures, and a pickled
Nozzle object beside the folder.

Author: Sean Bowman
Date:   08/28/2026

'''

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog

from .. import theme
from .. import runner
from ..widgets import card

def _formatSize(byteCount: int) -> str:

    for unit in ('B', 'KB', 'MB', 'GB'):
        if byteCount < 1024 or unit == 'GB':
            return f'{byteCount:.0f} {unit}' if unit == 'B' else f'{byteCount:.1f} {unit}'
        byteCount /= 1024
    return f'{byteCount:.1f} GB'

class ExportTab(ttk.Frame):

    '''

    Output-location control and the produced-files listing.

    '''

    def __init__(self, master, app):

        super().__init__(master, style = 'TFrame', padding = theme.scaled(8))

        self._app = app
        self._result = None

        # Default to the runs directory at the NOVA repository root, so generated output
        # collects in one place rather than beside the source.
        repositoryRoot = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        defaultBase = os.path.join(repositoryRoot, 'runs')
        self._baseDir = tk.StringVar(value = defaultBase)

        picker = ttk.Frame(self, style = 'TFrame', padding = (theme.scaled(4), theme.scaled(4)))
        picker.pack(fill = 'x')
        picker.columnconfigure(1, weight = 1)

        ttk.Label(picker, text = 'Output location', style = 'TLabel').grid(row = 0, column = 0, sticky = 'w')
        ttk.Entry(picker, textvariable = self._baseDir).grid(row = 0, column = 1, sticky = 'ew', padx = theme.scaled(8))
        ttk.Button(picker, text = 'Browse', command = self._browse).grid(row = 0, column = 2)

        self._resolved = ttk.Label(picker, text = '', style = 'Muted.TLabel')
        self._resolved.grid(row = 1, column = 1, sticky = 'w', padx = theme.scaled(8), pady = (theme.scaled(4), 0))
        self._baseDir.trace_add('write', lambda *_: self._updateResolved())

        ttk.Label(
            self, style = 'Muted.TLabel', wraplength = theme.scaled(900), padding = (theme.scaled(8), theme.scaled(4)),
            text = ('Runs always execute with data export enabled so the View and Analyze tabs have '
                    'files to read. The export flag on the Design tab is overridden.'),
        ).pack(fill = 'x')

        listWrap = card(self, fill = 'both', expand = True, pady = (theme.scaled(4), 0))

        actions = ttk.Frame(listWrap, style = 'Surface.TFrame')
        actions.pack(fill = 'x', pady = (0, theme.scaled(6)))
        ttk.Label(actions, text = 'PRODUCED FILES', style = 'Eyebrow.Card.TLabel').pack(side = 'left')
        ttk.Button(actions, text = 'Open folder', command = self.openFolder,
                   style = 'Small.Card.TButton').pack(side = 'right', padx = (theme.scaled(4), 0))
        ttk.Button(actions, text = 'Refresh', command = self._populateFiles,
                   style = 'Small.Card.TButton').pack(side = 'right')

        self._tree = ttk.Treeview(listWrap, columns = ('type', 'size'), show = 'tree headings')
        self._tree.heading('#0', text = 'File')
        self._tree.heading('type', text = 'Type')
        self._tree.heading('size', text = 'Size')
        self._tree.column('#0', width = theme.scaled(380), anchor = 'w')
        self._tree.column('type', width = theme.scaled(90), anchor = 'w')
        self._tree.column('size', width = theme.scaled(90), anchor = 'e')
        scroll = ttk.Scrollbar(listWrap, orient = 'vertical', command = self._tree.yview, style = 'Card.Vertical.TScrollbar')
        self._tree.configure(yscrollcommand = scroll.set)
        scroll.pack(side = 'right', fill = 'y')
        self._tree.pack(side = 'left', fill = 'both', expand = True)
        self._tree.bind('<Double-1>', self._openSelected)

        self._updateResolved()

    # -- Used by the app -- #

    @property
    def outputBaseDir(self) -> str:

        return self._baseDir.get().strip() or os.getcwd()

    def currentRunName(self) -> str:

        try:
            return str(self._app.configTab.getConfig().get('filename') or 'novaRun')
        except Exception:
            return 'novaRun'

    def refresh(self, runResult) -> None:

        self._result = runResult
        self._populateFiles()

    # -- Internals -- #

    def _updateResolved(self) -> None:

        name = self.currentRunName()
        self._resolved.configure(text = os.path.join(self.outputBaseDir, name + 'Outputs') + os.sep)

    def _browse(self) -> None:

        chosen = filedialog.askdirectory(title = 'Output location', initialdir = self.outputBaseDir)
        if chosen:
            self._baseDir.set(chosen)

    def _outputDir(self) -> str:

        if self._result is not None and getattr(self._result, 'outputDir', ''):
            return self._result.outputDir
        return os.path.join(self.outputBaseDir, self.currentRunName() + 'Outputs')

    def _populateFiles(self) -> None:

        self._tree.delete(*self._tree.get_children())
        outputDir = self._outputDir()
        if not os.path.isdir(outputDir):
            self._tree.insert('', 'end', text = '(no output folder yet)', values = ('', ''))
            return

        for path in runner.findOutputs(outputDir, self.currentRunName())['all']:
            name = os.path.basename(path)
            extension = os.path.splitext(name)[1].lstrip('.').upper() or 'FILE'
            size = _formatSize(os.path.getsize(path))
            self._tree.insert('', 'end', text = name, values = (extension, size), tags = (path,))

    def openFolder(self) -> None:

        '''Open the run's output folder in the system file browser.'''


        outputDir = self._outputDir()
        if os.path.isdir(outputDir):
            self._openPath(outputDir)

    def _openSelected(self, _event) -> None:

        selection = self._tree.selection()
        if not selection:
            return
        tags = self._tree.item(selection[0], 'tags')
        if tags:
            self._openPath(tags[0])

    def _openPath(self, path: str) -> None:

        try:
            if sys.platform.startswith('win'):
                os.startfile(path)                       # noqa: S606 -- user-initiated open
            elif sys.platform == 'darwin':
                subprocess.run(['open', path], check = False)
            else:
                subprocess.run(['xdg-open', path], check = False)
        except OSError:
            pass
