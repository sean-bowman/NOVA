'''
Axisymmetric free-jet MOC on an explicit characteristic net.

Redesign notes, and why the earlier line-march failed:

  Sign-agnostic intersections.  Characteristic directions are carried as unit vectors and the
  intersection is solved parametrically, requiring positive arc length along BOTH parents. A
  slope-based test cannot do this: a slope loses direction, so it cannot tell a valid downstream
  intersection from one that lies behind a parent. Behind a strong lip shock theta = -30 deg with
  mu = 22.6 deg puts both families on negative slopes, and that is exactly where the slope test
  gave wrong answers.

  Explicit connectivity.  Every node records which C+ and C- family index it belongs to and which
  nodes it came from, so the net can be walked, plotted and debugged rather than inferred from
  list positions.

  First-class boundary streamline.  The free boundary is its own polyline, started at the lip at
  the FULLY EXPANDED state. A centerd corner expansion turns the boundary streamline through the
  whole fan at the corner itself; only the fan characteristics are spread downstream. Pinning the
  boundary to the lip for the duration of the fan, as the line-march did, strands it.

Compatibility relations are the velocity form used by Nozzle.axisymmetricMethodOfCharacteristics:

    lambda = cot(mu) / V
    C+ :  theta_i = theta1 + lambda1 (V_i - V1) - (S+/r)(r_i - r1)
    C- :  theta_i = theta2 - lambda2 (V_i - V2) + (S-/r)(r_i - r2)
    S+ = sin(theta) sin(mu) / sin(theta + mu),   S- = sin(theta) sin(mu) / sin(theta - mu)
'''

from dataclasses import dataclass, field

import numpy as np

# ------------------------------------------------------------------ gas ---

class Gas:
    '''Calorically perfect gas at a fixed stagnation state.'''

    def __init__(self, gamma, gasConstant, stagnationTemperature, stagnationPressure):
        self.gamma, self.gasConstant = gamma, gasConstant
        self.T0, self.P0 = stagnationTemperature, stagnationPressure
        self.vMax = np.sqrt(2.0 * gamma * gasConstant * stagnationTemperature / (gamma - 1.0))

    def velocity(self, mach):
        return mach * np.sqrt(self.gamma * self.gasConstant * self.T0
                              / (1.0 + 0.5 * (self.gamma - 1.0) * mach**2))

    def mach(self, velocity):
        ratio = min(velocity / self.vMax, 1.0 - 1e-14)
        return np.sqrt((2.0 / (self.gamma - 1.0)) * ratio**2 / (1.0 - ratio**2))

    def pressure(self, mach):
        return self.P0 * (1.0 + 0.5 * (self.gamma - 1.0) * mach**2)**(-self.gamma / (self.gamma - 1.0))

    def machFromPressure(self, pressure):
        return np.sqrt(2.0 / (self.gamma - 1.0)
                       * ((self.P0 / pressure)**((self.gamma - 1.0) / self.gamma) - 1.0))

def prandtlMeyer(mach, gamma):
    if mach <= 1.0:
        return 0.0
    k = (gamma + 1.0) / (gamma - 1.0)
    return np.sqrt(k) * np.arctan(np.sqrt((mach**2 - 1.0) / k)) - np.arctan(np.sqrt(mach**2 - 1.0))

# ----------------------------------------------------------------- node ---

@dataclass
class Node:
    x: float
    r: float
    theta: float
    mach: float
    kind: str = 'interior'          # 'lip' | 'interior' | 'axis' | 'boundary'
    plusFamily: int = -1            # index of the C+ characteristic through this node
    minusFamily: int = -1           # index of the C- characteristic through this node
    parents: tuple = ()

    def state(self):
        return self.x, self.r, self.theta, self.mach

def _machAngle(mach):
    return np.arcsin(1.0 / max(mach, 1.0 + 1e-12))

def _lam(mu, velocity):
    return (1.0 / np.tan(mu)) / velocity

def _sourcePlus(theta, mu):
    return np.sin(theta) * np.sin(mu) / np.sin(theta + mu)

def _sourceMinus(theta, mu):
    return np.sin(theta) * np.sin(mu) / np.sin(theta - mu)

