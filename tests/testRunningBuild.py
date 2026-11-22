# -- NOVA: What Runs -- #

'''

The GUI names what runs (novaGui.runningBuild) in the health route, the About dialog and the first
line of the launcher's log: NOVA's version, the standalone build or the checkout's revision, and
the Python and system under it.

    the health route carries the version, the build and the label
    the launcher's first line is the label
    the standalone build is named as such and asks git nothing
    a checkout's revision reads as git describe gives it, uncommitted changes spelled out
    a folder without history, or a system without git, has no revision

packaging/smokeTest.py checks the standalone build's health route and log against the built exe.

Author: Sean Bowman

'''

import os
import shutil
import subprocess
import sys

import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

import novaGui
from novaGui import __main__ as launcher

@pytest.fixture
def freshBuild():

    '''runningBuild reads once per process; clear it around a test that changes what it reads.'''

    novaGui.runningBuild.cache_clear()
    yield
    novaGui.runningBuild.cache_clear()

def testTheHealthRouteNamesWhatRuns():

    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient

    from novaGui.server import createApp
    from novaGui.session import RunSession

    session = RunSession()
    try:
        with TestClient(createApp(session = session, warm = False)) as client:
            health = client.get('/api/health').json()
    finally:
        session.shutdown()
    assert health['ok'] is True
    assert health['version'] == novaGui.__version__
    assert health['build'] == 'checkout'
    assert health['label'] == novaGui.runningBuild()['label']
    assert health['label'].startswith(f'NOVA {novaGui.__version__}, checkout')

def testACheckoutWithHistoryNamesItsCommit():

    if shutil.which('git') is None or not os.path.exists(os.path.join(root, '.git')):
        pytest.skip('git or the checkout\'s history is missing')
    commit = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'], capture_output = True, text = True,
                            check = True).stdout.strip()
    tagged = subprocess.run(['git', '-C', root, 'tag', '--points-at', 'HEAD'], capture_output = True, text = True,
                            check = True).stdout.split()
    revision = novaGui.checkoutRevision().removesuffix('-dirty')
    # git describe gives the tag on a tagged commit, and the commit's abbreviation everywhere else
    assert revision in tagged or commit.startswith(revision.rsplit('-g', 1)[-1])

def testTheLaunchersFirstLineNamesWhatRuns(monkeypatch, capsys):

    # A checkout missing its files stops the launcher before any server starts
    monkeypatch.setattr(novaGui, 'missingCheckoutFiles', lambda: ['docs/validationStatus.json'])
    assert launcher.main([]) == 1
    assert capsys.readouterr().out.splitlines()[0] == novaGui.runningBuild()['label']

def testTheStandaloneBuildIsNamedAsSuch(monkeypatch, freshBuild):

    def askedGit():
        raise AssertionError('the standalone build asked git for a revision')

    monkeypatch.setattr(sys, 'frozen', True, raising = False)
    monkeypatch.setattr(novaGui, 'checkoutRevision', askedGit)
    running = novaGui.runningBuild()
    assert (running['build'], running['revision']) == ('standalone', '')
    assert running['label'].startswith(f'NOVA {novaGui.__version__}, standalone build, Python ')

@pytest.mark.parametrize('revision, where', [
    ('89d703f', 'checkout 89d703f,'),
    ('89d703f-dirty', 'checkout 89d703f with uncommitted changes,'),
    ('v0.1.0-3-g89d703f-dirty', 'checkout v0.1.0-3-g89d703f with uncommitted changes,'),
    ('v0.1.0', 'checkout v0.1.0,'),
    ('', 'checkout,'),
])
def testARevisionReadsAsGitDescribeGivesIt(revision, where):

    assert novaGui.buildLabel('0.1.0', 'checkout', revision).startswith(f'NOVA 0.1.0, {where} Python ')

def testAFolderWithoutHistoryHasNoRevision(monkeypatch, tmp_path):

    monkeypatch.setattr(novaGui, 'repositoryRoot', str(tmp_path))
    assert novaGui.checkoutRevision() == ''

def testASystemWithoutGitHasNoRevision(monkeypatch):

    def noGit(*args, **kwargs):
        raise FileNotFoundError('git')

    monkeypatch.setattr(subprocess, 'run', noGit)
    assert novaGui.checkoutRevision() == ''
