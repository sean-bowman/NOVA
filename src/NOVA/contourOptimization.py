
# -- Thrust-Optimized Contour by Direct Search -- #

'''

Finding the bell wall that gives the most thrust for a given length and area ratio.

Rao's 1958 result is a variational one: he wrote the thrust as an integral over a control surface,
applied the calculus of variations, and derived conditions the optimum wall satisfies. That is the
canonical method and it is not what this does. This is Allman and Hoffman's 1981 alternative,
which fixes the initial expansion, gives the rest of the wall a small number of coefficients, and
varies them directly against the thrust the flow solver returns. The two were shown to agree, and
the direct route has a property the variational one does not: nothing in it has to be transcribed
from equations that cannot be checked against anything.

Why the answer means something
------------------------------

An optimizer that returns a number is not evidence of an optimum. Three things here are what make
the result readable.

**The search space contains the incumbent.** A quadratic Bezier is exactly a cubic with its
interior control points placed two thirds of the way along the same tangents, so every Rao
parabola is a member of the cubic family searched here. The optimizer starts at the parabola the
chart gives, which means it can only improve on it, and "does the optimum beat the parabola" stops
being a race between two search procedures and becomes a question about the two families.

**The design constraints are absorbed rather than imposed.** The exit point is fixed by the area
ratio and the length, so every candidate delivers the requested design point exactly, whatever its
interior control points do. The optimizer never sees a constraint and never has to trade
feasibility against objective.

**The noise floor is measured before the margin is claimed.** A thrust coefficient read off a
discrete mesh is only piecewise smooth: the exit-plane sampler's edge set changes as the plane
crosses different cells, and the wall point count changes discretely with the inflection angle. So
the search is derivative-free, and the perturbation check that follows it is reported against a
measured noise floor rather than against zero. A margin smaller than the noise is reported as
exactly that.

What the objective is, and what it deliberately is not
------------------------------------------------------

The raw thrust coefficient, among candidates whose exit plane closes mass to within a small band
of the incumbent's. Both halves of that were arrived at by getting it wrong first.

Dividing the coefficient by the mass closure is the right way to COMPARE two families, because the
exit plane samples less mass than the throat passes and the momentum term scales with what it
samples: over a threefold change in mesh a fixed contour's raw coefficient moves 0.89 per cent
while the ratio moves 0.066. It is the wrong thing to OPTIMIZE, because the optimizer can raise
the ratio by driving the denominator down. Given that objective it did exactly that, walking to a
wall whose closure had fallen from 96 to 87 per cent and claiming a 21.8 per cent gain over the
parabola, which is two orders of magnitude larger than anything the literature reports.

So the band does the work the division was doing. Candidates are compared on raw coefficient, and
a candidate whose plane closes materially worse than the incumbent's is refused rather than
scored, on the grounds that its mesh is not comparable and its coefficient therefore is not
either.

The limit this cannot express
-----------------------------

**The march is isentropic, so nothing here charges a wall for the shock it would form.** A bell
that turns hard enough generates compression that coalesces, and the stagnation pressure lost
across that shock is precisely what stops a real thrust-optimized contour from turning harder. A
solver that does not model it sees only the benefit of turning, so an unconstrained search over
this family walks toward the hardest turn the box allows and reports a gain that does not exist.

The inflection angle is therefore bounded to the range Rao's own chart covers, and that bound is
a statement about where this model is trustworthy rather than about where good nozzles live. It
should be relaxed when, and only when, the shock loss is in the solve. Until then a converged
point sitting against that bound is a result about the bound.

Both coefficients and the closure are recorded on every candidate either way.

Validation status
-----------------

**Not validated against an external optimum, and there is no obvious way to be.** No source in the
reference set publishes wall coordinates for a Rao optimum contour, so there is nothing to compare
a contour against point by point. What can be established is internal and is: that the converged
point beats its neighbourhood by more than the measured noise, that it beats the parabola it
started from, and that the optimum does not move when the mesh is refined. The first two are
reported on every solve; the third needs the coarse and fine solves the driver runs anyway.

The published expectation the result is read against is the ordering, not a number: SP-8120 puts a
truncated ideal contour of the order of a quarter of a per cent behind the optimum, and reviews put
the gain from length-constrained optimization at half to one per cent in thrust at equal length.
A result outside that band is a reason to look at the solver rather than a discovery.

Author: Sean Bowman

'''

