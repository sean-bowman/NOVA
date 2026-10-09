'''
Method-of-characteristics free-jet interior, shaded by Mach number.

This is the capability that would let a plume be drawn with a real interior field rather than a
boundary outline. It is EXPERIMENTAL and is not part of the NOVA backend: the net is grid
converged but its plume dimensions are low against NASA TN D-2327 by roughly a factor of two,
because the internal shock that recompresses the over-expanded core is not yet solved. The figure
states that on its face so it cannot be mistaken for a validated result.
'''
import os
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np

import showcasePalette
from matplotlib.patches import Polygon

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'experimental'))

import tnd2327 as moc

background = showcasePalette.background
panel      = showcasePalette.panel
copper     = showcasePalette.copper
green      = showcasePalette.green
ink        = showcasePalette.ink
muted      = showcasePalette.muted
warn       = showcasePalette.warn

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': showcasePalette.gridColor,
    'axes.grid': False, 'font.size': 9,
    'axes.titlesize': 12, 'axes.titleweight': 'bold', 'legend.framealpha': 0.0,
})

gamma = 1.4

def ambientOverTotal(machJet, staticRatio):
    '''TN D-2327 tabulates p_j/p_a, the jet static to ambient ratio.'''
    return 1.0 / (staticRatio * (1.0 + 0.5 * (gamma - 1.0) * machJet ** 2) ** (gamma / (gamma - 1.0)))

def drawInterior(machJet, thetaNDeg, staticRatio, slug, targetRadius, targetAxial):
    '''Shade the characteristics net by Mach number, with the computed jet boundary over it.'''
    gas = moc.Gas(gamma)
    net = moc.solveNet(gas, machJet, np.radians(thetaNDeg), 1.0,
                       ambientOverTotal(machJet, staticRatio),
                       numRays = 40, numLeading = 900, maxLines = 12000)

    nodes = [point for line in net['lines'] for point in line]
    if not nodes:
        print(f'  skipped {slug}: net did not build')
        return None

    x = np.array([p.x for p in nodes])
    y = np.array([p.y for p in nodes])
    mach = np.array([p.mach for p in nodes])
    boundaryX = np.array([p.x for p in net['boundary']])
    boundaryY = np.array([p.y for p in net['boundary']])

    machBoundary = net['boundaryMach']
    radiusMax = float(np.max(np.abs(boundaryY)))
    axialAt = float(boundaryX[int(np.argmax(np.abs(boundaryY)))])
    machMax = float(mach[x <= 1.35 * axialAt].max())

    figure, axes = plt.subplots(figsize = (13, 6.4))

    # tricontourf fills the convex hull of the nodes, which bridges the region downstream of the
    # last computed line where nothing was solved. The solved domain is bounded by the jet
    # boundary outward and by the last line downstream, so the fill is clipped to that outline.
    lastLine = net['lines'][-1]
    lastX = np.array([p.x for p in lastLine])
    lastY = np.array([p.y for p in lastLine])

    # The net degenerates once its lines have lost most of their points, spanning long distances
    # with too few nodes to shade. The view is carried to a third past the boundary maximum,
    # which covers the expansion and its turnover and drops the degenerate tail.
    solvedTo = float(boundaryX[int(np.argmax(np.abs(boundaryY)))] * 1.35)
    keep = boundaryX <= solvedTo + 1e-9
    boundaryX, boundaryY = boundaryX[keep], boundaryY[keep]
    lastIndex = int(np.argmin(np.abs(lastX - solvedTo)))
    lastX, lastY = lastX[:lastIndex + 1], lastY[:lastIndex + 1]

    outline = np.vstack([
        np.column_stack([boundaryX, -boundaryY]),            # upper boundary, lip to end
        np.column_stack([lastX[::-1], -lastY[::-1]]),         # upper last line, boundary to axis
        np.column_stack([lastX, lastY]),                      # lower last line, axis to boundary
        np.column_stack([boundaryX[::-1], boundaryY[::-1]]),  # lower boundary, end back to lip
    ])

    field = axes.tricontourf(np.concatenate([x, x]), np.concatenate([y, -y]),
                             np.concatenate([mach, mach]), levels = 100, cmap = showcasePalette.machMap)
    clip = Polygon(outline, closed = True, transform = axes.transData,
                   facecolor = 'none', edgecolor = 'none')
    axes.add_patch(clip)
    field.set_clip_path(clip)

    axes.plot(boundaryX, boundaryY, color = green, lw = 1.6, label = 'jet boundary')
    axes.plot(boundaryX, -boundaryY, color = green, lw = 1.6)
    axes.plot([-0.6, 0.0], [-1.0, -1.0], color = copper, lw = 2.4, label = 'nozzle lip')
    axes.plot([-0.6, 0.0], [1.0, 1.0], color = copper, lw = 2.4)

    axes.set_title(f'MOC free-jet interior    Mj {machJet}    '
                   f'wall angle {thetaNDeg} deg    pj/pa {staticRatio:.0f}    '
                   f'M boundary {machBoundary:.2f}')
    axes.set_xlabel('Axial distance from exit  x / r_j')
    axes.set_ylabel('Radius  r / r_j')
    axes.set_xlim(-8.0, solvedTo)
    axes.legend(loc = 'upper right', fontsize = 8, labelcolor = ink)

    figure.text(0.012, -0.02,
                'EXPERIMENTAL, NOT VALIDATED.  Grid converged, but the plume is low against '
                f'TN D-2327: max radius {radiusMax:.0f} against {targetRadius:.0f} r_j, '
                f'at x {axialAt:.0f} against {targetAxial:.0f} r_j.' + chr(10) +
                'The internal shock that recompresses the over-expanded core is not solved, so '
                f'the core reaches M {machMax:.0f} against a boundary M of {machBoundary:.1f}.',
                fontsize = 8.5, color = warn, va = 'top')

    bar = figure.colorbar(field, ax = axes, orientation = 'vertical', pad = 0.02, fraction = 0.035)
    bar.set_label('Mach number [-]')

    path = os.path.join(here, f'mocPlumeInterior_{slug}.png')
    figure.savefig(path, dpi = 160, bbox_inches = 'tight')
    plt.close(figure)
    print(f'  wrote mocPlumeInterior_{slug}.png   '
          f'(rmax {radiusMax:.1f} vs {targetRadius}, x {axialAt:.0f} vs {targetAxial})')
    return path

