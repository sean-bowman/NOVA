'''

Tests for the 40k calorimeter case in `calorimeter40kCase.py`.

Three kinds. The digitized data is checked against what its own figures and tables state
independently of the digitization: the second axes of the measurement figures, and the hardware
table for RPA's wall. The scorecard and the recovered wall temperature are checked against what
must hold whatever the models do. And the scorecards of the gas-side models as they stand are
pinned.

**The pinned scorecards are a regression, not an agreement threshold.** They record where each
model sits against the measurement so that a change to the model shows up as a change here, with
its size. None of them is a statement that the model is good enough.

'''

import numpy as np
import pytest

import calorimeter40kCase as case

@pytest.fixture(scope = 'module')
def gas():
    return case.gasState('measured')

@pytest.fixture(scope = 'module')
def wall():
    return case.rpaContour()

@pytest.fixture(scope = 'module')
def wallTemperature(gas, wall):
    return case.reductionWallTemperature(wall[0], gas)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The digitized data against what the sources state -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testEveryCoolantCircuitIsRead():
    '''The calorimeter had 58 water circuits, and both figures give one marker for each, in axial order.'''
    data = np.asarray(case.measuredData)
    assert data.shape == (58, 3)
    assert np.all(np.diff(data[:, 0]) > 0.0)

def testTheUnitConversionsMatchTheFiguresOwnSecondAxes():
    '''
    Fig. 11 carries kW/m^2 on its right axis with 90 000 on the 55 BTU/s-in^2 gridline, and Fig. 12
    carries kW/m^2-K with 55 at 0.01868 BTU/in^2-s-F. Both are independent statements of the
    conversions the case carries.
    '''
    assert 55.0 * case.btuPerSquareInchSecond == pytest.approx(90.0e6, rel = 2e-3)
    assert 55.0e3 / case.btuPerSquareInchSecondF == pytest.approx(0.018685, rel = 1e-3)

def testTheMeasuredPeakIsAPlateauUpstreamOfTheThroat():
    '''
    The highest marker is about 93.3 MW/m^2 at 0.76 cm ahead of the throat, and the region within
    5 percent of it is centred about 17 mm ahead: the measurement does not peak at the throat.
    '''
    location, heatFlux = case.measuredProfile()
    assert heatFlux.max() == pytest.approx(93.3e6, rel = 5e-3)
    assert 0.330 < case.peakPosition(location, heatFlux) < 0.345

def testRpasWallIsTheHardwaresSize():
    '''
    Dexter's Table 1 gives an 84.1 mm throat, a contraction ratio of 2.92 and an expansion ratio of
    7. The wall read off RPA's figure, before any scaling, has to return all three to within what
    one pixel of radius allows.
    '''
    location, radius = case.rpaContour(scaledThroatRadius = None, alignThroat = False)
    throat = radius.min()
    assert throat == pytest.approx(0.04205, rel = 0.01)
    assert (np.interp(0.150, location, radius) / throat)**2 == pytest.approx(case.contractionRatio, rel = 0.02)
    assert (radius[-1] / throat)**2 == pytest.approx(case.expansionRatio, rel = 0.03)

def testScalingTheWallKeepsItsAreaRatios():
    '''Radial scaling onto the hardware throat moves no area ratio, which is why it is allowed.'''
    _, digitized = case.rpaContour(scaledThroatRadius = None, alignThroat = False)
    _, scaled = case.rpaContour(alignThroat = False)
    assert scaled.min() == pytest.approx(case.throatRadius, rel = 1e-12)
    assert (scaled / scaled.min())**2 == pytest.approx((digitized / digitized.min())**2, rel = 1e-12)

def testTheDigitizedFluxCarriesTheTestsHeatLoad(wall):
    '''
    Dexter gives Test 024's total heat load as 9079 kW. The digitized flux, with each circuit
    assigned the wall between the midpoints to its neighbours on RPA's wall, has to carry it to
    within what the unknown circuit boundaries allow: 3 percent.
    '''
    stations, heatFlux = case.measuredProfile()
    location, radius = wall
    edges = np.concatenate(([1.5 * stations[0] - 0.5 * stations[1]], 0.5 * (stations[1:] + stations[:-1]),
                            [1.5 * stations[-1] - 0.5 * stations[-2]]))
    fine = np.linspace(edges[0], edges[-1], 20001)
    fineRadius = np.interp(fine, location, radius)
    ringArea = 2.0 * np.pi * 0.5 * (fineRadius[1:] + fineRadius[:-1]) * np.hypot(np.diff(fine), np.diff(fineRadius))
    circuitArea = np.diff(np.interp(edges, fine, np.concatenate(([0.0], np.cumsum(ringArea)))))
    assert np.sum(heatFlux * circuitArea) == pytest.approx(9079.0e3, rel = 0.03)

