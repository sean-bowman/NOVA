/* ========================================
   FIGURE VIEW
   Every view of a run, drawn interactive (plotly.js: zoom, pan, rotate, hover to read values),
   one at a time picked from a grouped dropdown, or four at once in a grid. Views the run did not
   produce stay listed and disabled, so the list reads the same from run to run.

   The figures drawn along the nozzle axis share one cursor and one zoom (axialLink.ts), so in
   the grid the wall temperature, the heat flux and the coolant state read off at one station.
   Beside a baseline run, the line plots draw the baseline dashed over the shown run.

   Save PNG saves the Matplotlib drawing of the view (novaGui.plotting, thermalPlots), the
   picture NOVA's saved figures use, at the pane's size. Pop out opens the figures in a window of
   their own, for a second monitor; it follows the latest run, or keeps to the run it was opened
   on when that is an older one.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useEffect, useMemo, useState } from 'react';

import { openWindow, saveBlob, staticFigure } from '../api';
import { GridIcon, ImageIcon, PopOutIcon } from '../components/Icons';
import type { RunChoice } from '../result/useRuns';
import type { Mode, ViewIndex, ViewSpec } from '../types';
import { AxialLink } from './axialLink';
import { PlotlyFigure } from './PlotlyFigure';

export type FigureLayout = 'single' | 'grid';

const gridSize = 4;
const saveRatio = 2;            // [-] pixels per CSS pixel of a saved PNG

// The views a grid opens on, in order of preference: the jacket read along the axis, else the flow
const coolingGrid = ['contour', 'jacketTemperatures', 'heatFlux', 'coolantFlow'];
const flowGrid = ['contour', 'nearWall', 'mach', 'pressure'];
const threeD = new Set(['channelMesh', 'revolved', 'volute']);

interface FigureViewProps {
    index: ViewIndex | null;
    mode: Mode;
    compare: number | null;          // the baseline run, drawn over the comparable views
    selected: string;
    layout: FigureLayout;
    runChoice: RunChoice;            // what a popped-out window follows
    initialGrid?: string[];
    onSelect: (key: string) => void;
    onLayout: (layout: FigureLayout) => void;
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

/** The grid's views: those kept that the run produced, then the preferred ones, then any it produced. */
export function gridFor(available: Set<string>, kept: string[]): string[] {
    const chosen = kept.filter((key) => available.has(key));
    const preferred = available.has('jacketTemperatures') ? coolingGrid : flowGrid;
    for (const key of [...preferred, ...available]) {
        if (chosen.length >= gridSize) {
            break;
        }
        if (available.has(key) && !chosen.includes(key) && !threeD.has(key)) {
            chosen.push(key);
        }
    }
    return chosen.slice(0, gridSize);
}

function groupsOf(views: ViewSpec[]): { name: string; views: ViewSpec[] }[] {
    const ordered: { name: string; views: ViewSpec[] }[] = [];
    for (const spec of views) {
        const last = ordered[ordered.length - 1];
        if (last && last.name === spec.group) {
            last.views.push(spec);
        } else {
            ordered.push({ name: spec.group, views: [spec] });
        }
    }
    return ordered;
}

function ViewSelect({ views, available, value, onChange, compact = false }: {
    views: ViewSpec[]; available: Set<string>; value: string; onChange: (key: string) => void; compact?: boolean;
}) {
    const groups = useMemo(() => groupsOf(views), [views]);
    return (
        <select className={`input view-select ${compact ? 'view-select-compact' : ''}`} aria-label="View" value={value}
                disabled={views.length === 0} onChange={(event) => onChange(event.target.value)}>
            {groups.map((group) => (
                <optgroup key={group.name} label={group.name}>
                    {group.views.map((candidate) => (
                        <option key={candidate.key} value={candidate.key} disabled={!available.has(candidate.key)}>
                            {candidate.label}
                        </option>
                    ))}
                </optgroup>
            ))}
        </select>
    );
}

