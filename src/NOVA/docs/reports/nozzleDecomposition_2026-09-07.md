# Decomposing the rest of Nozzle.py

A running record of the effort to reduce `Nozzle` to an orchestration facade, with every capability isolated in a module that can be imported, tested and verified on its own.

The contour work that preceded this took `Nozzle.py` from 12,528 to 9,261 lines and produced `gasDynamics.py`, `characteristics.py`, `contourKernel.py`, `contour.py` and `plume.py`. What remained was the regeneratively cooled jacket: channel geometry, channel sizing, heat transfer, volutes, the converging section, the configuration reader and the export surface.

Each stage is held to bit-identity against a recorded baseline, the same discipline the contour work used. Defects are recorded here as they surface, with what the defect was, how it surfaced, and what it cost.

---

## Stage 0: a runnable case, a harness, and a clean root

### Why this had to come first

Nothing exercised the regenerative path. Both shipped configurations set `makeCoolingChannels` false, no test in `tests/` reached it, and the feature showcase did not run it. That left 4,385 lines with no evidence they ran at all, let alone a record of what they produced. Without such a record there is no way to tell a refactor that preserved behavior from one that changed it, and the contour work was safe precisely because that record existed.

Building the case found nine defects. Seven of them are on paths a user would reach with a valid configuration, and one of those sizes a pressure vessel wall.

### The defects

**A missing method left two paths unreachable.** `self.getDome()` was called in the sunken converging section and again in the volute view, and was not defined anywhere in the class. `xDome2D` and `rDome2D` were initialised to empty arrays and never written, so both paths raised `AttributeError` on the first call. The method existed in the predecessor repository, where it read a part-specific contour from a CSV that is not in either repository and whose generation branch was an unimplemented stub. The dome described a geometry that no longer exists, so it is not restored. What the two call sites needed is now supplied by a keep-out envelope, described below.

**The cross-section roll was computed from a flute helix angle that circular channels do not have.** Every channel type ran

```python
rollTotal = np.tan(np.deg2rad(self.fluteHelixAngle)) * totalPathLength / channelRadius
```

before branching on the cross-section shape. A circular channel carries no helix angle, so the configuration supplies none, the value arrives as NaN, and the roll of every station became NaN. The failure appeared 100 lines later as `ValueError: data must be finite` from a `KDTree` build, with nothing pointing at the helix angle. A circle is rotationally symmetric and a roll leaves it unchanged, so the roll is now taken as zero where there is no helix angle to turn through.

**The return volute turnaround accepted two mutually exclusive locators and silently used one.** `returnVoluteAxialOffset` and `returnVoluteRadialOffset` name the same station two different ways, and the code applied both in sequence, so a configuration giving both got the radial one with no warning. Giving both is now refused, and so is giving neither. A station resolving to the very start of the converging section is refused as well: the index is reused as the point count of the resampled turnaround, so a station at index 0 produced `IndexError` inside `arcSpline` rather than a message about the offset that caused it.

**The fluted channel model read a data file from a sibling repository.** The flute heat transfer study was loaded as `self.topLevelDirectory + '\propulsionDesign\assets\Nozzle\FlutedChannelHeatTransferStudy.csv'`, a path that resolves inside NOVA and points at a directory NOVA does not have. The file is in neither repository. The study is a CFD sweep of one family of flute geometries, so it is a supplied input rather than something the tool derives. It is now looked for in NOVA's own `assets/`, and its absence is reported with the path and the columns expected. The fluted channel type no longer requires it: the data map supplied a third comparison curve beside the fluted and circular results, and a run without one draws the two curves it can compute. `exportData` had the same cross-repository path for a configuration workbook; it now copies the workbook that was actually read, when one was.

**The sunken-contour validation had never run.** Section 9 of `_validateConvergingSectionInputs` was gated on `self.contourType == 'Sunk'`, with a capital S, while the validator immediately above admits only `'trad'` and `'sunk'`. The whole section was unreachable. Made reachable, it rejected a valid configuration: it required `infillThickness` to be a non-empty numpy array, while every other reference in the class, and the GUI schema, treats it as a scalar. It is now validated as the scalar it is.

