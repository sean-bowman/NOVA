'''

Tests for the segment intersection in geometryTools.py.

`intersection` finds where two polylines cross by testing every pair of segments whose bounding
boxes overlap. Every segment of both curves has to be a candidate, the first and the last among
them, and a single crossing in the first segment of both curves has to be reported rather than
read as none, since its candidate index is (0, 0).

Author: Sean Bowman

'''

import numpy as np
import pytest

from NOVA.geometryTools import intersection

def crossingsOfAVerticalLine(at, xCurve, yCurve):

    '''Where a vertical line at x = at crosses the curve.'''

    return intersection(np.asarray(xCurve, dtype = float), np.asarray(yCurve, dtype = float),
                        np.array([at, at]), np.array([-1.0, 1.0]))

class TestIntersection:

    '''Every segment is tested, and one crossing in the first segments is found.'''

    xCurve, yCurve = [0.0, 0.5, 1.0], [0.0, 0.0, 0.0]

    @pytest.mark.parametrize('at', [0.2, 0.9])
    def testACrossingInTheFirstOrLastSegmentIsFound(self, at):

        x, y = crossingsOfAVerticalLine(at, self.xCurve, self.yCurve)

        assert np.ravel(x).tolist() == [pytest.approx(at)]
        assert np.ravel(y).tolist() == [pytest.approx(0.0)]

    def testAMissIsEmpty(self):

        x, y = crossingsOfAVerticalLine(1.2, self.xCurve, self.yCurve)

        assert len(x) == 0 and len(y) == 0

    def testTwoSegmentsCrossingAtTheirFirstSegmentsAreFound(self):

        x, y = intersection(np.array([0.0, 1.0]), np.array([0.0, 1.0]),
                            np.array([0.0, 1.0]), np.array([1.0, 0.0]))

        assert np.ravel(x).tolist() == [pytest.approx(0.5)]
        assert np.ravel(y).tolist() == [pytest.approx(0.5)]

    def testEveryCrossingOfALongCurveIsFound(self):

        # A sine sampled coarsely crosses its axis once per half period, the last one included
        x = np.linspace(0.0, 3.0, 31)
        y = np.sin(np.pi * x + 0.3)
        xCross, _ = intersection(x, y, np.array([-1.0, 4.0]), np.array([0.0, 0.0]))

        expected = (np.arange(1, 4) - 0.3 / np.pi)
        assert np.allclose(np.sort(np.ravel(xCross)), expected, atol = 5e-3)
