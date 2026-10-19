# -- NOVA GUI: The Design Form -- #

'''

The Design tab's layout and the rows it is built from.

Each section leads with the fields a design is made from and folds the rest into Advanced
settings; each volute has a fold of its own, and a fold with nothing to show is hidden. Alternative
inputs share a selector row, which writes the chosen option's key and None to the others, so a form
cannot set both of a mutually exclusive pair. Program flags the GUI sets itself have no row and
pass through a loaded config. The form round-trips the shipped nozzle exactly, whichever rows its
keys live in.

Choosing an extension material fills what NOVA's material store carries for it. The Export tab
copies the checked outputs of a run from its staging folder to the output folder.

The scroll container gathers wheel input: deltas smaller than a notch add up, and notches that
arrive before the form redraws are applied in one scroll, because every scroll redraws the visible
form.

Author: Sean Bowman

'''

import os
import sys

import pytest

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

from novaGui import configSchema, theme

def _group(title: str):
    return next(group for group in configSchema.groups if group.title == title)

def _name(item) -> str:
    return item.name if isinstance(item, configSchema.Selector) else item.key

#--------------------------------------------------------------------------------------------------------------------------#
# -- The schema -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testTheContourSectionLeadsWithWhatADesignStartsFrom():
    '''The diverging type, the chamber diameter and the chamber length; the rest is advanced.'''
    contour = _group('Contour Definition')
    main = [_name(item) for item in contour.fields if not item.advanced]
    assert main == ['divergingSectionType', 'chamberDiameter', 'Chamber length']
    assert len([item for item in contour.fields if item.advanced]) == 10

def testTheTruncationIsSetWithTheRegenerativeCooling():
    cooling = _group('Regenerative Cooling')
    assert [_name(item) for item in cooling.fields][:2] == ['makeCoolingChannels', 'Regen truncation']
    contourKeys = {spec.key for spec in configSchema.allFields()[:len(_group('Contour Definition').fields) + 1]}
    assert 'regenTruncationType' not in contourKeys

def testCombustionSizesTheEngineOnTwoSelectorsAndFoldsTheInletTemperatures():
    combustion = _group('Combustion')
    main = [_name(item) for item in combustion.fields if not item.advanced]
    assert main == ['Fuel', 'Oxidizer', 'OFRatio', 'chamberPressure', 'Engine size', 'Nozzle expansion']
    advanced = [_name(item) for item in combustion.fields if item.advanced]
    assert advanced == ['fuelInitialTemperature', 'oxidizerInitialTemperature']

def testRegenerativeCoolingShowsTheJacketsDesignInputsAndFoldsTheRest():
    cooling = _group('Regenerative Cooling')
    main = [_name(item) for item in cooling.fields if not configSchema.foldOf(item)]
    # The helix angle and the manual profile belong to the channel type and sizing they complete:
    # each is required when its choice is made, and shows only then
    assert main == ['makeCoolingChannels', 'Regen truncation', 'material', 'channelType', 'channelHelixAngle',
                    'channelSizingMode', 'manualChannelProfileKey', 'manualChannelProfile', 'nChannel',
                    'hotWallThickness', 'infillThickness', 'shellThickness', 'maxWallTemperature',
                    'coolantClass', 'coolant', 'coolantInitialTemperature', 'coolantInitialPressure',
                    'coolantMassFlow']
    assert all(configSchema.foldOf(item) == configSchema.advancedFold
               for item in cooling.fields if _name(item) not in main)

def testEachVoluteHasAFoldOfItsOwn():
    volutes = _group('Volutes')
    for item in volutes.fields:
        fold = configSchema.foldOf(item)
        if item.key.startswith(('inlet', 'makeInlet')):
            assert fold == 'Inlet volute', item.key
        elif item.key.startswith(('outlet', 'makeOutlet')):
            assert fold == 'Outlet volute', item.key
        else:
            assert fold is None, item.key

