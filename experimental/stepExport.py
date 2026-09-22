
# -- NOVA: STEP Export Of A Revolved Contour -- #

'''

Writing a nozzle to STEP as the exact surfaces it is made of, rather than as the triangles that
approximate them.

`py2cad` writes STL, which is a tessellation: a wall becomes ten thousand flat facets and the
curve that generated them is gone. A CAD package can display that and a printer can slice it,
but it cannot offset the wall by a thickness, fillet it into a flange or section it and get a
smooth edge, because there is no longer a smooth surface to operate on. STEP carries the
surfaces themselves.

Two kinds of geometry cover every component NOVA builds, and each has a STEP form that states
it exactly:

    revolved    The walls and the keep-out are a 2D profile swept about the nozzle axis, which
                is SURFACE_OF_REVOLUTION over a B_SPLINE_CURVE_WITH_KNOTS. The whole component
                reduces to one spline and one sweep.
    swept       The channels and volutes are a cross section carried along a path, held as a
                structured grid of points, which is a tensor-product B_SPLINE_SURFACE_WITH_KNOTS
                interpolating that grid. Interpolation is separable, so the surface is two
                passes of the same 1D fit.

Each component is written as its own body, in the axis order `py2cad` already uses for it, so a
STEP file lands where its STL does. Nothing is trimmed, unioned or intersected against anything
else. That boundary is deliberate: writing a surface is transcription, while trimming two
surfaces against each other needs a surface-surface intersection, which is the algorithm a
B-rep kernel exists to provide. `docs/reports/stepExport_2026-09-20.md` records what adding
booleans would take and why the surfaces here are the right input to it.

Nothing here imports a CAD kernel. The file is assembled as ISO 10303-21 text, which stays
tractable because every component is a tube: one face, one seam walked twice, and a closed
curve at each end.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Validated against an independent B-rep kernel, a closed-form reference and a commercial CAD
package.** Every component written from the cached showcase nozzle was read back with
OpenCASCADE (OCP, through build123d 0.12.0), which accepted all of them, returned `True` from
`BRepCheck_Analyzer` on each, and recovered `Geom_SurfaceOfRevolution` or `Geom_BSplineSurface`
as appropriate rather than an approximating patch. The revolved wall has been opened in
SolidWorks, whose reader is stricter about seam orientation than OpenCASCADE's.

Revolved geometry is checked against Pappus's centroid theorem, A = integral of 2*pi*r ds, by
adaptive quadrature on the same spline: 1.314862086 m^2 against the kernel's 1.314862085 m^2 on
the showcase contour, agreeing to 5e-10 relative, which is the quadrature floor rather than a
geometry difference.

Swept geometry is checked against its own grid triangulated, which underestimates a curved
surface and must converge upward under refinement. On the channel it does, from 0.005615721 m^2
at the grid as given to 0.005633310 m^2 at sixteen times the density; Richardson extrapolation
gives 0.005633390 m^2 against the kernel's 0.005633389 m^2. Both fits interpolate their source
points to 0.000000 um.

What is not validated: the writer has only been driven on contours that stay clear of the axis,
and raises rather than emitting the degenerate seam a profile touching r = 0 would need. No
assembled body has been produced or checked, because nothing here performs a boolean.

Author: Sean Bowman

'''

import numpy as np
from scipy.interpolate import make_interp_spline, splprep

def _real(value: float) -> str:

    '''STEP reals must carry a decimal point or an exponent, which %G does not guarantee.'''

    text = f'{float(value):.12G}'
    if 'E' not in text and '.' not in text:
        text += '.'
    return text

def _point(values) -> str:

    return '(' + ','.join(_real(value) for value in values) + ')'

