/* ========================================
   RESULT PANE
   The right of the window, beside the Design form: the last good run's figures or its results
   table, the run they come from, and the Export button.

   The pane always shows a finished run, so what it shows can fall behind the form. A strip under
   its header says so: while a run is going, which run the pane still shows; after a run was
   cancelled or failed, that the pane kept the run before; and once the form is edited, which
   fields differ from the config the shown run ran, with the value each had then and has now.
   Sean Bowman [11/19/2026]
   ======================================== */

import { useMemo, useState } from 'react';

import { ResultsTable } from '../analyze/ResultsTable';
import { DownloadIcon, InfoIcon } from '../components/Icons';
import { formatClock } from '../run/stageText';
import type { RunView } from '../run/useRunEvents';
import type { Config, Mode, ResultTable, Schema, ViewIndex } from '../types';
import { FigureView } from '../view/FigureView';
import { changesSince, type FieldChange } from './changes';

const changesListed = 3;        // changes named in the strip; the rest are counted, and all are in its tooltip

interface ResultPaneProps {
    index: ViewIndex | null;
    mode: Mode;
    run: RunView;
    schema: Schema | null;
    config: Config;
    table: ResultTable | null;
    tableLoading: boolean;
    tableError: string;
    onExport: () => void;
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

function changeText(change: FieldChange): string {
    return `${change.label}, ${change.before} to ${change.after}`;
}

/** What the strip says, and whether it warns, or null when the pane is current. */
function statusOf(run: RunView, shownRun: number | null, changes: FieldChange[]): { text: string; tone: 'quiet' | 'warn' } | null {
    if (run.state === 'running') {
        return {
            tone: 'quiet',
            text: shownRun !== null
                ? `Run ${run.runId} is running. This shows run ${shownRun} until it finishes.`
                : `Run ${run.runId} is running. Its figures and results appear here when it finishes.`,
        };
    }
    const parts: string[] = [];
    if ((run.state === 'cancelled' || run.state === 'error') && run.runId !== null && run.runId !== shownRun) {
        parts.push(run.state === 'cancelled' ? `Run ${run.runId} was cancelled.` : `Run ${run.runId} failed; the run log has the error.`);
    }
    if (shownRun !== null && changes.length > 0) {
        const listed = changes.slice(0, changesListed).map(changeText).join('; ');
        const more = changes.length > changesListed ? `; and ${changes.length - changesListed} more` : '';
        const count = changes.length === 1 ? 'One field has' : `${changes.length} fields have`;
        parts.push(`This shows run ${shownRun}. ${count} changed since it ran: ${listed}${more}.`);
    } else if (parts.length > 0 && shownRun !== null) {
        parts.push(`This shows run ${shownRun}.`);
    }
    return parts.length > 0 ? { tone: 'warn', text: parts.join(' ') } : null;
}

export function ResultPane({ index, mode, run, schema, config, table, tableLoading, tableError, onExport,
                             onNotify }: ResultPaneProps) {
    const [showing, setShowing] = useState<'figure' | 'table'>('figure');

    const shownRun = index?.runId ?? null;
    const changes = useMemo(
        () => (schema && index?.config ? changesSince(schema, index.config, config) : []),
        [schema, index, config]);
    const status = statusOf(run, shownRun, changes);

    // The run's time and the result table's headline: thrust, delivered Isp, propellants
    const headline = table && table.runId === shownRun ? table.summary.split(/\s{2,}/).filter(Boolean) : [];
    const meta = [index?.elapsedSec != null ? `finished in ${formatClock(index.elapsedSec)}` : '', ...headline]
        .filter(Boolean).join(' · ');

    return (
        <section className="result-pane card" aria-label="Result">
            <header className="result-head">
                <span className={`run-chip ${shownRun === null ? 'is-empty' : ''}`}>
                    {shownRun !== null ? `Run ${shownRun}` : 'No run yet'}
                </span>
                {index?.runName && <span className="result-name">{index.runName}</span>}
                {meta && <span className="muted result-meta">{meta}</span>}
                <span className="toolbar-spacer" />
                <div className="segmented" role="group" aria-label="Result view">
                    <button type="button" className={showing === 'figure' ? 'is-selected' : ''} aria-pressed={showing === 'figure'}
                            onClick={() => setShowing('figure')}>Figure</button>
                    <button type="button" className={showing === 'table' ? 'is-selected' : ''} aria-pressed={showing === 'table'}
                            onClick={() => setShowing('table')}>Table</button>
                </div>
                <button type="button" className="button" onClick={onExport} title="Copy the run's outputs to a folder">
                    <DownloadIcon /> Export
                </button>
            </header>
            {status && (
                <div className={`result-status is-${status.tone}`} role="status"
                     title={changes.length > changesListed ? changes.map(changeText).join('\n') : undefined}>
                    <InfoIcon />
                    <span>{status.text}</span>
                </div>
            )}
            <div className="result-content" hidden={showing !== 'figure'}>
                <FigureView index={index} mode={mode} />
            </div>
            <div className="result-content" hidden={showing !== 'table'}>
                <ResultsTable table={table} loading={tableLoading} error={tableError} onNotify={onNotify} />
            </div>
        </section>
    );
}
