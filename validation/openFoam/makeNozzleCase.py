# -- NOVA Nozzle: OpenFOAM Case Generator -- #

'''

Write an axisymmetric OpenFOAM case of NOVA's shipped nozzle, and the NOVA solution it is checked
against.

The case solves the problem NOVA's method of characteristics solves: the Euler equations for a
calorically perfect gas at NOVA's chamber ratio of specific heats and gas constant, from the
injector face to the exit plane, with slip walls and the chamber's stagnation state at the inlet.
`rhoCentralFoam` solves it on a 5 degree wedge with the Kurganov-Tadmor central scheme. Both
methods then answer the same question, so a difference between them is a difference of method.

NOVA is solved flow only, with no jacket, film, extension or plume, none of which touch the flow
the case solves, and with a 2000 point contour so the wall the mesh follows carries the throat
radius to 1.5 parts per million. A 100 point contour gives the same characteristic solution to the
bit; only the wall it is resampled to is coarser. NOVA is solved a second time with the transonic
near-wall model, which changes only the converging wall's state, so the case can be read against
both converging-wall models.

The solution is written to `reference/novaNozzle.json`: the gas, the wall, the near-wall state,
every node of the characteristic mesh inside the nozzle, NOVA's exit plane and its performance
figures. `reference/style.json` carries NOVA's dark figure palette, so the comparison figures
match the rest of NOVA's documentation without importing NOVA.

Run it with the Python NOVA is installed in, from the NOVA root:

    python validation/openFoam/makeNozzleCase.py                          # medium grid
    python validation/openFoam/makeNozzleCase.py --resolution fine
    python validation/openFoam/makeNozzleCase.py --resolution coarse --output <folder>
    python validation/openFoam/makeNozzleCase.py --refresh                # re-solve NOVA first

The case is written to `validation/openFoam/cases/novaNozzle2D-<resolution>/` unless `--output`
says otherwise. It is self-contained: the reference, the initialization and the comparison scripts
travel with it, so it runs anywhere OpenFOAM and Python with NumPy and Matplotlib do. The coarse
grid runs from the quasi one-dimensional flow; each finer grid runs from the next coarser grid's
converged solution, `./Allrun ../novaNozzle2D-coarse`. See README.md.

Author: Sean Bowman

'''

import argparse
import json
import math
import os
import shutil
import sys

import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
repositoryRoot = os.path.dirname(os.path.dirname(here))
referencePath = os.path.join(here, 'reference', 'novaNozzle.json')
stylePath = os.path.join(here, 'reference', 'style.json')

# OpenFOAM's universal gas constant [J/kmol K], which turns NOVA's specific gas constant into the
# molecular weight OpenFOAM's perfect gas is specified by
universalGasConstant = 8314.47

wedgeAngle = 5.0              # [deg], the whole wedge, half each side of the x-y plane
contourPoints = 2000          # [-], points in the wall the mesh follows

# A wedge built from flat faces has a cross-section of r^2 sin(a) / 2 where the axisymmetric sector
# it stands for has r^2 a / 2, which is 0.13 percent less flow area at 5 degrees. Pushing every wall
# point out by sqrt(a / sin a) gives the flat-faced wedge the sector's exact area at every station,
# so the throat area, the mass flow and the thrust need no correction afterwards.
radialScale = math.sqrt(math.radians(wedgeAngle) / math.sin(math.radians(wedgeAngle)))

# Cells across the radius at each resolution, each level twice the last for a Richardson estimate.
# Axial cells are sized from the local radius, so a cell is cellAspect times as long as it is tall
# everywhere along the nozzle.
resolutions = {'coarse': 30, 'medium': 60, 'fine': 120}
cellAspect = 1.5

# Physical time each grid runs [s]. The coarse grid starts from the quasi one-dimensional flow and
# needs several passes of the chamber for its acoustics to die away. Each finer grid starts from the
# converged solution one level coarser, mapped onto it, and only has the difference to settle.
endTimes = {'coarse': 6e-3, 'medium': 3e-3, 'fine': 1e-3}

# rhoCentralFoam's Courant number counts the wedge faces, which carry no flux. On the prisms along
# the axis they make up about nine tenths of it, so the step is set there, and the in-plane Courant
# number at the throat, where the scheme's stability is decided, is about a fifth of this. At 2.5 the
# run is unstable: the chamber's acoustic ringing grows instead of decaying.
maxCourant = 1.0

