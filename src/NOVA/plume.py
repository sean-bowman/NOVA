
# -- Exhaust Plume Structure and Interior -- #

'''

The exhaust plume: its outer structure from correlation, its interior from characteristics.

Three layers sit here, in increasing order of how much they actually solve.

The correlations place the jet boundary, the shock cell spacing and the Mach disk from
published fits. They need only the exit state, they cover every operating point, and they solve
nothing. Every one of them traces to `docs/references_plumeStructure_2026-09-04.md`.

The free-jet lattice, the `freeJet*` functions, is a transcription of the axisymmetric
method-of-characteristics program in NASA TN D-2327. It solves a jet from a supplied exit Mach
number and wall angle, independent of any nozzle.

The plume march, `PlumeFlow` through `solvePlumeMarch`, continues NOVA's own nozzle
characteristics solution past the lip. Inside the nozzle the outer boundary is a wall and the
contour prescribes the flow angle; past the lip it is a free streamline at ambient pressure and
the angle falls out. Nothing else changes, which is what makes the two halves one solution
rather than a solution and a picture. Its interior point calls the same routine the contour
solver calls, so the two cannot drift apart.

Where the march stands, what is validated and against what, and what is still open is recorded
in
`experimental/plumeDevelopmentState.md`.

Author: Sean Bowman

'''

import bisect
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .gasDynamics import prandtlMeyerAngle, machFromPressureRatio

#--------------------------------------------------------------------------------------------------------------------------#
# -- Correlation constants -- #
#--------------------------------------------------------------------------------------------------------------------------#

# Prandtl (1904), first term of the series solution for the cell length of an almost perfectly
# expanded circular supersonic jet. Pack recomputed it with 40 terms and obtained 1.22; both are
# offered because the literature quotes each, and the spread is a fair measure of the
# uncertainty in any cell-spacing prediction.
prandtlCellCoefficient = 1.306
packCellCoefficient    = 1.22

# Ashkenas and Sherman (1966): x_M / D* = 0.67 sqrt(P0 / Pa). Reported coefficients across
# sources span 0.64 to 0.67.
machDiskLocationCoefficient = 0.67

# Nozzle pressure ratio above which a Mach reflection (Mach disk) replaces the regular
# reflection. Classical measurements cluster near 3.9 (Crist 1966), 3.78 (Antsupov 1974), 3.67
# (Addy 1981); recent DNS puts it near 3.1. The threshold is uncertain at roughly the 20 %
# level, so it is deliberately a soft switch reported alongside the value used.
machDiskOnsetPressureRatio = 3.5

# Summerfield criterion: an overexpanded nozzle separates internally below roughly this exit to
# ambient static pressure ratio, at which point the plume correlations, which all assume flow
# attached at the lip, no longer describe the real jet.
separationPressureRatio = 0.4

# Validity envelope for the solved plume interior, `Nozzle.plumeField`.
#
# The characteristics net is quantitatively defensible only for a mildly underexpanded jet. There
# the compression waves reflected from the jet boundary have not yet coalesced, the flow really is
# isentropic, and the net reproduces the first shock cell without any shock model at all. Measured
# against Prandtl's cell length over exit Mach 1.5 to 5.0, the net runs long by between 3.9 and
# 10.0 percent everywhere inside these bounds, and the error is systematic rather than scattered.
#
# Outside them it is not defensible and `plumeField` refuses rather than returning a field:
#
#   Pe/Pa below 1.05   a jet this close to design has no wave structure worth resolving
#   Pe/Pa above 2.0    the first cell runs short, reaching -10 percent by 3.0 and -46 by 5.0,
#                      because the internal shock that recompresses the core is not solved
#   overexpanded       the lip turns through an oblique shock rather than an expansion fan, which
#                      this formulation does not carry
#   divergent exit     the solved cell length falls away steeply with exit wall angle, reaching
#                      -25 percent by 5 degrees and -34 by 11. Love et al. (NASA TR R-6) measured
#                      that effect and report it as small over 0 to 20 degrees, so this is a
#                      defect in the march rather than a region merely lacking a reference. The
#                      net also stops surviving a divergent exit: the boundary falls from 1 139
#                      points at a parallel exit to 92 at fourteen degrees, which is too few to
#                      resolve the second cell a wavelength would have to be measured between.
#
#                      One cause has been found and removed without closing the gap. A truncated
#                      ideal contour does not leave a uniform exit plane; the showcase nozzle
#                      leaves at 0 degrees and Mach 4.81 on the axis and 14.1 degrees and Mach
#                      4.04 at the wall, while the source flow of Appendix A puts Mach 8.10 on the
#                      axis for the same nozzle. `freeJetInitialLine` replaces that construction
#                      with the exit plane of the contour solve, which is now what the march
#                      starts from. It carries the boundary further, from 46 points to 68, and
#                      lowers the peak Mach number from 5.53 to 5.41, but the boundary still does
#                      not turn over before the line runs out of points against a jet that is
#                      opening much faster than the march advances. That is the remaining defect.
#
# The strongly underexpanded plume that `plumeStructure` correlates is deliberately outside this
# envelope. Against NASA TN D-2327 the net reaches 47 percent low on maximum jet radius there.
# Four of these are enforced in `solvePlumeField`. `plumeFieldMinPressureRatio` is not, and is
# kept as a statement about what is worth resolving rather than what is valid: a jet at a ratio of
# 1.02 solves correctly and carries a wave structure too weak to be interesting. Enforcing it as a
# floor would also refuse every overexpanded jet, which the march handles deliberately and with a
# measured approximation, taking the lip turn as an isentropic compression rather than the oblique
# shock it is. That approximation holds to 0.2 percent at a ratio of 0.6 and 0.8 percent at 0.4,
# below which `separationPressureRatio` refuses on the Summerfield criterion instead.
plumeFieldMinPressureRatio = 1.05
plumeFieldMaxPressureRatio = 2.0
plumeFieldMinExitMach = 1.5
plumeFieldMaxExitMach = 5.0
plumeFieldMaxWallAngle = np.radians(0.5)

# How near the center line a point has to be for the symmetry condition to apply to it, and how
# much flow angle it may carry there. The march builds every line to cross the axis straight, and
# an initial line that does not is refused rather than marched: see `solvePlumeMarch`.
centerLineRadiusTolerance = 1e-9
centerLineAngleTolerance = np.radians(1e-6)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Elementary gas dynamics -- #
#--------------------------------------------------------------------------------------------------------------------------#

# The isentropic ratios, the Prandtl-Meyer function and the area-Mach relation live in
# gasDynamics.py and are imported above. They are re-exported from here because the plume block,
# the contour solver and the test suite all reach for them through this module.

def fullyExpandedDiameter(exitDiameter: float, exitMach: float, jetMach: float,
                          gamma: float) -> float:

    '''

    Equivalent fully expanded jet diameter (Tam and Tanna).

        d_j / d_e = [ (1 + (g-1)/2 Mj^2) / (1 + (g-1)/2 Me^2) ]^((g+1)/(4(g-1))) * (Me/Mj)^(1/2)

    This follows from mass conservation between the exit plane and the fully expanded state
    under isentropic flow, and reduces to d_j = d_e when Mj = Me. The shock cell correlation is
    written in terms of this diameter, not the geometric exit diameter; conflating the two is
    the largest single error available here.

    '''

    if exitMach <= 0.0 or jetMach <= 0.0:
        return exitDiameter
    numerator = 1.0 + 0.5 * (gamma - 1.0) * jetMach**2
    denominator = 1.0 + 0.5 * (gamma - 1.0) * exitMach**2
    exponent = (gamma + 1.0) / (4.0 * (gamma - 1.0))
    return float(exitDiameter * (numerator / denominator)**exponent
                 * np.sqrt(exitMach / jetMach))

def shockCellLength(jetDiameter: float, jetMach: float,
                    coefficient: float = prandtlCellCoefficient) -> float:

    '''

    Shock cell spacing, Prandtl's formula: lambda = C * d_j * sqrt(Mj^2 - 1).

    Both arguments must be the **fully expanded** jet values. This is a linearized,
    small-perturbation result: it predicts the first cell of a weakly imperfectly expanded jet
    well and does not capture the downstream shortening caused by viscous dissipation, so an
    average spacing taken from it runs long against experiment.

    Returns 0.0 for a subsonic jet, where no cell structure exists.

    '''

    if jetMach <= 1.0:
        return 0.0
    return float(coefficient * jetDiameter * np.sqrt(jetMach**2 - 1.0))

def machDiskLocation(throatDiameter: float, nozzlePressureRatio: float,
                     coefficient: float = machDiskLocationCoefficient) -> float:

    '''

    Axial distance from the nozzle exit plane to the Mach disk (Ashkenas and Sherman, 1966).

        x_M / D* = C * sqrt(P0 / Pa)

    Scaled on the **throat** diameter and the **chamber stagnation** pressure, not the exit
    values. Very weakly dependent on gamma.

    '''

    if nozzlePressureRatio <= 1.0:
        return 0.0
    return float(coefficient * throatDiameter * np.sqrt(nozzlePressureRatio))

def machDiskDiameter(exitDiameter: float, nozzlePressureRatio: float) -> float:

    '''

    Mach disk diameter from the logarithmic fit D_MD/D_e = 1.78 log10(NPR) - 0.98.

    Fitted for coflowing jets rather than still air, so this carries more uncertainty than the
    location correlation. Returns 0.0 below the pressure ratio at which the fit reaches zero,
    which is close to the measured onset threshold.

    '''

    if nozzlePressureRatio <= 1.0:
        return 0.0
    ratio = 1.78 * np.log10(nozzlePressureRatio) - 0.98
    return float(max(0.0, ratio) * exitDiameter)

def obliqueShockDeflection(mach: float, gamma: float, pressureRatio: float) -> float:

    '''

    Flow deflection angle [rad] through the oblique shock that raises static pressure by
    `pressureRatio`, for an overexpanded jet turning inward at the lip.

    The shock angle follows from the Rankine-Hugoniot normal-Mach relation
    P2/P1 = 1 + 2g/(g+1) (Mn^2 - 1), and the deflection from the theta-beta-M relation.
    Returns 0.0 when the required pressure rise exceeds what an attached oblique shock can
    deliver at this Mach number, which is the detachment condition.

    '''

    if mach <= 1.0 or pressureRatio <= 1.0:
        return 0.0

    # Normal Mach number the shock must have to produce the pressure rise.
    normalMachSquared = 1.0 + (pressureRatio - 1.0) * (gamma + 1.0) / (2.0 * gamma)
    if normalMachSquared > mach**2:
        # Required rise is beyond an attached oblique shock: the shock detaches.
        return 0.0

    shockAngle = np.arcsin(np.sqrt(normalMachSquared) / mach)
    numerator = 2.0 / np.tan(shockAngle) * (mach**2 * np.sin(shockAngle)**2 - 1.0)
    denominator = mach**2 * (gamma + np.cos(2.0 * shockAngle)) + 2.0
    return float(np.arctan(numerator / denominator))

def obliqueShockState(mach: float, gamma: float, pressureRatio: float) -> tuple:

    '''

    State behind the oblique shock that raises static pressure by `pressureRatio`.

    Returns (deflection [rad], downstream Mach [-], stagnation pressure ratio p02/p01 [-]).
    The stagnation ratio is the useful one for deciding whether a shock may be ignored: it is the
    entropy rise in disguise, it departs from one only at third order in shock strength, and it is
    what bounds an isentropic treatment of a weak shock.

    Returns (0.0, mach, 1.0) when the required pressure rise is beyond an attached oblique shock,
    which is the detachment condition, and for a pressure ratio at or below one.

    '''

    if mach <= 1.0 or pressureRatio <= 1.0:
        return 0.0, mach, 1.0

    normalMachSquared = 1.0 + (pressureRatio - 1.0) * (gamma + 1.0) / (2.0 * gamma)
    if normalMachSquared > mach**2:
        return 0.0, mach, 1.0

    shockAngle = np.arcsin(np.sqrt(normalMachSquared) / mach)
    deflection = obliqueShockDeflection(mach, gamma, pressureRatio)
    if deflection <= 0.0:
        return 0.0, mach, 1.0

    downstreamNormalSquared = (1.0 + 0.5 * (gamma - 1.0) * normalMachSquared)                               / (gamma * normalMachSquared - 0.5 * (gamma - 1.0))
    downstreamMach = np.sqrt(downstreamNormalSquared) / np.sin(shockAngle - deflection)

    stagnationRatio = ((gamma + 1.0) * normalMachSquared
                       / ((gamma - 1.0) * normalMachSquared + 2.0)) ** (gamma / (gamma - 1.0))                       * ((gamma + 1.0)
                         / (2.0 * gamma * normalMachSquared - (gamma - 1.0))) ** (1.0 / (gamma - 1.0))
    return float(deflection), float(downstreamMach), float(stagnationRatio)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Plume structure -- #
#--------------------------------------------------------------------------------------------------------------------------#

@dataclass
class PlumeStructure:

    '''

    Correlation-based plume structure downstream of the nozzle exit plane.

    Every scalar here traces to a source in docs/references_plumeStructure_2026-09-04.md. The
    boundary curve interpolates between correlated quantities and is a shape assumption, stated
    as such in `notes`.

    '''

    jetType: str = 'ideallyExpanded'      # 'underexpanded' | 'overexpanded' | 'ideallyExpanded'
    ambientPressure: float = 0.0          # [Pa]

    # Lip state, used for the initial boundary inclination
    lipX: float = 0.0                     # [m]
    lipRadius: float = 0.0                # [m]
    lipMach: float = 0.0                  # [-]
    lipPressure: float = 0.0              # [Pa]
    lipWallAngle: float = 0.0             # [rad], nozzle wall divergence at the exit

    # Jet-scale state, used for the cell and Mach disk correlations
    exitMach: float = 0.0                 # [-], one-dimensional
    exitPressure: float = 0.0             # [Pa], one-dimensional
    exitDiameter: float = 0.0             # [m], geometric
    throatDiameter: float = 0.0           # [m]
    gamma: float = 0.0                    # [-]

    nozzlePressureRatio: float = 0.0      # [-], P0 / Pa
    exitPressureRatio: float = 0.0        # [-], Pe / Pa
    fullyExpandedMach: float = 0.0        # [-], Mj
    fullyExpandedDiameter: float = 0.0    # [m], Dj

    initialTurnAngle: float = 0.0         # [rad], positive outward
    shockCellLength: float = 0.0          # [m]
    boundaryAmplitudeLimited: bool = False  # cell amplitude capped to keep r > 0
    cellLengthPack: float = 0.0           # [m], the same with Pack's coefficient
    machDiskPresent: bool = False
    machDiskX: float = 0.0                # [m], absolute axial position
    machDiskDiameter: float = 0.0         # [m]
    plumeLength: float = 0.0              # [m]

    boundaryX: np.ndarray = field(default_factory = lambda: np.array([]))   # [m]
    boundaryR: np.ndarray = field(default_factory = lambda: np.array([]))   # [m]
    cellX: np.ndarray = field(default_factory = lambda: np.array([]))       # [m]

    notes: list = field(default_factory = list)

