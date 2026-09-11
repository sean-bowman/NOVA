# -- NOVA: Radiative Heat Transfer Tests -- #

'''

Verification of the radiation primitives in NOVA.radiativeCooling.

Almost everything here is an identity rather than a comparison. The factorisation the module
rests on is exact algebra, so the test is whether the code reproduces the fourth-power law it was
derived from, and the tolerance is rounding rather than a judgement about accuracy. The same
holds for the effective coefficient and driving temperature: they are constructed to reproduce
the sum of two fluxes exactly, and they either do or there is a bug.

The one thing that is not an identity is the radiation equilibrium root, which is checked by
substituting the answer back into the balance it solves.

What these tests deliberately do not cover is whether the grey-gas model describes a real
combustion gas. It does not, particularly: a real gas radiates in bands, a real wall reflects, and
the gas emissivity is an input here rather than something NOVA computes. Those limits are in the
module docstring, and no test can close them.

Author: Sean Bowman

'''

import numpy as np
import pytest

from NOVA.radiativeCooling import (STEFANBOLTZMANN, cylinderMeanBeamLength,
                                   effectiveGasSideDriving, meanBeamLength,
                                   netWallRadiativeFlux, radiationEquilibriumTemperature,
                                   wallRadiationCoefficient)
from NOVA.utils import ConvergenceFailureError, InvalidInputError

# A hot wall in a chamber, and a station out in the diverging section. The pair spans the range
# the coefficient has to hold over, from a large temperature difference to a small one.
CHAMBER = dict(wallEmissivity = 0.8, gasEmissivity = 0.3,
               gasTemperature = 3400.0, wallTemperature = 750.0)
DIVERGING = dict(wallEmissivity = 0.35, gasEmissivity = 0.05,
                 gasTemperature = 1700.0, wallTemperature = 1650.0)

class TestTheFactorisationIsExact:

    '''

    The coefficient form and the fourth-power law are the same expression.

    `sigma (T_g^4 - T_w^4) = sigma (T_g + T_w)(T_g^2 + T_w^2)(T_g - T_w)` is a difference of two
    squares applied twice. Nothing is linearised, so the agreement has to hold at any pair of
    temperatures rather than only near equality, and that is what makes it safe to put radiation
    in parallel with a convective coefficient.

    '''

    @pytest.mark.parametrize('condition', [CHAMBER, DIVERGING], ids = ['chamber', 'diverging'])
    def testItReproducesTheFourthPowerLaw(self, condition):

        coefficient = wallRadiationCoefficient(**condition)
        difference = condition['gasTemperature'] - condition['wallTemperature']

        direct = condition['wallEmissivity'] * condition['gasEmissivity'] * STEFANBOLTZMANN * (
            condition['gasTemperature']**4 - condition['wallTemperature']**4)

        assert coefficient * difference == pytest.approx(direct, rel = 1.0e-13)

    def testItHoldsWhereTheTemperaturesNearlyMeet(self):

        # The place a linearisation would show. One millikelvin apart, the flux is tiny and the
        # coefficient is not, and the product still has to be right.
        coefficient = wallRadiationCoefficient(0.8, 0.3, 2000.001, 2000.0)
        direct = 0.8 * 0.3 * STEFANBOLTZMANN * (2000.001**4 - 2000.0**4)

        assert coefficient * 0.001 == pytest.approx(direct, rel = 1.0e-9)

    def testItIsFiniteWhereTheTemperaturesCoincide(self):

        # No singularity, because the potential the coefficient multiplies is the one radiation
        # actually has. A coefficient written on the convective potential would blow up here.
        coefficient = wallRadiationCoefficient(0.8, 0.3, 2000.0, 2000.0)

        assert np.isfinite(coefficient)
        assert coefficient > 0.0

    def testItIsSymmetricInTheTwoTemperatures(self):

        # The coefficient is even in the pair; only the difference it multiplies carries the
        # direction of the flux.
        forward = wallRadiationCoefficient(0.8, 0.3, 3000.0, 900.0)
        reversed_ = wallRadiationCoefficient(0.8, 0.3, 900.0, 3000.0)

        assert forward == reversed_

