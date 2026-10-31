# -- NOVA Plume: OpenFOAM Case Generator -- #

'''

Write an axisymmetric OpenFOAM case of the exhaust plume of NOVA's shipped nozzle, and the NOVA
solution it is checked against.

NOVA describes the plume two ways. `stationMarch.solveStationField` marches the boundary and the
interior from the nozzle's exit plane, isentropically, for two lip radii; `plume.solvePlumeStructure`
places the shock cell length, the Mach disk and an assumed boundary shape from published
correlations. This case solves the same jet with the Euler equations and captures the shocks
neither of them carries.

The case starts from the exit station NOVA's march starts from: the same radii, Mach numbers and
flow angles, at NOVA's chamber ratio of specific heats and gas constant. Both methods then solve the
same initial-value problem, so a difference between the march and the case is a difference of
method. The station is the nozzle's exit plane, from the wall to the axis, so the station radius is
the lip radius. The jet expands into the shipped ambient of 5 kPa. The ambient gas is the
exhaust gas at rest at 216.65 K, the standard atmosphere's temperature at that pressure; an inviscid
steady jet depends on the ambient's pressure alone, so its temperature and composition only mark
where the jet ends.

The domain is a 5 degree wedge from the exit plane downstream. The exit plane inside the station
radius is a supersonic inflow, every field fixed; outside it is a slip wall standing for the
nozzle's base. The far radial boundary and the downstream boundary let gas in or out, pass outgoing
waves through and relax the pressure toward the ambient's. A boundary held at a fixed pressure
reflects every wave instead, and the still ambient, cold and wide, then rings in its radial
acoustic modes, with a period near 16 ms here, moving the pressure the jet expands into by a fifth
of itself.

The solution is written to `reference/novaPlume.json`: the gas, the exit station, the march at the
shipped reach and at a longer one, and the correlated structure as NOVA reports it, with its
scalars re-evaluated independently from NOVA's functions as a check on the reported ones.

Run it with the Python NOVA is installed in, from the NOVA root:

    python validation/openFoam/makePlumeCase.py                          # medium grid
    python validation/openFoam/makePlumeCase.py --resolution fine
    python validation/openFoam/makePlumeCase.py --refresh                # re-solve NOVA first

The case is written to `validation/openFoam/cases/novaPlume2D-<resolution>/` unless `--output`
says otherwise, and carries everything it runs with. The coarse grid starts from the ambient with
the exit flow filling a column downstream of the exit plane; each finer grid starts from the next
coarser grid's solution, `./Allrun ../novaPlume2D-coarse`. See plume.md.

Author: Sean Bowman

'''

import argparse
import json
import math
import os
import shutil
import sys

import numpy as np

import makeNozzleCase as nozzleCase
from makeNozzleCase import _cellsBetween, _header, _rounded, radialScale, wedgeAngle

here = os.path.dirname(os.path.abspath(__file__))
repositoryRoot = os.path.dirname(os.path.dirname(here))
referencePath = os.path.join(here, 'reference', 'novaPlume.json')

# The ambient's temperature: the U.S. Standard Atmosphere (1976) holds 216.65 K from 11 to 20 km,
# and reaches 5 kPa at about 20.6 km, where it is 217.3 K. The jet does not depend on it.
ambientTemperature = 216.65   # [K]

# The march is run a second time to this reach, five times the shipped one, to show where it parts
# from the case. NOVA calls a march trustworthy within one percent of mass drift, which the shipped
# nozzle holds to about two lip radii.
extendedReach = 10.0          # [-], lip radii

# Cells across the station radius at each resolution, each level twice the last. Cells are square
# out to `uniformLength` and `uniformRadius`, which hold the lip's expansion fan and the jet
# boundary, and grow geometrically beyond.
resolutions = {'coarse': 10, 'medium': 20, 'fine': 40}

# The domain, in station radii from the exit plane and the axis
domain = {
    'length': 30.0,           # to the outlet
    'uniformLength': 4.0,     # square cells to here
    'axialGrowth': 4.0,       # last axial cell over the first
    'radius': 8.0,            # to the far field
    'uniformRadius': 3.0,     # square cells to here
    'radialGrowth': 6.0,      # outermost radial cell over the first
}

# Physical time each grid runs [s]. The coarse grid starts from a column of exit flow and needs the
# ambient's response to it to leave the domain; each finer grid starts from the coarser solution.
endTimes = {'coarse': 60e-3, 'medium': 10e-3, 'fine': 5e-3}

