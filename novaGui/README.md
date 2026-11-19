# NOVA GUI

The front end for the NOVA nozzle design suite: a React app served by a FastAPI layer over the Python backend, in a desktop window. It builds a configuration in the `NOVANozzle.json` schema, runs `Nozzle.generateNozzle()` in a worker process, and shows the result beside the form: the Design form on the left, the last finished run's figures or results table on the right, and a run bar that steps through the run's stages.

The package also holds every piece of a front end that is not drawing widgets: the config schema, the form checks, the units, the runner, the progress model, the view list, the Matplotlib drawers, the result table, the output categories and the palette. The Tkinter front end it replaced, [legacy/novaTk](../legacy/novaTk/README.md), draws its widgets over these same modules.

## Launch

From the repository root:

```bash
python -m novaGui               # desktop window (pywebview hosting WebView2)
python -m novaGui --browser     # the system browser instead
```

On Windows, `novaGui.bat` at the repository root double-clicks to launch with no console window. Without a console the launcher writes its output to `%TEMP%\NOVA\novaGui.log`, replaced at each launch, so a failed start leaves its traceback there.

The Python side needs FastAPI, uvicorn and pywebview: `pip install -e .[web]`. pywebview uses the WebView2 runtime that ships with Windows 11.

## Build

The server serves the built front end from `novaGui/frontend/dist/`, which git ignores. Build it once, and again after any change under `frontend/src/`:

```bash
cd novaGui/frontend
npm install
npm run build
```

Node is needed to build, not to run.

## Development

Two terminals, with hot reload on the front end:

```bash
python -m novaGui --api         # the API alone on 127.0.0.1:8765
cd novaGui/frontend && npm run dev     # Vite on http://localhost:5173, proxying /api to 8765
```

`npm run typecheck` runs the TypeScript compiler alone.

## Architecture

Three processes take part in a run:

| Process | Role |
| --- | --- |
| Window | WebView2 (or a browser) running the React app. Holds the form state and the config in backend values (SI). |
| Server | `server.py`, on 127.0.0.1 at a free port. Serves the app, evaluates the form's dependency predicates and cross-field checks, reads the material store, starts and cancels runs, streams run events, keeps the recent runs, draws the views, builds and compares the result tables, previews the outputs and copies the ones chosen for export. |
| Worker | `worker.py`, one per run, started with `spawn`. Runs `runner.PipelineRunner`, sends the figures the contour stage settles when that stage ends, then pickles the finished `Nozzle` into the run's staging folder. |

A run is a separate process so it can be cancelled: the server terminates it. RocketCEA's machine-wide `nova.lock` is an `msvcrt` byte lock, which Windows releases when the process ends, so a cancelled run does not hold up the next. Each run writes into its own folder under `%TEMP%\NOVA\web<pid>\`, removed when the window closes; `runner.clearStaging` removes one a crashed server left behind after twelve hours.

