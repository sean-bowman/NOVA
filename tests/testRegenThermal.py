'''

Tests for the regenerative cooling thermal model in regenThermal.py.

**The gas side is checked, but not validated against a measurement.** No published worked example
with a complete set of inputs and a stated answer was available to set the implementation against.
What is checked instead is everything that can be checked without one:

  - the stagnation viscosity constant, which is a unit conversion of the fit published in
    Huzel and Huang, NASA SP-125, and is verified as that conversion rather than taken on trust;
  - the dimensions, which must reduce to kg s^-3 K^-1, that is W/(m^2 K), exactly;
  - the exponent each input enters with, driven one at a time against the published form;
  - the limiting behavior, since the coefficient must fall as the area ratio grows and must rise
    as the wall gets colder.

Those establish that the implementation is the correlation it claims to be. They do not establish
that the correlation predicts a real engine, and nothing here should be read as saying so.

**The coolant side is not validated at all.** The correlation is Gnielinski, which is published
and whose range of validity is known, but nothing here checks the implementation against a
reference case.

What closes both gaps is a measurement: a fired engine with instrumented wall temperatures, or a
published test case with its conditions fully stated.

Author: Sean Bowman

'''

import os
import sys

import numpy as np
import pytest

from NOVA.fluidProperties import fluidProps
from NOVA.gasSideHeatTransfer import bartzHeatTransferCoefficient
from NOVA.regenThermal import (RegenThermalContext,
                          coolantFrictionAndNusselt, hotWallSectorArea, regenHeatTransferModel,
                          solveStationWallTemperature, validateRegenHeatTransferInputs,
                          wallConductionResistance)

class TestBartzViscosityConstant:

    '''The stagnation viscosity constant is a unit conversion of a published fit.'''

    def testConstantIsTheSiFormOfTheSp125Fit(self):

        # SP-125: mu = 46.6e-10 M^0.5 T^0.6, lbm/(in s), T in Rankine.
        lbmPerInchSecondToPascalSecond = 0.45359237 / 0.0254
        rankineToKelvinOnTheExponent   = 1.8 ** 0.6

        converted = 46.6e-10 * lbmPerInchSecondToPascalSecond * rankineToKelvinOnTheExponent

        assert converted == pytest.approx(1.184e-7, rel = 1e-4)

    def testTheModuleUsesThatConstant(self):

        # Drive the correlation with everything else at unity so the viscosity term is isolated:
        # h scales as mu^0.2, and mu itself as M^0.5 T0^0.6.
        base = dict(nearWallTemperature = 1000.0, nearWallMachNumber = 0.0,
                    exhaustGamma = 1.2, exhaustGasConstant = 400.0,
                    exhaustMolecularWeight = 20.0, hotWallTemperature = 800.0,
                    chamberPressure = 5e6, characteristicVelocity = 1700.0,
                    throatDiameter = 0.1, throatRadiusOfCurvature = 0.1,
                    throatArea = 0.00785, localArea = 0.00785)

        doubledWeight = dict(base, exhaustMolecularWeight = 40.0)

        ratio = bartzHeatTransferCoefficient(**doubledWeight) / bartzHeatTransferCoefficient(**base)

        # mu goes as M^0.5 and h as mu^0.2, so doubling M multiplies h by 2^0.1.
        assert ratio == pytest.approx(2.0 ** 0.1, rel = 1e-12)

class TestBartzDimensions:

    '''The correlation reduces to the units of a heat transfer coefficient, exactly.'''

    def testTheExponentsBalanceToWattsPerSquareMeterKelvin(self):

        # Bartz as implemented, factor by factor, in base SI dimensions:
        #
        #   0.026 / D^0.2            m^-0.2
        #   mu_0^0.2                 (kg m^-1 s^-1)^0.2
        #   c_p0                     m^2 s^-2 K^-1
        #   Pr_0^-0.6                dimensionless
        #   (P_c / c*)^0.8           (kg m^-1 s^-2 / m s^-1)^0.8
        #   (D_t / R_c)^0.1          dimensionless
        #   (A_t / A)^0.9            dimensionless
        #   sigma                    dimensionless
        #
        # A heat transfer coefficient is W/(m^2 K), which in base units is kg s^-3 K^-1.
        kilogram = 0.2 * 1 + 0.8 * 1
        meter    = -0.2 + 0.2 * (-1) + 2 + 0.8 * (-1 - 1)
        second   = 0.2 * (-1) + (-2) + 0.8 * (-2 + 1)
        kelvin   = -1

        assert (kilogram, meter, second, kelvin) == (1.0, 0.0, -3.0, -1.0)

    def testTheImplementationTransformsLikeThoseDimensions(self):

        # Rescale every dimensional input as though the unit of length had changed by a factor L,
        # and check the coefficient moves by exactly the factor those exponents demand. This
        # catches a wrong exponent that the one-at-a-time scaling tests would each pass, because
        # it constrains their sum rather than each in isolation.
        #
        # One factor cannot be rescaled from outside: the stagnation viscosity comes from the
        # fit 1.184e-7 M^0.5 T^0.6, whose constant carries units, so it stays at its SI value
        # whatever the caller does. Holding it fixed removes its contribution of 0.2 x (-1) to the
        # meter exponent, so the coefficient scales as L^0.2 rather than staying put. That the
        # residual is exactly L^0.2 and nothing else is what confirms every other exponent.
        #
        # It also says something about the correlation as implemented: the embedded fit ties it
        # to SI, and it would give a wrong answer in any other unit system.
        lengthFactor = 3.0

        base = dict(nearWallTemperature = 2000.0, nearWallMachNumber = 1.0,
                    exhaustGamma = 1.2, exhaustGasConstant = 400.0,
                    exhaustMolecularWeight = 22.0, hotWallTemperature = 800.0,
                    chamberPressure = 6.9e6, characteristicVelocity = 1750.0,
                    throatDiameter = 0.1, throatRadiusOfCurvature = 0.15,
                    throatArea = 0.00785, localArea = 0.0157)

        # Lengths by L, areas by L^2, velocity by L, pressure by L^-1, specific heat by L^2.
        scaled = dict(base,
                      exhaustGasConstant      = base['exhaustGasConstant']      * lengthFactor**2,
                      characteristicVelocity  = base['characteristicVelocity']  * lengthFactor,
                      chamberPressure         = base['chamberPressure']         / lengthFactor,
                      throatDiameter          = base['throatDiameter']          * lengthFactor,
                      throatRadiusOfCurvature = base['throatRadiusOfCurvature'] * lengthFactor,
                      throatArea              = base['throatArea']              * lengthFactor**2,
                      localArea               = base['localArea']               * lengthFactor**2)

        ratio = bartzHeatTransferCoefficient(**scaled) / bartzHeatTransferCoefficient(**base)

        assert ratio == pytest.approx(lengthFactor ** 0.2, rel = 1e-14)

    def testHoldingTheSpecificHeatFixedTooGivesTheDeficitItShould(self):

        # Freezing the specific heat as well removes a further +2 from the meter exponent, so the
        # deficit becomes 0.2 + 2 = 1.8 and the coefficient scales as L^-1.8. Two independent
        # deficits landing exactly where the exponents predict leaves no room for a compensating
        # pair of errors.
        lengthFactor = 3.0

        base = dict(nearWallTemperature = 2000.0, nearWallMachNumber = 1.0,
                    exhaustGamma = 1.2, exhaustGasConstant = 400.0,
                    exhaustMolecularWeight = 22.0, hotWallTemperature = 800.0,
                    chamberPressure = 6.9e6, characteristicVelocity = 1750.0,
                    throatDiameter = 0.1, throatRadiusOfCurvature = 0.15,
                    throatArea = 0.00785, localArea = 0.0157)

        scaled = dict(base,
                      characteristicVelocity  = base['characteristicVelocity']  * lengthFactor,
                      chamberPressure         = base['chamberPressure']         / lengthFactor,
                      throatDiameter          = base['throatDiameter']          * lengthFactor,
                      throatRadiusOfCurvature = base['throatRadiusOfCurvature'] * lengthFactor,
                      throatArea              = base['throatArea']              * lengthFactor**2,
                      localArea               = base['localArea']               * lengthFactor**2)

        ratio = bartzHeatTransferCoefficient(**scaled) / bartzHeatTransferCoefficient(**base)

        assert ratio == pytest.approx(lengthFactor ** -1.8, rel = 1e-14)

