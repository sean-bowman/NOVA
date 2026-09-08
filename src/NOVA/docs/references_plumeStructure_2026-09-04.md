# Plume Structure References

Sources gathered to replace NOVA's plume extension with correlations that can be traced and checked. Collected 2026-09-04.

The question driving the search: what is the minimum set of published correlations needed to place the jet boundary, the shock cell spacing and the Mach disk of a rocket exhaust plume, given a nozzle exit state that NOVA already computes?

These back the plume correlations in `src/NOVA/Nozzle.py` (`Nozzle.plumeStructure`), which sit beside the method-of-characteristics solver they will eventually be driven by.

---

## Prandtl (1904) shock cell length, and Pack's correction

- **URL:** <https://journals.sagepub.com/doi/10.1260/1475-472X.9.1-2.207> (Powell, *On Prandtl's Formulas for Supersonic Jet Cell Length*, Int. J. Aeroacoustics 9, 2010)
- **Accessed:** 2026-09-04
- **Relevance:** Establishes the shock cell spacing formula NOVA's old code cited, and the conditions under which it holds. Needed to decide whether the existing implementation was merely mis-parameterised or fundamentally misapplied.
- **Key findings:**
  - Prandtl's 1904 result for the cell length of an almost perfectly expanded circular supersonic jet is `λ = 1.306 · d · sqrt(M² − 1)`, where `d` is the **jet** diameter and `M` the **mean unperturbed jet** Mach number.
  - The coefficient 1.306 comes from taking only the **first term** of the series solution. Pack computed up to 40 terms and obtained **1.22**.
  - The formula is a small-perturbation (linearised) result. It is valid for weakly imperfectly expanded jets and predicts the **first** cell well.
  - It cannot capture the downstream shortening of cells caused by viscous dissipation, so an average spacing taken from it runs long compared with experiment.

## Ashkenas and Sherman (1966) Mach disk location

- **URL:** <https://www.cambridge.org/core/journals/journal-of-fluid-mechanics/article/experimental-and-numerical-investigation-of-inertial-particles-in-underexpanded-jets/FD4B67B1E32FF8AA5FC745CEC93F856C>
- **Accessed:** 2026-09-04
- **Relevance:** The dominant feature of a strongly underexpanded plume is the Mach disk, which NOVA's old model omitted entirely. This is the standard correlation for its axial position.
- **Key findings:**
  - `z_m = 1.34 · r* · sqrt(p_0 / p_c)`, with `r*` the effective **sonic (throat)** radius, `p_0` the stagnation pressure and `p_c` the ambient back pressure. Equivalently `x_M / D* = 0.67 · sqrt(NPR)`.
  - The location scales as the **square root of the stagnation-to-ambient pressure ratio**, confirmed both experimentally and numerically.
  - Very weakly dependent on the ratio of specific heats.
  - Reported coefficients across sources fall in the 0.64 to 0.67 band (radius form 1.28 to 1.34).
  - Note the scaling variables: throat diameter and **chamber stagnation** pressure, not exit diameter and exit pressure.

## Crist, Sherman and Glass (1966) Mach disk onset

- **URL:** <https://www.semanticscholar.org/paper/Study-of-the-highly-underexpanded-sonic-jet.-Crist-Glass/6d00cf121947a0b5749fadc356ea12223baf4496>
- **Accessed:** 2026-09-04
- **Relevance:** Sets the threshold below which a Mach disk does not form, so the model knows when to switch between a regular reflection (cell train only) and a Mach reflection.
- **Key findings:**
  - Mach disk formation observed at `NPR ≈ 3.9`.
  - Gives a method for computing the position of the first normal shock behind a highly underexpanded nozzle.
  - Describes the mechanism: expansion fans form at the lip, reflect as weak compression waves, and coalesce into the intercepting (barrel) shock.

## Mach disk onset threshold, modern survey

