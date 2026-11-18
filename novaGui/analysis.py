# -- NOVA GUI Result Table -- #

'''

The result table for a finished run: sizing, the chamber, delivered performance, station
thermochemistry from CEA, the cooling summary and each coolant pass, the extension circuit, the gas
generator, the films and the plume.

`resultRows` builds the rows as plain text, and both front ends show them: the web front end's
Analyze tab through `resultTable`, and the legacy Tkinter front end's Analyze tab directly. They
therefore list the same quantities with the same formatting.

The performance section carries three columns (equilibrium 1D, chamber gas 1D, delivered) as one
text joined by `columnSeparator`, under a row named `Columns`. `resultTable` splits them into cells,
so the browser draws them as columns, and returns:

    {'summary': str,
     'sections': [{'title': str, 'columns': [str] | None,
                   'rows': [{'label': str, 'cells': [str], 'unit': str, 'indent': bool}]}]}

A single-value row whose text reads `<number> <unit>` is split into the two, so the browser can
align the numbers; any other text stays whole in `cells` with an empty `unit`.

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
        # The limit is on the metal; under a barrier coating the gas-side surface runs hotter.
        # A multi-pass jacket's peak is the hotter of its two families.
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
        wallTemperature = metal if metal is not None else surface
        row(cooling, 'Peak hot wall temperature',
            None if wallTemperature is None else float(max(wallTemperature)), '{:.1f}', 'K')
        if metal is not None and surface is not None and not np.array_equal(np.asarray(metal), np.asarray(surface)):
            row(cooling, 'Peak coating surface temperature', float(max(surface)), '{:.1f}', 'K')
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
    dict : {'summary', 'sections'}; see the module docstring

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
            rows.append({'label': label.strip(), 'cells': cells, 'unit': unit, 'indent': label.startswith(' ')})
        sections.append({'title': title, 'columns': columns, 'rows': rows})

    return {'summary': summary, 'sections': sections}
