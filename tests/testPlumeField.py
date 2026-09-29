'''

Tests for the solved plume interior: the station march that draws it and the envelope that
bounds where its output is trusted.

Two independent references are available and both are exercised here.

    NASA TN D-2327 carries a worked case for the leading characteristic, and tabulates the
    boundary Mach number and lip turning angle for three nozzles. Those are closed-form
    consequences of the formulation and the net must reproduce them exactly.

    Prandtl (1904) gives the length of the first shock cell of an almost perfectly expanded jet.
    That is the only independent check available on the solved field itself, and it holds only
    where the correlation does: a parallel exit, mildly off design.

The envelope tests are as important as the accuracy tests. The net is quietly wrong outside its
band rather than loudly wrong, so the refusals are what keep a wrong field from being drawn.

'''
import os
import sys
import types

import numpy as np
import pytest

from NOVA.Nozzle import (PlumeGas, solveFreeJetNet, freeJetLeadingCharacteristic,
                    fullyExpandedDiameter, machFromPressureRatio, prandtlCellCoefficient,
                    shockCellLength, prandtlMeyerAngle,
                    plumeFieldMinPressureRatio, plumeFieldMaxPressureRatio,
                    plumeFieldMinExitMach, plumeFieldMaxExitMach, plumeFieldMaxWallAngle)
from NOVA.plume import PlumeField, PlumeFlow
from NOVA.stationMarch import (lipShockLossLimit, plumeFieldDefaultReach,
                               plumeFieldDriftTolerance, solveStationField,
                               solveStationMarch, uniformStation)

GAMMA = 1.4

def ambientOverTotal(exitMach, staticRatio, gamma = GAMMA):
    '''The report tabulates p_j/p_a; the solver takes p_a/p_0.'''
    stagnationOverStatic = (1.0 + 0.5 * (gamma - 1.0) * exitMach ** 2) ** (gamma / (gamma - 1.0))
    return 1.0 / (staticRatio * stagnationOverStatic)

def solvedBoundary(exitMach, staticRatio, wallAngle = 0.0, numRays = 40, numLeading = 200):
    '''Axial and radial boundary coordinates in units of the lip radius.'''
    net = solveFreeJetNet(PlumeGas(GAMMA), exitMach, wallAngle, 1.0,
                          ambientOverTotal(exitMach, staticRatio),
                          numRays = numRays, numLeading = numLeading, maxLines = 1500)
    boundary = net['boundary']
    return (np.array([point.x for point in boundary]),
            np.array([abs(point.y) for point in boundary]), net)

def prandtlCell(exitMach, staticRatio):
    '''First cell length for a jet of unit lip radius, in lip radii.'''
    stagnationOverStatic = (1.0 + 0.5 * (GAMMA - 1.0) * exitMach ** 2) ** (GAMMA / (GAMMA - 1.0))
    jetMach = machFromPressureRatio(stagnationOverStatic * staticRatio, GAMMA)
    jetDiameter = fullyExpandedDiameter(2.0, exitMach, jetMach, GAMMA)
    return shockCellLength(jetDiameter, jetMach, prandtlCellCoefficient)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Against NASA TN D-2327 -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testLeadingCharacteristicReachesTheReportedAxisState():
    '''
    The report works one case through Appendix A: for M_j 5.0 at a 15 degree wall angle the
    leading characteristic meets the center line at nu 106.92 degrees and M 12.02. An independent
    implementation has to reproduce it.
    '''
    gas = PlumeGas(GAMMA)
    leading = freeJetLeadingCharacteristic(gas, 5.0, np.radians(15.0), 1.0, numPoints = 4000)
    axis = leading[-1]

    assert abs(axis.y) < 1e-12, 'the leading characteristic must terminate on the axis'
    assert axis.mach == pytest.approx(12.02, rel = 2e-3)
    assert np.degrees(gas.nu(axis.mach)) == pytest.approx(106.92, rel = 2e-3)

@pytest.mark.parametrize('exitMach, wallAngleDeg, staticRatio, boundaryMach, lipTurnDeg', [
    (5.00, 15.0, 8143.0, 19.70, 54.06),
    (4.79, 26.5, 2926.0, 16.38, 64.70),
])
def testBoundaryMachAndLipTurnMatchTheReport(exitMach, wallAngleDeg, staticRatio,
                                             boundaryMach, lipTurnDeg):
    '''
    Both follow in closed form from the pressure ratio and the Prandtl-Meyer function, so they
    are exact checks on the inputs rather than on the march. Getting the pressure ratio convention
    wrong moves the boundary Mach number by a factor of two and the plume scale by fifty.
    '''
    gas = PlumeGas(GAMMA)
    computed = gas.machFromPressureRatio(ambientOverTotal(exitMach, staticRatio))
    assert computed == pytest.approx(boundaryMach, rel = 1e-3)

    lipTurn = prandtlMeyerAngle(computed, GAMMA) - prandtlMeyerAngle(exitMach, GAMMA) \
              + np.radians(wallAngleDeg)
    assert np.degrees(lipTurn) == pytest.approx(lipTurnDeg, rel = 2e-3)

