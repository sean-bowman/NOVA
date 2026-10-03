# Regenerative Cooling Architectures

This document covers the cooling circuit options a regeneratively cooled jacket can be built from, what reference practice says about each, what each would change in NOVA, and the order they are worth adding in. It is about circuit topology: how many passes the coolant makes, which way it runs relative to the gas, how many channels carry it at each station, how many fluids are involved, and where the propellant that does not enter the jacket goes. The cross-section families and the station thermal model are in [NozzleCooling.md](NozzleCooling.md). Sources are in [references_regenCoolingTopologies_2026-10-02.md](references_regenCoolingTopologies_2026-10-02.md).

---

## Nomenclature

| Symbol | Meaning | Units |
|---|---|---|
| $N$ | number of channels at a station | -- |
| $p$ | circumferential pitch, $2\pi r/N$ | m |
| $t_{infill}$ | rib thickness between channels | m |
| $\dot m_c$ | coolant mass flow through the jacket | kg/s |
| $\dot m_f$ | engine fuel mass flow | kg/s |
| $T_{hw}$ | hot-gas-side wall temperature | K |
| $T_b$ | coolant bulk temperature | K |
| $\Delta p_c$ | coolant pressure drop over the jacket | Pa |
| $\varepsilon$ | local area ratio | -- |

---

## What the jacket is today

One circuit, one pass, counterflow, one channel count, one fluid, and every kilogram of the nominated coolant through the channels.

| Property | Current behavior | Set by |
|---|---|---|
| Passes | One, over the whole regen section | Fixed in the build |
| Direction | Counterflow: inlet at the aft truncation, outlet at the injector face | Fixed in the build |
| Channel count | One integer for the whole jacket | ``nChannel`` |
| Channel size | Converged per station against ``maxWallTemperature``, or read from a recorded profile | ``channelSizingMode`` |
| Coolant | One species, one inlet state, one mass flow | ``coolant``, ``coolantInitialTemperature``, ``coolantInitialPressure``, ``coolantMassFlow`` |
| Flow accounting | ``coolantMassFlow`` is an independent input, unconnected to the engine propellant flow | ``coolantMassFlow`` |
| Exit constraints | Optional floors on exit pressure and exit temperature | ``minCoolantExitPressure``, ``minCoolantExitTemperature`` |

``coolantClass`` is read from the configuration and never used. It becomes meaningful only when more than one circuit exists, where it says which propellant stream a circuit draws from and returns to.

The station march carries specific enthalpy, not heat per channel, so the energy balance closes to the property backend's own inversion. That choice matters for everything below: a change in channel count, a stream split, or a stream recombination is exact in specific enthalpy and would not be exact in a heat-per-channel formulation.

---

## Where the fixed channel count binds

A single count has to serve the whole radius range of the jacket, because the pitch grows with the wall radius while the count does not. How much that costs depends entirely on where the jacket ends.

**Truncated at an area ratio of 3, the reference configuration, one count is enough.** The wall runs from 50.3 mm at the throat to 90.0 mm at the barrel, a factor of 1.79, so the cold-wall pitch at 60 channels spans 5.4 to 9.5 mm. Every station can hold a channel within a factor of two of its neighbors.

**Carried over the full area ratio of 40, one count is not enough.** In the ``regenCircle`` regression case, which cools the whole contour, the converged channel radius runs from 2.287 mm at the throat to 16.545 mm at the aft end, a factor of 7.2. The aft channels are 33 mm across. Of the 60 stations, 15 are decided by the 800 K wall limit and 45 are decided by a geometric bound, which leaves up to 318 K of unused thermal margin on the stations that are not thermally limited. The pressure drop over that jacket is 193 kPa against a 12.0 MPa inlet, so the aft stations are buying almost nothing with their size.

The reference answer to exactly this is a channel count that changes along the nozzle. The F-1 doubles its tube count from 178 to 356 at an area ratio of 3, which is the same station where the reference configuration stops cooling altogether. SP-8087 gives bifurcation joints as the recommended practice for maintaining reasonable coolant velocities as the diameter grows, and names them operational on Titan II Stage I and the F-1.

---

## The option space

### Flow direction

