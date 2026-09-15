# Extending the cooling model past the regenerative jacket

NOVA modeled one cooling method. The ablative liner arrived in `ablative.py`; radiative cooling and film cooling are the two that remain, and unlike the ablative they combine with the jacket rather than replacing it.

Adding them turned up a defect in the jacket itself that had to be fixed first, and this records that fix along with the groundwork that preceded it.

---

## The data map was dead code

`flutedHeatTransferStudyPath` pointed at `assets/FlutedChannelHeatTransferStudy.csv`, which the repository has never contained. Every entry into the branch raised immediately. It cost 118 references in `regenThermal.py` and 24 more across six other files, and it was one of three near-identical copies of the hot wall convergence loop.

Removing it took 241 lines out and left two copies, which were then reduced to one. The copies had already drifted: the fluted one converged to 0.01 K, the circular one to 0.1 K, and the circular one carried an extra `locals()` NaN sweep inside the loop that the other did not and that had never fired.

---

## The jacket was driven by the static gas temperature

Convection into a wall is driven by the adiabatic wall temperature. For a turbulent boundary layer that is the static temperature raised by the recovery factor times the dynamic rise:

```
T_aw = T_static (1 + Pr^(1/3) (gamma - 1)/2 M^2)
```

NOVA computes exactly that at `chamber.py:559-560` and carries it to `regenStations.py:524` as `regenSectionNearWallRecoveryTemperature`. It was then never trimmed and never passed on. `channelSizing` handed the thermal model the static array, and the flux was driven by it.

### Magnitude on the shipped example

Measured on `regenExample.json`, a LOX/LH2 engine with a circular-channel jacket over a contour reaching Mach 3.74:

| | static | recovery | change |
|---|---|---|---|
| Driving temperature ratio along the jacket | 1.000 | 1.005 to 1.829 | |
| Driving temperature at the highest-Mach station | 1672.7 K | 3059.5 K | +1386.8 K |
| Peak hot wall temperature | 482.9 K | 594.4 K | **+111.5 K, +23.1 %** |
| Coolant exit temperature, circular channels | 150.07 K | 185.89 K | **+23.9 %** |
| Coolant exit temperature, fluted channels | 157.03 K | 195.48 K | **+24.5 %** |
| Coolant exit pressure, circular channels | 11.885 MPa | 11.847 MPa | -0.32 % |
| Coolant exit pressure, fluted channels | 10.986 MPa | 10.612 MPa | -3.40 % |

The ratio is 1.005 at the chamber end, where the flow is nearly stagnant and the recovery rise is nothing, and 1.83 at the exit end of the jacket. That is the shape of the defect: it was invisible where most people look and worst where the jacket ends.

### The channel radii did not move, and that is worth understanding

The sizing loop converges each station's channel radius so the hot wall runs at `maxWallTemperature`, which this configuration sets to 800 K. Twenty-four per cent more heat moved no radius at all, to the bit.

The reason is that **this example is nowhere near its wall temperature limit**. The hot wall runs 294 to 483 K under the static model and 400 to 594 K under the recovery model, against a target of 800 K. No station reaches it. The radius is therefore set by the largest channel that fits between its neighbours, not by temperature, and the extra heat shows up entirely as coolant temperature rise.

On an engine sized closer to its limit the same change would move the geometry instead, and it would move it a long way. The correction should not be read off this example as geometrically harmless.

---

## What the change consists of

`regenSectionNearWallRecoveryTemperature` now follows the same path the other three near-wall arrays already took: declared on `RegenChannelState`, trimmed and interpolated at the four sites that trim the others, passed through `_sizingState` into `ChannelSizingState`, and written into the thermal model's input dictionary.

It arrives under the key `drivingTemperature`, named for what it is rather than for what produced it. A film coolant will write the same key, and the thermal model never learns which of them did.

`drivingTemperatureModel` selects between `'recovery'` and `'static'`, defaulting to `'recovery'`. The static model is kept so the earlier answer stays reachable and recorded rather than only described, and the regression harness carries a `regenCircleStatic` case that pins it. It is not a default anybody should choose, and the configuration field says so.

The convergence tolerance is now 0.01 K for both channel families. Unifying it moved the circular result by about 4e-10, which is why it was done here rather than in a change that was supposed to move nothing.

---

## Radiation and blowing, present but inert

Both terms now sit in the station solve unconditionally, with no branch around the physics, and a jacket that names neither reproduces one from before they existed to the bit. Three things make that exact rather than close:

- `blowingCorrection(0)` returns exactly 1.0, and multiplying by 1.0 is bitwise neutral.
- The radiative coefficient returns exactly 0.0 when either emissivity is zero.
- The driving temperature array is bound to the near-wall temperature, not copied, when none is supplied.

### Radiation as algebra rather than linearisation

Convection is driven by the adiabatic wall temperature and radiation by the gas temperature, and they are not the same quantity. Writing radiation as a coefficient on the convective potential puts a singularity where the wall reaches the driving temperature, because convection vanishes there and radiation does not.

The way out is exact. The fourth-power difference factors:

```
sigma (T_g^4 - T_w^4) = sigma (T_g + T_w) (T_g^2 + T_w^2) (T_g - T_w)
```

so radiation becomes a coefficient on its own potential, smooth and finite everywhere. The two are then combined into one effective coefficient and one effective driving temperature that reproduce the sum of both fluxes at any wall temperature:

```
h_eff = h_conv + h_rad
T_eff = (h_conv T_aw + h_rad T_g) / h_eff
```

The resistance network keeps its shape and both wall temperature back-outs stay correct rather than merely unchanged. `tests/testRadiativeCooling.py` asserts the identity to 1e-13, including at one millikelvin of separation where a linearisation would show.

There is one deliberate branch on exact zero, in `effectiveGasSideDriving`. Without radiation the algebra returns `(h T) / h`, which is not bitwise `T`.

---

## Emissivity, and what is not known

A radiation-cooled wall settles where its own emissivity puts it. The store now carries one value: 0.7 for R512E coated columbium, from Levine and Merutka, NTRS 19740015000, whose summary reports emittance falling generally below that as surface refractory metal pentoxides form.

Three caveats travel with it, and a test pins each. The substrates measured were FS-85, Cb-752 and C-129Y rather than C103, so it transfers on the coating being the emitting surface. The environment was a plasma arc at 4.9 torr of air near 1390 degC, which oxidises far harder than a vacuum extension, so this is how far emittance can fall rather than where it sits in service. And no beginning-of-life value is recorded because none was found.

Nothing else carries an emissivity. Emissivity is a property of a surface rather than of an alloy: polished and oxidised samples of the same metal differ by an order of magnitude, and the surface changes during a firing. No source gives one for any of the copper wall alloys at the as-built powder bed fusion finish a printed chamber has. The accessor refuses rather than substituting, and gas radiation in the jacket is therefore off unless somebody supplies a number they can defend.

### The quarter-power rule oversells it

Halving emissivity is often quoted as raising the equilibrium wall temperature by `2^(1/4)`, about 19 per cent. That holds only where the wall sits far below the gas driving it, so the convective input barely notices the wall moving. In a real nozzle it does notice, because a hotter wall takes in less:

| Convective coefficient [W/m^2 K] | Wall temperature rise on halving emissivity |
|---|---|
| 5 | 17.2 % |
| 50 | 15.6 % |
| 500 | 12.0 % |
| 5000 | 5.5 % |

The bound is real and it is never reached. A test pins it as a strict inequality.

---

## The film closure, and the property temperature it needs

`filmCooling.py` carries Hatch and Papell, NASA TN D-130, equation (12). It was chosen over the SP-8124 entrainment model for one reason: it arrives with a stated accuracy from its own source, five per cent on film-cooled wall temperature over an effectiveness range of 0.2 to 1.0, and it is the only film closure found that does. That accuracy was earned on a flat plate below 1100 K at 32 to 317 m/s in a constant-area duct.

The film solves once from the station gas state, marching forward from its slot while the jacket marches back from the coolant inlet. It writes the `drivingTemperature` key the recovery fix created, so the jacket never learns a film produced it.

### Assumption 6 asks for properties at a temperature NOVA does not carry

The correlation evaluates every property at the arithmetic mean of the static gas and coolant temperatures. A station carries one temperature, the static gas one, because Bartz and the jacket both want that and nothing else ever wanted a second. Bartz sidesteps the same question with a closed-form property ratio, its `sigma`, rather than a second property evaluation, so the gap never surfaced until a second consumer appeared.

Reading the conductivity alone suggests the correction is conservative. It is not. At fixed pressure the density goes as `1/T` and the viscosity falls, and together they raise `Re^0.8` by more than the conductivity loses. Fitting the transport power laws from CEA solves at frozen composition, which sweeps temperature by expansion while holding the mixture fixed:

| Propellant | `k ~ T^a` | `mu ~ T^b` | `Pr ~ T^c` | net power on `h` |
|---|---|---|---|---|
| LH2 / LOX, O/F 5.5 | 1.000 | 0.816 | 0.071 | -0.431 |
| LH2 / LOX, O/F 7.0 | 1.053 | 0.813 | 0.011 | -0.394 |
| LH2 / LOX, 2 MPa | 0.997 | 0.808 | 0.065 | -0.430 |
| RP-1 / LOX, O/F 2.4 | 0.979 | 0.739 | -0.058 | -0.429 |
| CH4 / LOX, O/F 3.4 | 1.030 | 0.758 | -0.068 | -0.397 |

The net power is what reaches the answer, and across hydrogen, kerosene and methane at two mixture ratios and two chamber pressures it stays inside 0.394 to 0.431. That is a two per cent spread in the correction, which is why fixed exponents are defensible and a per-run fit is not worth the CEA calls. `referenceTemperatureCorrection` applies `(T*/T)^(a - 0.8 - 0.8b + 0.3c)` to the transfer coefficient, and on the reference case it runs 1.262 to 1.300.

Correcting it moved the reference film case and nothing else. Effectiveness fell at every station, the peak driving temperature rose 3137 to 3228 K, and the coolant exit temperature rose 171.8 to 176.6 K. The four non-film baselines did not move a value.

### What is still outstanding, and why it is left

The conductivity a station carries is the equilibrium value, whose reaction contribution is a factor of 2.67 at 3398 K, 2.42 at 3193 K and 1.37 by 2269 K. By the film mean temperature it has vanished. A Colburn form fitted on non-reacting air has no such term in it, so the molecular conductivity is the one it contemplates, and near a slot in the chamber that discrepancy is larger than the reference-temperature effect and runs the other way. Removing it needs a frozen-composition solve at every station, and it raises the same question for Bartz, which is partly immune because `cp / Pr^0.6` largely cancels the reaction term while a bare `k` does not. That is a decision about the jacket, not a bug in the film, and it is recorded rather than taken.

### Acceleration and turning, measured rather than asserted

SP-8124 states that acceleration and flow turning are very significant for film cooling and that accounting for them is the key to predicting coolant requirements. Two measurements say what that means here.

Acceleration does reach the answer, through the local coefficient: over the 43 mm the film survives on the reference case, `h` rises by a factor of 1.74 on velocity alone. Relaminarisation is not the missing mechanism either. The acceleration parameter `K = (nu/U^2) dU/ds` peaks at 1.6e-6 against the 3e-6 threshold, and no station exceeds it on either the 60 or the 100 point grid.

What is genuinely absent is a term for the extra entrainment a pressure gradient and a curved wall drive beyond what the local Reynolds number carries, and the one term that could have absorbed it cannot. The velocity-ratio correction is arctan-bounded at `1 + 0.4 pi/2 = 1.628`, and at the slot it already reads 1.539. It has spent 86 per cent of its range before the film has gone anywhere, so a doubling of core velocity moves it three per cent. Turning has no term at all: the throat radius of curvature is 41 mm and the film is turned through nine degrees of wall angle over the length it survives.

The remedy is the SP-8124 entrainment model, whose position-dependent multiplier is exactly an empirical accounting for acceleration and turning. Adopting it trades a stated accuracy for a design chart with no stated scatter, which is the trade rather than an improvement, and anything built on it has to ship labeled calibrated.

---

## The radiation-cooled extension

`regenStations.py` already populated five arrays describing the exhaust past the end of the jacket, and nothing read any of them. `radiativeNozzleExtension` does.

### Why it needs a different solver

The jacket converges by successive substitution, and it contracts because the only wall-temperature dependence is Bartz's `sigma`, which is weak. On an uncooled shell radiation is the balance, and its derivative gains `4 eps sigma T^3`, about 150 W/m^2 K at 1500 K and an emissivity of 0.8. That is comparable to the convective coefficient, the map stops contracting, and the problem becomes a nonlinear two-point boundary value problem. It is solved by damped Newton on a tridiagonal Jacobian, per unit area of a thin shell along arc length `s`:

```
(1/r) d/ds [ r k t dT/ds ] + h_g (T_aw - T_w)
    + eps_i eps_g sigma (T_g^4 - T_w^4) - eps_o F_o sigma (T_w^4 - T_sink^4) = 0
```

The starting guess is the pointwise balance with conduction switched off, iterated to self-consistency in both the Bartz coefficient and the band term. That matters: without the iteration it is a guess rather than the zero-conduction answer, and the difference between it and the solution would not be conduction alone.

### The band term can cool

In a chamber, band radiation heats the wall. On an extension it usually does not. The wall is driven by the recovery temperature while the exchange is written in the static one, and at Mach 3 those differ by more than a thousand kelvin. A wall settling above the static gas radiates into it, so the exhaust becomes a second sink alongside space. On the reference extension the band term is about minus 4 per cent of the convective flux.

