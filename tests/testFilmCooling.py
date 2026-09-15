# -- NOVA: Film Cooling Tests -- #

'''

Verification of the film cooling closure in NOVA.filmCooling.

The correlation is Hatch and Papell, NASA TN D-130, equation (12). What is checked here is that
the code is that equation: the two empirical groups, the two branches of the velocity-ratio
correction, the onset below which effectiveness is exactly one, and the limits the derivation
requires. Those are transcription checks, and transcription is the thing most likely to be wrong.

What is not checked here is whether the equation describes a rocket. It was fitted to a flat
plate below 1100 K at subsonic speed, and the module docstring says so. The source states its own
accuracy, within five per cent on film-cooled wall temperature over an effectiveness range of
roughly 0.2 to 1.0, and that figure is the source's claim rather than a measurement made here.
Its figure 7 plots the equation as `exp(-Z)` against the correlating abscissa and the line leaves
the bottom of the frame, at an effectiveness of 0.1, at an abscissa near 2.3; `exp(-2.303)` is
0.100, which is the read that confirms the sign and the grouping.

Author: Sean Bowman

'''

import numpy as np
import pytest

from NOVA.filmCooling import (FILMCONDUCTIVITYEXPONENT, FILMPRANDTLEXPONENT,
                              FILMVISCOSITYEXPONENT, FilmCoolingResult, HATCHPAPELLONSET,
                              SP8124EFFECTIVENESSASYMPTOTE, SP8124EFFECTIVENESSONSET,
                              SP8124THROATMULTIPLIER,
                              entrainmentAdiabaticWallTemperature, entrainmentEffectiveness,
                              entrainmentFilmArrays, entrainmentMultiplier,
                              filmCoolingArrays, filmDrivingTemperature,
                              filmTransferCoefficient, hatchPapellEffectiveness,
                              referenceEntrainmentFraction, referenceTemperatureCorrection,
                              velocityRatioCorrection, velocityRatioFunction,
                              wallMixtureRatio)
from NOVA.utils import InvalidInputError

def publishedEffectiveness(transferGroup, slotHeight, gasVelocity, coolantVelocity,
                           diffusivity):

    '''

    Equation (12) written out independently of the module, for the transcription check.

        ln eta = - [ X - 0.04 ] (S V_g / alpha_c)^0.125 f(V_g / V_c)

    '''

    if transferGroup <= 0.04:
        return 1.0

    ratio = gasVelocity / coolantVelocity
    if ratio >= 1.0:
        correction = 1.0 + 0.4 * np.arctan(ratio - 1.0)
    else:
        correction = (1.0 / ratio)**(1.5 * (1.0 / ratio - 1.0))

    return np.exp(-(transferGroup - 0.04)
                  * (slotHeight * gasVelocity / diffusivity)**0.125 * correction)

class TestTheCorrelationIsTheOnePublished:

    '''Equation (12) and (12a), against an independent writing of the same two equations.'''

    @pytest.mark.parametrize('transferGroup', [0.0, 0.02, 0.04, 0.05, 0.2, 0.5, 1.0, 2.5])
    @pytest.mark.parametrize('velocityRatio', [0.5, 1.0, 2.0])
    def testItReproducesTheEquation(self, transferGroup, velocityRatio):

        arguments = (transferGroup, 0.0025, 400.0 * velocityRatio, 400.0, 2.5e-5)

        assert hatchPapellEffectiveness(*arguments) == pytest.approx(
            publishedEffectiveness(*arguments), rel = 1.0e-13)

    def testTheOnsetGroupIsTheOnePublished(self):

        # Equation (12a): the wall has not warmed above the coolant below this group.
        assert HATCHPAPELLONSET == 0.04

    @pytest.mark.parametrize('transferGroup', [0.0, 0.01, 0.039, 0.04])
    def testEffectivenessIsExactlyOneBelowTheOnset(self, transferGroup):

        assert hatchPapellEffectiveness(transferGroup, 0.0025, 400.0, 400.0, 2.5e-5) == 1.0

    def testItIsContinuousAcrossTheOnset(self):

        justAbove = hatchPapellEffectiveness(0.04 + 1.0e-9, 0.0025, 400.0, 400.0, 2.5e-5)

        assert justAbove == pytest.approx(1.0, abs = 1.0e-6)

    def testTheFigureLineCrossesWhereTheEquationSaysItShould(self):

        # Figure 7 plots the equation as exp(-Z) and its line leaves the frame at an
        # effectiveness of 0.1. That happens at Z = ln(10) = 2.303, which is the read that
        # confirms the sign and the grouping rather than only the algebra.
        slotHeight, gasVelocity, diffusivity = 0.0025, 400.0, 2.5e-5
        diffusionGroup = (slotHeight * gasVelocity / diffusivity)**0.125
        transferGroup = np.log(10.0) / diffusionGroup + HATCHPAPELLONSET

        assert hatchPapellEffectiveness(
            transferGroup, slotHeight, gasVelocity, gasVelocity, diffusivity) == \
            pytest.approx(0.1, rel = 1.0e-12)