class TestBartzMagnitude:

    '''A sanity check on size, which is not a validation.'''

    def testAThroatCoefficientLandsInThePublishedRange(self):

        # Published gas-side throat coefficients for large liquid engines sit in the range of
        # roughly 5 to 50 kW/(m^2 K). Landing outside that would mean something is wrong; landing
        # inside it means nothing is obviously wrong, which is all a range can establish.
        coefficient = bartzHeatTransferCoefficient(
            nearWallTemperature = 3200.0, nearWallMachNumber = 1.0,
            exhaustGamma = 1.20, exhaustGasConstant = 8314.462618 / 22.0,
            exhaustMolecularWeight = 22.0, hotWallTemperature = 800.0,
            chamberPressure = 6.9e6, characteristicVelocity = 1750.0,
            throatDiameter = 0.1, throatRadiusOfCurvature = 0.15,
            throatArea = np.pi * 0.05**2, localArea = np.pi * 0.05**2)

        assert 5.0e3 < coefficient < 5.0e4, f'{coefficient:.0f} W/m^2 K is outside the range'

class TestBartzAlgebra:

    '''Each factor enters with the exponent the correlation states.'''

    def baseCase(self):

        return dict(nearWallTemperature = 2000.0, nearWallMachNumber = 0.5,
                    exhaustGamma = 1.2, exhaustGasConstant = 400.0,
                    exhaustMolecularWeight = 22.0, hotWallTemperature = 800.0,
                    chamberPressure = 6.9e6, characteristicVelocity = 1750.0,
                    throatDiameter = 0.1, throatRadiusOfCurvature = 0.15,
                    throatArea = 0.00785, localArea = 0.00785)

    @pytest.mark.parametrize('parameter, factor, exponent', [
        ('chamberPressure',         2.0,  0.8),   # (P_c / c*)^0.8
        ('characteristicVelocity',  2.0, -0.8),
        ('localArea',               2.0, -0.9),   # (A_t / A)^0.9
        ('throatArea',              2.0,  0.9),
        ('throatRadiusOfCurvature', 2.0, -0.1),   # (D_t / R_c)^0.1
    ])
    def testScalingExponents(self, parameter, factor, exponent):

        base = self.baseCase()
        scaled = dict(base, **{parameter: base[parameter] * factor})

        ratio = bartzHeatTransferCoefficient(**scaled) / bartzHeatTransferCoefficient(**base)

        assert ratio == pytest.approx(factor ** exponent, rel = 1e-12)

    def testThroatDiameterCarriesTheNetExponent(self):

        # D_t enters twice, as D_t^-0.2 and as (D_t / R_c)^0.1, so the net is D_t^-0.1.
        base = self.baseCase()
        scaled = dict(base, throatDiameter = base['throatDiameter'] * 2.0)

        ratio = bartzHeatTransferCoefficient(**scaled) / bartzHeatTransferCoefficient(**base)

        assert ratio == pytest.approx(2.0 ** -0.1, rel = 1e-12)