**A contour type was documented, branched on, and rejected.** `'newSunk'` appeared in the validator's own error message as a valid choice, was branched on in `truncateForRegen`, and was refused by the same validator's check. The branch computed points of inflection and discarded them; its only consumer was commented out. Removed.

**The coolant exit state was read from the inlet end of the jacket.** The station loop marches from the coolant inlet and writes each station into `heatTransferPlots` reversed, at `N - 1 - i`, which puts the inlet at the last index and the exit at the first. That is the convention the model's own summary uses when it reports a pressure drop. `coolantExitPressure` and `coolantExitTemperature` were read from the last index, so they held the inlet state under the name of the exit state.

On the reference case the exit temperature was recorded as 30.73 K against a true 148.83 K, and the exit pressure as 12.0000 MPa against a true 11.8854 MPa. The pressure error is the whole jacket pressure drop, which the same run printed to the console as 0.1146 MPa; the corrected value now agrees with it exactly.

The consequence is structural. `generateRegenVolutes` sizes the return volute wall from the GRCop-42 yield strength at that temperature. Reading 30.73 K instead of 148.83 K put the lookup 47 K below the bottom of the alloy data, which spans 77.6 K to 1073.2 K, so the cubic spline was extrapolating outside its range as well as being asked about the wrong temperature. It returned 254.88 MPa where the material delivers 204.67 MPa at the temperature the volute actually sees: **the allowable stress was overstated by 24.5 per cent and the required wall thickness understated by 18.9 per cent.** The 0.96 per cent error in pressure differential runs the other way and does not offset it.

**A volute exported its geometry beside whichever script launched the run.** `Volute.generateVolute` resolved its output directory as `os.path.dirname(__main__.__file__)`, so an STL landed wherever the entry point happened to live, and an interactive session, which has no `__main__.__file__`, raised `AttributeError` instead of exporting. The directory is now a property of the volute, defaulting to the working directory. NOVA itself never reached this path, because `generateRegenVolutes` sets each volute's own export off and `exportData` writes the volute geometry, so it bit only a volute driven directly.

**The sunken turnaround was sized at the nozzle exit.** The widest a cooling channel can be where it leaves the jacket was taken from `max(self.rNozzleWall)`, marked in the source with `# idk how to replace channel outlet radius so were doing this instead`. At that point in the run `rNozzleWall` holds only the diverging contour, so the maximum is the nozzle exit radius, a station the jacket does not reach. On the reference case that read 318 mm where the chamber wall is 90 mm, giving a turnaround radius of 37 mm against a correct 12 mm. It is now measured at the chamber wall, where the channels actually leave.

### The keep-out envelope

The dome is replaced by a keep-out envelope: the axisymmetric volume behind the chamber that the jacket has to pack around, named by three numbers rather than read from a part-specific contour. It lives in [keepOut.py](../keepOut.py) and is a quarter ellipse of revolution swept from a shoulder at the chamber radius inward to a hub,

$$
x(\theta) = x_0 - d\sin\theta, \qquad r(\theta) = R\cos\theta, \qquad 0 \le \theta \le \arccos\!\left(\frac{r_{hub}}{R}\right)
$$

with the profile ordered from the shoulder inward. It is a packaging boundary, not a model of a closure, and its only claim is that geometry outside it does not intersect it. `packingClearance` reports the signed radial clearance of any profile against it.

Both former dome call sites read it. The sunken converging section offsets it by the width of the turnaround to get the wall that closes the chamber, and stores the outer arc and the envelope as the turnaround the return volute routes around. The volute view closes it back out to the chamber wall along a 35 degree ramp to get the winder keep-out. The configuration surface is `plotKeepOut`, `keepOutAxialOffset`, `keepOutRadius`, `keepOutDepth` and `keepOutHubRadius`; a dimension left unset takes a default from the chamber radius.

Where the sunken section is concerned the hub radius is not free. The wall that stands off the envelope is the converging wall, so it cannot close below the throat: an area ratio under one has no subsonic solution, and the failure surfaced 200 lines downstream as a Mach solver that would not converge at an area ratio of 0.81 rather than as the geometry that caused it. The offset between hub and closure is not a simple sum, so where the configuration does not name a hub radius the closure is solved for, and an explicit value that does not close is refused by name.