# Fraction of each run, at its end, the fields are averaged over. The chamber's radial acoustic
# modes carry almost nothing into the nozzle and an inviscid solution has nothing else to damp them,
# so they ring for as long as the run lasts: the first radial mode at 11 kHz on the coarse grid and
# the second at 20 kHz on the medium, at 0.2 to 0.3 percent of the inlet mass flow and a fifth of
# that at the exit. The mean flow is steady; the comparison reads the mean.
averagedFraction = 0.5

# Blocks are split wherever the wall radius has changed by this factor since the last split, so the
# geometric axial grading inside each block follows the radius closely
blockRadiusRatio = 1.3

#--------------------------------------------------------------------------------------------------------------------------#
# -- The NOVA solution -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _rounded(values, digits: int = 9) -> list:

    '''An array as a list of floats to `digits` significant figures.'''

    return [float(f'{value:.{digits}g}') for value in np.asarray(values, dtype = float).ravel()]

def _solve(config: dict, name: str):

    '''

    Solve one configuration with NOVA, writing nothing outside the case folder.

    Parameters:
    -----------
    config : dict
        The configuration, as the JSON NOVA reads
    name : str
        Name of the run, for its scratch folder

    Returns:
    --------
    Nozzle : the solved nozzle

    '''

    os.environ.setdefault('NOVA_HEADLESS', '1')
    sys.path.insert(0, os.path.join(repositoryRoot, 'src'))
    from NOVA import Nozzle

    scratch = os.path.join(here, 'cases', '_novaRuns', name)
    os.makedirs(scratch, exist_ok = True)
    configPath = os.path.join(scratch, 'config.json')
    with open(configPath, 'w', encoding = 'utf-8') as handle:
        json.dump(config, handle, indent = 2)

    Nozzle._getOutputRoot = lambda self: scratch
    nozzle = Nozzle()
    nozzle.generateNozzle(configPath = configPath)

    return nozzle

def _chokedMassFlow(chamberPressure: float, throatArea: float, gamma: float, gasConstant: float,
                    stagnationTemperature: float) -> float:

    '''One-dimensional choked mass flow through a throat with a flat sonic line [kg/s].'''

    return (chamberPressure * throatArea * math.sqrt(gamma / (gasConstant * stagnationTemperature))
            * (2.0 / (gamma + 1.0))**((gamma + 1.0) / (2.0 * (gamma - 1.0))))

