# Plume development: state of play

A record of where the plume solver stands, written to be picked up cold. It covers what exists, what is validated and against what, what is broken, and the findings that cost the most to establish and should not be rediscovered.

The immediate reason work stopped here: verification of the contour generator turned up defects upstream of the plume, and those are being addressed first. Nothing below depends on that work finishing, but two of the open items may be resolved by it.

## Where the code is

The solver lives in `src/NOVA/plume.py`, in three layers, and is re-exported from `Nozzle.py` so existing imports resolve unchanged.

The correlations place the jet boundary, the shock cell spacing and the Mach disk from published fits, and solve nothing.

`PlumeGas`, `PlumeNode` and the `freeJet*` functions are the TN D-2327 lattice, transcribed from the FORTRAN listings. `experimental/tnd2327.py` is a thin shim onto them so the studies in this directory can drive the net directly, at operating points well outside anything the product would accept.

`PlumeFlow`, `PlumePoint`, the `plume*Point` unit processes and `solvePlumeMarch` are the march that continues the nozzle characteristics solution past the lip. This is the one that matters. `Nozzle.plumeField` is its product face.

The nozzle unit process the march is meant to continue is `characteristics.axisymmetricMethodOfCharacteristics`, which is importable rather than buried in a closure, so the two can be compared directly.

Tests are `tests/testPlume.py`, `tests/testPlumeMarch.py`, `tests/testPlumeField.py` and `tests/testCharacteristics.py`, 97 tests together.

## The shipped envelope, and the part of it that is not enforced

`Nozzle.plumeField` is the only product face on a solved plume, and `solvePlumeField` admits or refuses a case on four conditions: a plume structure exists, the exit Mach number lies in `plumeFieldMinExitMach` to `plumeFieldMaxExitMach`, 1.5 to 5.0; the exit static pressure ratio is at or above `separationPressureRatio`, 0.4, which is the Summerfield criterion for the nozzle separating internally; the contour carries a characteristic mesh, which a conical one does not; and the march returned at least ten nodes.

**Three of the five envelope constants are dead.** `plumeFieldMinPressureRatio` at 1.05, `plumeFieldMaxPressureRatio` at 2.0 and `plumeFieldMaxWallAngle` at half a degree are defined beside the two that work, re-exported through `Nozzle.py` and imported by `tests/testPlumeField.py`, and they appear in no conditional anywhere in the package.

That matters because the documentation states the opposite. `docs/references_plumeStructure_2026-09-04.md` records that `Nozzle.plumeField` refuses beyond half a degree of exit divergence, which excludes every bell contour. It does not refuse. A bell contour reaching `plumeField` is marched by a solver that stops after about one shock cell on a divergent exit, and the only thing standing between that and a returned field is the ten node floor. The jet static pressure ratio band is unenforced in the same way, at both ends.

Either the constants are wired into `solvePlumeField` or they are deleted and the claim rewritten. The first is the smaller change and matches what every document says is already true.

## What is validated, and against what

**The interior point reproduces the compatibility relations exactly on one pass.** Not to a tolerance, to `0.00e+00` on position, Mach number and flow angle across four kernels, against the relations transcribed into `tests/testPlumeMarch.py` as a fixture. If the plume's relations ever drift from those, it stops being an extension of the contour solve and becomes a second approximation of it, which is what that test exists to prevent.

**Converged, the plume and the nozzle unit processes differ by about one per cent.** The nozzle version is now importable, as `characteristics.axisymmetricMethodOfCharacteristics`, so the two can be compared directly rather than through a transcription, and `tests/testCharacteristics.py` does that. They agree on the first pass and separate under iteration, because the nozzle moves both upstream points toward the intersection under a fixed weight and re-evaluates while the plume holds the upstream points and averages the characteristic properties along each characteristic. On three representative kernels the converged answers land within 1.1 per cent in Mach number, 1.3 per cent in axial position and 0.7 degrees in flow angle. There is also a one-ulp difference in the limiting velocity, written `sqrt(gamma R) sqrt(2 T0 / (gamma - 1))` by the nozzle and `sqrt(2 gamma R T0 / (gamma - 1))` by the plume, which is recorded but is not what causes the one per cent.

