# -- NOVA Backend Access -- #

'''

Lazy access to the NOVANozzleDesigner package from the GUI process. The heavy modules (Nozzle,
CEA) are loaded by the runner on a worker thread; the light ones (materials, units) can be
imported on demand from the main thread for the config panels.

Author: Sean Bowman
Date:   08/28/2026

'''

import os
import sys

packageDir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'NOVANozzleDesigner')

def _ensurePath() -> None:

    if packageDir not in sys.path:
        sys.path.insert(0, packageDir)

def figuresModule():

    '''

    The NOVANozzleDesigner figures module: renderer-independent figure data plus the plotly
    builders. NumPy only unless a plotly builder is called, so it is safe on the main thread.

    '''

    _ensurePath()
    import figures
    return figures

def materialsModule():

    '''

    The NOVANozzleDesigner materials module (numpy only, safe on the main thread).

    '''

    _ensurePath()
    import materials
    return materials
