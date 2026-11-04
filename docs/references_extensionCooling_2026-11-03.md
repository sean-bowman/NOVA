# References: Actively Cooled and Film-Cooled Nozzle Extensions

Sources gathered on multi-pass coolant circuits that carry a jacket over a nozzle extension, and on film cooling an extension with turbine exhaust or dumped coolant. Pass configurations, jacket bypass, bifurcation and dump cooling are already annotated in [references_regenCoolingTopologies_2026-10-02.md](references_regenCoolingTopologies_2026-10-02.md); SP-8124, Hatch and Papell and the radiative extension sources are in [references_filmAndRadiativeCooling_2026-09-11.md](references_filmAndRadiativeCooling_2026-09-11.md). Several primary documents could not be retrieved on 2026-11-03 and are marked as such; their findings below come from abstracts and search summaries and are labeled accordingly.

---

## Rocketdyne F-1

- **URL:** https://en.wikipedia.org/wiki/Rocketdyne_F-1 (revision 1363029414)
- **Accessed:** 2026-11-03
- **Relevance:** The flight engine that combines a two-pass regenerative chamber with a turbine-exhaust film-cooled extension, which are the two features under study. Secondary source.
- **Key findings:**
  - Part of the fuel "first traveled in 178 tubes down the length of the thrust chamber ... and back in order to cool the nozzle"; the tube bundle covered about the upper half of the nozzle. The primary circuit description (70 percent through the tubes, alternating down and up tubes, return manifold at the aft end, 178 primary tubes bifurcating to 356 at an area ratio of 3) is in the 2026-10-02 bibliography.
  - The extension takes the area ratio from 10 to 16. "The exhaust from the turbine was fed into the nozzle extension by a large, tapered manifold; this relatively cool gas formed a film which protected the nozzle extension from the hot (5,800 F) exhaust gas."
  - LOX/RP-1, 70 bar chamber pressure, mixture ratio 2.27, gas generator cycle, 6.77 MN at sea level.
  - The F-1B concept removes "the turbine exhaust mid-nozzle and the 'curtain' cooling manifold", so the film-cooled extension is a feature of the gas generator cycle rather than of the circuit.

## F-1 Engine Thrust Chamber (heroicrelics.org)

- **URL:** http://heroicrelics.org/info/f-1/f-1-thrust-chamber.html
- **Accessed:** 2026-11-03, **not read**: the server refused the connection. Findings are from a search summary of the page.
- **Relevance:** The construction of the F-1 turbine exhaust injection, which sets what an extension film model has to represent.
- **Key findings (search summary only):**
  - The turbine exhaust, at about 1200 F (920 K), enters the extension between a continuous outer wall and a shingled inner wall and leaves through injection slots between the shingles, so the film is renewed at several stations rather than injected once.
  - About two thirds to 70 percent of the fuel passes through the tubes; the sources disagree on the figure.

## Rocketdyne J-2

- **URL:** https://en.wikipedia.org/wiki/Rocketdyne_J-2 ; https://www.enginehistory.org/Rockets/RPE08.22/RPE08.22.shtml
- **Accessed:** 2026-11-03, through search summaries
- **Relevance:** The one-and-a-half pass circuit on a hydrogen engine, with the inlet partway down the nozzle.
- **Key findings:**
  - "The fuel made a one-half pass downward through 180 tubes and was returned in a full pass up to the thrust chamber injector through 360 tubes": one tube down for every two up.
  - Tubes of 0.012 in stainless steel, stacked longitudinally and furnace brazed.

## Vulcain 2 nozzle cooling

- **URL:** https://en.wikipedia.org/wiki/Vulcain_(rocket_engine) ; https://www.volvogroup.com/en/news-and-media/news/2001/apr/volvo-technology-prize-2001.html
- **Accessed:** 2026-11-03, through search summaries
- **Relevance:** The production example of a dump-cooled upper nozzle whose coolant, together with the turbine exhaust, film-cools the lower nozzle. It joins the two features into one circuit.
- **Key findings:**
  - The upper nozzle is dump cooled by hydrogen at about 3 kg/s through helical rectangular channels in the liner.
  - The lower nozzle is film cooled by the turbine exhaust at about 10 kg/s, together with the hydrogen already used to cool the upper part, injected at a set area ratio. Taken against an engine flow of roughly 320 kg/s, estimated here from published thrust and specific impulse rather than read from a source, that is about 3 percent turbine exhaust and 1 percent hydrogen.
  - Film cooling let the lower wall be sheet metal rather than welded tubes, which reduced cost. A later Vulcain 2+ demonstrator used a full-length dump-cooled laser-welded sandwich wall.

