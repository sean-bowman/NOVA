
# References: film cooling, radiative cooling and surface emissivity

Sources consulted while extending NOVA's thermal model beyond the regeneratively cooled jacket, and the record of which ones could not supply what was wanted.

Accessed 2026-09-10 and 2026-09-11 unless noted otherwise.

---

## NASA SP-8124, Liquid Rocket Engine Self-Cooled Combustion Chambers

- **URL:** <https://ntrs.nasa.gov/api/citations/19780013268/downloads/19780013268.pdf>
- **Authors:** R. L. Ewen and H. M. Evensen, Aerojet Liquid Rocket Company, for NASA Lewis Research Center. September 1977.
- **Accessed:** 2026-09-10
- **Relevance:** The NASA design criteria monograph covering every cooling method NOVA does not yet model. It is the primary reference for both features: film cooling and radiation-cooled chambers.
- **Key findings:**
  - Appendix A is an analytical model for gas film cooling, Appendix B for liquid film cooling. Section 2.2 covers radiation-cooled chambers, 2.5 covers heat transfer to the wall including film cooling analysis and film coolant injection.
  - **Gas film cooling is an entrainment model.** The entrainment flux of core flow into a mixing layer containing all the film coolant is the product of the core axial mass velocity and an entrainment fraction. Coolant effectiveness is defined on total enthalpies and the wall mixture ratio comes from a mass-transfer analogy, which is why a fuel film lowers the adiabatic wall temperature by more than dilution alone.
  - The entrainment fraction is written as `psi_r * psi_m(x)`, where `psi_r` is the plane unaccelerated continuous-slot value and `psi_m` is an empirical multiplier carrying rocket turbulence, injection configuration, flow turning and acceleration. **Recommended values: 3 to 4 at the injection point, decaying linearly to about 1.75 at the throat**, then along Figure 17 to roughly 0.35 by area ratio 28.
  - **Liquid film cooling** uses an empirical injection factor `delta` of 1.0 to 1.6 for orifice injection parallel to the core flow, as low as 0.4 for swirl. Downstream of the liquid film the entrainment fraction is `psi_L psi_m` with `psi_L` of 0.025 to 0.06. For a monopropellant coolant the vapour superheats without decomposing until a critical wall temperature, about 550 degF for MMH, after which the vapour fraction decays with an empirical constant of roughly 3000 per second.
  - **Injection guidance that constrains a design:** liquid film coolant orifices spaced no more than 0.3 in apart, impinging on the wall at 25 to 35 degrees; gaseous coolant injected parallel through slots at a coolant-to-core velocity ratio of 0.9 to 1.15.
  - The monograph is explicit that `psi_m` is the key to predicting coolant flow requirements and that the acceleration and turning effects it absorbs are very significant. Implementing this model makes a result calibrated to SP-8124's recommendation rather than validated.
  - **Format:** scanned, CCITT fax encoded. There is no text layer, so it reads page by page as images. Document page `p` is PDF page `p + 12`.
  - **Appendix A, read in full from document pages 89 to 93.** Entrainment flow ratio, the reference entrainment fraction `psi_r`, the effective contour distance, Figure A-1 for the velocity-ratio correlation function, Figure A-2 for effectiveness against entrainment flow ratio, and both the reactive and non-reactive adiabatic wall expressions. Every group in it is dimensionless, so it implements in SI with no conversion. Figure A-1 states its lower branch, `f = (u_c/u_e)^1.5` for velocity ratios at or below one; Figure A-2 states both of its limits, `eta = 1` below an entrainment ratio of 0.06 and `eta = 1.32/(1 + W_E/W_c)` above 1.4.
  - **Appendix B, read in full from document pages 95 to 99, and not implemented.** The liquid film length runs on two curves plotted on Figure B-1, a rotated scan whose values cannot be read to a useful accuracy, and the chain to the answer is multiplicative through a Stanton number, a surface tension, a saturation loop on the coolant partial pressure, and a roughness augmentation factor. The appendix states outright that it is a dimensional correlation in which only the numerical values of the specified units may be used, with the gravitational constant written into the entrainment parameter. Nothing in the monograph gives a worked example to check an implementation against.

## Hatch and Papell, NASA TN D-130