#--------------------------------------------------------------------------------------------------------------------------#
# -- The NOVA solution -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _stationMassFlow(radius: np.ndarray, mach: np.ndarray, angle: np.ndarray, gas: dict) -> float:

    '''Axial mass flow through a station [kg/s], by the trapezoid NOVA's `stationMassFlux` uses.'''

    gamma, gasConstant = gas['gamma'], gas['gasConstant']
    stagnation = 1.0 + 0.5 * (gamma - 1.0) * mach**2
    temperature = gas['stagnationTemperature'] / stagnation
    density = gas['chamberPressure'] * stagnation**(-gamma / (gamma - 1.0)) / (gasConstant * temperature)
    flux = density * mach * np.sqrt(gamma * gasConstant * temperature) * np.cos(angle) * radius

    return float(2.0 * math.pi * np.trapezoid(flux, radius))

def _correlations(structure, gamma: float, exitMach: float, lipMach: float) -> dict:

    '''

    NOVA's correlated plume structure at a given ratio of specific heats.

    The scalars `plume.solvePlumeStructure` derives from the exit and fully expanded states,
    re-evaluated with NOVA's own functions from the exit Mach number handed in, the one-dimensional
    one at the area ratio. The first shock on the axis is the Mach disk when the exit pressure ratio
    is above the onset, and the regular reflection point otherwise.

    '''

    from NOVA.gasDynamics import machFromPressureRatio, prandtlMeyerAngle
    from NOVA.plume import (fullyExpandedDiameter, machReflectionOnset, packCellCoefficient, prandtlCellCoefficient,
                            regularReflectionLocation, shockCellLength, supersonicMachDiskDiameter,
                            supersonicMachDiskLocation)

    jetMach = machFromPressureRatio(structure.nozzlePressureRatio, gamma)
    jetDiameter = fullyExpandedDiameter(structure.exitDiameter, exitMach, jetMach, gamma)
    turn = prandtlMeyerAngle(jetMach, gamma) - prandtlMeyerAngle(lipMach, gamma)
    exitPressureRatio = (structure.nozzlePressureRatio
                         * (1.0 + 0.5 * (gamma - 1.0) * exitMach**2)**(-gamma / (gamma - 1.0)))
    onset = machReflectionOnset(exitMach, gamma)
    diskPresent = exitPressureRatio > onset
    if diskPresent:
        axisShock = supersonicMachDiskLocation(structure.exitDiameter, exitMach, exitPressureRatio, gamma)
    else:
        axisShock = regularReflectionLocation(0.5 * structure.exitDiameter, exitMach, exitPressureRatio)

    return {
        'gamma': gamma, 'exitMach': exitMach, 'lipMach': lipMach, 'exitPressureRatio': exitPressureRatio,
        'fullyExpandedMach': jetMach, 'fullyExpandedDiameter': jetDiameter,
        'shockCellLength': shockCellLength(jetDiameter, jetMach, prandtlCellCoefficient),
        'cellLengthPack': shockCellLength(jetDiameter, jetMach, packCellCoefficient),
        'initialTurnAngle': structure.lipWallAngle + turn,
        'machReflectionOnset': onset, 'machDiskPresent': bool(diskPresent),
        'machDiskX': structure.lipX + axisShock if diskPresent else 0.0,
        'machDiskDiameter': supersonicMachDiskDiameter(structure.exitDiameter, exitPressureRatio, onset),
        'axisShockX': structure.lipX + axisShock,
    }

def _march(field, gas: dict) -> dict:

    '''A solved plume field as plain data, with the mass flow through every station.'''

    stations, points = field.gridShape
    grid = {key: np.asarray(value, dtype = float).reshape(stations, points)
            for key, value in (('x', field.nodeX), ('r', field.nodeR), ('mach', field.nodeMach),
                               ('flowAngle', field.nodeFlowAngle), ('pressure', field.nodePressure))}
    massFlow = np.array([_stationMassFlow(grid['r'][k], grid['mach'][k], grid['flowAngle'][k], gas)
                         for k in range(stations)])

    return {'grid': grid, 'massFlow': massFlow, 'boundaryX': np.asarray(field.boundaryX, dtype = float),
            'boundaryR': np.asarray(field.boundaryR, dtype = float), 'solvedTo': float(field.solvedTo),
            'stop': field.stop, 'massDriftWorst': float(field.massDriftWorst),
            'trustworthy': bool(field.trustworthy), 'notes': list(field.notes)}

