
# -- Units and Physical Constants -- #

'''

Unit conversion constants and the US Standard Atmosphere 1976 model.

Everything internal to NOVA is mass-base SI. These constants exist so that imperial values
appearing in vendor catalogs, MIL specs and ASME tables can be converted at the boundary instead
of being carried through the calculations.

Two different standard reference states are in circulation and mixing them is a classic sizing
error, so both are carried explicitly rather than either being assumed.

Local copy of orbitalRockets/common/units.py, forked here so NOVA carries no external dependency.
Diverge freely; the source is no longer maintained.

Author: Sean Bowman
Date:   08/06/2026

'''

import numpy as np

#--------------------------------------------------------------------------------------------------------------------------#
# -- Physical Constants and Unit Conversions -- #
#--------------------------------------------------------------------------------------------------------------------------#


# Everything internal to this library is mass-base SI. These constants exist so that imperial
# values appearing in vendor catalogs, MIL specs and ASME tables can be converted at the boundary
# instead of being carried through the calculations.

# -- Pressure -- #
PA_PER_PSIA       = 6894.757293168361   # psia    -> Pa
PA_PER_BAR        = 1.0e5               # bar     -> Pa
PA_PER_ATM        = 101325.0            # atm     -> Pa
PA_PER_TORR       = 133.32236842105263  # torr    -> Pa
PA_PER_MBAR       = 100.0               # mbar    -> Pa
PA_PER_INH2O      = 249.0889            # inH2O   -> Pa (at 4 degC)

# -- Length, area, volume -- #
M_PER_IN          = 0.0254              # in      -> m
M_PER_FT          = 0.3048              # ft      -> m
M_PER_MIL         = 2.54e-5             # mil     -> m
M_PER_MICRON      = 1.0e-6              # micron  -> m
M3_PER_FT3        = 0.028316846592       # ft^3    -> m^3
M3_PER_L          = 1.0e-3              # L       -> m^3
M3_PER_GAL        = 3.785411784e-3      # US gal  -> m^3

# -- Mass, force -- #
KG_PER_LBM        = 0.45359237          # lbm     -> kg
N_PER_LBF         = 4.4482216152605     # lbf     -> N
NM_PER_INLBF      = 0.1129848290276167  # in-lbf  -> N-m
NM_PER_FTLBF      = 1.3558179483314004  # ft-lbf  -> N-m

# -- Temperature -- #
K_PER_DEGR        = 5.0 / 9.0           # degR    -> K (multiplicative)
DEGC_OFFSET       = 273.15              # degC    -> K (additive)

# -- Fundamental -- #
GRAVITY           = 9.80665             # m/s2, standard gravity
R_UNIVERSAL       = 8.314462618         # J/mol-K, universal gas constant
STEFAN_BOLTZMANN  = 5.670374419e-8      # W/m2-K4
SECONDS_PER_YEAR  = 31557600.0          # s/yr, Julian year

# -- Standard reference states -- #
# Two different 'standard' states are in circulation and mixing them is a classic sizing error.
# Leak rates and sccm/sccs use the vacuum-industry standard (0 degC, 1 atm). SCFM in the US gas
# industry uses 60 degF, 1 atm. Both are carried explicitly so neither is assumed by accident.
LEAK_STD_TEMPERATURE = 273.15           # K,  0 degC   -- basis for scc, sccm, sccs
LEAK_STD_PRESSURE    = 101325.0         # Pa, 1 atm
SCFM_STD_TEMPERATURE = 288.706          # K,  60 degF  -- basis for SCFM
SCFM_STD_PRESSURE    = 101325.0         # Pa, 1 atm

# Cv (US, gpm water at 1 psi) to Kv (metric, m3/h water at 1 bar) and to SI flow coefficient.
KV_PER_CV         = 0.8646              # Cv      -> Kv
CV_PER_KV         = 1.0 / KV_PER_CV     # Kv      -> Cv

#--------------------------------------------------------------------------------------------------------------------------#
# -- Standard Atmosphere -- #
#--------------------------------------------------------------------------------------------------------------------------#

