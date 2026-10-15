
# -- NOVA Configuration Schema -- #

'''

Field metadata for the config tab, ordered and grouped to mirror
src/NOVA/assets/NOVANozzle.json. Every key that configuration carries appears
here exactly once so the dictionary the GUI hands to Nozzle.setInputs() is
always complete.

Each field is a Field record:

    key        config-dictionary key, verbatim
    label      human label shown in the form
    kind       'bool' | 'int' | 'float' | 'text' | 'choice' | 'floatText'
               ('floatText' parses as a float when it can, else stays a string)
    choices    for 'choice': a list of (displayLabel, backendValue) pairs. A bare
               string is shorthand for a pair with the same label and value. The
               form shows the labels; get() returns the backend value.
    editable   for 'choice': True lets the user type a value outside the list
    default    backend value pre-filled on a fresh form (None renders blank). The
               shipped NOVANozzle.json overrides it at import, so a fresh form is
               the shipped nozzle; the value written here is the fallback for a
               key that file leaves out.
    unit       short unit string appended to the label, or ''
    help       one-line tooltip
    showWhen   predicate over the current config dict; the row is hidden when it
               returns False
    synthetic  True for a form-only helper that does not map to a config key; the
               config tab drops it on the way out. No field is one at present.
    advanced   True puts the field in its group's Advanced settings fold, which
               opens on demand. Every advanced field defaults to the shipped
               nozzle's value, so a design can be made from the main fields alone.
    fold       the name of another fold inside the group the field sits in, such
               as one volute's settings; None for the group's own rows
    hidden     True keeps the key in every config the form writes, at its loaded
               or default value, without a row: a program flag the GUI sets itself

A Selector is one form row standing for several keys that are alternatives to one
another: thrust or engine mass flow, an area ratio or an exit pressure. Its first
column picks an Option, the second takes that option's value and the third its
unit. Choosing an option writes the value to the option's key, any constants the
option fixes (a truncation mode), and None to every other key the row holds, so
two alternatives cannot both be set. The Fields a Selector holds are its members;
they carry the keys, kinds, help and defaults as any other field does.

Groups carry `collapsed`, `showWhen` (hide the whole section) and `expandWhen`
(auto-open the section when the predicate first becomes true).

Author: Sean Bowman
Date:   08/28/2026

'''

import json
import os
from dataclasses import dataclass, field

# The configuration NOVA ships and `Nozzle().generateNozzle()` builds when given no path
shippedConfigPath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 'src', 'NOVA', 'assets', 'NOVANozzle.json')

@dataclass
class Field:

    '''

    One editable configuration parameter.

    '''

    key: str
    label: str
    kind: str
    choices: list = field(default_factory = list)
    default: object = None
    unit: str = ''
    help: str = ''
    editable: bool = False
    showWhen: object = None
    synthetic: bool = False
    advanced: bool = False
    fold: str = None
    hidden: bool = False
    dimension: object = None      # set in __post_init__ from `unit`; drives the unit dropdown

    def __post_init__(self):

        normalized = []
        for entry in self.choices:
            if isinstance(entry, (tuple, list)):
                normalized.append((str(entry[0]), entry[1]))
            else:
                normalized.append((str(entry), entry))
        self.choices = normalized

        if self.kind in ('float', 'int', 'floatText') and self.unit:
            from .units import dimensionForUnit
            self.dimension = dimensionForUnit(self.unit)

    def choiceLabels(self) -> list:

        '''

        Display labels for the combobox, in order.

        '''

        return [label for label, _ in self.choices]

    def labelToValue(self, label: str):

        '''

        Backend value for a display label. An unrecognized label is returned
        unchanged so editable choice fields pass through custom input.

        '''

        for candidateLabel, value in self.choices:
            if candidateLabel == label:
                return value
        return label

    def valueToLabel(self, value) -> str:

        '''

        Display label for a backend value. An unrecognized value is shown
        verbatim so a loaded config with an off-list value still renders.

        '''

        for label, candidateValue in self.choices:
            if candidateValue == value:
                return label
        return '' if value is None else str(value)

@dataclass
class Option:

    '''

    One choice in a Selector row.

    '''

    label: str                    # what the first column shows
    key: str = None               # config key the entered value is written to; None takes no value
    unit: str = None              # unit of the entered value; None takes the member field's own
    sets: dict = field(default_factory = dict)    # config keys the choice fixes, such as a mode

@dataclass
class Selector:

    '''

    One form row for several alternative config keys: an option dropdown, a value and its unit.

    '''

    name: str                     # what messages call the row
    members: list                 # the Fields the row holds
    options: list                 # Option records, in dropdown order
    help: str = ''
    blank: str = ''               # option shown when a config sets none of the row's values
    required: bool = True         # False lets the chosen option's value stay blank
    advanced: bool = False
    fold: str = None
    showWhen: object = None

    def member(self, key: str) -> Field:

        '''

        The member Field for a config key.

        '''

        for spec in self.members:
            if spec.key == key:
                return spec
        raise KeyError(key)

    def unitFor(self, option: Option) -> str:

        '''

        The unit an option's value is entered in: its own, else its member field's, else none.

        '''

        if option.unit is not None:
            return option.unit
        return self.member(option.key).unit if option.key else ''

    def keys(self) -> list:

        '''

        Every config key the row writes, in member order.

        '''

        return [spec.key for spec in self.members]

advancedFold = 'Advanced settings'

def foldOf(item) -> str:

    '''

    The fold a Field or Selector sits in: its own, the Advanced settings fold, or None for the
    group's own rows.

    '''

    return item.fold or (advancedFold if item.advanced else None)

@dataclass
class Group:

    '''

    A titled, collapsible block of fields in the config tab. `fields` holds Field and Selector
    records in form order; advanced ones go to the group's Advanced settings fold.

    '''

    title: str
    fields: list
    collapsed: bool = False
    note: str = ''
    showWhen: object = None
    expandWhen: object = None

# -- Program option flags forced on for every GUI run -- #

# Every GUI run writes every figure and data file into a staging folder, and the
# Export tab copies the ones chosen to the output folder, so the runner sets these
# and the form has no row for them.
forcedFlags = ('export', 'plotsEnabled')

# -- Dependency predicates -- #