**The unit process is second order, checked against exact planar theory.** Far from the axis the axisymmetric term vanishes and the Riemann invariants of planar flow must be conserved. Halving the state jump between the two upstream points quarters the departure from them: measured orders run 1.88, 1.94, 1.97, 1.99, 1.99. This is the only check on the scheme against a result that does not come from the code, and it is what rules out a scheme that is self-consistent and wrong.

**The shock cell period matches Prandtl (1904).** At a parallel exit near design, measured as the axial period between successive boundary crests over fourteen cells, the march lands within half a per cent. This is the only external validation the solver has, and it holds only where Prandtl's linearised result does: a parallel exit, mildly off design.

**Mass conservation is the internal check.** Every characteristic line spans the jet from the axis to the free boundary, so every one carries the whole mass flow and they must all carry the same. `plumeMassFlux` integrates it and the march reports its own worst departure. A parallel exit holds 0.03 per cent over a thousand lines. Nothing external is needed, which makes it the only quality measure available at an operating point with no correlation to compare against.

**Conservation does not bound the interior.** Held against NASA TR R-6's table II, a dense characteristic net for a near-sonic exit at a jet static pressure ratio of 2, the station marcher over-predicts the center-line wave by 7.8 per cent of its own amplitude rms while conserving mass to two tenths of a per cent and leaving the boundary unaffected. That report computed table II to establish the point: errors near the axis may have negligibly small effects on the boundary shape, even for a sonic exit. Whatever passes conservation and a boundary check here is not thereby validated in the interior, and the same caution applies to this march, which has never been held against table II at all.

**The lip fan and the leading characteristic reproduce TN D-2327's tabulated cases**, boundary Mach numbers 19.70 and 16.38 and the worked axis state at Mach 12.02, to better than a tenth of a per cent.

## What is open

The order below is the order the items were found in, which is no longer the order worth attacking them in. Diagnosing the first two moved the third.

**Shock detection is now the gating item.** It decides where both solvers stop, and at present the characteristic march stops at a coalescence without knowing that is what happened, while the station marcher does not stop at all and reports converging conservation while it integrates through one. Nothing else on this list can be finished without it: an interior error cannot be attributed while the solution may contain a discontinuity nothing has flagged, and an envelope cannot be drawn around a solver that does not know when it has left the region its equations describe.

After that, the initial line work is closed, the reach limits are understood and are physical, and what remains is the interior accuracy of both solvers and the gas model.

**The divergent exit, which is two defects and only one of them is the solver's.** The march stops after about one shock cell whenever the exit diverges, which is every bell contour. This is the single thing standing between the solver and the nozzles NOVA actually designs.

The conservation collapse recorded here previously was the initial line rather than the divergence. Driving the march at Mach 3 and a jet static pressure ratio of 1.05 from a uniform Mach number at a constant flow angle, which is what every earlier sweep used, gives mass drift of 4.5 per cent at two degrees, 21 at three, 53 at five and 70 at eight. Driving it from a conical source flow, which is the exact exit of a conical nozzle and carries zero flow angle on the center line, gives 0.11, 0.15, 0.26 and 0.36 per cent at the same four angles. Two hundred times better, from the initial condition alone.

A constant flow angle across the exit puts that angle on the center line, where symmetry forbids it. The march accepts such a line because it never applies the axis condition to what it is handed; the station marcher rejects it at the first station. Any divergence result in this repository taken on a constant-angle line is measuring that, not the exit angle.

What survives the correction is the reach. A conical exit at two to five degrees still ends between 6.4 and 6.6 lip radii against 17.2 at a parallel exit, and every one of them ends on a failed boundary point. Past about eight degrees conservation collapses again on the conical line too, to 41 per cent at eleven degrees, so there is a second and genuine high-divergence limit behind the first.

**Both open items above fail in the same function.** A parallel exit at a ratio of 1.2 and a conical exit at two degrees both end with `boundaryPointFailed`, in `plumeFreeBoundaryPoint`, with mass drift of a tenth of a per cent at the moment they stop. The solution is accurate right up to the wall it hits, so what is wrong is the free boundary unit process rather than the mesh behind it, and one repair addresses both.

