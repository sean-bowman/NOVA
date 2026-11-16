/* ========================================
   STATIC FIGURE
   A view's Matplotlib drawing, the one the Tkinter pane shows, rendered on the server at
   this pane's size and the display's pixel ratio. A resize asks for a new image once the
   pane has settled.
   Sean Bowman [11/16/2026]
   ======================================== */

import { useEffect, useRef, useState } from 'react';

import { staticFigure } from '../api';
import type { Mode } from '../types';

const settleMs = 250;           // [ms] quiet time after a resize before a new image is drawn

interface StaticFigureProps {
    viewKey: string;
    mode: Mode;
    runId: number | null;
}

export function StaticFigure({ viewKey, mode, runId }: StaticFigureProps) {
    const host = useRef<HTMLDivElement>(null);
    const [size, setSize] = useState<{ width: number; height: number } | null>(null);
    const [image, setImage] = useState<string | null>(null);
    const [message, setMessage] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const element = host.current;
        if (!element) {
            return;
        }
        let timer: number | undefined;
        let first = true;
        const observer = new ResizeObserver(([entry]) => {
            window.clearTimeout(timer);
            const { width, height } = entry.contentRect;
            // The first size draws at once; later ones wait for the resize to settle
            timer = window.setTimeout(() => setSize({ width, height }), first ? 0 : settleMs);
            first = false;
        });
        observer.observe(element);
        return () => {
            observer.disconnect();
            window.clearTimeout(timer);
        };
    }, []);

    useEffect(() => {
        if (!size || size.width < 50 || size.height < 50) {
            return;
        }
        const controller = new AbortController();
        setLoading(true);
        staticFigure(viewKey, mode, size.width, size.height, window.devicePixelRatio || 1, controller.signal)
            .then((drawn) => {
                if ('url' in drawn) {
                    setImage((previous) => {
                        if (previous) {
                            URL.revokeObjectURL(previous);
                        }
                        return drawn.url;
                    });
                    setMessage('');
                } else {
                    setImage(null);
                    setMessage(drawn.message);
                }
                setLoading(false);
            })
            .catch((error: Error) => {
                if (error.name !== 'AbortError') {
                    setMessage(error.message);
                    setLoading(false);
                }
            });
        return () => controller.abort();
    }, [viewKey, mode, runId, size]);

    return (
        <div ref={host} className="figure-pane">
            {image && !message && <img className="static-image" src={image} alt="" draggable={false} />}
            {loading && <div className="figure-overlay"><span className="spinner" /> Drawing</div>}
            {!loading && message && <div className="figure-overlay figure-message">{message}</div>}
        </div>
    );
}
