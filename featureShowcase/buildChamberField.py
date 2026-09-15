'''
Mach, pressure and temperature through the combustion chamber and the converging section.

The chamber and the converging section are subsonic, so there is no characteristics mesh there and
nothing solves them. What is drawn is the quasi one-dimensional answer: at each axial station the
local area ratio fixes a Mach number, and that value is held across the whole cross section.

Every figure says so on its face. They sit beside the characteristics fields of the diverging
section, which ARE solved, and the two must not be read as the same kind of result.

The last figure makes the comparison explicit: the same one-dimensional construction continued past
the throat, against the characteristics solution over the same geometry. The difference between
them is what the mesh buys.

Run after runBaseCase.py:

    python featureShowcase/buildChamberField.py
'''
import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
from NOVA.characteristics import CharacteristicGas
from NOVA.contour import quasiOneDimensionalField

background = '#1a1e2a'
panel      = '#222735'
copper     = '#E0975A'
green      = '#86C06C'
ink        = '#E8E6E1'
muted      = '#8B93A7'
warn       = '#E8A0A0'

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': '#333A4D',
    'axes.grid': False, 'font.size': 9,
    'axes.titlesize': 11, 'axes.titleweight': 'bold', 'legend.framealpha': 0.0,
})

quantities = {
    'mach':        ('Mach number', '[-]', 1.0, 'viridis'),
    'pressure':    ('Static pressure', '[MPa]', 1e-6, 'magma'),
    'temperature': ('Static temperature', '[K]', 1.0, 'inferno'),
}

def savePanel(figure, name):
    path = os.path.join(here, f'{name}.png')
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print(f'  wrote {name}.png')
    return path

def drawChamberField(nozzle, quantity):
    '''One quantity over the chamber and converging section, up to the throat plane.'''
    label, unit, scale, colorMap = quantities[quantity]

    gas = CharacteristicGas(nozzle.chamberGamma, nozzle.chamberRGasConstant,
                            nozzle.chamberStagnationTemperature)
    wallX = np.asarray(nozzle.xNozzleWall, dtype = float)
    wallR = np.asarray(nozzle.rNozzleWall, dtype = float)
    throatIndex = int(np.argmin(wallR))

    # Up to and including the throat plane. Past it the flow is supersonic and solved, and drawing
    # the one-dimensional answer there would invite the two to be confused.
    upstream = slice(0, throatIndex + 1)
    field = quasiOneDimensionalField(wallX[upstream], wallR[upstream], gas,
                                     nozzle.chamberPressure,
                                     throatRadius = wallR[throatIndex], branch = 'subsonic')

    figure = plt.figure(figsize = (11, 5.0))
    grid = GridSpec(2, 1, height_ratios = [1.0, 0.05], hspace = 0.40, figure = figure)
    axes = figure.add_subplot(grid[0])

    # Mirror about the axis with the radial coordinate kept monotone from -R to +R, so contourf
    # sees a structured grid rather than one that doubles back on itself.
    x = np.concatenate([field['x'][:, ::-1], field['x']], axis = 1) * 1e3
    r = np.concatenate([-field['r'][:, ::-1], field['r']], axis = 1) * 1e3
    values = np.concatenate([field[quantity][:, ::-1], field[quantity]], axis = 1) * scale

    mesh = axes.contourf(x, r, values, levels = 60, cmap = colorMap)
    axes.plot(field['wallX'] * 1e3, field['wallR'] * 1e3, color = copper, lw = 1.6)
    axes.plot(field['wallX'] * 1e3, -field['wallR'] * 1e3, color = copper, lw = 1.6)
    axes.axvline(field['wallX'][-1] * 1e3, color = green, lw = 1.2, ls = '--')
    axes.text(field['wallX'][-1] * 1e3, 0.0, ' throat', color = green, fontsize = 8,
              va = 'center')

    axes.set_xlabel('Axial station [mm]')
    axes.set_ylabel('Radius [mm]')
    axes.set_title(f'{label} through the chamber and converging section, ONE DIMENSIONAL')
    axes.set_aspect('equal', adjustable = 'box')
    axes.grid(False)

    figure.colorbar(mesh, cax = figure.add_subplot(grid[1]), orientation = 'horizontal',
                    label = f'{label} {unit}')
    figure.text(0.012, 0.005,
                'Properties vary axially only. At each station the local area ratio fixes the '
                'subsonic Mach number and that value is held across the whole cross section. '
                'Nothing here is solved; the radial structure of a real converging flow, and the '
                'curvature of its sonic line, are absent by construction.',
                fontsize = 8, color = warn, va = 'bottom')
    return savePanel(figure, f'chamberField{quantity.capitalize()}')