Run events (log lines, progress, status, a running run's settled figures, the result, changes to the kept runs, saved preferences) reach every window as Server-Sent Events. Each connection opens with a snapshot of the session, so a reload mid-run picks up where the run is, and a popped-out figure window hears the same events as the main one.

## Modules

| Module | Holds |
| --- | --- |
| `server`, `session`, `worker`, `__main__` | The HTTP routes, the run session that relays a worker's messages, the worker process, and the launcher |
| `configSchema` | The Design form: sections, fields, selectors, folds, defaults, examples, dependency predicates |
| `schemaJson` | The schema as JSON for the browser, and the predicates evaluated on a posted config |
| `design` | The cross-field checks and the rows they name, the wall alloy's sampled properties, the extension material's store note and fill |
| `units` | The unit table, reduced to `si = scale * shown + offset` per display unit |
| `runner` | The run itself: forced program flags, the staging folder, headless figures, the progress reporter, the output listing |
| `progress` | `RunProgress`, which folds a run's progress events into the stage tree the stepper and the stage list draw, and into the legacy window's single bar |
| `viewCatalog` | The views a run can produce, in menu order, and the test of which ones it produced |
| `plotting`, `thermalPlots` | The Matplotlib drawers, the plotly builder for each view, and the jacket, film and extension accessors |
| `coolingFigures` | Plotly figures for the nine cooling views |
| `views` | Each view rendered for the browser: plotly JSON, with a second run drawn over a line plot or from a running run's settled figures, or the Matplotlib drawing as PNG |
| `analysis` | The result table, its headline numbers, the figure that shows each row, and two runs' tables side by side |
| `outputs` | The output categories, and listing, previewing (an STL read into vertices and triangles), copying and opening a run's files |
| `themeColors`, `paletteCss` | The palette in both modes with its Matplotlib styling, and the stylesheet written from it |
| `settings`, `backend` | The saved theme mode and form width, and lazy access to NOVA's figures and material store |
| `assets/` | The plume mark in each mode, the window icon and the nozzle outline |

The legacy Tkinter front end imports `configSchema`, `design`, `units`, `runner`, `progress`, `viewCatalog`, `plotting`, `thermalPlots`, `analysis`, `outputs`, `themeColors`, `settings`, `backend` and the assets, so both front ends build the same config, raise the same problems in the same words, list the same results and draw the same static figures.

The schema's `showWhen` and `expandWhen` predicates are Python functions. The browser receives each row's static description with a `conditional` flag and posts its config to `/api/schema/state`, which returns the rows and sections to hide, the sections to open, and the cross-field problems with the rows they name.

The cross-field checks warn rather than block: Generate with problems open asks whether to run anyway. The one check left to the form itself, a required selector option left blank, runs in the browser's selector row, where it blocks the run with the entries that do not parse.

## How a run works

Generate hands the form's config to a worker, whose `PipelineRunner`:

- imports `Nozzle` from the installed `NOVA` package,
- forces the Matplotlib `Agg` backend and sets NOVA's figure mode (`NOVA.palette.setFigureMode`) to the window's, so the figures the run writes match the theme it started in,
- sets `NOVA_HEADLESS` so no figure opens a window or a browser tab,
- sends the outputs to the run's staging folder,
- writes the config to `<name>RunConfig.json` and calls `generateNozzle()` with a `NOVA.progress` reporter installed, which forwards the run's progress events.

The runner calls a stage hook with each progress event on the run's own thread, while NOVA waits on it, so the hook reads the `Nozzle` in a settled state. When the top-level contour stage ends, the worker's hook takes the figure descriptions that stage settles (`plotting.contourStageViews`: the contour, the near-wall state, the three flow fields and the revolved wall) and sends them ahead of the result. A description is plain arrays and labels in no palette, so the server draws it in whichever mode a window asks for; the result pane shows them while cooling and the plume still run. The result also carries the headline of the run's result table, so the run list names a run without unpickling it.

The program flags `export` and `plotsEnabled` have no row in the Design form. Every run writes every figure and data file into the staging folder, where the result pane reads them, and Export copies the chosen ones to the output folder; nothing else is written there. A loaded config's values for the two flags pass through to a saved one unchanged.

## Kept runs and the baseline

The session keeps the last eight finished runs (`session.keptRuns`), each with the config it ran and its headline, and every route that draws or lists a run takes `?run=` to name one; without it a route answers for the latest. One kept run can be the baseline, set with `PUT /api/runs/baseline`, and it is kept however many runs follow it. A run that drops out of the list takes its staging folder with it. A kept run unpickles its `Nozzle` on first use, and only the three drawn from most recently (`session.keptNozzles`) keep theirs in memory; the others read their pickle again when next drawn.

With a baseline other than the shown run, `GET /api/views/{key}/interactive?compare=` draws the baseline's lines dashed over the shown run's in the same colors, for the line plots along the axis (`views.comparableViews`), with the title saying which run is which; the baseline's fills, markers and labels are left out. `GET /api/analysis?baseline=` sets the baseline's table beside the shown one (`analysis.compareTables`): rows match by section and label, each value gains the baseline's and the change, written to the shown value's own decimals with the percent change, and rows only the baseline has follow at the end of their section.

## Run progress

NOVA reports a run's progress as structured events (`NOVA.progress`): the plan of top-level stages the configuration will run, each stage opening and closing (nested, so the coolant circuit's down and up passes sit inside the cooling stage), the steps of its long loops, and the iterations of its iterative solves with the scalars that show them converging (the contour's design Mach and residual per characteristics solve, the circuit's coolant outlet temperatures and change per pass). The printed output is the human log and is not read for progress.

