
# -- NOVA: Cooling Channel Section Properties -- #

'''

What the thermal model needs to know about a channel's cross section, for each family NOVA builds.

A family is the shape of the section and the rule that sizes it. The thermal model does not care
how a section is drawn; it needs the flow area, the wetted perimeter the friction acts on, the
hydraulic diameter both correlations are written in, the perimeter the heat enters the coolant
through, and, where the section has one, the rib between channels treated as a fin. This module
turns the sized quantity at each station into those numbers and holds nothing else: no geometry
module and no thermal module is imported here, so both can import it.

    circle        A circular channel of radius r. The flow area is pi r^2 and the hydraulic
                  diameter sqrt(4 A / pi), which is 2r. Heat enters the coolant through the half
                  of the perimeter that faces the hot wall, pi r, and no fin is modeled.

    rectangular   A rectangle of width w across the circumference and depth d = 2h out from
                  the wall, corners rounded at r_c. The width fills the pitch at the cold wall
                  less the rib, w = 2 pi r_cw / N - t_rib, so the rib at its root is exactly the
                  infill thickness, and the depth is what the sizing solve converges. The flow
                  area is w d - (4 - pi) r_c^2 and the wetted perimeter 2(w + d) - (8 - 2 pi)
                  r_c, and the hydraulic diameter is 4 A / P. Heat enters through the floor,
                  w - 2 r_c plus half of each floor corner, and through the two side walls as the
                  faces of the ribs, each a fin of height d - 2 r_c plus half of each of its
                  corners and thickness t_rib.

    helical       The same rounded rectangle, run as a helix of N starts at a constant angle phi
                  to the meridian: a loxodrome on the cold wall, d(theta)/ds_m = tan(phi)/r_cw.
                  The passes then sit 2 pi r_cw cos(phi) / N apart measured across the channel.
                  The width is what the sizing solve converges, the depth is the configured
                  aspect ratio times it, and the rib is what is left of the pass spacing, so it
                  varies along the nozzle with the radius. It may not fall below the infill
                  thickness, which caps the width, and the depth may not pass maxChannelDepth.

The perimeter of a rounded rectangle is split so the floor, the two sides and the roof each carry
their straight run and half of each corner they touch; the four parts sum to the perimeter. The
roof is the closeout, and the fin model's adiabatic tip is what leaves it out of the heated area.

The cold-wall radius a width is taken at is the hot wall offset by the wall thickness along its
normal, which is where the ribs stand.

----------------------------------------------------------------------
                        Fin efficiency
----------------------------------------------------------------------

A rib between two channels conducts heat from the hot wall into the coolant through both of its
faces. It is treated as a straight fin of uniform thickness t cooled on both faces at the coolant
coefficient h, with an adiabatic tip:

    eta = tanh(m H) / (m H),   m = sqrt(2 h / (k t))

with H the fin height and k the wall conductivity (Incropera, Fundamentals of Heat and Mass
Transfer, straight fin of uniform cross section). The coolant-side area of a station is then the
heated perimeter plus 2 eta H, times the station length. A section with no fin has H = 0 and the
area is the heated perimeter alone, exactly.

All units are mass base SI:
    - Length [m]
    - Area   [m^2]

Author: Sean Bowman

'''

from dataclasses import dataclass

import numpy as np

# The families the package builds, and how a figure names them.
SECTIONFAMILIES = ('circle', 'rectangular', 'helical')
SECTIONLABELS   = {'circle': 'Circular', 'rectangular': 'Rectangular', 'helical': 'Helical'}

# The families drawn as a rounded rectangle on the wall normal
RECTANGULARFAMILIES = ('rectangular', 'helical')

@dataclass(frozen = True)
class SectionProperties:

    '''

    One family's section at every station, as the thermal model reads it.

    Every attribute is an array with one entry per station, or a scalar broadcast against one.

    Attributes:
    -----------
    halfExtent : np.ndarray
        Radial half-extent of the section, the quantity the sizing solve converges [m]. A
        circle's radius.
    width, depth : np.ndarray
        Circumferential and radial extent [m].
    cornerRadius : np.ndarray
        Corner radius of a polygonal section, zero for a sharp corner or a circle [m].
    flowArea : np.ndarray
        Cross-sectional flow area [m^2].
    wettedPerimeter : np.ndarray
        Perimeter the friction acts on [m].
    hydraulicDiameter : np.ndarray
        Diameter both coolant correlations are written in [m].
    heatedPerimeter : np.ndarray
        Perimeter the heat enters the coolant through directly, before any fin [m].
    finHeight, finThickness : np.ndarray
        Rib treated as a fin, zero where there is none [m].

    '''

    halfExtent:        np.ndarray
    width:             np.ndarray
    depth:             np.ndarray
    cornerRadius:      np.ndarray
    flowArea:          np.ndarray
    wettedPerimeter:   np.ndarray
    hydraulicDiameter: np.ndarray
    heatedPerimeter:   np.ndarray
    finHeight:         np.ndarray
    finThickness:      np.ndarray

