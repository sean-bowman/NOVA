
# -- NOVA Web Front End Package -- #

'''

Browser-engine front end for the NOVA nozzle design suite.

A FastAPI server wraps the NOVA backend and serves a React application built from
novaWeb/frontend. `python -m novaWeb` opens it in a desktop window (pywebview, which hosts
the system's WebView2 on Windows) or, with --browser, in the system browser.

The server reuses the Tkinter front end's non-visual modules as they stand: the config
schema (novaGui.configSchema), the pipeline runner and stage tracker (novaGui.runner,
novaGui.progress), the view list and its availability tests (novaGui.tabs.viewTab), the
Matplotlib drawers (novaGui.plotting, novaGui.thermalPlots), the Design form's cross-field
checks and extension material helpers (novaGui.tabs.configTab), the result table
(novaGui.tabs.analysisTab) and the output categories (novaGui.tabs.exportTab). Both front ends
therefore build the same config, raise the same problems and draw the same figures. The cooling
views' plotly figures (novaWeb.coolingFigures) are the web front end's own, drawn from the same
arrays as the Matplotlib drawers.

Author: Sean Bowman
Date:   11/16/2026

'''

__version__ = '0.1.0'
