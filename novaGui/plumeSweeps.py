
# -- NOVA GUI Plume Sweeps -- #

'''

A finished run's plume over a list of ambient pressures, solved on the nozzle the run kept.

Of NOVA's stages, only the plume and the delivered performance read the ambient pressure; the
contour, the cooling and the extension give the same answer at any ambient. A plume sweep takes a
finished run and solves its plume at each ambient on the run's own Nozzle, in a worker process
(`runSweep`), without running the pipeline again. It is kept with its run, in the run's folder,
and goes when the run goes (novaGui.plumeQueue).

At each ambient, `solvePoint` gives:

    the correlated structure (NOVA.plume.solvePlumeStructure): the jet type, the fully expanded
        jet diameter, the shock cell length, and where the first shock meets the axis, a Mach disk
        or a regular reflection
    the station march (NOVA.stationMarch.solveStationField) to two lip radii, the reach over which
        it conserves mass, and, for a sweep drawn farther, a second march to that reach; the
        boundary drawn is from the longer march, and each march's mass continuity error is kept
    the delivered thrust coefficient, specific impulse and thrust at that ambient, from the run's
        own exit-plane integral by the relation NOVA.performance states,
        C_F(p_a) = C_F,vac - p_a A_e / (p_c A_t), with the impulse and the thrust scaled by the
        coefficient as the run's own summary scales them

A throttle sweep holds the ambient and varies the engine instead: each point is a power level, the
chamber pressure as a fraction of its rated value, solved on the run's contour with every absolute
pressure scaled by it (NOVA.plume.throttledContour) and the gas held at its rated state. The field
at a given exit pressure ratio is the same either way, since the march carries one stagnation
pressure and its relations are homogeneous in pressure; what a throttle sweep answers is how far
the engine throttles at one ambient before its nozzle separates. That limit, the power level at
which the exit pressure ratio falls to the Summerfield criterion, is exact within the model:
f_sep = 0.40 p_a / p_e,rated (`separation`). The delivered performance follows the same frozen
gas state (docs/plumeThrottleModel.md): mass flow and every static pressure scale with the
chamber while the exit velocity does not, so the vacuum thrust scales with the power level and

    F(f, p_a) = f F_vac - p_a A_e,    C_F(f, p_a) = C_F,vac - p_a A_e / (f p_c A_t)

which is the ambient relation above at a chamber pressure of f p_c. Holding the gas at its rated
state puts the separation limit high, on the safe side: on the shipped LOX/LH2 engine a gas
re-solved at 20 percent power has an exit pressure 4.9 percent above the held gas's, so it
separates at 19.1 percent where the held gas reports 20.0.

The march decides which points the sweep takes. A point it refuses (one that separates the
nozzle internally, compresses the lip past a weak oblique shock, or puts the free boundary at or
below Mach one) is a refused point, with the march's reason and no numbers. A point whose march
loses more than `plumeFieldDriftTolerance` of the exit mass flow is kept and marked: its boundary
draws dashed and its error reads as a warning. Measured on the shipped nozzle at two lip radii,
the mass continuity error is 0.24 to 0.42 percent over lip pressure ratios of 0.70 to 2.5 and
0.93 percent at 10, and the march refuses 0.60, where the lip's oblique shock is too strong; at
six lip radii the error runs 7.5 to 31 percent over 0.70 to 2.5.

`table` lays a sweep out for the browser, its numbers as text in display units, and `figure`
draws its boundaries over one another in lip radii from the exit plane, each labeled with its lip
pressure ratio, against the nozzle wall. `performanceFigure` draws a throttle sweep's delivered
thrust and specific impulse against power level, with the separation limit marked.

Validation status: an ambient sweep adds no model. Its numbers carry the status of the models
behind them (docs/validationStatus.json): the plume march and the plume correlations are
unvalidated, and the delivered performance is unvalidated over a contour that is cross-checked. The
table and the figure carry those badges. A throttle sweep adds the frozen gas state, which is an
approximation, not a validated model. Two of its properties are exact and tested
(tests/testPlumeSweeps.py): a power level solves the same field as the ambient scaled by it, and
its performance follows F = f F_vac - p_a A_e. Its cost on the separation limit is measured
against re-solved thermochemistry in docs/plumeThrottleModel.md, 4.9 percent of the power level on
the shipped engine, on the conservative side; the separation criterion itself is an empirical
correlation with a quoted spread of 0.35 to 0.40.

Author: Sean Bowman
Date:   11/22/2026

'''

# Standard library imports
import contextlib
import io
import json
import math
import os
import pickle
import time
import warnings

# Local imports
from . import themeColors
from . import units
from . import validationStatus

maxPoints = 20                  # points one plume sweep solves
nearReach = 2.0                 # [lip radii] the march's own default reach, which it conserves mass over
maxReach = 6.0                  # [lip radii] the longest reach a sweep draws
maxFraction = 1.5               # [-] the highest power level a throttle sweep takes, as a fraction of rated
boundaryPoints = 300            # boundary points kept for each point's drawing
nameLength = 80                 # [characters] the longest name a plume sweep takes
pointStates = ('queued', 'running', 'done', 'refused', 'failed', 'cancelled')
sweepKinds = ('ambient', 'throttle')

