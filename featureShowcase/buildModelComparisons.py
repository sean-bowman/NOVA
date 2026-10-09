# -- Model comparison figures for the NOVA feature showcase -- #

'''

What the selectable thermal and gas models do, drawn side by side.

Three choices in NOVA change a number a designer reads, and each carries hardware behind it:

    gasSideAxialModel       one correlation constant along the whole wall, as Bartz assumes, or
                            the distribution measured along a LOX/GH2 chamber (NASA TN D-2832)
    coolantRoughnessModel   what a rough wall may do to the coolant-side heat transfer, from
                            nothing to the full friction multiplier, with the measured rough-wall
                            heat transfer of Dipprey and Sabersky between them
    the gas the mesh runs in  one ratio of specific heats, or local properties along an
                            equilibrium expansion

The first figure draws the models themselves, which needs no run. The second runs the reference
jacket under each and draws what changes along the wall.

Written to `modelComparisonsModels.png` and `modelComparisonsJacket.png`.

Author: Sean Bowman

'''

import io
import json
import os
import sys

import numpy as np

import showcasePalette
import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'tests'))
os.environ.setdefault('NOVA_HEADLESS', '1')

from NOVA.equilibriumExpansion import EquilibriumGas, expansionTable
from NOVA.gasDynamics import prandtlMeyerAngle
from NOVA.gasSideHeatTransfer import (MEASUREDAXIALCONSTANTS, MEASUREDBARRELCONSTANT,
                                      measuredAxialFactor)
from NOVA.regenThermal import (COOLANTROUGHNESSMODELS, coolantFrictionAndNusselt,
                               entranceEnhancementFactor, itoCurvatureFactor)

background = showcasePalette.background
panel      = showcasePalette.panel
copper     = showcasePalette.copper
green      = showcasePalette.green
ink        = showcasePalette.ink
muted      = showcasePalette.muted
warn       = showcasePalette.warn
blue       = showcasePalette.blue

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': showcasePalette.gridColor,
    'axes.grid': False, 'font.size': 9,
    'axes.titlesize': 11, 'axes.titleweight': 'bold', 'legend.framealpha': 0.0,
})

#--------------------------------------------------------------------------------------------------------------------------#
# -- The models themselves -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawGasSideAxial(axes):

    '''The correlation constant along the wall, measured against the single value Bartz carries.'''

    for branch, color, label in (('subsonic', copper, 'chamber to throat'),
                                 ('supersonic', blue, 'throat to exit')):
        ratios = np.array([station[0] for station in MEASUREDAXIALCONSTANTS[branch]])
        constants = np.array([station[1] for station in MEASUREDAXIALCONSTANTS[branch]])
        scatter = np.array([station[2] for station in MEASUREDAXIALCONSTANTS[branch]])

        sampled = np.geomspace(min(ratios), max(ratios), 200)
        drawn = [measuredAxialFactor(ratio, branch == 'subsonic')*MEASUREDBARRELCONSTANT
                 for ratio in sampled]

        axes.plot(sampled, drawn, color = color, lw = 1.6, label = label)
        axes.errorbar(ratios, constants, yerr = 1.96*scatter*constants, fmt = 'o', ms = 4,
                      color = color, ecolor = color, elinewidth = 1, capsize = 3, alpha = 0.9)

    axes.axhline(0.026, color = warn, lw = 1.4, ls = '--', label = 'Bartz, one value')
    axes.set_xscale('log')
    axes.set_xlabel('area ratio [-]')
    axes.set_ylabel('correlation constant C [-]')
    axes.set_title('Gas side: C along the wall')
    axes.legend(loc = 'lower right', fontsize = 8)
    axes.text(0.03, 0.06, 'bars are the 95 % spread\nof the measurements',
              transform = axes.transAxes, color = muted, fontsize = 7.5)