def testTheWallsThroatIsOnRpasMarker(wall):
    '''Aligned, the minimum radius lands within half a station of the throat the measurement uses.'''
    location, radius = wall
    assert abs(location[np.argmin(radius)] - case.throatLocation) < 1.25e-3

def testRpasPredictedPeak():
    '''RPA's own curve peaks near 95.5 MW/m^2 at the throat, as the figure draws it.'''
    location, heatFlux = case.rpaHeatFlux()
    assert heatFlux.max() == pytest.approx(95.5e6, rel = 0.01)
    assert abs(location[np.argmax(heatFlux)] - case.throatLocation) < 5e-3

#--------------------------------------------------------------------------------------------------------------------------#
# -- The reduction's wall temperature -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheReductionsWallHoldsItsCapThroughTheThroat(gas):
    '''
    The reduction capped the hot wall at the water's saturation temperature plus 283 K, so the
    recovered wall has to flatten where the flux is highest: within 60 K over the 26 mm ahead of
    the throat, at a level between 840 and 900 K.
    '''
    stations = np.linspace(0.330, 0.356, 14)
    wall = case.reductionWallTemperature(stations, gas)
    assert np.ptp(wall) < 60.0
    assert 840.0 < wall.mean() < 900.0

def testTheReductionsWallStaysAboveTheWaterDownstream(gas):
    '''
    With the frozen Prandtl number in the recovery factor the recovered wall past the throat sits
    at or above the water feeding it without being held there, which the equilibrium value does
    not manage. That is why the frozen reading is the one carried.
    '''
    stations, heatFlux = case.measuredProfile()
    _, coefficient = case.measuredCoefficient()
    downstream = stations > 0.37
    frozenWall = (case.reductionRecoveryTemperature(stations, gas, 'frozen') - heatFlux / coefficient)[downstream]
    equilibriumWall = (case.reductionRecoveryTemperature(stations, gas, 'equilibrium') - heatFlux / coefficient)[downstream]
    assert np.all(frozenWall > case.waterTemperature - 30.0)
    assert np.any(equilibriumWall < case.waterTemperature - 50.0)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The edge state and the scorecard -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheOneDimensionalStateIsSonicAtTheThroatAndConservesMass(gas, wall):
    '''Subsonic upstream, supersonic downstream, and the same mass flow through every station.'''
    location, radius = wall
    mach, temperature, pressure, velocity = case.oneDimensionalEdgeState(location, radius, gas)
    throat = int(np.argmin(radius))
    assert mach[throat] == 1.0
    assert np.all(mach[:throat] < 1.0) and np.all(mach[throat + 1:] > 1.0)
    massFlow = pressure / (gas['gasConstant'] * temperature) * velocity * np.pi * radius**2
    assert massFlow == pytest.approx(massFlow[throat], rel = 1e-6)

def testTheMeasurementScoresZeroAgainstItself(wall):
    '''
    The measurement handed in as a model has to score no error anywhere, and its slope and
    asymmetry have to equal the measured ones exactly.
    '''
    location, radius = wall
    measuredLocation, measuredHeatFlux = case.measuredProfile()
    inside = (location >= measuredLocation.min()) & (location <= measuredLocation.max())
    card = case.scorecard(measuredLocation, measuredHeatFlux, location[inside], radius[inside])
    assert card['barrelError'] == pytest.approx(0.0, abs = 1e-12)
    assert card['throatError'] == pytest.approx(0.0, abs = 1e-12)
    assert card['rmsError'] == pytest.approx(0.0, abs = 1e-12)
    assert card['peakError'] == pytest.approx(0.0, abs = 1e-12)
    assert card['peakLocationError'] == pytest.approx(0.0, abs = 1e-9)
    assert card['convergingSlope']['model'] == pytest.approx(card['convergingSlope']['measured'], rel = 1e-9)
    assert card['asymmetry']['model'] == pytest.approx(card['asymmetry']['measured'], rel = 1e-9)

