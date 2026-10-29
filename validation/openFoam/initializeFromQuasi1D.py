# -- NOVA Nozzle: Quasi One-Dimensional Initial Field -- #

'''

Write the quasi one-dimensional isentropic flow into the case's initial fields.

Each cell takes the Mach number its station's area ratio gives, subsonic ahead of the throat and
supersonic behind it, with the static state from the isentropic relations at NOVA's chamber
stagnation state. The velocity is turned toward the wall in proportion to the cell's height in the
section, so the flow starts close to tangent to the wall everywhere. The run then has the
two-dimensional flow to settle rather than the start-up of the whole nozzle, which cuts the
physical time it needs to a few passes of the chamber.

The cell centers come from `postProcess -func writeCellCentres`, which writes `0/C`. Allrun runs
both before decomposing the case:

    python3 scripts/initializeFromQuasi1D.py <case>

Needs NumPy only.

Author: Sean Bowman

'''

import json
import os
import re
import sys

import numpy as np

def readCellCenters(path: str) -> np.ndarray:

    '''

    The cell centers from an ASCII `C` field.

    Returns:
    --------
    np.ndarray : (cells, 3) [m]

    '''

    with open(path, encoding = 'utf-8') as handle:
        text = handle.read()
    match = re.search(r'internalField\s+nonuniform\s+List<vector>\s*(\d+)\s*\((.*?)\n\)\s*;', text, re.DOTALL)
    if match is None:
        raise ValueError(f'{path} carries no ASCII list of cell centers; write it with writeFormat ascii.')
    count = int(match.group(1))
    centers = np.array(match.group(2).replace('(', ' ').replace(')', ' ').split(), dtype = float).reshape(-1, 3)
    if len(centers) != count:
        raise ValueError(f'{path} declares {count} cell centers and carries {len(centers)}.')

    return centers

def areaRatio(mach: np.ndarray, gamma: float) -> np.ndarray:

    '''Isentropic area ratio A/A* at a Mach number [-].'''

    exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))

    return (1.0 / mach) * ((2.0 / (gamma + 1.0)) * (1.0 + 0.5 * (gamma - 1.0) * mach**2))**exponent

def machFromAreaRatio(ratio: np.ndarray, gamma: float, supersonic: np.ndarray) -> np.ndarray:

    '''

    Mach number at each area ratio, on the branch `supersonic` picks, by bisection. The area ratio
    falls with Mach number below one and rises above it, so each branch is monotonic.

    '''

    ratio = np.maximum(ratio, 1.0)
    low = np.where(supersonic, 1.0, 1e-6)
    high = np.where(supersonic, 50.0, 1.0)
    for _ in range(80):
        middle = 0.5 * (low + high)
        # On the subsonic branch a ratio above the target means the Mach number is too low
        tooLow = (areaRatio(middle, gamma) > ratio) ^ supersonic
        low, high = np.where(tooLow, middle, low), np.where(tooLow, high, middle)

    return 0.5 * (low + high)

def writeInternalField(path: str, values: np.ndarray) -> None:

    '''Replace a field's uniform internal value with one value per cell.'''

    with open(path, encoding = 'utf-8') as handle:
        text = handle.read()
    if values.ndim == 1:
        body = '\n'.join(f'{value:.10g}' for value in values)
        listType = 'scalar'
    else:
        body = '\n'.join(f'({u:.10g} {v:.10g} {w:.10g})' for u, v, w in values)
        listType = 'vector'
    field = f'internalField   nonuniform List<{listType}>\n{len(values)}\n(\n{body}\n)\n;'
    text, replaced = re.subn(r'internalField\s+uniform\s+[^;]+;', lambda _: field, text, count = 1)
    if replaced != 1:
        raise ValueError(f'{path} has no uniform internal field to replace.')
    with open(path, 'w', encoding = 'utf-8', newline = '\n') as handle:
        handle.write(text)

def main(case: str) -> None:

    with open(os.path.join(case, 'reference', 'novaNozzle.json'), encoding = 'utf-8') as handle:
        reference = json.load(handle)
    with open(os.path.join(case, 'reference', 'case.json'), encoding = 'utf-8') as handle:
        caseSettings = json.load(handle)

    gas, geometry = reference['gas'], reference['geometry']
    gamma, gasConstant = gas['gamma'], gas['gasConstant']
    stagnationTemperature, chamberPressure = gas['stagnationTemperature'], gas['chamberPressure']
    wallX, wallR = np.asarray(geometry['wallX']), np.asarray(geometry['wallR'])
    wallSlope = np.gradient(wallR, wallX)

    centers = readCellCenters(os.path.join(case, '0', 'C'))
    x, y, z = centers.T
    radius = np.hypot(y, z)

    # Mach number from the station's area ratio, on the branch the side of the throat picks
    stationRadius = np.interp(x, wallX, wallR)
    mach = machFromAreaRatio((stationRadius / geometry['throatRadius'])**2, gamma, x > geometry['throatX'])

    temperature = stagnationTemperature / (1.0 + 0.5 * (gamma - 1.0) * mach**2)
    pressure = chamberPressure * (temperature / stagnationTemperature)**(gamma / (gamma - 1.0))
    speed = mach * np.sqrt(gamma * gasConstant * temperature)

    # Flow angle from zero on the axis to the wall's own angle at the wall. The mesh's wall sits
    # radialScale out from the contour, so the cell's height in the section is taken against that.
    height = np.clip(radius / (caseSettings['radialScale'] * stationRadius), 0.0, 1.0)
    angle = np.arctan(height * np.interp(x, wallX, wallSlope))
    radial = speed * np.sin(angle)
    velocity = np.column_stack([speed * np.cos(angle), radial * y / radius, radial * z / radius])

    writeInternalField(os.path.join(case, '0', 'p'), pressure)
    writeInternalField(os.path.join(case, '0', 'T'), temperature)
    writeInternalField(os.path.join(case, '0', 'U'), velocity)

    print(f'{len(x)} cells initialized: Mach {mach.min():.4f} to {mach.max():.4f}, '
          f'pressure {pressure.min():.6g} to {pressure.max():.6g} Pa')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
