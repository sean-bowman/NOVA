/* ========================================
   DISPLAY UNITS
   Conversion between a field's SI value and the unit its dropdown shows. The factors come
   from the server's unit table, which reads NOVA's own registry: si = scale * shown + offset.
   Sean Bowman [11/16/2026]
   ======================================== */

import type { ConfigValue, Schema } from '../types';

export type UnitTable = Schema['units'];

function entry(table: UnitTable, dimension: string, unit: string) {
    const found = table[dimension]?.units.find((candidate) => candidate.unit === unit);
    if (!found) {
        throw new Error(`no unit ${unit} for ${dimension}`);
    }
    return found;
}

export function siUnit(table: UnitTable, dimension: string): string {
    return table[dimension].si;
}

export function unitsFor(table: UnitTable, dimension: string): string[] {
    return table[dimension]?.units.map((candidate) => candidate.unit) ?? [];
}

export function toSI(table: UnitTable, value: number, dimension: string, unit: string): number {
    const { scale, offset } = entry(table, dimension, unit);
    return scale * value + offset;
}

export function fromSI(table: UnitTable, value: number, dimension: string, unit: string): number {
    const { scale, offset } = entry(table, dimension, unit);
    return (value - offset) / scale;
}

/**
 * Compact text for a number: an integer when it is one, otherwise up to ten significant
 * figures. The same rule as legacy.novaTk.widgets.FieldRow._formatNumber.
 */
export function formatNumber(value: number | null | undefined): string {
    if (value === null || value === undefined || Number.isNaN(value)) {
        return '';
    }
    if (Math.abs(value - Math.round(value)) < 1e-9 * Math.max(1, Math.abs(value))) {
        return String(Math.round(value));
    }
    return String(Number(value.toPrecision(10)));
}

/**
 * Whether two config values are the same setting. Numbers compare to a relative 1e-9, so a
 * value converted to a display unit and back still matches its default.
 */
export function sameValue(a: ConfigValue | undefined, b: ConfigValue | undefined): boolean {
    if (typeof a === 'number' && typeof b === 'number') {
        return Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));
    }
    if (typeof a === 'boolean' || typeof b === 'boolean') {
        return asBool(a ?? null) === asBool(b ?? null);
    }
    return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}

/** A config flag as a boolean: true, 'on' and 'true' are on. */
export function asBool(value: ConfigValue): boolean {
    return value === true || value === 'on' || value === 'true' || value === 'True';
}
