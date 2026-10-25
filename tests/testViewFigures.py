# -- NOVA: The View Tab's Figures -- #

'''

The figure descriptions behind the GUI's flow, plume and cooling views, and the views themselves.

A flow field runs from the injector face to the exit plane: the quasi one-dimensional chamber
upstream of the throat, the characteristic mesh from the throat to the exit plane of the wall that
is built, never the mesh a truncated contour carries past it. The plume scene is one Mach field
from the chamber through the nozzle and into the march, on a scale set by the supersonic flow. The
cooling views draw from the jacket's station arrays, the film arrays and the extension solution.

The descriptions are checked on a synthetic nozzle, which is all they read; the views are drawn on
one carrying every array a cooled, film-cooled run with an extension keeps.

Author: Sean Bowman

'''

import os
import sys
import types

import numpy as np
import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (root, os.path.join(root, 'src')):
    if path not in sys.path:
        sys.path.insert(0, path)

from NOVA.figures import plumeSceneFigure, stitchedFieldFigure

def _syntheticNozzle(**extra):

    '''

    A converging-diverging wall in metres, a chamber state, and a characteristic mesh stored the way
    the contour solve stores it: normalized blocks that run on past the wall's exit plane, as a
    truncated contour's mesh does.

    '''

    chamber = np.linspace(-0.30, -0.10, 20)
    converging = np.linspace(-0.10, 0.0, 20)[1:]
    diverging = np.linspace(0.0, 0.60, 40)[1:]
    wallX = np.concatenate([chamber, converging, diverging])
    wallR = np.concatenate([np.full(chamber.size, 0.09), 0.05 + 0.04 * (converging / -0.10) ** 2,
                            0.05 + 0.40 * np.sqrt(diverging) * 0.4])

    # The mesh, in throat radii: it starts at the throat and reaches past the 0.60 m exit plane
    scale = 0.05
    meshX = np.linspace(0.0, 0.80, 30)[:, None] * np.ones((1, 8)) / scale
    meshR = np.linspace(0.0, 1.0, 8)[None, :] * (0.05 + 0.16 * np.sqrt(meshX * scale))[:, :1] / scale
    mach = 1.0 + 3.0 * np.sqrt(meshX * scale / 0.8)

    nozzle = types.SimpleNamespace(
        xNozzleWall = wallX, rNozzleWall = wallR, nozzleScalingFactor = scale,
        allXPoints = [meshX], allRPoints = [meshR], allMachNumbers = [mach],
        allPressures = [7e6 / mach ** 6], allTemperatures = [3400.0 / (1.0 + 0.1 * mach ** 2)],
        chamberGamma = 1.2, chamberRGasConstant = 600.0, chamberStagnationTemperature = 3400.0,
        chamberPressure = 7.0e6)
    for key, value in extra.items():
        setattr(nozzle, key, value)

    return nozzle

#--------------------------------------------------------------------------------------------------------------------------#
# -- The descriptions -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.mark.parametrize('quantity', ['mach', 'pressure', 'temperature'])
def testAFieldRunsFromTheInjectorFaceToTheExitPlaneAndNoFurther(quantity):
    nozzle = _syntheticNozzle()
    data = stitchedFieldFigure(nozzle, quantity)
    throatX = nozzle.xNozzleWall[int(np.argmin(nozzle.rNozzleWall))]

    # The characteristic mesh is clipped to the wall that is built
    assert data.meshX.size and data.meshX.min() >= throatX and data.meshX.max() <= nozzle.xNozzleWall[-1]
    # Upstream is the one-dimensional answer, from the injector face to the throat
    assert data.upstreamX.min() == pytest.approx(nozzle.xNozzleWall[0])
    assert data.upstreamX.max() == pytest.approx(throatX)
    assert data.logarithmic == (quantity == 'pressure')

def testTheChamberIsSubsonicAndEveryCrossSectionHoldsOneValue():
    data = stitchedFieldFigure(_syntheticNozzle(), 'mach')
    assert data.upstreamValues.max() <= 1.0 + 1e-9
    assert np.allclose(data.upstreamValues, data.upstreamValues[:, :1])

def testNoMeshMeansNoField():
    assert stitchedFieldFigure(_syntheticNozzle(allXPoints = None), 'mach') is None

def _plume(solved = True):
    x = np.linspace(0.60, 0.90, 12)[:, None] * np.ones((1, 6))
    r = np.linspace(0.0, 1.0, 6)[None, :] * np.linspace(0.31, 0.40, 12)[:, None]
    return types.SimpleNamespace(
        solved = solved, nodeX = x.ravel(), nodeR = r.ravel(), nodeMach = np.full(x.size, 4.6),
        boundaryX = x[:, -1], boundaryR = r[:, -1], lipX = 0.60, lipRadius = 0.31, solvedTo = 0.90,
        lipPressureRatio = 1.4, massDriftWorst = -0.3, trustworthy = True)

def testThePlumeSceneIsOneFieldFromTheChamberThroughTheMarch():
    nozzle = _syntheticNozzle(nozzlePlumeField = _plume(), plumeAmbientPressure = 20000.0, nozzlePlumeStructure = None)
    scene = plumeSceneFigure(nozzle)
    assert scene.nodeX.min() == pytest.approx(nozzle.xNozzleWall[0])
    assert scene.nodeX.max() == pytest.approx(0.90)
    # The interior stops at the lip, where the march takes over
    interior = (scene.nodeX > 0.0) & (scene.nodeX < 0.60)
    assert interior.any()
    # The scale spans the supersonic flow; the subsonic chamber sits below it
    assert scene.machRange[0] >= 1.0 and scene.machRange[1] == pytest.approx(4.6)
    assert scene.reach == pytest.approx((0.90 - 0.60) / 0.31)

