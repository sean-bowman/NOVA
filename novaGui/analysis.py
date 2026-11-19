# -- NOVA GUI Result Table -- #

'''

The result table for a finished run: sizing, the chamber, delivered performance, station
thermochemistry from CEA, the cooling summary and each coolant pass, the extension circuit, the gas
generator, the films and the plume.

`resultRows` builds the rows as plain text, and both front ends show them: the web front end's
results table through `resultTable`, and the legacy Tkinter front end's Analyze tab directly. They
therefore list the same quantities with the same formatting.

The performance section carries three columns (equilibrium 1D, chamber gas 1D, delivered) as one
text joined by `columnSeparator`, under a row named `Columns`. `resultTable` splits them into cells,
so the browser draws them as columns, and returns:

    {'summary': str,
     'headline': [{'key', 'label', 'value', 'unit', 'detail', 'tone', 'view'}],
     'sections': [{'title': str, 'columns': [str] | None,
                   'rows': [{'label': str, 'cells': [str], 'unit': str, 'indent': bool,
                             'view': str | None}]}]}

A single-value row whose text reads `<number> <unit>` is split into the two, so the browser can
align the numbers; any other text stays whole in `cells` with an empty `unit`.

`headline` is the handful of numbers a design is judged by first, drawn above the table: delivered
Isp and thrust at the design back pressure, contour length, exit diameter, the peak hot wall
temperature against its limit (`tone` 'warn' above it), and the coolant pressure drop of each pass.
They repeat rows of the table, in display units.

`view` names the figure that shows a row (novaGui.viewCatalog), so the browser can open it from the
row: a section's own figure, or for some rows a closer one (`rowViews`). The browser offers it
only when the run produced that view.

`compareTables` sets two runs' tables side by side for the result pane's baseline: each row and
headline number of the shown run gains the baseline run's cells and the change from the baseline,
and the rows only the baseline has follow at the end of their section with blank cells.

Author: Sean Bowman
Date:   11/17/2026

'''

# Standard library imports
import math
import re

# Third-party imports
import numpy as np

columnSeparator = '  |  '
_leadingNumber = re.compile(r'^([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s+(\S.*)$')

def _cell(value) -> str:

    '''One number of a three-column performance row, blank where the column has no value.'''

    number = _num(value)
    if number is None or number != number:
        return '--'
    if abs(number) >= 1000.0:
        return f'{number:.0f}'
    return f'{number:.4g}'

def _num(value):

    '''

    Coerce NOVA's mix of scalars, 0-d arrays and empty lists to a float, or None.

    '''

    try:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return None if len(value) == 0 else float(value[-1])
        result = float(value)
        return None if math.isnan(result) else result
    except (TypeError, ValueError):
        return None

def _mm(value):

    '''Meters to millimeters, with None passed through.'''

    return None if value in (None, '') else float(value) * 1e3

def _cm3(value):

    '''Cubic meters to cubic centimeters, with None passed through.'''

    return None if value in (None, '') else float(value) * 1e6

def _throatRadius(nozzle):

    '''Throat radius [mm], from the throat area or else the smallest wall radius.'''

    area = _num(getattr(nozzle, 'throatArea', None))
    if area:
        return math.sqrt(area / math.pi) * 1e3
    radii = getattr(nozzle, 'rNozzleWall', [])
    try:
        return float(min(radii)) * 1e3
    except (TypeError, ValueError):
        return None

def _exitRadius(nozzle):

    '''Exit radius [mm]: the last wall station.'''

    radii = getattr(nozzle, 'rNozzleWall', [])
    try:
        return float(radii[-1]) * 1e3
    except (TypeError, IndexError):
        return None

def _length(nozzle):

    '''Contour length [mm], first wall station to last.'''

    axis = getattr(nozzle, 'xNozzleWall', [])
    try:
        return (float(axis[-1]) - float(axis[0])) * 1e3
    except (TypeError, IndexError):
        return None