class TestBartzBehavior:

    '''The coefficient behaves the way a boundary layer does.'''

    def testItFallsMonotonicallyDownTheNozzle(self):

        base = dict(nearWallTemperature = 2000.0, nearWallMachNumber = 2.0,
                    exhaustGamma = 1.2, exhaustGasConstant = 400.0,
                    exhaustMolecularWeight = 22.0, hotWallTemperature = 800.0,
                    chamberPressure = 6.9e6, characteristicVelocity = 1750.0,
                    throatDiameter = 0.1, throatRadiusOfCurvature = 0.15,
                    throatArea = 0.00785)

        areaRatios = np.linspace(1.0, 40.0, 40)
        coefficients = np.array([bartzHeatTransferCoefficient(localArea = 0.00785 * ratio, **base)
                                 for ratio in areaRatios])

        assert np.all(np.diff(coefficients) < 0)
        # (A_t/A)^0.9 over a factor of 40 in area.
        assert coefficients[-1] / coefficients[0] == pytest.approx(40.0 ** -0.9, rel = 1e-12)

    def testAColderWallDrawsMoreHeat(self):

        base = dict(nearWallTemperature = 2000.0, nearWallMachNumber = 1.0,
                    exhaustGamma = 1.2, exhaustGasConstant = 400.0,
                    exhaustMolecularWeight = 22.0, chamberPressure = 6.9e6,
                    characteristicVelocity = 1750.0, throatDiameter = 0.1,
                    throatRadiusOfCurvature = 0.15, throatArea = 0.00785, localArea = 0.00785)

        cold = bartzHeatTransferCoefficient(hotWallTemperature = 400.0,  **base)
        warm = bartzHeatTransferCoefficient(hotWallTemperature = 1200.0, **base)

        # sigma carries a negative exponent on the wall temperature ratio.
        assert cold > warm

    def testTheStagnantAirSentinel(self):

        # A near-wall temperature of exactly 300 K marks a station that sees no exhaust.
        base = dict(nearWallMachNumber = 1.0, exhaustGamma = 1.2, exhaustGasConstant = 400.0,
                    exhaustMolecularWeight = 22.0, hotWallTemperature = 800.0,
                    chamberPressure = 6.9e6, characteristicVelocity = 1750.0,
                    throatDiameter = 0.1, throatRadiusOfCurvature = 0.15,
                    throatArea = 0.00785, localArea = 0.00785)

        assert bartzHeatTransferCoefficient(nearWallTemperature = 300.0, **base) == 5

        # It is an equality test against a float, so a hair either side runs the correlation.
        # This is recorded rather than relied upon.
        assert bartzHeatTransferCoefficient(nearWallTemperature = 300.0001, **base) != 5

class TestContext:

    '''The context is the whole of the model coupling to a Nozzle.'''

    def testDefaultsAreInert(self):

        context = RegenThermalContext()

        assert context.material     == 'GRCop-42'
        assert context.plotsEnabled == 'off'
        assert context.export       == 'off'

    def testItCarriesNothingThatChangesANumber(self):

        # Every field is an output or material setting. If a field is added that feeds the
        # arithmetic, this list has to change, which is the point of the test.
        fields = set(RegenThermalContext.__dataclass_fields__)

        assert fields == {'material', 'dataFolder', 'plotsEnabled', 'export'}

class TestInputValidation:

    '''The validator rejects what it says it rejects.'''

    def validInputs(self):

        stations = 10
        return {
            'numCrossSections'         : stations,
            'nChannel'                 : 60,
            'xHotWall3D'               : np.linspace(0.0, 0.3, stations),
            'rHotWall3D'               : np.linspace(0.05, 0.09, stations),
            'hotWallThickness'         : 1.0e-3,
            'throatRadiusOfCurvature'  : 0.075,
            'throatDiameter'           : 0.1,
            'throatArea'               : np.pi * 0.05 ** 2,
            'differentialPathLength'   : np.full(stations, 0.03),
            'hotWallSegmentLength'     : np.full(stations, 0.03),
            'turnAngle'                : np.zeros(stations),
            'radiusOfCurvature'        : np.full(stations, 1.0),
            'coolant'                  : 'Hydrogen',
            'mdot'                     : 3.4 / 60,
            'chamberPressure'          : 6.9e6,
            'coolantInitialTemperature': 30.0,
            'coolantInitialPressure'   : 1.2e7,
            'theoreticalCharVel'       : 1750.0,
            'gamma'                    : np.full(stations, 1.2),
            'molecularWeight'          : np.full(stations, 22.0),
            'gasConstant'              : np.full(stations, 378.0),
            'nearWallTemperature'      : np.full(stations, 2000.0),
            'nearWallMachNumber'       : np.linspace(0.2, 3.0, stations),
            'channelType'              : 'circle',
            'flowArea'                 : np.full(stations, 1.0e-5),
            'heatedArea'               : np.full(stations, 5.0e-5),
            'hydraulicDiameter'        : np.full(stations, np.sqrt(4 * 1.0e-5 / np.pi)),
        }

    def testAValidSetPasses(self):

        validateRegenHeatTransferInputs(self.validInputs())

    @pytest.mark.parametrize('missing', ['numCrossSections', 'nChannel', 'coolant', 'mdot',
                                         'chamberPressure', 'throatDiameter', 'throatArea'])
    def testAMissingKeyIsRejected(self, missing):

        inputs = self.validInputs()
        del inputs[missing]

        with pytest.raises(Exception):
            validateRegenHeatTransferInputs(inputs)

