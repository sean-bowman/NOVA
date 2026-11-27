/* ========================================
   FORM MODEL TESTS
   src/design/formModel.ts: how a section lays out its rows and folds, when a row counts as
   changed or matches a search, which option a selector row shows and what it writes, and how
   an entry's text becomes a config value and back.
   Sean Bowman [11/27/2026]
   ======================================== */

import { describe, expect, it } from 'vitest';

import {
    blocksOf, chooseOption, choiceLabel, choiceValue, isChanged, keysOf, matchesSearch, optionValue, selectorPatch,
    textToValue, valueToText, type Parsed,
} from '../src/design/formModel';
import { sameValue, toSI, unitsFor } from '../src/design/units';
import type { ConfigValue, GroupSpec } from '../src/types';
import {
    chamberPressure, combustion, coolant, defaults, designVariables, divergingSectionType, engineSize, field,
    maxWallTemperature, nChannel, nozzleExpansion, ofRatio, regenTruncation, throatInletCurvature, units,
} from './fixtures';

/** The value of an entry that parsed; fails the test on one that did not. */
function valueOf(parsed: Parsed): ConfigValue {
    if (!parsed.ok) {
        throw new Error(`expected a value, got '${parsed.message}'`);
    }
    return parsed.value;
}

function messageOf(parsed: Parsed): string {
    if (parsed.ok) {
        throw new Error(`expected a problem, got ${JSON.stringify(parsed.value)}`);
    }
    return parsed.message;
}

// -- Layout -- //

describe('blocksOf', () => {
    it('lays a section out in form order with its fold where the fold\'s first row falls', () => {
        const blocks = blocksOf(combustion);
        expect(blocks.map((block) => (block.kind === 'item' ? block.item.id : `fold ${block.name}`))).toEqual([
            'divergingSectionType', 'OFRatio', 'chamberPressure', 'selector:Engine size', 'selector:Nozzle expansion',
            'fold Advanced settings',
        ]);
        const fold = blocks[5];
        expect(fold.kind === 'fold' && fold.items).toEqual([designVariables, throatInletCurvature]);
    });

    it('gathers a fold\'s later rows into it, past rows outside the fold', () => {
        const group: GroupSpec = { ...combustion, items: [
            chamberPressure, { ...nChannel, fold: 'Channels' }, coolant, { ...ofRatio, fold: 'Channels' },
        ] };
        const blocks = blocksOf(group);
        expect(blocks.map((block) => block.kind)).toEqual(['item', 'fold', 'item']);
        expect(blocks[1].kind === 'fold' && blocks[1].items.map((item) => item.id)).toEqual(['nChannel', 'OFRatio']);
    });

    it('leaves out a hidden field, which has no row', () => {
        const ids = blocksOf({ ...combustion, items: [chamberPressure, field({ key: 'export', label: 'Export',
            kind: 'bool', hidden: true })] }).map((block) => block.kind === 'item' && block.item.id);
        expect(ids).toEqual(['chamberPressure']);
    });
});

describe('keysOf', () => {
    it('gives a field its key and a selector every key it holds', () => {
        expect(keysOf(chamberPressure)).toEqual(['chamberPressure']);
        expect(keysOf(regenTruncation)).toEqual(['regenTruncationType', 'regenTruncationValue']);
    });
});

// -- Changed and search -- //

describe('isChanged', () => {
    it('is false for the shipped value and true for another', () => {
        expect(isChanged(chamberPressure, defaults, defaults)).toBe(false);
        expect(isChanged(chamberPressure, { ...defaults, chamberPressure: 7e6 }, defaults)).toBe(true);
    });

    it('is false for the shipped value entered in another unit', () => {
        for (const unit of unitsFor(units, 'pressure')) {
            const text = valueToText(chamberPressure, defaults.chamberPressure, units, unit);
            const value = valueOf(textToValue(chamberPressure, text, units, unit));
            expect(isChanged(chamberPressure, { ...defaults, chamberPressure: value }, defaults), unit).toBe(false);
        }
    });

    it('marks a selector row changed when any key it holds differs', () => {
        expect(isChanged(engineSize, defaults, defaults)).toBe(false);
        expect(isChanged(engineSize, { ...defaults, thrust: null, engineMassFlow: 50 }, defaults)).toBe(true);
        expect(isChanged(regenTruncation, { ...defaults, regenTruncationType: 'er', regenTruncationValue: 12 },
            defaults)).toBe(true);
    });
});

