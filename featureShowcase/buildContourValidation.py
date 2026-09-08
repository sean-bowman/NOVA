'''
Validation of the NOVA contour generator against references that do not come from NOVA.

Four studies, in decreasing order of how much they settle.

  Rao wall angles     The only reference that checks the CONTOUR rather than its end points.
                      A truncated ideal contour and a thrust-optimised parabola of the same area
                      ratio and length are different families, so a difference is expected; what is
                      reported is its size and its sign.

  RS-25 geometry      The one flight engine whose nozzle dimensions are public enough to compare
                      against. Its published throat and exit diameters and its quoted nozzle length
                      give a length fraction that can be checked directly.

  Grid convergence    How much of the delivered geometry is physics and how much is mesh. A contour
                      tool with no convergence study has no claim on its own digits.

  Exit plane          What the exit pressure matching condition is actually converging on, which is
                      the assumption this whole assessment set out to test.

Each study runs the solver, so the whole thing takes on the order of fifteen minutes. Results are
cached to contourValidation.npz; pass --draw to redraw the figure from the cache without re-running.

    python featureShowcase/buildContourValidation.py
    python featureShowcase/buildContourValidation.py --draw
'''
import json
import os
import sys
import time

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
from NOVA.contour import raoWallAngles, raoParabolicContour, raoChartExtrapolatedAbove
from NOVA.contourKernel import ThroatGeometry
from NOVA.gasDynamics import (conicalLength, machFromAreaRatio, staticPressureRatio,
                         divergenceLossFactor)
from NOVA.Nozzle import Nozzle

background = '#1a1e2a'
panel      = '#222735'
copper     = '#E0975A'
green      = '#86C06C'
ink        = '#E8E6E1'
muted      = '#8B93A7'
warn       = '#E8A0A0'
blue       = '#6BA3D6'

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': '#333A4D',
    'axes.grid': False, 'font.size': 9,
    'axes.titlesize': 11, 'axes.titleweight': 'bold', 'legend.framealpha': 0.0,
})

cachePath = os.path.join(here, 'contourValidation.npz')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Running the solver -- #
#--------------------------------------------------------------------------------------------------------------------------#

def runCase(areaRatio, lengthFraction, mesh = 50, fuel = 'LH2', oxidizer = 'LOX',
            mixtureRatio = 5.5, chamberPressure = 6894757.0, thrust = 100000.0):
    '''
    One contour, returned as a flat dictionary of what it delivered. Returns None if the solve
    fails, so a sweep can report a hole rather than stopping at one.
    '''
    config = json.load(open(os.path.join(root, 'src', 'NOVA', 'assets',
                                         'loxLh2Example.json')))
    config.update({'Fuel': fuel, 'Oxidizer': oxidizer, 'OFRatio': mixtureRatio,
                   'chamberPressure': chamberPressure, 'thrust': thrust,
                   'targetExitPressure': None, 'expansionRatio': areaRatio,
                   'lengthFraction': lengthFraction, 'Lstar': None,
                   'plumeAmbientPressure': None, 'plotsBasic': False, 'plotsAdv': False,
                   'export': False, 'visualizeContour': False, 'filename': 'contourValidation'})
    configPath = os.path.join(here, 'validationConfig.json')
    json.dump(config, open(configPath, 'w'), indent = 2)

    Nozzle._getOutputRoot = lambda self, _base = here: _base
    nozzle = Nozzle()
    try:
        nozzle.setInputs(inputsPath = configPath)
        nozzle.numCharacteristicsRequested = mesh
        nozzle.pressureMatchTruncatedIdealContour(float(lengthFraction))
    except Exception as error:                                      # noqa: BLE001
        print(f'    FAILED eps {areaRatio} bell {lengthFraction} mesh {mesh}: {error}')
        return None

    solution = nozzle.nozzleContourSolution
    throatRadius = float(np.min(solution.rNozzleWallDivergingNonDimensional))
    return {
        'requestedAreaRatio': float(areaRatio),
        'requestedLengthFraction': float(lengthFraction),
        'mesh': float(mesh),
        'deliveredAreaRatio': float(solution.deliveredAreaRatio),
        'deliveredLengthFraction': float(solution.deliveredLengthFraction),
        'inflectionWallAngle': float(np.degrees(solution.inflectionWallAngle)),
        'exitWallAngle': float(np.degrees(solution.exitWallAngle)),
        'thrustCoef': float(solution.thrustCoef),
        'velocityTerm': float(solution.velocityTermThrustCoef),
        'pressureTerm': float(solution.pressureTermThrustCoef),
        'wallExitPressure': float(solution.exitPlanePressure[0]),
        'axisExitPressure': float(solution.exitPlanePressure[-1]),
        'areaAveragedExitPressure': float(solution.exitAreaAveragedPressure),
        'massAveragedExitPressure': float(solution.exitMassAveragedPressure),
        'targetExitPressure': float(nozzle.targetExitPressure),
        'chamberGamma': float(nozzle.chamberGamma),
        'chamberPressure': float(nozzle.chamberPressure),
        'throatRadius': throatRadius,
        'scalingFactor': float(solution.nozzleScalingFactor),
        'exitLengthNonDimensional': float(solution.xNozzleWallDivergingNonDimensional[-1]),
        # The diverging wall, non-dimensional against the throat radius. Kept so a contour can be
        # drawn against a reference without re-solving it, which is a minute per case.
        'wallX': np.asarray(solution.xNozzleWallDivergingNonDimensional, dtype = float),
        'wallR': np.asarray(solution.rNozzleWallDivergingNonDimensional, dtype = float),
    }

