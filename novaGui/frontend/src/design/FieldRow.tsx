/* ========================================
   FIELD ROW
   One config key on the Design form: the label with its help and changed marker, an editor
   chosen by the field's kind, and a unit dropdown for a dimensioned value. The config holds
   SI; the row shows the unit its dropdown names and converts in place when that changes. A
   label in amber is one a cross-field problem names, and the problem is written under the row.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useEffect, useId, useRef, useState } from 'react';

import { HelpMarker } from '../components/Tooltip';
import type { Config, ConfigValue, FieldSpec } from '../types';
import { asBool, choiceLabel, choiceValue, textToValue, valueToText } from './formModel';
import { sameValue, siUnit, unitsFor, type UnitTable } from './units';

interface FieldRowProps {
    spec: FieldSpec;
    value: ConfigValue;
    defaultValue: ConfigValue;
    units: UnitTable;
    visible: boolean;
    changed: boolean;
    error: string | null;
    flagged?: boolean;
    notes?: string[];
    onChange: (patch: Config) => void;
    onError: (id: string, message: string | null) => void;
    /** Called when the user picks from a fixed choice list, and not when the value changes otherwise */
    onChoose?: (value: ConfigValue) => void;
}

export function FieldRow({ spec, value, defaultValue, units, visible, changed, error, flagged = false, notes = [], onChange,
                           onError, onChoose }: FieldRowProps) {
    const inputId = useId();
    const focused = useRef(false);
    const [unit, setUnit] = useState<string | null>(spec.dimension ? siUnit(units, spec.dimension) : null);
    const [text, setText] = useState(() => valueToText(spec, value, units, unit));

    // Follow the config while the user is not typing: a loaded file, a reset, a unit change. An
    // entry that does not read keeps its text until it is fixed or restored, so the problem written
    // under the row stays the problem with what the row shows.
    useEffect(() => {
        if (!focused.current && !error) {
            setText(valueToText(spec, value, units, unit));
        }
    }, [spec, value, units, unit, error]);

    const commit = (raw: string) => {
        setText(raw);
        const parsed = textToValue(spec, raw, units, unit);
        if (!parsed.ok) {
            onError(spec.id, parsed.message);
            return;
        }
        onError(spec.id, null);
        if (!sameValue(parsed.value, value)) {
            onChange({ [spec.key]: parsed.value });
        }
    };

    const changeUnit = (next: string) => {
        setUnit(next);
        // The quantity is kept: the text is the config's SI value in the new unit
        if (!error) {
            setText(valueToText(spec, value, units, next));
        }
    };

    let editor;
    if (spec.kind === 'bool') {
        editor = (
            <label className="switch">
                <input id={inputId} type="checkbox" checked={asBool(value)}
                       onChange={(event) => onChange({ [spec.key]: event.target.checked })} />
                <span className="switch-track" aria-hidden="true" />
            </label>
        );
    } else if (spec.kind === 'choice' && !spec.editable) {
        const shown = choiceLabel(spec, value);
        const offList = shown !== '' && !spec.choices.some((choice) => choice.label === shown);
        editor = (
            <select id={inputId} className="input" value={shown}
                    onChange={(event) => {
                        const chosen = choiceValue(spec, event.target.value);
                        onChange({ [spec.key]: chosen });
                        onChoose?.(chosen);
                    }}>
                {value === null && <option value="" />}
                {offList && <option value={shown}>{shown}</option>}
                {spec.choices.map((choice) => <option key={choice.label} value={choice.label}>{choice.label}</option>)}
            </select>
        );
    } else if (spec.kind === 'choice') {
        // Editable: the list offers the known values and the entry takes anything typed
        const listId = `${inputId}-list`;
        editor = (
            <>
                <input id={inputId} className="input" list={listId} value={focused.current ? text : choiceLabel(spec, value)}
                       onFocus={(event) => { focused.current = true; setText(event.target.value); }}
                       onBlur={() => { focused.current = false; }}
                       onChange={(event) => { setText(event.target.value); onChange({ [spec.key]: choiceValue(spec, event.target.value) }); }} />
                <datalist id={listId}>
                    {spec.choices.map((choice) => <option key={choice.label} value={choice.label} />)}
                </datalist>
            </>
        );
    } else {
        const numeric = spec.kind === 'int' || spec.kind === 'float';
        editor = (
            <input id={inputId} className={`input ${error ? 'input-error' : ''}`} value={text} spellCheck={false}
                   inputMode={numeric ? 'decimal' : 'text'}
                   onFocus={() => { focused.current = true; }}
                   onBlur={() => {
                       focused.current = false;
                       if (!error) {
                           setText(valueToText(spec, value, units, unit));
                       }
                   }}
                   onChange={(event) => commit(event.target.value)} />
        );
    }

    const note = spec.kind === 'choice' ? spec.optionHelp[String(value)] : undefined;

    return (
        <div className="form-row" hidden={!visible}>
            <div className="form-label">
                <label htmlFor={inputId} className={error ? 'label-error' : (flagged ? 'label-warn' : undefined)}>{spec.label}</label>
                <HelpMarker text={spec.help} />
                {changed && (
                    <button type="button" className="changed-dot" aria-label={`Restore ${spec.label} to the shipped value`}
                            title="Changed from the shipped nozzle. Click to restore."
                            onClick={() => { onError(spec.id, null); onChange({ [spec.key]: defaultValue }); }} />
                )}
            </div>
            <div className="form-editor">{editor}</div>
            <div className="form-unit">
                {spec.dimension && unit && (
                    <select className="input input-unit" value={unit} aria-label={`${spec.label} unit`}
                            onChange={(event) => changeUnit(event.target.value)}>
                        {unitsFor(units, spec.dimension).map((candidate) => <option key={candidate}>{candidate}</option>)}
                    </select>
                )}
                {!spec.dimension && spec.unit && <span className="unit-static">{spec.unit}</span>}
            </div>
            {error && <div className="form-note form-note-error">{error}</div>}
            {!error && notes.map((problem) => <div key={problem} className="form-note form-note-warn" role="note">{problem}</div>)}
            {note && <div className="form-note">{note}</div>}
        </div>
    );
}
