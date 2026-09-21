
[Home](../../README.md) &gt; [Nozzle Cooling](./NozzleCooling.md)

# NOVA: Regeneratively Cooled Nozzle Design

This document describes the theory, code backend, process flow, and user interfacing of the propulsionDesign Nozzle module's regeneratively cooled nozzle design section.

- Nozzle
- Optimization for
- Variable
- Applications

## Nomenclature

- $A =$ area

Greek:

- $\gamma =$ ratio of specific heats

Subscripts:

- $differential =$ between two values

Superscripts/Overheads:

- dot ($\dot{a}$) = per time
- bar ($\bar{a}$) = non-dimensional
- star (${a}^*$) = ratio

# Regenerative Cooling Architecture Design

This section details the theory and implementation for the design of regenerative cooling architecture, and finishes with a worked regeneratively cooled nozzle design example.

Each section will contain information pertaining to the mathematical background as well as the process flow of the ideas presented, which will additionally be supplemented with imagery to hopefully make for a complete understanding of the underlying approach.

## Regenerative Cooling Background

One of the fundamental challenges when working with rocket hardware is designing around the extreme physics conditions that rocket components are subjected to. Combustion chambers can reach temperatures comparable to the surface of the sun, while cryogenic propellants can be kept at temperatures near absolute zero (the coldest anything in the universe could possibly be!). During operation, rocket nozzles that are directing the super-hot exhaust flow need to maintain their shape to continue to operate as designed, but the temperature of most exhaust flows far exceeds the melting temperatures of possible materials that nozzles could be made of.

*[Figure: Different Engines Firing]*

*Orbital Class Engines Firing*

Faced with a physics-based challenge, there are two primary approaches to the problem of nozzles eroding during operation.

### Ablative Nozzles

#### Let it melt!

The first approach is commonly referred to as "ablative" nozzle design, where the nozzle material is allowed to ablate but the rate of ablation is known and the motor/engine operation can be tailored to that ablation rate. This approach is often seen for small duration burn motors (such as missiles or small student rockets) or solid propellant applications where there is not a readily available cooling fluid.

The challenge with ablation is that the size and shape of the nozzle contour changes over time, which changes the fundamental properties of the nozzle (most notably the size of the nozzle throat, which controls the total mass flow rate and subsequent thrust production). Many ablative nozzle designs are only ablative near the nozzle throat where the highest heat transfer occurs, while the rest of the nozzle contour is made of some well-characterized high-temperature material such as a phenolic resin.

*[Figure: TRL Nozzle]*

*TRL ablative nozzle pre- and post-fire*

*[Figure: Thrust vs Time]*

*Thrust output decrease over burn duration*

### Active Cooling

#### Fighting the Sun

Allowing performance to vary with time can often be impractical for orbital applications if it is avoidable, making ablative nozzles disadvantageous for space launch vehicles or reusable applications. The alternative approach to nozzle design involves maintaining the nozzle contour shape throughout the entire burn duration (and for any number of conceivable burns), which requires some form of active cooling of (or heat transfer reduction to) the nozzle hot wall. This allows nozzles to maintain their designed performance throughout an entire long-duration burn of multiple minutes or be reused indefinitely.

*[Figure: Same Nozzle]*

*Same nozzles, same performance, different stage of mission*

But how can we keep something so hot from melting? In liquid bi-propellant and hybrid rocket engines, there is often a supply of cryogenic liquid that is being stored as propellant to feed the engines that can be utilized as a cooling fluid during operation. This has many advantages beyond the obvious one of maintaining nozzle geometry. The reason propellants are stored in their cryogenic liquid form is for volumetric efficiency, because carrying the equivalent mass of gaseous propellant would require huge high-pressure tanks and be very impractical. In their liquid form, common propellants can be hundreds of times more dense than their gaseous counterparts and therefore be storable in a much smaller volume. However, the propellant must be turned into a gas as some point before the combustion process, because only gaseous materials are capable of combusting. We're in need of a heat exchanger to expand the liquid into a gas before it reaches the combustion chamber, and there just happens to be a very convenient heat exchanger at the end of the engine directing the exhaust flow (the nozzle!).

*[Figure: Heat exchanger diagram]*

*Generic heat exchanger*

In liquid bi-propellant systems the common approach is to utilize the liquid fuel, as it often has a much higher heat capacity than the oxidizer that is also stored on-board. Heat capacity can be thought of as the amount of energy it takes to raise the temperature of a given fluid, so a higher heat capacity means that it takes more energy to raise the temperature of the fluid, or conversely that a cooling fluid can accept much more energy without raising its temperature that much. This is an advantage for fuels as coolants, because there is often a lot of nozzle and chamber wall that needs to be cooled and a limited amount of cooling fluid to work with, making this the more efficient choice.

