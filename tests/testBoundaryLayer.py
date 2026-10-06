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

from NOVA.boundaryLayer import (COLESFRICTIONTABLE, bartzSkinFriction,
                                colesLowSpeedFriction, compressibleShapeFactor, offsetWall,
                                referenceTemperature, skinFrictionCoefficient,
                                solveBoundaryLayer, thicknessInteractionFactor)

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

#--------------------------------------------------------------------------------------------------------------------------#
# -- The integral energy equation and the heat transfer it carries -- #
#--------------------------------------------------------------------------------------------------------------------------#

class TestEnergyEquation:

    '''
    JPL Technical Report 32-387's integral energy equation, marched beside the momentum one, and
    von Karman's analogy closing it. This is what lets a gas-side coefficient carry boundary layer
    history, which an algebraic correlation cannot.
    '''

    def wall(self, stations = 400, converging = True):
        '''A chamber and nozzle wall with a near-wall state to march against.'''
        x = np.linspace(0.0, 0.70, stations)
        if converging:
            radius = np.where(x < 0.35, 0.075,
                              0.075 - 0.031*np.clip((x - 0.35)/0.05, 0.0, 1.0))
            radius = np.where(x > 0.40, 0.044 + 0.25*(x - 0.40), radius)
        else:
            radius = np.full_like(x, 0.075)
        area = np.pi*radius**2
        mach = np.clip(0.2*area.min()/area*4.0, 0.2, 4.0)
        temperature = 3500.0/(1.0 + 0.5*0.2*mach**2)
        pressure = 1.0e7*(temperature/3500.0)**(1.2/0.2)
        velocity = mach*np.sqrt(1.2*700.0*temperature)
        return x, radius, mach, temperature, pressure, velocity

    def testStantonReturnsHalfTheFrictionAtPrandtlOne(self):
        '''Von Karman's correction vanishes at unity Prandtl, leaving the bare analogy.'''
        from NOVA.boundaryLayer import vonKarmanStanton
        assert float(vonKarmanStanton(0.004, 1.0)) == pytest.approx(0.002, rel = 1e-12)

    def testStantonExceedsHalfTheFrictionBelowPrandtlOne(self):
        '''
        Heat diffuses faster than momentum below a Prandtl number of one, so the analogy has to
        give more heat transfer than the bare friction does, not less.
        '''
        from NOVA.boundaryLayer import vonKarmanStanton
        assert float(vonKarmanStanton(0.004, 0.7)) > 0.002

    def testTheMarchReturnsTheEnergyQuantities(self):
        '''The three new outputs exist and are finite everywhere.'''
        from NOVA.boundaryLayer import solveBoundaryLayer
        x, radius, mach, temperature, pressure, velocity = self.wall()
        layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity,
                                   1.2, 700.0, wallTemperature = 800.0)
        for key in ('energyThickness', 'stantonNumber', 'gasSideCoefficient'):
            assert key in layer
            assert np.all(np.isfinite(layer[key]))
            assert np.all(np.asarray(layer[key])[1:] > 0.0)

    def testTheEnergyThicknessGrowsAlongAConstantAreaWall(self):
        '''With no acceleration and no radius change there is nothing to thin it, so it grows.'''
        from NOVA.boundaryLayer import solveBoundaryLayer
        x, radius, mach, temperature, pressure, velocity = self.wall(converging = False)
        layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity,
                                   1.2, 700.0, wallTemperature = 800.0)
        energy = np.asarray(layer['energyThickness'])
        assert np.all(np.diff(energy) > 0.0)

    def testTheTwoThicknessesTrackEachOtherWithoutAcceleration(self):
        '''
        On a constant-area wall the momentum and energy equations differ only through the Prandtl
        correction, so the thicknesses must stay close. They separate under acceleration, and that
        separation is the physics this equation was added for.
        '''
        from NOVA.boundaryLayer import solveBoundaryLayer
        x, radius, mach, temperature, pressure, velocity = self.wall(converging = False)
        layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity,
                                   1.2, 700.0, wallTemperature = 800.0)
        ratio = np.asarray(layer['energyThickness'])[-1] / np.asarray(layer['momentumThickness'])[-1]
        assert 0.8 < ratio < 1.4

    def testAColderWallDrawsMoreHeat(self):
        '''The driving potential is the adiabatic wall temperature less the wall, so it must.'''
        from NOVA.boundaryLayer import solveBoundaryLayer
        x, radius, mach, temperature, pressure, velocity = self.wall()
        flux = []
        for wallTemperature in (400.0, 900.0):
            layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity,
                                       1.2, 700.0, wallTemperature = wallTemperature)
            recovery = temperature*(1.0 + 0.89*0.5*0.2*mach**2)
            flux.append(np.max(np.asarray(layer['gasSideCoefficient'])*(recovery - wallTemperature)))
        assert flux[0] > flux[1]

    def testTheMarchedCoefficientIsAsymmetricAboutAThroat(self):
        '''
        **The acceptance test for this method.** At matched area ratio an algebraic correlation in
        area alone gives the same heat flux either side of a throat. A marched method must not,
        because the layer arriving downstream carries the history of the throat it came through.
        The measured 40k chamber gives 0.28 to 0.79 for this ratio, at area ratios from 2.0 to 1.1.
        '''
        from NOVA.boundaryLayer import solveBoundaryLayer
        x, radius, mach, temperature, pressure, velocity = self.wall()
        layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity,
                                   1.2, 700.0, wallTemperature = 800.0)
        recovery = temperature*(1.0 + 0.89*0.5*0.2*mach**2)
        flux = np.asarray(layer['gasSideCoefficient'])*(recovery - 800.0)

        throat = int(np.argmin(radius))
        area = (radius/radius[throat])**2
        upstream, downstream = np.arange(len(x)) < throat, np.arange(len(x)) > throat
        target = 1.4
        up = float(np.interp(target, area[upstream][::-1], flux[upstream][::-1]))
        down = float(np.interp(target, area[downstream], flux[downstream]))

        assert down < up, 'the marched layer must carry less heat downstream at the same area'