# The Summerfield criterion's quoted spread, 0.35 to 0.40 in the exit to ambient pressure ratio
# (docs/plumeThrottleModel.md); the march refuses at the upper end, NOVA.plume.separationPressureRatio
separationSpreadLow = 0.35

# The frozen gas state's bias on the separation limit, measured on the shipped engine (LOX/LH2,
# mixture ratio 5.5, area ratio 40) over a 5:1 throttle: the held gas reports separation at 20.0
# percent power, a gas re-solved at each power level at 19.1 (docs/plumeThrottleModel.md)
frozenGasBias = 4.9             # [%] of the power level, the held gas's limit above the re-solved gas's

# The models behind each kind of number (docs/validationStatus.json)
performanceModels = ['contour', 'deliveredPerformance']
structureModels = ['plumeCorrelations']
marchModels = ['plumeMarch']

#----------------------------------------------------------------------#
# -- The request -- #
#----------------------------------------------------------------------#

def defaultName(ambients: list, unit: str) -> str:

    '''A plume sweep's name when it is given none: the range of its ambients.'''

    low, high = (units.fromSI(value, 'pressure', unit) for value in (min(ambients), max(ambients)))

    return f'Plume, {low:.4g} to {high:.4g} {unit}'

def throttleName(fractions: list, ambient: float, unit: str) -> str:

    '''A throttle sweep's name when it is given none: its power levels and the ambient it holds.'''

    held = units.fromSI(ambient, 'pressure', unit)

    return f'Throttle, {100.0 * max(fractions):.4g} to {100.0 * min(fractions):.4g} % at {held:.4g} {unit}'

def _isNumber(value) -> bool:

    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)

def _distinct(values, many: str, one: str, rule: str, check) -> list:

    '''

    Two to `maxPoints` distinct numbers that each pass `check`, as floats. `many`, `one` and `rule`
    word the refusals: 'ambient pressures', 'an ambient pressure', 'each is a number of pascals
    above zero'.

    '''

    if not isinstance(values, list) or len(values) < 2:
        raise ValueError(f'give at least two {many}')
    if len(values) > maxPoints:
        raise ValueError(f'{len(values)} {many}; a plume sweep solves at most {maxPoints}')
    for value in values:
        if not _isNumber(value) or not check(value):
            raise ValueError(f'{value!r} is not {one}; {rule}')
    values = [float(value) for value in values]
    if len(set(values)) < len(values):
        raise ValueError(f'{one} is given twice')

    return values

def build(request: dict) -> dict:

    '''

    A plume sweep from what the browser sends, checked, without its number or its run.

    Parameters:
    -----------
    request : dict
        An ambient sweep, {'kind': 'ambient', 'name': str, 'ambients': [float], 'unit': str,
        'reach': float}: the ambient pressures in Pa, the pressure unit they were entered in, and
        the reach to draw in lip radii. A throttle sweep, {'kind': 'throttle', 'name': str,
        'ambient': float, 'fractions': [float], 'unit': str, 'reach': float}: the one ambient in Pa
        and the power levels as fractions of rated chamber pressure. 'kind' defaults to 'ambient'.

    Returns:
    --------
    dict : {'kind', 'name', 'createdAt', 'unit', 'reach', 'points'}, with 'ambient' for a throttle
        sweep; each point {'index', 'ambient' or 'fraction', 'state', 'error', 'result'}

    Raises:
    -------
    ValueError : with the reason, for a sweep that cannot be solved

    '''

    if not isinstance(request, dict):
        raise ValueError('a plume sweep must be an object')
    kind = request.get('kind') or 'ambient'
    if kind not in sweepKinds:
        raise ValueError(f'{kind!r} is not a kind of plume sweep; it is {" or ".join(sweepKinds)}')

    unit = str(request.get('unit') or 'kPa')
    if unit not in units.unitsFor('pressure'):
        raise ValueError(f'{unit!r} is not a unit of pressure')
    reach = request.get('reach', nearReach)
    if not _isNumber(reach) or not nearReach <= reach <= maxReach:
        raise ValueError(f'the reach is {nearReach:g} to {maxReach:g} lip radii')

    held = {}
    if kind == 'ambient':
        ambients = _distinct(request.get('ambients'), 'ambient pressures', 'an ambient pressure',
                             'each is a number of pascals above zero', lambda value: value > 0.0)
        points = [{'index': index, 'ambient': ambient} for index, ambient in enumerate(ambients)]
        named = defaultName(ambients, unit)
    else:
        ambient = request.get('ambient')
        if not _isNumber(ambient) or ambient <= 0.0:
            raise ValueError(f'{ambient!r} is not an ambient pressure; it is a number of pascals above zero')
        fractions = _distinct(request.get('fractions'), 'power levels', 'a power level',
                              f'each is a fraction of rated chamber pressure above 0 and at most {maxFraction:g}',
                              lambda value: 0.0 < value <= maxFraction)
        points = [{'index': index, 'fraction': fraction} for index, fraction in enumerate(fractions)]
        held = {'ambient': float(ambient)}
        named = throttleName(fractions, ambient, unit)

    name = ' '.join(str(request.get('name') or '').split()) or named
    if len(name) > nameLength:
        raise ValueError(f'a plume sweep name takes at most {nameLength} characters')
    points = [{**point, 'state': 'queued', 'error': '', 'result': None} for point in points]

    return {'kind': kind, 'name': name, 'createdAt': time.time(), 'unit': unit, 'reach': float(reach), **held,
            'points': points}

