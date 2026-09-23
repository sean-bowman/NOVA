# References: gas-side and coolant-side heat transfer in the chamber and nozzle

Sources retrieved for a chamber-side heat transfer model and for validating the thermal model against fired hardware rather than against a worked example.

## Experimental Investigation of Hot-Gas Side Heat-Transfer Rates for a Hydrogen-Oxygen Rocket

- **URL:** https://ntrs.nasa.gov/api/citations/19650016811/downloads/19650016811.pdf
- **Accessed:** 2026-09-22
- **Relevance:** The gas-side validation case. It measures the heat transfer coefficient at five axial stations of a LOX/GH2 chamber, one of them in the cylindrical barrel, over a wide chamber pressure range, and reports the correlation constant and its scatter at each station.
- **Key findings:**
  - Ralph L. Schacht, Richard J. Quentmeyer and William L. Jones, NASA TN D-2832, Lewis Research Center, June 1965.
  - Copper heat-sink chamber: 5 in throat, 10.77 in chamber bore, 14.5 in from injector face to throat, L* 54 in, contraction and expansion area ratio 4.64, 234-element coaxial injector, 26 000 lbf at 900 psia.
  - Chamber pressures 150 to 1000 psia at 11 to 17 percent hydrogen by weight, most runs near 15 percent. Average combustion efficiency 98 percent of equilibrium.
  - Transient wall temperatures on inserted copper rods, reduced through a one-dimensional semi-infinite slab solution; measurement uncertainty about 6 percent in hX/k.
  - Data correlate as St* Pr*^0.7 = C Re*_d^-0.2 with all transport properties at Eckert's reference enthalpy H* = H_s + 0.5(H_w - H_s) + 0.22 Pr*^(1/3)(H_tot - H_s) and the local static pressure, from an equilibrium solution.
  - No single C fits every station. Station 1 (chamber, A/A* 4.64) gives C = 0.0257 with 10.9 percent standard deviation; station 2 (A/A* 1.78) 0.0240; the throat 0.0148, and 0.0151 averaged over three circumferential stations; station 4 (A/A* 1.27) 0.0153; station 5 (A/A* 3.33) 0.0188.
  - The throat value is 42 percent below the widely used C = 0.026, which the report states overpredicts every station except the chamber. Three other nozzle configurations recomputed the same way give throat constants of 0.019, 0.017, 0.023 and about 0.018.
  - The report states explicitly that C varies with area ratio in this pattern (high in the chamber, low at the throat, rising again toward the exit) for this geometry, propellant and injector, and is not to be treated as universal.

## Coolant-Side Heat-Transfer Rates for a Hydrogen-Oxygen Rocket and a New Technique for Data Correlation

- **URL:** https://ntrs.nasa.gov/api/citations/19730010241/downloads/19730010241.pdf
- **Accessed:** 2026-09-22
- **Relevance:** The coolant-side validation case, on the same chamber geometry as TN D-2832, with liquid hydrogen taken through its pseudo-critical region. It measures local coolant-side coefficients rather than an overall wall temperature, which is what a station model can be held to.
- **Key findings:**
  - Ralph L. Schacht and Richard J. Quentmeyer, NASA TN D-7207, Lewis Research Center, March 1973.
  - Same gas-side geometry and injector as TN D-2832: contraction and expansion 4.64, 14.5 in injector face to throat, L* 54 in, 5 in throat.
  - 150 coolant tubes of AISI-347 stainless, 0.010 in wall, with liquid hydrogen above critical pressure and below critical temperature at inlet, so the coolant passes through the pseudo-critical temperature inside the passage.
  - Five axial stations on two tubes 180 degrees apart, each with four hot-gas-side thermocouples plus coolant temperature taps 0.5 in upstream and downstream and a static pressure tap. Chamber pressures 300 and 450 psia with coolant flow and pressure set independently of the gas side.
  - Proposed correlation St Pr^0.6 = 0.023 Re^-0.2 with transport properties evaluated by integration across the film rather than at a single reference temperature, which holds across the subcritical to supercritical transition without changing the correlation.
  - Standard entrance corrections apply, and Ito's curvature correction gives about the right magnitude for the enhancement needed in the throat region.
  - The gas-side coefficients used to reduce the coolant-side data come from the TN D-2832 correlation constant curve, so the two reports form one package.

## A Comparison of Experimental Heat-Transfer Coefficients in a Nozzle With Analytical Predictions From Bartz's Methods

- **URL:** https://ntrs.nasa.gov/api/citations/19710011726/downloads/19710011726.pdf
- **Accessed:** 2026-09-22
- **Relevance:** An independent check on Bartz in a nozzle, retrieved to see whether the overprediction in TN D-2832 repeats in another propellant system. It does.
- **Key findings:**
  - Dewey M. Smith, MS thesis, North Carolina State University at Raleigh, 1970, NASA accession N71-21201, hardware and tests at Langley Research Center.
  - Solid propellant motor, ammonium perchlorate and polybutadiene acrylic acid, at average chamber pressures of 220, 410 and 742 psia, with a steel-cased nozzle and a ZTA graphite throat insert.
  - Measurements in the convergent section, at the throat and in the divergent section, from five thermocouples per station reduced through a finite-difference heat balance.
  - Experimental coefficients in the convergent region and at the throat are consistently below both Bartz's Nusselt-number correlation and his boundary-layer method.
  - Divergent-section data correlate when the skin friction coefficient is evaluated at the free-stream temperature.

## Benchmark Wall Heat Flux Data for a GO2/GH2 Single Element Combustor

- **URL:** https://ntrs.nasa.gov/citations/20050209932
- **Accessed:** 2026-09-22
- **Relevance:** A modern axial heat flux distribution close to the injector, retrieved for the shape of the near-injector rise that a station correlation cannot produce. Single-element hardware, so it bounds the effect rather than representing a flight injector.
- **Key findings:**
  - William M. Marshall, Sibtosh Pal, Roger D. Woodward and Robert J. Santoro, Pennsylvania State University, AIAA 2005-3572, January 2005.
  - 1.5 in diameter circular chamber with a uni-element shear coaxial injector on gaseous oxygen and hydrogen, at 300, 450, 600 and 750 psia, mixture ratio 6.0 ambient and 6.6 with vitiated preburner propellants.
  - Gardon gauges and coaxial thermocouples give axial wall heat flux distributions intended as CFD validation data.
  - Peak heat flux falls 2.0 to 3.0 in from the injector face, between one and two chamber diameters downstream, with the preburner case about twice the ambient case.