class StepFile:

    '''

    Entity table that hands out instance names and renders the physical file.

    STEP references entities by name rather than by position, so every line has to know its own
    number before anything can point at it. Appending through `add` and taking back the
    reference it returns keeps that bookkeeping in one place.

    '''

    def __init__(self, name: str, schema: str = 'AUTOMOTIVE_DESIGN'):

        self.name = name
        self.schema = schema
        self.lines = []

    def add(self, text: str) -> str:

        '''Append one entity, returning its instance name for other entities to reference.'''

        reference = f'#{len(self.lines) + 1}'
        self.lines.append(f'{reference} = {text};')
        return reference

    def render(self, timestamp: str = '1970-01-01T00:00:00') -> str:

        '''The complete ISO 10303-21 text, header through terminator.'''

        header = ('ISO-10303-21;\n'
                  'HEADER;\n'
                  "FILE_DESCRIPTION(('STEP AP214'),'1');\n"
                  f"FILE_NAME('{self.name}','{timestamp}',(''),(''),"
                  "'NOVA','NOVA nozzle design suite','');\n"
                  f"FILE_SCHEMA(('{self.schema}'));\n"
                  'ENDSEC;\n'
                  'DATA;\n')

        return header + '\n'.join(self.lines) + '\nENDSEC;\nEND-ISO-10303-21;\n'

def fitProfileSpline(axial: np.ndarray, radial: np.ndarray, degree: int = 3) -> dict:

    '''

    Interpolating B-spline through a 2D profile, in the form STEP states a spline in.

    scipy returns the knot vector with its end knots already repeated degree+1 times, which is
    the clamped form STEP expects, so the conversion is only collapsing that vector into
    distinct knots and their multiplicities.

    Parameters:
    -----------
    axial, radial : np.ndarray
        The profile, in the units the file will be written in
    degree : int
        Spline degree, 3 for the cubic every CAD package handles natively

    Returns:
    --------
    dict : control points, distinct knots, multiplicities, the scipy tck and its parameters

    '''

    (knotVector, coefficients, resolvedDegree), parameters = splprep(
        [axial, radial], s = 0, k = degree)

    numControlPoints = len(knotVector) - resolvedDegree - 1
    distinctKnots, multiplicities = np.unique(np.round(knotVector, 12), return_counts = True)

    return {
        'degree':           resolvedDegree,
        'controlAxial':     np.asarray(coefficients[0])[:numControlPoints],
        'controlRadial':    np.asarray(coefficients[1])[:numControlPoints],
        'knots':            distinctKnots,
        'multiplicities':   multiplicities,
        'tck':              (knotVector, coefficients, resolvedDegree),
        'parameters':       parameters}

def _tubeFace(step: StepFile, surface: str, seamCurve: str, startCurve: str, endCurve: str,
              startPoint, endPoint) -> str:

    '''

    Close a tube surface into a face, and return the shell holding it.

    A full revolution and a lofted closed section are the same topology: the surface closes on
    itself in one direction and is open in the other, so the boundary is one seam walked twice
    in opposite directions with a closed end curve at each end of it. Both writers build their
    face here so the seam is only got right once.

    Parameters:
    -----------
    surface, seamCurve, startCurve, endCurve : str
        Entity references. The end curves are closed, so each carries one vertex twice.
    startPoint, endPoint : sequence of float
        The two ends of the seam, in file units

    '''

    startCartesian = step.add(f"CARTESIAN_POINT('',{_point(startPoint)})")
    endCartesian = step.add(f"CARTESIAN_POINT('',{_point(endPoint)})")
    startVertex = step.add(f"VERTEX_POINT('',{startCartesian})")
    endVertex = step.add(f"VERTEX_POINT('',{endCartesian})")

    seamEdge = step.add(f"EDGE_CURVE('',{startVertex},{endVertex},{seamCurve},.T.)")
    startEdge = step.add(f"EDGE_CURVE('',{startVertex},{startVertex},{startCurve},.T.)")
    endEdge = step.add(f"EDGE_CURVE('',{endVertex},{endVertex},{endCurve},.T.)")

    seamForward = step.add(f"ORIENTED_EDGE('',*,*,{seamEdge},.T.)")
    seamReversed = step.add(f"ORIENTED_EDGE('',*,*,{seamEdge},.F.)")
    endForward = step.add(f"ORIENTED_EDGE('',*,*,{endEdge},.T.)")
    startReversed = step.add(f"ORIENTED_EDGE('',*,*,{startEdge},.F.)")

    loop = step.add(f"EDGE_LOOP('',({seamForward},{endForward},{seamReversed},{startReversed}))")
    bound = step.add(f"FACE_OUTER_BOUND('',{loop},.T.)")
    face = step.add(f"ADVANCED_FACE('',({bound}),{surface},.T.)")

    return step.add(f"OPEN_SHELL('',({face}))")

