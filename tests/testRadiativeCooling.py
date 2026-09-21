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

from NOVA.radiativeCooling import (RadiativeShell, STEFANBOLTZMANN, cylinderMeanBeamLength,
                                   effectiveGasSideDriving, meanBeamLength,
                                   netWallRadiativeFlux, radiationEquilibriumTemperature,
                                   radiativeNozzleExtension, wallRadiationCoefficient)
from NOVA.errors import ConvergenceFailureError, InvalidInputError

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

def conicalExtension(stations = 61):

    '''A straight conical extension and the exhaust along it, shared by the solver tests.'''

    return dict(
        axialPosition = np.linspace(0.0, 0.60, stations),
        radius = np.linspace(0.10, 0.32, stations),
        machNumber = np.linspace(2.6, 3.8, stations),
        staticTemperature = np.linspace(1500.0, 900.0, stations),
        recoveryTemperature = np.linspace(2600.0, 1900.0, stations))

def exhaust():

    '''The engine the extension hangs off, held fixed across the solver tests.'''

    return dict(chamberPressure = 6.895e6, characteristicVelocity = 2300.0,
                exhaustGamma = 1.20, exhaustGasConstant = 520.0, exhaustMolecularWeight = 16.0,
                throatRadius = 0.05, throatRadiusOfCurvature = 0.04)

def shell(**overrides):

    '''A thin coated shell, varied from by the tests that need to.'''

    arguments = dict(thermalConductivity = 45.0, thickness = 5.0e-4, innerEmissivity = 0.0,
                     outerEmissivity = 0.8, gasEmissivity = 0.0)
    arguments.update(overrides)

    return RadiativeShell(**arguments)

class TestTheExtensionSolverAgainstAnswersItDidNotProduce:

    '''

    The four verification checks. Each compares the solver to something computed another way.

    '''

    def testWithConductionOffEveryStationSitsAtItsOwnEquilibrium(self):

        # Conductivity small enough that conduction cannot move anything, which isolates the
        # pointwise balance. Then a scalar root find at each station is the exact answer.
        contour = conicalExtension()
        result = radiativeNozzleExtension(shell(thermalConductivity = 1.0e-9), **contour,
                                          **exhaust())

        independent = np.array([radiationEquilibriumTemperature(
            result.extensionConvectiveCoefficient[i],
            contour['recoveryTemperature'][i], 0.8, 0.0, 0.0, 1.0)
            for i in range(contour['axialPosition'].size)])

        assert np.max(np.abs(result.extensionWallTemperature - independent) / independent) < 1.0e-9

    def testTheConductionOperatorIsSecondOrder(self):

        # Method of manufactured solutions on a cylinder, where r drops out and the operator is
        # k t d2T/ds2 with a known second derivative. The observed order is reported by the
        # refinement rather than assumed.
        conductivity, thickness, cylinderRadius, length = 45.0, 5.0e-4, 0.20, 0.5
        amplitude, offset, wave = 300.0, 1200.0, 2.0 * np.pi / length

        errors = []
        for stations in (41, 81, 161, 321):

            axial = np.linspace(0.0, length, stations)
            exact = offset + amplitude * np.sin(wave * axial)
            faceSpacing = np.diff(axial)
            faceConductance = cylinderRadius * conductivity * thickness / faceSpacing
            cellLength = np.zeros(stations)
            cellLength[0] = 0.5 * faceSpacing[0]
            cellLength[-1] = 0.5 * faceSpacing[-1]
            cellLength[1:-1] = 0.5 * (faceSpacing[:-1] + faceSpacing[1:])

            conduction = np.zeros(stations)
            flowing = faceConductance * np.diff(exact)
            conduction[:-1] += flowing
            conduction[1:] -= flowing
            conduction /= cylinderRadius * cellLength

            analytic = -conductivity * thickness * amplitude * wave**2 * np.sin(wave * axial)
            errors.append(np.max(np.abs(conduction[1:-1] - analytic[1:-1])))

        orders = [np.log2(before / after) for before, after in zip(errors, errors[1:])]

        assert all(abs(order - 2.0) < 0.05 for order in orders), orders

    def testTheEnergyBalanceCloses(self):

        # Power in equals power out plus what leaves through the joint. This is the check that
        # catches an arc length or a wall area written wrong, which a converged residual alone
        # would not.
        result = radiativeNozzleExtension(shell(), **conicalExtension(), **exhaust())

        assert result.extensionEnergyBalanceResidual < 1.0e-8

    def testHalvingTheEmissivityStaysUnderTheQuarterPowerBound(self):

        # With no convection the balance gives T to the inverse fourth root of emissivity, so
        # halving it would raise the wall by 2^0.25. Convection holds it strictly below that,
        # because a hotter wall takes in less.
        contour, engine = conicalExtension(), exhaust()
        high = radiativeNozzleExtension(shell(outerEmissivity = 0.8), **contour, **engine)
        low = radiativeNozzleExtension(shell(outerEmissivity = 0.4), **contour, **engine)

        ratio = low.extensionPeakWallTemperature / high.extensionPeakWallTemperature

        assert 1.0 < ratio < 2.0**0.25

