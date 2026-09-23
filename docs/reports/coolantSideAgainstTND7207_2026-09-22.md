# The coolant side against NASA TN D-7207

Schacht and Quentmeyer measured local coolant-side heat transfer in a liquid-hydrogen cooled LOX/GH2 thrust chamber, on the same hardware whose gas side is reported in TN D-2832, and published both the corrections a station correlation needs and a table of measured-to-predicted ratios for cryogenic hydrogen. Three things come out of comparing NOVA against it.

**The entrance and curvature corrections are implemented and validated against the source's own tabulated values.** `coolantGeometryCorrections` switches them on.

**NOVA's roughness credit is wrong in kind, and this is the second independent measurement that says so.** At the 35 um roughness NOVA assumes for a printed channel, its coefficient runs 1.5 to 5 times the measurements. At the roughness those tubes actually had, it lands within about a factor of 1.5.

**The comparison is bracketed, not tight.** The published ratios carry a bulk state but no Reynolds number, so NOVA's position depends on where in a plausible Reynolds range each point sat. It is a sensitivity-bounded comparison, like the Carlile one, rather than a validation.

## The corrections

A coolant correlation is written for a straight passage with a developed boundary layer. A rocket passage is neither, and the report gives the two corrections it found necessary.

**Entrance.** Boelter, Young and Iversen's fit for a 90 degree entrance, $\varphi_2 = 2.88\,(S/d)^{-0.325}$, never below 1, with $S$ measured along the channel from the inlet manifold. It reaches 1 at $S/d$ near 33.

Table III of the report lists the coefficient it used at four length-to-diameter ratios. `tests/testCoolantGeometryFactors.py` holds the implementation to those published numbers:

| S/d | Published | NOVA |
|---|---|---|
| 7.5 | 1.5 | 1.485 |
| 25 | 1.01 | 1.009 |
| 40 | 1 | 1 (fit gives 0.87, clamped) |
| 46 | 1 | 1 (fit gives 0.83, clamped) |

**Curvature.** Ito's resistance ratio for turbulent flow in a curved pipe, $\varphi_1 = [Re\,(R/r)^2]^{0.05}$ for $Re\,(R/r)^2 > 6$, with $R$ the passage's own cross-sectional radius and $r$ the radius of the bend. The report built an enhancement from its station data that peaks at 1.52 about 25 diameters past the tangent point, and states that this is the magnitude Ito's equation predicts for that geometry. NOVA reads the radius of curvature it already computes for bend pressure losses.

Neither correction knows which way a passage bends. Measured enhancement takes roughly 15 diameters to build and 14 or more to decay, so through a throat, where the wall turns one way and then the other within a few diameters, these are upper bounds rather than distributions. The report says as much: five stations were not enough to describe the curvature and reverse-curvature region.

## Where NOVA sits against the measurements

Table III reports the ratio of measured to predicted coefficient for four correlations at five bulk states, covering 30.4 to 61.3 K at 2.8 to 4.9 MPa. That is hydrogen through and above its pseudo-critical region, which is where NOVA's shipped jacket starts: 30 K at 12 MPa.

Taking their recommended correlation as the reference, $St\,Pr^{0.6} = 0.023\,Re^{-0.2}$, and reading their measured-to-predicted ratio, NOVA's Gnielinski coefficient can be placed against the measurement at each state. The Reynolds number is not reported, so the comparison runs over $5\times10^5$ to $4\times10^6$.

| Bulk state | Measured / theirs | Measured / NOVA at 1.9 um | Measured / NOVA at 35 um |
|---|---|---|---|
| 30.4 K, 2.82 MPa, S/d 7.5 | 2.05 | 0.98 to 1.42 | 0.45 to 0.68 |
| 34.9 K, 4.86 MPa, S/d 7.5 | 1.46 | 0.70 to 1.02 | 0.32 to 0.48 |
| 40.5 K, 2.78 MPa, S/d 40 | 1.13 | 0.50 to 0.74 | 0.25 to 0.38 |
| 47.0 K, 4.85 MPa, S/d 25 | 1.14 | 0.54 to 0.78 | 0.25 to 0.37 |
| 61.3 K, 4.82 MPa, S/d 46 | 0.91 | 0.46 to 0.66 | 0.20 to 0.30 |

A ratio below 1 means NOVA predicts more heat transfer than was measured.

Two readings. At a roughness like the one those tubes had, 1.905 um rms on a passage of a few millimetres, NOVA is high by up to a factor of 2 at the warm, developed end and about right at the cold entrance. At the 35 um NOVA assumes for a printed channel, it is high by 1.5 to 5 times everywhere.

The cold end is the interesting one. Every correlation in the report underpredicts there: measured over predicted is 2.05 for their own correlation, 3.54 for Hess and Kunz, 3.92 for the film correlation. Hydrogen near its pseudo-critical line transfers more heat than a correlation fitted on moderate property variation expects, which is the whole reason that report exists. NOVA's roughness credit happens to push in the same direction at that station, which makes it look better there than it is.

## What the source says about roughness

The report computes friction factors with a surface irregularity of 1.905 um rms and states plainly that **no roughness effects were accounted for in the heat transfer**. Its conclusion is that standard friction factors with roughness taken into account predict the pressure drops well, alongside a heat transfer correlation carrying no roughness term at all.

NOVA does the opposite: it feeds the rough-wall Swamee-Jain factor into Gnielinski, so roughness raises the Nusselt number in proportion to the friction it adds. That is what the Carlile comparison found from an inferred wall temperature, and it is what these ratios show directly against measured coefficients.

The physical position sits between the two. Dipprey and Sabersky measured rough tubes and found heat transfer rising with roughness, but by less than friction does. So a roughness term belongs in the heat transfer, bounded well below the friction multiplier, rather than either omitted outright or credited in full.

## Status

Calibrated and disclosed, not validated:

- The entrance and curvature factors reproduce the source's published values, which validates the implementation against the numbers it came from. What is not established is that they are right for NOVA's channel shapes: they were fitted on round tubes, and a high aspect ratio rectangle has a different developing length and a different secondary flow.
- The comparison of NOVA's coefficient against the measured ratios is bracketed on Reynolds number and on the roughness of hardware from two other experiments. It bounds the error; it does not measure it.
- The corrections default off, so every result recorded before this exists is unaffected.

## Sources

Annotated in [references_gasSideHeatTransfer_2026-09-22.md](../references_gasSideHeatTransfer_2026-09-22.md). The roughness finding it corroborates is in [carlileQuentmeyer_2026-09-22.md](./carlileQuentmeyer_2026-09-22.md).
