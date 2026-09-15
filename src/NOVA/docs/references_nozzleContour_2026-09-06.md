# Nozzle Contour References

Sources gathered to check NOVA's axisymmetric method-of-characteristics contour generator against published practice, and to establish what an independent reference for a truncated ideal contour actually is. Collected 2026-09-06.

The question driving the search: given a contour generator that solves the method of characteristics and then truncates, what published data fixes the answer it should produce, and where does its treatment of the transonic starting line, the truncation criterion and the exit-plane average stand against the reference method?

These back the contour generation described in `NozzleContour.md`, the taxonomy in `NozzleContourMethods.md`, and the comparison in `NozzleContourValidation.md`.

---

## NASA SP-8120, Liquid Rocket Engine Nozzles

- **URL:** <https://ntrs.nasa.gov/api/citations/19770009165/downloads/19770009165.pdf>
- **Accessed:** 2026-09-06
- **Relevance:** The NASA design criteria monograph for liquid rocket nozzles. It is the single source that defines the vocabulary NOVA uses (percent bell, truncated ideal, canted parabola), states the recommended practice for each step NOVA implements, and supplies the wall-angle chart against which a bell contour is checked. Everything else in this file is either cited by it or fills a gap it leaves.
- **Key findings:**
  - Percent bell is defined precisely: the length of the bell nozzle as a percent of the length of a 15 degree half-angle conical nozzle **having the same expansion area ratio**. The reference cone is tied to the delivered area ratio, not to a design-point area ratio computed separately.
  - The truncated ideal contour is described exactly as the method NOVA implements: design an ideal nozzle to a higher area ratio than required, then truncate it **to the desired area ratio**, at which point the correct nozzle length is obtained (section 2.1.2.1.2, citing Ahlberg et al.). The area ratio is the binding constraint and the length is the result.
  - The truncated ideal contour is classified as a **nonoptimum** contour. Its use is recommended where performance losses of the order of **0.25 percent** are tolerable, or where rigorous optimization methods do not exist, such as short nozzles at high area ratio.
  - Unlike the mathematical optimum, the truncated ideal method can be used to design a nozzle as short as desired. The mathematical optimum method fails below a minimum length that grows with area ratio.
  - Figure 5(b) gives the initial and final wall angles for the canted-parabola contour against area ratio and nozzle length. The monograph states that the region of that chart above an area ratio of about 50 is **extrapolated**, so any comparison at higher area ratio inherits that extrapolation.
  - Throat upstream wall: the wall radius to throat radius ratio should be kept greater than 0.6, and about 1.0 gives the best compromise between nozzle efficiency and throat surface area exposed near Mach 1. A ratio of 1.5 is identified as the commonly used value.
  - Transonic starting line, section 3.1.1.1 verbatim: *"Use a reference-streamline series-form transonic solution (e.g., ref. 4) **or the method of reference 5** to obtain a line along which supersonic flow properties are known ... Employ a 29-term series for the commonly used radius ratio of 1.5. Increase the number of terms for small approach radii **to obtain a close fit to the desired wall geometry**."* Use a constant specific heat for the transonic solution.
  - **The 29 terms belong to a different method family than the one NOVA implements, and the two term counts are not comparable.** Reference 4 is `PWA 2888, Suppl. 4`, a Pratt and Whitney program manual, and section 2.1.1.1 describes the method as reference 8's, Oswatitsch and Rothstein: the velocity distribution along some reference streamline is assumed, the power-series form of the compressible-flow equation is integrated numerically, and the wall is located by summing the flow in each streamline until the desired mass flow is attained. That is an **inverse** method in which the wall falls out of the solution, and the monograph states that the number of terms required depends on the wall geometry. The terms buy a close fit to the requested wall, not accuracy in a fixed expansion. Sauer, Hall and Kliegel-Quan are a different thing: an asymptotic series in inverse powers of the throat wall curvature, in which term count means order of accuracy.
  - **The manual is proprietary and was not obtainable**, so that branch of the recommendation is closed regardless of effort.
  - **The second branch is open, and is the family NOVA is already in.** Reference 5 is Kliegel and Levine (1969), below, which SP-8120 offers as an equally acceptable route. NOVA's `smallRadius` transonic model is an approximation of it.
  - Section 2.1.1.1 also records that existing transonic methods are limited to radius ratios of about 1.0 for accurate results, that a computer solution can reach 0.6, and that nozzle aerodynamic efficiency was found constant for upstream radius ratios from 1.5 down to 0.6.
  - Throat downstream wall: for conical divergence sections at a 15 degree half angle, experiment indicates the downstream radius ratio should not be made smaller than about 0.75, on heat transfer grounds.
  - Flow separation: the exit-to-ambient pressure ratio of 0.4 is described as an **early rule**. A fit of experimental data for short contoured nozzles over a broad range of area ratios gives `p_wall / p_amb = 0.583 (p_amb / p_c)^(-0.195)`, with `p_wall` the wall static pressure at separation and `p_c` the chamber total pressure.

