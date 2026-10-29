# NOVA Plume in OpenFOAM

An axisymmetric Euler solution of the exhaust plume of NOVA's shipped nozzle in OpenFOAM, run as a cross-check of NOVA's two plume outputs: the station march that solves the boundary and interior for two lip radii past the exit plane, and the correlations that place the shock cell length and the Mach disk. The nozzle's interior is a separate case, described in [README.md](README.md).

## Contents

- [Summary](#summary)
- [What the case solves](#what-the-case-solves)
- [Running it](#running-it)
- [What is compared](#what-is-compared)
- [Acceptance criteria](#acceptance-criteria)
- [Results](#results)
- [Findings](#findings)
- [Validation status](#validation-status)
- [References](#references)
- [Files](#files)

## Summary

Within its shipped reach of two station radii, NOVA's station march agrees with the Euler solution. On the fine grid the march's boundary sits 1.0 percent of radius inside OpenFOAM's on average. The worst station, 2.0 percent, is the first, one fine cell from the lip. The field Mach number agrees to 1.0 percent at the 95th percentile, and the boundary angle at the lip to 0.07 degree once the grid error is extrapolated out. Two of those three miss their criteria on the fine grid itself (2.04 percent against 2.0, and 1.15 degrees against 1.0), by margins that roughly halve with each halving of the cell size. Marched on to 10 station radii, the march still follows OpenFOAM's axis to within 0.5 percent outside the arrival of the first expansion wave, and its boundary to 2.3 percent at 6 station radii, while its own mass flow falls 16 percent.

The correlations do not hold. The jet's barrel shock reflects regularly from the axis at 12.8 station radii on all three grids. NOVA's Ashkenas and Sherman Mach disk sits at 8.05, 37 percent short, and its diameter correlation gives a disk 9.4 station radii across, twice the jet's widest diameter, where the case resolves none. The first shock cell is 18.7 station radii long against Prandtl's 20.0 at the chamber gas (6.9 percent, within its criterion) and the 22.8 NOVA reports at the exit gas (21.7 percent). The steadiness criteria fail on the open ambient, which settles over tens of milliseconds and trades mass through the far field; the jet itself is steady, its shock reflection moving 0.06 station radii over the averaging window.

The case also exposes four faults in NOVA. Its march starts 1.7 percent of the lip radius short of the wall and carries 4.7 percent less mass than its nozzle. Its correlations use the exit ratio of specific heats while its march uses the chamber's. The correlated boundary's amplitude is held at 0.95 of the lip radius, which then sets its widest radius. `PlumeField.lipTurnAngle` is declared and never set. OpenFOAM and NOVA are both unvalidated for this flow, so the agreement is a cross-check, not a validation; see [Validation status](#validation-status).

## What the case solves

The problem NOVA's station march solves, from the station it starts on: the Euler equations for a calorically perfect gas at NOVA's chamber ratio of specific heats, from the exit station NOVA hands its march, into a still ambient at the shipped pressure. The march is isentropic and carries no shock; the case captures the shocks. A difference between the two within the march's reach is a difference of method, because the starting data and the physics are identical.

| Item | Setting |
| --- | --- |
| Nozzle and plume | `src/NOVA/assets/NOVANozzle.json`: the nozzle of [README.md](README.md), with `plumeAmbientPressure` 5000 Pa and `plumeFieldReach` 2 lip radii |
| Gas | NOVA's chamber values, as in the nozzle case: gamma = 1.147542, R = 656.596 J/kg K, T0 = 3398.37 K, P0 = 6.895 MPa |
| Inflow | NOVA's march exit station: 121 points from the axis to 0.31270 m, which is 0.9826 of the 0.31825 m lip radius; Mach 4.2033 on the axis to 3.7971 at the edge, flow angle 0 to 8.69 degrees. Each inlet face takes the station's Mach number and angle at its radius, with p and T from the isentropic relations; every field fixed, since the flow is supersonic |
| Base | The exit plane outside the station radius; slip wall |
| Ambient | 5000 Pa and 216.65 K, the exhaust gas at rest |
| Far field and outlet | 8 station radii out (2.50 m) and 30 downstream (9.38 m). Pressure `waveTransmissive`, relaxing toward 5000 Pa over the domain's radius and length; velocity `pressureInletOutletVelocity` at the far field and `inletOutlet` at the outlet; temperature `inletOutlet` at the ambient's |
| Mesh | 5 degree wedge, six blocks in three radial bands. Square cells of one Nth of the station radius out to 4 station radii downstream and 3 out, growing to 4 times that size at the outlet and 6 times at the far field. N = 10, 20 and 40 (7680, 30720 and 123072 cells) |
| Solver | `rhoCentralFoam` (OpenFOAM v2606, ESI): Kurganov-Tadmor central fluxes, Minmod limited reconstruction, explicit Euler in time, `maxCo 1.0` |
| Initial field | Coarse grid: the ambient, with a column of the station's flow at ambient pressure inside the station radius along the whole domain. Medium and fine: the next coarser grid's solution, mapped |
| Run | Coarse 60 ms, medium 10 ms, fine 5 ms of physical time; fields averaged over the second half of each run |

Six details of the setup matter to the numbers.

**The case starts from NOVA's station, not from the nozzle's exit plane.** NOVA's march does not start at the nozzle's lip. `plume.plumeExitLine` reads the exit plane from where the characteristic mesh's rows cross it, and the outermost row crosses at 0.9826 of the lip radius. The station then carries 3.5 percent less area than the exit plane, and 21.76 kg/s against the 22.83 kg/s NOVA reports for its own nozzle, 4.7 percent less. The case's jet issues from the station radius so that both methods solve the same problem; the shortfall is a finding about NOVA rather than a difference between the methods. See [Findings](#findings).

**The ambient's temperature does not change the jet.** A steady inviscid jet meets its ambient at a contact surface across which only the pressure must match, so the ambient's temperature and composition only mark where the jet ends. It is the standard atmosphere's 216.65 K, near the altitude where pressure is 5 kPa, in the exhaust gas. What it does set is the ambient's sound speed, 408 m/s, which sets how slowly the ambient settles.

**The open boundaries pass waves rather than hold a pressure.** With the far field held at the ambient's total pressure, which reflects every wave back into the domain, the mass through it swung from 630 kg/s outward to 90 kg/s inward between 4.7 and 7.6 ms of the first sizing run, thirty times the jet's own flow. That is the still ambient, 5 m across and cold, ringing in its first radial acoustic mode, whose period for a cylinder of this radius with a pressure-release wall is about 16 ms. `waveTransmissive` lets outgoing waves leave at the local wave speed and relaxes the pressure toward the ambient's over the domain's own size. The start-up still disturbs the ambient: on the coarse grid its pressure beyond 5 station radii falls to 4420 Pa, 11.6 percent low, at 8 ms, and stays within 2 percent of 5000 Pa from 18 ms on, reading 5014 Pa at 60 ms. The coarse grid runs 60 ms for that reason, and each finer grid starts from the settled solution of the one before it.

**The limiter is Minmod, not van Leer.** Where the barrel shock meets the axis, van Leer's limiter, which the nozzle case uses, drives the axis cells past the gas's limiting velocity of 5893 m/s (to 6640 m/s in the run that failed) and the temperature negative, at a Courant number of 1.0 and of 0.5 alike. Minmod, the most dissipative of the TVD limiters, runs through. It smears the shocks and the contact surface over more cells; the grid study measures what that costs.

**The coarse grid starts from a column of exit flow at ambient pressure.** Started from rest, the jet's head takes about 10 ms to cross the domain, because the expanded jet is much lighter than the cold ambient it pushes aside. A column of the station's flow inside the station radius puts the jet's core in place from the first step. At the station's own pressure, two to five times the ambient's, the column expands radially as a blast; at ambient pressure, moving axially at the station's speed and temperature, it carries no radial pressure difference. With van Leer's limiter the run failed from rest, from a column at the station's pressure and from one at ambient pressure alike, so the start-up sets how long the run takes rather than whether it survives.

**The jet boundary is a total temperature contour.** Total temperature is conserved along streamlines of an inviscid adiabatic flow, so it is the chamber's 3398 K inside the jet and the ambient's 216.65 K outside. The case smears the contact surface between them over a few cells. The boundary is taken where total temperature is halfway between the two, and the radii where it is 10 and 90 percent of the way give the width of the smeared layer.

## Running it

The case is written and run the way the nozzle case is; see [README.md](README.md#running-it) for the environment.

1. Write the three cases. The first call solves NOVA with its plume (about two minutes), marches it a second time to 10 lip radii, and writes `reference/novaPlume.json`; later calls reuse it until `--refresh` is passed.

   ```bash
   python validation/openFoam/makePlumeCase.py --resolution coarse --writes 15
   python validation/openFoam/makePlumeCase.py --resolution medium --writes 10
   python validation/openFoam/makePlumeCase.py --resolution fine --writes 10
   ```

2. Copy them into the Linux file system and run the coarse grid, then each finer grid from the one before it. Each `Allrun` meshes, writes the inflow (and on the coarse grid the starting column), runs on four processors, reconstructs the last write and runs the comparison, which it logs to `log.python3.compare`. On four processors the coarse grid's 60 ms take 7 minutes, the medium grid's 10 ms 13 minutes and the fine grid's 5 ms 72 minutes.

   ```bash
   cp -r /mnt/c/.../NOVA/validation/openFoam/cases/novaPlume2D-* ~/foam/
   cd ~/foam/novaPlume2D-coarse && ./Allrun
   cd ~/foam/novaPlume2D-medium && ./Allrun ../novaPlume2D-coarse
   cd ~/foam/novaPlume2D-fine && ./Allrun ../novaPlume2D-medium
   ```

3. Run the grid study across the three:

   ```bash
   cd ~/foam
   python3 novaPlume2D-fine/scripts/plumeGridConvergence.py novaPlume2D-coarse novaPlume2D-medium novaPlume2D-fine
   ```

Each case's `comparison/` folder holds `comparison.json` and the figures.

## What is compared

| Quantity | OpenFOAM | NOVA |
| --- | --- | --- |
| Jet boundary | The 50 percent total temperature contour, column by column, from the averaged fields | `PlumeField.boundaryX`, `boundaryR`: the march's free boundary, one point per station |
| Boundary angle at the lip | Straight-line fit to the boundary over the first half station radius | The same fit to the march's boundary; and the Prandtl-Meyer turn from the station's edge to the boundary Mach number |
| Interior field | Cell values interpolated linearly to each march node inside 0.9 of the march's boundary radius | Mach number, pressure and flow angle at every node of the march's 130 stations of 121 points |
| Axis | Line sample on the axis | The march's axis nodes |
| Mach disk location | The steepest fall in axis Mach number ahead of the first subsonic stretch, or ahead of the first minimum when the reflection is regular | `PlumeStructure.machDiskX`: Ashkenas and Sherman, x / D* = 0.67 sqrt(P0 / Pa) [1] |
| Mach disk diameter | Twice the radius of the subsonic region a tenth of a station radius behind the disk | `machDiskDiameter`: D / De = 1.78 log10(P0 / Pa) - 0.98 [2] |
| First shock cell | Exit plane to the boundary's first neck | `shockCellLength`: Prandtl, 1.306 Dj sqrt(Mj^2 - 1), with Tam and Tanna's fully expanded diameter [3, 4] |
| Widest boundary | The boundary's first maximum | The correlated boundary's maximum |

NOVA evaluates its correlations at CEA's exit ratio of specific heats, 1.257, while its march and this case run at the chamber's 1.1475. Each correlation is therefore evaluated twice: as NOVA reports it, and at the chamber gas with NOVA's own functions (`plume.fullyExpandedDiameter`, `shockCellLength`, `gasDynamics.machFromPressureRatio`, `prandtlMeyerAngle`). The criteria judge the second, which compares like with like. The Mach disk correlations do not depend on the gas.

## Acceptance criteria

Every limit is a relative difference of NOVA against OpenFOAM unless stated, and every limit was fixed in `comparePlume.py` and `plumeGridConvergence.py` before the first run. Three sizing runs on the coarse grid then settled the boundary conditions, the start-up and the limiter described above; none of them changed a limit or a measurement.

| Criterion | Limit | Basis |
| --- | --- | --- |
| Boundary radius, worst march station | 2.0 % | The boundary is what the march exists to produce; 2 percent of radius is 4 percent of area |
| Field Mach, 95th percentile over march nodes inside 0.9 of its boundary | 2.0 % | As for the nozzle |
| Boundary angle over the first half station radius | 1.0 degree | The lip's expansion fan, which sets everything downstream |
| Mach disk location | 10 % | The correlation's coefficient spans 0.64 to 0.67 across sources, 5 percent, and it is fitted to sonic nozzles |
| Mach disk diameter | 25 % | A fit for coflowing jets, less certain than the location |
| First shock cell length | 10 % | Prandtl's and Pack's coefficients differ by 7 percent |
| Mass imbalance, inflow against outflow, window means | 0.2 % | Steady state; the open boundaries exchange mass with the ambient, which the nozzle's walls do not |
| Drift of the outlet mass flow, second half of the window against the first | 0.1 % | Steady state |
| Boundary radius at the end of the march, medium grid against fine | 0.5 % | Grid convergence |
| Mach disk location, medium grid against fine | 2.0 % | Grid convergence |

## Results

Lengths are in station radii (0.31270 m), measured from the exit plane. The figures are the fine grid's. Each grid's full comparison is in `results/plume/<grid>/comparison.txt` and `comparison.json`, and the grid study in `results/plume/plumeGridConvergence.json`.

### Criteria

On the fine grid:

| Criterion | NOVA against OpenFOAM | Limit | Result |
| --- | --- | --- | --- |
| Boundary radius, worst march station | 2.04 % | 2.0 % | Fail |
| Field Mach, 95th percentile | 0.99 % | 2.0 % | Pass |
| Boundary angle over the first half station radius | 1.15 degrees | 1.0 degree | Fail |
| Mach disk location | -37.1 % (reflection, no disk) | 10 % | Fail |
| Mach disk diameter | No disk resolved | 25 % | Fail |
| First shock cell length, at the chamber gas | +6.9 % | 10 % | Pass |
| Mass imbalance | -37.3 % | 0.2 % | Fail |
| Drift of the outlet mass flow | -4.0 % | 0.1 % | Fail |
| Boundary radius at the end of the march, medium grid against fine | 0.31 % | 0.5 % | Pass |
| Mach disk location, medium grid against fine | 0.51 % | 2.0 % | Pass |

### Grid convergence

| Quantity | Coarse | Medium | Fine | Observed order | Extrapolated | GCI | NOVA |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Boundary radius at the end of the march | 1.7292 | 1.7391 | 1.7337 | oscillatory | | 0.13 % | 1.7155 |
| Boundary angle at the lip [deg] | 17.87 | 22.05 | 23.71 | 1.34 | 24.79 | 5.7 % | 24.86 |
| Reflection on the axis | 12.64 | 12.86 | 12.79 | oscillatory | | 0.21 % | 8.05 (Mach disk) |
| Mach disk diameter | none | none | none | | | | 9.38 |
| First shock cell length | 18.57 | 18.66 | 18.72 | 0.46 | 18.88 | 1.1 % | 20.00 |
| Widest boundary radius | 2.277 | 2.255 | 2.222 | -0.53 | | 0.61 % | 1.927 |

An oscillatory sequence, or one whose change grows with refinement, has no observed order; it gets no extrapolation, and its index is taken at a formal second order. The boundary where the march ends and the reflection settle to 0.3 and 0.5 percent between the medium and fine grids. The widest boundary radius narrows by more with each refinement, so its grids are outside the asymptotic range, and its fine value carries an error of order its last change, 1.5 percent.

The near field converges toward the march:

| Grid | Cells | Boundary, mean / worst station | Field Mach, p95 | Field pressure, p95 | Field flow angle, p95 | Lip angle | Contact layer at the end of the march |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Coarse | 7680 | 1.5 / 6.9 % | 4.6 % | 30 % | 3.25 deg | 17.87 deg | 0.45 |
| Medium | 30720 | 1.2 / 3.8 % | 1.8 % | 16 % | 1.61 deg | 22.05 deg | 0.29 |
| Fine | 123072 | 1.0 / 2.0 % | 0.99 % | 7.6 % | 0.73 deg | 23.71 deg | 0.18 |

The worst-station boundary difference falls by a factor of 1.83 per halving, at an observed order of 0.87, and extrapolates to zero within 0.03 percent. The mean holds near 1 percent: the 50 percent contour at the end of the march has converged to 0.13 percent, and the march's boundary sits 1.05 percent inside it.

![Near field](results/plume/plumeNearField.png)

![Field difference](results/plume/plumeFieldDifference.png)

### Near field

The worst boundary difference, 2.04 percent, is at the march's first station, 0.019 station radii from the lip and inside the first fine cell, where OpenFOAM's contact layer is still forming; it falls to 1.5 percent by 0.06 station radii, and past 0.25 station radii the worst is 1.19 percent. The largest field differences lie in a band 0.2 to 0.3 station radii inside the boundary, from half a station radius downstream: the barrel shock forming. Both solutions carry a Mach peak and a compression there. At the end of the march OpenFOAM's pressure rises from 0.43 to 0.66 of ambient between 1.36 and 1.51 station radii, while the march's Mach number drops from 5.08 to 4.81 between 1.46 and 1.51. The Minmod scheme spreads the compression over about six cells and starts it inward of the march's steeper one, so along the band's inner edge the march's Mach number runs up to 4 percent above OpenFOAM's and its pressure up to 36 percent below. Away from the band the two agree to a few tenths of a percent.

The lip angle measures the first half station radius of the fan. OpenFOAM's rises from 17.9 to 23.7 degrees with refinement and extrapolates to 24.79 degrees, against the march's 24.86; the grid convergence index of 5.7 percent (1.4 degrees) bounds that agreement. The march's own first segment leaves at 17.4 degrees. The Prandtl-Meyer turn from the station's edge to the ambient pressure, 27.2 degrees at the chamber gas, is the boundary's slope at the lip itself, which bends back toward the axis within the first cells.

![Boundary](results/plume/plumeBoundary.png)

### Structure

On the axis the march and OpenFOAM agree to 0.005 percent upstream of 3.2 station radii, where the lip's expansion first reaches the axis in OpenFOAM. The march's arrival is steeper and about 0.4 station radii later, a 2.9 percent difference at 4.3 station radii; past it, to the end of the march at 10 station radii, they agree to 0.47 percent. The Mach number on the axis rises to 6.14 at 12.7 station radii and falls to 2.81 across the reflected shock, with no subsonic cell on any grid. The reflection moves 0.055 station radii over the fine grid's averaging window.

The boundary widens to 2.22 station radii at 8.1 and narrows to its first neck, 1.31 station radii, at 18.7. NOVA's correlated boundary, a sinusoid about the lip radius, peaks at 1.93 station radii at 5.7 and dips to 0.22 at 17.1.

![Plume field](results/plume/plumeField.png)

![Axis](results/plume/plumeAxis.png)

| Structure | OpenFOAM, fine grid | NOVA at the chamber gas | NOVA as reported | Chamber gas against OpenFOAM |
| --- | --- | --- | --- | --- |
| Mach disk location | 12.79 (reflection) | 8.05 | 8.05 | -37.1 % |
| Mach disk diameter | none | 9.38 | 9.38 | |
| First shock cell length | 18.72 | 20.00 (Prandtl); 18.68 (Pack) | 22.78 | +6.9 %; -0.2 % |
| Widest boundary radius | 2.222 | 1.927 | 1.927 | -13.3 % |
| Boundary angle at the lip [deg] | 23.71 (24.79 extrapolated) | 27.55 | 30.32 | |

### Steadiness

The inflow carries 21.7586 kg/s against the march station's 21.7598, a difference of 0.005 percent, and holds it to machine precision. The jet's structure is steady; the ambient is not. On the fine grid 32.2 kg/s enters through the far field and 45.9 kg/s leaves through the outlet, so the domain gains 8.1 kg/s, 37 percent of the jet's flow. That is 0.3 percent of the domain's 6.5 kg of gas over the 2.5 ms window, about 15 Pa of ambient pressure. To meet the 0.2 percent criterion the ambient's pressure would have to change by less than 0.7 percent per second, which an ambient with a 16 ms acoustic period, disturbed by the start-up, does not reach in tens of milliseconds. The criterion suits the nozzle's closed walls more than an open ambient.

The flow in through the far field is entrainment. An inviscid jet entrains nothing, but the smeared contact layer drags ambient gas along with the jet, and the far field replaces it; on the coarse grid the ambient beyond 5 station radii moves at about 20 m/s. It is 29 kg/s on the coarse grid, 65 on the medium and 32 on the fine, following the ambient's settling more than the grid. The boundary pressure averages 1.6 percent from ambient on the fine grid, 7.3 percent on the coarse.

![March mass flow](results/plume/plumeMarchMass.png)

![Mass flow](results/plume/plumeMassFlow.png)

![Grid convergence](results/plume/plumeGridConvergence.png)

## Findings

**NOVA's march starts short of the wall.** `plume.plumeExitLine` builds the march's first station from the rows of the characteristic mesh that cross the exit plane, and the outermost row crosses at 0.9826 of the lip radius. The station carries 3.5 percent less area than the exit plane and 21.76 kg/s against the 22.83 kg/s NOVA reports for its nozzle, 4.7 percent less. The gap is the near-wall flow, which the nozzle's exit sampler reaches and the plume's does not. Extending the station to the wall with the nozzle's near-wall state would close it; until then every plume output, the march's boundary included, belongs to a jet 4.7 percent lighter than the nozzle's.

**The march's boundary holds past its reach.** Inside two station radii the march matches the Euler solution within the grid's error. Past them its mass flow drifts (-5.8 percent at 4 station radii, -16 at 6, -34 at 8), as NOVA's trust limit says, yet its boundary stays within 1.0 percent at 4 station radii and 2.3 percent at 6, and its axis within 0.5 percent to 10 outside the expansion's arrival. The drift belongs to the interior field near the boundary; the boundary's position and the axis hold much longer. A trust limit set on the boundary alone could reach about 6 station radii.

**The Mach disk correlations do not fit this nozzle.** Ashkenas and Sherman fitted x / D* = 0.67 sqrt(P0 / Pa) to sonic orifices and nozzles [1]; NOVA applies it with the throat diameter to a Mach 4.2 exit at P0 / Pa = 1379. The case's barrel shock reaches the axis at 12.8 station radii, and NOVA's own march, run to 10 station radii, passes the correlated 8.05 with the axis Mach number at 5.4 and rising, in agreement with OpenFOAM. The diameter correlation, D / De = 1.78 log10(P0 / Pa) - 0.98 [2], gives 4.6 exit diameters at this pressure ratio, twice the jet's widest diameter, which no jet can contain. Inviscid theory does not allow a converging conical shock to reflect regularly from the axis [6], so a Mach disk is expected; the case resolves none, which puts any disk below the grid's resolution at the reflection, about 0.05 station radii axially and 0.025 radially, and under 1 percent of the correlated diameter.

**NOVA's correlations use a different gas from its march.** `plume.solvePlumeStructure` takes CEA's exit ratio of specific heats, 1.257, when the CEA result is present, and the march runs at the chamber's 1.1475. The reported shock cell length is 22.8 station radii and the lip turn 30.3 degrees; at the chamber gas, with NOVA's own functions, they are 20.0 station radii and 27.6 degrees. At the chamber gas Prandtl's coefficient is 6.9 percent long against OpenFOAM, and Pack's 40-term coefficient of 1.22 lands within 0.2 percent. Which gas is right is a question of the thermochemistry; that the correlations and the march disagree on it is a fault either way.

**The correlated boundary is set by its amplitude cap.** The correlated boundary is a decaying sinusoid about the lip radius with amplitude L tan(turn) / 2 pi. At the reported cell length and turn that is 0.663 m, and NOVA holds it to 0.95 of the lip radius, 0.302 m, so that the sinusoid stays off the axis. The widest radius, 1.93 station radii, is therefore the cap's, 13.3 percent narrow against OpenFOAM's 2.22; uncapped it would be about 3.0, 35 percent wide. The sinusoid then carries the boundary down to 0.22 station radii at its first neck, where OpenFOAM's neck is 1.31. NOVA flags the cap with `boundaryAmplitudeLimited`; the march's boundary, where it is solved, is the better output.

**`PlumeField.lipTurnAngle` is never set.** It is declared in `plume.py` with a default of 0.0, and no code assigns it, so every reader gets zero; `examples/novaNozzle.py` prints it as a lip turn angle of 0.00 degrees.

## Validation status

The case is a cross-check between two unvalidated tools, not a validation. Neither OpenFOAM's `rhoCentralFoam` with this mesh, limiter and boundaries nor NOVA's march has been compared here with a measured underexpanded jet or an exact solution of one. Their agreement within the march's reach shows that the two methods, from the same starting data and under the same physics, produce the same near field; it does not show that either matches a real jet. Both solve the Euler equations, so neither carries the turbulent mixing layer that thickens a real plume's boundary. The correlations are the opposite case: each is a fit to measurements, which NOVA applies outside the conditions they were fitted to.

Sanity checks in place of a validation:

- Mass: the inflow carries the march station's mass flow to 0.005 percent.
- Limiting case: on the axis, upstream of where the lip's expansion arrives, both solutions hold the station's Mach 4.2033 to 0.005 percent.
- Grid convergence: three grids at a refinement ratio of 2, with both grid criteria met and the near-field differences falling toward zero with refinement.
- Steadiness of the jet: the shock reflection moves 0.055 station radii over the averaging window. The ambient fails the steadiness criteria, for the reasons in [Steadiness](#steadiness).

Closing the gap needs a measured supersonic underexpanded jet run through the same setup. The axisymmetric free jets of Love et al. [5] give jet boundaries and shock positions for supersonic nozzles at known exit Mach numbers and pressure ratios; agreement there, with this mesh, limiter and boundary treatment, would make the case a validation of the march's near field and a measured reference for the Mach disk.

## References

[1] Ashkenas, H., and Sherman, F. S.: *The Structure and Utilization of Supersonic Free Jets in Low Density Wind Tunnels*. Rarefied Gas Dynamics, 4th Symposium, vol. 2, Academic Press, 1966, pp. 84-105. x / D* = 0.67 sqrt(P0 / Pa), fitted to sonic orifices and nozzles; see `docs/references_plumeStructure_2026-09-04.md`.

[2] *Mach-Disk Formation and Shock-Structure Transitions in Underexpanded Coflowing Jets*. arXiv:2608.18923, <https://arxiv.org/html/2608.18923>. D_MD / De = 1.78 log10(NPR) - 0.98, fitted to coflowing jets.

[3] Powell, A.: *On Prandtl's Formulas for Supersonic Jet Cell Length*. International Journal of Aeroacoustics, vol. 9, no. 1-2, 2010, p. 207. Prandtl's 1904 first-term coefficient 1.306 and Pack's 40-term 1.22, for an almost perfectly expanded jet.

[4] Schindler, Castner and Zaman: *A Study of Highly Underexpanded Supersonic Jets in Subsonic Crossflow*. NASA/TM-20210024918, 2022, equation 6: Tam and Tanna's fully expanded jet diameter.

[5] Love, E. S., Grigsby, C. E., Lee, L. P., and Woodling, M. J.: *Experimental and Theoretical Studies of Axisymmetric Free Jets*. NASA TR R-6, 1959. <https://ntrs.nasa.gov/citations/19980228067>

[6] Courant, R., and Friedrichs, K. O.: *Supersonic Flow and Shock Waves*. Interscience, 1948. A conical shock with converging flow behind it cannot reflect regularly from the axis; as cited by Hew, J. K. J., Ogawa, H., and Boswell, R. W.: *Centreline Shock Reflection Phenomena for Supersonic Internal Flows in the Non-Rankine-Hugoniot Zone*, arXiv:2209.13453, 2022.

## Files

| File | Purpose |
| --- | --- |
| `makePlumeCase.py` | Solves NOVA with its plume, writes `reference/novaPlume.json` and a case folder for one grid |
| `setPlumeInflow.py` | Writes NOVA's exit station into the inflow, and the starting column on the coarse grid; copied into each case |
| `comparePlume.py` | Compares a converged case with NOVA's march and correlations and judges the criteria; copied into each case |
| `plumeGridConvergence.py` | Richardson extrapolation and grid convergence index across the three grids; copied into each case with `gridConvergence.py`, whose estimate it uses |
| `compareWithNova.py` | The nozzle case's comparison, whose readers and figure style the plume comparison imports; copied into each case |
| `reference/novaPlume.json` | NOVA's plume: gas, exit station, the march at the shipped reach (every node) and at 10 lip radii (boundary, axis and mass flow), the correlated structure as reported and at the chamber gas |
| `results/plume/` | The comparison of each grid, the fine grid's figures and the grid study |