def solveNova() -> dict:

    '''

    Solve the shipped nozzle with its plume, flow only, and gather what the case is built from and
    checked against.

    Returns:
    --------
    dict : the reference, ready to write as JSON

    '''

    with open(os.path.join(repositoryRoot, 'src', 'NOVA', 'assets', 'NOVANozzle.json'), encoding = 'utf-8') as handle:
        config = json.load(handle)
    config.pop('_comment', None)

    # The plume reads the contour, its characteristic mesh and the near-wall state; nothing
    # switched off here reaches it
    config.update(filename = 'openFoamPlumeReference', makeCoolingChannels = False, makeInletVolute = False,
                  makeOutletVolute = False, filmCooling = False, makeRadiativeExtension = False,
                  export = 'off', plotsEnabled = 'off')
    nozzle = nozzleCase._solve(config, 'plume')
    structure, field = nozzle.nozzlePlumeStructure, nozzle.nozzlePlumeField
    if field is None or not field.solved:
        raise RuntimeError('NOVA did not march the plume at the shipped settings.')

    ambientPressure = float(config['plumeAmbientPressure'])
    gamma, gasConstant = float(nozzle.chamberGamma), float(nozzle.chamberRGasConstant)
    gas = {'gamma': gamma, 'gasConstant': gasConstant,
           'stagnationTemperature': float(nozzle.chamberStagnationTemperature),
           'chamberPressure': float(nozzle.chamberPressure), 'specificHeat': gamma * gasConstant / (gamma - 1.0),
           'molecularWeight': nozzleCase.universalGasConstant / gasConstant,
           'ambientPressure': ambientPressure, 'ambientTemperature': ambientTemperature,
           'correlationGamma': float(structure.gamma)}

    shipped = _march(field, gas)
    station = {key: value[0] for key, value in shipped['grid'].items()}
    longer = _march(nozzle.plumeField(ambientPressure, reach = extendedReach), gas)

    throatRadius = float(nozzle.nozzleScalingFactor)
    wallX, wallR = np.asarray(nozzle.xNozzleWall, dtype = float), np.asarray(nozzle.rNozzleWall, dtype = float)

    # The one-dimensional exit Mach number at the chamber gas, for the correlations evaluated in it.
    # The area ratio is the lip's against the throat radius; the resampled wall's smallest radius
    # misses the throat.
    from NOVA.gasDynamics import machFromAreaRatio
    chamberExitMach = float(machFromAreaRatio((wallR[-1] / throatRadius)**2, gamma))

    def marchOut(march: dict, nodes: bool) -> dict:
        out = {'boundaryX': _rounded(march['boundaryX']), 'boundaryR': _rounded(march['boundaryR']),
               'stationX': _rounded(march['grid']['x'][:, 0]), 'axisMach': _rounded(march['grid']['mach'][:, 0]),
               'axisPressure': _rounded(march['grid']['pressure'][:, 0]),
               'boundaryMach': _rounded(march['grid']['mach'][:, -1]),
               'massFlow': _rounded(march['massFlow']), 'solvedTo': march['solvedTo'], 'stop': march['stop'],
               'massDriftWorst': march['massDriftWorst'], 'trustworthy': march['trustworthy'],
               'notes': march['notes']}
        if nodes:
            # Every station is a plane, so x is `stationX`; pressure follows from the Mach number
            out['gridShape'] = list(march['grid']['x'].shape)
            out.update({key: _rounded(march['grid'][key], 7) for key in ('r', 'mach', 'flowAngle')})
        return out

    return {
        'description': ('NOVA\'s shipped nozzle and its exhaust plume at the shipped ambient: the station march from '
                        'the exit plane and the correlated structure'),
        'config': {key: config[key] for key in ('Fuel', 'Oxidizer', 'OFRatio', 'chamberPressure', 'thrust',
                                                'expansionRatio', 'divergingSectionType', 'lengthFraction',
                                                'numCharacteristics', 'numContourPoints', 'plumeAmbientPressure',
                                                'plumeFieldReach')},
        'gas': gas,
        'nozzle': {'wallX': _rounded(wallX), 'wallR': _rounded(wallR), 'throatRadius': throatRadius,
                   'lipX': float(wallX[-1]), 'lipRadius': float(wallR[-1]),
                   'exitMassFlow': float(nozzle.exitMassFlux) * throatRadius**2},
        'station': {'x': float(station['x'][0]), 'r': _rounded(station['r']), 'mach': _rounded(station['mach']),
                    'flowAngle': _rounded(station['flowAngle']), 'pressure': _rounded(station['pressure']),
                    'radius': float(station['r'][-1]), 'massFlow': float(shipped['massFlow'][0])},
        'march': {**marchOut(shipped, True), 'reach': float(config['plumeFieldReach']),
                  'lipPressureRatio': float(field.lipPressureRatio), 'marchBoundaryMach': float(field.boundaryMach),
                  'lipTurnAngle': float(field.lipTurnAngle)},
        'extendedMarch': {**marchOut(longer, False), 'reach': extendedReach},
        'structure': {
            'reported': {'gamma': float(structure.gamma), 'jetType': structure.jetType,
                         'exitMach': float(structure.exitMach), 'exitPressure': float(structure.exitPressure),
                         'exitPressureRatio': float(structure.exitPressureRatio),
                         'nozzlePressureRatio': float(structure.nozzlePressureRatio),
                         'lipMach': float(structure.lipMach), 'lipPressure': float(structure.lipPressure),
                         'lipWallAngle': float(structure.lipWallAngle),
                         'fullyExpandedMach': float(structure.fullyExpandedMach),
                         'fullyExpandedDiameter': float(structure.fullyExpandedDiameter),
                         'shockCellLength': float(structure.shockCellLength),
                         'cellLengthPack': float(structure.cellLengthPack),
                         'initialTurnAngle': float(structure.initialTurnAngle),
                         'machReflectionOnset': float(structure.machReflectionOnset),
                         'machDiskPresent': bool(structure.machDiskPresent), 'machDiskX': float(structure.machDiskX),
                         'machDiskDiameter': float(structure.machDiskDiameter),
                         'axisShockX': float(structure.axisShockX),
                         'boundaryAmplitudeLimited': bool(structure.boundaryAmplitudeLimited),
                         'boundaryX': _rounded(structure.boundaryX), 'boundaryR': _rounded(structure.boundaryR),
                         'notes': list(structure.notes)},
            'chamberGas': _correlations(structure, gamma, chamberExitMach, float(station['mach'][-1])),
        },
    }

