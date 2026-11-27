/* ========================================
   RUNS NOT RUN
   What the run bar says of a run a closed window left unrun (NotRunEntry): the fields its config
   changes from the shipped nozzle, so runs queued under one filename read apart, and when it was
   queued.
   Sean Bowman [11/27/2026]
   ======================================== */

import { changesSince, type FieldChange } from '../result/changes';
import type { NotRunEntry, Schema } from '../types';

/** The rows of the form whose value in the run's config differs from the shipped nozzle, in form order. */
export function notRunChanges(schema: Schema, entry: NotRunEntry): FieldChange[] {
    // A field added since the run was queued takes its default, as it does when the config goes to the form
    return changesSince(schema, schema.defaults, { ...schema.defaults, ...entry.config });
}

/** The changes in one line: the first `shown` as label and value, then how many more. */
export function changesText(changes: FieldChange[], shown = 3): string {
    if (changes.length === 0) {
        return 'the shipped nozzle';
    }
    const named = changes.slice(0, shown).map((change) => `${change.label} ${change.after}`).join(', ');
    const more = changes.length - shown;
    return more > 0 ? `${named} and ${more} more` : named;
}

/** When the run was queued, or '' when the store did not say. */
export function queuedText(queuedAt: number): string {
    if (!(queuedAt > 0)) {
        return '';
    }
    return `queued ${new Date(queuedAt * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`;
}
