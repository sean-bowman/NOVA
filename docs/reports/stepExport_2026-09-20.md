# A STEP export strategy for py2cad

NOVA writes geometry as STL. That is a tessellation, and it is the wrong format for most of what the geometry is for: a CAD package cannot offset a faceted wall by a thickness, fillet it into a flange, or section it and get a smooth edge, because the curve that generated the facets is gone by the time the file is written.

`experimental/stepExport.py` now writes every component of a finished nozzle as exact STEP geometry, with no CAD kernel and no new dependency. The revolved walls come out as surfaces of revolution and the swept components as B-spline surfaces, one body per file. Every file is accepted by OpenCASCADE, passes `BRepCheck_Analyzer`, and interpolates its source points exactly. The revolved wall has been opened in SolidWorks.

The deliberate boundary is booleans. Each component is written as its own body and nothing is trimmed, unioned or intersected against anything else, so assembling the jacket remains the CAD user's operation. [What booleans would take](#future-improvement-booleans) is recorded below.

---

## STL and STEP are not the same job

`py2cad` takes an (m, n) surface mesh and writes two triangles per quad. Every NOVA surface reaches it the same way, as points sampled off a parametric object that has already been solved.

The temptation is to convert that mesh to STEP, since STEP can hold a faceted B-rep. It is the worst available option. A faceted STEP carries the same approximation as the STL, loses the compactness of the binary STL, and gains an entity graph of roughly 150,000 lines for the shipped contour, estimated at the fifteen to twenty entities a triangular `ADVANCED_FACE` needs once shared vertices and edges are counted. What it does not gain is a surface, so none of the CAD operations that motivated the export become available.

The geometry NOVA holds upstream of the mesh is the thing worth exporting. For the nozzle wall that is a 2D profile and an axis, which is precisely `SURFACE_OF_REVOLUTION`.

---

## Three routes, measured

Driven on the shipped showcase contour, 100 points from the chamber end to the exit, throat radius 50.6 mm, exit radius 318.3 mm.

| Route | Time | File size | What the file carries |
|---|---|---|---|
| Hand-written STEP | < 0.01 s | 10.7 kB | 151 entities, one `Geom_SurfaceOfRevolution` |
| build123d through OpenCASCADE | 9.48 s | 23.4 kB | 3 faces, one revolution and two planar caps |
| `py2cad` STL, today | 0.95 s | 473.8 kB | 9,702 facets, no surface |

The STEP file is 44 times smaller than the STL of the same wall and carries geometry the STL does not have at any size.

The 9.48 s for build123d is almost entirely import: the kernel alone costs 7.0 s to load, on top of 89.9 MB installed (OCP 87.3 MB, build123d 2.6 MB). That is the number that decides the dependency question. A 7 s import is tolerable in an export script and is not tolerable at package import, so a CAD kernel in NOVA has to be an optional extra loaded lazily inside the function that needs it, never a module-level import.

build123d installed cleanly from pip on Python 3.10 under Windows, so the difficulty is footprint rather than availability.

---

## What the trial produced

`experimental/stepExport.py` fits the profile as an interpolating cubic B-spline and sweeps it. The fit is the only place fidelity can be lost, and it is not lost: scipy returns the clamped knot vector STEP expects, so the conversion is collapsing repeated knots into distinct values and multiplicities, with no refitting or resampling in between.

**Interpolation.** The spline passes through all 100 contour stations to 0.0000 um, which is exact to the printed resolution. An interpolating fit should do this, and confirming it rules out the chord-length parameterization being misread, which is the failure that looks like a 152 um error and is really a measurement made at the wrong parameters.

**Acceptance.** OpenCASCADE, reading the file with no knowledge of how it was written, accepted it, transferred one shape, and recovered the topology as written: one shell, one face, four oriented edges. The face's surface came back as `Geom_SurfaceOfRevolution`, not as an approximating NURBS patch, so the analytic form survives the round trip.

**Area.** The reference is Pappus's centroid theorem, A = integral of 2*pi*r ds, by adaptive quadrature on the same spline: 1.314862086 m^2. The kernel computes 1.314862085 m^2 on the geometry it reconstructed. The relative difference is 5e-10, which is the quadrature floor rather than a geometry difference.

One trap is worth recording. OpenCASCADE's `BRepGProp::SurfaceProperties` defaults to a loose tolerance and first returned 1.314448 m^2, a 0.031 percent error that looks like a geometry defect and is not. Tightening the requested accuracy converges monotonically onto the analytic value, reaching it by 1e-9. Any future check of a written file has to pass an explicit tolerance or it will measure the quadrature instead of the geometry.

**SolidWorks.** The written wall opens in SolidWorks as a single revolved surface with the seam reading correctly. That was the verification the first draft of this report left open, and it settles more than the wall: the header, unit and product-structure boilerplate is the part of hand-writing STEP most likely to be silently wrong, and it is the same for every component written since.

---

## The swept components

The channels and volutes are cross sections swept along a path, which does not reduce to one curve and an axis the way a revolution does. It reduces to something almost as cheap. NOVA already holds each of them as a structured grid of points, so the surface is a tensor-product B-spline interpolating that grid, and tensor-product interpolation is separable: fit a curve through the data in one direction, then fit a curve through those control points in the other.

**The seam was the only real decision.** Every component grid closes exactly in one direction, around the cross section, and is open in the other. Fitting the closed direction as an ordinary clamped spline leaves a tangent break at the seam, measured at 0.085 degrees on the channel and volute sections and 0.025 on the keep-out. A periodic fit removes it but needs an unclamped knot vector, which is the classic thing CAD readers handle unevenly.

