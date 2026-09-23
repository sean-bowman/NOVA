'''

Tests for the measured axial distribution of the gas-side correlation constant.

Bartz carries one correlation constant along the whole wall. Schacht, Quentmeyer and Jones
measured it at five stations of a LOX/GH2 chamber over 150 to 1000 psia (NASA TN D-2832) and
found it varies: 0.0257 in the cylindrical barrel, 0.0240 through the converging section, 0.0151
at the throat averaged over three circumferential stations, and 0.0153 to 0.0188 downstream. The
same area ratio occurs on both sides of the throat with different constants, so the two branches
are separate.

`measuredAxialFactor` carries the shape of that distribution rather than its absolute level: the
factor is the station constant over the barrel constant, and the barrel constant is within
1 percent of the 0.026 the Bartz form already uses. These tests hold the factor to the measured
stations, to the shape between them, and hold the station solve to leaving the barrel alone while
taking 41 percent off the throat.

Author: Sean Bowman

'''

import numpy as np
import pytest

from NOVA.regenThermal import (MEASUREDAXIALCONSTANTS, MEASUREDBARRELCONSTANT,
                               bartzHeatTransferCoefficient, measuredAxialFactor,
                               solveStationWallTemperature)

class TestMeasuredStations:

    '''The factor reproduces the constant measured at each station.'''

    @pytest.mark.parametrize('branch', ['subsonic', 'supersonic'])
    def testEachStationIsReproduced(self, branch):

        for areaRatio, constant, _ in MEASUREDAXIALCONSTANTS[branch]:
            factor = measuredAxialFactor(areaRatio, subsonic = branch == 'subsonic')

            assert factor == pytest.approx(constant/MEASUREDBARRELCONSTANT, rel = 1e-12)

    def testTheBarrelIsLeftAlone(self):

        # The barrel station is what the absolute level is anchored to
        assert measuredAxialFactor(4.64, subsonic = True) == pytest.approx(1.0, rel = 1e-12)

    def testTheThroatIsTheMinimum(self):

        throat = measuredAxialFactor(1.0, subsonic = True)

        assert throat == pytest.approx(0.0151/0.0257, rel = 1e-12)
        assert throat == pytest.approx(0.588, abs = 0.001)
        assert measuredAxialFactor(1.0, subsonic = False) == pytest.approx(throat, rel = 1e-12)

class TestShape:

    '''Between the stations the constant follows the measured trend.'''

    def testItFallsFromTheBarrelToTheThroat(self):

        ratios = [4.64, 3.0, 2.0, 1.5, 1.2, 1.0]
        factors = [measuredAxialFactor(ratio, subsonic = True) for ratio in ratios]

        assert np.all(np.diff(factors) < 0)

    def testItRisesAgainDownstream(self):

        ratios = [1.0, 1.27, 2.0, 3.33]
        factors = [measuredAxialFactor(ratio, subsonic = False) for ratio in ratios]

        assert np.all(np.diff(factors) > 0)

    def testTheTwoBranchesDifferAtTheSameAreaRatio(self):

        # 1.78 upstream of the throat was measured at 0.0240, while downstream the constant at
        # that area ratio is on its way back up from 0.0151
        assert measuredAxialFactor(1.78, subsonic = True) \
               > measuredAxialFactor(1.78, subsonic = False)

    @pytest.mark.parametrize('areaRatio, subsonic, expected',
                             [(12.0, True, 0.0257), (0.5, True, 0.0151),
                              (0.5, False, 0.0151), (40.0, False, 0.0188)])
    def testOutsideTheMeasuredRangeTheEndValueIsHeld(self, areaRatio, subsonic, expected):

        # Holding the end value rather than extrapolating a trend the data does not cover
        assert measuredAxialFactor(areaRatio, subsonic) \
               == pytest.approx(expected/MEASUREDBARRELCONSTANT, rel = 1e-12)

