# -- Top-Level Code Interface for the NOVA Nozzle Design Tool -- #

'''

Smallest possible NOVA run. Builds a Nozzle from the worked LOX/LH2 example and generates it
end to end.

Point generateNozzle at a different configuration file to run a different case:

    myNozzle.generateNozzle(configPath = 'path/to/myConfig.json')

The package default, src/NOVA/assets/nozzleConfig.json, is a zeroed template rather than a
runnable case: it names no propellants, so a run started from it stops in the thermochemistry.
It is the key list to copy when writing a new configuration.

Outputs, when the configuration enables export, are written to runs/<filename>Outputs/
at the repository root.

Author: Sean Bowman

'''

import os

from NOVA import Nozzle

exampleConfig = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'src', 'NOVA', 'assets', 'loxLh2Example.json')

if __name__ == '__main__':

    os.system('cls' if os.name == 'nt' else 'clear')

    myNozzle = Nozzle()
    myNozzle.generateNozzle(configPath = exampleConfig)
