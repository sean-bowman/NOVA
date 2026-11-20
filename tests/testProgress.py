
'''

Tests for the run progress events (NOVA.progress) and the model both front ends fold them with
(novaGui.progress.RunProgress).

The reporter's own behavior is held on small blocks: nesting and paths, a stage that raises, the
step throttle, the JSON safety of iteration metrics, a broken listener and the thread a reporter
belongs to. A reduced single-pass run (conical contour, 24 cooling stations, nothing past the
jacket) is then solved twice, once under a reporter: its events must follow the plan, nest, run
in time order and serialize, no tqdm bar may reach the console while it reports, and the solved
arrays must be identical to the unreported run's. The model is checked on synthetic events and
on that run's events.

Author: Sean Bowman

'''

import contextlib
import io
import json
import os
import threading

import numpy as np
import pytest

from NOVA import progress
from novaGui.progress import RunProgress, keptIterations, loadingCeiling

repositoryRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def record(stepInterval: float = 0.0):

    '''A list that collects events, and the reporter context that fills it.'''

    events = []
    return events, progress.reporting(events.append, stepInterval = stepInterval)

# -- The reporter -- #

class TestWithoutAReporter:

    def testEveryCallIsANoOp(self):

        assert not progress.active()
        progress.plan([('contour', 'Contour')])
        progress.iteration(1, {'change': 1.0})
        with progress.stage('contour', 'Contour'):
            pass

    def testTrackStillYieldsEveryItem(self):

        assert list(progress.track(range(5), label = 'quiet', disable = True)) == [0, 1, 2, 3, 4]

class TestStages:

    def testTheyNestAndCarryTheirPath(self):

        events, reporting = record()
        with reporting:
            assert progress.active()
            with progress.stage('cooling', 'Cooling channels'):
                with progress.stage('circuit', 'Coolant circuit'):
                    progress.iteration(1, {'change': 2.5}, name = 'pass')

        kinds = [(event['type'], event.get('path')) for event in events]
        assert kinds == [('stageStart', 'cooling'), ('stageStart', 'cooling.circuit'),
                         ('iteration', 'cooling.circuit'), ('stageEnd', 'cooling.circuit'),
                         ('stageEnd', 'cooling')]
        assert [event['depth'] for event in events if event['type'] == 'stageStart'] == [0, 1]
        assert all(event['ok'] and event['elapsed'] >= 0.0 for event in events if event['type'] == 'stageEnd')
        assert events[2]['name'] == 'pass' and events[2]['index'] == 1 and events[2]['metrics'] == {'change': 2.5}

    def testOneThatRaisesEndsNotOkAndTheErrorPropagates(self):

        events, reporting = record()
        with reporting, pytest.raises(RuntimeError):
            with progress.stage('contour', 'Contour'):
                raise RuntimeError('solve failed')

        assert events[-1]['type'] == 'stageEnd' and events[-1]['ok'] is False

    def testAKeyWithADotIsRefused(self):

        with pytest.raises(ValueError):
            with progress.stage('a.b', 'A'):
                pass

    def testADisabledOneReportsNothing(self):

        events, reporting = record()
        with reporting:
            with progress.stage('extension', 'Extension', enabled = False):
                progress.iteration(1)

        assert [event['type'] for event in events] == ['iteration']
        assert events[0]['path'] == ''

class TestSteps:

    def testTheFirstAndLastAlwaysGo(self):

        events, reporting = record(stepInterval = 1.0e3)
        with reporting:
            assert list(progress.track(range(10), label = 'stations')) == list(range(10))

        assert [(event['done'], event['total']) for event in events] == [(0, 10), (10, 10)]
        assert events[0]['label'] == 'stations'

    def testWithNoThrottleEveryItemGoes(self):

        events, reporting = record(stepInterval = 0.0)
        with reporting:
            list(progress.track(range(4)))

        assert [event['done'] for event in events] == [0, 1, 2, 3, 4]

    def testAnUnknownLengthIsSentAsNone(self):

        events, reporting = record(stepInterval = 1.0e3)
        with reporting:
            list(progress.track(item for item in range(3)))

        assert [(event['done'], event['total']) for event in events] == [(0, None)]

