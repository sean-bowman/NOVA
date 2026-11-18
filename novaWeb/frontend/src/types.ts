/* ========================================
   API TYPES
   The shapes the NOVA server sends: the Design form schema, run events, the view list, the
   result table and the export listing. They mirror novaWeb/schemaJson.py, session.py, views.py,
   analysis.py and outputs.py.
   Sean Bowman [11/16/2026]
   ======================================== */

export type Mode = 'dark' | 'light';

export type ConfigValue = string | number | boolean | null | ConfigValue[] | { [key: string]: ConfigValue };
export type Config = Record<string, ConfigValue>;

export interface Choice {
    label: string;
    value: ConfigValue;
}

export type FieldKind = 'bool' | 'int' | 'float' | 'text' | 'choice' | 'floatText';

export interface FieldSpec {
    type: 'field';
    id: string;
    key: string;
    label: string;
    kind: FieldKind;
    choices: Choice[];
    editable: boolean;
    default: ConfigValue;
    unit: string;
    dimension: string | null;
    help: string;
    advanced: boolean;
    fold: string | null;
    hidden: boolean;
    synthetic: boolean;
    optionHelp: Record<string, string>;
    conditional: boolean;
}

export interface OptionSpec {
    label: string;
    key: string | null;
    unit: string;
    dimension: string | null;
    sets: Config;
}

export interface SelectorSpec {
    type: 'selector';
    id: string;
    name: string;
    help: string;
    blank: string;
    required: boolean;
    advanced: boolean;
    fold: string | null;
    members: FieldSpec[];
    options: OptionSpec[];
    conditional: boolean;
}

export type ItemSpec = FieldSpec | SelectorSpec;

export interface GroupSpec {
    id: string;
    title: string;
    note: string;
    collapsed: boolean;
    items: ItemSpec[];
    conditional: boolean;
}

export interface UnitEntry {
    unit: string;
    scale: number;
    offset: number;
}

export interface Schema {
    groups: GroupSpec[];
    defaults: Config;
    examples: { title: string; name: string }[];
    units: Record<string, { si: string; units: UnitEntry[] }>;
    advancedFold: string;
    forcedFlags: string[];
}

export interface FormState {
    hidden: string[];
    expand: string[];
    /** Cross-field problems: warnings, a run with them asks before it starts */
    problems: string[];
    /** Row ids the problems name */
    flagged: string[];
}

/** A wall alloy's properties at one temperature (novaWeb.design.wallSample), SI */
export interface WallSample {
    material: string;
    temperatureK: number;
    thermalConductivity: number;
    density: number;
    elasticModulus: number;
    yieldStrength: number;
    cte: number;
    elongation: number;
    source: string;
    fallback: boolean;
    measured: Record<string, boolean>;
}

/** What the material store holds for an extension material: the note, and the fields it fills */
export interface ExtensionEntry {
    note: string;
    fill: Record<string, number>;
}

export type RunStateName = 'idle' | 'running' | 'done' | 'error' | 'cancelled';

export interface RunSummary {
    runId: number;
    ok: boolean;
    runName: string;
    elapsedSec: number;
    error: string;
}

/** A top-level stage of a run, from the progress events NOVA sends (NOVA.progress). */
export interface RunStage {
    key: string;
    label: string;
    state: 'pending' | 'running' | 'done' | 'failed';
    started: number | null;       // [s] on the run's own clock
    elapsed: number | null;       // [s] once finished
    expected: number | null;      // [s] on the last finished run
}

export interface RunSnapshot {
    type: 'snapshot';
    state: RunStateName;
    detail: string;
    fraction: number;
    ceiling: number;
    label: string;
    stageDetail: string;
    stages: RunStage[];
    runId: number | null;
    startedAt: number | null;
    log: string[];
    result: RunSummary | null;
}

export type RunEvent =
    | RunSnapshot
    | { type: 'log'; line: string }
    | { type: 'status'; state: RunStateName; detail: string }
    | { type: 'progress'; fraction: number; ceiling: number; label: string; stageDetail: string; stages: RunStage[] }
    | ({ type: 'result' } & RunSummary);

export interface ViewSpec {
    key: string;
    group: string;
    label: string;
    source: string;
    interactive: boolean;
    static: boolean;
}

export interface ViewIndex {
    views: ViewSpec[];
    available: string[];
    runId: number | null;
}

export interface ResultRow {
    label: string;
    cells: string[];
    unit: string;
    indent: boolean;
}

export interface ResultSection {
    title: string;
    columns: string[] | null;
    rows: ResultRow[];
}

export interface ResultTable {
    runId: number | null;
    runName: string;
    summary: string;
    sections: ResultSection[];
}

export interface OutputCategory {
    key: string;
    name: string;
    description: string;
}

export interface OutputFile {
    name: string;
    category: string;
    bytes: number;
}

export interface ExportIndex {
    categories: OutputCategory[];
    defaultBaseDir: string;
    runId: number | null;
    runName: string;
    files: OutputFile[];
}

export interface ExportTarget {
    target: string;
    exists: boolean;
}

export interface ExportResult {
    target: string;
    written: number;
    bytes: number;
}