def solveNova() -> dict:

    '''

    Solve the shipped nozzle, flow only, and gather what the case is built from and checked
    against.

    Returns:
    --------
    dict : the reference, ready to write as JSON

    '''

    with open(os.path.join(repositoryRoot, 'src', 'NOVA', 'assets', 'NOVANozzle.json'), encoding = 'utf-8') as handle:
        config = json.load(handle)
    config.pop('_comment', None)

    # Nothing switched off here reaches the flow the case solves
    config.update(filename = 'openFoamReference', numContourPoints = contourPoints, makeCoolingChannels = False,
                  makeInletVolute = False, makeOutletVolute = False, filmCooling = False,
                  makeRadiativeExtension = False, plumeAmbientPressure = None, export = 'off', plotsEnabled = 'off')
    nozzle = _solve(config, 'oneDimensional')
    transonic = _solve(dict(config, nearWallStateModel = 'transonic'), 'transonic')

    gamma, gasConstant = float(nozzle.chamberGamma), float(nozzle.chamberRGasConstant)
    stagnationTemperature, chamberPressure = float(nozzle.chamberStagnationTemperature), float(nozzle.chamberPressure)
    throatRadius = float(nozzle.nozzleScalingFactor)    # [m], the length the characteristic mesh is scaled by

    wallX, wallR = np.asarray(nozzle.xNozzleWall, dtype = float), np.asarray(nozzle.rNozzleWall, dtype = float)
    throat = int(np.argmin(wallR))

    # The chamber barrel ends at the last point still at the chamber radius
    barrelEnd = max(int(np.argmax(wallR < wallR[0] * (1.0 - 1e-9))) - 1, 0)

    # Every node of the characteristic mesh inside the nozzle, in meters. The truncated ideal
    # contour is cut from a longer ideal nozzle, and the mesh carries on past the cut; nothing past
    # the exit plane or outside the wall can reach the flow inside it.
    fields = {'x': [], 'r': [], 'mach': [], 'flowAngle': [], 'pressure': [], 'temperature': []}
    for block in zip(nozzle.allXPoints, nozzle.allRPoints, nozzle.allMachNumbers, nozzle.allFlowAngles,
                     nozzle.allPressures, nozzle.allTemperatures):
        x, r, mach, angle, pressure, temperature = (np.asarray(value, dtype = float).ravel() for value in block)
        x, r = x * throatRadius, r * throatRadius
        keep = np.all(np.isfinite([x, r, mach, angle, pressure, temperature]), axis = 0)
        keep &= (x <= wallX[-1]) & (r <= np.interp(x, wallX, wallR) * (1.0 + 1e-6))
        for key, value in zip(fields, (x, r, mach, angle, pressure, temperature)):
            fields[key].append(value[keep])
    characteristics = {key: _rounded(np.concatenate(value), 8) for key, value in fields.items()}

    # The exit plane comes back in throat radii, ordered from the wall to the axis
    exitRadius = np.asarray(nozzle.exitPlaneRadius, dtype = float)
    throatArea = math.pi * throatRadius**2

    # NOVA's pressure term is taken against the design exit pressure. In vacuum it is taken against
    # nothing, which adds that pressure back over the area the plane integral covers.
    vacuumThrustCoefficient = (float(nozzle.thrustCoef)
                               + float(nozzle.targetExitPressure) * float(exitRadius[0])**2 / chamberPressure)

    return {
        'description': ('NOVA\'s shipped nozzle, flow only, solved by NOVA\'s method of characteristics at the chamber '
                        'ratio of specific heats'),
        'config': {key: config[key] for key in ('Fuel', 'Oxidizer', 'OFRatio', 'chamberPressure', 'thrust',
                                                'expansionRatio', 'divergingSectionType', 'lengthFraction',
                                                'chamberDiameter', 'Lstar', 'convergingSectionAngle',
                                                'throatInletCurvature', 'throatOutletCurvature', 'numCharacteristics',
                                                'transonicModel', 'gammaModel', 'numContourPoints')},
        'gas': {'gamma': gamma, 'gasConstant': gasConstant, 'stagnationTemperature': stagnationTemperature,
                'chamberPressure': chamberPressure, 'specificHeat': gamma * gasConstant / (gamma - 1.0),
                'molecularWeight': universalGasConstant / gasConstant, 'throatGamma': float(nozzle.throatGamma)},
        'geometry': {'wallX': _rounded(wallX, 12), 'wallR': _rounded(wallR, 12),
                     'barrelEndIndex': barrelEnd, 'throatIndex': throat, 'throatRadius': throatRadius,
                     'injectorX': float(wallX[0]), 'throatX': float(wallX[throat]), 'exitX': float(wallX[-1]),
                     'chamberRadius': float(wallR[0]), 'exitRadius': float(wallR[-1])},
        'nearWall': {'x': _rounded(wallX, 12), 'mach': _rounded(nozzle.nozzleNearWallMachNumber),
                     'pressure': _rounded(nozzle.nozzleNearWallPressure),
                     'temperature': _rounded(nozzle.nozzleNearWallTemperature),
                     'transonicMach': _rounded(transonic.nozzleNearWallMachNumber),
                     'transonicPressure': _rounded(transonic.nozzleNearWallPressure)},
        'characteristics': characteristics,
        'exitPlane': {'r': _rounded(exitRadius * throatRadius), 'mach': _rounded(nozzle.exitPlaneMach),
                      'flowAngle': _rounded(nozzle.exitPlaneFlowAngle), 'pressure': _rounded(nozzle.exitPlanePressure),
                      'sampledFraction': float(nozzle.exitPlaneSampledFraction)},
        'performance': {'thrustCoefficient': float(nozzle.thrustCoef),
                        'velocityTermThrustCoefficient': float(nozzle.velocityTermThrustCoef),
                        'pressureTermThrustCoefficient': float(nozzle.pressureTermThrustCoef),
                        'designExitPressure': float(nozzle.targetExitPressure),
                        'vacuumThrustCoefficient': vacuumThrustCoefficient,
                        'exitAreaAveragedPressure': float(nozzle.exitAreaAveragedPressure),
                        'exitMassAveragedPressure': float(nozzle.exitMassAveragedPressure),
                        'massFlow': float(nozzle.exitMassFlux) * throatRadius**2,
                        'exitMassClosure': float(nozzle.exitMassClosure),
                        'chokedMassFlow': _chokedMassFlow(chamberPressure, throatArea, gamma, gasConstant,
                                                          stagnationTemperature),
                        'engineMassFlow': float(nozzle.engineMassFlow)},
    }

