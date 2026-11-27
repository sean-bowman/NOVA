/* ========================================
   FORM FIXTURES
   A small Design form schema for the tests. The unit factors and the field and selector specs
   are copies of what the server sends (novaGui/schemaJson.py) for these keys; the default
   values of the three selectors are test values. Two sections, Combustion and Regenerative
   Cooling, hold them with an Advanced settings fold and a hidden field, as the shipped schema
   does.
   Sean Bowman [11/27/2026]
   ======================================== */

import type { UnitTable } from '../src/design/units';
import type { Config, FieldSpec, FormState, GroupSpec, Schema, SelectorSpec } from '../src/types';

export const units: UnitTable = {
    length: { si: 'm', units: [
        { unit: 'm', scale: 1.0, offset: 0.0 },
        { unit: 'mm', scale: 0.001, offset: 0.0 },
        { unit: 'cm', scale: 0.01, offset: 0.0 },
        { unit: 'in', scale: 0.0254, offset: 0.0 },
        { unit: 'ft', scale: 0.30479999999999996, offset: 0.0 },
    ] },
    pressure: { si: 'Pa', units: [
        { unit: 'Pa', scale: 1.0, offset: 0.0 },
        { unit: 'kPa', scale: 1000.0, offset: 0.0 },
        { unit: 'MPa', scale: 1000000.0, offset: 0.0 },
        { unit: 'bar', scale: 100000.0, offset: 0.0 },
        { unit: 'psi', scale: 6894.7572931683635, offset: 0.0 },
        { unit: 'atm', scale: 101325.0, offset: 0.0 },
        { unit: 'torr', scale: 133.32236842105263, offset: 0.0 },
    ] },
    force: { si: 'N', units: [
        { unit: 'N', scale: 1.0, offset: 0.0 },
        { unit: 'kN', scale: 1000.0, offset: 0.0 },
        { unit: 'MN', scale: 1000000.0, offset: 0.0 },
        { unit: 'lbf', scale: 4.4482216152605005, offset: 0.0 },
    ] },
    temperature: { si: 'K', units: [
        { unit: 'K', scale: 1.0, offset: 0.0 },
        { unit: 'degC', scale: 1.0, offset: 273.15 },
        { unit: 'degR', scale: 0.5555555555555556, offset: 0.0 },
        { unit: 'degF', scale: 0.5555555555555429, offset: 255.37222222222223 },
    ] },
    massFlow: { si: 'kg/s', units: [
        { unit: 'kg/s', scale: 1.0, offset: 0.0 },
        { unit: 'g/s', scale: 0.001, offset: 0.0 },
        { unit: 'lbm/s', scale: 0.45359237, offset: 0.0 },
    ] },
};

/** A field spec with the server's defaults for whatever the test does not name. */
export function field(spec: Partial<FieldSpec> & Pick<FieldSpec, 'key' | 'label' | 'kind'>): FieldSpec {
    return {
        type: 'field', id: spec.key, choices: [], editable: false, default: null, unit: '', dimension: null, help: '',
        advanced: false, fold: null, hidden: false, synthetic: false, optionHelp: {}, conditional: false, ...spec,
    };
}

// -- Fields -- //

export const chamberPressure = field({
    key: 'chamberPressure', label: 'Chamber pressure', kind: 'float', default: 6894757.0, unit: 'Pa',
    dimension: 'pressure', help: 'Chamber stagnation pressure. 6.895 MPa is 1000 psia.',
});

export const maxWallTemperature = field({
    key: 'maxWallTemperature', label: 'Max wall temperature', kind: 'float', default: 800.0, unit: 'K',
    dimension: 'temperature',
});

export const divergingSectionType = field({
    key: 'divergingSectionType', label: 'Diverging section type', kind: 'choice', default: 'tic',
    choices: [
        { label: 'Truncated ideal contour (tic)', value: 'tic' },
        { label: 'Thrust-optimized parabola (top)', value: 'top' },
        { label: 'Thrust-optimized contour (toc)', value: 'toc' },
        { label: 'Conical (cone)', value: 'cone' },
    ],
});

export const ofRatio = field({ key: 'OFRatio', label: 'O/F ratio', kind: 'floatText', default: 5.5 });

export const nChannel = field({ key: 'nChannel', label: 'Number of channels', kind: 'int', default: 60 });

export const coolant = field({ key: 'coolant', label: 'Coolant species', kind: 'text', default: 'Hydrogen' });

