# -- NOVA: The TN D-2832 Chamber Case -- #

'''

The LOX/GH2 heat-sink chamber of NASA TN D-2832 (Schacht, Quentmeyer and Jones, Lewis Research
Center, June 1965), and the shape of its measured gas-side heat transfer, as a second chamber to hold
gas-side models to.

The chamber
-----------

From the report's Figure 1, in inches: a 10.77 bore, a 5.00 throat, a 30 degree converging cone, a
15 degree diverging cone, a throat radius of curvature of 2.5 (one throat radius), 14.500 from the
injector face to the throat and 11.058 from the throat to the exit. The fillet where the barrel
meets the cone is drawn and not dimensioned; it is carried as one throat radius and bracketed. The
wall built from those numbers puts the report's instrumentation stations (its Figure 3) at area
ratios of 4.64, 1.785, 1.00, 1.267 and 3.33 against the tabulated 4.64, 1.78, 1.00, 1.27 and 3.33.

What was measured
-----------------

Transient temperatures in copper rods at the five stations, over chamber pressures of 150 to 1000
psia, most runs near 15 percent hydrogen by weight. The data correlate as

    St* Pr*^0.7 = C Re*_d^-0.2

with properties at Eckert's reference enthalpy and the local static pressure, and C is not one
number along the wall: 0.0257 in the barrel, 0.0240 at an area ratio of 1.78, 0.0151 at the throat
(the mean of three circumferential stations), 0.0153 at 1.27 and 0.0188 at 3.33. The report states
that changing the transport data moved every C by about 30 percent together, so what survives a
change of property model is the shape, C at a station over C in the barrel, and that is what is
compared here.

A model is held to the shape by computing its own C at each station with one consistent property
evaluation, a reference temperature with CEA's viscosity and Prandtl number, and dividing by its own
C at station 1. Because the same evaluation enters numerator and denominator, the comparison does
not depend on matching the report's property routine, only on the property variation between
stations, which a reference-temperature evaluation carries.

NOVA's `measured` gas-side axial model is built from these constants, so this chamber is not a test
of it. It is independent of the marched layer and of Ievlev's method.

Author: Sean Bowman

'''

import math

import numpy as np

inch = 0.0254                         # [m]

throatRadius      = 2.5 * inch        # [m]
chamberRadius     = 0.5 * 10.77 * inch
injectorToThroat  = 14.5 * inch
throatToExit      = 11.058 * inch
convergingAngle   = 30.0              # [deg]
divergingAngle    = 15.0              # [deg]
throatCurvature   = 1.0               # [-] both arcs, over the throat radius
filletCurvature   = 1.0               # [-] not dimensioned in the report
filletBracket     = (0.5, 2.0)

# Station, axial distance from the throat [in], area ratio, measured C, and its scatter as a
# fraction of C (the report's standard deviation of the data about the station's value)
stations = (
    (1, -8.774, 4.64, 0.0257, 0.109),
    (2, -2.125, 1.78, 0.0240, 0.163),
    (3,  0.000, 1.00, 0.0151, 0.132),
    (4,  1.500, 1.27, 0.0153, 0.104),
    (5,  8.026, 3.33, 0.0188, 0.079),
)

# 15 percent hydrogen by weight, the bulk of the runs, over the pressure range they span
mixtureRatio     = 0.85 / 0.15
chamberPressures = (300.0 * 6894.757, 600.0 * 6894.757, 900.0 * 6894.757)    # [Pa]
wallTemperature  = 500.0              # [K] a heat-sink wall partway through its transient
wallBracket      = (350.0, 800.0)

def measuredShape() -> np.ndarray:

    '''

    The measured C at each station over the measured C in the barrel.

    '''

    constants = np.array([station[3] for station in stations])

    return constants / constants[0]

