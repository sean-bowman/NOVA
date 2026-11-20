# -- NOVA: Validation Status Tests -- #

'''

The validation status summary (docs/validationStatus.json) against the records it is summarized
from, and the badges the GUI's result table carries from it.

Every status stands on passages quoted from its records: the documents, the module docstrings and
the validation write-ups. These tests fail when a record no longer carries a quoted passage, so a
record that changes its numbers or its verdict forces the summary to be read again; when the
summary table docs/validationStatus.md is not the one the summary writes; and when the result
table gains a section or a headline number with no model behind it. The badge tests hold the
rule that a result reads as the weakest status among its models, and that the models follow
what the run used. None of them needs a run; they take about a second.

Author: Sean Bowman

'''

import os
import re
import sys
import types

import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

from novaGui import validationStatus

@pytest.fixture(scope = 'module')
def summary():
    loaded = validationStatus.load()
    assert loaded is not None, f'{validationStatus.summaryPath} is missing or does not read'
    return loaded

def _modelIds(summary) -> list:
    return list(summary['models'])

@pytest.mark.parametrize('modelId', _modelIds(validationStatus.load() or {'models': {}}))
def testEveryQuoteIsStillInItsRecord(summary, modelId):
    '''A status stands on its quotes; a record that no longer carries one sends the summary back to be read.'''
    for passage in validationStatus.passages(modelId, summary):
        assert passage['text'], f'{passage["path"]} no longer carries: {passage["quote"]}'
        assert passage['quote'] in passage['text']

def testEveryModelIsComplete(summary):
    statuses = set(summary['statuses'])
    assert statuses == set(validationStatus.statusRank) | {validationStatus.constructionStatus}
    for modelId, model in summary['models'].items():
        assert model['status'] in statuses, modelId
        for field in ('name', 'reference', 'result'):
            assert model.get(field), f'{modelId} has no {field}'
        assert model['sources'], f'{modelId} cites no record'
        for source in model['sources']:
            assert os.path.isfile(os.path.join(root, source['path'])), source['path']

def testTheSummaryTableIsCurrent(summary):
    '''docs/validationStatus.md is what the summary writes; `python -m novaGui.validationStatus --write` makes it so.'''
    with open(validationStatus.markdownPath, encoding = 'utf-8') as handle:
        assert handle.read() == validationStatus.markdown(summary)

def testEverySectionAndHeadlineNumberHasItsModels(summary):
    '''
    Each section title and headline key the result table can produce maps to models the summary
    holds, so no result reaches the browser without a status.
    '''
    with open(os.path.join(root, 'novaGui', 'analysis.py'), encoding = 'utf-8') as handle:
        source = handle.read()
    titles = set(re.findall(r"section\('([^']+)'\)", source))
    assert titles == set(validationStatus.sectionModelIds)
    keys = set(re.findall(r"add\('(\w+)'", source)) | {'dropDown', 'dropUp'}
    assert keys == set(validationStatus.headlineModelIds)
    standIns = {'gasSide', 'circuit', 'chamberFilm'}
    named = {modelId for ids in list(validationStatus.sectionModelIds.values()) + list(validationStatus.headlineModelIds.values())
             for modelId in ids} - standIns
    assert named <= set(summary['models'])
    assert set(validationStatus.gasSideModels.values()) <= set(summary['models'])

@pytest.mark.parametrize('ids, status', [
    (['cea'], 'validated'),
    (['cea', 'contour'], 'crossCheck'),
    (['contour', 'coolantSide'], 'crossCheck'),
    (['cea', 'gasSideMeasured'], 'calibrated'),
    (['cea', 'gasSideUniform', 'pressureDrop'], 'unvalidated'),
    (['chamberGeometry'], 'construction'),
    (['chamberGeometry', 'cea'], 'validated'),
])
def testABadgeReadsAsItsWeakestModel(summary, ids, status):
    shown = validationStatus.badge(ids, summary)
    assert shown['status'] == status
    assert shown['label'] == summary['statuses'][status]['label']
    assert [model['id'] for model in shown['models']] == ids

def testABadgeOfNoKnownModelIsNone(summary):
    assert validationStatus.badge(['notAModel'], summary) is None
    assert validationStatus.badge(['cea'], {}) is None

def testTheModelsFollowWhatTheRunUsed():
    '''The gas-side model the run selected; the circuit and the chamber film only where the run has them.'''
    standIns = ['gasSide', 'coolantSide', 'circuit', 'chamberFilm']
    plain = types.SimpleNamespace(gasSideAxialModel = None, filmCooling = 'off', coolantCircuitSolution = None)
    assert validationStatus.modelsFor(standIns, plain) == ['gasSideUniform', 'coolantSide']
    full = types.SimpleNamespace(gasSideAxialModel = 'ievlev', filmCooling = 'on', coolantCircuitSolution = object())
    assert validationStatus.modelsFor(standIns, full) == ['gasSideIevlev', 'coolantSide', 'coolantCircuit', 'filmChamber']
    measured = types.SimpleNamespace(gasSideAxialModel = 'measured')
    assert validationStatus.modelsFor(['gasSide', 'gasSide'], measured) == ['gasSideMeasured']

def testATableIsAnnotatedForItsRun():
    nozzle = types.SimpleNamespace(gasSideAxialModel = 'measured', filmCooling = 'off', coolantCircuitSolution = None)
    table = {'headline': [{'key': 'peakWall'}, {'key': 'length'}],
             'sections': [{'title': 'Chamber'}, {'title': 'Not a section'}]}
    validationStatus.annotate(table, nozzle)
    peak, length = table['headline']
    assert [model['id'] for model in peak['validation']['models']] == ['gasSideMeasured', 'coolantSide']
    assert peak['validation']['status'] == 'compared'
    assert length['validation']['status'] == 'crossCheck'
    assert table['sections'][0]['validation']['status'] == 'validated'
    assert table['sections'][1]['validation'] is None

def testAPassageMarksItsQuoteInPlainText(summary):
    '''The browser shows a record's paragraph with the quote marked, bold markers and link syntax dropped.'''
    found = validationStatus.passages('gasSideIevlev', summary)[0]
    assert '**' not in found['text'] and '](' not in found['text']
    assert found['quote'] in found['text']
    assert validationStatus.passages('notAModel', summary) is None
