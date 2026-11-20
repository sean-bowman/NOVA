/* ========================================
   RUN BAR
   Generate, Sweep and Cancel, the stage stepper, the run's elapsed time, the runs queued behind
   it, the count of the warnings the run has raised, and the buttons for the stage list and the
   run log; the log drawer sits above it. The warning count opens the log, where each warning sits
   among the output around it.

   During a run Generate becomes Queue: the form joins the queue and runs when the runs before it
   end. The queued count opens the queue, where a run can be taken out before it starts. With runs
   queued, Cancel asks whether to stop the run alone, so the queue goes on, or the queue with it.

   NOVA reports its progress as events (NOVA.progress), which the server folds into a stage tree
   (novaGui.progress.RunProgress). The stepper draws one segment per top-level stage of the run's
   plan, as wide as the time the stage is expected to take: its time on the last finished run, or
   a nominal time before the first. A segment fills with the stage's own loop where it reports
   one, else with its elapsed time against the expected time; the coolant circuit's segment is
   notched at each finished pass. The contour solve reports every few seconds and some stages only
   at their start and end, so the times advance on the run's clock between events.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

import { CloseIcon, PlayIcon, StopIcon, SweepIcon, WarningIcon } from '../components/Icons';
import type { QueueEntry, RunStage } from '../types';
import { StagePanel } from './StagePanel';
import { formatClock, runClockNow, runElapsed, shownState, stageElapsed, stageTime, type ShownState } from './stageText';
import { useTicker, type RunView } from './useRunEvents';

const fullBeforeDone = 0.95;    // [-] the most a running segment fills on time alone

interface RunBarProps {
    run: RunView;
    canGenerate: boolean;
    blockReason: string;
    logOpen: boolean;
    stagesOpen: boolean;
    onGenerate: () => void;
    onSweep: () => void;
    onCancel: (everything: boolean) => void;
    onUnqueue: (queueIds: number[]) => void;
    onToggleLog: () => void;
    onToggleStages: () => void;
}

/** A small panel above the run bar that closes on Escape or a click outside it. */
function Popover({ className, label, onClose, children }: { className: string; label: string; onClose: () => void; children: ReactNode }) {
    const box = useRef<HTMLDivElement>(null);
    useEffect(() => {
        const onDown = (event: MouseEvent) => {
            if (box.current && !box.current.contains(event.target as Node)) {
                onClose();
            }
        };
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                event.stopPropagation();
                onClose();
            }
        };
        // The click that opened the panel has finished by the time this listens
        const timer = window.setTimeout(() => document.addEventListener('mousedown', onDown), 0);
        document.addEventListener('keydown', onKey, true);
        return () => {
            window.clearTimeout(timer);
            document.removeEventListener('mousedown', onDown);
            document.removeEventListener('keydown', onKey, true);
        };
    }, [onClose]);
    return <div ref={box} className={`card run-popover ${className}`} role="dialog" aria-label={label}>{children}</div>;
}

function QueuePanel({ queue, onUnqueue, onClose }: { queue: QueueEntry[]; onUnqueue: (queueIds: number[]) => void; onClose: () => void }) {
    return (
        <Popover className="queue-panel" label="Run queue" onClose={onClose}>
            <div className="stage-panel-head">
                <span className="stage-panel-title">Queue</span>
                <span className="muted">{queue.length === 1 ? 'one run, after the run going' : `${queue.length} runs, in this order`}</span>
                <span className="toolbar-spacer" />
                <button type="button" className="button button-quiet button-small" onClick={() => onUnqueue(queue.map((entry) => entry.queueId))}
                        title="Take every run out of the queue; the run going carries on">
                    Clear
                </button>
                <button type="button" className="icon-button" aria-label="Close the queue" onClick={onClose}><CloseIcon /></button>
            </div>
            <ol className="queue-list">
                {queue.map((entry, place) => (
                    <li key={entry.queueId} className="queue-row">
                        <span className="queue-place">{place + 1}</span>
                        <span className="queue-label" title={entry.label}>
                            {entry.sweepId !== null && <SweepIcon />} {entry.label}
                        </span>
                        <button type="button" className="icon-button" aria-label={`Take ${entry.label} out of the queue`}
                                onClick={() => onUnqueue([entry.queueId])}>
                            <CloseIcon />
                        </button>
                    </li>
                ))}
            </ol>
        </Popover>
    );
}

