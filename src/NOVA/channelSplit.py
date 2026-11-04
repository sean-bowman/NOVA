# -- NOVA: Bifurcated Cooling Channels -- #

'''

A jacket whose channels split in two partway along the nozzle.

A bell's circumference grows several times from the throat to the exit, and a fixed count of
channels sized for the throat leaves each channel a wide pitch downstream: either the channel
grows with it, which slows the coolant and loses the heat transfer, or it stays small and leans
over to fill the pitch, which lengthens it. Doubling the count partway along keeps the channels
near the size the heat flux wants. Wadel's bifurcated designs for NASA did this in a single
transition, and the SSME's main chamber and the RL10's tubes bifurcate the same way.

**The section through a split.** Each parent channel forks into two daughters over a transition
whose length is a multiple of the parent's diameter. Through it the passage is the union of two
equal circles whose centers move apart along the circumference from coincident to the daughter
pitch, on a cosine blend so both ends are smooth. The union's area, wetted perimeter and hydraulic
diameter are closed form:

    A_lens = 2 r^2 acos(d / 2r) - (d / 2) sqrt(4 r^2 - d^2)
    A      = 2 pi r^2 - A_lens
    P      = 4 r (pi - acos(d / 2r))

for a center separation d up to 2r, and twice one circle beyond. At d = 0 they are one circle of
radius r; at d = 2r they are two, and the mass flux and hydraulic diameter of a pair carrying one
parent's flow equal those of two daughters each carrying half. So the jacket is marched per parent
channel straight through the split: the flow per passage, the hot wall share and the count stay
the parent's, and only the section changes. A rectangular channel splits by a rib that grows from
zero thickness to the full rib at the end of the transition.

**The pitch.** The circumferential room a pair occupies is the parent pitch less the separation
already spent, so the largest a daughter can be without leaning is

    r_max = (2 pi R / N - d - t_rib) / 2

which runs continuously from the parent's limit to the daughter's. A daughter smaller than that
leans, as an undivided channel does, by the angle whose cosine is (2r + t_rib) / (2 pi R / N - d).

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Geometry, verified.** The union's area and perimeter are closed form and are held in
tests/testChannelSplit.py against the shoelace area and the length of the outline polygon the 3D
geometry is built from, and against the limits of one circle and two. **The heat transfer through
a split is unvalidated**: the coolant correlations are applied to the union's hydraulic diameter as
to any duct, and no measurement of a bifurcation's local heat transfer is available here. Wadel's
bifurcated designs are the comparison the transition is checked against, as a trend.

All units are mass base SI:
    - Length [m]
    - Area [m^2]

Author: Sean Bowman

'''

import numpy as np

from .errors import InvalidInputError

__all__ = ['splitBlend', 'circleUnion', 'circleUnionOutline', 'splitSeparation',
           'splitPitchShare', 'daughterCenterlines']

def splitBlend(meridionalPosition, startPosition: float, length: float) -> np.ndarray:

    '''

    How far through the split each station is: zero before it, one after, a cosine between.

    Parameters:
    -----------
    meridionalPosition : array_like
        Distance along the wall of each station, measured the same way as the start [m].
    startPosition : float
        Where the transition begins [m].
    length : float
        Length of the transition along the wall [m].

    Returns:
    --------
    numpy.ndarray
        The blend, beta, at each station [-].

    '''

    position = np.asarray(meridionalPosition, dtype = float)
    if length <= 0.0:
        raise InvalidInputError(
            message = 'A channel split needs a transition of some length to fork over.',
            parameterName = 'channelSplitLength', value = length, validRange = 'greater than zero')
    progress = np.clip((position - startPosition) / length, 0.0, 1.0)
    return 0.5 * (1.0 - np.cos(np.pi * progress))

def splitSeparation(blend, wallRadius, nChannel: int) -> np.ndarray:

    '''

    Circumferential distance between the two daughters' centers [m].

    The daughters end half a parent pitch apart, so the separation is the blend times pi R / N.

    Parameters:
    -----------
    blend : array_like
        Progress through the split [-].
    wallRadius : array_like
        Radius the pitch is measured at [m].
    nChannel : int
        Parent channel count.

    '''

    return np.asarray(blend, dtype = float) * np.pi * np.asarray(wallRadius, dtype = float) / nChannel

def splitPitchShare(wallRadius, nChannel: int, separation) -> np.ndarray:

    '''

    Circumferential room one daughter pair has for its two channels and the rib beside them [m].

    The parent pitch less the separation already spent: the parent pitch at the start of the
    split, the daughter pitch at its end.

    '''

    return 2.0 * np.pi * np.asarray(wallRadius, dtype = float) / nChannel - np.asarray(separation, dtype = float)

