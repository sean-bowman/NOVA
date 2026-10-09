# -- NOVA: Interactive Figure Builder Tests -- #

'''

The interactive figure builders against runs that have nothing for them to draw.

`figures.exportInteractiveFigures` tries every builder and skips one that raises, printing a note,
so a builder that mistakes empty data for data never fails a run; it prints an error into the log
of every run that lacks the feature instead. Each builder states what it returns when there is
nothing to draw, and that is what is checked here.

Author: Sean Bowman

'''

import types

import numpy as np

from NOVA.figures import channelMeshFigure

def testTheChannelViewIsSkippedWhenNoJacketWasBuilt():
    '''
    A run without cooling channels leaves the channel coordinates as an empty array rather than
    None, and the channel view has to return None for either.
    '''
    for channel in (None, np.array([]), np.zeros((0, 0))):
        assert channelMeshFigure(types.SimpleNamespace(xChannel = channel)) is None
