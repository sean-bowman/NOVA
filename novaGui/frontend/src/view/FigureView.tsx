/* ========================================
   FIGURE VIEW
   Every view of a run, picked from a grouped dropdown, drawn in the result pane. A view draws
   interactive (plotly.js: zoom, pan, rotate, hover to read values) or static (the Matplotlib
   drawing, as NOVA's saved figures look), whichever it has; a view with both offers a switch.
   Views the run did not produce stay listed and disabled, so the list reads the same from run
   to run.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useEffect, useMemo, useState } from 'react';

import type { Mode, ViewIndex, ViewSpec } from '../types';
import { PlotlyFigure } from './PlotlyFigure';
import { StaticFigure } from './StaticFigure';

type Rendering = 'interactive' | 'static';

interface FigureViewProps {
    index: ViewIndex | null;
    mode: Mode;
}

function renderingFor(spec: ViewSpec, preferred: Rendering): Rendering {
    if (preferred === 'interactive' && spec.interactive) {
        return 'interactive';
    }
    if (preferred === 'static' && spec.static) {
        return 'static';
    }
    return spec.interactive ? 'interactive' : 'static';
}

export function FigureView({ index, mode }: FigureViewProps) {
    const [selected, setSelected] = useState('contour');
    const [preferred, setPreferred] = useState<Rendering>('interactive');

    const available = useMemo(() => new Set(index?.available ?? []), [index]);
    const views = index?.views ?? [];

    // Keep the selection on a view the run produced
    useEffect(() => {
        if (index && index.available.length > 0 && !available.has(selected)) {
            setSelected(index.available[0]);
        }
    }, [index, available, selected]);

    const groups = useMemo(() => {
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
    }, [views]);

    const spec = views.find((candidate) => candidate.key === selected);
    const produced = spec !== undefined && available.has(spec.key);
    const rendering = spec ? renderingFor(spec, preferred) : 'interactive';
    const runId = index?.runId ?? null;

    let pane;
    if (!index) {
        pane = <div className="figure-pane"><div className="figure-overlay"><span className="spinner" /> Loading views</div></div>;
    } else if (runId === null) {
        pane = <div className="figure-pane"><div className="figure-overlay figure-message">Generate a nozzle to draw its views here.</div></div>;
    } else if (!spec || !produced) {
        pane = <div className="figure-pane"><div className="figure-overlay figure-message">{spec?.label ?? 'This view'} was not produced by this run.</div></div>;
    } else if (rendering === 'interactive') {
        pane = <PlotlyFigure key={`${spec.key}-${runId}`} viewKey={spec.key} mode={mode} runId={runId} />;
    } else {
        pane = <StaticFigure key={`${spec.key}-${runId}`} viewKey={spec.key} mode={mode} runId={runId} />;
    }

    return (
        <div className="figure-view">
            <div className="figure-toolbar">
                <select className="input view-select" aria-label="View" value={selected} disabled={views.length === 0}
                        onChange={(event) => setSelected(event.target.value)}>
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
                <span className="muted figure-source" title={produced ? spec?.source : undefined}>
                    {produced ? spec?.source : ''}
                </span>
                {produced && spec && spec.interactive && spec.static && (
                    <div className="segmented" role="group" aria-label="Rendering">
                        <button type="button" className={rendering === 'interactive' ? 'is-selected' : ''}
                                aria-pressed={rendering === 'interactive'} onClick={() => setPreferred('interactive')}
                                title="plotly.js: zoom, pan, rotate and read values by hovering">Interactive</button>
                        <button type="button" className={rendering === 'static' ? 'is-selected' : ''}
                                aria-pressed={rendering === 'static'} onClick={() => setPreferred('static')}
                                title="The Matplotlib drawing the saved figures use">Static</button>
                    </div>
                )}
            </div>
            {pane}
        </div>
    );
}
