# -- The anatomy of an underexpanded plume -- #

'''

A labelled reference for the shock structure of an underexpanded jet, beside what NOVA's solver
actually produces.

The upper panel is a schematic. It is drawn by hand from the canonical structure and is not a solve
of anything: the shapes are illustrative and only the topology is meant to be right. Its job is to
name the features and show how they connect, because the names only make sense once the reflection
argument is laid out.

The lower panel is the station march on the shipped nozzle, with callouts placing each feature in
the computed field. The solver is isentropic, so none of the shocks exist in it. What it shows
instead is the smooth wave pattern that precedes them: the compressions are there and converging,
they simply never steepen, and the axis crossing is a regular reflection where a strong enough jet
would put a Mach disk.

The physics in one line: a free jet boundary reflects an expansion as a compression, those
compressions converge on the axis, and when the turn they demand at the axis exceeds what an
attached oblique shock can supply, the regular reflection is replaced by a three-shock intersection
whose middle leg is the Mach disk.

Run it from the NOVA root, after `python featureShowcase/runBaseCase.py` has written the pickle:

    python experimental/plumeShockAnatomy.py

Author: Sean Bowman

'''

import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'src'))
sys.path.insert(0, here)

from NOVA.plume import (PlumeFlow, plumeCharacteristicSeed, plumeExitLine, solvePlumeStructure,
                        machDiskLocation, machDiskOnsetPressureRatio)
from stationMarch import solveStationMarch, stationFromLine
from stationMarchErrorField import axisFoci
from stationMarchNozzleField import copper, green, ink, muted, warn

PRESSURERATIO = 1.5        # [-], lip static pressure over ambient, for the computed panel
DESIGNAMBIENT = 5000.0     # [Pa], the ambient the shipped contour is sized at
REACH = 12.0               # [-], axial distance marched, in lip radii
RADIALPOINTS = 161         # [-], points across each station

CELL = 5.0                 # [-], schematic cell length
DISKX = CELL               # [-], schematic Mach disk station
TRIPLER = 0.80             # [-], schematic triple-point radius
slip = '#9AD7E8'           # slip line and shear layer
def schematicBoundary(x):

    '''

    An illustrative jet boundary.

    A decaying cosine about a slowly opening mean, which is the shape a free boundary takes: it
    bulges where the flow has overexpanded against ambient and necks where it has been compressed
    back. The numbers are chosen to read clearly, not computed.

    '''

    return 1.45 - 0.45*np.exp(-0.07*x)*np.cos(2.0*np.pi*x/CELL)

def schematicBarrel(x):

    '''The intercepting shock, from near the lip in to the triple point, always inside the jet.'''

    span = np.clip((x - 0.4)/(DISKX - 0.4), 0.0, 1.0)

    return 1.0 + 0.32*np.sin(np.pi*span) - (1.0 - TRIPLER)*span