*[Figure: RS25 Hot Fire]*

*The Space Shuttle RS-25 Hydrolox engines are cooled with liquid Hydrogen fuel!*

However, in hybrid engines the fuel material is a solid, leaving only cryogenic oxidizer as the lone choice for designers of active cooling systems for hybrid engines. This is not great news, as common oxidizers have a substantially lower heat capacity than common fuels.

*[Figure: Cp Comparison]*

*Liquid Methane has about twice the heat capacity of liquid oxygen*

Don't panic, though, because there are still things that can be done to successfully cool a nozzle using the oxidizer instead! We will touch more on this later, but with modern design and manufacturing techniques we can get creative with cooling geometry in new and exciting ways to unlock previously unattainable design solutions.

In general, a system that utilizes the available propellant to cool the nozzle walls *and* heats that propellant with energy from the engine operation to drive the engine cycle is called *regeneratively cooled*.

### What is *Regenerative* Cooling?

The term *regenerative* refers to the fact that energy from the exhaust flow is recaptured and used to heat the same propellant that will eventually be used in combustion to perpetuate the engine cycle. The propellant acts as a nozzle coolant during operation by being passed between the walls of the nozzle, which allows for the double use of the propellant both in combustion and as a cooling fluid.

*[Figure: Regenerative Cooling]*

*Example of regen cooling*

There are other forms of active cooling, such as *film cooling*, where a thin sheet of unburnt gaseous propellant (again, typically the fuel) is passed along the nozzle hot wall to create a boundary between the exhaust and the nozzle wall, which is famously the cooling method used on the nozzle extension of the F-1 engines that lift the Saturn-V!

*[Figure: Film Cooling]*

*Film cooling exhaust of F-1*

The dark band before the bright orange of the plume is the unburnt gas film leaving the nozzle, which eventually reacts with the oxygen in the air and burns where the plume turns all orange!

A hybrid engine has no gaseous fuel on hand, so a film on a hybrid nozzle means carrying a separate coolant for it, and most of what follows is about the regenerative jacket. NOVA does model a film where one exists: `filmCooling.py` lowers the temperature the wall is driven by over the length the film survives, rather than removing heat the way a jacket does. Switch it on with `filmCooling` and give it a coolant, a flow, a temperature, a slot position and a slot height. Two closures are available through `filmCoolingModel`. The Hatch and Papell correlation from NASA TN D-130 is the default and the only one that states its own accuracy, but it was fitted in a constant-area duct and cannot see acceleration or flow turning. The entrainment model of NASA SP-8124 Appendix A accounts for both, through an empirical multiplier read off a design chart, so it is calibrated rather than validated. On a hydrogen film the two disagree by hundreds of kelvin, which is a fair measure of how well film cooling is known at rocket conditions.

The third method is to remove the coolant entirely and let the wall radiate. Past some area ratio the flux has fallen far enough that an uncooled shell settles below its own temperature limit, and carrying a jacket further costs mass and pressure drop for nothing. `radiativeCooling.py` solves that balance along the extension beyond the jacket and reports the margin against the material limit, which is the only question worth asking about an uncooled shell. Switch it on with `makeRadiativeExtension`, and note that it needs a non-`none` `regenTruncationType`, because with none the jacket runs the whole contour and there is no extension to solve.

Both combine with a jacket rather than replacing it, which is why they are described here alongside it rather than as alternatives to it.

## Hybrid Supercritical Oxygen Expander Cycle

At the time of writing, the main engine cycle employed for orbital-class hybrid engines covered by this codebase is the Expander Cycle.

*[Figure: Expander Cycle]*

*Liquid Bi-Prop Expander Cycle Example*

The expander cycle operates on the premise that a single fluid (typically the fuel) can be *expanded* from its compressed liquid form to a more useable high-energy form (gas/supercritical fluid) to then drive a turbine which perpetuates the engine cycle. This is the general baseline premise of the expander cycle, however for a hybrid engine application there are some niche details that distinguish the design practices used here from traditional liquid bi-prop expander cycle practices.

*[Figure: Hybrid Expander Cycle]*

*Hybrid Expander Cycle*

The first and most obvious deviation from standard practices is the use of Oxygen as the working fluid in the cooling architecture. This is not entirely unheard of, however the aforementioned disadvantageous heat capacity make Oxygen a secondary choice for other designers. With a solid-fuel hybrid, however, there is no alternative and one must make due with what is available. The second is the system pressure. The orbital-class engines being modeled here operate at a relatively high chamber pressure (~15 MPa or ~2000 psi) which leads to an interesting distinction in the fluid physics of the engine fluid system. In order to make the most accurate predictive models and design tools, it is pertinent to model the fluids in the fluid system in the most physically accurate way, and when fluids exceed what is known as their *critical* state they behave differently than fluids at more familiar temperatures and pressures. To be more clear about what this means and why it matters, the following sections briefly go over the physics of supercritical fluids and how that distinction impacts the design of a rocket fluid system. The reference design used throughout this document (chamber pressure ~15 MPa, LOX coolant, HDPE solid fuel) is one specific reduction to practice of the methods described here.

