# -- NOVA GUI: Update Check -- #

'''

Whether a newer release of NOVA is out, asked of GitHub when the user presses Check for updates in
the About dialog. The app makes no request of its own otherwise.

GitHub's latest release (`GET /repos/sean-bowman/NOVA/releases/latest`, which passes over drafts
and pre-releases) carries its tag, `v<version>` (docs/releasing.md), and when it was published. The
running version is `novaGui.__version__`. The answer's status is one of:

    newer        a later release is out
    current      the running version is the latest release
    ahead        the running version is later than the latest release: a checkout past the last tag
    none         no release is published
    unreachable  no answer from GitHub: no network, a proxy in the way, a timeout, or a TLS failure
    refused      GitHub answered with an error, such as its limit of 60 requests an hour from one
                 address
    unreadable   the answer carries no version to compare

The release page's link is built from the tag, once the tag reads as a version, so the page links
to nothing GitHub's answer names. The request carries nothing about the user or their runs: the
User-Agent GitHub asks for names NOVA and its version.

Installing stays manual. The standalone build is unzipped in place of the old folder; its runs,
settings and exports live outside that folder (docs/releasing.md), so they are kept. A checkout
pulls.

Author: Sean Bowman
Date:   11/22/2026

'''

# Standard library imports
import json
import re
import urllib.error
import urllib.request
from typing import Callable

# Local imports
from . import __version__, runningBuild

releaseApi = 'https://api.github.com/repos/sean-bowman/NOVA/releases/latest'
releasePages = 'https://github.com/sean-bowman/NOVA/releases/tag/'
requestTimeoutSec = 10.0                            # [s]

def parseVersion(text: str) -> tuple | None:

    '''

    A version as numbers to compare, from '0.1.0' or a tag 'v0.1.0'; None for anything else, a
    pre-release suffix included, since releases are tagged with the plain version.

    '''

    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', text.strip()) if isinstance(text, str) else None
    return tuple(int(part) for part in match.groups()) if match else None

def fetchLatestRelease() -> dict:

    '''

    GitHub's latest release of NOVA, as its API returns it.

    Raises:
    -------
    urllib.error.HTTPError : GitHub answered with an error; 404 when no release is published
    urllib.error.URLError, OSError : no answer
    ValueError : the answer is not JSON

    '''

    request = urllib.request.Request(releaseApi, headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': f'NOVA/{__version__}',
    })
    with urllib.request.urlopen(request, timeout = requestTimeoutSec) as response:
        return json.loads(response.read().decode('utf-8'))

def checkForUpdate(fetch: Callable[[], dict] | None = None) -> dict:

    '''

    Ask for the latest release and compare it with the running version.

    Parameters:
    -----------
    fetch : callable, optional
        Returns the latest release as GitHub's API does; fetchLatestRelease when not given

    Returns:
    --------
    dict : 'status' (above), 'running' and 'build' (novaGui.runningBuild), 'latest' (the latest
           release's version, or ''), 'url' (its page, or ''), 'published' (its date, YYYY-MM-DD, or
           ''), 'detail' (why the answer is unreachable, refused or unreadable, or '')

    '''

    running = runningBuild()
    answer = {'status': '', 'running': running['version'], 'build': running['build'], 'latest': '', 'url': '',
              'published': '', 'detail': ''}
    try:
        release = (fetch or fetchLatestRelease)()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {**answer, 'status': 'none'}
        detail = f'GitHub answered {error.code} {error.reason}'
        if error.headers is not None and error.headers.get('X-RateLimit-Remaining') == '0':
            detail = 'GitHub allows 60 requests an hour from one address, and they are spent; try again later'
        return {**answer, 'status': 'refused', 'detail': detail}
    except (urllib.error.URLError, OSError) as error:
        return {**answer, 'status': 'unreachable', 'detail': str(getattr(error, 'reason', error))}
    except ValueError:
        return {**answer, 'status': 'unreadable', 'detail': 'the answer is not JSON'}

    tag = release.get('tag_name') if isinstance(release, dict) else None
    latest = parseVersion(tag)
    if latest is None:
        return {**answer, 'status': 'unreadable', 'detail': f'the latest release is tagged {tag!r}'}
    published = release.get('published_at')
    published = published[:10] if isinstance(published, str) and re.match(r'\d{4}-\d{2}-\d{2}', published) else ''
    current = parseVersion(running['version'])
    status = 'newer' if latest > current else 'ahead' if latest < current else 'current'
    return {**answer, 'status': status, 'latest': '.'.join(str(part) for part in latest),
            'url': releasePages + tag.strip(), 'published': published}
