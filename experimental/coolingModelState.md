# Cooling model extension: state of play

A record of where the cooling work stands, written to be picked up cold. It covers what exists, what is validated and against what, what was deliberately left out and why, and the findings that cost the most to establish and should not be rediscovered.

The work extended NOVA past the regenerative jacket: film cooling, radiative cooling, and a radiation-cooled nozzle extension. Along the way it turned up a defect in the jacket itself, a calibration choice in the contour solve, and two robustness holes in the gas dynamics. Those are recorded here alongside the features because they are the parts most likely to be rediscovered the hard way.

The full technical account is `docs/reports/coolingModelExtension_2026-09-11.md`. This file is the shorter view: what to pick up next, and what not to repeat.

## Where the code is

| Module | State |
|--------|-------|
| `src/NOVA/filmCooling.py` | Two closures behind `filmCoolingModel`. Hatch and Papell, NASA TN D-130, is the default; SP-8124 Appendix A entrainment is the alternative. 1424 lines, 149 tests |
| `src/NOVA/radiativeCooling.py` | Radiation primitives for the jacket, and a damped Newton solver for the wall temperature of an uncooled extension. 936 lines, 71 tests |
| `src/NOVA/gasDynamics.py` | Gained `effectiveGamma`, and two guards at the sonic point |
| `src/NOVA/regenStations.py` | Dispatches the film solve on `filmCoolingModel` and carries what each closure produces |
| `src/NOVA/materials.py` | Emissivity as a surface property with provenance, and `surfaceEmissivity` |
| `examples/filmAndRadiativeCooling.py` | Both film closures on one engine, then a coated columbium extension swept along the same contour |

The regression harness carries `contour`, `contourEffectiveGamma`, `contourParabola`, `contourToc`, `regenCircle`, `regenCircleFilm`, `regenCircleEntrainment`, `regenFluted`. Baselines are tracked in the repository so a change that moves a number shows up in the diff.

Twenty-one configuration keys were added. Of the ones that change an answer rather than switching a feature on, `filmCoolingModel` and `gammaModel` remain: each keeps the earlier behavior reachable under a named value with a harness case pinning it. `drivingTemperatureModel` did the same for the static driving temperature, but the static path was never the physical answer and was removed once the recovery temperature was carried through; there is no longer an earlier behavior to keep reachable.

## What is validated, and against what

**The jacket was driven by the static gas temperature, and now is not.** Convection is driven by the adiabatic wall temperature. NOVA computed the recovery temperature, carried it as far as the station split, and then dropped it. On the shipped LOX/LH2 example the ratio runs 1.005 at the chamber end and 1.829 at the highest-Mach station, and correcting it moved the coolant exit temperature 23.9 per cent on circular channels. This is a fix, not a feature, and it is the largest single number the work moved.

**The radiation primitives are identities, not approximations.** The fourth-power difference is factored exactly rather than linearised, so the coefficient form and the fourth-power law agree to 1e-13 at any pair of temperatures, including at one millikelvin of separation where a linearisation would show.

**The extension solver is verified against four answers it did not produce.** With conduction off it reproduces a scalar root find at every station to 1.4e-12 relative; the conduction operator converges at observed order 2.000 against a manufactured sine solution refined four times; the energy balance closes to 7e-12 of the power in; and halving the emissivity moves the peak wall temperature 5.9 per cent against the 18.9 per cent bound it must stay under.

**The entrainment closure has two exact limits and both are tested.** Zero effectiveness reproduces the station solve's own recovery array to the bit. Full effectiveness returns the coolant's recovery temperature at the core velocity, to 1e-13.

**Hatch and Papell carries the only stated accuracy in the film work**, five per cent on wall temperature over an effectiveness range of 0.2 to 1.0, and that figure is the source's claim rather than a measurement made here.

### Not validated, and why

The radiation-cooled extension has no open dataset giving a measured wall temperature distribution along a fully specified firing. What exists is a plausibility check: a 0.5 mm coated shell at an emissivity of 0.7 on a one megapascal storable apogee thruster from area ratio 20 comes out at 1544 K at the joint, against a published band near 1590 K. The engines behind that band are not specified well enough for the agreement to be an error figure.

The SP-8124 entrainment closure is calibrated rather than validated. Its entrainment multiplier is a design-chart recommendation with no stated scatter, and across the recommended band alone, 3 to 4, the peak driving temperature moves 96 K on the reference engine.

