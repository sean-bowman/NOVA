/* ========================================
   FIELD ROW TESTS
   src/design/FieldRow.tsx in a harness that holds the value and the row's problem the way
   App.tsx holds the config and the form's problems: an entry read in the unit shown, the
   conversion in place when the unit changes, the restore to the shipped value, and the problems
   written under the row.
   Sean Bowman [11/27/2026]
   ======================================== */

import { fireEvent, render, screen, within } from '@testing-library/react';
import { useCallback, useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { FieldRow } from '../src/design/FieldRow';
import { sameValue, toSI } from '../src/design/units';
import type { Config, ConfigValue, FieldSpec } from '../src/types';
import { chamberPressure, divergingSectionType, makeCoolingChannels, maxWallTemperature, nChannel, units } from './fixtures';

interface HarnessProps {
    spec: FieldSpec;
    start: ConfigValue;
    notes?: string[];
    flagged?: boolean;
    spy?: (patch: Config) => void;
}

function Harness({ spec, start, notes, flagged, spy }: HarnessProps) {
    const [value, setValue] = useState<ConfigValue>(start);
    const [error, setError] = useState<string | null>(null);
    const onChange = useCallback((patch: Config) => {
        spy?.(patch);
        setValue(patch[spec.key] ?? null);
    }, [spec, spy]);
    const onError = useCallback((_id: string, message: string | null) => setError(message), []);
    return (
        <>
            <FieldRow spec={spec} value={value} defaultValue={spec.default} units={units} visible
                      changed={!sameValue(value, spec.default)} error={error} flagged={flagged} notes={notes}
                      onChange={onChange} onError={onError} />
            <output data-testid="value">{JSON.stringify(value)}</output>
        </>
    );
}

const entry = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const unitOf = (label: string) => screen.getByLabelText(`${label} unit`) as HTMLSelectElement;
const rowOf = (label: string) => entry(label).closest('.form-row') as HTMLElement;
const held = () => JSON.parse(screen.getByTestId('value').textContent ?? 'null') as ConfigValue;

/** Typing into an entry: it holds the focus while the text changes. */
function type(input: HTMLElement, text: string) {
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: text } });
}

describe('a dimensioned entry', () => {
    it('shows the value in SI to begin with', () => {
        render(<Harness spec={chamberPressure} start={6894757} />);
        expect(entry('Chamber pressure').value).toBe('6894757');
        expect(unitOf('Chamber pressure').value).toBe('Pa');
    });

    it('converts the shown value in place when the unit changes, and writes nothing', () => {
        const spy = vi.fn();
        render(<Harness spec={chamberPressure} start={6894757} spy={spy} />);
        fireEvent.change(unitOf('Chamber pressure'), { target: { value: 'MPa' } });
        expect(entry('Chamber pressure').value).toBe('6.894757');
        fireEvent.change(unitOf('Chamber pressure'), { target: { value: 'bar' } });
        expect(entry('Chamber pressure').value).toBe('68.94757');
        expect(spy).not.toHaveBeenCalled();
        expect(held()).toBe(6894757);
    });

    it('converts a temperature through its offset', () => {
        render(<Harness spec={maxWallTemperature} start={800} />);
        fireEvent.change(unitOf('Max wall temperature'), { target: { value: 'degC' } });
        expect(entry('Max wall temperature').value).toBe('526.85');
        fireEvent.change(unitOf('Max wall temperature'), { target: { value: 'degF' } });
        expect(entry('Max wall temperature').value).toBe('980.33');
    });

    it('reads a typed value in the unit shown and writes it in SI', () => {
        render(<Harness spec={chamberPressure} start={6894757} />);
        fireEvent.change(unitOf('Chamber pressure'), { target: { value: 'psi' } });
        type(entry('Chamber pressure'), '1200');
        expect(held()).toBeCloseTo(toSI(units, 1200, 'pressure', 'psi'), 6);
        // The entry keeps what was typed while it holds the focus, and shows the value again on leaving
        expect(entry('Chamber pressure').value).toBe('1200');
        fireEvent.blur(entry('Chamber pressure'));
        expect(entry('Chamber pressure').value).toBe('1200');
    });

    it('writes nothing for an entry equal to the value held', () => {
        const spy = vi.fn();
        render(<Harness spec={chamberPressure} start={6894757} spy={spy} />);
        fireEvent.change(unitOf('Chamber pressure'), { target: { value: 'MPa' } });
        type(entry('Chamber pressure'), '6.894757');
        expect(spy).not.toHaveBeenCalled();
    });
});

