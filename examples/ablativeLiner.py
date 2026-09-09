# -- Ablative Liner Example for the NOVA Nozzle Design Tool -- #

'''

An ablative nozzle liner, solved two ways.

The first half runs the Ablation Workshop's first test case, which is the benchmark NOVA's
material response is validated against: a slab of TACOT with its surface held at 1644 K for a
minute. It needs no nozzle and no thermochemistry, and it is the fastest way to see what the
model actually computes.

The second half puts the same material on a LOX/RP-1 nozzle contour and marches every station
through a firing, which is the design question: how much throat is lost, and how hot does the
back of the liner get.

Two things about the second half are stated in the model's own documentation and are repeated
here because they decide how its numbers should be read. TACOT is a low-density entry heatshield
at 280 kg/m^3, not a tape-wrapped nozzle liner at 1450, and recession scales inversely with char
density. And the char removal rate is a transport-limited upper bound rather than a prediction,
which is why `charRemovalEfficiency` appears below with a value fitted to nothing.

Author: Sean Bowman

'''

import os

import numpy as np

from NOVA.ablative import AblationEnvironment, ablativeNozzleLiner, \
                          diffusionLimitedCharBPrime, propellantElementMassFractions, \
                          solveMaterialResponse
from NOVA.gasDynamics import machFromAreaRatio, staticTemperatureRatio

def workshopTestCase():

    '''

    Ablation Workshop test case 1: five centimetres of TACOT held at 1644 K for a minute.

    Returns:
    --------
    MaterialResponseResult

    '''

    def surfaceTemperature(time):

        '''298 K to 1644 K over the first tenth of a second, then held.'''

        return 298.0 + (1644.0 - 298.0) * min(time / 0.1, 1.0)

    environment = AblationEnvironment(
        surfaceClosure = 'temperature',
        surfaceTemperature = surfaceTemperature,
        pressure = 101325.0,
        backFaceCondition = 'adiabatic')

    return solveMaterialResponse(
        'TACOT v3.0', environment, thickness = 0.05, duration = 60.0,
        timeStep = 0.05, numberOfNodes = 101, growthRatio = 1.05,
        initialTemperature = 298.0, outputInterval = 0.25)

def nozzleLiner():

    '''

    A thirty millimetre liner on a LOX/RP-1 nozzle through an eight second firing.

    The contour is a simple converging-diverging wall rather than a NOVA-generated one, so that
    the example runs without thermochemistry. Replace the three station arrays with a real
    contour and its one-dimensional flow solution to use this on a design.

    Returns:
    --------
    AblativeLinerResult

    '''

    gamma = 1.19
    molecularWeight = 22.0
    throatRadius = 0.050

    axial = np.linspace(-0.12, 0.30, 25)
    radius = np.where(axial < 0.0,
                      throatRadius * (1.0 + 0.8 * (axial / 0.12)**2),
                      throatRadius * (1.0 + 1.4 * (np.abs(axial) / 0.30)**1.3))

    mach = np.array([machFromAreaRatio(float((wall / throatRadius)**2), gamma,
                                       'subsonic' if station < 0.0 else 'supersonic')
                     for wall, station in zip(radius, axial)])
    staticTemperature = 3550.0 * np.array(
        [staticTemperatureRatio(float(number), gamma) for number in mach])

    # Combustion conserves elements, so the exhaust composition follows from the reactants and
    # the mixture ratio without an equilibrium solve. RP-1 is taken as CH1.95.
    exhaust = propellantElementMassFractions(
        fuelElements = {'C': 0.8594, 'H': 0.1406},
        oxidiserElements = {'O': 1.0},
        mixtureRatio = 2.7)

    print('Exhaust by element, mass fraction: '
          + ', '.join('%s %.4f' % pair for pair in sorted(exhaust.items())))
    print('Transport-limited char blowing rate: %.4f' % diffusionLimitedCharBPrime(exhaust))
    print()

    return ablativeNozzleLiner(
        'TACOT v3.0', axial, radius, mach, staticTemperature,
        edgeElements = exhaust,
        chamberPressure = 5.0e6,
        chamberTemperature = 3550.0,
        characteristicVelocity = 1780.0,
        exhaustGamma = gamma,
        exhaustGasConstant = 8314.46261815324 / molecularWeight,
        exhaustMolecularWeight = molecularWeight,
        throatRadiusOfCurvature = 0.075,
        burnTime = 8.0,
        linerThickness = 0.030,
        timeStep = 0.02,
        numberOfNodes = 61,
        # Fitted to nothing. One returns the transport-limited bound; anything below it is a
        # calibration and carries only as far as the firing it was fitted to.
        charRemovalEfficiency = 0.12,
        viewFactor = 0.5)

if __name__ == '__main__':

    os.system('cls' if os.name == 'nt' else 'clear')

    print('Ablation Workshop test case 1: TACOT at 1644 K')
    print('-' * 78)
    response = workshopTestCase()
    print('  surface                %8.1f K' % response.surfaceTemperature[-1])
    print('  back face              %8.1f K' % response.backFaceTemperature[-1])
    print('  char front             %8.2f mm below the original surface'
          % (response.charDepth[-1] * 1e3))
    print('  pyrolysis front        %8.2f mm' % (response.pyrolysisDepth[-1] * 1e3))
    print('  peak gas blowing rate  %8.4f kg/m^2 s'
          % response.pyrolysisGasMassFlux.max())
    print('  energy closure error   %8.2e' % response.energyImbalance)
    print()
    print('  temperature at the workshop probe depths, at 60 s')
    for depth in (0.001, 0.002, 0.004, 0.008, 0.016, 0.050):
        print('    %5.0f mm   %8.1f K' % (depth * 1e3, response.temperatureAtDepth(depth)[-1]))

    print()
    print('Ablative liner on a LOX/RP-1 nozzle, eight second firing')
    print('-' * 78)
    liner = nozzleLiner()
    print('     x [mm]   r [mm]   h_g [W/m^2 K]   recession [mm]   char [mm]'
          '   T_wall [K]   T_back [K]')
    for index in range(0, liner.axialPosition.size, 3):
        print('   %8.1f %8.2f %15.0f %16.3f %11.2f %12.0f %12.1f' % (
            liner.axialPosition[index] * 1e3, liner.radius[index] * 1e3,
            liner.heatTransferCoefficient[index], liner.recession[index] * 1e3,
            liner.charDepth[index] * 1e3, liner.surfaceTemperature[index],
            liner.backFaceTemperature[index]))
    print()
    print('  throat recession       %8.3f mm' % (liner.throatRecession * 1e3))
    print('  throat area ratio      %8.4f' % liner.throatAreaRatio)
    print('  hottest back face      %8.1f K' % liner.backFaceTemperature.max())
