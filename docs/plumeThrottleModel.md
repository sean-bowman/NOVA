# Throttled Plume Model

This document covers a plume solve driven by engine power level at a fixed ambient pressure, the counterpart of the existing sweep that holds the engine fixed and varies the ambient. It states what is and is not new physics in that change, the throttle range the reference engine has before its nozzle separates, a defect that has to be fixed before any of it is trustworthy, and the staged path to building it. The march itself is documented in `stationMarch.py`; the correlations it seeds from are in `plume.py`.

---

## Nomenclature

| Symbol | Meaning | Units |
|---|---|---|
| $f$ | throttle fraction, chamber pressure over its rated value | -- |
| $p_c$ | chamber stagnation pressure | Pa |
| $p_e$ | one-dimensional exit static pressure | Pa |
| $p_a$ | ambient static pressure | Pa |
| $p_{lip}$ | static pressure at the wall on the exit plane | Pa |
| $p_{sep}$ | wall static pressure at separation | Pa |
| $M_{sep}$ | wall Mach number at separation | -- |
| $\gamma$ | ratio of specific heats | -- |

---

## Pressure ratio invariance

**The plume field is invariant under scaling the chamber and the ambient together, so a throttle sweep at frozen gas properties is the existing ambient sweep relabeled.** Solving the shipped contour at full chamber pressure against an ambient of 10.764 kPa, and again at half chamber pressure against half that ambient, returns identical fields: 30 855 nodes with zero difference in node position, node Mach number and jet boundary, and the same worst mass drift to every digit.

That is the expected result rather than a surprise. The march carries one stagnation pressure, the boundary Mach number follows from the stagnation to ambient ratio, and the compatibility relations are homogeneous in pressure. Nothing in an inviscid perfect-gas solution knows the absolute pressure level.

The consequence sets the whole design. Rebuilding the sweep with the engine as the variable produces the same frames in the same order unless the model is given something that actually depends on power level. There are three such things, and they are what the work consists of.

---

## What changes with throttle

**The gas state.** Chamber temperature, molecular weight and $\gamma$ all shift as chamber pressure falls, through the equilibrium composition. The exit Mach number follows the area ratio and $\gamma$, so the characteristic mesh the march continues is strictly a function of the power level. The shift is small over a 5:1 throttle on LOX/LH2 and it is not zero, and it is the only mechanism by which the plume shape at a given pressure ratio depends on where that ratio came from.

**The separation limit becomes a throttle limit.** At fixed ambient, throttling down walks the nozzle from underexpanded to overexpanded to separated. Where the existing sweep refuses a case for being outside the attached-flow envelope, a throttle sweep reports a minimum power level, which is an engineering answer about the engine rather than a refusal about the model.

**Delivered performance.** Thrust, specific impulse and mass flow against power level are what a throttle study is usually for, and all three fall out of the same solve.

---

## Steady solutions, not a transient

The sweep is a sequence of steady solutions, one per power level. That is a modeling choice with a margin behind it.

**A true transient is a different solver, not a modified one.** The march is hyperbolic in space: steady supersonic flow sends information only downstream, which is what lets it advance station by station from the exit plane. Unsteady flow is hyperbolic in time, so the whole field has to advance together and there is no station, no marching direction and no initial line at the lip. Four further assumptions break at the same time:

- One stagnation pressure for the whole field, which is exactly why the scheme describes no shock. A transient forms and moves shocks, so entropy stops being uniform and the scheme needs a Riemann solver.
- The ambient as a pressure rather than a fluid. A moving jet boundary pushes on something, so the ambient has to enter the domain across a contact discontinuity.
- Inviscid, which is survivable here only because the envelope keeps the solve away from separation. Separation is a boundary-layer phenomenon, so a transient worth running is viscous.
- The nozzle as the system. A real throttle transient is driven upstream of the lip by valve motion, feed inertia and chamber filling.

**The margin is three orders of magnitude.** Unsteady terms scale with the ratio of flow residence time to forcing time. A particle crosses the 1.152 m of wall and the roughly 1.9 m of drawn plume at a few thousand m/s, so residence is about a millisecond.

