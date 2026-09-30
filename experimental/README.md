# Experimental

Work that is not part of the shipped tool: research records for methods still being established,
and features taken out of the package that are worth keeping the source of.

| Module | What it is |
|--------|-----------|
| `tnd2327.py`, `convergeMarch.py`, `convergeRun.py`, `jetNetPrototype.py` | The MOC free-jet plume interior study, described below |
| `stationMarch.py` | The plume solved on prescribed stations rather than on the characteristics, described below |
| `stationMarchVerification.py` | The station marcher held against an exact spherical source flow |
| `exitPressureConvention.py` | The two exit pressures a truncated contour leaves, and the reach the march holds over |
| `stationMarchErrorField.py` | The mass continuity error contoured as a field, to locate it in the jet |
| `stationMarchLongField.py` | The Mach field of the same case over four shock cells |
| `plumeShockAnatomy.py` | The shock structure of an underexpanded jet, labelled, beside what the solver produces |
| `sunkenNozzle.py` | The sunken throat converging section, removed from the package |
| `flutedChannels.py` | Spirally fluted cooling channels and their blended correlation, removed from the package |
| `keepOut.py` | The keep-out envelope behind the chamber, which the sunken throat wraps around, removed from the package |
| `eggVolute.py` | The egg volute cross section, removed from the package |
| `stepExport.py` | STEP export of every nozzle component as exact surfaces, described below |
| `plumeDevelopmentState.md` | Where the plume solver stands, written to be picked up cold |
| `coolingModelState.md` | Where the film, radiative and extension cooling work stands, and what is open |
| `internalShockState.md` | How the shock inside an optimized contour is detected and captured, and what a correct rotational solve would take |
| `gasModelState.md` | What the exhaust is modeled as, what local equilibrium properties would take, and where finite-rate chemistry sits beyond them |

## Sunken throat converging section

`sunkenNozzle.py` holds the converging section that recesses the throat inside the chamber and
wraps the wall back around the closure behind it. It was a second `contourType` in `chamber.py`
until it moved here; the package now builds the traditional section only.

It builds. It did not until `arcSpline` was made shape preserving: the stitch presents an
isolated conic control point between two dense runs, and the unconstrained cubic that `arcSpline`
used to fit rang across it and drove sixteen of sixty points below the throat, which has no
subsonic solution. Driven against the shipped regenerative example it now returns a closed
contour with no point below the throat and a near-wall Mach number running 0.117 to 3.787.

That does not make it a validated design. Nothing here has been checked against a reference
sunken nozzle, and the cooling correlations carry no correction for a recessed throat. The module
docstring says what wiring it back into the package would take.

## Spirally fluted channels

`flutedChannels.py` holds the fluted cooling channel: a circle modulated by helical flutes,
compressed toward a circle on the hot-wall side, blended to a plain circle at each volute
interface, and rated with a fifty-fifty blend of Gnielinski and the spirally fluted tube
correlation of Webb and Kim. It was a second `channelType` in the package until it moved here.

The geometry builds and was checked against the package implementation before removal: identical
areas and interface blend on a 60 station channel, and flutes that turn at the requested rate.
The correlation is the reason it is here. No source states the blend or its roughness
amplification, the documentation and the code disagreed on its weights, and no measurement is
available to set it against. The module docstring lists what reinstating it would take.

## Keep-out envelope

`keepOut.py` holds the quarter ellipse of revolution that described the volume behind a chamber
closure, drawn when the jacket's return turned around on the converging section of a hybrid
nozzle and routed behind a closure NOVA did not generate. NOVA jackets its own chamber to the
injector face, where the outlet volute sits, so the package does not build, draw or export it.

`sunkenNozzle.py` is its one geometric consumer and imports it from beside itself. Nothing ever
checked geometry against it: `packingClearance` had no caller. The module docstring records a
default-placement defect, a null axial offset landing the envelope on the throat plane, and what
reinstating it would take.

## Egg volute cross section

`eggVolute.py` holds the egg cross section for a volute scroll: two circular arcs joined by a
Bezier tip whose control magnitudes follow the shoulder tangents, with `eggPointiness` setting how
sharp the point is. It was a third `crossSectionType` on `Volute` until it moved here, and the
package builds circles and squircles.

`EggVolute` subclasses the package `Volute`, so the section runs from here unchanged and any other
cross section passes through to the package. Its own dispatch predates the two scroll
topologies and carries neither: an egg is always drawn as a monotone taper over a full turn, so
`voluteScrollType` does not reach it.