- **URL:** <https://pubs.aip.org/aip/pof/article/34/11/116125/2848522/Onset-conditions-for-Mach-disk-formation-in> (*Onset conditions for Mach disk formation in underexpanded jet flows*, Physics of Fluids 34, 2022)
- **Accessed:** 2026-09-04
- **Relevance:** Quantifies the spread in the onset threshold, which sets how much confidence the regime switch in the model deserves.
- **Key findings:**
  - Reported transition NPR: 3.78 (Antsupov 1974), 3.9 (Crist 1966), 3.67 (Addy 1981), 3.79 (Lee 2004).
  - Recent direct numerical simulation (Muraoka and Hiejima 2022) puts the transition lower, around **3.08 to 3.12**.
  - The threshold is therefore uncertain at roughly the 20 % level; a model should not treat it as sharp.

## Tam and Tanna fully expanded (equivalent) jet diameter

- **URL:** <https://ntrs.nasa.gov/api/citations/20210024918/downloads/TM-20210024918.pdf> (Schindler, Castner and Zaman, *A Study of Highly Underexpanded Supersonic Jets in Subsonic Crossflow*, NASA/TM-20210024918, February 2022, Eq. 6)
- **Accessed:** 2026-09-04
- **Relevance:** The shock cell formula is written in terms of the fully expanded jet diameter, not the nozzle exit diameter. This is the standard conversion, and getting it wrong is the single largest error in the old NOVA implementation.
- **Key findings:**
  - `d_j / d = [ (1 + ½(γ−1) M_j²) / (1 + ½(γ−1) M_e²) ]^{(γ+1)/(4(γ−1))} · (M_e / M_j)^{1/2}`
  - `M_e` is the nozzle exit Mach number, `M_j` the fully expanded jet Mach number, attributed to Tam and Tanna.
  - Follows from mass conservation between the exit plane and the fully expanded state under isentropic flow, so it reduces to `d_j = d` when `M_j = M_e`.
  - The same report notes that four published jet trajectory correlations were all inadequate for its conditions without refitting, a useful caution about the transferability of plume correlations.

## Love, Grigsby, Lee and Woodling (1959), NASA TR R-6

- **URL:** <https://ntrs.nasa.gov/citations/19980228067> (full text: <https://archive.org/stream/nasa_techdoc_19980228067/19980228067_djvu.txt>)
- **Accessed:** 2026-09-04
- **Relevance:** The foundational experimental and theoretical treatment of axisymmetric free jets, and the source for jet boundary shape and curvature rather than just cell spacing.
- **Key findings:**
  - Title: *Experimental and Theoretical Studies of Axisymmetric Free Jets*, NASA Technical Report R-6, Langley Research Center, 1959.
  - Covers jets from sonic and supersonic nozzles into still air and into supersonic streams.
  - For jets into still air, treats the effect of **jet Mach number, nozzle divergence angle and jet static pressure ratio** on jet structure, jet wavelength, and the **shape and curvature of the jet boundary**.
  - Establishes nozzle exit divergence angle as a primary variable for boundary inclination, which a Prandtl-Meyer-only estimate omits.

## Mach disk diameter scaling

- **URL:** <https://arxiv.org/html/2608.18923> (*Mach-disk formation and shock-structure transitions in underexpanded coflowing jets*)
- **Accessed:** 2026-09-04
- **Relevance:** Needed to draw the Mach disk at a defensible size rather than a token line.
- **Key findings:**
  - Empirical fit from that study: `D_MD / D_e = 1.78 · log10(NPR) − 0.98`, R² = 0.99.
  - The fit extrapolates to zero disk diameter at `NPR ≈ 3.57`, consistent with the onset thresholds above.
  - Fitted for coflowing jets; the coflow is weak but this is not a still-air correlation, so it carries more uncertainty than the location correlation.

---

## What these sources do and do not support

Supported, with traceable formulas: fully expanded jet Mach number and diameter, shock cell spacing for weakly imperfectly expanded jets, Mach disk axial location, Mach disk onset threshold, initial jet boundary inclination from Prandtl-Meyer turning plus nozzle divergence angle.

Not supported by anything found: a two-dimensional Mach and pressure field inside the plume. Every source treats the field either experimentally or by method of characteristics / CFD. There is no correlation that yields an interior flowfield, so any code producing one from closed-form expressions is drawing a picture, not solving a flow.

---

# Part 2: MOC plume interior

Sources gathered 2026-09-04 as a source of truth for implementing the method of characteristics in the plume, after three attempts converged on an architecture that could not be validated against anything external.