def loadReference(refresh: bool = False) -> dict:

    '''The NOVA reference, solved and written when it is missing or a refresh is asked for.'''

    if refresh or not os.path.isfile(referencePath):
        os.environ.setdefault('NOVA_HEADLESS', '1')
        sys.path.insert(0, os.path.join(repositoryRoot, 'src'))
        reference = solveNova()
        os.makedirs(os.path.dirname(referencePath), exist_ok = True)
        with open(referencePath, 'w', encoding = 'utf-8') as handle:
            json.dump(reference, handle, separators = (',', ':'))
        print(f'wrote {os.path.relpath(referencePath, repositoryRoot)}')

    # The figure palette is the one the nozzle case writes
    nozzleCase.loadReference(refresh = False)

    with open(referencePath, encoding = 'utf-8') as handle:
        return json.load(handle)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The mesh -- #
#--------------------------------------------------------------------------------------------------------------------------#

def bands(cellsPerRadius: int, extent: dict) -> tuple:

    '''

    Block edges and cell distributions along the axis and the radius.

    Returns:
    --------
    tuple : (axial edges, axial cells and expansions, radial edges, radial cells and expansions), the
            edges in station radii
    '''

    size = 1.0 / cellsPerRadius
    axialEdges = [0.0, extent['uniformLength'], extent['length']]
    axial = [(round(extent['uniformLength'] * cellsPerRadius), 1.0),
             _cellsBetween(extent['length'] - extent['uniformLength'], size, extent['axialGrowth'] * size)]
    radialEdges = [0.0, 1.0, extent['uniformRadius'], extent['radius']]
    radial = [(cellsPerRadius, 1.0), (round((extent['uniformRadius'] - 1.0) * cellsPerRadius), 1.0),
              _cellsBetween(extent['radius'] - extent['uniformRadius'], size, extent['radialGrowth'] * size)]

    return axialEdges, axial, radialEdges, radial

