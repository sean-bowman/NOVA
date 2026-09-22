
# -- NOVA: Cooling Channel Section Properties -- #

'''

What the thermal model needs to know about a channel's cross section, for each family NOVA builds.

A family is the shape of the section and the rule that sizes it. The thermal model does not care
how a section is drawn; it needs the flow area, the wetted perimeter the friction acts on, the
hydraulic diameter both correlations are written in, the perimeter the heat enters the coolant
through, and, where the section has one, the rib between channels treated as a fin. This module
turns the sized quantity at each station into those numbers and holds nothing else: no geometry
module and no thermal module is imported here, so both can import it.

    circle   A circular channel of radius r. The flow area is pi r^2 and the hydraulic diameter
             sqrt(4 A / pi), which is 2r. Heat enters the coolant through the half of the
             perimeter that faces the hot wall, pi r, and no fin is modeled.

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
SECTIONFAMILIES = ('circle',)
SECTIONLABELS   = {'circle': 'Circular'}

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

def sectionProperties(family: str, halfExtent) -> SectionProperties:

    '''

    The section of one family at every station.

    Parameters:
    -----------
    family : str
        One of SECTIONFAMILIES.
    halfExtent : array_like
        Radial half-extent at each station [m]; a circle's radius.

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

    raise ValueError(f"Unknown channel family '{family}'; the package builds {SECTIONFAMILIES}.")

def equivalentDiameter(family: str, halfExtent) -> np.ndarray:

    '''

    The diameter a round port matching this section would have [m].

    What a volute interface is sized from. A circle returns its own diameter.

    '''

    if family == 'circle':
        return np.asarray(halfExtent, dtype = float)*2

    raise ValueError(f"Unknown channel family '{family}'; the package builds {SECTIONFAMILIES}.")

def throatChannelCount(family: str, throatRadius: float, hotWallThickness: float,
                       infillThickness: float, minHalfExtent: float) -> int:

    '''

    The most channels whose section at the throat is no smaller than the process minimum.

    A circle of radius r packs tangent to its neighbors and to the wall offset by the hot wall
    less the infill, R = r_t + t - t_inf, when sin(pi / N) = (r + t_inf/2) / (R + r + t_inf/2).
    Solving at r = minHalfExtent and rounding down gives the channel count.

    Parameters:
    -----------
    family : str
        One of SECTIONFAMILIES.
    throatRadius : float
        Hot wall radius at the throat [m].
    hotWallThickness, infillThickness : float
        Wall between coolant and exhaust, and material left between channels [m].
    minHalfExtent : float
        Smallest half-extent the process can build [m].

    Returns:
    --------
    int

    '''

    if family == 'circle':
        reach = minHalfExtent + infillThickness/2
        return int(np.pi / (np.arcsin(reach / (reach + throatRadius + hotWallThickness - infillThickness))))

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