def flatten(records, key):
    return np.array([record[key] if record is not None else np.nan for record in records])

def storeWalls(payload, records, prefix):
    '''
    Keep each case's wall under its own key.

    Stacking them would make a ragged array as soon as one case fails or one runs at a different
    contour resolution, and numpy would silently store objects instead of numbers.
    '''
    for index, record in enumerate(records):
        if record is None:
            continue
        payload[f'{prefix}_wallX_{index}'] = record['wallX']
        payload[f'{prefix}_wallR_{index}'] = record['wallR']

def study():
    '''Run every sweep and cache the result.'''
    started = time.time()
    payload = {}

    print('Rao wall angle sweep')
    raoCases = ([(ratio, 0.80) for ratio in [10.0, 20.0, 40.0, 70.0]]
                + [(40.0, fraction) for fraction in [0.60, 0.70, 0.90]])
    raoRecords = []
    for areaRatio, lengthFraction in raoCases:
        print(f'  eps {areaRatio:6.1f}  bell {lengthFraction:.2f}')
        raoRecords.append(runCase(areaRatio, lengthFraction))
    for key in ['requestedAreaRatio', 'requestedLengthFraction', 'deliveredAreaRatio',
                'deliveredLengthFraction', 'inflectionWallAngle', 'exitWallAngle', 'thrustCoef',
                'velocityTerm', 'pressureTerm', 'wallExitPressure', 'axisExitPressure',
                'areaAveragedExitPressure', 'massAveragedExitPressure', 'targetExitPressure',
                'chamberGamma', 'chamberPressure', 'throatRadius', 'scalingFactor']:
        payload[f'rao_{key}'] = flatten(raoRecords, key)
    storeWalls(payload, raoRecords, 'rao')

    print('Grid convergence sweep')
    meshRecords = []
    for mesh in [25, 35, 50, 70, 100]:
        print(f'  characteristics {mesh}')
        meshRecords.append(runCase(40.0, 0.80, mesh = mesh))
    for key in ['mesh', 'deliveredAreaRatio', 'deliveredLengthFraction', 'inflectionWallAngle',
                'exitWallAngle', 'thrustCoef', 'exitLengthNonDimensional']:
        payload[f'mesh_{key}'] = flatten(meshRecords, key)

    print('RS-25 class case')
    # RS-25D at 109 per cent rated power: Pc 20.64 MPa, mixture ratio 6.03, vacuum thrust 2279 kN.
    # Its published expansion ratio is about 69 and its nozzle is described as an 80 per cent bell.
    rs25 = runCase(69.5, 0.806, mixtureRatio = 6.03, chamberPressure = 20.64e6,
                   thrust = 2279000.0)
    for key, value in (rs25 or {}).items():
        payload[f'rs25_{key}'] = np.asarray(value, dtype = float)
    storeWalls(payload, [rs25], 'rs25')

    np.savez(cachePath, **payload)
    print(f'cached to {cachePath} in {time.time() - started:.0f} s')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Drawing -- #
