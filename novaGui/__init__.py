
# -- NOVA GUI Package -- #

'''

The NOVA nozzle design suite's front end.

A FastAPI server wraps the NOVA backend and serves a React application built from
novaGui/frontend. `nova-gui`, the launcher an install writes, opens it in a desktop window
(pywebview, which hosts the system's WebView2 on Windows) with no console; `python -m novaGui`
opens the same window from a console, or with --browser the system browser.

The package runs from a NOVA checkout, installed editable (`pip install -e .[web]`): it reads the
checkout's validation summary and shipped configuration, and exports to its runs/ folder.

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

import os

__version__ = '0.1.0'

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
