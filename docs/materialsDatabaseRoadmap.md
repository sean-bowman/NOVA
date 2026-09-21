
# Materials Database Roadmap

Where NOVA's material data stands, and what a general materials database for it would need.

The tool currently needs one thing from a material: the conductivity of the chamber wall as a function of temperature, so the regenerative cooling solve can close a conductive resistance at each station. Everything else it stores is either carried for margin checks that have not been written or is not read at all. That is a reasonable place to be for a nozzle tool, and it is a poor place to stay for one that will eventually size ablatives, composite overwraps and printed polymer tooling.

This document is the parking place for that longer plan. It is not a commitment to a schedule.

---

## What exists today

Three stores, in `src/NOVA/materials.py`.

### `_MATERIALCLASSES`, reached through `availableMaterials` and `materialProfile`

Everything a nozzle is made of that is not a regeneratively cooled wall: throat inserts, nozzle extensions, ablative liners, thermal barrier coatings and the polymers in the feed system. Eleven materials across six classes.

| Material | Class | Density [kg/m3] | Inert limit [degC] | Oxidizing limit [degC] | Basis |
|---|---|---|---|---|---|
| ATJ Graphite | refractory | 1760 | 2800 | 400 | producer datasheet |
| Carbon-Carbon (2D) | composite | 1825 | 2500 | 400 bare, 1750 coated | literature review |
| C/SiC | composite | 2050 | 1700 | 1400 | literature review |
| SiC/SiC | composite | 2700 | 1700 | 1600 | literature review |
| Carbon Phenolic | ablative | 1450 | 2500 char | 1000 | literature review |
| Silica Phenolic | ablative | 1700 | -- | 1650 | representative |
| 7YSZ | ceramic | 6000 | -- | 1200 | representative |
| C103 | refractory metal | 8850 | 1400 | 400 | literature review |
| PTFE | polymer | 2175 | -- | 260 | representative |
| PCTFE | polymer | 2130 | -- | 193 | producer datasheet |
| PEEK | polymer | 1320 | -- | 249 | representative |

It is kept apart from the wall alloys deliberately. `wallMaterialCurves` is what the heat transfer model reads, and nothing in this table can be a cooled wall: carbon phenolic is meant to be consumed, graphite cannot be brazed into a jacket, PTFE is a seal.

**This store is selection grade, not analysis grade, and its `basis` field says which per property.** For metals there are critically evaluated compilations that are freely available. The equivalents here are access controlled or paywalled, so almost nothing carries a temperature-dependent curve. What it does carry is the property that usually governs the choice: the maximum use temperature, with the atmosphere it applies in. For the carbon materials those differ by a factor of six.

### The wall alloy stores

Two stores that do not know about each other.

### `_WALLCURVEDATA`, reached through `wallMaterialCurves` and `sampleWallMaterial`

Ten wall alloys, each on its own temperature grid, in degrees Celsius: GRCop-42, CuCrZr, OFHC Copper, NARloy-Z, AlSi10Mg, Al 6061-T6, Inconel 718, Inconel 625, 316L and Ti-6Al-4V. Four properties per material plus two scalars and a free-text source string.

This is the store production uses. `regenThermal` builds a conductivity interpolator from it at three places in the heat transfer loop, `channelSizing` builds four interpolators, and the GUI's material panel samples it.

Twenty-one of its forty properties are measured curves. The other nineteen are a single room-temperature value broadcast flat across the grid:

| Material | Conductivity | Yield | CTE | Elongation | Grid, degC |
|---|---|---|---|---|---|
| GRCop-42 | curve | curve | curve | curve | 25 to 900 |
| CuCrZr | curve | flat | curve | flat | 20 to 600 |
| OFHC Copper | curve | flat | curve | flat | **-253** to 900 |
| NARloy-Z | curve | flat | flat | flat | 25 to 800 |
| AlSi10Mg | curve | flat | flat | flat | 25 to 900 |
| Al 6061-T6 | curve | flat | curve | flat | **-253** to 400 |
| Inconel 718 | curve | curve | curve | curve | **-253** to 900 |
| Inconel 625 | curve | flat | flat | flat | 21 to 982 |
| 316L | curve | flat | curve | flat | **-253** to 900 |
| Ti-6Al-4V | curve | flat | curve | flat | **-253** to 800 |

