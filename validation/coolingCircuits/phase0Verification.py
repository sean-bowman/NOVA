# -- Verification Figures: Defect Fixes and the Performance Summary -- #

'''

Figures that show three corrections behaving as intended on real nozzles.

1. **The slow-film slot limit.** A cold methane film injected through a slot at the jacket joint
   of a sea-level LOX/CH4 first stage, at a twentieth of the core velocity. The entrainment
   closure as SP-8124 writes it charges the coolant the core's kinetic energy and drives the wall
   below absolute zero at the slot; written at the film layer's own velocity it starts at the
   coolant's temperature. Both are drawn, with the extension wall temperature the corrected drive
   produces.
2. **The friction wall temperature.** The boundary layer march on the shipped nozzle is handed a
   wall temperature at every wall station. Matched by index fraction, a jacket ending at an area
   ratio of 3 is stretched over the whole bell; placed by axial position, the jacket covers its own
   section and the extension carries its solved shell temperature.
3. **Estimated against delivered performance.** The thrust coefficient of the shipped nozzle
   against back pressure, as the one-dimensional equilibrium and chamber-gas estimates and as the
   solved exit plane delivers it, with the named back pressures marked; and the exit plane's
   static pressure against the one-dimensional values.

These are verification figures, not validations. The film closures are unvalidated at rocket
conditions (filmCooling.py); the performance integral is verified against the closed form in
tests/testPerformance.py, and the solve itself is cross-checked in validation/openFoam.

Run from the NOVA root:

    python validation/coolingCircuits/phase0Verification.py

Two nozzles are solved, the shipped one and the first stage, in sequence because RocketCEA cannot
run two solves at once. Figures are written beside this script, under phase0/.

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

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(here))
sys.path.insert(0, os.path.join(root, 'src'))

from NOVA import Nozzle, palette
from NOVA.filmCooling import entrainmentAdiabaticWallTemperature, entrainmentFilmArrays, filmCoolantState
from NOVA.geometryTools import sizedThroatRadius
from NOVA.radiativeCooling import radiativeNozzleExtension

outputFolder = os.path.join(here, 'phase0')
colors = palette.colors('dark')
plt.rcParams.update(palette.matplotlibStyle('dark'))
plt.rcParams.update({'font.size': 9, 'axes.grid': True, 'grid.alpha': 0.4})

# A sea-level LOX/CH4 first stage: 500 kN at 10 MPa, area ratio 25, methane-cooled to an area ratio
# of 3 with a radiation-cooled extension beyond
METHANESTAGE = {'Fuel': 'LCH4', 'Oxidizer': 'LOX', 'OFRatio': 3.5, 'fuelInitialTemperature': 111.7,
                'chamberPressure': 10.0e6, 'thrust': 500000.0, 'expansionRatio': 25.0,
                'chamberDiameter': 0.34, 'plumeAmbientPressure': 101325.0, 'plumeFieldReach': None,
                'coolant': 'Methane', 'coolantInitialTemperature': 115.0,
                'coolantInitialPressure': 20.0e6, 'coolantMassFlow': 33.0, 'nChannel': 120,
                'filmCooling': False, 'makeInletVolute': False, 'makeOutletVolute': False}

def solve(name: str, overrides: dict):

    '''Run the shipped configuration with overrides, or load the pickle a previous run left.'''

    picklePath = os.path.join(outputFolder, f'{name}.pkl')
    if '--reuse' in sys.argv and os.path.isfile(picklePath):
        with open(picklePath, 'rb') as handle:
            return pickle.load(handle)

    with open(os.path.join(root, 'src', 'NOVA', 'assets', 'NOVANozzle.json'), encoding = 'utf-8') as handle:
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

def fullWall(nozzle):

    '''The jacket and extension station arrays joined, so a film march sees the real throat.'''

    keep = nozzle.xRegenNozzle < nozzle.xExtension[0] - 1e-9

    def join(regen, extension):
        return np.concatenate([np.asarray(regen, float)[keep], np.asarray(extension, float)])

    arrays = dict(
        x = join(nozzle.xRegenNozzle, nozzle.xExtension),
        r = join(nozzle.rRegenNozzle, nozzle.rExtension),
        u = join(nozzle.regenSectionNearWallVelocity, nozzle.extensionNearWallVelocity),
        rho = join(nozzle.densityRegenSection, nozzle.densityExtension),
        T = join(nozzle.regenSectionNearWallTemperature, nozzle.extensionNearWallTemperature),
        M = join(nozzle.regenSectionNearWallMachNumber, nozzle.extensionNearWallMachNumber),
        recovery = join(nozzle.regenSectionNearWallRecoveryTemperature,
                        nozzle.extensionNearWallRecoveryTemperature),
        cp = join(nozzle.specificHeatRegenSection, nozzle.specificHeatExtension))
    arrays['total'] = arrays['T'] * (1.0 + 0.5 * (nozzle.chamberGamma - 1.0) * arrays['M']**2)
    arrays['fluxRatio'] = arrays['rho'] * arrays['u'] / (nozzle.engineMassFlow / (np.pi * arrays['r']**2))
    arrays['extension'] = slice(int(keep.sum()), None)
    return arrays

def slowFilmFigure(nozzle) -> str:

    '''Figure 1: the slow-film slot limit on the first stage's extension.'''

    wall = fullWall(nozzle)
    slotX, slotHeight, flow, coolantTemperature = float(nozzle.xExtension[0]), 0.004, 6.0, 272.0
    coolant = filmCoolantState('Methane', coolantTemperature, float(nozzle.extensionNearWallPressure[0]),
                               flow, slotHeight, float(nozzle.rExtension[0]))
    film = entrainmentFilmArrays(
        wall['x'], wall['r'], wall['u'], wall['rho'], wall['total'], wall['recovery'], wall['cp'],
        wall['fluxRatio'], slotX, slotHeight, nozzle.engineMassFlow, flow, coolant.density,
        coolant.velocity, coolant.viscosity, coolant.specificHeat, coolantTemperature,
        nozzle.OFRatio, 0.0,
        throatRadius = sizedThroatRadius(nozzle.rRegenNozzle, nozzle.nozzleScalingFactor))

    # The closure as the source writes it: the same effectiveness, the defect at the core velocity
    injection = film.injectionIndex
    sourceForm = np.array(wall['recovery'], dtype = float)
    for index in range(injection, wall['x'].size):
        sourceForm[index] = entrainmentAdiabaticWallTemperature(
            film.effectiveness[index], wall['total'][index], wall['recovery'][index],
            wall['cp'][index], coolant.specificHeat, coolantTemperature, 1.0)

    shell, arguments = nozzle.radiativeExtensionInputs()
    withoutFilm = radiativeNozzleExtension(shell, **arguments)
    arguments['recoveryTemperature'] = np.asarray(film.drivingTemperature)[wall['extension']]
    withFilm = radiativeNozzleExtension(shell, **arguments)

    extensionX = np.asarray(nozzle.xExtension) * 1e3
    figure, (left, right) = plt.subplots(1, 2, figsize = (11.0, 4.2))
    left.plot(extensionX, np.asarray(wall['recovery'])[wall['extension']], color = colors['textMuted'],
              label = 'No film: recovery temperature')
    left.plot(extensionX, sourceForm[wall['extension']], color = colors['red'], linestyle = '--',
              label = 'SP-8124 as written: defect at the core velocity')
    left.plot(extensionX, np.asarray(film.drivingTemperature)[wall['extension']], color = colors['accent'],
              label = 'Defect at the film layer velocity')
    left.axhline(0.0, color = colors['border'], linewidth = 0.8)
    left.set_xlabel('Axial station [mm]')
    left.set_ylabel('Wall driving temperature [K]')
    left.set_title(f'6 kg/s methane at 272 K, injection velocity ratio {film.injectionVelocityRatio:.2f}')
    left.legend(fontsize = 8)

    right.plot(extensionX, withoutFilm.extensionWallTemperature, color = colors['textMuted'],
               label = 'No film')
    right.plot(extensionX, withFilm.extensionWallTemperature, color = colors['accent'],
               label = 'Film, corrected drive')
    right.axhline(float(withoutFilm.extensionTemperatureLimit), color = colors['red'], linestyle = ':',
                  label = 'C103 limit')
    right.set_xlabel('Axial station [mm]')
    right.set_ylabel('Extension wall temperature [K]')
    right.set_title('Radiation-cooled C103 extension')
    right.legend(fontsize = 8)

    figure.suptitle('The slow-film slot limit, LOX/CH4 first stage, 500 kN, area ratio 25')
    figure.tight_layout()
    path = os.path.join(outputFolder, 'slowFilmSlotLimit.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    print(f'  slot: source form {sourceForm[injection]:.1f} K, corrected '
          f'{film.drivingTemperature[injection]:.1f} K; extension peak with film '
          f'{withFilm.extensionPeakWallTemperature:.0f} K against {withoutFilm.extensionPeakWallTemperature:.0f} K')
    return path

