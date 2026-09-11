
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
            # The first two entries, 1.5e-6/K at 25 degC and 9.3e-6/K at 100 degC, are not
            # physical for a copper alloy: they imply 45 per cent less expansion by 100 degC
            # than a constant 17e-6/K would, and no copper alloy expands like an Invar. From
            # 300 degC upward the curve is sensible and agrees with a constant 17e-6/K to
            # within 12 per cent. The low end reads like a fit artefact near the reference
            # temperature, where a mean from 293 K is ill conditioned. Left as the source
            # gives it rather than corrected to a guess.
            'cte':                 ('NASA GRCop-42 thermal expansion report. The 25 and '
                                    '100 degC entries are not physical for a copper alloy '
                                    'and look like a fit artefact where a mean from 293 K '
                                    'is ill conditioned; above 300 degC the curve is sound.',
                                    (25, 900)),
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
#--------------------------------------------------------------------------------------------------------------------------#
# -- Non-metallic and refractory materials -- #
#--------------------------------------------------------------------------------------------------------------------------#

# Everything a nozzle is made of that is not a regeneratively cooled wall: throat inserts, nozzle
# extensions, ablative liners, thermal barrier coatings and the polymers in the feed system.
#
# This is a separate store from _WALLCURVEDATA on purpose. `wallMaterialCurves` is what
# regenThermal and channelSizing read, and nothing in this table can be a cooled wall: carbon
# phenolic is meant to be consumed, graphite cannot be brazed into a jacket, and PTFE is a seal.
# Keeping them apart means a material cannot be selected for a job it cannot do.
#
# ----------------------------------------------------------------------
#                     What grade of data this is
# ----------------------------------------------------------------------
#
# Lower than the wall alloys, and deliberately so. For metals there are critically evaluated
# compilations with stated fit errors: NIST for cryogenic properties, producer bulletins with
# tabulated tensile data. The equivalents here are either access controlled (the DTIC ablative
# thermal property reports), paywalled (MIL-HDBK-17 for composites, CINDAS) or do not exist in
# one place. What is freely available is vendor datasheets giving room-temperature values and
# journal papers characterising one formulation.
#
# So these entries are SELECTION grade, not analysis grade. They answer "will this survive here,
# what does it weigh, and roughly how does it conduct", which is the question these materials are
# usually asked. They do not answer "what is k at 847 K" and they are not design allowables. Each
# property carries a `basis` saying which it is.
#
# The governing property for most of this table is not a curve at all but the maximum use
# temperature, and for the carbon materials that number depends entirely on the atmosphere: 2D
# carbon-carbon is good past 2500 degC in an inert environment and oxidises from about 400 degC
# bare. Both are recorded, because quoting only the first is how a nozzle extension gets designed
# to a number it will never see.

# Property values are keyed by variant so that anisotropy, and the virgin-versus-char split an
# ablative needs, use one mechanism. Isotropic materials use the single key 'isotropic'.

