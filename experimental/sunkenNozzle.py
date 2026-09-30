# -- NOVA (experimental): Sunken Throat Converging Section -- #

'''

The converging section that recesses the throat inside the chamber.

A traditional converging section runs a cone from the chamber wall into the throat arc. A sunken
one puts the throat inside the chamber instead, and wraps the wall back around the closure behind
it, which buys chamber volume at a given overall length and shortens the run the coolant makes
between the manifolds. The wall is stitched from an ellipse at the entry, an inner arc, a single
conic control point and the wall that closes onto the throat, with the hub radius solved so the
closure lands on the throat rather than below it.

----------------------------------------------------------------------
                        Status
----------------------------------------------------------------------

This builds. It is here because the package does not offer a sunken contour, not because the
contour cannot be drawn.

It did not build until `arcSpline` was made shape preserving. The stitch this contour presents is
a dense ellipse, a dense arc, a single isolated conic control point, then a dense wall, and the
unconstrained cubic that `arcSpline` used to fit rang across the isolated point. That put sixteen
of sixty contour points below the throat radius, the worst 15.6 mm inside it, and an area ratio
below one has no subsonic solution, so the run failed two hundred lines downstream in the Mach
solver rather than at the geometry that caused it. `arcSpline` now fits a shape-preserving
interpolant by default, which cannot leave the range of the points it is given.

Driven directly against the shipped regenerative example, with the diverging contour and chamber
thermochemistry of a real run and a throat eccentricity of 0.88, this solver returns a 100-point
contour whose minimum radius is 0.050464 m against a throat of 0.050320 m, no points below the
throat, and a near-wall Mach number running 0.117 at the chamber to 3.787 at the exit. Asking it
for the old curvature-continuous fit reproduces the original failure exactly, a subsonic area-Mach
solve refused at an area ratio of 0.684.

What that does not establish: that the resulting nozzle is a good one. The contour closes and the
quasi-1D flow solve runs on it. Nothing here has been checked against a reference sunken design,
and the correction terms the cooling correlations would need for a recessed throat, noted in
`docs/NozzleCooling.md`, do not exist.

----------------------------------------------------------------------
                        Wiring it back in
----------------------------------------------------------------------

`solveSunkenConvergingSection` takes the same state object `chamber.solveConvergingSection`
builds, plus its local quasi-1D wall property helper, and returns what the traditional branch
assigns. A caller reinstating the feature needs to:

  - restore the six configuration keys listed in `sunkenConfigurationKeys` on the Nozzle and in
    the GUI schema, and add `sunkenRules` to `chamber.convergingSectionRules`,
  - give the converging section a shape selector again: `chamber.solveConvergingSection` builds
    one traditional shape unconditionally now, with no `contourType` field or choice rule left to
    branch on,
  - carry `xSunkTurnaround2D` and `rSunkTurnaround2D` on `ConvergingSectionState` and
    `RegenChannelState` again, since the outlet volute interface reads them,
  - put back the `ConvergingSectionState` fields this module is the only reader of:
    `conicDepthModifier`, `conicPinchModifier`, `hotWallThickness`, `infillThickness`,
    `nChannel`, `numCrossSections`, `shellThickness`, `throatBackWallPitch`,
    `throatEccentricity`, `throatEntryLength` and `throatGapThickness`,
  - bring `keepOut.py` back into the package with it, since the closure is wrapped around that
    envelope; it sits beside this module and is imported from there.

'''

import numpy as np
from scipy.interpolate import UnivariateSpline
from scipy.optimize import brentq

from NOVA.errors import GeometricConstraintError
from NOVA.gasDynamics import isentropicValues
from NOVA.geometryTools import arcSpline, parallelOffset
from keepOut import keepOutEnvelope
from NOVA.validation import integerRule, numericRule

# The configuration keys that exist only for this contour. They were removed from Nozzle and from
# the GUI schema when the feature moved here.
sunkenConfigurationKeys = ('conicDepthModifier', 'conicPinchModifier', 'throatBackWallPitch',
                           'throatEccentricity', 'throatEntryLength', 'throatGapThickness')

