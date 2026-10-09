'''
NOVA contours drawn directly on top of their reference counterparts.

Three panels, and they establish different things.

  RS-25            The one flight engine with enough public geometry to overlay. Its published
                   throat diameter, exit diameter and area ratio are mutually inconsistent by 12
                   per cent, so both readings of the envelope are drawn and neither is picked
                   silently.

  Rao bell family  NOVA against the thrust-optimized parabola at matched area ratio and length.
                   The Rao bell follows exactly from its construction, so it is the only reference
                   contour that needs no reconstruction and the only overlay that is a like-for-like
                   comparison of shape.

  Reconstructed    Vulcain 2, RL10A-4-2 and F-1. Their contours are NOT published. What is drawn is
                   a Rao bell at each engine's published area ratio and an assumed percent bell,
                   against a NOVA contour at the same operating point. This panel is about the
                   shape family across an area ratio of 16 to 84. It is not a dimensional claim
                   about any of those engines, and the figure says so on its face.

The Rao panel reads its contours from contourValidation.npz. The RS-25 and the reconstructions are
solved here and cached to referenceOverlays.npz, so redrawing is instant.

    python featureShowcase/buildReferenceOverlays.py
    python featureShowcase/buildReferenceOverlays.py --draw
'''
import json
import os
import sys
import time

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np

import showcasePalette

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
from NOVA.contour import raoParabolicContour, raoWallAngles
from NOVA.contourKernel import ThroatGeometry
from NOVA.gasDynamics import conicalLength
from NOVA.Nozzle import Nozzle

background = showcasePalette.background
panel      = showcasePalette.panel
copper     = showcasePalette.copper
green      = showcasePalette.green
ink        = showcasePalette.ink
muted      = showcasePalette.muted
warn       = showcasePalette.warn
blue       = showcasePalette.blue
purple     = showcasePalette.purple

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': showcasePalette.gridColor,
    'axes.grid': False, 'font.size': 9,
    'axes.titlesize': 11, 'axes.titleweight': 'bold', 'legend.framealpha': 0.0,
})

cachePath = os.path.join(here, 'referenceOverlays.npz')
validationCache = os.path.join(here, 'contourValidation.npz')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Published engine data -- #
#--------------------------------------------------------------------------------------------------------------------------#

# Everything here is public data with its source noted. `contourPublished` is the field that
# matters: only the RS-25 has enough dimensional data to draw an envelope from, and even there the
# numbers disagree with each other.
engines = {
    'RS-25': {
        'fuel': 'LH2', 'oxidizer': 'LOX', 'mixtureRatio': 6.03,
        'chamberPressure': 20.64e6, 'thrust': 2279000.0,
        'areaRatio': 69.5, 'lengthFraction': 0.806,
        'exitDiameter': 2.3038, 'throatDiameter': 0.2616, 'nozzleLength': 3.0734,
        'contourPublished': False,
        'note': 'RS-25D at 109 per cent rated power. Vacuum thrust 2279 kN, Isp 452.3 s.',
    },
    'RL10A-4-2': {
        'fuel': 'LH2', 'oxidizer': 'LOX', 'mixtureRatio': 5.5,
        'chamberPressure': 4.36e6, 'thrust': 99000.0,
        'areaRatio': 84.0, 'lengthFraction': 0.80,
        'exitDiameter': 1.17, 'throatDiameter': None, 'nozzleLength': None,
        'contourPublished': False,
        'note': 'Vacuum thrust 99 kN, Isp 451 s. The quoted 2.29 m is the engine height, not the '
                'nozzle length.',
    },
    'Vulcain 2': {
        'fuel': 'LH2', 'oxidizer': 'LOX', 'mixtureRatio': 6.1,
        'chamberPressure': 11.7e6, 'thrust': 1359000.0,
        'areaRatio': 58.5, 'lengthFraction': 0.80,
        'exitDiameter': 2.10, 'throatDiameter': None, 'nozzleLength': None,
        'contourPublished': False,
        'note': 'Area ratio quoted as 58.5 and as 61.5 across sources.',
    },
    'F-1': {
        'fuel': 'RP-1', 'oxidizer': 'LOX', 'mixtureRatio': 2.27,
        'chamberPressure': 7.76e6, 'thrust': 7770000.0,
        'areaRatio': 16.0, 'lengthFraction': 0.80,
        'exitDiameter': None, 'throatDiameter': None, 'nozzleLength': None,
        'contourPublished': False,
        'note': 'Regeneratively cooled to the 10:1 plane, turbine-exhaust-cooled extension to 16:1.',
    },
}