### Verification

| Check | Result |
|---|---|
| Conduction off, against a scalar root find at every station | 1.4e-12 relative, one Newton step |
| Conduction operator, manufactured sine solution refined four times | observed order 2.000 |
| Energy balance: power in against power out plus the joint | 7e-12 of the power in |
| Emissivity halved, against the `2^0.25` bound | 5.9 per cent against 18.9 |
| Through-thickness drop `q t / k`, reported not asserted | a few kelvin against a wall above 2000 K |

Conduction along the shell barely matters and the solver says so: going from 45 to 400 W/m-K on a 0.5 mm shell narrows the temperature span by under three per cent, and the conduction length `sqrt(k t / h)` is about ten millimeters, so the joint with the jacket reaches only the first few stations. That is worth knowing before spending effort on a two-dimensional wall solve.

### Plausibility, labeled as such

No open dataset gives a measured wall temperature distribution along a fully specified firing, so there is nothing to validate against. Published coated-columbium extension temperatures near 1590 K exist as a band. Against it, a 0.5 mm coated shell at an emissivity of 0.7 comes out at 1544 K at the joint on a one megapascal storable apogee thruster running from area ratio 20, and 1372 K on a 0.7 megapascal reaction control thruster from area ratio 30. Those sit where the literature puts them, but the engines behind the band are not specified well enough for the agreement to be an error figure.

### What the solver says about NOVA's own reference engine

A coated C103 shell fails everywhere on the 6.9 MPa LOX/LH2 contour:

| Joint area ratio | Peak wall [K] | Margin against the 1673 K vacuum limit [K] |
|---|---|---|
| 3.0 | 2763 | -1090 |
| 9.9 | 2368 | -695 |
| 20.1 | 2116 | -443 |
| 29.9 | 1975 | -302 |
| 34.8 | 1921 | -248 |

That is the flux rather than the solver. Bartz scales as chamber pressure to the 0.8, so the same shell on a one megapascal engine sees a fifth of the coefficient and settles about thirty per cent cooler. Reporting the margin alongside the temperature is what makes that conclusion fall out of the solve instead of being left to the reader.

---

## The second film closure, and why it disagrees

The acceleration and turning limitation above has one remedy, and it is the model SP-8124's own design criteria recommend. `filmCoolingModel` now chooses between two closures.

### What Appendix A actually says

The monograph is a scanned image with no text layer, so the appendix was read page by page. Its gas film model treats the film as a mixing layer that starts holding all the coolant and entrains core flow as it runs:

```
W_E/W_c = ((W - W_c)/W_c) [ 2 z - z^2 ],   z = psi_r xbar / (r_i - s_i)

xbar    = integral of (r_i/r) ((rho_e u_e)_2D / (rho_e u_e)_1D) psi_m ds, from the slot
psi_r   = 0.1 (u_c/u_e) / [ (rho_c/rho_e)^0.15 (rho_c u_c s_i / mu_c)^0.25 f ]
```

Every group is dimensionless, so it works in SI without conversion. Effectiveness follows from the entrainment ratio through Figure A-2, and the adiabatic wall temperature from an enthalpy balance across the mixing layer.

Three details are worth recording because they are decisions rather than transcription.

The bracket `2z - z^2` is the fraction of the core the mixing layer has swallowed and it reaches one at `z = 1`. Past that the parabola turns over, which would say a film entrains less the further it runs, so `z` is held at one. The source does not say to do this; it is what the expression means.

Figure A-2 prints both of its limits, `eta = 1` below an entrainment ratio of 0.06 and `eta = 1.32/(1 + W_E/W_c)` above 1.4, and both are reproduced exactly. Between them the source gives a plotted curve and no equation, and what is used is a cubic Hermite in the logarithm of the abscissa, flat where it leaves one and matching the value and slope of the asymptotic form where it joins it. Clipping the asymptotic form at one would have been simpler and is wrong in the unsafe direction: that form reaches one only at a ratio of 0.32 while the source says effectiveness leaves one at 0.06, so the real curve drops earlier than the formula does.

The reactive branch is not implemented. It reads a temperature off the wall mixture ratio and the wall enthalpy through an equilibrium solve, which is the half of Appendix A that would capture a fuel-rich wall burning cooler than dilution alone predicts. Leaving it out is conservative, because the non-reactive branch returns a hotter wall. The wall mixture ratio is computed and reported anyway.

### Two limits that had to be exact

