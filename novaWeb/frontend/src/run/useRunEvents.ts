/* ========================================
   RUN EVENTS
   The run session as React state, fed by the server's event stream. The stream opens with a
   snapshot, so a reload or a reconnect mid-run picks up where the run is.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useEffect, useRef, useState } from 'react';

import { subscribeRunEvents } from '../api';
import type { RunEvent, RunStage, RunStateName, RunSummary } from '../types';

const maxLogLines = 4000;

export interface RunView {
    state: RunStateName;
    detail: string;
    fraction: number;
    ceiling: number;
    label: string;
    stageDetail: string;          // every open stage, with its iteration or loop
    stages: RunStage[];
    progressAt: number;           // [ms] client clock at the last progress event
    startedAt: number | null;     // [s] server clock, epoch
    log: string[];
    result: RunSummary | null;
    connected: boolean;
}

const initial: RunView = {
    state: 'idle', detail: '', fraction: 0, ceiling: 0, label: '', stageDetail: '', stages: [], progressAt: 0, startedAt: null,
    log: [], result: null, connected: false,
};

function reduce(previous: RunView, event: RunEvent): RunView {
    switch (event.type) {
        case 'snapshot':
            return {
                ...previous, state: event.state, detail: event.detail, fraction: event.fraction, ceiling: event.ceiling,
                label: event.label, stageDetail: event.stageDetail ?? '', stages: event.stages ?? [],
                progressAt: performance.now(), startedAt: event.startedAt, log: event.log.slice(-maxLogLines),
                result: event.result,
            };
        case 'log': {
            const log = previous.log.length >= maxLogLines ? previous.log.slice(1 - maxLogLines) : previous.log.slice();
            log.push(event.line);
            return { ...previous, log };
        }
        case 'status':
            return {
                ...previous, state: event.state, detail: event.detail,
                ...(event.state === 'running' && previous.state !== 'running'
                    ? { startedAt: Date.now() / 1000, fraction: 0, ceiling: 0, label: '', log: [] } : {}),
            };
        case 'progress':
            return {
                ...previous, fraction: event.fraction, ceiling: event.ceiling, label: event.label,
                stageDetail: event.stageDetail ?? '', stages: event.stages ?? [], progressAt: performance.now(),
            };
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