describe('matchesSearch', () => {
    it('matches everything on an empty query', () => {
        expect(matchesSearch(chamberPressure, '')).toBe(true);
    });

    it('finds a field by its label, key, help or a choice\'s label', () => {
        expect(matchesSearch(chamberPressure, 'chamber pres')).toBe(true);
        expect(matchesSearch(chamberPressure, 'chamberpressure')).toBe(true);
        expect(matchesSearch(chamberPressure, 'stagnation')).toBe(true);
        expect(matchesSearch(divergingSectionType, 'parabola')).toBe(true);
        expect(matchesSearch(chamberPressure, 'parabola')).toBe(false);
    });

    it('finds a selector by its name, an option\'s label or a key it holds', () => {
        expect(matchesSearch(engineSize, 'engine size')).toBe(true);
        expect(matchesSearch(engineSize, 'mass flow')).toBe(true);
        expect(matchesSearch(nozzleExpansion, 'targetexitpressure')).toBe(true);
        expect(matchesSearch(nozzleExpansion, 'thrust')).toBe(false);
    });
});

// -- Selectors -- //

describe('chooseOption', () => {
    it('shows the option whose key holds a value', () => {
        expect(chooseOption(engineSize, defaults).label).toBe('Thrust');
        expect(chooseOption(engineSize, { ...defaults, thrust: null, engineMassFlow: 50 }).label).toBe('Engine mass flow');
    });

    it('falls back to the blank option when no key holds a value', () => {
        expect(chooseOption(engineSize, { ...defaults, thrust: null }).label).toBe('Thrust');
        expect(chooseOption(regenTruncation, { regenTruncationType: null, regenTruncationValue: null }).label)
            .toBe('No truncation (full contour)');
    });

    it('tells apart options that share a key by the constants they set', () => {
        const at = (type: string, value: number | null) =>
            chooseOption(regenTruncation, { regenTruncationType: type, regenTruncationValue: value }).label;
        expect(at('none', null)).toBe('No truncation (full contour)');
        expect(at('temp', 600)).toBe('Truncate at recovery temperature');
        expect(at('er', 12)).toBe('Truncate at area ratio');
        // A mode with no value yet still shows its option
        expect(at('er', null)).toBe('Truncate at area ratio');
    });
});

describe('optionValue', () => {
    it('reads the value only for the option the config describes', () => {
        const [none, temp, er] = regenTruncation.options;
        const config = { regenTruncationType: 'temp', regenTruncationValue: 600 };
        expect(optionValue(temp, config)).toBe(600);
        expect(optionValue(er, config)).toBeNull();
        expect(optionValue(none, config)).toBeNull();
    });
});

describe('selectorPatch', () => {
    it('writes the chosen option\'s value and null to the row\'s other keys', () => {
        const massFlow = engineSize.options[1];
        expect(selectorPatch(engineSize, massFlow, 50)).toEqual({ thrust: null, engineMassFlow: 50 });
    });

    it('writes the constants an option sets', () => {
        const [none, temp] = regenTruncation.options;
        expect(selectorPatch(regenTruncation, temp, 600)).toEqual({ regenTruncationType: 'temp', regenTruncationValue: 600 });
        // An option with no value of its own clears the value key, whatever it is given
        expect(selectorPatch(regenTruncation, none, 600)).toEqual({ regenTruncationType: 'none', regenTruncationValue: null });
    });

    it('writes no key outside the row', () => {
        for (const selector of [engineSize, nozzleExpansion, regenTruncation]) {
            for (const option of selector.options) {
                const written = Object.keys(selectorPatch(selector, option, 1)).sort();
                expect(written, `${selector.name}: ${option.label}`).toEqual([...keysOf(selector)].sort());
            }
        }
    });
});

// -- Entry text -- //

describe('valueToText', () => {
    it('shows a dimensioned value in the unit the row displays', () => {
        expect(valueToText(chamberPressure, 6894757, units, 'Pa')).toBe('6894757');
        expect(valueToText(chamberPressure, 6894757, units, 'MPa')).toBe('6.894757');
        expect(valueToText(chamberPressure, toSI(units, 1000, 'pressure', 'psi'), units, 'psi')).toBe('1000');
        expect(valueToText(maxWallTemperature, 800, units, 'degC')).toBe('526.85');
        expect(valueToText(maxWallTemperature, 800, units, 'degF')).toBe('980.33');
    });

    it('shows a list of numbers as comma-separated text', () => {
        expect(valueToText(designVariables, [0.1, 0.25, 1 / 3], units, null)).toBe('0.1, 0.25, 0.3333333333');
    });

    it('shows a structured value as JSON, and text, flags and nothing as they are', () => {
        const slots = field({ key: 'extensionFilmSlots', label: 'Film slots', kind: 'text' });
        expect(valueToText(slots, [{ position: 0.5 }], units, null)).toBe('[{"position":0.5}]');
        expect(valueToText(coolant, 'Hydrogen', units, null)).toBe('Hydrogen');
        expect(valueToText(coolant, true, units, null)).toBe('true');
        expect(valueToText(chamberPressure, null, units, 'MPa')).toBe('');
    });
});

