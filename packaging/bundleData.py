# -- NOVA: Checkout Files the Standalone Build Carries -- #

'''

The checkout files the GUI reads at run time, which the standalone build has to carry at the same
paths relative to its root.

The GUI finds them from its own location (`novaGui.repositoryRoot`), which in the frozen build is
the bundle's folder of supporting files. Laid out there as in the checkout, they resolve with no
code of the GUI's changed:

    novaGui.checkoutFiles       the validation summary and the shipped configuration
    the validation records      the files the summary quotes, which the result pane's badges open
                                (`novaGui.validationStatus.passages`)

The list is built from those two sources each time, so a record added to the summary rides along
without an edit here. tests/testPackaging.py holds it to them.

Author: Sean Bowman
Date:   11/21/2026

'''

# Standard library imports
import json
import os

def recordPaths(root: str) -> set:

    '''Every record the validation summary quotes, as a path relative to the checkout root.'''

    with open(os.path.join(root, 'docs', 'validationStatus.json'), encoding = 'utf-8') as handle:
        summary = json.load(handle)
    return {source['path'] for model in summary['models'].values() for source in model.get('sources', [])}

def checkoutData(root: str) -> list:

    '''

    The checkout files the build carries, as PyInstaller `datas` pairs: the file's absolute path and
    the folder it goes to, relative to the bundle root.

    Parameters:
    -----------
    root : str
        The checkout's root folder

    Returns:
    --------
    list : (source path, destination folder) pairs, sorted by path

    '''

    import sys

    if root not in sys.path:
        sys.path.insert(0, root)
    import novaGui

    paths = set(novaGui.checkoutFiles) | recordPaths(root)
    return [(os.path.join(root, *path.split('/')), os.path.dirname(path)) for path in sorted(paths)]
