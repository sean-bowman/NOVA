/* ========================================
   SELECTOR ROW TESTS
   src/design/SelectorRow.tsx in a harness that holds the config and the row's problem the way
   App.tsx does: the option the config describes, the keys a choice writes and the ones it
   leaves alone, each option's own text and unit, the conversion in place when the unit changes,
   and the problems written under the row.
   Sean Bowman [11/27/2026]
   ======================================== */

import { fireEvent, render, screen, within } from '@testing-library/react';
import { useCallback, useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { isChanged, keysOf } from '../src/design/formModel';
import { SelectorRow } from '../src/design/SelectorRow';
import type { Config, SelectorSpec } from '../src/types';
import { defaults, engineSize, regenTruncation, units } from './fixtures';

interface HarnessProps {
    selector: SelectorSpec;
    start?: Config;
    visible?: boolean;
    notes?: string[];
    flagged?: boolean;
    spy?: (patch: Config) => void;
}

function Harness({ selector, start = defaults, visible = true, notes, flagged, spy }: HarnessProps) {
    const [config, setConfig] = useState<Config>(start);
    const [error, setError] = useState<string | null>(null);
    const onChange = useCallback((patch: Config) => {
        spy?.(patch);
        setConfig((previous) => ({ ...previous, ...patch }));
    }, [spy]);
    const onError = useCallback((_id: string, message: string | null) => setError(message), []);
    return (
        <>
            <SelectorRow selector={selector} config={config} units={units} visible={visible}
                         changed={isChanged(selector, config, defaults)} error={error} flagged={flagged} notes={notes}
                         onChange={onChange} onError={onError} />
            <output data-testid="config">{JSON.stringify(config)}</output>
            <output data-testid="error">{error ?? ''}</output>
        </>
    );
}

const optionOf = (selector: SelectorSpec) => screen.getByLabelText(selector.name) as HTMLSelectElement;
const entry = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const unitOf = (label: string) => screen.getByLabelText(`${label} unit`) as HTMLSelectElement;
const held = () => JSON.parse(screen.getByTestId('config').textContent ?? '{}') as Config;
const problem = () => screen.getByTestId('error').textContent;
const row = () => document.querySelector('.form-row') as HTMLElement;

const choose = (selector: SelectorSpec, label: string) => fireEvent.change(optionOf(selector), { target: { value: label } });
const type = (input: HTMLElement, text: string) => fireEvent.change(input, { target: { value: text } });

/** The config with every key outside the row as the start had it. */
function outside(selector: SelectorSpec, config: Config): Config {
    const keys = new Set(keysOf(selector));
    return Object.fromEntries(Object.entries(config).filter(([key]) => !keys.has(key)));
}

describe('the option shown', () => {
    it('is the one whose key the config holds a value for', () => {
        render(<Harness selector={engineSize} start={{ ...defaults, thrust: null, engineMassFlow: 50 }} />);
        expect(optionOf(engineSize).value).toBe('Engine mass flow');
        expect(entry('Engine mass flow').value).toBe('50');
        expect(unitOf('Engine mass flow').value).toBe('kg/s');
    });

    it('is the one whose constants the config sets, among options sharing a key', () => {
        render(<Harness selector={regenTruncation}
                        start={{ ...defaults, regenTruncationType: 'er', regenTruncationValue: 12 }} />);
        expect(optionOf(regenTruncation).value).toBe('Truncate at area ratio');
        expect(entry('Truncate at area ratio').value).toBe('12');
    });
});

describe('a choice', () => {
    it('writes the chosen option\'s value and null to the row\'s other key, and no key outside the row', () => {
        const spy = vi.fn();
        render(<Harness selector={engineSize} spy={spy} />);
        choose(engineSize, 'Engine mass flow');
        type(entry('Engine mass flow'), '50');
        expect(held()).toMatchObject({ thrust: null, engineMassFlow: 50 });
        expect(outside(engineSize, held())).toEqual(outside(engineSize, defaults));
        for (const [patch] of spy.mock.calls) {
            expect(Object.keys(patch).sort()).toEqual(['engineMassFlow', 'thrust']);
        }
    });

    it('keeps each option\'s text while another is chosen', () => {
        render(<Harness selector={engineSize} />);
        choose(engineSize, 'Engine mass flow');
        type(entry('Engine mass flow'), '50');
        choose(engineSize, 'Thrust');
        expect(entry('Thrust').value).toBe('100000');
        expect(held()).toMatchObject({ thrust: 100000, engineMassFlow: null });
        choose(engineSize, 'Engine mass flow');
        expect(entry('Engine mass flow').value).toBe('50');
        expect(held()).toMatchObject({ thrust: null, engineMassFlow: 50 });
    });

    it('writes the constants of options that share a key', () => {
        render(<Harness selector={regenTruncation} />);
        choose(regenTruncation, 'Truncate at recovery temperature');
        fireEvent.change(unitOf('Truncate at recovery temperature'), { target: { value: 'degC' } });
        type(entry('Truncate at recovery temperature'), '326.85');
        expect(held().regenTruncationType).toBe('temp');
        expect(held().regenTruncationValue).toBeCloseTo(600, 9);
        choose(regenTruncation, 'Truncate at area ratio');
        expect(held()).toMatchObject({ regenTruncationType: 'er', regenTruncationValue: null });
        type(entry('Truncate at area ratio'), '12');
        expect(held()).toMatchObject({ regenTruncationType: 'er', regenTruncationValue: 12 });
        choose(regenTruncation, 'No truncation (full contour)');
        expect(held()).toMatchObject({ regenTruncationType: 'none', regenTruncationValue: null });
        expect(entry('No truncation (full contour)').disabled).toBe(true);
    });
});

describe('a unit change', () => {
    it('converts the shown number in place and writes nothing', () => {
        const spy = vi.fn();
        render(<Harness selector={engineSize} spy={spy} />);
        fireEvent.change(unitOf('Thrust'), { target: { value: 'kN' } });
        expect(entry('Thrust').value).toBe('100');
        fireEvent.change(unitOf('Thrust'), { target: { value: 'lbf' } });
        expect(entry('Thrust').value).toBe('22480.89431');
        expect(spy).not.toHaveBeenCalled();
    });

    it('reads what is typed next in the new unit', () => {
        render(<Harness selector={engineSize} />);
        fireEvent.change(unitOf('Thrust'), { target: { value: 'kN' } });
        type(entry('Thrust'), '120');
        expect(held().thrust).toBe(120000);
    });

    it('keeps an entry it cannot read as typed', () => {
        render(<Harness selector={engineSize} />);
        type(entry('Thrust'), 'abc');
        fireEvent.change(unitOf('Thrust'), { target: { value: 'kN' } });
        expect(entry('Thrust').value).toBe('abc');
        expect(problem()).toBe('Thrust: \'abc\' is not a number');
    });
});

describe('the problems under the row', () => {
    it('name an entry it cannot read, which writes nothing', () => {
        const spy = vi.fn();
        render(<Harness selector={engineSize} spy={spy} />);
        type(entry('Thrust'), '1e5 N');
        expect(spy).not.toHaveBeenCalled();
        expect(held().thrust).toBe(100000);
        expect(row().querySelector('.form-note-error')?.textContent).toBe('Thrust: \'1e5 N\' is not a number');
        expect(entry('Thrust').className).toContain('input-error');
    });

    it('ask for a value a required row lacks, while the row is shown', () => {
        render(<Harness selector={engineSize} />);
        type(entry('Thrust'), '');
        expect(held().thrust).toBeNull();
        expect(problem()).toBe('\'Thrust\' needs a value.');
        type(entry('Thrust'), '9e4');
        expect(problem()).toBe('');
    });

    it('do not ask for a value while the row is hidden', () => {
        render(<Harness selector={engineSize} start={{ ...defaults, thrust: null }} visible={false} />);
        expect(problem()).toBe('');
    });

    it('do not ask for a value an option has none of', () => {
        render(<Harness selector={regenTruncation} />);
        expect(optionOf(regenTruncation).value).toBe('No truncation (full contour)');
        expect(problem()).toBe('');
    });

    it('write each cross-field problem that names the row and mark the option', () => {
        const notes = ['Thrust and chamber pressure give a throat smaller than the channel count allows.'];
        render(<Harness selector={engineSize} notes={notes} flagged />);
        expect(within(row()).getByRole('note').textContent).toBe(notes[0]);
        expect(optionOf(engineSize).className).toContain('input-warn');
    });
});
