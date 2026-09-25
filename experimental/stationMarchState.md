# Station marching: state of play

A record of the plume solver that prescribes its data line, written to be picked up cold. It marches, it is verified against an exact solution, and it has passed the first of four staged references. This document is what works, what does not, and what remains before anything in the package reads it.

The goal it serves: extend the nozzle interior solution past the lip to give the jet boundary and the interior field, on a method that can be held against measurement.

## Why a second solver

`NOVA.plume.solvePlumeMarch` marches the characteristics themselves and the mesh goes where they take it. It is validated where it survives and it does not survive far. On a uniform parallel exit at Mach 3 it ends at 3.3 lip radii at a jet static pressure ratio of 1.2 on a failed boundary point, and reaches 8.6 at 1.5 carrying 38 per cent mass drift. Both are well inside the envelope where an isentropic net is defensible. A divergent exit, which is every bell contour, stops it after about one shock cell.

Diagnosing why produced a measurement rather than a suspicion. At the point the front-advancing variant stalls on a mildly underexpanded jet, the data line lies within **0.00 degrees** of the first-family characteristic direction over part of its length, the point spacing along it spans **114 to 1**, and the boundary has run to two lip radii while the center line has reached a tenth of one. A data line lying on a characteristic carries no information across itself, so the unit process returns points already on the line and the march ends.

That is what happens when the mesh is allowed to choose the data line.

## What this solver does instead

Stations are planes normal to the axis. The points on each sit at fixed fractions of the local jet radius, and the flow at those prescribed positions is solved by tracing each point's two characteristics back to the previous station and interpolating the state at their feet. The line can never rotate into a characteristic, and resolution is held as the plume opens out.

The compatibility relations and the velocity formulation are imported from `NOVA.plume` rather than transcribed, so the two solvers cannot drift apart on the physics. Only which quantities are known changes: the characteristic march knows the parents and solves for the position, this knows the position and solves for the parents.

Three things follow that the characteristic march does not give:

- the jet boundary is one point per station, so it is an output rather than a reconstruction from scattered nodes
- the interior is a structured grid, station by radial fraction, which contours directly
- a divergent exit stops being a special case, because a station is normal to the axis whatever angle the flow leaves the lip at

The cost is an interpolation at every station, which the characteristic march does not pay.

## Verification against an exact solution

`stationMarchVerification.py` holds the scheme against a spherical source flow, which is an exact solution of the steady isentropic axisymmetric equations. It is the one case where a unit process can be handed known data and its own error measured, rather than inferred from a conservation residual that says a solve is wrong without saying where.

| Process | Observed order |
|---|---|
| interior point, Mach number | 1.98 to 2.00 |
| interior point, flow angle | 1.94 to 1.99 |
| center-line point | 1.98 to 2.00 |
| interior point with its first-family foot reflected through the axis | 1.96 to 1.99 |
| accumulated mass drift over a marched length | 1.00 |

Second order per step over a step count rising as its inverse gives first order in the accumulated error, which is what the last row is. Both fixes recorded below were found with this, not guessed at.

It is a verification and not a validation: it establishes that the discretization solves the equations it claims to, and says nothing about whether those equations describe a real plume.

## Stage 1: uniform parallel exit

Mach 3, gamma 1.2, 81 points across the jet, marched 26 lip radii. The period is measured crest to crest, because lip to first crest is not the wavelength.

| Pe/Pa | crests [lip radii] | period | Prandtl | error | worst mass drift |
|---|---|---|---|---|---|
| 1.05 | 4.150, 11.559, 18.440 | 7.409 | 7.595 | -2.45% | -0.169% |
| 1.20 | 4.492, 12.501, 19.900 | 8.009 | 8.191 | -2.22% | -0.335% |
| 1.50 | 5.097, 14.109, 23.133 | 9.012 | 9.282 | -2.91% | +0.778% |
| 2.00 | 5.901, 16.421 | 10.520 | 10.888 | -3.38% | -0.973% |

Prandtl's length is `NOVA.plume.shockCellLength` on the fully expanded jet diameter and Mach number, which is the reference the characteristic march was held to. Its own docstring records that it runs long against experiment, so a measured period a few per cent under it is the expected sign.

**The characteristic march agrees where it survives.** At Pe/Pa 1.05 over 26 lip radii the two solvers put the first three crests at 4.182, 11.590, 18.473 and at 4.150, 11.559, 18.440, giving periods of 7.408 and 7.409. They differ by 0.01 per cent on the period and by three hundredths of a lip radius on crest position, having been run on different meshes with different unit processes. That is the strongest statement available here, because neither solver informs the other.

