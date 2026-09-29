# Plume development: state of play

A record of where the plume solver stands, written to be picked up cold. It covers what exists, what is validated and against what, what is broken, and the findings that cost the most to establish and should not be rediscovered.

The station marcher is now the product face. The characteristic march that used to hold that role stalled on every bell contour, and an envelope gate written for it refused every divergent exit, so the shipped nozzle could not produce a plume at all. Both are gone. What replaced them draws a real plume for the shipped contour, over a short reach, and reports what that reach costs.

## Where the code is

`src/NOVA/stationMarch.py` is the solver. It marches the plume on planes normal to the axis, so the data line cannot rotate into a characteristic direction and points stay at fixed fractions of the local jet radius as the jet opens out. `solveStationField` is its product face and `Nozzle.plumeField` calls it.

`src/NOVA/plume.py` keeps everything else: the correlations in `plumeStructure`, which place the jet boundary, the shock cell spacing and the Mach disk from published fits and solve nothing; the TN D-2327 lattice; the `PlumeFlow` and `PlumePoint` primitives the station marcher imports rather than transcribes; and `solvePlumeMarch`, the characteristic march, which is retained as a primitive and is no longer anything's product face.

`plume.solvePlumeField`, the 217-line characteristic-march product face, is deleted.

The dependency runs one way, `stationMarch` importing `plume`, so the two cannot drift apart on the physics and there is no cycle.

Tests are `tests/testPlume.py`, `tests/testPlumeMarch.py`, `tests/testPlumeField.py` and `tests/testCharacteristics.py`. `tests/testDirectCharacteristics.py` covers the forward contour march the plume seeds from.

## The shipped envelope

`Nozzle.plumeField(ambientPressure, reach = 2.0)` admits a case on seven conditions: a plume structure exists; the exit Mach number lies in 1.5 to 5.0; `Pe/Pa` is at or above the Summerfield criterion of 0.4, below which the nozzle separates internally and no attached plume model describes it; the contour carries a characteristic mesh, which a conical one does not; the free boundary is supersonic; a compressed lip passes the weak-shock bound below; and the march returned at least ten nodes with a finite mass drift. Each refusal writes its reason into `notes`.

The wall angle gate is gone. It refused anything diverging past half a degree, which is every bell, and it existed because the characteristic march solved a wedge near the boundary and never reached the center line on a divergent exit. The station marcher spans the jet at every station, so the condition it guarded against does not arise.

`reach` is an input because it trades picture against accuracy, and the default is short on purpose. Whatever is asked for, the drift is measured and returned in `massDriftWorst`, and `trustworthy` is False whenever it exceeds `plumeFieldDriftTolerance`, one per cent.

### A compressed lip is admitted as a bounded approximation

Below a lip ratio of one the jet is compressed rather than expanded to reach ambient, which physically means an oblique shock off the lip. The scheme turns the flow isentropically instead, which is exact only in the limit of vanishing shock strength, so it is admitted only while the shock it stands in for is weak: `lipShockLossLimit` refuses past one per cent of stagnation pressure destroyed, and the loss is returned in `lipShockLoss` either way.

On the shipped contour that bound never binds, because the nozzle separates internally first. Separation is at a lip ratio of 0.704, where the shock would have cost 0.58 per cent. Every attached condition this engine can reach is therefore admitted.

### The pressure gate reads a different pressure than the march does

`plumeFieldMaxPressureRatio` tests `exitPressureRatio`, built from the one-dimensional design exit state. The free boundary the march imposes is at the lip. On a truncated contour those differ by the truncation, so a one-dimensional ratio of 2.0 is a lip ratio of 3.52 on this nozzle. Nothing reaches that today because other gates refuse first, but the mismatch is real and is the kind of thing that returns.

## What the solver is good for

Two lip radii, at a lip ratio near one, to better than half a per cent and converging.

That is a narrow window and it is not nothing: base heating and plume impingement are near-field questions. Everything below is the evidence for the number and for its limits.

| Family | drift at 2 lip radii | conserves |
|---|---|---|
| truncated ideal | -0.72 % | yes |
| thrust-optimized parabola | -5.53 % | **no** |
| thrust-optimized contour | -0.84 % | yes |
| conical | no mesh, refused | -- |