## Vick, Andrews, Dennard and Craidon (1964), NASA TN D-2327

- **URL:** <https://ntrs.nasa.gov/api/citations/19640013118/downloads/19640013118.pdf>
- **Title:** *Comparisons of Experimental Free-Jet Boundaries with Theoretical Results Obtained with the Method of Characteristics*, NASA Technical Note D-2327, Langley Research Center, June 1964
- **Accessed:** 2026-09-04
- **Relevance:** This is the source of truth. It gives the complete characteristic-network algorithm for a free jet, the FORTRAN that implements it, and schlieren-validated boundary coordinates to check an independent implementation against. It is the single reference the NOVA plume MOC work should be built and validated on.
- **Key findings:**

  **Architecture.** The net is "a lattice point-type structure **requiring no iteration**, machine computed in a **point-to-point** calculation procedure". Computation starts from the leading characteristic plus a series of two-dimensional expansion rays originating at the nozzle lip.

  **Assumptions:** constant ambient pressure and hence a constant Mach number boundary; constant gamma; isentropic flow throughout.

  **Five distinct point solutions** are required, and this is the part a naive implementation misses:
  1. general points
  2. points on the jet boundary
  3. **intersection of characteristic lines of the SAME family, indicating the presence of an internal shock**
  4. point adjacent to the axial centre line
  5. points on the centre line

  **Line taxonomy.** Type A lines originate at the nozzle lip and form the corner expansion fan. Type B lines originate on the leading characteristic or the diametrically opposite lip. Type C lines are reflected rays: B lines strike the boundary and reflect as though from a physical surface. Coalescence of those reflected compression waves forms the internal shock.

  **General-point equations** (working below the centre line, A the outer/first-family point, B the inner/second-family point, C the new point):
  - `dy/dx = (y_C - y_A)/(x_C - x_A) = tan(theta_A + mu_A)`  (C1)
  - `dy/dx = (y_C - y_B)/(x_C - x_B) = tan(theta_B - mu_B)`  (C2)
  - `x_C = [x_A tan(theta_A+mu_A) - y_A + y_B - x_B tan(theta_B-mu_B)] / [tan(theta_A+mu_A) - tan(theta_B-mu_B)]`  (C3)
  - `y_C = (x_C - x_A) tan(theta_A+mu_A) + y_A`  (C4)

  **Compatibility relations**, velocity form, credited to ref. 32 p. 264:
  - first family:  `dV_A/V_A - dtheta_A tan(mu_A) - l_A dx_A/y_A = 0`  (C5)
  - second family: `dV_B/V_B + dtheta_B tan(mu_B) - m_B dx_B/y_B = 0`  (C6)
  - non-dimensionalised by the limiting velocity, `W = V/V_limiting`, with `dtheta_B = dtheta_A + theta_A - theta_B`

  Note `dV/V - dtheta tan(mu) = 0` rearranges to `dtheta = cot(mu) dV/V`, which is the same relation NOVA's own `axisymmetricMethodOfCharacteristics` uses in the form `dtheta = (cot(mu)/V) dV`. The two formulations agree; only the source-term bookkeeping differs.

  **Initial turning angle at the lip:** `alpha_N = nu_1 - nu_N + theta_N`, where `nu_1` corresponds to the jet-boundary Mach number and `nu_N` to the nozzle-exit Mach number. This confirms the formula already used in `Nozzle.plumeStructure`.

  **Leading characteristic (Appendix A):**
  - `nu_centreline = nu_N + 2 theta_N`  (A1)
  - `R = C [1 + (2/(gamma-1))(1/M^2)]^((gamma+1)/(4(gamma-1))) M^(1/(gamma-1))`  (A2)
  - `x = R cos(theta) - R_N cos(theta_N)`  (A3), `y = -R |sin(theta)|`  (A6)

  **Worked numeric check:** for `Mj = 5.0`, `theta_N = 15 deg`, `gamma = 1.4`, the leading characteristic meets the centre line at `nu = 106.92 deg` and `M = 12.02`. An independent implementation must reproduce this.

  **Validation targets — maximum jet boundary**, the numbers to check a plume MOC against:

  | Mj | theta_N | pj/p_inf | (r/rj)max | x/rj at max |
  |---|---|---|---|---|
  | 1.0 | 0 deg | 45,000 | 450 | 1,300 |
  | 5.0 | 15 deg | 8,143 | 225 | 1,050 |
  | 4.79 | 26.5 deg | 2,926 | 188 | 720 |

  Maximum boundary size varies almost linearly with pressure ratio on log-log coordinates, so intermediate cases can be interpolated. Jet boundary coordinates in non-dimensional `x/rj`, `r/rj` are tabulated for `Mj = 1` at `pj/p_inf` of 20 and 45,000 (figure 7), and boundaries are plotted for all four nozzles (figures 8a-8g).

  **Riemann wave (Mach disk):** location `l/dj` and diameter `S/dj` both vary near-linearly with pressure ratio on log-log coordinates. At `pj/p_inf = 30,000` the shock diameter is about 100 nozzle diameters, roughly 30 % of the maximum plume diameter. Lower ambient pressure moves the shock closer to the exit at a given pressure ratio. At low pressure ratios the Riemann wave sits downstream of the maximum plume diameter; at high pressure ratios it sits upstream of it.

  **Maximum Prandtl-Meyer turning** (relevant to how far the lip fan can turn): 130.45 deg at gamma = 1.4, 203 deg at gamma = 1.20, 243 deg at gamma = 1.15. Initial turning angles at or beyond 90 deg are normal for rocket exhaust.

  **FORTRAN source** for the leading characteristic line, the corner expansion ray program (P-5433) and the characteristic network is printed in the appendices.

