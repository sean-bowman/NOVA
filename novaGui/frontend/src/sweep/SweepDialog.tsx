/* ========================================
   SWEEP DIALOG
   A trade sweep from the form as it stands: one field varied over a range or a list of values, or
   two fields against each other as a grid, each point one run in the queue. A number field takes a
   range (both ends and a count, evenly spaced) or a list, in a unit picked beside it; a choice or a
   switch takes the options ticked. The second field becomes the lines of the sweep's plot, so it
   takes few values.

   The dialog counts the runs, estimates their time from the latest run's and their size from its
   files, and names the form's cross-field problems, which every point runs with. An entry the form
   cannot parse blocks the sweep, as it blocks Generate.
   Sean Bowman [11/20/2026]
   ======================================== */

import { useEffect, useMemo, useState } from 'react';

import { api } from '../api';
import { CloseIcon } from '../components/Icons';
import { siUnit, unitsFor } from '../design/units';
import { formatSize } from '../export/fileSize';
import { formatClock } from '../run/stageText';
import type { Config, ConfigValue, Mode, Schema, Sweep } from '../types';
import {
    choicesOf, defaultName, isNumeric, startEntry, sweepables, valuesOf, type SweepEntry, type Sweepable, type Values,
} from './sweepModel';

/** The unit a sweep's values are first entered in, where the SI unit makes long numbers. */
const preferredUnits: Record<string, string> = { pressure: 'MPa', length: 'mm', force: 'kN' };