class TestIterationMetrics:

    def testTheyAreAlwaysValidJson(self):

        events, reporting = record()
        with reporting:
            progress.iteration(3, {'finite': np.float64(1.5), 'notANumber': np.nan, 'infinite': np.inf,
                                   'text': 'four', 'missing': None})

        assert events[0]['metrics'] == {'finite': 1.5, 'notANumber': None, 'infinite': None,
                                        'text': None, 'missing': None}
        json.dumps(events[0], allow_nan = False)

class TestIterationProfiles:

    def testTheyArriveAsListsAndAreAlwaysValidJson(self):

        '''Arrays go as lists of floats with None where not finite; strings stay; metrics as an iteration's.'''

        events, reporting = record()
        with reporting:
            with progress.stage('circuit', 'Coolant circuit'):
                progress.profiles(2, [{'leg': 'down', 'x': np.array([0.0, 0.5]), 'wall': [700.0, np.nan]},
                                      {'leg': 'up', 'x': (0.0, 0.5), 'wall': np.array([650.0, np.inf])}],
                                  {'change': np.float64(1.25), 'tolerance': 0.05}, name = 'pass')

        event = events[1]
        assert {key: event[key] for key in ('type', 'path', 'name', 'index')} == {
            'type': 'profiles', 'path': 'circuit', 'name': 'pass', 'index': 2}
        assert event['metrics'] == {'change': 1.25, 'tolerance': 0.05}
        assert event['profiles'] == [{'leg': 'down', 'x': [0.0, 0.5], 'wall': [700.0, None]},
                                     {'leg': 'up', 'x': [0.0, 0.5], 'wall': [650.0, None]}]
        json.dumps(event, allow_nan = False)

    def testWithoutAReporterNothingIsSent(self):

        assert progress.profiles(1, [{'leg': 'up', 'x': [0.0]}]) is None

    def testTheModelLeavesThemOut(self):

        '''A profiles event is the circuit view's, not the stage tree's: the model ignores it.'''

        model = RunProgress()
        model.apply(plan)
        assert not model.apply(event('profiles', 0.0, path = '', name = 'pass', index = 1, metrics = {}, profiles = []))

class TestTheListener:

    def testOneThatFailsDoesNotStopTheRun(self):

        def broken(event):
            raise OSError('queue closed')

        ran = []
        with progress.reporting(broken):
            with progress.stage('contour', 'Contour'):
                ran.append(True)

        assert ran == [True]

    def testAReporterBelongsToItsThread(self):

        events, reporting = record()
        elsewhere = []

        def other():
            elsewhere.append(progress.active())
            with progress.stage('contour', 'Contour'):
                pass

        with reporting:
            thread = threading.Thread(target = other)
            thread.start()
            thread.join()

        assert elsewhere == [False] and events == []

# -- The plan -- #

def shippedConfig() -> dict:

    with open(os.path.join(repositoryRoot, 'src', 'NOVA', 'assets', 'NOVANozzle.json'), encoding = 'utf-8') as handle:
        return json.load(handle)

def planOf(**overrides) -> list:

    from NOVA import Nozzle

    config = shippedConfig()
    config.update(overrides)
    nozzle = Nozzle()
    nozzle.setInputs(inputsPath = config)
    return [key for key, _ in nozzle.progressPlan()]

class TestThePlan:

    def testTheShippedNozzle(self):

        assert planOf() == ['contour', 'cooling', 'volutes', 'performance', 'plume', 'outputs']

    def testNoChannelsMeansNoVolutes(self):

        assert planOf(makeCoolingChannels = False) == ['contour', 'performance', 'plume', 'outputs']

    def testARadiativeExtensionAddsItsStage(self):

        assert 'extension' in planOf(makeRadiativeExtension = True)

    def testNoAmbientPressureMeansNoPlume(self):

        assert 'plume' not in planOf(plumeAmbientPressure = None, plumeFieldReach = None)