def pointConditions(sweep: dict, point: dict) -> tuple:

    '''A point's (ambient [Pa], power level [-]): an ambient sweep's points run at rated power.'''

    if sweep.get('kind', 'ambient') == 'throttle':
        return float(sweep['ambient']), float(point['fraction'])

    return float(point['ambient']), 1.0

#----------------------------------------------------------------------#
# -- The solve -- #
#----------------------------------------------------------------------#

def plumeContour(nozzle):

    '''

    The fields a plume is seeded from, read off a run's Nozzle (or any object carrying them by
    name), as Nozzle.plumeContour reads them, with no structure solved at another ambient.

    '''

    from NOVA.plume import PlumeContour

    contour = PlumeContour()
    for name in PlumeContour.__dataclass_fields__:
        setattr(contour, name, getattr(nozzle, name, None))
    contour.nozzlePlumeStructure = None

    return contour

def lipState(nozzle) -> dict:

    '''

    The lip and the wall a sweep is drawn against: the lip's static pressure, which sets each
    ambient's lip pressure ratio, its position and radius, and the wall in lip radii from it, all at
    rated power. With them, the one-dimensional exit pressure at the area ratio in the contour's
    gas, which the separation criterion reads (NOVA.plume.solvePlumeStructure).

    Returns:
    --------
    dict : {'pressure' [Pa], 'exitPressure' [Pa], 'x' [m], 'radius' [m], 'wall': {'x', 'r'}} or
        {'reason': str} when the run's contour carries no characteristic mesh for the march to
        continue

    '''

    import numpy as np
    from NOVA.plume import PlumeFlow, plumeCharacteristicSeed, plumeExitLine, solvePlumeStructure
    from NOVA.stationMarch import plumeFieldRadialPoints, stationFromLine

    seed = plumeCharacteristicSeed(plumeContour(nozzle))
    required = ('gamma', 'gasConstant', 'stagnationTemperature', 'stagnationPressure', 'exitX', 'exitRadius',
                'xMesh', 'rMesh', 'flowAngleMesh', 'machMesh')
    if seed is None or any(seed.get(key) is None for key in required):
        return {'reason': 'the contour carries no characteristic mesh for the plume march to continue; '
                          'a conical nozzle has none'}
    flow = PlumeFlow(seed['gamma'], seed['gasConstant'], seed['stagnationTemperature'], seed['stagnationPressure'])
    line = plumeExitLine(flow, seed, numPoints = 400)
    if line is None:
        return {'reason': 'the exit plane could not be read from the characteristic mesh'}
    station = stationFromLine(line, plumeFieldRadialPoints)
    pressure = float(flow.staticPressure(float(station.mach[-1])))

    # The lip as every point's structure and march place it, so the wall and the boundaries share an origin
    structure = solvePlumeStructure(plumeContour(nozzle), ambientPressure = pressure)
    if structure is None or not structure.lipRadius:
        return {'reason': 'the run carries no exit state to solve a plume from'}
    lipX, lipRadius = float(structure.lipX), float(structure.lipRadius)
    wallX = np.asarray(getattr(nozzle, 'xNozzleWall', []), dtype = float)
    wallR = np.asarray(getattr(nozzle, 'rNozzleWall', []), dtype = float)
    keep = np.isfinite(wallX) & np.isfinite(wallR)

    return {'pressure': pressure, 'exitPressure': float(structure.exitPressure), 'x': lipX, 'radius': lipRadius,
            'wall':{'x': _thinned((wallX[keep] - lipX) / lipRadius), 'r': _thinned(wallR[keep] / lipRadius)}}

def _thinned(values, count: int = boundaryPoints) -> list:

    '''At most `count` values, evenly by index, the last always among them, as plain floats.'''

    values = list(values)
    if len(values) > count:
        step = (len(values) - 1) / (count - 1)
        values = [values[round(index * step)] for index in range(count)]

    return [round(float(value), 6) for value in values]

