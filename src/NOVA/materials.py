
# -- Material Property Lookup -- #

'''

Structural and thermal property data for the alloys used in NOVA nozzle hardware.

Two layers:

  materialProperties(material, temperature)
      Scalar room-temperature structural and thermal values with a linear cryogenic strength
      correction. Typical handbook values for preliminary sizing, NOT design allowables. Use
      MMPDS or the material specification for anything that flies. Seeded from
      orbitalRockets/common/materials.py.

  wallMaterialCurves(material)
      Temperature-dependent thermal conductivity, and where published, 0.2 % yield strength,
      mean CTE and elongation, for the regenerative-cooling wall alloys. This is what the
      Nozzle heat transfer model samples: wall temperature ranges from ~300 K coolant side to
      1000 K+ hot side, so a single room-temperature conductivity would misstate the gradient.

Validation of the conductivity curves against their cited sources is in
tests/testMaterials.py; the error at each reference temperature is quantified there.

Local fork of orbitalRockets/common/materials.py. Diverge freely; the source is no longer
maintained.

Author: Sean Bowman
Date:   08/06/2026

'''

import warnings

import numpy as np

from . import units

#--------------------------------------------------------------------------------------------------------------------------#
# -- Material and Surface Data -- #
#--------------------------------------------------------------------------------------------------------------------------#

def materialProperties(material: str, temperature: float = 293.15) -> dict:

    '''

    Structural and thermal property lookup for the alloys that show up in aerospace fluid systems.

    Room-temperature values with a linear cryogenic correction where one is meaningful. These are
    typical handbook values for preliminary sizing, NOT design allowables. Use MMPDS or the material
    specification for anything that flies.

    Returned dictionary keys, all mass-base SI:
        'density'              [kg/m^3]
        'yieldStrength'        [Pa]   0.2 % offset at the requested temperature
        'ultimateStrength'     [Pa]
        'elasticModulus'       [Pa]
        'poissonRatio'         [-]
        'thermalConductivity'  [W/m-K]
        'thermalExpansion'     [1/K]  mean CTE from 293 K to the requested temperature
        'allowableStress'      [Pa]   ASME B31.3 style, min(2/3 yield, 1/3.5 ultimate)
        'notes'                [str]  the thing that will bite you with this alloy

    '''

    materialTable = {
        '304L': {
            'density': 8000.0, 'yieldStrength': 170.0e6, 'ultimateStrength': 485.0e6,
            'elasticModulus': 193.0e9, 'poissonRatio': 0.29, 'thermalConductivity': 16.2,
            'thermalExpansion': 17.3e-6, 'cryogenicYieldFactor': 2.5,
            'notes': 'Austenitic, fully ductile to LH2 temperature, non-magnetic until cold worked. Low carbon variant resists sensitization during welding.'
        },
        '316L': {
            'density': 8000.0, 'yieldStrength': 170.0e6, 'ultimateStrength': 485.0e6,
            'elasticModulus': 193.0e9, 'poissonRatio': 0.29, 'thermalConductivity': 16.3,
            'thermalExpansion': 16.0e-6, 'cryogenicYieldFactor': 2.4,
            'notes': 'The default aerospace fluid system alloy. Molybdenum adds pitting resistance. Compatible with hydrazine, LOX and cryogens. Galls badly against itself in threaded joints without plating.'
        },
        '321': {
            'density': 8000.0, 'yieldStrength': 205.0e6, 'ultimateStrength': 515.0e6,
            'elasticModulus': 193.0e9, 'poissonRatio': 0.29, 'thermalConductivity': 16.1,
            'thermalExpansion': 16.6e-6, 'cryogenicYieldFactor': 2.3,
            'notes': 'Titanium stabilized against sensitization. Preferred where welds see 800-1500 F service, common in hot gas and gas generator lines.'
        },
        '6061-T6': {
            'density': 2700.0, 'yieldStrength': 276.0e6, 'ultimateStrength': 310.0e6,
            'elasticModulus': 68.9e9, 'poissonRatio': 0.33, 'thermalConductivity': 167.0,
            'thermalExpansion': 23.6e-6, 'cryogenicYieldFactor': 1.25,
            'notes': 'Loses roughly 40 percent of its yield strength in the weld heat affected zone and does not recover without a full solution treat and age. Never size an aluminum weldment on parent metal properties.'
        },
        '7075-T73': {
            'density': 2810.0, 'yieldStrength': 435.0e6, 'ultimateStrength': 505.0e6,
            'elasticModulus': 71.7e9, 'poissonRatio': 0.33, 'thermalConductivity': 155.0,
            'thermalExpansion': 23.4e-6, 'cryogenicYieldFactor': 1.2,
            'notes': 'High strength but not weldable and susceptible to stress corrosion cracking in the short transverse direction. Fittings and manifold bodies only.'
        },
        'INCONEL 718': {
            'density': 8190.0, 'yieldStrength': 1034.0e6, 'ultimateStrength': 1276.0e6,
            'elasticModulus': 200.0e9, 'poissonRatio': 0.29, 'thermalConductivity': 11.4,
            'thermalExpansion': 13.0e-6, 'cryogenicYieldFactor': 1.15,
            'notes': 'Precipitation hardened, requires post-weld solution and age to recover joint properties. Resistant to hydrogen embrittlement relative to other superalloys but not immune.'
        },
        'INCONEL 625': {
            'density': 8440.0, 'yieldStrength': 414.0e6, 'ultimateStrength': 827.0e6,
            'elasticModulus': 207.0e9, 'poissonRatio': 0.31, 'thermalConductivity': 9.8,
            'thermalExpansion': 12.8e-6, 'cryogenicYieldFactor': 1.2,
            'notes': 'Solid solution strengthened, weldable without post-weld heat treatment. Common for hot gas ducting and bellows.'
        },
        'TI-6AL-4V': {
            'density': 4430.0, 'yieldStrength': 880.0e6, 'ultimateStrength': 950.0e6,
            'elasticModulus': 113.8e9, 'poissonRatio': 0.342, 'thermalConductivity': 6.7,
            'thermalExpansion': 8.6e-6, 'cryogenicYieldFactor': 1.4,
            'notes': 'Outstanding strength to weight for pressure vessels. Absolutely incompatible with LOX, GOX, red fuming nitric acid and N2O4: it is impact sensitive and will burn. Never use in an oxidizer system.'
        },
        'MONEL 400': {
            'density': 8800.0, 'yieldStrength': 240.0e6, 'ultimateStrength': 550.0e6,
            'elasticModulus': 179.0e9, 'poissonRatio': 0.32, 'thermalConductivity': 21.8,
            'thermalExpansion': 13.9e-6, 'cryogenicYieldFactor': 1.5,
            'notes': 'Nickel-copper, one of the few alloys usable in gaseous fluorine and high concentration hydrogen peroxide service. Expensive and hard to machine.'
        }
    }

    key = material.strip().upper()
    if key not in materialTable:
        raise KeyError(f'materialProperties has no entry for \'{material}\'. Available: {sorted(materialTable.keys())}')

    entry = dict(materialTable[key])

    # Cryogenic strength correction. Austenitic stainless and nickel alloys gain substantial strength
    # on cooling; the factor is applied linearly between room temperature and 77 K and held constant
    # below that. This is a preliminary-sizing approximation, not a design allowable.
    if temperature < 293.15:
        fraction              = min(1.0, (293.15 - temperature) / (293.15 - 77.0))
        strengthFactor        = 1.0 + fraction * (entry['cryogenicYieldFactor'] - 1.0)
        entry['yieldStrength']    *= strengthFactor
        entry['ultimateStrength'] *= strengthFactor

    # ASME B31.3 style basic allowable stress. The governing criterion below the creep range is the
    # lesser of two thirds of yield and one third of ultimate (B31.3 uses 1/3 UTS; the 3.5 divisor
    # here is the more conservative Section VIII Division 1 basis, kept because flight hardware
    # rarely gets to use the thinner of the two).
    entry['allowableStress'] = min(2.0 / 3.0 * entry['yieldStrength'], entry['ultimateStrength'] / 3.5)
    entry['temperature']     = temperature

    return entry

