'''

Tests for the entrainment film closure where it leaves the band SP-8124 calibrated it for.

SP-8124 writes the recovery defect at the core velocity, which is right for a film injected at
the 0.9 to 1.15 velocity ratio the monograph recommends and wrong for one injected slower: at the
slot a slow film is coolant moving at its own velocity, and charging it the core's kinetic energy
drives a low heat capacity coolant below absolute zero. These tests hold the closure to the
source's expression inside the band and to the coolant's own recovery at the slot outside it, and
hold the march to the real throat when it is handed arrays that do not contain one.

Author: Sean Bowman

'''

import numpy as np
import pytest

from NOVA.filmCooling import (SP8124INJECTIONBAND, entrainmentAdiabaticWallTemperature,
                              entrainmentFilmArrays, entrainmentMultiplier)

# A Mach 3 core under a slow methane film, the case the investigation found reading 164 K below zero
CORETOTAL = 3427.0          # [K]
CORERECOVERY = 3100.0       # [K]
CORESPECIFICHEAT = 3500.0   # [J/kg-K], equilibrium
METHANEHEAT = 2221.0        # [J/kg-K]
METHANETOTAL = 272.0        # [K]

class TestTheAdiabaticWallTemperature:

    def testALayerMovingWithTheCoreIsTheSourceExpression(self):

        effectiveness = 0.6
        expected = CORETOTAL - (effectiveness * METHANEHEAT * (CORETOTAL - METHANETOTAL)
                                + CORESPECIFICHEAT * (CORETOTAL - CORERECOVERY)) \
                   / (effectiveness * METHANEHEAT + (1.0 - effectiveness) * CORESPECIFICHEAT)

        result = entrainmentAdiabaticWallTemperature(effectiveness, CORETOTAL, CORERECOVERY,
                                                     CORESPECIFICHEAT, METHANEHEAT, METHANETOTAL,
                                                     layerVelocityRatio = 1.0)

        assert result == expected

    def testPureCoreReturnsTheRecoveryTemperatureAtAnyLayerVelocity(self):

        # A layer of pure core moves at the core velocity whatever the slot did, and the march
        # never hands this limit a ratio other than one; the expression is still exact at it
        result = entrainmentAdiabaticWallTemperature(0.0, CORETOTAL, CORERECOVERY,
                                                     CORESPECIFICHEAT, METHANEHEAT, METHANETOTAL,
                                                     layerVelocityRatio = 1.0)

        assert result == pytest.approx(CORERECOVERY, abs = 1e-9)

    def testPureCoolantRecoversAtItsOwnVelocity(self):

        ratio = 0.06
        expected = METHANETOTAL - CORESPECIFICHEAT * (CORETOTAL - CORERECOVERY) * ratio**2 / METHANEHEAT

        result = entrainmentAdiabaticWallTemperature(1.0, CORETOTAL, CORERECOVERY,
                                                     CORESPECIFICHEAT, METHANEHEAT, METHANETOTAL,
                                                     layerVelocityRatio = ratio)

        assert result == pytest.approx(expected, rel = 1e-12)

    def testASlowMethaneFilmStaysNearItsOwnTemperature(self):

        coreVelocityResult = entrainmentAdiabaticWallTemperature(
            1.0, CORETOTAL, CORERECOVERY, CORESPECIFICHEAT, METHANEHEAT, METHANETOTAL, 1.0)
        slowResult = entrainmentAdiabaticWallTemperature(
            1.0, CORETOTAL, CORERECOVERY, CORESPECIFICHEAT, METHANEHEAT, METHANETOTAL, 0.06)

        # The source's expression charges the coolant the core's kinetic energy...
        assert coreVelocityResult < 0.0
        # ...and the coolant moving at its own velocity recovers to within a few kelvin of its total
        assert METHANETOTAL - 5.0 < slowResult <= METHANETOTAL

def uniformDuct(stations = 80, radius = 0.1, length = 0.6):

    '''A constant-area supersonic duct and its core, enough for the march to run on.'''

    x = np.linspace(0.0, length, stations)
    return dict(axialPosition = x, radius = np.full(stations, radius),
                gasVelocity = np.full(stations, 3000.0), gasDensity = np.full(stations, 0.4),
                totalTemperature = np.full(stations, CORETOTAL),
                recoveryTemperature = np.full(stations, CORERECOVERY),
                coreSpecificHeat = np.full(stations, CORESPECIFICHEAT),
                massFluxRatio = np.ones(stations))

def march(coolantVelocity, **overrides):

    arguments = dict(uniformDuct(), injectionPosition = 0.0, slotHeight = 0.003,
                     coreMassFlow = 100.0, coolantMassFlow = 2.0, coolantDensity = 2.0,
                     coolantVelocity = coolantVelocity, coolantViscosity = 1.0e-5,
                     coolantSpecificHeat = METHANEHEAT, coolantTotalTemperature = METHANETOTAL,
                     coreMixtureRatio = 3.5)
    arguments.update(overrides)
    return entrainmentFilmArrays(**arguments)

class TestTheMarch:

    def testItReportsTheInjectionVelocityRatioAgainstTheBand(self):

        inside = march(3000.0)
        outside = march(300.0)

        assert inside.injectionVelocityRatio == pytest.approx(1.0)
        assert inside.withinInjectionBand
        assert outside.injectionVelocityRatio == pytest.approx(0.1)
        assert not outside.withinInjectionBand
        assert SP8124INJECTIONBAND == (0.9, 1.15)

    def testASlowFilmNeverDrivesTheWallBelowItsOwnTemperatureLessItsRecoveryDefect(self):

        result = march(150.0)
        injection = result.injectionIndex

        assert np.all(result.drivingTemperature[injection:] > 0.0)
        assert result.drivingTemperature[injection] == pytest.approx(METHANETOTAL, abs = 2.0)

    def testAnExtensionOnlyArrayReadsFigure17AtItsTrueAreaRatio(self):

        # The arrays start at an area ratio of 3, so their own smallest radius is not the throat
        throatRadius = 0.05
        duct = uniformDuct(radius = throatRadius * np.sqrt(3.0))

        withThroat = march(3000.0, **duct, throatRadius = throatRadius)
        withoutThroat = march(3000.0, **duct)

        assert withThroat.entrainmentMultiplier[0] == pytest.approx(entrainmentMultiplier(3.0))
        assert withoutThroat.entrainmentMultiplier[0] == pytest.approx(entrainmentMultiplier(1.0))
