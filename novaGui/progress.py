
# -- NOVA GUI Run Progress -- #

'''

Folds the progress events a NOVA run sends (`NOVA.progress`) into what a front end shows: a
0-1 fraction and a ceiling for the run bar, a short label naming where the run is, a longer
detail line, and the run's top-level stages with their state and times.

Both front ends use it. The Tkinter window folds the runner's events on its main thread; the
web server folds the same events in its run session and sends the result to the browser.

Each top-level stage spans a share of the bar in proportion to the time it is expected to take:
its time on the last finished run of the same window or server process when there is one, else
the nominal time in `nominalStageTimes`. The bar sits at the start of the running stage and its
ceiling is the stage's end. A loop that reports its steps directly in a top-level stage moves the
bar inside that stage; elsewhere the front end eases the bar toward the ceiling between events,
as a stage like the contour solve reports only every few seconds.

The module imports nothing from NOVA, so the window opens without the scientific stack.

Author: Sean Bowman
Date:   08/28/2026

'''

# Nominal top-level stage times [s]: the median over the shipped nozzle and the five example
# configurations, each run with every output written, on one desktop (Ryzen 7 2700X, 11/18/2026).
# They set the shares of a window's first run only; later runs use the last run's own times. The
# spread behind a median can be wide: a multi-pass circuit's cooling stage ran 255 to 345 s against
# 20 to 34 s single pass, and the methalox booster's extension 729 s against a 9 s median.
nominalStageTimes = {
    'contour':     55.0,
    'cooling':     30.0,
    'volutes':     0.06,
    'extension':   9.4,
    'performance': 0.1,
    'plume':       6.2,
    'outputs':     2.2,
}
defaultStageTime = 5.0      # [s] a stage the table does not name
shortestShare = 0.3         # [s] the least time a stage is weighted with, so each shows on the bar
loadingCeiling = 0.02       # [-] the share of the bar the run spends before its plan arrives

