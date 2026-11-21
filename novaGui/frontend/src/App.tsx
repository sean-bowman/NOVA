/* ========================================
   NOVA APP
   The window: header (plume mark, wordmark, Load config, theme switch, About), the Design form
   and the result pane side by side with a splitter between them, and the run bar with its stage
   stepper. The config lives here in backend values (SI), so the form edits it and the run bar
   sends it as it stands. An entry that does not parse blocks a run; a cross-field problem asks
   first. Generate during a run queues the form behind it, and
   Sweep queues a trade sweep (SweepDialog), which then opens in the result pane's Sweep view.

   The form's width is dragged on the splitter, or moved with the arrow keys on it, and is kept
   between launches with the theme mode (novaGui.settings). A double click returns it to the
   default. Below a narrow window width the form and the pane stack instead. A theme mode saved
   from a popped-out figure window switches this window too.
   Sean Bowman [11/16/2026]
   ======================================== */

import {
    useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent,
    type PointerEvent as ReactPointerEvent,
} from 'react';

import { api } from './api';
import { CloseIcon, MoonIcon, SunIcon } from './components/Icons';
import { DesignForm } from './design/DesignForm';
import { ExportPanel } from './export/ExportPanel';
import { ResultPane } from './result/ResultPane';
import { LogDrawer, RunBar } from './run/RunBar';
import { useRunEvents } from './run/useRunEvents';
import { useRuns } from './result/useRuns';
import { SweepDialog } from './sweep/SweepDialog';
import { useSweeps } from './sweep/useSweeps';
import type { Config, FormState, Mode, RunEntry, RunSummary, Schema, Submitted, Sweep } from './types';

const defaultFormWidth = 540;   // [px]
const minFormWidth = 380;       // [px]
const minPaneWidth = 480;       // [px]
const keyStep = 24;             // [px] one arrow key press on the splitter

interface Toast {
    id: number;
    kind: 'info' | 'error';
    title: string;
    body: string;
}

function initialMode(): Mode {
    return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}

