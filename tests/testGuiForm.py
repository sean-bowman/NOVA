# -- NOVA GUI: The Design Form -- #

'''

The Design form's layout as the schema lays it out (novaGui.configSchema), and the server's
staging folders.

Each section leads with the fields a design is made from and folds the rest into Advanced
settings; each volute has a fold of its own. Alternative inputs share a selector row, whose options
write only the keys the row holds. Program flags the GUI sets itself have no row. The extension
materials offered are the material store's hot structures.

A server that crashed leaves its staging folder behind, and the next one to start collects it.

Author: Sean Bowman

'''

import os
import sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.insert(0, root)

from novaGui import configSchema

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
# -- The server's staging -- #
#--------------------------------------------------------------------------------------------------------------------------#

def testAnOldServersStagingIsClearedAndThisOnesIsKept(tmp_path, monkeypatch):
    '''A crashed server's staging folder goes after twelve hours; this server's own stays however old.'''
    import time
    from novaGui import session
    monkeypatch.setattr(session.tempfile, 'gettempdir', lambda: str(tmp_path))
    mine = session.stagingRoot()
    old, recent = (os.path.join(os.path.dirname(mine), name) for name in ('web1', 'web2'))
    for folder, ageHours in ((mine, 13), (old, 13), (recent, 1)):
        os.makedirs(folder)
        stamp = time.time() - ageHours * 3600
        os.utime(folder, (stamp, stamp))
    session.clearStaging()
    assert os.path.isdir(mine) and not os.path.isdir(old) and os.path.isdir(recent)