class TestStationSolveIdentities:

    '''

    Radiation and film cooling live inside the station solve unconditionally, and both have to be
    exactly absent when they are not asked for.

    This is the property the whole extension rests on. A jacket run that names no emissivity and
    no film has to reproduce, to the bit, one from before either existed. That is asserted with
    `==` rather than with `approx`, because a tolerance here would hide exactly the drift it is
    meant to catch. The regression harness makes the same check across a whole contour; this
    makes it on one station, where a failure says which term did it.

    '''

    def station(self, **overrides):

        '''One station of a plausible throat, with whatever the caller wants changed.'''

        arguments = dict(
            drivingTemperature         = 3400.0,
            gasStaticTemperature       = 3400.0,
            gasMachNumber              = 1.0,
            gasGamma                   = 1.2,
            gasConstant                = 378.0,
            gasMolecularWeight         = 22.0,
            coolantTemperature         = 120.0,
            coolantThermalConductivity = 0.12,
            coolantNusseltNumber       = 350.0,
            coolantSpecificHeat        = 14000.0,
            coolantMassFlow            = 0.05,
            hydraulicDiameter          = 0.0022,
            coolantWettedArea          = 6.0e-5,
            hotWallArea                = 5.0e-5,
            hotWallThickness           = 0.001,
            wallRadius                 = 0.05,
            pathLength                 = 0.006,
            conductivityInterpolator   = lambda temperature: 320.0,
            chamberPressure            = 5.0e6,
            characteristicVelocity     = 1800.0,
            throatDiameter             = 0.1,
            throatRadiusOfCurvature    = 0.075,
            throatArea                 = np.pi * 0.05**2,
            localArea                  = np.pi * 0.05**2)
        arguments.update(overrides)

        return solveStationWallTemperature(**arguments)

    def testAbsentAndExplicitlyZeroAgreeToTheBit(self):

        absent = self.station()
        zeroed = self.station(filmMassFlux = 0.0, wallEmissivity = 0.0, gasEmissivity = 0.0)

        for field in absent.__dataclass_fields__:
            assert getattr(absent, field) == getattr(zeroed, field), field

    def testAnEmissivityWithoutAGasEmissivityStillDoesNothing(self):

        # Radiation needs both. A wall emissivity on its own describes a surface with nothing to
        # exchange with, and the term has to stay exactly zero rather than nearly zero.
        absent = self.station()
        walled = self.station(wallEmissivity = 0.85, gasEmissivity = 0.0)

        assert walled.radiationCoefficient == 0.0
        assert walled.heatTransfer == absent.heatTransfer

    def testTheTermsAreNotVacuous(self):

        # The tests above are only worth having if the terms do something when asked. Radiation
        # adds a second path into the wall, so the flux rises; blowing removes convective
        # coefficient, so it falls.
        absent = self.station()
        radiating = self.station(wallEmissivity = 0.85, gasEmissivity = 0.25)
        blown = self.station(filmMassFlux = 0.4)

        assert radiating.radiationCoefficient > 0.0
        assert radiating.heatTransfer > absent.heatTransfer
        assert blown.blowingReduction < 1.0
        assert blown.heatTransfer < absent.heatTransfer

    def testTheBlowingReductionIsExactlyOneWithoutAFilm(self):

        assert self.station().blowingReduction == 1.0

    def testRadiationIsReportedAsItsOwnShareOfTheFlux(self):

        radiating = self.station(wallEmissivity = 0.85, gasEmissivity = 0.25)

        # The reported radiative flow is the coefficient times its own area and potential, and it
        # is a fraction of the total rather than all of it.
        expected = radiating.radiationCoefficient * 5.0e-5 * (3400.0 - radiating.hotWallTemperature)

        assert radiating.radiativeHeatTransfer == pytest.approx(expected, rel = 1.0e-12)
        assert 0.0 < radiating.radiativeHeatTransfer < radiating.heatTransfer

    def testTheWallStillSitsBetweenTheCoolantAndTheGas(self):

        for solution in (self.station(),
                         self.station(wallEmissivity = 0.85, gasEmissivity = 0.25),
                         self.station(filmMassFlux = 0.4)):
            assert 120.0 < solution.coldWallTemperature < solution.hotWallTemperature < 3400.0

    def testItConverges(self):

        solution = self.station(wallEmissivity = 0.85, gasEmissivity = 0.25)

        assert solution.converged
        assert solution.residual < 0.01

class TestWallConduction:

    '''

    The wall behind one channel is a sector of a cylindrical shell.

    A channel owns 2 pi / N of the circumference, so its share of the wall is that sector of the
    shell between r and r + t over the station. Its conduction resistance is

        R_k = ln(1 + t/r) / (k (2 pi / N) dL) = r ln(1 + t/r) / (k A_hw)

    with A_hw = (2 pi r / N) dL the sector's gas-side area. N sectors in parallel are the whole
    shell, ln(1 + t/r) / (2 pi k dL), and a wall thin against its radius conducts as a slab,
    t / (k A_hw). Each is checked in closed form, and the station solve is checked to carry the
    resistance it reports: the drop across the wall is the heat flow times that resistance.

    '''

    radius, thickness, conductivity, length, count = 0.05, 0.001, 320.0, 0.006, 60

    def sectorArea(self):

        return 2 * np.pi * self.radius / self.count * self.length

    def testTheSectorResistanceIsTheClosedForm(self):

        expected = self.count * np.log(1 + self.thickness / self.radius) \
                   / (2 * np.pi * self.length * self.conductivity)
        computed = wallConductionResistance(self.thickness, self.radius, self.conductivity,
                                            self.sectorArea())

        assert computed == pytest.approx(expected, rel = 1e-14)

    def testTheSectorsInParallelAreTheWholeShell(self):

        sector = wallConductionResistance(self.thickness, self.radius, self.conductivity,
                                          self.sectorArea())
        shell  = np.log(1 + self.thickness / self.radius) \
                 / (2 * np.pi * self.length * self.conductivity)

        assert sector / self.count == pytest.approx(shell, rel = 1e-14)

    @pytest.mark.parametrize('ratio', [1e-2, 1e-3, 1e-4])
    def testAThinWallConductsAsASlab(self, ratio):

        # ln(1 + x) / x = 1 - x/2 + O(x^2), so the shell falls short of the slab by x/2.
        thickness = ratio * self.radius
        slab      = thickness / (self.conductivity * self.sectorArea())
        shell     = wallConductionResistance(thickness, self.radius, self.conductivity,
                                             self.sectorArea())

        assert 1 - shell / slab == pytest.approx(ratio / 2, rel = 0.01)

    def testTheStationWallDropIsTheHeatFlowTimesTheResistance(self):

        for solution in (TestStationSolveIdentities().station(),
                         TestStationSolveIdentities().station(wallEmissivity = 0.85,
                                                              gasEmissivity = 0.25)):
            drop = solution.hotWallTemperature - solution.coldWallTemperature
            assert drop == pytest.approx(solution.heatTransfer * solution.conductiveResistance,
                                         rel = 1e-9)

    def testTheStationSolveUsesTheSectorResistance(self):

        solution = TestStationSolveIdentities().station()
        expected = wallConductionResistance(0.001, 0.05, 320.0, 5.0e-5)

        assert solution.conductiveResistance == expected

