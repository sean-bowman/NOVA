# Releasing the Desktop App

A release is NOVA's GUI frozen into a Windows folder, `NOVA.exe` with its supporting files, zipped and attached to a [GitHub Release](https://github.com/sean-bowman/NOVA/releases) for users without Python. Development runs from the checkout (`nova-gui`, [novaGui/README.md](../novaGui/README.md)); a release is built from a version tag.

## Making a release

1. Set the version in `pyproject.toml`, `src/NOVA/__init__.py` and `novaGui/__init__.py`. `tests/testStandaloneBuild.py` holds the three equal.
2. Merge the change to main.
3. Once the Tests workflow ([.github/workflows/tests.yml](../.github/workflows/tests.yml)) has passed on the merge commit, tag it with the version and push the tag:

   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. The Release workflow ([.github/workflows/release.yml](../.github/workflows/release.yml)) builds `NOVA.exe` on a Windows runner and runs the shipped nozzle through it. It then publishes the release with `NOVA-<version>-win64.zip` attached and notes generated from the pull requests merged since the last tag, under the install note in [packaging/releaseNotes.md](../packaging/releaseNotes.md).

A tag that does not match the version in `pyproject.toml` stops the build. A failed smoke test stops it before anything is published.

A pull request that touches `packaging/`, `pyproject.toml` or the workflow runs the same build and smoke test without publishing, and keeps the zip as a workflow artifact for two weeks. The workflow can also be run by hand from the Actions tab.

## Building locally

From a clean Python 3.10 environment, so nothing outside NOVA's dependencies gets bundled:

```bash
pip install .[web,refprop] -r packaging/requirements.txt -c packaging/constraints.txt
python packaging/buildRelease.py               # build, smoke test, zip
python packaging/buildRelease.py --skip-smoke  # build and zip only
```

A conda Python links some of its extension modules to DLLs in the environment's `Library\bin` (`pyexpat.pyd` to `libexpat.dll`, for one). PyInstaller finds those through `PATH`, so build from the activated environment (`conda activate`, or `conda run -p <env> python packaging/buildRelease.py`); otherwise it can bundle another install's copy, and the exe fails to load the module. A python.org Python, which the Release workflow uses, keeps those DLLs beside the modules in its own `DLLs` folder, where PyInstaller finds them first.

[packaging/requirements.txt](../packaging/requirements.txt) pins PyInstaller. [packaging/constraints.txt](../packaging/constraints.txt) pins NOVA's dependencies to the versions the test suite passes with in the development environment, so a release runs what was tested; update it when the development environment moves to new versions and the suite passes there.

The build lands in `dist/NOVA/` and the zip beside it, `dist/NOVA-<version>-win64.zip`. [packaging/smokeTest.py](../packaging/smokeTest.py) runs on its own against any build: it starts the exe from a folder outside the checkout with a run store of its own, checks that the schema loads and that every validation model reads its records as the checkout does, runs the shipped nozzle, and draws an interactive figure, a static figure and the report.

## What the build carries

[packaging/nova.spec](../packaging/nova.spec) is the PyInstaller build: a folder of about 240 MB, 110 MB zipped, which a clean build makes in about 4 minutes. It takes:

- `NOVA` and `novaGui` from the checkout, every submodule and every file under their assets folders, so new modules and assets need no edit to the build
- the front end as its build, `novaGui/frontend/dist`, without its sources
- the checkout files the GUI reads at run time, at their checkout paths: the validation summary, the shipped configuration and the records the summary quotes ([packaging/bundleData.py](../packaging/bundleData.py))
- the third-party packages through PyInstaller's hooks, with RocketCEA's data files (`thermo.lib`, `trans.lib`) added by hand
- ctREFPROP, NIST's wrapper for REFPROP, so a machine with REFPROP installed uses it; REFPROP itself is licensed separately and not included, and a machine without it uses CoolProp

`tkinter` and `pytest` are left out. The executable is not UPX-packed, since packed executables draw more antivirus false positives.

A new third-party dependency, or a data file read from outside the assets folders, may need an entry in the spec. The smoke test on the pull request shows whether it does.

## The app on a user's machine

| What | Where |
| --- | --- |
| Finished runs | `%LOCALAPPDATA%\NOVA\runs` |
| Exports | `Documents\NOVA`, unless the Export dialog names another folder |
| Theme setting | `%APPDATA%\NOVA` |
| Startup log | `%TEMP%\NOVA\novaGui.log` |
| CEA work files | `%USERPROFILE%\RocketCEA` |

[packaging/userReadme.txt](../packaging/userReadme.txt) goes into the folder as `README.txt` and tells the user the same.

## Code signing

Releases are not code-signed. Windows SmartScreen shows "Windows protected your PC" on the first launch, and the user clicks **More info**, then **Run anyway**. Some antivirus tools flag PyInstaller builds, and company IT often blocks unsigned executables. Signing is roadmap item G12 ([guiRoadmap.md](guiRoadmap.md)).
