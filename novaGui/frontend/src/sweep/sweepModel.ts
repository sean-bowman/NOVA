/* ========================================
   SWEEP MODEL
   Pure helpers for the sweep dialog: the fields a sweep can vary on the form as it stands, and the
   values an entry gives, from a range and a count, a list, or the choices ticked. Numbers are
   entered in a display unit and sent in backend values (SI), the same conversion the form's rows
   use (units.ts).
   Sean Bowman [11/20/2026]
   ======================================== */

import { chooseOption, memberOf } from '../design/formModel';
import { formatNumber, fromSI, sameValue, toSI, type UnitTable } from '../design/units';
import type { Config, ConfigValue, FieldSpec, Schema } from '../types';

/** A field the dialog offers: its spec, the label it goes by, and the form section it sits in. */
export interface Sweepable {
    key: string;
    label: string;
    section: string;
    spec: FieldSpec;
}

/** How one field's values are entered. */
export interface SweepEntry {
    key: string;
    how: 'range' | 'list';
    from: string;
    to: string;
    count: string;
    list: string;
    unit: string;                 // the display unit, '' for a field without one
    picked: ConfigValue[];        // a choice or switch field's values
}

/** An entry's values in backend values, their text with the unit, and the numbers alone as entered. */
export type Values = { ok: true; values: ConfigValue[]; texts: string[]; shown: string[] } | { ok: false; message: string };

const numericKinds = new Set(['float', 'int', 'floatText']);

export function isNumeric(spec: FieldSpec): boolean {
    return numericKinds.has(spec.kind);
}

/**
 * Every field a sweep can vary on the form as the config stands: a number, a choice or a switch
 * with a row the config shows. A selector row offers the quantity its chosen option sets, and a
 * floatText field only while it holds a number. novaGui.sweeps.sweepableFields checks the same on
 * the server.
 */
export function sweepables(schema: Schema, config: Config, hidden: Set<string>): Sweepable[] {
    const found: Sweepable[] = [];
    for (const group of schema.groups) {
        if (hidden.has(group.id)) {
            continue;
        }
        for (const item of group.items) {
            if (hidden.has(item.id)) {
                continue;
            }
            if (item.type === 'selector') {
                const option = chooseOption(item, config);
                const member = option.key ? memberOf(item, option.key) : undefined;
                if (member && isNumeric(member)) {
                    found.push({ key: member.key, label: option.label, section: group.title, spec: member });
                }
                continue;
            }
            if (item.hidden || item.synthetic) {
                continue;
            }
            const usable = item.kind === 'choice' || item.kind === 'bool' || item.kind === 'float' || item.kind === 'int'
                || (item.kind === 'floatText' && typeof config[item.key] === 'number');
            if (usable) {
                found.push({ key: item.key, label: item.label, section: group.title, spec: item });
            }
        }
    }
    return found;
}

/** A field's choices for the dialog's ticks: its list, with the config's own value when it is off the list. */
export function choicesOf(spec: FieldSpec, current: ConfigValue): { label: string; value: ConfigValue }[] {
    if (spec.kind === 'bool') {
        return [{ label: 'on', value: true }, { label: 'off', value: false }];
    }
    const listed = spec.choices.map((choice) => ({ label: choice.label, value: choice.value }));
    if (current !== null && current !== undefined && !listed.some((choice) => sameValue(choice.value, current))) {
        listed.push({ label: String(current), value: current });
    }
    return listed;
}

/** A round step near a tenth of a value: 1, 2, 2.5 or 5 times a power of ten. */
function roundStep(value: number): number {
    const size = Math.abs(value) / 10;
    if (size === 0) {
        return 1;
    }
    const power = 10 ** Math.floor(Math.log10(size));
    const scaled = size / power;
    const pick = [1, 2, 2.5, 5, 10].reduce((best, candidate) =>
        (Math.abs(Math.log(candidate / scaled)) < Math.abs(Math.log(best / scaled)) ? candidate : best));
    return pick * power;
}

/**
 * A first entry for a field: `count` round values centred on the config's value, a round step
 * apart, or its choices with the config's ticked.
 */
