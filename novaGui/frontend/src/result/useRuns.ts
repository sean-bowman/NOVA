/* ========================================
   KEPT RUNS
   The runs the server keeps (novaGui.session), which of them a window shows, the view index of
   that run, and the baseline the others are compared against.

   A window follows the latest run until a run is picked from the list, and Generate puts it back
   to following; a queued run that starts later leaves a picked run shown, so reading an earlier
   point of a sweep is not cut short as the next point starts. Following, it shows a run still going once that run's contour stage has settled
   the contour and the flow fields, and the latest finished run before then. A picked run that drops
   out of the server's list gives way to the latest.
   Sean Bowman [11/19/2026]
   ======================================== */

import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '../api';
import type { RunView } from '../run/useRunEvents';
import type { RunEntry, RunList, ViewIndex } from '../types';

export type RunChoice = number | 'latest';

export interface RunsView {
    list: RunList | null;
    choice: RunChoice;
    shown: number | null;          // the run the window shows
    partial: boolean;              // the shown run is still going
    index: ViewIndex | null;       // the shown run's views
    baseline: number | null;
    entry: (runId: number | null) => RunEntry | undefined;
    choose: (choice: RunChoice) => void;
    setBaseline: (runId: number | null) => void;
}

export function useRuns(run: RunView, initialChoice: RunChoice = 'latest',
                        onError?: (title: string, message: string) => void): RunsView {
    const [list, setList] = useState<RunList | null>(null);
    const [choice, setChoice] = useState<RunChoice>(initialChoice);
    const [index, setIndex] = useState<ViewIndex | null>(null);
    const listRequest = useRef(0);
    const indexRequest = useRef(0);
    const errorHandler = useRef(onError);
    errorHandler.current = onError;

    // -- The list follows every change the event stream reports -- //
    const partialKey = run.partial ? `${run.partial.runId}:${run.partial.views.join(',')}` : '';
    useEffect(() => {
        const request = ++listRequest.current;
        api.runs()
            .then((loaded) => request === listRequest.current && setList(loaded))
            .catch((failure: Error) => errorHandler.current?.('Runs unavailable', failure.message));
    }, [run.runsVersion, run.state, run.result, partialKey]);

    // -- The run shown -- //
    const running = list?.running ?? null;
    const settled = running ? (run.partial?.runId === running.runId ? run.partial.views : running.views) : [];
    const kept = (runId: number) => list?.runs.some((entry) => entry.runId === runId) ?? false;
    let shown: number | null = null;
    let partial = false;
    if (list) {
        if (choice !== 'latest' && kept(choice)) {
            shown = choice;
        } else if (running && settled.length > 0 && (choice === 'latest' || choice === running.runId)) {
            shown = running.runId;
            partial = true;
        } else {
            shown = list.latest;
        }
    }

    // -- Its view index, again whenever a running run settles more or finishes -- //
    const indexKey = list ? `${shown}|${partial}|${partial ? settled.join(',') : ''}` : '';
    useEffect(() => {
        if (!indexKey) {
            return;
        }
        const request = ++indexRequest.current;
        api.views(shown)
            .then((loaded) => request === indexRequest.current && setIndex(loaded))
            .catch((failure: Error) => errorHandler.current?.('Views unavailable', failure.message));
    }, [indexKey]);

    const entry = useCallback((runId: number | null) => list?.runs.find((candidate) => candidate.runId === runId),
        [list]);

    const setBaseline = useCallback((runId: number | null) => {
        api.setBaseline(runId).catch((failure: Error) => errorHandler.current?.('Baseline not set', failure.message));
    }, []);

    // An index for another run is held back until the shown run's own arrives
    const shownIndex = index && index.runId === shown && index.partial === partial ? index : null;

    return { list, choice, shown, partial, index: shownIndex, baseline: list?.baseline ?? null, entry, choose: setChoice,
             setBaseline };
}