class TestAgainstTheStationSolve:

    '''The station solve applies the factor where it is asked for and nowhere else.'''

    def station(self, **overrides):

        arguments = {
            'drivingTemperature': 3400.0, 'gasStaticTemperature': 3200.0, 'gasMachNumber': 0.2,
            'gasGamma': 1.15, 'gasConstant': 650.0, 'gasMolecularWeight': 12.8,
            'coolantTemperature': 120.0, 'coolantThermalConductivity': 0.1,
            'coolantNusseltNumber': 400.0, 'coolantSpecificHeat': 14000.0,
            'coolantMassFlow': 3.4/60, 'hydraulicDiameter': 0.003,
            'coolantWettedArea': 5.0e-5, 'hotWallArea': 5.0e-5, 'hotWallThickness': 1.0e-3,
            'wallRadius': 0.09, 'pathLength': 0.01,
            'conductivityInterpolator': lambda temperature: 320.0,
            'chamberPressure': 6.9e6, 'characteristicVelocity': 2340.0,
            'throatDiameter': 0.101, 'throatRadiusOfCurvature': 0.0757,
            'throatArea': np.pi*0.0505**2, 'localArea': np.pi*0.0505**2*4.64,
        }
        arguments.update(overrides)

        return arguments

    def testTheBarrelStationDoesNotMove(self):

        arguments = self.station()
        uniform  = solveStationWallTemperature(**arguments, gasSideAxialModel = 'uniform')
        measured = solveStationWallTemperature(**arguments, gasSideAxialModel = 'measured')

        assert measured.exhaustConvectiveCoefficient \
               == pytest.approx(uniform.exhaustConvectiveCoefficient, rel = 1e-12)
        assert measured.hotWallTemperature == pytest.approx(uniform.hotWallTemperature, rel = 1e-12)

    def testTheThroatCoefficientIsTheFactorTimesBartz(self):

        arguments = self.station(localArea = np.pi*0.0505**2, gasMachNumber = 1.0)
        # Converged hard, so the wall temperature the coefficient was evaluated at and the one
        # handed back are the same number to well within the comparison below
        measured = solveStationWallTemperature(**arguments, gasSideAxialModel = 'measured',
                                               tolerance = 1e-10, maximumIterations = 200)

        # At the wall temperature the solve landed on, the coefficient is Bartz times the factor
        atConvergedWall = bartzHeatTransferCoefficient(
            arguments['gasStaticTemperature'], arguments['gasMachNumber'], arguments['gasGamma'],
            arguments['gasConstant'], arguments['gasMolecularWeight'], measured.hotWallTemperature,
            arguments['chamberPressure'], arguments['characteristicVelocity'],
            arguments['throatDiameter'], arguments['throatRadiusOfCurvature'],
            arguments['throatArea'], arguments['localArea'])

        assert measured.exhaustConvectiveCoefficient \
               == pytest.approx(atConvergedWall*measuredAxialFactor(1.0, subsonic = False), rel = 1e-9)

    def testTheBoundaryLayerCorrectionTakesBackPartOfTheDrop(self):

        arguments = self.station(localArea = np.pi*0.0505**2, gasMachNumber = 1.0)
        uniform  = solveStationWallTemperature(**arguments, gasSideAxialModel = 'uniform')
        measured = solveStationWallTemperature(**arguments, gasSideAxialModel = 'measured')

        # A cooler wall raises sigma, so the converged coefficients sit closer together than the
        # factor alone would put them, and the wall still lands cooler
        ratio = measured.exhaustConvectiveCoefficient / uniform.exhaustConvectiveCoefficient
        assert measuredAxialFactor(1.0, subsonic = False) < ratio < 1.0
        assert measured.hotWallTemperature < uniform.hotWallTemperature

    def testAPrescribedCoefficientIsNotScaled(self):

        arguments = self.station(localArea = np.pi*0.0505**2, gasMachNumber = 1.0)
        prescribed = solveStationWallTemperature(**arguments, gasSideAxialModel = 'measured',
                                                 prescribedGasCoefficient = 12000.0)

        assert prescribed.exhaustConvectiveCoefficient == pytest.approx(12000.0, rel = 1e-12)

class TestPressureScaling:

    '''

    What the data does confirm about the form NOVA already uses.

    One constant per station fits chamber pressures from 150 to 1000 psia, within a standard
    deviation of 8 to 16 percent depending on the station, which is a statement about the
    Reynolds scaling rather than about the constant. The correlation makes the coefficient
    proportional to mass flux to the 0.8, and so does Bartz through its (P_c / c*)^0.8 term.

    '''

    def coefficient(self, chamberPressure):

        return bartzHeatTransferCoefficient(
            nearWallTemperature = 3200.0, nearWallMachNumber = 0.2, exhaustGamma = 1.15,
            exhaustGasConstant = 650.0, exhaustMolecularWeight = 12.8,
            hotWallTemperature = 700.0, chamberPressure = chamberPressure,
            characteristicVelocity = 2340.0, throatDiameter = 0.101,
            throatRadiusOfCurvature = 0.0757, throatArea = np.pi*0.0505**2,
            localArea = np.pi*0.0505**2*4.64)

    @pytest.mark.parametrize('pressureRatio', [2.0, 6.67])

    def testTheCoefficientScalesWithMassFluxToThe0p8(self, pressureRatio):

        # 150 to 1000 psia is the range the constants were fitted over, a ratio of 6.67
        base = self.coefficient(1.034e6)

        assert self.coefficient(1.034e6*pressureRatio)/base \
               == pytest.approx(pressureRatio**0.8, rel = 1e-12)
