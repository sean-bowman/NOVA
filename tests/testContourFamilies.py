'''

Tests for the three contoured families and the properties that let them be compared.

Most of this file is cheap: the family resolver and the geometric exactness of a prescribed wall
need no flow solve at all. The rest is not, because the only way to establish that the cubic
family contains the parabolic one, or that a wall which must compress is seen to compress, is to
march the characteristics over both and look at what comes back. Those solves are held to one
coarse mesh and shared across the tests that read them.

The containment test is the load-bearing one. Every claim that a searched contour beats a charted
parabola rests on the searched family containing the charted one, because otherwise a worse result
cannot distinguish a worse family from a worse search. If that test fails, no cross-family number
in the validation document means anything.

'''
import os

import numpy as np
import pytest

from NOVA.contour import divergingSectionFamily, divergingSectionSpellings
from NOVA.contourKernel import ThroatGeometry
from NOVA.contourOptimization import isMonotoneWall, parabolaDesignVector
from NOVA.gasDynamics import conicalLength
from NOVA.wallGeometry import thrustOptimizedParabolaWall

GAMMA = 1.1475421191138746
AREA_RATIO, LENGTH_FRACTION, MESH = 40.0, 0.80, 30

#--------------------------------------------------------------------------------------------------------------------------#
# -- The family selector -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.mark.parametrize('spelling, family', [
    ('rao', 'truncatedIdeal'), ('tic', 'truncatedIdeal'), ('TIC', 'truncatedIdeal'),
    ('truncatedIdeal', 'truncatedIdeal'),
    ('top', 'thrustOptimizedParabola'), ('TOP', 'thrustOptimizedParabola'),
    ('thrustOptimizedParabola', 'thrustOptimizedParabola'),
    ('toc', 'thrustOptimizedContour'), ('thrustOptimizedContour', 'thrustOptimizedContour'),
    ('Conical', 'conical'), ('cone', 'conical'),
])
def testEverySpellingResolvesToItsFamily(spelling, family):
    '''Case is not significant, and the short tokens reach the same family as the long ones.'''
    assert divergingSectionFamily(spelling) == family

@pytest.mark.parametrize('spelling', ['thrustOptimisedParabola', 'thrustOptimisedContour'])
def testTheBritishSpellingIsNoLongerAccepted(spelling):
    '''
    The resolver once took either spelling of "optimized", so a config written either way would
    load. It takes only the American one now, and the point of this test is that the change is
    visible: a config carrying the old spelling fails at load with a message naming the accepted
    set, rather than falling through to a default and building a contour of the wrong family.
    '''
    with pytest.raises(ValueError):
        divergingSectionFamily(spelling)

def testAnUnknownFamilyIsRejectedRatherThanDefaulted():
    '''
    The failure this replaces was silent: an unrecognized value fell through to the truncated
    ideal branch, so a typo produced a contour of the wrong family without saying so.
    '''
    with pytest.raises(ValueError):
        divergingSectionFamily('thrustOptimizedParabolla')

def testTheResolverIsIdempotent():
    '''Every canonical name is itself an accepted spelling, or a round trip would fail.'''
    for family in set(divergingSectionSpellings.values()):
        assert divergingSectionFamily(family) == family

#--------------------------------------------------------------------------------------------------------------------------#
# -- What a prescribed wall delivers, before any flow is solved -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.fixture(scope = 'module')
def throat():
    return ThroatGeometry(GAMMA, 1.0, 1.5, 0.382)

@pytest.fixture(scope = 'module')
def parabolaWall(throat):
    nozzleLength = LENGTH_FRACTION * conicalLength(AREA_RATIO, throat.throatRadius)
    return thrustOptimizedParabolaWall(throat.throatRadius, throat.outletCurvature, AREA_RATIO,
                                       nozzleLength, np.deg2rad(31.0), np.deg2rad(8.0))

def testTheWallEndsAtTheRequestedAreaRatio(parabolaWall):
    '''
    The design point is absorbed into the geometry rather than constrained during a solve: the
    exit radius is set when the wall is drawn, so it is exact and not iterated to.
    '''
    exitRadius, _ = parabolaWall.exitPoint[1], parabolaWall.exitPoint[0]
    assert exitRadius ** 2 == pytest.approx(AREA_RATIO, rel = 1e-12)