def testTheGuiSetsThePlotAndExportFlagsItself():
    hidden = {spec.key for spec in configSchema.allFields() if spec.hidden}
    assert hidden == set(configSchema.forcedFlags)

def testTheLabelsSayChamberDiameterAndNameNoStandardAlloy():
    spec = next(field for field in configSchema.allFields() if field.key == 'chamberDiameter')
    assert spec.label == 'Chamber diameter'
    assert all('standard' not in label for label, _ in configSchema.materialChoices)

def testTheExtensionMaterialsAreTheStoresHotStructures():
    '''Every material the store carries that can be a radiation-cooled shell, and no other.'''
    from novaGui import backend
    materials = backend.materialsModule()
    offered = {value for _, value in configSchema.extensionMaterialChoices if value is not None}
    hotStructure = {name for name in materials.availableMaterials()
                    if materials.materialProfile(name)['class'] in ('refractoryMetal', 'composite', 'refractory')}
    assert offered == hotStructure

def testEverySelectorWritesOnlyTheKeysItHolds():
    for group in configSchema.groups:
        for item in group.fields:
            if not isinstance(item, configSchema.Selector):
                continue
            keys = set(item.keys())
            labels = [option.label for option in item.options]
            assert item.blank in labels, item.name
            for option in item.options:
                assert option.key is None or option.key in keys, (item.name, option.label)
                assert set(option.sets) <= keys, (item.name, option.label)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The form -- #
#--------------------------------------------------------------------------------------------------------------------------#

@pytest.fixture
def form(tkRoot):
    from novaGui.tabs.configTab import ConfigTab
    theme.applyTheme(tkRoot, 'dark')
    tab = ConfigTab(tkRoot, None)
    tab.pack()
    tkRoot.update_idletasks()
    return tab

def _selector(form, name: str):
    return next(row for row in form._selectors if row.spec.name == name)

def _choose(row, label: str) -> None:
    row._choice.set(label)
    row._onChoice()

def testTheFormRoundTripsTheShippedNozzle(form):
    '''Every key, in the shipped file's order, whether it lives in a field row or a selector.'''
    shipped = configSchema.defaultConfig()
    config = form.getConfig()
    assert config == shipped
    assert list(config) == list(shipped)
    assert form.validate() == []

def testChoosingAnOptionWritesItsKeyAndClearsTheOther(form):
    chamber = _selector(form, 'Chamber length')
    assert chamber.selectedLabel == 'Characteristic length L*'
    _choose(chamber, 'Chamber barrel length')
    chamber._var.set('0.25')
    config = form.getConfig()
    assert config['Lstar'] is None and config['chamberLength'] == pytest.approx(0.25)

    # Each option keeps its own entry while another is chosen
    _choose(chamber, 'Characteristic length L*')
    config = form.getConfig()
    assert config['Lstar'] == pytest.approx(1.0) and config['chamberLength'] is None

def testTheTruncationModeTravelsWithItsValue(form):
    truncation = _selector(form, 'Regen truncation')
    assert truncation.selectedLabel == 'Truncate at area ratio'

    _choose(truncation, 'Truncate at recovery temperature')
    assert "'Truncate at recovery temperature' needs a value." in form.validate()
    truncation._var.set('3000')
    config = form.getConfig()
    assert (config['regenTruncationType'], config['regenTruncationValue']) == ('temp', pytest.approx(3000.0))

    _choose(truncation, 'No truncation (full contour)')
    config = form.getConfig()
    assert (config['regenTruncationType'], config['regenTruncationValue']) == ('none', None)