## What this changes about the NOVA attempt

Three concrete corrections fall straight out of this reference, recorded here so the next attempt does not rediscover them:

1. **Same-family intersections are a point type, not a failure.** The prototype treats "characteristics crossed" as a termination condition. TN D-2327 treats it as solution case (3) and uses it to build the internal shock. That alone explains most of the early terminations seen in the underexpanded and overexpanded cases.

2. **The scheme is non-iterative and point-to-point on a lattice.** The prototype iterates 15 to 20 times per node with averaged properties. That is a different formulation and is not what the validated program does.

3. **Points adjacent to the centre line need their own solution**, separate from both general points and centre-line points. The prototype has no such case, and the axisymmetric source term is singular as `y -> 0`, which is exactly the region it omits.

## Still to obtain

Zucrow and Hoffman, *Gas Dynamics, Volume 2: Multidimensional Flow* (Wiley, 1977) is the standard textbook treatment of MOC unit processes and would complement TN D-2327 on the derivations. It is not freely available; ADS record at <https://ui.adsabs.harvard.edu/abs/1977nyjw.book.....Z/abstract>. TN D-2327 is self-contained enough to implement from without it. Part 3 carries a fuller entry and a second route to the same material.

# Part 3: Shock fitting, the internal shock and the Mach disk

Sources gathered 2026-09-05 for the second half of the plume interior: the recompression shock that TN D-2327 solves through `SAMFM`, and the Mach disk, which TN D-2327 describes but gives no algorithm for.

The question driving the search: a characteristics net that stays isentropic over-expands the plume core and closes the jet boundary early, landing roughly a factor of two low against TN D-2327. What is the minimum published basis for turning a same-family characteristic crossing into a discrete internal shock, and for locating and sizing the Mach disk from a solved characteristics field?

## Mach-disk formation and shock-structure transitions in underexpanded coflowing jets

