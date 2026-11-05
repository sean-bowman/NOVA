# -- Verification Figures: Turbine Exhaust and the Extension Film -- #

'''

Figures that show the gas generator model and the films over an extension behaving as intended.

1. **The gas generator and its turbine exhaust against mixture ratio**, for LOX/LH2, LOX/CH4 and
   LOX/RP-1 at 8 MPa through a turbine of pressure ratio 16 and efficiency 0.6. The turbine inlet
   and exhaust temperatures are drawn with the condensed carbon CEA's equilibrium forms, and the
   F-1's published gas generator point is marked against the RP-1 curve.
2. **The extension of a methalox first stage with and without a turbine exhaust film**: the drive
   and the solved wall temperature with no film, and with the exhaust film under each closure.
3. **Film flow against the extension's peak temperature**, sweeping the turbine exhaust flow under
   both closures.
4. **The Sellers stacking** of the turbine exhaust film and a dumped methane film downstream of it.

The first stage is a sea-level LOX/CH4 engine: 500 kN at 10 MPa and a mixture ratio of 3.5, area
ratio 25, methane-cooled to an area ratio of 3, a 1.5 kg/s methane chamber film at 350 K, and a
C103 extension beyond. Its gas generator burns LOX/CH4 at 0.35 and 10 MPa through a turbine of
pressure ratio 10, and 5 kg/s of its exhaust enters a slot at the jacket joint, as the F-1's did.
The stacking figure adds a second slot of 1 kg/s of methane at 300 K at an area ratio of 8.

These are verification figures, not validations. The film closures are unvalidated on an
extension (extensionFilm.py) and the hydrocarbon gas generator runs hot at equilibrium
(turbineExhaust.py); the figures show the models doing what they are written to do.

Run from the NOVA root:

    python validation/coolingCircuits/phase2Verification.py [--reuse]

Author: Sean Bowman

'''

import copy
import dataclasses
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
from NOVA.errors import ConvergenceFailureError
from NOVA.extensionFilm import ExtensionFilmState, solveExtensionFilm
from NOVA.radiativeCooling import radiativeNozzleExtension
from NOVA.turbineExhaust import turbineExhaustState

outputFolder = os.path.join(here, 'phase2')
colors = palette.colors('dark')
plt.rcParams.update(palette.matplotlibStyle('dark'))
plt.rcParams.update({'font.size': 9, 'axes.grid': True, 'grid.alpha': 0.4})

EXHAUSTSLOT = {'areaRatio': 3.0, 'slotHeight': 0.015, 'source': 'turbineExhaust'}
DUMPSLOT = {'areaRatio': 8.0, 'slotHeight': 0.004, 'source': 'species', 'species': 'Methane',
            'massFlow': 1.0, 'temperature': 300.0}
METHANESTAGE = {'Fuel': 'LCH4', 'Oxidizer': 'LOX', 'OFRatio': 3.5, 'fuelInitialTemperature': 111.7,
                'chamberPressure': 10.0e6, 'thrust': 500000.0, 'expansionRatio': 25.0,
                'chamberDiameter': 0.34, 'plumeAmbientPressure': None, 'plumeFieldReach': None,
                'coolant': 'Methane', 'coolantInitialTemperature': 115.0,
                'coolantInitialPressure': 20.0e6, 'coolantMassFlow': 33.0, 'nChannel': 120,
                'filmCooling': True, 'filmCoolant': 'Methane', 'filmMassFlow': 1.5,
                'filmInletTemperature': 350.0, 'makeInletVolute': False, 'makeOutletVolute': False,
                'makeRadiativeExtension': True, 'gasGeneratorMixtureRatio': 0.35,
                'gasGeneratorPressure': 10.0e6, 'turbinePressureRatio': 10.0,
                'turbineEfficiency': 0.6, 'turbineExhaustMassFlow': 5.0,
                'extensionFilmSlots': [EXHAUSTSLOT]}

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

def filmState(nozzle, **changes) -> ExtensionFilmState:

    '''The nozzle's extension film state, with fields changed.'''

    state = ExtensionFilmState()
    for name in ExtensionFilmState.__dataclass_fields__:
        setattr(state, name, copy.deepcopy(getattr(nozzle, name, None)))
    for name, value in changes.items():
        setattr(state, name, value)
    return state