def blockMeshDict(reference: dict, cellsPerRadius: int, extent: dict) -> tuple:

    '''

    The wedge mesh: three bands of blocks out from the axis (the jet as it leaves the exit plane,
    the region it expands into, and the ambient beyond), each split once along the axis where the
    square cells end. The innermost band's axis is a collapsed edge, so its cells are prisms.

    Returns:
    --------
    tuple : (dictionary text, cell count)

    '''

    station = reference['station']
    startX, unit = station['x'], station['radius']
    half = math.radians(wedgeAngle / 2.0)
    axialEdges, axial, radialEdges, radial = bands(cellsPerRadius, extent)

    # Vertices: the axis point at every axial edge, and the points either side of the wedge at every
    # other radial edge. Radii sit radialScale out, which gives the flat-faced wedge the sector's area.
    vertices, axisIndex, lowIndex, highIndex = [], {}, {}, {}
    for i, edgeX in enumerate(axialEdges):
        x = startX + edgeX * unit
        axisIndex[i] = len(vertices); vertices.append((x, 0.0, 0.0))
        for j, edgeR in enumerate(radialEdges[1:], start = 1):
            radius = radialScale * edgeR * unit
            lowIndex[i, j] = len(vertices); vertices.append((x, radius * math.cos(half), -radius * math.sin(half)))
            highIndex[i, j] = len(vertices); vertices.append((x, radius * math.cos(half), radius * math.sin(half)))

    blocks, cells = [], 0
    patches = {'inlet': ('patch', []), 'base': ('wall', []), 'outlet': ('patch', []), 'farField': ('patch', []),
               'front': ('wedge', []), 'back': ('wedge', [])}
    last, outer = len(axialEdges) - 1, len(radialEdges) - 1
    for i, (axialCells, axialExpansion) in enumerate(axial):
        for j, (radialCells, radialExpansion) in enumerate(radial):
            cells += axialCells * radialCells
            size = f'({axialCells} {radialCells} 1) simpleGrading ({axialExpansion:.6f} {radialExpansion:.6f} 1)'
            l0, l1, h0, h1 = lowIndex[i, j + 1], lowIndex[i + 1, j + 1], highIndex[i, j + 1], highIndex[i + 1, j + 1]
            if j == 0:
                a0, a1 = axisIndex[i], axisIndex[i + 1]
                blocks.append(f'    hex ({a0} {a1} {l1} {l0} {a0} {a1} {h1} {h0}) {size}')
                patches['front'][1].append(f'({a0} {a1} {h1} {h0})')
                patches['back'][1].append(f'({a0} {l0} {l1} {a1})')
                if i == 0:
                    patches['inlet'][1].append(f'({a0} {h0} {l0} {a0})')
                if i + 1 == last:
                    patches['outlet'][1].append(f'({a1} {l1} {h1} {a1})')
                continue
            # The block's inner edge is the band below's outer edge
            m0, m1, n0, n1 = lowIndex[i, j], lowIndex[i + 1, j], highIndex[i, j], highIndex[i + 1, j]
            blocks.append(f'    hex ({m0} {m1} {l1} {l0} {n0} {n1} {h1} {h0}) {size}')
            patches['front'][1].append(f'({n0} {n1} {h1} {h0})')
            patches['back'][1].append(f'({m0} {l0} {l1} {m1})')
            if i == 0:
                patches['base'][1].append(f'({m0} {n0} {h0} {l0})')
            if i + 1 == last:
                patches['outlet'][1].append(f'({m1} {l1} {h1} {n1})')
            if j + 1 == outer:
                patches['farField'][1].append(f'({l0} {h0} {h1} {l1})')

    boundary = '\n'.join(f'    {name}\n    {{\n        type {kind};\n        faces\n        (\n'
                         + '\n'.join(f'            {face}' for face in faces) + '\n        );\n    }'
                         for name, (kind, faces) in patches.items())

    text = (_header('dictionary', 'blockMeshDict', 'system')
            + f'// {len(blocks)} blocks, {cellsPerRadius} cells across the exit station\'s radius of {unit:.6f} m.\n'
            + f'// Radii sit {radialScale:.6f} times out, which gives the flat-faced wedge the flow area of the sector.\n'
            + '// The axis is a collapsed edge of the inner blocks, so its points are merged rather than its faces.\n'
            + 'mergeType points;\n\nscale 1;\n\nvertices\n(\n'
            + '\n'.join('    ({:.9f} {:.9f} {:.9f})'.format(*vertex) for vertex in vertices)
            + '\n);\n\nblocks\n(\n' + '\n'.join(blocks) + '\n);\n\nedges\n(\n);\n\nboundary\n(\n' + boundary
            + '\n);\n\nmergePatchPairs\n(\n);\n')

    return text, cells