The session folds those events with `progress.RunProgress` into a stage tree: the top-level stages, the stages one level inside each, and the iterations sent in each with the values they report. Anything deeper shows only in the live detail of the stage it runs in, for example `Up pass 45%` under the coolant circuit.

The run bar draws the tree as a stepper, one segment per top-level stage of the plan, each as wide as the stage's time on the last finished run of the same server, or a nominal time on its first run. A segment fills with the stage's own loop where it reports one, else with its elapsed time against the expected time, and names what the stage is doing: `evaluation 6` in the contour, `pass 4` in the coolant circuit, whose segment is notched at each finished pass. Times advance on the run's own clock between events, so a stage that reports only every few seconds still reads as working.

Stages opens the stage list: every stage and sub-stage with its time, and the passes of a convergent loop, each with the values it reports. The coolant circuit lists its two legs' outlet temperatures and the up leg's change per pass, so the circuit can be watched settling. Until this run reaches them, the list carries the sub-stages the last finished run took, as pending with that run's times, and a running loop says how many passes that run took. The contour solve's evaluations are too many to list; its sub-stage shows their count and the latest design Mach and residual.

The legacy Tkinter window keeps one bar over the same model: each stage spans a share of the bar in proportion to the same times, the label names the running stage and its iteration or loop (`Cooling channels, pass 4`), and between events the bar eases toward the running stage's end.

## Views

Each view draws interactive, and Save PNG saves its static drawing:

| Rendering | Source | Views |
| --- | --- | --- |
| Interactive | A plotly figure sent as JSON and drawn by plotly.js 3.0.1, the version plotly.py 6.2 bundles: NOVA's plotly builder for the view, or for the cooling views `coolingFigures.py` | Every view |
| Static | The Matplotlib drawer (`plotting.py`, `thermalPlots.py`), rendered headless to PNG at the pane's size and twice its pixel density, the picture NOVA's saved figures use | Every view except the channel mesh and volutes |

The flow fields draw filled (`NOVA.figures.plotlyField(filled = True)`): the field is interpolated onto a regular grid of square cells over the nozzle, linearly inside the characteristic nodes' triangles and from the nearest node in the sliver between the outermost nodes and the wall, and blank outside the wall. The solved nodes are a legend entry, hidden until shown, whose hover reads the value the solve produced at each. The interactive plume opens on the static drawing's frame, the nozzle and the marched plume, and zooming out shows the correlated shock cells past the march.

Grid draws four views at once. Every figure drawn along the nozzle axis (`frontend/src/view/axialLink.ts`) joins the pane's axial link: its axial x axes are those titled "Nozzle axis" and those matched to one, the mouse over any of their subplots moves one cursor to that station on every linked figure, the figures whose hover reads along x show their values there, and a zoom along the axis on one is applied to the rest. The cursor is a line drawn over the plot, not a plotly shape, so moving it never redraws a figure. The grid places two views a row where the pane is wide enough and one where it is not; Pop out opens the figure or the grid in a window of its own (`/?popout=figure`), which follows the latest run, or keeps to an older run it was opened on, and switches theme with the main window.