def loadReference(refresh: bool = False) -> dict:

    '''The NOVA reference, solved and written when it is missing or a refresh is asked for.'''

    if refresh or not os.path.isfile(referencePath):
        reference = solveNova()
        os.makedirs(os.path.dirname(referencePath), exist_ok = True)
        with open(referencePath, 'w', encoding = 'utf-8') as handle:
            json.dump(reference, handle, separators = (',', ':'))
        print(f'wrote {os.path.relpath(referencePath, repositoryRoot)}')

    if refresh or not os.path.isfile(stylePath):
        sys.path.insert(0, os.path.join(repositoryRoot, 'src'))
        from NOVA import palette
        with open(stylePath, 'w', encoding = 'utf-8') as handle:
            json.dump({'colors': palette.colors('dark'), 'categories': palette.categories('dark'),
                       'colormaps': {name: list(stops) for name, stops in palette.colormapStops['dark'].items()}},
                      handle, indent = 2)

    with open(referencePath, encoding = 'utf-8') as handle:
        return json.load(handle)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The mesh -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _cellsBetween(length: float, startSize: float, endSize: float) -> tuple:

    '''

    Cells and expansion ratio for a geometric spacing from `startSize` to `endSize` over `length`.

    Returns:
    --------
    tuple : (cells, expansion), the expansion being the last cell over the first, as blockMesh takes it

    '''

    if abs(endSize - startSize) < 1e-9 * max(startSize, endSize):
        return max(2, round(length / startSize)), 1.0
    cells = max(2, round(length * math.log(endSize / startSize) / (endSize - startSize)))

    return cells, endSize / startSize

def blockStations(geometry: dict) -> list:

    '''

    Indices of the wall points the blocks are split at: the injector, the end of the chamber barrel,
    the throat, the exit, and every point where the radius has changed by `blockRadiusRatio` since
    the last split.

    '''

    wallR = np.asarray(geometry['wallR'])
    barrelEnd, throat, last = geometry['barrelEndIndex'], geometry['throatIndex'], len(wallR) - 1

    stations = [0] + ([barrelEnd] if barrelEnd > 0 else [])
    for start, end in ((stations[-1], throat), (throat, last)):
        reference = wallR[start]
        for index in range(start + 1, end):
            change = max(wallR[index] / reference, reference / wallR[index])
            # A split within a few points of the next fixed station would leave a sliver block
            if change >= blockRadiusRatio and end - index > 10:
                stations.append(index)
                reference = wallR[index]
        stations.append(end)

    return stations

