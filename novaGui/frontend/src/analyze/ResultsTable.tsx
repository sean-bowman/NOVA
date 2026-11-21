/* ========================================
   RESULTS TABLE
   A run's scalar results, the result pane's Table: sizing, the chamber, delivered performance
   against the 1D estimates, station thermochemistry, the cooling summary and passes, the
   extension, the gas generator, films and the plume. The rows are built on the server
   (novaGui/analysis.py), and the three performance columns are drawn as columns. A filter narrows the rows by name, and the table
   copies to the clipboard as tab-separated text or saves as CSV.

   The numbers a design is judged by first head the table: delivered Isp and thrust, length,
   exit diameter, the peak hot wall against its limit, and each pass's pressure drop. A row or a
   number that a figure shows opens that figure.

   Beside a baseline run, each value carries the baseline's value and the change from it, the
   shown run minus the baseline; a value that did not move reads blank. Rows only the baseline
   has follow at the end of their section.

   Each headline number and section carries its validation status (ValidationBadge): the weakest
   status among the models behind it, which opens the references and the records.
   Sean Bowman [11/17/2026]
   ======================================== */

import { useEffect, useMemo, useRef, useState } from 'react';

import { ChartIcon, CopyIcon, DownloadIcon, InfoIcon, NozzleGlyph, SearchIcon } from '../components/Icons';
import type { HeadlineNumber, ResultRow, ResultSection, ResultTable } from '../types';
import { ValidationBadge } from './ValidationBadge';

interface ResultsTableProps {
    table: ResultTable | null;
    loading: boolean;
    error: string;
    emptyText: string;
    available: Set<string>;         // the views the shown run produced
    onOpenView: (key: string) => void;
    onNotify: (kind: 'info' | 'error', title: string, body?: string) => void;
}

/**
 * The table as rows of cells: a section's title, its column heads, then label, values, unit;
 * beside a baseline each value is followed by the baseline's and the change.
 */
