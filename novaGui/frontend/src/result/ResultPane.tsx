/* ========================================
   RESULT PANE
   The right of the window, beside the Design form: a run's figures or its results table, the
   run they come from, the baseline it is compared against, and the Export button.

   The run list holds the runs the server keeps. The pane follows the latest until another run is
   picked, and a new run puts it back to following; while a run is going, the pane shows its
   contour and flow fields once its contour stage has settled them. The baseline is any kept run:
   the line plots draw it dashed under the shown run, and the table sets its values and the change
   from them beside the shown run's.

   What the pane shows can fall behind the form, so a strip under its header says so: while a
   run is going, which run the pane shows; after a run was cancelled or failed, that the pane kept
   the run before; and once the form is edited, which fields differ from the config the shown run
   ran. A second strip names the fields that differ between the shown run and the baseline.
   Sean Bowman [11/19/2026]
   ======================================== */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../api';
import { ResultsTable } from '../analyze/ResultsTable';
import { DownloadIcon, InfoIcon } from '../components/Icons';
import { formatClock } from '../run/stageText';
import type { RunView } from '../run/useRunEvents';
import type { Config, Mode, ResultTable, Schema } from '../types';
import { FigureView, type FigureLayout } from '../view/FigureView';
import { changesSince, type FieldChange } from './changes';
import { RunSelect } from './RunSelect';
import type { RunsView } from './useRuns';

const changesListed = 3;        // changes named in a strip; the rest are counted, and all are in its tooltip