def testTheMeasurementIsFlatterThroughTheConvergenceThanMassFluxScaling(wall):
    '''
    The measured flux at an area ratio of 1.05 is 1.32 times that at 2.5. Mass flux per unit area
    alone, raised to 0.8, gives 2.0. Every model built on mass-flux scaling has to overshoot this.
    '''
    location, radius = wall
    card = case.scorecard(*case.measuredProfile(), location, radius)
    assert card['convergingSlope']['measured'] == pytest.approx(1.32, abs = 0.02)
    assert (case.slopeRatios[1] / case.slopeRatios[0])**0.8 > 1.9

#--------------------------------------------------------------------------------------------------------------------------#
# -- Where the models stand: pinned, not judged -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testMarchedLayerScorecard(gas, wall, wallTemperature):
    '''
    The marched boundary layer with its default closure, the energy-thickness Stanton law, on RPA's
    wall with a one-dimensional edge state, on the reduction's wall temperature.
    '''
    location, radius = wall
    heatFlux, _ = case.marchedHeatFlux(location, radius, gas, wallTemperature)
    card = case.scorecard(location, heatFlux, location, radius)
    assert card['barrelError'] == pytest.approx(-0.1389, abs = 2e-3)
    assert card['throatToBarrelError'] == pytest.approx(0.1049, abs = 2e-3)
    assert card['peakError'] == pytest.approx(-0.1112, abs = 2e-3)
    assert card['throatError'] == pytest.approx(-0.0486, abs = 2e-3)
    assert card['peakLocationError'] == pytest.approx(14.5, abs = 1.0)
    assert card['convergingSlope']['model'] == pytest.approx(1.855, abs = 5e-3)
    assert card['asymmetry']['model'] == pytest.approx([0.992, 1.081, 0.992], abs = 5e-3)
    assert card['rmsError'] == pytest.approx(0.6314, abs = 5e-3)

def testMarchedLayerScorecardUnderBartzsInteraction(gas, wall, wallTemperature):
    '''
    The same march under Bartz's thickness interaction exponent of 0.1, which TN D-2832 ranks below
    the default and which runs the throat a third high against the barrel here.
    '''
    location, radius = wall
    heatFlux, _ = case.marchedHeatFlux(location, radius, gas, wallTemperature, thicknessInteractionExponent = 0.1)
    card = case.scorecard(location, heatFlux, location, radius)
    assert card['barrelError'] == pytest.approx(-0.1336, abs = 2e-3)
    assert card['throatToBarrelError'] == pytest.approx(0.3485, abs = 2e-3)
    assert card['peakError'] == pytest.approx(0.0909, abs = 2e-3)
    assert card['throatError'] == pytest.approx(0.1683, abs = 2e-3)
    assert card['peakLocationError'] == pytest.approx(17.25, abs = 1.0)
    assert card['convergingSlope']['model'] == pytest.approx(2.157, abs = 5e-3)
    assert card['asymmetry']['model'] == pytest.approx([1.036, 1.142, 1.080], abs = 5e-3)
    assert card['rmsError'] == pytest.approx(0.7997, abs = 5e-3)

def testBartzScorecard(gas, wall, wallTemperature):
    '''
    Bartz with one constant along the wall, on the same wall, edge state and wall temperature, with
    the entrant arc RPA's wall was fitted to.
    '''
    location, radius = wall
    heatFlux = case.bartzHeatFlux(location, radius, gas, wallTemperature)
    card = case.scorecard(location, heatFlux, location, radius)
    assert card['barrelError'] == pytest.approx(-0.1041, abs = 2e-3)
    assert card['throatToBarrelError'] == pytest.approx(0.3789, abs = 2e-3)
    assert card['peakError'] == pytest.approx(0.1529, abs = 2e-3)
    assert card['throatError'] == pytest.approx(0.2353, abs = 2e-3)
    assert card['convergingSlope']['model'] == pytest.approx(2.020, abs = 5e-3)
    assert card['asymmetry']['model'] == pytest.approx([1.026, 1.166, 1.125], abs = 5e-3)
    assert card['rmsError'] == pytest.approx(1.0281, abs = 5e-3)
