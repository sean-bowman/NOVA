
# -- NOVA: Curve and Surface Geometry Primitives -- #

'''

Pure geometry math with no NOVA state and no gas: parametric curve offsets, intersections,
fillets, splines and revolutions, plus the direction-cosine rotation every 3D sweep uses to wrap
a cross section around the nozzle axis.

Every solver that builds a swept surface, a wall contour or a wrapped channel calls in here
rather than differentiating a curve or rotating a point cloud itself, so the same numerical
technique backs the chamber wall, the cooling channels, the volutes and the plume lattice alike.

Author: Sean Bowman

'''

import numpy as np

# Permissive numeric-input alias: these helpers accept arrays, lists, or scalars
# interchangeably. Using this keeps static analysis from flagging valid array-like
# call sites while documenting intent.
ArrayLike = np.ndarray | list | float | int

#--------------------------------------------------------------------------------------------------------------------------#
# -- Curve tools -- #
#--------------------------------------------------------------------------------------------------------------------------#

def parallelOffset(xCurve: ArrayLike, yCurve: ArrayLike, offsetDistance: ArrayLike, centralDifference: bool = True) -> tuple:

    '''

    This function takes in the X and Y coordinates of a curve and creates a curve that is
    an equal distance to that curve in the curve normal direction. This acts like a curve offset
    in a traditional CAD software. The equations that drive this process are given as:

    x_parallel = x + (-offset_distance)*dy / sqrt(dx^2 + dy^2)
    y_parallel = y - (-offset_distance)*dx / sqrt(dx^2 + dy^2)

    '''

    # If the user has a constant offset distance, make it into an array for the loop
    if isinstance(offsetDistance, float):
        offsetDistance = offsetDistance * np.ones(len(xCurve))

    # Declare empty arrays
    deltaX = np.zeros(len(xCurve))
    deltaY = np.zeros(len(yCurve))
    xCurveParalleloffset = np.zeros(len(xCurve))
    yCurveParalleloffset = np.zeros(len(xCurve))

    # Do numerical derivative for passed in curve
    if centralDifference:
        deltaX = np.gradient(xCurve)
        deltaY = np.gradient(yCurve)
    else:
        for i in range(len(xCurve) - 1):
            deltaX[i] = xCurve[i+1] - xCurve[i]
            deltaY[i] = yCurve[i+1] - yCurve[i]
        deltaX[-1] = deltaX[-2]
        deltaY[-1] = deltaY[-2]

    norm = np.sqrt(deltaX**2 + deltaY**2)

    # Calculate points of parallel offset curve
    xCurveParalleloffset = xCurve + -offsetDistance * deltaY / norm
    yCurveParalleloffset = yCurve - -offsetDistance * deltaX / norm

    return xCurveParalleloffset, yCurveParalleloffset

