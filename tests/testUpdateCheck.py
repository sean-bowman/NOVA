# -- NOVA: Update Check -- #

'''

The About dialog's Check for updates (novaGui.updates): GitHub's latest release against the running
version. Every test stands in for GitHub, so none leaves the machine.

    a later, equal or earlier release reads as newer, current or ahead
    the release page's link is built from the tag, never taken from the answer
    no release, an error from GitHub, its spent hourly limit, no answer, and an answer without a
    version each say so
    the request goes to GitHub's latest-release route naming NOVA and its version, and nothing else
    the app asks GitHub nothing until the update route is called

Author: Sean Bowman

'''

import email.message
import json
import os
import sys
import urllib.error
import urllib.request

import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

import novaGui
from novaGui import updates

def _release(tag, published = '2026-12-01T18:04:11Z', **extra) -> dict:

    return {'tag_name': tag, 'published_at': published, **extra}

def _answered(release):

    return lambda: release

def _failed(error):

    def fetch():
        raise error
    return fetch

def _httpError(code: int, reason: str, **headers) -> urllib.error.HTTPError:

    message = email.message.Message()
    for name, value in headers.items():
        message[name.replace('_', '-')] = value
    return urllib.error.HTTPError(updates.releaseApi, code, reason, message, None)

def _later(steps: tuple) -> str:

    return '.'.join(str(part + step) for part, step in zip(updates.parseVersion(novaGui.__version__), steps))

@pytest.mark.parametrize('text, parsed', [
    ('0.1.0', (0, 1, 0)), ('v0.1.0', (0, 1, 0)), (' v12.0.3 ', (12, 0, 3)),
    ('v0.2.0-rc1', None), ('0.2', None), ('nightly', None), ('', None), (None, None),
])
def testAVersionReadsOnlyAsThreeNumbers(text, parsed):

    assert updates.parseVersion(text) == parsed

def testTheRunningVersionReadsAsAVersion():

    assert updates.parseVersion(novaGui.__version__) is not None

def testALaterReleaseLinksToItsPage():

    latest = _later((0, 1, 0))
    answer = updates.checkForUpdate(_answered(_release(f'v{latest}')))
    assert answer['status'] == 'newer'
    assert (answer['running'], answer['latest'], answer['published']) == (novaGui.__version__, latest, '2026-12-01')
    assert answer['url'] == f'https://github.com/sean-bowman/NOVA/releases/tag/v{latest}'
    assert answer['build'] == novaGui.runningBuild()['build']

def testTheLinkIsBuiltFromTheTagNotTakenFromTheAnswer():

    release = _release(f'v{_later((1, 0, 0))}', html_url = 'https://example.com/nova.exe')
    assert updates.checkForUpdate(_answered(release))['url'].startswith(updates.releasePages)

def testTheRunningReleaseIsCurrent():

    answer = updates.checkForUpdate(_answered(_release(f'v{novaGui.__version__}')))
    assert (answer['status'], answer['latest']) == ('current', novaGui.__version__)

def testAnEarlierReleaseLeavesTheRunningVersionAhead():

    answer = updates.checkForUpdate(_answered(_release('v0.0.0')))
    assert (answer['status'], answer['latest']) == ('ahead', '0.0.0')

def testAReleaseWithoutADateStillCompares():

    answer = updates.checkForUpdate(_answered(_release(f'v{_later((0, 0, 1))}', published = None)))
    assert (answer['status'], answer['published']) == ('newer', '')

def testNoPublishedReleaseSaysSo():

    answer = updates.checkForUpdate(_failed(_httpError(404, 'Not Found')))
    assert (answer['status'], answer['latest'], answer['url']) == ('none', '', '')

def testASpentHourlyLimitSaysToTryLater():

    answer = updates.checkForUpdate(_failed(_httpError(403, 'Forbidden', X_RateLimit_Remaining = '0')))
    assert answer['status'] == 'refused'
    assert '60 requests an hour' in answer['detail'] and 'try again later' in answer['detail']

def testAnotherErrorFromGitHubIsNamed():

    answer = updates.checkForUpdate(_failed(_httpError(503, 'Service Unavailable')))
    assert (answer['status'], answer['detail']) == ('refused', 'GitHub answered 503 Service Unavailable')

@pytest.mark.parametrize('error, detail', [
    (urllib.error.URLError('getaddrinfo failed'), 'getaddrinfo failed'),
    (TimeoutError('timed out'), 'timed out'),
])
def testNoAnswerSaysWhy(error, detail):

    answer = updates.checkForUpdate(_failed(error))
    assert (answer['status'], answer['detail']) == ('unreachable', detail)

@pytest.mark.parametrize('fetch', [
    _answered(_release('nightly')),
    _answered(_release('v0.2.0-rc1')),
    _answered(['not', 'a', 'release']),
    _failed(json.JSONDecodeError('Expecting value', '<html>', 0)),
])
def testAnAnswerWithoutAVersionOffersNothing(fetch):

    answer = updates.checkForUpdate(fetch)
    assert answer['status'] == 'unreadable' and answer['detail']
    assert (answer['latest'], answer['url']) == ('', '')

def testTheRequestNamesNovaAndItsVersionAlone(monkeypatch):

    sent = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(_release('v0.1.0')).encode('utf-8')

    def urlopen(request, timeout):
        sent.append((request, timeout))
        return Response()

    monkeypatch.setattr(urllib.request, 'urlopen', urlopen)
    assert updates.fetchLatestRelease()['tag_name'] == 'v0.1.0'
    request, timeout = sent[0]
    assert (request.full_url, request.get_method(), timeout) == (updates.releaseApi, 'GET', updates.requestTimeoutSec)
    assert dict(request.header_items()) == {'Accept': 'application/vnd.github+json', 'X-github-api-version': '2022-11-28',
                                            'User-agent': f'NOVA/{novaGui.__version__}'}
    assert request.data is None

def testTheAppAsksGitHubOnlyThroughTheUpdateRoute(monkeypatch):

    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient

    from novaGui.server import createApp
    from novaGui.session import RunSession

    asked = []
    monkeypatch.setattr(updates, 'fetchLatestRelease', lambda: asked.append(1) or _release(f'v{_later((0, 1, 0))}'))
    session = RunSession()
    try:
        with TestClient(createApp(session = session, warm = False)) as client:
            for path in ('/api/health', '/api/schema', '/api/runs', '/api/sweeps'):
                assert client.get(path).status_code == 200
            assert asked == []
            answer = client.get('/api/updates').json()
    finally:
        session.shutdown()
    assert asked == [1]
    assert answer['status'] == 'newer'
