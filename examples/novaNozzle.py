
# -- The NOVA nozzle, end to end -- #

'''

The reference nozzle, run through every part of the tool.

`assets/NOVANozzle.json` reaches most of NOVA on its own: contour, chamber, cooling jacket, film,
volutes, keep-out, printability, radiation-cooled extension and the correlated plume all run from
`generateNozzle()`. Four capabilities have no configuration key and are driven here against the
geometry that run produced: the characteristics plume march, the compressible boundary layer, an
ablative liner as the alternative to a cooled wall, and the materials store the wall alloys come
from.

The engine is a 100 kN LOX/LH2 upper stage: Pc = 1000 psia, MR = 5.5, area ratio 40, a truncated
ideal contour at an 80 percent length fraction. The operating point matches the CEA validation
case in `tests/testCeaInterface.py`.

Run it from the repository root:

    python examples/novaNozzle.py

Set NOVA_HEADLESS=1 to write the figures without opening a window.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

Nothing here is validated by being run. Each solver carries its own validation statement in its
module docstring, and this script inherits every one of them without adding evidence. What it
demonstrates is coverage: that each path runs, on one engine, and reports a number.

Two of the numbers printed below rest on inputs chosen for this example rather than measured. The
C103 thermal conductivity is a nominal handbook figure for Nb-10Hf-1Ti, and the ablative liner's
char removal efficiency is a calibration fitted to nothing. Both are called out where they print.

Three results come out negative on this engine, and each is the solver reporting rather than
failing. The C103 extension exceeds its temperature limit, because Bartz scales with chamber
pressure to the 0.8 and a 6.9 MPa hydrogen engine puts a coated columbium shell over its limit at
any area ratio. The plume march reaches only the near-lip region and says so, because a truncated
ideal contour leaves a 9 degree divergent exit and the march degrades with that angle. The
ablative liner recedes the throat by a centimeter in eight seconds, which is what an uncooled
liner does on a hydrogen engine and is the reason this one is regeneratively cooled.

All units are mass base SI.

Author: Sean Bowman

'''

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from NOVA.Nozzle import Nozzle                                          # noqa: E402
from NOVA.boundaryLayer import solveBoundaryLayer                       # noqa: E402
from NOVA.ablative import (ablativeNozzleLiner,                         # noqa: E402
                           propellantElementMassFractions)
from NOVA.materials import (availableMaterials, availableWallMaterials,  # noqa: E402
                            materialProfile, maxUseTemperature, wallMaterialCurves)

RULE = '=' * 86

# CODATA molar gas constant [J/kmol-K], for recovering molecular weight from a specific one.
R_UNIVERSAL_KMOL = 8314.46261815324

def referenceNozzle():

    '''

    The shipped reference nozzle, generated from its configuration.

    Returns:
    --------
    Nozzle
        The generated object, with every attribute the run set.

    '''

    print(RULE)
    print('The NOVA nozzle')
    print(RULE)

    nozzle = Nozzle()
    nozzle.generateNozzle()

    return nozzle

def reportConfiguredFeatures(nozzle):

    '''

    What the configuration reached: contour, chamber, jacket, film, volutes and extension.

    Parameters:
    -----------
    nozzle : Nozzle
        A generated nozzle.

    '''

    throatRadius = float(np.min(nozzle.rNozzleWall))

    print()
    print('Contour')
    print('  family                       %s' % nozzle.divergingSectionType)
    print('  throat radius                %8.2f mm' % (1000.0 * throatRadius))
    print('  exit radius                  %8.2f mm' % (1000.0 * nozzle.rNozzleWall[-1]))
    print('  length                       %8.2f mm' % (1000.0 * nozzle.xNozzleWall[-1]))
    print('  area ratio reached           %8.3f' % nozzle.exitExpansionRatio)
    print('  thrust coefficient           %8.4f' % nozzle.thrustCoef)

    print()
    print('Cooling jacket')
    if getattr(nozzle, 'channelRadius', None) is not None:
        radius = np.asarray(nozzle.channelRadius, dtype = float)
        print('  channels                     %8d %s' % (nozzle.nChannel, nozzle.channelType))
        print('  wall alloy                   %s' % nozzle.material)
        print('  channel radius               %8.3f to %.3f mm'
              % (1000.0 * np.nanmin(radius), 1000.0 * np.nanmax(radius)))
    else:
        print('  not built on this run')

    print()
    print('Radiation-cooled extension')
    peak = getattr(nozzle, 'extensionPeakWallTemperature', None)
    if peak is not None:
        margin = getattr(nozzle, 'extensionTemperatureMargin', float('nan'))
        print('  shell                        %s, %.1f mm'
              % (nozzle.extensionMaterial, 1000.0 * nozzle.extensionThickness))
        print('  peak wall temperature        %8.1f K' % peak)
        print('  margin to the limit          %8.1f K  (%s)'
              % (margin, 'survives' if margin > 0.0 else 'fails'))
        print('  conductivity used            %8.1f W/m-K, a nominal handbook figure for'
              % nozzle.extensionThermalConductivity)
        print('                               Nb-10Hf-1Ti rather than a measured curve')
    else:
        print('  not built on this run')