### Aside: Supercritical Fluids

To be *painfully* clear about the distinction being made here, let's start with the simplest example. At standard temperatures and pressures, referring to a substance as a "fluid" encapsulates the concepts of both "liquids" and "gasses", which share the property that the individual particles that comprise them are able to flow and take the shape of their containers. Liquids are held together by stronger intermolecular forces which causes local fluid density to be high, whereas gasses consist of individual particles whose motion and internal energy state exceed any intermolecular forces, allowing particles to move about independently of one another leading to low local fluid density. At the boundary between these two states of matter there exists a clear delineation in fluid properties and crossing over this boundary causes the state of the fluid to vary dramatically. This is more colloquially known as "vaporization", or more distinctly "evaporation" when the process happens at the liquid surface boundary and "boiling" when the process takes place within the bulk liquid. Something very interesting happens, however, when you increase the pressure past a certain threshold known as the "critical pressure".

*[Figure: Oxygen Phase Diagram]*

*Oxygen Phase Diagram*

In the above phase diagram for Oxygen, the "critical point" denoted by the red star represents the physical state of the fluid where the distinction between liquid and gas loses practical meaning. This means that properties of the fluid will no longer change rapidly with increases of temperature or pressure, and instead changes in properties will be gradual and the magnitudes of the properties will be some average of the liquid and gas states. We can visualize this by plotting thermophysical properties (like density and viscosity) instead of fluid phase, to get an idea for how the properties vary with changes in temperature and pressure.

*[Figure: Oxygen Properties]*

*Oxygen Properties*

On the left we can see how Oxygen's density varies over the same temperature and pressure ranges from the phase diagram above. There is a steep drop off in density where the phase change from liquid to gas occurs, causing the density to drop from the high liquid value (~1000 [kg/m^3]) to the low gaseous value (~10 [kg/m^3]). However, at higher pressures, the drop off becomes more gradual until eventually there is no drop at all. Instead, the density varies smoothly as the temperature increases (I like to call this region the "density slide").

What this means for rocket engines is that propellant that begins the engine cycle journey as a liquid in the propellant tank does not phase change in the traditional sense at any point in the engine. Instead, we can avoid the rapid property changes and take advantage of the physics of supercritical fluids by operating at a higher system pressure, and we can create more accurate representative physics models by capturing these unique behaviors of supercritical fluids.

*[Figure: Oxygen Properties 2]*

*Oxygen Properties in Engine*

## Great, Now Let's Make a Regeneratively Cooled Nozzle Using Oxygen

To tie this all together, let's apply this knowledge to the design of a regeneratively cooled nozzle from first principles. So far we have not been speaking about legacy design practices, but rather the fundamental physics of the problem, which is a core tenant of the design philosophy used in this codebase. When you take a first-principles approach, there is often something natural hiding in the physics of the problem that can be taken advantage of. If you are thoughtful enough, you may find it easier to swim with the river rather than against it.

With that in mind we have a physics problem, so let's lay that out and begin to chip away at it.

### What are the problems, and what does physics want?

Let's list out some of the fundamental physics challenges that we are facing that are relevant to the design of regenerative cooling architecture:

- Sub-optimal cooling fluid (Oxygen)
- Extreme temperature gradient from exhaust to wall and coolant
- Extreme pressure gradient from internal to external volumes
- Achieving adequate propellant conditioning to drive engine cycle
- Minimization of pressure losses in system
- Limited propellant mass flow per time to use as coolant
- Optimum material selection and manufacturability

Some of these things are not changeable and we must simply work around them, such as the amount of mass flow and type of coolant that is on-hand. They are critical to identify, though, because they inform us going forward. Others have more design freedom, and I will try to motivate each thought process and decision made moving forward as we discuss potential solutions to these issues. Broadly speaking, we will focus on the underlying physics to motivate the solutions rather than any existing design practices, however when the comparison to a historical context reveals something interesting I will relate the old way to a new way of thinking. That being said, technological improvements in recent years have unlocked new avenues for designing and manufacturing components that can and will change the way we think about the solutions to these issues.

Unencumbered by legacy design choices, how might we attack these issues from the ground-up? First, let's take inventory of the tools available to us.

### What options do we have to solve the problems?

We can leverage two critical concepts to get creative with the problem solving process:

1. Additive Manufacturing
2. Algorithmic Modeling

