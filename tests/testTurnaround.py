'''

Tests for the turnaround ring of a two-pass jacket in turnaround.py.

Author: Sean Bowman

'''

import numpy as np
import pytest

from NOVA.errors import InvalidInputError
from NOVA.turnaround import sizeTurnaround, turnaroundSurface

RING = dict(channelMassFlow = 0.05, density = 40.0, downFlowArea = 8.0e-6, upFlowArea = 1.2e-5,
            pitch = 0.012, wallRadius = 0.3, axialPosition = 1.2, channelDepth = 0.004,
            hotWallThickness = 0.001, pressure = 1.0e7, yieldStrength = 2.0e8)

def testTheRingTurnsAtTheVelocityItIsSizedFor():

    ring = sizeTurnaround(**RING)
    turning = RING['channelMassFlow'] / (RING['density'] * 2.0 * ring.sectionRadius * RING['pitch'])

    assert ring.downVelocity == pytest.approx(0.05 / (40.0 * 8.0e-6), rel = 1e-14)
    assert turning == pytest.approx(0.5 * ring.downVelocity, rel = 1e-12)

def testTheLossIsAnExitAndAnEntrance():

    ring = sizeTurnaround(**RING)
    expected = 0.5 * 40.0 * ring.downVelocity**2 + 0.25 * 40.0 * ring.upVelocity**2

    assert ring.pressureDrop == pytest.approx(expected, rel = 1e-14)

def testTheWallCarriesTheHoopStress():

    ring = sizeTurnaround(**RING)
    hoop = RING['pressure'] * ring.sectionRadius / ring.wallThickness

    assert hoop == pytest.approx(RING['yieldStrength'] / 1.5, rel = 1e-12)
    assert sizeTurnaround(**RING, minWallThickness = 0.05).wallThickness == 0.05

def testTheRingSitsOutsideTheChannels():

    ring = sizeTurnaround(**RING)
    assert ring.ringRadius - ring.sectionRadius - ring.wallThickness == pytest.approx(0.3 + 0.001 + 0.004, rel = 1e-14)

def testTheSurfaceIsATorus():

    ring = sizeTurnaround(**RING)
    x, y, z = turnaroundSurface(ring, numAround = 60, numSection = 30)
    distance = np.hypot(np.hypot(y, z) - ring.ringRadius, x - ring.axialPosition)

    assert distance == pytest.approx(np.full(x.shape, ring.sectionRadius), rel = 1e-12)

@pytest.mark.parametrize('name, value', [('density', 0.0), ('pitch', -1.0), ('velocityRatio', 1.5)])
def testAnUnsizableRingIsRefused(name, value):

    with pytest.raises(InvalidInputError):
        sizeTurnaround(**{**RING, name: value})