def intersection(xCurve1: ArrayLike, yCurve1: ArrayLike, xCurve2: ArrayLike, yCurve2: ArrayLike) -> tuple:

    r'''

    Given two line segments segment1 and segment2 of curve1 and curve2 with endpoints:

    segment1 endpoints:  (x1[0], y1[0]) and (x1[-1], y1[-1])
    segment2 endpoints:  (x2[0], y2[0]) and (x2[-1], y2[-1])

    we can write four equations with four unknowns and solve them. The
    four unknowns are a, b, x, and y, where (x, y) is the intersection of
    segment1 and segment2. a is the distance from the starting point of segment1 to the
    intersection relative to the length of segment1, and b is the distance from the
    starting point of segment2 to the intersection relative to the length of segment2.
    For this function, we only care about the intersection point: (x, y).

    The four equations are:

    (x1[-1] - x1[0]) * a = x - x1[0]
    (x2[-1] - x2[0]) * b = x - x2[0]
    (y1[-1] - y1[0]) * a = y - y1[0]
    (y2[-1] - y2[0]) * b = y - y2[0]

    Rearranging and writing in matrix form:

    [dx1    0   -1   0      [a      [-x1[0]
      0    dx2  -1   0   *   b   =   -x2[0]
     dy1    0    0  -1       x       -y1[0]
      0    dy2   0  -1]      y]      -y2[0]]

    This is A*z = B. We can solve for z with z = A\B, where A\B is solvable with numpy.linalg.solve(A, B)

    Once we have our solution, z, we just have to look at a and b to determine
    whether segment1 and segment2 intersect.  If 0 <= a <= 1 and 0 <= b <= 1, then the two
    line segments cross and the intersection point is z[3, 4] = (x, y)
    
    '''

    # Helper functions to calculate moving minimum and maximum for passed in curves
    def movingMin(array):
        if len(array) == 2:
            movingMinimum = np.minimum(array[0],array[1])
        else:
            movingMinimum = np.minimum(array[0:-2],array[1:-1])
        return movingMinimum
    def movingMax(array):
        if len(array) == 2:
            movingMaximum = np.maximum(array[0],array[1])
        else:
            movingMaximum = np.maximum(array[0:-2],array[1:-1])
        return movingMaximum

    # If passed in arrays are lists, make them numpy arrays
    if type(xCurve1) is list:
        xCurve1 = np.array(xCurve1)
    if type(xCurve2) is list:
        xCurve2 = np.array(xCurve2)
    if type(yCurve1) is list:
        yCurve1 = np.array(yCurve1)
    if type(yCurve2) is list:
        yCurve2 = np.array(yCurve2)

    # If passed in arrays have no second dimension, give them one for convenience
    if len(xCurve1.shape) < 2:
        xCurve1 = xCurve1.reshape(len(xCurve1),1)
        yCurve1 = yCurve1.reshape(len(yCurve1),1)
    if len(xCurve2.shape) < 2:
        xCurve2 = xCurve2.reshape(len(xCurve2),1)
        yCurve2 = yCurve2.reshape(len(yCurve2),1)

    # Concatenate x and y parts of each curve into a single array and take their derivative
    curve1 = np.concatenate((xCurve1, yCurve1), axis = 1)
    curve2 = np.concatenate((xCurve2, yCurve2), axis = 1)
    dydx1 = np.diff(curve1, axis = 0)
    dydx2 = np.diff(curve2, axis = 0)

    # Draw bounding box for intersection
    foundIndex = np.argwhere((movingMin(xCurve1) <= movingMax(xCurve2).T) &
                             (movingMax(xCurve1) >= movingMin(xCurve2).T) &
                             (movingMin(yCurve1) <= movingMax(yCurve2).T) &
                             (movingMax(yCurve1) >= movingMin(yCurve2).T))

    # Special case for when each array is 2 elements long
    if foundIndex.shape == (1, 1):
        foundIndex_int = np.zeros((1,2), dtype = int)
        foundIndex_int[0,0] = foundIndex_int[0,1] = foundIndex[0][0]
        foundIndex = foundIndex_int
    # Special case for when there is no intersection (return an empty element for x and y)
    elif not foundIndex.any():
        xIntersect, yIntersect = [], []
        return xIntersect, yIntersect

    # Count number of intersections and build A, B, and z (output) arrays
    numIntersections = foundIndex.shape[0]
    outputArray = np.zeros((4,numIntersections))
    A = np.zeros((numIntersections,4,4))
    B = np.zeros((4,numIntersections))

    # Build A and B arrays
    A[:, [0, 1], 2] = -1
    A[:, [2, 3], 3] = -1
    A[:, [0, 2], 0] = dydx1[foundIndex[:,0],:]
    A[:, [1, 3], 1] = dydx2[foundIndex[:,1],:]

    B = -np.array([xCurve1[foundIndex[:,0]], xCurve2[foundIndex[:,1]], yCurve1[foundIndex[:,0]], yCurve2[foundIndex[:,1]]]).reshape((4,numIntersections))

    # Perform matrix solve operation to solve for z (outputArray)
    for i in range(numIntersections):
        outputArray[:,i] = np.linalg.solve(A[i,:,:], B[:,i])

    # Find where first two elements of outputArray are between 0 and 1
    inRange = np.argwhere((outputArray[0,:] >= 0) &
                          (outputArray[0,:] <= 1) &
                          (outputArray[1,:] >= 0) &
                          (outputArray[1,:] <= 1))

    # Return x and y coordinates of intersection point by sampling out of the 3rd and 4th elements of outputArray
    xIntersect = outputArray[2,inRange][:]
    yIntersect = outputArray[3,inRange][:]

    return xIntersect, yIntersect