class TestHotWallArea:

    '''

    The gas side of one channel is its share of the wall, not of the channel.

    A channel owns 2 pi r / N of the circumference and the wall's own meridional length ds_m of
    the station, so its gas-side area is (2 pi r / N) ds_m and the N channels tile the wall
    exactly. A wrapped channel's path is longer than ds_m by 1/cos of its wrap angle, 2.9 times
    at 70 degrees, but the exhaust sees the wall rather than the path, so lengthening the path
    must leave the gas side alone.

    '''

    def testTheSectorsTileTheWall(self):

        radius, segment = 0.05, 0.004
        for count in (1, 7, 60, 240):
            assert count * hotWallSectorArea(radius, count, segment) == \
                   pytest.approx(2 * np.pi * radius * segment, rel = 1e-14)

    def station(self, pathLength):

        '''One throat station through the whole model, with the channel path set independently.'''

        inputs = {key: (value[:1] if isinstance(value, np.ndarray) else value)
                  for key, value in TestInputValidation().validInputs().items()}
        inputs.update({
            'numCrossSections'      : 1,
            'rHotWall3D'            : np.array([0.05]),
            'nearWallTemperature'   : np.array([3000.0]),
            'nearWallMachNumber'    : np.array([1.0]),
            'hotWallSegmentLength'  : np.array([0.004]),
            'differentialPathLength': np.array([pathLength]),
            'flowArea'              : np.array([np.pi * 0.002**2]),
            'heatedArea'            : np.array([np.pi * 0.002 * 0.004]),
            'hydraulicDiameter'     : np.array([0.004]),
        })

        outputs, plots = regenHeatTransferModel(RegenThermalContext(), inputs)

        return outputs, plots

    def testLengtheningThePathLeavesTheGasSideAlone(self):

        # A 70 degree wrap stretches the path by 1/cos(70 deg). The coolant-side area is held
        # fixed here, so only the friction length changes, and the wall must not notice.
        straight, straightPlots = self.station(0.004)
        wrapped,  wrappedPlots  = self.station(0.004 / np.cos(np.deg2rad(70.0)))

        assert wrapped['hotWallTemperature'][0] == straight['hotWallTemperature'][0]
        assert wrappedPlots['heatTransfer'][0] == straightPlots['heatTransfer'][0]
        assert wrapped['coolantPressure'][0] < straight['coolantPressure'][0]

class TestCoolantEnergyBalance:

    '''

    The coolant carries the heat it takes on as enthalpy, station by station.

    A rise taken as Q / (mdot cp) does not conserve energy where cp varies across the station,
    which for hydrogen near its pseudo-critical line is a factor of several over a few kelvin.
    The march adds the heat to the enthalpy and reads back the temperature that carries it, so
    the enthalpy the coolant gains is the heat the wall gave up, to the backend's own inversion.

    '''

    def inputs(self):

        return TestInputValidation().validInputs()

    def testEachStationGainsTheEnthalpyTheWallGaveUp(self):

        inputs = self.inputs()
        outputs, plots = regenHeatTransferModel(RegenThermalContext(), inputs, returnDict = True)

        temperature, pressure = plots['temperature'], plots['pressure']
        enthalpy = np.array([float(fluidProps(inputs['coolant'], 'TP', 'H', t, p))
                             for t, p in zip(temperature, pressure)])
        heat = plots['heatTransfer']

        # The march runs from the coolant inlet at the last index toward the chamber at the first.
        # The bound is the property backend's own inversion, which returns the temperature
        # carrying a given enthalpy to about 1e-9 relative.
        for i in range(len(heat) - 1, 0, -1):
            assert enthalpy[i-1] - enthalpy[i] == pytest.approx(heat[i]/inputs['mdot'], rel = 1e-8)

    def testTheJacketConservesWhatItPutIn(self):

        inputs = self.inputs()
        outputs, plots = regenHeatTransferModel(RegenThermalContext(), inputs, returnDict = True)

        temperature, pressure = plots['temperature'], plots['pressure']
        inletEnthalpy = float(fluidProps(inputs['coolant'], 'TP', 'H', temperature[-1], pressure[-1]))
        exitEnthalpy  = float(fluidProps(inputs['coolant'], 'TP', 'H', temperature[0], pressure[0]))

        # Every station's heat except the one at the chamber end, which lands on no station below it
        heatIntoTheCoolant = float(np.sum(plots['heatTransfer'][1:]))

        assert exitEnthalpy - inletEnthalpy == pytest.approx(heatIntoTheCoolant/inputs['mdot'], rel = 1e-9)