class TestTheExtensionSolverBehavior:

    '''The shape the physics requires, separately from the numbers.'''

    def testAHigherConductivityFlattensTheDistribution(self):

        contour, engine = conicalExtension(), exhaust()
        spans = []
        for conductivity in (1.0e-9, 45.0, 400.0):
            result = radiativeNozzleExtension(shell(thermalConductivity = conductivity),
                                              **contour, **engine)
            wall = result.extensionWallTemperature
            spans.append(wall.max() - wall.min())

        assert spans[0] > spans[1] > spans[2]

    def testConductionBarelyMovesAThinShell(self):

        # Worth pinning: a two-dimensional wall solve would buy very little here, and the reason
        # is that the conduction length is a centimeter against a contour of half a meter.
        contour, engine = conicalExtension(), exhaust()
        thin = radiativeNozzleExtension(shell(thermalConductivity = 1.0e-9),
                                        **contour, **engine).extensionWallTemperature
        conducting = radiativeNozzleExtension(shell(thermalConductivity = 400.0),
                                              **contour,
                                              **engine).extensionWallTemperature
        span = thin.max() - thin.min()
        narrowed = span - (conducting.max() - conducting.min())

        assert narrowed / span < 0.05

    def testTheJointTemperatureIsHeldExactly(self):

        result = radiativeNozzleExtension(shell(upstreamTemperature = 900.0),
                                          **conicalExtension(), **exhaust())

        assert result.extensionWallTemperature[0] == 900.0

    def testTheJointDoesNotReachFarDownItsOwnContour(self):

        # sqrt(k t / h) is about ten millimeters on this shell, so a joint held four hundred
        # kelvin below equilibrium should be invisible within a few stations.
        contour, engine = conicalExtension(), exhaust()
        free = radiativeNozzleExtension(shell(), **contour, **engine)
        held = radiativeNozzleExtension(shell(upstreamTemperature = 900.0), **contour, **engine)
        difference = np.abs(held.extensionWallTemperature - free.extensionWallTemperature)

        assert difference[0] > 400.0
        assert np.all(difference[6:] < 1.0)

    def testTheStartingGuessIsTheZeroConductionAnswer(self):

        # The equilibrium array is returned so the reader can see what conduction did, and with
        # conduction off the two must coincide.
        result = radiativeNozzleExtension(shell(thermalConductivity = 1.0e-9),
                                          **conicalExtension(), **exhaust())

        assert result.extensionWallTemperature == pytest.approx(
            result.extensionEquilibriumTemperature, rel = 1.0e-9)

    def testABandTermSignedByTheStaticGasCoolsAHotterWall(self):

        # On an extension the wall is driven by the recovery temperature and the band exchange is
        # written in the static one. A wall above the static gas radiates into it, so the gas is
        # a second sink rather than a source. The sign is the station's, not an assumption.
        contour, engine = conicalExtension(), exhaust()
        transparent = radiativeNozzleExtension(shell(innerEmissivity = 0.8), **contour, **engine)
        absorbing = radiativeNozzleExtension(shell(innerEmissivity = 0.8, gasEmissivity = 0.30),
                                             **contour, **engine)

        assert np.all(absorbing.extensionWallTemperature[0]
                      < transparent.extensionWallTemperature[0])
        assert absorbing.extensionGasRadiativeFlux[0] < 0.0

    def testAColderExhaustGivesAColderWall(self):

        contour, engine = conicalExtension(), exhaust()
        hot = radiativeNozzleExtension(shell(), **contour, **engine)
        contour['recoveryTemperature'] = contour['recoveryTemperature'] - 400.0
        cool = radiativeNozzleExtension(shell(), **contour, **engine)

        assert cool.extensionPeakWallTemperature < hot.extensionPeakWallTemperature

    def testTheThroughThicknessDropIsSmallEnoughToLump(self):

        result = radiativeNozzleExtension(shell(), **conicalExtension(), **exhaust())

        assert np.max(result.extensionThroughThicknessDrop) \
               < 0.01 * result.extensionPeakWallTemperature

    def testTheMarginIsReportedAgainstTheMaterialLimit(self):

        contour = conicalExtension()
        contour['recoveryTemperature'] = np.linspace(1400.0, 1000.0, 61)
        contour['staticTemperature'] = np.linspace(800.0, 500.0, 61)
        result = radiativeNozzleExtension(
            shell(innerEmissivity = 0.7, outerEmissivity = 0.7, material = 'C103',
                  atmosphere = 'inert'), **contour, **exhaust())

        # 1400 degC in kelvin, which is the store's inert limit for C103.
        assert result.extensionTemperatureLimit == pytest.approx(1673.15)
        assert result.extensionTemperatureMargin == pytest.approx(
            result.extensionTemperatureLimit - result.extensionPeakWallTemperature)

    def testNoMaterialMeansNoMargin(self):

        result = radiativeNozzleExtension(shell(), **conicalExtension(), **exhaust())

        assert result.extensionTemperatureLimit is None
        assert result.extensionTemperatureMargin is None

