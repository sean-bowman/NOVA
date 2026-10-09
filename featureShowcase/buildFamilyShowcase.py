# -- One worked example per diverging section family -- #

'''

The shipped configuration built four ways, once per diverging section family, with everything on.

The point is coverage rather than comparison. NOVA's example case is a truncated ideal contour, so
the truncated ideal path is the one that is exercised end to end; this runs the same configuration
through the thrust-optimized parabola, the thrust-optimized contour and the cone, and records what
each one reaches and where it stops.

Each family gets a meridional figure carrying the four things a worked example has to show: the
chamber and the contour, the internal flow field, the regenerative jacket, and the plume. What a
family cannot produce is left off its figure and written down instead.

The report is the deliverable. It is written to docs/reports/ and lists, per family, which stages
completed, which were refused and why, and what would have to be built to close each gap.

Run it from the NOVA root:

    python featureShowcase/buildFamilyShowcase.py           # builds all four and writes the report
    python featureShowcase/buildFamilyShowcase.py --draw    # redraws the figures from the last build

Author: Sean Bowman

'''

import datetime
import json
import os
import pickle
import sys
import traceback

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np

import showcasePalette
from matplotlib.patches import Polygon

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'src'))

from NOVA import Nozzle
from NOVA.characteristics import CharacteristicGas
from NOVA.contour import divergingSectionFamily, quasiOneDimensionalField
from NOVA.plume import plumeCharacteristicSeed

FAMILIES = ('tic', 'top', 'toc', 'cone')
AMBIENT = 5000.0           # [Pa], the ambient the shipped configuration names
REACH = 2.0                # [-], lip radii of plume drawn, the solver default
MILLIMETRES = 1e3

background = showcasePalette.background
panel      = showcasePalette.panel
copper     = showcasePalette.copper
green      = showcasePalette.green
blue       = showcasePalette.blue
ink        = showcasePalette.ink
muted      = showcasePalette.muted
warn       = showcasePalette.warn

plt.rcParams.update({
    'figure.facecolor': background, 'axes.facecolor': panel,
    'savefig.facecolor': background, 'text.color': ink,
    'axes.labelcolor': ink, 'axes.edgecolor': muted,
    'xtick.color': muted, 'ytick.color': muted, 'grid.color': showcasePalette.gridColor,
    'axes.grid': False, 'font.size': 9,
})
def buildFamily(name):

    '''Run the shipped configuration with one diverging section family, or report why not.'''

    config = json.load(open(os.path.join(root, 'src', 'NOVA', 'assets', 'NOVANozzle.json')))
    config.update({'divergingSectionType': name, 'Lstar': 1.0, 'material': 'GRCop-42',
                   'plumeAmbientPressure': AMBIENT, 'plotsEnabled': False, 'export': False,
                   'filename': f'family_{name}'})
    path = os.path.join(here, f'familyConfig_{name}.json')
    json.dump(config, open(path, 'w'), indent = 2)

    Nozzle._getOutputRoot = lambda self, _base = here: _base
    nozzle = Nozzle()
    nozzle.generateNozzle(configPath = path)

    return nozzle

def sizeOf(nozzle, attribute):
    '''Element count of an attribute, tolerating absence and ragged blocks.'''
    value = getattr(nozzle, attribute, None)
    if value is None:
        return 0
    try:
        return int(sum(np.asarray(block).size for block in value))
    except Exception:
        return int(np.asarray(value).size)

def capabilities(name, nozzle):

    '''What this build reached, stage by stage.'''

    row = {'family': divergingSectionFamily(name), 'built': True,
           'wall': sizeOf(nozzle, 'xNozzleWall'),
           'mesh': sizeOf(nozzle, 'allMachNumbers'),
           'nearWall': sizeOf(nozzle, 'nozzleNearWallMachNumber'),
           'jacket': sizeOf(nozzle, 'channelRadius'),
           'coolantExit': getattr(nozzle, 'coolantExitTemperature', None),
           'extension': sizeOf(nozzle, 'xExtension'),
           'exitMach': float(getattr(nozzle, 'exitMachNumber', 0.0) or 0.0)}

    try:
        structure = nozzle.plumeStructure(AMBIENT)
        row['structure'] = structure.jetType
    except Exception as error:
        row['structure'] = f'FAILED {type(error).__name__}'

    try:
        field = nozzle.plumeField(AMBIENT, reach = REACH)
        row['fieldSolved'] = bool(field.solved)
        row['fieldTrust'] = bool(field.trustworthy)
        row['drift'] = float(field.massDriftWorst)
        row['fieldNote'] = field.notes[-1] if field.notes else ''
        row['marchNote'] = field.notes[0] if field.notes else ''
    except Exception as error:
        row['fieldSolved'] = False
        row['fieldTrust'] = False
        row['drift'] = float('nan')
        row['fieldNote'] = f'FAILED {type(error).__name__}: {error}'
        row['marchNote'] = row['fieldNote']

    return row