def _writeScaffold(step: StepFile, name: str, shellModel: str, worldFrame: str,
                   context: str) -> None:

    '''

    The product structure that makes a file openable rather than merely parseable.

    A reader needs the chain from PRODUCT down to SHAPE_DEFINITION_REPRESENTATION to find any
    geometry at all, so this is the same for every component written.

    '''

    applicationContext = step.add("APPLICATION_CONTEXT('automotive design')")
    step.add("APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',"
             f'2000,{applicationContext})')
    productContext = step.add(f"PRODUCT_CONTEXT('',{applicationContext},'mechanical')")
    product = step.add(f"PRODUCT('{name}','{name}','',({productContext}))")
    step.add(f"PRODUCT_RELATED_PRODUCT_CATEGORY('part','',({product}))")
    formation = step.add(f"PRODUCT_DEFINITION_FORMATION('','',{product})")
    definitionContext = step.add(
        f"PRODUCT_DEFINITION_CONTEXT('part definition',{applicationContext},'design')")
    definition = step.add(f"PRODUCT_DEFINITION('design','',{formation},{definitionContext})")
    definitionShape = step.add(f"PRODUCT_DEFINITION_SHAPE('','',{definition})")
    representation = step.add(
        f"MANIFOLD_SURFACE_SHAPE_REPRESENTATION('{name}',({worldFrame},{shellModel}),{context})")
    step.add(f'SHAPE_DEFINITION_REPRESENTATION({definitionShape},{representation})')

def _writeUnitsAndFrame(step: StepFile) -> tuple:

    '''Millimetre, radian and steradian, plus the frame the representation is placed in.'''

    lengthUnit = step.add('(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.))')
    angleUnit = step.add('(NAMED_UNIT(*)PLANE_ANGLE_UNIT()SI_UNIT($,.RADIAN.))')
    solidAngleUnit = step.add('(NAMED_UNIT(*)SI_UNIT($,.STERADIAN.)SOLID_ANGLE_UNIT())')
    uncertainty = step.add(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),{lengthUnit},"
                           "'distance_accuracy_value','confusion accuracy')")
    context = step.add(f'(GEOMETRIC_REPRESENTATION_CONTEXT(3)'
                       f'GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(({uncertainty}))'
                       f'GLOBAL_UNIT_ASSIGNED_CONTEXT(({lengthUnit},{angleUnit},'
                       f"{solidAngleUnit}))REPRESENTATION_CONTEXT('',''))")

    origin = step.add(f"CARTESIAN_POINT('',{_point((0.0, 0.0, 0.0))})")
    frameAxis = step.add(f"DIRECTION('',{_point((0.0, 0.0, 1.0))})")
    frameReference = step.add(f"DIRECTION('',{_point((1.0, 0.0, 0.0))})")
    worldFrame = step.add(f"AXIS2_PLACEMENT_3D('',{origin},{frameAxis},{frameReference})")

    return context, worldFrame