_MATERIALCLASSES = {

    'ATJ Graphite': {
        'class':        'refractory',
        'form':         'fine-grain isomolded graphite',
        'application':  'Throat inserts, nozzle liners, hot-pressing tooling',
        'density':      1760.0,        # [kg/m^3]
        'properties': {
            # The datasheet reports with-grain values only. Isomolded ATJ is near isotropic but
            # not isotropic: across-grain strength runs roughly 10 to 20 per cent lower.
            'thermalConductivity': {'withGrain': 116.0},        # [W/m-K] at room temperature
            'cte':                 {'withGrain': 3.0e-6},       # [1/K], mean to 100 degC
            'tensileStrength':     {'withGrain': 26.0e6},       # [Pa]
            'flexuralStrength':    {'withGrain': 31.0e6},       # [Pa]
            'compressiveStrength': {'withGrain': 66.0e6},       # [Pa]
            'elasticModulus':      {'withGrain': 9.7e9},        # [Pa]
        },
        'maxUseTemperatureC': {'inert': 2800.0, 'oxidising': 400.0},
        'basis': 'producerDatasheet',
        'provenance': {
            'thermalConductivity': ('GrafTech GT-5028 Rev 2 (2009), Grade ATJ, room temperature, '
                                    'with grain. Graphite conductivity falls steeply with '
                                    'temperature, roughly as 1/T above 500 K, so this value is '
                                    'not usable hot.', 'producerDatasheet'),
            'cte':                 ('GrafTech GT-5028 Rev 2, mean to 100 degC, with grain.',
                                    'producerDatasheet'),
            'tensileStrength':     ('GrafTech GT-5028 Rev 2, room temperature, with grain. '
                                    'Graphite gains strength with temperature to about 2500 degC, '
                                    'which is the opposite of every metal in this module.',
                                    'producerDatasheet'),
            'flexuralStrength':    ('GrafTech GT-5028 Rev 2, room temperature, with grain.',
                                    'producerDatasheet'),
            'compressiveStrength': ('GrafTech GT-5028 Rev 2, room temperature, with grain.',
                                    'producerDatasheet'),
            'elasticModulus':      ('GrafTech GT-5028 Rev 2, room temperature, with grain.',
                                    'producerDatasheet'),
            'maxUseTemperatureC':  ('Inert limit is the sublimation-limited working range for '
                                    'bulk graphite. The oxidising limit is where measurable '
                                    'oxidation begins in air, not where the part fails.',
                                    'literatureRepresentative'),
        },
    },

    'Carbon-Carbon (2D)': {
        'class':        'composite',
        'form':         '2D laminate, CVI or PIP densified',
        'application':  'Nozzle extensions, throat inserts, hot structure',
        'density':      1825.0,        # [kg/m^3], midpoint of 1750 to 1900
        'properties': {
            'cte':                 {'inPlane': 1.25e-6},        # [1/K], 0.5 to 2.0e-6 reported
            'tensileStrength':     {'inPlane': 155.0e6},        # [Pa], 150 to 160 MPa
            'flexuralStrength':    {'inPlane': 170.0e6},        # [Pa]
            'compressiveStrength': {'inPlane': 200.0e6},        # [Pa], 150 to 250 MPa
            'elasticModulus':      {'inPlane': 75.0e9},         # [Pa]
            'fractureToughness':   {'inPlane': 7.5e6},          # [Pa m^0.5], 5 to 10
        },
        # Bare C/C oxidises from about 400 degC. The 1750 degC figure is for coated material and
        # is the number that gets quoted; both are here so neither is mistaken for the other.
        'maxUseTemperatureC': {'inert': 2500.0, 'oxidising': 400.0, 'oxidisingCoated': 1750.0},
        'basis': 'literatureReview',
        'provenance': {
            'cte':                 ('Multimatrix Composite Materials for Rocket Nozzle '
                                    'Manufacturing: A Comparative Review, PMC12610372. Reported '
                                    'as 0.5 to 2.0e-6/K; the midpoint is stored.',
                                    'literatureReview'),
            'tensileStrength':     ('PMC12610372, PIP densified, inert atmosphere, 150 to 160 MPa.',
                                    'literatureReview'),
            'flexuralStrength':    ('PMC12610372, air, transient loading.', 'literatureReview'),
            'compressiveStrength': ('PMC12610372, CVI densified, air, 150 to 250 MPa.',
                                    'literatureReview'),
            'elasticModulus':      ('PMC12610372, air, steady loading.', 'literatureReview'),
            'fractureToughness':   ('PMC12610372, CVI+PIP, inert, 5 to 10 MPa m^0.5.',
                                    'literatureReview'),
            'maxUseTemperatureC':  ('PMC12610372 gives 1750 degC in air and above 2500 degC '
                                    'inert. The 1750 figure requires an oxidation-protection '
                                    'coating; bare 2D C/C oxidises measurably from about 400 '
                                    'degC, which is the limit stored under oxidising.',
                                    'literatureReview'),
        },
        'notes': ('Through-thickness tensile and shear strength of a 2D layup are far below the '
                  'in-plane values, which is what governs a bonded or bolted joint. 3D '
                  'reinforcement recovers 30 to 40 per cent of it. No through-thickness values '
                  'are stored because none were found tabulated.'),
    },

    'C/SiC': {
        'class':        'composite',
        'form':         'carbon fibre, silicon carbide matrix, CVI or RS',
        'application':  'Nozzle extensions where bare carbon-carbon would oxidise',
        'density':      2050.0,        # [kg/m^3], 2.0 to 2.1
        'properties': {
            'tensileStrength':     {'inPlane': 230.0e6},        # [Pa]
            'flexuralStrength':    {'inPlane': 295.0e6},        # [Pa], 290 to 300
            'compressiveStrength': {'inPlane': 390.0e6},        # [Pa]
            'elasticModulus':      {'inPlane': 78.2e9},         # [Pa]
            'fractureToughness':   {'inPlane': 5.45e6},         # [Pa m^0.5]
        },
        'maxUseTemperatureC': {'inert': 1700.0, 'oxidising': 1400.0},
        'basis': 'literatureReview',
        'provenance': {
            'tensileStrength':     ('PMC12610372, reaction sintered, air, steady.',
                                    'literatureReview'),
            'flexuralStrength':    ('PMC12610372, PIP, air, transient, 290 to 300 MPa.',
                                    'literatureReview'),
            'compressiveStrength': ('PMC12610372, CVI, air, steady.', 'literatureReview'),
            'elasticModulus':      ('PMC12610372, reaction sintered, air, steady.',
                                    'literatureReview'),
            'fractureToughness':   ('PMC12610372, CVI+PIP, inert.', 'literatureReview'),
            'maxUseTemperatureC':  ('PMC12610372 gives 1300 to 1500 degC in an oxidising '
                                    'atmosphere. Retained strength at 1500 to 1700 degC is about '
                                    '88 MPa, which is what sets the inert figure.',
                                    'literatureReview'),
        },
        'notes': ('The reason to accept C/SiC over C/C is that it holds up in air without a '
                  'separate oxidation coating, at the cost of density and toughness.'),
    },

    'SiC/SiC': {
        'class':        'composite',
        'form':         'silicon carbide fibre and matrix, 2D woven or 3D braided',
        'application':  'Hot structure, turbine and nozzle components in oxidising service',
        'density':      2700.0,        # [kg/m^3], 2.4 to 3.0
        'properties': {
            'tensileStrength':     {'inPlane': 287.0e6},        # [Pa]
            'flexuralStrength':    {'inPlane': 300.0e6},        # [Pa]
            'compressiveStrength': {'inPlane': 232.0e6},        # [Pa]
            'elasticModulus':      {'inPlane': 255.0e9},        # [Pa], 250 to 260
            'fractureToughness':   {'inPlane': 15.0e6},         # [Pa m^0.5]
        },
        'maxUseTemperatureC': {'inert': 1700.0, 'oxidising': 1600.0},
        'basis': 'literatureReview',
        'provenance': {
            'tensileStrength':     ('PMC12610372, 2D plain weave with BN interphase, air.',
                                    'literatureReview'),
            'flexuralStrength':    ('PMC12610372, 3D braided with PyC interphase, inert.',
                                    'literatureReview'),
            'compressiveStrength': ('PMC12610372, LSI, steam or moist air.', 'literatureReview'),
            'elasticModulus':      ('PMC12610372, 2D woven with BN interphase, air, 250 to 260 '
                                    'GPa.', 'literatureReview'),
            'fractureToughness':   ('PMC12610372, 3D braided with BN interphase, air.',
                                    'literatureReview'),
            'maxUseTemperatureC':  ('PMC12610372, 1600 to 1700 degC, sustained above 1400 to '
                                    '1600 degC.', 'literatureReview'),
        },
        'notes': ('Stiffest of the ceramic composites here by a factor of three, and the only one '
                  'whose strength is quoted in steam, which is the environment a hydrogen-fuelled '
                  'exhaust actually presents.'),
    },

    'Carbon Phenolic': {
        'class':        'ablative',
        'form':         'woven carbon fabric in phenolic resin, tape wrapped or moulded',
        'application':  'Solid motor throat and exit cone liners, uncooled chambers',
        'density':      1450.0,        # [kg/m^3], typical virgin MX-4926 class
        'properties': {
            'tensileStrength':     {'virgin': 60.0e6},          # [Pa]
            'flexuralStrength':    {'virgin': 90.0e6},          # [Pa]
            'compressiveStrength': {'virgin': 150.0e6},         # [Pa]
            'elasticModulus':      {'virgin': 20.0e9},          # [Pa]
            'ablationRate':        {'plasmaTorch': 1.25e-4},    # [m/s], 0.05 to 0.20 mm/s
        },
        'maxUseTemperatureC': {'oxidising': 1000.0, 'charInert': 2500.0},
        'basis': 'literatureReview',
        'provenance': {
            'tensileStrength':     ('PMC12610372, compression moulded, air.', 'literatureReview'),
            'flexuralStrength':    ('PMC12610372, filament wound, air.', 'literatureReview'),
            'compressiveStrength': ('PMC12610372, hand lay-up, air.', 'literatureReview'),
            'elasticModulus':      ('PMC12610372, transient loading.', 'literatureReview'),
            'ablationRate':        ('PMC12610372, plasma torch testing, 0.05 to 0.20 mm/s. A '
                                    'torch number is not a motor number: recession depends on '
                                    'enthalpy, pressure and shear at the wall, none of which the '
                                    'torch reproduces.', 'literatureReview'),
            'density':             ('Virgin density typical of the MX-4926 class. Char density '
                                    'is roughly half, and the store carries no char value.',
                                    'literatureRepresentative'),
            'maxUseTemperatureC':  ('PMC12610372: above 1000 degC a carbon layer forms, and the '
                                    'char protects to 2000 to 3000 degC in an inert environment. '
                                    'The lower figure is stored for the char limit as the '
                                    'conservative end of that range.', 'literatureReview'),
        },
        'notes': ('The material NOVA cannot currently model. An ablative needs virgin and char '
                  'conductivity as separate curves, a pyrolysis gas mass flux, and a recession '
                  'rate against local heat flux; this entry has none of those. It is here so the '
                  'material can be compared on density and strength, not so it can be analysed. '
                  'The DTIC reports that carry virgin and char conductivity to 5000 degF are '
                  'access controlled.'),
    },

    'Silica Phenolic': {
        'class':        'ablative',
        'form':         'silica fabric in phenolic resin',
        'application':  'Exit cones and lower-flux ablative liners',
        'density':      1700.0,        # [kg/m^3]
        'properties': {
            'thermalConductivity': {'virgin': 0.6},             # [W/m-K], room temperature
        },
        'maxUseTemperatureC': {'oxidising': 1650.0},
        'basis': 'literatureRepresentative',
        'provenance': {
            'thermalConductivity': ('Representative room-temperature value for silica-phenolic '
                                    'ablators. Not traced to a primary source.',
                                    'literatureRepresentative'),
            'density':             ('Representative virgin density.', 'literatureRepresentative'),
            'maxUseTemperatureC':  ('Set by silica melting and the onset of a molten surface '
                                    'layer rather than by the resin.', 'literatureRepresentative'),
        },
        'notes': ('Lower conductivity and lower cost than carbon phenolic, and lower flux '
                  'capability. Included for comparison only; every value is representative rather '
                  'than sourced, which is why the basis says so.'),
    },

    '7YSZ': {
        'class':        'ceramic',
        'form':         '7 to 8 wt% yttria stabilised zirconia, APS or EB-PVD',
        'application':  'Thermal barrier coating over a metallic wall',
        'density':      6000.0,        # [kg/m^3], bulk; a sprayed coating is 10 to 20 % porous
        'properties': {
            # Conductivity depends on porosity more than on chemistry. A dense sintered body is
            # near 2.3 W/m-K; a sprayed coating with its porosity and splat boundaries is nearer
            # 1.0. Both ends are recorded rather than a single misleading midpoint.
            'thermalConductivity': {'denseSintered': 2.3, 'sprayedCoating': 1.0},   # [W/m-K]
            'cte':                 {'isotropic': 11.0e-6},      # [1/K]
        },
        'maxUseTemperatureC': {'oxidising': 1200.0},
        'basis': 'literatureRepresentative',
        'provenance': {
            'thermalConductivity': ('Roughly 2.3 W/m-K for dense 7 wt% YSZ, falling to about 1.0 '
                                    'for a sprayed coating whose porosity and splat boundaries '
                                    'do most of the insulating. Porosity, not composition, is '
                                    'the variable.', 'literatureRepresentative'),
            'cte':                 ('About 11e-6/K for 8YSZ. The number that matters is not this '
                                    'but its mismatch against the substrate: against GRCop-42 at '
                                    '17e-6/K the difference drives the strain that spalls the '
                                    'coating.', 'literatureRepresentative'),
            'maxUseTemperatureC':  ('Phase stability and sintering of the porous structure limit '
                                    'sustained use; the tetragonal prime phase destabilises above '
                                    'roughly 1200 degC.', 'literatureRepresentative'),
        },
        'notes': ('A coating is not a material in the sense the rest of this table means. What '
                  'governs its life is adhesion, the thermally grown oxide under it and the '
                  'expansion mismatch against what it is sprayed onto, none of which is a bulk '
                  'property.'),
    },

    'PTFE': {
        'class':        'polymer',
        'form':         'virgin unfilled polytetrafluoroethylene',
        'application':  'Cryogenic seals, valve seats, bearing surfaces',
        'density':      2175.0,        # [kg/m^3]
        'properties': {
            'thermalConductivity': {'isotropic': 0.25},         # [W/m-K] at room temperature
            'cte':                 {'isotropic': 135.0e-6},     # [1/K], near room temperature
        },
        'maxUseTemperatureC': {'continuous': 260.0},
        'minUseTemperatureC': -260.0,
        'basis': 'literatureRepresentative',
        'provenance': {
            'thermalConductivity': ('Representative room-temperature value for unfilled PTFE.',
                                    'literatureRepresentative'),
            'cte':                 ('PTFE expansion is an order of magnitude above copper and is '
                                    'strongly non-linear: two solid-solid transitions near room '
                                    'temperature take the instantaneous coefficient above '
                                    '500e-6/K. A single number is a poor description and is '
                                    'stored only for rough comparison.',
                                    'literatureRepresentative'),
            'maxUseTemperatureC':  ('Thermally stable to about 260 degC.',
                                    'literatureRepresentative'),
        },
        'notes': ('Cold flow under sustained load is what usually governs a PTFE seal, not '
                  'strength, and no creep data is stored here.'),
    },

    'PCTFE': {
        'class':        'polymer',
        'form':         'polychlorotrifluoroethylene, Kel-F or Neoflon',
        'application':  'Cryogenic valve seats and seals, liquid oxygen service',
        'density':      2130.0,        # [kg/m^3]
        'properties': {
            # One of the few polymers here with a measured temperature dependence.
            'thermalConductivity': {'isotropic': 0.25, 'atLiquidNitrogen': 0.12},   # [W/m-K]
        },
        'maxUseTemperatureC': {'continuous': 193.0},
        'minUseTemperatureC': -240.0,
        'basis': 'producerDatasheet',
        'provenance': {
            'thermalConductivity': ('0.24 to 0.26 W/m-K at 23 degC falling to 0.10 to 0.14 at '
                                    '-196 degC, from fluoropolymer supplier datasheets. '
                                    'Midpoints stored.', 'producerDatasheet'),
            'maxUseTemperatureC':  ('Useful range quoted as -240 to 193 degC.',
                                    'producerDatasheet'),
        },
        'notes': ('The lowest expansion and least cold flow of the unfilled fluoropolymers, which '
                  'is why it is the usual choice for a cryogenic seat where PTFE would extrude.'),
    },

    'PEEK': {
        'class':        'polymer',
        'form':         'unfilled polyetheretherketone',
        'application':  'Structural polymer parts, bearings, cryogenic sealing',
        'density':      1320.0,        # [kg/m^3]
        'properties': {
            'thermalConductivity': {'isotropic': 0.25},         # [W/m-K]
        },
        'maxUseTemperatureC': {'continuous': 249.0},
        'glassTransitionC': 143.0,
        'basis': 'literatureRepresentative',
        'provenance': {
            'thermalConductivity': ('About 0.25 W/m-K at room temperature for unfilled PEEK. '
                                    'Filled and carbon-reinforced grades run several times '
                                    'higher and are a different material for this purpose.',
                                    'literatureRepresentative'),
            'maxUseTemperatureC':  ('Maximum continuous working temperature about 249 degC, with '
                                    'properties retained to roughly 299 degC under pressure.',
                                    'literatureRepresentative'),
            'glassTransitionC':    ('The highest glass transition of the common sealing polymers, '
                                    'which is what recommends it for cryogenic hydrogen service.',
                                    'literatureRepresentative'),
        },
        'notes': ('Structural where PTFE and PCTFE are sealing materials.'),
    },

    'C103': {
        'class':        'refractoryMetal',
        'form':         'Nb-10Hf-1Ti, wrought or laser powder bed fusion',
        'application':  'Radiatively cooled nozzle extensions, reaction control thrusters',
        'density':      8850.0,        # [kg/m^3]
        'properties': {
            'yieldStrength':   {'wrought': 276.0e6, 'lpbfStressRelieved': 411.0e6},   # [Pa]
            'tensileStrength': {'wrought': 386.0e6, 'lpbfStressRelieved': 560.0e6},   # [Pa]
            'elongation':      {'wrought': 20.0, 'lpbfStressRelieved': 16.7},         # [%]
            # A radiation-cooled wall sits where its own emissivity puts it: the equilibrium
            # temperature goes as the inverse fourth root, so a factor of four here is a factor
            # of 1.41 in wall temperature. Only the degraded value is sourced, and it is the
            # conservative one, because lower emissivity means a hotter wall.
            'emissivity':      {'r512eCoatedOxidised': 0.7},                          # [-]
        },
        'maxUseTemperatureC': {'inert': 1400.0, 'oxidising': 400.0},
        'basis': 'literatureReview',
        'provenance': {
            'yieldStrength':   ('Wrought room-temperature values are the commonly quoted '
                                'specification figures. The LPBF numbers are Mireles, Rodriguez, '
                                'Gao and Philips, Additive Manufacture of Refractory Alloy C103 '
                                'for Propulsion Applications, NASA MSFC, AIAA 2020, Table 3, '
                                'as-built Z direction. NOTE: that table lists yield above '
                                'ultimate, which is impossible, so its two columns are '
                                'transposed. The values here take the smaller as yield.',
                                'literatureReview'),
            'tensileStrength': ('Same source and same transposition caveat as the yield strength.',
                                'literatureReview'),
            'elongation':      ('NASA MSFC AIAA 2020 Table 3, as-built Z direction, 16.67 +/- 0.2 '
                                'per cent; wrought specification minimum is 20 per cent.',
                                'literatureReview'),
            'maxUseTemperatureC': ('C103 is used to roughly 1400 degC in vacuum or inert '
                                   'atmosphere. It oxidises catastrophically in air from about '
                                   '400 degC and is always used with a silicide coating, '
                                   'typically R512E, in any oxidising service.',
                                   'literatureReview'),
            'emissivity':      ('Levine and Merutka, Performance of Coated Columbium and Tantalum '
                                'Alloys in Plasma Arc Reentry Simulation Tests, NASA Lewis '
                                'Research Center and US Army Air Mobility R&D Laboratory, NTRS '
                                '19740015000. Its summary reports large emittance losses, '
                                'generally to below 0.7, from surface refractory metal pentoxides '
                                'forming on R512E coated columbium. Three caveats, and they '
                                'matter. The substrates tested were FS-85, Cb-752 and C-129Y '
                                'rather than C103, so the value transfers on the coating being '
                                'the emitting surface. The environment was a plasma arc at 4.9 '
                                'torr of air for fifty half-hour cycles near 1390 degC, which '
                                'oxidises far harder than a vacuum nozzle extension, so this is '
                                'how far the emittance can fall rather than where it sits in '
                                'service. And no beginning-of-life value is recorded here because '
                                'none was found: an extension sized on 0.7 is sized on the hot '
                                'case, which is the right direction to be wrong in.',
                                'literatureReview'),
        },
        'notes': ('The classic radiatively cooled extension material. Its temperature-dependent '
                  'strength is published only as a figure in the sources found, so no curve is '
                  'stored; strength at 1093 degC is roughly 172 MPa ultimate, and elongation '
                  'still exceeds 50 per cent at 1371 degC.'),
    },
}

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

