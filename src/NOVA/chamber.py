
# -- NOVA: Combustion Chamber and Converging Section -- #

'''

The half of the contour upstream of the throat.

The method of characteristics builds the diverging section. It starts at the throat. What
gets the flow there is this: a chamber of the volume the propellant combination needs, and a
converging wall that turns it into the throat without separating.

One shape is supported. The wall runs from the chamber barrel through a fillet tangent to it,
down a straight run, and into the throat inlet arc. It is the conventional converging section
and it is what every shipped configuration uses.

A sunken converging section, which recesses the throat inside the chamber and wraps the wall
back around the closure behind it, lives in `experimental/sunkenNozzle.py`. It builds. It is
outside the package because nothing has validated it as a design rather than because it cannot
be drawn.

The near-wall state along the converging wall is quasi one-dimensional: an area ratio at each
station gives a subsonic Mach number, and the isentropic relations give the rest. That is the
only flow model here. It is stated as one.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**The chamber sizing is arithmetic against a definition.** Characteristic length is
chamber volume over throat area, and the volume the section reports is the volume it drew. That
is a closed-form check rather than a model, and the tests hold it to machine precision.

**The converging flow is quasi one-dimensional and unvalidated.** Every station is solved
from its own area ratio as though the flow were uniform across it, which it is not: the wall
turns, and a turning subsonic flow is faster on the inside of the turn than the one-dimensional
value. Nothing here estimates that error. No reference is available for a converging section
of this family. What can be said is that the solve is the isentropic relations applied
consistently, and that it reproduces the throat condition at the throat.

The area ratio has no subsonic solution below one, so a converging wall that dips inside the
throat radius is a geometry error rather than a numerical one. It is reported as one.

----------------------------------------------------------------------
                        Geometry conventions
----------------------------------------------------------------------

Contour geometry is two-dimensional and axisymmetric:

    - X is along the nozzle axis, positive in the direction of the outgoing plume
    - R is the radial direction away from that axis

The converging section is prepended to the diverging contour, so a converging station has a
smaller X than the throat.

All units are mass base SI:
    - Length      [m]
    - Volume      [m^3]
    - Temperature [K]
    - Pressure    [Pa]
    - Angle       [rad] internally, [deg] where a configuration names one

Author: Sean Bowman

'''

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import brentq, fsolve

from .geometryTools import arcSpline, parallelOffset
from .errors import GeometricConstraintError, InvalidInputError
from .contour import divergingSectionFamily
from .gasDynamics import isentropicValues, machFromAreaRatio
from .validation import (Overlay, applyRules, arrayRule, choiceRule, integerRule,
                         numericRule, presentRule, read)

# The converging section reads the diverging contour and the chamber state it was solved in.
# Written as a table rather than as branches: see validation.py for why, and for what each rule
# kind means.
#
# The order matters. Rules are checked in order and the first failure is the one reported, so the
# table runs from the contour that must exist through the chamber state that must be physical.

def _isNotConical(source):

    '''True when the diverging section was solved rather than drawn as a cone.'''

    return divergingSectionFamily(read(source, 'divergingSectionType')) != 'conical'

