'''
Representative plotted outputs for the NOVA nozzle designer.

Renders geometry, flowfield, plume and material views from the renderer-independent figure
dataclasses in src/NOVA/figures.py, so the same data that drives the GUI panes and the
interactive exports also drives these figures. The contour, near-wall and field panels are
drawn by the same Matplotlib renderers a real run calls to write its own PNGs, so neither can
drift from the other.
'''
import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np

import showcasePalette

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
from NOVA import figures as figureModule
from NOVA import materials as materialModule

#--------------------------------------------------------------------------------------------------------------------------#
# -- Palette -- #
#--------------------------------------------------------------------------------------------------------------------------#

background = showcasePalette.background
panel      = showcasePalette.panel
ink        = showcasePalette.ink
muted      = showcasePalette.muted

# One color per wall alloy. A sampled colormap put the four copper alloys within a few
# degrees of each other, which is unreadable on a ten-series axis, so the assignment is
# explicit: the palette's warm metals for the coppers, its cool ones for everything else.
# The palette's orange and cyan sit too close to its copper and green to tell apart on a thin
# line, so the second alloy of each family takes a lighter step of the first's hue instead.
materialColors = {
    'GRCop-42':    showcasePalette.copper,
    'CuCrZr':      showcasePalette.yellow,
    'OFHC Copper': showcasePalette.mix(showcasePalette.copper, showcasePalette.ink, 0.5),
    'NARloy-Z':    showcasePalette.red,
    'AlSi10Mg':    showcasePalette.blue,
    'Al 6061-T6':  showcasePalette.mix(showcasePalette.blue, showcasePalette.ink, 0.55),
    'Inconel 718': showcasePalette.green,
    'Inconel 625': showcasePalette.muted,
    '316L':        showcasePalette.purple,
    'Ti-6Al-4V':   showcasePalette.ink,
}

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': showcasePalette.gridColor,
    'axes.grid': True, 'grid.alpha': 0.4, 'font.size': 9,
    'axes.titlesize': 11, 'axes.titleweight': 'bold', 'legend.framealpha': 0.0,
})

def savePanel(figure, name):
    '''Write one figure into the showcase folder.'''
    path = os.path.join(here, name)
    figure.savefig(path, dpi = 160, bbox_inches = 'tight')
    plt.close(figure)
    print(f'  wrote {name}')
    return path

#--------------------------------------------------------------------------------------------------------------------------#
# -- Geometry -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawContour(nozzle):
    '''Wall contour with the generated combustion chamber called out.'''
    figure = figureModule.drawContourFigure(nozzle)
    return savePanel(figure, 'contour.png') if figure is not None else None

def drawNearWall(nozzle):
    '''Near-wall exhaust state along the axis.'''
    figure = figureModule.drawNearWallFigure(nozzle)
    return savePanel(figure, 'nearWallState.png') if figure is not None else None

def drawJacket(nozzle):
    '''
    One cooling channel and its two neighbors against the cold wall.

    The jacket is this channel patterned about the axis `nChannel` times, so a pair of neighbors
    is enough to draw the rib to scale without building the pattern. The view is a plotly scene
    rather than a Matplotlib panel, so it is written through kaleido with a fixed camera: a
    figure that moves between runs cannot be compared against the one before it.
    '''
    figure = figureModule.channelMeshFigure(nozzle)
    if figure is None:
        print('  skipped jacket.png: no channel on this run')
        return None
    figure.update_layout(
        width = 1600, height = 780,
        scene_camera = dict(eye = dict(x = 1.25, y = -1.15, z = 0.62),
                            center = dict(x = 0.0, y = 0.0, z = -0.18)),
        title = {'text': 'One cooling channel and its neighbors against the cold wall',
                 'x': 0.5, 'xanchor': 'center', 'y': 0.96, 'yanchor': 'top'},
        margin = dict(l = 0, r = 0, t = 50, b = 0),
        paper_bgcolor = background)
    path = os.path.join(here, 'jacket.png')
    figure.write_image(path, width = 1600, height = 780, scale = 1)
    print('  wrote jacket.png')
    return path