def fillet(xCurve1: np.ndarray | list, yCurve1: np.ndarray | list, xCurve2: np.ndarray | list, yCurve2: np.ndarray | list, radiusOfCurvature: float, numPoints: int = 50) -> list[float]:

    '''
    
    This function is intended to be used for filleting two linear segments that are
    joined at a single point (or intersect at a single point that can be used as the join point).
    The two segments can be any length and any separation angle, and may be comprised of as few as 2 points each.

    This function works by first creating parallel offset curves of each of the passed in line segments. These offset
    curves are used to determine the unique solution where a fillet is applicable, which exists in the only intersection
    between the offset curves so long as the offset distance is the radius of curvature specified. If there are no intersections,
    then the fillet radius of curvature is too large to create a fillet between the given line segments.

    The fillet start and end angles are determined by the slope of each line segment at its respective endpoint,
    and a super ugly conditional statement built with trial and error catches all possible orientations of the fillet
    such that the function will work regardless of the orientation of the passed-in lines.

    Future update: Would love to re-orient the lines inside the function so that the fillet always occurs under the same
    spatial coordinates and then transform back to the original reference frame. That will get rid of the ugly
    conditional statement.
    
    '''

    # Find x and y differences for each curve
    dx1 = np.diff(xCurve1)
    dy1 = np.diff(yCurve1)

    dx2 = np.diff(xCurve2)
    dy2 = np.diff(yCurve2)

    # Create parallel offset curves
    xCurve1Offset1, yCurve1Offset1 = parallelOffset(xCurve1, yCurve1, radiusOfCurvature)
    xCurve1Offset2, yCurve1Offset2 = parallelOffset(xCurve1, yCurve1, -radiusOfCurvature)
    xCurve2Offset1, yCurve2Offset1 = parallelOffset(xCurve2, yCurve2, radiusOfCurvature)
    xCurve2Offset2, yCurve2Offset2 = parallelOffset(xCurve2, yCurve2, -radiusOfCurvature)

    # Find intersections between offset curves
    x1CircleIntersect, y1CircleIntersect = intersection(xCurve1Offset1, yCurve1Offset1, xCurve2Offset1, yCurve2Offset1)
    x2CircleIntersect, y2CircleIntersect = intersection(xCurve1Offset1, yCurve1Offset1, xCurve2Offset2, yCurve2Offset2)
    x3CircleIntersect, y3CircleIntersect = intersection(xCurve1Offset2, yCurve1Offset2, xCurve2Offset1, yCurve2Offset1)
    x4CircleIntersect, y3CircleIntersect = intersection(xCurve1Offset2, yCurve1Offset2, xCurve2Offset2, yCurve2Offset2)

    # Store intersection (x, y) pairs
    intersectionPoints    = [0 for x in range(4)]
    intersectionPoints[0] = [x1CircleIntersect, y1CircleIntersect]
    intersectionPoints[1] = [x2CircleIntersect, y2CircleIntersect]
    intersectionPoints[2] = [x3CircleIntersect, y3CircleIntersect]
    intersectionPoints[3] = [x4CircleIntersect, y3CircleIntersect]

    # Check for which of these are empty
    intersectionFlag = [1 for i in range(4)]
    for i in range(4):
        # If the given index is empty, change the 1 in the array to a 0
        if isinstance(intersectionPoints[i][0], list) and len(intersectionPoints[i][0]) == 0:
            intersectionFlag[i] = 0
        elif isinstance(intersectionPoints[i][0], np.ndarray) and intersectionPoints[i][0].size == 0:
            intersectionFlag[i] = 0
    # Find the index of the non-zero element
    intersectionIndex = [i for i, value in enumerate(intersectionFlag) if value != 0]

    # Calculate start and end angles of the fillet
    thetaFillet1 = np.arctan2(dy1[-1], dx1[-1])
    thetaFillet2 = np.arctan2(dy2[-1], dx2[-1])

    # Ugly conditional statement that catches all possible orientations of the fillet
    if ((thetaFillet1 - thetaFillet2) >= np.pi) & (thetaFillet2 < 0):
        thetaFillet2 = abs(thetaFillet2)
        thetaFillet = np.linspace(thetaFillet1, thetaFillet2, numPoints)
    elif (abs(thetaFillet1 - thetaFillet2) >= np.pi) & (thetaFillet1 < 0):
        thetaFillet1 = abs(thetaFillet1)
        thetaFillet = np.linspace(thetaFillet1, thetaFillet2, numPoints) + np.pi
    elif ((thetaFillet1 < 0) & (thetaFillet2 >= 0)) | ((thetaFillet1 <= 0) & (thetaFillet2 > 0)):
        thetaFillet = np.linspace(thetaFillet1, thetaFillet2, numPoints) - np.pi/2
    else:
        thetaFillet = np.linspace(thetaFillet1, thetaFillet2, numPoints) + np.pi/2

    # Draw a circle centered at the intersection location comprised of only the angles required to draw the fillet
    xFillet = intersectionPoints[intersectionIndex[0]][0][0] + radiusOfCurvature * np.cos(thetaFillet)
    yFillet = intersectionPoints[intersectionIndex[0]][1][0] + radiusOfCurvature * np.sin(thetaFillet)

    # Plots for testing
    # plt.style.use('dark_background')
    # fig, ax = plt.subplots(1, 1)
    # plt.plot(xCurve1, yCurve1, 'b')
    # plt.plot(xCurve2, yCurve2, 'r')
    # plt.plot(xCurve1Offset1,yCurve1Offset1,'--w')
    # plt.plot(xCurve1Offset2,yCurve1Offset2,'--w')
    # plt.plot(xCurve2Offset1,yCurve2Offset1,'--w')
    # plt.plot(xCurve2Offset2,yCurve2Offset2,'--w')
    # plt.plot(x1CircleIntersect,y1CircleIntersect,'*m')
    # plt.plot(x2CircleIntersect,y2CircleIntersect,'*m')
    # plt.plot(x3CircleIntersect,y3CircleIntersect,'*m')
    # plt.plot(x4CircleIntersect,y3CircleIntersect,'*m')
    # plt.plot(xFillet,yFillet,'c')
    # ax.set_aspect(aspect = 'equal')
    # plt.show(block = False)

    return xFillet, yFillet

