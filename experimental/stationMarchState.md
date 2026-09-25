# Station marching: state of play

A record of the plume solver that prescribes its data line, written to be picked up cold. It exists, it marches, and it is not yet validated. This document is what works, what does not, and the staged references it has to pass before anything in the package reads it.

The goal it serves: extend the nozzle interior solution past the lip to give the jet boundary and the interior field, on a method that can be held against measurement.

## Why a second solver

`NOVA.plume.solvePlumeMarch` marches the characteristics themselves and the mesh goes where they take it. It is validated where it survives, reproducing Prandtl's cell period within half a per cent at a parallel exit and TN D-2327's worked cases to a tenth, and it does not survive a divergent exit, which is every bell contour.

Diagnosing why produced a measurement rather than a suspicion. At the point the front-advancing variant stalls on a mildly underexpanded jet, the data line lies within **0.00 degrees** of the first-family characteristic direction over part of its length, the point spacing along it spans **114 to 1**, and the boundary has run to two lip radii while the center line has reached a tenth of one. A data line lying on a characteristic carries no information across itself, so the unit process returns points already on the line and the march ends.

That is not a tuning problem. It is what happens when the mesh is allowed to choose the data line.

## What this solver does instead

Stations are planes normal to the axis. The points on each sit at fixed fractions of the local jet radius, and the flow at those prescribed positions is solved by tracing each point's two characteristics back to the previous station and interpolating the state at their feet. The line can never rotate into a characteristic, and resolution is held as the plume opens out.

The compatibility relations, the axisymmetric source terms and the velocity formulation are imported from `NOVA.plume` rather than transcribed, so the two solvers cannot drift apart on the physics. Only which quantities are known changes: the characteristic march knows the parents and solves for the position, this knows the position and solves for the parents.

Three things follow that the characteristic march does not give:

- the jet boundary is one point per station, so it is an output rather than a reconstruction from scattered nodes
- the interior is a structured grid, station by radial fraction, which contours directly
- a divergent exit stops being a special case, because a station is normal to the axis whatever angle the flow leaves the lip at

The cost is an interpolation at every station, which the characteristic march does not pay.

## What works

**It marches.** On a uniform parallel exit at Mach 3 and a jet static pressure ratio of 1.5, it runs the full 14 lip radii asked of it, against roughly 2 for the front-advancing variant with its boundary defect fixed, and about 16 for the characteristic march.

**The boundary turns over.** A complete first cell, with the crest at 5.09 lip radii, which is what a wavelength would have to be measured between and what neither existing variant reached on this case.

**The boundary shape is grid converged.** First crest at 5.088, 5.094 and 5.091 lip radii at 41, 81 and 161 points across the jet. Four times the resolution moves it by a tenth of a per cent.

## What does not work

**It loses mass.** About 0.8 per cent of the axial mass flow over 8 lip radii, and the loss is real rather than a measurement artefact: re-integrating the same solved stations on a monotone fit at 4001 samples instead of the station's own trapezoid gives -0.9109 per cent against -0.9128, so the quadrature is not what is wrong.

It converges only weakly with radial resolution, -0.91, -0.80 and -0.74 per cent at 41, 81 and 161 points, and not at all with step size, -0.80, -0.87 and -0.72 per cent at half, a quarter and an eighth of the step limit. A defect that ignores both refinements is a formulation error rather than a discretisation one. The characteristic march holds 0.03 per cent on the same case, so this is the gap to close.

Ruled out so far: characteristic feet landing outside the station and being clamped, which does not happen once in a full march, and the quadrature, above. The remaining suspects are the axis point, which closes on a single relation with an axisymmetric source evaluated at a foot whose radius shrinks with the step, and the free boundary point, whose radius advances on a mean flow angle and therefore sets the enclosed area.

**No second crest.** One crest within 14 lip radii, where Prandtl's cell length for this jet, 7.39, would put a second near 12.5. Whether the march is damping the wave or the first crest is simply late is not established, and the plume notes already record that lip to first crest is not the wavelength.

**It fails above a pressure ratio of about 1.5.** At 2.0 the march ends at 7.3 lip radii with a station that cannot be solved. That is inside the envelope where an isentropic net is still defensible, so it is a defect rather than the physics running out.

## The staged references

Stages 1 to 3 need no data that is not already in hand. Stage 4 needs manual transcription from a scanned report.

1. **Uniform parallel exit, Pe/Pa 1.05 to 2.** Mass conservation, and the cell period against Prandtl. The characteristic march holds 0.03 per cent and half a per cent here, so it is a like-for-like target rather than a new claim. **Open**: conservation is 0.8 per cent and no period has been measured.
2. **NASA TN D-2327's worked cases.** Lip fan and leading characteristic to the center line, which the characteristic march reproduces to a tenth of a per cent. **Not started.**
3. **A divergent exit.** TR R-6 measures divergence angle as a small effect on wavelength over 0 to 20 degrees; the characteristic march contradicts it at -25 per cent by 5 degrees and -34 by 11. Reproducing the insensitivity is the falsifiable test that this solver is better rather than merely different. **Not started.**
4. **TR R-6's interior field and boundary shape.** Table II tabulates a characteristic flow field per nozzle and figures 8a to 8g give boundaries. This is the only interior-field reference available and it has not been transcribed. **Not started.**

Above a jet static pressure ratio of about 2, no isentropic net is defensible, by Prandtl's cell length and by TR R-6 independently, because the compression waves reflected from the boundary have coalesced into a shock the net does not carry. That ceiling belongs to the physics and applies here unchanged.

## Promotion

Nothing in the package imports this module. It moves into `src/NOVA` when stages 1 to 3 pass, and not before.

## Reproducing

Run from the NOVA root with `C:\Users\seanb\miniconda3\python.exe`.

```
python -c "import sys; sys.path.insert(0, 'experimental'); import stationMarch"
```

A march on the case above is `solveStationMarch(flow, uniformStation(flow, 3.0, 1.0, 81), ambient)`, with `ambient` the exit static pressure divided by the jet static pressure ratio. The result carries the stations, the boundary and the per-station mass drift.
