# -- NOVA: The Built Front End -- #

'''

The repository carries the GUI's built front end (novaGui/frontend/dist), so a checkout runs the
GUI without Node. These tests hold that build to its sources.

The build stamps `dist/buildStamp.json` with a hash of every file it reads (vite.config.ts says
which, and how the hash is taken). A front-end source changed without the build it makes no longer
matches the stamp, and the stamp test fails until `npm run build` in novaGui/frontend is run and
dist/ committed with the change. The build is also held whole: every asset index.html loads is
there, and every asset there is loaded by something, so a file left from an earlier build cannot
ride along.

Author: Sean Bowman

'''

import hashlib
import json
import os
import re

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend = os.path.join(root, 'novaGui', 'frontend')
dist = os.path.join(frontend, 'dist')

def sourceHash(inputs: list) -> str:

    '''

    The hash vite.config.ts stamps: SHA-256 over each source file's path relative to the front end
    folder, in sorted order, each followed by a newline, the file's bytes with CRLF read as LF, and
    a newline.

    '''

    files = []
    for name in inputs:
        path = os.path.join(frontend, name)
        if os.path.isdir(path):
            for folder, _, names in os.walk(path):
                files += [os.path.relpath(os.path.join(folder, entry), frontend).replace(os.sep, '/') for entry in names]
        else:
            files.append(name)
    digest = hashlib.sha256()
    for name in sorted(files):
        with open(os.path.join(frontend, name), 'rb') as handle:
            content = handle.read().replace(b'\r\n', b'\n')
        digest.update(name.encode('utf-8') + b'\n' + content + b'\n')

    return digest.hexdigest()

def _stamp() -> dict:

    with open(os.path.join(dist, 'buildStamp.json'), encoding = 'utf-8') as handle:
        return json.load(handle)

def testTheBuildIsOfTheSourcesAsTheyStand():

    stamp = _stamp()
    assert sourceHash(stamp['inputs']) == stamp['sources'], (
        'novaGui/frontend/dist is older than its sources: run `npm run build` in novaGui/frontend '
        'and commit dist/ with the change')

def testEveryAssetIndexLoadsIsThereAndEveryAssetThereIsLoaded():

    with open(os.path.join(dist, 'index.html'), encoding = 'utf-8') as handle:
        index = handle.read()
    loaded = set(re.findall(r'(?:src|href)="/(assets/[^"]+)"', index))
    assert loaded, 'index.html loads no asset'
    assets = {f'assets/{name}' for name in os.listdir(os.path.join(dist, 'assets'))}
    assert loaded <= assets, f'index.html loads assets the build does not hold: {sorted(loaded - assets)}'

    # An asset not named in index.html is loaded by another one: a chunk imported by the app, a
    # font named in the stylesheet
    texts = index
    for name in assets:
        if name.endswith(('.js', '.css')):
            with open(os.path.join(dist, name), encoding = 'utf-8') as handle:
                texts += handle.read()
    orphans = sorted(name for name in assets if os.path.basename(name) not in texts)
    assert orphans == [], f'assets nothing loads, left from an earlier build: {orphans}'

def testTheBuildCarriesNothingButTheAppAndItsStamp():

    assert sorted(os.listdir(dist)) == ['assets', 'buildStamp.json', 'index.html']
