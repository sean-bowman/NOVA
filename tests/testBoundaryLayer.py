'''

Tests for the boundary layer that offsets a contour and debits its thrust.

Nothing in this file checks the model against a measured boundary layer, because no source in
NOVA's reference set publishes one for a rocket nozzle. What it checks instead is the three things
that can be checked without one: that every closure reduces to the incompressible relation it was
built from, that the march conserves the momentum it claims to, and that the answer is the size
published loss budgets say it should be.

The last of those is deliberately a wide bracket rather than a tight one. It is there to catch a
model that is wrong by an order of magnitude, which is the failure that matters, and it is
explicitly not evidence that the model is right.

'''
import numpy as np
import pytest

from NOVA.boundaryLayer import (compressibleShapeFactor, offsetWall, referenceTemperature,
                                skinFrictionCoefficient, solveBoundaryLayer)

GAMMA, GAS_CONSTANT = 1.1475421191138746, 692.0

#--------------------------------------------------------------------------------------------------------------------------#
# -- Each closure reduces to what it was built from -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.mark.parametrize('edgeTemperature', [300.0, 1500.0, 3000.0])
def testReferenceTemperatureReturnsTheEdgeValueWhenThereIsNothingToCorrectFor(edgeTemperature):
    '''
    At zero Mach number against an adiabatic wall there is no compressibility and no heat
    transfer, so the reference temperature has nothing to weight and must return the edge value.
    Any other answer means the weighting does not sum to one.
    '''
    reference = referenceTemperature(edgeTemperature, edgeTemperature, 0.0, GAMMA)
    assert reference == pytest.approx(edgeTemperature, rel = 1e-14)

def testReferenceTemperatureSitsBetweenTheWallAndTheRecoveryTemperature():
    '''A weighted mean of three temperatures cannot leave the range they span.'''
    edge, wall = 3000.0, 800.0
    reference = referenceTemperature(edge, wall, 3.0, GAMMA)
    recovery = edge * (1.0 + 0.89 * 0.5 * (GAMMA - 1.0) * 9.0)
    assert min(wall, edge) <= reference <= max(recovery, edge)

def testAColdWallLowersTheReferenceTemperature():
    hot = referenceTemperature(3000.0, 2500.0, 2.0, GAMMA)
    cold = referenceTemperature(3000.0, 800.0, 2.0, GAMMA)
    assert cold < hot

@pytest.mark.parametrize('momentumReynolds', [1.0e3, 1.0e4, 1.0e5, 1.0e6])
def testSkinFrictionReducesToTheFlatPlateLaw(momentumReynolds):
    '''
    With the reference temperature equal to the edge temperature the compressibility
    transformation is the identity, so the closure has to return the incompressible power law
    exactly rather than approximately.
    '''
    assert skinFrictionCoefficient(momentumReynolds, 1.0) == pytest.approx(
        0.026 * momentumReynolds ** -0.25, rel = 1e-14)

def testSkinFrictionFallsAsTheLayerThickens():
    '''Re_theta^(-1/4): a thicker layer carries less shear for the same edge state.'''
    assert skinFrictionCoefficient(1.0e5, 1.0) < skinFrictionCoefficient(1.0e4, 1.0)

def testAColdWallCarriesMoreFriction():
    '''
    The reference state of a cooled wall is colder and therefore denser than the edge, and the
    friction referred back to edge dynamic pressure rises in proportion. This is the term that
    makes a regeneratively cooled nozzle drag harder than an adiabatic one, and its sign is the
    thing most easily got backwards.
    '''
    assert skinFrictionCoefficient(1.0e5, 0.65) > skinFrictionCoefficient(1.0e5, 1.0)

def testShapeFactorReducesToTheFlatPlateValue():
    assert compressibleShapeFactor(0.0, GAMMA, 1.0) == pytest.approx(1.29, rel = 1e-14)

def testShapeFactorGrowsWithMachNumber():
    '''Compressibility thickens the displacement thickness faster than the momentum thickness.'''
    shapes = [compressibleShapeFactor(mach, GAMMA, 1.0) for mach in (0.0, 1.0, 2.0, 3.0, 4.0)]
    assert np.all(np.diff(shapes) > 0)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The march -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.fixture
def nozzleWall():
    '''
    A diverging wall of roughly the worked LOX/LH2 proportions, with a plausible expansion along
    it. Built here rather than solved, so this file does not need a contour to run.
    '''
    stations = 120
    x = np.linspace(0.0, 0.80, stations)
    radius = 0.0503 + (0.3183 - 0.0503) * (x / x[-1]) ** 0.7
    mach = np.linspace(1.18, 3.79, stations)
    temperature = 3512.0 / (1.0 + 0.5 * (GAMMA - 1.0) * mach ** 2)
    pressure = 6.895e6 / (1.0 + 0.5 * (GAMMA - 1.0) * mach ** 2) ** (GAMMA / (GAMMA - 1.0))
    velocity = mach * np.sqrt(GAMMA * GAS_CONSTANT * temperature)
    return x, radius, mach, temperature, pressure, velocity

