
# -- NOVA GUI Reports -- #

'''

A run, a run against its baseline, or a trade sweep, as one HTML file to send to someone without
the GUI.

A run's report holds the run's headline numbers with the validation status of the model behind
each, the inputs that differ from the shipped nozzle (and from the baseline, beside one), the
whole result table, four figures (the contour, the near-wall state, the jacket temperatures and
the plume, where the run has them), the warnings the run raised, a validation section listing
every model behind the reported numbers, and the config the run ran. A sweep's report holds the
swept fields and the inputs the sweep starts from, the range of each headline number across the
points, a plot of every headline number against the swept field, the table of points, the
warnings the sweep's runs raised, the same validation section, and the base config.

The file stands alone: the figures are PNGs written into it, drawn by the GUI's static drawers
(novaGui.views.staticFigure) and, for a sweep, by `sweepFigurePng`; it loads nothing from the
network and names no folder on the machine that made it. On screen it uses the report palette;
printed, it switches to a light page and the light-mode drawings of the same figures.

The report adds no model of its own. Its validation section repeats docs/validationStatus.json
(novaGui.validationStatus): each model's standing against its references, which is not a check
of this run's numbers.

Author: Sean Bowman
Date:   11/20/2026

'''

# Standard library imports
import base64
import datetime
import html
import io
import json
import math
import re

# Local imports
from . import configSchema
from . import sweeps as sweepModel
from . import themeColors
from . import units
from . import validationStatus
from . import views

reportFigures = (('contour', 'Contour'), ('nearWall', 'Near-wall state'),
                 ('jacketTemperatures', 'Jacket temperatures'), ('plume', 'Plume'))
figureSize = (1000, 560)          # [px] a figure's size in CSS pixels, the width the page shows it at
figureRatio = 1.5                 # [-] PNG pixels per CSS pixel, for a sharp print
skippedKeys = set(configSchema.forcedFlags) | {'filename'}

statusClasses = {'validated': 'status-pass', 'calibrated': 'status-warn', 'compared': 'status-warn',
                 'crossCheck': 'status-warn', 'unvalidated': 'status-fail', 'construction': 'status-none'}
statusColors = {'validated': 'var(--green)', 'calibrated': 'var(--yellow)', 'compared': 'var(--yellow)',
                'crossCheck': 'var(--yellow)', 'unvalidated': 'var(--red)', 'construction': 'var(--text-dim)'}

#----------------------------------------------------------------------#
# -- Values in words -- #
#----------------------------------------------------------------------#

def _e(text) -> str:

    return html.escape('' if text is None else str(text))

def _trimmed(value: float) -> str:

    '''A number to five significant figures, an integer when it is one.'''

    rounded = float(f'{value:.5g}')
    if rounded == int(rounded) and abs(rounded) < 1e15:
        return str(int(rounded))

    return f'{rounded:.10g}'

def numberText(value: float, dimension: str | None, unit: str) -> str:

    '''

    A number in the first of its dimension's units that reads between 0.1 and 10000, so a chamber
    pressure reads in kPa or MPa rather than seven digits of Pa; the same rule as the GUI's list
    of changed fields (frontend/src/result/changes.ts).

    '''

    if dimension:
        readable = units.siUnit(dimension)
        for name in units.unitsFor(dimension):
            shown = abs(units.fromSI(value, dimension, name))
            if shown == 0 or 0.1 <= shown < 1e4:
                readable = name
                break
        return f'{_trimmed(units.fromSI(value, dimension, readable))} {readable}'

    return f'{_trimmed(value)} {unit}' if unit else _trimmed(value)

def valueText(spec: configSchema.Field, value) -> str:

    '''A config value as words: blank, on or off, a choice's label, a number with its unit, or the text.'''

    if value is None or value == '':
        return 'blank'
    if spec.kind == 'bool':
        return 'on' if value in (True, 'on', 'true', 'True') else 'off'
    if spec.choices:
        return spec.valueToLabel(value)
    if isinstance(value, bool):
        return 'on' if value else 'off'
    if isinstance(value, (int, float)):
        return numberText(float(value), spec.dimension, spec.unit)
    if isinstance(value, list):
        return ', '.join(_trimmed(entry) if isinstance(entry, (int, float)) else json.dumps(entry) for entry in value)
    if isinstance(value, dict):
        return json.dumps(value)

    return str(value)

def _same(a, b) -> bool:

    '''Whether two config values are the same setting, numbers to a relative 1e-9.'''

    if isinstance(a, bool) or isinstance(b, bool):
        return (a in (True, 'on', 'true', 'True')) == (b in (True, 'on', 'true', 'True'))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))

    return (a if a != '' else None) == (b if b != '' else None)

