# NOVA GUI

The front end for the NOVA nozzle design suite: a React app served by a FastAPI layer over the Python backend, in a desktop window. It builds a configuration in the `NOVANozzle.json` schema, runs `Nozzle.generateNozzle()` in a worker process, and shows the result beside the form: the Design form on the left, the last finished run's figures or results table on the right, and a run bar that steps through the run's stages.

The package also holds every piece of a front end that is not drawing widgets: the config schema, the form checks, the units, the runner, the progress model, the view list, the Matplotlib drawers, the result table, the output categories and the palette.

## Launch

Install the checkout editable with the `web` extra, which brings FastAPI, uvicorn and pywebview. pywebview uses the WebView2 runtime that ships with Windows 11.

```bash
pip install -e .[web]
nova-gui                        # desktop window (pywebview hosting WebView2), no console
python -m novaGui               # the same window, from a console
python -m novaGui --browser     # the system browser instead
```

`nova-gui` is the launcher pip writes from the `gui-scripts` entry point in `pyproject.toml`: `nova-gui.exe` in the environment's `Scripts` folder on Windows. It starts from any folder, and Start or the taskbar can pin it. The window it opens takes a taskbar button of its own with NOVA's icon (`assets/nova.ico`). It runs under `pythonw`, so it writes its output to `%TEMP%\NOVA\novaGui.log`, replaced at each launch, and a failed start leaves its traceback there. The log's first line names what runs (`runningBuild`): NOVA's version, the standalone build or the checkout's revision as `git describe --always --dirty` gives it, and the Python and system under it. The About dialog shows the same line, and `GET /api/health` returns it with its parts.

The install has to be editable. The GUI reads the checkout's validation summary (`docs/validationStatus.json`) and shipped configuration (`src/NOVA/assets/NOVANozzle.json`), and exports to its `runs/` folder. A regular install carries the package without them, and the launcher stops with a message naming what is missing.

## Desktop app

The GUI also ships as a Windows desktop app for users without Python: a folder holding `NOVA.exe`, frozen by PyInstaller from a version tag and attached to a GitHub Release. The frozen GUI exports to `Documents\NOVA` and leaves out the app id, since `NOVA.exe` carries the icon itself. [docs/releasing.md](../docs/releasing.md) covers the build, its smoke test and the release workflow.

## Build

The server serves the built front end from `novaGui/frontend/dist/`, which the repository carries, so a checkout runs the GUI without Node. Node is needed only to change the front end: after any change under `frontend/` (its sources, `index.html`, the package files, the TypeScript or Vite configuration), rebuild and commit `dist/` with the change:

```bash
cd novaGui/frontend
npm install
npm run build
```

The build stamps `dist/buildStamp.json` with a hash of every file it reads, and `tests/testFrontendBuild.py` fails when the sources no longer match the stamp, so a front-end change cannot be committed without its build; it also fails on an asset that index.html loads and the build lacks, or one nothing loads. `.gitattributes` marks `dist/` as generated, so `git diff` shows the sources' changes rather than the minified bundle's.

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
| Server | `server.py`, on 127.0.0.1 at a free port. Serves the app, evaluates the form's dependency predicates and cross-field checks, reads the material store, queues, starts and cancels runs, streams run events, keeps the finished runs and the trade sweeps in the run store, draws the views, builds and compares the result tables, previews the outputs and copies the ones chosen for export. |
| Worker | `worker.py`, one per run, started with `spawn`. Runs `runner.PipelineRunner`, sends the figures the contour stage settles when that stage ends and each pass of a multi-pass coolant circuit as it ends, then pickles the finished `Nozzle` into the run's folder. |

A run is a separate process so it can be cancelled: the server terminates it. RocketCEA's machine-wide `nova.lock` is an `msvcrt` byte lock, which Windows releases when the process ends, so a cancelled run does not hold up the next. Each run writes into its own folder in the run store (`runStore`), `%LOCALAPPDATA%\NOVA\runs\run<id>\`; a cancelled or failed run's folder is removed when the run ends, and one a closed server never finished is removed at the next launch once it is twelve hours old.