def arcSpline(xPoints: ArrayLike, yPoints: ArrayLike, zPoints: ArrayLike | None = None,
              newNumPoints: int = 100, method: str = 'shapePreserving') -> tuple:

    '''

    Resample a polyline onto points spaced evenly along its own arc length.

    The input is a curve given as unevenly spaced points, in 2D or 3D. The output is
    `newNumPoints` points on a smooth curve through them, spaced at equal arc length rather than
    at equal parameter. NOVA uses it wherever a contour built from several pieces has to become
    one evenly sampled wall.

    Parameters:
    -----------
    xPoints, yPoints : ArrayLike
        The curve. Consecutive duplicates are dropped before fitting.
    zPoints : ArrayLike | None
        Third coordinate. None makes the call 2D and returns two arrays.
    newNumPoints : int
        Points in the result.
    method : str
        'shapePreserving' fits a PCHIP interpolant, which cannot leave the range of the points it
        passes through. 'curvatureContinuous' fits a natural cubic, which is C2 but overshoots at
        a corner. See below for why the first is the default.

    Returns:
    --------
    tuple
        (x, r) for a 2D call, (x, y, z) for a 3D one.

    Raises:
    -------
    ValueError
        If fewer than two distinct points remain after duplicates are dropped, or if `method` is
        not one of the two above.

    ----------------------------------------------------------------------
                    Why the fit is shape preserving
    ----------------------------------------------------------------------

    A C2 cubic through a curve with a corner in it must overshoot: continuity of curvature across
    a point where the curvature is genuinely discontinuous can only be bought by bending the
    curve out past the data on both sides. NOVA hands this function stitched curves routinely,
    where a converging section meets a throat arc, or a channel interface meets a turnaround, and
    those joins are corners.

    Measured on the shipped regenerative example, a natural cubic through the interfaced regen
    contour left the data by 6.36 mm at a station whose radius is 83.42 mm, which is 7.6 percent
    of the local radius, in a direction no input point goes. A PCHIP fit through the same points
    overshoots by zero, which is a property of the interpolant rather than a result for that case.

    The cost is curvature: PCHIP is C1, so the second derivative jumps at each input point. That
    is not read anywhere. Wall angles are taken with `np.gradient`, a first derivative, which
    stays continuous; the throat radius of curvature the Bartz correlation wants is a
    configuration input rather than something measured off the wall.

    'curvatureContinuous' restores the old behavior for a caller that knows its input is smooth
    and wants C2.

    ----------------------------------------------------------------------
                    Arc length
    ----------------------------------------------------------------------

    Spacing points evenly along the curve means inverting s(t), the arc length as a function of
    the spline parameter. That is done by sampling the fitted curve densely, integrating the
    speed |dP/dt| with the trapezoid rule, and interpolating the inverse. The sampling is fine
    enough that the residual is far below the geometry's own tolerance, and the whole thing is
    array work.

    '''

    from scipy.interpolate import CubicSpline, PchipInterpolator

    fitters = {'shapePreserving': PchipInterpolator, 'curvatureContinuous': CubicSpline}
    if method not in fitters:
        raise ValueError(f'arcSpline: method must be one of {sorted(fitters)}, got {method!r}.')

    is3D = zPoints is not None
    if not is3D:
        zPoints = np.zeros(len(xPoints))

    points = np.column_stack([np.asarray(array, dtype = float).ravel()
                              for array in (xPoints, yPoints, zPoints)])

    # A repeated point gives a zero-length segment, which is a zero-width parameter interval and
    # an unbounded derivative. One such pair appears in the shipped diverging contour, 6.7e-8 m
    # apart on a curve 1.6 m long.
    segment = np.linalg.norm(np.diff(points, axis = 0), axis = 1)
    scale = segment.sum()
    if scale <= 0:
        raise ValueError('arcSpline: every point is coincident, so there is no curve to resample.')

    keep = np.insert(segment > scale * 1e-12, 0, True)
    points = points[keep]

    if len(points) < 2:
        raise ValueError('arcSpline: fewer than two distinct points, so there is no curve.')

    # Chordal parameterization, normalized so the fit is scale independent.
    segment = np.linalg.norm(np.diff(points, axis = 0), axis = 1)
    parameter = np.insert(np.cumsum(segment / segment.sum()), 0, 0.0)

    fitter = fitters[method]
    curves = [fitter(parameter, points[:, i]) for i in range(3)]

    # Arc length along the fitted curve. The sample count scales with the input so a long,
    # detailed contour is not integrated more coarsely than a short one.
    sampleCount = max(4001, 40 * len(points))
    dense = np.linspace(0.0, 1.0, sampleCount)

    speed = np.linalg.norm(np.column_stack([curve.derivative()(dense) for curve in curves]),
                           axis = 1)
    arclength = np.concatenate([[0.0],
                                np.cumsum(0.5 * (speed[1:] + speed[:-1]) * np.diff(dense))])

    # Invert s(t) at evenly spaced arc lengths. np.interp needs an increasing first argument,
    # which arclength is by construction: speed is a norm, so it cannot be negative.
    targets = np.linspace(0.0, arclength[-1], newNumPoints)
    atParameter = np.interp(targets, arclength, dense)

    resampled = np.column_stack([curve(atParameter) for curve in curves])

    if is3D:
        return resampled[:, 0], resampled[:, 1], resampled[:, 2]

    return resampled[:, 0], resampled[:, 1]

