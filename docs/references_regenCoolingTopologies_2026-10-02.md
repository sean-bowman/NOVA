# References: regenerative cooling circuit topologies

Sources retrieved for the cooling circuit architecture of a regeneratively cooled jacket: the number of coolant passes, the flow direction relative to the gas, changes in channel count along the chamber, independent and multi-fluid circuits, and the coolant that bypasses the jacket. The cross-section families and the coolant-side correlations are covered in references_regenChannels_2026-09-22.md.

## Liquid Rocket Engine Fluid-Cooled Combustion Chambers

- **URL:** https://ntrs.nasa.gov/citations/19730022965 (PDF: https://ntrs.nasa.gov/api/citations/19730022965/downloads/19730022965.pdf)
- **Accessed:** 2026-10-02
- **Relevance:** The design monograph that enumerates the pass configurations and states which to use where. It is the primary source for every topology claim in regenCoolingArchitectures.md.
- **Key findings:**
  - NASA SP-8087, NASA Space Vehicle Design Criteria (Chemical Propulsion), Lewis Research Center, April 1972. Section 2.1.1.2 "Number of Passes" at page 10; design criteria at 3.1.1.3.3, page 56.
  - Three pass configurations are in use: one pass, with the coolant flowing forward from the expansion section; one-and-a-half passes, with the coolant introduced in the expansion section, flowing down and then up to the injector; two passes, with the flow proceeding down from the injector and returning up through alternating passages.
  - One pass is the simplest concept, requires larger flow passages at the highest-flux regions and a large manifold at a high expansion ratio, and puts mass at the aft end, which aggravates gimballing requirements and reduces the engine natural frequency. The monograph recommends it for smaller chambers only.
  - The "half" of a one-and-a-half pass is a partial pass starting below the throat. The configuration is used with coolants that must be heated before they become effective: liquid hydrogen is introduced in the expansion sections of the RL10 and J-2 because it must be gasified before it can accommodate the throat heat flux.
  - Two passes complicate the forward manifold and permit higher coolant velocities with larger diameter tubes than one pass. The turnaround manifold is light, so gimballing is less affected. More than two passes has been considered where coolant was limited; the additional pressure drop and the manifolding made it undesirable.
  - Turnaround manifolds collect the coolant at the end of a pass and direct it into the next. The reversal is taken at low velocity. The manifold is either a common annulus to all tubes or carries discrete passages.
  - Bifurcation joints, where two smaller tubes are joined to the large end of a single tube, are used in expansion nozzles "to maintain reasonable coolant velocities with state-of-the-art tubes". They are operational on Stage I Titan II and F-1 and are named a persistent trouble source. Two construction methods are allowed: full welding with the tubes fitted against each other, or brazing with the secondary tubes inserted into the primary.
  - All of the large thrust production units use multi-pass tubular wall construction. The single-pass exception is NERVA, whose U-section tubes were brazed to a heavy outer shell because nuclear heating required the structural jacket to be cooled.
  - The Agena drilled-passageway chamber runs its aft conical section two-pass at a 25 degree cant angle with the inlet at the forward end of the cone.
  - RP-1 is noted for coking at wall temperatures above 800 to 900 degrees F (700 to 756 K).
  - On transpiration cooling: "many design, fabrication, and operational areas must be resolved before transpiration cooling can be considered operational."

## Space Shuttle Main Engine Orientation

- **URL:** http://large.stanford.edu/courses/2011/ph240/nguyen1/docs/SSME_PRESENTATION.pdf
- **Accessed:** 2026-10-02
- **Relevance:** The flight example of two cooled circuits in parallel with a controlled bypass around one of them. It is the reference for treating the jacket flow fraction as a design variable rather than an input.
- **Key findings:**
  - Boeing / Rocketdyne Propulsion and Power, Space Transportation System training data, SSME orientation, 1998.
  - Hydrogen leaving the main fuel valve splits three ways at the diffuser: 19 percent up the 430 main combustion chamber coolant channels, 27.5 percent up the 1080 nozzle tubes, and 48.5 percent around the nozzle through the chamber coolant valve.
  - Both cooled circuits run up-pass, against the gas. They are in parallel with each other, not in series.
  - The chamber circuit discharges into the low-pressure fuel turbopump turbine, so its exit enthalpy is a cycle requirement and not only a wall-temperature result.
  - The chamber coolant valve is one of the five valves that set start, run and shutdown behavior, so the split is actively controlled rather than fixed by the hardware.
  - The MCC liner carries 430 vertical milled slots closed out by electrodeposited nickel.

## LUMEN: Design of the Regenerative Cooling System for an Expander Bleed Cycle Engine Using Methane