def roughnessTable(surface: str = 'drawn tube') -> float:

    '''

    Absolute surface roughness [m] by material and manufacturing process.

    Roughness only matters through eps/D, so it matters enormously in small-bore tubing and barely
    at all in a large duct. A 0.0015 mm drawn-tube roughness in a 6 mm ID line is eps/D = 2.5e-4,
    which is squarely in the roughness-dependent part of the Moody diagram.

    The additive entries are the ones people get wrong: as-built LPBF internal surfaces are one to
    two orders of magnitude rougher than drawn tube, and downskin surfaces are worse than upskin.
    An additively manufactured manifold sized on drawn-tube roughness will under-predict its
    pressure drop by a large factor.

    '''

    roughnessValues = {
        'drawn tube':        1.5e-6,    # drawn stainless, copper, aluminum tubing
        'commercial steel':  45.0e-6,   # welded and seamless steel pipe
        'stainless pipe':    15.0e-6,   # commercial stainless pipe
        'galvanized':        150.0e-6,
        'cast iron':         260.0e-6,
        'concrete':          1000.0e-6,
        'glass':             0.0,       # hydraulically smooth
        'flexhose':          300.0e-6,  # convoluted metal hose, dominated by the convolutions
        'braided flexhose':  500.0e-6,
        'lpbf as-built':     20.0e-6,   # laser powder bed fusion, upskin, well developed parameters
        'lpbf downskin':     40.0e-6,   # overhanging surfaces, partially sintered powder adhesion
        'lpbf abrasive flow': 5.0e-6,   # after abrasive flow machining of internal passages
        'ded as-built':      100.0e-6   # directed energy deposition
    }

    key = surface.strip().lower()
    if key not in roughnessValues:
        raise KeyError(f'roughnessTable has no entry for \'{surface}\'. Available: {sorted(roughnessValues.keys())}')

    return roughnessValues[key]