#--------------------------------------------------------------------------------------------------------------------------#
# -- Solving -- #
#--------------------------------------------------------------------------------------------------------------------------#

def runEngine(name):
    '''Generate a NOVA contour at one engine's published operating point.'''
    spec = engines[name]
    config = json.load(open(os.path.join(root, 'src', 'NOVA', 'assets',
                                         'NOVANozzle.json')))
    config.update({'Fuel': spec['fuel'], 'Oxidizer': spec['oxidizer'],
                   'OFRatio': spec['mixtureRatio'],
                   'chamberPressure': spec['chamberPressure'], 'thrust': spec['thrust'],
                   'targetExitPressure': None, 'expansionRatio': spec['areaRatio'],
                   'lengthFraction': spec['lengthFraction'], 'Lstar': None,
                   'plumeAmbientPressure': None, 'plotsEnabled': False,
                   'export': False, 'filename': 'referenceOverlays'})
    configPath = os.path.join(here, 'overlayConfig.json')
    json.dump(config, open(configPath, 'w'), indent = 2)

    Nozzle._getOutputRoot = lambda self, _base = here: _base
    nozzle = Nozzle()
    try:
        nozzle.setInputs(inputsPath = configPath)
        nozzle.solveTruncatedIdealDesignPoint(float(spec['lengthFraction']))
    except Exception as error:                                          # noqa: BLE001
        print(f'    FAILED {name}: {error}')
        return None

    solution = nozzle.nozzleContourSolution
    scale = float(solution.nozzleScalingFactor)
    return {
        'wallX': np.asarray(solution.xNozzleWallDivergingNonDimensional, dtype = float) * scale,
        'wallR': np.asarray(solution.rNozzleWallDivergingNonDimensional, dtype = float) * scale,
        'scalingFactor': np.asarray(scale),
        'deliveredAreaRatio': np.asarray(float(solution.deliveredAreaRatio)),
        'deliveredLengthFraction': np.asarray(float(solution.deliveredLengthFraction)),
        'inflectionWallAngle': np.asarray(float(np.degrees(solution.inflectionWallAngle))),
        'exitWallAngle': np.asarray(float(np.degrees(solution.exitWallAngle))),
        'chamberGamma': np.asarray(float(nozzle.chamberGamma)),
    }

def study():
    started = time.time()
    payload = {}
    for name in engines:
        print(f'  {name}')
        record = runEngine(name)
        if record is None:
            continue
        key = name.replace(' ', '').replace('-', '')
        for field, value in record.items():
            payload[f'{key}_{field}'] = value
    np.savez(cachePath, **payload)
    print(f'cached to {os.path.basename(cachePath)} in {time.time() - started:.0f} s')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Drawing -- #
#--------------------------------------------------------------------------------------------------------------------------#

def engineKey(name):
    return name.replace(' ', '').replace('-', '')

def drawRs25(axes, data):
    '''
    NOVA against the RS-25 envelope, with both readings of the published dimensions.

    The published throat diameter, exit diameter and area ratio cannot all be right at once. Taking
    the exit diameter and the area ratio as the consistent pair puts the throat at 276.3 mm; the
    separately quoted throat is 261.6 mm. Both are drawn.
    '''
    key = engineKey('RS-25')
    wallX = data[f'{key}_wallX'] * 1e3
    wallR = data[f'{key}_wallR'] * 1e3
    spec = engines['RS-25']

    exitRadius = spec['exitDiameter'] / 2 * 1e3
    quotedThroat = spec['throatDiameter'] / 2 * 1e3
    impliedThroat = exitRadius / np.sqrt(spec['areaRatio'])
    length = spec['nozzleLength'] * 1e3

    axes.plot(wallX, wallR, color = copper, lw = 2.6, label = 'NOVA truncated ideal contour')
    axes.plot(wallX, -wallR, color = copper, lw = 2.6)

    # A Rao bell through the published area ratio and length. The RS-25's wall is NOT published, so
    # this is a reconstruction; it is drawn rather than a straight line because a straight line
    # between the published end points would read as a claim that the engine is conical.
    throat = ThroatGeometry(float(data[f'{key}_chamberGamma']))
    raoX, raoR = raoParabolicContour(throat, spec['areaRatio'], spec['lengthFraction'],
                                     impliedThroat, numPoints = 300)
    axes.plot(raoX, raoR, color = green, lw = 1.5, ls = '--',
              label = 'RECONSTRUCTED Rao bell at the published point')
    axes.plot(raoX, -raoR, color = green, lw = 1.5, ls = '--')

    # The published dimensions, as the three measurements they are.
    axes.plot([0, 0], [-impliedThroat, impliedThroat], color = blue, lw = 2.4,
              label = f'published throat, from area ratio ({impliedThroat*2:.1f} mm)')
    axes.plot([0, 0], [-quotedThroat, quotedThroat], color = warn, lw = 2.4,
              label = f'published throat, as quoted ({quotedThroat*2:.1f} mm)')
    axes.plot([length, length], [-exitRadius, exitRadius], color = blue, lw = 2.0,
              label = f'published exit, {exitRadius*2:.1f} mm at {length:.0f} mm')
    axes.plot([0, length], [exitRadius, exitRadius], color = muted, lw = 0.8, ls = ':')
    axes.plot([0, length], [-exitRadius, -exitRadius], color = muted, lw = 0.8, ls = ':')

    novaThroat = wallR[0]
    axes.set_xlabel('Distance from the throat [mm]')
    axes.set_ylabel('Radius [mm]')
    axes.set_title(f'RS-25    NOVA throat {novaThroat*2:.1f} mm against '
                   f'{impliedThroat*2:.1f} and {quotedThroat*2:.1f} mm published')
    axes.set_aspect('equal', adjustable = 'box')
    axes.grid(True, alpha = 0.22)
    axes.legend(loc = 'lower right', fontsize = 7, labelcolor = ink)