- **URL:** <https://arxiv.org/html/2608.18923>
- **Accessed:** 2026-09-05
- **Relevance:** The only source found that states, in implementable terms, how to extract the Mach disk and the triple point from a solved inviscid characteristics field rather than from a correlation. It is the operative reference for the disk fitting step.
- **Key findings:**
  - The MOC solve is the steady, irrotational, isentropic potential equation for axisymmetric flow, tracking flow inclination and the Prandtl-Meyer function along the two characteristic families. This is the same formulation TN D-2327 uses.
  - **Disk location criterion:** the axial station on the jet centre line where the local axial Mach number first reaches sonic. This is computable directly from a centre-line march; it needs no correlation.
  - **Disk diameter criterion:** scan radially on a line just downstream of the disk. The triple point is the radial station where the axial Mach number becomes sonic, and the disk diameter is twice that radius.
  - **Triple point structure:** the embedded shock, also called the barrel or intercepting shock, forms where compression waves reflected from the jet boundary coalesce; the reflected shock leaves the triple point; the Mach disk is the near-normal segment on the axis that terminates the embedded shock; the slip line is the contact discontinuity from the triple point, appearing in a viscous jet as a thin annular shear layer.
  - **Regular versus Mach reflection:** the switch is the classical detachment condition. Where the turning the flow must accomplish exceeds the maximum turning available at the local Mach number, no attached oblique-shock solution exists and the reflection must be a Mach reflection carrying a disk. Rising pressure ratio promotes Mach reflection; coflow promotes regular reflection.
  - The coflow in this study is a real difference from a still-air rocket plume, so the reflection-transition boundary transfers with caution. The extraction criteria do not depend on it.

## Abbett, The Mach Disc in Underexpanded Exhaust Plumes

- **URL:** <https://ntrs.nasa.gov/citations/19700042060> (AIAA Paper 70-231); journal version <https://doi.org/10.2514/3.6212> (AIAA Journal 9, no. 3, 1971, pp. 512-514)
- **Accessed:** 2026-09-05
- **Relevance:** The original statement of the model that later plume codes locate the disk with. Named here because it is the antecedent every subsequent treatment cites, not because it was readable.
- **Key findings:**
  - The method divides the flow field into subregions and matches them; the NTRS record confirms this much and carries no abstract.
  - **Not obtained.** The AIAA full text is paywalled and returns HTTP 403 to automated retrieval, as does the NTRS entry beyond its citation record. The model is characterised second-hand through AEDC-TR-76-129 below.

## AEDC-TR-76-129, An Approximate Analysis of the Shock Structure in Underexpanded Plumes

- **URL:** <https://apps.dtic.mil/sti/pdfs/ADA030705.pdf>, HTML rendering at <https://apps.dtic.mil/sti/html/tr/ADA030705/index.html>
- **Accessed:** 2026-09-05
- **Relevance:** An approximate analytical model for the first cycle of the shock structure in an axisymmetric underexpanded plume, built on the same physical basis as Abbett's model. It is the closest thing found to a self-contained recipe for the disk.
- **Key findings:**
  - The disk location follows from coupling the flow near the disk to the reaccelerating transonic flow downstream of it, expressed as a local compatibility condition on the flow just behind the disk.
  - Scope is the first shock cycle of an axisymmetric underexpanded nozzle, which is the region a plume characteristics net resolves before the waves coalesce.
  - **Not obtained.** DTIC returns HTTP 403 to automated retrieval for both the PDF and the HTML rendering. Retrieval needs a manual browser session. The summary above is from the indexed abstract, not the report body.

## Mitchell, Honnery and Soria, The underexpanded jet Mach disk and its associated shear layer

- **URL:** <https://doi.org/10.1063/1.4894741>, Physics of Fluids 26, 096101, 2014
- **Accessed:** 2026-09-05
- **Relevance:** Experimental structure of the region a characteristics march cannot enter. It bounds what an inviscid solve may claim about the flow behind the disk.
- **Key findings:**
  - High-resolution planar PIV of an axisymmetric underexpanded jet from a convergent nozzle.
  - The annular shear layer generated by the slip line from the triple point persists across several shock cells downstream, so the slip line is not a local feature that decays within one cell.
  - **No evidence was found for a recirculation region behind the Mach disk**, contrary to an earlier hypothesis. A solver that stops its march at the disk and treats the slip line as an internal boundary is therefore not omitting a recirculating pocket.
  - The external helical screech structure forces oscillation of the disk, which is a viscous and unsteady effect entirely outside an inviscid steady formulation.

## Salas, The Numerical Calculation of Inviscid Plume Flow Fields

