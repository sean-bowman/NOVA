'''

Tests for the keep-out envelope in keepOut.py.

The envelope is a packaging boundary rather than a physical model, so there is no external
reference to validate it against and none is claimed. What is checked is that it is the surface
its construction says it is: the quarter ellipse closes on the dimensions it was given, the
ordering the two consumers depend on holds, the revolved surface is consistent with the profile,
and the clearance measure reports the sign it promises.

The one closed-form check available is the ellipse itself. Every point must satisfy

    ((x - x0) / depth)^2 + (r / radius)^2 = 1

exactly, which is what makes the profile an ellipse rather than something ellipse-like.

Author: Sean Bowman

'''

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'NOVANozzleDesigner'))

from keepOut import KeepOutEnvelope, keepOutEnvelope, packingClearance, revolveKeepOut

chamberRadius = 0.09

class TestConstruction:

    '''The envelope closes on the dimensions it was given.'''

    def testEndpointsAreTheShoulderAndTheHub(self):

        envelope = keepOutEnvelope(chamberRadius, axialOffset = -0.02, radius = 0.08,
                                   depth = 0.05, hubRadius = 0.03)

        shoulderX, shoulderR = envelope.shoulder
        hubX, hubR = envelope.hub

        # The shoulder sits on the offset plane at the full radius, its tangent axial.
        assert shoulderX == pytest.approx(-0.02, abs = 1e-15)
        assert shoulderR == pytest.approx(0.08,  abs = 1e-15)

        # The hub is where the sweep is truncated, at the radius that was asked for.
        assert hubR == pytest.approx(0.03, abs = 1e-12)
        assert hubX < shoulderX

    def testProfileIsExactlyAnEllipse(self):

        envelope = keepOutEnvelope(chamberRadius, axialOffset = -0.02, radius = 0.08,
                                   depth = 0.05, hubRadius = 0.03, numPoints = 250)

        residual = (((envelope.x - envelope.axialOffset) / envelope.depth)**2
                    + (envelope.r / envelope.radius)**2) - 1.0

        assert np.max(np.abs(residual)) < 1e-14

    def testOrderingRunsShoulderToHub(self):

        # Both consumers read index 0 as the outermost point and index -1 as the innermost:
        # the sunken section takes its outer arc centre from the first point, and the volute
        # packing check closes its ramp from the last.
        envelope = keepOutEnvelope(chamberRadius, numPoints = 40)

        assert np.all(np.diff(envelope.r) < 0)
        assert np.all(np.diff(envelope.x) < 0)
        assert envelope.r[0] > envelope.r[-1]

    def testDepthSetsTheAxialExtent(self):

        shallow = keepOutEnvelope(chamberRadius, depth = 0.02, hubRadius = 0.0)
        deep    = keepOutEnvelope(chamberRadius, depth = 0.06, hubRadius = 0.0)

        # Swept all the way to the axis, the axial extent is the depth exactly.
        assert shallow.x[0] - shallow.x[-1] == pytest.approx(0.02, abs = 1e-12)
        assert deep.x[0]    - deep.x[-1]    == pytest.approx(0.06, abs = 1e-12)

    def testPointCountIsHonoured(self):

        for numPoints in (2, 17, 100, 501):
            envelope = keepOutEnvelope(chamberRadius, numPoints = numPoints)
            assert len(envelope.x) == numPoints
            assert len(envelope.r) == numPoints

class TestDefaults:

    '''Unset dimensions take their defaults, whether unset means None or NaN.'''

    def testDefaultsComeFromTheChamberRadius(self):

        envelope = keepOutEnvelope(chamberRadius)

        assert envelope.radius      == pytest.approx(chamberRadius)
        assert envelope.depth       == pytest.approx(0.5  * chamberRadius)
        assert envelope.hubRadius   == pytest.approx(0.25 * chamberRadius)
        assert envelope.axialOffset == 0.0

    def testNanMeansUnsetJustAsNoneDoes(self):

        # setInputs turns an unset JSON field into NaN rather than None, so both spellings
        # of 'not specified' have to reach the same envelope.
        fromNone = keepOutEnvelope(chamberRadius, axialOffset = None, radius = None,
                                   depth = None, hubRadius = None)
        fromNan  = keepOutEnvelope(chamberRadius, axialOffset = np.nan, radius = np.nan,
                                   depth = np.nan, hubRadius = np.nan)

        assert np.array_equal(fromNone.x, fromNan.x)
        assert np.array_equal(fromNone.r, fromNan.r)

    def testDepthAndHubFollowAnExplicitRadius(self):

        # Naming a radius smaller than the chamber has to move the defaults with it, or the
        # hub would sit at a fraction of a radius the envelope does not have.
        envelope = keepOutEnvelope(chamberRadius, radius = 0.04)

        assert envelope.depth     == pytest.approx(0.5  * 0.04)
        assert envelope.hubRadius == pytest.approx(0.25 * 0.04)