The first concept, "*additive manufacturing*", is a manufacturing type that materializes components from the addition of material (otherwise known as *3D printing*), which allows for the design of components with complex internal geometries that would be challenging/impossible to subtractively machine. The second concept, "*algorithmic modeling*" is a design approach relying on the creation of a *base set of rules* that designs are forced to follow, and allowing resultant components to emerge naturally from specifying design parameters and allowing some algorithm to determine the resulting geometry. This approach results in something interesting that I have been referencing: here the physics of the problem create the geometry rather than a designers whims. So long as the physics is modeled accurately, such designs will need very little verification of their performance between the models and real life, because their very shape was born of the desires of physics itself.

Such an algorithmic design approach could conceivably be built to accommodate additive manufacturing constraints, which further tightens the rules that the geometry-making algorithm(s) live within. This approach has the added benefit, though, of being able to churn out thousands of parametrized designs to find optimal performance in a challenging design space.

The algorithm(s) need to know about the physics of the problem in its most accurate representation possible to then use that information to create the best performing design, regardless of what those physics conditions are. This is a powerful toolset, because you are not designing just one specific nozzle, but every conceivable nozzle that can have its physics modeled accurately at varying conditions and scales. This is incredibly helpful and time efficient when the system being designed is largely novel and tweaks to the system are common and numerous. Building tools that build tools has an up front cost, but the juice is worth the squeeze when many of the questions about a design are unanswered.

### Where do we start?

With our tools in hand, we can tackle some of the easier problems first. Some things only have a few solutions, after all, and some things are beyond our control entirely (like system requirements, the divine word). For example, the coolant fluid mass flow is simply something we must live with, as it is a fundamental parameter of the overall engine and we cannot change that without changing the engine concept entirely. We must be aware of the value, however, because it will be important information to later feed to an algorithmic design tool to provide insight into the physics of our problem, but more on that later.

What about the material selection, or how to work around the extreme physics conditions? Let's think about what would be ideal and go from there:

#### Problem Solving: Material Selection

We need to keep the nozzle cool and transfer as much heat as possible into the coolant to drive the engine cycle, so we want something with a high thermal conductivity that can effectively transfer heat, but also something that is strong enough to withstand high internal pressures and other erroneous forces. If we wanted to just resist the heat we could use something with a very low thermal conductivity (like a phenolic resin or ceramic), but in this case we are prioritizing heat transfer to condition propellant, not just keeping the nozzle alive.

Copper is a common material that has a high thermal conductivity, but there's a problem. Copper, as far as metal is concerned, might as well be butter. That just won't do if we expect to hold an extreme pressure inside of the fluid system and survive potential loads from shocks or vibrations. Well, we could use some sort of copper alloy that is much stronger, but we will have to pay a price in the heat transfer because we will have to remove some copper and replaced it with things that are much stronger but have a much lower thermal conductivity. A recent-ish development in copper alloys comes from NASA's Glenn Research Center, named GR-Cop42, which swaps the pure copper out for a ratio of [94% Copper, 4% Chromium, 2% Niobium]. With these ratios the yield and ultimate strength of the material effectively doubles, however you pay a small fee of ~15-20% in reduced thermal conductivity. [6] This trade is very much worth it, making GR-Cop42 a great choice for the cooled portion of the nozzle.

To keep the discussion brief, we have entirely neglected other printable metals that simply don't even make it out of the gate from a heat transfer perspective. However, it is the onus of the designer to properly trade study the material of any given design.

#### Problem Solving: Extreme Physics Conditions with a Sub-Optimal Cooling Fluid

One of the most distinct physics challenges to solve is the use of Oxygen as the sole cooling fluid for a nozzle. The use of Oxygen in cooling architecture is not unheard of, however it has only really been used in lab settings as opposed to flight-grade vehicle systems. We also are limited to relatively small nozzles, which at first might sound like a good thing but there is a sneaky problem that must be contended with:

In a regeneratively cooled nozzle, the volume of a cooling jacket increases cubically (to the 3rd power) while the nozzle surface area that needs to be cooled increases quadratically (to the second power). This means that as nozzles grow, the conventional wisdom is that the volume of propellant cooling the wall grows exponentially faster than the wall that needs to be cooled, so the ability to condition (heat) a propellant to drive an engine cycle gets harder the larger a nozzle becomes (Fans of pop-science may be familiar with the square-cube law problem). This problem happens in reverse for small nozzles, where lower coolant flowrates (due to smaller engines) are responsible for cooling more wall, which is further complicated by using Oxygen as a coolant.

In the days of old there were two common approaches to manufacturing the cooling architecture that were inevitable based on manufacturing constraints: brazed tubes and milled rectilinear channels. In the former case, long circular tubes were bent into the shape of a nozzle contour and welded together, and in the latter case rectangular slots were milled along the outside of a nozzle block and later capped with some sleeve to hold the fluid in.

