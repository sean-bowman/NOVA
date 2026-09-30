# Volute generator audit

## Summary

The volute generator builds the surface it is asked for accurately. What it is asked for does not follow volute design practice, and on the shipped configuration the inlet volute intersects the nozzle wall.

Measured on the built geometry rather than on the inputs: cross-section areas match the requested distribution to 0.43 per cent, the shell offset matches the requested wall thickness to better than 0.01 per cent at interior points, and no section is degenerate or non-finite. The geometry kernel is sound.

Four results bear on whether the volute is the right shape:

| Finding | Measured |
|---|---|
| Neither volute reaches the channels it feeds | Ports end 13.18 mm and 12.39 mm short of the scroll |
| Inlet volute intersects the gas-side wall | 1.51 mm at the duct, 2.20 mm at the shell |
| The scroll closes on itself with no cutwater | Tongue section nested inside the throat section, 0.21 mm between walls |
| The area law is not the constant-velocity law | 6.18x the required area at the inlet tongue, 10.85x at the return tongue |
| The feed is undersized for distribution | Velocity head 4.16x the jacket pressure drop at the inlet, 20.2x at the return |

Nine selectable options either raise, do nothing, or silently produce something other than what they name. The printability support cannot be switched on from a configuration file at all.

Nothing in the volute build has been validated against a measured manifold. The comparisons below are against published design rules and closed-form solutions.

## Scope and method

The audit covers `src/NOVA/Volute.py` (the scroll generator) and `src/NOVA/nozzleVolutes.py` (the nozzle-facing wrapper), exercised three ways:

1. **Geometry recovered from the point cloud.** Section areas by Newell's method, perimeters by summed segment length, wall offsets by nearest-point distance from each shell point to the inner section, radial clearance against the interpolated gas-side wall. Every quantity the generator reports is compared against the same quantity measured on the surface it wrote.
2. **Every selectable option, once.** Three cross sections, nine anchors, two scroll directions, four printability settings, eleven area-specification combinations, eleven wall-sizing combinations, five resolutions, both through the `Volute` class and through `solveRegenVolutes`.
3. **Published design rules.** The volute area law, the manifold distribution criterion, the toroidal membrane solution, the alloy data behind the allowable stress, and the LPBF minimum wall.

The case is `featureShowcase/showcaseConfig.json`: a 6.895 MPa chamber, 60 circular channels in GRCop-42, hydrogen coolant at 3.4 kg/s entering at 12 MPa and 30 K, both volutes circular with `outer` alignment and 1 inch Grayloc fittings, 60 cross sections at 40 points each.

## Geometry as built

| Check | Result |
|---|---|
| Section area, drawn against requested | -0.432 per cent at every section, both volutes |
| Hydraulic diameter, 4A/P against reported | -0.324 per cent at every section |
| Area linear in wrap angle | Residual 0.0000 per cent of the maximum area |
| Wall offset at interior points | 0.00 per cent error against the requested thickness |
| Wall offset at each section's first and last point | Up to 0.33 per cent of the thickness |
| Non-finite points, degenerate sections | None |

The area deficit is the inscribed polygon. A closed curve of 40 points has 39 chords, and the polygon they enclose is smaller than the circle by `1 - (39/2 pi) sin(2 pi/39)`, which is 0.432 per cent; the perimeter ratio gives 0.324 per cent on `4A/P`. Both measured values match the closed form to four digits. The bias falls as the square of the point count: 0.105 per cent at 80 points, 0.026 per cent at 160. The consequence is that the reported `crossSectionalArea` is the area of the ideal circle and the duct written to STL is 0.43 per cent smaller, which no output states.

The 0.33 per cent offset error at each section's first and last point is the gap-closure branch in `dynamicEggShell`. It tests the first and last shell point for exact float equality, which a closed circle fails by rounding, then reconstructs the closure point from the intersection of two nearly parallel tangent lines. On a circular section the error it introduces is negligible. On a section with a genuine open end it is doing necessary work.

With a printability support inside the duct the reported area stops being either the ideal or the built flow area. The support area is subtracted and the section radius is grown until the remainder matches the request, but `crossSectionalArea` is then written back as the nominal circle. On the test case that overstates the flow area by 11.8 per cent.

## The scroll closes on itself