class TestRejections:

    '''Dimensions that do not describe an envelope are refused.'''

    @pytest.mark.parametrize('chamber', [0.0, -0.05, np.nan, np.inf])
    def testChamberRadiusMustBeAPositiveNumber(self, chamber):

        with pytest.raises(ValueError, match = 'chamberRadius'):
            keepOutEnvelope(chamber)

    def testHubOutsideTheShoulderIsRefused(self):

        with pytest.raises(ValueError, match = 'hub radius'):
            keepOutEnvelope(chamberRadius, radius = 0.05, hubRadius = 0.05)

        with pytest.raises(ValueError, match = 'hub radius'):
            keepOutEnvelope(chamberRadius, radius = 0.05, hubRadius = 0.06)

        with pytest.raises(ValueError, match = 'hub radius'):
            keepOutEnvelope(chamberRadius, hubRadius = -0.01)

    def testNonPositiveDepthIsRefused(self):

        with pytest.raises(ValueError, match = 'depth'):
            keepOutEnvelope(chamberRadius, depth = 0.0)

        with pytest.raises(ValueError, match = 'depth'):
            keepOutEnvelope(chamberRadius, depth = -0.01)

    def testAtLeastTwoPointsAreNeeded(self):

        with pytest.raises(ValueError, match = 'numPoints'):
            keepOutEnvelope(chamberRadius, numPoints = 1)

class TestRevolve:

    '''The revolved surface is the profile, swept.'''

    def testShapeAndAxisConvention(self):

        envelope = keepOutEnvelope(chamberRadius, numPoints = 30)
        x, y, z = revolveKeepOut(envelope, numSlices = 24)

        assert x.shape == y.shape == z.shape == (30, 24)

        # x is constant around a slice: it is the nozzle axis station of that profile point.
        assert np.allclose(x - envelope.x[:, None], 0.0, atol = 0.0)

    def testRadiusIsPreservedAtEverySlice(self):

        envelope = keepOutEnvelope(chamberRadius, numPoints = 30)
        _, y, z = revolveKeepOut(envelope, numSlices = 24)

        sweptRadius = np.sqrt(y**2 + z**2)

        assert np.max(np.abs(sweptRadius - envelope.r[:, None])) < 1e-15

    def testDefaultSliceCountGivesASquareMesh(self):

        envelope = keepOutEnvelope(chamberRadius, numPoints = 30)
        x, _, _ = revolveKeepOut(envelope)

        assert x.shape == (30, 30)

class TestPackingClearance:

    '''The clearance reports the sign it promises.'''

    def testOutsideIsPositiveAndInsideIsNegative(self):

        envelope = keepOutEnvelope(chamberRadius, radius = 0.08, depth = 0.05, hubRadius = 0.02)

        # A point on the envelope, and the same station moved out and moved in.
        station = envelope.x[len(envelope.x) // 2]
        onEnvelope = envelope.r[len(envelope.x) // 2]

        assert packingClearance(envelope, station, onEnvelope)[0] == pytest.approx(0.0, abs = 1e-12)
        assert packingClearance(envelope, station, onEnvelope + 0.01)[0] > 0
        assert packingClearance(envelope, station, onEnvelope - 0.01)[0] < 0

    def testStationsClearOfTheEnvelopeCannotIntrude(self):

        envelope = keepOutEnvelope(chamberRadius)

        # Downstream of the shoulder and upstream of the hub there is no envelope to hit.
        clearance = packingClearance(envelope, [envelope.x[0] + 0.05, envelope.x[-1] - 0.05], [0.0, 0.0])

        assert np.all(np.isinf(clearance))
        assert np.all(clearance > 0)

    def testTheEnvelopeHasZeroClearanceAgainstItself(self):

        envelope = keepOutEnvelope(chamberRadius, numPoints = 60)
        clearance = packingClearance(envelope, envelope.x, envelope.r)

        assert np.max(np.abs(clearance)) < 1e-12

class TestDataclass:

    '''The envelope carries the numbers it was built from.'''

    def testDimensionsAreRecorded(self):

        envelope = keepOutEnvelope(chamberRadius, axialOffset = -0.01, radius = 0.07,
                                   depth = 0.03, hubRadius = 0.02)

        assert isinstance(envelope, KeepOutEnvelope)
        assert envelope.axialOffset == -0.01
        assert envelope.radius      == 0.07
        assert envelope.depth       == 0.03
        assert envelope.hubRadius   == 0.02