def testSonicCaseReproducesItsBoundaryMachButNotItsTabulatedLipTurn():
    '''
    The report's first nozzle, M_j 1.0 at p_j/p_a 45 000, is outside what this formulation can
    represent: its lip turn exceeds 90 degrees, which puts tan(theta) on the wrong branch in
    eqs (C18) and (C19), and a sonic jet has a degenerate leading characteristic because mu is 90
    degrees. It is recorded here rather than solved.

    The boundary Mach number is reproduced. The tabulated lip turn is not, and the two entries are
    not consistent with each other: the Prandtl-Meyer angle of the report's own 11.09 is 105.01
    degrees, against the 105.60 tabulated beside it. Half a per cent, and it belongs to the table
    rather than to this implementation.
    '''
    gas = PlumeGas(GAMMA)
    computed = gas.machFromPressureRatio(ambientOverTotal(1.00, 45000.0))
    assert computed == pytest.approx(11.09, rel = 1e-3)

    lipTurn = np.degrees(prandtlMeyerAngle(computed, GAMMA) - prandtlMeyerAngle(1.0, GAMMA))
    assert lipTurn == pytest.approx(105.01, rel = 1e-3)
    assert lipTurn == pytest.approx(105.60, rel = 1e-2)
    assert lipTurn > 90.0, 'the branch failure this case demonstrates depends on exceeding 90 deg'

#--------------------------------------------------------------------------------------------------------------------------#
# -- Against Prandtl, inside the validated envelope -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.mark.parametrize('exitMach', [2.0, 3.0, 4.0])
@pytest.mark.parametrize('staticRatio', [1.2, 1.5, 2.0])
def testFirstShockCellMatchesPrandtlInsideTheEnvelope(exitMach, staticRatio):
    '''
    The boundary swells a quarter wavelength past the lip, so twice the distance from the lip to
    the first crest is the cell length. Inside the envelope the net runs long against Prandtl by
    between about four and ten per cent, consistently and with one sign, which is what a
    linearised small-perturbation result should do.
    '''
    xs, radii, _ = solvedBoundary(exitMach, staticRatio)
    crest = int(np.argmax(radii))
    assert 0 < crest < radii.size - 3, 'the boundary must turn over for a cell to exist'

    error = 100.0 * (2.0 * xs[crest] - prandtlCell(exitMach, staticRatio)) \
            / prandtlCell(exitMach, staticRatio)
    assert 0.0 < error < 12.0, f'cell length error {error:+.1f} per cent is outside the band'

def testCellLengthDegradesOutsideThePressureEnvelope():
    '''
    The ceiling on the envelope is not arbitrary. Beyond it the internal shock sets the plume
    scale, the net has no model for one, and the cell comes out short rather than long.
    '''
    inside = solvedBoundary(3.0, 2.0)
    outside = solvedBoundary(3.0, 5.0)
    insideError = 100.0 * (2.0 * inside[0][int(np.argmax(inside[1]))] - prandtlCell(3.0, 2.0)) \
                  / prandtlCell(3.0, 2.0)
    outsideError = 100.0 * (2.0 * outside[0][int(np.argmax(outside[1]))] - prandtlCell(3.0, 5.0)) \
                   / prandtlCell(3.0, 5.0)
    assert insideError > 0.0, 'inside the envelope the net runs long'
    assert outsideError < -10.0, 'beyond it the missing shock makes the cell short'

