# The gas model: state of play

A record of what the exhaust is modeled as, written to be picked up cold. The mesh runs on one ratio of specific heats. The gas that would replace it with local properties exists and is validated; nothing uses it yet. This document is the scope of that work, what it would buy, and where finite-rate chemistry sits beyond it.

The standard method is the reference throughout. SP-8120 asks for equilibrium gas properties and confines a constant specific heat to the transonic solution, and TDK, the JANNAF reference code, carries fully coupled finite-rate kinetics. NOVA sits at the simple end of that axis, which `docs/NozzleContourMethods.md` records in its cross-reference table.

## Where the code is

`src/NOVA/equilibriumExpansion.py` holds the gas. `expansionTable` samples CEA along the chamber isentrope and returns the local state at each station. `EquilibriumGas` answers the same four questions `characteristics.CharacteristicGas` answers, by interpolating that table rather than evaluating a closed form at one exponent.

`tests/testEquilibriumExpansion.py` is the suite. Nothing in the package imports the module, so no result NOVA produces depends on it.

## What is validated, and against what

**The generalized Prandtl-Meyer integral reproduces its own closed form.** The Prandtl-Meyer function is the one relation with no closed form once the exponent varies, so it is integrated from its defining differential, `d(nu) = sqrt(M^2 - 1) dV / V`, along the table. Generated from a constant-gamma expansion at the module's default sampling, it lands within 0.022 degrees of `gasDynamics.prandtlMeyerAngle` at gamma 1.15, 1.2 and 1.4, over area ratios to 100. That is the only check available that does not come from the thermochemistry it is meant to replace.

**The table is CEA's and carries CEA's validation, which `tests/testCeaInterface.py` establishes against CEARun.** What is not established is that an equilibrium expansion is the right model. A real nozzle recombines at a finite rate and freezes somewhere in the diverging section, which neither limit describes.

## What one exponent costs

Turning from the throat on the LOX/LH2 reference engine, 6.89 MPa at a mixture ratio of 5.5:

| Area ratio | Local gamma | Equilibrium | At chamber gamma 1.1475 | At effective gamma 1.2005 |
|---|---|---|---|---|
| 1.95 | 1.1709 | 33.06 deg | 32.98 deg | 31.27 deg |
| 9.86 | 1.2223 | 72.62 deg | 75.02 deg | 68.92 deg |
| 39.58 | 1.2569 | 95.19 deg | 103.14 deg | 92.77 deg |
| 67.97 | 1.2719 | 102.37 deg | 113.09 deg | 100.97 deg |

The chamber value agrees near the throat, where the gas it describes actually is, and overstates the available turning by 8 degrees at an area ratio of 40 and 10.7 by 68. The effective gamma understates it by 1.4 to 3.7 degrees over the same span and is the better of the two past an area ratio of about 3, which its own docstring predicted on pressure grounds.

A wall is drawn from that turning. The contour delivers an area ratio of 69.8 against the 40 requested, recorded under the contour work, and an overstated turning is the kind of error that would do it. Whether it is the cause is not established: nobody has put the two disagreements together, and that comparison is the cheapest next step available here, because it either validates the whole direction or rules it out.

The chemistry choice is worth quoting alongside it. Equilibrium against frozen on the same engine is 4 per cent in exit Mach number, 1.8 per cent in exit gamma, 15 per cent in exit temperature and 2.1 per cent in exit velocity. Every layer of the plume reads the first two, anything thermal reads the third, and the fourth is the standard performance bracket.

## Equilibrium properties in the mesh: what it would take

**No new method.** The characteristics stay the Mach lines and the compatibility relations stay as they are. What changes is the thermodynamic closure, for three reasons that all have to hold together.

The characteristic directions are Mach lines at `arcsin(1/M)` for any gas, provided the Mach number is formed with the equilibrium sound speed. CEA's numbers are self-consistent on that point: the reported sonic velocity equals `sqrt(gamma R T)` to five figures and the reported Mach number is velocity over that sound speed, so the gamma NOVA receives is the isentropic exponent belonging to the sound speed rather than the ratio of specific heats.