@dataclass
class PlumeField:

    '''

    Solved plume interior, from the free-jet characteristic net downstream of the exit plane.

    Unlike `PlumeStructure`, which interpolates between correlated scalars, every node here is a
    solution of the characteristic equations and the boundary is a computed constant-pressure
    streamline rather than an assumed shape. That holds only inside the validity envelope; see
    `plumeFieldMinPressureRatio`. Outside it `solved` is False, the arrays are empty, and `notes`
    says why.

    '''

    solved: bool = False                  # whether the characteristics march was run
    trustworthy: bool = False             # whether it conserved mass well enough to be believed
    withinEnvelope: bool = False          # whether the operating point is inside the validated band
    seededFromMesh: bool = False          # exit plane taken from the contour solve, not assumed

    exitMach: float = 0.0                 # [-], at the lip
    exitPressureRatio: float = 0.0        # [-], Pe / Pa
    boundaryMach: float = 0.0             # [-], constant along the free boundary
    lipTurnAngle: float = 0.0             # [rad], Prandtl-Meyer turning at the lip, positive outward
    lipX: float = 0.0                     # [m]
    lipRadius: float = 0.0                # [m]

    shockCellLength: float = 0.0          # [m], axial period between boundary crests
    cellsResolved: int = 0                # [-], complete cells the march carried
    solvedTo: float = 0.0                 # [m], axial station the march reached
    stop: str = ''                        # why the march ended
    massDriftWorst: float = float('nan')  # [%], flux departure from the exit plane
    machDiskPresent: bool = False
    machDiskX: float = 0.0                # [m]
    machDiskDiameter: float = 0.0         # [m]

    nodeX: np.ndarray = field(default_factory = lambda: np.array([]))        # [m]
    nodeR: np.ndarray = field(default_factory = lambda: np.array([]))        # [m]
    nodeMach: np.ndarray = field(default_factory = lambda: np.array([]))     # [-]
    nodePressure: np.ndarray = field(default_factory = lambda: np.array([]))  # [Pa]
    nodeFlowAngle: np.ndarray = field(default_factory = lambda: np.array([]))  # [rad]

    boundaryX: np.ndarray = field(default_factory = lambda: np.array([]))    # [m]
    boundaryR: np.ndarray = field(default_factory = lambda: np.array([]))    # [m]
    shockX: np.ndarray = field(default_factory = lambda: np.array([]))       # [m]
    shockR: np.ndarray = field(default_factory = lambda: np.array([]))       # [m]

    notes: list = field(default_factory = list)