def drawSchematic(axes):

    '''The canonical structure, named.'''

    x = np.linspace(0.0, 10.6, 700)
    boundary = schematicBoundary(x)

    for sign in (1.0, -1.0):
        axes.fill_between(x, 0.0, sign*boundary, color = '#2A3145', zorder = 1)
        axes.plot(x, sign*boundary, color = ink, lw = 1.8, zorder = 4)

        # The fan at the lip, turning the flow outward.
        for angle in np.linspace(10.0, 44.0, 5):
            axes.plot([0.0, 1.25*np.cos(np.radians(angle))],
                      [sign*1.0, sign*(1.0 + 1.25*np.sin(np.radians(angle)))],
                      color = green, lw = 0.9, alpha = 0.9, zorder = 3)

        # Compressions running back off the boundary, each stopping on the barrel shock it feeds.
        for start in np.linspace(1.1, 3.6, 6):
            finish = start + 1.35
            axes.annotate('', xy = (finish, sign*schematicBarrel(finish)),
                          xytext = (start, sign*schematicBoundary(start)),
                          arrowprops = dict(arrowstyle = '-|>', color = copper, lw = 0.9,
                                            alpha = 0.75, shrinkA = 1, shrinkB = 0), zorder = 3)

        barrelX = np.linspace(0.4, DISKX, 300)
        axes.plot(barrelX, sign*schematicBarrel(barrelX), color = warn, lw = 2.6, zorder = 5)
        axes.plot([DISKX, DISKX + 3.0], [sign*TRIPLER, sign*(TRIPLER + 0.62)],
                  color = warn, lw = 2.0, zorder = 5)
        axes.plot([DISKX, DISKX + 4.6], [sign*TRIPLER, sign*(TRIPLER - 0.20)],
                  color = slip, lw = 1.4, ls = (0, (5, 3)), zorder = 5)
        axes.plot(DISKX, sign*TRIPLER, 'o', color = ink, ms = 6.0, zorder = 6)

    axes.plot([DISKX, DISKX], [-TRIPLER, TRIPLER], color = warn, lw = 4.5, zorder = 5)

    # The subsonic pocket behind the disk, closing as the core reaccelerates.
    pocketX = np.linspace(DISKX, DISKX + 1.9, 60)
    pocketR = TRIPLER*np.sqrt(np.clip(1.0 - ((pocketX - DISKX)/1.9)**2, 0.0, 1.0))
    axes.fill_between(pocketX, -pocketR, pocketR, color = warn, alpha = 0.22, zorder = 2)

    axes.axhline(0.0, color = muted, lw = 0.8, ls = '-.', zorder = 3)
    for sign in (1.0, -1.0):
        axes.plot([-0.85, 0.0], [sign*1.0, sign*1.0], color = copper, lw = 3.2, zorder = 6)

    # Two rows above and two below, each label in its own x slot, so no leader crosses another.
    callouts = (
        ('nozzle lip, Pe > Pa', (0.0, 1.0), (-0.35, 2.30), copper),
        ('Prandtl-Meyer fan turns the flow\noutward and accelerates it', (0.85, 1.55),
         (1.75, 2.95), green),
        ('jet boundary: constant static\npressure, so it is a free streamline', (2.5, 1.84),
         (2.9, 2.30), ink),
        ('the boundary reflects an expansion\nAS A COMPRESSION, and that sign flip\ndrives '
         'everything', (3.15, 1.62), (5.9, 2.95), copper),
        ('triple point', (DISKX, TRIPLER), (6.45, 2.30), ink),
        ('reflected shock', (DISKX + 2.0, TRIPLER + 0.41), (9.15, 2.30), warn),
        ('second cell', (8.6, schematicBoundary(8.6)), (9.7, 2.95), ink),
        ('barrel (intercepting) shock:\nthose compressions, coalesced', (2.9, -1.17),
         (1.15, -2.40), warn),
        ('MACH DISK, a near-normal shock.\nThe flow behind it is subsonic', (DISKX, -0.42),
         (4.35, -2.95), warn),
        ('subsonic pocket', (DISKX + 0.75, -0.42), (7.85, -2.40), warn),
        ('slip line: same pressure and direction,\ndifferent entropy, Mach and temperature',
         (DISKX + 3.3, -(TRIPLER - 0.14)), (8.45, -2.95), slip))

    for text, point, place, color in callouts:
        axes.annotate(text, xy = point, xytext = place, fontsize = 8.2, color = color,
                      ha = 'center', va = 'center', zorder = 7,
                      arrowprops = dict(arrowstyle = '-|>', color = color, lw = 1.0,
                                        shrinkA = 3, shrinkB = 4, alpha = 0.9))

    axes.set_facecolor('#1a1e2a')
    axes.set_xlim(-1.1, 10.8)
    axes.set_ylim(-3.3, 3.3)
    axes.set_aspect('equal', adjustable = 'box')
    axes.set_xticks([])
    axes.set_yticks([])
    for spine in axes.spines.values():
        spine.set_visible(False)
    axes.set_title('Highly underexpanded jet, canonical structure\n'
                   'schematic: the shapes are illustrative, the topology is the point',
                   fontsize = 11.5, pad = 8)

