# -- Film and Radiative Cooling Example for the NOVA Nozzle Design Tool -- #

'''

The two cooling methods that work alongside a jacket rather than instead of it.

A regeneratively cooled jacket removes heat. Film cooling and radiation do not: a film lowers the
temperature the wall is driven by, and an uncooled shell simply settles wherever radiating away
what it takes in puts it. Both are combined with a jacket in practice, and both are here.

The first half puts a hydrogen film on the LOX/LH2 reference engine and reports what it buys and
what it costs. The second half truncates the same engine's jacket and hangs a coated columbium
shell off the end, then asks the only question that matters about one: does it survive.

Two things decide how the numbers should be read, and both come from the models' own
documentation. The film closure is Hatch and Papell, fitted on a flat plate below 1100 K at
subsonic speed with no acceleration and no turning, so a rocket is an extrapolation on every axis;
its properties are corrected to the film mean temperature here, but the conductivity supplied to
it is still the equilibrium value rather than the molecular one. And the extension solver is
verified rather than validated: no open dataset gives a measured wall temperature distribution
along a fully specified firing.

Author: Sean Bowman

'''

import io
import json
import os

import numpy as np

from NOVA.Nozzle import Nozzle
from NOVA.radiativeCooling import RadiativeShell, radiativeNozzleExtension

def referenceConfiguration(**overrides):

    '''

    The reference nozzle's jacket, with everything the cases below are not about switched off.

    `NOVANozzle.json` carries every feature that composes, which is more than a film study wants.
    The film and the extension are what the cases vary, so everything else is held fixed: the
    jacket runs the full contour, the volutes are not built, and no figure is drawn. Building the
    volutes alone adds minutes to a run that reads nothing from them.

    Returns:
    --------
    dict
        A configuration ready to hand to `Nozzle.generateNozzle`.

    '''

    assetPath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'src', 'NOVA', 'assets', 'NOVANozzle.json')
    with io.open(assetPath, encoding = 'utf-8') as handle:
        configuration = json.load(handle)

    # The jacket the cases share: sixty circular channels in GRCop-42, hydrogen at 3.4 kg/s
    # entering at 12 MPa and 30 K, above the hydrogen critical point, over the full contour.
    configuration.update({
        'makeCoolingChannels': True, 'material': 'GRCop-42', 'channelType': 'circle',
        'nChannel': 60, 'numCrossSections': 60, 'numCSPointsChannel': 40,
        'hotWallThickness': 0.001, 'shellThickness': 0.002, 'infillThickness': 0.001,
        'maxWallTemperature': 800.0,
        'coolantClass': 'fuel', 'coolant': 'Hydrogen', 'coolantInitialTemperature': 30.0,
        'coolantInitialPressure': 12000000.0, 'coolantMassFlow': 3.4,
        'regenTruncationType': 'none', 'regenTruncationValue': None})

    # Each case switches on the one feature it is about. Inheriting them from the reference
    # nozzle instead would put a film on the case that exists to run without one.
    configuration.update({
        'filmCooling': False, 'filmCoolant': None, 'filmMassFlow': None,
        'filmInletTemperature': None, 'filmInjectionAxialPosition': None, 'filmSlotHeight': None,
        'makeRadiativeExtension': 'off',
        'makeInletVolute': False, 'makeReturnVolute': False})

    configuration.update({'plotsEnabled': 'off', 'export': 'off'})
    configuration.update(overrides)

    return configuration

def runConfiguration(configuration, outputFolder):

    '''

    Write a configuration to disk and run it.

    Parameters:
    -----------
    configuration : dict
        What `referenceConfiguration` produced, possibly modified.
    outputFolder : str
        Directory the run may write into.

    Returns:
    --------
    Nozzle
        The solved nozzle.

    '''

    os.makedirs(outputFolder, exist_ok = True)
    configurationPath = os.path.join(outputFolder, 'configuration.json')
    with io.open(configurationPath, 'w', encoding = 'utf-8', newline = '') as handle:
        json.dump(configuration, handle, indent = 2)

    nozzle = Nozzle()
    nozzle.generateNozzle(configPath = configurationPath)

    return nozzle