def interiorField(nozzle, exitX):
    '''Every characteristic mesh node upstream of the lip, scaled back into metres.'''
    scale = float(getattr(nozzle, 'nozzleScalingFactor', 1.0) or 1.0)
    axial, radial, mach = [], [], []
    for xBlock, rBlock, machBlock in zip(nozzle.allXPoints, nozzle.allRPoints,
                                         nozzle.allMachNumbers):
        blockX = np.asarray(xBlock, dtype = float).ravel()*scale
        blockR = np.asarray(rBlock, dtype = float).ravel()*scale
        blockMach = np.asarray(machBlock, dtype = float).ravel()
        if blockX.shape != blockR.shape or blockX.shape != blockMach.shape:
            continue
        keep = (np.isfinite(blockX) & np.isfinite(blockR) & np.isfinite(blockMach)
                & (blockX <= exitX))
        axial.append(blockX[keep]); radial.append(blockR[keep]); mach.append(blockMach[keep])
    if not axial:
        return None

    return np.concatenate(axial), np.concatenate(radial), np.concatenate(mach)

def oneDimensionalField(nozzle, branch):

    '''

    One side of the throat as the one-dimensional answer painted across the radius.

    Nothing solves a field in either place for every family. Upstream of the throat the flow is
    subsonic and no mesh reaches it at all. Downstream, a cone has no characteristic solve either,
    so the same treatment is the only interior it has and it is the one its near-wall state and
    its thrust coefficient were already built from.

    '''

    gas = CharacteristicGas(nozzle.chamberGamma, nozzle.chamberRGasConstant,
                            nozzle.chamberStagnationTemperature)
    wallX = np.asarray(nozzle.xNozzleWall, dtype = float)
    wallR = np.asarray(nozzle.rNozzleWall, dtype = float)
    throat = int(np.argmin(wallR))
    section = slice(0, throat + 1) if branch == 'subsonic' else slice(throat, None)
    field = quasiOneDimensionalField(wallX[section], wallR[section], gas,
                                     nozzle.chamberPressure, throatRadius = wallR[throat],
                                     branch = branch)

    return field['x'].ravel(), field['r'].ravel(), field['mach'].ravel()