def availableMaterialClasses() -> list:

    '''

    The material classes the non-metallic store carries.

    Returns:
    --------
    list
        Sorted class names: 'ablative', 'ceramic', 'composite', 'polymer', 'refractory',
        'refractoryMetal'.

    '''

    return sorted({entry['class'] for entry in _MATERIALCLASSES.values()})

def availableMaterials(materialClass: str = None) -> list:

    '''

    Non-metallic and refractory materials, optionally filtered to one class.

    These are not wall alloys and cannot be used as one. `wallMaterialCurves` reads a separate
    store, so nothing here can be selected as a regeneratively cooled wall.

    Parameters:
    -----------
    materialClass : str | None
        One of `availableMaterialClasses()`, or None for everything.

    Returns:
    --------
    list
        Sorted material names.

    Raises:
    -------
    KeyError
        If the class is not one this store carries.

    '''

    if materialClass is None:
        return sorted(_MATERIALCLASSES)

    if materialClass not in availableMaterialClasses():
        raise KeyError('Unknown material class {!r}. Known classes: {}.'.format(
            materialClass, availableMaterialClasses()))

    return sorted(name for name, entry in _MATERIALCLASSES.items()
                  if entry['class'] == materialClass)

def materialProfile(material: str) -> dict:

    '''

    Everything the non-metallic store holds for one material.

    Parameters:
    -----------
    material : str
        A name from `availableMaterials()`, matched case insensitively.

    Returns:
    --------
    dict
        The stored entry, with keys 'class', 'form', 'application', 'density', 'properties',
        'maxUseTemperatureC', 'basis', 'provenance' and optionally 'notes'.

    Raises:
    -------
    KeyError
        If the material is not in the store. Unlike the wall alloys there is no fallback: there
        is no sensible default throat insert, and quietly substituting one would be worse than
        refusing.

    '''

    for name, entry in _MATERIALCLASSES.items():
        if name.lower() == material.strip().lower():
            return entry

    raise KeyError('Unknown material {!r}. Known materials: {}.'.format(
        material, availableMaterials()))