*[Figure: Brazed Tube Cooling Channels]*

*Saturn V Injector and Nozzle Throat with Brazed Tube Cooling Channels*

*[Figure: Milled Regen Channels]*

*Rectilinear Cooling Channels Milled into Copper Nozzle*

The geometry of cooling architectures were largely fixed at that point, which was fine for those cases because the fuel material was sufficient to cool the walls and drive the engine cycle.

With a more adept cooling fluid we may have been able to just place some straight tubes from one end of the nozzle to the other, or rely on legacy rectangular channel designs, but doing so with Oxygen-filled channels would leave us with one melty nozzle. We need a way to both increase the amount of heat transfer into the Oxygen, and increase the amount of time it is able to perform heat transfer.

There are competing problems at play that we must contend with: heat transfer and pressure drop. The longer and smaller we make the channels the greater the heat transfer, but the larger the pressure drop. This is because fluid moving faster through a smaller channel has a larger heat transfer coefficient, but also experiences more viscous pressure losses. That pressure is needed downstream to spin a turbine and maintain chamber pressure, so we can't be selfish and eat it all while cooling the nozzle down. We need a way to determine, ideally quickly and at a glance, how small variations in cooling geometry impact the heat transfer and pressure drop performance.

### Problem Solving: Listening to Physics

Rectangular shaped cooling channels were a consequence of manufacturing constraints, but engineers still retroactively justified their performance by tweaking the parameters of the channels that were able to be manipulated and determining what made the best version of the limited geometry scope. The biggest improvement came from realizing that high aspect-ratio rectangular cross section channels (skinny and tall) created natural convective vortices due to the temperature gradient from the hot side of the rectangle to the colder side, which improved coolant mixing and overall performance. If we lean further into the idea of improved mixing to improve heat transfer, we might imagine a way to induce vorticity in the flow without relying on the natural convective vortices that arise due to the temperature gradient in the cooling passages. If the fluid wants to spin regardless then let's not get in the way! If we want to get more involved in the vorticity, why don't we nudge the Oxygen into a vortex ourselves? We could make a tube that has grooves of some kind so that when you twist it you end up with a helical shape similar to the inside of a gun barrel (or a churro for my foodies).

*[Figure: Gun Barrel Rifling]*

*Internal Rifling of a 105mm Royal Ordinance L7 Tank Gun*

*[Figure: Churro]*

*Churros*

This will cause the Oxygen inside of the cooling channels to spin, which will disrupt thermal boundary layer development and increase variable density fluid mixing, improving overall heat transfer into the fluid and thereby increasing heat transfer to the hot wall.

We're not fighting the current, but we still have some things to keep in mind. Fluids don't *love* sharp corners from a pressure drop perspective, and both the square rifling in the tank barrel and the sharp pointy curro peaks are a bit aggressive for our purposes. We would be better off smoothening the rifling out a bit, more like a cartoon flower:

*[Figure: Spongebob Flowers]*

*Unrelated Cartoon Flowers*

Cartoon flowers are a bit exaggerated, I want something a bit more tame:

*[Figure: Single Fluted Cross Section]*

*Fluted Cross Section*

There we go. We've been calling this fluted, which is how I will refer to it from now on. This is a step in the right direction, lets extrude this and spin it about and see how it looks:

*[Figure: Straight fully-fluted channel 1]*
*[Figure: Straight fully-fluted channel 2]*

*Straight Fully-Fluted Helical Channel*

This is looking good, but we have a problem. Right now, the channels have a non-uniform hot-wall thickness because of the flutes:

*[Figure: We have a problem]*

*Variable hot wall thickness due to flutes*

This will inevitably lead to temperature variation on the hot wall, which is not ideal for us. What if we could smush all of the flutes on the side near the hot wall flat, so that on the hot wall side the cross section was a circle but it still had the flutes on the top side?

*[Figure: We have solved the probelm]*

*Fluted cross sections flattened along the hot wall*

The helix is maintained as the flutes are rolled about the channel centerline, but the flattened side is always held adjacent to the nozzle hot wall. See the above sketch of three adjactent channels. As a result, the flutes would appear to poke in and out of existance as they spun around if you looked down the length of a channel.

The heat transfer at each point along the channel is related to the velocity of the coolant. Since the massflow of coolant through the nozzle is driven by the system thrust requirement, the velocity of the coolant at any point of the channel is manipulated by varying the cross sectional area. In a stationary nozzle reference frame, when the velocity of the coolant is high, it can be thought of like an ice pack that is constantly being refreshed. The nozzle wall stays cool but the coolant does not experience adequate conditioning. The cooling architecture radius variation is designed to balance the channel outlet conditions with the nozzle wall conditions, transfering as much energy into the coolant as possible without melting critical hardware.