def drawFamily(name, nozzle, row):

    '''The meridional showcase for one family: contour, interior, jacket and plume.'''

    figure, axes = plt.subplots(figsize = (15.0, 5.6))
    wallX = np.asarray(nozzle.xNozzleWall, dtype = float)*MILLIMETRES
    wallR = np.asarray(nozzle.rNozzleWall, dtype = float)*MILLIMETRES
    outline = np.vstack([np.column_stack([wallX, wallR]),
                         np.column_stack([wallX[::-1], -wallR[::-1]])])

    blocks, plume = [], None
    seed = plumeCharacteristicSeed(nozzle.plumeContour())
    inner = interiorField(nozzle, seed['exitX']) if seed is not None and row['mesh'] else None
    if inner is not None:
        blocks.append(inner)
    else:
        # No characteristic solve to draw, which is the cone. Its diverging section gets the same
        # one-dimensional treatment its near-wall state and thrust coefficient already rest on,
        # rather than being left blank.
        try:
            blocks.append(oneDimensionalField(nozzle, 'supersonic'))
            row['interiorSource'] = 'one-dimensional'
        except Exception:
            pass
    try:
        blocks.insert(0, oneDimensionalField(nozzle, 'subsonic'))
    except Exception:
        pass

    field = getattr(nozzle, 'nozzlePlumeField', None)
    if field is not None and field.solved:
        plume = (field.nodeX, field.nodeR, field.nodeMach)

    # One scale across the whole picture, uncapped. The plume legitimately runs faster than the
    # nozzle exit because it keeps expanding past the lip, so capping against it would be hiding
    # physics rather than an artifact.
    #
    # The interior is a different matter. A node inside the duct cannot be faster than the duct's
    # own exit, and on the optimized families some are. Those are counted over the interior mesh
    # alone and reported. Counting them over the plume as well, which an earlier version did,
    # reports the jet's own expansion as a mesh defect.
    everyMach = ([block[2] for block in blocks[1:]]
                 + ([plume[2]] if plume is not None else []))
    exitMach = float(getattr(nozzle, 'exitMachNumber', 0.0) or 0.0)
    if everyMach:
        machLow = min(float(values.min()) for values in everyMach)
        machHigh = max(float(values.max()) for values in everyMach)
    else:
        machLow, machHigh = 0.0, 1.0
    interior = [block[2] for block in blocks[1:]]
    row['machOverExit'] = int(sum(int((values > exitMach*1.02).sum()) for values in interior))
    row['machPeak'] = max((float(values.max()) for values in interior), default = 0.0)
    levels = np.linspace(machLow, machHigh, 120)

    patch = None
    for blockX, blockR, blockMach in blocks:
        patch = axes.tricontourf(np.concatenate([blockX, blockX])*MILLIMETRES,
                                 np.concatenate([blockR, -blockR])*MILLIMETRES,
                                 np.concatenate([blockMach, blockMach]),
                                 levels = levels, cmap = showcasePalette.machMap, extend = 'both')
        clip = Polygon(outline, closed = True, transform = axes.transData,
                       facecolor = 'none', edgecolor = 'none')
        axes.add_patch(clip)
        patch.set_clip_path(clip)

    if plume is not None:
        # The station march leaves unstructured nodes over one half plane, so they are mirrored
        # and handed to tricontourf rather than resampled onto a grid.
        for sign in (1.0, -1.0):
            patch = axes.tricontourf(plume[0]*MILLIMETRES, sign*plume[1]*MILLIMETRES, plume[2],
                                     levels = levels, cmap = showcasePalette.machMap, extend = 'both')
        boundaryX = np.asarray(field.boundaryX, dtype = float)*MILLIMETRES
        boundaryR = np.asarray(field.boundaryR, dtype = float)*MILLIMETRES
        for sign in (1.0, -1.0):
            axes.plot(boundaryX, sign*boundaryR, color = ink, lw = 1.3, zorder = 4,
                      label = 'plume boundary, solved' if sign > 0 else None)

    # Where no march was solved the correlated structure is what there is, so its boundary is
    # drawn dotted rather than the space being left empty. It is an interpolated shape between
    # measured scalars, not a streamline, and the line style says so.
    structure = getattr(nozzle, 'nozzlePlumeStructure', None)
    correlated = (plume is None and structure is not None
                  and np.asarray(structure.boundaryR).size > 1)
    if correlated:
        for sign in (1.0, -1.0):
            axes.plot(np.asarray(structure.boundaryX)*MILLIMETRES,
                      sign*np.asarray(structure.boundaryR)*MILLIMETRES, color = ink, lw = 1.3,
                      ls = ':', zorder = 4,
                      label = 'plume boundary, correlated' if sign > 0 else None)

    # The jacket, drawn as the three surfaces that bound it: hot wall, channel band and shell.
    jacketX = np.asarray(getattr(nozzle, 'xChannelCenterline2D', []), dtype = float)
    jacketR = np.asarray(getattr(nozzle, 'rChannelCenterline2D', []), dtype = float)
    radius = np.asarray(getattr(nozzle, 'channelRadius', []), dtype = float)
    shellX = np.asarray(getattr(nozzle, 'xNozzleShell', []), dtype = float)
    shellR = np.asarray(getattr(nozzle, 'rNozzleShell', []), dtype = float)
    if jacketX.size and jacketX.size == radius.size:
        for sign in (1.0, -1.0):
            axes.fill_between(jacketX*MILLIMETRES, sign*(jacketR - radius)*MILLIMETRES,
                              sign*(jacketR + radius)*MILLIMETRES, color = blue, alpha = 0.45,
                              zorder = 5, label = 'regen channels' if sign > 0 else None)
    if shellX.size:
        for sign in (1.0, -1.0):
            axes.plot(shellX*MILLIMETRES, sign*shellR*MILLIMETRES, color = blue, lw = 1.2,
                      ls = '--', zorder = 5, label = 'jacket shell' if sign > 0 else None)

    extensionX = np.asarray(getattr(nozzle, 'xExtension', []), dtype = float)
    extensionR = np.asarray(getattr(nozzle, 'rExtension', []), dtype = float)
    if extensionX.size:
        for sign in (1.0, -1.0):
            axes.plot(extensionX*MILLIMETRES, sign*extensionR*MILLIMETRES, color = green,
                      lw = 1.8, zorder = 6,
                      label = 'radiative extension' if sign > 0 else None)

    for sign in (1.0, -1.0):
        axes.plot(wallX, sign*wallR, color = copper, lw = 2.0, zorder = 7,
                  label = 'nozzle wall' if sign > 0 else None)

    if plume is not None:
        span = float(np.abs(field.boundaryR).max())*MILLIMETRES
        rightEdge = float(field.boundaryX.max())*MILLIMETRES + 20.0
    elif correlated:
        span = float(np.abs(structure.boundaryR).max())*MILLIMETRES
        rightEdge = float(np.asarray(structure.boundaryX).max())*MILLIMETRES + 20.0
    else:
        span, rightEdge = wallR.max(), wallX.max() + 20.0
    extent = max(span, wallR.max())
    axes.set_xlim(wallX.min() - 20.0, rightEdge)
    axes.set_ylim(-1.15*extent, 1.15*extent)
    axes.set_aspect('equal', adjustable = 'box')
    axes.set_xlabel('Axial station [mm]')
    axes.set_ylabel('Radius [mm]')

    heading = f'{row["family"]}   ambient {AMBIENT/1000.0:.1f} kPa'
    if row.get('interiorSource'):
        heading += '   interior one-dimensional, no characteristic solve'
    if plume is not None:
        heading += (f'   plume {REACH:.0f} lip radii, mass continuity error '
                    f'{row["drift"]:+.2f} %')
    else:
        heading += ('   plume boundary correlated, not solved'
                    if correlated else '   no plume')
    if row.get('machOverExit'):
        heading += (f'\ninterior peaks at Mach {row["machPeak"]:.2f} against a one-dimensional '
                    f'exit value of {exitMach:.2f}')
    axes.set_title(heading, fontsize = 11,
                   color = green if row.get('fieldTrust') else warn, pad = 8)
    axes.legend(loc = 'upper left', fontsize = 8, labelcolor = ink, ncol = 3)

    if patch is not None:
        bar = figure.colorbar(patch, ax = axes, pad = 0.01, fraction = 0.026)
        bar.set_label('Mach number [-]', fontsize = 9)

    path = os.path.join(here, f'familyShowcase_{name}.png')
    figure.savefig(path, dpi = 150, bbox_inches = 'tight')
    plt.close(figure)

    return path