def lineIntersection(point1: ArrayLike, angle1: float, point2: ArrayLike, angle2: float) -> tuple:

    '''
    
    This function takes in, for two different lines, a point on each line and the angle that each 
    line makes with the X axis and calculates the intersection point between the two lines.
    
    '''

    slope1, slope2 = np.tan(angle1), np.tan(angle2)
    yIntercept1, yIntercept2 = point1[1] - slope1 * point1[0], point2[1] - slope2 * point2[0]

    xIntersection = (yIntercept2 - yIntercept1) / (slope1 - slope2)
    yIntersection = (slope1 * xIntersection + yIntercept1 + slope2 * xIntersection + yIntercept2) / 2

    return xIntersection, yIntersection

#--------------------------------------------------------------------------------------------------------------------------#
# -- Surfaces and rotation -- #
#--------------------------------------------------------------------------------------------------------------------------#

def revolveContour(xContour: list | np.ndarray, rContour: list | np.ndarray, numSlices: int = 50) -> np.ndarray:

    '''
    
    Given a 2D contour, revolve it about the central axis to create a surface.
    
    '''

    if isinstance(xContour, list):
        xContour  = np.array(xContour)
        rContour  = np.array(rContour)

    zContour       = np.zeros(len(xContour))
    beforeRevolve  = np.zeros((numSlices, 3, len(xContour)))
    afterRevolve   = np.zeros((numSlices, 3, len(xContour)))
    rotationMatrix = np.zeros((numSlices, 3, 3))
    xContourRevolved, yContourRevolved, zContourRevolved = [np.zeros((numSlices, len(xContour))) for _ in range(3)]
    rollAngle      = np.linspace(0, 2 * np.pi, numSlices)

    beforeRevolve = np.array([zContour, rContour, xContour])

    for i in range(numSlices):

        # Create an array to hold the Euler angles for the rotation calculation
        rotationValue = [0, 0, rollAngle[i]]

        # Create the rotation cosine matrices in each cartesian direction
        Rx = np.array([[1, 0, 0],
                [0, np.cos(rotationValue[0]), -np.sin(rotationValue[0])],
                [0, np.sin(rotationValue[0]), np.cos(rotationValue[0])]])

        Ry = np.array([[np.cos(rotationValue[1]), 0, np.sin(rotationValue[1])],
                [0, 1, 0],
                [-np.sin(rotationValue[1]), 0, np.cos(rotationValue[1])]])

        Rz = np.array([[np.cos(rotationValue[2]), -np.sin(rotationValue[2]), 0],
                [np.sin(rotationValue[2]), np.cos(rotationValue[2]), 0],
                [0, 0, 1]])

        # Matrix multiply the rotation matrices to get a single rotation matrix that describes this rotation
        rotationMatrix[i,:,:] = Rz @ Ry @ Rx

        # Apply that rotation matrix to the pre-rotated volute matrix
        afterRevolve[i,:,:] = rotationMatrix[i,:,:] @ beforeRevolve

        # Extract the X, Y, and Z data from the 3D rotated volute matrix
        xContourRevolved[i,:] = afterRevolve[i,0,:]
        yContourRevolved[i,:] = afterRevolve[i,1,:]
        zContourRevolved[i,:] = afterRevolve[i,2,:]

    return xContourRevolved, yContourRevolved, zContourRevolved