class TestRadiationSwitchesOffExactly:

    '''

    Zero has to mean zero to the bit, not to a tolerance.

    A jacket run with no emissivity supplied must reproduce one from before radiation existed.
    That is the property the whole change rests on, so it is asserted with `==` rather than with
    `approx`.

    '''

    def testZeroWallEmissivityGivesExactlyZero(self):

        assert wallRadiationCoefficient(0.0, 0.3, 3400.0, 750.0) == 0.0

    def testZeroGasEmissivityGivesExactlyZero(self):

        assert wallRadiationCoefficient(0.8, 0.0, 3400.0, 750.0) == 0.0

    def testZeroWallEmissivityGivesExactlyZeroFlux(self):

        assert netWallRadiativeFlux(0.0, 0.3, 3400.0, 750.0, 0.0) == 0.0

    def testTheEffectivePairIsUntouchedWithoutRadiation(self):

        coefficient, temperature = effectiveGasSideDriving(12345.6789, 0.0, 3456.789, 2000.0)

        assert coefficient == 12345.6789
        assert temperature == 3456.789

    @pytest.mark.parametrize('coefficient', [1.0, 1234.5, 98765.4321, 1.0e-9])
    def testTheDrivingTemperatureSurvivesUnchangedForAnyCoefficient(self, coefficient):

        # The algebra would give (h T) / h, which is not bitwise T. The branch on exact zero is
        # what makes this hold, and it is the reason that branch exists.
        _, temperature = effectiveGasSideDriving(coefficient, 0.0, 3123.4567890123, 1000.0)

        assert temperature == 3123.4567890123

class TestTheEffectivePairReproducesBothFluxes:

    '''

    One coefficient and one temperature standing in for convection plus radiation.

    Convection is driven by the adiabatic wall temperature and radiation by the gas temperature.
    The pair is constructed so that their product reproduces the sum of the two fluxes at any wall
    temperature, which is what keeps the resistance network correct rather than merely unchanged.

    '''

    @pytest.mark.parametrize('wallTemperature', [300.0, 750.0, 1500.0, 2500.0, 3399.0])
    def testTheIdentityHoldsAtAnyWallTemperature(self, wallTemperature):

        convective = 14000.0
        gasTemperature = 3400.0
        drivingTemperature = 3600.0
        radiative = wallRadiationCoefficient(0.8, 0.3, gasTemperature, wallTemperature)

        coefficient, temperature = effectiveGasSideDriving(
            convective, radiative, drivingTemperature, gasTemperature)

        combined = coefficient * (temperature - wallTemperature)
        separate = convective * (drivingTemperature - wallTemperature) \
                   + radiative * (gasTemperature - wallTemperature)

        assert combined == pytest.approx(separate, rel = 1.0e-13)

    def testTheEffectiveTemperatureLiesBetweenTheTwoItCombines(self):

        coefficient, temperature = effectiveGasSideDriving(14000.0, 900.0, 3600.0, 3400.0)

        assert 3400.0 <= temperature <= 3600.0
        assert coefficient == 14000.0 + 900.0