def materialProperty(material: str, propertyName: str, variant: str = None):

    '''

    One property of a non-metallic material.

    Properties are keyed by variant so that anisotropy and the virgin-versus-char split of an
    ablative use one mechanism: 'withGrain' and 'acrossGrain' for graphite, 'inPlane' and
    'throughThickness' for a laminate, 'virgin' and 'char' for an ablative, 'isotropic' where
    there is only one value.

    Parameters:
    -----------
    material : str
        A name from `availableMaterials()`.
    propertyName : str
        A key of the material's 'properties' entry.
    variant : str | None
        Which variant to read. None returns the whole variant mapping.

    Returns:
    --------
    float | dict
        The value, or the mapping of every variant when `variant` is None.

    Raises:
    -------
    KeyError
        If the material, property or variant is absent. A property missing from an entry means
        no source was found for it, not that it is zero.

    '''

    entry = materialProfile(material)
    properties = entry['properties']

    if propertyName not in properties:
        raise KeyError(
            '{!r} carries no {!r}. It has: {}. A property absent from this store means no '
            'source was found for it.'.format(material, propertyName, sorted(properties)))

    if variant is None:
        return properties[propertyName]

    if variant not in properties[propertyName]:
        raise KeyError('{!r} {!r} has no variant {!r}. It has: {}.'.format(
            material, propertyName, variant, sorted(properties[propertyName])))

    return properties[propertyName][variant]