def _exitWallAngle(x: np.ndarray, r: np.ndarray) -> float:

    '''

    Nozzle wall divergence angle at the exit [rad], from the slope of the last contour segment.
    Love et al. identify this as a primary variable for the boundary inclination, so it is read
    from the geometry rather than assumed zero.

    '''

    if x.size < 3:
        return 0.0
    span = max(2, x.size // 50)
    deltaX = float(x[-1] - x[-1 - span])
    deltaR = float(r[-1] - r[-1 - span])
    if deltaX <= 0.0:
        return 0.0
    return float(np.arctan2(deltaR, deltaX))

#--------------------------------------------------------------------------------------------------------------------------#
# -- Free-jet characteristic net -- #
#--------------------------------------------------------------------------------------------------------------------------#

# The plume interior, solved rather than correlated, by the method of characteristics of NASA
# TN D-2327 (Andrews, Craidon, Dennard and Vick, 1964), Appendices A and C. This carries the
# nozzle-interior solver past the exit plane, where the outer boundary stops being a wall and
# becomes a free constant-pressure streamline.
#
# Equation numbers refer to that report. Sign conventions follow it: the net is built BELOW the
# center line, so y <= 0, theta is negative where the flow turns away from the axis, and mu is
# positive. The scheme is a lattice, point to point, and does not iterate. Point C on
# second-family line j comes from A, point i of line j-1, and B, point i-1 of line j.
#
# The net is quantitatively trustworthy only inside the envelope Nozzle.plumeField() enforces;
# see plumeFieldMinPressureRatio and the constants beside it.

class PlumeGas:
    '''Calorically perfect gas. W is velocity over the limiting velocity, as in TN D-2327.'''

    def __init__(self, gamma):
        self.gamma = gamma

    def nu(self, mach):
        '''Prandtl-Meyer angle, eq (A5). The module function is the single implementation.'''
        return prandtlMeyerAngle(mach, self.gamma)

    def machFromNu(self, target):
        low, high = 1.0 + 1e-12, 1.0e6
        for _ in range(200):
            mid = 0.5 * (low + high)
            if self.nu(mid) < target:
                low = mid
            else:
                high = mid
        return 0.5 * (low + high)

    def machAngle(self, mach):
        '''Eq (A4).'''
        return math.asin(1.0 / mach)

    def W(self, mach):
        '''Velocity ratio V / V_limiting.'''
        half = 0.5 * (self.gamma - 1.0)
        return math.sqrt(half * mach**2 / (1.0 + half * mach**2))

    def machFromW(self, W):
        '''Inverse of W(mach); equivalent to eq (C12) followed by (C13).'''
        half = 0.5 * (self.gamma - 1.0)
        value = W * W
        if value >= 1.0:
            return math.inf
        return math.sqrt(value / (half * (1.0 - value)))

    def muFromW(self, W):
        '''Eq (C12).'''
        half = 0.5 * (self.gamma - 1.0)
        argument = half * (1.0 / (W * W) - 1.0)
        if argument >= 1.0:
            return math.pi / 2
        return math.asin(math.sqrt(argument))

    def pressureRatio(self, mach):
        '''p / p_total.'''
        return (1.0 + 0.5 * (self.gamma - 1.0) * mach**2)**(-self.gamma / (self.gamma - 1.0))

    def machFromPressureRatio(self, ratio):
        '''Mach for p / p_total. The module function is written the other way up.'''
        return machFromPressureRatio(1.0 / ratio, self.gamma)

class PlumeNode:
    __slots__ = ('x', 'y', 'theta', 'mach', 'mu', 'W', 'kind')

    def __init__(self, x, y, theta, mach, gas, kind='general'):
        self.x, self.y, self.theta, self.mach = x, y, theta, mach
        self.mu = gas.machAngle(mach)
        self.W = gas.W(mach)
        self.kind = kind

    def __repr__(self):
        return (f'PlumeNode({self.kind} x={self.x:.4f} y={self.y:.4f} '
                f'th={math.degrees(self.theta):.3f} M={self.mach:.4f})')

def _lA(point):
    '''
    Eq (C9), the first-family axisymmetric source coefficient. Transcribed from the FORTRAN
    subroutine GENL: FLA = (B3*SIN(GTA)*D4)/B4 with B3 = sin(mu), D4 = tan(mu), B4 = cos(th+mu).

    No point type is exempt. Corner rays carry the lip coordinates (0, -r_j) on every card, as
    punched by the corner expansion ray program P-5433, so the source is integrated over the full
    ray length on the first line and over the local segment thereafter.
    '''
    return (math.sin(point.mu) * math.sin(point.theta) * math.tan(point.mu)
            / math.cos(point.theta + point.mu))

def _mB(point, sameFamily=False):
    '''Eq (C10), or (C24) when both rays belong to the first family.'''
    denominator = math.cos(point.theta + point.mu) if sameFamily else math.cos(point.theta - point.mu)
    return math.sin(point.mu) * math.sin(point.theta) * math.tan(point.mu) / denominator

def _thetaC(A, B, xC, lA, mB):
    '''Eq (C8). Also used for the same-family point with mB from (C24).'''
    numerator = (-A.W - A.W * (-A.theta * math.tan(A.mu) + (lA / A.y) * (xC - A.x))
                 + B.W + B.W * (B.theta * math.tan(B.mu) + (mB / B.y) * (xC - B.x)))
    return numerator / (A.W * math.tan(A.mu) + B.W * math.tan(B.mu))

def _WC(A, thetaC, xC, lA):
    '''Eq (C11).'''
    return A.W + A.W * (math.tan(A.mu) * (thetaC - A.theta) + (lA / A.y) * (xC - A.x))

def _finish(gas, x, y, theta, W, kind):
    mach = gas.machFromW(W)
    if not math.isfinite(mach) or mach <= 1.0:
        return None
    point = PlumeNode(x, y, theta, mach, gas, kind)
    point.W = W
    point.mu = gas.muFromW(W)
    return point

def _interpolate(gas, left, right, weight):
    """Linear blend of two points on a line; W carries the state, mach and mu follow from it."""
    x = left.x + (right.x - left.x) * weight
    y = left.y + (right.y - left.y) * weight
    theta = left.theta + (right.theta - left.theta) * weight
    W = left.W + (right.W - left.W) * weight
    return _finish(gas, x, y, theta, W, 'inserted')

def freeJetRefineLine(gas, line, fraction=0.10, limit=800):
    """
    Insert points where a line has stretched.

    Characteristics absorbed at the jet boundary leave the net coarser than they found it, and
    nothing in a plain point-to-point march puts that resolution back. Left alone the lines decay
    until each step spans a large fraction of the jet, at which point the linearized source term
    in eq (C11) is no longer valid over a step and the solution degrades.

    A segment is split when it is longer than `fraction` of the local radius, which holds the
    step small compared with the length scale the axisymmetric source terms vary over. `limit`
    caps the count: a line that is only ever added to grows without bound, and since every line is
    walked point by point against the one before it, the march would then cost the square of the
    number of lines. Refinement simply stops at the cap rather than thinning the line, because
    dropping points from a lattice breaks the point-to-point correspondence the scheme rests on.

    The local radius is floored at a small part of the line's own radial extent. Taken literally
    it goes to zero on the axis, and the splitting then packs thousands of points into the last
    fraction of a percent of the jet radius. A line built against an A array like that spends
    every point it has crawling beside the axis, never reaches the boundary, and the march stops.
    The source terms do not need that resolution there: the term is l_A (x_C - x_A) / y_A, and the
    step in x collapses in proportion to y as the axis is approached, so the quotient stays
    bounded.
    """
    if len(line) < 2:
        return line

    floor = 0.02 * max(abs(point.y) for point in line)
    refined = [line[0]]
    for left, right in zip(line[:-1], line[1:]):
        span = math.hypot(right.x - left.x, right.y - left.y)
        scale = max(abs(left.y), abs(right.y), floor, 1e-9)
        splits = int(span / (fraction * scale))
        if splits > 0 and len(refined) + splits < limit:
            for index in range(1, splits + 1):
                inserted = _interpolate(gas, left, right, index / (splits + 1.0))
                if inserted is not None:
                    refined.append(inserted)
        refined.append(right)
    return refined

def freeJetGeneralPoint(gas, A, B):
    '''First-family point A, second-family point B. Eqs (C3), (C4), (C8), (C11).'''
    slopeA = math.tan(A.theta + A.mu)
    slopeB = math.tan(B.theta - B.mu)
    if abs(slopeA - slopeB) < 1e-14:
        return None
    xC = (A.x * slopeA - A.y + B.y - B.x * slopeB) / (slopeA - slopeB)      # (C3)
    yC = (xC - A.x) * slopeA + A.y                                          # (C4)
    if xC < max(A.x, B.x) - 1e-9:
        return None
    lA, mB = _lA(A), _mB(B)
    thetaC = _thetaC(A, B, xC, lA, mB)                                      # (C8)
    return _finish(gas, xC, yC, thetaC, _WC(A, thetaC, xC, lA), 'general')   # (C11)

def freeJetSameFamilyPoint(gas, A, B):
    '''Two first-family rays crossing: the internal shock. Eqs (C23), (C24).'''
    slopeA = math.tan(A.theta + A.mu)
    slopeB = math.tan(B.theta + B.mu)
    if abs(slopeA - slopeB) < 1e-14:
        return None
    xC = (A.x * slopeA - A.y + B.y - B.x * slopeB) / (slopeA - slopeB)      # (C23)
    yC = (xC - A.x) * slopeA + A.y                                          # (C4)
    lA, mB = _lA(A), _mB(B, sameFamily=True)                                # (C24)
    thetaC = _thetaC(A, B, xC, lA, mB)
    return _finish(gas, xC, yC, thetaC, _WC(A, thetaC, xC, lA), 'shock')

def freeJetBoundaryPoint(gas, A, B):
    '''
    A is the previous boundary point, so line AC is a STREAMLINE, not a characteristic.
    Boundary Mach is constant, so W_C = W_A and mu_C = mu_A. Eqs (C18)-(C20).
    '''
    slopeA = math.tan(A.theta)
    slopeB = math.tan(B.theta - B.mu)
    if abs(slopeA - slopeB) < 1e-14:
        return None
    xC = (A.x * slopeA - A.y + B.y - B.x * slopeB) / (slopeA - slopeB)      # (C18)
    yC = (xC - A.x) * slopeA + A.y                                          # (C19)
    mB = _mB(B)
    WC = A.W
    thetaC = B.theta + (-(WC - B.W) / B.W + mB * (xC - B.x) / B.y) / math.tan(B.mu)   # (C20)
    point = PlumeNode(xC, yC, thetaC, A.mach, gas, 'boundary')
    point.W, point.mu = WC, A.mu
    return point

def freeJetNearAxisPoint(gas, A, B):
    '''
    PlumeNode one off the center line, subroutine OFCNT. B lies on the center line, so y_B = 0 and
    theta_B = 0 and the B-side source term m_B dx_B / y_B is 0/0. Eq (C27) drops it entirely:
    GTC = (-GWA - GWA*C1 + GWB)/(GWA*D1 + GWB*D2), with D1 = tan(mu_A) and D2 = tan(mu_B).
    '''
    slopeA = math.tan(A.theta + A.mu)
    slopeB = -math.tan(B.mu)
    if abs(slopeA - slopeB) < 1e-14:
        return None
    xC = (A.x * slopeA - A.y - B.x * slopeB) / (slopeA - slopeB)            # (C3), y_B = 0
    yC = (xC - A.x) * slopeA + A.y                                          # (C4)
    if xC < max(A.x, B.x) - 1e-9:
        return None
    lA = _lA(A)
    c1 = -A.theta * math.tan(A.mu) + lA * (xC - A.x) / A.y
    thetaC = (-A.W - A.W * c1 + B.W) / (A.W * math.tan(A.mu) + B.W * math.tan(B.mu))   # (C27)
    return _finish(gas, xC, yC, thetaC, _WC(A, thetaC, xC, lA), 'nearAxis')

def freeJetCenterLineTarget(gas, A):
    '''
    Where A's first-family characteristic reaches the axis, subroutine CENTL.

    Returned as a bare (x, mu, W) triple rather than a point because the march does not jump
    straight to it. The approach is taken in thirds, and the intermediate stations are states on
    the axis that no single CENTL call produces.
    '''
    slopeA = math.tan(A.theta + A.mu)
    if abs(slopeA) < 1e-14:
        return None
    xC = A.x - A.y / slopeA                                                 # (C28)
    if xC < A.x - 1e-9:
        return None
    lA = _lA(A)
    WC = _WC(A, 0.0, xC, lA)                                                # (C11) with theta_C = 0
    mach = gas.machFromW(WC)
    if not math.isfinite(mach) or mach <= 1.0:
        return None
    return xC, gas.muFromW(WC), WC                                          # (C12)

def freeJetCenterLinePoint(gas, A):
    '''y = 0 and theta = 0 by symmetry. Eq (C28), then the general-point relations.'''
    target = freeJetCenterLineTarget(gas, A)
    if target is None:
        return None
    xC, _, WC = target
    return _finish(gas, xC, 0.0, 0.0, WC, 'centerLine')

def _freeJetCrossed(x, y, xMin, xMax, yMin, yMax, first, second, slope, intercept):
    '''
    Subroutine CROSS. Decides whether one candidate same-family point is a real crossing.

    Three conditions, in the order the listing applies them: the candidate lies inside the box
    spanning the points that produced it, the two rays are converging rather than diverging, and
    the candidate lies beyond the second-family line through the last point placed on the line
    being built. The sense of that last test flips with the sign of the line's slope.
    '''
    if not (yMin < y < yMax):
        return False
    if not (xMin < x < xMax):
        return False
    if (first.theta + first.mu) - (second.theta + second.mu) > 0.0:
        return False
    residual = y - slope * x
    return residual <= intercept if slope < 0.0 else residual >= intercept

def freeJetCrossing(gas, aPoints, index, reference):
    '''
    Subroutine TEST, which decides where the internal shock forms.

    Three candidate shock points are built from the consecutive first-family pairs starting at
    `index`, each by eqs (C23) and (C24), and each is put to CROSS against a box spanning those
    four A points and the last point placed on the current line. Where more than one qualifies,
    the one nearest the station the search began from wins, per statements 740, 760, 770 and 780.

    Returns the offset of the pair that crosses and the shock point it produces, or None when the
    characteristics are still diverging and the flow is smooth.
    '''
    if index + 3 >= len(aPoints):
        return None

    # The second-family characteristic leaving the last point on the line. A candidate has to sit
    # beyond it, or it belongs to a line already computed rather than to this one.
    slope = math.tan(reference.theta - reference.mu)
    intercept = reference.y - reference.x * slope

    box = [reference] + aPoints[index:index + 4]
    xMin = min(point.x for point in box)
    xMax = max(point.x for point in box)
    yMin = min(point.y for point in box)
    yMax = max(point.y for point in box)

    saved = aPoints[index + 1].x
    best = None
    for offset in range(3):
        A, B = aPoints[index + offset], aPoints[index + offset + 1]
        # CROSS rejects diverging rays, and that test needs only the two A points. Applying it
        # before eqs (C23) and (C24) rather than after skips the solve for every pair in a smooth
        # expansion, which is nearly all of them.
        if (A.theta + A.mu) - (B.theta + B.mu) > 0.0:
            continue
        candidate = freeJetSameFamilyPoint(gas, A, B)
        if candidate is None:
            continue
        if not _freeJetCrossed(candidate.x, candidate.y, xMin, xMax, yMin, yMax, A, B, slope, intercept):
            continue
        distance = abs(candidate.x - saved)
        if best is None or distance < best[0]:
            best = (distance, offset, candidate)

    return None if best is None else (best[1], best[2])

def freeJetLeadingCharacteristic(gas, exitMach, thetaN, nozzleRadius, numPoints=60):
    '''
    Points along the leading characteristic, Appendix A. Working below the center line, the lip
    is at y = -nozzleRadius.

    Contoured nozzle (thetaN = 0): parallel exit flow, so the leading characteristic is the
    straight Mach line from the lip.

    Conical nozzle (thetaN > 0): radial source flow, so it is curved and follows (A2), (A3),
    (A6). The Mach number at the center line comes from (A1).
    '''
    if abs(thetaN) < 1e-12:
        machEnd = exitMach
        muN = gas.machAngle(exitMach)
        length = nozzleRadius / math.tan(muN)
        return [PlumeNode(length * (i / (numPoints - 1)),
                      -nozzleRadius * (1.0 - i / (numPoints - 1)),
                      0.0, exitMach, gas, 'leading')
                for i in range(numPoints)]

    # Conical nozzle: radial (source) flow. Eq (A1) fixes the Mach number where the leading
    # characteristic meets the center line.
    nuCenter = gas.nu(exitMach) + 2.0 * thetaN                              # (A1)
    machEnd = gas.machFromNu(nuCenter)
    exponent = (gas.gamma + 1.0) / (4.0 * (gas.gamma - 1.0))

    def logRadius(mach):
        '''Natural log of (A2) without the constant.'''
        return (exponent * np.log(1.0 + (2.0 / (gas.gamma - 1.0)) / mach**2)
                + np.log(mach) / (gas.gamma - 1.0))

    # In the source-flow region the Mach line makes angle mu with the radial flow direction, so
    # d(phi) = -tan(mu) d(ln R) along the leading characteristic. Integrating this from the lip
    # reaches phi = 0 at exactly the Mach number (A1) predicts, which is the check that the
    # geometry here is the one the report intends.
    machSamples = np.linspace(exitMach, machEnd, 20001)
    phi = np.empty_like(machSamples)
    phi[0] = thetaN
    for i in range(1, machSamples.size):
        midMach = 0.5 * (machSamples[i] + machSamples[i - 1])
        phi[i] = phi[i - 1] - math.tan(math.asin(1.0 / midMach)) * (
            logRadius(machSamples[i]) - logRadius(machSamples[i - 1]))
    phi[-1] = 0.0

    # The lip sits at radial distance R_N = r_j / sin(thetaN) from the virtual source apex, so
    # that (A6) places it at y = -r_j.
    radiusLip = nozzleRadius / math.sin(thetaN)
    constant = radiusLip / np.exp(logRadius(exitMach))

    points = []
    indices = np.linspace(0, machSamples.size - 1, numPoints).round().astype(int)
    for index in indices:
        mach = float(machSamples[index])
        angle = float(phi[index])
        radius = constant * np.exp(logRadius(mach))
        x = radius * math.cos(angle) - radiusLip * math.cos(thetaN)             # (A3)
        y = -radius * abs(math.sin(angle))                                    # (A6)
        points.append(PlumeNode(x, y, -angle, mach, gas, 'leading'))
    points[-1] = PlumeNode(points[-1].x, 0.0, 0.0, machEnd, gas, 'leading')
    return points

def freeJetCornerRays(gas, exitMach, thetaN, nozzleRadius, boundaryMach, numRays=40):
    '''
    Centerd expansion fan at the lip. All rays share the lip location; the state steps from the
    exit condition to the jet-boundary condition. Initial turning angle alpha_N = nu_1 - nu_N +
    theta_N, as given in the body of the report.
    '''
    # The first card is the exit state itself. It duplicates the leading characteristic
    # and is never used as a source point, but it keeps the A array index-aligned with
    # the C array exactly as the FORTRAN does (NA is incremented before the first GENL).
    machSteps = np.linspace(exitMach, boundaryMach, numRays + 1)
    rays = []
    for mach in machSteps:
        turning = gas.nu(mach) - gas.nu(exitMach)
        theta = -(turning + thetaN)          # below the center line: turning away from the axis
        rays.append(PlumeNode(0.0, -nozzleRadius, theta, mach, gas, 'cornerRay'))
    return rays

def solveFreeJetNet(gas, exitMach, thetaN, nozzleRadius, ambientOverTotal,
             numRays=30, numLeading=40, maxLines=4000, refine=True, shocks=True,
             lineLimit=800, initialLine=None):
    '''
    Build the free-jet characteristic net.

    Marching, per TN D-2327 p.37: a second-family (downward sloping) line is computed from each
    given point on the leading characteristic until its boundary point is reached. PlumeNode C on
    line j at index i takes A from line j-1 at index i, and B from line j at index i-1. For the
    first line the A points are the corner expansion rays, which all share the lip location.

    Once the leading characteristic is exhausted the net has reached the axis and each line
    instead starts on the center line. That approach is sub-stepped in thirds, and the first-family
    characteristics are watched for crossings, which are the internal shock.

    `initialLine` replaces the leading characteristic with an explicit data line, ordered from the
    lip to the axis. Appendix A builds that line from a source flow of half-angle `thetaN`, which
    suits a conical nozzle and badly misrepresents a contoured one: for the worked LOX/LH2 case it
    puts Mach 8.10 on the axis where the nozzle solution has 4.81, and every line of the march
    starts from that. Passing the exit plane of the characteristic mesh instead removes the
    assumption. `exitMach` and `thetaN` are then read from the first point of the line.

    Returns a dict with the lines, the boundary polyline, the center-line points and the shock.
    '''
    boundaryMach = gas.machFromPressureRatio(ambientOverTotal)
    if initialLine is None:
        leading = freeJetLeadingCharacteristic(gas, exitMach, thetaN, nozzleRadius,
                                               numPoints=numLeading)
    else:
        if len(initialLine) < 3:
            raise ValueError('initialLine needs at least three points, lip to axis')
        leading = list(initialLine)
        # The lip fan expands the wall streamline, so the corner rays start from the state at the
        # wall rather than from a one-dimensional average across the exit.
        exitMach = leading[0].mach
        thetaN = -leading[0].theta
    rays = freeJetCornerRays(gas, exitMach, thetaN, nozzleRadius, boundaryMach, numRays=numRays)

    lipTurn = gas.nu(boundaryMach) - gas.nu(exitMach) + thetaN
    boundaryOrigin = PlumeNode(0.0, -nozzleRadius, -lipTurn, boundaryMach, gas, 'boundary')

    lines = []
    boundary = [boundaryOrigin]
    centerLine = []
    shock = []
    stop = 'maxLines'

    # The A array for line j is the complete line j-1: its start point, its general points and
    # its boundary point, per MOVE C ARRAY (DO 125 I=1,LINE).
    previous = list(rays)
    starts = list(leading[1:])
    startIndex = 0

    boundaryX = [boundaryOrigin.x]
    boundaryY = [boundaryOrigin.y]

    # The center-line march is sub-stepped in thirds, statements 700, 740 and 760. Jumping
    # straight to where the source characteristic meets the axis puts the next line's first
    # off-axis point a rounding error away from the axis, and CENTL from there advances almost
    # nothing, so the net stalls after a single shock cell. Instead the center line takes two
    # steps of a third holding the source point, then lands the true CENTL point on the third and
    # releases the source point forward by one. `cellPhase` is the report's ICELL, cycling 3, 2, 1.
    cellPhase = 3
    deltaX = deltaMu = deltaW = 0.0
    axisPoint = leading[-1]
    centerX, centerMu, centerW = axisPoint.x, axisPoint.mu, axisPoint.W

    while len(lines) < maxLines:
        sourceIndex = 1
        if startIndex < len(starts):
            start = starts[startIndex]
            startIndex += 1
        else:
            if len(previous) < 3:
                stop = 'centerLineExhausted'
                break

            if cellPhase == 3:
                target = freeJetCenterLineTarget(gas, previous[1])
                if target is None:
                    stop = 'centerLineFailed'
                    break
                deltaX = (target[0] - centerX) / 3.0
                deltaMu = (target[1] - centerMu) / 3.0
                deltaW = (target[2] - centerW) / 3.0
                centerX, centerMu, centerW = centerX + deltaX, centerMu + deltaMu, centerW + deltaW
                cellPhase = 2
            elif cellPhase == 2:
                centerX, centerMu, centerW = centerX + deltaX, centerMu + deltaMu, centerW + deltaW
                cellPhase = 1
            else:
                target = freeJetCenterLineTarget(gas, previous[1])
                if target is None:
                    stop = 'centerLineFailed'
                    break
                centerX, centerMu, centerW = target
                # The true CENTL point releases the source point forward, so the line advances.
                sourceIndex = 2
                cellPhase = 3

            start = _finish(gas, centerX, 0.0, 0.0, centerW, 'centerLine')
            if start is None:
                stop = 'centerLineFailed'
                break
            # Over a sub-step the report carries mu as its own interpolated quantity rather than
            # recovering it from W, so the two disagree slightly until the cycle closes on CENTL.
            start.mu = centerMu
            centerLine.append(start)

        line = [start]
        generals = []
        anchor = previous[-1]
        anchorSlope = math.tan(anchor.theta)

        def outside(point):
            '''
            True once a point has passed through the jet boundary. Inside the region already
            solved the boundary is the computed polyline; beyond it the boundary continues along
            the streamline leaving the anchor, eq (C19). Extrapolating that streamline upstream
            instead would place it above every interior point and end the line immediately.

            The polyline lookup is a bisection rather than np.interp because this runs once per
            point of every line, and np.interp rebuilds an array from the boundary list on each
            call, which turns the march into an O(n^2) walk over a boundary that only grows.
            '''
            if point.x > boundaryX[-1]:
                return point.y < anchor.y + (point.x - anchor.x) * anchorSlope
            slot = bisect.bisect_right(boundaryX, point.x)
            if slot == 0:
                return point.y < boundaryY[0]
            if slot >= len(boundaryX):
                return point.y < boundaryY[-1]
            leftX, rightX = boundaryX[slot - 1], boundaryX[slot]
            span = rightX - leftX
            if span <= 0.0:
                return point.y < boundaryY[slot]
            weight = (point.x - leftX) / span
            return point.y < boundaryY[slot - 1] + weight * (boundaryY[slot] - boundaryY[slot - 1])

        # CENTL and OFCNT take the same A entry, and the general loop continues from the next
        # one. Starting the loop earlier would hand it an A point upstream of the new center-line
        # start, whose characteristic never reaches the line being built.
        #
        # The A array is walked by index rather than iterated, because TEST may splice a shock
        # point into it: two first-family rays that cross are replaced by the single same-family
        # point they produce, which removes a wave from the net exactly as statement 726 does.
        aPoints = list(previous)
        index = sourceIndex
        while index < len(aPoints) - 1:
            B = line[-1]
            if shocks and len(line) > 1:
                crossing = freeJetCrossing(gas, aPoints, index, B)
                if crossing is not None:
                    offset, shockPoint = crossing
                    aPoints[index + offset + 1] = shockPoint
                    del aPoints[index + offset]
                    shock.append(shockPoint)
                    continue

            A = aPoints[index]
            C = freeJetNearAxisPoint(gas, A, B) if abs(B.y) < 1e-9 else freeJetGeneralPoint(gas, A, B)
            if C is None or C.y > 0.0 or outside(C):
                break
            generals.append(C)
            line.append(C)
            index += 1

        if not generals:
            stop = 'lineCollapsed'
            break

        bp = freeJetBoundaryPoint(gas, anchor, generals[-1])
        if bp is None or bp.x < anchor.x - 1e-12:
            stop = 'boundaryPointFailed'
            break
        line.append(bp)
        boundary.append(bp)
        boundaryX.append(bp.x)
        boundaryY.append(bp.y)
        lines.append(line)
        previous = freeJetRefineLine(gas, line, limit=lineLimit) if refine else line

    return {
        'boundaryMach': boundaryMach, 'lipTurn': lipTurn,
        'leading': leading, 'rays': rays, 'lines': lines,
        'boundary': boundary, 'centerLine': centerLine, 'shock': shock, 'stop': stop,
        'nodes': [p for ln in lines for p in ln],
    }

def freeJetInitialLine(gas, seed, numPoints = 200):
    '''

    The nozzle exit plane, as a data line the free-jet march can start from.

    Appendix A of TN D-2327 constructs its leading characteristic from a source flow, which
    assumes the exit plane diverges uniformly at the wall angle. A contoured nozzle is built to
    do the opposite: the flow is straightened toward the axis, so the exit is strongly
    non-uniform and the source-flow line is nowhere near it. Taking the mesh column at the exit
    plane replaces the assumption with the solution already in hand.

    Ordering and signs follow the report. The line runs from the lip to the axis, lengths are in
    units of the lip radius, y is negative below the center line, and theta is negative where the
    flow turns away from the axis.

    Parameters:
    -----------
    gas : PlumeGas
    seed : dict
        As returned by `Nozzle.plumeCharacteristicSeed`.
    numPoints : int
        Points to resample the column onto. More of them lets the march start more lines.

    Returns:
    --------
    list of PlumeNode, or None when the mesh carries no usable column at the exit plane.

    '''
    required = ('scalingFactor', 'exitX', 'exitRadius', 'xMesh', 'rMesh',
                'flowAngleMesh', 'machMesh')
    if any(seed.get(key) is None for key in required):
        return None
    scale = seed['scalingFactor']
    exitX = seed['exitX']
    lipRadius = seed['exitRadius']
    if not lipRadius or not scale:
        return None
    # The column is normalized on its own outermost point rather than on the reported exit radius.
    # The mesh is curvilinear, so the column gathered within a tolerance of the exit station can
    # reach a percent or so beyond the lip, and a first point outside the jet boundary ends the
    # march on the line it starts.

    radii, angles, machs = [], [], []
    for xBlock, rBlock, angleBlock, machBlock in zip(seed['xMesh'], seed['rMesh'],
                                                     seed['flowAngleMesh'], seed['machMesh']):
        x = np.asarray(xBlock, dtype = float).ravel() * scale
        r = np.asarray(rBlock, dtype = float).ravel() * scale
        angle = np.asarray(angleBlock, dtype = float).ravel()
        mach = np.asarray(machBlock, dtype = float).ravel()
        keep = np.isfinite(x) & np.isfinite(r) & np.isfinite(angle) & np.isfinite(mach)
        # A tolerance rather than an exact station, because the mesh is curvilinear and its last
        # column is not a straight line of constant x.
        keep &= np.abs(x - exitX) < 0.02 * max(exitX, lipRadius)
        if keep.any():
            radii.append(r[keep])
            angles.append(angle[keep])
            machs.append(mach[keep])

    if not radii:
        return None
    radii = np.concatenate(radii)
    angles = np.concatenate(angles)
    machs = np.concatenate(machs)
    if radii.size < 5:
        return None

    # Lip first, axis last, and one sample per radius so the resampling is single valued.
    order = np.argsort(-radii)
    radii, angles, machs = radii[order], angles[order], machs[order]
    unique = np.concatenate([[True], np.diff(radii) < 0.0])
    radii, angles, machs = radii[unique], angles[unique], machs[unique]
    if radii.size < 5 or machs.min() <= 1.0:
        return None

    # Resample onto an even radial grid running from the lip to the axis. np.interp needs an
    # increasing abscissa, so the sampling is done on radius ascending and then reversed.
    outermost = radii.max()
    sampled = np.linspace(0.0, outermost, numPoints)
    angleAt = np.interp(sampled, radii[::-1], angles[::-1])
    machAt = np.interp(sampled, radii[::-1], machs[::-1])

    line = []
    for radius, angle, mach in zip(sampled[::-1], angleAt[::-1], machAt[::-1]):
        if mach <= 1.0:
            continue
        line.append(PlumeNode(0.0, -radius / outermost, -abs(angle), mach, gas, 'leading'))
    if len(line) < 5:
        return None

    # The march expects its data line to terminate on the axis, where symmetry fixes the angle.
    line[-1] = PlumeNode(line[-1].x, 0.0, 0.0, line[-1].mach, gas, 'leading')
    return line

#--------------------------------------------------------------------------------------------------------------------------#
# -- Plume march: the nozzle characteristics solution continued past the lip -- #
#--------------------------------------------------------------------------------------------------------------------------#

# Inside the nozzle the outer boundary is a wall and the contour prescribes the flow angle. Past
# the lip it is a free streamline at ambient pressure, the flow angle falls out of the solution,
# and nothing else about the problem changes. So the plume is the same march under one different
# boundary condition, which is how the production codes treat it: RAMP2 computes the engine
# interior and the plume expansion in a single characteristics solution.
#
# These unit processes carry the same compatibility relations as `axisymmetricMethodOfCharacteristics`
# inside `truncatedIdealContour`, in the same velocity formulation and the same sign convention:
# r is positive above the center line and the flow angle is positive turning away from it. They are
# written at module scope because the nozzle version is a closure over the contour solver and
# cannot be called from outside it. `testPlumeMarch` checks the interior point against the nozzle
# solver directly, so the two cannot drift apart silently.
#
# Compatibility relations, first family (left running, C+) and second family (right running, C-):
#
#     dtheta = +cot(mu)/V dV - [sin(theta) sin(mu) / sin(theta + mu)] dr / r      (C+)
#     dtheta = -cot(mu)/V dV + [sin(theta) sin(mu) / sin(theta - mu)] dr / r      (C-)

class PlumeFlow:

    '''

    Stagnation state and the gas properties the plume march works in.

    Velocity rather than a velocity ratio, to match the nozzle solver, so that a point handed
    over at the exit plane needs no conversion.

    '''

    def __init__(self, gamma: float, gasConstant: float, stagnationTemperature: float,
                 stagnationPressure: float):
        self.gamma = gamma
        self.gasConstant = gasConstant
        self.stagnationTemperature = stagnationTemperature
        self.stagnationPressure = stagnationPressure
        # Limiting velocity, reached if the flow expanded to zero static temperature.
        self.maxVelocity = math.sqrt(2.0 * gamma * gasConstant * stagnationTemperature
                                   / (gamma - 1.0))

    def velocity(self, mach: float) -> float:
        '''Local velocity [m/s] at a Mach number.'''
        temperature = self.stagnationTemperature / (1.0 + 0.5 * (self.gamma - 1.0) * mach ** 2)
        return math.sqrt(self.gamma * self.gasConstant * temperature) * mach

    def machFromVelocity(self, velocity: float) -> float:
        '''
        Inverse of `velocity`, as the nozzle solver writes it.

        A diverging predictor-corrector step can hand this a velocity past the limiting one or a
        negative one, neither of which is a state. Both return NaN so the caller rejects the point
        rather than taking the square root of a negative number.
        '''
        ratio = velocity / self.maxVelocity
        if not math.isfinite(ratio) or ratio <= 0.0 or ratio >= 1.0:
            return math.nan
        return math.sqrt((2.0 / (self.gamma - 1.0)) * (ratio ** 2 / (1.0 - ratio ** 2)))

    def machFromStaticPressure(self, pressure: float) -> float:
        '''Mach number of an isentropic expansion from the stagnation state to this pressure.'''
        return machFromPressureRatio(self.stagnationPressure / pressure, self.gamma)

    def staticPressure(self, mach: float) -> float:
        '''Static pressure [Pa] at a Mach number.'''
        return self.stagnationPressure \
               * (1.0 + 0.5 * (self.gamma - 1.0) * mach ** 2) ** (-self.gamma / (self.gamma - 1.0))

    def density(self, mach: float) -> float:
        '''Static density [kg/m^3] at a Mach number.'''
        temperature = self.stagnationTemperature / (1.0 + 0.5 * (self.gamma - 1.0) * mach ** 2)
        return self.staticPressure(mach) / (self.gasConstant * temperature)

class PlumePoint:

    '''One node of the plume march. Mach number is the state; velocity and Mach angle follow.'''

    __slots__ = ('x', 'r', 'mach', 'flowAngle', 'machAngle', 'velocity', 'kind')

    def __init__(self, x: float, r: float, mach: float, flowAngle: float, flow: PlumeFlow,
                 kind: str = 'interior'):
        self.x, self.r, self.mach, self.flowAngle = x, r, mach, flowAngle
        self.machAngle = math.asin(1.0 / mach)
        self.velocity = flow.velocity(mach)
        self.kind = kind

    def __repr__(self):
        return (f'PlumePoint({self.kind} x={self.x:.5f} r={self.r:.5f} '
                f'M={self.mach:.4f} th={math.degrees(self.flowAngle):.3f})')

def _leftRunningTerm(point: PlumePoint) -> float:
    '''Axisymmetric source coefficient on a first-family characteristic.'''
    return (math.sin(point.flowAngle) * math.sin(point.machAngle)
            / math.sin(point.flowAngle + point.machAngle))

def _rightRunningTerm(point: PlumePoint) -> float:
    '''Axisymmetric source coefficient on a second-family characteristic.'''
    denominator = math.sin(point.flowAngle - point.machAngle)
    if abs(denominator) < 1e-14:
        return 0.0
    return math.sin(point.flowAngle) * math.sin(point.machAngle) / denominator

def _reciprocalVelocitySlope(point: PlumePoint) -> float:
    '''cot(mu) / V, the coefficient on dV in both compatibility relations.'''
    return (1.0 / math.tan(point.machAngle)) / point.velocity

def plumeInteriorPoint(flow: PlumeFlow, first: PlumePoint, second: PlumePoint,
                       tolerance: float = 1e-8, maxIterations: int = 20) -> PlumePoint:

    '''

    Interior point from a first-family point below it and a second-family point above it.

    Same relations as the nozzle solver, iterated on averaged properties until the intersection
    stops moving. `first` carries the left-running characteristic and sits nearer the axis;
    `second` carries the right-running one and sits nearer the boundary.

    Returns None when the characteristics do not cross ahead of both parents.

    '''
    leftAngle = first.flowAngle + first.machAngle
    rightAngle = second.flowAngle - second.machAngle
    workingMach, workingAngle, workingR = None, None, None
    xIntersection = None

    for _ in range(maxIterations):
        slopeLeft, slopeRight = math.tan(leftAngle), math.tan(rightAngle)
        if abs(slopeLeft - slopeRight) < 1e-14:
            return None
        previousX = xIntersection
        xIntersection = (second.r - first.r - second.x * slopeRight + first.x * slopeLeft) \
                        / (slopeLeft - slopeRight)
        rIntersection = first.r + (xIntersection - first.x) * slopeLeft
        if rIntersection < 0.0:
            return None

        leftTerm, rightTerm = _leftRunningTerm(first), _rightRunningTerm(second)
        slopeOne, slopeTwo = _reciprocalVelocitySlope(first), _reciprocalVelocitySlope(second)
        if first.r <= 0.0 or second.r <= 0.0:
            return None

        velocity = (1.0 / (slopeOne + slopeTwo)) \
                   * (first.velocity * slopeOne + second.velocity * slopeTwo
                      + (leftTerm / first.r) * (rIntersection - first.r)
                      + (rightTerm / second.r) * (rIntersection - second.r)
                      + second.flowAngle - first.flowAngle)
        mach = flow.machFromVelocity(velocity)
        if not math.isfinite(mach) or mach <= 1.0:
            return None

        fromFirst = first.flowAngle + slopeOne * (velocity - first.velocity) \
                    - (leftTerm / first.r) * (rIntersection - first.r)
        fromSecond = second.flowAngle - slopeTwo * (velocity - second.velocity) \
                     + (rightTerm / second.r) * (rIntersection - second.r)
        flowAngle = 0.5 * (fromFirst + fromSecond)

        workingMach, workingAngle, workingR = mach, flowAngle, rIntersection
        if previousX is not None and abs(xIntersection - previousX) \
                <= tolerance * max(abs(xIntersection), 1e-12):
            break

        # Second order: advance on the mean of the parent and the new estimate.
        machAngle = math.asin(1.0 / mach)
        leftAngle = 0.5 * ((first.flowAngle + first.machAngle) + (flowAngle + machAngle))
        rightAngle = 0.5 * ((second.flowAngle - second.machAngle) + (flowAngle - machAngle))

    # The radius has to come from the pass that produced the abscissa. Recomputing it here from
    # `leftAngle` would use the slope the loop has already advanced for the next pass.
    if workingMach is None or workingR is None:
        return None
    if xIntersection < max(first.x, second.x) - 1e-9 or workingR < 0.0:
        return None
    return PlumePoint(xIntersection, workingR, workingMach, workingAngle, flow, 'interior')

def plumeAxisPoint(flow: PlumeFlow, second: PlumePoint, tolerance: float = 1e-8,
                   maxIterations: int = 20) -> PlumePoint:

    '''

    Point where a second-family characteristic reaches the center line.

    Symmetry fixes the flow angle at zero, so the single compatibility relation along that
    characteristic determines the velocity rather than the angle.

    '''
    rightAngle = second.flowAngle - second.machAngle
    workingMach = None
    xIntersection = None

    for _ in range(maxIterations):
        slopeRight = math.tan(rightAngle)
        if abs(slopeRight) < 1e-14:
            return None
        previousX = xIntersection
        xIntersection = second.x - second.r / slopeRight
        if xIntersection < second.x - 1e-12:
            return None

        rightTerm = _rightRunningTerm(second)
        slopeTwo = _reciprocalVelocitySlope(second)
        # theta_C = 0 in the second-family relation, solved for the velocity.
        velocity = second.velocity \
                   + (second.flowAngle + (rightTerm / second.r) * (0.0 - second.r)) / slopeTwo
        mach = flow.machFromVelocity(velocity)
        if not math.isfinite(mach) or mach <= 1.0:
            return None
        workingMach = mach

        if previousX is not None and abs(xIntersection - previousX) \
                <= tolerance * max(abs(xIntersection), 1e-12):
            break
        rightAngle = 0.5 * ((second.flowAngle - second.machAngle) + (0.0 - math.asin(1.0 / mach)))

    if workingMach is None:
        return None
    return PlumePoint(xIntersection, 0.0, workingMach, 0.0, flow, 'axis')

def plumeNearAxisPoint(flow: PlumeFlow, axisPoint: PlumePoint, second: PlumePoint,
                       tolerance: float = 1e-8, maxIterations: int = 20) -> PlumePoint:

    """

    First point off the center line, where the first-family parent sits on the axis.

    The axisymmetric source term carries dr / r, which is singular there, so the first-family
    relation cannot be applied as written. The nozzle solver meets the same problem at the axis
    and answers it the same way: drop the singular term and close the pair as a small linear
    system in flow angle and velocity. This is the direct solution of the two rows that
    `axisymmetricMethodOfCharacteristics` assembles and reduces.

        theta - (n1 / 2) V           = -(n1 V1) / 2
        -theta / (n1 + n2) +   V     = P

    with P collecting the second-family relation, which is regular because that parent is off the
    axis.

    """
    leftAngle = axisPoint.flowAngle + axisPoint.machAngle
    rightAngle = second.flowAngle - second.machAngle
    workingMach, workingAngle, workingR = None, None, None
    xIntersection = None

    for _ in range(maxIterations):
        slopeLeft, slopeRight = math.tan(leftAngle), math.tan(rightAngle)
        if abs(slopeLeft - slopeRight) < 1e-14 or second.r <= 0.0:
            return None
        previousX = xIntersection
        xIntersection = (second.r - axisPoint.r - second.x * slopeRight
                         + axisPoint.x * slopeLeft) / (slopeLeft - slopeRight)
        rIntersection = axisPoint.r + (xIntersection - axisPoint.x) * slopeLeft
        if rIntersection < 0.0:
            return None

        slopeOne = _reciprocalVelocitySlope(axisPoint)
        slopeTwo = _reciprocalVelocitySlope(second)
        rightTerm = _rightRunningTerm(second)
        collected = (1.0 / (slopeOne + slopeTwo))                     * (axisPoint.velocity * slopeOne + second.velocity * slopeTwo
                       + (rightTerm / second.r) * (rIntersection - second.r)
                       + second.flowAngle)

        denominator = 1.0 - slopeOne / (2.0 * (slopeOne + slopeTwo))
        if abs(denominator) < 1e-14:
            return None
        flowAngle = 0.5 * slopeOne * (collected - axisPoint.velocity) / denominator
        velocity = collected + flowAngle / (slopeOne + slopeTwo)
        mach = flow.machFromVelocity(velocity)
        if not math.isfinite(mach) or mach <= 1.0:
            return None

        workingMach, workingAngle, workingR = mach, flowAngle, rIntersection
        if previousX is not None and abs(xIntersection - previousX)                 <= tolerance * max(abs(xIntersection), 1e-12):
            break
        machAngle = math.asin(1.0 / mach)
        leftAngle = 0.5 * ((axisPoint.flowAngle + axisPoint.machAngle) + (flowAngle + machAngle))
        rightAngle = 0.5 * ((second.flowAngle - second.machAngle) + (flowAngle - machAngle))

    if workingMach is None or workingR is None:
        return None
    if xIntersection < max(axisPoint.x, second.x) - 1e-9 or workingR < 0.0:
        return None
    return PlumePoint(xIntersection, workingR, workingMach, workingAngle, flow, 'nearAxis')

def plumeFreeBoundaryPoint(flow: PlumeFlow, first: PlumePoint, previous: PlumePoint,
                           boundaryMach: float, tolerance: float = 1e-8,
                           maxIterations: int = 20) -> PlumePoint:

    '''

    Point on the free jet boundary, the one process the nozzle march has no equivalent of.

    A wall prescribes the flow angle and leaves the pressure to the solution. A free boundary is
    the reverse: static pressure equals ambient all along it, so the Mach number is fixed and it
    is the flow angle that the solution returns. The boundary is a streamline, so the new point
    lies where the first-family characteristic arriving from inside meets the streamline leaving
    the previous boundary point.

    Parameters:
    -----------
    first : PlumePoint
        The interior point whose left-running characteristic reaches the boundary.
    previous : PlumePoint
        The boundary point upstream of this one, which the streamline leaves.
    boundaryMach : float
        Mach number of an isentropic expansion to ambient pressure, constant along the boundary.

    '''
    boundaryVelocity = flow.velocity(boundaryMach)
    leftAngle = first.flowAngle + first.machAngle
    streamAngle = previous.flowAngle
    workingAngle, workingR = None, None
    xIntersection = None

    for _ in range(maxIterations):
        slopeLeft, slopeStream = math.tan(leftAngle), math.tan(streamAngle)
        if abs(slopeLeft - slopeStream) < 1e-14:
            return None
        previousX = xIntersection
        xIntersection = (previous.r - first.r - previous.x * slopeStream + first.x * slopeLeft) \
                        / (slopeLeft - slopeStream)
        rIntersection = first.r + (xIntersection - first.x) * slopeLeft
        if rIntersection <= 0.0 or first.r <= 0.0:
            return None

        leftTerm = _leftRunningTerm(first)
        slopeOne = _reciprocalVelocitySlope(first)
        flowAngle = first.flowAngle + slopeOne * (boundaryVelocity - first.velocity) \
                    - (leftTerm / first.r) * (rIntersection - first.r)
        workingAngle, workingR = flowAngle, rIntersection

        if previousX is not None and abs(xIntersection - previousX) \
                <= tolerance * max(abs(xIntersection), 1e-12):
            break
        machAngle = math.asin(1.0 / boundaryMach)
        leftAngle = 0.5 * ((first.flowAngle + first.machAngle) + (flowAngle + machAngle))
        streamAngle = 0.5 * (previous.flowAngle + flowAngle)

    if workingAngle is None or workingR is None:
        return None
    if xIntersection < first.x - 1e-9 or workingR <= 0.0:
        return None
    return PlumePoint(xIntersection, workingR, boundaryMach, workingAngle, flow, 'boundary')

def plumeSameFamilyPoint(flow: PlumeFlow, inner: PlumePoint, outer: PlumePoint,
                         tolerance: float = 1e-8, maxIterations: int = 20) -> PlumePoint:

    """

    Two first-family characteristics crossing, which is where the internal shock forms.

    Compression waves reflected from the jet boundary travel inward and steepen. Where one
    overtakes the one ahead of it the characteristics cross, the solution would otherwise become
    multivalued, and the physical answer is that they have coalesced. This merges the pair into
    the point they meet at: TN D-2327's solution case 3, its `SAMFM`.

    Only two things change from the interior point. The outer ray is followed along its
    first-family slope rather than its second-family one, eq (C23), and its source coefficient
    takes the first-family denominator, eq (C24). The closure on flow angle and velocity is the
    interior one unchanged, which is what the report does and what keeps it conditioned: closing
    it instead by subtracting the two relations is singular whenever the parents carry nearly the
    same state, which adjacent points on a line almost always do.

    This is a coalescence, not a fitted shock. No Rankine-Hugoniot jump is applied and the net
    stays isentropic, which is the assumption the whole formulation rests on. That holds while the
    shock is weak, because entropy rise is third order in shock strength, and degrades as it
    strengthens.

    """
    innerAngle = inner.flowAngle + inner.machAngle
    outerAngle = outer.flowAngle + outer.machAngle
    workingMach, workingAngle, workingR = None, None, None
    xIntersection = None

    for _ in range(maxIterations):
        slopeInner, slopeOuter = math.tan(innerAngle), math.tan(outerAngle)
        if abs(slopeInner - slopeOuter) < 1e-14 or inner.r <= 0.0 or outer.r <= 0.0:
            return None
        previousX = xIntersection
        xIntersection = (outer.r - inner.r - outer.x * slopeOuter + inner.x * slopeInner)                         / (slopeInner - slopeOuter)
        rIntersection = inner.r + (xIntersection - inner.x) * slopeInner
        if rIntersection < 0.0:
            return None

        # Both source coefficients take the first-family denominator, eqs (C9) and (C24).
        innerTerm, outerTerm = _leftRunningTerm(inner), _leftRunningTerm(outer)
        slopeOne = _reciprocalVelocitySlope(inner)
        slopeTwo = _reciprocalVelocitySlope(outer)

        velocity = (1.0 / (slopeOne + slopeTwo))                    * (inner.velocity * slopeOne + outer.velocity * slopeTwo
                      + (innerTerm / inner.r) * (rIntersection - inner.r)
                      + (outerTerm / outer.r) * (rIntersection - outer.r)
                      + outer.flowAngle - inner.flowAngle)
        mach = flow.machFromVelocity(velocity)
        if not math.isfinite(mach) or mach <= 1.0:
            return None

        fromInner = inner.flowAngle + slopeOne * (velocity - inner.velocity)                     - (innerTerm / inner.r) * (rIntersection - inner.r)
        fromOuter = outer.flowAngle - slopeTwo * (velocity - outer.velocity)                     + (outerTerm / outer.r) * (rIntersection - outer.r)
        flowAngle = 0.5 * (fromInner + fromOuter)

        workingMach, workingAngle, workingR = mach, flowAngle, rIntersection
        if previousX is not None and abs(xIntersection - previousX)                 <= tolerance * max(abs(xIntersection), 1e-12):
            break
        machAngle = math.asin(1.0 / mach)
        innerAngle = 0.5 * ((inner.flowAngle + inner.machAngle) + (flowAngle + machAngle))
        outerAngle = 0.5 * ((outer.flowAngle + outer.machAngle) + (flowAngle + machAngle))

    if workingMach is None or workingR is None:
        return None
    if xIntersection < max(inner.x, outer.x) - 1e-9 or workingR < 0.0:
        return None
    return PlumePoint(xIntersection, workingR, workingMach, workingAngle, flow, 'shock')

def _plumeCrossed(x, r, xMin, xMax, rMin, rMax, inner, outer, slope, intercept) -> bool:

    '''

    Whether one candidate coalescence point is a crossing this line owns, subroutine CROSS.

    Three conditions in the order the listing applies them: the candidate lies inside the box
    spanning the points that produced it, the two rays are converging rather than diverging, and
    it lies beyond the second-family line through the last point placed on the line being built.

    '''
    if not (rMin < r < rMax) or not (xMin < x < xMax):
        return False
    # Converging: walking outward, the inner ray must be no shallower than the one ahead of it.
    if (inner.flowAngle + inner.machAngle) - (outer.flowAngle + outer.machAngle) < 0.0:
        return False
    residual = r - slope * x
    return residual <= intercept if slope < 0.0 else residual >= intercept

def plumeShockCrossing(flow: PlumeFlow, aPoints: list, index: int, reference: PlumePoint,
                       coalescenceRange: float = None):

    '''

    Where the internal shock forms on this line, subroutine TEST.

    Three candidates are built from the consecutive first-family pairs starting at `index` and
    each is put to `_plumeCrossed`. Where more than one qualifies the nearest to the station the
    search began from wins, which is the selection statements 740, 760, 770 and 780 make.

    The box the report draws round the candidates does not discriminate at high resolution. It
    spans four neighboring points of the previous line and one point of the current one, so its
    axial extent is set by the line spacing while its radial extent shrinks as the line is
    refined. Two almost parallel characteristics then appear to cross inside it even though they
    would not meet for many jet radii, and every such false merge deletes a wave the net needed.
    `coalescenceRange` is the physical scale that fixes it: a crossing only counts as coalescence
    if it happens within that distance of the parents, which the caller sets from the local jet
    radius rather than from the mesh.

    Returns the offset of the pair that crosses and the point it coalesces to, or None while the
    characteristics are still diverging and the flow is smooth.

    '''
    if index + 3 >= len(aPoints):
        return None

    # The candidate has to lie beyond the characteristic the march is building along, or it
    # belongs to a line already computed. That is the report's second family; mirrored above the
    # center line it is the first, so the slope is theta + mu rather than theta - mu.
    slope = math.tan(reference.flowAngle + reference.machAngle)
    intercept = reference.r - reference.x * slope

    box = [reference] + aPoints[index:index + 4]
    xMin = min(point.x for point in box)
    xMax = max(point.x for point in box)
    rMin = min(point.r for point in box)
    rMax = max(point.r for point in box)

    saved = aPoints[index + 1].x
    best = None
    for offset in range(3):
        inner, outer = aPoints[index + offset], aPoints[index + offset + 1]
        # The convergence test needs only the two parents, so applying it before the solve skips
        # the work for every pair in a smooth expansion, which is nearly all of them.
        if (inner.flowAngle + inner.machAngle) - (outer.flowAngle + outer.machAngle) < 0.0:
            continue
        candidate = plumeSameFamilyPoint(flow, inner, outer)
        if candidate is None:
            continue
        if coalescenceRange is not None                 and candidate.x - max(inner.x, outer.x) > coalescenceRange:
            continue
        if not _plumeCrossed(candidate.x, candidate.r, xMin, xMax, rMin, rMax,
                             inner, outer, slope, intercept):
            continue
        distance = abs(candidate.x - saved)
        if best is None or distance < best[0]:
            best = (distance, offset, candidate)

    return None if best is None else (best[1], best[2])

def plumeMassFlux(flow: PlumeFlow, line: list) -> float:

    """

    Mass flow through a characteristic line [kg/s].

    Every line of the march spans the jet from the center line to the free boundary, so every one
    of them carries the whole mass flow and they must all carry the same. Checking that needs
    nothing external, which makes it the one measure of solution quality available at any
    operating point, including those with no correlation to compare against.

    Integrates rho (V . n) over the line, with n the segment normal and the area element the
    surface of revolution, 2 pi r ds, by the trapezoidal rule along each segment.

    """
    total = 0.0
    for first, second in zip(line[:-1], line[1:]):
        deltaX, deltaR = second.x - first.x, second.r - first.r
        length = math.hypot(deltaX, deltaR)
        if length <= 0.0:
            continue
        normalX, normalR = deltaR / length, -deltaX / length
        for point in (first, second):
            through = point.velocity * (math.cos(point.flowAngle) * normalX
                                        + math.sin(point.flowAngle) * normalR)
            total += 0.5 * flow.density(point.mach) * through                      * 2.0 * math.pi * max(point.r, 0.0) * length
    return abs(total)

def plumeMachDisk(flow: PlumeFlow, net: dict, sonicThreshold: float = 1.05) -> dict:

    """

    Locate the Mach disk in a solved plume field.

    Taken from the solution rather than from a correlation. The disk is where the center-line flow
    can no longer stay supersonic, so its station is the first on the axis at which the Mach number
    falls to one, and its radius is found by scanning outward from there to the triple point, the
    radial station where the flow is again sonic. That is the procedure the coflowing-jet study
    (arXiv 2608.18923) applies to an inviscid characteristics field, and it needs no scaling law.

    Whether a disk forms at all is the regular against Mach reflection question, and the classical
    answer is the detachment condition: where the turning the flow must accomplish on the axis
    exceeds what an attached oblique shock can deliver at the local Mach number, the reflection
    cannot be regular and carries a disk. `obliqueShockDeflection` already returns zero at exactly
    that point, so it is reused rather than restated.

    Exactly sonic is not a state this net can hold: every node is supersonic by construction, and
    a center line that truly reached Mach one would end the march rather than record it. So the
    test is made against `sonicThreshold`, a Mach number close enough to one that the core is
    plainly about to fail, and `minimumAxisMach` is always reported so a caller can see how near it
    came rather than only whether it crossed.

    Returns a dict with `present`, and when present the axial station, diameter and the Mach number
    just ahead of the disk. A net with no shock in it will not usually decelerate its core that
    far, and reporting no disk is then the right answer: a disk appears above a nozzle pressure
    ratio of roughly 3.5 and it is a shock, which this net does not carry.

    """
    absent = {'present': False, 'x': float('nan'), 'diameter': float('nan'),
              'upstreamMach': float('nan'), 'minimumAxisMach': float('nan'),
              'reason': 'the core stays supersonic on the axis'}
    nodes = net.get('nodes') or []
    if not nodes:
        return dict(absent, reason = 'no solved field')

    axis = sorted((point for point in nodes if point.r <= 1e-9), key = lambda point: point.x)
    if len(axis) < 3:
        return dict(absent, reason = 'the march did not reach the center line')

    minimumAxisMach = min(point.mach for point in axis)
    absent = dict(absent, minimumAxisMach = minimumAxisMach)
    sonic = next((point for point in axis if point.mach <= sonicThreshold), None)
    if sonic is None:
        return absent

    # Triple point: scan outward just behind the disk for the radius at which the flow is sonic
    # again. The slip line leaves that point, and the disk spans twice its radius.
    # The scan window is a length, taken from the radial extent of the field, rather than a
    # fraction of the axial station, which would collapse near the lip and sprawl far downstream.
    extent = max((point.r for point in nodes), default = 0.0)
    window = 0.25 * extent if extent > 0.0 else 0.0
    station = [point for point in nodes if sonic.x < point.x <= sonic.x + window]
    triple = next((point for point in sorted(station, key = lambda point: point.r)
                   if point.mach > sonicThreshold), None)
    diameter = 2.0 * triple.r if triple is not None else float('nan')
    upstream = max((point.mach for point in axis if point.x < sonic.x), default = float('nan'))
    return {'present': True, 'x': sonic.x, 'diameter': diameter, 'upstreamMach': upstream,
            'minimumAxisMach': minimumAxisMach,
            'reason': f'the center line fell to Mach {sonic.mach:.3f}'}

def _crossingsAlongRows(x, r, angle, mach, exitX):

    '''Where each row of a mesh block crosses the exit plane, and the state it carries there.'''

    found = []
    for index in range(x.shape[0]):
        usable = (np.isfinite(x[index]) & np.isfinite(r[index])
                  & np.isfinite(angle[index]) & np.isfinite(mach[index]))
        if usable.sum() < 2:
            continue
        rowX = x[index][usable]
        order = np.argsort(rowX)
        rowX = rowX[order]
        if rowX[0] > exitX or rowX[-1] < exitX:
            continue
        rowR = r[index][usable][order]
        rowAngle = angle[index][usable][order]
        rowMach = mach[index][usable][order]
        advancing = np.concatenate(([True], np.diff(rowX) > 0.0))
        if advancing.sum() < 2:
            continue
        rowX, rowR = rowX[advancing], rowR[advancing]
        rowAngle, rowMach = rowAngle[advancing], rowMach[advancing]
        found.append((float(np.interp(exitX, rowX, rowR)),
                      float(np.interp(exitX, rowX, rowAngle)),
                      float(np.interp(exitX, rowX, rowMach))))

    return found

def _exitPlaneCrossings(seed: dict, scale: float, exitX: float):

    '''

    The state on the exit plane, taken where each mesh characteristic actually crosses it.

    The mesh is stored as structured blocks whose rows march downstream, so a row that spans the
    exit abscissa crosses it once and the state there follows by interpolating along that row. That
    is a point on the plane rather than a point near it.

    Gathering every node within a tolerance of the exit abscissa instead, and then sorting the
    cloud by radius, is what this replaces. None of the nodes it collected lay on the plane: on the
    shipped nozzle all forty spanned 31 mm of axial distance about an exit at 800 mm, and the flow
    is still expanding across that distance. Sorting them by radius alone mapped an axial variation
    onto the radial coordinate, so walking outward alternately sampled upstream and downstream
    nodes. The profile it produced sawtoothed by 0.4 degrees in flow angle near the lip, against a
    Prandtl-Meyer turn of 0.62 degrees for the same nozzle near its design point, and it was not
    monotone in either Mach number or flow angle. A truncated ideal contour leaves neither.

    Returns radius, flow angle and Mach number, ascending in radius, or None.

    '''

    # A node is on the plane or it is not. The tolerance is rounding, not a band: the defect this
    # replaces came from treating 2 percent of the nozzle length as "on the exit plane".
    onThePlane = 1e-9 * max(1.0, abs(exitX))

    found = []
    for xBlock, rBlock, angleBlock, machBlock in zip(seed['xMesh'], seed['rMesh'],
                                                     seed['flowAngleMesh'], seed['machMesh']):
        x = np.asarray(xBlock, dtype = float) * scale
        r = np.asarray(rBlock, dtype = float) * scale
        angle = np.asarray(angleBlock, dtype = float)
        mach = np.asarray(machBlock, dtype = float)
        if r.shape != x.shape or angle.shape != x.shape or mach.shape != x.shape:
            continue

        # A block that already lies in the exit plane needs no interpolation, which is how a
        # solver that hands over its exit station directly presents it.
        exact = (np.isfinite(x) & np.isfinite(r) & np.isfinite(angle) & np.isfinite(mach)
                 & (np.abs(x - exitX) <= onThePlane))
        if exact.any():
            found.extend(zip(r[exact].ravel(), angle[exact].ravel(), mach[exact].ravel()))
            continue

        if x.ndim != 2:
            continue
        rows = _crossingsAlongRows(x, r, angle, mach, exitX)
        # A mesh stored the other way round has its characteristics down the columns.
        found.extend(rows if rows else _crossingsAlongRows(x.T, r.T, angle.T, mach.T, exitX))

    usable = [row for row in found if math.isfinite(row[0]) and row[2] > 1.0]
    if len(usable) < 5:
        return None

    usable.sort(key = lambda row: row[0])
    radii = np.array([row[0] for row in usable])
    angles = np.array([row[1] for row in usable])
    machs = np.array([row[2] for row in usable])

    advancing = np.concatenate(([True], np.diff(radii) > 0.0))

    return radii[advancing], angles[advancing], machs[advancing]

def plumeExitLine(flow: PlumeFlow, seed: dict, numPoints: int = 120) -> list:

    '''

    The nozzle exit plane as a data line for the plume march, ordered lip to axis.

    This is the handover. The contour solve already knows the flow across the exit plane, so the
    plume starts from it rather than from an assumption about it. Coordinates stay dimensional and
    in the nozzle's own frame, so nothing is scaled on the way across.

    Returns None when the contour carries no characteristic mesh, which is the conical case.

    '''
    required = ('scalingFactor', 'exitX', 'exitRadius', 'xMesh', 'rMesh',
                'flowAngleMesh', 'machMesh')
    if any(seed.get(key) is None for key in required):
        return None
    scale, exitX, exitRadius = seed['scalingFactor'], seed['exitX'], seed['exitRadius']
    if not scale or not exitRadius:
        return None

    crossings = _exitPlaneCrossings(seed, scale, exitX)
    if crossings is None:
        return None
    radii, angles, machs = crossings

    sampled = np.linspace(0.0, radii.max(), numPoints)
    angleAt = np.interp(sampled, radii, angles)
    machAt = np.interp(sampled, radii, machs)

    # Lip first, axis last, matching the order the march consumes start points in.
    line = [PlumePoint(exitX, radius, mach, abs(angle), flow, 'exit')
            for radius, angle, mach in zip(sampled[::-1], angleAt[::-1], machAt[::-1])
            if mach > 1.0]
    if len(line) < 5:
        return None
    line[-1] = PlumePoint(exitX, 0.0, line[-1].mach, 0.0, flow, 'exit')
    return line

def plumeCornerFan(flow: PlumeFlow, lip: PlumePoint, boundaryMach: float,
                   numRays: int = 40) -> list:

    '''

    Centerd expansion fan at the lip, where the wall boundary condition becomes a free one.

    The wall stops constraining the flow at the lip, so it turns through a Prandtl-Meyer expansion
    from the wall state to the ambient pressure. Every ray shares the lip position and they differ
    only in how far through the turn they sit, which is what makes the fan centered.

    '''
    lipNu = prandtlMeyerAngle(lip.mach, flow.gamma)
    machSteps = np.linspace(lip.mach, boundaryMach, numRays + 1)
    fan = []
    for mach in machSteps:
        if mach <= 1.0:
            continue
        turning = prandtlMeyerAngle(mach, flow.gamma) - lipNu
        fan.append(PlumePoint(lip.x, lip.r, mach, lip.flowAngle + turning, flow, 'cornerRay'))
    return fan

def solvePlumeMarch(flow: PlumeFlow, initialLine: list, ambientPressure: float,
                    numRays: int = 40, maxLines: int = 3000,
                    refineFraction: float = 0.10, lineLimit: int = 600,
                    shocks: bool = False, shockRange: float = 0.25) -> dict:

    '''

    March the characteristics net from the nozzle exit plane out into the plume.

    `shocks` drives the coalescence of crossing same-family characteristics and defaults off. It
    behaves correctly in one respect, firing more often as the pressure ratio rises: 0.3 merges
    per line at Pe/Pa 1.5, 0.95 at 5 and 1.5 at 20. But the crossing test it rests on is
    resolution dependent. Neighboring characteristics on a refined line cross locally under any
    convergence at all, so the detector fires on weak compression that would not coalesce for many
    jet radii, and each false merge deletes a wave. On a parallel exit at Pe/Pa 1.5, where the
    reflected compressions have not coalesced and the pattern is genuinely isentropic, it cuts the
    march from 3 790 lines to 119. Detecting a true envelope needs a criterion that does not scale
    with mesh spacing, and until there is one this stays off by default.

    `numRays` sets how finely the lip fan is discretized, and the right value is not settled. On a
    uniform exit line held at fourteen degrees, mass drift falls from 7.2 percent at forty rays to
    1.2 at a hundred and twenty and barely moves again by three hundred and sixty. On the exit
    plane of an actual contoured nozzle it goes the other way: a hundred and twenty rays cut the
    march from three hundred and thirty-nine lines to thirty-nine. The default stays at forty
    because that is what the real handover tolerates, and the disagreement between the two is
    unexplained rather than resolved.

    Structure follows TN D-2327 p.37 in NOVA's sign convention, where r is positive above the
    center line. Each line is a first-family characteristic running from a start point outward
    until it reaches the free boundary. Point C at index i on line j takes its second-family
    neighbor from index i of line j-1 and its first-family neighbor from index i-1 of line j.
    Start points come from the exit plane, lip first.

    Returns a dict with the lines, the boundary streamline and why the march stopped.

    '''
    if not initialLine or len(initialLine) < 3:
        return {'lines': [], 'boundary': [], 'nodes': [], 'shock': [], 'stop': 'noInitialLine',
                'boundaryMach': 0.0, 'referenceFlux': 0.0, 'fluxSamples': [],
                'massDriftWorst': float('nan'), 'massDriftFinal': float('nan')}

    boundaryMach = flow.machFromStaticPressure(ambientPressure)
    lip = initialLine[0]

    # An overexpanded lip turns the flow inward. Strictly that turn is an oblique shock, and this
    # takes it as an isentropic compression instead, which is the same fan machinery run with a
    # falling Mach number. The approximation is measured rather than assumed: at exit Mach 3 the
    # isentropic turn matches the shock turn to 0.2 percent down to Pe/Pa 0.6 and 0.8 percent at
    # 0.4, and the stagnation pressure the shock would cost is 1.3 and 7.4 percent there. Below
    # about 0.4 the nozzle separates internally anyway, by the Summerfield criterion, and no
    # attached plume model applies. Both numbers are returned so a caller can judge.
    lipPressure = flow.staticPressure(lip.mach)
    shockDeflection, shockMach, stagnationRatio = 0.0, lip.mach, 1.0
    if ambientPressure > lipPressure:
        shockDeflection, shockMach, stagnationRatio = obliqueShockState(
            lip.mach, flow.gamma, ambientPressure / lipPressure)

    # The initial line has to satisfy the condition every line the march builds satisfies: the
    # flow crosses the center line straight. A uniform Mach number at a constant nonzero flow
    # angle does not, and it is an easy line to write by hand, so it is refused rather than
    # marched. Measured on a Mach 3 exit at Pe/Pa 1.05, marching one costs 4.5 percent of the mass
    # flow at two degrees and 70 at eight, against 0.11 and 0.36 for the conical source flow that
    # is the exact exit of a conical nozzle. The exit plane of a contoured nozzle comes from the
    # characteristic mesh through `plumeExitLine` and satisfies this already.
    axisPoint = min(initialLine, key = lambda point: abs(point.r))

    refusal = None
    if abs(boundaryMach - lip.mach) < 1e-9:
        refusal = 'perfectlyExpanded'
    elif boundaryMach <= 1.0 or not math.isfinite(boundaryMach):
        refusal = 'boundarySubsonic'
    elif ambientPressure > lipPressure and shockDeflection <= 0.0:
        refusal = 'shockDetached'
    elif abs(axisPoint.r) <= centerLineRadiusTolerance \
            and abs(axisPoint.flowAngle) > centerLineAngleTolerance:
        refusal = 'initialLineNotSymmetric'
    if refusal is not None:
        return {'lines': [], 'boundary': [], 'nodes': [], 'shock': [], 'stop': refusal,
                'boundaryMach': boundaryMach, 'referenceFlux': 0.0, 'fluxSamples': [],
                'massDriftWorst': float('nan'), 'massDriftFinal': float('nan'),
                'lipShockDeflection': shockDeflection, 'lipStagnationRatio': stagnationRatio}

    fan = plumeCornerFan(flow, lip, boundaryMach, numRays = numRays)
    boundaryOrigin = PlumePoint(lip.x, lip.r, boundaryMach, fan[-1].flowAngle, flow, 'boundary')

    lines, boundary, shock = [], [boundaryOrigin], []
    referenceFlux = plumeMassFlux(flow, initialLine)
    fluxSamples = []
    boundaryX, boundaryR = [boundaryOrigin.x], [boundaryOrigin.r]
    previous = list(fan)
    starts = list(initialLine[1:])
    startIndex = 0
    stop = 'maxLines'

    # Once the exit plane stops supplying start points the net has reached the axis, and every
    # further line has to start there instead. Stepping straight to where the source
    # characteristic meets the axis stalls the march, because the first point off the axis on the
    # previous line sits a rounding error away from it and the axis then advances by almost
    # nothing. TN D-2327 sub-steps that approach in thirds, holding the source point for two
    # passes and releasing it forward on the third; `cellPhase` is its ICELL, cycling 3, 2, 1.
    axisSource = initialLine[-1]
    axisX, axisMach = axisSource.x, axisSource.mach
    cellPhase = 3
    deltaX = deltaMach = 0.0

    def outsideBoundary(point):
        '''
        Past the jet boundary. Inside the solved range the boundary is the computed polyline.

        Downstream of the last boundary point there is no boundary to test against, so points
        there are left to the boundary point solve, which carries the streamline properly. The
        line is bounded anyway by the length of the array it marches against. In practice the
        branch is almost never taken, since interior points land upstream of the boundary the
        previous line placed.
        '''
        if point.x > boundaryX[-1]:
            return False
        slot = bisect.bisect_right(boundaryX, point.x)
        if slot <= 0:
            return point.r > boundaryR[0]
        if slot >= len(boundaryX):
            return point.r > boundaryR[-1]
        span = boundaryX[slot] - boundaryX[slot - 1]
        if span <= 0.0:
            return point.r > boundaryR[slot]
        weight = (point.x - boundaryX[slot - 1]) / span
        return point.r > boundaryR[slot - 1] + weight * (boundaryR[slot] - boundaryR[slot - 1])

    while len(lines) < maxLines:
        sourceIndex = 1
        if startIndex < len(starts):
            start = starts[startIndex]
            startIndex += 1
        else:
            if len(previous) < 3:
                stop = 'centerLineExhausted'
                break
            if cellPhase == 3:
                target = plumeAxisPoint(flow, previous[1])
                if target is None:
                    stop = 'axisPointFailed'
                    break
                deltaX = (target.x - axisX) / 3.0
                deltaMach = (target.mach - axisMach) / 3.0
                axisX, axisMach = axisX + deltaX, axisMach + deltaMach
                cellPhase = 2
            elif cellPhase == 2:
                axisX, axisMach = axisX + deltaX, axisMach + deltaMach
                cellPhase = 1
            else:
                target = plumeAxisPoint(flow, previous[1])
                if target is None:
                    stop = 'axisPointFailed'
                    break
                axisX, axisMach = target.x, target.mach
                # The true axis point releases the source forward, so the march advances.
                sourceIndex = 2
                cellPhase = 3
            if axisMach <= 1.0 or not math.isfinite(axisMach):
                stop = 'axisPointFailed'
                break
            start = PlumePoint(axisX, 0.0, axisMach, 0.0, flow, 'axis')

        line = [start]
        interiors = []
        anchor = boundary[-1]
        # The A array is walked by index rather than iterated, because a coalescence splices into
        # it: two first-family rays that cross are replaced by the single point they merge to,
        # which removes a wave from the net.
        aPoints = previous
        copied = False
        index = sourceIndex
        while index < len(aPoints):
            first = line[-1]
            if shocks and len(line) > 1:
                crossing = plumeShockCrossing(flow, aPoints, index, first,
                                              coalescenceRange = shockRange * anchor.r)
                if crossing is not None:
                    offset, merged = crossing
                    if not copied:
                        aPoints, copied = list(previous), True
                    aPoints[index + offset + 1] = merged
                    del aPoints[index + offset]
                    shock.append(merged)
                    continue
            second = aPoints[index]
            # A line that starts on the center line needs the singular treatment for its first
            # step, because the first-family source term is dr / r with r zero at the parent.
            if first.r <= 1e-12:
                point = plumeNearAxisPoint(flow, first, second)
            else:
                point = plumeInteriorPoint(flow, first, second)
            if point is None or outsideBoundary(point):
                break
            interiors.append(point)
            line.append(point)
            index += 1

        if not interiors:
            stop = 'lineCollapsed'
            break

        edge = plumeFreeBoundaryPoint(flow, interiors[-1], anchor, boundaryMach)
        if edge is None or edge.x < anchor.x - 1e-12:
            stop = 'boundaryPointFailed'
            break
        line.append(edge)
        boundary.append(edge)
        boundaryX.append(edge.x)
        boundaryR.append(edge.r)
        lines.append(line)
        # Sampled rather than measured on every line: the integral costs about as much as building
        # the line, and the drift is smooth enough that a few dozen samples describe it. Only lines
        # that start on the axis span the jet and are comparable with the exit plane.
        if line[0].r <= 1e-9 and len(lines) % max(1, maxLines // 40) == 0:
            fluxSamples.append((len(lines), plumeMassFlux(flow, line)))
        previous = _refinePlumeLine(flow, line, refineFraction, lineLimit)
        if len(previous) > lineLimit:
            previous = _resamplePlumeLine(flow, previous, lineLimit)

    # Mass drift is the solver's report on itself: worst and final departure from the flux
    # crossing the exit plane, in percent, carrying no reference outside the solution.
    # A short march may never hit a sampling interval, and a solve with no quality number is worse
    # than a slow one, so the last line that spans the jet is always measured.
    spanning = [one for one in lines if one and one[0].r <= 1e-9]
    if spanning and (not fluxSamples or fluxSamples[-1][0] != len(lines)):
        fluxSamples.append((len(lines), plumeMassFlux(flow, spanning[-1])))
    drifts = [100.0 * (flux - referenceFlux) / referenceFlux
              for _, flux in fluxSamples] if referenceFlux > 0.0 else []
    return {'lines': lines, 'boundary': boundary, 'fan': fan, 'shock': shock,
            'nodes': [point for ln in lines for point in ln],
            'boundaryMach': boundaryMach, 'stop': stop,
            'referenceFlux': referenceFlux, 'fluxSamples': fluxSamples,
            'massDriftWorst': max(drifts, key = abs) if drifts else float('nan'),
            'massDriftFinal': drifts[-1] if drifts else float('nan'),
            'lipShockDeflection': shockDeflection, 'lipStagnationRatio': stagnationRatio}

def advancePlumeFront(flow: PlumeFlow, front: list, boundaryMach: float) -> list:

    """

    Step a whole data line one increment downstream.

    The march computes one characteristic at a time, from a start point out to the boundary. That
    leaves the center line trailing far behind the boundary, because a line started on the axis
    reaches the boundary in one pass while the axis advances by a single step, and the solved
    region comes out as a wedge rather than a slab. It also needs a rule for where each new line
    starts, which is what the center-line restart and its sub-stepping in thirds exist to supply.

    Advancing the front removes both. Every point moves together:

        the axis point       from the second-family characteristic leaving front[1]
        interior points      from the first family at front[i] and the second at front[i + 1]
        the boundary point   from the first family at the outermost new point, against the
                             streamline leaving the old boundary point

    The pairs at either end are skipped because they are degenerate: the boundary point already
    sits on the first-family characteristic of its inner neighbor, so crossing the two again
    returns it unchanged. That costs the front one point per step, which the refinement puts back.

    `front` runs from the axis outward, index 0 on the center line and the last point on the free
    boundary. Returns the new front, or None when it cannot be completed.

    """
    if len(front) < 4:
        return None

    # Both end pairs are degenerate and are handled by their own processes instead. The boundary
    # point was computed as the intersection of the first-family characteristic from its inner
    # neighbor with the boundary streamline, so it already lies on that characteristic and
    # crossing the two again returns the same point. The axis point is the mirror of that.
    axis = plumeAxisPoint(flow, front[1])
    if axis is None:
        return None
    advanced = [axis]

    for index in range(1, len(front) - 2):
        inner, outer = front[index], front[index + 1]
        if inner.r <= 1e-12:
            point = plumeNearAxisPoint(flow, inner, outer)
        else:
            point = plumeInteriorPoint(flow, inner, outer)
        if point is None:
            return None
        advanced.append(point)

    if len(advanced) < 3:
        return None
    # Both parents come from the old line. Crossing a characteristic leaving a point on the new
    # line against a streamline leaving the old boundary mixes the two, and the intersection walks
    # upstream as the outer region loses a point a step: the advance then stalls at eleven steps
    # having carried the boundary half a lip radius. From the old line it reaches fifty four.
    edge = plumeFreeBoundaryPoint(flow, front[-2], front[-1], boundaryMach)
    if edge is None or edge.x < front[-1].x - 1e-12:
        return None
    advanced.append(edge)
    return advanced

def solvePlumeFront(flow: PlumeFlow, initialLine: list, ambientPressure: float,
                    maxSteps: int = 4000, refineFraction: float = 0.10,
                    lineLimit: int = 250) -> dict:

    """

    Solve the plume by advancing the exit plane downstream as a front.

    The front has to be a line that is not itself a characteristic. That rules out seeding it from
    the march, whose lines are first-family characteristics: neighboring points on one are joined
    by the very characteristic the advance would cross against its neighbor's, and the
    intersection returns a point already there. The exit plane is the natural choice, being a
    station rather than a wave.

    The lip corner is the price. A centered fan turns the flow through a finite angle at a single
    point, which a front cannot hold, so the turning is instead spread over the first few steps as
    the free boundary condition rotates the outermost point. That smears the expansion near the
    lip and washes out downstream.

    NOT YET USABLE, and superseded by `experimental/stationMarch.py`, which prescribes the data
    line instead of letting the characteristics choose it. This one stalls because the line it
    advances rotates into the first-family characteristic direction: measured at the stall, the
    front lies within 0.00 degrees of it over part of its length, the spacing along it spans 114
    to 1, and the boundary has run to two lip radii while the center line has reached a tenth of
    one. A data line lying on a characteristic carries no information across itself.

    The march remains the package's solver. This is kept because the reason the obvious approach
    fails is worth keeping: any working front has to start from a station, and it has to be held
    away from the characteristic directions as it turns downstream, which is what a prescribed
    station does by construction.

    """
    if not initialLine or len(initialLine) < 6:
        return {'lines': [], 'boundary': [], 'nodes': [], 'shock': [], 'stop': 'noInitialLine',
                'boundaryMach': 0.0, 'referenceFlux': 0.0, 'fluxSamples': [], 'steps': 0,
                'massDriftWorst': float('nan'), 'massDriftFinal': float('nan')}

    boundaryMach = flow.machFromStaticPressure(ambientPressure)
    # The march works from the lip inward; the front indexes from the center line outward.
    front = list(reversed(initialLine)) if initialLine[0].r > initialLine[-1].r \
            else list(initialLine)
    if boundaryMach <= front[-1].mach:
        return {'lines': [], 'boundary': [], 'nodes': [], 'shock': [],
                'stop': 'notUnderexpanded', 'boundaryMach': boundaryMach, 'referenceFlux': 0.0,
                'fluxSamples': [], 'steps': 0, 'massDriftWorst': float('nan'),
                'massDriftFinal': float('nan')}

    referenceFlux = plumeMassFlux(flow, front)
    lines, boundary, fluxSamples = [], [front[-1]], []
    stop = 'maxSteps'
    steps = 0

    while steps < maxSteps:
        advanced = advancePlumeFront(flow, front, boundaryMach)
        if advanced is None:
            stop = 'frontStalled'
            break
        steps += 1
        lines.append(advanced)
        boundary.append(advanced[-1])
        if steps % max(1, maxSteps // 40) == 0:
            fluxSamples.append((steps, plumeMassFlux(flow, advanced)))
        refined = _refinePlumeLine(flow, advanced, refineFraction, lineLimit)
        if len(refined) > lineLimit:
            refined = _resamplePlumeLine(flow, refined, lineLimit)
        front = refined

    drifts = [100.0 * (flux - referenceFlux) / referenceFlux
              for _, flux in fluxSamples] if referenceFlux > 0.0 else []
    return {'lines': lines, 'boundary': boundary, 'fan': [], 'shock': [],
            'nodes': [point for ln in lines for point in ln],
            'boundaryMach': boundaryMach, 'stop': stop, 'steps': steps,
            'referenceFlux': referenceFlux, 'fluxSamples': fluxSamples,
            'massDriftWorst': max(drifts, key = abs) if drifts else float('nan'),
            'massDriftFinal': drifts[-1] if drifts else float('nan')}

def _resamplePlumeLine(flow: PlumeFlow, line: list, count: int) -> list:

    """

    Hold a data line to a fixed number of points.

    Each line carries one more point than the one before it, because it places an interior point
    against every entry of its parent and then adds its own boundary point. Left alone that grows
    without bound: the lines reach thousands of points, every one is walked against its parent,
    and the march slows until the center line advances by a ten-thousandth of a jet radius per
    line and stops. The report avoids this by counting the line length down rather than up,
    statements 302 and 404, so its net coarsens as it marches.

    Coarsening is not wanted here, since resolution is what the refinement exists to protect. The
    line is redistributed evenly along its own arc length instead, which caps the count, holds the
    resolution fixed and makes the cost per line constant. Both ends are kept exactly because they
    carry the axis and the boundary.

    Redistribution also fixes the spacing near the axis, where the march otherwise leaves its
    first point a rounding distance out and the next center-line point then advances by about that
    much. The count is never raised: interpolated points satisfy no characteristic relation, and
    padding a short line with them destabilises the march that reads it.

    """
    if len(line) < 3 or count < 3:
        return line

    xs = np.array([point.x for point in line])
    rs = np.array([point.r for point in line])
    distance = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(xs), np.diff(rs)))])
    if distance[-1] <= 0.0:
        return line
    machs = np.array([point.mach for point in line])
    angles = np.array([point.flowAngle for point in line])

    sampled = np.linspace(0.0, distance[-1], count)
    resampled = []
    for target in sampled:
        mach = float(np.interp(target, distance, machs))
        if mach <= 1.0:
            continue
        resampled.append(PlumePoint(float(np.interp(target, distance, xs)),
                                    float(np.interp(target, distance, rs)),
                                    mach,
                                    float(np.interp(target, distance, angles)),
                                    flow, 'resampled'))
    if len(resampled) < 3:
        return line
    resampled[0], resampled[-1] = line[0], line[-1]
    return resampled

