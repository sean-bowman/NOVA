/* ========================================
   RESULT PANE
   The right of the window, beside the Design form: a run's figures or its results table, the
   run they come from, the baseline it is compared against, and the Export button.

   The run list holds the runs the server keeps. The pane follows the latest until another run is
   picked, and Generate puts it back to following; while a run is going, the pane shows its
   contour and flow fields once its contour stage has settled them. The baseline is any kept run:
   the line plots draw it dashed under the shown run, and the table sets its values and the change
   from them beside the shown run's.

   What the pane shows can fall behind the form, so a strip under its header says so: while a
   run is going, which run the pane shows; after a run was cancelled or failed, that the pane kept
   the run before; and once the form is edited, which fields differ from the config the shown run
   ran, with a button that puts that config back into the form. A second strip names the fields
   that differ between the shown run and the baseline, and a third lists the warnings the shown
   run raised, each once with the number of times it came. A saved run whose result no longer
   loads in this NOVA says so in place of its figures, and its config can still go into the form.

   The pencil beside the run menu opens the shown run's details (RunDetails): its name and note,
   the baseline, putting its config into the form, and deleting it.

   The Sweep view shows a trade sweep (SweepView): its plot and the table of its points, from which
   a click shows a point's run. A sweep just queued opens in it.
   Sean Bowman [11/19/2026]
   ======================================== */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../api';
import { ResultsTable } from '../analyze/ResultsTable';
import { DownloadIcon, InfoIcon, PencilIcon } from '../components/Icons';
import type { RunView } from '../run/useRunEvents';
import { SweepView } from '../sweep/SweepView';
import type { Config, Mode, ResultTable, RunEntry, RunWarning, Schema, SweepList } from '../types';
import { FigureView, type FigureLayout } from '../view/FigureView';
import { changesSince, type FieldChange } from './changes';
import { RunDetails } from './RunDetails';
import { RunSelect, runTitle } from './RunSelect';
import type { RunsView } from './useRuns';

const changesListed = 3;        // changes named in a strip; the rest are counted, and all are in its tooltip
const warningsListed = 3;       // warnings listed in their strip; the rest are counted, and all are in its tooltip