class RunProgress:

    '''

    The progress of one run, folded from its events.

    Parameters:
    -----------
    history : dict
        Top-level stage times of the last finished run [s], by stage key. Stages it names are
        weighted by those times instead of the nominal ones.
    label : str
        What the bar says until the first stage starts.

    '''

    # -- Constructor -- #
    def __init__(self, history: dict = None, label: str = 'loading NOVA'):

        self.history = dict(history or {})
        self.stages = []          # top-level stages: dicts of key, label, state, started, elapsed
        self.t = 0.0              # [s] time of the latest event, from the run's own clock
        self.fraction = 0.0       # [-] where the bar sits
        self.ceiling = loadingCeiling
        self.label = label
        self.detail = ''
        self._open = []           # open stages, outermost first: dicts of path, label
        self._iterations = {}     # the latest iteration event, by the path it was sent in
        self._steps = {}          # the latest step event, by the path it was sent in

    # -- Private Helper Methods -- #
    def _stage(self, key: str, label: str) -> dict:

        '''The top-level stage of this key, appended when the plan did not name it.'''

        for stage in self.stages:
            if stage['key'] == key:
                return stage
        stage = {'key': key, 'label': label, 'state': 'pending', 'started': None, 'elapsed': None}
        self.stages.append(stage)
        return stage

    def _forget(self, path: str) -> None:

        '''Drop the iterations and steps sent inside a stage that has closed.'''

        prefix = path + '.'
        for store in (self._iterations, self._steps):
            for key in [key for key in store if key == path or key.startswith(prefix)]:
                del store[key]

    def _weight(self, key: str) -> float:

        seconds = self.history.get(key, nominalStageTimes.get(key, defaultStageTime))
        return max(float(seconds), shortestShare)

    def _recompute(self) -> None:

        if not self.stages:
            return

        weights = [self._weight(stage['key']) for stage in self.stages]
        total = sum(weights)
        span = 1.0 - loadingCeiling

        start = loadingCeiling
        fraction, ceiling = None, None
        for stage, weight in zip(self.stages, weights):
            share = span * weight / total
            if stage['state'] == 'running':
                inner = 0.0
                step = self._steps.get(stage['key'])
                if step is not None and step.get('total'):
                    inner = min(1.0, step['done'] / step['total'])
                fraction, ceiling = start + share * inner, start + share
                break
            if stage['state'] == 'pending':
                fraction = ceiling = start
                break
            start += share
        if fraction is None:
            fraction = ceiling = 1.0

        # The bar never runs backward: a stage that finishes sooner than its share closes the gap
        self.fraction = max(self.fraction, min(1.0, fraction))
        self.ceiling = max(self.fraction, min(1.0, ceiling))

        running = next((stage for stage in self.stages if stage['state'] == 'running'), None)
        if running is None:
            return

        # Short label: the top-level stage, and the deepest iteration or loop inside it
        suffix = ''
        for opened in reversed(self._open):
            iteration = self._iterations.get(opened['path'])
            if iteration is not None:
                suffix = f', {iteration["name"]} {iteration["index"] + 1}'
                break
        if not suffix and self._open:
            step = self._steps.get(self._open[-1]['path'])
            if step is not None and step.get('total'):
                suffix = f', {100 * step["done"] // step["total"]}%'
        self.label = running['label'] + suffix

        # Detail: every open stage, each with its own iteration, the innermost with its loop
        parts = []
        for position, opened in enumerate(self._open):
            part = opened['label']
            iteration = self._iterations.get(opened['path'])
            if iteration is not None:
                part += f' ({iteration["name"]} {iteration["index"] + 1})'
            step = self._steps.get(opened['path'])
            if position == len(self._open) - 1 and step is not None and step.get('total'):
                part += f' {100 * step["done"] // step["total"]}%'
            parts.append(part)
        self.detail = ' / '.join(parts)

    # -- Public Methods -- #
    def apply(self, event: dict) -> bool:

        '''

        Fold one event in.

        Returns:
        --------
        bool : True when the fraction, ceiling, label or detail changed.

        '''

        before = (self.fraction, self.ceiling, self.label, self.detail)
        kind = event.get('type')
        self.t = max(self.t, float(event.get('t', self.t)))

        if kind == 'plan':
            for entry in event.get('stages', []):
                self._stage(entry['key'], entry['label'])

        elif kind == 'stageStart':
            if event['depth'] == 0:
                stage = self._stage(event['key'], event['label'])
                stage.update(state = 'running', started = event['t'], elapsed = None)
                self._open = []
            self._open.append({'path': event['path'], 'label': event['label']})

        elif kind == 'stageEnd':
            self._open = [opened for opened in self._open
                          if opened['path'] != event['path'] and not opened['path'].startswith(event['path'] + '.')]
            self._forget(event['path'])
            if event['depth'] == 0:
                stage = self._stage(event['key'], event['key'])
                stage.update(state = 'done' if event['ok'] else 'failed', elapsed = event['elapsed'])
                if not self._open:
                    self.detail = ''

        elif kind == 'step':
            self._steps[event['path']] = event

        elif kind == 'iteration':
            self._iterations[event['path']] = event

        self._recompute()
        return (self.fraction, self.ceiling, self.label, self.detail) != before

    def summary(self) -> tuple:

        '''(fraction, ceiling, label) for a run bar.'''

        return self.fraction, self.ceiling, self.label

    def stageList(self) -> list:

        '''

        The top-level stages as plain dicts: key, label, state ('pending', 'running', 'done',
        'failed'), started [s], elapsed [s] once finished, and expected [s] from the last
        finished run, or None.

        '''

        return [dict(stage, expected = self.history.get(stage['key'])) for stage in self.stages]

    def durations(self) -> dict:

        '''Top-level stage times of this run [s], by key, for the stages that finished.'''

        return {stage['key']: float(stage['elapsed']) for stage in self.stages
                if stage['state'] == 'done' and stage['elapsed'] is not None}