With this methodology of designing the channel radius distribution, it is inevitable that there would be large gaps between the channels if you were to simply align them axially along the nozzle wall. To make effecient use of the space and  maximize energy exchange, the channels, which are themselves helical, are wrapped around the nozzle wall.

![Jacket](.\regenDesignImages\jacket.png)

*A completed regen jacket*

## The Algorithm

Think long and hard about how you would make the previously described cooling channels in a CAD software like NX. Now throw those thoughts away because we did it in Python.

The Nozzle class not only handles the contour generation but also the cooling architecture. With this tool in our design suite, we can rapidly interate through regen designs, generating geometry and doing the first pass of performance analysis in a matter of minutes.

### Generating the pathline

The pathline is the centerline of one cooling channel. The inner nozzle wall is defined by method of characteristics, so the 2D pathline is offset by one channel radius plus the desired hot wall thickness. Thus, the channel radius distibution must be calculated first with the private method ``distributeChannelRadii()``, which creates a smooth transition between the 5 channel radius control points. The inlet and outlet control points refer to the flow of the coolant, so the "inlet" is located where we would normally consider the exit plane of the nozzle and vice versa. The throat control point is automatically placed where the nozzle contour radius is smallest. The grain control point is located where the inner surface of the fuel grain intersects the nozzle contour. Finally, the "throat inlet" control point is an additional point between the throat and the grain interface. This control point is loacted at a point of inflection of a sunken contour.

The channel distribution function first validates the user inputs to ensure that

$$
channel Outlet Radius < channel Grain Radius
$$

$$
channel Grain Radius < channel Throat Inlet Radius
$$

$$
channel Throat Inlet Radius < channel Throat Radius
$$

$$
channel Throat Radius > channel Inlet Radius
$$

This check ensures that there will be no backwards roll or overlapping channels. The distribution function then uses a combination of cubic and bezier splines to enforce appropriate tangencies and extrema for both traditional and sunken contours.

*[Figure: Channel Radius Control Points]*

With the channel radius distribution defined, the 2D channel centerline can be constructed with a simple call to our in house ``parallelOffset()`` tool. Simulataneously, a few other offset curves are generated for later reference. The "cold wall" is offset from the hot wall by one hot wall thickness. The 3D channels will eventually rest against this imaginary wall, therefor all the heat transfer that we care about happens between the hot and cold walls. The "shell" is also generated by offsetting one hot wall thickness, one channel diameter, and one shell thickenss from the hot wall. The shell is the outermost wall that you see when you look at a completed nozzle in the real, physical world. The shell ultimately gives the nozzle wall finite depth for the channels to live within.

*[Figure: Nozzle]*

The 2D channel pathline must then be wrapped around the nozzle. Channel wrapping allows for the most efficient use of space for heat transfer. The algorithm that detwermines the wrap angles is called Kineo's Algorithm because Kineo wrote it and is the only person who really knows how it works. This author is not Kineo.

As an aside, this author did write the smartRadii option for Kineo's Algorithm. When smartRadii is set to True (which it is by default), the method will calculate the maximum number of channels, N, that can fit at any point along the nozzle based on the local channel radius:

$$
\begin{align}
    N = floor(w{2 \pi R\over{t_{infill} + r(2+2f)}})
\end{align}
$$

where $w$ is the channel wrap modifier, $R$ is the nozzle radius, $t$ is the infill thickness, $r$ is the channel radius, and $f$ is the flute amplitude coefficient. The check is triggered if any $N$ is less than $N$ based on the throat, inidcating that the channel radius is too large at that point. If the check is triggered at any point, the equation is solved in reverse for the maximum allowable radius at that point:

$$
\begin{align}
    r = {w 2 \pi R + N_{throat} t_{infill} \over 2N_{throat}(1+f)} 
\end{align}
$$

The offset curves are then recalculated with this new channel radius distribution. This check is intended to keep channels from overlapping, however a visual check by the engineer is always necessary for all things. smartRadii runs inside Kineo's Algorithm and prints to the terminal when triggered.

So anyway, trust and beleive you now have wrap angles. The wrap angles are used in a DCM roll operation about the nozzle azis to create the 3D channel centerline.

### Generating the cross sections

A fluted cross section starts in an "unwrapped" state in the form of a sine wave. The sine wave takes in the arguments of $n_f$ (the number of flutes) and $f$ (the flute amplitude coefficient). The wave is shifted vertically based on the local channel radius and closed by converting from polar to cartesian. The result is a set of flower shaped cross sections which vary only with the local channel radius.

