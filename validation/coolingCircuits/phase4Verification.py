# -- Verification Figures: Two-Pass and One-and-a-Half-Pass Jackets -- #

'''

Figures that show the multi-pass circuits behaving as intended, and the check on the rib between
their passes.

1. **The rib conductance against a conduction solve.** The heat two neighboring circular channels
   exchange through the web between them, solved in two dimensions by finite differences
   (convection inside each channel, the hot wall below and the shell above, symmetry through the
   channel centers), against the slab conductance the march uses with each channel's half
   perimeter as its face. Over channel radii of 2 to 4 mm and coolant coefficients of 1e4 to
   1e5 W/m^2 K.
2. **Coolant along the jacket, per pass.** The reference LOX/LH2 jacket cut at an area ratio of 10:
   a single pass of 60 channels, a two-pass jacket of 30 down and 30 up, and a one-and-a-half-pass
   jacket of the same with its inlet at an area ratio of 3. Coolant temperature and pressure of
   each pass, the turnaround marked.
3. **Wall temperature per family, and the rib exchange.** The hot wall each family holds, and the
   rib heat each pass gains against the heat the wall gives it.
4. **The geometry.** The up and down channels around part of the circumference near the aft end,
   and the turnaround ring they meet in.

These are verification figures. The circuits are unvalidated as circuits (coolantCircuit.py); the
conduction solve is the check on the one approximation the coupling adds.

Run from the NOVA root:

    python validation/coolingCircuits/phase4Verification.py [--reuse]

Author: Sean Bowman

'''

import json
import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np
import scipy.sparse as sparse
from scipy.sparse.linalg import spsolve

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(here))
sys.path.insert(0, os.path.join(root, 'src'))

from NOVA import Nozzle, palette
from NOVA.regenThermal import ribExchangeConductance

outputFolder = os.path.join(here, 'phase4')
colors = palette.colors('dark')
plt.rcParams.update(palette.matplotlibStyle('dark'))
plt.rcParams.update({'font.size': 9, 'axes.grid': True, 'grid.alpha': 0.4})

JACKET = {'regenTruncationType': 'er', 'regenTruncationValue': 10.0, 'makeRadiativeExtension': False,
          'filmCooling': False, 'numCrossSections': 60, 'plumeAmbientPressure': None,
          'plumeFieldReach': None, 'makeInletVolute': False, 'makeOutletVolute': False}
CASES = {
    'singlePass':     {**JACKET, 'nChannel': 60},
    'twoPass':        {**JACKET, 'nChannel': 30, 'coolantCircuit': 'twoPass'},
    'oneAndHalfPass': {**JACKET, 'nChannel': 30, 'coolantCircuit': 'oneAndHalfPass',
                       'coolantInletAreaRatio': 3.0},
}

def solve(name: str, overrides: dict):

    '''Run the single-pass reference configuration with overrides, or load the pickle a previous run left.'''

    picklePath = os.path.join(outputFolder, f'{name}.pkl')
    if '--reuse' in sys.argv and os.path.isfile(picklePath):
        with open(picklePath, 'rb') as handle:
            return pickle.load(handle)

    with open(os.path.join(root, 'src', 'NOVA', 'assets', 'examples', 'novaSinglePass.json'), encoding = 'utf-8') as handle:
        config = json.load(handle)
    config.update({'plotsEnabled': False, 'export': False, 'filename': name})
    config.update(overrides)
    configPath = os.path.join(outputFolder, f'{name}.json')
    with open(configPath, 'w', encoding = 'utf-8', newline = '\n') as handle:
        json.dump(config, handle, indent = 2)

    original = Nozzle._getOutputRoot
    Nozzle._getOutputRoot = lambda self: outputFolder
    try:
        nozzle = Nozzle()
        nozzle.generateNozzle(configPath = configPath)
    finally:
        Nozzle._getOutputRoot = original

    with open(picklePath, 'wb') as handle:
        pickle.dump(nozzle, handle)
    return nozzle

