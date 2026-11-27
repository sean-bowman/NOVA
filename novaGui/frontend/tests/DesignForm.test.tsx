/* ========================================
   DESIGN FORM TESTS
   src/design/DesignForm.tsx over the fixture schema, in a harness that holds the config and
   the form's problems the way App.tsx does: Changed only and the restore under it, the search,
   and the server's cross-field problems written over the form, under the rows they name and
   counted on their section.
   Sean Bowman [11/27/2026]
   ======================================== */

import { fireEvent, render, screen, within } from '@testing-library/react';
import { useCallback, useState } from 'react';
import { describe, expect, it } from 'vitest';

import { DesignForm } from '../src/design/DesignForm';
import type { Config, FormState } from '../src/types';
import { defaults, quietForm, schema } from './fixtures';

function Harness({ start = defaults, formState = quietForm }: { start?: Config; formState?: FormState }) {
    const [config, setConfig] = useState<Config>(start);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const onPatch = useCallback((patch: Config) => setConfig((previous) => ({ ...previous, ...patch })), []);
    const onError = useCallback((id: string, message: string | null) => {
        setErrors((previous) => {
            if ((previous[id] ?? null) === message) {
                return previous;
            }
            const next = { ...previous };
            if (message === null) {
                delete next[id];
            } else {
                next[id] = message;
            }
            return next;
        });
    }, []);
    const ignore = () => undefined;
    return <DesignForm schema={schema} config={config} formVersion={0} formState={formState} errors={errors}
                       onPatch={onPatch} onError={onError} onReset={ignore} onLoadExample={ignore} onSave={ignore} />;
}

/** Whether a row shows: neither it nor its fold nor its section is hidden. */
function shown(label: string): boolean {
    return screen.getByLabelText(label).closest('[hidden]') === null;
}

const rowOf = (label: string) => screen.getByLabelText(label).closest('.form-row') as HTMLElement;
const sectionOf = (title: string) =>
    screen.getByText(title, { selector: '.section-title' }).closest('section') as HTMLElement;
const changedCount = () => screen.getByText(/changed from the shipped nozzle$/).textContent;
const restore = (label: string) =>
    fireEvent.click(screen.getByRole('button', { name: `Restore ${label} to the shipped value` }));

describe('Changed only', () => {
    const start = { ...defaults, chamberPressure: 7e6, nChannel: 80 };

    it('shows the rows that differ from the shipped values and no others', () => {
        render(<Harness start={start} />);
        expect(changedCount()).toBe('2 changed from the shipped nozzle');
        fireEvent.click(screen.getByLabelText('Changed only'));
        expect(shown('Chamber pressure')).toBe(true);
        expect(shown('Number of channels')).toBe(true);
        for (const label of ['O/F ratio', 'Coolant species', 'Engine size', 'Regen truncation', 'Design vector']) {
            expect(shown(label), label).toBe(false);
        }
    });

    it('takes a restored row off the list, and its section once none is left', () => {
        render(<Harness start={start} />);
        fireEvent.click(screen.getByLabelText('Changed only'));
        restore('Chamber pressure');
        expect(shown('Chamber pressure')).toBe(false);
        expect(sectionOf('Combustion').hidden).toBe(true);
        expect(changedCount()).toBe('1 changed from the shipped nozzle');
        restore('Number of channels');
        expect(changedCount()).toBe('0 changed from the shipped nozzle');
        expect(screen.getByText('No field matches.')).toBeTruthy();
    });

    it('shows a selector row whose option or value differs', () => {
        render(<Harness start={{ ...defaults, thrust: null, engineMassFlow: 50 }} />);
        fireEvent.click(screen.getByLabelText('Changed only'));
        expect(shown('Engine size')).toBe(true);
        expect(shown('Nozzle expansion')).toBe(false);
    });

    it('counts a changed row on its section', () => {
        render(<Harness start={start} />);
        expect(within(sectionOf('Combustion')).getByText('1 changed')).toBeTruthy();
        expect(within(sectionOf('Regenerative Cooling')).getByText('1 changed')).toBeTruthy();
    });

    it('counts a value typed in a display unit as unchanged when it is the shipped value', () => {
        render(<Harness />);
        fireEvent.change(screen.getByLabelText('Chamber pressure unit'), { target: { value: 'psi' } });
        fireEvent.focus(screen.getByLabelText('Chamber pressure'));
        fireEvent.change(screen.getByLabelText('Chamber pressure'), { target: { value: '999.9999575' } });
        expect(changedCount()).toBe('0 changed from the shipped nozzle');
    });
});

describe('the search', () => {
    it('narrows the form to the rows that match, inside a closed fold too', () => {
        render(<Harness />);
        expect(shown('Design vector')).toBe(false);
        fireEvent.change(screen.getByLabelText('Find a field'), { target: { value: 'Stagnation' } });
        expect(shown('Chamber pressure')).toBe(true);
        expect(shown('O/F ratio')).toBe(false);
        expect(sectionOf('Regenerative Cooling').hidden).toBe(true);
        fireEvent.change(screen.getByLabelText('Find a field'), { target: { value: 'design vector' } });
        expect(shown('Design vector')).toBe(true);
    });

    it('says so when nothing matches', () => {
        render(<Harness />);
        fireEvent.change(screen.getByLabelText('Find a field'), { target: { value: 'turbopump' } });
        expect(screen.getByText('No field matches.')).toBeTruthy();
    });
});

describe('the problems', () => {
    const message = 'Chamber pressure is below the coolant\'s critical pressure.';
    const formState: FormState = {
        ...quietForm, problems: [message], flagged: ['chamberPressure'], notes: { chamberPressure: [message] },
    };

    it('lists the server\'s problems over the form', () => {
        render(<Harness formState={formState} />);
        expect(within(screen.getByRole('status')).getByText(message)).toBeTruthy();
    });

    it('writes a problem under the row it names and counts it on the section, to check', () => {
        render(<Harness formState={formState} />);
        expect(within(rowOf('Chamber pressure')).getByRole('note').textContent).toBe(message);
        expect(within(sectionOf('Combustion')).getByText('1 to check')).toBeTruthy();
        expect(within(sectionOf('Regenerative Cooling')).queryByText(/to check/)).toBeNull();
    });

    it('counts an entry it cannot read on its section, to fix, in place of a problem to check', () => {
        render(<Harness formState={formState} />);
        fireEvent.focus(screen.getByLabelText('Chamber pressure'));
        fireEvent.change(screen.getByLabelText('Chamber pressure'), { target: { value: 'abc' } });
        expect(within(sectionOf('Combustion')).getByText('1 to fix')).toBeTruthy();
        expect(within(sectionOf('Combustion')).queryByText(/to check/)).toBeNull();
        expect(within(rowOf('Chamber pressure')).queryByRole('note')).toBeNull();
    });

    it('counts a required selector row left blank, to fix', () => {
        render(<Harness />);
        fireEvent.change(screen.getByLabelText('Thrust'), { target: { value: '' } });
        expect(within(sectionOf('Combustion')).getByText('1 to fix')).toBeTruthy();
    });
});
