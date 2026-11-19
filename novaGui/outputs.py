
# -- NOVA GUI Run Outputs -- #

'''

Export's file handling: listing a finished run's outputs, copying the chosen ones to an
output folder, and opening a file or folder in the desktop's own application.

Every run writes all of NOVA's outputs into a folder of its own, in the web GUI its run store
folder (`<store>/run<id>/`, novaGui.runStore): the outputs in `<runName>Outputs/` and the config
the run was given beside it as `<runName>RunConfig.json`. Nothing reaches the output folder until an export copies the chosen
files into `<output folder>/<runName>Outputs/`. The categories and the rule that files an output
in one by its name (`outputCategories`, `categoryOf`) are shared with the legacy Tkinter front
end's Export tab; the default output folder is `runs/` at the repository root.

The browser names files by their base name, and only names the run listed are copied, opened or
previewed, so a request cannot reach a file outside the run's own folder.

The Export dialog previews a file before it is exported: an image as itself, an STL surface in the
browser's WebGL viewer (`stlMesh` reads it into vertices and triangles), and a text, CSV or JSON
file as its first lines (`previewKind` says which).

Author: Sean Bowman
Date:   11/17/2026

'''

# Standard library imports
import os
import re
import shutil
import subprocess
import sys

repositoryRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_unsafeName = re.compile(r'[\\/:*?"<>|]')

# What a run can write, in the order the list shows it: key, name, what it holds
outputCategories = (
    ('figures',     'Figures',              'PNG images of the contour, flow fields, near-wall state and heat transfer'),
    ('interactive', 'Interactive figures',  'plotly HTML views, with the plotly.js they load'),
    ('contours',    'Contour coordinates',  'hot wall, shell and channel centerline text files'),
    ('geometry',    '3D geometry',          'STL surfaces of the wall, the channels and the volutes'),
    ('profile',     'Channel size profile', 'the profile the jacket was built to, as JSON'),
    ('nozzle',      'Nozzle object',        'the pickled Nozzle, reloadable in Python'),
    ('config',      'Run configuration',    'the JSON the run was given'),
    ('other',       'Other files',          'anything else the run wrote'),
)

def categoryOf(fileName: str) -> str:

    '''

    The category a run output belongs to, by its name.

    '''

    lower = fileName.lower()
    if lower.endswith('runconfig.json'):
        return 'config'
    if lower.endswith('channelprofile.json'):
        return 'profile'
    if lower.endswith('.png'):
        return 'figures'
    if lower.endswith('.html') or lower == 'plotly.min.js':
        return 'interactive'
    if lower.endswith('.txt'):
        return 'contours'
    if lower.endswith(('.stl', '.step', '.stp')):
        return 'geometry'
    if lower.endswith('.pkl'):
        return 'nozzle'

    return 'other'

previewTextBytes = 200000      # [B] the most of a text file a preview reads
previewTriangles = 200000      # [-] the most triangles an STL preview draws

def previewKind(fileName: str) -> str | None:

    '''How the Export dialog previews a file: 'image', 'mesh', 'text', or None for no preview.'''

    lower = fileName.lower()
    if lower.endswith(('.png', '.jpg', '.jpeg', '.svg')):
        return 'image'
    if lower.endswith('.stl'):
        return 'mesh'
    if lower.endswith(('.txt', '.csv', '.json', '.dat')):
        return 'text'
    return None

def _readStl(path: str):

    '''

    An STL file's triangles as an (n, 3, 3) array [file units], binary or ASCII.

    '''

    import numpy as np

    size = os.path.getsize(path)
    with open(path, 'rb') as handle:
        head = handle.read(84)
        count = int.from_bytes(head[80:84], 'little') if len(head) == 84 else -1
        if count >= 0 and size == 84 + 50 * count:
            record = np.dtype([('normal', '<f4', 3), ('corners', '<f4', (3, 3)), ('attribute', '<u2')])
            return np.fromfile(handle, dtype = record, count = count)['corners'].astype(float)

    corners = []
    with open(path, encoding = 'ascii', errors = 'replace') as handle:
        for line in handle:
            parts = line.split()
            if len(parts) == 4 and parts[0] == 'vertex':
                corners.append([float(value) for value in parts[1:]])
    usable = len(corners) - len(corners) % 3
    return np.asarray(corners[:usable], dtype = float).reshape(-1, 3, 3)

