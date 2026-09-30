# References: volute and manifold design

Sources consulted for the volute generator audit, covering scroll area laws, manifold flow distribution, toroidal shell stress and the printability limits of GRCop alloys.

## Design of Liquid Propellant Rocket Engines, NASA SP-125 (Huzel and Huang, 1967)

- **URL:** <https://web.stanford.edu/~cantwell/AA284A_Course_Material/AA284A_Resources/Huzel%20and%20Huang,%20Design_Of_Liquid_Propellant_Rocket_Engines%20NASA%201967.pdf>
- **Accessed:** 2026-09-29
- **Relevance:** The canonical rocket design reference, and the only one that states a scroll area law in the same geometry class as a coolant manifold. Used for the area law, the pressure recovery fraction and the treatment of the tongue.
- **Key findings:**
  - Equation 6-69, plain volute casing: `c3' = Q/(3.12 a_v) = (1/3.12)(Q/360)(theta/a_theta)`, so the area at angular position `theta` from the tongue is `a_theta = a_v theta/360`. All of the flow passes the throat `a_v`, and only part passes any other section, the amount depending on distance from the tongue. Stated as "one design approach is to keep a constant average flow velocity at all sections of the volute".
  - Volute pressure recovery: "approximately 70 to 90 percent of the flow kinetic energy is converted into pressure head in either volute type", and "head losses in pump volutes are relatively high".
  - Tongue geometry is a design parameter in its own right: the tongue angle is set to the absolute discharge flow angle to avoid impact shocks and separation losses, and the tongue radius is 5 to 10 per cent larger than the impeller radius so the flow can equalize before reaching it.
  - Volute pressure cannot be kept uniform off design, producing a radial thrust; the fix is a double volute with two tongues 180 degrees apart.
  - Coolant passage pressure drop is treated as a hydraulic conduit, equation 4-32. No manifold velocity rule and no manifold distribution criterion appear in the regenerative cooling chapter.
  - Propellant duct design trend is toward higher flow velocities, "over 100 fps", with high-impact loading on control surfaces called out as the consequence.

## Volute spiral development design rules, CFturbo manual

- **URL:** <https://manual.cfturbo.com/en/voldesignrule.html>
- **Accessed:** 2026-09-29
- **Relevance:** States the two standard area laws side by side with the names used in the turbomachinery literature, which fixes the vocabulary for comparing NOVA's law against practice.
- **Key findings:**
  - Pfleiderer rule: `c_u r^x = constant`, with `x = 1` the constant angular momentum (free vortex) case and `x = 0` constant tangential velocity.
  - Stepanoff rule: constant velocity in all cross sections of the circumference, with the velocity set from an empirical coefficient dependent on specific speed.
  - A third category defines the geometry progression directly, by height, area or area over radius, rather than from a velocity assumption.

## Analysis and Comparison of Two Kinds of Design Approaches for Volutes of Centrifugal Pump (Energies, 2023)

- **URL:** <https://www.mdpi.com/1996-1073/16/17/6128>
- **Accessed:** 2026-09-29
- **Relevance:** Gives the constant angular momentum law in the form that matters for a scroll whose cross-section centroid moves, and compares the two laws on performance.
- **Key findings:**
  - Constant angular momentum is achieved by controlling the cross-sectional centroid, "by ensuring that the cross-sectional area of the scroll divided by the centroid radius varies as a linear function of the circumference of the scroll".
  - The integral can be solved explicitly for rectangles, trapezoids and circles, numerically otherwise.
  - Volutes designed on constant angular momentum outperformed constant mean velocity on radial force magnitude and peak scalar stresses.

## Flow Distribution Manifolds (Bajura and Jones, ASME J. Fluids Eng. 98(4), 1976, pp. 654-666)

- **URL:** <https://ui.adsabs.harvard.edu/abs/1976ATJFE..98..654B/abstract>
- **Accessed:** 2026-09-29
- **Relevance:** The foundational treatment of flow distribution in dividing and combining manifolds, which is what the inlet and outlet volutes are. Establishes the governing equations and what a distribution prediction requires.
- **Key findings:**
  - Lateral branch flows in dividing, combining, reverse and parallel manifolds follow from two first-order differential equations in flow rate and header pressure difference, or one second-order nonlinear equation in flow rate alone.
  - Prediction depends on the momentum exchange and discharge coefficients and on a valid physical model of the branching process.
  - A manifold with many branches is better handled by a continuous flow model than by a discrete branch-point model.

## Modeling the Uniformity of Manifold with Various Configurations (Journal of Fluids, 2014)

- **URL:** <https://onlinelibrary.wiley.com/doi/10.1155/2014/325259>
- **Accessed:** 2026-09-29
- **Relevance:** States the practical distribution criterion in the ratio form used in the audit.
- **Key findings:**
  - Distribution is acceptable as long as the pressure drop along the header is much less than the pressure drop across any one branch.
  - Uniformity depends on the ratio of dynamic pressure at the branch inlet to the frictional pressure drop through the branch. A large branch-inlet velocity head relative to the branch drop sends flow preferentially to the nearest branches and starves the remote ones.
  - Larger manifold area and longer branch length both improve distribution. For liquid service, header velocity of 1 to 2 m/s keeps the velocity head negligible.

## Resolution and geometric limitations in laser powder bed fusion additively manufactured GRCop-84 structures (Fusion Engineering and Design, 2021)

- **URL:** <https://www.sciencedirect.com/science/article/abs/pii/S0920379621006232>
- **Accessed:** 2026-09-29
- **Relevance:** The printability limit for the alloy family the volute is built in, used to judge the sized wall thickness.
- **Key findings:**
  - Internal stress limits the minimum thickness of vertical walls and septa to 1 mm; thinner walls warp during printing.
  - Accuracy within 40 micrometres is typical on well supported structures.
  - Roughness is minimized on vertical surfaces and grows on both upper and lower surfaces as the angle increases.
  - Reported for GRCop-84. GRCop-42 is processed the same way and the limit is taken to carry across, which is an assumption rather than a measurement on GRCop-42.

## Toroidal shell under internal pressure, Roark's Formulas for Stress and Strain

- **URL:** <https://www.engineersedge.com/pressure,045vessel/toroidal_shell_internal_or_external_pressure_15188.htm>
- **Accessed:** 2026-09-29
- **Relevance:** Confirms that a toroidal shell carries a position-dependent membrane stress rather than the constant hoop stress of a cylinder, which is the correction the wall sizing omits.
- **Key findings:**
  - Membrane stress formulas for thin-walled toroidal shells, valid for `b/t > 10`, are tabulated in Roark's as functions of tube radius, bend radius and angular position.
  - In a constant-thickness toroidal vessel the inside wall carries more load than the outside, so the hoop stress varies around the meridian rather than holding the constant value simple theory suggests.
  - The page renders its formulas as images, so the closed form used in the audit was derived from membrane equilibrium and checked against the straight-cylinder limit rather than copied from this source.