def surfaceEmissivity(material: str, condition: str = None):

    """

    Total hemispherical emissivity of a material's surface, where one is carried.

    Emissivity is a property of a surface rather than of an alloy. Oxide state and roughness set
    it, a polished and an oxidised sample of the same metal differ by an order of magnitude, and
    it moves over a firing as the surface changes. So it is keyed on a surface condition, and the
    store carries a value only where one could be traced to a source describing that condition.

    Most materials here carry none, and that is the honest state rather than an omission. There
    is no published emissivity for the copper wall alloys at the surface finish a printed
    regenerative chamber actually has. A radiation term that needs one takes it from the
    configuration, where whoever supplies it owns it.

    Parameters:
    -----------
    material : str
        A name from `availableMaterials()` or `availableWallMaterials()`.
    condition : str | None
        Which surface condition to read. None returns the whole mapping.

    Returns:
    --------
    float | dict
        Emissivity [-], or the mapping of every stored condition when `condition` is None.

    Raises:
    -------
    KeyError
        If the material carries no emissivity, or carries none for that surface condition. A
        guessed emissivity propagates to the fourth root of wall temperature, so the store
        refuses rather than substitutes.

    """

    carried = sorted(name for name, entry in _MATERIALCLASSES.items()
                     if 'emissivity' in entry['properties'])

    known = resolveWallMaterialName(material) is not None             or any(name.lower() == material.strip().lower() for name in _MATERIALCLASSES)
    if not known:
        raise KeyError('Unknown material {!r}. Wall alloys: {}. Everything else: {}.'.format(
            material, availableWallMaterials(), availableMaterials()))

    try:
        stored = materialProperty(material, 'emissivity')
    except KeyError:
        raise KeyError(
            'No emissivity is carried for {!r}. Emissivity is a surface property, not an alloy '
            'property, and the store holds one only where a source describes the surface. '
            'Supply one through the configuration instead. Carried for: {}.'.format(
                material, carried))

    if condition is None:
        return stored

    if condition not in stored:
        raise KeyError('{!r} carries no emissivity for the surface condition {!r}. It has: '
                       '{}.'.format(material, condition, sorted(stored)))

    return stored[condition]

