# -- NOVA: The Installed Package -- #

'''

What an install of the repository carries. `pip install -e .[web]` maps NOVA (under src/) and the
GUI package novaGui (at the repository root) into the environment, and writes the `nova-gui`
launcher from the gui-scripts entry point. These tests build the wheel from a copy of the files
the build reads, so nothing is written into the checkout, and hold what it holds: both packages
with their data, the GUI's icons and built front end among it, the launcher's entry point, and
nothing else of the repository (tests, validation, the front end's sources).

The GUI reads files of the checkout that no install carries, so the launcher stops with a message
naming them when the package is not in a checkout; the last tests hold that check.

Author: Sean Bowman

'''

import configparser
import os
import shutil
import subprocess
import sys
import zipfile

import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

import novaGui
import novaGui.__main__ as launcher

# What the build reads: the project file, the readme it names, the license and both packages
buildInputs = ('pyproject.toml', 'README.md', 'LICENSE', 'src', 'novaGui')
skipped = shutil.ignore_patterns('__pycache__', '*.egg-info', 'node_modules')

def _filesUnder(folder: str) -> list:

    '''Every file under `folder` of the repository, as a path relative to the root with / separators.'''

    found = []
    for path, folders, names in os.walk(os.path.join(root, folder)):
        folders[:] = [name for name in folders if name != '__pycache__']
        found += [os.path.relpath(os.path.join(path, name), root).replace(os.sep, '/') for name in names]
    return found

@pytest.fixture(scope = 'module')
def wheel(tmp_path_factory) -> zipfile.ZipFile:

    '''The wheel pip builds from a copy of the build's inputs, without build isolation or dependencies.'''

    pytest.importorskip('setuptools')
    pytest.importorskip('wheel')
    project = tmp_path_factory.mktemp('project')
    for name in buildInputs:
        source = os.path.join(root, name)
        if os.path.isdir(source):
            shutil.copytree(source, project / name, ignore = skipped)
        else:
            shutil.copy2(source, project / name)
    out = tmp_path_factory.mktemp('wheel')
    result = subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
                             '--no-cache-dir', '--quiet', '-w', str(out), str(project)],
                            capture_output = True, text = True)
    assert result.returncode == 0, result.stderr
    built = [name for name in os.listdir(out) if name.endswith('.whl')]
    assert len(built) == 1, built
    with zipfile.ZipFile(out / built[0]) as archive:
        yield archive

def testTheWheelHoldsBothPackagesAndNothingElseOfTheRepository(wheel):

    tops = {name.split('/')[0] for name in wheel.namelist()}
    infos = {top for top in tops if top.endswith('.dist-info')}
    assert len(infos) == 1 and tops - infos == {'NOVA', 'novaGui'}, sorted(tops)

def testTheWheelHoldsTheGuiModulesIconsAndBuiltFrontEnd(wheel):

    names = set(wheel.namelist())
    modules = [path for path in _filesUnder('novaGui') if path.count('/') == 1 and path.endswith('.py')]
    assert 'novaGui/__main__.py' in modules
    expected = modules + _filesUnder('novaGui/assets') + _filesUnder('novaGui/frontend/dist')
    assert sorted(set(expected) - names) == []

    # The front end goes as its build alone: its sources and npm files stay in the checkout
    frontEnd = sorted(name for name in names if name.startswith('novaGui/frontend/'))
    assert all(name.startswith('novaGui/frontend/dist/') for name in frontEnd), frontEnd

def testTheWheelHoldsTheShippedConfiguration(wheel):

    assert 'NOVA/assets/NOVANozzle.json' in wheel.namelist()

def testTheWheelDeclaresTheNovaGuiLauncher(wheel):

    entryPoints = next(name for name in wheel.namelist() if name.endswith('.dist-info/entry_points.txt'))
    parser = configparser.ConfigParser()
    parser.read_string(wheel.read(entryPoints).decode('utf-8'))
    assert dict(parser['gui_scripts']) == {'nova-gui': 'novaGui.__main__:main'}

def testTheCheckoutHoldsEveryFileTheGuiReads():

    assert novaGui.missingCheckoutFiles() == []

def testTheLauncherStopsOutsideACheckoutNamingWhatIsMissing(monkeypatch, capsys):

    monkeypatch.setattr(novaGui, 'checkoutFiles', ('docs/validationStatus.json', 'docs/noSuchSummary.json'))
    assert launcher.main([]) == 1
    message = capsys.readouterr().err
    assert 'pip install -e .[web]' in message and 'docs/noSuchSummary.json' in message
    assert 'docs/validationStatus.json' not in message
