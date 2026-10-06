# -- NOVA: The 40k Calorimeter Chamber Case -- #

'''

The measured wall heat flux and heat transfer coefficient of the MSFC 40k calorimeter chamber, RPA's
prediction for the same test, the chamber's geometry, and the scorecard every gas-side model is held
to on it.

Sources
-------

The measurement is Test 024 of the 40k water-cooled calorimeter chamber, Figs. 11 and 12 of Dexter,
Fisher, Hulka, Denisov, Shibanov and Agarkov, "Scaling Techniques for Design, Development, and
Test", in *Liquid Rocket Thrust Chambers: Aspects of Modeling, Analysis, and Design*, Progress in
Astronautics and Aeronautics Vol. 200, AIAA, 2004: 10.87 MPa, O/F 6.0, the heat flux from each of
58 circumferential water circuits and the heat transfer coefficient reduced from it. RPA's
prediction for the same test and the wall RPA built for it are Figure 14 of A. Ponomarenko, "RPA:
Tool for Rocket Propulsion Analysis. Thermal Analysis of Thrust Chambers", 2012, which also
reproduces the measurement as its Figure 13. `featureShowcase/digitizeCalorimeter40k.py`
regenerates every array below from the two PDFs and states the method and its resolution.

The chamber
-----------

Dexter's Table 1: an 84.1 mm throat, a 143.8 mm chamber, a contraction ratio of 2.92, 355.6 mm from
the injector face to the throat and an expansion ratio of 7, with 61 injection elements. The
chamber shares its convergence angle and throat radius of curvature with the full-scale SSME main
chamber, whose values the chapter does not give. RPA's table carries a "combustion chamber
diameter" of 43.8 mm, which is the 143.8 mm with its first digit lost; Dexter's table prints the
same slip in its regeneratively cooled column.

RPA's drawn wall is the hardware's to within its reading: a 42.3 mm throat against 42.05, a
contraction ratio of 2.91 against 2.92, an expansion ratio of 7.06 against 7. `rpaContour` scales
it radially onto the 42.05 mm throat, which keeps every area ratio and axial station, and places
its minimum on RPA's throat marker. The wall is still RPA's construction of the chamber rather
than a survey of it, and its throat arc spans two or three pixel rows, so the entrant arc radius
is carried as a bracket.

The wall temperature
--------------------

The coefficient was reduced as h = (Q/A) / (T_aw - T_wh), with T_aw the chamber temperature times
the recovery factor (1 + Pr^(1/3) (gamma - 1)/2 M^2) / (1 + (gamma - 1)/2 M^2) from one-dimensional
equilibrium, and T_wh from a two-dimensional finite-difference model of the wall with forced
convection and nucleate boiling on the water side, capped at the water's saturation temperature
plus 283 K. Both figures together therefore give the wall temperature the reduction used:
T_wh = T_aw - (Q/A) / h. `reductionWallTemperature` recovers it. With CEA's frozen Prandtl number
in the recovery factor it reads 690 to 830 K over the barrel and a plateau of 865 to 890 K over the
26 mm ahead of the throat, which is the cap, and falls to 275 to 505 K from 380 mm on. With the
equilibrium Prandtl number the diverging-section wall would fall below the water temperature,
which it cannot, so the frozen value is the reading carried.

What is not known
-----------------

The hardware contour, beyond its throat, chamber, length and expansion ratio. The faceplate was
transpiration cooled and the outer injector row carried no mixture-ratio bias, so no wall film was
injected; the low flux over the first 85.6 mm is the faceplate coolant and the injector near field,
and those stations are outside every comparison. The fuel arrived warm from a preburner, at a
temperature the chapter does not give; CEA is run on liquid hydrogen.

The scorecard
-------------

Every number is a model's relative error against the measurement unless named otherwise:

    barrelError         mean over measured stations from 100 to 250 mm
    throatToBarrelError the model's throat-to-barrel ratio over the measured one, less one: the
                        shape of the profile with its level taken out, which property choices
                        move by a few percent where they move the level by tens
    peakError           model maximum over the measured maximum
    peakLocationError   model peak position less the measured one [mm], each taken as the centroid
                        of the region within 5 percent of its own maximum, because the measurement
                        holds a plateau rather than a single peak
    throatError         at the throat station, 355.6 mm
    convergingSlope     flux at area ratio 1.05 over flux at 2.5 on the subsonic branch, reported
                        for the model and the measurement
    asymmetry           diverging over converging flux at matched area ratios of 1.1, 1.5 and 2.0,
                        reported for the model and the measurement
    rmsError            over measured stations from 100 to 480 mm

The model's area ratios come from the model's own wall and the measurement's from RPA's wall.

Author: Sean Bowman

'''

import json
import math
import os

import numpy as np

from NOVA.boundaryLayer import solveBoundaryLayer
from NOVA.gasDynamics import isentropicValues, machFromAreaRatio
from NOVA.gasSideHeatTransfer import bartzHeatTransferCoefficient, measuredAxialFactor

#----------------------------------------------------------------------#
# -- Constants -- #
#----------------------------------------------------------------------#

btuPerSquareInchSecond = 1.63534e6         # [W/m^2] per BTU/(s in^2)
btuPerSquareInchSecondF = 2.94361e6        # [W/m^2-K] per BTU/(in^2 s F)

throatLocation    = 0.3556            # [m] from the injector face, Dexter's L'
throatRadius      = 0.5 * 0.0841      # [m] Dexter's Table 1
contractionRatio  = (143.8 / 84.1)**2 # [-] 2.92
expansionRatio    = 7.0               # [-]
filmCooledEnd     = 0.0856            # [m] from the injector; the faceplate coolant dominates upstream of it
waterTemperature  = 289.0             # [K] coolant inlet, about 60 F

# RPA's converging section as RPA builds one, fitted to its digitized wall from 240 mm to the
# throat: a 30.1 degree cone between a fillet of 1.48 and an entrant arc of 1.15 throat radii, at a
# contraction ratio of 2.90, to 0.31 mm RMS. The same answer comes back from three starting points.
# The entrant arc is the least certain of the four, because the figure gives it two or three pixel
# rows, so it carries the widest bracket.
throatInletCurvature = 1.15           # [-] entrant arc over throat radius
throatInletCurvatureBracket = (0.8, 1.5)
convergingHalfAngle  = 30.0           # [deg]
chamberFilletRadius  = 1.48           # [-] fillet over throat radius

