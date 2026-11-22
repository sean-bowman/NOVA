/* ========================================
   PLUME SWEEP DIALOG
   A run's plume solved on the run's own nozzle without running it again (novaGui.plumeSweeps),
   over one of two things:

   Ambient pressures: a range or a list of ambients in a pressure unit, the engine at rated power.
   Beside them the dialog gives each one's lip pressure ratio, the run's lip static pressure over
   the ambient, which sets how the plume turns at the lip.

   Power levels: one ambient held, and a range or a list of power levels in percent of rated
   chamber pressure. Beside them the dialog gives each one's exit pressure ratio and the power level
   below which the nozzle separates at that ambient. The first ambient puts rated power at the top
   of the march's envelope, as featureShowcase/buildPlumeThrottle.py does.

   Both take the reach the boundaries are drawn to and a name. The march decides which points it
   solves: one that separates the nozzle, or compresses the lip past a weak oblique shock, comes
   back refused with the march's reason.
   Sean Bowman [11/22/2026]
   ======================================== */

import { useEffect, useMemo, useState } from 'react';

import { api } from '../api';
import { CloseIcon } from '../components/Icons';
import { formatNumber, fromSI, toSI, unitsFor, type UnitTable } from '../design/units';
import { FieldEntry } from '../sweep/SweepDialog';
import { valuesOf, type SweepEntry, type Sweepable } from '../sweep/sweepModel';
import type { FieldSpec, PlumeSweep, PlumeSweepKind, PlumeSweepRequest } from '../types';

const ambientField: Sweepable = {
    key: 'ambient', label: 'Ambient pressure', section: '',
    spec: { key: 'ambient', label: 'Ambient pressure', kind: 'float', dimension: 'pressure', unit: 'Pa', choices: [] } as unknown as FieldSpec,
};
const powerField: Sweepable = {
    key: 'power', label: 'Power level', section: '',
    spec: { key: 'power', label: 'Power level', kind: 'float', dimension: '', unit: '%', choices: [] } as unknown as FieldSpec,
};
const firstRatios = [2.0, 0.75];       // [-] the lip pressure ratios a first range spans, low ambient to high
const firstPower = { from: '100', to: '25', count: '16' };     // [%] a first throttle range, 5 percent steps

export interface PlumeLimits {
    maxPoints: number;
    nearReach: number;
    maxReach: number;
    maxFraction: number;
    separationRatio: number;
    maxPressureRatio: number;
}

