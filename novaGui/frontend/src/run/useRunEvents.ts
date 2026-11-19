/* ========================================
   RUN EVENTS
   The run session as React state, fed by the server's event stream. The stream opens with a
   snapshot, so a reload or a reconnect mid-run picks up where the run is.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useEffect, useRef, useState } from 'react';

import { subscribeRunEvents } from '../api';
import type { RunEvent, RunProgressFields, RunStage, RunStateName, RunSummary } from '../types';

const maxLogLines = 4000;

export interface RunView {
    state: RunStateName;
    detail: string;
    runId: number | null;         // the run in progress, or the last one started
    fraction: number;
    ceiling: number;
    label: string;
    stageDetail: string;          // every open stage, with its iteration or loop
    stages: RunStage[];
    expectedRun: number | null;   // the run whose stage times the stages expect
    runClock: number;             // [s] the run's own clock at the last progress event
    progressAt: number;           // [ms] client clock at the last progress event
    startedAt: number | null;     // [s] server clock, epoch
    endedAt: number | null;       // [s] client clock, epoch, when this window saw the run end
    log: string[];
    result: RunSummary | null;
    connected: boolean;
}

const initial: RunView = {
    state: 'idle', detail: '', runId: null, fraction: 0, ceiling: 0, label: '', stageDetail: '', stages: [],
    expectedRun: null, runClock: 0, progressAt: 0, startedAt: null, endedAt: null, log: [], result: null,
    connected: false,
};

function progressOf(event: RunProgressFields): Partial<RunView> {
    return {
        runId: event.runId, fraction: event.fraction, ceiling: event.ceiling, label: event.label,
        stageDetail: event.stageDetail ?? '', stages: event.stages ?? [], expectedRun: event.expectedRun ?? null,
        runClock: event.t ?? 0, progressAt: performance.now(),
    };
}

function reduce(previous: RunView, event: RunEvent): RunView {
    switch (event.type) {
        case 'snapshot':
            return {
                ...previous, ...progressOf(event), state: event.state, detail: event.detail,
                startedAt: event.startedAt, endedAt: null, log: event.log.slice(-maxLogLines), result: event.result,
            };
        case 'log': {
            const log = previous.log.length >= maxLogLines ? previous.log.slice(1 - maxLogLines) : previous.log.slice();
            log.push(event.line);
            return { ...previous, log };
        }
        case 'status':
            return {
                ...previous, state: event.state, detail: event.detail, runId: event.runId ?? previous.runId,
                ...(event.state === 'running' && previous.state !== 'running'
                    ? {
                        startedAt: Date.now() / 1000, endedAt: null, fraction: 0, ceiling: 0, label: '', stages: [],
                        runClock: 0, log: [],
                    }
                    : {}),
                ...(event.state !== 'running' && previous.state === 'running' ? { endedAt: Date.now() / 1000 } : {}),
            };
        case 'progress':
            return { ...previous, ...progressOf(event) };
        case 'result': {
            const { type: _type, ...summary } = event;
            return { ...previous, result: summary };
        }
        default:
            return previous;
    }
}

/**
 * The run session's state, and a callback for each finished run.
 */
export function useRunEvents(onResult: (result: RunSummary) => void): RunView {
    const [run, setRun] = useState<RunView>(initial);
    const resultHandler = useRef(onResult);
    resultHandler.current = onResult;

    useEffect(() => subscribeRunEvents(
        (event) => {
            setRun((previous) => reduce(previous, event));
            if (event.type === 'result') {
                const { type: _type, ...summary } = event;
                resultHandler.current(summary);
            }
        },
        (open) => setRun((previous) => ({ ...previous, connected: open })),
    ), []);

    return run;
}

/**
 * A clock that ticks while `running`, for the elapsed times a run bar shows between events.
 */
export function useTicker(running: boolean, periodMs = 250): number {
    const [now, setNow] = useState(() => performance.now());
    useEffect(() => {
        if (!running) {
            return;
        }
        const timer = window.setInterval(() => setNow(performance.now()), periodMs);
        return () => window.clearInterval(timer);
    }, [running, periodMs]);
    return now;
}