# Uniform walls to set beside the reduction's own wall temperature
uniformWallTemperatures = (550.0, 700.0, 850.0)    # [K]

operatingPoints = {
    # Test 024; the mass flow is Pc At / c* through the 84.1 mm throat
    'measured': {'mixtureRatio': 6.0, 'chamberPressure': 10.87e6, 'massFlow': 26.11},
}
# RPA ran its prediction at the test's own operating point
operatingPoints['rpa'] = operatingPoints['measured']
# The fuel reached the injector warm, through a preburner, at a temperature the chapter does not
# give. Hydrogen fed as gas at 298 K is the sensitivity of the chamber state to that.
operatingPoints['warmFuel'] = dict(operatingPoints['measured'], fuel = 'GH2')

def operatingPoint(point) -> dict:

    '''

    An operating point as a full description: a name from `operatingPoints`, or a dict carrying
    'mixtureRatio' and 'chamberPressure' and optionally 'fuel', 'oxidizer', 'oxidizerTemperature'
    and 'expansionRatio'. The defaults are this chamber's.

    '''

    point = dict(operatingPoints[point]) if isinstance(point, str) else dict(point)
    point.setdefault('fuel', 'LH2')
    point.setdefault('oxidizer', 'LOX')
    point.setdefault('oxidizerTemperature', 90.17)
    point.setdefault('expansionRatio', expansionRatio)

    return point

def _pointKey(point) -> tuple:

    '''A hashable record of everything the CEA solve depends on.'''

    point = operatingPoint(point)

    return tuple(point[name] for name in ('fuel', 'oxidizer', 'oxidizerTemperature', 'mixtureRatio',
                                          'chamberPressure', 'expansionRatio'))

barrelWindow = (0.100, 0.250)         # [m] from the injector
rmsWindow    = (0.100, 0.480)         # [m] from the injector
slopeRatios  = (1.05, 2.5)            # [-] subsonic area ratios the converging slope spans
matchedRatios = (1.1, 1.5, 2.0)       # [-] area ratios the asymmetry is taken at
reportStations = (0.250, 0.290, 0.3306, 0.3456, 0.3556, 0.3706, 0.390, 0.460)   # [m]

# Dexter Figs. 11 and 12, Test 024: axial distance from the throat [cm], wall heat flux
# [BTU/s-in^2], heat transfer coefficient [BTU/in^2-s-F]
measuredData = (
    (-35.27, 17.65, 0.00331), (-34.18, 17.62, 0.00335), (-33.23, 19.05, 0.00359), (-32.12, 19.72, 0.00376),
    (-31.17, 21.84, 0.00419), (-30.03, 23.99, 0.00471), (-28.82, 26.09, 0.00512), (-27.67, 28.13, 0.00566),
    (-26.66, 28.55, 0.00570), (-25.56, 28.82, 0.00592), (-24.62, 29.52, 0.00596), (-23.42, 32.63, 0.00662),
    (-22.46, 32.05, 0.00646), (-21.39, 30.88, 0.00627), (-20.39, 31.09, 0.00630), (-19.37, 30.48, 0.00620),
    (-18.38, 30.78, 0.00623), (-17.22, 31.15, 0.00626), (-16.06, 29.44, 0.00597), (-15.03, 30.20, 0.00613),
    (-13.93, 29.83, 0.00599), (-12.95, 28.96, 0.00577), (-11.88, 27.43, 0.00548), (-11.04, 28.91, 0.00565),
    (-10.52, 27.29, 0.00520), (-10.01, 26.30, 0.00501), (-9.32, 26.34, 0.00495), (-8.96, 30.05, 0.00563),
    (-8.34, 33.28, 0.00639), (-7.78, 34.79, 0.00665), (-7.24, 37.29, 0.00717), (-6.57, 39.00, 0.00761),
    (-5.98, 42.41, 0.00849), (-5.32, 45.74, 0.00929), (-4.80, 48.43, 0.00988), (-4.19, 49.74, 0.01019),
    (-3.70, 53.26, 0.01106), (-3.07, 53.85, 0.01123), (-2.66, 56.81, 0.01201), (-2.02, 54.56, 0.01143),
    (-1.52, 56.57, 0.01184), (-0.76, 57.03, 0.01207), (-0.37, 54.21, 0.01141), (0.31, 52.36, 0.01097),
    (0.76, 44.25, 0.00905), (1.44, 38.40, 0.00777), (1.92, 29.52, 0.00576), (2.53, 21.15, 0.00394),
    (3.26, 18.33, 0.00339), (3.78, 16.68, 0.00303), (4.62, 16.97, 0.00320), (5.32, 13.01, 0.00241),
    (6.34, 12.16, 0.00226), (7.55, 10.95, 0.00205), (8.52, 9.82, 0.00173), (9.59, 8.63, 0.00156),
    (10.63, 7.62, 0.00140), (11.55, 6.63, 0.00119))

# RPA Figure 14, red: distance from the injector face [mm], heat flux [kW/m^2], at Test 024's point
rpaFlux = (
    (0.0, 40784), (5.0, 41145), (10.0, 41609), (15.0, 42035), (20.0, 42307), (25.0, 42834),
    (30.0, 43234), (35.0, 43497), (40.0, 43824), (45.0, 44022), (50.0, 44149), (55.0, 44292),
    (60.0, 44475), (65.0, 44556), (70.0, 44589), (75.0, 44589), (80.0, 44589), (85.0, 44696),
    (90.0, 44790), (95.0, 44790), (100.0, 44706), (105.0, 44835), (110.0, 44980), (115.0, 44974),
    (120.0, 44990), (125.0, 44894), (130.0, 45210), (135.0, 45198), (140.0, 45190), (145.0, 45308),
    (150.0, 45391), (155.0, 45391), (160.0, 45304), (165.0, 45456), (170.0, 45589), (175.0, 45591),
    (180.0, 45681), (185.0, 45595), (190.0, 45720), (195.0, 45792), (200.0, 45792), (205.0, 45792),
    (210.0, 45865), (215.0, 45992), (220.0, 45935), (225.0, 45992), (230.0, 45992), (235.0, 45992),
    (240.0, 45912), (245.0, 45992), (250.0, 45992), (255.0, 45992), (260.0, 45895), (265.0, 46002),
    (270.0, 46249), (275.0, 46674), (280.0, 47474), (285.0, 48466), (290.0, 49984), (295.0, 52018),
    (300.0, 54486), (305.0, 57617), (310.0, 62034), (315.0, 66422), (320.0, 71268), (325.0, 77419),
    (330.0, 82483), (335.0, 87073), (340.0, 90813), (345.0, 93850), (350.0, 95203), (355.0, 95354),
    (360.0, 89914), (365.0, 83983), (370.0, 78115), (375.0, 72800), (380.0, 67570), (385.0, 62510),
    (390.0, 58364), (395.0, 54350), (400.0, 50606), (405.0, 47638), (410.0, 44647), (415.0, 41792),
    (420.0, 39649), (425.0, 37425), (430.0, 35384), (435.0, 33543), (440.0, 31999), (445.0, 30564),
    (450.0, 28987), (455.0, 27708), (460.0, 26564), (465.0, 25571), (470.0, 24647), (475.0, 23727),
    (480.0, 22761), (485.0, 22003), (490.0, 21344), (495.0, 20624), (500.0, 19849), (505.0, 19372),
    (510.0, 18852), (515.0, 18298), (520.0, 17649), (525.0, 17404), (530.0, 16982), (535.0, 16570),
    (540.0, 16186), (545.0, 15757), (550.0, 15514), (555.0, 15159), (560.0, 14934), (565.0, 14601),
    (570.0, 14340), (575.0, 14086), (580.0, 13816), (585.0, 13530), (590.0, 13403), (595.0, 13193),
    (600.0, 12826), (605.0, 12794), (610.0, 12654), (615.0, 12511), (620.0, 12343), (625.0, 12251),
    (630.0, 12123), (635.0, 11983), (640.0, 11920), (645.0, 11706), (650.0, 11573))

