# Plume development: state of play

A record of where the plume solver stands, written to be picked up cold. It covers what exists, what is validated and against what, what is broken, and the findings that cost the most to establish and should not be rediscovered.

The immediate reason work stopped here: verification of the contour generator turned up defects upstream of the plume, and those are being addressed first. Nothing below depends on that work finishing, but two of the open items may be resolved by it.

## Where the code is

The solver lives in `src/NOVA/plume.py`, in three layers, and is re-exported from `Nozzle.py` so existing imports resolve unchanged.

The correlations place the jet boundary, the shock cell spacing and the Mach disk from published fits, and solve nothing.

`PlumeGas`, `PlumeNode` and the `freeJet*` functions are the TN D-2327 lattice, transcribed from the FORTRAN listings. `experimental/tnd2327.py` is a thin shim onto them so the studies in this directory can drive the net directly, at operating points well outside anything the product would accept.

`PlumeFlow`, `PlumePoint`, the `plume*Point` unit processes and `solvePlumeMarch` are the march that continues the nozzle characteristics solution past the lip. This is the one that matters. `Nozzle.plumeField` is its product face.

The nozzle unit process the march is meant to continue is `characteristics.axisymmetricMethodOfCharacteristics`, which is importable rather than buried in a closure, so the two can be compared directly.

Tests are `tests/testPlumeMarch.py`, `tests/testPlumeField.py` and `tests/testCharacteristics.py`. The whole suite is 278 tests.

## What is validated, and against what

**The interior point reproduces the compatibility relations exactly on one pass.** Not to a tolerance, to `0.00e+00` on position, Mach number and flow angle across four kernels, against the relations transcribed into `tests/testPlumeMarch.py` as a fixture. If the plume's relations ever drift from those, it stops being an extension of the contour solve and becomes a second approximation of it, which is what that test exists to prevent.

**Converged, the plume and the nozzle unit processes differ by about one per cent.** The nozzle version is now importable, as `characteristics.axisymmetricMethodOfCharacteristics`, so the two can be compared directly rather than through a transcription, and `tests/testCharacteristics.py` does that. They agree on the first pass and separate under iteration, because the nozzle moves both upstream points toward the intersection under a fixed weight and re-evaluates while the plume holds the upstream points and averages the characteristic properties along each characteristic. On three representative kernels the converged answers land within 1.1 per cent in Mach number, 1.3 per cent in axial position and 0.7 degrees in flow angle. There is also a one-ulp difference in the limiting velocity, written `sqrt(gamma R) sqrt(2 T0 / (gamma - 1))` by the nozzle and `sqrt(2 gamma R T0 / (gamma - 1))` by the plume, which is recorded but is not what causes the one per cent.

**The unit process is second order, checked against exact planar theory.** Far from the axis the axisymmetric term vanishes and the Riemann invariants of planar flow must be conserved. Halving the state jump between the two upstream points quarters the departure from them: measured orders run 1.88, 1.94, 1.97, 1.99, 1.99. This is the only check on the scheme against a result that does not come from the code, and it is what rules out a scheme that is self-consistent and wrong.

**The shock cell period matches Prandtl (1904).** At a parallel exit near design, measured as the axial period between successive boundary crests over fourteen cells, the march lands within half a per cent. This is the only external validation the solver has, and it holds only where Prandtl's linearised result does: a parallel exit, mildly off design.

**Mass conservation is the internal check.** Every characteristic line spans the jet from the axis to the free boundary, so every one carries the whole mass flow and they must all carry the same. `plumeMassFlux` integrates it and the march reports its own worst departure. A parallel exit holds 0.03 per cent over a thousand lines. Nothing external is needed, which makes it the only quality measure available at an operating point with no correlation to compare against.

**The lip fan and the leading characteristic reproduce TN D-2327's tabulated cases**, boundary Mach numbers 19.70 and 16.38 and the worked axis state at Mach 12.02, to better than a tenth of a per cent.

## What is open

Roughly in the order worth attacking.

**The divergent exit.** The march stops after about one shock cell whenever the exit diverges, which is every bell contour. Conservation degrades with the angle, from 0.03 per cent at a parallel exit to about one per cent at fourteen degrees. Fan resolution accounts for part of it on a uniform exit line and saturates; the residual is unexplained. This is the single thing standing between the solver and the nozzles NOVA actually designs.

**The advancing front.** The march computes one characteristic at a time from a fixed start, which leaves the center line trailing the boundary and the solved region shaped like a wedge. Advancing a whole data line downstream together would remove that, and would remove the center-line restart and its sub-stepping in thirds with it. `solvePlumeFront` exists and is marked NOT YET USABLE: it advances stably but stalls after about thirty steps. See the finding below before restarting it.

**Shock coalescence.** `plumeSameFamilyPoint` and `plumeShockCrossing` are written and driven, and default off. The crossing test underneath them is resolution dependent, so they fire on characteristics that would not meet for many jet radii, and each false merge deletes a wave. On the one case that validates they cost more than they buy. Even working, they would give a coalescence inside an isentropic net, with no entropy jump, which is sound only while a shock is weak.

**Rotational method of characteristics.** The destination for a strongly underexpanded plume, where the barrel shock is not weak. Deferred deliberately: the failures met so far have all been bookkeeping in a marching scheme, not missing entropy, and adding shock physics on top of a march that stalls would not help. Note also that shock fitting still needs to know where a shock starts, so the detection problem above follows it there.

**Performance.** Pure Python, roughly a hundred seconds for eight thousand lines. Adequate for study, not for an interactive path. numba is neither installed nor declared.

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
python -m pytest                            # the suite, 155 tests
python experimental/convergeMarch.py        # grid convergence of the march
python featureShowcase/buildPlumeMarch.py   # the figures
python featureShowcase/verifyContour.py     # contour against its references
```

`featureShowcase/plumeCellTrain.png` is the validated case and the one to look at first. `plumeContinuousField.png` is currently near empty on the worked nozzle and says so; it is not a result.

## What the contour work may settle

Two of the open items sit downstream of the contour generator rather than inside the plume.

The nozzle delivers an area ratio of 69.84 against the 40 requested and 0.639 of the conical reference length against the 0.80 requested, because the pressure match drives the pressure at the wall to a one-dimensional target. Until the delivered geometry is the requested geometry, no plume result on that contour describes the nozzle anyone asked for.

`nozzleNearWallMachNumber` and the characteristic mesh disagree about the wall state, by twelve per cent at the exit and in the other direction upstream. The march reads the mesh; anything reading the near-wall array sees something else. Which of the two is right is not established.
