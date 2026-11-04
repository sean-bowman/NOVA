'''

Tests for the estimated and delivered performance in performance.py and the exit-plane integral
it is built from.

The delivered values are an integral over a solved exit plane, so they cannot be checked against
a published nozzle; what can be checked is the integral itself. A uniform, axial exit plane at the
one-dimensional Mach number has to integrate to the one-dimensional answer, and every coefficient
at a back pressure has to follow from the vacuum one by C_F(p_a) = C_F,vac - p_a eps / p_c.

Author: Sean Bowman

'''

import json
from types import SimpleNamespace

import numpy as np
import pytest

from NOVA import units
from NOVA.contour import exitPlaneThrustCoefficient
from NOVA.gasDynamics import machFromAreaRatio
from NOVA.performance import SEALEVELPRESSURE, chamberGasEstimate, summarizePerformance

GAMMA = 1.1475                  # [-]
GASCONSTANT = 656.6             # [J/kg-K]
STAGNATIONTEMPERATURE = 3398.0  # [K]
CHAMBERPRESSURE = 6.894757e6    # [Pa]
AREARATIO = 40.0                # [-]

def estimate():

    return chamberGasEstimate(AREARATIO, GAMMA, GASCONSTANT, STAGNATIONTEMPERATURE, CHAMBERPRESSURE)

class TestTheChamberGasEstimate:

    def testTheVacuumCoefficientIsTheMomentumAndPressureTerms(self):

        result = estimate()
        expected = result['exitVelocity'] / result['characteristicVelocity'] \
                   + AREARATIO * result['exitPressure'] / CHAMBERPRESSURE

        assert result['vacuumThrustCoef'] == pytest.approx(expected, rel = 1e-14)

    def testTheCharacteristicVelocityIsTheChokedFlowPerThroatForce(self):

        result = estimate()
        chokedFlux = CHAMBERPRESSURE * np.sqrt(GAMMA / (GASCONSTANT * STAGNATIONTEMPERATURE)
                                               * (2.0 / (GAMMA + 1.0))**((GAMMA + 1.0) / (GAMMA - 1.0)))

        assert result['characteristicVelocity'] == pytest.approx(CHAMBERPRESSURE / chokedFlux,
                                                                 rel = 1e-12)

    def testTheExitStateIsTheAreaMachRelation(self):

        result = estimate()

        assert result['exitMach'] == pytest.approx(machFromAreaRatio(AREARATIO, GAMMA), rel = 1e-12)

def uniformPlane(stations = 400):

    '''A uniform, axial exit plane at the one-dimensional Mach number, wall inward to the axis.'''

    state = SimpleNamespace(chamberPressure = CHAMBERPRESSURE,
                            chamberStagnationTemperature = STAGNATIONTEMPERATURE,
                            chamberGamma = GAMMA, throatGamma = GAMMA,
                            chamberRGasConstant = GASCONSTANT, throatRadiusNonDimensional = 1.0,
                            targetExitPressure = 14000.0)
    radius = np.linspace(np.sqrt(AREARATIO), 0.0, stations)
    mach = np.full(stations, machFromAreaRatio(AREARATIO, GAMMA))
    exitPlaneThrustCoefficient(state, radius, mach, np.zeros(stations))
    return state

class TestTheExitPlaneIntegral:

    def testAUniformAxialPlaneDeliversTheOneDimensionalVacuumCoefficient(self):

        state = uniformPlane()

        assert state.vacuumThrustCoef == pytest.approx(estimate()['vacuumThrustCoef'], rel = 1e-10)

    def testAUniformAxialPlaneDeliversTheOneDimensionalImpulse(self):

        state = uniformPlane()
        result = estimate()
        expected = result['vacuumThrustCoef'] * result['characteristicVelocity'] / units.GRAVITY

        assert state.exitVacuumSpecificImpulse == pytest.approx(expected, rel = 1e-10)

    def testItCarriesAllOfTheChokedFlow(self):

        assert uniformPlane().exitMassClosure == pytest.approx(1.0, rel = 1e-10)

    def testItReportsThePlaneAreaRatioAndItsAverages(self):

        state = uniformPlane()
        result = estimate()

        assert state.exitPlaneAreaRatio == pytest.approx(AREARATIO, rel = 1e-14)
        assert state.exitMassAveragedMach == pytest.approx(result['exitMach'], rel = 1e-12)
        assert state.exitMassAveragedPressure == pytest.approx(result['exitPressure'], rel = 1e-12)
        assert state.exitMassAveragedVelocity == pytest.approx(result['exitVelocity'], rel = 1e-12)