interface SweepDialogProps {
    schema: Schema;
    config: Config;
    hidden: string[];             // the rows and sections the config hides
    problems: string[];           // the form's cross-field problems
    blockReason: string;          // why nothing can run now, '' when a sweep can
    mode: Mode;
    lastRun: { seconds: number; bytes: number } | null;
    limits: { maxPoints: number; maxSeries: number };
    onQueued: (sweep: Sweep) => void;
    onClose: () => void;
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

/** A field's values: a range or a list in a unit for a number, the options ticked for a choice or a switch. */
export function FieldEntry({ field, entry, values, choices, units, onChange }: {
    field: Sweepable;
    entry: SweepEntry;
    values: Values;
    choices: { label: string; value: ConfigValue }[];
    units: string[];
    onChange: (patch: Partial<SweepEntry>) => void;
}) {
    if (!isNumeric(field.spec)) {
        return (
            <div className="sweep-choices" role="group" aria-label={`${field.label} values`}>
                {choices.map((choice) => {
                    const ticked = entry.picked.some((value) => value === choice.value);
                    return (
                        <label key={choice.label} className="check sweep-choice">
                            <input type="checkbox" checked={ticked}
                                   onChange={() => onChange({ picked: ticked
                                       ? entry.picked.filter((value) => value !== choice.value)
                                       : [...entry.picked, choice.value] })} />
                            {choice.label}
                        </label>
                    );
                })}
            </div>
        );
    }
    return (
        <div className="sweep-entry">
            <div className="segmented" role="group" aria-label={`${field.label} entry`}>
                <button type="button" className={entry.how === 'range' ? 'is-selected' : ''} aria-pressed={entry.how === 'range'}
                        onClick={() => onChange({ how: 'range' })}>Range</button>
                <button type="button" className={entry.how === 'list' ? 'is-selected' : ''} aria-pressed={entry.how === 'list'}
                        onClick={() => onChange({ how: 'list' })}>List</button>
            </div>
            {entry.how === 'range' ? (
                <div className="sweep-range">
                    <input className="input" aria-label={`${field.label} from`} value={entry.from}
                           onChange={(event) => onChange({ from: event.target.value })} />
                    <span className="muted">to</span>
                    <input className="input" aria-label={`${field.label} to`} value={entry.to}
                           onChange={(event) => onChange({ to: event.target.value })} />
                    <span className="muted">in</span>
                    <input className="input sweep-count" aria-label={`${field.label} count`} value={entry.count}
                           onChange={(event) => onChange({ count: event.target.value })} />
                    <span className="muted">values</span>
                </div>
            ) : (
                <input className="input sweep-list" aria-label={`${field.label} values`} value={entry.list}
                       placeholder="6, 7, 8, 9" onChange={(event) => onChange({ list: event.target.value })} />
            )}
            {units.length > 0 && (
                <select className="input input-unit" aria-label={`${field.label} unit`} value={entry.unit}
                        onChange={(event) => onChange({ unit: event.target.value })}>
                    {units.map((unit) => <option key={unit} value={unit}>{unit}</option>)}
                </select>
            )}
            {!units.length && field.spec.unit && <span className="unit-static">{field.spec.unit}</span>}
            {values.ok && <span className="sweep-values muted">{values.shown.join(', ')}{entry.unit ? ` ${entry.unit}` : ''}</span>}
        </div>
    );
}

export function SweepDialog({ schema, config, hidden, problems, blockReason, mode, lastRun, limits, onQueued, onClose,
                              onNotify }: SweepDialogProps) {
    const fields = useMemo(() => sweepables(schema, config, new Set(hidden)), [schema, config, hidden]);
    const byKey = useMemo(() => new Map(fields.map((field) => [field.key, field])), [fields]);
    const sections = useMemo(() => [...new Set(fields.map((field) => field.section))], [fields]);

    const entryFor = (key: string, count = 5): SweepEntry => {
        const field = byKey.get(key)!;
        const dimension = field.spec.dimension;
        let unit = '';
        if (dimension) {
            const offered = unitsFor(schema.units, dimension);
            unit = offered.includes(preferredUnits[dimension] ?? '') ? preferredUnits[dimension] : siUnit(schema.units, dimension);
        }
        return startEntry(field, config, unit, schema.units, count);
    };

    const [entries, setEntries] = useState<SweepEntry[]>(() => {
        const first = byKey.has('chamberPressure') ? 'chamberPressure' : fields[0]?.key;
        return first ? [entryFor(first)] : [];
    });
    const [name, setName] = useState('');
    const [sending, setSending] = useState(false);

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

    const patch = (index: number, change: Partial<SweepEntry>) =>
        setEntries((previous) => previous.map((entry, at) => (at === index ? { ...entry, ...change } : entry)));
    const pick = (index: number, key: string) =>
        setEntries((previous) => previous.map((entry, at) => (at === index ? entryFor(key, index === 0 ? 5 : 3) : entry)));

    const shown = entries.filter((entry) => byKey.has(entry.key));
    const results = shown.map((entry) => valuesOf(entry, byKey.get(entry.key)!, schema.units));
    const labels = shown.map((entry) => byKey.get(entry.key)!.label);
    const count = results.reduce((product, result) => product * (result.ok ? result.values.length : 0), 1);

    let problem = blockReason;
    const failed = results.find((result) => !result.ok);
    if (!problem && failed && !failed.ok) {
        problem = failed.message;
    } else if (!problem && shown.length === 2 && shown[0].key === shown[1].key) {
        problem = 'Pick two different fields for a grid.';
    } else if (!problem && shown.length === 2 && results[1].ok && results[1].values.length > limits.maxSeries) {
        problem = `The second field takes at most ${limits.maxSeries} values, one line each on the plot.`;
    } else if (!problem && count > limits.maxPoints) {
        problem = `That makes ${count} runs; a sweep queues at most ${limits.maxPoints}.`;
    }

    const countText = shown.length === 2 && results.every((result) => result.ok)
        ? `${results.map((result) => (result.ok ? result.values.length : 0)).join(' x ')} = ${count} runs`
        : `${count} ${count === 1 ? 'run' : 'runs'}`;
    const estimate = lastRun && count > 0
        ? `about ${formatClock(count * lastRun.seconds)} at ${formatClock(lastRun.seconds)} a run`
          + (lastRun.bytes > 0 ? `, ${formatSize(count * lastRun.bytes)} in the run store` : '')
        : '';

    const send = () => {
        if (problem || sending) {
            return;
        }
        setSending(true);
        api.addSweep({
            name, config, mode,
            fields: shown.map((entry, index) => {
                const result = results[index];
                return { key: entry.key, unit: entry.unit, values: result.ok ? result.values : [] };
            }),
        })
            .then((sweep) => {
                onQueued(sweep);
                onClose();
            })
            .catch((failure: Error) => {
                setSending(false);
                onNotify('error', 'Sweep not queued', failure.message);
            });
    };

    const fieldSelect = (index: number) => (
        <select className="input sweep-field" aria-label={index === 0 ? 'Field to sweep' : 'Second field'}
                value={entries[index].key} onChange={(event) => pick(index, event.target.value)}>
            {sections.map((section) => (
                <optgroup key={section} label={section}>
                    {fields.filter((field) => field.section === section).map((field) => (
                        <option key={field.key} value={field.key}>{field.label}</option>
                    ))}
                </optgroup>
            ))}
        </select>
    );

    return (
        <div className="modal-scrim" onClick={onClose}>
            <div className="card modal sweep-dialog" role="dialog" aria-label="Trade sweep" onClick={(event) => event.stopPropagation()}>
                <div className="run-details-head">
                    <h2>Trade sweep</h2>
                    <span className="toolbar-spacer" />
                    <button type="button" className="icon-button" aria-label="Close" onClick={onClose}>
                        <CloseIcon />
                    </button>
                </div>
                <p className="muted sweep-lead">
                    One run per value, each from the form as it stands with the swept field set. The runs queue
                    behind any run going, and stay in the run store until the sweep is deleted.
                </p>
                {fields.length === 0 ? <p>The form has no field a sweep can vary.</p> : (
                    <>
                        {entries.map((entry, index) => {
                            const field = byKey.get(entry.key);
                            if (!field) {
                                return null;
                            }
                            return (
                                <div key={index} className="sweep-row">
                                    <div className="sweep-row-head">
                                        <span className="eyebrow">{index === 0 ? 'Sweep' : 'Against'}</span>
                                        {fieldSelect(index)}
                                        {index === 1 && (
                                            <button type="button" className="button button-quiet" onClick={() => setEntries((previous) => previous.slice(0, 1))}>
                                                Remove
                                            </button>
                                        )}
                                    </div>
                                    <FieldEntry field={field} entry={entry} values={results[index]}
                                                choices={choicesOf(field.spec, config[field.key] ?? null)}
                                                units={field.spec.dimension ? unitsFor(schema.units, field.spec.dimension) : []}
                                                onChange={(change) => patch(index, change)} />
                                </div>
                            );
                        })}
                        {entries.length === 1 && (
                            <button type="button" className="button sweep-add"
                                    onClick={() => {
                                        const other = fields.find((field) => field.key !== entries[0].key && field.key === 'OFRatio')
                                            ?? fields.find((field) => field.key !== entries[0].key);
                                        if (other) {
                                            setEntries((previous) => [...previous, entryFor(other.key, 3)]);
                                        }
                                    }}
                                    title="A grid: every value of the first field against each of the second, one line each on the plot">
                                Against a second field
                            </button>
                        )}
                        <label className="run-details-field">
                            <span>Name</span>
                            <input className="input" value={name} maxLength={80} placeholder={defaultName(labels)}
                                   onChange={(event) => setName(event.target.value)} />
                        </label>
                        <div className="sweep-summary">
                            <strong>{countText}</strong>
                            {estimate && <span className="muted">{estimate}</span>}
                        </div>
                        {problems.length > 0 && (
                            <div className="result-status is-caution sweep-problems" role="status">
                                <span>Every point runs with the form's issues: {problems.join(' ')}</span>
                            </div>
                        )}
                    </>
                )}
                {problem && fields.length > 0 && <p className="form-note form-note-error" role="alert">{problem}</p>}
                <div className="modal-actions">
                    <button type="button" className="button" onClick={onClose}>Cancel</button>
                    <button type="button" className="button button-primary" disabled={!!problem || sending || fields.length === 0}
                            onClick={send}>
                        {sending ? 'Queueing' : `Queue ${count} ${count === 1 ? 'run' : 'runs'}`}
                    </button>
                </div>
            </div>
        </div>
    );
}