def frictionFigure(nozzle) -> str:

    '''Figure 2: the wall temperature the boundary layer march is handed, before and after.'''

    from NOVA.boundaryLayer import wallTemperatureProfile

    results = nozzle.channelThermalResults
    wallX = np.asarray(nozzle.xNozzleWall, dtype = float)
    jacket = np.asarray(nozzle.channelWallTemperature, dtype = float)
    byIndex = np.interp(np.linspace(0.0, 1.0, wallX.size), np.linspace(0.0, 1.0, jacket.size), jacket)
    byPosition = wallTemperatureProfile(wallX, results['xHotWall3D'], results['wallTemperature'],
                                        nozzle.xExtension, nozzle.extensionWallTemperature)

    figure, axes = plt.subplots(figsize = (8.0, 4.2))
    axes.plot(wallX * 1e3, byIndex, color = colors['red'], linestyle = '--',
              label = 'Matched by index fraction')
    axes.plot(wallX * 1e3, byPosition, color = colors['accent'], label = 'Placed by axial position')
    axes.axvline(float(nozzle.xExtension[0]) * 1e3, color = colors['border'], linestyle = ':')
    axes.text(float(nozzle.xExtension[0]) * 1e3 + 8.0, 300.0, 'jacket ends,\narea ratio 3',
              color = colors['textMuted'], fontsize = 8)
    axes.set_xlabel('Axial station [mm]')
    axes.set_ylabel('Wall temperature [K]')
    axes.set_title('Wall temperature handed to the boundary layer march, shipped nozzle')
    axes.legend(fontsize = 8)
    figure.tight_layout()
    path = os.path.join(outputFolder, 'frictionWallTemperature.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def performanceFigure(nozzle) -> str:

    '''Figure 3: estimated against delivered thrust coefficient, and the exit plane pressure.'''

    summary = nozzle.performance
    pressure = np.linspace(0.0, 110.0e3, 200)
    epsilon, chamber = summary.areaRatio, float(nozzle.chamberPressure)

    def line(vacuum):
        return vacuum - pressure * epsilon / chamber

    figure, (left, right) = plt.subplots(1, 2, figsize = (11.5, 4.4))
    for label, table, color, style in (
            ('1D equilibrium', summary.thrustCoefEquilibrium, colors['blue'], '-'),
            ('1D chamber gas', summary.thrustCoefChamberGas, colors['textMuted'], '-'),
            ('Delivered', summary.thrustCoefDelivered, colors['accent'], '-'),
            ('Delivered after friction', summary.thrustCoefDeliveredFrictionCorrected, colors['accent'], '--')):
        left.plot(pressure / 1e3, line(table['vacuum']), color = color, linestyle = style, label = label)
    for name, value in summary.backPressures.items():
        left.axvline(value / 1e3, color = colors['border'], linewidth = 0.8)
        left.text(value / 1e3 + 1.0, 1.95, name, rotation = 90, va = 'top', fontsize = 7,
                  color = colors['textMuted'])
    left.set_xlabel('Back pressure [kPa]')
    left.set_ylabel('Thrust coefficient [-]')
    left.set_title('Thrust coefficient against back pressure')
    left.legend(fontsize = 8, loc = 'lower left')

    radius = np.asarray(nozzle.exitPlaneRadius) * float(nozzle.nozzleScalingFactor) * 1e3
    right.plot(radius, np.asarray(nozzle.exitPlanePressure) / 1e3, color = colors['accent'],
               label = 'Solved exit plane')
    right.axhline(summary.exitPressureEquilibrium / 1e3, color = colors['blue'], label = '1D equilibrium')
    right.axhline(summary.exitPressureChamberGas / 1e3, color = colors['textMuted'], label = '1D chamber gas')
    right.axhline(summary.exitPressureDelivered / 1e3, color = colors['accent'], linestyle = '--',
                  label = 'Mass average of the plane')
    right.set_xlabel('Radius [mm]')
    right.set_ylabel('Static pressure [kPa]')
    right.set_title('Exit plane static pressure, wall to axis')
    right.legend(fontsize = 8)

    figure.suptitle(f'Shipped nozzle: delivered vacuum C_F {summary.thrustCoefDelivered["vacuum"]:.3f} '
                    f'against {summary.thrustCoefChamberGas["vacuum"]:.3f} one-dimensional, '
                    f'efficiency {summary.nozzleEfficiency:.4f}')
    figure.tight_layout()
    path = os.path.join(outputFolder, 'performanceEstimatedDelivered.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def main():

    os.makedirs(outputFolder, exist_ok = True)
    shipped = solve('shipped', {})
    print('  wrote', performanceFigure(shipped))
    print('  wrote', frictionFigure(shipped))
    methane = solve('methaneStage', METHANESTAGE)
    print('  wrote', slowFilmFigure(methane))

if __name__ == '__main__':
    main()
