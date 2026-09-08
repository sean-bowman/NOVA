# References: temperature-dependent wall-alloy properties

Sources consulted while extending `src/NOVA/materials.py` from room-temperature-only data to temperature-resolved curves, and the record of which ones could not supply what was wanted.

Accessed 2026-09-08 unless noted otherwise.

---

## NIST Cryogenic Material Properties Database

- **URL:** <https://trc.nist.gov/cryogenics/materials/materialproperties.htm>
- **Accessed:** 2026-09-08
- **Relevance:** The single most useful source found. NOVA's grids all began at room temperature while regenerative coolant inlets sit near 20 K, so every jacket was being sized on a clamped room-temperature conductivity. This database supplies critically evaluated curve fits from 4 K to 300 K with stated fit errors, which is exactly the missing range.
- **Key findings:**
  - Covers 43 materials. Five of NOVA's ten wall alloys are among them: OFHC copper (C10100/C10200), type 316 stainless, 6061-T6 aluminium, Ti-6Al-4V and Inconel 718.
  - Thermal conductivity and specific heat use `log10 y = sum_k c_k (log10 T)^k` to eighth order; linear expansion and Young's modulus use `y = sum_k c_k T^k` with a constant held below a stated `Tlow`.
  - Linear expansion is tabulated as `(L - L293)/L293 x 1e5`, so the instantaneous coefficient is `1e-5` times the derivative and the mean from 293 K follows from the difference.
  - Stated fit errors are 0.5 % to 2 % on conductivity and 1.1 % to 5 % on expansion, quoted per material.
  - **The fits diverge outside 4-300 K.** Extrapolated to 600 K the Ti-6Al-4V expansion fit returns a *negative* mean coefficient and the 6061-T6 fit falls to 13.2e-6/K. They are usable strictly below 300 K.
  - The Inconel 718 page is reachable only through a misspelled path, `/cryogenics/materials/Iconel 718/`.

## NIST cryogenic properties: OFHC copper

- **URL:** <https://trc.nist.gov/cryogenics/materials/OFHC%20Copper/OFHC_Copper_rev1.htm>
- **Accessed:** 2026-09-08
- **Relevance:** Copper is the chamber wall material family, so its cryogenic behaviour matters most. It also turned out to be the one alloy whose conductivity moves in the opposite direction to the rest.
- **Key findings:**
  - Conductivity uses a rational form, `k = 10^[(a + cT^0.5 + eT + gT^1.5 + iT^2)/(1 + bT^0.5 + dT + fT^1.5 + hT^2)]`, with separate coefficient sets for residual resistivity ratio 50, 100, 150, 300 and 500.
  - **Conductivity is strongly purity dependent at low temperature and not at all at room temperature.** At 20 K the fits give 1368 W/m-K at RRR 50 and 3245 W/m-K at RRR 150, a factor of 2.4; at 293 K they span 392.8 to 398.3 W/m-K, a factor of 1.014. A room-temperature measurement cannot tell you which curve applies.
  - NOVA stores the RRR 50 set, as the low end appropriate to fabricated hardware rather than a research-grade sample, and the stored provenance says so.
  - Expansion is given as the coefficient directly in 1e-6/K on the log form, unlike the other materials which give the integrated strain.
  - At 293 K the fit gives 396.5 W/m-K against the 391 W/m-K NOVA already carried from Touloukian, a 0.4 % difference and the closest agreement of the five.

## NIST cryogenic properties: 316 stainless, 6061-T6, Ti-6Al-4V, Inconel 718

