# References: engine throttling and nozzle flow separation

Sources retrieved for a plume model driven by engine power level at fixed ambient pressure: how far real engines throttle, what limits them, and where an overexpanded nozzle separates. The plume structure correlations and the characteristics march they seed are covered in references_plumeStructure_2026-09-04.md.

## Liquid-Propellant Rocket Engine Throttling: A Comprehensive Review

- **URL:** https://ntrs.nasa.gov/citations/20090037061 (PDF: https://ntrs.nasa.gov/api/citations/20090037061/downloads/20090037061.pdf)
- **Accessed:** 2026-10-03
- **Relevance:** The survey of what throttling does to an engine, and the source for the hardware evidence that separated nozzle operation is a damaging regime rather than merely an inaccurate one.
- **Key findings:**
  - M. J. Casiano, J. R. Hulka and V. Yang, NASA Marshall Space Flight Center, published as Journal of Propulsion and Power Vol. 26 No. 5, 2010.
  - Throttling beyond 4:1 is termed deep throttling, and a fixed-geometry injector accommodating 5:1 or more needs a higher than usual injector pressure drop.
  - On an early throttled engine, heat transfer rates held constant down to roughly 59 percent chamber pressure and dropped below it, which the program attributed to flow separating in the nozzle. Characteristic velocity efficiency fell significantly below roughly 30 percent chamber pressure, explained by poorer combustion rather than by the nozzle.
  - RD-0120 was run at 25 percent power at a sea level facility for 480 seconds. About 20 percent of the brackets holding the stiffening rings to the nozzle were damaged, attributed to excessive nozzle vibration during separated nozzle flow. The nozzle was not designed for that power level.
  - SSME was throttled to 17 percent, about 6.4:1 from maximum power, in the X-33 evaluations. Nozzle separation heat loads came in higher than expected. Mixture ratio was held between 3 and 4 for turbopump margin, and the pump stall point, not the nozzle, was the issue that drove the operating balance.
  - Below roughly 30 percent chamber pressure on a regeneratively cooled engine, the fuel coolant was projected to vaporize in the jacket, and the engine had to be run at low mixture ratio to prevent it.

## CECE: Expanding the Envelope of Deep Throttling Technology in Liquid Oxygen/Liquid Hydrogen Rocket Engines

- **URL:** https://ntrs.nasa.gov/citations/20100032918 (PDF: https://ntrs.nasa.gov/api/citations/20100032918/downloads/20100032918.pdf)
- **Accessed:** 2026-10-03
- **Relevance:** The deepest demonstrated throttle range on an engine of the class NOVA's reference case describes, which bounds how much of a throttle sweep is an engine question rather than a nozzle question.
- **Key findings:**
  - Pratt and Whitney Rocketdyne Deep Throttling Common Extensible Cryogenic Engine, NASA Exploration Technology Development Program. The testbed was an RL10 derivative, LOX/LH2, expander cycle.
  - 7436 seconds of hot fire over 47 tests between April 2006 and April 2010.
  - The final test demonstrated a chug-free minimum power level of 5.9 percent, an overall throttling ratio of 17.6:1 from 104 percent.
  - The instabilities that bounded the range were combustion-side, and the mitigations were injector and propellant-conditioning technologies rather than nozzle changes.

## Flow Separation in Rocket Nozzles, an Overview

- **URL:** https://elib.dlr.de/49253/1/AIAA2005-3940.pdf
- **Accessed:** 2026-10-03
- **Relevance:** The separation criteria themselves, with a measurement of how well they do. It is the source for the criterion a throttle model should use and for the caveat on using it.
- **Key findings:**
  - R. Stark, DLR Lampoldshausen, AIAA Paper 2005-3940, 41st Joint Propulsion Conference.
  - Summerfield criterion: separation at a wall static to ambient pressure ratio of 0.35 to 0.40, independent of Mach number. Original source M. Summerfield, C. Foster and W. Swan, "Flow Separation in Overexpanded Supersonic Exhaust Nozzles", Jet Propulsion Vol. 24 No. 9, 1954, pp. 319-321, cited through this overview rather than read directly.
  - Schmucker criterion, suggested for short bell nozzles: `p_sep / p_a = (1.88 Ma_sep - 1)^-0.64`, with `Ma_sep` the wall Mach number at the separation point. Original source R. Schmucker, "Stroemungsvorgaenge beim Betrieb ueberexpandierter Duesen chemischer Raketentriebwerke, Teil 1: Stroemungsabloesung", Bericht TB-7, TU Munich, 1973, in German, cited through this overview rather than read directly.
  - Against the cold gas campaigns reported here, the common criteria including Schmucker's under-predict the separation location. Hot gas data differ less but the gap grows with wall Mach number at separation.
  - Hot gas separation carries large wall pressure variance from total pressure fluctuation. Injecting a cooling film damps that interaction and causes premature separation.
  - The criterion gives a mean position only. The separation point fluctuates in time and is more accurately a region.

## Passive Flow-Separation Control in a Dual-Bell Rocket Nozzle

- **URL:** https://arxiv.org/pdf/2005.00037
- **Accessed:** 2026-10-03
- **Relevance:** Retrieved for the distinction between the two separation patterns, which decides whether a single separation criterion is enough for a given contour.
- **Key findings:**
  - Free shock separation leaves the separated flow detached, with wall pressure tending to ambient downstream of the separation point. Restricted shock separation reattaches.
  - Truncated ideal contour and conical nozzles display free shock separation only. Restricted shock separation is a thrust-optimized contour phenomenon.
  - In free shock separation the compression waves coalesce into a conical separation shock, which reflects on the axis through a Mach disk and a second oblique leg.
  - Side loads from asymmetric separation are the structural concern, following R. Schmucker, "Flow process in overexpanded chemical rocket nozzles, part 2: side loads due to asymmetric separation".
