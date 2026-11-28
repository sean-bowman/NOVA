/* ========================================
   PASS PICKER TESTS
   The figure view's Pass picker (src/view/FigureView.tsx): which pass of the coolant the jacket
   views draw, the pass the jacket reports until another is picked, and when the picker shows.
   The figures themselves are stood in for, so only the pass each is handed is read.
   Sean Bowman [11/27/2026]
   ======================================== */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { CoolantPass, ViewIndex, ViewSpec } from '../src/types';
import { FigureView } from '../src/view/FigureView';

vi.mock('../src/view/PlotlyFigure', () => ({
    PlotlyFigure: ({ viewKey, pass }: { viewKey: string; pass?: string | null }) => (
        <div data-testid="figure" data-view={viewKey} data-pass={pass ?? ''} />
    ),
}));

function spec(key: string, label: string, byPass: boolean): ViewSpec {
    return { key, group: byPass ? 'Cooling' : 'Contour', label, source: '', interactive: true, static: true,
             comparable: true, byPass };
}

const views = [spec('contour', 'Computed contour', false), spec('jacketTemperatures', 'Temperatures', true),
               spec('heatFlux', 'Heat flux', true)];
const multiPass: CoolantPass[] = [{ key: 'jacketDown', label: 'Jacket, down pass' }, { key: 'jacketUp', label: 'Jacket, up pass' }];

function indexOf(passes: CoolantPass[], defaultPass: string | null, runId = 3): ViewIndex {
    return { views, available: views.map((entry) => entry.key), runId, runName: 'NOVANozzle', elapsedSec: 1.0,
             config: null, partial: false, loadError: '', passes, defaultPass };
}

function shown(index: ViewIndex, selected: string) {
    return (
        <FigureView index={index} mode="dark" compare={null} selected={selected} layout="single" runChoice="latest"
                    onSelect={() => undefined} onLayout={() => undefined} onNotify={() => undefined} />
    );
}

const passDrawn = () => screen.getByTestId('figure').getAttribute('data-pass');

describe('the pass picker', () => {
    it('draws the pass the jacket reports until another is picked', () => {
        render(shown(indexOf(multiPass, 'jacketUp'), 'jacketTemperatures'));
        const picker = screen.getByLabelText('Pass') as HTMLSelectElement;
        expect(Array.from(picker.options).map((option) => option.text)).toEqual(['Jacket, down pass', 'Jacket, up pass']);
        expect(picker.value).toBe('jacketUp');
        expect(passDrawn()).toBe('jacketUp');

        fireEvent.change(picker, { target: { value: 'jacketDown' } });
        expect(passDrawn()).toBe('jacketDown');
    });

    it('hands a view that draws no pass none, and shows no picker beside it', () => {
        render(shown(indexOf(multiPass, 'jacketUp'), 'contour'));
        expect(screen.queryByLabelText('Pass')).toBeNull();
        expect(passDrawn()).toBe('');
    });

    it('shows no picker for a run with one pass', () => {
        render(shown(indexOf([{ key: 'jacket', label: 'Jacket' }], 'jacket'), 'heatFlux'));
        expect(screen.queryByLabelText('Pass')).toBeNull();
        expect(passDrawn()).toBe('jacket');
    });

    it('draws the jacket\'s own pass on a run without the pass picked, and the pick again on a run with it', () => {
        const { rerender } = render(shown(indexOf(multiPass, 'jacketUp'), 'heatFlux'));
        fireEvent.change(screen.getByLabelText('Pass'), { target: { value: 'jacketDown' } });

        const withExtension = [{ key: 'jacket', label: 'Jacket' }, { key: 'extension', label: 'Extension circuit' }];
        rerender(shown(indexOf(withExtension, 'jacket', 2), 'heatFlux'));
        expect(passDrawn()).toBe('jacket');
        expect((screen.getByLabelText('Pass') as HTMLSelectElement).value).toBe('jacket');

        rerender(shown(indexOf(multiPass, 'jacketUp', 3), 'heatFlux'));
        expect(passDrawn()).toBe('jacketDown');
    });
});
