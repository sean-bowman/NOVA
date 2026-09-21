
# References: charring ablator modeling and material response data

Sources consulted while building `src/NOVA/ablative.py` and the ablative response store in `src/NOVA/materials.py`, and the record of which ones could not supply what was wanted.

Accessed 2026-09-08 unless noted otherwise.

---

## Ablation Test-Case Series #1, version 1.1

- **URL:** <https://www.jeanlachaud.com/research/AblationTestCase%231.pdf>
- **Authors:** J. Lachaud, A. Martin, I. Cozmuta, B. Laub
- **Accessed:** 2026-09-08
- **Relevance:** Defines the benchmark NOVA's material response is validated against, and carries the FIAT baseline results that the validation is measured on. Prepared for the 4th AF-SNL-NASA Ablation Workshop, March 2011.
- **Key findings:**
  - The case: a 5 cm sample of TACOT, surface driven from 298 K to 1644 K over 0.1 s and held for 60 s, adiabatic and impermeable back face, 1 atm throughout, no recession. Fixing the surface temperature isolates conduction and pyrolysis from the boundary layer, which is exactly the separation a first verification needs.
  - Temperature probes are specified at 1, 2, 4, 8, 16 and 50 mm below the original surface.
  - Pyrolysis and char fronts are defined by density thresholds: `rho_v(98%) = rho_c + 0.98 (rho_v - rho_c)` and `rho_c(2%) = rho_c + 0.02 (rho_v - rho_c)`.
  - Codes are classified into three types. Type 1 is CMA-equivalent: heat transfer, pyrolysis, simplified mass transport. NOVA is type 1.
  - Fourteen participants ran it, estimated at half the community. The workshop reported temperature differences between type 1 and type 2 codes as **mostly below 1 percent**, which sets the standard any new implementation should be held to.
  - Figure 1 carries the FIAT baseline as marker series against PATO/PAM_1 as lines. Digitizing it at 400 dpi gives the reference values NOVA is tested against; the axis tick marks, whose values are known, come back to within 1.5 K, and the 1644 K surface line comes back as 1643.9 K.

## Ablation Test-Case Series #2, version 2.8

- **URL:** <https://jeanlachaud.com/research/AblationTestCase%232.pdf>
- **Authors:** J. Lachaud, A. Martin, T. van Eekelen, I. Cozmuta
- **Accessed:** 2026-09-08
- **Relevance:** Adds the convective boundary condition and surface recession, which is the configuration NOVA's `bPrimeTable` closure implements. Prepared for the 5th Ablation Workshop, 2012.
- **Key findings:**
  - Four sub-cases: 2.1 low heating without recession, 2.2 low heating with recession, 2.3 high heating with recession, 2.4 the ablation rate itself.
  - Boundary condition schedule: `rho_e u_e C_H` ramps 0 to 0.3 kg/m^2 s over 0.1 s, holds to 60 s, then drops; edge enthalpy 1.5e6 J/kg for 2.1 and 2.2, 2.5e7 J/kg for 2.3; wall pressure 101325 Pa throughout; 60 s of purely radiative cooldown after.
  - **The blowing correction factor is fixed at lambda = 0.5**, with `Pr = Le = 1` and a view factor of one against a 300 K sink. This is why NOVA's default is 0.5.
  - Test case 2.1 exists purely to separate the boundary condition from the moving mesh: `B'c` is forced to zero while the wall enthalpy is still read from the table. The document states plainly that this is not physical, since the wall enthalpy of a non-ablating surface differs from that of an ablating one. NOVA carries `suppressRecession` for exactly this.
  - The surface energy balance is given as `q = rho_e u_e C_h [(h_e - h_w) + B'c (h_c - h_w) + B'g (h_g - h_w)]`, which settles that `h_g` is the pyrolysis gas enthalpy and not the wall mixture enthalpy.
  - Preliminary results for 2.1 to 2.3 are provided with an explicit warning to use them **for sanity check rather than for comparison**. NOVA's report treats them that way.
  - Figure 2 shows the `B'c` table as a family of curves against temperature: a low-temperature plateau near 0.087, a monoxide plateau near 0.175, and a steep sublimation rise above about 3200 K.

## Ablation Test-Case Series #3, version 2.0

- **URL:** <https://jeanlachaud.com/research/AblationTestCase%233.pdf>
- **Authors:** T. van Eekelen, J. Lachaud, A. Martin, D. Bianchi
- **Accessed:** 2026-09-08
- **Relevance:** Consulted for its statement of the surface energy balance and for the multi-dimensional extension NOVA does not implement. Prepared for the 6th Ablation Workshop, 2014.
- **Key findings:**
  - Moves to a two- and three-dimensional iso-Q specimen with an orthotropic material, which is beyond what a station-independent one-dimensional march can represent.
  - Gives the initial surface energy balance explicitly as `q_ini = rho_e u_e C_h [(h_e - h_w) + B'c (h_c - h_w) + B'g (h_g - h_w)]`, confirming that a single transfer coefficient multiplies all three terms and that the blowing correction therefore applies to the whole bracket.
  - Notes that the pyrolysis gas enthalpy term is negative under the equilibrium assumption at low temperature, which is the cooldown effect NOVA reproduces and which only appears if the real gas enthalpy curve is used.

