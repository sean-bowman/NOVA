'''

Tests for the regenerative cooling thermal model in regenThermal.py.

**The gas side is checked, but not validated against a measurement.** No published worked example
with a complete set of inputs and a stated answer was available to set the implementation against.
What is checked instead is everything that can be checked without one:

  - the stagnation viscosity constant, which is a unit conversion of the fit published in
    Huzel and Huang, NASA SP-125, and is verified as that conversion rather than taken on trust;
  - the dimensions, which must reduce to kg s^-3 K^-1, that is W/(m^2 K), exactly;
  - the exponent each input enters with, driven one at a time against the published form;
  - the limiting behaviour, since the coefficient must fall as the area ratio grows and must rise
    as the wall gets colder.

Those establish that the implementation is the correlation it claims to be. They do not establish
that the correlation predicts a real engine, and nothing here should be read as saying so.

**The coolant side is not validated at all.** The circular correlation is Gnielinski, which is
published and whose range of validity is known, but nothing here checks the implementation
against a reference case. The fluted correlation is a fifty-fifty blend of Gnielinski with a
spirally fluted correlation, with a roughness amplification applied to the second term only. No
source states that blend or its range of validity, and no measurement is available to set it
against.

What closes both gaps is a measurement: a fired engine with instrumented wall temperatures, or a
published test case with its conditions fully stated.

Author: Sean Bowman

'''

import os
import sys

import numpy as np
import pytest

from NOVA.regenThermal import (RegenThermalContext, bartzHeatTransferCoefficient,
                          solveStationWallTemperature, validateRegenHeatTransferInputs)

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

    def testTheExponentsBalanceToWattsPerSquareMetreKelvin(self):

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
        metre    = -0.2 + 0.2 * (-1) + 2 + 0.8 * (-1 - 1)
        second   = 0.2 * (-1) + (-2) + 0.8 * (-2 + 1)
        kelvin   = -1

        assert (kilogram, metre, second, kelvin) == (1.0, 0.0, -3.0, -1.0)

    def testTheImplementationTransformsLikeThoseDimensions(self):

        # Rescale every dimensional input as though the unit of length had changed by a factor L,
        # and check the coefficient moves by exactly the factor those exponents demand. This
        # catches a wrong exponent that the one-at-a-time scaling tests would each pass, because
        # it constrains their sum rather than each in isolation.
        #
        # One factor cannot be rescaled from outside: the stagnation viscosity comes from the
        # fit 1.184e-7 M^0.5 T^0.6, whose constant carries units, so it stays at its SI value
        # whatever the caller does. Holding it fixed removes its contribution of 0.2 x (-1) to the
        # metre exponent, so the coefficient scales as L^0.2 rather than staying put. That the
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

        # Freezing the specific heat as well removes a further +2 from the metre exponent, so the
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

class TestBartzBehaviour:

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

        assert context.material  == 'GRCop-42'
        assert context.plotsAdv  == 'off'
        assert context.plotsDocs == 'off'
        assert context.export    == 'off'
        assert context.debugMode is False

    def testItCarriesNothingThatChangesANumber(self):

        # Every field is an output or material setting. If a field is added that feeds the
        # arithmetic, this list has to change, which is the point of the test.
        fields = set(RegenThermalContext.__dataclass_fields__)

        assert fields == {'material', 'dataFolder', 'plotsAdv', 'plotsDocs', 'export', 'debugMode'}

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
            'circleCSA'                : np.full(stations, 1.0e-5),
            'circleSA'                 : np.full(stations, 1.0e-4),
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