# The validation rules that guarded those keys, lifted out of chamber.convergingSectionRules.
# They were gated on a `contourType == 'sunk'` predicate that no longer has anything to match.
sunkenRules = (
    numericRule('throatEntryLength', 'Throat entry length', units = 'm', minimum = 0),
    numericRule('throatEccentricity', 'Throat eccentricity', minimum = 0, maximum = 1),
    numericRule('throatBackWallPitch', 'Throat back wall pitch', units = 'deg',
                minimum = 0, maximum = 90),
    numericRule('throatGapThickness', 'Throat gap thickness', units = 'm', minimum = 0),
    numericRule('conicPinchModifier', 'Conic pinch modifier', minimum = 0),
    numericRule('conicDepthModifier', 'Conic depth modifier', minimum = 0),
    integerRule('nChannel', 'Number of channels', minimum = 10, exclusiveMinimum = False),
    numericRule('hotWallThickness', 'Hot wall thickness', units = 'm',
                minimum = 0.5e-3, exclusiveMinimum = False),
    numericRule('shellThickness', 'Shell thickness', units = 'm', minimum = 0),
    numericRule('infillThickness', 'Infill thickness', units = 'm',
                minimum = 0.5e-3, exclusiveMinimum = False),
    integerRule('numCrossSections', 'Cross sections', minimum = 50, exclusiveMinimum = False),
)