## TACOT v3.0 property spreadsheet

- **URL:** <https://jeanlachaud.com/research/TACOT_3.0.xls>
- **Authors:** J. Lachaud, T. van Eekelen, D. Bianchi, A. Martin
- **Accessed:** 2026-09-08
- **Relevance:** The complete property set NOVA's ablative response store is built from. It is the only charring ablator whose full response data is in the open literature; every real nozzle liner material has its property set behind an access control or a license.
- **Key findings:**
  - TACOT is a **theoretical** material: ex-cellulose carbon fibers at 0.1 volume fraction and a novolac/formaldehyde matrix at 0.1, with 0.8 porosity, giving 280 kg/m^3 virgin and 220 kg/m^3 char. It is a low-density entry heatshield, not a nozzle liner, and roughly a fifth the density of tape-wrapped carbon phenolic.
  - Thermal Properties sheet gives virgin and char specific heat, conductivity and absolute enthalpy on a 13-point grid from 460 to 6000 degR, in both British and SI columns. Emissivity is 0.8 virgin and 0.9 char.
  - **Enthalpy is absolute and self-consistent.** The datum is char at 298 K equal to zero; the phenolic heat of formation is -2.0 MJ/kg and the virgin value of -857142.857 J/kg is exactly the 0.42857 matrix mass fraction times it. This is what lets the heat of pyrolysis fall out of the enthalpy difference instead of being supplied separately.
  - Property blending is stated for CMA users: `tau = (1 - rho_c/rho)/(1 - rho_c/rho_v)`, with `cp = tau cp_v + (1 - tau) cp_c` and the same for conductivity.
  - Pyrolysis model sheet gives Goldstein's 1965 two-phase kinetics: component A at 300/0 kg/m^3 with `A = 1.2e4` and `E/R = 8555.6 K`, component B at 900/600 with `A = 4.48e9` and `E/R = 20444.4 K`, both third order, plus a non-decomposing carbon reinforcement at 1600. The mixing rule `rho = (1 - phi)[gamma (rho_A + rho_B) + (1 - gamma) rho_C]` with `phi = 0.8` and `gamma = 0.5` returns 280 and 220 exactly.
  - Pyrolysis gas elemental composition, from Sykes NASA TN D-3810: C 0.206, H 0.679, O 0.115 by mole.
  - **B-prime sheet holds a full three-dimensional table**: 4 pressures (0.001 to 1 atm), 25 pyrolysis gas blowing rates (0 to 10), 151 temperatures (250 to 4000 K), giving `B'c` and wall enthalpy at each of 15,100 points. Generated with TARGET on the CEA database over a reduced 25-species mixture.
  - **The table stops at 1 atm.** A rocket chamber is two to three orders above that, which is why NOVA's nozzle path uses the elemental balance instead of the table.
  - Equilibrium pyrolysis gas properties are tabulated separately at four pressures from 200 to 3975 K. The gas enthalpy at 1 atm runs from -7.09 MJ/kg at 300 K to +11.5 MJ/kg at 3000 K, a range the solid curves nowhere approach; substituting the solid enthalpy for it makes pyrolysis thermally neutral and moves the in-depth temperature by tens of kelvin.
  - Transport properties sheet gives porosity 0.8 virgin and 0.85 char, permeability 1.6e-11 and 2e-11 m^2, tortuosity 1.2 and 1.1. NOVA does not use these: they belong to a type 2 model with a momentum equation for the gas.
  - The sheet names its main property source as Milos and Chen, *Performance of a Low-Density Ablative Heat Shield Material*, Journal of Spacecraft and Rockets 45(4), 2008.

## Ablation Workshop code comparison archive

- **URL:** <https://uknowledge.uky.edu/ablation_code/>
- **Accessed:** 2026-09-08
- **Relevance:** Checked for tabulated inter-code results that would give a stronger reference than a digitized figure.
- **Key findings:**
  - Hosts TACOT v3.0, test case series 1 and 3, and an overview of the test case 1 intercalibration results.
  - **The numerical result files are not there.** Everything except the spreadsheet is a PDF, so the code-to-code comparison is available only as plots.
  - Direct fetches of the hosted PDFs return **HTTP 403** to automated access. The intercalibration overview, which would carry the spread across all fourteen participating codes, could not be retrieved.