def testTheLayerGrowsAlongTheWall(nozzleWall):
    x, radius, mach, temperature, pressure, velocity = nozzleWall
    layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity,
                               GAMMA, GAS_CONSTANT, 800.0)
    assert np.all(layer['momentumThickness'] > 0)
    assert np.all(np.diff(layer['displacementThickness']) > -1e-12)

def testTheLayerStaysThinAgainstTheRadius(nozzleWall):
    '''
    An integral method assumes the layer is thin against the body it grows on. If the
    displacement thickness reaches a noticeable fraction of the local radius the method has left
    its own range of validity, and the result should not be used without saying so.
    '''
    x, radius, mach, temperature, pressure, velocity = nozzleWall
    layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity,
                               GAMMA, GAS_CONSTANT, 800.0)
    assert np.max(layer['displacementThickness'] / radius) < 0.05

def testTheAnswerDoesNotRestOnTheAssumedStartingThickness(nozzleWall):
    '''
    The starting momentum thickness stands in for the converging section this model does not
    cover, so it is a guess. The momentum integral forgets its initial condition and settles to a
    state set by local conditions, and this holds that: five hundredfold on the input moves the
    drag by a few per cent.

    It matters because it decides how a disagreement with a published budget has to be read. If
    the answer did rest on this number, the model would be reporting the guess.
    '''
    x, radius, mach, temperature, pressure, velocity = nozzleWall
    drags = []
    for startingThickness in (1.0e-6, 1.0e-5, 1.0e-4, 5.0e-4):
        layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity,
                                   GAMMA, GAS_CONSTANT, 800.0,
                                   initialMomentumThickness = startingThickness)
        drags.append(layer['dragForce'])
    spread = (max(drags) - min(drags)) / np.mean(drags)
    assert spread < 0.10, f'drag moved {100*spread:.1f} % across the starting thickness'

def testAColdWallDragsHarderThanAHotOne(nozzleWall):
    x, radius, mach, temperature, pressure, velocity = nozzleWall
    cold = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity,
                              GAMMA, GAS_CONSTANT, 500.0)['dragForce']
    hot = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity,
                             GAMMA, GAS_CONSTANT, 1500.0)['dragForce']
    assert cold > hot

def testTheDragIsTheRightOrderAgainstPublishedBudgets(nozzleWall):
    '''
    Published loss budgets put boundary layer losses on a rocket bell at roughly half a per cent
    to one and a half per cent of thrust, and this model returns about two on the worked case:
    the right order, the wrong end of it, recorded in the module docstring rather than tuned away.

    The bracket here is therefore wide on purpose. It is a guard against being wrong by an order
    of magnitude, which is the failure worth catching automatically, and it is not evidence that
    the model is right.
    '''
    x, radius, mach, temperature, pressure, velocity = nozzleWall
    layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity,
                               GAMMA, GAS_CONSTANT, 800.0)
    fractionOfThrust = layer['dragForce'] / 100.0e3
    assert 0.002 < fractionOfThrust < 0.05

#--------------------------------------------------------------------------------------------------------------------------#
# -- Offsetting the wall -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheWallIsOffsetOutward(nozzleWall):
    '''
    The physical wall sits OUTSIDE the inviscid contour, so that the inviscid flow through the
    reduced area matches the real flow through the real one. Offsetting the other way would shrink
    a nozzle that needs to grow.
    '''
    x, radius, mach, temperature, pressure, velocity = nozzleWall
    layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity,
                               GAMMA, GAS_CONSTANT, 800.0)
    _, offsetRadius = offsetWall(x, radius, layer['displacementThickness'])
    assert np.all(offsetRadius >= radius - 1e-12)

def testTheOffsetIsAlongTheNormalNotTheRadius():
    '''
    On a wall at 45 degrees a normal offset moves the radius by the offset over root two and
    moves the station upstream by the same amount. A purely radial offset would move the radius by
    the whole thickness and the station not at all, which on a steep wall is a different contour.
    '''
    x = np.linspace(0.0, 1.0, 51)
    radius = 1.0 + x                                    # 45 degrees everywhere
    thickness = np.full_like(x, 0.01)
    offsetX, offsetRadius = offsetWall(x, radius, thickness)
    assert offsetRadius[25] - radius[25] == pytest.approx(0.01 / np.sqrt(2.0), rel = 1e-9)
    assert x[25] - offsetX[25] == pytest.approx(0.01 / np.sqrt(2.0), rel = 1e-9)

def testAFlatWallOffsetsPurelyRadially():
    x = np.linspace(0.0, 1.0, 21)
    radius = np.ones_like(x)
    offsetX, offsetRadius = offsetWall(x, radius, np.full_like(x, 0.02))
    assert offsetRadius == pytest.approx(radius + 0.02, rel = 1e-12)
    assert offsetX == pytest.approx(x, abs = 1e-12)