- **URL:** <https://trc.nist.gov/cryogenics/materials/316Stainless/316Stainless_rev.htm>, <https://trc.nist.gov/cryogenics/materials/6061%20Aluminum/6061_T6Aluminum_rev.htm>, <https://trc.nist.gov/cryogenics/materials/Ti6Al4V/Ti6Al4V_rev.htm>, <https://trc.nist.gov/cryogenics/materials/Iconel%20718/Inconel718_rev.htm>
- **Accessed:** 2026-09-08
- **Relevance:** The four structural alloys in NOVA's table that NIST covers. Supplies both the cryogenic conductivity and the cryogenic expansion that were missing.
- **Key findings:**
  - Conductivity at 20 K as a fraction of the room-temperature value: 316L 0.142, Ti-6Al-4V 0.114, 6061-T6 0.183, Inconel 718 0.303. Every one of them conducts *worse* cold, by a factor of three to nine.
  - Disagreement with the room-temperature value NOVA already carried, at the join: 316L +4.5 %, 6061-T6 -7.1 %, Ti-6Al-4V +9.9 %, Inconel 718 -12.8 %. The cryogenic segment is normalised onto NOVA's value so the validated high-temperature curve is preserved; the factor is recorded per alloy.
  - The NIST fit is for type 316 rather than 316L. The two differ mainly in carbon content, which has little effect on conductivity.
  - Ti-6Al-4V conductivity data covers 23-300 K, narrower than the others.

## Special Metals, INCONEL alloy 718 technical bulletin

- **URL:** <https://www.specialmetals.com/documents/technical-bulletins/inconel/inconel-alloy-718.pdf>
- **Accessed:** 2026-09-08
- **Relevance:** The producer's own datasheet, and the only openly available source found that tabulates 0.2 % offset yield strength and elongation against temperature from cryogenic to hot on a stated product form and heat treatment.
- **Key findings:**
  - Table 19, hot-rolled 4-in round annealed 1950 F/1 hr and aged 1400 F/10 hr, gives yield and elongation at room temperature and 600, 1000, 1200, 1300, 1400 and 1500 F.
  - Table 21, forging annealed 1800 F/45 min and aged 1325 F/8 hr, gives the same at -423, -320, -110 F and room temperature. -423 F is liquid hydrogen.
  - The two product forms differ by 1.8 % where they overlap at room temperature (165.9 against 163.0 ksi), which is the error of splicing them into one curve. NOVA does splice them and records that figure.
  - Yield rises 19.6 % from room temperature to -423 F, 1123.8 to 1343.8 MPa. A held-flat room-temperature value understates the cold end.
  - Elongation is **not monotone**: it falls to 5 % at 1400 F and recovers to 15 % at 1500 F. This is the alloy, and it is pinned by a test so it does not get smoothed away.
  - Table 20 offers a single product form spanning -320 to 1300 F but with only five points and an 80-to-1200 F gap, so it was not used as the backbone.

## Special Metals, INCONEL alloy 625 technical bulletin

- **URL:** <https://www.specialmetals.com/documents/technical-bulletins/inconel/inconel-alloy-625.pdf>
- **Accessed:** 2026-09-08
- **Relevance:** Sought for the same yield-versus-temperature table as the 718 bulletin. It does not have one.
- **Key findings:**
  - Temperature-dependent tensile properties appear only as Figures 3, 4, 5 and 10, as plotted curves without an accompanying table.
  - Table 6 gives properties after 2000 hr exposure at 1200, 1400 and 1600 F, which is an ageing study rather than a yield-versus-temperature curve, and is not the same quantity.
  - **Nothing was taken from this source for yield strength.** Digitising a plot is not a citation, and Inconel 625's yield stays a held-flat room-temperature value with its provenance saying why.

## de Groh, Ellis and Loewenthal, *Comparison of GRCop-84 to Other Cu Alloys With High Thermal Conductivities*