The section solve is the reason it is here. Three of its branches, the ones handed an area rather
than a hydraulic diameter, test convergence with the inequality reversed, so they exit on the
first pass and keep an initial guess that uses an area as a length. The branches driven by
hydraulic diameter converge, by a fixed-step walk of a few micrometres per iteration.
`crossSectionResolution` is ignored, `scaledBy = 'momentum'` raises, and there is no printability
support or cross-section tilt. The module docstring lists what reinstating it would take.

## STEP export

`stepExport.py` writes every component of a finished nozzle to STEP as the exact surfaces it is
made of, rather than as the triangles `py2cad` produces. The walls become surfaces of
revolution, 151 entities for a wall that takes 9,702 facets as STL; the channels and
volutes become tensor-product B-spline surfaces interpolating the point grids NOVA already holds.

It writes ISO 10303-21 text directly and imports no CAD kernel. Every component is a tube, so
each file is one face with a seam walked twice and a closed curve at each end.

Run it standalone to reproduce its own verification:

```bash
python experimental/stepExport.py
```

That writes the revolved wall beside the module and the full component set into
`stepComponents/`, which is gitignored as regenerable output.

**One body per file, and no booleans.** Nothing is trimmed, unioned or intersected against
anything else, so assembling the jacket stays the CAD user's operation. That line is deliberate:
writing a surface is transcription, while trimming two surfaces against each other needs a
surface-surface intersection, which is the algorithm a B-rep kernel exists to provide. Adding
booleans later does not invalidate any of these surfaces, since a boolean wants bounded faces
and these are already bounded, valid and exact.

Every written component was read back with OpenCASCADE, which accepted all of them and returned
`True` from `BRepCheck_Analyzer` on each. The revolved wall has been opened in SolidWorks. Areas
match a closed-form reference to 5e-10 for the revolved case and 1e-7 for the swept case.
[docs/reports/stepExport_2026-09-20.md](../docs/reports/stepExport_2026-09-20.md) carries the
measurements, the seam study behind the fit, and what booleans would take.

## Station marching

`stationMarch.py` solves the same plume on planes normal to the axis instead of on the characteristics. Points sit at fixed fractions of the local jet radius and the flow at those prescribed positions is found by tracing each point's two characteristics back to the previous station, so the data line can never rotate into a characteristic direction and resolution is held as the jet opens out. The compatibility relations and the velocity formulation are `NOVA.plume`'s, imported rather than transcribed.

It exists because the characteristic march lets the mesh choose its data line, and measured at the point the front-advancing variant stalls that line has rotated to within 0.00 degrees of the first-family direction, with the spacing along it spanning 114 to 1. A data line lying on a characteristic carries no information across itself.

`stationMarchVerification.py` holds it against an exact spherical source flow, which is the one case where a unit process can be handed known data and its own error measured. Every process is second order and the accumulated march error is first, as a second-order step over a step count rising as its inverse must be.

`stationMarchFigures.py` draws what the scheme gives that the characteristic net does not: the boundary against the other solver over three shock cells, the interior Mach field as a contour, and the cell period against exit divergence angle. That last one is the falsifiable test. TR R-6 measures divergence as a small effect on the primary wavelength and the characteristic march makes it dominant at -24.6 per cent by five degrees; the station marcher reads +6.04 per cent there, and puts the first crest 52 per cent nearer the lip, which is what the characteristic march was measuring instead.

`stationMarchValidation.py` holds it against NASA TR R-6's table II, a dense characteristic net for a near-sonic exit at a jet static pressure ratio of 2 and the only published interior field available. It fails: the center-line wave is over-predicted by 7.8 per cent of its own amplitude rms, the error does not converge with resolution, and neither the jet boundary nor mass conservation shows it.

The same module then localizes the defect against the characteristic march, on a Mach 3 exit where both solvers survive. The disagreement is bimodal along the axis: a few tenths of a per cent of the wave amplitude between the foci of the cell train, and 58 to 62 per cent at them. At each focus the station marcher overshoots the peak by about a quarter and places it 0.057 lip radii early. The interior error belongs to the near-axis treatment at a converging wave, and a plume is a train of them. TR R-6 computed that table to establish exactly this, that errors near the axis may have negligibly small effects on the boundary shape, so a solver validated on its boundary is not validated.

