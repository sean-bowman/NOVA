# -- Arc-length resampling tests -- #

'''

Checks on `utils.arcSpline`, which every contour NOVA builds passes through.

Two things are tested. That the resampling is right: points come back evenly spaced along the
curve, an exactly representable curve is reproduced exactly, and the fit converges on an analytic
curve as the input is refined. And that the fit cannot invent geometry: the shape-preserving
method must never return a point outside the range of the points it was given, because that is
the failure that made the sunken converging contour unbuildable.

The second property is the reason the default is shape preserving. A C2 cubic through a curve
with a genuine corner has to overshoot: curvature continuity across a point where the curvature
is really discontinuous can only be had by bending the curve out past the data on both sides. On
a converging wall that produces a radius below the throat, an area ratio below one, and no
subsonic solution.

'''

import numpy as np
import pytest

from NOVA.utils import arcSpline

# --------------------------------------------------------------------------------------------- #
# -- The resampling itself -- #
# --------------------------------------------------------------------------------------------- #

@pytest.mark.parametrize('method', ['shapePreserving', 'curvatureContinuous'])
def testAStraightLineIsReproducedExactly(method):

    '''A line is in the span of both interpolants, so it comes back exactly and evenly divided.'''

    x, y = arcSpline(np.array([0.0, 1.0, 2.0, 5.0]), np.array([0.0, 2.0, 4.0, 10.0]),
                     newNumPoints = 6, method = method)

    assert x == pytest.approx(np.linspace(0.0, 5.0, 6), abs = 1e-9)
    assert y == pytest.approx(np.linspace(0.0, 10.0, 6), abs = 1e-9)

@pytest.mark.parametrize('method', ['shapePreserving', 'curvatureContinuous'])
def testPointsComeBackEvenlySpacedAlongTheCurve(method):

    '''

    The whole purpose: equal arc length between consecutive points, whatever the input spacing.
    Checked on a quarter circle sampled non-uniformly, where equal arc length is equal angle.

    '''

    angle = np.linspace(0.0, np.pi / 2, 60)**1.7 * (np.pi / 2) / (np.pi / 2)**1.7
    x, y = arcSpline(np.cos(angle), np.sin(angle), newNumPoints = 9, method = method)

    resampledAngle = np.arctan2(y, x)

    assert np.degrees(resampledAngle) == pytest.approx(np.linspace(0.0, 90.0, 9), abs = 0.05)

def testSpacingIsUniformOnAContourLikeCurve():

    '''Consecutive chord lengths agree to a fraction of a per cent on a smooth curve.'''

    t = np.linspace(0.0, 1.0, 140)
    x = t
    y = 1.0 + 3.0 * t**1.5

    resampledX, resampledY = arcSpline(x, y, newNumPoints = 80)
    chord = np.hypot(np.diff(resampledX), np.diff(resampledY))

    assert chord.std() / chord.mean() < 5e-3

def testTheEndPointsAreHeld():

    '''Resampling must not move the ends of the curve, which are joins to other geometry.'''

    x = np.array([0.0, 0.3, 0.55, 0.9, 1.4, 2.0])
    y = np.array([1.0, 1.2, 1.35, 1.5, 1.55, 1.6])

    resampledX, resampledY = arcSpline(x, y, newNumPoints = 40)

    assert (resampledX[0], resampledY[0]) == pytest.approx((x[0], y[0]), abs = 1e-12)
    assert (resampledX[-1], resampledY[-1]) == pytest.approx((x[-1], y[-1]), abs = 1e-9)

def testRefiningTheInputConverges():

    '''

    Deviation from an analytic curve falls as the input is refined, for both methods. A
    resampler that did not converge would be fitting something other than the curve it is given.

    '''

    truthT = np.linspace(0.0, 1.0, 200001)
    truthX, truthY = truthT, np.exp(-((truthT - 0.5)**2) / 0.02)

    def deviation(count, method):
        t = np.linspace(0.0, 1.0, count)
        x, y = arcSpline(t, np.exp(-((t - 0.5)**2) / 0.02), newNumPoints = 60, method = method)
        return max(float(np.min(np.hypot(px - truthX, py - truthY))) for px, py in zip(x, y))

    for method in ('shapePreserving', 'curvatureContinuous'):
        coarse = deviation(30, method)
        fine = deviation(300, method)
        assert fine < coarse / 10.0, method

# --------------------------------------------------------------------------------------------- #
# -- The guarantee: no invented geometry -- #
# --------------------------------------------------------------------------------------------- #

def stitchedConvergingWall():

    '''

    The shape that broke the sunken contour: a dense run, a single isolated control point, then
    another dense run, with a corner where they meet. The minimum radius is at the join, which is
    what a throat is.

    '''

    gap = 0.025

    ellipse = np.linspace(-0.30, -0.18, 45)
    ellipseRadius = 0.180 - 0.35 * (ellipse + 0.30)

    arc = np.linspace(-0.175, -0.130, 40)
    arcRadius = 0.138 - 0.40 * (arc + 0.175)

    controlX, controlRadius = -0.130 + gap, 0.1200

    wall = np.linspace(-0.130 + 2 * gap, 0.30, 45)
    wallRadius = 0.1200 + 1.05 * (wall - (-0.130 + 2 * gap))

    x = np.concatenate([ellipse, arc, [controlX], wall])
    r = np.concatenate([ellipseRadius, arcRadius, [controlRadius], wallRadius])

    return x, r