def ribConduction(radius: float, pitch: float, conductivity: float, coefficient: float,
                  cells: int = 240, wallBelow: float = 0.001, roomAbove: float = 0.002) -> float:

    '''

    Heat per unit length and per kelvin between two neighboring channels' coolant [W/m K].

    The cell runs from one channel's center to the next, so both channel sections are halves at
    its edges and the edges are planes of symmetry. Below the channels is the hot wall, above
    them the shell, both adiabatic: conduction is linear, so the gas-side heat superposes and
    leaves the exchange alone. A cell inside a channel is coolant at its temperature; a face
    between coolant and metal carries half a cell of conduction in series with the convection,
    scaled so the faces of each channel add up to its true half-perimeter.

    '''

    height = wallBelow + 2.0 * radius + roomAbove
    dx = pitch / cells
    rows = int(round(height / dx))
    centerHeight = wallBelow + radius
    x, y = np.meshgrid((np.arange(cells) + 0.5) * dx, (np.arange(rows) + 0.5) * dx, indexing = 'ij')
    inLeft = np.hypot(x, y - centerHeight) < radius
    inRight = np.hypot(x - pitch, y - centerHeight) < radius
    metal = ~(inLeft | inRight)
    index = -np.ones(x.shape, int)
    index[metal] = np.arange(metal.sum())
    neighbors = ((1, 0), (-1, 0), (0, 1), (0, -1))

    faces = {True: 0, False: 0}
    for i, j in zip(*np.nonzero(metal)):
        for di, dj in neighbors:
            a, b = i + di, j + dj
            if 0 <= a < cells and 0 <= b < rows and not metal[a, b]:
                faces[bool(inLeft[a, b])] += 1
    scale = {side: np.pi * radius / (count * dx) for side, count in faces.items()}

    entries, rhs, leftFaces = [], np.zeros(metal.sum()), []
    for i, j in zip(*np.nonzero(metal)):
        row, diagonal = index[i, j], 0.0
        for di, dj in neighbors:
            a, b = i + di, j + dj
            if not (0 <= a < cells and 0 <= b < rows):
                continue
            if metal[a, b]:
                entries.append((row, index[a, b], -conductivity))
                diagonal += conductivity
            else:
                left = bool(inLeft[a, b])
                conductance = scale[left] / (0.5 / conductivity + 1.0 / (coefficient * dx))
                diagonal += conductance
                if left:
                    rhs[row] += conductance
                    leftFaces.append((row, conductance))
        entries.append((row, row, diagonal))
    rowIndex, columnIndex, values = zip(*entries)
    matrix = sparse.csr_matrix((values, (rowIndex, columnIndex)), shape = (len(rhs), len(rhs)))
    temperature = spsolve(matrix, rhs)
    return float(sum(conductance * (1.0 - temperature[row]) for row, conductance in leftFaces))