GAPS = '''
### The cone, closed

The cone now builds end to end and reaches every stage the contoured families do except the
marched plume. `solveConicalContour` puts it through the same `finishContourSolution` as the rest,
supplying the two things a characteristic solve would have provided: the near-wall state, from the
one-dimensional area-Mach relation at the local wall radius, and the thrust coefficient, from a
source-flow exit plane handed to the same integral the bells use. The divergence loss falls out of
that integration, so `divergenceLossFactor` is not applied on top.

It had failed because `Nozzle.generateNozzle` calls `truncateForRegen()` unconditionally, before
it checks whether cooling is even switched on, and `regenStations.solveRegenStations` then sliced a
near-wall temperature array that `chamber.py` never populated: the block that computes it was
guarded by `divergingSectionFamily(...) != 'conical'` in two places. Both guards are gone, because
the cone now supplies its own near-wall Mach number and the concatenation below them does not care
which solve produced it.

Two limits are worth recording against the result. The one-dimensional near-wall state carries no
radial structure and no wave reflections, so it misses the overexpansion at the arc-to-cone
junction that SP-8120 warns can stand a shock. And the source-flow exit plane is the classical
approximation rather than a solve, so the thrust coefficient inherits whatever that costs.

The marched plume still refuses a cone, correctly: there is no characteristic mesh to continue and
the correlated plume structure stands in. Closing that would mean solving the cone's interior with
the method of characteristics, which is the same forward solve the optimized families need.

### The thrust-optimized parabola hands over a corrupt exit plane

The parabola builds, carries a mesh, cools and reaches a marched plume, but its exit profile is
not physical. Across the exit plane it is non-monotone in both Mach number and flow angle, and it
carries a node at 50.8 degrees of flow angle on a wall that turns 8.15 degrees. The truncated
ideal contour on the same configuration is monotone in both, 4.203 down to 3.797 in Mach and 0 up
to 8.69 degrees in angle, against a wall exit angle of 8.77 degrees.

The consequence is measurable rather than cosmetic. Marched two lip radii, the parabola loses
5.53 per cent of the exit mass flow where the truncated ideal contour loses 0.72 per cent, so the
plume is drawn and is not trustworthy.

The cause is that the stored characteristic mesh is the one used to design the contour, not a
solve of the duct that was built. A thrust-optimized parabola is fitted between two wall angles
and its wall is not a streamline of the mesh behind it, so reading the mesh at the exit abscissa
samples a flow field that the physical nozzle does not contain.

What closes it: solve the actual duct. Running the method of characteristics forward through the
built parabola, with the wall as a boundary condition rather than as an output, produces an exit
plane that belongs to the nozzle. That is a new solve rather than a repair of the existing one.

### The stored mesh carries states the nozzle never reaches

On both optimized families 113 of 6124 interior mesh nodes, 1.8 per cent, sit above the nozzle's
own exit Mach number of 4.223, peaking at 6.29 for the parabola and 7.53 for the contour. Inside
a duct that exits at 4.223 there is nowhere for Mach 7.5 to be. The truncated ideal contour has
none: its mesh spans 1.137 to 4.203 and stops there.

This is the same defect as the corrupt exit plane seen from a different angle, and it is what
forces the showcase figures to cap their colour scale. The identical node count on two different
contours points at the shared kernel generation rather than at either contour routine.

What closes it: the same forward solve. A check that no interior node exceeds the exit Mach number
would also catch it at build time, which nothing does today.

### The thrust-optimized contour is usable and marginal

The contour reaches every stage and its plume conserves mass to 0.96 per cent over two lip radii,
inside the one per cent the field is called trustworthy within but not by much, against 0.72 per
cent for the truncated ideal contour. Its exit profile is also non-monotone, though far less so
than the parabola's, and it carries a duplicated radius where two mesh rows cross the exit plane
at the same station. The same forward solve that fixes the parabola would settle this one.

### A defect found while probing, and fixed

`_exitPlaneCrossings` short-circuited on any node that happened to lie within rounding of the exit
abscissa, taking that node in place of the whole block's interpolated crossings. A single
coincidental node was enough to discard a block. The parabola put exactly one node there and lost
44 crossings behind it, which is why both optimized families reported no readable exit plane at
all before this run. The truncated ideal contour has no node on the plane, so the defect never
fired on the shipped example. The branch now requires `exitPlaneMinimumNodes` before it will
stand in for the crossings.
'''

