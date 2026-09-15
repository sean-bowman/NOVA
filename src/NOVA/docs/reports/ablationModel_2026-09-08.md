# An ablation model for NOVA

NOVA could size a regeneratively cooled wall and could not say anything about a liner that is meant to be consumed. `NOVA.ablative` closes that: a charring ablator response solver, the surface thermochemistry that sets how fast the char goes away, and a station march that applies both along a nozzle contour.

This records what the model solves, what it was checked against, how far the checks reach, and where they stop.

---

## What the model solves

The formulation is CMA's, after Moyer and Rindal, NASA CR-1061. In a coordinate attached to the receding surface, with `y` measured into the material and `s_dot` the recession rate:

```
d(rho h)/dt = d/dy (k dT/dy) + s_dot d(rho h)/dy + d(m_g h_g)/dy
```

Three terms on the right: conduction, the material sliding past a mesh that follows the surface, and the pyrolysis gas carrying enthalpy toward that surface. Resin decomposition follows Goldstein's two-phase Arrhenius law, and every property is blended between the virgin and char states on the CMA resin fraction

```
tau = (1 - rho_c / rho) / (1 - rho_c / rho_v)
```

Enthalpy is absolute and carries the heat of formation, so the heat of pyrolysis is the gap between the solid enthalpy leaving and the gas enthalpy replacing it rather than a separate constant. That is the whole reason the pyrolysis gas equilibrium enthalpy curve is a required part of a material's data: without it the reaction is silently thermally neutral, which is not a property of any resin.

The mesh is normalized on the shrinking thickness, so nodes hold their proportion as the surface recedes and none is ever dropped. Decomposition integrates in closed form over each step, which removes its stiffness entirely, and the energy equation is then solved implicitly by Newton iteration on the nodal temperatures. The surface node carries no heat capacity and is an algebraic statement of the surface energy balance, which is CMA's convention and avoids having to define the mass of a cell that is being eaten.

### Three surface closures

| Closure | Char removal | Wall enthalpy | Answers |
|---|---|---|---|
| `temperature` | none | not needed | the in-depth problem alone |
| `bPrimeTable` | tabulated equilibrium | tabulated | arc-jet and entry, to 1 atm |
| `diffusionLimited` | closed-form elemental balance | temperature potential | rocket conditions, as a bound |

---

## Verification

Verification asks whether the discretisation solves the equations it claims to. Every case below has a solution that is known exactly, so the error is a number rather than an impression. All of them live in `tests/testAblative.py`.

### Conduction

| Case | Reference | Error |
|---|---|---|
| Semi-infinite solid, step surface temperature | `T = Ts + (T0 - Ts) erf(y / 2 sqrt(alpha t))` | **0.051 K** on a 700 K step, 0.007 % |
| Semi-infinite solid, constant surface flux | `Ts = T0 + 2 q sqrt(alpha t / pi) / k` | **0.60 K** on a 437 K rise, 0.14 % |

Refining the surface cell from 37 to 6.5 microns takes the first case from 0.61 K to 0.018 K.

### Steady ablation

Once the recession rate is constant and the profile has stopped moving in the surface frame, the equation collapses to `alpha T'' + s_dot T' = 0`, whose solution is a pure exponential decaying over a length `alpha / s_dot`. This is the only check that exercises the moving-mesh term.

| Quantity | Result |
|---|---|
| Recession rate against the rate the closure asks for | agrees to **1e-6** relative |
| Profile against `T_inf + (T_w - T_inf) exp(-s_dot y / alpha)` | **14 K** worst, 0.71 % of the wall-to-far-field difference |
| Wall temperature against the algebraic steady balance | **0.46 %** |

The 0.71 per cent is the first order error of the upwinded mesh-motion term, and it is the largest verification error anywhere in the model.

### Decomposition

The closed-form step is checked against 40,000 explicit substeps of the rate law it integrates.

| Temperature | Worst relative difference |
|---|---|
| 700 K | 3.8e-07 |
| 900 K | 1.1e-05 |
| 1200 K | 3.4e-05 |
| 1600 K | 5.1e-05 |

A side result worth recording, because it looks like a bug and is not: a third-order reaction decays as the inverse square root of time and therefore **never reaches the char density exactly**. After an hour at 3000 K the faster TACOT phase still holds 0.134 kg/m^3 of the 300 it started with. A solver that returned exactly the char density would be wrong rather than converged.

### Energy closure

The discrete global balance is measured every step against the largest single term in it.

With a fixed surface it closes to **6e-10**, which is the Newton tolerance. Nothing moves, so every term sits on a control volume that does not, and the scheme is conservative to machine precision.

With recession it does not, and the reason is structural. The surface node carries no volume, which is what makes the surface energy balance exact at the surface temperature; the price is that material leaving through that node is in no control volume. The error is first order in the size of the first cell:

| First cell | Closure error | Ratio | Recession | Wall temperature |
|---|---|---|---|---|
| 39.9 um | 3.07e-02 | | 4.1036 mm | 1558.97 K |
| 18.2 um | 1.56e-02 | 1.97 | 4.1064 mm | 1557.91 K |
| 8.7 um | 7.87e-03 | 1.98 | 4.1078 mm | 1557.36 K |
| 4.3 um | 3.95e-03 | 1.99 | 4.1085 mm | 1557.07 K |

Halving the cell halves the error, exactly as first order requires. The two right-hand columns are the point: recession moves 0.1 per cent and wall temperature 1.9 K across a range over which the bookkeeping error changes by a factor of eight. The error is in the accounting, not in the answer.

---

## Validation

Validation asks whether the equations describe reality, and needs data somebody else produced.

### Surface thermochemistry, against an independent equilibrium solution

The packaged B-prime table was generated by the Ablation Workshop using TARGET on the CEA thermodynamic database, for air, over a 25 species mixture, with equal diffusion coefficients and equilibrium imposed at the wall. Nothing in NOVA had a hand in it.

The closed-form diffusion-limited rate comes from an elemental balance at the surface: requiring that every wall oxygen atom leaves as carbon monoxide and that no free carbon is left over closes it at

```
B'c = (M_C / M_O) (Z_O,e + B'g Z_O,g) - Z_C,e - B'g Z_C,g
```

with a factor of one half on the mass ratio for the carbon dioxide branch. Those two branches are the asymptotes the equilibrium table runs between, and that is where they can be checked.

| Branch | Closed form | Table | Error |
|---|---|---|---|
| Carbon dioxide, 250 K, 1 atm | 0.0874252 | 0.0874262 | **0.0011 %** |
| Carbon monoxide, 1500 to 2500 K plateau, 1 atm | 0.1748505 | 0.1748510 | **0.0003 %** |

Between the two branches the equilibrium result lies between them and neither closed form describes it. That region is what the table is for.

### Material response, against the FIAT baseline

Ablation Workshop test case 1: five centimeters of TACOT, surface driven to 1644 K in 0.1 s and held for a minute, adiabatic back face, one atmosphere. The workshop designated FIAT results from the Thermal Performance Data Base as the baseline; fourteen codes ran the case in 2011 and the workshop reported agreement between type 1 codes as mostly below one per cent.

The reference values were digitized from the published figure at 400 dpi. The calibration is good to about 1.5 K: the axis tick marks, whose values are known exactly, come back as 199.5, 399.0, 600.0, 799.5, 999.0 and 1599.0, and the imposed surface line, known to be 1644 K, comes back as 1643.9. Marker centring adds a few kelvin on top.

At 60 s, on a 241 node mesh:

| Probe | FIAT | NOVA | Difference |
|---|---|---|---|
| 1 mm | 1526.7 K | 1527.9 K | +0.08 % |
| 2 mm | 1417.4 K | 1420.8 K | +0.24 % |
| 4 mm | 1223.0 K | 1229.5 K | +0.53 % |
| 8 mm | 912.3 K | 919.6 K | +0.80 % |
| 16 mm | 549.4 K | 558.5 K | +1.65 % |
| 50 mm | 297.8 K | 298.1 K | +0.11 % |
| char front | 2.63 mm | 2.72 mm | +3.3 % |
| pyrolysis front | 14.93 mm | 15.10 mm | +1.2 % |

Five of the six temperature probes sit inside one per cent, which is the band the workshop itself reported between codes of this type. The deepest probe is the one the mesh resolves least well, and it converges toward the reference as the mesh is refined: 2.60 per cent at 101 nodes, 1.97 at 161, 1.65 at 241.

The two front locations are the weakest agreement. They are defined by where the density profile crosses a threshold, so they inherit the resolution of the profile rather than of the temperature, and a two per cent density threshold on a sixty kilogram per cubic meter density range is a fine thing to ask a mesh to locate.

### Test case 2.2, as a sanity check only

The same material with a convective boundary and recession. The workshop's own note on its preliminary results is explicit: use them for sanity check rather than for comparison. Read that way:

| Quantity | PATO / Amaryllis | NOVA |
|---|---|---|
| Surface temperature at 60 s | ~1565 K | 1583 K |
| Recession at 60 s | ~12.0 mm | 12.74 mm |
| Char removal rate at plateau | ~0.045 kg/m^2 s | 0.048 kg/m^2 s |
| Pyrolysis front at 60 s | ~19.5 mm | 19.59 mm |

---

## What is not validated

### The nozzle application

No open source gives measured throat recession against a firing condition specified in enough detail to set a model against. The station march is therefore a verified solver driven by a correlated gas-side coefficient and a bounded recession rate. Its numbers compare design options; they do not predict recession.

