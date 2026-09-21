
# -- NOVA GUI Launcher -- #

'''

Standalone launcher so the GUI can be started with

    python novaGui/run.py

from the repository root, without needing the package on sys.path. Prefer
python -m novaGui when the working directory already contains the package.

Author: Sean Bowman
Date:   08/28/2026

'''

import os
import sys

# Put the repository root on the path so `import novaGui` resolves when this
# file is run directly.
repositoryRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repositoryRoot not in sys.path:
    sys.path.insert(0, repositoryRoot)

from novaGui.app import main

if __name__ == '__main__':
    main()
