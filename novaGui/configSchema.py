# -- NOVA Configuration Schema -- #

'''

Field metadata for the config tab, ordered and grouped to mirror
src/NOVA/assets/nozzleConfig.json. Every key in that template appears
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
# when export is enabled, so the runner overrides these regardless of the form.
forcedFlags = ('export', 'visualizeContour', 'plotsBasic')

# Flags additionally forced on when cooling channels are enabled, so the 3D tab
# has jacket geometry to show.
forcedCoolingFlags = ('plotsAdv', 'plotJacket')

# -- Dependency predicates -- #

def _divergingIsConical(config: dict) -> bool:
    return config.get('divergingSectionType') == 'Conical'

def _coolingOn(config: dict) -> bool:
    return config.get('makeCoolingChannels') in (True, 'on')

def _anyVolute(config: dict) -> bool:
    return (config.get('makeInletVolute') in (True, 'on')
            or config.get('makeReturnVolute') in (True, 'on'))

def _filmCoolingOn(config: dict) -> bool:
    return config.get('filmCooling') in (True, 'on')

def _printabilityOn(config: dict) -> bool:
    return _coolingOn(config) and config.get('printabilityCheck') in (True, 'on')

def _truncateByTemp(config: dict) -> bool:
    return config.get('truncationMethod') == 'temp'

def _truncateByAreaRatio(config: dict) -> bool:
    return config.get('truncationMethod') == 'er'

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
        Field('contourType', 'Converging section type', 'choice',
              choices = [('Traditional', 'trad')], default = 'trad',
              help = 'Conical converging section into a throat arc.'),
        Field('divergingSectionType', 'Diverging section type', 'choice',
              choices = [('Method of characteristics', 'rao'), ('Conical', 'Conical')], default = 'rao',
              help = 'Method of characteristics: truncated ideal contour. Conical: straight cone at a fixed half angle.'),
        Field('chamberDiameter', 'Chamber outer diameter', 'float', default = 0.18, unit = 'm',
              help = 'Outer diameter of the chamber wall at the converging inlet. Sets the contraction ratio.'),
        Field('raoThroatAngle', 'Converging wall angle at throat', 'float', default = 30.0, unit = 'deg',
              help = 'Wall angle of the converging section where it meets the throat.'),
        Field('chamberInterfaceAngle', 'Converging wall angle at chamber', 'float', default = 15.0, unit = 'deg',
              help = 'Wall angle where the converging section meets the chamber. Must differ from the throat angle.'),
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
        Field('truncateOn', 'Binding constraint', 'choice',
              choices = [('Area ratio', 'areaRatio'), ('Exit wall pressure', 'wallPressure'),
                         ('Length', 'length')], default = 'areaRatio',
              help = 'Which requested number the geometry is held to. A truncated ideal contour '
                     'has one free parameter, so two of the three can be delivered and not all '
                     'three. Area ratio cuts at the requested expansion ratio. Exit wall pressure '
                     'cuts where the wall static pressure reaches the target exit pressure, which '
                     'is the maximum-thrust nozzle for that ambient and is what a pressure-matched '
                     'design means; set the target to the operating ambient. Both then solve the '
                     'design Mach number for the requested length fraction. Length cuts at the '
                     'requested length and delivers neither; it is kept for earlier designs.'),
        Field('numCharacteristics', 'Characteristics', 'int', default = 50,
              help = 'Characteristics launched from the throat arc, which sets the mesh resolution '
                     'of the whole solve. At the default the exit wall angle carries about 2 '
                     'percent of mesh error and the thrust coefficient about 1 percent.'),
        Field('conicalHalfAngle', 'Conical half angle', 'float', default = None, unit = 'deg',
              showWhen = _divergingIsConical,
              help = 'Half angle of the diverging cone.'),
        Field('truncationMethod', 'Regen truncation method', 'choice',
              choices = [('None (full contour)', 'none'), ('Wall temperature', 'temp'), ('Area ratio', 'er')],
              default = 'none',
              help = 'Split the regen-cooled section from a radiation-cooled extension by near-wall '
                     'gas temperature or by area ratio. The cut point is entered below.'),
        Field('truncationTemperature', 'Truncation wall temperature', 'float', default = None, unit = 'K',
              synthetic = True, showWhen = _truncateByTemp,
              help = 'Near-wall gas temperature at which the regen section ends. Folded into '
                     "the backend as 'temp <K>'."),
        Field('truncationAreaRatio', 'Truncation area ratio', 'float', default = None,
              synthetic = True, showWhen = _truncateByAreaRatio,
              help = "Local area ratio at which the regen section ends. Folded into the backend as 'er <ratio>'."),
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
        Field('channelType', 'Channel type', 'choice',
              choices = [('Fluted', 'fluted'), ('Circular', 'circle')],
              default = 'fluted', showWhen = _coolingOn, help = 'Cooling channel cross-section family.'),
        Field('drivingTemperatureModel', 'Driving gas temperature', 'choice',
              choices = [('Recovery', 'recovery'), ('Static', 'static')],
              default = 'recovery', showWhen = _coolingOn,
              help = 'Which gas temperature drives the heat flux. Recovery is the adiabatic '
                     'wall temperature and is the physical choice. Static reproduces results '
                     'recorded before the recovery temperature was carried through, and '
                     'understates the flux by the whole recovery rise.'),
        Field('hotWallThickness', 'Hot wall thickness', 'float', default = None, unit = 'm',
              showWhen = _coolingOn, help = 'Combustion-side wall thickness.'),
        Field('shellThickness', 'Shell thickness', 'float', default = None, unit = 'm',
              showWhen = _coolingOn, help = 'Outer structural shell thickness.'),
        Field('infillThickness', 'Infill thickness', 'float', default = None, unit = 'm',
              showWhen = _coolingOn, help = 'Rib / infill thickness between channels.'),
        Field('nChannel', 'Number of channels', 'int', default = None, showWhen = _coolingOn,
              help = 'Fixed channel count. Leave blank to let the optimizer choose within the bounds below.'),
        Field('numFlutes', 'Number of flutes', 'int', default = None, showWhen = _coolingOn,
              help = 'Flute count for the fluted channel type.'),
        Field('fluteAmplitudeCoef', 'Flute amplitude coefficient', 'float', default = None, showWhen = _coolingOn,
              help = 'Flute amplitude as a fraction of the local channel radius.'),
        Field('fluteHelixAngle', 'Flute helix angle', 'float', default = None, unit = 'deg', showWhen = _coolingOn,
              help = 'Helix angle of the fluted channels.'),
        Field('interfaceLength', 'Circular interface length', 'float', default = None, unit = 'm', showWhen = _coolingOn,
              help = 'Length of the circular channel interface at the volute ends.'),
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
        Field('printabilityCheck', 'Check printability', 'bool', default = False, showWhen = _coolingOn,
              help = 'Flag channel walls that exceed the maximum overhang angle for the print direction.'),
        Field('printDirection', 'Print direction', 'choice',
              choices = [('Positive Z', '+z'), ('Negative Z', '-z')], default = '+z', showWhen = _printabilityOn,
              help = 'Build direction for the printability check.'),
        Field('maxOverhangAngle', 'Max overhang angle', 'float', default = None, unit = 'deg', showWhen = _printabilityOn,
              help = 'Maximum self-supporting overhang from vertical.'),
    ], collapsed = True, expandWhen = _coolingOn),

    Group('Film Cooling', [
        Field('filmCooling', 'Film cooling', 'bool', default = False,
              help = 'Inject a sheet of coolant along the wall. It lowers the temperature '
                     'the wall is driven by rather than carrying heat away, and it works '
                     'with a jacket rather than instead of one.'),
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
        Field('plotKeepOut', 'Plot keep-out', 'bool', default = False, showWhen = _anyVolute,
              help = 'Include the chamber closure keep-out envelope in the volute views.'),
        Field('keepOutAxialOffset', 'Keep-out axial offset', 'float', default = None, unit = 'm', showWhen = _anyVolute,
              help = 'Axial station of the keep-out shoulder, relative to the chamber end.'),
        Field('keepOutRadius', 'Keep-out radius', 'float', default = None, unit = 'm', showWhen = _anyVolute,
              help = 'Widest radius of the keep-out envelope. Blank takes the chamber radius.'),
        Field('keepOutDepth', 'Keep-out depth', 'float', default = None, unit = 'm', showWhen = _anyVolute,
              help = 'Axial depth from the keep-out shoulder to its hub. Blank takes half the keep-out radius.'),
        Field('keepOutHubRadius', 'Keep-out hub radius', 'float', default = None, unit = 'm', showWhen = _anyVolute,
              help = 'Radius the keep-out is truncated at. Blank takes a quarter of the keep-out radius.'),
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
              help = 'Axial offset of the inlet volute turnaround.'),
        Field('inletVoluteFlareRoverD', 'Inlet flare R/D', 'float', default = None, showWhen = _anyVolute,
              help = 'Flare radius over diameter for the inlet channel entry.'),
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
              help = 'Axial offset of the return volute turnaround.'),
        Field('returnVoluteRadialOffset', 'Return volute radial offset', 'float', default = None, unit = 'm', showWhen = _anyVolute,
              help = 'Radial offset of the return volute turnaround.'),
        Field('returnVoluteFlareRoverD', 'Return flare R/D', 'float', default = None, showWhen = _anyVolute,
              help = 'Flare radius over diameter for the return channel exit.'),
        Field('returnVoluteReturnAngle', 'Return channel angle', 'float', default = None, unit = 'deg', showWhen = _anyVolute,
              help = 'Return angle of the collected channel flow.'),
        Field('returnVoluteFlareLen', 'Return flare length', 'float', default = None, unit = 'm', showWhen = _anyVolute,
              help = 'Flare extension length for the return channel exit.'),
    ], collapsed = True, note = 'Requires cooling channels to be enabled.', expandWhen = _anyVolute),

    Group('Program Options', [
        Field('filename', 'Output name', 'text', default = 'novaRun',
              help = 'Base name for the output folder: <name>Outputs/ beside the export location.'),
        Field('plotsAdv', 'Advanced plots', 'bool', default = False,
              help = 'Write the interactive channel-mesh HTML views.'),
        Field('plotJacket', 'Full jacket plot', 'bool', default = False,
              help = 'Write the full regen jacket HTML view.'),
        Field('plotsDebug', 'Debug plots', 'bool', default = False,
              help = 'Write additional diagnostic figures.'),
        Field('visualizeContour', 'Contour plots', 'bool', default = True,
              help = 'Write the contour, Mach, pressure, temperature and near-wall figures. Forced on by the GUI.'),
        Field('plotsBasic', 'Basic plots', 'bool', default = True,
              help = 'Write the basic result figures. Forced on by the GUI.'),
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