#--------------------------------------------------------------------------------------------------------------------------#
# -- Bartz's thickness interaction factor -- #
#--------------------------------------------------------------------------------------------------------------------------#

class TestThicknessInteraction:

    '''
    Reynolds analogy was correlated on flows whose energy and momentum thicknesses stay near
    equal. A nozzle throat drives them apart, so Bartz NTRS 19650013685 Eq. 42 carries the ratio
    as a power.
    These are the closed forms that power has to satisfy.
    '''

    def testTheFactorIsUnityWhereTheThicknessesAreEqual(self):
        '''At equal thicknesses there is no interaction to correct for, at any exponent.'''
        for exponent in (0.0, 0.1, 3.0/28.0, 0.25):
            assert float(thicknessInteractionFactor(1.0, exponent)) == pytest.approx(1.0, rel = 1e-14)

    def testAZeroExponentRecoversTheUncorrectedAnalogy(self):
        '''Zero is the endpoint that leaves the whole quarter power on the energy thickness.'''
        for ratio in (0.3, 1.0, 5.0, 14.0):
            assert float(thicknessInteractionFactor(ratio, 0.0)) == pytest.approx(1.0, rel = 1e-14)

    def testTheFactorIsThePowerItClaimsToBe(self):
        '''The whole function is one power law, so it is checked against the arithmetic.'''
        assert float(thicknessInteractionFactor(9.0, 0.1)) == pytest.approx(9.0**0.1, rel = 1e-14)
        assert float(thicknessInteractionFactor(5.0, 3.0/28.0)) == pytest.approx(5.0**(3.0/28.0),
                                                                                 rel = 1e-14)

    def testTheFactorRaisesHeatTransferWhereTheThermalLayerIsThicker(self):
        '''
        A thermal layer thicker than the velocity layer means the friction coefficient taken at
        the energy thickness understates the heat transfer, which is the direction Bartz corrects.
        '''
        assert float(thicknessInteractionFactor(9.0, 0.1)) > 1.0
        assert float(thicknessInteractionFactor(0.5, 0.1)) < 1.0

    def testTheFactorAcceptsAnArray(self):
        '''The march stores a ratio per station, so the factor has to broadcast over them.'''
        factors = thicknessInteractionFactor(np.array([1.0, 4.0, 16.0]), 0.25)
        assert factors == pytest.approx(np.array([1.0, np.sqrt(2.0), 2.0]), rel = 1e-14)

    def testTheExponentMovesTheMarchedHeatFlux(self):
        '''
        The exponent is only worth carrying if it changes the answer, and where the thicknesses
        separate it must raise the coefficient rather than leave it alone.
        '''
        geometry = TestEnergyEquation().wall()
        x, radius, mach, temperature, pressure, velocity = geometry
        corrected, uncorrected = [
            solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, 1.2, 700.0,
                               wallTemperature = 800.0, thicknessInteractionExponent = exponent)
            for exponent in (0.1, 0.0)]

        throat = int(np.argmin(radius))
        assert np.asarray(corrected['thicknessRatio'])[throat] > 2.0
        assert (np.asarray(corrected['gasSideCoefficient'])[throat]
                > np.asarray(uncorrected['gasSideCoefficient'])[throat])
        assert np.asarray(corrected['momentumThickness']) == pytest.approx(
            np.asarray(uncorrected['momentumThickness']), rel = 1e-14), \
            'the exponent must not touch the momentum equation'