### What still does not run

**The sunken contour reaches the flow solve and stops there.** With the keep-out envelope in place and the closure solved onto the throat, the stitched wall enters `arcSpline` with a minimum radius exactly at the throat and leaves it with sixteen of sixty points below the throat, the worst 15.6 mm inside it. `arcSpline` fits an unconstrained cubic spline through the raw points, and the sunken stitch presents it with a corner: a dense ellipse, a dense arc, a single isolated conic control point, then a dense wall. The spline rings across the isolated point and overshoots by about 30 per cent of the local radius.

This is a defect in `arcSpline` rather than in the sunken contour, and `arcSpline` is used by every contour NOVA builds. Fixing it moves geometry throughout the tool, including the contour results that the preceding effort validated. It is therefore not fixed here: it is fixed in a stage that has a recorded baseline to measure the change against. The traditional contour, which every shipped configuration and the whole feature showcase uses, is unaffected and is what the baselines are recorded from.

**Fixed subsequently.** `arcSpline` now fits a shape-preserving interpolant, which cannot leave the range of the points it is given, and the diverging wall declares its input smooth to keep the curvature-continuous fit where that is the more accurate choice. See `arcSplineOvershoot_2026-09-08.md`.

**The data-map fluted channel model needs a study NOVA does not have.** Reported by name and path rather than by a file-not-found error against a directory that does not exist.

**The alloy strength curves extrapolate without saying so.** `getGRCopStrength` interpolates manufacturer data on a cubic spline and returns a value for any temperature it is handed, including temperatures outside the data. That is how a 30.73 K lookup returned a yield strength from a curve whose lowest datum is 77.6 K. The temperature error that triggered it is fixed; the curve still extrapolates silently, and clamping it to its endpoints the way `materials.py` clamps thermal conductivity would close it.

### The reference cases

`assets/regenExample.json` is the LOX/LH2 worked example with the jacket switched on: sixty circular channels in GRCop-42, hydrogen coolant at 3.4 kg/s entering at 12 MPa and 30 K, both volutes built with the return turnaround located by radial offset. `assets/regenExampleFluted.json` is the same case with fluted channels.

### The harness

[tests/regressionHarness.py](../../../tests/regressionHarness.py) runs a case end to end, walks every public attribute of the resulting `Nozzle`, and records what it found. A later run compares against that record and reports any attribute that differs at all. Floats are compared for exact equality rather than closeness, because a refactor that only moves code has no reason to change a single bit; NaN compares equal to itself, since it is a legitimate value here.

The comparison is worth nothing unless the run is deterministic, so `--verify` runs each case twice and compares the two before any baseline is trusted.

```bash
python tests/regressionHarness.py --record --verify   # record, and prove determinism
python tests/regressionHarness.py --compare           # after each stage
```

Baselines live in `tests/baselines/` and are not carried in the repository, so a fresh checkout records its own before it starts moving code.

### The repository root

Two generated artefacts sat in the root because the writers put them there. The GUI's export tab defaulted its output location to the repository root, so every run wrote `<name>RunConfig.json` into it, and `generateNozzle` resolved its export root the same way and created `<name>Outputs/` beside it. Both now resolve through `Nozzle._getOutputRoot`, which returns a gitignored `runs/` directory and which the GUI and the showcase scripts override with their own location. `codeInterface.py` moved to `examples/`.

The root now holds `README.md`, `dependencies.txt`, `pytest.ini`, `objectives.md`, `novaGui.bat` and the package directories.

---

## Stage 1: the thermal model

`regenHeatTransferModel`, `regenHeatTransferModelPlots` and `_validateRegenHeatTransferInputs` moved to [regenThermal.py](../regenThermal.py), 2,011 lines. The move was held to bit-identity on all three reference cases before anything else was touched.

The model's entire coupling to a `Nozzle` was six attributes, none of which it writes and none of which changes a number it computes: `material`, `dataFolder`, `plotsAdv`, `plotsDocs`, `export` and `debugMode`. They are now a `RegenThermalContext`, and `Nozzle.regenThermalContext()` builds one. Everything else already arrived through a single dictionary.