**Counterflow is the default for the chamber and the nozzle; coflow is used on nozzle extensions.** The LUMEN expander-bleed engine runs counterflow over the chamber and the nozzle and coflow over the nozzle extension, so direction is a per-section choice rather than a global one. The argument for counterflow is that the coolant arrives coldest where the flux is highest and the outlet manifold ends up near the injector it feeds. The argument for coflow is that a ruptured channel leaks coolant into the gas upstream of the wall it then protects, and that the manifold ends up where the feed line already is.

In NOVA the station march is indexed from the coolant inlet with the geometry arrays flipped at entry and flipped back on return, and the two volute interfaces are already built as mirror images of each other. Direction is therefore a choice of which end carries the inlet state, not a new solver.

### Jacket flow fraction

**Production engines send a controlled fraction of the propellant around the jacket, not through it.** The F-1 passes 70 percent of the fuel through the chamber tubes and sends 30 percent straight to the injector through an orificed plug. The SSME splits hydrogen three ways: 19 percent up the chamber channels, 27.5 percent up the nozzle tubes and 48.5 percent around the nozzle through the chamber coolant valve, which is one of the five valves that control the engine.

This is the knob that makes the sizing problem well posed. Minimizing pressure drop subject to a wall temperature limit, at a fixed coolant flow, is under-constrained in channel count: the total flow area scales as $1/N$, so the drop falls monotonically as channels are removed and the optimum runs to the fewest channels the throat allows. Treating the jacket flow as a fraction of the available propellant puts a cost on the other side of that trade.

It also exposes an accounting gap. The reference configuration draws 3.4 kg/s through the jacket and 0.3 kg/s through the film, against a fuel flow of 3.610 kg/s at 23.466 kg/s total and a mixture ratio of 5.5. The jacket and the film together ask for 2.5 percent more hydrogen than the engine burns, and nothing refuses it.

### Axial channel count

**Changing the count along the nozzle is both heritage practice and current practice, and it is the highest-value option.** Wadel's seven-design comparison found bifurcated channels gave the largest overall benefit of any configuration tried: 20 percent off the wall temperature for a 9 percent pressure drop increase, and after optimization 18 percent off the wall temperature with the pressure drop 4 percent lower than the baseline. Gradl and Protz report a subscale channel wall nozzle in Inconel 625, built by blown powder directed energy deposition and hot-fire tested, that "used a bifurcated channel design as the diameter increased".

Three shapes are distinguished in the literature, and the distinction is worth keeping: continuous channels change width smoothly, bifurcated channels split into two and merge back, stepped channels change width abruptly. A zoned channel count in a tool like NOVA is the stepped case unless the transition is drawn explicitly.

Wadel also measured the penalty of pretending the split is ideal. Milling leaves a transition section where the flow area is larger than either side, heat transfer falls there, and the wall temperature rises locally. Any implementation that does not resolve the transition is optimistic at the transition station and must say so.

Two findings bound the enthusiasm. High aspect ratio channels over the entire chamber gave no significant wall temperature benefit over the throat region alone while significantly increasing the pressure drop, and 200 channels over the entire length improved the wall temperature profile at a high pressure drop penalty. More channels everywhere is not the answer; more channels where the pitch has grown is.

### Independent circuits and a second fluid

**Parallel circuits are flight practice, and a second fluid has a demonstrated case.** The SSME chamber and nozzle circuits are in parallel, not in series: each takes its own fraction of the hydrogen from the same discharge, and the chamber circuit's exit feeds a turbine. Treating the jacket as a list of circuits, each with its own axial span, coolant, flow, inlet state and direction, covers that case and several others with one structure.

The second-fluid case is strongest for LOX/hydrocarbon boosters, where RP-1 runs out of cooling capacity. Oxygen cooling has been demonstrated to a chamber pressure of 13.8 MPa, and the deliberate crack-simulation tests concluded that LOX can be used safely as a coolant even where cracks develop in the wall upstream of the throat. The same work records an unexplained throat melting that was not in line with the simulated cracks, so the conclusion is about the cracks and not a clean bill of health for the configuration.

A second fluid is also what makes a coolant temperature ceiling necessary rather than optional. RP-1 cokes above a wall temperature of 700 to 756 K, which is below the 800 K that a copper wall will tolerate, so for a hydrocarbon circuit the binding limit is the coolant's and not the wall's.

### Multiple passes