/** [-] How full a segment is. */
function fillOf(stage: RunStage, state: ShownState, elapsed: number | null): number {
    if (state === 'done') {
        return 1;
    }
    if (state === 'pending' || elapsed === null) {
        return 0;
    }
    if (stage.fraction !== null) {
        return stage.fraction;
    }
    // Against the last run's time the fill is linear; against a nominal time, which can be far
    // off, it eases so a long first run never sits at the cap from its first seconds
    if (stage.expected !== null) {
        return Math.min(elapsed / stage.expected, fullBeforeDone);
    }
    return fullBeforeDone * (1 - Math.exp(-elapsed / stage.weight));
}

/** [%] Where the finished passes inside a stage fall along its segment. */
function notchesOf(stage: RunStage, state: ShownState, elapsed: number | null): number[] {
    if (stage.started === null || elapsed === null || elapsed <= 0) {
        return [];
    }
    const span = state === 'done' ? elapsed : Math.max(stage.expected ?? stage.weight, elapsed);
    const passes = [stage, ...stage.children].filter((node) => node.iterationName === 'pass')
        .flatMap((node) => node.iterations);
    return passes.map((iteration) => (100 * (iteration.t - stage.started!)) / span)
        .filter((left) => left > 0.5 && left < 99);
}

function Stepper({ run, clock }: { run: RunView; clock: number }) {
    if (run.stages.length === 0) {
        return (
            <div className="stepper stepper-empty">
                {run.state === 'running'
                    ? <><span className="spinner" /> {run.label || 'starting'}</>
                    : 'Generate runs the form as it stands.'}
            </div>
        );
    }
    return (
        <ol className="stepper" aria-label="Run stages">
            {run.stages.map((stage) => {
                const state = shownState(stage, run);
                const elapsed = stageElapsed(stage, clock);
                const time = stageTime(stage, state, elapsed);
                const note = state === 'pending' ? '' : stage.note;
                const fill = fillOf(stage, state, elapsed);
                return (
                    <li key={stage.key} className={`stage-step is-${state}`} style={{ flexGrow: stage.weight }}
                        title={[stage.label, note, time].filter(Boolean).join(', ')}>
                        <div className="stage-step-head">
                            <span className="stage-step-label">
                                {stage.label}
                                {note && <span className="stage-step-note"> · {note}</span>}
                            </span>
                            <span className="stage-step-time">{time}</span>
                        </div>
                        <div className="stage-step-track">
                            <div className="stage-step-fill" style={{ width: `${(100 * fill).toFixed(1)}%` }} />
                            {notchesOf(stage, state, elapsed).map((left) => (
                                <span key={left} className="stage-step-notch" style={{ left: `${left.toFixed(2)}%` }} />
                            ))}
                        </div>
                    </li>
                );
            })}
        </ol>
    );
}