def testTheWallEndsAtTheRequestedLength(parabolaWall, throat):
    expected = LENGTH_FRACTION * conicalLength(AREA_RATIO, throat.throatRadius)
    assert parabolaWall.exitPoint[0] == pytest.approx(expected, rel = 1e-12)

def testTheWallLeavesTheThroatArcAtTheInflectionAngle(parabolaWall):
    '''The parabola is tangent to the arc, so the join carries no kink.'''
    arcEnd = parabolaWall.segments[0].tangentAngle(1.0)
    curveStart = parabolaWall.segments[1].tangentAngle(0.0)
    assert arcEnd == pytest.approx(curveStart, abs = 1e-12)
    assert arcEnd == pytest.approx(np.deg2rad(31.0), abs = 1e-9)

def testTheWallReachesTheExitAtTheExitAngle(parabolaWall):
    assert parabolaWall.exitAngle == pytest.approx(np.deg2rad(8.0), abs = 1e-9)

def testTheWallTurnsOnlyOneWay(parabolaWall):
    '''
    A wall whose tangent angle is not monotone has a wave in it, and the characteristics solve
    turns a wave into a compression fan that is an artefact of the drawing rather than the design.
    '''
    angles = [parabolaWall.segments[1].tangentAngle(t) for t in np.linspace(0.0, 1.0, 200)]
    assert np.all(np.diff(angles) < 1e-12)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Containment -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheParabolaDesignVectorIsAValidWall(throat):
    vector = parabolaDesignVector(throat, AREA_RATIO, LENGTH_FRACTION)
    assert isMonotoneWall(vector)

def testTheParabolaDesignVectorCarriesTheChartAngles(throat):
    '''
    The first two design variables ARE the chart angles, so the search starts at the chart
    parabola rather than near it. An optimizer started elsewhere could report a gain that is
    only the distance from its own starting point.
    '''
    from NOVA.contour import raoWallAngles
    inflection, exitAngle, _, _ = parabolaDesignVector(throat, AREA_RATIO, LENGTH_FRACTION)
    chartInflection, chartExit, _ = raoWallAngles(AREA_RATIO, LENGTH_FRACTION)
    assert inflection == pytest.approx(chartInflection, rel = 1e-12)
    assert exitAngle == pytest.approx(chartExit, rel = 1e-12)

def testTheTensionsAreInteriorToTheirBounds(throat):
    '''
    A parabola sitting on a bound would mean the search could not move off it in one direction,
    which would make the containment property useless in practice even though it holds in theory.
    '''
    _, _, inflectionTension, exitTension = parabolaDesignVector(throat, AREA_RATIO,
                                                                LENGTH_FRACTION)
    for tension in (inflectionTension, exitTension):
        assert 0.15 < tension < 0.85

def testTheCubicAtTheParabolaVectorIsTheParabola(throat, parabolaWall):
    '''
    Containment, as geometry rather than as a solve. A cubic built from the design vector has to
    trace the same points as the quadratic it was derived from, or the searched family does not
    contain the charted one.
    '''
    from NOVA.wallGeometry import bezierBellWall
    nozzleLength = LENGTH_FRACTION * conicalLength(AREA_RATIO, throat.throatRadius)
    inflection, exitAngle, inflectionTension, exitTension = parabolaDesignVector(
        throat, AREA_RATIO, LENGTH_FRACTION)
    cubic = bezierBellWall(throat.throatRadius, throat.outletCurvature, AREA_RATIO,
                           nozzleLength, inflection, exitAngle, inflectionTension, exitTension)

    quadraticX, quadraticR = parabolaWall.sample(400)
    cubicX, cubicR = cubic.sample(400)
    assert np.max(np.abs(cubicX - quadraticX)) < 1e-9
    assert np.max(np.abs(cubicR - quadraticR)) < 1e-9

#--------------------------------------------------------------------------------------------------------------------------#
# -- The internal shock, against walls that must and must not carry one -- #
#--------------------------------------------------------------------------------------------------------------------------#

