'''

Tests for the combustion chamber barrel in chamber.py.

`prependCombustionChamber` sizes a constant-area barrel so that the chamber volume, injector face
to throat, is what the characteristic length asks for. L* is defined over the whole chamber, so
the converging cone counts toward it and the barrel is the remainder: sizing the barrel as
Lstar * At / Ac instead would overshoot the target volume by exactly the cone. These tests hold
the delivered L* to the requested one, the delivered volume to the profile the caller gets back,
and each refusal to the input that earns it.

Author: Sean Bowman

'''

from types import SimpleNamespace

import numpy as np
import pytest

from NOVA.chamber import prependCombustionChamber
from NOVA.errors import InvalidInputError

throatRadius  = 0.05
chamberRadius = 0.09
coneLength    = 0.08

def convergingCone(numberOfPoints: int = 60):

    '''A straight converging cone from the chamber radius to the throat, chamber end first.'''

    x = np.linspace(-coneLength, 0.0, numberOfPoints)
    r = np.linspace(chamberRadius, throatRadius, numberOfPoints)

    return x, r

def chamberState(numContourPoints: int = 100, **fields):

    '''The fields of a converging section state that the barrel reads.'''

    return SimpleNamespace(**{'rNozzleWall': np.array([throatRadius]),
                              'numContourPoints': numContourPoints,
                              'chamberLength': None, 'Lstar': None, **fields})

def volumeOfRevolution(x, r):

    '''The volume the profile sweeps about the axis, by the same rule the barrel is sized with.'''

    return float(np.trapezoid(np.pi*np.asarray(r, dtype = float)**2, np.asarray(x, dtype = float)))

class TestCharacteristicLength:

    '''The barrel is sized so that the chamber delivers the requested L*.'''

    @pytest.mark.parametrize('requestedLstar', [0.6, 1.0, 1.5])
    def testTheDeliveredLstarIsTheRequestedOne(self, requestedLstar):

        state = chamberState(Lstar = requestedLstar)
        x, r = convergingCone()

        prependCombustionChamber(state, x, r)

        assert state.chamberLstarActual == pytest.approx(requestedLstar, rel = 1e-12)

    @pytest.mark.parametrize('requestedLstar', [0.6, 1.0, 1.5])
    def testTheProfileHandedBackSweepsTheReportedVolume(self, requestedLstar):

        state = chamberState(Lstar = requestedLstar)
        x, r = convergingCone()

        xChamber, rChamber = prependCombustionChamber(state, x, r)

        assert volumeOfRevolution(xChamber, rChamber) == pytest.approx(state.chamberVolume, rel = 1e-12)
        assert state.chamberVolume == pytest.approx(requestedLstar*np.pi*throatRadius**2, rel = 1e-12)

    def testTheConeCountsTowardTheVolume(self):

        # Sizing the barrel as Lstar * At / Ac would ignore the cone and overshoot by its volume
        state = chamberState(Lstar = 1.0)
        x, r = convergingCone()

        prependCombustionChamber(state, x, r)

        ignoringTheCone = 1.0*throatRadius**2/chamberRadius**2
        assert state.chamberBarrelLength < ignoringTheCone
        assert (ignoringTheCone - state.chamberBarrelLength) \
               == pytest.approx(volumeOfRevolution(x, r)/(np.pi*chamberRadius**2), rel = 1e-12)

class TestBarrelGeometry:

    '''A given barrel length is honored exactly, and the barrel sits at the chamber radius.'''

    def testTheBarrelExtendsTheContourByItsLength(self):

        state = chamberState(chamberLength = 0.2)
        x, r = convergingCone()

        xChamber, rChamber = prependCombustionChamber(state, x, r)

        assert state.chamberBarrelLength == pytest.approx(0.2)
        assert xChamber[0] == pytest.approx(x[0] - 0.2)
        assert xChamber[-1] == pytest.approx(x[-1])
        assert rChamber[-1] == pytest.approx(r[-1])

    def testTheBarrelIsStraightAtTheChamberRadius(self):

        state = chamberState(chamberLength = 0.2)
        x, r = convergingCone()

        xChamber, rChamber = prependCombustionChamber(state, x, r)

        onBarrel = xChamber < x[0]
        assert onBarrel.sum() > 1
        assert np.allclose(rChamber[onBarrel], chamberRadius)
        assert np.all(np.diff(xChamber) > 0)

    def testTheContractionRatioIsTheAreaRatio(self):

        state = chamberState(chamberLength = 0.2)
        x, r = convergingCone()

        prependCombustionChamber(state, x, r)

        assert state.chamberContractionRatio == pytest.approx(chamberRadius**2/throatRadius**2)

class TestNoChamberRequested:

    '''With neither length nor L*, the converging section is the whole chamber.'''

    def testTheContourIsHandedBackUnchanged(self):

        state = chamberState()
        x, r = convergingCone()

        xChamber, rChamber = prependCombustionChamber(state, x, r)

        assert xChamber is x and rChamber is r
        assert state.chamberBarrelLength == 0.0
        assert state.chamberLstarActual \
               == pytest.approx(volumeOfRevolution(x, r)/(np.pi*throatRadius**2), rel = 1e-12)

    def testAnLstarThatTheConeAlreadyFillsLeavesNoBarrel(self):

        x, r = convergingCone()
        exactly = volumeOfRevolution(x, r)/(np.pi*throatRadius**2)
        state = chamberState(Lstar = exactly)

        xChamber, rChamber = prependCombustionChamber(state, x, r)

        assert state.chamberBarrelLength == pytest.approx(0.0, abs = 1e-15)
        assert xChamber is x and rChamber is r

class TestRefusals:

    '''Each refusal names the input that earns it.'''

    def testBothLengthAndLstarIsRefused(self):

        state = chamberState(chamberLength = 0.2, Lstar = 1.0)
        x, r = convergingCone()

        with pytest.raises(InvalidInputError, match = 'chamberLength'):
            prependCombustionChamber(state, x, r)

    def testANegativeLengthIsRefused(self):

        state = chamberState(chamberLength = -0.01)
        x, r = convergingCone()

        with pytest.raises(InvalidInputError, match = 'chamberLength'):
            prependCombustionChamber(state, x, r)

    @pytest.mark.parametrize('requestedLstar', [0.0, -1.0])
    def testANonPositiveLstarIsRefused(self, requestedLstar):

        state = chamberState(Lstar = requestedLstar)
        x, r = convergingCone()

        with pytest.raises(InvalidInputError, match = 'Lstar'):
            prependCombustionChamber(state, x, r)

    def testAnLstarSmallerThanTheConeIsRefused(self):

        x, r = convergingCone()
        tooSmall = 0.5*volumeOfRevolution(x, r)/(np.pi*throatRadius**2)
        state = chamberState(Lstar = tooSmall)

        with pytest.raises(InvalidInputError, match = 'Lstar'):
            prependCombustionChamber(state, x, r)
