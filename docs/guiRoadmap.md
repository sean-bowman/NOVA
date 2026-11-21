# GUI Roadmap

The work open on NOVA's GUI (`novaGui/`), with what each item is for, what it would take and what it depends on. Items keep their number when others close, so a reference to G4 stays good. This is a list to work from, not a schedule.

---

## Open

| Item | Title | Effort | Depends on |
| --- | --- | --- | --- |
| [G11](#g11-a-standalone-windows-build) | A standalone Windows build | Large | A user without Python |

A new item takes the next number, G12.

### G11. A standalone Windows build

The GUI needs a Python environment with NOVA installed from a checkout. A frozen build (PyInstaller, as a folder: the packages it would carry take about 430 MB in the development environment, which one file would unpack to the temp folder at every launch) would run it on a machine with no Python, for someone who wants the GUI alone. It would ship as a GitHub Release file from a Windows CI job, not in the repository. What it takes:

- `multiprocessing.freeze_support()` first in `main`, or each run's 'spawn' worker opens the GUI again.
- RocketCEA's compiled Fortran, its data files (`thermo.lib`, `trans.lib`) and the gfortran runtime DLLs, collected by hand.
- REFPROP cannot ship under its license. The build falls back to CoolProp unless the machine has REFPROP installed.
- The checkout files the GUI reads carried in the bundle (`docs/validationStatus.json` and the records it quotes, `src/NOVA/assets/NOVANozzle.json`), and exports moved from the checkout's `runs/` to a user folder. The writable state already lives outside the package: the run store in `%LOCALAPPDATA%\NOVA\runs`, settings in `~/.config/NOVA`, run folders in the temp folder, CEA files in `~/RocketCEA`.
- A test that holds the release to the source, as `tests/testFrontendBuild.py` holds `dist/`.
- Code signing. Unsigned, the exe meets a SmartScreen warning on first run, some antivirus tools flag PyInstaller builds, and company IT often blocks it outright.

It waits on a user who needs it. For a user inside a company, signing is part of the item from the start.

---

## Built

| Pull request | What it built |
| --- | --- |
| #1 | The React front end (`novaGui`), served by FastAPI in a pywebview window |
| #2 | Run progress as structured events (`NOVA.progress`); the Tkinter front end moved to `legacy/novaTk` |
| #3 | The Design form beside the result pane; the stage stepper and the stage list |
| #4 | Kept runs and a baseline; the contour drawn before a run ends; the grid with one cursor and zoom along the axis; the pop-out window; interactive-only views with Save PNG and filled flow fields; the section outline; problems written under their fields; headline numbers; rows that open their figure; export previews |
| #5 | The contour and near-wall state hover along the axis; figures cached and gzipped; a run's warnings counted in the run bar and listed in the result pane; the run time and headline in the run menu; a browser test of the front end (`tests/testGuiBrowser.py`) |
| #6 | G2, saved and named runs: a run store (`novaGui.runStore`) kept between launches, run ids that never repeat, a name and note per run, delete, and limits on unnamed runs. G4, edit from a kept run: in the run's details, and in the strip that names the form's changes |
| #7 | G3, validation status on the results: `docs/validationStatus.json` summarizes each model's status from its records, quoting them word for word, held by `tests/testValidationStatus.py`; a badge on each headline number and section reads as the weakest model behind it and opens the passages of its records; `docs/validationStatus.md` is the same summary as one table |
| #8 | G1, trade sweeps with a run queue: Generate during a run queues the form, Cancel stops the run alone or the queue with it, and a queued run can be taken out; a sweep (`novaGui.sweeps`) varies one field over a range or a list, or two as a grid, queues one run per point, goes on past a failed point, and keeps its runs until it is deleted; the Sweep view plots a headline number against the swept field and tabulates the points with each number's validation status |
| #10 | G6, reports: a run's report, alone or against its baseline, and a sweep's, each one HTML file (`novaGui.report`) with the headline numbers and their validation status, the inputs that differ from the shipped nozzle, the result table or the sweep's points and plot, the figures as PNGs in both modes, the warnings, a validation section and the config; saved from the Export dialog and the Sweep view |
| #11 | G9, the methalox extension stage. Of its 729 s, about 690 went to building the REFPROP library object again on each of the stage's 23,000 property calls, about 30 ms a call against 0.6 ms for the property itself. `fluidProperties.refpropLibrary` builds it once a process: every result is the same bit for bit, the extension circuit takes 41 s in place of 733 s, and the whole example 106 s. What is left is the circuit's 14 outer iterations of two sizing marches each, converging at a ratio of 0.52 an iteration. A multi-pass circuit draws its heat transfer figure once, of its up pass, and the extension circuit draws none, so the exported figure is the chamber jacket's |
| #12 | G5, the jacket profile while the circuit iterates: each pass of a multi-pass coolant circuit's outer iteration sends both legs' hot wall and coolant along the wall (`NOVA.progress.profiles`) and the circuit solution keeps them; the Circuit iterations view draws them pass over pass, the latest solid and the earlier ones fading, live while the run goes on and from the finished run after |
| #13 | G7, the Tkinter front end retired (11/20/2026): `legacy/` is removed, with what the shared modules carried for it alone: the run bar's fraction and ceiling in `RunProgress`, the plume title rewording (the drawer says the interactive view directly), the Matplotlib redraw of the 3D views, `themeColors.styleFigure`, its session staging folder (the server collects a crashed server's own) and the nozzle outline asset; the tests that drew through its pane draw on the static renderer's |
| #14 | G8, install without Node: the repository carries the built front end (`novaGui/frontend/dist`), so a checkout and `pip install -e .[web]` run the GUI; the build stamps a hash of its sources (`dist/buildStamp.json`) and `tests/testFrontendBuild.py` fails when the sources move past it or the build holds an asset nothing loads; `.gitattributes` keeps `dist/` byte for byte and out of diffs |
| #15 | G10, the `nova-gui` launcher: `novaGui` joins the installed package with its icons, marks and built front end as package data, and the gui-scripts entry point `nova-gui` (`nova-gui.exe` on Windows) opens the window with no console from any folder, in place of `novaGui.bat` and its fixed interpreter path. The window takes an app id of its own and `assets/nova.ico`, so its taskbar button carries NOVA's icon. The launcher stops with a message when the package is not in a checkout, whose validation summary and shipped configuration the GUI reads; `tests/testPackaging.py` builds the wheel and checks what it holds |
