/* ========================================
   API TYPES
   The shapes the NOVA server sends: the Design form schema, run events and the view list.
   They mirror novaWeb/schemaJson.py, novaWeb/session.py and novaWeb/views.py.
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
}

export type RunStateName = 'idle' | 'running' | 'done' | 'error' | 'cancelled';

export interface RunSummary {
    runId: number;
    ok: boolean;
    runName: string;
    elapsedSec: number;
    error: string;
}

export interface RunSnapshot {
    type: 'snapshot';
    state: RunStateName;
    detail: string;
    fraction: number;
    ceiling: number;
    label: string;
    runId: number | null;
    startedAt: number | null;
    log: string[];
    result: RunSummary | null;
}

export type RunEvent =
    | RunSnapshot
    | { type: 'log'; line: string }
    | { type: 'status'; state: RunStateName; detail: string }
    | { type: 'progress'; fraction: number; ceiling: number; label: string }
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