**Conservation grid converges at Pe/Pa 1.05 and stalls above it.**

| Points | 1.05 | 1.20 | 1.50 | 2.00 |
|---|---|---|---|---|
| 41 | -0.292% | -0.819% | -1.200% | -1.932% |
| 81 | -0.169% | -0.335% | +0.778% | -0.973% |
| 161 | -0.095% | +0.151% | +0.976% | +1.831% |

At 1.05 the drift falls by a factor near 1.75 per doubling, holding one sign, which is the first order the verification predicts. From 1.2 upward it crosses zero between 81 and 161 points and grows again.

**What stops it converging is a discontinuity forming in the solution.** The steepest radial Mach gradient on each station, taken in units of the local jet radius so the measure does not scale with the grid, sits at x 5.22 to 5.24 lip radii at Pe/Pa 1.5, which is the first boundary crest. Its magnitude at that one location runs 15.7, 44.3 and 102.4 at 41, 81 and 161 points: growth exponents of 1.52 and 1.22 against resolution, trending toward the 1/h of a gradient that has no converged value. At Pe/Pa 1.05 nothing downstream exceeds 1.7 and the largest gradient in the field moves to the lip, where a centered fan is genuinely singular and the station scheme smears it.

So the reflected compression is coalescing, and refining the grid resolves the coalescence more sharply rather than removing it. No isentropic net carries a discontinuity, so no step size or point count recovers conservation there. That is the same ceiling Prandtl's cell length and TR R-6 both put at a pressure ratio of about 2, arrived at a third way, from the solver's own gradients.

**Stage 1 passes at the weak end, and above it the scheme is not the limit.** Grid-converged conservation below a tenth of a per cent, a period within 2.5 per cent of Prandtl, and independent agreement with the characteristic march to 0.01 per cent all hold at Pe/Pa 1.05. At 1.2 to 2.0 the period holds to 3.4 per cent, conservation stalls near one per cent, and the cause is the formulation's assumption rather than its discretization.

## Stage 3: the divergent exit

The test TR R-6 makes falsifiable. Conclusion 1 reads that divergence angle over 0 to 20 degrees has a small effect on the primary wavelength, with a mild decrease attributed to rising shock losses. The characteristic march contradicts it by -24.6 per cent at 5 degrees and -34.3 at 11.

The exit is a conical source flow, which is an exact solution and is what a conical nozzle delivers, run at Pe/Pa 1.05 with the lip held at Mach 3 so only the divergence changes. 81 points, 26 lip radii, period crest to crest.

| Divergence | first crest | period | on parallel | worst mass drift |
|---|---|---|---|---|
| 0 deg | 4.150 | 7.409 | | -0.17% |
| 5 deg | 1.994 | 7.856 | +6.04% | -0.42% |
| 11 deg | 2.003 | 7.723 | +4.24% | +8.47% |
| 14 deg | 2.060 | 7.698 | +3.90% | +11.57% |
| 20 deg | 2.137 | 7.770 | +4.87% | march failed at 15.8 lip radii |

**The period is insensitive to divergence, which is what the experiment says.** The spread over 0 to 20 degrees is +0 to +6 per cent, against -25 to -34 for the characteristic march. The 5 degree point is the one that carries weight on its own, because conservation there is 0.42 per cent: it reads +6.04 per cent where the characteristic march reads -24.6. From 11 degrees up the period still reads within +5 per cent, but a period measured in a solution losing 8 to 12 per cent of its mass is indicative rather than established.

**Most of the characteristic march's disagreement is the measure, not the physics.** Between a parallel exit and 5 degrees the first crest moves from 4.150 to 1.994 lip radii, which is -52 per cent on lip to first crest while the period moves +6. A divergent exit throws the boundary out early without changing the axial period of the wave structure, and the period is what the report measures.

**Conservation degrades with divergence because the compression coalesces earlier.** The steepest radial Mach gradient, in units of the local jet radius, runs 3.19 to 9.61 at 5 degrees and 29.2 to 69.1 at 11 over 41 and 81 points, at a fixed location each time. Both are gradients with no converged value, and the 11 degree one is where conservation stops converging: 5.08 per cent at 41 points against 8.47 at 81. TR R-6 records that increasing divergence sharply reduces the range of pressure ratios over which no Riemann wave forms, which is the same statement. So the solver reaches its ceiling sooner at a divergent exit, for the reason the report gives.

**A constant flow angle across the exit is not an initial condition.** The uniform Mach, uniform angle line the characteristic march was driven with sets a nonzero flow angle at the center line, which symmetry forbids. The station marcher rejects it at the first station for every angle tested, because it enforces the axis condition. The characteristic march accepted it because it never applies that condition to its initial line, so part of its divergent-exit behavior comes from a line that is not a solution of the equations.