# -- A reduced run, reported and not -- #

@pytest.fixture(scope = 'module')
def reducedRuns(tmp_path_factory):

    '''The reduced single-pass run solved twice: (events, console text, reported, unreported).'''

    from testDefectGuards import runConfiguration

    overrides = dict(divergingSectionType = 'conical', makeInletVolute = False, makeOutletVolute = False,
                     makeRadiativeExtension = False, regenTruncationType = 'none')

    events = []
    console = io.StringIO()
    with progress.reporting(events.append, stepInterval = 0.0):
        with contextlib.redirect_stdout(console), contextlib.redirect_stderr(console):
            reported = runConfiguration(tmp_path_factory.mktemp('reported'), **overrides)
    unreported = runConfiguration(tmp_path_factory.mktemp('unreported'), **overrides)

    return events, console.getvalue(), reported, unreported

class TestAReportedRun:

    def testItFollowsItsPlan(self, reducedRuns):

        events = reducedRuns[0]
        plans = [event for event in events if event['type'] == 'plan']
        started = [event['key'] for event in events if event['type'] == 'stageStart' and event['depth'] == 0]

        assert len(plans) == 1 and events[0]['type'] == 'plan'
        assert [stage['key'] for stage in plans[0]['stages']] == started
        assert started == ['contour', 'cooling', 'performance']

    def testEveryStageClosesInsideItsParent(self, reducedRuns):

        stack = []
        for event in reducedRuns[0]:
            if event['type'] == 'stageStart':
                assert event['path'] == '.'.join(stack + [event['key']])
                stack.append(event['key'])
            elif event['type'] == 'stageEnd':
                assert stack and stack[-1] == event['key'] and event['ok']
                stack.pop()
            elif event['type'] in ('step', 'iteration'):
                assert event['path'] == '.'.join(stack)
        assert stack == []

    def testTheSizingMarchReportsEveryStation(self, reducedRuns):

        steps = [event for event in reducedRuns[0] if event['type'] == 'step'
                 and event['path'] == 'cooling.sizing' and event['label'] == 'Solving for channel radii']

        assert steps and all(event['total'] == 24 for event in steps)
        assert [event['done'] for event in steps] == list(range(25))

    def testItsEventsRunInTimeOrderAndSerialize(self, reducedRuns):

        times = [event['t'] for event in reducedRuns[0]]

        assert times == sorted(times)
        for event in reducedRuns[0]:
            json.dumps(event, allow_nan = False)

    def testNoTqdmBarReachesTheConsole(self, reducedRuns):

        console = reducedRuns[1]

        assert 'Solving for channel radii' not in console
        assert '%|' not in console

    @pytest.mark.parametrize('name', ['xNozzleWall', 'rNozzleWall', 'channelRadius', 'channelWallTemperature',
                                      'coolantExitTemperature', 'coolantExitPressure'])
    def testTheReporterChangesNoResult(self, reducedRuns, name):

        reported, unreported = reducedRuns[2], reducedRuns[3]
        first, second = getattr(reported, name), getattr(unreported, name)

        assert first is not None
        assert np.array_equal(np.asarray(first, dtype = float), np.asarray(second, dtype = float), equal_nan = True)

# -- The model the front ends fold events with -- #

def event(kind: str, t: float, **fields) -> dict:

    return {'type': kind, 't': t, **fields}

def start(t: float, path: str, label: str) -> dict:

    return event('stageStart', t, path = path, key = path.split('.')[-1], label = label, depth = path.count('.'))

def end(t: float, path: str, elapsed: float, ok: bool = True) -> dict:

    return event('stageEnd', t, path = path, key = path.split('.')[-1], depth = path.count('.'), ok = ok,
                 elapsed = elapsed)

plan = event('plan', 0.0, stages = [{'key': 'contour', 'label': 'Contour'},
                                    {'key': 'cooling', 'label': 'Cooling channels'}])

