/* ========================================
   SWEEP VIEW
   A trade sweep in the result pane: one headline number plotted against the swept field, a line
   per value of a second field, and below it the table of the sweep's points. Each row is a point:
   its swept values, its run, the run's headline numbers, and its state; a failed point carries
   its reason. A click on a row or on a plotted point shows that run in the pane.

   Each number's column carries the validation status of the model behind it, read from the
   result table of one of the sweep's runs, so the sweep's numbers say how far they can be trusted
   as the result pane's headline does.

   A sweep whose points were cancelled, or whose window closed before they ran, can queue them
   again. Delete takes the sweep, its queued points and its runs, except a run that was named or is
   the baseline.
   Sean Bowman [11/20/2026]
   ======================================== */

import { Fragment, useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../api';
import { ValidationBadge } from '../analyze/ValidationBadge';
import { formatClock } from '../run/stageText';
import type { RunsView } from '../result/useRuns';
import type { Mode, Sweep, SweepList, SweepPoint, ValidationBadgeInfo } from '../types';
import { loadPlotly } from '../view/PlotlyFigure';

interface SweepViewProps {
    list: SweepList | null;
    runs: RunsView;
    mode: Mode;
    chosen: number | null;
    onChoose: (sweepId: number) => void;
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

const stateText: Record<SweepPoint['state'], string> = {
    queued: 'queued', running: 'running', done: 'done', failed: 'failed', cancelled: 'not run',
};

/** A sweep's progress in a few words: '5 of 8 done, 1 failed, 2 to run'. */
export function progressText(sweep: Sweep): string {
    const { counts } = sweep;
    const parts = [`${counts.done} of ${sweep.points.length} done`];
    if (counts.failed > 0) {
        parts.push(`${counts.failed} failed`);
    }
    if (counts.running + counts.queued > 0) {
        parts.push(`${counts.running + counts.queued} to run`);
    }
    if (counts.cancelled > 0) {
        parts.push(`${counts.cancelled} not run`);
    }
    return parts.join(', ');
}

function SweepPlot({ sweep, number, mode, onPick }: { sweep: Sweep; number: string; mode: Mode; onPick: (runId: number) => void }) {
    const host = useRef<HTMLDivElement>(null);
    const [message, setMessage] = useState('');
    const pick = useRef(onPick);
    pick.current = onPick;
    // Draw again as points finish: the key moves with each point's state and run
    const drawKey = sweep.points.map((point) => `${point.state}:${point.runId ?? ''}:${point.kept}`).join(',');

    useEffect(() => {
        let cancelled = false;
        const element = host.current;
        if (!element || !number) {
            return;
        }
        Promise.all([loadPlotly(), api.sweepFigure(sweep.sweepId, number, mode)])
            .then(([Plotly, figure]) => {
                if (cancelled) {
                    return undefined;
                }
                setMessage('');
                return Plotly.react(element, figure.data as Plotly.Data[], { ...figure.layout, autosize: true } as Partial<Plotly.Layout>,
                                    { responsive: true, displaylogo: false })
                    .then((graph) => {
                        const target = graph as unknown as { removeAllListeners?: (name: string) => void; on: (name: string, handler: (data: { points: { customdata?: unknown }[] }) => void) => void };
                        target.removeAllListeners?.('plotly_click');
                        target.on('plotly_click', (data) => {
                            const runId = data.points[0]?.customdata;
                            if (typeof runId === 'number') {
                                pick.current(runId);
                            }
                        });
                    });
            })
            .catch((failure: Error) => {
                if (!cancelled) {
                    setMessage(failure.message);
                }
            });
        return () => {
            cancelled = true;
        };
    }, [sweep.sweepId, number, mode, drawKey]);

    // The plot follows the pane's size, as the figures do
    useEffect(() => {
        const element = host.current;
        if (!element) {
            return;
        }
        const observer = new ResizeObserver(() => {
            if ((element as unknown as { _fullLayout?: unknown })._fullLayout && element.clientWidth > 0) {
                loadPlotly().then((Plotly) => Plotly.Plots.resize(element)).catch(() => undefined);
            }
        });
        observer.observe(element);
        return () => observer.disconnect();
    }, []);

    return (
        <div className="sweep-plot">
            <div ref={host} className="plotly-host" hidden={!!message} />
            {message && <div className="figure-message">{message}</div>}
        </div>
    );
}

export function SweepView({ list, runs, mode, chosen, onChoose, onNotify }: SweepViewProps) {
    const sweeps = list?.sweeps ?? [];
    const sweep = sweeps.find((entry) => entry.sweepId === chosen) ?? sweeps[0] ?? null;
    const [number, setNumber] = useState('isp');
    const [confirming, setConfirming] = useState(false);
    const [badges, setBadges] = useState<Record<string, ValidationBadgeInfo>>({});

    const plotted = sweep?.numbers.some((entry) => entry.key === number) ? number : (sweep?.numbers[0]?.key ?? '');
    const sample = sweep?.points.find((point) => point.kept)?.runId ?? null;

    // -- The validation status of each number, from one of the sweep's runs -- //
    useEffect(() => {
        setBadges({});
        if (sample === null) {
            return;
        }
        let cancelled = false;
        api.analysis(sample, null)
            .then((table) => {
                if (!cancelled) {
                    setBadges(Object.fromEntries(table.headline.filter((item) => item.validation)
                        .map((item) => [item.key, item.validation as ValidationBadgeInfo])));
                }
            })
            .catch(() => undefined);
        return () => {
            cancelled = true;
        };
    }, [sample]);

    useEffect(() => setConfirming(false), [sweep?.sweepId]);

    const keptRuns = useMemo(() => (sweep ? sweep.points.filter((point) => point.kept) : []), [sweep]);
    const named = keptRuns.filter((point) => {
        const entry = runs.entry(point.runId);
        return !!entry?.title || point.runId === runs.baseline;
    });

    if (!sweep) {
        return <div className="empty">No trade sweep yet. Sweep in the run bar queues one run per value of a field.</div>;
    }

    const show = (runId: number | null) => {
        if (runId !== null && runs.entry(runId)) {
            runs.choose(runId);
        }
    };

    const resume = () => {
        api.resumeSweep(sweep.sweepId)
            .then((done) => onNotify('info', `${sweep.name}: ${done.queued} ${done.queued === 1 ? 'run' : 'runs'} queued again`))
            .catch((failure: Error) => onNotify('error', 'Sweep not resumed', failure.message));
    };

    const remove = () => {
        api.deleteSweep(sweep.sweepId)
            .then((done) => onNotify('info', `${sweep.name} deleted`,
                                     `${done.runs.length} ${done.runs.length === 1 ? 'run' : 'runs'} deleted with it`))
            .catch((failure: Error) => onNotify('error', 'Sweep not deleted', failure.message))
            .finally(() => setConfirming(false));
    };

    const first = sweep.fields[0];
    return (
        <div className="sweep-view">
            <div className="figure-toolbar sweep-toolbar">
                <select className="input view-select" aria-label="Sweep shown" value={sweep.sweepId}
                        onChange={(event) => onChoose(Number(event.target.value))}>
                    {sweeps.map((entry) => (
                        <option key={entry.sweepId} value={entry.sweepId}>
                            {entry.name} · {entry.points.length} {entry.points.length === 1 ? 'run' : 'runs'}
                        </option>
                    ))}
                </select>
                <span className="muted sweep-progress">{progressText(sweep)}</span>
                <span className="toolbar-spacer" />
                {sweep.numbers.length > 0 && (
                    <label className="baseline-pick">
                        <span className="muted">Plot</span>
                        <select className="input baseline-select" aria-label="Number plotted" value={plotted}
                                onChange={(event) => setNumber(event.target.value)}>
                            {sweep.numbers.map((entry) => <option key={entry.key} value={entry.key}>{entry.label}</option>)}
                        </select>
                    </label>
                )}
                {sweep.counts.cancelled > 0 && (
                    <button type="button" className="button" onClick={resume}
                            title="Queue the points that were cancelled or did not run before NOVA closed">
                        Run the {sweep.counts.cancelled} not run
                    </button>
                )}
                <button type="button" className="button button-quiet" onClick={() => setConfirming(true)}>Delete sweep</button>
            </div>
            {confirming && (
                <div className="result-status is-warn sweep-confirm" role="alert">
                    <span>
                        Delete {sweep.name}, its queued points and its {keptRuns.length - named.length} unnamed
                        {keptRuns.length - named.length === 1 ? ' run' : ' runs'}?
                        {named.length > 0 ? ` ${named.length === 1 ? 'Its named run or baseline stays' : 'Its named runs and the baseline stay'} as runs of their own.` : ''}
                    </span>
                    <span className="toolbar-spacer" />
                    <button type="button" className="button strip-action" onClick={() => setConfirming(false)}>Keep it</button>
                    <button type="button" className="button button-danger strip-action" onClick={remove}>Delete</button>
                </div>
            )}
            {sweep.numbers.length > 0
                ? <SweepPlot sweep={sweep} number={plotted} mode={mode} onPick={show} />
                : <div className="sweep-plot sweep-plot-empty muted">The plot draws as the sweep's first run finishes.</div>}
            <div className="sweep-table-wrap">
                <table className="result-table sweep-table">
                    <thead>
                        <tr>
                            <th className="sweep-index">#</th>
                            {sweep.fields.map((field) => <th key={field.key} className="sweep-input">{field.label}</th>)}
                            <th>Run</th>
                            <th>State</th>
                            {sweep.numbers.map((entry) => (
                                <th key={entry.key} className={`sweep-number ${entry.key === plotted ? 'is-plotted' : ''}`}>
                                    <span className="sweep-number-head">
                                        <span>{entry.label}{entry.unit ? ` [${entry.unit}]` : ''}</span>
                                        <ValidationBadge info={badges[entry.key]} subject={entry.label} />
                                    </span>
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {sweep.points.map((point) => {
                            const entry = point.kept ? runs.entry(point.runId) : undefined;
                            const shown = point.kept && point.runId === runs.shown;
                            const columns = sweep.fields.length + 2 + sweep.numbers.length;   // every column past the index
                            return (
                                <Fragment key={point.index}>
                                <tr className={`sweep-point is-${point.state} ${shown ? 'is-shown' : ''} ${point.kept ? 'is-kept' : ''}`}
                                    onClick={() => show(point.runId)} aria-selected={shown}
                                    title={point.kept ? `Show run ${point.runId}` : (point.error || stateText[point.state])}>
                                    <td className="sweep-index">{point.index + 1}</td>
                                    {point.texts.map((text, at) => <td key={sweep.fields[at].key} className="result-value">{text}</td>)}
                                    <td className="sweep-run">
                                        {point.kept ? `${point.runId}${entry ? ` · ${formatClock(entry.elapsedSec)}` : ''}`
                                                    : (point.runId !== null && point.state === 'done' ? 'deleted' : '--')}
                                    </td>
                                    <td className={`sweep-state is-${point.state}`}>{stateText[point.state]}</td>
                                    {sweep.numbers.map((number) => {
                                        const value = point.numbers[number.key];
                                        return (
                                            <td key={number.key} className={`result-value ${value ? '' : 'is-blank'} ${value?.tone === 'warn' ? 'is-warn' : ''}`}>
                                                {value ? value.text : '--'}
                                            </td>
                                        );
                                    })}
                                </tr>
                                {point.error && (
                                    <tr className={`sweep-error-row is-${point.state}`}>
                                        <td />
                                        <td colSpan={columns} className="sweep-error">{point.error}</td>
                                    </tr>
                                )}
                                </Fragment>
                            );
                        })}
                    </tbody>
                </table>
            </div>
            <p className="muted sweep-foot">
                {first.label} varies {sweep.fields.length > 1 ? `fastest, against ${sweep.fields[1].label}` : 'from point to point'};
                every other field is the config the sweep started from.
            </p>
        </div>
    );
}