Run events (log lines, progress, status, a running run's settled figures, its warnings, the result, the queue, changes to the kept runs and the sweeps, saved preferences) reach every window as Server-Sent Events. Each connection opens with a snapshot of the session, so a reload mid-run picks up where the run is, and a popped-out figure window hears the same events as the main one.

## Modules

| Module | Holds |
| --- | --- |
| `server`, `session`, `worker`, `__main__` | The HTTP routes, the run session that queues runs, relays a worker's messages and keeps the finished runs and the sweeps, the worker process, and the launcher |
| `runStore` | The run folders kept between launches: claiming a run id, saving and reading a run's record, the limits on unnamed runs, collecting runs that never finished, and the sweep files |
| `sweeps` | Trade sweeps: a sweep checked against the form's fields and laid out as points, a point's config, the sweep's table of points and headline numbers, and its plot |
| `report` | A run's report, alone or against its baseline, and a sweep's, each as one HTML file in the report palette |
| `configSchema` | The Design form: sections, fields, selectors, folds, defaults, examples, dependency predicates |
| `schemaJson` | The schema as JSON for the browser, and the predicates evaluated on a posted config |
| `design` | The cross-field checks and the rows they name, the wall alloy's sampled properties, the extension material's store note and fill |
| `units` | The unit table, reduced to `si = scale * shown + offset` per display unit |
| `runner` | The run itself: forced program flags, the run's own output folder, headless figures, the progress reporter, the output listing |
| `progress` | `RunProgress`, which folds a run's progress events into the stage tree the stepper and the stage list draw |
| `viewCatalog` | The views a run can produce, in menu order, and the test of which ones it produced |
| `plotting`, `thermalPlots` | The Matplotlib drawers, the plotly builder for each view, and the jacket, film and extension accessors |
| `coolingFigures` | Plotly figures for the ten cooling views |
| `views` | Each view rendered for the browser: plotly JSON, with a second run drawn over a line plot or from a running run's settled figures, or the Matplotlib drawing as PNG |
| `analysis` | The result table, its headline numbers, the figure that shows each row, and two runs' tables side by side |
| `validationStatus` | The validation status of each headline number and table section, read from `docs/validationStatus.json`, and the passages of the records each status stands on |
| `outputs` | The output categories, and listing, previewing (an STL read into vertices and triangles), copying and opening a run's files |
| `themeColors`, `paletteCss` | The palette in both modes with its Matplotlib styling, and the stylesheet written from it |
| `settings`, `backend` | The saved theme mode and form width, and lazy access to NOVA's figures and material store |
| `assets/` | The plume mark in each mode and the window icon |

The schema's `showWhen` and `expandWhen` predicates are Python functions. The browser receives each row's static description with a `conditional` flag and posts its config to `/api/schema/state`, which returns the rows and sections to hide, the sections to open, and the cross-field problems with the rows they name.

The cross-field checks warn rather than block: Generate with problems open asks whether to run anyway. The one check left to the form itself, a required selector option left blank, runs in the browser's selector row, where it blocks the run with the entries that do not parse.

## How a run works

Generate hands the form's config to a worker, whose `PipelineRunner`:

- imports `Nozzle` from the installed `NOVA` package,
- forces the Matplotlib `Agg` backend and sets NOVA's figure mode (`NOVA.palette.setFigureMode`) to the window's, so the figures the run writes match the theme it started in,
- sets `NOVA_HEADLESS` so no figure opens a window or a browser tab,
- sends the outputs to the run's folder,
- writes the config to `<name>RunConfig.json` and calls `generateNozzle()` with a `NOVA.progress` reporter installed, which forwards the run's progress events.

A warning the run raises through Python's warnings module, NOVA's own or numpy's and scipy's, is written to the log as Python prints it and sent as a message of its own (`runner.warningRelay`). The session keeps each distinct warning once with the number of times it came, and keeps the list with the run.

The runner calls a stage hook with each progress event on the run's own thread, while NOVA waits on it, so the hook reads the `Nozzle` in a settled state. When the top-level contour stage ends, the worker's hook takes the figure descriptions that stage settles (`plotting.contourStageViews`: the contour, the near-wall state, the three flow fields and the revolved wall) and sends them ahead of the result. A description is plain arrays and labels in no palette, so the server draws it in whichever mode a window asks for; the result pane shows them while cooling and the plume still run. The worker sends the throat's axial position with them, where the circuit iteration view marks it. The result also carries the summary line of the run's result table and its headline numbers (`worker.headlineNumbers`), so the run list names a run, and a sweep's table reads it, without unpickling it.

The program flags `export` and `plotsEnabled` have no row in the Design form. Every run writes every figure and data file into its own folder, where the result pane reads them, and Export copies the chosen ones to the output folder; nothing else is written there. A loaded config's values for the two flags pass through to a saved one unchanged.

## Kept runs and the baseline

The session keeps the finished runs in the run store (`runStore.RunStore`), so they outlast the window. Each run has a folder of its own, `<store>/run<id>/`, which the worker writes into: the outputs, the run config and the pickled `Nozzle`. When the run finishes, the session saves `run.json` beside them: the config it ran, the headline of its result table, its warnings, its run time, its size, and the name and note it is given, with paths relative to the folder. The next launch starts with every run the store holds and the baseline it last had. Run ids count up across launches and are never given out twice: `store.json` holds the highest given out, and creating a run's folder claims its id, so two servers on one store never share a number. The figure and table caches key on the run id, which this keeps from ever answering for another run.

Every route that draws or lists a run takes `?run=` to name one; without it a route answers for the latest. `PATCH /api/runs/{id}` gives a run a name, a note or both, and `DELETE /api/runs/{id}` removes it, its folder and its cached figures and table. One kept run can be the baseline, set with `PUT /api/runs/baseline`. Named runs, a sweep's runs and the baseline stay however many runs follow; unnamed runs go oldest first once there are more than 24 of them (`runStore.unnamedRuns`) or the store holds more than 2 GB (`runStore.storeBytes`), never the run that has just finished (`runStore.pruned`). A run's outputs take 8 to 17 MB. A kept run unpickles its `Nozzle` on first use, and only the three drawn from most recently (`session.keptNozzles`) keep theirs in memory; the others read their pickle again when next drawn. A saved run whose pickle no longer loads, because NOVA's classes have changed since it ran, still lists with its config, so Edit from this run still works; its views and table answer with the reason.

The store is `%LOCALAPPDATA%\NOVA\runs` on Windows and `~/.local/share/NOVA/runs` elsewhere; `NOVA_RUN_STORE` names another folder. A session made without a store, as the tests make, keeps the last eight runs besides a sweep's (`session.keptRuns`) in a staging folder under `%TEMP%\NOVA\web<pid>\`, removed when the server exits.

The details dialog (`RunDetails.tsx`) names the shown run, writes its note, sets or clears the baseline, deletes the run, and puts its config into the Design form (Edit from this run): the config the run kept, over the defaults for any field added since. The form then reads as that run did, and the status strip names no changes until a field is edited.

The work still open on the GUI is listed in [docs/guiRoadmap.md](../docs/guiRoadmap.md).

With a baseline other than the shown run, `GET /api/views/{key}/interactive?compare=` draws the baseline's lines dashed over the shown run's in the same colors, for the line plots along the axis (`views.comparableViews`), with the title saying which run is which; the baseline's fills, markers and labels are left out. `GET /api/analysis?baseline=` sets the baseline's table beside the shown one (`analysis.compareTables`): rows match by section and label, each value gains the baseline's and the change, written to the shown value's own decimals with the percent change, and rows only the baseline has follow at the end of their section.

## The run queue and trade sweeps

Runs go one at a time. `POST /api/runs` queues the config it is sent (`session.RunSession.submit`): it starts at once when nothing is running, and otherwise when the runs before it end, whether they finish, fail or are cancelled. RocketCEA's machine-wide lock serializes the CEA solves of concurrent runs anyway, so the queue costs no speed. During a run Generate becomes Queue, and the run bar counts the queued runs; the count opens the queue, which takes any run out before it starts (`DELETE /api/queue/{id}`). With runs queued, Cancel offers the run alone, after which the queue goes on, or the run and the queue (`POST /api/runs/cancel` with `{"all": true}`). The queue lives in the server; closing it drops the runs not yet started.

Sweep in the run bar opens the sweep dialog (`SweepDialog.tsx`), which builds a trade sweep from the form as it stands. It varies one field over a range (both ends and a count, evenly spaced) or a list, entered in a display unit beside it, or two fields against each other as a grid; a choice or a switch takes the options ticked. The fields offered are the numbers, choices and switches the config shows a row for, and for a selector row the quantity its chosen option sets. The dialog counts the runs and estimates their time from the latest run's and their size from its files. `POST /api/sweeps` checks the sweep against the schema (`sweeps.build`): at most 64 runs (`sweeps.maxPoints`), and at most six values of a second field (`sweeps.maxSeries`), each a line on the plot. Its points queue in order, the first field varying fastest, each point's config being the sweep's base config with its values set. A point whose run fails keeps its reason, and the queue goes on to the next.

A sweep's runs carry the sweep's id and their point's index, and stay in the run store until the sweep is deleted, as named runs do; the sweep itself is saved as `<store>/sweeps/sweep<id>.json` each time a point moves, so it outlasts the window. Points still to run when the window closed read as not run in the next one, and Run the N not run queues them again (`POST /api/sweeps/{id}/resume`). `DELETE /api/sweeps/{id}` takes the sweep, its queued points, its run in progress and its runs, except a run that was named or is the baseline, which stays as a run of its own.

The result pane's Sweep view (`SweepView.tsx`) plots one headline number against the first swept field, one line per value of the second (`GET /api/sweeps/{id}/figure?number=`), with a failed or unrun point left as a gap, and lists the points below: the swept values, the run, its state, the run's headline numbers, and a failed point's reason under it. Each number's column carries the validation status of the model behind it, read from the result table of one of the sweep's runs. A click on a row or a plotted point shows that run in the pane, and the run menu groups a sweep's runs under its name by point. The sweep reports the numbers NOVA computed for each point and adds no model of its own.

## Reports

A report is a run, a run against its baseline, or a sweep, as one HTML file to send to someone without the GUI (`report.runReport`, `report.sweepReport`). Save report in the Export dialog writes the shown run's, beside the baseline when the pane has one (`GET /api/report?run=&baseline=`); Save report in the Sweep view writes the sweep's (`GET /api/sweeps/{id}/report`). The button beside each opens the report in a window of its own. A report takes about three seconds to write and comes to 0.5 to 0.7 MB.

A run's report holds the headline numbers, each with the validation status of the models behind it and, beside a baseline, the change from it; the fields where the run differs from the shipped nozzle and from the baseline, worded as the GUI's change strip words them; the whole result table; the contour, the near-wall state, the jacket temperatures and the plume, where the run has them; the run's warnings and note; a validation section listing every model behind the reported numbers with its status, reference, result and what would close the gap, from `docs/validationStatus.json`; and the config the run ran. A sweep's report holds the swept fields and the inputs the sweep starts from, the range of each headline number across the points that ran, every headline number plotted against the swept field (`report.sweepFigurePng`), the points with a failed point's reason, the warnings with the points that raised them, the same validation section, and the base config.

The file stands alone. Its figures are PNGs written into it, drawn by the static drawers behind Save PNG; it loads nothing from the network, so it opens offline, and it names no folder of the machine that wrote it. On screen it uses the report palette; printed, it turns to a light page with the light-mode drawings of the same figures. The validation section says what it is: each model's standing against its references, not a check of the reported numbers.

## Run progress

NOVA reports a run's progress as structured events (`NOVA.progress`): the plan of top-level stages the configuration will run, each stage opening and closing (nested, so the coolant circuit's down and up passes sit inside the cooling stage), the steps of its long loops, and the iterations of its iterative solves with the scalars that show them converging (the contour's design Mach and residual per characteristics solve, the circuit's coolant outlet temperatures and change per pass). The printed output is the human log and is not read for progress.