`exitPressureConvention.py` prints the two exit states a truncated contour leaves and measures how far the march holds against the lip one. The one-dimensional design station and the lip differ by the truncation, 14.0 kPa against 24.6 kPa on the shipped nozzle, a factor of 1.760, so `Pe/Pa` names two numbers and the `plumeFieldMaxPressureRatio` gate tests the one the march does not use. The station table separates discretization error from the scheme's own: at a lip ratio of 1.5 the error at two lip radii falls from 0.334 to 0.117 per cent as the station goes from 81 points to 321, while the negative excursion near four radii holds at 1.9 per cent and sits at the same place on every mesh. The center-line Mach number locates that place, holding flat to four figures until four lip radii and then swinging by a quarter, so the excursion is the lip fan arriving at the axis. Refining the mesh buys accuracy from the exit plane to the first axis crossing and nothing past it.

`stationMarchErrorField.py` contours the mass continuity error as a field instead of reporting it per station. The local quantity is the residual of the continuity equation, d(rho u r)/dx + d(rho v r)/dr, whose integral over the region up to a station returns that station mass flux change, so the field is a decomposition of the drift rather than a proxy for it; the script checks the running integral against the reported drift at every station and closes to 0.049 percentage points, 2.7 per cent of the excursion. The result is that the jet interior is clean and the whole error sits on the two wave fronts leaving the lip and on the spot where they meet the center line. It is a wave-front and near-axis problem, not a diffuse accumulation.

`stationMarchLongField.py` draws the Mach field of that same case out to thirty-six lip radii, four shock cells, so the structure the error rides on sits beside the error itself. The two figures share a lip ratio, a solve and an axis in lip radii, so a position on one reads straight across to the other. The march holds all thirty-six without failing, 2122 stations, with the center line swinging between Mach 2.53 and 5.14.

`plumeShockAnatomy.py` is a reference sheet rather than a result. Its upper panel is a hand-drawn schematic of the canonical underexpanded jet with every feature named: the lip fan, the free boundary, the compressions the boundary reflects back in, the barrel shock they coalesce into, the triple point, the Mach disk, the reflected shock, the slip line and the subsonic pocket. The lower panel is the station march on the shipped nozzle with the same features located in the computed field, which is where the point lands: the compressions are there and converging, the scheme simply never lets them steepen, and the axis crossing it produces is the regular reflection that a strong enough jet replaces with a disk. It writes two files: `plumeShockAnatomy.png` carries the reasoning as prose blocks beneath the panels, and `plumeShockAnatomyPlain.png` is the same diagram with the callouts and nothing else.

`stationMarchState.md` is the handoff: what works, what does not, and the staged references it has to pass before anything in the package reads it. Nothing does, and stage 4 says nothing should until the interior error is bounded over the range NOVA designs for.

## MOC free-jet plume interior

This directory is the research record for the free-jet characteristic net of NASA TN D-2327,
*Comparisons of Experimental Free-jet Boundaries with Theoretical Results Obtained with the Method
of Characteristics*, Andrews, Craidon, Dennard and Vick, Langley Research Center, June 1964
(Appendix C), which carries the nozzle-interior MOC solver in `Nozzle.py` past the exit plane.

The implementation lives in `src/NOVA/Nozzle.py` and `tnd2327.py` is a shim onto it, so
there is one solver rather than two that drift apart. `Nozzle.plumeField` exposes it to the product
behind a validity envelope. The studies here drive the net directly instead, at operating points
well outside that envelope, which is what mapping where a formulation breaks down requires.

What follows is where it stands, what has been corrected against the FORTRAN, and what is still
wrong. The envelope in `Nozzle.py` is drawn from these numbers.

`plumeDevelopmentState.md` beside this file is the handoff: what is validated and against what,
what is open and in what order, and the findings that cost the most to establish. Read that first
if you are picking the plume work back up.

## Source of truth

The report carries complete FORTRAN listings, and they are the authority here rather than the
prose or the typeset equations:

| Program | What it is | Report page |
|---------|-----------|-------------|
| P-5433  | Corner expansion ray generator | 23 |
| P-5430  | Free jet characteristic network, main program | 38-42 |
| `GENL`  | General point subroutine | 43 |
| `CENTL` | Center-line point subroutine | 44 |
| `OFCNT` | One-point-off-center-line subroutine | 44 |
| `BNDRY` | Boundary point subroutine | 44 |
| `SAMFM` | Same-family (internal shock) point subroutine | 44-45 |
| `TEST`  | Characteristic crossing detection | 45-46 |

