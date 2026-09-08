# -- NOVA GUI Unit Conversions -- #

'''

Per-field display units for the config form. Every field is stored and handed to the backend in
NOVA's own SI unit; this module converts between that and whatever unit the field's dropdown is
set to.

A unit is an affine map: SI = display * scale + offset. Pure scale factors (offset 0) cover
pressure, length, force and mass flow; temperature carries an offset. `dimensionForUnit` maps a
schema field's declared unit string to one of the dimension tables below.

Factors match src/NOVA/units.py and ceaInterface.py so a value typed in psi lands on
the same Pa the CEA interface would compute.

Author: Sean Bowman
Date:   08/28/2026

'''

# scale, offset such that  siValue = displayValue * scale + offset
_dimensions = {

    'length': {
        'si': 'm',
        'units': {
            'm':  (1.0, 0.0),
            'mm': (1.0e-3, 0.0),
            'cm': (1.0e-2, 0.0),
            'in': (0.0254, 0.0),
            'ft': (0.3048, 0.0),
        },
    },

    # Grayloc seal diameters are already inches on the backend, so 'in' is the SI slot here.
    'lengthInch': {
        'si': 'in',
        'units': {
            'in': (1.0, 0.0),
            'mm': (1.0 / 25.4, 0.0),
            'cm': (1.0 / 2.54, 0.0),
        },
    },

    'pressure': {
        'si': 'Pa',
        'units': {
            'Pa':  (1.0, 0.0),
            'kPa': (1.0e3, 0.0),
            'MPa': (1.0e6, 0.0),
            'bar': (1.0e5, 0.0),
            'psi': (6894.757293168361, 0.0),
            'atm': (101325.0, 0.0),
            'torr': (133.32236842105263, 0.0),
        },
    },

    'force': {
        'si': 'N',
        'units': {
            'N':   (1.0, 0.0),
            'kN':  (1.0e3, 0.0),
            'MN':  (1.0e6, 0.0),
            'lbf': (4.4482216152605, 0.0),
        },
    },

    'temperature': {
        'si': 'K',
        'units': {
            'K':    (1.0, 0.0),
            'degC': (1.0, 273.15),
            'degR': (5.0 / 9.0, 0.0),
            'degF': (5.0 / 9.0, 273.15 - 32.0 * 5.0 / 9.0),
        },
    },

    'angle': {
        'si': 'deg',
        'units': {
            'deg': (1.0, 0.0),
            'rad': (57.29577951308232, 0.0),
        },
    },

    'massFlow': {
        'si': 'kg/s',
        'units': {
            'kg/s':  (1.0, 0.0),
            'g/s':   (1.0e-3, 0.0),
            'lbm/s': (0.45359237, 0.0),
            't/h':   (1000.0 / 3600.0, 0.0),
        },
    },
}

# schema `unit` string -> dimension name
_unitToDimension = {
    'm': 'length',
    'in': 'lengthInch',
    'Pa': 'pressure',
    'N': 'force',
    'K': 'temperature',
    'deg': 'angle',
    'kg/s': 'massFlow',
}

def dimensionForUnit(unitString: str):

    '''

    Dimension name for a schema field's declared unit, or None if the field is dimensionless.

    '''

    return _unitToDimension.get(unitString)

def unitsFor(dimension: str) -> list:

    '''

    Ordered list of display-unit names for a dimension, SI unit first.

    '''

    table = _dimensions[dimension]
    ordered = [table['si']] + [name for name in table['units'] if name != table['si']]
    return ordered

def siUnit(dimension: str) -> str:

    '''

    The backend unit name for a dimension.

    '''

    return _dimensions[dimension]['si']

def toSI(value: float, dimension: str, unit: str) -> float:

    '''

    Convert a display value to the backend SI value for its dimension.

    '''

    scale, offset = _dimensions[dimension]['units'][unit]
    return value * scale + offset

def fromSI(value: float, dimension: str, unit: str) -> float:

    '''

    Convert a backend SI value to the display value for a chosen unit.

    '''

    scale, offset = _dimensions[dimension]['units'][unit]
    return (value - offset) / scale