def marchThePlume(nozzle):

    '''

    The plume interior, by continuing the characteristics march past the lip.

    `generateNozzle` runs the correlated plume only. The march is the other model, and it has no
    configuration key, so it is driven here.

    Parameters:
    -----------
    nozzle : Nozzle
        A generated nozzle.

    '''

    print()
    print(RULE)
    print('Plume interior, method of characteristics')
    print(RULE)

    ambient = float(nozzle.plumeAmbientPressure)
    field = nozzle.plumeField(ambientPressure = ambient, numRays = 24, exitPoints = 60)

    print('  ambient                      %8.0f Pa' % ambient)

    print('  solved                       %s' % field.solved)
    print('  within the tested envelope   %s' % field.withinEnvelope)
    print('  exit Mach number             %8.3f' % field.exitMach)
    print('  exit pressure ratio          %8.3f' % field.exitPressureRatio)
    print('  lip turn angle               %8.2f deg' % field.lipTurnAngle)
    print('  points solved                %8d' % len(np.asarray(field.nodeX).ravel()))
    print('  shock cells resolved         %8s' % field.cellsResolved)
    print('  Mach disk present            %s' % field.machDiskPresent)

    if field.notes:
        for note in field.notes:
            print('  note: %s' % note)

    return field

def solveTheBoundaryLayer(nozzle):

    '''

    Compressible turbulent boundary layer along the wall the contour produced.

    The layer is what stands between the inviscid contour and the wall it is cut to. It has no
    configuration key either.

    Parameters:
    -----------
    nozzle : Nozzle
        A generated nozzle.

    '''

    print()
    print(RULE)
    print('Boundary layer')
    print(RULE)

    axial = np.asarray(nozzle.xNozzleWall, dtype = float)
    radius = np.asarray(nozzle.rNozzleWall, dtype = float)

    layer = solveBoundaryLayer(axial, radius,
                               np.asarray(nozzle.nozzleNearWallMachNumber, dtype = float),
                               np.asarray(nozzle.nozzleNearWallTemperature, dtype = float),
                               np.asarray(nozzle.nozzleNearWallPressure, dtype = float),
                               np.asarray(nozzle.nozzleNearWallVelocity, dtype = float),
                               nozzle.chamberGamma, nozzle.chamberRGasConstant,
                               wallTemperature = 800.0)

    displacement = np.asarray(layer['displacementThickness'], dtype = float)
    momentum = np.asarray(layer['momentumThickness'], dtype = float)

    print('  displacement thickness at exit  %8.3f mm' % (1000.0 * displacement[-1]))
    print('  momentum thickness at exit      %8.3f mm' % (1000.0 * momentum[-1]))
    print('  displacement as a fraction of exit radius  %6.4f'
          % (displacement[-1] / radius[-1]))

    return layer