## Rao (1958), Exhaust Nozzle Contour for Optimum Thrust

- **URL:** Jet Propulsion, vol. 28, no. 6, June 1958, pp. 377-382. Cited as reference 16 of NASA SP-8120.
- **Accessed:** 2026-09-06 (citation and secondary summaries; the article itself is behind a publisher paywall)
- **Relevance:** The origin of the optimum bell contour, and therefore of every published bell length quoted as a percent. NOVA does not implement this method, so its role here is to define what NOVA's contour is being compared against.
- **Key findings:**
  - The optimum contour follows from a variational-calculus maximization over a control surface, subject to a fixed length and exit area.
  - The resulting shape is insensitive to gas properties and to small departures from the optimum, which is what makes a single parabolic approximation usable across propellant combinations.
  - Lengths are reported as fractions of the 15 degree conical nozzle of the same area ratio, which is the convention that entered general use.

## Rao (1960), Approximation of Optimum Thrust Nozzle Contour

- **URL:** ARS Journal, vol. 30, no. 6, June 1960, pp. 561-563.
- **Accessed:** 2026-09-06 (citation and secondary reproductions of the chart)
- **Relevance:** The parabolic approximation to the 1958 optimum contour, and the source of the wall-angle chart that SP-8120 reproduces as figure 5. This is the practical anchor for a bell contour check, because it reduces a whole contour to two angles that can be measured on any generated wall.
- **Key findings:**
  - The bell is approximated by a skewed parabola, in modern terms a quadratic Bezier curve, tangent to the throat exit arc at the inflection point N and running to the exit point E.
  - The construction is fixed by two angles: the wall angle at the inflection point, theta_n, and at the exit, theta_e.
  - Throat geometry is a 1.5 throat-radius entrant arc and a 0.382 throat-radius exit arc. NOVA hardcodes both of these values.
  - Exit radius `Re = sqrt(eps) * Rt`, and nozzle length `Ln = f * (sqrt(eps) - 1) * Rt / tan(15 deg)` for a bell of length fraction f.
  - A representative point on the chart: an 80 percent bell at area ratio 70 has theta_n near 33 degrees and theta_e near 7 degrees.
  - A digitization of the chart in circulation gives, at area ratio 40, theta_n of 37.1, 31.0 and 29.5 degrees and theta_e of 13.5, 8.0 and 6.0 degrees for 60, 80 and 90 percent bell. That digitization is non-monotone in theta_n between area ratios 40 and 50 at 60 percent bell, so it carries at least one transcription error and is indicative rather than authoritative.

## Ahlberg, Hamilton, Migdal and Nilson (1961), Truncated Perfect Nozzles in Optimum Nozzle Design