def maxUseTemperature(material: str, atmosphere: str = 'oxidising') -> float:

    '''

    The temperature limit of a non-metallic material in a given atmosphere, in degrees Celsius.

    For the carbon materials this is the governing selection property and it depends entirely on
    the atmosphere. Bare 2D carbon-carbon is good past 2500 degC inert and oxidises from about
    400 degC in air, a factor of six. Quoting only the inert figure is how a nozzle extension
    gets designed to a number it will never see.

    Parameters:
    -----------
    material : str
        A name from `availableMaterials()`.
    atmosphere : str
        'inert', 'oxidising', 'oxidisingCoated', 'charInert' or 'continuous', depending on what
        the material's entry defines.

    Returns:
    --------
    float
        Temperature limit [degC].

    Raises:
    -------
    KeyError
        If the material defines no limit for that atmosphere.

    '''

    limits = materialProfile(material)['maxUseTemperatureC']

    if atmosphere not in limits:
        raise KeyError('{!r} defines no limit in a {!r} atmosphere. It defines: {}.'.format(
            material, atmosphere, sorted(limits)))

    return limits[atmosphere]

def materialPropertyProvenance(material: str, propertyName: str) -> tuple:

    '''

    Where a non-metallic property came from, and what grade of source it is.

    Parameters:
    -----------
    material : str
        A name from `availableMaterials()`.
    propertyName : str
        A property or 'density' or 'maxUseTemperatureC'.

    Returns:
    --------
    tuple
        (source, basis), where basis is 'producerDatasheet', 'literatureReview' or
        'literatureRepresentative' in descending order of how much weight it carries.

    '''

    provenance = materialProfile(material)['provenance']

    if propertyName not in provenance:
        raise KeyError('{!r} records no provenance for {!r}. It records: {}.'.format(
            material, propertyName, sorted(provenance)))

    return provenance[propertyName]

#--------------------------------------------------------------------------------------------------------------------------#
# -- Ablative Material Response Data -- #
#--------------------------------------------------------------------------------------------------------------------------#

