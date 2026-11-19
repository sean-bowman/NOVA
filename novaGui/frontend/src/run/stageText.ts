/* ========================================
   STAGE TEXT
   Times and words for the stage stepper and the stage list: a stage's state as shown, its
   elapsed time on the run's clock between events, its time text, and an iteration's metrics.
   Sean Bowman [11/19/2026]
   ======================================== */

import type { StageNode, StageState } from '../types';
import type { RunView } from './useRunEvents';

/** A stage's state as shown: a stage left running by a run that ended was cut short. */
export type ShownState = StageState | 'cancelled';

/** m:ss */
export function formatClock(seconds: number): string {
    const whole = Math.max(0, Math.floor(seconds));
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

/** A stage's duration: '<0.1 s' and '12.3 s' under a minute, m:ss above. */
export function formatDuration(seconds: number): string {
    if (seconds < 0.1) {
        return '<0.1 s';
    }
    if (seconds < 60) {
        return `${seconds.toFixed(1)} s`;
    }
    return formatClock(seconds);
}

export function plural(name: string, count: number): string {
    if (count === 1) {
        return name;
    }
    return name.endsWith('s') ? `${name}es` : `${name}s`;
}

/** The run's own clock [s] now: the last event's time, advanced by the wall time since while running. */
export function runClockNow(run: RunView, now: number): number {
    if (run.state !== 'running') {
        return run.runClock;
    }
    return run.runClock + Math.max(0, now - run.progressAt) / 1000;
}

export function shownState(stage: StageNode, run: RunView): ShownState {
    if (stage.state === 'running' && run.state !== 'running') {
        return run.state === 'cancelled' ? 'cancelled' : 'failed';
    }
    return stage.state;
}

/** [s] how long a stage ran or has run so far, or null before it starts. */
export function stageElapsed(stage: StageNode, clock: number): number | null {
    if (stage.elapsed !== null) {
        return stage.elapsed;
    }
    if (stage.started === null) {
        return null;
    }
    return Math.max(0, clock - stage.started);
}

/** An expected time: '~52.0 s', and '<0.1 s' alone, which is already an estimate. */
function expectedText(seconds: number): string {
    return seconds < 0.1 ? formatDuration(seconds) : `~${formatDuration(seconds)}`;
}

/** '52.0 s' done, '1:10 / ~0:52' running against the last run, '~52.0 s' pending. */
export function stageTime(stage: StageNode, state: ShownState, elapsed: number | null): string {
    if (state === 'pending') {
        return stage.expected !== null ? expectedText(stage.expected) : '';
    }
    if (elapsed === null) {
        return '';
    }
    if (state === 'running' && stage.expected !== null) {
        return `${formatDuration(elapsed)} / ${expectedText(stage.expected)}`;
    }
    return formatDuration(elapsed);
}

/**
 * [s] The run's time on the wall clock, from Generate: the time waited, worker start included.
 * Running, it counts on; finished, it is the run's own figure; cut short, it stops where the run
 * ended, or at the run's last event when the window opened after it ended.
 */
export function runElapsed(run: RunView): number | null {
    if (run.state === 'running') {
        return run.startedAt !== null ? Math.max(0, Date.now() / 1000 - run.startedAt) : null;
    }
    if (run.state === 'done') {
        return run.result ? run.result.elapsedSec : null;
    }
    if (run.state === 'cancelled' || run.state === 'error') {
        return run.endedAt !== null && run.startedAt !== null ? run.endedAt - run.startedAt : run.runClock;
    }
    return null;
}

function small(value: number): string {
    const size = Math.abs(value);
    if (size >= 10) {
        return value.toFixed(1);
    }
    if (size >= 0.1) {
        return value.toFixed(2);
    }
    return value.toPrecision(2);
}

// The metrics NOVA's iterative solves report (NOVA.progress.iteration), SI. The coolant circuit
// sends its two legs' outlet temperatures and the up leg's largest change, Ievlev's gas side the
// wall temperature's largest change, the contour solve its design Mach number and residual.
const metricWords: Record<string, ((value: number) => string) | null> = {
    downOutletTemperature: (value) => `down outlet ${value.toFixed(1)} K`,
    upOutletTemperature: (value) => `up outlet ${value.toFixed(1)} K`,
    change: (value) => `change ${small(value)} K`,
    designMach: (value) => `design Mach ${value.toFixed(4)}`,
    residual: (value) => `residual ${value.toExponential(2)}`,
    tolerance: null,
};

/** An iteration's metrics as text: 'down outlet 94.9 K · up outlet 257.0 K · change 0.03 K'. */
export function metricsText(metrics: Record<string, number | null>): string {
    const parts: string[] = [];
    for (const [key, value] of Object.entries(metrics)) {
        if (value === null || !Number.isFinite(value)) {
            continue;
        }
        const words = key in metricWords ? metricWords[key] : (number: number) => `${key} ${Number(number.toPrecision(4))}`;
        if (words) {
            parts.push(words(value));
        }
    }
    return parts.join(' · ');
}