| Forcing | Time scale | Residence over forcing |
|---|---|---|
| Throttle ramp | ~1 s | ~0.001 |
| Valve slam | ~10 ms | ~0.1 |
| Chug at 300 Hz | ~3 ms | ~0.3 |

At the ramp the unsteady correction is a tenth of a percent, against a march whose own mass continuity is a few tenths of a percent at two lip radii. **The term a transient solver would buy is smaller than the error bar the steady model already carries.**

Quasi-steady fails not during the ramp but at the events either side of it: startup and shutdown, where the structure establishes in milliseconds and overexpanded nozzles throw their largest side loads; chug, where the forcing is at the flow's own time scale; and the separation point sweeping along the wall, which has hysteresis. All three are viscous and unsteady, none is reachable by making this formulation time-dependent, and all three are out of scope.

---

## The reference engine's throttle envelope

Measured on the shipped case, which is a 100 kN LOX/LH2 upper stage at a chamber pressure of 6.8948 MPa, mixture ratio 5.5 and area ratio 40:

| Quantity | Value |
|---|---|
| $\gamma$ from the chamber solve | 1.14754 |
| One-dimensional exit Mach number | 4.2234 |
| Exit static pressure $p_e$ at full throttle | 13.993 kPa |
| Lip static pressure $p_{lip}$ at full throttle | 24.626 kPa |
| $p_{lip} / p_e$ | 1.7599 |
| Ideally expanded altitude | 14.05 km |

The march admits $p_e/p_a$ from the Summerfield separation floor of 0.40 up to `plumeFieldMaxPressureRatio` of 2.0. At a fixed ambient $p_a$ the exit ratio is $13.993\,f / p_a$ in kPa, so both bounds map onto throttle fraction directly.

Choosing $p_a$ so that full throttle sits at the top of the envelope gives $p_a = 7.00$ kPa, an altitude of 18.44 km. Separation then arrives at

$$f_{sep} = 0.40 \times \frac{7.00}{13.993} = 0.200$$

**A 5:1 throttle range, 100 percent down to 20 percent, at a fixed ambient of 7 kPa.** The sweep solves it in seventeen frames. The exit ratio walks 2.000 to 0.400 exactly linearly with power level, which is what a frozen gas state predicts, and the near-field mass continuity holds inside 0.6 percent over the whole range. Thrust falls from 106.4 to 19.5 kN and the one-dimensional ideal specific impulse from 462.5 to 423.8 s.

The number worth reporting from it is which side binds. CECE demonstrated 17.6:1 on an RL10 derivative of this propellant combination and cycle, so the engine is not what stops this case at 20 percent: the nozzle is. Raise the ambient and the nozzle limit tightens further, until at sea level an area ratio of 40 is separated at any power level at all, which is why the shipped configuration draws its plume at 5 kPa.

---

## The separation gate does not move with the chamber

**`solvePlumeStructure` takes its exit pressure from a stored array that no throttle touches, so a fixed-ambient throttle sweep would never trip the separation check.** The structure sets

- `exitPressure = targetExitPressure or nozzleNearWallPressure[-1]`, both carried from the rated-power nozzle solve,
- `exitPressureRatio = exitPressure / ambientPressure`,
- `nozzlePressureRatio = chamberPressure / ambientPressure`.

The second ignores chamber pressure and the third does not. Scaling `chamberPressure` by 0.5 and the ambient by 0.5 leaves `exitPressureRatio` reporting 2.600 where the march is solving 1.300, which is the measurement behind the invariance result above.

At fixed ambient the error is worse than a factor: `exitPressureRatio` is then constant for the whole sweep. Every separation refusal in `solveStationField` and `solvePlumeStructure` is written against it, so the model would march a nozzle at 5 percent power, deep inside separated flow, and return a clean attached plume with no note. The Mach disk and shock cell correlations would meanwhile respond correctly through `nozzlePressureRatio`, so the structure would be internally inconsistent rather than uniformly wrong.

