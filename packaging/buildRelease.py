# -- NOVA: Build the Standalone Release -- #

'''

Builds the standalone GUI and packs it for a GitHub Release:

    1. PyInstaller freezes packaging/nova.spec into dist/NOVA/: NOVA.exe and its supporting files
    2. packaging/smokeTest.py runs the shipped nozzle through the built exe
    3. the folder, with packaging/userReadme.txt as README.txt, is zipped to
       dist/NOVA-<version>-win64.zip

Run it from the Python environment the build is made from: NOVA's dependencies with the web and
refprop extras (ctREFPROP, the wrapper a machine with REFPROP installed needs) at the versions the
suite is tested with (packaging/constraints.txt), and the pinned PyInstaller.

    pip install .[web,refprop] -r packaging/requirements.txt -c packaging/constraints.txt
    python packaging/buildRelease.py [--tag v<version>] [--skip-smoke]

--tag checks a release tag against the version in pyproject.toml and stops on a mismatch, so a
release cannot carry another version's number. .github/workflows/release.yml runs this script on a
version tag and attaches the zip to the release.

Author: Sean Bowman
Date:   11/21/2026

'''

# Standard library imports
import argparse
import os
import re
import shutil
import subprocess
import sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
packaging = os.path.join(root, 'packaging')
dist = os.path.join(root, 'dist')

def projectVersion() -> str:

    '''The version pyproject.toml declares.'''

    with open(os.path.join(root, 'pyproject.toml'), encoding = 'utf-8') as handle:
        found = re.search(r"^version\s*=\s*'([^']+)'", handle.read(), re.MULTILINE)
    if found is None:
        raise SystemExit('pyproject.toml declares no version')
    return found.group(1)

def _run(command: list) -> None:

    print('>', ' '.join(command), flush = True)
    subprocess.run(command, cwd = root, check = True)

def main(argv: list | None = None) -> int:

    parser = argparse.ArgumentParser(description = 'Build, test and zip the standalone NOVA GUI')
    parser.add_argument('--tag', default = '', help = 'release tag to check against the project version')
    parser.add_argument('--skip-smoke', action = 'store_true', help = 'build and zip without the smoke test')
    options = parser.parse_args(argv)

    version = projectVersion()
    if options.tag and options.tag != f'v{version}':
        raise SystemExit(f'tag {options.tag} does not match pyproject.toml version {version} (expected v{version})')

    _run([sys.executable, '-m', 'PyInstaller', os.path.join(packaging, 'nova.spec'), '--noconfirm', '--clean',
          '--distpath', dist, '--workpath', os.path.join(root, 'build', 'pyinstaller')])
    folder = os.path.join(dist, 'NOVA')
    shutil.copyfile(os.path.join(packaging, 'userReadme.txt'), os.path.join(folder, 'README.txt'))

    if not options.skip_smoke:
        _run([sys.executable, os.path.join(packaging, 'smokeTest.py'), os.path.join(folder, 'NOVA.exe')])

    archive = shutil.make_archive(os.path.join(dist, f'NOVA-{version}-win64'), 'zip', root_dir = dist, base_dir = 'NOVA')
    print(f'{archive} ({os.path.getsize(archive) / 1e6:.0f} MB)')

    return 0

if __name__ == '__main__':
    sys.exit(main())
