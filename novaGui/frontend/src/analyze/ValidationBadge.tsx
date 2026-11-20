/* ========================================
   VALIDATION BADGE
   How far a headline number or a table section can be trusted, from the validation records
   (novaGui/validationStatus.py, docs/validationStatus.json). The badge names the weakest status
   among the models behind the result, with an icon so it never reads by color alone: validated in
   green, calibrated, compared and cross-checked in amber, unvalidated in red, and a value that
   holds by construction in the muted ink.

   A click opens the models behind the result: each one's status, the reference it was put
   against, the result in numbers and what would close the gap. Show the record fetches the
   passages of the records the status stands on, with the quoted words marked, so the evidence
   reads in place.
   Sean Bowman [11/19/2026]
   ======================================== */

import { useEffect, useState } from 'react';

import { api } from '../api';
import { CloseIcon, ValidationIcon } from '../components/Icons';
import type { ValidationBadgeInfo, ValidationDetail, ValidationModel, ValidationStatusName } from '../types';

const tones: Record<ValidationStatusName, string> = {
    validated: 'is-good', calibrated: 'is-mid', compared: 'is-mid', crossCheck: 'is-mid', unvalidated: 'is-weak',
    construction: 'is-neutral',
};

function StatusChip({ status, label }: { status: ValidationStatusName; label: string }) {
    return (
        <span className={`validation-chip ${tones[status] ?? 'is-weak'}`}>
            <ValidationIcon status={status} /> {label}
        </span>
    );
}

/** A record's paragraph with the quoted words marked. */
function Passage({ text, quote }: { text: string; quote: string }) {
    const at = quote ? text.indexOf(quote) : -1;
    if (at < 0) {
        return <p className="validation-passage">{text}</p>;
    }
    return (
        <p className="validation-passage">
            {text.slice(0, at)}<mark>{quote}</mark>{text.slice(at + quote.length)}
        </p>
    );
}

function ModelEntry({ model }: { model: ValidationModel }) {
    const [detail, setDetail] = useState<ValidationDetail | null>(null);
    const [open, setOpen] = useState(false);
    const [error, setError] = useState('');

    const toggle = () => {
        setOpen((previous) => !previous);
        if (!detail && !error) {
            api.validationModel(model.id).then(setDetail).catch((failure: Error) => setError(failure.message));
        }
    };

    return (
        <li className="validation-model">
            <div className="validation-model-head">
                <span className="validation-model-name">{model.name}</span>
                <StatusChip status={model.status} label={model.label} />
            </div>
            <dl className="validation-facts">
                <dt>Reference</dt><dd>{model.reference}</dd>
                <dt>Result</dt><dd>{model.result}</dd>
                {model.gap && <><dt>To close it</dt><dd>{model.gap}</dd></>}
            </dl>
            <button type="button" className="button validation-record-button" aria-expanded={open} onClick={toggle}>
                {open ? 'Hide the record' : 'Show the record'}
            </button>
            {open && (
                <div className="validation-record">
                    {error && <p className="muted">{error}</p>}
                    {!detail && !error && <p className="muted"><span className="spinner" /> Reading the record</p>}
                    {detail?.passages.map((passage, at) => (
                        <div key={`${passage.path}-${at}`}>
                            <code className="validation-path">{passage.path}</code>
                            {passage.text
                                ? <Passage text={passage.text} quote={passage.quote} />
                                : <p className="muted">The record no longer carries the passage this status was summarized from.</p>}
                        </div>
                    ))}
                </div>
            )}
        </li>
    );
}

function ValidationDialog({ subject, info, onClose }: { subject: string; info: ValidationBadgeInfo; onClose: () => void }) {
    // Escape closes this dialog alone, ahead of the window's own Escape handling
    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                event.stopPropagation();
                onClose();
            }
        };
        document.addEventListener('keydown', onKey, true);
        return () => document.removeEventListener('keydown', onKey, true);
    }, [onClose]);

    const several = info.models.length > 1;
    return (
        <div className="modal-scrim" onClick={onClose}>
            <div className="card modal validation-dialog" role="dialog" aria-label={`Validation of ${subject}`}
                 onClick={(event) => event.stopPropagation()}>
                <div className="run-details-head">
                    <h2>{subject}</h2>
                    <StatusChip status={info.status} label={info.label} />
                    <span className="toolbar-spacer" />
                    <button type="button" className="icon-button" aria-label="Close" onClick={onClose}>
                        <CloseIcon />
                    </button>
                </div>
                <p className="muted">
                    {info.meaning}{several ? ` ${info.label} is the weakest status among the ${info.models.length} models it rests on.` : ''}
                </p>
                <ul className="validation-models">
                    {info.models.map((model) => <ModelEntry key={model.id} model={model} />)}
                </ul>
                <p className="muted validation-source">
                    The statuses are summarized in docs/validationStatus.json from the records shown, and the
                    test suite fails when a record stops carrying a quoted passage.
                </p>
            </div>
        </div>
    );
}

/** A result's validation status: a small chip that opens the models behind it. */
export function ValidationBadge({ info, subject }: { info: ValidationBadgeInfo | null | undefined; subject: string }) {
    const [open, setOpen] = useState(false);
    if (!info) {
        return null;
    }
    const names = info.models.map((model) => `${model.name}: ${model.label}`).join('\n');
    return (
        <>
            <button type="button" className={`validation-badge ${tones[info.status] ?? 'is-weak'}`}
                    title={`${info.label}. ${info.meaning}\n\n${names}\n\nClick for the references and records.`}
                    aria-label={`${subject}: ${info.label}, open the validation records`}
                    onClick={(event) => {
                        event.stopPropagation();
                        setOpen(true);
                    }}>
                <ValidationIcon status={info.status} />
                <span>{info.label}</span>
            </button>
            {open && <ValidationDialog subject={subject} info={info} onClose={() => setOpen(false)} />}
        </>
    );
}