class TestEffectivenessBehavior:

    '''The shape the derivation requires, regardless of the empirical fit on top of it.'''

    @pytest.mark.parametrize('transferGroup', [0.05, 0.3, 1.0, 3.0, 10.0])
    def testItStaysWithinItsPhysicalBounds(self, transferGroup):

        value = hatchPapellEffectiveness(transferGroup, 0.0025, 400.0, 400.0, 2.5e-5)

        assert 0.0 < value <= 1.0

    def testItDecaysMonotonicallyWithTheGroup(self):

        groups = np.linspace(0.05, 3.0, 40)
        values = [hatchPapellEffectiveness(g, 0.0025, 400.0, 400.0, 2.5e-5) for g in groups]

        assert all(later < earlier for earlier, later in zip(values, values[1:]))

    def testItApproachesZeroFarDownstream(self):

        # The derivation's own requirement: as x goes to infinity the wall approaches the
        # adiabatic wall temperature of the main stream.
        assert hatchPapellEffectiveness(50.0, 0.0025, 400.0, 400.0, 2.5e-5) < 1.0e-6

    def testMoreCoolantSurvivesFurther(self):

        # The group carries the coolant heat capacity rate in its denominator, so doubling the
        # flow halves the group at a given station.
        assert hatchPapellEffectiveness(0.5, 0.0025, 400.0, 400.0, 2.5e-5) > \
               hatchPapellEffectiveness(1.0, 0.0025, 400.0, 400.0, 2.5e-5)

    def testANarrowerSlotCoolsBetterAtTheSameFlow(self):

        # The diffusion group rewards a narrow slot: more of the coolant's mass is doing the
        # absorbing rather than being carried past.
        narrow = hatchPapellEffectiveness(0.5, 0.0010, 400.0, 400.0, 2.5e-5)
        wide = hatchPapellEffectiveness(0.5, 0.0100, 400.0, 400.0, 2.5e-5)

        assert narrow > wide

class TestVelocityRatioCorrection:

    '''Equations (10) and (11), and the fact that they meet.'''

    def testItIsExactlyOneAtMatchedVelocities(self):

        assert velocityRatioCorrection(400.0, 400.0) == 1.0

    def testTheTwoBranchesMeet(self):

        justBelow = velocityRatioCorrection(400.0 * (1.0 - 1.0e-9), 400.0)
        justAbove = velocityRatioCorrection(400.0 * (1.0 + 1.0e-9), 400.0)

        assert justBelow == pytest.approx(justAbove, abs = 1.0e-6)

    @pytest.mark.parametrize('ratio', [0.25, 0.5, 0.8, 1.25, 2.0, 5.0, 15.0])
    def testAnyMismatchCostsEffectiveness(self, ratio):

        # Both branches rise above one, because shear between the streams breaks the film up
        # whichever way the mismatch runs.
        assert velocityRatioCorrection(400.0 * ratio, 400.0) > 1.0

    def testTheFastBranchIsTheArctangentForm(self):

        assert velocityRatioCorrection(1200.0, 400.0) == pytest.approx(
            1.0 + 0.4 * np.arctan(2.0), rel = 1.0e-13)

    def testTheSlowBranchIsThePowerForm(self):

        assert velocityRatioCorrection(200.0, 400.0) == pytest.approx(
            2.0**(1.5 * 1.0), rel = 1.0e-13)

    def testOverInjectingIsPenalisedHarderThanUnderInjecting(self):

        # The correlation is strongly asymmetric, and the asymmetry is the design lesson. A
        # coolant leaving the slot faster than the core jets away from the wall and mixes hard; a
        # slow one is simply dragged along. Doubling the coolant velocity above the core costs a
        # factor of 2.83 in the exponent, while halving it costs only 1.31.
        fastCoolant = velocityRatioCorrection(400.0, 800.0)
        slowCoolant = velocityRatioCorrection(400.0, 200.0)

        assert fastCoolant > slowCoolant
        assert fastCoolant == pytest.approx(2.0**1.5, rel = 1.0e-12)
        assert slowCoolant == pytest.approx(1.0 + 0.4 * np.arctan(1.0), rel = 1.0e-12)

    def testTheSlowCoolantPenaltySaturates(self):

        # The arctangent branch is bounded: however much faster the core runs, the penalty tends
        # to 1 + 0.4 pi/2. The other branch has no such bound, which is why the design guidance
        # brackets the ratio just below one rather than just above it.
        assert velocityRatioCorrection(4.0e6, 400.0) == pytest.approx(
            1.0 + 0.2 * np.pi, rel = 1.0e-4)
        assert velocityRatioCorrection(400.0, 1600.0) > 10.0

    def testAStationaryStreamIsRefused(self):

        with pytest.raises(InvalidInputError):
            velocityRatioCorrection(0.0, 400.0)

        with pytest.raises(InvalidInputError):
            velocityRatioCorrection(400.0, 0.0)

class TestFilmTransferCoefficient:

    '''Assumption 6 of the source, which is where the correlating group comes from.'''

    def testItIsTheCorrelationPublished(self):

        value = filmTransferCoefficient(0.3, 0.1, 5.0e5, 0.6)
        expected = 0.0265 * (0.3 / 0.1) * 5.0e5**0.8 * 0.6**0.3

        assert value == pytest.approx(expected, rel = 1.0e-13)

    def testItScalesTheWayTurbulentPipeFlowDoes(self):

        # Re^0.8 is the whole reason the throat is the worst station on a nozzle.
        single = filmTransferCoefficient(0.3, 0.1, 1.0e5, 0.6)
        double = filmTransferCoefficient(0.3, 0.1, 2.0e5, 0.6)

        assert double / single == pytest.approx(2.0**0.8, rel = 1.0e-12)

    def testADuctWithNoDiameterIsRefused(self):

        with pytest.raises(InvalidInputError):
            filmTransferCoefficient(0.3, 0.0, 5.0e5, 0.6)