def _intersect(originA, directionA, originB, directionB, tolerance=-1e-9):
    '''
    Parametric intersection of two rays. Returns (point, sA, sB) or None when the rays are
    parallel or the intersection lies behind either origin. Sign agnostic by construction.
    '''
    ax, ar = originA
    bx, br = originB
    dax, dar = directionA
    dbx, dbr = directionB
    determinant = dax * (-dbr) - (-dbx) * dar
    if abs(determinant) < 1e-14:
        return None
    rhsX, rhsR = bx - ax, br - ar
    sA = (rhsX * (-dbr) - (-dbx) * rhsR) / determinant
    sB = (dax * rhsR - dar * rhsX) / determinant
    if sA < tolerance or sB < tolerance:
        return None
    return (ax + sA * dax, ar + sA * dar), sA, sB

# --------------------------------------------------------- unit processes ---

def interiorNode(gas, plusParent, minusParent, iterations=20):
    '''C+ from plusParent crossed with C- from minusParent.'''
    x1, r1, th1, M1 = plusParent.state()
    x2, r2, th2, M2 = minusParent.state()
    mu1, mu2 = _machAngle(M1), _machAngle(M2)
    V1, V2 = gas.velocity(M1), gas.velocity(M2)
    xi, ri = 0.5 * (x1 + x2), 0.5 * (r1 + r2)
    thi, Mi = 0.5 * (th1 + th2), 0.5 * (M1 + M2)

    for _ in range(iterations):
        mui, Vi = _machAngle(Mi), gas.velocity(Mi)
        thA1, muA1 = 0.5 * (th1 + thi), 0.5 * (mu1 + mui)
        thA2, muA2 = 0.5 * (th2 + thi), 0.5 * (mu2 + mui)
        VA1, VA2 = 0.5 * (V1 + Vi), 0.5 * (V2 + Vi)
        rA1, rA2 = 0.5 * (r1 + ri), 0.5 * (r2 + ri)

        anglePlus, angleMinus = thA1 + muA1, thA2 - muA2
        hit = _intersect((x1, r1), (np.cos(anglePlus), np.sin(anglePlus)),
                         (x2, r2), (np.cos(angleMinus), np.sin(angleMinus)))
        if hit is None:
            return None, 'characteristicsCrossed'
        (xNew, rNew), _, _ = hit
        if rNew < -1e-10:
            return None, 'crossedAxis'

        lam1, lam2 = _lam(muA1, VA1), _lam(muA2, VA2)
        t1 = 0.0 if rA1 < 1e-10 else (_sourcePlus(thA1, muA1) / rA1) * (rNew - r1)
        t2 = 0.0 if rA2 < 1e-10 else (_sourceMinus(thA2, muA2) / rA2) * (rNew - r2)

        Vnew = (V1 * lam1 + V2 * lam2 + t1 + t2 + th2 - th1) / (lam1 + lam2)
        thNew = 0.5 * ((th1 + lam1 * (Vnew - V1) - t1) + (th2 - lam2 * (Vnew - V2) + t2))
        Mnew = gas.mach(Vnew)
        if not np.isfinite(Mnew) or Mnew <= 1.0:
            return None, 'wentSubsonic'

        done = abs(xNew - xi) < 1e-13 and abs(Mnew - Mi) < 1e-13
        xi, ri, thi, Mi = xNew, rNew, thNew, Mnew
        if done:
            break

    return Node(xi, ri, thi, Mi, 'interior', parents=(plusParent, minusParent)), None

def axisNode(gas, minusParent, iterations=20):
    '''C- from minusParent reaching r = 0, where theta = 0 by symmetry.'''
    x2, r2, th2, M2 = minusParent.state()
    mu2, V2 = _machAngle(M2), gas.velocity(M2)
    Mi, xi = M2, x2

    for _ in range(iterations):
        mui, Vi = _machAngle(Mi), gas.velocity(Mi)
        thA2, muA2 = 0.5 * th2, 0.5 * (mu2 + mui)
        VA2, rA2 = 0.5 * (V2 + Vi), 0.5 * r2
        angleMinus = thA2 - muA2
        direction = (np.cos(angleMinus), np.sin(angleMinus))
        if abs(direction[1]) < 1e-14:
            return None, 'characteristicParallelToAxis'
        arcLength = -r2 / direction[1]
        if arcLength < -1e-9:
            return None, 'characteristicsCrossed'
        xNew = x2 + arcLength * direction[0]

        lam2 = _lam(muA2, VA2)
        t2 = 0.0 if rA2 < 1e-10 else (_sourceMinus(thA2, muA2) / rA2) * (0.0 - r2)
        Vnew = V2 + (th2 + t2) / lam2
        Mnew = gas.mach(Vnew)
        if not np.isfinite(Mnew) or Mnew <= 1.0:
            return None, 'wentSubsonic'

        done = abs(xNew - xi) < 1e-13 and abs(Mnew - Mi) < 1e-13
        xi, Mi = xNew, Mnew
        if done:
            break

    return Node(xi, 0.0, 0.0, Mi, 'axis', parents=(minusParent,)), None

