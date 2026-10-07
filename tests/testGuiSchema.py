# -- NOVA: GUI Import and Configuration Schema Tests -- #

'''

The GUI package against what it has to hold without a display.

`novaGui.bat` launches through `pythonw`, which has no console, so a GUI module that fails to
import closes the launcher without a word. Every module is therefore imported here, where the
traceback is visible. The configuration tab builds the dictionary it hands the runner from
`novaGui.configSchema` alone, and that module states that it carries every key of the shipped
configuration exactly once; a key the backend reads and the schema lacks never reaches a GUI run.
Neither check needs a Tk root.

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
from novaGui import configSchema

# The entry points run the application when imported
entryModules = {'novaGui.__main__', 'novaGui.run'}

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

def testEveryFixedChoiceDefaultIsOneOfItsChoices():
    '''A choice field that cannot be typed into has to default to a value its dropdown offers.'''
    for field in configSchema.allFields():
        if field.kind == 'choice' and not field.editable and field.default is not None:
            assert field.default in [value for _, value in field.choices], field.key
