# -- Top-Level Code Interface for the NOVA Nozzle Design Tool -- #

'''

Smallest possible NOVA run. Builds a Nozzle from the default configuration in
NOVANozzleDesigner/assets/nozzleConfig.json and generates it end to end.

Point generateNozzle at a different configuration file to run a different case:

    myNozzle.generateNozzle(configPath = 'path/to/myConfig.json')

Outputs, when the configuration enables export, are written to runs/<filename>Outputs/
at the repository root.

Author: Sean Bowman

'''

import os
import sys

# NOVA's modules import each other by bare name, so the package directory itself has to be
# on the path rather than only its parent.
repositoryRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(repositoryRoot, 'NOVANozzleDesigner'))

from Nozzle import Nozzle

if __name__ == '__main__':

    os.system('cls' if os.name == 'nt' else 'clear')

    myNozzle = Nozzle()
    myNozzle.generateNozzle()
