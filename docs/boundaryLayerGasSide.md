# Gas-Side Heat Transfer From the Boundary Layer

This document covers NOVA's gas-side heat transfer read from an integral boundary layer: the marched layer in `boundaryLayer.py`, Ievlev's integral method in `ievlevHeatTransfer.py`, the near-wall state both read, how a jacket couples to a method that carries the wall's history, and what each is validated against. The comparison behind it is [reports/calorimeter40k_2026-10-04.md](reports/calorimeter40k_2026-10-04.md); the algebraic correlation and its own validation status are in `gasSideHeatTransfer.py`.

---

## Why

Bartz is an algebraic correlation whose only axial variable is the area ratio. It carries no boundary-layer history and cannot distinguish the two sides of a throat, because mass flux per unit area is identical on both branches by continuity and that is all its area term knows. On Test 024 of the MSFC 40k calorimeter chamber it runs the throat 38 percent high against the barrel.

At matched area ratio the measured heat flux downstream of that throat is a fraction of the upstream value. Every model below runs on the hot-wall temperature the test's reduction used, which falls from about 860 K at the throat to between 300 and 500 K on the diverging side, so each model's diverging flux sits higher against its converging flux than it would on a uniform wall:

| Area ratio | Measured | Bartz | Marched layer, 1-D edge | Marched layer, characteristics edge | Ievlev, 1-D edge | RPA's own output |
|---|---|---|---|---|---|---|
| 1.1 | 0.79 | 1.03 | 0.97 | 0.67 | 0.98 | 0.93 |
| 1.5 | 0.36 | 1.17 | 1.02 | 0.79 | 1.03 | 0.82 |
| 2.0 | 0.28 | 1.12 | 0.93 | 0.79 | 0.95 | 0.73 |

**The history an integral method carries is worth 6 to 17 percent of this asymmetry; the edge state is worth more.** A marched layer on a one-dimensional edge state is close to symmetric. On NOVA's wall the characteristics solve puts the wall at Mach 1.82 twelve millimetres past the throat where the one-dimensional state puts it at 1.46, and the lower mass flux per unit area there is most of what separates the two sides. No method here reaches the measured 0.28 at an area ratio of 2.

The acceleration parameter peaks at 1.2e-6, below both the 3e-6 usually quoted for relaminarization and the 2e-6 Wang and Luong take from Back, Cuffel and Massier as the onset of reduced heat transfer, so the layer is treated as turbulent throughout.

## The marched layer

`boundaryLayer.solveBoundaryLayer` marches the integral momentum and energy equations along the wall, after JPL Technical Report 32-387. Momentum, Eq. 22 in its transformed form:

    dtheta/dx = Cf/2 - theta (2 + H - M^2)(1/U)(dU/dx) - theta (1/r)(dr/dx)

Energy, from Eq. 28 with the energy thickness `phi`, divided through by r rho U cp (T0 - Tw):

    dphi/dx = St (Taw - Tw)/(T0 - Tw)
              - phi [ (1/r)(dr/dx) + (1/(rho U)) d(rho U)/dx + (1/(T0 - Tw)) d(T0 - Tw)/dx ]

The source terms carry the wall inclination, after Eqs. 25 and 30, because friction and heat act over the wall rather than its axial projection. The last bracketed term vanishes on a uniform wall and does not on a cooled one. The march integrates on a refined grid of 32 subdivisions per supplied interval, because forward Euler at a contour's own spacing is not converged through a throat.

**Stanton number**, JPL 32-387 Eq. 46, von Karman's form of Reynolds analogy:

    St = (Cf/2) / ( 1 + 5 sqrt(Cf/2) [ (Pr - 1) + ln((5 Pr + 1)/6) ] )

with Cf evaluated at the energy-thickness Reynolds number `R_phi = rho U phi / mu`, which is how the thermal and velocity layers are allowed to differ.

**Thickness interaction**, Bartz NTRS 19650013685 Eq. 42, splits the quarter power of the friction law between the two Reynolds numbers:

    Ch = const / ( Pr^(2/3) R_theta^n R_phi^(1/4 - n) )

