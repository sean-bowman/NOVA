# -- NOVA: GUI Theme Tests -- #

'''

The GUI's theme: the palette it shares with NOVA's figures in both modes, the preference that
remembers the mode and the form's width, the views a run offers, and the notes a circuit choice
carries.

Author: Sean Bowman

'''

import json
import os
import sys
import types

import numpy as np
import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

from NOVA import palette as novaPalette
from novaGui import configSchema, settings, themeColors

#--------------------------------------------------------------------------------------------------------------------------#
# -- The palette -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheGuiAndNovasFiguresShareOnePalette():
    '''
    The GUI carries its own copy of the palette so it can open without importing NOVA. Every color
    the two share has to agree, in both modes, or the window and the figures it shows drift apart.
    '''
    for mode in novaPalette.modes:
        for name, color in novaPalette.palettes[mode].items():
            assert themeColors.palettes[mode][name].upper() == color.upper(), (mode, name)

def testBothModesNameTheSameColors():
    assert set(themeColors.palettes['dark']) == set(themeColors.palettes['light'])

def testEachFieldRampRisesInLightnessAndStandsClearOfItsBackground():
    '''
    A sequential field map has to rise monotonically in lightness, so value reads as value, and its
    ends must not vanish into the page they are drawn on.
    '''
    from matplotlib.colors import to_rgb

    def lightness(color):
        def linear(channel):
            return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055)**2.4
        red, green, blue = (linear(channel) for channel in to_rgb(color))
        luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        return 116.0 * luminance**(1.0 / 3.0) - 16.0 if luminance > 0.008856 else 903.3 * luminance

    for mode in novaPalette.modes:
        background = lightness(novaPalette.palettes[mode]['bg'])
        for name in ('mach', 'temperature'):
            values = [lightness(color) for color in novaPalette.colormapStops[mode][name]]
            assert all(later > earlier for earlier, later in zip(values, values[1:])), (mode, name)
            assert min(abs(values[0] - background), abs(values[-1] - background)) > 5.0, (mode, name)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The remembered preference -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheThemeModeRoundTrips(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'settingsPath', lambda: str(tmp_path / 'guiSettings.json'))
    assert settings.load()['themeMode'] == 'dark'
    settings.save({'themeMode': 'light'})
    assert settings.load()['themeMode'] == 'light'

@pytest.mark.parametrize('content', ['not json', json.dumps({'themeMode': 'sepia'}), json.dumps(['light'])])
def testAnUnreadablePreferenceReadsAsTheDefault(tmp_path, monkeypatch, content):
    path = tmp_path / 'guiSettings.json'
    path.write_text(content, encoding = 'utf-8')
    monkeypatch.setattr(settings, 'settingsPath', lambda: str(path))
    assert settings.load()['themeMode'] == 'dark'

def testTheFormWidthRoundTripsBesideTheThemeMode(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'settingsPath', lambda: str(tmp_path / 'guiSettings.json'))
    assert settings.load()['formWidth'] is None
    settings.save({**settings.load(), 'formWidth': 560})
    assert settings.load() == {'themeMode': 'dark', 'formWidth': 560}

@pytest.mark.parametrize('width', [True, '560', 12, 1e6, None])
def testAnOutOfRangeFormWidthIsNotKept(width):
    assert 'formWidth' not in settings.clean({'formWidth': width})

#--------------------------------------------------------------------------------------------------------------------------#
# -- The views and the circuit notes -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheViewsOfferOnlyWhatARunProduced():
    from novaGui.viewCatalog import availableViews

    assert availableViews(None, {}) == set()
    contourOnly = types.SimpleNamespace(xNozzleWall = np.linspace(0, 1, 10), nozzleNearWallMachNumber = np.ones(10),
                                        allXPoints = [np.zeros((3, 3))], xChannel = np.array([]),
                                        channelWallTemperature = np.array([]), nozzlePlumeStructure = None,
                                        # Both volutes asked for, none built: there are no channels to grow them on
                                        makeInletVolute = 'on', makeOutletVolute = 'on', inletVolute = None,
                                        outletVolute = None)
    available = availableViews(contourOnly, {'figures': {}})
    assert {'contour', 'nearWall', 'mach', 'pressure', 'temperature', 'revolved'} <= available
    cooling = {'wallMap', 'jacketTemperatures', 'coolantFlow', 'coolantProperties', 'heatFlux', 'film', 'extension'}
    assert not available & ({'plume', 'channelMesh', 'volute'} | cooling)

    cooled = types.SimpleNamespace(**{**vars(contourOnly), 'xChannel': np.zeros((40, 60)),
                                      'channelThermalResults': {'xHotWall3D': np.linspace(0, 1, 60)},
                                      'outletVolute': object(), 'nozzlePlumeStructure': object(),
                                      'filmCooling': 'on', 'xRegenNozzle': np.linspace(0, 1, 60),
                                      'regenSectionFilmEffectiveness': np.ones(60),
                                      'radiativeExtensionSolution': object(),
                                      'extensionWallTemperature': np.ones(40)})
    available = availableViews(cooled, {'figures': {}})
    assert {'plume', 'channelMesh', 'volute'} | cooling <= available

def testACircuitChoiceExplainsEveryOption():
    '''Every circuit the choice offers carries a note, which names the engines that flew it.'''
    spec = next(field for field in configSchema.allFields() if field.key == 'coolantCircuit')
    assert set(spec.optionHelp) == {value for _, value in spec.choices}
    assert 'F-1' in configSchema.optionHelpText(spec.optionHelp['twoPass'])
    assert 'J-2' in configSchema.optionHelpText(spec.optionHelp['oneAndHalfPass'])

def testEveryOptionAccountNamesWhereItFitsAndWhatFlewIt():
    from novaGui import configSchema

    for table in (configSchema.coolantCircuitHelp, configSchema.extensionOutletHelp):
        for entry in table.values():
            assert set(entry) == {'name', 'circuit', 'viable', 'heritage'}
            assert all(entry[key].strip() for key in entry)