A curve can be measured over part of its grid and held flat over the rest: the four expansion curves that came from NIST are data below room temperature and a held constant above it. `propertyProvenance(material, property)` returns the citation and the temperature range over which the stored values are data, which is the question `propertyIsMeasured` is too coarse to answer.

Sources are recorded in `references_materialProperties_2026-09-08.md`.

Since a flat property is broadcast to the grid's length, it is the same shape as a real curve and an interpolator built on it behaves the same way. `wallMaterialCurves` therefore returns a `measured` map saying which is which. Anything drawing a conclusion from how a property changes with temperature has to consult it first.

### `materialProperties` and `roughnessTable`

Nine structural alloys with scalar density, yield, ultimate, modulus, Poisson ratio, conductivity, expansion and a cryogenic yield factor, plus thirteen surface finishes. Neither function has a production caller; only `tests/testMaterials.py` reaches them.

Two problems worth naming:

- **The stores disagree.** 316L appears in both, with a conductivity of 16.3 W/m-K in one and 14.6 W/m-K in the other. Nothing reconciles them, and only the second is validated against a cited source.
- **The temperature argument is half honoured.** Only yield and ultimate strength respond to it, through a piecewise-linear cryogenic ramp below 293 K that saturates at 77 K. Conductivity and expansion are returned unchanged whatever temperature is asked for, while the docstring describes expansion as a mean from 293 K to the requested temperature.

---

## Gaps that affect results now

**Half the table still has no cryogenic data.** GRCop-42, CuCrZr, NARloy-Z, AlSi10Mg and Inconel 625 still start at room temperature and clamp below it, and regen coolant inlets are at liquid hydrogen temperature. The five NIST covers now reach 20 K, and the size of what was being missed is worth recording:

| Material | k(20 K) / k(293 K) |
|---|---|
| OFHC Copper | **3.49** |
| Inconel 718 | 0.303 |
| Al 6061-T6 | 0.183 |
| 316L | 0.142 |
| Ti-6Al-4V | 0.114 |

Clamping put every one of those at 1.0. The alloys conduct three to nine times *worse* at 20 K, and pure copper three and a half times *better*, so the error does not even have a consistent sign. My earlier estimate in this document, that 316L would be off by roughly a factor of two, was wrong by a further factor of three.

For the copper alloys the missing data matters less than the bare gap suggests. The low-temperature conductivity peak is a purity effect: it comes from electron scattering falling away in a nearly perfect lattice, and alloying suppresses it. Carrying OFHC's peak across to GRCop-42 or NARloy-Z would be wrong in the direction that flatters the design. Their cryogenic behavior needs measuring, not inferring.

**Conductivity is evaluated at the hot wall only.** `regenThermal` reads `k(T_hot)` and uses it across the full wall thickness, which the code comments already acknowledge. With a real curve and a hot-to-cold span of several hundred kelvin the mean value through the wall is the physically correct one. A `k` accessor taking two temperatures and returning the thickness-averaged value would slot into three call sites with no other change.

**Four interpolators are built and never read.** `channelSizing` constructs yield, elongation, CTE and conductivity interpolators, exports them on its state, declares them on two dataclasses, and evaluates none of them. The comment beside them says they are carried for downstream margin checks. Those margin checks are the missing feature, and they are the reason the strength and expansion curves would be worth having.

---

## What a general materials database would need

The current shape, a dictionary of property names to values, does not survive contact with ablatives or composites. Three things break it.

