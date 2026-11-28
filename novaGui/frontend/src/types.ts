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
    /** The problems naming each flagged row, written under it */
    notes: Record<string, string[]>;
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
    label: string;
    stageDetail: string;
    stages: RunStage[];
}

/** A warning a run raised, once per category and message, with how many times it came. */
export interface RunWarning {
    category: string;             // 'UserWarning', 'RuntimeWarning'
    message: string;
    where: string;                // the file and line that raised it: 'ceaInterface.py:409'
    count: number;
}

/** The views a running run's contour stage settled, which draw before the run finishes. */
export interface PartialRun {
    runId: number;
    views: string[];
    revision?: number;            // the circuit passes the run has kept, in a snapshot
}

/** A run waiting its turn (novaGui.session.QueuedRun.entry). */
export interface QueueEntry {
    queueId: number;
    label: string;                // its config's filename, or a sweep's point
    runName: string;
    sweepId: number | null;
    point: number | null;         // the sweep point's index, from 0
}

/** A run a closed window left unrun: queued on its own, or going, when NOVA last closed (novaGui.session.RunSession.notRunList). */
export interface NotRunEntry {
    notRunId: number;
    label: string;                // what the queue called it: its config's filename, or the label it was queued with
    runName: string;
    config: Config;
    mode: Mode;                   // the figures' palette it was queued with
    queuedAt: number;             // [s] epoch, 0 when the store did not say
    reason: string;               // 'NOVA closed before it ran' or 'NOVA closed while it ran'
}

export interface RunSnapshot extends RunProgressFields {
    type: 'snapshot';
    state: RunStateName;
    detail: string;
    startedAt: number | null;
    log: string[];
    result: RunSummary | null;
    partial: PartialRun | null;
    baseline: number | null;
    warnings: RunWarning[];       // the run in progress, or the last one started
    queue: QueueEntry[];
    notRun?: NotRunEntry[];
}

export type RunEvent =
    | RunSnapshot
    | { type: 'log'; line: string }
    | { type: 'status'; state: RunStateName; detail: string; runId?: number | null }
    | ({ type: 'progress' } & RunProgressFields)
    | ({ type: 'partial' } & PartialRun)
    | { type: 'iterations'; runId: number; revision: number }
    | { type: 'warning'; runId: number; warnings: RunWarning[] }
    | ({ type: 'result' } & RunSummary)
    | { type: 'runs'; baseline: number | null }
    | { type: 'queue'; queue: QueueEntry[] }
    | { type: 'notRun'; notRun: NotRunEntry[] }
    | { type: 'sweeps' }
    | { type: 'plumeSweeps'; runId: number }
    | ({ type: 'settings' } & Settings);

/** Where a run asked for went: started (position 0, with its id) or queued (its place from 1). */
export interface Submitted {
    queueId: number;
    runId: number | null;
    position: number;
}

/** One of a run's headline numbers as the worker records it (novaGui.worker.headlineNumbers). */
export interface RunNumber {
    key: string;
    label: string;
    value: string;                // text, in the unit given
    unit: string;
    tone: '' | 'warn';
}

/** A kept finished run, as the run list carries it (novaGui.session.RunRecord.entry). */
export interface RunEntry {
    runId: number;
    runName: string;              // the config's filename, which names its outputs
    title: string;                // the name given to the run, '' for none
    note: string;
    elapsedSec: number;
    headline: string;             // thrust, delivered Isp, propellants
    numbers: RunNumber[];         // the headline numbers, [] for a run saved before they were recorded
    sweep: { sweepId: number; index: number } | null;
    finishedAt: number;           // [s] epoch
    config: Config | null;
    warnings: RunWarning[];
    bytes: number;                // [B] its files in the run store, 0 for a run held in memory
    saved: boolean;               // the run store holds it
}

export type SweepPointState = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

/** A field a sweep varies, its values in backend values and as the table shows them. */
export interface SweepField {
    key: string;
    label: string;
    kind: FieldKind;
    dimension: string | null;
    unit: string;                 // the display unit its values were entered in
    values: ConfigValue[];
    texts: string[];
}

export interface SweepPoint {
    index: number;
    at: number[];                 // the index of its value in each field
    values: Record<string, ConfigValue>;
    texts: string[];
    state: SweepPointState;
    runId: number | null;
    error: string;
    kept: boolean;                // its run is still kept
    numbers: Record<string, { text: string; value: number | null; tone: '' | 'warn' }>;
}