### The Bartz correlation, written once

The gas-side coefficient appeared three times, once per channel family, byte-identical apart from the name of the array it assigned to. It is now `bartzHeatTransferCoefficient`, and the three call sites pass their own arrays to it.

### Defects found

**The input validator was commented out.** 283 lines of validation with `# validateRegenHeatTransferInputs(inputsDict)` at the call site. It had drifted out of sync with the dictionary it validates in three ways, all of which would have failed on the first run had it been enabled:

- It required `coolantMassFlow`, a key the dictionary does not carry. The model reads the per-channel mass flow as `mdot`.
- It called `len()` on `gausFlutedCSA` without checking it was present. A circular-channel run supplies `None` there, so the validator raised `TypeError` rather than validating anything.
- It did not require `throatDiameter` or `throatArea`, which the Bartz correlation reads and cannot do without.

Corrected and enabled. It now accepts every one of the 615 dictionaries the two reference cases build, 307 from the circular case and 308 from the fluted one, and the runs remain bit-identical.

**A sentinel that no longer fires.** The gas-side coefficient is short-circuited to 5 W/m²K when the near-wall temperature is exactly 300 K, marking a station that sees no exhaust. Nothing in NOVA sets that value any more, so the branch is unreachable. It is kept, because a caller supplying its own station properties may still use it, and documented as what it is: an equality test against a float, which 300.0000001 would miss.

### Validation status

**Not validated against a measurement.** No published worked example with a complete set of inputs and a stated answer was available to set the implementation against. Searches of the accessible literature returned discussions of the correlation and comparisons against experiment, but none stating all of chamber pressure, throat diameter, throat curvature, gamma, molecular weight, characteristic velocity, gas and wall temperature together with the resulting coefficient.

**Checked in every way that does not need one.**

- *The stagnation viscosity constant is a unit conversion, and is verified as one.* Huzel and Huang give the fit as $\mu_0 = 46.6	imes10^{-10}\,M^{0.5}T^{0.6}$ in lbm/(in s) with $T$ in Rankine. Converting to SI gives $1.18408	imes10^{-7}$ against the $1.184	imes10^{-7}$ in the source, agreeing to five figures. The constant had no reference beside it before.
- *The dimensions reduce exactly.* Summing the meter exponents of every factor gives zero and the whole reduces to kg s⁻³ K⁻¹, which is W/(m² K). The implementation is held to that by rescaling every input as though the unit of length had changed, and confirming the coefficient moves by exactly the predicted factor. One term cannot be rescaled from outside, the embedded viscosity fit, so the residual is a clean $L^{0.2}$; freezing the specific heat as well makes it $L^{-1.8}$. Both land to machine precision, which constrains the exponents as a set rather than one at a time.
- *Each exponent is driven independently*, including the throat diameter, which enters twice and nets to $D_t^{-0.1}$.
- *The limiting behavior holds*: the coefficient falls monotonically with area ratio as $(A_t/A)^{0.9}$ over a factor of forty in area, and rises as the wall gets colder.

Those establish that the implementation is the correlation it claims to be. They do not establish that the correlation predicts a real engine.

**The embedded fit ties the correlation to SI.** Its constant carries units, so the function gives a wrong answer in any other unit system. That is recorded in the module rather than left for someone to find.

**The coolant side is not validated.** The circular correlation is Gnielinski, which is published and whose range of validity is known, but nothing checks the implementation against a reference case. The fluted correlation is a fifty-fifty blend of Gnielinski with a spirally fluted correlation from *Principles of Enhanced Heat Transfer*, with a roughness amplification applied to the second term only. No source states that blend or its range of validity.

What closes both gaps is a measurement: a fired engine with instrumented wall temperatures, or a published test case with its conditions fully stated.

---

## Stage 2: the channel cross sections

`generateCrossSections` and `getMaxChannelRadius`, with the frame construction, the fluting and the printability blend nested inside them, moved to [channelGeometry.py](../channelGeometry.py), 800 lines. They read sixteen attributes off the `Nozzle` and write none, so the coupling is a `ChannelGeometryInputs` and nothing more.

Geometry is the one part of this tool that can be held to closed form rather than to a correlation, and the tests do that.