# RPA Figure 14, black, through a least-squares spline: distance from the injector face [mm], radius [mm]
rpaContourDigitized = (
    (0.0, 72.07), (2.5, 72.08), (5.0, 72.08), (7.5, 72.06), (10.0, 72.08), (12.5, 72.10),
    (15.0, 72.08), (17.5, 72.01), (20.0, 71.98), (22.5, 72.01), (25.0, 72.07), (27.5, 72.10),
    (30.0, 72.10), (32.5, 72.08), (35.0, 72.05), (37.5, 72.03), (40.0, 72.01), (42.5, 72.02),
    (45.0, 72.04), (47.5, 72.08), (50.0, 72.10), (52.5, 72.09), (55.0, 72.05), (57.5, 72.02),
    (60.0, 72.00), (62.5, 72.01), (65.0, 72.05), (67.5, 72.09), (70.0, 72.11), (72.5, 72.10),
    (75.0, 72.06), (77.5, 72.00), (80.0, 71.99), (82.5, 72.02), (85.0, 72.08), (87.5, 72.09),
    (90.0, 72.08), (92.5, 72.07), (95.0, 72.07), (97.5, 72.08), (100.0, 72.08), (102.5, 72.08),
    (105.0, 72.08), (107.5, 72.08), (110.0, 72.08), (112.5, 72.08), (115.0, 72.07), (117.5, 72.04),
    (120.0, 72.00), (122.5, 72.00), (125.0, 72.04), (127.5, 72.09), (130.0, 72.11), (132.5, 72.09),
    (135.0, 72.05), (137.5, 72.01), (140.0, 71.99), (142.5, 72.02), (145.0, 72.07), (147.5, 72.10),
    (150.0, 72.10), (152.5, 72.08), (155.0, 72.04), (157.5, 72.01), (160.0, 72.01), (162.5, 72.03),
    (165.0, 72.06), (167.5, 72.08), (170.0, 72.09), (172.5, 72.09), (175.0, 72.07), (177.5, 72.03),
    (180.0, 71.99), (182.5, 72.00), (185.0, 72.06), (187.5, 72.10), (190.0, 72.10), (192.5, 72.07),
    (195.0, 72.06), (197.5, 72.08), (200.0, 72.09), (202.5, 72.08), (205.0, 72.06), (207.5, 72.08),
    (210.0, 72.10), (212.5, 72.09), (215.0, 72.04), (217.5, 72.00), (220.0, 72.00), (222.5, 72.03),
    (225.0, 72.06), (227.5, 72.08), (230.0, 72.09), (232.5, 72.08), (235.0, 72.06), (237.5, 72.03),
    (240.0, 72.00), (242.5, 72.01), (245.0, 72.05), (247.5, 72.10), (250.0, 72.10), (252.5, 72.08),
    (255.0, 72.06), (257.5, 72.04), (260.0, 72.01), (262.5, 71.99), (265.0, 72.01), (267.5, 72.11),
    (270.0, 72.21), (272.5, 72.13), (275.0, 71.84), (277.5, 71.50), (280.0, 71.20), (282.5, 70.83),
    (285.0, 70.22), (287.5, 69.41), (290.0, 68.56), (292.5, 67.75), (295.0, 66.86), (297.5, 65.78),
    (300.0, 64.55), (302.5, 63.28), (305.0, 61.98), (307.5, 60.51), (310.0, 58.79), (312.5, 57.11),
    (315.0, 55.82), (317.5, 54.78), (320.0, 53.42), (322.5, 51.53), (325.0, 49.73), (327.5, 48.64),
    (330.0, 48.06), (332.5, 47.39), (335.0, 46.40), (337.5, 45.36), (340.0, 44.54), (342.5, 43.91),
    (345.0, 43.40), (347.5, 42.97), (350.0, 42.59), (352.5, 42.31), (355.0, 42.39), (357.5, 43.03),
    (360.0, 44.03), (362.5, 45.03), (365.0, 45.85), (367.5, 46.62), (370.0, 47.45), (372.5, 48.32),
    (375.0, 49.17), (377.5, 50.01), (380.0, 50.89), (382.5, 51.84), (385.0, 52.77), (387.5, 53.61),
    (390.0, 54.41), (392.5, 55.27), (395.0, 56.22), (397.5, 57.15), (400.0, 58.02), (402.5, 58.85),
    (405.0, 59.72), (407.5, 60.62), (410.0, 61.51), (412.5, 62.37), (415.0, 63.23), (417.5, 64.14),
    (420.0, 65.07), (422.5, 65.97), (425.0, 66.83), (427.5, 67.69), (430.0, 68.59), (432.5, 69.47),
    (435.0, 70.28), (437.5, 71.04), (440.0, 71.84), (442.5, 72.74), (445.0, 73.67), (447.5, 74.57),
    (450.0, 75.46), (452.5, 76.38), (455.0, 77.29), (457.5, 78.09), (460.0, 78.69), (462.5, 79.19),
    (465.0, 79.74), (467.5, 80.41), (470.0, 81.18), (472.5, 82.00), (475.0, 82.71), (477.5, 83.18),
    (480.0, 83.58), (482.5, 84.24), (485.0, 85.19), (487.5, 86.09), (490.0, 86.65), (492.5, 87.06),
    (495.0, 87.61), (497.5, 88.36), (500.0, 89.18), (502.5, 89.94), (505.0, 90.57), (507.5, 91.03),
    (510.0, 91.39), (512.5, 91.80), (515.0, 92.32), (517.5, 92.82), (520.0, 93.24), (522.5, 93.62),
    (525.0, 94.04), (527.5, 94.51), (530.0, 94.96), (532.5, 95.41), (535.0, 96.05), (537.5, 97.04),
    (540.0, 98.07), (542.5, 98.62), (545.0, 98.67), (547.5, 98.88), (550.0, 99.71), (552.5, 100.68),
    (555.0, 101.04), (557.5, 100.81), (560.0, 100.58), (562.5, 100.73), (565.0, 101.13), (567.5, 101.57),
    (570.0, 101.98), (572.5, 102.37), (575.0, 102.74), (577.5, 103.13), (580.0, 103.55), (582.5, 104.03),
    (585.0, 104.56), (587.5, 105.08), (590.0, 105.48), (592.5, 105.71), (595.0, 105.82), (597.5, 105.90),
    (600.0, 106.04), (602.5, 106.30), (605.0, 106.71), (607.5, 107.21), (610.0, 107.72), (612.5, 108.15),
    (615.0, 108.40), (617.5, 108.49), (620.0, 108.55), (622.5, 108.66), (625.0, 108.90), (627.5, 109.31),
    (630.0, 109.83), (632.5, 110.31), (635.0, 110.68), (637.5, 110.98), (640.0, 111.25), (642.5, 111.50),
    (645.0, 111.76), (647.5, 112.00), (650.0, 112.22))