# The figure that shows each section, and the rows a closer figure shows
sectionViews = {
    'Sizing': 'contour', 'Combustion Chamber': 'contour',
    'Cooling': 'jacketTemperatures', 'Coolant passes': 'passes', 'Extension circuit': 'extension',
    'Films over the extension': 'film', 'Plume': 'plume',
}
rowViews = {
    ('Performance: 1D estimate and delivered', 'Exit Mach number'): 'mach',
    ('Performance: 1D estimate and delivered', 'Exit Mach number at the wall'): 'nearWall',
    ('Performance: 1D estimate and delivered', 'Exit pressure [Pa]'): 'pressure',
    ('Performance: 1D estimate and delivered', 'Exit pressure, area averaged [Pa]'): 'pressure',
    ('Performance: 1D estimate and delivered', 'Exit pressure at the wall [Pa]'): 'nearWall',
    ('Performance: 1D estimate and delivered', 'Exit temperature [K]'): 'temperature',
    ('Performance: 1D estimate and delivered', 'Exit velocity [m/s]'): 'nearWall',
    ('Chamber', 'Temperature'): 'temperature', ('Chamber', 'Pressure'): 'pressure',
    ('Throat', 'Temperature'): 'temperature', ('Throat', 'Pressure'): 'pressure',
    ('Cooling', 'Number of channels'): 'channelMesh', ('Cooling', 'Channels split to'): 'channelMesh',
    ('Cooling', 'Split area ratio'): 'channelMesh', ('Cooling', 'Coolant exit temperature'): 'coolantFlow',
    ('Cooling', 'Coolant exit pressure'): 'coolantFlow', ('Cooling', 'Coolant mass flow'): 'coolantFlow',
    ('Cooling', 'Coolant circuit'): 'circuit', ('Coolant passes', 'Turnaround loss'): 'circuit',
    ('Coolant passes', 'Turnaround section radius'): 'circuit',
}

def _rowView(section: str, label: str) -> str | None:

    '''The figure that shows a row: its own from rowViews, else its section's, else None.'''

    return rowViews.get((section, label), sectionViews.get(section))

def _peakWall(nozzle) -> tuple:

    '''

    (peak hot wall temperature, peak coating surface temperature) [K] of the jacket, None where the
    run has none. The limit is on the metal; under a barrier coating the gas-side surface runs
    hotter. A multi-pass jacket's peak is the hotter of its two families.

    '''

    circuit = getattr(nozzle, 'coolantCircuitSolution', None)
    if circuit is not None:
        passes = [passSolution.results for passSolution in (circuit.down, circuit.up)]
        surface = np.concatenate([np.asarray(results['wallTemperature']) for results in passes])
        metal = np.concatenate([np.asarray(results.get('metalWallTemperature', results['wallTemperature']))
                                for results in passes])
    else:
        surface = getattr(nozzle, 'channelWallTemperature', None)
        results = getattr(nozzle, 'channelThermalResults', None)
        metal = results.get('metalWallTemperature') if isinstance(results, dict) else None
    wall = metal if metal is not None else surface
    peak = None if wall is None or np.size(wall) == 0 else float(np.max(wall))
    coated = None
    if metal is not None and surface is not None and not np.array_equal(np.asarray(metal), np.asarray(surface)):
        coated = float(np.max(surface))
    return peak, coated

def _pressureText(pascals: float) -> tuple:

    '''

    A pressure drop in MPa to three figures: (number text, unit). One unit for every run, so two
    runs' drops compare however far apart they are.

    '''

    return f'{pascals / 1e6:.3g}', 'MPa'