def blockMeshDict(reference: dict, radialCells: int) -> tuple:

    '''

    The wedge mesh: one row of blocks from the axis to the wall, split along the nozzle at
    `blockStations`, with the wall followed as a polyline through every contour point inside each
    block. The axis is a collapsed edge of each block, so its cells are prisms.

    Returns:
    --------
    tuple : (dictionary text, cell count)

    '''

    geometry = reference['geometry']
    wallX, wallR = np.asarray(geometry['wallX']), np.asarray(geometry['wallR'])
    half = math.radians(wedgeAngle / 2.0)
    stations = blockStations(geometry)

    def wallPoint(index: int, sign: float) -> tuple:
        radius = radialScale * wallR[index]
        return (wallX[index], radius * math.cos(half), sign * radius * math.sin(half))

    # Vertices: at every station, the axis point and the wall point either side of the wedge
    vertices, axisIndex, lowIndex, highIndex = [], [], [], []
    for station in stations:
        axisIndex.append(len(vertices)); vertices.append((wallX[station], 0.0, 0.0))
        lowIndex.append(len(vertices)); vertices.append(wallPoint(station, -1.0))
        highIndex.append(len(vertices)); vertices.append(wallPoint(station, 1.0))

    blocks, edges, cells = [], [], 0
    for k in range(len(stations) - 1):
        start, end = stations[k], stations[k + 1]
        # Cells cellAspect times as long as they are tall, from the radius at each end
        axialCells, expansion = _cellsBetween(wallX[end] - wallX[start], cellAspect * wallR[start] / radialCells,
                                              cellAspect * wallR[end] / radialCells)
        cells += axialCells * radialCells
        a0, a1, l0, l1, h0, h1 = axisIndex[k], axisIndex[k + 1], lowIndex[k], lowIndex[k + 1], highIndex[k], highIndex[k + 1]
        blocks.append(f'    hex ({a0} {a1} {l1} {l0} {a0} {a1} {h1} {h0}) ({axialCells} {radialCells} 1) '
                      f'simpleGrading ({expansion:.6f} 1 1)')
        for first, second, sign in ((l0, l1, -1.0), (h0, h1, 1.0)):
            points = ' '.join('({:.9f} {:.9f} {:.9f})'.format(*wallPoint(index, sign)) for index in range(start + 1, end))
            edges.append(f'    polyLine {first} {second} ({points})')

    # Faces are listed so their normals point out of the domain
    spans = range(len(stations) - 1)
    patches = {
        'inlet':  ('patch', [f'({axisIndex[0]} {highIndex[0]} {lowIndex[0]} {axisIndex[0]})']),
        'outlet': ('patch', [f'({axisIndex[-1]} {lowIndex[-1]} {highIndex[-1]} {axisIndex[-1]})']),
        'wall':   ('wall', [f'({lowIndex[k]} {highIndex[k]} {highIndex[k + 1]} {lowIndex[k + 1]})' for k in spans]),
        'front':  ('wedge', [f'({axisIndex[k]} {axisIndex[k + 1]} {highIndex[k + 1]} {highIndex[k]})' for k in spans]),
        'back':   ('wedge', [f'({axisIndex[k]} {lowIndex[k]} {lowIndex[k + 1]} {axisIndex[k + 1]})' for k in spans]),
    }
    boundary = '\n'.join(f'    {name}\n    {{\n        type {kind};\n        faces\n        (\n'
                         + '\n'.join(f'            {face}' for face in faces) + '\n        );\n    }'
                         for name, (kind, faces) in patches.items())

    text = (_header('dictionary', 'blockMeshDict', 'system')
            + f'// {len(stations) - 1} blocks, {radialCells} cells across the radius. Wall points sit {radialScale:.6f}\n'
            + '// times the contour radius out, which gives the flat-faced wedge the flow area of the sector.\n'
            + '// The axis is a collapsed edge of every block, so its points are merged rather than its faces.\n'
            + 'mergeType points;\n\nscale 1;\n\nvertices\n(\n'
            + '\n'.join('    ({:.9f} {:.9f} {:.9f})'.format(*vertex) for vertex in vertices)
            + '\n);\n\nblocks\n(\n' + '\n'.join(blocks) + '\n);\n\nedges\n(\n' + '\n'.join(edges)
            + '\n);\n\nboundary\n(\n' + boundary + '\n);\n\nmergePatchPairs\n(\n);\n')

    return text, cells

#--------------------------------------------------------------------------------------------------------------------------#
# -- The case files -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _header(fileClass: str, name: str, location: str) -> str:

    return ('/*--------------------------------*- C++ -*----------------------------------*\\\n'
            '| Written by NOVA validation/openFoam/makeNozzleCase.py                       |\n'
            '\\*---------------------------------------------------------------------------*/\n'
            'FoamFile\n{\n    version     2.0;\n    format      ascii;\n'
            f'    class       {fileClass};\n    location    "{location}";\n    object      {name};\n}}\n'
            '// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n')

def thermophysicalProperties(reference: dict) -> str:

    gas = reference['gas']

    return (_header('dictionary', 'thermophysicalProperties', 'constant')
            + '// A calorically perfect gas at NOVA\'s chamber ratio of specific heats and gas constant, the gas\n'
            + '// its method of characteristics solves in. Zero viscosity reduces rhoCentralFoam to the Euler\n'
            + '// equations.\n'
            + 'thermoType\n{\n    type            hePsiThermo;\n    mixture         pureMixture;\n'
            + '    transport       const;\n    thermo          hConst;\n    equationOfState perfectGas;\n'
            + '    specie          specie;\n    energy          sensibleInternalEnergy;\n}\n\n'
            + 'mixture\n{\n    specie\n    {\n'
            + f'        molWeight       {gas["molecularWeight"]:.9g};    // [kg/kmol], R = {gas["gasConstant"]:.6f} J/kg K\n'
            + '    }\n    thermodynamics\n    {\n'
            + f'        Cp              {gas["specificHeat"]:.9g};    // [J/kg K], gamma = {gas["gamma"]:.6f}\n'
            + '        Hf              0;\n    }\n    transport\n    {\n        mu              0;\n'
            + '        Pr              1;\n    }\n}\n')

