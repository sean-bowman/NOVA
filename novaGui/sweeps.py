
# -- NOVA GUI Trade Sweeps -- #

'''

Trade sweeps: one run per value of a config field, or one per pair of values of two fields.

The browser sends a sweep as a base config, the fields it sweeps with their values in backend (SI)
values, and the display unit each field's values were entered in. `build` checks it against the
Design form's schema (novaGui.configSchema) and lays out its points: one per value of the first
field, or with a second field one per pair, the first field varying fastest, so the runs of one
value of the second field finish together. A point's config is the base config with its values
set (`pointConfig`).

The session (novaGui.session) queues a sweep's points in order and marks each as its run goes:
queued, running, done, failed or cancelled. A point whose run fails or is cancelled keeps the
reason, and the queue goes on to the next point. A sweep's runs carry its id and their point's
index, and stay in the run store until the sweep is deleted, as named runs do.

`table` reads a sweep's points against the kept runs: each point's swept values, its state and its
run, and the headline numbers of the run (novaGui.analysis.headline), which the worker records as
the run finishes. `figure` draws one headline number against the first swept field, one line per
value of the second, as a plotly figure in the GUI's palette.

A sweep reports the numbers NOVA computed for each point and adds no model of its own. Each
number's validation status is that of the model behind it (novaGui.validationStatus), which the
browser reads from the result table of one of the sweep's runs.

Author: Sean Bowman
Date:   11/20/2026

'''

# Standard library imports
import itertools
import json
import math
import time

# Local imports
from . import configSchema
from . import themeColors
from . import units

maxPoints = 64                  # runs one sweep queues
maxSeries = 6                   # values of a second field, each a line on the sweep's plot
nameLength = 80                 # [characters] the longest name a sweep takes
sweepableKinds = ('float', 'int', 'floatText', 'choice', 'bool')
pointStates = ('queued', 'running', 'done', 'failed', 'cancelled')
seriesColors = ('accent', 'blue', 'green', 'purple', 'yellow', 'cyan')   # palette roles, in order

def sweepableFields() -> dict:

    '''

    Every config field a sweep can vary, by key: the numbers, the choices and the switches that have
    a row on the form.

    '''

    return {spec.key: spec for spec in configSchema.allFields()
            if spec.kind in sweepableKinds and not spec.hidden and not spec.synthetic}

def _number(spec: configSchema.Field, raw) -> float | int:

    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        raise ValueError(f'{spec.label}: {raw!r} is not a number')
    if spec.kind == 'int':
        if not float(raw).is_integer():
            raise ValueError(f'{spec.label}: {raw!r} is not an integer')
        return int(raw)

    return float(raw)

def _value(spec: configSchema.Field, raw):

    '''A swept value checked against its field: a number, one of its choices, or a switch.'''

    if spec.kind in ('float', 'floatText', 'int'):
        return _number(spec, raw)
    if spec.kind == 'bool':
        if not isinstance(raw, bool):
            raise ValueError(f'{spec.label}: {raw!r} is not on or off')
        return raw
    if any(raw == value for _, value in spec.choices):
        return raw
    if spec.editable and isinstance(raw, str) and raw.strip():
        return raw.strip()

    raise ValueError(f'{spec.label}: {raw!r} is not one of its choices')

def valueText(field: dict, value) -> str:

    '''

    A swept value as the sweep's table shows it: a number in the unit it was entered in, a
    choice's label, or on and off.

    '''

    kind = field['kind']
    if kind == 'bool':
        return 'on' if value else 'off'
    if kind == 'choice':
        spec = sweepableFields().get(field['key'])
        return spec.valueToLabel(value) if spec is not None else str(value)
    shown = units.fromSI(float(value), field['dimension'], field['unit']) if field['dimension'] else float(value)
    text = f'{shown:.6g}'

    return f'{text} {field["unit"]}' if field['unit'] else text

def shownValue(field: dict, value):

    '''A swept value on the plot's axis: a number in the unit it was entered in, else its text.'''

    if field['kind'] in ('float', 'floatText', 'int'):
        return units.fromSI(float(value), field['dimension'], field['unit']) if field['dimension'] else float(value)

    return valueText(field, value)

def defaultName(fields: list) -> str:

    '''A sweep's name when it is given none: the fields it sweeps.'''

    labels = [field['label'] for field in fields]

    return f'{labels[0]} sweep' if len(labels) == 1 else f'{labels[0]} by {labels[1]}'

