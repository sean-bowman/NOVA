/* ========================================
   PLUME SWEEP VIEW
   A run's plume over a list of ambient pressures (novaGui.plumeSweeps), solved on the run's own
   nozzle and kept with the run. The plot draws the plume boundaries over one another in lip radii
   from the exit plane, each named by its lip pressure ratio and its ambient; a boundary past the
   march's trusted bound of mass continuity draws dashed. The table gives each ambient's lip
   pressure ratio, delivered thrust coefficient, specific impulse and thrust, fully expanded jet
   diameter, first shock on the axis and the march's mass error, each column with the validation
   status of the models behind it. An ambient the march refused carries its reason.

   New plume sweep opens the dialog (PlumeSweepDialog); it needs the form's unit table, so a
   popped-out window shows the sweeps without starting one. A sweep whose window closed before its
   ambients were solved can solve them again, and Delete takes the sweep, cancelling it if it is
   solving.
   Sean Bowman [11/22/2026]
   ======================================== */

import { Fragment, useEffect, useRef, useState } from 'react';

import { api } from '../api';
import { ValidationBadge } from '../analyze/ValidationBadge';
import type { UnitTable } from '../design/units';
import type { Mode, PlumePoint, PlumeSweep, PlumeSweepList } from '../types';
import { loadPlotly } from './PlotlyFigure';
import { PlumeSweepDialog } from './PlumeSweepDialog';

interface PlumeSweepViewProps {
    runId: number;
    mode: Mode;
    version: number;              // moves when one of the run's plume sweeps changes
    units: UnitTable | null;      // the form's units; without them no sweep starts here
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

const stateText: Record<PlumePoint['state'], string> = {
    queued: 'queued', running: 'solving', done: 'solved', refused: 'refused', failed: 'failed', cancelled: 'not solved',
};

/** A plume sweep's progress in a few words: '4 of 6 solved, 1 refused, 1 to solve'. */
export function plumeProgress(sweep: PlumeSweep): string {
    const { counts } = sweep;
    const parts = [`${counts.done} of ${sweep.points.length} solved`];
    if (counts.refused > 0) {
        parts.push(`${counts.refused} refused`);
    }
    if (counts.failed > 0) {
        parts.push(`${counts.failed} failed`);
    }
    if (counts.running + counts.queued > 0) {
        parts.push(`${counts.running + counts.queued} to solve`);
    }
    if (counts.cancelled > 0) {
        parts.push(`${counts.cancelled} not solved`);
    }
    return parts.join(', ');
}

function PlumePlot({ sweep, mode }: { sweep: PlumeSweep; mode: Mode }) {
    const host = useRef<HTMLDivElement>(null);
    const [message, setMessage] = useState('');
    // Draw again as points end
    const drawKey = sweep.points.map((point) => point.state).join(',');
    const solved = sweep.counts.done;

    useEffect(() => {
        let cancelled = false;
        const element = host.current;
        if (!element) {
            return;
        }
        if (solved === 0) {
            setMessage(sweep.counts.queued + sweep.counts.running > 0 ? 'The plot draws as the first ambient is solved.'
                                                                     : 'No ambient of this sweep was solved.');
            return;
        }
        Promise.all([loadPlotly(), api.plumeSweepFigure(sweep.runId, sweep.number, mode)])
            .then(([Plotly, figure]) => {
                if (cancelled) {
                    return undefined;
                }
                setMessage('');
                return Plotly.react(element, figure.data as Plotly.Data[], { ...figure.layout, autosize: true } as Partial<Plotly.Layout>,
                                    { responsive: true, displaylogo: false });
            })
            .catch((failure: Error) => !cancelled && setMessage(failure.message));
        return () => {
            cancelled = true;
        };
    }, [sweep.runId, sweep.number, mode, drawKey, solved, sweep.counts.queued, sweep.counts.running]);

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
        <div className="sweep-plot plume-sweep-plot">
            <div ref={host} className="plotly-host" hidden={!!message} />
            {message && <div className="figure-message sweep-plot-empty muted">{message}</div>}
        </div>
    );
}

