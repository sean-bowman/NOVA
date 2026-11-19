/* ========================================
   CHANGES SINCE A RUN
   The Design form's rows whose value differs from the config a run ran, each as its label and
   the value before and after in words: 'Ambient pressure, 5000 Pa to 2000 Pa'. Numbers show in
   the first of the dimension's units that reads between 0.1 and 10000, so a chamber pressure
   reads in kPa or MPa rather than as seven digits of Pa.
   Sean Bowman [11/19/2026]
   ======================================== */

import { chooseOption, choiceLabel, isChanged, optionValue } from '../design/formModel';
import { asBool, formatNumber, fromSI, type UnitTable } from '../design/units';
import type { Config, ConfigValue, FieldSpec, ItemSpec, Schema } from '../types';

export interface FieldChange {
    id: string;
    label: string;
    before: string;
    after: string;
}

function trimmed(value: number): string {
    return formatNumber(Number(value.toPrecision(5)));
}

function numberText(value: number, dimension: string | null, unit: string, units: UnitTable): string {
    const table = dimension ? units[dimension] : undefined;
    if (dimension && table && table.units.length > 0) {
        const readable = table.units.find((entry) => {
            const shown = Math.abs(fromSI(units, value, dimension, entry.unit));
            return shown === 0 || (shown >= 0.1 && shown < 1e4);
        }) ?? table.units.find((entry) => entry.unit === table.si) ?? table.units[0];
        return `${trimmed(fromSI(units, value, dimension, readable.unit))} ${readable.unit}`;
    }
    return unit ? `${trimmed(value)} ${unit}` : trimmed(value);
}

function fieldText(spec: FieldSpec, value: ConfigValue | undefined, units: UnitTable): string {
    if (value === null || value === undefined || value === '') {
        return 'blank';
    }
    if (spec.kind === 'bool') {
        return asBool(value) ? 'on' : 'off';
    }
    if (spec.choices.length > 0) {
        return choiceLabel(spec, value);
    }
    if (typeof value === 'number') {
        return numberText(value, spec.dimension, spec.unit, units);
    }
    if (Array.isArray(value)) {
        return value.map((entry) => (typeof entry === 'number' ? trimmed(entry) : JSON.stringify(entry))).join(', ');
    }
    if (typeof value === 'object') {
        return JSON.stringify(value);
    }
    return String(value);
}

function itemText(item: ItemSpec, config: Config, units: UnitTable): string {
    if (item.type === 'field') {
        return fieldText(item, config[item.key], units);
    }
    const option = chooseOption(item, config);
    const value = optionValue(option, config);
    if (option.key === null) {
        return option.label;
    }
    if (typeof value === 'number') {
        return `${option.label} ${numberText(value, option.dimension, option.unit, units)}`;
    }
    return value === null ? `${option.label} blank` : `${option.label} ${String(value)}`;
}

/** Every row of the form that differs between a run's config and the form's, in form order. */
export function changesSince(schema: Schema, ran: Config, current: Config): FieldChange[] {
    const changes: FieldChange[] = [];
    for (const group of schema.groups) {
        for (const item of group.items) {
            if ((item.type === 'field' && item.hidden) || !isChanged(item, current, ran)) {
                continue;
            }
            changes.push({
                id: item.id, label: item.type === 'field' ? item.label : item.name,
                before: itemText(item, ran, schema.units), after: itemText(item, current, schema.units),
            });
        }
    }
    return changes;
}