The compatibility relation NOVA integrates carries no gamma at all. It is the velocity form,

    d(theta) +/- cot(mu) dV / V + sin(theta) sin(mu) / sin(theta +/- mu) dx / r = 0

which is geometry, angle and velocity throughout. That is a better starting point than a Prandtl-Meyer formulation, where the closed form is written into the relation itself.

The flow is homentropic, so one table describes the whole field. Uniform chamber state, no shocks and a composition fixed by the local state put every streamline on the same isentrope, which collapses the thermodynamic state to a one-parameter family. That is what makes a tabulated gas legitimate rather than convenient.

**The work is therefore four call sites and two decisions.** `characteristics.axisymmetricMethodOfCharacteristics` reads `gas.gamma` and `gas.gasConstant` inline where it converts between Mach number, velocity and temperature, as well as through the four methods; those have to go through the interface before any other gas can be substituted. The wall projection already calls `gas.prandtlMeyerAngle`, which the tabulated angle satisfies.

The first decision is what a finished mesh answers when something asks it for a gamma. `CharacteristicGas` holds one deliberately, and its docstring warns that a net built under one gamma and read back under another is invalid. Once properties vary by station, the gamma of the net stops being a thing, and the plume march, the near-wall arrays and the run's own reporting all ask for it.

The second is the internal shock. `contour.py` carries a per-streamline stagnation pressure debit for streamlines that crossed a captured front, and those streamlines are on a different isentrope, so a single table no longer describes the field. The shock-free truncated ideal and parabolic paths are unaffected. The searched contour that carries a weak front needs either a family of tables keyed on local stagnation pressure or the rotational solve that `internalShockState.md` scopes.

**The transonic start stays as it is.** Sauer's solution is a constant-gamma result and SP-8120 allows constant specific heat there, so it can remain, but the sonic state it anchors on should come from the equilibrium table or the start line and the mesh will disagree about the throat.

**What could be checked afterwards.** A contour solved on local properties will not match any recorded baseline and there is no reference contour to say which is right. The honest checks are internal: mass conservation through the mesh, which the plume work already uses, and whether the delivered area ratio stops overshooting the requested one.

## Finite-rate chemistry: what it would take

Three things break, in increasing order of cost.

**Composition stops being a state function.** Each fluid element carries its own, evolving along its own path by `dY_i/dt = omega_i / rho`. That removes the one-parameter table outright.

**The characteristics move to the frozen sound speed.** Waves propagate faster than chemistry relaxes, so the characteristic surfaces are set by the frozen sound speed at the local composition rather than the equilibrium one. Mach number, Mach angle and every area relation shift with it, and the equilibrium sound speed that makes the tabulated gas legitimate becomes the wrong one.

**The flow becomes non-homentropic and gains a third family of curves.** Irreversible relaxation produces entropy that varies from streamline to streamline, so the relations pick up an entropy-gradient term and a chemical source proportional to the sum of enthalpy times production rate. Streamlines become a third family the mesh must carry and interpolate across, alongside the two Mach families it carries now. A two-family marching scheme becoming a three-family one is the structural change.

### What is already on hand

| Piece | Status |
|---|---|
| Species thermodynamics, NASA nine-coefficient polynomials | present, `rocketcea/thermo.inp`, 5377 species over two temperature ranges |
| Transport data | present, `rocketcea/trans.inp` |
| Equilibrium and frozen limits to bracket against | present, and measured at 2.1 per cent of exit velocity |
| Velocity-form compatibility relations, the right form to add sources to | present |
| Per-streamline stagnation bookkeeping | partly present, from the shock capture |
| Reaction mechanism with rate constants | absent |
| Stiff integrator | absent; scipy's BDF or Radau would serve |
| Frozen-composition property evaluation | absent |
| Rotational characteristics solve | absent, scoped in `internalShockState.md` |

