/* ========================================
   ANALYZE TAB
   The last good run's scalar results: sizing, the chamber, delivered performance against the
   1D estimates, station thermochemistry, the cooling summary and passes, the extension, the gas
   generator, films and the plume. The rows are built on the server (novaGui/analysis.py), the
   same rows the legacy Tkinter Analyze tab lists; the three performance columns are drawn as
   columns. A filter narrows
   the rows by name, and the table copies to the clipboard as tab-separated text or saves as CSV.
   Sean Bowman [11/17/2026]
   ======================================== */

import { useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../api';
import { CopyIcon, DownloadIcon, NozzleGlyph, SearchIcon } from '../components/Icons';
import type { ResultRow, ResultSection, ResultTable } from '../types';

interface AnalyzeTabProps {
    runId: number | null;
    visible: boolean;
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

/**
 * The table as rows of cells: a section's title, its column heads, then label, values, unit.
 */
function tableRows(sections: ResultSection[]): string[][] {
    const rows: string[][] = [];
    for (const section of sections) {
        rows.push([section.title]);
        if (section.columns) {
            rows.push(['', ...section.columns]);
        }
        for (const row of section.rows) {
            rows.push([row.label, ...row.cells, ...(row.unit ? [row.unit] : [])]);
        }
    }
    return rows;
}

/**
 * The rows whose label matches, each indented row kept under the row it belongs to (a coolant
 * pass's pressure drop under the pass), so a match never loses its context.
 */
function matchingRows(rows: ResultRow[], needle: string): ResultRow[] {
    const kept: ResultRow[] = [];
    let parent: ResultRow | null = null;
    let parentKept = false;
    for (const row of rows) {
        const matches = row.label.toLowerCase().includes(needle);
        if (!row.indent) {
            parent = row;
            parentKept = matches;
            if (matches) {
                kept.push(row);
            }
        } else if (matches) {
            if (parent && !parentKept) {
                kept.push(parent);
                parentKept = true;
            }
            kept.push(row);
        }
    }
    return kept;
}

function csvCell(text: string): string {
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

async function copyText(text: string): Promise<void> {
    if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text);
    }
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand('copy');
    area.remove();
    if (!copied) {
        throw new Error('the clipboard refused the text');
    }
}

export function AnalyzeTab({ runId, visible, onNotify }: AnalyzeTabProps) {
    const [table, setTable] = useState<ResultTable | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [query, setQuery] = useState('');
    const [closed, setClosed] = useState<Record<string, boolean>>({});
    const requested = useRef<number | null | undefined>(undefined);
    const scroller = useRef<HTMLDivElement>(null);

    // Fetch when the tab shows a run it has not asked for; the server caches the table per run
    useEffect(() => {
        if (!visible || requested.current === runId) {
            return;
        }
        // A reply counts only while its run is still the one asked for
        const forRun = runId;
        requested.current = forRun;
        setLoading(true);
        setError('');
        api.analysis()
            .then((loaded) => {
                if (requested.current === forRun) {
                    setTable(loaded);
                    setLoading(false);
                }
            })
            .catch((failure: Error) => {
                if (requested.current === forRun) {
                    // A failed table may be asked for again
                    requested.current = undefined;
                    setError(failure.message);
                    setLoading(false);
                }
            });
    }, [visible, runId]);

    const filtered = useMemo(() => {
        const sections = table?.sections ?? [];
        const needle = query.trim().toLowerCase();
        if (!needle) {
            return sections;
        }
        return sections
            .map((section) => (section.title.toLowerCase().includes(needle)
                ? section
                : { ...section, rows: matchingRows(section.rows, needle) }))
            .filter((section) => section.rows.length > 0);
    }, [table, query]);

    // A new filter reads from the top
    useEffect(() => {
        scroller.current?.scrollTo(0, 0);
    }, [query]);

    const copyTable = () => {
        copyText(tableRows(filtered).map((cells) => cells.join('\t')).join('\n'))
            .then(() => onNotify('info', 'Table copied', 'Tab-separated, ready to paste into a spreadsheet.'))
            .catch((failure: Error) => onNotify('error', 'Copy failed', failure.message));
    };

    const saveCsv = () => {
        const text = tableRows(filtered).map((cells) => cells.map(csvCell).join(',')).join('\r\n') + '\r\n';
        const link = document.createElement('a');
        link.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' }));
        link.download = `${table?.runName || 'novaRun'}Results.csv`;
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    };

    const hasRun = table !== null && table.runId !== null;

    let body;
    if (error) {
        body = <div className="empty">{error}</div>;
    } else if (table === null || (loading && !hasRun)) {
        body = <div className="empty"><span className="spinner" /> Loading results</div>;
    } else if (!hasRun) {
        body = <div className="empty">Generate a nozzle from the Design tab to fill this table.</div>;
    } else if (filtered.length === 0) {
        body = <div className="empty">No quantity matches “{query}”.</div>;
    } else {
        body = filtered.map((section) => {
            const open = query.trim() !== '' || !closed[section.title];
            const valueColumns = section.columns?.length ?? 1;
            return (
                <section key={section.title} className={`card section ${open ? 'is-open' : ''}`}>
                    <button type="button" className="section-header" aria-expanded={open}
                            onClick={() => setClosed((previous) => ({ ...previous, [section.title]: !previous[section.title] }))}>
                        <NozzleGlyph className="section-glyph" />
                        <span className="section-title">{section.title}</span>
                        <span className="section-count">{section.rows.length}</span>
                    </button>
                    <div className="section-body result-body" hidden={!open}>
                        <table className="result-table">
                            <colgroup>
                                <col className="result-label-col" />
                                {Array.from({ length: valueColumns }, (_, index) => <col key={index} className="result-value-col" />)}
                                <col className="result-unit-col" />
                            </colgroup>
                            {section.columns && (
                                <thead>
                                    <tr>
                                        <th />
                                        {section.columns.map((column) => <th key={column} className="result-value">{column}</th>)}
                                        <th />
                                    </tr>
                                </thead>
                            )}
                            <tbody>
                                {section.rows.map((row, index) => (
                                    <tr key={`${row.label}-${index}`} className={row.indent ? 'is-indented' : ''}>
                                        <td className="result-label">{row.label}</td>
                                        {row.cells.length === valueColumns
                                            ? row.cells.map((cell, cellIndex) => (
                                                <td key={cellIndex} className={`result-value ${cell === '--' ? 'is-blank' : ''}`}>{cell}</td>
                                            ))
                                            : <td className="result-value" colSpan={valueColumns}>{row.cells.join(' ')}</td>}
                                        <td className="result-unit">{row.unit}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </section>
            );
        });
    }

    return (
        <div className="analyze-tab">
            <div className="toolbar">
                <span className="eyebrow eyebrow-inline">Results</span>
                {hasRun && <span className="result-summary">{table.summary}</span>}
                <span className="toolbar-spacer" />
                <label className="search">
                    <SearchIcon />
                    <input className="input search-input" type="search" placeholder="Filter quantities" value={query}
                           onChange={(event) => setQuery(event.target.value)} disabled={!hasRun} />
                </label>
                <button type="button" className="button" onClick={copyTable} disabled={!hasRun}
                        title="Copy the table, as filtered, as tab-separated text">
                    <CopyIcon /> Copy
                </button>
                <button type="button" className="button" onClick={saveCsv} disabled={!hasRun}
                        title="Save the table, as filtered, as a CSV file">
                    <DownloadIcon /> Save CSV
                </button>
            </div>
            <div className="design-scroll" ref={scroller}>
                <div className="design-column result-column">{body}</div>
            </div>
        </div>
    );
}