`coolingFigures.py` draws the nine cooling views (circuit, passes, jacket on the wall, temperatures, coolant flow and properties, heat flux, film, radiative extension) with plotly from the same Nozzle arrays, titles and colors as `thermalPlots`, read through that module's own accessors. A line colored station by station is drawn as closely spaced markers, with a transparent marker at each solver station carrying the hover; the film map resamples the core and the film band onto a rectangular grid. The 3D assemblies draw at full resolution in WebGL. Figures are drawn in one palette mode at a time, held in module globals, so the server renders one figure at a time.

The Matplotlib plume title points a legacy Tkinter user at its Open interactive button for the correlated structure beyond the march; the static drawing here, saved as a PNG, rewords that to the interactive view (`views.staticTextOverrides`).

## Theme

The Engineering Flat Metal palette lives in `themeColors.palettes`, and `src/NOVA/palette.py` holds the same values for NOVA's own figures; `tests/testGuiTheme.py` keeps the two equal. `frontend/src/styles/palette.css` carries the palette as CSS custom properties for both modes and is written by `python -m novaGui.paletteCss`; `tests/testWebServer.py` fails if the two differ. The server writes the saved mode into `index.html` before sending it, so the first paint is in the right palette. The mode persists in `%APPDATA%\NOVA\guiSettings.json` with the Design form's width; the legacy front end reads the mode from the same file.

## Layout

| Part | Contents |
| --- | --- |
| Design form | The left of the window. Every field of the config schema in its sections, with the main fields first and the rest folded into Advanced settings or a named fold. An outline of the sections runs above the form, or down its side when the form is 760 px wide or more; each entry counts its section's changed fields, problems and entries to fix, marks the section in view, and jumps to it. Selector rows choose between alternative keys (L* or barrel length, thrust or mass flow, area ratio or exit pressure, the regen truncation). Every dimensioned field has a unit dropdown that converts in place. A search box filters by label, key, help and option text; Changed only shows the fields that differ from the shipped nozzle, each marked with a copper dot that restores the shipped value when clicked. An entry that does not parse is flagged on its row and its section, and blocks Generate. Cross-field problems list in a strip above the form, mark the rows they name in amber with the problem written under each, and ask before a run. Under the wall material, a panel samples the alloy's conductivity, density, modulus, yield, expansion and elongation at a temperature it sets, with the data source; a name the store does not carry falls back to GRCop-42 and says so. Under the extension material, a note gives its temperature limits and what the store holds, and choosing a material fills the shell conductivity and emissivities the store carries. Reset to example, Load example and Save config sit in the toolbar. |
| Splitter | Sets the form's width by drag or by the arrow keys, kept between launches; a double click returns the default. Below a window width of 960 px the form and the result pane stack instead. |
| Result pane | The right of the window. The run menu shows any kept run, with its time and headline (thrust, delivered Isp, propellants); it follows the latest until another is picked, a new run sets it back to following, and a running run shows its settled figures once its contour stage ends. Baseline picks the run the shown one is compared against. Figure draws one view, picked from a grouped menu, or four in the grid; views the run did not produce are disabled. Save PNG saves the static drawing, and Pop out opens the figures in a second window. Table lists the run's scalar results in sections: sizing, the combustion chamber, delivered performance beside the two 1D estimates, chamber and throat thermochemistry, the cooling summary and each coolant pass, the extension circuit, the gas generator, the films and the plume, under the headline numbers (delivered Isp and thrust, length, exit diameter, the peak hot wall against its limit, each pass's pressure drop). A row or a headline number a figure shows opens it. Beside a baseline each value carries the baseline's and the change. A filter narrows the rows by name; Copy puts the table, as filtered, on the clipboard as tab-separated text, and Save CSV writes it as `<run name>Run<n>Results.csv`, with the baseline's columns when there is one. |
| Status strips | Under the result pane's header. The first whenever the pane is behind the form: a run in progress, a run cancelled or failed, or fields edited since the shown run, each named with its value then and now from the config the run kept. The second beside a baseline, naming the fields that differ between the baseline's config and the shown run's. |
| Export | A dialog opened from the result pane's header. The shown run's outputs by category (figures, interactive figures, contour coordinates, 3D geometry, channel size profile, the pickled Nozzle, the run config, other files), each category and file with a check. Every output is checked after a run, except the categories unchecked before it. Export copies the checked files into `<output folder>/<run name>Outputs/`; the output folder defaults to `runs/` at the repository root. A double click opens a file in its desktop application, and Open folder opens the target. Figures carry thumbnails, and the eye on a row previews the file beside the list: an image, an STL surface in plotly's 3D viewer (thinned past 200 000 triangles), or the first 400 lines of a text, CSV or JSON file. In the desktop window Browse opens the native folder picker; in a browser the folder is typed. |
| Run bar | Generate (Cancel while running), the stage stepper, the run's elapsed time against the last run's, Stages for the stage list, which opens as each run starts, and Show log for the run's output. |
| Pop-out window | One view or the grid, with the run menu, the same axial link and the main window's baseline, for a second monitor. In the desktop window it is a second pywebview window, closed with the main one; in a browser, a popup. |