**Properties stop being scalars or single-variable curves.** An ablative needs a pyrolysis model, a char layer conductivity distinct from the virgin conductivity, and a recession rate against heat flux. A composite is orthotropic, so conductivity and expansion are tensors and depend on lay-up rather than on the material alone. A property has to be able to be a callable with its own signature.

**Provenance has to carry more than a citation and a range.** The per-property `provenance` entry now gives both, which is enough to say what a number is and where it stops being data. A design allowable needs more: the date, the specification, the basis (typical, A-basis, B-basis, S-basis), and the product form and thickness it applies to. Inconel 718's yield curve already shows why the last of those matters, since it is spliced from two product forms that disagree by 1.8 percent where they meet, and that figure currently lives in prose rather than in a field anything can check.

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

### Classes worth carrying

| Class | Why NOVA would want it | What it needs beyond the current shape |
|---|---|---|
| Metals | Chamber walls, jackets, manifolds, structure | Cryogenic grids; A- and B-basis allowables; weld and printed-condition knockdowns |
| Ablatives | Throat inserts, uncooled extensions | Pyrolysis kinetics, char and virgin conductivity, recession against flux and enthalpy |
| Composites | Overwraps, nozzle extensions, structure | Orthotropic tensors, lay-up dependence, interlaminar properties |
| Polymers | Seals, tooling, printed test articles | Glass transition, creep, chemical compatibility with the propellant |
| Ceramics and coatings | Thermal barriers | Thin-layer conductivity, adhesion limits, spallation |
| Refractories | Throat inserts | Behavior above 2000 K, oxidation |

---

## Order of work

Each step is worth doing on its own, and each is a prerequisite for the one after it.

1. ~~**Extend the metal grids to cryogenic temperature.**~~ Done for the five alloys NIST covers, down to 20 K, with the fit errors NIST states and a test on each conductivity ratio. Still open for GRCop-42, CuCrZr, NARloy-Z, AlSi10Mg and Inconel 625, none of which NIST carries. The copper alloys need measurement rather than inference, for the reason given above.

   One caveat that came out of doing it. Where NIST and the existing high-temperature source disagree at the 293 K join, the cryogenic segment is scaled onto the existing value so the validated hot curve is preserved. That is a normalization, not a validation. The factors run from x0.996 for OFHC copper to x1.147 for Inconel 718, and each is recorded in the entry it applies to. Inconel 718's 12.8 percent join disagreement is the one worth revisiting if a single source covering both ranges turns up.

2. **Add measured yield and elongation for the eight alloys that lack them.** Inconel 718 now has both, from -253 to 816 degC, out of the Special Metals bulletin. The others are blocked on sources rather than on effort: ASME Section II Part D and MMPDS carry exactly the tables wanted for 316L, Inconel 625, 6061-T6 and Ti-6Al-4V, and both are paywalled; the Inconel 625 bulletin plots the curve without tabulating it. Filling these from assorted journal papers on different product forms would produce something that looks authoritative and is not traceable to one condition. Until a source is available `propertyIsMeasured` reports False, and that is the right answer.
3. **Reconcile the two stores into one.** One entry per material carrying every property, with `materialProperties` and `wallMaterialCurves` as two views of it. This removes the 316L disagreement by construction.
4. **Add the structured provenance record**, and with it the typical-against-allowable distinction.
5. **Write the margin checks** that `channelSizing`'s four unused interpolators were built for. Once those exist, the strength and expansion curves are load-bearing rather than decorative, which is the point at which step 2 pays for itself.
6. **Generalize the property model** to callables and tensors, which is what admits ablatives and composites. The non-metallic store took a first step by keying every property on a variant, so anisotropy and the virgin-versus-char split of an ablative use one mechanism, but the values behind those keys are still scalars.

