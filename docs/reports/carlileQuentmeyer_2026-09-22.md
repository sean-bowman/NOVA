# NOVA's channel thermal model against Carlile and Quentmeyer

Carlile and Quentmeyer (NASA TM-105679, 1992) fired three cylindrical OFHC copper chambers on GH2 and LOX at 4.136 MPa, cooled by liquid hydrogen in straight channels of throat aspect ratio 0.75, 1.50 and 5.00, and reported the hot-gas wall temperature at the throat against coolant mass flux. NOVA's station model, run on their geometry with the gas side fixed from their stated operating point, puts every one of their 13 measurements inside its predicted band, and predicts the high aspect ratio chamber cooler than the baseline everywhere in the bracket.

It is not a validation. The paper does not give the coolant state at the throat or the roughness of the channels, and the bracketed roughness alone moves the prediction by more than either acceptance tolerance. Under the rule stated before the first run, the result is a **sensitivity-bounded comparison**.

The comparison also produced a finding about the shipped model. NOVA feeds a rough-wall friction factor into Gnielinski, which credits roughness with heat transfer in proportion to the friction it adds. At the 35 um roughness NOVA assumes for a printed channel, that predicts the baseline chamber's wall-to-coolant temperature difference 39 percent low. Rough-tube measurements show heat transfer rising less than friction, so where the credit is not real the model runs the wall cooler than the hardware will.

`tests/testRegenValidation.py` reproduces every number here and holds the outcome.

---

## The experiment

| Configuration | Aspect ratio (throat) | Passages | Depth [cm] | Width [cm] | Rib at the floor [cm] |
|---|---|---|---|---|---|
| 1 (baseline) | 0.75 | 72 | 0.127 | 0.170 | 0.126 |
| 2 | 1.50 | 100 | 0.152 | 0.102 | 0.111 |
| 3 | 5.00 | 400 | 0.127 | 0.0254 | 0.028 |

The first five columns are the paper's Table 1. The rib is the pitch at the floor of the channel, 2 pi (r + t) / N, less the width, with r = 3.30 cm and t = 0.089 cm. Every chamber is 15.24 cm long, straight-channelled, and fired at a mixture ratio of 6.0. The paper states that the baseline was designed for a 778 K hot-gas wall at 0.909 kg/s of coolant, at a throat heat flux of about 97.1 MW/m^2.

The measured temperatures are digitized from Fig. 12 against its axis ticks, to within 10 K. Each point's mass flux matches a coolant flow stated in the text to within one percent, and the stated flow is used.

---

## Method

Each point is a single station solve, `regenThermal.solveStationWallTemperature`, the one the jacket sizing runs:

- **Section** from `channelSections.sectionProperties('rectangular', ...)`: sharp corners, the Table 1 width and depth, hydraulic diameter 4A/P, the floor as the heated perimeter and the side walls as rib faces.
- **Rib** as a straight fin cooled on both faces with an adiabatic tip, at the rib thickness above.
- **Wall** as the cylindrical sector each channel owns, OFHC copper conductivity from NOVA's materials store (NIST cryogenic database below 300 K, TPRC above).
- **Coolant** hydrogen properties at the bulk state from REFPROP or CoolProp; Swamee-Jain friction and Gnielinski's Nusselt number from `regenThermal.coolantFrictionAndNusselt`.
- **Gas side** not predicted. Its coefficient is fixed from the paper's operating point, h_g = 97.1 MW/m^2 / (T_aw - 778 K), and held, so the gas-side flux follows the predicted wall. This uses the station solve's `prescribedGasCoefficient` in place of Bartz.

### Unknowns, bracketed

| Unknown | Bracket | Reasoning |
|---|---|---|
| Coolant bulk temperature at the throat | 30 K plus 10 to 70 K at 0.841 kg/s, scaled by 0.841 / flow | The heat taken up upstream of the throat is roughly fixed |
| Coolant pressure | 6 to 12 MPa | Supercritical, around the 4.136 MPa pressure drop |
| Adiabatic wall temperature | 3000 to 3400 K | GH2/LOX at a mixture ratio of 6.0 |
| Throat heat flux | 97.1 MW/m^2 plus or minus 10 percent | "Approximately" in the paper |
| Channel roughness | 0.8 to 3.2 um | Machined copper; not reported |

Every point is solved at all 72 combinations and reported as the band they span.

### Acceptance, stated before the first run

- **A.** At every point run at 0.7 kg/s or more, the predicted T_hw - T_b within 20 percent of the measured one over the whole bracket.
- **B.** The difference between the 0.75 and 5.00 chambers at the baseline's mass flux, 5410 kg/s/m^2, predicted within 30 percent. The unknowns act on both chambers alike, so this cancels most of them and tests the section and fin physics.

A criterion is met when its whole band lies inside its tolerance. It counts as a validation only if the band is also narrower than half the tolerance; otherwise the result is a sensitivity-bounded comparison.

---

## Results

