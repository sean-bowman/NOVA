# Feature showcase

Representative plotted outputs for the NOVA nozzle designer, rendered from a single worked case.

## The case

LOX/LH2 upper stage, Pc = 1000 psia, MR = 5.5, expansion ratio 40, 100 kN thrust, truncated ideal
contour at an 80 percent length fraction. Two settings differ from `assets/NOVANozzle.json`:
`Lstar` is 1.0 m so the combustion chamber is generated, and `material` is GRCop-42.

Reproduce with:

```
python featureShowcase/runBaseCase.py      # runs the case, writes showcaseBase.pkl
python featureShowcase/buildShowcase.py    # geometry, flowfield and material figures
python featureShowcase/buildPlumeCases.py  # one plume figure per operating regime
python featureShowcase/buildMocPlume.py    # experimental MOC plume interior
python featureShowcase/buildPlumeMarch.py # the plume march, continued from the nozzle solution
python featureShowcase/buildPlumeSweep.py # the same plume across its usable back pressures, animated
python featureShowcase/buildPlumeThrottle.py # the plume across the engine's throttle range at one altitude
python featureShowcase/verifyContour.py   # contour against its independent references
python featureShowcase/buildContourValidation.py  # sweeps against the Rao chart, about 16 minutes
python featureShowcase/buildContourFamilies.py    # the three families compared, about 40 minutes
python featureShowcase/buildSubfamilyStudy.py     # searched quadratic against cubic, about 2 hours
python featureShowcase/buildReferenceOverlays.py  # contours on their references, about 5 minutes
python featureShowcase/buildFamilyShowcase.py     # the shipped nozzle once per diverging family
python featureShowcase/buildStitchedField.py      # chamber to exit in one frame
python featureShowcase/buildChamberField.py       # chamber and converging section, one dimensional
python featureShowcase/buildModelComparisons.py    # the selectable thermal and gas models, about 4 minutes
python featureShowcase/buildFamiliesReportFigures.py  # figures for the contour families report
python featureShowcase/buildCalorimeter40k.py figures # figures for the 40k calorimeter report
python featureShowcase/buildReport.py             # renders the effort report to HTML
python featureShowcase/buildGuiGraphic.py         # the GUI's plume graphic, banner and icon
python featureShowcase/buildGuiScreenshots.py     # the GUI walkthrough screenshots in docs/images/gui
```

The five slow studies cache what they solve (`contourValidation.npz`, `contourFamilies.npz`, `subfamilyStudy.npz`, `referenceOverlays.npz`, `family_*.pkl`) and take `--draw` to redraw their figures from the cache in seconds.

## Palette

Every figure here draws from `showcasePalette.py`: the Engineering Flat Metal palette in its dark mode, read from `NOVA.palette`, so the showcase, the reports, the figures a run writes and the GUI share one set of colors. Mach number takes the steel ramp, a single cool hue whose lightness rises with Mach; temperature takes gunmetal through bronze to brass; pressure takes a diverging blued steel to rust. `showcasePalette.restyleHtml` sets an HTML report's CSS variables to the same palette, which `buildReport.py` applies to the page documentProcessor writes.

## Figures

