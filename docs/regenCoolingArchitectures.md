# Regenerative Cooling Architectures

This document covers the cooling circuits a NOVA jacket can be built from: what reference practice says about each, how NOVA solves each, where each is viable, and the example engines that exercise them. It is about circuit topology: how many passes the coolant makes, which way it runs relative to the gas, how many channels carry it at each station, whether the extension has a circuit of its own, and where the propellant that does not enter the jacket goes. The cross-section families and the station thermal model are in [NozzleCooling.md](NozzleCooling.md). Sources are in [references_regenCoolingTopologies_2026-10-02.md](references_regenCoolingTopologies_2026-10-02.md) and [references_extensionCooling_2026-11-03.md](references_extensionCooling_2026-11-03.md).

---

## Nomenclature

| Symbol | Meaning | Units |
|---|---|---|
| $N$ | number of channels at a station | -- |
| $N_{down}$, $N_{up}$ | channels in the down and up families of a multi-pass jacket | -- |
| $p$ | circumferential pitch, $2\pi r/N$ | m |
| $t_{infill}$ | rib thickness between channels | m |
| $\dot m_c$ | coolant mass flow through the jacket | kg/s |
| $\dot m_f$ | engine fuel mass flow | kg/s |
| $T_{hw}$ | hot-gas-side wall temperature | K |
| $T_b$ | coolant bulk temperature | K |
| $\Delta p_c$ | coolant pressure drop over the jacket | Pa |
| $G$ | rib conductance between neighboring channels of two passes | W/(m K) |
| $\beta$ | split blend, 0 before a channel split and 1 after it | -- |
| $\varepsilon$ | local area ratio | -- |

---

## The architectures

| Key | Name | Circuit | Viable where | Heritage |
|---|---|---|---|---|
| `coolantCircuit` `singlePass` | A. Single pass | In at the jacket's aft end, up every channel to the injector. With the jacket to the exit, the inlet manifold sits at the exit | Small chambers, and wherever the aft manifold's mass and size are acceptable | SSME nozzle tubes, fed at the exit; NERVA |
| `coolantCircuit` `oneAndHalfPass` | B. One and a half pass | In at a ring manifold at `coolantInletAreaRatio`, down one family of alternating channels to a turnaround ring at the aft end, up the other to the injector; forward of the manifold the up family runs alone | Hydrogen, which must be warmed before it reaches the throat; upper stages | J-2 (180 tubes down, 360 up), RL10 |
| `coolantCircuit` `twoPass` | C. Two pass | In at the injector end, down one family to the turnaround ring, up the other | Large tube-wall boosters, which keep both manifolds forward of the gimbal | F-1 (alternating tubes, 70 percent of the fuel) |
| `extensionCircuit` on | D. Extension circuit | A second circuit from the joint to `extensionCircuitEndAreaRatio`, in parallel with the chamber's: one pass coflow or counterflow, or two passes; its outlet returned to the feed, dumped as a film, or dumped overboard | First stages and long bells where the throat must see cold coolant | Vulcain 2 (upper nozzle dump-cooled into a film), SSME (parallel nozzle circuit) |

D combines with any of A to C for the chamber. The extension films are independent of the circuit: a slot can carry turbine exhaust from a specified gas generator and turbine, the extension circuit's own outlet, or a named species, and every film over the extension stacks with the chamber film carried past the joint. Their heritage is the F-1 and J-2X turbine exhaust and the Vulcain 2's dumped hydrogen.

