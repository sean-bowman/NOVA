# -- NOVA: Standalone Build Entry Point -- #

'''

The script PyInstaller freezes into NOVA.exe (packaging/nova.spec). It opens the GUI as `nova-gui`
does.

Each run's worker is a process started with 'spawn', which in the frozen build is NOVA.exe started
again with multiprocessing's arguments. `freeze_support` turns that start into the worker; without
it, every run would open a second GUI.

Author: Sean Bowman
Date:   11/21/2026

'''

# Standard library imports
import multiprocessing
import sys

if __name__ == '__main__':
    multiprocessing.freeze_support()

    from novaGui.__main__ import main

    sys.exit(main())