#--------------------------------------------------------------------------------------------------------------------------#
# -- Flowfield -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawField(nozzle, quantity, name):
    '''Method-of-characteristics field over the curvilinear mesh, one quantity per call.'''
    figure = figureModule.drawFieldFigure(nozzle, quantity)
    if figure is None:
        print(f'  skipped {name}: no {quantity} field on this run')
        return None
    return savePanel(figure, name)
def drawMaterialCurves():

    """
    Wall property curves behind the material selector.

    A curve is drawn solid over the temperatures its source actually measured and dotted where
    the nearest measured value is held flat, which `materials.propertyProvenance` reports per
    property. The distinction matters because a held value is broadcast across the grid and comes
    back the same shape as data: an interpolator built on it returns a constant and looks exactly
    like one built on a real curve.

    Temperature is logarithmic so the cryogenic decade is legible beside the hot one. Coolant
    inlet temperatures are marked because that is where the curves were previously clamped.
    """

    names = materialModule.availableWallMaterials()
    figure, axesGrid = plt.subplots(2, 2, figsize = (13, 8.4))
    axesFlat = axesGrid.ravel()
    colors = [materialColors[name] for name in names]

    panels = (('thermalConductivity', 'Thermal conductivity [W/m-K]', 1.0,   True),
              ('yieldStrength',       '0.2 % offset yield [MPa]',     1e-6,  False),
              ('cte',                 'Mean CTE from 293 K [1e-6/K]', 1e6,   False),
              ('elongation',          'Elongation [%]',               1.0,   False))

    handles, labels = [], []

    for index, (axes, (key, label, scale, logY)) in enumerate(zip(axesFlat, panels)):

        for name, color in zip(names, colors):

            curves = materialModule.wallMaterialCurves(name)
            kelvin = np.asarray(curves['temperatureK'], dtype = float)
            values = np.asarray(curves[key], dtype = float) * scale

            _, (lowC, highC) = materialModule.propertyProvenance(name, key)
            lowK, highK = lowC + 273.15, highC + 273.15

            # The span the source measured, and everything outside it.
            measured = (kelvin >= lowK - 1.0) & (kelvin <= highK + 1.0)

            # Dotted for the held part, drawn first so the measured line sits on top.
            axes.plot(kelvin, values, color = color, lw = 1.0, ls = ':', alpha = 0.5)

            if measured.sum() > 1:
                line, = axes.plot(kelvin[measured], values[measured], color = color,
                                  lw = 1.8, ls = '-', label = name)
            else:
                line, = axes.plot(kelvin, values, color = color, lw = 1.0, ls = ':',
                                  alpha = 0.5, label = name)

            if index == 0:
                handles.append(line)
                labels.append(name)

        axes.set_xscale('log')
        if logY:
            axes.set_yscale('log')
        axes.set_xlabel('Temperature [K]')
        axes.set_ylabel(label)
        axes.set_xlim(18, 1300)

        # Where the coolant enters. Every curve used to be clamped below these.
        for temperature, tag in ((20.3, 'LH2'), (90.2, 'LOX')):
            axes.axvline(temperature, color = muted, lw = 0.8, ls = '--', alpha = 0.5)
            axes.annotate(tag, xy = (temperature, 0.02), xycoords = ('data', 'axes fraction'),
                          color = muted, fontsize = 7, ha = 'right', rotation = 90)

    axesFlat[0].set_title('Thermal conductivity: copper rises as it cools, the alloys fall',
                          loc = 'left')
    axesFlat[1].set_title('Yield strength', loc = 'left')
    axesFlat[2].set_title('Thermal expansion', loc = 'left')
    axesFlat[3].set_title('Elongation', loc = 'left')

    figure.suptitle('Wall material property curves    '
                    'solid where the source measured it, dotted where a value is held flat',
                    color = ink, fontsize = 10, x = 0.012, ha = 'left', y = 0.995)

    figure.legend(handles, labels, fontsize = 8, ncol = 5, loc = 'lower center',
                  bbox_to_anchor = (0.5, -0.035), labelcolor = ink)
    figure.tight_layout(rect = (0, 0.02, 1, 0.975))

    return savePanel(figure, 'materialCurves.png')

