# NOVA GUI

The front end for the NOVA nozzle design suite: a React app served by a FastAPI layer over the Python backend, in a desktop window. It builds a configuration in the `NOVANozzle.json` schema, runs `Nozzle.generateNozzle()` in a worker process, and presents the result across four tabs: Design, View, Analyze and Export.

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
| Server | `server.py`, on 127.0.0.1 at a free port. Serves the app, evaluates the form's dependency predicates and cross-field checks, reads the material store, starts and cancels runs, streams run events, draws the views, builds the result table and copies the outputs chosen for export. |
| Worker | `worker.py`, one per run, started with `spawn`. Runs `runner.PipelineRunner`, then pickles the finished `Nozzle` into the run's staging folder. |

A run is a separate process so it can be cancelled: the server terminates it. RocketCEA's machine-wide `nova.lock` is an `msvcrt` byte lock, which Windows releases when the process ends, so a cancelled run does not hold up the next. Each run writes into its own folder under `%TEMP%\NOVA\web<pid>\`, removed when the window closes; `runner.clearStaging` removes one a crashed server left behind after twelve hours.

Run events (log lines, progress, status, result) reach the browser as Server-Sent Events. Each connection opens with a snapshot of the session, so a reload mid-run picks up where the run is.

## Modules

| Module | Holds |
| --- | --- |
| `server`, `session`, `worker`, `__main__` | The HTTP routes, the run session that relays a worker's messages, the worker process, and the launcher |
| `configSchema` | The Design form: sections, fields, selectors, folds, defaults, examples, dependency predicates |
| `schemaJson` | The schema as JSON for the browser, and the predicates evaluated on a posted config |
| `design` | The cross-field checks and the rows they name, the wall alloy's sampled properties, the extension material's store note and fill |
| `units` | The unit table, reduced to `si = scale * shown + offset` per display unit |
| `runner` | The run itself: forced program flags, the staging folder, headless figures, the progress reporter, the output listing |
| `progress` | `RunProgress`, which folds a run's progress events into the run bar and the stage list |
| `viewCatalog` | The views a run can produce, in sidebar order, and the test of which ones it produced |
| `plotting`, `thermalPlots` | The Matplotlib drawers, the plotly builder for each view, and the jacket, film and extension accessors |
| `coolingFigures` | Plotly figures for the nine cooling views |
| `views` | Each view rendered for the browser: plotly JSON, or the Matplotlib drawing as PNG |
| `analysis` | The result table |
| `outputs` | The output categories, and listing, copying and opening a run's files |
| `themeColors`, `paletteCss` | The palette in both modes with its Matplotlib styling, and the stylesheet written from it |
| `settings`, `backend` | The saved theme mode, and lazy access to NOVA's figures and material store |
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

The program flags `export` and `plotsEnabled` have no row on the Design tab. Every run writes every figure and data file into the staging folder, where the View tab reads them, and the Export tab copies the chosen ones to the output folder; nothing else is written there. A loaded config's values for the two flags pass through to a saved one unchanged.

## Run progress

NOVA reports a run's progress as structured events (`NOVA.progress`): the plan of top-level stages the configuration will run, each stage opening and closing (nested, so the coolant circuit's down and up passes sit inside the cooling stage), the steps of its long loops, and the iterations of its iterative solves with the scalars that show them converging (the contour's design Mach and residual per characteristics solve, the circuit's coolant outlet temperatures and change per pass). The printed output is the human log and is not read for progress.

The session folds those events with `progress.RunProgress`. Each top-level stage spans a share of the bar in proportion to its time on the last finished run of the same server, or a nominal time on its first run. The label names the running stage and its iteration or loop: `Contour, evaluation 6`, `Cooling channels, pass 4`. Between events the bar eases toward the running stage's end, so a stage that reports only every few seconds still reads as working.

## Views

Each view draws one or both of two ways:

| Rendering | Source | Views |
| --- | --- | --- |
| Interactive | A plotly figure sent as JSON and drawn by plotly.js 3.0.1, the version plotly.py 6.2 bundles: NOVA's plotly builder for the view, or for the cooling views `coolingFigures.py` | Every view |
| Static | The Matplotlib drawer (`plotting.py`, `thermalPlots.py`), rendered headless to PNG at the pane's size and the display's pixel ratio | Every view except the channel mesh and volutes |

`coolingFigures.py` draws the nine cooling views (circuit, passes, jacket on the wall, temperatures, coolant flow and properties, heat flux, film, radiative extension) with plotly from the same Nozzle arrays, titles and colors as `thermalPlots`, read through that module's own accessors. A line colored station by station is drawn as closely spaced markers, with a transparent marker at each solver station carrying the hover; the film map resamples the core and the film band onto a rectangular grid. The 3D assemblies draw at full resolution in WebGL. Figures are drawn in one palette mode at a time, held in module globals, so the server renders one figure at a time.

The Matplotlib plume title points a legacy Tkinter user at its Open interactive button for the correlated structure beyond the march; the static rendering here rewords that to the Interactive rendering (`views.staticTextOverrides`).

## Theme

