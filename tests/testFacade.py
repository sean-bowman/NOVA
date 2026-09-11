'''

The closing checks on the decomposition.

The effort is closed when `Nozzle` is a facade and every capability behind it stands on its own.
That is a structural claim, so it is checked structurally rather than asserted in a document.

Four things are held here:

  - **No module reaches back.** A module that imports `Nozzle`, or that still says `self`, has not
    actually been separated from it; it has been moved.
  - **`Nozzle` computes nothing.** Every public method is a facade: it assembles inputs, calls a
    module, and copies the result back. What it must not contain is arithmetic.
  - **Every state object is complete.** A field reached by name rather than by attribute is
    invisible to a static read, and four of them were lost that way during this work. Both forms
    are collected here and held against what each state declares.
  - **Nothing writes beside the source.** Output resolves through one hook, and the repository
    root holds no generated file.

Author: Sean Bowman

'''

import ast
import importlib
import io
import os
import re
import sys

import pytest

repositoryRoot   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
packageDirectory = os.path.join(repositoryRoot, 'src', 'NOVA')
# Every module the decomposition produced, plus the ones it built on.
decomposedModules = (
    'ablative', 'chamber', 'channelGeometry', 'channelSizing', 'characteristics',
    'ceaInterface', 'config',
    'contour', 'contourKernel', 'exports', 'figures', 'gasDynamics', 'keepOut', 'materials',
    'plume', 'regenChannels', 'regenStations', 'regenThermal', 'units', 'validation',
    'nozzleVolutes',
)

def moduleSource(name: str) -> str:

    '''The text of one module.'''

    return io.open(os.path.join(packageDirectory, name + '.py'), encoding = 'utf-8').read()

def packageModule(name: str):

    '''One module of the package, imported by its dotted name.'''

    return importlib.import_module('NOVA.' + name)

def nozzleClass() -> ast.ClassDef:

    '''The Nozzle class, parsed.'''

    tree = ast.parse(moduleSource('Nozzle'))

    return [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Nozzle'][0]

class TestModulesStandAlone:

    '''A module that reaches back has not been separated.'''

    @pytest.mark.parametrize('name', decomposedModules)
    def testNoModuleImportsNozzle(self, name):

        source = moduleSource(name)

        assert not re.search(r'^\s*(from|import)\s+\.?Nozzle\b', source, re.MULTILINE), \
            f'{name}.py imports Nozzle'

    @pytest.mark.parametrize('name', decomposedModules)
    def testNoModuleReachesThroughSelf(self, name):

        # A leftover self is a reference to an object the module no longer has. Both forms are
        # checked: attribute access, and the by-name reads a static scan would otherwise miss.
        source = moduleSource(name)
        tree = ast.parse(source)

        # A module may define its own classes, whose methods take self legitimately. What must
        # not survive is a reference to self outside one, which is a leftover from the object the
        # code used to live on. Both forms count: attribute access, and the by-name reads that a
        # static scan for attribute access would otherwise miss.
        insideAClass = set()
        for classNode in [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]:
            for node in ast.walk(classNode):
                insideAClass.add(id(node))

        offenders = [f'self.{node.attr}' for node in ast.walk(tree)
                     if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                     and node.value.id == 'self' and id(node) not in insideAClass]
        offenders += [f'{node.func.id}(self, ...)' for node in ast.walk(tree)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                      and node.func.id in ('getattr', 'hasattr', 'setattr')
                      and node.args and isinstance(node.args[0], ast.Name)
                      and node.args[0].id == 'self' and id(node) not in insideAClass]

        assert offenders == [], f'{name}.py reaches self outside a class: {offenders[:3]}'

    @pytest.mark.parametrize('name', decomposedModules)
    def testEveryModuleImportsOnItsOwn(self, name):

        packageModule(name)

class TestNozzleIsAFacade:

    '''Nozzle assembles and delegates. It does not compute.'''

    def facadeMethods(self):

        '''Public methods, excluding the state builders and the two path resolvers.'''

        return [method for method in nozzleClass().body
                if isinstance(method, ast.FunctionDef)
                and not method.name.startswith('_')
                and not method.name.endswith(('State', 'Inputs', 'Context', 'Contour'))]

    def testNoMethodCarriesALoop(self):

        # A loop in a facade is work the facade is doing itself.
        offenders = []
        for method in self.facadeMethods():
            for node in ast.walk(method):
                if isinstance(node, (ast.For, ast.While)):
                    # The copy-back loop over an outputs tuple is the facade pattern itself.
                    if isinstance(node, ast.For) and isinstance(node.iter, ast.Name) \
                       and node.iter.id.endswith('Outputs'):
                        continue
                    offenders.append(method.name)
                    break

        assert offenders == [], offenders

    def testNoMethodDoesArithmetic(self):

        # Anything computing a number is physics that belongs in a module.
        offenders = []
        for method in self.facadeMethods():
            for node in ast.walk(method):
                if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div,
                                                                       ast.Pow, ast.Sub)):
                    offenders.append(f'{method.name}:{node.lineno}')
                    break

        assert offenders == [], offenders

    def testEveryFacadeMethodIsDocumented(self):

        undocumented = [method.name for method in self.facadeMethods()
                        if ast.get_docstring(method) is None]

        assert undocumented == []

    def testTheClassIsSmallEnoughToRead(self):

        # Not an arbitrary bound: it is the size at which the class stops being a facade and
        # starts being a place things accumulate again. It began this effort at 12,528 lines.
        source = moduleSource('Nozzle')

        assert source.count('\n') < 2500, f'Nozzle.py is {source.count(chr(10))} lines'