def _refinePlumeLine(flow: PlumeFlow, line: list, fraction: float, limit: int) -> list:

    '''

    Put back the resolution a line loses as characteristics are absorbed at the boundary.

    A segment is split when it spans more than `fraction` of the local radius, with the radius
    floored at a small part of the line's own extent so the criterion does not collapse on the
    axis. Refinement stops at `limit` rather than thinning the line, because dropping points
    breaks the point-to-point correspondence the scheme rests on.

    '''
    if len(line) < 2:
        return line
    floor = 0.02 * max(point.r for point in line)
    refined = [line[0]]
    for left, right in zip(line[:-1], line[1:]):
        span = math.hypot(right.x - left.x, right.r - left.r)
        scale = max(left.r, right.r, floor, 1e-12)
        splits = int(span / (fraction * scale))
        if splits > 0 and len(refined) + splits < limit:
            for index in range(1, splits + 1):
                weight = index / (splits + 1.0)
                mach = left.mach + (right.mach - left.mach) * weight
                if mach <= 1.0:
                    continue
                refined.append(PlumePoint(
                    left.x + (right.x - left.x) * weight,
                    left.r + (right.r - left.r) * weight,
                    mach,
                    left.flowAngle + (right.flowAngle - left.flowAngle) * weight,
                    flow, 'inserted'))
        refined.append(right)
    return refined