def rectangularWidth(coldWallRadius, nChannel: int, infillThickness: float):

    '''

    Width of a rectangular channel that fills its pitch at the cold wall less the rib [m].

        w = 2 pi r_cw / N - t_rib

    '''

    return 2*np.pi*np.asarray(coldWallRadius, dtype = float)/nChannel - infillThickness

def helicalSpacing(coldWallRadius, nChannel: int, helixAngle: float):

    '''

    Distance between neighboring helical passes, measured across the channel [m].

        s = 2 pi r_cw cos(phi) / N

    with phi the helix angle from the meridian [deg on the interface].

    '''

    return 2*np.pi*np.asarray(coldWallRadius, dtype = float)*np.cos(np.deg2rad(helixAngle))/nChannel

def loxodromeWrap(meridionalLength, coldWallRadius, helixAngle: float, active = None) -> np.ndarray:

    '''

    Azimuth of a curve that crosses every meridian of the cold wall at the helix angle [rad].

        d(theta)/d(s_m) = tan(phi) / r_cw

    integrated along the meridian with the trapezoid rule from zero at the first station. Where
    `active` is false the rate is zero, which holds the azimuth through a stretch the channel
    runs straight across, such as a volute interface.

    Parameters:
    -----------
    meridionalLength : array_like
        Arc length along the cold-wall meridian at each station [m].
    coldWallRadius : array_like
        Cold-wall radius at each station [m].
    helixAngle : float
        Angle between the channel and the meridian [deg].
    active : array_like of bool, optional
        Stations the helix applies at.

    Returns:
    --------
    np.ndarray
        Wrap angle at each station [rad].

    '''

    length = np.asarray(meridionalLength, dtype = float)
    rate   = np.tan(np.deg2rad(helixAngle))/np.asarray(coldWallRadius, dtype = float)
    if active is not None:
        rate = np.where(np.asarray(active, dtype = bool), rate, 0.0)

    return np.concatenate([[0.0], np.cumsum(0.5*(rate[1:] + rate[:-1])*np.diff(length))])

def roundedRectangle(width, depth, cornerRadius) -> tuple:

    '''

    Flow area and perimeter of a rectangle with rounded corners.

        A = w d - (4 - pi) r_c^2
        P = 2 (w + d) - (8 - 2 pi) r_c

    The corner radius is clamped to half the smaller side, where the section becomes a stadium.

    Returns:
    --------
    tuple
        (clamped corner radius [m], area [m^2], perimeter [m])

    '''

    width, depth = np.asarray(width, dtype = float), np.asarray(depth, dtype = float)
    corner       = np.minimum(np.asarray(cornerRadius, dtype = float), 0.5*np.minimum(width, depth))

    return corner, width*depth - (4 - np.pi)*corner**2, 2*(width + depth) - (8 - 2*np.pi)*corner

def sectionProperties(family: str, halfExtent, width = None, cornerRadius = 0.0,
                      ribThickness = 0.0) -> SectionProperties:

    '''

    The section of one family at every station.

    Parameters:
    -----------
    family : str
        One of SECTIONFAMILIES.
    halfExtent : array_like
        Radial half-extent at each station [m]; a circle's radius, half a rectangle's depth.
    width : array_like
        Width across the channel at each station [m]. Required for a rectangle or a helix.
    cornerRadius : float
        Corner radius of a rectangle or a helix [m].
    ribThickness : array_like
        Rib between neighboring channels, at its root [m]. Used by a rectangle or a helix.

    Returns:
    --------
    SectionProperties

    Raises:
    -------
    ValueError
        For a family the package does not build.

    '''

    halfExtent = np.asarray(halfExtent, dtype = float)

    if family == 'circle':

        # Written in the order the circular model has always evaluated them, so a run through
        # this module reproduces one from before it to the bit.
        flowArea          = np.pi*halfExtent**2
        wettedPerimeter   = np.pi*2*halfExtent
        hydraulicDiameter = np.sqrt(4 * flowArea / np.pi)
        zeros             = np.zeros_like(halfExtent)

        return SectionProperties(
            halfExtent        = halfExtent,
            width             = 2*halfExtent,
            depth             = 2*halfExtent,
            cornerRadius      = zeros,
            flowArea          = flowArea,
            wettedPerimeter   = wettedPerimeter,
            hydraulicDiameter = hydraulicDiameter,
            heatedPerimeter   = np.pi*halfExtent,
            finHeight         = zeros,
            finThickness      = zeros)

    if family in RECTANGULARFAMILIES:

        if width is None:
            raise ValueError(f'A {family} section needs its width at every station.')

        width  = np.asarray(width, dtype = float)
        depth  = 2*halfExtent
        corner, flowArea, wettedPerimeter = roundedRectangle(width, depth, cornerRadius)

        # Floor, sides and roof each take their straight run and half of each corner they touch
        cornerShare = 0.5*np.pi*corner

        return SectionProperties(
            halfExtent        = halfExtent,
            width             = width,
            depth             = depth,
            cornerRadius      = corner,
            flowArea          = flowArea,
            wettedPerimeter   = wettedPerimeter,
            hydraulicDiameter = 4*flowArea/wettedPerimeter,
            heatedPerimeter   = width - 2*corner + cornerShare,
            finHeight         = depth - 2*corner + cornerShare,
            finThickness      = np.broadcast_to(np.asarray(ribThickness, dtype = float),
                                                halfExtent.shape).copy())

    raise ValueError(f"Unknown channel family '{family}'; the package builds {SECTIONFAMILIES}.")