Neither was necessary. Fitting clamped while pinning the seam tangent at both ends, taken from a periodic fit of the same section, gives a seam kink of 1.2e-6 degrees and a curve that sits 0.0000 um from the periodic one, with a clamped knot vector throughout. That is what the writer does.

**Fidelity.** The surface interpolates all 2,400 channel grid points to 0.000000 um.

**Area.** The reference is the channel's own grid triangulated, which underestimates a curved surface and must converge upward as the grid refines. It does: 0.005615721 m^2 as given at 40 by 60, then 0.005632113, 0.005633071 and 0.005633310 m^2 at successive doublings. Richardson extrapolation on the last two gives 0.005633390 m^2 against the kernel's 0.005633389 m^2, so the 0.31 percent gap against the raw grid is the triangulation's own deficit and not a geometry error.

**Every component.** Driven on the cached showcase nozzle, the writer produces the hot wall, the keep-out, the channel, and both volutes with their shells: seven files, each accepted by OpenCASCADE, each returning `True` from `BRepCheck_Analyzer`, each carrying `Geom_SurfaceOfRevolution` or `Geom_BSplineSurface` as appropriate. Components a run did not build are skipped rather than raising, which is the rule `exports.exportData` already follows.

Each component is written in the axis order `py2cad` already uses for it, so a STEP body lands where its STL does and the two overlay. That mapping is not uniform across components, and the reason is that the arrays are not: the channel is held in its own frame and the volutes in the nozzle frame. Reproducing the existing mapping keeps STEP a drop-in for STL rather than introducing a third convention.

---

## What is not covered

**Booleans**, deliberately. See below.

**Solids.** Each component is written as a surface, which is what each component's data describes. The hot wall has a natural solid form, since NOVA also holds `rNozzleShell`: revolving the region between the two profiles closes a real solid with the jacket thickness in it. That is a small extension of the same writer, two profiles and two end annuli instead of one profile and two circles, and it needs no booleans.

**Contours reaching the axis.** A profile touching r = 0 closes the surface to a point and needs a degenerate seam the writer does not emit. It raises rather than writing a bad file. No NOVA contour does this, since the throat radius is positive by construction.

**The full jacket.** One channel is written, not the sixty that make up the jacket. The pattern is a rotation about the nozzle axis, so this is cheap to add, either as sixty bodies or as one body the CAD user patterns themselves.

---

## Future improvement: booleans

Everything above writes surfaces. Nothing trims one surface against another, and that is the line worth naming, because it is where the work changes kind rather than degree.

Writing a surface is transcription: the geometry is already solved and the file states it. Trimming two surfaces against each other requires computing their intersection curve, which is a genuine numerical algorithm with marching, subdivision, tolerance management and a long tail of degenerate configurations. OpenCASCADE is roughly 1.5 million lines largely because of that problem, and reimplementing it is not a proportionate response to wanting a merged jacket.

What NOVA would need booleans for:

- **Uniting the sixty channels with the wall and shell** into one manifold jacket body rather than sixty-two surfaces.
- **Trimming the volutes against the channel interface**, where the scroll meets the channel ends.
- **Trimming the print supports against the volute wall** they stand on.
- **Subtracting the keep-out envelope** from anything that has to route around it.

The recommended route when that day comes is build123d under a `cad` extra in `pyproject.toml`, imported lazily inside the export function. The optional-extras pattern is already established there for `gui`, `refprop` and `screenshots`. Nothing at package import should touch it: the kernel costs 7.0 s to load and 89.9 MB installed, which is fine in an export path and not fine in a test suite.

The surfaces this writer produces are the right input to that step, since a boolean needs bounded faces and these are already bounded, valid and exact. Adding booleans later does not invalidate any of it.

One thing not to do in the meantime: approximate a boolean by writing overlapping bodies and hoping the CAD package resolves them. A reader will import them as separate bodies that interpenetrate, which is worse than separate bodies that do not, because the overlap is invisible until someone tries to mesh it.

---

## Recommended path

**Now.** Move `writeRevolvedContour`, `writeLoftedSurface` and `exportNozzleStep` into `exports.py` beside `py2cad`, and call it from `exportData` under the existing `export` flag. It adds no dependency and no measurable time.

**Next.** The two-profile solid for the wall, and the sixty-channel pattern. Both are extensions of what is there and neither needs a kernel.

**Later, behind an optional extra.** Booleans, as above, when an assembled body is actually wanted.

---

## Where the code stands

`experimental/stepExport.py` runs standalone against the cached showcase nozzle and prints its own verification:

```bash
python experimental/stepExport.py
```

It writes the revolved wall beside the module and the full component set into `experimental/stepComponents/`, which is gitignored as regenerable output. The single `nozzleWall.step` is kept, since it is the file the SolidWorks check was run against.

It has no NOVA imports and depends only on numpy and scipy, both of which NOVA already requires. The validation numbers above are reproduced by that run, except the kernel read-back and the `BRepCheck_Analyzer` result, which need build123d installed.

The public entry points:

| Function | Writes |
|---|---|
| `writeRevolvedContour` | One 2D profile swept about the nozzle axis, as a surface of revolution |
| `writeLoftedSurface` | One structured point grid, as a tensor-product B-spline surface |
| `exportNozzleStep` | Every component a finished nozzle built, one file each |