def drawCryogenicRatio():

    """
    What extending the grids to 20 K was worth.

    Every curve used to stop at room temperature, so a jacket running liquid hydrogen was sized
    on a conductivity clamped to its room-temperature value. This is the size of that error, and
    it does not have a consistent sign: pure copper conducts several times better cold because
    electron scattering falls away in a nearly perfect lattice, while every alloy conducts worse.
    """

    withCryogenic, withoutCryogenic = [], []
    for name in materialModule.availableWallMaterials():
        grid = materialModule.wallMaterialCurves(name)['temperatureK']
        (withCryogenic if grid.min() <= 25.0 else withoutCryogenic).append(name)

    ratios = []
    for name in withCryogenic:
        cold = materialModule.sampleWallMaterial(name, 20.3)['thermalConductivity']
        room = materialModule.sampleWallMaterial(name, 298.15)['thermalConductivity']
        ratios.append((name, cold / room))
    ratios.sort(key = lambda pair: pair[1])

    figure, axes = plt.subplots(figsize = (8.5, 4.2))

    positions = np.arange(len(ratios))
    values = [ratio for _, ratio in ratios]
    barColors = [materialColors[name] for name, _ in ratios]

    axes.set_axisbelow(True)
    axes.barh(positions, values, color = barColors, height = 0.6)
    axes.axvline(1.0, color = ink, lw = 1.2)
    axes.annotate('clamped: what every curve returned\nbefore the grids reached 20 K',
                  xy = (1.0, 1.55), xytext = (1.5, 2.35),
                  color = ink, fontsize = 8,
                  arrowprops = dict(arrowstyle = '->', color = ink, lw = 0.9))

    for position, (name, ratio) in enumerate(ratios):
        axes.annotate('{:.3f}x'.format(ratio), xy = (ratio, position),
                      xytext = (6, 0), textcoords = 'offset points',
                      va = 'center', color = ink, fontsize = 9)

    axes.set_yticks(positions)
    axes.set_yticklabels([name for name, _ in ratios])
    axes.set_xlabel('Thermal conductivity at 20 K, as a fraction of its value at 298 K')
    axes.set_xlim(0, 4.1)
    axes.set_title('Conductivity at liquid hydrogen temperature', loc = 'left')

    footnote = ('Still clamped, no cryogenic source: ' + ', '.join(sorted(withoutCryogenic))
                + '.\nOFHC copper assumes RRR 50; the 20 K peak spans 1368 to 3245 W/m-K '
                  'over RRR 50 to 150.')
    figure.text(0.012, -0.06, footnote, color = muted, fontsize = 7.5, ha = 'left')

    figure.tight_layout()

    return savePanel(figure, 'materialCryogenicRatio.png')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Driver -- #
#--------------------------------------------------------------------------------------------------------------------------#

def main():
    '''Render the full showcase from the pickled base run.'''
    with open(os.path.join(here, 'showcaseBase.pkl'), 'rb') as handle:
        nozzle = pickle.load(handle)

    print('Rendering showcase figures')
    drawContour(nozzle)
    drawNearWall(nozzle)
    drawJacket(nozzle)
    drawField(nozzle, 'mach', 'fieldMach.png')
    drawField(nozzle, 'pressure', 'fieldPressure.png')
    drawField(nozzle, 'temperature', 'fieldTemperature.png')
    drawMaterialCurves()
    drawCryogenicRatio()

    written = figureModule.exportInteractiveFigures(nozzle, here)
    print(f'  wrote {len(written)} interactive figures')

if __name__ == '__main__':
    main()