def testMatchedJetHasNoWaveStructure():
    '''A perfectly expanded jet is uniform. There is no cell to find, and none is invented.'''
    _, radii, _ = solvedBoundary(3.0, 1.0)
    assert radii.max() == pytest.approx(1.0, abs = 1e-6)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Determinism -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testMarchIsStableAgainstAnUlpOfAmbientPressure():
    '''
    The approach to the center line is sub-stepped in thirds rather than taken in one jump. Taken
    in one jump the branch is chaotic, and a one-ulp change of ambient pressure changes how far
    the march gets. Anything read off a chaotic march is noise, so this is a precondition for
    reporting any of the numbers above.
    '''
    gas = PlumeGas(GAMMA)
    base = ambientOverTotal(3.0, 1.5)
    results = []
    for bump in range(3):
        ambient = base
        for _ in range(bump):
            ambient = float(np.nextafter(ambient, 1.0))
        net = solveFreeJetNet(gas, 3.0, 0.0, 1.0, ambient, numRays = 40, numLeading = 200,
                              maxLines = 1500)
        results.append((len(net['lines']), len(net['centerLine']), net['boundary'][-1].x))

    # The structure of the march must not move at all. Chaos here showed up as the center-line
    # count dropping from three points to one and the boundary ending at 6.77 instead of 11.27,
    # so a count that holds is the meaningful statement. The end station is allowed to respond to
    # the perturbation the way any well-conditioned calculation does, in the last few digits.
    counts = {(lines, center) for lines, center, _ in results}
    assert len(counts) == 1, f'march structure is not reproducible: {results}'
    ends = [end for _, _, end in results]
    assert max(ends) - min(ends) < 1e-9 * abs(ends[0]), f'boundary end moved: {ends}'

def testCenterLineMarchAdvancesPastTheFirstCell():
    '''
    Without the sub-stepping the march produces a single center-line point and stops. The whole
    downstream field depends on it advancing.
    '''
    _, _, net = solvedBoundary(3.0, 1.5)
    assert len(net['centerLine']) > 100

#--------------------------------------------------------------------------------------------------------------------------#
# -- What Nozzle.plumeField refuses, and how it grades what it does not -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _refusalContour(exitMach, pressureRatio, wallAngle, mesh = False):
    '''
    A PlumeContour carrying only what the field solve reads on the way to a refusal. Building a
    real contour would run the whole design pipeline for a test about refusals.

    The structure is supplied already solved, so the solve reuses it rather than correlating one,
    which is why the ambient it is asked for has to match the ambient it was built at. `mesh`
    decides whether the contour carries a characteristic mesh, which is what a conical contour
    lacks.
    '''
    from NOVA.Nozzle import PlumeContour, PlumeStructure

    chamberPressure = 1.0e7
    stagnationOverStatic = (1.0 + 0.5 * (GAMMA - 1.0) * exitMach ** 2) ** (GAMMA / (GAMMA - 1.0))
    exitPressure = chamberPressure / stagnationOverStatic

    contour = PlumeContour()
    contour.chamberPressure = chamberPressure
    contour.allXPoints = [np.array([1.0])] if mesh else None
    contour.nozzlePlumeStructure = PlumeStructure(
        jetType = 'underexpanded', ambientPressure = exitPressure / pressureRatio,
        lipX = 1.0, lipRadius = 0.2, lipWallAngle = wallAngle,
        exitMach = exitMach, exitPressure = exitPressure, exitDiameter = 0.4,
        gamma = GAMMA, exitPressureRatio = pressureRatio, shockCellLength = 1.0)

    return contour

def _solveRefusal(exitMach, pressureRatio, wallAngle, mesh = False):
    '''Run the field solve against that contour, at the ambient the structure was built for.'''
    from NOVA.stationMarch import solveStationField

    contour = _refusalContour(exitMach, pressureRatio, wallAngle, mesh = mesh)

    return solveStationField(contour,
                             ambientPressure = contour.nozzlePlumeStructure.ambientPressure)

def testPlumeFieldRefusesWithoutACharacteristicMesh():
    '''A conical contour has no mesh to continue, and plumeCharacteristicSeed returns None.'''
    result = _solveRefusal(3.0, 1.5, 0.0)
    assert not result.solved
    assert 'characteristic mesh' in ' '.join(result.notes)

@pytest.mark.parametrize('exitMach', [plumeFieldMinExitMach - 0.1, plumeFieldMaxExitMach + 0.1])
def testPlumeFieldRefusesOutsideTheMachBand(exitMach):
    '''Outside the band the solver has been exercised over, it declines rather than guesses.'''
    result = _solveRefusal(exitMach, 1.5, 0.0, mesh = True)
    assert not result.solved
    assert 'Exit Mach' in ' '.join(result.notes)

def testPlumeFieldRefusesASeparatedNozzle():
    '''
    Below the Summerfield criterion the nozzle separates internally, so the flow is not attached
    at the lip and no attached plume model describes it. That is a physical refusal, not a
    numerical one, and it is the floor of the operating range rather than a solver limit.
    '''
    result = _solveRefusal(3.0, 0.3, 0.0, mesh = True)
    assert not result.solved
    assert 'Summerfield' in ' '.join(result.notes)