def drawComputed(axes, nozzle):

    '''The station march, with the same features located in it.'''

    seed = plumeCharacteristicSeed(nozzle.plumeContour())
    flow = PlumeFlow(seed['gamma'], seed['gasConstant'], seed['stagnationTemperature'],
                     seed['stagnationPressure'])
    station = stationFromLine(plumeExitLine(flow, seed, numPoints = 400), RADIALPOINTS)
    lipPressure = flow.staticPressure(float(station.mach[-1]))
    ambient = lipPressure/PRESSURERATIO
    result = solveStationMarch(flow, station, ambient, maxLength = REACH, maxStations = 200000)
    structure = solvePlumeStructure(nozzle.plumeContour(), ambient)
    lipRadius, lipX = structure.lipRadius, structure.lipX

    stations = result['stations']
    x = (np.array([[one.x]*one.radius.size for one in stations]) - lipX)/lipRadius
    r = np.array([one.radius for one in stations])/lipRadius
    mach = np.array([one.mach for one in stations])
    foci = axisFoci(mach[:, 0])
    boundary = np.array(result['boundary'])
    boundaryX = (boundary[:, 0] - lipX)/lipRadius
    boundaryR = boundary[:, 1]/lipRadius

    for sign in (1.0, -1.0):
        axes.contourf(x, sign*r, mach, levels = np.linspace(mach.min(), mach.max(), 140),
                      cmap = 'viridis', zorder = 1)
        axes.plot(boundaryX, sign*boundaryR, color = ink, lw = 1.4, zorder = 4)

    axes.axhline(0.0, color = muted, lw = 0.7, ls = '-.', zorder = 3)
    firstFocus = float(x[foci[0], 0])
    axes.plot(firstFocus, 0.0, 'o', color = warn, ms = 6, zorder = 6)

    # The design ambient is a different operating point, so its Mach disk is quoted rather than
    # drawn: putting a 5 kPa feature on a 16 kPa field would be two solves on one axis.
    design = solvePlumeStructure(nozzle.plumeContour(), DESIGNAMBIENT)
    designDisk = machDiskLocation(design.throatDiameter,
                                  design.nozzlePressureRatio)/design.lipRadius

    callouts = (
        ('lip fan, resolved as smooth characteristics', (0.5, 0.95), (0.9, 2.30), green),
        ('jet boundary, solved as a free streamline\nheld at ambient static pressure',
         (2.2, 1.19), (4.3, 2.85), ink),
        ('compressions converging. They are carried\nas smooth waves and never steepen',
         (3.9, 0.60), (8.6, 2.85), copper),
        ('where the barrel shock would stand,\nif the scheme could coalesce them', (4.5, 0.26),
         (1.9, -2.35), warn),
        (f'regular reflection at {firstFocus:.1f} lip radii: at this\npressure ratio the turn the '
         f'axis demands stays\nwithin what an oblique shock can supply', (firstFocus, 0.0),
         (5.6, -2.90), ink),
        (f'at the design 5 kPa a Mach disk replaces\nthis reflection, correlated '
         f'{designDisk:.1f} lip radii out', (9.6, 0.55), (9.9, 2.30), warn))

    for text, point, place, color in callouts:
        axes.annotate(text, xy = point, xytext = place, fontsize = 8.2, color = color,
                      ha = 'center', va = 'center', zorder = 7,
                      arrowprops = dict(arrowstyle = '-|>', color = color, lw = 1.0,
                                        shrinkA = 3, shrinkB = 4, alpha = 0.9))

    axes.set_xlim(-0.5, 12.5)
    axes.set_ylim(-3.3, 3.3)
    axes.set_aspect('equal', adjustable = 'box')
    axes.set_yticks([-1, 0, 1])
    axes.set_xlabel('Distance downstream of the exit plane [lip radii]')
    axes.set_ylabel('Radius [lip radii]')
    axes.set_title('What the station marcher produces on the shipped nozzle\n'
                   f'Mach field at a lip ratio of {PRESSURERATIO:.1f}, shaded '
                   f'{mach.min():.2f} to {mach.max():.2f}', fontsize = 11.5, pad = 8)

    return structure, design

