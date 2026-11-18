
# -- NOVA Web Result Table -- #

'''

The Analyze tab's result table for a finished run, as JSON.

The rows come from the Tkinter front end's own table code, `novaGui.tabs.analysisTab.AnalysisTab.
refresh`, so both front ends list the same quantities with the same formatting. That method fills a
ttk.Treeview and a summary label; here it runs on a stand-in object whose tree and label record
what they are given, and no Tk window is created. The stand-in carries every helper the class
defines, so a helper added to the table code is picked up without a change here.

The Tkinter table packs the three performance columns (equilibrium 1D, chamber gas 1D, delivered)
into one cell joined by `  |  `, under a row named `Columns`. The table here splits them into
cells, so the browser draws them as columns.

Returned shape:

    {'summary': str,
     'sections': [{'title': str, 'columns': [str] | None,
                   'rows': [{'label': str, 'cells': [str], 'unit': str}]}]}

A single-value row whose text reads `<number> <unit>` is split into the two, so the browser can
align the numbers; any other text stays whole in `cells` with an empty `unit`.

Author: Sean Bowman
Date:   11/17/2026

'''

# Standard library imports
import re
import types

columnSeparator = '  |  '
_leadingNumber = re.compile(r'^([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s+(\S.*)$')

class _TreeRecorder:

    '''Records the ttk.Treeview calls the table code makes: insert, delete, get_children.'''

    def __init__(self):

        self.items = {}               # item id -> {'parent', 'text', 'values'}
        self.order = []               # item ids in insertion order
        self._count = 0

    def insert(self, parent, index, iid = None, text = '', values = (), **_options):

        self._count += 1
        item = iid or f'I{self._count:04d}'
        self.items[item] = {'parent': parent, 'text': str(text), 'values': tuple(values)}
        self.order.append(item)
        return item

    def delete(self, *items):

        doomed = set(items)
        # Deleting a parent deletes its children, as in Tk
        changed = True
        while changed:
            changed = False
            for item, entry in self.items.items():
                if entry['parent'] in doomed and item not in doomed:
                    doomed.add(item)
                    changed = True
        for item in doomed:
            self.items.pop(item, None)
        self.order = [item for item in self.order if item not in doomed]

    def get_children(self, item = ''):

        return tuple(child for child in self.order if self.items[child]['parent'] == item)

class _LabelRecorder:

    '''Records the text a ttk.Label is configured with.'''

    def __init__(self):

        self.text = ''

    def configure(self, text = None, **_options):

        if text is not None:
            self.text = str(text)

def _tableClass():

    '''

    A plain class carrying AnalysisTab's methods but not its ttk.Frame base, so `refresh` runs
    without a Tk root.

    '''

    from novaGui.tabs.analysisTab import AnalysisTab

    methods = {name: value for name, value in vars(AnalysisTab).items()
               if name not in ('__init__', '__dict__', '__weakref__', '__module__', '__qualname__')}
    return type('AnalysisTable', (), methods)

def _splitUnit(text: str) -> tuple:

    '''

    ('1234', 'N') from '1234 N'. Text whose remainder holds another number ('12 channels, 1.2 g/s
    each', '300.0 to 340.0 K') stays whole: it is a sentence, not a value and a unit.

    '''

    match = _leadingNumber.match(text)
    if match is None:
        return text, ''
    number, rest = match.groups()
    if any(_leadingNumber.match(token + ' x') for token in rest.replace(',', ' ').split()):
        return text, ''
    return number, rest

def resultTable(nozzle) -> dict:

    '''

    The result table for a finished run's Nozzle.

    Parameters:
    -----------
    nozzle : NOVA.Nozzle
        The run's Nozzle, after generateNozzle.

    Returns:
    --------
    dict : {'summary', 'sections'}; see the module docstring

    '''

    table = _tableClass()()
    table._tree = _TreeRecorder()
    table._summary = _LabelRecorder()
    table._app = None
    table.refresh(types.SimpleNamespace(nozzle = nozzle))

    tree = table._tree
    sections = []
    for sectionId in tree.get_children(''):
        columns = None
        rows = []
        for rowId in tree.get_children(sectionId):
            entry = tree.items[rowId]
            text = str(entry['values'][0]) if entry['values'] else ''
            if entry['text'] == 'Columns' and columnSeparator in text:
                columns = text.split(columnSeparator)
                continue
            cells = text.split(columnSeparator) if columns and columnSeparator in text else [text]
            unit = ''
            if len(cells) == 1:
                cells[0], unit = _splitUnit(cells[0])
            rows.append({'label': entry['text'].strip(), 'cells': cells, 'unit': unit,
                         'indent': entry['text'].startswith(' ')})
        sections.append({'title': tree.items[sectionId]['text'], 'columns': columns, 'rows': rows})

    return {'summary': table._summary.text, 'sections': sections}