- **URL:** <https://ui.adsabs.harvard.edu/abs/1974STIN...7513313S/abstract>, AIAA Paper 74-523, June 1974
- **Accessed:** 2026-09-05
- **Relevance:** The standard citation for discrete shock fitting in an inviscid plume field, and the antecedent for treating the embedded shock as a tracked discontinuity rather than a smeared region.
- **Key findings:**
  - Widely cited as the foundational treatment of numerically computed inviscid plume flow fields with shocks carried as discontinuities.
  - **Full text not obtained.** Only the citation record was reachable. Recorded so the provenance of the shock-fitting approach is traceable, not as a source of equations.

## Smith, Improvement of Rocket Engine Plume Analysis Techniques

- **URL:** <https://ntrs.nasa.gov/citations/19820010442>, NASA-CR-167516, Lockheed Missiles and Space Co., 1982
- **Accessed:** 2026-09-05
- **Relevance:** Establishes what JANNAF standard practice actually does about shocks in a plume, which bounds how much of this problem is reasonably closable with a characteristics net alone.
- **Key findings:**
  - RAMP2 is the refined Reacting and Multi-Phase code. It marches the nozzle from the throat through the exit plane and on into the plume.
  - Its shock treatment is a **shock capturing finite difference operator**, not shock fitting inside the characteristics net. The production standard switches numerical method rather than extending the characteristics scheme to carry discontinuities.
  - It interfaces directly with the JANNAF SPF code; a Level 2 analysis characterises the viscous plume with SPF/2 or RAMP2/LAMP and passes it to the Plume Impingement Program.
  - Reading for this work: fitting a discrete shock inside a characteristics lattice, which is what `SAMFM` does, is the older and narrower approach. It suits the first cells of an inviscid plume and is not what a general-purpose plume code relies on.

## Hoffman, accuracy of the numerical method of characteristics for axisymmetric steady supersonic flow

- **URL:** <https://www.sciencedirect.com/journal/journal-of-computational-physics>, Journal of Computational Physics, 1973
- **Accessed:** 2026-09-05
- **Relevance:** The step-size refinement in the NOVA free-jet net is a numerical device with no reference behind it. This is the published accuracy study for that question in this formulation.
- **Key findings:**
  - Accuracy studies of the numerical MOC for axisymmetric steady supersonic flow, by the co-author of the standard textbook treatment.
  - **Full text not obtained.** Recorded as the source to consult before defending any particular refinement criterion or step-size limit.

## Zucrow and Hoffman, Gas Dynamics, Volume 2: Multidimensional Flow

- **URL:** <https://ui.adsabs.harvard.edu/abs/1977nyjw.book.....Z/abstract>, Wiley, 1977
- **Accessed:** 2026-09-05
- **Relevance:** Standing gap from Part 2. It remains the standard textbook derivation of MOC unit processes, including the shock point and the free-pressure-boundary point, which TN D-2327 gives only as FORTRAN.
- **Key findings:**
  - Volume 2 places its emphasis on applying the method of characteristics to steady and unsteady multidimensional flow, deriving the characteristic equations for rotational flow from the governing equations for steady adiabatic inviscid flow.
  - **Still not freely available.** The related chapter treatment, *Flows with Shock Waves: Rotational Method of Characteristics*, appears as Chapter 20 of the *Handbook of Compressible Fluid Dynamics*, which is a second route to the same material.

## Love, Grigsby, Lee and Woodling (1959), NASA TR R-6, extracted for the divergent exit