## Suslov, Arnold and Haidn, Convective and Film Cooled Nozzle Extension for a High Pressure Rocket Subscale Combustion Chamber

- **URL:** https://core.ac.uk/works/4663449 (PDF https://core.ac.uk/download/11140342.pdf); https://elib.dlr.de/62530/
- **Accessed:** 2026-11-03. The PDF returned **HTTP 403**; findings are from the abstract.
- **Relevance:** Measured film cooling of a supersonic extension at engine-like chamber pressure, which is the data an extension film closure would be validated against.
- **Key findings (abstract only):**
  - AIAA paper, 2010. A Vulcain 2-like nozzle geometry tested at chamber pressures up to 13 MPa, with hydrogen injected at supersonic velocity as a film at an area ratio of 32 to protect the lower nozzle.
  - Reports stable operation across coolant mass flows, and studies heat transfer, flow separation and side loads.
  - A companion 2009 Journal of Propulsion and Power paper by the same group gives a model predicting film effectiveness at sub-, trans- and supersonic conditions and different film blowing rates; a 2009 AIAA paper names blowing rate, velocity ratio and slot height as the governing parameters.

## Martelli, Nasuti and Onofri, Numerical Analysis of Film Cooling in Advanced Rocket Nozzles

- **URL:** https://iris.uniroma1.it/handle/11573/358252 ; DOI 10.1514/1.39217
- **Accessed:** 2026-11-03, abstract only
- **Relevance:** Turbine exhaust film in a nozzle divergent section, studied numerically, including its effect on side loads.
- **Key findings (abstract only):**
  - AIAA Journal 47, 2009, pages 2558 to 2566. Parametric study of film effectiveness in dual-bell nozzles with turbine exhaust injected in the divergent section, described as a common way to recover some performance in gas generator open-cycle engines.

## NASA MSFC, J-2X nozzle extension turbine exhaust film cooling

- **URL:** https://ntrs.nasa.gov/citations/20120002821 ; companion https://ntrs.nasa.gov/api/citations/20100033432/downloads/20100033432.pdf
- **Accessed:** 2026-11-03, **not read**: ntrs.nasa.gov did not resolve. Findings are from search summaries.
- **Relevance:** The closest open treatment of a turbine exhaust film on a large metallic extension, and the source of the Calspan supersonic film data a closure could be checked against.
- **Key findings (search summary only):**
  - CFD (Loci-CHEM) of the turbine exhaust manifold, the structural ribs and the mixing with the core: manifold swirl, non-uniformity and rib wakes reduce film effectiveness below that of idealized injection.
  - Morris and Ruf (2010) checked the CFD against Calspan supersonic film cooling experiments from the late 1980s and early 1990s, two- and three-dimensional, covering flat plate heating, the coolant nozzle flow and the film flowfield.

## Juhany, Supersonic Film Cooling Including the Effect of Shock Wave Interaction

- **URL:** https://thesis.library.caltech.edu/4945
- **Accessed:** 2026-11-03, abstract only
- **Relevance:** Measured supersonic slot film effectiveness, including injection Mach number and temperature effects.
- **Key findings (abstract only):**
  - Caltech PhD, 1994, advised by M. Hunt. Larger injection Mach numbers slightly increase the cooling length per unit injected mass; heated injection at velocity ratios above one can give effectiveness above one downstream of the slot; an impinging shock degrades the film where it lands.
  - Companion paper: Juhany, Hunt and Sivo, Journal of Thermophysics and Heat Transfer, 1994, on the influence of injectant Mach number and temperature.

## Goldstein, Eckert, Tsou and Haji-Sheikh, Film Cooling with Air and Helium Injection through a Rearward-Facing Slot into a Supersonic Air Flow

- **URL:** https://experts.umn.edu/en/publications/film-cooling-with-air-and-helium-injection-through-a-rearward-fac/ ; DOI 10.2514/3.3591
- **Accessed:** 2026-11-03, abstract only
- **Relevance:** The founding measurement of tangential slot film cooling in a supersonic stream, and the starting point for supersonic effectiveness correlations.
- **Key findings (abstract only):**
  - AIAA Journal 4, 1966, pages 981 to 985. Air and helium injected parallel to the wall through a rearward-facing slot into a Mach 3 stream.
  - The correlation form was not retrieved. Goldstein's 1971 review, Film Cooling, Advances in Heat Transfer 7, pages 321 to 380, collects the early correlations.

