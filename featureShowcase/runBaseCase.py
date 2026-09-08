'''Base LOX/LH2 run used by the feature showcase: chamber generation, material selection, plume.'''
import json, os, sys, pickle
import matplotlib
matplotlib.use('Agg', force=True)

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'NOVANozzleDesigner'))

import Nozzle as nozzleModule
from Nozzle import Nozzle

config = json.load(open(os.path.join(root, 'NOVANozzleDesigner', 'assets', 'loxLh2Example.json')))
config.update({
    'Lstar': 1.0,                    # exercises combustion chamber generation
    'material': 'GRCop-42',          # exercises the material-indifferent wall curves
    'plumeAmbientPressure': 101325.0,
    'plotsBasic': True,
    'plotsAdv': False,
    'export': True,
    'filename': 'showcaseBase',
})
configPath = os.path.join(here, 'showcaseConfig.json')
json.dump(config, open(configPath, 'w'), indent=2)

Nozzle._getOutputRoot = lambda self, _base=here: _base
nozzle = Nozzle()
nozzle.generateNozzle(configPath=configPath)

with open(os.path.join(here, 'showcaseBase.pkl'), 'wb') as handle:
    pickle.dump(nozzle, handle)
print('BASE RUN COMPLETE')
print('chamberDiameter      ', getattr(nozzle, 'chamberDiameter', None))
print('chamberInterfaceAngle', getattr(nozzle, 'chamberInterfaceAngle', None))
print('material             ', getattr(nozzle, 'material', None))
print('plume                ', type(getattr(nozzle, 'nozzlePlumeStructure', None)).__name__)