def headline(nozzle) -> list:

    '''

    The numbers a design is judged by first, as the result pane draws them above the table. Each
    is {'key', 'label', 'value', 'unit', 'detail', 'tone', 'view'}; `tone` is 'warn' for a peak wall
    temperature above its limit and '' otherwise. A number the run did not produce is left out.

    '''

    items = []

    def add(key, label, value, unit, detail = '', tone = '', view = None):
        if value is not None:
            items.append({'key': key, 'label': label, 'value': value, 'unit': unit, 'detail': detail,
                          'tone': tone, 'view': view})

    summary = getattr(nozzle, 'performance', None)
    if summary is not None:
        isp = _num(summary.specificImpulseDelivered.get('design'))
        vacuum = _num(summary.specificImpulseDelivered.get('vacuum'))
        add('isp', 'Delivered Isp', None if isp is None else f'{isp:.1f}', 's',
            f'vacuum {vacuum:.1f} s' if vacuum is not None else '', view = 'nearWall')
        thrust = _num(summary.thrustDelivered.get('design'))
        add('thrust', 'Delivered thrust', None if thrust is None else f'{thrust / 1e3:.4g}', 'kN', 'design back pressure')

    length = _length(nozzle)
    add('length', 'Contour length', None if length is None else f'{length:.1f}', 'mm', view = 'contour')
    exitRadius = _exitRadius(nozzle)
    ratio = _num(getattr(nozzle, 'exitExpansionRatio', None))
    add('exitDiameter', 'Exit diameter', None if exitRadius is None else f'{2.0 * exitRadius:.1f}', 'mm',
        f'area ratio {ratio:.4g}' if ratio is not None else '', view = 'contour')

    if str(getattr(nozzle, 'makeCoolingChannels', 'off')) not in ('off', 'False', ''):
        peak, _ = _peakWall(nozzle)
        limit = _num(getattr(nozzle, 'maxWallTemperature', None))
        detail, tone = '', ''
        if peak is not None and limit is not None:
            # Judged as shown: a jacket sized to its limit reads 800.0 K against 800 K, and is not over it
            margin = round(limit - peak)
            detail = f'limit {limit:.0f} K, margin {margin + 0:.0f} K'
            tone = 'warn' if round(peak, 1) > limit else ''
        add('peakWall', 'Peak hot wall', None if peak is None else f'{peak:.1f}', 'K', detail, tone, 'jacketTemperatures')

        circuit = getattr(nozzle, 'coolantCircuitSolution', None)
        if circuit is not None:
            for passSolution in (circuit.down, circuit.up):
                state = passSolution.state
                drop = float(state.coolantInitialPressure) - float(state.coolantExitPressure)
                value, unit = _pressureText(drop)
                add(f'drop{passSolution.name.capitalize()}', f'{passSolution.name.capitalize()} pass pressure drop',
                    value, unit, f'{passSolution.channelCount} channels', view = 'passes')
        else:
            inlet = _num(getattr(nozzle, 'coolantInitialPressure', None))
            outlet = _num(getattr(nozzle, 'coolantExitPressure', None))
            if inlet is not None and outlet is not None:
                value, unit = _pressureText(inlet - outlet)
                add('drop', 'Coolant pressure drop', value, unit, 'single pass', view = 'coolantFlow')

    return items