class TestDrivingTemperature:

    '''

    The definition of effectiveness, rearranged.

    The limit that matters most is the one at zero: a station the film has not reached has to be
    driven by exactly what it was driven by before, or a jacket with a film somewhere else stops
    reproducing a jacket with no film at all.

    '''

    def testFullEffectivenessGivesTheCoolantTemperature(self):

        assert filmDrivingTemperature(3400.0, 1.0, 400.0) == pytest.approx(400.0, rel = 1.0e-13)

    def testZeroEffectivenessGivesTheRecoveryTemperatureToTheBit(self):

        assert filmDrivingTemperature(3400.0, 0.0, 400.0) == 3400.0

    @pytest.mark.parametrize('effectiveness', [0.1, 0.25, 0.5, 0.75, 0.9])
    def testItLiesBetweenTheTwo(self, effectiveness):

        value = filmDrivingTemperature(3400.0, effectiveness, 400.0)

        assert 400.0 < value < 3400.0

    def testItWorksOnArrays(self):

        values = filmDrivingTemperature(np.full(4, 3400.0), np.array([0.0, 0.5, 1.0, 0.25]),
                                        400.0)

        assert values[0] == 3400.0
        assert values[2] == pytest.approx(400.0, rel = 1.0e-13)

class TestTheStationMarch:

    '''

    Accumulating the correlating group along a contour, which is where NOVA leaves the source.

    The published group is `h L x / (m_dot c_p)` for a flat plate at one coefficient. A nozzle has
    neither, so the group is integrated instead. The reduction test below is the check that the
    generalisation is the same thing where the two overlap.

    '''

    def contour(self, stations = 60, radius = 0.05):

        '''A straight duct, so the flat-plate reduction has something to reduce to.'''

        return dict(
            axialPosition = np.linspace(0.0, 1.0, stations),
            radius = np.full(stations, radius),
            gasVelocity = np.full(stations, 400.0),
            gasStaticTemperature = np.full(stations, 3000.0),
            recoveryTemperature = np.full(stations, 3400.0),
            gasThermalConductivity = np.full(stations, 0.30),
            gasDensity = np.full(stations, 1.5),
            gasViscosity = np.full(stations, 8.0e-5),
            gasPrandtlNumber = np.full(stations, 0.60))

    def film(self, **overrides):

        '''The film definition the tests vary from.'''

        arguments = dict(injectionPosition = 0.0, slotHeight = 0.0020,
                         coolantMassFlow = 0.5, coolantSpecificHeat = 2500.0,
                         coolantTemperature = 400.0, coolantThermalDiffusivity = 2.5e-5,
                         coolantVelocity = 400.0)
        arguments.update(overrides)

        return arguments

    def testTheGroupReducesToTheFlatPlateForm(self):

        # Constant radius and constant properties, so the integral has to come back as the
        # published h L x / (m_dot c_p) with L the circumference and x the distance from the slot.
        contour = self.contour()
        result = filmCoolingArrays(**contour, **self.film())

        radius = contour['radius'][0]
        diameter = 2.0 * radius
        reynolds = contour['gasDensity'][0] * contour['gasVelocity'][0] * diameter \
                   / contour['gasViscosity'][0]
        coefficient = filmTransferCoefficient(contour['gasThermalConductivity'][0], diameter,
                                              reynolds, contour['gasPrandtlNumber'][0]) \
                      * referenceTemperatureCorrection(contour['gasStaticTemperature'][0], 400.0)
        area = 2.0 * np.pi * radius * contour['axialPosition'][-1]
        expected = coefficient * area / (0.5 * 2500.0)

        assert result.transferGroup[-1] == pytest.approx(expected, rel = 1.0e-12)

    def testUpstreamOfTheSlotNothingIsTouched(self):

        contour = self.contour()
        result = filmCoolingArrays(**contour, **self.film(injectionPosition = 0.5))

        upstream = slice(0, result.injectionIndex)

        assert np.all(result.effectiveness[upstream] == 0.0)
        assert np.array_equal(result.drivingTemperature[upstream],
                              contour['recoveryTemperature'][upstream])

    def testTheGroupGrowsAndTheEffectivenessFallsDownstream(self):

        result = filmCoolingArrays(**self.contour(), **self.film())
        downstream = slice(result.injectionIndex, None)

        group = result.transferGroup[downstream]
        effectiveness = result.effectiveness[downstream]

        assert np.all(np.diff(group) > 0.0)
        assert np.all(np.diff(effectiveness) <= 0.0)

    def testTheFilmStartsFullyEffectiveAtTheSlot(self):

        result = filmCoolingArrays(**self.contour(), **self.film())

        assert result.effectiveness[result.injectionIndex] == 1.0
        assert result.drivingTemperature[result.injectionIndex] == pytest.approx(400.0)

    def testMoreCoolantReachesFurther(self):

        thin = filmCoolingArrays(**self.contour(), **self.film(coolantMassFlow = 0.25))
        thick = filmCoolingArrays(**self.contour(), **self.film(coolantMassFlow = 1.0))

        assert thick.survivalLength > thin.survivalLength

    def testTheSurvivalLengthIsWhereTheCorrelationStopsBeingTrusted(self):

        # Defined at an effectiveness of 0.3, which is where the source says its equation turns
        # pessimistic, rather than at the point the film vanishes.
        result = filmCoolingArrays(**self.contour(), **self.film())
        downstream = result.effectiveness[result.injectionIndex:]
        useful = downstream[downstream >= 0.3]

        assert useful.size > 0
        assert result.survivalLength > 0.0

    def testTheFilmMassFluxIsZeroThroughout(self):

        # Slot film cooling puts its whole effect into the effectiveness. Blowing the gas-side
        # coefficient as well would count the film twice.
        result = filmCoolingArrays(**self.contour(), **self.film())

        assert np.all(result.filmMassFlux == 0.0)

    def testAConvergingContourUsesArcLengthRatherThanAxialStep(self):

        # A steep wall covers more area per axial step than a straight one, so the group has to
        # grow faster. Taking the axial step for the arc length would understate it.
        stations = 60
        straight = self.contour(stations)
        tapered = dict(straight)
        tapered['radius'] = np.linspace(0.05, 0.02, stations)

        assert filmCoolingArrays(**tapered, **self.film()).transferGroup[-1] != \
               filmCoolingArrays(**straight, **self.film()).transferGroup[-1]

    def testTheResultIsTheDocumentedShape(self):

        result = filmCoolingArrays(**self.contour(), **self.film())

        assert isinstance(result, FilmCoolingResult)
        for name in ('effectiveness', 'drivingTemperature', 'transferGroup', 'filmMassFlux'):
            assert getattr(result, name).size == 60, name

