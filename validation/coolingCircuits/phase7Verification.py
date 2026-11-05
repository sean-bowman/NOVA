# -- Verification Figures: The Coolant-Side Roughness Bounds and a Coated Wall's Margin -- #

'''

Figures that show two Phase 7 corrections behaving as intended.

1. **The roughness correlation across the onset of roughness.** Dipprey and Sabersky's rough-wall
   Nusselt number over the smooth-wall Gnielinski value, against the roughness Reynolds number,
   at Prandtl numbers of 0.7 (hydrogen), 2.5 (liquid methane) and 25 (a liquid hydrocarbon such as
   dodecane). Drawn three ways: the expression on its own, a switch to the smooth-wall form below
   e+ = 5, and the expression held between smooth-wall Gnielinski and Gnielinski on the wall's
   own friction factor, which is what regenThermal.dippreySaberskyNusselt returns. The switch steps
   at e+ = 5 by an amount that grows with the Prandtl number; the bounded value is continuous.
2. **A coated wall against its limits.** The F-1-like example's two-pass Inconel jacket under its
   carbon layer: the metal behind the layer, which the 900 K limit applies to; the layer's own
   gas-side surface; and the coolant-side wall against the 560 K coking ceiling, for both families.

These are verification figures, not validations. The first is closed form, held in
tests/testCoolantRoughness.py, and the correlation is extrapolated outside its fitted Prandtl
range (regenThermal.py). The second reads the solved example from the cooling showcase's cache;
the carbon layer is an assumed value (assets/examples/keroloxF1.json).

Run from the NOVA root:

    python validation/coolingCircuits/phase7Verification.py

The second figure needs featureShowcase/coolingRuns/keroloxF1.pkl, which
`python featureShowcase/buildCoolingShowcase.py --engine keroloxF1` writes.

Author: Sean Bowman

'''

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

from NOVA import palette
from NOVA.regenThermal import dippreySaberskyNusselt, gnielinskiNusselt, swameeJainFriction

outputFolder = os.path.join(here, 'phase7')
colors = palette.colors('dark')
plt.rcParams.update(palette.matplotlibStyle('dark'))
plt.rcParams.update({'font.size': 9, 'axes.grid': True, 'grid.alpha': 0.4})

REYNOLDS = 1.0e5            # [-]
DIAMETER = 0.003            # [m], hydraulic diameter
PRANDTL = (0.7, 2.5, 25.0)  # [-]

def roughnessCurves(prandtlNumber: float) -> dict:

    '''Each form of the rough-wall Nusselt number over the smooth-wall one, across roughness.'''

    roughness = np.logspace(-9, -3.5, 400)                                 # [m]
    relative = roughness / DIAMETER
    friction = swameeJainFriction(REYNOLDS, relative)
    group = np.sqrt(friction / 8)
    roughnessReynolds = relative * REYNOLDS * group
    smooth = gnielinskiNusselt(swameeJainFriction(REYNOLDS, 0.0), REYNOLDS, prandtlNumber)

    expression = group**2 / (1 + group * (5.19 * roughnessReynolds**0.2 * prandtlNumber**0.44 - 8.48)) \
                 * REYNOLDS * prandtlNumber
    switched = np.where(roughnessReynolds > 5.0, expression, smooth)
    bounded = dippreySaberskyNusselt(friction, REYNOLDS, prandtlNumber, relative)
    fullCredit = gnielinskiNusselt(friction, REYNOLDS, prandtlNumber)

    return {'eplus': roughnessReynolds, 'expression': expression / smooth, 'switched': switched / smooth,
            'bounded': bounded / smooth, 'fullCredit': fullCredit / smooth}

