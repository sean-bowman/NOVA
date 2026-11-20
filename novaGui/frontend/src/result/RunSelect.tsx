/* ========================================
   RUN SELECT
   The run a window shows, picked from the runs the server keeps: the latest, followed as new
   runs finish, or any kept run by its number, the name it was given (else its config's filename),
   headline and run time. A run still going is listed once its contour stage has settled the
   contour and the flow fields. The menu's own label carries the shown run's headline, and its
   tooltip the whole of it with the run's note.

   A trade sweep's runs are grouped under the sweep's name, in point order, where the sweep's
   newest run falls among the others; each names its point and the values it ran.
   Sean Bowman [11/19/2026]
   ======================================== */

import { formatClock } from '../run/stageText';
import type { RunEntry, SweepList } from '../types';
import type { RunsView } from './useRuns';

/** The result table's summary line as one line: thrust, delivered Isp, propellants. */
export function headlineOf(entry: RunEntry): string {
    return entry.headline.split(/\s{2,}/).filter(Boolean).join(', ');
}

/** A run's name: the one it was given, else its config's filename. */
export function runTitle(entry: RunEntry): string {
    return entry.title || entry.runName;
}

function runLabel(entry: RunEntry, baseline: number | null, sweeps?: SweepList | null): string {
    // A sweep's run goes by its name if it has one, then its point; any other run by its name or filename
    let names = [runTitle(entry)];
    if (entry.sweep) {
        const sweep = sweeps?.sweeps.find((candidate) => candidate.sweepId === entry.sweep?.sweepId);
        const texts = sweep?.points[entry.sweep.index]?.texts ?? [];
        names = [entry.title, [`point ${entry.sweep.index + 1}`, ...texts].join(', ')];
    }
    const parts = [`Run ${entry.runId}`, ...names, headlineOf(entry), formatClock(entry.elapsedSec)];
    return parts.filter(Boolean).join(' · ') + (entry.runId === baseline ? ' · baseline' : '');
}

/** The kept runs as the menu lists them: single runs, and each sweep's runs as one group where its newest falls. */
function grouped(kept: RunEntry[]): (RunEntry | { sweepId: number; members: RunEntry[] })[] {
    const items: (RunEntry | { sweepId: number; members: RunEntry[] })[] = [];
    const groups = new Map<number, RunEntry[]>();
    for (const entry of kept) {
        if (!entry.sweep) {
            items.push(entry);
            continue;
        }
        let members = groups.get(entry.sweep.sweepId);
        if (!members) {
            members = [];
            groups.set(entry.sweep.sweepId, members);
            items.push({ sweepId: entry.sweep.sweepId, members });
        }
        members.push(entry);
    }
    for (const members of groups.values()) {
        members.sort((a, b) => (a.sweep?.index ?? 0) - (b.sweep?.index ?? 0));
    }
    return items;
}

export function RunSelect({ runs, sweeps = null }: { runs: RunsView; sweeps?: SweepList | null }) {
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
            {grouped(kept).map((item) => ('runId' in item
                ? <option key={item.runId} value={item.runId}>{runLabel(item, baseline, sweeps)}</option>
                : (
                    <optgroup key={`sweep${item.sweepId}`}
                              label={`Sweep: ${sweeps?.sweeps.find((sweep) => sweep.sweepId === item.sweepId)?.name ?? `sweep ${item.sweepId}`}`}>
                        {item.members.map((entry) => (
                            <option key={entry.runId} value={entry.runId}>{runLabel(entry, baseline, sweeps)}</option>
                        ))}
                    </optgroup>
                )))}
        </select>
    );
}