export function RunBar({ run, canGenerate, blockReason, logOpen, stagesOpen, onGenerate, onSweep, onCancel, onUnqueue,
                         onToggleLog, onToggleStages }: RunBarProps) {
    const running = run.state === 'running';
    const [queueOpen, setQueueOpen] = useState(false);
    const [cancelOpen, setCancelOpen] = useState(false);
    const queued = run.queue.length;
    const closeQueue = useCallback(() => setQueueOpen(false), []);
    const closeCancel = useCallback(() => setCancelOpen(false), []);

    useEffect(() => {
        if (queued === 0) {
            setQueueOpen(false);
            setCancelOpen(false);
        }
    }, [queued]);
    useEffect(() => {
        if (!running) {
            setCancelOpen(false);
        }
    }, [running]);
    const now = useTicker(running);
    const clock = runClockNow(run, now);

    // The whole run's time against the last run's, once every stage has one to expect
    const expectedTotal = run.stages.length > 0 && run.stages.every((stage) => stage.expected !== null)
        ? run.stages.reduce((sum, stage) => sum + (stage.expected ?? 0), 0) : null;

    const elapsed = runElapsed(run);
    const clockMain = elapsed !== null ? formatClock(elapsed) : '';
    let clockSub = '';
    if (running) {
        clockSub = expectedTotal !== null ? `of ~${formatClock(expectedTotal)} (run ${run.expectedRun})` : `run ${run.runId ?? ''}`;
    } else if (run.state === 'done') {
        clockSub = `run ${run.runId}, done`;
    } else if (run.state === 'error') {
        clockSub = `run ${run.runId} failed`;
    } else if (run.state === 'cancelled') {
        clockSub = `run ${run.runId} cancelled`;
    }

    return (
        <div className={`run-bar state-${run.state}`}>
            {running && (
                <button type="button" className="button button-danger" aria-expanded={queued > 0 ? cancelOpen : undefined}
                        onClick={() => (queued > 0 ? setCancelOpen((open) => !open) : onCancel(false))}
                        title={queued > 0 ? 'Stop the run, or the run and the queue' : 'Stop the run'}>
                    <StopIcon /> Cancel
                </button>
            )}
            <button type="button" className={`button ${running ? '' : 'button-primary'}`} onClick={onGenerate} disabled={!canGenerate}
                    title={canGenerate ? (running ? 'Queue the form: it runs when the runs before it end  Ctrl+R' : 'Generate the nozzle  Ctrl+R')
                                       : blockReason}>
                <PlayIcon /> {running ? 'Queue' : 'Generate'}
            </button>
            <button type="button" className="button" onClick={onSweep} disabled={!run.connected}
                    title="A trade sweep: one run per value of a field, or of two fields against each other">
                <SweepIcon /> Sweep
            </button>
            <Stepper run={run} clock={clock} />
            <div className="run-clock">
                <span className="run-clock-main">{clockMain}</span>
                <span className="run-clock-sub">{clockSub}</span>
            </div>
            {run.warnings.length > 0 && (
                <button type="button" className="button button-quiet run-warnings" onClick={onToggleLog}
                        title={run.warnings.map((warning) => `${warning.message} (${warning.where}${warning.count > 1 ? `, ${warning.count} times` : ''})`).join('\n')}>
                    <WarningIcon /> {run.warnings.length === 1 ? '1 warning' : `${run.warnings.length} warnings`}
                </button>
            )}
            {queued > 0 && (
                <button type="button" className={`button button-quiet run-queued ${queueOpen ? 'is-pressed' : ''}`}
                        aria-expanded={queueOpen} onClick={() => setQueueOpen((open) => !open)}
                        title={run.queue.map((entry, place) => `${place + 1}. ${entry.label}`).join('\n')}>
                    {queued} queued
                </button>
            )}
            {!run.connected && <span className="badge badge-error" title="The NOVA server is not answering">offline</span>}
            <button type="button" className={`button ${stagesOpen ? 'is-pressed' : ''}`} onClick={onToggleStages}
                    aria-expanded={stagesOpen} disabled={run.stages.length === 0} title="Every stage of the run, with its time">
                Stages
            </button>
            <button type="button" className="button button-quiet" onClick={onToggleLog} aria-expanded={logOpen}>
                {logOpen ? 'Hide log' : 'Show log'}
            </button>
            {stagesOpen && run.stages.length > 0 && <StagePanel run={run} clock={clock} onClose={onToggleStages} />}
            {queueOpen && queued > 0 && <QueuePanel queue={run.queue} onUnqueue={onUnqueue} onClose={closeQueue} />}
            {cancelOpen && running && queued > 0 && (
                <Popover className="cancel-menu" label="Cancel" onClose={closeCancel}>
                    <button type="button" className="cancel-choice" onClick={() => {
                        setCancelOpen(false);
                        onCancel(false);
                    }}>
                        <strong>Cancel run {run.runId}</strong>
                        <span className="muted">The queue goes on with its next run.</span>
                    </button>
                    <button type="button" className="cancel-choice" onClick={() => {
                        setCancelOpen(false);
                        onCancel(true);
                    }}>
                        <strong>Cancel run {run.runId} and the {queued} queued</strong>
                        <span className="muted">Nothing runs after it; a sweep's points read not run.</span>
                    </button>
                </Popover>
            )}
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