class TestModelSafeguards:

    '''

    The adiabatic comparison balances its own heat, and a bad state stops the march where it
    appears rather than stations later.

    Two ways a station goes bad. A NaN in the coolant state means an upstream quantity is already
    wrong, and the scan catches it before it spreads. A station that spends more pressure than
    arrives at it leaves a pressure at or below zero, which no equation of state answers for: the
    property call then fails somewhere that says nothing about the channel that was too small.

    '''

    def inputs(self):

        inputs = {key: (value[:1] if isinstance(value, np.ndarray) else value)
                  for key, value in TestInputValidation().validInputs().items()}
        inputs.update({
            'numCrossSections'      : 1,
            'rHotWall3D'            : np.array([0.05]),
            'nearWallTemperature'   : np.array([3000.0]),
            'nearWallMachNumber'    : np.array([1.0]),
            'hotWallSegmentLength'  : np.array([0.004]),
            'differentialPathLength': np.array([0.004]),
            'flowArea'              : np.array([np.pi * 0.002**2]),
            'heatedArea'            : np.array([np.pi * 0.002 * 0.004]),
            'hydraulicDiameter'     : np.array([0.004]),
        })

        return inputs

    def testTheAdiabaticWallBalancesOnTheHeatedArea(self):

        inputs = self.inputs()
        coldWall = 300.0
        outputs, plots = regenHeatTransferModel(RegenThermalContext(), inputs,
                                                constantColdWallTemperature = coldWall)

        coefficient = plots['adiabaticConvectiveHeatTransferCoef'][0]
        heat = coefficient * inputs['heatedArea'][0] * (coldWall - inputs['coolantInitialTemperature'])

        # The coolant takes the heat on as enthalpy, so the temperature it reaches is the one
        # that carries the raised enthalpy at the pressure it reaches
        inletEnthalpy = fluidProps(inputs['coolant'], 'TP', 'H', inputs['coolantInitialTemperature'],
                                   inputs['coolantInitialPressure'])
        expected = fluidProps(inputs['coolant'], 'PH', 'T', plots['pressure'][0],
                              inletEnthalpy + heat/inputs['mdot'])

        assert outputs['coolantTemperature'][0] == pytest.approx(float(expected), rel = 1e-12)

    def testANaNInTheCoolantStateStopsTheMarch(self, monkeypatch):

        import NOVA.regenThermal as regenThermal
        from NOVA.errors import NumericalInstabilityError

        realProperties = regenThermal.fluidProps

        def poisoned(*arguments, **keywords):
            values = list(realProperties(*arguments, **keywords))
            values[0] = float('nan')
            return tuple(values)

        monkeypatch.setattr(regenThermal, 'fluidProps', poisoned)

        with pytest.raises(NumericalInstabilityError, match = 'NaN'):
            regenHeatTransferModel(RegenThermalContext(), self.inputs())

    def testAStationThatSpendsMorePressureThanItHasStopsTheMarch(self):

        from NOVA.errors import PressureDropError

        # A channel small enough that the station's own drop exceeds the pressure arriving at it.
        # Carried on, the station computes its coolant temperature at a negative pressure, which
        # no equation of state answers for, and the failure surfaces far from its cause.
        inputs = self.inputs()
        inputs.update({
            'coolantInitialPressure': 2.0e5,
            'flowArea'              : np.array([np.pi * 0.00012**2]),
            'hydraulicDiameter'     : np.array([0.00024]),
            'differentialPathLength': np.array([0.5]),
        })

        with pytest.raises(PressureDropError, match = 'runs out of pressure'):
            regenHeatTransferModel(RegenThermalContext(), inputs)

    def testTheReportNamesWhereTheDropWentAndWhatToChange(self):

        from NOVA.errors import PressureDropError

        inputs = self.inputs()
        inputs.update({
            'coolantInitialPressure': 2.0e5,
            'flowArea'              : np.array([np.pi * 0.00012**2]),
            'hydraulicDiameter'     : np.array([0.00024]),
            'differentialPathLength': np.array([0.5]),
        })

        with pytest.raises(PressureDropError) as raised:
            regenHeatTransferModel(RegenThermalContext(), inputs)

        message = str(raised.value)

        assert 'friction' in message
        assert 'turning' in message
        assert 'maxChannelDepth' in message
        assert raised.value.context['exitPressure'] <= 0.0
        assert raised.value.context['pressureDrop'] > 2.0e5

    def testAStationWithPressureToSpareIsLeftAlone(self):

        # The same station at the pressure the fixture normally runs, which it can afford
        outputs, _ = regenHeatTransferModel(RegenThermalContext(), self.inputs())

        assert outputs['coolantPressure'][0] > 0.0

class TestRectangularDepth:

    '''

    A deeper rectangle runs its wall hotter, at every station, which is what the sizing solve's
    secant search needs to be a root find.

    At a fixed coolant flow a deeper channel carries it slower, so the coolant coefficient
    falls; the rib grows with the depth and adds area, but less effectively the taller it is.
    The first wins everywhere checked here, from a throat-like station to a barrel-like one.

    '''

    def wallTemperature(self, depth, width, machNumber, radius):

        from NOVA.channelSections import sectionProperties

        section = sectionProperties('rectangular', np.array([depth / 2]), width = np.array([width]),
                                    cornerRadius = 0.2e-3, ribThickness = 1.0e-3)
        inputs = TestModelSafeguards().inputs()
        inputs.update({
            'channelType'       : 'rectangular',
            'mdot'              : 3.4 / 160,
            'nChannel'          : 160,
            'rHotWall3D'        : np.array([radius]),
            'nearWallMachNumber': np.array([machNumber]),
            'flowArea'          : section.flowArea,
            'heatedArea'        : section.heatedPerimeter * 0.004,
            'hydraulicDiameter' : section.hydraulicDiameter,
            'finHeight'         : section.finHeight,
            'finThickness'      : section.finThickness,
        })

        outputs, _ = regenHeatTransferModel(RegenThermalContext(), inputs)

        return outputs['hotWallTemperature'][0]

    @pytest.mark.parametrize('width, machNumber, radius', [(1.0e-3, 1.0, 0.0503), (2.5e-3, 0.2, 0.09)])
    def testTheWallRunsHotterAsTheChannelDeepens(self, width, machNumber, radius):

        depths = [1.5e-3, 2.5e-3, 4.0e-3, 6.0e-3, 8.0e-3]
        temperatures = [self.wallTemperature(depth, width, machNumber, radius) for depth in depths]

        assert all(later > earlier for earlier, later in zip(temperatures, temperatures[1:])), temperatures

class TestCoolantCorrelation:

    '''

    The friction factor is Swamee and Jain's explicit form of Colebrook. It is commonly quoted as
    within one percent of Colebrook for relative roughness 1e-6 to 1e-2 and Reynolds numbers 5e3
    to 1e8. Measured against Colebrook solved by iteration it is within one percent for Reynolds
    numbers 1e4 to 1e7 at relative roughness up to 1e-3, and within 2.8 percent over the whole
    quoted range, the worst at the rough, low-Reynolds corner (1e-2, 5e3).

    '''

    @staticmethod
    def colebrook(reynolds, relativeRoughness):

        friction = 0.02
        for _ in range(100):
            friction = (-2 * np.log10(relativeRoughness / 3.7 + 2.51 / (reynolds * np.sqrt(friction))))**-2
        return friction

    @pytest.mark.parametrize('reynolds', [5e3, 1e4, 1e5, 1e6, 1e7, 1e8])
    @pytest.mark.parametrize('relativeRoughness', [1e-6, 1e-5, 1e-4, 1e-3, 1e-2])
    def testTheFrictionFactorIsColebrook(self, reynolds, relativeRoughness):

        diameter = 2.0e-3
        friction, _ = coolantFrictionAndNusselt(reynolds, 0.7, diameter,
                                                surfaceRoughness = relativeRoughness * diameter)
        tolerance = 0.01 if (1e4 <= reynolds <= 1e7 and relativeRoughness <= 1e-3) else 0.03

        assert friction == pytest.approx(self.colebrook(reynolds, relativeRoughness), rel = tolerance)

    def testTheShippedRoughnessIsAPrintedChannel(self):

        smooth, _   = coolantFrictionAndNusselt(1e5, 0.7, 2.0e-3, surfaceRoughness = 0.0)
        printed, _  = coolantFrictionAndNusselt(1e5, 0.7, 2.0e-3)

        assert printed > smooth

