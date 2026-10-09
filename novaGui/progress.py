
# -- NOVA GUI Run Progress Tracking -- #

'''

Turns the pipeline's own console output into a progress fraction for the run bar.

NOVA prints a short banner as it enters each stage and drives tqdm bars inside the long ones.
Neither is a progress API, so this module matches those lines against an ordered stage table
and converts them to a 0-1 fraction. The table is built per run, because which stages exist
depends on whether cooling channels and volutes were requested.

Each stage carries the fraction it starts at and the fraction it may creep to while it runs.
The method-of-characteristics solve is silent for tens of seconds, so the run bar eases toward
the ceiling rather than sitting still; a matched marker snaps it to the true value.

Author: Sean Bowman
Date:   08/28/2026

'''

import re

class Stage:

    '''

    One recognizable step of the pipeline.

    '''

    def __init__(self, pattern: str, start: float, ceiling: float, label: str):

        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.start = start
        self.ceiling = ceiling
        self.label = label

# Fractions are cumulative over the whole run and were set from observed timings on the
# LOX/LH2 worked example: the MOC contour dominates a contour-only run, and the channel
# radius solve dominates a cooling run.

def _contourStages() -> list:

    return [
        Stage(r'run config written',                      0.02, 0.06, 'writing run config'),
        Stage(r'Generating a (truncated ideal|conical|thrust-optimized)|Optimizing the length fraction',
              0.08, 0.62, 'solving nozzle contour'),
        Stage(r'Generating Traditional Converging Section', 0.64, 0.68, 'converging section'),
        Stage(r'Generating Combustion Chamber',           0.70, 0.72, 'combustion chamber'),
        Stage(r'Truncating Nozzle Regen Section',         0.74, 0.78, 'regen truncation'),
    ]

def _coolingStages() -> list:

    return [
        Stage(r'Solving for channel radii',               0.80, 0.88, 'solving channel radii'),
        Stage(r'Scanning Nozzle Wall',                    0.88, 0.90, 'scanning nozzle wall'),
        Stage(r'Scanning Cross Sections',                 0.90, 0.92, 'scanning cross sections'),
        Stage(r'Generating Jacket Geometry',              0.92, 0.95, 'building jacket geometry'),
    ]

def _voluteStages() -> list:

    return [
        Stage(r'Generating Inlet Volute',                 0.95, 0.96, 'inlet volute'),
        Stage(r'Generating Outlet Volute',                0.96, 0.97, 'outlet volute'),
    ]

def _plumeStages(cooling: bool) -> list:

    # The march takes seconds against a jacket solve of minutes, but a large share of a
    # contour-only run, so its slice depends on which run it sits in
    start, ceiling = (0.970, 0.975) if cooling else (0.80, 0.95)

    return [
        Stage(r'Marching the exhaust plume',              start, ceiling, 'marching the plume'),
    ]

def _outputStages() -> list:

    return [
        Stage(r'Saving .* to \.html',                     0.975, 0.985, 'writing interactive views'),
        Stage(r'Exporting .* to \.stl|Pickling|Writing',  0.985, 0.99, 'exporting geometry'),
    ]

class StageTracker:

    '''

    Matches run output against the stage table and reports the resulting progress.

    '''

    def __init__(self, config: dict = None):

        config = config or {}
        cooling = config.get('makeCoolingChannels') in (True, 'on')
        volutes = (config.get('makeInletVolute') in (True, 'on')
                   or config.get('makeOutletVolute') in (True, 'on'))

        plume = config.get('plumeAmbientPressure') is not None and config.get('plumeFieldReach') is not None

        self.stages = _contourStages()
        if cooling:
            self.stages += _coolingStages()
            if volutes:
                self.stages += _voluteStages()
        if plume:
            self.stages += _plumeStages(cooling)
        self.stages += _outputStages()

        self._index = -1
        self.fraction = 0.0
        self.ceiling = 0.06
        self.label = 'starting'

    def match(self, line: str):

        '''

        Advance on a stage banner or a tqdm percentage.

        Returns (fraction, ceiling, label) when the run moved forward, otherwise None. Only
        forward matches count, so a stage banner printed twice inside a loop cannot rewind
        the bar.

        '''

        # tqdm renders as ' 47%|#####     | ...'; interpolate inside the current stage.
        percent = re.match(r'\s*(\d{1,3})%\|', line)
        if percent and self._index >= 0:
            stage = self.stages[self._index]
            span = stage.ceiling - stage.start
            candidate = stage.start + span * min(100, int(percent.group(1))) / 100.0
            if candidate > self.fraction:
                self.fraction = candidate
                return self.fraction, stage.ceiling, stage.label
            return None

        for index in range(self._index + 1, len(self.stages)):
            stage = self.stages[index]
            if stage.pattern.search(line):
                self._index = index
                self.fraction = stage.start
                self.ceiling = stage.ceiling
                self.label = stage.label
                return self.fraction, self.ceiling, self.label
        return None