def drawOneDimensionalAgainstTheMesh(nozzle):
    '''
    The same one-dimensional construction continued past the throat, against the characteristics
    solution over the same wall. What separates them is what the mesh is for.
    '''
    gas = CharacteristicGas(nozzle.chamberGamma, nozzle.chamberRGasConstant,
                            nozzle.chamberStagnationTemperature)
    wallX = np.asarray(nozzle.xNozzleWall, dtype = float)
    wallR = np.asarray(nozzle.rNozzleWall, dtype = float)
    throatIndex = int(np.argmin(wallR))

    field = quasiOneDimensionalField(wallX, wallR, gas, nozzle.chamberPressure,
                                     throatRadius = wallR[throatIndex], branch = 'auto')
    nearWallMach = np.asarray(nozzle.nozzleNearWallMachNumber, dtype = float)

    figure, axes = plt.subplots(1, 2, figsize = (14.0, 4.8))

    left = axes[0]
    left.plot(wallX * 1e3, field['mach1D'], color = green, lw = 2.0,
              label = 'one-dimensional at the local area')
    left.plot(wallX * 1e3, nearWallMach, color = copper, lw = 2.0,
              label = 'near-wall, from the characteristics solve')
    left.axvline(wallX[throatIndex] * 1e3, color = muted, lw = 1.0, ls = '--')
    left.set_xlabel('Axial station [mm]')
    left.set_ylabel('Mach number')
    left.set_title('Near-wall Mach number: solved against one-dimensional')
    left.grid(True, alpha = 0.25)
    left.legend(loc = 'upper left', fontsize = 8, labelcolor = ink)

    right = axes[1]
    diverging = slice(throatIndex + 1, len(wallX))
    difference = 100.0 * (nearWallMach[diverging] / field['mach1D'][diverging] - 1.0)
    right.plot(wallX[diverging] * 1e3, difference, color = copper, lw = 2.0)
    right.axhline(0.0, color = muted, lw = 1.0, ls = '--')
    right.set_xlabel('Axial station [mm]')
    right.set_ylabel('Near-wall Mach against one-dimensional [%]')
    right.set_title(f'The wall is not at the one-dimensional state\n'
                    f'worst departure {np.nanmax(np.abs(difference)):.1f} % over the '
                    f'diverging section')
    right.grid(True, alpha = 0.25)

    figure.suptitle('What the characteristics mesh buys over a one-dimensional solve',
                    fontsize = 13, fontweight = 'bold')
    figure.tight_layout(rect = [0, 0.06, 1, 0.94])
    figure.text(0.012, 0.045,
                'A one-dimensional solve has one state per station. A characteristics solve has a '
                'state per point, and the wall is not at the average of its plane. The gap on the '
                'right is why a design criterion applied at the wall, such as an exit pressure '
                'match, is not the same criterion applied to the flow.',
                fontsize = 8.5, color = ink, va = 'top')
    return savePanel(figure, 'oneDimensionalAgainstMesh')

def main():
    with open(os.path.join(here, 'showcaseBase.pkl'), 'rb') as handle:
        nozzle = pickle.load(handle)

    print('Rendering chamber and converging section fields')
    for quantity in quantities:
        drawChamberField(nozzle, quantity)
    drawOneDimensionalAgainstTheMesh(nozzle)

if __name__ == '__main__':
    main()
