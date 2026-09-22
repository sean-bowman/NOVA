'''

Comparison of the regenerative thermal model against Carlile and Quentmeyer, NASA TM-105679 (1992).

Carlile and Quentmeyer fired three cylindrical OFHC copper chambers, 6.60 cm inside diameter with a
0.089 cm hot wall, on GH2 and LOX at 4.136 MPa and a mixture ratio of 6.0, cooled by liquid
hydrogen in straight axial channels of throat aspect ratio 0.75, 1.50 and 5.00 (their Table 1). They
report the hot-gas wall temperature at the throat against coolant mass flux (their Fig. 12) and
state that the baseline chamber runs a 778 K wall at a throat heat flux of about 97.1 MW/m^2.

What is compared is the wall and coolant side at one station: the rectangular section, the rib as a
fin, the conduction through the wall sector, and the Gnielinski coefficient on the hydraulic
diameter. The gas side is not predicted. Its coefficient is fixed from the paper's own operating
point, h_g = 97.1 MW/m^2 / (T_aw - 778 K), and held for every point, so the gas-side heat flux
follows the wall temperature the model predicts.

----------------------------------------------------------------------
                        Unknowns, bracketed
----------------------------------------------------------------------

The paper does not give the coolant state at the throat, the adiabatic wall temperature or the
channel roughness. Each is bracketed and every point is reported as a predicted band:

    coolant bulk temperature   30 K inlet plus a pickup of 10 to 70 K at 0.841 kg/s, scaled with
                               the inverse of the flow, since the heat taken up upstream of the
                               throat is roughly fixed
    coolant pressure           6 to 12 MPa, supercritical, around a 4.136 MPa pressure drop
    adiabatic wall temperature 3000 to 3400 K
    throat heat flux           97.1 MW/m^2 plus or minus 10 percent
    channel roughness          0.8 to 3.2 um, machined copper

The measured temperatures are digitized from Fig. 12 to within 10 K, against its axis ticks; each
point's mass flux matches a coolant flow stated in the text to within one percent, and the stated
flow is used.

----------------------------------------------------------------------
                        Acceptance, stated before the first run
----------------------------------------------------------------------

  A. At every point run at 0.7 kg/s or more, the predicted T_hw - T_b is within 20 percent of the
     measured one over the whole bracket.
  B. The difference between the 0.75 and the 5.00 aspect ratio walls at the baseline's mass flux,
     5410 kg/s/m^2, is predicted within 30 percent. The unknowns act on both chambers alike, so
     this cancels most of them and tests the fin and hydraulic diameter physics directly.

A criterion is met when its whole band lies inside its tolerance, and it counts as a validation
only when the band is also narrower than half the tolerance; a band wider than that is a
sensitivity-bounded comparison.

----------------------------------------------------------------------
                        Disclosed
----------------------------------------------------------------------

  - The paper's wall temperatures are not measured directly. They are a SINDA conduction model's
    hot-wall node, fitted to thermocouples in the ribs and the backside, with coolant-side
    coefficients on the sides and roof of the channel adjusted to fit.
  - The reported temperature is the hottest point, on the channel centerline. The model's is one
    wall temperature for the whole channel sector, which is cooler than the centerline between
    the ribs, most for the wide channels of the baseline.
  - The passages are straight: the comparison says nothing about the helical layout.
  - The coolant correlation carries no wall-to-bulk property ratio correction, which hydrogen at
    these temperature ratios is known to need, and no account of thermal stratification in a
    tall channel.

Author: Sean Bowman

'''

import itertools

import numpy as np
import pytest
from scipy.interpolate import interp1d

from NOVA.channelSections import sectionProperties
from NOVA.fluidProperties import fluidProps
from NOVA.materials import wallMaterialCurves
from NOVA.regenThermal import coolantFrictionAndNusselt, solveStationWallTemperature

# -- The chambers, Table 1 and the test section description -- #
chamberRadius = 0.0330       # [m], 6.60 cm inside diameter
wallThickness = 0.089e-2     # [m]

configurations = {
    0.75: dict(count = 72,  depth = 0.127e-2, width = 0.170e-2),
    1.50: dict(count = 100, depth = 0.152e-2, width = 0.102e-2),
    5.00: dict(count = 400, depth = 0.127e-2, width = 0.0254e-2),
}

# -- The operating point the gas side is fixed from -- #
anchorHeatFlux, anchorWallTemperature = 97.1e6, 778.0   # [W/m^2], [K]

