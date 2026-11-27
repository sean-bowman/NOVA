/* ========================================
   NOT RUN TESTS
   src/run/notRun.ts and the run bar's list of the runs a closed window left unrun (NotRunPanel):
   what each run's config changes from the shipped nozzle, when it was queued, and the run ids
   each button hands on.
   Sean Bowman [11/27/2026]
   ======================================== */

import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { changesText, notRunChanges, queuedText } from '../src/run/notRun';
import { NotRunPanel } from '../src/run/RunBar';
import type { NotRunEntry } from '../src/types';
import { schema } from './fixtures';

function entry(notRunId: number, label: string, config: NotRunEntry['config'], reason = 'NOVA closed before it ran'): NotRunEntry {
    return { notRunId, label, runName: label, config, mode: 'dark', queuedAt: 1.8e9, reason };
}

const going = entry(1, 'NOVANozzle', { chamberPressure: 7e6, thrust: 120000 }, 'NOVA closed while it ran');
const waiting = entry(2, 'NOVANozzle', { nChannel: 80 });
const shipped = entry(3, 'shipped', {});

describe('notRunChanges', () => {
    it('lists the rows a run\'s config changes from the shipped nozzle, in form order', () => {
        expect(notRunChanges(schema, going).map((change) => [change.label, change.after])).toEqual([
            ['Chamber pressure', '7000 kPa'], ['Engine size', 'Thrust 120 kN'],
        ]);
    });

    it('takes a field the config lacks at its default', () => {
        expect(notRunChanges(schema, waiting).map((change) => change.label)).toEqual(['Number of channels']);
        expect(notRunChanges(schema, shipped)).toEqual([]);
    });
});

describe('changesText', () => {
    const changes = (count: number) => Array.from({ length: count }, (_, index) => ({
        id: `field${index}`, label: `Field ${index}`, before: '1', after: String(index + 2),
    }));

    it('names the shipped nozzle for a config that changes nothing', () => {
        expect(changesText([])).toBe('the shipped nozzle');
    });

    it('names up to three changes, then counts the rest', () => {
        expect(changesText(changes(2))).toBe('Field 0 2, Field 1 3');
        expect(changesText(changes(3))).toBe('Field 0 2, Field 1 3, Field 2 4');
        expect(changesText(changes(5))).toBe('Field 0 2, Field 1 3, Field 2 4 and 2 more');
    });
});

describe('queuedText', () => {
    it('says when the run was queued, and nothing when the store did not', () => {
        expect(queuedText(1.8e9)).toMatch(/^queued \S/);
        expect(queuedText(0)).toBe('');
    });
});

describe('the list of runs not run', () => {
    function renderPanel(withSchema = true) {
        const handlers = { onQueue: vi.fn(), onDiscard: vi.fn(), onEdit: vi.fn(), onClose: vi.fn() };
        render(<NotRunPanel entries={[going, waiting]} schema={withSchema ? schema : null} {...handlers} />);
        return handlers;
    }

    const rows = () => screen.getAllByRole('listitem');

    it('shows each run with why it did not run and what it changes', () => {
        renderPanel();
        expect(rows()).toHaveLength(2);
        expect(within(rows()[0]).getByText(/^NOVA closed while it ran, queued /)).toBeTruthy();
        expect(within(rows()[0]).getByText('Chamber pressure 7000 kPa, Engine size Thrust 120 kN')).toBeTruthy();
        expect(within(rows()[1]).getByText('Number of channels 80')).toBeTruthy();
    });

    it('hands on the run of the button pressed', () => {
        const handlers = renderPanel();
        fireEvent.click(within(rows()[1]).getByRole('button', { name: 'Queue NOVANozzle again' }));
        expect(handlers.onQueue).toHaveBeenCalledWith([2]);
        fireEvent.click(within(rows()[0]).getByRole('button', { name: 'Discard NOVANozzle' }));
        expect(handlers.onDiscard).toHaveBeenCalledWith([1]);
        fireEvent.click(within(rows()[0]).getByRole('button', { name: 'Edit NOVANozzle in the form' }));
        expect(handlers.onEdit).toHaveBeenCalledWith(going);
    });

    it('queues or discards every run, in the order listed', () => {
        const handlers = renderPanel();
        fireEvent.click(screen.getByRole('button', { name: 'Queue all' }));
        expect(handlers.onQueue).toHaveBeenCalledWith([1, 2]);
        fireEvent.click(screen.getByRole('button', { name: 'Discard all' }));
        expect(handlers.onDiscard).toHaveBeenCalledWith([1, 2]);
    });

    it('leaves the changes out before the schema has loaded', () => {
        renderPanel(false);
        expect(screen.queryByText(/Chamber pressure/)).toBeNull();
        expect(within(rows()[0]).getByText(/^NOVA closed while it ran/)).toBeTruthy();
    });
});
