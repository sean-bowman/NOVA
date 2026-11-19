/* ========================================
   POP-OUT FIGURE WINDOW
   Figures in a window of their own, for a second monitor: the page the result pane's Pop out
   opens, at /?popout=figure&run=&layout=&views=. It shows one view or the grid, with the same
   axial cursor and the same baseline as the main window, and follows the latest run or keeps to
   the run it was opened on. It listens to the same event stream, so a finished run, a new
   baseline or a theme switched in the main window reach it.
   Sean Bowman [11/19/2026]
   ======================================== */

import { useCallback, useEffect, useState } from 'react';

import { useRuns, type RunChoice } from './result/useRuns';
import { RunSelect } from './result/RunSelect';
import { useRunEvents } from './run/useRunEvents';
import type { Mode } from './types';
import { FigureView, type FigureLayout } from './view/FigureView';

interface Toast {
    id: number;
    title: string;
    body: string;
}

export function popoutParams(): { run: RunChoice; layout: FigureLayout; views: string[] } | null {
    const params = new URLSearchParams(window.location.search);
    if (params.get('popout') !== 'figure') {
        return null;
    }
    const run = params.get('run');
    const views = (params.get('views') ?? '').split(',').filter(Boolean);
    return {
        run: run && run !== 'latest' && Number.isFinite(Number(run)) ? Number(run) : 'latest',
        layout: params.get('layout') === 'grid' ? 'grid' : 'single',
        views,
    };
}

export function Popout({ initial }: { initial: { run: RunChoice; layout: FigureLayout; views: string[] } }) {
    const [mode, setMode] = useState<Mode>(() => (document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'));
    const [selected, setSelected] = useState(initial.views[0] ?? 'contour');
    const [layout, setLayout] = useState<FigureLayout>(initial.layout);
    const [toast, setToast] = useState<Toast | null>(null);

    const notify = useCallback((_kind: 'info' | 'error', title: string, body = '') => {
        setToast({ id: Date.now(), title, body });
    }, []);

    const run = useRunEvents(() => undefined);
    const runs = useRuns(run, initial.run, (title, message) => notify('error', title, message));
    const against = runs.baseline !== null && runs.baseline !== runs.shown && !runs.partial ? runs.baseline : null;

    // The theme follows a switch in the main window
    useEffect(() => {
        if (run.savedMode && run.savedMode !== mode) {
            document.documentElement.dataset.theme = run.savedMode;
            setMode(run.savedMode);
        }
    }, [run.savedMode, mode]);

    useEffect(() => {
        const label = runs.index?.views.find((spec) => spec.key === selected)?.label;
        document.title = ['NOVA', layout === 'grid' ? 'Grid' : label, runs.shown !== null ? `run ${runs.shown}` : '']
            .filter(Boolean).join(' -- ');
    }, [runs.index, runs.shown, selected, layout]);

    return (
        <div className="app popout">
            <header className="app-header popout-header">
                <span className="wordmark wordmark-small">NOVA</span>
                <RunSelect runs={runs} />
                {against !== null && <span className="muted">dashed: run {against}, the baseline</span>}
                <span className="toolbar-spacer" />
                {!run.connected && <span className="badge badge-error" title="The NOVA server is not answering">offline</span>}
            </header>
            <main className="popout-body card">
                <FigureView index={runs.index} mode={mode} compare={against} selected={selected} layout={layout}
                            runChoice={runs.choice} initialGrid={initial.layout === 'grid' ? initial.views : undefined}
                            onSelect={setSelected} onLayout={setLayout} onNotify={notify} />
            </main>
            {toast && (
                <div className="toasts" aria-live="polite">
                    <div className="toast toast-error">
                        <div className="toast-title">{toast.title}</div>
                        {toast.body && <div className="toast-body">{toast.body}</div>}
                        <button type="button" className="toast-close" aria-label="Dismiss" onClick={() => setToast(null)}>&times;</button>
                    </div>
                </div>
            )}
        </div>
    );
}
