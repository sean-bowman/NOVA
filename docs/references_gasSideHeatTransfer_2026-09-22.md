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

## RPA: Tool for Rocket Propulsion Analysis. Thermal Analysis of Thrust Chambers

- **URL:** https://www.propulsion-analysis.com/downloads/2/docs/RPA_ThermalAnalysis.pdf
- **Accessed:** 2026-10-03
- **Relevance:** RPA's gas-side model and its one published comparison against fired hardware, retrieved to hold NOVA's gas side to a measured axial heat flux profile and to implement the method RPA uses.
- **Key findings:**
  - A. Ponomarenko, June 2012. Ievlev's method in full, Eqs. 1.1 to 1.6: the energy integral in closed form, an algebraic momentum-to-energy group ratio, a Stanton relation in the momentum group, and an enthalpy driving potential with the wall gas at its 1500 K composition. The exponent in Eq. 1.2 and the base of the logarithm in Eq. 1.3 are not stated.
  - Figure 13 is the measured wall heat flux of Test 024 on the MSFC 40k calorimeter chamber, Fig. 11 of Dexter et al. in Progress in Astronautics and Aeronautics Vol. 200. Figure 14 is RPA's prediction for the same test, at its own operating point of mixture ratio 6.0 and 10.87 MPa, with the wall RPA built for it.
  - The design parameter table's "combustion chamber diameter" of 43.8 mm is the hardware's 143.8 mm with its first digit lost; Dexter's Table 1 prints the same slip in its regeneratively cooled column. The wall RPA drew has the hardware's 84.1 mm throat to within its reading.
  - RPA does not state the wall temperature its prediction used.
  - RPA's quasi-one-dimensional chamber flow is not described; its barrel flux rises from the injector, which the Ievlev equations alone cannot produce.

## Hot-Gas-Side and Coolant-Side Heat Transfer in Liquid Rocket Engine Combustors

- **URL:** https://ntrs.nasa.gov/citations/19970011069
- **Accessed:** 2026-10-04
- **Relevance:** Retrieved for the operating point and film flow of the 40k calorimeter test. Its operating point is not Test 024's; what carries over is the coolant water state and the onset criterion for reduced heat transfer.
- **Key findings:**
  - Ten-See Wang and Van Luong, Marshall Space Flight Center, Journal of Thermophysics and Heat Transfer Vol. 8 No. 3, 1994; AIAA Paper 92-3151.
  - Table 3: 1568 psia, 64.3 lbm/s, mixture ratio 6.87, and 3.8 lbm/s of film coolant, which is 47 percent of the fuel; the text says about 5 percent of the fuel flowed as film. That does not match Test 024 (1577 psia, mixture ratio 6.0, 57.6 lbm/s through the 84.1 mm throat), and Dexter's account of the hardware has a transpiration-cooled faceplate and no injected film.
  - The chamber was water cooled through circumferential passages in Narloy-Z, with the water at about 60 F and 4600 psia.
  - Their CFD with wall functions reproduced the throat region and overpredicted the barrel; they credit film coolant for the low flux at the injector face.
  - The acceleration parameter along the 40k wall stays below the 2e-6 at which Back, Cuffel and Massier found heat transfer reduced below turbulent values.

## NIST-JANAF Thermochemical Tables: water vapour and hydrogen

- **URL:** https://janaf.nist.gov/tables/H-064.txt and https://janaf.nist.gov/tables/H-050.txt
- **Accessed:** 2026-10-06
- **Relevance:** An independent reference for the wall gas enthalpy that the enthalpy driving potential and Ievlev's method rest on.
- **Key findings:**
  - M. W. Chase, NIST-JANAF Thermochemical Tables, 4th edition, 1998.
  - Water vapour: formation enthalpy -241.826 kJ/mol; H - H(298.15) of 6.925 kJ/mol at 500 K and 10.501 at 600 K.
  - Hydrogen: H - H(298.15) of 5.882 kJ/mol at 500 K and 8.811 at 600 K.
  - Fully recombined LOX/LH2 products at a mixture ratio of 6.0 and 550 K come to -12.362 MJ/kg from these; CEA's expansion route returns the same to 0.1 percent.

## Scaling Techniques for Design, Development, and Test

- **URL:** https://doi.org/10.2514/5.9781600866760.0553.0600
- **Accessed:** 2026-10-06
- **Relevance:** The primary source of the 40k calorimeter measurement that RPA's paper reproduces: the hardware, the test's operating point, the heat flux and heat transfer coefficient profiles, and the reduction that relates them.
- **Key findings:**
  - Carol E. Dexter, Mark F. Fisher (NASA MSFC), James R. Hulka (Aerojet), Konstantin P. Denisov, Alexander A. Shibanov and Anatoliy F. Agarkov (NIICHIMMASH), Chapter 16 of *Liquid Rocket Thrust Chambers: Aspects of Modeling, Analysis, and Design*, Progress in Astronautics and Aeronautics Vol. 200, AIAA, 2004, pp. 553-600. Section IV, pp. 586-591, covers heat transfer.
  - Table 1: the 40k water-cooled calorimeter chamber has an 84.1 mm throat, a 143.8 mm chamber, a contraction ratio of 2.92, 355.6 mm from injector face to throat, an expansion ratio of 7 and 61 injection elements. It shares the SSME main chamber's length, convergence angle, throat radius of curvature and contraction ratio. The regeneratively cooled column prints the chamber diameter as 43.8 mm.
  - The faceplate was transpiration cooled, the outer element row carried no mixture-ratio bias, and the fuel reached the injector warm from a preburner. 116 circumferential water channels were manifolded into 58 circuits, each with its own temperature and pressure measurement.
  - Test 024 ran at 10.87 MPa and mixture ratio 6.0 with a total heat load of 9079 kW and a characteristic velocity efficiency of 100 percent. Fig. 11 gives its heat flux and Fig. 12 its heat transfer coefficient.
  - Eqs. 21 to 24: h_g = (Q/A) / (T_aw - T_wh), with T_aw = R_c T_c from one-dimensional equilibrium Pr, gamma and Mach number, and T_wh from a two-dimensional finite-difference wall model with forced convection and nucleate boiling, held at the water's saturation temperature plus 283 K once reached. Figs. 11 and 12 together therefore return the hot-wall temperature the reduction used.
  - Near the injector, out to about 127 mm, heat transfer is governed by distance from the injector; further downstream, by velocity. The full-scale prediction scaled from these data came within 2 to 5 percent of the measured SSME heat load.