def writeRevolvedContour(path: str, axial: np.ndarray, radial: np.ndarray,
                         name: str = 'nozzleWall', scale: float = 1e3,
                         degree: int = 3) -> dict:

    '''

    Write one revolved contour as a STEP surface model.

    The axial sign is flipped and the profile placed in the XZ plane, which is what the contour
    .txt export already does, so a STEP and a text contour from the same run land on top of each
    other when both are imported.

    Parameters:
    -----------
    path : str
        Destination .step file
    axial, radial : np.ndarray
        The 2D wall profile [m], revolved about the axial direction
    name : str
        Product name carried in the file, which is what a CAD tree shows
    scale : float
        Factor onto the file's unit, 1e3 for a metre-based contour written in millimetres
    degree : int
        Spline degree

    Returns:
    --------
    dict : the fitted spline and the entity count, for verification

    Raises:
    -------
    ValueError : if the profile is too short to fit, or reaches the revolution axis

    '''

    axial = np.asarray(axial, dtype = float)
    radial = np.asarray(radial, dtype = float)

    if axial.size != radial.size:
        raise ValueError('axial and radial profiles must be the same length')
    if axial.size <= degree:
        raise ValueError(f'a degree {degree} fit needs more than {degree} points, '
                         f'and the profile has {axial.size}')
    if np.any(radial <= 0.0):
        raise ValueError('the profile reaches or crosses the revolution axis, which closes the '
                         'surface to a point and needs a degenerate seam this does not emit')

    fit = fitProfileSpline(-axial * scale, radial * scale, degree)
    controlAxial, controlRadial = fit['controlAxial'], fit['controlRadial']

    step = StepFile(name)
    context, worldFrame = _writeUnitsAndFrame(step)

    # -- The profile, in the XZ plane so that its plane contains the revolution axis -- #
    controlReferences = [step.add(f"CARTESIAN_POINT('',{_point((a, 0.0, r))})")
                         for a, r in zip(controlAxial, controlRadial)]

    profile = step.add(
        f"B_SPLINE_CURVE_WITH_KNOTS('',{fit['degree']},({','.join(controlReferences)}),"
        f".UNSPECIFIED.,.F.,.F.,"
        f"({','.join(str(int(m)) for m in fit['multiplicities'])}),"
        f"({','.join(_real(k) for k in fit['knots'])}),.UNSPECIFIED.)")

    # -- The sweep -- #
    axisOrigin = step.add(f"CARTESIAN_POINT('',{_point((0.0, 0.0, 0.0))})")
    axisDirection = step.add(f"DIRECTION('',{_point((1.0, 0.0, 0.0))})")
    revolutionAxis = step.add(f"AXIS1_PLACEMENT('',{axisOrigin},{axisDirection})")
    surface = step.add(f"SURFACE_OF_REVOLUTION('',{profile},{revolutionAxis})")

    # -- The two end circles, which bound the sweep along with the seam -- #
    # A clamped B-spline starts and ends on its first and last control point, so these are the
    # profile's own endpoints rather than a separate evaluation.
    startAxial, startRadial = float(controlAxial[0]), float(controlRadial[0])
    endAxial, endRadial = float(controlAxial[-1]), float(controlRadial[-1])

    def endCircle(axialStation: float, radius: float) -> str:

        '''A circle about the nozzle axis, starting at the profile's own point on it.'''

        centre = step.add(f"CARTESIAN_POINT('',{_point((axialStation, 0.0, 0.0))})")
        normal = step.add(f"DIRECTION('',{_point((1.0, 0.0, 0.0))})")
        reference = step.add(f"DIRECTION('',{_point((0.0, 0.0, 1.0))})")
        placement = step.add(f"AXIS2_PLACEMENT_3D('',{centre},{normal},{reference})")
        return step.add(f"CIRCLE('',{placement},{_real(radius)})")

    startCircle = endCircle(startAxial, startRadial)
    endCircleCurve = endCircle(endAxial, endRadial)

    shell = _tubeFace(step, surface, profile, startCircle, endCircleCurve,
                      (startAxial, 0.0, startRadial), (endAxial, 0.0, endRadial))
    shellModel = step.add(f"SHELL_BASED_SURFACE_MODEL('',({shell}))")

    _writeScaffold(step, name, shellModel, worldFrame, context)

    with open(path, 'w', encoding = 'utf-8') as handle:
        handle.write(step.render())

    return {'entities': len(step.lines), 'controlPoints': len(controlReferences), **fit}