#--------------------------------------------------------------------------------------------------------------------------#
# -- The march is converged on its own grid -- #
#--------------------------------------------------------------------------------------------------------------------------#

class TestMarchConvergence:

    '''
    Forward Euler at a contour's own station spacing is not converged through a throat, where the
    fractional thinning rate of the momentum thickness reaches 100 per metre. The march therefore
    subdivides each interval it is given, and these tests hold it to that.
    '''

    def coarseWall(self, stations = 40):
        '''A deliberately coarse throat, which is what the convergence has to survive.'''
        return TestEnergyEquation().wall(stations = stations)

    def testTheArraysComeBackAtTheStationsSupplied(self):
        '''
        The march reports on the grid it was handed whatever it subdivided internally, because
        every caller indexes these arrays against its own contour.
        '''
        x, radius, mach, temperature, pressure, velocity = self.coarseWall()
        layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, 1.2, 700.0,
                                   wallTemperature = 800.0, marchSubsteps = 16)
        for key in ('momentumThickness', 'energyThickness', 'thicknessRatio',
                    'displacementThickness', 'frictionCoefficient', 'stantonNumber',
                    'gasSideCoefficient', 'wallShear'):
            assert np.asarray(layer[key]).shape == x.shape, key

    def testRefiningTheMarchConverges(self):
        '''
        Doubling the subdivision from the default must not move the drag, which is the statement
        that the default is converged rather than merely finer than the contour.
        '''
        x, radius, mach, temperature, pressure, velocity = self.coarseWall()
        drags = []
        for substeps in (32, 64, 128):
            layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity,
                                       1.2, 700.0, wallTemperature = 800.0,
                                       marchSubsteps = substeps)
            drags.append(layer['divergingDragForce'])
        assert drags[1] == pytest.approx(drags[0], rel = 0.01)
        assert drags[2] == pytest.approx(drags[1], rel = 0.005)

    def testMarchingOnTheStationsAsGivenOverstatesTheDrag(self):
        '''
        The reason the refinement exists. One subdivision marches the contour's own spacing, which
        over-thins the momentum thickness through the throat and so overstates the friction. The
        test records the direction and that the error is large enough to matter.
        '''
        x, radius, mach, temperature, pressure, velocity = self.coarseWall()
        unrefined, refined = [
            solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, 1.2, 700.0,
                               wallTemperature = 800.0, marchSubsteps = substeps)
            for substeps in (1, 64)]

        throat = int(np.argmin(radius))
        assert (np.asarray(unrefined['momentumThickness'])[throat]
                < np.asarray(refined['momentumThickness'])[throat])
        assert unrefined['divergingDragForce'] > refined['divergingDragForce']

    def testASingleSubstepMarchesTheStationsAsGiven(self):
        '''One subdivision has to be the unrefined march exactly, not an approximation of it.'''
        x, radius, mach, temperature, pressure, velocity = self.coarseWall()
        single = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, 1.2, 700.0,
                                    wallTemperature = 800.0, marchSubsteps = 1)
        zero = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, 1.2, 700.0,
                                  wallTemperature = 800.0, marchSubsteps = 0)
        assert np.asarray(zero['momentumThickness']) == pytest.approx(
            np.asarray(single['momentumThickness']), rel = 1e-14)

    def testARepeatedStationCarriesBothThicknesses(self):
        '''
        A zero-width interval advances neither equation, and leaving the energy thickness at its
        allocated zero would send the Stanton number to the floor at the next station.
        '''
        x, radius, mach, temperature, pressure, velocity = self.coarseWall(stations = 20)
        x = np.insert(x, 10, x[10])
        radius = np.insert(radius, 10, radius[10])
        mach = np.insert(mach, 10, mach[10])
        temperature = np.insert(temperature, 10, temperature[10])
        pressure = np.insert(pressure, 10, pressure[10])
        velocity = np.insert(velocity, 10, velocity[10])
        layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, 1.2, 700.0,
                                   wallTemperature = 800.0)
        energy = np.asarray(layer['energyThickness'])
        assert np.all(energy > 0.0)
        assert np.all(np.isfinite(np.asarray(layer['gasSideCoefficient'])))