def solveSunkenConvergingSection(state, geometryOnly, calculateConvergingFlowProperties):

    '''

    Build the sunken converging section and stitch it onto the diverging contour.

    Parameters:
    -----------
    state : ConvergingSectionState
        The state chamber.solveConvergingSection assembles, carrying the diverging contour, the
        chamber thermochemistry and the jacket definition the wall wraps around.
    geometryOnly : bool
        True draws the wall and skips the flow solve.
    calculateConvergingFlowProperties : callable
        The quasi-1D wall property solver local to chamber.solveConvergingSection. Takes an
        (x, r) pair and returns temperature, pressure, velocity and Mach number along it.

    Returns:
    --------
    tuple
        (xNozzle, rNozzle, flowProperties, turnaround), where flowProperties is None under
        geometryOnly and otherwise a dict of the five near-wall arrays, and turnaround is the
        (x, r) pair the outlet volute routes around.

    Raises:
    -------
    GeometricConstraintError
        If the converging wall cannot be closed onto the throat, or closes below it.

    '''

    print(f'Generating Sunken Converging Section.')

    # Widest a channel can be where it leaves the jacket, from the wedge of the
    # annulus one of nChannel channels occupies there. The channels leave at the
    # turnaround, which sits at the chamber wall, so that is the station the wedge is
    # measured at. Reading it off max(rNozzleWall) instead takes the nozzle exit, a
    # station the jacket does not reach.
    offsetHotWallThickness = state.hotWallThickness - state.infillThickness
    arcAngle = 2*np.pi / state.nChannel
    theta = arcAngle/2
    R = 0.5*state.chamberDiameter + offsetHotWallThickness
    r = R*np.sin(theta) / (1 - np.sin(theta))
    maxChannelOutletRadius = r - state.infillThickness / 2

    outerArcRadius = 2*maxChannelOutletRadius + state.hotWallThickness + state.shellThickness
    state.keepOutAxialOffset = -(state.throatEntryLength - outerArcRadius)

    # The sunken chamber wraps around whatever closes it, so the closure is described
    # as a keep-out envelope and the wall is built to clear it.
    throatRadius = min(state.rNozzleWall)

    def sunkenInnerWall(hubRadius):

        '''Envelope at this hub radius, and the wall that stands off it.'''

        envelope = keepOutEnvelope(chamberRadius = 0.5*state.chamberDiameter,
                                   axialOffset   = state.keepOutAxialOffset,
                                   radius        = state.keepOutRadius,
                                   depth         = state.keepOutDepth,
                                   hubRadius     = hubRadius,
                                   numPoints     = state.numCrossSections)
        xWall, rWall = parallelOffset(envelope.x, envelope.r, -2*outerArcRadius)

        return envelope, xWall, rWall

    # The wall that stands off the envelope is the converging wall, so it cannot close
    # below the throat: an area ratio under one has no subsonic solution and the flow
    # solve downstream fails on it rather than on the geometry that caused it. The hub
    # radius is what sets where it closes, and the offset between the two is not a
    # simple sum, so where the configuration does not name a hub it is solved for.
    if state.keepOutHubRadius is None or not np.isfinite(state.keepOutHubRadius):
        # Solved a hair outside the throat rather than onto it, so the check below
        # is not deciding on the last bit of a float.
        closureTarget = throatRadius * (1 + 1e-9)

        def closureResidual(hubRadius):
            return sunkenInnerWall(hubRadius)[2].min() - closureTarget

        upperHub = 0.5*state.chamberDiameter * (1 - 1e-6)
        if closureResidual(upperHub) < 0:
            raise GeometricConstraintError(
                message = ('The sunken converging wall cannot be closed onto the throat for '
                           'any keep-out hub radius. The turnaround is too wide for the '
                           'chamber, so reduce nChannel, the wall thicknesses, or the '
                           'throat entry length'),
                constraintType = 'sunkenWallClosure',
                value = float(sunkenInnerWall(upperHub)[2].min()),
                limit = float(throatRadius))
        state.keepOutHubRadius = float(brentq(closureResidual, 1e-6, upperHub))

    state.nozzleKeepOut, xInnerWall, rInnerWall = sunkenInnerWall(state.keepOutHubRadius)

    if rInnerWall.min() < throatRadius * (1 - 1e-9):
        raise GeometricConstraintError(
            message = ('The sunken converging wall closes below the throat radius, which has '
                       'no subsonic solution. Raise keepOutHubRadius, or leave it unset and '
                       'let the closure be solved for'),
            constraintType = 'sunkenWallClosure',
            value = float(rInnerWall.min()),
            limit = float(throatRadius))

    # Outer envelope
    xOuterEnvelope, rOuterEnvelope = state.nozzleKeepOut.x.copy(), state.nozzleKeepOut.r.copy()

    xInnerWall, rInnerWall = np.flip(xInnerWall),  np.flip(rInnerWall)

    # Outer Arc
    xOuterArcCenter = xOuterEnvelope[0]
    rOuterArcCenter = rOuterEnvelope[0] - outerArcRadius
    theta = np.linspace(3*np.pi/2,np.pi/2)
    xOuterArc = outerArcRadius*np.cos(theta) + xOuterArcCenter
    rOuterArc = outerArcRadius*np.sin(theta) + rOuterArcCenter

    xInnerWall += abs(xInnerWall[-1] - xOuterArc[0])
    xOuterArc, rOuterArc = xOuterArc[1:-1], rOuterArc[1:-1]

    rOuterArc = np.delete(rOuterArc, np.where(np.diff(xOuterArc) == 0))
    xOuterArc = np.delete(xOuterArc, np.where(np.diff(xOuterArc) == 0))

    # Throat ellipse
    semimajor = np.abs(state.keepOutAxialOffset) + outerArcRadius
    semiminor = semimajor*np.sqrt(1-state.throatEccentricity**2)

    # idk how to replace channel throat inlet radius so were doing this instead
    offsetHotWallThickness = state.hotWallThickness - state.infillThickness
    arcAngle = 2*np.pi / state.nChannel
    theta = arcAngle/2
    R = min(state.rNozzleWall) + offsetHotWallThickness
    r = R*np.sin(theta) / (1 - np.sin(theta))
    maxThroatChannelRadius = r - state.infillThickness / 2

    # Inner arc
    innerArcRadius = 2*maxThroatChannelRadius + state.hotWallThickness + state.shellThickness + state.throatGapThickness/2
    def ellipseCurvature(a, b, theta):
        return (a * b) / (( (a * np.sin(theta))**2 + (b * np.cos(theta))**2 )**1.5)

    targetCurvature = 1 / innerArcRadius

    def f(theta): return ellipseCurvature(semimajor, semiminor, theta) - targetCurvature

    tStart = 3*np.pi/2
    tEnd = np.pi
    if ellipseCurvature(semimajor, semiminor, np.pi) > targetCurvature:
        tMatch = brentq(f, tStart, tEnd)
    else:
        # The throat ellipse has to curve at least as tightly as the arc it hands off
        # to, or there is no station where the two are tangent. Its tightest curvature
        # is a/b^2 at the minor axis, so the condition reduces to a(1 - e^2) < r_arc,
        # which is a lower bound on the eccentricity for a given gap thickness.
        minimumEccentricity = np.sqrt(max(0.0, 1 - innerArcRadius / semimajor))
        raise GeometricConstraintError(
            message = ('The throat ellipse never curves as tightly as the inner arc, so the '
                       'two cannot be made tangent. Raise throatEccentricity above '
                       f'{minimumEccentricity:.4f}, or raise throatGapThickness'),
            constraintType = 'throatEllipseCurvature',
            value = state.throatEccentricity,
            limit = minimumEccentricity)

    theta = np.linspace(3*np.pi/2, tMatch, 100)
    xEllipse = semimajor * np.cos(theta)
    rEllipse = semiminor * np.sin(theta)
    rEllipse += semiminor + state.rNozzleWall[0]

    xEnd = xEllipse[-1]
    rEnd = rEllipse[-1]
    dx = np.gradient(xEllipse)
    dr = np.gradient(rEllipse)
    slopeEnd = dr[-1] / dx[-1]
    thetaTangent = np.arctan(slopeEnd)

    theta = np.linspace(3*np.pi/2+thetaTangent,(np.pi/2)-np.deg2rad(state.throatBackWallPitch))
    xInnerArcCenter = xEnd - innerArcRadius * np.sin(thetaTangent)
    rInnerArcCenter = rEnd + innerArcRadius * np.cos(thetaTangent)
    xInnerArc = (innerArcRadius*np.cos(theta) + xInnerArcCenter)[1:]
    rInnerArc = (innerArcRadius*np.sin(theta) + rInnerArcCenter)[1:]

    # Psuedo conic
    xConicCTRL = xEllipse[-1] - xEllipse[-1]*state.conicDepthModifier
    drConicCTRL = abs(xInnerArc[-1])*np.tan(0.5*np.deg2rad(state.throatBackWallPitch)) * state.conicPinchModifier
    rConicCTRL = state.rNozzleWall[0] + drConicCTRL
    xConicGuide = [xInnerArc[-1],xConicCTRL,xInnerWall[0]]
    rConicGuide = [rInnerArc[-1],rConicCTRL,rInnerWall[0]]

    # Stitch it all together
    xConvergingSectionRough = np.flip(np.concatenate([xEllipse,xInnerArc,[xConicCTRL],xInnerWall]))
    rConvergingSectionRough = np.flip(np.concatenate([rEllipse,rInnerArc,[rConicCTRL],rInnerWall]))
    xConvergingSection, rConvergingSection = arcSpline(xConvergingSectionRough,rConvergingSectionRough, newNumPoints=state.numCrossSections)

    # Concantentate and interpolate (equal arc spacing of nozzle contour)

    xNozzleWallCoarse = np.concatenate([xConvergingSection[:-1], state.xNozzleWall])
    rNozzleWallCoarse = np.concatenate([rConvergingSection[:-1], state.rNozzleWall])

    xNozzle, rNozzle  = arcSpline(xNozzleWallCoarse, rNozzleWallCoarse, newNumPoints = state.numContourPoints)

    # store for outlet volute channel interfacing
    xSunkTurnaround2D = np.concatenate([xOuterArc,xOuterEnvelope])
    rSunkTurnaround2D = np.concatenate([rOuterArc,rOuterEnvelope])

    throatIndex = rNozzle.argmin()

    # Calculate flow properties only if not geometry-only mode
    if not geometryOnly:
        # Near Wall properties
        # Flow properties do not include the turnaround outside the chamber
        xConvergingFlow, rConvergingFlow = xNozzle[:throatIndex], rNozzle[:throatIndex]
        temperatureNearWallConv, pressureNearWallConv, velocityNearWallConv, machNumberNearWallConv = \
            calculateConvergingFlowProperties(xConvergingFlow, rConvergingFlow)
        # As in the traditional case: interpolate the Mach number and derive the rest
        # from it, so the four arrays cannot disagree about the state they describe.
        machNumberWallDiv  = UnivariateSpline(state.xNozzleWall, state.nozzleNearWallMachNumber , k = 1, s = 0)(xNozzle[throatIndex:])
        nozzleNearWallMachNumber  = np.concatenate([machNumberNearWallConv , machNumberWallDiv ])
        nozzleNearWallTemperature, nozzleNearWallPressure, nozzleNearWallVelocity                         = isentropicValues(nozzleNearWallMachNumber, state.chamberStagnationTemperature,
                               state.chamberPressure, state.chamberGamma, state.chamberRGasConstant)

        # Calculate recovery temperature distribution
        recoveryFactor      = state.ceaOutput.ceaResults['combustionChamberPrandtlNumber']**(1/3) # For turbulent flows
        recoveryTemperature = nozzleNearWallTemperature * (1 + recoveryFactor * ((state.chamberGamma - 1) / 2) * nozzleNearWallMachNumber**2)

    turnaround = (xSunkTurnaround2D, rSunkTurnaround2D)

    if geometryOnly:
        return xNozzle, rNozzle, None, turnaround

    flowProperties = {
        'nozzleNearWallTemperature':         nozzleNearWallTemperature,
        'nozzleNearWallPressure':            nozzleNearWallPressure,
        'nozzleNearWallVelocity':            nozzleNearWallVelocity,
        'nozzleNearWallMachNumber':          nozzleNearWallMachNumber,
        'nozzleNearWallRecoveryTemperature': recoveryTemperature,
    }

    return xNozzle, rNozzle, flowProperties, turnaround