7. ~~**Give the ablatives a model rather than a datasheet entry.**~~ Done, and it moved the blocker rather than removing it. `NOVA.ablative` solves the charring ablator response in the CMA formulation: virgin and char curves blended on the resin fraction, Arrhenius decomposition, pyrolysis gas convecting its own enthalpy to the surface, and a receding boundary closed either by a tabulated equilibrium surface thermochemistry or by the closed-form diffusion-limited carbon oxidation rate. A third store, `_ABLATIVERESPONSEDATA`, holds what that needs, and the accessors are `availableAblativeMaterials` and `ablativeResponseData`. Verification and validation are in `docs/reports/ablationModel_2026-09-08.md`.

   **The remaining gap is the material, not the model.** The store holds one entry, TACOT v3.0, which is the theoretical composite the Ablation Workshop publishes so that codes can be compared on identical inputs. It is the only charring ablator whose complete response property set is open, and at 280 kg/m^3 virgin it is a low-density entry heatshield rather than a tape-wrapped nozzle liner at 1450. The DTIC reports holding the carbon phenolic conductivity curves, AD0702112 and AD0675179, still refuse automated access, and MIL-HDBK-17 and CINDAS carry the equivalent behind licenses. Obtaining one real liner property set would turn the nozzle path from a demonstration into a design tool without touching the solver.

9. **Find an emissivity anybody measured.** The store now carries one, for R512E coated columbium, and it is the degraded value after pentoxide formation rather than a beginning-of-life number. Nothing else has one. That matters more than it looks: a radiation-cooled wall settles where its own emissivity puts it, the equilibrium temperature goes as the inverse fourth root, and a factor of four in emissivity is a factor of 1.41 in wall temperature, which is the difference between 1100 K and 1550 K on a C103 extension.

   The obstacle is that emissivity is a property of a surface rather than of an alloy. Polished and oxidized samples of the same metal differ by an order of magnitude, and the surface changes during a firing. A published number for an alloy means nothing without the surface condition attached, which is why the store keys it on one. No source was found giving emissivity for any of the copper wall alloys at the as-built laser powder bed fusion finish a printed chamber actually has, and the GRCop hot-fire literature reports oxidation behavior without radiative properties. What would close this is a measurement on a representative coupon, before and after firing, rather than more searching.

8. **Get one firing with measured recession.** A throat diameter before and after, with chamber pressure, mixture ratio and burn time, sets `charRemovalEfficiency` for that propellant combination. The diffusion-limited rate the model computes is an upper bound: it assumes infinitely fast surface kinetics and that every wall oxygen atom leaves as carbon monoxide, and both assumptions overstate recession for a hydrocarbon exhaust, where the hydrogen competes for that oxygen. Two firings at different mixture ratios would say whether a single efficiency holds or whether the closure needs the equilibrium treatment instead.

10. **Give the refractory metals a conductivity curve.** `_WALLCURVEDATA` holds the ten jacket alloys and nothing else, so `wallMaterialCurves('C103')` warns and substitutes GRCop-42, which conducts about eight times better. The radiation-cooled extension solver in `NOVA.radiativeCooling` therefore takes conductivity as an explicit input rather than looking it up, and the number and its source belong to the caller. That is the honest arrangement while the store is empty, and it is not where the value should live.

    The consequence is smaller than it sounds and worth recording alongside the gap. On a 0.5 mm shell the conduction length is about ten millimeters against a contour of half a meter, and moving conductivity from 45 to 400 W/m-K narrows the wall temperature span by under three percent. A wrong conductivity misplaces the joint's influence over a few stations rather than the whole distribution. What would close this is a measured curve for C103 across its service range, which unlike the emissivity is a routine measurement somebody has almost certainly made.

Steps 1, 2 and 3 are data and refactoring inside the current design. Steps 4 through 6 change the design, and there is no reason to change it before something needs the generality. Steps 7, 8, 9 and 10 are all waiting on data that either is not open or has never been measured, which is a different kind of blocker from the rest of this list and will not be cleared by writing more code.
