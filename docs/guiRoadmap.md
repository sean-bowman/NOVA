# GUI Roadmap

The work open on NOVA's GUI (`novaGui/`), with what each item is for, what it would take and what it depends on. Items keep their number when others close, so a reference to G4 stays good. This is a list to work from, not a schedule.

---

## Open

| Item | Title | Effort | Depends on |
| --- | --- | --- | --- |
| [G1](#g1-trade-sweeps-with-a-run-queue) | Trade sweeps with a run queue | Large | G2 |
| [G2](#g2-saved-named-runs) | Saved, named runs | Medium | |
| [G3](#g3-validation-status-on-the-results) | Validation status on the results | Medium | |
| [G4](#g4-edit-from-a-kept-run) | Edit from a kept run | Small | |
| [G5](#g5-the-jacket-profile-while-the-circuit-iterates) | The jacket profile while the circuit iterates | Medium | |
| [G6](#g6-run-report) | Run report | Medium | |
| [G7](#g7-retire-the-tkinter-front-end) | Retire the Tkinter front end | Medium | a decision |
| [G8](#g8-install-without-node) | Install without Node | Medium | |
| [G9](#g9-the-methalox-extension-stage) | The methalox extension stage | Investigation | |

The suggested order is G4, then G2, then G1: G4 is small and makes the kept runs useful for iterating on a design, and a sweep of several five-minute runs should not be lost when the window closes. G3 stands alone and can go at any point.

### G1. Trade sweeps with a run queue

NOVA's main use is trade studies, and today each point of a study is one press of Generate, made by hand after the last run finishes.

- **The sweep.** Pick a field, give it a list of values (chamber pressure at 6, 7, 8 and 9 MPa) or a range and a count, and the GUI queues one run per value. Two fields swept against each other make a grid.
- **The queue.** Runs go one at a time. RocketCEA's machine-wide lock (`nova.lock`) serializes the CEA solves of concurrent runs anyway, so a queue costs no speed. Generate during a run adds to the queue rather than refusing; the run bar shows the queue's length and Cancel offers this run or the rest.
- **The result.** A sweep table, one row per run, with the swept inputs and the headline numbers (`analysis.headline`), and a plot of any headline number against a swept value. A sweep's runs carry its name, so the run menu can group them.
- **Where it goes.** The session holds a queue of configs and starts the next when a run ends (`session.RunSession._drain`). The kept-run cap (`session.keptRuns`, 8) needs to rise for a sweep, or a sweep's runs need to count against it as one.

### G2. Saved, named runs

Kept runs live in the server's memory and its staging folder (`%TEMP%\NOVA\web<pid>`), so closing the window loses them, and a study runs over days.

- Persist each finished run, its config, headline, warnings and pickled `Nozzle`, under a runs store: `%APPDATA%\NOVA\runs\` or the repository's `runs/`. Reload the store at launch.
- A run gets a name and a free-text note, editable from the run menu, and can be deleted from it.
- The store needs a size limit with the oldest unnamed runs going first, since each run's outputs are tens of megabytes. Named runs and the baseline stay.
- The figure cache and the result table cache key on run ids, which then have to be unique across sessions, not counted from 1 per server.

### G3. Validation status on the results

The table and the headline numbers show values with no sign of how far each can be trusted. The plume section already reports its own bound ("Within the trusted bound"); nothing else does.

- A mapping in `novaGui`, from each model behind a result (the gas-side heat transfer, the contour solve, the near-wall state, the plume march, the coolant pressure drop) to its validation status: the reference and the error against it in percent, or "unvalidated" with the reason no reference applies.
- A badge on each headline number and each table section, its tooltip giving the reference, and a link to the validation document it comes from (`docs/NozzleContourValidation.md`, the cooling and boundary layer documents, `validation/`).
- The statuses must come from the validation records, not be written into the GUI by hand, or they drift from them. A small machine-readable summary kept beside the validation documents, read by both the documents' tables and the GUI, avoids that.

### G4. Edit from a kept run

Going back to an earlier design means exporting its config and loading the file. An entry on each run in the run menu, "Edit from this run", would load that run's config into the Design form: the form then reads as that run did, and the status strip shows no changes until a field is edited. Each kept run already carries its config (`RunRecord.config`, returned in `/api/runs`), so this is a frontend change.

### G5. The jacket profile while the circuit iterates

The stage list shows each coolant circuit pass's outlet temperatures and change, which says the circuit is converging but not where along the wall it is still moving. Each pass could also send its hot wall temperature profile and its coolant temperature profile along the axis, and the result pane could draw them pass over pass, the latest solid and the earlier ones fading, while the run continues. The worker already has a stage hook on the run's own thread (`runner.PipelineRunner.stageHook`); the profiles would ride on the circuit's `iteration` events or a message of their own, a few kilobytes per pass.

### G6. Run report

A report of one run, or of a run against its baseline, to send to someone without the GUI: the inputs that differ from the shipped nozzle, the headline numbers, the result table, the key figures as static drawings, and the run's warnings, as one HTML file in the report palette. The pieces exist: `analysis.resultTable`, `analysis.compareTables`, the static drawers behind Save PNG, and the run's config and warnings.

### G7. Retire the Tkinter front end

`novaGui` now does everything `legacy/novaTk` does. Keeping the legacy window costs code the shared modules carry for it alone, for example the plume title rewording (`views.staticTextOverrides`) and the bar fraction and ceiling `progress.RunProgress.summary` computes for the legacy window's single bar, and the tests of both front ends. Retiring it takes a decision and a date: from then on, `legacy/` is removed, and the shared modules drop what only it reads.

### G8. Install without Node

The GUI needs `npm install && npm run build` in `novaGui/frontend` before its first launch, so a user without Node cannot run it. Shipping the built front end with the package (a release artifact, or the built `dist/` included in the wheel) removes that step; a one-file bundle of the server, the built front end and pywebview would remove the Python install as well.

### G9. The methalox extension stage

The methalox booster example (`src/NOVA/assets/examples/methaloxBooster.json`) spends 729 s in its radiative extension stage, where the other examples with an extension take 0.1 to 30 s. Whether the time is the extension's own solve, its film, or a convergence loop that runs to its limit is not known. A profile of that stage alone would say which.

---

## Built

| Pull request | What it built |
| --- | --- |
| #1 | The React front end (`novaGui`), served by FastAPI in a pywebview window |
| #2 | Run progress as structured events (`NOVA.progress`); the Tkinter front end moved to `legacy/novaTk` |
| #3 | The Design form beside the result pane; the stage stepper and the stage list |
| #4 | Kept runs and a baseline; the contour drawn before a run ends; the grid with one cursor and zoom along the axis; the pop-out window; interactive-only views with Save PNG and filled flow fields; the section outline; problems written under their fields; headline numbers; rows that open their figure; export previews |
| #5 | The contour and near-wall state hover along the axis; figures cached and gzipped; a run's warnings counted in the run bar and listed in the result pane; the run time and headline in the run menu; a browser test of the front end (`tests/testGuiBrowser.py`) |
