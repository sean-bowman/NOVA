/* ========================================
   RUN SELECT
   The run a window shows, picked from the runs the server keeps: the latest, followed as new
   runs finish, or any kept run by its number, name, headline and run time. A run still going is
   listed once its contour stage has settled the contour and the flow fields. The menu's own
   label carries the shown run's headline, and its tooltip the whole of it.
   Sean Bowman [11/19/2026]
   ======================================== */

import { formatClock } from '../run/stageText';
import type { RunEntry } from '../types';
import type { RunsView } from './useRuns';

function headlineOf(entry: RunEntry): string {
    return entry.headline.split(/\s{2,}/).filter(Boolean).join(', ');
}

function runLabel(entry: RunEntry, baseline: number | null): string {
    const parts = [`Run ${entry.runId}`, entry.runName, headlineOf(entry), formatClock(entry.elapsedSec)];
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
        latest = [`Latest: run ${latestEntry.runId}`, headlineOf(latestEntry)].filter(Boolean).join(' · ');
    }

    const shownEntry = runs.entry(shown);
    let title = 'The run this pane shows';
    if (partial && shown !== null) {
        title = `Run ${shown}, running: its contour stage is done`;
    } else if (shownEntry) {
        title = `${runLabel(shownEntry, baseline)}\nfinished in ${formatClock(shownEntry.elapsedSec)}`;
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