class TestPrescribedGasCoefficient:

    '''A prescribed gas-side coefficient replaces Bartz and is held fixed through the solve.'''

    def testTheGasSideFluxIsTheCoefficientTimesItsDrivingDifference(self):

        solution = TestStationSolveIdentities().station(prescribedGasCoefficient = 40.0e3)
        flux = solution.heatTransfer / 5.0e-5

        assert solution.exhaustConvectiveCoefficient == 40.0e3
        assert flux == pytest.approx(40.0e3 * (3400.0 - solution.hotWallTemperature), rel = 1e-12)
        assert solution.converged

#--------------------------------------------------------------------------------------------------------------------------#
# -- Taylor's wall-to-bulk property correction -- #
#--------------------------------------------------------------------------------------------------------------------------#

class TestTaylorPropertyCorrection:

    '''
    NASA TN D-4332, the correction a smooth-tube correlation needs when the wall is much hotter
    than the fluid. The direction is the point: it lowers the coolant-side coefficient, so a
    jacket solved without it is not conservative.
    '''

    def testNoGradientIsNoCorrection(self):
        '''A surface at the bulk temperature has no property variation to correct for.'''
        from NOVA.regenThermal import taylorPropertyFactor
        assert taylorPropertyFactor(300.0, 300.0, 100.0) == pytest.approx(1.0, rel = 1e-12)

    def testAHotterSurfaceLowersTheCoefficient(self):
        '''The exponent is negative, so the factor is below one wherever the wall is hotter.'''
        from NOVA.regenThermal import taylorPropertyFactor
        assert taylorPropertyFactor(600.0, 150.0, 100.0) < 1.0

    def testTheFactorFallsAsTheWallGetsHotter(self):
        '''Monotone in the temperature ratio, which is what makes it a correction and not a fudge.'''
        from NOVA.regenThermal import taylorPropertyFactor
        ratios = [taylorPropertyFactor(t, 150.0, 100.0) for t in (200.0, 400.0, 800.0)]
        assert ratios[0] > ratios[1] > ratios[2]

    def testFarFromTheInletTheExponentReachesItsAsymptote(self):
        '''
        The entrance term is 1.59 D/x, so a long channel approaches the bare -0.57 exponent that
        other tools quote on its own. RPA's hydrogen correlation uses exactly that asymptote.
        '''
        from NOVA.regenThermal import taylorPropertyFactor
        assert taylorPropertyFactor(600.0, 150.0, 1.0e6) == pytest.approx(4.0**-0.57, rel = 1e-5)

    def testNearTheInletTheCorrectionIsWeaker(self):
        '''
        The entrance term subtracts from the exponent, so a station close to the inlet is
        corrected less than one far downstream.
        '''
        from NOVA.regenThermal import taylorPropertyFactor
        near = taylorPropertyFactor(600.0, 150.0, 3.0)
        far  = taylorPropertyFactor(600.0, 150.0, 300.0)
        assert near > far

    def testASurfaceColderThanTheBulkIsHeldAtUnity(self):
        '''
        Outside the fit, and inverting the correction there would raise the coefficient where the
        correlation has nothing to say.
        '''
        from NOVA.regenThermal import taylorPropertyFactor
        assert taylorPropertyFactor(100.0, 300.0, 100.0) == pytest.approx(1.0, rel = 1e-12)

    def testTheCorrectionIsOffByDefault(self):
        '''
        Off is both what reproduces every earlier result and what the hardware comparison
        supports. Carlile and Quentmeyer's 13 measured throat wall temperatures land 13 of 13
        inside the predicted band without this correction and 0 of 13 with it, so the default is
        a measured choice and not merely a compatibility one. tests/testRegenValidation.py owns
        that comparison; this pins the default it rests on.
        '''
        from NOVA.regenThermal import COOLANTPROPERTYCORRECTIONS
        assert COOLANTPROPERTYCORRECTIONS[0] == 'none'

    def testTheShippedConfigurationLeavesItOff(self):
        '''A trap is only a trap if something walks into it. The reference nozzle does not.'''
        import json, os
        import NOVA

        shipped = os.path.join(os.path.dirname(NOVA.__file__), 'assets', 'NOVANozzle.json')
        config = json.load(open(shipped, encoding = 'utf-8'))
        assert config['coolantPropertyCorrection'] == 'none'

    def testAnUnknownCorrectionIsRefused(self):
        '''A misspelled option must not fall through to no correction at all.'''
        import json, os
        import NOVA
        from NOVA.config import setInputs
        from NOVA.errors import InvalidInputError

        shipped = os.path.join(os.path.dirname(NOVA.__file__), 'assets', 'NOVANozzle.json')
        config = json.load(open(shipped, encoding = 'utf-8'))
        config['coolantPropertyCorrection'] = 'siederTate'

        with pytest.raises(InvalidInputError, match = 'coolantPropertyCorrection'):
            setInputs(NOVA.Nozzle(), config)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Thermal barrier coating -- #
#--------------------------------------------------------------------------------------------------------------------------#