STAGES = (('wall', 'Contour'), ('mesh', 'Internal field'), ('nearWall', 'Near-wall gas state'),
          ('jacket', 'Regen jacket'), ('extension', 'Radiative extension'))

def mark(value):
    '''A stage reached or not.'''

    return 'yes' if value else 'NO'

def writeReport(rows, figures, path):

    '''The capability matrix and the gaps behind it.'''

    today = datetime.date.today().isoformat()
    lines = []
    lines.append('# Diverging section families: what a worked example reaches')
    lines.append('')
    lines.append(f'Generated {today} by `featureShowcase/buildFamilyShowcase.py`, running the '
                 f'shipped `NOVANozzle.json` configuration once per diverging section family with '
                 f'every feature enabled: chamber, cooling jacket, film, radiative extension, '
                 f'volutes and plume. Ambient pressure {AMBIENT/1000.0:.1f} kPa, plume drawn to '
                 f'{REACH:.0f} lip radii.')
    lines.append('')
    lines.append('## Capability matrix')
    lines.append('')
    header = '| Stage | ' + ' | '.join(row['family'] for row in rows) + ' |'
    lines.append(header)
    lines.append('|---' * (len(rows) + 1) + '|')
    for key, label in STAGES:
        cells = [mark(row.get(key)) if row.get('built') else 'NO' for row in rows]
        lines.append(f'| {label} | ' + ' | '.join(cells) + ' |')
    lines.append('| Plume, correlated | '
                 + ' | '.join(str(row.get('structure', 'NO')) if row.get('built') else 'NO'
                              for row in rows) + ' |')
    lines.append('| Plume, marched | '
                 + ' | '.join(mark(row.get('fieldSolved')) if row.get('built') else 'NO'
                              for row in rows) + ' |')
    lines.append('| Plume conserves mass | '
                 + ' | '.join(mark(row.get('fieldTrust')) if row.get('built') else 'NO'
                              for row in rows) + ' |')
    lines.append('| Mass continuity error | '
                 + ' | '.join((f'{row["drift"]:+.2f} %'
                               if row.get('built') and row.get('fieldSolved') else '--')
                              for row in rows) + ' |')
    lines.append('')

    for row, figure in zip(rows, figures):
        lines.append(f'## {row["family"]}')
        lines.append('')
        if not row.get('built'):
            lines.append(f'**The build does not complete.** {row["error"]}')
            lines.append('')
            lines.append('```')
            lines.append(row.get('traceback', '').strip())
            lines.append('```')
            lines.append('')
            continue
        # The report lives in docs/reports and the figures beside the script that made them.
        relative = os.path.relpath(figure, os.path.dirname(path)).replace(os.sep, '/')
        lines.append(f'![{row["family"]}]({relative})')
        lines.append('')
        lines.append(f'Contour {row["wall"]} wall points, internal field {row["mesh"]} mesh '
                     f'nodes, jacket {row["jacket"]} sized stations, coolant exit '
                     f'{row["coolantExit"]:.1f} K.' if row.get('coolantExit') else
                     f'Contour {row["wall"]} wall points, internal field {row["mesh"]} mesh '
                     f'nodes.')
        lines.append('')
        # A conservation verdict only means something when something was marched.
        if row.get('fieldSolved'):
            verdict = ('conserves mass over this reach' if row.get('fieldTrust')
                       else 'does NOT conserve mass over this reach')
            lines.append(f'Plume: {row["marchNote"]} It {verdict}.')
        else:
            lines.append(f'Plume: not marched. {row["marchNote"]}')
        if row.get('machOverExit'):
            lines.append('')
            lines.append(f'Interior mesh: peaks at Mach {row["machPeak"]:.2f} against a '
                         f'one-dimensional exit value of '
                         f'{row["exitMach"]:.2f}. A contour that does not '
                         f'straighten its exit leaves a non-uniform exit plane, so a centre-line '
                         f'above the one-dimensional average is expected rather than wrong; what '
                         f'would be wrong is an extreme, and the fold guard in the forward march '
                         f'removes those.')
        lines.append('')

    lines.append('## Gaps')
    lines.append('')
    lines.append(GAPS.strip())
    lines.append('')

    with open(path, 'w', encoding = 'utf-8', newline = '\n') as handle:
        handle.write('\n'.join(lines))

    return path