def testShapePreservingNeverLeavesTheDataRange():

    '''

    The property the default exists for. On a stitched wall with a corner the resampled contour
    must stay inside the range of the points it was built from.

    '''

    x, r = stitchedConvergingWall()
    resampledX, resampledR = arcSpline(x, r, newNumPoints = 60)

    assert resampledR.min() >= r.min() - 1e-12
    assert resampledR.max() <= r.max() + 1e-12
    assert resampledX.min() >= x.min() - 1e-12
    assert resampledX.max() <= x.max() + 1e-12

def testTheCurvatureContinuousFitDoesLeaveItOnACorner():

    '''

    The converse, recorded so the reason for the default is not lost. This is not a defect in
    scipy: a C2 interpolant through a corner has no other option.

    '''

    x, r = stitchedConvergingWall()
    _, overshootingR = arcSpline(x, r, newNumPoints = 60, method = 'curvatureContinuous')

    # Four of sixty points land below the throat, the worst 1.7 mm inside it. The sunken contour
    # this reproduces put sixteen of sixty below, the worst 15.6 mm in.
    assert overshootingR.min() < r.min()
    assert np.count_nonzero(overshootingR < r.min()) >= 3

def testNoPointFallsBelowTheThroat():

    '''

    The failure stated in the terms that matter. A converging wall resampled below its own
    minimum radius has an area ratio under one, which has no subsonic solution, and the run stops
    two hundred lines later in a Mach solver rather than here.

    '''

    x, r = stitchedConvergingWall()
    throatRadius = r.min()

    _, resampledR = arcSpline(x, r, newNumPoints = 60)

    assert np.count_nonzero(resampledR < throatRadius - 1e-12) == 0

@pytest.mark.parametrize('newNumPoints', [10, 60, 250])
def testTheGuaranteeHoldsAtEverySampleCount(newNumPoints):

    '''Resampling coarser than the input is where an interpolant is most tempted to overshoot.'''

    x, r = stitchedConvergingWall()
    _, resampledR = arcSpline(x, r, newNumPoints = newNumPoints)

    assert resampledR.min() >= r.min() - 1e-12
    assert resampledR.max() <= r.max() + 1e-12

# --------------------------------------------------------------------------------------------- #
# -- Degenerate input -- #
# --------------------------------------------------------------------------------------------- #

def testRepeatedPointsAreDropped():

    '''

    A repeated point is a zero-length segment, so a zero-width parameter interval and an
    unbounded derivative. The shipped diverging contour contains one such pair, 6.7e-8 m apart on
    a curve 1.6 m long.

    '''

    x = np.array([0.0, 0.0, 1.0, 2.0, 2.0, 3.0])
    y = np.array([0.0, 0.0, 1.0, 4.0, 4.0, 9.0])

    resampledX, resampledY = arcSpline(x, y, newNumPoints = 20)

    assert np.all(np.isfinite(resampledX))
    assert np.all(np.isfinite(resampledY))
    assert np.all(np.diff(resampledX) > 0)

def testNearlyRepeatedPointsAreDroppedToo():

    '''The real case is not an exact duplicate but a segment far below the curve scale.'''

    x = np.array([0.0, 6.7e-8, 0.5, 1.0, 1.6])
    y = np.array([1.0, 1.0,    1.4, 1.9, 2.5])

    resampledX, resampledY = arcSpline(x, y, newNumPoints = 30)

    assert np.all(np.isfinite(resampledX))
    assert np.all(np.isfinite(resampledY))

def testAllCoincidentPointsIsAnError():

    '''There is no curve through a single repeated point, and saying so beats returning NaN.'''

    with pytest.raises(ValueError):
        arcSpline(np.zeros(5), np.zeros(5), newNumPoints = 10)

def testAnUnknownMethodIsRefusedByName():

    with pytest.raises(ValueError, match = 'method'):
        arcSpline(np.array([0.0, 1.0]), np.array([0.0, 1.0]),
                  newNumPoints = 5, method = 'cubic')

# --------------------------------------------------------------------------------------------- #
# -- Three dimensions -- #
# --------------------------------------------------------------------------------------------- #

def testThreeDimensionalCallReturnsThreeArrays():

    '''The volute and channel geometry resample 3D paths through the same function.'''

    t = np.linspace(0.0, 2 * np.pi, 80)
    x, y, z = arcSpline(np.cos(t), np.sin(t), t / (2 * np.pi), newNumPoints = 25)

    assert len(x) == len(y) == len(z) == 25

def testAHelixComesBackEvenlySpaced():

    '''A helix has constant speed in arc length, so equal spacing is exactly checkable.'''

    t = np.linspace(0.0, 4 * np.pi, 400)
    x, y, z = arcSpline(np.cos(t), np.sin(t), 0.3 * t, newNumPoints = 40)

    chord = np.sqrt(np.diff(x)**2 + np.diff(y)**2 + np.diff(z)**2)

    assert chord.std() / chord.mean() < 1e-3