def extensionWall(nozzle, drive):

    '''The extension's solved wall under a given drive.'''

    shell, arguments = nozzle.radiativeExtensionInputs()
    arguments['recoveryTemperature'] = np.asarray(drive, dtype = float)
    return radiativeNozzleExtension(shell, **arguments)

def gasGeneratorFigure() -> str:

    '''Figure 1: gas generator and turbine exhaust temperature against mixture ratio.'''

    propellants = (('LH2', 'LOX/LH2', np.linspace(0.5, 1.4, 10), colors['blue']),
                   ('CH4', 'LOX/CH4', np.linspace(0.3, 0.6, 7), colors['green']),
                   ('RP-1', 'LOX/RP-1', np.linspace(0.25, 0.6, 8), colors['accent']))
    figure, (axis, carbonAxis) = plt.subplots(1, 2, figsize = (12.0, 4.2), constrained_layout = True)
    for fuel, label, ratios, color in propellants:
        # CEA's frozen expansion fails on the most carbon-laden gases; those points are refused
        # by the module and left out here
        solved = []
        for ratio in ratios:
            try:
                solved.append((ratio, turbineExhaustState(fuel, 'LOX', ratio, 8.0e6, 16.0, 0.6, 1.0)))
            except ConvergenceFailureError:
                continue
        ratios = np.array([ratio for ratio, _ in solved])
        states = [state for _, state in solved]
        axis.plot(ratios, [state.gasGeneratorTemperature for state in states], color = color,
                  linewidth = 2.0, label = f'{label} turbine inlet')
        axis.plot(ratios, [state.temperature for state in states], color = color, linestyle = '--',
                  label = f'{label} exhaust')
        carbonAxis.plot(ratios, [100.0 * state.condensedMassFraction for state in states],
                        color = color, linewidth = 2.0, label = label)
    axis.plot(0.416, 1063.0, marker = '*', markersize = 13, color = colors['red'], linestyle = 'none',
              label = 'F-1 gas generator, published (1453 F)')
    axis.set_xlabel('Gas generator mixture ratio [-]')
    axis.set_ylabel('Temperature [K]')
    axis.legend(fontsize = 6.5, loc = 'lower right')
    axis.set_title('Equilibrium gas generator at 8 MPa, frozen through PR 16 at efficiency 0.6')
    carbonAxis.set_xlabel('Gas generator mixture ratio [-]')
    carbonAxis.set_ylabel('Condensed carbon at equilibrium [% by mass]')
    carbonAxis.legend(fontsize = 8)
    carbonAxis.set_title('Graphite a real gas generator does not form in its residence time')
    path = os.path.join(outputFolder, 'gasGeneratorExhaust.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def extensionFigure(nozzle) -> str:

    '''Figure 2: the extension's drive and wall with and without the exhaust film.'''

    x = 1000.0 * np.asarray(nozzle.xExtension)
    recovery = np.asarray(nozzle.extensionNearWallRecoveryTemperature)
    chamberOnly = solveExtensionFilm(filmState(nozzle, extensionFilmSlots = []))
    cases = [('No film', recovery, colors['red']),
             ('Chamber film only, ' + chamberOnly.closure, chamberOnly.extensionDrivingTemperature,
              colors['textMuted'])]
    for closure, color in (('hatchPapell', colors['accent']), ('sp8124Entrainment', colors['blue'])):
        film = solveExtensionFilm(filmState(nozzle, extensionFilmModel = closure))
        cases.append((f'Chamber and exhaust films, {closure}', film.extensionDrivingTemperature, color))

    figure, (driveAxis, wallAxis) = plt.subplots(1, 2, figsize = (12.0, 4.2), constrained_layout = True)
    for label, drive, color in cases:
        wall = extensionWall(nozzle, drive)
        driveAxis.plot(x, drive, color = color, label = label)
        wallAxis.plot(x, wall.extensionWallTemperature, color = color,
                      label = f'{label}: peak {wall.extensionPeakWallTemperature:.0f} K')
    limit = extensionWall(nozzle, recovery).extensionTemperatureLimit
    wallAxis.axhline(limit, color = colors['red'], linestyle = ':', linewidth = 1.0)
    wallAxis.text(x[-1], limit, f' C103 limit {limit:.0f} K', va = 'bottom', ha = 'right', fontsize = 8)
    slot = nozzle.extensionFilmSolution.layers[-1]
    for axis in (driveAxis, wallAxis):
        axis.axvline(1000.0 * nozzle.extensionFilmSolution.x[slot.injectionIndex], color = colors['border'])
        axis.set_xlabel('Axial position [mm]')
    driveAxis.set_ylabel('Driving temperature [K]')
    wallAxis.set_ylabel('Extension wall temperature [K]')
    driveAxis.legend(fontsize = 7)
    wallAxis.legend(fontsize = 7)
    exhaust = nozzle.turbineExhaust
    figure.suptitle(f'Methalox first stage extension, area ratio 3 to 25: {exhaust.massFlow:.0f} kg/s of '
                    f'turbine exhaust at {exhaust.temperature:.0f} K through a slot at the joint')
    path = os.path.join(outputFolder, 'extensionWithExhaustFilm.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def sweepFigure(nozzle) -> str:

    '''Figure 3: turbine exhaust flow against the extension's peak wall temperature.'''

    flows = np.array([0.5, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0])                  # [kg/s]
    figure, axis = plt.subplots(figsize = (7.0, 4.2), constrained_layout = True)
    for closure, color in (('hatchPapell', colors['accent']), ('sp8124Entrainment', colors['blue'])):
        peaks = []
        for flow in flows:
            exhaust = dataclasses.replace(nozzle.turbineExhaust, massFlow = float(flow))
            film = solveExtensionFilm(filmState(nozzle, extensionFilmModel = closure, turbineExhaust = exhaust))
            peaks.append(extensionWall(nozzle, film.extensionDrivingTemperature).extensionPeakWallTemperature)
        axis.plot(100.0 * flows / nozzle.engineMassFlow, peaks, marker = 'o', color = color, label = closure)
    limit = extensionWall(nozzle, nozzle.extensionFilmDrivingTemperature).extensionTemperatureLimit
    axis.axhline(limit, color = colors['red'], linestyle = ':', label = f'C103 limit {limit:.0f} K')
    axis.set_xlabel('Turbine exhaust film flow [% of chamber flow]')
    axis.set_ylabel('Peak extension wall temperature [K]')
    axis.set_title('Methalox first stage: exhaust slot at the jacket joint, area ratio 3')
    axis.legend(fontsize = 8)
    path = os.path.join(outputFolder, 'exhaustFlowSweep.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def stackingFigure(nozzle) -> str:

    '''Figure 4: the exhaust film and a dumped methane film, each alone and stacked.'''

    film = solveExtensionFilm(filmState(nozzle, extensionFilmSlots = [EXHAUSTSLOT, DUMPSLOT]))
    joint = film.jointIndex
    x = 1000.0 * film.x[joint:]
    figure, axis = plt.subplots(figsize = (10.0, 4.2), constrained_layout = True)
    axis.plot(x, film.recoveryTemperature[joint:], color = colors['red'], label = 'Recovery temperature')
    for layer, color in zip([layer for layer in film.layers if layer.source != 'chamber'],
                            (colors['blue'], colors['green'])):
        axis.plot(x, layer.result.drivingTemperature[joint:], color = color, linestyle = '--',
                  label = f'{layer.name} alone ({layer.massFlow:.2g} kg/s at {layer.coolantTemperature:.0f} K)')
    axis.plot(x, film.drivingTemperature[joint:], color = colors['accent'], linewidth = 2.4,
              label = f'Stacked, Sellers superposition ({film.closure})')
    axis.set_xlabel('Axial position [mm]')
    axis.set_ylabel('Driving temperature [K]')
    axis.legend(fontsize = 6.5, loc = 'lower right')
    axis.set_title('Turbine exhaust at the joint and dumped methane at area ratio 8, methalox first stage extension')
    path = os.path.join(outputFolder, 'filmStacking.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def main():

    os.makedirs(outputFolder, exist_ok = True)
    print('  wrote', gasGeneratorFigure())
    stage = solve('methaneStage', METHANESTAGE)
    print('  wrote', extensionFigure(stage))
    print('  wrote', sweepFigure(stage))
    print('  wrote', stackingFigure(stage))

if __name__ == '__main__':
    main()