class TestStationMarchRefusals:

    '''What the march will not do quietly.'''

    def arguments(self, **overrides):

        stations = 20
        arguments = dict(
            axialPosition = np.linspace(0.0, 1.0, stations),
            radius = np.full(stations, 0.05),
            gasVelocity = np.full(stations, 400.0),
            gasStaticTemperature = np.full(stations, 3400.0),
            recoveryTemperature = np.full(stations, 3400.0),
            gasThermalConductivity = np.full(stations, 0.30),
            gasDensity = np.full(stations, 1.5),
            gasViscosity = np.full(stations, 8.0e-5),
            gasPrandtlNumber = np.full(stations, 0.60),
            injectionPosition = 0.0, slotHeight = 0.0020,
            coolantMassFlow = 0.5, coolantSpecificHeat = 2500.0,
            coolantTemperature = 400.0, coolantThermalDiffusivity = 2.5e-5,
            coolantVelocity = 400.0)
        arguments.update(overrides)

        return arguments

    def testMismatchedStationArraysAreRefused(self):

        with pytest.raises(InvalidInputError):
            filmCoolingArrays(**self.arguments(radius = np.full(19, 0.05)))

    def testAFilmWithNoFlowIsRefused(self):

        with pytest.raises(InvalidInputError):
            filmCoolingArrays(**self.arguments(coolantMassFlow = 0.0))

    def testASlotPastTheEndOfTheContourIsRefused(self):

        with pytest.raises(InvalidInputError):
            filmCoolingArrays(**self.arguments(injectionPosition = 2.0))

    def testANegativeTransferGroupIsRefused(self):

        with pytest.raises(InvalidInputError):
            hatchPapellEffectiveness(-0.1, 0.0025, 400.0, 400.0, 2.5e-5)

    def testASlotWithNoHeightIsRefused(self):

        with pytest.raises(InvalidInputError):
            hatchPapellEffectiveness(0.5, 0.0, 400.0, 400.0, 2.5e-5)

class TestReferenceTemperatureCorrection:

    '''

    Assumption 6 of the source evaluates every property at the mean of the gas and coolant
    temperatures. The correction moves a coefficient built at the gas temperature onto that mean.

    '''

    def testACoolantAtTheGasTemperatureIsExactlyTheIdentity(self):

        # No film means no property shift, and the caller relies on this being bitwise one so a
        # station with no temperature difference is untouched.
        assert referenceTemperatureCorrection(3000.0, 3000.0) == 1.0

    def testAColdCoolantRaisesTheCoefficient(self):

        # The conductivity falls, but the density rises as 1/T and the viscosity falls, and those
        # two move Re^0.8 further than the conductivity moves. Reading the conductivity alone
        # gives the wrong sign, which is the mistake this test exists to pin.
        assert referenceTemperatureCorrection(3400.0, 250.0) > 1.0

    def testTheCorrectionGrowsAsTheCoolantGetsColder(self):

        colder = [referenceTemperatureCorrection(3400.0, temperature)
                  for temperature in (3000.0, 2000.0, 1000.0, 250.0)]

        assert colder == sorted(colder)

    def testTheMagnitudeMatchesTheMeasuredExhaust(self):

        # A LOX/LH2 station at 3400 K with a 250 K film sits at T*/T = 0.537, and the exponents
        # measured for that exhaust put the correction near 1.3. A regression here means the
        # stored exponents moved.
        assert referenceTemperatureCorrection(3400.0, 250.0) == pytest.approx(1.30, abs = 0.03)

    def testItIsTheDocumentedPowerLaw(self):

        power = FILMCONDUCTIVITYEXPONENT - 0.8 - 0.8 * FILMVISCOSITYEXPONENT \
                + 0.3 * FILMPRANDTLEXPONENT
        expected = (0.5 * (3400.0 + 250.0) / 3400.0)**power

        assert referenceTemperatureCorrection(3400.0, 250.0) == pytest.approx(expected,
                                                                              rel = 1.0e-14)

    def testTheExponentsAreOverridable(self):

        # A propellant outside the fitted set can supply its own, and zero exponents throughout
        # reduce the factor to the density term alone, (T*/T)^-0.8.
        expected = (0.5 * (3400.0 + 250.0) / 3400.0)**(-0.8)

        assert referenceTemperatureCorrection(3400.0, 250.0, 0.0, 0.0, 0.0) \
               == pytest.approx(expected, rel = 1.0e-14)

    def testTheNetPowerIsNegativeForEveryExhaustMeasured(self):

        # The five propellant fits in the module header. If any of them turned positive the
        # correction would change sign and the film would read as safer than it is.
        for conductivity, viscosity, prandtl in ((1.000, 0.816, 0.071), (1.053, 0.813, 0.011),
                                                 (0.997, 0.808, 0.065), (0.979, 0.739, -0.058),
                                                 (1.030, 0.758, -0.068)):
            assert referenceTemperatureCorrection(3400.0, 250.0,
                                                  conductivity, viscosity, prandtl) > 1.0

    def testTheSpreadAcrossPropellantsStaysInsideThreePerCent(self):

        factors = [referenceTemperatureCorrection(3400.0, 250.0, conductivity, viscosity, prandtl)
                   for conductivity, viscosity, prandtl in ((1.000, 0.816, 0.071),
                                                            (1.053, 0.813, 0.011),
                                                            (0.997, 0.808, 0.065),
                                                            (0.979, 0.739, -0.058),
                                                            (1.030, 0.758, -0.068))]

        assert max(factors) / min(factors) - 1.0 < 0.03

    def testANonPositiveTemperatureIsRefused(self):

        with pytest.raises(InvalidInputError):
            referenceTemperatureCorrection(0.0, 250.0)
        with pytest.raises(InvalidInputError):
            referenceTemperatureCorrection(3400.0, -1.0)

