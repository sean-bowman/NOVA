/* ========================================
   OUTPUT PREVIEW
   One of a run's outputs, shown in the Export dialog before it is exported: an image as itself,
   an STL surface in plotly.js's WebGL viewer (turn, zoom, pan), and a text, CSV or JSON file as
   its first lines. The server reads the STL into shared vertices and triangles
   (novaGui.outputs.stlMesh), thinning a surface too large to draw quickly, and says so.
   Sean Bowman [11/19/2026]
   ======================================== */

import { useEffect, useRef, useState } from 'react';

import { api, exportFileUrl } from '../api';
import { CloseIcon } from '../components/Icons';
import type { Mode, OutputFile } from '../types';
import { loadPlotly } from '../view/PlotlyFigure';
import { formatSize } from './fileSize';

const textLines = 400;          // lines of a text file the preview shows

function cssColor(name: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function MeshView({ runId, name, mode }: { runId: number | null; name: string; mode: Mode }) {
    const host = useRef<HTMLDivElement>(null);
    const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
    const [note, setNote] = useState('');

    useEffect(() => {
        let cancelled = false;
        const element = host.current;
        setState('loading');
        Promise.all([loadPlotly(), api.exportMesh(runId, name)])
            .then(([Plotly, mesh]) => {
                if (cancelled || !element) {
                    return;
                }
                setNote(mesh.shown < mesh.triangles
                    ? `${mesh.triangles.toLocaleString()} triangles, drawn thinned to ${mesh.shown.toLocaleString()}`
                    : `${mesh.triangles.toLocaleString()} triangles`);
                const axis = { backgroundcolor: cssColor('--bg'), gridcolor: cssColor('--border'), color: cssColor('--text-muted'),
                               showbackground: true };
                return Plotly.react(element, [{
                    type: 'mesh3d', x: mesh.x, y: mesh.y, z: mesh.z, i: mesh.i, j: mesh.j, k: mesh.k,
                    color: cssColor('--accent'), flatshading: true, hoverinfo: 'skip',
                    lighting: { ambient: 0.45, diffuse: 0.8, specular: 0.15, roughness: 0.6 },
                } as unknown as Plotly.Data], {
                    paper_bgcolor: cssColor('--surface'), margin: { l: 0, r: 0, t: 0, b: 0 },
                    scene: { aspectmode: 'data', xaxis: axis, yaxis: axis, zaxis: axis },
                    font: { color: cssColor('--text') },
                } as Partial<Plotly.Layout>, { displaylogo: false, responsive: true }).then(() => {
                    if (!cancelled) {
                        setState('ready');
                    }
                });
            })
            .catch((failure: Error) => {
                if (!cancelled) {
                    setNote(failure.message);
                    setState('error');
                }
            });
        return () => {
            cancelled = true;
            if (element) {
                loadPlotly().then((Plotly) => Plotly.purge(element)).catch(() => undefined);
            }
        };
    }, [runId, name, mode]);

    return (
        <>
            <div className="preview-stage">
                <div ref={host} className="plotly-host" />
                {state === 'loading' && <div className="figure-overlay"><span className="spinner" /> Reading the surface</div>}
                {state === 'error' && <div className="figure-overlay figure-message">{note}</div>}
            </div>
            {state === 'ready' && <p className="preview-note muted">{note}</p>}
        </>
    );
}

function TextView({ runId, name }: { runId: number | null; name: string }) {
    const [text, setText] = useState<string | null>(null);
    const [note, setNote] = useState('');

    useEffect(() => {
        let cancelled = false;
        setText(null);
        api.exportText(runId, name)
            .then((loaded) => {
                if (cancelled) {
                    return;
                }
                const lines = loaded.text.split(/\r?\n/);
                setText(lines.slice(0, textLines).join('\n'));
                setNote(lines.length > textLines || loaded.cut
                    ? `The first ${Math.min(lines.length, textLines)} lines of ${formatSize(loaded.bytes)}.` : formatSize(loaded.bytes));
            })
            .catch((failure: Error) => !cancelled && setNote(failure.message));
        return () => {
            cancelled = true;
        };
    }, [runId, name]);

    return (
        <>
            <pre className="preview-text">{text ?? ''}</pre>
            <p className="preview-note muted">{text === null && !note ? 'Reading' : note}</p>
        </>
    );
}

export function OutputPreview({ runId, file, mode, onClose }: { runId: number | null; file: OutputFile; mode: Mode; onClose: () => void }) {
    let body;
    if (file.preview === 'image') {
        body = (
            <div className="preview-stage">
                <img className="preview-image" src={exportFileUrl(runId, file.name)} alt={file.name} />
            </div>
        );
    } else if (file.preview === 'mesh') {
        body = <MeshView runId={runId} name={file.name} mode={mode} />;
    } else {
        body = <TextView runId={runId} name={file.name} />;
    }

    return (
        <aside className="card output-preview" aria-label={`Preview of ${file.name}`}>
            <div className="output-preview-head">
                <span className="mono output-preview-name" title={file.name}>{file.name}</span>
                <span className="muted">{formatSize(file.bytes)}</span>
                <span className="toolbar-spacer" />
                <button type="button" className="icon-button" aria-label="Close the preview" onClick={onClose}>
                    <CloseIcon />
                </button>
            </div>
            {body}
        </aside>
    );
}
