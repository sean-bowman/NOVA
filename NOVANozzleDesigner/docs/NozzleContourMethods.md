[Home](../../README.md) &gt; [Nozzle Contour Methods](./NozzleContourMethods.md)

# NOVA: Nozzle Contour Methods and Their Limits

A supersonic nozzle wall is a free surface. Nothing in the physics fixes its shape; the designer chooses it, and the choice is a trade between the thrust the wall recovers and the length, mass and cost it takes to recover it. The families below are the answers that trade has produced, in the order they were invented. This document says what each one optimises, how it is generated, what it gives up, and which one NOVA builds.

The companion documents are [NozzleContour.md](./NozzleContour.md), which derives NOVA's implementation, and [NozzleContourValidation.md](./NozzleContourValidation.md), which measures it. Sources are recorded in [references_nozzleContour_2026-09-06.md](./references_nozzleContour_2026-09-06.md).

## Contents

- [The reference length](#the-reference-length)
- [Conical](#conical)
- [Ideal](#ideal)
- [Truncated ideal](#truncated-ideal-contour-tic)
- [Thrust-optimised contour](#thrust-optimised-contour-toc)
- [Thrust-optimised parabola](#thrust-optimised-parabola-top)
- [Compressed truncated ideal](#compressed-truncated-ideal-ctic)
- [Dual bell](#dual-bell)
- [Plug and aerospike](#plug-and-aerospike)
- [Choosing between them](#choosing-between-them)
- [The transonic starting line](#the-transonic-starting-line)
- [What NOVA builds](#what-nova-builds)

---

## The reference length

Every bell length in the literature is quoted against the same yardstick, and the definition matters more than it looks.

NASA SP-8120 states it exactly: percent bell is the length of the bell nozzle as a percent of the length of a 15 degree half-angle conical nozzle **having the same expansion area ratio**. So

$$L_{cone} = \frac{(\sqrt{\epsilon} - 1) \, R_t}{\tan 15^\circ}, \qquad f = \frac{L_{nozzle}}{L_{cone}}$$

The cone is tied to the area ratio the nozzle actually delivers. A tool that computes the reference cone from a design-point area ratio and then delivers a different one is quoting a length fraction against a yardstick nobody else uses, and its numbers will not compare against published bells.

Two conventions follow from this and are worth stating once. The 15 degree half angle is a convention, not an optimum. And the length is measured from the throat plane, not from the injector face or the end of the throat arc.

## Conical

**What it optimises.** Nothing. It is a straight line at a chosen half angle.

**How it is generated.** Geometry alone. Given the throat radius, the area ratio and the half angle, the wall is fixed.

**What it costs.** The exit flow diverges, so the axial component of the exhaust momentum is reduced. The classical correction is the divergence loss factor

$$\lambda = \frac{1 + \cos\alpha}{2}$$

which is 0.983 at 15 degrees. This is a point-source result and becomes exact only as the area ratio grows; at low area ratio the divergence efficiency oscillates with area ratio rather than following the formula, and shocks can form at the tangency where the arc meets the straight wall.

**Where it is used.** Small rockets, and anywhere tooling cost dominates performance. SP-8120 notes that for low area ratios cones can be used with no measurable loss.

## Ideal

**What it optimises.** Nothing directly; it is the contour that produces a **uniform, axial, shock-free exit flow**. Every streamline leaves at the same Mach number and parallel to the axis, so there is no divergence loss and no exit-plane non-uniformity at all.

**How it is generated.** A method-of-characteristics solve. A starting line is placed just downstream of the throat, the characteristic mesh is marched outward, and the wall is drawn as the streamline that turns the flow from its initial divergence back to axial. The wall shape is a result of the mesh, not an input to it.

**What it costs.** Length. An ideal nozzle at a useful area ratio is far too long to fly, and the last part of it contributes almost nothing, because the flow there is already nearly axial. This is the reason nobody flies one.

## Truncated ideal contour (TIC)

**What it optimises.** Nothing directly. It inherits the ideal contour's shock-free interior and then throws away the part that does not pay for its own mass.

**How it is generated.** SP-8120 states the method in one sentence: design an ideal nozzle to a **higher area ratio than required**, so that when the ideal nozzle is truncated **to the desired area ratio** the correct nozzle length is obtained. The primary reference is Ahlberg, Hamilton, Migdal and Nilson (1961).

Note the direction of the constraint. The area ratio is what you specify and where you cut. The length is what falls out. Specifying a length and cutting there instead is a different design method with a different name, and it will not land on the requested area ratio.

**What it costs.** The truncated exit plane is no longer uniform. The flow still diverges at the wall, so a divergence loss returns, smaller than a cone's. SP-8120 classifies the TIC as a **nonoptimum** contour, recommended where performance losses of the order of 0.25 percent against the mathematical optimum are tolerable.

**What it buys.** The TIC has no minimum length. The optimum method fails below a minimum length that grows with area ratio, and the TIC is what SP-8120 recommends in exactly that regime: short nozzles at high area ratio.

## Thrust-optimised contour (TOC)

**What it optimises.** Axial thrust, directly, at a fixed length and exit area.

**How it is generated.** Rao's 1958 variational-calculus maximisation over a control surface. The wall is the shape that maximises the momentum integral subject to the length and area constraints.

**What it costs.** The interior is no longer shock free. Recompression waves generated by the wall coalesce into an internal shock, which is the price of turning the flow more aggressively in less length. The method also fails outright below a minimum length.

**What it buys.** The best thrust available for a given length and area ratio. This is the mathematical optimum every other family is measured against.

## Thrust-optimised parabola (TOP)

**What it optimises.** The same thing as the TOC, approximately, with a contour anyone can draw.

**How it is generated.** Rao's 1960 approximation. A skewed parabola, in modern terms a quadratic Bezier curve, runs from the throat exit arc at inflection angle theta_n to the exit at angle theta_e. The two angles are read from a chart against area ratio and percent bell. The throat is a 1.5 throat-radius entrant arc and a 0.382 throat-radius exit arc.

**What it costs.** A fraction of a percent against the true optimum, and a chart that SP-8120 marks as **extrapolated above an area ratio of about 50**. Any TOP drawn at high area ratio is drawn from extrapolated data.

**What it buys.** Almost all of the TOC performance with no solver at all, plus a practical advantage the optimum does not have: the higher exit wall pressure of a parabolic contour delays flow separation at sea level, which is why parabolic contours appear on engines that must be ground tested overexpanded. SP-8120 records the J-2 as the case where this was done deliberately, and where getting it wrong produced unstable asymmetric separation and structural failures.

**What the angles look like.** An 80 percent bell at area ratio 70 has theta_n near 33 degrees and theta_e near 7 degrees. At area ratio 40 the same bell is near 31 and 8 degrees.

## Compressed truncated ideal (CTIC)

**What it optimises.** Length, by scaling a truncated ideal contour axially so it fits a shorter envelope.

**How it is generated.** Take a TIC and compress it along the axis.

**What it costs.** The compression breaks the characteristic solution the contour came from, so the interior is no longer shock free. Reviews report that the CTIC is not more efficient than a Rao contour, so it is a geometric convenience rather than a performance method.

## Dual bell

**What it optimises.** Altitude compensation, with no moving parts.

**How it is generated.** A base bell of moderate area ratio joined at a deliberate wall inflection to an extension of much higher area ratio. At low altitude the flow separates cleanly and repeatably at the inflection; at high altitude it attaches through the extension.

**What it costs.** A transition that must be made to happen at the right altitude and to happen symmetrically. The side loads during transition are the design problem.

## Plug and aerospike

**What it optimises.** Altitude compensation through an unconfined outer boundary, and package length.

**How it is generated.** SP-8120 describes the design as running backwards: start from the Mach line of an ideal exit flowfield, where the Mach number is constant and the flow is axial, and work upstream along the expansion surface. Then truncate to the desired length. The transonic flowfield is not computed, and the resulting difference between the design and actual flowfields is not significant for overall efficiency.

**What it costs.** A base. The truncation leaves a recirculating region whose pressure adds to thrust and whose thermal environment is severe. Base pressure, and how secondary flow is introduced into the base, dominates the design. Direct optimisation of a truncated plug has not been developed; SP-8120 notes that truncated ideal plug nozzles outperform optimum plugs designed on a zero base pressure assumption.

**Where it stands.** Not operational as of SP-8120, and still not as of today.

## Choosing between them

| Family | Optimises | Interior | Minimum length | Typical use |
|---|---|---|---|---|
| Conical | nothing | shock free if the tangency is clean | none | small engines, low area ratio |
| Ideal | uniform axial exit | shock free | none, but impractically long | reference only |
| Truncated ideal | inherited from ideal | shock free | none | high area ratio, short length, upper stages |
| Thrust-optimised contour | axial thrust at fixed length and area | internal shock | grows with area ratio | the performance benchmark |
| Thrust-optimised parabola | approximates the TOC | internal shock | inherits the TOC chart | most flight bells |
| Compressed truncated ideal | envelope length | shock introduced by compression | none | packaging |
| Dual bell | altitude compensation | separation at a designed inflection | not applicable | research |
| Plug and aerospike | altitude compensation, package length | shock free on the spike | not applicable | research |

The ordering by performance at equal length and area ratio is TOC first, TOP a fraction of a percent behind, TIC about a quarter of a percent behind that, conical last. The ordering by ease of generation is the reverse. Reported figures put the gain from length-constrained optimisation at 0.5 to 1 percent in thrust at equal length or weight, and a TIC at the same area ratio as a parabolic baseline delivers nearly identical thrust and specific impulse while running roughly 10 percent longer.

## The transonic starting line

Every characteristics method needs a line on which the flow is already supersonic and known. That line comes from a transonic solution near the throat, and it is the one part of a contour generator whose accuracy is set entirely by a choice made before any characteristic is drawn.

The solutions form a single series. Sauer (1944) is the first-order term. Hall (1962) extended it; Kliegel and Quan (1966) gave the series explicitly and showed their first-order throat conditions are identical to Sauer's and Hall's, and their second-order conditions identical to Hall's. The throat wall velocity for axisymmetric flow is

$$u(0,1) = 1 + \frac{1}{4R} + \frac{14\gamma + 15}{288 R^2} + O(R^{-3})$$

with R the throat wall radius of curvature normalised by the throat radius. All orders share the property that the throat conditions are independent of nozzle shape; only the behaviour away from the throat plane depends on the wall.

Two consequences matter for a solver.

The series is ill-behaved at small R. Taken literally it maximises near R = 1 and returns a subsonic throat wall velocity below about R = 0.5. Kliegel and Levine (1969) recast it in inverse powers of R + 1, which fixes the small-radius behaviour and shifts the sonic line towards the divergent section. The Hall and Kliegel-Quan forms are reported to give favourable results only for R of about 1.5 or greater.

Retaining Sauer's term alone is a quantifiable choice. At R = 1.5 and gamma = 1.1475 the retained first-order term contributes 0.1667 to the normalised throat wall velocity and the first neglected term contributes 0.0479, so the dropped term is 29 percent of the retained correction. SP-8120's recommended practice at this radius ratio is a 29-term series.

## Cross-reference against other axisymmetric characteristics implementations

Contour generators that solve the axisymmetric method of characteristics differ from one another along five axes, and the axes are worth naming because they are the questions to ask of any of them, NOVA included.

**The starting line.** Where does supersonic flow begin, and how is it known there? The choices run from a straight sonic line through Sauer's first-order solution to a high-order series. This is where the largest unforced error usually lives, because everything downstream is marched from it.

**The unit process.** Whether the compatibility relations are integrated in a velocity formulation or a Prandtl-Meyer formulation, whether the coefficients are evaluated at the upstream point or averaged along the characteristic, and how many corrector passes are taken. Averaged coefficients with iteration are second-order accurate; a single upstream evaluation is first-order.

**How the wall is constructed.** An ideal or truncated ideal contour draws the wall as a streamline through a solved mesh. A thrust-optimised contour solves for the wall as part of an optimisation. A parabolic contour draws the wall first and never solves for it at all.

**The gas model.** Perfect gas at a single ratio of specific heats, perfect gas with a frozen exit gamma, equilibrium properties, or coupled finite-rate kinetics.

**What terminates the solve.** Area ratio, length, exit Mach number, exit pressure, or the end of the mesh. This choice decides which of the requested design parameters is binding and which are outputs, and it is the axis most often left implicit.

Four implementations for comparison:

| Implementation | Starting line | Wall construction | Gas model | Terminates on |
|---|---|---|---|---|
| TDK, the JANNAF standard | series-form transonic solution | reads a supplied contour; contour design is a separate module | coupled finite-rate kinetics, plus a boundary layer module | supplied geometry |
| IMOCND (NASA LAR-16744-1) | uniform or non-uniform supersonic inflow, supplied | streamline through the mesh, for shock-free uniform exit | irrotational potential flow; the run stops if a shock forms | uniform exit achieved |
| Young (Auburn, 2012) | not stated in the published abstract | full characteristics solution, driven by an optimised wall pressure distribution | finite-rate chemistry coupled to the characteristics solve | a specified performance goal |
| NOVA | Sauer, first order | streamline through the mesh, flow straightened to axial | perfect gas at chamber gamma | see [NozzleContourValidation.md](./NozzleContourValidation.md) |

Two observations follow. First, NOVA sits at the simple end of every axis except wall construction, where it does the same thing the reference codes do. That is a coherent position for a design tool: the contour a full characteristics solve produces is not very sensitive to the gas model, which is exactly why Rao's parabolic approximation works across propellant combinations at all.

Second, the axis where simplicity is least defensible is the starting line, because SP-8120 names a specific practice (a 29-term series at a radius ratio of 1.5) and Sauer is one term of it. That is a measurable gap rather than a matter of taste, and it is measured in the validation document.

## What NOVA builds

NOVA generates a **truncated ideal contour**, by the method above: a characteristics mesh from a transonic starting line, a wall traced as the streamline that straightens the flow, and a truncation.

Within that, the specific choices are:

| Element | NOVA | Reference practice |
|---|---|---|
| Transonic starting line | Sauer, first order | Series-form solution, 29 terms at a radius ratio of 1.5 (SP-8120) |
| Throat entrant arc | 1.5 throat radii | 1.5 is the commonly used value; SP-8120 prefers about 1.0 for efficiency, and requires above 0.6 |
| Throat exit arc | 0.382 throat radii | Rao's preferred throat geometry, the same value used in the TOP construction |
| Initial wall angle | one quarter of the Prandtl-Meyer angle at the design exit Mach number | Rao throat assumption |
| Gas model | perfect gas at a single chamber gamma | equilibrium gas properties (SP-8120); constant specific heat is recommended only for the transonic solution |
| Truncation criterion | see [NozzleContourValidation.md](./NozzleContourValidation.md) | truncate to the desired area ratio (SP-8120, Ahlberg et al.) |
| Boundary layer | not modelled | displacement thickness computed and the wall offset point by point |
| Kinetics | not modelled | finite rate, coupled, in the JANNAF standard method |

The last three rows bound what NOVA can claim. A perfect-gas inviscid characteristics solve is the aerodynamic core of the standard method with the chemistry and the viscous corrections removed. For scale, the JANNAF standard code TDK predicts delivered vacuum specific impulse to within 0.12 to 1.9 percent of experiment with all of that included.

## References

[1] Anon.: *Liquid Rocket Engine Nozzles*. NASA Space Vehicle Design Criteria Monograph, NASA SP-8120, July 1976.

[2] Rao, G. V. R.: *Exhaust Nozzle Contour for Optimum Thrust*. Jet Propulsion, vol. 28, no. 6, June 1958, pp. 377-382.

[3] Rao, G. V. R.: *Approximation of Optimum Thrust Nozzle Contour*. ARS Journal, vol. 30, no. 6, June 1960, pp. 561-563.

[4] Ahlberg, J. H.; Hamilton, S.; Migdal, D.; and Nilson, E. N.: *Truncated Perfect Nozzles in Optimum Nozzle Design*. ARS Journal, vol. 31, no. 5, May 1961, pp. 614-620.

[5] Sauer, R.: *General Characteristics of the Flow Through Nozzles at Near Critical Speeds*. NACA TM 1147, 1947.

[6] Hall, I. M.: *Transonic Flow in Two-Dimensional and Axially-Symmetric Nozzles*. Quarterly Journal of Mechanics and Applied Mathematics, vol. 15, 1962, pp. 487-508.

[7] Kliegel, J. R.; and Quan, V.: *Convergent-Divergent Nozzle Flows*. AIAA Journal, vol. 6, no. 9, September 1968, pp. 1728-1734. Full report: TRW Systems 02874-6002-R000, December 1966, NASA contract NAS9-4358.

[8] Kliegel, J. R.; and Levine, J. N.: *Transonic Flow in Small Throat Radius of Curvature Nozzles*. AIAA Journal, vol. 7, no. 7, July 1969, pp. 1375-1378.

[9] Migdal, D.; and Landis, F.: *Characteristics of Conical Supersonic Nozzles*. ARS Journal, vol. 32, no. 12, December 1962, pp. 1898-1901.

[10] Nickerson, G. R.; Dang, L. D.; and Coats, D. E.: *Engineering and Programming Manual: Two-Dimensional Kinetic Reference Computer Program (TDK)*. NASA CR-178628, 1985.

[11] *Rocket nozzles: 75 years of research and development*. Sadhana, Indian Academy of Sciences, vol. 46, 2021.

## Author's Information

Sean Bowman - Last Updated [09/06/2026]