def ablativeAlternative(nozzle):

    '''

    The same contour with a charring liner instead of a cooled wall.

    An ablator is the other way to survive the heat flux: the wall is consumed rather than cooled.
    The solver takes the exhaust and the geometry directly, with no `Nozzle` involved, which is
    why a configuration cannot reach it.

    Parameters:
    -----------
    nozzle : Nozzle
        A generated nozzle, read for its geometry and near-wall exhaust state.

    '''

    print()
    print(RULE)
    print('Ablative liner on the same contour')
    print(RULE)

    axial = np.asarray(nozzle.xNozzleWall, dtype = float)
    radius = np.asarray(nozzle.rNozzleWall, dtype = float)
    mach = np.asarray(nozzle.nozzleNearWallMachNumber, dtype = float)
    temperature = np.asarray(nozzle.nozzleNearWallTemperature, dtype = float)

    curvature = 0.5 * nozzle.nozzleScalingFactor * (nozzle.throatInletCurvatureNonDimensional
                                                    + nozzle.throatOutletCurvatureNonDimensional)

    # Combustion conserves elements, so the exhaust composition follows from the reactants and
    # the mixture ratio without a second equilibrium solve.
    exhaust = propellantElementMassFractions(
        fuelElements = {'H': 1.0},
        oxidiserElements = {'O': 1.0},
        mixtureRatio = float(nozzle.OFRatio))

    molecularWeight = R_UNIVERSAL_KMOL / float(nozzle.chamberRGasConstant)

    response = ablativeNozzleLiner(
        'TACOT v3.0', axial, radius, mach, temperature,
        edgeElements = exhaust,
        chamberPressure = float(nozzle.chamberPressure),
        chamberTemperature = float(nozzle.chamberStagnationTemperature),
        characteristicVelocity = float(nozzle.theoreticalCharacteristicVelocity),
        exhaustGamma = float(nozzle.chamberGamma),
        exhaustGasConstant = float(nozzle.chamberRGasConstant),
        exhaustMolecularWeight = molecularWeight,
        throatRadiusOfCurvature = curvature,
        burnTime = 8.0,
        linerThickness = 0.030,
        timeStep = 0.05,
        numberOfNodes = 41,
        # Fitted to nothing. One returns the transport-limited bound; anything below it is a
        # calibration, and it carries only as far as the firing it was fitted to.
        charRemovalEfficiency = 0.12,
        viewFactor = 0.5)

    recession = np.asarray(response.recession, dtype = float)
    surface = np.asarray(response.surfaceTemperature, dtype = float)

    print('  exhaust by element           '
          + ', '.join('%s %.4f' % pair for pair in sorted(exhaust.items())))
    print('  exhaust molecular weight     %8.3f g/mol' % molecularWeight)
    print('  throat radius of curvature   %8.2f mm' % (1000.0 * curvature))
    print('  stations solved              %8d' % len(recession))
    print('  peak surface temperature     %8.1f K' % np.nanmax(surface))
    print('  throat recession in 8 s      %8.2f mm' % (1000.0 * response.throatRecession))
    print('  throat area growth           %8.4f' % response.throatAreaRatio)
    print('  worst station recession      %8.2f mm' % (1000.0 * np.nanmax(recession)))
    print('  char removal efficiency      %8.2f, a calibration rather than a measurement' % 0.12)

    return response

def reportTheMaterialsStore():

    '''

    The two material stores the tool draws on.

    The wall alloys carry temperature-dependent property curves, and whether a point on a curve
    was measured or held flat is recorded alongside it. The non-metallics carry a profile and a
    use limit instead, which is what an extension or a liner is chosen against.

    '''

    print()
    print(RULE)
    print('Wall alloys, from their property curves')
    print(RULE)
    print('  %-16s %12s %14s  %s' % ('alloy', 'k at 300 K', 'range', 'conductivity measured'))

    for name in availableWallMaterials():
        curves = wallMaterialCurves(name)
        temperature = np.asarray(curves['temperatureK'], dtype = float)
        conductivity = np.asarray(curves['thermalConductivity'], dtype = float)
        atRoom = float(np.interp(300.0, temperature, conductivity))
        measured = 'yes' if curves['measured'].get('thermalConductivity', False) else 'held flat'
        print('  %-16s %9.1f W/m-K %5.0f-%.0f K  %s'
              % (name, atRoom, temperature[0], temperature[-1], measured))

    print()
    print(RULE)
    print('Non-metallics and refractories, for liners and extensions')
    print(RULE)
    print('  %-20s %-18s %s' % ('material', 'class', 'limit in an inert atmosphere'))

    for name in availableMaterials():
        profile = materialProfile(name)
        try:
            limit = '%.0f degC' % maxUseTemperature(name, 'inert')
        except KeyError:
            limit = 'not stated for this atmosphere'
        print('  %-20s %-18s %s' % (name, profile['class'], limit))

def main():

    nozzle = referenceNozzle()
    reportConfiguredFeatures(nozzle)
    marchThePlume(nozzle)
    solveTheBoundaryLayer(nozzle)
    ablativeAlternative(nozzle)
    reportTheMaterialsStore()

    print()
    print('Output written to %s' % nozzle.dataFolder)

    return nozzle

if __name__ == '__main__':
    main()