def inputRows(config: dict, against: list) -> list:

    '''

    The form's fields where a config differs from any of the configs it is set against, in form order.

    Parameters:
    -----------
    config : dict
        The config the report is about.
    against : list
        [dict] the configs it is compared with: the shipped nozzle, then the baseline's.

    Returns:
    --------
    list : [{'section', 'key', 'label', 'values': [str, ...]}], the config's value first

    '''

    rows = []
    for group in configSchema.groups:
        for item in group.fields:
            for spec in (item.members if isinstance(item, configSchema.Selector) else [item]):
                if spec.key in skippedKeys or spec.hidden:
                    continue
                value = config.get(spec.key)
                others = [other.get(spec.key) for other in against]
                if all(_same(value, other) for other in others):
                    continue
                rows.append({'section': group.title, 'key': spec.key, 'label': spec.label,
                             'values': [valueText(spec, value)] + [valueText(spec, other) for other in others]})

    return rows

#----------------------------------------------------------------------#
# -- Figures -- #
#----------------------------------------------------------------------#

def _png(data: bytes) -> str:

    return 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')

def runFigures(nozzle, available: set) -> list:

    '''

    The report's figures for a run, each drawn in both modes: [{'label', 'dark', 'light'}] with
    the PNGs as data URIs, or {'label', 'message'} where the drawer has nothing to draw.

    '''

    found = []
    for key, label in reportFigures:
        if key not in available:
            continue
        drawn = {mode: views.staticFigure(nozzle, key, mode, figureSize[0], figureSize[1], figureRatio)
                 for mode in ('dark', 'light')}
        if 'message' in drawn['dark']:
            found.append({'label': label, 'message': drawn['dark']['message']})
            continue
        found.append({'label': label, 'dark': _png(drawn['dark']['png']), 'light': _png(drawn['light']['png'])})

    return found

