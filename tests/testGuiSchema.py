# -- NOVA: GUI Import and Configuration Schema Tests -- #

'''

The GUI package against what it has to hold without a display.

`novaGui.bat` launches through `pythonw`, which has no console, so a module that fails to import
closes the launcher without a word. Every module of `novaGui` is therefore imported here, where the
traceback is visible. The Design form builds the config it hands a run from `novaGui.configSchema`
alone, and that module states that it carries every key of the shipped configuration exactly once;
a key the backend reads and the schema lacks never reaches a GUI run. The window icon and the
banner mark are images the GUI loads by path, so their files are checked too.

Author: Sean Bowman

'''

import importlib
import json
import os
import pkgutil
import sys

import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

import novaGui
from novaGui import assetFolder, configSchema

# The entry point runs the application when imported
entryModules = {'novaGui.__main__'}

guiModules = sorted(name for _, name, _ in pkgutil.walk_packages(novaGui.__path__, 'novaGui.')
                    if name not in entryModules)

@pytest.mark.parametrize('moduleName', guiModules)
def testEveryGuiModuleImports(moduleName):
    '''Each module of the GUI package imports headless, so the launcher can reach its window.'''
    importlib.import_module(moduleName)

def testTheSchemaCarriesEveryShippedKeyExactlyOnce():
    '''
    The schema's real fields are the shipped configuration's keys, each once, with none added. Keys
    led by an underscore annotate the file and are not configuration.
    '''
    with open(os.path.join(root, 'src', 'NOVA', 'assets', 'NOVANozzle.json'), encoding = 'utf-8') as handle:
        shipped = {key for key in json.load(handle) if not key.startswith('_')}
    keys = [field.key for field in configSchema.allFields() if not field.synthetic]
    assert len(keys) == len(set(keys)), 'a key appears in more than one field'
    assert set(keys) - shipped == set(), 'the schema carries keys the shipped configuration does not'
    assert shipped - set(keys) == set(), 'the shipped configuration carries keys the schema does not'

def testTheRunnerLoadsNovaAndRedirectsItsOutput(tmp_path):
    '''
    The runner patches names it expects NOVA's modules to carry, so a name that moves inside NOVA
    breaks the GUI at the first press of Generate and nowhere else. Loading NOVA the way the runner
    does catches it here. The loader patches the Nozzle class and matplotlib's settings for the
    whole process, so each is put back for the tests that follow.
    '''
    import queue
    import matplotlib
    from NOVA import Nozzle
    from novaGui.runner import PipelineRunner

    # The class's own binding, if it has one rather than inheriting the method
    savedOutputRoot = Nozzle.__dict__.get('_getOutputRoot')
    try:
        with matplotlib.rc_context():
            _, nozzleClass = PipelineRunner(queue.Queue())._loadNova(str(tmp_path))
        assert nozzleClass is Nozzle
        assert Nozzle._getOutputRoot(None) == str(tmp_path)
    finally:
        if savedOutputRoot is not None:
            Nozzle._getOutputRoot = savedOutputRoot
        elif '_getOutputRoot' in Nozzle.__dict__:
            del Nozzle._getOutputRoot

def testTheBrandingImagesShipAtEverySizeOnATransparentGround():
    '''
    Every icon frame is drawn at its own size, the Windows icon file carries all of them, and the
    icons and the banner marks are transparent at the corner, so they sit on the taskbar and the
    header rather than on a painted square.
    '''
    from PIL import Image
    folder = os.path.join(assetFolder, 'icon')
    sizes = sorted(int(name[len('icon'):-len('.png')]) for name in os.listdir(folder) if name.endswith('.png'))
    assert 64 in sizes, 'the server serves the 64 px icon as the page icon'
    for size in sizes:
        with Image.open(os.path.join(folder, f'icon{size}.png')) as image:
            assert image.size == (size, size)
            assert image.mode == 'RGBA' and image.getpixel((0, 0))[3] == 0
    for banner in ('plumeBanner.png', 'plumeBannerLight.png'):
        with Image.open(os.path.join(assetFolder, banner)) as image:
            assert image.mode == 'RGBA' and image.getpixel((0, 0))[3] == 0
    with Image.open(os.path.join(assetFolder, 'nova.ico')) as image:
        assert set(image.info['sizes']) == {(size, size) for size in sizes}

def testAFreshFormIsTheShippedNozzle():
    '''
    The form's defaults are the shipped configuration's values, key for key, so a fresh form and
    Reset to example build the nozzle `generateNozzle()` builds with no configuration given.
    '''
    with open(configSchema.shippedConfigPath, encoding = 'utf-8') as handle:
        shipped = {key: value for key, value in json.load(handle).items() if not key.startswith('_')}
    assert configSchema.defaultConfig() == shipped

def testTheLengthFractionCanCarryTheOptimizeRequest():
    '''A text length fraction asks the backend to search for the best one, so the field keeps text.'''
    spec = next(field for field in configSchema.allFields() if field.key == 'lengthFraction')
    assert spec.kind == 'floatText'

def testEveryFixedChoiceDefaultIsOneOfItsChoices():
    '''A choice field that cannot be typed into has to default to a value its dropdown offers.'''
    for field in configSchema.allFields():
        if field.kind == 'choice' and not field.editable and field.default is not None:
            assert field.default in [value for _, value in field.choices], field.key