equivalently the Stanton number at `R_phi` times `(phi/theta)^n`. Bartz selects 0.1 and states that the selection is arbitrary. Through a throat the march's thickness ratio reaches 8 to 10, where that factor is 1.23 to 1.26. **The default is n = 0**, the energy-thickness law that Ambrok, Kays and Crawford, and Kutateladze and Leont'ev use. It was selected over 0.1 and over Ievlev's method on NASA TN D-2832 by a rule fixed before the candidates ran, and it takes the 40k chamber's throat-to-barrel error from 32 percent to 8.5 on RPA's wall, and to 7.5 on NOVA's wall with the transonic near-wall state. Nothing else in NOVA reads the march's heat transfer, and the drag it supplies to the thrust debit does not depend on n.

**Gas-side coefficient**, h_g = St rho U cp, with cp = gamma R / (gamma - 1). On LOX/LH2 that specific heat overstates the enthalpy the layer carries to a cold wall by about a quarter; `tests/calorimeter40kCase.marchedHeatFlux` substitutes the enthalpy difference to the wall gas at its result, which is what the comparisons use.

## Ievlev's method

`ievlevHeatTransfer` implements Ievlev's method as RPA gives it, Eqs. 1.1 to 1.6 of Ponomarenko's 2012 thermal analysis paper. Only the energy integral carries history, integrated in closed form; the momentum side is an algebraic ratio near 1.5; and the potential is the enthalpy difference to the wall gas at its 1500 K composition. The module's notes say how the paper's four open choices are settled. Against RPA's own output for the same test, on the test's own wall temperature, it reproduces RPA's barrel and peak to 0 and 3 percent. Past the throat it runs 16 to 26 percent above RPA, which a 900 K wall closes to 4 percent; RPA does not state the wall temperature it used.

## The near-wall state

The converging near-wall state is one-dimensional by default, which puts the sonic point at the geometric throat on every streamline. `nearWallStateModel: transonic` carries the transonic solution the characteristics net starts from over the entrant arc (`contourKernel.transonicConvergingWallMach`), tapered back to one-dimensional where the arc meets the cone. The wall then goes sonic 0.18 to 0.22 throat radii ahead of the throat, where its mass flux per unit area peaks, and the state joins the characteristics solve without the jump from Mach 1.0 to about 1.3 that a one-dimensional sonic throat leaves. Downstream of the throat the near-wall state is the characteristics solve's. On the 40k chamber, under n = 0, the transonic state moves the marched layer's heat flux peak 2.5 mm (Sauer) to 3.9 mm (second order) upstream and takes 5 to 7 points off the throat-to-barrel error. Tapering it over half the arc instead of all of it moves the peak by 2.0 mm and the throat-to-barrel ratio by under 0.1 percent.

## Coupling to a jacket

The gas side of an integral method depends on the wall upstream of a station, and the coolant marches from the aft end forward, so the two cannot be carried in one pass. `regenChannels.generateChannelRadiiIevlev` sizes the jacket around an outer iteration: the flux is solved over the whole regen wall at a guessed wall temperature, handed to each station as a prescribed coefficient referred to the recovery temperature, the jacket is sized, and the wall temperature it lands on is the next guess. The first guess is the jacket's wall limit. On the regression jacket (`regenIevlev` in `tests/regressionHarness.py`) it closes in three passes, with 0.58 K of change on the last.

`gasSideAxialModel: ievlev` runs that loop. The marched layer is not offered as a jacket gas side; the same loop would carry it, with the march in place of `ievlevJacketCoefficient`.

## Validation

**Closed forms.** The energy equation reduces to the flat-plate result with the Mach number at zero, a uniform wall and no radius change; the Stanton closure returns Cf/2 over the Prandtl correction with phi equal to theta, and Cf/2 at a Prandtl number of one (`tests/testBoundaryLayer.py`). Ievlev's quadrature is exact in a straight duct to 1e-10, and its wall gas enthalpy agrees with NIST-JANAF to 0.1 percent (`tests/testIevlev.py`). The transonic wall state reproduces the starting line's throat-wall velocity and Sauer's sonic point (`tests/testContourKernel.py`).

**Against NASA TN D-2832**, on the station-to-station shape of the measured correlation constant: the energy-thickness law ranks first among the three closures, Ievlev's method second, Bartz's interaction third. All three underpredict the throat's drop on that chamber. NOVA's `measured` axial model is built from the same constants, so the chamber does not test it.

**Against the 40k calorimeter**, Test 024, with the closure selected on TN D-2832, CEA properties, an equilibrium enthalpy potential, the test's own wall temperature and the transonic near-wall state, the throat-to-barrel ratio lands 7.5 percent high (5.0 under the second-order transonic solution). The level runs 17 to 23 percent low and is not validated, and the converging slope and the diverging section are not reproduced.