The first and last cross sections sit at the same wrap angle, 90.00 degrees on both volutes, because `rollAngle` spans a full 2 pi over the section count. With `outer` alignment both sections are tangent to the same cylinder, so the tongue section is nested entirely inside the throat section:

| | Tongue section radius | Throat section radius | Centres apart | Wall to wall |
|---|---|---|---|---|
| Inlet | 4.07 mm | 12.69 mm | 8.41 mm | 0.21 mm |
| Return | 5.40 mm | 12.69 mm | 7.12 mm | 0.18 mm |

There is no cutwater between them and no end face on either section, so the duct is a closed annular manifold joined through a 0.2 mm lip. A monotone area taper is the design law for a scroll with a cutwater, where the flow passes each station once. In a closed ring the flow divides at the feed and reaches every station from both directions, and the area law that follows is symmetric about the feed rather than monotone.

No feed port is generated. `expandedHydraulicDiameter` sets the largest section area and nothing else; the Grayloc connection is implied, and the face it would attach to is the one the tongue section is nested inside.

## The scroll does not reach the channels

Sixty channels end in mid air. The flare carries each channel radially off the wall to its last
centerline station, and the scroll is placed from a station two positions inboard of that, so the
port and the duct never meet:

| | Nearest scroll point to the channel port | Port radius | Short by | Sections containing the port |
|---|---|---|---|---|
| Inlet | 16.89 mm | 3.71 mm | 13.18 mm | 0 of 60 |
| Return | 16.89 mm | 4.50 mm | 12.39 mm | 0 of 60 |

The gap is the placement index. `rChannelCenterline2D[-3]` sits two stations inboard of the flare
end, and consecutive stations along the flare differ by 8.4 mm in radius, which is the 16.89 mm
measured at both ends. The squircle branch places its scroll from the flare end instead and so
does not share the defect, which is why it also reads a different wall clearance.

Nothing reports it. The volute build checks that the channels exist and that their radii are
positive, and then grows a scroll wherever the index lands.

## Interference with the nozzle wall

Radial clearance between every volute point and the gas-side wall at the same axial station:

| Surface | Minimum clearance | Points inside the wall |
|---|---|---|
| Inlet volute duct | -1.51 mm | 30 of 2400 |
| Inlet volute shell | -2.20 mm | 48 of 2400 |
| Return volute duct | +5.66 mm | 0 |
| Return volute shell | +4.90 mm | 0 |

The inlet volute occupies radii from 79.5 mm to 104.9 mm across an axial span of 43.3 mm to 68.6 mm, where the diverging wall runs from 71.6 mm to 86.4 mm. The intersection is at the innermost points of the largest sections.

The cause is the combination of `outer` alignment, which grows the section inward from the scroll radius, and the scroll radius itself, which is read as `rChannelCenterline2D[-3]`. That index falls inside the interface flare, where consecutive stations differ by 8.4 mm in radius:

| Index | -4 | -3 (used) | -2 | -1 |
|---|---|---|---|---|
| Radius | 96.57 mm | 104.91 mm | 113.35 mm | 121.79 mm |

The flare occupies 6 of the 60 channel stations at the inlet end and 8 at the return end, and those counts are derived from the flare geometry and then re-derived after resampling. The scroll radius is therefore a function of station count rather than of the geometry, and a one-station shift moves it further than the interference it currently has.

Alignment alone resolves it on this configuration:

| Alignment | Inlet clearance |
|---|---|
| `o` (shipped) | -1.51 mm |
| `s` | +3.77 mm |
| `no` | +7.47 mm |
| `c` | +11.19 mm |
| `n` | +18.63 mm |
| `i` | +23.89 mm |
| `ni` | +25.43 mm |

An egg cross section clashes by 1.02 mm. A squircle clears by 37.51 mm: the wrapper carries a separate placement branch for it, which sets the scroll radius from the flare end and the local channel radius rather than from a station index, putting it at 118.79 mm instead of 104.91 mm. The two placements are 13.88 mm apart, so the rest of the clearance difference is in how the squircle section sits on its anchor.

## Option matrix

Every selectable option, exercised once. `silent` means geometry was produced without the requested behaviour and without an error.