def drawCells(machJet, staticRatio, slug, numRays = 40, numLeading = 200):
    """
    Shock cell structure of a mildly off-design jet.

    Shock diamonds are the repeated reflection of the lip expansion fan off the constant pressure
    jet boundary and off the axis. At mild pressure ratios the compression waves have not yet
    coalesced into shocks, so the pattern is isentropic and the characteristics net resolves it
    directly. At Pe/Pa exactly 1 there is no wave structure to draw: a perfectly expanded jet is
    uniform, and the diamonds only exist off design.
    """
    gas = moc.Gas(gamma)
    ambient = ambientOverTotal(machJet, staticRatio)
    net = moc.solveNet(gas, machJet, 0.0, 1.0, ambient, numRays = numRays,
                       numLeading = numLeading, maxLines = 4000)

    nodes = [point for line in net['lines'] for point in line]
    if len(nodes) < 100:
        print(f'  skipped {slug}: net did not build')
        return None

    x = np.array([p.x for p in nodes])
    y = np.array([p.y for p in nodes])
    mach = np.array([p.mach for p in nodes])
    boundaryX = np.array([p.x for p in net['boundary']])
    boundaryY = np.array([p.y for p in net['boundary']])
    machBoundary = net['boundaryMach']

    lastLine = net['lines'][-1]
    lastX = np.array([p.x for p in lastLine])
    lastY = np.array([p.y for p in lastLine])

    radii = np.abs(boundaryY)
    slope = np.sign(np.diff(radii))
    cells = int(np.sum(slope[1:] * slope[:-1] < 0))

    figure, axes = plt.subplots(figsize = (14, 5.2))
    outline = np.vstack([
        np.column_stack([boundaryX, -boundaryY]),
        np.column_stack([lastX[::-1], -lastY[::-1]]),
        np.column_stack([lastX, lastY]),
        np.column_stack([boundaryX[::-1], boundaryY[::-1]]),
    ])
    field = axes.tricontourf(np.concatenate([x, x]), np.concatenate([y, -y]),
                             np.concatenate([mach, mach]), levels = 120, cmap = showcasePalette.machMap)
    clip = Polygon(outline, closed = True, transform = axes.transData,
                   facecolor = 'none', edgecolor = 'none')
    axes.add_patch(clip)
    field.set_clip_path(clip)

    axes.plot(boundaryX, boundaryY, color = ink, lw = 1.3, label = 'jet boundary')
    axes.plot(boundaryX, -boundaryY, color = ink, lw = 1.3)
    axes.plot([-0.5, 0.0], [-1.0, -1.0], color = copper, lw = 3.0, label = 'nozzle lip')
    axes.plot([-0.5, 0.0], [1.0, 1.0], color = copper, lw = 3.0)

    axes.set_title(f'MOC shock cell structure    Mj {machJet}    pj/pa {staticRatio}    '
                   f'M boundary {machBoundary:.2f}    cells resolved {cells}')
    axes.set_xlabel('Axial distance from exit  x / r_j')
    axes.set_ylabel('Radius  r / r_j')
    axes.set_xlim(-0.5, float(lastX.max()))
    axes.set_aspect('equal', adjustable = 'box')
    axes.legend(loc = 'upper right', fontsize = 8, labelcolor = ink)

    figure.text(0.012, -0.04,
                'EXPERIMENTAL, NOT VALIDATED.  The wave pattern is isentropic and resolved '
                'directly by the characteristics net: at this pressure ratio the compression '
                'waves reflected from' + chr(10) +
                'the boundary have not yet coalesced into shocks, so no shock capturing is needed '
                'to see the cell. The bright focus on the axis is the first diamond node.' +
                chr(10) +
                f'The net sustains {cells} cell before the center-line march stalls. A diamond '
                'train needs the sub-stepped approach to the center line from the report '
                '(statements 700, 740, 760)' + chr(10) +
                'and, once the waves coalesce, the SAMFM internal shock point. Forcing the march '
                'further with an axis offset is chaotic: one ulp of ambient pressure changes the '
                'cell count.',
                fontsize = 8.5, color = warn, va = 'top')

    bar = figure.colorbar(field, ax = axes, orientation = 'vertical', pad = 0.02, fraction = 0.030)
    bar.set_label('Mach number [-]')

    path = os.path.join(here, f'mocShockCells_{slug}.png')
    figure.savefig(path, dpi = 160, bbox_inches = 'tight')
    plt.close(figure)
    print(f'  wrote mocShockCells_{slug}.png   (cells {cells}, x to {lastX.max():.1f} r_j, '
          f'M {mach.min():.2f}-{mach.max():.2f})')
    return path

def main():
    '''Render the two TN D-2327 validation cases that the formulation can represent.'''
    print('Rendering MOC plume interiors')
    drawInterior(5.00, 15.0, 8143.0, 'machJet5', 225.0, 1050.0)
    drawInterior(4.79, 26.5, 2926.0, 'machJet4p79', 188.0, 720.0)
    print('Rendering MOC shock cell structure')
    drawCells(3.0, 1.5, 'machJet3ratio1p5')

if __name__ == '__main__':
    main()