function tableRows(sections: ResultSection[], baselineRun: number | null): string[][] {
    const rows: string[][] = [];
    for (const section of sections) {
        rows.push([section.title]);
        const heads = section.columns ?? ['value'];
        if (section.columns || baselineRun !== null) {
            rows.push(['', ...(baselineRun === null ? heads
                : heads.flatMap((head) => [head, `${head}, run ${baselineRun}`, `${head}, change`]))]);
        }
        for (const row of section.rows) {
            const cells = baselineRun === null ? row.cells
                : row.cells.flatMap((cell, at) => [cell, row.baseline?.[at] ?? '', row.change?.[at] ?? '']);
            rows.push([row.label, ...cells, ...(row.unit ? [row.unit] : [])]);
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

function Headline({ numbers, baselineRun, available, onOpenView }: {
    numbers: HeadlineNumber[]; baselineRun: number | null; available: Set<string>; onOpenView: (key: string) => void;
}) {
    return (
        <div className="headline" role="list" aria-label="Headline numbers">
            {numbers.map((number) => {
                const opens = number.view !== null && available.has(number.view);
                const body = (
                    <>
                        <span className="headline-label">{number.label}</span>
                        <span className="headline-value">
                            {number.value}<span className="headline-unit">{number.unit}</span>
                        </span>
                        {number.tone === 'warn' && (
                            <span className="headline-flag"><InfoIcon /> above its limit</span>
                        )}
                        {number.detail && <span className="headline-detail">{number.detail}</span>}
                        {baselineRun !== null && (
                            <span className="headline-change">
                                {number.baseline == null ? `not in run ${baselineRun}`
                                    : (number.change ? `${number.change} vs run ${baselineRun}` : `same as run ${baselineRun}`)}
                            </span>
                        )}
                    </>
                );
                return (
                    <div key={number.key} role="listitem" className={`headline-item ${number.tone === 'warn' ? 'is-warn' : ''}`}>
                        {opens ? (
                            <button type="button" className="headline-number is-link"
                                    onClick={() => onOpenView(number.view!)} title="Open the figure that shows it">
                                {body}
                            </button>
                        ) : (
                            <div className="headline-number">{body}</div>
                        )}
                        <ValidationBadge info={number.validation} subject={number.label} />
                    </div>
                );
            })}
        </div>
    );
}

export function ResultsTable({ table, loading, error, emptyText, available, onOpenView, onNotify }: ResultsTableProps) {
    const [query, setQuery] = useState('');
    const [closed, setClosed] = useState<Record<string, boolean>>({});
    const scroller = useRef<HTMLDivElement>(null);
    const baselineRun = table?.baselineRun ?? null;

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
        copyText(tableRows(filtered, baselineRun).map((cells) => cells.join('\t')).join('\n'))
            .then(() => onNotify('info', 'Table copied', 'Tab-separated, ready to paste into a spreadsheet.'))
            .catch((failure: Error) => onNotify('error', 'Copy failed', failure.message));
    };

    const saveCsv = () => {
        const text = tableRows(filtered, baselineRun).map((cells) => cells.map(csvCell).join(',')).join('\r\n') + '\r\n';
        const link = document.createElement('a');
        link.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' }));
        const against = baselineRun !== null ? `VsRun${baselineRun}` : '';
        link.download = `${table?.runName || 'novaRun'}Run${table?.runId ?? ''}${against}Results.csv`;
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    };

    const hasRun = table !== null && table.runId !== null;

    const valueCell = (cell: string, key: number, baseline: string | undefined, change: string | undefined, span = 1) => (
        <td key={key} colSpan={span} className={`result-value ${cell === '--' ? 'is-blank' : ''}`}
            title={baseline !== undefined && baselineRun !== null ? `run ${baselineRun}: ${baseline}` : undefined}>
            {cell}
            {change !== undefined && change !== '' && <span className="result-change">{change}</span>}
        </td>
    );

    let body;
    if (error) {
        body = <div className="empty">{error}</div>;
    } else if (table === null || (loading && !hasRun)) {
        body = <div className="empty"><span className="spinner" /> Loading results</div>;
    } else if (!hasRun) {
        body = <div className="empty">{emptyText}</div>;
    } else if (filtered.length === 0) {
        body = <div className="empty">No quantity matches “{query}”.</div>;
    } else {
        body = filtered.map((section) => {
            const open = query.trim() !== '' || !closed[section.title];
            const columned = section.columns !== null;
            // Beside a baseline a one-value section reads value, baseline, change in three columns;
            // a columned section keeps its columns and writes each change under its value
            const split = baselineRun !== null && !columned;
            const valueColumns = section.columns?.length ?? (split ? 3 : 1);
            return (
                <section key={section.title} className={`card section ${open ? 'is-open' : ''}`}>
                    <div className="section-head-row">
                        <button type="button" className="section-header" aria-expanded={open}
                                onClick={() => setClosed((previous) => ({ ...previous, [section.title]: !previous[section.title] }))}>
                            <NozzleGlyph className="section-glyph" />
                            <span className="section-title">{section.title}</span>
                            {section.baselineOnly && <span className="badge">only in run {baselineRun}</span>}
                            <span className="section-count">{section.rows.length}</span>
                        </button>
                        <ValidationBadge info={section.validation} subject={section.title} />
                    </div>
                    <div className="section-body result-body" hidden={!open}>
                        <table className={`result-table ${baselineRun !== null ? 'is-compared' : ''}`}>
                            <colgroup>
                                <col className="result-label-col" />
                                {Array.from({ length: valueColumns }, (_, at) => <col key={at} className="result-value-col" />)}
                                <col className="result-unit-col" />
                            </colgroup>
                            {(columned || split) && (
                                <thead>
                                    <tr>
                                        <th />
                                        {split
                                            ? [`run ${table.runId}`, `run ${baselineRun}`, 'change'].map((head) => (
                                                <th key={head} className="result-value">{head}</th>
                                            ))
                                            : section.columns!.map((column) => <th key={column} className="result-value">{column}</th>)}
                                        <th />
                                    </tr>
                                </thead>
                            )}
                            <tbody>
                                {section.rows.map((row, at) => {
                                    const opens = row.view !== null && available.has(row.view);
                                    let cells;
                                    if (split) {
                                        const cell = row.cells.join(' ');
                                        const baseline = row.baseline ? row.baseline.join(' ') : '--';
                                        cells = [
                                            valueCell(cell, 0, undefined, undefined),
                                            <td key={1} className={`result-value is-baseline ${baseline === '--' ? 'is-blank' : ''}`}>{baseline}</td>,
                                            <td key={2} className="result-value result-change-cell">{row.change?.join(' ') ?? ''}</td>,
                                        ];
                                    } else if (row.cells.length === valueColumns) {
                                        cells = row.cells.map((cell, cellAt) => valueCell(cell, cellAt, row.baseline?.[cellAt], row.change?.[cellAt]));
                                    } else {
                                        cells = [valueCell(row.cells.join(' '), 0, row.baseline?.join(' '), row.change?.join(' '), valueColumns)];
                                    }
                                    return (
                                        <tr key={`${row.label}-${at}`}
                                            className={[row.indent ? 'is-indented' : '', opens ? 'is-link' : '',
                                                        row.baselineOnly ? 'is-baseline-only' : ''].filter(Boolean).join(' ')}
                                            onClick={opens ? () => onOpenView(row.view!) : undefined}
                                            title={opens ? 'Open the figure that shows it' : undefined}>
                                            <td className="result-label">
                                                {row.label}
                                                {opens && <ChartIcon className="result-link-icon" />}
                                            </td>
                                            {cells}
                                            <td className="result-unit">{row.unit}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </section>
            );
        });
    }

    return (
        <div className="results-table">
            <div className="figure-toolbar">
                <label className="search">
                    <SearchIcon />
                    <input className="input search-input" type="search" placeholder="Filter quantities" value={query}
                           onChange={(event) => setQuery(event.target.value)} disabled={!hasRun} />
                </label>
                <span className="toolbar-spacer" />
                <button type="button" className="button" onClick={copyTable} disabled={!hasRun}
                        title="Copy the table, as filtered, as tab-separated text">
                    <CopyIcon /> Copy
                </button>
                <button type="button" className="button" onClick={saveCsv} disabled={!hasRun}
                        title="Save the table, as filtered, as a CSV file">
                    <DownloadIcon /> Save CSV
                </button>
            </div>
            <div className="pane-scroll" ref={scroller}>
                <div className="pane-column">
                    {hasRun && !error && table.headline.length > 0 && !query.trim() && (
                        <Headline numbers={table.headline} baselineRun={baselineRun} available={available} onOpenView={onOpenView} />
                    )}
                    {body}
                </div>
            </div>
        </div>
    );
}
