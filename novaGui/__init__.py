
# -- NOVA Nozzle Designer GUI Package -- #

'''

Tkinter front end for the NOVA nozzle design suite.

The GUI builds a configuration dictionary in the same schema as
src/NOVA/assets/NOVANozzle.json, runs Nozzle.generateNozzle() on a
worker thread, and presents the result across four tabs: Design, View,
Analyze and Export. It opens on the shipped nozzle, in the Engineering Flat
Metal theme, dark or light.

Launch with:

    python -m novaGui

from the repository root, or run novaGui/run.py directly.

Author: Sean Bowman
Date:   08/28/2026

'''

__version__ = '0.1.0'