The shipped engine, `assets/NOVANozzle.json`, runs B to the exit. `assets/examples/` holds one engine for each of the others; [Example engines](#example-engines) lists them.

---

## What the jacket does

| Property | Behavior | Set by |
|---|---|---|
| Passes | One (A), or two in alternating families (B, C) that share the pitch where both run | ``coolantCircuit``, ``passChannelRatio``, ``coolantInletAreaRatio`` |
| Direction | Counterflow or coflow for a single pass; the up family of a multi-pass jacket is counterflow | ``jacketFlowDirection`` |
| Channel count | One count per family; a single pass may split each channel to two partway down the bell | ``nChannel``, ``channelSplitAreaRatio``, ``channelSplitLength`` |
| Channel size | Converged per station against ``maxWallTemperature`` on the metal, or read from a recorded profile | ``channelSizingMode`` |
| Coolant | One species, one inlet state, one mass flow per circuit | ``coolant``, ``coolantInitialTemperature``, ``coolantInitialPressure``, ``coolantMassFlow`` |
| Flow accounting | The jacket flow is given, or is the fraction of the propellant not bypassed to the injector; the jacket, the chamber film and a returned extension circuit are held to the chamber's flow of that propellant | ``coolantMassFlow``, ``coolantBypassFraction``, ``coolantClass`` |
| Limits | The wall limit on the metal behind any coating, a bulk coolant ceiling, and a ceiling on the coolant-side wall for a coking fuel | ``maxWallTemperature``, ``maxCoolantTemperature``, ``maxColdWallTemperature`` |
| Exit constraints | Optional floors on exit pressure and exit temperature | ``minCoolantExitPressure``, ``minCoolantExitTemperature`` |
| Extension | A radiation-cooled shell, a circuit of its own (D), and films from slots | ``makeRadiativeExtension``, ``extensionCircuit`` and its keys, ``extensionFilmSlots`` |

The station march carries specific enthalpy, not heat per channel, so the energy balance closes to the property backend's own inversion. A change in channel count, a stream split, a turnaround or a stream recombination is exact in specific enthalpy and would not be exact in a heat-per-channel formulation.

---

## Where the fixed channel count binds

A single count has to serve the whole radius range of the jacket, because the pitch grows with the wall radius while the count does not. How much that costs depends on where the jacket ends.

**Truncated at an area ratio of 3, as the single-pass reference is, one count is enough.** The wall runs from 50.5 mm at the throat to 90.0 mm at the barrel, a factor of 1.78, so the cold-wall pitch at 60 channels spans 5.4 to 9.5 mm. Every station can hold a channel within a factor of two of its neighbors.

**Carried over the full area ratio of 40 on a single pass, one count is not enough.** In the ``regenCircle`` regression case, which cools the whole contour, the converged channel radius runs from 2.363 mm at the throat to 16.601 mm at the aft end, a factor of 7.0. The aft channels are 33 mm across. Most stations are decided by a geometric bound rather than the 800 K wall limit, and the pressure drop over that jacket is 170 kPa against a 12.0 MPa inlet, so the aft stations are buying almost nothing with their size.

Reference practice answers this with a count that changes along the nozzle. The F-1 doubles its tube count from 178 to 356 at an area ratio of 3, and SP-8087 gives bifurcation joints as the recommended practice for holding coolant velocity as the diameter grows, operational on Titan II Stage I and the F-1. NOVA offers it two ways: a single pass splits each channel to two (`channelSplitAreaRatio`), and B doubles the count aft of its inlet manifold by adding the down family. The shipped engine runs 60 up channels at the throat and 120 channels aft of an area ratio of three, and its aft channels are 16 mm across.

---

## The option space

### Flow direction

**Counterflow is the default for the chamber and the nozzle; coflow is used on nozzle extensions.** The LUMEN expander-bleed engine runs counterflow over the chamber and the nozzle and coflow over the nozzle extension, so direction is a per-section choice rather than a global one. The argument for counterflow is that the coolant arrives coldest where the flux is highest and the outlet manifold ends up near the injector it feeds. The argument for coflow is that a ruptured channel leaks coolant into the gas upstream of the wall it then protects, and that the manifold ends up where the feed line already is.

In NOVA direction is a choice of which end carries the inlet state, not a new solver. The march runs in an explicit station order, and the two volute interfaces are mirror images of each other, so a coflow jacket swaps the volute roles and marches the same stations the other way.

### Jacket flow fraction

**Production engines send a controlled fraction of the propellant around the jacket, not through it.** The F-1 passes 70 percent of the fuel through the chamber tubes and sends 30 percent straight to the injector through an orificed plug. The SSME splits hydrogen three ways: 19 percent up the chamber channels, 27.5 percent up the nozzle tubes and 48.5 percent around the nozzle through the chamber coolant valve, which is one of the five valves that control the engine.

This is the knob that makes the sizing problem well posed. Minimizing pressure drop subject to a wall temperature limit, at a fixed coolant flow, is under-constrained in channel count: the total flow area scales as $1/N$, so the drop falls monotonically as channels are removed and the optimum runs to the fewest channels the throat allows. Treating the jacket flow as a fraction of the available propellant puts a cost on the other side of that trade. `coolantBypassFraction` sets it, and the flow accounting refuses a jacket, film and returned extension circuit that together ask for more of a propellant than the chamber burns.

### Axial channel count

**Changing the count along the nozzle is both heritage practice and current practice, and it is the highest-value option.** Wadel's seven-design comparison found bifurcated channels gave the largest overall benefit of any configuration tried: 20 percent off the wall temperature for a 9 percent pressure drop increase, and after optimization 18 percent off the wall temperature with the pressure drop 4 percent lower than the baseline. Gradl and Protz report a subscale channel wall nozzle in Inconel 625, built by blown powder directed energy deposition and hot-fire tested, that "used a bifurcated channel design as the diameter increased".

Three shapes are distinguished in the literature: continuous channels change width smoothly, bifurcated channels split into two and merge back, stepped channels change width abruptly. Wadel measured the penalty of pretending the split is ideal: milling leaves a transition section where the flow area is larger than either side, heat transfer falls there, and the wall temperature rises locally. NOVA draws the transition rather than stepping across it. The section through the fork is the union of two circles parting on a cosine blend, so the larger flow area and the dip in heat transfer emerge from the march instead of being declared.

Two findings bound the enthusiasm. High aspect ratio channels over the entire chamber gave no significant wall temperature benefit over the throat region alone while significantly increasing the pressure drop, and 200 channels over the entire length improved the wall temperature profile at a high pressure drop penalty. More channels everywhere is not the answer; more channels where the pitch has grown is.

### Independent circuits and a second fluid

**Parallel circuits are flight practice, and a second fluid has a demonstrated case.** The SSME chamber and nozzle circuits are in parallel, not in series: each takes its own fraction of the hydrogen from the same discharge, and the chamber circuit's exit feeds a turbine. NOVA's extension circuit (D) is that structure: a second circuit with its own span, coolant, flow, inlet state, channel count and direction, solved by the chamber's own sizing march.

The second-fluid case is strongest for LOX/hydrocarbon boosters, where RP-1 runs out of cooling capacity. Oxygen cooling has been demonstrated to a chamber pressure of 13.8 MPa, and the deliberate crack-simulation tests concluded that LOX can be used safely as a coolant even where cracks develop in the wall upstream of the throat. The same work records an unexplained throat melting that was not in line with the simulated cracks, so the conclusion is about the cracks and not a clean bill of health for the configuration.

A hydrocarbon coolant is also what makes a ceiling on the coolant-side wall necessary rather than optional. RP-1 cokes above a wall temperature of 700 to 756 K, which is below the 800 K that a copper wall will tolerate, so for a hydrocarbon circuit the binding limit is often the coolant's and not the wall's. `maxColdWallTemperature` adds that limit to the sizing search, which shrinks the channel until the coolant-side wall sits at its ceiling where that binds first.

### Multiple passes

**Two passes is what large production engines do.** SP-8087 states that all of the large thrust production units use multi-pass tubular wall construction, with NERVA the single-pass exception for reasons specific to nuclear heating. It gives three configurations: one pass forward from the expansion section; one and a half passes, introduced in the expansion section, down and then up to the injector, used where the coolant must be heated before it is effective, as liquid hydrogen is in the RL10 and the J-2; and two passes, down from the injector and back up through alternating passages. It recommends one pass for smaller chambers only, on the grounds that a single pass needs larger passages at the high-flux stations and a large manifold at high expansion ratio, and that aft mass aggravates gimballing and lowers the engine's natural frequency. More than two passes it rules out on pressure drop and manifolding.

The march is not the hard part of a second pass; it is the second march, seeded by the first pass's exit state less the turnaround's loss. The wall model is. Alternating passages mean each channel's neighbors carry coolant the other way at a different temperature, so heat crosses the rib between them, and each pass's march depends on the other's coolant along the whole wall. NOVA carries a rib conductance between the two families and solves the two marches in turn until neither moves.

### Dump cooling and the inverted objective

**Dump cooling changes the objective function, not the geometry.** Pavli and co-authors state the contrast directly: a dump-cooled engine is designed to raise the coolant to the highest temperature the materials allow using the minimum flow possible, "unlike the design of a more conventional regeneratively cooled engine where the coolant flow is fixed and the pressure drop in the coolant jacket is minimized." Their 500 lbf engine found a minimum satisfactory coolant flow of 6.9 percent of the total propellant flow with an aluminum oxide coating and 7.5 percent without, and they held the metal temperature nearly constant at the material limit along the chamber, which is the same per-station rule a wall-temperature-targeted sizing solve already implements.

NOVA dumps an extension circuit's coolant as a film (`extensionCircuitOutlet` `film`) or overboard (`overboard`), and counts it as flow beside the chamber in the engine's specific impulse, with the film's thrust returned. The objective is not inverted: the circuit is sized at the flow it is given, and the minimum flow that holds the wall is found by running it at several.

The expander cycle imposes the same inversion from the other direction. LUMEN's third design goal is enough coolant enthalpy rise to drive the turbopumps, which opposes minimum wall temperature, and that conflict is why expander engines carry long cylindrical chambers.

### Transpiration cooling

**Out of scope.** SP-8087's verdict after its survey is that "many design, fabrication, and operational areas must be resolved before transpiration cooling can be considered operational", and lists hot spots in apparently well-cooled zones, pore properties that change with time, and penetration depth that grows under throttling. NOVA's film cooling covers the cases a conceptual tool needs from mass addition at the wall.

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

## Implementation

### Flow accounting and limits

`flowAccounting.py` splits the engine's flow into fuel and oxidizer, takes the jacket's share as `coolantMassFlow` or as what `coolantBypassFraction` leaves, and holds the jacket, the chamber film and a returned extension circuit to the chamber's flow of the propellant `coolantClass` names. Dumped circuits, extension films and turbine exhaust are extra draws beside the chamber, summed into the engine total the engine specific impulse is taken on. `maxCoolantTemperature` is checked at every station; `maxColdWallTemperature` enters the sizing search.

### Flow direction

`jacketFlowDirection` `coflow` takes the coolant in at the injector end and runs it aft. The march order is explicit (`coolantMarchOrder`), the channel centerline offset follows the march, and the volute roles swap ends. Verified by reflection: on a uniform barrel under a uniform gas state the coflow solution is the counterflow one mirrored about the midpoint, to 6.6e-15 relative (validation/coolingCircuits/phase1).

### Channel split

`channelSplitAreaRatio` forks each circular channel into two where the diverging wall reaches that area ratio, over `channelSplitLength` parent diameters (default 4). The daughters' centers part on a cosine blend $\beta$ to a separation $d = \beta\pi R/N$; the section is the union of two circles, with its area and perimeter in closed form; the march stays one parent channel wide through the split, so mass and enthalpy are continuous across it. In three dimensions each daughter is the parent's centerline turned by $\pm\beta\pi/(2N)$ about the axis and is exported as its own body. Rectangular and helical channels are refused a split, and so is a multi-pass jacket, which doubles its count by its down family instead (validation/coolingCircuits/phase3).

### Two passes (B and C)

`coolantCircuit` `oneAndHalfPass` or `twoPass` builds two families of circular channels alternating around the circumference, `nChannel` up channels and `passChannelRatio` times as many down (1, or 0.5 for the J-2's one down to two up). Where both run, every channel of both shares the pitch, $2\pi R/(N_{down} + N_{up})$. Each family is marched by the single-pass sizing march in the direction its coolant runs, with its own flow per channel. The down family's outlet turns in a torus at the aft end, sized so the coolant turns at half the channel velocity, losing one velocity head of the down channel and half of the up channel's, with its enthalpy kept. Neighbors of the two families exchange heat through the rib,

$$
G = {1 \over {1 \over h_1 a_1} + {t \over k \bar{a}} + {1 \over h_2 a_2}}
$$

with each channel's face its half perimeter toward that neighbor, and the two marches are solved in turn, each beside the other's last profile at the middle of each station, until neither moves by more than 0.05 K, at most 30 passes. A multi-pass jacket is counterflow in its up family, takes its coolant in through a ring manifold rather than an inlet scroll, and is refused a channel split (validation/coolingCircuits/phase4).

### Extension circuit (D)

`extensionCircuit` on runs a second circuit from the joint to `extensionCircuitEndAreaRatio` with its own coolant, flow, inlet state, channel count, passes (1 or 2) and direction. It is the chamber's sizing march on the extension's stations, in the thermal mode against the same wall limit, with the real throat passed explicitly. Its outlet is returned to the feed (held with the chamber jacket to the chamber's flow of that propellant), laid as a film from a slot at the circuit's outlet with the circuit's outlet state, or dumped overboard. Beyond the circuit the shell is radiation cooled under whatever films run over it, and the friction march sees the circuit's wall over its span and the shell's beyond (validation/coolingCircuits/phase5).

### Extension films and turbine exhaust

`turbineExhaust.py` takes a specified gas generator (mixture ratio, pressure, flow) and turbine (pressure ratio, efficiency): no power balance with the pumps is carried. The generator is burned in CEA at equilibrium and expanded frozen through the turbine, $h_{te} = h_{gg} - \eta_t (h_{gg} - h_{is})$; condensed carbon in a fuel-rich generator is reported, and a frozen expansion CEA returns at the throat state is refused. `extensionFilm.py` joins the jacket and extension stations into one wall, marches every film from its own slot (the chamber film carried past the joint, turbine exhaust, the extension circuit's outlet, a named species), and stacks them by Sellers superposition,

$$
T_{aw,n} = T_{aw,n-1} - \eta_n \left(T_{aw,n-1} - T_{c,n}\right)
$$

so each film sees the wall the films upstream have made. Both closures are solved and reported, each with its band flag, and a slot whose flow would leave it at Mach 1 or more at the wall pressure is refused with the height it needs. A film's thrust is its unmixed expansion from the slot to the exit pressure, with the fully mixed value reported beside it (validation/coolingCircuits/phase2).

---

## Example engines

Each is a complete configuration in `src/NOVA/assets/examples/`, loadable from the GUI's Design tab. Each borrows the architecture of the engine it is named after, not its published dimensions or flows, and its `_comment` says where it departs. [featureShowcase/buildCoolingShowcase.py](../featureShowcase/buildCoolingShowcase.py) solves all of them and draws each one.

| File | Engine | Chamber circuit | Extension | Result |
|---|---|---|---|---|
| `NOVANozzle.json` (shipped) | 100 kN LOX/LH2 upper stage, 6.9 MPa, $\varepsilon$ 40 | B, 60 down and 60 up GRCop-42 channels, inlet at $\varepsilon$ 3, jacket to the exit | none | 0.42 MPa over the circuit, hydrogen out at 257 K, wall at its 800 K limit |
| `novaSinglePass.json` | The same engine | A, 60 channels to $\varepsilon$ 3 | C103 shell beyond | The shell exceeds its limit: Bartz at 6.9 MPa puts a columbium shell over it at any area ratio |
| `methaloxBooster.json` | 500 kN LOX/LCH4 first stage, 10 MPa, $\varepsilon$ 25 | A, 120 channels splitting to 240 at $\varepsilon$ 2 | D: two passes to $\varepsilon$ 12, returned; turbine exhaust film over a C103 shell | Shell 1340 K, 333 K inside its limit; engine 321.8 s at its design back pressure |
| `keroloxF1.json` | 6.77 MN LOX/RP-1, 7 MPa, $\varepsilon$ 16 | C, 90 down and 90 up Inconel 718 channels to $\varepsilon$ 10, 30 percent bypass, 560 K coking ceiling, soot layer | Turbine exhaust film over a C103 shell | 1.48 MPa over both passes, metal 725 K with the coking ceiling binding; shell 1240 K |
| `hydroloxVulcain.json` | 1.2 MN LOX/LH2, 11.5 MPa, $\varepsilon$ 58 | A, 180 channels to $\varepsilon$ 4 | D: one pass coflow to $\varepsilon$ 12, dumped as a film; turbine exhaust film below it; C103 shell | Shell 865 K, 808 K inside its limit; engine 429.3 s |
| `ssmeNozzle.json` | 1.86 MN LOX/LH2, 20.6 MPa, $\varepsilon$ 69 | A, 390 rectangular NARloy-Z channels to $\varepsilon$ 5 | D: one pass counterflow from $\varepsilon$ 68, 873 channels, returned | Chamber circuit 4.5 MPa; nozzle circuit 50 to 263 K for 0.54 MPa |

---

## Validation

**Verified against identities and closed forms.** The flow accounting is arithmetic, held to its identities in `tests/testFlowAccounting.py`. A coflow solve reproduces a reflected counterflow solve on a uniform barrel to 6.6e-15 relative. Through a split, mass and enthalpy are continuous, the summed hot-wall sector areas equal $2\pi r\,ds_m$, and the union area matches a numerical polygon area (`tests/testChannelSplit.py`). For two passes, with the rib conductance off the passes are two independent marches; the heat the two coolants take on together matches what the wall gives them to 0.2 percent; the rib heat one pass gains the other loses; the turnaround's loss is charged once and keeps the enthalpy; and the flow splits between the families in the ratio asked for (`tests/testCoolantCircuit.py`). A one-pass extension circuit reproduces a standalone single-pass march on the same span bit for bit (`tests/testExtensionCircuit.py`). With no film the extension drive is the recovery temperature to the bit, and a turbine at an efficiency of one reproduces CEA's frozen expansion (`tests/testExtensionFilm.py`, `tests/testTurbineExhaust.py`).

**Checked against an independent solve.** The rib conductance runs 2 to 40 percent above a two-dimensional finite-difference conduction solve of the web between two circular channels, the most for large channels at high coolant coefficients, where conduction through the web limits the exchange (validation/coolingCircuits/phase4).

**Compared against published data, and off.** The F-1's gas generator at a mixture ratio of 0.416 and 6.65 MPa reads 1252 K at equilibrium against the 1063 K published, with 35 percent of its mass as graphite. A real fuel-rich generator does not reach equilibrium, so the exhaust temperature, and the film it lays, is overstated for hydrocarbon generators.

**Not validated, and no reference available here.** No measurement of a multi-pass jacket's wall or coolant temperatures, of a split channel's heat transfer, or of a film over a radiation-cooled extension is available to this tool; the DLR supersonic hydrogen film data that would close the last of these is not accessible. The comparison against Wadel's bifurcated designs has not been made: their baseline chamber, heat flux profile and coolant-side correlation all differ from NOVA's, so it would be a comparison of trends, not a validation of numbers. Film slots on the example engines run at 0.06 to 0.15 of the core velocity, well outside the 0.9 to 1.15 band SP-8124's entrainment closure was written for; every run reports Hatch-Papell beside it.

**Inherited, unchanged.** Every circuit inherits the gas-side and coolant-side validation status recorded in ``gasSideHeatTransfer.py`` and ``regenThermal.py``. None of them improves it, and a topology that moves the wall temperature by 20 percent sits on a coolant-side correlation that is a sensitivity-bounded comparison rather than a validation. On a hydrocarbon coolant the coolant side is further out of its fitted range: Dipprey and Sabersky's roughness correlation was fitted at Prandtl numbers of 1.2 to 5.94, and at a liquid hydrocarbon's 20 to 30 it is held to the full-credit bound.