#----------------------------------------------------------------------#
# -- Data -- #
#----------------------------------------------------------------------#

def measuredProfile() -> tuple:

    '''

    The measured heat flux, on the injector-face axis.

    Returns:
    --------
    tuple : (location [m from the injector face], heat flux [W/m^2])

    '''

    data = np.asarray(measuredData, dtype = float)

    return throatLocation + 0.01 * data[:, 0], btuPerSquareInchSecond * data[:, 1]

def measuredCoefficient() -> tuple:

    '''

    The measured heat transfer coefficient, h = (Q/A) / (T_aw - T_wh) as the reduction formed it.

    Returns:
    --------
    tuple : (location [m from the injector face], coefficient [W/m^2-K])

    '''

    data = np.asarray(measuredData, dtype = float)

    return throatLocation + 0.01 * data[:, 0], btuPerSquareInchSecondF * data[:, 2]

def reductionRecoveryTemperature(location, gas: dict, prandtlModel: str = 'frozen') -> np.ndarray:

    '''

    The adiabatic wall temperature the reduction used, Dexter's Eqs. 23 and 24, at stations on
    RPA's wall with a one-dimensional state.

    Parameters:
    -----------
    location : array_like
        Stations [m from the injector face].
    gas : dict
        From `gasState` at the test's operating point.
    prandtlModel : str
        'frozen' or 'equilibrium': which of CEA's chamber Prandtl numbers the recovery factor takes.

    Returns:
    --------
    numpy.ndarray : T_aw [K]

    '''

    wallX, wallR = rpaContour()
    mach = np.interp(location, wallX, oneDimensionalEdgeState(wallX, wallR, gas)[0])
    prandtl = gas['prandtlFrozen']['chamber'] if prandtlModel == 'frozen' else gas['prandtl']['chamber']
    expansion = 0.5 * (gas['gamma'] - 1.0) * mach**2

    return gas['stagnationTemperature'] * (1.0 + prandtl**(1.0 / 3.0) * expansion) / (1.0 + expansion)

def reductionWallTemperature(location, gas: dict, prandtlModel: str = 'frozen') -> np.ndarray:

    '''

    The hot-wall temperature the reduction used, T_wh = T_aw - (Q/A) / h, carried onto any stations.

    It is recovered at the 58 measured stations, held no lower than the water, and interpolated
    between them; outside the measured span it holds its end values.

    Parameters:
    -----------
    location : array_like
        Stations to return it at [m from the injector face].
    gas : dict
        From `gasState` at the test's operating point.
    prandtlModel : str
        As `reductionRecoveryTemperature`.

    Returns:
    --------
    numpy.ndarray : T_wh [K]

    '''

    stations, heatFlux = measuredProfile()
    _, coefficient = measuredCoefficient()
    wall = reductionRecoveryTemperature(stations, gas, prandtlModel) - heatFlux / coefficient

    return np.interp(location, stations, np.maximum(wall, waterTemperature))

def rpaHeatFlux() -> tuple:

    '''

    RPA's predicted heat flux for Test 024.

    Returns:
    --------
    tuple : (location [m from the injector face], heat flux [W/m^2])

    '''

    data = np.asarray(rpaFlux, dtype = float)

    return 1e-3 * data[:, 0], 1e3 * data[:, 1]

def rpaContour(scaledThroatRadius: float = throatRadius, alignThroat: bool = True) -> tuple:

    '''

    RPA's wall for the chamber, scaled radially onto a throat radius and placed on the throat.

    Radial scaling keeps every area ratio and every axial station, which are the two things a
    comparison against the measurement reads off the wall; the default, the hardware's 42.05 mm,
    is a 0.6 percent change from the 42.3 mm RPA drew. The digitized minimum sits about 2.4 mm
    upstream of RPA's own throat marker, inside a flat of about 3 mm that the figure draws at the
    throat, so by default the wall is moved axially to put its minimum on the marker: the station
    the measurement calls its throat.

    Parameters:
    -----------
    scaledThroatRadius : float
        Throat radius to scale onto [m]. None returns the wall as digitized.
    alignThroat : bool
        Move the wall so its minimum radius is at `throatLocation`.

    Returns:
    --------
    tuple : (location [m from the injector face], radius [m])

    '''

    data = np.asarray(rpaContourDigitized, dtype = float)
    location, radius = 1e-3 * data[:, 0], 1e-3 * data[:, 1]
    if scaledThroatRadius is not None:
        radius = radius * scaledThroatRadius / radius.min()
    if alignThroat:
        # Vertex of the parabola through the minimum and its two neighbours
        index = int(np.argmin(radius))
        before, at, after = radius[index - 1], radius[index], radius[index + 1]
        spacing = location[index + 1] - location[index]
        vertex = location[index] + 0.5 * spacing * (before - after) / (before - 2.0 * at + after)
        location = location + (throatLocation - vertex)

    return location, radius

