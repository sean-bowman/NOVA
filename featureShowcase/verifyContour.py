'''
Verification of the truncated ideal contour of the worked case against references outside NOVA.

This is the quick check: it reads the pickled base case and re-solves nothing. The sweeps across
area ratio, percent bell and mesh resolution are in buildContourValidation.py.

Four properties are checked, and they are fixed by definition or by published data rather than by
this implementation:

    the delivered area ratio is the one that was asked for
    the delivered length is the requested fraction of the 15 degree cone OF THAT AREA RATIO, which
    is how NASA SP-8120 defines percent bell
    the near-wall pressure and Mach number satisfy the isentropic relation they were both built
    from, everywhere along the wall
    the exit plane is reported as it is rather than as its wall value, because a truncated contour
    has a strongly non-uniform exit and the wall is its extreme point

Run after runBaseCase.py:

    python featureShowcase/verifyContour.py
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
from NOVA.gasDynamics import (areaMachRelation, machFromAreaRatio, staticPressureRatio,
                         conicalLength, divergenceLossFactor)
from NOVA.contour import raoWallAngles, raoParabolicContour, wallAnglesFromContour
from NOVA.contourKernel import ThroatGeometry

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

def verify(nozzle):
    gamma = nozzle.chamberGamma
    solution = nozzle.nozzleContourSolution
    wallX = np.asarray(nozzle.xNozzleWall)
    wallR = np.asarray(nozzle.rNozzleWall)
    throatIndex = int(np.argmin(wallR))
    throatRadius = wallR[throatIndex]
    throatX = wallX[throatIndex]

    diverging = wallX >= throatX
    x = wallX[diverging]
    r = wallR[diverging]
    localRatio = (r / throatRadius) ** 2

    requested = float(nozzle.expansionRatio)
    delivered = float(solution.deliveredAreaRatio)
    deliveredFraction = float(solution.deliveredLengthFraction)
    coneLength = conicalLength(delivered, throatRadius)

    figure, axes = plt.subplots(2, 2, figsize = (14.0, 8.6))

    # -- Contour against its length reference and a Rao bell of the same design point -- #
    upper = axes[0][0]
    upper.plot((x - throatX) * 1e3, r * 1e3, color = copper, lw = 2.4,
               label = 'NOVA truncated ideal contour')
    upper.plot([0.0, coneLength * 1e3], [throatRadius * 1e3, r[-1] * 1e3], color = blue,
               lw = 1.6, ls = '--',
               label = f'15 deg cone to the same area ratio ({coneLength * 1e3:.0f} mm)')
    throat = ThroatGeometry(gamma)
    raoX, raoR = raoParabolicContour(throat, delivered, deliveredFraction, throatRadius,
                                     numPoints = 400)
    upper.plot(raoX * 1e3, raoR * 1e3, color = green, lw = 1.8, ls = '-.',
               label = 'Rao parabolic bell, same area ratio and length')
    upper.set_xlabel('Distance from the throat [mm]')
    upper.set_ylabel('Radius [mm]')
    upper.set_title(f'Contour against its references    delivered {deliveredFraction:.4f} '
                    f'of the cone')
    upper.grid(True, alpha = 0.25)
    upper.legend(loc = 'lower right', fontsize = 8, labelcolor = ink)

    # -- Area ratio, requested against delivered -- #
    ratioPanel = axes[0][1]
    ratioPanel.plot((x - throatX) * 1e3, localRatio, color = copper, lw = 2.0,
                    label = 'local area ratio along the wall')
    ratioPanel.axhline(requested, color = green, lw = 1.6, ls = '--',
                       label = f'requested {requested:.2f}')
    ratioPanel.axhline(delivered, color = warn, lw = 1.4, ls = ':',
                       label = f'delivered {delivered:.4f}')
    ratioPanel.set_xlabel('Distance from the throat [mm]')
    ratioPanel.set_ylabel('A / A*')
    ratioPanel.set_title(f'Area ratio: delivered is {100*(delivered/requested - 1):+.4f} % '
                         f'from requested')
    ratioPanel.grid(True, alpha = 0.25)
    ratioPanel.legend(loc = 'lower right', fontsize = 8, labelcolor = ink)

    # -- Near-wall state, checked against the relation it was built from -- #
    machPanel = axes[1][0]
    wallMach = np.asarray(nozzle.nozzleNearWallMachNumber)[diverging]
    wallPressure = np.asarray(nozzle.nozzleNearWallPressure)[diverging]
    impliedPressure = nozzle.chamberPressure * np.array(
        [staticPressureRatio(mach, gamma) for mach in wallMach])
    oneDMach = np.array([machFromAreaRatio(ratio, gamma) for ratio in localRatio])

    machPanel.plot(localRatio, oneDMach, color = blue, lw = 2.0,
                   label = 'area-Mach relation at the local area')
    machPanel.plot(localRatio, wallMach, color = copper, lw = 2.0,
                   label = 'near-wall Mach number')
    consistency = np.max(np.abs(wallPressure / impliedPressure - 1.0))
    machPanel.set_xlabel('Local area ratio  A / A*')
    machPanel.set_ylabel('Mach number')
    machPanel.set_title(f'Near-wall Mach against the one-dimensional relation\n'
                        f'pressure and Mach agree to {100*consistency:.3f} % of each other')
    machPanel.grid(True, alpha = 0.25)
    machPanel.legend(loc = 'lower right', fontsize = 8, labelcolor = ink)

    # -- The exit plane -- #
    exitPanel = axes[1][1]
    exitRadius = np.asarray(solution.exitPlaneRadius)
    exitPressure = np.asarray(solution.exitPlanePressure)
    exitPanel.plot(exitRadius / exitRadius[0], exitPressure * 1e-3, color = copper, lw = 2.2,
                   label = 'exit plane static pressure')
    exitPanel.axhline(solution.exitAreaAveragedPressure * 1e-3, color = green, lw = 1.5, ls = '--',
                      label = f'area averaged {solution.exitAreaAveragedPressure*1e-3:.1f} kPa')
    exitPanel.axhline(solution.exitMassAveragedPressure * 1e-3, color = blue, lw = 1.5, ls = '-.',
                      label = f'mass averaged {solution.exitMassAveragedPressure*1e-3:.1f} kPa')
    oneDimensional = nozzle.chamberPressure * staticPressureRatio(
        machFromAreaRatio(delivered, gamma), gamma)
    exitPanel.axhline(oneDimensional * 1e-3, color = muted, lw = 1.4, ls = ':',
                      label = f'one-dimensional at that area {oneDimensional*1e-3:.1f} kPa')
    exitPanel.plot([1.0], [exitPressure[0] * 1e-3], 'o', color = warn, ms = 9,
                   label = f'at the wall {exitPressure[0]*1e-3:.1f} kPa')
    exitPanel.set_xlabel('Radius as a fraction of the exit radius')
    exitPanel.set_ylabel('Static pressure [kPa]')
    exitPanel.set_title(f'The exit plane is not uniform: wall is '
                        f'{exitPressure[0]/exitPressure[-1]:.1f} times the axis')
    exitPanel.grid(True, alpha = 0.25)
    exitPanel.legend(loc = 'upper left', fontsize = 8, labelcolor = ink)

    figure.suptitle('Truncated ideal contour verification', fontsize = 13, fontweight = 'bold')
    figure.tight_layout(rect = [0, 0.085, 1, 0.965])

    chartInflection, chartExit, extrapolated = raoWallAngles(delivered, deliveredFraction)
    figure.text(0.012, 0.072,
                f'The contour is asked for an area ratio of {requested:.1f} and delivers '
                f'{delivered:.4f}, and for {nozzle.lengthFraction:.2f} of the conical length and '
                f'delivers {deliveredFraction:.4f}. The wall is cut at the requested area ratio '
                f'and the design Mach number is\nsolved for the length, so both are outcomes of '
                f'the same solve rather than one being traded against the other. Wall angles come '
                f'out at {np.degrees(solution.inflectionWallAngle):.2f} deg at the inflection and '
                f'{np.degrees(solution.exitWallAngle):.2f} deg at the exit, against '
                f'{np.degrees(chartInflection):.1f} and {np.degrees(chartExit):.1f} deg from the '
                f'Rao chart\nfor a thrust-optimized parabola of the same design point'
                f'{" (read from the extrapolated region of that chart)" if extrapolated else ""}. '
                f'The exit pressure is a result, not a target: the plane runs from '
                f'{exitPressure[0]*1e-3:.1f} kPa at the wall to {exitPressure[-1]*1e-3:.1f} kPa on '
                f'the axis.',
                fontsize = 8.5, color = ink, va = 'top')

    path = os.path.join(here, 'contourVerification.png')
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)

    print(f'requested area ratio        {requested:10.4f}')
    print(f'delivered area ratio        {delivered:10.4f}   ({100*(delivered/requested-1):+.4f} %)')
    print(f'requested length fraction   {nozzle.lengthFraction:10.4f}')
    print(f'delivered length fraction   {deliveredFraction:10.4f}   '
          f'({100*(deliveredFraction/nozzle.lengthFraction-1):+.4f} %)  '
          f'of a {coneLength*1e3:.0f} mm cone')
    print(f'inflection wall angle       {np.degrees(solution.inflectionWallAngle):10.3f} deg   '
          f'Rao chart {np.degrees(chartInflection):.2f} deg  '
          f'({np.degrees(solution.inflectionWallAngle - chartInflection):+.2f} deg)')
    print(f'exit wall angle             {np.degrees(solution.exitWallAngle):10.3f} deg   '
          f'Rao chart {np.degrees(chartExit):.2f} deg  '
          f'({np.degrees(solution.exitWallAngle - chartExit):+.2f} deg)')
    print(f'near-wall P against P(M)    {100*consistency:10.4f} %  worst departure along the wall')
    print()
    print(f'exit plane, wall            {exitPressure[0]:10.1f} Pa')
    print(f'exit plane, mass averaged   {solution.exitMassAveragedPressure:10.1f} Pa')
    print(f'exit plane, area averaged   {solution.exitAreaAveragedPressure:10.1f} Pa')
    print(f'exit plane, axis            {exitPressure[-1]:10.1f} Pa')
    print(f'one-dimensional at that eps {oneDimensional:10.1f} Pa')
    print(f'CEA exit pressure at eps    {nozzle.targetExitPressure:10.1f} Pa   '
          f'({100*(nozzle.targetExitPressure/oneDimensional-1):+.1f} % from the perfect-gas value)')
    print()
    print(f'thrust coefficient          {solution.thrustCoef:10.5f}   '
          f'(velocity {solution.velocityTermThrustCoef:.5f}, '
          f'pressure {solution.pressureTermThrustCoef:+.5f})')
    idealMach = machFromAreaRatio(delivered, gamma)
    idealExitPressure = nozzle.chamberPressure * staticPressureRatio(idealMach, gamma)
    idealVelocity = np.sqrt((2 * gamma**2 / (gamma - 1))
                            * ((2 / (gamma + 1))**((gamma + 1)/(gamma - 1)))
                            * (1 - (idealExitPressure / nozzle.chamberPressure)**((gamma - 1)/gamma)))
    idealTotal = idealVelocity + (idealExitPressure - nozzle.targetExitPressure) / nozzle.chamberPressure * delivered
    divergence = divergenceLossFactor(float(solution.exitWallAngle))
    print(f'one-dimensional ideal Cf    {idealTotal:10.5f}   '
          f'({100*(solution.thrustCoef/idealTotal-1):+.3f} %)')
    print(f'divergence factor at exit   {divergence:10.5f}   '
          f'which alone would cost {100*(divergence-1):+.3f} % on the velocity term')
    print('wrote contourVerification.png')

def main():
    with open(os.path.join(here, 'showcaseBase.pkl'), 'rb') as handle:
        verify(pickle.load(handle))

if __name__ == '__main__':
    main()