The non-reactive expression carries an enthalpy defect term, `(1 - Pr^1/3)(H_o,e - H_e)`, which is `C_p,e (T_o,e - T_recovery)` by definition. Written that way the closure has two exact limits, and both are tested rather than asserted:

| Limit | Result |
|---|---|
| Zero effectiveness against the station solve's own recovery array | identical, to the bit |
| Full effectiveness against the coolant's recovery temperature at core velocity | exact to 1e-13 |

The second limit is why the coolant temperature is read as a total rather than a static one. The source writes it against `H_o,e` in a difference of total enthalpies, and only that reading puts a wall bathed in pure coolant at the coolant's recovery temperature instead of below it.

Getting the first limit required building the local total temperature the same way NOVA builds the recovery temperature, from one chamber gamma and the station Mach array. Using the chamber stagnation temperature instead was wrong by up to 130 K, because a reacting expansion does not follow a constant-gamma isentrope.

### The two closures disagree by 680 K

On the reference engine with 0.30 kg/s of hydrogen injected at the chamber end:

| | no film | Hatch and Papell | SP-8124 entrainment |
|---|---|---|---|
| peak driving temperature [K] | 3397 | 3228 | 2548 |
| film survival [mm] | n/a | 43.0 | 29.1 |
| coolant exit temperature [K] | 200.1 | 179.6 | 147.6 |

The correlation's effectiveness collapses within a hundred millimeters; the entrainment model holds about 0.08 the whole way down the nozzle. The larger cause is elsewhere though. Hatch and Papell blends temperatures linearly and has no term for specific heat at all, while the entrainment model mixes on enthalpy. Hydrogen carries roughly three times the specific heat of the exhaust, so a small entrained fraction of it pulls the wall down hard, and only one of the two closures can see that.

Neither is validated at rocket conditions. The spread between them is a fair statement of how well film cooling is known here, and it is larger than any other disclosed uncertainty in the cooling model.

### What the multiplier costs

`psi_m` is where SP-8124 puts acceleration and turning, and it is a design-chart recommendation rather than a measured curve. Across the recommended injection band alone, 3 to 4, the peak driving temperature moves 96 K on the reference engine. That is the model's uncertainty before anything else is counted, and it is why the closure ships labeled calibrated rather than validated.

### Appendix B is not implemented

The liquid film model was in scope and is left out. Its film length runs through two curves on Figure B-1, a rotated scanned plot that cannot be digitized here to an accuracy worth carrying, and the chain from them is multiplicative: a Stanton number, a surface tension, a saturation loop on the coolant partial pressure, and a heat-transfer augmentation factor for liquid surface roughness. Unlike Appendix A it is an explicitly dimensional correlation in US customary units with the gravitational constant written into the entrainment parameter, and the appendix states that only the numerical values of those units may be used. Implementing it from a scan with no worked example to check against would produce a number nothing could verify, which is worse than not having it.

---

## Verification status

**The radiation primitives are verified as identities, not approximations.** The factorisation is a difference of two squares applied twice, so the coefficient form and the fourth-power law are the same expression and agree to 1e-13 at any pair of temperatures. The effective coefficient and driving temperature reproduce the sum of both fluxes to the same tolerance. The radiation equilibrium root is checked by substituting the answer back into the balance it solves, with a residual below 1e-6 W/m^2.

**The grey-gas, grey-wall model is a model.** A real combustion gas radiates in bands and a real wall reflects. What is implemented is the one-dimensional grey exchange, which neglects multiple reflection between wall and gas. Hottel's enclosure correction, an effective wall emissivity of `(eps_w + 1)/2`, would raise the flux by about twelve per cent at an emissivity of 0.8. It is not applied.

**Gas emissivity is supplied, not computed.** NOVA carries no correlation for the total emissivity of water vapour and carbon dioxide. Leckner's 1972 correlations are the usual closed form and would slot in as a function returning that input. Their stated accuracy is about ten per cent against the spectral data they were fitted to, and up to forty per cent against HITEMP-2010; a flux computed through them inherits that.

**The recovery temperature itself is textbook rather than correlated.** `Pr^(1/3)` is the standard turbulent recovery factor and the expression is the definition of the adiabatic wall temperature. There is nothing to validate; there was something to connect.

**Everything the jacket already could not validate, it still cannot.** The coolant-side correlation remains unvalidated, and the fifty-fifty fluted Nusselt blend remains a correlation of convenience with no source stating it. Driving the solve with the right gas temperature does not make the coolant side any more defensible, and a result that rests on it should still be read that way.

---

## Sources

`docs/references_filmAndRadiativeCooling_2026-09-11.md` carries the annotated bibliography, including the four sources that could not be reached.