def testALoadedConfigChoosesTheOptionsItSets(form):
    config = configSchema.defaultConfig()
    config.update(thrust = None, engineMassFlow = 23.466, expansionRatio = None, targetExitPressure = 14000.0,
                  Lstar = None, chamberLength = None, regenTruncationType = 'temp', regenTruncationValue = 3200.0)
    form.setConfig(config)
    assert _selector(form, 'Engine size').selectedLabel == 'Engine mass flow'
    assert _selector(form, 'Nozzle expansion').selectedLabel == 'Target exit pressure'
    assert _selector(form, 'Chamber length').selectedLabel == 'Chamber barrel length'
    assert _selector(form, 'Regen truncation').selectedLabel == 'Truncate at recovery temperature'
    assert form.getConfig() == config

def testABlankChamberLengthIsAllowedAndABlankThrustIsNot(form):
    '''No barrel is a design; no engine size is not.'''
    _choose(_selector(form, 'Chamber length'), 'Chamber barrel length')
    assert form.validate() == []
    size = _selector(form, 'Engine size')
    _choose(size, 'Engine mass flow')
    assert form.validate() == ["'Engine mass flow' needs a value."]

def testAFlagWithNoRowPassesThroughALoadedConfig(form):
    config = configSchema.defaultConfig()
    config['export'] = 'off'
    form.setConfig(config)
    assert 'export' not in form._rows
    assert form.getConfig()['export'] == 'off'

def testAFoldWithNothingToShowIsHidden(form, tkRoot):
    cooling = next(entry for entry in form._folds if form._rows['gasSideAxialModel'] in entry[3])
    assert cooling[1].winfo_manager()
    config = configSchema.defaultConfig()
    config['makeCoolingChannels'] = False
    form.setConfig(config)
    assert not cooling[1].winfo_manager()

def testChoosingAnExtensionMaterialFillsWhatTheStoreCarries(form):
    row = form._rows['extensionMaterial']
    row._var.set(row.spec.valueToLabel('ATJ Graphite'))
    form._onExtensionMaterial()
    assert form.getConfig()['extensionThermalConductivity'] == pytest.approx(116.0)

    # C103 carries an emissivity and no conductivity, which keeps the value it had
    form._rows['extensionInnerEmissivity'].set(0.4)
    row._var.set(row.spec.valueToLabel('C103'))
    form._onExtensionMaterial()
    config = form.getConfig()
    assert config['extensionInnerEmissivity'] == pytest.approx(0.7)
    assert config['extensionThermalConductivity'] == pytest.approx(116.0)

def testAnAtmosphereTheMaterialHasNoLimitForIsFlagged(form):
    config = configSchema.defaultConfig()
    config.update(makeRadiativeExtension = True, extensionMaterial = 'C103', extensionAtmosphere = 'oxidisingCoated')
    form.setConfig(config)
    assert any("'Service atmosphere'" in problem for problem in form.validate())

def testNoDropdownClipsItsLongestOption(form, tkRoot):
    '''Every dropdown on show is wide enough for its longest option, in the font it draws with.'''
    from tkinter import font as tkfont
    from novaGui import units
    form.pack(fill = 'both', expand = True)
    for _, fold, _, _ in form._folds:
        fold.setOpen(True)
    tkRoot.update()

    def textSpace(widget):
        measure = tkfont.Font(root = tkRoot, font = widget.cget('font')).measure
        overhead = widget.winfo_reqwidth() - measure('0') * int(widget.cget('width'))
        return measure, widget.winfo_width() - overhead

    dropdowns = [(row._widget, row.spec.choiceLabels()) for row in form._rows.values() if row.spec.kind == 'choice']
    dropdowns += [(row._unitWidget, units.unitsFor(row._dimension)) for row in form._rows.values() if row._unitWidget]
    dropdowns += [(row._picker, list(row._options)) for row in form._selectors]
    checked = 0
    for widget, texts in dropdowns:
        if not widget.winfo_ismapped():
            continue
        measure, space = textSpace(widget)
        widest = max(texts, key = measure)
        assert measure(widest) <= space, widest
        checked += 1
    assert checked > 40

