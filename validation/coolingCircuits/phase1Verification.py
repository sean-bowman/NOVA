# -- Verification Figures: Coolant March Order, Direction and Flow Accounting -- #

'''

Figures that show the sizing march running the jacket in either direction, and the propellant
accounting that bounds a jacket's flow.

1. **The reflection check.** A uniform barrel, a constant radius wall under a uniform gas state
   with channels of one fixed size, describes the same problem either way the coolant runs, mirrored
   about the barrel's midpoint. The coflow solution is drawn over the counterflow one reflected;
   the two must agree to round-off. This is the closed-form check on `coolantMarchOrder`: any part of
   the march that still reads the wall in wall order rather than coolant order breaks the mirror.
2. **The shipped jacket run both ways.** The LOX/LH2 nozzle sized counterflow, its shipped
   direction, and coflow. The coolant temperature, hot wall temperature and pressure are drawn
   along the wall, with the inlet and outlet volutes marked where each direction places them.
3. **The propellant accounting.** The chamber flow of each propellant for the shipped engine and
   for the F-1 operating point (2578 kg/s at a mixture ratio of 2.27, 70 percent of the fuel
   through the tubes), split into the jacket's share and the bypass, with the chamber film drawn
   at the injector marked against the fuel it comes out of.

These are verification figures, not validations. The reflection is an identity the march must
satisfy, held to a relative 1e-9 in tests/testFlowDirection.py; the accounting is arithmetic, held
to its identities in tests/testFlowAccounting.py. The jacket heat transfer itself carries the
validation status stated in regenThermal.py.

Run from the NOVA root:

    python validation/coolingCircuits/phase1Verification.py [--reuse]

The two shipped runs are solved in sequence because RocketCEA cannot run two solves at once.
Figures are written beside this script, under phase1/.

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
sys.path.insert(0, os.path.join(root, 'tests'))

from NOVA import Nozzle, palette
from NOVA.flowAccounting import accountForFlows
from testFlowDirection import solveBarrel

outputFolder = os.path.join(here, 'phase1')
colors = palette.colors('dark')
plt.rcParams.update(palette.matplotlibStyle('dark'))
plt.rcParams.update({'font.size': 9, 'axes.grid': True, 'grid.alpha': 0.4})

def solve(name: str, overrides: dict):

    '''Run the shipped configuration with overrides, or load the pickle a previous run left.'''

    picklePath = os.path.join(outputFolder, f'{name}.pkl')
    if '--reuse' in sys.argv and os.path.isfile(picklePath):
        with open(picklePath, 'rb') as handle:
            return pickle.load(handle)

    with open(os.path.join(root, 'src', 'NOVA', 'assets', 'NOVANozzle.json'), encoding = 'utf-8') as handle:
        config = json.load(handle)
    config.update({'plotsEnabled': False, 'export': False, 'filename': name,
                   'plumeAmbientPressure': None, 'plumeFieldReach': None})
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

def reflectionFigure() -> str:

    '''Figure 1: coflow against counterflow reflected, on a uniform barrel.'''

    counterflow = solveBarrel('counterflow', outputFolder)
    coflow = solveBarrel('coflow', outputFolder)
    x = 1000.0 * np.asarray(coflow.xRegenNozzleTrimmed)    # [mm]

    panels = (('wallTemperature', 'Hot wall temperature [K]', 1.0),
              ('temperature', 'Coolant temperature [K]', 1.0),
              ('pressure', 'Coolant pressure [MPa]', 1.0e-6))
    figure, axes = plt.subplots(1, 3, figsize = (12.0, 3.8), constrained_layout = True)
    worst = 0.0
    for axis, (key, label, scale) in zip(axes, panels):
        mirrored = np.asarray(counterflow.channelThermalResults[key])[::-1]
        direct = np.asarray(coflow.channelThermalResults[key])
        worst = max(worst, float(np.max(np.abs(direct - mirrored) / np.abs(mirrored))))
        axis.plot(x, scale * np.asarray(counterflow.channelThermalResults[key]), color = colors['textMuted'],
                  linestyle = ':', label = 'Counterflow, as solved')
        axis.plot(x, scale * mirrored, color = colors['accent'], linewidth = 2.6,
                  label = 'Counterflow, reflected')
        axis.plot(x, scale * direct, color = colors['blue'], linestyle = 'none', marker = 'o',
                  markersize = 3.5, label = 'Coflow')
        axis.set_xlabel('Axial position [mm]')
        axis.set_ylabel(label)
    axes[0].legend(loc = 'best', fontsize = 8)
    figure.suptitle(f'Uniform barrel, 24 stations, 60 fixed 2 mm channels: coflow matches counterflow '
                    f'reflected to a relative {worst:.1e}')
    path = os.path.join(outputFolder, 'reflectionCheck.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def directionFigure(counterflow, coflow) -> str:

    '''Figure 2: the shipped jacket sized counterflow and coflow.'''

    panels = (('temperature', 'Coolant temperature [K]', 1.0),
              ('wallTemperature', 'Hot wall temperature [K]', 1.0),
              ('pressure', 'Coolant pressure [MPa]', 1.0e-6))
    figure, axes = plt.subplots(1, 3, figsize = (12.5, 4.0), constrained_layout = True)
    for nozzle, color, name in ((counterflow, colors['accent'], 'Counterflow'),
                                (coflow, colors['blue'], 'Coflow')):
        x = 1000.0 * np.asarray(nozzle.xRegenNozzleTrimmed)
        for axis, (key, label, scale) in zip(axes, panels):
            axis.plot(x, scale * np.asarray(nozzle.channelThermalResults[key]), color = color, label = name)
            axis.set_xlabel('Axial position [mm]')
            axis.set_ylabel(label)
        for volute, marker, role in ((nozzle.inletVolute, 'v', 'inlet'), (nozzle.outletVolute, '^', 'outlet')):
            if volute is None:
                continue
            ends = np.asarray(nozzle.channelThermalResults['temperature'])
            station = int(np.argmin(np.abs(np.asarray(nozzle.xRegenNozzleTrimmed) - volute.axialOffset)))
            axes[0].plot(1000.0 * volute.axialOffset, ends[station], marker = marker, color = color,
                         markersize = 9, linestyle = 'none', label = f'{name} {role} volute')
    axes[0].legend(loc = 'best', fontsize = 7)
    axes[1].axhline(counterflow.maxWallTemperature, color = colors['red'], linestyle = '--', linewidth = 1.0)
    for axis in axes:
        axis.axvline(0.0, color = colors['border'], linewidth = 0.8)
    summary = (f'Counterflow: exit {counterflow.coolantExitTemperature:.0f} K, drop '
               f'{1e-6 * (counterflow.coolantInitialPressure - counterflow.coolantExitPressure):.2f} MPa.  '
               f'Coflow: exit {coflow.coolantExitTemperature:.0f} K, drop '
               f'{1e-6 * (coflow.coolantInitialPressure - coflow.coolantExitPressure):.2f} MPa')
    figure.suptitle(f'Shipped LOX/LH2 jacket, 3.4 kg/s hydrogen from 30 K, throat at 0 mm.  {summary}')
    path = os.path.join(outputFolder, 'shippedJacketBothDirections.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def accountingFigure(shipped) -> str:

    '''Figure 3: each engine's propellant flows, the jacket's share and the film drawn.'''

    engines = (
        ('Shipped LOX/LH2', accountForFlows(shipped.engineMassFlow, shipped.OFRatio, 'fuel',
                                            coolantMassFlow = shipped.coolantMassFlow,
                                            filmMassFlow = shipped.filmMassFlow), shipped.filmMassFlow),
        ('F-1 operating point', accountForFlows(2578.0, 2.27, 'fuel', coolantBypassFraction = 0.30), None))

    figure, axes = plt.subplots(1, 2, figsize = (12.0, 3.4), constrained_layout = True)
    for axis, (name, account, film) in zip(axes, engines):
        rows = (('Fuel', account.fuelMassFlow), ('Oxidizer', account.oxidizerMassFlow))
        for row, (label, flow) in enumerate(rows):
            if label == 'Fuel':
                axis.barh(row, account.coolantMassFlow, color = colors['accent'], label = 'Through the jacket')
                axis.barh(row, flow - account.coolantMassFlow, left = account.coolantMassFlow,
                          color = colors['accentMuted'], label = 'Bypass to the injector')
                filmNote = f', film {film:.2g}' if film else ''
                axis.text(flow, row, f'  {flow:.4g} kg/s, jacket {account.coolantMassFlow:.4g} '
                          f'({100.0 * (1.0 - account.coolantBypassFraction):.1f} %){filmNote}',
                          va = 'center', fontsize = 8, color = colors['text'])
            else:
                axis.barh(row, flow, color = colors['blue'], label = 'Oxidizer to the injector')
                axis.text(flow, row, f'  {flow:.4g} kg/s', va = 'center', fontsize = 8, color = colors['text'])
        if film:
            axis.plot([account.fuelMassFlow - film, account.fuelMassFlow], [0.42, 0.42],
                      color = colors['green'], linewidth = 4.0, solid_capstyle = 'butt',
                      label = f'Chamber film {film:.2g} kg/s, drawn at the injector')
        axis.set_yticks([0, 1], ['Fuel', 'Oxidizer'])
        axis.set_xlim(0.0, 1.45 * max(account.fuelMassFlow, account.oxidizerMassFlow))
        axis.set_xlabel('Chamber mass flow [kg/s]')
        axis.set_title(name)
        axis.legend(loc = 'lower right', fontsize = 7)
    figure.suptitle('Propellant accounting: a jacket returned to the injector, and the film the '
                    'injector draws, fit inside the chamber flow of their propellant')
    path = os.path.join(outputFolder, 'propellantAccounting.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def main():

    os.makedirs(outputFolder, exist_ok = True)
    print('  wrote', reflectionFigure())
    counterflow = solve('shippedCounterflow', {})
    coflow = solve('shippedCoflow', {'jacketFlowDirection': 'coflow'})
    print('  wrote', directionFigure(counterflow, coflow))
    print('  wrote', accountingFigure(counterflow))

if __name__ == '__main__':
    main()
