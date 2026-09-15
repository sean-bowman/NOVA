# Internal shock treatment: state of play

A record of how NOVA handles the shock inside a thrust-optimized nozzle, written to be picked up cold. Detection and weak-shock capture ship. The rotational characteristics solve that would make the treatment exact does not, and this document is the scope of that work and the reasons it was left out.

## Why there is a shock at all

A truncated ideal contour cannot carry one. Its wall is a streamline of a shock-free field, so the characteristics leaving it never converge by construction.

Both optimized families can. A wall that turns the flow harder than an ideal contour generates compression, and compression waves in a diverging section can coalesce before they leave the nozzle. That is the price of the length the family buys, and the stagnation pressure lost across the resulting front is exactly what stops a real thrust-optimized contour from turning harder still.

That last sentence is the reason this work sits where it does in the solver rather than in the reporting. An isentropic march charges a wall nothing for turning, so an optimizer given one will run to whatever inflection bound it is handed and call the result an optimum. A thrust-optimized contour cannot be optimized honestly by a solver that ignores the shock.

## What ships

**Detection, from the wall characteristic envelope.** Every wall point launches a right-running characteristic at `theta - mu`. Past the inflection the wall angle falls, each characteristic leaves aimed further inboard than the one before it, and the family closes on itself. The earliest meeting that lands inside the nozzle and above the axis is the onset. This is the classical envelope construction, it is asked at the wall rather than in the mesh, and it needs nothing from the interior.

**Capture, as a weak shock.** The cumulative wall turning reaching a point on the front is the deflection that front has to absorb. The oblique shock relations give the stagnation pressure ratio across it, and that ratio is carried downstream as a per-streamline debit on the exit plane while the characteristics within each region stay isentropic. The solution reports the onset station, the peak deflection, the minimum stagnation ratio, whether the front is weak, and the thrust the shock cost.

**What the detector is measured on.** `featureShowcase/buildContourFamilies.py` turns one wall progressively harder than the chart parabola and records what comes back. At area ratio 40 and 80 per cent bell the chart parabola forms no shock inside the nozzle, and from there the onset moves upstream and the deflection grows monotonically with inflection angle. A sweep that found nothing on seven gentle walls would say nothing about the detector; that response curve is what makes the zeros meaningful.

## What the capture is worth, and where it stops being worth anything

The weak-shock treatment is defensible while the front is weak. Entropy rise across an oblique shock is third order in shock strength, so at a normal Mach number barely above one the error in holding each region isentropic is small against everything else in the solve.

It is not defensible once the front is strong, and the walls that produce a strong front are not exotic. Four degrees of extra inflection past the chart parabola gives a front turning the flow by 0.8 degrees with 99.999 per cent of the stagnation pressure surviving, which is weak by any measure. Fourteen degrees gives 29 degrees of turning and 56 per cent of the stagnation pressure surviving, which is not a weak shock and not a small correction to anything.

So the reported `isWeak` flag is not decoration. **A front that is not weak is reported rather than trusted**, and a design that depends on the number attached to it needs the solver below rather than this one.

## What a correct treatment would take

Entropy varying from streamline to streamline puts a Crocco term in the compatibility relations. That is not an addition to the shock treatment; it is a different solver, and the reach of the change is what keeps it out.

`characteristics.axisymmetricMethodOfCharacteristics` would have to change. It is shared with the plume march, and it is the one function in the codebase with a measured order of accuracy, verified against exact planar Riemann invariants at orders 1.88 through 1.99. Changing it puts that measurement back on the table for the plume as well as the nozzle.

The isentropic field fill would have to go. Temperature, pressure and velocity are currently recovered from the Mach number alone at fixed stagnation conditions, in the mesh fill and again in the near-wall derive after the wall is resampled. Neither is valid once stagnation pressure varies across streamlines, so both would need the local stagnation state carried with the point rather than assumed.

The exit-plane integral would have to carry it too. It already accepts a stagnation pressure field rather than a scalar, which is the seam the weak-shock capture uses, so this part is prepared.

And the front itself would have to be fitted rather than inferred, with the jump applied as an internal boundary the march respects, instead of a post-hoc debit on a solution that was marched through it.

## Findings worth not rediscovering

**Three mesh-position tests were built and all three were wrong in the same way.** Each compared the positions of mesh points on adjacent characteristic lines and called a crossing a shock. What that measures is where the march has drifted, which near the axis it always does, and the answers were backwards: the reported deflection fell as the wall turned harder, the onset moved downstream rather than upstream, and the two most over-turned walls in a sweep reported no shock at all. A forty-seven degree turn cannot compress less than an eighteen degree one. The question has to be asked about directions at the wall, not positions in the mesh.

**The convergence condition reads backwards until it is written down.** Along a bell wall the flow angle falls and the Mach angle falls with it, and `theta - mu` falls faster than either: on the worked parabola it runs from plus 1.8 degrees at the inflection to minus 6.9 at the exit. Convergence is therefore the LATER ray being steeper downward. Requiring the reverse, which reads as the natural condition, finds nothing on any wall. The first working version of the detector reported no shocks anywhere for exactly this reason.

**A shocked wall can report a higher raw thrust coefficient than a good one.** At fourteen degrees past the chart parabola the coefficient comes back above the parabola's while the exit plane closes only 72 per cent of the throat mass flow. The momentum term scales with the mass the plane samples, so a wall that spills its flow out of the sampled region is flattered by its own discretisation. This is the failure mode the optimizer's closure band exists to refuse, and it is the reason a raw coefficient is never comparable across walls without the closure printed beside it.

**The TN D-2327 same-family point is not a Rankine-Hugoniot jump.** It is a source of crossing geometry and a detection pattern, and it does not become a capture scheme by being called a shock point. The free-jet work in this directory already records that driving it did not close the gap it was aimed at.

## Reproducing

```
python featureShowcase/buildContourFamilies.py     # the response sweep is its INTERNAL SHOCK section
python -m pytest tests/testContourFamilies.py
```

The detector is `directCharacteristics.shockFromWallEnvelope`, the jump inversion is `shockFromDeflection`, and the downstream debit is `stagnationPressureField`. The solution fields are `internalShock`, `shockFront`, `thrustCoefWithoutShock` and `shockThrustDebit`.