#--------------------------------------------------------------------------------------------------------------------------#
# -- The drag is split at the throat -- #
#--------------------------------------------------------------------------------------------------------------------------#

class TestDragSplit:

    '''
    Only the diverging section's friction is a debit against exit thrust. What the subsonic wall
    takes is a chamber momentum loss, and charging it against exit momentum would be the wrong
    bookkeeping, so the march reports the two separately.
    '''

    def testTheTwoSharesSumToTheWhole(self):
        '''
        Split at the minimum radius, the two integrals cover every interval exactly once, so they
        have to add to the whole-wall drag to machine precision.
        '''
        x, radius, mach, temperature, pressure, velocity = TestEnergyEquation().wall()
        layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, 1.2, 700.0,
                                   wallTemperature = 800.0)
        assert (layer['divergingDragForce'] + layer['chamberDragForce']
                == pytest.approx(layer['dragForce'], rel = 1e-12))

    def testTheSplitIsAtTheMinimumRadius(self):
        '''
        Where the split falls is the whole content of the bookkeeping, so it is checked against an
        independent integral of the returned wall shear rather than taken on trust.
        '''
        x, radius, mach, temperature, pressure, velocity = TestEnergyEquation().wall()
        layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, 1.2, 700.0,
                                   wallTemperature = 800.0, marchSubsteps = 1)
        throat = int(np.argmin(radius))
        load = np.asarray(layer['wallShear'])*2.0*np.pi*radius
        arc = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(radius)))])
        assert layer['chamberDragForce'] == pytest.approx(
            float(np.trapezoid(load[:throat + 1], arc[:throat + 1])), rel = 1e-12)
        assert layer['divergingDragForce'] == pytest.approx(
            float(np.trapezoid(load[throat:], arc[throat:])), rel = 1e-12)
        assert layer['chamberDragForce'] > 0.0

    def testAWallWithNoChamberPutsEverythingInTheDivergingShare(self):
        '''
        Handed a wall whose first station is its narrowest, there is nothing upstream of the
        throat and the chamber share has to be zero rather than a sliver of the first interval.
        '''
        x, radius, mach, temperature, pressure, velocity = TestEnergyEquation().wall()
        throat = int(np.argmin(radius))
        layer = solveBoundaryLayer(x[throat:], radius[throat:], mach[throat:], temperature[throat:],
                                   pressure[throat:], velocity[throat:], 1.2, 700.0,
                                   wallTemperature = 800.0)
        assert layer['chamberDragForce'] == pytest.approx(0.0, abs = 1e-12)
        assert layer['divergingDragForce'] == pytest.approx(layer['dragForce'], rel = 1e-12)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Coles' skin friction, as Bartz uses it -- #
#--------------------------------------------------------------------------------------------------------------------------#