#--------------------------------------------------------------------------------------------------------------------------#
# -- Temperature-Dependent Wall Alloy Curves -- #
#--------------------------------------------------------------------------------------------------------------------------#

# Thermal conductivity as a function of temperature for the alloys a regen-cooled nozzle wall
# might be built from. The heat transfer model marches wall temperature from the ~300 K coolant
# side to 1000 K or more on the hot side, so it samples k(T) rather than a single value.
#
# Each entry carries its temperature grid in degrees Celsius (converted to kelvin on read),
# thermal conductivity in W/m-K, and, where an entry is a scalar rather than an array, that
# scalar is held constant across the grid. Yield strength, CTE and elongation are secondary
# outputs, off the thermal solution path; only GRCop-42 carries real temperature curves for
# them and the rest are held at their room-temperature value with that stated in `source`.
#
# Conductivity curves are validated against their cited sources in tests/testMaterials.py.
#
# A property written as a list is a measured curve. A property written as a scalar is one
# value held flat across the grid, and `wallMaterialCurves` reports which is which in its
# 'measured' map, because the two are the same shape once broadcast. Twenty-seven of the
# forty properties here are held flat, and none of the grids reaches cryogenic temperature.
# docs/materialsDatabaseRoadmap.md carries what closing those gaps would take.