@dataclass
class PlumeContour:

    '''

    The nozzle a plume is seeded from.

    The march past the lip continues the characteristics net the nozzle solve produced, so it
    needs that net, the wall it was solved against, and the gas it was solved in. Nothing else
    about the nozzle is relevant, which is why this is nineteen fields rather than a Nozzle.

    Two of them are not inputs in the ordinary sense. `nozzlePlumeStructure` carries a structure
    already solved for this contour, which the field solve reuses when the ambient matches, and
    `ceaOutput` is the thermochemistry the exit state is read back from.

    Every field starts empty. A solve reports what it could not do rather than assuming a value.

    '''

    allFlowAngles:                   Any = None
    allMachNumbers:                  Any = None
    allRPoints:                      Any = None
    allXPoints:                      Any = None
    ceaOutput:                       Any = None
    chamberGamma:                    Any = None
    chamberPressure:                 Any = None
    chamberRGasConstant:             Any = None
    chamberStagnationTemperature:    Any = None
    exitMachNumber:                  Any = None
    limitingCharacteristicR:         Any = None
    limitingCharacteristicX:         Any = None
    nozzleNearWallMachNumber:        Any = None
    nozzleNearWallPressure:          Any = None
    nozzlePlumeStructure:            Any = None
    nozzleScalingFactor:             Any = None
    rNozzleWall:                     Any = None
    targetExitPressure:              Any = None
    xNozzleWall:                     Any = None