def boundaryNode(gas, plusParent, boundaryOrigin, boundaryMach, iterations=20):
    '''
    Free constant-pressure boundary. Pressure fixed at ambient fixes the Mach number, so the
    C+ compatibility relation returns the flow angle directly. The node sits where the C+ meets
    the boundary streamline leaving boundaryOrigin.
    '''
    x1, r1, th1, M1 = plusParent.state()
    xb, rb, thb, _ = boundaryOrigin.state()
    mu1, V1 = _machAngle(M1), gas.velocity(M1)
    Vi, mui = gas.velocity(boundaryMach), _machAngle(boundaryMach)
    thi, xi, ri = thb, xb, rb

    for _ in range(iterations):
        thA1, muA1 = 0.5 * (th1 + thi), 0.5 * (mu1 + mui)
        VA1, rA1 = 0.5 * (V1 + Vi), 0.5 * (r1 + ri)
        anglePlus = thA1 + muA1
        streamAngle = 0.5 * (thb + thi)
        hit = _intersect((x1, r1), (np.cos(anglePlus), np.sin(anglePlus)),
                         (xb, rb), (np.cos(streamAngle), np.sin(streamAngle)))
        if hit is None:
            return None, 'characteristicsCrossed'
        (xNew, rNew), _, _ = hit
        if rNew < 0.0:
            return None, 'boundaryCollapsed'

        lam1 = _lam(muA1, VA1)
        t1 = 0.0 if rA1 < 1e-10 else (_sourcePlus(thA1, muA1) / rA1) * (rNew - r1)
        thNew = th1 + lam1 * (Vi - V1) - t1

        done = abs(xNew - xi) < 1e-13 and abs(thNew - thi) < 1e-13
        xi, ri, thi = xNew, rNew, thNew
        if done:
            break

    return Node(xi, ri, thi, boundaryMach, 'boundary', parents=(plusParent, boundaryOrigin)), None

def obliqueShock(mach, gamma, pressureRatio):
    '''Deflection, wave angle and post-shock Mach for a prescribed static pressure rise.'''
    if mach <= 1.0 or pressureRatio <= 1.0:
        return None
    normalSquared = 1.0 + (pressureRatio - 1.0) * (gamma + 1.0) / (2.0 * gamma)
    if normalSquared > mach**2:
        return None
    beta = np.arcsin(np.sqrt(normalSquared) / mach)
    numerator = 2.0 / np.tan(beta) * (mach**2 * np.sin(beta)**2 - 1.0)
    denominator = mach**2 * (gamma + np.cos(2.0 * beta)) + 2.0
    deflection = np.arctan(numerator / denominator)
    normalUpstream = mach * np.sin(beta)
    normalDownstream = np.sqrt((1.0 + 0.5 * (gamma - 1.0) * normalUpstream**2)
                               / (gamma * normalUpstream**2 - 0.5 * (gamma - 1.0)))
    return deflection, beta, normalDownstream / np.sin(beta - deflection)

# -------------------------------------------------------------- the net ---

@dataclass
class JetNet:
    regime: str = ''
    exitMach: float = 0.0
    exitPressure: float = 0.0
    ambientPressure: float = 0.0
    jetMach: float = 0.0
    lipTurn: float = 0.0
    shock: tuple = None
    characteristics: list = field(default_factory = list)   # list of C- node lists
    boundary: list = field(default_factory = list)          # boundary polyline nodes
    axis: list = field(default_factory = list)
    stop: str = ''
    stopNode: Node = None
    notes: list = field(default_factory = list)

    @property
    def nodes(self):
        return [n for line in self.characteristics for n in line]