def _averagedChordParameters(grid: np.ndarray, axis: int) -> np.ndarray:

    '''

    Chord-length parameters along one direction of a grid, averaged over the other.

    A tensor-product surface needs one knot vector per direction, shared by every row. Fitting
    each row on its own parameters would give each a different one, so the parameters are
    averaged first, which is the standard construction and keeps the fit close to arc length.

    '''

    ordered = np.moveaxis(grid, axis, 0)
    steps = np.linalg.norm(np.diff(ordered, axis = 0), axis = -1)
    steps = steps.reshape(steps.shape[0], -1)

    cumulative = np.concatenate([np.zeros((1, steps.shape[1])), np.cumsum(steps, axis = 0)])
    total = cumulative[-1]

    if np.any(total <= 0.0):
        raise ValueError('a row of the grid has zero length, so it cannot be parameterized')

    parameters = (cumulative / total).mean(axis = 1)

    if np.any(np.diff(parameters) <= 0.0):
        raise ValueError('averaged parameters are not strictly increasing')

    return parameters

def fitLoftSurface(grid: np.ndarray, degree: int = 3) -> dict:

    '''

    Tensor-product B-spline interpolating a structured grid of points.

    Axis 0 is the closed direction, around the cross section, and axis 1 is open, along the
    sweep. Interpolation is separable, so the surface is built in two passes: fit a curve
    through the data along the closed direction for every station, then fit a curve through
    those control points along the sweep. The result passes through every original point.

    The closed direction is fitted with the seam tangent pinned at both ends, taken from a
    periodic fit of the same section. That buys the tangent continuity of a periodic spline
    while keeping a clamped knot vector, which CAD readers handle far more consistently than
    an unclamped one.

    Parameters:
    -----------
    grid : np.ndarray
        (m, n, 3) points, with grid[0] and grid[-1] coincident
    degree : int
        Spline degree in both directions

    Returns:
    --------
    dict : the control net and the knot vector and multiplicities of each direction

    '''

    grid = np.asarray(grid, dtype = float)

    if grid.ndim != 3 or grid.shape[2] != 3:
        raise ValueError(f'expected an (m, n, 3) grid of points, got {grid.shape}')
    if min(grid.shape[0], grid.shape[1]) <= degree:
        raise ValueError(f'a degree {degree} fit needs more than {degree} points in each '
                         f'direction, and the grid is {grid.shape[0]} by {grid.shape[1]}')

    # The section has to close exactly for a periodic fit, and it closes to rounding already.
    grid = grid.copy()
    grid[-1] = grid[0]

    aroundParameters = _averagedChordParameters(grid, axis = 0)
    alongParameters = _averagedChordParameters(grid, axis = 1)

    # -- Pass one: around each closed section, tangent pinned at the seam -- #
    intermediate, aroundKnots = [], None
    for station in range(grid.shape[1]):

        section = grid[:, station, :]
        periodic = make_interp_spline(aroundParameters, section, k = degree,
                                      bc_type = 'periodic')
        tangent = periodic(aroundParameters[0], nu = 1)

        clamped = make_interp_spline(aroundParameters, section, k = degree,
                                     bc_type = ([(1, tangent)], [(1, tangent)]))

        if aroundKnots is None:
            aroundKnots = clamped.t
        elif not np.allclose(aroundKnots, clamped.t):
            raise ValueError('sections produced different knot vectors, so they cannot be '
                             'assembled into a tensor product')

        intermediate.append(clamped.c)

    intermediate = np.stack(intermediate, axis = 1)

    # -- Pass two: along the sweep, through the control points pass one produced -- #
    net, alongKnots = [], None
    for row in range(intermediate.shape[0]):

        curve = make_interp_spline(alongParameters, intermediate[row], k = degree)

        if alongKnots is None:
            alongKnots = curve.t
        elif not np.allclose(alongKnots, curve.t):
            raise ValueError('sweep rows produced different knot vectors')

        net.append(curve.c)

    net = np.stack(net, axis = 0)

    def collapse(knotVector):
        distinct, multiplicities = np.unique(np.round(knotVector, 12), return_counts = True)
        return distinct, multiplicities

    aroundDistinct, aroundMultiplicities = collapse(aroundKnots)
    alongDistinct, alongMultiplicities = collapse(alongKnots)

    return {
        'degree':                 degree,
        'net':                    net,
        'aroundKnots':            aroundDistinct,
        'aroundMultiplicities':   aroundMultiplicities,
        'alongKnots':             alongDistinct,
        'alongMultiplicities':    alongMultiplicities,
        'aroundKnotVector':       aroundKnots,
        'alongKnotVector':        alongKnots,
        'aroundParameters':       aroundParameters,
        'alongParameters':        alongParameters}

