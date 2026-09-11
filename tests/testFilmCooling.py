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

from NOVA.filmCooling import (FilmCoolingResult, HATCHPAPELLONSET, filmCoolingArrays,
                              filmDrivingTemperature, filmTransferCoefficient,
                              hatchPapellEffectiveness, velocityRatioCorrection)
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

class TestEffectivenessBehaviour:

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
            recoveryTemperature = np.full(stations, 3400.0),
            meanThermalConductivity = np.full(stations, 0.30),
            meanDensity = np.full(stations, 1.5),
            meanViscosity = np.full(stations, 8.0e-5),
            meanPrandtlNumber = np.full(stations, 0.60))

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
        reynolds = contour['meanDensity'][0] * contour['gasVelocity'][0] * diameter \
                   / contour['meanViscosity'][0]
        coefficient = filmTransferCoefficient(contour['meanThermalConductivity'][0], diameter,
                                              reynolds, contour['meanPrandtlNumber'][0])
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
            recoveryTemperature = np.full(stations, 3400.0),
            meanThermalConductivity = np.full(stations, 0.30),
            meanDensity = np.full(stations, 1.5),
            meanViscosity = np.full(stations, 8.0e-5),
            meanPrandtlNumber = np.full(stations, 0.60),
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