def wall(filletRadius: float = filletCurvature, spacing: float = 1.0e-3) -> tuple:

    '''

    The chamber wall from the injector face, with the throat at `injectorToThroat`.

    Returns:
    --------
    tuple : (location [m from the injector face], radius [m])

    '''

    rt = throatRadius
    arc = throatCurvature * rt
    fillet = filletRadius * rt
    upSlope, downSlope = math.radians(convergingAngle), math.radians(divergingAngle)

    # Upstream, in a coordinate that is zero at the throat
    arcStart = -arc * math.sin(upSlope)
    arcStartRadius = rt + arc * (1.0 - math.cos(upSlope))
    filletEndRadius = chamberRadius - fillet * (1.0 - math.cos(upSlope))
    filletEnd = arcStart - (filletEndRadius - arcStartRadius) / math.tan(upSlope)
    filletCentre = filletEnd - fillet * math.sin(upSlope)

    local = np.arange(-injectorToThroat, throatToExit + spacing / 2.0, spacing)
    radius = np.full_like(local, chamberRadius)
    onFillet = (local > filletCentre) & (local <= filletEnd)
    radius[onFillet] = chamberRadius - fillet + np.sqrt(fillet**2 - (local[onFillet] - filletCentre)**2)
    onCone = (local > filletEnd) & (local <= arcStart)
    radius[onCone] = arcStartRadius + (arcStart - local[onCone]) * math.tan(upSlope)
    onArc = (local > arcStart) & (local <= 0.0)
    radius[onArc] = rt + arc - np.sqrt(arc**2 - local[onArc]**2)

    # Downstream: the same arc onto the 15 degree cone
    arcEnd = arc * math.sin(downSlope)
    arcEndRadius = rt + arc * (1.0 - math.cos(downSlope))
    onDownArc = (local > 0.0) & (local <= arcEnd)
    radius[onDownArc] = rt + arc - np.sqrt(arc**2 - local[onDownArc]**2)
    onDownCone = local > arcEnd
    radius[onDownCone] = arcEndRadius + (local[onDownCone] - arcEnd) * math.tan(downSlope)

    return local + injectorToThroat, radius

def stationLocations() -> np.ndarray:

    '''

    The instrumentation stations on the injector-face axis [m].

    '''

    return injectorToThroat + inch * np.array([station[1] for station in stations])

def correlationConstant(heatTransferCoefficient, staticTemperature, mach, pressure, velocity,
                        radius, wallTemperatureValue: float, gamma: float, gasConstant: float,
                        viscosityFit: dict, prandtlNumber: float) -> np.ndarray:

    '''

    C in St* Pr*^0.7 = C Re*_d^-0.2, from a heat transfer coefficient, at Eckert's reference
    temperature.

    The coefficient is referred to the adiabatic wall temperature less the wall temperature, as the
    report's is, and the Stanton number to the reference density and the specific heat
    gamma R / (gamma - 1). The diameter Reynolds number is on the local wall diameter.

    Returns:
    --------
    numpy.ndarray : C at each station [-]

    '''

    recoveryFactor = prandtlNumber**(1.0 / 3.0)
    stagnation = staticTemperature * (1.0 + 0.5 * (gamma - 1.0) * mach**2)
    reference = staticTemperature + 0.5 * (wallTemperatureValue - staticTemperature) \
                + 0.22 * recoveryFactor * (stagnation - staticTemperature)
    density = pressure / (gasConstant * reference)
    viscosity = viscosityFit['viscosityReference'] * (reference / viscosityFit['viscosityTemperature'])**viscosityFit['viscosityExponent']
    specificHeat = gamma * gasConstant / (gamma - 1.0)
    stanton = heatTransferCoefficient / (density * velocity * specificHeat)
    reynolds = density * velocity * 2.0 * radius / viscosity

    return stanton * prandtlNumber**0.7 * reynolds**0.2

def shapeError(modelShape, measured = None) -> float:

    '''

    RMS of the log ratio of model to measured C over C in the barrel, over stations 2 to 5: the
    selection metric, fixed before any candidate was scored.

    '''

    measured = measuredShape() if measured is None else measured

    return float(np.sqrt(np.mean(np.log(np.asarray(modelShape)[1:] / measured[1:])**2)))