Two things about the recorded -24.6 per cent at five degrees and -34.3 at eleven are now measured rather than assumed. Most of it is the measure: the station marcher puts the first crest 52 per cent nearer the lip at five degrees while the crest-to-crest period moves +6.04, so divergence throws the boundary out early without changing the axial period, which is what TR R-6 reports. The rest is the initial line: a uniform Mach number at a constant nonzero flow angle sets a flow angle on the center line, which symmetry forbids, and the station marcher rejects such a line at its first station for every angle. This march accepts it because it never applies the axis condition to its initial line. A conical source flow is the exact exit of a conical nozzle and is what TR R-6's hardware delivers.

**The pressure ratio ceiling is lower than the physics, and how much lower depends on `numRays`.** At the default of forty rays a parallel exit at Mach 3 reaches 17.2 lip radii at a jet static pressure ratio of 1.05 and 1.1, both ending on the line budget rather than on a failure, and then ends on a failed boundary point at 7.3 radii at a ratio of 1.2, 9.2 at 1.5 and 4.0 at 2.0. Mass drift at those failures is 0.1 to 0.3 per cent, so the march is accurate right up to the point it stops: what fails is the boundary point, not the solution behind it.

Raising the ray count makes it worse rather than better. The same ratio of 1.2 ends at 3.3 lip radii at a hundred and twenty rays, and a ratio of 1.5 carries 38 per cent drift there against a quarter of a per cent at forty. Earlier records in this document quoted the hundred and twenty ray figures without saying so, which made the ceiling look lower and the drift look worse than the shipped default produces. `solvePlumeMarch` already records the same inversion for a contoured exit line and calls it unexplained; it is the same effect.

**The march stops where a shock forms, and stopping is the right answer.** The stall was read as a mesh defect for as long as nobody looked at what the flow was doing there. It is a coalescing compression.

Two measurements establish it. The boundary does not fail, it converges to a fixed point: over the last eleven lines of the parallel case at a ratio of 1.2 the boundary advances 3.2e-3, 9.5e-4, 8.7e-4, 2.3e-3, 6.4e-4, 5.6e-4, 1.4e-3, 3.3e-4, 2.4e-4, 4.1e-4 and finally 6.6e-6 lip radii, and the gap between each new line's outer end and the previous boundary point closes the same way. Only after that does a shortened line return a point eight ten-thousandths of a radius upstream, which is what `boundaryPointFailed` reports. A tolerance on that test would buy a few lines and nothing else.

And the flow at the stall carries a gradient with no converged value, sitting on the boundary itself. Measured with the station marcher at the same condition, the steepest radial Mach gradient within half a lip radius of the stall runs 2.355, 4.350 and 8.252 over 41, 81 and 161 points across the jet, growing by 1.85 and 1.90 per doubling against the 2.0 of a true discontinuity. The lip fan in the same solutions grows at exactly 2.0, being a centered expansion. At a ratio of 1.05, where the march survives seventeen lip radii, the largest gradient in the field grows at 1.60 and 1.47 and there is no such feature downstream at all.

Where it sits is what makes it this solver's problem. Over those stations the gradient peaks at a radius fraction of 1.000, on the free boundary, while the inner third of the jet reads 0.071, 0.076 and 0.079 and is converged. The compression is coalescing onto the boundary, which is the one place the march closes its lines, so the boundary point is the first thing to feel it.

That also settles why the march is not simply intolerant of steep gradients. At a ratio of 1.5 the strongest feature in the field is an axis focus at 5.21 lip radii growing at 3.1 and 2.47 per doubling, and the march passes straight through it, stalling later at 9.17 where the boundary gradient goes again. It tolerates a focus on the center line and stops at a coalescence on the boundary.

So the ceiling is the physics after all, and the sentence this paragraph used to carry, that the limit belongs to the mesh rather than to the relations, was wrong.

**What that says about the station marcher is worse than what it said about the march.** On the same case it runs the full fourteen lip radii with mass drift of 0.596, 0.261 and 0.146 per cent over those three resolutions, halving cleanly, while marching straight through the coalescence. Its conservation residual reports first-order convergence on a solution containing a discontinuity it cannot represent. Conservation does not detect a shock, which is the same lesson TR R-6's table II teaches about the boundary, arriving from a third direction.

Neither solver should be trusted past a coalescence, and only one of them currently notices one. Shock detection is therefore not a later refinement; it is what decides where both solvers stop.