def roughnessFigure() -> str:

    '''Figure 1: the three forms across the onset of roughness, one panel per Prandtl number.'''

    figure, axes = plt.subplots(1, 3, figsize = (14.0, 4.4), constrained_layout = True, sharex = True)
    for axis, prandtlNumber in zip(axes, PRANDTL):
        curves = roughnessCurves(prandtlNumber)
        eplus = curves['eplus']
        axis.plot(eplus, curves['expression'], color = colors['textMuted'], linestyle = '--', linewidth = 1.2,
                  label = 'Dipprey-Sabersky expression')
        axis.plot(eplus, curves['fullCredit'], color = colors['blue'], linestyle = ':', linewidth = 1.2,
                  label = 'Gnielinski on the rough friction factor')
        axis.plot(eplus, curves['switched'], color = colors['red'], linewidth = 1.4,
                  label = 'switch to smooth below e+ = 5')
        axis.plot(eplus, curves['bounded'], color = colors['accent'], linewidth = 2.2,
                  label = 'bounded, as solved')
        onset = np.argmin(np.abs(eplus - 5.0))
        step = curves['switched'][onset + 1] / curves['switched'][onset - 1] - 1.0
        axis.axvline(5.0, color = colors['textDim'], linewidth = 0.8)
        axis.set_xscale('log')
        axis.set_xlabel('Roughness Reynolds number e+ [-]')
        axis.set_title(f'Pr = {prandtlNumber:g}: the switch steps {100 * step:.0f} percent at e+ = 5')
    axes[0].set_ylabel('Nusselt number over smooth-wall Gnielinski [-]')
    axes[0].legend(fontsize = 7, loc = 'upper left')
    figure.suptitle(f'Rough-wall coolant heat transfer at Re = {REYNOLDS:.0e}, {1e3 * DIAMETER:.0f} mm hydraulic '
                    f'diameter: the bounded value is continuous where the switch is not')
    path = os.path.join(outputFolder, 'roughnessContinuity.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def coatedWallFigure() -> str:

    '''Figure 2: the F-1-like jacket's metal, coating surface and coolant-side wall against their limits.'''

    cache = os.path.join(root, 'featureShowcase', 'coolingRuns', 'keroloxF1.pkl')
    if not os.path.isfile(cache):
        print('  no cached F-1-like run; run featureShowcase/buildCoolingShowcase.py --engine keroloxF1')
        return None
    with open(cache, 'rb') as handle:
        nozzle = pickle.load(handle)

    circuit = nozzle.coolantCircuitSolution
    figure, axis = plt.subplots(figsize = (11.0, 5.0), constrained_layout = True)
    for passSolution, style in ((circuit.down, '--'), (circuit.up, '-')):
        results = passSolution.results
        x = 1000.0 * np.asarray(results['xHotWall3D'])
        axis.plot(x, results['wallTemperature'], color = colors['textMuted'], linestyle = style,
                  label = f'carbon layer surface, {passSolution.name} family')
        axis.plot(x, results['metalWallTemperature'], color = colors['accent'], linestyle = style, linewidth = 1.8,
                  label = f'metal behind the layer, {passSolution.name} family')
        axis.plot(x, results['coldWallTemperature'], color = colors['blue'], linestyle = style, linewidth = 1.6,
                  label = f'coolant-side wall, {passSolution.name} family')
    axis.axhline(float(nozzle.maxWallTemperature), color = colors['red'], linewidth = 1.0,
                 label = f'metal limit {float(nozzle.maxWallTemperature):.0f} K')
    axis.axhline(float(nozzle.maxColdWallTemperature), color = colors['yellow'], linewidth = 1.0,
                 label = f'coking ceiling {float(nozzle.maxColdWallTemperature):.0f} K')
    axis.axvline(0.0, color = colors['textDim'], linewidth = 0.8)
    axis.set_xlabel('Axial position [mm]')
    axis.set_ylabel('Temperature [K]')
    axis.legend(fontsize = 7, ncol = 2)
    metal = max(float(np.max(p.results['metalWallTemperature'])) for p in (circuit.down, circuit.up))
    surface = max(float(np.max(p.results['wallTemperature'])) for p in (circuit.down, circuit.up))
    axis.set_title(f'F-1-like two-pass Inconel 718 jacket under a 60 micrometer carbon layer\n'
                   f'metal peaks at {metal:.0f} K and the layer surface at {surface:.0f} K; the coking ceiling binds')
    path = os.path.join(outputFolder, 'coatedWallMargins.png')
    figure.savefig(path, dpi = 150)
    plt.close(figure)
    return path

def main():

    os.makedirs(outputFolder, exist_ok = True)
    print('  wrote', roughnessFigure())
    written = coatedWallFigure()
    if written:
        print('  wrote', written)

if __name__ == '__main__':
    main()