def convertPressureToAltitude(pressure: float | np.ndarray) -> float | np.ndarray:

    '''

    Geopotential altitude [m] from ambient pressure [Pa] using the US Standard Atmosphere 1976.

    Implemented over the seven standard layers from sea level to 84.852 km. Used for setting the
    ambient back-pressure on vent and relief sizing, and for the altitude compensation term in
    nozzle performance.

    '''

    pressureArray = np.atleast_1d(np.asarray(pressure, dtype = float))

    # Layer bases: geopotential altitude [m], temperature [K], pressure [Pa], lapse rate [K/m]
    baseAltitude    = np.array([0.0, 11000.0, 20000.0, 32000.0, 47000.0, 51000.0, 71000.0])
    baseTemperature = np.array([288.15, 216.65, 216.65, 228.65, 270.65, 270.65, 214.65])
    basePressure    = np.array([101325.0, 22632.06, 5474.889, 868.0187, 110.9063, 66.93887, 3.956420])
    lapseRate       = np.array([-0.0065, 0.0, 0.001, 0.0028, 0.0, -0.0028, -0.002])

    gasConstantAir  = 287.05287   # J/kg-K

    altitude = np.zeros_like(pressureArray)

    for index, localPressure in enumerate(pressureArray):

        # Find the layer that contains this pressure (pressure decreases monotonically with altitude)
        layer = int(np.searchsorted(-basePressure, -localPressure, side = 'right') - 1)
        layer = max(0, min(layer, len(baseAltitude) - 1))

        if lapseRate[layer] == 0.0:
            # Isothermal layer: exponential pressure profile
            altitude[index] = baseAltitude[layer] - (gasConstantAir * baseTemperature[layer] / GRAVITY) * np.log(localPressure / basePressure[layer])
        else:
            # Gradient layer: power-law pressure profile
            exponent        = -lapseRate[layer] * gasConstantAir / GRAVITY
            altitude[index] = baseAltitude[layer] + (baseTemperature[layer] / lapseRate[layer]) * ((localPressure / basePressure[layer])**exponent - 1.0)

    return altitude[0] if np.isscalar(pressure) or np.ndim(pressure) == 0 else altitude

def convertAltitudeToPressure(altitude: float | np.ndarray) -> float | np.ndarray:

    '''

    Ambient pressure [Pa] from geopotential altitude [m] using the US Standard Atmosphere 1976.

    The inverse of convertPressureToAltitude, over the same seven layers.

    '''

    altitudeArray = np.atleast_1d(np.asarray(altitude, dtype = float))

    baseAltitude    = np.array([0.0, 11000.0, 20000.0, 32000.0, 47000.0, 51000.0, 71000.0])
    baseTemperature = np.array([288.15, 216.65, 216.65, 228.65, 270.65, 270.65, 214.65])
    basePressure    = np.array([101325.0, 22632.06, 5474.889, 868.0187, 110.9063, 66.93887, 3.956420])
    lapseRate       = np.array([-0.0065, 0.0, 0.001, 0.0028, 0.0, -0.0028, -0.002])

    gasConstantAir  = 287.05287   # J/kg-K

    pressure = np.zeros_like(altitudeArray)

    for index, localAltitude in enumerate(altitudeArray):

        layer = int(np.searchsorted(baseAltitude, localAltitude, side = 'right') - 1)
        layer = max(0, min(layer, len(baseAltitude) - 1))

        deltaAltitude = localAltitude - baseAltitude[layer]

        if lapseRate[layer] == 0.0:
            pressure[index] = basePressure[layer] * np.exp(-GRAVITY * deltaAltitude / (gasConstantAir * baseTemperature[layer]))
        else:
            localTemperature = baseTemperature[layer] + lapseRate[layer] * deltaAltitude
            exponent         = -GRAVITY / (lapseRate[layer] * gasConstantAir)
            pressure[index]  = basePressure[layer] * (localTemperature / baseTemperature[layer])**exponent

    return pressure[0] if np.isscalar(altitude) or np.ndim(altitude) == 0 else pressure