The session folds those events with `progress.RunProgress` into a stage tree: the top-level stages, the stages one level inside each, and the iterations sent in each with the values they report. Anything deeper shows only in the live detail of the stage it runs in, for example `Up pass 45%` under the coolant circuit.

The run bar draws the tree as a stepper, one segment per top-level stage of the plan, each as wide as the stage's time on the last finished run of the same server, or a nominal time on its first run. A segment fills with the stage's own loop where it reports one, else with its elapsed time against the expected time, and names what the stage is doing: `evaluation 6` in the contour, `pass 4` in the coolant circuit, whose segment is notched at each finished pass. Times advance on the run's own clock between events, so a stage that reports only every few seconds still reads as working.

Stages opens the stage list: every stage and sub-stage with its time, and the passes of a convergent loop, each with the values it reports. The coolant circuit lists its two legs' outlet temperatures and the up leg's change per pass, so the circuit can be watched settling. Until this run reaches them, the list carries the sub-stages the last finished run took, as pending with that run's times, and a running loop says how many passes that run took. The contour solve's evaluations are too many to list; its sub-stage shows their count and the latest design Mach and residual.

A multi-pass coolant circuit also sends each pass of its outer iteration as it ends (a `profiles` event): both legs' axial positions, metal hot wall and coolant temperature, a few kilobytes a pass, and the circuit's solution keeps the same passes (`CircuitSolution.iterationProfiles`). `RunProgress` leaves these out of the stage tree. The session keeps them as the running run's description of the Circuit iterations view, the chamber jacket's and the extension circuit's apart by the top-level stage they run in, and sends `{'type': 'iterations', 'revision'}` with the count kept so far; a pass numbered 1 starts its circuit over, as under Ievlev's outer gas-side iteration. The view's figure is drawn and kept once per pass, and the browser fetches it again at each revision and draws it over the last in place, keeping the reader's zoom (plotly's `uirevision`) with no loading overlay between. Once the run finishes, the view draws from the Nozzle's circuit solutions, so it stays. A run solved before its circuits kept their passes has no such view.

## Validation status

`docs/validationStatus.json` summarizes the validation status of every model behind a reported result: the status, the reference, the result in numbers, what would close the gap, and the records it comes from, each with a passage quoted word for word. `validationStatus.annotate` puts a badge on each headline number and section of a run's table: the models behind it (`sectionModelIds`, `headlineModelIds`), with the gas-side model resolved from the run's `gasSideAxialModel` and the multi-pass circuit and chamber film included only where the run has them, and the weakest of their statuses, so a number reads as no stronger than its least trusted model. `GET /api/validation/{model}` returns a model with the paragraphs of its records that carry its quotes, which the badge's dialog shows with the quote marked.

The GUI decides no status. A record that changes its numbers or its verdict fails `tests/testValidationStatus.py` until the summary is read against it again, and `docs/validationStatus.md`, the same summary as one table, is written from the JSON by `python -m novaGui.validationStatus --write`.

## Views

Each view draws interactive, and Save PNG saves its static drawing:

| Rendering | Source | Views |
| --- | --- | --- |
| Interactive | A plotly figure sent as JSON and drawn by plotly.js 3.0.1, the version plotly.py 6.2 bundles: NOVA's plotly builder for the view, or for the cooling views `coolingFigures.py` | Every view |
| Static | The Matplotlib drawer (`plotting.py`, `thermalPlots.py`), rendered headless to PNG at the pane's size and twice its pixel density, the picture NOVA's saved figures use | Every view except the channel mesh and volutes |

The flow fields draw filled (`NOVA.figures.plotlyField(filled = True)`): the field is interpolated onto a regular grid of square cells over the nozzle, linearly inside the characteristic nodes' triangles and from the nearest node in the sliver between the outermost nodes and the wall, and blank outside the wall. The solved nodes are a legend entry, hidden until shown, whose hover reads the value the solve produced at each. The interactive plume opens on the static drawing's frame, the nozzle and the marched plume, and zooming out shows the correlated shock cells past the march.

Grid draws four views at once. Every figure drawn along the nozzle axis (`frontend/src/view/axialLink.ts`) joins the pane's axial link: its axial x axes are those titled "Nozzle axis" and those matched to one, the mouse over any of their subplots moves one cursor to that station on every linked figure, the figures whose hover reads along x show their values there, and a zoom along the axis on one is applied to the rest. The cursor is a line drawn over the plot, not a plotly shape, so moving it never redraws a figure. The contour and the near-wall state hover along the axis in the browser (`views.alongAxisHover`), as the cooling plots do, so the cursor reads the wall radius and the gas state at its station; NOVA's own HTML files keep their hover to the nearest point.

A view's figure is built once per run, view, palette mode and compared run, gzipped once, and kept while its run is kept, up to 160 MB of figures with the least recently drawn going first. The first drawing of a filled flow field takes about half a second to build; drawing it again, in the grid or a popped-out window, takes about 10 ms, and it goes out at 35 to 39 % of its 1.5 to 2.5 MB. Every other response is compressed as it goes out, except the event stream and the PNGs. The grid places two views a row where the pane is wide enough and one where it is not; Pop out opens the figure or the grid in a window of its own (`/?popout=figure`), which follows the latest run, or keeps to an older run it was opened on, and switches theme with the main window.

`coolingFigures.py` draws the ten cooling views (circuit, passes, circuit iterations, jacket on the wall, temperatures, coolant flow and properties, heat flux, film, radiative extension) with plotly from the same Nozzle arrays, titles and colors as `thermalPlots`, read through that module's own accessors. A line colored station by station is drawn as closely spaced markers, with a transparent marker at each solver station carrying the hover; the film map resamples the core and the film band onto a rectangular grid. The circuit iterations view draws each pass of a multi-pass circuit's outer iteration, the hot wall above and the coolant below, the jacket's down leg blue and up leg copper and the extension circuit's legs purple with the down leg dashed, as the passes view colors them; the latest pass is solid and in the legend, and the earlier ones fade with age. `thermalPlots.iterationDescription` reads the passes off a finished Nozzle in the same form the session builds from a running one, so both draw through `coolingFigures.plotIterations`. The 3D assemblies draw at full resolution in WebGL. Figures are drawn in one palette mode at a time, held in module globals, so the server renders one figure at a time.

## Theme

The Engineering Flat Metal palette lives in `themeColors.palettes`, and `src/NOVA/palette.py` holds the same values for NOVA's own figures; `tests/testGuiTheme.py` keeps the two equal. `frontend/src/styles/palette.css` carries the palette as CSS custom properties for both modes and is written by `python -m novaGui.paletteCss`; `tests/testWebServer.py` fails if the two differ. The server writes the saved mode into `index.html` before sending it, so the first paint is in the right palette. The mode persists in `%APPDATA%\NOVA\guiSettings.json` with the Design form's width.

## Layout

| Part | Contents |
| --- | --- |
| Design form | The left of the window. Every field of the config schema in its sections, with the main fields first and the rest folded into Advanced settings or a named fold. An outline of the sections runs above the form, or down its side when the form is 760 px wide or more; each entry counts its section's changed fields, problems and entries to fix, marks the section in view, and jumps to it. Selector rows choose between alternative keys (L* or barrel length, thrust or mass flow, area ratio or exit pressure, the regen truncation). Every dimensioned field has a unit dropdown that converts in place. A search box filters by label, key, help and option text; Changed only shows the fields that differ from the shipped nozzle, each marked with a copper dot that restores the shipped value when clicked. An entry that does not parse is flagged on its row and its section, and blocks Generate. Cross-field problems list in a strip above the form, mark the rows they name in amber with the problem written under each, and ask before a run. Under the wall material, a panel samples the alloy's conductivity, density, modulus, yield, expansion and elongation at a temperature it sets, with the data source; a name the store does not carry falls back to GRCop-42 and says so. Under the extension material, a note gives its temperature limits and what the store holds, and choosing a material fills the shell conductivity and emissivities the store carries. Reset to example, Load example and Save config sit in the toolbar. |
| Splitter | Sets the form's width by drag or by the arrow keys, kept between launches; a double click returns the default. Below a window width of 960 px the form and the result pane stack instead. |
| Result pane | The right of the window. The run menu shows any kept run, with its name, headline (thrust, delivered Isp, propellants) and run time, and the pencil beside it opens the run's details: name, note, baseline, Edit from this run, Delete run; it follows the latest until another is picked, Generate sets it back to following, and a running run shows its settled figures once its contour stage ends. Baseline picks the run the shown one is compared against. Figure draws one view, picked from a grouped menu, or four in the grid; views the run did not produce are disabled. Save PNG saves the static drawing, and Pop out opens the figures in a second window. Table lists the run's scalar results in sections: sizing, the combustion chamber, delivered performance beside the two 1D estimates, chamber and throat thermochemistry, the cooling summary and each coolant pass, the extension circuit, the gas generator, the films and the plume, under the headline numbers (delivered Isp and thrust, length, exit diameter, the peak hot wall against its limit, each pass's pressure drop). A row or a headline number a figure shows opens it. Beside a baseline each value carries the baseline's and the change. A filter narrows the rows by name; Copy puts the table, as filtered, on the clipboard as tab-separated text, and Save CSV writes it as `<run name>Run<n>Results.csv`, with the baseline's columns when there is one. |
| Status strips | Under the result pane's header. The first whenever the pane is behind the form: a run in progress, a run cancelled or failed, or fields edited since the shown run, each named with its value then and now from the config the run kept, with Edit from the run to put that config back. The second beside a baseline, naming the fields that differ between the baseline's config and the shown run's. The third when the shown run raised warnings, listing each with where it was raised and how many times. |
| Export | A dialog opened from the result pane's header. The shown run's outputs by category (figures, interactive figures, contour coordinates, 3D geometry, channel size profile, the pickled Nozzle, the run config, other files), each category and file with a check. Every output is checked after a run, except the categories unchecked before it. Export copies the checked files into `<output folder>/<run name>Outputs/`; the output folder defaults to `runs/` at the repository root. A double click opens a file in its desktop application, and Open folder opens the target. Figures carry thumbnails, and the eye on a row previews the file beside the list: an image, an STL surface in plotly's 3D viewer (thinned past 200 000 triangles), or the first 400 lines of a text, CSV or JSON file. In the desktop window Browse opens the native folder picker; in a browser the folder is typed. |
| Run bar | Generate (Cancel and Queue while running), Sweep, the stage stepper, the run's elapsed time against the last run's, the count of warnings the run has raised, which opens the log, Stages for the stage list, which opens as each run starts, the count of queued runs, which opens the queue, and Show log for the run's output. |
| Pop-out window | One view or the grid, with the run menu, the same axial link and the main window's baseline, for a second monitor. In the desktop window it is a second pywebview window, closed with the main one; in a browser, a popup. |

| Shortcut | Action |
| --- | --- |
| Ctrl+R | Generate, or Queue during a run |
| Ctrl+O | Load a config |
| Ctrl+S | Save the config |
| Escape | Close the dialog or the stage list |

## Units and materials

`units.py` holds the per-field unit tables (pressure, length, force, temperature, angle, mass flow). Each numeric field stores and submits its value in NOVA's SI unit; the dropdown only changes the display, and switching it converts the shown number so the physical quantity is preserved.

The wall material panel reads `src/NOVA/materials.py` directly (numpy only, no CEA), sampling `sampleWallMaterial(name, temperature)`.

## Tests

`tests/testWebServer.py` covers the serialized schema against `configSchema`, the dependency predicates, the unit table against `NOVA.units` to a relative 1e-12, the routes that read files, the cross-field checks with the rows they flag and the notes they carry, the material routes against `NOVA.materials`, the result table (performance columns, value and unit split, the rows and summary, the headline numbers, the figure each row names), the comparison against a baseline (row matching, change text, the route), the kept runs (the cap, the baseline kept past it, released Nozzles, the run list and baseline routes), the run store (ids never given out twice, a run and its name, note and baseline read back by the next session, the oldest unnamed runs dropped past the limits with named runs and the baseline kept, runs that never finished collected, a pickle that no longer loads, the name, note and delete routes), the export routes (listing by category, a copy compared byte for byte, refusal of names outside the run's listing, open, previews, STL reading and thinning), a running run's settled figures, the cooling figures, the baseline overlay, the filled field (blank outside the wall, inside the solved range), the plume title rewording, the palette stylesheet, and a run session's error, cancel and contour-stage paths with real worker processes, the first two on a run store whose folder they leave empty. It takes about two minutes.

The cooling figure tests cross-check each plotly builder against the Matplotlib drawer it ports: every labelled series the drawer plots must appear in the plotly figure under the same name with the same values, and the panels the drawer leaves unlabelled must carry the jacket solve's arrays. They read the showcase cooling runs in `featureShowcase/coolingRuns/`, which are local outputs that git ignores, and skip without them.

It also covers the warning relay and the session's count of a run's warnings, the figure cache and its compression, the views that hover along the axis, and the validation status on each section and headline number with the route that returns a model's records.

`tests/testSweeps.py` covers the run queue and trade sweeps with a scripted worker standing in for NOVA's, so it makes no run and takes about twenty seconds: a sweep laid out with its first field fastest and refused when the form could not run it, runs that queue and start in turn with each run's events following the last one's result, cancelling one run or the whole queue, a run taken out of the queue, a sweep that goes on past a failed point with its runs kept past the session's limit, its table and its plot, a grid's lines, a sweep that outlasts its window in the run store and queues its unrun points again, deleting a sweep with its named run and baseline kept, a run whose sweep the store no longer holds loaded as a run of its own, and the sweep and queue routes.

`tests/testValidationStatus.py` holds the summary to its records: every quoted passage is still in its record, every model is complete, the summary table is current, every section and headline number the table can produce has models behind it, a badge reads as its weakest model, and the models follow what the run used. It needs no run and takes under a second.

`tests/testRunReport.py` covers the reports: a config value in the GUI's words, the inputs that differ in form order, a sweep's report of scripted runs with its plot, the reports of the showcase runs alone and against a baseline with each section, the figures in both modes and the validation statuses, and a refusal for a run or sweep not kept. Every report is held to standing alone: its images are data URIs, nothing loads from the network, and no local folder appears. The showcase tests skip without the showcase runs.

`tests/testGuiBrowser.py` drives the built front end in Playwright's Chromium against a server that keeps the showcase runs as if they had just run: the run menu, a run's name and note, Edit from a run, deleting a run, the baseline drawn under a line plot, a run's warnings, the grid's shared cursor and zoom, compressed figure responses, the headline numbers and a row that opens its figure, a validation badge opening its record, the section outline and a problem under its field, the export previews, a popped-out window, a sweep's plot, table and grouped run menu over the showcase runs, the sweep dialog's request in SI values with its limit on a second field, a run taken out of the queue, Save report in the Export dialog and the Sweep view, read back from the download, and a running circuit's passes drawn one by one in Circuit iterations with the reader's zoom held. No test makes a run: the sweep dialog's request is caught before it reaches the server, the queue holds runs that never start, and the running circuit is a worker the test feeds. Each test fails on a console error. It takes about a minute, and skips without the showcase runs and their outputs, Playwright and its Chromium, or the built front end.

`tests/testCircuitIterations.py` covers the circuit iteration view: a finished run's passes in drawing order with the wall limit and the throat, no view for a run with no multi-pass circuit or one solved before passes were kept, both renderers (every pass on both panels, the latest alone in the legend and solid, the earlier ones fading, a PNG), and a running run fed pass by pass: the view settled once, each pass announced, the jacket and the extension circuit kept apart, a circuit solved again starting over, the figure route growing a pass at a time and the passes dropped when the run ends. It makes no run and takes about ten seconds.

`tests/testProgress.py` covers the progress events and `RunProgress`; `tests/testGuiSchema.py` imports every module of the package headless and holds the schema to the shipped configuration; `tests/testGuiForm.py` holds the Design form's layout to the schema and the collection of a crashed server's staging folder; `tests/testViewFigures.py` draws every Matplotlib view on the static renderer's pane in both modes.

## Security

The server binds to 127.0.0.1 only. It runs NOVA on any config it is sent, unpickles its own run results from the run store, which is the user's own folder, copies a run's outputs into any folder it is given and opens a run's files in the desktop's applications; it is not meant to face a network. Export, open and preview requests name files by base name, and the server acts only on names in the finished run's own listing, so none reaches a file outside the run's own folder.

The desktop window exposes two native calls to the page through pywebview's bridge (`WindowApi` in `__main__.py`): `browseFolder`, which opens the folder picker and returns the path chosen, and `openWindow`, which opens a page of this server, a path beginning with a single `/`, in a second window.