## Ludescher and Olivier, supersonic tangential film cooling in a conical nozzle

- **URL:** https://publications.rwth-aachen.de/record/817881
- **Accessed:** 2026-11-03, **not read**: the server returned an empty page.
- **Relevance:** Reported in search results as an experimental and theoretical study of supersonic tangential film cooling in a conical nozzle with an axisymmetric film model, which is the geometry an extension film closure needs.
- **Key findings:** none retrieved.

## Cadou group, University of Maryland: film cooling in supersonic flow

- **URL:** https://drum.lib.umd.edu/handle/1903/10376 (dissertation, 2010); https://drum.lib.umd.edu/handle/1903/16806 (Collett, thesis, 2015)
- **Accessed:** 2026-11-03, abstracts only
- **Relevance:** Semi-empirical corrections for the effects a flat-plate closure misses, and a supersonic rig built on J-2X extension conditions.
- **Key findings (abstracts only):**
  - The 2010 dissertation proposes semi-empirical models for pressure gradient, compressibility and density gradient effects on film effectiveness, and states that there is little usable supersonic film cooling data for engine designers and that CFD did not yet match it quantitatively.
  - The 2015 thesis measured effectiveness from wall thermocouples on a test matrix drawn from J-2X nozzle extension conditions and compared it with Loci-CHEM.

## Peter and Kloker, Direct Numerical Simulation of Supersonic Turbulent Flow with Film Cooling by Wall-Parallel Blowing

- **URL:** DOI 10.1063/5.0080049
- **Accessed:** 2026-11-03, abstract only
- **Relevance:** A resolved flat-plate reference for a supersonic slot film behind a step, usable to check a closure's trend, not its rocket-condition level.
- **Key findings (abstract only):** Physics of Fluids, 2022. Mach 3.3 turbulent steam flow with a laminar supersonic helium film injected behind a backward-facing step.

## NASA SP-8120, Liquid Rocket Engine Nozzles

- **URL:** https://ntrs.nasa.gov/citations/19770009165
- **Accessed:** 2026-11-03, record only; full text not read
- **Relevance:** The design monograph for nozzle extensions, including those cooled by turbine exhaust gas.
- **Key findings (record only):** 1976. Covers regeneratively cooled tube-wall nozzles and extensions, extensions cooled by turbine exhaust gas, and ablative and radiation-cooled extensions; a figure gives two recommended methods for introducing turbine exhaust into the nozzle.

## Two-directional regenerative cooling passages for a 30 tonf liquid rocket nozzle

- **URL:** https://www.koreascience.or.kr/article/JAKO200811433116303.page?lang=en
- **Accessed:** 2026-11-03, English abstract only
- **Relevance:** A mid-nozzle coolant inlet with flow going both ways from it, analyzed for pressure loss.
- **Key findings (abstract only):** 2008. Fuel fed at a mid-nozzle position flows toward both ends to reduce the pressure loss of the cooling passage; the abstract does not treat heat exchange between passes.

## Multi-pass coolant passage patents

- **URL:** https://patents.google.com/patent/US2977754A/en ; https://patents.google.com/patent/US8689540
- **Accessed:** 2026-11-03, through search summaries
- **Relevance:** Hardware arrangements for adjacent passes flowing in opposite directions, and the manifolding and flow-balance problems they bring.
- **Key findings:**
  - US2977754A pairs first-pass and second-pass tubes, the first pass nearer the axis, coolant collecting in an annulus and returning through the outer tube.
  - US8689540B2 surveys single-pass, double-pass and balanced double-pass layouts: double-pass layouts are hard to connect to manifolds, and flow imbalance between paths costs cooling and life.

## Sources generated rather than retrieved

- **Extension feasibility runs on NOVA, 2026-11-03.** The shipped LOX/LH2 nozzle and a sea-level LOX/CH4 first stage (500 kN, 10 MPa, mixture ratio 3.5, area ratio 25, 120 channels, 33 kg/s of methane at 115 K and 20 MPa) were solved with the jacket ending at an area ratio of 3 and carried to the exit, and a slot film at the joint was run through the existing SP-8124 and Hatch-Papell closures into the radiative extension solver. These are computed results of unvalidated models, recorded so they are not mistaken for literature values.
