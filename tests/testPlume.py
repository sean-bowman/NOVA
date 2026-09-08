# -- Tests for the Plume Structure Correlations -- #

'''

Validation and behaviour tests for the plume correlations in src/NOVA/Nozzle.py.

Each correlation is checked against the source it was taken from, and against limiting cases
where the answer is known independently: the Tam and Tanna diameter must collapse to the exit
diameter at matched Mach number, the Prandtl-Meyer function must reproduce its published value
at Mach 2, and the oblique shock deflection must agree with the theta-beta-M relation solved
the other way round.

Sources are listed in src/NOVA/docs/references_plumeStructure_2026-09-04.md.

Author: Sean Bowman
Date:   09/04/2026

'''

import os
import sys

import numpy as np
import pytest

from NOVA.Nozzle import (Nozzle, prandtlMeyerAngle, machFromPressureRatio, fullyExpandedDiameter,
                    shockCellLength, machDiskLocation, machDiskDiameter,
                    obliqueShockDeflection,
                    prandtlCellCoefficient, packCellCoefficient,
                    machDiskLocationCoefficient, machDiskOnsetPressureRatio)

# -- Elementary gas dynamics against published values -- #

def testPrandtlMeyerAgainstTables():

    '''

    nu(M) at gamma = 1.4 against standard compressible flow tables: 26.380 deg at M = 2,
    49.757 deg at M = 3, 0 at M = 1.

    '''

    assert np.degrees(prandtlMeyerAngle(2.0, 1.4)) == pytest.approx(26.380, abs = 0.01)
    assert np.degrees(prandtlMeyerAngle(3.0, 1.4)) == pytest.approx(49.757, abs = 0.01)
    assert prandtlMeyerAngle(1.0, 1.4) == 0.0
    assert prandtlMeyerAngle(0.5, 1.4) == 0.0

def testPrandtlMeyerMonotone():

    angles = [prandtlMeyerAngle(m, 1.4) for m in np.linspace(1.01, 6.0, 60)]
    assert np.all(np.diff(angles) > 0)

def testMachFromPressureRatioIsIsentropicInverse():

    '''

    machFromPressureRatio must invert the isentropic stagnation pressure relation exactly.

    '''

    gamma = 1.2
    for mach in (0.5, 1.0, 2.0, 3.5, 5.0):
        ratio = (1.0 + 0.5 * (gamma - 1.0) * mach**2)**(gamma / (gamma - 1.0))
        assert machFromPressureRatio(ratio, gamma) == pytest.approx(mach, rel = 1e-9)

def testMachFromPressureRatioDegenerate():

    assert machFromPressureRatio(1.0, 1.4) == 0.0
    assert machFromPressureRatio(0.5, 1.4) == 0.0

# -- Tam and Tanna equivalent diameter -- #

def testFullyExpandedDiameterCollapsesAtMatchedMach():

    '''

    The equivalent diameter must equal the exit diameter when the jet is already fully
    expanded. This is the one exact check available on the correlation.

    '''

    for gamma in (1.1475, 1.2, 1.4):
        for mach in (1.5, 3.0, 4.7):
            assert fullyExpandedDiameter(0.85, mach, mach, gamma) == pytest.approx(0.85, rel = 1e-12)

def testFullyExpandedDiameterDirection():

    '''

    Underexpanded (Mj > Me) grows the jet; overexpanded (Mj < Me) compresses it.

    '''

    gamma = 1.1475
    assert fullyExpandedDiameter(1.0, 3.0, 4.0, gamma) > 1.0
    assert fullyExpandedDiameter(1.0, 4.7, 3.125, gamma) < 1.0

def testFullyExpandedDiameterAgainstMassConservation():

    '''

    The correlation is mass conservation between the exit plane and the fully expanded state
    under isentropic flow, so it must reproduce rho_e A_e u_e = rho_j A_j u_j independently.

    '''

    gamma, exitMach, jetMach, exitDiameter = 1.2, 3.0, 4.2, 0.5

    def massFluxGroup(mach):
        # rho * u * A / (rho0 a0) for unit area, from the isentropic relations
        temperatureRatio = 1.0 + 0.5 * (gamma - 1.0) * mach**2
        density = temperatureRatio**(-1.0 / (gamma - 1.0))
        velocity = mach * np.sqrt(1.0 / temperatureRatio)
        return density * velocity

    areaRatio = massFluxGroup(exitMach) / massFluxGroup(jetMach)
    expected = exitDiameter * np.sqrt(areaRatio)
    assert fullyExpandedDiameter(exitDiameter, exitMach, jetMach, gamma) == pytest.approx(expected, rel = 1e-10)

# -- Shock cell spacing -- #

