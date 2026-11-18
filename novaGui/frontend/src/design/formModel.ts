/* ========================================
   DESIGN FORM MODEL
   Pure helpers over the schema and a config: how a section lays out its rows and folds,
   which option a selector row shows, and how a text entry becomes a config value.
   Sean Bowman [11/16/2026]
   ======================================== */

import type { Config, ConfigValue, FieldSpec, GroupSpec, ItemSpec, OptionSpec, SelectorSpec } from '../types';
import { asBool, formatNumber, fromSI, sameValue, toSI, type UnitTable } from './units';

/** A section's contents in form order: single rows, and folds placed where their first row falls. */
export type Block =
    | { kind: 'item'; item: ItemSpec }
    | { kind: 'fold'; name: string; items: ItemSpec[] };

export function blocksOf(group: GroupSpec): Block[] {
    const blocks: Block[] = [];
    const folds = new Map<string, ItemSpec[]>();
    for (const item of group.items) {
        // A hidden field has no row; its value passes through the config untouched
        if (item.type === 'field' && item.hidden) {
            continue;
        }
        if (!item.fold) {
            blocks.push({ kind: 'item', item });
            continue;
        }
        let members = folds.get(item.fold);
        if (!members) {
            members = [];
            folds.set(item.fold, members);
            blocks.push({ kind: 'fold', name: item.fold, items: members });
        }
        members.push(item);
    }
    return blocks;
}

/** Every config key a row writes. */
export function keysOf(item: ItemSpec): string[] {
    return item.type === 'selector' ? item.members.map((member) => member.key) : [item.key];
}

/** Whether a row's value differs from the shipped default. */
export function isChanged(item: ItemSpec, config: Config, defaults: Config): boolean {
    return keysOf(item).some((key) => !sameValue(config[key], defaults[key]));
}

/** Whether a row matches a search: its label, key, help or option labels. */
export function matchesSearch(item: ItemSpec, query: string): boolean {
    if (!query) {
        return true;
    }
    const text = item.type === 'selector'
        ? [item.name, item.help, ...item.options.map((option) => option.label), ...item.members.map((member) => member.key)]
        : [item.label, item.key, item.help, ...item.choices.map((choice) => choice.label)];
    return text.join(' ').toLowerCase().includes(query);
}

// -- Selectors -- //

function optionMatches(option: OptionSpec, config: Config): boolean {
    return Object.entries(option.sets).every(([key, value]) => sameValue(config[key], value));
}

/**
 * The option a config describes: the first whose constants it matches and whose value it
 * sets, then the first whose constants it matches, then the row's blank option. The same
 * rule as legacy.novaTk.widgets.SelectorRow.set.
 */
export function chooseOption(selector: SelectorSpec, config: Config): OptionSpec {
    const options = selector.options;
    const withValue = options.find((option) =>
        optionMatches(option, config) && (option.key === null || (config[option.key] ?? null) !== null));
    if (withValue) {
        return withValue;
    }
    const byMode = options.find((option) => Object.keys(option.sets).length > 0 && optionMatches(option, config));
    if (byMode) {
        return byMode;
    }
    return options.find((option) => option.label === selector.blank) ?? options[0];
}

/** The value a config holds for an option, or null where the option is not the one it describes. */
export function optionValue(option: OptionSpec, config: Config): ConfigValue {
    if (option.key === null || !optionMatches(option, config)) {
        return null;
    }
    return config[option.key] ?? null;
}

/** Every key a selector row writes for a choice: the option's value, its constants, null for the rest. */
export function selectorPatch(selector: SelectorSpec, option: OptionSpec, value: ConfigValue): Config {
    const patch: Config = {};
    for (const member of selector.members) {
        patch[member.key] = null;
    }
    Object.assign(patch, option.sets);
    if (option.key !== null) {
        patch[option.key] = value;
    }
    return patch;
}

export function memberOf(selector: SelectorSpec, key: string): FieldSpec | undefined {
    return selector.members.find((member) => member.key === key);
}

// -- Entry text -- //

/** Keys whose value is a list of numbers entered as comma-separated text. */
const numberListKeys = new Set(['divergingSectionDesignVariables']);

/** A config value as the text its entry shows, in the unit the row displays. */
export function valueToText(spec: FieldSpec, value: ConfigValue, units: UnitTable, unit: string | null): string {
    if (value === null || value === undefined) {
        return '';
    }
    if (typeof value === 'number') {
        if (spec.dimension && unit) {
            return formatNumber(fromSI(units, value, spec.dimension, unit));
        }
        return formatNumber(value);
    }
    if (Array.isArray(value) && numberListKeys.has(spec.key)) {
        return value.map((number) => formatNumber(Number(number))).join(', ');
    }
    if (typeof value === 'object') {
        // A structured value, the film slots, round-trips as JSON text
        return JSON.stringify(value);
    }
    return String(value);
}

export type Parsed = { ok: true; value: ConfigValue } | { ok: false; message: string };

/**
 * An entry's text as a config value in SI, following legacy.novaTk.widgets.FieldRow.get: blank is
 * null, int and float must parse, floatText falls back to text, and a dimensioned value is
 * converted from the unit shown.
 */
export function textToValue(spec: FieldSpec, raw: string, units: UnitTable, unit: string | null, label?: string): Parsed {
    const text = raw.trim();
    const name = label ?? spec.label;
    if (text === '') {
        return { ok: true, value: null };
    }
    const convert = (number: number) => (spec.dimension && unit ? toSI(units, number, spec.dimension, unit) : number);

    switch (spec.kind) {
        case 'int': {
            const number = Number(text);
            if (!Number.isFinite(number)) {
                return { ok: false, message: `${name}: '${text}' is not an integer` };
            }
            return { ok: true, value: Math.round(convert(Math.trunc(number))) };
        }
        case 'float': {
            const number = Number(text);
            if (!Number.isFinite(number)) {
                return { ok: false, message: `${name}: '${text}' is not a number` };
            }
            return { ok: true, value: convert(number) };
        }
        case 'floatText': {
            const number = Number(text);
            return { ok: true, value: Number.isFinite(number) ? convert(number) : text };
        }
        default:
            break;
    }

    if (numberListKeys.has(spec.key)) {
        const parts = text.replace(/^\[|\]$/g, '').split(',').map((part) => part.trim()).filter(Boolean);
        const numbers = parts.map(Number);
        if (numbers.some((number) => !Number.isFinite(number))) {
            return { ok: false, message: `${name}: '${text}' is not a list of numbers` };
        }
        return { ok: true, value: numbers };
    }
    if (text.startsWith('[') || text.startsWith('{')) {
        try {
            return { ok: true, value: JSON.parse(text) as ConfigValue };
        } catch {
            return { ok: false, message: `${name}: '${text}' is not valid JSON` };
        }
    }
    return { ok: true, value: text };
}

/** A choice field's display label for a backend value; an off-list value shows verbatim. */
export function choiceLabel(spec: FieldSpec, value: ConfigValue): string {
    const found = spec.choices.find((choice) => sameValue(choice.value, value));
    if (found) {
        return found.label;
    }
    return value === null || value === undefined ? '' : String(value);
}

/** A choice field's backend value for a label; an unrecognized label passes through as typed. */
export function choiceValue(spec: FieldSpec, label: string): ConfigValue {
    const found = spec.choices.find((choice) => choice.label === label);
    if (found) {
        return found.value;
    }
    return label === '' ? null : label;
}

export { asBool };
