'''
Representative plotted outputs for the NOVA nozzle designer.

Renders geometry, flowfield, plume and material views from the renderer-independent figure
dataclasses in NOVANozzleDesigner/figures.py, so the same data that drives the GUI panes and the
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
sys.path.insert(0, os.path.join(root, 'NOVANozzleDesigner'))

import figures as figureModule
import materials as materialModule

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
    for axes, values, label, colour, scale in panels:
        axes.plot(axis, np.asarray(values) * scale, color = colour, lw = 1.6)
        axes.set_ylabel(label)

    axesList[0].set_title('Near-wall exhaust state')
    axesList[-1].set_xlabel('Axial station [mm]')
    return savePanel(figure, 'nearWallState.png')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Flowfield -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawField(nozzle, quantity, name):
    '''
    Method-of-characteristics field over the curvilinear mesh. The colour bar sits below the
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

    Solid lines carry measured temperature-dependent data. Dashed lines are materials held at a
    single value across the range, which the materials module flags as a fallback; they are drawn
    differently so the figure does not imply data that is not there.
    """
    names = materialModule.availableWallMaterials()
    figure, axesGrid = plt.subplots(1, 3, figsize = (13, 4.4))
    colours = plt.cm.plasma(np.linspace(0.12, 0.92, len(names)))

    panels = (('thermalConductivity', 'Thermal conductivity [W/m-K]', 1.0),
              ('yieldStrength',       'Yield strength [MPa]',         1e-6),
              ('cte',                 'CTE [1e-6 / K]',               1e6))
    handles, labels = [], []
    for index, (axes, (key, label, scale)) in enumerate(zip(axesGrid, panels)):
        for name, colour in zip(names, colours):
            curves = materialModule.wallMaterialCurves(name)
            values = np.asarray(curves[key], dtype = float) * scale
            constant = np.allclose(values, values[0])
            line, = axes.plot(curves['temperatureK'], values, color = colour,
                              lw = 1.5 if not constant else 1.0,
                              ls = '-' if not constant else '--',
                              alpha = 1.0 if not constant else 0.55, label = name)
            if index == 0:
                handles.append(line)
                labels.append(name)
        axes.set_xlabel('Temperature [K]')
        axes.set_ylabel(label)

    axesGrid[0].set_title('Wall material property curves   (dashed: single-value data)',
                          loc = 'left')
    figure.legend(handles, labels, fontsize = 8, ncol = 5, loc = 'lower center',
                  bbox_to_anchor = (0.5, -0.06), labelcolor = ink)
    figure.tight_layout()
    return savePanel(figure, 'materialCurves.png')

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

    if figureModule.plotlyAvailable:
        written = figureModule.exportInteractiveFigures(nozzle, here)
        print(f'  wrote {len(written)} interactive figures')
    else:
        print('  plotly not installed, interactive export skipped')

if __name__ == '__main__':
    main()