def solvedSource(dragForce = None):

    '''A source carrying what a solved nozzle hands the summary, here from a uniform plane.'''

    plane = uniformPlane()
    cea = SimpleNamespace(
        ceaResults = dict(characteristicVelocity = 2340.0, exitMach = 4.22, exitPressure = 13993.0,
                          exitTemperature = 1275.0, exitVelocity = 4260.0, expansionRatio = AREARATIO),
        nozzlePerformance = {'vacuumThrustCoef': 1.9017})
    throatArea = 0.008                                                       # [m^2]
    return SimpleNamespace(**vars(plane), ceaOutput = cea, throatArea = throatArea,
                           thrust = 100000.0, engineMassFlow = 23.466,
                           plumeAmbientPressure = 5000.0, frictionDragForce = dragForce,
                           thrustCoef = plane.vacuumThrustCoef
                           - plane.targetExitPressure * AREARATIO / CHAMBERPRESSURE)

class TestTheSummary:

    def testEveryBackPressureFollowsFromTheVacuumCoefficient(self):

        summary = summarizePerformance(solvedSource())

        for name, pressure in summary.backPressures.items():
            for table in (summary.thrustCoefEquilibrium, summary.thrustCoefChamberGas,
                          summary.thrustCoefDelivered):
                assert table[name] == pytest.approx(
                    table['vacuum'] - pressure * AREARATIO / CHAMBERPRESSURE, rel = 1e-12)

    def testTheDesignBackPressureIsTheSolvesOwnObjective(self):

        source = solvedSource()
        summary = summarizePerformance(source)

        assert summary.backPressures['design'] == source.targetExitPressure
        assert summary.thrustCoefDelivered['design'] == pytest.approx(source.thrustCoef, rel = 1e-12)
        assert summary.backPressures['seaLevel'] == SEALEVELPRESSURE
        assert summary.backPressures['ambient'] == 5000.0

    def testAUniformPlaneIsAPerfectNozzle(self):

        assert summarizePerformance(solvedSource()).nozzleEfficiency == pytest.approx(1.0, rel = 1e-10)

    def testFrictionIsChargedAsDragOverTheThroatForce(self):

        drag = 2000.0
        summary = summarizePerformance(solvedSource(drag))
        charge = drag / (CHAMBERPRESSURE * 0.008)

        assert summary.frictionThrustCoef == pytest.approx(charge, rel = 1e-12)
        for name in summary.backPressures:
            assert summary.thrustCoefDeliveredFrictionCorrected[name] == pytest.approx(
                summary.thrustCoefDelivered[name] - charge, rel = 1e-12)

    def testDeliveredThrustIsTheEngineFlowTimesTheDeliveredImpulse(self):

        summary = summarizePerformance(solvedSource())

        for name in summary.backPressures:
            assert summary.thrustDelivered[name] == pytest.approx(
                23.466 * units.GRAVITY * summary.specificImpulseDelivered[name], rel = 1e-12)

    def testItSerializesAndTabulates(self):

        summary = summarizePerformance(solvedSource(2000.0))

        json.dumps(summary.toDict())
        rows = summary.rows()
        assert all(len(row) == 5 for row in rows)
        assert sum(row[0].startswith('Thrust coefficient') for row in rows) == len(summary.backPressures)
        assert 'Nozzle performance' in summary.report()