class TestColesFriction:

    '''
    Bartz publishes Coles' correlation three ways: Table A-1 over the turbulent range, Eq. A-4
    above it and Eq. A-5 below it. The table is given against the product of the friction
    coefficient and the Reynolds number, so dividing each row by its coefficient recovers a plain
    Reynolds number and the three pieces have to agree where they meet.
    '''

    def tableReynolds(self):
        '''Each published row recast as the Reynolds number it corresponds to.'''
        return [(product/friction, friction) for product, friction in COLESFRICTIONTABLE]

    def testEachPublishedRowIsReturned(self):
        '''The interpolation has to pass through every tabulated point, not near it.'''
        for reynolds, friction in self.tableReynolds():
            assert colesLowSpeedFriction(reynolds) == pytest.approx(friction, rel = 1e-9)

    def testTheLowEndClosedFormJoinsTheTable(self):
        '''
        Eq. A-5 covers Reynolds numbers below the table. Solved for the coefficient it has to
        return the table's first row at the Reynolds number where the two meet.
        '''
        reynolds, friction = self.tableReynolds()[0]
        assert colesLowSpeedFriction(0.999*reynolds) == pytest.approx(friction, rel = 2e-3)

    def testTheHighEndClosedFormJoinsTheTable(self):
        '''
        Eq. A-4 covers Reynolds numbers above the table. It is a logarithmic law and the table is
        tabulated data, so they are independent statements that have to agree where they meet.
        '''
        reynolds, friction = self.tableReynolds()[-1]
        assert colesLowSpeedFriction(1.001*reynolds) == pytest.approx(friction, rel = 5e-3)

    def testFrictionFallsWithReynoldsNumber(self):
        '''A friction law that is not monotone in Reynolds number is wrong.'''
        values = [colesLowSpeedFriction(r) for r in (300.0, 1e3, 1e4, 1e5, 1e6, 1e7)]
        assert all(a > b for a, b in zip(values, values[1:]))

    def testBlasiusAgreesWhereBartzSaysItDoes(self):
        '''
        Bartz states the Blasius equation he uses for illustration is within 5 percent of Coles
        between Reynolds numbers of 400 and 15 000. Reproducing that bound is the check that the
        table has been transcribed correctly, since it is his claim about his own numbers.
        '''
        for reynolds in (400.0, 1000.0, 3000.0, 7000.0, 12000.0, 15000.0):
            blasius = 0.0256/reynolds**0.25
            assert blasius == pytest.approx(colesLowSpeedFriction(reynolds), rel = 0.056)

    def testBlasiusDivergesAboveThatRange(self):
        '''
        The reason the correlation is worth carrying. A fixed quarter power cannot follow a
        logarithmic law, so the two separate at the Reynolds numbers a large engine reaches.
        '''
        assert 0.0256/1e6**0.25 < 0.7*colesLowSpeedFriction(1e6)

class TestBartzWallProperties:

    '''
    Bartz offers two answers for carrying Coles' adiabatic correlation to a cooled wall, and
    states that the relationship is uncertain for severely cooled layers. Both are implemented and
    neither is preferred here.
    '''

    def testBothAssumptionsReduceToTheLowSpeedValue(self):
        '''
        With no heat transfer and no compressibility there is nothing for either assumption to
        correct, so both have to return Coles' coefficient itself. This is the strongest available
        check on the two correction factors, because they are built from different quantities and
        have to agree exactly here.
        '''
        temperature = 1000.0
        expected = colesLowSpeedFriction(5000.0)
        for assumption in ('adiabatic', 'film'):
            friction = bartzSkinFriction(5000.0, temperature, temperature, temperature,
                                         temperature, 0.6, assumption)
            assert friction == pytest.approx(expected, rel = 1e-6), assumption

    def testCoolingRaisesTheFilmPropertyCoefficient(self):
        '''
        A cold wall carries denser gas, so the coefficient referred to edge dynamic pressure has to
        rise. The reference-temperature method in this module carries the same effect, and the two
        agreeing in direction is the only thing they are checked against each other for.
        '''
        hot = bartzSkinFriction(5000.0, 3000.0, 3200.0, 3150.0, 3150.0, 0.6, 'film')
        cold = bartzSkinFriction(5000.0, 3000.0, 3200.0, 3150.0, 600.0, 0.6, 'film')
        assert cold > hot

    def testTheClosuresAreSelectable(self):
        '''Every named closure has to run the march and return finite heat transfer.'''
        geometry = TestEnergyEquation().wall()
        x, radius, mach, temperature, pressure, velocity = geometry
        for closure in ('referenceTemperature', 'colesFilm', 'colesAdiabatic'):
            layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, 1.2,
                                       700.0, wallTemperature = 800.0, frictionClosure = closure)
            assert np.all(np.isfinite(np.asarray(layer['gasSideCoefficient'])))
            assert np.all(np.asarray(layer['frictionCoefficient'])[1:] > 0.0)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The wall is longer than its axial projection -- #