The film property correction is derived rather than cited. Its transport exponents were fitted from CEA solves at frozen composition, not taken from a source.

## Findings worth not rediscovering

**The two film closures disagree by 680 K on the same engine.** With 0.30 kg/s of hydrogen the correlation gives a peak driving temperature of 3228 K and the entrainment model 2548 K. The cause is not the effectiveness decay. Hatch and Papell blends temperatures linearly and has no term for specific heat at all, while the entrainment model mixes on enthalpy, and hydrogen carries about three times the specific heat of the exhaust. Neither is validated at rocket conditions, and the spread between them is the honest measure of how well film cooling is known here.

**The film property correction runs the unsafe way, and reading the conductivity alone gives the wrong sign.** The correlation wants properties at the mean of the gas and coolant temperatures. The conductivity does fall there, which suggests the error is conservative. It is not: at fixed pressure the density rises as 1/T and the viscosity falls, and together they move Re^0.8 further than the conductivity moves. The correction is 1.26 to 1.30 on the reference engine, so it lowers effectiveness.

**A radiation-cooled C103 extension cannot work on a 6.9 MPa hydrogen engine.** It fails at every joint area ratio from 3 to 35, by 248 K even at the far end. That is the flux, not the solver: Bartz scales as chamber pressure to the 0.8, so the same shell on a one megapascal engine sees a fifth of the coefficient. Reporting the margin alongside the temperature is what makes that fall out of the solve.

**Gas band radiation cools an extension rather than heating it.** In a chamber the wall sits far below the gas and band radiation is a source. On an extension the wall is driven by the recovery temperature while the exchange is written in the static one, and at Mach 3 those differ by more than a thousand kelvin, so the wall radiates into the gas and the exhaust becomes a second sink.

**Conduction along an extension shell barely matters.** Going from 45 to 400 W/m-K on a 0.5 mm shell narrows the temperature span by under three per cent, and the conduction length is about ten millimeters against a contour of half a meter. Worth knowing before spending effort on a two-dimensional wall solve.

**Per-station CEA already runs; it just never reaches the geometry.** There are five CEA call sites in `regenStations.py`, all inside per-station loops, and zero in `contour.py`, `chamber.py` and `plume.py`. The single design-point solve produces one exponent that drives the entire characteristics mesh.

**An effective gamma buys pressure and does not buy temperature.** Fitted so the pressure ratio and the area ratio close together at the design point, it cuts the mean pressure error from 12.8 to 4.2 per cent against CEA over area ratios 2 to 40, and moves the temperature error from 10.1 to 11.0 per cent while flipping its sign from hot to cold. One exponent cannot reproduce both the pressure-area relation and the specific heat.

**Two plotly figure paths existed, not one.** Every display site had both a `plot(fig, filename = ...)` that writes an HTML file and opens a tab, and a `fig.show()` that starts a local web server and opens another. There is no `plt.show()` on a plotly figure anywhere in the package, so selecting a non-interactive matplotlib backend suppresses none of it. A monkeypatch in the GUI runner had been aimed at the name bound in `NOVA.Nozzle` while all six write calls live in three other modules that bind it themselves, so the GUI had been opening tabs too.

## What is open

Ordered by what would change an answer most.

**The sizing march can stall where the coolant-side corrections flatten its response.** The
entrance enhancement grows as the channel's own diameter to the 0.325, since it is a function of
S/d, which opposes the usual result that a larger channel runs its wall hotter. Near the inlet the
two nearly cancel: on the reference jacket with `coolantGeometryCorrections` on, station 51 settles
9.3 K above an 800 K target and stops moving, at a radius that is neither bound. Raising the
iteration ceiling from 50 to 120 changes the residual not at all, so it is a stationary point of
the search rather than an oscillation. The corrections default off and the harness case carries a
900 K target, where the same jacket converges. What would settle it is a bracketed root find on a
station, which the march does not currently use.

**Variable-property characteristics solve.** The mesh runs on one exponent. Fitting that exponent to the design point is the mitigation that exists; removing the choice means giving the characteristics local properties, which is a different solver. `characteristics.CharacteristicGas` holds one gamma deliberately, and its docstring says a net cannot be built with one gamma and read back under another, so this is a rewrite of that module rather than an extension of it. Tracked as the largest one-dimensional dependency in `docs/NozzleContourValidation.md`.