### The recession bound is loose for a rocket

The diffusion-limited rate assumes two things, both optimiztic about how fast the char disappears. Surface kinetics are taken to be infinitely fast, which holds above roughly 2000 K and fails below it. And every oxygen atom reaching the wall is taken to leave as carbon monoxide, which over-consumes carbon whenever the exhaust carries hydrogen, because in equilibrium the hydrogen competes for that oxygen and some of it leaves as water.

Both errors run the same way, and for a hydrocarbon propellant the gap is large. LOX/RP-1 at a mixture ratio of 2.7 has an exhaust that is 73.0 per cent oxygen and 23.2 per cent carbon by element, which gives a transport-limited `B'c` of 0.316, nearly twice the value for air. Driven at that rate against a Bartz coefficient of 9.5 kW/m^2 K, the bound predicts a throat recession an order above what motors of that class actually show.

`charRemovalEfficiency` exists so that gap can be closed against firing data. Doing so is calibration, not validation: the value that comes out holds only over the conditions it was fitted to, and that should be stated wherever the result is.

### Surface chemical heat release

The diffusion-limited closure returns a mass removal rate and leaves the reaction enthalpy to the caller through `surfaceHeatOfAblation`, defaulting to zero. Zero is not the physical value.

In a rocket exhaust the char-consuming reactions are dominated by `C + CO2 -> 2 CO` and `C + H2O -> CO + H2`, endothermic at 14.4 and 10.9 MJ per kg of carbon. Omitting them therefore **overpredicts** wall temperature rather than underpredicting it, which is the safe direction but still a known bias. Pure oxidation, `C + 1/2 O2 -> CO`, runs the other way at 9.2 MJ/kg released.

### The material

TACOT is the only charring ablator whose complete response property set is in the open literature, and it is a theoretical material published so that codes can be compared on identical inputs. At 280 kg/m^3 virgin it is a low-density entry heatshield, roughly a fifth the density of the tape-wrapped carbon phenolic used in a nozzle throat, and it chars and conducts accordingly.

Applying it to a nozzle gives the right physics on the wrong material. The demonstration case above recedes at 0.68 mm/s at the throat; scaling by the char density ratio to a real carbon phenolic gives 0.12 mm/s, which is where motors of that class sit. That the scaling lands in the right place is a sanity check on the mechanism, not a validation of the number.

### The B-prime table cannot close a rocket problem

The packaged table is for air and its pressure axis stops at one atmosphere, two orders below a rocket chamber. `BPrimeTable.clampedRequests` counts how often a run left the grid, and a nozzle run through that closure would leave it on every call. That is why the nozzle path uses the elemental balance instead: a transport limit does not depend on pressure, and the table confirms as much, returning the same low-temperature value across all four of its pressures to nine decimal places.

---

## The data

The material store gained `_ABLATIVERESPONSEDATA`, holding TACOT v3.0 with virgin and char curves for specific heat, conductivity and absolute enthalpy on a shared grid to 3333 K, emissivities, the three-component Goldstein kinetics with the mixing rule that returns the stored end-state densities, and the elemental composition of both the pyrolysis gas and the char.

Two packaged assets carry what is too large to hold as source:

| Asset | Contents |
|---|---|
| `assets/tacotBPrimeAir.npz` | `B'c` and wall enthalpy on 4 pressures x 25 gas blowing rates x 151 temperatures |
| `assets/tacotPyrolysisGas.npz` | equilibrium pyrolysis gas enthalpy and molar mass on 4 pressures x 152 temperatures |

Both were extracted from the TACOT v3.0 spreadsheet distributed with the Ablation Workshop test case series. Sources are in `docs/references_ablationModeling_2026-09-08.md`.

---

## What would close the remaining gaps

**A real liner material.** The property set for tape-wrapped carbon phenolic exists, in DTIC reports that return 403 to automated access and in MIL-HDBK-17 and CINDAS behind licenses. Obtaining one would change the nozzle path from a demonstration to a design tool without touching the solver.

**One firing with measured recession.** A throat diameter before and after, with chamber pressure, mixture ratio and burn time recorded, sets `charRemovalEfficiency` for that propellant combination. Two firings at different mixture ratios would say whether a single value holds.

**Surface thermochemistry for exhaust rather than air.** Generating a `B'c` table for the actual propellant products, at chamber pressures, removes both the hydrogen-competition error and the pressure clamp at once. It needs an equilibrium solver that accepts an arbitrary element mixture with condensed carbon, which `rocketcea` does not expose.

**Axial conduction across the throat.** Each station is solved independently, which is right where the liner is thin against the local radius. Across the throat the flux changes by a factor of several over a few liner thicknesses, so the throat runs slightly hot and slightly deep against a two-dimensional solve.
