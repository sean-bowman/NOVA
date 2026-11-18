# -- NOVA Web Design Aids -- #

'''

The Design tab's server-side pieces beyond the schema: the cross-field checks, the wall alloy's
sampled properties and the radiative extension material's store entry.

The checks and the extension entry are the Tkinter Design tab's own code
(`novaGui.tabs.configTab.ConfigTab`): `validate`, `_extensionLimits`, `_extensionProperties` and
`_extensionStoreText` run here on a stand-in object that holds the browser's config, and no Tk
window is created. Both front ends therefore raise the same problems in the same words.

`validate` also checks that a required selector option has a value. The browser's selector row
makes that check itself and blocks the run on it, so the stand-in hands `validate` no selector
rows and the problem is not reported twice.

The checks are warnings, as in the Tkinter form: a run with problems asks before it starts. A row
is flagged when a problem names its label in quotes, the Tkinter form's rule.

The wall alloy's properties come from `NOVA.materials.sampleWallMaterial`, which falls back to
GRCop-42 for a name it does not carry and says so in the result.

Author: Sean Bowman
Date:   11/17/2026

'''

# Standard library imports
import warnings

# Local imports
from novaGui import configSchema

# The ConfigTab members the stand-in carries: the checks and the extension store helpers
_borrowed = ('validate', '_extensionLimits', '_extensionProperties', '_extensionStoreText')

def _designClass() -> type:

    '''

    A class with the borrowed ConfigTab members and nothing that touches Tk. The Tkinter tabs are
    imported here rather than with this module, as novaWeb.analysis imports its tab, so the server
    starts without them.

    '''

    from novaGui.tabs.configTab import ConfigTab

    return type('DesignChecks', (), {name: vars(ConfigTab)[name] for name in _borrowed})

def _standIn(config: dict | None = None):

    '''

    A stand-in ConfigTab over a config: `getConfig` returns it with the schema defaults under it,
    and there are no selector rows (see the module docstring).

    '''

    standIn = _designClass()()
    merged = {**configSchema.defaultConfig(), **(config or {})}
    standIn.getConfig = lambda: dict(merged)
    standIn._selectors = []

    return standIn

def _chosenLabel(selector: configSchema.Selector, config: dict) -> str:

    '''

    The option a selector row shows for a config, by novaGui.widgets.SelectorRow.set's rule: the
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
    dict : {'problems': [str], 'flagged': [row ids]}; ids as novaWeb.schemaJson gives them

    '''

    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            problems = list(_standIn(config).validate())
    except Exception as exc:                               # noqa: BLE001 -- report rather than fail the form
        problems = [f'The form checks did not run: {type(exc).__name__}: {exc}']

    # The Tkinter form's rule: a row is flagged when a problem quotes its label
    text = ' '.join(problems).lower()
    merged = {**configSchema.defaultConfig(), **config}
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

    from novaGui import backend

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
    dict : {'note': str, 'fill': {config key: value}}; the note is the Tkinter form's text under
           the material, and fill holds the shell properties choosing the material sets

    '''

    standIn = _standIn()
    fill = {key: float(value) for key, (value, _) in standIn._extensionProperties(name).items()}

    return {'note': standIn._extensionStoreText(name), 'fill': fill}
