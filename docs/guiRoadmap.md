# GUI Roadmap

The work open on NOVA's GUI (`novaGui/`), with what each item is for, what it would take and what it depends on. Items keep their number when others close, so a reference to G4 stays good. This is a list to work from, not a schedule.

---

## Open

| Item | Title | Effort | Depends on |
| --- | --- | --- | --- |
| [G7](#g7-retire-the-tkinter-front-end) | Retire the Tkinter front end | Medium | a decision |
| [G8](#g8-install-without-node) | Install without Node | Medium | |

### G7. Retire the Tkinter front end

`novaGui` now does everything `legacy/novaTk` does. Keeping the legacy window costs code the shared modules carry for it alone, for example the plume title rewording (`views.staticTextOverrides`) and the bar fraction and ceiling `progress.RunProgress.summary` computes for the legacy window's single bar, and the tests of both front ends. Retiring it takes a decision and a date: from then on, `legacy/` is removed, and the shared modules drop what only it reads.

### G8. Install without Node

The GUI needs `npm install && npm run build` in `novaGui/frontend` before its first launch, so a user without Node cannot run it. Shipping the built front end with the package (a release artifact, or the built `dist/` included in the wheel) removes that step; a one-file bundle of the server, the built front end and pywebview would remove the Python install as well.

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
