
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
    default    backend value pre-filled on a fresh form (None renders blank)
    unit       short unit string appended to the label, or ''
    help       one-line tooltip
    showWhen   predicate over the current config dict; the row is hidden when it
               returns False
    synthetic  True for a form-only helper that does not map to a config key.
               The config tab folds these into a real key on the way out and
               unpacks them on the way in (see the truncation fields).

Groups carry `collapsed`, `showWhen` (hide the whole section) and `expandWhen`
(auto-open the section when the predicate first becomes true).

Author: Sean Bowman
Date:   08/28/2026

'''

from dataclasses import dataclass, field

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
class Group:

    '''

    A titled, collapsible block of fields in the config tab.

    '''

    title: str
    fields: list
    collapsed: bool = False
    note: str = ''
    showWhen: object = None
    expandWhen: object = None

# -- Program option flags forced on for every GUI run -- #

# The geometry and analysis tabs read the PNG and HTML files NOVA only writes
# when plots and export are enabled, so the runner overrides these regardless
# of the form.
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

def _anyVolute(config: dict) -> bool:
    return (config.get('makeInletVolute') in (True, 'on')
            or config.get('makeReturnVolute') in (True, 'on'))

def _radiativeExtensionOn(config: dict) -> bool:
    return config.get('makeRadiativeExtension') in (True, 'on')

def _filmCoolingOn(config: dict) -> bool:
    return config.get('filmCooling') in (True, 'on')

def _entrainmentModelOn(config: dict) -> bool:
    return _filmCoolingOn(config) \
           and config.get('filmCoolingModel') == 'sp8124Entrainment'

def _truncationNeedsValue(config: dict) -> bool:
    return config.get('regenTruncationType') in ('temp', 'er')

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
    ('GRCop-42 (Cu-Cr-Nb, regen standard)', 'GRCop-42'),
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

groups = [

    Group('Contour Definition', [
        Field('numContourPoints', 'Contour points', 'int', default = 100,
              help = 'Number of points in the resampled wall contour.'),
        Field('divergingSectionType', 'Diverging section type', 'choice',
              choices = [('Truncated ideal contour (tic)', 'tic'),
                         ('Thrust-optimized parabola (top)', 'top'),
                         ('Thrust-optimized contour (toc)', 'toc'),
                         ('Conical (cone)', 'cone')], default = 'tic',
              help = 'tic and top are method-of-characteristics contours evaluated directly; toc '
                     'searches over them for the shortest length at the requested performance. '
                     'cone is a straight 15 degree half-angle cone.'),
        Field('divergingSectionDesignVariables', 'Design vector', 'text', default = None,
              showWhen = _searchedContour,
              help = 'Pins a thrust-optimized wall instead of searching for one: four numbers, '
                     'the inflection and exit wall angles in degrees then the inflection and '
                     'exit tensions, separated by commas. Blank runs the search.'),
        Field('chamberDiameter', 'Chamber outer diameter', 'float', default = 0.18, unit = 'm',
              help = 'Outer diameter of the chamber wall at the converging inlet. Sets the contraction ratio.'),
        Field('convergingSectionAngle', 'Converging wall angle at throat', 'float', default = 30.0, unit = 'deg',
              help = 'Wall angle of the converging section where it meets the throat.'),
        Field('Lstar', 'Characteristic length L*', 'float', default = 1.0, unit = 'm',
              help = 'Chamber volume over throat area, injector face to throat. Sets the cylindrical '
                     'barrel length after the converging section volume is subtracted. Mutually '
                     'exclusive with chamber barrel length. The contour is resampled at equal arc '
                     'length, so a long barrel takes points from the diverging section: raise the '
                     'contour point count to compensate.'),
        Field('chamberLength', 'Chamber barrel length', 'float', default = None, unit = 'm',
              help = 'Cylindrical chamber length, specified directly instead of through L*. '
                     'Leave blank to derive it from L*; set to 0 for no barrel.'),
        Field('lengthFraction', 'Length fraction', 'float', default = 0.8,
              help = 'Truncated ideal contour length as a fraction of a 15 deg conical nozzle of '
                     'the same area ratio, which is how NASA SP-8120 defines percent bell.'),
        Field('numCharacteristics', 'Characteristics', 'int', default = 50,
              help = 'Characteristics launched from the throat arc, which sets the mesh resolution '
                     'of the whole solve. At the default the exit wall angle carries about 2 '
                     'percent of mesh error and the thrust coefficient about 1 percent.'),
        Field('transonicModel', 'Transonic model', 'choice',
              choices = [('Sauer', 'sauer'), ('Second order', 'secondOrder'),
                         ('Small radius', 'smallRadius')], default = 'sauer',
              help = 'Which starting line the characteristics net is launched from. Sauer is the '
                     'first-order transonic solution and is the default. The second-order and '
                     'small-radius lines are the ones to reach for at a sharp throat, where the '
                     'Sauer expansion is weakest.'),
        Field('throatInletCurvature', 'Throat inlet curvature', 'float', default = 1.5,
              help = 'Radius of curvature of the throat inlet arc, as a multiple of the throat '
                     'radius. NASA SP-8120 takes this above 0.6.'),
        Field('throatOutletCurvature', 'Throat outlet curvature', 'float', default = 0.382,
              help = 'Radius of curvature of the throat outlet arc, as a multiple of the throat '
                     'radius. The default is the Rao value.'),
        Field('regenTruncationType', 'Regen truncation method', 'choice',
              choices = [('None (full contour)', 'none'), ('Wall temperature', 'temp'), ('Area ratio', 'er')],
              default = 'none',
              help = 'Split the regen-cooled section from a radiation-cooled extension by near-wall '
                     'gas temperature or by area ratio. The cut point is entered below; ignored when '
                     'the method is none.'),
        Field('regenTruncationValue', 'Truncation value', 'float', default = None,
              showWhen = _truncationNeedsValue,
              help = 'Near-wall recovery temperature [K] where the regen section ends if the '
                     'method is temperature, or the local area ratio if the method is area '
                     'ratio. Recovery temperature stays near the stagnation temperature along a '
                     'nozzle, so it spans only a few hundred kelvin over the whole bell.'),
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
        Field('fuelInitialTemperature', 'Fuel inlet temperature', 'float', default = 20.27, unit = 'K',
              help = 'Fuel temperature at the injector.'),
        Field('oxidizerInitialTemperature', 'Oxidizer inlet temperature', 'float', default = 90.17, unit = 'K',
              help = 'Oxidizer temperature at the injector.'),
        Field('thrust', 'Thrust', 'float', default = 100000.0, unit = 'N',
              help = 'Target thrust. Specify this OR engine mass flow, leave the other blank.'),
        Field('engineMassFlow', 'Engine mass flow', 'float', default = None, unit = 'kg/s',
              help = 'Total propellant mass flow. Specify this OR thrust, leave the other blank.'),
        Field('expansionRatio', 'Expansion ratio', 'float', default = 40.0,
              help = 'One-dimensional CEA area ratio. Specify this OR target exit pressure, leave the other blank.'),
        Field('targetExitPressure', 'Target exit pressure', 'float', default = None, unit = 'Pa',
              help = 'Design exit static pressure. Specify this OR expansion ratio, leave the other blank.'),
        Field('plumeAmbientPressure', 'Plume ambient pressure', 'float', default = 101325.0, unit = 'Pa',
              help = 'Ambient static pressure the exhaust plume is drawn against. Sets the jet regime, '
                     'shock cell spacing and Mach disk. Leave blank to skip the plume figures.'),
    ]),

    Group('Cooling Channels', [
        Field('makeCoolingChannels', 'Generate cooling channels', 'bool', default = False,
              help = 'Build the regenerative cooling jacket and run the heat transfer model.'),
        Field('material', 'Wall material', 'choice',
              choices = materialChoices, default = 'GRCop-42', editable = True,
              showWhen = _coolingOn,
              help = 'Hot wall alloy. Drives the temperature-dependent thermal conductivity in the '
                     'heat transfer model; sampled properties are shown below.'),
        Field('gasSideAxialModel', 'Gas-side axial model', 'choice',
              choices = [('Uniform constant (Bartz)', 'uniform'),
                         ('Measured distribution (TN D-2832)', 'measured')],
              default = 'uniform', showWhen = _coolingOn,
              help = 'Bartz carries one correlation constant along the whole wall. The measured '
                     'distribution scales it by constants measured along a LOX/GH2 chamber, which '
                     'leaves the barrel alone and takes about 40 percent off the throat. It is a '
                     'calibration from one engine and injector, not a universal curve.'),
        Field('coolantGeometryCorrections', 'Coolant entrance and curvature corrections', 'bool',
              default = False, showWhen = _coolingOn,
              help = 'Enhances the coolant-side coefficient in the developing length after the '
                     'inlet and through the bends, by the entrance fit and Ito curvature factor '
                     'NASA TN D-7207 found a station correlation needs to match measured rates.'),
        Field('channelType', 'Channel type', 'choice',
              choices = [('Circular', 'circle'), ('Rectangular', 'rectangular'), ('Helical', 'helical')],
              default = 'circle', showWhen = _coolingOn,
              help = 'Cooling channel cross-section family. Circular channels are sized by radius; '
                     'rectangular channels fill the pitch less the rib and are sized by depth; '
                     'helical channels run at a fixed angle and aspect ratio and are sized by width.'),
        Field('channelHelixAngle', 'Channel helix angle', 'float', default = None, unit = 'deg',
              showWhen = _helicalChannels,
              help = 'Angle the helical channels run at from the meridian, 0 to 85 degrees. nChannel is the number of starts.'),
        Field('channelAspectRatio', 'Channel aspect ratio', 'float', default = 1.0,
              showWhen = _helicalChannels,
              help = 'Depth of a helical channel as a multiple of its width.'),
        Field('minChannelWidth', 'Minimum channel width', 'float', default = 1.0e-3, unit = 'm',
              showWhen = _rectangularOrHelicalChannels,
              help = 'Narrowest channel the process can build. The channel count is reduced to hold it at the throat.'),
        Field('channelCornerRadius', 'Channel corner radius', 'float', default = None, unit = 'm',
              showWhen = _rectangularOrHelicalChannels,
              help = 'Corner radius of a rectangular channel. Blank is a sharp corner; the STEP writer needs it above zero.'),
        Field('maxChannelAspectRatio', 'Maximum aspect ratio', 'float', default = 8.0,
              showWhen = _rectangularChannels,
              help = 'Depth a rectangular channel may reach, as a multiple of its width.'),
        Field('maxChannelDepth', 'Maximum channel depth', 'float', default = None, unit = 'm',
              showWhen = _rectangularOrHelicalChannels,
              help = 'Depth a rectangular or helical channel may reach outright. Blank leaves the aspect ratio, '
                     'or for a helix the rib, to limit it.'),
        Field('hotWallThickness', 'Hot wall thickness', 'float', default = None, unit = 'm',
              showWhen = _coolingOn, help = 'Combustion-side wall thickness.'),
        Field('shellThickness', 'Shell thickness', 'float', default = None, unit = 'm',
              showWhen = _coolingOn, help = 'Outer structural shell thickness.'),
        Field('infillThickness', 'Rib thickness', 'float', default = None, unit = 'm',
              showWhen = _coolingOn,
              help = 'Rib between neighboring channels. A rectangular channel\'s rib is exactly this at the wall; '
                     'a helical channel\'s rib varies and never falls below it.'),
        Field('nChannel', 'Number of channels', 'int', default = None, showWhen = _coolingOn,
              help = 'Fixed channel count. Leave blank to let the optimizer choose within the bounds below.'),
        Field('numCrossSections', 'Channel cross sections', 'int', default = 100, showWhen = _coolingOn,
              help = 'Number of cross sections swept along each channel.'),
        Field('numCSPointsChannel', 'Points per channel cross section', 'int', default = 50, showWhen = _coolingOn,
              help = 'Number of points defining each channel cross section.'),
        Field('maxWallTemperature', 'Max hot wall temperature', 'float', default = None, unit = 'K', showWhen = _coolingOn,
              help = 'Hard cap on hot wall temperature. Leave blank to optimize between the bounds below.'),
        Field('maxWallTempUpperBound', 'Max wall temp upper bound', 'float', default = None, unit = 'K', showWhen = _coolingOn,
              help = 'Upper bound for the wall temperature optimization.'),
        Field('maxWallTempLowerBound', 'Max wall temp lower bound', 'float', default = None, unit = 'K', showWhen = _coolingOn,
              help = 'Lower bound for the wall temperature optimization.'),
        Field('nChannelUpperBound', 'Channel count upper bound', 'int', default = None, showWhen = _coolingOn,
              help = 'Upper bound for the channel-count search.'),
        Field('nChannelLowerBound', 'Channel count lower bound', 'int', default = None, showWhen = _coolingOn,
              help = 'Lower bound for the channel-count search.'),
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
        Field('minCoolantExitPressure', 'Min coolant exit pressure', 'float', default = None, unit = 'Pa', showWhen = _coolingOn,
              help = 'Lower limit on coolant pressure at the jacket exit.'),
        Field('minCoolantExitTemperature', 'Min coolant exit temperature', 'float', default = None, unit = 'K', showWhen = _coolingOn,
              help = 'Lower limit on coolant temperature at the jacket exit.'),
    ], collapsed = True, expandWhen = _coolingOn),

    Group('Radiative Extension', [
        Field('makeRadiativeExtension', 'Radiation-cooled extension', 'bool', default = False,
              help = 'Solve the wall temperature of the uncooled extension beyond the jacket. '
                     'It needs a truncation, because with none the jacket runs the whole '
                     'contour and there is no extension to solve.'),
        Field('extensionMaterial', 'Extension material', 'text', default = 'C103',
              showWhen = _radiativeExtensionOn,
              help = 'Named only to look up a temperature limit for the margin report. Leave it '
                     'empty to skip the margin.'),
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
              help = 'Supplied rather than looked up: the materials store carries conductivity '
                     'curves only for the jacket alloys and would substitute GRCop-42, which '
                     'conducts eight times better than a refractory metal.'),
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

    Group('Gas Model', [
        Field('gammaModel', 'Ratio of specific heats', 'choice',
              choices = [('Chamber value', 'chamber'),
                         ('Effective, fitted to the design point', 'effective')],
              default = 'chamber',
              help = 'A real exhaust recombines as it expands and has no single ratio of '
                     'specific heats, so the contour solve picks one. The chamber value is '
                     'the default and the one the solve has always used. The effective '
                     'value is fitted so the pressure ratio and the area ratio agree with '
                     'the thermochemistry at the design point: it cuts the pressure error '
                     'threefold and biases the gas temperature cold, which undersizes a '
                     'cooling jacket. Choose it for contour and performance work, not for '
                     'a jacket. Both values are reported either way.'),
    ], collapsed = True),

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
        Field('makeInletVolute', 'Generate inlet volute', 'bool', default = False,
              help = 'Build the inlet manifold volute that feeds the channels.'),
        Field('makeReturnVolute', 'Generate return volute', 'bool', default = False,
              help = 'Build the return manifold volute that collects the channels.'),
        Field('numCSVolute', 'Volute cross sections', 'int', default = None, showWhen = _anyVolute,
              help = 'Number of cross sections swept around each volute.'),
        Field('numCSPointsVolute', 'Points per volute cross section', 'int', default = None, showWhen = _anyVolute,
              help = 'Number of points defining each volute cross section.'),
        Field('voluteRelativeRoll', 'Volute relative roll', 'float', default = None, unit = 'deg', showWhen = _anyVolute,
              help = 'Roll offset between the inlet and return volutes.'),
        Field('inletVoluteCrossSection', 'Inlet cross section', 'choice',
              choices = [('Circle', 'circle'), ('Egg', 'egg'), ('Squircle', 'squarc')], default = 'circle',
              showWhen = _anyVolute, help = 'Cross-section shape of the inlet volute.'),
        Field('inletVoluteAlignment', 'Inlet alignment', 'choice',
              choices = [('Center', 'c'), ('North', 'n'), ('South', 's'), ('Inner', 'i'), ('Outer', 'o'),
                         ('North-inner', 'ni'), ('South-inner', 'si'), ('North-outer', 'no'), ('South-outer', 'so')],
              default = 'o', showWhen = _anyVolute,
              help = 'Alignment of the inlet volute cross section relative to the wall.'),
        Field('inletVolutePrintability', 'Inlet printability shaping', 'bool', default = False, showWhen = _anyVolute,
              help = 'Apply overhang-safe shaping to the inlet volute.'),
        Field('inletVoluteTilt', 'Inlet volute tilt', 'float', default = None, unit = 'deg', showWhen = _anyVolute,
              help = 'Tilt of the inlet volute cross section.'),
        Field('inletGraylocDiameter', 'Inlet Grayloc seal ID', 'float', default = None, unit = 'in', showWhen = _anyVolute,
              help = 'Inner diameter of the inlet Grayloc seal ring.'),
        Field('inletVoluteAxialOffset', 'Inlet volute axial offset', 'float', default = None, unit = 'm', showWhen = _anyVolute,
              help = 'Distance upstream of the aft end of the regen section at which the inlet flare leaves the wall.'),
        Field('inletVoluteFlareRoverD', 'Inlet flare R/D', 'float', default = None, showWhen = _anyVolute,
              help = 'Fillet radius of the turn into the inlet flare, over the jacket depth.'),
        Field('inletVoluteFlareLength', 'Inlet flare length', 'float', default = None, unit = 'm', showWhen = _anyVolute,
              help = 'Flare extension length for the inlet channel entry.'),
        Field('returnVoluteCrossSection', 'Return cross section', 'choice',
              choices = [('Circle', 'circle'), ('Egg', 'egg'), ('Squircle', 'squarc')], default = 'circle',
              showWhen = _anyVolute, help = 'Cross-section shape of the return volute.'),
        Field('returnVoluteAlignment', 'Return alignment', 'choice',
              choices = [('Center', 'c'), ('North', 'n'), ('South', 's'), ('Inner', 'i'), ('Outer', 'o'),
                         ('North-inner', 'ni'), ('South-inner', 'si'), ('North-outer', 'no'), ('South-outer', 'so')],
              default = 'o', showWhen = _anyVolute,
              help = 'Alignment of the return volute cross section relative to the wall.'),
        Field('returnVolutePrintability', 'Return printability shaping', 'bool', default = False, showWhen = _anyVolute,
              help = 'Apply overhang-safe shaping to the return volute.'),
        Field('returnVoluteTilt', 'Return volute tilt', 'float', default = None, unit = 'deg', showWhen = _anyVolute,
              help = 'Tilt of the return volute cross section.'),
        Field('returnGraylocDiameter', 'Return Grayloc seal ID', 'float', default = None, unit = 'in', showWhen = _anyVolute,
              help = 'Inner diameter of the return Grayloc seal ring.'),
        Field('returnVoluteAxialOffset', 'Return volute axial offset', 'float', default = None, unit = 'm', showWhen = _anyVolute,
              help = 'Distance downstream of the injector face at which the return flare leaves the wall.'),
        Field('returnVoluteFlareRoverD', 'Return flare R/D', 'float', default = None, showWhen = _anyVolute,
              help = 'Fillet radius of the turn into the return flare, over the jacket depth.'),
        Field('returnVoluteFlareLen', 'Return flare length', 'float', default = None, unit = 'm', showWhen = _anyVolute,
              help = 'Flare extension length for the return channel exit.'),
    ], collapsed = True, note = 'Requires cooling channels to be enabled.', expandWhen = _anyVolute),

    Group('Program Options', [
        Field('filename', 'Output name', 'text', default = 'novaRun',
              help = 'Base name for the output folder: <name>Outputs/ beside the export location.'),
        Field('plotsEnabled', 'Plots', 'bool', default = True,
              help = 'Write every figure the run generates: contour, Mach, pressure, temperature '
                     'and near-wall views, the channel-mesh and jacket HTML views, and the volute '
                     'assembly. Forced on by the GUI.'),
        Field('export', 'Export data files', 'bool', default = True,
              help = 'Write contour text files, STL geometry and the pickled nozzle. Forced on by the GUI.'),
    ]),
]

def allFields() -> list:

    '''

    Every Field across all groups, in form order, including synthetic helpers.

    '''

    return [f for group in groups for f in group.fields]

def defaultConfig() -> dict:

    '''

    A complete config dictionary with every real key set to its schema default.
    Blank numeric and text fields resolve to None, which NOVA reads as
    'not specified'. Choice fields hold their backend value, not the label.
    Synthetic form-only helpers are excluded; the config tab folds them in.

    '''

    return {f.key: f.default for f in allFields() if not f.synthetic}