def drawRoughness(axes):

    '''What each roughness model does to the Nusselt number as the wall gets rougher.'''

    diameter, reynolds, prandtl = 0.003, 1.0e6, 1.0
    roughness = np.geomspace(1.0e-7, 2.0e-4, 200)
    smooth = coolantFrictionAndNusselt(reynolds, prandtl, diameter, 0.0, 'frictionOnly')[1]

    for model, color in zip(COOLANTROUGHNESSMODELS, (green, copper, warn)):
        nusselt = [coolantFrictionAndNusselt(reynolds, prandtl, diameter, e, model)[1]
                   for e in roughness]
        axes.plot(roughness*1e6, np.asarray(nusselt)/smooth, color = color, lw = 1.6, label = model)

    friction = [coolantFrictionAndNusselt(reynolds, prandtl, diameter, e, 'frictionOnly')[0]
                for e in roughness]
    smoothFriction = coolantFrictionAndNusselt(reynolds, prandtl, diameter, 0.0)[0]
    # Full credit lies on this line by construction, which is what the panel is for
    axes.plot(roughness*1e6, np.asarray(friction)/smoothFriction, color = ink, lw = 2.6,
              ls = ':', alpha = 0.75, zorder = 0, label = 'friction factor')

    axes.axvline(35.0, color = ink, lw = 1.0, ls = '--', alpha = 0.5)
    axes.text(37.0, 1.05, 'printed\nchannel', color = ink, fontsize = 7.5)
    axes.set_xscale('log')
    axes.set_xlabel('surface roughness [um]')
    axes.set_ylabel('over the smooth-wall value [-]')
    axes.set_title('Coolant side: what roughness buys')
    axes.legend(loc = 'upper left', fontsize = 8)

def drawTurning(axes):

    '''Turning from the throat under local properties, against the two constant exponents.'''

    table = expansionTable('LH2', 'LOX', 5.5, 6894757.0)
    inRange = table.areaRatio >= 1.2

    axes.plot(table.areaRatio[inRange], np.degrees(table.prandtlMeyer[inRange]),
              color = green, lw = 1.8, label = 'equilibrium, local properties')
    for gamma, color, label in ((1.1475, warn, 'chamber gamma 1.1475'),
                                (1.2005, blue, 'effective gamma 1.2005')):
        turning = [np.degrees(prandtlMeyerAngle(mach, gamma)) for mach in table.mach[inRange]]
        axes.plot(table.areaRatio[inRange], turning, color = color, lw = 1.4, ls = '--', label = label)

    axes.axvline(40.0, color = ink, lw = 1.0, ls = ':', alpha = 0.6)
    axes.text(41.0, 40.0, 'reference\nengine', color = ink, fontsize = 7.5)
    axes.set_xscale('log')
    axes.set_xlabel('area ratio [-]')
    axes.set_ylabel('turning from the throat [deg]')
    axes.set_title('Gas model: Prandtl-Meyer turning')
    axes.legend(loc = 'upper left', fontsize = 8)

def drawCoolantGeometry(axes):

    '''The entrance and curvature corrections, over the range a channel sees.'''

    lengthToDiameter = np.geomspace(0.5, 60.0, 200)
    axes.plot(lengthToDiameter, entranceEnhancementFactor(lengthToDiameter*0.003, 0.003),
              color = copper, lw = 1.6, label = 'entrance, against S/d')

    published = ((7.5, 1.5), (25.0, 1.01), (40.0, 1.0), (46.0, 1.0))
    axes.plot([point[0] for point in published], [point[1] for point in published], 'o',
              ms = 5, color = copper, label = 'published coefficients')

    bendOverDiameter = np.geomspace(1.0, 200.0, 200)
    curvature = itoCurvatureFactor(2.0e6, 0.0015, bendOverDiameter*0.003)
    axes.plot(bendOverDiameter, curvature, color = blue, lw = 1.6, label = 'curvature, against r/d')

    axes.set_xscale('log')
    axes.set_xlabel('S/d for the entrance, r/d for the bend [-]')
    axes.set_ylabel('multiplier on the coefficient [-]')
    axes.set_title('Coolant side: entrance and curvature')
    axes.legend(loc = 'upper right', fontsize = 8)

def drawModels():

    '''The four model panels.'''

    figure, axesGrid = plt.subplots(2, 2, figsize = (11.5, 8.0))
    drawGasSideAxial(axesGrid[0][0])
    drawRoughness(axesGrid[0][1])
    drawTurning(axesGrid[1][0])
    drawCoolantGeometry(axesGrid[1][1])

    figure.suptitle('What each selectable model does', color = ink, fontsize = 13, fontweight = 'bold')
    figure.tight_layout(rect = (0, 0, 1, 0.96))
    path = os.path.join(here, 'modelComparisonsModels.png')
    figure.savefig(path, dpi = 160)
    plt.close(figure)
    print(f'wrote {path}')

#--------------------------------------------------------------------------------------------------------------------------#
# -- The same jacket under each model -- #
#--------------------------------------------------------------------------------------------------------------------------#

variants = {
    'default': {},
    'roughness credited in full': {'coolantRoughnessModel': 'fullCredit'},
    'no roughness credit': {'coolantRoughnessModel': 'frictionOnly'},
    'measured gas-side C(A/A*)': {'gasSideAxialModel': 'measured'},
}