#--------------------------------------------------------------------------------------------------------------------------#
# -- The case files -- #
#--------------------------------------------------------------------------------------------------------------------------#

def fieldFile(name: str, reference: dict, extent: dict) -> str:

    '''

    The boundary conditions of one field. The inflow and the initial field are written by
    `setPlumeInflow.py`; until it runs, both are the ambient.

    '''

    gas = reference['gas']
    gamma, ambientPressure = gas['gamma'], gas['ambientPressure']
    unit = reference['station']['radius']
    wedges = ('    front\n    {\n        type            wedge;\n    }\n'
              '    back\n    {\n        type            wedge;\n    }\n')
    inflow = ('    // The march\'s exit station: supersonic, so every field is fixed. Written by setPlumeInflow.py.\n'
              '    inlet\n    {\n        type            fixedValue;\n        value           uniform {value};\n    }\n')

    def transmissive(relaxation: float) -> str:

        # Outgoing waves leave at the local wave speed and the pressure relaxes toward the ambient's
        # over the domain's own size, so the boundary neither holds a pressure nor reflects a wave
        return ('        type            waveTransmissive;\n        field           p;\n'
                f'        psi             thermo:psi;\n        gamma           {gamma:.9g};\n'
                f'        fieldInf        {ambientPressure};\n        lInf            {relaxation:.6g};\n'
                f'        value           uniform {ambientPressure};\n')

    if name == 'p':
        return (_header('volScalarField', 'p', '0') + 'dimensions      [1 -1 -2 0 0 0 0];\n\n'
                + f'internalField   uniform {ambientPressure};\n\nboundaryField\n{{\n'
                + inflow.replace('{value}', f'{ambientPressure}')
                + '    base\n    {\n        type            zeroGradient;\n    }\n'
                + '    // Both open boundaries pass outgoing waves and relax toward the ambient\n'
                + '    farField\n    {\n' + transmissive(extent['radius'] * unit) + '    }\n'
                + '    outlet\n    {\n' + transmissive(extent['length'] * unit) + '    }\n' + wedges + '}\n')
    if name == 'T':
        ambient = gas['ambientTemperature']
        return (_header('volScalarField', 'T', '0') + 'dimensions      [0 0 0 1 0 0 0];\n\n'
                + f'internalField   uniform {ambient};\n\nboundaryField\n{{\n'
                + inflow.replace('{value}', f'{ambient}')
                + '    base\n    {\n        type            zeroGradient;\n    }\n'
                + '    farField\n    {\n        type            inletOutlet;\n'
                + f'        inletValue      uniform {ambient};\n        value           uniform {ambient};\n    }}\n'
                + '    outlet\n    {\n        type            inletOutlet;\n'
                + f'        inletValue      uniform {ambient};\n        value           uniform {ambient};\n    }}\n'
                + wedges + '}\n')

    return (_header('volVectorField', 'U', '0') + 'dimensions      [0 1 -1 0 0 0 0];\n\n'
            + 'internalField   uniform (0 0 0);\n\nboundaryField\n{\n'
            + inflow.replace('{value}', '(0 0 0)')
            + '    // The nozzle\'s base, inviscid\n'
            + '    base\n    {\n        type            slip;\n    }\n'
            + '    farField\n    {\n        type            pressureInletOutletVelocity;\n'
            + '        value           uniform (0 0 0);\n    }\n'
            + '    outlet\n    {\n        type            inletOutlet;\n        inletValue      uniform (0 0 0);\n'
            + '        value           uniform (0 0 0);\n    }\n' + wedges + '}\n')

