/* ========================================
   API TYPES
   The shapes the NOVA server sends: the Design form schema, run events, the view list, the
   result table and the export listing. They mirror novaGui/schemaJson.py, session.py, views.py,
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

/** A wall alloy's properties at one temperature (novaGui.design.wallSample), SI */
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

export type StageState = 'pending' | 'running' | 'done' | 'failed';

/** One finished iteration of an iterative solve, as NOVA.progress reports it. */
export interface StageIteration {
    index: number;                            // numbered from 1
    t: number;                                // [s] on the run's own clock
    metrics: Record<string, number | null>;   // SI
}

/** A stage of a run (novaGui.progress.RunProgress.stageList), top-level or one level inside. */
export interface StageNode {
    key: string;
    label: string;
    state: StageState;
    started: number | null;       // [s] on the run's own clock
    elapsed: number | null;       // [s] once finished
    expected: number | null;      // [s] on the last finished run
    detail: string;               // what runs below it while it runs: 'Up pass 45%'
    iterationName: string | null; // 'pass', 'evaluation'
    iterationCount: number;
    iterations: StageIteration[]; // the latest ones, oldest first
    expectedIterations: number | null;
}

/** A top-level stage, with the share of the run it stands for and its sub-stages. */
export interface RunStage extends StageNode {
    weight: number;               // [s] its expected time, or the nominal one before any run
    note: string;                 // 'pass 4', '45%', or once finished '7 passes'
    fraction: number | null;      // how far a loop reported in the stage itself has gone
    children: StageNode[];
}

/** The run fields a progress event carries; a snapshot carries them too. */
export interface RunProgressFields {
    runId: number | null;
    t: number;                    // [s] the run's own clock at its latest event
    expectedRun: number | null;   // the run whose times the stages expect
    fraction: number;
    ceiling: number;
    label: string;
    stageDetail: string;
    stages: RunStage[];
}

export interface RunSnapshot extends RunProgressFields {
    type: 'snapshot';
    state: RunStateName;
    detail: string;
    startedAt: number | null;
    log: string[];
    result: RunSummary | null;
}

export type RunEvent =
    | RunSnapshot
    | { type: 'log'; line: string }
    | { type: 'status'; state: RunStateName; detail: string; runId?: number | null }
    | ({ type: 'progress' } & RunProgressFields)
    | ({ type: 'result' } & RunSummary);

export interface ViewSpec {
    key: string;
    group: string;
    label: string;
    source: string;
    interactive: boolean;
    static: boolean;
}

/** The views of the last good run, and that run: its id, name, time and the config it ran. */
export interface ViewIndex {
    views: ViewSpec[];
    available: string[];
    runId: number | null;
    runName: string;
    elapsedSec: number | null;
    config: Config | null;
}

export interface Settings {
    themeMode: Mode;
    formWidth: number | null;     // [px] the Design form's width beside the result pane
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