| Shortcut | Action |
| --- | --- |
| Ctrl+R | Generate |
| Ctrl+O | Load a config |
| Ctrl+S | Save the config |
| Escape | Close the dialog or the stage list |

## Units and materials

`units.py` holds the per-field unit tables (pressure, length, force, temperature, angle, mass flow). Each numeric field stores and submits its value in NOVA's SI unit; the dropdown only changes the display, and switching it converts the shown number so the physical quantity is preserved.

The wall material panel reads `src/NOVA/materials.py` directly (numpy only, no CEA), sampling `sampleWallMaterial(name, temperature)`.

## Tests

`tests/testWebServer.py` covers the serialized schema against `configSchema`, the dependency predicates, the unit table against `NOVA.units` to a relative 1e-12, the routes that read files, the cross-field checks with the rows they flag and the notes they carry, the material routes against `NOVA.materials`, the result table (performance columns, value and unit split, the rows and summary, the headline numbers, the figure each row names), the comparison against a baseline (row matching, change text, the route), the kept runs (the cap, the baseline kept past it, released Nozzles, the run list and baseline routes), the export routes (listing by category, a copy compared byte for byte, refusal of names outside the run's listing, open, previews, STL reading and thinning), a running run's settled figures, the cooling figures, the baseline overlay, the filled field (blank outside the wall, inside the solved range), the plume title rewording, the palette stylesheet, and a run session's error, cancel and contour-stage paths with real worker processes. It takes about two minutes.

The cooling figure tests cross-check each plotly builder against the Matplotlib drawer it ports: every labelled series the drawer plots must appear in the plotly figure under the same name with the same values, and the panels the drawer leaves unlabelled must carry the jacket solve's arrays. They read the showcase cooling runs in `featureShowcase/coolingRuns/`, which are local outputs that git ignores, and skip without them.

`tests/testProgress.py` covers the progress events and `RunProgress`; `tests/testGuiSchema.py` imports every module of both front ends headless and holds the schema to the shipped configuration.

## Security

The server binds to 127.0.0.1 only. It runs NOVA on any config it is sent, unpickles its own run results from its staging folder, copies a run's outputs into any folder it is given and opens a run's files in the desktop's applications; it is not meant to face a network. Export, open and preview requests name files by base name, and the server acts only on names in the finished run's own listing, so none reaches a file outside the run's staging folder.

The desktop window exposes two native calls to the page through pywebview's bridge (`WindowApi` in `__main__.py`): `browseFolder`, which opens the folder picker and returns the path chosen, and `openWindow`, which opens a page of this server, a path beginning with a single `/`, in a second window.
