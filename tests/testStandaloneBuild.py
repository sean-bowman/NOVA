# -- NOVA: The Standalone Build's Inputs -- #

'''

The standalone build (packaging/) freezes the GUI into NOVA.exe, and packaging/smokeTest.py runs the
shipped nozzle through the built exe, on a release tag and on a pull request that touches the build
(.github/workflows/release.yml). A build takes minutes and PyInstaller, so the suite holds the
build's inputs instead:

    the checkout files the bundle carries (packaging/bundleData.py) are every file the GUI reads
    from the checkout, each one there, each at its checkout path
    pyproject.toml, NOVA and novaGui declare one version, the one a release is tagged with
    a tag that names another version stops the build before PyInstaller starts

Author: Sean Bowman

'''

import json
import os
import re
import sys

import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for folder in (root, os.path.join(root, 'packaging')):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import buildRelease
import bundleData
import novaGui
from novaGui import configSchema, validationStatus

def _relative(path: str) -> str:

    return os.path.relpath(path, root).replace(os.sep, '/')

def testTheCheckoutFilesNameWhatTheGuiReads():

    '''The paths the GUI's modules open are the ones novaGui.checkoutFiles lists.'''

    assert set(novaGui.checkoutFiles) == {_relative(validationStatus.summaryPath),
                                          _relative(configSchema.shippedConfigPath)}

def testTheBundleCarriesEveryCheckoutFileTheGuiReadsAtItsCheckoutPath():

    with open(validationStatus.summaryPath, encoding = 'utf-8') as handle:
        summary = json.load(handle)
    records = {source['path'] for model in summary['models'].values() for source in model['sources']}
    carried = {}
    for source, folder in bundleData.checkoutData(root):
        assert os.path.isfile(source), source
        carried[f'{folder}/{os.path.basename(source)}' if folder else os.path.basename(source)] = source
    assert set(carried) == set(novaGui.checkoutFiles) | records
    for path, source in carried.items():
        assert os.path.normcase(source) == os.path.normcase(os.path.join(root, *path.split('/')))

def testPyprojectNovaAndNovaGuiDeclareOneVersion():

    with open(os.path.join(root, 'src', 'NOVA', '__init__.py'), encoding = 'utf-8') as handle:
        novaVersion = re.search(r"^__version__\s*=\s*'([^']+)'", handle.read(), re.MULTILINE).group(1)
    assert buildRelease.projectVersion() == novaVersion == novaGui.__version__

def testATagNamingAnotherVersionStopsTheBuildBeforeItStarts(monkeypatch):

    def started(command):
        raise AssertionError(f'the build started: {command}')

    monkeypatch.setattr(buildRelease, '_run', started)
    with pytest.raises(SystemExit) as stopped:
        buildRelease.main(['--tag', 'v0.0.0'])
    assert 'does not match' in str(stopped.value)