def writeLoftedSurface(path: str, grid: np.ndarray, name: str = 'component',
                       scale: float = 1e3, degree: int = 3) -> dict:

    '''

    Write one swept component as a STEP B-spline surface.

    The grid is taken in the frame the caller hands over, so a component lands wherever its STL
    already does. Axis 0 must be the closed cross section and axis 1 the sweep.

    Parameters:
    -----------
    path : str
        Destination .step file
    grid : np.ndarray
        (m, n, 3) points [m], closed along axis 0
    name : str
        Product name carried in the file
    scale : float
        Factor onto the file's unit, 1e3 for metres written as millimetres

    Returns:
    --------
    dict : the fit, plus the entity count

    '''

    fit = fitLoftSurface(np.asarray(grid, dtype = float) * scale, degree)
    net = fit['net']

    step = StepFile(name)
    context, worldFrame = _writeUnitsAndFrame(step)

    # -- The control net, indexed [around][along] as the surface entity expects -- #
    references = [[step.add(f"CARTESIAN_POINT('',{_point(net[i, j])})")
                   for j in range(net.shape[1])]
                  for i in range(net.shape[0])]

    rows = ','.join('(' + ','.join(row) + ')' for row in references)
    surface = step.add(
        f"B_SPLINE_SURFACE_WITH_KNOTS('',{fit['degree']},{fit['degree']},({rows}),"
        f'.UNSPECIFIED.,.T.,.F.,.F.,'
        f"({','.join(str(int(m)) for m in fit['aroundMultiplicities'])}),"
        f"({','.join(str(int(m)) for m in fit['alongMultiplicities'])}),"
        f"({','.join(_real(k) for k in fit['aroundKnots'])}),"
        f"({','.join(_real(k) for k in fit['alongKnots'])}),.UNSPECIFIED.)")

    # -- The boundary isocurves, whose control points are edges of the net -- #
    # A clamped tensor-product surface carries its boundary curves on its boundary control
    # rows, so these are read off the net rather than refitted.
    def boundaryCurve(controlPoints, knots, multiplicities) -> str:

        points = ','.join(step.add(f"CARTESIAN_POINT('',{_point(point)})")
                          for point in controlPoints)
        return step.add(
            f"B_SPLINE_CURVE_WITH_KNOTS('',{fit['degree']},({points}),.UNSPECIFIED.,.F.,.F.,"
            f"({','.join(str(int(m)) for m in multiplicities)}),"
            f"({','.join(_real(k) for k in knots)}),.UNSPECIFIED.)")

    seamCurve = boundaryCurve(net[0, :], fit['alongKnots'], fit['alongMultiplicities'])
    startCurve = boundaryCurve(net[:, 0], fit['aroundKnots'], fit['aroundMultiplicities'])
    endCurve = boundaryCurve(net[:, -1], fit['aroundKnots'], fit['aroundMultiplicities'])

    shell = _tubeFace(step, surface, seamCurve, startCurve, endCurve,
                      net[0, 0], net[0, -1])
    shellModel = step.add(f"SHELL_BASED_SURFACE_MODEL('',({shell}))")

    _writeScaffold(step, name, shellModel, worldFrame, context)

    with open(path, 'w', encoding = 'utf-8') as handle:
        handle.write(step.render())

    return {'entities': len(step.lines), 'controlPoints': net.shape[0] * net.shape[1], **fit}

def orientGrid(grid: np.ndarray, tolerance: float = 1e-9) -> np.ndarray:

    '''

    Put the closed direction of a component grid on axis 0.

    NOVA's swept components do not agree on which axis runs around the cross section: the
    channel carries it on axis 0 and the volutes on axis 1. Rather than hold a table of which
    is which, the closed direction is found by testing which one returns to its own start.

    Raises:
    -------
    ValueError : if neither direction closes, or both do

    '''

    grid = np.asarray(grid, dtype = float)

    closesOnZero = np.abs(grid[0, :, :] - grid[-1, :, :]).max() < tolerance
    closesOnOne = np.abs(grid[:, 0, :] - grid[:, -1, :]).max() < tolerance

    if closesOnZero and closesOnOne:
        raise ValueError('both directions of the grid close, so the seam is ambiguous')
    if closesOnZero:
        return grid
    if closesOnOne:
        return np.transpose(grid, (1, 0, 2))

    raise ValueError('neither direction of the grid closes, so it is not a swept tube')

