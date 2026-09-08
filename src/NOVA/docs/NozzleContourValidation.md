[Home](../../README.md) &gt; [Nozzle Contour Validation](./NozzleContourValidation.md)

# NOVA: Nozzle Contour Validation

What the contour generator is checked against, what those checks establish, and what they do not.

The companion documents are [NozzleContour.md](./NozzleContour.md), which derives the implementation, and [NozzleContourMethods.md](./NozzleContourMethods.md), which places it among the alternatives. Sources are recorded in [references_nozzleContour_2026-09-06.md](./references_nozzleContour_2026-09-06.md).

## Contents

- [What can and cannot be checked](#what-can-and-cannot-be-checked)
- [Does it deliver what it was asked for](#does-it-deliver-what-it-was-asked-for)
- [Wall angles against the Rao chart](#wall-angles-against-the-rao-chart)
- [The RS-25](#the-rs-25)
- [Grid convergence](#grid-convergence)
- [The exit pressure matching condition](#the-exit-pressure-matching-condition)
- [Which pressure a pressure match should converge on](#which-pressure-a-pressure-match-should-converge-on)
- [One-dimensional dependencies](#one-dimensional-dependencies)
- [Defects found](#defects-found)
- [Validation status](#validation-status)
- [Reproducing](#reproducing)

---

## What can and cannot be checked

A contour generator can be wrong in three separate ways, and they need three separate checks.

It can fail to deliver the design point it was asked for. That is checkable exactly, against arithmetic, and needs no reference at all.

It can produce a contour of the wrong shape. That needs an external reference, and the only one available is Rao's wall-angle chart. It is for a thrust-optimised parabola rather than a truncated ideal contour, so the two are different families and a difference is expected; what the comparison establishes is the size and the sign of that difference against a known expectation.

It can solve the flow wrongly on a contour of the right shape. This is the hardest to check, because no source publishes a tabulated axisymmetric flowfield for a rocket bell. What is available instead is internal: the exit plane must pass the same mass the throat does, the wall state must satisfy the isentropic relation it was built from, and the answer must stop moving as the mesh is refined.

Flight engines settle less than they appear to. Public data gives chamber pressure, mixture ratio, area ratio and performance; it does not give wall coordinates. Feeding an engine's area ratio and length fraction into the tool and recovering its area ratio and length is circular. The RS-25 comparison below is included for the one quantity in it that is not: the throat diameter, which follows from thrust and chamber conditions and nothing else.

## Does it deliver what it was asked for

Yes, to the arithmetic.

The wall is cut where it reaches the requested area ratio, and the exit Mach number of the underlying ideal nozzle is solved so that the length which falls out is the requested fraction of the 15 degree conical reference. Both requested numbers are outcomes of the same solve rather than one being traded against the other.

| Requested area ratio | Requested bell | Delivered area ratio | Error | Delivered bell | Error |
|---|---|---|---|---|---|
| 10 | 0.80 | 10.0000 | 0.0000 % | 0.8000 | 0.0000 % |
| 20 | 0.80 | 20.0000 | 0.0000 % | 0.8000 | 0.0000 % |
| 40 | 0.80 | 40.0000 | 0.0000 % | 0.8000 | 0.0000 % |
| 70 | 0.80 | 70.0000 | 0.0000 % | 0.8000 | 0.0000 % |
| 40 | 0.60 | 40.0000 | 0.0000 % | 0.6000 | 0.0000 % |
| 40 | 0.70 | 40.0000 | 0.0000 % | 0.7000 | 0.0000 % |
| 40 | 0.90 | 40.0000 | 0.0000 % | 0.9000 | 0.0000 % |

This was not previously the case, and the size of the miss is worth recording. On the worked LOX/LH2 case the tool was asked for an area ratio of 40 and delivered 69.84, and was asked for 80 per cent of the conical length and delivered 63.9 per cent of it. The reasons were three, and they compounded.

The requested area ratio was never used as a geometric constraint. It was converted to a CEA exit pressure and the wall was cut on length instead.

The conical reference the length fraction was measured against was taken from a one-dimensional Mach number rather than from the area ratio. That Mach number corresponds to an area ratio of 48.5, so the reference cone was 12.0 per cent longer than the one NASA SP-8120 defines.

The exit Mach number was solved so that the wall static pressure equalled a target taken from CEA at the requested area ratio. The wall is a defensible station to measure at, as the section below establishes; the target was not. It was a property of the design point rather than of the atmosphere the engine runs in, and it was computed with equilibrium chemistry while the mesh is a perfect gas, so the two differ by 20.9 per cent before any contour exists. Driving the wall to it pushed the area ratio well past the request.

## Wall angles against the Rao chart

The comparison that checks the contour itself. Both angles are measured off the generated wall and compared against the chart for a thrust-optimised parabola at the same area ratio and length.

| Area ratio | Bell | NOVA inflection | Rao chart | Difference | NOVA exit | Rao chart | Difference |
|---|---|---|---|---|---|---|---|
| 10 | 0.80 | 24.36 | 26.30 | -1.94 | 11.15 | 11.00 | +0.15 |
| 20 | 0.80 | 27.45 | 28.80 | -1.35 | 9.67 | 9.00 | +0.67 |
| 40 | 0.80 | 30.38 | 31.00 | -0.62 | 8.77 | 8.00 | +0.77 |
| 70 | 0.80 | 32.59 | 32.47 | +0.12 | 8.52 | 7.26 | +1.26 |
| 40 | 0.60 | 32.78 | 37.10 | -4.32 | 15.54 | 13.50 | +2.04 |
| 40 | 0.70 | 31.33 | 34.05 | -2.73 | 11.76 | 10.75 | +1.01 |
| 40 | 0.90 | 29.75 | 29.50 | +0.25 | 6.60 | 6.00 | +0.60 |

All angles in degrees. The area ratio 70 row is read from the region SP-8120 marks as extrapolated, so the chart there is not a measurement.

The pattern is consistent and is the one the difference in families predicts. NOVA turns the wall LESS hard at the inflection and leaves it STEEPER at the exit than a thrust-optimised parabola of the same design point. That is what a truncated ideal contour does: it inherits the gentle opening of the ideal nozzle it was cut from, and it is cut before the straightening section has finished its work. A thrust-optimised contour opens harder early precisely so it can straighten more by the exit, which is where its fraction of a per cent of extra thrust comes from.

The disagreement grows as the bell shortens, from a quarter of a degree at 90 per cent to more than four degrees at 60 per cent. That is also expected: SP-8120 records that the optimum method fails below a minimum length and recommends the truncated ideal contour in exactly that regime, which is another way of saying the two families separate there.

Over the range where the chart is a measurement rather than an extrapolation, and at the conventional 80 per cent bell, the two agree to within 2 degrees on the inflection angle and 0.8 degrees on the exit angle.

**This is a comparison, not a validation.** The reference is a different contour family, and the chart itself is a digitisation of a figure. Neither the sign nor the size of the difference is evidence that either contour is wrong.

## The RS-25

Run at the RS-25D published operating point: LOX/LH2 at a mixture ratio of 6.03, a chamber pressure of 20.64 MPa, a vacuum thrust of 2279 kN, an area ratio of 69.5 and a length fraction of 0.806.

| Quantity | NOVA | Published | Difference |
|---|---|---|---|
| Throat diameter | 273.0 mm | 261.6 mm (10.3 in) | +4.4 % |
| Exit diameter | 2275.7 mm | 2303.8 mm (90.7 in) | -1.2 % |
| Nozzle length | 3012.1 mm | 3073.4 mm (121 in) | -2.0 % |
| Area ratio | 69.500 | about 69.5 | delivered exactly |
| Length fraction | 0.8060 | about 0.806 | delivered exactly |
| Exit wall angle | 8.48 deg | not published | -- |
| Inflection wall angle | 32.53 deg | not published | -- |

Read this carefully. The area ratio and the length fraction were inputs, so their agreement is arithmetic rather than evidence. The exit diameter and the nozzle length follow from the throat diameter and those two inputs, so they carry no independent information either.

**One number here is a prediction: the throat diameter.** It comes from the requested thrust and the chamber conditions through the choked mass flow, and nothing about the nozzle geometry enters it.

The published dimensions are not self-consistent, so it has two things to be compared against. A throat diameter of 10.3 in with an exit diameter of 90.7 in gives a geometric area ratio of 77.6 against the published 69.5. Taking the exit diameter and the area ratio as the consistent pair puts the throat at 276.3 mm; the separately quoted 261.6 mm is 5.3 per cent away from that. At least one of the three published numbers is not the quantity it appears to be.

| NOVA throat diameter | Against | Difference |
|---|---|---|
| 273.0 mm | 276.3 mm, implied by the published exit diameter and area ratio | -1.2 % |
| 273.0 mm | 261.6 mm, the separately quoted throat diameter | +4.4 % |

Against the self-consistent pair the throat sizing lands within 1.2 per cent, on an engine whose only inputs here were its propellants, mixture ratio, chamber pressure, thrust and area ratio.

The throat sizing itself has a cleaner check that does not depend on any published dimension. The choked-flow relation NOVA uses is a perfect-gas expression at the throat ratio of specific heats; CEA computes the characteristic velocity from equilibrium thermochemistry. At this operating point they give **2320.2 m/s and 2320.7 m/s**, agreeing to **0.02 per cent**. The throat sizing path is therefore not where any remaining disagreement lives.

For scale on the rest: CEA gives a vacuum specific impulse of 462.9 s at this operating point against the RS-25's published 452.3 s, so the engine delivers 97.7 per cent of the theoretical value. That is a normal figure for combustion efficiency, a boundary layer and kinetic losses together, and none of the three is modelled here.

The one other thing this case establishes independently is the length convention. The 15 degree cone to the RS-25's published exit radius is 3.81 m against its quoted nozzle length of 3.07 m, which is 80.6 per cent, and the engine is described as an 80 per cent bell. The definition of percent bell used here is the one the engine is quoted against.

## Grid convergence

Fifty characteristics are launched from the throat arc by default. Sweeping that resolution at area ratio 40 and 80 per cent bell, against the finest mesh:

| Characteristics | Area ratio | Length fraction | Exit wall angle | Error | Thrust coefficient | Error |
|---|---|---|---|---|---|---|
| 25 | 40.0000 | 0.8000 | 8.571 | -4.26 % | 1.78908 | -0.81 % |
| 35 | 40.0000 | 0.8000 | 8.947 | -0.07 % | 1.79562 | -0.44 % |
| 50 | 40.0000 | 0.8000 | 8.773 | -2.02 % | 1.79494 | -0.48 % |
| 70 | 40.0000 | 0.8000 | 8.956 | +0.03 % | 1.80170 | -0.11 % |
| 100 | 40.0000 | 0.8000 | 8.953 | 0 | 1.80363 | 0 |

The area ratio and the length fraction are converged trivially, because they are constraints the solve satisfies rather than results it produces.

**Neither the thrust coefficient nor the exit wall angle is converged at the default mesh, and neither approaches its limit monotonically.** The thrust coefficient carries about 0.5 per cent of mesh error there and the exit wall angle about 2 per cent, which is 0.18 degrees. In both the error at 50 characteristics is larger than at 35.

An earlier version of this section reported the thrust coefficient as converged to 0.013 per cent. That was an artefact of how it was computed. The exit-plane integral used a smooth one-dimensional coefficient evaluated at the local pressure, which varied little as the mesh changed; replacing it with the actual momentum flux, which is what the momentum theorem requires, exposed a mesh sensitivity that had been there all along and was being smoothed over. The correction is described under the defects below.

Non-monotone convergence of this kind is the signature of an answer that moves discretely as mesh lines land on either side of the truncation point rather than one converging smoothly.

Nought point two degrees is small against the 0.6 to 4 degree differences the Rao comparison reports, so the conclusions there survive. It is not small against the precision the numbers are printed to, and an exit wall angle should be quoted to no better than a tenth of a degree at this mesh. Every wall angle quoted in the Rao comparison above inherits that error.

The thrust coefficient behaves correctly against length, which is a physical check rather than a numerical one. At an area ratio of 40 it rises monotonically with the bell, from 1.7673 at 60 per cent to 1.7885 at 70, 1.7949 at 80 and 1.7998 at 90. The gain from 80 to 90 per cent is 0.27 per cent, against a gain of 1.56 per cent from 60 to 80. Published practice puts an 85 per cent bell at about 99 per cent nozzle efficiency with only a further 0.2 per cent available by going to full length, and the diminishing return here is of that size. It is the reason 80 per cent is the conventional choice, and the solver reproduces it without being told.

## The exit pressure matching condition

The assumption under test: that the static pressure at the end of the contour can be used to enforce an exit pressure matching condition.

It cannot, for three independent reasons, and the exit plane of the worked case shows all three at once. At an area ratio of 40 and 80 per cent bell:

| Where on the exit plane | Static pressure |
|---|---|
| At the wall | 25.2 kPa |
| Mass averaged | 18.3 kPa |
| Area averaged | 17.4 kPa |
| One-dimensional at that area ratio | 17.7 kPa |
| On the axis | 8.4 kPa |

**The wall is the right station, and an earlier version of this section said otherwise.** That version argued the wall is the extreme of the plane rather than its average, and that a residual built on it therefore drives the wrong quantity. That is wrong for the purpose the residual serves.

Extending a nozzle by a ring of wall adds an axial force of $(P_{wall} - P_{ambient})$ times that ring's projected area. The thrust along the wall is therefore

$$F(R) = \int_{R_t}^{R} \left(P_{wall}(r) - P_{ambient}\right) 2\pi r\, \mathrm{d}r$$

and its maximum sits exactly where the integrand changes sign, which is where the wall static pressure reaches ambient. That is the classical optimum-expansion result in the form that survives a non-uniform exit. The plane average describes the flow leaving the nozzle; the wall pressure describes the surface the force acts on, and only the second decides whether more nozzle is worth having.

Measured on the worked case at an ambient of 101.3 kPa, the thrust integral peaks at an area ratio of 13.18, where the wall pressure is 99.3 kPa, within 2 per cent of ambient. Cutting instead where the mass-averaged exit pressure reaches ambient stops at an area ratio of 10.03 and gives up 2.0 per cent of the available thrust gain, because on this contour the mass average is 0.729 of the wall value.

What remains true is that the plane is strongly non-uniform, spanning a factor of 3.0 in static pressure from wall to axis. That matters for describing the exit state and for the state handed to the plume march. It does not make the wall the wrong place to apply a thrust criterion.

**The target is a different quantity from the residual.** The target exit pressure comes from CEA at the requested area ratio, computed with equilibrium chemistry and a varying ratio of specific heats. The mesh is a perfect gas at the chamber ratio of specific heats throughout. At an area ratio of 40 the two disagree before any contour is drawn: CEA gives an exit Mach number of 4.2234 and an exit pressure of 13993 Pa, against 3.9537 and 17699 Pa from the perfect-gas relation at the chamber gamma. That is 6.8 per cent in Mach number and 20.9 per cent in pressure. Driving a perfect-gas wall pressure to an equilibrium one-dimensional target is not a matching condition; it is a comparison between two different models evaluated at two different places.

**There is no free parameter left to satisfy all three at once.** A truncated ideal contour has one free parameter, the design exit Mach number of the ideal nozzle it is cut from. Fixing an area ratio and a length uses it up and the exit pressure is a result; fixing a pressure and a length uses it up equally well and the area ratio is the result. What cannot be done is asking for all three.

`truncateOn` selects which. `areaRatio` cuts at the requested expansion ratio. `wallPressure` cuts where the wall reaches the target pressure, which is the maximum-thrust nozzle for that ambient and is what a pressure-matched design means. Both then solve the design Mach number for the requested length fraction, so both deliver two of the three exactly. `length` is the legacy path: it cuts at the requested length and drives the wall pressure to a target derived from CEA rather than from the ambient, and delivers neither the area ratio nor a meaningful pressure match.

The area-averaged exit pressure of 17.4 kPa against the perfect-gas one-dimensional value of 17.7 kPa at the same area ratio, a 1.8 per cent difference, is a useful internal check in its own right: the characteristics solution, averaged over its exit plane, agrees with the one-dimensional answer for the same area, as conservation requires.

## Which pressure a pressure match should converge on

Measured rather than argued. One ideal contour at a fixed design Mach number, truncated across a range of area ratios at an ambient of 101.325 kPa, with the thrust coefficient computed at each cut.

| Convergence target | Delivered area ratio | Thrust coefficient | Against the peak |
|---|---|---|---|
| Wall static pressure | 12.40 | 1.46342 | -0.026 % |
| Mass-averaged exit pressure | 10.40 | 1.46062 | -0.217 % |
| Area-averaged exit pressure | 10.40 | 1.46062 | -0.217 % |
| *the true maximum* | *12.80* | *1.46380* | -- |

**The wall wins, and by an order of magnitude.** Converging on it lands within 0.03 per cent of the maximum thrust coefficient; converging on either average under-expands by more than two in area ratio and gives up 0.22 per cent.

That is what the surface integral predicts. Extending a nozzle adds a ring of wall whose axial force is $(P_{wall} - P_{ambient})$ times its projected area, so the sign of the gain is set by the wall pressure alone. Because the flow is supersonic, adding wall at the exit cannot change anything upstream of it, and the relation is exact rather than approximate.

Two independent formulations of thrust agree on the location. The wall surface integral gives its maximum at $P_{wall} = P_{ambient}$ analytically. The exit-plane control-volume integral, computed over the same sweep, peaks at an area ratio of 12.60 where $P_{wall}/P_{ambient} = 0.9988$.

Two qualifications belong with the result. It is the **unconstrained** optimum, assuming no penalty for length or mass; a length-constrained design truncates earlier, which is the problem Rao's optimisation solves. And it is the condition for **where to cut one ideal contour**, not the optimality condition across a family of different design Mach numbers at a fixed length.

This is what `truncateOn = 'wallPressure'` implements, with the target set to the operating ambient rather than to a CEA exit pressure.

## One-dimensional dependencies

Where a one-dimensional relation stands in for the solved field, and what it costs.

| Where | What it sets | Cost | Status |
|---|---|---|---|
| Reference cone length | The length the bell fraction is measured against | Was 12.0 per cent long, because it came from a one-dimensional Mach number rather than the area ratio | Corrected |
| Conical diverging section | The entire wall of a conical nozzle | Delivered area ratio 48.5 against a requested 40 | Corrected |
| Exit line of the flow-straightening kernel | Where the ideal mesh terminates | None. An ideal nozzle exit IS uniform and axial by definition, so its radius follows from continuity exactly | By construction |
| Converging section wall state | Mach, pressure, temperature and velocity from the chamber to the throat | Not quantified. There is no solved subsonic field to compare against, and building one is a different problem from this one | Open, disclosed |
| Transport properties for cooling | Every gas-side property the regenerative model uses | Taken from CEA at each area ratio, so the cooling model never sees the characteristics field. Near-wall Mach differs from the one-dimensional value by up to 42 per cent just past the throat and settles about 5 per cent below it through the rest of the nozzle | Open, quantified |
| Ratio of specific heats | The entire mesh | The mesh is a perfect gas at the chamber value throughout. Against CEA at an area ratio of 40 that is 6.8 per cent in exit Mach number and 20.9 per cent in exit pressure | Open, quantified |
| Throat area correction | Every dimension the tool produces | An unsourced factor reducing throat area by 0.070 per cent. Documented in `contour.throatScalingFactor` as unsourced | Open, disclosed |
| Thrust coefficient back pressure | The pressure term of the thrust coefficient | Uses the design exit pressure as the ambient, so the reported thrust coefficient is a design-point value and not the value at the operating altitude | Open, disclosed |

The largest of these by far is the ratio of specific heats. A perfect-gas mesh at the chamber value is the aerodynamic core of the standard method with the chemistry removed, and the standard method uses equilibrium properties. For scale, the JANNAF standard code predicts delivered vacuum specific impulse to within 0.12 to 1.9 per cent of experiment with kinetics, a boundary layer and its displacement thickness all included; none of those are here.

## Defects found

Five, all found by comparison rather than by inspection, and all corrected.

**The near-wall Mach number was destroyed by a smoothing spline.** The near-wall arrays are resampled onto an evenly spaced contour with `UnivariateSpline`, whose default smoothing factor is an absolute residual budget of one per data point. Whether it interpolates or fits therefore depends on the magnitude of the values rather than on their shape. Pressure in pascals came through untouched; Mach number, being of order one, was replaced by a single straight line through the whole wall. It read 4.81 at the exit against a true 4.07, and 1.90 at the throat, while the pressure beside it stayed correct, so the two arrays disagreed by a factor of 4.7 on the isentropic relation they were both built from. The regenerative cooling model reads the Mach array for the recovery temperature, which moved by up to 600 K when this was fixed. The geometry and the thrust coefficient were unaffected. Locked by `tests/testContour.py`.

**The exit plane was integrated over only 92 per cent of its area.** The walk that samples the exit plane descends through the mesh from the wall and runs out of columns at about 29 per cent of the exit radius, leaving the core unsampled. Because the thrust integral weights by area over the full exit area, the unsampled core subtracted directly from the thrust coefficient rather than appearing as a gap. The plane is now closed on the axis, where the flow angle is zero by symmetry and the Mach number is extrapolated from the two innermost sampled points, and `exitPlaneSampledFraction` records how much of the plane the mesh actually supplied.

**The pressure term of the thrust coefficient was halved.** It normalised by `pi * rt * 2` rather than `pi * rt^2`. With the non-dimensional throat radius at one this divided by twice the correct value.

**The requested area ratio was never a constraint.** Covered above.

**The reference cone was measured against the wrong area ratio.** Covered above.

Two further discrepancies are recorded rather than fixed, because fixing either would move numbers for reasons unrelated to the physics.

The nozzle and the plume carry the limiting velocity in two algebraically identical but numerically different groupings, differing by about one unit in the last place. It is recorded in `tests/testCharacteristics.py`.

The design Mach number was solved to a tolerance loose enough that a one-ulp change in a Prandtl-Meyer evaluation moved the delivered area ratio in the fourth decimal. The tolerance is now 1e-8 and the Prandtl-Meyer function has one grouping across the whole codebase.

## Validation status

Stated plainly, because the three categories are not the same thing.

**Checked against an independent reference.** The unit process is second order, verified against the exact planar Riemann invariants: halving the state jump quarters the departure, with measured orders of 1.88, 1.94, 1.97, 1.99 and 1.99. The gas relations reproduce published compressible flow tables. The throat sizing agrees with CEA's equilibrium characteristic velocity to 0.02 per cent, and gives an RS-25 throat diameter within 1.2 per cent of the value implied by that engine's published exit diameter and area ratio. The percent bell convention reproduces the RS-25's published 80 per cent. The Rao wall-angle comparison is against a published chart, with the caveat that it is a different contour family.

**Checked internally, with no external reference.** The exit plane passes 97.4 per cent of the choked throat mass flow, the remaining 2.6 per cent being discretisation in the mesh and in the integration. The near-wall pressure, temperature, velocity and Mach number satisfy the isentropic relations they were built from exactly, everywhere along the wall, because only the Mach number is interpolated onto the resampled contour and the other three are derived from it. The area-averaged exit pressure agrees with the one-dimensional value at the same area ratio to 1.8 per cent.

The thrust coefficient agrees with an independent momentum integral over the same exit plane to 0.03 per cent, which checks the formulation. It sits 3.7 per cent below the closed-form one-dimensional ideal, and most of that is the exit plane's own resolution rather than physics: the plane carries 2.6 per cent less mass than the throat, and the momentum term scales with it. The divergence loss at the delivered exit wall angle accounts for a further 0.6 per cent. An earlier version reported 0.28 per cent against the ideal, which looked better only because a single-cosine error in the momentum term was cancelling the mass deficit.

**Not validated.** The flowfield itself, point by point: no source in the reference set publishes a tabulated axisymmetric solution for a rocket bell that could serve as a reference. The transonic starting line: Sauer's solution is the first term of a series whose next term is 29 per cent as large at this throat curvature, and SP-8120's recommended practice at this curvature is a 29-term series. The gas model: nothing here establishes what a perfect-gas mesh at a single ratio of specific heats costs against an equilibrium one. The converging section: quasi one-dimensional with nothing to check it against. And absolute performance: NOVA has no boundary layer and no kinetics, so its thrust coefficient is an inviscid perfect-gas result and cannot be compared with a delivered engine specific impulse without accounting for both.

Closing the transonic gap means implementing the Kliegel and Levine series. Closing the gas-model gap means either an equilibrium mesh or a quantified study of what the perfect-gas assumption costs. Closing the flowfield gap means finding or generating a reference solution, which no source in this set supplies.

## Reproducing

Run from the NOVA root with `C:\Users\seanb\miniconda3\python.exe`:

```
python -m pytest                                   # the suite
python featureShowcase/runBaseCase.py              # the worked LOX/LH2 case
python featureShowcase/verifyContour.py            # the single-case check
python featureShowcase/buildContourValidation.py   # the sweeps, about fifteen minutes
python featureShowcase/buildChamberField.py        # the chamber and converging section fields
```

`featureShowcase/contourValidation.png` carries the sweeps and `featureShowcase/contourVerification.png` the single case. Every number quoted above is printed by one of those scripts rather than stored.

## Author's Information

Sean Bowman - Last Updated [09/06/2026]
