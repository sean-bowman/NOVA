
# -- NOVA: Run Progress Events -- #

'''

Structured progress events for a NOVA run.

A front end that follows a run installs a reporter with `reporting(emit)` around
`generateNozzle`. The pipeline calls `plan`, `stage`, `track`, `iteration` and `profiles` at its
stage boundaries and inside its long loops, and each call hands one event dictionary to `emit`. With
no reporter installed every call does nothing, except `track`, which draws the tqdm bar a
terminal user expects.

The console output is unchanged by any of this. The printed lines stay the run's
human-readable log, and nothing reads them for progress.

----------------------------------------------------------------------
                            Events
----------------------------------------------------------------------

Every event is a plain dict of strings, numbers, booleans and None, so it crosses a process
boundary and serializes to JSON as it is. `t` is seconds since the reporter was installed, on a
monotonic clock. `path` is the dotted keys of the open stages, outermost first: in
'cooling.circuit.up', `up` is the up pass of the coolant circuit inside the cooling stage.

    {'type': 'plan', 't', 'stages': [{'key', 'label'}, ...]}
        The top-level stages the run will pass through, in order.

    {'type': 'stageStart', 't', 'path', 'key', 'label', 'depth'}
    {'type': 'stageEnd', 't', 'path', 'key', 'depth', 'ok', 'elapsed'}
        A stage opening and closing. `depth` is 0 for a top-level stage. `ok` is False when the
        stage raised; the exception still propagates. `elapsed` is in seconds.

    {'type': 'step', 't', 'path', 'label', 'done', 'total'}
        A loop inside the innermost open stage: `done` items of `total`, which is None when the
        loop's length is unknown. Sent for the first item, then at most once every
        `stepInterval` seconds, and always for the last item of a loop of known length.

    {'type': 'iteration', 't', 'path', 'name', 'index', 'metrics'}
        One finished iteration of an iterative solve inside the innermost open stage, numbered
        from 1. `name` says what an iteration is ('pass', 'evaluation'). `metrics` holds the
        scalars that show the solve converging, keyed by name, SI units.

    {'type': 'profiles', 't', 'path', 'name', 'index', 'metrics', 'profiles': [{...}, ...]}
        What one finished iteration settled on along the wall, sent after its iteration event:
        each profile a dict of strings, scalars and lists of floats, SI units, a non-finite value
        None. A multi-pass coolant circuit sends one per leg, each with its axial positions and
        its hot wall and coolant temperatures, so a front end can draw the circuit settling. A few
        kilobytes an iteration.

----------------------------------------------------------------------
                            Threads
----------------------------------------------------------------------

The reporter lives in a context variable, so it belongs to the thread that installed it. A
front end that runs the pipeline on a worker thread installs it on that thread, and another
thread's run neither sees nor disturbs it. Calls made from threads the pipeline starts itself
report nothing.

Sean Bowman [11/18/2026]

'''

# Standard library imports
import contextvars
import math
import time
from contextlib import contextmanager
from typing import Callable, Iterable, Optional

defaultStepInterval = 0.25  # [s] shortest time between two step events of one loop

_current = contextvars.ContextVar('novaProgressReporter', default = None)

class _Reporter:

    '''

    The installed listener and the stack of stages open on it.

    '''

    # -- Constructor -- #
    def __init__(self, emit: Callable[[dict], None], stepInterval: float):

        self.emit = emit
        self.stepInterval = float(stepInterval)  # [s]
        self.origin = time.perf_counter()        # [s] the clock reading t is measured from
        self.stack = []                          # [(key, label, startTime)], outermost first

    # -- Public Methods -- #
    def now(self) -> float:

        '''Seconds since the reporter was installed.'''

        return time.perf_counter() - self.origin

    def path(self) -> str:

        '''The dotted keys of the open stages.'''

        return '.'.join(key for key, _, _ in self.stack)

    def send(self, event: dict) -> None:

        '''

        Hand one event to the listener. A listener that fails loses that event and nothing
        else: a closed queue or a broken window must not stop a multi-minute solve.

        '''

        try:
            self.emit(event)
        except Exception:                                   # noqa: BLE001 -- see the docstring
            pass

    def track(self, iterable: Iterable, total: Optional[int], label: Optional[str]):

        '''Yield from `iterable`, sending step events as it goes.'''

        if total is None:
            try:
                total = len(iterable)
            except TypeError:
                total = None
        path = self.path()

        def step(done: int) -> None:
            self.send({'type': 'step', 't': self.now(), 'path': path, 'label': label,
                       'done': done, 'total': total})

        step(0)
        last = self.now()
        done = 0
        for item in iterable:
            yield item
            done += 1
            finished = total is not None and done >= total
            if finished or self.now() - last >= self.stepInterval:
                step(done)
                last = self.now()

