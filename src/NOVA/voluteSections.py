
# -- NOVA: Volute Cross Section Properties -- #

'''

What a volute cross section measures, and how the scroll grows it around the wrap.

This module holds the numbers. `Volute.py` holds the drawing: it reads a section area from here,
turns it into a profile in the YZ plane, and sweeps it. Keeping the two apart means a section
family is described once rather than once per generator, which is where the families had drifted.

----------------------------------------------------------------------
                        The families
----------------------------------------------------------------------

**A circle** of radius `r` has area `pi r^2` and hydraulic diameter `2 r`. Its characteristic
length is its radius.

**A squircle** is a square of side `2 L` with quarter-round corners of radius `L`, so its area is
`(1 + 0.75 pi) L^2` and its perimeter `(2 + 1.5 pi) L`. Its hydraulic diameter `4 A / P` is
therefore `2 L`, the same as a circle of radius `L`, and the characteristic length a hydraulic
diameter implies is `D (2 + 1.5 pi)/(4 + 3 pi)`, which is `D / 2`. The two forms are kept apart in
the code because the shape factors are what a reader needs to see.

----------------------------------------------------------------------
                        The area law
----------------------------------------------------------------------

The scroll area is linear in wrap angle, from the interface area at the tongue to the expanded
area at the throat over one full turn.

A scroll that sheds or gathers the same flow through every one of `N` ports and holds a constant
velocity needs `A(theta) = A_throat theta / 360`, so its tongue area is `A_throat / N`. That is
the law in Huzel and Huang eq. 6-69, and it is what `constantVelocityTongueArea` returns. Passing
`numOrifices` alongside an expanded area asks for exactly that distribution. Passing an interface
area directly does not, and how far the result departs from the law is
`scrollVelocityRatio`: the ratio of the velocity at the throat to the velocity at the tongue,
which a constant velocity scroll holds at one.

Author: Sean Bowman

'''

import numpy as np

# The cross section families a scroll can be built from. An egg section is kept in
# experimental/eggVolute.py.
VOLUTESECTIONS = ('circle', 'squarc')

# How the scroll closes on itself. A ring wraps a full turn and is fed from both directions at
# once; a cutwater stops short of a full turn and puts a wall between its two ends.
SCROLLTYPES = ('ring', 'cutwater')

# The overhang supports a printed scroll can carry inside it. 'thick' braces the duct with a
# rectilinear wall and two filleted transitions, 'thin' with a sheet and one. Both are drawn from a
# circular wall, so a squircle section takes neither.
VOLUTEPRINTABILITY = ('off', 'thick', 'thin')

# A squircle of characteristic length L encloses (1 + 0.75 pi) L^2 behind a perimeter of
# (2 + 1.5 pi) L. The expressions below are written in those factors rather than in these names,
# because the generators they replace were, and a rewritten sum rounds differently.

def sectionArea(family: str, hydraulicDiameter = None, characteristicLength = None):

    '''

    Area of one cross section [m^2], from whichever measure of its size is known.

    Parameters:
    -----------
    family : str
        One of `VOLUTESECTIONS`.
    hydraulicDiameter : float or np.ndarray, optional
        Hydraulic diameter of the section [m].
    characteristicLength : float or np.ndarray, optional
        Radius of a circle, or the quarter-round corner radius of a squircle [m].

    Returns:
    --------
    float or np.ndarray
        Cross-sectional area [m^2].

    Raises:
    -------
    ValueError
        On an unrecognized family, or when neither size is given.

    '''

    checkFamily(family)

    if hydraulicDiameter is not None:
        if family == 'circle':
            return np.pi * (hydraulicDiameter / 2)**2
        characteristicLength = characteristicLengthFromDiameter(family, hydraulicDiameter)

    if characteristicLength is None:
        raise ValueError('sectionArea needs a hydraulic diameter or a characteristic length.')

    if family == 'circle':
        return np.pi * characteristicLength**2

    return (characteristicLength**2)*(1 + 0.75*np.pi)