def drawRaoFamily(axes, validation):
    '''
    NOVA against the thrust-optimized parabola at matched design points.

    Both contours are normalized to the throat radius so shape is comparable across area ratios
    that differ by a factor of seven.
    '''
    requestedRatio = validation['rao_requestedAreaRatio']
    requestedLength = validation['rao_requestedLengthFraction']
    atEightyPercent = np.isclose(requestedLength, 0.80)
    indices = [index for index in np.argsort(requestedRatio) if atEightyPercent[index]]

    colors = [blue, green, copper, purple]
    for color, index in zip(colors, indices):
        ratio = float(requestedRatio[index])
        wallX = validation[f'rao_wallX_{index}']
        wallR = validation[f'rao_wallR_{index}']
        throatRadius = float(np.min(wallR))

        axes.plot(wallX / throatRadius, wallR / throatRadius, color = color, lw = 2.2,
                  label = f'NOVA, area ratio {ratio:.0f}')

        throat = ThroatGeometry(float(validation['rao_chamberGamma'][index]))
        raoX, raoR = raoParabolicContour(throat, ratio, 0.80, 1.0, numPoints = 300)
        axes.plot(raoX, raoR, color = ink, lw = 1.1, ls = (0, (5, 3)), alpha = 0.75)

    axes.plot([], [], color = ink, lw = 1.1, ls = (0, (5, 3)),
              label = 'Rao parabolic bell, same design point')
    axes.set_xlabel('Distance from the throat, throat radii')
    axes.set_ylabel('Radius, throat radii')
    axes.set_title('Against the Rao bell at 80 percent length\n'
                   'solid NOVA, dashed the thrust-optimized parabola')
    axes.grid(True, alpha = 0.22)
    axes.legend(loc = 'upper left', fontsize = 7.5, labelcolor = ink)

def drawReconstructed(axes, data):
    '''
    NOVA against Rao bells reconstructed from published area ratios.

    None of these engines publishes a wall. The dashed curves are what a thrust-optimized parabola
    at the published area ratio and an assumed 80 per cent bell would look like, which is a shape
    family comparison and nothing more.
    '''
    names = ['F-1', 'Vulcain 2', 'RL10A-4-2']
    colors = [green, copper, blue]

    for name, color in zip(names, colors):
        key = engineKey(name)
        if f'{key}_wallX' not in data:
            continue
        wallX, wallR = data[f'{key}_wallX'], data[f'{key}_wallR']
        throatRadius = float(np.min(wallR))
        ratio = engines[name]['areaRatio']

        axes.plot(wallX / throatRadius, wallR / throatRadius, color = color, lw = 2.2,
                  label = f'NOVA at the {name} point, area ratio {ratio:.0f}')

        throat = ThroatGeometry(float(data[f'{key}_chamberGamma']))
        raoX, raoR = raoParabolicContour(throat, ratio, 0.80, 1.0, numPoints = 300)
        axes.plot(raoX, raoR, color = ink, lw = 1.1, ls = (0, (5, 3)), alpha = 0.75)

    axes.plot([], [], color = ink, lw = 1.1, ls = (0, (5, 3)),
              label = 'RECONSTRUCTED Rao bell, not a published contour')
    axes.set_xlabel('Distance from the throat, throat radii')
    axes.set_ylabel('Radius, throat radii')
    axes.set_title('Reconstructed engines, area ratio 16 to 84\n'
                   'NO published contour exists for any of these')
    axes.grid(True, alpha = 0.22)
    axes.legend(loc = 'upper left', fontsize = 7.5, labelcolor = ink)