export function FigureView({ index, mode, compare, selected, layout, runChoice, initialGrid, onSelect, onLayout,
                             onNotify }: FigureViewProps) {
    const [gridKeys, setGridKeys] = useState<string[]>(initialGrid ?? []);
    const [saving, setSaving] = useState('');
    const link = useMemo(() => new AxialLink(), []);

    const available = useMemo(() => new Set(index?.available ?? []), [index]);
    const views = index?.views ?? [];
    const runId = index?.runId ?? null;
    const partial = index?.partial ?? false;
    const grid = useMemo(() => gridFor(available, gridKeys), [available, gridKeys]);

    // Keep the selection on a view the run produced
    useEffect(() => {
        if (index && index.available.length > 0 && !available.has(selected)) {
            onSelect(index.available[0]);
        }
    }, [index, available, selected, onSelect]);

    const specOf = (key: string) => views.find((candidate) => candidate.key === key);
    const compareFor = (key: string) => (compare !== null && compare !== runId && !partial && specOf(key)?.comparable
        ? compare : null);

    const save = (key: string, element: HTMLElement | null) => {
        if (runId === null || partial) {
            return;
        }
        const width = element?.clientWidth || 1200;
        const height = element?.clientHeight || 800;
        setSaving(key);
        staticFigure(key, mode, runId, width, height, saveRatio)
            .then((drawn) => {
                if ('blob' in drawn) {
                    saveBlob(drawn.blob, `${index?.runName || 'nova'}Run${runId}-${key}.png`);
                } else {
                    onNotify('error', 'No PNG for this view', drawn.message);
                }
            })
            .catch((failure: Error) => onNotify('error', 'PNG not saved', failure.message))
            .finally(() => setSaving(''));
    };

    const popOut = () => {
        const keys = layout === 'grid' ? grid : [selected];
        const params = new URLSearchParams({ popout: 'figure', run: String(runChoice), layout, views: keys.join(',') });
        const label = keys.map((key) => specOf(key)?.label ?? key).join(', ');
        openWindow(`/?${params.toString()}`, `NOVA -- ${label}`);
    };

    const savingTitle = partial ? 'The PNG saves once the run finishes' : 'Save the Matplotlib drawing of this view as a PNG';

    const figureFor = (key: string, inGrid = false) => {
        const spec = specOf(key);
        if (!index) {
            return <div className="figure-pane"><div className="figure-overlay"><span className="spinner" /> Loading views</div></div>;
        }
        if (runId === null) {
            return <div className="figure-pane"><div className="figure-overlay figure-message">Generate a nozzle to draw its views here.</div></div>;
        }
        if (!spec || !available.has(key)) {
            return <div className="figure-pane"><div className="figure-overlay figure-message">{spec?.label ?? 'This view'} was not produced by this run.</div></div>;
        }
        const against = compareFor(key);
        return <PlotlyFigure key={`${key}-${runId}-${partial}-${against}`} viewKey={key} mode={mode} runId={runId}
                             compare={against} link={link} scrollZoom={!inGrid} />;
    };

    const spec = specOf(selected);
    const produced = spec !== undefined && available.has(spec.key);

    return (
        <div className="figure-view">
            <div className="figure-toolbar">
                {layout === 'single' && <ViewSelect views={views} available={available} value={selected} onChange={onSelect} />}
                <span className="muted figure-source" title={layout === 'single' && produced ? spec?.source : undefined}>
                    {layout === 'single' && produced ? spec?.source : (layout === 'grid' ? 'One cursor and one zoom along the nozzle axis' : '')}
                </span>
                <div className="segmented" role="group" aria-label="Figure layout">
                    <button type="button" className={layout === 'single' ? 'is-selected' : ''} aria-pressed={layout === 'single'}
                            onClick={() => onLayout('single')} title="One view">One</button>
                    <button type="button" className={layout === 'grid' ? 'is-selected' : ''} aria-pressed={layout === 'grid'}
                            onClick={() => onLayout('grid')} title="Four views along the nozzle axis, with one cursor">
                        <GridIcon /> Grid
                    </button>
                </div>
                {layout === 'single' && (
                    <button type="button" className="button" disabled={!produced || partial || saving !== ''} title={savingTitle}
                            onClick={(event) => save(selected, event.currentTarget.closest('.figure-view')?.querySelector('.figure-pane') as HTMLElement)}>
                        {saving ? <span className="spinner" /> : <ImageIcon />} Save PNG
                    </button>
                )}
                <button type="button" className="icon-button" onClick={popOut} disabled={runId === null}
                        aria-label="Pop out" title="Open in a window of its own, for a second monitor">
                    <PopOutIcon />
                </button>
            </div>
            {layout === 'single' ? figureFor(selected) : (
                <div className="figure-grid">
                    {grid.map((key, position) => (
                        <div key={position} className="figure-cell">
                            <div className="figure-cell-head">
                                <ViewSelect views={views} available={available} value={key} compact
                                            onChange={(next) => setGridKeys(() => grid.map((old, at) => (at === position ? next : old)))} />
                                <button type="button" className="icon-button" disabled={partial || saving !== ''} title={savingTitle}
                                        aria-label={`Save ${specOf(key)?.label ?? key} as a PNG`}
                                        onClick={(event) => save(key, event.currentTarget.closest('.figure-cell')?.querySelector('.figure-pane') as HTMLElement)}>
                                    {saving === key ? <span className="spinner" /> : <ImageIcon />}
                                </button>
                            </div>
                            {figureFor(key, true)}
                        </div>
                    ))}
                    {grid.length === 0 && (
                        <div className="figure-pane"><div className="figure-overlay figure-message">
                            {runId === null ? 'Generate a nozzle to draw its views here.' : 'This run produced no views along the axis.'}
                        </div></div>
                    )}
                </div>
            )}
        </div>
    );
}