#--------------------------------------------------------------------------------------------------------------------------#

class TestWallInclination:

    '''
    Friction and heat act over the wall. A march that steps axially therefore carries both source
    terms multiplied by ds/dx, which is the radical in JPL 32-387 Eqs. 25 and 30.
    '''

    def cone(self, slope, stations = 400):
        '''A straight cone of a given slope, at a fixed edge state so only geometry differs.'''
        x = np.linspace(0.0, 0.5, stations)
        radius = 0.05 + slope*x
        mach = np.full_like(x, 2.0)
        temperature = np.full_like(x, 2000.0)
        pressure = np.full_like(x, 1.0e6)
        velocity = mach*np.sqrt(1.2*700.0*temperature)
        return x, radius, mach, temperature, pressure, velocity

    def testAFlatWallIsUnaffected(self):
        '''
        At zero slope the factor is exactly one, so a constant-radius wall must march identically
        whether the term is carried or not. This is what fixes the term's magnitude rather than
        only its sign.
        '''
        x, radius, mach, temperature, pressure, velocity = self.cone(0.0)
        layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, 1.2, 700.0,
                                   wallTemperature = 800.0, marchSubsteps = 1)
        # With no gradients at all the momentum equation is dtheta/dx = cf/2 exactly.
        growth = np.diff(np.asarray(layer['momentumThickness']))
        expected = 0.5*np.asarray(layer['frictionCoefficient'])[:-1]*np.diff(x)
        assert growth == pytest.approx(expected, rel = 1e-9)

    @pytest.mark.parametrize('slope', [0.0, 0.5, 1.0])
    def testTheFirstStepMatchesHandArithmetic(self, slope):
        '''
        The whole momentum equation at the first station of a cone, against the arithmetic written
        out. At a constant edge state the velocity gradient vanishes, leaving the friction source
        carrying ds/dx against the radius term that stretches the layer over a growing
        circumference. A wrong inclination factor cannot survive three slopes.
        '''
        x, radius, mach, temperature, pressure, velocity = self.cone(slope)
        layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, 1.2, 700.0,
                                   wallTemperature = 800.0, marchSubsteps = 1)
        thickness = np.asarray(layer['momentumThickness'])
        friction = np.asarray(layer['frictionCoefficient'])
        step = x[1] - x[0]

        inclination = np.sqrt(1.0 + slope**2)
        radiusGradient = (radius[1] - radius[0])/step/radius[0]
        expected = (0.5*friction[0]*inclination - thickness[0]*radiusGradient)*step
        assert thickness[1] - thickness[0] == pytest.approx(expected, rel = 1e-12)

    def testAnInclinedWallCollectsMoreFriction(self):
        '''
        The direction the factor exists for. Holding the edge state and the starting thickness
        fixed, a steeper wall has more area per unit axial distance and so more wall shear.
        '''
        sources = []
        for slope in (0.0, 1.0):
            x, radius, mach, temperature, pressure, velocity = self.cone(slope)
            layer = solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, 1.2,
                                       700.0, wallTemperature = 800.0, marchSubsteps = 1)
            step = x[1] - x[0]
            radiusGradient = (radius[1] - radius[0])/step/radius[0]
            thickness = np.asarray(layer['momentumThickness'])
            # Back out the source alone by adding the stretching term that worked against it.
            sources.append((thickness[1] - thickness[0])/step + thickness[0]*radiusGradient)
        assert sources[1] == pytest.approx(np.sqrt(2.0)*sources[0], rel = 1e-9)