def _coolingOn(config: dict) -> bool:
    return config.get('makeCoolingChannels') in (True, 'on')

def _rectangularChannels(config: dict) -> bool:
    return _coolingOn(config) and config.get('channelType') == 'rectangular'

def _helicalChannels(config: dict) -> bool:
    return _coolingOn(config) and config.get('channelType') == 'helical'

def _rectangularOrHelicalChannels(config: dict) -> bool:
    return _rectangularChannels(config) or _helicalChannels(config)

def _manualChannelSizing(config: dict) -> bool:
    return _coolingOn(config) and config.get('channelSizingMode') == 'manual'

def _anyVolute(config: dict) -> bool:
    return (config.get('makeInletVolute') in (True, 'on')
            or config.get('makeOutletVolute') in (True, 'on'))

def _inletVoluteOn(config: dict) -> bool:
    return config.get('makeInletVolute') in (True, 'on')

def _outletVoluteOn(config: dict) -> bool:
    return config.get('makeOutletVolute') in (True, 'on')

def _radiativeExtensionOn(config: dict) -> bool:
    return config.get('makeRadiativeExtension') in (True, 'on')

def _filmCoolingOn(config: dict) -> bool:
    return config.get('filmCooling') in (True, 'on')

def _entrainmentModelOn(config: dict) -> bool:
    return _filmCoolingOn(config) \
           and config.get('filmCoolingModel') == 'sp8124Entrainment'

def _searchedContour(config: dict) -> bool:
    return config.get('divergingSectionType') in ('top', 'toc')

# -- Propellant choices -- #

# Canonical rocketcea keys, mapped from friendly labels. The field stays
# editable so any exact rocketcea card key or ceaInterface alias also works.
fuelChoices = [
    ('LH2', 'LH2'), ('CH4', 'CH4'), ('RP-1', 'RP_1'), ('Ethanol', 'C2H5OH'),
    ('Methanol', 'CH3OH'), ('HTPB', 'HTPB'), ('HDPE', 'HDPE'), ('GH2', 'GH2'),
    ('GCH4', 'GCH4'), ('MMH', 'MMH'), ('Hydrazine (N2H4)', 'N2H4'), ('UDMH', 'UDMH'),
    ('Aerozine 50', 'A50'), ('Ammonia (NH3)', 'NH3'), ('Propane', 'Propane'),
    ('Propylene', 'Propylene'), ('Jet-A', 'JetA'), ('JP-10', 'JP10'),
]
oxidizerChoices = [
    ('LOX', 'LOX'), ('GOX', 'GOX'), ('N2O', 'N2O'), ('N2O4 / NTO', 'N2O4'),
    ('MON-3', 'MON3'), ('MON-15', 'MON15'), ('MON-25', 'MON25'), ('H2O2 (HTP)', 'H2O2'),
    ('IRFNA', 'IRFNA'), ('HNO3', 'HNO3'), ('Air', 'AIR'), ('F2', 'F2'), ('ClF5', 'CLF5'),
]

# -- Wall alloy choices -- #

# Canonical names must match materials.availableWallMaterials(); the config info panel samples
# k(T), density and modulus from that module for the selected alloy. Copper alloys first.
materialChoices = [
    ('GRCop-42 (Cu-Cr-Nb)', 'GRCop-42'),
    ('CuCrZr (C18150)', 'CuCrZr'),
    ('OFHC copper (C10100)', 'OFHC Copper'),
    ('NARloy-Z (Cu-Ag-Zr)', 'NARloy-Z'),
    ('AlSi10Mg', 'AlSi10Mg'),
    ('Aluminium 6061-T6', 'Al 6061-T6'),
    ('Inconel 718', 'Inconel 718'),
    ('Inconel 625', 'Inconel 625'),
    ('316L stainless', '316L'),
    ('Ti-6Al-4V', 'Ti-6Al-4V'),
]

# -- Radiative extension materials -- #

# The hot-structure entries of materials.availableMaterials(): the refractory metal, the ceramic
# matrix and carbon composites, and graphite. The store's polymers, ablatives and thermal barrier
# coating are not radiation-cooled shells. The names must match the store, which tests hold.
extensionMaterialChoices = [
    ('C103 (Nb-10Hf-1Ti)', 'C103'),
    ('Carbon-carbon (2D)', 'Carbon-Carbon (2D)'),
    ('C/SiC', 'C/SiC'),
    ('SiC/SiC', 'SiC/SiC'),
    ('ATJ graphite', 'ATJ Graphite'),
    ('None (no margin report)', None),
]