def controlDict(reference: dict, extent: dict, endTime: float, writes: int) -> str:

    station = reference['station']
    unit = station['radius']
    # The axis line sits a hair off the axis and inside each end, so every sample falls in a cell
    inset = 1e-4 * unit
    history = ('        type            surfaceFieldValue;\n        libs            (fieldFunctionObjects);\n'
               '        writeControl    timeStep;\n        writeInterval   20;\n        log             false;\n'
               '        writeFields     false;\n        regionType      patch;\n        operation       sum;\n'
               '        fields          (phi);\n')

    return (_header('dictionary', 'controlDict', 'system')
            + 'application     rhoCentralFoam;\n\nstartFrom       latestTime;\n\nstartTime       0;\n\nstopAt          endTime;\n\n'
            + f'endTime         {endTime:g};\n\ndeltaT          1e-9;\n\nwriteControl    adjustable;\n\n'
            + f'writeInterval   {endTime / writes:g};\n\npurgeWrite      0;\n\n'
            + '// ASCII, so the inflow script and the comparison read the fields without OpenFOAM\n'
            + 'writeFormat     ascii;\n\nwritePrecision  10;\n\nwriteCompression off;\n\ntimeFormat      general;\n\n'
            + 'timePrecision   8;\n\nrunTimeModifiable true;\n\nadjustTimeStep  yes;\n\n'
            + '// Counts the wedge faces, which carry no flux: see makeNozzleCase.py\n'
            + f'maxCo           {nozzleCase.maxCourant:g};\n\nmaxDeltaT       1;\n\n'
            + 'functions\n{\n'
            + '    Ma\n    {\n        type            MachNo;\n        libs            (fieldFunctionObjects);\n'
            + '        executeControl  writeTime;\n        writeControl    writeTime;\n    }\n\n'
            + '    // The comparison reads the mean over the second half of the run\n'
            + '    average\n    {\n        type            fieldAverage;\n        libs            (fieldFunctionObjects);\n'
            + f'        timeStart       {endTime * (1.0 - nozzleCase.averagedFraction):g};\n        writeControl    writeTime;\n'
            + '        fields\n        (\n'
            + ''.join(f'            {field}\n            {{\n                mean        on;\n                prime2Mean  off;\n'
                      f'                base        time;\n            }}\n' for field in ('p', 'T', 'U'))
            + '        );\n    }\n\n'
            + '    // Mass through each open boundary, for steadiness and the mass balance\n'
            + ''.join(f'    {name}Flow\n    {{\n{history}        name            {name};\n    }}\n\n'
                      for name in ('inlet', 'outlet', 'farField'))
            + '    axis\n    {\n        type            sets;\n        libs            (sampling);\n'
            + '        writeControl    writeTime;\n        setFormat       raw;\n        interpolationScheme cellPoint;\n'
            + '        fields          (p T U Ma pMean TMean UMean);\n        sets\n        {\n'
            + '            axis\n            {\n                type    uniform;\n                axis    xyz;\n'
            + f'                start   ({station["x"] + inset:.9f} {inset:.9f} 0);\n'
            + f'                end     ({station["x"] + extent["length"] * unit - inset:.9f} {inset:.9f} 0);\n'
            + '                nPoints 6000;\n            }\n        }\n    }\n}\n')

def fvSchemes() -> str:

    '''

    The nozzle case's schemes with the Minmod limiter in place of van Leer's. Where the barrel shock
    meets the axis, van Leer's limiter drives the axis cells past the gas's limiting velocity, and
    the temperature negative, at a Courant number of 1.0 and of 0.5 alike; Minmod, the most
    dissipative of the TVD limiters, does not.

    '''

    return (nozzleCase.fvSchemes()
            .replace('van Leer limited reconstruction, as the rhoCentralFoam\n// tutorials run it',
                     'Minmod limited reconstruction: van Leer\'s\n// limiter fails on the axis where the barrel shock meets it')
            .replace('reconstruct(rho) vanLeer;', 'reconstruct(rho) Minmod;')
            .replace('reconstruct(U)  vanLeerV;', 'reconstruct(U)  Minmod;')
            .replace('reconstruct(T)  vanLeer;', 'reconstruct(T)  Minmod;'))

allrun = '''#!/bin/sh
# ./Allrun                 start from the ambient, with the exit flow filling a column downstream
# ./Allrun <source case>   start from another grid's solution, mapped onto this one
cd "${0%/*}" || exit                                # Run from this directory
. ${WM_PROJECT_DIR:?}/bin/tools/RunFunctions        # Tutorial run functions
#------------------------------------------------------------------------------

restore0Dir
runApplication blockMesh
runApplication checkMesh

# The cell and face centers, which the inflow script and the comparison both read
runApplication postProcess -func writeCellCentres -time 0

if [ -n "$1" ]
then
    runApplication mapFields "$1" -consistent -sourceTime latestTime
    runApplication -s inflow python3 scripts/setPlumeInflow.py .
else
    runApplication -s inflow python3 scripts/setPlumeInflow.py . --column
fi

runApplication decomposePar
runParallel $(getApplication)
runApplication reconstructPar -latestTime

runApplication -s compare python3 scripts/comparePlume.py .
touch case.foam

#------------------------------------------------------------------------------
'''