class TestTheGeneralFluxAndItsChamberReduction:

    '''

    The sink-aware flux, and the case where the wall sees only more wall.

    Setting the sink to the wall's own temperature cancels the transmitted term and leaves the
    chamber form the coefficient factors. That the two agree is the check that the general
    expression and the one used in the jacket are the same physics.

    '''

    def testASelfSinkReducesToTheChamberForm(self):

        general = netWallRadiativeFlux(0.8, 0.3, 3400.0, 750.0, None)
        chamber = 0.8 * 0.3 * STEFANBOLTZMANN * (3400.0**4 - 750.0**4)

        assert general == pytest.approx(chamber, rel = 1.0e-13)

    def testAnExplicitSelfSinkMatchesTheImplicitOne(self):

        implicit = netWallRadiativeFlux(0.8, 0.3, 3400.0, 750.0, None)
        explicit = netWallRadiativeFlux(0.8, 0.3, 3400.0, 750.0, 750.0)

        assert implicit == explicit

    def testATransparentGasExchangesDirectlyWithTheSink(self):

        # Gas emissivity zero, so the wall sees straight through to the sink.
        flux = netWallRadiativeFlux(0.9, 0.0, 3400.0, 1200.0, 4.0)
        direct = 0.9 * STEFANBOLTZMANN * (4.0**4 - 1200.0**4)

        assert flux == pytest.approx(direct, rel = 1.0e-13)

    def testAWallHotterThanEverythingLoses(self):

        assert netWallRadiativeFlux(0.9, 0.2, 1000.0, 2000.0, 0.0) < 0.0

class TestRadiationEquilibrium:

    '''

    The temperature an uncooled wall settles at, checked by substitution.

    There is no closed form for the root of a quartic plus a linear term that is worth writing
    out, so the check is that the answer satisfies the balance it was found from. That is a
    complete verification: the balance is the definition.

    '''

    @pytest.mark.parametrize('coefficient, driving, emissivity', [
        (500.0, 3000.0, 0.7), (2000.0, 2500.0, 0.9), (120.0, 3400.0, 0.4)])
    def testTheAnswerSatisfiesItsOwnBalance(self, coefficient, driving, emissivity):

        wall = radiationEquilibriumTemperature(coefficient, driving, emissivity)
        residual = coefficient * (driving - wall) - emissivity * STEFANBOLTZMANN * wall**4

        assert abs(residual) < 1.0e-6

    def testTheWallSitsBelowTheGasDrivingIt(self):

        wall = radiationEquilibriumTemperature(500.0, 3000.0, 0.7)

        assert 0.0 < wall < 3000.0

    @pytest.mark.parametrize('coefficient', [5.0, 50.0, 500.0, 5000.0])
    def testLowerEmissivityMeansAHotterWall(self, coefficient):

        hot = radiationEquilibriumTemperature(coefficient, 3000.0, 0.35)
        cool = radiationEquilibriumTemperature(coefficient, 3000.0, 0.70)

        assert hot > cool

    @pytest.mark.parametrize('coefficient', [5.0, 50.0, 500.0, 5000.0])
    def testTheQuarterPowerRuleIsAnUpperBoundRatherThanTheAnswer(self, coefficient):

        # Halving the emissivity is often quoted as raising the wall by 2^(1/4), about 19 per
        # cent. That holds only where the wall sits far below the gas driving it, so that the
        # convective input barely notices the wall moving. In a real nozzle it does notice:
        # a hotter wall takes in less, which partly offsets the emissivity it lost.
        #
        # Measured here, halving the emissivity from 0.70 to 0.35 against a 3000 K driving
        # temperature raises the wall by 17.2 per cent at a coefficient of 5 W/m^2 K and only
        # 5.5 per cent at 5000. The bound is real and it is never reached.
        hot = radiationEquilibriumTemperature(coefficient, 3000.0, 0.35)
        cool = radiationEquilibriumTemperature(coefficient, 3000.0, 0.70)

        assert 1.0 < hot / cool < 2.0**0.25

    def testTheBoundIsApproachedAsConvectionWeakens(self):

        def ratio(coefficient):
            return (radiationEquilibriumTemperature(coefficient, 3000.0, 0.35)
                    / radiationEquilibriumTemperature(coefficient, 3000.0, 0.70))

        # Monotone toward the bound as the wall drops away from the gas.
        assert ratio(5.0) > ratio(50.0) > ratio(500.0) > ratio(5000.0)
        assert ratio(5.0) == pytest.approx(2.0**0.25, rel = 0.02)

    def testAbsorbedFluxRaisesIt(self):

        without = radiationEquilibriumTemperature(500.0, 3000.0, 0.7)
        with_ = radiationEquilibriumTemperature(500.0, 3000.0, 0.7, absorbedFlux = 50.0e3)

        assert with_ > without

    def testAViewFactorBelowOneRaisesIt(self):

        open_ = radiationEquilibriumTemperature(500.0, 3000.0, 0.7, viewFactor = 1.0)
        enclosed = radiationEquilibriumTemperature(500.0, 3000.0, 0.7, viewFactor = 0.5)

        assert enclosed > open_

    def testASurfaceThatRadiatesNothingIsRefused(self):

        with pytest.raises(InvalidInputError):
            radiationEquilibriumTemperature(500.0, 3000.0, 0.0)

        with pytest.raises(InvalidInputError):
            radiationEquilibriumTemperature(500.0, 3000.0, 0.7, viewFactor = 0.0)

    def testAWallThatCannotRadiateEnoughSaysSo(self):

        # An enormous coefficient against a low emissivity puts the root past the bracket, and
        # being told is better than being handed the bracket end as an answer.
        with pytest.raises(ConvergenceFailureError):
            radiationEquilibriumTemperature(1.0e9, 5000.0, 0.01, upperBound = 4000.0)

    def testASurfaceAlreadyAboveTheDrivingTemperatureCoolsToTheSink(self):

        wall = radiationEquilibriumTemperature(500.0, 300.0, 0.7, sinkTemperature = 300.0)

        assert wall == pytest.approx(300.0, abs = 1.0e-6)