convergingSectionRules = (

    # -- The contour the converging section attaches to -- #
    arrayRule('xNozzleWall', 'Diverging contour axial coordinate', units = 'm'),
    arrayRule('rNozzleWall', 'Diverging contour radius', units = 'm',
              positive = True, sameLengthAs = 'xNozzleWall'),

    # -- How the section is built -- #
    # There is one shape, so nothing names it. Presence only, since which spellings are legal for
    # the diverging section is decided once, where the configuration is read, by the same
    # resolver the dispatch uses; a literal choice list here would have to enumerate every
    # capitalization and would disagree with that resolver the moment one was missed.
    presentRule('divergingSectionType', 'Diverging section type'),
    numericRule('nozzleScalingFactor', 'Nozzle scaling factor', units = 'm', minimum = 0),
    integerRule('numContourPoints', 'Contour points', minimum = 100, exclusiveMinimum = False),

    # -- The chamber state the flow solve works in -- #
    numericRule('chamberGamma', 'Chamber ratio of specific heats', minimum = 1,
                note = 'Typically 1.1 to 1.67 for combustion gases'),
    numericRule('chamberStagnationTemperature', 'Chamber stagnation temperature',
                units = 'K', minimum = 0),
    numericRule('chamberPressure', 'Chamber pressure', units = 'Pa', minimum = 0),
    numericRule('chamberRGasConstant', 'Chamber specific gas constant',
                units = 'J/kg K', minimum = 0),

    # -- The throat the section runs into -- #
    numericRule('throatRadiusNonDimensional', 'Non-dimensional throat radius', minimum = 0,
                note = 'One by construction'),
    numericRule('throatInletCurvatureNonDimensional', 'Throat inlet curvature', minimum = 0,
                note = 'As a multiple of the throat radius, conventionally 1.5'),

    # -- Section shape, each of which may ask to be worked out rather than given -- #
    numericRule('convergingSectionAngle', 'Converging section angle', units = 'deg',
                minimum = 0, maximum = 90, allowDefault = True),
    numericRule('chamberDiameter', 'Chamber diameter', units = 'm',
                minimum = 0, allowDefault = True),

    # -- Which volutes the section has to leave room for -- #
    choiceRule('makeInletVolute', 'Inlet volute', choices = ('on', 'off')),
    choiceRule('makeOutletVolute', 'Outlet volute', choices = ('on', 'off')),

    # -- The near-wall state a solved diverging section hands over -- #
    arrayRule('nozzleNearWallTemperature', 'Near wall temperature', units = 'K',
              positive = True, when = _isNotConical),
    arrayRule('nozzleNearWallPressure', 'Near wall pressure', units = 'Pa',
              positive = True, when = _isNotConical),
    arrayRule('nozzleNearWallVelocity', 'Near wall velocity', units = 'm/s',
              when = _isNotConical),
    arrayRule('nozzleNearWallMachNumber', 'Near wall Mach number',
              positive = True, when = _isNotConical),
    presentRule('ceaOutput', 'Thermochemistry output', when = _isNotConical),
)

def validateConvergingSectionInputs(state, convergingSectionAngle,
                                    chamberDiameter, inletVolute, outletVolute) -> None:

    '''

    Check that the converging section can be built from what the state carries.

    The rules are the table above, checked by `validation.applyRules`. Three of the four
    arguments may be given per call rather than read off the state, so they are layered over it
    for the check.

    Raises:
    -------
    InvalidInputError
        On the first rule the configuration fails.

    '''

    applyRules(Overlay(state,
                       convergingSectionAngle = convergingSectionAngle,
                       chamberDiameter       = chamberDiameter,
                       inletVolute           = inletVolute,
                       outletVolute          = outletVolute),
               convergingSectionRules)

@dataclass
class ConvergingSectionState:

    '''

    Everything the converging section reads, and everything it produces.

    The contour arrays are extended in place rather than replaced: the converging wall is
    prepended to the diverging one, so the same field is both an input and an output.

    Every field starts as None. One still None after a build is a branch that was not reached.

    '''

    # -- What the section is built from -- #
    # Read by name rather than by attribute, which is why they are named here explicitly.
    chamberLength:                           Any = None
    Lstar:                                   Any = None

    ceaOutput:                               Any = None
    chamberDiameter:                         Any = None
    chamberGamma:                            Any = None
    chamberPressure:                         Any = None
    chamberRGasConstant:                     Any = None
    chamberStagnationTemperature:            Any = None
    convergingSectionAngle:                  Any = None
    divergingSectionType:                    Any = None
    makeInletVolute:                         Any = None
    makeOutletVolute:                        Any = None
    nozzleScalingFactor:                     Any = None
    numContourPoints:                        Any = None
    throatInletCurvatureNonDimensional:      Any = None
    throatRadiusNonDimensional:              Any = None

    # -- Extended in place, since the converging wall is prepended to the diverging one -- #
    chamberContractionRatio:                 Any = None
    chamberLstarActual:                      Any = None
    chamberVolume:                           Any = None
    nozzleNearWallMachNumber:                Any = None
    rNozzleWall:                             Any = None
    xNozzleWall:                             Any = None

    # -- Produced by the build -- #
    chamberBarrelLength:                     Any = None
    nozzleNearWallPressure:                  Any = None
    nozzleNearWallRecoveryTemperature:       Any = None
    nozzleNearWallTemperature:               Any = None
    nozzleNearWallVelocity:                  Any = None

