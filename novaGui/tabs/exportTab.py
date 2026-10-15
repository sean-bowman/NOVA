
# -- Export Tab -- #

'''

Chooses which of a run's outputs to keep and writes them to an output folder.

Every run writes all of NOVA's outputs into the session's staging folder (`runner.stagingFolder`),
where the View tab reads them. Nothing reaches the output folder until Export copies the chosen
files into <output folder>/<output name>Outputs/. The outputs are listed by category, and a check
on a category or on a single file chooses it; every output is chosen after a run, except the
categories unchecked before it.

Author: Sean Bowman
Date:   08/28/2026

'''

import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .. import theme
from ..widgets import card, Tooltip

# What a run can write, in the order the list shows it: key, name, what it holds
categories = (
    ('figures',     'Figures',              'PNG images of the contour, flow fields, near-wall state and heat transfer'),
    ('interactive', 'Interactive figures',  'plotly HTML views, with the plotly.js they load'),
    ('contours',    'Contour coordinates',  'hot wall, shell and channel centerline text files'),
    ('geometry',    '3D geometry',          'STL surfaces of the wall, the channels and the volutes'),
    ('profile',     'Channel size profile', 'the profile the jacket was built to, as JSON'),
    ('nozzle',      'Nozzle object',        'the pickled Nozzle, reloadable in Python'),
    ('config',      'Run configuration',    'the JSON the run was given'),
    ('other',       'Other files',          'anything else the run wrote'),
)

def categoryOf(fileName: str) -> str:

    '''

    The category a run output belongs to, by its name.

    '''

    lower = fileName.lower()
    if lower.endswith('runconfig.json'):
        return 'config'
    if lower.endswith('channelprofile.json'):
        return 'profile'
    if lower.endswith('.png'):
        return 'figures'
    if lower.endswith('.html') or lower == 'plotly.min.js':
        return 'interactive'
    if lower.endswith('.txt'):
        return 'contours'
    if lower.endswith(('.stl', '.step', '.stp')):
        return 'geometry'
    if lower.endswith('.pkl'):
        return 'nozzle'

    return 'other'

def _formatSize(byteCount: int) -> str:

    for unit in ('B', 'KB', 'MB', 'GB'):
        if byteCount < 1024 or unit == 'GB':
            return f'{byteCount:.0f} {unit}' if unit == 'B' else f'{byteCount:.1f} {unit}'
        byteCount /= 1024
    return f'{byteCount:.1f} GB'