class TestTheCorrectionReachesTheMarch:

    '''

    The correction has to arrive inside the accumulated group, not sit beside it unused.

    '''

    def contour(self, staticTemperature, stations = 60):

        return dict(
            axialPosition = np.linspace(0.0, 1.0, stations),
            radius = np.full(stations, 0.05),
            gasVelocity = np.full(stations, 400.0),
            gasStaticTemperature = np.full(stations, staticTemperature),
            recoveryTemperature = np.full(stations, 3400.0),
            gasThermalConductivity = np.full(stations, 0.30),
            gasDensity = np.full(stations, 1.5),
            gasViscosity = np.full(stations, 8.0e-5),
            gasPrandtlNumber = np.full(stations, 0.60))

    def film(self, **overrides):

        arguments = dict(injectionPosition = 0.0, slotHeight = 0.0020,
                         coolantMassFlow = 0.5, coolantSpecificHeat = 2500.0,
                         coolantTemperature = 400.0, coolantThermalDiffusivity = 2.5e-5,
                         coolantVelocity = 400.0)
        arguments.update(overrides)

        return arguments

    def testAMatchedCoolantLeavesTheGroupUntouchedToTheBit(self):

        # Coolant at the gas temperature makes every station's correction exactly one, so the
        # group must equal what the uncorrected correlation would have produced.
        matched = filmCoolingArrays(**self.contour(400.0), **self.film())

        assert np.all(matched.propertyCorrection == 1.0)

    def testAColdFilmShortensTheFilm(self):

        warm = filmCoolingArrays(**self.contour(600.0), **self.film())
        hot = filmCoolingArrays(**self.contour(3400.0), **self.film())

        # A hotter core means a larger correction, a larger group and less reach.
        assert hot.propertyCorrection[-1] > warm.propertyCorrection[-1]
        assert hot.transferGroup[-1] > warm.transferGroup[-1]
        assert hot.survivalLength <= warm.survivalLength

    def testTheCorrectionIsOneWhereNoFilmReaches(self):

        result = filmCoolingArrays(**self.contour(3400.0), **self.film(injectionPosition = 0.5))

        assert np.all(result.propertyCorrection[:result.injectionIndex + 1] == 1.0)
        assert np.all(result.propertyCorrection[result.injectionIndex + 1:] > 1.0)

    def testTheGroupScalesWithTheCorrection(self):

        # One constant-property duct, so the whole group is a single factor times the correction.
        result = filmCoolingArrays(**self.contour(3400.0), **self.film())
        uncorrected = filmCoolingArrays(**self.contour(400.0), **self.film())
        factor = referenceTemperatureCorrection(3400.0, 400.0)

        assert result.transferGroup[-1] == pytest.approx(factor * uncorrected.transferGroup[-1],
                                                         rel = 1.0e-12)

class TestTheEntrainmentMultiplier:

    """Figure 17 and the convergent-section recommendation of SP-8124 section 3.5.2."""

    def testItStartsAtTheInjectionValue(self):

        assert entrainmentMultiplier(3.0, 0.0, 3.5) == 3.5

    def testItReachesTheThroatValueAtTheThroat(self):

        assert entrainmentMultiplier(1.0, 1.0, 3.5) == SP8124THROATMULTIPLIER

    def testItFallsLinearlyThroughTheConvergentSection(self):

        midpoint = entrainmentMultiplier(2.0, 0.5, 4.0)

        assert midpoint == pytest.approx(0.5 * (4.0 + SP8124THROATMULTIPLIER))

    def testTheExpansionCurveStartsWhereTheConvergentOneEnds(self):

        # Figure 17 is anchored at the throat value the body text gives, so the two halves of
        # the recommendation meet rather than stepping.
        assert entrainmentMultiplier(1.0, None) == pytest.approx(SP8124THROATMULTIPLIER)

    def testTheExpansionCurveFallsMonotonically(self):

        values = [entrainmentMultiplier(ratio, None) for ratio in np.linspace(1.0, 28.0, 60)]

        assert all(later <= earlier for earlier, later in zip(values, values[1:]))

    def testItReachesTheValueTheBodyTextGivesAtAreaRatioTwentyEight(self):

        assert entrainmentMultiplier(28.0, None) == pytest.approx(0.35)

    def testAMultiplierOfZeroIsRefused(self):

        with pytest.raises(InvalidInputError):
            entrainmentMultiplier(4.0, 0.0, 0.0)