def fieldFile(name: str, reference: dict) -> str:

    '''The boundary conditions of one field. The interior is written by the initialization.'''

    gas = reference['gas']
    gamma, chamberPressure, stagnationTemperature = gas['gamma'], gas['chamberPressure'], gas['stagnationTemperature']
    wedges = ('    front\n    {\n        type            wedge;\n    }\n'
              '    back\n    {\n        type            wedge;\n    }\n')

    if name == 'p':
        return (_header('volScalarField', 'p', '0') + 'dimensions      [1 -1 -2 0 0 0 0];\n\n'
                + f'internalField   uniform {chamberPressure};\n\nboundaryField\n{{\n'
                + '    // The chamber\'s stagnation pressure, the static pressure following from the local velocity\n'
                + '    inlet\n    {\n        type            totalPressure;\n        rho             none;\n'
                + f'        psi             thermo:psi;\n        gamma           {gamma:.9g};\n'
                + f'        p0              uniform {chamberPressure};\n        value           uniform {chamberPressure};\n    }}\n'
                + '    // Supersonic outflow: nothing travels back upstream through the exit plane\n'
                + '    outlet\n    {\n        type            zeroGradient;\n    }\n'
                + '    wall\n    {\n        type            zeroGradient;\n    }\n' + wedges + '}\n')
    if name == 'T':
        return (_header('volScalarField', 'T', '0') + 'dimensions      [0 0 0 1 0 0 0];\n\n'
                + f'internalField   uniform {stagnationTemperature};\n\nboundaryField\n{{\n'
                + '    inlet\n    {\n        type            totalTemperature;\n'
                + f'        gamma           {gamma:.9g};\n        T0              uniform {stagnationTemperature};\n'
                + f'        value           uniform {stagnationTemperature};\n    }}\n'
                + '    outlet\n    {\n        type            zeroGradient;\n    }\n'
                + '    wall\n    {\n        type            zeroGradient;\n    }\n' + wedges + '}\n')

    return (_header('volVectorField', 'U', '0') + 'dimensions      [0 1 -1 0 0 0 0];\n\n'
            + 'internalField   uniform (0 0 0);\n\nboundaryField\n{\n'
            + '    inlet\n    {\n        type            zeroGradient;\n    }\n'
            + '    outlet\n    {\n        type            zeroGradient;\n    }\n'
            + '    // Inviscid: the flow slides along the wall\n'
            + '    wall\n    {\n        type            slip;\n    }\n' + wedges + '}\n')