class TestStateObjectsAreComplete:

    '''A field reached by name is invisible to a static read, and four were lost that way.'''

    stateModules = {
        'regenChannels': 'RegenChannelState',
        'channelSizing': 'ChannelSizingState',
        'nozzleVolutes': 'RegenVoluteState',
        'chamber':       'ConvergingSectionState',
        'regenStations': 'RegenStationState',
        'plume':         'PlumeContour',
    }

    def fieldsReached(self, name: str, variableName: str) -> set:

        '''Every field the module reaches, by attribute and by name.'''

        source = moduleSource(name)
        tree = ast.parse(source)

        reached = {node.attr for node in ast.walk(tree)
                   if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                   and node.value.id == variableName}
        reached |= set(re.findall(
            r"\b(?:get|has|set)attr\(" + variableName + r",\s*'(\w+)'", source))
        reached |= set(re.findall(
            r"\b_specified\(" + variableName + r",\s*'(\w+)'", source))

        return reached

    @pytest.mark.parametrize('name, stateName', sorted(stateModules.items()))
    def testEveryFieldReachedIsDeclared(self, name, stateName):

        module = packageModule(name)
        declared = set(getattr(module, stateName).__dataclass_fields__)

        variableName = 'contour' if stateName == 'PlumeContour' else 'state'
        reached = self.fieldsReached(name, variableName)

        assert reached <= declared, sorted(reached - declared)

    @pytest.mark.parametrize('name, stateName', sorted(stateModules.items()))
    def testTheNozzleSeedsEveryField(self, name, stateName):

        import matplotlib
        matplotlib.use('Agg', force = True)
        from NOVA.Nozzle import Nozzle

        module = packageModule(name)
        builder = {'RegenChannelState':      'regenChannelState',
                   'ChannelSizingState':     'channelSizingState',
                   'RegenVoluteState':       'regenVoluteState',
                   'ConvergingSectionState': 'convergingSectionState',
                   'RegenStationState':      'regenStationState',
                   'PlumeContour':           'plumeContour'}[stateName]

        state = getattr(Nozzle(), builder)()
        missing = [field for field in getattr(module, stateName).__dataclass_fields__
                   if not hasattr(state, field)]

        assert missing == []

    def testTheSizingStateBuilderPassesEveryInputField(self):

        # testEveryFieldReachedIsDeclared catches a field the solve reads but the dataclass does
        # not declare. This catches the other direction: a field declared on ChannelSizingState
        # that regenChannels._sizingState forgets to pass. That one is silent, because the field
        # keeps its dataclass default and the solve runs on a None or a NaN it was never given.
        source = moduleSource('channelSizing')
        tree = ast.parse(source)

        # The dataclass splits its inputs from its outputs with a comment, which the AST drops,
        # so the split is found in the text and the fields filtered by line number.
        marker = '# -- What the solve produces -- #'
        assert source.count(marker) == 1, 'the input/output marker moved or was duplicated'
        outputsBegin = source[:source.index(marker)].count('\n') + 1

        declaration = [node for node in ast.walk(tree)
                       if isinstance(node, ast.ClassDef) and node.name == 'ChannelSizingState'][0]
        inputFields = {node.target.id for node in declaration.body
                       if isinstance(node, ast.AnnAssign) and node.lineno < outputsBegin}

        builder = [node for node in ast.walk(ast.parse(moduleSource('regenChannels')))
                   if isinstance(node, ast.FunctionDef) and node.name == '_sizingState'][0]
        constructions = [node for node in ast.walk(builder)
                         if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                         and node.func.id == 'ChannelSizingState']
        assert len(constructions) == 1, '_sizingState builds the state once'
        passed = {keyword.arg for keyword in constructions[0].keywords}

        assert inputFields <= passed, sorted(inputFields - passed)

    def testEveryOutputTupleNamesDeclaredFields(self):

        pairs = (('regenChannels', 'RegenChannelState', 'regenChannelOutputs'),
                 ('channelSizing', 'ChannelSizingState', 'channelSizingOutputs'),
                 ('nozzleVolutes', 'RegenVoluteState',   'regenVoluteOutputs'),
                 ('chamber',       'ConvergingSectionState', 'convergingSectionOutputs'),
                 ('regenStations', 'RegenStationState',  'regenStationOutputs'))

        for name, stateName, outputName in pairs:
            module = packageModule(name)
            declared = set(getattr(module, stateName).__dataclass_fields__)
            outputs = set(getattr(module, outputName))
            assert outputs <= declared, (name, sorted(outputs - declared))

class TestOutputStaysOutOfTheRepository:

    '''Generated files collect in one place, not beside the source.'''

    def testTheOutputRootIsTheRunsDirectory(self):

        import matplotlib
        matplotlib.use('Agg', force = True)
        from NOVA.Nozzle import Nozzle

        assert os.path.basename(Nozzle()._getOutputRoot()) == 'runs'

    def testTheRepositoryRootHoldsNoGeneratedFile(self):

        generated = [entry for entry in os.listdir(repositoryRoot)
                     if entry.lower().endswith(('.json', '.pkl', '.npz', '.stl', '.png'))]

        assert generated == []

    def testEveryOverrideTargetsTheOutputHook(self):

        # The showcase scripts and the GUI redirect output. They must override the output hook,
        # not the repository root, or they move where the tool thinks it is installed.
        for relative in ('featureShowcase/runBaseCase.py', 'featureShowcase/buildContourValidation.py',
                         'featureShowcase/buildReferenceOverlays.py', 'novaGui/runner.py'):
            source = io.open(os.path.join(repositoryRoot, relative), encoding = 'utf-8').read()
            assert '_getRepositoryRoot =' not in source, relative
            assert '_getOutputRoot =' in source, relative