#--------------------------------------------------------------------------------------------------------------------------#

def draw():
    data = np.load(cachePath)
    figure, axes = plt.subplots(2, 3, figsize = (18.0, 9.5))

    # -- 1. Delivered against requested -- #
    panelOne = axes[0][0]
    requestedRatio = data['rao_requestedAreaRatio']
    deliveredRatio = data['rao_deliveredAreaRatio']
    requestedLength = data['rao_requestedLengthFraction']
    deliveredLength = data['rao_deliveredLengthFraction']
    panelOne.plot([0, 1.1 * np.nanmax(requestedRatio)], [0, 1.1 * np.nanmax(requestedRatio)],
                  color = muted, ls = '--', lw = 1.0, label = 'delivered equals requested')
    panelOne.plot(requestedRatio, deliveredRatio, 'o', color = copper, ms = 9,
                  label = 'area ratio')
    worstRatio = np.nanmax(np.abs(deliveredRatio / requestedRatio - 1.0))
    worstLength = np.nanmax(np.abs(deliveredLength / requestedLength - 1.0))
    panelOne.set_xlabel('Requested area ratio')
    panelOne.set_ylabel('Delivered area ratio')
    panelOne.set_title(f'Delivered against requested\nworst error {100*worstRatio:.4f} % on area '
                       f'ratio, {100*worstLength:.4f} % on length')
    panelOne.grid(True, alpha = 0.25)
    panelOne.legend(loc = 'upper left', fontsize = 8, labelcolor = ink)

    # -- 2. Wall angles against the Rao chart, over area ratio -- #
    panelTwo = axes[0][1]
    atEightyPercent = np.isclose(requestedLength, 0.80)
    ratios = requestedRatio[atEightyPercent]
    order = np.argsort(ratios)
    chartRatios = np.logspace(np.log10(4.0), np.log10(100.0), 60)
    chartInflection = [np.degrees(raoWallAngles(ratio, 0.80)[0]) for ratio in chartRatios]
    chartExit = [np.degrees(raoWallAngles(ratio, 0.80)[1]) for ratio in chartRatios]
    panelTwo.semilogx(chartRatios, chartInflection, color = blue, lw = 2.0,
                      label = 'Rao chart, inflection')
    panelTwo.semilogx(chartRatios, chartExit, color = blue, lw = 2.0, ls = '--',
                      label = 'Rao chart, exit')
    panelTwo.semilogx(ratios[order], data['rao_inflectionWallAngle'][atEightyPercent][order],
                      'o-', color = copper, ms = 8, label = 'NOVA, inflection')
    panelTwo.semilogx(ratios[order], data['rao_exitWallAngle'][atEightyPercent][order],
                      's--', color = green, ms = 8, label = 'NOVA, exit')
    panelTwo.axvspan(raoChartExtrapolatedAbove, 100.0, color = warn, alpha = 0.10)
    panelTwo.text(raoChartExtrapolatedAbove * 1.05, 3.0, 'chart extrapolated', color = warn,
                  fontsize = 7.5, rotation = 90, va = 'bottom')
    panelTwo.set_xlabel('Area ratio')
    panelTwo.set_ylabel('Wall angle [deg]')
    panelTwo.set_title('Wall angles against the Rao chart, 80 percent bell')
    panelTwo.grid(True, alpha = 0.25, which = 'both')
    panelTwo.legend(loc = 'upper right', fontsize = 8, labelcolor = ink)

    # -- 3. Wall angles over percent bell at a fixed area ratio -- #
    panelThree = axes[0][2]
    atFortyRatio = np.isclose(requestedRatio, 40.0)
    fractions = requestedLength[atFortyRatio]
    order = np.argsort(fractions)
    chartFractions = np.linspace(0.60, 0.90, 40)
    panelThree.plot(chartFractions,
                    [np.degrees(raoWallAngles(40.0, f)[0]) for f in chartFractions],
                    color = blue, lw = 2.0, label = 'Rao chart, inflection')
    panelThree.plot(chartFractions,
                    [np.degrees(raoWallAngles(40.0, f)[1]) for f in chartFractions],
                    color = blue, lw = 2.0, ls = '--', label = 'Rao chart, exit')
    panelThree.plot(fractions[order], data['rao_inflectionWallAngle'][atFortyRatio][order],
                    'o-', color = copper, ms = 8, label = 'NOVA, inflection')
    panelThree.plot(fractions[order], data['rao_exitWallAngle'][atFortyRatio][order],
                    's--', color = green, ms = 8, label = 'NOVA, exit')
    panelThree.set_xlabel('Length as a fraction of the 15 degree cone')
    panelThree.set_ylabel('Wall angle [deg]')
    panelThree.set_title('Wall angles against the Rao chart, area ratio 40')
    panelThree.grid(True, alpha = 0.25)
    panelThree.legend(loc = 'upper right', fontsize = 8, labelcolor = ink)

    # -- 4. Grid convergence -- #
    panelFour = axes[1][0]
    mesh = data['mesh_mesh']
    finest = -1
    for label, key, colour in [('area ratio', 'mesh_deliveredAreaRatio', copper),
                               ('length fraction', 'mesh_deliveredLengthFraction', green),
                               ('thrust coefficient', 'mesh_thrustCoef', blue),
                               ('exit wall angle', 'mesh_exitWallAngle', warn)]:
        values = data[key]
        panelFour.plot(mesh, 100.0 * (values / values[finest] - 1.0), 'o-', color = colour,
                       ms = 7, label = label)
    panelFour.axhline(0.0, color = muted, lw = 1.0, ls = '--')
    panelFour.set_xlabel('Characteristics launched from the throat arc')
    panelFour.set_ylabel('Departure from the finest mesh [%]')
    panelFour.set_title('Grid convergence at area ratio 40, 80 percent bell')
    panelFour.grid(True, alpha = 0.25)
    panelFour.legend(loc = 'upper right', fontsize = 8, labelcolor = ink)

    # -- 5. What the exit pressure match converges on -- #
    panelFive = axes[1][1]
    labels = ['wall', 'mass\naveraged', 'area\naveraged', 'axis']
    keys = ['rao_wallExitPressure', 'rao_massAveragedExitPressure',
            'rao_areaAveragedExitPressure', 'rao_axisExitPressure']
    reference = data['rao_targetExitPressure']
    index = int(np.nanargmin(np.abs(requestedRatio - 40.0) + np.abs(requestedLength - 0.80)))
    values = [data[key][index] * 1e-3 for key in keys]
    colours = [warn, copper, copper, green]
    panelFive.bar(labels, values, color = colours, alpha = 0.85)
    panelFive.axhline(reference[index] * 1e-3, color = blue, lw = 1.8, ls = '--',
                      label = f'target exit pressure {reference[index]*1e-3:.1f} kPa')
    oneDimensional = data['rao_chamberPressure'][index] * staticPressureRatio(
        machFromAreaRatio(data['rao_deliveredAreaRatio'][index],
                          data['rao_chamberGamma'][index]),
        data['rao_chamberGamma'][index])
    panelFive.axhline(oneDimensional * 1e-3, color = green, lw = 1.8, ls = ':',
                      label = f'one-dimensional at that area {oneDimensional*1e-3:.1f} kPa')
    panelFive.set_ylabel('Exit static pressure [kPa]')
    panelFive.set_title('What an exit pressure residual could be built on\n'
                        f'wall is {values[0]/values[2]:.2f} times the area average')
    panelFive.grid(True, alpha = 0.25, axis = 'y')
    panelFive.legend(loc = 'upper right', fontsize = 8, labelcolor = ink)

    # -- 6. Thrust coefficient against closed-form theory -- #
    panelSix = axes[1][2]
    deliveredRatios = data['rao_deliveredAreaRatio'][atEightyPercent]
    gamma = data['rao_chamberGamma'][atEightyPercent]
    chamberPressure = data['rao_chamberPressure'][atEightyPercent]
    ambient = data['rao_targetExitPressure'][atEightyPercent]
    idealTotal, idealVelocity = [], []
    for ratio, g, pc, pa in zip(deliveredRatios, gamma, chamberPressure, ambient):
        exitPressure = pc * staticPressureRatio(machFromAreaRatio(ratio, g), g)
        velocity = np.sqrt((2 * g**2 / (g - 1)) * ((2 / (g + 1))**((g + 1)/(g - 1)))
                           * (1 - (exitPressure / pc)**((g - 1)/g)))
        idealVelocity.append(velocity)
        idealTotal.append(velocity + (exitPressure - pa) / pc * ratio)
    order = np.argsort(deliveredRatios)
    novaTotal = data['rao_thrustCoef'][atEightyPercent]
    novaVelocity = data['rao_velocityTerm'][atEightyPercent]
    divergence = np.array([divergenceLossFactor(np.radians(angle))
                           for angle in data['rao_exitWallAngle'][atEightyPercent]])
    panelSix.plot(deliveredRatios[order], np.array(idealTotal)[order], 'o-', color = blue,
                  ms = 7, label = 'one-dimensional ideal')
    panelSix.plot(deliveredRatios[order], novaTotal[order], 's-', color = copper, ms = 7,
                  label = 'NOVA')
    panelSix.plot(deliveredRatios[order],
                  (np.array(idealVelocity) * divergence
                   + (np.array(idealTotal) - np.array(idealVelocity)))[order],
                  '^--', color = green, ms = 7,
                  label = 'ideal with the divergence factor at the delivered exit angle')
    panelSix.set_xlabel('Delivered area ratio')
    panelSix.set_ylabel('Thrust coefficient')
    panelSix.set_title('Thrust coefficient against closed-form theory')
    panelSix.grid(True, alpha = 0.25)
    panelSix.legend(loc = 'lower right', fontsize = 8, labelcolor = ink)

    figure.suptitle('NOVA truncated ideal contour: validation against independent references',
                    fontsize = 14, fontweight = 'bold')
    figure.tight_layout(rect = [0, 0.055, 1, 0.965])

    inflectionError = (data['rao_inflectionWallAngle'][atEightyPercent]
                       - np.array([np.degrees(raoWallAngles(r, 0.80)[0]) for r in ratios]))
    exitError = (data['rao_exitWallAngle'][atEightyPercent]
                 - np.array([np.degrees(raoWallAngles(r, 0.80)[1]) for r in ratios]))
    figure.text(0.012, 0.045,
                f'The area ratio and the length fraction are both delivered to better than '
                f'{100*max(worstRatio, worstLength):.3f} per cent, because the wall is cut at the '
                f'requested area ratio and the design Mach number is solved for the length.\n'
                f'Against the Rao chart at 80 percent bell the inflection angle runs '
                f'{inflectionError.min():+.1f} to {inflectionError.max():+.1f} degrees and the exit '
                f'angle {exitError.min():+.1f} to {exitError.max():+.1f} degrees. These are '
                f'different contour families, a truncated ideal against a thrust-optimised '
                f'parabola, so a difference is expected;\nthe sign is the informative part. Above '
                f'an area ratio of 50 the chart itself is extrapolated and is not a measurement.',
                fontsize = 8.5, color = ink, va = 'top')

    path = os.path.join(here, 'contourValidation.png')
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print(f'wrote {os.path.basename(path)}')

    report(data)