def solveWall(designVariables):
    '''One searched-family solve at a fixed design point, returning the filled solution.'''
    import json
    from NOVA.Nozzle import Nozzle

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    assetPath = os.path.join(root, 'src', 'NOVA', 'assets', 'NOVANozzle.json')
    with open(assetPath, encoding = 'utf-8') as handle:
        config = json.load(handle)
    config.update({'targetExitPressure': None, 'expansionRatio': AREA_RATIO, 'Lstar': None,
                   'lengthFraction': LENGTH_FRACTION, 'plumeAmbientPressure': None,
                   'plotsEnabled': False, 'export': False, 'makeCoolingChannels': 'off'})

    scratch = os.path.join(root, 'runs', 'testContourFamilies')
    os.makedirs(scratch, exist_ok = True)
    configPath = os.path.join(scratch, 'familiesTestConfig.json')
    with open(configPath, 'w', encoding = 'utf-8') as handle:
        json.dump(config, handle, indent = 2)

    # Redirecting the output root keeps a solve from writing into the repository, and it is a
    # change to the class rather than to an instance. Leaving it in place makes every later test
    # in the session see this directory as the output root, which is how this file first broke a
    # facade test that passes on its own. Restore it whatever happens.
    originalOutputRoot = Nozzle._getOutputRoot
    try:
        Nozzle._getOutputRoot = lambda self, _base = scratch: _base
        nozzle = Nozzle()
        nozzle.setInputs(inputsPath = configPath)
        nozzle.numCharacteristicsRequested = MESH
        nozzle.thrustOptimizedContour(LENGTH_FRACTION, designVariables = designVariables)
        return nozzle.nozzleContourSolution
    finally:
        Nozzle._getOutputRoot = originalOutputRoot

@pytest.fixture(scope = 'module')
def gentleAndTurnedSolutions(throat):
    '''
    The chart parabola, and the same wall turned eight degrees harder at the inflection. One
    should carry no shock inside the nozzle and the other should.
    '''
    vector = parabolaDesignVector(throat, AREA_RATIO, LENGTH_FRACTION)
    inflection, exitAngle, inflectionTension, exitTension = vector
    turned = (inflection + np.deg2rad(8.0), exitAngle, inflectionTension, exitTension)
    return solveWall(vector), solveWall(turned)

def testTheChartParabolaCarriesNoShockInsideTheNozzle(gentleAndTurnedSolutions):
    '''
    Not a claim that a parabola never shocks. At this area ratio and length fraction it turns
    gently enough that the wall characteristics meet beyond the exit, which is no shock in the
    nozzle. Detection is a property of the design point, not of the family.
    '''
    gentle, _ = gentleAndTurnedSolutions
    assert gentle.internalShock is None

def testTurningTheWallHarderProducesAShock(gentleAndTurnedSolutions):
    _, turned = gentleAndTurnedSolutions
    assert turned.internalShock is not None
    assert turned.internalShock['peakDeflection'] > 0.0

def testAStrongFrontIsReportedAsNotWeak(gentleAndTurnedSolutions):
    '''
    The capture holds each region isentropic, which is only defensible while the front is weak.
    Eight degrees of extra turning is past that, and the solution has to say so rather than
    quietly returning a number the treatment does not support.
    '''
    _, turned = gentleAndTurnedSolutions
    assert turned.internalShock['minimumStagnationRatio'] < 1.0
    if turned.internalShock['minimumStagnationRatio'] <= 0.99:
        assert turned.internalShock['isWeak'] is False

def testAnUnresolvedFrontSaysSoRatherThanReportingANegligibleLoss(gentleAndTurnedSolutions):
    '''
    The downstream stagnation field interpolates along the front, so a front of one crossing has
    no radial extent to interpolate along and nothing is charged for it. The debit then comes back
    exactly zero, which beside a stagnation ratio near one reads as "the loss was negligible" when
    what happened is "the loss was never applied".

    `frontResolved` is what separates them, and this holds the two together: a front that is not
    resolved must report a debit of exactly zero, and a debit of exactly zero on a resolved front
    would mean something else again.
    '''
    _, turned = gentleAndTurnedSolutions
    shock = turned.internalShock
    assert shock['frontResolved'] == (shock['numCrossings'] >= 2)
    if not shock['frontResolved']:
        assert turned.shockThrustDebit == 0.0

def testTheShockCostsThrustRatherThanAddingIt(gentleAndTurnedSolutions):
    '''A stagnation pressure loss cannot raise the coefficient it is subtracted from.'''
    _, turned = gentleAndTurnedSolutions
    assert turned.shockThrustDebit is not None
    assert turned.shockThrustDebit <= 0.0
    assert turned.thrustCoef <= turned.thrustCoefWithoutShock + 1e-12