class TestExtensionSolverRefusals:

    '''What the solver will not pretend to answer.'''

    def testTwoStationsAreBothBoundaries(self):

        with pytest.raises(InvalidInputError):
            radiativeNozzleExtension(
                shell(), axialPosition = np.array([0.0, 0.1]), radius = np.array([0.1, 0.2]),
                machNumber = np.array([2.6, 3.0]), staticTemperature = np.array([1500.0, 1200.0]),
                recoveryTemperature = np.array([2600.0, 2200.0]), **exhaust())

    def testMismatchedStationArraysAreRefused(self):

        contour = conicalExtension()
        contour['radius'] = contour['radius'][:-1]

        with pytest.raises(InvalidInputError):
            radiativeNozzleExtension(shell(), **contour, **exhaust())

    def testAShellWithNoThicknessIsRefused(self):

        with pytest.raises(InvalidInputError):
            radiativeNozzleExtension(shell(thickness = 0.0), **conicalExtension(), **exhaust())

    def testAShellWithNoConductivityIsRefused(self):

        with pytest.raises(InvalidInputError):
            radiativeNozzleExtension(shell(thermalConductivity = 0.0), **conicalExtension(),
                                     **exhaust())

    def testASurfaceThatRadiatesNothingIsRefused(self):

        # There is no equilibrium at all: the wall heats until something else carries the flux,
        # which is a different problem from the one this solves.
        with pytest.raises(InvalidInputError):
            radiativeNozzleExtension(shell(outerEmissivity = 0.0), **conicalExtension(),
                                     **exhaust())
        with pytest.raises(InvalidInputError):
            radiativeNozzleExtension(shell(outerViewFactor = 0.0), **conicalExtension(),
                                     **exhaust())