- **URL:** <https://ntrs.nasa.gov/api/citations/19980228067/downloads/19980228067.pdf>, OCR text at <https://archive.org/stream/nasa_techdoc_19980228067/19980228067_djvu.txt>
- **Accessed:** 2026-09-05
- **Relevance:** Part 1 cites this report for jet boundary shape. It was read again here for one question the correlations cannot answer: how much the nozzle exit divergence angle changes the shock cell length. That decides whether a characteristics net can be trusted on a bell contour, whose exit diverges at eight to fifteen degrees.
- **Key findings:**
  - Conclusion 1, verbatim: *"Divergence angle of the nozzle (0 deg to 20 deg) has a small effect upon the primary wavelength of the jet. Existing methods for predicting the wavelength of an axisymmetric jet are inadequate above a jet static-pressure ratio of about 2. Semiempirical relations are presented which give fair predictions of experimental results for jet Mach numbers from 1 to 3."*
  - **Divergence angle is of secondary importance over 0 to 20 degrees.** The trend is a decrease in wavelength with increasing divergence, attributed to the rising shock losses and hence rising entropy that come with it, and the report notes that exceptions to the trend sit within experimental scatter.
  - **Existing wavelength methods fail above a jet static pressure ratio of about 2.** This is an independent experimental confirmation of the ceiling that a characteristics net can be held to, arrived at separately from any comparison against Prandtl.
  - Prandtl's formula is described as known to be in error, and Pack's correction of it as unsatisfactory except at very low pressure ratios. Neither is a strong reference; they are the only closed-form ones available.
  - The report tabulates an expansive flow field from characteristic calculations, table II, repeated for each nozzle. That is a direct reference for an interior field rather than for a scalar, and it has not yet been transcribed.
  - Increasing divergence angle sharply reduces the range of pressure ratios over which no Riemann wave forms, so a divergent exit brings on the Mach disk earlier than a parallel one.

### What this settles about the divergent exit

The free-jet net in `Nozzle.py` makes exit divergence a dominant effect rather than a secondary one. Measured against Prandtl's cell length at jet Mach 3 and a static pressure ratio of 1.5, it runs +9.0 per cent at a parallel exit, -24.6 per cent at five degrees and -34.3 per cent at eleven. TR R-6 says the true effect over that range is small.

Two contributions to that, separated by measurement:

- Part of it is the measure. Lip to first crest is not the primary wavelength. A steeply diverging exit throws the boundary out early and brings the first crest forward without changing the axial period of the wave structure, which is what the report measures between successive periodic features.
- The rest is the march itself. It cannot be measured as a period, because with divergence the net does not survive long enough to produce a second crest: the boundary falls from 1 139 points at a parallel exit to 92 at fourteen degrees under identical settings. A solver that collapses as the exit opens out cannot be held against an experiment that says the effect should be mild.

So TR R-6 does not widen the validated envelope. It narrows the question: the parallel-exit result stands, the pressure ratio ceiling of 2 is confirmed from a second and experimental direction, and the divergent exit is a defect to fix rather than a region merely lacking a reference.

The exit plane of a truncated ideal contour is the reason the question arises at all. It is not uniform. On the showcase nozzle the flow leaves at zero degrees and Mach 4.81 on the axis and at 14.1 degrees and Mach 4.04 at the wall, so handing the solver a single wall angle asks it to treat the whole exit plane as diverging at the steepest streamline in it. `Nozzle.plumeCharacteristicSeed` already returns the exit-plane profile that would replace that assumption.
---

## What these sources do and do not support

**Supported, with a traceable procedure.** Locating the Mach disk from a solved characteristics field, as the first centre-line station where the axial Mach number reaches sonic. Sizing it from the triple point, found by a radial scan just downstream. Deciding between regular and Mach reflection on the axis by the classical shock detachment condition, which `obliqueShockDeflection` in `Nozzle.py` already implements. Treating the slip line as an internal boundary and stopping the march at the disk, with experimental support that no recirculation region is being omitted.

**Supported by provenance only, not by equations in hand.** The Abbett compatibility condition. Both the original paper and the AEDC report that expands it sit behind access controls that automated retrieval cannot pass. The extraction criteria above do not depend on them, but a claim that a NOVA disk follows Abbett's model would not be defensible without reading them first.

**Contradicted by experiment.** The strength of the exit divergence effect on shock cell length. TR R-6 measures it as small over 0 to 20 degrees; the net makes it dominant, and additionally fails to survive a divergent exit long enough to resolve a second cell. `Nozzle.plumeField` refuses beyond half a degree of exit divergence for this reason, which excludes every bell contour.

**Not supported by anything found.** A derivation of how a same-family characteristic crossing becomes a discrete shock, how the shock point advances line to line, and how the entropy rise is carried through a net whose remaining points are isentropic. TN D-2327 gives this as FORTRAN only, in `SAMFM` and `TEST`. The production standard, RAMP2, sidesteps the question by switching to a shock-capturing finite difference operator. An implementation here is therefore a transcription of the listings, verifiable against the report's tabulated boundaries but not against an independent derivation.