def sectionHydraulicDiameter(family: str, area):

    '''

    Hydraulic diameter of one cross section [m], from its area.

    Both families reduce to `4 A / P`. A circle returns `2 sqrt(A / pi)`, and a squircle returns
    the same expression in its own shape factors so that the perimeter it divides by is visible.

    '''

    checkFamily(family)

    if family == 'circle':
        return 2 * np.sqrt(area / np.pi)

    length = characteristicLengthFromArea(family, area)

    return 4*area / ((1.5*np.pi*length) + (2*length))

def characteristicLengthFromArea(family: str, area):

    '''Characteristic length of a section carrying `area` [m].'''

    checkFamily(family)

    if family == 'circle':
        return np.sqrt(area / np.pi)

    return np.sqrt(area/(1 + 0.75*np.pi))

def characteristicLengthFromDiameter(family: str, hydraulicDiameter):

    '''Characteristic length of a section of hydraulic diameter `hydraulicDiameter` [m].'''

    checkFamily(family)

    if family == 'circle':
        return hydraulicDiameter / 2

    return hydraulicDiameter*(2 + 1.5*np.pi)/(4 + 3*np.pi)

def checkFamily(family: str) -> None:

    '''Reject a cross section family the module does not describe.'''

    if family not in VOLUTESECTIONS:
        parked = (' An egg cross section is kept in experimental/eggVolute.py.'
                  if family == 'egg' else '')
        raise ValueError(f'crossSectionType must be one of {", ".join(VOLUTESECTIONS)}, '
                         f'not {family!r}.{parked}')

def resolveScrollAreas(family: str, interfaceArea = None, interfaceHydraulicDiameter = None,
                       interfaceCharacteristicLength = None, expandedArea = None,
                       expandedHydraulicDiameter = None, expandedCharacteristicLength = None,
                       numOrifices = None) -> dict:

    '''

    Work out the two end areas of a scroll from whatever the caller specified.

    Either end can be given as an area, a hydraulic diameter or a characteristic length, and an
    orifice count stands in for one of them: `numOrifices` with an expanded end divides it, and
    with an interface end multiplies it.

    Parameters:
    -----------
    family : str
        One of `VOLUTESECTIONS`.
    interfaceArea, interfaceHydraulicDiameter, interfaceCharacteristicLength : float, optional
        The tongue end, where the scroll meets one port.
    expandedArea, expandedHydraulicDiameter, expandedCharacteristicLength : float, optional
        The throat end, where the scroll carries the whole flow.
    numOrifices : float, optional
        Ports the scroll feeds or gathers, standing in for whichever end is absent.

    Returns:
    --------
    dict
        `interfaceArea`, `expandedArea`, `interfaceHydraulicDiameter`,
        `expandedHydraulicDiameter` and `numOrifices`.

    Raises:
    -------
    ValueError
        When the specification does not determine both ends, or when the interface end is not
        smaller than the expanded end.

    '''

    checkFamily(family)

    def areaOf(area, diameter, length):
        if area is not None:
            return area
        if diameter is not None:
            return sectionArea(family, hydraulicDiameter = diameter)
        if length is not None:
            return sectionArea(family, characteristicLength = length)
        return None

    interface = areaOf(interfaceArea, interfaceHydraulicDiameter, interfaceCharacteristicLength)
    expanded = areaOf(expandedArea, expandedHydraulicDiameter, expandedCharacteristicLength)

    if interface is None and expanded is not None and numOrifices is not None:
        interface = expanded / numOrifices
    elif expanded is None and interface is not None and numOrifices is not None:
        expanded = interface * numOrifices

    if interface is None or expanded is None:
        raise ValueError('A scroll needs both of its end areas. Give an area, a hydraulic '
                         'diameter or a characteristic length at each end, or one end and an '
                         'orifice count.')

    if not np.all(np.asarray(expanded) > np.asarray(interface)):
        raise ValueError(f'The expanded area {expanded} must exceed the interface area '
                         f'{interface}: a scroll grows toward the end that carries the flow.')

    return {'interfaceArea': interface,
            'expandedArea': expanded,
            'interfaceHydraulicDiameter': (interfaceHydraulicDiameter
                                           if interfaceHydraulicDiameter is not None
                                           else sectionHydraulicDiameter(family, interface)),
            'expandedHydraulicDiameter': (expandedHydraulicDiameter
                                          if expandedHydraulicDiameter is not None
                                          else sectionHydraulicDiameter(family, expanded)),
            'numOrifices': expanded / interface if numOrifices is None else numOrifices}

