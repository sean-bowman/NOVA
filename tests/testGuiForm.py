# -- NOVA GUI: The Design Form -- #

'''

The Design tab's layout and the rows it is built from.

Each section leads with the fields a design is made from and folds the rest into Advanced
settings. Alternative inputs share a selector row, which writes the chosen option's key and None
to the others, so a form cannot set both of a mutually exclusive pair. The form round-trips the
shipped nozzle exactly, whichever rows its keys live in.

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