import numpy as np
from scipy.optimize import minimize

from .contour import (ContourSolution, raoWallAngles, thrustOptimizedContour,
                      thrustOptimizedParabolaWall)
from .gasDynamics import conicalLength
from .wallGeometry import parabolaAsCubicTensions

# Bounds on the four design variables, from the digitized Rao chart widened by about a third so
# the optimum is not pinned against a wall of the box by the chart's own range.
# The inflection bound is back to a generous 45 degrees, where it started. It was pulled in to 38
# while the march had no shock in it, because an isentropic solve charges a wall nothing for
# turning and the search ran straight to whatever limit it was given. The wall envelope now finds
# the coalescence and the exit plane is integrated against the stagnation pressure it costs, so
# the penalty is in the objective rather than in the box: the debit is 0.06 per cent at an
# inflection of 38 degrees and 3.6 per cent at 42. Whether that is enough to hold the search back
# on its own is a question the search answers, not this comment.
designVariableBounds = ((np.radians(15.0), np.radians(45.0)),      # inflection angle [rad]
                        (np.radians(0.0),  np.radians(20.0)),      # exit angle [rad]
                        (0.15, 0.85),                              # inflection tension [-]
                        (0.15, 0.85))                              # exit tension [-]

def parabolaDesignVector(throat, areaRatio: float, lengthFraction: float,
                        inflectionAngle: float = None, exitAngle: float = None) -> tuple:

    '''

    The design vector that reproduces a parabola exactly, from the chart or from given angles.

    The optimizer's starting point, and the incumbent every result is reported against. Because
    the cubic family contains the quadratic one, evaluating the objective here gives the parabola's
    own thrust coefficient through exactly the same solve the optimizer uses, which is what makes
    the comparison between them a comparison of walls rather than of code paths.

    Parameters:
    -----------
    throat : ThroatGeometry
        Supplies the throat radius and the exit arc.
    areaRatio : float
        Exit area over throat area [-].
    lengthFraction : float
        Length as a fraction of the 15 degree cone of the same area ratio [-].
    inflectionAngle, exitAngle : float
        Wall angles to build the parabola at [rad]. Both default to the chart reading, which is
        the incumbent. Supplying them is what lets the quadratic subfamily be searched: the two
        angles become the design variables and the tensions follow from them, so every vector the
        search visits is a genuine parabola rather than a cubic that resembles one.

    Returns:
    --------
    tuple : (inflectionAngle, exitAngle, inflectionTension, exitTension)

    '''

    chartInflection, chartExit, _ = raoWallAngles(areaRatio, lengthFraction)
    inflectionAngle = chartInflection if inflectionAngle is None else float(inflectionAngle)
    exitAngle = chartExit if exitAngle is None else float(exitAngle)
    nozzleLength = lengthFraction * conicalLength(areaRatio, throat.throatRadius)

    parabola = thrustOptimizedParabolaWall(throat.throatRadius, throat.outletCurvature, areaRatio,
                                           nozzleLength, inflectionAngle, exitAngle)
    quadratic = parabola.segments[1]
    start, control, end = (tuple(point) for point in quadratic.points)
    inflectionTension, exitTension = parabolaAsCubicTensions(start, control, end)

    return (float(inflectionAngle), float(exitAngle),
            float(inflectionTension), float(exitTension))