def sweepFigurePng(table: dict, mode: str) -> bytes | None:

    '''

    Every headline number of a sweep against its first field, one panel each, one line per value
    of a second field, in the GUI palette of `mode`. A point without the number leaves a gap.
    None when no point has a number.

    '''

    numbers = table['numbers']
    if not numbers:
        return None

    import matplotlib
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    first = table['fields'][0]
    second = table['fields'][1] if len(table['fields']) > 1 else None
    numeric = first['kind'] in ('float', 'floatText', 'int')
    columns = 2 if len(numbers) > 1 else 1
    rows = math.ceil(len(numbers) / columns)

    with views.renderLock:
        themeColors.bindPalette(mode)
        palette = themeColors.palettes[mode]
        with matplotlib.rc_context(themeColors.matplotlibRcParams()):
            figure = Figure(figsize = (figureSize[0] / 100.0, 2.7 * rows + 0.6), dpi = 100.0 * figureRatio)
            figure.patch.set_facecolor(palette['surface'])
            axes = figure.subplots(rows, columns, squeeze = False)
            positions = [sweepModel.shownValue(first, value) for value in first['values']] if numeric \
                else list(range(len(first['values'])))
            for at, number in enumerate(numbers):
                ax = axes[at // columns][at % columns]
                for series in range(len(second['values']) if second else 1):
                    points = sorted((point for point in table['points'] if not second or point['at'][1] == series),
                                    key = lambda point: point['at'][0])
                    x = [positions[point['at'][0]] for point in points]
                    y = [point['numbers'].get(number['key'], {}).get('value') for point in points]
                    y = [float('nan') if value is None else value for value in y]
                    color = palette[sweepModel.seriesColors[series % len(sweepModel.seriesColors)]]
                    ax.plot(x, y, color = color, linewidth = 2.0, marker = 'o', markersize = 6,
                            markeredgecolor = palette['surface'], markeredgewidth = 1.5,
                            label = second['texts'][series] if second else None)
                unit = f' [{number["unit"]}]' if number['unit'] else ''
                ax.set_title(f'{number["label"]}{unit}', fontsize = 10)
                if not numeric:
                    ax.set_xticks(positions, first['texts'])
                pad = 0.05 * (max(positions) - min(positions) or 1.0)
                ax.set_xlim(min(positions) - pad, max(positions) + pad)
                if at // columns == rows - 1 or at + columns >= len(numbers):
                    xUnit = f' [{first["unit"]}]' if numeric and first['unit'] else ''
                    ax.set_xlabel(f'{first["label"]}{xUnit}')
                themeColors.styleAxes(ax)
            for at in range(len(numbers), rows * columns):
                axes[at // columns][at % columns].set_visible(False)
            if second is not None:
                axes[0][0].legend(title = second['label'], fontsize = 8, title_fontsize = 8)
            figure.tight_layout()
            FigureCanvasAgg(figure)
            buffer = io.BytesIO()
            figure.savefig(buffer, format = 'png', facecolor = palette['surface'])

    return buffer.getvalue()

#----------------------------------------------------------------------#
# -- Page parts -- #
#----------------------------------------------------------------------#

def _statusBadge(info: dict | None) -> str:

    if not info:
        return ''
    return (f'<span class="status-badge {statusClasses.get(info["status"], "status-fail")}" '
            f'title="{_e(info.get("meaning", ""))}">{_e(info["label"])}</span>')

def _headlineCards(numbers: list, baselineRun: int | None) -> str:

    cards = []
    for number in numbers:
        info = number.get('validation')
        color = statusColors.get(info['status'], 'var(--border)') if info else 'var(--border)'
        detail = [_e(number.get('detail', ''))] if number.get('detail') else []
        if baselineRun is not None:
            if number.get('baseline') is None:
                detail.append(f'not in run {baselineRun}')
            elif number.get('change'):
                detail.append(f'{_e(number["change"])} against run {baselineRun}')
            else:
                detail.append(f'same as run {baselineRun}')
        warn = (' is-warn' if number.get('tone') == 'warn' else '') + (' is-range' if number.get('range') else '')
        cards.append(
            f'<div class="summary-card" style="border-top-color: {color}">'
            f'<div class="summary-label">{_e(number["label"])}</div>'
            f'<div class="summary-value{warn}">{_e(number["value"])} <span class="summary-unit">{_e(number["unit"])}</span></div>'
            f'<div class="summary-detail">{"<br>".join(detail)}</div>'
            f'<div class="summary-status">{_statusBadge(info)}</div></div>')

    return f'<div class="summary-grid">{"".join(cards)}</div>'

def _inputsTable(rows: list, heads: list, empty: str) -> str:

    if not rows:
        return f'<p class="lead">{_e(empty)}</p>'
    head = ''.join(f'<th>{_e(name)}</th>' for name in ['Section', 'Field'] + heads)
    body = []
    for row in rows:
        values = ''.join(f'<td class="{"value" if at == 0 else "value is-other"}">{_e(value)}</td>'
                         for at, value in enumerate(row['values']))
        body.append(f'<tr><td class="muted">{_e(row["section"])}</td><td>{_e(row["label"])}</td>{values}</tr>')

    return (f'<div class="data-table-wrap"><table class="data-table"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')

def _resultSections(table: dict) -> str:

    '''The result table, a section at a time, as the GUI's table lays it out.'''

    baselineRun = table.get('baselineRun')
    parts = []
    for section in table.get('sections', []):
        columned = bool(section.get('columns'))
        split = baselineRun is not None and not columned
        if columned:
            heads = list(section['columns'])
        elif split:
            heads = [f'Run {table["runId"]}', f'Run {baselineRun}', 'Change']
        else:
            heads = ['Value']
        head = '<th>Quantity</th>' + ''.join(f'<th class="num">{_e(name)}</th>' for name in heads) + '<th>Unit</th>'
        body = []
        for row in section['rows']:
            indent = ' class="is-indented"' if row.get('indent') else ''
            if split:
                baseline = ' '.join(row['baseline']) if row.get('baseline') else '--'
                change = ' '.join(text for text in (row.get('change') or []) if text)
                cells = [' '.join(row['cells']), baseline, change]
                tds = ''.join(f'<td class="num{" is-other" if at else ""}">{_e(cell)}</td>' for at, cell in enumerate(cells))
            else:
                tds = ''
                for at, cell in enumerate(row['cells']):
                    change = (row.get('change') or [None] * len(row['cells']))[at] if baselineRun is not None else None
                    under = f'<span class="change">{_e(change)}</span>' if change else ''
                    tds += f'<td class="num">{_e(cell)}{under}</td>'
                tds += '<td></td>' * max(0, len(heads) - len(row['cells']))
            body.append(f'<tr{indent}><td>{_e(row["label"])}</td>{tds}<td class="muted">{_e(row.get("unit", ""))}</td></tr>')
        only = f' <span class="status-badge status-none">only in run {baselineRun}</span>' if section.get('baselineOnly') else ''
        parts.append(
            f'<div class="result-block"><div class="result-head"><h3>{_e(section["title"])}</h3>'
            f'{_statusBadge(section.get("validation"))}{only}</div>'
            f'<div class="data-table-wrap"><table class="data-table result-table"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div></div>')

    return ''.join(parts)

def _figureCards(figures: list, empty: str) -> str:

    if not figures:
        return f'<p class="lead">{_e(empty)}</p>'
    cards = []
    for figure in figures:
        if 'message' in figure:
            cards.append(f'<div class="figure-card"><h3>{_e(figure["label"])}</h3>'
                         f'<p class="muted">{_e(figure["message"])}</p></div>')
            continue
        cards.append(f'<figure class="figure-card"><h3>{_e(figure["label"])}</h3>'
                     f'<img class="figure-dark" src="{figure["dark"]}" alt="{_e(figure["label"])}">'
                     f'<img class="figure-light" src="{figure["light"]}" alt="{_e(figure["label"])}"></figure>')

    return f'<div class="figure-grid">{"".join(cards)}</div>'

def _warningsList(warnings: list, empty: str) -> str:

    if not warnings:
        return f'<p class="lead">{_e(empty)}</p>'
    items = []
    for warning in warnings:
        times = f', {warning["count"]} times' if warning.get('count', 1) > 1 else ''
        runs = f'<span class="muted"> {_e(warning["runs"])}</span>' if warning.get('runs') else ''
        items.append(f'<li><span class="warning-message">{_e(warning["message"])}</span>'
                     f'<span class="muted"> ({_e(warning.get("category", ""))}, <code>{_e(warning.get("where", ""))}</code>{times})</span>{runs}</li>')

    return f'<ul class="warning-list">{"".join(items)}</ul>'

def _validationSection(modelIds: list) -> str:

    summary = validationStatus.load()
    info = validationStatus.badge(modelIds, summary) if summary else None
    if info is None:
        return '<p class="lead">The validation records are not in this installation.</p>'
    rows = []
    for model in info['models']:
        gap = _e(model['gap']) if model['gap'] else '<span class="muted">none named</span>'
        rows.append(f'<tr><td>{_e(model["name"])}</td><td>{_statusBadge(model)}</td><td>{_e(model["reference"])}</td>'
                    f'<td>{_e(model["result"])}</td><td>{gap}</td><td><code>{_e(model["record"])}</code></td></tr>')
    meanings = ''.join(f'<li>{_statusBadge({"status": key, "label": entry["label"]})} {_e(entry["meaning"])}</li>'
                       for key, entry in summary.get('statuses', {}).items())
    weakest = (f'The weakest status among them is <strong>{_e(info["label"])}</strong>, so the reported numbers as a set '
               f'are no better than that.')

    return (f'<p class="lead">Each number in this report comes from the models below. Their statuses are NOVA\'s '
            f'validation records (<code>docs/validationStatus.md</code>): each model\'s standing against its '
            f'references, not a check of these particular numbers. {weakest}</p>'
            f'<div class="data-table-wrap"><table class="data-table validation-table"><thead><tr><th>Model</th>'
            f'<th>Status</th><th>Reference</th><th>Result</th><th>What would close the gap</th><th>Record</th></tr>'
            f'</thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<div class="key-box statuses"><h4>Statuses</h4><ul>{meanings}</ul></div>')

def _configBlock(config: dict, caption: str) -> str:

    shown = {key: value for key, value in sorted(config.items()) if key not in configSchema.forcedFlags}
    return (f'<details class="config"><summary>{_e(caption)}</summary>'
            f'<pre>{_e(json.dumps(shown, indent = 2, sort_keys = True))}</pre></details>')

def novaVersion() -> str:

    try:
        from importlib.metadata import version
        return version('nova-nozzle')
    except Exception:                                      # noqa: BLE001 -- not installed as a package
        return ''

def _when(epochSec: float) -> str:

    return datetime.datetime.fromtimestamp(epochSec).strftime('%d %b %Y %H:%M')

def _clock(seconds: float) -> str:

    seconds = int(round(seconds))
    return f'{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}' if seconds >= 3600 \
        else f'{seconds // 60}:{seconds % 60:02d}'

def _page(title: str, eyebrow: str, heroTitle: str, lead: str, meta: list, sections: list, note: str = '') -> str:

    '''

    The whole page. `sections` is [(id, nav label, title, subtitle, body html)].

    '''

    nav = ''.join(f'<li><a href="#{key}">{_e(label)}</a></li>' for key, label, *_ in sections)

    def subtitleOf(subtitle: str) -> str:
        return f'<p class="section-subtitle">{_e(subtitle)}</p>' if subtitle else ''

    metaHtml = ''.join(f'<span>{_e(item)}</span>' for item in meta if item)
    noteHtml = (f'<div class="callout-box"><div class="callout-title">Note</div>'
                f'<div class="callout-text">{_e(note)}</div></div>') if note else ''
    body = ''.join(
        f'<section id="{key}"><div class="container"><div class="section-header">'
        f'<h2 class="section-title">{_e(sectionTitle)}</h2>'
        f'{subtitleOf(subtitle)}</div>{content}</div></section>'
        for key, _, sectionTitle, subtitle, content in sections)
    stamp = _e(f'Written by NOVA{" " + novaVersion() if novaVersion() else ""} on {_when(datetime.datetime.now().timestamp())}.')

    return (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f'<title>{_e(title)}</title>\n<style>{reportCss}</style>\n</head>\n<body>\n'
            f'<nav><ul>{nav}</ul></nav>\n'
            f'<header class="hero"><div class="container"><div class="hero-eyebrow">{_e(eyebrow)}</div>'
            f'<h1 class="hero-title">{_e(heroTitle)}</h1><p class="hero-desc">{_e(lead)}</p>'
            f'<div class="hero-meta">{metaHtml}</div>{noteHtml}</div></header>\n'
            f'{body}\n<footer><div class="container">{stamp}</div></footer>\n</body>\n</html>\n')

#----------------------------------------------------------------------#
# -- Reports -- #
#----------------------------------------------------------------------#

def _modelIds(table: dict, nozzle) -> list:

    '''Every model behind a result table's headline numbers and sections, resolved for the run.'''

    ids = []
    for number in table.get('headline', []):
        ids += validationStatus.headlineModelIds.get(number['key'], [])
    for section in table.get('sections', []):
        ids += validationStatus.sectionModelIds.get(section['title'], [])

    return validationStatus.modelsFor(ids, nozzle)

def runReport(record, nozzle, table: dict, available: set, baseline = None) -> str:

    '''

    A run's report.

    Parameters:
    -----------
    record : novaGui.session.RunRecord
        The run.
    nozzle : Nozzle
        Its Nozzle, for the figures and the models it used.
    table : dict
        Its result table with validation badges (novaGui.analysis.resultTable,
        novaGui.validationStatus.annotate), set beside the baseline's when there is one
        (novaGui.analysis.compareTables).
    available : set
        The views the run produced (novaGui.views.availableViews).
    baseline : RunRecord, optional
        The run it is compared against.

    Returns:
    --------
    str : the HTML page

    '''

    name = record.title or record.runName or f'Run {record.runId}'
    shipped = configSchema.defaultConfig()
    config = record.config or {}
    against = [shipped] + ([baseline.config or {}] if baseline is not None else [])
    heads = [f'Run {record.runId}', 'Shipped nozzle'] + ([f'Run {baseline.runId}'] if baseline is not None else [])
    summaryLine = ', '.join(part.strip() for part in re.split(r'\s{2,}', record.headline) if part.strip())
    lead = summaryLine + (f'; against run {baseline.runId} ({baseline.title or baseline.runName}) as the baseline'
                          if baseline is not None else '')
    meta = [f'Run {record.runId}', f'config {record.runName}' if record.runName else '',
            f'finished {_when(record.finishedAt)}', f'ran {_clock(record.elapsedSec)}']
    baselineRun = baseline.runId if baseline is not None else None

    inputsNote = ('Every field of the form where this run differs from the shipped nozzle'
                  + (f' or from run {baseline.runId}' if baseline is not None else '') + '.')
    sections = [
        ('summary', 'Summary', 'Headline numbers',
         'The numbers a design is judged by first, each with the validation status of the models behind it'
         + (f', and the change from run {baselineRun}' if baselineRun is not None else '') + '.',
         _headlineCards(table.get('headline', []), baselineRun)),
        ('inputs', 'Inputs', 'Inputs', inputsNote,
         _inputsTable(inputRows(config, against), heads, 'This run is the shipped nozzle: no field differs.')),
        ('results', 'Results', 'Results',
         'The whole result table' + (f', beside run {baselineRun}: the change is this run minus the baseline'
                                     if baselineRun is not None else '') + '.',
         _resultSections(table)),
        ('figures', 'Figures', 'Figures', 'Drawn from the run by the same drawers as NOVA\'s saved figures.',
         _figureCards(runFigures(nozzle, available), 'The run produced none of the report\'s figures.')),
        ('warnings', 'Warnings', 'Warnings', 'Each warning the run raised, once, with the number of times it came.',
         _warningsList(record.warnings, 'The run raised no warnings.')),
        ('validation', 'Validation', 'Validation', '', _validationSection(_modelIds(table, nozzle))),
        ('config', 'Config', 'Config', 'The config the run ran, which reruns it in NOVA or in the GUI.',
         _configBlock(config, f'{record.runName or "run"}RunConfig.json')),
    ]
    title = f'{name}, run {record.runId}' + (f' against run {baseline.runId}' if baseline is not None else '')

    return _page(title, 'NOVA run report', name, lead, meta, sections, note = record.note)

def sweepReport(table: dict, records: dict, sampleTable: dict | None, sampleNozzle) -> str:

    '''

    A trade sweep's report.

    Parameters:
    -----------
    table : dict
        The sweep as novaGui.sweeps.table reads it.
    records : dict
        {runId: RunRecord}, the kept runs.
    sampleTable : dict or None
        The result table of one of the sweep's runs, with validation badges, for the status of each
        headline number.
    sampleNozzle : Nozzle or None
        That run's Nozzle, for the models it used.

    Returns:
    --------
    str : the HTML page

    '''

    fields = table['fields']
    points = table['points']
    counts = table['counts']
    shipped = configSchema.defaultConfig()
    swept = {field['key'] for field in fields}
    specs = {spec.key: spec for spec in configSchema.allFields()}
    baseRows = [row for row in inputRows(table['config'], [shipped]) if row['key'] not in swept]
    sweptRows = [{'section': 'Swept', 'key': field['key'], 'label': field['label'],
                  'values': [', '.join(field['texts']), valueText(specs[field['key']], shipped.get(field['key']))]}
                 for field in fields]
    summary = validationStatus.load()
    badges = {number['key']: validationStatus.badge(validationStatus.modelsFor(
        validationStatus.headlineModelIds.get(number['key'], []), sampleNozzle), summary) if summary else None
        for number in table['numbers']}

    # -- The range of each headline number across the points that ran -- #
    cards = []
    for number in table['numbers']:
        values = [(point['numbers'][number['key']]['value'], point['numbers'][number['key']]['text'])
                  for point in points if number['key'] in point['numbers'] and point['numbers'][number['key']]['value'] is not None]
        if values:
            low, high = min(values), max(values)
            span = low[1] if low[0] == high[0] else f'{low[1]} to {high[1]}'
        else:
            span = '--'
        cards.append({'key': number['key'], 'label': number['label'], 'value': span, 'unit': number['unit'],
                      'detail': f'across {len(values)} of {len(points)} points', 'tone': '', 'range': True,
                      'validation': badges.get(number['key'])})

    # -- The plot, in both modes -- #
    plots = {mode: sweepFigurePng(table, mode) for mode in ('dark', 'light')}
    figures = [{'label': f'Headline numbers against {fields[0]["label"].lower()}', 'dark': _png(plots['dark']),
                'light': _png(plots['light'])}] if plots['dark'] else []

    # -- The points -- #
    heads = (['#'] + [field['label'] for field in fields] + ['Run', 'State']
             + [f'{number["label"]} [{number["unit"]}]' if number['unit'] else number['label'] for number in table['numbers']])
    stateWords = {'queued': 'queued', 'running': 'running', 'done': 'done', 'failed': 'failed', 'cancelled': 'not run'}
    body = []
    for point in points:
        record = records.get(point['runId']) if point['kept'] else None
        run = f'{point["runId"]} · {_clock(record.elapsedSec)}' if record is not None else '--'
        cells = [str(point['index'] + 1)] + point['texts'] + [run, stateWords.get(point['state'], point['state'])]
        numbers = [point['numbers'].get(number['key'], {}).get('text', '--') for number in table['numbers']]
        tds = ''.join(f'<td>{_e(cell)}</td>' for cell in cells) + ''.join(f'<td class="num">{_e(cell)}</td>' for cell in numbers)
        body.append(f'<tr class="is-{point["state"]}">{tds}</tr>')
        if point['error']:
            body.append(f'<tr class="error-row"><td></td><td colspan="{len(heads) - 1}">{_e(point["error"])}</td></tr>')
    pointsTable = (f'<div class="data-table-wrap"><table class="data-table points-table"><thead><tr>'
                   + ''.join(f'<th>{_e(head)}</th>' for head in heads)
                   + f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')

    # -- The warnings of every run, each once, with the points that raised it -- #
    found = {}
    for point in points:
        record = records.get(point['runId']) if point['kept'] else None
        for warning in (record.warnings if record is not None else []):
            entry = found.setdefault((warning['category'], warning['message']), {**warning, 'count': 0, 'points': []})
            entry['count'] += warning.get('count', 1)
            entry['points'].append(str(point['index'] + 1))
    warnings = [{**entry, 'runs': f'points {", ".join(entry["points"])}' if len(entry['points']) > 1
                 else f'point {entry["points"][0]}'} for entry in found.values()]

    modelIds = []
    for number in table['numbers']:
        modelIds += validationStatus.headlineModelIds.get(number['key'], [])
    modelIds = validationStatus.modelsFor(modelIds, sampleNozzle)

    elapsed = sum(records[point['runId']].elapsedSec for point in points if point['kept'] and point['runId'] in records)
    lead = (' against '.join(f'{field["label"]} over {", ".join(field["texts"])}' for field in fields)
            + f': {len(points)} runs from one config, the first field varying fastest.')
    parts = [f'{counts["done"]} of {len(points)} done']
    if counts['failed']:
        parts.append(f'{counts["failed"]} failed')
    if counts['cancelled']:
        parts.append(f'{counts["cancelled"]} not run')
    if counts['queued'] + counts['running']:
        parts.append(f'{counts["queued"] + counts["running"]} still to run')
    meta = [f'Sweep {table["sweepId"]}', ', '.join(parts), f'started {_when(table["createdAt"])}',
            f'runs took {_clock(elapsed)} in all' if elapsed else '']

    sections = [
        ('summary', 'Summary', 'Headline numbers', 'The range of each headline number across the points that ran, '
         'with the validation status of the models behind it.', _headlineCards(cards, None)),
        ('inputs', 'Inputs', 'Inputs', 'The swept fields, then every other field where the sweep\'s config differs '
         'from the shipped nozzle; every point runs that config with its swept values set.',
         _inputsTable(sweptRows + baseRows, ['Sweep', 'Shipped nozzle'], '')),
        ('plots', 'Plots', 'Plots', 'A point that failed or did not run leaves a gap.',
         _figureCards(figures, 'No point has a result yet.')),
        ('points', 'Points', 'Points', 'Each point in run order, with its run\'s headline numbers; a failed point '
         'carries its reason.', pointsTable),
        ('warnings', 'Warnings', 'Warnings', 'Each warning the sweep\'s runs raised, once, with the points that raised it.',
         _warningsList(warnings, 'The sweep\'s runs raised no warnings.')),
        ('validation', 'Validation', 'Validation', '', _validationSection(modelIds)),
        ('config', 'Config', 'Config', 'The config every point starts from; a point sets its swept values over it.',
         _configBlock({key: value for key, value in table['config'].items() if key not in swept} | {
             field['key']: field['values'] for field in fields}, 'sweepConfig.json')),
    ]

    return _page(f'{table["name"]}, sweep {table["sweepId"]}', 'NOVA trade sweep report', table['name'], lead, meta,
                 sections)

#----------------------------------------------------------------------#
# -- Style -- #
#----------------------------------------------------------------------#

reportCss = '''
:root {
    --bg: #1a1e2a; --surface: #22273a; --surface-2: #292f42; --border: #3a4055;
    --text: #d8e0ec; --text-muted: #8a95a8; --text-dim: #5c6575;
    --green: #86C06C; --accent: #E0975A; --red: #e08080; --yellow: #d4b86a; --blue: #7baee8;
    --orange: #d48c5a; --purple: #aa84d8; --cyan: #6ad4c8;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text);
       line-height: 1.6; }
.container { max-width: 1400px; margin: 0 auto; padding: 0 2rem; }
section { padding: 3rem 0; border-bottom: 1px solid var(--border); }
.section-header { margin-bottom: 1.5rem; }
.section-title { font-size: 1.4rem; font-weight: 600; margin-bottom: 0.4rem; }
.section-subtitle, .lead { color: var(--text-muted); font-size: 0.9rem; max-width: 900px; }
.lead { margin-bottom: 1rem; }
nav { position: sticky; top: 0; background: rgba(26, 30, 42, 0.96); backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border); z-index: 100; padding: 0 2rem; }
nav ul { display: flex; list-style: none; overflow-x: auto; scrollbar-width: none; }
nav ul::-webkit-scrollbar { display: none; }
nav a { display: block; padding: 0.9rem 1.1rem; color: var(--text-muted); text-decoration: none; font-size: 0.82rem;
        white-space: nowrap; border-bottom: 2px solid transparent; transition: all 0.15s; }
nav a:hover { color: var(--accent); border-bottom-color: var(--accent); }
.hero { padding: 4rem 0 3rem; border-bottom: 1px solid var(--border); }
.hero-eyebrow { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.12em; color: var(--text-dim);
                margin-bottom: 1rem; }
.hero-title { font-size: 2.6rem; font-weight: 700; line-height: 1.15; margin-bottom: 1rem; overflow-wrap: anywhere; }
.hero-desc { font-size: 1.05rem; color: var(--text-muted); max-width: 900px; margin-bottom: 1.5rem; line-height: 1.65; }
.hero-meta { display: flex; gap: 0.4rem 2rem; font-size: 0.82rem; color: var(--text-dim); flex-wrap: wrap; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 1rem; }
.summary-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.2rem 1.4rem;
                border-top: 3px solid var(--border); }
.summary-label { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-dim);
                 margin-bottom: 0.4rem; }
.summary-value { font-size: 1.6rem; font-weight: 700; margin-bottom: 0.2rem; font-variant-numeric: tabular-nums; }
.summary-value.is-warn { color: var(--yellow); }
.summary-value.is-range { font-size: 1.15rem; padding: 0.35rem 0 0.15rem; }
.summary-unit { font-size: 0.9rem; font-weight: 500; color: var(--text-muted); }
.summary-detail { font-size: 0.8rem; color: var(--text-muted); line-height: 1.5; min-height: 1.2em; }
.summary-status { margin-top: 0.6rem; }
.data-table-wrap { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: 0.83rem; }
.data-table th { padding: 0.6rem 0.9rem; text-align: left; background: var(--surface-2); border-bottom: 2px solid var(--border);
                 font-weight: 500; color: var(--text-muted); font-size: 0.78rem; white-space: nowrap; }
.data-table td { padding: 0.5rem 0.9rem; border-bottom: 1px solid rgba(58, 64, 85, 0.45); vertical-align: top; }
.data-table tr:hover td { background: rgba(34, 39, 58, 0.8); }
.data-table th.num, .data-table td.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums;
                                         font-family: Consolas, 'Fira Code', monospace; }
.data-table td.value { font-weight: 600; }
.data-table td.is-other { color: var(--text-muted); font-weight: 400; }
.data-table .change { display: block; color: var(--text-muted); font-size: 0.72rem; }
.data-table tr.is-indented td:first-child { padding-left: 2rem; color: var(--text-muted); }
.result-block { margin-bottom: 1.8rem; }
.result-head { display: flex; align-items: center; gap: 0.7rem; margin-bottom: 0.5rem; }
.result-head h3 { font-size: 1rem; font-weight: 600; }
.result-table { max-width: 1100px; }
.points-table td { white-space: nowrap; }
.points-table tr.is-failed td { color: var(--red); }
.points-table tr.is-cancelled td { color: var(--text-dim); }
.points-table tr.error-row td { color: var(--text-muted); font-size: 0.78rem; border-bottom-style: dashed;
                                white-space: normal; }
.validation-table td { min-width: 120px; }
.validation-table td:nth-child(3), .validation-table td:nth-child(4), .validation-table td:nth-child(5) { min-width: 220px; }
.status-badge { display: inline-block; padding: 1px 7px; border-radius: 3px; font-size: 0.65rem; font-weight: 600;
                text-transform: uppercase; letter-spacing: 0.05em; white-space: nowrap; }
.status-pass { background: rgba(134, 192, 108, 0.12); color: var(--green); border: 1px solid rgba(134, 192, 108, 0.3); }
.status-fail { background: rgba(224, 128, 128, 0.12); color: var(--red); border: 1px solid rgba(224, 128, 128, 0.3); }
.status-warn { background: rgba(212, 184, 106, 0.12); color: var(--yellow); border: 1px solid rgba(212, 184, 106, 0.3); }
.status-none { background: rgba(92, 101, 117, 0.1); color: var(--text-dim); border: 1px solid rgba(92, 101, 117, 0.2); }
.callout-box { background: rgba(224, 151, 90, 0.06); border: 1px solid rgba(224, 151, 90, 0.2); border-radius: 8px;
               padding: 1rem 1.3rem; margin-top: 1.5rem; max-width: 900px; }
.callout-title { font-size: 0.78rem; font-weight: 600; color: var(--accent); margin-bottom: 0.3rem; }
.callout-text { font-size: 0.85rem; color: var(--text-muted); white-space: pre-wrap; }
.key-box { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.2rem 1.4rem;
           margin-top: 1.5rem; }
.key-box h4 { font-size: 0.85rem; font-weight: 600; margin-bottom: 0.6rem; }
.key-box ul { list-style: none; display: grid; gap: 0.4rem; }
.key-box li { font-size: 0.82rem; color: var(--text-muted); }
.figure-grid { display: grid; gap: 1.2rem; max-width: calc(1000px + 2rem + 2px); }
.figure-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }
.figure-card h3 { font-size: 0.9rem; font-weight: 600; margin-bottom: 0.6rem; }
.figure-card img { display: block; width: 100%; height: auto; border-radius: 4px; }
.figure-light { display: none !important; }
.warning-list { list-style: none; display: grid; gap: 0.5rem; font-size: 0.85rem; }
.warning-list li { padding: 0.6rem 0.9rem; background: rgba(212, 184, 106, 0.06); border: 1px solid rgba(212, 184, 106, 0.2);
                   border-radius: 6px; }
code { font-family: Consolas, 'Fira Code', monospace; font-size: 0.78rem; color: var(--cyan); background: var(--surface-2);
       padding: 1px 5px; border-radius: 3px; }
.muted { color: var(--text-muted); }
details.config { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; }
details.config summary { padding: 0.8rem 1.2rem; cursor: pointer; color: var(--accent); font-size: 0.85rem; }
details.config pre { padding: 0 1.2rem 1.2rem; font-size: 0.75rem; color: var(--text-muted); overflow-x: auto;
                     font-family: Consolas, 'Fira Code', monospace; }
footer { padding: 2rem 0 3rem; font-size: 0.78rem; color: var(--text-dim); }
@media (max-width: 640px) {
    .container { padding: 0 16px; }
    nav { padding: 0 8px; }
    .hero-title { font-size: 1.9rem; }
}
@media print {
    :root { --bg: #ffffff; --surface: #ffffff; --surface-2: #eef0f3; --border: #c9ced6; --text: #1a1e2a;
            --text-muted: #475063; --text-dim: #6b7486; --green: #3f7a2b; --accent: #a35d22; --red: #a33b3b;
            --yellow: #7f6516; --blue: #2f5f99; --cyan: #1f6f68; }
    * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    nav { display: none; }
    .hero { padding: 0 0 1.2rem; }
    section { padding: 1.4rem 0; }
    .figure-dark { display: none !important; }
    .figure-light { display: block !important; }
    .summary-card, .figure-card, .result-block, tr { break-inside: avoid; }
    .data-table tr:hover td { background: none; }
    details.config { display: none; }
}
'''
