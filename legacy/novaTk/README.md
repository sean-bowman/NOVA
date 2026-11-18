
# NOVA Legacy Tkinter GUI

The Tkinter front end for the NOVA nozzle design suite, kept for reference beside the current front end, [novaGui](../../novaGui/README.md). It builds a configuration in the `NOVANozzle.json` schema, runs `Nozzle.generateNozzle()` on a background thread, and presents the result across four tabs: Design, View, Analyze and Export.

This package holds the widgets alone: the window, the tabs, the Tk theme engine and the Matplotlib pane on a Tk canvas. Everything else comes from `novaGui`: the config schema and the form checks, the units, the runner and the progress model, the view list and the Matplotlib drawers, the result table, the output categories, the palette, the saved settings and the assets. The two front ends therefore build the same config, raise the same problems, list the same results and draw the same figures.

## Launch

From the repository root:

```bash
python -m legacy.novaTk
```

or

```bash
python legacy/novaTk/run.py
```

On Windows, `legacy/novaTk.bat` double-clicks to launch with no console window (it hands off to `pythonw.exe` and exits). Run `python -m legacy.novaTk` from a terminal when a startup traceback needs to be visible.

The main window opens without loading the scientific stack; NumPy, SciPy, Matplotlib, rocketcea and the rest are imported on the first run.

## Window

The header carries the plume mark, the NOVA wordmark and the subtitle on the left, and **About**, the light/dark switch and **Load config** on the right. The run bar along the bottom holds **Generate**, the current stage, a progress bar, the latest output line and the run log toggle.

| Shortcut | Action |
| --- | --- |
| Ctrl+R | Generate |
| Ctrl+O | Load a config |
| Ctrl+S | Save the config |

## Tabs

| Tab | Contents |
| --- | --- |
| Design | Every field in the NOVA config schema, grouped into collapsible sections whose headers carry a nozzle glyph, turned sideways when closed and pointing downstream when open. Each section leads with the fields a design is made from and folds the rest into **Advanced settings**, closed until opened and filled with the shipped nozzle's values: Contour Definition shows the diverging section type, the chamber diameter and the chamber length; Combustion folds the propellant inlet temperatures; Regenerative Cooling shows the truncation, the wall material, the channel type and sizing, the channel count, the hot wall, rib and shell thicknesses, the wall temperature limit and the coolant, and folds the correlations, channel limits, coatings, mesh counts and exit limits. Each volute has a fold of its own beside the settings they share, and a fold with nothing to show is hidden. Alternative inputs share one selector row whose first column picks the option, the second takes its value and the third its unit: L* or barrel length, thrust or engine mass flow, expansion ratio or exit pressure, and the regen truncation (none, at a recovery temperature, or at an area ratio). Each option keeps its own entry while another is chosen, and only the chosen one is written to the config. The radiative extension's material is a dropdown of the hot-structure materials in NOVA's material store; choosing one fills the shell conductivity and emissivities the store carries for it, and a note beneath gives its temperature limits and what the store does not carry. A fresh form is the shipped nozzle, `src/NOVA/assets/NOVANozzle.json`: **Reset to example** at the top returns to it, **Load example** beside it offers the engines in `src/NOVA/assets/examples/`, one for each cooling architecture, and **Save config** sits at the foot of the form. Every field carries an (i) icon whose tooltip gives its meaning and, for a choice field, its options. Dependent fields stay hidden until they apply: the design vector only for a searched contour, and the cooling, extension, film and volute fields only once their toggle is on. Fuel and oxidizer are dropdowns that can be typed into for exotic entries; the selected wall alloy's sampled conductivity, density, modulus, yield and CTE show below it at a chosen temperature. Every dimensioned field carries a unit dropdown that converts in place and hands SI to the backend. Choice fields read as plain language and convert to the backend form on build. Cross-field warnings (`novaGui.design`) show before a run starts. |
| View | One figure at a time, picked from a sidebar grouped as `novaGui.viewCatalog` lists them: Contour, Flow, Plume, Cooling and 3D. Views the last run did not produce are disabled. Each is drawn in Matplotlib from the `Nozzle` object by the drawers in `novaGui.plotting` and `novaGui.thermalPlots`, and **Open interactive** opens its plotly version in the system browser. |
| Analyze | One table, the rows of `novaGui.analysis.resultRows`: sizing, combustion chamber, delivered performance, station thermochemistry from CEA, the regenerative cooling summary and each coolant pass, the extension, the films and the plume. |
| Export | The last run's outputs by category (`novaGui.outputs`), each with a check: figures, interactive figures, contour coordinates, 3D geometry, the channel size profile, the pickled `Nozzle` and the run configuration. A category opens to its files, each checkable on its own. **Export** copies the checked files to `<output folder>/<output name>Outputs/`, and **Open folder** opens it. A category unchecked before a run stays unchecked for the next. Double-click a file to open it. |

