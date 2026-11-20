
# -- NOVA Validation Status -- #

'''

How far each number in a run's result table can be trusted, read from the validation records.

`docs/validationStatus.json` summarizes the validation status of every model behind NOVA's
reported results: the status, the reference it was put against, the result in numbers, what would
close the gap, and the records it comes from, each with a passage quoted from the record. This
module reads that summary for the GUI and writes the summary table `docs/validationStatus.md` from
it. Nothing here decides a status: the summary does, and tests/testValidationStatus.py fails when a
record no longer carries a quote the summary stands on, so the two cannot drift apart unseen.

The statuses follow the validation hierarchy (strongest first): validated against a reference
inside its acceptance criterion, calibrated to a reference, compared with measured data outside
its tolerance, cross-checked against another unvalidated tool, and unvalidated. 'construction'
marks geometry or accounting on the inputs, which is not a physical model.

`annotate` puts a `validation` badge on each headline number and section of a result table
(novaGui.analysis.resultTable): the models behind it, as this run used them (the gas-side model
the run selected, the multi-pass circuit and the chamber film only where the run has them), and
the weakest of their statuses, so a number reads as no stronger than the least trusted model it
rests on. `passages` returns the paragraphs of the records that carry a model's quotes, for the
browser to show the evidence in place.

    python -m novaGui.validationStatus --write      write docs/validationStatus.md
    python -m novaGui.validationStatus --check      exit 1 if it is out of date

Author: Sean Bowman
Date:   11/19/2026

'''

# Standard library imports
import argparse
import json
import os
import re
import sys

repositoryRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
summaryPath = os.path.join(repositoryRoot, 'docs', 'validationStatus.json')
markdownPath = os.path.join(repositoryRoot, 'docs', 'validationStatus.md')

# Weakest first; a badge carries the weakest status among its models
statusRank = {'unvalidated': 0, 'crossCheck': 1, 'compared': 2, 'calibrated': 3, 'validated': 4}
constructionStatus = 'construction'

# The gas-side model each `gasSideAxialModel` option runs
gasSideModels = {'uniform': 'gasSideUniform', 'measured': 'gasSideMeasured', 'ievlev': 'gasSideIevlev'}

# The models behind each section of the result table and each headline number. 'gasSide', 'circuit'
# and 'chamberFilm' stand for the model the run used, or nothing where the run has none.
sectionModelIds = {
    'Sizing': ['throatSizing', 'contour'],
    'Combustion Chamber': ['chamberGeometry'],
    'Performance: 1D estimate and delivered': ['cea', 'contour', 'friction', 'deliveredPerformance'],
    'Chamber': ['cea'],
    'Throat': ['cea'],
    'Cooling': ['gasSide', 'coolantSide', 'pressureDrop', 'circuit', 'chamberFilm'],
    'Coolant passes': ['coolantCircuit', 'coolantSide', 'pressureDrop', 'turnaround'],
    'Extension circuit': ['extensionCircuit', 'coolantSide', 'pressureDrop'],
    'Gas generator and turbine': ['gasGenerator'],
    'Films over the extension': ['extensionFilm', 'radiativeExtension'],
    'Engine flows': ['flowAccounting', 'extensionFilm', 'friction', 'deliveredPerformance'],
    'Plume': ['plumeMarch', 'plumeCorrelations'],
}
headlineModelIds = {
    'isp': ['contour', 'deliveredPerformance'],
    'thrust': ['contour', 'deliveredPerformance'],
    'length': ['contour'],
    'exitDiameter': ['contour'],
    'peakWall': ['gasSide', 'coolantSide', 'circuit', 'chamberFilm'],
    'drop': ['pressureDrop'],
    'dropDown': ['pressureDrop', 'turnaround', 'coolantCircuit'],
    'dropUp': ['pressureDrop', 'turnaround', 'coolantCircuit'],
}

_cache = {'mtime': None, 'summary': None}