def resultRows(nozzle) -> tuple:

    '''

    The result table of a finished run, as both front ends show it.

    Parameters:
    -----------
    nozzle : NOVA.Nozzle
        The run's Nozzle, after generateNozzle.

    Returns:
    --------
    tuple : (summary, sections). `summary` is the one-line headline (thrust, delivered Isp,
        propellants). `sections` is a list of (title, rows), each row a (label, text) pair. The
        performance section opens with a row labelled 'Columns' naming its three columns, and
        its rows join their three values with `columnSeparator`.

    '''

    sections = []
    cea = getattr(nozzle, 'ceaOutput', None)
    ceaResults = getattr(cea, 'ceaResults', {}) if cea is not None else {}
    performance = getattr(cea, 'nozzlePerformance', None) if cea is not None else None
    performance = performance or {}

    def section(title):
        sections.append((title, []))
        return sections[-1][1]

    def row(parent, label, value, fmt = '{:.4g}', unit = ''):
        number = _num(value) if not isinstance(value, str) else value
        if number is None or number == '':
            text = '--'
        elif isinstance(number, str):
            text = number
        else:
            text = fmt.format(number) + (f' {unit}' if unit else '')
        parent.append((label, text))

    def ceaGet(key):
        try:
            return ceaResults.get(key)
        except Exception:
            return None

    sizing = section('Sizing')
    row(sizing, 'Thrust', getattr(nozzle, 'thrust', None), '{:.0f}', 'N')
    row(sizing, 'Engine mass flow', getattr(nozzle, 'engineMassFlow', None), '{:.3f}', 'kg/s')
    row(sizing, 'Throat radius', _throatRadius(nozzle), '{:.2f}', 'mm')
    row(sizing, 'Exit radius', _exitRadius(nozzle), '{:.2f}', 'mm')
    row(sizing, 'Contour length', _length(nozzle), '{:.1f}', 'mm')
    row(sizing, 'Expansion ratio (1D)', getattr(nozzle, 'expansionRatio', None))
    row(sizing, 'Geometric area ratio', getattr(nozzle, 'exitExpansionRatio', None))
    row(sizing, 'Contraction ratio', getattr(nozzle, 'inletContractionRatio', None))
    row(sizing, 'Design back pressure (1D exit)', getattr(nozzle, 'targetExitPressure', None),
        '{:.0f}', 'Pa')

    chamberGeometry = section('Combustion Chamber')
    row(chamberGeometry, 'Barrel length', _mm(getattr(nozzle, 'chamberBarrelLength', None)), '{:.1f}', 'mm')
    row(chamberGeometry, 'Chamber volume', _cm3(getattr(nozzle, 'chamberVolume', None)), '{:.1f}', 'cm3')
    row(chamberGeometry, 'Characteristic length L*', getattr(nozzle, 'chamberLstarActual', None), '{:.4f}', 'm')
    row(chamberGeometry, 'Contraction ratio', getattr(nozzle, 'chamberContractionRatio', None))
    row(chamberGeometry, 'Chamber diameter', _mm(getattr(nozzle, 'chamberDiameter', None)), '{:.1f}', 'mm')

    # One-dimensional estimates beside what the solved exit plane delivers, each thrust
    # coefficient and impulse at a named back pressure
    summary = getattr(nozzle, 'performance', None)
    perf = section('Performance: 1D estimate and delivered')
    if summary is not None:
        perf.append(('Columns', columnSeparator.join(('equilibrium 1D', 'chamber gas 1D', 'delivered'))))
        for quantity, unit, equilibrium, chamberGas, delivered in summary.rows():
            cells = columnSeparator.join(_cell(value) for value in (equilibrium, chamberGas, delivered))
            label = quantity + (f' [{unit}]' if unit != '-' else '')
            perf.append((label, cells))
        row(perf, 'Nozzle efficiency, vacuum', summary.nozzleEfficiency, '{:.4f}')
        row(perf, 'Friction cost of thrust coefficient', summary.frictionThrustCoef, '{:.4f}')
        row(perf, 'Requested thrust, design back pressure', summary.requestedThrust, '{:.0f}', 'N')
        row(perf, 'Delivered thrust, design back pressure',
            summary.thrustDelivered.get('design'), '{:.0f}', 'N')
        row(perf, 'Delivered thrust after friction',
            summary.thrustDeliveredFrictionCorrected.get('design'), '{:.0f}', 'N')
        row(perf, 'Exit mass closure', summary.exitMassClosure, '{:.4f}')
    else:
        row(perf, 'Vacuum Isp (1D equilibrium)', performance.get('vacuumISP[s]'), '{:.1f}', 's')
        row(perf, 'Vacuum thrust coefficient (1D equilibrium)', performance.get('vacuumThrustCoef'))
    row(perf, 'Operating mode at sea level (1D)', performance.get('mode') or '--')

    chamber = section('Chamber')
    row(chamber, 'Temperature', ceaGet('combustionChamberTemperature')
        or getattr(nozzle, 'chamberStagnationTemperature', None), '{:.1f}', 'K')
    row(chamber, 'Pressure', getattr(nozzle, 'chamberPressure', None), '{:.0f}', 'Pa')
    row(chamber, 'Gamma', getattr(nozzle, 'chamberGamma', None) or ceaGet('combustionChamberGamma'))
    row(chamber, 'Molecular weight', ceaGet('combustionChamberMolecularWeight'), '{:.3f}', 'g/mol')
    row(chamber, 'Gas constant', getattr(nozzle, 'chamberRGasConstant', None), '{:.1f}', 'J/kg-K')
    row(chamber, 'Prandtl number', ceaGet('combustionChamberPrandtlNumber'))

    throat = section('Throat')
    row(throat, 'Temperature', ceaGet('throatTemperature'), '{:.1f}', 'K')
    row(throat, 'Pressure', ceaGet('throatPressure'), '{:.0f}', 'Pa')
    row(throat, 'Gamma', ceaGet('throatGamma') or getattr(nozzle, 'throatGamma', None))

    if str(getattr(nozzle, 'makeCoolingChannels', 'off')) not in ('off', 'False', ''):
        cooling = section('Cooling')
        row(cooling, 'Number of channels', getattr(nozzle, 'nChannel', None), '{:.0f}')
        peak, coated = _peakWall(nozzle)
        row(cooling, 'Peak hot wall temperature', peak, '{:.1f}', 'K')
        if coated is not None:
            row(cooling, 'Peak coating surface temperature', coated, '{:.1f}', 'K')
        row(cooling, 'Hot wall temperature limit', getattr(nozzle, 'maxWallTemperature', None),
            '{:.1f}', 'K')
        row(cooling, 'Coolant exit temperature',
            getattr(nozzle, 'coolantExitTemperature', None), '{:.1f}', 'K')
        row(cooling, 'Coolant exit pressure',
            getattr(nozzle, 'coolantExitPressure', None), '{:.0f}', 'Pa')
        row(cooling, 'Coolant mass flow', getattr(nozzle, 'coolantMassFlow', None), '{:.3f}', 'kg/s')
        row(cooling, 'Coolant circuit', {'singlePass': 'A, single pass', 'oneAndHalfPass': 'B, one and a half pass',
                                         'twoPass': 'C, two pass'}.get(getattr(nozzle, 'coolantCircuit', None),
                                                                       'A, single pass'))
        if getattr(nozzle, 'channelSplitAreaRatio', None):
            row(cooling, 'Channels split to', 2 * int(getattr(nozzle, 'nChannel', 0) or 0), '{:.0f}')
            row(cooling, 'Split area ratio', getattr(nozzle, 'channelSplitAreaRatio', None), '{:.3g}')

        # Each pass of a multi-pass jacket, and the ring between them
        circuit = getattr(nozzle, 'coolantCircuitSolution', None)
        if circuit is not None:
            passes = section('Coolant passes')
            for passSolution in (circuit.down, circuit.up):
                state = passSolution.state
                row(passes, f'{passSolution.name.capitalize()} pass',
                    f'{passSolution.channelCount} channels, {1e3*passSolution.channelMassFlow:.1f} g/s each')
                row(passes, f'  coolant', f'{float(state.coolantInitialTemperature):.1f} to '
                                          f'{float(state.coolantExitTemperature):.1f} K')
                row(passes, f'  pressure drop', float(state.coolantInitialPressure) - float(state.coolantExitPressure),
                    '{:.0f}', 'Pa')
                row(passes, f'  peak hot wall', float(max(passSolution.results.get(
                    'metalWallTemperature', passSolution.results['wallTemperature']))), '{:.1f}', 'K')
            row(passes, 'Turnaround loss', circuit.turnaround.pressureDrop, '{:.0f}', 'Pa')
            row(passes, 'Turnaround section radius', _mm(circuit.turnaround.sectionRadius), '{:.1f}', 'mm')
            downRib, upRib = circuit.ribHeatBalance()
            row(passes, 'Rib heat into the down pass', downRib, '{:.0f}', 'W')
            row(passes, 'Outer iteration', f'{circuit.iterations} passes, last change {circuit.history[-1]:.3f} K')

    # The extension's own circuit, the gas generator, and the films over the extension
    extensionCircuit = getattr(nozzle, 'extensionCircuitSolution', None)
    if extensionCircuit is not None:
        extensionSection = section('Extension circuit')
        row(extensionSection, 'Passes', extensionCircuit.passes, '{:.0f}')
        row(extensionSection, 'Direction', extensionCircuit.direction)
        row(extensionSection, 'Coolant', f'{extensionCircuit.massFlow:.3g} kg/s of {extensionCircuit.coolant}')
        row(extensionSection, 'Outlet', f'{extensionCircuit.outlet} at area ratio {extensionCircuit.outletAreaRatio:.3g}')
        row(extensionSection, 'Outlet temperature', extensionCircuit.outletTemperature, '{:.1f}', 'K')
        row(extensionSection, 'Peak hot wall', float(max(extensionCircuit.metalWallTemperature)), '{:.1f}', 'K')

    exhaust = getattr(nozzle, 'turbineExhaust', None)
    if exhaust is not None:
        generator = section('Gas generator and turbine')
        row(generator, 'Gas generator temperature', exhaust.gasGeneratorTemperature, '{:.0f}', 'K')
        row(generator, 'Turbine exhaust temperature', exhaust.temperature, '{:.0f}', 'K')
        row(generator, 'Turbine exhaust pressure', exhaust.pressure, '{:.0f}', 'Pa')
        row(generator, 'Turbine power', exhaust.turbinePower, '{:.4g}', 'W')
        if exhaust.condensedSpecies:
            row(generator, 'Condensed at equilibrium', f'{100*exhaust.condensedMassFraction:.1f} % by mass')

    film = getattr(nozzle, 'extensionFilmSolution', None)
    if film is not None:
        films = section('Films over the extension')
        for layer in film.layers:
            row(films, layer.name, f'{layer.massFlow:.3g} kg/s at {layer.coolantTemperature:.0f} K, '
                                   f'velocity ratio {layer.velocityRatio:.2f}')
        margin = getattr(nozzle, 'extensionTemperatureMargin', None)
        if margin is not None:
            row(films, 'Shell peak wall', getattr(nozzle, 'extensionPeakWallTemperature', None), '{:.0f}', 'K')
            row(films, 'Shell margin to its limit', margin, '{:.0f}', 'K')

    if summary is not None and summary.extraMassFlows:
        engine = section('Engine flows')
        for name, flow in summary.extraMassFlows.items():
            row(engine, name, flow, '{:.3f}', 'kg/s')
        row(engine, 'Engine total flow', summary.engineTotalMassFlow, '{:.3f}', 'kg/s')
        row(engine, 'Film thrust, kept apart', summary.filmThrustUnmixed, '{:.0f}', 'N')
        row(engine, 'Film thrust, fully mixed', summary.filmThrustMixed, '{:.0f}', 'N')
        row(engine, 'Engine Isp after friction, design back pressure',
            summary.engineSpecificImpulse.get('design'), '{:.1f}', 's')

    # The march's own numbers first, because they say whether its picture can be used, then
    # the correlated quantities the march cannot produce
    structure = getattr(nozzle, 'nozzlePlumeStructure', None)
    field = getattr(nozzle, 'nozzlePlumeField', None)
    if structure is not None or field is not None:
        plume = section('Plume')
        row(plume, 'Ambient pressure', getattr(nozzle, 'plumeAmbientPressure', None), '{:.0f}', 'Pa')
        if field is not None and field.solved:
            row(plume, 'Lip pressure ratio', field.lipPressureRatio, '{:.3f}')
            row(plume, 'Boundary Mach', field.boundaryMach, '{:.3f}')
            if field.lipRadius:
                row(plume, 'Marched reach', (field.solvedTo - field.lipX) / field.lipRadius, '{:.2f}', 'lip radii')
            row(plume, 'Mass continuity error', field.massDriftWorst, '{:+.2f}', '%')
            row(plume, 'Within the trusted bound', 'yes' if field.trustworthy else 'no, shorten the reach')
        elif field is not None:
            row(plume, 'March', 'declined')
            row(plume, 'Reason', (field.notes[-1] if field.notes else '--')[:140])
        if structure is not None:
            row(plume, 'Shock cell length (correlated)', getattr(structure, 'shockCellLength', 0.0) * 1e3,
                '{:.1f}', 'mm')
            lipRadius = getattr(structure, 'lipRadius', 0.0)
            axisShock = getattr(structure, 'axisShockX', 0.0)
            if getattr(structure, 'machDiskPresent', False) and lipRadius:
                row(plume, 'Mach disk (correlated)',
                    (structure.machDiskX - structure.lipX) / lipRadius, '{:.1f}', 'lip radii downstream')
            elif axisShock and lipRadius:
                row(plume, 'Regular reflection (correlated)',
                    (axisShock - structure.lipX) / lipRadius, '{:.1f}', 'lip radii downstream')
            else:
                row(plume, 'Mach disk (correlated)', 'none')

    thrust = _num(getattr(nozzle, 'thrust', None))
    isp = (summary.specificImpulseDelivered.get('design') if summary is not None
           else performance.get('idealISP[s]'))
    parts = []
    if thrust:
        parts.append(f'{thrust / 1e3:.0f} kN')
    if _num(isp):
        parts.append(f'Isp {_num(isp):.0f} s')
    fuel = getattr(nozzle, 'Fuel', '')
    ox = getattr(nozzle, 'Oxidizer', '')
    if fuel and ox:
        parts.append(f'{ox}/{fuel}')

    return '   '.join(parts), sections