# The fields a build hands back to a Nozzle. Kept beside the class so that adding a field
# and forgetting to surface it is a one-line fix rather than a silent drop.
convergingSectionOutputs = (
    'chamberBarrelLength', 'chamberContractionRatio', 'chamberLstarActual', 'chamberVolume',
    'nozzleNearWallMachNumber',
    'nozzleNearWallPressure', 'nozzleNearWallRecoveryTemperature', 'nozzleNearWallTemperature',
    'nozzleNearWallVelocity', 'rNozzleWall', 'xNozzleWall')

def prependCombustionChamber(state, xConvergingSection: np.ndarray, rConvergingSection: np.ndarray) -> tuple:

    '''

    Prepend a cylindrical combustion chamber barrel to the converging section.

    The barrel length comes from `chamberLength` when that is given, otherwise it is
    derived from the characteristic length `Lstar`:

        Vc      = Lstar * At                  total chamber volume, injector face to throat
        Vconv   = integral( pi r^2 dx )       volume the converging section already occupies
        Lbarrel = (Vc - Vconv) / (pi Rc^2)    the remainder, as a constant-area barrel

    L* is defined over the whole chamber volume, so the converging cone counts toward it.
    Sizing the barrel as Lstar * At / Ac instead would overshoot the target volume by
    exactly the cone, which for a contraction ratio near 3 is a 20-30 % error in Vc.

    Parameters:
    -----------
    xConvergingSection : np.ndarray
        Axial coordinates of the converging section, chamber end first [m]
    rConvergingSection : np.ndarray
        Radial coordinates of the converging section [m]

    Returns:
    --------
    tuple : (x, r) with the barrel prepended, or the inputs unchanged when neither
            `chamberLength` nor `Lstar` is specified

    Raises:
    -------
    InvalidInputError
        If both `chamberLength` and `Lstar` are given, if either is non-positive, or if
        the requested L* is smaller than the converging section volume already implies

    '''

    def isSpecified(value) -> bool:
        if value is None or isinstance(value, (list, tuple)) and len(value) == 0:
            return False
        try:
            return bool(np.isfinite(float(value)))
        except (TypeError, ValueError):
            return False

    chamberLength = getattr(state, 'chamberLength', None)
    characteristicLength = getattr(state, 'Lstar', None)

    haveLength = isSpecified(chamberLength)
    haveLstar  = isSpecified(characteristicLength)

    throatRadius   = float(state.rNozzleWall[0])
    chamberRadius  = float(rConvergingSection[0])
    throatArea     = np.pi * throatRadius**2
    chamberArea    = np.pi * chamberRadius**2

    # Volume of revolution already taken up by the converging section.
    convergingVolume = float(np.trapezoid(np.pi * np.asarray(rConvergingSection, dtype = float)**2,
                                          np.asarray(xConvergingSection, dtype = float)))

    state.chamberContractionRatio = chamberArea / throatArea

    if not haveLength and not haveLstar:
        # No chamber requested: the converging section is the whole chamber.
        state.chamberBarrelLength = 0.0
        state.chamberVolume       = convergingVolume
        state.chamberLstarActual  = convergingVolume / throatArea
        return xConvergingSection, rConvergingSection

    if haveLength and haveLstar:
        raise InvalidInputError(
            message = 'You cannot specify both chamberLength and Lstar, specify one or the other',
            parameterName = 'chamberLength, Lstar',
            value = (float(chamberLength), float(characteristicLength)),
            validRange = 'exactly one of the two',
        )

    if haveLength:
        barrelLength = float(chamberLength)
        if barrelLength < 0:
            raise InvalidInputError(
                message = 'Chamber length must be non-negative',
                parameterName = 'chamberLength',
                value = barrelLength,
                validRange = 'Float >= 0',
            )
    else:
        characteristicLength = float(characteristicLength)
        if characteristicLength <= 0:
            raise InvalidInputError(
                message = 'Characteristic length L* must be positive',
                parameterName = 'Lstar',
                value = characteristicLength,
                validRange = 'Float > 0',
            )
        targetVolume = characteristicLength * throatArea
        barrelLength = (targetVolume - convergingVolume) / chamberArea
        if barrelLength < 0:
            minimumLstar = convergingVolume / throatArea
            raise InvalidInputError(
                message = (f'L* of {characteristicLength:.4f} m implies a chamber volume of '
                           f'{targetVolume * 1e6:.1f} cm^3, but the converging section alone is '
                           f'{convergingVolume * 1e6:.1f} cm^3. Raise L* above {minimumLstar:.4f} m, '
                           f'widen the converging angles, or reduce the chamber diameter.'),
                parameterName = 'Lstar',
                value = characteristicLength,
                validRange = f'Float > {minimumLstar:.4f} m for this converging geometry',
            )

    state.chamberBarrelLength = barrelLength
    state.chamberVolume       = convergingVolume + barrelLength * chamberArea
    state.chamberLstarActual  = state.chamberVolume / throatArea

    print(f'Generating Combustion Chamber: barrel {barrelLength * 1e3:.1f} mm, '
          f'volume {state.chamberVolume * 1e6:.1f} cm^3, L* {state.chamberLstarActual:.4f} m, '
          f'contraction ratio {state.chamberContractionRatio:.2f}.')

    if barrelLength <= 0:
        return xConvergingSection, rConvergingSection

    # Straight barrel at the chamber radius, injector face first. The final point is
    # dropped because it coincides with the start of the converging section.
    barrelPoints = max(2, int(np.floor(state.numContourPoints / 4)))
    xBarrel = np.linspace(xConvergingSection[0] - barrelLength, xConvergingSection[0], barrelPoints)[:-1]
    rBarrel = np.full(xBarrel.shape, chamberRadius)

    return (np.concatenate([xBarrel, xConvergingSection]),
            np.concatenate([rBarrel, rConvergingSection]))