def build(captions = True, name = 'plumeShockAnatomy.png'):

    '''

    Draw the sheet, with or without the prose blocks under it.

    The plain version carries the same callouts and nothing else, for use where the reasoning is
    already to hand and the diagram is wanted on its own.

    '''

    with open(os.path.join(root, 'featureShowcase', 'showcaseBase.pkl'), 'rb') as handle:
        nozzle = pickle.load(handle)

    figure, (upper, lower) = plt.subplots(2, 1, figsize = (15.0, 12.5))
    drawSchematic(upper)
    structure, design = drawComputed(lower, nozzle)

    if not captions:
        figure.subplots_adjust(hspace = 0.22)
        path = os.path.join(here, name)
        figure.savefig(path, dpi = 150, bbox_inches = 'tight')
        plt.close(figure)
        print(f'  wrote {name}')
        return path

    figure.text(0.012, 0.035,
                'Why the disk appears. By symmetry the flow reaching the axis has to leave parallel '
                'to it, so the barrel shock has to be turned back through some angle. A regular '
                'reflection does that with a second oblique shock, and it exists only while the '
                'turn required stays under the maximum deflection an attached\noblique shock can '
                'supply at the local Mach number. Raise the pressure ratio and the flow expands '
                'harder, the boundary bulges further, the compressions coalesce more strongly and '
                'the demanded turn grows. Past the point where no regular reflection\nexists, the '
                'flow takes the three-shock solution instead: a near-normal disk on the axis, a '
                'reflected shock above it, and a slip line between them.\n'
                'Why it stops the march. Behind the disk the flow is subsonic, so the steady Euler '
                'equations are elliptic there and a marching scheme has no initial-value problem to '
                'pose. That is a change of equation type, not a loss of accuracy. Across the slip '
                'line the stagnation\npressure differs by path, which a solver carrying one '
                'stagnation pressure for the whole field cannot hold either.',
                fontsize = 8.5, color = muted, va = 'top')
    figure.text(0.012, -0.035,
                f'Placement. NOVA reports a disk above a nozzle pressure ratio of '
                f'{machDiskOnsetPressureRatio:.1f} and locates it by Ashkenas and Sherman, '
                f'x/D* = 0.67 sqrt(P0/Pa). That scales on the throat diameter and the chamber '
                f'pressure rather than on anything at the exit, which is the\nsonic-source result: '
                f'far enough out, a strongly underexpanded jet has forgotten the nozzle that made '
                f'it. The shipped nozzle at 5 kPa runs a pressure ratio of '
                f'{design.nozzlePressureRatio:.0f} and puts its disk '
                f'{(design.machDiskX - design.lipX)/design.lipRadius:.1f} lip radii out.\n'
                f'No disk diameter is drawn. The diameter correlation is unusable at this nozzle '
                f'pressure ratio: it returns a disk two to three times wider than the jet it sits '
                f'in.',
                fontsize = 8.5, color = warn, va = 'top')

    figure.subplots_adjust(hspace = 0.22)
    path = os.path.join(here, name)
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)
    print(f'  wrote {name}')
    print(f'  computed panel at lip ratio {PRESSURERATIO:.1f}, design NPR '
          f'{design.nozzlePressureRatio:.0f}, design disk at '
          f'{(design.machDiskX - design.lipX)/design.lipRadius:.2f} lip radii')

    return path

if __name__ == '__main__':
    build()
    build(captions = False, name = 'plumeShockAnatomyPlain.png')