### What is now verified

**The largest channel that fits is exact.** It is a circle inscribed in a wedge of half-angle $\pi/n$ and tangent externally to the wall circle: its center sits at distance $d$ with radius $r = d\sin	heta$, and tangency gives $d = R + r$, so

$$
r = rac{R\sin	heta}{1 - \sin	heta}
$$

The implementation matches that to machine precision across channel counts from 10 to 240 and wall radii from 30 to 300 mm. The independent check is packing: placing that many circles of the computed radius on their pitch circle leaves neighbours separated by exactly the infill thickness, and none crosses the wall.

**The transport frame is what it claims to be.** Orthonormal, right-handed and twist-minimizing. The last is the property that separates it from a Frenet frame and is what stops flutes winding up where the centerline happens to bend: on a planar curve the frame acquires no rotation about the tangent at all, held to $10^{-9}$. On a helical centerline every cross-section point stays perpendicular to the local tangent and at exactly the channel radius.

**A circular section is a circle.** Every point sits at the channel radius from the centerline to $10^{-12}$, the section lies in the plane normal to the tangent, and a single-station call reproduces the full sweep exactly.

**A bend reports its own radius.** A centerline bent into a circle of 50 mm reports 50 mm back through the turn-angle and curvature calculation that feeds the coolant pressure drop, to 0.1 per cent.

### Defects found

**`useGPU` was read but never defined.** The cross-section builder guards its CuPy nearest-neighbour search with `if GPU_AVAILABLE and self.useGPU != 'off'`. `useGPU` is set nowhere in the class and appears in no configuration, so on a machine without CuPy the first condition short-circuits and it is never reached, and on a machine with CuPy it raises `AttributeError`. The GPU path would have failed on exactly the machines it was written for. Initialised to `'off'`, which is the behavior every run has had.

**`nonPrintableIndices` was read but only sometimes defined.** Set by the printability audit and read by the cross-section builder whether or not that audit ran. Nested, it was reached only inside the printability branch, so the gap was invisible. Initialised to an empty list.

**A flute of zero amplitude produced NaN geometry in silence.** The profile is built by scaling a wave by its amplitude and normalizing by the same amplitude, which is singular at zero. A configuration setting `fluteAmplitudeCoef` to zero got NaN cross sections with no error, and the failure would have surfaced far downstream. A non-positive amplitude, or fewer than three flutes, is now refused by name.

### A disclosed difference, not fixed here

**The two channel families do not measure cross-sectional area the same way.** The circular family reports $\pi r^2$ exactly. The fluted family integrates its own polygon with the trapezoidal rule, which under-reports the same circle by the polygon deficit at that resolution:

| `numCSPointsChannel` | Deficit against$\pi r^2$ |
| ---------------------- | -------------------------- |
| 24                     | 1.239 %                    |
| 48                     | 0.298 %                    |
| 60                     | 0.189 %                    |
| 100                    | 0.067 %                    |

Driving the flute amplitude toward zero confirms it: the fluted area converges to the discretised circle, not to $\pi r^2$, and stops 0.19 per cent short at the default 60 points. The deficit is second order in the point count.

This matters because every fluted run plots its results against circular results computed at the same radius, and the comparison therefore carries a systematic area offset that is a discretisation artefact rather than a geometric difference. Flow area sets velocity, velocity sets Reynolds number, and the coolant-side correlation reads both. It is recorded rather than corrected here, because the areas feed the sizing convergence loop and that is Stage 3's subject.

---

## Stage 3: the channel sizing loop

`generateChannelRadii` and everything nested inside it moved to [channelSizing.py](../channelSizing.py), 977 lines. This is the automated sizing tool, and it is structurally unlike the two stages before it in two ways.

**It writes.** Eleven attributes, so it follows the pattern `contour.py` established rather than a read-only context: a `ChannelSizingState` carrying inputs and outputs, outputs starting as `None`, and a `channelSizingOutputs` tuple governing what is copied back. An output still `None` after a solve means that branch was never reached, which is worth keeping rather than hiding behind a zero.