def DCM(eulerAngles: ArrayLike, valueMatrix: ArrayLike, transpose: bool = False, rotationOrder: str = 'zyx') -> np.ndarray:

    '''
    
    Apply direction cosine matrix transformations to 'valueMatrix' given the angles in 'eulerAngles' and the order specified by 'rotationOrder'.
    
    '''

    # Create the rotation cosine matrices in each cartesian direction
    Rx = np.array([                                                                 \
                [1,             0,                        0           ],            \
                [0,             np.cos(eulerAngles[0]),  -np.sin(eulerAngles[0])],  \
                [0,             np.sin(eulerAngles[0]),   np.cos(eulerAngles[0])]]) # X-Axis rotation

    Ry = np.array([                                                                 \
                [np.cos(eulerAngles[1]),  0,              np.sin(eulerAngles[1])],  \
                [0,                       1,              0                     ],  \
                [-np.sin(eulerAngles[1]), 0,              np.cos(eulerAngles[1])]]) # Y-axis rotation

    Rz = np.array([                                                                 \
                [np.cos(eulerAngles[2]), -np.sin(eulerAngles[2]),   0           ],  \
                [np.sin(eulerAngles[2]),  np.cos(eulerAngles[2]),   0           ],  \
                [0,                       0,                        1           ]]) # Z-axis rotation

    # Matrix multiply the rotation matrices to get a single rotation matrix that describes this rotation
    if not transpose:
        match rotationOrder:
            case 'zyx':
                # Default operation order
                rotationMatrix = Rz @ Ry @ Rx
            case 'yzx':
                rotationMatrix = Ry @ Rz @ Rx
            case 'xyz':
                rotationMatrix = Rx @ Ry @ Rz
    elif transpose:
        match rotationOrder:
            case 'zyx':
                rotationMatrix = Rz @ Ry @ Rx . T
            case 'yzx':
                rotationMatrix = Ry @ Rz @ Rx . T
            case 'xyz':
                rotationMatrix = Rx @ Ry @ Rz . T

    # Apply that rotation matrix to the pre-rotated volute matrix
    unCenteredRotatedValueMatrix = rotationMatrix @ valueMatrix

    # Extract the X, Y, and Z data from the 3D rotated volute matrix
    rotatedX = unCenteredRotatedValueMatrix[0]
    rotatedY = unCenteredRotatedValueMatrix[1]
    rotatedZ = unCenteredRotatedValueMatrix[2]

    return rotatedX, rotatedY, rotatedZ

