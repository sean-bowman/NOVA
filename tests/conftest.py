# -- NOVA: Test Session Configuration -- #

'''

What the whole test session needs set before any test module is imported.

pytest imports this before it collects anything, which is the only moment early enough to decide
things that are fixed at import time. Two of them are.

**No figure may open a window.** NOVA draws a lot of them, and a suite that opens even a few
leaves somebody clicking through browser tabs and Tk windows before the run can finish. Setting
`NOVA_HEADLESS` here reaches `figures.headlessPlots`, which selects a non-interactive matplotlib
backend before pyplot is imported and turns off plotly's browser launch. Nothing is suppressed
except the display: every figure is still built and every file still written, so a test that
checks an export still has something to check.

It is set with `setdefault` rather than assigned, so a value already in the environment wins.
Exporting `NOVA_HEADLESS=0` before a run puts the windows back, which is what to do when the
thing being debugged is a plot.

**The backend is forced as well as requested.** A test run started through an IDE can have
imported pyplot already, before this file is read, in which case the environment variable arrives
too late to choose the backend and only forcing it works.

Author: Sean Bowman

'''

import os

os.environ.setdefault('NOVA_HEADLESS', '1')

import matplotlib

matplotlib.use('Agg', force = True)

import matplotlib.pyplot as plt
import pytest

@pytest.fixture(autouse = True)
def closeFiguresAfterEveryTest():

    '''

    Discard whatever figures a test left behind.

    Nothing in NOVA closes a figure, which costs nothing in a single run and accumulates across a
    suite this size. A non-interactive backend hides the symptom rather than removing it: the
    figures are still held open, and past twenty of them matplotlib starts warning about it in
    the middle of unrelated output. No test reads a figure, so there is nothing to preserve.

    '''

    yield

    plt.close('all')