$$
\begin{align}
    r_{fluted} = r_{i} + fr_{i}sin(\theta n_{f})
\end{align}
$$

$$
0<\theta<2\pi
$$

![Unwrapped Fully Fluted Cross Section](.\regenDesignImages\unwrappedFlutes2.png)

$$
\begin{align} 
    x_{fluted,i} = r_{fluted}sin(\theta) \\
    y_{fluted,i} = r_{fluted}cos(\theta) \\
\end{align}
$$

*[Figure: Wrapped Fully Fluted Cross Sections]*

### Generating the channel

To create the helical pattern, each cross section must be rolled about its center. The amount each cross section is rolled is dependent on the user input the helix angle, the local channel radius $r_c$, and the emergent total path length. The differential path length $\Delta L$ is the length of path between one cross section and the next and $L$ is the total path length of the channel.

$$
\Delta L = \sqrt{\Delta x_{3Dpath}^{2} + \Delta y_{3Dpath}^{2} + \Delta z_{3Dpath}^{2}}
$$

$$
L = \Sigma (\Delta L)
$$

The differential roll $\phi_i$ of each cross section is a percentage of the total roll $\Phi$ of the path equivalent to the percentage of the total path length represented by that cross section:

$$
\Phi = tan(H_f) * L/r_c
$$

$$
\bar{\phi_i} = dL/L
$$

$$
\phi_i = \bar{\phi_i} * \Phi
$$

Each cross section is then rolled with a simple DCM operation:

$$
{\begin{bmatrix}
    x\\
    y\\
    0\\
\end{bmatrix}}_{rolled,i} 
= 
\begin{bmatrix}
    1 & 0     & 0     \\
    0 & cos(\phi_{i}) & -sin(\phi_{i})\\
    0 & sin(\phi_{i}) &  cos(\phi_{i})\\
\end{bmatrix}
{\begin{bmatrix}
    x\\
    y\\
    0\\
\end{bmatrix}}_{fluted,i}
$$

*[Figure: Wrapped and Rolled Fully Fluted Cross Sections]*

The fully fluted and rolled cross sections are then placed along the pathline. They are "flown" along the pathline with a DCM operation to maintain each face locally perpendicular to the pathline. In this operation, the "roll" has already been achieved by Kineo's wrapping algorithm. The pitch and yaw are calculated as such by the 3D centerline:

$$
\begin{align}
    Yaw:\psi = -arctan({\Delta z_{3Dpath}\over \Delta x_{3Dpath}})
\end{align}
$$

$$
\begin{align}
    Pitch:\theta = -arctan({\Delta y_{3Dpath}\over \sqrt{\Delta x_{3Dpath}^2 + \Delta z_{3Dpath}^2}})
\end{align}
$$

Finally, each cross section must be flattened along the cold wall. This is acheived by identifying the index of the cross section which is closest to the hot wall with a searching algorithm and superimposing a gausian curve over the unwrapped cross section at this index. The process to find the "gaussian compression index" is split into two searches for efficiency. Instead of searching the whole cross section, the pathline location of the cross section is compared to the nozzle wall to yeild the "nozzle index," then the nozzle index is compared to the corresponding circular cross section to yeild the final compression index.

The compressed sin wave is then converted back to polar to yeild the final cross section.

*[Figure: Compression Process, Unwrapped]*
*[Figure: Compression Process, Wrapped]*

### Generating the jacket

Now that one gaussian fluted channel has been created, the jacket is made by simply patterning the channel about the nozzle axis the correct number of times. EZPZ lemon squeezy.

![Jacket](.\regenDesignImages\jacket.png)

*A completed regen jacket*

### Modeling the performance

To fascilitate rapid iterative design, the heat transfer properties of the generated architecture are estimated by a 1 dimensional (along the nozzle wall) heat transfer model.

The heat transfer of the system is estimated using a thermal resistance model. Thermal resistance models imagine heat flux like current  and temperature like voltage in an electric circuit. The different heat transfer modes are modeled as resistances to the flow of energy.

*[Figure: Thermal Resistance]*

*A thermal resistance circuit*

The heat transfer through a circuit is

$$
\begin{align}
    \dot{Q} = \Delta T / R_{equivalent}
\end{align}
$$

where $\dot{Q}$ is constant throughout the circuit. The thermal resistances of conduction across a circular pipe wall and convection respectively are

$$
\begin{align}
    R_{COND} = {ln(r_{outer} / r_{inner}) \over 2\pi L k}
\end{align}
$$

$$
\begin{align}
    R_{CONV} ={1 \over hA}
\end{align}
$$

where $r_{outer}$ and $r_{inner}$ are the outer and inner radii of the conducting wall, $L$ is the differential path length, $k$ is the thermal conductivity of the conducting material, $h$ is the heat transfer coefficient of the convecting flow, and $A$ is the surface area. The equivalent resistance for three resistors in series is