export function PlumeSweepView({ runId, mode, version, units, onNotify }: PlumeSweepViewProps) {
    const [list, setList] = useState<PlumeSweepList | null>(null);
    const [error, setError] = useState('');
    const [chosen, setChosen] = useState<number | null>(null);
    const [adding, setAdding] = useState(false);
    const [confirming, setConfirming] = useState(false);
    const request = useRef(0);

    useEffect(() => {
        const asked = ++request.current;
        api.plumeSweeps(runId)
            .then((loaded) => {
                if (asked === request.current) {
                    setList(loaded);
                    setError('');
                }
            })
            .catch((failure: Error) => asked === request.current && setError(failure.message));
    }, [runId, version]);

    useEffect(() => {
        setChosen(null);
        setConfirming(false);
    }, [runId]);

    const sweeps = list?.runId === runId ? list.sweeps : [];
    const sweep = sweeps.find((entry) => entry.number === chosen) ?? sweeps[0] ?? null;
    useEffect(() => setConfirming(false), [sweep?.number]);

    const limits = list ? { maxPoints: list.maxPoints, nearReach: list.nearReach, maxReach: list.maxReach } : null;
    const dialog = adding && units && limits && (
        <PlumeSweepDialog runId={runId} units={units} limits={limits} onClose={() => setAdding(false)} onNotify={onNotify}
                          onAdded={(added) => setChosen(added.number)} />
    );
    const newButton = units && limits && (
        <button type="button" className={`button ${sweep ? '' : 'button-primary'}`} onClick={() => setAdding(true)}
                title="Solve this run's plume over a list of ambient pressures, on its nozzle, without running it again">
            New plume sweep
        </button>
    );

    if (error) {
        return <div className="figure-pane"><div className="figure-overlay figure-message">{error}</div></div>;
    }
    if (!list) {
        return <div className="figure-pane"><div className="figure-overlay"><span className="spinner" /> Loading plume sweeps</div></div>;
    }
    if (!sweep) {
        return (
            <div className="sweep-view plume-sweep-view plume-sweep-empty">
                <p>
                    No plume sweep of run {runId} yet. A plume sweep solves the run's plume and delivered performance at each
                    of a list of ambient pressures on the run's own nozzle, seconds an ambient, where a trade sweep runs the
                    whole pipeline again at each.
                </p>
                {newButton}
                {!units && <p className="muted">Start one from the main window.</p>}
                {dialog}
            </div>
        );
    }

    const resume = () => {
        api.resumePlumeSweep(runId, sweep.number)
            .then((done) => onNotify('info', `${sweep.name}: ${done.queued} ${done.queued === 1 ? 'ambient' : 'ambients'} queued again`))
            .catch((failure: Error) => onNotify('error', 'Plume sweep not resumed', failure.message));
    };

    const remove = () => {
        api.deletePlumeSweep(runId, sweep.number)
            .then(() => {
                onNotify('info', `${sweep.name} deleted`);
                setChosen(null);
            })
            .catch((failure: Error) => onNotify('error', 'Plume sweep not deleted', failure.message))
            .finally(() => setConfirming(false));
    };

    const columns = sweep.columns;
    return (
        <div className="sweep-view plume-sweep-view">
            <div className="figure-toolbar sweep-toolbar">
                <select className="input view-select" aria-label="Plume sweep shown" value={sweep.number}
                        onChange={(event) => setChosen(Number(event.target.value))}>
                    {sweeps.map((entry) => (
                        <option key={entry.number} value={entry.number}>
                            {entry.name} · {entry.points.length} ambients
                        </option>
                    ))}
                </select>
                <span className="muted sweep-progress">{plumeProgress(sweep)}</span>
                <ValidationBadge info={sweep.badge} subject="The plume" />
                <span className="toolbar-spacer" />
                {sweep.counts.cancelled > 0 && (
                    <button type="button" className="button" onClick={resume}
                            title="Solve the ambients that were cancelled or not solved before NOVA closed">
                        Solve the {sweep.counts.cancelled} not solved
                    </button>
                )}
                {newButton}
                <button type="button" className="button button-quiet" onClick={() => setConfirming(true)}>Delete</button>
            </div>
            {confirming && (
                <div className="result-status is-warn sweep-confirm" role="alert">
                    <span>
                        Delete {sweep.name}?
                        {sweep.counts.running + sweep.counts.queued > 0 ? ' Its ambients still to solve are cancelled.' : ''}
                    </span>
                    <span className="toolbar-spacer" />
                    <button type="button" className="button strip-action" onClick={() => setConfirming(false)}>Keep it</button>
                    <button type="button" className="button button-danger strip-action" onClick={remove}>Delete</button>
                </div>
            )}
            <PlumePlot sweep={sweep} mode={mode} />
            <div className="sweep-table-wrap">
                <table className="result-table sweep-table plume-sweep-table">
                    <thead>
                        <tr>
                            <th className="sweep-index">#</th>
                            <th>Ambient</th>
                            <th>State</th>
                            {columns.map((column) => (
                                <th key={column.key} className="sweep-number">
                                    <span className="sweep-number-head">
                                        <span>{column.label}{column.unit ? ` [${column.unit}]` : ''}</span>
                                        <ValidationBadge info={column.validation} subject={column.label} />
                                    </span>
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {sweep.points.map((point) => {
                            const reason = point.error || (point.notes.length > 0 ? point.notes.join('\n') : stateText[point.state]);
                            const failed = point.state === 'refused' || point.state === 'failed' || point.state === 'cancelled';
                            return (
                                <Fragment key={point.index}>
                                    <tr className={`sweep-point is-${point.state === 'refused' ? 'failed' : point.state}`} title={reason}>
                                        <td className="sweep-index">{point.index + 1}</td>
                                        <td className="result-value">{point.ambientText}</td>
                                        <td className={`sweep-state is-${point.state === 'refused' ? 'failed' : point.state}`}>
                                            {stateText[point.state]}
                                            {point.trustworthy === false ? ', past the bound' : ''}
                                        </td>
                                        {columns.map((column) => {
                                            const cell = point.cells[column.key];
                                            return (
                                                <td key={column.key} className={`result-value ${cell ? '' : 'is-blank'} ${cell?.tone === 'warn' ? 'is-warn' : ''}`}>
                                                    {cell ? cell.text : '--'}
                                                </td>
                                            );
                                        })}
                                    </tr>
                                    {failed && point.error && (
                                        <tr className={`sweep-error-row ${point.state === 'cancelled' ? 'is-cancelled' : 'is-failed'}`}>
                                            <td />
                                            <td colSpan={columns.length + 2} className="sweep-error">{point.error}</td>
                                        </tr>
                                    )}
                                </Fragment>
                            );
                        })}
                    </tbody>
                </table>
            </div>
            <p className="muted sweep-foot">
                Solved on run {runId}'s nozzle{sweep.lip ? `, whose lip static pressure is ${sweep.lip.pressureText}` : ''}; the lip
                pressure ratio is that over the ambient. Every ambient is marched {list.nearReach} lip radii for its numbers
                {sweep.reach > list.nearReach ? `, and ${sweep.reach} for the boundary drawn` : ''}. The jet diameter and the first
                shock are the correlations', which the march cannot give.
            </p>
            {dialog}
        </div>
    );
}