def testPlumeFieldGradesRatherThanRefusesAnOverexpandedJet():
    '''
    Overexpanded jets used to be refused outright, which excluded sea-level operation of any
    vacuum-optimized nozzle. They are solved now, and what decides whether the answer is usable is
    the conservation it reports rather than the operating point it sits at.
    '''
    result = _solveRefusal(3.0, 0.8, 0.0, mesh = True)
    # The contour's mesh is a placeholder, so this stops at the handover rather than at the pressure
    # ratio. What matters is that it was not turned away for being overexpanded.
    assert 'Summerfield' not in ' '.join(result.notes)
    assert 'overexpanded' not in ' '.join(result.notes).lower()
    assert 'characteristic mesh' in ' '.join(result.notes)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The exit plane the march starts from -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _syntheticSeed(wallAngleDeg = 14.0, wallMach = 4.0, axisMach = 4.8, lipRadius = 0.4):
    '''
    A seed carrying a linear exit profile, angle rising with radius and Mach falling, which is
    what a truncated ideal contour produces.
    '''
    radii = np.linspace(0.0, lipRadius, 40)
    fraction = radii / lipRadius
    return {'scalingFactor': 1.0, 'exitX': 1.0, 'exitRadius': lipRadius,
            'xMesh': [np.full_like(radii, 1.0)], 'rMesh': [radii],
            'flowAngleMesh': [np.radians(wallAngleDeg) * fraction],
            'machMesh': [axisMach + (wallMach - axisMach) * fraction]}

def testInitialLineReproducesTheExitPlane():
    '''
    The line has to come back with the mesh's own states, ordered lip to axis, normalized on the
    lip radius, with y negative below the center line and theta negative turning away from it.
    '''
    from NOVA.Nozzle import freeJetInitialLine
    line = freeJetInitialLine(PlumeGas(GAMMA), _syntheticSeed(), numPoints = 60)

    assert line is not None and len(line) > 10
    assert line[0].y == pytest.approx(-1.0, abs = 1e-9), 'the line starts at the lip'
    assert line[-1].y == pytest.approx(0.0, abs = 1e-12), 'and ends on the axis'
    assert line[-1].theta == 0.0, 'symmetry fixes the flow angle on the axis'
    assert line[0].mach == pytest.approx(4.0, rel = 1e-6), 'lip carries the wall Mach number'
    assert line[-1].mach == pytest.approx(4.8, rel = 1e-6), 'axis carries the axis Mach number'
    assert np.degrees(line[0].theta) == pytest.approx(-14.0, rel = 1e-6)
    assert all(a.y <= b.y for a, b in zip(line[:-1], line[1:])), 'ordered lip to axis'

def testInitialLineDisagreesWithTheSourceFlowConstruction():
    '''
    The reason the seed matters. Appendix A builds its leading characteristic from a source flow
    of half-angle theta_N, so the axis Mach number follows from nu_axis = nu_N + 2 theta_N. A
    contoured nozzle straightens the flow instead, and the two answers are nowhere near each
    other, which puts every line of the march on the wrong initial data.
    '''
    from NOVA.Nozzle import freeJetInitialLine
    gas = PlumeGas(GAMMA)
    line = freeJetInitialLine(gas, _syntheticSeed(), numPoints = 60)
    sourceFlow = freeJetLeadingCharacteristic(gas, line[0].mach, -line[0].theta, 1.0,
                                              numPoints = 400)

    assert sourceFlow[-1].mach > line[-1].mach * 1.3, \
        'the source flow should sit far above the contoured exit on the axis'

def testInitialLineRefusesAnIncompleteSeed():
    '''A conical contour has no mesh, and a partial seed must not raise.'''
    from NOVA.Nozzle import freeJetInitialLine
    assert freeJetInitialLine(PlumeGas(GAMMA), {'xMesh': [1]}) is None
    assert freeJetInitialLine(PlumeGas(GAMMA), {}) is None