def circleUnion(radius, separation) -> dict:

    '''

    Area and perimeters of the union of two equal circles.

    Parameters:
    -----------
    radius : array_like
        Circle radius [m].
    separation : array_like
        Center separation, measured across the channel's own section [m].

    Returns:
    --------
    dict
        'flowArea' [m^2], 'wettedPerimeter' [m], 'heatedPerimeter' [m], the half of the outline
        facing the wall, and 'hydraulicDiameter' [m].

    '''

    radius = np.asarray(radius, dtype = float)
    separation = np.minimum(np.asarray(separation, dtype = float), 2.0 * radius)
    halfAngle = np.arccos(np.clip(separation / (2.0 * radius), 0.0, 1.0))
    lens = (2.0 * radius**2 * halfAngle
            - 0.5 * separation * np.sqrt(np.maximum(4.0 * radius**2 - separation**2, 0.0)))
    flowArea = 2.0 * np.pi * radius**2 - lens
    wettedPerimeter = 4.0 * radius * (np.pi - halfAngle)
    return {'flowArea': flowArea, 'wettedPerimeter': wettedPerimeter,
            'heatedPerimeter': 0.5 * wettedPerimeter,
            'hydraulicDiameter': 4.0 * flowArea / wettedPerimeter}

def daughterCenterlines(x, y, z, blend, nChannel: int) -> tuple:

    '''

    The two daughters' centerlines, forked from the parent's about the nozzle axis.

    Each daughter is the parent's centerline turned about the axis by plus or minus a quarter of
    the parent's angular pitch times the blend, so the two start on the parent and end half a
    parent pitch apart, the daughter pitch. The turn is an angle, so it is the same at every
    radius: the fork follows the wall as the wall grows. With the cosine blend the turn has zero
    slope at both ends of the transition, so each daughter leaves the parent and joins its own
    run tangentially.

    Parameters:
    -----------
    x, y, z : array_like
        Parent centerline, x along the nozzle axis [m].
    blend : array_like
        Progress through the split at each centerline point [-].
    nChannel : int
        Parent channel count.

    Returns:
    --------
    tuple
        ((x, y, z) of the first daughter, (x, y, z) of the second).

    '''

    y, z = np.asarray(y, dtype = float), np.asarray(z, dtype = float)
    turn = np.asarray(blend, dtype = float) * np.pi / (2.0 * nChannel)
    daughters = []
    for sign in (1.0, -1.0):
        cosine, sine = np.cos(sign * turn), np.sin(sign * turn)
        daughters.append((np.asarray(x, dtype = float).copy(), y * cosine - z * sine, y * sine + z * cosine))
    return tuple(daughters)

def circleUnionOutline(radius: float, separation: float, numPoints: int) -> list:

    '''

    The outline of two equal circles' union, as one closed loop or two.

    The centers sit at (-d/2, 0) and (d/2, 0). While the circles overlap the outline is one loop:
    the right circle's arc outside the left, then the left circle's outside the right, each from
    one intersection to the other. Once they no longer overlap it is two circles.

    Parameters:
    -----------
    radius, separation : float
        Circle radius and center separation [m].
    numPoints : int
        Points on the whole outline.

    Returns:
    --------
    list
        One or two (n, 2) arrays, each a closed loop counterclockwise, not repeating its first
        point.

    '''

    half = 0.5 * separation
    if separation >= 2.0 * radius:
        count = max(numPoints // 2, 8)
        angles = np.linspace(0.0, 2.0 * np.pi, count, endpoint = False)
        circle = np.column_stack([radius * np.cos(angles), radius * np.sin(angles)])
        return [circle + [-half, 0.0], circle + [half, 0.0]]

    halfAngle = float(np.arccos(separation / (2.0 * radius)))
    # The right circle runs from the lower intersection through its rightmost point to the upper;
    # the left from the upper through its leftmost point to the lower
    span = 2.0 * (np.pi - halfAngle)
    count = max(numPoints // 2, 4)
    right = np.linspace(-(np.pi - halfAngle), np.pi - halfAngle, count, endpoint = False)
    left = np.linspace(halfAngle, halfAngle + span, count, endpoint = False)
    loop = np.vstack([np.column_stack([half + radius * np.cos(right), radius * np.sin(right)]),
                      np.column_stack([-half + radius * np.cos(left), radius * np.sin(left)])])
    return [loop]