def solveConvergingSection(state, convergingSectionAngle: float = 'default', chamberDiameter: float = 'default',
                      inletVolute: bool = 'default', outletVolute: bool = 'default', geometryOnly: bool = False) -> None:

    '''

    Define the converging section of a nozzle given the desired nozzle type, and perform nozzle contour post-processing
    to include geometry for volute interfacing if volutes are being generated by the program.

    Angles are defined based on the angle made with the nozzle axis.

    Types of nozzles supported:
    - 'trad' : traditional converging section

    The wall meets the chamber barrel tangentially. There is no chamber interface angle to set:
    a barrel is a constant-radius wall, so the only slope that joins it without a kink is zero,
    and a nonzero interface angle used to draw exactly that kink. See the note below.

    '''

    # Validate inputs before processing
    validateConvergingSectionInputs(state, convergingSectionAngle, chamberDiameter, inletVolute, outletVolute)

    # Locally scoped imports
    from scipy.interpolate import UnivariateSpline, interp1d
    from scipy.optimize import fsolve, brentq
    from pandas import read_csv

    # -- Helper Function(s) -- #

    def calculateConvergingFlowProperties(xConvergingSection, rConvergingSection) -> np.ndarray:

        '''

        Calculate the local wall properties for the converging section using quasi 1d compressible flow theory and isentropic relations.

        '''

        # Non-dimensionalize geometry
        xConvergingSection, rConvergingSection = xConvergingSection / state.nozzleScalingFactor, rConvergingSection / state.nozzleScalingFactor

        nearWallMachNumber, temperatureNearWall, pressureNearWall, velocityNearWall \
        = [np.zeros(len(xConvergingSection)) for _ in range(4)]

        for i, _ in enumerate(nearWallMachNumber):

            localAreaRatio = (rConvergingSection[i] / state.throatRadiusNonDimensional)**2

            # A failure to converge here is a geometry problem, not a numerical one: it means a
            # station of the converging wall has no subsonic solution. Name the station.
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings('error')  # Turn warnings into exceptions
                try:
                    quasi1DMachNumber = machFromAreaRatio(localAreaRatio, state.chamberGamma,
                                                          branch = 'subsonic')
                except (RuntimeWarning, Warning) as w:
                    raise ValueError(f'Mach number solver failed to make progress at point {i}: {str(w)}')
                except ValueError as e:
                    raise ValueError(f'Mach number solve failed at point {i}: {e}')

            nearWallMachNumber[i] = quasi1DMachNumber

            temperatureNearWall[i], pressureNearWall[i], velocityNearWall[i] = isentropicValues(nearWallMachNumber[i], state.chamberStagnationTemperature,
                                                                                    state.chamberPressure, state.chamberGamma,
                                                                                    state.chamberRGasConstant)

        return temperatureNearWall, pressureNearWall, velocityNearWall, nearWallMachNumber

    # Check to see if the nozzle object has values associated with the wall points for the diverging section
    # and if not warn the user
    if state.xNozzleWall is None:
        raise Exception(f'There is no diverging section, generate one with Nozzle.truncatedIdealContour()')
    else:
        # Assign relevant properties if the user did not specify them
        if convergingSectionAngle == 'default' and state.convergingSectionAngle is None:
            convergingSectionAngle = 45
        elif state.convergingSectionAngle is not None:
            convergingSectionAngle = state.convergingSectionAngle

        # Fixed at zero rather than read from the configuration. A barrel is a constant-radius
        # wall, and the only angle that meets it without a slope discontinuity is the one that
        # continues it: flat. A nonzero value here used to draw that discontinuity deliberately,
        # from a time before a straight chamber existed to draw it against.
        chamberInterfaceAngle = 0.0

        if chamberDiameter == 'default' and state.chamberDiameter is None:
            chamberDiameter          = 580e-3
        elif state.chamberDiameter is not None:
            # if not np.isnan(state.contractionAreaRatio):
            #     state.chamberDiameter = np.sqrt((4 * np.pi * min(state.rNozzleWall)**2) / np.pi) * 2
            #     chamberDiameter = state.chamberDiameter
            # else:
            chamberDiameter = state.chamberDiameter

        if inletVolute == 'default' and state.makeInletVolute == 'off':
            inletVolute    = False
        elif state.makeInletVolute == 'on':
            inletVolute = True

        if outletVolute == 'default' and state.makeOutletVolute == 'off':
            outletVolute    = False
        elif state.makeOutletVolute == 'on':
            outletVolute = True

    print(f'Generating Traditional Converging Section.')

    # -- Interface with chamber -- #

    # Convert the angles with respect to axis to angles with respect to radius for calcs
    convergingSectionAngle, chamberInterfaceAngle = np.deg2rad(convergingSectionAngle), np.deg2rad(chamberInterfaceAngle)
    convergingSectionAngle, chamberInterfaceAngle = np.pi/2 - convergingSectionAngle, np.pi/2 - chamberInterfaceAngle

    # Create Rao Throat for converging section
    convergingRadiusOfCurvature = state.throatInletCurvatureNonDimensional * state.rNozzleWall[0]
    convergingThroatAngles      = np.linspace(np.pi + convergingSectionAngle, 3*np.pi/2, int(np.floor(state.numContourPoints / 4)))
    xConvergingThroat           = convergingRadiusOfCurvature * np.cos(convergingThroatAngles)
    rConvergingThroat           = convergingRadiusOfCurvature * np.sin(convergingThroatAngles) \
                                  + state.rNozzleWall[0] + convergingRadiusOfCurvature

    # Draw 'convergingSectionAngle' degree angle line off of Rao throat out to the chamber wall
    chamberDiameter = state.chamberDiameter

    # Interface with chamber
    interfaceRadiusOfCurvature = state.throatInletCurvatureNonDimensional * state.rNozzleWall[0]

    interfaceCircleCenterR     = chamberDiameter/2 - interfaceRadiusOfCurvature * np.sin(chamberInterfaceAngle)
    rStraightStep              = interfaceCircleCenterR + interfaceRadiusOfCurvature * np.cos(np.pi/2 - convergingSectionAngle) - rConvergingThroat[0]
    xStraightStep              = rStraightStep / np.tan(np.pi/2 - convergingSectionAngle)
    xFilletStep                = interfaceRadiusOfCurvature * np.cos(convergingSectionAngle)
    interfaceCircleCenterX     = xConvergingThroat[0] - xStraightStep - xFilletStep
    interfaceAngles            = np.linspace(chamberInterfaceAngle, convergingSectionAngle, int(np.floor(state.numContourPoints / 4)))
    xInterface                 = interfaceRadiusOfCurvature * np.cos(interfaceAngles) + interfaceCircleCenterX
    rInterface                 = interfaceRadiusOfCurvature * np.sin(interfaceAngles) + interfaceCircleCenterR

    # Concatenate converging section arrays
    xConvergingSection = np.concatenate([xInterface, xConvergingThroat])
    rConvergingSection = np.concatenate([rInterface, rConvergingThroat])

    # Prepend the cylindrical combustion chamber. The barrel is added before the
    # flow properties are evaluated below, so the constant-area chamber station
    # falls out of the same isentropic area-ratio solve as the rest of the
    # converging section rather than needing a special case.
    xConvergingSection, rConvergingSection = prependCombustionChamber(state,
        xConvergingSection, rConvergingSection)

    # Concantentate and interpolate (equal arc spacing of nozzle contour)
    xNozzleWallCoarse = np.concatenate([xConvergingSection[:-1], state.xNozzleWall])
    rNozzleWallCoarse = np.concatenate([rConvergingSection[:-1], state.rNozzleWall])

    xNozzle, rNozzle  = arcSpline(xNozzleWallCoarse, rNozzleWallCoarse, newNumPoints = state.numContourPoints)

    # Calculate flow properties only if not geometry-only mode. Every family reaches here now: a
    # cone carries no characteristic solve, so it supplies its diverging near-wall Mach number
    # from the one-dimensional area-Mach relation instead, and the concatenation below does not
    # care which of the two produced it.
    if not geometryOnly:

        # Wall properties
        temperatureWall, pressureWall, velocityWall, machNumberWall = calculateConvergingFlowProperties(xConvergingSection, rConvergingSection)

        # Only the Mach number is interpolated onto the resampled contour. Temperature,
        # pressure and velocity are isentropic functions of it at fixed stagnation
        # conditions, so deriving them keeps the four arrays consistent with each other
        # by construction. Interpolating each separately leaves them satisfying the
        # relation they came from only where it happens to be linear, and across the
        # sonic transition at the throat it is not: that one station used to carry a
        # ten percent inconsistency.
        nozzleWallMachNumberCoarse  = np.concatenate([machNumberWall[:-1], state.nozzleNearWallMachNumber])
        nozzleNearWallMachNumber    = UnivariateSpline(xNozzleWallCoarse, nozzleWallMachNumberCoarse, k = 1, s = 0)(xNozzle)
        nozzleNearWallTemperature, nozzleNearWallPressure, nozzleNearWallVelocity                         = isentropicValues(nozzleNearWallMachNumber, state.chamberStagnationTemperature,
                               state.chamberPressure, state.chamberGamma, state.chamberRGasConstant)

        # Calculate recovery temperature distribution
        recoveryFactor = state.ceaOutput.ceaResults['combustionChamberPrandtlNumber']**(1/3) # For turbulent flows
        recoveryTemperature = nozzleNearWallTemperature * (1 + recoveryFactor * ((state.chamberGamma - 1) / 2) * nozzleNearWallMachNumber**2)

    # Assign properties to object
    # Always assign geometry
    state.xNozzleWall = xNozzle
    state.rNozzleWall = rNozzle

    # Only assign flow properties if calculated. This condition has to be the same one that
    # guarded the calculation above, or the assignment reads names that were never bound.
    if not geometryOnly:
        state.nozzleNearWallTemperature         = nozzleNearWallTemperature
        state.nozzleNearWallPressure            = nozzleNearWallPressure
        state.nozzleNearWallVelocity            = nozzleNearWallVelocity
        state.nozzleNearWallMachNumber          = nozzleNearWallMachNumber
        state.nozzleNearWallRecoveryTemperature = recoveryTemperature

    return state