- **URL:** https://elib.dlr.de/141456/1/210217_SP_Haemisch_final.pdf
- **Accessed:** 2026-10-02
- **Relevance:** Current practice for parameterizing a cooling channel design, and the reference for mixed flow direction within one engine. It is also the source for the expander-cycle constraint that opposes minimum wall temperature.
- **Key findings:**
  - J. Haemisch, D. Suslov, G. Waxenegger-Wilfing, K. Dresia and M. Oschwald, DLR Institute of Space Propulsion, Space Propulsion 2020, paper SP2020_00068.
  - "The flow direction is counterflow for the nozzle and combustion chamber and coflow for the nozzle extension." Direction is treated as a per-section choice.
  - Design goals: coolant exit temperature above 400 K, wall temperature below 900 K, channel pressure drop below 25 bar.
  - Manufacturing and structural constraints: channel width at least 1 mm, rib between channels at least 1 mm, 1 mm to the hot gas side, at most 86 channels. The channel count follows from these constraints at the throat.
  - The channel geometry is varied at 5 characteristic axial positions and interpolated linearly between them. The positions are the start and end of the decreasing heat flux in the cylindrical part, the nozzle, and the start and end of the chamber.
  - Coolant mass flow is a design variable alongside the geometry, within the range the engine architecture allows.
  - For an expander cycle a third goal applies: enough coolant enthalpy rise to drive the turbopumps. It opposes maximum cooling, since a large coolant temperature rise comes with a hot wall. This is why expander engines carry long cylindrical chambers.
  - A 40 K reduction in hot-gas-side wall temperature is quoted as doubling engine life.

## Comparison of High Aspect Ratio Cooling Channel Designs for a Rocket Combustion Chamber

- **URL:** https://ntrs.nasa.gov/citations/19980017619 (PDF: https://ntrs.nasa.gov/api/citations/19980017619/downloads/19980017619.pdf)
- **Accessed:** 2026-10-02
- **Relevance:** The quantitative case for changing the channel count along the chamber instead of holding it fixed. The channel-family entry for the same report is in references_regenChannels_2026-09-22.md; the findings here are the ones about channel count and shape.
- **Key findings:**
  - Mary F. Wadel, NASA TM-1998-206313, January 1998. Liquid hydrogen cooled chamber, wall temperature limit 667 K (1200 degrees R), analyzed with the Rocket Thermal Evaluation code coupled to Two-Dimensional Kinetics.
  - Three channel shapes are defined and compared (Figure 5): continuous, with smooth transitions in width; bifurcated, split into two channels and combined back into one; stepped, with a sharp change to another width.
  - Of the seven designs, the one using bifurcated channels gave the largest overall benefit: 20 percent wall temperature reduction for a 9 percent pressure drop increase. Optimizing that design gave an 18 percent wall temperature reduction with a 4 percent pressure drop reduction.
  - High aspect ratio channels over the entire chamber length gave no significant wall temperature advantage over the throat region alone and significantly increased the pressure drop. Running 200 channels over the entire length improved the wall temperature profile at a high pressure drop penalty.
  - Reducing coolant mass flow by 40 percent on the optimized design still gave a 5 percent wall temperature reduction against the baseline and cut the pressure drop by 47 percent.
  - Milling cannot produce a clean bifurcation. The transition section leaves the single channel with an exaggerated flow area, which reduces heat transfer locally and can raise the wall temperature there. The study carried the transition area explicitly rather than assuming an ideal split.
  - The coolant inlet pressure was raised until the coolant exit pressure exceeded the chamber pressure, to hold the positive differential that prevents back flow into the channels.

## Technology Advancements for Channel Wall Nozzle Manufacturing in Liquid Rocket Engines

- **URL:** https://ntrs.nasa.gov/citations/20205002297 (PDF: https://ntrs.nasa.gov/api/citations/20205002297/downloads/Gradl_Protz_CWN_Manufacturing_Acta-Astronautica_May2020.pdf)
- **Accessed:** 2026-10-02
- **Relevance:** Establishes that a channel count change along the nozzle is current, hot-fire tested practice in printed and milled channel wall nozzles, not only tube-bundle heritage.
- **Key findings:**
  - P. R. Gradl and C. S. Protz, Acta Astronautica 174 (2020) 148-158.
  - Multi-axis abrasive water jet milling allows "bifurcated channels, dove tail channels for bonding enhancement, integral instrumentation ports, multi-pass channels and integral turnarounds, undercuts".
  - A subscale channel wall nozzle built from Inconel 625 by blown powder directed energy deposition "used a bifurcated channel design as the diameter increased". It was hot-fire tested with LOX/GH2 and later regeneratively cooled with RP-1. A second nozzle of the same design was built in JBK-75.
  - Earlier water jet milling left tapered channel sidewalls, narrower at the hot wall, which added material volume over the hot wall and was undesirable. The process was changed to square the channels and replicate slotting.
  - Nozzles were assembled in three pieces: the channel liner, the forward manifold and the aft manifold.

## Design and Cooling Performance of a Dump-Cooled Rocket Engine

