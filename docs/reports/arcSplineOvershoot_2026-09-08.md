
# arcSpline: overshoot at a corner

`arcSpline` resamples a curve onto points spaced evenly along its own arc length. Every contour NOVA builds passes through it, at ten call sites: the diverging wall, the converging stitch, the regen section and extension, the channel interfaces and turnarounds.

It fitted an unconstrained C2 cubic. This records what that did, what replaced it, and by how much the results moved.

---

## The defect

A C2 interpolant through a curve with a genuine corner has to overshoot. Continuity of curvature across a point where the curvature is really discontinuous can only be bought by bending the curve out past the data on both sides. It is not a defect in scipy; it is the wrong interpolant for the data.

NOVA hands `arcSpline` stitched curves routinely, and a stitch is a corner.

Measured on the shipped `regenExample` configuration, by recording every point set `arcSpline` was asked to fit during a run:

| Call site | Points | Worst excursion outside the data |
|---|---|---|
| `contour`: diverging wall | 148 → 100 | 0 |
| `chamber`: converging stitch | 149 → 100 | 0.0041 mm |
| `regenStations`: regen section | 100 → 60 | 0.286 mm |
| `regenStations`: extension | 54 → 60 | 0.058 mm |
| `regenChannels`: interfaced regen nozzle | 383 → 60 | **6.36 mm** |

The last one is the important row. Its worst excursion is 6.36 mm at a station whose radius is 83.42 mm, which is 7.6 percent of the local radius, and the resampled contour's minimum radius came out at 0.05076 m against an input minimum of 0.05086 m. The fit returned a wall radius that no input point supports, on the mainline regenerative path, in every cooled run.

On the sunken converging section the same mechanism was fatal. That stitch is a dense ellipse, a dense arc, a single isolated conic control point, then a dense wall. The spline rang across the isolated point and put sixteen of sixty contour points below the throat radius, the worst 15.6 mm inside it. An area ratio below one has no subsonic solution, so the run failed two hundred lines downstream in the Mach solver rather than at the geometry that caused it.

A second, unrelated problem in the same function: the shipped diverging contour contains a pair of points 6.7e-8 m apart on a curve 1.6 m long, a segment ratio of nine million against the longest. A zero-width parameter interval gives an unbounded derivative.

---

## What replaced it

The fit is now shape preserving by default, a PCHIP interpolant, which cannot leave the range of the points it passes through. Near-duplicate points are dropped before fitting. The arc-length inversion, which was a `solve_ivp` call per output point wrapped in a bare `except` that silently collapsed a failed point to its segment start, is now dense sampling with a trapezoid integral and an interpolated inverse.

`method = 'curvatureContinuous'` restores the C2 fit for a caller that knows its input is smooth.

### Why the choice is made per call site rather than globally

Neither interpolant dominates on accuracy. Against analytic curves, resampling to 60 points:

| Curve | Input points | C2 cubic | Shape preserving |
|---|---|---|---|
| Circular arc | 40 | **3.86e-06** | 6.00e-05 |
| Circular arc | 150 | 3.86e-06 | **3.85e-06** |
| Gaussian bump | 40 | 3.51e-03 | **3.39e-03** |
| Gaussian bump | 150 | 1.39e-05 | **1.15e-05** |
| Two arcs with a corner | 40 | 3.78e-03 | **2.33e-03** |
| Two arcs with a corner | 150 | **8.11e-05** | 1.10e-04 |

On a coarsely sampled smooth arc the C2 fit is fifteen times more accurate. On a corner it is worse, and more importantly it can be categorically wrong rather than merely less accurate: a wall radius below the throat is not an inaccurate answer, it is an impossible one.

So the input declares itself. `contour.py` asks for the curvature-continuous fit, because the diverging wall comes off the characteristic mesh as a single streamline with no join in it and is smooth by construction. Every other caller takes the shape-preserving default, because every other caller is resampling something stitched.

This also avoids a method that switches on a threshold, which would put a discontinuity into the pressure-matching iteration that calls `arcSpline` twelve times per solve.

---

## What moved

The rewritten arc-length machinery is faithful to the original: asked for the curvature-continuous fit, it reproduces the previous output to 2e-10 relative on the smooth contour cases. Every change below is the interpolant, not the resampling.

The diverging contour is preserved, because it kept the C2 fit:

| Quantity | Before | After |
|---|---|---|
| `calculatedExitRadius` (non-dimensional) | 7.839861790292017 | 7.839861788923794 |
| `exitWallAngle` [deg] | 0.15311181587138173 | 0.15311181588896652 |
| `inflectionWallAngle` [deg] | 0.5301661955488559 | 0.5301661955015563 |
| `deliveredAreaRatio` | 40.000000000000014 | 39.99999999999999 |

The stitched contour moves, which is the point:

| Quantity | Before | After | Change |
|---|---|---|---|
| `inletContractionRatio` | 3.1698994 | 3.1672548 | 0.083 % |
| `exitExpansionRatio` | 39.63672 | 39.60365 | 0.083 % |
| `rNozzleWall`, largest element change | | | 0.061 mm |
| `nozzleNearWallPressure`, largest element change | | | 1100 Pa |

The residual 1e-6 movement in the characteristic mesh is convergence noise: `arcSpline` runs inside the pressure-matching loop, so a 2e-10 change per call lands the secant solve on a marginally different iterate.

`exitExpansionRatio` reads 0.99 percent below the delivered area ratio of 40 after the change and 0.91 percent below before it. Both are resampling loss rather than a physics difference: a hundred points cannot represent the exit radius exactly, and the shape-preserving fit hugs its data slightly more closely. Measured against the input polyline the new fit is the more faithful of the two at every call site, by a factor of 3.7 at the worst one.

---

## What it unblocked

Driven directly against the `regenExample` diverging contour and chamber thermochemistry, with a throat eccentricity of 0.88, the sunken converging section now returns a 100-point contour with a minimum radius of 0.050464 m against a throat of 0.050320 m, no points below the throat, and a near-wall Mach number running 0.117 at the chamber to 3.787 at the exit. Asking the same solver for the curvature-continuous fit reproduces the original failure exactly: a subsonic area-Mach solve refused at an area ratio of 0.684.

That establishes that the contour closes and the quasi-1D flow solve runs on it. It does not establish that the resulting nozzle is a good one. Nothing has been checked against a reference sunken design, and the cooling correlations carry no correction term for a recessed throat.

---

## Validation

`tests/testArcSpline.py`, 19 tests, covering both what the resampling must do and what it must never do.

Resampling: a straight line is reproduced exactly; a quarter circle sampled non-uniformly comes back at equal angles, which is what equal arc length means there; a helix comes back with chord lengths agreeing to 1e-3; the ends of the curve are held; and deviation from an analytic curve falls by more than a factor of ten when the input is refined tenfold, for both methods.

The guarantee: on a stitch reproducing the sunken pattern, the shape-preserving fit stays inside the range of its input at 10, 60 and 250 output points, and no point falls below the throat. The converse is recorded too, so the reason for the default is not lost: the curvature-continuous fit on the same input puts four of sixty points below the throat.

Degenerate input: exact and near-duplicate points are dropped, wholly coincident input is refused by name rather than returning NaN, and an unrecognized method is refused.

Full suite 646 passed. Harness baselines re-recorded against the changes tabulated above.

---

## Incidental

`arcSpline` ran `solve_ivp` once per output point. Over the sixteen calls a `regenExample` run makes, it took 5.24 s. The vectorized replacement takes 0.030 s, which is 175 times faster, and removes the bare `except` that could silently place a point at its segment start.
