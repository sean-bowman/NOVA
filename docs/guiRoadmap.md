# GUI Roadmap

The work open on NOVA's GUI (`novaGui/`), with what each item is for, what it would take and what it depends on. Items keep their number when others close, so a reference to G4 stays good. This is a list to work from, not a schedule.

---

## Open

| Item | Title | Effort | Depends on |
| --- | --- | --- | --- |
| [G12](#g12-code-signing) | Code signing of the desktop app | Small | Users outside the developer who need it |
| [G13](#g13-test-suite-on-pull-requests) | Test suite on pull requests | Medium | None |
| [G14](#g14-version-shown-in-the-app) | Version shown in the app | Small | None |
| [G15](#g15-new-release-notice) | New release notice | Small | G14 |
| [G16](#g16-plume-sweep-over-a-finished-run) | Plume sweep over a finished run | Medium | None |
| [G17](#g17-throttled-plume) | Throttled plume | Medium | G16 |
| [G18](#g18-every-pass-in-the-jacket-views) | Every pass in the jacket views | Medium | None |
| [G19](#g19-faster-circuit-convergence) | Faster circuit convergence | Medium | None |
| [G20](#g20-queued-runs-kept-across-launches) | Queued runs kept across launches | Small | None |
| [G21](#g21-front-end-unit-tests) | Front-end unit tests | Small | None |
| [G22](#g22-python-past-310) | Python past 3.10 | Medium | Wheels for the target version |
| [G23](#g23-macos-build) | macOS build | Large | A user on a Mac |

A new item takes the next number, G24. The materials data behind the wall material panel and the thermal results has gaps of its own (no cryogenic conductivity for five wall alloys, conductivity read at the hot wall only), tracked in [materialsDatabaseRoadmap.md](materialsDatabaseRoadmap.md).

### G12. Code signing

Releases of the desktop app are unsigned ([releasing.md](releasing.md)). Windows SmartScreen warns on the first launch, some antivirus tools flag PyInstaller builds, and company IT often blocks unsigned executables. Signing `NOVA.exe` in the Release workflow, between the build and the zip, is what most company IT asks for; SmartScreen's warning fades as the certificate gains reputation. It takes a code-signing certificate, which since 2023 lives on a hardware token or in a cloud key store, or a cloud signing service; its credentials in the repository's Actions secrets; and the signing step. The certificate is a recurring cost, so this waits on users outside the developer who need it.

### G13. Test suite on pull requests

The only workflow, `release.yml`, builds and smoke-tests the desktop app. The test suite runs only on the developer's machine, so a version tag can publish code whose suite never ran on main. A `tests.yml` workflow on pull requests and pushes to main would install `.[web]` against `packaging/constraints.txt` on a Windows runner and run pytest.

Three things set the size of the work. The runner has no REFPROP, so `fluidProps` takes CoolProp, and a test whose tolerance was set against REFPROP's answer may miss by a small margin; the first run finds these, and each takes a tolerance that holds on both backends or a skip without REFPROP, as `testFluidProperties.py` has. `testGuiBrowser.py`, and the tests in `testWebServer.py` and `testRunReport.py` that read the showcase runs, skip without those local runs, so the workflow either makes them first, at a full run each, or leaves those tests local. The suite runs in one process for about 21 minutes on the development desktop; pytest-xdist would split it, though RocketCEA's machine-wide lock (`nova.lock`) still runs every CEA solve one at a time. `tests/regressionHarness.py` stays local, since its baselines are bit-for-bit records of one machine's answer.

### G14. Version shown in the app

A user of a release cannot see which version is running. The About dialog (`frontend/src/App.tsx`) names NOVA and describes the window without a version, and the startup log (`%TEMP%\NOVA\novaGui.log`) records none. Reports already carry it: `report.py` reads `importlib.metadata.version('nova-nozzle')`, which the desktop app keeps through `copy_metadata` in `packaging/nova.spec`. The work is the version in `/api/health`, a line in the About dialog, and the version as the log's first line with whether the GUI runs frozen or from a checkout, so a report of a problem names what ran.

### G15. New release notice

The desktop app has no way to learn of a newer release; a user finds one on the Releases page. A Check for updates button in the About dialog would ask GitHub for the latest release (`GET /repos/sean-bowman/NOVA/releases/latest`), compare its tag with the running version (G14), and link to the release when it is newer. A button rather than a check at every launch keeps the app off the network unless the user asks; GitHub's unauthenticated limit of 60 requests an hour is no constraint either way. Installing stays manual: the user unzips the new folder in place of the old one. Runs, settings and exports live outside the app folder ([releasing.md](releasing.md)), so nothing is lost.

### G16. Plume sweep over a finished run

A trade sweep (G1) runs the whole pipeline at every point, about 67 s each for the shipped nozzle. Of the stages, only the plume and the delivered performance read the ambient pressure (`plumeAmbientPressure`); the contour, cooling and extension give the same answer at every ambient. The plume stage takes 6.1 s of the 67 (`progress.nominalStageTimes`), and the performance at a back pressure is closed form (`performance.py`). A plume sweep would take a finished run, call `plumeStructure` and `plumeField` on its Nozzle at each ambient in a worker, and keep the fields with that run rather than as runs of their own. Ten points would take about a minute where a trade sweep over the same values takes eleven.

The view would draw the plume boundaries over one another, each labeled with its lip pressure ratio, and the table would give the thrust coefficient, specific impulse, jet scale and Mach disk position at each ambient. Each point carries the march's mass continuity error at two and six lip radii, as `featureShowcase/buildPlumeSweep.py` does. The sweep refuses ambients outside the march's envelope, which on the shipped contour runs from a lip pressure ratio of 0.75 to about 1.8. The plume march is unvalidated (`docs/validationStatus.json`), and the view's badge says so.

### G17. Throttled plume

`Nozzle.throttledPlumeField` solves the plume at a fraction of rated chamber pressure against a fixed ambient, and no part of the GUI reaches it. It answers what an ambient sweep cannot: how far the engine throttles at one altitude before its nozzle separates. `featureShowcase/buildPlumeThrottle.py` is that sweep as a script: it walks the power level down in 5 percent steps until the march refuses on the separation criterion, and draws thrust and specific impulse against power level with the separation limit marked. On G16's machinery it becomes a second kind of plume sweep, with the power level as the swept field and the thrust from the frozen-gas relation in [plumeThrottleModel.md](plumeThrottleModel.md).

The model holds the gas at its rated state, which biases the power level at which separation is reported by about 4.9 percent, toward reporting it later than it happens. The model document measures that bias as the size of the separation criterion's own spread, so the GUI need not wait for the open model work it lists: the gas state re-solved at each power level, the boundary layer thickening as power falls, and separation located with Schmucker's criterion. The view states the bias beside the separation limit.

### G18. Every pass in the jacket views

The five jacket views (Jacket on the wall, Temperatures, Coolant flow, Coolant properties, Heat flux) read `Nozzle.channelThermalResults`, which on a multi-pass circuit holds the up pass alone. NOVA's exported heat transfer figure is drawn once, of the up pass (`coolantCircuit.solveCoolantCircuit`). The extension circuit draws none, since its passes would write over the jacket's figure, which is saved under one name (`extensionCircuit.solveExtensionCircuit`). The Coolant per pass view gives each pass's coolant and hot wall, but not its pressure, velocity, film coefficients or heat flux.

The solutions already keep every pass: `Nozzle.coolantCircuitSolution.down.state` and `.up.state` hold their station results, and `Nozzle.extensionCircuitSolution` keeps its single pass as `sizing` or its two as `circuit`. The work is a pass picker on the jacket views (the jacket's passes, then the extension circuit's), drawers that read the chosen pass's results, and the heat transfer figure written under a name per pass so the Export dialog lists each one.

### G19. Faster circuit convergence

A multi-pass circuit solves its passes in turn until the up pass's coolant temperature stops moving (`coolantCircuit.solveCoolantCircuit`): the down pass against the up pass's last profile, then the up pass against the new down pass, two sizing marches an iteration. The iteration is a plain fixed point. On the methalox booster's two-pass extension circuit it takes 14 iterations and 41 s, the change falling by a ratio of 0.52 an iteration, and a multi-pass jacket's cooling stage takes 14 to 24 s against 2.4 to 3.1 s for a single pass (`progress.nominalStageTimes`). A fixed point converging linearly at a steady ratio is the case Anderson acceleration, or Aitken's delta-squared applied to the neighbor profile, is built for.

The first trial measures the iterations saved. The acceptance test is that every converged circuit, on the shipped nozzle and the five example configurations, agrees with the plain iteration to within the circuit's own tolerance. The results will not stay bit for bit, so the regression harness baselines for the circuit cases are recorded again.

### G20. Queued runs kept across launches

The run queue lives in the server, and closing the window drops the runs not yet started. A sweep already survives this: its points live in the run store, and a sweep whose window closed lists its unrun points as cancelled, with a way to queue them again (`session.resumeSweep`). Single queued runs would follow the same pattern. The session writes the queue to the run store at each change, and the next launch lists the runs that never started, with their configs, to queue again or discard. They do not start unasked, since the user may have closed the window to stop them.

### G21. Front-end unit tests

The front end's only tests drive the built app in Chromium (`tests/testGuiBrowser.py`), and they skip without the local showcase runs, so on a CI runner (G13) they cover nothing unless the workflow makes those runs. The form carries the most rules with no direct test: entry parsing, conversion in place when a unit changes, Changed only and its restore, the selector rows that write only their own keys, and the problems written under fields (`design/formModel.ts`, `design/units.ts`). `testGuiForm.py` covers the schema's layout on the Python side, not this logic. Vitest runs on the existing Vite configuration, and a `test` script beside `typecheck` would run in G13's workflow once Node is set up there.

### G22. Python past 3.10

Development and the release build both run Python 3.10, which reached end of life in October 2026 and no longer gets security fixes. The desktop app bundles its interpreter, so its users inherit it. Moving to 3.12 or 3.13 takes wheels for the target version of every compiled dependency (RocketCEA's Fortran extension first, then pythonnet, CoolProp and the scientific stack), a full suite pass on the new interpreter, new pins in `packaging/constraints.txt`, the workflow's `python-version`, and new regression harness baselines, since a different numpy or scipy build moves the last bits.

### G23. macOS build

The desktop app is Windows only. Most of the code already allows for other platforms: the CEA lock falls back to `fcntl`, the run store, settings and log have POSIX folders, opening a file uses `open` on macOS, and pywebview runs on WebKit there. What is missing is the build: a macOS job in `release.yml`, a spec that makes a `.app` bundle, RocketCEA's Fortran built or installed for the platform, and the smoke test with its Windows `taskkill` replaced by a process-group kill. The smoke test runs without a window, so it works on a runner; the window itself needs a Mac to check. An unsigned app meets Gatekeeper, which on current macOS blocks it until the user allows it in System Settings. Notarization takes an Apple Developer account at a yearly fee, the macOS counterpart of G12.

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
| #16 | G11, the desktop app: `packaging/nova.spec` freezes the GUI with PyInstaller into a folder holding `NOVA.exe` (no console, NOVA's icon) and its supporting files: NOVA and novaGui whole, the front end's build, the checkout files the GUI reads at their checkout paths (`packaging/bundleData.py`), RocketCEA's data files and ctREFPROP. `packaging/smokeTest.py` runs the shipped nozzle through the built exe and draws an interactive figure, a static figure and the report; `packaging/buildRelease.py` builds, tests and zips it. `.github/workflows/release.yml` does the same on a Windows runner and publishes a GitHub Release on a version tag, or keeps the zip as an artifact on a pull request that touches the build. Frozen, the GUI exports to `Documents\NOVA` and leaves out the app id, so its window groups with a pinned `NOVA.exe`. `docs/releasing.md` is the release procedure; releases are unsigned (G12) |