def stlMesh(path: str, maxTriangles: int = previewTriangles) -> dict:

    '''

    An STL surface as the browser's mesh viewer draws it: shared vertices and the triangles
    between them.

    Corners are merged where they coincide, as an STL repeats each one for every triangle that
    meets it. A surface with more than `maxTriangles` is thinned by clustering: corners are
    snapped to a lattice fine enough to keep the shape, and triangles whose corners collapse
    together are dropped.

    Returns:
    --------
    dict : {'x', 'y', 'z': [vertex coordinates], 'i', 'j', 'k': [vertex indices per triangle],
        'triangles': in the file, 'shown': drawn}

    '''

    import numpy as np

    triangles = _readStl(path)
    total = len(triangles)
    corners = triangles.reshape(-1, 3)
    if total == 0:
        return {'x': [], 'y': [], 'z': [], 'i': [], 'j': [], 'k': [], 'triangles': 0, 'shown': 0}

    # The first lattice only merges coincident corners (an STL stores single precision); coarser
    # ones thin a surface over the cap
    extent = float(np.max(np.ptp(corners, axis = 0))) or 1.0
    cells = 1e6
    while True:
        snapped = np.round(corners / (extent / cells))
        vertices, index = np.unique(snapped, axis = 0, return_inverse = True)
        faces = index.reshape(-1, 3)
        faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])]
        if len(faces) <= maxTriangles or cells < 20.0:
            break
        cells = min(cells, 3000.0) * 0.7

    points = vertices * (extent / cells)
    return {'x': points[:, 0].tolist(), 'y': points[:, 1].tolist(), 'z': points[:, 2].tolist(),
            'i': faces[:, 0].tolist(), 'j': faces[:, 1].tolist(), 'k': faces[:, 2].tolist(),
            'triangles': total, 'shown': int(len(faces))}

def categories() -> list:

    '''[{key, name, description}] in the order the list shows them.'''

    return [{'key': key, 'name': name, 'description': description} for key, name, description in outputCategories]

def defaultBaseDir() -> str:

    '''The runs folder at the repository root, so exported output collects in one place.'''

    return os.path.join(repositoryRoot, 'runs')

def safeRunName(name: str) -> str:

    '''A run name usable as a folder name: the config's `filename`, else novaRun.'''

    name = str(name or '').strip()
    if not name or _unsafeName.search(name) or name in ('.', '..'):
        return 'novaRun'
    return name

def targetFolder(baseDir: str, runName: str) -> str:

    '''`<baseDir>/<runName>Outputs`, with a blank base meaning the default folder.'''

    base = os.path.abspath(os.path.expanduser(str(baseDir or '').strip() or defaultBaseDir()))
    return os.path.join(base, safeRunName(runName) + 'Outputs')

def runFiles(record) -> dict:

    '''

    {base name: path} of a finished run's outputs and its run config, or {} for no run.

    '''

    if record is None or not record.ok or not record.outputDir:
        return {}

    files = {}
    if os.path.isdir(record.outputDir):
        for entry in sorted(os.listdir(record.outputDir)):
            path = os.path.join(record.outputDir, entry)
            if os.path.isfile(path):
                files[entry] = path
    configPath = os.path.join(os.path.dirname(record.outputDir), record.runName + 'RunConfig.json')
    if os.path.isfile(configPath):
        files[os.path.basename(configPath)] = configPath

    return files

def listing(record) -> list:

    '''[{name, category, bytes}] for a finished run's outputs, in name order.'''

    return [{'name': name, 'category': categoryOf(name), 'bytes': os.path.getsize(path)}
            for name, path in runFiles(record).items()]

def export(record, baseDir: str, names: list) -> dict:

    '''

    Copy the named outputs of a finished run into its target folder.

    Parameters:
    -----------
    record : novaGui.session.RunRecord
        The finished run.
    baseDir : str
        The output folder; the files land in `<baseDir>/<runName>Outputs/`.
    names : list
        Base names from the run's listing.

    Returns:
    --------
    dict : {'target': str, 'written': int, 'bytes': int}

    Raises:
    -------
    ValueError : if nothing is named, or a name is not one of the run's outputs
    OSError : if the target folder cannot be written

    '''

    files = runFiles(record)
    unknown = [name for name in names if name not in files]
    if unknown:
        raise ValueError(f'not outputs of this run: {", ".join(unknown[:5])}')
    if not names:
        raise ValueError('nothing is checked')

    target = targetFolder(baseDir, record.runName)
    os.makedirs(target, exist_ok = True)
    written = 0
    total = 0
    for name in names:
        destination = os.path.join(target, name)
        shutil.copy2(files[name], destination)
        written += 1
        total += os.path.getsize(destination)

    return {'target': target, 'written': written, 'bytes': total}

def openPath(path: str) -> None:

    '''Open a file or folder in the desktop's application for it.'''

    if sys.platform.startswith('win'):
        os.startfile(path)                                 # noqa: S606 -- user-initiated open
    elif sys.platform == 'darwin':
        subprocess.run(['open', path], check = False)
    else:
        subprocess.run(['xdg-open', path], check = False)
