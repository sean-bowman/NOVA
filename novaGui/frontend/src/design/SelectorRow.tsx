/* ========================================
   SELECTOR ROW
   One row for several alternative config keys (thrust or mass flow, area ratio or exit
   pressure): an option dropdown in the label column, the value, and its unit. Each option
   keeps its own text and unit while another is chosen. Choosing an option writes its value,
   the constants it fixes, and null to every other key the row holds, as
   legacy.novaTk.widgets.SelectorRow does. An option in amber is one a cross-field problem names.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useEffect, useState } from 'react';

import { HelpMarker } from '../components/Tooltip';
import type { Config, OptionSpec, SelectorSpec } from '../types';
import { chooseOption, memberOf, optionValue, selectorPatch } from './formModel';
import { formatNumber, fromSI, siUnit, toSI, unitsFor, type UnitTable } from './units';

interface SelectorRowProps {
    selector: SelectorSpec;
    config: Config;
    units: UnitTable;
    visible: boolean;
    changed: boolean;
    error: string | null;
    flagged?: boolean;
    onChange: (patch: Config) => void;
    onError: (id: string, message: string | null) => void;
}

type Parsed = { ok: true; value: number | null } | { ok: false; message: string };

export function SelectorRow({ selector, config, units, visible, changed, error, flagged = false, onChange,
                              onError }: SelectorRowProps) {
    const [chosen, setChosen] = useState(() => chooseOption(selector, config).label);
    const [optionUnits, setOptionUnits] = useState<Record<string, string | null>>(() => Object.fromEntries(
        selector.options.map((option) => [option.label, option.dimension ? siUnit(units, option.dimension) : null])));
    const [texts, setTexts] = useState<Record<string, string>>(() => Object.fromEntries(selector.options.map((option) => {
        const value = optionValue(option, config);
        if (typeof value !== 'number') {
            return [option.label, value === null ? '' : String(value)];
        }
        return [option.label, formatNumber(value)];
    })));

    const option = selector.options.find((candidate) => candidate.label === chosen) ?? selector.options[0];
    const unit = optionUnits[option.label];

    const parse = (target: OptionSpec, raw: string, targetUnit: string | null): Parsed => {
        const text = raw.trim();
        if (target.key === null || text === '') {
            return { ok: true, value: null };
        }
        const number = Number(text);
        if (!Number.isFinite(number)) {
            return { ok: false, message: `${target.label}: '${text}' is not a number` };
        }
        let value = target.dimension && targetUnit ? toSI(units, number, target.dimension, targetUnit) : number;
        if (memberOf(selector, target.key)?.kind === 'int') {
            value = Math.round(value);
        }
        return { ok: true, value };
    };

    const emit = (target: OptionSpec, raw: string, targetUnit: string | null) => {
        const parsed = parse(target, raw, targetUnit);
        if (parsed.ok) {
            onChange(selectorPatch(selector, target, parsed.value));
        }
    };

    // Report what blocks a run: an entry that is not a number, or a required option left blank
    useEffect(() => {
        const parsed = parse(option, texts[option.label] ?? '', unit);
        let message: string | null = null;
        if (!parsed.ok) {
            message = parsed.message;
        } else if (visible && selector.required && option.key !== null && parsed.value === null) {
            message = `'${option.label}' needs a value.`;
        }
        onError(selector.id, message);
    }, [option, texts, unit, visible, selector, onError]);

    const choose = (label: string) => {
        const next = selector.options.find((candidate) => candidate.label === label);
        if (!next) {
            return;
        }
        setChosen(label);
        emit(next, texts[label] ?? '', optionUnits[label]);
    };

    const type = (raw: string) => {
        setTexts((previous) => ({ ...previous, [option.label]: raw }));
        emit(option, raw, unit);
    };

    const changeUnit = (next: string) => {
        // The quantity is kept: convert the shown number into the new unit
        const raw = (texts[option.label] ?? '').trim();
        const number = Number(raw);
        if (raw !== '' && Number.isFinite(number) && option.dimension && unit) {
            const si = toSI(units, number, option.dimension, unit);
            setTexts((previous) => ({ ...previous, [option.label]: formatNumber(fromSI(units, si, option.dimension!, next)) }));
        }
        setOptionUnits((previous) => ({ ...previous, [option.label]: next }));
    };

    const memberHelp = option.key ? memberOf(selector, option.key)?.help : '';
    const help = [selector.help, memberHelp ? `${option.label}: ${memberHelp}` : ''].filter(Boolean).join('\n\n');

    return (
        <div className="form-row" hidden={!visible}>
            <div className="form-label form-label-selector">
                <select className={`input input-selector ${error ? 'input-error' : (flagged ? 'input-warn' : '')}`} value={chosen}
                        aria-label={selector.name} onChange={(event) => choose(event.target.value)}>
                    {selector.options.map((candidate) => <option key={candidate.label}>{candidate.label}</option>)}
                </select>
                <HelpMarker text={help} />
                {changed && <span className="changed-dot changed-dot-static" title="Changed from the shipped nozzle" />}
            </div>
            <div className="form-editor">
                <input className={`input ${error ? 'input-error' : ''}`} value={texts[option.label] ?? ''} spellCheck={false}
                       inputMode="decimal" disabled={option.key === null} aria-label={option.label}
                       onChange={(event) => type(event.target.value)} />
            </div>
            <div className="form-unit">
                {option.dimension && unit && (
                    <select className="input input-unit" value={unit} aria-label={`${option.label} unit`}
                            onChange={(event) => changeUnit(event.target.value)}>
                        {unitsFor(units, option.dimension).map((candidate) => <option key={candidate}>{candidate}</option>)}
                    </select>
                )}
                {!option.dimension && option.unit && <span className="unit-static">{option.unit}</span>}
            </div>
            {error && <div className="form-note form-note-error">{error}</div>}
        </div>
    );
}