**Molecular rather than equilibrium conductivity in the film transfer coefficient.** A Colburn form fitted on non-reacting air has no reaction conductivity in it, but the station arrays carry the equilibrium value, whose reaction contribution is a factor of 2.7 at 3398 K and 1.4 by 2269 K. Near a slot in the chamber that difference is larger than the reference-temperature effect and runs the other way. Removing it needs a frozen-composition solve at every station, and it raises the same question for Bartz, which is partly immune because `cp / Pr^0.6` largely cancels the reaction term while a bare `k` does not.

**The reactive branch of SP-8124 Appendix A.** It reads a temperature off the wall mixture ratio and the wall enthalpy through an equilibrium solve, and it is the half that would capture a fuel-rich wall burning cooler than dilution alone predicts. Leaving it out is conservative, because the non-reactive branch returns a hotter wall. The wall mixture ratio is already computed and reported.

**SP-8124 Appendix B, liquid film cooling.** Read in full and not implemented. Its film length runs through two curves on Figure B-1, a rotated scan that cannot be digitized to a useful accuracy, and the chain from them is multiplicative through a Stanton number, a surface tension, a saturation loop on the coolant partial pressure and a roughness augmentation factor. Unlike Appendix A it is an explicitly dimensional correlation in US customary units with the gravitational constant written into the entrainment parameter, and the monograph gives no worked example to check an implementation against.

**The near-wall against one-dimensional disagreement.** The characteristics solve and the station properties disagree about the wall state by up to 42 per cent in Mach number just past the throat. Making the chemistry consistent between them would say how much of that was ever two-dimensional structure. It is the reason the extension solver's near-wall comparison against CEA cannot be read as a pure gamma error.

**Two material gaps, both waiting on data rather than code.** No source gives an emissivity for any of the copper wall alloys at the as-built powder bed fusion finish a printed chamber has, so gas radiation in the jacket stays off unless somebody supplies a number they can defend. And `_WALLCURVEDATA` holds the ten jacket alloys only, so `wallMaterialCurves` substitutes GRCop-42 for a refractory metal, which conducts about eight times better; the extension solver takes conductivity as an explicit input in consequence. Both are recorded in `docs/materialsDatabaseRoadmap.md` as steps 9 and 10.

**Gas emissivity is supplied, not computed.** Leckner's 1972 correlations are the usual closed form and would slot in as a function returning that input. Their stated accuracy is about ten per cent against the spectral data they were fitted to and up to forty per cent against HITEMP-2010, so a flux computed through them inherits that.

**NASA TN D-3836 is retrieved and not digitized.** It measures gaseous film cooling at rocket conditions rather than on a flat plate, which is the gap the whole film section has. It is a scan with no text layer and its values would come off the figures the way the FIAT baseline was digitized for the ablation work. It is the nearest thing to a validation case for either film closure.

**Figures are never closed outside the test suite.** Nothing in the package calls `plt.close`, so a long scripted run accumulates them and eventually trips matplotlib's twenty-figure warning. `tests/conftest.py` closes them between tests; a script does not get that.

## Ideas raised and not pursued

**Finite-rate chemistry.** Real nozzle flow sits between equilibrium and frozen, and NOVA's CEA wrapper already takes a `frozen` flag, so the bracket is one argument away. It is worth 2.2 per cent of specific impulse on hydrogen and 3.7 per cent on kerosene. Reporting that bracket wherever a performance number is quoted buys most of the honesty that implementing kinetics would, at almost no cost.

**Plume afterburning.** The plume module does frozen ideal-gas gas dynamics with gamma passed in and no chemistry at all. For plume structure and keep-out envelopes that is defensible, and it is the lowest-value chemistry work available.

**Multiple film injection rings.** Both closures describe one slot. The configuration schema has no list field, and a single float for the injection station is what the effectiveness closure is validated for anyway.

**Re-closing the design point for film coolant.** A film is propellant bypassing the injector, so it shifts the core mixture ratio and costs specific impulse. NOVA closes its design point through CEA at one mixture ratio and does not re-close it, so the film currently appears free at the engine level even though its local effect is modeled.

## Reproducing

```bash
python -m pytest tests/ -q                            # 1141 tests
python tests/regressionHarness.py --compare           # seven cases, exact equality
python examples/filmAndRadiativeCooling.py            # both film closures, then the extension
```

Set `NOVA_HEADLESS=1` on anything that draws figures to write them without opening windows or browser tabs. The test suite and the harness set it for themselves.