**It has collaborators.** It rebuilds the cross section at each proposed radius and runs the thermal model against it, so it depends on both modules extracted before it. Those are now imports at the top of the file rather than closures reached through `self`, which is what makes the dependency order visible: geometry, then thermal, then sizing on top of both. Each was extracted against modules that had already stopped moving.

### What the loop is

The channel radius at a station is not a free choice. Too small and the coolant chokes, the pressure drop runs away and the wall overheats; too large and the channel will not fit between its neighbours or will not print. What sets it is the hot wall temperature, which is not known until the channel is drawn, the coolant marched through it and the heat balance solved.

So it is a one-dimensional root find on a monotone function, since a wider channel runs cooler. It is written as an adaptive secant with backtracking, overshoot damping and a step fraction ramping from 0.01 to 40 per cent with distance from target, capped at fifty iterations, to a tolerance of one part in ten thousand of the target wall temperature.

### Validation status

**Not validated, and there is nothing available to validate it against.** No published case states a channel radius distribution alongside the conditions that produced it. What can be claimed is internal: the loop converges to the requested wall temperature within its tolerance where the bounds allow, and reports the bound it hit where they do not.

It inherits every disclosure of the model it converges against. The coolant-side correlation is unvalidated, so a channel sized this way is sized against an unvalidated number however tightly the loop converges. That is stated in the module rather than left to be inferred.

### Not acted on

Two things visible from the extraction that would change numbers, and so belong with a decision rather than with a move:

- **The search is unbracketed** on a function that is known to be monotone. A bracketed method would be both faster and more robust, and would remove the iteration ceiling as a failure mode.
- **The area-basis difference from Stage 2 feeds this loop.** Flow area sets coolant velocity, velocity sets Reynolds number, and the correlation reads both, so the 0.19 per cent offset between how the two channel families measure area propagates into the radius the loop converges on.

---

## Stage 4: the channel build

Everything left in `generateRegenChannels` moved to [regenChannels.py](../regenChannels.py), 1,205 lines: the volute interfaces, the channel centerline and its wrapping, the printability audit, the three-dimensional sweep and the jacket. The method went from 2,185 lines to 32.

This stage was a different shape from the three before it. The remaining block read 70 attributes and wrote 48, across five nested functions that all work on the same arrays. Splitting that across three modules would have produced three modules sharing one mutable state, which is worse than one, so the whole build moved as a unit behind a single `RegenChannelState`. Its fields are grouped by how the build uses them: what it reads and does not change, what it works on in place, and what it produces outright.

**The geometry and sizing inputs are derived inside the build rather than passed in.** Both depend on arrays the build itself produces: the sizing solve works on the regen section after the volute interfaces have trimmed it, and the cross-section builder reads the printability stations and the wall point cloud as they are filled in. Building them up front captured the state before those steps ran, which the harness caught as an empty contour.

### Defects found

**The channel validator's guards were vacuous.** Written as `hasattr(self, 'nChannel')` against an object whose attributes `setInputs` always sets, so every guard was true and the check did nothing.

**Two fields were reached by name and lost.** `_specified(state, 'coolant')` passes its field as a string, which a scan for attribute access cannot see, so `coolant` was never declared on the state and the validator refused a configuration that plainly had one. The same class of gap dropped nine of the sizing solve's outputs, which the build copies onto its state by name: `coolantExitPressure` and the wall property curves among them reached the volute sizing as empty arrays. Both are now tests rather than fixed instances, and the second is a structural one -- everything `channelSizingOutputs` names must appear in `regenChannelOutputs`, checked rather than kept in step by hand.

**`revolveContour` was resolving through a wildcard import.** Nested in the class it came in through `from utils import *`; as a module it had to be named, and the unresolved-name audit is what named it.

---

## The validators, consolidated

Four validators totalling 1,278 lines enforced 124 rules, about ten lines of hand-written branch per rule, in four copies of the same shapes. Three of the four were wrong.

They are now one engine, [validation.py](../validation.py), and four rule tables that sit beside the code they guard.

|                      | before          | after                         |
| -------------------- | --------------- | ----------------------------- |
| Converging section   | 719 lines       | 33 rules                      |
| Heat transfer        | 289 lines       | 31 rules                      |
| Channel definition   | 208 lines       | 12 rules                      |
| Volute prerequisites | 62 lines        | 3 rules                       |
| Engine               | --              | 462 lines                     |
| **Total**      | **1,278** | **380 plus one engine** |