| Option | Value | Result |
|---|---|---|
| `crossSectionType` | `circle`, `egg`, `squarc` | Build |
| | Unrecognized, or `Circle` | **silent**: empty arrays, no error. The `match` is case sensitive while every other option is lowered |
| `anchorBy` | Nine documented values | Build |
| | Unrecognized or empty | Centres the section, as the docstring says it will |
| `scrollDirection` | `cw`, `ccw`, `CW` | Build |
| | `clockwise` | Raises |
| `alignWallBy` | `inner`, `outer` | Build |
| | With `outer` and a printability support | **Raises** `ValueError`: the per-section offset is applied unindexed at four sites |
| | Unrecognized | Raises |
| `circlePrintability` | `thin`, `thick` | Build with support surfaces |
| | `on` | **silent**: no support. Configuration converts the boolean `True` to `'on'`, so the feature is unreachable from a config file or the GUI |
| | `thin` or `thick` on a squircle | **Raises** `ValueError` and `LinAlgError` |
| `printabilityAngle` | Any value | Used by the squircle only. The circle support hardcodes 30 degrees at four sites, and the circle and egg never read the parameter |
| `wallThickness` | Scalar, or array of the right length | Build |
| | Array of the wrong length | **Raises** `IndexError`. The check exists, and its body is an ellipsis with the raise commented out |
| | numpy scalar | **Raises** `TypeError`: the class test accepts `int` and `float` only |
| `wallHoopStress` | With `pressureDifferential` | Build |
| | Without it, or with `wallThickness` | Raises |
| `scaledBy` | `linear` | Build |
| | `momentum` | **silent**: circle and squircle produce the linear law. Egg raises `AttributeError` |
| | Unrecognized | **silent**: produces the linear law |
| Area specification | Interface and expanded, or orifice count and expanded | Build |
| | Interface and orifice count | **Raises** on a circle, builds on a squircle and an egg |
| | One quantity alone, or none | Raises |
| | Interface larger than expanded | **silent**: builds a scroll that narrows toward the feed |
| `numCrossSections` | 1 | Builds a single section |
| `crossSectionResolution` | 3 | Builds a triangular duct |
| | Any value, on an egg | Ignored: 24 requested returns 152 points |
| `progressbar` | `off` | Honoured by the egg only. Circle and squircle print a tqdm bar unconditionally |

Further defects found by reading:

- `crossSectionArea` is declared in `__init__` and never written. The generators write `crossSectionalArea`, which is not declared. The declared attribute stays an empty list.
- `numOrifices` is replaced by the area ratio during the build, so an integer count passed in comes back as a float that is not a count.
- `hoopStressCalculator` leaves its mode flags unbound when both or neither of `thickness` and `hoopStress` are given, raising `UnboundLocalError` instead of validating.
- No volute key is validated in `config.py`. The channel keys are checked against rules; the twenty volute keys are read and passed through.
- `voluteFOS` is set to 1 in `Nozzle.py` and is not a configuration key.
- The exporter is handed `xVolute[1:]`, so the STL is one cross section shorter than the computed scroll.
- `writeFacet` normalizes each facet normal with no guard, writing NaN normals for degenerate facets. The support export raises a divide warning on every run.
- No volute pressure drop enters the coolant circuit. `regenThermal.py` mentions volutes only in two roughness docstrings. The interface flare is part of the channel path and carries friction and bend losses; the scroll carries none.

## Area law

The published law for a scroll that distributes or collects evenly around its wrap is that the area at angular position `theta` from the tongue carries the fraction `theta/360` of the throat flow, so `A(theta) = A_throat theta/360`. Huzel and Huang give it as equation 6-69 for a plain pump volute; it is Stepanoff's constant-velocity rule.

NOVA's area is linear in wrap angle, which is the right form, with a tongue intercept that is not. The intercept is set by the channel port: `interfaceHydraulicDiameter` is the port equivalent diameter times 1.1 at the inlet and 1.2 at the return. The constant-velocity law asks for the throat area divided by the channel count.

| | Tongue area built | Law at 60 channels | Ratio |
|---|---|---|---|
| Inlet | 52.21 mm2 | 8.45 mm2 | 6.18 |
| Return | 91.62 mm2 | 8.45 mm2 | 10.85 |

Built area over the law, around the wrap:

| Position from the tongue | 0 deg | 36 deg | 180 deg | 360 deg |
|---|---|---|---|---|
| Inlet | 6.18x | 1.67x | 1.08x | 1.00x |
| Return | 10.85x | 2.26x | 1.16x | 1.00x |