- **URL:** <https://ntrs.nasa.gov/api/citations/20070026245/downloads/20070026245.pdf>
- **Accessed:** 2026-09-08
- **Relevance:** NASA Glenn's side-by-side characterisation of the copper alloys used in rocket chambers. The only source found that gives CuCrZr thermal expansion as a fitted correlation rather than a single number.
- **Key findings:**
  - Table 5 gives thermal expansion as a quadratic in Celsius, `alpha(T) = A T^2 + B T + C`, for AMZIRC, GlidCop Al-15, Cu-1Cr-0.1Zr and Cu-0.9Cr, stated accurate to 1 %.
  - Cu-1Cr-0.1Zr is C18150, which is the CuCrZr in NOVA's table. Its coefficients are A = 4.947e-09, B = 1.559e-05, C = -8.019e-05.
  - The quantity is cumulative expansion strain, so the instantaneous coefficient is its derivative and the mean from 20 degC is the difference over the interval. That gives 15.79e-6/K at 20 degC rising to 18.66e-6/K at 600 degC, an 18 % rise the previously stored flat 17.0e-6/K missed.
  - Tables 3 and 4 give steady-state creep power laws at 500 and 650 degC for the same alloys. Not used, but they are what a creep model would start from.
  - Also carries composition (Table 1) and a simulated braze cycle (Table 2) that materially weakens AMZIRC and Cu-1Cr-0.1Zr above 500 degC.

## ASME Boiler and Pressure Vessel Code, Section II Part D

- **URL:** <https://www.asme.org/codes-standards/find-codes-standards/bpvc-iid-bpvc-section-ii-materials-part-d-properties>
- **Accessed:** 2026-09-08
- **Relevance:** Table Y-1 carries yield strength against temperature for 316L and N06625, which is exactly the missing data for two alloys.
- **Key findings:**
  - Copyrighted and available only by purchase or institutional subscription. The tabulated values are not publicly reproducible.
  - **Nothing was taken from this source.** It is recorded as the route to close the 316L and Inconel 625 yield gap should the standard be available.

## MMPDS (Metallic Materials Properties Development and Standardization)

- **URL:** <https://www.mmpds.org/>
- **Accessed:** 2026-09-08
- **Relevance:** The aerospace design-allowables handbook, and the correct source for 6061-T6 and Ti-6Al-4V yield against temperature, with A- and B-basis allowables rather than typical values.
- **Key findings:**
  - Paywalled. No openly available reproduction of its elevated-temperature knockdown curves was found.
  - **Nothing was taken from this source.** 6061-T6 and Ti-6Al-4V yield remain held-flat room-temperature values, and their provenance says MMPDS carries the temperature dependence but is not openly available.
  - Worth noting for the 6061-T6 entry specifically: the T6 temper over-ages above roughly 200 degC, so a flat room-temperature yield is unconservative there, and the stored provenance says so.

## NARloy-Z (Cu-3Ag-0.5Zr) elevated-temperature behaviour

- **URL:** <https://link.springer.com/article/10.1007/s11665-019-04499-w>, <https://ntrs.nasa.gov/api/citations/20160001827/downloads/20160001827.pdf>
- **Accessed:** 2026-09-08
- **Relevance:** NARloy-Z is the SSME main combustion chamber alloy and is in NOVA's table with an explicitly unvalidated conductivity trend. Sought a tabulated yield curve.
- **Key findings:**
  - The literature describes the shape consistently: yield falls only marginally from 27 to 500 degC, then roughly halves by 600-700 degC. Reported points include 146 MPa at 540 degC and 100 MPa at 640 degC in the solution-treated and aged condition, against roughly 200 MPa at room temperature.
  - Those figures come from different studies on different product forms and conditions, including cold-spray and glazed material, so they do not form one curve.
  - **Nothing was taken.** NARloy-Z yield stays held flat, with its provenance recording the shape the literature reports and why it was not adopted.

---

## What this left undone

Yield strength against temperature is still a held-flat room-temperature value for eight of the ten alloys. The tabulated sources that would close it, ASME Section II Part D and MMPDS, are both paywalled; the producer datasheets either plot it without tabulating it (Inconel 625) or do not cover it (CuCrZr, AlSi10Mg). Filling those from journal papers on assorted product forms would produce a curve that looks authoritative and is not traceable to one condition, which is worse than a flag saying the data is absent.

Cryogenic data is absent for GRCop-42, CuCrZr, NARloy-Z, AlSi10Mg and Inconel 625. For the copper alloys this matters less than it might: the low-temperature conductivity peak that makes pure copper so conductive at 20 K is a purity effect, and alloying additions suppress it, so extrapolating OFHC behaviour onto GRCop-42 or NARloy-Z would be wrong in a way that flatters the design.