def maxHalfExtent(family: str, width, maxAspectRatio: float, maxDepth: float = None):

    '''

    Largest radial half-extent a rectangle may be sized to at each station [m].

    The depth is held to maxAspectRatio times the width, and to maxDepth where one is given. A
    helix passes the widest channel its pass spacing allows, the spacing less the minimum rib,
    as the width and its fixed aspect ratio as the ratio, so the same product bounds it.

    '''

    if family in RECTANGULARFAMILIES:
        depthLimit = maxAspectRatio*np.asarray(width, dtype = float)
        if maxDepth is not None and np.isfinite(maxDepth):
            depthLimit = np.minimum(depthLimit, maxDepth)
        return 0.5*depthLimit

    raise ValueError(f"No width-based half-extent limit for channel family '{family}'.")

def equivalentDiameter(family: str, halfExtent, width = None, cornerRadius = 0.0) -> np.ndarray:

    '''

    The diameter a round port matching this section would have [m].

    What a volute interface is sized from. A circle returns its own diameter; a rectangle
    returns the diameter of the circle of the same flow area.

    '''

    if family == 'circle':
        return np.asarray(halfExtent, dtype = float)*2

    if family in RECTANGULARFAMILIES:
        _, flowArea, _ = roundedRectangle(width, 2*np.asarray(halfExtent, dtype = float), cornerRadius)
        return np.sqrt(4*flowArea/np.pi)

    raise ValueError(f"Unknown channel family '{family}'; the package builds {SECTIONFAMILIES}.")

def throatChannelCount(family: str, throatRadius: float, hotWallThickness: float,
                       infillThickness: float, minHalfExtent: float, helixAngle: float = 0.0) -> int:

    '''

    The most channels whose section at the throat is no smaller than the process minimum.

    A circle of radius r packs tangent to its neighbors and to the wall offset by the hot wall
    less the infill, R = r_t + t - t_inf, when sin(pi / N) = (r + t_inf/2) / (R + r + t_inf/2).
    Solving at r = minHalfExtent and rounding down gives the channel count. A rectangle's width
    is fixed by the count, so it is the count at which the throat width is minChannelWidth:
    N = floor(2 pi (r_t + t) / (w_min + t_inf)). A helix's passes are closer by cos(phi), so its
    count of starts is N = floor(2 pi (r_t + t) cos(phi) / (w_min + t_inf)).

    Parameters:
    -----------
    family : str
        One of SECTIONFAMILIES.
    throatRadius : float
        Hot wall radius at the throat [m].
    hotWallThickness, infillThickness : float
        Wall between coolant and exhaust, and material left between channels [m].
    minHalfExtent : float
        Smallest half-extent the process can build [m] for a circle; the smallest width for a
        rectangle.

    Returns:
    --------
    int

    '''

    if family == 'circle':
        reach = minHalfExtent + infillThickness/2
        return int(np.pi / (np.arcsin(reach / (reach + throatRadius + hotWallThickness - infillThickness))))

    if family == 'rectangular':
        return int(np.floor(2*np.pi*(throatRadius + hotWallThickness) / (minHalfExtent + infillThickness)))

    if family == 'helical':
        return int(np.floor(2*np.pi*(throatRadius + hotWallThickness)*np.cos(np.deg2rad(helixAngle))
                            / (minHalfExtent + infillThickness)))

    raise ValueError(f"Unknown channel family '{family}'; the package builds {SECTIONFAMILIES}.")

def finEfficiency(coolantCoefficient: float, wallConductivity: float, finThickness: float,
                  finHeight: float) -> float:

    '''

    Efficiency of a straight rib cooled on both faces with an adiabatic tip [-].

        eta = tanh(m H) / (m H),   m = sqrt(2 h / (k t))

    Parameters:
    -----------
    coolantCoefficient : float
        Coolant-side convective coefficient on the fin faces [W/m^2 K].
    wallConductivity : float
        Rib conductivity [W/m K].
    finThickness : float
        Rib thickness [m].
    finHeight : float
        Rib height from root to tip [m].

    Returns:
    --------
    float
        Fin efficiency, one for a fin of no height.

    '''

    if finHeight <= 0:
        return 1.0

    mH = np.sqrt(2 * coolantCoefficient / (wallConductivity * finThickness)) * finHeight

    return float(np.tanh(mH) / mH) if mH > 0 else 1.0