`throttledContour` is what closes this. It scales every absolute pressure the contour carries and clears the structure, so the contour handed to a solve describes one engine at one power level. The hazard is not in the solvers, which are correct given a self-consistent contour; it is that nothing stopped a caller assembling an inconsistent one. `tests/testPlumeField.py` pins both halves: that the structure's exit ratio moves with the power level, and that the separation refusal fires when a sweep walks down to it.

---

## What the model does

`plume.throttledContour(contour, throttleFraction)` returns the same nozzle at a different power level. It scales every absolute pressure the contour carries, named in `contourPressureFields`, and clears any structure solved at the old one. `ceaOutput` is left alone deliberately: the plume path reads one dimensionless number from it.

`Nozzle.throttledPlumeField(throttleFraction, ambientPressure)` is `plumeField` with the engine as the variable. It returns the field rather than keeping it, because a sweep produces one per power level and none of them is the nozzle's own state.

`featureShowcase/buildPlumeThrottle.py` is the sweep. It takes the ambient from the contour so that rated power lands at the top of the march's envelope, walks the power level down in 5 percent steps, and stops where the march refuses on the separation criterion. Each frame carries its power level, its exit pressure ratio, the mass continuity at two and six lip radii, and the delivered thrust and specific impulse against power level with the separation limit marked.

Performance is analytic at a frozen gas state. Mass flow and every static pressure scale with the chamber while exit velocity does not, because the area ratio sets the exit Mach number, so

$$F(f) = f\,\dot m_r V_e + (f\,p_{e,r} - p_a)A_e$$

with the pressure term going negative as the engine throttles into overexpansion. It is drawn only over the attached range: below separation the jet leaves from inside the nozzle and the geometric exit area is no longer the area that matters.

## Cost of the frozen gas state

Chamber temperature, molecular weight and the ratio of specific heats all move with chamber pressure through the equilibrium composition. Holding them at their rated values is the model's largest approximation, so it is measured rather than asserted. Run at mixture ratio 5.5 on LOX/LH2 over a 5:1 throttle:

| Power level | Chamber pressure [MPa] | $\gamma$ | $T_c$ [K] | Exit Mach | $p_e/p_c$ |
|---|---|---|---|---|---|
| 100 % | 6.8948 | 1.14748 | 3392.3 | 3.9533 | 0.002568 |
| 60 % | 4.1369 | 1.14355 | 3343.9 | 3.9330 | 0.002608 |
| 40 % | 2.7579 | 1.14049 | 3303.7 | 3.9172 | 0.002640 |
| 20 % | 1.3790 | 1.13541 | 3232.3 | 3.8913 | 0.002693 |

**The field is unaffected and the separation limit is not.** Over the full range $\gamma$ moves 1.05 percent and the exit Mach number 1.57 percent, both inside the march's own mass drift. The exit static pressure ratio moves 4.9 percent, which biases the power level at which separation is reported by about the same amount, in the direction of reporting separation later than it happens. That bias is the size of the spread in the separation criterion itself, which is quoted as 0.35 to 0.40, so correcting one without the other buys nothing.

## What remains

**The gas state per power level.** Re-running the thermochemistry at each chamber pressure is straightforward; carrying it into the field is not. The characteristic mesh was solved at the rated $\gamma$, and reading its Mach numbers under a different one makes the state discontinuous at the plane the march starts from. The mesh has to be re-solved over the fixed wall, which `directCharacteristics.marchPrescribedWall` already does for the `top` and `toc` families, against a throat kernel re-launched at the new $\gamma$. The work is the wiring and a second regression baseline, not a new solver. The measurement above is what says it is worth deferring rather than worth doing now.

**Nothing else in the field moves with power level.** `CharacteristicGas` carries $\gamma$, the gas constant and the stagnation temperature, and `marchPrescribedWall` takes no chamber pressure at all, so the Mach and flow-angle field over a fixed wall is a function of geometry and $\gamma$ alone. Re-generating the mesh from the fixed throat at a different mass flow returns the same mesh by construction. Pressure enters afterward, as the multiplier that converts a solved Mach field into static pressures.

