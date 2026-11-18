
# -- NOVA Legacy Tkinter GUI Package -- #

'''

The legacy Tkinter front end for the NOVA nozzle design suite, kept beside the current one
(novaGui) and drawn over the same non-visual modules: the config schema, the runner, the
progress model, the drawers, the result table and the palette all come from novaGui.

The GUI builds a configuration dictionary in the same schema as
src/NOVA/assets/NOVANozzle.json, runs Nozzle.generateNozzle() on a
worker thread, and presents the result across four tabs: Design, View,
Analyze and Export. It opens on the shipped nozzle, in the Engineering Flat
Metal theme, dark or light.

Launch with:

    python -m legacy.novaTk

from the repository root, run legacy/novaTk/run.py directly, or double-click
legacy/novaTk.bat.

Author: Sean Bowman
Date:   08/28/2026

'''

__version__ = '0.1.0'