# -- Fig. 12, digitized: (aspect ratio, coolant flow from the text [kg/s], hot-gas wall [K]) -- #
measured = [
    (0.75, 0.841, 768.1),
    (1.50, 0.909, 701.0), (1.50, 0.841, 729.6), (1.50, 0.773, 756.8),
    (5.00, 0.714, 492.5), (5.00, 0.641, 508.4), (5.00, 0.600, 517.7), (5.00, 0.559, 527.0),
    (5.00, 0.495, 545.6), (5.00, 0.400, 577.5), (5.00, 0.314, 618.7), (5.00, 0.255, 657.2),
    (5.00, 0.182, 726.9),
]
digitization = 10.0   # [K]

# -- The brackets -- #
inletTemperature = 30.0                        # [K]
referenceFlow    = 0.841                       # [kg/s]
pickups          = (10.0, 40.0, 70.0)          # [K] at the reference flow
pressures        = (6.0e6, 12.0e6)             # [Pa]
adiabaticWalls   = (3000.0, 3400.0)            # [K]
heatFluxScales   = (0.9, 1.0, 1.1)
roughnesses      = (0.8e-6, 3.2e-6)            # [m]

def flowArea(aspectRatio):

    '''Total coolant flow area at the throat [m^2].'''

    configuration = configurations[aspectRatio]
    return configuration['count'] * configuration['depth'] * configuration['width']

def copperConductivity():

    '''OFHC copper conductivity against temperature, clamped at the ends of its data.'''

    curves = wallMaterialCurves('OFHC Copper')
    return interp1d(curves['temperatureK'], curves['thermalConductivity'], bounds_error = False,
                    fill_value = (curves['thermalConductivity'][0], curves['thermalConductivity'][-1]))

def bulkTemperature(coolantFlow, pickup):

    '''Coolant bulk temperature at the throat for a pickup stated at the reference flow [K].'''

    return inletTemperature + pickup * referenceFlow / coolantFlow

def predictedWallTemperature(aspectRatio, coolantFlow, pickup, pressure, adiabaticWall,
                             heatFluxScale, roughness, conductivity = None):

    '''The station solve for one chamber at one point of the bracket [K].'''

    configuration = configurations[aspectRatio]
    count, depth, width = configuration['count'], configuration['depth'], configuration['width']
    rib = 2 * np.pi * (chamberRadius + wallThickness) / count - width

    section = sectionProperties('rectangular', np.array([depth / 2]), width = np.array([width]),
                                cornerRadius = 0.0, ribThickness = rib)
    diameter = float(section.hydraulicDiameter[0])

    bulk = bulkTemperature(coolantFlow, pickup)
    density, viscosity, specificHeat, thermalConductivity, prandtl = \
        fluidProps('Hydrogen', 'TP', 'D VIS Cp TCX PRANDTL', bulk, pressure)

    massFlux = coolantFlow / flowArea(aspectRatio)
    reynolds = massFlux * diameter / viscosity
    _, nusselt = coolantFrictionAndNusselt(reynolds, prandtl, diameter, surfaceRoughness = roughness)

    gasCoefficient = heatFluxScale * anchorHeatFlux / (adiabaticWall - anchorWallTemperature)
    length = 1.0e-3   # [m], cancels

    solution = solveStationWallTemperature(
        drivingTemperature = adiabaticWall, gasStaticTemperature = adiabaticWall,
        gasMachNumber = 1.0, gasGamma = 1.2, gasConstant = 700.0, gasMolecularWeight = 12.0,
        coolantTemperature = bulk, coolantThermalConductivity = thermalConductivity,
        coolantNusseltNumber = nusselt, coolantSpecificHeat = specificHeat,
        coolantMassFlow = coolantFlow / count, hydraulicDiameter = diameter,
        coolantWettedArea = float(section.heatedPerimeter[0]) * length,
        hotWallArea = 2 * np.pi * chamberRadius / count * length,
        hotWallThickness = wallThickness, wallRadius = chamberRadius, pathLength = length,
        conductivityInterpolator = conductivity or copperConductivity(),
        chamberPressure = 4.136e6, characteristicVelocity = 2300.0, throatDiameter = 0.066,
        throatRadiusOfCurvature = 0.066, throatArea = np.pi * chamberRadius**2,
        localArea = np.pi * chamberRadius**2,
        finHeight = float(section.finHeight[0]), finThickness = float(section.finThickness[0]),
        prescribedGasCoefficient = gasCoefficient)

    if not solution.converged:
        raise RuntimeError(f'Station did not converge at aspect ratio {aspectRatio}, {coolantFlow} kg/s')

    return solution.hotWallTemperature

def bracket():

    '''Every combination of the unknowns.'''

    return list(itertools.product(pickups, pressures, adiabaticWalls, heatFluxScales, roughnesses))