- **URL:** ARS Journal, vol. 31, no. 5, May 1961, pp. 614-620. Cited as reference 14 of NASA SP-8120.
- **Accessed:** 2026-09-06 (citation, recovered through the SP-8120 reference list)
- **Relevance:** The primary reference for the truncated ideal contour, which is the family NOVA generates. It is the source SP-8120 points to for both the method and its performance relative to the mathematical optimum.
- **Key findings:**
  - The method: design an ideal, full-length, uniform parallel exit nozzle to an area ratio above the one required, then truncate to the required area ratio.
  - Performance differences between a truncated ideal contour and the mathematical optimum at the same length and area ratio are small, of the order of a quarter of a percent per SP-8120.
  - The truncated ideal method has no minimum length, which is why SP-8120 recommends it in exactly the regime where the optimum method fails.

## Kliegel and Quan (1966), Convergent-Divergent Nozzle Flows

- **URL:** <https://ntrs.nasa.gov/api/citations/19670009614/downloads/19670009614.pdf> (TRW Systems 02874-6002-R000, prepared under NASA contract NAS9-4358; the journal version is AIAA Journal 6(9), September 1968, pp. 1728-1734)
- **Accessed:** 2026-09-06
- **Relevance:** Gives the transonic throat solution as an explicit series in inverse powers of the normalized throat wall radius of curvature, with the first-order and second-order throat conditions written out. Sauer's solution is the first-order term, so this source is what quantifies the error of using Sauer alone at a stated throat curvature.
- **Key findings:**
  - The first-order throat conditions derived here are stated to be **identical to those obtained by Sauer and by Hall**. The solutions differ only away from the throat plane, through the dependence of the coefficients on the axial coordinate.
  - The second-order throat conditions are identical to Hall's. Both the first-order and second-order throat conditions are independent of nozzle shape and are therefore universally valid; the solution away from the throat depends on the shape at every order.
  - The axisymmetric throat wall velocity series is `u(0,1) = 1 + 1/(4R) + (14 gamma + 15) / (288 R^2) + O(R^-3)`, with R the throat wall radius of curvature normalized by the throat radius.
  - The series is ill-behaved at small R: taken literally it maximizes near R = 1 and returns a subsonic throat wall velocity below about R = 0.5, which is physically impossible. Appendix B gives a rational-fraction rewriting that matches the same terms at large R and behaves correctly at small R.
  - Consequence for a solver that retains only Sauer's term: at a normalized throat curvature of 1.5 the retained first-order term contributes `1 / (4 x 1.5) = 0.1667` to the normalized throat wall velocity, and the first neglected term contributes `(14 gamma + 15) / (288 x 2.25)`, which is `0.0479` at gamma = 1.1475. The dropped term is 29 percent of the retained correction.

## Kliegel and Levine (1969), Transonic Flow in Small Throat Radius of Curvature Nozzles

- **URL:** <https://arc.aiaa.org/doi/abs/10.2514/3.5355> (AIAA Journal, vol. 7, no. 7, July 1969, pp. 1375-1378). Cited as reference 5 of NASA SP-8120.
- **Accessed:** 2026-09-06
- **Relevance:** The recommended transonic starting-line method in SP-8120, and the correction that extends the Hall series into the small-curvature regime. Establishes the range over which the Sauer and Hall family is trustworthy.
- **Key findings:**
  - The series is recast in inverse powers of the normalized throat radius of curvature **plus one**, rather than of the radius itself, which is what removes the small-radius breakdown.
  - The Hall and Kliegel-Quan solutions give favourable results for throat radius curvature ratios of approximately 1.5 or greater. Below that they degrade and the reformulation is required.
  - Sauer's and Hall's sonic lines are nearly coincident because they share a coordinate system. The Kliegel and Levine sonic line is displaced towards the divergent section.
  - **The authors later concluded that the series they employ does not converge for higher approximations.** This is recorded in NASA AED-R-71-10, below, which also describes the construction as a wall contour represented by a series suggested by orthogonal toroidal coordinates, expanded in inverse powers of `R + 1`, reducing to Hall's solution at large `R` and continuing to give realistic results below one. **The consequence for NOVA is that this row cannot be closed by carrying more terms of this series**, in addition to not being closeable by the 29-term route, which belongs to a proprietary program in a different method family.

## NASA AED-R-71-10 (1971), transonic nozzle flow survey

