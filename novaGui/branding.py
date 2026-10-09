# -- NOVA GUI Branding -- #

'''

The plume graphic as the window icon and as the mark beside the NOVA wordmark.

The images are drawn by `featureShowcase/buildGuiGraphic.py` into `novaGui/assets/`: one vertical
icon frame per size under `icon/`, and a horizontal banner mark for each theme mode. Nothing here is required to run:
a missing image leaves the window with Tk's own icon or the header with its wordmark alone.

Windows groups a taskbar button under the process's application id, and a GUI started through
`pythonw` would otherwise be grouped, and badged, as Python. Setting an explicit id before the
first window is created gives NOVA its own button carrying its own icon.

Author: Sean Bowman

'''

import os
import sys
import tkinter as tk

assetFolder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
appUserModelId = 'SeanBowman.NOVA.NozzleDesigner'
iconSizes = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)    # [px]

def setAppUserModelId() -> None:

    '''

    Give the process its own taskbar identity on Windows. Must run before the Tk root exists.

    '''

    if sys.platform != 'win32':
        return

    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appUserModelId)
    except (AttributeError, OSError):
        pass

def applyWindowIcon(root: tk.Tk) -> list:

    '''

    Set the plume icon on the root and on every window opened after it.

    Every size is handed to Tk, which picks the frame nearest to what the title bar, the taskbar
    and the task switcher each ask for, so none of them is scaled from a single image.

    Returns:
    --------
    list : the PhotoImages, which the caller has to keep referenced for as long as the window lives

    '''

    images = []
    for size in sorted(iconSizes, reverse = True):
        path = os.path.join(assetFolder, 'icon', f'icon{size}.png')
        if os.path.exists(path):
            images.append(tk.PhotoImage(master = root, file = path))
    if images:
        root.iconphoto(True, *images)

    return images

def bannerImage(master: tk.Misc, height: int, mode: str = 'dark'):

    '''

    The horizontal plume mark at a given height, for the header in a theme mode.

    The mark is drawn once at 192 px tall with lines heavy enough to survive the reduction, and
    reduced here to the header's height for the display it opens on. Pillow does the reduction,
    with premultiplied alpha so the transparent background lends no color to the edges.

    Parameters:
    -----------
    master : tkinter.Misc
        Any widget of the window the image is shown in.
    height : int
        Display height [px].
    mode : str
        'dark' or 'light': the light header gets a mark drawn in the light palette, because the
        dark one's fastest flow is nearly the light header's color.

    Returns:
    --------
    PIL.ImageTk.PhotoImage or None : None if the image or Pillow is missing

    '''

    path = os.path.join(assetFolder, 'plumeBannerLight.png' if mode == 'light' else 'plumeBanner.png')
    if not os.path.exists(path):
        path = os.path.join(assetFolder, 'plumeBanner.png')
    if not os.path.exists(path):
        return None
    try:
        from PIL import Image, ImageTk
    except ImportError:
        return None

    with Image.open(path) as source:
        width = max(1, int(round(source.width * height / source.height)))
        reduced = source.convert('RGBa').resize((width, height), Image.LANCZOS).convert('RGBA')

    return ImageTk.PhotoImage(reduced, master = master)
