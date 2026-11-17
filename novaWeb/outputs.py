
# -- NOVA Web Run Outputs -- #

'''

The Export tab's file handling: listing a finished run's outputs, copying the chosen ones to an
output folder, and opening a file or folder in the desktop's own application.

Every run writes all of NOVA's outputs into its staging folder (`<temp>/NOVA/web<pid>/run<n>/`):
the outputs in `<runName>Outputs/` and the config the run was given beside it as
`<runName>RunConfig.json`. Nothing reaches the output folder until an export copies the chosen
files into `<output folder>/<runName>Outputs/`, as the Tkinter front end does. The categories, the
rule that files a category by its name, and the default output folder (`runs/` at the repository
root) are the Tkinter Export tab's.

The browser names files by their base name, and only names the run listed are copied or opened, so
a request cannot reach a file outside the run's staging folder.

Author: Sean Bowman
Date:   11/17/2026

'''

# Standard library imports
import os
import re
import shutil
import subprocess
import sys

repositoryRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_unsafeName = re.compile(r'[\\/:*?"<>|]')

def categories() -> list:

    '''[{key, name, description}] in the order the list shows them.'''

    from novaGui.tabs.exportTab import categories as tkCategories

    return [{'key': key, 'name': name, 'description': description} for key, name, description in tkCategories]

def defaultBaseDir() -> str:

    '''The runs folder at the repository root, so exported output collects in one place.'''

    return os.path.join(repositoryRoot, 'runs')

def safeRunName(name: str) -> str:

    '''A run name usable as a folder name: the config's `filename`, else novaRun.'''

    name = str(name or '').strip()
    if not name or _unsafeName.search(name) or name in ('.', '..'):
        return 'novaRun'
    return name

def targetFolder(baseDir: str, runName: str) -> str:

    '''`<baseDir>/<runName>Outputs`, with a blank base meaning the default folder.'''

    base = os.path.abspath(os.path.expanduser(str(baseDir or '').strip() or defaultBaseDir()))
    return os.path.join(base, safeRunName(runName) + 'Outputs')

def runFiles(record) -> dict:

    '''

    {base name: path} of a finished run's outputs and its run config, or {} for no run.

    '''

    if record is None or not record.ok or not record.outputDir:
        return {}

    files = {}
    if os.path.isdir(record.outputDir):
        for entry in sorted(os.listdir(record.outputDir)):
            path = os.path.join(record.outputDir, entry)
            if os.path.isfile(path):
                files[entry] = path
    configPath = os.path.join(os.path.dirname(record.outputDir), record.runName + 'RunConfig.json')
    if os.path.isfile(configPath):
        files[os.path.basename(configPath)] = configPath

    return files

def listing(record) -> list:

    '''[{name, category, bytes}] for a finished run's outputs, in name order.'''

    from novaGui.tabs.exportTab import categoryOf

    return [{'name': name, 'category': categoryOf(name), 'bytes': os.path.getsize(path)}
            for name, path in runFiles(record).items()]

def export(record, baseDir: str, names: list) -> dict:

    '''

    Copy the named outputs of a finished run into its target folder.

    Parameters:
    -----------
    record : novaWeb.session.RunRecord
        The finished run.
    baseDir : str
        The output folder; the files land in `<baseDir>/<runName>Outputs/`.
    names : list
        Base names from the run's listing.

    Returns:
    --------
    dict : {'target': str, 'written': int, 'bytes': int}

    Raises:
    -------
    ValueError : if nothing is named, or a name is not one of the run's outputs
    OSError : if the target folder cannot be written

    '''

    files = runFiles(record)
    unknown = [name for name in names if name not in files]
    if unknown:
        raise ValueError(f'not outputs of this run: {", ".join(unknown[:5])}')
    if not names:
        raise ValueError('nothing is checked')

    target = targetFolder(baseDir, record.runName)
    os.makedirs(target, exist_ok = True)
    written = 0
    total = 0
    for name in names:
        destination = os.path.join(target, name)
        shutil.copy2(files[name], destination)
        written += 1
        total += os.path.getsize(destination)

    return {'target': target, 'written': written, 'bytes': total}

def openPath(path: str) -> None:

    '''Open a file or folder in the desktop's application for it.'''

    if sys.platform.startswith('win'):
        os.startfile(path)                                 # noqa: S606 -- user-initiated open
    elif sys.platform == 'darwin':
        subprocess.run(['open', path], check = False)
    else:
        subprocess.run(['xdg-open', path], check = False)