class ExportTab(ttk.Frame):

    '''

    The output folder, the run's outputs with a check for each, and the Export button.

    '''

    def __init__(self, master, app):

        super().__init__(master, style = 'TFrame', padding = theme.scaled(8))

        self._app = app
        self._result = None
        self._files = {}                  # path -> category, for the last run
        self._chosen = set()              # paths Export copies
        self._unchecked = set()           # categories left out of the next run's choice
        self._lastExport = ''

        # The runs directory at the NOVA repository root, so exported output collects in one place
        repositoryRoot = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self._baseDir = tk.StringVar(value = os.path.join(repositoryRoot, 'runs'))

        picker = ttk.Frame(self, style = 'TFrame', padding = (theme.scaled(4), theme.scaled(4)))
        picker.pack(fill = 'x')
        picker.columnconfigure(1, weight = 1)
        ttk.Label(picker, text = 'Output folder', style = 'TLabel').grid(row = 0, column = 0, sticky = 'w')
        ttk.Entry(picker, textvariable = self._baseDir).grid(row = 0, column = 1, sticky = 'ew', padx = theme.scaled(8))
        ttk.Button(picker, text = 'Browse', command = self._browse).grid(row = 0, column = 2)
        self._resolved = ttk.Label(picker, text = '', style = 'Muted.TLabel')
        self._resolved.grid(row = 1, column = 1, sticky = 'w', padx = theme.scaled(8), pady = (theme.scaled(4), 0))
        self._baseDir.trace_add('write', lambda *_: self._updateResolved())

        listWrap = card(self, fill = 'both', expand = True, pady = (theme.scaled(6), 0))
        heading = ttk.Frame(listWrap, style = 'Surface.TFrame')
        heading.pack(fill = 'x', pady = (0, theme.scaled(6)))
        ttk.Label(heading, text = 'OUTPUTS', style = 'Eyebrow.Card.TLabel').pack(side = 'left')
        ttk.Button(heading, text = 'None', command = lambda: self._chooseAll(False),
                   style = 'Small.Card.TButton').pack(side = 'right', padx = (theme.scaled(4), 0))
        ttk.Button(heading, text = 'All', command = lambda: self._chooseAll(True),
                   style = 'Small.Card.TButton').pack(side = 'right')

        # Rows are chosen by their check, not selected, so a row never takes the selection color
        # behind its check image
        self._tree = ttk.Treeview(listWrap, columns = ('kind', 'size'), show = 'tree headings', selectmode = 'none')
        self._tree.heading('#0', text = 'Output')
        self._tree.heading('kind', text = 'Files')
        self._tree.heading('size', text = 'Size')
        self._tree.column('#0', width = theme.scaled(520), anchor = 'w')
        self._tree.column('kind', width = theme.scaled(110), anchor = 'w')
        self._tree.column('size', width = theme.scaled(90), anchor = 'e')
        scroll = ttk.Scrollbar(listWrap, orient = 'vertical', command = self._tree.yview, style = 'Card.Vertical.TScrollbar')
        self._tree.configure(yscrollcommand = scroll.set)
        scroll.pack(side = 'right', fill = 'y')
        self._tree.pack(side = 'left', fill = 'both', expand = True)
        self._tree.bind('<Button-1>', self._onClick)
        self._tree.bind('<Double-1>', self._onDoubleClick)

        actions = ttk.Frame(self, style = 'TFrame', padding = (theme.scaled(4), theme.scaled(8), theme.scaled(4), 0))
        actions.pack(fill = 'x')
        self._exportButton = ttk.Button(actions, text = 'Export', style = 'Accent.TButton', command = self.export)
        self._exportButton.pack(side = 'right')
        Tooltip(self._exportButton, 'Copy the checked outputs into the output folder.')
        self._openButton = ttk.Button(actions, text = 'Open folder', style = 'Small.TButton', command = self.openFolder)
        self._openButton.pack(side = 'right', padx = (0, theme.scaled(8)))
        self._status = ttk.Label(actions, text = '', style = 'Muted.TLabel')
        self._status.pack(side = 'left', fill = 'x', expand = True)

        theme.addListener(self._restyle)
        # The output name lives on the Design tab, so the target is read again each time this tab shows
        self.bind('<Map>', lambda _event: self._updateResolved(), add = '+')
        self._populate()
        self._updateResolved()

    # -- Used by the app -- #

    @property
    def outputBaseDir(self) -> str:

        return self._baseDir.get().strip() or os.getcwd()

    def runName(self) -> str:

        '''The name the outputs go under: the last run's, else the Design form's.'''

        if self._result is not None and getattr(self._result, 'runName', ''):
            return self._result.runName
        try:
            return str(self._app.configTab.getConfig().get('filename') or 'novaRun')
        except Exception:                                  # noqa: BLE001 -- a half-typed form still names a folder
            return 'novaRun'

    def targetFolder(self) -> str:

        return os.path.join(self.outputBaseDir, self.runName() + 'Outputs')

    def refresh(self, runResult) -> None:

        self._result = runResult
        self._files = {}
        outputDir = getattr(runResult, 'outputDir', '')
        paths = []
        if outputDir and os.path.isdir(outputDir):
            paths = [os.path.join(outputDir, entry) for entry in sorted(os.listdir(outputDir))]
        configPath = getattr(runResult, 'configPath', '')
        if configPath:
            paths.append(configPath)
        for path in paths:
            if os.path.isfile(path):
                self._files[path] = categoryOf(os.path.basename(path))

        self._chosen = {path for path, category in self._files.items() if category not in self._unchecked}
        self._lastExport = ''
        self._populate()
        self._updateResolved()

    def export(self) -> list:

        '''

        Copy the chosen outputs into the target folder. Returns the paths written.

        '''

        chosen = [path for path in self._files if path in self._chosen]
        if not chosen:
            self._status.configure(text = 'Nothing is checked.')
            return []
        # A run started since this list was made replaces the files of the same name as it goes
        chosen = [path for path in chosen if os.path.isfile(path)]
        if not chosen:
            self._status.configure(text = 'A run in progress is replacing these outputs; export once it finishes.')
            return []

        target = self.targetFolder()
        written = []
        try:
            os.makedirs(target, exist_ok = True)
            for path in chosen:
                destination = os.path.join(target, os.path.basename(path))
                shutil.copy2(path, destination)
                written.append(destination)
        except OSError as error:
            messagebox.showerror('Export failed', f'Could not write to {target}\n\n{error}')
            return written

        total = sum(os.path.getsize(path) for path in written)
        self._lastExport = target
        self._status.configure(text = f'Exported {len(written)} files, {_formatSize(total)}, to {target}')
        self._updateButtons()
        return written

    def openFolder(self) -> None:

        '''Open the folder the last export wrote to, or the target folder if it exists.'''

        folder = self._lastExport or self.targetFolder()
        if os.path.isdir(folder):
            self._openPath(folder)

    # -- Choosing -- #

    def _categoryState(self, category: str) -> str:

        paths = [path for path, kind in self._files.items() if kind == category]
        # Before a run a category's check says whether the run's files of that kind will be chosen
        if not paths:
            return 'none' if category in self._unchecked else 'all'
        chosen = sum(1 for path in paths if path in self._chosen)
        if chosen == len(paths):
            return 'all'
        return 'some' if chosen else 'none'

    def _choose(self, paths: list, on: bool) -> None:

        for path in paths:
            if on:
                self._chosen.add(path)
            else:
                self._chosen.discard(path)

    def _chooseAll(self, on: bool) -> None:

        self._choose(list(self._files), on)
        self._unchecked = set() if on else {key for key, _, _ in categories}
        self._refreshChecks()

    def _onClick(self, event) -> str:

        item = self._tree.identify_row(event.y)
        if not item or 'indicator' in self._tree.identify_element(event.x, event.y):
            return ''

        if item.startswith('category:'):
            category = item.split(':', 1)[1]
            paths = [path for path, kind in self._files.items() if kind == category]
            on = self._categoryState(category) != 'all'
            self._choose(paths, on)
            if on:
                self._unchecked.discard(category)
            else:
                self._unchecked.add(category)
        else:
            self._choose([item], item not in self._chosen)
        self._refreshChecks()

        return 'break'

    def _onDoubleClick(self, event) -> str:

        item = self._tree.identify_row(event.y)
        if item and not item.startswith('category:') and os.path.isfile(item):
            self._openPath(item)

        return 'break'

    # -- Drawing -- #

    def _checkImages(self) -> dict:

        from .. import themeImages
        images = themeImages.buildImages(self.winfo_toplevel(), theme.mode, theme.palettes[theme.mode], theme.uiScale)

        return {'none': images['cardCheck'], 'all': images['cardCheck.selected'],
                'some': images['cardCheck.alternate']}

    def _populate(self) -> None:

        self._tree.delete(*self._tree.get_children())
        checks = self._checkImages()
        for key, name, description in categories:
            paths = [path for path, kind in self._files.items() if kind == key]
            if not paths and (self._files or key == 'other'):
                continue
            size = _formatSize(sum(os.path.getsize(path) for path in paths)) if paths else ''
            count = f'{len(paths)} file{"s" if len(paths) != 1 else ""}' if paths else 'after a run'
            self._tree.insert('', 'end', iid = f'category:{key}', text = f'  {name}: {description}',
                              values = (count, size), image = checks[self._categoryState(key)])
            for path in paths:
                self._tree.insert(f'category:{key}', 'end', iid = path, text = '  ' + os.path.basename(path),
                                  values = (os.path.splitext(path)[1].lstrip('.').upper(), _formatSize(os.path.getsize(path))),
                                  image = checks['all' if path in self._chosen else 'none'])
        self._updateButtons()

    def _refreshChecks(self) -> None:

        checks = self._checkImages()
        for key, _, _ in categories:
            item = f'category:{key}'
            if self._tree.exists(item):
                self._tree.item(item, image = checks[self._categoryState(key)])
        for path in self._files:
            if self._tree.exists(path):
                self._tree.item(path, image = checks['all' if path in self._chosen else 'none'])
        self._updateButtons()

    def _restyle(self) -> None:

        self._refreshChecks()

    def _updateButtons(self) -> None:

        self._exportButton.state(['!disabled'] if self._chosen else ['disabled'])
        folder = self._lastExport or self.targetFolder()
        self._openButton.state(['!disabled'] if os.path.isdir(folder) else ['disabled'])
        if not self._files:
            self._status.configure(text = 'Generate a nozzle to have outputs to export.')
        elif not self._lastExport:
            count = len(self._chosen)
            self._status.configure(text = f'{count} of {len(self._files)} outputs checked.')

    def _updateResolved(self) -> None:

        self._resolved.configure(text = self.targetFolder() + os.sep)
        self._updateButtons()

    def _browse(self) -> None:

        chosen = filedialog.askdirectory(title = 'Output folder', initialdir = self.outputBaseDir)
        if chosen:
            self._baseDir.set(chosen)

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