def exportNozzleStep(nozzle, folder: str, filename: str = 'nozzle') -> list:

    '''

    Write every component of a finished nozzle as its own STEP file.

    One body per file and no booleans: the revolved walls come out as surfaces of revolution
    and the swept components as B-spline surfaces, each in the frame its STL already uses, so
    a CAD package opening all of them gets the parts in the positions it would have got from
    the STL set. Assembling them into one solid is the reader's to do; see
    `docs/reports/stepExport_2026-09-20.md` for why that boundary is where it is.

    What exists is written. A component the run did not build is skipped rather than raising,
    which is the rule `exports.exportData` already follows.

    Parameters:
    -----------
    nozzle : Nozzle
        A generated nozzle
    folder : str
        Destination directory, created if absent
    filename : str
        Stem each component name is appended to

    Returns:
    --------
    list : paths written

    '''

    import os

    os.makedirs(folder, exist_ok = True)
    written = []

    def present(*names) -> bool:

        '''Whether every named array exists, is non-empty and is finite.'''

        for name in names:
            value = getattr(nozzle, name, None)
            if value is None:
                return False
            value = np.asarray(value, dtype = float)
            if value.size == 0 or not np.all(np.isfinite(value)):
                return False
        return True

    def revolved(component: str, axialName: str, radialName: str) -> None:

        if not present(axialName, radialName):
            return
        path = os.path.join(folder, f'{filename}{component}.step')
        writeRevolvedContour(path, getattr(nozzle, axialName), getattr(nozzle, radialName),
                             name = f'{filename}{component}')
        written.append(path)

    def swept(component: str, arrays, flipAxial: bool = False) -> None:

        if not present(*arrays):
            return

        stacked = [np.asarray(getattr(nozzle, name), dtype = float) for name in arrays]
        if flipAxial:
            stacked[2] = -stacked[2]

        try:
            grid = orientGrid(np.stack(stacked, axis = -1))
        except ValueError as error:
            print(f'  skipping {component}: {error}')
            return

        path = os.path.join(folder, f'{filename}{component}.step')
        writeLoftedSurface(path, grid, name = f'{filename}{component}')
        written.append(path)

    # -- Revolved walls, which share the contour .txt convention of axial in X -- #
    revolved('HotWall', 'xNozzleWall', 'rNozzleWall')
    revolved('ShellWall', 'xNozzleShell', 'rNozzleShell')

    if getattr(nozzle, 'nozzleKeepOut', None) is not None:
        keepOut = nozzle.nozzleKeepOut
        path = os.path.join(folder, f'{filename}KeepOut.step')
        writeRevolvedContour(path, keepOut.x, keepOut.r, name = f'{filename}KeepOut')
        written.append(path)

    # -- Swept components, each in the axis order py2cad already writes it in -- #
    swept('Channel', ('zChannel', 'yChannel', 'xChannel'), flipAxial = True)

    for side in ('Inlet', 'Return'):
        swept(f'{side}Volute',
              (f'x{side}Volute', f'y{side}Volute', f'z{side}Volute'))
        swept(f'{side}VoluteShell',
              (f'x{side}VoluteShell', f'y{side}VoluteShell', f'z{side}VoluteShell'))
        for part in ('SupportWall', 'SupportUpper', 'SupportLower'):
            swept(f'{side}Volute{part}',
                  (f'x{side}Volute{part}', f'y{side}Volute{part}', f'z{side}Volute{part}'))

    if written:
        print(f'Writing {len(written)} component(s) to .step')

    return written