def performanceAt(nozzle, ambient: float, fraction: float = 1.0) -> dict | None:

    '''

    The run's delivered thrust coefficient, specific impulse and thrust at an ambient pressure and
    a power level.

    The run integrates its exit plane once, against no back pressure (NOVA.performance), and the
    coefficient at any ambient follows from it exactly: C_F(p_a) = C_F,vac - p_a A_e / (p_c A_t).
    The impulse and the thrust are the plane's own vacuum values scaled by the coefficient, as the
    run's summary scales them to each named back pressure.

    At a power level f with the gas held at its rated state, every density and static pressure on
    the exit plane scales with the chamber and every velocity holds, so the plane's vacuum thrust
    scales by f and its vacuum coefficient and impulse hold. The chamber pressure in the relation
    becomes f p_c, and the thrust is f F_vac - p_a A_e (docs/plumeThrottleModel.md).

    Parameters:
    -----------
    nozzle : NOVA.Nozzle
        The run's Nozzle, with its performance summary.
    ambient : float
        Back pressure [Pa].
    fraction : float
        Power level, the chamber pressure as a fraction of its rated value.

    Returns:
    --------
    dict : {'thrustCoef' [-], 'specificImpulse' [s], 'thrust' [N]}, or None for a run without a
        delivered vacuum coefficient

    '''

    summary = getattr(nozzle, 'performance', None)
    if summary is None:
        return None
    vacuumCoef = summary.thrustCoefDelivered.get('vacuum')
    vacuumImpulse = summary.specificImpulseDelivered.get('vacuum')
    if vacuumCoef is None or not math.isfinite(vacuumCoef) or vacuumCoef == 0.0:
        return None
    chamberPressure = float(fraction) * float(nozzle.chamberPressure)    # [Pa]
    coefficient = float(vacuumCoef) - float(ambient) * float(summary.areaRatio) / chamberPressure
    scale = coefficient / float(vacuumCoef)
    vacuumThrust = summary.thrustDelivered.get('vacuum') if summary.thrustDelivered else None

    return {'thrustCoef': coefficient,
            'specificImpulse': float(vacuumImpulse) * scale if vacuumImpulse is not None else None,
            'thrust': float(fraction) * float(vacuumThrust) * scale if vacuumThrust is not None else None}

def solvePoint(nozzle, ambient: float, reach: float, lip: dict, fraction: float = 1.0) -> dict:

    '''

    The plume and the delivered performance of a run's nozzle at one ambient pressure and one
    power level.

    Parameters:
    -----------
    nozzle : NOVA.Nozzle
        The run's Nozzle, as it was pickled.
    ambient : float
        Pressure the plume expands into [Pa].
    reach : float
        The reach drawn [lip radii]; the march runs to `nearReach` first, and again to this reach
        when it is longer.
    lip : dict
        `lipState` of the nozzle.
    fraction : float
        Power level, the chamber pressure as a fraction of its rated value. Every absolute
        pressure the contour carries scales by it (NOVA.plume.throttledContour); the gas holds.

    Returns:
    --------
    dict : {'state': 'done' | 'refused', 'error': str, 'result': dict | None}. The result holds the
        power level, the lip and exit pressure ratios, the jet type, the performance, the fully
        expanded jet diameter [m], the shock cell length [m], the first shock on the axis and where
        [lip radii from the exit plane], the mass continuity error [%] at each reach and whether
        the drawn one is within the trusted bound, the boundary Mach number, the march's notes and
        its boundary in lip radii from the exit plane.

    '''

    from NOVA.plume import solvePlumeStructure, throttledContour
    from NOVA.stationMarch import plumeFieldDriftTolerance, solveStationField

    contour = plumeContour(nozzle)
    if fraction != 1.0:
        contour = throttledContour(contour, fraction)
    notes = []
    with warnings.catch_warnings(record = True) as caught, contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter('always')
        structure = solvePlumeStructure(contour, ambientPressure = ambient)
        # Handed to the march, which reuses a structure solved at its own ambient
        contour.nozzlePlumeStructure = structure
        near = solveStationField(contour, ambientPressure = ambient, reach = nearReach)
        far = (solveStationField(contour, ambientPressure = ambient, reach = reach)
               if near.solved and reach > nearReach + 1e-9 else near)
    for message in dict.fromkeys(f'{entry.category.__name__}: {entry.message}' for entry in caught):
        notes.append(message)

    if structure is None:
        return {'state': 'refused', 'error': 'the run carries no exit state to solve a plume from', 'result': None}
    if not near.solved:
        return {'state': 'refused', 'error': near.notes[-1] if near.notes else 'the plume march declined', 'result': None}
    # A longer march that declines leaves the short one to draw, and no error at the reach asked for
    drawn = far if far.solved else near
    if not far.solved:
        notes.append(f'The march to {reach:g} lip radii declined, so the boundary drawn is the one to {nearReach:g}: '
                     + (far.notes[-1] if far.notes else 'no reason given'))

    lipX, lipRadius = lip['x'], lip['radius']
    axisKind, axisAt = '', None
    if structure.machDiskPresent and structure.lipRadius:
        axisKind, axisAt = 'Mach disk', (structure.machDiskX - structure.lipX) / structure.lipRadius
    elif structure.axisShockX and structure.lipRadius:
        axisKind, axisAt = 'regular reflection', (structure.axisShockX - structure.lipX) / structure.lipRadius

    result = {
        'fraction': float(fraction),
        # The lip pressure scales with the chamber, as every static pressure in the nozzle does
        'lipRatio': fraction * lip['pressure'] / ambient,
        'exitRatio': float(structure.exitPressureRatio),
        'jetType': structure.jetType,
        **(performanceAt(nozzle, ambient, fraction) or {'thrustCoef': None, 'specificImpulse': None, 'thrust': None}),
        'jetDiameter': float(structure.fullyExpandedDiameter),
        'shockCellLength': float(structure.shockCellLength),
        'axisShockKind': axisKind,
        'axisShockAt': float(axisAt) if axisAt is not None else None,
        'nearDrift': float(near.massDriftWorst),
        'drift': float(far.massDriftWorst) if far.solved else None,
        'trustworthy': bool(drawn.trustworthy),
        'tolerance': float(plumeFieldDriftTolerance),
        'boundaryMach': float(drawn.boundaryMach),
        'notes': list(drawn.notes) + notes,
        'boundary': {'x': _thinned((drawn.boundaryX - lipX) / lipRadius), 'r': _thinned(drawn.boundaryR / lipRadius)},
    }

    return {'state': 'done', 'error': '', 'result': result}

