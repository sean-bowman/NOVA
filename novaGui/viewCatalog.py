
# -- NOVA GUI View Catalog -- #

'''

Every view a run can produce, in the order the view menu lists them, and the test of which ones a
finished run produced.

Each view names the Matplotlib drawer's source line, the plotly builder that renders it
interactively (`plotting.interactiveBuilders`), and the HTML file the run writes for it
(`runner.htmlFiles`), where it has them. The plume sweep view has none of the three: the browser
draws it from the run's plume sweeps (novaGui.plumeSweeps), and it is there for any run whose
contour the plume march can continue.

Author: Sean Bowman
Date:   08/28/2026

'''

from dataclasses import dataclass

import numpy as np

@dataclass(frozen = True)
class ViewSpec:

    '''

    One entry in the sidebar.

    key          the view's own name
    group        the sidebar heading it sits under
    label        what the sidebar shows
    source       a line under the title saying where the picture comes from
    builderKey   plotting.interactiveBuilders key that renders it with plotly, or None
    htmlKey      runner.htmlFiles key of an HTML file the run writes for it, or None

    '''

    key: str
    group: str
    label: str
    source: str
    builderKey: str = None
    htmlKey: str = None

fieldSource = 'one-dimensional chamber, characteristic mesh to the exit plane'
jacketSource = 'drawn from the jacket solve'

views = (
    ViewSpec('contour', 'Contour', 'Computed contour', 'drawn from the run', 'contour'),
    ViewSpec('nearWall', 'Flow', 'Near-wall state', 'drawn from the run', 'nearWall'),
    ViewSpec('mach', 'Flow', 'Mach field', fieldSource, 'mach', 'machField'),
    ViewSpec('pressure', 'Flow', 'Pressure field', fieldSource, 'pressure', 'pressureField'),
    ViewSpec('temperature', 'Flow', 'Temperature field', fieldSource, 'temperature', 'temperatureField'),
    ViewSpec('plume', 'Plume', 'Plume', 'chamber, nozzle and marched plume as one field', 'plume', 'plume'),
    ViewSpec('plumeSweep', 'Plume', 'Plume sweep', 'the plume marched at each ambient on this run\'s nozzle'),
    ViewSpec('circuit', 'Cooling', 'Coolant circuit', 'drawn from the jacket, extension and film solves'),
    ViewSpec('passes', 'Cooling', 'Coolant per pass', 'drawn from the coupled passes'),
    ViewSpec('circuitIterations', 'Cooling', 'Circuit iterations', 'every pass of the outer iteration, earlier ones fading'),
    ViewSpec('wallMap', 'Cooling', 'Jacket on the wall', jacketSource, None, 'heatTransfer'),
    ViewSpec('jacketTemperatures', 'Cooling', 'Temperatures', jacketSource, None, 'heatTransfer'),
    ViewSpec('coolantFlow', 'Cooling', 'Coolant flow', jacketSource, None, 'heatTransfer'),
    ViewSpec('coolantProperties', 'Cooling', 'Coolant properties', jacketSource, None, 'heatTransfer'),
    ViewSpec('heatFlux', 'Cooling', 'Heat flux', jacketSource, None, 'heatTransfer'),
    ViewSpec('film', 'Cooling', 'Film cooling', 'drawn from the film solve'),
    ViewSpec('extension', 'Cooling', 'Radiative extension', 'drawn from the extension solve'),
    ViewSpec('channelMesh', 'Cooling', 'Channel mesh', '3D assembly, decimated for the inline view',
             'channelMesh', 'channelMesh'),
    ViewSpec('revolved', '3D', 'Revolved contour', 'drawn from the run', 'revolved'),
    ViewSpec('volute', '3D', 'Volutes', '3D assembly, decimated for the inline view', 'volute', 'volute'),
)

def _attributeSize(nozzle, name: str) -> int:

    value = getattr(nozzle, name, None)
    try:
        return int(np.size(value)) if value is not None else 0
    except Exception:                                      # noqa: BLE001
        return 0

def availableViews(nozzle, outputs: dict) -> set:

    '''

    The keys of the views a run produced. Each test reads only what the view itself draws from,
    and any test that fails reads as unavailable rather than as an error.

    Parameters:
    -----------
    nozzle : Nozzle or None
        The run's nozzle.
    outputs : dict
        runner.findOutputs for the run's folder.

    Returns:
    --------
    set : view keys

    '''

    if nozzle is None:
        return set()

    def has(name, minimum = 2):
        return _attributeSize(nozzle, name) >= minimum

    def on(name):
        return str(getattr(nozzle, name, 'off')) in ('on', 'True', 'true')

    # The thermal drawers' accessors read the jacket, film and extension; imported here so the
    # catalog loads without the plotting stack
    from . import plumeSweeps, thermalPlots

    def jacket():
        return thermalPlots.thermalResults(nozzle) is not None

    tests = {
        'contour':            lambda: has('xNozzleWall'),
        'nearWall':           lambda: has('nozzleNearWallMachNumber'),
        'mach':               lambda: len(getattr(nozzle, 'allXPoints', []) or []) > 0,
        'pressure':           lambda: len(getattr(nozzle, 'allXPoints', []) or []) > 0,
        'temperature':        lambda: len(getattr(nozzle, 'allXPoints', []) or []) > 0,
        'plume':              lambda: getattr(nozzle, 'nozzlePlumeStructure', None) is not None,
        # Any run whose contour the march can continue, swept or not: the view is where a sweep starts
        'plumeSweep':         lambda: 'reason' not in plumeSweeps.lipState(nozzle),
        'circuit':            jacket,
        'passes':             lambda: (getattr(nozzle, 'coolantCircuitSolution', None) is not None
                                       or getattr(nozzle, 'extensionCircuitSolution', None) is not None),
        'circuitIterations':  lambda: thermalPlots.iterationDescription(nozzle) is not None,
        'wallMap':            jacket,
        'jacketTemperatures': jacket,
        'coolantFlow':        jacket,
        'coolantProperties':  jacket,
        'heatFlux':           jacket,
        'film':               lambda: on('filmCooling') and thermalPlots.filmSolved(nozzle),
        'extension':          lambda: thermalPlots.extensionSolved(nozzle),
        'channelMesh':        lambda: np.ndim(getattr(nozzle, 'xChannel', None)) == 2 and has('xChannel'),
        'revolved':     lambda: has('xNozzleWall'),
        # A volute is built only with the cooling channels, so the built object, not the flag
        'volute':       lambda: (getattr(nozzle, 'inletVolute', None) is not None
                                 or getattr(nozzle, 'outletVolute', None) is not None),
    }

    available = set()
    for key, test in tests.items():
        try:
            if test():
                available.add(key)
        except Exception:                                  # noqa: BLE001 -- unavailable, not broken
            continue

    return available