def load() -> dict | None:

    '''

    The summary, read again when the file changes; None when it is missing or does not read.

    '''

    try:
        mtime = os.path.getmtime(summaryPath)
    except OSError:
        return None
    if _cache['mtime'] != mtime:
        try:
            with open(summaryPath, encoding = 'utf-8') as handle:
                _cache['summary'] = json.load(handle)
        except (OSError, ValueError):
            _cache['summary'] = None
        _cache['mtime'] = mtime

    return _cache['summary']

def normalized(text: str) -> str:

    '''Text with every run of whitespace made one space, so a quote matches across line wraps.'''

    return ' '.join(str(text).split())

def _plain(text: str) -> str:

    '''A record's paragraph as the browser shows it: bold markers dropped, a link reduced to its text.'''

    return re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text.replace('**', ''))

def _on(value) -> bool:

    return str(value).lower() in ('on', 'true', '1')

def modelsFor(ids: list, nozzle) -> list:

    '''

    The model ids a list names, with the stand-ins resolved for this run and duplicates dropped.

    '''

    resolved = []
    for modelId in ids:
        if modelId == 'gasSide':
            modelId = gasSideModels.get(str(getattr(nozzle, 'gasSideAxialModel', None) or 'uniform'), 'gasSideUniform')
        elif modelId == 'circuit':
            modelId = 'coolantCircuit' if getattr(nozzle, 'coolantCircuitSolution', None) is not None else None
        elif modelId == 'chamberFilm':
            modelId = 'filmChamber' if _on(getattr(nozzle, 'filmCooling', 'off')) else None
        if modelId is not None and modelId not in resolved:
            resolved.append(modelId)

    return resolved

def badge(ids: list, summary: dict | None = None) -> dict | None:

    '''

    A badge for the models named: the weakest of their statuses, and each model as the summary
    records it. None when the summary is missing or names none of them.

    Returns:
    --------
    dict : {'status', 'label', 'meaning', 'models': [{'id', 'name', 'status', 'label', 'reference',
        'result', 'gap', 'record'}]}

    '''

    summary = summary if summary is not None else load()
    if not summary:
        return None
    statuses = summary.get('statuses', {})
    known = summary.get('models', {})
    models = []
    for modelId in ids:
        model = known.get(modelId)
        if model is None:
            continue
        status = model.get('status', 'unvalidated')
        sources = model.get('sources') or [{}]
        models.append({'id': modelId, 'name': model.get('name', modelId), 'status': status,
                       'label': statuses.get(status, {}).get('label', status),
                       'reference': model.get('reference', ''), 'result': model.get('result', ''),
                       'gap': model.get('gap', ''), 'record': sources[0].get('path', '')})
    if not models:
        return None

    physical = [model['status'] for model in models if model['status'] != constructionStatus]
    status = min(physical, key = lambda name: statusRank.get(name, 0)) if physical else constructionStatus
    return {'status': status, 'label': statuses.get(status, {}).get('label', status),
            'meaning': statuses.get(status, {}).get('meaning', ''), 'models': models}

def annotate(table: dict, nozzle) -> dict:

    '''

    Put a `validation` badge on each headline number and section of a result table, in place.

    Parameters:
    -----------
    table : dict
        novaGui.analysis.resultTable's table.
    nozzle : NOVA.Nozzle
        The run it was built from, which says which models the run used.

    Returns:
    --------
    dict : the same table

    '''

    summary = load()
    for number in table.get('headline', []):
        number['validation'] = badge(modelsFor(headlineModelIds.get(number['key'], []), nozzle), summary)
    for section in table.get('sections', []):
        section['validation'] = badge(modelsFor(sectionModelIds.get(section['title'], []), nozzle), summary)

    return table

def _recordFile(path: str) -> str | None:

    '''A record's absolute path, only if it lies inside the repository.'''

    absolute = os.path.realpath(os.path.join(repositoryRoot, path))
    return absolute if absolute.startswith(os.path.realpath(repositoryRoot) + os.sep) else None