def _splitUnit(text: str) -> tuple:

    '''

    ('1234', 'N') from '1234 N'. Text whose remainder holds another number ('12 channels, 1.2 g/s
    each', '300.0 to 340.0 K') stays whole: it is a sentence, not a value and a unit.

    '''

    match = _leadingNumber.match(text)
    if match is None:
        return text, ''
    number, rest = match.groups()
    if any(_leadingNumber.match(token + ' x') for token in rest.replace(',', ' ').split()):
        return text, ''
    return number, rest

def resultTable(nozzle) -> dict:

    '''

    The result table for a finished run's Nozzle.

    Parameters:
    -----------
    nozzle : NOVA.Nozzle
        The run's Nozzle, after generateNozzle.

    Returns:
    --------
    dict : {'summary', 'headline', 'sections'}; see the module docstring

    '''

    summary, rawSections = resultRows(nozzle)
    sections = []
    for title, rawRows in rawSections:
        columns = None
        rows = []
        for label, text in rawRows:
            if label == 'Columns' and columnSeparator in text:
                columns = text.split(columnSeparator)
                continue
            cells = text.split(columnSeparator) if columns and columnSeparator in text else [text]
            unit = ''
            if len(cells) == 1:
                cells[0], unit = _splitUnit(cells[0])
            rows.append({'label': label.strip(), 'cells': cells, 'unit': unit, 'indent': label.startswith(' '),
                         'view': _rowView(title, label.strip())})
        sections.append({'title': title, 'columns': columns, 'rows': rows})

    try:
        numbers = headline(nozzle)
    except Exception:                                      # noqa: BLE001 -- the table stands without them
        numbers = []

    return {'summary': summary, 'headline': numbers, 'sections': sections}

