
# -- Config Schema as JSON -- #

'''

The Design form's schema, serialized for the browser, and the evaluation of its dependency
predicates.

novaGui.configSchema describes every config key as a Field or Selector record grouped into
sections. Those records carry Python predicates (`showWhen`, `expandWhen`) that cannot travel
as JSON, so the browser receives each record's static description with a `conditional` flag,
and asks `formState(config)` which rows and sections the current config hides and which
sections it opens. The predicates stay in one place, written once in Python.

Unit conversion travels as data. Every display unit NOVA's registry offers is reduced to the
affine map `si = scale * display + offset`, taken from `NOVA.units.toSI` at two points, so the
browser converts in place without a second table of factors. Temperature is the only affine
dimension; every other offset is zero.

Author: Sean Bowman
Date:   11/16/2026

'''

# Standard library imports
import os

# Local imports
from novaGui import configSchema
from novaGui import units

def _exampleName(path: str) -> str:

    return os.path.splitext(os.path.basename(path))[0]

def _fieldId(spec: configSchema.Field) -> str:

    return spec.key

def _selectorId(selector: configSchema.Selector) -> str:

    return 'selector:' + selector.name

def _groupId(index: int) -> str:

    return f'group{index}'

def _field(spec: configSchema.Field) -> dict:

    '''

    One Field as JSON. Choices become {label, value} pairs; the dimension names the unit table
    entry the row's unit dropdown draws from.

    '''

    return {
        'type':       'field',
        'id':         _fieldId(spec),
        'key':        spec.key,
        'label':      spec.label,
        'kind':       spec.kind,
        'choices':    [{'label': label, 'value': value} for label, value in spec.choices],
        'editable':   spec.editable,
        'default':    spec.default,
        'unit':       spec.unit,
        'dimension':  spec.dimension,
        'help':       spec.help,
        'advanced':   spec.advanced,
        'fold':       configSchema.foldOf(spec),
        'hidden':     spec.hidden,
        'synthetic':  spec.synthetic,
        'optionHelp': {str(value): configSchema.optionHelpText(entry) for value, entry in spec.optionHelp.items()},
        'conditional': spec.showWhen is not None,
    }

def _selector(selector: configSchema.Selector) -> dict:

    '''

    One Selector as JSON: its member Fields, and each Option with the unit its value is entered in.

    '''

    options = []
    for option in selector.options:
        unit = selector.unitFor(option)
        options.append({
            'label':     option.label,
            'key':       option.key,
            'unit':      unit or '',
            'dimension': units.dimensionForUnit(unit) if unit else None,
            'sets':      dict(option.sets),
        })

    return {
        'type':        'selector',
        'id':          _selectorId(selector),
        'name':        selector.name,
        'help':        selector.help,
        'blank':       selector.blank,
        'required':    selector.required,
        'advanced':    selector.advanced,
        'fold':        configSchema.foldOf(selector),
        'members':     [_field(spec) for spec in selector.members],
        'options':     options,
        'conditional': selector.showWhen is not None,
    }

def _unitTable() -> dict:

    '''

    Every display dimension: its SI unit, and for each unit the affine map to SI.

    Returns:
    --------
    dict : {dimension: {'si': str, 'units': [{'unit', 'scale', 'offset'}]}}

    '''

    table = {}
    for dimension, entry in units.DIMENSIONS.items():
        rows = []
        for unit in units.unitsFor(dimension):
            offset = float(units.toSI(0.0, dimension, unit))
            scale = float(units.toSI(1.0, dimension, unit)) - offset
            rows.append({'unit': unit, 'scale': scale, 'offset': offset})
        table[dimension] = {'si': entry['si'], 'units': rows}

    return table

def serializeSchema() -> dict:

    '''

    The whole Design form as JSON: sections in form order, the default config (the shipped
    nozzle), the shipped example engines, the unit table, and the program flags every run forces.

    '''

    groups = []
    for index, group in enumerate(configSchema.groups):
        items = []
        for item in group.fields:
            items.append(_selector(item) if isinstance(item, configSchema.Selector) else _field(item))
        groups.append({
            'id':          _groupId(index),
            'title':       group.title,
            'note':        group.note,
            'collapsed':   group.collapsed,
            'items':       items,
            'conditional': group.showWhen is not None,
        })

    return {
        'groups':       groups,
        'defaults':     configSchema.defaultConfig(),
        'examples':     [{'title': title, 'name': _exampleName(path)} for title, path in configSchema.exampleConfigs()],
        'units':        _unitTable(),
        'advancedFold': configSchema.advancedFold,
        'forcedFlags':  list(configSchema.forcedFlags),
    }

def examplePath(name: str) -> str | None:

    '''

    The path of a shipped example by its file stem, or None. Only names the examples folder
    lists are accepted, so a request cannot reach any other file.

    '''

    for _, path in configSchema.exampleConfigs():
        if _exampleName(path) == name:
            return path
    return None

def _test(predicate, config: dict) -> bool:

    '''

    A dependency predicate's verdict. A predicate that raises on a half-typed config reads as
    True, so the row stays visible rather than vanishing while the user edits.

    '''

    if predicate is None:
        return True
    try:
        return bool(predicate(config))
    except Exception:                                      # noqa: BLE001 -- show rather than hide
        return True

def formState(config: dict) -> dict:

    '''

    Which rows and sections a config hides, and which sections it asks to open.

    Parameters:
    -----------
    config : dict
        The form's current config, in backend values.

    Returns:
    --------
    dict : {'hidden': [row or section ids], 'expand': [section ids]}

    '''

    hidden, expand = [], []
    for index, group in enumerate(configSchema.groups):
        if not _test(group.showWhen, config):
            hidden.append(_groupId(index))
        if group.expandWhen is not None and _test(group.expandWhen, config):
            expand.append(_groupId(index))
        for item in group.fields:
            if isinstance(item, configSchema.Selector):
                if not _test(item.showWhen, config):
                    hidden.append(_selectorId(item))
            elif not _test(item.showWhen, config):
                hidden.append(_fieldId(item))

    return {'hidden': hidden, 'expand': expand}
