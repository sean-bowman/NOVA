/* ========================================
   RUN SELECT
   The run a window shows, picked from the runs the server keeps: the latest, followed as new
   runs finish, or any kept run by its number, the name it was given (else its config's filename),
   headline and run time. A run still going is listed once its contour stage has settled the
   contour and the flow fields. The menu's own label carries the shown run's headline, and its
   tooltip the whole of it with the run's note.
   Sean Bowman [11/19/2026]
   ======================================== */

import { formatClock } from '../run/stageText';
import type { RunEntry } from '../types';
import type { RunsView } from './useRuns';

/** The result table's summary line as one line: thrust, delivered Isp, propellants. */
export function headlineOf(entry: RunEntry): string {
    return entry.headline.split(/\s{2,}/).filter(Boolean).join(', ');
}

/** A run's name: the one it was given, else its config's filename. */
export function runTitle(entry: RunEntry): string {
    return entry.title || entry.runName;
}

function runLabel(entry: RunEntry, baseline: number | null): string {
    const parts = [`Run ${entry.runId}`, runTitle(entry), headlineOf(entry), formatClock(entry.elapsedSec)];
    return parts.filter(Boolean).join(' · ') + (entry.runId === baseline ? ' · baseline' : '');
}

export function RunSelect({ runs }: { runs: RunsView }) {
    const { list, choice, partial, baseline, shown } = runs;
    const kept = list?.runs ?? [];
    const running = list?.running ?? null;
    const latestEntry = runs.entry(list?.latest ?? null);

    let latest = 'Latest run';
    if (running && partial && choice === 'latest') {
        latest = `Latest: run ${running.runId}, running`;
    } else if (latestEntry) {
        latest = [`Latest: run ${latestEntry.runId}`, latestEntry.title, headlineOf(latestEntry)].filter(Boolean).join(' · ');
    }

    const shownEntry = runs.entry(shown);
    let title = 'The run this pane shows';
    if (partial && shown !== null) {
        title = `Run ${shown}, running: its contour stage is done`;
    } else if (shownEntry) {
        const named = shownEntry.title ? `\nconfig ${shownEntry.runName}` : '';
        const note = shownEntry.note ? `\n\n${shownEntry.note}` : '';
        title = `${runLabel(shownEntry, baseline)}${named}\nfinished in ${formatClock(shownEntry.elapsedSec)}${note}`;
    }

    return (
        <select className="input run-select" aria-label="Run shown" value={String(choice)} title={title}
                disabled={!list || (kept.length === 0 && !running)}
                onChange={(event) => runs.choose(event.target.value === 'latest' ? 'latest' : Number(event.target.value))}>
            <option value="latest">{latest}</option>
            {running && running.views.length > 0 && <option value={running.runId}>Run {running.runId} · running</option>}
            {kept.map((entry) => <option key={entry.runId} value={entry.runId}>{runLabel(entry, baseline)}</option>)}
        </select>
    );
}
