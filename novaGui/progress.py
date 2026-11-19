
# -- NOVA GUI Run Progress -- #

'''

Folds the progress events a NOVA run sends (`NOVA.progress`) into what a front end shows: a
0-1 fraction and a ceiling for the run bar, a short label naming where the run is, a longer
detail line, and the run's stages as a two-level tree with their state, times and iterations.

Both front ends use it. The legacy Tkinter window folds the runner's events on its main thread and
draws the bar; the web server folds the same events in its run session and sends the browser the
tree, which it draws as a stage stepper and a stage list.

Each top-level stage spans a share of the bar in proportion to the time it is expected to take:
its time on the last finished run of the same window or server process when there is one, else
the nominal time in `nominalStageTimes`. The bar sits at the start of the running stage and its
ceiling is the stage's end. A loop that reports its steps directly in a top-level stage moves the
bar inside that stage; elsewhere the front end eases the bar toward the ceiling between events,
as a stage like the contour solve reports only every few seconds.

The tree keeps the top-level stages and the stages one level inside them; anything deeper shows
only in the live detail of the stage it runs in. An iteration event is kept on the stage it was
sent in, so the coolant circuit's passes sit under the circuit and the contour solve's evaluations
under the diverging section. Given the last finished run's tree, a stage lists the sub-stages that
run took, as pending with their times, until this run reaches them.

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
keptIterations = 50         # the most iterations a stage keeps; older ones are counted, not kept

def _node(key: str, label: str) -> dict:

    '''A stage of the tree before it starts.'''

    return {'key': key, 'label': label, 'state': 'pending', 'started': None, 'elapsed': None,
            'iterationName': None, 'iterationCount': 0, 'iterations': [], 'children': []}

def _plural(name: str) -> str:

    return name + ('es' if name.endswith('s') else 's')

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
    previous : list
        The last finished run's stages, as its `stageList` returned them. A stage of this run
        lists the sub-stages that run took until it reaches them, and each sub-stage carries
        that run's time and iteration count as the expected ones.

    '''

    # -- Constructor -- #
    def __init__(self, history: dict = None, label: str = 'loading NOVA', previous: list = None):

        self.history = dict(history or {})
        self.previous = {stage['key']: stage for stage in (previous or [])}
        self.stages = []          # top-level stages, each with its sub-stages under 'children'
        self.t = 0.0              # [s] time of the latest event, from the run's own clock
        self.fraction = 0.0       # [-] where the bar sits
        self.ceiling = loadingCeiling
        self.label = label
        self.detail = ''
        self._nodes = {}          # the stages of the tree, by path
        self._open = []           # open stages, outermost first: dicts of path, label
        self._iterations = {}     # the latest iteration event, by the path it was sent in
        self._steps = {}          # the latest step event, by the path it was sent in

    # -- Private Helper Methods -- #
    def _stage(self, key: str, label: str) -> dict:

        '''The top-level stage of this key, appended when the plan did not name it.'''

        for stage in self.stages:
            if stage['key'] == key:
                return stage
        stage = _node(key, label)
        self.stages.append(stage)
        self._nodes[key] = stage
        return stage

    def _child(self, path: str, label: str) -> dict | None:

        '''The sub-stage at a two-key path, appended to its stage on first sight.'''

        parent = self._nodes.get(path.split('.')[0])
        if parent is None:
            return None
        key = path.split('.')[1]
        for child in parent['children']:
            if child['key'] == key:
                return child
        child = _node(key, label)
        parent['children'].append(child)
        self._nodes[path] = child
        return child

    def _inProgress(self, path: str) -> str:

        '''

        What a stage is doing inside itself, for a stage label: the deepest iteration in progress
        at or below `path` ('pass 4'), else the innermost loop's percentage ('45%').

        '''

        inside = [opened for opened in self._open
                  if opened['path'] == path or opened['path'].startswith(path + '.')]
        for opened in reversed(inside):
            iteration = self._iterations.get(opened['path'])
            if iteration is not None:
                return f'{iteration["name"]} {iteration["index"] + 1}'
        if inside:
            step = self._steps.get(inside[-1]['path'])
            if step is not None and step.get('total'):
                return f'{100 * step["done"] // step["total"]}%'
        return ''

    def _below(self, path: str) -> str:

        '''

        The open stages below `path`, each with its own iteration in progress, the innermost with
        its loop's percentage: 'Up pass 45%', or 'Coolant circuit (pass 3) / Up pass'.

        '''

        below = [opened for opened in self._open if opened['path'].startswith(path + '.')]
        parts = []
        for opened in below:
            part = opened['label']
            iteration = self._iterations.get(opened['path'])
            if iteration is not None:
                part += f' ({iteration["name"]} {iteration["index"] + 1})'
            parts.append(part)
        step = self._steps.get(below[-1]['path'] if below else path)
        if step is not None and step.get('total'):
            percent = f'{100 * step["done"] // step["total"]}%'
            if parts:
                parts[-1] += f' {percent}'
            else:
                parts.append(f'{step["label"]} {percent}' if step.get('label') else percent)
        return ' / '.join(parts)

    def _done(self, stage: dict) -> str:

        '''A finished stage's iteration count, from the first stage of its tree that iterated: '7 passes'.'''

        for node in [stage] + stage['children']:
            count = node['iterationCount']
            if count:
                return f'{count} {node["iterationName"] if count == 1 else _plural(node["iterationName"])}'
        return ''

    def _out(self, node: dict, path: str, before: dict | None) -> dict:

        '''A stage of the tree as a front end receives it, without its sub-stages.'''

        out = {key: node[key] for key in ('key', 'label', 'state', 'started', 'elapsed',
                                          'iterationName', 'iterationCount')}
        out['iterations'] = [dict(item) for item in node['iterations']]
        out['detail'] = self._below(path) if node['state'] == 'running' else ''
        out['expectedIterations'] = (before or {}).get('iterationCount') or None
        return out

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
        inside = self._inProgress(running['key'])
        self.label = running['label'] + (f', {inside}' if inside else '')

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
        bool : True when the bar, its label or detail, or the stage tree changed.

        '''

        before = (self.fraction, self.ceiling, self.label, self.detail)
        kind = event.get('type')
        self.t = max(self.t, float(event.get('t', self.t)))
        treeChanged = kind == 'plan'

        if kind == 'plan':
            for entry in event.get('stages', []):
                self._stage(entry['key'], entry['label'])

        elif kind == 'stageStart':
            if event['depth'] == 0:
                stage = self._stage(event['key'], event['label'])
                stage.update(state = 'running', started = event['t'], elapsed = None)
                self._open = []
            elif event['depth'] == 1:
                child = self._child(event['path'], event['label'])
                if child is not None:
                    child.update(state = 'running', started = event['t'], elapsed = None)
            self._open.append({'path': event['path'], 'label': event['label']})
            treeChanged = event['depth'] <= 1

        elif kind == 'stageEnd':
            self._open = [opened for opened in self._open
                          if opened['path'] != event['path'] and not opened['path'].startswith(event['path'] + '.')]
            self._forget(event['path'])
            if event['depth'] <= 1:
                node = (self._stage(event['key'], event['key']) if event['depth'] == 0
                        else self._child(event['path'], event['key']))
                if node is not None:
                    node.update(state = 'done' if event['ok'] else 'failed', elapsed = event['elapsed'])
                treeChanged = True
            if event['depth'] == 0 and not self._open:
                self.detail = ''

        elif kind == 'step':
            self._steps[event['path']] = event

        elif kind == 'iteration':
            self._iterations[event['path']] = event
            node = self._nodes.get(event['path'])
            if node is not None:
                node['iterationName'] = event['name']
                node['iterationCount'] = max(node['iterationCount'], int(event['index']))
                node['iterations'].append({'index': int(event['index']), 't': float(event['t']),
                                           'metrics': dict(event.get('metrics') or {})})
                del node['iterations'][:-keptIterations]
                treeChanged = True

        self._recompute()
        return treeChanged or (self.fraction, self.ceiling, self.label, self.detail) != before

    def summary(self) -> tuple:

        '''(fraction, ceiling, label) for a run bar.'''

        return self.fraction, self.ceiling, self.label

    def stageList(self) -> list:

        '''

        The stage tree as plain dicts, one per top-level stage, in run order.

        Every stage, top-level or sub-stage, carries: key, label, state ('pending', 'running',
        'done', 'failed'), started [s] on the run's clock, elapsed [s] once finished, the name and
        count of the iterations sent in it with the last `keptIterations` of them (index, t [s],
        metrics), a live `detail` of what runs below it while it runs ('Up pass 45%'), its
        expected time [s] and the expected iteration count from the last finished run, or None.

        A top-level stage adds its `weight` [s], the time its share of the bar stands for; `note`,
        what it is doing ('pass 4', '45%') or, finished, how many iterations it took
        ('7 passes'); `fraction`, how far a loop reported in the stage itself has gone, or None;
        and `children`, its sub-stages. Until it finishes, its sub-stages include those the last
        finished run took and this one has not reached, as pending.

        '''

        stages = []
        for stage in self.stages:
            before = self.previous.get(stage['key'])
            beforeChildren = {child['key']: child for child in (before or {}).get('children', [])}

            out = self._out(stage, stage['key'], before)
            out['expected'] = self.history.get(stage['key'])
            out['weight'] = self._weight(stage['key'])
            if stage['state'] == 'running':
                out['note'] = self._inProgress(stage['key'])
            else:
                out['note'] = self._done(stage) if stage['state'] in ('done', 'failed') else ''
            step = self._steps.get(stage['key'])
            out['fraction'] = (min(1.0, step['done'] / step['total'])
                               if stage['state'] == 'running' and step is not None and step.get('total') else None)

            children = []
            for child in stage['children']:
                earlier = beforeChildren.get(child['key'])
                entry = self._out(child, f'{stage["key"]}.{child["key"]}', earlier)
                entry['expected'] = (earlier or {}).get('elapsed')
                children.append(entry)
            if stage['state'] in ('pending', 'running'):
                reached = {child['key'] for child in stage['children']}
                for key, earlier in beforeChildren.items():
                    if key not in reached:
                        entry = self._out(_node(key, earlier['label']), f'{stage["key"]}.{key}', earlier)
                        entry.update(iterationName = earlier.get('iterationName'), expected = earlier.get('elapsed'))
                        children.append(entry)
            out['children'] = children
            stages.append(out)

        return stages

    def durations(self) -> dict:

        '''Top-level stage times of this run [s], by key, for the stages that finished.'''

        return {stage['key']: float(stage['elapsed']) for stage in self.stages
                if stage['state'] == 'done' and stage['elapsed'] is not None}