For hydrogen and oxygen the mechanism is eight species and twenty to thirty elementary reactions. At 70 bar the choice matters rather than being a formality: the pressure-dependent `H + O2 (+M) = HO2 (+M)` channel is significant there, so the mechanism has to be one validated at high pressure rather than a generic set.

### Three tiers

**One-dimensional kinetics.** Integrate species and one-dimensional flow along the area distribution from the throat. No change to the characteristics at all. It produces the kinetic loss and shows where the composition freezes, and it is what the JANNAF simplified procedure uses for that loss factor. The largest increment in honesty for the least structural risk.

**Streamline kinetics on the existing mesh.** Solve the mesh as now, then integrate chemistry along its streamlines as a post-process. Not conservative, and the mesh never feels the heat release, but it shows the two-dimensional freezing structure and costs little once the first tier exists.

**Coupled two-dimensional kinetics.** Sources inside the unit process, frozen sound speed, rotational relations, three families. This is the standard method and a rewrite of `characteristics` rather than an extension of it.

### How it would be validated

The strong test is internal and cheap. Scaling every rate constant up by a factor of a million must reproduce CEA's equilibrium answer, and scaling it down by the same factor must reproduce CEA's frozen answer. That exercises the integrator, the thermodynamics and the coupling in one stroke against two answers NOVA already computes. Element conservation through the mesh is the second invariant and catches most implementation errors.

Past those two, the mechanism carries its own published validation range and nothing else is available: there is no measured composition profile in a rocket nozzle to compare against, and public kinetic-loss figures for specific engines are sparse.

### Whether it is worth it

The bracket bounds the prize. Equilibrium to frozen is 2.1 per cent of exit velocity on this engine, and finite rate lands inside it, nearer equilibrium for hydrogen at 69 bar where three-body recombination is fast. A coupled solve therefore buys a refinement of at most two per cent and usually well under one.

It matters more where the bracket is wider or the chemistry slower: low chamber pressure, small throats with short residence time, high area ratio extensions, and hydrocarbons, where `coolingModelState.md` records 3.7 per cent for kerosene against 2.2 for hydrogen.

The place it would matter most here is not thrust. A frozen boundary layer against a catalytic wall changes the enthalpy driving wall heat transfer, and `coolingModelState.md` already carries the narrower version of that: the film transfer coefficient reads an equilibrium conductivity whose reaction contribution is a factor of 2.7 at 3398 K. That is a boundary layer problem rather than a characteristics problem, and no amount of coupled two-dimensional kinetics in the core flow would settle it.

## Findings worth not rediscovering

**The Prandtl-Meyer integral has to resolve the sonic point.** Its integrand rises as `sqrt(M^2 - 1)` out of Mach 1, so the first stretch above the throat carries a disproportionate share of the turning. Sampled from an area ratio of 1.05 upward the integral lands a full degree low at every station downstream, and refining anywhere further out does not recover it, because the whole error is in the first interval. The module's default sampling refines to within a part in a hundred thousand of the throat, and a test records the failure mode alongside the fix.

**CEA can return a Mach number that does not advance.** Two area ratios a part in ten thousand apart can come back with the same Mach number, or one a fraction lower, at the tolerance CEA converges its own iteration to. Every relation in the gas is an interpolation on Mach number, which needs it strictly increasing, so `expansionTable` drops a station that does not advance rather than smoothing it.

**The reported gamma is the isentropic exponent, not the ratio of specific heats.** It is consistent with the reported sonic velocity to five figures, which is what the characteristics need. Anything that assumes otherwise will be subtly wrong in a way that looks like a units error.

## Reproducing

Run from the NOVA root with `C:\Users\seanb\miniconda3\python.exe`.

```
python -m pytest tests/testEquilibriumExpansion.py -q   # the gas and its integral
python featureShowcase/buildModelComparisons.py         # the turning panel, and the jacket models
```

`featureShowcase/modelComparisonsModels.png` draws the turning under local properties against both constant exponents, which is the figure to look at first.