_WALLCURVEDATA = {

    'GRCop-42': {
        'temperatureC':        [25, 100, 200, 300, 400, 500, 600, 700, 800, 900],
        'thermalConductivity': [289, 301, 310, 313, 312, 308, 301, 293, 284, 274],   # [W/m-K]
        'yieldStrength':       [199.6e6, 186.3e6, 171.1e6, 156.9e6, 140.6e6,
                                121.6e6, 98.7e6, 68.8e6, 31.2e6, 1.0e6],              # [Pa], 0.2 % offset
        'cte':                 [1.5e-6, 9.3e-6, 14.4e-6, 16.3e-6, 16.9e-6,
                                17.2e-6, 17.7e-6, 18.2e-6, 18.7e-6, 19.0e-6],         # [1/K], mean from 293 K
        'elongation':          [30.0, 27.1, 24.2, 22.3, 21.1, 20.3, 19.7, 19.2, 18.5, 17.8],  # [%]
        'density':             8756.0,   # [kg/m^3]
        'elasticModulus':      124.0e9,  # [Pa]
        'source':              'NASA "GRCop-42 and -84 Typical Average Summary" (k); NASA GRCop-42 '
                               'tensile report (yield, elongation); NASA GRCop-42 CTE report.',
        'provenance': {
            'thermalConductivity': ('NASA GRCop-42/-84 typical average summary.', (25, 900)),
            'yieldStrength':       ('NASA GRCop-42 tensile report.', (25, 900)),
            'cte':                 ('NASA GRCop-42 thermal expansion report.', (25, 900)),
            'elongation':          ('NASA GRCop-42 tensile report.', (25, 900)),
        },
    },

    'CuCrZr': {
        'temperatureC':        [20, 100, 200, 300, 400, 500, 600],
        'thermalConductivity': [320, 324, 333, 335, 332, 327, 320],   # [W/m-K]
        # Mean from 20 degC, from the quadratic expansion fit of de Groh et al. Table 5 for
        # Cu-1Cr-0.1Zr (C18150). The first entry is the instantaneous value at 20 degC, where the
        # mean from 20 degC is undefined.
        'cte':                 [1.5788e-05, 1.6184e-05, 1.6678e-05, 1.7173e-05,
                                1.7668e-05, 1.8162e-05, 1.8657e-05],   # [1/K]
        'yieldStrength':       350.0e6,   # [Pa], solution treated and aged, held constant
        'elongation':          20.0,
        'density':             8900.0,
        'elasticModulus':      128.0e9,
        'source':              'ITER Material Properties Handbook, CuCrZr (C18150), solution annealed '
                               'and aged (k, strength). Expansion from de Groh, Ellis and Loewenthal, '
                               'NASA/TM-2007-214663 Table 5.',
        'provenance': {
            'thermalConductivity': ('ITER Material Properties Handbook, CuCrZr (C18150), '
                                    'solution annealed and aged.', (20, 600)),
            'yieldStrength':       ('ITER handbook room-temperature value, held flat. No '
                                    'temperature-resolved source located.', (20, 20)),
            'cte':                 ('de Groh, Ellis and Loewenthal, NASA/TM-2007-214663, Table 5, '
                                    'Cu-1Cr-0.1Zr quadratic expansion fit, stated +/-1 %.', (20, 600)),
            'elongation':          ('ITER handbook room-temperature value, held flat.', (20, 20)),
        },
    },

    'OFHC Copper': {
        # Cryogenic segment from the NIST fit for RRR = 50, normalised by x0.9962 onto the
        # room-temperature value below; the two sources differ by 0.4 % at 298 K.
        'temperatureC':        [-253.1, -233.1, -196.1, -183.1, -153.1, -113.1, -73.1, -23.1,
                                25, 100, 200, 300, 400, 500, 600, 700, 800, 900],
        'thermalConductivity': [1362.68, 1158.96, 513.13, 463.37, 420.2, 404.49, 398.59, 394.24,
                                391, 385, 381, 377, 372, 366, 360, 354, 347, 340],   # [W/m-K]
        'cte':                 [1.1921e-05, 1.2778e-05, 1.4085e-05, 1.4427e-05, 1.5043e-05,
                                1.5632e-05, 1.6062e-05, 1.6425e-05, 1.7000e-05, 1.7000e-05,
                                1.7000e-05, 1.7000e-05, 1.7000e-05, 1.7000e-05, 1.7000e-05,
                                1.7000e-05, 1.7000e-05, 1.7000e-05],   # [1/K], mean from 293 K
        'yieldStrength':       70.0e6,    # [Pa], annealed, held constant
        'elongation':          45.0,
        'density':             8940.0,
        'elasticModulus':      117.0e9,
        'source':              'NIST Cryogenic Material Properties Database, OFHC copper '
                               'C10100/C10200 (k below 300 K, expansion); Touloukian TPRC / CRC '
                               'Handbook above room temperature. Strength and elongation are the '
                               'room-temperature annealed values held flat.',
        'provenance': {
            'thermalConductivity': ('NIST cryogenic database, RRR = 50 fit, 4-300 K, stated 2 %; '
                                    'Touloukian TPRC above 298 K. STRONGLY purity dependent: at '
                                    '20 K the NIST fit spans 1368 to 3245 W/m-K over RRR 50 to '
                                    '150, and room temperature cannot distinguish them.',
                                    (-253.1, 900)),
            'yieldStrength':       ('Annealed room-temperature value, held flat.', (25, 25)),
            'cte':                 ('NIST cryogenic database expansion fit, 4-300 K, stated 5 % '
                                    'above 50 K; held flat above 25 degC.', (-253.1, 25)),
            'elongation':          ('Annealed room-temperature value, held flat.', (25, 25)),
        },
    },

    'NARloy-Z': {
        'temperatureC':        [25, 100, 200, 300, 400, 500, 600, 700, 800],
        'thermalConductivity': [290, 296, 304, 310, 314, 316, 316, 314, 311],   # [W/m-K], approximate
        'yieldStrength':       100.0e6,   # [Pa], held constant
        'cte':                 18.0e-6,
        'elongation':          20.0,
        'density':             8940.0,
        'elasticModulus':      110.0e9,
        'source':              'NARloy-Z (Cu-3Ag-0.5Zr), SSME main combustion chamber alloy. '
                               'Room-temperature k ~290 W/m-K is well established; the temperature '
                               'trend here is approximate and is NOT independently validated.',
        'provenance': {
            'thermalConductivity': ('Room-temperature value well established; the trend is '
                                    'approximate and NOT independently validated.', (25, 800)),
            'yieldStrength':       ('Room-temperature value held flat. Literature reports yield '
                                    'roughly flat to 500 degC then halving by 600-700 degC, but no '
                                    'tabulated curve on a single product form was located.',
                                    (25, 25)),
            'cte':                 ('Room-temperature value held flat.', (25, 25)),
            'elongation':          ('Room-temperature value held flat.', (25, 25)),
        },
    },

    'AlSi10Mg': {
        'temperatureC':        [25, 100, 200, 300, 400, 500, 600, 700, 800, 900],
        'thermalConductivity': [110.1, 112, 113, 116, 116, 109, 72, 51, 51, 51],   # [W/m-K]
        'yieldStrength':       230.0e6,   # [Pa], LPBF T6, held constant
        'cte':                 20.0e-6,
        'elongation':          6.0,
        'density':             2670.0,
        'elasticModulus':      70.0e9,
        'source':              'AlSi10Mg LPBF, vendor simulation data carried from the original NOVA '
                               'heat transfer model. Not traceable to a primary source; retained for continuity.',
        'provenance': {
            'thermalConductivity': ('Vendor simulation data, not traceable to a primary source. '
                                    'The alloy melts near 590 degC, so the entries above that are '
                                    'not physical.', (25, 900)),
            'yieldStrength':       ('LPBF T6 room-temperature value, held flat.', (25, 25)),
            'cte':                 ('Room-temperature value held flat.', (25, 25)),
            'elongation':          ('LPBF T6 room-temperature value, held flat.', (25, 25)),
        },
    },

    'Al 6061-T6': {
        # Cryogenic segment from the NIST fit, normalised by x1.0770 onto the room-temperature
        # value below; the two sources differ by 7.1 % at 298 K.
        'temperatureC':        [-253.1, -233.1, -196.1, -183.1, -153.1, -113.1, -73.1, -23.1,
                                25, 100, 200, 300, 400],
        'thermalConductivity': [30.62, 56.25, 89.96, 98.99, 116.17, 133.48, 146.49, 158.57,
                                167, 172, 177, 180, 182],   # [W/m-K]
        'cte':                 [1.5216e-05, 1.6265e-05, 1.7995e-05, 1.8538e-05, 1.9663e-05,
                                2.0883e-05, 2.1783e-05, 2.2460e-05, 2.3600e-05, 2.3600e-05,
                                2.3600e-05, 2.3600e-05, 2.3600e-05],   # [1/K], mean from 293 K
        'yieldStrength':       276.0e6,
        'elongation':          12.0,
        'density':             2700.0,
        'elasticModulus':      68.9e9,
        'source':              'NIST Cryogenic Material Properties Database, 6061-T6 (k and '
                               'expansion below 300 K); ASM Handbook Vol 2 above room temperature. '
                               'Grid capped at 400 C where the T6 temper is lost. Strength and '
                               'elongation held flat.',
        'provenance': {
            'thermalConductivity': ('NIST cryogenic database fit, 1-300 K, stated 0.5 %; ASM '
                                    'Handbook Vol 2 above 298 K.', (-253.1, 400)),
            'yieldStrength':       ('ASM Handbook room-temperature T6 value, held flat. The T6 '
                                    'temper over-ages above about 200 degC, so the flat value is '
                                    'unconservative there.', (25, 25)),
            'cte':                 ('NIST cryogenic database expansion fit, 4-300 K, stated 4 %; '
                                    'held flat above 25 degC.', (-253.1, 25)),
            'elongation':          ('ASM Handbook room-temperature T6 value, held flat.', (25, 25)),
        },
    },

    'Inconel 718': {
        # Cryogenic conductivity from the NIST fit, normalised by x1.1468 onto the
        # room-temperature value below; the two sources differ by 12.8 % at 298 K, the largest
        # join disagreement in this table. Yield and elongation are measured across the whole
        # grid, spliced from two Special Metals tables that differ by 1.8 % where they overlap.
        'temperatureC':        [-253.1, -233.1, -196.1, -183.1, -153.1, -113.1, -78.9, -73.1,
                                -23.1, 21.1, 25, 100, 200, 300, 315.6, 400, 500, 537.8, 600,
                                648.9, 700, 704.4, 760, 800, 815.6, 900],
        'thermalConductivity': [3.39, 5.44, 7.38, 7.85, 8.7, 9.48, 9.92, 10.0, 10.55, 11.15,
                                11.2, 12.5, 14.1, 15.7, 15.95, 17.3, 18.9, 19.47, 20.4, 21.18,
                                22.0, 22.07, 23.02, 23.7, 23.97, 25.4],   # [W/m-K]
        'yieldStrength':       [1.3438e+09, 1.3246e+09, 1.2884e+09, 1.2788e+09, 1.2568e+09,
                                1.2275e+09, 1.2024e+09, 1.1979e+09, 1.1586e+09, 1.1238e+09,
                                1.1232e+09, 1.1109e+09, 1.0945e+09, 1.0781e+09, 1.0756e+09,
                                1.0546e+09, 1.0298e+09, 1.0204e+09, 9.8954e+08, 9.6527e+08,
                                9.3353e+08, 9.3079e+08, 7.9979e+08, 7.2043e+08, 6.8948e+08,
                                6.8948e+08],   # [Pa], 0.2 % offset
        'cte':                 [8.7467e-06, 9.3602e-06, 1.0350e-05, 1.0653e-05, 1.1264e-05,
                                1.1885e-05, 1.2228e-05, 1.2286e-05, 1.2478e-05, 1.2958e-05,
                                1.3000e-05, 1.3000e-05, 1.3000e-05, 1.3000e-05, 1.3000e-05,
                                1.3000e-05, 1.3000e-05, 1.3000e-05, 1.3000e-05, 1.3000e-05,
                                1.3000e-05, 1.3000e-05, 1.3000e-05, 1.3000e-05, 1.3000e-05,
                                1.3000e-05],   # [1/K], mean from 293 K
        'elongation':          [13.5, 13.7, 14.0, 14.3, 15.2, 16.3, 17.2, 17.4, 19.3, 21.0,
                                20.9, 19.7, 18.0, 16.3, 16.0, 16.0, 16.0, 16.0, 15.4, 15.0,
                                8.6, 8.0, 5.0, 12.2, 15.0, 15.0],   # [%]
        'density':             8190.0,
        'elasticModulus':      200.0e9,
        'source':              'NIST Cryogenic Material Properties Database, Inconel 718 (k and '
                               'expansion below 300 K); Special Metals INCONEL alloy 718 bulletin '
                               '(k above room temperature, and yield and elongation across the '
                               'whole range, Tables 21 and 19).',
        'provenance': {
            'thermalConductivity': ('NIST cryogenic database fit, 4-300 K, stated 2 %; Special '
                                    'Metals bulletin above 298 K. The two disagree by 12.8 % at '
                                    'the join, the largest in this table, and the cryogenic '
                                    'segment is normalised onto the Special Metals value.',
                                    (-253.1, 900)),
            'yieldStrength':       ('Special Metals INCONEL alloy 718 bulletin. Table 21, forging '
                                    'aged 1800 F/45 min + 1325 F/8 hr, for -423 to -110 F; Table '
                                    '19, hot-rolled 4-in round aged 1950 F/1 hr + 1400 F/10 hr, '
                                    'for 70 to 1500 F. The two product forms differ by 1.8 % at '
                                    'room temperature, which is the splice error.', (-252.8, 815.6)),
            'cte':                 ('NIST cryogenic database expansion fit, 4-300 K, stated 1.1 %; '
                                    'held flat above 25 degC.', (-253.1, 25)),
            'elongation':          ('Special Metals bulletin, same two tables as the yield '
                                    'strength. Elongation is not monotone: it falls to 5 % near '
                                    '760 degC and recovers above it, which is the alloy, not a '
                                    'transcription error.', (-252.8, 815.6)),
        },
    },

    'Inconel 625': {
        'temperatureC':        [21, 93, 204, 316, 427, 538, 649, 760, 871, 982],
        'thermalConductivity': [9.8, 10.8, 12.5, 14.1, 15.7, 17.5, 19.0, 20.8, 22.8, 25.2],   # [W/m-K]
        'yieldStrength':       414.0e6,
        'cte':                 12.8e-6,
        'elongation':          30.0,
        'density':             8440.0,
        'elasticModulus':      207.0e9,
        'source':              'Special Metals INCONEL alloy 625 datasheet (k). Strength, expansion '
                               'and elongation are room-temperature values held flat.',
        'provenance': {
            'thermalConductivity': ('Special Metals INCONEL alloy 625 bulletin.', (21, 982)),
            'yieldStrength':       ('Annealed room-temperature value, held flat. The Special '
                                    'Metals bulletin gives the temperature dependence only as a '
                                    'figure, and digitising a plot is not a source.', (21, 21)),
            'cte':                 ('Room-temperature value held flat.', (21, 21)),
            'elongation':          ('Annealed room-temperature value, held flat.', (21, 21)),
        },
    },

    '316L': {
        # Cryogenic segment from the NIST fit for type 316, normalised by x0.9568 onto the
        # room-temperature value below; the two sources differ by 4.5 % at 298 K.
        'temperatureC':        [-253.1, -233.1, -196.1, -183.1, -153.1, -113.1, -73.1, -23.1,
                                25, 100, 200, 300, 400, 500, 600, 700, 800, 900],
        'thermalConductivity': [2.07, 4.47, 7.58, 8.33, 9.66, 10.98, 12.09, 13.38,
                                14.6, 15.6, 17.0, 18.3, 19.6, 20.9, 22.1, 23.4, 24.6, 25.8],   # [W/m-K]
        'cte':                 [1.0993e-05, 1.1777e-05, 1.2961e-05, 1.3301e-05, 1.3953e-05,
                                1.4572e-05, 1.4967e-05, 1.5244e-05, 1.6000e-05, 1.6000e-05,
                                1.6000e-05, 1.6000e-05, 1.6000e-05, 1.6000e-05, 1.6000e-05,
                                1.6000e-05, 1.6000e-05, 1.6000e-05],   # [1/K], mean from 293 K
        'yieldStrength':       170.0e6,
        'elongation':          40.0,
        'density':             8000.0,
        'elasticModulus':      193.0e9,
        'source':              'NIST Cryogenic Material Properties Database, type 316 (k and '
                               'expansion below 300 K); ASM Handbook Vol 1 / Touloukian above room '
                               'temperature. Strength and elongation held flat.',
        'provenance': {
            'thermalConductivity': ('NIST cryogenic database fit for type 316, 1-300 K, stated '
                                    '2 %; ASM/Touloukian above 298 K. The NIST fit is for 316 '
                                    'rather than 316L; the two differ mainly in carbon, which has '
                                    'little effect on conductivity.', (-253.1, 900)),
            'yieldStrength':       ('ASTM A240 room-temperature minimum for 316L, held flat.',
                                    (25, 25)),
            'cte':                 ('NIST cryogenic database expansion fit, 4-300 K, stated 5 %; '
                                    'held flat above 25 degC.', (-253.1, 25)),
            'elongation':          ('Annealed room-temperature value, held flat.', (25, 25)),
        },
    },

    'Ti-6Al-4V': {
        # Cryogenic segment from the NIST fit, normalised by x0.9095 onto the room-temperature
        # value below; the two sources differ by 9.9 % at 293 K.
        'temperatureC':        [-253.1, -233.1, -196.1, -183.1, -153.1, -113.1, -73.1, -23.1,
                                20, 100, 200, 300, 400, 500, 600, 700, 800],
        'thermalConductivity': [0.77, 1.73, 3.16, 3.35, 3.69, 4.41, 5.23, 6.0,
                                6.7, 7.4, 8.7, 9.8, 10.3, 11.8, 13.4, 15.5, 17.9],   # [W/m-K]
        'cte':                 [6.3596e-06, 6.8154e-06, 7.5153e-06, 7.7149e-06, 8.0840e-06,
                                8.3769e-06, 8.4423e-06, 8.2041e-06, 8.6000e-06, 8.6000e-06,
                                8.6000e-06, 8.6000e-06, 8.6000e-06, 8.6000e-06, 8.6000e-06,
                                8.6000e-06, 8.6000e-06],   # [1/K], mean from 293 K
        'yieldStrength':       880.0e6,
        'elongation':          14.0,
        'density':             4430.0,
        'elasticModulus':      113.8e9,
        'source':              'NIST Cryogenic Material Properties Database, Ti-6Al-4V (k and '
                               'expansion below 300 K); ASM Handbook Vol 2 / MMPDS annealed above '
                               'room temperature. Strength and elongation held flat.',
        'provenance': {
            'thermalConductivity': ('NIST cryogenic database fit, 20-300 K, stated 2 %; '
                                    'ASM/MMPDS above 293 K.', (-253.1, 800)),
            'yieldStrength':       ('Annealed room-temperature value, held flat. MMPDS carries the '
                                    'temperature dependence but is not openly available.',
                                    (20, 20)),
            'cte':                 ('NIST cryogenic database expansion fit, 4-300 K, stated 1.5 %; '
                                    'held flat above 20 degC.', (-253.1, 20)),
            'elongation':          ('Annealed room-temperature value, held flat.', (20, 20)),
        },
    },
}

