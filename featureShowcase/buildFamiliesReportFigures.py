'''

Figures for the contour families report.

Every panel is drawn from a cache another script wrote or from a solve run here, so no number in
the report is typed by hand. The two studies are slow and are not re-run: `contourFamilies.npz`
carries the cross-family sweep, the grid convergence and the shock response, and
`subfamilyStudy.npz` carries the quadratic-against-cubic searches. The boundary layer and the
transonic models are cheap and are computed fresh.

Run: python featureShowcase/buildFamiliesReportFigures.py

Author: Sean Bowman

'''
import json
import os
import sys

import matplotlib
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'src'))

os.environ.setdefault('NOVA_HEADLESS', '1')
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt                                         # noqa: E402

from NOVA.Nozzle import Nozzle                                          # noqa: E402
from NOVA.boundaryLayer import offsetWall, solveBoundaryLayer           # noqa: E402
from NOVA.contourKernel import transonicModels, transonicThroatVelocity  # noqa: E402

outputFolder = os.path.join(root, 'src', 'NOVA', 'docs', 'reports', 'contourFamilies_2026-09-15')
os.makedirs(outputFolder, exist_ok = True)

# The report palette, so the figures sit inside the page rather than on top of it.
BG, SURFACE, BORDER = '#1a1e2a', '#22273a', '#3a4055'
TEXT, MUTED = '#d8e0ec', '#8a95a8'
ACCENT, GREEN, BLUE = '#E0975A', '#86C06C', '#7baee8'
PURPLE, RED, YELLOW = '#aa84d8', '#e08080', '#d4b86a'

plt.rcParams.update({
    'figure.facecolor': BG, 'axes.facecolor': SURFACE, 'savefig.facecolor': BG,
    'text.color': TEXT, 'axes.labelcolor': TEXT, 'axes.edgecolor': BORDER,
    'xtick.color': MUTED, 'ytick.color': MUTED, 'grid.color': BORDER,
    'axes.titlecolor': TEXT, 'font.size': 9, 'axes.titlesize': 10,
    'legend.facecolor': SURFACE, 'legend.edgecolor': BORDER, 'legend.framealpha': 0.9,
})

def finish(figure, name: str) -> None:
    figure.tight_layout()
    path = os.path.join(outputFolder, name)
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print(f'  wrote {name}')

families = ('truncatedIdeal', 'thrustOptimizedParabola', 'thrustOptimizedContour')
familyLabels = {'truncatedIdeal': 'truncated ideal',
                'thrustOptimizedParabola': 'thrust-optimized parabola',
                'thrustOptimizedContour': 'searched contour'}
familyColors = {'truncatedIdeal': BLUE, 'thrustOptimizedParabola': ACCENT,
                'thrustOptimizedContour': GREEN}

study = dict(np.load(os.path.join(here, 'contourFamilies.npz'), allow_pickle = False))
subfamily = dict(np.load(os.path.join(here, 'subfamilyStudy.npz'), allow_pickle = False))
designPoints = [tuple(row) for row in study['designPoints']]