Every equation in `tnd2327.py` is transcribed directly from those subroutines. The FORTRAN
resolves three questions the typeset equations leave ambiguous.

### The axisymmetric source applies to corner rays

`GENL` computes `FLA = (B3*SIN(GTA)*D4)/B4` with no exemption for any point type, and P-5433
sets `XA=0.0` / `YA=-1.0` once and punches those same lip coordinates onto every ray card. So
eq (C9) is evaluated with the full ray length on the first line. Treating the corner rays as
two-dimensional (`l_A = 0`) contradicts the reference.

### The A array is the entire previous line

`MOVE C ARRAY` copies `DO 125 I=1,LINE`, which spans the leading-characteristic start point at
index 1, every general point, and the boundary point at the end. Point C on line j at index i
takes A from line j-1 at index i. Dropping the start point or the boundary point from the A
array shifts the indexing by one every line and makes the net inconsistent; the symptom is a
Mach number that grows without bound and scales linearly with the number of rays.

Statement 28 (`LINE = NRAY - 1`) follows from this: a line computes one general point per A
entry except the last, which anchors the boundary point.

### Line length is adaptive, not a fixed count

Statement 350 recomputes the line length from the number of points actually placed:

```fortran
350 LOOK=NC-1
    IF(LOOK-NRAY)352,353,356
352 NRAY=LOOK
353 NREFL=0
356 NREFL=LOOK-NRAY
370 LINE=NRAY+NREFL
```

General points are therefore generated until one falls outside the boundary streamline, which
is the "max boundary reached" condition that selects between the program's four modes. A fixed
count lets the line punch through the boundary, after which eq (C20) is evaluated against a
point far outside the jet and the boundary angle runs away through zero and positive.

## Pressure ratio convention

The report's `pr` is the jet static to ambient ratio `p_j/p_a`, not the total to ambient ratio.
For case 2 this is the difference between a boundary Mach number of 7.78 and of 19.70, and it
sets the plume scale. Convert with

```
p_a/p_0 = 1 / (pr * (1 + (gamma-1)/2 * M_j^2)^(gamma/(gamma-1)))
```

## Validation cases

| Case | M_j | theta_N | p_j/p_a | M_boundary | Lip turn | (r/r_j)max | at x/r_j |
|------|-----|---------|---------|-----------|----------|-----------|----------|
| 1 | 1.00 | 0 | 45 000 | 11.09 | 105.6 deg | 450 | 1 300 |
| 2 | 5.00 | 15.0 deg | 8 143 | 19.70 | 54.06 deg | 225 | 1 050 |
| 3 | 4.79 | 26.5 deg | 2 926 | 16.38 | 64.70 deg | 188 | 720 |

Case 1 is outside what this formulation can represent. Its lip turn exceeds 90 degrees, so
`tan(theta)` in eqs (C18) and (C19) selects the wrong branch and the boundary marches toward
the axis instead of away from it; separately, a sonic jet has a degenerate leading
characteristic, since `mu = 90` degrees puts every point of it in the exit plane. Cases 2 and 3
are the well-posed ones and are what `convergeRun.py` exercises.

## Status

Validated for a mildly underexpanded jet leaving a near-parallel exit, and not otherwise. That
band is what `Nozzle.plumeField` will solve; everything below is why the bounds sit where they do.

Eight defects have been corrected against the listings and three numerical mechanisms added.

| Fix | Symptom before | Source |
|-----|----------------|--------|
| A array is the whole previous line | Mach grew without bound, linearly with ray count (26, 124, 578, 1750, 5382) | `MOVE C ARRAY`, `DO 125 I=1,LINE` |
| `NA` incremented before the first `GENL` | Off-by-one in the A index every line | statements 102, 110 |
| `OFCNT` denominator is `GWA*D1 + GWB*D2` | A spurious factor of two halved the center-line weight | `OFCNT` |
| `OFCNT` applies when B is on the center line | The march ended the line instead of calling it | `OFCNT` signature |
| `pr` is jet static to ambient | Boundary Mach 7.78 instead of 19.70, plume scale wrong by 50x | report tables |
| Center-line approach sub-stepped in thirds | One center-line point per run; the march stalled after a single shock cell | statements 700, 740, 760 |
| `TEST` and `CROSS` written and driven | The internal shock was unreachable; `SAMFM` had no caller | statements 500-785, `CROSS` |
| Refinement floored away from the axis | Lines packed thousands of points inside 1e-4 of the axis and never reached the boundary | numerical, not from the report |
| Adaptive line refinement | Line length decayed from 40 points to 4, invalidating eq (C11) over a step | numerical, not from the report |
| Line budget | Lines grew without bound, so the march cost the square of the line count | numerical, not from the report |
| Boundary lookup by bisection | `np.interp` rebuilt an array from the boundary list once per point, an O(n^2) march | numerical, not from the report |

