'''
Representative plotted outputs for the NOVA nozzle designer.

Renders geometry, flowfield, plume and material views from the renderer-independent figure
dataclasses in src/NOVA/figures.py, so the same data that drives the GUI panes and the
interactive exports also drives these figures.
'''
import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
from NOVA import figures as figureModule
from NOVA import materials as materialModule

#--------------------------------------------------------------------------------------------------------------------------#
# -- Palette -- #
#--------------------------------------------------------------------------------------------------------------------------#

background = '#1a1e2a'
panel      = '#222735'
copper     = '#E0975A'
green      = '#86C06C'
ink        = '#E8E6E1'
muted      = '#8B93A7'
blue       = '#6BA3D6'

# One hue per wall alloy. A sampled colormap put the four copper alloys within a few
# degrees of each other, which is unreadable on a ten-series axis, so the assignment is
# explicit: warm for the coppers, cool for everything else.
materialColors = {
    'GRCop-42':    '#E0975A',
    'CuCrZr':      '#F4C95D',
    'OFHC Copper': '#FF7043',
    'NARloy-Z':    '#B5651D',
    'AlSi10Mg':    '#6BA3D6',
    'Al 6061-T6':  '#9BD1E5',
    'Inconel 718': '#86C06C',
    'Inconel 625': '#4F9D69',
    '316L':        '#C792EA',
    'Ti-6Al-4V':   '#D8DEE9',
}

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': '#333A4D',
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
    data = figureModule.contourFigure(nozzle)
    figure, axes = plt.subplots(figsize = (11, 4.2))
    x, r = np.asarray(data.x) * 1e3, np.asarray(data.r) * 1e3
    axes.plot(x, r, color = copper, lw = 1.8)
    axes.plot(x, -r, color = copper, lw = 1.8)
    axes.fill_between(x, r, -r, color = copper, alpha = 0.08)

    if len(data.xRegen):
        xRegen, rRegen = np.asarray(data.xRegen) * 1e3, np.asarray(data.rRegen) * 1e3
        axes.plot(xRegen, rRegen, color = green, lw = 1.2, label = 'regen jacket')
        axes.plot(xRegen, -rRegen, color = green, lw = 1.2)

    axes.axvline(data.throatX * 1e3, color = muted, ls = '--', lw = 0.9)
    axes.annotate(f'throat  r = {data.throatRadius * 1e3:.1f} mm',
                  (data.throatX * 1e3, 0.0), textcoords = 'offset points',
                  xytext = (6, 6), color = muted, fontsize = 8)

    chamberDiameter = getattr(nozzle, 'chamberDiameter', None)
    if chamberDiameter:
        axes.axhline(chamberDiameter * 0.5e3, color = blue, ls = ':', lw = 1.0)
        axes.axhline(-chamberDiameter * 0.5e3, color = blue, ls = ':', lw = 1.0)
        axes.annotate(f'chamber D = {chamberDiameter * 1e3:.0f} mm',
                      (x[0], chamberDiameter * 0.5e3), textcoords = 'offset points',
                      xytext = (8, 6), color = blue, fontsize = 8)

    axes.set_xlabel('Axial station [mm]')
    axes.set_ylabel('Radius [mm]')
    axes.set_title('Nozzle contour with generated combustion chamber')
    axes.set_aspect('equal', adjustable = 'box')
    return savePanel(figure, 'contour.png')

def drawNearWall(nozzle):
    '''Near-wall exhaust state along the axis.'''
    data = figureModule.nearWallFigure(nozzle)
    figure, axesList = plt.subplots(3, 1, figsize = (9, 7), sharex = True)
    axis = np.asarray(data.axis) * 1e3

    panels = ((axesList[0], data.temperature, 'Static temperature [K]', copper, 1.0),
              (axesList[1], data.pressure, 'Static pressure [MPa]', green, 1e-6),
              (axesList[2], data.mach, 'Mach number [-]', blue, 1.0))
    for axes, values, label, color, scale in panels:
        axes.plot(axis, np.asarray(values) * scale, color = color, lw = 1.6)
        axes.set_ylabel(label)

    axesList[0].set_title('Near-wall exhaust state')
    axesList[-1].set_xlabel('Axial station [mm]')
    return savePanel(figure, 'nearWallState.png')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Flowfield -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawField(nozzle, quantity, name):
    '''
    Method-of-characteristics field over the curvilinear mesh. The color bar sits below the
    axes so the plot itself takes the full width of the panel.
    '''
    data = figureModule.fieldFigure(nozzle, quantity)
    if data is None:
        print(f'  skipped {name}: no {quantity} field on this run')
        return None

    figure = plt.figure(figsize = (11, 4.6))
    grid = GridSpec(2, 1, height_ratios = [1.0, 0.05], hspace = 0.35, figure = figure)
    axes = figure.add_subplot(grid[0])

    # The mesh is curvilinear and padded with NaN, so the field is drawn from the finite nodes
    # directly rather than as a structured grid.
    xs, rs, vs = [], [], []
    for xBlock, rBlock, valueBlock in zip(data.xBlocks, data.rBlocks, data.valueBlocks):
        xBlock = np.asarray(xBlock, dtype = float).ravel()
        rBlock = np.asarray(rBlock, dtype = float).ravel()
        valueBlock = np.asarray(valueBlock, dtype = float).ravel()
        keep = np.isfinite(xBlock) & np.isfinite(rBlock) & np.isfinite(valueBlock)
        xs.append(xBlock[keep])
        rs.append(rBlock[keep])
        vs.append(valueBlock[keep])

    scale = 1e-6 if quantity == 'pressure' else 1.0
    xs = np.concatenate(xs) * 1e3
    rs = np.concatenate(rs) * 1e3
    vs = np.concatenate(vs) * scale

    mesh = axes.tricontourf(np.concatenate([xs, xs]), np.concatenate([rs, -rs]),
                            np.concatenate([vs, vs]), levels = 80, cmap = 'viridis')
    wallX, wallR = np.asarray(data.wallX) * 1e3, np.asarray(data.wallR) * 1e3
    axes.plot(wallX, wallR, color = copper, lw = 1.4)
    axes.plot(wallX, -wallR, color = copper, lw = 1.4)
    # The contour is a truncated ideal nozzle, so the characteristics mesh extends past the
    # delivered wall to the full ideal exit. Clip to the wall that is actually built.
    axes.set_xlim(wallX.min(), wallX.max())
    axes.set_ylim(-1.08 * abs(wallR).max(), 1.08 * abs(wallR).max())
    axes.set_xlabel('Axial station [mm]')
    axes.set_ylabel('Radius [mm]')
    axes.set_title(data.title)
    axes.set_aspect('equal', adjustable = 'box')
    axes.grid(False)

    label = data.label.replace('[Pa]', '[MPa]') if quantity == 'pressure' else data.label
    figure.colorbar(mesh, cax = figure.add_subplot(grid[1]), orientation = 'horizontal',
                    label = label)
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
    drawField(nozzle, 'mach', 'fieldMach.png')
    drawField(nozzle, 'pressure', 'fieldPressure.png')
    drawField(nozzle, 'temperature', 'fieldTemperature.png')
    drawMaterialCurves()
    drawCryogenicRatio()

    if figureModule.plotlyAvailable:
        written = figureModule.exportInteractiveFigures(nozzle, here)
        print(f'  wrote {len(written)} interactive figures')
    else:
        print('  plotly not installed, interactive export skipped')

if __name__ == '__main__':
    main()
