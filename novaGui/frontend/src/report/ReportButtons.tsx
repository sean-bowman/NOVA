/* ========================================
   REPORT BUTTONS
   Save report and the window beside it, for a run's report (in the Export dialog, against the
   baseline when there is one) and a sweep's (in the Sweep view). The server writes the report as
   one HTML file (novaGui.report) in a few seconds; Save report downloads it, and the window button
   opens it in a window of its own, to read before it is sent.
   Sean Bowman [11/20/2026]
   ======================================== */

import { useState } from 'react';

import { fetchPage, openWindow, saveBlob } from '../api';
import { PopOutIcon } from '../components/Icons';

interface ReportButtonsProps {
    path: string | null;           // the report's route on this server, null when there is nothing to report
    fileName: string;
    title: string;                 // what the report is of, for the window and the notices
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

export function ReportButtons({ path, fileName, title, onNotify }: ReportButtonsProps) {
    const [busy, setBusy] = useState(false);

    const save = () => {
        if (!path || busy) {
            return;
        }
        setBusy(true);
        fetchPage(path)
            .then((page) => {
                saveBlob(page, fileName);
                onNotify('info', 'Report saved', fileName);
            })
            .catch((failure: Error) => onNotify('error', 'Report not written', failure.message))
            .finally(() => setBusy(false));
    };

    return (
        <span className="report-buttons">
            <button type="button" className="button" onClick={save} disabled={!path || busy}
                    title={`${title} as one HTML file: the headline numbers, the inputs, the results, figures, `
                           + 'warnings and validation status, to read without the GUI'}>
                {busy ? <span className="spinner" /> : null} Save report
            </button>
            <button type="button" className="icon-button" disabled={!path} aria-label="Open the report in a window"
                    title="Open the report in a window of its own" onClick={() => path && openWindow(path, title)}>
                <PopOutIcon />
            </button>
        </span>
    );
}