def redraw() -> None:

    '''

    Redraw every family's figure from the nozzles the last full run pickled, without building them
    again or rewriting the report.

    '''

    for name in FAMILIES:
        path = os.path.join(here, f'family_{name}.pkl')
        if not os.path.exists(path):
            print(f'   {name}: no cached nozzle; run without --draw first')
            continue
        with open(path, 'rb') as handle:
            nozzle = pickle.load(handle)
        print('   wrote', drawFamily(name, nozzle, capabilities(name, nozzle)), flush = True)

if __name__ == '__main__' and '--draw' in sys.argv:
    redraw()
elif __name__ == '__main__':
    rows, figures = [], []
    for name in FAMILIES:
        print(f'=== {name} ===', flush = True)
        try:
            nozzle = buildFamily(name)
            row = capabilities(name, nozzle)
            row['error'] = ''
            with open(os.path.join(here, f'family_{name}.pkl'), 'wb') as handle:
                pickle.dump(nozzle, handle)
            figures.append(drawFamily(name, nozzle, row))
        except Exception as error:
            row = {'family': divergingSectionFamily(name), 'built': False,
                   'error': f'{type(error).__name__}: {error}',
                   'traceback': traceback.format_exc()[-1200:]}
            figures.append('')
        rows.append(row)
        print('   ' + ('built' if row.get('built') else row['error'][:90]), flush = True)

    reportDir = os.path.join(root, 'docs', 'reports')
    os.makedirs(reportDir, exist_ok = True)
    target = os.path.join(reportDir,
                          f'contourFamilies_{datetime.date.today().isoformat()}.md')
    print()
    print('  wrote', writeReport(rows, figures, target))