The Engineering Flat Metal palette lives in `themeColors.palettes`, and `src/NOVA/palette.py` holds the same values for NOVA's own figures; `tests/testGuiTheme.py` keeps the two equal. `frontend/src/styles/palette.css` carries the palette as CSS custom properties for both modes and is written by `python -m novaGui.paletteCss`; `tests/testWebServer.py` fails if the two differ. The server writes the saved mode into `index.html` before sending it, so the first paint is in the right palette. The mode persists in `%APPDATA%\NOVA\guiSettings.json`, the file the legacy front end reads too.

## Tabs

| Tab | Contents |
| --- | --- |
| Design | Every field of the config schema in its sections, with the main fields first and the rest folded into Advanced settings or a named fold. Selector rows choose between alternative keys (L* or barrel length, thrust or mass flow, area ratio or exit pressure, the regen truncation). Every dimensioned field has a unit dropdown that converts in place. A search box filters by label, key, help and option text; Changed only shows the fields that differ from the shipped nozzle, each marked with a copper dot that restores the shipped value when clicked. An entry that does not parse is flagged on its row and its section, and blocks Generate. Cross-field problems list in a strip above the form, mark the rows they name in amber, and ask before a run. Under the wall material, a panel samples the alloy's conductivity, density, modulus, yield, expansion and elongation at a temperature it sets, with the data source; a name the store does not carry falls back to GRCop-42 and says so. Under the extension material, a note gives its temperature limits and what the store holds, and choosing a material fills the shell conductivity and emissivities the store carries. Reset to example, Load example and Save config sit in the toolbar. |
| View | Every view a run can produce, grouped in a sidebar; views the last run did not produce are greyed. Every view draws interactive, and all but the 3D assemblies also static, behind an Interactive and Static switch. |
| Analyze | The last good run's scalar results in sections: sizing, the combustion chamber, delivered performance beside the two 1D estimates, chamber and throat thermochemistry, the cooling summary and each coolant pass, the extension circuit, the gas generator, the films and the plume. A filter narrows the rows by name; Copy puts the table, as filtered, on the clipboard as tab-separated text, and Save CSV writes it as `<run name>Results.csv`. |
| Export | The last good run's outputs by category (figures, interactive figures, contour coordinates, 3D geometry, channel size profile, the pickled Nozzle, the run config, other files), each category and file with a check. Every output is checked after a run, except the categories unchecked before it. Export copies the checked files into `<output folder>/<run name>Outputs/`; the output folder defaults to `runs/` at the repository root. A double click opens a file in its desktop application, and Open folder opens the target. In the desktop window Browse opens the native folder picker; in a browser the folder is typed. |

The run bar holds Generate (Cancel while running), the current stage, a progress bar, the elapsed time, the latest output line and the run log. Hovering the stage shows every open stage with its iteration or loop, for example `Cooling channels / Coolant circuit (pass 4) / Up pass 45%`. The progress events also carry the run's top-level stages with their state and times.

| Shortcut | Action |
| --- | --- |
| Ctrl+R | Generate |
| Ctrl+O | Load a config |
| Ctrl+S | Save the config |

## Units and materials

`units.py` holds the per-field unit tables (pressure, length, force, temperature, angle, mass flow). Each numeric field stores and submits its value in NOVA's SI unit; the dropdown only changes the display, and switching it converts the shown number so the physical quantity is preserved.

The wall material panel reads `src/NOVA/materials.py` directly (numpy only, no CEA), sampling `sampleWallMaterial(name, temperature)`.

## Tests

`tests/testWebServer.py` covers the serialized schema against `configSchema`, the dependency predicates, the unit table against `NOVA.units` to a relative 1e-12, the routes that read files, the cross-field checks and the rows they flag, the material routes against `NOVA.materials`, the result table (performance columns, value and unit split, the rows and summary), the export routes (listing by category, a copy compared byte for byte, refusal of names outside the run's listing, open), the cooling figures, the plume title rewording, the palette stylesheet, and a run session's error and cancel paths with real worker processes. It takes about 35 s.

The cooling figure tests cross-check each plotly builder against the Matplotlib drawer it ports: every labelled series the drawer plots must appear in the plotly figure under the same name with the same values, and the panels the drawer leaves unlabelled must carry the jacket solve's arrays. They read the showcase cooling runs in `featureShowcase/coolingRuns/`, which are local outputs that git ignores, and skip without them.

`tests/testProgress.py` covers the progress events and `RunProgress`; `tests/testGuiSchema.py` imports every module of both front ends headless and holds the schema to the shipped configuration.

## Security

The server binds to 127.0.0.1 only. It runs NOVA on any config it is sent, unpickles its own run results from its staging folder, copies a run's outputs into any folder it is given and opens a run's files in the desktop's applications; it is not meant to face a network. Export and open requests name files by base name, and the server acts only on names in the finished run's own listing, so neither reaches a file outside the run's staging folder.

The desktop window exposes one native call to the page through pywebview's bridge, `browseFolder` (`WindowApi` in `__main__.py`), which opens the folder picker and returns the path chosen.