def passages(modelId: str, summary: dict | None = None) -> list | None:

    '''

    The paragraphs of a model's records that carry its quotes, whitespace made single, with bold
    markers dropped and links reduced to their text.

    Returns:
    --------
    list : [{'path', 'quote', 'text'}], with `text` '' where the record no longer carries the quote;
        None for a model the summary does not name

    '''

    summary = summary if summary is not None else load()
    model = (summary or {}).get('models', {}).get(modelId)
    if model is None:
        return None
    found = []
    for source in model.get('sources', []):
        path, quote = source.get('path', ''), normalized(source.get('quote', ''))
        absolute = _recordFile(path)
        text = ''
        if absolute is not None and os.path.isfile(absolute):
            with open(absolute, encoding = 'utf-8') as handle:
                content = handle.read()
            for paragraph in re.split(r'\n\s*\n', content):
                if quote and quote in normalized(paragraph):
                    text = normalized(paragraph)
                    break
        found.append({'path': path, 'quote': _plain(quote), 'text': _plain(text)})

    return found

def markdown(summary: dict) -> str:

    '''

    The summary table, as docs/validationStatus.md carries it.

    '''

    statuses = summary['statuses']
    lines = ['# NOVA Validation Status', '',
             'The validation status of each model behind NOVA\'s reported results, written from '
             '[validationStatus.json](validationStatus.json) by `python -m novaGui.validationStatus --write`. Each '
             'status stands on the records linked in its row, which carry the quoted passage word for word; '
             '`tests/testValidationStatus.py` fails when one no longer does. The GUI\'s result table shows the same '
             'statuses on its headline numbers and sections, each the weakest status among the models behind it.',
             '', '## Statuses', '', '| Status | Meaning |', '| --- | --- |']
    for status in list(statusRank)[::-1] + [constructionStatus]:
        lines.append(f'| {statuses[status]["label"]} | {statuses[status]["meaning"]} |')
    lines += ['', '## Models', '', '| Model | Status | Reference | Result | Records |', '| --- | --- | --- | --- | --- |']
    for model in summary['models'].values():
        records = []
        for source in model['sources']:
            link = os.path.relpath(os.path.join(repositoryRoot, source['path']),
                                   os.path.dirname(markdownPath)).replace(os.sep, '/')
            entry = f'[{os.path.basename(source["path"])}]({link})'
            if entry not in records:
                records.append(entry)
        result = model['result'] + (f' To close it: {model["gap"]}' if model.get('gap') else '')
        lines.append(f'| {model["name"]} | {statuses[model["status"]]["label"]} | {model["reference"]} | '
                     f'{result} | {", ".join(records)} |')
    lines += ['', 'Author: Sean Bowman', '']

    return '\n'.join(lines)

def main(argv: list | None = None) -> int:

    parser = argparse.ArgumentParser(prog = 'python -m novaGui.validationStatus',
                                     description = 'Write or check docs/validationStatus.md')
    parser.add_argument('--write', action = 'store_true', help = 'write the summary table')
    parser.add_argument('--check', action = 'store_true', help = 'exit 1 if the summary table is out of date')
    options = parser.parse_args(argv)

    summary = load()
    if summary is None:
        print(f'{summaryPath} is missing or does not read', file = sys.stderr)
        return 1
    text = markdown(summary)
    if options.write:
        with open(markdownPath, 'w', encoding = 'utf-8', newline = '\n') as handle:
            handle.write(text)
        print(f'wrote {markdownPath}')
        return 0
    try:
        with open(markdownPath, encoding = 'utf-8') as handle:
            current = handle.read()
    except OSError:
        current = ''
    if current != text:
        print(f'{markdownPath} is out of date: run python -m novaGui.validationStatus --write', file = sys.stderr)
        return 1
    print('up to date')
    return 0

if __name__ == '__main__':
    sys.exit(main())
