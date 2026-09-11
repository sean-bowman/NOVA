# Extending the cooling model past the regenerative jacket

NOVA modelled one cooling method. The ablative liner arrived in `ablative.py`; radiative cooling and film cooling are the two that remain, and unlike the ablative they combine with the jacket rather than replacing it.

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

## Verification status

**The radiation primitives are verified as identities, not approximations.** The factorisation is a difference of two squares applied twice, so the coefficient form and the fourth-power law are the same expression and agree to 1e-13 at any pair of temperatures. The effective coefficient and driving temperature reproduce the sum of both fluxes to the same tolerance. The radiation equilibrium root is checked by substituting the answer back into the balance it solves, with a residual below 1e-6 W/m^2.

**The grey-gas, grey-wall model is a model.** A real combustion gas radiates in bands and a real wall reflects. What is implemented is the one-dimensional grey exchange, which neglects multiple reflection between wall and gas. Hottel's enclosure correction, an effective wall emissivity of `(eps_w + 1)/2`, would raise the flux by about twelve per cent at an emissivity of 0.8. It is not applied.

**Gas emissivity is supplied, not computed.** NOVA carries no correlation for the total emissivity of water vapour and carbon dioxide. Leckner's 1972 correlations are the usual closed form and would slot in as a function returning that input. Their stated accuracy is about ten per cent against the spectral data they were fitted to, and up to forty per cent against HITEMP-2010; a flux computed through them inherits that.

**The recovery temperature itself is textbook rather than correlated.** `Pr^(1/3)` is the standard turbulent recovery factor and the expression is the definition of the adiabatic wall temperature. There is nothing to validate; there was something to connect.

**Everything the jacket already could not validate, it still cannot.** The coolant-side correlation remains unvalidated, and the fifty-fifty fluted Nusselt blend remains a correlation of convenience with no source stating it. Driving the solve with the right gas temperature does not make the coolant side any more defensible, and a result that rests on it should still be read that way.

---

## Sources

`docs/references_filmAndRadiativeCooling_2026-09-11.md` carries the annotated bibliography, including the four sources that could not be reached.