def build(request: dict) -> dict:

    '''

    A sweep from what the browser sends, checked and laid out, without its id.

    Parameters:
    -----------
    request : dict
        {'name': str, 'config': dict, 'fields': [{'key': str, 'unit': str, 'values': list}]}: the
        base config and up to two fields, each with its values in backend values and the display
        unit they were entered in ('' for a field without one).

    Returns:
    --------
    dict : {'name', 'createdAt', 'config', 'fields', 'points'}. Each field is {'key', 'label',
        'kind', 'dimension', 'unit', 'values', 'texts'}; each point is {'index', 'at', 'values',
        'state', 'runId', 'error'}, `at` the index of its value in each field.

    Raises:
    -------
    ValueError : with the reason, for a sweep the form could not run

    '''

    if not isinstance(request, dict):
        raise ValueError('a sweep must be an object')
    config = request.get('config')
    if not isinstance(config, dict):
        raise ValueError('a sweep must carry the config it starts from')
    requested = request.get('fields')
    if not isinstance(requested, list) or not 1 <= len(requested) <= 2:
        raise ValueError('a sweep varies one field, or two')

    known = sweepableFields()
    fields = []
    for entry in requested:
        if not isinstance(entry, dict) or entry.get('key') not in known:
            raise ValueError(f'{entry.get("key") if isinstance(entry, dict) else entry!r} is not a field a sweep can vary')
        spec = known[entry['key']]
        if any(field['key'] == spec.key for field in fields):
            raise ValueError(f'{spec.label} is swept twice')
        raw = entry.get('values')
        if not isinstance(raw, list) or len(raw) < 2:
            raise ValueError(f'{spec.label}: give at least two values')
        values = [_value(spec, value) for value in raw]
        if any(a == b for a, b in itertools.combinations(values, 2)):
            raise ValueError(f'{spec.label}: a value is given twice')
        unit = str(entry.get('unit') or '')
        if spec.dimension:
            unit = unit or units.siUnit(spec.dimension)
            if unit not in units.unitsFor(spec.dimension):
                raise ValueError(f'{spec.label}: {unit!r} is not a unit of {spec.dimension}')
        else:
            unit = spec.unit or ''
        field = {'key': spec.key, 'label': spec.label, 'kind': spec.kind, 'dimension': spec.dimension,
                 'unit': unit, 'values': values}
        field['texts'] = [valueText(field, value) for value in values]
        fields.append(field)

    if len(fields) == 2 and len(fields[1]['values']) > maxSeries:
        raise ValueError(f'{fields[1]["label"]}: a second field takes at most {maxSeries} values, one line each on the plot')
    count = math.prod(len(field['values']) for field in fields)
    if count > maxPoints:
        raise ValueError(f'the sweep makes {count} runs; a sweep queues at most {maxPoints}')

    name = ' '.join(str(request.get('name') or '').split()) or defaultName(fields)
    if len(name) > nameLength:
        raise ValueError(f'a sweep name takes at most {nameLength} characters')

    # The first field varies fastest, so one value of the second field finishes before the next
    points = []
    ranges = [range(len(field['values'])) for field in fields]
    for at in itertools.product(*reversed(ranges)):
        at = list(reversed(at))
        points.append({'index': len(points), 'at': at,
                       'values': {field['key']: field['values'][i] for field, i in zip(fields, at)},
                       'state': 'queued', 'runId': None, 'error': ''})

    return {'name': name, 'createdAt': time.time(), 'config': dict(config), 'fields': fields, 'points': points}

def pointConfig(sweep: dict, point: dict) -> dict:

    '''The config a point runs: the sweep's base config with the point's values set.'''

    return {**sweep['config'], **point['values']}

def pointLabel(sweep: dict, point: dict) -> str:

    '''A point as the queue names it: the sweep, the point's place, and its values.'''

    texts = ', '.join(f'{field["label"]} {field["texts"][i]}' for field, i in zip(sweep['fields'], point['at']))

    return f'{sweep["name"]}, {point["index"] + 1} of {len(sweep["points"])}: {texts}'

def numberValue(text) -> float | None:

    '''A headline number's text as a float, or None.'''

    try:
        value = float(str(text).replace(',', ''))
    except (TypeError, ValueError):
        return None

    return value if math.isfinite(value) else None

def _counts(points: list) -> dict:

    counts = {state: 0 for state in pointStates}
    for point in points:
        counts[point['state']] = counts.get(point['state'], 0) + 1

    return counts