def _number(text: str):

    '''The number a cell reads, or None for text.'''

    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None

def change(shown: str, baseline: str) -> str:

    '''

    How a cell differs from the baseline's: '+1.8 (+0.41 %)' for numbers, written to the shown
    cell's own decimals; '' when the two read the same; 'differs' for text that does not.

    '''

    if shown == baseline:
        return ''
    a, b = _number(shown), _number(baseline)
    if a is None or b is None:
        return 'differs' if shown not in ('', '--') and baseline not in ('', '--') else ''
    difference = a - b
    if 'e' in shown.lower():
        text = f'{difference:+.3g}'
    else:
        decimals = len(shown.split('.')[1]) if '.' in shown else 0
        text = f'{difference:+.{decimals}f}'
    if b != 0.0:
        percent = 100.0 * difference / abs(b)
        digits = 0 if abs(percent) >= 10.0 else (1 if abs(percent) >= 1.0 else 2)
        text += f' ({percent:+.{digits}f} %)'
    return text

def _occurrences(rows: list) -> list:

    '''(label, how many rows of that label came before) for each row, to match rows across runs.'''

    seen = {}
    keys = []
    for row in rows:
        count = seen.get(row['label'], 0)
        seen[row['label']] = count + 1
        keys.append((row['label'], count))
    return keys

