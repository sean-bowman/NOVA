/* ========================================
   API CLIENT
   Typed calls to the NOVA server under /api. Every route is same-origin: the NOVA server
   serves the built app, and the Vite dev server proxies /api to it.
   Sean Bowman [11/16/2026]
   ======================================== */

import type {
    Config, ExportIndex, ExportResult, ExportTarget, FormState, Mode, ResultTable, RunEvent, Schema, ViewIndex,
} from './types';

export class ApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
        super(message);
        this.status = status;
    }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(path, init);
    if (!response.ok) {
        let message = `${response.status} ${response.statusText}`;
        try {
            const body = await response.json();
            if (body && typeof body.detail === 'string') {
                message = body.detail;
            }
        } catch {
            // The body was not JSON; the status line is the message
        }
        throw new ApiError(response.status, message);
    }
    return response.json() as Promise<T>;
}

function jsonBody(method: string, body: unknown): RequestInit {
    return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

export const api = {
    schema: () => request<Schema>('/api/schema'),
    formState: (config: Config) => request<FormState>('/api/schema/state', jsonBody('POST', config)),
    example: (name: string) => request<Config>(`/api/examples/${encodeURIComponent(name)}`),
    settings: () => request<{ themeMode: Mode }>('/api/settings'),
    saveSettings: (settings: { themeMode: Mode }) => request<{ themeMode: Mode }>('/api/settings', jsonBody('PUT', settings)),
    startRun: (config: Config, mode: Mode) => request<{ runId: number }>('/api/runs', jsonBody('POST', { config, mode })),
    cancelRun: () => request<{ cancelled: boolean }>('/api/runs/cancel', { method: 'POST' }),
    views: () => request<ViewIndex>('/api/views'),
    interactiveFigure: (key: string, mode: Mode) =>
        request<{ data: object[]; layout: Record<string, unknown> }>(`/api/views/${key}/interactive?mode=${mode}`),
    analysis: () => request<ResultTable>('/api/analysis'),
    exportIndex: () => request<ExportIndex>('/api/export'),
    exportTarget: (base: string, name: string) =>
        request<ExportTarget>(`/api/export/target?base=${encodeURIComponent(base)}&name=${encodeURIComponent(name)}`),
    exportFiles: (baseDir: string, files: string[]) => request<ExportResult>('/api/export', jsonBody('POST', { baseDir, files })),
    openOutput: (name: string) => request<{ opened: string }>('/api/export/open', jsonBody('POST', { what: 'file', name })),
    openFolder: (baseDir: string, name: string) =>
        request<{ opened: string }>('/api/export/open', jsonBody('POST', { what: 'folder', baseDir, name })),
};

interface WindowBridge {
    browseFolder: (initial: string) => Promise<string>;
}

/**
 * The desktop window's native calls (pywebview's bridge, novaWeb/__main__.py WindowApi), or null
 * in a browser. pywebview attaches the bridge after the page loads and fires pywebviewready.
 */
export function windowBridge(): WindowBridge | null {
    const bridge = (window as unknown as { pywebview?: { api?: Partial<WindowBridge> } }).pywebview?.api;
    return bridge && typeof bridge.browseFolder === 'function' ? (bridge as WindowBridge) : null;
}

/**
 * A static view: the PNG's URL, or the drawer's message when the run lacks the view's data.
 */
export async function staticFigure(key: string, mode: Mode, width: number, height: number, ratio: number,
                                   signal: AbortSignal): Promise<{ url: string } | { message: string }> {
    const query = `mode=${mode}&width=${Math.round(width)}&height=${Math.round(height)}&ratio=${ratio.toFixed(2)}`;
    const response = await fetch(`/api/views/${key}/static?${query}`, { signal });
    if (!response.ok) {
        throw new ApiError(response.status, `${response.status} ${response.statusText}`);
    }
    if ((response.headers.get('Content-Type') || '').startsWith('application/json')) {
        return response.json();
    }
    return { url: URL.createObjectURL(await response.blob()) };
}

/**
 * Subscribe to run events. EventSource reconnects on its own, and the server opens every
 * connection with a snapshot, so a reconnect resynchronizes the state.
 */
export function subscribeRunEvents(onEvent: (event: RunEvent) => void, onConnection: (open: boolean) => void): () => void {
    const source = new EventSource('/api/runs/events');
    source.onopen = () => onConnection(true);
    source.onerror = () => onConnection(false);
    source.onmessage = (message) => {
        try {
            onEvent(JSON.parse(message.data) as RunEvent);
        } catch {
            // A malformed event is dropped; the next snapshot corrects the state
        }
    };
    return () => source.close();
}