# Free-text names, and the legacy 'cu' / 'al' / 'in' keys the earlier heat transfer model used,
# folded to the canonical entries above.
_WALLMATERIALALIASES = {
    'cu': 'GRCop-42', 'copper': 'GRCop-42', 'grcop42': 'GRCop-42', 'grcop-42': 'GRCop-42',
    'grcop 42': 'GRCop-42', 'gr-cop42': 'GRCop-42', 'grcop': 'GRCop-42',
    'cucrzr': 'CuCrZr', 'c18150': 'CuCrZr', 'c18200': 'CuCrZr', 'cu-cr-zr': 'CuCrZr',
    'ofhc': 'OFHC Copper', 'ofhc copper': 'OFHC Copper', 'c10100': 'OFHC Copper',
    'c10200': 'OFHC Copper', 'pure copper': 'OFHC Copper', 'etp copper': 'OFHC Copper',
    'narloyz': 'NARloy-Z', 'narloy-z': 'NARloy-Z', 'narloy z': 'NARloy-Z',
    'al': 'AlSi10Mg', 'aluminum': 'AlSi10Mg', 'aluminium': 'AlSi10Mg', 'alsi10mg': 'AlSi10Mg',
    '6061': 'Al 6061-T6', '6061-t6': 'Al 6061-T6', 'al6061': 'Al 6061-T6', 'al 6061': 'Al 6061-T6',
    'in': 'Inconel 718', 'inconel': 'Inconel 718', 'inconel718': 'Inconel 718',
    'in718': 'Inconel 718', 'alloy 718': 'Inconel 718', 'inconel 718': 'Inconel 718',
    'inconel625': 'Inconel 625', 'in625': 'Inconel 625', 'alloy 625': 'Inconel 625',
    'inconel 625': 'Inconel 625',
    '316': '316L', '316l': '316L', 'ss316': '316L', 'ss316l': '316L', '304l': '316L',
    'stainless': '316L', 'stainless steel': '316L',
    'ti6al4v': 'Ti-6Al-4V', 'ti-6al-4v': 'Ti-6Al-4V', 'ti64': 'Ti-6Al-4V',
    'ti-64': 'Ti-6Al-4V', 'grade 5': 'Ti-6Al-4V', 'ti 6al 4v': 'Ti-6Al-4V',
}