What that does to the velocity, on the assumption that each of the 60 channels takes an equal share:

| | Tongue | Feed | Ratio |
|---|---|---|---|
| Inlet | 14.6 m/s | 90.3 m/s | 6.18 |
| Return | 40.4 m/s | 438.7 m/s | 10.85 |

A constant-velocity scroll holds that ratio at 1.00. The scroll as built is a diffuser: the inlet decelerates by a factor of 6.2 between the feed and the tongue, and the return accelerates by a factor of 10.9 between the tongue and the feed.

The other published law, Pfleiderer's constant angular momentum, requires `A(theta)/r(theta)` to be linear through the origin. On a scroll of fixed radius the centroid radius varies only because the section grows off its anchor, by 9.4 per cent at the inlet and 6.7 per cent at the return, so the two laws coincide to within that on this geometry. The choice between them is second order beside the 6x to 11x departure from both.

## Distribution criterion

The criterion for even distribution between branches is that the pressure change along the manifold, dynamic head included, is small against the pressure drop across one branch. Bajura and Jones give the governing equations; the practical form is the ratio below.

| | Feed velocity | Mach | Velocity head | Head over jacket drop |
|---|---|---|---|---|
| Inlet | 90.3 m/s | 0.065 | 303 kPa | 4.16 |
| Return | 438.7 m/s | 0.381 | 1472 kPa | 20.24 |

The jacket pressure drop is 72.71 kPa, 1.05 per cent of chamber pressure. Both volutes therefore carry several times more velocity head than the channels carry pressure drop, with the ratio the wrong side of unity by 4x and 20x. Huzel and Huang put the pressure recovery of a pump volute at 70 to 90 per cent of the flow kinetic energy, so most of that head appears as a static pressure difference between the channels near the tongue and those near the feed.

A one-dimensional distribution model over the 60 channels, with each channel a quadratic resistance calibrated on the design drop and the scroll static pressure taken from its recovered dynamic head, does not converge to a physical distribution at these ratios: it drives nearly all the flow into the channels nearest the tongue. That divergence is the result. The geometry is outside the regime in which a manifold behaves as a distributor, and no distribution number should be quoted from it.

Two independent criteria give nearly the same feed size:

| Criterion | Inlet bore | Return bore |
|---|---|---|
| Velocity head at 10 per cent of the jacket drop | 64.5 mm (2.54 in) | 95.8 mm (3.77 in) |
| Velocity head at 25 per cent of the jacket drop | 51.3 mm (2.02 in) | 76.2 mm (3.00 in) |
| Taper ratio equal to the channel count | 63.2 mm (2.49 in) | 83.7 mm (3.29 in) |
| Shipped | 25.4 mm (1.00 in) | 25.4 mm (1.00 in) |

The two are not independent by accident: making the taper match the channel count is making the tongue carry one channel's flow at the feed velocity, which is the same statement as holding the velocity head down once the tongue area is fixed by the port.

Part of the ratio is the jacket, not the manifold. A channel pressure drop of 1.05 per cent of chamber pressure is low, because the channels are sized to hold wall temperature and end up large. A manifold feeding a jacket with that little resistance has to be correspondingly generous.

## Wall

### Against the toroidal membrane solution

The code sizes the wall with the straight-cylinder relation `t = p D / (2 sigma)` evaluated on the section hydraulic diameter. A scroll is a torus. For a toroidal shell of tube radius `a` on a bend radius `R`, the membrane stress around the tube is

    sigma = (p a)/(2 t) (2R + a sin(phi))/(R + a sin(phi))

which tends to `p a / t` as `R` grows, recovering the cylinder. The maximum is at the inner crotch, `sin(phi) = -1`, so the thickness required there exceeds the cylinder relation by `(2R - a)/(2(R - a))`.

| | Tube radius | Bend radius | Correction | Built | Required |
|---|---|---|---|---|---|
| Inlet | 4.08 to 12.70 mm | 92.2 to 100.8 mm | 1.021 to 1.080 | 0.192 to 0.597 mm | 0.196 to 0.645 mm |
| Return | 5.40 to 12.70 mm | 108.3 to 115.6 mm | 1.025 to 1.066 | 0.325 to 0.764 mm | 0.333 to 0.815 mm |