| File | Shows |
|------|-------|
| `contour.png` | Wall contour with the generated combustion chamber, throat and chamber diameter called out |
| `modelComparisonsModels.png` | What each selectable model does: the gas-side constant along the wall against Bartz's single value, what roughness buys on the coolant side, Prandtl-Meyer turning under local properties against two constant exponents, and the entrance and curvature corrections |
| `modelComparisonsJacket.png` | The reference jacket solved under each model: hot wall temperature, coolant temperature and the channel the sizing march picked |
| `jacket.png` | One cooling channel and its two neighbors swept against the cold wall, centerline and cross-sections called out on the middle one |
| `nearWallState.png` | Near-wall static temperature, static pressure and Mach number along the axis |
| `fieldMach.png` | Mach number over the characteristics mesh |
| `fieldPressure.png` | Static pressure over the characteristics mesh |
| `fieldTemperature.png` | Static temperature over the characteristics mesh |
| `plume_highlyUnderexpanded.png` | Correlated plume structure, Pe/Pa 10, equal aspect |
| `plume_ideallyExpanded.png` | Correlated plume structure, Pe/Pa 1.0, equal aspect |
| `plume_overexpanded.png` | Correlated plume structure, Pe/Pa 0.6, equal aspect |
| `plume_separated.png` | Correlated plume structure, Pe/Pa 0.3, equal aspect |
| `plumeContinuousField.png` | Nozzle interior and plume as one solution; near empty, see the caution below |
| `contourVerification.png` | The worked case against its references: length, area ratio, near-wall consistency, exit plane |
| `contourFamilies.png` | The three diverging families compared on one engine: truncated ideal, thrust-optimized parabola and searched thrust-optimized contour |
| `subfamilyStudy.png` | The searched thrust-optimized contour, quadratic against cubic wall |
| `familyShowcase_*.png` | The shipped nozzle built once per diverging family: chamber and contour, flow field, jacket and plume |
| `contourValidation.png` | Sweeps over area ratio, percent bell and mesh resolution, against the Rao chart |
| `chamberFieldMach.png`, `chamberFieldPressure.png`, `chamberFieldTemperature.png` | Chamber and converging section, ONE DIMENSIONAL |
| `oneDimensionalAgainstMesh.png` | What the characteristics mesh buys over a one-dimensional solve |
| `referenceOverlays.png` | NOVA contours drawn on the RS-25 envelope, on Rao bells, and on reconstructed engines |
| `stitchedFieldMach.png`, `stitchedFieldPressure.png`, `stitchedFieldTemperature.png` | Chamber to exit in one frame, seam marked |
| `plumeCellTrain.png` | Shock cell train at a parallel exit, validated against Prandtl |
| `plumeExitHandover.png` | The exit plane the march starts from, against the source flow it replaces |
| `plumeOperatingRange.png` | Overexpanded through underexpanded, with the cost of the isentropic lip |
| `plumeOperatingEnvelope.png` | How far the march carries, over exit divergence and pressure ratio |
| `plumeSweep.gif` | The nozzle and its plume over lip pressure ratios 0.75 to 1.8, shaded by Mach number, each frame carrying its own mass continuity error |
| `plumeThrottle.gif` | The same nozzle at a fixed altitude over its throttle range, down to the power level where it separates, with thrust and one-dimensional ideal specific impulse alongside |
| `mocPlumeInterior_*.png` | EXPERIMENTAL method-of-characteristics plume interior, shaded by Mach |
| `mocShockCells_*.png` | EXPERIMENTAL shock cell structure of a mildly off-design jet |
| `materialCurves.png` | Wall property curves behind the material selector, solid where a source measured it and dotted where a value is held flat |
| `materialCryogenicRatio.png` | Conductivity at liquid hydrogen temperature against its room-temperature value, for the five alloys with cryogenic data |
| `*Interactive.html` | The same views as pan-and-zoom plotly figures |

## Reading the figures

**Wall materials.** `materialCurves.png` draws each property solid over the temperatures its
source actually measured and dotted where the nearest measured value is held flat, which
`materials.propertyProvenance` reports per property. The distinction is not cosmetic: a held
value is broadcast across the grid and comes back the same shape as data, so an interpolator
built on one returns a constant and looks exactly like an interpolator built on a real curve.
Temperature is logarithmic so the cryogenic decade is legible beside the hot one, and the
coolant inlet temperatures are marked because that is where every curve used to be clamped.

`materialCryogenicRatio.png` is the size of what that clamping cost. The error has no consistent
sign: pure copper conducts three and a half times better at 20 K because electron scattering
falls away in a nearly perfect lattice, while every alloy conducts three to nine times worse.
Five alloys still have no cryogenic source and are named on the figure. The copper alloys are
the ones worth measuring rather than inferring, since the low-temperature peak is a purity
effect that alloying suppresses.

One thing the figure shows that the numbers hid: GRCop-42's expansion curve drops to 1.5e-6/K
near room temperature, which is an Invar and not a copper alloy. Above 300 degC the curve is
sound. It is left as the source gives it, and its provenance says so.


**Combustion chamber.** The barrel is sized from L\*, `Lbarrel = (L* At - integral of pi r^2 dx) /
(pi Rc^2)`, so the delivered characteristic length matches the requested one. This case gives a
257.7 mm barrel at a contraction ratio of 3.20 and returns L\* = 1.0000 m.

**Characteristics fields.** The contour is a truncated ideal nozzle, so the mesh extends past the
delivered wall out to the full ideal exit. The field panels are clipped to the wall that is
actually built.