@contextmanager
def reporting(emit: Callable[[dict], None], stepInterval: float = defaultStepInterval):

    '''

    Send this thread's progress events to `emit` for the length of the block.

    Parameters:
    -----------
    emit : callable
        Called with each event dict, on the thread that runs the pipeline. It should return
        quickly; a queue's put is the intended use.
    stepInterval : float
        Shortest time between two step events of one loop [s].

    Examples:
    ---------
    >>> events = []
    >>> with reporting(events.append):
    ...     nozzle.generateNozzle(configPath = 'myNozzle.json')

    '''

    token = _current.set(_Reporter(emit, stepInterval))
    try:
        yield
    finally:
        _current.reset(token)

def active() -> bool:

    '''Whether a reporter is installed on this thread.'''

    return _current.get() is not None

def plan(stages: list) -> None:

    '''

    Announce the top-level stages the run will pass through.

    Parameters:
    -----------
    stages : list
        (key, label) pairs, in the order the stages will run.

    '''

    reporter = _current.get()
    if reporter is None:
        return
    reporter.send({'type': 'plan', 't': reporter.now(),
                   'stages': [{'key': str(key), 'label': str(label)} for key, label in stages]})

@contextmanager
def stage(key: str, label: str, enabled: bool = True):

    '''

    Report the enclosed block as one stage of the run.

    Parameters:
    -----------
    key : str
        Short identifier, unique among the stages open beside it, without a dot.
    label : str
        What a person reads for it, in sentence case.
    enabled : bool
        False makes the block report nothing, for a block that runs whether or not the stage
        was planned.

    '''

    if '.' in key:
        raise ValueError(f'a stage key cannot contain a dot, got {key!r}')

    reporter = _current.get()
    if reporter is None or not enabled:
        yield
        return

    depth = len(reporter.stack)
    started = reporter.now()
    reporter.stack.append((key, label, started))
    path = reporter.path()
    reporter.send({'type': 'stageStart', 't': started, 'path': path, 'key': key, 'label': label,
                   'depth': depth})
    ok = False
    try:
        yield
        ok = True
    finally:
        reporter.stack.pop()
        ended = reporter.now()
        reporter.send({'type': 'stageEnd', 't': ended, 'path': path, 'key': key, 'depth': depth,
                       'ok': ok, 'elapsed': ended - started})

def track(iterable: Iterable, total: int = None, label: str = None, **tqdmOptions):

    '''

    Iterate with progress: step events under a reporter, a tqdm bar without one.

    Parameters:
    -----------
    iterable : iterable
        What the loop runs over.
    total : int
        Its length, when `len` cannot tell.
    label : str
        What the loop does, shown on the tqdm bar and carried by the step events.
    **tqdmOptions
        Passed to tqdm when no reporter is installed (`colour`, `disable`, ...).

    Returns:
    --------
    iterable : The items of `iterable`, in order.

    '''

    reporter = _current.get()
    if reporter is None:
        from tqdm import tqdm
        return tqdm(iterable, total = total, desc = label, **tqdmOptions)
    return reporter.track(iterable, total, label)

def iteration(index: int, metrics: dict = None, name: str = 'iteration') -> None:

    '''

    Report one finished iteration of an iterative solve inside the innermost open stage.

    Parameters:
    -----------
    index : int
        The iteration's number, from 1.
    metrics : dict
        Scalars that show the solve converging, keyed by name, SI units. Values that do not
        convert to a finite float are sent as None, which keeps the event valid JSON.
    name : str
        What one iteration is, for a person: 'pass', 'evaluation'.

    '''

    reporter = _current.get()
    if reporter is None:
        return

    reporter.send({'type': 'iteration', 't': reporter.now(), 'path': reporter.path(),
                   'name': name, 'index': int(index), 'metrics': _scalars(metrics)})

def profiles(index: int, entries: list, metrics: dict = None, name: str = 'iteration') -> None:

    '''

    Report what one finished iteration of an iterative solve settled on along the wall, inside the
    innermost open stage. Sent after the iteration's own `iteration` event.

    Parameters:
    -----------
    index : int
        The iteration's number, from 1.
    entries : list
        One dict per profile: strings, scalars, and arrays along the wall, SI units. Arrays are
        sent as lists of floats, with None for a non-finite value.
    metrics : dict
        The iteration's scalars, as its iteration event carries them.
    name : str
        What one iteration is, for a person: 'pass', 'evaluation'.

    '''

    reporter = _current.get()
    if reporter is None:
        return

    reporter.send({'type': 'profiles', 't': reporter.now(), 'path': reporter.path(), 'name': name,
                   'index': int(index), 'metrics': _scalars(metrics),
                   'profiles': [{str(key): _plain(value) for key, value in profile.items()}
                                for profile in entries]})

def _number(value) -> float | None:

    '''A value as a finite float, or None.'''

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return number if math.isfinite(number) else None

def _scalars(metrics: dict | None) -> dict:

    '''Metrics as finite floats by name, None for any that is not one.'''

    return {str(key): _number(value) for key, value in (metrics or {}).items()}

def _plain(value):

    '''A profile's value as JSON takes it: a string as it is, an array as a list of floats.'''

    if value is None or isinstance(value, (str, bool)):
        return value
    if hasattr(value, '__len__'):
        return [_number(item) for item in value]

    return _number(value)