def parametricWall(contraction: float = contractionRatio, inletCurvature: float = throatInletCurvature,
                   convergingAngle: float = convergingHalfAngle, filletRadius: float = chamberFilletRadius,
                   spacing: float = 1.0e-3) -> tuple:

    '''

    A converging section built the way RPA builds one, joined to RPA's diverging wall.

    Barrel, a concave fillet onto a straight cone, and a convex entrant arc onto the throat, with
    the throat at `throatLocation` and the barrel starting at the injector face. Downstream of the
    throat the wall is RPA's, so a sweep over these parameters moves the converging section alone.

    Parameters:
    -----------
    contraction : float
        Chamber over throat area [-].
    inletCurvature : float
        Entrant arc radius over the throat radius [-].
    convergingAngle : float
        Cone half-angle [deg].
    filletRadius : float
        Barrel-to-cone fillet radius over the throat radius [-].
    spacing : float
        Station spacing on the converging section [m].

    Returns:
    --------
    tuple : (location [m from the injector face], radius [m])

    '''

    slope = math.radians(convergingAngle)
    chamberRadius = throatRadius * math.sqrt(contraction)
    entrant = inletCurvature * throatRadius
    fillet = filletRadius * throatRadius

    # Local axial coordinate, zero at the throat and negative upstream
    arcStart = -entrant * math.sin(slope)
    arcStartRadius = throatRadius + entrant * (1.0 - math.cos(slope))
    filletEndRadius = chamberRadius - fillet * (1.0 - math.cos(slope))
    filletEnd = arcStart - (filletEndRadius - arcStartRadius) / math.tan(slope)
    filletCentre = filletEnd - fillet * math.sin(slope)
    if filletEndRadius < arcStartRadius:
        raise ValueError('The fillet and the entrant arc overlap; no straight cone fits between them.')

    local = np.arange(-throatLocation, 0.0 + spacing / 2.0, spacing)
    radius = np.full_like(local, chamberRadius)
    onFillet = (local > filletCentre) & (local <= filletEnd)
    radius[onFillet] = chamberRadius - fillet + np.sqrt(fillet**2 - (local[onFillet] - filletCentre)**2)
    onCone = (local > filletEnd) & (local <= arcStart)
    radius[onCone] = arcStartRadius + (arcStart - local[onCone]) * math.tan(slope)
    onArc = local > arcStart
    radius[onArc] = throatRadius + entrant - np.sqrt(entrant**2 - local[onArc]**2)

    divergingLocation, divergingRadius = rpaContour()
    downstream = divergingLocation > throatLocation

    return (np.concatenate([local + throatLocation, divergingLocation[downstream]]),
            np.concatenate([radius, divergingRadius[downstream]]))

#----------------------------------------------------------------------#
# -- Gas state -- #
#----------------------------------------------------------------------#

def gasState(pointName = 'measured') -> dict:

    '''

    The constant-property gas NOVA runs at one operating point, from CEA.

    Mirrors what `config.py` sets on a nozzle with the default chamber gamma model: the chamber
    equilibrium gamma, the gas constant from the chamber molecular weight and the chamber
    temperature as the stagnation temperature. Transport properties are CEA's equilibrium values at
    the chamber, the throat and an expansion ratio of 7.

    Parameters:
    -----------
    pointName : str | dict
        A key of `operatingPoints`, or a point as `operatingPoint` takes it.

    Returns:
    --------
    dict : gamma, gasConstant [J/kg-K], molecularWeight, stagnationTemperature [K],
        chamberPressure [Pa], characteristicVelocity [m/s], chamberEnthalpy [J/kg], viscosity
        [Pa-s], temperature [K] and equilibrium Prandtl number at 'chamber', 'throat' and 'exit',
        and the frozen Prandtl number at 'chamber' and 'throat'

    '''

    point = operatingPoint(pointName)
    solve = _ceaSolve(point)
    results = solve.ceaResults
    molecularWeight = float(results['combustionChamberMolecularWeight'])

    # Frozen transport at the chamber and throat, which CEA reports beside the equilibrium values.
    # The exit is left out: a frozen run expands to a different exit state.
    pressurePsia = point['chamberPressure'] / 6894.757
    frozenChamber = solve.ceaObject.get_Chamber_Transport(Pc = pressurePsia, MR = point['mixtureRatio'],
                                                          eps = point['expansionRatio'], frozen = 1)
    frozenThroat = solve.ceaObject.get_Throat_Transport(Pc = pressurePsia, MR = point['mixtureRatio'],
                                                        eps = point['expansionRatio'], frozen = 1)

    return {
        'pointName':              point,
        'gamma':                  float(results['combustionChamberGamma']),
        'gasConstant':            8314.0 / molecularWeight,
        'molecularWeight':        molecularWeight,
        'stagnationTemperature':  float(results['combustionChamberTemperature']),
        'chamberPressure':        point['chamberPressure'],
        'characteristicVelocity': float(results['characteristicVelocity']),
        'chamberEnthalpy':        float(results['combustionChamberEnthalpy']),
        'viscosity': {'chamber': float(results['combustionChamberViscosity']),
                      'throat':  float(results['throatViscosity']),
                      'exit':    float(results['exitViscosity'])},
        'temperature': {'chamber': float(results['combustionChamberTemperature']),
                        'throat':  float(results['throatTemperature']),
                        'exit':    float(results['exitTemperature'])},
        'prandtl': {'chamber': float(results['combustionChamberPrandtlNumber']),
                    'throat':  float(results['throatPrandtlNumber']),
                    'exit':    float(results['exitPrandtlNumber'])},
        'prandtlFrozen': {'chamber': float(frozenChamber[3]), 'throat': float(frozenThroat[3])},
    }

def _ceaSolve(pointName):

    '''

    The CEA solve at one operating point, expanded to its exit area ratio.

    '''

    from NOVA.ceaInterface import CEA

    point = operatingPoint(pointName)

    return CEA(fuelName = point['fuel'], oxidizerName = point['oxidizer'],
               oxidizerInitialTemperature = point['oxidizerTemperature'],
               chamberPressure = point['chamberPressure'], expansionRatio = point['expansionRatio'],
               pressureUnits = 'Pa', OFRatio = point['mixtureRatio'])

