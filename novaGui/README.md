# NOVA GUI

A Tkinter front end for the NOVA nozzle design suite. It builds a configuration in the `nozzleConfig.json` schema, runs `Nozzle.generateNozzle()` on a background thread, and presents the result across five tabs.

## Launch

From the repository root:

```bash
python -m novaGui
```

or

```bash
python novaGui/run.py
```

On Windows, `novaGui.bat` at the repository root double-clicks to launch with no console window (it hands off to `pythonw.exe` and exits, matching the `autoClicker/control.bat` pattern). Run `python -m novaGui` from a terminal when a startup traceback needs to be visible.

The main window opens without loading the scientific stack; NumPy, SciPy, Matplotlib, rocketcea and the rest are imported on the first run.

## Tabs

| Tab | Contents |
| --- | --- |
| Config | Every field in the NOVA config schema, grouped into collapsible sections. Dependent fields stay hidden until they apply: the sunken-throat section only for a sunken converging type, the conical half angle only for a conical diverging type, the truncation cut-point field only when a truncation mode is picked, and the cooling and volute fields only once their toggle is on. Fuel, oxidizer and wall material are dropdowns (still typeable for exotic entries); the selected alloy's sampled conductivity, density, modulus, yield and CTE show below it at a chosen temperature. Every dimensioned field carries a unit dropdown that converts in place and hands SI to the backend. Choice fields read as plain language (`Traditional`, `Wall temperature`) and convert to the backend form (`trad`, `temp 1200`) on build. Chamber sizing takes either L* or an explicit barrel length. Load and save JSON, reset to defaults, cross-field warnings. |
| 2D Geometry | The computed wall contour, near-wall exhaust state and exhaust plume structure drawn from the `Nozzle` object, plus the Mach, pressure and temperature field figures written during the run. |
| 3D Geometry | A revolved surface of the contour rendered inline, and the interactive plotly channel-mesh, jacket and volute views embedded through `tkinterweb` with a system-browser fallback. |
| Analysis | Sizing, chamber (barrel length, volume, delivered L*, contraction ratio), delivered performance, station thermochemistry from CEA, and the regenerative cooling summary when a jacket was built. The heat transfer figure is shown beside the table. |
| Export | Chooses the output location and lists the files the last run produced. Double-click a row to open it. |

## How a run works

The run bar hands the form contents to a `PipelineRunner`, which:

- puts `NOVANozzleDesigner` on `sys.path` and imports `Nozzle`,
- forces the Matplotlib `Agg` backend and applies the GUI palette so NOVA's saved figures match the window,
- stops `plotly.offline.plot` from opening browser tabs and silences the tqdm progress bars,
- redirects the output folder to the location set in the Export tab,
- writes the config to `<name>RunConfig.json` and calls `generateNozzle()`.

Program-option flags `export`, `visualizeContour` and `plotsBasic` are forced on for every run so the geometry and analysis tabs have files to read. With cooling channels enabled and the "Interactive 3D views" box checked, `plotsAdv` and `plotJacket` are forced on as well.

Progress printed by NOVA drives the run bar and is mirrored into the collapsible run log.

## Plotting

Two renderers, one description. `NOVANozzleDesigner/figures.py` extracts each figure into a
plain dataclass that mentions neither plotting library, then offers a plotly renderer for it.
`novaGui/plotting.py` renders the same dataclasses with Matplotlib.

Matplotlib draws every inline pane, because it is the only backend that renders into a Tk
canvas and it is a required dependency. Plotly draws the interactive companion, which opens in
the system browser: it pans, zooms and reads values off a mesh far better than a static pane,
and it genuinely cannot be embedded in Tkinter (tkhtml has no canvas or WebGL, and static
export through kaleido needs a separate Chrome install).

Every view in the 2D tab has an **Open interactive** button, and the 3D tab's revolved contour
uses its **Open in browser** button the same way. Both grey out when plotly is not installed.
A run also writes the HTML companions beside its PNGs automatically.

## Display scaling

`theme.enableDpiAwareness()` runs before the Tk root is built so Windows composites the window
at native resolution instead of upscaling a 96 dpi bitmap. `theme.applyTheme` then reads the
real screen DPI, sets `tk scaling`, and rebinds every font to its scaled size; `theme.uiScale`
and `theme.scaled(px)` carry that factor to window geometry, wrap lengths and Matplotlib
figure DPI. At 100 % scaling the factor is 1.0 and nothing changes.

## Run progress

`progress.py` maps the pipeline's own banners and tqdm bars onto a 0-1 fraction. The stage
table is built per run, so cooling and volute stages only count when those are enabled. The
run bar shows the current stage, a determinate progress bar, and the latest output line, so a
run is legible without opening the log. Between banners the bar eases toward the current
stage's ceiling: the method-of-characteristics solve is silent for tens of seconds and a
motionless bar reads as a hang.

## Units and materials

`novaGui/units.py` holds the per-field unit tables (pressure, length, force, temperature, angle, mass flow). Each numeric field stores and submits its value in NOVA's SI unit; the dropdown only changes the display, and switching it converts the shown number so the physical quantity is preserved.

The wall material picker and its property panel read `NOVANozzleDesigner/materials.py` directly (numpy only, no CEA), sampling `sampleWallMaterial(name, temperature)` for the info line.

## Dependencies

Everything in `dependencies.txt`. `tkinterweb` is the only addition beyond what a JSON-driven NOVA run already needs; without it the 3D tab still works through the revolved contour and the browser button.
