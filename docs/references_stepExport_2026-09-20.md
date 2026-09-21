# STEP Export References

Sources gathered to decide how NOVA should write B-rep geometry, rather than the tessellation `py2cad` produces today. Collected 2026-09-20.

The question driving the search: what is the cheapest way to put an exact nozzle wall into a CAD package, and does it require taking on a CAD kernel as a dependency?

These back `experimental/stepExport.py` and the strategy in [reports/stepExport_2026-09-20.md](reports/stepExport_2026-09-20.md). Unlike the other reference files here, these are tooling and file-format sources rather than literature, so the useful ones are documentation and a production STEP file read directly.

---

## A production STEP AP214 file, read for its boilerplate

- **URL:** <https://www.wirecrafters.com/wp-content/uploads/44.step> (exported by SolidWorks 2021 through SwSTEP 2.0)
- **Accessed:** 2026-09-20
- **Relevance:** The highest-value source of the search. The geometry entities in a STEP file are the easy part; the header, unit and product-structure boilerplate is what decides whether a CAD package opens the file or rejects it, and that is not well documented anywhere. Reading a file a commercial CAD system actually wrote settles it.
- **Key findings:**
  - Header form: `FILE_DESCRIPTION(('STEP AP214'),'1')`, `FILE_SCHEMA(('AUTOMOTIVE_DESIGN'))`. The schema name is `AUTOMOTIVE_DESIGN` even for AP214 files that have nothing to do with automotive work.
  - Units arrive as **complex entity instances**, several types fused into one instance: `(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.))`. Writing these as separate entities produces a file that parses and does not load.
  - The representation context fuses four types the same way, carrying `GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT` with an `UNCERTAINTY_MEASURE_WITH_UNIT` that the reading kernel adopts as its own tolerance.
  - The product chain a loadable file needs: `APPLICATION_CONTEXT`, `APPLICATION_PROTOCOL_DEFINITION`, `PRODUCT_CONTEXT`, `PRODUCT`, `PRODUCT_RELATED_PRODUCT_CATEGORY`, `PRODUCT_DEFINITION_FORMATION`, `PRODUCT_DEFINITION_CONTEXT`, `PRODUCT_DEFINITION`, `PRODUCT_DEFINITION_SHAPE`, and a `SHAPE_DEFINITION_REPRESENTATION` tying it to the geometry.

## ISO 10303-21, the physical file encoding

- **URL:** <https://en.wikipedia.org/wiki/ISO_10303-21>
- **Accessed:** 2026-09-20
- **Relevance:** The syntax rules for the text encoding itself, needed to emit entities by hand rather than through a library.
- **Key findings:**
  - Instances are named `#n` and referenced by name, not position, so entity order in the file is free. The writer exploits this by appending entities as it builds and taking the reference back.
  - Reals must carry a decimal point or an exponent. `1` is invalid where `1.` is valid, which a naive `%G` format will get wrong.
  - `$` marks an unset optional attribute and `*` a derived one, both of which appear in `ORIENTED_EDGE` and in the complex unit instances.

## STEP file format, AP203 against AP214 against AP242

- **URL:** <https://cadshift.com/blog/what-is-step-file-format/>
- **Accessed:** 2026-09-20
- **Relevance:** Which application protocol to target. The choice affects which readers accept the file.
- **Key findings:**
  - AP203 is the geometry-only baseline with the widest reader support. AP214 adds colour, layers and assembly structure and is equally widely read. AP242 supersedes both and adds PMI, with slightly less universal support in older readers.
  - AP214 is the safe default for a file that is geometry plus a product name, which is what NOVA writes.
  - Both AP203 and AP214 support analytic surfaces and NURBS, so nothing about the surface of revolution forces the choice.

## build123d installation and platform support

- **URL:** <https://build123d.readthedocs.io/en/stable/installation.html>
- **Accessed:** 2026-09-20
- **Relevance:** Whether the OpenCASCADE route is actually installable on the target platform, which determines if it is a real option or a theoretical one.
- **Key findings:**
  - `pip install build123d` is the recommended route and supports Python 3.10 through 3.14. This was confirmed by installing it: it resolved and installed on Python 3.10 under Windows with no conda and no compiler.
  - The kernel arrives as the `OCP` wheel, prebuilt. Measured footprint after install: 87.3 MB for OCP plus 2.6 MB for build123d.
  - Version installed and used for the validation: build123d 0.12.0.

## CadQuery import and export

- **URL:** <https://cadquery.readthedocs.io/en/latest/importexport.html>
- **Accessed:** 2026-09-20
- **Relevance:** The other OpenCASCADE-backed option, checked to confirm the two are equivalent for this purpose before choosing between them.
- **Key findings:**
  - CadQuery exports STEP through the same OpenCASCADE writer build123d uses, so the output is equivalent and the choice between them is API preference, not capability.
  - Both wrap raw OCP shapes, so a shape built through either can be handed to the other. Neither locks in.

## OpenCASCADE STEP support

- **URL:** <https://github.com/Open-Cascade-SAS/OCCT/wiki/step>
- **Accessed:** 2026-09-20
- **Relevance:** What OpenCASCADE will accept on read, since it is the kernel used to verify the hand-written file and therefore defines what "valid" meant in the trial.
- **Key findings:**
  - `STEPControl_Reader` reports an `IFSelect_ReturnStatus`, and `IFSelect_RetDone` is the only value that means the file was understood.
  - OCC reads AP203, AP214 and AP242, and preserves analytic surface types through the transfer rather than converting everything to NURBS. This is what made it possible to confirm the written file carries a genuine `Geom_SurfaceOfRevolution`.
  - OCC's reader is more permissive than NX's or SolidWorks's, particularly on seam edge orientation, so acceptance here is necessary and not sufficient.

## build123d, project source

- **URL:** <https://github.com/gumyr/build123d>
- **Accessed:** 2026-09-20
- **Relevance:** Confirming the API used for the benchmark route, specifically how to revolve a spline profile and export it.
- **Key findings:**
  - `Spline(*points)` inside a `BuildLine` context fits through the given points, `make_face()` closes the sketch and `revolve(axis = Axis.X)` sweeps it.
  - `export_step(part, path)` is the export entry point.
  - A revolved closed profile yields a solid, so the exported file carries the two planar end caps in addition to the swept surface. The benchmark's larger area, 1.658499 m^2 against 1.314862 m^2 for the surface alone, is those caps: the difference of 0.343637 m^2 matches pi times the sum of the squares of the two end radii to six figures, which is a useful cross-check that both routes describe the same wall.
