/* ========================================
   PLUME SWEEP DIALOG
   A run's plume over a list of ambient pressures, solved on the run's own nozzle without running
   it again (novaGui.plumeSweeps): a range or a list of ambients in a pressure unit, the reach the
   boundaries are drawn to, and a name. Beside the ambients the dialog gives each one's lip
   pressure ratio, the run's lip static pressure over the ambient, which sets how the plume turns
   at the lip.

   The march decides which ambients it solves: one that separates the nozzle, or compresses the lip
   past a weak oblique shock, comes back refused with the march's reason.
   Sean Bowman [11/22/2026]
   ======================================== */

import { useEffect, useMemo, useState } from 'react';

import { api } from '../api';
import { CloseIcon } from '../components/Icons';
import { formatNumber, fromSI, unitsFor, type UnitTable } from '../design/units';
import { FieldEntry } from '../sweep/SweepDialog';
import { valuesOf, type SweepEntry, type Sweepable } from '../sweep/sweepModel';
import type { FieldSpec, PlumeSweep } from '../types';

const ambientField: Sweepable = {
    key: 'ambient', label: 'Ambient pressure', section: '',
    spec: { key: 'ambient', label: 'Ambient pressure', kind: 'float', dimension: 'pressure', unit: 'Pa', choices: [] } as unknown as FieldSpec,
};
const firstRatios = [2.0, 0.75];       // [-] the lip pressure ratios a first range spans, low ambient to high

interface PlumeSweepDialogProps {
    runId: number;
    units: UnitTable;
    limits: { maxPoints: number; nearReach: number; maxReach: number };
    onAdded: (sweep: PlumeSweep) => void;
    onClose: () => void;
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

/** A round number near `value`, two significant figures. */
function rounded(value: number): string {
    return formatNumber(Number(value.toPrecision(2)));
}

export function PlumeSweepDialog({ runId, units, limits, onAdded, onClose, onNotify }: PlumeSweepDialogProps) {
    const [lip, setLip] = useState<{ pressure: number | null; reason: string } | null>(null);
    const [entry, setEntry] = useState<SweepEntry>({ key: 'ambient', how: 'range', from: '', to: '', count: '6', list: '',
                                                     unit: 'kPa', picked: [] });
    const [reach, setReach] = useState(String(limits.nearReach));
    const [name, setName] = useState('');
    const [sending, setSending] = useState(false);

    // The lip pressure, and a first range across the lip ratios the march usually holds over
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
            })
            .catch((failure: Error) => !cancelled && setLip({ pressure: null, reason: failure.message }));
        return () => {
            cancelled = true;
        };
    }, [runId, units]);

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

    const values = useMemo(() => valuesOf(entry, ambientField, units), [entry, units]);
    const reachValue = Number(reach);
    const ratios = values.ok && lip?.pressure ? values.values.map((ambient) => (lip.pressure as number) / (ambient as number)) : [];

    let problem = '';
    if (lip && lip.pressure === null) {
        problem = `This run's plume cannot be swept: ${lip.reason}.`;
    } else if (!values.ok) {
        problem = values.message;
    } else if (values.values.some((value) => (value as number) <= 0)) {
        problem = 'Each ambient pressure is above zero.';
    } else if (values.values.length > limits.maxPoints) {
        problem = `That is ${values.values.length} ambients; a plume sweep solves at most ${limits.maxPoints}.`;
    } else if (!Number.isFinite(reachValue) || reachValue < limits.nearReach || reachValue > limits.maxReach) {
        problem = `The reach is ${limits.nearReach} to ${limits.maxReach} lip radii.`;
    }
    const count = values.ok ? values.values.length : 0;

    const send = () => {
        if (problem || sending || !values.ok) {
            return;
        }
        setSending(true);
        api.addPlumeSweep(runId, { name, ambients: values.values as number[], unit: entry.unit, reach: reachValue })
            .then((sweep) => {
                onAdded(sweep);
                onClose();
            })
            .catch((failure: Error) => {
                setSending(false);
                onNotify('error', 'Plume sweep not started', failure.message);
            });
    };

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
                <p className="muted sweep-lead">
                    The run's plume and delivered performance at each ambient, solved on its nozzle without running it
                    again: the contour and the cooling do not depend on the ambient. The sweep is kept with the run.
                </p>
                <div className="sweep-row">
                    <div className="sweep-row-head">
                        <span className="eyebrow">Sweep</span>
                        <span>Ambient pressure</span>
                        <span className="muted plume-lip">
                            {lip === null ? 'reading the lip' : lip.pressure !== null
                                ? `lip static pressure ${formatNumber(Number(fromSI(units, lip.pressure, 'pressure', entry.unit || 'kPa').toPrecision(4)))} ${entry.unit || 'kPa'}`
                                : ''}
                        </span>
                    </div>
                    <FieldEntry field={ambientField} entry={entry} values={values} choices={[]} units={unitsFor(units, 'pressure')}
                                onChange={(change) => setEntry((previous) => ({ ...previous, ...change }))} />
                    {ratios.length > 0 && (
                        <span className="sweep-values muted plume-ratios">
                            lip pressure ratio {ratios.map((ratio) => ratio.toFixed(2)).join(', ')}
                        </span>
                    )}
                </div>
                <div className="sweep-row">
                    <div className="sweep-row-head">
                        <span className="eyebrow">Reach</span>
                        <input className="input plume-reach" aria-label="Reach drawn" type="number" min={limits.nearReach}
                               max={limits.maxReach} step={0.5} value={reach} onChange={(event) => setReach(event.target.value)} />
                        <span className="muted">lip radii past the exit plane</span>
                    </div>
                    <p className="muted plume-reach-note">
                        The march conserves mass within its 1 per cent bound to about {limits.nearReach} lip radii, and every
                        ambient is marched that far for its numbers. A longer reach marches again to draw the boundary there; a
                        boundary past the bound draws dashed.
                    </p>
                </div>
                <label className="run-details-field">
                    <span>Name</span>
                    <input className="input" value={name} maxLength={80} placeholder="the range of its ambients"
                           onChange={(event) => setName(event.target.value)} />
                </label>
                <div className="sweep-summary">
                    <strong>{count} {count === 1 ? 'ambient' : 'ambients'}</strong>
                    <span className="muted">An ambient the march refuses, such as one that separates the nozzle, comes back with its reason.</span>
                </div>
                {problem && <p className="form-note form-note-error" role="alert">{problem}</p>}
                <div className="modal-actions">
                    <button type="button" className="button" onClick={onClose}>Cancel</button>
                    <button type="button" className="button button-primary" disabled={!!problem || sending || lip === null}
                            onClick={send}>
                        {sending ? 'Starting' : `Solve ${count} ${count === 1 ? 'ambient' : 'ambients'}`}
                    </button>
                </div>
            </div>
        </div>
    );
}