**Two passes is what large production engines do, and it is the most expensive option to model honestly.** SP-8087 states that all of the large thrust production units use multi-pass tubular wall construction, with NERVA the single-pass exception for reasons specific to nuclear heating. It gives three configurations: one pass forward from the expansion section; one and a half passes, introduced in the expansion section, down and then up to the injector, used where the coolant must be heated before it is effective, as liquid hydrogen is in the RL10 and the J-2; and two passes, down from the injector and back up through alternating passages. It recommends one pass for smaller chambers only, on the grounds that a single pass needs larger passages at the high-flux stations and a large manifold at high expansion ratio, and that aft mass aggravates gimballing and lowers the engine's natural frequency. More than two passes it rules out on pressure drop and manifolding.

What a second pass costs NOVA is not the march, which is a second march seeded by the first pass's exit state. It is the geometry and the wall model. Alternating passages mean each channel's neighbors carry coolant in the opposite direction at a different temperature, which the current rib model cannot represent: the fin is cooled on both faces by the same coolant state. It also needs a turnaround manifold at the far end, and the channel count per pass halves, which changes the fit bound at every station.

### Dump cooling and the inverted objective

**Dump cooling changes the objective function, not the geometry.** Pavli and co-authors state the contrast directly: a dump-cooled engine is designed to raise the coolant to the highest temperature the materials allow using the minimum flow possible, "unlike the design of a more conventional regeneratively cooled engine where the coolant flow is fixed and the pressure drop in the coolant jacket is minimized." Their 500 lbf engine found a minimum satisfactory coolant flow of 6.9 percent of the total propellant flow with an aluminum oxide coating and 7.5 percent without, and they held the metal temperature nearly constant at the material limit along the chamber, which is the same per-station rule a wall-temperature-targeted sizing solve already implements.

Two consequences are worth modeling. The jacket pressure drop goes in parallel with the injector drop rather than in series, so the exit pressure floor is set by the dump nozzle and not by the injector feed, which lowers the required pump or tank pressure. And the dumped coolant is expanded through its own nozzle, so it returns thrust: at a high enough exit temperature its specific impulse approaches that of the main combustion process.

The expander cycle imposes the same inversion from the other direction. LUMEN's third design goal is enough coolant enthalpy rise to drive the turbopumps, which opposes minimum wall temperature, and that conflict is why expander engines carry long cylindrical chambers.

### Transpiration cooling

**Out of scope.** SP-8087's verdict after its survey is that "many design, fabrication, and operational areas must be resolved before transpiration cooling can be considered operational", and lists hot spots in apparently well-cooled zones, pore properties that change with time, and penetration depth that grows under throttling. NOVA's film cooling module covers the cases a conceptual tool needs from mass addition at the wall.

---

## What production engines do

| Engine | Passes | Direction | Count change | Jacket fraction | Coolant |
|---|---|---|---|---|---|
| F-1 | Two, alternating tubes | Down then up | 178 to 356 at $\varepsilon$ = 3 | 70 percent, 30 percent to the injector | RP-1 |
| RL10, J-2 | One and a half | Partial pass below the throat, then up | Tube bundle | Full | LH2 |
| SSME chamber | One | Up, counterflow | 430 channels, constant | 19 percent of fuel | LH2 |
| SSME nozzle | One | Up, counterflow | 1080 tubes | 27.5 percent of fuel, 48.5 percent bypassed | LH2 |
| Agena aft cone | Two | Inlet at the forward end of the cone, 25 degree cant | Drilled passages | Full | Fuel |
| NERVA | One | Forward | U-section tubes | Full | LH2 |
| LUMEN | One | Counterflow chamber and nozzle, coflow extension | 86 channels or fewer, constant | Variable by design | CH4 |

---

## Roadmap

Ordered by value divided by cost, not by the order the references were written. Each stage is independently useful and leaves the shipped configuration's results unchanged when its keys are unset.

### Stage 1: flow accounting

Close the propellant books before adding topology that depends on them.

- ``coolantBypassFraction``, the fraction of the drawn propellant that goes around the jacket to the injector. The jacket flow becomes the remainder, and the mixed injector-side temperature is reported.
- A closure check: the jacket plus the film plus the bypass may not exceed the engine's flow of the nominated propellant class, refused by name and number.
- ``maxCoolantTemperature``, a bulk temperature ceiling checked at every station, defaulting to unset. The coking limit is the reason it exists.

Touches ``config.py``, ``channelSizing.py``, ``regenThermal.py``, ``errors.py``, the GUI schema and the JSON. No geometry. Three new state attributes, so one baseline re-record.