def testShockCellLengthPrandtlFormula():

    '''

    lambda = 1.306 d sqrt(Mj^2 - 1), and Pack's coefficient is the smaller of the two.

    '''

    assert shockCellLength(1.0, 2.0) == pytest.approx(prandtlCellCoefficient * np.sqrt(3.0), rel = 1e-12)
    assert shockCellLength(1.0, 2.0, packCellCoefficient) < shockCellLength(1.0, 2.0)
    assert packCellCoefficient / prandtlCellCoefficient == pytest.approx(0.934, abs = 0.005)

def testShockCellLengthSubsonic():

    assert shockCellLength(1.0, 1.0) == 0.0
    assert shockCellLength(1.0, 0.5) == 0.0

def testShockCellUsesFullyExpandedValues():

    '''

    Feeding the geometric exit diameter and exit Mach instead of the fully expanded values is
    the error the correlation is most often used with. For an overexpanded LOX/LH2 nozzle at sea
    level the two differ by several times, so the distinction is not academic.

    '''

    gamma, exitDiameter, exitMach = 1.1475, 0.85, 4.7
    jetMach = machFromPressureRatio(6.8948e6 / 101325.0, gamma)
    jetDiameter = fullyExpandedDiameter(exitDiameter, exitMach, jetMach, gamma)

    correct = shockCellLength(jetDiameter, jetMach)
    naive = shockCellLength(exitDiameter, exitMach)
    assert naive > 4.0 * correct

# -- Mach disk -- #

def testMachDiskLocationAshkenasSherman():

    '''

    x_M / D* = 0.67 sqrt(NPR), equivalently 1.34 r* sqrt(NPR).

    '''

    throatDiameter, pressureRatio = 0.101, 68.0
    expected = machDiskLocationCoefficient * throatDiameter * np.sqrt(pressureRatio)
    assert machDiskLocation(throatDiameter, pressureRatio) == pytest.approx(expected, rel = 1e-12)

    # Radius form must agree with the diameter form.
    radiusForm = 1.34 * (throatDiameter / 2.0) * np.sqrt(pressureRatio)
    assert machDiskLocation(throatDiameter, pressureRatio) == pytest.approx(radiusForm, rel = 0.005)

def testMachDiskLocationScalesAsSqrtPressureRatio():

    base = machDiskLocation(0.1, 25.0)
    assert machDiskLocation(0.1, 100.0) == pytest.approx(2.0 * base, rel = 1e-12)

def testMachDiskDiameterVanishesNearOnset():

    '''

    The logarithmic fit reaches zero near NPR 3.57, close to the measured onset threshold, and
    must never return a negative diameter.

    '''

    assert machDiskDiameter(1.0, 3.57) == pytest.approx(0.0, abs = 0.01)
    assert machDiskDiameter(1.0, 2.0) == 0.0
    assert machDiskDiameter(1.0, 100.0) > 0.0
    assert 3.0 < machDiskOnsetPressureRatio < 4.0

# -- Oblique shock at an overexpanded lip -- #

def testObliqueShockDeflectionAgainstThetaBetaM():

    '''

    Solve for the deflection that produces a known pressure rise, then verify the shock angle
    that deflection implies reproduces the same pressure rise through Rankine-Hugoniot.

    '''

    gamma, mach, pressureRise = 1.4, 3.0, 3.0
    deflection = obliqueShockDeflection(mach, gamma, pressureRise)
    assert deflection > 0.0

    # Recover the shock angle from theta-beta-M by bisection, then check the pressure rise.
    def deflectionFromAngle(beta):
        numerator = 2.0 / np.tan(beta) * (mach**2 * np.sin(beta)**2 - 1.0)
        denominator = mach**2 * (gamma + np.cos(2.0 * beta)) + 2.0
        return np.arctan(numerator / denominator)

    low, high = np.arcsin(1.0 / mach) + 1e-6, np.pi / 2 - 1e-6
    for _ in range(200):
        middle = 0.5 * (low + high)
        if deflectionFromAngle(middle) < deflection:
            low = middle
        else:
            high = middle
    beta = 0.5 * (low + high)
    normalMach = mach * np.sin(beta)
    recovered = 1.0 + 2.0 * gamma / (gamma + 1.0) * (normalMach**2 - 1.0)
    assert recovered == pytest.approx(pressureRise, rel = 1e-3)

def testObliqueShockDetachment():

    '''

    A pressure rise beyond what an attached oblique shock can deliver returns zero, flagging
    detachment rather than silently producing a wrong angle.

    '''

    assert obliqueShockDeflection(1.5, 1.4, 100.0) == 0.0
    assert obliqueShockDeflection(0.8, 1.4, 2.0) == 0.0
    assert obliqueShockDeflection(3.0, 1.4, 1.0) == 0.0

# -- End to end on a synthetic nozzle -- #