## Runs

The run bar hands the form contents to `novaGui.runner.PipelineRunner` on a thread of the window; [novaGui/README.md](../../novaGui/README.md) describes what the runner does. NOVA's printed output is mirrored into the collapsible run log, and its progress events drive the run bar through `novaGui.progress.RunProgress`, weighted by the stage times of the window's last finished run. The staging folder belongs to the window's session and is deleted when the window closes.

## Theme

The window uses the Engineering Flat Metal palette (`novaGui.themeColors`) in a dark mode (gunmetal, the default) and a light mode (brushed aluminum), switched from the sun and moon button in the header. The choice persists in `%APPDATA%/NOVA/guiSettings.json`, which the current front end reads too. `theme.py` binds the active mode's colors as its own attributes, which every widget reads, and builds the ttk themes.

Rounded corners come from images. `themeImages.py` draws each control (buttons, entry and dropdown fields, cards, tabs, the progress bar, scrollbar thumbs, the check box) as a rounded rectangle with Pillow at four times its size and reduces it, and `theme.py` registers it as a ttk image element with a nine-slice border. Each image keeps a large flat middle and each element declares a minimum size: a nine-slice image whose corners meet in the middle makes Tk tile it pixel by pixel, which stalls the event loop on a form of a hundred rows.

Every image is flattened onto the color of the container it sits on and drawn wide. Tk 8.6 on Windows draws a partly transparent photo image by reading the screen back and blending it in software on every redraw, and ttk draws a stretched element one tile per middle-width; together they made a scroll step of the Design form take about 55 ms to redraw. Opaque, wide images bring it to about 32 ms, against 16 ms for the same widgets in the stock `clam` theme. An element that appears on two containers therefore has an image for each, registered under the container's style prefix. The scrolling frame adds up wheel deltas smaller than a notch (a precision touchpad's), applies the notches that arrive before a redraw in one scroll, and keeps a dropdown under the pointer from taking the wheel.

Each mode is its own ttk theme, built on first use and switched with `theme_use`, so a switch restyles the live widgets in place. The widgets ttk does not style (the run log, the Matplotlib panes, tooltips) follow through callbacks registered with `theme.addListener`. A run in progress keeps going through a switch. On Windows the title bar, tooltips and dropdown lists take the palette and rounded corners through DWM window attributes.

## Plotting

`src/NOVA/figures.py` extracts each figure into a plain dataclass that mentions neither plotting library, then offers a plotly renderer for it; `novaGui/plotting.py` renders the same dataclasses with Matplotlib. `plotting.py` here holds `MplPane`, the Matplotlib figure on a Tk canvas the drawers draw into, and the helpers that open a view in the browser.

Matplotlib draws every pane in the View tab, because it is the only backend that renders into a Tk canvas. Plotly draws the interactive version, which **Open interactive** opens in the system browser, because it cannot be embedded in Tkinter. The channel mesh and volutes are decimated for the inline pane; the interactive version carries the full mesh. **Open interactive** stays grey until a nozzle has been generated, and for views with no plotly version.

## Display scaling

`theme.enableDpiAwareness()` runs before the Tk root is built so Windows composites the window at native resolution instead of upscaling a 96 dpi bitmap. `theme.applyTheme` then reads the real screen DPI, sets `tk scaling`, and rebinds every font to its scaled size; `theme.uiScale` and `theme.scaled(px)` carry that factor to window geometry, wrap lengths, the theme images and Matplotlib figure DPI. At 100 % scaling the factor is 1.0 and nothing changes.

## Dependencies

Everything in `dependencies.txt`, and Pillow (`pip install -e .[gui]`), which draws the controls and icons.
