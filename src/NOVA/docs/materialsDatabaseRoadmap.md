# Materials Database Roadmap

Where NOVA's material data stands, and what a general materials database for it would need.

The tool currently needs one thing from a material: the conductivity of the chamber wall as a function of temperature, so the regenerative cooling solve can close a conductive resistance at each station. Everything else it stores is either carried for margin checks that have not been written or is not read at all. That is a reasonable place to be for a nozzle tool, and it is a poor place to stay for one that will eventually size ablatives, composite overwraps and printed polymer tooling.

This document is the parking place for that longer plan. It is not a commitment to a schedule.

---

## What exists today

Two stores, in `src/NOVA/materials.py`, that do not know about each other.

### `_WALLCURVEDATA`, reached through `wallMaterialCurves` and `sampleWallMaterial`

Ten wall alloys, each on its own temperature grid, in degrees Celsius: GRCop-42, CuCrZr, OFHC Copper, NARloy-Z, AlSi10Mg, Al 6061-T6, Inconel 718, Inconel 625, 316L and Ti-6Al-4V. Four properties per material plus two scalars and a free-text source string.

This is the store production uses. `regenThermal` builds a conductivity interpolator from it at three places in the heat transfer loop, `channelSizing` builds four interpolators, and the GUI's material panel samples it.

Thirteen of its forty properties are measured curves. The other twenty-seven are a single room-temperature value broadcast flat across the grid:

| Material | Conductivity | Yield | CTE | Elongation | Grid, degC |
|---|---|---|---|---|---|
| GRCop-42 | curve | curve | curve | curve | 25 to 900 |
| CuCrZr | curve | flat | flat | flat | 20 to 600 |
| OFHC Copper | curve | flat | flat | flat | 25 to 900 |
| NARloy-Z | curve | flat | flat | flat | 25 to 800 |
| AlSi10Mg | curve | flat | flat | flat | 25 to 900 |
| Al 6061-T6 | curve | flat | flat | flat | 25 to 400 |
| Inconel 718 | curve | flat | flat | flat | 25 to 900 |
| Inconel 625 | curve | flat | flat | flat | 21 to 982 |
| 316L | curve | flat | flat | flat | 25 to 900 |
| Ti-6Al-4V | curve | flat | flat | flat | 20 to 800 |

Since a flat property is broadcast to the grid's length, it is the same shape as a real curve and an interpolator built on it behaves the same way. `wallMaterialCurves` therefore returns a `measured` map saying which is which, and `propertyIsMeasured` reads it. Anything drawing a conclusion from how a property changes with temperature has to consult that map first.

### `materialProperties` and `roughnessTable`

Nine structural alloys with scalar density, yield, ultimate, modulus, Poisson ratio, conductivity, expansion and a cryogenic yield factor, plus thirteen surface finishes. Neither function has a production caller; only `tests/testMaterials.py` reaches them.

Two problems worth naming:

- **The stores disagree.** 316L appears in both, with a conductivity of 16.3 W/m-K in one and 14.6 W/m-K in the other. Nothing reconciles them, and only the second is validated against a cited source.
- **The temperature argument is half honoured.** Only yield and ultimate strength respond to it, through a piecewise-linear cryogenic ramp below 293 K that saturates at 77 K. Conductivity and expansion are returned unchanged whatever temperature is asked for, while the docstring describes expansion as a mean from 293 K to the requested temperature.

---

## Gaps that affect results now

**Nothing covers cryogenic temperature.** Every grid starts at 20 to 25 degC, and regen coolant inlets are at liquid hydrogen temperature; the shipped example configures a fuel inlet of 20.27 K. `sampleWallMaterial('316L', 90.0)` clamps to the 25 degC value and returns it silently. For austenitic stainless the real conductivity at 90 K is roughly half its room-temperature value, so the cold end of a jacket is being sized on a conductivity that is materially wrong. Extending the grids downward is the single highest-value addition to the data.

**Conductivity is evaluated at the hot wall only.** `regenThermal` reads `k(T_hot)` and uses it across the full wall thickness, which the code comments already acknowledge. With a real curve and a hot-to-cold span of several hundred kelvin the mean value through the wall is the physically correct one. A `k` accessor taking two temperatures and returning the thickness-averaged value would slot into three call sites with no other change.