export const makeCoolingChannels = field({
    key: 'makeCoolingChannels', label: 'Generate cooling channels', kind: 'bool', default: true,
});

export const designVariables = field({
    key: 'divergingSectionDesignVariables', label: 'Design vector', kind: 'text', fold: 'Advanced settings',
});

export const throatInletCurvature = field({
    key: 'throatInletCurvature', label: 'Throat inlet curvature', kind: 'float', default: 1.5, fold: 'Advanced settings',
});

export const plotsEnabled = field({ key: 'plotsEnabled', label: 'Plots enabled', kind: 'bool', default: false, hidden: true });

// -- Selectors -- //

export const engineSize: SelectorSpec = {
    type: 'selector', id: 'selector:Engine size', name: 'Engine size', help: '', blank: 'Thrust', required: true,
    advanced: false, fold: null, conditional: false,
    members: [
        field({ key: 'thrust', label: 'Thrust', kind: 'float', unit: 'N', dimension: 'force' }),
        field({ key: 'engineMassFlow', label: 'Engine mass flow', kind: 'float', unit: 'kg/s', dimension: 'massFlow' }),
    ],
    options: [
        { label: 'Thrust', key: 'thrust', unit: 'N', dimension: 'force', sets: {} },
        { label: 'Engine mass flow', key: 'engineMassFlow', unit: 'kg/s', dimension: 'massFlow', sets: {} },
    ],
};

export const nozzleExpansion: SelectorSpec = {
    type: 'selector', id: 'selector:Nozzle expansion', name: 'Nozzle expansion', help: '', blank: 'Expansion ratio',
    required: true, advanced: false, fold: null, conditional: false,
    members: [
        field({ key: 'expansionRatio', label: 'Expansion ratio', kind: 'float' }),
        field({ key: 'targetExitPressure', label: 'Target exit pressure', kind: 'float', unit: 'Pa', dimension: 'pressure' }),
    ],
    options: [
        { label: 'Expansion ratio', key: 'expansionRatio', unit: '', dimension: null, sets: {} },
        { label: 'Target exit pressure', key: 'targetExitPressure', unit: 'Pa', dimension: 'pressure', sets: {} },
    ],
};

export const regenTruncation: SelectorSpec = {
    type: 'selector', id: 'selector:Regen truncation', name: 'Regen truncation', help: '',
    blank: 'No truncation (full contour)', required: true, advanced: false, fold: null, conditional: false,
    members: [
        field({ key: 'regenTruncationType', label: 'Truncation type', kind: 'choice' }),
        field({ key: 'regenTruncationValue', label: 'Truncation value', kind: 'float' }),
    ],
    options: [
        { label: 'No truncation (full contour)', key: null, unit: '', dimension: null, sets: { regenTruncationType: 'none' } },
        { label: 'Truncate at recovery temperature', key: 'regenTruncationValue', unit: 'K', dimension: 'temperature',
          sets: { regenTruncationType: 'temp' } },
        { label: 'Truncate at area ratio', key: 'regenTruncationValue', unit: '', dimension: null,
          sets: { regenTruncationType: 'er' } },
    ],
};

// -- The form -- //

export const combustion: GroupSpec = {
    id: 'group1', title: 'Combustion', note: '', collapsed: false, conditional: false,
    items: [divergingSectionType, ofRatio, chamberPressure, engineSize, nozzleExpansion, designVariables,
            throatInletCurvature],
};

export const cooling: GroupSpec = {
    id: 'group3', title: 'Regenerative Cooling', note: '', collapsed: false, conditional: false,
    items: [makeCoolingChannels, nChannel, plotsEnabled, coolant, maxWallTemperature, regenTruncation],
};

export const defaults: Config = {
    divergingSectionType: 'tic', OFRatio: 5.5, chamberPressure: 6894757.0, thrust: 100000.0, engineMassFlow: null,
    expansionRatio: 40.0, targetExitPressure: null, divergingSectionDesignVariables: null, throatInletCurvature: 1.5,
    makeCoolingChannels: true, nChannel: 60, plotsEnabled: false, coolant: 'Hydrogen', maxWallTemperature: 800.0,
    regenTruncationType: 'none', regenTruncationValue: null,
};

export const schema: Schema = {
    groups: [combustion, cooling], defaults, examples: [], units, advancedFold: 'Advanced settings', forcedFlags: [],
};

export const quietForm: FormState = { hidden: [], expand: [], problems: [], flagged: [], notes: {} };