interface ResultPaneProps {
    runs: RunsView;
    mode: Mode;
    run: RunView;
    schema: Schema | null;
    config: Config;
    sweeps: SweepList | null;
    focusSweep: { sweepId: number; at: number } | null;   // a sweep to open in the Sweep view, and when it was asked for
    onExport: () => void;
    onEditFrom: (entry: RunEntry) => void;
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

/** A warning as its strip lists it: the message, where it was raised, and how often. */
export function warningText(warning: RunWarning): string {
    const times = warning.count > 1 ? `, ${warning.count} times` : '';
    return `${warning.message} (${warning.category}, ${warning.where}${times})`;
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
            text = runs.index?.available.includes('circuitIterations')
                ? `Run ${run.runId} is running. Its contour and flow fields are in, and Circuit iterations draws its `
                  + `coolant circuit's passes as they end; the rest follows when it finishes.`
                : `Run ${run.runId} is running. Its contour and flow fields are in; cooling, the plume and the table `
                  + 'follow when it finishes.';
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

export function ResultPane({ runs, mode, run, schema, config, sweeps, focusSweep, onExport, onEditFrom, onNotify }: ResultPaneProps) {
    const [showing, setShowing] = useState<'figure' | 'table' | 'sweep'>('figure');
    const [sweepShown, setSweepShown] = useState<number | null>(null);
    const [detailsFor, setDetailsFor] = useState<number | null>(null);
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

    // The warnings of the run shown: the run in progress keeps them in the event stream's state
    const shownWarnings: RunWarning[] = partial ? run.warnings : (shownEntry?.warnings ?? []);

    // A sweep just queued opens in the Sweep view
    useEffect(() => {
        if (focusSweep) {
            setSweepShown(focusSweep.sweepId);
            setShowing('sweep');
        }
    }, [focusSweep]);

    const openView = useCallback((key: string) => {
        setSelected(key);
        setLayout('single');
        setShowing('figure');
    }, []);

    const available = useMemo(() => new Set(index?.available ?? []), [index]);
    const keptRuns = list?.runs ?? [];
    const detailsEntry = detailsFor !== null ? runs.entry(detailsFor) : undefined;
    // The form differs from the run shown, finished, whose config it can go back to
    const canEditFrom = run.state !== 'running' && !partial && formChanges.length > 0 && !!shownEntry?.config;
    const loadError = !partial && shown !== null ? (index?.loadError ?? '') : '';

    return (
        <section className="result-pane card" aria-label="Result">
            <header className="result-head">
                <RunSelect runs={runs} sweeps={sweeps} />
                <button type="button" className="icon-button" disabled={!shownEntry || partial}
                        aria-label={shownEntry ? `Details of run ${shownEntry.runId}` : 'Run details'}
                        title={shownEntry ? `Run ${shownEntry.runId}: name, note, baseline, edit from it, delete` : 'No finished run shown'}
                        onClick={() => shownEntry && setDetailsFor(shownEntry.runId)}>
                    <PencilIcon />
                </button>
                <span className="toolbar-spacer" />
                <label className="baseline-pick">
                    <span className="muted">Baseline</span>
                    <select className="input baseline-select" aria-label="Baseline run" value={baseline ?? ''}
                            disabled={keptRuns.length === 0} onChange={(event) => runs.setBaseline(event.target.value ? Number(event.target.value) : null)}
                            title="A run the shown run is compared against: drawn dashed on the line plots, and set beside it in the table">
                        <option value="">None</option>
                        {keptRuns.map((entry) => (
                            <option key={entry.runId} value={entry.runId}>Run {entry.runId}{runTitle(entry) ? ` · ${runTitle(entry)}` : ''}</option>
                        ))}
                    </select>
                </label>
                <div className="segmented" role="group" aria-label="Result view">
                    <button type="button" className={showing === 'figure' ? 'is-selected' : ''} aria-pressed={showing === 'figure'}
                            onClick={() => setShowing('figure')}>Figure</button>
                    <button type="button" className={showing === 'table' ? 'is-selected' : ''} aria-pressed={showing === 'table'}
                            onClick={() => setShowing('table')}>Table</button>
                    <button type="button" className={showing === 'sweep' ? 'is-selected' : ''} aria-pressed={showing === 'sweep'}
                            disabled={!sweeps || sweeps.sweeps.length === 0}
                            title={sweeps && sweeps.sweeps.length > 0 ? 'A trade sweep: its plot and the table of its points'
                                                                      : 'No trade sweep yet: Sweep in the run bar queues one'}
                            onClick={() => setShowing('sweep')}>Sweep</button>
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
                    {canEditFrom && shownEntry && (
                        <button type="button" className="button strip-action" onClick={() => onEditFrom(shownEntry)}
                                title={`Put the config run ${shownEntry.runId} ran back into the Design form`}>
                            Edit from run {shownEntry.runId}
                        </button>
                    )}
                </div>
            )}
            {loadError && (
                <div className="result-status is-warn" role="status">
                    <InfoIcon />
                    <span>Run {shown} cannot be drawn: {loadError}. Its config can still go into the form.</span>
                    {shownEntry?.config && !canEditFrom && (
                        <button type="button" className="button strip-action" onClick={() => onEditFrom(shownEntry)}>
                            Edit from run {shownEntry.runId}
                        </button>
                    )}
                </div>
            )}
            {baselineText && (
                <div className="result-status is-baseline" role="status"
                     title={baselineChanges.length > changesListed ? baselineChanges.map(changeText).join('\n') : undefined}>
                    <span className="baseline-key" aria-hidden="true" />
                    <span>{baselineText}</span>
                </div>
            )}
            {shownWarnings.length > 0 && shown !== null && (
                <div className="result-status is-caution" role="status"
                     title={shownWarnings.length > warningsListed ? shownWarnings.map(warningText).join('\n') : undefined}>
                    <InfoIcon />
                    <div className="warning-text">
                        <span>
                            Run {shown} raised {shownWarnings.length === 1 ? 'a warning' : `${shownWarnings.length} warnings`}
                            {partial ? ' so far' : ''}; the run log has them in place.
                        </span>
                        <ul className="warning-list">
                            {shownWarnings.slice(0, warningsListed).map((warning) => (
                                <li key={`${warning.category}:${warning.message}`}>{warningText(warning)}</li>
                            ))}
                            {shownWarnings.length > warningsListed && <li>and {shownWarnings.length - warningsListed} more</li>}
                        </ul>
                    </div>
                </div>
            )}
            <div className="result-content" hidden={showing !== 'figure'}>
                <FigureView index={index} mode={mode} compare={against} selected={selected} layout={layout}
                            runChoice={runs.choice} liveRevision={run.iterationRevision} onSelect={setSelected}
                            onLayout={setLayout} onNotify={onNotify} />
            </div>
            <div className="result-content" hidden={showing !== 'table'}>
                <ResultsTable table={table} loading={tableLoading} error={tableError} available={available}
                              emptyText={partial ? `The table fills when run ${shown} finishes.` : 'Generate a nozzle to fill this table.'}
                              onOpenView={openView} onNotify={onNotify} />
            </div>
            <div className="result-content" hidden={showing !== 'sweep'}>
                {showing === 'sweep' && (
                    <SweepView list={sweeps} runs={runs} mode={mode} chosen={sweepShown} onChoose={setSweepShown} onNotify={onNotify} />
                )}
            </div>
            {detailsEntry && (
                <RunDetails key={detailsEntry.runId} entry={detailsEntry} baseline={baseline} store={list?.store ?? null}
                            onEditFrom={onEditFrom} onBaseline={runs.setBaseline} onClose={() => setDetailsFor(null)}
                            onNotify={onNotify} />
            )}
        </section>
    );
}