groups = [

    Group('Contour Definition', [
        Field('divergingSectionType', 'Diverging section type', 'choice',
              choices = [('Truncated ideal contour (tic)', 'tic'),
                         ('Thrust-optimized parabola (top)', 'top'),
                         ('Thrust-optimized contour (toc)', 'toc'),
                         ('Conical (cone)', 'cone')], default = 'tic',
              help = 'tic and top are method-of-characteristics contours evaluated directly; toc '
                     'searches over them for the shortest length at the requested performance. '
                     'cone is a straight 15 degree half-angle cone.'),
        Field('chamberDiameter', 'Chamber diameter', 'float', default = 0.18, unit = 'm',
              help = 'Diameter of the chamber at the converging inlet. Sets the contraction ratio.'),
        Selector('Chamber length', [
            Field('Lstar', 'Characteristic length L*', 'float', default = 1.0, unit = 'm',
                  help = 'Chamber volume over throat area, injector face to throat. Sets the cylindrical '
                         'barrel length after the converging section volume is subtracted. The contour '
                         'is resampled at equal arc length, so a long barrel takes points from the '
                         'diverging section: raise the contour point count to compensate.'),
            Field('chamberLength', 'Chamber barrel length', 'float', default = None, unit = 'm',
                  help = 'Cylindrical barrel length, given directly instead of through L*. Zero or '
                         'blank builds no barrel.'),
            ], options = [
                Option('Characteristic length L*', key = 'Lstar'),
                Option('Chamber barrel length', key = 'chamberLength'),
            ], blank = 'Chamber barrel length', required = False,
            help = 'The cylindrical chamber barrel ahead of the converging section, sized through '
                   'the characteristic length L* or given as a length directly. Blank builds no barrel.'),
        Field('lengthFraction', 'Length fraction', 'floatText', advanced = True, default = 0.8,
              help = 'Truncated ideal contour length as a fraction of a 15 deg conical nozzle of '
                     'the same area ratio, which is how NASA SP-8120 defines percent bell. Any '
                     'text instead of a number, such as optimize, searches for the length fraction '
                     'that maximizes the thrust coefficient.'),
        Field('divergingSectionDesignVariables', 'Design vector', 'text', advanced = True,
              default = None, showWhen = _searchedContour,
              help = 'Pins a thrust-optimized wall instead of searching for one: four numbers, '
                     'the inflection and exit wall angles in degrees then the inflection and '
                     'exit tensions, separated by commas. Blank runs the search.'),
        Field('convergingSectionAngle', 'Converging wall angle at throat', 'float', advanced = True,
              default = 30.0, unit = 'deg',
              help = 'Wall angle of the converging section where it meets the throat.'),
        Field('throatInletCurvature', 'Throat inlet curvature', 'float', advanced = True,
              default = 1.5,
              help = 'Radius of curvature of the throat inlet arc, as a multiple of the throat '
                     'radius. NASA SP-8120 takes this above 0.6.'),
        Field('throatOutletCurvature', 'Throat outlet curvature', 'float', advanced = True,
              default = 0.382,
              help = 'Radius of curvature of the throat outlet arc, as a multiple of the throat '
                     'radius. The default is the Rao value.'),
        Field('numContourPoints', 'Contour points', 'int', advanced = True, default = 100,
              help = 'Number of points in the resampled wall contour.'),
        Field('numCharacteristics', 'Characteristics', 'int', advanced = True, default = 50,
              help = 'Characteristics launched from the throat arc, which sets the mesh resolution '
                     'of the whole solve. At the default the exit wall angle carries about 2 '
                     'percent of mesh error and the thrust coefficient about 1 percent.'),
        Field('transonicModel', 'Transonic model', 'choice', advanced = True,
              choices = [('Sauer', 'sauer'), ('Second order', 'secondOrder'),
                         ('Small radius', 'smallRadius')], default = 'sauer',
              help = 'Which starting line the characteristics net is launched from. Sauer is the '
                     'first-order transonic solution and is the default. The second-order and '
                     'small-radius lines are the ones to reach for at a sharp throat, where the '
                     'Sauer expansion is weakest.'),
        Field('nearWallStateModel', 'Near-wall state', 'choice', advanced = True,
              choices = [('One-dimensional', 'oneDimensional'), ('Transonic', 'transonic')],
              default = 'oneDimensional',
              help = 'Where the converging wall state comes from. One-dimensional puts the sonic '
                     'point at the geometric throat. Transonic carries the starting line\'s own '
                     'solution over the entrant arc, so the wall goes sonic ahead of the throat '
                     'and the state joins the characteristics net without a jump.'),
        Field('gammaModel', 'Ratio of specific heats', 'choice', advanced = True,
              choices = [('Chamber value', 'chamber'),
                         ('Effective, fitted to the design point', 'effective')],
              default = 'chamber',
              help = 'A real exhaust recombines as it expands and has no single ratio of '
                     'specific heats, so the contour solve picks one. The chamber value is '
                     'the default. The effective '
                     'value is fitted so the pressure ratio and the area ratio agree with '
                     'the thermochemistry at the design point: it cuts the pressure error '
                     'threefold and biases the gas temperature cold, which undersizes a '
                     'cooling jacket. Choose it for contour and performance work, not for '
                     'a jacket. Both values are reported either way.'),
    ]),

    Group('Combustion', [
        Field('Fuel', 'Fuel', 'choice', choices = fuelChoices, default = 'LH2', editable = True,
              help = 'CEA fuel. Any exact rocketcea card key or ceaInterface alias can also be typed.'),
        Field('Oxidizer', 'Oxidizer', 'choice', choices = oxidizerChoices, default = 'LOX', editable = True,
              help = 'CEA oxidizer. Any exact rocketcea card key or ceaInterface alias can also be typed.'),
        Field('OFRatio', 'O/F ratio', 'floatText', default = 5.5,
              help = "Oxidizer to fuel mass ratio, or 'maxisp' to let CEA optimize it."),
        Field('chamberPressure', 'Chamber pressure', 'float', default = 6894757.0, unit = 'Pa',
              help = 'Chamber stagnation pressure. 6.895 MPa is 1000 psia.'),
        Selector('Engine size', [
            Field('thrust', 'Thrust', 'float', default = 100000.0, unit = 'N',
                  help = 'Thrust the engine is sized to deliver.'),
            Field('engineMassFlow', 'Engine mass flow', 'float', default = None, unit = 'kg/s',
                  help = 'Total propellant mass flow the engine is sized to pass.'),
            ], options = [
                Option('Thrust', key = 'thrust'),
                Option('Engine mass flow', key = 'engineMassFlow'),
            ], blank = 'Thrust',
            help = 'What sizes the engine: the thrust it delivers or the propellant flow it passes.'),
        Selector('Nozzle expansion', [
            Field('expansionRatio', 'Expansion ratio', 'float', default = 40.0,
                  help = 'One-dimensional CEA area ratio the wall is cut at.'),
            Field('targetExitPressure', 'Target exit pressure', 'float', default = None, unit = 'Pa',
                  help = 'Design exit static pressure. CEA resolves it to the area ratio that '
                         'delivers it, and the wall is cut there.'),
            ], options = [
                Option('Expansion ratio', key = 'expansionRatio'),
                Option('Target exit pressure', key = 'targetExitPressure'),
            ], blank = 'Expansion ratio',
            help = 'Where the nozzle is cut: at a one-dimensional area ratio, or at the area ratio '
                   'that expands to a design exit pressure.'),
        Field('fuelInitialTemperature', 'Fuel inlet temperature', 'float', advanced = True,
              default = 20.27, unit = 'K',
              help = 'Fuel temperature at the injector.'),
        Field('oxidizerInitialTemperature', 'Oxidizer inlet temperature', 'float', advanced = True,
              default = 90.17, unit = 'K',
              help = 'Oxidizer temperature at the injector.'),
    ]),

    Group('Plume', [
        Field('plumeAmbientPressure', 'Ambient pressure', 'float', default = 101325.0, unit = 'Pa',
              help = 'Ambient static pressure the exhaust plume expands into: the altitude the plume is '
                     'solved at. It sets the lip pressure ratio, and with it how the boundary turns at the '
                     'lip, the shock cell spacing and whether a Mach disk stands. Above about 2.5 times the '
                     'one-dimensional exit pressure the nozzle separates internally (Summerfield) and the '
                     'plume is not solved. Leave blank to skip the plume.'),
        Field('plumeFieldReach', 'March reach', 'float', default = 2.0, unit = 'lip radii',
              help = 'How far past the exit plane the plume boundary and interior are marched, in lip '
                     'radii. Mass continuity holds within 1 percent to about two lip radii, which is the '
                     'trusted reach; past about six the march draws a shape whose numbers are not to be '
                     'used. The error is reported either way. Leave blank to keep only the correlated '
                     'structure.'),
    ]),

    Group('Regenerative Cooling', [
        Field('makeCoolingChannels', 'Generate cooling channels', 'bool', default = False,
              help = 'Build the regenerative cooling jacket and run the heat transfer model.'),
        Selector('Regen truncation', [
            Field('regenTruncationType', 'Regen truncation method', 'choice',
                  choices = [('None (full contour)', 'none'), ('Wall temperature', 'temp'), ('Area ratio', 'er')],
                  default = 'none',
                  help = 'How the regen-cooled section is cut from a radiation-cooled extension: not at '
                         'all, by near-wall recovery temperature, or by area ratio.'),
            Field('regenTruncationValue', 'Truncation value', 'float', default = None,
                  help = 'Near-wall recovery temperature [K] where the regen section ends if the '
                         'method is temperature, or the local area ratio if the method is area '
                         'ratio. Recovery temperature stays near the stagnation temperature along a '
                         'nozzle, so it spans only a few hundred kelvin over the whole bell.'),
            ], options = [
                Option('No truncation (full contour)', sets = {'regenTruncationType': 'none'}),
                Option('Truncate at recovery temperature', key = 'regenTruncationValue', unit = 'K',
                       sets = {'regenTruncationType': 'temp'}),
                Option('Truncate at area ratio', key = 'regenTruncationValue', unit = '',
                       sets = {'regenTruncationType': 'er'}),
            ], blank = 'No truncation (full contour)',
            help = 'Where the regeneratively cooled section ends and a radiation-cooled extension '
                   'takes over: at the full contour, where the near-wall recovery temperature falls '
                   'to a value, or at a local area ratio.'),
        Field('material', 'Wall material', 'choice',
              choices = materialChoices, default = 'GRCop-42', editable = True,
              showWhen = _coolingOn,
              help = 'Hot wall alloy. Drives the temperature-dependent thermal conductivity in the '
                     'heat transfer model; sampled properties are shown below.'),
        Field('channelType', 'Channel type', 'choice',
              choices = [('Circular', 'circle'), ('Rectangular', 'rectangular'), ('Helical', 'helical')],
              default = 'circle', showWhen = _coolingOn,
              help = 'Cooling channel cross-section family. Circular channels are sized by radius; '
                     'rectangular channels fill the pitch less the rib and are sized by depth; '
                     'helical channels run at a fixed angle and aspect ratio and are sized by width.'),
        Field('channelHelixAngle', 'Channel helix angle', 'float', default = None, unit = 'deg',
              showWhen = _helicalChannels,
              help = 'Angle the helical channels run at from the meridian, 0 to 85 degrees. nChannel is the number of starts.'),
        Field('channelSizingMode', 'Channel sizing', 'choice',
              choices = [('Converge on the wall temperature limit', 'thermal'),
                         ('Manual size profile', 'manual')],
              default = 'thermal', showWhen = _coolingOn,
              help = 'Converging runs a search at every station for the largest channel that '
                     'holds the wall at its limit, at about seven passes of the thermal model '
                     'per station. A manual profile fixes the size and marches once, so the '
                     'wall temperature and the pressure drop come out as results. Every run '
                     'prints the profile it built and writes it beside the exported geometry.'),
        Field('manualChannelProfileKey', 'Profile key', 'choice',
              choices = [('Area ratio through the throat', 'areaRatio'),
                         ('Fraction along the jacket', 'jacketFraction')],
              default = 'areaRatio', showWhen = _manualChannelSizing,
              help = 'Coordinate the profile\'s control points are given in. Area ratio is '
                     'negative upstream of the throat, so the throat is -1 on the converging '
                     'side and +1 on the diverging side. It holds one value along a constant '
                     'radius barrel; the jacket fraction, 0 at the injector face and 1 at the '
                     'regen truncation, is the key a recorded profile is written in.'),
        Field('manualChannelProfile', 'Manual size profile', 'text', default = None,
              showWhen = _manualChannelSizing,
              help = 'The radial half-extent to build: a circle\'s radius, half a rectangle\'s '
                     'depth. One number in meters is a constant channel. A list of [key, '
                     'half-extent] pairs, such as [[-2, 0.0015], [1, 0.0015], [3, 0.003]], is '
                     'interpolated between the points and held flat outside them. A path is '
                     'read as a profile a run recorded, such as '
                     'runs/NOVANozzleOutputs/NOVANozzleChannelProfile.json.'),
        Field('nChannel', 'Number of channels', 'int', default = None, showWhen = _coolingOn,
              help = 'Channel count, or starts for a helix. Required. It is reduced at run time if the '
                     'throat cannot hold the smallest channel the process can build, unless a manual '
                     'size profile fixed it, in which case the run stops instead.'),
        Field('hotWallThickness', 'Hot wall thickness', 'float', default = None, unit = 'm',
              showWhen = _coolingOn, help = 'Combustion-side wall thickness.'),
        Field('infillThickness', 'Rib thickness', 'float', default = None, unit = 'm',
              showWhen = _coolingOn,
              help = 'Rib between neighboring channels. A rectangular channel\'s rib is exactly this at the wall; '
                     'a helical channel\'s rib varies and never falls below it.'),
        Field('shellThickness', 'Shell thickness', 'float', default = None, unit = 'm',
              showWhen = _coolingOn, help = 'Outer structural shell thickness.'),
        Field('maxWallTemperature', 'Max hot wall temperature', 'float', default = None, unit = 'K', showWhen = _coolingOn,
              help = 'Hot wall temperature the jacket is held to, one value for the whole jacket. '
                     'Required whenever the jacket is built: the sizing search converges each station '
                     'against it, and a manual size profile is reported against it.'),
        Field('coolantClass', 'Coolant class', 'choice',
              choices = [('Fuel', 'fuel'), ('Oxidizer', 'oxidizer')], default = 'fuel', showWhen = _coolingOn,
              help = 'Which propellant stream feeds the jacket.'),
        Field('coolant', 'Coolant species', 'text', default = None, showWhen = _coolingOn,
              help = 'REFPROP / CoolProp fluid name. Leave blank to inherit from the coolant class.'),
        Field('coolantInitialTemperature', 'Coolant inlet temperature', 'float', default = None, unit = 'K', showWhen = _coolingOn,
              help = 'Coolant temperature entering the jacket.'),
        Field('coolantInitialPressure', 'Coolant inlet pressure', 'float', default = None, unit = 'Pa', showWhen = _coolingOn,
              help = 'Coolant pressure entering the jacket.'),
        Field('coolantMassFlow', 'Coolant mass flow', 'float', default = None, unit = 'kg/s', showWhen = _coolingOn,
              help = 'Coolant mass flow through the jacket. Leave blank to derive from O/F.'),
        Field('gasSideAxialModel', 'Gas-side axial model', 'choice', advanced = True,
              choices = [('Uniform constant (Bartz)', 'uniform'),
                         ('Measured distribution (TN D-2832)', 'measured'),
                         ('Integral method (Ievlev, as RPA)', 'ievlev')],
              default = 'uniform', showWhen = _coolingOn,
              help = 'Bartz carries one correlation constant along the whole wall. The measured '
                     'distribution scales it by constants measured along a LOX/GH2 chamber, which '
                     'leaves the barrel alone and takes about 40 percent off the throat. It is a '
                     'calibration from one engine and injector, not a universal curve. Ievlev\'s '
                     'method integrates the energy equation along the wall, as RPA does; it '
                     'depends on the wall upstream, so the jacket is solved two or three times.'),
        Field('coolantRoughnessModel', 'Coolant roughness model', 'choice', advanced = True,
              choices = [('Friction only (no heat transfer credit)', 'frictionOnly'),
                         ('Dipprey and Sabersky rough-wall heat transfer', 'dippreySabersky'),
                         ('Full credit (rough friction into Gnielinski)', 'fullCredit')],
              default = 'dippreySabersky', showWhen = _coolingOn,
              help = 'What a rough wall may do to the coolant-side heat transfer. Roughness '
                     'raises the friction factor and the pressure drop under all three. Friction '
                     'only is the treatment the hardware comparisons support; full credit is what '
                     'runs the wall coolest and what no measurement supports.'),
        Field('channelSurfaceRoughness', 'Channel surface roughness', 'float', default = 3.5e-05, advanced = True,
              unit = 'm', showWhen = _coolingOn,
              help = 'Absolute roughness the coolant-side friction factor is built on. The '
                     'default is a printed GRCop-42 channel from the Velo3D datasheet.'),
        Field('coolantPropertyCorrection', 'Coolant property correction', 'choice', advanced = True,
              choices = [('None (every property at the bulk temperature)', 'none'),
                         ('Taylor, surface to bulk temperature ratio', 'taylor')],
              default = 'none', showWhen = _coolingOn,
              help = 'Whether the coolant-side correlation is corrected for the property '
                     'variation between the bulk and the hot wall. Leave it at none. Taylor is '
                     'NASA TN D-4332, fitted on symmetrically heated tubes, and against the '
                     'hardware comparison it puts 0 of 13 measured wall temperatures inside the '
                     'band where none puts 13 of 13. It is kept only so that result can be '
                     'reproduced.'),
        Field('coolantGeometryCorrections', 'Coolant entrance and curvature corrections', 'bool', advanced = True,
              default = False, showWhen = _coolingOn,
              help = 'Enhances the coolant-side coefficient in the developing length after the '
                     'inlet and through the bends, by the entrance fit and Ito curvature factor '
                     'NASA TN D-7207 found a station correlation needs to match measured rates.'),
        Field('channelAspectRatio', 'Channel aspect ratio', 'float', default = 1.0, advanced = True,
              showWhen = _helicalChannels,
              help = 'Depth of a helical channel as a multiple of its width.'),
        Field('minChannelWidth', 'Minimum channel width', 'float', default = 1.0e-3, unit = 'm', advanced = True,
              showWhen = _rectangularOrHelicalChannels,
              help = 'Narrowest channel the process can build. The channel count is reduced to hold it at the throat.'),
        Field('channelCornerRadius', 'Channel corner radius', 'float', default = None, unit = 'm', advanced = True,
              showWhen = _rectangularOrHelicalChannels,
              help = 'Corner radius of a rectangular channel. Blank is a sharp corner; the STEP writer needs it above zero.'),
        Field('maxChannelAspectRatio', 'Maximum aspect ratio', 'float', default = 8.0, advanced = True,
              showWhen = _rectangularChannels,
              help = 'Depth a rectangular channel may reach, as a multiple of its width.'),
        Field('maxChannelDepth', 'Maximum channel depth', 'float', default = None, unit = 'm', advanced = True,
              showWhen = _coolingOn,
              help = 'How far any channel may reach out from the wall, a circle\'s diameter included. Blank '
                     'leaves the aspect ratio, or for a helix the rib, to limit a rectangle, and leaves a '
                     'circle bounded only by the room between its neighbors.'),
        Field('thermalBarrierThickness', 'Thermal barrier thickness', 'float',
              default = None, unit = 'm', advanced = True,
              showWhen = _coolingOn,
              help = 'Ceramic coating over the hot wall. Blank for none. With a coating the wall '
                     'temperature limit applies to the metal behind it, not to the coating surface.'),
        Field('thermalBarrierConductivity', 'Thermal barrier conductivity', 'float', default = None, advanced = True,
              unit = 'W/m-K', showWhen = _coolingOn,
              help = 'Conductivity of the coating. Yttria-stabilized zirconia is about 1.5 W/m-K.'),
        Field('numCrossSections', 'Channel cross sections', 'int',
              default = 100, showWhen = _coolingOn, advanced = True,
              help = 'Number of cross sections swept along each channel.'),
        Field('numCSPointsChannel', 'Points per channel cross section', 'int',
              default = 50, showWhen = _coolingOn, advanced = True,
              help = 'Number of points defining each channel cross section.'),
        Field('minCoolantExitPressure', 'Min coolant exit pressure', 'float',
              default = None, unit = 'Pa', showWhen = _coolingOn, advanced = True,
              help = 'Lower limit on coolant pressure at the jacket exit. Checked once the jacket is '
                     'solved, and the run is refused below it. Blank is no limit.'),
        Field('minCoolantExitTemperature', 'Min coolant exit temperature', 'float',
              default = None, unit = 'K', showWhen = _coolingOn, advanced = True,
              help = 'Lower limit on coolant temperature at the jacket exit, for a cycle that needs the '
                     'enthalpy. Checked once the jacket is solved. Blank is no limit.'),
        Field('maxWallTempUpperBound', 'Max wall temp upper bound', 'float',
              default = None, unit = 'K', showWhen = _coolingOn, advanced = True,
              help = 'Upper bound for a wall temperature search. Carried in the configuration and read '
                     'by no solver: no search over the wall temperature is implemented.'),
        Field('maxWallTempLowerBound', 'Max wall temp lower bound', 'float',
              default = None, unit = 'K', showWhen = _coolingOn, advanced = True,
              help = 'Lower bound for a wall temperature search. Carried in the configuration and read '
                     'by no solver: no search over the wall temperature is implemented.'),
        Field('nChannelUpperBound', 'Channel count upper bound', 'int',
              default = None, showWhen = _coolingOn, advanced = True,
              help = 'Upper bound for a channel-count search. Carried in the configuration and read by '
                     'no solver: no search over the channel count is implemented.'),
        Field('nChannelLowerBound', 'Channel count lower bound', 'int',
              default = None, showWhen = _coolingOn, advanced = True,
              help = 'Lower bound for a channel-count search. Carried in the configuration and read by '
                     'no solver: no search over the channel count is implemented.'),
    ], collapsed = True, expandWhen = _coolingOn),

    Group('Radiative Extension', [
        Field('makeRadiativeExtension', 'Radiation-cooled extension', 'bool', default = False,
              help = 'Solve the wall temperature of the uncooled extension beyond the jacket. '
                     'It needs a truncation, because with none the jacket runs the whole '
                     'contour and there is no extension to solve.'),
        Field('extensionMaterial', 'Extension material', 'choice', choices = extensionMaterialChoices,
              default = 'C103', showWhen = _radiativeExtensionOn,
              help = 'The shell material. Its temperature limit in the service atmosphere sets the '
                     'margin report. Choosing it fills the conductivity and emissivities from '
                     'NOVA\'s material store where the store carries them, and leaves the rest as '
                     'they are. None skips the margin.'),
        Field('extensionAtmosphere', 'Service atmosphere', 'choice',
              choices = [('Inert or vacuum', 'inert'), ('Oxidising', 'oxidising'),
                         ('Oxidising, coated', 'oxidisingCoated')],
              default = 'inert', showWhen = _radiativeExtensionOn,
              help = 'Which of the material\'s limits applies. For C103 the inert and oxidizing '
                     'limits differ by a factor of three, so this is a design choice rather '
                     'than a label.'),
        Field('extensionThickness', 'Shell thickness', 'float', default = 0.0005, unit = 'm',
              showWhen = _radiativeExtensionOn,
              help = 'Sets conduction along the shell and the through-thickness drop the lumped '
                     'treatment neglects. The drop is reported so it can be checked.'),
        Field('extensionThermalConductivity', 'Shell conductivity', 'float', default = 45.0,
              unit = 'W/m-K', showWhen = _radiativeExtensionOn,
              help = 'One value for the whole shell. The material store carries a conductivity '
                     'for ATJ graphite alone, at room temperature, so for the others it is '
                     'supplied here. C103 is near 45 W/m-K.'),
        Field('extensionInnerEmissivity', 'Inner emissivity', 'float', default = 0.7,
              showWhen = _radiativeExtensionOn,
              help = 'Gas-side surface. Sets how much band radiation the wall exchanges with '
                     'the exhaust, which on an extension is usually a loss rather than a gain.'),
        Field('extensionOuterEmissivity', 'Outer emissivity', 'float', default = 0.7,
              showWhen = _radiativeExtensionOn,
              help = 'The one that governs. Wall temperature goes as the inverse fourth root of '
                     'it, so halving it costs about nineteen percent. Only the degraded R512E '
                     'coated value has a source in the store.'),
        Field('extensionOuterViewFactor', 'Outer view factor', 'float', default = 1.0,
              showWhen = _radiativeExtensionOn,
              help = 'Fraction of the outward emission that reaches the sink. One for a surface '
                     'looking at open space, less where it sees vehicle structure.'),
        Field('extensionSinkTemperature', 'Sink temperature', 'float', default = 4.0, unit = 'K',
              showWhen = _radiativeExtensionOn,
              help = 'What the outer surface radiates to. Its fourth power is negligible '
                     'against any wall temperature, so the exact value rarely matters.'),
        Field('extensionGasEmissivity', 'Gas emissivity', 'float', default = 0.0,
              showWhen = _radiativeExtensionOn,
              help = 'Total emissivity of the exhaust over the mean beam length. Zero makes the '
                     'gas transparent and removes the band term exactly.'),
        Field('extensionJointTemperature', 'Joint temperature', 'float', default = None,
              unit = 'K', showWhen = _radiativeExtensionOn,
              help = 'Wall temperature where the shell meets whatever is upstream. Empty makes '
                     'the joint adiabatic, which lets no heat out through the flange and is the '
                     'conservative reading of an unknown one.'),
    ], collapsed = True, expandWhen = _radiativeExtensionOn),

    Group('Film Cooling', [
        Field('filmCooling', 'Film cooling', 'bool', default = False,
              help = 'Inject a sheet of coolant along the wall. It lowers the temperature '
                     'the wall is driven by rather than carrying heat away, and it works '
                     'with a jacket rather than instead of one.'),
        Field('filmCoolingModel', 'Film closure', 'choice',
              choices = [('Hatch and Papell (TN D-130)', 'hatchPapell'),
                         ('SP-8124 entrainment', 'sp8124Entrainment')],
              default = 'hatchPapell', showWhen = _filmCoolingOn,
              help = 'Hatch and Papell states its own accuracy but was fitted in a '
                     'constant-area duct and cannot see acceleration or turning. The '
                     'SP-8124 entrainment model accounts for both through an empirical '
                     'multiplier read off a design chart, so it is calibrated rather than '
                     'validated. On a hydrogen film the two disagree by hundreds of '
                     'kelvin.'),
        Field('filmEntrainmentMultiplier', 'Entrainment multiplier at the slot', 'float',
              default = 3.5, showWhen = _entrainmentModelOn,
              help = 'psi_m where the coolant enters. SP-8124 3.5.2 recommends 3 to 4 and '
                     'does not narrow it further; across that band alone the peak driving '
                     'temperature moves about a hundred kelvin. It is the single largest '
                     'lever in the model.'),
        Field('filmCoolantMixtureRatio', 'Film coolant mixture ratio', 'float',
              default = 0.0, showWhen = _entrainmentModelOn,
              help = 'Oxidiser to fuel ratio of the coolant itself. Zero is a pure fuel '
                     'film, which is the usual case and the one that leaves the wall gas '
                     'fuel-rich.'),
        Field('filmCoolant', 'Film coolant species', 'text', default = None,
              showWhen = _filmCoolingOn,
              help = 'REFPROP or CoolProp fluid name. It has to be a gas at its slot '
                     'conditions: the closure describes a gaseous film.'),
        Field('filmMassFlow', 'Film coolant flow', 'float', default = None, unit = 'kg/s',
              showWhen = _filmCoolingOn,
              help = 'Coolant through the film ring. This is propellant bypassing the '
                     'injector, so it costs performance.'),
        Field('filmInletTemperature', 'Film coolant temperature', 'float', default = None,
              unit = 'K', showWhen = _filmCoolingOn,
              help = 'Coolant temperature leaving the slot.'),
        Field('filmInjectionAxialPosition', 'Injection position', 'float', default = None,
              unit = 'm', showWhen = _filmCoolingOn,
              help = 'Axial position of the slot. One ring only; the correlation is '
                     'written for a single continuous slot.'),
        Field('filmSlotHeight', 'Slot height', 'float', default = None, unit = 'm',
              showWhen = _filmCoolingOn,
              help = 'Radial height of the annular slot. It sets the injection velocity '
                     'through the flow area, and the correlation rewards a narrow slot.'),
    ], collapsed = True, expandWhen = _filmCoolingOn),

    Group('Volutes', [
        Field('numCSVolute', 'Volute cross sections', 'int', default = None, showWhen = _anyVolute,
              help = 'Number of cross sections swept around each volute.'),
        Field('numCSPointsVolute', 'Points per volute cross section', 'int', default = None, showWhen = _anyVolute,
              help = 'Number of points defining each volute cross section.'),
        Field('voluteRelativeRoll', 'Volute relative roll', 'float', default = None, unit = 'deg', showWhen = _anyVolute,
              help = 'Roll offset between the inlet and outlet volutes.'),
        Field('voluteScrollType', 'Scroll type', 'choice',
              choices = [('Ring', 'ring'), ('Cutwater', 'cutwater')], default = 'ring',
              showWhen = _anyVolute,
              help = 'Ring wraps a full turn and is fed from both directions, so its throat is at '
                     'the feed and its tongue half a turn away. Cutwater stops short of a full '
                     'turn and puts a wall between its two ends, with the tongue at one end and '
                     'the throat at the other.'),
        Field('voluteFOS', 'Volute factor of safety', 'float', default = 1.5,
              showWhen = _anyVolute,
              help = 'Factor the alloy yield strength is divided by to size the volute wall. The '
                     'wall is sized on the warmer of the coolant and a room temperature proof '
                     'case, since a copper alloy is weaker warm.'),
        Field('minVoluteWallThickness', 'Minimum volute wall', 'float', default = 1.0e-3,
              unit = 'm', showWhen = _anyVolute,
              help = 'Thinnest wall the process can print, which floors what the hoop stress asks '
                     'for. Published LPBF work on GRCop holds vertical walls at 1 mm.'),
        Field('maxVoluteBore', 'Maximum scroll bore', 'float', default = 0.15, unit = 'm',
              showWhen = _anyVolute,
              help = 'Largest scroll throat the build will accept. The throat follows from the '
                     'channel port and the port count, so a large channel asks for a large '
                     'scroll; past this the build refuses rather than drawing one that will not '
                     'fit.'),
        Field('makeInletVolute', 'Generate inlet volute', 'bool', default = False, fold = 'Inlet volute',
              help = 'Build the inlet manifold volute that feeds the channels.'),
        Field('inletVoluteCrossSection', 'Inlet cross section', 'choice', fold = 'Inlet volute',
              choices = [('Circle', 'circle'), ('Squircle', 'squarc')], default = 'circle',
              showWhen = _inletVoluteOn, help = 'Cross-section shape of the inlet volute.'),
        Field('inletVoluteAlignment', 'Inlet alignment', 'choice', fold = 'Inlet volute',
              choices = [('Center', 'c'), ('North', 'n'), ('South', 's'), ('Inner', 'i'), ('Outer', 'o'),
                         ('North-inner', 'ni'), ('South-inner', 'si'), ('North-outer', 'no'), ('South-outer', 'so')],
              default = 'i', showWhen = _inletVoluteOn,
              help = 'Which edge of the inlet volute cross section holds still as the scroll '
                     'grows, and so whether the growing sections reach toward the nozzle or away '
                     'from it. Inner grows them outward, clear of the wall.'),
        Field('inletVolutePrintability', 'Inlet printability shaping', 'choice', fold = 'Inlet volute',
              choices = [('Off', 'off'), ('Thick', 'thick'), ('Thin', 'thin')], default = 'off',
              showWhen = _inletVoluteOn,
              help = 'Overhang support drawn inside the inlet scroll. Thick braces it with a wall '
                     'and two filleted transitions, thin with a sheet and one. Circular sections '
                     'only.'),
        Field('inletVoluteTilt', 'Inlet volute tilt', 'float',
              default = None, unit = 'deg', showWhen = _inletVoluteOn, fold = 'Inlet volute',
              help = 'Tilt of the inlet volute cross section.'),
        Field('inletGraylocDiameter', 'Inlet Grayloc seal ID', 'float',
              default = None, unit = 'in', showWhen = _inletVoluteOn, fold = 'Inlet volute',
              help = 'Inner diameter of the inlet Grayloc seal ring.'),
        Field('inletVoluteAxialOffset', 'Inlet volute axial offset', 'float',
              default = None, unit = 'm', showWhen = _inletVoluteOn, fold = 'Inlet volute',
              help = 'Distance upstream of the aft end of the regen section at which the inlet flare leaves the wall.'),
        Field('inletVoluteFlareRoverD', 'Inlet flare R/D', 'float',
              default = None, showWhen = _inletVoluteOn, fold = 'Inlet volute',
              help = 'Fillet radius of the turn into the inlet flare, over the jacket depth.'),
        Field('inletVoluteFlareLength', 'Inlet flare length', 'float',
              default = None, unit = 'm', showWhen = _inletVoluteOn, fold = 'Inlet volute',
              help = 'Flare extension length for the inlet channel entry.'),
        Field('makeOutletVolute', 'Generate outlet volute', 'bool', default = False, fold = 'Outlet volute',
              help = 'Build the outlet manifold volute that collects the channels.'),
        Field('outletVoluteCrossSection', 'Outlet cross section', 'choice', fold = 'Outlet volute',
              choices = [('Circle', 'circle'), ('Squircle', 'squarc')], default = 'circle',
              showWhen = _outletVoluteOn, help = 'Cross-section shape of the outlet volute.'),
        Field('outletVoluteAlignment', 'Outlet alignment', 'choice', fold = 'Outlet volute',
              choices = [('Center', 'c'), ('North', 'n'), ('South', 's'), ('Inner', 'i'), ('Outer', 'o'),
                         ('North-inner', 'ni'), ('South-inner', 'si'), ('North-outer', 'no'), ('South-outer', 'so')],
              default = 'i', showWhen = _outletVoluteOn,
              help = 'Which edge of the outlet volute cross section holds still as the scroll '
                     'grows, and so whether the growing sections reach toward the nozzle or away '
                     'from it. Inner grows them outward, clear of the wall.'),
        Field('outletVolutePrintability', 'Outlet printability shaping', 'choice', fold = 'Outlet volute',
              choices = [('Off', 'off'), ('Thick', 'thick'), ('Thin', 'thin')], default = 'off',
              showWhen = _outletVoluteOn,
              help = 'Overhang support drawn inside the outlet scroll. Thick braces it with a wall '
                     'and two filleted transitions, thin with a sheet and one. Circular sections '
                     'only.'),
        Field('outletVoluteTilt', 'Outlet volute tilt', 'float',
              default = None, unit = 'deg', showWhen = _outletVoluteOn, fold = 'Outlet volute',
              help = 'Tilt of the outlet volute cross section.'),
        Field('outletGraylocDiameter', 'Outlet Grayloc seal ID', 'float',
              default = None, unit = 'in', showWhen = _outletVoluteOn, fold = 'Outlet volute',
              help = 'Inner diameter of the outlet Grayloc seal ring.'),
        Field('outletVoluteAxialOffset', 'Outlet volute axial offset', 'float',
              default = None, unit = 'm', showWhen = _outletVoluteOn, fold = 'Outlet volute',
              help = 'Distance downstream of the injector face at which the outlet flare leaves the wall.'),
        Field('outletVoluteFlareRoverD', 'Outlet flare R/D', 'float',
              default = None, showWhen = _outletVoluteOn, fold = 'Outlet volute',
              help = 'Fillet radius of the turn into the outlet flare, over the jacket depth.'),
        Field('outletVoluteFlareLength', 'Outlet flare length', 'float',
              default = None, unit = 'm', showWhen = _outletVoluteOn, fold = 'Outlet volute',
              help = 'Flare extension length for the outlet channel exit.'),
    ], collapsed = True, note = 'Requires cooling channels to be enabled.', expandWhen = _anyVolute),

    Group('Program Options', [
        Field('filename', 'Output name', 'text', default = 'novaRun',
              help = 'Base name for the output folder: <name>Outputs/ beside the export location.'),
        Field('plotsEnabled', 'Plots', 'bool', default = True, hidden = True,
              help = 'Write every figure the run generates. Every GUI run writes them.'),
        Field('export', 'Export data files', 'bool', default = True, hidden = True,
              help = 'Write contour text files, STL geometry and the pickled nozzle. Every GUI run '
                     'writes them, and the Export tab chooses which are kept.'),
    ]),
]

def allFields() -> list:

    '''

    Every Field across all groups, in form order, including synthetic helpers and the members of
    each Selector.

    '''

    flat = []
    for group in groups:
        for item in group.fields:
            flat += item.members if isinstance(item, Selector) else [item]
    return flat

def _applyShippedDefaults() -> None:

    '''

    Make the shipped nozzle the form's default.

    A fresh form, and Reset to example, then build exactly the design the backend builds with no
    configuration given, rather than a second nozzle maintained by hand beside it. A key the file
    leaves out keeps the default written in its Field, and an unreadable file leaves every default
    as written.

    '''

    try:
        with open(shippedConfigPath, encoding = 'utf-8') as handle:
            shipped = json.load(handle)
    except (OSError, ValueError):
        return

    for spec in allFields():
        if not spec.synthetic and spec.key in shipped:
            spec.default = shipped[spec.key]

_applyShippedDefaults()

def defaultConfig() -> dict:

    '''

    A complete config dictionary with every real key set to its default, which is the shipped
    nozzle's value. Blank numeric and text fields resolve to None, which NOVA reads as 'not
    specified'. Choice fields hold their backend value, not the label. Synthetic form-only
    helpers are excluded.

    '''

    return {f.key: f.default for f in allFields() if not f.synthetic}
