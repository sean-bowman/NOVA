# -- NOVA Nozzle Designer GUI Package -- #

'''

Tkinter front end for the NOVA nozzle design suite.

The GUI builds a configuration dictionary in the same schema as
NOVANozzleDesigner/assets/nozzleConfig.json, runs Nozzle.generateNozzle() on a
worker thread, and presents the resulting geometry and analysis across five
tabs: config, 2D geometry, 3D geometry, analysis, and export.

Launch with:

    python -m novaGui

from the repository root, or run novaGui/run.py directly.

Author: Sean Bowman
Date:   08/28/2026

'''

__version__ = '0.1.0'