- **URL:** <https://ntrs.nasa.gov/api/citations/19710024785/downloads/19710024785.pdf>
- **Accessed:** 2026-09-14
- **Relevance:** Found while establishing what SP-8120's transonic recommendation actually asks for. It is the source that closes off the "add more terms" route and names the successor method, which is what makes the transonic row a bounded question rather than an open-ended one.
- **Key findings:**
  - Characterizes the Kliegel and Levine approach as representing the wall contour by a series suggested by orthogonal toroidal coordinates, expanding in `1/(R + 1)`, and states the solution is essentially Hall's at large `R` while continuing to predict realistic results below one.
  - **States that Kliegel and Levine have concluded the series employed does not converge for higher approximations.**
  - Notes the general difficulty of the preceding methods as producing a number of terms "not necessarily matching the desired contour", which is the same property SP-8120 describes when it ties term count to fitting the wall geometry.
  - Names the successor: a special form of the Cauchy nozzle flow problem, specifying a centerline function and representing the dependent variables by a finite series in the independent variables, citing Hopkins and Hill (1966), AIAA J 4(8) 1337-1343, and **Levine and Coar, NASA CR-111104 (1970)**, which is openly available.

## Sauer (1944), General Characteristics of the Flow Through Nozzles at Near Critical Speeds

- **URL:** NACA TM 1147. Already cited in NOVA's `NozzleContour.md` as reference [2].
- **Accessed:** 2026-09-06 (citation)
- **Relevance:** The transonic starting line NOVA implements. Its standing is established by what the later series solutions say about it rather than by the paper alone.
- **Key findings:**
  - Sauer's result is the leading term of the series that Hall, Kliegel and Quan, and Kliegel and Levine later extended.
  - At the throat plane the Sauer conditions coincide with the higher-order solutions. The departure grows with distance from the throat plane, which is precisely where a starting line for a characteristics march is drawn.

## Rocket nozzles: 75 years of research and development

- **URL:** <https://www.ias.ac.in/article/fulltext/sadh/046/0076> (Sadhana, Indian Academy of Sciences, vol. 46, 2021)
- **Accessed:** 2026-09-06 (indexed summary; the full text did not return to an automated fetch)
- **Relevance:** A review that places the contour families in relation to one another and gives the relative performance figures a taxonomy needs.
- **Key findings:**
  - The families in practical use for real rocket nozzles are the truncated ideal contour, the thrust-optimized contour, the thrust-optimized parabolic approximation, and the compressed truncated ideal contour.
  - The highest performance for a given length and area ratio belongs to the thrust-optimized contour, closely approximated by the thrust-optimized parabola.
  - A truncated ideal contour gives significant length and weight reduction for a relatively small performance loss. At the same area ratio its thrust and specific impulse are almost identical to a parabolic baseline, and it is longer by roughly 10 percent.
  - Reported gains from length-constrained optimization are 0.5 to 1 percent in thrust at equal nozzle length or weight, depending on mixture ratio, chamber pressure and altitude.
  - The compressed truncated ideal contour was not found to be more efficient than the Rao contour.

## TDK, the JANNAF standard nozzle performance code

- **URL:** <https://ntrs.nasa.gov/citations/19860007470> (Engineering and programming manual: Two-dimensional kinetic reference computer program)
- **Accessed:** 2026-09-06
- **Relevance:** The state of practice, and therefore the boundary of what a contour tool of NOVA's scope can reasonably claim. It also fixes the accuracy a nozzle performance prediction is expected to reach.
- **Key findings:**
  - TDK is the reference program for the JANNAF liquid rocket thrust chamber performance prediction methodology.
  - It carries a two-dimensional method-of-characteristics solver with fully coupled finite-rate kinetics, a parabolised Navier-Stokes solver, and a mass-addition boundary layer module.
  - Reported accuracy: delivered vacuum specific impulse predicted to within 0.12 to 1.9 percent of experimental data.
  - What that scope implies for a comparison: kinetics, the boundary layer and its displacement thickness, and multi-zone chemistry all sit inside the standard method and outside an inviscid perfect-gas characteristics solve.