def table(sweep: dict, records: dict) -> dict:

    '''

    A sweep as the browser's sweep view reads it.

    Parameters:
    -----------
    sweep : dict
        The sweep, as `build` laid it out with its id and its points' states.
    records : dict
        {runId: novaGui.session.RunRecord}, the kept runs.

    Returns:
    --------
    dict : {'sweepId', 'name', 'createdAt', 'config', 'fields', 'numbers', 'counts', 'points'}.
        `numbers` lists the headline numbers its runs report, {'key', 'label', 'unit'}, in the
        order the result pane draws them. Each point adds 'texts' (its values as the table shows
        them), 'kept' (its run is still kept) and 'numbers' ({key: {'text', 'value', 'tone'}}).

    '''

    catalog = {}
    points = []
    for point in sweep['points']:
        record = records.get(point['runId']) if point['runId'] is not None else None
        numbers = {}
        for number in (getattr(record, 'numbers', None) or []):
            catalog.setdefault(number['key'], {'key': number['key'], 'label': number['label'], 'unit': number['unit']})
            numbers[number['key']] = {'text': number['value'], 'value': numberValue(number['value']),
                                      'tone': number.get('tone', '')}
        points.append({**point, 'texts': [field['texts'][i] for field, i in zip(sweep['fields'], point['at'])],
                       'kept': record is not None, 'numbers': numbers})

    return {'sweepId': sweep['sweepId'], 'name': sweep['name'], 'createdAt': sweep['createdAt'],
            'config': sweep['config'], 'fields': sweep['fields'], 'numbers': list(catalog.values()),
            'counts': _counts(sweep['points']), 'points': points}

def figure(sweep: dict, records: dict, numberKey: str, mode: str) -> str | None:

    '''

    One headline number against the first swept field, one line per value of the second, as
    plotly figure JSON in the palette of `mode`. A point without the number (still to run, failed,
    cancelled or deleted) leaves a gap. Each point carries its run's id as `customdata`, None where
    the run is not kept, so a click can show the run. None when no point has the number.

    '''

    shown = table(sweep, records)
    number = next((entry for entry in shown['numbers'] if entry['key'] == numberKey), None)
    if number is None:
        return None
    palette = themeColors.palettes[mode]
    first = sweep['fields'][0]
    second = sweep['fields'][1] if len(sweep['fields']) > 1 else None
    numeric = first['kind'] in ('float', 'floatText', 'int')
    yTitle = f'{number["label"]} [{number["unit"]}]' if number['unit'] else number['label']
    xTitle = f'{first["label"]} [{first["unit"]}]' if numeric and first['unit'] else first['label']

    data = []
    for series in range(len(second['values']) if second else 1):
        members = sorted((point for point in shown['points'] if not second or point['at'][1] == series),
                         key = lambda point: point['at'][0])
        x, y, text, runs = [], [], [], []
        for point in members:
            value = point['numbers'].get(numberKey, {}).get('value')
            x.append(shownValue(first, first['values'][point['at'][0]]))
            y.append(value)
            runs.append(point['runId'] if point['kept'] else None)
            run = f'run {point["runId"]}' if point['kept'] else point['state']
            text.append(f'{", ".join(point["texts"])}<br>{number["label"]} '
                        f'{point["numbers"].get(numberKey, {}).get("text", "--")} {number["unit"]} ({run})')
        color = palette[seriesColors[series % len(seriesColors)]]
        data.append({'type': 'scatter', 'mode': 'lines+markers', 'x': x, 'y': y, 'text': text, 'customdata': runs,
                     'name': second['texts'][series] if second else number['label'],
                     'hovertemplate': '%{text}<extra></extra>', 'connectgaps': False,
                     'line': {'color': color, 'width': 2},
                     'marker': {'color': color, 'size': 8, 'line': {'color': palette['surface'], 'width': 2}}})

    axis = {'gridcolor': palette['border'], 'linecolor': palette['border'], 'zeroline': False}
    title = f'{number["label"]} against {first["label"].lower()}'
    layout = {
        'title': {'text': title, 'font': {'color': palette['text'], 'size': 16}},
        'font': {'color': palette['text'], 'family': 'Segoe UI, Inter, sans-serif'},
        'paper_bgcolor': palette['surface'], 'plot_bgcolor': palette['bg'],
        'margin': {'l': 70, 'r': 30, 't': 60, 'b': 60},
        'xaxis': {**axis, 'title': {'text': xTitle}, **({} if numeric else {'type': 'category'})},
        'yaxis': {**axis, 'title': {'text': yTitle}},
        'showlegend': second is not None, 'hovermode': 'closest',
        'legend': {'title': {'text': second['label'] if second else ''}, 'bgcolor': 'rgba(0,0,0,0)'},
    }

    return json.dumps({'data': data, 'layout': layout})