def report(data):
    '''Print the numbers the write-up quotes, so they are computed rather than remembered.'''
    print()
    print('=' * 104)
    print('DELIVERED AGAINST REQUESTED')
    print('=' * 104)
    print(f'{"eps req":>9} {"eps del":>9} {"err %":>9} {"bell req":>9} {"bell del":>9} {"err %":>9} '
          f'{"theta_n":>9} {"theta_e":>9} {"Cf":>9}')
    for i in range(len(data['rao_requestedAreaRatio'])):
        print(f'{data["rao_requestedAreaRatio"][i]:9.2f} {data["rao_deliveredAreaRatio"][i]:9.4f} '
              f'{100*(data["rao_deliveredAreaRatio"][i]/data["rao_requestedAreaRatio"][i]-1):9.4f} '
              f'{data["rao_requestedLengthFraction"][i]:9.3f} '
              f'{data["rao_deliveredLengthFraction"][i]:9.4f} '
              f'{100*(data["rao_deliveredLengthFraction"][i]/data["rao_requestedLengthFraction"][i]-1):9.4f} '
              f'{data["rao_inflectionWallAngle"][i]:9.3f} {data["rao_exitWallAngle"][i]:9.3f} '
              f'{data["rao_thrustCoef"][i]:9.5f}')

    print()
    print('=' * 104)
    print('WALL ANGLES AGAINST THE RAO CHART')
    print('=' * 104)
    print(f'{"eps":>9} {"bell":>7} {"NOVA n":>9} {"Rao n":>9} {"diff":>8} {"NOVA e":>9} '
          f'{"Rao e":>9} {"diff":>8}  extrapolated')
    for i in range(len(data['rao_requestedAreaRatio'])):
        ratio = data['rao_deliveredAreaRatio'][i]
        fraction = data['rao_requestedLengthFraction'][i]
        chartInflection, chartExit, extrapolated = raoWallAngles(ratio, fraction)
        chartInflection, chartExit = np.degrees(chartInflection), np.degrees(chartExit)
        print(f'{ratio:9.2f} {fraction:7.2f} {data["rao_inflectionWallAngle"][i]:9.3f} '
              f'{chartInflection:9.3f} {data["rao_inflectionWallAngle"][i]-chartInflection:+8.3f} '
              f'{data["rao_exitWallAngle"][i]:9.3f} {chartExit:9.3f} '
              f'{data["rao_exitWallAngle"][i]-chartExit:+8.3f}  {extrapolated}')

    print()
    print('=' * 104)
    print('GRID CONVERGENCE, against the finest mesh')
    print('=' * 104)
    print(f'{"mesh":>6} {"eps":>10} {"err %":>9} {"bell":>9} {"err %":>9} {"Cf":>10} {"err %":>9} '
          f'{"theta_e":>9} {"err %":>9}')
    for i in range(len(data['mesh_mesh'])):
        row = [data['mesh_mesh'][i]]
        for key in ['mesh_deliveredAreaRatio', 'mesh_deliveredLengthFraction', 'mesh_thrustCoef',
                    'mesh_exitWallAngle']:
            row += [data[key][i], 100.0 * (data[key][i] / data[key][-1] - 1.0)]
        print(f'{row[0]:6.0f} {row[1]:10.4f} {row[2]:9.4f} {row[3]:9.4f} {row[4]:9.4f} '
              f'{row[5]:10.5f} {row[6]:9.4f} {row[7]:9.3f} {row[8]:9.4f}')

    if 'rs25_deliveredAreaRatio' in data:
        print()
        print('=' * 104)
        print('RS-25 CLASS CASE')
        print('=' * 104)
        scale = float(data['rs25_scalingFactor'])
        throat = float(data['rs25_throatRadius']) * scale
        exitRadius = np.sqrt(float(data['rs25_deliveredAreaRatio'])) * throat
        length = float(data['rs25_exitLengthNonDimensional']) * scale
        print(f'  NOVA throat diameter        {2*throat*1e3:8.1f} mm    '
              f'published 261.6 mm (10.3 in)')
        print(f'  NOVA exit diameter          {2*exitRadius*1e3:8.1f} mm    '
              f'published 2303.8 mm (90.7 in)')
        print(f'  NOVA nozzle length          {length*1e3:8.1f} mm    '
              f'published 3073.4 mm (121 in)')
        print(f'  NOVA delivered area ratio   {float(data["rs25_deliveredAreaRatio"]):8.3f}       '
              f'published about 69.5')
        print(f'  NOVA length fraction        {float(data["rs25_deliveredLengthFraction"]):8.4f}       '
              f'published about 0.806 of the 15 degree cone')
        print(f'  NOVA exit wall angle        {float(data["rs25_exitWallAngle"]):8.3f} deg')
        print(f'  NOVA inflection wall angle  {float(data["rs25_inflectionWallAngle"]):8.3f} deg')
        print()
        print('  The published throat and exit diameters imply a geometric area ratio of 77.5')
        print('  against the published 69.5, so at least one of the three quoted dimensions is not')
        print('  the quantity it appears to be. The comparison above uses the published 69.5.')

def main():
    if '--draw' in sys.argv:
        draw()
    else:
        study()
        draw()

if __name__ == '__main__':
    main()