def solveJet(gas, exitMach, exitRadius, exitX, ambientPressure,
             numFan=20, numRadial=32, maxCharacteristics=600, maxLength=None,
             maxNodesPerLine=200):
    '''
    Build the characteristic net for a free jet leaving a nozzle lip.

    The march is a sequence of C- characteristics from the free boundary down to the axis.
    Reflection off the axis and off the free boundary is implicit: the C+ leaving one
    characteristic's node is consumed by the next characteristic's node at the same index.
    '''
    exitPressure = gas.pressure(exitMach)
    ratio = exitPressure / ambientPressure
    regime = 'underexpanded' if ratio > 1.02 else ('overexpanded' if ratio < 0.98 else 'ideal')
    net = JetNet(regime=regime, exitMach=exitMach, exitPressure=exitPressure,
                 ambientPressure=ambientPressure)
    if maxLength is None:
        maxLength = 16.0 * exitRadius

    jetMach = gas.machFromPressure(ambientPressure)
    fan = []
    initialLine = None

    if regime == 'underexpanded':
        net.lipTurn = prandtlMeyer(jetMach, gas.gamma) - prandtlMeyer(exitMach, gas.gamma)
        machSteps = np.linspace(exitMach, jetMach, numFan + 1)[1:]
        fan = [(prandtlMeyer(m, gas.gamma) - prandtlMeyer(exitMach, gas.gamma), m) for m in machSteps]
    elif regime == 'overexpanded':
        result = obliqueShock(exitMach, gas.gamma, ambientPressure / exitPressure)
        if result is None:
            net.stop = 'lipShockDetached'
            net.notes.append('The pressure rise the lip needs exceeds what an attached oblique '
                             'shock can deliver at this exit Mach number. The shock is detached '
                             'and MOC cannot be started from it.')
            return net
        deflection, beta, postMach = result
        net.shock = result
        net.lipTurn = -deflection
        jetMach = postMach
        reach = exitRadius / np.tan(beta)
        initialLine = [Node(exitX + reach * (i / (numRadial - 1)),
                            exitRadius * (1.0 - i / (numRadial - 1)),
                            -deflection, postMach,
                            'boundary' if i == 0 else ('axis' if i == numRadial - 1 else 'interior'))
                       for i in range(numRadial)]
        net.notes.append(f'Lip shock fitted: {np.degrees(deflection):.2f} deg deflection at a '
                         f'{np.degrees(beta):.2f} deg wave angle, exit M {exitMach:.2f} -> '
                         f'{postMach:.2f}. The march starts from the uniform post-shock state on '
                         f'the downstream face of that shock.')

    net.jetMach = jetMach

    if initialLine is None:
        initialLine = [Node(exitX, exitRadius * (1.0 - i / (numRadial - 1)), 0.0, exitMach,
                            'boundary' if i == 0 else ('axis' if i == numRadial - 1 else 'interior'))
                       for i in range(numRadial)]

    net.characteristics.append(initialLine)
    line = initialLine

    # The boundary streamline leaves the lip at the FULL turning angle: a centerd corner
    # expansion turns the streamline through the whole fan at the corner itself.
    boundaryOrigin = Node(exitX, exitRadius, net.lipTurn, jetMach, 'boundary')
    net.boundary.append(boundaryOrigin)

    fanIndex = 0
    for step in range(maxCharacteristics):
        newLine, failure = [], None

        if fanIndex < len(fan):
            theta, mach = fan[fanIndex]
            newLine.append(Node(exitX, exitRadius, theta, mach, 'lip', minusFamily=step))
            fanIndex += 1
            offset = 0
        else:
            node, why = boundaryNode(gas, line[1], boundaryOrigin, jetMach)
            if node is None:
                failure = (why, line[0])
            else:
                node.minusFamily = step
                newLine.append(node)
                boundaryOrigin = node
                net.boundary.append(node)
            offset = 1

        if failure is None:
            for k in range(1, len(line) - offset):
                node, why = interiorNode(gas, line[k + offset], newLine[k - 1])
                if node is None:
                    failure = (why, newLine[k - 1])
                    break
                node.minusFamily = step
                node.plusFamily = k
                newLine.append(node)

        if failure is None:
            node, why = axisNode(gas, newLine[-1])
            if node is None:
                failure = (why, newLine[-1])
            else:
                node.minusFamily = step
                newLine.append(node)
                net.axis.append(node)

        if failure is not None:
            net.stop, net.stopNode = failure
            break

        if len(newLine) > maxNodesPerLine:
            keep = sorted(set(np.linspace(1, len(newLine) - 2, maxNodesPerLine - 2).round().astype(int)))
            newLine = [newLine[0]] + [newLine[i] for i in keep] + [newLine[-1]]

        net.characteristics.append(newLine)
        line = newLine

        if newLine[0].x - exitX > maxLength:
            net.stop = 'maxLength'
            break
        if len(line) < 4:
            net.stop = 'lineCollapsed'
            break
    else:
        net.stop = 'maxCharacteristics'

    return net