### The center-line march

`CENTL` projects a point's first-family characteristic onto the axis. Taken in one step from a
source point a rounding error off the axis it advances almost nothing, and the net stalls. The
report divides the approach into three, holding the source point for two sub-steps and landing the
true `CENTL` point on the third, where the source point is released forward by one. Interpolated
sub-step states carry x, mu and W independently.

With it the march runs. For M_j 3.0 at p_j/p_a 1.5 the number of center-line points goes from 1 to
843 and the boundary carries to x/r_j 8.62.

The branch is no longer chaotic. Perturbing the ambient pressure by one and two ulp leaves the run
identical: 1041 lines, 843 center-line points, boundary end 8.618720 in every case. The earlier
`axisOffset` workaround is gone, and with it the sensitivity that moved the answer from three
center-line points to one on a 4e-16 relative change.

### Grid convergence, and the limits of the earlier claim

Refinement splits any segment longer than a tenth of the local radius, with the radius floored at
two per cent of the line's own extent. Without that floor the criterion collapses on the axis and
packs the line so densely there that the next line spends every point it has beside the axis.

Convergence holds only over part of the parameter space, and the earlier claim that the net is
grid independent was drawn from too narrow a sweep. Sweeping corner rays and leading-characteristic
points together gives:

| Case | 30 rays, 400 leading | 45 rays, 600 leading | 60 rays, 800 leading | 90 rays, 1 200 leading |
|------|---------------------|---------------------|---------------------|-----------------------|
| 2, `(r/r_j)max` | 119.20 | 59.92 | 118.94 | 119.26 |
| 2, lines | 3 000 | 108 | 3 000 | 3 000 |
| 3, `(r/r_j)max` | 30.81 | 9.82 | 81.24 | 85.58 |
| 3, lines | 1 | 1 | 332 | 507 |
| 3, `M` max | 307.15 | 330.91 | 112.94 | 50.05 |

Case 2 repeats to three figures at 30, 60 and 90 rays and collapses at 45, where the march ends
after 108 lines without reaching the center line. Case 3 does not run at all below 60 rays: the
first line fails and the core Mach number reaches several hundred against a boundary Mach of 16.38.
Above that threshold it settles toward the low eighties, still short of the report by more than
half.

The net is therefore not grid independent in general. It is repeatable at settings that let the
march get started, and it fails outright at settings that do not. Running the same sweep against the
solver as it stood before the center-line and refinement work returns the same numbers to two
decimal places, so this fragility belongs to the formulation as transcribed rather than to the
sub-stepping or the refinement floor.

### Remaining error

| Case | M_j | theta_N | p_j/p_a | `(r/r_j)max` | Report | error | at x/r_j | Report | error |
|------|-----|---------|---------|-------------|--------|-------|----------|--------|-------|
| 2 | 5.00 | 15.0 deg | 8 143 | 119.20 | 225 | -47.0 % | 450.0 | 1 050 | -57.1 % |
| 3 | 4.79 | 26.5 deg | 2 926 | 81.24 | 188 | -56.8 % | 249.7 | 720 | -65.3 % |

The internal shock is now driven, and it does not close this gap. `TEST` fires six times over a
3 000 line run of case 2 and moves the maximum radius from 119.13 to 119.20.

The reason is that the net contains almost no converging first-family characteristics to find.
`CROSS` rejects a pair whose rays diverge, and through the expansion every pair does. Compression
only appears once the boundary has turned back toward the axis, which happens at x/r_j 450, and by
then the core has already reached M 60 against a boundary Mach of 19.70 and the plume is closing.
The recompression has to exist before the maximum to change where the maximum falls.

Reflection off the constant-pressure boundary is the physical source of those compressions, and
admitting the boundary point to the first-family sweep does not supply them: the maximum radius
moves from 119.13 to 118.97 and the run shortens. So the missing piece is not simply the shock point
solver, which is transcribed and correct against the listing, but the mechanism that generates
converging characteristics upstream of the boundary maximum.

