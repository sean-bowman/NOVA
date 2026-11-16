/* ========================================
   VIEW TAB
   Every view of a run, picked from a grouped sidebar, drawn in one pane. A view draws
   interactive (plotly.js: zoom, pan, rotate, hover to read values) or static (the Matplotlib
   drawing NOVA's Tkinter front end and saved figures use), whichever it has; a view with both
   offers a switch. Views the last run did not produce stay listed and greyed, so the list
   reads the same from run to run.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useEffect, useMemo, useState } from 'react';

import type { Mode, ViewIndex, ViewSpec } from '../types';
import { PlotlyFigure } from './PlotlyFigure';
import { StaticFigure } from './StaticFigure';

type Rendering = 'interactive' | 'static';

interface ViewTabProps {
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

export function ViewTab({ index, mode }: ViewTabProps) {
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
        pane = <div className="figure-pane"><div className="figure-overlay figure-message">Generate a nozzle to populate this view.</div></div>;
    } else if (!spec || !produced) {
        pane = <div className="figure-pane"><div className="figure-overlay figure-message">{spec?.label ?? 'This view'} was not produced by this run.</div></div>;
    } else if (rendering === 'interactive') {
        pane = <PlotlyFigure key={`${spec.key}-${runId}`} viewKey={spec.key} mode={mode} runId={runId} />;
    } else {
        pane = <StaticFigure key={`${spec.key}-${runId}`} viewKey={spec.key} mode={mode} runId={runId} />;
    }

    return (
        <div className="view-tab">
            <nav className="card view-sidebar" aria-label="Views">
                {groups.map((group) => (
                    <div key={group.name} className="view-group">
                        <div className="eyebrow">{group.name}</div>
                        {group.views.map((candidate) => (
                            <button key={candidate.key} type="button"
                                    className={`nav-item ${candidate.key === selected ? 'is-selected' : ''}`}
                                    disabled={!available.has(candidate.key)} onClick={() => setSelected(candidate.key)}>
                                {candidate.label}
                            </button>
                        ))}
                    </div>
                ))}
            </nav>
            <section className="card view-content">
                <header className="view-heading">
                    <h2>{spec?.label ?? 'View'}</h2>
                    {produced && <span className="muted">{spec?.source}</span>}
                    <span className="toolbar-spacer" />
                    {produced && spec && spec.interactive && spec.static && (
                        <div className="segmented" role="group" aria-label="Rendering">
                            <button type="button" className={rendering === 'interactive' ? 'is-selected' : ''}
                                    onClick={() => setPreferred('interactive')}
                                    title="plotly.js: zoom, pan, rotate and read values by hovering">Interactive</button>
                            <button type="button" className={rendering === 'static' ? 'is-selected' : ''}
                                    onClick={() => setPreferred('static')}
                                    title="The Matplotlib drawing the saved figures use">Static</button>
                        </div>
                    )}
                </header>
                {pane}
            </section>
        </div>
    );
}