def runSweep(picklePath: str, points: list, reach: float, eventQueue) -> None:

    '''

    Solve a plume sweep's points on a run's pickled Nozzle and report through `eventQueue`. Called
    in the child process. `points` is [(point index, ambient [Pa], power level [-])], the points to
    solve (`pointConditions`).

    Messages put on the queue:

        ('start', dict)             the lip (lipState), before the first point
        ('begin', index)            a point starts
        ('point', (index, dict))    a point ended: {'state', 'error', 'result'} (solvePoint), or
                                    'failed' with the error
        ('end', str)                terminal: '' when every point was solved, else why the sweep stopped

    '''

    # Before anything imports NOVA: open no windows or browser tabs
    os.environ['NOVA_HEADLESS'] = '1'

    try:
        with open(picklePath, 'rb') as handle:
            nozzle = pickle.load(handle)
        lip = lipState(nozzle)
    except Exception as exc:                               # noqa: BLE001 -- any load failure ends the sweep
        eventQueue.put(('end', f'the run\'s saved result does not load ({type(exc).__name__}: {exc})'))
        return
    if 'reason' in lip:
        eventQueue.put(('end', lip['reason']))
        return
    eventQueue.put(('start', lip))

    for index, ambient, fraction in points:
        eventQueue.put(('begin', index))
        try:
            outcome = solvePoint(nozzle, ambient, reach, lip, fraction)
        except Exception as exc:                           # noqa: BLE001 -- a failed point leaves the rest
            outcome = {'state': 'failed', 'error': f'{type(exc).__name__}: {exc}', 'result': None}
        eventQueue.put(('point', (index, outcome)))
    eventQueue.put(('end', ''))

#----------------------------------------------------------------------#
# -- The browser's table and figure -- #
#----------------------------------------------------------------------#

def _text(value, template: str) -> str:

    return template.format(value) if value is not None and math.isfinite(value) else '--'

def columns(sweep: dict) -> list:

    '''

    The table's number columns, in order: {'key', 'label', 'unit', 'models'}, `models` naming the
    models behind the column. A throttle sweep adds the exit pressure ratio, which the separation
    criterion reads, and a sweep drawn past two lip radii adds the error at its own reach.

    '''

    throttle = [{'key': 'exitRatio', 'label': 'Exit pressure ratio', 'unit': '', 'models': []}] \
               if sweep.get('kind') == 'throttle' else []
    found = [
        *throttle,
        {'key': 'lipRatio', 'label': 'Lip pressure ratio', 'unit': '', 'models': []},
        {'key': 'thrustCoef', 'label': 'Thrust coefficient', 'unit': '', 'models': performanceModels},
        {'key': 'specificImpulse', 'label': 'Delivered Isp', 'unit': 's', 'models': performanceModels},
        {'key': 'thrust', 'label': 'Delivered thrust', 'unit': 'kN', 'models': performanceModels},
        {'key': 'jetDiameter', 'label': 'Jet diameter', 'unit': 'mm', 'models': structureModels},
        {'key': 'axisShock', 'label': 'First shock on the axis', 'unit': 'lip radii', 'models': structureModels},
        {'key': 'nearDrift', 'label': f'Mass error at {nearReach:g} lip radii', 'unit': '%', 'models': marchModels},
    ]
    if sweep['reach'] > nearReach + 1e-9:
        found.append({'key': 'drift', 'label': f'Mass error at {sweep["reach"]:g} lip radii', 'unit': '%',
                      'models': marchModels})

    return found

