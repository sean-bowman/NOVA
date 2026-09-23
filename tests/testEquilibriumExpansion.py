'''

Tests for the equilibrium expansion table and the gas built on it.

A characteristics solve needs four relations from its gas: the Prandtl-Meyer angle, the static
temperature and the velocity at a Mach number, and the Mach number at a velocity. For a calorically
perfect gas each follows in closed form from one ratio of specific heats. `EquilibriumGas` answers
the same four from a tabulated expansion instead, so the exponent may vary along it, which is what
a recombining exhaust does.

The check that matters is the Prandtl-Meyer integral, because it is the one relation that has no
closed form once the exponent varies. Generated from a constant-gamma expansion it must reproduce
`gasDynamics.prandtlMeyerAngle`, and it is held to that here at the sampling the module defaults
to. That sampling is not arbitrary: the integrand rises as sqrt(M^2 - 1) out of the sonic point,
so a table that starts at an area ratio of 1.05 lands a full degree low at every station
downstream, and the test records that too.

Author: Sean Bowman

'''

import numpy as np
import pytest
from scipy.optimize import brentq

from NOVA.equilibriumExpansion import (EquilibriumGas, expansionTable,
                                       generalizedPrandtlMeyerAngle)
from NOVA.gasDynamics import prandtlMeyerAngle

def perfectGasExpansion(gamma, areaRatios):

    '''Mach number and velocity along a constant-gamma expansion, velocity on sqrt(gamma R T0).'''

    def areaMach(mach):
        return (1/mach)*((2/(gamma + 1))*(1 + 0.5*(gamma - 1)*mach**2))**((gamma + 1)/(2*(gamma - 1)))

    mach = np.array([1.0] + [brentq(lambda m: areaMach(m) - ratio, 1.0 + 1e-12, 40.0)
                             for ratio in areaRatios[1:]])
    velocity = mach*np.sqrt(1.0/(1 + 0.5*(gamma - 1)*mach**2))

    return mach, velocity

def defaultSampling():

    '''The area ratios expansionTable samples by default.'''

    return np.concatenate(([1.0], 1.0 + np.geomspace(1e-5, 0.05, 60),
                           np.geomspace(1.05, 100.0, 60)[1:]))

class TestAgainstTheClosedForm:

    '''The integral reduces to the Prandtl-Meyer function when the exponent does not vary.'''

    @pytest.mark.parametrize('gamma', [1.15, 1.2, 1.4])
    def testItReproducesTheClosedForm(self, gamma):

        ratios = defaultSampling()
        mach, velocity = perfectGasExpansion(gamma, ratios)

        integrated = generalizedPrandtlMeyerAngle(mach, velocity)
        closedForm = np.array([prandtlMeyerAngle(m, gamma) for m in mach])

        assert np.degrees(np.abs(integrated - closedForm)).max() < 0.025

    @pytest.mark.parametrize('gamma', [1.15, 1.4])
    def testTheNearThroatSamplingIsWhatMakesItWork(self, gamma):

        # Starting the table at an area ratio of 1.05 puts the whole turning from Mach 1 to about
        # 1.3 in one interval, and every station downstream inherits the error
        coarse = np.concatenate(([1.0], np.geomspace(1.05, 100.0, 60)))
        mach, velocity = perfectGasExpansion(gamma, coarse)

        integrated = generalizedPrandtlMeyerAngle(mach, velocity)
        closedForm = np.array([prandtlMeyerAngle(m, gamma) for m in mach])

        assert np.degrees(np.abs(integrated - closedForm)).max() > 1.0

    def testItStartsFromZeroAtTheSonicPoint(self):

        mach, velocity = perfectGasExpansion(1.2, defaultSampling())

        assert generalizedPrandtlMeyerAngle(mach, velocity)[0] == 0.0

    def testItTurnsOneWay(self):

        mach, velocity = perfectGasExpansion(1.2, defaultSampling())

        assert np.all(np.diff(generalizedPrandtlMeyerAngle(mach, velocity)) > 0)

class TestTheTable:

    '''What the thermochemistry gives back along the expansion.'''

    table = expansionTable('LH2', 'LOX', 5.5, 6894757.0)

    def testItStartsAtTheThroat(self):

        assert self.table.mach[0] == 1.0
        assert self.table.areaRatio[0] == 1.0

    def testEveryQuantityRunsTheRightWay(self):

        assert np.all(np.diff(self.table.mach) > 0)
        assert np.all(np.diff(self.table.velocity) > 0)
        assert np.all(np.diff(self.table.temperature) < 0)
        assert np.all(np.diff(self.table.pressure) < 0)

    def testTheExponentClimbsAsItRecombines(self):

        # A recombining exhaust stiffens as it cools, which is the whole reason one value cannot
        # stand for the expansion
        assert self.table.gamma[-1] > self.table.gamma[0]
        assert self.table.gamma[0] == pytest.approx(1.15, abs = 0.02)
        assert self.table.gamma[-1] == pytest.approx(1.28, abs = 0.02)

    def testFrozenChemistryStiffensTheGas(self):

        frozen = expansionTable('LH2', 'LOX', 5.5, 6894757.0,
                                areaRatios = [2.0, 10.0, 40.0], frozenAtThroat = True, frozen = True)
        equilibrium = expansionTable('LH2', 'LOX', 5.5, 6894757.0, areaRatios = [2.0, 10.0, 40.0])

        assert np.all(frozen.gamma[1:] > equilibrium.gamma[1:])
        assert frozen.temperature[-1] < equilibrium.temperature[-1]

class TestTheGasInterface:

    '''The four relations a characteristics solve asks for.'''

    gas = EquilibriumGas(expansionTable('LH2', 'LOX', 5.5, 6894757.0))

    def testVelocityAndMachInvertEachOther(self):

        for mach in (1.5, 2.5, 3.5, 4.5):
            assert self.gas.machFromVelocity(self.gas.localVelocity(mach)) \
                   == pytest.approx(mach, rel = 1e-6)

    def testTemperatureFallsWithMach(self):

        temperatures = [self.gas.localTemperature(m) for m in (1.5, 2.5, 3.5, 4.5)]

        assert np.all(np.diff(temperatures) < 0)

    def testTheTurningIsLessThanAConstantChamberGammaPredicts(self):

        # The finding this module exists for: at the reference engine's exit the chamber value
        # overstates the turning by about 8 degrees, because it is the exponent of the hottest,
        # most dissociated gas in the nozzle rather than of the gas doing the expanding
        mach = 4.215
        chamberGamma = 1.1475

        assert np.degrees(prandtlMeyerAngle(mach, chamberGamma)
                          - self.gas.prandtlMeyerAngle(mach)) == pytest.approx(8.0, abs = 1.0)

    def testItReportsTheStationItIsAsked(self):

        assert self.gas.stagnationTemperature == pytest.approx(3398.0, abs = 5.0)
        assert 1.15 < self.gas.gamma < 1.30