A rule is data: a field, a kind, a range, and optionally a predicate saying when it applies. The checker walks the table in order and reports the first failure, so a table reads from the most basic requirement to the most specific. The same table checks an object, a state dataclass or the heat transfer input dictionary, because the reader handles all three.

### Why the copies drifted

The range quoted in each message was a string typed beside the comparison that enforced it, free to disagree with it. `validRange='Float >= 0.5e-3 [m]'` sat next to `if value < 0.0005`, and nothing held them together. The range text is now generated from the rule, so there is one number.

### What changed as a result

Stating each rule exactly meant three were found to have been stated wrongly:

- **Presence checks now check presence.** Every `hasattr` guard was already true. A configuration leaves a field unset in three ways depending on which reader loaded it, and `specified` treats all three the same: absent, `None`, and the NaN `setInputs` produces from a null entry.
- **Types are enforced where they were assumed.** A boolean no longer passes as a number, so `chamberPressure: true` is refused rather than becoming 1 Pa. Infinity is refused wherever a finite value is meant.
- **Array lengths agree by rule.** The old validators checked lengths in some places and not others.

One rule was deliberately made stricter: the volute check tested only the last channel radius, and now tests every one. The sizing solve bounds every radius below by `minChannelRadius`, so the two cannot differ in practice.

All three reference cases remain bit-identical.

### What a validator is for, and what a test is for

They answer different questions. A test asks whether the code is right, against fixtures the author chose. A validator asks whether *this* configuration is usable, about numbers the author never saw. Neither substitutes for the other, and the case for keeping validators is what happens without one: an unset flute helix angle surfaced as `ValueError: data must be finite` inside a spatial index, a hundred lines from the field that caused it.

What was not worth keeping was the form. A rule table can be read at a glance and held against the state it guards by a test; 86 branches with no tests could only be checked by running them, which is why three of the four had rotted.

---

## Stages 5 to 8: the rest of it

The remaining stages went the same way, each held to bit-identity against the reference cases before the next began.

| Stage | Moved to                                             | Lines    | Was                                                                |
| ----- | ---------------------------------------------------- | -------- | ------------------------------------------------------------------ |
| 5     | [volutes.py](../volutes.py)                           | 798      | `generateRegenVolutes`, 545 lines, 80 reads and 36 writes        |
| 6     | [chamber.py](../chamber.py)                           | 797      | `convergingSection` and `_prependCombustionChamber`, 510 lines |
| 7     | [regenStations.py](../regenStations.py)               | 754      | `truncateForRegen`, 591 lines                                    |
| 8     | [config.py](../config.py), [exports.py](../exports.py) | 793, 198 | `setInputs` and the four export methods                          |
| 8     | [contour.py](../contour.py)                           | +231     | `pressureMatchTruncatedIdealContour`, the outer design solve     |
| 8     | [plume.py](../plume.py)                               | +470     | `plumeStructure`, `plumeCharacteristicSeed` and `plumeField` |

### The by-name gap, four times

The same class of defect appeared four times and is worth naming, because a static read of a module cannot see it.

A field reached through a string rather than through attribute syntax is invisible to a scan for `state.something`:

```python
_specified(state, 'coolant')          # a string argument
getattr(self, 'xNozzleWall', [])      # a string argument
setattr(state, name, value)           # a name computed at runtime
```

| Where                                                | What it cost                                                                                                                       |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `coolant` on the channel state                     | The validator refused a configuration that plainly carried a coolant                                                               |
| Nine sizing outputs, copied by`setattr`            | The return volute was sized on empty arrays                                                                                        |
| `chamberLength` and `Lstar` on the chamber state | Would have read`None` where a chamber length was given                                                                           |
| Nine plume fields, all read through`getattr`       | An attribute scan reported`plumeStructure` as reading nothing; it reads nine, and the plume structure would have come back empty |

Three of the four were caught by an audit before the code was wired in, once the audit was widened to collect all three forms. The fourth was caught by the harness. None would have been caught by reading the code.