export function App() {
    const [schema, setSchema] = useState<Schema | null>(null);
    const [config, setConfig] = useState<Config>({});
    const [formVersion, setFormVersion] = useState(0);
    const [formState, setFormState] = useState<FormState>({ hidden: [], expand: [], problems: [], flagged: [], notes: {} });
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [mode, setMode] = useState<Mode>(initialMode);
    const [formWidth, setFormWidth] = useState(defaultFormWidth);
    const [logOpen, setLogOpen] = useState(false);
    const [stagesOpen, setStagesOpen] = useState(false);
    const [exportOpen, setExportOpen] = useState(false);
    const [aboutOpen, setAboutOpen] = useState(false);
    const [sweepOpen, setSweepOpen] = useState(false);
    const [focusSweep, setFocusSweep] = useState<{ sweepId: number; at: number } | null>(null);
    const [confirmProblems, setConfirmProblems] = useState<string[] | null>(null);
    const [toasts, setToasts] = useState<Toast[]>([]);
    const [loadError, setLoadError] = useState('');
    const fileInput = useRef<HTMLInputElement>(null);
    const workspace = useRef<HTMLDivElement>(null);
    const toastCount = useRef(0);

    const notify = useCallback((kind: Toast['kind'], title: string, body = '') => {
        const id = ++toastCount.current;
        setToasts((previous) => [...previous, { id, kind, title, body }]);
        if (kind === 'info') {
            window.setTimeout(() => setToasts((previous) => previous.filter((toast) => toast.id !== id)), 4000);
        }
    }, []);

    // -- Startup: the schema, the form's first state, the saved form width -- //
    useEffect(() => {
        api.schema()
            .then(async (loaded) => {
                const state = await api.formState(loaded.defaults);
                setFormState(state);
                setConfig(loaded.defaults);
                setSchema(loaded);
            })
            .catch((error: Error) => setLoadError(error.message));
        api.settings().then((saved) => saved.formWidth && setFormWidth(saved.formWidth)).catch(() => undefined);
    }, []);

    // -- The schema's predicates decide which rows show; ask the server as the config changes -- //
    useEffect(() => {
        if (!schema) {
            return;
        }
        let cancelled = false;
        const timer = window.setTimeout(() => {
            api.formState(config).then((state) => !cancelled && setFormState(state)).catch(() => undefined);
        }, 60);
        return () => {
            cancelled = true;
            window.clearTimeout(timer);
        };
    }, [schema, config]);

    const patchConfig = useCallback((patch: Config) => setConfig((previous) => ({ ...previous, ...patch })), []);

    const reportError = useCallback((id: string, message: string | null) => {
        setErrors((previous) => {
            if ((previous[id] ?? null) === message) {
                return previous;
            }
            const next = { ...previous };
            if (message === null) {
                delete next[id];
            } else {
                next[id] = message;
            }
            return next;
        });
    }, []);

    const replaceConfig = useCallback((next: Config) => {
        setErrors({});
        setConfig(next);
        setFormVersion((version) => version + 1);
    }, []);

    // -- Runs -- //
    const onResult = useCallback((result: RunSummary) => {
        if (result.ok) {
            notify('info', 'Nozzle generated', `${result.runName} in ${result.elapsedSec.toFixed(1)} s`);
        } else if (result.error !== 'run cancelled') {
            notify('error', 'Run failed', `${result.error}\nThe run log carries the full traceback.`);
        }
    }, [notify]);

    const run = useRunEvents(onResult);
    const runs = useRuns(run, 'latest', (title, message) => notify('error', title, message));
    const sweeps = useSweeps(run, (title, message) => notify('error', title, message));
    // A run still going has nothing to export yet; Export offers the latest finished run instead
    const exportRun = runs.partial ? (runs.list?.latest ?? null) : runs.shown;
    const running = run.state === 'running';
    const errorList = Object.values(errors);
    // A run going does not block: the form queues behind it
    const canGenerate = schema !== null && errorList.length === 0 && run.connected;
    const blockReason = errorList.length > 0 ? `Fix first: ${errorList[0]}` : (!run.connected ? 'The NOVA server is not answering' : '');

    // The stage list opens as a run starts; closing it holds until the next run
    const wasRunning = useRef(false);
    useEffect(() => {
        if (running && !wasRunning.current) {
            setStagesOpen(true);
        }
        wasRunning.current = running;
    }, [running]);

    const startRun = useCallback(() => {
        setConfirmProblems(null);
        api.startRun(config, mode)
            .then((placed: Submitted) => {
                if (placed.position === 0) {
                    // A run started from the form is followed; one queued leaves the pane as it is
                    runs.choose('latest');
                } else {
                    const ahead = placed.position === 1 ? 'the run going ends' : `the run going and ${placed.position - 1} queued before it end`;
                    notify('info', 'Queued', `${String(config.filename || 'The form')} runs when ${ahead}.`);
                }
            })
            .catch((error: Error) => notify('error', 'Run did not start', error.message));
    }, [config, mode, notify, runs.choose]);

    const generate = useCallback(() => {
        if (!canGenerate) {
            if (errorList.length > 0) {
                notify('error', 'The form has problems', errorList.join('\n'));
            }
            return;
        }
        // Cross-field problems warn: the run starts once they are seen and accepted
        if (formState.problems.length > 0) {
            setConfirmProblems(formState.problems);
            return;
        }
        startRun();
    }, [canGenerate, errorList, formState.problems, notify, startRun]);

    const cancel = useCallback((everything: boolean) => {
        api.cancelRun(everything).catch((error: Error) => notify('error', 'Cancel failed', error.message));
    }, [notify]);

    const unqueue = useCallback((queueIds: number[]) => {
        Promise.all(queueIds.map((queueId) => api.unqueue(queueId)))
            .catch((error: Error) => notify('error', 'Not taken out of the queue', error.message));
    }, [notify]);

    const sweepQueued = useCallback((sweep: Sweep) => {
        notify('info', `${sweep.name} queued`, `${sweep.points.length} runs, one at a time`);
        setFocusSweep({ sweepId: sweep.sweepId, at: Date.now() });
    }, [notify]);

    const latestEntry = runs.entry(runs.list?.latest ?? null);
    const lastRun = latestEntry ? { seconds: latestEntry.elapsedSec, bytes: latestEntry.bytes } : null;

    // -- Config files -- //
    const loadExample = useCallback((name: string) => {
        api.example(name)
            .then((loaded) => {
                replaceConfig(loaded);
                notify('info', 'Example loaded', String(loaded._title ?? name));
            })
            .catch((error: Error) => notify('error', 'Example not loaded', error.message));
    }, [notify, replaceConfig]);

    // A kept run's config, over the defaults for any field added since it ran
    const editFrom = useCallback((entry: RunEntry) => {
        if (!entry.config) {
            return;
        }
        replaceConfig({ ...(schema?.defaults ?? {}), ...entry.config });
        notify('info', `Run ${entry.runId}'s config is in the form`, entry.title || entry.runName);
    }, [schema, notify, replaceConfig]);

    const resetConfig = useCallback(() => {
        if (schema) {
            replaceConfig(schema.defaults);
        }
    }, [schema, replaceConfig]);

    const openFile = useCallback(() => fileInput.current?.click(), []);

    const readFile = (file: File) => {
        file.text()
            .then((text) => {
                const loaded = JSON.parse(text);
                if (!loaded || typeof loaded !== 'object' || Array.isArray(loaded)) {
                    throw new Error('the file does not hold a config object');
                }
                replaceConfig({ ...(schema?.defaults ?? {}), ...loaded });
                notify('info', 'Config loaded', file.name);
            })
            .catch((error: Error) => notify('error', 'Config not loaded', `${file.name}: ${error.message}`));
    };

    const saveConfig = useCallback(() => {
        const name = String(config.filename || 'novaConfig');
        const blob = new Blob([JSON.stringify(config, null, 4)], { type: 'application/json' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `${name}.json`;
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    }, [config]);

    // -- Theme -- //
    useEffect(() => {
        if (run.savedMode && run.savedMode !== document.documentElement.dataset.theme) {
            document.documentElement.dataset.theme = run.savedMode;
            setMode(run.savedMode);
        }
    }, [run.savedMode]);

    const toggleMode = () => {
        const next: Mode = mode === 'dark' ? 'light' : 'dark';
        document.documentElement.dataset.theme = next;
        setMode(next);
        api.saveSettings({ themeMode: next }).catch(() => undefined);
    };

    // -- Splitter -- //
    const clampWidth = useCallback((width: number) => {
        const total = workspace.current?.clientWidth ?? window.innerWidth;
        return Math.round(Math.max(minFormWidth, Math.min(width, total - minPaneWidth)));
    }, []);

    const keepWidth = useCallback((width: number) => {
        api.saveSettings({ formWidth: width }).catch(() => undefined);
    }, []);

    const drag = useRef<{ x: number; width: number } | null>(null);

    const onSplitterDown = (event: ReactPointerEvent<HTMLDivElement>) => {
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = { x: event.clientX, width: clampWidth(formWidth) };
    };

    const onSplitterMove = (event: ReactPointerEvent<HTMLDivElement>) => {
        if (drag.current) {
            setFormWidth(clampWidth(drag.current.width + event.clientX - drag.current.x));
        }
    };

    const onSplitterUp = (event: ReactPointerEvent<HTMLDivElement>) => {
        if (drag.current) {
            drag.current = null;
            event.currentTarget.releasePointerCapture(event.pointerId);
            keepWidth(formWidth);
        }
    };

    const onSplitterKey = (event: ReactKeyboardEvent<HTMLDivElement>) => {
        const moves: Record<string, number> = {
            ArrowLeft: formWidth - keyStep, ArrowRight: formWidth + keyStep, Home: minFormWidth, End: Number.MAX_SAFE_INTEGER,
        };
        if (event.key in moves) {
            event.preventDefault();
            const width = clampWidth(moves[event.key]);
            setFormWidth(width);
            keepWidth(width);
        }
    };

    const resetWidth = () => {
        setFormWidth(defaultFormWidth);
        keepWidth(defaultFormWidth);
    };

    // -- Shortcuts: the browser's own Ctrl+R, Ctrl+O and Ctrl+S give way to NOVA's; Escape closes -- //
    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                if (confirmProblems) {
                    setConfirmProblems(null);
                } else if (aboutOpen) {
                    setAboutOpen(false);
                } else if (exportOpen) {
                    setExportOpen(false);
                } else if (stagesOpen) {
                    setStagesOpen(false);
                }
                return;
            }
            if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) {
                return;
            }
            const key = event.key.toLowerCase();
            if (key === 'r') {
                event.preventDefault();
                generate();
            } else if (key === 'o') {
                event.preventDefault();
                openFile();
            } else if (key === 's') {
                event.preventDefault();
                saveConfig();
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [generate, openFile, saveConfig, confirmProblems, aboutOpen, exportOpen, stagesOpen]);

    return (
        <div className="app">
            <header className="app-header">
                <img className="brand-mark" src={`/api/brand/${mode === 'light' ? 'bannerLight' : 'bannerDark'}`} alt="" />
                <span className="wordmark">NOVA</span>
                <span className="subtitle">Nozzle Optimization for Variable Applications</span>
                <span className="toolbar-spacer" />
                <button type="button" className="button button-header" onClick={openFile} title="Load a JSON config  Ctrl+O">
                    Load config
                </button>
                <button type="button" className="icon-button" onClick={toggleMode}
                        title={mode === 'dark' ? 'Switch to the light theme' : 'Switch to the dark theme'}>
                    {mode === 'dark' ? <SunIcon /> : <MoonIcon />}
                </button>
                <button type="button" className="button button-quiet" onClick={() => setAboutOpen(true)}>About</button>
                <input ref={fileInput} type="file" accept=".json,application/json" hidden
                       onChange={(event) => {
                           const file = event.target.files?.[0];
                           if (file) {
                               readFile(file);
                           }
                           event.target.value = '';
                       }} />
            </header>

            <main ref={workspace} className="workspace" style={{ '--form-width': `${formWidth}px` } as CSSProperties}>
                <section className="design-pane" aria-label="Design">
                    {loadError && <div className="empty">The NOVA server did not answer: {loadError}</div>}
                    {!schema && !loadError && <div className="empty"><span className="spinner" /> Loading</div>}
                    {schema && (
                        <DesignForm schema={schema} config={config} formVersion={formVersion} formState={formState}
                                    errors={errors} onPatch={patchConfig} onError={reportError} onReset={resetConfig}
                                    onLoadExample={loadExample} onSave={saveConfig} />
                    )}
                </section>
                <div className="splitter" role="separator" aria-orientation="vertical" aria-label="Form width"
                     aria-valuenow={formWidth} aria-valuemin={minFormWidth} tabIndex={0}
                     title="Drag to resize the form; double-click for the default width"
                     onPointerDown={onSplitterDown} onPointerMove={onSplitterMove} onPointerUp={onSplitterUp}
                     onPointerCancel={onSplitterUp} onKeyDown={onSplitterKey} onDoubleClick={resetWidth} />
                <ResultPane runs={runs} mode={mode} run={run} schema={schema} config={config} sweeps={sweeps} focusSweep={focusSweep}
                            onExport={() => setExportOpen(true)} onEditFrom={editFrom} onNotify={notify} />
            </main>

            {logOpen && <LogDrawer lines={run.log} />}
            <RunBar run={run} canGenerate={canGenerate} blockReason={blockReason} logOpen={logOpen} stagesOpen={stagesOpen}
                    onGenerate={generate} onSweep={() => setSweepOpen(true)} onCancel={cancel} onUnqueue={unqueue}
                    onToggleLog={() => setLogOpen((open) => !open)} onToggleStages={() => setStagesOpen((open) => !open)} />

            {sweepOpen && schema && (
                <SweepDialog schema={schema} config={config} hidden={formState.hidden} problems={formState.problems}
                             blockReason={errorList.length > 0 ? `Fix the form first: ${errorList[0]}` : blockReason}
                             mode={mode} lastRun={lastRun}
                             limits={{ maxPoints: sweeps?.maxPoints ?? 64, maxSeries: sweeps?.maxSeries ?? 6 }}
                             onQueued={sweepQueued} onClose={() => setSweepOpen(false)} onNotify={notify} />
            )}

            <div className="toasts" aria-live="polite">
                {toasts.map((toast) => (
                    <div key={toast.id} className={`toast toast-${toast.kind}`}>
                        <div className="toast-title">{toast.title}</div>
                        {toast.body && <div className="toast-body">{toast.body}</div>}
                        <button type="button" className="toast-close" aria-label="Dismiss"
                                onClick={() => setToasts((previous) => previous.filter((entry) => entry.id !== toast.id))}>
                            &times;
                        </button>
                    </div>
                ))}
            </div>

            {/* Kept mounted while closed, so the folder and the checks hold from one opening to the next */}
            {schema && (
                <div className="modal-scrim" hidden={!exportOpen} onClick={() => setExportOpen(false)}>
                    <div className="card modal export-dialog" role="dialog" aria-label="Export outputs"
                         onClick={(event) => event.stopPropagation()}>
                        <div className="export-dialog-head">
                            <h2>Export outputs</h2>
                            <span className="toolbar-spacer" />
                            <button type="button" className="icon-button" aria-label="Close the export dialog"
                                    onClick={() => setExportOpen(false)}>
                                <CloseIcon />
                            </button>
                        </div>
                        <ExportPanel runId={exportRun} baseline={runs.baseline} mode={mode} formName={String(config.filename || '')}
                                     onNotify={notify} />
                    </div>
                </div>
            )}

            {confirmProblems && (
                <div className="modal-scrim" onClick={() => setConfirmProblems(null)}>
                    <div className="card modal" role="alertdialog" aria-label="Configuration warnings"
                         onClick={(event) => event.stopPropagation()}>
                        <h2>Configuration warnings</h2>
                        <p>The form has unresolved issues:</p>
                        <ul className="modal-list">
                            {confirmProblems.map((problem) => <li key={problem}>{problem}</li>)}
                        </ul>
                        <div className="modal-actions">
                            <button type="button" className="button" onClick={() => setConfirmProblems(null)}>
                                Back to the form
                            </button>
                            <button type="button" className="button button-primary" onClick={startRun} autoFocus>
                                Run anyway
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {aboutOpen && (
                <div className="modal-scrim" onClick={() => setAboutOpen(false)}>
                    <div className="card modal" role="dialog" aria-label="About NOVA" onClick={(event) => event.stopPropagation()}>
                        <h2>NOVA -- Nozzle Optimization for Variable Applications</h2>
                        <p>
                            Web front end for the NOVA suite. Design a nozzle in the form on the left and Generate it:
                            the contour, cooling, heat transfer and plume pipeline runs in a worker process, and the
                            run bar steps through its stages. Generate during a run queues the form behind it, and
                            Sweep queues one run per value of a field. The pane on the right shows any of the saved
                            runs, as figures or as a results table, against a baseline run when one is chosen, and a
                            sweep as a plot and a table of its points; Export copies a run's outputs to keep, and
                            Save report writes a run's or a sweep's report as one HTML file to send.
                        </p>
                        <p className="muted">Shortcuts: Ctrl+R generate, Ctrl+O load a config, Ctrl+S save one, Escape close.</p>
                        <div className="modal-actions">
                            <button type="button" className="button" onClick={() => setAboutOpen(false)}>Close</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