def checkScrollType(scrollType: str) -> None:

    '''Reject a scroll topology the module does not describe.'''

    if scrollType not in SCROLLTYPES:
        raise ValueError(f'voluteScrollType must be one of {", ".join(SCROLLTYPES)}, '
                         f'not {scrollType!r}.')

def portsPerScroll(numPorts: float, scrollType: str) -> float:

    '''

    Ports one continuous run of the scroll feeds or gathers [-].

    A cutwater scroll passes every port once, so its run carries all of them. A ring is fed at one
    point and reaches every port from both directions, so each half run carries half of them.

    '''

    checkScrollType(scrollType)

    return numPorts if scrollType == 'cutwater' else numPorts/2.0

def scrollAreaDistribution(interfaceArea: float, expandedArea: float, sections: int,
                           scrollType: str = 'cutwater'):

    '''

    Section areas around the scroll [m^2].

    Both laws are linear in wrap angle, because the flow a station carries is linear in the ports
    it has passed. They differ in where the tongue sits.

    A **cutwater** scroll runs from the tongue at the start of the wrap to the throat at the end,
    with a wall between the two, so the area rises once across a full turn.

    A **ring** is fed at one point and splits, so the throat is at both ends of the wrap and the
    tongue sits half a turn away. The area falls to the tongue and rises back, which also makes
    the two ends of the sweep the same size and lets the ring close on itself without a step.

    Parameters:
    -----------
    interfaceArea : float
        Area at the tongue, where the scroll meets one port [m^2].
    expandedArea : float
        Area at the throat, where the scroll carries the whole flow [m^2].
    sections : int
        Cross sections swept around the scroll.
    scrollType : str
        One of `SCROLLTYPES`.

    Returns:
    --------
    np.ndarray
        Section area at each station [m^2].

    '''

    checkScrollType(scrollType)

    if scrollType == 'cutwater':
        return np.linspace(interfaceArea, expandedArea, sections)

    fraction = np.linspace(0.0, 1.0, sections)

    return interfaceArea + (expandedArea - interfaceArea)*np.abs(2.0*fraction - 1.0)

def tongueGapAngle(scrollRadius: float, wallThickness, sections: int) -> float:

    '''

    Angle a cutwater's tongue wall subtends at the scroll radius [rad].

    The sweep stops short of a full turn by this much, so the tongue section and the throat
    section end up in different meridional planes with room for a wall between them instead of one
    nested inside the other. The gap is the angle the wall itself occupies, floored at one section
    step so the sweep always resolves it.

    '''

    step = 2.0*np.pi/(sections - 1) if sections > 1 else 0.0

    if wallThickness is None:
        return step

    thickness = float(np.max(np.atleast_1d(np.asarray(wallThickness, dtype = float))))

    return max(2.0*np.arcsin(min(thickness/(2.0*scrollRadius), 1.0)), step)

def constantVelocityTongueArea(expandedArea: float, numOrifices: float,
                               scrollType: str = 'cutwater'):

    '''

    Tongue area that holds the scroll velocity constant [m^2].

    A scroll run shedding equal flow through `n` ports carries `theta/360` of its throat flow at
    wrap angle `theta`, so constant velocity needs `A_throat/n` at the tongue (Huzel and Huang,
    Design of Liquid Propellant Rocket Engines, eq. 6-69). A ring splits its ports between two
    runs, so `n` is half the port count.

    '''

    return expandedArea / portsPerScroll(numOrifices, scrollType)

def constantVelocityThroatArea(interfaceArea: float, numOrifices: float,
                               scrollType: str = 'cutwater'):

    '''

    Throat area that holds the scroll velocity constant, given the tongue [m^2].

    The inverse of `constantVelocityTongueArea`, and the one a nozzle uses: the tongue is fixed by
    the port it has to meet, so the throat is what the law is free to set.

    '''

    return interfaceArea * portsPerScroll(numOrifices, scrollType)

