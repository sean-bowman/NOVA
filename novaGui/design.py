# -- NOVA GUI Design Aids -- #

'''

The Design tab's pieces beyond the schema: the cross-field checks, the wall alloy's sampled
properties and the radiative extension material's store entry.

Both front ends use them, so they raise the same problems in the same words: the web front end
through `checks`, `wallSample` and `extensionEntry`, and the legacy Tkinter form directly. The one
check left to each form is that a required selector option has a value, because it reads the
selector rows themselves; the browser's selector row blocks the run on it.

The checks are warnings: a run with problems asks before it starts. A row is flagged when a problem
names its label in quotes.

The wall alloy's properties come from `NOVA.materials.sampleWallMaterial`, which falls back to
GRCop-42 for a name it does not carry and says so in the result.

Author: Sean Bowman
Date:   11/17/2026

'''

# Standard library imports
import re
import warnings

# Local imports
from . import backend
from . import configSchema

def _words(name: str) -> str:

    '''

    A material store key as words: oxidisingCoated reads oxidising coated, r512eCoatedOxidised
    reads R512E coated oxidised.

    '''

    spaced = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', name).lower()

    return re.sub(r'\br(\d+)e\b', lambda match: f'R{match.group(1)}E', spaced)

def extensionLimits(material: str) -> dict:

    '''The material's temperature limits [degC] by atmosphere, empty if the store has no entry.'''

    try:
        return dict(backend.materialsModule().materialProfile(material)['maxUseTemperatureC'])
    except KeyError:
        return {}

def extensionProperties(material: str) -> dict:

    '''

    What the store carries for an extension material, as the fields it fills: (value, the
    condition the value is for) per config key. A property the store does not carry is absent.

    '''

    materials = backend.materialsModule()
    found = {}
    try:
        condition, value = next(iter(materials.materialProperty(material, 'thermalConductivity').items()))
        found['extensionThermalConductivity'] = (value, condition)
    except KeyError:
        pass
    try:
        condition, value = next(iter(materials.surfaceEmissivity(material).items()))
        found['extensionInnerEmissivity'] = (value, condition)
        found['extensionOuterEmissivity'] = (value, condition)
    except KeyError:
        pass

    return found

def extensionStoreText(material: str) -> str:

    '''The note under the material: its limits and what the store fills, or what it does not.'''

    limits = extensionLimits(material)
    if not limits:
        return f'{material} is not in the material store, so no limit or property is known for it.'

    parts = ['Limit ' + ', '.join(f'{value:.0f} °C {_words(name)}' for name, value in limits.items())]
    properties = extensionProperties(material)
    if 'extensionInnerEmissivity' in properties:
        value, condition = properties['extensionInnerEmissivity']
        parts.append(f'emissivity {value:g} ({_words(condition)})')
    if 'extensionThermalConductivity' in properties:
        value, condition = properties['extensionThermalConductivity']
        parts.append(f'conductivity {value:g} W/m-K ({_words(condition)})')
    missing = [name for key, name in (('extensionInnerEmissivity', 'emissivity'),
                                      ('extensionThermalConductivity', 'conductivity'))
               if key not in properties]
    text = '; '.join(parts) + '.'
    if missing:
        text += f' The store carries no {" or ".join(missing)} for it, so the fields below keep their values.'

    return text

def crossFieldProblems(config: dict) -> list:

    '''

    The problems in a config that only show across fields: a non-positive L*, an extension
    material with no limit in its service atmosphere, cooling channels missing a wall or coolant
    value, a helix with no angle, volutes without channels.

    Parameters:
    -----------
    config : dict
        The form's config, in backend values.

    Returns:
    --------
    list : one sentence per problem, quoting the label of each row it names; empty when the
        config is consistent

    '''

    problems = []

    def isSet(key) -> bool:
        return config.get(key) not in (None, '')

    if isSet('Lstar') and float(config['Lstar']) <= 0:
        problems.append("'Characteristic length L*' must be positive.")

    # The margin report reads the material's limit in the service atmosphere, and a material
    # defines limits only for the atmospheres a source covers
    if config.get('makeRadiativeExtension') in (True, 'on') and isSet('extensionMaterial'):
        limits = extensionLimits(config['extensionMaterial'])
        atmosphere = config.get('extensionAtmosphere')
        if limits and atmosphere not in limits:
            problems.append(f"'Service atmosphere' has no limit for {config['extensionMaterial']}, which "
                            f"has one for {', '.join(_words(name) for name in limits)}.")

    if config.get('makeCoolingChannels') in (True, 'on'):
        needed = ['hotWallThickness', 'shellThickness', 'coolantInitialTemperature', 'coolantInitialPressure']
        missing = [k for k in needed if not isSet(k)]
        if missing:
            problems.append('Cooling channels need: ' + ', '.join(missing) + '.')
        # A helix has no default angle; the backend rejects the run without one
        if config.get('channelType') == 'helical' and not isSet('channelHelixAngle'):
            problems.append("Helical channels need a 'Channel helix angle'.")

    if config.get('makeInletVolute') in (True, 'on') or config.get('makeOutletVolute') in (True, 'on'):
        if config.get('makeCoolingChannels') not in (True, 'on'):
            problems.append('Volute generation requires cooling channels to be enabled.')

    return problems