**The boundary layer does move with power level, and the sweep does not carry it.** At a frozen gas state the near-wall Mach, temperature and velocity hold while the pressure scales, so the Reynolds number falls with the chamber and the layer thickens relative to the nozzle. Marched on the shipped contour at a 800 K wall:

| Power level | Exit displacement thickness [mm] | Effective area ratio | Friction drag [N] |
|---|---|---|---|
| 100 % | 3.723 | 38.647 | 2016.7 |
| 60 % | 4.124 | 38.548 | 1339.7 |
| 40 % | 4.474 | 38.463 | 968.3 |
| 20 % | 5.141 | 38.299 | 555.9 |

Displacement thickness grows 38 percent and the exit skin friction coefficient 38 percent, against a geometric area ratio of 39.57. Two consequences. The effective area ratio falls 0.95 percent over the range, which shifts the exit pressure and so the power level at which separation is reported, by rather less than the 4.9 percent the frozen gas state already costs. And friction drag, which is 2.02 percent of thrust at rated power, is 2.79 percent at 20 percent power: **throttling makes the nozzle relatively draggier, by 38 percent.** The plume sweep does not include either effect.

**Separation as a model rather than a refusal.** Schmucker's criterion, `p_sep / p_a = (1.88 Ma_sep - 1)^-0.64`, evaluated along the wall locates the separation point instead of only declaring that one exists. The outputs that follow are the separation station, the area ratio there, the effective exit the jet actually leaves from, and the power level at which separation first enters the nozzle rather than sitting at the lip. The shipped contour is a truncated ideal contour, and truncated ideal and conical nozzles show free shock separation only; restricted shock separation belongs to thrust-optimized contours, so the `top` and `toc` families need checking before they take the same treatment. The plume downstream of a separated nozzle stays out of scope either way.

## Validation

**Closed form.** Pressure ratio invariance is an exact property of the formulation, and `tests/testPlumeField.py` holds it at zero difference in node position, node Mach number, jet boundary and mass drift. The mapping from throttle fraction to exit pressure ratio is linear at frozen $\gamma$ and is checkable against the march's own reported ratio at every frame.

**Against criteria, not against measurement.** Summerfield and Schmucker disagree by construction: one is a constant and the other rises with wall Mach number. Reporting both and the station they place separation at is a comparison of criteria, not a validation, and the document should say so. Stark's cold gas campaigns found Schmucker under-predicts the separation location, with the gap growing with wall Mach number at separation, so the criterion is a lower bound on how far the flow stays attached rather than a best estimate.

**A disclosed interaction with film cooling.** Stark reports that injecting a cooling film causes premature separation. NOVA's reference case carries a hydrogen film at the chamber end. Any separation station this model reports for a film-cooled engine is therefore optimistic by an amount no source here quantifies.

**Quasi-steady, by a margin stated above.** The sweep is a sequence of steady solutions and is defensible as one by three orders of magnitude in time scale. It is not a transient model and should not be described as one.

**Inherited, unchanged.** Every frame inherits the march's own envelope and its mass drift behavior: continuity holds inside a percent over roughly two lip radii and is worthless past six. A throttle axis does not improve that, and the frames should carry the same two drift numbers the ambient sweep carries.

**Hardware context, not validation.** CECE at 17.6:1, SSME at 17 percent power and RD-0120 at 25 percent are evidence about what engines do and what separated operation costs, including the nozzle brackets RD-0120 damaged in 480 seconds of separated running. None of them measures a plume NOVA computes.

---

## Out of scope

Side loads from asymmetric separation, which are the structural reason separated operation is avoided and which need an unsteady, three-dimensional treatment. Restricted shock separation and the transition between separation patterns. Mixture ratio excursion with power level, which real engines have and which NOVA's fixed mixture ratio does not represent. Combustion-side throttle limits, chug and injector pressure drop, which is where the demonstrated deep throttle ranges were actually won.
