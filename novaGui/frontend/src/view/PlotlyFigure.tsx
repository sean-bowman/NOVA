/* ========================================
   PLOTLY FIGURE
   A view's plotly figure, built on the server by NOVA's own builders and drawn here by
   plotly.js. plotly.js loads on the first figure, in its own chunk, so the window opens
   without it. The figure fills its pane and follows the pane's size.

   A figure drawn along the nozzle axis joins the pane's axial link (axialLink.ts): the mouse
   over it moves one cursor across every linked figure, and a zoom along the axis zooms them all.

   A figure of a running run that grows as the run goes on (the coolant circuit's passes) takes a
   revision: each new one fetches the figure again and draws it over the last in place, keeping
   the reader's zoom, with no loading overlay between.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useEffect, useId, useRef, useState } from 'react';

import { api } from '../api';
import type { Mode } from '../types';
import { axialAxes, pixelOf, stationAt, type AxialAxis, type AxialLink, type FullLayout } from './axialLink';

type PlotlyModule = typeof import('plotly.js-dist-min');

let plotlyPromise: Promise<PlotlyModule> | null = null;

export function loadPlotly(): Promise<PlotlyModule> {
    if (!plotlyPromise) {
        plotlyPromise = import('plotly.js-dist-min').then((module) => (module as { default?: PlotlyModule }).default ?? module);
    }
    return plotlyPromise;
}

interface PlotlyFigureProps {
    viewKey: string;
    mode: Mode;
    runId: number | null;
    compare?: number | null;        // a second run drawn over a line plot
    link?: AxialLink;
    scrollZoom?: boolean;           // the wheel zooms; off where it scrolls a grid of figures
    revision?: number;              // a live figure's revision: each new one draws it again
}

/** The plotly graph element and the internals the cursor reads. */
type Graph = HTMLDivElement & {
    _fullLayout?: FullLayout;
    on?: (event: string, handler: (data: Record<string, unknown>) => void) => void;
};

/** The axis range a relayout set, from its keys: [low, high], 'auto', or undefined if it set none. */
function rangeOf(update: Record<string, unknown>, name: string): [number, number] | 'auto' | undefined {
    if (update[`${name}.autorange`] === true) {
        return 'auto';
    }
    const whole = update[`${name}.range`];
    if (Array.isArray(whole) && whole.length === 2) {
        return [Number(whole[0]), Number(whole[1])];
    }
    const low = update[`${name}.range[0]`];
    const high = update[`${name}.range[1]`];
    if (low !== undefined && high !== undefined) {
        return [Number(low), Number(high)];
    }
    return undefined;
}