#--------------------------------------------------------------------------------------------------------------------------#
# -- The three families -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawFamilies():

    figure, (wallPanel, deltaPanel, thrustPanel) = plt.subplots(1, 3, figsize = (16.0, 4.6))

    index = designPoints.index((40.0, 0.80))
    walls = {}
    for family in families:
        x = study.get(f'design_{family}_wallX_{index}')
        r = study.get(f'design_{family}_wallR_{index}')
        if x is None:
            continue
        walls[family] = (np.asarray(x, dtype = float), np.asarray(r, dtype = float))
        style = '--' if family == 'thrustOptimizedContour' else '-'
        wallPanel.plot(x, r, style, color = familyColors[family], linewidth = 1.8,
                       label = familyLabels[family])
    wallPanel.set_xlabel('axial station, throat radii')
    wallPanel.set_ylabel('wall radius, throat radii')
    wallPanel.set_title('Diverging walls, area ratio 40 at 80 per cent bell')
    wallPanel.legend(loc = 'lower right', fontsize = 8)
    wallPanel.grid(alpha = 0.25)

    # The three walls are within about one per cent of each other, so the separation only reads
    # against one of them. All three start and end at the same two points by construction.
    if 'truncatedIdeal' in walls:
        baseX, baseR = walls['truncatedIdeal']
        for family in families:
            if family == 'truncatedIdeal' or family not in walls:
                continue
            x, r = walls[family]
            style = '--' if family == 'thrustOptimizedContour' else '-'
            deltaPanel.plot(x,
                            100.0 * (np.interp(x, baseX, baseR) - r) / np.interp(x, baseX, baseR),
                            style, color = familyColors[family], linewidth = 1.8,
                            label = familyLabels[family])
        deltaPanel.axhline(0.0, color = BORDER, linewidth = 1.0)
        deltaPanel.set_xlabel('axial station, throat radii')
        deltaPanel.set_ylabel('wall radius below the truncated ideal, per cent')
        deltaPanel.set_title('Where the families actually differ\n'
                             'the two coincide here: the search returned its incumbent',
                             fontsize = 9)
        deltaPanel.legend(loc = 'upper right', fontsize = 8)
        deltaPanel.grid(alpha = 0.25)

    # The truncated ideal contour is the zero line here rather than a third bar.
    labels = [f'{int(eps)}\n{bell:.2f}' for eps, bell in designPoints]
    base = study['design_truncatedIdeal_normalizedThrustCoef']
    positions = np.arange(len(designPoints))
    width = 0.38
    for offset, family in zip((-0.5 * width, 0.5 * width), families[1:]):
        values = study[f'design_{family}_normalizedThrustCoef']
        thrustPanel.bar(positions + offset, 100.0 * (values / base - 1.0), width,
                        color = familyColors[family], alpha = 0.9, label = familyLabels[family])
    thrustPanel.axhline(0.0, color = BLUE, linewidth = 1.4, label = 'truncated ideal, the baseline')
    thrustPanel.set_xticks(positions)
    thrustPanel.set_xticklabels(labels, fontsize = 8)
    thrustPanel.set_xlabel('area ratio and bell fraction')
    thrustPanel.set_ylabel('per cent against truncated ideal')
    thrustPanel.set_title('Thrust coefficient over exit mass closure')
    thrustPanel.legend(loc = 'upper left', fontsize = 8)
    thrustPanel.grid(axis = 'y', alpha = 0.25)

    finish(figure, 'families.png')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Grid convergence -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawGridConvergence():

    figure, (rawPanel, ratioPanel) = plt.subplots(1, 2, figsize = (13.0, 4.4))

    for family in families:
        mesh = study[f'mesh_{family}_mesh']
        raw = study[f'mesh_{family}_thrustCoef']
        ratio = study[f'mesh_{family}_normalizedThrustCoef']
        rawPanel.plot(mesh, 100.0 * (raw / raw[-1] - 1.0), 'o-', color = familyColors[family],
                      linewidth = 1.6, markersize = 4, label = familyLabels[family])
        ratioPanel.plot(mesh, 100.0 * (ratio / ratio[-1] - 1.0), 'o-',
                        color = familyColors[family], linewidth = 1.6, markersize = 4,
                        label = familyLabels[family])

    for panel, title in ((rawPanel, 'Raw thrust coefficient'),
                         (ratioPanel, 'Divided by exit mass closure')):
        panel.axhline(0.0, color = BORDER, linewidth = 1.0)
        panel.set_xlabel('characteristics launched from the throat arc')
        panel.set_ylabel('per cent against the finest mesh')
        panel.set_title(title)
        panel.grid(alpha = 0.25)
        panel.legend(loc = 'lower right', fontsize = 8)

    finish(figure, 'gridConvergence.png')