def testChangingAUnitKeepsTheQuantity(form):
    size = _selector(form, 'Engine size')
    _choose(size, 'Engine mass flow')
    size._var.set('10')
    size._unitVar.set('lbm/s')
    size._onUnitChange()
    assert float(size._var.get()) == pytest.approx(22.0462, rel = 1e-4)
    assert form.getConfig()['engineMassFlow'] == pytest.approx(10.0)

#--------------------------------------------------------------------------------------------------------------------------#
# -- Scrolling -- #
#--------------------------------------------------------------------------------------------------------------------------#

class _Wheel:
    def __init__(self, delta):
        self.delta = delta

@pytest.fixture
def scroller(tkRoot):
    from novaGui.widgets import ScrollableFrame
    theme.applyTheme(tkRoot, 'dark')
    frame = ScrollableFrame(tkRoot)
    frame.pack()
    return frame

def testDeltasSmallerThanANotchAddUp(scroller):
    '''A precision touchpad reports a fraction of a notch at a time; four quarters are one notch.'''
    for _ in range(4):
        scroller._onWheel(_Wheel(-30))
    assert scroller._pendingLines == scroller.wheelLines

def testNotchesBeforeARedrawAreAppliedInOneScroll(tkRoot, scroller):
    scrolls = []
    scroller._canvas.yview_scroll = lambda number, what: scrolls.append((number, what))
    for _ in range(4):
        scroller._onWheel(_Wheel(-120))
    tkRoot.update()
    assert scrolls == [(4 * scroller.wheelLines, 'units')]

def testADropdownDoesNotTakeTheWheel(tkRoot, scroller):
    '''Scrolling the form over a dropdown scrolls the form rather than changing the dropdown.'''
    assert tkRoot.bind_class('TCombobox', '<MouseWheel>') == ''

#--------------------------------------------------------------------------------------------------------------------------#
# -- Export -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testAnOldSessionsStagingIsClearedAndThisOnesIsKept(tmp_path, monkeypatch):
    import os
    import time
    from novaGui import runner
    monkeypatch.setattr(runner.tempfile, 'gettempdir', lambda: str(tmp_path))
    mine = runner.stagingFolder()
    old = os.path.join(os.path.dirname(mine), 'session1')
    for folder in (mine, old):
        os.makedirs(folder)
        stale = time.time() - 13 * 3600
        os.utime(folder, (stale, stale))
    runner.clearStaging()
    assert os.path.isdir(mine) and not os.path.isdir(old)

def testExportCopiesOnlyTheCheckedOutputs(tkRoot, tmp_path):
    import os
    import types
    from novaGui.tabs.exportTab import ExportTab
    theme.applyTheme(tkRoot, 'dark')
    tab = ExportTab(tkRoot, types.SimpleNamespace(configTab = None))
    tab.pack()

    staging = tmp_path / 'staging' / 'demoOutputs'
    staging.mkdir(parents = True)
    for name in ('machContours.png', 'contourInteractive.html', 'plotly.min.js', 'demoChannel.stl', 'demo.pkl'):
        (staging / name).write_text('x')
    configPath = tmp_path / 'staging' / 'demoRunConfig.json'
    configPath.write_text('{}')
    result = types.SimpleNamespace(outputDir = str(staging), configPath = str(configPath), runName = 'demo')
    tab.refresh(result)
    assert len(tab._chosen) == 6

    # Unchecking a category leaves its files behind, and stays unchecked for the next run
    tab._choose([path for path, kind in tab._files.items() if kind == 'geometry'], False)
    tab._unchecked.add('geometry')
    tab._baseDir.set(str(tmp_path / 'out'))
    written = tab.export()
    assert sorted(os.path.basename(path) for path in written) == [
        'contourInteractive.html', 'demo.pkl', 'demoRunConfig.json', 'machContours.png', 'plotly.min.js']
    assert all(os.path.dirname(path) == str(tmp_path / 'out' / 'demoOutputs') for path in written)
    tab.refresh(result)
    assert not any(kind == 'geometry' for path, kind in tab._files.items() if path in tab._chosen)
