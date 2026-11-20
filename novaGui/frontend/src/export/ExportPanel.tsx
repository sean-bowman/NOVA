/* ========================================
   EXPORT PANEL
   The dialog the result pane's Export button opens. Chooses which of the shown run's outputs to
   keep and copies them to an output folder, as <output folder>/<run name>Outputs/. The outputs
   are listed by category (novaGui/outputs.py, shared with the legacy Tkinter Export tab); a check
   on a category or on a single file chooses it. Every output is chosen after a run, except the
   categories unchecked before it. A file opens in its desktop application on a double click.
   In the desktop window Browse opens the native folder picker; in a browser the folder is typed.

   An image, an STL surface or a text file previews beside the list (OutputPreview.tsx), and the
   images carry a thumbnail in their row. Save report writes the run's report as one HTML file
   (ReportButtons.tsx), against the baseline when the pane has one.
   Sean Bowman [11/17/2026]
   ======================================== */

import { useEffect, useMemo, useRef, useState } from 'react';

import { api, exportFileUrl, runReportPath, windowBridge } from '../api';
import { ChevronIcon, EyeIcon, FolderIcon } from '../components/Icons';
import type { ExportIndex, ExportTarget, Mode, OutputFile } from '../types';
import { formatSize } from './fileSize';
import { OutputPreview } from './OutputPreview';
import { ReportButtons } from '../report/ReportButtons';

