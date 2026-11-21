/* ========================================
   API CLIENT
   Typed calls to the NOVA server under /api. Every route is same-origin: the NOVA server
   serves the built app, and the Vite dev server proxies /api to it. A run argument names one of
   the runs the server keeps; without it a route answers for the latest good run.
   Sean Bowman [11/16/2026]
   ======================================== */

import type {
    Config, ExportIndex, ExportResult, ExportTarget, ExtensionEntry, FormState, MeshPreview, Mode, ResultTable, RunEntry,
    RunEvent, RunList, Schema, Settings, Submitted, Sweep, SweepList, SweepRequest, ValidationDetail, ViewIndex, WallSample,
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

/** A query string from the values that are set: '?run=3&mode=dark', or ''. */
export function query(values: Record<string, string | number | null | undefined>): string {
    const parts = Object.entries(values)
        .filter(([, value]) => value !== null && value !== undefined && value !== '')
        .map(([key, value]) => `${key}=${encodeURIComponent(String(value))}`);
    return parts.length > 0 ? `?${parts.join('&')}` : '';
}

export const api = {
    schema: () => request<Schema>('/api/schema'),
    formState: (config: Config) => request<FormState>('/api/schema/state', jsonBody('POST', config)),
    example: (name: string) => request<Config>(`/api/examples/${encodeURIComponent(name)}`),
    wallMaterial: (name: string, temperatureK: number) =>
        request<WallSample>(`/api/materials/wall${query({ name, temperatureK })}`),
    extensionMaterial: (name: string) => request<ExtensionEntry>(`/api/materials/extension${query({ name })}`),
    settings: () => request<Settings>('/api/settings'),
    saveSettings: (settings: Partial<Settings>) => request<Settings>('/api/settings', jsonBody('PUT', settings)),
    runs: () => request<RunList>('/api/runs'),
    setBaseline: (runId: number | null) => request<{ baseline: number | null }>('/api/runs/baseline', jsonBody('PUT', { runId })),
    describeRun: (runId: number, fields: { title?: string; note?: string }) =>
        request<RunEntry>(`/api/runs/${runId}`, jsonBody('PATCH', fields)),
    deleteRun: (runId: number) => request<{ deleted: number }>(`/api/runs/${runId}`, { method: 'DELETE' }),
    startRun: (config: Config, mode: Mode) => request<Submitted>('/api/runs', jsonBody('POST', { config, mode })),
    cancelRun: (all = false) => request<{ cancelled: boolean }>('/api/runs/cancel', jsonBody('POST', { all })),
    unqueue: (queueId: number) => request<{ unqueued: number }>(`/api/queue/${queueId}`, { method: 'DELETE' }),
    sweeps: () => request<SweepList>('/api/sweeps'),
    addSweep: (sweep: SweepRequest) => request<Sweep>('/api/sweeps', jsonBody('POST', sweep)),
    resumeSweep: (sweepId: number) => request<{ queued: number }>(`/api/sweeps/${sweepId}/resume`, { method: 'POST' }),
    deleteSweep: (sweepId: number) => request<{ deleted: number; runs: number[] }>(`/api/sweeps/${sweepId}`, { method: 'DELETE' }),
    sweepFigure: (sweepId: number, number: string, mode: Mode) =>
        request<{ data: object[]; layout: Record<string, unknown> }>(`/api/sweeps/${sweepId}/figure${query({ number, mode })}`),
    views: (run: number | null) => request<ViewIndex>(`/api/views${query({ run })}`),
    interactiveFigure: (key: string, mode: Mode, run: number | null, compare: number | null, revision?: number) =>
        request<{ data: object[]; layout: Record<string, unknown> }>(
            `/api/views/${key}/interactive${query({ mode, run, compare, rev: revision })}`),
    analysis: (run: number | null, baseline: number | null) => request<ResultTable>(`/api/analysis${query({ run, baseline })}`),
    validationModel: (model: string) => request<ValidationDetail>(`/api/validation/${encodeURIComponent(model)}`),
    exportIndex: (run: number | null) => request<ExportIndex>(`/api/export${query({ run })}`),
    exportTarget: (base: string, name: string) => request<ExportTarget>(`/api/export/target${query({ base, name })}`),
    exportText: (run: number | null, name: string) =>
        request<{ text: string; bytes: number; cut: boolean }>(`/api/export/file${query({ run, name })}`),
    exportMesh: (run: number | null, name: string) => request<MeshPreview>(`/api/export/mesh${query({ run, name })}`),
    exportFiles: (run: number | null, baseDir: string, files: string[]) =>
        request<ExportResult>('/api/export', jsonBody('POST', { runId: run, baseDir, files })),
    openOutput: (run: number | null, name: string) =>
        request<{ opened: string }>('/api/export/open', jsonBody('POST', { what: 'file', runId: run, name })),
    openFolder: (run: number | null, baseDir: string, name: string) =>
        request<{ opened: string }>('/api/export/open', jsonBody('POST', { what: 'folder', runId: run, baseDir, name })),
};

/** The URL an image file of a run is previewed from. */
export function exportFileUrl(run: number | null, name: string): string {
    return `/api/export/file${query({ run, name })}`;
}

interface WindowBridge {
    browseFolder: (initial: string) => Promise<string>;
    openWindow?: (path: string, title: string) => Promise<boolean>;
}

/**
 * The desktop window's native calls (pywebview's bridge, novaGui/__main__.py WindowApi), or null
 * in a browser. pywebview attaches the bridge after the page loads and fires pywebviewready.
 */
export function windowBridge(): WindowBridge | null {
    const bridge = (window as unknown as { pywebview?: { api?: Partial<WindowBridge> } }).pywebview?.api;
    return bridge && typeof bridge.browseFolder === 'function' ? (bridge as WindowBridge) : null;
}

/**
 * Open a page of the app in a window of its own: a desktop window beside the main one, or in a
 * browser a popup window.
 */
export function openWindow(path: string, title: string): void {
    const bridge = windowBridge();
    if (bridge?.openWindow) {
        bridge.openWindow(path, title).catch(() => window.open(path, '_blank', 'popup,width=1100,height=760'));
        return;
    }
    window.open(path, '_blank', 'popup,width=1100,height=760');
}

/**
 * A static view: the PNG as a blob, or the drawer's message when the run lacks the view's data.
 */
export async function staticFigure(key: string, mode: Mode, run: number | null, width: number, height: number,
                                   ratio: number, signal?: AbortSignal): Promise<{ blob: Blob } | { message: string }> {
    const path = `/api/views/${key}/static${query({ mode, run, width: Math.round(width), height: Math.round(height),
                                                    ratio: ratio.toFixed(2) })}`;
    const response = await fetch(path, { signal });
    if (!response.ok) {
        let message = `${response.status} ${response.statusText}`;
        try {
            const body = await response.json();
            if (body && typeof body.detail === 'string') {
                message = body.detail;
            }
        } catch {
            // The status line is the message
        }
        throw new ApiError(response.status, message);
    }
    if ((response.headers.get('Content-Type') || '').startsWith('application/json')) {
        return response.json();
    }
    return { blob: await response.blob() };
}

/** The route of a run's report, against a baseline when one is given. */
export function runReportPath(run: number, baseline: number | null): string {
    return `/api/report${query({ run, baseline })}`;
}

/** The route of a sweep's report. */
export function sweepReportPath(sweepId: number): string {
    return `/api/sweeps/${sweepId}/report`;
}

/** A page this server writes, such as a report, as a blob; the server's reason when it refuses. */
export async function fetchPage(path: string): Promise<Blob> {
    const response = await fetch(path);
    if (!response.ok) {
        let message = `${response.status} ${response.statusText}`;
        try {
            const body = await response.json();
            if (body && typeof body.detail === 'string') {
                message = body.detail;
            }
        } catch {
            // The status line is the message
        }
        throw new ApiError(response.status, message);
    }
    return response.blob();
}

/** A name as one word for a file, the first word as typed: 'Chamber pressure sweep' to 'ChamberPressureSweep'. */
export function fileStem(text: string, fallback = 'nova'): string {
    const words = text.split(/[^A-Za-z0-9]+/).filter(Boolean);
    if (words.length === 0) {
        return fallback;
    }
    return words.map((word, at) => (at === 0 ? word : word[0].toUpperCase() + word.slice(1))).join('');
}

/** Save a blob as a download. */
export function saveBlob(blob: Blob, fileName: string): void {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = fileName;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
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