**Against Carlile and Quentmeyer**, the jacket's throat-region comparison, nothing moves: it runs on Bartz, and every default path is unchanged.

**Not done: JPL 32-387's own Figure 4**, which compares the Stanton closure against flat-plate and tube-entrance data.

## Risks

**The Stanton closure is applied outside the range it was correlated on.** JPL derives Eq. 46 for equal thicknesses and adopts it as a first approximation when they are not, on tube data spanning thickness ratios of 0.3 to 1.0; the 40k throat reaches 8 to 10. With n = 0 the closure no longer multiplies by that ratio, but the analogy underneath is still carried past its data, and the agreement at the 40k throat rests on one selection among three closures on one other chamber.

**The friction closure is open.** Coles' correlation after Bartz, with his two wall-property assumptions, sits beside the reference-temperature power law. On the 40k chamber the film-property assumption improves the barrel and worsens the throat, the adiabatic one does the reverse, and NASA RP-1104's friction factor does not choose between them. On a cooled throat the two assumptions differ by about half in the friction coefficient.

**The level rests on the chemistry assumption.** A recombined wall gas with equilibrium transport and a wall gas at chamber composition with frozen transport put the 40k barrel 18 points apart, at -17 and -35 percent. The comparisons take the recombined one, as the layer near a catalytic copper wall at 10.9 MPa should be. The test's fuel inlet temperature, which the source does not give, moves the level by about 5 points more.

**The starting thickness is not a risk.** Across three decades of the starting thicknesses, 0.1 to 100 micron, the throat heat flux moves by about 1 percent; Ievlev's starting value moves it by under 2 percent across two decades.

## What this does not fix

The closed march runs 17 to 23 percent low on the 40k chamber, and nothing here fixes the level. The measurement rises earlier and flatter through the convergence than any model here, already 1.41 times the barrel at an area ratio of 2.5, and past an area ratio of 1.2 on the diverging side it falls well below all of them. The contour does not explain either: NOVA's wall reaches each area ratio in 87 to 91 percent of the wall length RPA's takes, and the measured stations' errors barely move between the two. TN D-2832's supersonic station at an area ratio of 3.33 is reproduced to within 10 percent, so the diverging discrepancy is specific to the 40k chamber. No film was injected on that hardware, and the mechanism is not identified.

## Sources

- D. R. Bartz, D. G. Elliott and S. Silver, "Calculation of Turbulent Boundary-Layer Growth and Heat Transfer in Axi-Symmetric Nozzles", JPL Technical Report 32-387, February 1963. Public domain, at `archive.org/details/nasa_techdoc_19630004589`. The integral momentum and energy equations, the skin-friction and Stanton closures, the shape parameter and the validation figures.
- D. R. Bartz, "Turbulent Boundary-Layer Heat Transfer from Rapidly Accelerating Flow of Rocket Combustion Gases and of Heated Air", JPL, December 1963, NTRS 19650013685. The thickness interaction factor and the driving-potential treatment.
- A. Ponomarenko, "RPA: Tool for Rocket Propulsion Analysis. Thermal Analysis of Thrust Chambers", June 2012. Ievlev's method as RPA carries it.
- R. L. Schacht, R. J. Quentmeyer and W. L. Jones, NASA TN D-2832, June 1965, NTRS 19650016811. The selection chamber.
- S. S. Kutateladze and A. I. Leont'ev, "Heat-Mass Transfer and Friction in Turbulent Boundary Layer", NASA Technical Translation TT F-805, 1974. The Russian school's integral theory, Ievlev's lineage.
- C. E. Dexter, M. F. Fisher, J. R. Hulka, K. P. Denisov, A. A. Shibanov and A. F. Agarkov, "Scaling Techniques for Design, Development, and Test", Progress in Astronautics and Aeronautics Vol. 200, AIAA, 2004, Chapter 16, DOI 10.2514/5.9781600866760.0553.0600. The 40k hardware, Test 024's heat flux and heat transfer coefficient, and the reduction that relates them.
- Ten-See Wang and Van Luong, Journal of Thermophysics and Heat Transfer, Vol. 8, No. 3, 1994. The calorimeter's coolant water inlet temperature, and the onset criterion they take from Back, Cuffel and Massier.
