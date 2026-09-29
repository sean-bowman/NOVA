# -- Where the station marcher loses mass -- #

'''

The shipped nozzle and its plume with the mass continuity error contoured instead of Mach number.

`massDrift` is one number per station: the station's axial mass flux against the exit plane's. That
locates the error in x and says nothing about where in the jet it comes from. The local quantity
behind it is the residual of the continuity equation,

    d(rho u r)/dx + d(rho v r)/dr

which is zero for an exact axisymmetric solution. Integrated over the region between two stations it
returns the change in station mass flux, so the residual field is the density of the drift and
contouring it says which part of the jet is responsible. The integral is checked station by station
against the reported drift before anything is drawn, because a decomposition that does not sum to
the known answer is not a decomposition.

The residual carries the radius as a factor, in the conservative form that integrates to the flux. A
given velocity error therefore counts for less near the center line than out at the boundary, which
is true of mass flow rather than an artifact: a streamtube at small radius carries little mass. The
center-line Mach number is drawn underneath so the axis is not read as quiet when it is only narrow.

Only the plume is shaded. Upstream of the lip the field comes from the contour solve and the
one-dimensional chamber, neither of which the station marcher touches, so there is no residual to
draw there and the engine is outlined for position.

Run it from the NOVA root, after `python featureShowcase/runBaseCase.py` has written the pickle:

    python experimental/stationMarchErrorField.py

Author: Sean Bowman

'''

import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon
from scipy.signal import find_peaks, peak_prominences

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'src'))
sys.path.insert(0, here)

from NOVA.plume import PlumeFlow, plumeCharacteristicSeed, plumeExitLine, solvePlumeStructure
from stationMarch import solveStationMarch, stationFromLine, stationMassFlux
from stationMarchNozzleField import copper, green, ink, muted, panel, warn

PRESSURERATIO = 1.5        # [-], lip static pressure over ambient
REACH = 36.0               # [-], axial distance marched, in lip radii
RADIALPOINTS = 161         # [-], points across each station
CLIP = 98.0                # [%], percentile of residual magnitude the color scale is cut at
AXISTOLERANCE = 0.01       # [-], center-line Mach departure that counts as the fan arriving
def marchTheJet(nozzle):

    '''The march, and the states the residual is built from.'''

    seed = plumeCharacteristicSeed(nozzle.plumeContour())
    flow = PlumeFlow(seed['gamma'], seed['gasConstant'], seed['stagnationTemperature'],
                     seed['stagnationPressure'])
    line = plumeExitLine(flow, seed, numPoints = 400)
    station = stationFromLine(line, RADIALPOINTS)
    lipPressure = flow.staticPressure(float(station.mach[-1]))
    ambient = lipPressure / PRESSURERATIO
    result = solveStationMarch(flow, station, ambient, maxLength = REACH, maxStations = 200000)

    return seed, flow, station, lipPressure, ambient, result