The built wall is 7.4 per cent thin at the worst inlet section and 6.2 per cent thin at the worst return section. Thin-wall membrane theory is valid here: the worst `t/a` is 0.060.

### Allowable stress

The allowable is GRCop-42 0.2 per cent yield from manufacturer data, interpolated on a cubic spline, divided by `voluteFOS`.

| Temperature | Spline | Status |
|---|---|---|
| 20.0 K | 261.2 MPa | Extrapolated |
| 30.0 K | 255.3 MPa | Extrapolated |
| 50.0 K | 244.4 MPa | Extrapolated |
| 77.6 K | 231.0 MPa | Lowest datum |
| 293.0 K | 178.0 MPa | Interpolated |

Three things follow. The inlet volute is sized at the coolant inlet temperature of 30 K, which is 48 K below the lowest datum, on a spline that extrapolates without saying so. `voluteFOS` is 1, so the wall is sized to the full extrapolated yield. And sizing at 30 K gives 1.43 times the allowable that ambient temperature would, so a wall sized for the cold condition is 30 per cent thin for a proof or leak check at room temperature, which is the governing case for the same pressure.

### Manufacturability

The sized wall runs 0.192 mm to 0.764 mm. Published LPBF work on GRCop-84 reports that internal stress limits vertical walls and septa to 1 mm, thinner walls warping during the build. Every section of both volutes is below that, and nothing in the sizing imposes a minimum.

The printability support hardcodes a 30 degree overhang criterion, a 0.75 mm sheet and a 1 mm fillet, while `printabilityAngle` is carried through the configuration and the GUI and read only by the squircle.

## Found outside the volute, on the way

**Six recorded baselines size a 33 mm diameter coolant channel.** The `regenCircle` family jackets
the whole bell to an area ratio near 49, and the channel sizer grows the aft channels until they
hold the wall at 800 K where the heat flux is nearly nothing, bounded only by packing. At 60
channels and 3.4 kg/s that is roughly 0.9 m/s of hydrogen in a 33 mm channel. Its consequences
reach the volute twice: the port area of 1040.6 mm2 is double the 506.7 mm2 the 1 inch fitting
gives, so those baselines already carried scrolls that narrow 2:1 toward the feed, and a constant
velocity scroll feeding a port that size needs a 199 mm bore as a ring or 282 mm with a cutwater.

The sizing bounds are the thing to look at: there is no maximum channel size and no minimum
coolant velocity, so a station with almost no heat flux has nothing to stop it growing. That is
channel work rather than volute work and is not addressed here.

## Validation status

**The geometry is verified, not validated.** Section areas, hydraulic diameters, wall offsets and clearances are checked against closed forms and against the point cloud the generator writes. That establishes the generator builds what it is asked for. It says nothing about whether the shape is right.

**The wall sizing is a hoop stress calculation against manufacturer data**, and the audit adds a closed-form toroidal correction it does not carry. The data itself is a manufacturer curve, spline interpolated, extrapolated below 77.6 K without notice.

**Nothing about the flow is validated.** No measured manifold, no water-flow distribution test, no CFD comparison. The area law and the distribution criterion are compared against published design rules, which is a comparison against practice rather than against data. Closing that gap needs either a flow-distribution measurement on a printed scroll or a CFD solution of the built surface with the 60 channel branches resolved.

## Ranked changes