def solvePlumeStructure(contour, ambientPressure: float, plumeLength: float = None,
                   numBoundaryPoints: int = 400):

    '''

    Correlation-based structure of the exhaust plume at a given ambient pressure.

    Places the jet boundary, the shock cell spacing and the Mach disk from published
    correlations, each traceable to docs/references_plumeStructure_2026-09-04.md. The
    interior of the plume is deliberately not solved: no correlation in the literature
    yields an interior flowfield, and closed-form expressions that appear to are drawing a
    picture rather than solving a flow.

    Extending the method of characteristics past the exit plane is what would give a real
    interior, and everything that solve needs is already on this object; see
    plumeCharacteristicSeed() for the handover.

    Parameters:
    -----------
    ambientPressure : float
        Ambient static pressure [Pa]
    plumeLength : float, optional
        Axial extent to model [m]. Defaults to the larger of ten fully expanded jet
        diameters and two Mach disk distances.
    numBoundaryPoints : int, optional
        Resolution of the boundary curve

    Returns:
    --------
    plume.PlumeStructure : correlated structure, or None when the contour is unavailable.
        Read `.notes` before using the numbers: it carries the separation and Mach-disk
        onset caveats, and the spread between the Prandtl and Pack cell coefficients.

    Examples:
    ---------
    >>> nozzle.generateNozzle(configPath = 'case.json')
    >>> structure = nozzle.plumeStructure(ambientPressure = 101325.0)
    >>> structure.jetType
    'overexpanded'

    '''

    x = np.asarray(getattr(contour, 'xNozzleWall', []), dtype = float)
    r = np.asarray(getattr(contour, 'rNozzleWall', []), dtype = float)
    if x.size == 0 or r.size != x.size or ambientPressure <= 0.0:
        return None

    structure = PlumeStructure()
    structure.ambientPressure = float(ambientPressure)
    structure.notes = []

    # -- Gas properties -- #
    gamma = float(getattr(contour, 'chamberGamma', 0.0) or 0.0)
    ceaOutput = getattr(contour, 'ceaOutput', None)
    if ceaOutput is not None:
        try:
            gamma = float(ceaOutput.ceaResults['exitGamma'])
        except Exception:                          # noqa: BLE001 -- chamber gamma is a fine fallback
            pass
    if not 1.01 < gamma < 1.99:
        return None
    structure.gamma = gamma

    # -- Lip state: local wall conditions at the last contour point -- #
    structure.lipX = float(x[-1])
    structure.lipRadius = float(r[-1])
    structure.lipWallAngle = _exitWallAngle(x, r)
    nearWallMach = np.asarray(getattr(contour, 'nozzleNearWallMachNumber', []), dtype = float)
    nearWallPressure = np.asarray(getattr(contour, 'nozzleNearWallPressure', []), dtype = float)
    structure.lipMach = float(nearWallMach[-1]) if nearWallMach.size else 0.0
    structure.lipPressure = float(nearWallPressure[-1]) if nearWallPressure.size else 0.0

    # -- Jet-scale state: one-dimensional exit and throat -- #
    throatIndex = int(np.argmin(r))
    structure.throatDiameter = float(2.0 * r[throatIndex])
    structure.exitDiameter = float(2.0 * r[-1])
    structure.exitMach = float(getattr(contour, 'exitMachNumber', 0.0) or structure.lipMach)
    structure.exitPressure = float(getattr(contour, 'targetExitPressure', 0.0) or structure.lipPressure)

    chamberPressure = float(getattr(contour, 'chamberPressure', 0.0) or 0.0)
    if chamberPressure <= 0.0 or structure.exitPressure <= 0.0:
        return None

    structure.nozzlePressureRatio = chamberPressure / ambientPressure
    structure.exitPressureRatio = structure.exitPressure / ambientPressure

    # -- Regime -- #
    if structure.exitPressureRatio > 1.05:
        structure.jetType = 'underexpanded'
    elif structure.exitPressureRatio < 0.95:
        structure.jetType = 'overexpanded'
    else:
        structure.jetType = 'ideallyExpanded'

    if structure.exitPressureRatio < separationPressureRatio:
        structure.notes.append(
            f'Exit-to-ambient pressure ratio {structure.exitPressureRatio:.2f} is below the '
            f'Summerfield separation criterion of {separationPressureRatio:.2f}: the jet is '
            f'very likely separated internally at this altitude. Every correlation here assumes '
            f'flow attached at the lip, so the structure below is not descriptive of the real jet.')

    # -- Fully expanded jet -- #
    structure.fullyExpandedMach = machFromPressureRatio(structure.nozzlePressureRatio, gamma)
    structure.fullyExpandedDiameter = fullyExpandedDiameter(
        structure.exitDiameter, structure.exitMach, structure.fullyExpandedMach, gamma)

    # -- Shock cell spacing -- #
    structure.shockCellLength = shockCellLength(
        structure.fullyExpandedDiameter, structure.fullyExpandedMach, prandtlCellCoefficient)
    structure.cellLengthPack = shockCellLength(
        structure.fullyExpandedDiameter, structure.fullyExpandedMach, packCellCoefficient)

    # -- Mach disk -- #
    # Ashkenas and Sherman, Crist and the onset surveys all measured jets exhausting into a
    # back pressure BELOW their exit pressure. The correlation is an underexpanded-jet result
    # and does not transfer to an overexpanded jet, whose near field is a lip shock train; a
    # Mach reflection can still occur there but not at a position this correlation predicts.
    structure.machDiskPresent = (structure.jetType == 'underexpanded'
                                 and structure.nozzlePressureRatio >= machDiskOnsetPressureRatio)
    if structure.jetType == 'overexpanded' and structure.nozzlePressureRatio >= machDiskOnsetPressureRatio:
        structure.notes.append(
            'The jet is overexpanded, so no Mach disk is reported: the Ashkenas and Sherman '
            'correlation is an underexpanded-jet result and does not apply here, even though the '
            'jet pressure ratio is above its onset threshold. A Mach reflection may still form '
            'in the lip shock train, but locating it needs a shock-capturing solution.')
    if structure.machDiskPresent:
        structure.machDiskX = structure.lipX + machDiskLocation(
            structure.throatDiameter, structure.nozzlePressureRatio)
        structure.machDiskDiameter = machDiskDiameter(
            structure.exitDiameter, structure.nozzlePressureRatio)
        structure.notes.append(
            f'Nozzle pressure ratio {structure.nozzlePressureRatio:.1f} is above the Mach disk '
            f'onset threshold of {machDiskOnsetPressureRatio:.1f}, so the first cell is bounded '
            f'by a Mach disk rather than a regular reflection. Published onset thresholds range '
            f'from about 3.1 to 3.9, so treat the switch as soft.')

    # -- Initial boundary turning at the lip -- #
    if structure.jetType == 'underexpanded':
        # The lip flow turns outward through a Prandtl-Meyer fan from the local wall Mach number
        # to the fully expanded Mach number, on top of the wall divergence already present.
        turning = (prandtlMeyerAngle(structure.fullyExpandedMach, gamma)
                   - prandtlMeyerAngle(structure.lipMach, gamma))
        structure.initialTurnAngle = structure.lipWallAngle + turning
    elif structure.jetType == 'overexpanded':
        # An oblique shock at the lip raises static pressure to ambient and turns the flow in.
        requiredRise = ambientPressure / structure.lipPressure if structure.lipPressure > 0 else 1.0
        deflection = obliqueShockDeflection(structure.lipMach, gamma, requiredRise)
        if deflection == 0.0 and requiredRise > 1.0:
            structure.notes.append(
                'The pressure rise needed at the lip exceeds what an attached oblique shock can '
                'deliver at this exit Mach number, so the lip shock is detached. The initial '
                'boundary angle below is the wall angle only.')
        structure.initialTurnAngle = structure.lipWallAngle - deflection
    else:
        structure.initialTurnAngle = structure.lipWallAngle

    # -- Axial extent -- #
    if plumeLength is None:
        plumeLength = max(10.0 * max(structure.fullyExpandedDiameter, structure.exitDiameter),
                          2.0 * (structure.machDiskX - structure.lipX))
    structure.plumeLength = float(plumeLength)

    # -- Boundary curve -- #
    # The two ends of each cell are set by correlation: the boundary leaves the lip at
    # `initialTurnAngle` and the pattern repeats every `shockCellLength`. The sinusoid between
    # them is a shape assumption, chosen so its initial slope matches the correlated turning
    # angle exactly. It is not a computed streamline; a real boundary is the pressure-matched
    # streamline from a method-of-characteristics solution.
    axial = np.linspace(0.0, structure.plumeLength, numBoundaryPoints)
    cellLength = structure.shockCellLength
    if cellLength > 0.0 and abs(structure.initialTurnAngle) > 1e-6:
        amplitude = cellLength * np.tan(structure.initialTurnAngle) / (2.0 * np.pi)

        # A strongly underexpanded jet correlates an amplitude larger than the lip radius,
        # which a sinusoid about that radius would carry through the axis and out the other
        # side. The cap holds the boundary positive everywhere. Where it binds, the swell is
        # understated and the correlated turning angle is no longer reproduced, which is what
        # `boundaryAmplitudeLimited` records; a real boundary needs the characteristics solve.
        amplitudeLimit = 0.95 * structure.lipRadius
        structure.boundaryAmplitudeLimited = bool(abs(amplitude) > amplitudeLimit)
        amplitude = float(np.clip(amplitude, -amplitudeLimit, amplitudeLimit))

        # Cells decay downstream through turbulent dissipation. The decay length is an
        # assumption, not a correlation; it is set to four cells so the pattern fades over the
        # distance shock-cell noise measurements typically still resolve it.
        decay = np.exp(-axial / (4.0 * cellLength))
        radius = structure.lipRadius + amplitude * np.sin(2.0 * np.pi * axial / cellLength) * decay
        structure.cellX = structure.lipX + np.arange(
            0.0, structure.plumeLength + cellLength, cellLength)
    else:
        radius = np.full(axial.shape, structure.lipRadius)
        structure.cellX = np.array([])

    structure.boundaryX = structure.lipX + axial
    structure.boundaryR = np.maximum(radius, 0.0)

    if structure.boundaryAmplitudeLimited:
        structure.notes.append(
            'Shock cell amplitude capped to keep the boundary off the axis. The correlated '
            'turning angle implies a swell wider than the lip radius, so the drawn boundary '
            'understates the plume; use it for cell spacing and scale, not for width.')

    structure.notes.append(
        'Boundary, cell spacing and Mach disk are correlations (Prandtl 1904 / Pack, Ashkenas '
        'and Sherman 1966, Tam and Tanna); the interior of the plume is not solved. Cell '
        f'spacing with Pack\'s coefficient would be {structure.cellLengthPack:.3f} m against '
        f'{structure.shockCellLength:.3f} m with Prandtl\'s, which is a fair measure of the '
        'uncertainty.')

    return structure