- **URL:** <https://ntrs.nasa.gov/citations/19890068390>
- **Title:** Use of a Theoretical Flow Model to Correlate Data for Film Cooling or Heating an Adiabatic Wall by Tangential Injection of Gases of Different Fluid Properties. NASA Lewis Research Center, November 1959.
- **Accessed:** 2026-09-10
- **Relevance:** The tangential-injection effectiveness correlation, and the only film cooling closure found that arrives with an accuracy figure from its own source. That makes it the one to implement and validate first.
- **Key findings:**
  - Models tangential slot injection by taking the mainstream and the coolant stream as separate, with heat transfer between them driven by a characteristic heat transfer coefficient.
  - Later work uses it as the baseline for angled injection, adding corrective terms, which establishes it as the reference form rather than one option among several.
  - Restricted to tangential injection.

## NASA TN D-3836, Gaseous-Film Cooling of a Rocket Motor with Injection Near the Throat

- **URL:** <https://ntrs.nasa.gov/api/citations/19670008176/downloads/19670008176.pdf>
- **Accessed:** 2026-09-10
- **Relevance:** Film cooling measured at rocket conditions rather than on a flat plate, which is the gap most of the film cooling literature has. Intended as the validation case for the gaseous closure.
- **Key findings:**
  - Retrieved as a 1.7 MB scanned PDF with no text layer. Its contents have not yet been extracted; the reference values will be digitized from its figures the way the FIAT baseline was for the ablation work.

## Levine and Merutka, Performance of Coated Columbium and Tantalum Alloys in Plasma Arc Reentry Simulation Tests

- **URL:** <https://ntrs.nasa.gov/api/citations/19740015000/downloads/19740015000.pdf>
- **Authors:** Stanley R. Levine and John P. Merutka, NASA Lewis Research Center and U.S. Army Air Mobility R&D Laboratory.
- **Accessed:** 2026-09-11
- **Relevance:** The one source found that puts a number on the emissivity of silicide-coated columbium. That number sets where a radiation-cooled nozzle extension settles, because equilibrium temperature goes as the inverse fourth root of emissivity.
- **Key findings:**
  - **"Large emittance losses (generally to below 0.7) occurred as a result of the formation of surface refractory metal pentoxides on coated columbium alloys."** This is the value NOVA stores, and it is the conservative one: lower emissivity means a hotter wall.
  - Test conditions: R512E, a fused slurry silicide of Si-20Cr-20Fe, on thin sheet columbium. Half-hour square-wave heating cycles at a stagnation pressure of 6.5e2 N/m^2, which is 4.9 torr of air. Planned 1260 degC, actual average about 1390 degC. Up to 50 cycles as-coated, 5 cycles for intentionally defected specimens.
  - **The substrates were FS-85, Cb-752 and C-129Y, not C103.** The value transfers to C103 only on the coating being the emitting surface, which the report supports by attributing the loss to oxides forming on the coating rather than on the substrate.
  - **The environment oxidises far harder than a vacuum nozzle extension.** This is how far emittance can fall, not where it sits in service.
  - No beginning-of-life emittance is stated in the summary. NOVA therefore stores only the degraded value and records that it stores nothing else.
  - Other findings, useful context rather than stored data: the best system was R512E on FS-85, with first local coating breakdown between 12 and 50 cycles; metal recession at intentional coating defects ran about 0.005 mm/min; coatings retained tensile strength and ductility to 25 cycles, which the report equates to roughly a 100-reentry mission life.
  - **Format:** scanned, 8.3 MB, no text layer.

## Advanced Materials for Radiation-Cooled Rockets

- **URL:** <https://ntrs.nasa.gov/archive/nasa/casi.ntrs.nasa.gov/19940018579.pdf>
- **Accessed:** 2026-09-11
- **Relevance:** Checked as a second source for the emissivity of radiation-cooled thruster materials, and for the wall temperatures such an extension actually runs at.
- **Key findings:**
  - Confirms the material system: C-103 niobium with an R-512A or R-512E fused silica coating is the standard for low-thrust radiation-cooled rockets, with **a maximum operating temperature of 1370 degC**. That sits just under the 1400 degC inert limit NOVA already stores for C103.
  - **Carries no emissivity values at all**, for C-103 or for the iridium-coated rhenium it discusses as the successor. It is a materials-selection and life-limiting-mechanism paper rather than a thermal-design one.

## Leckner, Spectral and Total Emissivity of Water Vapor and Carbon Dioxide

