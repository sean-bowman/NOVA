# References: regenerative cooling channels

Sources retrieved for the rectangular and helical channel families and for the comparison of the channel thermal model against hardware.

## An Experimental Investigation of High-Aspect-Ratio Cooling Passages

- **URL:** https://ntrs.nasa.gov/citations/19920016715 (PDF: https://ntrs.nasa.gov/api/citations/19920016715/downloads/19920016715.pdf)
- **Accessed:** 2026-09-22
- **Relevance:** The hardware reference for rectangular channels: three copper chambers differing only in channel aspect ratio, with the throat wall temperature reported against coolant mass flux. NOVA's section, fin and coolant-side model is compared against it in docs/reports/carlileQuentmeyer_2026-09-22.md.
- **Key findings:**
  - Julie A. Carlile and Richard J. Quentmeyer, NASA TM-105679, AIAA-92-3154, July 1992.
  - OFHC copper cylinders, 6.60 cm inside diameter, 0.089 cm hot wall, 15.24 cm long; GH2/LOX at 4.136 MPa and a mixture ratio of 6.0; liquid hydrogen coolant.
  - Throat channels (Table 1): aspect ratio 0.75 with 72 passages 0.127 by 0.170 cm; 1.50 with 100 passages 0.152 by 0.102 cm; 5.00 with 400 passages 0.127 by 0.0254 cm.
  - The baseline runs a 778 K wall at 0.909 kg/s, at a throat heat flux of about 97.1 MW/m^2. At the same 4.136 MPa coolant pressure drop the 5.00 chamber's wall is 30 percent cooler (765 to 539 K), and it showed no fatigue damage after 440 cycles.
  - Wall temperatures are inferred from thermocouples through a SINDA conduction model with fitted coolant-side coefficients; the channels are straight, and the authors name mixing between the bottom and top of a tall channel as what sets the optimum aspect ratio.

## Comparison of High Aspect Ratio Cooling Channel Designs for a Rocket Combustion Chamber With Development of an Optimized Design

- **URL:** https://ntrs.nasa.gov/citations/19980017619 (PDF: https://ntrs.nasa.gov/api/citations/19980017619/downloads/19980017619.pdf)
- **Accessed:** 2026-09-22
- **Relevance:** An analytical study of the same class of channels, retrieved for context on high aspect ratio design trades. Not used as a reference for any number.
- **Key findings:**
  - Mary F. Wadel, NASA TM-1998-206313, January 1998.
  - Seven channel designs for a liquid hydrogen cooled chamber, varying the length of chamber given high aspect ratio channels, the channel count and the channel shape, analyzed with the Rocket Thermal Evaluation code coupled to Two-Dimensional Kinetics.
  - Hot-gas wall temperature reductions of up to 22 percent with coolant pressure drop increases as low as 7.5 percent; with milled-channel fabrication limits, up to 20 percent and 2 percent.

## Explicit Equations for Pipe-Flow Problems

- **URL:** https://www.researchgate.net/publication/280018838_Explicit_eqations_for_pipe-flow_problems
- **Accessed:** 2026-09-22
- **Relevance:** The source of the explicit friction factor NOVA's coolant side uses.
- **Key findings:**
  - P. K. Swamee and A. K. Jain, Journal of the Hydraulics Division, ASCE, Vol. 102, No. 5, 1976, pp. 657-664.
  - An explicit approximation to Colebrook-White for the Darcy friction factor, quoted for relative roughness 1e-6 to 1e-2 and Reynolds numbers 5e3 to 1e8.
  - Measured in tests/testRegenThermal.py against Colebrook solved by iteration: within 1 percent for Reynolds numbers 1e4 to 1e7 at relative roughness up to 1e-3, within 2.8 percent over the quoted range.

## Heat and Momentum Transfer in Smooth and Rough Tubes at Various Prandtl Numbers

- **URL:** https://www.sciencedirect.com/science/article/abs/pii/0017931063900978
- **Accessed:** 2026-09-22
- **Relevance:** Rough-tube heat transfer data, cited for the finding that NOVA credits roughness with heat transfer in proportion to friction.
- **Key findings:**
  - D. F. Dipprey and R. H. Sabersky, International Journal of Heat and Mass Transfer, Vol. 6, 1963, pp. 329-353.
  - Sand-grain roughened tubes measured for friction and heat transfer over a range of Prandtl numbers.
  - The heat transfer increase from roughness lags the friction increase, so a smooth-tube correlation fed a rough-wall friction factor overstates the heat transfer.

## Properties of Selected Materials at Cryogenic Temperatures

- **URL:** https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=913059 (index: https://www.nist.gov/mml/acmd/cryogenic-materials-properties-reference-list)
- **Accessed:** 2026-09-22
- **Relevance:** The cryogenic segment of the OFHC copper conductivity curve NOVA's materials store holds and the comparison uses.
- **Key findings:**
  - Curve-fitted conductivity, specific heat, expansion and modulus from 4 to 300 K.
  - Fits typically within 1 to 2 percent of a single data set, and up to about 5 percent where several are combined.
  - Copper conductivity at cryogenic temperature depends strongly on purity (RRR); room temperature cannot distinguish grades.