**Stage 3 passes at 5 degrees and is open above it.** The insensitivity is reproduced where conservation holds. Extending it needs either a coalescence treatment or an acceptance that the isentropic ceiling falls with divergence, which is what the reference implies.

## Two defects, found and closed

**The axisymmetric source term was ill-conditioned.** The relation carries `sin(theta) sin(mu) / sin(theta +/- mu) * dr / r`, and the increment in radius along the characteristic is `tan(theta +/- mu) dx`. Both vanish together as the second-family characteristic turns axis-parallel, which happens wherever the flow angle reaches the Mach angle, and the product they form is then set by which state each factor was evaluated at rather than by the flow. Measured at Mach 4 with 14.4 degrees of turning, the coefficient reached -1.6e4 and the solve diverged within four iterations. Cancelling the two analytically gives `sin(theta) sin(mu) / cos(theta +/- mu) * dx / r`, the same quantity with nothing small in the denominator, and the only singular direction left is a characteristic normal to the axis, which the second family cannot reach.

**The step limit was reasoning backwards.** Holding the step to half the radial spacing put every characteristic foot inside its own grid cell, so each solve read the interpolant's slope instead of the station's data. A monotone cubic carries only second order in its first derivative, so the error per step stopped falling while the number of steps kept rising, and refining the step made the answer worse: 1.13 per cent drift at half a spacing against 0.78 at one, and 7.20 against 0.97 at a ratio of 2. The step now places the steepest foot one spacing out.

Lifting it needed the axis treated. A near-axis point's first-family foot crosses the center line, which capped the step at a fraction of the spacing for those points alone. The jet is symmetric, so that foot is read by reflection: the state at a negative radius is the state at its magnitude with the flow angle reversed, and the first-family characteristic reaching the point from below is the mirror of a second-family one in the lower half. The verification confirms it at second order.

## The staged references

Stages 1 to 3 need no data that is not already in hand. Stage 4 needs manual transcription from a scanned report.

1. **Uniform parallel exit, Pe/Pa 1.05 to 2.** Mass conservation, and the cell period against Prandtl. **Passed at 1.05, open above it**: the period holds to 3.4 per cent throughout, conservation stops converging near one per cent from 1.2 upward.
2. **NASA TN D-2327's worked cases.** Lip fan and leading characteristic to the center line, which the characteristic march reproduces to a tenth of a per cent. **Not started.**
3. **A divergent exit.** TR R-6 conclusion 1 measures divergence angle over 0 to 20 degrees as a small effect on the primary wavelength. **Passed at 5 degrees, open above it**: the period spread over 0 to 20 degrees is +0 to +6 per cent against the characteristic march's -25 to -34, and conservation carries the 5 degree point at 0.42 per cent. Beyond 11 degrees conservation runs 8 to 12 per cent and the march fails at 20.
4. **TR R-6's interior field and boundary shape.** Table II tabulates a characteristic flow field per nozzle and figures 8a to 8g give boundaries. This is the only interior-field reference available and it has not been transcribed. **Not started.**

Above a jet static pressure ratio of about 2, no isentropic net is defensible, by Prandtl's cell length and by TR R-6 independently, because the compression waves reflected from the boundary have coalesced into a shock the net does not carry. That ceiling belongs to the physics and applies here unchanged. TR R-6 adds that divergence brings it on earlier, so stage 3 runs at the weak end.

## Promotion

Nothing in the package imports this module. It moves into `src/NOVA` when stages 1 to 3 pass, and not before. Stages 1 and 3 pass at the weak end of their ranges and stage 2 has not been run, so it stays here.

The envelope it would carry on promotion, drawn from what is measured: a jet static pressure ratio to about 1.2 and an exit divergence to about 5 degrees, inside which conservation grid converges below half a per cent and the period holds within 6 per cent of the references. That is already wider than `Nozzle.plumeField`, which refuses beyond half a degree of exit divergence.

## Reproducing

Run from the NOVA root with `C:\Users\seanb\miniconda3\python.exe`.

```
python experimental/stationMarchVerification.py   # the exact solution and the observed orders
python experimental/stationMarchFigures.py        # the boundary, the field, the divergence sweep
```

A march is `solveStationMarch(flow, uniformStation(flow, 3.0, 1.0, 81), ambient)`, with `ambient` the exit static pressure divided by the jet static pressure ratio. `conicalStation(flow, 3.0, radians(5.0), 1.0, 81)` replaces the exit plane with a conical nozzle's. The result carries the stations, the boundary and the per-station mass drift.