### The divergent exit

The net is quantitatively defensible at a parallel exit and not at a divergent one, and NASA
TR R-6 is what establishes the difference rather than an absence of evidence.

Measured against Prandtl's first cell length at jet Mach 3 and a static pressure ratio of 1.5, as
the exit wall angle opens out:

| Exit wall angle | 0 deg | 2 deg | 5 deg | 8 deg | 11 deg | 18 deg |
|-----------------|-------|-------|-------|-------|--------|--------|
| Cell length error | +9.0 % | -8.4 % | -24.6 % | -31.3 % | -34.3 % | -36.1 % |
| Boundary points | 1 139 | 293 | 214 | 158 | 193 | 111 |

TR R-6 conclusion 1 measures the same effect experimentally and reports that divergence angle over
0 to 20 degrees has a small effect on the primary wavelength. The net makes it dominant, so this is
a defect rather than an unmapped region. The same report puts the ceiling on existing wavelength
methods at a jet static pressure ratio of about 2, which arrives at the ceiling in the shipped
envelope from an independent and experimental direction.

Part of the discrepancy is the measure and part is the march. Lip to first crest is not a
wavelength: a steeply diverging exit throws the boundary out early and brings the first crest
forward without changing the axial period. The period cannot be substituted for it, because with
divergence the net does not survive to a second crest, as the boundary point count above shows.

The exit plane is where this starts, and correcting it was necessary but not sufficient.

A truncated ideal contour does not leave a uniform exit plane. On the showcase nozzle the flow
leaves at 0 degrees and Mach 4.81 on the axis and at 14.1 degrees and Mach 4.04 at the wall.
Appendix A builds its leading characteristic from a source flow of half-angle theta_N, which for
that same nozzle puts Mach 8.10 on the axis. Every line of the march then starts from initial data
that is 68 per cent wrong in the core.

`freeJetInitialLine` replaces the construction with the exit plane of the contour solve, taken from
`Nozzle.plumeCharacteristicSeed`, and `solveNet` accepts it through `initialLine`. The march starts
from the nozzle solution rather than from an assumption about it, which is what makes the plume an
extension of the contour rather than a separate problem.

It is an improvement and it does not widen the envelope. At p_j/p_a 1.5 on the showcase nozzle the
boundary carries 68 points instead of 46 and the peak Mach number falls from 5.53 to 5.41, but the
boundary still does not turn over: the line runs out of points against a jet opening far faster
than the march advances along it. The remaining defect is in the march, not in what it starts from.

### To return to: the advancing front

The march computes one characteristic at a time, from a start point out to the boundary, which
leaves the center line trailing the boundary and the solved region shaped like a wedge. Advancing a
whole data line downstream together would remove that, and would remove the center-line restart and
its sub-stepping with it.

The obvious way of building one does not work, and the reason is worth keeping. Seeding a front
from the march's own lines cannot succeed, because those lines are first-family characteristics:
250 of 250 neighbouring pairs on one lie along the very characteristic the advance would cross
against its neighbour's, so the intersection returns a point already on the front. A front has to
be a station rather than a wave.

`Nozzle.solvePlumeFront` seeds from the exit plane instead and is marked NOT YET USABLE. It
advances, and stably, but stalls after about thirty steps having carried the boundary less than one
lip radius against the march's sixteen. The remaining problem is holding the front away from the
characteristic directions as it turns downstream. A test records the degeneracy so it is not
rediscovered.

### Shock cells

At mild pressure ratios the compression waves reflected from the jet boundary have not yet
coalesced into shocks, so the cell pattern is isentropic and the net resolves it with no shock
capturing at all. For M_j 3.0 at p_j/p_a 1.5 the first cell comes out cleanly: the flow leaves the
lip at M 3.00, the fan accelerates it to M 3.98, and the waves focus on the axis at x/r_j 3.2,
which is the first diamond node.

The march now carries to x/r_j 8.62 rather than stopping at 6.77, and it does so repeatably. It
still resolves one cell. The boundary reaches its maximum radius of 1.24 r_j and does not swell
again, which is the same behavior that limits the validation cases: without recompression upstream
of the maximum there is no second cell for the boundary to describe.

Run `convergeRun.py` for the current grid sweep. `featureShowcase/buildMocPlume.py` renders the
interior Mach field, with its error against the report stated on the figure.
