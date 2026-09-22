# -- NOVA (experimental): Keep-Out Envelope -- #

'''

The axisymmetric volume behind the chamber that the cooling jacket has to pack around.

A regeneratively cooled chamber does not end at the injector face. Whatever closes the chamber
sits behind it, and the return volute and its supports have to route outside that volume. NOVA
does not model what fills it, so it is described as a keep-out: an envelope that geometry must
clear, named by three numbers rather than read from a part-specific contour.

The envelope is a quarter ellipse of revolution, swept from an outer shoulder at the chamber
radius inward to a hub where a boss or an igniter would sit:

    x(theta) = axialOffset - depth * sin(theta)
    r(theta) = radius * cos(theta)

with theta running from zero at the shoulder to arccos(hubRadius / radius) at the hub. The
returned arrays run in that order, from the shoulder inward, so index 0 is the outermost point
and index -1 is the innermost.

Nothing here is a model of a real closure. It is a packaging boundary, and its only claim is
that geometry outside it does not intersect it.

----------------------------------------------------------------------
                        Status
----------------------------------------------------------------------

The envelope was drawn for a hybrid nozzle, where the jacket's return turned around on the
converging section and routed behind a chamber closure NOVA did not generate. NOVA generates its
own chamber and jackets it to the injector face, where the return volute sits, so the volume
this described is the injector's. The package drew it and exported it, and nothing checked any
geometry against it: `packingClearance` has no caller outside its own tests.

`experimental/sunkenNozzle.py` is the one geometric consumer. The sunken throat wraps the
converging wall around the envelope, and it imports it from here.

The default placement is wrong. The package placed the shoulder at `keepOutAxialOffset` plus
the upstream end of the regen section, and a null offset turns that sum into NaN, which
`keepOutEnvelope` reads as unset and replaces with zero. Zero is the throat plane, so an
envelope asked for without an offset sat at the throat rather than at the injector face.

----------------------------------------------------------------------
                        Wiring it back in
----------------------------------------------------------------------

A caller reinstating it needs to:

  - restore `keepOutAxialOffset`, `keepOutRadius`, `keepOutDepth` and `keepOutHubRadius` on the
    Nozzle, in `config.py`, the GUI schema and `assets/NOVANozzle.json`,
  - build it in `nozzleVolutes.solveRegenVolutes` with `keepOutEnvelope` and `revolveKeepOut`,
    and place an unset offset at the injector face rather than letting NaN fall through to zero,
  - restore the `KeepOut.txt` export in `exports.py` and the envelope and winder ramp in
    `figures.volutesFigure`,
  - call `packingClearance` on the volutes if the envelope is meant to constrain anything.

All units are mass-base SI:
    - Length [m]
    - Angle  [rad] on the interface, [deg] where a configuration names one

Author: Sean Bowman

'''

from dataclasses import dataclass

import numpy as np

@dataclass
class KeepOutEnvelope:

    '''

    A keep-out envelope and the numbers that define it.

    Attributes:
    -----------
    x : np.ndarray
        Axial coordinate of the envelope profile, shoulder first [m]
    r : np.ndarray
        Radial coordinate of the envelope profile, shoulder first [m]
    radius : float
        Shoulder radius, the widest point of the envelope [m]
    depth : float
        Axial depth from the shoulder plane to the hub [m]
    hubRadius : float
        Radius the envelope is truncated at, where a boss would sit [m]
    axialOffset : float
        Axial station of the shoulder plane [m]

    '''

    x: np.ndarray
    r: np.ndarray
    radius: float
    depth: float
    hubRadius: float
    axialOffset: float

    @property
    def shoulder(self) -> tuple:

        '''Outermost point of the envelope, as (x, r) [m].'''

        return float(self.x[0]), float(self.r[0])

    @property
    def hub(self) -> tuple:

        '''Innermost point of the envelope, as (x, r) [m].'''

        return float(self.x[-1]), float(self.r[-1])