$$
\begin{align}
    R_{equivalent} = R_{CONV,HOT} + R_{COND} + R_{CONV,COLD}
\end{align}
$$

The material properties of GR-Cop42 are well characterized, however determining convective heat transfer coefficients is very tricky and usually requires an empirical correlation. For the exhaust side we use the Bartz equations [8]:

$$
\begin{align}
    h_{Hot} = ({0.026 \over D_{throat}^{0.2}}) 
        ({\mu^{0.2}c_P \over Pr^{0.6}})
        ({P_{chamber} \over c^*})^{0.8}
        ({D_{throat} \over r_c})^{0.1}
        ({A_{throat} \over A})^{0.9}
        \sigma
\end{align}
$$

$$
\begin{align}
    \sigma = {1 \over ({1 \over 2}{T_{wall} \over T_{chamber}}(1 + {\gamma - 1 \over 2}M^2) + {1 \over 2})^{0.68}
        (1 + {\gamma - 1 \over 2}M^2)^{0.12}}
\end{align}
$$

where $r_c$ is the radius of curvature of the throat ans the Prandtl number, viscosity, and heat capacity are stagnation values.

$$
\begin{align}
    Pr = {4\gamma  \over 9\gamma - 5}
\end{align}
$$

$$
\begin{align}
    \mu = 1.184 \times 10^7MW^{0.5}T_{total}^{0.6}
\end{align}
$$

$$
\begin{align}
    c_P = R{\gamma \over \gamma - 1}
\end{align}
$$

The molecular weight, gas constant, and ratio of specific heats are caclulated with NASA's CEA.

Because the Bartz heat transfer coefficient equation is dependent on the yet unkown hot wall temperature, it must be run in a convergence loop.

This correlation is well chracterized for the regen nozzles of old, but it has been shown in our simulations to unable to account for two important effects in our nozzle design. First, the $\sigma$ term in is a boundary layer correction term. This holds up well for showerhead injection, however our boundary layer is appreciably effected by swirling flow. Secondly, there is no term which captures the impingement and recirculation effects of a sunken converging section. As of [07/16/2025], we are developing our own correction terms for both of these factors with a CFD study.

For the coolant flow, we use the definition of Nusselt number to calculate the convective heat transfer coefficient:

$$
\begin{align}
    h_{COLD} = {k_{fluid} * Nu \over d_H}
\end{align}
$$

where $d_H$ is the hydraulic diameter of the channel. Thermofluid properties like thermal conductivity are calculated with refWrap, and we leverage two empirical correlations for the Nusselt number itself. We consider the Nusselt number to be in bewtween the Gnielinski correlation for circular channels [9] and the fully fluted correlation from Principles of Enhanced Heat Transfer [6].

$$
\begin{align}
    Nu_{Semi Fluted} =( 0.25*Nu_{Fluted}) + (0.75*Nu_{Gnielinski})
\end{align}
$$

$$
\begin{align}
    Nu_{Gnielinski} = {({f/8})(Re_D-1000)Pr \over 1 + 12.7(f/8)^{1/2}(Pr^{2/3}-1)}
\end{align}
$$

$$
\begin{align}
    Nu_{Fluted} = 0.064Re_{d_H}^{0.773}Pr^{0.4}({F_A\over d_H})^{-0.242}({F_P\over d_H})^{-0.108}({F_H\over 90})^{0.599}
\end{align}
$$

where the Gnielinski friction factor is $ f = (0.79*ln(Re)-1.64)^{-2} $ and $F_A$, $F_P$, and $F_H$ are the flute amplitude, pitch, and helix angle respectively.

The heat transfer model outputs 10 plots of coolant properties, the exhaust side heat transfer coefficent, and the nozzle hot wall temperature along the nozzle axis. Additionally, the results for circular channels as well as CFD correlation study results are also plotted for comparison. These outputs are intended to help the engineer narrow down the cooling architecture by making the iterative design process quicker, however the model is inherently limited and the selected design should be put through a complete analysis package including three dimensional FEA and CFD.

![Heat Transfer Model Outputs](.\regenDesignImages\heatTransferModel.png)

*Sample heat transfer model outputs.*

# References

[6] Webb, Kim - Principles of Enhanced Heat Transfer

[8] Bartz - A Simple Equation for the Rapid Estimation of Rocket Nozzle Convective Heat Transfer

[9] Gnielinski - Neue Gleichungen für den Wärme- und den Stoffübergang in turbulent durchströmten Rohren und Kanälen
        (New equations for heat and mass transfer in turbulent flow pipes and channels)

# Author

Author: Isabella Duprey-Churn
Date:   07/16/2025
