
# -- NOVA GUI Tabs -- #

'''

The four notebook tabs: Design (ConfigTab), View, Analyze (AnalysisTab) and
Export. Each is a ttk.Frame subclass taking (master, app) and exposing
refresh(runResult); the Design tab additionally exposes getConfig(),
setConfig() and validate().

Author: Sean Bowman
Date:   08/28/2026

'''

from .configTab import ConfigTab
from .viewTab import ViewTab
from .analysisTab import AnalysisTab
from .exportTab import ExportTab

__all__ = ['ConfigTab', 'ViewTab', 'AnalysisTab', 'ExportTab']