## What is validated, and against what

The scheme is **verified** against an exact spherical source flow in `stationMarchVerification.py`: every unit process runs at second order, 1.94 to 2.00 observed, and the accumulated mass drift over a marched length at first, which is what a second-order step over a step count rising as its inverse gives. That establishes the discretization solves the equations it claims to and says nothing about the physics.

It **fails** the one published interior field available, NASA TR R-6 table II, a dense characteristic net for a near-sonic exit at a jet static pressure ratio of 2. The center-line wave is over-predicted by 7.8 per cent of its own amplitude rms, the error does not converge with resolution, and neither the jet boundary nor mass conservation shows it. That report computed table II to establish exactly this, that errors near the axis may have negligibly small effects on the boundary shape, so a solver validated on its boundary is not validated.

Mass continuity is the only quality measure available at an operating point with no reference to compare against, and it is the one wired into the envelope.

## What is open

**Shock capturing remains the long pole.** The scheme carries one stagnation pressure for the whole field, so it describes no shock. Above a jet static pressure ratio of about 2 the compressions reflected from the boundary have coalesced, by Prandtl and by TR R-6 independently, and an isentropic net is not defensible past that whatever it reports.

**The thrust-optimized parabola's plume does not conserve.** It loses 5.53 per cent over two lip radii where the truncated ideal contour loses 0.72. The fold guard in the forward contour march cleaned its interior without moving this at all, so whatever its exit plane hands the march is a separate problem and is not the folded nodes.

**A cone has no marched plume.** There is no characteristic mesh to continue, so the correlated structure stands in. Closing it means solving the cone's interior with the method of characteristics, which `directCharacteristics.marchPrescribedWall` could do today on a prescribed wall.

**`machDiskDiameter` returns a disk wider than the jet.** The fit `D_MD/D_e = 1.78 log10(NPR) - 0.98` is applied with no upper bound, and at the pressure ratios this engine runs it returns a disk radius of 4.07 to 5.32 lip radii against a fully expanded jet radius of 1.31 to 2.42. The location correlation beside it is sound. Either bound it against the fully expanded jet diameter and say what the bound is, or refuse to report a diameter above the fit range.

## Findings worth not rediscovering

**Pe/Pa names two different numbers on a truncated contour.** The one-dimensional exit state and the lip state differ by the truncation: 14.0 kPa at Mach 4.223 against 24.6 kPa at Mach 3.797 on the shipped nozzle, a factor of 1.760. Correlations are written in the one-dimensional ratio, the march's free boundary is applied at the lip, and both are correct for what they describe. Any pressure ratio quoted anywhere has to say which one it is.

**The march holds a bell exit until the lip fan reaches the axis.** At a lip ratio of 1.5 the error at two lip radii falls 0.334, 0.199 and 0.117 per cent across 81, 161 and 321 station points, and at three radii 0.638, 0.496 and 0.434. It then hits a negative excursion of about 1.9 per cent whose location does not move with the mesh: x/rLip 4.40, 4.36 and 4.40 at the three resolutions. A location fixed under refinement is a feature of the flow rather than a property of the grid, and the center line says which feature. Its Mach number holds 4.2033 to four figures out to four lip radii, then rises to 4.758 and collapses to 3.392.

**Read the drift at the station, never as a running worst over a reach.** It recovers through zero near six lip radii before running away, so a running worst repeats one excursion in every row past it and hides where the error is.

**The error is carried on the wave fronts, not spread through the field.** Contouring the continuity residual, which is the local form of the quantity the drift integrates, leaves the jet interior clean and puts the entire residual on the two fronts leaving the lip and on the spot where they converge on the center line. Along each front it alternates in sign, which is dispersive error on an under-resolved steep feature rather than diffusion. The decomposition closes: integrated from the exit plane it tracks the reported drift to 0.049 percentage points at every station.