def _stubNozzle(exitPressure: float) -> Nozzle:

    '''

    A Nozzle carrying only the attributes plumeStructure reads, so the structure logic is
    testable without a CEA solve. Uses the real class rather than a stand-in, so the tests
    exercise the method as callers reach it.

    '''

    nozzle = Nozzle()
    nozzle.xNozzleWall = np.linspace(-0.35, 1.0, 200)
    nozzle.rNozzleWall = 0.0505 + 0.375 * np.clip(nozzle.xNozzleWall, 0.0, None)**0.7
    nozzle.nozzleNearWallMachNumber = np.linspace(0.05, 5.0, 200)
    nozzle.nozzleNearWallPressure = np.linspace(6.8948e6, exitPressure, 200)
    nozzle.chamberPressure = 6.8948e6
    nozzle.chamberGamma = 1.1475
    nozzle.exitMachNumber = 4.06
    nozzle.targetExitPressure = exitPressure
    nozzle.ceaOutput = None
    return nozzle

def testStructureRegimeClassification():

    # Sea level: design exit pressure is far below ambient, so overexpanded.
    overexpanded = _stubNozzle(13993.0).plumeStructure(101325.0)
    assert overexpanded.jetType == 'overexpanded'
    assert overexpanded.exitPressureRatio < 1.0

    # Near vacuum: underexpanded.
    underexpanded = _stubNozzle(13993.0).plumeStructure(1000.0)
    assert underexpanded.jetType == 'underexpanded'
    assert underexpanded.initialTurnAngle > 0.0

    # Matched.
    matched = _stubNozzle(13993.0).plumeStructure(13993.0)
    assert matched.jetType == 'ideallyExpanded'

def testStructureFlagsSeparation():

    '''

    A heavily overexpanded case must say so rather than quietly reporting a plume that cannot
    exist.

    '''

    structure = _stubNozzle(13993.0).plumeStructure(101325.0)
    assert any('separation' in note.lower() or 'separated' in note.lower() for note in structure.notes)

def testStructureMachDiskConsistency():

    structure = _stubNozzle(13993.0).plumeStructure(1000.0)
    assert structure.machDiskPresent
    assert structure.machDiskX > structure.lipX
    assert structure.machDiskDiameter > 0.0
    # Location must match the correlation applied to the reported inputs.
    expected = structure.lipX + machDiskLocation(structure.throatDiameter, structure.nozzlePressureRatio)
    assert structure.machDiskX == pytest.approx(expected, rel = 1e-12)

def testStructureBoundaryStartsAtLip():

    structure = _stubNozzle(13993.0).plumeStructure(1000.0)
    assert structure.boundaryX[0] == pytest.approx(structure.lipX)
    assert structure.boundaryR[0] == pytest.approx(structure.lipRadius)
    assert np.all(structure.boundaryR >= 0.0)
    assert np.all(np.isfinite(structure.boundaryR))

def testStructureBoundaryInitialSlopeMatchesTurnAngle():

    """

    The boundary shape is an assumption, but it is anchored so its initial slope equals the
    correlated turning angle. That anchoring is worth holding to wherever it survives, which is
    wherever the cell amplitude is not capped to keep the boundary off the axis.

    """

    structure = _stubNozzle(13993.0).plumeStructure(1000.0)
    slope = ((structure.boundaryR[1] - structure.boundaryR[0])
             / (structure.boundaryX[1] - structure.boundaryX[0]))
    if structure.boundaryAmplitudeLimited:
        assert abs(slope) < abs(np.tan(structure.initialTurnAngle))
    else:
        assert slope == pytest.approx(np.tan(structure.initialTurnAngle), rel = 0.02)

def testStructureBoundaryStaysOffTheAxis():

    """

    A capped amplitude exists so the boundary never lies flat on the centre line. Whatever the
    pressure ratio, the drawn radius stays strictly positive.

    """

    for ambientPressure in (100.0, 1000.0, 13993.0, 50000.0, 101325.0):
        structure = _stubNozzle(13993.0).plumeStructure(ambientPressure)
        assert structure is not None
        assert float(np.min(structure.boundaryR)) > 0.0

def testCappedAmplitudeIsDisclosed():

    """A capped boundary is stated in the notes rather than left for the reader to notice."""

    structure = _stubNozzle(13993.0).plumeStructure(100.0)
    if structure.boundaryAmplitudeLimited:
        assert any('capped' in note.lower() for note in structure.notes)

def testStructureCarriesUncertaintyNote():

    structure = _stubNozzle(13993.0).plumeStructure(1000.0)
    assert any('correlation' in note.lower() for note in structure.notes)
    assert structure.cellLengthPack < structure.shockCellLength

def testStructureRejectsBadInput():

    assert _stubNozzle(13993.0).plumeStructure(0.0) is None

    empty = Nozzle()
    empty.xNozzleWall = np.array([])
    empty.rNozzleWall = np.array([])
    assert empty.plumeStructure(101325.0) is None