def ribFigure() -> str:

    '''Figure 1: the slab rib conductance against the conduction solve.'''

    conductivity, rib = 300.0, 0.0015
    figure, axis = plt.subplots(figsize = (7.5, 4.2), constrained_layout = True)
    for coefficient, color in ((1.0e4, colors['blue']), (3.0e4, colors['accent']), (1.0e5, colors['green'])):
        radii = np.array([0.002, 0.0025, 0.003, 0.0035, 0.004])
        ratio = []
        for radius in radii:
            solved = ribConduction(radius, 2.0 * radius + rib, conductivity, coefficient)
            face = np.pi * radius
            slab = ribExchangeConductance(coefficient, coefficient, face, face, rib, conductivity)
            ratio.append(slab / solved)
        axis.plot(1e3 * radii, ratio, marker = 'o', color = color, label = f'h = {coefficient:.0e} W/m2 K')
    axis.axhline(1.0, color = colors['textMuted'], linestyle = ':')
    axis.set_xlabel('Channel radius [mm], 1.5 mm rib, GRCop-42 at 300 W/m K')
    axis.set_ylabel('Slab over conduction solve [-]')
    axis.set_title('Rib conductance between neighboring channels')
    axis.legend(fontsize = 8)
    path = os.path.join(outputFolder, 'ribConductance.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def passFigure(single, twoPass, oneAndHalf) -> str:

    '''Figure 2: coolant temperature and pressure of each pass along the jacket.'''

    figure, (temperatureAxis, pressureAxis) = plt.subplots(1, 2, figsize = (12.5, 4.3), constrained_layout = True)

    def wallX(state):
        return 1000.0 * np.asarray(state.xRegenNozzleTrimmed)

    results = single.channelThermalResults
    x = wallX(single.channelSizingSolution)
    temperatureAxis.plot(x, results['temperature'], color = colors['textMuted'], label = 'A, 60 channels')
    pressureAxis.plot(x, 1e-6 * np.asarray(results['pressure']), color = colors['textMuted'], label = 'A, 60 channels')
    for nozzle, color, name in ((twoPass, colors['accent'], 'C'), (oneAndHalf, colors['blue'], 'B')):
        circuit = nozzle.coolantCircuitSolution
        for passSolution, style in ((circuit.down, '--'), (circuit.up, '-')):
            xPass = wallX(passSolution.state)
            temperatureAxis.plot(xPass, passSolution.results['temperature'], color = color, linestyle = style,
                                 label = f'{name}, {passSolution.name} pass')
            pressureAxis.plot(xPass, 1e-6 * np.asarray(passSolution.results['pressure']), color = color,
                              linestyle = style, label = f'{name}, {passSolution.name} pass')
        pressureAxis.annotate(f'turnaround {1e-3*circuit.turnaround.pressureDrop:.0f} kPa',
                              (1000.0 * circuit.turnaround.axialPosition, 1e-6 * float(circuit.up.state.coolantInitialPressure)),
                              fontsize = 7, color = color, ha = 'right')
    temperatureAxis.set_ylabel('Coolant temperature [K]')
    pressureAxis.set_ylabel('Coolant pressure [MPa]')
    for axis in (temperatureAxis, pressureAxis):
        axis.set_xlabel('Axial position [mm]')
        axis.legend(fontsize = 7)
    figure.suptitle('Reference LOX/LH2 jacket to area ratio 10, 3.4 kg/s hydrogen from 30 K: single pass against '
                    'two pass (C) and one and a half pass from area ratio 3 (B)')
    path = os.path.join(outputFolder, 'passesAlongJacket.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def wallFigure(twoPass, oneAndHalf) -> str:

    '''Figure 3: hot wall per family, and the rib heat against the wall heat.'''

    figure, axes = plt.subplots(2, 2, figsize = (12.5, 6.6), constrained_layout = True)
    for row, (nozzle, name) in enumerate(((twoPass, 'C, two pass'), (oneAndHalf, 'B, one and a half pass'))):
        circuit = nozzle.coolantCircuitSolution
        wallAxis, ribAxis = axes[row]
        for passSolution, color in ((circuit.down, colors['blue']), (circuit.up, colors['accent'])):
            x = 1000.0 * np.asarray(passSolution.state.xRegenNozzleTrimmed)
            wallAxis.plot(x, passSolution.results['wallTemperature'], color = color, label = f'{passSolution.name} family')
            ribAxis.plot(x, passSolution.results['heatTransfer'], color = color, label = f'{passSolution.name}: from the wall')
            ribAxis.plot(x, passSolution.results['ribHeatTransfer'], color = color, linestyle = '--',
                         label = f'{passSolution.name}: across the rib')
        wallAxis.axhline(nozzle.maxWallTemperature, color = colors['red'], linestyle = ':')
        wallAxis.set_ylabel('Hot wall temperature [K]')
        ribAxis.set_ylabel('Heat per channel per station [W]')
        downRib, upRib = circuit.ribHeatBalance()
        wallAxis.set_title(name)
        ribAxis.set_title(f'{name}: rib heat down {1e-3*downRib:+.1f} kW, up {1e-3*upRib:+.1f} kW')
        for axis in (wallAxis, ribAxis):
            axis.set_xlabel('Axial position [mm]')
            axis.legend(fontsize = 7)
    path = os.path.join(outputFolder, 'wallAndRibExchange.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def geometryFigure(nozzle) -> str:

    '''Figure 4: up and down channels near the aft end, and the turnaround ring.'''

    circuit = nozzle.coolantCircuitSolution
    figure = plt.figure(figsize = (10.0, 6.5), constrained_layout = True)
    axis = figure.add_subplot(projection = '3d')
    upPitch = 2.0 * np.pi / circuit.up.channelCount
    window = slice(-12, None)
    for k in range(-2, 3):
        roll = k * upPitch
        cosine, sine = np.cos(roll), np.sin(roll)
        for x, y, z, color in ((nozzle.xChannel, nozzle.yChannel, nozzle.zChannel, colors['accent']),
                               (nozzle.xChannelDown, nozzle.yChannelDown, nozzle.zChannelDown, colors['blue'])):
            axis.plot_surface(1000.0 * x[:, window], 1000.0 * (y[:, window] * cosine - z[:, window] * sine),
                              1000.0 * (y[:, window] * sine + z[:, window] * cosine), color = color,
                              linewidth = 0.0, shade = True)
    around = np.abs(np.angle(np.exp(1j * np.arctan2(nozzle.zTurnaround, nozzle.yTurnaround)))) < 3.0 * upPitch
    xRing, yRing, zRing = (np.where(around, value, np.nan) for value in (nozzle.xTurnaround, nozzle.yTurnaround, nozzle.zTurnaround))
    axis.plot_surface(1000.0 * xRing, 1000.0 * yRing, 1000.0 * zRing, color = colors['green'], alpha = 0.5, linewidth = 0.0)
    axis.set_xlabel('Axial position [mm]')
    axis.set_ylabel('y [mm]')
    axis.set_zlabel('z [mm]')
    axis.view_init(elev = 35, azim = -60)
    axis.set_title(f'Two-pass jacket near its aft end: up channels, down channels and the turnaround ring '
                   f'({1e3*circuit.turnaround.sectionRadius:.1f} mm section)')
    path = os.path.join(outputFolder, 'twoPassGeometry.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def main():

    os.makedirs(outputFolder, exist_ok = True)
    print('  wrote', ribFigure())
    solved = {name: solve(name, overrides) for name, overrides in CASES.items()}
    print('  wrote', passFigure(solved['singlePass'], solved['twoPass'], solved['oneAndHalfPass']))
    print('  wrote', wallFigure(solved['twoPass'], solved['oneAndHalfPass']))
    print('  wrote', geometryFigure(solved['twoPass']))

if __name__ == '__main__':
    main()
