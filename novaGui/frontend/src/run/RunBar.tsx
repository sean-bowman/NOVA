/* ========================================
   RUN BAR
   Generate and Cancel, the current stage, a determinate progress bar, elapsed time, the
   latest output line, and the run log drawer above it.

   NOVA reports its progress as events (NOVA.progress), which the server folds into a fraction,
   the running stage's ceiling and a label. The contour solve reports every few seconds and some
   stages only at their start and end, so between events the bar eases toward the ceiling and a
   long stage reads as working rather than hung.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useEffect, useRef, useState } from 'react';

import { PlayIcon, StopIcon } from '../components/Icons';
import type { RunView } from './useRunEvents';

const creepTimeSec = 12;        // [s] time constant of the ease toward the stage ceiling

interface RunBarProps {
    run: RunView;
    canGenerate: boolean;
    blockReason: string;
    logOpen: boolean;
    onGenerate: () => void;
    onCancel: () => void;
    onToggleLog: () => void;
}

function formatElapsed(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const rest = Math.floor(seconds % 60);
    return `${minutes}:${String(rest).padStart(2, '0')}`;
}

export function RunBar({ run, canGenerate, blockReason, logOpen, onGenerate, onCancel, onToggleLog }: RunBarProps) {
    const running = run.state === 'running';
    const [now, setNow] = useState(() => performance.now());

    useEffect(() => {
        if (!running) {
            return;
        }
        const timer = window.setInterval(() => setNow(performance.now()), 200);
        return () => window.clearInterval(timer);
    }, [running]);

    let shown = run.fraction;
    if (running && run.ceiling > run.fraction) {
        const waited = Math.max(0, now - run.progressAt) / 1000;
        shown = run.fraction + (run.ceiling - run.fraction) * (1 - Math.exp(-waited / creepTimeSec));
    } else if (run.state === 'done') {
        shown = 1;
    }

    const elapsed = running && run.startedAt ? Math.max(0, Date.now() / 1000 - run.startedAt) : null;
    const latest = run.log.length > 0 ? run.log[run.log.length - 1] : '';

    let stage = 'Ready';
    if (running) {
        stage = run.label || run.detail || 'running';
    } else if (run.state === 'done') {
        stage = `Done in ${run.detail}`;
    } else if (run.state === 'error') {
        stage = 'Run failed';
    } else if (run.state === 'cancelled') {
        stage = 'Cancelled';
    }

    return (
        <div className={`run-bar state-${run.state}`}>
            {running ? (
                <button type="button" className="button button-danger" onClick={onCancel} title="Stop the run">
                    <StopIcon /> Cancel
                </button>
            ) : (
                <button type="button" className="button button-primary" onClick={onGenerate} disabled={!canGenerate}
                        title={canGenerate ? 'Generate the nozzle  Ctrl+R' : blockReason}>
                    <PlayIcon /> Generate
                </button>
            )}
            <div className="run-stage" title={running && run.stageDetail ? run.stageDetail : undefined}>{stage}</div>
            <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100}
                 aria-valuenow={Math.round(shown * 100)}>
                <div className="progress-fill" style={{ width: `${(shown * 100).toFixed(1)}%` }} />
            </div>
            <div className="run-elapsed">{elapsed !== null ? formatElapsed(elapsed) : ''}</div>
            <div className="run-latest" title={latest}>{run.state === 'error' ? run.detail : latest}</div>
            {!run.connected && <span className="badge badge-error" title="The NOVA server is not answering">offline</span>}
            <button type="button" className="button button-quiet" onClick={onToggleLog} aria-expanded={logOpen}>
                {logOpen ? 'Hide log' : 'Show log'}
            </button>
        </div>
    );
}

export function LogDrawer({ lines }: { lines: string[] }) {
    const box = useRef<HTMLPreElement>(null);
    const pinned = useRef(true);

    // Follow new output while the view is at the bottom; leave it where the user scrolled otherwise
    useEffect(() => {
        const element = box.current;
        if (element && pinned.current) {
            element.scrollTop = element.scrollHeight;
        }
    }, [lines]);

    return (
        <pre ref={box} className="log-drawer" onScroll={(event) => {
            const element = event.currentTarget;
            pinned.current = element.scrollHeight - element.scrollTop - element.clientHeight < 24;
        }}>
            {lines.length > 0 ? lines.join('\n') : 'No output yet.'}
        </pre>
    );
}