interface PlumeSweepDialogProps {
    runId: number;
    units: UnitTable;
    limits: PlumeLimits;
    onAdded: (sweep: PlumeSweep) => void;
    onClose: () => void;
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

/** A round number near `value`, `digits` significant figures. */
function rounded(value: number, digits = 2): string {
    return formatNumber(Number(value.toPrecision(digits)));
}

function plural(count: number, kind: PlumeSweepKind): string {
    return kind === 'ambient' ? (count === 1 ? 'ambient' : 'ambients') : (count === 1 ? 'power level' : 'power levels');
}

export function PlumeSweepDialog({ runId, units, limits, onAdded, onClose, onNotify }: PlumeSweepDialogProps) {
    const [lip, setLip] = useState<{ pressure: number | null; exitPressure: number | null; reason: string } | null>(null);
    const [kind, setKind] = useState<PlumeSweepKind>('ambient');
    const [entry, setEntry] = useState<SweepEntry>({ key: 'ambient', how: 'range', from: '', to: '', count: '6', list: '',
                                                     unit: 'kPa', picked: [] });
    const [power, setPower] = useState<SweepEntry>({ key: 'power', how: 'range', ...firstPower, list: '100, 75, 50, 25',
                                                     unit: '', picked: [] });
    const [held, setHeld] = useState({ value: '', unit: 'kPa' });
    const [reach, setReach] = useState(String(limits.nearReach));
    const [name, setName] = useState('');
    const [sending, setSending] = useState(false);

    // The lip pressure, a first range across the lip ratios the march usually holds over, and a
    // first held ambient that puts rated power at the top of the march's envelope
    useEffect(() => {
        let cancelled = false;
        api.plumeLip(runId)
            .then((loaded) => {
                if (cancelled) {
                    return;
                }
                setLip(loaded);
                if (loaded.pressure !== null) {
                    const [low, high] = firstRatios.map((ratio) => fromSI(units, (loaded.pressure as number) / ratio, 'pressure', 'kPa'));
                    setEntry((previous) => ({ ...previous, from: rounded(low), to: rounded(high), list: `${rounded(low)}, ${rounded(high)}` }));
                }
                if (loaded.exitPressure !== null) {
                    const first = fromSI(units, loaded.exitPressure / limits.maxPressureRatio, 'pressure', 'kPa');
                    setHeld({ value: rounded(first, 3), unit: 'kPa' });
                }
            })
            .catch((failure: Error) => !cancelled && setLip({ pressure: null, exitPressure: null, reason: failure.message }));
        return () => {
            cancelled = true;
        };
    }, [runId, units, limits.maxPressureRatio]);

    // Escape closes this dialog alone, ahead of the window's own Escape handling
    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                event.stopPropagation();
                onClose();
            }
        };
        document.addEventListener('keydown', onKey, true);
        return () => document.removeEventListener('keydown', onKey, true);
    }, [onClose]);

    const values = useMemo(() => (kind === 'ambient' ? valuesOf(entry, ambientField, units) : valuesOf(power, powerField, units)),
                           [kind, entry, power, units]);
    const reachValue = Number(reach);
    const heldNumber = held.value.trim() === '' ? NaN : Number(held.value);
    const heldAmbient = Number.isFinite(heldNumber) ? toSI(units, heldNumber, 'pressure', held.unit) : NaN;
    const fractions = kind === 'throttle' && values.ok ? values.values.map((value) => (value as number) / 100) : [];

    // Beside the values: each ambient's lip pressure ratio, or each power level's exit pressure ratio
    let ratios = '';
    let limit = '';
    if (kind === 'ambient' && values.ok && lip?.pressure) {
        ratios = `lip pressure ratio ${values.values.map((ambient) => ((lip.pressure as number) / (ambient as number)).toFixed(2)).join(', ')}`;
    } else if (kind === 'throttle' && lip?.exitPressure && heldAmbient > 0) {
        const exitPressure = lip.exitPressure;
        if (fractions.length > 0) {
            ratios = `exit pressure ratio ${fractions.map((fraction) => ((fraction * exitPressure) / heldAmbient).toFixed(2)).join(', ')}`;
        }
        const separates = (limits.separationRatio * heldAmbient) / exitPressure;
        limit = `At this ambient the nozzle separates below ${rounded(100 * separates, 3)} % power, where the exit pressure ratio `
              + `falls to ${limits.separationRatio}; a power level below it comes back refused.`;
    }

    let problem = '';
    if (lip && lip.pressure === null) {
        problem = `This run's plume cannot be swept: ${lip.reason}.`;
    } else if (kind === 'throttle' && !(heldAmbient > 0)) {
        problem = 'The ambient pressure is a number above zero.';
    } else if (!values.ok) {
        problem = values.message;
    } else if (kind === 'ambient' && values.values.some((value) => (value as number) <= 0)) {
        problem = 'Each ambient pressure is above zero.';
    } else if (kind === 'throttle' && fractions.some((fraction) => fraction <= 0 || fraction > limits.maxFraction)) {
        problem = `Each power level is above 0 and at most ${100 * limits.maxFraction} % of rated.`;
    } else if (values.values.length > limits.maxPoints) {
        problem = `That is ${values.values.length} ${plural(values.values.length, kind)}; a plume sweep solves at most ${limits.maxPoints}.`;
    } else if (!Number.isFinite(reachValue) || reachValue < limits.nearReach || reachValue > limits.maxReach) {
        problem = `The reach is ${limits.nearReach} to ${limits.maxReach} lip radii.`;
    }
    const count = values.ok ? values.values.length : 0;

    const send = () => {
        if (problem || sending || !values.ok) {
            return;
        }
        setSending(true);
        const request: PlumeSweepRequest = kind === 'ambient'
            ? { kind, name, ambients: values.values as number[], unit: entry.unit, reach: reachValue }
            : { kind, name, ambient: heldAmbient, fractions, unit: held.unit, reach: reachValue };
        api.addPlumeSweep(runId, request)
            .then((sweep) => {
                onAdded(sweep);
                onClose();
            })
            .catch((failure: Error) => {
                setSending(false);
                onNotify('error', 'Plume sweep not started', failure.message);
            });
    };

    const pressureUnits = unitsFor(units, 'pressure');
    const lipText = lip === null ? 'reading the lip' : lip.pressure !== null
        ? `lip static pressure ${formatNumber(Number(fromSI(units, lip.pressure, 'pressure', entry.unit || 'kPa').toPrecision(4)))} ${entry.unit || 'kPa'}`
        : '';
    const exitText = lip?.exitPressure
        ? `exit pressure at rated power ${formatNumber(Number(fromSI(units, lip.exitPressure, 'pressure', held.unit).toPrecision(4)))} ${held.unit}`
        : lipText;

    return (
        <div className="modal-scrim" onClick={onClose}>
            <div className="card modal sweep-dialog plume-sweep-dialog" role="dialog" aria-label="Plume sweep"
                 onClick={(event) => event.stopPropagation()}>
                <div className="run-details-head">
                    <h2>Plume sweep over run {runId}</h2>
                    <span className="toolbar-spacer" />
                    <button type="button" className="icon-button" aria-label="Close" onClick={onClose}>
                        <CloseIcon />
                    </button>
                </div>
                <div className="segmented plume-kind" role="group" aria-label="Plume sweep over">
                    <button type="button" className={kind === 'ambient' ? 'is-selected' : ''} aria-pressed={kind === 'ambient'}
                            onClick={() => setKind('ambient')}>Ambient pressures</button>
                    <button type="button" className={kind === 'throttle' ? 'is-selected' : ''} aria-pressed={kind === 'throttle'}
                            onClick={() => setKind('throttle')}>Power levels</button>
                </div>
                {kind === 'ambient' ? (
                    <p className="muted sweep-lead">
                        The run's plume and delivered performance at each ambient, solved on its nozzle without running it
                        again: the contour and the cooling do not depend on the ambient. The sweep is kept with the run.
                    </p>
                ) : (
                    <p className="muted sweep-lead">
                        The run's plume and delivered performance at each power level against one ambient, solved on its nozzle
                        with every pressure scaled by the power level and the gas held at its rated state. It gives how far the
                        engine throttles at that ambient before its nozzle separates. The sweep is kept with the run.
                    </p>
                )}
                {kind === 'ambient' ? (
                    <div className="sweep-row">
                        <div className="sweep-row-head">
                            <span className="eyebrow">Sweep</span>
                            <span>Ambient pressure</span>
                            <span className="muted plume-lip">{lipText}</span>
                        </div>
                        <FieldEntry field={ambientField} entry={entry} values={values} choices={[]} units={pressureUnits}
                                    onChange={(change) => setEntry((previous) => ({ ...previous, ...change }))} />
                        {ratios && <span className="sweep-values muted plume-ratios">{ratios}</span>}
                    </div>
                ) : (
                    <>
                        <div className="sweep-row">
                            <div className="sweep-row-head">
                                <span className="eyebrow">Hold</span>
                                <span>Ambient pressure</span>
                                <input className="input plume-held" aria-label="Ambient pressure held" value={held.value}
                                       onChange={(event) => setHeld({ ...held, value: event.target.value })} />
                                <select className="input input-unit plume-held-unit" aria-label="Ambient pressure unit" value={held.unit}
                                        onChange={(event) => setHeld({ ...held, unit: event.target.value })}>
                                    {pressureUnits.map((unit) => <option key={unit} value={unit}>{unit}</option>)}
                                </select>
                                <span className="muted plume-lip">{exitText}</span>
                            </div>
                        </div>
                        <div className="sweep-row">
                            <div className="sweep-row-head">
                                <span className="eyebrow">Sweep</span>
                                <span>Power level, percent of rated chamber pressure</span>
                            </div>
                            <FieldEntry field={powerField} entry={power} values={values} choices={[]} units={[]}
                                        onChange={(change) => setPower((previous) => ({ ...previous, ...change }))} />
                            {ratios && <span className="sweep-values muted plume-ratios">{ratios}</span>}
                            {limit && <p className="muted plume-reach-note plume-limit-note">{limit}</p>}
                        </div>
                    </>
                )}
                <div className="sweep-row">
                    <div className="sweep-row-head">
                        <span className="eyebrow">Reach</span>
                        <input className="input plume-reach" aria-label="Reach drawn" type="number" min={limits.nearReach}
                               max={limits.maxReach} step={0.5} value={reach} onChange={(event) => setReach(event.target.value)} />
                        <span className="muted">lip radii past the exit plane</span>
                    </div>
                    <p className="muted plume-reach-note">
                        The march conserves mass within its 1 percent bound to about {limits.nearReach} lip radii, and every
                        point is marched that far for its numbers. A longer reach marches again to draw the boundary there; a
                        boundary past the bound draws dashed.
                    </p>
                </div>
                <label className="run-details-field">
                    <span>Name</span>
                    <input className="input" value={name} maxLength={80}
                           placeholder={kind === 'ambient' ? 'the range of its ambients' : 'its power levels and ambient'}
                           onChange={(event) => setName(event.target.value)} />
                </label>
                <div className="sweep-summary">
                    <strong>{count} {plural(count, kind)}</strong>
                    <span className="muted">
                        {kind === 'ambient' ? 'An ambient' : 'A power level'} the march refuses, such as one that separates the
                        nozzle, comes back with its reason.
                    </span>
                </div>
                {problem && <p className="form-note form-note-error" role="alert">{problem}</p>}
                <div className="modal-actions">
                    <button type="button" className="button" onClick={onClose}>Cancel</button>
                    <button type="button" className="button button-primary" disabled={!!problem || sending || lip === null}
                            onClick={send}>
                        {sending ? 'Starting' : `Solve ${count} ${plural(count, kind)}`}
                    </button>
                </div>
            </div>
        </div>
    );
}