def resolveWallMaterialName(material) -> str:

    '''

    Fold a free-text or legacy material key to a canonical wall-alloy name. Unknown input
    returns None so the caller can decide whether to fall back or raise.

    '''

    if material is None:
        return None
    key = str(material).strip()
    if key in _WALLCURVEDATA:
        return key
    return _WALLMATERIALALIASES.get(key.lower())

def availableWallMaterials() -> list:

    '''

    Canonical names of every wall alloy with a conductivity curve, copper alloys first.

    '''

    return ['GRCop-42', 'CuCrZr', 'OFHC Copper', 'NARloy-Z',
            'AlSi10Mg', 'Al 6061-T6', 'Inconel 718', 'Inconel 625', '316L', 'Ti-6Al-4V']

def propertyProvenance(material, propertyName: str) -> tuple:

    '''

    Where a wall-alloy property came from, and over what temperature range it is data.

    A property can be a measured curve over part of its grid and a held constant over the rest.
    `propertyIsMeasured` only says whether it varies at all; this says where.

    Parameters:
    -----------
    material : str
        Canonical name, legacy key or alias.
    propertyName : str
        One of 'thermalConductivity', 'yieldStrength', 'cte', 'elongation'.

    Returns:
    --------
    tuple
        (source, (lowC, highC)) where source cites where the numbers came from and the pair is
        the temperature range in degrees Celsius over which the stored values are measured data.
        Outside that range the property is the nearest measured value held flat.

    '''

    canonical = resolveWallMaterialName(material) or 'GRCop-42'

    return _WALLCURVEDATA[canonical]['provenance'][propertyName]