1. **Attach the scroll to the channels and clear the wall.** Both follow from the same placement: put the tongue section on the port it meets, rather than reading a scroll radius from `rChannelCenterline2D[-3]`, and check the clearance after placement rather than trusting the alignment. The tongue is drawn barely wider than the port, so centring it on the port is the only placement that opens one into the other.
2. **Decide what the scroll is.** A cutwater and an end face make the monotone taper correct and give the feed somewhere to attach. Leaving it a closed ring makes the taper symmetric about the feed instead. The generator currently builds neither.
3. **Size the feed from the flow.** The tongue area is set by the channel port and the throat by the fitting, so velocity is an outcome nothing checks. Deriving the throat from a target velocity head, or from the tongue area times the channel count, ties both ends to the flow and puts the shipped case near a 2.5 inch inlet and a 3 to 3.8 inch return.
4. **Report the scroll velocity and its head against the jacket drop.** One line of output makes the whole class of error visible at build time.
5. **Expose `voluteFOS`, bound the allowable to its data range, and size at the governing temperature.** The ambient proof case asks for 43 per cent more wall than the cold case.
6. **Carry the toroidal correction and a minimum printable wall.** 6 to 7 per cent and a 1 mm floor respectively.
7. **Make the silent paths loud.** Unrecognized cross section, `momentum` scaling, unrecognized scaling, `on` printability, an interface larger than the expanded end, and a wrong-length wall thickness array should each raise.
8. **Fix the raising combinations.** Outer alignment with a support, and squircle supports.
9. **Reach the printability support from configuration.** The boolean that the GUI and JSON carry cannot select either support type.
10. **Report the built area, not the ideal one.** The polygon bias is 0.43 per cent at 40 points, and with a support inside the duct the reported area is 11.8 per cent above the flow area.

## Where the same measurements land after the changes

Every figure below is measured the same way on the same configuration, `showcaseConfig.json`, with
a ring scroll and inner alignment.

| Measurement | Audit | After |
|---|---|---|
| Channel port to the nearest scroll surface | 13.18 mm short (inlet), 12.39 mm (return) | port centred in the tongue section |
| Sections containing the port | 0 of 60 | 60 of 60 |
| Inlet wall clearance | -1.51 mm | +32.3 mm |
| Return wall clearance | +5.66 mm | +40.1 mm |
| Scroll velocity, throat over tongue | 6.18 (inlet), 10.85 (return) | 1.00 by construction |
| Velocity head over jacket pressure drop | 4.16 (inlet), 20.24 (return) | 0.11 (inlet), 0.25 (return) |
| Inlet throat | 506.7 mm2, the 1 inch fitting | 1566 mm2, 44.7 mm bore, from the law |
| Return throat | 506.7 mm2 | 2310 mm2, 54.2 mm bore |
| Feed velocity | 90.3 m/s (inlet), 438.7 m/s (return) | 14.6 m/s (inlet), 48.1 m/s (return) |
| Allowable stress | 255.3 MPa, extrapolated 48 K below its data, at FOS 1 | 118.7 MPa, at the ambient proof temperature, at FOS 1.5 |
| Volute wall | 0.192 to 0.597 mm (inlet), 0.325 to 0.764 mm (return) | 1.000 to 2.472 mm (inlet), 1.000 to 3.003 mm (return) |
| Toroidal crotch correction | absent, wall 7.4 per cent thin | carried per section |
| Area the build reports | the ideal circle only | `crossSectionalArea`, `drawnArea` and `flowArea` |
| Options that raise from inside or do nothing quietly | nine | none |

The distribution criterion is the one that moved furthest. The head a scroll carries relative to
the pressure drop across one channel went from four and twenty times it to a ninth and a quarter,
which is the range the manifold literature asks for, and it came from the area law rather than from
any change to the fitting.

The wall went the other way, thickening by a factor of five at the tongue, and three quarters of
that is the allowable rather than the geometry: sizing at the ambient proof temperature instead of
at 30 K costs 1.30, refusing to extrapolate below the data costs 1.11, and the factor of safety
costs 1.50. The printable minimum then floors the thinnest sections at 1 mm.

## What is still open

**The squircle ignores the alignment.** `anchorBy` is read by the circle alone. A squircle is drawn
with its corner on the scroll radius and grows into one quadrant, so its sections reach the same way
whatever the configuration asks, and the clearance it ends up with is not a choice.

**The circle ignores the cross-section tilt.** `printabilityAngle` is read by the squircle alone,
and the circle's overhang support hardcodes 30 degrees at four sites.

**A cutwater has no tongue wall or end faces.** The sweep leaves the angle for one, and the two
sections that bound it are exposed, but the wall between them is a planar face with a hole in it
and `py2cad` writes surface grids. Closing it belongs in CAD, or in a writer that can triangulate a
face.

**Nothing measures the distribution.** The area law is followed and the head ratio is reported, and
neither is a measurement of how evenly sixty channels are fed. A water-flow test on a printed scroll
or a CFD solution with the branches resolved is what would close it.

## References

Sources and what each establishes are recorded in [references_voluteDesign_2026-09-29.md](../references_voluteDesign_2026-09-29.md).
