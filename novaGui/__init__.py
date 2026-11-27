
# -- NOVA GUI Package -- #

'''

The NOVA nozzle design suite's front end.

A FastAPI server wraps the NOVA backend and serves a React application built from
novaGui/frontend. `nova-gui`, the launcher an install writes, opens it in a desktop window
(pywebview, which hosts the system's WebView2 on Windows) with no console; `python -m novaGui`
opens the same window from a console, or with --browser the system browser.

The package runs from a NOVA checkout, installed editable (`pip install -e .[web]`): it reads the
checkout's validation summary and shipped configuration, and exports to its runs/ folder.
`runningBuild` names what runs, for the launcher's log, the About dialog and the health route: the
version, the standalone build (packaging/) or the checkout's revision, and the Python and system.

Besides the server, the package holds every piece of the front end that is not drawing widgets,
so a front end built on another toolkit reads the same definitions:

    configSchema    the Design form: sections, fields, selectors, defaults, dependency predicates
    design          the cross-field checks and the material store's entries for the form
    units           the unit table every dimensioned field converts through
    runner          the pipeline run itself, with its output listing
    progress        the model that folds a run's progress events into the stage stepper and list
    viewCatalog     the views a run can produce and the test of which ones it produced
    plotting, thermalPlots    the Matplotlib drawers for the views
    coolingFigures  plotly figures for the cooling views
    analysis        the result table
    outputs         the output categories, and listing, copying and opening a run's files
    themeColors     the Engineering Flat Metal palette in both modes, and its Matplotlib styling
    settings        the saved theme mode
    assets/         the plume mark and the window icon

Author: Sean Bowman
Date:   11/16/2026

'''

# Standard library imports
import functools
import os
import platform
import subprocess
import sys

__version__ = '0.1.1'

# The plume mark in each mode and the window icon
assetFolder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')

# The checkout the package runs from, and the files of it the GUI reads
repositoryRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
checkoutFiles = ('docs/validationStatus.json', 'src/NOVA/assets/NOVANozzle.json')

def missingCheckoutFiles() -> list:

    '''

    The files of the checkout the GUI reads that are not beside the package. A checkout, or an
    editable install of one, has them all; a regular install carries the package alone.

    '''

    return [path for path in checkoutFiles if not os.path.isfile(os.path.join(repositoryRoot, *path.split('/')))]

def checkoutRevision() -> str:

    '''

    The checkout's revision as `git describe --always --dirty` gives it: the latest tag, the commits
    since it and the commit ('v0.1.0-3-g89d703f'), or the commit alone before any tag, with '-dirty'
    when tracked files have uncommitted changes. '' when the folder has no history (a downloaded
    archive) or git is not on the path.

    '''

    if not os.path.exists(os.path.join(repositoryRoot, '.git')):
        return ''
    # Under pythonw a console program opens a console window of its own unless told not to
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        done = subprocess.run(['git', '-C', repositoryRoot, 'describe', '--always', '--dirty'], capture_output = True,
                              text = True, timeout = 10.0, creationflags = flags)
    except (OSError, subprocess.SubprocessError):
        return ''
    return done.stdout.strip() if done.returncode == 0 else ''

def buildLabel(version: str, build: str, revision: str) -> str:

    '''

    One line naming what runs, for a report of a problem: 'NOVA 0.1.0, checkout 89d703f with
    uncommitted changes, Python 3.14.10 on Windows 10.0.26300'.

    '''

    if build == 'standalone':
        where = 'standalone build'
    elif revision.endswith('-dirty'):
        where = f'checkout {revision.removesuffix("-dirty")} with uncommitted changes'
    else:
        where = f'checkout {revision}' if revision else 'checkout'
    # Python before 3.12 reports Windows 11 as release '10'; the version's build number tells them
    # apart on every Python
    system = platform.version() if sys.platform == 'win32' else platform.release()
    return f'NOVA {version}, {where}, Python {platform.python_version()} on {platform.system()} {system}'

@functools.lru_cache(maxsize = 1)
def runningBuild() -> dict:

    '''

    What is running, as it stood when first asked (the launcher asks before the server starts).

    Returns:
    --------
    dict : 'version', NOVA's version; 'build', 'standalone' for NOVA.exe (packaging/) or 'checkout';
           'revision', the checkout's (checkoutRevision), '' for the standalone build; 'label', the
           line naming all of it (buildLabel)

    '''

    build = 'standalone' if getattr(sys, 'frozen', False) else 'checkout'
    revision = checkoutRevision() if build == 'checkout' else ''
    return {'version': __version__, 'build': build, 'revision': revision,
            'label': buildLabel(__version__, build, revision)}