def propertyIsMeasured(material, propertyName: str) -> bool:

    '''

    True when a wall-alloy property is a measured temperature curve rather than one value held
    flat across the grid.

    Parameters:
    -----------
    material : str
        Canonical name, legacy key or alias.
    propertyName : str
        One of 'thermalConductivity', 'yieldStrength', 'cte', 'elongation'.

    Returns:
    --------
    bool

    Raises:
    -------
    KeyError
        If the property is not one of the four the table carries.

    '''

    return wallMaterialCurves(material)['measured'][propertyName]

def wallMaterialCurves(material) -> dict:

    '''

    Temperature-dependent wall-alloy properties for the regenerative cooling heat transfer model.

    Parameters:
    -----------
    material : str
        Canonical name, legacy key ('cu', 'al', 'in') or a recognized alias.

    Returns:
    --------
    dict with keys, all mass-base SI:
        'material'             [str]        canonical name actually used
        'temperatureK'         [np.ndarray] grid the property arrays are defined on [K]
        'thermalConductivity'  [np.ndarray] [W/m-K]
        'yieldStrength'        [np.ndarray] [Pa]
        'cte'                  [np.ndarray] [1/K]
        'elongation'           [np.ndarray] [%]
        'density'              [float]      [kg/m^3]
        'elasticModulus'       [float]      [Pa]
        'source'               [str]
        'fallback'             [bool]       True when the requested material was not recognized
                                            and GRCop-42 was substituted
        'measured'             [dict]       property name -> True when the array is a measured
                                            curve, False when it is one value held flat across
                                            the grid

    The 'measured' map exists because the four property arrays are the same shape either way. A
    scalar in the table is broadcast across the grid, so an interpolator built on a held-flat
    property returns a constant and looks exactly like one built on real data. Anything drawing a
    conclusion from how a property changes with temperature has to check this first.

    Every material carries a measured conductivity curve. Only GRCop-42 carries measured yield
    strength, expansion and elongation; for the other nine those are room-temperature values held
    flat. See docs/materialsDatabaseRoadmap.md for what closing that would take.

    '''

    canonical = resolveWallMaterialName(material)
    fallback = canonical is None
    if fallback:
        warnings.warn(
            f'wallMaterialCurves: unrecognized wall material {material!r}; using GRCop-42. '
            f'Known materials: {availableWallMaterials()}.'
        )
        canonical = 'GRCop-42'

    entry = _WALLCURVEDATA[canonical]
    temperatureK = np.asarray(entry['temperatureC'], dtype = float) + units.DEGC_OFFSET
    gridLength = temperatureK.size

    def asArray(value):
        array = np.atleast_1d(np.asarray(value, dtype = float))
        return array if array.size == gridLength else np.full(gridLength, array.flat[0])

    # A list in the table is a measured curve; a scalar is one value held across the grid.
    def isMeasured(name):
        return isinstance(entry[name], (list, tuple))

    return {
        'material':            canonical,
        'temperatureK':        temperatureK,
        'thermalConductivity': asArray(entry['thermalConductivity']),
        'yieldStrength':       asArray(entry['yieldStrength']),
        'cte':                 asArray(entry['cte']),
        'elongation':          asArray(entry['elongation']),
        'density':             float(entry['density']),
        'elasticModulus':      float(entry['elasticModulus']),
        'source':              entry['source'],
        'fallback':            fallback,
        'measured':            {name: isMeasured(name) for name in
                                ('thermalConductivity', 'yieldStrength', 'cte', 'elongation')},
        'provenance':          entry['provenance'],
    }