- **URL:** <https://ui.adsabs.harvard.edu/abs/1972CoFl...19...33L/abstract>
- **Venue:** Combustion and Flame, volume 19, 1972.
- **Accessed:** 2026-09-10
- **Relevance:** The standard closed-form alternative to Hottel's charts for the total emissivity of combustion gases, and the intended basis for the gas radiation term. Combustion products radiate through the H2O and CO2 bands, so a gas radiation model needs their partial pressures and a total emissivity.
- **Key findings:**
  - Widely used in place of Hottel's charts, which are known to give water vapour emissivity too low above 900 degC and to carry a temperature-dependent partial pressure correction.
  - **Stated accuracy is about 10 percent** against the spectral data Leckner compiled it from.
  - **Departures from more recent high-resolution spectral data, HITEMP-2010, are typically within plus or minus 40 percent.** Any gas radiation result NOVA produces inherits that, and it has to be reported rather than buried.
  - Abstract only; the correlation coefficients were not retrieved here.

## Stollery and El-Ehwany, A Note on the Use of a Boundary Layer Model for Correlating Film Cooling Data

- **Venue:** International Journal of Heat and Mass Transfer, volume 8, 1965, pages 55 to 65.
- **Accessed:** 2026-09-10, through secondary citations only
- **Relevance:** The other foundational correlation for tangential slot film cooling, repeatedly cited as the basis for correlating film cooling data in a turbulent boundary layer.
- **Key findings:**
  - Referenced throughout the later literature as the boundary-layer-model approach to collapsing film cooling data. Not retrieved directly; Hatch and Papell was preferred because it states its own accuracy.

## Blocked and paywalled

- **Shine and Nidhi, Review on Film Cooling of Liquid Rocket Engines**, Propulsion and Power Research, 2018. <https://www.sciencedirect.com/science/article/pii/S2212540X1830004X> returns **HTTP 403** to automated access. It reviews the Grisson, Shembharkar-Pai and Stechman liquid film models together, which would have saved reading them separately.
- **EUCASS 2022 and 2023 papers on low-order film cooling modeling and validation.** <https://www.eucass.eu/> timed out. These carry validation against open-literature experimental data, which is exactly what the liquid film closure needs and currently lacks.
- **Taylor and Groot, Thermal Conductivity and Electrical Resistivity of Two Types of ATJ-S Graphite to 3500 K**, Carbon, 1973. Paywalled, abstract only. Would have supplied the conductivity curve for a graphite radiation-cooled component.
- **Emissivity of the copper wall alloys.** No source was found giving emissivity for GRCop-42, GRCop-84, CuCrZr or NARloy-Z at any surface condition, let alone the oxidized as-built finish a laser powder bed fusion chamber actually has. Searching the GRCop development and hot-fire literature returns oxidation behavior and blanching resistance but no radiative properties. NOVA therefore stores none, and a radiation term that needs one takes it from the configuration.
- **Thermal conductivity of C103 across its service range.** The store carries conductivity curves for the ten jacket alloys only, and `wallMaterialCurves` substitutes GRCop-42 for anything else, which conducts about eight times better. Unlike the emissivity this is a routine measurement rather than a hard one, but no open curve was located in the sources reached here. The extension solver takes conductivity as an explicit input in consequence, and `docs/materialsDatabaseRoadmap.md` records it as step 10.

## Sources generated rather than retrieved

Two quantities the models needed were not available as published numbers and were computed instead. Both are recorded here so that a reader can tell them apart from literature values.

- **Transport power laws for a rocket exhaust**, `k ~ T^a`, `mu ~ T^b`, `Pr ~ T^c`, fitted over 900 to 3600 K from CEA solves at frozen composition across five propellant cases. They set the film correlation's property correction to the film mean temperature. The fitted values and the propellants behind them are in the `filmCooling` module header and in `docs/reports/coolingModelExtension_2026-09-11.md`; the net power reaching the answer stays inside 0.394 to 0.431 across hydrogen, kerosene and methane.
- **The equilibrium contribution to CEA's thermal conductivity**, a factor of 2.67 at 3398 K falling to 1.37 by 2269 K for a LOX/LH2 exhaust at 6.9 MPa, from the same solves run frozen and equilibrium. It is why a Colburn-form correlation fitted on non-reacting air should be given the molecular conductivity rather than the equilibrium one, which is recorded as outstanding rather than done.