def continuityResidual(flow, result):

    '''

    The local continuity residual on the march's own grid, with its integral as the check.

    The grid is rectilinear in (x, eta) with eta = r/R(x). Stations are planes normal to the axis,
    so x depends only on the station index, and points sit at fixed fractions of the local jet
    radius, so eta depends only on the point index. That makes the chain rule exact rather than
    interpolated:

        d/dx at fixed r = d/dx at fixed eta - (eta R'/R) d/d(eta)
        d/dr            = (1/R) d/d(eta)

    Returns the residual normalized by the lip mass flux density, which makes it dimensionless,
    with the running integral of the residual and the drift the march reported, for comparison.

    '''

    stations = result['stations']
    x = np.array([one.x for one in stations])
    eta = stations[0].radius / stations[0].boundaryRadius
    radius = np.array([one.boundaryRadius for one in stations])
    r = radius[:, None] * eta[None, :]
    mach = np.array([one.mach for one in stations])
    angle = np.array([one.flowAngle for one in stations])

    density = np.vectorize(flow.density)(mach)
    speed = np.vectorize(flow.velocity)(mach)
    axialFlux = density * speed * np.cos(angle) * r      # rho u r
    radialFlux = density * speed * np.sin(angle) * r     # rho v r

    slope = np.gradient(radius, x)
    axialAtEta = np.gradient(axialFlux, x, axis = 0)
    axialInEta = np.gradient(axialFlux, eta, axis = 1)
    radialInEta = np.gradient(radialFlux, eta, axis = 1)

    stretch = eta[None, :] * slope[:, None] / radius[:, None]
    residual = (axialAtEta - stretch * axialInEta) + radialInEta / radius[:, None]

    # The running integral is the validation. By the divergence theorem, 2 pi times the residual
    # integrated over the meridional region up to a station equals that station's change in mass
    # flux, because the outer boundary is a streamline and carries no flux through it. At fixed x,
    # dr = R d(eta).
    perStation = np.trapezoid(residual * radius[:, None], eta, axis = 1)
    reference = stationMassFlux(flow, stations[0])
    running = np.concatenate([[0.0], np.cumsum(0.5*(perStation[1:] + perStation[:-1])*np.diff(x))])
    predicted = 100.0 * 2.0 * np.pi * running / reference
    reported = np.array(result['massDrift'])

    # Checked at every station rather than at the end alone: the reported drift passes back through
    # zero near six lip radii, so an endpoint comparison would agree for the wrong reason. The gap
    # is quoted against the size of the excursion the field is meant to explain.
    gap = float(np.abs(predicted - reported).max())
    excursion = float(np.abs(reported).max())

    lipDensity = flow.density(float(stations[0].mach[-1]))
    lipSpeed = flow.velocity(float(stations[0].mach[-1]))

    return {'x': x, 'r': r, 'residual': residual / (lipDensity * lipSpeed),
            'gap': gap, 'excursion': excursion, 'axisMach': mach[:, 0], 'drift': reported}

def axisFoci(axisMach, prominence = 0.08):

    '''

    Where the wave fronts converge on the center line.

    A focus shows as a minimum in the center-line Mach number, but so does every ripple the trace
    carries, and the foci weaken downstream as the cells decay, so depth alone separates them
    badly: on the shipped nozzle the fourth focus is shallower than a ripple threshold that admits
    the first three. Prominence separates them by an order instead, 0.43 to 2.45 for the foci
    against 0.04 to 0.28 for the ripples, and `prominence` is the cut as a fraction of the exit
    Mach number.

    '''

    minima, _ = find_peaks(-np.asarray(axisMach, dtype = float))
    if minima.size == 0:
        return []
    strength = peak_prominences(-np.asarray(axisMach, dtype = float), minima)[0]

    return [int(index) for index, value in zip(minima, strength)
            if value > prominence*axisMach[0]]