def sampleWallMaterial(material, temperatureK: float = 293.15) -> dict:

    '''

    Wall-alloy properties interpolated to a single temperature, for display and quick checks.
    Values are clamped to the ends of each property's temperature grid rather than extrapolated.

    Returns a dict: 'material', 'temperatureK', 'thermalConductivity' [W/m-K],
    'yieldStrength' [Pa], 'cte' [1/K], 'elongation' [%], 'density' [kg/m^3],
    'elasticModulus' [Pa], 'source', 'fallback', 'measured'.

    A sampled value whose 'measured' entry is False is the room-temperature value, whatever
    temperature was asked for. It is not a reading off a curve.

    '''

    curves = wallMaterialCurves(material)
    grid = curves['temperatureK']
    clamped = float(np.clip(temperatureK, grid[0], grid[-1]))

    return {
        'material':            curves['material'],
        'temperatureK':        clamped,
        'thermalConductivity': float(np.interp(clamped, grid, curves['thermalConductivity'])),
        'yieldStrength':       float(np.interp(clamped, grid, curves['yieldStrength'])),
        'cte':                 float(np.interp(clamped, grid, curves['cte'])),
        'elongation':          float(np.interp(clamped, grid, curves['elongation'])),
        'density':             curves['density'],
        'elasticModulus':      curves['elasticModulus'],
        'source':              curves['source'],
        'fallback':            curves['fallback'],
        'measured':            curves['measured'],
        'provenance':          curves['provenance'],
    }