def cells(result: dict) -> dict:

    '''A solved point's numbers as the table shows them: {key: {'text', 'tone'}}.'''

    tolerance = result.get('tolerance', 1.0)

    def drift(value) -> dict:
        return {'text': _text(value, '{:+.2f}'), 'tone': 'warn' if value is not None and abs(value) > tolerance else ''}

    shock = result.get('axisShockAt')
    thrust = result.get('thrust')
    diameter = result.get('jetDiameter')

    return {
        'exitRatio': {'text': _text(result.get('exitRatio'), '{:.3f}'), 'tone': ''},
        'lipRatio': {'text': _text(result.get('lipRatio'), '{:.3f}'), 'tone': ''},
        'thrustCoef': {'text': _text(result.get('thrustCoef'), '{:.4f}'), 'tone': ''},
        'specificImpulse': {'text': _text(result.get('specificImpulse'), '{:.1f}'), 'tone': ''},
        'thrust': {'text': _text(thrust / 1e3 if thrust is not None else None, '{:.1f}'), 'tone': ''},
        'jetDiameter': {'text': _text(diameter * 1e3 if diameter is not None else None, '{:.1f}'), 'tone': ''},
        'axisShock': {'text': f'{shock:.1f}, {result["axisShockKind"]}' if shock is not None else 'none', 'tone': ''},
        'nearDrift': drift(result.get('nearDrift')),
        'drift': drift(result.get('drift')),
    }

def ambientText(sweep: dict, ambient: float) -> str:

    return f'{units.fromSI(ambient, "pressure", sweep["unit"]):.4g} {sweep["unit"]}'

def powerText(fraction: float) -> str:

    return f'{100.0 * fraction:.4g} %'

def pointLabel(sweep: dict, point: dict) -> str:

    '''What names a point: its ambient, or for a throttle sweep its power level.'''

    if sweep.get('kind', 'ambient') == 'throttle':
        return powerText(point['fraction'])

    return ambientText(sweep, point['ambient'])

def separation(sweep: dict) -> dict | None:

    '''

    Where a throttle sweep's nozzle separates: the power level at which the exit pressure ratio
    falls to the Summerfield criterion at the sweep's ambient. At a frozen gas state the exit
    pressure scales with the chamber, so the limit is exact within the model,
    f_sep = 0.40 p_a / p_e,rated, rather than found by search.

    Returns:
    --------
    dict : {'fraction', 'lowFraction', 'ratio', 'lowRatio', 'limit', 'bias'}: the limit at the
        criterion the march refuses on and at the low end of its quoted spread, the two ratios, and
        the limit and the frozen gas state's bias on it as sentences; None for an ambient sweep or
        a sweep whose lip carries no exit pressure

    '''

    from NOVA.plume import separationPressureRatio

    lip = sweep.get('lip') or {}
    exitPressure = lip.get('exitPressure')
    if sweep.get('kind') != 'throttle' or not exitPressure:
        return None
    ambient = float(sweep['ambient'])
    fraction = separationPressureRatio * ambient / exitPressure
    lowFraction = separationSpreadLow * ambient / exitPressure
    limit = (f'The nozzle separates below {powerText(fraction)} power at {ambientText(sweep, ambient)}, where the exit '
             f'pressure ratio falls to {separationPressureRatio:g}, the Summerfield criterion the march refuses on; '
             f'below {powerText(lowFraction)} at {separationSpreadLow:g}, the low end of the criterion\'s quoted spread.')
    bias = (f'The gas is held at its rated state, which puts the limit high, on the safe side. On the shipped LOX/LH2 '
            f'engine the held gas reports 20.0 % where a gas re-solved at each power level separates at 19.1 %, '
            f'{frozenGasBias:g} % high (docs/plumeThrottleModel.md).')

    return {'fraction': fraction, 'lowFraction': lowFraction, 'ratio': separationPressureRatio,
            'lowRatio': separationSpreadLow, 'limit': limit, 'bias': bias}

def _counts(points: list) -> dict:

    counts = {state: 0 for state in pointStates}
    for point in points:
        counts[point['state']] = counts.get(point['state'], 0) + 1

    return counts

def table(sweep: dict) -> dict:

    '''

    A plume sweep as the browser reads it.

    Returns:
    --------
    dict : {'runId', 'number', 'kind', 'name', 'createdAt', 'unit', 'reach', 'ambient',
        'ambientText', 'lip', 'separation', 'columns', 'counts', 'badge', 'points'}. 'ambient' and
        'ambientText' are a throttle sweep's held ambient, None for an ambient sweep, and
        'separation' its limit (`separation`). Each column adds its validation badge; each point is
        {'index', 'ambient', 'fraction', 'label', 'state', 'error', 'trustworthy', 'jetType',
        'notes', 'cells'}.

    '''

    summary = validationStatus.load()
    kind = sweep.get('kind', 'ambient')
    shownColumns = [{**column, 'validation': validationStatus.badge(column['models'], summary) if column['models'] else None}
                    for column in columns(sweep)]
    points = []
    for point in sweep['points']:
        result = point.get('result') or {}
        ambient, fraction = pointConditions(sweep, point)
        points.append({'index': point['index'], 'ambient': ambient, 'fraction': fraction,
                       'label': pointLabel(sweep, point), 'state': point['state'],
                       'error': point.get('error', ''), 'trustworthy': result.get('trustworthy'),
                       'jetType': result.get('jetType', ''), 'notes': result.get('notes', []),
                       'cells': cells(result) if result else {}})
    lip = sweep.get('lip')
    held = sweep.get('ambient') if kind == 'throttle' else None

    return {'runId': sweep['runId'], 'number': sweep['number'], 'kind': kind, 'name': sweep['name'],
            'createdAt': sweep['createdAt'], 'unit': sweep['unit'], 'reach': sweep['reach'],
            'ambient': held, 'ambientText': ambientText(sweep, held) if held is not None else None,
            'lip': {'pressure': lip['pressure'], 'pressureText': ambientText(sweep, lip['pressure'])} if lip else None,
            'separation': separation(sweep), 'columns': shownColumns, 'counts': _counts(sweep['points']),
            'badge': validationStatus.badge(marchModels + structureModels, summary), 'points': points}

