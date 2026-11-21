# -- NOVA: PyInstaller Build of the Standalone GUI -- #

'''

Freezes the GUI into a folder holding NOVA.exe and its supporting files (`_internal/`), so it runs
on a Windows machine with no Python. packaging/buildRelease.py runs it; on its own:

    python -m PyInstaller packaging/nova.spec --noconfirm

The bundle takes NOVA and novaGui from the checkout (`pathex`), whole: every submodule, so a module
imported by name at run time (runner.py's `NOVA.Nozzle`) is there, and every file under their
assets folders, so a new asset rides along without an edit here. novaGui's front end goes
as its build (`frontend/dist`) alone. The checkout files the GUI reads go at their checkout paths
(packaging/bundleData.py). The third-party packages come through PyInstaller's hooks, with
RocketCEA's data files (`thermo.lib`, `trans.lib`) and the `_version.py` its `__init__` reads as
text, which no hook collects, added here.

REFPROP itself is left out: its license does not allow shipping it. NIST's Python wrapper for it,
ctREFPROP (the `refprop` extra), goes in, so a machine with REFPROP installed uses it, and one
without falls back to CoolProp (NOVA.fluidProperties.fluidProps).

Author: Sean Bowman
Date:   11/21/2026

'''

import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = os.path.dirname(SPECPATH)
sys.path[:0] = [root, os.path.join(root, 'src'), SPECPATH]

from bundleData import checkoutData

datas = checkoutData(root)
datas += collect_data_files('NOVA', includes = ['assets/**'])
datas += collect_data_files('novaGui', includes = ['assets/**', 'frontend/dist/**'])
datas += collect_data_files('rocketcea')
# RocketCEA's __init__ reads its _version.py as text, so the source goes in beside the compiled module
datas += collect_data_files('rocketcea', include_py_files = True, includes = ['_version.py'])
# The report states the version it was made by (novaGui.report.novaVersion)
datas += copy_metadata('nova-nozzle')

analysis = Analysis(
    [os.path.join(SPECPATH, 'novaApp.py')],
    pathex = [root, os.path.join(root, 'src')],
    datas = datas,
    hiddenimports = collect_submodules('NOVA') + collect_submodules('novaGui'),
    # The Tk front end is retired; Matplotlib draws off screen (Agg)
    excludes = ['tkinter', 'pytest'],
    noarchive = False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries = True,
    name = 'NOVA',
    icon = os.path.join(root, 'novaGui', 'assets', 'nova.ico'),
    # A window, no console: the GUI writes its output to <temp>/NOVA/novaGui.log
    console = False,
    # UPX-packed executables draw more antivirus false positives than they save in size
    upx = False,
)
coll = COLLECT(exe, analysis.binaries, analysis.datas, name = 'NOVA', upx = False)