### Text that was wrong

Two plume notes said "self" where they meant "jet":

> the Summerfield criterion of 1.75: **the self is** very likely separated internally at this altitude

> even though the **self pressure ratio** is above its onset threshold

These are the notes attached to a plume structure when the nozzle is running separated, which is to say the ones an engineer reads to decide whether the result means anything. Almost certainly collateral from an earlier rename. Corrected.

### A builder that raised on a fresh object

`channelSizingState` was the one state builder written out field by field rather than filled by name, and it read `maxWallTemperature` and eight other fields that only exist once a configuration has been loaded. On a fresh `Nozzle` it raised. In practice it is only called after `setInputs`, which is why nothing had hit it. Made consistent with the others.

---

## Where it ended

`Nozzle.py` went from 12,528 lines at the start of the contour work, through 9,261 at the start of this one, to **1,648**.

| Module                 | Lines | Holds                                                      |
| ---------------------- | ----- | ---------------------------------------------------------- |
| `utils.py`           | 3,629 | Fluid properties, geometry helpers, the error hierarchy    |
| `plume.py`           | 2,691 | Correlations, the free-jet lattice, the march past the lip |
| `Volute.py`          | 2,519 | The three volute cross-section families                    |
| `regenThermal.py`    | 2,026 | Bartz, Gnielinski, the fluted blend, the views             |
| `contour.py`         | 1,839 | The truncated ideal solve and the outer design solve       |
| `Nozzle.py`          | 1,648 | The facade                                                 |
| `regenChannels.py`   | 1,205 | The jacket build                                           |
| `ceaInterface.py`    | 1,026 | Thermochemistry                                            |
| `channelSizing.py`   | 994   | The dynamic channel radius solve                           |
| `channelGeometry.py` | 801   | Cross sections and the transport frame                     |
| `volutes.py`         | 798   | Inlet and return scrolls, walls, print supports            |
| `chamber.py`         | 797   | Combustion chamber and converging section                  |
| `config.py`          | 793   | The three configuration readers                            |
| `regenStations.py`   | 754   | The regen split and station properties                     |
| `figures.py`         | 664   | One figure description per view                            |
| `validation.py`      | 462   | Rule tables and one checker                                |
| `materials.py`       | 460   | Wall alloy property curves                                 |
| `characteristics.py` | 421   | The method of characteristics unit processes               |
| `gasDynamics.py`     | 297   | Isentropic relations and Prandtl-Meyer                     |
| `contourKernel.py`   | 286   | Rao arcs and Sauer's starting line                         |
| `keepOut.py`         | 225   | The chamber closure envelope                               |
| `exports.py`         | 198   | Contours, geometry, exhaust properties, the pickle         |
| `units.py`           | 159   | Conversions and the standard atmosphere                    |

### What is left in the facade

1,128 lines across 28 methods:

- **332** are `__init__`, the object's own state declaration
- **~470** are state builders, each assembling the inputs one module needs
- **~250** are facade methods: build a state, call a module, copy the result back
- **75** are `generateNozzle`, the orchestration
- The largest method that is not `__init__` is 78 lines, and it is a facade

### How that is held

The claim that `Nozzle` is a facade is structural, so it is checked structurally in [tests/testFacade.py](../../../tests/testFacade.py) rather than asserted here. Eighty checks:

- No module imports `Nozzle`, and none reaches `self` outside its own classes, by attribute or by name.
- No facade method contains a loop, other than the copy-back over an outputs tuple, and none contains a multiplication, division, power or subtraction. That is a stronger statement than a line count.
- Every state object is complete in both directions: every field reached is declared, and a fresh `Nozzle` seeds every field declared.
- Every output tuple names declared fields.
- Output resolves through one hook, the repository root holds no generated file, and every override in the showcase and the GUI targets that hook rather than the repository root.

### Verification

534 tests pass, from 285 at the start of this effort. All three reference cases are bit-identical to their baselines. Every showcase figure regenerates byte-identically.

```bash
python -m pytest                            # the suite, including the closing audits
python tests/regressionHarness.py --compare # bit-identity on all three reference cases
```

---

## Author's Information

Sean Bowman, Director of Propulsion, Vaya Space.