def viscosityFit(gas: dict) -> dict:

    '''

    The power-law viscosity `solveBoundaryLayer` takes, fitted to CEA's chamber and exit values.

    Two points fix the two constants. The throat value is the check: it falls between them in
    temperature and the fit has to return it.

    Returns:
    --------
    dict : viscosityReference [Pa-s], viscosityTemperature [K] and viscosityExponent [-], the
        keyword arguments `solveBoundaryLayer` takes

    '''

    chamberViscosity, exitViscosity = gas['viscosity']['chamber'], gas['viscosity']['exit']
    chamberTemperature, exitTemperature = gas['temperature']['chamber'], gas['temperature']['exit']
    exponent = math.log(chamberViscosity / exitViscosity) / math.log(chamberTemperature / exitTemperature)

    return {'viscosityReference': chamberViscosity, 'viscosityTemperature': chamberTemperature,
            'viscosityExponent': exponent}

_wallEnthalpyCache = {}

def wallEnthalpy(pointName, wallTemperature: float, frozen: bool = False) -> float:

    '''

    Enthalpy of the combustion gas brought to the wall temperature [J/kg].

    The enthalpy of an ideal-gas mixture depends only on its temperature and composition, so CEA
    supplies it by expanding the chamber gas until it reaches the wall temperature: an equilibrium
    expansion recombines it on the way, which is the gas a near-equilibrium layer delivers to a
    cold wall, and a frozen expansion keeps the chamber composition. The pressure that expansion
    ends at does not enter.

    Parameters:
    -----------
    pointName : str | dict
        A key of `operatingPoints`, or a point as `operatingPoint` takes it.
    wallTemperature : float
        Wall temperature [K], within roughly 300 to 2400 K.
    frozen : bool
        Chamber composition rather than equilibrium.

    Returns:
    --------
    float : the enthalpy [J/kg], on CEA's reference

    '''

    from scipy.optimize import brentq

    key = (_pointKey(pointName), round(float(wallTemperature), 3), bool(frozen))
    if key not in _wallEnthalpyCache:
        point = operatingPoint(pointName)
        solve = _ceaSolve(point)
        pressurePsia = point['chamberPressure'] / 6894.757
        flag = int(bool(frozen))
        exitTemperature = lambda ratio: solve.ceaObject.get_Temperatures(
            Pc = pressurePsia, MR = point['mixtureRatio'], eps = ratio, frozen = flag)[2] * 5.0 / 9.0
        # The upper bound stays below the area ratios where CEA's expansion stops converging
        ratio = brentq(lambda value: exitTemperature(value) - wallTemperature, 2.0, 2.0e4, xtol = 1e-6)
        enthalpyBtuPerLbm = solve.ceaObject.get_Enthalpies(Pc = pressurePsia, MR = point['mixtureRatio'],
                                                          eps = ratio, frozen = flag)[2]
        _wallEnthalpyCache[key] = enthalpyBtuPerLbm * 2326.0

    return _wallEnthalpyCache[key]

def oneDimensionalEdgeState(location, radius, gas: dict) -> tuple:

    '''

    Isentropic one-dimensional state along a wall, subsonic upstream of its minimum and supersonic
    downstream.

    Parameters:
    -----------
    location, radius : array_like
        The wall [m].
    gas : dict
        From `gasState`.

    Returns:
    --------
    tuple : (Mach number [-], temperature [K], pressure [Pa], velocity [m/s])

    '''

    radius = np.asarray(radius, dtype = float)
    throat = int(np.argmin(radius))
    areaRatio = (radius / radius[throat])**2
    mach = np.array([1.0 if index == throat else
                     machFromAreaRatio(max(float(ratio), 1.0 + 1e-12), gas['gamma'],
                                       branch = 'subsonic' if index < throat else 'supersonic')
                     for index, ratio in enumerate(areaRatio)])
    temperature, pressure, velocity = isentropicValues(mach, gas['stagnationTemperature'],
                                                       gas['chamberPressure'], gas['gamma'],
                                                       gas['gasConstant'])

    return mach, temperature, pressure, velocity

#----------------------------------------------------------------------#
# -- Gas-side models on a wall -- #
#----------------------------------------------------------------------#

def adiabaticWallTemperature(temperature, mach, gamma: float, recoveryFactor: float = 0.89):

    '''

    Recovery temperature, with the recovery factor `solveBoundaryLayer` carries by default.

    '''

    return np.asarray(temperature) * (1.0 + recoveryFactor * 0.5 * (gamma - 1.0) * np.asarray(mach)**2)

def marchedHeatFlux(location, radius, gas: dict, wallTemperature, drivingPotential: str = 'temperature',
                    edgeState: tuple = None, **marchOptions) -> tuple:

    '''

    Wall heat flux from the marched boundary layer.

    The march returns its coefficient as St rho u cp with cp = gamma R / (gamma - 1), and with the
    default potential the flux is that coefficient times T_aw - T_w. The enthalpy potentials keep
    the march's Stanton number and replace cp (T_aw - T_w) with h_aw - h_w, the recovery enthalpy
    less the gas enthalpy at the wall temperature, which is the potential a reacting layer runs
    on. With a uniform wall the march's energy equation sees the potential only through the ratio
    (T_aw - T_w) / (T0 - T_w), which differs from its enthalpy counterpart by under one percent
    here, so the substitution is made on the result.

    Parameters:
    -----------
    location, radius : array_like
        The wall [m], from the injector face.
    gas : dict
        From `gasState`.
    wallTemperature : float | array_like
        Hot-wall temperature [K].
    drivingPotential : str
        'temperature' for cp (T_aw - T_w); 'equilibrium' or 'frozen' for the enthalpy difference
        with the wall gas recombined or at chamber composition.
    edgeState : tuple
        (Mach, temperature, pressure, velocity) at the wall stations. None takes the
        one-dimensional state.
    **marchOptions
        Passed to `solveBoundaryLayer`.

    Returns:
    --------
    tuple : (heat flux [W/m^2], the march's full return dictionary)

    '''

    if edgeState is None:
        edgeState = oneDimensionalEdgeState(location, radius, gas)
    mach, temperature, pressure, velocity = (np.asarray(array, dtype = float) for array in edgeState)
    layer = solveBoundaryLayer(location, radius, mach, temperature, pressure, velocity, gas['gamma'],
                               gas['gasConstant'], wallTemperature = wallTemperature, **marchOptions)
    recoveryFactor = marchOptions.get('recoveryFactor', 0.89)
    coefficient = np.asarray(layer['gasSideCoefficient'])
    wall = np.broadcast_to(np.asarray(wallTemperature, dtype = float), coefficient.shape)

    if drivingPotential == 'temperature':
        recovery = adiabaticWallTemperature(temperature, mach, gas['gamma'], recoveryFactor)
        return coefficient * (recovery - wall), layer

    specificHeat = gas['gamma'] * gas['gasConstant'] / (gas['gamma'] - 1.0)
    frozen = drivingPotential == 'frozen'
    if np.ptp(wall) == 0.0:
        enthalpyAtWall = np.full_like(wall, wallEnthalpy(gas['pointName'], float(wall[0]), frozen))
    else:
        # A wall profile is read off a 25 K grid; the enthalpy is smooth on that scale
        grid = np.arange(25.0 * math.floor(wall.min() / 25.0), 25.0 * math.ceil(wall.max() / 25.0) + 1.0, 25.0)
        gridEnthalpy = np.array([wallEnthalpy(gas['pointName'], value, frozen) for value in grid])
        enthalpyAtWall = np.interp(wall, grid, gridEnthalpy)
    recoveryEnthalpy = gas['chamberEnthalpy'] - (1.0 - recoveryFactor) * 0.5 * velocity**2

    return coefficient / specificHeat * (recoveryEnthalpy - enthalpyAtWall), layer