def testAPlumeThatDidNotMarchHasNoScene():
    nozzle = _syntheticNozzle(nozzlePlumeField = _plume(solved = False))
    assert plumeSceneFigure(nozzle) is None

#--------------------------------------------------------------------------------------------------------------------------#
# -- The views -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _cooledNozzle():

    '''Everything a jacketed, film-cooled run with a radiative extension keeps for the views.'''

    nozzle = _syntheticNozzle()
    stations = 30
    x = np.linspace(-0.28, 0.05, stations)
    r = np.interp(x, nozzle.xNozzleWall, nozzle.rNozzleWall)
    ramp = np.linspace(0.0, 1.0, stations)
    nozzle.channelThermalResults = {
        'xHotWall3D': x, 'rHotWall3D': r, 'temperature': 40.0 + 120.0 * ramp[::-1],
        'pressure': 12.0e6 - 1e5 * ramp[::-1], 'wallTemperature': 500.0 + 250.0 * np.sin(np.pi * ramp),
        'velocity': 100.0 + 50.0 * ramp, 'machNumber': 0.1 + 0.1 * ramp, 'heatTransfer': 1000.0 + 1500.0 * ramp,
        'heatFlux': 1e7 + 6e7 * ramp, 'density': 70.0 - 50.0 * ramp, 'viscosity': 1e-5 * (1.0 + ramp),
        'specificHeat': 1.4e4 + 1e3 * ramp, 'nusseltNumber': 2000.0 + 3000.0 * ramp,
        'exhaustConvectiveHeatTransferCoef': 1e4 + 2e4 * ramp, 'coolantConvectiveHeatTransferCoef': 3e4 + 9e4 * ramp,
        'reynoldsNumber': 1e6 + 1e6 * ramp, 'radiativeHeatTransfer': 50.0 * ramp,
        'drivingTemperature': 3000.0 + 300.0 * ramp}
    nozzle.maxWallTemperature, nozzle.nChannel, nozzle.coolant = 800.0, 60, 'Hydrogen'

    nozzle.xRegenNozzle, nozzle.rRegenNozzle = x, r
    effectiveness = np.exp(-ramp * 8.0)
    nozzle.regenSectionFilmEffectiveness = effectiveness
    nozzle.regenSectionNearWallRecoveryTemperature = np.full(stations, 3400.0)
    nozzle.regenSectionFilmDrivingTemperature = 3400.0 - effectiveness * 3100.0
    nozzle.regenSectionFilmEntrainmentFlowRatio = 20.0 * ramp
    nozzle.regenSectionFilmWallMixtureRatio = 4.0 * ramp
    nozzle.filmCooling, nozzle.filmCoolingModel, nozzle.filmCoolant = 'on', 'sp8124Entrainment', 'Hydrogen'
    nozzle.filmMassFlow, nozzle.filmSlotHeight, nozzle.filmSurvivalLength = 0.3, 0.0015, 0.05

    extensionX = np.linspace(0.05, 0.60, 25)
    nozzle.extensionWallTemperature = 2700.0 - 800.0 * np.linspace(0.0, 1.0, 25)
    nozzle.radiativeExtensionSolution = types.SimpleNamespace(
        axialPosition = extensionX, radius = np.interp(extensionX, nozzle.xNozzleWall, nozzle.rNozzleWall),
        extensionWallTemperature = nozzle.extensionWallTemperature,
        extensionEquilibriumTemperature = nozzle.extensionWallTemperature + 3.0,
        extensionConvectiveFlux = np.linspace(2e6, 5e5, 25), extensionGasRadiativeFlux = np.zeros(25),
        extensionEmittedFlux = np.linspace(2e6, 5e5, 25), extensionConductionFlux = np.zeros(25),
        extensionPeakWallTemperature = 2700.0, extensionTemperatureLimit = 1673.15,
        extensionTemperatureMargin = 1673.15 - 2700.0, extensionEnergyBalanceResidual = 1e-12)
    nozzle.extensionMaterial, nozzle.extensionAtmosphere = 'C103', 'inert'

    return nozzle

@pytest.mark.parametrize('name', ['drawWallMap', 'drawJacketTemperatures', 'drawCoolantFlow', 'drawCoolantProperties',
                                  'drawHeatFlux', 'drawFilm', 'drawExtension'])
def testEveryCoolingViewDrawsInBothModes(tkRoot, name):
    from novaGui import theme, thermalPlots
    from novaGui.plotting import MplPane

    theme.applyTheme(tkRoot, 'dark')
    pane = MplPane(tkRoot)
    nozzle = _cooledNozzle()
    for mode in ('dark', 'light'):
        theme.setMode(tkRoot, mode, matplotlib = False)
        pane.render(getattr(thermalPlots, name), nozzle)
        pane.figure.canvas.draw()
        assert len(pane.figure.get_axes()) >= 2

@pytest.mark.parametrize('name', ['drawWallMap', 'drawFilm', 'drawExtension'])
def testACoolingViewWithNothingToDrawSaysSo(tkRoot, name):
    from novaGui import theme, thermalPlots
    from novaGui.plotting import MplPane

    theme.applyTheme(tkRoot, 'dark')
    pane = MplPane(tkRoot)
    pane.render(getattr(thermalPlots, name), _syntheticNozzle())
    assert pane.figure.get_axes()[0].texts

@pytest.mark.parametrize('quantity', ['mach', 'pressure', 'temperature'])
def testTheFieldViewDraws(tkRoot, quantity):
    from novaGui import theme
    from novaGui.plotting import MplPane, drawField

    theme.applyTheme(tkRoot, 'dark')
    pane = MplPane(tkRoot)
    pane.render(drawField, _syntheticNozzle(), quantity)
    pane.figure.canvas.draw()
    assert pane.figure.get_axes()