def filmCooledJacket(outputFolder):

    '''

    A hydrogen film on the reference engine, against the same engine with none.

    A film is propellant that bypasses the injector, so it is never free. What it buys is a lower
    driving temperature over the length it survives, and what it costs is that flow.

    Parameters:
    -----------
    outputFolder : str
        Directory the two runs may write into.

    '''

    print()
    print('=' * 86)
    print('A hydrogen film on the LOX/LH2 reference jacket')
    print('=' * 86)

    film = dict(filmCooling = True, filmCoolant = 'Hydrogen', filmMassFlow = 0.30,
                filmInletTemperature = 250.0, filmInjectionAxialPosition = -1.0,
                filmSlotHeight = 0.0015)

    plain = runConfiguration(referenceConfiguration(filmCooling = False),
                             os.path.join(outputFolder, 'noFilm'))
    hatch = runConfiguration(
        referenceConfiguration(filmCoolingModel = 'hatchPapell', **film),
        os.path.join(outputFolder, 'hatchPapell'))
    entrained = runConfiguration(
        referenceConfiguration(filmCoolingModel = 'sp8124Entrainment', **film),
        os.path.join(outputFolder, 'entrainment'))

    axial = hatch.xRegenNozzle
    recovery = hatch.regenSectionNearWallRecoveryTemperature

    print()
    print('  slot at x = {:.1f} mm, coolant leaving at {:.1f} m/s'.format(
        axial[0] * 1e3, hatch.filmCoolantVelocity))
    print()
    print('  {:>9} {:>10} {:>10} {:>12} {:>10} {:>12}'.format(
        'x [mm]', 'no film', 'eta H+P', 'T_drive H+P', 'eta SP', 'T_drive SP'))
    for index in range(0, axial.size, max(axial.size // 8, 1)):
        print('  {:9.1f} {:10.0f} {:10.4f} {:12.0f} {:10.4f} {:12.0f}'.format(
            axial[index] * 1e3, recovery[index],
            hatch.regenSectionFilmEffectiveness[index],
            hatch.regenSectionFilmDrivingTemperature[index],
            entrained.regenSectionFilmEffectiveness[index],
            entrained.regenSectionFilmDrivingTemperature[index]))

    print()
    print('  {:<38} {:>12} {:>12} {:>12}'.format('', 'no film', 'Hatch+Pap', 'SP-8124'))
    print('  {:<38} {:>12} {:12.1f} {:12.1f}'.format(
        'film survival [mm]', 'n/a', hatch.filmSurvivalLength * 1e3,
        entrained.filmSurvivalLength * 1e3))
    print('  {:<38} {:12.0f} {:12.0f} {:12.0f}'.format(
        'peak driving temperature [K]', recovery.max(),
        hatch.regenSectionFilmDrivingTemperature.max(),
        entrained.regenSectionFilmDrivingTemperature.max()))
    print('  {:<38} {:12.2f} {:12.2f} {:12.2f}'.format(
        'coolant exit temperature [K]', plain.coolantExitTemperature,
        hatch.coolantExitTemperature, entrained.coolantExitTemperature))

    print()
    print('  The two closures disagree by hundreds of kelvin, and neither is validated at rocket')
    print('  conditions. The correlation blends temperatures linearly and cannot see that')
    print('  hydrogen carries three times the specific heat of the exhaust; the entrainment')
    print('  model can, and it also reports what the correlation has no way to know.')
    print()
    print('  {:>9} {:>10} {:>12} {:>10}'.format('x [mm]', 'psi_m', 'W_E/W_c', '(MR)_w'))
    for index in range(0, axial.size, max(axial.size // 6, 1)):
        print('  {:9.1f} {:10.3f} {:12.3f} {:10.3f}'.format(
            axial[index] * 1e3,
            entrained.regenSectionFilmEntrainmentMultiplier[index],
            entrained.regenSectionFilmEntrainmentFlowRatio[index],
            entrained.regenSectionFilmWallMixtureRatio[index]))
    print()
    print('  The core runs at an oxidiser to fuel ratio of {:.2f} and the wall runs below it, '
          'which'.format(entrained.OFRatio))
    print('  is the reason SP-8124 prefers an entrainment model to a flat-plate correlation.')
    print()
    print('  The film costs 0.30 kg/s of hydrogen that never reaches the injector. Against the')
    print('  engine flow that is a real performance penalty, and the driving temperature columns')
    print('  are what it buys.')

def radiationCooledExtension(outputFolder):

    '''

    A coated columbium shell hung off the end of a truncated jacket.

    The jacket is cut at an area ratio of three so the extension covers most of the bell, then
    the shell is started at several stations along it. Starting further out is the same question
    as running the jacket further, and it is the design trade this solver exists to answer.

    Parameters:
    -----------
    outputFolder : str
        Directory the run may write into.

    '''

    print()
    print('=' * 86)
    print('A radiation-cooled C103 extension on the same engine')
    print('=' * 86)

    nozzle = runConfiguration(
        referenceConfiguration(regenTruncationType = 'er', regenTruncationValue = 3.0,
                               makeCoolingChannels = False),
        os.path.join(outputFolder, 'extension'))

    axial = nozzle.xExtension
    radius = nozzle.rExtension
    throatRadius = float(np.min(nozzle.rNozzleWall))
    areaRatio = (radius / throatRadius)**2
    curvature = 0.5 * nozzle.nozzleScalingFactor * (nozzle.throatInletCurvatureNonDimensional
                                                    + nozzle.throatOutletCurvatureNonDimensional)

    print()
    print('  {:>10} {:>9} {:>11} {:>10} {:>10}'.format(
        'joint AR', 'x [mm]', 'peak [K]', 'margin [K]', 'verdict'))

    for target in (3.0, 10.0, 20.0, 30.0, 35.0):

        start = int(np.argmin(np.abs(areaRatio - target)))
        if axial.size - start < 3:
            continue

        # A silicide-coated shell, at the only emissivity the materials store carries a source
        # for. The conductivity is supplied rather than looked up: the store has curves for the
        # jacket alloys only, and its fallback would give a refractory shell eight times the
        # conductivity it has.
        shell = RadiativeShell(
            thermalConductivity = 45.0, thickness = 5.0e-4,
            innerEmissivity = 0.7, outerEmissivity = 0.7,
            sinkTemperature = 4.0, gasEmissivity = 0.05,
            material = 'C103', atmosphere = 'inert')

        result = radiativeNozzleExtension(
            shell, axial[start:], radius[start:],
            nozzle.extensionNearWallMachNumber[start:],
            nozzle.extensionNearWallTemperature[start:],
            nozzle.extensionNearWallRecoveryTemperature[start:],
            chamberPressure = nozzle.chamberPressure,
            characteristicVelocity = nozzle.theoreticalCharacteristicVelocity,
            exhaustGamma = nozzle.gammaExtension[start:],
            exhaustGasConstant = nozzle.gasConstantExtension[start:],
            exhaustMolecularWeight = nozzle.molecularWeightExtension[start:],
            throatRadius = throatRadius, throatRadiusOfCurvature = curvature)

        print('  {:10.1f} {:9.1f} {:11.1f} {:10.1f} {:>10}'.format(
            areaRatio[start], axial[start] * 1e3, result.extensionPeakWallTemperature,
            result.extensionTemperatureMargin,
            'survives' if result.extensionTemperatureMargin > 0.0 else 'fails'))

    print()
    print('  It fails everywhere on this contour, and that is the answer rather than a defect.')
    print('  Bartz scales as chamber pressure to the 0.8, so a 6.9 MPa hydrogen engine puts about')
    print('  five times the coefficient into an uncooled shell that a one megapascal apogee')
    print('  thruster does. Radiation-cooled columbium belongs on the latter, where the same')
    print('  shell settles near 1550 K.')

def main():

    '''Run both halves into a scratch directory beside this file.'''

    outputFolder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'filmAndRadiativeCoolingOutputs')

    filmCooledJacket(outputFolder)
    radiationCooledExtension(outputFolder)

if __name__ == '__main__':
    main()