### Every point

| Aspect ratio | Coolant flow [kg/s] | Measured [K] | Predicted band [K] | Error on T_hw - T_b | Criterion A |
|---|---|---|---|---|---|
| 0.75 | 0.841 | 768 | 569 to 842 | -28 to +13 % | Not met, band wider than tolerance |
| 1.50 | 0.909 | 701 | 521 to 752 | -28 to +10 % | Not met, band wider than tolerance |
| 1.50 | 0.841 | 730 | 532 to 776 | -30 to +9 % | Not met, band wider than tolerance |
| 1.50 | 0.773 | 757 | 543 to 804 | -31 to +9 % | Not met, band wider than tolerance |
| 5.00 | 0.714 | 493 | 401 to 590 | -22 to +29 % | Not met, band wider than tolerance |
| 5.00 | 0.641 | 508 | 408 to 609 | -23 to +30 % | Below 0.7 kg/s |
| 5.00 | 0.600 | 518 | 412 to 622 | -24 to +30 % | Below 0.7 kg/s |
| 5.00 | 0.559 | 527 | 418 to 635 | -24 to +31 % | Below 0.7 kg/s |
| 5.00 | 0.495 | 546 | 428 to 660 | -25 to +32 % | Below 0.7 kg/s |
| 5.00 | 0.400 | 578 | 450 to 708 | -26 to +36 % | Below 0.7 kg/s |
| 5.00 | 0.314 | 619 | 484 to 771 | -25 to +42 % | Below 0.7 kg/s |
| 5.00 | 0.255 | 657 | 522 to 838 | -24 to +49 % | Below 0.7 kg/s |
| 5.00 | 0.182 | 727 | 590 to 973 | -22 to +71 % | Below 0.7 kg/s |

The error bands include the 10 K digitization. Every measurement lies inside its predicted band.

**Criterion B.** The measured difference at 5410 kg/s/m^2 is 272 K, interpolating the 5.00 chamber between its two nearest points. The predicted difference spans 152 to 302 K, an error of -49 to +16 percent including 14 K of combined digitization. The measurement lies inside the band; the band is wider than the tolerance, so the criterion is not met as stated. Across the whole bracket the 5.00 chamber is predicted cooler than the baseline, by at least 152 K.

### The central case

At the middle of the bracket (40 K pickup, 9 MPa, 3200 K, 97.1 MW/m^2, 1.6 um):

| Aspect ratio | Coolant flow [kg/s] | Measured [K] | Predicted [K] | Error on T_hw - T_b |
|---|---|---|---|---|
| 0.75 | 0.841 | 768 | 684 | -12.0 % |
| 1.50 | 0.909 | 701 | 617 | -13.3 % |
| 1.50 | 0.841 | 730 | 638 | -13.9 % |
| 1.50 | 0.773 | 757 | 662 | -13.9 % |
| 5.00 | 0.714 | 493 | 492 | -0.0 % |
| 5.00 | 0.641 | 508 | 509 | +0.1 % |
| 5.00 | 0.600 | 518 | 519 | +0.4 % |
| 5.00 | 0.559 | 527 | 531 | +0.9 % |
| 5.00 | 0.495 | 546 | 552 | +1.4 % |
| 5.00 | 0.400 | 578 | 592 | +3.0 % |
| 5.00 | 0.314 | 619 | 642 | +4.8 % |
| 5.00 | 0.255 | 657 | 690 | +6.6 % |
| 5.00 | 0.182 | 727 | 784 | +11.2 % |

The central difference is 189 K against 272 K measured, -31 percent.

### What drives the band

One unknown at a time from the central case:

| Unknown, over its bracket | 0.75 chamber at 0.841 kg/s [K] | 5.00 chamber at 0.714 kg/s [K] | Difference at 5410 kg/s/m^2 [K] |
|---|---|---|---|
| Roughness, 0.8 to 3.2 um | 729 to 640 | 511 to 473 | 215 to 163 |
| Heat flux, -10 to +10 % | 633 to 735 | 455 to 529 | 175 to 202 |
| Bulk pickup, 10 to 70 K | 707 to 729 | 472 to 527 | 233 to 198 |
| Pressure, 6 to 12 MPa | 692 to 688 | 495 to 492 | 193 to 193 |
| Adiabatic wall, 3000 to 3400 K | 686 to 683 | 496 to 489 | 187 to 190 |

Roughness and heat flux dominate. The pickup is not monotonic in its effect on the baseline because hydrogen's specific heat and viscosity swing sharply between 40 and 100 K at these pressures.

No single roughness fits both families:

| Roughness [um] | 0.75 at 0.841 kg/s | 1.50 at 0.841 kg/s | 5.00 at 0.714 kg/s | Difference |
|---|---|---|---|---|
| 0 (smooth) | 905 K, +19.6 % | 818 K, +13.4 % | 586 K, +22.5 % | 315 K, +16 % |
| 0.4 | 773 K, +0.6 % | 709 K, -3.1 % | 529 K, +8.7 % | 240 K, -12 % |
| 1.6 | 684 K, -12.0 % | 638 K, -13.9 % | 492 K, -0.0 % | 189 K, -31 % |
| 35 (NOVA's printed default) | 498 K, -38.7 % | 482 K, -37.5 % | 407 K, -20.5 % | 88 K, -68 % |

Errors are on T_hw - T_b at the central case otherwise.

---

## Finding: roughness is credited in full

Gnielinski's correlation is written for smooth tubes. NOVA evaluates it with the Swamee-Jain friction factor at the channel roughness, so the Nusselt number rises with the friction factor. At these Reynolds numbers, 1.2 to 1.6 million for the two low aspect ratio chambers, a relative roughness of 1e-3 is fully rough and nearly doubles the friction factor, and the model nearly doubles the heat transfer with it: at 1.6 um the Nusselt number is 1.7 to 2.2 times its smooth value across every point here.

Rough-tube measurements do not support that. Dipprey and Sabersky found the heat transfer increase from sand-grain roughness to lag the friction increase, most at Prandtl numbers near one, which is where hydrogen sits here (0.68 to 0.89). The comparison above shows the consequence: a small change in an unknown roughness swings the prediction across the data, and no one roughness fits both chamber families.

For NOVA as shipped, the default roughness is 35 um, the Velo3D datasheet value for printed GRCop-42. Applied to the baseline chamber, the model predicts T_hw - T_b 39 percent below the measurement. If the roughness credit is not real for a printed channel either, the jacket NOVA sizes runs its wall hotter than NOVA reports. That is non-conservative, and it applies to every channel family.

A rough-wall heat transfer correction, which limits the Nusselt augmentation to a fraction of the friction augmentation, is what would close it, with printed-channel heat transfer data to set it against. None was implemented or tuned here; calibrating one to this data set and then reporting the match would be calibration, not validation.

---

## Cross-check

Dittus-Boelter, 0.023 Re^0.8 Pr^0.4, against Gnielinski on a smooth wall at the central bulk state: within 2 to 13 percent at every point, Dittus-Boelter higher, with the largest gaps at the low Reynolds numbers of the 5.00 chamber's low-flow points. Two correlations agreeing is a cross-check and says nothing about either against hardware.

---

## Disclosed

- **The measured temperatures are inferred.** The paper's hot-gas wall temperature is a SINDA conduction model's node, fitted to rib and backside thermocouples, with the coolant coefficients on the sides and roof of the channel adjusted to fit.
- **Hottest point against sector mean.** The paper reports the hottest point, on the channel centerline. NOVA solves one wall temperature for the channel's sector, which is cooler than the centerline between the ribs. The bias is largest for the wide channels of the baseline and is consistent with the 0.75 and 1.50 chambers being predicted cool at the central case.
- **No property ratio correction.** The coolant correlation evaluates every property at the bulk temperature. Hydrogen at wall-to-bulk temperature ratios of 3 to 11, as here, is known to need a correction, which would reduce the predicted coefficient.
- **No stratification.** A tall channel's coolant heats nonuniformly from floor to roof, which the paper names in its concluding remarks and the model does not represent.
- **Straight passages.** Nothing here tests the helical layout, whose hoop curvature and secondary flow the model does not represent.
- **The gas side is prescribed.** Bartz is not exercised by this comparison.

---

## Reproduce

```bash
pytest tests/testRegenValidation.py -v
```

The module holds the digitized data, the brackets, the acceptance and the classification rule, and fails if a change to the model moves the outcome recorded here.

---

## References

1. Carlile, J. A., and Quentmeyer, R. J., "An Experimental Investigation of High-Aspect-Ratio Cooling Passages," NASA TM-105679, AIAA-92-3154, July 1992.
2. Swamee, P. K., and Jain, A. K., "Explicit Equations for Pipe-Flow Problems," Journal of the Hydraulics Division, ASCE, Vol. 102, No. 5, 1976, pp. 657-664.
3. Gnielinski, V., "New Equations for Heat and Mass Transfer in Turbulent Pipe and Channel Flow," International Chemical Engineering, Vol. 16, 1976, pp. 359-368.
4. Dipprey, D. F., and Sabersky, R. H., "Heat and Momentum Transfer in Smooth and Rough Tubes at Various Prandtl Numbers," International Journal of Heat and Mass Transfer, Vol. 6, 1963, pp. 329-353.
5. Incropera, F. P., DeWitt, D. P., Bergman, T. L., and Lavine, A. S., Fundamentals of Heat and Mass Transfer, straight fins of uniform cross section.
6. NIST, Properties of Selected Materials at Cryogenic Temperatures, OFHC copper.
7. Wadel, M. F., "Comparison of High Aspect Ratio Cooling Channel Designs for a Rocket Combustion Chamber With Development of an Optimized Design," NASA TM-1998-206313, January 1998.