def isMonotoneWall(designVariables: tuple) -> bool:

    '''

    Whether a design vector describes a wall that turns one way.

    A cubic Bezier's tangent angle sweeps monotonically from its start angle to its end angle when
    its control polygon turns monotonically, and a bell wall that turns back on itself is not a
    bell. Checking it costs nothing and refusing a candidate here avoids a march that would have
    produced a mesh nobody wants an answer from.

    '''

    inflectionAngle, exitAngle, inflectionTension, exitTension = designVariables
    if not (exitAngle < inflectionAngle):
        return False
    if not (0.0 < inflectionTension < 1.0 and 0.0 < exitTension < 1.0):
        return False
    return inflectionTension + exitTension < 1.6

def solveThrustOptimizedContour(nozzle, lengthFraction: float,
                                numCharacteristicsCoarse: int = None,
                                numCharacteristicsFine: int = None,
                                searchFamily: str = 'cubic',
                                maximumEvaluations: int = 160,
                                maximumRestarts: int = 6,
                                restartTolerance: float = 1e-7,
                                closureTolerance: float = 0.01,
                                perturbationFraction: float = 0.01) -> dict:

    '''

    Search the cubic-Bezier bell family for the wall that gives the most thrust.

    Runs the search at a coarse mesh, re-solves the winner at the working mesh, and then measures
    whether the point it stopped at is actually a local optimum rather than simply where the
    optimizer ran out of patience.

    Takes the Nozzle rather than the workspace, for the same reason `contour.solveDesignPoint`
    does: each objective evaluation is a complete solve, and a Nozzle is what assembles one.

    Parameters:
    -----------
    nozzle : Nozzle
        Carrying a closed design point, so the chamber state is available.
    lengthFraction : float
        Length as a fraction of the 15 degree cone of the same area ratio [-].
    numCharacteristicsCoarse : int
        Mesh the search runs at. None searches at the working mesh, which is the default and
        should stay that way: see the note below on why searching coarse was false economy.
    numCharacteristicsFine : int
        Mesh the winner is re-solved at. None takes the nozzle's configured resolution.
    maximumEvaluations : int
        Cap on objective evaluations within one Powell run.
    maximumRestarts : int
        How many times Powell may be restarted from where it stopped. Restarting resets its
        direction set, which is what lets it leave a point it declared converged at.
    restartTolerance : float
        A restart that improves the merit by less than this ends the loop.
    perturbationFraction : float
        Size of the perturbation, as a fraction of each variable's range, used to test whether the
        converged point beats its neighbourhood.

    Returns:
    --------
    dict
        The converged design vector, both thrust coefficients, the parabola incumbent, the
        measured noise floor, the perturbation margin and the mesh sensitivity.

    '''

    from .characteristics import CharacteristicGas
    from .contourKernel import ThroatGeometry

    gas = CharacteristicGas(nozzle.chamberGamma, nozzle.chamberRGasConstant,
                            nozzle.chamberStagnationTemperature)
    throat = ThroatGeometry(nozzle.chamberGamma, nozzle.throatRadiusNonDimensional,
                            nozzle.throatInletCurvatureNonDimensional,
                            nozzle.throatOutletCurvatureNonDimensional)

    if numCharacteristicsFine is None:
        numCharacteristicsFine = int(getattr(nozzle, 'numCharacteristicsRequested', 50))

    # Search at the working mesh unless told otherwise, because searching coarse buys almost
    # nothing and costs the answer.
    #
    # The saving is small: `solveKernel` takes 3.8 seconds at a mesh of 21 and 5.0 at a mesh of
    # 51, because its cost sits in root finds at the throat rather than in the node count. So a
    # coarse pass is about a quarter cheaper per evaluation, not an order.
    #
    # What it costs is the result. The merit moves by more between two meshes than the optimum
    # beats its own neighbourhood by, so the landscape at a coarse mesh is not the landscape the
    # answer is read off. A search at a mesh of 14 returned a wall that scored 1.707 at the
    # working mesh against the parabola's 1.778: it had converged, on a different problem.
    if numCharacteristicsCoarse is None:
        numCharacteristicsCoarse = numCharacteristicsFine

    def workspace(mesh: int) -> ContourSolution:
        return ContourSolution(
            gas = gas, throat = throat,
            chamberPressure = nozzle.chamberPressure,
            engineMassFlow = nozzle.engineMassFlow,
            throatGamma = nozzle.throatGamma,
            idealMachNumber = nozzle.idealMachNumber,
            targetExitPressure = nozzle.targetExitPressure,
            numContourPoints = nozzle.numContourPoints,
            requestedAreaRatio = float(nozzle.expansionRatio),
            truncateOn = nozzle.truncateOn,
            numCharacteristicsRequested = mesh,
            ambientSpecificImpulse = nozzle.ceaOutput.nozzlePerformance['ambientISP[s]'],
            plotsDocs = 'off')

    evaluations = {'count': 0}

    def merit(designVariables: tuple, mesh: int) -> tuple:

        '''Thrust coefficient over mass closure, and the raw pair behind it.'''

        if not isMonotoneWall(designVariables):
            return refusedMerit, np.nan, np.nan

        evaluations['count'] += 1
        try:
            state = thrustOptimizedContour(workspace(mesh), lengthFraction, designVariables,
                                           assignOutputsToObject = False)
        except Exception:                                               # noqa: BLE001
            # A wall the march cannot solve is not a candidate. Returning rather than raising
            # keeps one bad vector from ending a search that is otherwise going well.
            return refusedMerit, np.nan, np.nan

        thrustCoef, closure = state.thrustCoef, state.exitMassClosure
        if thrustCoef is None or closure is None or not np.isfinite(thrustCoef):
            return refusedMerit, np.nan, np.nan

        # The comparability band. A plane that closes materially worse than the incumbent's is a
        # mesh this candidate cannot be judged on, whatever coefficient it reports.
        #
        # Refused GRADUALLY rather than absolutely, and the difference is not cosmetic. An
        # infinite penalty says a region is bad without saying which way is out of it, so a whole
        # Powell iteration inside one makes no progress, its updated direction collapses to zero,
        # and scipy fails inside its own line search on an empty array. A penalty proportional to
        # how far outside the band a candidate sits leaves the objective finite and pointed back
        # toward the feasible region.
        reference = closureBand.get('incumbent')
        if reference is not None and closure < reference - closureTolerance:
            shortfall = (reference - closureTolerance) - closure
            return float(thrustCoef - refusalGradient * shortfall), float(thrustCoef), float(closure)

        return float(thrustCoef), float(thrustCoef), float(closure)

    # Finite, because an optimizer cannot walk out of a region it is told is infinitely bad.
    # Far enough below any real thrust coefficient to never win, close enough to stay a number.
    refusedMerit = -1.0e3
    refusalGradient = 20.0

    # -- Which family is being searched, and how a search point becomes a wall -- #
    #
    # `merit` always takes a full four-variable design vector, so the two families differ only in
    # what the optimizer is allowed to vary and how that maps onto one. Under `cubic` the map is
    # the identity. Under `quadratic` the optimizer varies the two wall angles and the tensions
    # are derived from them, which confines the search to the surface inside the cubic box on
    # which every wall is a genuine parabola.
    #
    # The point of running both is that today's comparison cannot separate two different things.
    # A searched cubic beating the CHART parabola could mean the cubic family is better, or it
    # could mean the chart reading is poor, and the chart is a digitization that carries a known
    # transcription error. Searching the quadratic subfamily splits them: quadratic against chart
    # is what the chart costs, and cubic against quadratic is what the extra freedom buys.
    if searchFamily not in ('cubic', 'quadratic'):
        raise ValueError(f"No search family called '{searchFamily}'. "
                         f"Choose from 'cubic' or 'quadratic'.")

    areaRatio = float(nozzle.expansionRatio)
    if searchFamily == 'cubic':
        searchBounds = designVariableBounds
        toDesignVector = lambda variables: tuple(float(value) for value in variables)
    else:
        searchBounds = designVariableBounds[:2]
        toDesignVector = lambda variables: parabolaDesignVector(
            throat, areaRatio, lengthFraction,
            inflectionAngle = float(variables[0]), exitAngle = float(variables[1]))

    closureBand = {}
    incumbent = parabolaDesignVector(throat, float(nozzle.expansionRatio), lengthFraction)
    incumbentSearch = incumbent if searchFamily == 'cubic' else incumbent[:2]
    incumbentCoarse = merit(incumbent, numCharacteristicsCoarse)
    closureBand['incumbent'] = incumbentCoarse[2]

    objective = lambda variables: -merit(toDesignVector(variables), numCharacteristicsCoarse)[0]

    # Powell is restarted from wherever it stopped, until a restart stops finding anything.
    #
    # Not a refinement. Powell searches along a set of directions it builds as it goes, and on a
    # objective with any structure to it those directions can become nearly parallel, at which
    # point it reports success while sitting somewhere a single coordinate step would improve on.
    # The first run of this driver did exactly that: it converged, declared success, and left a
    # neighbour better by fifteen thousand times the measured noise floor. Restarting resets the
    # direction set, and the loop ends when a whole restart cannot better the point it began at.
    start = np.array(incumbentSearch, dtype = float)
    bestMerit, restarts = -np.inf, 0
    result = None

    for restarts in range(1, maximumRestarts + 1):
        result = minimize(objective, start, method = 'Powell',
                          bounds = searchBounds,
                          options = {'maxfev': maximumEvaluations, 'xtol': 1e-6, 'ftol': 1e-9})
        gained = -float(result.fun) - bestMerit
        bestMerit = -float(result.fun)
        start = np.array(result.x, dtype = float)
        if gained < restartTolerance:
            break

    convergedSearch = tuple(float(value) for value in result.x)
    converged = toDesignVector(convergedSearch)
    coarseMerit = bestMerit

    # -- The winner at the working mesh, and the incumbent beside it for comparison -- #
    #
    # The band has to be re-referenced first. It compares a candidate's mass closure against the
    # incumbent's, and the incumbent's closure is a function of the mesh: carried over from the
    # coarse pass it would refuse the fine-mesh solves, the incumbent's own included.
    closureBand.pop('incumbent', None)
    incumbentFine = merit(incumbent, numCharacteristicsFine)
    closureBand['incumbent'] = incumbentFine[2]

    fineMerit, fineThrust, fineClosure = merit(converged, numCharacteristicsFine)

    # -- A search that found nothing better returns the incumbent, and says so -- #
    #
    # Rejection is graded rather than infinite, so an infeasible candidate still carries a finite
    # score, and a search on a tight budget can wander into that region and converge inside it.
    # Left alone the driver then hands back a penalised wall as its answer: the study that
    # prompted this guard had two design points reporting gains of minus thirty-seven and minus
    # forty-three per cent, on walls whose exit planes closed four points worse than the parabola
    # they were being compared with.
    #
    # Failing to improve on the incumbent is a legitimate outcome and belongs in the output as
    # one. What is not legitimate is presenting the failure as a contour.
    improvedOnIncumbent = bool(np.isfinite(fineMerit) and fineMerit > incumbentFine[0])
    if not improvedOnIncumbent:
        converged, convergedSearch = incumbent, incumbentSearch
        fineMerit, fineThrust, fineClosure = incumbentFine

    # -- Is this a local optimum, or just where the search stopped -- #
    #
    # The noise floor first. A perturbation far too small to be physical still moves the answer,
    # because the mesh reorganizes under it; whatever it moves by is the resolution of any claim
    # made below.
    # Perturbations walk the SEARCH space, not the design vector. Under `quadratic` the two are
    # different sizes, and nudging a tension directly would step off the subfamily the search was
    # confined to, which would test a neighbourhood the optimizer was never allowed to reach.
    spans = np.array([upper - lower for lower, upper in searchBounds])

    def admissible(searchPoint):
        '''
        The merit of a candidate that was actually scored, or None if it was refused.

        Finiteness is not the test, and using it was a defect. A refused candidate comes back
        with a large negative merit or a graded penalty, and both are finite, so a neighbourhood
        in which every perturbation is refused looked like a neighbourhood in which every
        perturbation was worse. That is what a demonstrated optimum is supposed to mean, and it
        made "no admissible neighbour exists" indistinguishable from "this point beats its
        neighbours". A candidate counts only when its merit IS its thrust coefficient, which is
        the case exactly when nothing was subtracted from it.
        '''
        value, thrust, _ = merit(toDesignVector(searchPoint), numCharacteristicsFine)
        if not np.isfinite(value) or not np.isfinite(thrust):
            return None
        return value if abs(value - thrust) <= 1e-12 * max(1.0, abs(thrust)) else None

    noiseFloor = 0.0
    for index in range(len(convergedSearch)):
        nudged = list(convergedSearch)
        nudged[index] += 1e-6 * spans[index]
        value = admissible(nudged)
        if value is not None:
            noiseFloor = max(noiseFloor, abs(value - fineMerit))

    bestNeighbour = -np.inf
    admissibleNeighbours = 0
    for index in range(len(convergedSearch)):
        for direction in (-1.0, 1.0):
            nudged = list(convergedSearch)
            nudged[index] += direction * perturbationFraction * spans[index]
            lower, upper = searchBounds[index]
            nudged[index] = float(np.clip(nudged[index], lower, upper))
            value = admissible(nudged)
            if value is not None:
                admissibleNeighbours += 1
                bestNeighbour = max(bestNeighbour, value)

    perturbationMargin = bestNeighbour - fineMerit if admissibleNeighbours else np.nan

    searchMeshMatchesReport = (numCharacteristicsCoarse == numCharacteristicsFine)
    usable = bool(np.isfinite(fineMerit) and fineMerit > 0.0)

    return {
        'usable':                 usable,
        'searchFamily':           searchFamily,
        'improvedOnIncumbent':    improvedOnIncumbent,
        'searchMeshMatchesReport': searchMeshMatchesReport,
        'designVariables':        converged,
        'incumbent':              incumbent,
        'coarseMerit':            coarseMerit,
        'merit':                  fineMerit,
        'thrustCoef':             fineThrust,
        'exitMassClosure':        fineClosure,
        'incumbentClosure':       incumbentFine[2],
        'incumbentMerit':         incumbentFine[0],
        'incumbentThrustCoef':    incumbentFine[1],
        'gainOverParabola':       fineMerit / incumbentFine[0] - 1.0
                                  if np.isfinite(incumbentFine[0]) and incumbentFine[0] else np.nan,
        # The raw gain above compares two coefficients whose exit planes need not sample the same
        # mass, and the difference between two closures is routinely larger than the difference
        # between two contours. This one divides that out, and it is the figure to quote.
        'normalizedGainOverParabola': ((fineThrust / fineClosure)
                                       / (incumbentFine[1] / incumbentFine[2]) - 1.0
                                       if all(np.isfinite(v) for v in
                                              (fineThrust, fineClosure, incumbentFine[1],
                                               incumbentFine[2]))
                                       and fineClosure and incumbentFine[2] and incumbentFine[1]
                                       else np.nan),
        'objectiveNoiseFloor':    noiseFloor,
        'perturbationMargin':     perturbationMargin,
        'admissibleNeighbours':   admissibleNeighbours,
        # Three things have to hold together. A neighbour has to have been scored at all, it has
        # to be worse, and it has to be worse by more than the mesh moves the answer on its own.
        'isLocalOptimum':         bool(admissibleNeighbours > 0
                                       and np.isfinite(perturbationMargin)
                                       and perturbationMargin < -noiseFloor),
        'meshSensitivity':        fineMerit - coarseMerit,
        'evaluations':            evaluations['count'],
        'restarts':               restarts,
        'optimizerMessage':       str(result.message),
        'optimizerSucceeded':     bool(result.success),
    }
