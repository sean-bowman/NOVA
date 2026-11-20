/* ========================================
   RUN DETAILS
   One kept run in a dialog: its name and note, what it ran and when, and what can be done with it.
   The name and the note are saved as they lose focus, and when the dialog closes; Enter in the
   name saves it too. A named run stays in the run store however many runs follow it, as a trade
   sweep's run does until its sweep is deleted, where an unnamed one goes once the store is past
   its limits.

   Edit from this run puts the config the run ran into the Design form, so the form reads as that
   run did and the status strip names no changes until a field is edited. The baseline button makes
   the run the baseline, or clears it when it is. Delete asks once more, then removes the run and
   its files.
   Sean Bowman [11/19/2026]
   ======================================== */

import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '../api';
import { CloseIcon } from '../components/Icons';
import { formatSize } from '../export/fileSize';
import { formatClock } from '../run/stageText';
import type { RunEntry, RunStoreInfo } from '../types';
import { headlineOf } from './RunSelect';

interface RunDetailsProps {
    entry: RunEntry;
    baseline: number | null;
    store: RunStoreInfo | null;
    onEditFrom: (entry: RunEntry) => void;
    onBaseline: (runId: number | null) => void;
    onClose: () => void;
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

/** A name as the server keeps it: trimmed, with each run of spaces made one. */
function tidy(text: string): string {
    return text.split(/\s+/).filter(Boolean).join(' ');
}

function finishedText(epochSec: number): string {
    return new Date(epochSec * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function storeText(entry: RunEntry, store: RunStoreInfo | null): string {
    if (!store) {
        return 'This server keeps its runs in memory; they go when it closes.';
    }
    const where = entry.saved ? `Saved in ${store.folder}.` : 'Kept in memory, not in the run store.';
    const sweep = entry.sweep ? ` It is point ${entry.sweep.index + 1} of a trade sweep, and stays until the sweep is deleted.` : '';
    return `${where}${sweep} Named runs, sweep runs and the baseline stay. Unnamed runs go oldest first past `
        + `${store.unnamedRuns} of them, or past ${formatSize(store.byteLimit)} in all; the store holds ${formatSize(store.bytes)}.`;
}

export function RunDetails({ entry, baseline, store, onEditFrom, onBaseline, onClose, onNotify }: RunDetailsProps) {
    const [title, setTitle] = useState(entry.title);
    const [note, setNote] = useState(entry.note);
    const [confirming, setConfirming] = useState(false);
    const [deleting, setDeleting] = useState(false);
    const saved = useRef({ title: entry.title, note: entry.note });
    const nameInput = useRef<HTMLInputElement>(null);

    useEffect(() => nameInput.current?.focus(), []);

    // -- Save what changed; the run list follows the server's runs event -- //
    const commit = useCallback(() => {
        const fields: { title?: string; note?: string } = {};
        if (tidy(title) !== saved.current.title) {
            fields.title = title;
        }
        if (note.trim() !== saved.current.note) {
            fields.note = note;
        }
        if (Object.keys(fields).length === 0) {
            return;
        }
        saved.current = { title: tidy(title), note: note.trim() };
        api.describeRun(entry.runId, fields)
            .then((described) => {
                saved.current = { title: described.title, note: described.note };
            })
            .catch((failure: Error) => onNotify('error', `Run ${entry.runId} not saved`, failure.message));
    }, [entry.runId, title, note, onNotify]);

    const close = useCallback(() => {
        commit();
        onClose();
    }, [commit, onClose]);

    // Escape closes this dialog alone, ahead of the window's own Escape handling
    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                event.stopPropagation();
                if (confirming) {
                    setConfirming(false);
                } else {
                    close();
                }
            }
        };
        document.addEventListener('keydown', onKey, true);
        return () => document.removeEventListener('keydown', onKey, true);
    }, [close, confirming]);

    const remove = () => {
        setDeleting(true);
        api.deleteRun(entry.runId)
            .then(() => {
                onNotify('info', `Run ${entry.runId} deleted`, entry.title || entry.runName);
                onClose();
            })
            .catch((failure: Error) => {
                setDeleting(false);
                setConfirming(false);
                onNotify('error', `Run ${entry.runId} not deleted`, failure.message);
            });
    };

    const isBaseline = baseline === entry.runId;
    const facts = [entry.runName, headlineOf(entry)].filter(Boolean).join(' · ');
    const timing = [
        `Finished ${finishedText(entry.finishedAt)}`, `ran ${formatClock(entry.elapsedSec)}`,
        entry.bytes > 0 ? formatSize(entry.bytes) : '',
        entry.warnings.length > 0 ? (entry.warnings.length === 1 ? 'a warning' : `${entry.warnings.length} warnings`) : '',
    ].filter(Boolean).join(' · ');

    return (
        <div className="modal-scrim" onClick={close}>
            <div className="card modal run-details" role="dialog" aria-label={`Run ${entry.runId}`}
                 onClick={(event) => event.stopPropagation()}>
                <div className="run-details-head">
                    <h2>Run {entry.runId}</h2>
                    {isBaseline && <span className="run-chip">Baseline</span>}
                    <span className="toolbar-spacer" />
                    <button type="button" className="icon-button" aria-label="Close" onClick={close}>
                        <CloseIcon />
                    </button>
                </div>
                <label className="run-details-field">
                    <span>Name</span>
                    <input ref={nameInput} className="input" value={title} maxLength={80} placeholder="Unnamed"
                           onChange={(event) => setTitle(event.target.value)} onBlur={commit}
                           onKeyDown={(event) => event.key === 'Enter' && commit()} />
                </label>
                <label className="run-details-field">
                    <span>Note</span>
                    <textarea className="input run-note" value={note} maxLength={4000} rows={4}
                              placeholder="What this run tried, and what it showed"
                              onChange={(event) => setNote(event.target.value)} onBlur={commit} />
                </label>
                <div className="run-details-facts">
                    {facts && <div>{facts}</div>}
                    <div className="muted">{timing}</div>
                </div>
                <p className="run-details-store muted">{storeText(entry, store)}</p>
                {confirming ? (
                    <div className="modal-actions run-details-confirm" role="alert">
                        <span>Delete run {entry.runId} and its files?</span>
                        <span className="toolbar-spacer" />
                        <button type="button" className="button" onClick={() => setConfirming(false)} disabled={deleting}>
                            Keep it
                        </button>
                        <button type="button" className="button button-danger" onClick={remove} disabled={deleting} autoFocus>
                            Delete
                        </button>
                    </div>
                ) : (
                    <div className="modal-actions">
                        <button type="button" className="button" onClick={() => setConfirming(true)}>Delete run</button>
                        <span className="toolbar-spacer" />
                        <button type="button" className="button" onClick={() => onBaseline(isBaseline ? null : entry.runId)}
                                title={isBaseline ? 'Compare the runs against no baseline' : 'Compare the other runs against this one'}>
                            {isBaseline ? 'Clear baseline' : 'Make baseline'}
                        </button>
                        <button type="button" className="button button-primary" disabled={!entry.config}
                                title={entry.config ? 'Put the config this run ran into the Design form' : 'This run kept no config'}
                                onClick={() => {
                                    commit();
                                    onEditFrom(entry);
                                    onClose();
                                }}>
                            Edit from this run
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