/** A trade sweep as its table reads it (novaGui.sweeps.table). */
export interface Sweep {
    sweepId: number;
    name: string;
    createdAt: number;            // [s] epoch
    config: Config;
    fields: SweepField[];
    numbers: { key: string; label: string; unit: string }[];
    counts: Record<SweepPointState, number>;
    points: SweepPoint[];
}

export interface SweepList {
    sweeps: Sweep[];              // newest first
    maxPoints: number;
    maxSeries: number;
}

/** A sweep as the dialog asks for it: values in backend values, entered in `unit`. */
export interface SweepRequest {
    name: string;
    config: Config;
    mode: Mode;
    fields: { key: string; unit: string; values: ConfigValue[] }[];
}

export type PlumePointState = 'queued' | 'running' | 'done' | 'refused' | 'failed' | 'cancelled';

/** A number column of a plume sweep's table, with the validation status of the models behind it. */
export interface PlumeColumn {
    key: string;
    label: string;
    unit: string;
    validation: ValidationBadgeInfo | null;
}

/** One ambient or power level of a plume sweep (novaGui.plumeSweeps.table). */
export interface PlumePoint {
    index: number;
    ambient: number;              // [Pa]
    fraction: number;             // [-] power level, 1 for an ambient sweep
    label: string;                // the ambient in the sweep's unit, or the power level
    state: PlumePointState;
    error: string;                // why a point was refused, failed or not solved
    trustworthy: boolean | null;  // the drawn march's mass error is within its bound; null before it is solved
    jetType: string;
    notes: string[];              // the march's own notes on the solve
    cells: Record<string, { text: string; tone: '' | 'warn' }>;
}

export type PlumeSweepKind = 'ambient' | 'throttle';

/** Where a throttle sweep's nozzle separates (novaGui.plumeSweeps.separation). */
export interface PlumeSeparation {
    fraction: number;             // [-] at the criterion the march refuses on
    lowFraction: number;          // [-] at the low end of the criterion's quoted spread
    ratio: number;
    lowRatio: number;
    limit: string;                // the limit as a sentence
    bias: string;                 // the frozen gas state's bias on it, as a sentence
}

/** A run's plume solved over a list of ambients, or over a list of power levels at one ambient, kept with the run. */
export interface PlumeSweep {
    runId: number;
    number: number;               // within its run
    kind: PlumeSweepKind;
    name: string;
    createdAt: number;            // [s] epoch
    unit: string;
    reach: number;                // [lip radii] drawn
    ambient: number | null;       // [Pa] a throttle sweep's held ambient
    ambientText: string | null;
    lip: { pressure: number; pressureText: string } | null;
    separation: PlumeSeparation | null;
    columns: PlumeColumn[];
    counts: Record<PlumePointState, number>;
    badge: ValidationBadgeInfo | null;
    points: PlumePoint[];
}

export interface PlumeSweepList {
    runId: number;
    sweeps: PlumeSweep[];         // newest first
    maxPoints: number;
    nearReach: number;            // [lip radii] the reach the march conserves mass over
    maxReach: number;             // [lip radii]
    maxFraction: number;          // [-] the highest power level a throttle sweep takes
    separationRatio: number;      // the exit pressure ratio the march refuses on as separated
    separationSpreadLow: number;  // the low end of that criterion's quoted spread
    maxPressureRatio: number;     // the exit pressure ratio a throttle sweep's first ambient puts rated power at
}

/** A plume sweep as the dialog asks for it: pressures in Pa, entered in `unit`, power levels as fractions. */
export type PlumeSweepRequest = { name: string; unit: string; reach: number } & (
    { kind: 'ambient'; ambients: number[] } | { kind: 'throttle'; ambient: number; fractions: number[] });

/** The run store the server keeps runs in between launches (novaGui.runStore). */
export interface RunStoreInfo {
    folder: string;
    unnamedRuns: number;          // unnamed runs kept, besides the named ones and the baseline
    bytes: number;                // [B] the kept runs' files
    byteLimit: number;            // [B] past which unnamed runs go
}

export interface RunList {
    runs: RunEntry[];             // newest first
    baseline: number | null;
    latest: number | null;        // the latest good run
    running: { runId: number; config: Config | null; views: string[]; warnings: RunWarning[] } | null;
    store: RunStoreInfo | null;   // null when the server keeps runs in memory alone
}