**The axisymmetric source term is ill-conditioned where the flow angle reaches the Mach angle.** `_rightRunningTerm` divides by `sin(theta - mu)` and its increment carries `tan(theta - mu)`, so both vanish together as the second-family characteristic turns axis-parallel and their product is set by which state each was evaluated at. Cancelling them analytically gives `sin(theta) sin(mu) / cos(theta +/- mu) * dx / r`, which `stationMarch` uses and which took its worst drift from 7.20 per cent to 0.97 on a parallel exit at a ratio of 2. Substituting it here moves the march's drift by a thousandth of a per cent and does not change where it fails, so it is left alone: it costs the bit-level agreement with the nozzle solver that `testInteriorPointReproducesTheNozzleSolverExactly` holds, and buys nothing this solver needs. The conditioning is therefore a known weakness of this module rather than the cause of any failure recorded above.

**The advancing front.** The march computes one characteristic at a time from a fixed start, which leaves the center line trailing the boundary and the solved region shaped like a wedge. Advancing a whole data line downstream together would remove that, and would remove the center-line restart and its sub-stepping in thirds with it. `solvePlumeFront` exists and is marked NOT YET USABLE, and is now superseded: `experimental/stationMarch.py` prescribes the data line rather than letting the characteristics choose it, and `experimental/stationMarchState.md` carries where that stands.

Two defects were found in the front while diagnosing it. Its free boundary point crossed a characteristic leaving the new line against a streamline leaving the old boundary, mixing the two; taking both parents from the old line carries it from eleven steps to fifty four, and that is fixed. The one that ends it is structural: the line rotates into the first-family characteristic direction, measured at the stall as 0.00 degrees of separation over part of its length, with the spacing along it spanning 114 to 1. A data line lying on a characteristic carries no information across itself, which is why prescribing the line is the answer rather than patching the advance.

**Shock coalescence, which is now the first thing to attack rather than the fourth.** `plumeSameFamilyPoint` and `plumeShockCrossing` are written and driven, and default off. The crossing test underneath them is resolution dependent, so they fire on characteristics that would not meet for many jet radii, and each false merge deletes a wave. On the one case that validates they cost more than they buy. Even working, they would give a coalescence inside an isentropic net, with no entropy jump, which is sound only while a shock is weak.

Detection is separable from coalescence and is the part that is needed first. Both solvers already carry enough to measure it without merging anything: a compression coalescing on the free boundary shows up as a radial gradient there whose value does not converge under refinement, 1.85 and 1.90 per doubling at a ratio of 1.2 against 1.60 and 1.47 for the same field at 1.05 where none forms. A criterion built on the ratio between two resolutions is not resolution dependent in the way the crossing test is, which is what made that test unusable. What it buys is that the march can say it stopped at a shock rather than that its boundary point failed, and that the station marcher can refuse to continue through one instead of reporting a converging conservation residual on a solution containing it.

**Rotational method of characteristics.** The destination for a strongly underexpanded plume, where the barrel shock is not weak. Deferred deliberately: the failures met so far have all been bookkeeping in a marching scheme, not missing entropy, and adding shock physics on top of a march that stalls would not help. Note also that shock fitting still needs to know where a shock starts, so the detection problem above follows it there.

**Performance.** Pure Python, roughly a hundred seconds for eight thousand lines. Adequate for study, not for an interactive path. numba is neither installed nor declared.

**The gas model, now with a number on it.** Every layer here treats the exhaust as calorically perfect at one ratio of specific heats, and the mesh carries the chamber value. A real exhaust recombines as it expands, and where it stops recombining is a kinetics problem that nothing in NOVA solves. The two limits bracket it, and CEA gives both, so the bracket can be quoted rather than described. On the LOX/LH2 reference engine at 6.89 MPa, a mixture ratio of 5.5 and an area ratio of 40:

| Quantity | Equilibrium | Frozen at throat | Frozen in chamber |
|---|---|---|---|
| Exit gamma | 1.2572 | 1.2801 | 1.2879 |
| Exit Mach | 4.2234 | 4.3901 | 4.4227 |
| Exit temperature [K] | 1275.3 | 1083.0 | 1025.4 |
| Exit velocity [m/s] | 4259.9 | 4168.9 | 4118.4 |
| Throat gamma | 1.1502 | 1.2027 | 1.2027 |