def keepOutEnvelope(chamberRadius: float, axialOffset: float = 0.0, radius: float = None,
                    depth: float = None, hubRadius: float = None,
                    numPoints: int = 100) -> KeepOutEnvelope:

    '''

    Build the keep-out envelope behind the chamber.

    Parameters:
    -----------
    chamberRadius : float
        Radius of the combustion chamber [m]. Sets the defaults for the other dimensions, so an
        envelope can be asked for with nothing but this.
    axialOffset : float
        Axial station of the shoulder plane [m]. Negative values sit upstream of the origin,
        which is the convention the converging section is built in.
    radius : float
        Shoulder radius [m]. Unset takes the chamber radius, which is the envelope of a closure
        meeting the chamber wall without a step.
    depth : float
        Axial depth from the shoulder plane to the hub [m]. Unset takes half the shoulder
        radius, a shallow ellipsoidal closure.
    hubRadius : float
        Radius the envelope is truncated at [m]. Unset takes a quarter of the shoulder radius.
    numPoints : int
        Points in the returned profile.

    A dimension left unset, as either None or NaN, takes its default.

    Returns:
    --------
    KeepOutEnvelope
        The profile and the dimensions behind it.

    Raises:
    -------
    ValueError
        If the dimensions do not describe an envelope: a non-positive chamber radius, a hub at
        or outside the shoulder, or a non-positive depth.

    '''

    if not np.isfinite(chamberRadius) or chamberRadius <= 0:
        raise ValueError(f'chamberRadius must be a positive number, got {chamberRadius}')

    # A configuration leaves a field unset as either None or NaN depending on which reader
    # loaded it, and both mean the same thing here: take the default.
    def specified(value):
        return value is not None and np.isfinite(value)

    axialOffset = float(axialOffset) if specified(axialOffset) else 0.0
    radius      = float(radius)      if specified(radius)      else float(chamberRadius)
    depth       = float(depth)       if specified(depth)       else 0.5  * radius
    hubRadius   = float(hubRadius)   if specified(hubRadius)   else 0.25 * radius

    if radius <= 0:
        raise ValueError(f'Keep-out radius must be positive, got {radius}')
    if depth <= 0:
        raise ValueError(f'Keep-out depth must be positive, got {depth}')
    if not 0 <= hubRadius < radius:
        raise ValueError(f'Keep-out hub radius must lie in [0, {radius}), got {hubRadius}')
    if numPoints < 2:
        raise ValueError(f'numPoints must be at least 2, got {numPoints}')

    # Zero at the shoulder, where the profile is widest and its tangent is axial, and the
    # truncation angle at the hub. Sweeping in this direction puts the shoulder at index 0,
    # which is what the converging section and the volute packing check both read.
    truncationAngle = np.arccos(hubRadius / radius)
    theta = np.linspace(0.0, truncationAngle, numPoints)

    x = axialOffset - depth  * np.sin(theta)
    r = radius      * np.cos(theta)

    return KeepOutEnvelope(x = x, r = r, radius = radius, depth = depth,
                           hubRadius = hubRadius, axialOffset = axialOffset)

def revolveKeepOut(envelope: KeepOutEnvelope, numSlices: int = None) -> tuple:

    '''

    Revolve a keep-out profile into the three-dimensional surface the views draw.

    Parameters:
    -----------
    envelope : KeepOutEnvelope
        The profile to revolve.
    numSlices : int
        Circumferential slices. Defaults to the number of points in the profile, giving a
        square mesh.

    Returns:
    --------
    tuple
        (x, y, z) arrays of shape (numPoints, numSlices) [m], in the cooling-channel convention
        where z is the nozzle axis.

    '''

    numSlices = len(envelope.x) if numSlices is None else int(numSlices)
    angles = np.linspace(0.0, 2 * np.pi, numSlices)

    x = np.tile(envelope.x[:, None], (1, numSlices))
    y = envelope.r[:, None] * np.sin(angles)[None, :]
    z = envelope.r[:, None] * np.cos(angles)[None, :]

    return x, y, z

def packingClearance(envelope: KeepOutEnvelope, x, r) -> np.ndarray:

    '''

    Signed radial clearance of a profile against the keep-out envelope.

    Positive where the profile lies outside the envelope, negative where it intrudes. Points
    axially clear of the envelope report positive infinity, since nothing there can intrude.

    Parameters:
    -----------
    envelope : KeepOutEnvelope
        The envelope to check against.
    x, r : array_like
        Profile to check [m].

    Returns:
    --------
    np.ndarray
        Radial clearance at each point [m].

    '''

    x = np.atleast_1d(np.asarray(x, dtype = float))
    r = np.atleast_1d(np.asarray(r, dtype = float))

    # The profile is swept monotonically in x, so it interpolates directly once put in
    # increasing order.
    order = np.argsort(envelope.x)
    envelopeRadius = np.interp(x, envelope.x[order], envelope.r[order],
                               left = np.nan, right = np.nan)

    clearance = r - envelopeRadius
    clearance[np.isnan(envelopeRadius)] = np.inf

    return clearance