export function startEntry(field: Sweepable, config: Config, unit: string, units: UnitTable, count = 5): SweepEntry {
    const entry: SweepEntry = { key: field.key, how: 'range', from: '', to: '', count: String(count), list: '', unit, picked: [] };
    const value = config[field.key];
    if (isNumeric(field.spec)) {
        if (typeof value === 'number' && Number.isFinite(value)) {
            const shown = field.spec.dimension && unit ? fromSI(units, value, field.spec.dimension, unit) : value;
            const step = field.spec.kind === 'int' ? Math.max(1, Math.round(roundStep(shown))) : roundStep(shown);
            const centre = Math.round(shown / step) * step;
            const half = Math.floor((count - 1) / 2);
            entry.from = formatNumber(Number((centre - half * step).toPrecision(10)));
            entry.to = formatNumber(Number((centre + (count - 1 - half) * step).toPrecision(10)));
            entry.list = formatNumber(shown);
        }
        return entry;
    }
    entry.picked = field.spec.kind === 'bool' ? [true, false] : (value === null || value === undefined ? [] : [value]);
    return entry;
}

function parseNumber(text: string): number | null {
    const trimmed = text.trim();
    if (trimmed === '') {
        return null;
    }
    const number = Number(trimmed);
    return Number.isFinite(number) ? number : null;
}

/**
 * The values an entry gives, in backend values, with their text as entered. A range spaces its
 * count of values evenly from one end to the other; a list takes numbers separated by commas,
 * semicolons or spaces. An integer field rounds each value.
 */
export function valuesOf(entry: SweepEntry, field: Sweepable, units: UnitTable): Values {
    const spec = field.spec;
    if (!isNumeric(spec)) {
        const choices = choicesOf(spec, null);
        const picked = entry.picked;
        if (picked.length < 2) {
            return { ok: false, message: `${field.label}: tick at least two` };
        }
        const texts = picked.map((value) => choices.find((choice) => sameValue(choice.value, value))?.label ?? String(value));
        return { ok: true, values: picked, texts, shown: texts };
    }

    let shown: number[];
    if (entry.how === 'range') {
        const from = parseNumber(entry.from);
        const to = parseNumber(entry.to);
        const count = parseNumber(entry.count);
        if (from === null || to === null) {
            return { ok: false, message: `${field.label}: give both ends of the range as numbers` };
        }
        if (count === null || !Number.isInteger(count) || count < 2) {
            return { ok: false, message: `${field.label}: the count is a whole number of 2 or more` };
        }
        shown = Array.from({ length: count }, (_, index) => from + ((to - from) * index) / (count - 1));
    } else {
        const parts = entry.list.split(/[\s,;]+/).filter(Boolean);
        const numbers = parts.map(parseNumber);
        const bad = parts.find((_, index) => numbers[index] === null);
        if (bad !== undefined) {
            return { ok: false, message: `${field.label}: '${bad}' is not a number` };
        }
        shown = numbers as number[];
        if (shown.length < 2) {
            return { ok: false, message: `${field.label}: give at least two values` };
        }
    }
    shown = shown.map((value) => (spec.kind === 'int' ? Math.round(value) : Number(value.toPrecision(10))));
    if (shown.some((value, index) => shown.indexOf(value) !== index)) {
        return { ok: false, message: `${field.label}: a value comes twice` };
    }
    const values = shown.map((value) => {
        const si = spec.dimension && entry.unit ? toSI(units, value, spec.dimension, entry.unit) : value;
        return spec.kind === 'int' ? Math.round(si) : si;
    });
    const unit = entry.unit ? ` ${entry.unit}` : '';
    return { ok: true, values, texts: shown.map((value) => `${formatNumber(value)}${unit}`), shown: shown.map(formatNumber) };
}

/** A sweep's name when it is given none, as novaGui.sweeps.defaultName writes it. */
export function defaultName(labels: string[]): string {
    return labels.length === 1 ? `${labels[0]} sweep` : `${labels[0]} by ${labels[1]}`;
}
