
# -- NOVA Web Front End Package -- #

'''

Browser-engine front end for the NOVA nozzle design suite.

A FastAPI server wraps the NOVA backend and serves a React application built from
novaWeb/frontend. `python -m novaWeb` opens it in a desktop window (pywebview, which hosts
the system's WebView2 on Windows) or, with --browser, in the system browser.

The server reuses the Tkinter front end's non-visual modules as they stand: the config
schema (novaGui.configSchema), the pipeline runner and stage tracker (novaGui.runner,
novaGui.progress), the view list and its availability tests (novaGui.tabs.viewTab), and
the Matplotlib drawers (novaGui.plotting, novaGui.thermalPlots). Both front ends therefore
build the same config and draw the same figures.

Author: Sean Bowman
Date:   11/16/2026

'''

__version__ = '0.1.0'
