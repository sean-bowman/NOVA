# -- NOVA GUI Tabs -- #

'''

The five notebook tabs. Each is a ttk.Frame subclass taking (master, app) and
exposing refresh(runResult); the config tab additionally exposes getConfig(),
setConfig() and validate().

Author: Sean Bowman
Date:   08/28/2026

'''

from .configTab import ConfigTab
from .geometry2dTab import Geometry2DTab
from .geometry3dTab import Geometry3DTab
from .analysisTab import AnalysisTab
from .exportTab import ExportTab

__all__ = ['ConfigTab', 'Geometry2DTab', 'Geometry3DTab', 'AnalysisTab', 'ExportTab']
