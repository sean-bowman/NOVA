/* ========================================
   NOVA APP
   The window: header (plume mark, wordmark, Load config, theme switch, About), the Design,
   View, Analyze and Export tabs, and the run bar. The config lives here in backend values
   (SI), so the Design tab edits it and the run bar sends it as it stands.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useCallback, useEffect, useRef, useState } from 'react';

import { AnalyzeTab } from './analyze/AnalyzeTab';
import { api } from './api';
import { MoonIcon, SunIcon } from './components/Icons';
import { DesignTab } from './design/DesignTab';
import { ExportTab } from './export/ExportTab';
import { LogDrawer, RunBar } from './run/RunBar';
import { useRunEvents } from './run/useRunEvents';
import type { Config, FormState, Mode, RunSummary, Schema, ViewIndex } from './types';
import { ViewTab } from './view/ViewTab';

type TabName = 'design' | 'view' | 'analyze' | 'export';

const tabs: { name: TabName; label: string }[] = [
    { name: 'design', label: 'Design' },
    { name: 'view', label: 'View' },
    { name: 'analyze', label: 'Analyze' },
    { name: 'export', label: 'Export' },
];

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
    const [formState, setFormState] = useState<FormState>({ hidden: [], expand: [] });
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [mode, setMode] = useState<Mode>(initialMode);
    const [tab, setTab] = useState<TabName>('design');
    const [viewIndex, setViewIndex] = useState<ViewIndex | null>(null);
    const [logOpen, setLogOpen] = useState(false);
    const [aboutOpen, setAboutOpen] = useState(false);
    const [toasts, setToasts] = useState<Toast[]>([]);
    const [loadError, setLoadError] = useState('');
    const fileInput = useRef<HTMLInputElement>(null);
    const toastCount = useRef(0);

    const notify = useCallback((kind: Toast['kind'], title: string, body = '') => {
        const id = ++toastCount.current;
        setToasts((previous) => [...previous, { id, kind, title, body }]);
        if (kind === 'info') {
            window.setTimeout(() => setToasts((previous) => previous.filter((toast) => toast.id !== id)), 4000);
        }
    }, []);

    const refreshViews = useCallback(() => {
        api.views().then(setViewIndex).catch((error: Error) => notify('error', 'Views unavailable', error.message));
    }, [notify]);

    // -- Startup: the schema, the form's first state, the views of any run the server holds -- //
    useEffect(() => {
        api.schema()
            .then(async (loaded) => {
                const state = await api.formState(loaded.defaults);
                setFormState(state);
                setConfig(loaded.defaults);
                setSchema(loaded);
            })
            .catch((error: Error) => setLoadError(error.message));
        refreshViews();
    }, [refreshViews]);

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
        refreshViews();
        if (result.ok) {
            notify('info', 'Nozzle generated', `${result.runName} in ${result.elapsedSec.toFixed(1)} s`);
            setTab('view');
        } else if (result.error !== 'run cancelled') {
            notify('error', 'Run failed', `${result.error}\nThe run log carries the full traceback.`);
        }
    }, [notify, refreshViews]);

    const run = useRunEvents(onResult);
    const running = run.state === 'running';
    const errorList = Object.values(errors);
    const canGenerate = schema !== null && !running && errorList.length === 0 && run.connected;
    const blockReason = errorList.length > 0 ? `Fix first: ${errorList[0]}` : (!run.connected ? 'The NOVA server is not answering' : '');

    const generate = useCallback(() => {
        if (!canGenerate) {
            if (errorList.length > 0) {
                notify('error', 'The form has problems', errorList.join('\n'));
                setTab('design');
            }
            return;
        }
        api.startRun(config, mode).catch((error: Error) => notify('error', 'Run did not start', error.message));
    }, [canGenerate, config, errorList, mode, notify]);

    const cancel = useCallback(() => {
        api.cancelRun().catch((error: Error) => notify('error', 'Cancel failed', error.message));
    }, [notify]);

    // -- Config files -- //
    const loadExample = useCallback((name: string) => {
        api.example(name)
            .then((loaded) => {
                replaceConfig(loaded);
                notify('info', 'Example loaded', String(loaded._title ?? name));
            })
            .catch((error: Error) => notify('error', 'Example not loaded', error.message));
    }, [notify, replaceConfig]);

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
    const toggleMode = () => {
        const next: Mode = mode === 'dark' ? 'light' : 'dark';
        document.documentElement.dataset.theme = next;
        setMode(next);
        api.saveSettings({ themeMode: next }).catch(() => undefined);
    };

    // -- Shortcuts: the browser's own Ctrl+R, Ctrl+O and Ctrl+S give way to NOVA's -- //
    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
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
    }, [generate, openFile, saveConfig]);

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

            <nav className="tab-bar" role="tablist">
                {tabs.map((entry) => (
                    <button key={entry.name} type="button" role="tab" aria-selected={tab === entry.name}
                            className={`tab ${tab === entry.name ? 'is-selected' : ''}`} onClick={() => setTab(entry.name)}>
                        {entry.label}
                    </button>
                ))}
            </nav>

            <main className="tab-content">
                {loadError && <div className="empty">The NOVA server did not answer: {loadError}</div>}
                {!schema && !loadError && <div className="empty"><span className="spinner" /> Loading</div>}
                {schema && (
                    <div className="tab-panel" hidden={tab !== 'design'}>
                        <DesignTab schema={schema} config={config} formVersion={formVersion} formState={formState}
                                   errors={errors} onPatch={patchConfig} onError={reportError} onReset={resetConfig}
                                   onLoadExample={loadExample} onSave={saveConfig} />
                    </div>
                )}
                {tab === 'view' && (
                    <div className="tab-panel">
                        <ViewTab index={viewIndex} mode={mode} />
                    </div>
                )}
                {schema && (
                    <div className="tab-panel" hidden={tab !== 'analyze'}>
                        <AnalyzeTab runId={viewIndex?.runId ?? null} visible={tab === 'analyze'} onNotify={notify} />
                    </div>
                )}
                {schema && (
                    <div className="tab-panel" hidden={tab !== 'export'}>
                        <ExportTab runId={viewIndex?.runId ?? null} formName={String(config.filename || '')} onNotify={notify} />
                    </div>
                )}
            </main>

            {logOpen && <LogDrawer lines={run.log} />}
            <RunBar run={run} canGenerate={canGenerate} blockReason={blockReason} logOpen={logOpen}
                    onGenerate={generate} onCancel={cancel} onToggleLog={() => setLogOpen((open) => !open)} />

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

            {aboutOpen && (
                <div className="modal-scrim" onClick={() => setAboutOpen(false)}>
                    <div className="card modal" role="dialog" aria-label="About NOVA" onClick={(event) => event.stopPropagation()}>
                        <h2>NOVA -- Nozzle Optimization for Variable Applications</h2>
                        <p>
                            Web front end for the NOVA suite. Design a nozzle on the Design tab, run the contour,
                            cooling, heat transfer and plume pipeline in a worker process, inspect the result on the
                            View and Analyze tabs, and copy the outputs to keep from the Export tab.
                        </p>
                        <p className="muted">Shortcuts: Ctrl+R generate, Ctrl+O load a config, Ctrl+S save one.</p>
                        <div className="modal-actions">
                            <button type="button" className="button" onClick={() => setAboutOpen(false)}>Close</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