- **URL:** https://ntrs.nasa.gov/citations/19660022898 (PDF: https://ntrs.nasa.gov/api/citations/19660022898/downloads/19660022898.pdf)
- **Accessed:** 2026-10-02
- **Relevance:** States the design objective of a dump-cooled jacket and contrasts it with the regenerative one. It is the reference for the objective inversion and for where the jacket pressure drop sits in the feed system.
- **Key findings:**
  - A. J. Pavli, J. K. Curley, P. A. Masters and R. M. Schwartz, NASA TN D-3532, Lewis Research Center, August 1966.
  - 500 lbf engine at 100 psig chamber pressure, GH2/LOX propellants, liquid hydrogen coolant, stainless steel, mixture ratio 5, designed at 7 percent of total propellant flow through the jacket. Fourteen firings, the last four with an aluminum oxide coating on the flame side.
  - In dump cooling the coolant is dumped overboard through its own convergent-divergent nozzle instead of passing through the injector. "By this means, coolant jacket pressure drop is put in parallel with the injector pressure drop, and the propellant tanks can be pressurized to a lower pressure than is possible for a similar regeneratively cooled engine."
  - The design objective inverts: "the dump-cooled engine must be designed to raise the temperature of the coolant to the highest temperature consistent with materials in the engine by using the minimum coolant flow possible. This is unlike the design of a more conventional regeneratively cooled engine where the coolant flow is fixed and the pressure drop in the coolant jacket is minimized."
  - Measured minimum satisfactory coolant flow was 6.9 percent of total propellant flow with the refractory coating and 7.5 percent without it.
  - Coolant velocity was optimized along the chamber so that the metal temperature was held nearly constant and equal to the material limit, which is the same per-station rule a wall-temperature-targeted sizing solve implements.
  - Analytically, the coolant exit temperature can be made high enough that the dumped hydrogen's specific impulse reaches or exceeds that of the main combustion process.

## Liquid Oxygen Cooling of Hydrocarbon Fueled Rocket Thrust Chambers

- **URL:** https://ntrs.nasa.gov/citations/19890015076 (PDF: https://ntrs.nasa.gov/api/citations/19890015076/downloads/19890015076.pdf)
- **Accessed:** 2026-10-02
- **Relevance:** The reference for running the oxidizer as the coolant, which is the case that makes a second fluid worth modeling rather than a second mass flow of the same fluid.
- **Key findings:**
  - Elizabeth S. Armstrong, NASA TM-102113, AIAA 89-2739, July 1989.
  - Hydrocarbons such as RP-1 are limited in cooling capability, which is what puts liquid oxygen forward as the coolant for high pressure LOX/hydrocarbon boosters.
  - Chambers tested with LOX/RP-1 propellants and LOX as the coolant demonstrated feasibility up to a chamber pressure of 13.8 MPa (2000 psia).
  - Chambers were built with slots machined between the coolant passage wall and the hot gas wall upstream of the throat to simulate fatigue cracks, and tested at a nominal 8.6 MPa (1247 psia) over mixture ratios of 1.9 to 3.1. The leaking LOX did not damage the chambers in the region of the slots. Both chambers showed unexplained melting in the throat region, not in line with the slots.

## Cooling of Rocket Thrust Chambers With Liquid Oxygen

- **URL:** https://ntrs.nasa.gov/citations/19900013289 (PDF: https://ntrs.nasa.gov/api/citations/19900013289/downloads/19900013289.pdf)
- **Accessed:** 2026-10-02
- **Relevance:** The follow-up that resolves the throat melting left open by TM-102113 and states the safety conclusion for an oxygen-cooled liner.
- **Key findings:**
  - Elizabeth S. Armstrong and Julie A. Schlumberger, NASA TM-103146, AIAA-90-2120, July 1990.
  - The program was run to find the cause of the earlier throat failures and to further test the effect of liner cracks upstream of the throat.
  - Conclusion: "LOX can be used safely as a coolant, even if cracks should develop in the chamber wall upstream of the throat", with no damage to the facility or attached hardware.

## F-1 Engine Thrust Chamber Description

- **URL:** https://www.enginehistory.org/Rockets/RPE08.11/RPE08.12.shtml
- **Accessed:** 2026-10-02
- **Relevance:** The concrete hardware example of a two-pass circuit with a jacket bypass and a tube count change, all on one engine. Secondary source, drawn from F-1 technical manuals rather than from a primary NASA report.
- **Key findings:**
  - Three toroidal fuel manifolds stacked at the top of the thrust chamber. Fuel enters the middle manifold.
  - An orificed plug above the inlet slot sends 30 percent of the fuel directly to the injector manifold; the remaining 70 percent cools the chamber.
  - Every other primary tube is a fuel-down tube. The coolant runs down the chamber to the fuel return manifold at the aft end and back up the adjacent tubes, which makes it a two-pass circuit in alternating passages.
  - 178 primary tubes of 1.093 in. Inconel-X above the 3:1 expansion ratio plane; 356 secondary tubes of 1.000 in. outside diameter from 3:1 to 10:1. The count doubles where the diameter grows.