class TestTheModel:

    def testItLoadsUntilThePlanArrives(self):

        model = RunProgress()

        assert model.summary() == (0.0, loadingCeiling, 'loading NOVA')
        assert RunProgress(label = 'starting worker').label == 'starting worker'

    def testTheLastRunsTimesShareOutTheBar(self):

        model = RunProgress(history = {'contour': 1.0, 'cooling': 9.0})
        model.apply(plan)
        model.apply(start(0.0, 'contour', 'Contour'))

        fraction, ceiling, label = model.summary()
        assert fraction == pytest.approx(loadingCeiling)
        assert ceiling == pytest.approx(loadingCeiling + 0.1 * (1.0 - loadingCeiling))
        assert label == 'Contour'

    def testAStepInATopLevelStageMovesTheBar(self):

        model = RunProgress(history = {'contour': 1.0, 'cooling': 1.0})
        model.apply(plan)
        model.apply(start(0.0, 'contour', 'Contour'))
        model.apply(event('step', 1.0, path = 'contour', label = None, done = 5, total = 10))

        assert model.fraction == pytest.approx(loadingCeiling + 0.25 * (1.0 - loadingCeiling))
        assert model.label == 'Contour, 50%'

    def testTheLabelCountsTheIterationInProgress(self):

        model = RunProgress()
        for item in (plan, start(0.0, 'contour', 'Contour'), end(1.0, 'contour', 1.0),
                     start(1.0, 'cooling', 'Cooling channels'), start(1.0, 'cooling.circuit', 'Coolant circuit'),
                     event('iteration', 30.0, path = 'cooling.circuit', name = 'pass', index = 3, metrics = {}),
                     start(30.0, 'cooling.circuit.up', 'Up pass'),
                     event('step', 31.0, path = 'cooling.circuit.up', label = None, done = 9, total = 20)):
            model.apply(item)

        assert model.label == 'Cooling channels, pass 4'
        assert model.detail == 'Cooling channels / Coolant circuit (pass 4) / Up pass 45%'

    def testAStageThatFailsIsNotRemembered(self):

        model = RunProgress()
        for item in (plan, start(0.0, 'contour', 'Contour'), end(2.0, 'contour', 2.0),
                     start(2.0, 'cooling', 'Cooling channels'), end(3.0, 'cooling', 1.0, ok = False)):
            model.apply(item)

        assert [stage['state'] for stage in model.stageList()] == ['done', 'failed']
        assert model.durations() == {'contour': 2.0}

    def testAStageThePlanDidNotNameIsAdded(self):

        model = RunProgress()
        model.apply(plan)
        model.apply(start(0.0, 'extension', 'Extension'))

        assert [stage['key'] for stage in model.stageList()] == ['contour', 'cooling', 'extension']

    def testANothingEventChangesNothing(self):

        model = RunProgress()
        model.apply(plan)

        assert not model.apply(event('step', 0.0, path = '', label = None, done = 0, total = None))

    def testASubStageHoldsItsPassesAndWhatRunsBelowIt(self):

        model = RunProgress()
        for item in (plan, start(0.0, 'contour', 'Contour'), end(1.0, 'contour', 1.0),
                     start(1.0, 'cooling', 'Cooling channels'), start(1.0, 'cooling.circuit', 'Coolant circuit'),
                     start(1.0, 'cooling.circuit.down', 'Down pass'), end(10.0, 'cooling.circuit.down', 9.0),
                     event('iteration', 20.0, path = 'cooling.circuit', name = 'pass', index = 1,
                           metrics = {'upOutletTemperature': 244.0}),
                     start(20.0, 'cooling.circuit.down', 'Down pass'),
                     event('step', 21.0, path = 'cooling.circuit.down', label = None, done = 3, total = 4)):
            model.apply(item)

        cooling = model.stageList()[1]
        (circuit,) = cooling['children']
        assert cooling['note'] == 'pass 2' and cooling['fraction'] is None
        assert circuit['state'] == 'running' and circuit['started'] == 1.0
        assert circuit['detail'] == 'Down pass 75%'
        assert circuit['iterationName'] == 'pass' and circuit['iterationCount'] == 1
        assert circuit['iterations'] == [{'index': 1, 't': 20.0, 'metrics': {'upOutletTemperature': 244.0}}]

    def testAFinishedStageCountsItsIterations(self):

        model = RunProgress()
        items = [plan, start(0.0, 'contour', 'Contour'), start(0.0, 'contour.diverging', 'Diverging section')]
        items += [event('iteration', float(index), path = 'contour.diverging', name = 'evaluation', index = index,
                        metrics = {}) for index in (1, 2, 3)]
        items += [end(4.0, 'contour.diverging', 4.0), end(4.0, 'contour', 4.0)]
        for item in items:
            model.apply(item)

        contour = model.stageList()[0]
        assert contour['note'] == '3 evaluations'
        assert contour['children'][0]['state'] == 'done' and contour['children'][0]['detail'] == ''

    def testItKeepsOnlyTheLatestIterations(self):

        model = RunProgress()
        model.apply(plan)
        model.apply(start(0.0, 'contour', 'Contour'))
        for index in range(1, keptIterations + 11):
            model.apply(event('iteration', float(index), path = 'contour', name = 'evaluation', index = index,
                              metrics = {}))

        contour = model.stageList()[0]
        assert contour['iterationCount'] == keptIterations + 10
        assert [item['index'] for item in contour['iterations']] == list(range(11, keptIterations + 11))

    def testTheLastRunListsTheSubStagesStillToCome(self):

        first = RunProgress()
        for item in (plan, start(0.0, 'contour', 'Contour'), start(0.0, 'contour.diverging', 'Diverging section'),
                     end(40.0, 'contour.diverging', 40.0), start(40.0, 'contour.converging', 'Converging section'),
                     end(41.0, 'contour.converging', 1.0), end(41.0, 'contour', 41.0),
                     start(41.0, 'cooling', 'Cooling channels'), end(50.0, 'cooling', 9.0)):
            first.apply(item)

        second = RunProgress(first.durations(), previous = first.stageList())
        for item in (plan, start(0.0, 'contour', 'Contour'), start(0.0, 'contour.diverging', 'Diverging section')):
            second.apply(item)

        contour, cooling = second.stageList()
        assert contour['expected'] == 41.0 and cooling['expected'] == 9.0
        assert [(child['key'], child['state'], child['expected']) for child in contour['children']] == \
            [('diverging', 'running', 40.0), ('converging', 'pending', 1.0)]

    def testASubStageOrAnIterationIsATreeChange(self):

        model = RunProgress()
        model.apply(plan)
        model.apply(start(0.0, 'contour', 'Contour'))
        model.apply(start(0.0, 'contour.diverging', 'Diverging section'))
        model.apply(event('iteration', 1.0, path = 'contour.diverging', name = 'evaluation', index = 1, metrics = {}))

        # The same iteration number again leaves the bar and its label alone but adds to the list
        assert model.apply(event('iteration', 2.0, path = 'contour.diverging', name = 'evaluation', index = 1,
                                 metrics = {}))

    def testARealRunEndsFullAndNeverRunsBackward(self, reducedRuns):

        model = RunProgress()
        fractions = []
        for item in reducedRuns[0]:
            model.apply(item)
            assert model.ceiling >= model.fraction
            fractions.append(model.fraction)

        assert fractions == sorted(fractions)
        assert model.fraction == 1.0
        assert all(stage['state'] == 'done' for stage in model.stageList())
        assert set(model.durations()) == {'contour', 'cooling', 'performance'}

    def testARealRunsTreeClosesEverySubStage(self, reducedRuns):

        model = RunProgress()
        for item in reducedRuns[0]:
            model.apply(item)

        stages = {stage['key']: stage for stage in model.stageList()}
        assert 'sizing' in [child['key'] for child in stages['cooling']['children']]
        for stage in stages.values():
            assert all(child['state'] == 'done' and child['elapsed'] is not None for child in stage['children'])
            json.dumps(stage, allow_nan = False)
