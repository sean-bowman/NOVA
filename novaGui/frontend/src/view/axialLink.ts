/* ========================================
   AXIAL LINK
   One cursor and one zoom shared by every figure drawn along the nozzle axis. The contour, the
   flow fields, the near-wall state and the cooling plots all plot against "Nozzle axis [m]" in
   the same frame, so a station read on one is the same station on the others.

   A figure's axial axes are the x axes titled "Nozzle axis" and those that match one (the rows
   of a stacked plot share one x axis). The mouse over any of their subplots moves the cursor to
   that station: a line is drawn across every axial subplot of every linked figure, and the
   figures whose hover reads along x show their values at the station. Zooming the axis on one
   figure zooms it on the rest. The cursor coalesces to one move per frame.
   Sean Bowman [11/19/2026]
   ======================================== */

export interface PlotAxis {
    _id: string;
    _name: string;
    _offset: number;              // [px] from the graph's left (x) or top (y) edge
    _length: number;              // [px]
    range: [number, number];
    matches?: string;
    title?: { text?: string };
    l2p: (value: number) => number;
    p2l: (pixel: number) => number;
    d2l: (value: number) => number;
    l2d: (value: number) => number;
}

interface PlotEntry {
    xaxis: PlotAxis;
    yaxis: PlotAxis;
}

export interface FullLayout {
    _plots?: Record<string, PlotEntry>;
    hovermode?: string | boolean;
    [key: string]: unknown;
}

/** An axial x axis of a figure, with the subplots drawn on it. */
export interface AxialAxis {
    axis: PlotAxis;
    subplots: { id: string; yaxis: PlotAxis }[];
    drives: boolean;              // its range is its own, not matched to another axis
}

const axialTitle = /nozzle axis/i;

/** The axial x axes of a drawn figure. */
export function axialAxes(full: FullLayout | undefined): AxialAxis[] {
    if (!full || !full._plots) {
        return [];
    }
    const axes = Object.keys(full).filter((name) => /^xaxis\d*$/.test(name)).map((name) => full[name] as PlotAxis)
        .filter((axis) => axis && typeof axis._id === 'string');
    const titled = new Set(axes.filter((axis) => axialTitle.test(axis.title?.text ?? '')).map((axis) => axis._id));
    // A titled axis that matches another shares its range: the one it matches is axial too
    for (const axis of axes) {
        if (titled.has(axis._id) && axis.matches) {
            titled.add(axis.matches);
        }
    }
    const plots = full._plots;
    return axes.filter((axis) => titled.has(axis._id) || (axis.matches !== undefined && titled.has(axis.matches)))
        .map((axis) => ({
            axis,
            subplots: Object.keys(plots).filter((id) => plots[id].xaxis === axis).map((id) => ({ id, yaxis: plots[id].yaxis })),
            drives: !axis.matches,
        }))
        .filter((entry) => entry.subplots.length > 0);
}

/** [m] The station under a point of the graph, or null off every axial subplot. */
export function stationAt(axes: AxialAxis[], left: number, top: number): number | null {
    for (const { axis, subplots } of axes) {
        if (left < axis._offset || left > axis._offset + axis._length) {
            continue;
        }
        for (const { yaxis } of subplots) {
            if (top >= yaxis._offset && top <= yaxis._offset + yaxis._length) {
                return axis.l2d(axis.p2l(left - axis._offset));
            }
        }
    }
    return null;
}

/** [px] Where a station falls on an axis, from the graph's left edge, or null outside its range. */
export function pixelOf(axis: PlotAxis, station: number): number | null {
    const [low, high] = [Math.min(...axis.range), Math.max(...axis.range)];
    if (!(station >= low && station <= high)) {
        return null;
    }
    return axis._offset + axis.l2p(axis.d2l(station));
}

export interface CursorMove {
    station: number | null;       // [m], null when the mouse leaves
    source: string;
}

export interface AxialZoom {
    range: [number, number] | null;   // [m], null to fit the data again
    source: string;
}

export class AxialLink {
    private cursorListeners = new Set<(move: CursorMove) => void>();
    private zoomListeners = new Set<(zoom: AxialZoom) => void>();
    private pending: CursorMove | null = null;
    private frame = 0;

    moveCursor(move: CursorMove): void {
        this.pending = move;
        if (this.frame) {
            return;
        }
        this.frame = window.requestAnimationFrame(() => {
            this.frame = 0;
            const next = this.pending;
            this.pending = null;
            if (next) {
                this.cursorListeners.forEach((listener) => listener(next));
            }
        });
    }

    onCursor(listener: (move: CursorMove) => void): () => void {
        this.cursorListeners.add(listener);
        return () => this.cursorListeners.delete(listener);
    }

    zoom(zoom: AxialZoom): void {
        this.zoomListeners.forEach((listener) => listener(zoom));
    }

    onZoom(listener: (zoom: AxialZoom) => void): () => void {
        this.zoomListeners.add(listener);
        return () => this.zoomListeners.delete(listener);
    }
}