export function PlotlyFigure({ viewKey, mode, runId, compare = null, link, scrollZoom = true, revision }: PlotlyFigureProps) {
    const host = useRef<HTMLDivElement>(null);
    const cursor = useRef<HTMLDivElement>(null);
    const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
    const [message, setMessage] = useState('');
    const [drawn, setDrawn] = useState(0);
    const linkId = useId();

    useEffect(() => {
        let cancelled = false;
        const element = host.current;
        // A live figure's next revision draws over the one shown, without the loading overlay
        setStatus((current) => (revision !== undefined && current === 'ready' ? current : 'loading'));

        Promise.all([loadPlotly(), api.interactiveFigure(viewKey, mode, runId, compare, revision)])
            .then(([Plotly, figure]) => {
                if (cancelled || !element) {
                    return;
                }
                const layout: Record<string, unknown> = { ...figure.layout, autosize: true };
                delete layout.width;
                delete layout.height;
                return Plotly.react(element, figure.data as Plotly.Data[], layout as Partial<Plotly.Layout>, {
                    responsive: true,
                    displaylogo: false,
                    scrollZoom,
                    toImageButtonOptions: { format: 'png', filename: `nova-${viewKey}`, scale: 2 },
                }).then(() => {
                    if (!cancelled) {
                        setStatus('ready');
                        setDrawn((count) => count + 1);
                    }
                });
            })
            .catch((error: Error) => {
                if (!cancelled) {
                    setMessage(error.message);
                    setStatus('error');
                }
            });

        return () => {
            cancelled = true;
        };
    }, [viewKey, mode, runId, compare, scrollZoom, revision]);

    // plotly.js's own responsive mode follows the window only. The pane also changes size when the
    // form beside it is dragged wider or a hidden pane is shown, so the figure follows the pane.
    useEffect(() => {
        const element = host.current;
        if (!element) {
            return;
        }
        let frame = 0;
        const observer = new ResizeObserver(() => {
            window.cancelAnimationFrame(frame);
            frame = window.requestAnimationFrame(() => {
                const ready = (element as Graph)._fullLayout !== undefined;
                if (ready && plotlyPromise && element.clientWidth > 0 && element.clientHeight > 0) {
                    plotlyPromise.then((Plotly) => Plotly.Plots.resize(element)).catch(() => undefined);
                }
            });
        });
        observer.observe(element);
        return () => {
            observer.disconnect();
            window.cancelAnimationFrame(frame);
        };
    }, []);

    // -- The axial cursor and zoom, once a figure is drawn -- //
    useEffect(() => {
        const graph = host.current as Graph | null;
        const overlay = cursor.current;
        if (!link || !graph || !overlay || status !== 'ready' || !plotlyPromise) {
            return;
        }
        let axes: AxialAxis[] = axialAxes(graph._fullLayout);
        if (axes.length === 0) {
            return;
        }
        let station: number | null = null;
        let inside = false;
        let applying = false;
        let alive = true;
        const plotly = plotlyPromise;

        const draw = () => {
            overlay.replaceChildren();
            if (station === null) {
                return;
            }
            let labelled = false;
            for (const { axis, subplots } of axes) {
                const left = pixelOf(axis, station);
                if (left === null) {
                    continue;
                }
                for (const { yaxis } of subplots) {
                    const line = document.createElement('div');
                    line.className = 'axial-cursor';
                    line.style.left = `${left}px`;
                    line.style.top = `${yaxis._offset}px`;
                    line.style.height = `${yaxis._length}px`;
                    overlay.appendChild(line);
                }
                if (!labelled) {
                    const top = Math.min(...subplots.map(({ yaxis }) => yaxis._offset));
                    const label = document.createElement('div');
                    label.className = 'axial-cursor-label';
                    label.textContent = `x ${station.toFixed(4)} m`;
                    label.style.left = `${left}px`;
                    label.style.top = `${top}px`;
                    overlay.appendChild(label);
                    labelled = true;
                }
            }
        };

        // Another figure's cursor reads this figure's values at its station, where the hover reads along x
        const readsAlongX = () => String(graph._fullLayout?.hovermode ?? '').startsWith('x');
        const subplotIds = () => axes.flatMap(({ subplots }) => subplots.map(({ id }) => id));

        const stopCursor = link.onCursor((move) => {
            station = move.station;
            draw();
            if (move.source === linkId || !alive) {
                return;
            }
            plotly.then((Plotly) => {
                const fx = (Plotly as unknown as { Fx: { hover: (...args: unknown[]) => void; unhover: (graph: HTMLElement) => void } }).Fx;
                if (move.station === null || !readsAlongX()) {
                    fx.unhover(graph);
                } else {
                    fx.hover(graph, { xval: move.station }, subplotIds());
                }
            }).catch(() => undefined);
        });

        const onMove = (event: MouseEvent) => {
            const box = graph.getBoundingClientRect();
            const at = stationAt(axes, event.clientX - box.left, event.clientY - box.top);
            if (at !== null) {
                inside = true;
                link.moveCursor({ station: at, source: linkId });
            } else if (inside) {
                inside = false;
                link.moveCursor({ station: null, source: linkId });
            }
        };
        const onLeave = () => {
            inside = false;
            link.moveCursor({ station: null, source: linkId });
        };
        graph.addEventListener('mousemove', onMove);
        graph.addEventListener('mouseleave', onLeave);

        // A zoom along the axis here zooms the other figures; theirs zoom this one
        const stopZoom = link.onZoom((zoom) => {
            if (zoom.source === linkId || !alive) {
                return;
            }
            const update: Record<string, unknown> = {};
            for (const { axis, drives } of axes) {
                if (drives) {
                    if (zoom.range) {
                        update[`${axis._name}.range`] = zoom.range;
                    } else {
                        update[`${axis._name}.autorange`] = true;
                    }
                }
            }
            applying = true;
            plotly.then((Plotly) => Plotly.relayout(graph, update)).catch(() => undefined).finally(() => {
                applying = false;
            });
        });
        const onRelayout = (update: Record<string, unknown>) => {
            axes = axialAxes(graph._fullLayout);
            draw();
            if (applying) {
                return;
            }
            for (const { axis } of axes) {
                const range = rangeOf(update, axis._name);
                if (range !== undefined) {
                    link.zoom({ range: range === 'auto' ? null : range, source: linkId });
                    return;
                }
            }
        };
        graph.on?.('plotly_relayout', onRelayout);
        const onAfterPlot = () => {
            axes = axialAxes(graph._fullLayout);
        };
        graph.on?.('plotly_afterplot', onAfterPlot);

        return () => {
            alive = false;
            stopCursor();
            stopZoom();
            graph.removeEventListener('mousemove', onMove);
            graph.removeEventListener('mouseleave', onLeave);
            const emitter = graph as unknown as { removeListener?: (event: string, handler: unknown) => void };
            emitter.removeListener?.('plotly_relayout', onRelayout);
            emitter.removeListener?.('plotly_afterplot', onAfterPlot);
            overlay.replaceChildren();
        };
    }, [link, status, drawn, linkId]);

    // Release WebGL contexts and listeners when the pane goes away
    useEffect(() => {
        const element = host.current;
        return () => {
            if (element && plotlyPromise) {
                plotlyPromise.then((Plotly) => Plotly.purge(element)).catch(() => undefined);
            }
        };
    }, []);

    return (
        <div className="figure-pane">
            <div ref={host} className="plotly-host" />
            <div ref={cursor} className="axial-cursor-layer" aria-hidden="true" />
            {status === 'loading' && <div className="figure-overlay"><span className="spinner" /> Drawing</div>}
            {status === 'error' && <div className="figure-overlay figure-message">{message}</div>}
        </div>
    );
}