class TestTheVelocityRatioFunction:

    """Figure A-1, whose lower branch the figure states exactly."""

    @pytest.mark.parametrize('ratio', [0.2, 0.5, 0.9, 1.0])
    def testTheStatedBranchIsExact(self, ratio):

        assert velocityRatioFunction(ratio) == pytest.approx(ratio**1.5, rel = 1.0e-13)

    def testTheTwoBranchesMeetAtMatchedVelocity(self):

        justBelow = velocityRatioFunction(1.0 - 1.0e-9)
        justAbove = velocityRatioFunction(1.0 + 1.0e-9)

        assert justBelow == pytest.approx(justAbove, abs = 1.0e-6)

    def testItFallsAwayOnBothSidesOfTheRecommendedBand(self):

        # SP-8124 3.5.3 recommends injecting at a coolant to core velocity ratio of 0.9 to 1.15.
        # f peaks near there, and f sits in the denominator of the entrainment fraction, so a
        # peak in f is a minimum in mixing.
        peak = max(velocityRatioFunction(ratio) for ratio in np.linspace(0.9, 1.3, 40))

        assert velocityRatioFunction(0.3) < peak
        assert velocityRatioFunction(6.0) < peak

    def testAStationaryFilmIsRefused(self):

        with pytest.raises(InvalidInputError):
            velocityRatioFunction(0.0)

class TestTheReferenceEntrainmentFraction:

    """psi_r, which is dimensionless and so needs no unit conversion."""

    def conditions(self, **overrides):

        arguments = dict(coolantVelocity = 300.0, coreVelocity = 300.0, coolantDensity = 6.0,
                         coreDensity = 3.0, coolantViscosity = 8.0e-6, slotHeight = 0.0015)
        arguments.update(overrides)

        return arguments

    def testItReproducesTheAppendixExpression(self):

        arguments = self.conditions(coolantVelocity = 150.0)
        ratio = 150.0 / 300.0
        reynolds = 6.0 * 150.0 * 0.0015 / 8.0e-6
        expected = 0.1 * ratio / ((6.0 / 3.0)**0.15 * reynolds**0.25 * ratio**1.5)

        assert referenceEntrainmentFraction(**arguments) == pytest.approx(expected, rel = 1.0e-13)

    def testASlowerFilmEntrainsHarder(self):

        # f goes as the velocity ratio to the 1.5 and sits in the denominator, so psi_r goes as
        # the ratio to the minus a half. A film far slower than the core carries a large velocity
        # difference across its shear layer and mixes hard, which is what the recommended
        # injection band exists to avoid.
        slow = referenceEntrainmentFraction(**self.conditions(coolantVelocity = 60.0))
        matched = referenceEntrainmentFraction(**self.conditions(coolantVelocity = 300.0))

        assert slow > matched

    def testANarrowerSlotEntrainsHarder(self):

        narrow = referenceEntrainmentFraction(**self.conditions(slotHeight = 0.0005))
        wide = referenceEntrainmentFraction(**self.conditions(slotHeight = 0.0050))

        assert narrow > wide

    def testItIsDimensionless(self):

        # Scaling every length, every velocity and every density by the same factors must leave
        # psi_r alone if the groups really are dimensionless as the appendix implies.
        base = referenceEntrainmentFraction(**self.conditions())
        scaled = referenceEntrainmentFraction(**self.conditions(
            coolantVelocity = 600.0, coreVelocity = 600.0, coolantDensity = 12.0,
            coreDensity = 6.0, coolantViscosity = 8.0e-6 * 2.0 * 2.0))

        assert scaled == pytest.approx(base, rel = 1.0e-13)

    def testAnAbsentSlotIsRefused(self):

        with pytest.raises(InvalidInputError):
            referenceEntrainmentFraction(**self.conditions(slotHeight = 0.0))

class TestTheEntrainmentEffectiveness:

    """Figure A-2, whose two limits the figure prints."""

    @pytest.mark.parametrize('ratio', [0.0, 0.01, 0.05, 0.06])
    def testItIsExactlyOneBelowTheOnset(self, ratio):

        assert entrainmentEffectiveness(ratio) == 1.0

    @pytest.mark.parametrize('ratio', [1.4, 3.0, 10.0, 100.0])
    def testItIsTheAsymptoticFormAboveTheJoin(self, ratio):

        assert entrainmentEffectiveness(ratio) == pytest.approx(1.32 / (1.0 + ratio),
                                                                rel = 1.0e-13)

    def testItIsContinuousAtBothJoins(self):

        for join in (SP8124EFFECTIVENESSONSET, SP8124EFFECTIVENESSASYMPTOTE):
            below = entrainmentEffectiveness(join * (1.0 - 1.0e-9))
            above = entrainmentEffectiveness(join * (1.0 + 1.0e-9))
            assert below == pytest.approx(above, abs = 1.0e-6), join

    def testItFallsMonotonicallyOverSixDecades(self):

        values = [entrainmentEffectiveness(ratio) for ratio in np.logspace(-3.0, 3.0, 400)]

        assert all(later <= earlier + 1.0e-15 for earlier, later in zip(values, values[1:]))

    def testItStaysWithinItsPhysicalBounds(self):

        values = [entrainmentEffectiveness(ratio) for ratio in np.logspace(-3.0, 3.0, 400)]

        assert all(0.0 < value <= 1.0 for value in values)

    def testTheInterpolatedBandSitsBelowTheClippedAsymptote(self):

        # Clipping the asymptotic form at one would have been simpler. It reaches one only at a
        # ratio of 0.32 while the source says effectiveness leaves one at 0.06, so it overstates
        # effectiveness through the band, which is the unsafe direction. This pins that the
        # interpolation does not do that.
        for ratio in (0.4, 0.6, 0.8, 1.0, 1.2):
            assert entrainmentEffectiveness(ratio) <= min(1.0, 1.32 / (1.0 + ratio)) + 1.0e-12

    def testANegativeRatioIsRefused(self):

        with pytest.raises(InvalidInputError):
            entrainmentEffectiveness(-0.1)