interface ExportPanelProps {
    runId: number | null;
    baseline: number | null;      // the run the report sets beside this one, or null
    mode: Mode;
    formName: string;
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

type CheckState = 'all' | 'some' | 'none';

function extension(name: string): string {
    const dot = name.lastIndexOf('.');
    return dot > 0 ? name.slice(dot + 1).toUpperCase() : '';
}

function Check({ state, label, onToggle }: { state: CheckState; label: string; onToggle: () => void }) {
    const box = useRef<HTMLInputElement>(null);
    useEffect(() => {
        if (box.current) {
            box.current.indeterminate = state === 'some';
        }
    }, [state]);
    return (
        <input ref={box} type="checkbox" className="output-check" aria-label={label} checked={state === 'all'}
               onChange={onToggle} onClick={(event) => event.stopPropagation()} />
    );
}

export function ExportPanel({ runId, baseline, mode, formName, onNotify }: ExportPanelProps) {
    const [index, setIndex] = useState<ExportIndex | null>(null);
    const [baseDir, setBaseDir] = useState('');
    const [chosen, setChosen] = useState<Set<string>>(new Set());
    const [unchecked, setUnchecked] = useState<Set<string>>(new Set());
    const [open, setOpen] = useState<Record<string, boolean>>({});
    const [target, setTarget] = useState<ExportTarget | null>(null);
    const [lastExport, setLastExport] = useState('');
    const [busy, setBusy] = useState(false);
    const [preview, setPreview] = useState<OutputFile | null>(null);
    const [bridgeReady, setBridgeReady] = useState(() => windowBridge() !== null);
    const reportRun = index?.runId ?? null;
    const reportAgainst = baseline !== null && baseline !== reportRun ? baseline : null;
    const uncheckedRef = useRef(unchecked);
    uncheckedRef.current = unchecked;

    // pywebview attaches its bridge after the page has loaded
    useEffect(() => {
        const ready = () => setBridgeReady(windowBridge() !== null);
        window.addEventListener('pywebviewready', ready);
        return () => window.removeEventListener('pywebviewready', ready);
    }, []);

    // A new run lists its outputs, every one chosen but those of the categories left unchecked
    useEffect(() => {
        let cancelled = false;
        setPreview(null);
        api.exportIndex(runId)
            .then((loaded) => {
                if (cancelled) {
                    return;
                }
                setIndex(loaded);
                setBaseDir((current) => current || loaded.defaultBaseDir);
                setChosen(new Set(loaded.files.filter((file) => !uncheckedRef.current.has(file.category)).map((file) => file.name)));
                setLastExport('');
            })
            .catch((failure: Error) => !cancelled && onNotify('error', 'Outputs unavailable', failure.message));
        return () => {
            cancelled = true;
        };
    }, [runId, onNotify]);

    const files = useMemo(() => index?.files ?? [], [index]);
    const runName = index?.runId != null ? index.runName : (formName || 'novaRun');

    // The folder an export writes to, resolved by the server as the base and run name change
    useEffect(() => {
        if (!index) {
            return;
        }
        let cancelled = false;
        const timer = window.setTimeout(() => {
            api.exportTarget(baseDir, runName).then((resolved) => !cancelled && setTarget(resolved)).catch(() => undefined);
        }, 200);
        return () => {
            cancelled = true;
            window.clearTimeout(timer);
        };
    }, [index, baseDir, runName, lastExport]);

    const byCategory = useMemo(() => {
        const groups: Record<string, OutputFile[]> = {};
        for (const file of files) {
            (groups[file.category] ??= []).push(file);
        }
        return groups;
    }, [files]);

    const categoryState = (key: string): CheckState => {
        const members = byCategory[key] ?? [];
        // Before a run a category's check says whether the run's files of that kind will be chosen
        if (members.length === 0) {
            return unchecked.has(key) ? 'none' : 'all';
        }
        const count = members.filter((file) => chosen.has(file.name)).length;
        return count === members.length ? 'all' : (count > 0 ? 'some' : 'none');
    };

    const toggleCategory = (key: string) => {
        const on = categoryState(key) !== 'all';
        setChosen((previous) => {
            const next = new Set(previous);
            for (const file of byCategory[key] ?? []) {
                if (on) {
                    next.add(file.name);
                } else {
                    next.delete(file.name);
                }
            }
            return next;
        });
        setUnchecked((previous) => {
            const next = new Set(previous);
            if (on) {
                next.delete(key);
            } else {
                next.add(key);
            }
            return next;
        });
        setLastExport('');
    };

    const toggleFile = (name: string) => {
        setChosen((previous) => {
            const next = new Set(previous);
            if (next.has(name)) {
                next.delete(name);
            } else {
                next.add(name);
            }
            return next;
        });
        setLastExport('');
    };

    const chooseAll = (on: boolean) => {
        setChosen(on ? new Set(files.map((file) => file.name)) : new Set());
        setUnchecked(on ? new Set() : new Set((index?.categories ?? []).map((category) => category.key)));
        setLastExport('');
    };

    const browse = () => {
        const bridge = windowBridge();
        if (!bridge) {
            return;
        }
        bridge.browseFolder(baseDir)
            .then((picked) => picked && setBaseDir(picked))
            .catch((failure: Error) => onNotify('error', 'Folder picker failed', String(failure?.message ?? failure)));
    };

    const exportChosen = () => {
        const names = files.filter((file) => chosen.has(file.name)).map((file) => file.name);
        if (names.length === 0) {
            return;
        }
        setBusy(true);
        api.exportFiles(index?.runId ?? null, baseDir, names)
            .then((result) => {
                setLastExport(`Exported ${result.written} files, ${formatSize(result.bytes)}, to ${result.target}`);
                onNotify('info', 'Outputs exported', `${result.written} files to ${result.target}`);
            })
            .catch((failure: Error) => onNotify('error', 'Export failed', failure.message))
            .finally(() => setBusy(false));
    };

    const openFolder = () => {
        api.openFolder(index?.runId ?? null, baseDir, runName).catch((failure: Error) => onNotify('error', 'Folder not opened', failure.message));
    };

    const openFile = (name: string) => {
        api.openOutput(index?.runId ?? null, name).catch((failure: Error) => onNotify('error', 'File not opened', failure.message));
    };

    // Categories shown: before a run every kind a run writes, after one only the kinds it wrote
    const shown = (index?.categories ?? []).filter((category) => {
        const count = byCategory[category.key]?.length ?? 0;
        return count > 0 || (files.length === 0 && category.key !== 'other');
    });

    const chosenCount = files.filter((file) => chosen.has(file.name)).length;
    const chosenBytes = files.filter((file) => chosen.has(file.name)).reduce((sum, file) => sum + file.bytes, 0);
    let status: string;
    if (files.length === 0) {
        status = 'Generate a nozzle to have outputs to export.';
    } else if (lastExport) {
        status = lastExport;
    } else {
        status = `${chosenCount} of ${files.length} outputs checked, ${formatSize(chosenBytes)}.`;
    }

    return (
        <div className="export-panel">
            <div className="card export-folder">
                <label className="export-folder-label" htmlFor="export-base">Output folder</label>
                <input id="export-base" className="input mono" value={baseDir} spellCheck={false}
                       onChange={(event) => {
                           setBaseDir(event.target.value);
                           setLastExport('');
                       }} />
                {bridgeReady && <button type="button" className="button" onClick={browse}><FolderIcon /> Browse</button>}
                <div className="export-target muted">
                    <span className="mono">{target ? target.target : ''}</span>
                    {target?.exists && <span className="badge">exists</span>}
                </div>
            </div>

            <div className={`export-body ${preview ? 'has-preview' : ''}`}>
            <div className="card export-list">
                <div className="export-list-heading">
                    <span className="eyebrow eyebrow-inline">Outputs</span>
                    {index?.runId != null && <span className="muted">{runName}, run {index.runId}</span>}
                    <span className="toolbar-spacer" />
                    <button type="button" className="button button-small" onClick={() => chooseAll(true)}>All</button>
                    <button type="button" className="button button-small" onClick={() => chooseAll(false)}>None</button>
                </div>
                <div className="output-scroll">
                    <div className="output-row output-head">
                        <span />
                        <span>Output</span>
                        <span>Files</span>
                        <span className="output-size">Size</span>
                    </div>
                    {shown.map((category) => {
                        const members = byCategory[category.key] ?? [];
                        const expanded = members.length > 0 && !!open[category.key];
                        const bytes = members.reduce((sum, file) => sum + file.bytes, 0);
                        return (
                            <div key={category.key} className="output-category">
                                <div className="output-row output-category-row"
                                     onClick={() => members.length > 0 && setOpen((previous) => ({ ...previous, [category.key]: !previous[category.key] }))}>
                                    <span className="output-toggle">
                                        {members.length > 0 && <ChevronIcon className={`output-chevron ${expanded ? 'is-open' : ''}`} />}
                                        <Check state={categoryState(category.key)} label={`Export ${category.name}`}
                                               onToggle={() => toggleCategory(category.key)} />
                                    </span>
                                    <span className="output-name">
                                        <strong>{category.name}</strong>
                                        <span className="muted">{category.description}</span>
                                    </span>
                                    <span className="muted">{members.length > 0 ? `${members.length} file${members.length === 1 ? '' : 's'}` : 'after a run'}</span>
                                    <span className="output-size">{members.length > 0 ? formatSize(bytes) : ''}</span>
                                </div>
                                {expanded && members.map((file) => (
                                    <div key={file.name} className={`output-row output-file-row ${preview?.name === file.name ? 'is-previewed' : ''}`}
                                         title="Double-click to open" onClick={() => toggleFile(file.name)}
                                         onDoubleClick={() => openFile(file.name)}>
                                        <span className="output-toggle output-file-check">
                                            <Check state={chosen.has(file.name) ? 'all' : 'none'} label={`Export ${file.name}`}
                                                   onToggle={() => toggleFile(file.name)} />
                                        </span>
                                        <span className="output-name mono">
                                            {file.preview === 'image' && (
                                                <img className="output-thumb" src={exportFileUrl(index?.runId ?? null, file.name)} alt=""
                                                     loading="lazy" draggable={false} />
                                            )}
                                            <span className="output-file-name">{file.name}</span>
                                        </span>
                                        <span className="muted output-kind">
                                            {extension(file.name)}
                                            {file.preview && (
                                                <button type="button" className="icon-button output-preview-button"
                                                        aria-label={`Preview ${file.name}`} title="Preview"
                                                        onClick={(event) => {
                                                            event.stopPropagation();
                                                            setPreview((current) => (current?.name === file.name ? null : file));
                                                        }}
                                                        onDoubleClick={(event) => event.stopPropagation()}>
                                                    <EyeIcon />
                                                </button>
                                            )}
                                        </span>
                                        <span className="output-size">{formatSize(file.bytes)}</span>
                                    </div>
                                ))}
                            </div>
                        );
                    })}
                </div>
            </div>

            {preview && <OutputPreview runId={index?.runId ?? null} file={preview} mode={mode} onClose={() => setPreview(null)} />}
            </div>

            <div className="export-actions">
                <ReportButtons path={reportRun !== null ? runReportPath(reportRun, reportAgainst) : null}
                               fileName={`${index?.runName || 'novaRun'}Run${reportRun}${reportAgainst !== null ? `VsRun${reportAgainst}` : ''}Report.html`}
                               title={reportRun !== null ? `Run ${reportRun}${reportAgainst !== null ? ` against run ${reportAgainst}` : ''}` : 'The run'}
                               onNotify={onNotify} />
                <span className="export-status muted">{status}</span>
                <button type="button" className="button" onClick={openFolder} disabled={!target?.exists}
                        title="Open the folder the export writes to">
                    <FolderIcon /> Open folder
                </button>
                <button type="button" className="button button-primary" onClick={exportChosen}
                        disabled={busy || chosenCount === 0} title="Copy the checked outputs into the output folder">
                    {busy ? <span className="spinner" /> : null} Export
                </button>
            </div>
        </div>
    );
}
