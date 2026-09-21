
[Home](../../README.md) &gt; [Nozzle Contour Methods](./NozzleContourMethods.md)

# NOVA: Nozzle Contour Methods and Their Limits

A supersonic nozzle wall is a free surface. Nothing in the physics fixes its shape; the designer chooses it, and the choice is a trade between the thrust the wall recovers and the length, mass and cost it takes to recover it. The families below are the answers that trade has produced, in the order they were invented. This document says what each one optimizes, how it is generated, what it gives up, and which ones NOVA builds.

NOVA builds three: the truncated ideal contour, the thrust-optimized parabola and the thrust-optimized contour. The conical section is available beside them. Each returns the same solution object, so the cooling model, the plume march, the figures and the export chain read any of them without knowing which family produced the wall.

The companion documents are [NozzleContour.md](./NozzleContour.md), which derives NOVA's implementation, and [NozzleContourValidation.md](./NozzleContourValidation.md), which measures it. Sources are recorded in [references_nozzleContour_2026-09-06.md](./references_nozzleContour_2026-09-06.md) and, for the optimized families, [references_thrustOptimizedContours_2026-09-13.md](./references_thrustOptimizedContours_2026-09-13.md).

## Contents

- [The reference length](#the-reference-length)
- [Conical](#conical)
- [Ideal](#ideal)
- [Truncated ideal](#truncated-ideal-contour-tic)
- [Thrust-optimized contour](#thrust-optimized-contour-toc)
- [Thrust-optimized parabola](#thrust-optimized-parabola-top)
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

**What it optimizes.** Nothing. It is a straight line at a chosen half angle.

**How it is generated.** Geometry alone. Given the throat radius, the area ratio and the half angle, the wall is fixed.

**What it costs.** The exit flow diverges, so the axial component of the exhaust momentum is reduced. The classical correction is the divergence loss factor

$$\lambda = \frac{1 + \cos\alpha}{2}$$

which is 0.983 at 15 degrees. This is a point-source result and becomes exact only as the area ratio grows; at low area ratio the divergence efficiency oscillates with area ratio rather than following the formula, and shocks can form at the tangency where the arc meets the straight wall.

**Where it is used.** Small rockets, and anywhere tooling cost dominates performance. SP-8120 notes that for low area ratios cones can be used with no measurable loss.

## Ideal

**What it optimizes.** Nothing directly; it is the contour that produces a **uniform, axial, shock-free exit flow**. Every streamline leaves at the same Mach number and parallel to the axis, so there is no divergence loss and no exit-plane non-uniformity at all.

**How it is generated.** A method-of-characteristics solve. A starting line is placed just downstream of the throat, the characteristic mesh is marched outward, and the wall is drawn as the streamline that turns the flow from its initial divergence back to axial. The wall shape is a result of the mesh, not an input to it.

**What it costs.** Length. An ideal nozzle at a useful area ratio is far too long to fly, and the last part of it contributes almost nothing, because the flow there is already nearly axial. This is the reason nobody flies one.

## Truncated ideal contour (TIC)

**What it optimizes.** Nothing directly. It inherits the ideal contour's shock-free interior and then throws away the part that does not pay for its own mass.

**How it is generated.** SP-8120 states the method in one sentence: design an ideal nozzle to a **higher area ratio than required**, so that when the ideal nozzle is truncated **to the desired area ratio** the correct nozzle length is obtained. The primary reference is Ahlberg, Hamilton, Migdal and Nilson (1961).

Note the direction of the constraint. The area ratio is what you specify and where you cut. The length is what falls out. Specifying a length and cutting there instead is a different design method with a different name, and it will not land on the requested area ratio.

**What it costs.** The truncated exit plane is no longer uniform. The flow still diverges at the wall, so a divergence loss returns, smaller than a cone's. SP-8120 classifies the TIC as a **nonoptimum** contour, recommended where performance losses of the order of 0.25 percent against the mathematical optimum are tolerable.

**What it buys.** The TIC has no minimum length. The optimum method fails below a minimum length that grows with area ratio, and the TIC is what SP-8120 recommends in exactly that regime: short nozzles at high area ratio.

## Thrust-optimized contour (TOC)

**What it optimizes.** Axial thrust, directly, at a fixed length and exit area.

**How it is generated.** Rao's 1958 variational-calculus maximization over a control surface. The wall is the shape that maximizes the momentum integral subject to the length and area constraints.

**How NOVA generates it.** By direct optimization rather than by Rao's variational conditions, following Allman and Hoffman (1981). A fixed throat arc is followed by a low-order wall whose coefficients an optimizer varies, and each candidate is scored by marching the characteristics over it and integrating the exit plane. The two approaches answer the same question differently: the variational method derives the optimum wall, the direct method searches a family of walls for it. The direct method's advantage is that changing the gas model or the nozzle configuration changes only the objective, where the variational method has to be rederived.

NOVA's wall is a cubic Bezier in tangent-magnitude form with four design variables: the inflection and exit wall angles, and the two control-point distances along those tangents. Allman and Hoffman used a second-degree polynomial with two variables, and concluded that a higher-degree wall would close the remaining gap to Rao. The cubic is that recommendation, and it matters for a second reason: **every quadratic Bezier is a cubic whose control points sit two thirds of the way along the same tangents**, so the thrust-optimized parabola family is contained exactly inside NOVA's search space. The search can therefore be started at the chart parabola, and the answer can only improve on it.

The length and the area ratio are absorbed rather than constrained. Both are fixed by the exit point of the wall, which is set before any characteristic is drawn, so every candidate delivers them exactly and the optimizer never has to trade the design point against the objective.

**What it costs.** The interior is no longer shock free. Recompression waves generated by the wall coalesce into an internal shock, which is the price of turning the flow more aggressively in less length. The method also fails outright below a minimum length.

**What it buys.** The best thrust available for a given length and area ratio. This is the mathematical optimum every other family is measured against.

## Thrust-optimized parabola (TOP)

**What it optimizes.** The same thing as the TOC, approximately, with a contour anyone can draw.

**How it is generated.** Rao's 1960 approximation. A skewed parabola, in modern terms a quadratic Bezier curve, runs from the throat exit arc at inflection angle theta_n to the exit at angle theta_e. The two angles are read from a chart against area ratio and percent bell. The throat is a 1.5 throat-radius entrant arc and a 0.382 throat-radius exit arc.

**What it costs.** A fraction of a percent against the true optimum, and a chart that SP-8120 marks as **extrapolated above an area ratio of about 50**. Any TOP drawn at high area ratio is drawn from extrapolated data.

**What it buys.** Almost all of the TOC performance with no solver at all, plus a practical advantage the optimum does not have: the higher exit wall pressure of a parabolic contour delays flow separation at sea level, which is why parabolic contours appear on engines that must be ground tested overexpanded. SP-8120 records the J-2 as the case where this was done deliberately, and where getting it wrong produced unstable asymmetric separation and structural failures.

**What the angles look like.** An 80 percent bell at area ratio 70 has theta_n near 33 degrees and theta_e near 7 degrees. At area ratio 40 the same bell is near 31 and 8 degrees.

**How NOVA generates it.** The wall is drawn first, from the chart angles, and the flow is then solved over it by a forward characteristics march. That is the reverse of the truncated ideal contour, which solves the flow and traces the wall as a streamline through it, and it is why the parabola needs no design-point iteration: there is no free parameter to solve for, so one kernel and one march produce the answer.

Because the chart is an input here rather than a comparison target, its two known weaknesses become the family's. The digitized arrays are checked for monotonicity, the extrapolation flag above area ratio 50 is carried onto the solution and printed by the run, and a caller with better data can override the angles directly.

## Compressed truncated ideal (CTIC)

**What it optimizes.** Length, by scaling a truncated ideal contour axially so it fits a shorter envelope.

**How it is generated.** Take a TIC and compress it along the axis.

**What it costs.** The compression breaks the characteristic solution the contour came from, so the interior is no longer shock free. Reviews report that the CTIC is not more efficient than a Rao contour, so it is a geometric convenience rather than a performance method.

## Dual bell

**What it optimizes.** Altitude compensation, with no moving parts.

**How it is generated.** A base bell of moderate area ratio joined at a deliberate wall inflection to an extension of much higher area ratio. At low altitude the flow separates cleanly and repeatably at the inflection; at high altitude it attaches through the extension.

**What it costs.** A transition that must be made to happen at the right altitude and to happen symmetrically. The side loads during transition are the design problem.

## Plug and aerospike

**What it optimizes.** Altitude compensation through an unconfined outer boundary, and package length.

**How it is generated.** SP-8120 describes the design as running backwards: start from the Mach line of an ideal exit flowfield, where the Mach number is constant and the flow is axial, and work upstream along the expansion surface. Then truncate to the desired length. The transonic flowfield is not computed, and the resulting difference between the design and actual flowfields is not significant for overall efficiency.

**What it costs.** A base. The truncation leaves a recirculating region whose pressure adds to thrust and whose thermal environment is severe. Base pressure, and how secondary flow is introduced into the base, dominates the design. Direct optimization of a truncated plug has not been developed; SP-8120 notes that truncated ideal plug nozzles outperform optimum plugs designed on a zero base pressure assumption.

**Where it stands.** Not operational as of SP-8120, and still not as of today.

## Choosing between them

| Family | Optimizes | Interior | Minimum length | Typical use |
|---|---|---|---|---|
| Conical | nothing | shock free if the tangency is clean | none | small engines, low area ratio |
| Ideal | uniform axial exit | shock free | none, but impractically long | reference only |
| Truncated ideal | inherited from ideal | shock free | none | high area ratio, short length, upper stages |
| Thrust-optimized contour | axial thrust at fixed length and area | internal shock | grows with area ratio | the performance benchmark |
| Thrust-optimized parabola | approximates the TOC | internal shock | inherits the TOC chart | most flight bells |
| Compressed truncated ideal | envelope length | shock introduced by compression | none | packaging |
| Dual bell | altitude compensation | separation at a designed inflection | not applicable | research |
| Plug and aerospike | altitude compensation, package length | shock free on the spike | not applicable | research |

The ordering by performance at equal length and area ratio is TOC first, TOP a fraction of a percent behind, TIC about a quarter of a percent behind that, conical last. The ordering by ease of generation is the reverse. Reported figures put the gain from length-constrained optimization at 0.5 to 1 percent in thrust at equal length or weight, and a TIC at the same area ratio as a parabolic baseline delivers nearly identical thrust and specific impulse while running roughly 10 percent longer.

**What NOVA measures reproduces the lower half of that ordering and not the top of it.** The parabola beats the truncated ideal contour at every design point swept, by 0.05 to 0.83 percent, which is the quarter of a percent SP-8120 quotes. The searched contour does not beat the parabola: it trails at most points and leads at one.

That is less surprising than it first reads. A directly optimized wall is a parametrized family and cannot beat an unconstrained variational optimum, and Allman and Hoffman measured exactly that, landing 0.05 to 0.21 percent below Rao at every matched length they tested. The gap between a TOC as Rao defined it and a TOC as any solver actually builds one is the whole subject. [NozzleContourValidation.md](./NozzleContourValidation.md) carries the measurement and what it does and does not establish.

## The transonic starting line

Every characteristics method needs a line on which the flow is already supersonic and known. That line comes from a transonic solution near the throat, and it is the one part of a contour generator whose accuracy is set entirely by a choice made before any characteristic is drawn.

The solutions form a single series. Sauer (1944) is the first-order term. Hall (1962) extended it; Kliegel and Quan (1966) gave the series explicitly and showed their first-order throat conditions are identical to Sauer's and Hall's, and their second-order conditions identical to Hall's. The throat wall velocity for axisymmetric flow is

$$u(0,1) = 1 + \frac{1}{4R} + \frac{14\gamma + 15}{288 R^2} + O(R^{-3})$$

with R the throat wall radius of curvature normalized by the throat radius. All orders share the property that the throat conditions are independent of nozzle shape; only the behavior away from the throat plane depends on the wall.

Two consequences matter for a solver.

The series is ill-behaved at small R. Taken literally it maximizes near R = 1 and returns a subsonic throat wall velocity below about R = 0.5. Kliegel and Levine (1969) recast it in inverse powers of R + 1, which fixes the small-radius behavior and shifts the sonic line toward the divergent section. The Hall and Kliegel-Quan forms are reported to give favorable results only for R of about 1.5 or greater.

Retaining Sauer's term alone is a quantifiable choice. At R = 1.5 and gamma = 1.1475 the retained first-order term contributes 0.1667 to the normalized throat wall velocity and the first neglected term contributes 0.0479, so the dropped term is 29 percent of the retained correction.

**SP-8120's "29-term series" is not a term count on this series, and the two numbers must not be compared.** The monograph offers two acceptable routes. The first is a reference-streamline solution in the manner of Oswatitsch and Rothstein, implemented in a proprietary Pratt and Whitney program: a velocity distribution along a reference streamline is assumed, the power-series form of the compressible-flow equation is integrated numerically, and the wall is located by summing streamline mass flow until the requested flow is reached. That is an inverse method in which the wall falls out, and the monograph ties the term count to obtaining a close fit to the desired wall geometry rather than to order of accuracy. The second route is Kliegel and Levine (1969), which is the family the series above belongs to and the family NOVA is in.

**What NOVA offers, and what it does not.** The starting line is selectable through `transonicModel` over three options, all of which carry their throat condition into Sauer's spatial form by inverting its one constant:

| `transonicModel` | Throat wall velocity | Where it holds |
|---|---|---|
| `sauer` | `1 + 1/(4R)` | the default; first order, and what every NOVA result before this selector existed was solved on |
| `secondOrder` | `1 + 1/(4R) + (14 gamma + 15)/(288 R^2)` | the term Hall and Kliegel and Quan agree on, reported as favorable for R of about 1.5 or greater |
| `smallRadius` | the same two terms in inverse powers of `R + 1` | small throat radii, where the series in `R` misbehaves |

`smallRadius` is a rearrangement that reproduces the two published asymptotic terms at large curvature and stays finite and supersonic at small, in the manner Kliegel and Quan's Appendix B and Kliegel and Levine describe. It is not a transcription of either paper's own recast coefficients, which are not in the reference set, and the two would differ beyond second order.

**This does not close the gap, and the reason is worth stating precisely.** What the selector moves is the throat *condition*. Throat conditions are the part of the series that is independent of nozzle shape, which is why they transfer cleanly into another solution's spatial form. The *shape* of the sonic line away from the throat plane remains Sauer's regardless of how many terms go into the anchor, and the shape is what a starting line is actually drawn from.

**Nor can the gap be closed by carrying more terms.** Kliegel and Levine concluded that the series they employ does not converge for higher approximations, which is recorded in NASA AED-R-71-10. Closing the row means a sonic-line field rather than a longer expansion, and the successor method that report names, specifying a centerline function and representing the dependent variables by a finite series, is where such a field would come from.

So what this row gains is narrower than it looks: the choice becomes explicit and selectable rather than silent, the size of the simplification becomes a measured number rather than a citation, and the throat entrant arc becomes safe to open to the smaller values SP-8120 prefers. The row itself stays open.

## Cross-reference against other axisymmetric characteristics implementations

Contour generators that solve the axisymmetric method of characteristics differ from one another along five axes, and the axes are worth naming because they are the questions to ask of any of them, NOVA included.

**The starting line.** Where does supersonic flow begin, and how is it known there? The choices run from a straight sonic line through Sauer's first-order solution to a high-order series. This is where the largest unforced error usually lives, because everything downstream is marched from it.

**The unit process.** Whether the compatibility relations are integrated in a velocity formulation or a Prandtl-Meyer formulation, whether the coefficients are evaluated at the upstream point or averaged along the characteristic, and how many corrector passes are taken. Averaged coefficients with iteration are second-order accurate; a single upstream evaluation is first-order.

**How the wall is constructed.** An ideal or truncated ideal contour draws the wall as a streamline through a solved mesh. A thrust-optimized contour solves for the wall as part of an optimization. A parabolic contour draws the wall first and never solves for it at all.

**The gas model.** Perfect gas at a single ratio of specific heats, perfect gas with a frozen exit gamma, equilibrium properties, or coupled finite-rate kinetics.

**What terminates the solve.** Area ratio, length, exit Mach number, exit pressure, or the end of the mesh. This choice decides which of the requested design parameters is binding and which are outputs, and it is the axis most often left implicit.

Four implementations for comparison:

| Implementation | Starting line | Wall construction | Gas model | Terminates on |
|---|---|---|---|---|
| TDK, the JANNAF standard | series-form transonic solution | reads a supplied contour; contour design is a separate module | coupled finite-rate kinetics, plus a boundary layer module | supplied geometry |
| IMOCND (NASA LAR-16744-1) | uniform or non-uniform supersonic inflow, supplied | streamline through the mesh, for shock-free uniform exit | irrotational potential flow; the run stops if a shock forms | uniform exit achieved |
| Young (Auburn, 2012) | not stated in the published abstract | full characteristics solution, driven by an optimized wall pressure distribution | finite-rate chemistry coupled to the characteristics solve | a specified performance goal |
| NOVA | Sauer by default, selectable to second order or a small-radius rearrangement; the throat condition only, on Sauer's spatial form | all three: streamline through the mesh (TIC), prescribed wall marched forward (TOP), prescribed wall searched by direct optimization (TOC) | perfect gas at chamber gamma | area ratio, by truncation (TIC) or by construction (TOP and TOC) |

Two observations follow. First, NOVA sits at the simple end of every axis except wall construction, where it now covers all three constructions the reference codes use between them. That is a coherent position for a design tool: the contour a full characteristics solve produces is not very sensitive to the gas model, which is exactly why Rao's parabolic approximation works across propellant combinations at all.

Second, the axis where simplicity is least defensible is still the starting line. NOVA carries at most two terms of its series, and carries them as a throat condition rather than as a field, so the sonic line's shape is Sauer's under every option. The selector makes the choice explicit and measurable. It does not make it the recommended practice, and the validation document reports it that way.

## What NOVA builds

NOVA generates three contoured families and a cone, selected by `divergingSectionType`.

| Family | Token | How the wall is fixed | Free parameter |
|---|---|---|---|
| Truncated ideal | `tic` (alias `rao`) | streamline through a solved mesh, then truncated to the requested area ratio | the design area ratio the ideal contour is run to before the cut |
| Thrust-optimized parabola | `top` | drawn from the chart angles, then marched | none; the area ratio and length are exact by construction |
| Thrust-optimized contour | `toc` | searched over a cubic Bezier by direct optimization | four design variables, bounded |
| Conical | `cone` (alias `conical`) | a straight wall at a fixed 15 degree half angle | none; the half angle is fixed |

The long spellings are accepted as aliases in either the American or the British form, and one resolver maps every accepted spelling to a canonical family, so an unrecognized value is rejected at load rather than falling through to a default.

Within the contoured families, the specific choices are:

| Element | NOVA | Reference practice |
|---|---|---|
| Transonic starting line | Sauer by default; `secondOrder` and `smallRadius` selectable, each carrying its throat condition on Sauer's spatial form | Either a reference-streamline inverse solution, whose 29 terms at a radius ratio of 1.5 buy a close fit to the requested wall, or the method of Kliegel and Levine (SP-8120 section 3.1.1.1) |
| Throat entrant arc | 1.5 throat radii by default, set by `throatInletCurvature`, required above 0.6 | 1.5 is the commonly used value; SP-8120 prefers about 1.0 for efficiency, and requires above 0.6 |
| Throat exit arc | 0.382 throat radii by default, set by `throatOutletCurvature` | Rao's preferred throat geometry, the same value used in the TOP construction |
| Initial wall angle | a fraction of the Prandtl-Meyer angle at the design exit Mach number, set by `initialWallAngleFraction`, one quarter by default. Read by the truncated ideal contour only | Rao throat assumption |
| Gas model | perfect gas at a single chamber gamma | equilibrium gas properties (SP-8120); constant specific heat is recommended only for the transonic solution |
| Truncation criterion | see [NozzleContourValidation.md](./NozzleContourValidation.md) | truncate to the desired area ratio (SP-8120, Ahlberg et al.) |
| Internal shock | detected from the wall characteristic envelope and captured as a weak shock, with the stagnation pressure loss carried downstream as a per-streamline debit | a rotational characteristics solve carrying entropy from streamline to streamline |
| Boundary layer | compressible integral turbulent layer on the finished wall: displacement thickness offsets the wall, skin friction debits the thrust. Laminar and transitional regions are not covered, and it does not couple back into the regenerative jacket's own wall temperature | displacement thickness computed and the wall offset point by point |
| Kinetics | not modeled; tracked in `experimental/coolingModelState.md` | finite rate, coupled, in the JANNAF standard method |

Three of these rows bound what NOVA can claim.

**The starting line row is open and stays open.** The selector makes the simplification explicit and measurable; it does not reach the recommended practice, for the reason set out under [the transonic starting line](#the-transonic-starting-line).

**The internal shock row is capture, not a rotational solve.** The jump is applied across a fitted front and the loss carried as a stagnation pressure debit, while the characteristics within each region stay isentropic. That is defensible at the shock strengths a bell produces, where the normal Mach number is barely above one and the entropy rise is third order in shock strength. A solve that carried entropy properly would put a Crocco term in the compatibility relations, which is a different solver rather than a better shock treatment.

**The gas model and kinetics rows are untouched by this work and are tracked elsewhere**, under "Variable-property characteristics solve" and "Finite-rate chemistry" in `experimental/coolingModelState.md`. A perfect-gas characteristics solve with a bolted-on boundary layer is the aerodynamic core of the standard method with the chemistry removed and the viscous correction approximated. For scale, the JANNAF standard code TDK predicts delivered vacuum specific impulse to within 0.12 to 1.9 percent of experiment with all of it included.

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