class TestTheWallMixtureRatio:

    """The mass-transfer analogy, and the reason this model beats a flat-plate correlation."""

    def testNoFilmLeavesTheCoreMixtureRatio(self):

        assert wallMixtureRatio(0.0, 5.5, 0.0) == pytest.approx(5.5)

    def testAFullFuelFilmDrivesTheWallToPureFuel(self):

        assert wallMixtureRatio(1.0, 5.5, 0.0) == pytest.approx(0.0, abs = 1.0e-12)

    def testItFallsMonotonicallyWithEffectiveness(self):

        values = [wallMixtureRatio(value, 5.5, 0.0) for value in np.linspace(0.0, 1.0, 50)]

        assert all(later <= earlier for earlier, later in zip(values, values[1:]))

    def testAnOxidiserFilmDrivesTheWallOxidiserRich(self):

        # A pure oxidiser film is an infinite coolant mixture ratio, which the expression handles
        # without a special case. The wall going oxidiser-rich is the failure this reports.
        assert wallMixtureRatio(0.5, 5.5, np.inf) > 5.5

    def testANegativeMixtureRatioIsRefused(self):

        with pytest.raises(InvalidInputError):
            wallMixtureRatio(0.5, -1.0, 0.0)

    def testAnEffectivenessOutsideItsRangeIsRefused(self):

        with pytest.raises(InvalidInputError):
            wallMixtureRatio(1.5, 5.5, 0.0)

class TestTheEntrainmentAdiabaticWall:

    """

    The two limits of the non-reactive model, which have to be exact rather than close.

    """

    def testNoFilmReturnsTheRecoveryTemperatureToTheBit(self):

        # This is the anchor for the whole closure. With no film the entrainment model has to
        # reproduce what the station solve already computed, exactly, or the two disagree about
        # an engine with no film in it.
        for recovery in (2500.0, 3000.0, 3387.123456789):
            assert entrainmentAdiabaticWallTemperature(
                0.0, 3400.0, recovery, 5000.0, 14000.0, 250.0) == recovery

    def testAFullFilmReturnsTheCoolantsOwnRecoveryTemperature(self):

        # At an effectiveness of one the wall gas is all coolant, and the source's expression
        # then gives the coolant's recovery temperature at the core velocity rather than
        # something below the coolant temperature. That only holds if the coolant temperature is
        # read as a total, which is how it is documented.
        total, recovery, coreHeat, coolantHeat, coolant = 3400.0, 3100.0, 2000.0, 14000.0, 250.0
        expected = coolant - (total - recovery) * coreHeat / coolantHeat

        assert entrainmentAdiabaticWallTemperature(
            1.0, total, recovery, coreHeat, coolantHeat, coolant) == pytest.approx(expected,
                                                                                   rel = 1.0e-13)

    def testItFallsMonotonicallyWithEffectiveness(self):

        values = [entrainmentAdiabaticWallTemperature(value, 3400.0, 3100.0, 5000.0, 14000.0,
                                                      250.0)
                  for value in np.linspace(0.0, 1.0, 50)]

        assert all(later <= earlier for earlier, later in zip(values, values[1:]))

    def testAHigherCoolantHeatCapacityBuysMore(self):

        # Hydrogen's specific heat is about three times the exhaust's, and the enthalpy-weighted
        # mixing is why a small entrained fraction of it still pulls the wall down hard. A
        # linear blend on temperature, which is what Hatch and Papell does, cannot see this.
        light = entrainmentAdiabaticWallTemperature(0.1, 3400.0, 3100.0, 5000.0, 14000.0, 250.0)
        heavy = entrainmentAdiabaticWallTemperature(0.1, 3400.0, 3100.0, 5000.0, 3000.0, 250.0)

        assert light < heavy

    def testAStreamWithNoHeatCapacityIsRefused(self):

        with pytest.raises(InvalidInputError):
            entrainmentAdiabaticWallTemperature(0.5, 3400.0, 3100.0, 0.0, 14000.0, 250.0)