def controlDict(reference: dict, endTime: float, writes: int) -> str:

    geometry = reference['geometry']
    # The axis line sits a hair off the axis and inside each end, so every sample falls in a cell
    inset = 1e-4 * geometry['throatRadius']
    history = ('        type            surfaceFieldValue;\n        libs            (fieldFunctionObjects);\n'
               '        writeControl    timeStep;\n        writeInterval   20;\n        log             false;\n'
               '        writeFields     false;\n        regionType      patch;\n')
    sampled = '(p T U Ma pMean TMean UMean)'

    return (_header('dictionary', 'controlDict', 'system')
            + 'application     rhoCentralFoam;\n\nstartFrom       latestTime;\n\nstartTime       0;\n\nstopAt          endTime;\n\n'
            + '// Several passes of the slow chamber flow, the last part of the nozzle to settle\n'
            + f'endTime         {endTime:g};\n\ndeltaT          1e-9;\n\nwriteControl    adjustable;\n\n'
            + f'writeInterval   {endTime / writes:g};\n\npurgeWrite      0;\n\n'
            + '// ASCII, so the initialization and the comparison read the fields without OpenFOAM\n'
            + 'writeFormat     ascii;\n\nwritePrecision  10;\n\nwriteCompression off;\n\ntimeFormat      general;\n\n'
            + 'timePrecision   8;\n\nrunTimeModifiable true;\n\nadjustTimeStep  yes;\n\n'
            + '// Counts the wedge faces, which carry no flux: see makeNozzleCase.py\n'
            + f'maxCo           {maxCourant:g};\n\nmaxDeltaT       1;\n\n'
            + 'functions\n{\n'
            + '    Ma\n    {\n        type            MachNo;\n        libs            (fieldFunctionObjects);\n'
            + '        executeControl  writeTime;\n        writeControl    writeTime;\n    }\n\n'
            + '    // The chamber\'s radial acoustic modes are not damped by an inviscid solution and ring for as\n'
            + '    // long as the run lasts, at a few tenths of a percent of the mass flow. The comparison reads\n'
            + '    // the mean over the second half of the run.\n'
            + '    average\n    {\n        type            fieldAverage;\n        libs            (fieldFunctionObjects);\n'
            + f'        timeStart       {endTime * (1.0 - averagedFraction):g};\n        writeControl    writeTime;\n'
            + '        fields\n        (\n'
            + ''.join(f'            {field}\n            {{\n                mean        on;\n                prime2Mean  off;\n'
                      f'                base        time;\n            }}\n' for field in ('p', 'T', 'U'))
            + '        );\n    }\n\n'
            + '    // Mass through each end, and the momentum and pressure forces on the exit plane, for steadiness\n'
            + f'    inletFlow\n    {{\n{history}        name            inlet;\n'
            + '        operation       sum;\n        fields          (phi);\n    }\n\n'
            + f'    outletFlow\n    {{\n{history}        name            outlet;\n'
            + '        operation       sum;\n        fields          (phi);\n    }\n\n'
            + f'    outletMomentum\n    {{\n{history}        name            outlet;\n'
            + '        operation       weightedSum;\n        weightField     phi;\n        fields          (U);\n    }\n\n'
            + f'    outletPressure\n    {{\n{history}        name            outlet;\n'
            + '        operation       areaIntegrate;\n        fields          (p);\n    }\n\n'
            + '    axis\n    {\n        type            sets;\n        libs            (sampling);\n'
            + '        writeControl    writeTime;\n        setFormat       raw;\n        interpolationScheme cellPoint;\n'
            + f'        fields          {sampled};\n        sets\n        {{\n'
            + '            axis\n            {\n                type    uniform;\n                axis    xyz;\n'
            + f'                start   ({geometry["injectorX"] + inset:.9f} {inset:.9f} 0);\n'
            + f'                end     ({geometry["exitX"] - inset:.9f} {inset:.9f} 0);\n'
            + '                nPoints 4000;\n            }\n        }\n    }\n\n'
            + '    // Face values on the wall and the exit plane: zero gradient, so each is its cell\'s value\n'
            + '    patches\n    {\n        type            surfaces;\n        libs            (sampling);\n'
            + '        writeControl    writeTime;\n        surfaceFormat   raw;\n'
            + f'        fields          {sampled};\n        surfaces\n        {{\n'
            + '            wall\n            {\n                type        patch;\n                patches     (wall);\n'
            + '                interpolate false;\n            }\n'
            + '            outlet\n            {\n                type        patch;\n                patches     (outlet);\n'
            + '                interpolate false;\n            }\n        }\n    }\n}\n')

def fvSchemes() -> str:

    return (_header('dictionary', 'fvSchemes', 'system')
            + '// The Kurganov-Tadmor central scheme with van Leer limited reconstruction, as the rhoCentralFoam\n'
            + '// tutorials run it\n'
            + 'fluxScheme          Kurganov;\n\nddtSchemes\n{\n    default         Euler;\n}\n\n'
            + 'gradSchemes\n{\n    default         Gauss linear;\n}\n\n'
            + 'divSchemes\n{\n    default         none;\n    div(tauMC)      Gauss linear;\n}\n\n'
            + 'laplacianSchemes\n{\n    default         Gauss linear corrected;\n}\n\n'
            + 'interpolationSchemes\n{\n    default         linear;\n    reconstruct(rho) vanLeer;\n'
            + '    reconstruct(U)  vanLeerV;\n    reconstruct(T)  vanLeer;\n}\n\n'
            + 'snGradSchemes\n{\n    default         corrected;\n}\n')

def fvSolution() -> str:

    return (_header('dictionary', 'fvSolution', 'system')
            + 'solvers\n{\n    "(rho|rhoU|rhoE)"\n    {\n        solver          diagonal;\n    }\n\n'
            + '    U\n    {\n        solver          smoothSolver;\n        smoother        GaussSeidel;\n'
            + '        nSweeps         2;\n        tolerance       1e-10;\n        relTol          0;\n    }\n\n'
            + '    e\n    {\n        $U;\n    }\n}\n')

def decomposeParDict(processors: int) -> str:

    return (_header('dictionary', 'decomposeParDict', 'system')
            + f'numberOfSubdomains {processors};\n\nmethod          scotch;\n')

def turbulenceProperties() -> str:

    return _header('dictionary', 'turbulenceProperties', 'constant') + 'simulationType  laminar;\n'