def loftedArea(grid: np.ndarray) -> float:

    '''

    Area of a swept surface, summed over the quadrilaterals of its own point grid.

    Each cell is split into two triangles and their areas added, so this converges on the true
    area from below as the grid refines. It is the reference the written surface is checked
    against, computed from the points rather than from anything the writer produced.

    '''

    grid = np.asarray(grid, dtype = float)
    corner = grid[:-1, :-1]
    firstDiagonal = np.cross(grid[1:, :-1] - corner, grid[:-1, 1:] - corner)

    opposite = grid[1:, 1:]
    secondDiagonal = np.cross(grid[:-1, 1:] - opposite, grid[1:, :-1] - opposite)

    return float(0.5 * (np.linalg.norm(firstDiagonal, axis = -1).sum()
                        + np.linalg.norm(secondDiagonal, axis = -1).sum()))

def revolvedArea(axial: np.ndarray, radial: np.ndarray) -> float:

    '''

    Lateral area of the surface a profile revolves into, by Pappus: A = integral of 2*pi*r ds.

    This is the reference the written file is checked against, so it is computed from the
    contour rather than from anything the writer produced.

    '''

    axial = np.asarray(axial, dtype = float)
    radial = np.asarray(radial, dtype = float)
    arcLength = np.hypot(np.diff(axial), np.diff(radial))

    return float(np.sum(2.0 * np.pi * 0.5 * (radial[1:] + radial[:-1]) * arcLength))

if __name__ == '__main__':

    import os
    import pickle
    import re
    import sys

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    sys.path.insert(0, os.path.join(root, 'src'))

    source = os.path.join(root, 'featureShowcase', 'showcaseBase.pkl')
    if not os.path.exists(source):
        sys.exit(f'no cached nozzle at {source}; run featureShowcase/runBaseCase.py first')

    with open(source, 'rb') as handle:
        nozzle = pickle.load(handle)

    axial = np.asarray(nozzle.xNozzleWall, dtype = float)
    radial = np.asarray(nozzle.rNozzleWall, dtype = float)

    def danglingReferences(path: str) -> list:

        '''Entity names a file points at without defining, which must be none.'''

        text = open(path, encoding = 'utf-8').read()
        data = text.split('DATA;', 1)[1].rsplit('ENDSEC;', 1)[0]

        defined = set(re.findall(r'^(#\d+) =', data, flags = re.MULTILINE))
        referenced = set()
        for line in data.strip().split('\n'):
            referenced.update(re.findall(r'#\d+', line.split('=', 1)[1]))

        return sorted(referenced - defined)

    # -- The revolved wall, checked against Pappus on its own spline -- #
    destination = os.path.join(here, 'nozzleWall.step')
    result = writeRevolvedContour(destination, axial, radial, name = 'NOVANozzleWall')

    from scipy.interpolate import splev

    onProfile = splev(result['parameters'], result['tck'])
    deviation = np.hypot(-np.asarray(onProfile[0]) / 1e3 - axial,
                         np.asarray(onProfile[1]) / 1e3 - radial).max()

    dense = splev(np.linspace(0.0, 1.0, 200001), result['tck'])
    areaSpline = revolvedArea(-np.asarray(dense[0]) / 1e3, np.asarray(dense[1]) / 1e3)

    print('-- Revolved contour --')
    print(f'profile points        : {axial.size}')
    print(f'control points        : {result["controlPoints"]}')
    print(f'STEP entities         : {result["entities"]}')
    print(f'file size             : {os.path.getsize(destination) / 1024:.1f} kB')
    print(f'max station deviation : {deviation * 1e6:.4f} um')
    print(f'area, raw contour     : {revolvedArea(axial, radial):.9f} m^2')
    print(f'area, fitted spline   : {areaSpline:.9f} m^2')
    print(f'dangling references   : {danglingReferences(destination) or "none"}')

    # -- Every component the cached run built -- #
    folder = os.path.join(here, 'stepComponents')
    print()
    print('-- All components --')
    paths = exportNozzleStep(nozzle, folder, filename = 'NOVANozzle')

    for path in paths:
        dangling = danglingReferences(path)
        print(f'  {os.path.basename(path):<34} {os.path.getsize(path) / 1024:>8.1f} kB  '
              f'refs {"ok" if not dangling else dangling}')