# A charring ablator needs more than the selection-grade numbers in _MATERIALCLASSES. Running a
# material response demands, at minimum: virgin and char conductivity, specific heat and enthalpy
# as curves; the Arrhenius kinetics of every decomposing component; and a surface thermochemistry
# closure that returns the char removal rate and the wall enthalpy. This store carries the
# materials that have all of it.
#
# It holds one material. TACOT is a theoretical composite published by the Ablation Workshop so
# that codes can be compared on identical data, and it is the only charring ablator whose complete
# response property set is in the open literature. Every real nozzle liner material -- MX-4926 and
# the rest of the tape-wrapped carbon phenolic family -- has its property set in reports that are
# access controlled or behind a licence.
#
# TACOT is NOT a stand-in for a nozzle liner. At 280 kg/m^3 virgin it is a low-density entry
# heatshield material, roughly a fifth the density of the tape-wrapped carbon phenolic used in a
# solid motor throat, and it chars and conducts accordingly. It is here so the solver can be
# verified against published results, and so that a user supplying a real property set has a
# worked example of the shape that set has to take.

_ABLATIVERESPONSEDATA = {

    'TACOT v3.0': {
        'class':         'ablative',
        'form':          'theoretical low-density carbon fibre preform in a phenolic matrix',
        'application':   'Open benchmark for ablation code verification and inter-code comparison',
        'virginDensity': 280.0,           # [kg/m^3]
        'charDensity':   220.0,           # [kg/m^3]

        # Shared temperature grid for every curve below. The values are the source's Rankine grid
        # converted to kelvin, which is why they are not round numbers.
        'temperature': [
            255.5555556, 298, 444.4444444, 555.5555556, 644.4444444, 833.3333333, 1111.111111,
            1388.888889, 1666.666667, 1944.444444, 2222.222222, 2777.777778, 3333.333333],

        # Enthalpy is absolute: it carries the heat of formation, so the heat of pyrolysis falls
        # out of the virgin-to-char enthalpy difference rather than being supplied separately.
        # The datum is char at 298 K.
        'virgin': {
            'specificHeat': [                                                    # [J/kg-K]
                879.228, 983.898, 1297.908, 1465.38, 1570.05, 1716.588, 1863.126, 1934.3016,
                1980.3564, 1988.73, 2001.2904, 2009.664, 2009.664],
            'thermalConductivity': [                                             # [W/m-K]
                0.3975151382, 0.4024996541, 0.4162070726, 0.452967877, 0.4697906179, 0.4859902944,
                0.5233741632, 0.5601349675, 0.6978322176, 0.872290272, 1.109054774, 1.750811189,
                2.778867581],
            'enthalpy': [                                                        # [J/kg]
                -896682.5311, -857142.8571, -690063.9511, -536547.9511, -401639.9511, -91235.25114,
                405947.2489, 933367.7489, 1477070.249, 2028332.249, 2582501.749, 3696655.749,
                4813135.749],
            'emissivity': 0.8,
        },

        'char': {
            'specificHeat': [                                                    # [J/kg-K]
                732.69, 782.9316, 1092.7548, 1318.842, 1431.8856, 1674.72, 1842.192, 1967.796,
                2051.532, 2093.4, 2110.1472, 2135.268, 2152.0152],
            'thermalConductivity': [                                             # [W/m-K]
                0.3975151382, 0.4024996541, 0.4162070726, 0.452967877, 0.4697906179, 0.4859902944,
                0.5233741632, 0.5601349675, 0.6049956101, 0.7289854416, 0.9221354304, 1.457970883,
                2.317799866],
            'enthalpy': [                                                        # [J/kg]
                -32164.8584, 0, 137341.9264, 271319.5264, 393574.0864, 686975.7264, 1175435.726,
                1704600.726, 2262840.726, 2838525.726, 3422351.726, 4601633.726, 5792545.726],
            'emissivity': 0.9,
        },

        # Goldstein's two-phase resin decomposition, in the form CMA and FIAT take it:
        #
        #     d(rho_i)/dt = -A_i rho_i_v ((rho_i - rho_i_c) / rho_i_v)^psi_i exp(-E_i / (R T))
        #
        # Below the onset temperature the rate is zero. The bulk density follows from the
        # component densities through the mixing rule
        #
        #     rho = (1 - porosity) [gamma (rho_A + rho_B) + (1 - gamma) rho_C]
        #
        # which returns 280 kg/m^3 for the virgin state and 220 for the char. Component C is the
        # carbon reinforcement and does not decompose, which is why its rate constant is zero.
        'pyrolysis': {
            'resinVolumeFraction': 0.5,
            'porosity':            0.8,
            'components': (
                {'name': 'A', 'virginDensity':  300.0, 'charDensity':    0.0,
                 'preExponentialFactor': 1.2e4,  'activationTemperature':  8555.555556,
                 'reactionOrder': 3.0, 'onsetTemperature': 333.3333333},
                {'name': 'B', 'virginDensity':  900.0, 'charDensity':  600.0,
                 'preExponentialFactor': 4.48e9, 'activationTemperature': 20444.44444,
                 'reactionOrder': 3.0, 'onsetTemperature': 555.5555556},
                {'name': 'C', 'virginDensity': 1600.0, 'charDensity': 1600.0,
                 'preExponentialFactor': 0.0,    'activationTemperature': 0.0,
                 'reactionOrder': 0.0, 'onsetTemperature': 5555.555556},
            ),
        },

        # Elemental composition of the pyrolysis gas, mole fractions. This is what a surface
        # thermochemistry closure needs; the molecular composition is a separate table.
        'pyrolysisGasElements': {'C': 0.206, 'H': 0.679, 'O': 0.115},

        # Char is pure carbon, so the diffusion-limited closure applies to it directly.
        'charElements': {'C': 1.0},

        # Names of the packaged tables that go with this material. The first is surface
        # thermochemistry, for air rather than exhaust: see the note. The second is the
        # equilibrium enthalpy of the pyrolysis gas, which is what fixes the heat of
        # pyrolysis, since the solid enthalpy curves alone do not.
        'surfaceThermochemistry': 'tacotBPrimeAir',
        'pyrolysisGasProperties': 'tacotPyrolysisGas',

        'basis': 'openBenchmark',

        'provenance': {
            'virgin':      ('TACOT v3.0 spreadsheet, Thermal Properties sheet, SI columns. '
                            'Distributed with the Ablation Workshop test-case series; the sheet '
                            'names its main source as Milos and Chen, Performance of a '
                            'Low-Density Ablative Heat Shield Material, Journal of Spacecraft and '
                            'Rockets 45(4), 2008.', 'openBenchmark'),
            'char':        ('TACOT v3.0 spreadsheet, Thermal Properties sheet, SI columns.',
                            'openBenchmark'),
            'virginDensity': ('TACOT v3.0, Pyrolysis model sheet: 0.1 fibre and 0.1 matrix volume '
                              'fraction at 1600 and 1200 kg/m^3 intrinsic gives 280 kg/m^3.',
                              'openBenchmark'),
            'charDensity':   ('TACOT v3.0, Pyrolysis model sheet: the matrix loses half its mass '
                              'during pyrolysis, giving 220 kg/m^3.', 'openBenchmark'),
            'pyrolysis':   ('TACOT v3.0, Pyrolysis model sheet, SI table. Kinetics after '
                            'Goldstein 1965: two decomposing resin phases plus a non-decomposing '
                            'carbon reinforcement.', 'openBenchmark'),
            'pyrolysisGasElements': ('TACOT v3.0, Pyrolysis model sheet, quoting Sykes, '
                                     'Decomposition Characteristics of a Char-Forming Phenolic '
                                     'Polymer Used for Ablative Composites, NASA TN D-3810, 1967.',
                                     'openBenchmark'),
            'charElements': ('The reinforcement is carbon fibre and the residue of the phenolic '
                             'is carbon, so the ablating surface is elemental carbon.',
                             'openBenchmark'),
            'surfaceThermochemistry': ('TACOT v3.0 B-prime sheet, generated with TARGET on the '
                                       'CEA database for air at four pressures spanning 0.001 to '
                                       '1 atm, 25 species, equal diffusion coefficients and '
                                       'equilibrium at the wall.', 'openBenchmark'),
            'pyrolysisGasProperties': ('TACOT v3.0, Pyrolysis model sheet: equilibrium '
                                       'properties of the pyrolysis gas at four pressures '
                                       'spanning 1e-5 to 1 atm, generated with TARGET on the '
                                       'CEA database, condensed species excluded. The datum '
                                       'is the same as the solid curves, which is what lets '
                                       'the heat of pyrolysis fall out of the enthalpy '
                                       'difference instead of being supplied.',
                                       'openBenchmark'),
        },

        'notes': ('A theoretical material, not a procurable one. It exists so that ablation codes '
                  'can be compared on identical inputs, and its property set is the only complete '
                  'one in the open literature. Two limits matter before it is used for anything '
                  'else. It is a low-density entry heatshield material at 280 kg/m^3 virgin, not '
                  'a tape-wrapped nozzle liner at 1450. And its B-prime table is for air and '
                  'stops at 1 atm, so it closes an arc-jet or entry problem and cannot close a '
                  'rocket nozzle, where the edge gas is reducing combustion products at tens of '
                  'atmospheres.'),
    },

}