**Four interpolators are built and never read.** `channelSizing` constructs yield, elongation, CTE and conductivity interpolators, exports them on its state, declares them on two dataclasses, and evaluates none of them. The comment beside them says they are carried for downstream margin checks. Those margin checks are the missing feature, and they are the reason the strength and expansion curves would be worth having.

---

## What a general materials database would need

The current shape, a dictionary of property names to values, does not survive contact with ablatives or composites. Three things break it.

**Properties stop being scalars or single-variable curves.** An ablative needs a pyrolysis model, a char layer conductivity distinct from the virgin conductivity, and a recession rate against heat flux. A composite is orthotropic, so conductivity and expansion are tensors and depend on lay-up rather than on the material alone. A property has to be able to be a callable with its own signature.

**Provenance has to be structured rather than a sentence.** The `source` string today is one line per material covering every property at once. A design allowable needs the source, the date, the specification it was taken from, the basis (typical, A-basis, B-basis, S-basis), the product form and thickness it applies to, and the range it was fitted over. Two of the current entries already carry warnings inside the prose, that NARloy-Z's trend is not independently validated and that AlSi10Mg is not traceable to a primary source, which is the right instinct and the wrong place for it.

**Typical values and design allowables have to be distinguishable.** The module docstring says the data is typical handbook values and not design allowables. Once anything computes a margin, that distinction has to be carried in the data and checked at the point of use, not stated once at the top of a file.

A shape that handles those:

```
Material
  name, class (metal / polymer / ablative / composite / ceramic)
  form (wrought / LPBF / cast / laminate), condition (annealed / STA / T6)
  properties: name -> Property
  
Property
  value        scalar, table, or callable
  unit         checked against the package registry
  basis        typical | A | B | S | derived
  provenance   source, date, specification, product form, thickness range
  validRange   temperature and any other independent variable
  measured     whether the variation is real or the value is held
```

with the registry from `units.py` checking the unit on every entry, which is the reason that module was put on Pint.

### Classes worth carrying, and why

| Class | Why NOVA would want it | What it needs beyond the current shape |
|---|---|---|
| Metals | Chamber walls, jackets, manifolds, structure | Cryogenic grids; A- and B-basis allowables; weld and printed-condition knockdowns |
| Ablatives | Throat inserts, uncooled extensions | Pyrolysis kinetics, char and virgin conductivity, recession against flux and enthalpy |
| Composites | Overwraps, nozzle extensions, structure | Orthotropic tensors, lay-up dependence, interlaminar properties |
| Polymers | Seals, tooling, printed test articles | Glass transition, creep, chemical compatibility with the propellant |
| Ceramics and coatings | Thermal barriers | Thin-layer conductivity, adhesion limits, spallation |
| Refractories | Throat inserts | Behaviour above 2000 K, oxidation |

---

## Order of work

Each step is worth doing on its own, and each is a prerequisite for the one after it.

1. **Extend the metal grids to cryogenic temperature.** This changes results today. Sources: NIST cryogenic material properties database for the austenitics and aluminium alloys, NASA-HDBK-6003 and the CINDAS/Touloukian series for the copper alloys. Every added curve validated against its source with the error quantified, in the manner `tests/testMaterials.py` already uses for conductivity.
2. **Add measured yield, expansion and elongation for the nine alloys that lack them.** Twenty-seven properties, each needing a cited source. Until then `propertyIsMeasured` reports False for all of them, and it should stay that way rather than being filled with plausible numbers.
3. **Reconcile the two stores into one.** One entry per material carrying every property, with `materialProperties` and `wallMaterialCurves` as two views of it. This removes the 316L disagreement by construction.
4. **Add the structured provenance record**, and with it the typical-against-allowable distinction.
5. **Write the margin checks** that `channelSizing`'s four unused interpolators were built for. Once those exist, the strength and expansion curves are load-bearing rather than decorative, which is the point at which step 2 pays for itself.
6. **Generalise the property model** to callables and tensors, which is what admits ablatives and composites.

Steps 1, 2 and 3 are data and refactoring inside the current design. Steps 4 through 6 change the design, and there is no reason to change it before something needs the generality.