class TestMeanBeamLength:

    '''The equivalent path a radiating gas presents to the surface bounding it.'''

    def testACylinderReducesToAFractionOfItsDiameter(self):

        assert cylinderMeanBeamLength(0.1) == pytest.approx(0.095, rel = 1.0e-12)

    def testTheGeneralFormAgreesWithTheCylinderShortcut(self):

        # A cylinder of length L and diameter D: 4V/A = D once the ends are negligible.
        diameter, length = 0.1, 100.0
        volume = np.pi * diameter**2 / 4.0 * length
        area = np.pi * diameter * length

        assert meanBeamLength(volume, area) == pytest.approx(cylinderMeanBeamLength(diameter),
                                                            rel = 1.0e-9)

    def testAGeometryWithNoGasIsRefused(self):

        with pytest.raises(InvalidInputError):
            meanBeamLength(0.0, 1.0)

        with pytest.raises(InvalidInputError):
            cylinderMeanBeamLength(0.0)

class TestInputBounds:

    '''An emissivity outside zero to one describes a surface that emits more than a black body.'''

    @pytest.mark.parametrize('wallEmissivity, gasEmissivity', [
        (-0.1, 0.3), (1.1, 0.3), (0.8, -0.01), (0.8, 1.5)])
    def testItIsRefused(self, wallEmissivity, gasEmissivity):

        with pytest.raises(InvalidInputError):
            wallRadiationCoefficient(wallEmissivity, gasEmissivity, 3000.0, 800.0)

    @pytest.mark.parametrize('value', [0.0, 1.0])
    def testTheEndsOfTheRangeAreAllowed(self, value):

        assert np.isfinite(wallRadiationCoefficient(value, value, 3000.0, 800.0))

class TestPhysicalConstant:

    '''The constant is the one the ablative model already uses, not a second copy.'''

    def testItIsTheCodataValue(self):

        assert STEFANBOLTZMANN == pytest.approx(5.670374419e-8, rel = 1.0e-12)

    def testItIsTheSameObjectTheAblativeModelUses(self):

        from NOVA.ablative import STEFANBOLTZMANN as ablativeConstant

        assert STEFANBOLTZMANN == ablativeConstant