def draw():
    data = np.load(cachePath)
    validation = np.load(validationCache)

    figure, axes = plt.subplots(1, 3, figsize = (18.5, 6.0))
    drawRs25(axes[0], data)
    drawRaoFamily(axes[1], validation)
    drawReconstructed(axes[2], data)

    figure.suptitle('NOVA contours against their reference counterparts',
                    fontsize = 14, fontweight = 'bold')
    figure.tight_layout(rect = [0, 0.10, 1, 0.94])

    figure.text(0.012, 0.085,
                'Only the RS-25 publishes enough dimensional data to overlay, and its three quoted '
                'numbers disagree: a throat of 10.3 in with an exit of 90.7 in gives an area ratio '
                'of 77.6 against the published 69.5. Both readings\nof the envelope are drawn. The '
                'Rao bell in the middle panel follows exactly from its construction, so that '
                'comparison is like for like; it is a different contour family from a truncated '
                'ideal, which is why the two separate near the throat.\nThe right-hand panel is '
                'RECONSTRUCTED. No wall coordinates are published for the F-1, Vulcain 2 or RL10, '
                'and the dashed curves there are Rao bells at each engine\'s published area ratio '
                'and an assumed 80 percent length. Nothing in that\npanel is a dimensional claim '
                'about any of those engines.',
                fontsize = 8.5, color = ink, va = 'top')

    path = os.path.join(here, 'referenceOverlays.png')
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print(f'wrote {os.path.basename(path)}')

    report(data)

def report(data):
    print()
    print('=' * 96)
    print('CONTOURS AT PUBLISHED ENGINE OPERATING POINTS')
    print('=' * 96)
    print(f'{"engine":<12} {"eps":>7} {"bell":>7} {"throat mm":>11} {"exit mm":>10} '
          f'{"length mm":>11} {"theta_n":>9} {"theta_e":>9}')
    for name in engines:
        key = engineKey(name)
        if f'{key}_wallX' not in data:
            print(f'{name:<12}   solve failed')
            continue
        wallX, wallR = data[f'{key}_wallX'], data[f'{key}_wallR']
        print(f'{name:<12} {float(data[f"{key}_deliveredAreaRatio"]):7.2f} '
              f'{float(data[f"{key}_deliveredLengthFraction"]):7.3f} '
              f'{2*wallR[0]*1e3:11.1f} {2*wallR[-1]*1e3:10.1f} {wallX[-1]*1e3:11.1f} '
              f'{float(data[f"{key}_inflectionWallAngle"]):9.2f} '
              f'{float(data[f"{key}_exitWallAngle"]):9.2f}')

    print()
    print('Against published dimensions, where any exist:')
    for name, spec in engines.items():
        key = engineKey(name)
        if f'{key}_wallX' not in data:
            continue
        wallR = data[f'{key}_wallR']
        if spec['exitDiameter']:
            error = 100 * (2 * wallR[-1] / spec['exitDiameter'] - 1)
            print(f'  {name:<12} exit diameter {2*wallR[-1]*1e3:8.1f} mm against '
                  f'{spec["exitDiameter"]*1e3:8.1f} mm published  ({error:+6.2f} %)')
        if spec['throatDiameter']:
            error = 100 * (2 * wallR[0] / spec['throatDiameter'] - 1)
            print(f'  {name:<12} throat diameter {2*wallR[0]*1e3:6.1f} mm against '
                  f'{spec["throatDiameter"]*1e3:8.1f} mm published  ({error:+6.2f} %)')
        if spec['nozzleLength']:
            error = 100 * (data[f'{key}_wallX'][-1] / spec['nozzleLength'] - 1)
            print(f'  {name:<12} nozzle length {data[f"{key}_wallX"][-1]*1e3:8.1f} mm against '
                  f'{spec["nozzleLength"]*1e3:8.1f} mm published  ({error:+6.2f} %)')

def main():
    if '--draw' in sys.argv:
        draw()
    else:
        study()
        draw()

if __name__ == '__main__':
    main()
