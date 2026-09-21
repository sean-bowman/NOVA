
[Home](../../README.md) > CEA Interface

# CEA Interface

`ceaInterface.py` supplies NOVA's combustion thermochemistry. It is a drop-in
replacement for the legacy f2py `CEAWrapper`, backed by the pip-installable
[`rocketcea`](https://rocketcea.readthedocs.io/) package.

## Contents

- [Why it was replaced](#why-it-was-replaced)
- [Usage](#usage)
- [Input modes](#input-modes)
- [Result keys and units](#result-keys-and-units)
- [Propellant names](#propellant-names)
- [Two corrected bugs](#two-corrected-bugs)
- [Performance and laziness](#performance-and-laziness)
- [Thread safety](#thread-safety)
- [Validation](#validation)

## Why it was replaced

The previous wrapper bound the NASA CEA FORTRAN source directly through f2py.
It could not run in a fresh checkout for two independent reasons:

1. No compiled `py_cea.pyd` was committed, only `.f`, `.pyf` and `.inc` sources.
   Building it required MinGW-w64 through `runSetup.bat`.
2. It called `import win32api` at module scope, so it also required `pywin32`.

`rocketcea` publishes a prebuilt `cp310-win_amd64` wheel, so `pip install
rocketcea` is the entire setup on Windows. It is actively maintained, exposes a
purpose-built rocket API, and runs in-process rather than shelling out to
`FCEA2.exe`.

Alternatives considered: NASA's own `cea` 3.2.1 is the long-term successor and
is Apache-2.0 rather than GPLv3, but it requires Python 3.11+ and NOVA targets
3.10. `CEA_Wrap` is thread-safe but roughly an order of magnitude slower per
point. `cantera` has no rocket nozzle API and would not be CEA-traceable.

## Usage

```python
from ceaInterface import CEA

case = CEA(fuelName          = 'LH2',
           oxidizerName      = 'LOX',
           chamberPressure   = 6894757.0,   # Pa
           expansionRatio    = 40.0,
           OFRatio           = 5.5,
           pressureUnits     = 'Pa')

results = case.ceaResults
print(results['combustionChamberTemperature'])   # 3398.4 K
print(results['characteristicVelocity'])         # 2339.9 m/s
print(case.nozzlePerformance['vacuumISP[s]'])    # 453.8 s
```

`OFRatio` accepts a number or the string `'maxisp'`, which runs a bounded
search for the peak-Isp mixture ratio.

## Input modes

Exactly one input normally drives a case.

| Input | Meaning | Exit keys produced |
|---|---|---|
| `expansionRatio` | Supersonic station at the given area ratio | Yes |
| `nozzleExitPressure` | Area ratio solved to hit the given exit pressure | Yes |
| `contractionRatio` | Subsonic finite-area-combustor station | No |

The contraction-ratio mode maps onto CEA's finite area combustor. In that mode
CEA treats the supplied `chamberPressure` as the **injector face** pressure and
the chamber station sits a few percent lower; both are reported separately.
`contractionRatio <= 1.0` falls back to an infinite-area chamber with a
warning, since the finite area combustor is degenerate there.

An `expansionRatio` of exactly 1.0 is clamped to `1 + 1e-6`, because the
supersonic branch is undefined at the throat. `Nozzle.py` substitutes true
throat-station values at that point anyway, but its NaN guard runs first, so
the returned numbers must be real rather than NaN.

## Result keys and units

Everything is SI. The key names and the `nozzlePerformance` sub-dictionary are
unchanged from the legacy wrapper, including the misspelled `'injectonGamma'`,
which is preserved deliberately for compatibility.

| Quantity | Unit | Stations |
|---|---|---|
| Temperature | K | injection, combustionChamber, throat, exit |
| Pressure | Pa | injection, combustionChamber, throat, exit |
| MolecularWeight | g/mol | injector, combustionChamber, throat, exit |
| GasConstant | J/kg-K | combustionChamber, throat, exit |
| Gamma | -- | injecton *(sic)*, combustionChamber, throat, exit |
| HeatCapacity | J/kg-K | injection, combustionChamber, throat, exit |
| ThermalConductivity | W/m-K | combustionChamber, throat, exit |
| Viscosity | Pa-s | combustionChamber, throat, exit |
| PrandtlNumber | -- | combustionChamber, throat, exit |
| Enthalpy | J/kg | injection, combustionChamber, throat, exit |
| Entropy | J/kg-K | injector, combustionChamber, throat, exit |
| Density | kg/m3 | combustionChamber, throat, exit |
| SonicVelocity | m/s | injector, combustionChamber, throat, exit |

Scalars: `characteristicVelocity` (m/s), `exitVelocity` (m/s), `exitMach`,
`throatMach` (always 1.0 by construction), `expansionRatio`,
`contractionRatio`, `'O/F Ratio'`, plus `massFractions`, `molFractions` and
`molWeights`, each keyed by species and then by station.

`nozzlePerformance` carries `seaLevelISP[s]`, `ambientISP[s]`, `idealISP[s]`,
`vacuumISP[s]`, the four matching thrust coefficients, and `mode`
(`Ideal` / `UnderExpanded` / `OverExpanded` / `Separated`).

### Unit conversion note

`rocketcea` runs CEA in calorie mode and returns English/CGS units, whereas the
legacy wrapper ran `output siunits` and read SI directly. Every value therefore
passes through a conversion constant defined at the top of the module.

The trap worth knowing: `BTU/(lbm-degR)` and `cal/(g-K)` are numerically
identical at 4184, but `BTU/lbm` is 2326 while `cal/g` is 4184, a factor of
1.8 apart. Enthalpies are BTU-based; heat capacities and entropies are
cal-based. If a validation number is off by a factor near 1.8, 4.184 or 9.81,
suspect a conversion constant rather than physics.

## Propellant names

Names are normalized case- and punctuation-insensitively, so `RP-1`, `rp 1` and
`RP_1` all resolve. This matters because `rocketcea`'s own card keys are case
sensitive and not always guessable: it uses `RP_1`, and a hyphenated `RP-1` is
not a valid key.

Recognized aliases cover LOX/GOX, LH2/GH2, CH4/GCH4, RP-1, N2O, N2O4/NTO, MON,
H2O2, MMH, N2H4, UDMH, A50, NH3, ethanol, methanol, propane, HTPB and HDPE. Any
exact `rocketcea` card key also passes straight through. An unrecognized name
raises `ValueError` listing the accepted alternatives.

**HDPE** is not in `rocketcea`'s built-in set and is registered from a card
lifted verbatim from the legacy wrapper:

```
fuel HDPE  C 2.0 H 4.0  wt%=100.00  h,cal=-13409.4  t(k)=1010  rho.kg/m^3=980
```

The `t(k)=1010` is deliberate: it is the HDPE pyrolysis surface temperature
used for hybrid grain analysis, not a typo for the 298.15 K standard state. Do
not "correct" it.

Custom cards are registered once per process, because `add_new_fuel` mutates
`rocketcea`'s global tables and invalidates its run cache.

### Oxidizer temperature

If `oxidizerInitialTemperature` is omitted or already matches the card's
assigned state, the built-in card is used unchanged. Otherwise a
temperature-shifted card is registered once, with the enthalpy correction
following the legacy formula `h_formation + h(T) * molarMass` through NOVA's
own `fluidProps()` accessor. That formula mixes CEA's assigned-state reference
with the CoolProp/REFPROP reference state, so it is approximate; it is kept for
continuity with prior NOVA results. If no property backend is available the
default card is used with a warning rather than failing the run.

## Two corrected bugs

The replacement fixes two defects in the legacy wrapper. Both change numbers
relative to historical NOVA output, so they are called out explicitly.

### Station index off-by-one

`CEAWrapper.py` lines 830, 831, 841, 842, 844 and 845 hardcoded COMMON block
indices `0` and `1` where every neighboring key used `self.chamberIndex` and
`self.throatIndex`. When a contraction ratio was supplied those indices shift,
so `combustionChamberThermalConductivity`, `combustionChamberViscosity` and
`combustionChamberPrandtlNumber` returned **injector-face** values, and the
`throat*` equivalents returned chamber values.

That is exactly the path NOVA's converging-section sweep uses, so converging
transport properties were pinned at stagnation values and barely varied with
contraction ratio. They now vary correctly, which shifts the converging-section
Bartz inputs.

### Exit pressure read in bar, compared against Pa

`CEAWrapper.py` line 937 read the exit pressure out of a COMMON block in bar
while `chamberPressure` and `ambientPressure` were in Pa. Two consequences:
`idealThrustCoef` collapsed onto `vacuumThrustCoef` because the subtracted term
was ~1e5 too small, and `separationPressure` collapsed so `mode` reported
`UnderExpanded` for essentially every case.

Because `Nozzle.py` sizes `engineMassFlow = thrust / (idealISP[s] * 9.81)`,
correcting `idealISP` downward raises the computed mass flow and every
downstream size. The effect is a few percent at sea-level area ratios and
smaller for high-expansion upper stages.

There is no numerical "before" to diff against: the legacy wrapper could not
execute in this checkout at all, for the two reasons listed at the top.

## Performance and laziness

Every `rocketcea` getter unconditionally re-runs the CEA FORTRAN solve; there is
no "cards unchanged, skip it" path. Any getter that requests transport
properties additionally forces `makeOutput=True`, so CEA writes and re-reads an
output file, costing roughly 26 ms against 1.7 ms for a plain solve.

Assembling all ~50 keys eagerly therefore cost about 140 ms per station, and
`Nozzle.py` calls CEA once per contour station. Two measures bring that down to
about 14 ms:

1. **One transport solve serves all three stations.** A single run fills the
   `trpts` COMMON arrays at every station, so the other two are read directly by
   index. This was verified bit-identical to calling the three separate getters.
2. **Results are grouped and computed on first access.** `ceaResults` is a
   `LazyResults` mapping. NOVA's sweeps read only transport and molecular-weight
   keys, so they never pay for thermodynamic state, species concentrations,
   performance or injector-face properties.

`LazyResults` behaves like an ordinary dict: `in`, `.get()`, `.keys()`,
`.items()`, iteration and `len()` all work, with enumeration materializing
everything first so a partially populated result is never observable.

Solver objects are cached with `functools.lru_cache` keyed on the `CEA_Obj`
constructor arguments only. Chamber pressure, mixture ratio and area ratio are
per-call and handled by `rocketcea`'s own run cache.

## Thread safety

**`rocketcea` is not thread-safe.** It carries module-level state
(`_last_called`, `_CacheObjDict`) and reads results out of process-global
FORTRAN COMMON blocks. Two threads interleaving calls silently return each
other's numbers with no exception raised: the dangerous failure mode is a wrong
answer, not a crash.

Every solve in this module is serialized behind a module-level lock. Do not wrap
CEA calls in `joblib.Parallel` with a threading backend. Process-based
parallelism is safe, since each process gets its own copy of the COMMON blocks.

### PATH sanitization

`rocketcea`'s `find_mingw_lib.add_mingw_lib()` walks `PATH` and calls
`os.add_dll_directory()` on every entry matching `*mingw64*bin`, with no
existence check. A single stale or misspelled `PATH` entry therefore raises
`FileNotFoundError` at import time. This module drops non-existent `PATH`
entries before importing `rocketcea`.

## Validation

`tests/testCeaInterface.py` covers the module in 50 tests, running in about two
seconds:

```bash
python -m pytest tests/testCeaInterface.py -v
```

The reference case is LOX/LH2 at Pc = 1000 psia, MR = 5.5, eps = 40, shifting
equilibrium, infinite-area chamber, cross-checkable against the NASA CEARun web
tool.

| Quantity | Computed | Expected |
|---|---|---|
| Chamber temperature | 3398.4 K | ~3400 K |
| Chamber molecular weight | 12.662 g/mol | ~12.7 g/mol |
| Chamber gamma | 1.1475 | ~1.14 |
| Characteristic velocity | 2339.9 m/s | ~2330 m/s |
| Vacuum Isp | 453.77 s | ~450 s |
| Chamber Prandtl | 0.5190 | ~0.5 |
| Exit Mach | 4.223 | -- |

Two checks in the suite are independent of any external reference and are the
strongest evidence the unit conversions are right:

- Recomputing Prandtl as `Cp * mu / k` reproduces CEA's own reported Prandtl
  number exactly, at every station. This validates the heat capacity, viscosity
  and thermal conductivity conversions simultaneously.
- `rho * R * T` at the chamber station recovers the input chamber pressure
  exactly, validating density, molecular weight and temperature together.
