# The gas-side correlation constant along the wall

Bartz carries one correlation constant from the injector face to the nozzle exit. Measurements do not support that. Schacht, Quentmeyer and Jones instrumented five stations of a LOX/GH2 chamber and reduced the data as $St^*Pr^{*0.7} = C\,Re^{*-0.2}_d$, and the constant they measured varies by a factor of 1.7 along the wall: 0.0257 in the cylindrical barrel against 0.0148 at the throat (NASA TN D-2832). `gasSideAxialModel = 'measured'` scales NOVA's gas-side coefficient by that distribution, normalized to the barrel. It leaves the barrel where Bartz puts it and takes 41 percent off the throat.

This is a calibration from one engine, not a validated correlation. What the data does validate is the scaling NOVA already uses.

## The measurement

A copper heat-sink chamber with a 5 in throat, a 10.77 in bore, 14.5 in from injector face to throat, L\* of 54 in, contraction and expansion area ratio 4.64, fired on liquid oxygen and gaseous hydrogen through a 234-element coaxial injector at 26 000 lbf. Chamber pressures ran 150 to 1000 psia at 11 to 17 percent hydrogen by weight, with combustion efficiency averaging 98 percent of equilibrium. Wall temperature transients on inserted copper rods were reduced through a one-dimensional semi-infinite slab solution.

| Station | A/A* | C | Standard deviation | 95 percent band |
|---|---|---|---|---|
| 1, cylindrical barrel | 4.64 | 0.0257 | 10.9 % | ±21.8 % |
| 2, converging section | 1.78 | 0.0240 | 16.3 % | ±32.1 % |
| 3, throat | 1.00 | 0.0148 | 13.5 % | ±26.3 % |
| 3 averaged over three circumferential stations | 1.00 | 0.0151 | 13.2 % | ±25.8 % |
| 4, diverging | 1.27 | 0.0153 | 10.4 % | ±20.3 % |
| 5, diverging | 3.33 | 0.0188 | 7.9 % | ±16.0 % |

The throat constant is 42 percent below the 0.026 the Bartz form carries. Three other nozzle configurations recomputed the same way give throat constants of 0.019, 0.017 and 0.023, and a fourth about 0.018, so the direction is not peculiar to this hardware. An independent comparison in a solid motor nozzle found measured coefficients below Bartz in the convergent section and at the throat as well.

## What is validated and what is calibrated

**Validated: the pressure scaling.** One constant per station fits the whole 150 to 1000 psia range, a factor of 6.7 in chamber pressure, with a standard deviation of 8 to 16 percent depending on the station. That is a statement about the Reynolds scaling rather than about the constant, and it is the scaling NOVA already has: the correlation makes the coefficient proportional to mass flux to the 0.8, and so does Bartz through its $(P_c/c^*)^{0.8}$ term. `tests/testGasSideAxial.py` holds NOVA to that exponent across the measured range.

**Calibrated: the axial distribution.** The factor is the measured constant at a station over the measured constant in the barrel. It reproduces the measured shape and adopts none of the absolute level, because the absolute level is not transferable: the source reports that changing which transport property data the reduction used moved every constant by about 30 percent together. A ratio between two stations of the same reduction survives that; a single constant does not.

**Not adopted: the property evaluation.** The constants were reduced with properties at Eckert's reference enthalpy, $H^* = H_s + 0.5(H_w - H_s) + 0.22\,Pr^{*1/3}(H_{tot} - H_s)$, and the local static pressure, from an equilibrium solution. NOVA evaluates its gas properties at the station state through CEA, which cannot solve for equilibrium at an arbitrary enthalpy and pressure. Taking only the ratio is what makes the difference second order rather than first.

## What it changes

Both cases are the shipped 100 kN LOX/LH2 jacket, sixty circular or 160 rectangular channels in GRCop-42, hydrogen at 3.4 kg/s from 12 MPa and 30 K, with nothing changed but the model.

| | Uniform | Measured | Change |
|---|---|---|---|
| **Circular channels**, packing-bound at every station | | | |
| Coolant exit temperature | 266.8 K | 230.8 K | -36.0 K |
| Jacket pressure drop | 0.174 MPa | 0.139 MPa | -19.7 % |
| Channel radius | 2.355 mm | 2.355 mm | unchanged |
| **Rectangular channels**, sized against a 600 K wall | | | |
| Throat channel depth | 5.58 mm | 6.00 mm | at the depth cap |
| Coolant exit temperature | 289.8 K | 247.6 K | -42.2 K |
| Jacket pressure drop | 1.003 MPa | 0.716 MPa | -28.6 % |

Where the channel is bound by what packs around the wall, as the circular jacket is everywhere, the geometry cannot respond and the whole effect lands on the coolant: 36 K less pickup and a fifth less pressure drop. Where the channel is sized against a wall temperature, as the rectangular jacket is at the throat, the solve opens the channel until it reaches its depth cap and the pressure drop falls by nearly a third.

For an expander cycle both directions matter: the wall is further from its limit, and the turbine has 36 to 42 K less enthalpy rise to work with.

## Limits

- One engine, one injector, one propellant combination, one contraction ratio. The source states that the constants are for that geometry, propellant and injector and are not to be used universally, and this report makes no wider claim for them.
- The chamber station sits 0.53 chamber diameters from a 234-element injector designed for uniform mass flux. A different injector puts a different distribution near the face: single-element hardware peaks one to two diameters downstream at roughly twice the level either side of the peak.
- Between stations the constant is interpolated linearly in area ratio, and outside the measured range it is held at the end value. Neither is a physical model.
- The same area ratio carries different constants upstream and downstream of the throat, so the branches are kept apart. A station is placed by its Mach number.
- The distribution applies only where NOVA computes the coefficient itself. A prescribed coefficient, which is what a comparison against measured heat flux supplies, is used as given.

## What would close the gap

Equilibrium properties at an arbitrary enthalpy and pressure would allow the reference-enthalpy reduction to be reproduced, and with it the absolute constants rather than their ratio. `rocketcea` exposes transport properties at the chamber, throat and exit only, so this needs either an equilibrium backend that solves an enthalpy-pressure problem or a mixture transport model built on the species fractions CEA already returns.

A second dataset with a different injector and contraction ratio would separate what is geometry from what is injector, which one engine cannot do.

## Sources

Annotated in [references_gasSideHeatTransfer_2026-09-22.md](../references_gasSideHeatTransfer_2026-09-22.md).