#--------------------------------------------------------------------------------------------------------------------------#
# -- The searched subfamily -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawSubfamily():

    points = ((40, 80), (70, 80))
    figure, panels = plt.subplots(1, len(points), figsize = (12.0, 4.6))

    for panel, (eps, bell) in zip(np.atleast_1d(panels), points):
        quadratic, cubic = f'{eps}_{bell}_quadratic', f'{eps}_{bell}_cubic'
        chart = (float(subfamily[f'{quadratic}_incumbentThrustCoef'][0])
                 / float(subfamily[f'{quadratic}_incumbentClosure'][0]))
        searchedQuadratic = (float(subfamily[f'{quadratic}_thrustCoef'][0])
                             / float(subfamily[f'{quadratic}_exitMassClosure'][0]))
        searchedCubic = (float(subfamily[f'{cubic}_thrustCoef'][0])
                         / float(subfamily[f'{cubic}_exitMassClosure'][0]))

        values = [chart, searchedQuadratic, searchedCubic]
        labels = ['chart\nparabola', 'optimized\nquadratic', 'optimized\ncubic']
        panel.bar(labels, values, color = [MUTED, ACCENT, GREEN], alpha = 0.9)

        span = max(values) - min(values)
        floor = min(values) - 3.5 * span - 1e-9
        panel.set_ylim(floor, max(values) + 1.6 * span + 1e-9)
        for position, value in enumerate(values):
            panel.text(position, value, f'{value:.5f}', ha = 'center', va = 'bottom',
                       fontsize = 8, color = TEXT)

        chartCost = 100.0 * (searchedQuadratic / chart - 1.0)
        freedom = 100.0 * (searchedCubic / searchedQuadratic - 1.0)
        panel.set_title(f'Area ratio {eps}, {bell} per cent bell\n'
                        f'chart costs {chartCost:+.3f} %, cubic freedom buys {freedom:+.3f} %',
                        fontsize = 9)
        panel.set_ylabel('thrust coefficient over mass closure')
        panel.grid(axis = 'y', alpha = 0.25)

    finish(figure, 'subfamily.png')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Shock capture -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawShock():

    offsets = study['turningOffsets']
    isCubic = study['turningIsCubic']
    detected = study['turning_shockDetected'] > 0
    # The first row is the parabola written as a parabola; the rest are cubics, and the second is
    # the same wall written as a cubic. Plot the cubic rows so the axis is one family.
    rows = np.where(isCubic > 0)[0]

    figure, (frontPanel, costPanel) = plt.subplots(1, 2, figsize = (13.0, 4.6))

    x = offsets[rows]
    deflection = np.degrees(study['turning_shockPeakDeflection'][rows])
    onset = study['turning_shockOnsetX'][rows]
    ratio = study['turning_shockStagnationRatio'][rows]
    debit = 100.0 * study['turning_shockThrustDebit'][rows]
    closure = 100.0 * study['turning_exitMassClosure'][rows]
    found = detected[rows]

    frontPanel.plot(x[found], deflection[found], 'o-', color = ACCENT, linewidth = 1.8,
                    markersize = 5, label = 'total wall turning absorbed')
    frontPanel.set_xlabel('inflection angle past the chart parabola, degrees')
    frontPanel.set_ylabel('front deflection, degrees', color = ACCENT)
    frontPanel.tick_params(axis = 'y', labelcolor = ACCENT)
    frontPanel.grid(alpha = 0.25)

    twin = frontPanel.twinx()
    twin.plot(x[found], onset[found], 's--', color = BLUE, linewidth = 1.6, markersize = 4,
              label = 'onset station')
    twin.set_ylabel('onset station, throat radii', color = BLUE)
    twin.tick_params(axis = 'y', labelcolor = BLUE)
    twin.set_facecolor('none')
    frontPanel.set_title('Onset moves upstream as the wall turns harder')

    handles = frontPanel.get_legend_handles_labels()[0] + twin.get_legend_handles_labels()[0]
    labels = (frontPanel.get_legend_handles_labels()[1] + twin.get_legend_handles_labels()[1])
    frontPanel.legend(handles, labels, loc = 'upper left', fontsize = 8)

    costPanel.plot(x[found], ratio[found], 'o-', color = GREEN, linewidth = 1.8, markersize = 5,
                   label = 'stagnation pressure surviving')
    costPanel.axhline(0.99, color = YELLOW, linestyle = ':', linewidth = 1.4,
                      label = 'weak-shock threshold')
    costPanel.set_xlabel('inflection angle past the chart parabola, degrees')
    costPanel.set_ylabel('stagnation ratio across the front', color = GREEN)
    costPanel.tick_params(axis = 'y', labelcolor = GREEN)
    costPanel.grid(alpha = 0.25)

    costTwin = costPanel.twinx()
    costTwin.bar(x[found], -debit[found], width = 0.8, color = RED, alpha = 0.55,
                 label = 'thrust debit charged')
    costTwin.set_ylabel('thrust debit charged, per cent', color = RED)
    costTwin.tick_params(axis = 'y', labelcolor = RED)
    costTwin.set_facecolor('none')
    costPanel.set_title('The capture charges nothing while the front stays weak')

    handles = costPanel.get_legend_handles_labels()[0] + costTwin.get_legend_handles_labels()[0]
    labels = costPanel.get_legend_handles_labels()[1] + costTwin.get_legend_handles_labels()[1]
    costPanel.legend(handles, labels, loc = 'lower left', fontsize = 8)

    finish(figure, 'shockCapture.png')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Throat geometry and the transonic starting line -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawThroatAndTransonic():

    figure, (arcPanel, modelPanel) = plt.subplots(1, 2, figsize = (13.0, 4.6))

    # Rao's throat, and what opening the entrant arc to the value SP-8120 prefers does to it.
    for curvature, color, style in ((1.5, ACCENT, '-'), (1.0, BLUE, '--'), (0.6, PURPLE, ':')):
        angles = np.linspace(np.radians(-135.0), np.radians(-90.0), 200)
        arcPanel.plot(curvature * np.cos(angles), curvature * np.sin(angles) + curvature + 1.0,
                      style, color = color, linewidth = 1.8,
                      label = f'entrant arc {curvature} $R_t$')
    exitAngles = np.linspace(np.radians(-90.0), np.radians(-55.0), 120)
    arcPanel.plot(0.382 * np.cos(exitAngles), 0.382 * np.sin(exitAngles) + 1.382,
                  color = GREEN, linewidth = 2.2, label = 'exit arc 0.382 $R_t$')
    arcPanel.axhline(1.0, color = BORDER, linewidth = 1.0)
    arcPanel.set_xlabel('axial station, throat radii')
    arcPanel.set_ylabel('wall radius, throat radii')
    arcPanel.set_title('Throat arcs, both now selectable')
    arcPanel.legend(loc = 'upper center', fontsize = 8)
    arcPanel.grid(alpha = 0.25)
    arcPanel.set_xlim(-1.3, 0.45)
    arcPanel.set_ylim(0.9, 2.3)

    # The three transonic models, as throat wall velocity against entrant curvature.
    curvatures = np.linspace(0.55, 3.0, 300)
    gamma = 1.1475421191138746
    styles = {'sauer': (ACCENT, '-'), 'secondOrder': (BLUE, '--'), 'smallRadius': (PURPLE, '-.')}
    for model in transonicModels:
        color, style = styles[model]
        velocity = [transonicThroatVelocity(gamma, value, model) for value in curvatures]
        modelPanel.plot(curvatures, velocity, style, color = color, linewidth = 1.8,
                        label = f"'{model}'")
    # Stacked at different heights so the two markers do not collide.
    marker = modelPanel.get_xaxis_transform()
    for value, height, label in ((1.5, 0.94, ' conventional 1.5'),
                                 (1.0, 0.80, ' SP-8120 prefers 1.0')):
        modelPanel.axvline(value, color = BORDER, linestyle = ':', linewidth = 1.2)
        modelPanel.text(value, height, label, fontsize = 8, color = MUTED,
                        va = 'center', transform = marker)
    modelPanel.set_xlabel('entrant arc curvature, throat radii')
    modelPanel.set_ylabel('throat wall velocity, $u / a^*$')
    modelPanel.set_title('Transonic models diverge exactly where the arc is opened')
    modelPanel.legend(loc = 'upper right', fontsize = 8)
    modelPanel.grid(alpha = 0.25)

    finish(figure, 'throatTransonic.png')

