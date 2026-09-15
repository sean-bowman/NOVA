# -- NOVA: Plot Suppression Tests -- #

'''

That a run can be told not to open anything, and that it stays that way.

A figure that opens a window costs nothing the first time and buries a developer on the twentieth.
There is no error when it happens, nothing fails, and the only symptom is a browser full of tabs
after a test run, so it comes back the moment somebody adds a display without thinking about it.
That is what makes it worth a test rather than a convention.

Two things are checked. The first is behavioral: `showFigure` and the plotly `auto_open` gate do
what they claim against the environment variable. The second is structural: no module displays a
figure by any route other than `showFigure`, and no plotly write leaves `auto_open` at its
default. The structural half is the one that holds, because it fails on the line that would
reintroduce the problem rather than on a symptom somewhere downstream.

What is deliberately not checked is that no window appears. That needs a display to test against
and would pass vacuously on a headless machine, which is every machine that would run it in
anger.

Author: Sean Bowman

'''

import ast
import io
import os
import re

import pytest

from NOVA.utils import headlessPlots, showFigure

repositoryRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
packageDirectory = os.path.join(repositoryRoot, 'src', 'NOVA')

def packageModules():

    '''Every module in the package, as a name and its source.'''

    for name in sorted(os.listdir(packageDirectory)):
        if name.endswith('.py'):
            path = os.path.join(packageDirectory, name)
            yield name, io.open(path, encoding = 'utf-8').read()

class TestTheSwitchItself:

    '''`headlessPlots` reads the environment and nothing else.'''

    @pytest.mark.parametrize('value', ['1', 'true', 'True', 'on', 'yes'])
    def testItIsOnForAnythingMeaningful(self, value, monkeypatch):

        monkeypatch.setenv('NOVA_HEADLESS', value)

        assert headlessPlots() is True

    @pytest.mark.parametrize('value', ['', '0', 'false', 'False', 'off', '  '])
    def testItIsOffForTheValuesThatMeanOff(self, value, monkeypatch):

        # An empty string has to mean off rather than set, or exporting the name without a value
        # would silently suppress every figure.
        monkeypatch.setenv('NOVA_HEADLESS', value)

        assert headlessPlots() is False

    def testItIsOffWhenTheVariableIsAbsent(self, monkeypatch):

        monkeypatch.delenv('NOVA_HEADLESS', raising = False)

        assert headlessPlots() is False

class TestShowFigure:

    '''The one route a figure takes to a screen.'''

    class RecordingFigure:

        '''Stands in for a plotly figure, which is the case that opens a browser tab.'''

        def __init__(self):
            self.shown = 0

        def show(self, *arguments, **keywords):
            self.shown += 1

    def testItDisplaysWhenNotHeadless(self, monkeypatch):

        monkeypatch.setenv('NOVA_HEADLESS', '0')
        figure = self.RecordingFigure()
        showFigure(figure)

        assert figure.shown == 1

    def testItDisplaysNothingWhenHeadless(self, monkeypatch):

        monkeypatch.setenv('NOVA_HEADLESS', '1')
        figure = self.RecordingFigure()
        showFigure(figure)

        assert figure.shown == 0

    def testItReturnsNothingEitherWay(self, monkeypatch):

        for value in ('0', '1'):
            monkeypatch.setenv('NOVA_HEADLESS', value)
            assert showFigure(self.RecordingFigure()) is None

class TestNoModuleOpensAFigureBehindTheSwitch:

    '''

    The structural half, which is what actually holds the line.

    '''

    def testNothingCallsShowOnAFigureDirectly(self):

        # `showFigure` is the exception, being the thing every other call routes through.
        offenders = []
        for name, source in packageModules():
            if name == 'utils.py':
                continue
            for number, line in enumerate(source.split('\n'), start = 1):
                if re.search(r'\bfig\w*\.show\(', line):
                    offenders.append(f'{name}:{number}')

        assert offenders == [], (
            'these display a figure without going through utils.showFigure, so NOVA_HEADLESS '
            'cannot suppress them: ' + ', '.join(offenders))

    def testUtilsRoutesItsOwnFiguresThroughTheHelper(self):

        # utils is excluded above because it defines the helper, so it is checked here with the
        # helper's own body cut out by line range. That one call is the whole point of it.
        source = io.open(os.path.join(packageDirectory, 'utils.py'), encoding = 'utf-8').read()

        helper = next(node for node in ast.parse(source).body
                      if isinstance(node, ast.FunctionDef) and node.name == 'showFigure')
        exempt = range(helper.lineno, helper.end_lineno + 1)

        offenders = [number for number, line in enumerate(source.split('\n'), start = 1)
                     if re.search(r'\bfig\w*\.show\(', line) and number not in exempt]

        assert offenders == [], offenders

    def testEveryPlotlyWriteDecidesWhetherToOpenABrowser(self):

        # plotly.offline.plot opens a tab unless told not to, and the default is the one that
        # opens. Every call has to say which it wants.
        offenders = []
        for name, source in packageModules():
            for node in ast.walk(ast.parse(source)):
                if not isinstance(node, ast.Call):
                    continue
                function = node.func
                if not (isinstance(function, ast.Name) and function.id == 'plot'):
                    continue
                if not any(keyword.arg == 'auto_open' for keyword in node.keywords):
                    offenders.append(f'{name}:{node.lineno}')

        assert offenders == [], (
            'these write a plotly figure without saying whether to open a browser tab, and the '
            'default opens one: ' + ', '.join(offenders))

class TestTheTestSessionIsHeadless:

    '''The suite has to be suppressed whether or not anybody remembered to set the variable.'''

    def testConftestSetsTheVariableForTheWholeSession(self):

        assert headlessPlots() is True

    def testTheMatplotlibBackendIsNonInteractive(self):

        import matplotlib

        assert matplotlib.get_backend().lower() == 'agg'