def writeCase(reference: dict, resolution: str, output: str, processors: int, endTime: float, writes: int,
              extent: dict) -> None:

    '''Write every file of the case, and the scripts and reference it runs with.'''

    cellsPerRadius = resolutions[resolution]
    meshText, cells = blockMeshDict(reference, cellsPerRadius, extent)

    files = {
        'system/blockMeshDict': meshText,
        'system/controlDict': controlDict(reference, extent, endTime, writes),
        'system/fvSchemes': fvSchemes(),
        'system/fvSolution': nozzleCase.fvSolution(),
        'system/decomposeParDict': nozzleCase.decomposeParDict(processors),
        'constant/thermophysicalProperties': nozzleCase.thermophysicalProperties(reference),
        'constant/turbulenceProperties': nozzleCase.turbulenceProperties(),
        '0.orig/p': fieldFile('p', reference, extent),
        '0.orig/T': fieldFile('T', reference, extent),
        '0.orig/U': fieldFile('U', reference, extent),
        'Allrun': allrun,
        'Allclean': nozzleCase.allclean,
    }
    for name, text in files.items():
        path = os.path.join(output, name)
        os.makedirs(os.path.dirname(path), exist_ok = True)
        with open(path, 'w', encoding = 'utf-8', newline = '\n') as handle:
            # The shared file header names its writer; padded to keep the banner's width
            handle.write(text.replace('validation/openFoam/makeNozzleCase.py', 'validation/openFoam/makePlumeCase.py '))

    os.makedirs(os.path.join(output, 'scripts'), exist_ok = True)
    for script in ('setPlumeInflow.py', 'comparePlume.py', 'compareWithNova.py', 'plumeGridConvergence.py',
                   'gridConvergence.py'):
        shutil.copyfile(os.path.join(here, script), os.path.join(output, 'scripts', script))
    os.makedirs(os.path.join(output, 'reference'), exist_ok = True)
    shutil.copyfile(referencePath, os.path.join(output, 'reference', 'novaPlume.json'))
    shutil.copyfile(nozzleCase.stylePath, os.path.join(output, 'reference', 'style.json'))
    with open(os.path.join(output, 'reference', 'case.json'), 'w', encoding = 'utf-8') as handle:
        json.dump({'resolution': resolution, 'cellsPerRadius': cellsPerRadius, 'cells': cells,
                   'wedgeAngle': wedgeAngle, 'radialScale': radialScale, 'endTime': endTime,
                   'averageStart': endTime * (1.0 - nozzleCase.averagedFraction), 'domain': extent}, handle, indent = 2)

    print(f'wrote {output}: {resolution} grid, {cells} cells, {cellsPerRadius} across the station radius')

def main() -> None:

    parser = argparse.ArgumentParser(description = 'Write the axisymmetric OpenFOAM case of the NOVA plume.')
    parser.add_argument('--resolution', choices = list(resolutions), default = 'medium')
    parser.add_argument('--output', default = None, help = 'case folder; cases/novaPlume2D-<resolution> by default')
    parser.add_argument('--processors', type = int, default = 4)
    parser.add_argument('--end-time', type = float, default = None,
                        help = 'physical time to run [s]; endTimes[resolution] by default')
    parser.add_argument('--writes', type = int, default = 8, help = 'times the solution is written over the run')
    parser.add_argument('--length', type = float, default = None, help = 'domain length in station radii')
    parser.add_argument('--radius', type = float, default = None, help = 'domain radius in station radii')
    parser.add_argument('--refresh', action = 'store_true', help = 'solve NOVA again before writing the case')
    arguments = parser.parse_args()

    extent = dict(domain)
    if arguments.length:
        extent['length'] = arguments.length
    if arguments.radius:
        extent['radius'] = arguments.radius

    reference = loadReference(arguments.refresh)
    output = arguments.output or os.path.join(here, 'cases', f'novaPlume2D-{arguments.resolution}')
    writeCase(reference, arguments.resolution, output, arguments.processors,
              arguments.end_time or endTimes[arguments.resolution], arguments.writes, extent)

if __name__ == '__main__':
    main()