### Stage 2: flow direction

- ``jacketFlowDirection``, one of ``counterflow`` or ``coflow``, defaulting to ``counterflow``.
- The inlet state attaches to the injector-face interface instead of the aft one; the station march reverses; the volute roles swap.

Touches ``regenChannels.py`` and ``channelSizing.py``. The interfaces are already mirror images and the volute module already separates inlet from outlet sizing, so the work is in the station ordering and in which interface is named which. Closed-form check available: a coflow run on a constant-radius barrel with a uniform heat flux must reproduce the counterflow run's wall temperature profile reflected about the barrel midpoint.

### Stage 3: axial channel count

- A channel count profile keyed the same way ``manualChannelProfile`` is keyed, read as a piecewise-constant integer against the area ratio or the jacket fraction.
- Per-station channel count through the sizing march, the fit bound, the section properties and the hot-wall sector area. ``rectangularWidth``, ``helicalSpacing`` and ``hotWallSectorArea`` already broadcast over the station arrays, and the specific-enthalpy march already makes a count change exact, so the physics work is the per-station mass flow and the fit bound.
- Geometry built one channel body per zone over its own station span, with the transition station declared unresolved rather than drawn. Wadel's measurement of the transition's flow area penalty is the reason that has to be a stated limitation and not a footnote.

Touches ``channelSizing.py``, ``channelSections.py``, ``channelGeometry.py``, ``regenChannels.py``, ``exports.py``, ``figures.py``. The largest stage, and the one the reference material supports most strongly.

### Stage 4: independent circuits

- A list of circuits, each with an axial span, a coolant, a mass flow, an inlet state, a direction and a channel count, replacing the single set of coolant keys while keeping them as the one-circuit spelling.
- ``coolantClass`` becomes load-bearing: it selects which propellant stream the closure check draws from.
- Dump cooling as a circuit property: the exit pressure floor comes from a dump nozzle rather than the injector, and the dumped flow carries an impulse credit.

Subsumes multi-fluid cooling, the SSME's parallel circuits, a hydrocarbon chamber with an oxygen-cooled nozzle, and a dump-cooled extension. Each circuit is an existing single-pass solve, so the new work is the bookkeeping and the volute pairs, not the physics.

### Stage 5: two passes

Deferred, with what it needs recorded rather than estimated:

- A turnaround interface at the far end, which is the mirror of a volute interface with the flare replaced by a return bend.
- Interleaved channels: the count per pass is half the count on the wall, which changes every fit bound.
- A rib model that accepts a different coolant state on each face. The current fin is cooled on both faces by one state, which is correct for a single pass and wrong for alternating passes.

The honest intermediate is a one-and-a-half pass, where the partial pass starts below the throat and the two passes do not share a rib over most of their length.

---

## Validation

What can be closed in closed form, what can be checked against hardware, and what cannot be either.

**Closed form, available now.** Flow accounting is arithmetic and is testable as such. A coflow solve is testable against a reflected counterflow solve on a uniform barrel. A channel count change is testable on three properties that must hold exactly: specific enthalpy continuous across the transition, pressure continuous across it, and the summed hot-wall sector areas on each side equal to $2\pi r\,ds_m$ at the same station.

**Against hardware, partially.** Wadel's bifurcated designs give a wall temperature reduction and a pressure drop change against a stated baseline, which is a comparison NOVA can attempt once a count profile exists, with the caveat that the baseline chamber, the heat flux profile and the RTE coolant-side correlation are all different from NOVA's. It would be a comparison of trends, not a validation of numbers, and it should be reported as such. The F-1 and SSME flow splits are design data, not measurements of anything NOVA computes.

**Not validated, and no reference available.** A stepped channel count with an unresolved transition is optimistic at the transition station by an amount Wadel measured on one geometry and that does not transfer. Two counter-flowing passes sharing a rib have no representation in the current wall model, which is why that stage is not attempted rather than attempted with a disclosure. Dump cooling's impulse credit depends on a dump nozzle NOVA does not size.

**Inherited, unchanged.** Every stage above inherits the gas-side and coolant-side validation status recorded in ``gasSideHeatTransfer.py`` and ``regenThermal.py``. None of them improves it, and a topology that moves the wall temperature by 20 percent sits on a coolant-side correlation that is a sensitivity-bounded comparison rather than a validation.
