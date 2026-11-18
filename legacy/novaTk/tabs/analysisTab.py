
# -- Analyze Tab -- #

'''

Scalar results from the run: sizing, the chamber, delivered performance, station thermochemistry
from CEA, the regenerative cooling summary when a jacket was built, and the plume. The figures that
go with them are on the View tab.

Author: Sean Bowman
Date:   08/28/2026

'''

from tkinter import ttk

from novaGui.analysis import resultRows

from .. import theme
from ..widgets import card

class AnalysisTab(ttk.Frame):

    '''

    Grouped result table.

    '''

    def __init__(self, master, app):

        super().__init__(master, style = 'TFrame', padding = theme.scaled(8))

        self._app = app

        header = ttk.Frame(self, style = 'TFrame', padding = (theme.scaled(4), 0, theme.scaled(4), theme.scaled(6)))
        header.pack(fill = 'x')
        ttk.Label(header, text = 'RESULTS', style = 'Eyebrow.TLabel').pack(side = 'left')
        self._summary = ttk.Label(header, text = '', style = 'Muted.TLabel')
        self._summary.pack(side = 'left', padx = theme.scaled(12))

        treeWrap = card(self, fill = 'both', expand = True)
        self._tree = ttk.Treeview(treeWrap, columns = ('value',), show = 'tree headings', height = 24)
        self._tree.heading('#0', text = 'Quantity')
        self._tree.heading('value', text = 'Value')
        self._tree.column('#0', width = theme.scaled(340), anchor = 'w')
        self._tree.column('value', width = theme.scaled(220), anchor = 'e')
        scroll = ttk.Scrollbar(treeWrap, orient = 'vertical', command = self._tree.yview, style = 'Card.Vertical.TScrollbar')
        self._tree.configure(yscrollcommand = scroll.set)
        scroll.pack(side = 'right', fill = 'y')
        self._tree.pack(side = 'left', fill = 'both', expand = True)

        self._placeholder()

    def _placeholder(self) -> None:

        self._tree.delete(*self._tree.get_children())
        node = self._tree.insert('', 'end', text = 'No run yet', open = True)
        self._tree.insert(node, 'end', text = 'Generate a nozzle from the Design tab', values = ('',))

    def refresh(self, runResult) -> None:

        nozzle = getattr(runResult, 'nozzle', None)
        if nozzle is None:
            self._placeholder()
            return

        self._tree.delete(*self._tree.get_children())
        summary, sections = resultRows(nozzle)
        for title, rows in sections:
            node = self._tree.insert('', 'end', text = title, open = True)
            for label, text in rows:
                self._tree.insert(node, 'end', text = label, values = (text,))
        self._summary.configure(text = summary)