export interface ViewSpec {
    key: string;
    group: string;
    label: string;
    source: string;
    interactive: boolean;
    static: boolean;
    comparable: boolean;          // a line plot that can draw a second run over the first
    byPass: boolean;              // a jacket view, which draws one pass of the coolant at a time
}

/** A pass of a run's coolant the jacket views can draw: a multi-pass jacket's down or up pass, or the extension circuit's. */
export interface CoolantPass {
    key: string;
    label: string;
}

/**
 * The views of a run, and that run: its id, name, time and the config it ran. A run still going
 * (`partial`) lists the views its contour stage settled.
 */
export interface ViewIndex {
    views: ViewSpec[];
    available: string[];
    runId: number | null;
    runName: string;
    elapsedSec: number | null;
    config: Config | null;
    partial: boolean;
    loadError: string;            // why the run's saved result does not load, '' when it does
    passes: CoolantPass[];        // the passes the jacket views can draw, in the order the picker lists them
    defaultPass: string | null;   // the pass the jacket reports, which they draw unless another is picked
}

export interface Settings {
    themeMode: Mode;
    formWidth: number | null;     // [px] the Design form's width beside the result pane
}

/** The server's liveness and what is running (novaGui.runningBuild). */
export interface Health {
    ok: boolean;
    viewsReady: boolean;
    version: string;
    build: 'standalone' | 'checkout';
    revision: string;             // the checkout's `git describe`; '' for the standalone build
    label: string;                // the line naming all of it, as the launcher's log starts
}

export type UpdateStatusName = 'newer' | 'current' | 'ahead' | 'none' | 'unreachable' | 'refused' | 'unreadable';

/** GitHub's latest release against the running version (novaGui.updates). */
export interface UpdateCheck {
    status: UpdateStatusName;
    running: string;
    build: 'standalone' | 'checkout';
    latest: string;               // the latest release's version, or ''
    url: string;                  // its release page, or ''
    published: string;            // its date, YYYY-MM-DD, or ''
    detail: string;               // why GitHub gave no answer to compare, or ''
}

export interface ResultRow {
    label: string;
    cells: string[];
    unit: string;
    indent: boolean;
    view: string | null;          // the figure that shows the row
    baseline?: string[] | null;   // the baseline run's cells, beside a baseline
    change?: string[] | null;     // the change from the baseline, one text per cell
    baselineOnly?: boolean;       // a row only the baseline has
}

export type ValidationStatusName = 'validated' | 'calibrated' | 'compared' | 'crossCheck' | 'unvalidated' | 'construction';

/** One model behind a reported result, as docs/validationStatus.json records it. */
export interface ValidationModel {
    id: string;
    name: string;
    status: ValidationStatusName;
    label: string;                // 'Cross-checked'
    reference: string;
    result: string;
    gap: string;                  // what would close it, '' where the record names nothing
    record: string;               // the record it comes from first, repository relative
}

/**
 * How far a headline number or a section can be trusted (novaGui.validationStatus.badge): the
 * weakest status among the models behind it, and each of them.
 */
export interface ValidationBadgeInfo {
    status: ValidationStatusName;
    label: string;
    meaning: string;
    models: ValidationModel[];
}

/** A model with the passages of its records that carry its status. */
export interface ValidationDetail extends ValidationModel {
    passages: { path: string; quote: string; text: string }[];
}

export interface ResultSection {
    title: string;
    columns: string[] | null;
    rows: ResultRow[];
    baselineOnly?: boolean;
    validation?: ValidationBadgeInfo | null;
}

/** One of the numbers drawn above the table (novaGui.analysis.headline). */
export interface HeadlineNumber {
    key: string;
    label: string;
    value: string;
    unit: string;
    detail: string;
    tone: '' | 'warn';
    view: string | null;
    baseline?: string | null;
    change?: string | null;
    validation?: ValidationBadgeInfo | null;
}

export interface ResultTable {
    runId: number | null;
    runName: string;
    summary: string;
    headline: HeadlineNumber[];
    sections: ResultSection[];
    baselineRun: number | null;   // the run set beside it, or null
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
    preview: 'image' | 'mesh' | 'text' | null;
}

/** An STL surface for the mesh viewer (novaGui.outputs.stlMesh). */
export interface MeshPreview {
    x: number[];
    y: number[];
    z: number[];
    i: number[];
    j: number[];
    k: number[];
    triangles: number;
    shown: number;
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