interface ResultPaneProps {
    runs: RunsView;
    mode: Mode;
    run: RunView;
    schema: Schema | null;
    config: Config;
    onExport: () => void;
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

function changeText(change: FieldChange): string {
    return `${change.label}, ${change.before} to ${change.after}`;
}

function listed(changes: FieldChange[]): string {
    const named = changes.slice(0, changesListed).map(changeText).join('; ');
    const more = changes.length > changesListed ? `; and ${changes.length - changesListed} more` : '';
    return `${named}${more}`;
}

/** What the strip says, and whether it warns, or null when the pane is current. */
function statusOf(run: RunView, runs: RunsView, changes: FieldChange[]): { text: string; tone: 'quiet' | 'warn' } | null {
    const shown = runs.shown;
    if (run.state === 'running') {
        let text: string;
        if (runs.partial) {
            text = `Run ${run.runId} is running. Its contour and flow fields are in; cooling, the plume and the table follow when it finishes.`;
        } else if (shown !== null && runs.choice === 'latest') {
            text = `Run ${run.runId} is running. This shows run ${shown} until its contour is in.`;
        } else if (shown !== null) {
            text = `Run ${run.runId} is running. This shows run ${shown}.`;
        } else {
            text = `Run ${run.runId} is running. Its contour and flow fields appear here as its contour stage ends.`;
        }
        return { tone: 'quiet', text };
    }
    const parts: string[] = [];
    if ((run.state === 'cancelled' || run.state === 'error') && run.runId !== null && run.runId !== shown) {
        parts.push(run.state === 'cancelled' ? `Run ${run.runId} was cancelled.` : `Run ${run.runId} failed; the run log has the error.`);
    }
    if (shown !== null && changes.length > 0) {
        const count = changes.length === 1 ? 'One field has' : `${changes.length} fields have`;
        parts.push(`This shows run ${shown}. ${count} changed since it ran: ${listed(changes)}.`);
    } else if (parts.length > 0 && shown !== null) {
        parts.push(`This shows run ${shown}.`);
    }
    return parts.length > 0 ? { tone: 'warn', text: parts.join(' ') } : null;
}

export function ResultPane({ runs, mode, run, schema, config, onExport, onNotify }: ResultPaneProps) {
    const [showing, setShowing] = useState<'figure' | 'table'>('figure');
    const [selected, setSelected] = useState('contour');
    const [layout, setLayout] = useState<FigureLayout>('single');
    const [table, setTable] = useState<ResultTable | null>(null);
    const [tableLoading, setTableLoading] = useState(false);
    const [tableError, setTableError] = useState('');
    const tableRequest = useRef(0);

    const { shown, partial, index, baseline, list } = runs;
    const against = baseline !== null && baseline !== shown && !partial ? baseline : null;
    const shownEntry = runs.entry(shown);
    const baselineEntry = runs.entry(baseline);

    // -- The table of the run shown, beside the baseline's when there is one -- //
    useEffect(() => {
        const request = ++tableRequest.current;
        if (shown === null || partial) {
            setTable({ runId: null, runName: '', summary: '', headline: [], sections: [], baselineRun: null });
            setTableLoading(false);
            setTableError('');
            return;
        }
        setTableLoading(true);
        setTableError('');
        api.analysis(shown, against)
            .then((loaded) => {
                if (request === tableRequest.current) {
                    setTable(loaded);
                    setTableLoading(false);
                }
            })
            .catch((failure: Error) => {
                if (request === tableRequest.current) {
                    setTableError(failure.message);
                    setTableLoading(false);
                }
            });
    }, [shown, partial, against]);

    const formChanges = useMemo(
        () => (schema && index?.config ? changesSince(schema, index.config, config) : []),
        [schema, index, config]);
    const baselineChanges = useMemo(
        () => (schema && against !== null && baselineEntry?.config && index?.config
            ? changesSince(schema, baselineEntry.config, index.config) : []),
        [schema, against, baselineEntry, index]);
    const status = statusOf(run, runs, formChanges);

    let baselineText = '';
    if (against !== null && baselineEntry) {
        baselineText = baselineChanges.length > 0
            ? `Against run ${against}, the baseline: ${listed(baselineChanges)}.`
            : `Against run ${against}, the baseline, which ran the same config.`;
    } else if (baseline !== null && baseline === shown) {
        baselineText = `Run ${shown} is the baseline the other runs are compared against.`;
    }

    // The run's time and its headline: thrust, delivered Isp, propellants
    let meta = '';
    if (partial) {
        meta = 'running, contour stage done';
    } else if (shownEntry) {
        meta = [`finished in ${formatClock(shownEntry.elapsedSec)}`, ...shownEntry.headline.split(/\s{2,}/).filter(Boolean)]
            .join(' · ');
    }

    const openView = useCallback((key: string) => {
        setSelected(key);
        setLayout('single');
        setShowing('figure');
    }, []);

    const available = useMemo(() => new Set(index?.available ?? []), [index]);
    const keptRuns = list?.runs ?? [];

    return (
        <section className="result-pane card" aria-label="Result">
            <header className="result-head">
                <RunSelect runs={runs} />
                <span className="muted result-meta" title={meta}>{meta}</span>
                <label className="baseline-pick">
                    <span className="muted">Baseline</span>
                    <select className="input baseline-select" aria-label="Baseline run" value={baseline ?? ''}
                            disabled={keptRuns.length === 0} onChange={(event) => runs.setBaseline(event.target.value ? Number(event.target.value) : null)}
                            title="A run the shown run is compared against: drawn dashed on the line plots, and set beside it in the table">
                        <option value="">None</option>
                        {keptRuns.map((entry) => (
                            <option key={entry.runId} value={entry.runId}>Run {entry.runId}{entry.runName ? ` · ${entry.runName}` : ''}</option>
                        ))}
                    </select>
                </label>
                <div className="segmented" role="group" aria-label="Result view">
                    <button type="button" className={showing === 'figure' ? 'is-selected' : ''} aria-pressed={showing === 'figure'}
                            onClick={() => setShowing('figure')}>Figure</button>
                    <button type="button" className={showing === 'table' ? 'is-selected' : ''} aria-pressed={showing === 'table'}
                            onClick={() => setShowing('table')}>Table</button>
                </div>
                <button type="button" className="button" onClick={onExport} title="Copy a run's outputs to a folder">
                    <DownloadIcon /> Export
                </button>
            </header>
            {status && (
                <div className={`result-status is-${status.tone}`} role="status"
                     title={formChanges.length > changesListed ? formChanges.map(changeText).join('\n') : undefined}>
                    <InfoIcon />
                    <span>{status.text}</span>
                </div>
            )}
            {baselineText && (
                <div className="result-status is-baseline" role="status"
                     title={baselineChanges.length > changesListed ? baselineChanges.map(changeText).join('\n') : undefined}>
                    <span className="baseline-key" aria-hidden="true" />
                    <span>{baselineText}</span>
                </div>
            )}
            <div className="result-content" hidden={showing !== 'figure'}>
                <FigureView index={index} mode={mode} compare={against} selected={selected} layout={layout}
                            runChoice={runs.choice} onSelect={setSelected} onLayout={setLayout} onNotify={onNotify} />
            </div>
            <div className="result-content" hidden={showing !== 'table'}>
                <ResultsTable table={table} loading={tableLoading} error={tableError} available={available}
                              emptyText={partial ? `The table fills when run ${shown} finishes.` : 'Generate a nozzle to fill this table.'}
                              onOpenView={openView} onNotify={onNotify} />
            </div>
        </section>
    );
}