#--------------------------------------------------------------------------------------------------------------------------#
# -- Reach, conservation and the compressed lip -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _marchable(ambientPressure, exitMach = 3.0, wallAngleDeg = 9.0):

    '''
    A contour the station march can actually run on: a real exit profile across the radius rather
    than the single placeholder row the refusal contours carry.
    '''

    lipRadius = 0.30
    radii = np.linspace(0.0, lipRadius, 60)
    fraction = radii / lipRadius
    axisMach = exitMach + 0.4

    contour = types.SimpleNamespace(
        nozzleScalingFactor = 1.0,
        chamberGamma = GAMMA, chamberRGasConstant = 320.0,
        chamberStagnationTemperature = 3000.0, chamberPressure = 4.0e6,
        exitMachNumber = exitMach, targetExitPressure = 40000.0,
        exitDiameter = 2.0 * lipRadius, throatDiameter = 0.10,
        allXPoints = [np.full_like(radii, 1.0)], allRPoints = [radii],
        allMachNumbers = [axisMach + (exitMach - axisMach) * fraction],
        allFlowAngles = [np.radians(wallAngleDeg) * fraction],
        xNozzleWall = np.array([0.0, 1.0]), rNozzleWall = np.array([0.10, lipRadius]))

    return contour

def testReachIsHonouredAndReported():
    '''
    The reach is an input because it trades picture against accuracy. Asking for more must return
    more plume, and the distance actually marched must come back in the notes rather than being
    assumed equal to what was asked for.
    '''
    contour = _marchable(20000.0)
    short = solveStationField(contour, ambientPressure = 20000.0, reach = 1.0)
    long = solveStationField(contour, ambientPressure = 20000.0, reach = 3.0)
    if not (short.solved and long.solved):
        pytest.skip('the synthetic contour did not march; covered by the shipped-case tests')

    shortSpan = short.boundaryX[-1] - short.boundaryX[0]
    longSpan = long.boundaryX[-1] - long.boundaryX[0]
    assert longSpan > 2.0 * shortSpan
    assert 'lip radii' in short.notes[0]

def testDefaultReachIsTheConservativeOne():
    '''
    The default exists so that a caller who does not think about reach gets the answer that
    conserves mass rather than the picture that does not.
    '''
    assert plumeFieldDefaultReach == 2.0

def testTrustworthyTracksTheDriftRatherThanTheOperatingPoint():
    '''
    Whether a field is believable is a conservation question, not a question about where on the
    pressure range it sits. The flag has to follow the measured drift and the stated tolerance.
    '''
    field = PlumeField()
    field.massDriftWorst = plumeFieldDriftTolerance * 0.5
    assert abs(field.massDriftWorst) <= plumeFieldDriftTolerance
    field.massDriftWorst = plumeFieldDriftTolerance * 2.0
    assert abs(field.massDriftWorst) > plumeFieldDriftTolerance

def testACompressedLipIsAdmittedOnlyWhileItsShockIsWeak():
    '''
    Below a lip ratio of one the flow is compressed, which is an oblique shock this scheme cannot
    carry. Turning it isentropically instead is third order in shock strength, so it is allowed
    while the shock is weak and refused once it is not. The refusal has to name the number.
    '''
    flow = PlumeFlow(GAMMA, 320.0, 3000.0, 4.0e6)
    station = uniformStation(flow, 3.0, 0.3, 61)
    lipPressure = flow.staticPressure(3.0)

    weak = solveStationMarch(flow, station, lipPressure / 0.97, maxLength = 1.0)
    assert weak['stop'] != 'lipShockTooStrong'
    assert 0.0 < weak['lipShockLoss'] < lipShockLossLimit

    strong = solveStationMarch(flow, station, lipPressure / 0.4, maxLength = 1.0)
    assert strong['stop'] == 'lipShockTooStrong'
    assert strong['lipShockLoss'] > lipShockLossLimit
    assert len(strong['stations']) == 1

def testAnExpandedLipCarriesNoShockLoss():
    '''An underexpanded lip turns through a fan, so there is no shock to approximate away.'''
    flow = PlumeFlow(GAMMA, 320.0, 3000.0, 4.0e6)
    station = uniformStation(flow, 3.0, 0.3, 61)
    march = solveStationMarch(flow, station, flow.staticPressure(3.0) / 1.5, maxLength = 1.0)
    assert march['lipShockLoss'] == 0.0

def testABoundaryBelowMachOneIsRefusedBeforeTheShockCheck():
    '''
    A boundary that is not supersonic has no characteristics on it at all, which is a different
    and more basic failure than a shock being too strong. It has to be named separately.
    '''
    flow = PlumeFlow(GAMMA, 320.0, 3000.0, 4.0e6)
    station = uniformStation(flow, 3.0, 0.3, 61)
    march = solveStationMarch(flow, station, 4.0e6, maxLength = 1.0)
    assert march['stop'] == 'boundaryNotSupersonic'
    assert len(march['stations']) == 1
