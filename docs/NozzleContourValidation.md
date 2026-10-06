
[Home](../../README.md) &gt; [Nozzle Contour Validation](./NozzleContourValidation.md)

# NOVA: Nozzle Contour Validation

What the contour generator is checked against, what those checks establish, and what they do not.

Three contoured families are generated: a truncated ideal contour, a thrust-optimized parabola and a thrust-optimized contour. The checks below are organized by what is being checked rather than by family, so each section carries its families alongside one another. Where a family has no entry in a section, that check does not apply to it and the section says why.

The companion documents are [NozzleContour.md](./NozzleContour.md), which derives the implementation, and [NozzleContourMethods.md](./NozzleContourMethods.md), which places it among the alternatives. Sources are recorded in [references_nozzleContour_2026-09-06.md](./references_nozzleContour_2026-09-06.md) and [references_thrustOptimizedContours_2026-09-13.md](./references_thrustOptimizedContours_2026-09-13.md).

## Contents

- [What can and cannot be checked](#what-can-and-cannot-be-checked)
- [Does it deliver what it was asked for](#does-it-deliver-what-it-was-asked-for)
- [Wall angles against the Rao chart](#wall-angles-against-the-rao-chart)
- [Comparing the families against one another](#comparing-the-families-against-one-another)
- [Beating the family, or beating the chart](#beating-the-family-or-beating-the-chart)
- [The internal shock](#the-internal-shock)
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

It can produce a contour of the wrong shape. That needs an external reference, and the only one available is Rao's wall-angle chart. What the chart establishes differs by family, and conflating the three would make a weak check look like a strong one.

For the **thrust-optimized parabola** the chart is the construction rather than a reference, so agreement measures the resample and the wall-angle measurement, not the physics. Disagreement there would mean the generated wall is not the wall that was drawn.

For the **searched contour** the chart is an approximation to the same family being searched, which makes it the one external check on a contour shape in this document.

For the **truncated ideal contour** the families genuinely differ, so a difference is expected; what the comparison establishes is the size and the sign of that difference against a known expectation.

In all three the chart is a digitization of a figure, it carries a recorded transcription error, and it is extrapolated above area ratio 50.

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

This was not previously the case, and the size of the miss is worth recording. On the worked LOX/LH2 case the tool was asked for an area ratio of 40 and delivered 69.84, and was asked for 80 percent of the conical length and delivered 63.9 percent of it. The reasons were three, and they compounded.

The requested area ratio was never used as a geometric constraint. It was converted to a CEA exit pressure and the wall was cut on length instead.

The conical reference the length fraction was measured against was taken from a one-dimensional Mach number rather than from the area ratio. That Mach number corresponds to an area ratio of 48.5, so the reference cone was 12.0 percent longer than the one NASA SP-8120 defines.

The exit Mach number was solved so that the wall static pressure equalled a target taken from CEA at the requested area ratio. The wall is a defensible station to measure at, as the section below establishes; the target was not. It was a property of the design point rather than of the atmosphere the engine runs in, and it was computed with equilibrium chemistry while the mesh is a perfect gas, so the two differ by 20.9 percent before any contour exists. Driving the wall to it pushed the area ratio well past the request.

## Wall angles against the Rao chart

The comparison that checks the contour itself. Both angles are measured off the generated wall and compared against the chart for a thrust-optimized parabola at the same area ratio and length.

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

The pattern is consistent and is the one the difference in families predicts. NOVA turns the wall LESS hard at the inflection and leaves it STEEPER at the exit than a thrust-optimized parabola of the same design point. That is what a truncated ideal contour does: it inherits the gentle opening of the ideal nozzle it was cut from, and it is cut before the straightening section has finished its work. A thrust-optimized contour opens harder early precisely so it can straighten more by the exit, which is where its fraction of a percent of extra thrust comes from.

The disagreement grows as the bell shortens, from a quarter of a degree at 90 percent to more than four degrees at 60 percent. That is also expected: SP-8120 records that the optimum method fails below a minimum length and recommends the truncated ideal contour in exactly that regime, which is another way of saying the two families separate there.

Over the range where the chart is a measurement rather than an extrapolation, and at the conventional 80 percent bell, the two agree to within 2 degrees on the inflection angle and 0.8 degrees on the exit angle.

**For the truncated ideal contour this is a comparison, not a validation.** The reference is a different contour family, and the chart itself is a digitization of a figure. Neither the sign nor the size of the difference is evidence that either contour is wrong.

### The parabola against the chart it is drawn from

For the thrust-optimized parabola the chart is the input rather than the reference, so this is a closure test on the pipeline: the angles are read from the chart, used to draw a wall, the wall is marched, resampled and then measured, and the measurement has to return what was read.

| Area ratio | Bell | Measured inflection | Chart | Difference | Measured exit | Chart | Difference |
|---|---|---|---|---|---|---|---|
| 10 | 0.80 | 26.07 | 26.30 | -0.23 | 11.06 | 11.00 | +0.06 |
| 20 | 0.80 | 28.52 | 28.80 | -0.28 | 9.19 | 9.00 | +0.19 |
| 40 | 0.80 | 30.48 | 31.00 | -0.52 | 8.15 | 8.00 | +0.15 |
| 70 | 0.80 | 32.11 | 32.47 | -0.37 | 7.34 | 7.26 | +0.08 |
| 40 | 0.60 | 36.74 | 37.10 | -0.36 | 13.56 | 13.50 | +0.06 |
| 40 | 0.70 | 33.55 | 34.05 | -0.50 | 10.81 | 10.75 | +0.06 |
| 40 | 0.90 | 29.19 | 29.50 | -0.31 | 6.09 | 6.00 | +0.09 |

**The wall comes back within 0.52 degrees at the inflection and 0.19 degrees at the exit, at every design point.** That is the error budget of the whole drawing-to-measurement path, and it bounds how finely any wall angle in this document can be quoted. It is an order of magnitude tighter than the truncated ideal contour's differences above, which is the evidence that those differences are the families separating rather than the measurement drifting.

The inflection is consistently low by a quarter to a half degree, and the sign is the same at every point. That is the resample: the throat arc joins the curve where the wall turns hardest, and an evenly spaced contour through that join reads the corner slightly rounded. It is a known and bounded error rather than an open one.

## Comparing the families against one another

The ordering the literature predicts is the thrust-optimized contour first, the parabola a fraction of a percent behind it, and the truncated ideal contour about a quarter of a percent behind the optimum. The measurement below returns that ordering for the parabola and does not return it for the searched contour, and the second half of that sentence is the result rather than a caveat.

**Every coefficient here is normalized by its own exit-plane mass closure, and that is a correction rather than a convenience.** The plane samples less mass than the throat passes, the momentum term scales with what it samples, and the families do not sample equally. The first run of this comparison, on raw coefficients, put the parabola 0.945 percent BELOW the truncated ideal contour, which is the wrong sign. A mesh sweep settled which it was: over a threefold change in mesh the parabola's raw coefficient moves 0.89 percent while the ratio moves 0.066, so thirteen fourteenths of the apparent difference was discretization. The closure is printed beside every coefficient the study reports for the same reason.

Against the truncated ideal contour at 50 characteristics, as a percentage of its normalized coefficient:

| Area ratio | Bell | Truncated ideal | Rao parabola | Searched contour |
|---|---|---|---|---|
| 10 | 0.80 | 0.000 % | +0.048 % | +0.001 % |
| 20 | 0.80 | 0.000 % | +0.171 % | +0.100 % |
| 40 | 0.80 | 0.000 % | +0.229 % | +0.229 % |
| 70 | 0.80 | 0.000 % | +0.477 % | +0.605 % |
| 40 | 0.60 | 0.000 % | +0.130 % | -0.256 % |
| 40 | 0.70 | 0.000 % | +0.213 % | +0.066 % |
| 40 | 0.90 | 0.000 % | +0.828 % | +0.828 % |

**The parabola beats the truncated ideal contour at every design point**, by 0.05 to 0.83 percent, and at the worked point by 0.229 percent. That lands on SP-8120's statement that a truncated ideal contour costs of the order of a quarter of a percent against the optimum a parabola approximates, and it is the one cross-family result here with an external expectation behind it.

**The searched contour does not beat the parabola.** Measured against the parabola rather than against the truncated ideal contour, it trails at four of the seven design points, ties at two where the search correctly returned its own incumbent, and leads at exactly one, by 0.127 percent at area ratio 70.

Two things have to be said about that before it is read as a verdict on the family.

The searches were run at 60 evaluations and one restart against the driver's defaults of 160 and six, so that seven design points fit in one sweep. Two of the seven converged. A row that did not converge is a statement about the search budget and not about the contour, and the study says so per row.

And a small or negative result is what the source for this method reports. Allman and Hoffman optimized a second-degree wall against Rao contours at thirteen matched lengths and landed 0.05 to 0.21 percent BELOW Rao at zero ambient pressure, in every row and above it in none, because a parametrized family cannot beat an unconstrained variational optimum. They also put their own characteristics algorithm's precision at 0.2 percent, which is larger than most of the differences in the table above. **A large gain here would be the surprising result, not the expected one.**

### Beating the family, or beating the chart

The comparison above cannot say whether the searched wall beats the Rao *family* or merely NOVA's *reading* of the Rao chart, and those are different questions because the chart carries a recorded transcription error and is extrapolated above area ratio 50. Searching the quadratic subfamily separates them. The cubic parametrization contains the quadratic one exactly, so the same optimizer can be confined to the surface on which every wall is a genuine parabola: the two wall angles become the design variables and the tensions are derived from them.

Three walls at each design point, every search at the driver's full settings rather than the throttled ones the sweep above uses:

| | Area ratio 40, 0.80 bell | Area ratio 70, 0.80 bell |
|---|---|---|
| Chart parabola | 1.84785 at 96.22 % closure | 1.91882 at 92.61 % closure |
| Optimized quadratic | 1.84785 at 96.22 % | 1.92122 at 95.68 % |
| Optimized cubic | 1.85048 at 96.47 % | 1.92174 at 95.62 % |
| **What the chart reading costs** | **+0.000 %** | **+0.125 %** |
| **What the cubic freedom buys** | **+0.143 %** | +0.027 %, below the noise floor |

**Both effects are real, and they change places.** At area ratio 40, where the chart is measured data, the quadratic search returned the chart vector unchanged. The chart reading is already the best wall in the parabola family there, so the whole of the gain is the cubic's extra freedom, and that gain is a demonstrated local optimum: a perturbation margin of -2.65e-4 against a noise floor of 9.75e-7 clears its own resolution by a factor of 270.

At area ratio 70, inside the region SP-8120 marks as extrapolated, the picture inverts. Most of the difference is the chart, worth 0.125 percent, and the cubic's further 0.027 percent is below the noise floor and is reported as unresolved rather than as a result. The chart parabola's exit plane there closes 92.6 percent against the searched walls' 95.7, the largest closure difference in this document, which is why every coefficient here is normalized.

**This does not contradict Allman and Hoffman, and the distinction is worth keeping.** They measured an optimized second-degree wall against a true Rao *variational* contour. NOVA's baseline is the Rao *parabola*, the 1960 approximation to that contour rather than the contour itself. A cubic beating the parabolic approximation by 0.143 percent is consistent with both walls sitting below a variational optimum that neither of them is.

What stays open is what their table implies: nothing here compares any NOVA wall against a true variational contour, because no source in the reference set publishes one as coordinates.

## The internal shock

A truncated ideal contour cannot carry one: its wall is a streamline of a shock-free field, so its characteristics never converge by construction. Both optimized families can, and whether they do is a property of the design point rather than of the family.

Across the seven design points swept, at bell fractions of 0.60 to 0.90, **no family produced a shock inside the nozzle**. A chart parabola at 80 percent bell turns gently enough that its wall characteristics meet beyond the exit plane, which is not a shock in the nozzle.

A sweep that finds nothing says nothing about the detector, so the response is measured directly by turning one wall progressively harder than the chart parabola at area ratio 40 and 80 percent bell:

| Wall | Shock | Onset x | Deflection | Stagnation ratio | Weak | Thrust debit | Cf | Closure |
|---|---|---|---|---|---|---|---|---|
| Parabola, chart angles | no | | | | | | 1.77798 | 96.22 % |
| Cubic at the parabola design vector | no | | | | | | 1.77798 | 96.22 % |
| Cubic, inflection +4 degrees | yes | 12.801 | 0.799 deg | 0.99999 | yes | 0.0000 % | 1.75756 | 94.59 % |
| Cubic, inflection +8 degrees | yes | 6.037 | 16.968 deg | 0.86912 | no | -0.7856 % | 1.68891 | 89.56 % |
| Cubic, inflection +14 degrees | yes | 3.440 | 29.470 deg | 0.55546 | no | -4.2924 % | 1.88719 | 72.00 % |

Onset moves upstream and deflection grows monotonically with wall turning, which is the behavior the physics requires and the opposite of what three earlier mesh-position detectors produced. The first two rows are the same wall written two ways, and their agreement is the containment property measured rather than asserted: the searched family contains the charted one, which is what makes any comparison between them a comparison of walls rather than of code paths.

**The capture is only as good as the weak column.** Holding each region isentropic and carrying a stagnation pressure debit across a fitted front is defensible while the entropy rise is third order in shock strength. At four degrees past the chart parabola it is; at eight and fourteen it is not, and the solution reports `isWeak` as false rather than returning a number the treatment does not support.

The last row is also the clearest statement of why a raw coefficient is never quoted alone here. It reports a HIGHER coefficient than the parabola while closing only 72 percent of the throat mass flow. A wall that spills its flow out of the sampled plane is flattered by its own discretization, and refusing that is what the optimizer's closure band exists for.

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

The published dimensions are not self-consistent, so it has two things to be compared against. A throat diameter of 10.3 in with an exit diameter of 90.7 in gives a geometric area ratio of 77.6 against the published 69.5. Taking the exit diameter and the area ratio as the consistent pair puts the throat at 276.3 mm; the separately quoted 261.6 mm is 5.3 percent away from that. At least one of the three published numbers is not the quantity it appears to be.

| NOVA throat diameter | Against | Difference |
|---|---|---|
| 273.0 mm | 276.3 mm, implied by the published exit diameter and area ratio | -1.2 % |
| 273.0 mm | 261.6 mm, the separately quoted throat diameter | +4.4 % |

Against the self-consistent pair the throat sizing lands within 1.2 percent, on an engine whose only inputs here were its propellants, mixture ratio, chamber pressure, thrust and area ratio.

The throat sizing itself has a cleaner check that does not depend on any published dimension. The choked-flow relation NOVA uses is a perfect-gas expression at the throat ratio of specific heats; CEA computes the characteristic velocity from equilibrium thermochemistry. At this operating point they give **2320.2 m/s and 2320.7 m/s**, agreeing to **0.02 percent**. The throat sizing path is therefore not where any remaining disagreement lives.

For scale on the rest: CEA gives a vacuum specific impulse of 462.9 s at this operating point against the RS-25's published 452.3 s, so the engine delivers 97.7 percent of the theoretical value. That is a normal figure for combustion efficiency, a boundary layer and kinetic losses together, and none of the three is modeled here.

The one other thing this case establishes independently is the length convention. The 15 degree cone to the RS-25's published exit radius is 3.81 m against its quoted nozzle length of 3.07 m, which is 80.6 percent, and the engine is described as an 80 percent bell. The definition of percent bell used here is the one the engine is quoted against.

## Grid convergence

Fifty characteristics are launched from the throat arc by default. Sweeping that resolution at area ratio 40 and 80 percent bell, against the finest mesh:

| Characteristics | Area ratio | Length fraction | Exit wall angle | Error | Thrust coefficient | Error |
|---|---|---|---|---|---|---|
| 25 | 40.0000 | 0.8000 | 8.571 | -4.26 % | 1.78908 | -0.81 % |
| 35 | 40.0000 | 0.8000 | 8.947 | -0.07 % | 1.79562 | -0.44 % |
| 50 | 40.0000 | 0.8000 | 8.773 | -2.02 % | 1.79494 | -0.48 % |
| 70 | 40.0000 | 0.8000 | 8.956 | +0.03 % | 1.80170 | -0.11 % |
| 100 | 40.0000 | 0.8000 | 8.953 | 0 | 1.80363 | 0 |

The area ratio and the length fraction are converged trivially, because they are constraints the solve satisfies rather than results it produces.

**Neither the thrust coefficient nor the exit wall angle is converged at the default mesh, and neither approaches its limit monotonically.** The thrust coefficient carries about 0.5 percent of mesh error there and the exit wall angle about 2 percent, which is 0.18 degrees. In both the error at 50 characteristics is larger than at 35.

An earlier version of this section reported the thrust coefficient as converged to 0.013 percent. That was an artefact of how it was computed. The exit-plane integral used a smooth one-dimensional coefficient evaluated at the local pressure, which varied little as the mesh changed; replacing it with the actual momentum flux, which is what the momentum theorem requires, exposed a mesh sensitivity that had been there all along and was being smoothed over. The correction is described under the defects below.

Non-monotone convergence of this kind is the signature of an answer that moves discretely as mesh lines land on either side of the truncation point rather than one converging smoothly.

**Most of that error is the exit plane's mass deficit rather than the contour solve, and the rest is not.** Recording the closure beside the coefficient separates the two:

| Characteristics | Thrust coefficient | Error | Exit mass closure | Coefficient over closure | Error |
|---|---|---|---|---|---|
| 25 | 1.78908 | -0.807 % | 96.916 % | 1.84601 | -0.185 % |
| 35 | 1.79562 | -0.444 % | 97.217 % | 1.84702 | -0.130 % |
| 50 | 1.79494 | -0.482 % | 97.359 % | 1.84362 | -0.314 % |
| 70 | 1.80170 | -0.107 % | 97.444 % | 1.84897 | -0.025 % |
| 100 | 1.80363 | 0 | 97.524 % | 1.84943 | 0 |

The closure climbs monotonically with mesh, and dividing it out cuts the coefficient's mesh error from 0.81 percent to 0.19 percent at the coarsest mesh. So the bulk of what this section previously attributed to the contour solve is the plane sampling less mass than the throat passes.

**It does not explain the non-monotonicity.** The ratio is still worse at 50 characteristics than at 35, by more than it is at either neighbor, so something in this family's solve genuinely moves discretely with mesh, and the truncation landing between mesh lines remains the best explanation for it.

The thrust-optimized parabola over the same sweep separates the two effects cleanly. Its mass closure rises monotonically and its normalized coefficient falls monotonically, but its raw coefficient dips once, at the step from 25 to 35 characteristics. So the raw coefficient is non-monotone in both families while the normalized one is non-monotone only in the truncated ideal contour. That is consistent with the truncation being the source of the residual, and it does not establish it.

The practical consequence is unchanged: quote the coefficient at this mesh to about two tenths of a percent, not better.

Nought point two degrees is small against the 0.6 to 4 degree differences the Rao comparison reports, so the conclusions there survive. It is not small against the precision the numbers are printed to, and an exit wall angle should be quoted to no better than a tenth of a degree at this mesh. Every wall angle quoted in the Rao comparison above inherits that error.

The thrust coefficient behaves correctly against length, which is a physical check rather than a numerical one. At an area ratio of 40 it rises monotonically with the bell, from 1.7673 at 60 percent to 1.7885 at 70, 1.7949 at 80 and 1.7998 at 90. The gain from 80 to 90 percent is 0.27 percent, against a gain of 1.56 percent from 60 to 80. Published practice puts an 85 percent bell at about 99 percent nozzle efficiency with only a further 0.2 percent available by going to full length, and the diminishing return here is of that size. It is the reason 80 percent is the conventional choice, and the solver reproduces it without being told.

## The exit pressure matching condition

The assumption under test: that the static pressure at the end of the contour can be used to enforce an exit pressure matching condition.

It cannot, for three independent reasons, and the exit plane of the worked case shows all three at once. At an area ratio of 40 and 80 percent bell:

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

Measured on the worked case at an ambient of 101.3 kPa, the thrust integral peaks at an area ratio of 13.18, where the wall pressure is 99.3 kPa, within 2 percent of ambient. Cutting instead where the mass-averaged exit pressure reaches ambient stops at an area ratio of 10.03 and gives up 2.0 percent of the available thrust gain, because on this contour the mass average is 0.729 of the wall value.

What remains true is that the plane is strongly non-uniform, spanning a factor of 3.0 in static pressure from wall to axis. That matters for describing the exit state and for the state handed to the plume march. It does not make the wall the wrong place to apply a thrust criterion.

**The target is a different quantity from the residual.** The target exit pressure comes from CEA at the requested area ratio, computed with equilibrium chemistry and a varying ratio of specific heats. The mesh is a perfect gas at the chamber ratio of specific heats throughout. At an area ratio of 40 the two disagree before any contour is drawn: CEA gives an exit Mach number of 4.2234 and an exit pressure of 13993 Pa, against 3.9537 and 17699 Pa from the perfect-gas relation at the chamber gamma. That is 6.8 percent in Mach number and 20.9 percent in pressure. Driving a perfect-gas wall pressure to an equilibrium one-dimensional target is not a matching condition; it is a comparison between two different models evaluated at two different places.

**There is no free parameter left to satisfy all three at once.** A truncated ideal contour has one free parameter, the design exit Mach number of the ideal nozzle it is cut from. Fixing an area ratio and a length uses it up and the exit pressure is a result; fixing a pressure and a length uses it up equally well and the area ratio is the result. What cannot be done is asking for all three.

NOVA resolves this by always cutting at the requested expansion ratio and solving the design Mach number for the requested length fraction, so it delivers those two exactly and reports the exit pressure as a result. A wall-pressure cut, described below, would deliver the maximum-thrust nozzle for a given ambient instead; NOVA does not implement it, since a criterion built on the wall's local static pressure was judged not worth the complexity against simply cutting on area ratio, which is what a requested exit pressure already reduces to through the one-dimensional CEA relation before the contour is drawn.

The area-averaged exit pressure of 17.4 kPa against the perfect-gas one-dimensional value of 17.7 kPa at the same area ratio, a 1.8 percent difference, is a useful internal check in its own right: the characteristics solution, averaged over its exit plane, agrees with the one-dimensional answer for the same area, as conservation requires.

## Which pressure a pressure match should converge on

Measured rather than argued. One ideal contour at a fixed design Mach number, truncated across a range of area ratios at an ambient of 101.325 kPa, with the thrust coefficient computed at each cut.

| Convergence target | Delivered area ratio | Thrust coefficient | Against the peak |
|---|---|---|---|
| Wall static pressure | 12.40 | 1.46342 | -0.026 % |
| Mass-averaged exit pressure | 10.40 | 1.46062 | -0.217 % |
| Area-averaged exit pressure | 10.40 | 1.46062 | -0.217 % |
| *the true maximum* | *12.80* | *1.46380* | -- |

**The wall wins, and by an order of magnitude.** Converging on it lands within 0.03 percent of the maximum thrust coefficient; converging on either average under-expands by more than two in area ratio and gives up 0.22 percent.

That is what the surface integral predicts. Extending a nozzle adds a ring of wall whose axial force is $(P_{wall} - P_{ambient})$ times its projected area, so the sign of the gain is set by the wall pressure alone. Because the flow is supersonic, adding wall at the exit cannot change anything upstream of it, and the relation is exact rather than approximate.

Two independent formulations of thrust agree on the location. The wall surface integral gives its maximum at $P_{wall} = P_{ambient}$ analytically. The exit-plane control-volume integral, computed over the same sweep, peaks at an area ratio of 12.60 where $P_{wall}/P_{ambient} = 0.9988$.

Two qualifications belong with the result. It is the **unconstrained** optimum, assuming no penalty for length or mass; a length-constrained design truncates earlier, which is the problem Rao's optimization solves. And it is the condition for **where to cut one ideal contour**, not the optimality condition across a family of different design Mach numbers at a fixed length.

NOVA does not implement a wall-pressure cut; this section records the analysis for a reader weighing whether it would be worth adding one against the operating ambient rather than a CEA exit pressure.

## One-dimensional dependencies

Where a one-dimensional relation stands in for the solved field, and what it costs.

| Where | What it sets | Cost | Status |
|---|---|---|---|
| Reference cone length | The length the bell fraction is measured against | Was 12.0 percent long, because it came from a one-dimensional Mach number rather than the area ratio | Corrected |
| Conical diverging section | The entire wall of a conical nozzle | Delivered area ratio 48.5 against a requested 40 | Corrected |
| Exit line of the flow-straightening kernel | Where the ideal mesh terminates | None. An ideal nozzle exit IS uniform and axial by definition, so its radius follows from continuity exactly | By construction |
| Converging section wall state | Mach, pressure, temperature and velocity from the chamber to the throat | Not quantified. There is no solved subsonic field to compare against, and building one is a different problem from this one | Open, disclosed |
| Transport properties for cooling | Every gas-side property the regenerative model uses | Taken from CEA at each area ratio, so the cooling model never sees the characteristics field. Near-wall Mach differs from the one-dimensional value by up to 42 percent just past the throat and settles about 5 percent below it through the rest of the nozzle | Open, quantified |
| Ratio of specific heats | The entire mesh | The mesh is a perfect gas at one value throughout. At the chamber value, the default, that is 6.8 percent in exit Mach number and 20.9 percent in exit pressure against CEA at an area ratio of 40. `gammaModel` can select an effective value instead, fitted so the pressure ratio and the area ratio close together, which cuts the mean pressure error from 12.8 to 4.2 percent and biases the gas temperature cold | Open, quantified, partly mitigable |
| Throat area correction | Every dimension the tool produces | An unsourced factor reducing throat area by 0.070 percent. Documented in `contour.throatScalingFactor` as unsourced | Open, disclosed |
| Thrust coefficient back pressure | The pressure term of the thrust coefficient | Uses the design exit pressure as the ambient, so the reported thrust coefficient is a design-point value and not the value at the operating altitude | Open, disclosed |

The largest of these by far is the ratio of specific heats. A perfect-gas mesh at one value is the aerodynamic core of the standard method with the chemistry removed, and the standard method uses equilibrium properties. For scale, the JANNAF standard code predicts delivered vacuum specific impulse to within 0.12 to 1.9 percent of experiment with kinetics, a boundary layer and its displacement thickness all included; none of those are here.

### Choosing the value the mesh runs at

The chamber is the hottest and most dissociated gas in the engine and the least like the gas doing the expanding, so taking its exponent is the obvious choice and the worst one. `gasDynamics.effectiveGamma` returns the value for which the two relations the contour is built from agree at the design point: the pressure ratio the thermochemistry gives and the area ratio it pairs with that pressure ratio come out of the perfect-gas relations together. On the LOX/LH2 reference engine that value is 1.2072, against 1.1475 at the chamber and 1.2572 at the exit, and it reproduces the requested area ratio of 40 exactly by construction.

It is a calibration and it does not buy everything. Measured one-dimensionally against CEA over area ratios 2 to 40, so the comparison is like for like:

| Mean absolute error against CEA | Chamber, 1.1475 | Effective, 1.2072 |
|---|---|---|
| Static pressure | 12.8 % | 4.2 % |
| Static temperature | 10.1 % | 11.0 % |

One exponent cannot reproduce both the pressure-area relation and the specific heat, and this one is fitted to the first. Temperature is a wash in magnitude and not in sign: the chamber value runs the gas hot as it expands and the effective one runs it cold. The thermal model reads its driving temperature off this same solve, so a cold bias undersizes a cooling jacket, and that is why the chamber value remains the default. The effective value is the better exponent for contour geometry and performance and the worse one for a jacket, and `gammaModel` makes that a stated choice rather than an accident. Both values are recorded on every run either way.

Removing the choice altogether means giving the characteristics solve local properties rather than one exponent, which is a different solver and is not this.

## Defects found

All found by comparison rather than by inspection, and all corrected.

Four of them share a shape worth naming, because it is the one this document exists to catch: **a quantity that was reported rather than measured**. A smoothing spline that returned a fit where an interpolation was intended, an integral over part of a plane presented as an integral over the plane, a search that reported an optimum it had not tested for, and a comparison that reported a gain its own normalization forbade. None announced itself, each produced a plausible number, and each was found by putting the number next to something it had to agree with.

**The near-wall Mach number was destroyed by a smoothing spline.** The near-wall arrays are resampled onto an evenly spaced contour with `UnivariateSpline`, whose default smoothing factor is an absolute residual budget of one per data point. Whether it interpolates or fits therefore depends on the magnitude of the values rather than on their shape. Pressure in pascals came through untouched; Mach number, being of order one, was replaced by a single straight line through the whole wall. It read 4.81 at the exit against a true 4.07, and 1.90 at the throat, while the pressure beside it stayed correct, so the two arrays disagreed by a factor of 4.7 on the isentropic relation they were both built from. The regenerative cooling model reads the Mach array for the recovery temperature, which moved by up to 600 K when this was fixed. The geometry and the thrust coefficient were unaffected. Locked by `tests/testContour.py`.

**The exit plane was integrated over only 92 percent of its area.** The walk that samples the exit plane descends through the mesh from the wall and runs out of columns at about 29 percent of the exit radius, leaving the core unsampled. Because the thrust integral weights by area over the full exit area, the unsampled core subtracted directly from the thrust coefficient rather than appearing as a gap. The plane is now closed on the axis, where the flow angle is zero by symmetry and the Mach number is extrapolated from the two innermost sampled points, and `exitPlaneSampledFraction` records how much of the plane the mesh actually supplied.

**The pressure term of the thrust coefficient was halved.** It normalized by `pi * rt * 2` rather than `pi * rt^2`. With the non-dimensional throat radius at one this divided by twice the correct value.

**The requested area ratio was never a constraint.** Covered above.

**The reference cone was measured against the wrong area ratio.** Covered above.

**An optimum was declared over a neighborhood that was never measured.** The optimality test perturbs each design variable and requires every neighbor to be worse by more than the mesh noise. A candidate refused by the closure band comes back with a large negative merit or a graded penalty, and both are finite, so a guard written on finiteness admitted refused candidates as though they were scored. A design point where all eight perturbations fell outside the band therefore looked exactly like a design point that beat its neighbors, and reported a margin of -1.6 against a noise floor of 0.279 on a coefficient near 1.8. The two magnitudes are impossible for the quantity and are what exposed it. A candidate now counts only when its merit IS its thrust coefficient, the number of perturbations actually scored is reported beside the verdict, and an optimum requires at least one.

**The gain over the parabola was quoted raw, in a study whose thesis is that raw coefficients are not comparable.** The searched contour and the parabola need not sample the same fraction of their exit planes, and at area ratio 70 they differ by 3.3 points of mass closure. The reported gain there read 3.652 percent where the closure-normalized figure is 0.127. Both defects on this line ran in the same direction, which is the direction that flatters the result.

**The internal shock was reported by code that had never run.** The study read the crossing arrays from a summary object that carries onset and strength instead, so any detection raised a `KeyError`. It never fired, because no design point in the sweep produces a shock, and the section printed a column of zeros that read as a measurement of the families and was in fact a measurement of nothing. The study now reads what the solution carries, and it drives one wall through increasing turning so the zeros have a response curve behind them.

**A reassociated expression moved a contour by parts in a billion.** Sauer's axial offset was derived from the flow parameter rather than kept as its own closed form. The two are equal in exact arithmetic and differ by one unit in the last place at some ratios of specific heats and not others, so six of seven regression cases stayed bit-identical and the seventh moved 61 quantities. Both closed forms are now written out on the default path. The failure was invisible for a day because the regression runs were piped through a filter that dropped the summary line: a gate that is filtered is not a gate.

Two further discrepancies are recorded rather than fixed, because fixing either would move numbers for reasons unrelated to the physics.

The nozzle and the plume carry the limiting velocity in two algebraically identical but numerically different groupings, differing by about one unit in the last place. It is recorded in `tests/testCharacteristics.py`.

The design Mach number was solved to a tolerance loose enough that a one-ulp change in a Prandtl-Meyer evaluation moved the delivered area ratio in the fourth decimal. The tolerance is now 1e-8 and the Prandtl-Meyer function has one grouping across the whole codebase.

## Validation status

Stated plainly, because the three categories are not the same thing.

**Checked against an independent reference.** The thrust-optimized parabola beats the truncated ideal contour at all seven design points by 0.05 to 0.83 percent, and by 0.229 percent at the worked point, against SP-8120's statement that a truncated ideal contour costs of the order of a quarter of a percent. The searched contour trails the parabola at four of seven points and leads at one, which is the direction Allman and Hoffman's own table reports for a directly optimized wall against Rao. The unit process is second order, verified against the exact planar Riemann invariants: halving the state jump quarters the departure, with measured orders of 1.88, 1.94, 1.97, 1.99 and 1.99. The gas relations reproduce published compressible flow tables. The throat sizing agrees with CEA's equilibrium characteristic velocity to 0.02 percent, and gives an RS-25 throat diameter within 1.2 percent of the value implied by that engine's published exit diameter and area ratio. The percent bell convention reproduces the RS-25's published 80 percent. The Rao wall-angle comparison is against a published chart, with the caveat that it is a different contour family.

**Checked internally, with no external reference.** The exit plane passes 97.4 percent of the choked throat mass flow, the remaining 2.6 percent being discretization in the mesh and in the integration. The near-wall pressure, temperature, velocity and Mach number satisfy the isentropic relations they were built from exactly, everywhere along the wall, because only the Mach number is interpolated onto the resampled contour and the other three are derived from it. The area-averaged exit pressure agrees with the one-dimensional value at the same area ratio to 1.8 percent.

The thrust coefficient agrees with an independent momentum integral over the same exit plane to 0.03 percent, which checks the formulation. It sits 3.7 percent below the closed-form one-dimensional ideal, and most of that is the exit plane's own resolution rather than physics: the plane carries 2.6 percent less mass than the throat, and the momentum term scales with it. The divergence loss at the delivered exit wall angle accounts for a further 0.6 percent. An earlier version reported 0.28 percent against the ideal, which looked better only because a single-cosine error in the momentum term was cancelling the mass deficit.

**Not validated.** The flowfield itself, point by point: no source in the reference set publishes a tabulated axisymmetric solution for a rocket bell that could serve as a reference, and that holds for the optimized families too, since neither Allman and Hoffman nor RP-1104 publishes wall coordinates.

The transonic starting line. Sauer's solution is the first term of a series whose next term is 29 percent as large at this throat curvature. Two further terms are selectable, but they are carried as a throat *condition* imposed on Sauer's spatial form rather than as the series field, so the shape of the sonic line away from the throat plane is Sauer's under every option. The gap is narrower and measurable; it is not closed.

SP-8120's "29-term series" is a different method and not a target for this one: it belongs to a reference-streamline inverse solution in a proprietary program, where the term count buys a close fit to the requested wall geometry rather than order of accuracy. The monograph's second permitted route, Kliegel and Levine, is the family NOVA is in, and its authors concluded that series does not converge for higher approximations. So the row is not closed by adding terms in either direction. What would close it is a sonic-line field rather than a throat condition on Sauer's shape.

The boundary layer, in magnitude, though the gap is smaller than it first looked and most of it is now accounted for. NASA RP-1104 charges friction over a perfect bell at a Fanning factor of 0.003, in the same convention this model uses, so the two compare directly. On the worked contour NOVA's effective factor over the diverging section is 0.003854, a ratio of 1.29 rather than the factor of two implied by comparing 2.0 percent against a 0.5 to 1.5 percent budget.

Running NOVA's own drag integral at RP-1104's factor, over the same wetted area and the same dynamic pressure, gives 1.55 percent. That is the number that settles it: at the reference friction level this contour still sits at the top of the published band, because it is a 40 to 1 bell with 1.13 square meters of wetted area on a 98 kN engine, and RP-1104 itself notes that small low-pressure nozzles run above 0.003. So about a third of the discrepancy is the friction level and the rest is the design point. What remains unvalidated is the friction closure against a measured profile, and the fact that this is friction drag alone where a budget is usually net of the displacement effect. Nothing has been tuned.

The internal shock capture. Detection and onset behave correctly against wall turning, and the capture applies a Rankine-Hugoniot jump across a fitted front while the characteristics stay isentropic within each region. That treatment is only defensible while the front is weak, and the solution reports whether it is. A front turning the flow by more than a degree or two is reported rather than trusted.

The gas model: nothing here establishes what a perfect-gas mesh at a single ratio of specific heats costs against an equilibrium one. The converging section: quasi one-dimensional with nothing to check it against. And absolute performance: the friction debit is now computed, but kinetics is not, so the thrust coefficient still cannot be compared directly with a delivered engine specific impulse.

Closing the transonic gap means implementing the series field rather than more terms of the throat condition. Closing the boundary layer gap means a published case to check the magnitude against, since the limiting cases already pass. Closing the gas-model gap means either an equilibrium mesh or a quantified study of what the perfect-gas assumption costs. Closing the flowfield gap means finding or generating a reference solution, which no source in this set supplies.

## Reproducing

Run from the NOVA root with `C:\Users\seanb\miniconda3\python.exe`:

```
python -m pytest                                   # the suite
python featureShowcase/runBaseCase.py              # the worked LOX/LH2 case
python featureShowcase/verifyContour.py            # the single-case check
python featureShowcase/buildContourValidation.py   # the truncated ideal sweeps, about fifteen minutes
python featureShowcase/buildContourFamilies.py     # the cross-family study, about forty minutes
python featureShowcase/buildSubfamilyStudy.py      # the quadratic subfamily, about two hours
python featureShowcase/buildChamberField.py        # the chamber and converging section fields
python tests/regressionHarness.py --compare        # bit identity against the recorded baselines
```

`featureShowcase/contourValidation.png` carries the sweeps and `featureShowcase/contourVerification.png` the single case. Every number quoted above is printed by one of those scripts rather than stored.

## Author's Information

Sean Bowman - Last Updated [09/06/2026]