def scrollVelocityRatio(interfaceArea: float, expandedArea: float, numOrifices: float,
                        scrollType: str = 'cutwater'):

    '''

    Throat velocity over tongue velocity for a scroll built on these areas [-].

    One means the velocity is constant around the wrap, which is what the constant velocity law
    delivers. Above one the scroll decelerates toward the tongue, turning velocity head into
    static pressure and biasing the ports it feeds last.

    '''

    return portsPerScroll(numOrifices, scrollType)*interfaceArea/expandedArea

def anchorOffset(anchor: str, halfExtent):

    '''

    Where a section sits relative to the scroll radius, as a radial and an axial offset [m].

    The anchor names the point of the section that lands on the scroll radius and the axial
    offset: `c` the centre, `o` the outermost point, `i` the innermost, `n` and `s` the extreme
    axial points, and the four diagonals the corresponding corners at `halfExtent/sqrt(2)`.
    Anything else centres the section, which is what the generator has always done.

    Parameters:
    -----------
    anchor : str
        One or two letters from `c`, `n`, `s`, `i`, `o`, `ni`, `si`, `no`, `so`.
    halfExtent : float
        Half the section's extent, its radius for a circle [m].

    Returns:
    --------
    tuple
        Radial offset and axial offset [m].

    '''

    diagonal = halfExtent/np.sqrt(2)

    offsets = {'n':  (0.0, -halfExtent),
               's':  (0.0, +halfExtent),
               'o':  (-halfExtent, 0.0),
               'i':  (+halfExtent, 0.0),
               'no': (-diagonal, -diagonal),
               'so': (-diagonal, +diagonal),
               'ni': (+diagonal, -diagonal),
               'si': (+diagonal, +diagonal)}

    return offsets.get(str(anchor).lower(), (0.0, 0.0))

def sectionCentreOffset(family: str, halfExtent, anchor: str = 'c', portRadius: float = 0.0):

    '''

    Where a section's centre sits relative to the scroll radius and the axial offset [m].

    A circle is drawn about the origin and then moved to its anchor, so its centre is the anchor
    offset, and a port centred on it is inside it as long as the section is the wider of the two.

    A squircle is drawn as a three quarter circle of radius `L` closed by a right angle at the
    local origin, and that corner is what the drawing anchors: it does not read the anchor. A port
    centred on the corner would touch both faces of the corner from outside and open only a
    quarter of itself into the section, so the corner is set back by the port radius in each
    direction, which inscribes the port in the corner instead.

    Parameters:
    -----------
    family : str
        One of `VOLUTESECTIONS`.
    halfExtent : float
        Half the section's extent, its radius for a circle [m].
    anchor : str
        The anchor the section is aligned by, for the families that read one.
    portRadius : float
        Radius of the port the section has to open onto [m]. Only a corner anchored family needs
        it.

    Returns:
    --------
    tuple
        Radial and axial offset of the section centre [m].

    '''

    checkFamily(family)

    if family == 'squarc':
        setBack = halfExtent - portRadius
        return (+setBack, -setBack)

    return anchorOffset(anchor, halfExtent)

def scrollPlacement(family: str, interfaceHydraulicDiameter: float, anchor: str,
                    portAxial: float, portRadius: float, portBore: float = 0.0):

    '''

    Scroll radius and axial offset that put the tongue section on the port it meets [m].

    The tongue carries one port's flow and is drawn barely wider than the port, so the two are
    effectively the same circle: a scroll placed anywhere else leaves the channels ending short of
    it. The anchor then says which edge of a section holds still as the scroll grows, and so
    whether the growing sections reach toward the nozzle or away from it.

    Parameters:
    -----------
    family : str
        One of `VOLUTESECTIONS`.
    interfaceHydraulicDiameter : float
        Hydraulic diameter of the tongue section [m].
    anchor : str
        The anchor the sections are aligned by.
    portAxial : float
        Axial position of the port centre [m].
    portRadius : float
        Radius of the port centre from the nozzle axis [m].
    portBore : float
        Diameter of the port itself [m], which a corner anchored section is set back by so the
        port opens fully into it.

    Returns:
    --------
    tuple
        Scroll radius and axial offset [m].

    '''

    halfExtent = characteristicLengthFromDiameter(family, interfaceHydraulicDiameter)
    radial, axial = sectionCentreOffset(family, halfExtent, anchor, portBore/2.0)

    return portRadius - radial, portAxial - axial