#--------------------------------------------------------------------------------------------------------------------------#
# -- The boundary layer -- #
#--------------------------------------------------------------------------------------------------------------------------#

def workedContour():

    config = json.load(open(os.path.join(root, 'src', 'NOVA', 'assets', 'loxLh2Example.json')))
    config.update({'plumeAmbientPressure': None, 'plotsBasic': False, 'plotsAdv': False,
                   'export': False, 'visualizeContour': False, 'makeCoolingChannels': 'off',
                   'filename': 'familiesReport'})
    scratch = os.path.join(root, 'runs', 'familiesReport')
    os.makedirs(scratch, exist_ok = True)
    path = os.path.join(scratch, 'config.json')
    json.dump(config, open(path, 'w'), indent = 2)
    Nozzle._getOutputRoot = lambda self, _base = scratch: _base
    nozzle = Nozzle()
    nozzle.setInputs(inputsPath = path)
    nozzle.pressureMatchTruncatedIdealContour(0.80)
    return nozzle

def drawBoundaryLayer():

    nozzle = workedContour()
    x = np.asarray(nozzle.xNozzleWall, dtype = float)
    radius = np.asarray(nozzle.rNozzleWall, dtype = float)
    layer = solveBoundaryLayer(x, radius,
                               np.asarray(nozzle.nozzleNearWallMachNumber, dtype = float),
                               np.asarray(nozzle.nozzleNearWallTemperature, dtype = float),
                               np.asarray(nozzle.nozzleNearWallPressure, dtype = float),
                               np.asarray(nozzle.nozzleNearWallVelocity, dtype = float),
                               nozzle.chamberGamma, nozzle.chamberRGasConstant, 800.0)

    figure, (thicknessPanel, frictionPanel, dragPanel) = plt.subplots(1, 3, figsize = (15.0, 4.4))

    thicknessPanel.plot(1000.0 * x, 1000.0 * layer['displacementThickness'], color = ACCENT,
                        linewidth = 1.8, label = 'displacement thickness $\\delta^*$')
    thicknessPanel.plot(1000.0 * x, 1000.0 * layer['momentumThickness'], color = BLUE,
                        linewidth = 1.8, label = 'momentum thickness $\\theta$')
    thicknessPanel.set_xlabel('axial station, mm')
    thicknessPanel.set_ylabel('thickness, mm')
    thicknessPanel.set_title('Layer growth along the wall')
    thicknessPanel.legend(loc = 'upper left', fontsize = 8)
    thicknessPanel.grid(alpha = 0.25)

    cf = np.asarray(layer['frictionCoefficient'], dtype = float)
    frictionPanel.plot(1000.0 * x, cf, color = GREEN, linewidth = 1.8,
                       label = 'NOVA, reference temperature')
    frictionPanel.axhline(0.003, color = YELLOW, linestyle = '--', linewidth = 1.6,
                          label = 'RP-1104 representative 0.003')
    frictionPanel.set_xlabel('axial station, mm')
    frictionPanel.set_ylabel('Fanning skin friction coefficient')
    frictionPanel.set_title('Friction against the published reference')
    frictionPanel.legend(loc = 'upper right', fontsize = 8)
    frictionPanel.grid(alpha = 0.25)

    shear = np.asarray(layer['wallShear'], dtype = float)
    dynamic = np.where(cf > 0, shear / np.where(cf > 0, cf, 1.0), 0.0)
    arcLength = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(radius)))])
    denominator = float(np.trapezoid(dynamic * 2.0 * np.pi * radius, arcLength))
    throatArea = np.pi * float(np.min(radius)) ** 2
    inviscid = float(nozzle.thrustCoef) * float(nozzle.chamberPressure) * throatArea

    values = [100.0 * float(layer['dragForce']) / inviscid,
              100.0 * 0.003 * denominator / inviscid]
    dragPanel.bar(['NOVA\nown friction', 'same integral\nat $c_f = 0.003$'], values,
                  color = [GREEN, YELLOW], alpha = 0.9)
    dragPanel.axhspan(0.5, 1.5, color = BLUE, alpha = 0.14)
    # The band label sits in reserved space to the right of the bars rather than over them.
    dragPanel.set_xlim(-0.6, 2.15)
    dragPanel.text(1.60, 1.0, 'published budget\n0.5 to 1.5 %', fontsize = 8, color = BLUE,
                   ha = 'left', va = 'center')
    for position, value in enumerate(values):
        dragPanel.text(position, value, f'{value:.2f} %', ha = 'center', va = 'bottom',
                       fontsize = 9, color = TEXT)
    dragPanel.set_ylabel('friction drag, per cent of inviscid thrust')
    dragPanel.set_title('Where the difference lives')
    dragPanel.set_ylim(0.0, 2.6)
    dragPanel.grid(axis = 'y', alpha = 0.25)

    finish(figure, 'boundaryLayer.png')

    offsetX, offsetRadius = offsetWall(x, radius, layer['displacementThickness'])
    print(f'  exit radius {1000*radius[-1]:.3f} mm offsets to {1000*offsetRadius[-1]:.3f} mm')

if __name__ == '__main__':
    print('Building report figures:')
    drawFamilies()
    drawGridConvergence()
    drawSubfamily()
    drawShock()
    drawThroatAndTransonic()
    drawBoundaryLayer()
    print(f'\nfigures in {os.path.relpath(outputFolder, root)}')