def runJacket(overrides):

    '''The reference jacket under one set of overrides, with the station arrays captured.'''

    import regressionHarness as harness
    import NOVA.channelSizing as channelSizing
    import NOVA.regenThermal as regenThermal
    from NOVA import Nozzle

    # The station arrays only ever reach the figure, so the figure is where they are taken from.
    # Plots have to be on for the sizing solve to hand them over, and both drawing routines are
    # replaced while that happens so nothing is actually rendered.
    captured = {}
    originalSizingDraw = channelSizing.drawRegenHeatTransfer
    originalModelDraw = regenThermal.regenHeatTransferModelPlots

    def capture(thermal, **keywords):
        captured.update(keywords.get('results') or {})
        return None

    configuration = json.load(open(os.path.join(root, 'src', 'NOVA', 'assets', 'NOVANozzle.json')))
    configuration.update(harness.harnessOverrides)
    configuration.update(harness.harnessCases['regenCircle']['overrides'])
    configuration.update(overrides)
    configuration.update({'plotsEnabled': True, 'export': False, 'plumeAmbientPressure': None,
                          'filename': 'modelComparison'})
    for key in [key for key, value in configuration.items() if value is harness.ABSENT]:
        del configuration[key]

    path = os.path.join(here, 'modelComparisonConfig.json')
    with io.open(path, 'w', encoding = 'utf-8', newline = '') as handle:
        json.dump(configuration, handle, indent = 2)

    channelSizing.drawRegenHeatTransfer = capture
    regenThermal.regenHeatTransferModelPlots = lambda *arguments, **keywords: None
    try:
        Nozzle._getOutputRoot = lambda self, _base = here: _base
        nozzle = Nozzle()
        nozzle.generateNozzle(configPath = path)
    finally:
        channelSizing.drawRegenHeatTransfer = originalSizingDraw
        regenThermal.regenHeatTransferModelPlots = originalModelDraw

    return nozzle, captured

def drawJacket():

    '''Wall temperature, coolant temperature and channel size along the wall, per model.'''

    results = {}
    for label, overrides in variants.items():
        print(f'running: {label}')
        results[label] = runJacket(overrides)

    figure, axesGrid = plt.subplots(1, 3, figsize = (13.5, 4.2))
    colors = (ink, warn, green, blue)

    for (label, (nozzle, plots)), color in zip(results.items(), colors):
        # The station arrays the thermal model hands the figure carry no axis of their own; the
        # interfaced wall is the one they were solved on
        x = np.asarray(nozzle.xRegenNozzleInterfaced, dtype = float)*1000.0
        wall = np.asarray(plots['wallTemperature'], dtype = float)
        if wall.size != x.size:
            x = np.linspace(x[0], x[-1], wall.size)
        style = dict(color = color, lw = 1.5, label = label)
        axesGrid[0].plot(x, np.asarray(plots['wallTemperature'], dtype = float), **style)
        axesGrid[1].plot(x, np.asarray(plots['temperature'], dtype = float), **style)
        axesGrid[2].plot(x, np.asarray(nozzle.channelRadius, dtype = float)*1000.0, **style)

    axesGrid[0].axhline(800.0, color = muted, lw = 1.0, ls = '--')
    axesGrid[0].text(axesGrid[0].get_xlim()[0], 805.0, 'wall limit', color = muted, fontsize = 7.5)
    axesGrid[0].set_ylabel('hot wall temperature [K]')
    axesGrid[0].set_title('Wall')
    axesGrid[1].set_ylabel('coolant temperature [K]')
    axesGrid[1].set_title('Coolant')
    axesGrid[2].set_ylabel('channel radius [mm]')
    axesGrid[2].set_title('Channel the solve picked')

    for axes in axesGrid:
        axes.set_xlabel('axial position [mm]')
    axesGrid[0].legend(loc = 'lower left', fontsize = 7.5)

    figure.suptitle('The reference jacket under each model, sixty circular channels',
                    color = ink, fontsize = 13, fontweight = 'bold')
    figure.tight_layout(rect = (0, 0, 1, 0.93))
    path = os.path.join(here, 'modelComparisonsJacket.png')
    figure.savefig(path, dpi = 160)
    plt.close(figure)
    print(f'wrote {path}')

    print(f"\n{'model':30s} {'coolant exit [K]':>17} {'pressure drop [MPa]':>21}")
    for label, (nozzle, _) in results.items():
        drop = (nozzle.coolantInitialPressure - nozzle.coolantExitPressure)*1e-6
        print(f'{label:30s} {nozzle.coolantExitTemperature:17.1f} {drop:21.4f}')

def main():

    drawModels()
    drawJacket()

if __name__ == '__main__':
    main()