def chunkInterpolate(xPoints: ArrayLike, yPoints: ArrayLike, xNewPoints: ArrayLike) -> np.ndarray:

    '''
    
    Interpolate yPoints to a not strictly increasing xPoints.

    Intended for use with similar old and new x arrays i.e. must have the same range
    and total number of inflection points
    
    '''

    if len(xPoints) != len(yPoints):
        raise Exception('x and y point arrays must be the same size.')

    pointsOfInflection = np.concatenate([[0],np.where(np.diff(np.sign(np.diff(xPoints))) != 0)[0] + 1])
    newPointsOfInflection = np.concatenate([[0],np.where(np.diff(np.sign(np.diff(xNewPoints))) != 0)[0] + 1])
    if 1 in newPointsOfInflection and 1 not in pointsOfInflection:
        newPointsOfInflection = np.delete(newPointsOfInflection,1)

    if len(pointsOfInflection) != len(newPointsOfInflection):
        raise Exception('Old and new x arrays must have the same number of inflection points.')

    yNewPoints = np.array([])

    ## 1...n-1 chunks
    for i in range(1,len(pointsOfInflection)):

        # chunk

        j = pointsOfInflection[i-1]
        k = pointsOfInflection[i]

        xChunk = xPoints[j:k]
        yChunk = yPoints[j:k]

        if sum(np.sign(np.diff(xChunk))) < 0:
            flipFlag = True
        else:
            flipFlag = False

        if flipFlag:
            xChunk = np.flip(xChunk)
            yChunk = np.flip(yChunk)

        # interpolate

        m = newPointsOfInflection[i-1]
        n = newPointsOfInflection[i]

        if not flipFlag:
            yNewChunk = np.interp(xNewPoints[m:n],xChunk,yChunk)
            yNewPoints = np.append(yNewPoints,yNewChunk)
        elif flipFlag:
            yNewChunk = np.interp(np.flip(xNewPoints[m:n]),xChunk,yChunk)
            yNewPoints = np.append(yNewPoints,np.flip(yNewChunk))

    ## n chunk

    # chunk

    j = pointsOfInflection[-1]

    xChunk = xPoints[j:]
    yChunk = yPoints[j:]

    if sum(np.sign(np.diff(xChunk))) < 0:
        flipFlag = True
    else:
        flipFlag = False

    if flipFlag:
        xChunk = np.flip(xChunk)
        yChunk = np.flip(yChunk)

    # interpolate

    m = newPointsOfInflection[-1]

    if not flipFlag:
        yNewChunk = np.interp(xNewPoints[m:],xChunk,yChunk)
        yNewPoints = np.append(yNewPoints,yNewChunk)
    elif flipFlag:
        yNewChunk = np.interp(np.flip(xNewPoints[m:]),xChunk,yChunk)
        yNewPoints = np.append(yNewPoints,np.flip(yNewChunk))

    return yNewPoints