class TestTheEntrainmentMarch:

    """The station march, and what it does and does not fill in."""

    def contour(self, stations = 60, **overrides):

        radius = np.concatenate([np.linspace(0.09, 0.05, stations // 3),
                                 np.linspace(0.05, 0.30, stations - stations // 3)])
        arguments = dict(
            axialPosition = np.linspace(-0.10, 0.60, stations),
            radius = radius,
            gasVelocity = np.linspace(300.0, 3000.0, stations),
            gasDensity = np.linspace(4.0, 0.2, stations),
            totalTemperature = np.full(stations, 3400.0),
            recoveryTemperature = np.linspace(3390.0, 3050.0, stations),
            coreSpecificHeat = np.full(stations, 5000.0),
            massFluxRatio = np.full(stations, 1.0))
        arguments.update(overrides)

        return arguments

    def film(self, **overrides):

        arguments = dict(injectionPosition = -0.10, slotHeight = 0.0015,
                         coreMassFlow = 23.5, coolantMassFlow = 0.30,
                         coolantDensity = 6.0, coolantVelocity = 56.0,
                         coolantViscosity = 8.0e-6, coolantSpecificHeat = 14000.0,
                         coolantTotalTemperature = 250.0, coreMixtureRatio = 5.5)
        arguments.update(overrides)

        return arguments

    def testTheFilmStartsFullyEffectiveAtTheSlot(self):

        result = entrainmentFilmArrays(**self.contour(), **self.film())

        assert result.effectiveness[result.injectionIndex] == 1.0
        assert result.entrainmentFlowRatio[result.injectionIndex] == 0.0

    def testUpstreamOfTheSlotNothingIsTouched(self):

        contour = self.contour()
        result = entrainmentFilmArrays(**contour, **self.film(injectionPosition = 0.2))
        before = result.injectionIndex

        assert np.all(result.drivingTemperature[:before]
                      == contour['recoveryTemperature'][:before])
        assert np.all(result.effectiveness[:before] == 0.0)

    def testEntrainmentGrowsAndEffectivenessFallsDownstream(self):

        result = entrainmentFilmArrays(**self.contour(), **self.film())
        start = result.injectionIndex + 1

        assert np.all(np.diff(result.entrainmentFlowRatio[start:]) >= -1.0e-12)
        assert np.all(np.diff(result.effectiveness[start:]) <= 1.0e-12)

    def testMoreCoolantReachesFurther(self):

        thin = entrainmentFilmArrays(**self.contour(), **self.film(coolantMassFlow = 0.15))
        thick = entrainmentFilmArrays(**self.contour(), **self.film(coolantMassFlow = 0.60))

        assert thick.effectiveness[-1] > thin.effectiveness[-1]

    def testALargerMultiplierMixesTheFilmAwayFaster(self):

        # psi_m is the single largest lever in the model, and SP-8124 recommends 3 to 4 without
        # narrowing it further.
        gentle = entrainmentFilmArrays(**self.contour(), **self.film(),
                                       injectionMultiplier = 3.0)
        harsh = entrainmentFilmArrays(**self.contour(), **self.film(),
                                      injectionMultiplier = 4.0)

        assert harsh.effectiveness[-1] < gentle.effectiveness[-1]
        assert harsh.drivingTemperature.max() > gentle.drivingTemperature.max()

    def testTheDrivingTemperatureStaysBetweenTheCoolantAndTheRecoveryTemperature(self):

        contour = self.contour()
        result = entrainmentFilmArrays(**contour, **self.film())

        assert np.all(result.drivingTemperature <= contour['recoveryTemperature'] + 1.0e-9)
        assert np.all(result.drivingTemperature > 0.0)

    def testTheEntrainedFractionIsHeldAtTheWholeCore(self):

        # The bracket 2z - z^2 is the fraction of the core the mixing layer has swallowed and it
        # reaches one at z = 1. Past that the parabola turns over, which would say a film
        # entrains less the further it runs, so z is held. A very large multiplier forces it.
        result = entrainmentFilmArrays(**self.contour(), **self.film(),
                                       injectionMultiplier = 4000.0)
        coreRatio = 23.5 / 0.30

        assert result.entrainmentFlowRatio.max() == pytest.approx(coreRatio, rel = 1.0e-12)
        assert np.all(np.diff(result.entrainmentFlowRatio[result.injectionIndex:]) >= -1.0e-12)

    def testItFillsItsOwnDiagnosticsAndNotTheOtherModels(self):

        result = entrainmentFilmArrays(**self.contour(), **self.film())

        assert result.entrainmentFlowRatio is not None
        assert result.wallMixtureRatio is not None
        assert result.entrainmentMultiplier is not None
        assert result.transferGroup is None
        assert result.propertyCorrection is None

    def testTheWallRunsFuelRichUnderAFuelFilm(self):

        result = entrainmentFilmArrays(**self.contour(), **self.film())
        reached = result.wallMixtureRatio[result.injectionIndex:]

        assert np.all(reached <= 5.5 + 1.0e-12)

class TestEntrainmentMarchRefusals:

    """What the march will not pretend to answer."""

    def arguments(self, **overrides):

        stations = 40
        arguments = dict(
            axialPosition = np.linspace(-0.10, 0.60, stations),
            radius = np.linspace(0.09, 0.30, stations),
            gasVelocity = np.linspace(300.0, 3000.0, stations),
            gasDensity = np.linspace(4.0, 0.2, stations),
            totalTemperature = np.full(stations, 3400.0),
            recoveryTemperature = np.linspace(3390.0, 3050.0, stations),
            coreSpecificHeat = np.full(stations, 5000.0),
            massFluxRatio = np.full(stations, 1.0),
            injectionPosition = -0.10, slotHeight = 0.0015,
            coreMassFlow = 23.5, coolantMassFlow = 0.30,
            coolantDensity = 6.0, coolantVelocity = 56.0, coolantViscosity = 8.0e-6,
            coolantSpecificHeat = 14000.0, coolantTotalTemperature = 250.0,
            coreMixtureRatio = 5.5)
        arguments.update(overrides)

        return arguments

    def testMismatchedStationArraysAreRefused(self):

        with pytest.raises(InvalidInputError):
            entrainmentFilmArrays(**self.arguments(radius = np.linspace(0.09, 0.30, 39)))

    def testAFilmWithNoFlowIsRefused(self):

        with pytest.raises(InvalidInputError):
            entrainmentFilmArrays(**self.arguments(coolantMassFlow = 0.0))

    def testAnEngineWithNoCoreFlowIsRefused(self):

        with pytest.raises(InvalidInputError):
            entrainmentFilmArrays(**self.arguments(coreMassFlow = 0.0))

    def testASlotPastTheEndOfTheContourIsRefused(self):

        with pytest.raises(InvalidInputError):
            entrainmentFilmArrays(**self.arguments(injectionPosition = 2.0))

    def testAMixingLayerAsTallAsTheChamberIsRefused(self):

        with pytest.raises(InvalidInputError):
            entrainmentFilmArrays(**self.arguments(slotHeight = 0.2))