So the chemistry choice alone is worth 4 per cent in exit Mach number and 1.8 per cent in exit gamma, which the correlations and the march both read, and 15 per cent in exit temperature, which anything thermal reads. It is 2.1 per cent in exit velocity, which is the standard equilibrium-to-frozen performance bracket and the size of the uncertainty any one-dimensional performance number here carries.

Three consequences worth separating. The plume geometry inherits the exit Mach and gamma, so a 4 per cent Mach shift moves the cell spacing and the boundary by about as much as the divergent-exit conservation error above. Nothing solved on the equilibrium side is conservative for a jacket, since equilibrium runs the gas hottest. And the mesh gamma, 1.1475 at the chamber, is far from the exit value under either chemistry, which is the same gap the finding above records from the other direction.

What would close it: driving the CEA calls from a `chemistryModel` selector so a run can be solved at either limit and the bracket reported, rather than equilibrium being assumed silently. That is plumbing rather than physics. Closing it properly means local properties through the mesh, which is the same different solver the effective-gamma note in `gasDynamics.effectiveGamma` names.

## Findings worth not rediscovering

**A front cannot be seeded from the march's own lines.** Those lines are first-family characteristics: 250 of 250 neighbouring pairs lie along the very characteristic the advance would cross against its neighbour's, so the intersection returns a point already on the front. Any working front has to start from a station, not a wave. A test records this.

**Lip to first crest is not the wavelength.** The lip fan throws the boundary wide before the pattern settles, so the first crest sits about ten per cent beyond half a period. Measuring the cell that way reads consistently long and was for some time mistaken for a physical discrepancy. TR R-6 separates the primary wavelength from the secondary and records that the two differ, which shows in the solver as well: early cells run short and the period settles as the march goes on.

**Grid convergence and reach are confounded.** Refining the mesh improves conservation monotonically and worsens the apparent period agreement, because a finer mesh costs reach, fewer cells get averaged, and early cells are shorter. Any period quoted has to say how many cells it averaged. `convergeMarch.py` runs the sweep.

**Appendix A's leading characteristic is a source flow.** It assumes the exit plane diverges uniformly at the wall angle, which is the opposite of what a contoured nozzle is built to do. `plumeExitLine` takes the exit plane from the contour solve instead, and `solvePlumeMarch` accepts it through `initialLine`. That correction is necessary and was not sufficient.

**Use the mesh's gamma, not the exit gamma.** `plumeStructure` reports CEA's exit gamma because that is the better number for a correlation evaluated at the exit. The characteristic mesh is built on the chamber gamma. Reading mesh Mach numbers under a different ratio of specific heats makes the state discontinuous at the exit plane and destroys conservation: on the worked case it put the exit flux 150 per cent above the choked throat flow, which was for a while mistaken for a defect in the march. With the mesh gamma the same flux lands within 0.2 per cent.

**Two bookkeeping defects, both of which looked like physics.** Lines grew by one point per line until the march drowned in its own mesh and the center line stopped advancing; TN D-2327 counts the line length down rather than up. And `outsideBoundary` once extrapolated the unknown boundary from the anchor's own flow angle, which in recompression rejected valid points. Neither was an entropy problem, and both were found by asking what a case with no shock in it was doing.

## Reproducing

Run from the NOVA root with `C:\Users\seanb\miniconda3\python.exe`.

```
python -m pytest tests/testPlume.py tests/testPlumeMarch.py tests/testPlumeField.py tests/testCharacteristics.py   # 97 tests
python experimental/convergeMarch.py        # grid convergence of the march
python featureShowcase/buildPlumeMarch.py   # the figures
python featureShowcase/verifyContour.py     # contour against its references
```

`featureShowcase/plumeCellTrain.png` is the validated case and the one to look at first. `plumeContinuousField.png` is currently near empty on the worked nozzle and says so; it is not a result.

## What the contour work may settle

Two of the open items sit downstream of the contour generator rather than inside the plume.

The nozzle delivers an area ratio of 69.84 against the 40 requested and 0.639 of the conical reference length against the 0.80 requested, because the pressure match drives the pressure at the wall to a one-dimensional target. Until the delivered geometry is the requested geometry, no plume result on that contour describes the nozzle anyone asked for.

`nozzleNearWallMachNumber` and the characteristic mesh disagree about the wall state, by twelve per cent at the exit and in the other direction upstream. The march reads the mesh; anything reading the near-wall array sees something else. Which of the two is right is not established.