**Chamber and converging section.** These are subsonic, so there is no characteristics mesh there
and nothing solves them. What is drawn is the quasi one-dimensional answer: at each station the
local area ratio fixes a Mach number and that value is held across the cross section. Each figure
says so on its face, because they sit beside the diverging-section fields, which ARE solved, and
the two are not the same kind of result. `oneDimensionalAgainstMesh.png` makes the difference
explicit: the near-wall Mach number departs from the one-dimensional value by 42 per cent just past
the throat and by about 5 per cent through the rest of the nozzle.

**Reference overlays.** Only the RS-25 publishes enough dimensional data to overlay, and its three
quoted numbers disagree with each other by 12 per cent, so both readings are drawn. The Rao bell
panel is the only like-for-like shape comparison, because that construction follows exactly from
two angles. The reconstructed panel is not a dimensional claim about any engine: no wall
coordinates are published for the F-1, Vulcain 2 or RL10.

**Stitched fields.** Chamber to exit on one color scale, with the seam at the throat marked. The
two halves are different kinds of result and the figure says so: upstream nothing is solved.
Pressure is drawn logarithmically because it falls three orders of magnitude, and on that scale the
radial gradient in the diverging section is visible, which is the exit-plane non-uniformity behind
the pressure-matching finding.

**Contour verification.** The worked case delivers the area ratio and the length fraction it was
asked for, exactly. See
[NozzleContourValidation.md](../docs/NozzleContourValidation.md) for what that
check does and does not establish, for the comparison against the Rao wall-angle chart, and for
the defects the comparison found.

**Plume.** One figure per regime, each at equal aspect ratio and sized to the plume it draws.
Ambient pressure is set from the nozzle exit pressure so each lands on a chosen Pe/Pa. The Mach
disk is placed from the Ashkenas and Sherman correlation, which is defined for underexpanded jets
only, so it appears in the underexpanded case and nowhere else. Separation follows the Summerfield
criterion, Pe/Pa < 0.4.

Everything in these figures is correlation. The boundary shape is a decaying sinusoid whose
initial slope matches the correlated turning angle; it is not a computed streamline. Its amplitude
is capped so the boundary cannot reach the axis, and where that cap binds the figure says so on
its face: the correlated turning angle for a strongly underexpanded jet implies a swell wider than
the lip radius, so the drawn width understates the plume. Cell spacing and Mach disk location are
unaffected. `PlumeStructure.boundaryAmplitudeLimited` carries the same flag in code.

**Plume interior.** There is no interior field in the shipped model. `plumeStructure` returns a
boundary, cell node positions and a Mach disk, and deliberately solves no interior, because no
correlation in the literature yields one. Coloring the inside of a correlated boundary would be
drawing a picture rather than solving a flow.

The route to a real interior is the free-jet method of characteristics in `experimental/`, and
`mocPlumeInterior_*.png` shows what it currently produces: a Mach field through the expansion, from
the lip out to the jet boundary. It is EXPERIMENTAL and NOT VALIDATED. The net is grid converged,
but plume dimensions come out low against NASA TN D-2327 by roughly a factor of two because the
internal shock that recompresses the over-expanded core is not solved. Each figure states its own
error against the report. See `experimental/README.md`.

**Shock diamonds.** `mocShockCells_machJet3ratio1p5.png` shows the first cell of a mildly
underexpanded jet, M_j 3.0 at p_j/p_a 1.5. Diamonds are the repeated reflection of the lip
expansion fan off the jet boundary and off the axis, and at this pressure ratio those waves have
not yet coalesced into shocks, so the pattern is isentropic and the characteristics net resolves
it with no shock capturing. The bright focus on the axis at x/r_j 3.2 is the first diamond node.

At Pe/Pa exactly 1 there is nothing to draw. A perfectly expanded jet is uniform and has no wave
structure; the diamonds exist only off design.

One cell is what the net currently sustains, because the center-line march stalls. See
`experimental/README.md` for why, and for why forcing it further is chaotic rather than merely
approximate.

## The plume march

`Nozzle.py` carries a method-of-characteristics march that continues the nozzle solution past the
lip. Inside the nozzle the outer boundary is a wall and the contour prescribes the flow angle; past
the lip it is a free streamline at ambient pressure and the angle falls out of the solution.
Nothing else changes, which is why the two halves are one solution rather than a solution followed
by a picture. Its interior point reproduces the contour solver's own relations exactly, and
`tests/testPlumeMarch.py` holds it to that.