allrun = '''#!/bin/sh
# ./Allrun                 start from the quasi one-dimensional flow
# ./Allrun <source case>   start from another grid's converged solution, mapped onto this one
cd "${0%/*}" || exit                                # Run from this directory
. ${WM_PROJECT_DIR:?}/bin/tools/RunFunctions        # Tutorial run functions
#------------------------------------------------------------------------------

restore0Dir
runApplication blockMesh
runApplication checkMesh

# The cell centers, which the initialization and the comparison both read
runApplication postProcess -func writeCellCentres -time 0

if [ -n "$1" ]
then
    runApplication mapFields "$1" -consistent -sourceTime latestTime
else
    # The run then settles the two-dimensional flow rather than the start-up of the whole nozzle
    runApplication -s initialize python3 scripts/initializeFromQuasi1D.py .
fi

runApplication decomposePar
runParallel $(getApplication)
runApplication reconstructPar -latestTime

runApplication -s compare python3 scripts/compareWithNova.py .
touch case.foam

#------------------------------------------------------------------------------
'''

allclean = '''#!/bin/sh
cd "${0%/*}" || exit                                # Run from this directory
. ${WM_PROJECT_DIR:?}/bin/tools/CleanFunctions      # Tutorial clean functions
#------------------------------------------------------------------------------

cleanCase0
rm -rf comparison case.foam

#------------------------------------------------------------------------------
'''

def writeCase(reference: dict, resolution: str, output: str, processors: int, endTime: float, writes: int) -> None:

    '''Write every file of the case, and the scripts and reference it runs with.'''

    radialCells = resolutions[resolution]
    meshText, cells = blockMeshDict(reference, radialCells)

    files = {
        'system/blockMeshDict': meshText,
        'system/controlDict': controlDict(reference, endTime, writes),
        'system/fvSchemes': fvSchemes(),
        'system/fvSolution': fvSolution(),
        'system/decomposeParDict': decomposeParDict(processors),
        'constant/thermophysicalProperties': thermophysicalProperties(reference),
        'constant/turbulenceProperties': turbulenceProperties(),
        '0.orig/p': fieldFile('p', reference),
        '0.orig/T': fieldFile('T', reference),
        '0.orig/U': fieldFile('U', reference),
        'Allrun': allrun,
        'Allclean': allclean,
    }
    for name, text in files.items():
        path = os.path.join(output, name)
        os.makedirs(os.path.dirname(path), exist_ok = True)
        with open(path, 'w', encoding = 'utf-8', newline = '\n') as handle:
            handle.write(text)

    os.makedirs(os.path.join(output, 'scripts'), exist_ok = True)
    for script in ('initializeFromQuasi1D.py', 'compareWithNova.py', 'gridConvergence.py'):
        shutil.copyfile(os.path.join(here, script), os.path.join(output, 'scripts', script))
    os.makedirs(os.path.join(output, 'reference'), exist_ok = True)
    shutil.copyfile(referencePath, os.path.join(output, 'reference', 'novaNozzle.json'))
    shutil.copyfile(stylePath, os.path.join(output, 'reference', 'style.json'))
    with open(os.path.join(output, 'reference', 'case.json'), 'w', encoding = 'utf-8') as handle:
        json.dump({'resolution': resolution, 'radialCells': radialCells, 'cells': cells, 'wedgeAngle': wedgeAngle,
                   'radialScale': radialScale, 'endTime': endTime,
                   'averageStart': endTime * (1.0 - averagedFraction)}, handle, indent = 2)

    print(f'wrote {output}: {resolution} grid, {cells} cells, {radialCells} across the radius')

def main() -> None:

    parser = argparse.ArgumentParser(description = 'Write the axisymmetric OpenFOAM case of the NOVA nozzle.')
    parser.add_argument('--resolution', choices = list(resolutions), default = 'medium')
    parser.add_argument('--output', default = None, help = 'case folder; cases/novaNozzle2D-<resolution> by default')
    parser.add_argument('--processors', type = int, default = 4)
    parser.add_argument('--end-time', type = float, default = None,
                        help = 'physical time to run [s]; endTimes[resolution] by default')
    parser.add_argument('--writes', type = int, default = 4, help = 'times the solution is written over the run')
    parser.add_argument('--refresh', action = 'store_true', help = 'solve NOVA again before writing the case')
    arguments = parser.parse_args()

    reference = loadReference(arguments.refresh)
    output = arguments.output or os.path.join(here, 'cases', f'novaNozzle2D-{arguments.resolution}')
    writeCase(reference, arguments.resolution, output, arguments.processors,
              arguments.end_time or endTimes[arguments.resolution], arguments.writes)

if __name__ == '__main__':
    main()