def compareTables(shown: dict, baseline: dict) -> dict:

    '''

    Two runs' result tables side by side: the shown run's, each row and headline number with the
    baseline's cells (`baseline`, None where the baseline has no such row) and the change from them
    (`change`, one text per cell). Rows only the baseline has follow at the end of their section,
    with blank cells and `baselineOnly`; sections only the baseline has follow at the end.

    Parameters:
    -----------
    shown, baseline : dict
        resultTable of each run.

    Returns:
    --------
    dict : the shown table with the comparison added

    '''

    baselineSections = {section['title']: section for section in baseline['sections']}
    sections = []
    for section in shown['sections']:
        other = baselineSections.pop(section['title'], None)
        otherRows = dict(zip(_occurrences(other['rows']), other['rows'])) if other is not None else {}
        rows = []
        for key, row in zip(_occurrences(section['rows']), section['rows']):
            match = otherRows.pop(key, None)
            if match is None or len(match['cells']) != len(row['cells']) or match['unit'] != row['unit']:
                rows.append({**row, 'baseline': None if match is None else match['cells'], 'change': None})
                continue
            rows.append({**row, 'baseline': match['cells'],
                         'change': [change(a, b) for a, b in zip(row['cells'], match['cells'])]})
        for row in otherRows.values():
            rows.append({**row, 'cells': ['--'] * len(row['cells']), 'baseline': row['cells'], 'change': None,
                         'baselineOnly': True})
        sections.append({**section, 'rows': rows})
    for section in baselineSections.values():
        rows = [{**row, 'cells': ['--'] * len(row['cells']), 'baseline': row['cells'], 'change': None,
                 'baselineOnly': True} for row in section['rows']]
        sections.append({**section, 'rows': rows, 'baselineOnly': True})

    otherNumbers = {item['key']: item for item in baseline.get('headline', [])}
    numbers = []
    for item in shown.get('headline', []):
        match = otherNumbers.get(item['key'])
        if match is None or match['unit'] != item['unit']:
            numbers.append({**item, 'baseline': None, 'change': None})
        else:
            numbers.append({**item, 'baseline': match['value'], 'change': change(item['value'], match['value'])})

    return {**shown, 'headline': numbers, 'sections': sections}