def build():

    with open(os.path.join(root, 'featureShowcase', 'showcaseBase.pkl'), 'rb') as handle:
        nozzle = pickle.load(handle)

    seed, flow, station, lipPressure, ambient, result = marchTheJet(nozzle)
    field = continuityResidual(flow, result)
    structure = solvePlumeStructure(nozzle.plumeContour(), ambient)
    lipRadius, lipX = structure.lipRadius, structure.lipX

    relative = 100.0 * field['gap'] / field['excursion']
    print(f'  residual integral tracks the reported drift to {field["gap"]:.4f} points at every '
          f'station, {relative:.1f} per cent of the {field["excursion"]:.3f} excursion')

    # Everything is drawn in lip radii from the exit plane, so the field and the error curve share
    # one axis and a feature in the field sits directly above its cost in mass.
    def inRadii(values):
        return (np.asarray(values, dtype = float) - lipX) / lipRadius

    wallX = inRadii(nozzle.xNozzleWall)
    wallR = np.asarray(nozzle.rNozzleWall, dtype = float) / lipRadius
    boundary = np.array(result['boundary'])
    boundaryX, boundaryR = inRadii(boundary[:, 0]), boundary[:, 1] / lipRadius
    reach = inRadii(field['x'])
    gridX = np.repeat(reach[:, None], field['r'].shape[1], axis = 1)
    gridR = field['r'] / lipRadius

    # The fan reaches the axis where the center-line state first leaves its exit value, which is
    # earlier than the first focus: the waves arrive before they converge.
    departure = np.abs(field['axisMach'] - field['axisMach'][0]) > AXISTOLERANCE
    crossing = float(reach[int(np.argmax(departure))])
    foci = axisFoci(field['axisMach'])
    # The drift changes sign, so the worst is the largest magnitude rather than the deepest dip:
    # the first leg loses mass and the legs behind it more than give it back.
    worst = int(np.argmax(np.abs(field['drift'])))
    trough = int(np.argmin(field['drift']))
    steps = [float(field['drift'][b] - field['drift'][a]) for a, b in zip(foci, foci[1:])]

    figure, (axes, lower) = plt.subplots(2, 1, figsize = (26.0, 6.4), sharex = True,
                                         gridspec_kw = {'height_ratios': [2.2, 1.0]})

    # The scale is cut at a percentile rather than at the extremes: a handful of nodes on the lip
    # fan and at the axis crossing run an order of magnitude past the rest and would flatten
    # everything else to one color.
    span = float(np.percentile(np.abs(field['residual']), CLIP))
    levels = np.linspace(-span, span, 141)
    patch = None
    for sign in (1.0, -1.0):
        patch = axes.contourf(gridX, sign * gridR, np.clip(field['residual'], -span, span),
                              levels = levels, cmap = 'RdBu_r', extend = 'both')

    # The engine is filled flat rather than contoured: nothing upstream of the lip is solved by this
    # scheme, so it carries no residual and the color scale belongs entirely to the plume.
    axes.add_patch(Polygon(np.vstack([np.column_stack([wallX, wallR]),
                                      np.column_stack([wallX[::-1], -wallR[::-1]])]),
                           closed = True, facecolor = panel, edgecolor = 'none', zorder = 2))
    for sign in (1.0, -1.0):
        axes.plot(wallX, sign * wallR, color = copper, lw = 2.0, zorder = 3,
                  label = 'nozzle wall' if sign > 0 else None)
        axes.plot(boundaryX, sign * boundaryR, color = ink, lw = 1.3, zorder = 3,
                  label = 'jet boundary' if sign > 0 else None)

    for host in (axes, lower):
        host.axvline(crossing, color = green, lw = 1.2, ls = '--', zorder = 3,
                     label = f'lip fan reaches the axis, {crossing:.1f}' if host is axes else None)
        for order, index in enumerate(foci):
            host.axvline(reach[index], color = ink, lw = 0.9, ls = ':', alpha = 0.7, zorder = 3,
                         label = ('axis foci' if order == 0 and host is axes else None))

    axes.set_xlim(wallX.min(), reach[-1])
    axes.set_ylim(-1.35, 1.35)
    axes.set_aspect('equal', adjustable = 'box')
    axes.set_ylabel('Radius [lip radii]')
    axes.set_title('Where the station marcher loses mass', fontsize = 13, pad = 26)
    axes.text(0.5, 1.02,
              f'continuity residual, lip Mach {float(station.mach[-1]):.2f} at '
              f'{lipPressure/1000.0:.1f} kPa into {ambient/1000.0:.1f} kPa, lip ratio '
              f'{PRESSURERATIO:.1f}   |   {len(result["stations"])} stations to {reach[-1]:.1f} '
              f'lip radii   |   worst error {field["drift"][worst]:+.2f} %',
              transform = axes.transAxes, ha = 'center', va = 'bottom', fontsize = 9.5,
              color = muted)
    axes.legend(loc = 'lower left', fontsize = 8, labelcolor = ink, ncol = 4,
                bbox_to_anchor = (0.0, 1.06))

    # Equal aspect shrinks the axes box inside its gridspec cell, and the colorbar is sized from
    # the cell rather than the box, so it is shrunk by hand to match the panel.
    bar = figure.colorbar(patch, ax = axes, orientation = 'vertical', pad = 0.010,
                          fraction = 0.016, shrink = 0.42, extend = 'both')
    bar.set_label('continuity residual / lip mass flux density [-]', fontsize = 8.5)
    bar.ax.tick_params(labelsize = 8)

    lower.plot(reach, field['drift'], color = copper, lw = 1.8, label = 'mass continuity error')
    lower.axhline(0.0, color = muted, lw = 0.8)
    for index, offset in ((trough, (-14, 10)), (worst, (-14, -16))):
        lower.plot(reach[index], field['drift'][index], 'o', color = warn, ms = 5)
        lower.annotate(f'{field["drift"][index]:+.2f} % at {reach[index]:.2f}',
                       (reach[index], field['drift'][index]), textcoords = 'offset points',
                       xytext = offset, ha = 'right', fontsize = 8.5, color = warn)
    lower.set_xlabel('Distance downstream of the exit plane [lip radii]')
    lower.set_ylabel('Error [% of exit mass flow]')

    twin = lower.twinx()
    twin.plot(reach, field['axisMach'], color = green, lw = 1.4, ls = '-.',
              label = 'center-line Mach')
    twin.set_ylabel('Center-line Mach [-]', color = green)
    twin.tick_params(axis = 'y', colors = green, labelsize = 8)

    # One legend for both y axes, so the two traces are named in the same place.
    handles, labels = lower.get_legend_handles_labels()
    extra = twin.get_legend_handles_labels()
    lower.legend(handles + extra[0], labels + extra[1], loc = 'lower right', fontsize = 8,
                 labelcolor = ink, ncol = 2)

    figure.text(0.012, -0.03,
                'The residual is the local form of the quantity the drift integrates, '
                'd(rho u r)/dx + d(rho v r)/dr, zero for an exact solution. Integrated from the '
                f'exit plane it tracks the reported drift to {field["gap"]:.3f} percentage points '
                f'at every station, {relative:.1f} per cent of the {field["excursion"]:.2f} '
                'excursion, so the contoured field accounts for the loss rather than standing in '
                'for it.\n'
                'Red and blue are a gain and a loss of axial mass flux per unit meridional area. '
                f'The scale is cut at the {CLIP:.0f}th percentile of magnitude because a few nodes '
                'on the lip fan and at the axis crossings run an order past the rest.\n'
                'The radius is a factor in the conservative form, so a given velocity error counts '
                'for less near the center line, which is true of mass flow.',
                fontsize = 8.5, color = muted, va = 'top')
    figure.text(0.012, -0.15,
                'This is a diagnostic, not a validated plume. The scheme carries one stagnation '
                'pressure for the whole field, so it describes no shock. The jet is overexpanded '
                'at this ratio, so `plumeStructure` places no Mach disk either: Ashkenas and '
                'Sherman is an underexpanded result and does not apply. A Mach reflection may '
                'still stand in the lip shock train, and locating it needs shock capturing.\n'
                'The error is made on the outward leg of each cell, from the axis focus out to the '
                'boundary pinch, and part of it is given back on the leg back in. The '
                f'{len(foci)} foci sit at '
                + ', '.join(f'{reach[i]:.1f}' for i in foci)
                + f' lip radii, a cell every '
                f'{np.mean(np.diff([reach[i] for i in foci])):.1f}.\n'
                'The net across each is '
                + ', '.join(f'{value:+.1f}' for value in steps)
                + ' percentage points. The near-axis treatment at a converging wave is the open '
                'defect, and this is its bill.',
                fontsize = 8.5, color = warn, va = 'top')

    path = os.path.join(here, 'stationMarchErrorField.png')
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print('  wrote stationMarchErrorField.png')
    print(f'  residual scale +/-{span:.3e}, worst error {field["drift"][worst]:+.2f} per cent at '
          f'{reach[worst]:.2f} lip radii, fan on the axis at {crossing:.2f}')
    print('  axis foci at ' + ', '.join(f'{reach[i]:.2f}' for i in foci)
          + ' lip radii, drift steps ' + ', '.join(f'{v:+.2f}' for v in steps))

    return path

if __name__ == '__main__':
    build()
