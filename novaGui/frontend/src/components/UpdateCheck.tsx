/* ========================================
   UPDATE CHECK
   The About dialog's Check for updates. The server (novaGui.updates) asks GitHub for the latest
   release and compares it with the running version; nothing is asked until the button is pressed.
   A later release links to its page, which the desktop window opens in the system browser, with
   how to install it for the build that runs.
   Sean Bowman [11/22/2026]
   ======================================== */

import { useState } from 'react';

import { api } from '../api';
import type { UpdateCheck as UpdateAnswer } from '../types';

function answerText(answer: UpdateAnswer): string {
    switch (answer.status) {
        case 'newer':
            return `NOVA ${answer.latest} is out${answer.published ? `, released ${answer.published}` : ''}. This is ${answer.running}.`;
        case 'current':
            return `This is the latest release, ${answer.running}.`;
        case 'ahead':
            return `This version, ${answer.running}, is later than the latest release, ${answer.latest}.`;
        case 'none':
            return 'No release of NOVA is published yet.';
        case 'unreachable':
            return `GitHub did not answer: ${answer.detail}.`;
        case 'refused':
            return `GitHub refused the check: ${answer.detail}.`;
        case 'unreadable':
            return `GitHub's answer carries no version to compare: ${answer.detail}.`;
    }
}

function installText(answer: UpdateAnswer): string {
    return answer.build === 'standalone'
        ? 'Unzip it in place of this folder. Runs, settings and exports live outside the folder and are kept.'
        : 'Pull the checkout to update it.';
}

export function UpdateCheck() {
    const [checking, setChecking] = useState(false);
    const [answer, setAnswer] = useState<UpdateAnswer | null>(null);
    const [failure, setFailure] = useState('');

    const check = () => {
        setChecking(true);
        setAnswer(null);
        setFailure('');
        api.updates()
            .then(setAnswer)
            .catch((error: Error) => setFailure(`The check failed: ${error.message}.`))
            .finally(() => setChecking(false));
    };

    const text = answer ? answerText(answer) : failure;
    return (
        <div className="update-check">
            <button type="button" className="button" onClick={check} disabled={checking}>
                {checking ? <><span className="spinner" /> Checking</> : 'Check for updates'}
            </button>
            {text && <p className={answer?.status === 'newer' ? 'update-answer' : 'update-answer muted'} role="status">{text}</p>}
            {answer?.status === 'newer' && (
                <div className="update-release">
                    <a className="button button-primary" href={answer.url} target="_blank" rel="noopener noreferrer">
                        Open the release page
                    </a>
                    <span className="muted">{installText(answer)}</span>
                </div>
            )}
        </div>
    );
}