def bartzHeatFlux(location, radius, gas: dict, wallTemperature, axialModel: str = 'uniform',
                  throatCurvature: float = throatInletCurvature) -> np.ndarray:

    '''

    Wall heat flux from the Bartz correlation as `regenThermal` evaluates it, on a one-dimensional
    edge state, with Bartz's own recovery temperature.

    Parameters:
    -----------
    location, radius : array_like
        The wall [m], from the injector face.
    gas : dict
        From `gasState`.
    wallTemperature : float | array_like
        Hot-wall temperature [K].
    axialModel : str
        'uniform' or 'measured', as `gasSideAxialModel`.
    throatCurvature : float
        Upstream throat radius of curvature over the throat radius [-], which Bartz carries as
        (D_t / R_c)^0.1.

    Returns:
    --------
    numpy.ndarray : heat flux [W/m^2]

    '''

    location = np.asarray(location, dtype = float)
    radius = np.asarray(radius, dtype = float)
    wall = np.broadcast_to(np.asarray(wallTemperature, dtype = float), location.shape)
    mach, temperature, _, _ = oneDimensionalEdgeState(location, radius, gas)
    gamma = gas['gamma']
    throat = int(np.argmin(radius))
    throatArea = math.pi * radius[throat]**2
    curvature = throatCurvature * radius[throat]
    prandtl = 4.0 * gamma / (9.0 * gamma - 5.0)

    flux = np.zeros_like(location)
    for index in range(location.size):
        localArea = math.pi * radius[index]**2
        coefficient = bartzHeatTransferCoefficient(
            temperature[index], mach[index], gamma, gas['gasConstant'], gas['molecularWeight'],
            wall[index], gas['chamberPressure'], gas['characteristicVelocity'],
            2.0 * radius[throat], curvature, throatArea, localArea)
        if axialModel == 'measured':
            coefficient *= measuredAxialFactor(localArea / throatArea, index < throat)
        recovery = gas['stagnationTemperature'] * (1.0 + prandtl**(1.0 / 3.0) * 0.5 * (gamma - 1.0) * mach[index]**2) \
                   / (1.0 + 0.5 * (gamma - 1.0) * mach[index]**2)
        flux[index] = coefficient * (recovery - wall[index])

    return flux

#----------------------------------------------------------------------#
# -- Scorecard -- #
#----------------------------------------------------------------------#

def peakPosition(location, heatFlux, window: tuple = (0.25, 0.45), fraction: float = 0.95) -> float:

    '''

    Centroid of the region within a fraction of the maximum, on a uniform resampling.

    Resampling first makes a finely drawn model and a sparsely measured profile answer the same
    question: where the high region sits, rather than which single point happens to be highest.

    Returns:
    --------
    float : the peak position [m]

    '''

    grid = np.arange(window[0], window[1], 5e-4)
    sampled = np.interp(grid, location, heatFlux)

    return float(grid[sampled >= fraction * sampled.max()].mean())

def _branchValue(location, radius, heatFluxAtWall, areaRatio: float, subsonic: bool) -> float:

    '''

    Heat flux at an area ratio on one branch of a wall, interpolated in area ratio.

    '''

    radius = np.asarray(radius, dtype = float)
    heatFluxAtWall = np.asarray(heatFluxAtWall, dtype = float)
    throat = int(np.argmin(radius))
    ratios = (radius / radius[throat])**2
    if subsonic:
        ratios, values = ratios[:throat + 1][::-1], heatFluxAtWall[:throat + 1][::-1]
    else:
        ratios, values = ratios[throat:], heatFluxAtWall[throat:]
    if areaRatio > ratios.max():
        return float('nan')

    return float(np.interp(areaRatio, ratios, values))