def _lastOrZero(values) -> float:

    '''Last element of an array, or zero when there is nothing there.'''

    if values is None or len(values) == 0:
        return 0.0

    return float(values[-1])

def plumeCharacteristicSeed(contour) -> dict:

    '''

    The exit-plane state a method-of-characteristics march into the plume would start from.

    This is the handover between the correlated plume structure above and a real interior
    solution. The contour solver already leaves everything needed on this object; this
    method gathers it so the extension does not have to rediscover which attribute holds
    what.

    What a plume march changes relative to the nozzle march:

      Boundary condition   Inside the nozzle the outer boundary is a wall, so the flow angle
                           is prescribed by the contour. In the plume it is a free
                           constant-pressure boundary: static pressure equals ambient and
                           the boundary streamline angle falls out of the solution. The
                           initial turning at the lip is the Prandtl-Meyer expansion, or the
                           oblique shock when overexpanded, that plumeStructure() already
                           reports as `initialTurnAngle`.

      Shocks               The nozzle interior is shock free by construction, so the solver
                           can stay isentropic. A plume is not: compression characteristics
                           coalesce into the intercepting barrel shock, and above the onset
                           pressure ratio into a Mach disk. A characteristics march alone
                           runs until characteristics cross; what happens after needs shock
                           fitting or a shock-capturing scheme.

      Termination          `plumeStructure().machDiskX` and `.shockCellLength` give a
                           physically motivated place to stop, and a sanity check on where
                           a march should first see characteristics cross.

    Returns:
    --------
    dict with keys:
        'xLimiting', 'rLimiting'     limiting characteristic, the last data line the nozzle
                                     march produced [m]
        'xMesh', 'rMesh'             full characteristic mesh, three blocks [m]
        'machMesh', 'flowAngleMesh'  Mach number [-] and flow angle [rad] on that mesh
        'scalingFactor'              multiplier taking the non-dimensional mesh to meters
        'gamma', 'gasConstant'       chamber ratio of specific heats [-] and R [J/kg-K]
        'stagnationPressure'         chamber stagnation pressure [Pa]
        'stagnationTemperature'      chamber stagnation temperature [K]
        'exitRadius', 'exitX'        nozzle lip position [m]

    Returns None when no characteristic mesh exists, which is the case for a conical
    diverging section.

    '''

    if getattr(contour, 'allXPoints', None) is None:
        return None

    return {
        'xLimiting':             getattr(contour, 'limitingCharacteristicX', None),
        'rLimiting':             getattr(contour, 'limitingCharacteristicR', None),
        'xMesh':                 contour.allXPoints,
        'rMesh':                 contour.allRPoints,
        'machMesh':              getattr(contour, 'allMachNumbers', None),
        'flowAngleMesh':         getattr(contour, 'allFlowAngles', None),
        'scalingFactor':         contour.nozzleScalingFactor,
        'gamma':                 contour.chamberGamma,
        'gasConstant':           contour.chamberRGasConstant,
        'stagnationPressure':    contour.chamberPressure,
        'stagnationTemperature': contour.chamberStagnationTemperature,
        # The lip, which is the last point of the wall. A contour that carries a mesh but no wall
        # reports zero rather than raising, and the march refuses on the seed it gets.
        'exitRadius':            _lastOrZero(getattr(contour, 'rNozzleWall', None)),
        'exitX':                 _lastOrZero(getattr(contour, 'xNozzleWall', None)),
    }

