# -- NOVA Plume: Inflow and Initial Field -- #

'''

Write NOVA's exit station into the plume case's inflow, and a column of exit flow into its initial
field when the case starts from rest.

The station is the one NOVA's plume march starts from: Mach number and flow angle at 121 radii from
the axis to the station radius, at NOVA's chamber stagnation state and ratio of specific heats.
Each inlet face takes the station's state at its own radius, interpolated linearly, with the static
pressure and temperature from the isentropic relations. The flow there is supersonic, so the
pressure, temperature and velocity are all fixed.

With `--column`, every cell inside the station radius, along the whole domain, also starts moving
axially at the station's speed and temperature for its radius, at the ambient's pressure, and every
other cell at the ambient. The jet's core is then in place from the first step. Started from rest
instead, the jet's head takes about 10 ms to cross the domain, because the expanded jet is much
lighter than the cold ambient it pushes aside. A column at the station's own pressure, two to five
times the ambient's, would expand radially as a blast; at ambient pressure it carries no radial
pressure difference.

The cell and face centers come from `postProcess -func writeCellCentres`, which writes `0/C`.
Allrun runs both before decomposing the case, after `mapFields` when the case starts from a coarser
grid:

    python3 scripts/setPlumeInflow.py <case> [--column]

Needs NumPy only.

Author: Sean Bowman

'''

import json
import math
import os
import re
import sys

import numpy as np

def readVectors(text: str, start: int = 0) -> tuple:

    '''

    The first vector list at or after `start` in a field file, uniform or not. OpenFOAM writes a
    short list on one line and a long one a vector per line, so the vectors are read one by one.

    Returns:
    --------
    tuple : (values as an (n, 3) array, or one row for a uniform value; the index the list ends at)

    '''

    match = re.compile(r'nonuniform\s+List<vector>\s*(\d+)\s*\(|uniform\s+\(([^)]*)\)').search(text, start)
    if match is None:
        raise ValueError('no vector list found')
    if match.group(2) is not None:
        return np.array(match.group(2).split(), dtype = float).reshape(1, 3), match.end()
    count, position, values = int(match.group(1)), match.end(), []
    for vector in re.finditer(r'\(([^()]*)\)', text[position:]):
        values.append(vector.group(1).split())
        if len(values) == count:
            return np.array(values, dtype = float), position + vector.end()

    raise ValueError(f'list declares {count} entries and carries {len(values)}')

def patchBlock(text: str, patch: str) -> tuple:

    '''Start and end of one patch's entry, name to closing brace, in a field file's boundaryField.'''

    boundary = text.index('boundaryField')
    match = re.compile(rf'\n([ \t]*){patch}\s*\n\s*\{{').search(text, boundary)
    if match is None:
        raise ValueError(f'no {patch} entry in boundaryField')
    depth, index = 0, match.end() - 1
    while True:
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return match.start() + 1, index + 1
        index += 1

def formatList(values: np.ndarray) -> tuple:

    '''A value list as OpenFOAM writes it, and its type.'''

    if values.ndim == 1:
        return '\n'.join(f'{value:.10g}' for value in values), 'scalar'

    return '\n'.join(f'({u:.10g} {v:.10g} {w:.10g})' for u, v, w in values), 'vector'

def writeField(path: str, inflow: np.ndarray, internal: np.ndarray = None) -> None:

    '''Replace a field's inlet entry with fixed values, and its internal field when one is given.'''

    with open(path, encoding = 'utf-8') as handle:
        text = handle.read()

    body, listType = formatList(inflow)
    start, end = patchBlock(text, 'inlet')
    text = (text[:start] + '    inlet\n    {\n        type            fixedValue;\n'
            f'        value           nonuniform List<{listType}>\n{len(inflow)}\n(\n{body}\n)\n;\n    }}' + text[end:])

    if internal is not None:
        body, listType = formatList(internal)
        field = f'internalField   nonuniform List<{listType}>\n{len(internal)}\n(\n{body}\n)\n;'
        text, replaced = re.subn(r'internalField\s+uniform\s+[^;]+;', lambda _: field, text, count = 1)
        if replaced != 1:
            raise ValueError(f'{path} has no uniform internal field to replace.')

    with open(path, 'w', encoding = 'utf-8', newline = '\n') as handle:
        handle.write(text)