def availableAblativeMaterials() -> list:

    '''

    Materials whose full charring-ablator response property set is carried.

    These are not the same as the ablatives in `availableMaterials('ablative')`. That list is
    selection grade: density, strength, a use temperature. This one is the much shorter list of
    materials that `NOVA.ablative` can actually run.

    Returns:
    --------
    list
        Sorted material names.

    '''

    return sorted(_ABLATIVERESPONSEDATA)

def ablativeResponseData(material: str) -> dict:

    '''

    The complete response property set for one charring ablator.

    Parameters:
    -----------
    material : str
        A name from `availableAblativeMaterials()`, matched case insensitively.

    Returns:
    --------
    dict
        The stored entry. Curves are plain lists on a shared temperature grid; the module source
        documents the key layout.

    Raises:
    -------
    KeyError
        If the material carries no response data. There is no fallback and no substitution: a
        response run on another material's kinetics is worse than no run.

    '''

    for name, entry in _ABLATIVERESPONSEDATA.items():
        if name.lower() == material.strip().lower():
            return entry

    raise KeyError(
        'No ablative response data for {!r}. Carried: {}. Selection-grade ablatives without a '
        'response property set are listed by availableMaterials with the ablative class.'.format(
            material, availableAblativeMaterials()))

def ablativeResponseProvenance(material: str, propertyName: str) -> tuple:

    '''

    Where one piece of a charring ablator's response data came from.

    Parameters:
    -----------
    material : str
        A name from `availableAblativeMaterials()`.
    propertyName : str
        A key of the material's 'provenance' entry.

    Returns:
    --------
    tuple
        (source, basis). A basis of 'openBenchmark' means a published inter-code comparison
        dataset: the numbers are traceable and fixed, but they describe a theoretical material.

    Raises:
    -------
    KeyError
        If no provenance is recorded under that name.

    '''

    provenance = ablativeResponseData(material)['provenance']

    if propertyName not in provenance:
        raise KeyError('{!r} records no response provenance for {!r}. It records: {}.'.format(
            material, propertyName, sorted(provenance)))

    return provenance[propertyName]