## The Thrust Optimized Parabolic nozzle (Newlands)

- **URL:** <https://www.aspirespace.org.uk/downloads/Thrust%20optimized%20parabolic%20nozzle.pdf>
- **Accessed:** 2026-09-06
- **Relevance:** A worked, reproducible statement of the Rao parabolic construction with explicit equations. Useful because it is checkable end to end, and because it names its own source as SP-8120 and Rao 1958 rather than presenting the chart as original.
- **Key findings:**
  - Full construction: entrant arc `x = 1.5 Rt cos(theta)`, `y = 1.5 Rt sin(theta) + 2.5 Rt` over -135 to -90 degrees; exit arc `x = 0.382 Rt cos(theta)`, `y = 0.382 Rt sin(theta) + 1.382 Rt` over -90 to `theta_n - 90` degrees; then a quadratic Bezier from N to E with the control point at the intersection of the tangents at theta_n and theta_e.
  - Efficiency against length: an 85 percent bell reaches about 99 percent nozzle efficiency, and going to 100 percent gains only a further 0.2 percent. Below 70 percent, efficiency suffers noticeably. This is the reasoning behind the conventional 80 percent choice.
  - The reproduced chart is labeled as extrapolated above an area ratio of 50, agreeing with SP-8120.

## Reference engine geometry

- **URL:** <https://everything.explained.today/RS-25/> and <http://www.astronautix.com/r/rd-180.html>
- **Accessed:** 2026-09-06
- **Relevance:** Public geometry for the engines used as end-point comparisons. Recorded with its limitations, because the quality of this data rather than the quality of the solver sets how much a comparison against a flight engine can settle.
- **Key findings:**
  - RS-25: nozzle length 121 in, throat diameter 10.3 in, exit diameter 90.7 in, published expansion ratio about 69.5.
  - Those RS-25 diameters imply a geometric area ratio of 77.5, which disagrees with the published 69.5 by 12 percent. At least one of the three quoted dimensions is not the quantity it appears to be, and a comparison has to state which value it used.
  - RS-25 from the quoted dimensions: the 15 degree cone to the same exit radius is 3.81 m against a nozzle length of 3.07 m, giving 80.6 percent of the cone. This is consistent with the engine being described as an 80 percent bell and is the most useful single check in the set.
  - RD-180: chamber pressure 256.6 bar and area ratio 36.4 are published. The nozzle contour and the throat and exit diameters are not. Any RD-180 comparison is limited to performance quantities.
  - Vulcain 2: nozzle exit diameter 2.10 m, with area ratio quoted variously as 58.5 and 61.5 across sources.
  - Merlin 1D Vacuum: expansion ratio 165. Geometry is manufacturer material rather than a technical publication.
  - F-1: overall expansion ratio 16, regeneratively cooled to the 10:1 plane with a turbine-exhaust-gas-cooled extension to 16:1. Diameters were not recovered from a citable source in this pass.

---

## What these sources support and what they do not

**Supported.** The definition of percent bell and the 15 degree cone reference. The truncated ideal contour as a named method with a named primary reference and a stated performance penalty against the mathematical optimum. The Rao throat construction NOVA hardcodes. The wall-angle chart as a comparison target, with its extrapolated region marked. The classification of Sauer's solution as the first term of a series whose next term is computable, and therefore a quantified statement of what Sauer omits at a given throat curvature. The recommended practice for the transonic starting line. A separation criterion better than the 0.4 rule.

**Not supported.** A validated axisymmetric characteristics solution to compare node by node: no source in this set publishes a tabulated flowfield for a rocket bell that could serve as a point-by-point reference. Wall-angle data above an area ratio of 50, which is extrapolated in the only chart available. Contour coordinates for any flight engine, since none of the engine sources publishes a wall table, so engine comparisons are limited to end-point dimensions and performance. And the accuracy of a contour generated with a single ratio of specific heats against one generated with equilibrium gas properties, which is what the reference method uses.
