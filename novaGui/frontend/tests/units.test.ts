/* ========================================
   DISPLAY UNIT TESTS
   src/design/units.ts: conversion through the server's unit table, the text a number shows
   as, and when two config values are the same setting.
   Sean Bowman [11/27/2026]
   ======================================== */

import { describe, expect, it } from 'vitest';

import { asBool, formatNumber, fromSI, sameValue, siUnit, toSI, unitsFor } from '../src/design/units';
import { units } from './fixtures';

describe('conversion', () => {
    it('takes a pressure to SI and back', () => {
        expect(toSI(units, 1000, 'pressure', 'psi')).toBeCloseTo(6894757.2931683635, 6);
        expect(fromSI(units, 6894757.2931683635, 'pressure', 'psi')).toBeCloseTo(1000, 9);
        expect(toSI(units, 6.9, 'pressure', 'MPa')).toBeCloseTo(6.9e6, 6);
    });

    it('applies the offset of a temperature scale', () => {
        expect(toSI(units, 0, 'temperature', 'degC')).toBe(273.15);
        expect(fromSI(units, 300, 'temperature', 'degC')).toBeCloseTo(26.85, 12);
        expect(toSI(units, 32, 'temperature', 'degF')).toBeCloseTo(273.15, 9);
        expect(fromSI(units, 373.15, 'temperature', 'degF')).toBeCloseTo(212, 9);
        expect(fromSI(units, 0, 'temperature', 'degR')).toBe(0);
    });

    it('names the SI unit and the units a dimension offers', () => {
        expect(siUnit(units, 'pressure')).toBe('Pa');
        expect(unitsFor(units, 'temperature')).toEqual(['K', 'degC', 'degR', 'degF']);
        expect(unitsFor(units, 'luminosity')).toEqual([]);
    });

    it('refuses a unit the table does not hold', () => {
        expect(() => toSI(units, 1, 'pressure', 'furlong')).toThrow('no unit furlong for pressure');
        expect(() => fromSI(units, 1, 'luminosity', 'cd')).toThrow('no unit cd for luminosity');
    });
});

describe('formatNumber', () => {
    it('writes an integer without a decimal point', () => {
        expect(formatNumber(1000)).toBe('1000');
        expect(formatNumber(-3)).toBe('-3');
        expect(formatNumber(0)).toBe('0');
    });

    it('writes a value within a relative 1e-9 of an integer as the integer', () => {
        expect(formatNumber(999.99999999999)).toBe('1000');
        expect(formatNumber(fromSI(units, toSI(units, 1000, 'pressure', 'psi'), 'pressure', 'psi'))).toBe('1000');
    });

    it('keeps ten significant figures and drops trailing zeros', () => {
        expect(formatNumber(6.894757)).toBe('6.894757');
        expect(formatNumber(1 / 3)).toBe('0.3333333333');
        expect(formatNumber(6894757.2931683635)).toBe('6894757.293');
        expect(formatNumber(1.5e-6)).toBe('0.0000015');
    });

    it('writes nothing for a missing or undefined number', () => {
        expect(formatNumber(null)).toBe('');
        expect(formatNumber(undefined)).toBe('');
        expect(formatNumber(Number.NaN)).toBe('');
    });
});

describe('sameValue', () => {
    it('matches numbers to a relative 1e-9', () => {
        expect(sameValue(6894757, 6894757 * (1 + 5e-10))).toBe(true);
        expect(sameValue(6894757, 6894757 * (1 + 2e-9))).toBe(false);
        expect(sameValue(0, 5e-10)).toBe(true);
        expect(sameValue(0, 2e-9)).toBe(false);
    });

    it('matches a value taken to a display unit and back', () => {
        for (const unit of unitsFor(units, 'temperature')) {
            const back = toSI(units, fromSI(units, 800, 'temperature', unit), 'temperature', unit);
            expect(sameValue(back, 800), unit).toBe(true);
        }
    });

    it('reads a flag the way asBool does', () => {
        expect(sameValue(true, 'on')).toBe(true);
        expect(sameValue(true, 'True')).toBe(true);
        expect(sameValue(false, null)).toBe(true);
        expect(sameValue(false, 'on')).toBe(false);
    });

    it('compares text, lists and missing values by content', () => {
        expect(sameValue('tic', 'tic')).toBe(true);
        expect(sameValue('tic', 'top')).toBe(false);
        expect(sameValue([0.1, 0.2], [0.1, 0.2])).toBe(true);
        expect(sameValue([0.1, 0.2], [0.2, 0.1])).toBe(false);
        expect(sameValue(null, undefined)).toBe(true);
        expect(sameValue(5.5, '5.5')).toBe(false);
    });
});

describe('asBool', () => {
    it('takes true and the on strings as on, everything else as off', () => {
        for (const value of [true, 'on', 'true', 'True']) {
            expect(asBool(value), String(value)).toBe(true);
        }
        for (const value of [false, 'off', 'false', null, 1, 'yes']) {
            expect(asBool(value), String(value)).toBe(false);
        }
    });
});
