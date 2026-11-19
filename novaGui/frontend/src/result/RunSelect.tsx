/* ========================================
   RUN SELECT
   The run a window shows, picked from the runs the server keeps: the latest, followed as new
   runs finish, or any kept run by its number, name and headline. A run still going is listed once
   its contour stage has settled the contour and the flow fields.
   Sean Bowman [11/19/2026]
   ======================================== */

import type { RunEntry } from '../types';
import type { RunsView } from './useRuns';

function runLabel(entry: RunEntry, baseline: number | null): string {
    const parts = [`Run ${entry.runId}`, entry.runName, entry.headline.split(/\s{2,}/).filter(Boolean).join(', ')];
    return parts.filter(Boolean).join(' · ') + (entry.runId === baseline ? ' · baseline' : '');
}

export function RunSelect({ runs }: { runs: RunsView }) {
    const { list, choice, partial, baseline } = runs;
    const kept = list?.runs ?? [];
    const running = list?.running ?? null;

    let latest = 'Latest run';
    if (running && partial && choice === 'latest') {
        latest = `Latest: run ${running.runId}, running`;
    } else if (list?.latest != null) {
        latest = `Latest: run ${list.latest}`;
    }

    return (
        <select className="input run-select" aria-label="Run shown" value={String(choice)}
                disabled={!list || (kept.length === 0 && !running)}
                onChange={(event) => runs.choose(event.target.value === 'latest' ? 'latest' : Number(event.target.value))}>
            <option value="latest">{latest}</option>
            {running && running.views.length > 0 && <option value={running.runId}>Run {running.runId} · running</option>}
            {kept.map((entry) => <option key={entry.runId} value={entry.runId}>{runLabel(entry, baseline)}</option>)}
        </select>
    );
}