def _ramp(start: str, end: str, fraction: float) -> str:

    '''A color `fraction` of the way from `start` to `end`, both '#rrggbb'.'''

    a = [int(start[at:at + 2], 16) for at in (1, 3, 5)]
    b = [int(end[at:at + 2], 16) for at in (1, 3, 5)]

    return '#' + ''.join(f'{round(x + (y - x) * fraction):02x}' for x, y in zip(a, b))

def figure(sweep: dict, mode: str) -> str | None:

    '''

    The sweep's plume boundaries over one another, as plotly figure JSON in the palette of `mode`:
    distance from the exit plane against radius, both in lip radii, the nozzle wall in the accent
    and one line per solved point, its color running with the lip pressure ratio from near the
    text color toward the background. A point past the trusted bound draws dashed. The plot opens
    on the end of the nozzle as long as the reach drawn, or two lip radii, and the whole wall is a
    zoom out away. A throttle sweep names each line by its power level. None before the first
    point is solved.

    '''

    throttle = sweep.get('kind') == 'throttle'

    solved = sorted((point for point in sweep['points'] if point['state'] == 'done' and point.get('result')),
                    key = lambda point: point['result']['lipRatio'])
    lip = sweep.get('lip')
    if not solved or not lip:
        return None
    palette = themeColors.palettes[mode]
    # One hue, from near the text color toward the background with the lip ratio, so the order reads without the legend
    first, last = _ramp(palette['blue'], palette['text'], 0.65), _ramp(palette['blue'], palette['bg'], 0.4)

    data = [{'type': 'scatter', 'mode': 'lines', 'x': lip['wall']['x'], 'y': lip['wall']['r'], 'name': 'nozzle wall',
             'line': {'color': palette['accent'], 'width': 3}, 'hoverinfo': 'skip'}]
    for order, point in enumerate(solved):
        result = point['result']
        color = _ramp(first, last, order / max(1, len(solved) - 1))
        label = pointLabel(sweep, point)
        name = f'{label}, {result["lipRatio"]:.3f}' if throttle else f'{result["lipRatio"]:.3f}, {label}'
        error = (f'mass error {result["drift"]:+.2f} % at {sweep["reach"]:g} lip radii' if result['drift'] is not None
                 else f'mass error {result["nearDrift"]:+.2f} % at {nearReach:g} lip radii')
        if not result['trustworthy']:
            error += ', past the trusted bound'
        named = (f'power {label}, lip ratio {result["lipRatio"]:.3f}' if throttle
                 else f'lip ratio {result["lipRatio"]:.3f}, ambient {label}')
        data.append({'type': 'scatter', 'mode': 'lines', 'x': result['boundary']['x'], 'y': result['boundary']['r'],
                     'name': name, 'customdata': [point['index']] * len(result['boundary']['x']),
                     'line': {'color': color, 'width': 2, 'dash': 'solid' if result['trustworthy'] else 'dash'},
                     'hovertemplate': f'{named}<br>x %{{x:.2f}}, r %{{y:.3f}} lip radii<br>{error}<extra></extra>'})

    axis = {'gridcolor': palette['border'], 'linecolor': palette['border'], 'zeroline': False}
    trusted = all(point['result']['trustworthy'] for point in solved)
    wallStart = min(lip['wall']['x']) if lip['wall']['x'] else -nearReach
    opening = [max(wallStart, -max(nearReach, sweep['reach'])), sweep['reach']]
    # A throttle sweep's plot shares the width with its performance, so its title leaves the name to the view
    title = (f'Plume boundary, {ambientText(sweep, sweep["ambient"])} held' if throttle
             else f'{sweep["name"]}: plume boundary at each ambient')
    title += '' if trusted else '<br><sup>dashed: past the march\'s trusted bound of mass continuity</sup>'
    layout = {
        'title': {'text': title, 'font': {'color': palette['text'], 'size': 16}},
        'font': {'color': palette['text'], 'family': 'Segoe UI, Inter, sans-serif'},
        'paper_bgcolor': palette['surface'], 'plot_bgcolor': palette['bg'],
        'margin': {'l': 70, 'r': 30, 't': 70 if trusted else 85, 'b': 60},
        'xaxis': {**axis, 'title': {'text': 'Distance from the exit plane [lip radii]'}, 'range': opening},
        'yaxis': {**axis, 'title': {'text': 'Radius [lip radii]'}, 'scaleanchor': 'x', 'scaleratio': 1, 'rangemode': 'tozero'},
        'showlegend': True, 'hovermode': 'closest',
        'legend': {'title': {'text': 'Power level, lip pressure ratio' if throttle else 'Lip pressure ratio, ambient'},
                   'bgcolor': 'rgba(0,0,0,0)'},
    }

    return json.dumps({'data': data, 'layout': layout})