class TestThermalBarrierCoating:

    '''
    A ceramic layer inside the metal one. It raises its own gas-side surface temperature and
    lowers the metal behind it, which is the whole point of fitting one, and it is the metal that
    a wall temperature limit applies to.
    '''

    def station(self, coatingThickness = 0.0, coatingConductivity = 1.5):
        '''One station of a copper wall, optionally behind a coating.'''
        from NOVA.regenThermal import solveStationWallTemperature

        return solveStationWallTemperature(
            drivingTemperature = 3400.0, gasStaticTemperature = 3400.0, gasMachNumber = 1.0,
            gasGamma = 1.2, gasConstant = 700.0, gasMolecularWeight = 12.0,
            coolantTemperature = 150.0, coolantThermalConductivity = 0.12,
            coolantNusseltNumber = 400.0, coolantSpecificHeat = 14000.0,
            coolantMassFlow = 0.05, hydraulicDiameter = 0.002,
            coolantWettedArea = 6.0e-5, hotWallArea = 6.0e-5,
            hotWallThickness = 1.0e-3, wallRadius = 0.05, pathLength = 1.0e-3,
            conductivityInterpolator = lambda temperature: 300.0,
            chamberPressure = 6.9e6, characteristicVelocity = 2300.0, throatDiameter = 0.1,
            throatRadiusOfCurvature = 0.1, throatArea = 0.00785, localArea = 0.00785,
            prescribedGasCoefficient = 25000.0,
            coatingThickness = coatingThickness, coatingConductivity = coatingConductivity)

    def testNoCoatingLeavesTheInterfaceAtTheHotWall(self):
        '''With no coating there is no interface, so the two temperatures are one number.'''
        solution = self.station()
        assert solution.coatingInterfaceTemperature == pytest.approx(solution.hotWallTemperature)

    def testACoatingRaisesItsOwnSurfaceAndLowersTheMetal(self):
        '''
        Both halves matter. A coating that only raised the surface would be a liability; one that
        only lowered the metal would be free. It does both, and the gap between them is the
        temperature drop across the ceramic.
        '''
        bare    = self.station()
        coated  = self.station(coatingThickness = 1.0e-4)

        assert coated.hotWallTemperature > bare.hotWallTemperature
        assert coated.coatingInterfaceTemperature < bare.hotWallTemperature
        assert coated.hotWallTemperature > coated.coatingInterfaceTemperature

    def testACoatingCutsTheHeatFlux(self):
        '''Adding resistance in series with everything else lowers the heat the wall passes.'''
        assert self.station(coatingThickness = 1.0e-4).heatTransfer \
               < self.station().heatTransfer

    def testAThickerCoatingProtectsTheMetalFurther(self):
        '''Monotone in thickness, over the range a coating is actually applied in.'''
        metal = [self.station(coatingThickness = t).coatingInterfaceTemperature
                 for t in (2.5e-5, 5.0e-5, 1.0e-4)]
        assert metal[0] > metal[1] > metal[2]

    def testALowerConductivityCoatingProtectsFurther(self):
        '''The resistance is thickness over conductivity, so the two trade against each other.'''
        assert self.station(coatingThickness = 1.0e-4, coatingConductivity = 1.0) \
                   .coatingInterfaceTemperature \
               < self.station(coatingThickness = 1.0e-4, coatingConductivity = 3.0) \
                   .coatingInterfaceTemperature

    def testAZeroConductivityCoatingIsIgnoredRatherThanInfinite(self):
        '''An unset conductivity must not divide by zero into an infinite resistance.'''
        solution = self.station(coatingThickness = 1.0e-4, coatingConductivity = 0.0)
        assert solution.converged
        assert solution.coatingInterfaceTemperature == pytest.approx(solution.hotWallTemperature)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Friction loss on the thrust coefficient -- #
#--------------------------------------------------------------------------------------------------------------------------#

class TestFrictionLoss:

    '''
    The inviscid exit plane reports a thrust the wall was never charged for. This is the debit,
    and the tests here are about the bookkeeping rather than the boundary layer itself, which
    tests/testBoundaryLayer.py owns.
    '''

    def nozzleWithWall(self, stations = 40):
        '''A bare nozzle carrying just enough for the friction stage to run.'''
        import NOVA

        nozzle = NOVA.Nozzle()
        x = np.linspace(-0.2, 0.6, stations)
        nozzle.xNozzleWall = x
        nozzle.rNozzleWall = 0.05 + 0.08*np.clip(x, 0.0, None)
        nozzle.nozzleNearWallMachNumber = np.linspace(1.05, 4.0, stations)
        nozzle.nozzleNearWallTemperature = np.linspace(3000.0, 1400.0, stations)
        nozzle.nozzleNearWallPressure = np.linspace(4.0e6, 2.0e4, stations)
        nozzle.nozzleNearWallVelocity = np.linspace(1200.0, 4200.0, stations)
        nozzle.chamberGamma = 1.2
        nozzle.chamberRGasConstant = 700.0
        nozzle.channelWallTemperature = np.full(stations, 800.0)
        nozzle.thrustCoef = 1.8
        nozzle.throatArea = np.pi*0.05**2
        nozzle.chamberPressure = 6.9e6
        return nozzle

    def testTheLossIsAFractionOfIdealThrust(self):
        '''The coefficient is the drag over the thrust the inviscid solve delivered.'''
        nozzle = self.nozzleWithWall()
        nozzle.solveFrictionLoss()

        ideal = nozzle.thrustCoef * nozzle.throatArea * nozzle.chamberPressure
        assert nozzle.frictionLossCoefficient == pytest.approx(nozzle.frictionDragForce / ideal)

    def testTheCorrectedCoefficientIsBelowTheIdealOne(self):
        '''Friction is a debit. A correction that raised the thrust coefficient would be a sign error.'''
        nozzle = self.nozzleWithWall()
        nozzle.solveFrictionLoss()

        assert 0.0 < nozzle.frictionLossCoefficient < 0.1
        assert nozzle.frictionCorrectedThrustCoef < nozzle.thrustCoef

    def testNoWallTemperatureMeansNoMarch(self):
        '''
        Without a jacket there is no solved wall temperature, and a boundary layer marched against
        an invented one would be a number with nothing behind it.
        '''
        nozzle = self.nozzleWithWall()
        nozzle.channelWallTemperature = None
        nozzle.solveFrictionLoss()

        assert nozzle.frictionDragForce is None
        assert nozzle.frictionCorrectedThrustCoef is None

    def testNoContourMeansNoMarch(self):
        '''A nozzle that has not been built yet reports nothing rather than raising.'''
        import NOVA

        nozzle = NOVA.Nozzle()
        nozzle.solveFrictionLoss()
        assert nozzle.frictionLossCoefficient is None

    def testAJacketShorterThanTheWallIsCarriedNotExtrapolated(self):
        '''
        The jacket covers the cooled section only. Its temperature is resampled onto the wall
        rather than the march being refused, and the result still runs.
        '''
        nozzle = self.nozzleWithWall()
        nozzle.channelWallTemperature = np.full(12, 750.0)
        nozzle.solveFrictionLoss()

        assert nozzle.frictionDragForce is not None
        assert nozzle.frictionDragForce > 0.0
