# -- Verification Figures: The Extension's Own Coolant Circuit -- #

'''

Figures that show a separately cooled extension behaving as intended.

**The wall along the whole nozzle.** The shipped LOX/LH2 nozzle with its chamber jacket cut at an
area ratio of 3 and carrying 3.1 kg/s of hydrogen, cooled beyond three ways:

1. a radiation-cooled C103 shell from the joint to the exit;
2. a circuit of its own from the joint to an area ratio of 12, 0.5 kg/s of hydrogen at 40 K run
   coflow through 90 channels and returned to the feed, with the shell beyond;
3. the same circuit with its hydrogen dumped as a film over the shell at its far end (Vulcain 2).

The hot wall of each, from the chamber jacket through the extension circuit to the shell, with the
shell's limit; the extension circuit's coolant; and the drive the dumped film leaves over the
shell.

These are verification figures. The extension circuit inherits the chamber march's validation
status, and the film over the shell the film closures' (extensionFilm.py).

Run from the NOVA root:

    python validation/coolingCircuits/phase5Verification.py [--reuse]

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

outputFolder = os.path.join(here, 'phase5')
colors = palette.colors('dark')
plt.rcParams.update(palette.matplotlibStyle('dark'))
plt.rcParams.update({'font.size': 9, 'axes.grid': True, 'grid.alpha': 0.4})

# The chamber jacket carries 3.1 kg/s so a returned extension circuit's 0.5 kg/s fits within the
# 3.61 kg/s of hydrogen the chamber burns
BASE = {'regenTruncationType': 'er', 'regenTruncationValue': 3.0, 'makeRadiativeExtension': True,
        'coolantMassFlow': 3.1,
        'filmCooling': False, 'makeInletVolute': False, 'makeOutletVolute': False,
        'plumeAmbientPressure': None, 'plumeFieldReach': None}
CIRCUIT = {**BASE, 'extensionCircuit': True, 'extensionCircuitEndAreaRatio': 12.0,
           'extensionCoolant': 'Hydrogen', 'extensionCoolantMassFlow': 0.5,
           'extensionCoolantInitialTemperature': 40.0, 'extensionCoolantInitialPressure': 8.0e6,
           'extensionChannelCount': 90, 'extensionCircuitDirection': 'coflow'}
CASES = {
    'radiativeOnly':  ('Radiation-cooled shell from area ratio 3', BASE),
    'circuitReturn':  ('Circuit to 12, returned; shell beyond', {**CIRCUIT, 'extensionCircuitOutlet': 'return'}),
    'circuitFilm':    ('Circuit to 12, dumped as a film over the shell', {
        **CIRCUIT, 'extensionCircuitOutlet': 'film',
        'extensionFilmSlots': [{'areaRatio': 12.0, 'slotHeight': 0.012, 'source': 'extensionCircuitOutlet'}]}),
}

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

def wallFigure(solved: dict) -> str:

    '''The hot wall along the whole nozzle, the extension coolant and the film's drive.'''

    figure, (wallAxis, coolantAxis, driveAxis) = plt.subplots(1, 3, figsize = (14.0, 4.4), constrained_layout = True)
    palettes = {'radiativeOnly': colors['red'], 'circuitReturn': colors['blue'], 'circuitFilm': colors['accent']}
    for name, (label, _) in CASES.items():
        nozzle, color = solved[name], palettes[name]
        results = nozzle.channelThermalResults
        x = 1000.0 * np.asarray(nozzle.channelSizingSolution.xRegenNozzleTrimmed)
        wallAxis.plot(x, results['wallTemperature'], color = colors['textMuted'])
        circuit = nozzle.extensionCircuitSolution
        xExtension = 1000.0 * np.asarray(nozzle.xExtension)
        if circuit is not None:
            wallAxis.plot(xExtension[circuit.stations], circuit.wallTemperature, color = color, linewidth = 2.2)
            coolantAxis.plot(xExtension[circuit.stations], circuit.sizing.channelThermalResults['temperature'],
                             color = color, label = label)
        if nozzle.extensionWallTemperature is not None:
            start = len(xExtension) - len(nozzle.extensionWallTemperature)
            wallAxis.plot(xExtension[start:], nozzle.extensionWallTemperature, color = color, linestyle = '--',
                          label = f'{label}: shell peak {nozzle.extensionPeakWallTemperature:.0f} K')
            drive = (nozzle.extensionFilmDrivingTemperature if nozzle.extensionFilmDrivingTemperature is not None
                     else nozzle.extensionNearWallRecoveryTemperature)
            driveAxis.plot(xExtension[start:], np.asarray(drive)[start:], color = color, label = label)
        limit = nozzle.extensionTemperatureLimit
    wallAxis.axhline(limit, color = colors['red'], linestyle = ':', linewidth = 1.0)
    wallAxis.set_ylabel('Hot wall temperature [K]')
    coolantAxis.set_ylabel('Extension circuit coolant [K]')
    driveAxis.set_ylabel('Driving temperature over the shell [K]')
    for axis in (wallAxis, coolantAxis, driveAxis):
        axis.set_xlabel('Axial position [mm]')
        axis.legend(fontsize = 7)
    figure.suptitle('Shipped LOX/LH2 nozzle, chamber jacket to area ratio 3 (grey): the extension radiation '
                    'cooled, on a circuit of its own to 12, and on that circuit dumped as a film')
    path = os.path.join(outputFolder, 'extensionCircuitWall.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def main():

    os.makedirs(outputFolder, exist_ok = True)
    solved = {name: solve(name, overrides) for name, (_, overrides) in CASES.items()}
    for name, nozzle in solved.items():
        performance = nozzle.performance
        print(f'  {name}: engine flow {performance.engineTotalMassFlow:.3f} kg/s, engine Isp at the design '
              f'back pressure {performance.engineSpecificImpulse.get("design", float("nan")):.1f} s')
    print('  wrote', wallFigure(solved))

if __name__ == '__main__':
    main()