**What it is validated against.** Prandtl (1904) gives the shock cell length of an almost perfectly
expanded jet. At a parallel exit near design the march reproduces it to within half a per cent over
fourteen cells, measured as the axial period between successive boundary crests.

That measure matters. The primary wavelength is the period, not twice the distance from the lip to
the first crest. The lip fan throws the boundary wide before the pattern settles, so the first
crest sits about ten per cent further out than half a period, and the naive measure reads about ten
per cent long. NASA TR R-6 separates the primary wavelength from the secondary and records that the
two differ, which shows here as well: over the first few cells the period runs about five per cent
under Prandtl and settles as the march goes on.

**A caution about the contoured case.** `plumeContinuousField.png` carries 1323 plume nodes over 33
lines on the current contour and still reports no mass conservation, because no line it builds
spans the jet from the axis to the free boundary and there is nothing to measure a flux across. It
is a near-lip field, not a plume.

It used to be worse. On the earlier contour the march reached sixteen lines, and before that a
version of the figure showed a full plume with a 31 per cent mass error. Both of those were
artefacts of reading the characteristic mesh under the wrong ratio of specific heats and neither
number should be used. The contour has since changed as well: it now delivers the area ratio and
length fraction it is asked for, where it previously delivered 69.84 against a requested 40. Every
figure on this page is built against the current contour.

What has not changed is the reason the march stops. The exit diverges, and a divergent exit halts
it after roughly one shock cell. That is recorded in
[plumeDevelopmentState.md](../experimental/plumeDevelopmentState.md) as the first open item, and
it is a property of the march rather than of the contour it starts from.

**How to tell a good solve from a bad one.** Every characteristic line spans the jet from the axis
to the free boundary, so every line carries the whole mass flow and they must all carry the same.
The march measures its own departure from that and reports it, which needs no reference outside the
solution and is the only quality number available at an operating point with nothing to compare
against. A parallel exit near design holds 0.03 per cent over a thousand lines; a fourteen degree
exit loses about one. `Nozzle.plumeField` grades itself the same way and sets `trustworthy`
accordingly, and a march too short to measure itself is graded untrustworthy rather than silent.

**Where it stops.** `plumeOperatingEnvelope.png` is the honest map. Near on design and near
parallel the march carries as far as it is asked to. Any real exit divergence stops it after
roughly one cell, when the line stops reaching the boundary and the new boundary point lands on the
one before it. A bell contour leaves the lip at eight to fifteen degrees, so it sits in the part of
that map that does not yet run far; `plumeContinuousField.png` shows how far it does get.

**What it now covers that it did not.** Overexpanded jets, down to the Summerfield separation
criterion of Pe/Pa 0.4, below which the nozzle separates internally and no attached plume model
applies. The lip turns inward through what is really an oblique shock, taken here as an isentropic
compression; at exit Mach 3 the two turning angles agree to 0.2 per cent at Pe/Pa 0.6 and 0.8 per
cent at 0.4, and the stagnation pressure the shock would cost is reported so the size of the
approximation is visible. `plumeMachDisk` locates a disk from the solved field rather than from a
scaling law, as the first center-line station falling to near sonic with the diameter taken out to
the triple point. A net with no shock in it reports no disk, which is the right answer for a mildly
off-design jet.

**What it does not solve.** Coalescence of crossing same-family characteristics is implemented and
is off by default. It fires more readily as compression strengthens, but the crossing test beneath
it scales with mesh spacing rather than with the flow, so it also fires on characteristics that
would not meet for many jet radii. On the one case that validates it costs more than it buys. Even
working, it would give a coalescence inside an isentropic net: no entropy jump, sound while a shock
is weak and degrading as it strengthens. A fitted shock with a proper jump, and the Mach disk with
its triple point and slip line, are further out again.

**Materials.** Solid lines carry measured temperature-dependent data. Dashed lines are held at a
single value across the range. Conductivity is a real curve for every material in the library;
yield strength and CTE are temperature-resolved only for GRCop-42.

## Interactive figures

The HTML views load plotly from a shared `plotly.min.js` beside them rather than embedding it in
each file, which is why the seven views total about 2 MB rather than 30 MB.

## Units

The units utility underpins per-field conversion in the GUI rather than any single figure, so it
has no panel here. Every axis label above carries the unit the quantity is plotted in.