def interpolatedMeasurement(aspectRatio, massFlux):

    '''The measured wall of one chamber at a mass flux between two of its points [K].'''

    points = sorted((flow / flowArea(aspectRatio), wall) for ratio, flow, wall in measured
                    if ratio == aspectRatio)
    fluxes, walls = zip(*points)
    return float(np.interp(massFlux, fluxes, walls))

def compareAgainstCarlile():

    '''Every point's predicted band, and the difference criterion's.'''

    conductivity = copperConductivity()
    combinations = bracket()

    points = []
    for aspectRatio, coolantFlow, wall in measured:
        errors, walls = [], []
        for pickup, pressure, adiabaticWall, scale, roughness in combinations:
            predicted = predictedWallTemperature(aspectRatio, coolantFlow, pickup, pressure,
                                                 adiabaticWall, scale, roughness, conductivity)
            driving = wall - bulkTemperature(coolantFlow, pickup)
            walls.append(predicted)
            errors.extend([(predicted - (wall + sign * digitization)) / (driving + sign * digitization)
                           for sign in (-1, 1)])
        points.append(dict(aspectRatio = aspectRatio, coolantFlow = coolantFlow, measured = wall,
                           predictedLow = min(walls), predictedHigh = max(walls),
                           errorLow = min(errors), errorHigh = max(errors)))

    # The difference at the baseline's mass flux, with the same unknowns on both chambers
    massFlux = 0.841 / flowArea(0.75)
    measuredDifference = interpolatedMeasurement(0.75, massFlux) - interpolatedMeasurement(5.00, massFlux)
    differences = []
    for pickup, pressure, adiabaticWall, scale, roughness in combinations:
        low  = predictedWallTemperature(0.75, massFlux * flowArea(0.75), pickup, pressure,
                                        adiabaticWall, scale, roughness, conductivity)
        high = predictedWallTemperature(5.00, massFlux * flowArea(5.00), pickup, pressure,
                                        adiabaticWall, scale, roughness, conductivity)
        differences.append(low - high)
    spread = np.hypot(digitization, digitization)
    differenceErrors = [(difference - (measuredDifference + sign * spread)) / measuredDifference
                        for difference in differences for sign in (-1, 1)]

    return dict(points = points, massFlux = massFlux, measuredDifference = measuredDifference,
                differenceLow = min(differences), differenceHigh = max(differences),
                differenceErrorLow = min(differenceErrors), differenceErrorHigh = max(differenceErrors))

@pytest.fixture(scope = 'module')
def comparison():

    return compareAgainstCarlile()

def classify(errorLow, errorHigh, tolerance):

    '''Validated, consistent, inconclusive or missed, by the rule stated before the first run.'''

    if -tolerance <= errorLow and errorHigh <= tolerance:
        return 'validated' if (errorHigh - errorLow) / 2 < tolerance / 2 else 'consistent'
    if errorHigh < -tolerance or errorLow > tolerance:
        return 'missed'
    return 'inconclusive'

class TestCarlileQuentmeyer:

    '''

    The outcome, recorded in docs/reports/carlileQuentmeyer_2026-09-22.md: a sensitivity-bounded
    comparison. Every measurement lies inside its predicted band, and neither criterion is met as
    stated, because the bracketed roughness of the machined channels alone moves the prediction
    by more than either tolerance. These tests hold that outcome, so a change to the model that
    moves it fails here and the report is rewritten with it.

    '''

    def testEveryMeasurementLiesInsideItsPredictedBand(self, comparison):

        for point in comparison['points']:
            assert point['predictedLow'] - digitization <= point['measured'] <= point['predictedHigh'] + digitization, point

        measured = comparison['measuredDifference']
        assert comparison['differenceLow'] <= measured <= comparison['differenceHigh']

    def testNeitherCriterionIsMetAsStated(self, comparison):

        highFlow = [point for point in comparison['points'] if point['coolantFlow'] >= 0.7]
        assert len(highFlow) == 5
        for point in highFlow:
            assert classify(point['errorLow'], point['errorHigh'], 0.20) == 'inconclusive', point

        assert classify(comparison['differenceErrorLow'], comparison['differenceErrorHigh'], 0.30) \
               == 'inconclusive'

    def testTheHighAspectRatioChamberRunsCoolerEverywhereInTheBracket(self, comparison):

        assert comparison['differenceLow'] > 0.0

    def testTheWallRisesAsTheFlowFalls(self):

        conductivity = copperConductivity()
        flows = sorted((flow for ratio, flow, _ in measured if ratio == 5.00), reverse = True)
        walls = [predictedWallTemperature(5.00, flow, 40.0, 9.0e6, 3200.0, 1.0, 1.6e-6, conductivity)
                 for flow in flows]

        assert all(later > earlier for earlier, later in zip(walls, walls[1:])), walls
