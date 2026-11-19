/* ========================================
   STAGE LIST
   Every stage of the run, opened from the run bar: each top-level stage with its time, the
   stages inside it, and the passes of a convergent loop with the values each pass reports. A
   coolant circuit lists each pass with its two legs' outlet temperatures and the up leg's change,
   so the list shows the circuit settling where the stepper shows only the pass count.

   Before this run reaches them, the stages the last finished run took are listed as pending with
   that run's times. Iterations named anything but 'pass' (the contour solve's evaluations) are
   too many to list; their stage shows the count and the latest values instead.
   Sean Bowman [11/19/2026]
   ======================================== */

import { CloseIcon, StageStateIcon } from '../components/Icons';
import type { StageNode } from '../types';
import {
    formatClock, formatDuration, metricsText, plural, runElapsed, shownState, stageElapsed, stageTime, type ShownState,
} from './stageText';
import type { RunView } from './useRunEvents';

interface Row {
    key: string;
    level: 0 | 1 | 2;
    state: ShownState | null;       // null: a note, drawn without an icon
    label: string;
    detail: string;
    time: string;
}

function capitalized(text: string): string {
    return text.charAt(0).toUpperCase() + text.slice(1);
}

/** A sub-stage's rows: itself, then for a loop of passes each finished pass and the one running. */
function childRows(child: StageNode, parentKey: string, run: RunView, clock: number): Row[] {
    const state = shownState(child, run);
    const elapsed = stageElapsed(child, clock);
    const key = `${parentKey}.${child.key}`;
    const passes = child.iterationName === 'pass';
    const last = child.iterations[child.iterations.length - 1];

    let detail = '';
    if (state === 'running' && !passes) {
        detail = child.detail;
    } else if (state !== 'pending' && !passes && child.iterationName && child.iterationCount > 0) {
        detail = `${child.iterationCount} ${plural(child.iterationName, child.iterationCount)}`;
        if (last && metricsText(last.metrics)) {
            detail += `, ${metricsText(last.metrics)}`;
        }
    }
    const rows: Row[] = [{ key, level: 1, state, label: child.label, detail, time: stageTime(child, state, elapsed) }];
    if (!passes) {
        return rows;
    }

    let previous: number | null = child.started;
    child.iterations.forEach((iteration, position) => {
        // A pass's time runs from the end of the one before; the first kept pass of a long loop has none
        const from = position > 0 || iteration.index === 1 ? previous : null;
        rows.push({
            key: `${key}#${iteration.index}`, level: 2, state: 'done', label: `${capitalized(child.iterationName!)} ${iteration.index}`,
            detail: metricsText(iteration.metrics), time: from !== null ? formatDuration(iteration.t - from) : '',
        });
        previous = iteration.t;
    });
    if (state === 'running' || state === 'cancelled' || state === 'failed') {
        const lastEnd = last ? last.t : child.started;
        rows.push({
            key: `${key}#next`, level: 2, state, label: `${capitalized(child.iterationName!)} ${child.iterationCount + 1}`,
            detail: state === 'running' ? child.detail : '',
            time: lastEnd !== null ? formatDuration(Math.max(0, clock - lastEnd)) : '',
        });
    }
    if (state === 'running' && child.expectedIterations !== null && run.expectedRun !== null) {
        rows.push({
            key: `${key}#expected`, level: 2, state: null, detail: '', time: '',
            label: `Run ${run.expectedRun} took ${child.expectedIterations} ${plural(child.iterationName!, child.expectedIterations)}.`,
        });
    }
    return rows;
}

export function StagePanel({ run, clock, onClose }: { run: RunView; clock: number; onClose: () => void }) {
    const rows: Row[] = [];
    for (const stage of run.stages) {
        const state = shownState(stage, run);
        rows.push({
            key: stage.key, level: 0, state, label: stage.label, detail: state === 'pending' ? '' : stage.note,
            time: stageTime(stage, state, stageElapsed(stage, clock)),
        });
        for (const child of stage.children) {
            rows.push(...childRows(child, stage.key, run, clock));
        }
    }

    // The caption reads the run bar's clock, which counts from Generate
    const elapsed = runElapsed(run);
    const at = elapsed !== null ? formatClock(elapsed) : '';
    let caption = `run ${run.runId ?? ''}`;
    if (run.state === 'running') {
        caption += `, ${at} elapsed`;
    } else if (run.state === 'done') {
        caption += `, ${at} total`;
    } else if (run.state === 'cancelled') {
        caption += `, cancelled at ${at}`;
    } else if (run.state === 'error') {
        caption += `, failed at ${at}`;
    }

    // Where the expected times come from; before any run has finished, the first run says so
    let foot = '';
    if (run.expectedRun !== null) {
        foot = `Expected times come from run ${run.expectedRun}, the last that finished.`;
    } else if (run.state === 'running') {
        foot = 'Expected times appear once a run has finished.';
    }

    return (
        <div className="stage-panel card" role="dialog" aria-label="Run stages">
            <div className="stage-panel-head">
                <span className="stage-panel-title">Stages</span>
                <span className="muted">{caption}</span>
                <span className="toolbar-spacer" />
                <button type="button" className="icon-button" aria-label="Close the stage list" onClick={onClose}>
                    <CloseIcon />
                </button>
            </div>
            <ul className="stage-rows">
                {rows.map((row) => (
                    <li key={row.key} className={`stage-row level-${row.level} ${row.state ? `is-${row.state}` : 'is-note'}`}>
                        <span className="stage-row-icon">{row.state && <StageStateIcon state={row.state} />}</span>
                        <span className="stage-row-text">
                            <span className="stage-row-label">{row.label}</span>
                            {row.detail && <span className="stage-row-detail">{row.detail}</span>}
                        </span>
                        <span className="stage-row-time">{row.time}</span>
                    </li>
                ))}
            </ul>
            {foot && <p className="stage-panel-foot">{foot}</p>}
        </div>
    );
}
