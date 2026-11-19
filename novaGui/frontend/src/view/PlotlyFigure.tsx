/* ========================================
   PLOTLY FIGURE
   A view's plotly figure, built on the server by NOVA's own builders and drawn here by
   plotly.js. plotly.js loads on the first figure, in its own chunk, so the window opens
   without it. The figure fills its pane and follows the pane's size.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useEffect, useRef, useState } from 'react';

import { api } from '../api';
import type { Mode } from '../types';

type PlotlyModule = typeof import('plotly.js-dist-min');

let plotlyPromise: Promise<PlotlyModule> | null = null;

function loadPlotly(): Promise<PlotlyModule> {
    if (!plotlyPromise) {
        plotlyPromise = import('plotly.js-dist-min').then((module) => (module as { default?: PlotlyModule }).default ?? module);
    }
    return plotlyPromise;
}

interface PlotlyFigureProps {
    viewKey: string;
    mode: Mode;
    runId: number | null;
}

export function PlotlyFigure({ viewKey, mode, runId }: PlotlyFigureProps) {
    const host = useRef<HTMLDivElement>(null);
    const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
    const [message, setMessage] = useState('');

    useEffect(() => {
        let cancelled = false;
        const element = host.current;
        setStatus('loading');

        Promise.all([loadPlotly(), api.interactiveFigure(viewKey, mode)])
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
                    scrollZoom: true,
                    toImageButtonOptions: { format: 'png', filename: `nova-${viewKey}`, scale: 2 },
                }).then(() => {
                    if (!cancelled) {
                        setStatus('ready');
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
    }, [viewKey, mode, runId]);

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
                const drawn = (element as unknown as { _fullLayout?: object })._fullLayout !== undefined;
                if (drawn && plotlyPromise && element.clientWidth > 0 && element.clientHeight > 0) {
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
            {status === 'loading' && <div className="figure-overlay"><span className="spinner" /> Drawing</div>}
            {status === 'error' && <div className="figure-overlay figure-message">{message}</div>}
        </div>
    );
}