describe('textToValue', () => {
    it('reads a blank entry as no value', () => {
        expect(valueOf(textToValue(chamberPressure, '   ', units, 'Pa'))).toBeNull();
        expect(valueOf(textToValue(coolant, '', units, null))).toBeNull();
    });

    it('reads a number in the unit shown and returns it in SI', () => {
        expect(valueOf(textToValue(chamberPressure, ' 6.9 ', units, 'MPa'))).toBeCloseTo(6.9e6, 6);
        expect(valueOf(textToValue(chamberPressure, '1e3', units, 'psi'))).toBeCloseTo(6894757.2931683635, 6);
        expect(valueOf(textToValue(maxWallTemperature, '526.85', units, 'degC'))).toBeCloseTo(800, 9);
    });

    it('refuses a number it cannot read, naming the field', () => {
        expect(messageOf(textToValue(chamberPressure, '7 MPa', units, 'Pa'))).toBe('Chamber pressure: \'7 MPa\' is not a number');
        expect(messageOf(textToValue(chamberPressure, '1,000', units, 'Pa'))).toContain('is not a number');
        expect(messageOf(textToValue(chamberPressure, 'Infinity', units, 'Pa'))).toContain('is not a number');
        expect(messageOf(textToValue(engineSize.members[0], 'lots', units, 'N', 'Thrust'))).toBe('Thrust: \'lots\' is not a number');
    });

    it('cuts an integer entry\'s fraction toward zero', () => {
        expect(valueOf(textToValue(nChannel, '60', units, null))).toBe(60);
        expect(valueOf(textToValue(nChannel, '60.7', units, null))).toBe(60);
        expect(valueOf(textToValue(nChannel, '-3.9', units, null))).toBe(-3);
        expect(messageOf(textToValue(nChannel, 'sixty', units, null))).toBe('Number of channels: \'sixty\' is not an integer');
    });

    it('reads a number-or-text entry as a number when it is one and as text otherwise', () => {
        expect(valueOf(textToValue(ofRatio, '5.5', units, null))).toBe(5.5);
        expect(valueOf(textToValue(ofRatio, 'fuelRich', units, null))).toBe('fuelRich');
    });

    it('reads a list of numbers with or without brackets', () => {
        expect(valueOf(textToValue(designVariables, '0.1, 0.25', units, null))).toEqual([0.1, 0.25]);
        expect(valueOf(textToValue(designVariables, '[1, 2, 3]', units, null))).toEqual([1, 2, 3]);
        expect(valueOf(textToValue(designVariables, '1,,2', units, null))).toEqual([1, 2]);
        expect(messageOf(textToValue(designVariables, '1, two', units, null)))
            .toBe('Design vector: \'1, two\' is not a list of numbers');
    });

    it('reads a structured entry as JSON and plain text as text', () => {
        const slots = field({ key: 'extensionFilmSlots', label: 'Film slots', kind: 'text' });
        expect(valueOf(textToValue(slots, '[{"position": 0.5}]', units, null))).toEqual([{ position: 0.5 }]);
        expect(messageOf(textToValue(slots, '{position', units, null))).toBe('Film slots: \'{position\' is not valid JSON');
        expect(valueOf(textToValue(coolant, 'Methane', units, null))).toBe('Methane');
    });

    it('returns the value it showed, in every unit', () => {
        const cases: [typeof chamberPressure, number][] = [[chamberPressure, 6894757], [chamberPressure, 101325 / 3],
                                                           [maxWallTemperature, 800], [maxWallTemperature, 20.27]];
        for (const [spec, value] of cases) {
            for (const unit of unitsFor(units, spec.dimension!)) {
                const text = valueToText(spec, value, units, unit);
                expect(sameValue(valueOf(textToValue(spec, text, units, unit)), value), `${value} in ${unit} as ${text}`)
                    .toBe(true);
            }
        }
    });
});

describe('choiceLabel and choiceValue', () => {
    it('map between a choice\'s value and its label', () => {
        expect(choiceLabel(divergingSectionType, 'top')).toBe('Thrust-optimized parabola (top)');
        expect(choiceValue(divergingSectionType, 'Conical (cone)')).toBe('cone');
    });

    it('pass a value off the list through as typed', () => {
        expect(choiceLabel(divergingSectionType, 'bell')).toBe('bell');
        expect(choiceValue(divergingSectionType, 'bell')).toBe('bell');
    });

    it('take no value as a blank label and a blank label as no value', () => {
        expect(choiceLabel(divergingSectionType, null)).toBe('');
        expect(choiceValue(divergingSectionType, '')).toBeNull();
    });
});