def _chosenLabel(selector: configSchema.Selector, config: dict) -> str:

    '''

    The option a selector row shows for a config, by the selector row's own rule: the
    first option whose constants the config matches and whose value it sets, then the first whose
    constants it matches, then the row's blank option.

    '''

    def matches(option) -> bool:
        return all(config.get(key) == value for key, value in option.sets.items())

    options = selector.options
    chosen = next((option for option in options
                   if matches(option) and (option.key is None or config.get(option.key) is not None)), None)
    if chosen is None:
        chosen = next((option for option in options if option.sets and matches(option)), None)
    if chosen is None:
        chosen = next((option for option in options if option.label == selector.blank), options[0])

    return chosen.label

def checks(config: dict) -> dict:

    '''

    The cross-field problems of a config, and the rows they name.

    Parameters:
    -----------
    config : dict
        The form's config, in backend values.

    Returns:
    --------
    dict : {'problems': [str], 'flagged': [row ids]}; ids as novaGui.schemaJson gives them

    '''

    merged = {**configSchema.defaultConfig(), **config}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            problems = crossFieldProblems(merged)
    except Exception as exc:                               # noqa: BLE001 -- report rather than fail the form
        problems = [f'The form checks did not run: {type(exc).__name__}: {exc}']

    # A row is flagged when a problem quotes its label
    text = ' '.join(problems).lower()
    flagged = []
    for group in configSchema.groups:
        for item in group.fields:
            if isinstance(item, configSchema.Selector):
                if f"'{_chosenLabel(item, merged).lower()}'" in text:
                    flagged.append('selector:' + item.name)
            elif not item.hidden and f"'{item.label.lower()}'" in text:
                flagged.append(item.key)

    return {'problems': problems, 'flagged': flagged}

def wallSample(name: str, temperatureK: float) -> dict:

    '''

    A wall alloy's properties at one temperature, for the panel under the material row.

    Parameters:
    -----------
    name : str
        The material as the config names it.
    temperatureK : float
        The temperature to sample at [K]. The store clamps it to each property's range.

    Returns:
    --------
    dict : material, temperatureK [K], thermalConductivity [W/m-K], density [kg/m^3],
           elasticModulus [Pa], yieldStrength [Pa], cte [1/K], elongation [%], source, fallback,
           and measured: {property: bool}, False where the value is the room-temperature one

    '''

    with warnings.catch_warnings():
        # An unknown name falls back to GRCop-42 with a warning; the result's 'fallback' says so
        warnings.simplefilter('ignore')
        sample = backend.materialsModule().sampleWallMaterial(name or 'GRCop-42', float(temperatureK))

    keys = ('material', 'temperatureK', 'thermalConductivity', 'density', 'elasticModulus', 'yieldStrength',
            'cte', 'elongation', 'source', 'fallback')
    result = {key: sample[key] for key in keys}
    result['fallback'] = bool(result['fallback'])
    result['measured'] = {key: bool(value) for key, value in dict(sample.get('measured') or {}).items()}

    return result

def extensionEntry(name: str) -> dict:

    '''

    What the material store holds for a radiative extension material.

    Parameters:
    -----------
    name : str
        The extension material as the config names it.

    Returns:
    --------
    dict : {'note': str, 'fill': {config key: value}}; the note is the text under the material, and fill holds the shell properties choosing the material sets

    '''

    fill = {key: float(value) for key, (value, _) in extensionProperties(name).items()}

    return {'note': extensionStoreText(name), 'fill': fill}
