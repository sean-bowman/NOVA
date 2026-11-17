# NOVA Web Front End

A React front end for the NOVA nozzle design suite, served by a FastAPI layer over the Python backend. It builds a configuration in the `NOVANozzle.json` schema, runs `Nozzle.generateNozzle()` in a worker process, and presents the result across four tabs: Design, View, Analyze and Export. It sits beside the Tkinter front end in `novaGui/` and changes nothing in it.

## Launch

From the repository root:

```bash
python -m novaWeb               # desktop window (pywebview hosting WebView2)
python -m novaWeb --browser     # the system browser instead
```

On Windows, `novaWeb.bat` at the repository root double-clicks to launch with no console window. Without a console the launcher writes its output to `%TEMP%\NOVA\novaWeb.log`, replaced at each launch, so a failed start leaves its traceback there.

The Python side needs FastAPI, uvicorn and pywebview: `pip install -e .[web]`. pywebview uses the WebView2 runtime that ships with Windows 11.

## Build

The server serves the built front end from `novaWeb/frontend/dist/`, which git ignores. Build it once, and again after any change under `frontend/src/`:

```bash
cd novaWeb/frontend
npm install
npm run build
```

Node is needed to build, not to run.

## Development

Two terminals, with hot reload on the front end:

```bash
python -m novaWeb --api         # the API alone on 127.0.0.1:8765
cd novaWeb/frontend && npm run dev     # Vite on http://localhost:5173, proxying /api to 8765
```

`npm run typecheck` runs the TypeScript compiler alone.

## Architecture

Three processes take part in a run:

| Process | Role |
| --- | --- |
| Window | WebView2 (or a browser) running the React app. Holds the form state and the config in backend values (SI). |
| Server | `novaWeb/server.py`, on 127.0.0.1 at a free port. Serves the app, evaluates the form's dependency predicates, starts and cancels runs, streams run events, draws the views, builds the result table and copies the outputs chosen for export. |
| Worker | `novaWeb/worker.py`, one per run, started with `spawn`. Runs `novaGui.runner.PipelineRunner` exactly as the Tkinter front end does, then pickles the finished `Nozzle` into the run's staging folder. |

A run is a separate process so it can be cancelled: the server terminates it. RocketCEA's machine-wide `nova.lock` is an `msvcrt` byte lock, which Windows releases when the process ends, so a cancelled run does not hold up the next. Each run writes into its own folder under `%TEMP%\NOVA\web<pid>\`, removed when the window closes; `novaGui.runner.clearStaging` removes one a crashed server left behind after twelve hours.

Run events (log lines, stage progress, status, result) reach the browser as Server-Sent Events. Each connection opens with a snapshot of the session, so a reload mid-run picks up where the run is.

### Shared with the Tkinter front end

The server imports these modules from `novaGui/` and does not copy them, so both front ends build the same config and draw the same figures:

| Module | Used for |
| --- | --- |
| `configSchema` | The Design form: sections, fields, selectors, folds, defaults, examples, dependency predicates |
| `units` | The unit table, reduced to `si = scale * shown + offset` per display unit |
| `runner`, `progress` | The run itself and its stage tracking |
| `tabs.viewTab` | The view list and the test of which views a run produced |
| `tabs.analysisTab` | The result table: its `refresh` runs on a stand-in that records the rows (`novaWeb/analysis.py`) |
| `tabs.exportTab` | The output categories and the rule that files an output by its name |
| `plotting`, `thermalPlots` | The plotly builder for each view, and the Matplotlib drawers |
| `settings` | The saved theme mode (`%APPDATA%\NOVA\guiSettings.json`), so a mode chosen in either front end opens the other in it |

The Analyze table is the Tkinter table's code run without Tk. `AnalysisTab.refresh` fills a ttk.Treeview and a summary label; `novaWeb/analysis.py` calls it on a plain object carrying the class's methods, a tree that records each insert and a label that records its text, so both front ends list the same quantities with the same formatting. The Tkinter table packs the three performance columns into one cell; the web table splits them into columns, and splits a single value from its unit so the numbers align.

The schema's `showWhen` and `expandWhen` predicates are Python functions. The browser receives each row's static description with a `conditional` flag and posts its config to `/api/schema/state`, which returns the rows and sections to hide and the sections to open.

### Views

Each view draws one or both of two ways:

| Rendering | Source | Views |
| --- | --- | --- |
| Interactive | NOVA's plotly builder for the view, sent as figure JSON and drawn by plotly.js 3.0.1, the version plotly.py 6.2 bundles | Contour, near-wall state, Mach, pressure and temperature fields, plume, channel mesh, revolved contour, volutes |
| Static | The Matplotlib drawer the Tkinter pane uses, rendered headless to PNG at the pane's size and the display's pixel ratio | Every view except the channel mesh and volutes |

The cooling views (circuit, passes, jacket, temperatures, coolant flow and properties, heat flux, film, radiative extension) have no plotly builder and draw static only. The 3D assemblies draw at full resolution in WebGL. Figures are drawn in one palette mode at a time, held in module globals, so the server renders one figure at a time.

### Theme

The Engineering Flat Metal palette lives in `novaGui.theme.palettes`. `src/styles/palette.css` carries it as CSS custom properties for both modes and is written by `python -m novaWeb.paletteCss`; `tests/testWebServer.py` fails if the two differ. The server writes the saved mode into `index.html` before sending it, so the first paint is in the right palette.

## Tabs

| Tab | Contents |
| --- | --- |
| Design | Every field of the config schema in its sections, with the main fields first and the rest folded into Advanced settings or a named fold. Selector rows choose between alternative keys (L* or barrel length, thrust or mass flow, area ratio or exit pressure, the regen truncation). Every dimensioned field has a unit dropdown that converts in place. A search box filters by label, key, help and option text; Changed only shows the fields that differ from the shipped nozzle, each marked with a copper dot that restores the shipped value when clicked. An entry that does not parse is flagged on its row and its section, and blocks Generate. Reset to example, Load example and Save config sit in the toolbar. |
| View | Every view a run can produce, grouped in a sidebar; views the last run did not produce are greyed. A view with both renderings offers an Interactive and Static switch. |
| Analyze | The last good run's scalar results in sections: sizing, the combustion chamber, delivered performance beside the two 1D estimates, chamber and throat thermochemistry, the cooling summary and each coolant pass, the extension circuit, the gas generator, the films and the plume. A filter narrows the rows by name; Copy puts the table, as filtered, on the clipboard as tab-separated text, and Save CSV writes it as `<run name>Results.csv`. |
| Export | The last good run's outputs by category (figures, interactive figures, contour coordinates, 3D geometry, channel size profile, the pickled Nozzle, the run config, other files), each category and file with a check. Every output is checked after a run, except the categories unchecked before it. Export copies the checked files into `<output folder>/<run name>Outputs/`; the output folder defaults to `runs/` at the repository root. A double click opens a file in its desktop application, and Open folder opens the target. In the desktop window Browse opens the native folder picker; in a browser the folder is typed. |

The run bar holds Generate (Cancel while running), the current stage, a progress bar that eases toward the stage's ceiling between NOVA's banners, the elapsed time, the latest output line and the run log.

| Shortcut | Action |
| --- | --- |
| Ctrl+R | Generate |
| Ctrl+O | Load a config |
| Ctrl+S | Save the config |

### Tkinter features not carried over

- The wall material panel (sampled conductivity, density, modulus, yield and CTE under the material field).
- The radiative extension's material fill (choosing a hot-structure material sets its conductivity and emissivities).
- The cross-field checks the Tkinter form runs before a run, beyond entries that do not parse and required selector values.

## Tests

`tests/testWebServer.py` covers the serialized schema against `configSchema`, the dependency predicates, the unit table against `NOVA.units` to a relative 1e-12, the routes that read files, the result table (performance columns, value and unit split, the Tkinter rows and summary), the export routes (listing by category, a copy compared byte for byte, refusal of names outside the run's listing, open), the palette stylesheet, and a run session's error and cancel paths with real worker processes. It takes about 25 s.

## Security

The server binds to 127.0.0.1 only. It runs NOVA on any config it is sent, unpickles its own run results from its staging folder, copies a run's outputs into any folder it is given and opens a run's files in the desktop's applications; it is not meant to face a network. Export and open requests name files by base name, and the server acts only on names in the finished run's own listing, so neither reaches a file outside the run's staging folder.

The desktop window exposes one native call to the page through pywebview's bridge, `browseFolder` (`WindowApi` in `novaWeb/__main__.py`), which opens the folder picker and returns the path chosen.
