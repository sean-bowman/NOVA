
# -- NOVA Backend Access -- #

'''

Lazy access to the NOVA package from the GUI process. The heavy modules (Nozzle, CEA) are
loaded by the runner on a worker thread; the light ones (materials, units) can be imported
on demand from the main thread for the config panels.

Author: Sean Bowman
Date:   08/28/2026

'''

def figuresModule():

    '''

    The NOVA figures module: renderer-independent figure data plus the plotly builders. NumPy
    only unless a plotly builder is called, so it is safe on the main thread.

    '''

    from NOVA import figures
    return figures

def materialsModule():

    '''

    The NOVA materials module (numpy only, safe on the main thread).

    '''

    from NOVA import materials
    return materials