**Over thirty-six lip radii the jet runs four cells and the error is spent at the foci.** Foci sit at 5.5, 14.3, 23.7 and 33.3 lip radii, a cell every 9.3. The drift is spent on the outward leg of each cell, from the axis focus out to the boundary pinch, and partly recovered on the leg back in, netting +4.65, +5.50 and +2.00 percentage points across the three complete cells. The measured cell is 9.3 lip radii against 12.0 from Prandtl, 22 per cent short, which is measured on a solution the mass loss says is wrong and so is not evidence either way about the correlation.

**The usable band in back pressure is bounded at both ends, and only one end refuses loudly.** Below a lip ratio of about 0.68 the march refuses on the lip shock bound. Above, it keeps returning `maxLength` while the free boundary collapses onto the axis, between lip ratios of 1.8 and 3 and again below 0.8, or sheds mass steadily through one long expansion above 4. Nothing in the return value flags either. At two lip radii the drift stays under one per cent at every admitted ratio, compressed and expanded alike, so the usable product is a short plume rather than a whole one.

**A front cannot be seeded from the march's own lines.** Those lines are first-family characteristics: 250 of 250 neighbouring pairs lie along the very characteristic the advance would cross against its neighbour's, so the intersection returns a point already on the front. Any working front has to start from a station. A test records this.

**Lip to first crest is not the wavelength.** The lip fan throws the boundary wide before the pattern settles, so the first crest sits about ten per cent beyond half a period. Measuring the cell that way reads consistently long and was for some time mistaken for a physical discrepancy.

**Grid convergence and reach are confounded.** Refining the mesh improves conservation monotonically and worsens the apparent period agreement, because a finer mesh costs reach, fewer cells get averaged, and early cells are shorter. Any period quoted has to say how many cells it averaged.

**Use the mesh's gamma, not the exit gamma.** `plumeStructure` reports CEA's exit gamma because that is the better number for a correlation evaluated at the exit. The characteristic mesh is built on the chamber gamma. Reading mesh Mach numbers under a different ratio of specific heats makes the state discontinuous at the exit plane and destroys conservation: on the worked case it put the exit flux 150 per cent above the choked throat flow.

**The exit plane must be read where the mesh crosses it, not near it.** Gathering every node within a tolerance of the exit abscissa and sorting the cloud by radius maps an axial variation onto the radial coordinate. On the shipped nozzle all forty gathered nodes spanned 31 mm of a nozzle whose exit is at 800 mm, and the profile sawtoothed by 0.4 degrees in flow angle against a Prandtl-Meyer turn of 0.62 degrees. Interpolating each mesh row to where it crosses gives a profile that is monotone in both Mach number and flow angle, which is what a truncated ideal contour leaves.

**A single node landing on the exit plane is not a station.** The crossing search takes an exact-match branch when nodes lie within rounding of the exit abscissa. Taking it on one node discards that block's interpolated crossings: a thrust-optimized parabola puts exactly one node there and lost 44 crossings behind it, which is why both optimized families reported no readable exit plane at all. The branch now requires `exitPlaneMinimumNodes`.

**Two bookkeeping defects, both of which looked like physics.** Lines grew by one point per line until the march drowned in its own mesh and the center line stopped advancing; TN D-2327 counts the line length down rather than up. And `outsideBoundary` once extrapolated the unknown boundary from the anchor's own flow angle, which in recompression rejected valid points. Neither was an entropy problem, and both were found by asking what a case with no shock in it was doing.

## Reproducing

Run from the NOVA root with `C:\Users\seanb\miniconda3\python.exe`.

```text
python -m pytest tests/testPlume.py tests/testPlumeMarch.py tests/testPlumeField.py tests/testCharacteristics.py
python experimental/convergeMarch.py             # grid convergence of the characteristic march
python experimental/exitPressureConvention.py    # lip against one-dimensional exit, and reach
python experimental/stationMarchErrorField.py    # the error contoured as a field
python experimental/stationMarchLongField.py     # the Mach field over four cells
python experimental/stationMarchAmbientSweep.py  # where the scheme refuses, works and fails quietly
python experimental/plumeShockAnatomy.py         # the shock structure, labelled
python featureShowcase/buildPlumeSweep.py        # the animation across the usable band
python featureShowcase/verifyContour.py          # contour against its references
```

`featureShowcase/plumeCellTrain.png` is the validated case and the one to look at first.