def scorecard(location, heatFlux, wallLocation, wallRadius) -> dict:

    '''

    A model's heat flux held against the measurement.

    Parameters:
    -----------
    location, heatFlux : array_like
        The model's profile [m from the injector face], [W/m^2].
    wallLocation, wallRadius : array_like
        The wall the model ran on [m], which sets the model's area ratios.

    Returns:
    --------
    dict : the scorecard entries described in the module docstring, plus 'stations', the relative
        error at each of `reportStations`

    '''

    location = np.asarray(location, dtype = float)
    heatFlux = np.asarray(heatFlux, dtype = float)
    measuredLocation, measuredHeatFlux = measuredProfile()
    referenceLocation, referenceRadius = rpaContour()

    modelAtStations = np.interp(measuredLocation, location, heatFlux)
    relative = modelAtStations / measuredHeatFlux - 1.0
    inBarrel = (measuredLocation >= barrelWindow[0]) & (measuredLocation <= barrelWindow[1])
    inRms = (measuredLocation >= rmsWindow[0]) & (measuredLocation <= rmsWindow[1])
    inWindow = (location >= 0.25) & (location <= 0.45)

    # Each profile on its own wall: the model's on the wall it ran on, the measurement's on RPA's
    modelOnWall = np.interp(wallLocation, location, heatFlux)
    measuredOnWall = np.interp(referenceLocation, measuredLocation, measuredHeatFlux,
                               left = np.nan, right = np.nan)

    def slope(onWall, wallX, wallR) -> float:
        return _branchValue(wallX, wallR, onWall, slopeRatios[0], True) \
               / _branchValue(wallX, wallR, onWall, slopeRatios[1], True)

    def asymmetry(onWall, wallX, wallR) -> list:
        return [_branchValue(wallX, wallR, onWall, ratio, False)
                / _branchValue(wallX, wallR, onWall, ratio, True) for ratio in matchedRatios]

    barrelError = float(relative[inBarrel].mean())
    throatError = float(np.interp(throatLocation, location, heatFlux)
                        / np.interp(throatLocation, measuredLocation, measuredHeatFlux) - 1.0)

    return {
        'barrelError':       barrelError,
        'throatToBarrelError': (1.0 + throatError) / (1.0 + barrelError) - 1.0,
        'peakError':         float(heatFlux[inWindow].max() / measuredHeatFlux.max() - 1.0),
        'peakLocationError': 1e3 * (peakPosition(location, heatFlux)
                                    - peakPosition(measuredLocation, measuredHeatFlux)),
        'throatError':       throatError,
        'convergingSlope':   {'model': slope(modelOnWall, wallLocation, wallRadius),
                              'measured': slope(measuredOnWall, referenceLocation, referenceRadius)},
        'asymmetry':         {'model': asymmetry(modelOnWall, wallLocation, wallRadius),
                              'measured': asymmetry(measuredOnWall, referenceLocation, referenceRadius)},
        'rmsError':          float(np.sqrt(np.mean(relative[inRms]**2))),
        'stations':          {station: float(np.interp(station, location, heatFlux)
                                             / np.interp(station, measuredLocation, measuredHeatFlux) - 1.0)
                              for station in reportStations},
    }

def formatScorecard(card: dict, label: str = '') -> str:

    '''

    One scorecard as a few lines of text.

    '''

    slope, asym = card['convergingSlope'], card['asymmetry']
    lines = [
        f'{label}',
        f'  barrel {100*card["barrelError"]:+6.1f} %   throat/barrel {100*card["throatToBarrelError"]:+6.1f} %   '
        f'peak {100*card["peakError"]:+6.1f} %   '
        f'peak at {card["peakLocationError"]:+6.1f} mm   throat {100*card["throatError"]:+6.1f} %   '
        f'rms {100*card["rmsError"]:5.1f} %',
        f'  converging slope {slope["model"]:.2f} (measured {slope["measured"]:.2f})   asymmetry '
        + '  '.join(f'{ratio:.1f}: {m:.2f} ({x:.2f})' for ratio, m, x in zip(matchedRatios, asym['model'], asym['measured'])),
        '  stations ' + '  '.join(f'{1e3*station:.0f}: {100*error:+.0f}%' for station, error in card['stations'].items()),
    ]

    return '\n'.join(lines)

#----------------------------------------------------------------------#
# -- The chamber as a NOVA nozzle -- #
#----------------------------------------------------------------------#

def novaCaseConfig(pointName: str = 'measured', overrides: dict = None) -> dict:

    '''

    The configuration that builds this chamber as a NOVA nozzle.

    NOVA sizes the throat from mass flow and CEA's characteristic velocity, so the delivered throat
    lands within a few tenths of a millimetre of 42.05 mm rather than on it. The converging section
    is NOVA's 30 degree cone with 1.5 throat-radius arcs, which lies on RPA's wall to within its
    digitization. The diverging section is NOVA's truncated ideal contour at an 80 percent length
    fraction. L' is injector face to throat, so the barrel is L' less the cone's run.

    Parameters:
    -----------
    pointName : str
        A key of `operatingPoints`.
    overrides : dict
        Configuration keys to set after the case's own.

    Returns:
    --------
    dict : a full NOVA configuration

    '''

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, '..', 'src', 'NOVA', 'assets', 'NOVANozzle.json'), encoding = 'utf-8') as handle:
        config = json.load(handle)

    point = operatingPoints[pointName]
    chamberRadius = throatRadius * math.sqrt(contractionRatio)
    convergingAngle = 30.0
    barrel = throatLocation - (chamberRadius - throatRadius) / math.tan(math.radians(convergingAngle))
    config.update({
        'chamberDiameter': 2.0 * chamberRadius, 'convergingSectionAngle': convergingAngle,
        'Lstar': None, 'chamberLength': barrel, 'divergingSectionType': 'tic', 'lengthFraction': 0.8,
        'expansionRatio': expansionRatio, 'targetExitPressure': None,
        'OFRatio': point['mixtureRatio'], 'chamberPressure': point['chamberPressure'],
        'thrust': None, 'engineMassFlow': point['massFlow'], 'Fuel': 'LH2', 'Oxidizer': 'LOX',
        'regenTruncationType': 'none', 'regenTruncationValue': None, 'makeCoolingChannels': False,
        'filmCooling': False, 'makeRadiativeExtension': False, 'makeInletVolute': False,
        'makeOutletVolute': False, 'plumeAmbientPressure': None, 'plotsEnabled': False,
        'export': False, 'filename': f'calorimeter40k_{pointName}',
    })
    config.update(overrides or {})

    return config

def buildNovaCase(pointName: str, outputFolder: str, overrides: dict = None):

    '''

    Build the chamber as a NOVA nozzle. Takes most of a minute, for the characteristics solve.

    Parameters:
    -----------
    pointName : str
        A key of `operatingPoints`.
    outputFolder : str
        Where the run writes its configuration and outputs.
    overrides : dict
        Configuration keys to set after the case's own.

    Returns:
    --------
    NOVA.Nozzle : the built nozzle

    '''

    from NOVA import Nozzle

    os.makedirs(outputFolder, exist_ok = True)
    path = os.path.join(outputFolder, f'calorimeter40k_{pointName}.json')
    with open(path, 'w', encoding = 'utf-8') as handle:
        json.dump(novaCaseConfig(pointName, overrides), handle, indent = 2)

    # The showcase scripts' override, put back afterwards so the caller's process is unchanged
    original = Nozzle._getOutputRoot
    Nozzle._getOutputRoot = lambda self, _base = outputFolder: _base
    try:
        nozzle = Nozzle()
        nozzle.generateNozzle(configPath = path)
    finally:
        Nozzle._getOutputRoot = original

    return nozzle