def stationState(radius: np.ndarray, station: dict, gas: dict, unit: np.ndarray) -> tuple:

    '''

    The station's state at each radius.

    Parameters:
    -----------
    radius : np.ndarray
        Radius on the contour's scale [m]
    unit : np.ndarray
        (n, 3) radial unit vectors at each point

    Returns:
    --------
    tuple : (pressure [Pa], temperature [K], velocity [m/s] as (n, 3))

    '''

    gamma, gasConstant = gas['gamma'], gas['gasConstant']
    stationRadius = np.asarray(station['r'])
    mach = np.interp(radius, stationRadius, station['mach'])
    angle = np.interp(radius, stationRadius, station['flowAngle'])
    stagnation = 1.0 + 0.5 * (gamma - 1.0) * mach**2
    temperature = gas['stagnationTemperature'] / stagnation
    pressure = gas['chamberPressure'] * stagnation**(-gamma / (gamma - 1.0))
    speed = mach * np.sqrt(gamma * gasConstant * temperature)
    velocity = (speed * np.cos(angle))[:, None] * np.array([1.0, 0.0, 0.0]) + (speed * np.sin(angle))[:, None] * unit

    return pressure, temperature, velocity

def radialUnit(points: np.ndarray, toRadius: float) -> tuple:

    '''Radius on the contour's scale [m] and the radial unit vector of each point.'''

    height = np.hypot(points[:, 1], points[:, 2])
    unit = np.zeros_like(points)
    unit[:, 1], unit[:, 2] = points[:, 1] / height, points[:, 2] / height

    return height / toRadius, unit

def main(case: str, column: bool) -> None:

    with open(os.path.join(case, 'reference', 'novaPlume.json'), encoding = 'utf-8') as handle:
        reference = json.load(handle)
    with open(os.path.join(case, 'reference', 'case.json'), encoding = 'utf-8') as handle:
        settings = json.load(handle)
    gas, station = reference['gas'], reference['station']

    # Mesh height on the wedge's mid-plane over radius on the contour's scale
    toRadius = settings['radialScale'] * math.cos(math.radians(settings['wedgeAngle'] / 2.0))

    with open(os.path.join(case, '0', 'C'), encoding = 'utf-8') as handle:
        text = handle.read()
    cells, _ = readVectors(text, text.index('internalField'))
    start, _ = patchBlock(text, 'inlet')
    faces, _ = readVectors(text, start)

    faceRadius, faceUnit = radialUnit(faces, toRadius)
    if faceRadius.max() > station['radius'] * (1.0 + 1e-6):
        raise ValueError(f'inlet reaches {faceRadius.max():.6f} m, past the station radius {station["radius"]:.6f} m')
    pressure, temperature, velocity = stationState(faceRadius, station, gas, faceUnit)

    internal, inside = {'p': None, 'T': None, 'U': None}, np.zeros(len(cells), dtype = bool)
    if column:
        cellRadius, cellUnit = radialUnit(cells, toRadius)
        inside = cellRadius < station['radius']
        internal = {'p': np.full(len(cells), gas['ambientPressure']),
                    'T': np.full(len(cells), gas['ambientTemperature']), 'U': np.zeros_like(cells)}
        _, columnTemperature, columnVelocity = stationState(cellRadius[inside], station, gas, cellUnit[inside])
        internal['T'][inside] = columnTemperature
        internal['U'][inside, 0] = np.linalg.norm(columnVelocity, axis = 1)

    writeField(os.path.join(case, '0', 'p'), pressure, internal['p'])
    writeField(os.path.join(case, '0', 'T'), temperature, internal['T'])
    writeField(os.path.join(case, '0', 'U'), velocity, internal['U'])

    mach = np.interp(faceRadius, station['r'], station['mach'])
    print(f'{len(faces)} inlet faces from r = {faceRadius.min():.6f} to {faceRadius.max():.6f} m: '
          f'Mach {mach.min():.4f} to {mach.max():.4f}, pressure {pressure.min():.6g} to {pressure.max():.6g} Pa'
          + (f'; {int(inside.sum())} cells start in the column' if column else ''))

if __name__ == '__main__':
    arguments = [argument for argument in sys.argv[1:] if not argument.startswith('--')]
    main(arguments[0] if arguments else '.', '--column' in sys.argv)