def performanceFigure(sweep: dict, mode: str) -> str | None:

    '''

    A throttle sweep's delivered thrust and specific impulse against power level, as plotly figure
    JSON in the palette of `mode`: two panels on one power level axis, one per quantity, each point
    a solved power level. The separation limit draws as a dashed line across both, with the
    criterion's quoted spread shaded below it. None for an ambient sweep or before the first point
    is solved.

    '''

    if sweep.get('kind') != 'throttle':
        return None
    solved = sorted((point for point in sweep['points'] if point['state'] == 'done' and point.get('result')
                     and point['result'].get('thrust') is not None),
                    key = lambda point: point['fraction'])
    if not solved:
        return None
    palette = themeColors.palettes[mode]
    power = [100.0 * point['fraction'] for point in solved]
    thrust = [point['result']['thrust'] / 1e3 for point in solved]
    impulse = [point['result']['specificImpulse'] for point in solved]
    marker = {'color': palette['blue'], 'size': 8, 'line': {'color': palette['bg'], 'width': 2}}
    data = [
        {'type': 'scatter', 'mode': 'lines+markers', 'x': power, 'y': thrust, 'xaxis': 'x', 'yaxis': 'y',
         'line': {'color': palette['blue'], 'width': 2}, 'marker': marker, 'name': 'Delivered thrust',
         'hovertemplate': 'power %{x:.4g} %<br>thrust %{y:.1f} kN<extra></extra>'},
        {'type': 'scatter', 'mode': 'lines+markers', 'x': power, 'y': impulse, 'xaxis': 'x2', 'yaxis': 'y2',
         'line': {'color': palette['blue'], 'width': 2}, 'marker': marker, 'name': 'Delivered Isp',
         'hovertemplate': 'power %{x:.4g} %<br>Isp %{y:.1f} s<extra></extra>'},
    ]

    limit = separation(sweep)
    high = max(105.0, max(power) + 5.0)
    shapes, annotations = [], []
    if limit is not None:
        at, low = 100.0 * limit['fraction'], 100.0 * limit['lowFraction']
        high = max(high, at + 5.0)
        shapes = [
            {'type': 'rect', 'xref': 'x', 'yref': 'paper', 'x0': low, 'x1': at, 'y0': 0.0, 'y1': 1.0,
             'fillcolor': palette['yellow'], 'opacity': 0.14, 'line': {'width': 0}, 'layer': 'below'},
            {'type': 'line', 'xref': 'x', 'yref': 'paper', 'x0': at, 'x1': at, 'y0': 0.0, 'y1': 1.0,
             'line': {'color': palette['yellow'], 'width': 1.5, 'dash': 'dash'}},
        ]
        annotations = [{'x': at, 'y': 1.0, 'xref': 'x', 'yref': 'paper', 'xanchor': 'left', 'yanchor': 'bottom',
                        'showarrow': False, 'font': {'color': palette['textMuted'], 'size': 11},
                        'text': f' separates below {powerText(limit["fraction"])}'}]

    axis = {'gridcolor': palette['border'], 'linecolor': palette['border'], 'zeroline': False}
    powerAxis = {**axis, 'range': [0.0, high]}
    layout = {
        'title': {'text': f'Delivered performance, {ambientText(sweep, sweep["ambient"])} held',
                  'font': {'color': palette['text'], 'size': 16}},
        'font': {'color': palette['text'], 'family': 'Segoe UI, Inter, sans-serif'},
        'paper_bgcolor': palette['surface'], 'plot_bgcolor': palette['bg'],
        'margin': {'l': 70, 'r': 30, 't': 80, 'b': 60},
        'xaxis': {**powerAxis, 'anchor': 'y', 'matches': 'x2', 'showticklabels': False},
        'yaxis': {**axis, 'domain': [0.55, 1.0], 'title': {'text': 'Thrust [kN]'}},
        'xaxis2': {**powerAxis, 'anchor': 'y2', 'title': {'text': 'Power level [% of rated]'}},
        'yaxis2': {**axis, 'domain': [0.0, 0.45], 'title': {'text': 'Isp [s]'}},
        'shapes': shapes, 'annotations': annotations, 'showlegend': False, 'hovermode': 'closest',
    }

    return json.dumps({'data': data, 'layout': layout})
