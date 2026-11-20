/* ========================================
   RUN EVENTS
   The run session as React state, fed by the server's event stream. The stream opens with a
   snapshot, so a reload or a reconnect mid-run picks up where the run is. Besides the run itself
   it carries the figures a running run has settled, how many passes its coolant circuit has
   kept (each one draws again in the circuit iteration view), the warnings it has raised, the runs queued
   behind it, a count that moves whenever the kept runs or the baseline change and one that moves
   whenever a trade sweep does, and the theme mode last saved from any window.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useEffect, useRef, useState } from 'react';

import { subscribeRunEvents } from '../api';
import type {
    Mode, PartialRun, QueueEntry, RunEvent, RunProgressFields, RunStage, RunStateName, RunSummary, RunWarning,
} from '../types';

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
    partial: PartialRun | null;   // the running run's settled figures
    iterationRevision: number;    // the circuit passes the running run has kept, which name its live figure
    warnings: RunWarning[];       // the warnings of the run in progress, or the last one started
    runsVersion: number;          // moves when the kept runs or the baseline change
    sweepsVersion: number;        // moves when a sweep is added or deleted, or a point's state moves
    queue: QueueEntry[];          // the runs waiting their turn, in order
    savedMode: Mode | null;       // the theme mode last saved from any window
}

const initial: RunView = {
    state: 'idle', detail: '', runId: null, fraction: 0, ceiling: 0, label: '', stageDetail: '', stages: [],
    expectedRun: null, runClock: 0, progressAt: 0, startedAt: null, endedAt: null, log: [], result: null,
    connected: false, partial: null, iterationRevision: 0, warnings: [], runsVersion: 0, sweepsVersion: 0, queue: [],
    savedMode: null,
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
                partial: event.partial ?? null, iterationRevision: event.partial?.revision ?? 0,
                warnings: event.warnings ?? [], runsVersion: previous.runsVersion + 1,
                sweepsVersion: previous.sweepsVersion + 1, queue: event.queue ?? [],
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
                        runClock: 0, log: [], partial: null, iterationRevision: 0, warnings: [],
                    }
                    : {}),
                ...(event.state !== 'running' && previous.state === 'running'
                    ? { endedAt: Date.now() / 1000, partial: null } : {}),
            };
        case 'progress':
            return { ...previous, ...progressOf(event) };
        case 'partial':
            return { ...previous, partial: { runId: event.runId, views: event.views } };
        case 'iterations':
            return event.runId === previous.runId ? { ...previous, iterationRevision: event.revision } : previous;
        case 'warning':
            return event.runId === previous.runId ? { ...previous, warnings: event.warnings } : previous;
        case 'result': {
            const { type: _type, ...summary } = event;
            return { ...previous, result: summary, partial: null };
        }
        case 'runs':
            return { ...previous, runsVersion: previous.runsVersion + 1 };
        case 'queue':
            return { ...previous, queue: event.queue };
        case 'sweeps':
            return { ...previous, sweepsVersion: previous.sweepsVersion + 1 };
        case 'settings':
            return { ...previous, savedMode: event.themeMode };
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