describe('an entry it cannot read', () => {
    it('writes the problem under the row and nothing to the config', () => {
        const spy = vi.fn();
        render(<Harness spec={chamberPressure} start={6894757} spy={spy} />);
        type(entry('Chamber pressure'), '7 MPa');
        expect(spy).not.toHaveBeenCalled();
        expect(rowOf('Chamber pressure').querySelector('.form-note-error')?.textContent)
            .toBe('Chamber pressure: \'7 MPa\' is not a number');
        expect(entry('Chamber pressure').className).toContain('input-error');
    });

    it('keeps the typed text over leaving the entry and over a unit change, with its problem', () => {
        render(<Harness spec={chamberPressure} start={6894757} />);
        type(entry('Chamber pressure'), 'abc');
        fireEvent.blur(entry('Chamber pressure'));
        expect(entry('Chamber pressure').value).toBe('abc');
        fireEvent.change(unitOf('Chamber pressure'), { target: { value: 'MPa' } });
        expect(entry('Chamber pressure').value).toBe('abc');
        expect(rowOf('Chamber pressure').querySelector('.form-note-error')?.textContent)
            .toBe('Chamber pressure: \'abc\' is not a number');
    });

    it('clears its problem once the entry reads', () => {
        render(<Harness spec={chamberPressure} start={6894757} />);
        type(entry('Chamber pressure'), 'abc');
        type(entry('Chamber pressure'), '7e6');
        expect(rowOf('Chamber pressure').querySelector('.form-note-error')).toBeNull();
        expect(held()).toBe(7e6);
    });

    it('cuts an integer entry\'s fraction', () => {
        render(<Harness spec={nChannel} start={60} />);
        type(entry('Number of channels'), '80.6');
        expect(held()).toBe(80);
    });
});

describe('the restore to the shipped value', () => {
    it('shows only on a changed row and writes the shipped value', () => {
        render(<Harness spec={chamberPressure} start={7e6} />);
        fireEvent.click(screen.getByRole('button', { name: 'Restore Chamber pressure to the shipped value' }));
        expect(held()).toBe(6894757);
        expect(entry('Chamber pressure').value).toBe('6894757');
        expect(screen.queryByRole('button', { name: /^Restore/ })).toBeNull();
    });

    it('clears a problem the entry had', () => {
        render(<Harness spec={chamberPressure} start={7e6} />);
        type(entry('Chamber pressure'), 'abc');
        fireEvent.blur(entry('Chamber pressure'));
        fireEvent.click(screen.getByRole('button', { name: 'Restore Chamber pressure to the shipped value' }));
        expect(entry('Chamber pressure').value).toBe('6894757');
        expect(rowOf('Chamber pressure').querySelector('.form-note-error')).toBeNull();
    });

    it('shows the shipped value in the unit the row displays', () => {
        render(<Harness spec={chamberPressure} start={7e6} />);
        fireEvent.change(unitOf('Chamber pressure'), { target: { value: 'MPa' } });
        expect(entry('Chamber pressure').value).toBe('7');
        fireEvent.click(screen.getByRole('button', { name: 'Restore Chamber pressure to the shipped value' }));
        expect(entry('Chamber pressure').value).toBe('6.894757');
    });
});

describe('the problems under the row', () => {
    it('writes each problem that names the row and marks its label', () => {
        const notes = ['Chamber pressure is below the coolant\'s critical pressure.'];
        render(<Harness spec={chamberPressure} start={6894757} notes={notes} flagged />);
        expect(within(rowOf('Chamber pressure')).getByRole('note').textContent).toBe(notes[0]);
        expect(screen.getByText('Chamber pressure', { selector: 'label' }).className).toBe('label-warn');
    });

    it('writes the entry\'s own problem in their place while it stands', () => {
        render(<Harness spec={chamberPressure} start={6894757} notes={['A cross-field problem.']} flagged />);
        type(entry('Chamber pressure'), 'abc');
        expect(within(rowOf('Chamber pressure')).queryByRole('note')).toBeNull();
        expect(screen.getByText('Chamber pressure', { selector: 'label' }).className).toBe('label-error');
    });
});

describe('the other editors', () => {
    it('writes a switch as a flag', () => {
        render(<Harness spec={makeCoolingChannels} start={true} />);
        fireEvent.click(entry('Generate cooling channels'));
        expect(held()).toBe(false);
    });

    it('writes a choice\'s value for its label and shows a value off the list', () => {
        render(<Harness spec={divergingSectionType} start="bell" />);
        const select = entry('Diverging section type') as unknown as HTMLSelectElement;
        expect(select.value).toBe('bell');
        fireEvent.change(select, { target: { value: 'Conical (cone)' } });
        expect(held()).toBe('cone');
    });
});