def solvePlumeField(contour, ambientPressure: float, numRays: int = 40, exitPoints: int = 140,
               maxLines: int = 2000, lineLimit: int = 250) -> 'PlumeField':

    '''

    Solve the plume interior by continuing the nozzle characteristics march past the lip.

    This is the crossing of the handover `plumeCharacteristicSeed` describes. Inside the nozzle
    the outer boundary is a wall and the contour prescribes the flow angle; past the lip it is
    a free streamline at ambient pressure and the angle falls out of the solution. Nothing else
    changes, so the two halves are one solution rather than a solution and a picture. The
    interior point reproduces the contour solver's own relations exactly, which
    `tests/testPlumeMarch.py` holds it to.

    Where a result is refused and where it is merely poor are different things, and both are
    reported rather than confused. Operating points the formulation cannot represent at all are
    refused outright: a perfectly expanded jet has no wave structure, a strongly overexpanded
    one detaches its lip shock, and a conical contour leaves no mesh to continue. Everything
    else is solved and graded, because the march measures its own mass conservation and that
    says how far a given answer can be trusted without appealing to anything outside it.

    Parameters:
    -----------
    ambientPressure : float
        Back pressure the jet discharges into [Pa].
    numRays : int
        Rays in the centered fan at the lip. Raising it helps a uniform exit and hurts a
        contoured one, and why is not yet understood, so it is left where the real handover
        works.
    exitPoints : int
        Points sampled across the exit plane, which set how many lines the march can start.
    maxLines : int
        Ceiling on characteristic lines, so a slow case cannot run unbounded.
    lineLimit : int
        Points a line is held to. Finer conserves better and reaches less far.

    Returns:
    --------
    PlumeField
        Solved interior with its own quality report, or an unsolved one carrying the reason.

    '''

    result = PlumeField()

    # A structure already solved at this ambient is reused; anything else is solved fresh.
    structure = getattr(contour, 'nozzlePlumeStructure', None)
    if structure is None or structure.ambientPressure != ambientPressure:
        structure = solvePlumeStructure(contour, ambientPressure = ambientPressure)
    if structure is None:
        result.notes.append('No plume structure: the nozzle contour or the exit state is '
                            'missing, so there is nothing to march from.')
        return result

    result.exitMach = structure.exitMach
    result.exitPressureRatio = structure.exitPressureRatio
    result.lipX = structure.lipX
    result.lipRadius = structure.lipRadius

    if not (plumeFieldMinExitMach <= structure.exitMach <= plumeFieldMaxExitMach):
        result.notes.append(
            f'Exit Mach {structure.exitMach:.3f} is outside the {plumeFieldMinExitMach:.1f} '
            f'to {plumeFieldMaxExitMach:.1f} band the solver has been exercised over.')
        return result
    if structure.exitPressureRatio < separationPressureRatio:
        result.notes.append(
            f'Pe/Pa is {structure.exitPressureRatio:.3f}, below the Summerfield separation '
            f'criterion of {separationPressureRatio:.2f}. The nozzle separates internally, so '
            f'the flow is not attached at the lip and no attached plume model describes it.')
        return result
    if structure.exitPressureRatio > plumeFieldMaxPressureRatio:
        result.notes.append(
            f'Pe/Pa is {structure.exitPressureRatio:.3f}, above the {plumeFieldMaxPressureRatio} '
            f'this march is held to. Past that ratio the compressions reflected from the jet '
            f'boundary have coalesced, by Prandtl and by NASA TR R-6 independently, and an '
            f'isentropic net carries no shock. `plumeStructure` correlates this jet instead.')
        return result
    if abs(structure.lipWallAngle) > plumeFieldMaxWallAngle:
        result.notes.append(
            f'The exit diverges at {np.degrees(abs(structure.lipWallAngle)):.2f} degrees, past '
            f'the {np.degrees(plumeFieldMaxWallAngle):.2f} this march is held to. On a divergent '
            f'exit it solves a wedge near the boundary and never reaches the center line, so no '
            f'line spans the jet and the solution cannot be checked against anything. '
            f'`plumeStructure` correlates this jet instead.')
        return result

    # The characteristic mesh is what makes this an extension of the nozzle solution rather
    # than a standalone jet. A conical contour has no mesh and returns None here.
    seed = plumeCharacteristicSeed(contour)
    required = ('gasConstant', 'stagnationTemperature', 'stagnationPressure', 'scalingFactor',
                'exitX', 'exitRadius', 'xMesh', 'rMesh', 'flowAngleMesh', 'machMesh')
    if seed is None or any(seed.get(key) is None for key in required):
        result.notes.append('No characteristic mesh on this contour, so the plume march has '
                            'no nozzle solution to continue. Conical nozzles take the '
                            'correlated plume structure instead.')
        return result

    # The gamma has to be the one the mesh was solved with, not the one the correlations
    # prefer. `plumeStructure` reports CEA's exit gamma because that is the better number for
    # a correlation evaluated at the exit; the characteristic mesh was built on the chamber
    # gamma, and reading its Mach numbers under a different ratio of specific heats makes the
    # state discontinuous at the very plane the march starts from.
    flow = PlumeFlow(seed['gamma'], seed['gasConstant'], seed['stagnationTemperature'],
                     seed['stagnationPressure'])
    exitLine = plumeExitLine(flow, seed, numPoints = exitPoints)
    if exitLine is None:
        result.notes.append('The exit plane could not be read from the characteristic mesh.')
        return result
    result.seededFromMesh = True

    net = solvePlumeMarch(flow, exitLine, ambientPressure, numRays = numRays,
                          maxLines = maxLines, lineLimit = lineLimit)
    nodes = net['nodes']
    if len(nodes) < 10:
        result.notes.append(f'The march did not build a usable net here; it stopped with '
                            f'"{net["stop"]}".')
        return result

    machNodes = np.array([point.mach for point in nodes])
    result.nodeX = np.array([point.x for point in nodes])
    result.nodeR = np.array([point.r for point in nodes])
    result.nodeMach = machNodes
    result.nodeFlowAngle = np.array([point.flowAngle for point in nodes])
    result.nodePressure = np.array([flow.staticPressure(mach) for mach in machNodes])

    result.boundaryX = np.array([point.x for point in net['boundary']])
    result.boundaryR = np.array([point.r for point in net['boundary']])
    result.boundaryMach = net['boundaryMach']
    result.lipTurnAngle = net['boundaryMach'] and (net['boundary'][-1].flowAngle
                                                   if len(net['boundary']) > 1 else 0.0)
    result.solvedTo = float(result.nodeX.max())
    result.stop = net['stop']
    result.massDriftWorst = net['massDriftWorst']

    # Mass conservation is the only check this field carries, and it needs a line that spans the
    # jet from the axis to the boundary. A march that never reaches the center line produces none,
    # so the flux has nothing to compare against and comes back as nan. A field with no quality
    # statement at all is not a solved field, whatever it drew, and a caller reading `solved` has
    # to see that without parsing the notes.
    if not np.isfinite(result.massDriftWorst):
        result.notes.append(
            'No line of this march spans the jet, so its mass flow cannot be compared with the '
            'exit plane and the field carries no quality statement. Reported as unsolved for '
            'that reason rather than for anything wrong with the nodes it did place.')
        return result

    result.solved = True

    disk = plumeMachDisk(flow, net)
    result.machDiskPresent = bool(disk['present'])
    if disk['present']:
        result.machDiskX = disk['x']
        result.machDiskDiameter = disk['diameter']

    # Shock cell length from the boundary itself, as the axial period between crests. Twice
    # the distance from the lip to the first crest is a different and larger quantity, because
    # the lip fan throws the boundary wide before the pattern settles.
    radii = result.boundaryR
    if radii.size > 40:
        window = max(5, radii.size // 200)
        smoothed = np.convolve(radii, np.ones(window) / window, mode = 'same')
        crests = []
        for index in range(window, smoothed.size - window - 1):
            if smoothed[index] >= smoothed[index - window:index].max() \
                    and smoothed[index] > smoothed[index + 1:index + 1 + window].max():
                if not crests or result.boundaryX[index] - result.boundaryX[crests[-1]] \
                        > 0.4 * max(structure.shockCellLength, 1e-9):
                    crests.append(index)
        result.cellsResolved = max(0, len(crests) - 1)
        if len(crests) >= 2:
            result.shockCellLength = float(np.diff(result.boundaryX[crests]).mean())

    result.notes.append(
        'Solved by continuing the nozzle characteristics march past the lip, isentropic and '
        'with no shock model. The interior point reproduces the contour solver exactly, and '
        'the march starts from the exit plane of that solve rather than from an assumed '
        'profile.')
    drift = abs(result.massDriftWorst)
    result.notes.append(
        f'Mass conservation: the flux through the last line differs from the exit plane by '
        f'{result.massDriftWorst:+.3f} percent. Every line spans the jet, so they must all '
        f'carry the same flow; this needs no reference outside the solution and is the measure '
        f'of how far the answer can be trusted.')
    # Grading rather than refusing. The bands come from what has been measured: a parallel exit
    # near design holds a few hundredths of a percent, and anything past a few percent has
    # lost the flow it started with.
    if not np.isfinite(drift):
        result.trustworthy = False
        result.notes.append('DO NOT TRUST: the march was too short to measure its own '
                            'conservation, so this field carries no quality statement at all.')
    elif drift > 5.0:
        result.trustworthy = False
        result.notes.append(
            f'DO NOT TRUST: losing {drift:.1f} percent of the mass flow means this field is '
            f'not a solution of the flow it started from. It is drawn only to show what the '
            f'march currently produces here.')
    elif drift > 1.0:
        result.trustworthy = False
        result.notes.append(
            f'Marginal: {drift:.1f} percent of the mass flow is unaccounted for. Treat the '
            f'field as indicative and not as a result.')
    else:
        result.trustworthy = True
    if abs(np.degrees(structure.lipWallAngle)) > 1.0:
        result.notes.append(
            f'The exit diverges at {np.degrees(structure.lipWallAngle):.1f} degrees. The march '
            f'stops after roughly one shock cell on a divergent exit, and its conservation '
            f'degrades with the angle, so the field here is near-lip only. It reached '
            f'{result.cellsResolved} full cells.')
    if structure.exitPressureRatio < 1.0 and net.get('lipStagnationRatio', 1.0) < 1.0:
        result.notes.append(
            f'Overexpanded: the lip turns inward through what is really an oblique shock, '
            f'taken here as an isentropic compression. The shock would cost '
            f'{100.0 * (1.0 - net["lipStagnationRatio"]):.2f} percent of stagnation pressure, '
            f'which is the size of the approximation.')

    return result