## Code-to-Code Comparison, and Material Response Modeling of Stardust and MSL Using PATO and FIAT

- **URL:** <https://jeanlachaud.com/research/NASA_CR-2015-218960.pdf>
- **Accessed:** 2026-09-08
- **Relevance:** Checked as a possible second source of tabulated test case 1 results.
- **Key findings:**
  - Runs the ablation test case 1 geometry and boundary condition, but with **PICA rather than TACOT**, so its numbers are not comparable to a TACOT run.
  - States that previous PATO-versus-FIAT comparisons using TACOT showed similar trends, which is corroborating but not quotable as a reference value.
  - Useful for its statement of what agreement between two mature implementations of the same model actually looks like on real entry cases.

## Moyer and Rindal, An Analysis of the Coupled Chemically Reacting Boundary Layer and Charring Ablator, NASA CR-1061

- **Accessed:** cited, not retrieved
- **Relevance:** The original CMA formulation, which is the model NOVA implements. Referenced throughout the test case series as the definition of a type 1 code.
- **Key findings:**
  - The governing equation set, blowing correction and B-prime closure are reproduced in enough detail across the three test case documents and the TACOT spreadsheet notes to implement without the original, which is what was done here.

## Stagnation line approximation for ablation thermochemistry

- **Authors:** J. de Muelenaere, J. Lachaud, N. N. Mansour, T. E. Magin
- **Venue:** 42nd AIAA Thermophysics Conference, June 2011
- **Accessed:** cited in the TACOT spreadsheet, not retrieved
- **Relevance:** The method behind the shipped B-prime table. Named in the spreadsheet header along with the Mutation-B' implementation used to generate it.

## A CEA-based Chemical Equilibrium Solver for Gas/Surface Thermochemistry and Thermochemical Tables Generation

- **Author:** D. Bianchi
- **Venue:** Centro Ricerca Aerospaziale Sapienza, contract CRAS-TTG-1001, 2013
- **Accessed:** cited in the TACOT spreadsheet, not retrieved
- **Relevance:** TARGET, the tool that produced the shipped B-prime and pyrolysis gas tables. Establishes that those tables come from CEA thermodynamic data through an independent implementation, which is what makes them a validation reference for NOVA's closed-form limits rather than a cross-check.

## Thermal Properties of G-348 Graphite, INL/EXT-16-38241

- **URL:** <https://www.osti.gov/servlets/purl/1330693>
- **Accessed:** 2026-09-08
- **Relevance:** Sought as a source of measured conductivity and specific heat curves for isomolded graphite, which would let a non-charring graphite throat insert join the response store alongside TACOT.
- **Key findings:**
  - Confirms ASTM C781-08 Table A6.1 as the recommended specific heat values for graphite over 300 to 3000 K, and the Butland and Maddison 1973/4 polynomial as the accepted correlation over 250 to 3000 K.
  - **Neither the ASTM table nor the Butland-Maddison coefficients appear in the report text**; both are shown only as curves in a figure. The correlation could not be transcribed to the accuracy the store requires.
  - The material is G-348, not ATJ, so its conductivity would need a grade correction that nothing in the report supports.
  - Outcome: graphite was **not** added to the ablative response store. Recorded as blocked rather than approximated.

## Thermal conductivity and electrical resistivity of two types of ATJ-S graphite to 3500 K

- **URL:** <https://www.sciencedirect.com/science/article/abs/pii/0008622373903102>
- **Accessed:** 2026-09-08
- **Relevance:** The correct primary source for ATJ conductivity against temperature, which is the grade NOVA already carries at room temperature.
- **Key findings:**
  - Reports measurements from 300 to 3500 K, which is the whole range a graphite throat sees.
  - Establishes that above 500 K the conductivity follows a `T^-1` law, characteristic of Umklapp scattering. This is why the room-temperature 116 W/m-K in NOVA's selection store carries a note saying it is not usable hot.
  - **Paywalled.** Abstract only.

## Blocked: tape-wrapped carbon phenolic response properties

- **Accessed:** 2026-09-08
- **Relevance:** The material an ablative rocket nozzle liner is actually made of, and the one gap that separates NOVA's nozzle path from a design tool.
- **Key findings:**
  - The virgin and char conductivity curves to 5000 degF for the MX-4926 class live in DTIC reports that return **HTTP 403** to automated access.
  - MIL-HDBK-17 and the CINDAS databases carry equivalent data behind licenses.
  - No open substitute was found. TACOT is a benchmark material rather than a replacement: at 280 kg/m^3 virgin against roughly 1450 for tape-wrapped carbon phenolic, its areal mass and its char density differ by a factor of five, and recession scales inversely with char density.
  - Outcome: the solver takes material properties as data and ships one open benchmark material. The store's notes say what it is not for.
