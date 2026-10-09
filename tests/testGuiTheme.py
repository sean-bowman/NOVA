# -- NOVA: GUI Theme Tests -- #

'''

The GUI's theme: the palette it shares with NOVA's figures, the images its rounded controls are
built from, the two modes it switches between, the preference that remembers the choice, and the
pieces of the View tab and the help markers that read from it.

The palette tests and the image tests need no display. The ones that build a Tk root skip where
Tk cannot open one.

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
from novaGui import configSchema, settings, theme, themeImages
from novaGui.widgets import fieldHelpText

@pytest.fixture
def tkRoot():
    import tkinter as tk
    try:
        window = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f'no display for a Tk root: {error}')
    window.withdraw()
    yield window
    theme._bindPalette('dark')
    window.destroy()

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
            assert theme.palettes[mode][name].upper() == color.upper(), (mode, name)

def testBothModesNameTheSameColors():
    assert set(theme.palettes['dark']) == set(theme.palettes['light'])

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
# -- The images -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.mark.parametrize('scale', [1.0, 1.5, 2.0])
def testEveryNineSliceKeepsAMiddleToTile(scale):
    '''
    ttk tiles an image element's middle to fill a widget. A border that reaches the middle leaves
    nothing to tile and the window never settles; a tiny middle makes a large widget draw from
    hundreds of thousands of tiles. Every image keeps a middle wider than its borders.
    '''
    images = themeImages.drawImages(theme.palettes['dark'], scale)
    borders = themeImages.elementBorders(scale)
    for role, border in (('button', borders['control']), ('field', borders['control']),
                         ('card', borders['card']), ('nav', borders['control'])):
        width, height = images[role].size
        assert width - 2 * border >= 2 * border and height - 2 * border >= 2 * border, role
    left, top, right, bottom = borders['tab']
    width, height = images['tab'].size
    assert width - left - right >= 2 and height - top - bottom >= 2

def testTheImagesScaleWithTheDisplay():
    small = themeImages.drawImages(theme.palettes['dark'], 1.0)
    large = themeImages.drawImages(theme.palettes['dark'], 2.0)
    assert large['info'].size[0] == 2 * small['info'].size[0]
    assert large['glyph.closed'].size[0] == 2 * small['glyph.closed'].size[0]

def testRoundedCornersAreTransparentAndTheMiddleIsTheFill():
    images = themeImages.drawImages(theme.palettes['dark'], 1.0)
    card = images['card']
    assert card.getpixel((0, 0))[3] == 0
    middle = card.getpixel((card.size[0] // 2, card.size[1] // 2))
    assert '#%02X%02X%02X' % middle[:3] == theme.palettes['dark']['surface'].upper()

def testTheOpenSectionMarkerIsTheClosedOneTurned():
    '''Closed, the nozzle lies on its side; open, it flows down. The open marker is the closed one turned.'''
    images = themeImages.drawImages(theme.palettes['dark'], 1.0)
    closed = np.asarray(images['glyph.closed'])[..., 3] > 128
    opened = np.asarray(images['glyph.open'])[..., 3] > 128
    rows, columns = np.nonzero(closed)
    assert np.ptp(columns) > np.ptp(rows)                  # wider than tall
    rows, columns = np.nonzero(opened)
    assert np.ptp(rows) > np.ptp(columns)                  # taller than wide

#--------------------------------------------------------------------------------------------------------------------------#
# -- The two modes -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testBothModesBuildEveryControlInEveryState(tkRoot):
    '''Every styled control is built and cycled through every state, in both modes, without a TclError.'''
    from tkinter import ttk

    theme.applyTheme(tkRoot, 'dark')
    widgets = [
        ttk.Button(tkRoot, text = 'b'), ttk.Button(tkRoot, text = 'a', style = 'Accent.TButton'),
        ttk.Button(tkRoot, text = 'h', style = 'Header.TButton'), ttk.Button(tkRoot, style = 'Toggle.Header.TButton'),
        ttk.Button(tkRoot, text = 's', style = 'Small.Card.TButton'), ttk.Entry(tkRoot), ttk.Entry(tkRoot, style = 'Card.TEntry'),
        ttk.Combobox(tkRoot), ttk.Combobox(tkRoot, style = 'Card.TCombobox'),
        ttk.Checkbutton(tkRoot, style = 'Card.TCheckbutton'), ttk.Frame(tkRoot, style = 'Card.TFrame'),
        ttk.Frame(tkRoot, style = 'Inset.TFrame'), ttk.Progressbar(tkRoot), ttk.Scrollbar(tkRoot),
        ttk.Scrollbar(tkRoot, style = 'Card.Vertical.TScrollbar'), ttk.Label(tkRoot, style = 'Info.Card.TLabel'),
        ttk.Label(tkRoot, style = 'Glyph.Card.TLabel'), ttk.Radiobutton(tkRoot, style = 'Nav.Toolbutton', value = 1),
        ttk.Notebook(tkRoot), ttk.Treeview(tkRoot),
    ]
    for widget in widgets:
        widget.pack()
    for mode in ('light', 'dark'):
        theme.setMode(tkRoot, mode)
        tkRoot.update_idletasks()
        for widget in widgets:
            for state in ('active', 'pressed', 'disabled', 'focus', 'selected', 'hover', 'readonly', 'alternate'):
                widget.state([state])
                tkRoot.update_idletasks()
                widget.state(['!' + state])

def testSwitchingModeRebindsThePaletteAndCallsTheListeners(tkRoot):
    theme.applyTheme(tkRoot, 'dark')
    heard = []
    callback = lambda: heard.append(theme.bg)
    theme.addListener(callback)
    theme.setMode(tkRoot, 'light')
    assert theme.mode == 'light' and theme.bg == theme.palettes['light']['bg']
    assert heard and heard[-1] == theme.palettes['light']['bg']

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

#--------------------------------------------------------------------------------------------------------------------------#
# -- Help markers and the View tab -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheHelpMarkerListsAChoiceFieldsOptions():
    spec = next(field for field in configSchema.allFields() if field.key == 'divergingSectionType')
    text = fieldHelpText(spec)
    assert spec.help.strip() in text
    for label in spec.choiceLabels():
        assert label in text

def testALongOptionListIsCountedRatherThanNamed():
    spec = configSchema.Field('example', 'Example', 'choice', choices = [f'option {index}' for index in range(20)],
                              help = 'An example.')
    text = fieldHelpText(spec, maximumOptions = 5)
    assert 'option 4' in text and 'option 5' not in text and 'and 15 more' in text

def testTheViewTabOffersOnlyWhatARunProduced():
    from novaGui.tabs.viewTab import availableViews

    assert availableViews(None, {}) == set()
    contourOnly = types.SimpleNamespace(xNozzleWall = np.linspace(0, 1, 10), nozzleNearWallMachNumber = np.ones(10),
                                        allXPoints = [np.zeros((3, 3))], xChannel = np.array([]),
                                        channelWallTemperature = np.array([]), makeInletVolute = 'off',
                                        makeOutletVolute = 'off', nozzlePlumeStructure = None)
    available = availableViews(contourOnly, {'figures': {}})
    assert {'contour', 'nearWall', 'mach', 'pressure', 'temperature', 'revolved'} <= available
    assert not available & {'plume', 'heatTransfer', 'channelMesh', 'volute', 'segments'}

    cooled = types.SimpleNamespace(**{**vars(contourOnly), 'xChannel': np.zeros((40, 60)),
                                      'channelWallTemperature': np.ones(60), 'makeOutletVolute': 'on',
                                      'nozzlePlumeStructure': object()})
    available = availableViews(cooled, {'figures': {'contour': 'x.png'}})
    assert {'plume', 'heatTransfer', 'channelMesh', 'volute', 'segments'} <= available
