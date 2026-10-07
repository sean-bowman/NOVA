# -- The GUI's plume graphic, banner mark and window icon -- #

'''

The NOVA nozzle and its plume at a lip pressure ratio of 1.05, drawn on a transparent background as
the GUI's graphic, its banner mark and its window icon.

A lip ratio of 1.05 is a jet leaving the lip 5 percent above ambient pressure: slightly
underexpanded, so the boundary turns gently outward at the lip, and the lip's expansion fan comes
back off the free boundary as compression that converges toward the axis. The plume is the station
march of `stationMarch.solveStationField` carried four lip radii past the exit plane, where mass
continuity holds within half a percent; past about six the march is a picture rather than an
answer (see `buildPlumeSweep.py`). Inside the nozzle the shading is the contour's own
characteristic mesh, and upstream of the throat the one-dimensional answer painted across the
radius.

One solve feeds every image, all written to `novaGui/assets/`:

    plumeGraphic.png    horizontal, 3200 px across, for documents and splash use
    plumeBanner.png     horizontal, 192 px tall, with lines heavy enough to survive the GUI
                        shrinking it to the banner's height
    icon/icon<N>.png    vertical, nozzle at the top and plume running down, one square frame per
                        icon size, each drawn at its own size so its lines stay visible
    nova.ico            the same frames in one Windows icon file, for shortcuts

The images carry no axes, title or color bar. They use the viridis map the GUI uses for its Mach
plots and fade out over the last part of the plume they show. Each frame is drawn at four times its
size and reduced, which antialiases the small icons far better than drawing them directly.

Run it from the NOVA root, after `python featureShowcase/runBaseCase.py` has written the pickle:

    python featureShowcase/buildGuiGraphic.py

Author: Sean Bowman

'''

import os
import pickle
import sys

import matplotlib
matplotlib.use('Agg', force = True)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon
from PIL import Image

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'src'))
sys.path.insert(0, here)

from buildPlumeSweep import chamberField, interiorField, lipPressureOf
from NOVA.plume import plumeCharacteristicSeed
from NOVA.stationMarch import solveStationField

LIPRATIO = 1.05            # [-], lip static over ambient
REACH = 4.0                # [-], lip radii past the exit plane the march is carried
ICONREACH = 2.5            # [-], lip radii the icon shows, so its silhouette is not a needle
RADIALPOINTS = 121         # [-], points across each station
SUPERSAMPLE = 4            # [-], drawn at this multiple of the final size, then reduced
ICONSIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)    # [px]

copper      = '#E0975A'    # novaGui.theme.accent
boundaryInk = '#d8e0ec'    # novaGui.theme.text

assetFolder = os.path.join(root, 'novaGui', 'assets')

#----------------------------------------------------------------------#
# -- The scene -- #
#----------------------------------------------------------------------#

def solveScene() -> dict:

    '''

    Solve the plume at the graphic's lip ratio and gather everything the images draw, in lip radii
    from the exit plane.

    The chamber's one-dimensional answer, the contour's characteristic mesh and the plume march are
    kept as one field. Shaded separately they leave a hairline of background at the throat and at
    the exit plane, where two filled contours meet edge to edge.

    Returns:
    --------
    dict : the field nodes, the wall, the plume boundary, the Mach levels and the solve's figures

    '''

    with open(os.path.join(here, 'showcaseBase.pkl'), 'rb') as handle:
        nozzle = pickle.load(handle)

    lipPressure = lipPressureOf(nozzle)
    ambient = lipPressure / LIPRATIO
    field = solveStationField(nozzle.plumeContour(), ambientPressure = ambient, reach = REACH,
                              radialPoints = RADIALPOINTS)
    if not field.solved:
        raise RuntimeError(f'the plume march refused lip ratio {LIPRATIO}: {field.notes[-1]}')

    lipX, lipRadius = field.lipX, field.lipRadius
    seed = plumeCharacteristicSeed(nozzle.plumeContour())
    blocks = [chamberField(nozzle), interiorField(nozzle, seed['exitX']),
              (np.asarray(field.nodeX), np.asarray(field.nodeR), np.asarray(field.nodeMach))]

    # One scale for the supersonic flow either side of the lip. The chamber is left out of it and
    # clips to the bottom color, as in the sweep, so the plume keeps the full range.
    supersonic = np.concatenate([np.asarray(values) for _, _, values in blocks[1:]])

    return {
        'axial':     np.concatenate([(np.asarray(x) - lipX) / lipRadius for x, _, _ in blocks]),
        'radial':    np.concatenate([np.asarray(r) / lipRadius for _, r, _ in blocks]),
        'mach':      np.concatenate([np.asarray(values) for _, _, values in blocks]),
        'wallX':     (np.asarray(nozzle.xNozzleWall, dtype = float) - lipX) / lipRadius,
        'wallR':     np.asarray(nozzle.rNozzleWall, dtype = float) / lipRadius,
        'boundaryX': (np.asarray(field.boundaryX) - lipX) / lipRadius,
        'boundaryR': np.asarray(field.boundaryR) / lipRadius,
        'levels':    np.linspace(float(supersonic.min()), float(supersonic.max()), 160),
        'lipPressure': lipPressure, 'ambient': ambient, 'drift': field.massDriftWorst,
    }

#----------------------------------------------------------------------#
# -- Drawing -- #
#----------------------------------------------------------------------#

def render(scene: dict, size: tuple, orientation: str, reach: float, wallWidth: float,
           boundaryWidth: float, fadeLength: float, margin: float = 0.0) -> Image.Image:

    '''

    Draw the scene on a transparent canvas.

    Parameters:
    -----------
    scene : dict
        From `solveScene`.
    size : tuple
        Final image size, (width, height) [px].
    orientation : str
        'horizontal', flow left to right, or 'vertical', nozzle at the top and flow running down.
    reach : float
        Lip radii past the exit plane to show [-].
    wallWidth, boundaryWidth : float
        Line widths in the final image [px]. A boundary width of zero leaves the boundary undrawn.
    fadeLength : float
        Lip radii over which the plume fades out, ending a little short of `reach` [-].
    margin : float
        Clear border on every side, as a fraction of the shorter side [-].

    Returns:
    --------
    PIL.Image.Image : an RGBA image of `size`

    '''

    width, height = size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE
    dpi = 100.0
    pointsPerPixel = 72.0 / dpi

    def screen(axial, radial):
        # Data to screen axes: the flow runs along +x, or down along -y when vertical
        if orientation == 'horizontal':
            return np.asarray(axial), np.asarray(radial)
        return np.asarray(radial), -np.asarray(axial)

    # The wall and the plume boundary as one closed outline, injector face to the end of the plume
    wallX, wallR = scene['wallX'], scene['wallR']
    boundaryX, boundaryR = scene['boundaryX'], scene['boundaryR']
    upperX = np.concatenate([wallX, boundaryX])
    upperR = np.concatenate([wallR, boundaryR])
    outlineAxial = np.concatenate([upperX, upperX[::-1]])
    outlineRadial = np.concatenate([upperR, -upperR[::-1]])

    # Data extent along the flow and across it, fitted inside the canvas at equal aspect
    start, end = float(wallX.min()), reach
    halfWidth = 1.04 * max(float(np.abs(boundaryR[boundaryX <= reach]).max()), float(wallR.max()))
    spanU, spanV = ((end - start), 2.0 * halfWidth) if orientation == 'horizontal' else (2.0 * halfWidth, end - start)
    border = margin * min(width, height)
    scale = min((width - 2.0 * border) / spanU, (height - 2.0 * border) / spanV)    # [px per lip radius]
    if orientation == 'horizontal':
        centerU, centerV = 0.5 * (start + end), 0.0
    else:
        centerU, centerV = 0.0, -0.5 * (start + end)
    limitsU = (centerU - 0.5 * width / scale, centerU + 0.5 * width / scale)
    limitsV = (centerV - 0.5 * height / scale, centerV + 0.5 * height / scale)

    figure = plt.figure(figsize = (width / dpi, height / dpi), dpi = dpi)
    figure.patch.set_alpha(0.0)
    axes = figure.add_axes([0.0, 0.0, 1.0, 1.0])
    axes.set_axis_off()
    axes.patch.set_alpha(0.0)

    u, v = screen(np.concatenate([scene['axial'], scene['axial']]),
                  np.concatenate([scene['radial'], -scene['radial']]))
    shading = axes.tricontourf(u, v, np.concatenate([scene['mach'], scene['mach']]), levels = scene['levels'],
                               cmap = 'viridis', extend = 'both')
    clip = Polygon(np.column_stack(screen(outlineAxial, outlineRadial)), closed = True, transform = axes.transData,
                   facecolor = 'none', edgecolor = 'none')
    axes.add_patch(clip)
    shading.set_clip_path(clip)

    for sign in (1.0, -1.0):
        if boundaryWidth > 0.0:
            axes.plot(*screen(boundaryX, sign * boundaryR), color = boundaryInk, alpha = 0.8, zorder = 3,
                      lw = boundaryWidth * SUPERSAMPLE * pointsPerPixel)
        axes.plot(*screen(wallX, sign * wallR), color = copper, solid_capstyle = 'round', zorder = 4,
                  lw = wallWidth * SUPERSAMPLE * pointsPerPixel)

    axes.set_xlim(*limitsU)
    axes.set_ylim(*limitsV)

    figure.canvas.draw()
    pixels = np.asarray(figure.canvas.buffer_rgba()).astype(float)
    plt.close(figure)

    # Fade the plume out along the flow: opaque until the fade starts, clear a little short of the
    # end of what is shown, so no edge survives where the shading stops
    fadeEnd = reach - 0.08 * fadeLength
    fadeStart = fadeEnd - fadeLength
    if orientation == 'horizontal':
        axial = limitsU[0] + (np.arange(width) + 0.5) / scale
        ramp = np.clip((axial - fadeStart) / (fadeEnd - fadeStart), 0.0, 1.0)[np.newaxis, :]
    else:
        axial = -(limitsV[1] - (np.arange(height) + 0.5) / scale)
        ramp = np.clip((axial - fadeStart) / (fadeEnd - fadeStart), 0.0, 1.0)[:, np.newaxis]
    pixels[..., 3] *= 1.0 - ramp * ramp * (3.0 - 2.0 * ramp)              # smoothstep

    # Reduce with premultiplied alpha, so transparent pixels lend no color to the edges they border
    image = Image.fromarray(np.round(pixels).astype(np.uint8), 'RGBA').convert('RGBa')

    return image.resize(size, Image.LANCZOS).convert('RGBA')

#----------------------------------------------------------------------#
# -- The images -- #
#----------------------------------------------------------------------#

def horizontalSize(scene: dict, height: int, reach: float) -> tuple:

    '''The width a horizontal image needs at a given height to show the scene edge to edge.'''

    halfWidth = 1.04 * max(float(np.abs(scene['boundaryR'][scene['boundaryX'] <= reach]).max()),
                           float(scene['wallR'].max()))

    return int(round(height * (reach - float(scene['wallX'].min())) / (2.0 * halfWidth))), height

def build() -> list:

    '''

    Solve once and write every image.

    Returns:
    --------
    list : the paths written

    '''

    scene = solveScene()
    os.makedirs(os.path.join(assetFolder, 'icon'), exist_ok = True)
    written = []

    graphicHeight = horizontalSize(scene, 1000, REACH)
    graphic = render(scene, (3200, int(round(3200 * graphicHeight[1] / graphicHeight[0]))), 'horizontal', REACH,
                     wallWidth = 7.0, boundaryWidth = 3.0, fadeLength = 1.1)
    written.append(os.path.join(assetFolder, 'plumeGraphic.png'))
    graphic.save(written[-1])

    # Shrunk to a banner about 30 to 60 px tall, these widths land near 1.5 px for the wall
    banner = render(scene, horizontalSize(scene, 192, REACH), 'horizontal', REACH,
                    wallWidth = 7.0, boundaryWidth = 3.5, fadeLength = 1.1)
    written.append(os.path.join(assetFolder, 'plumeBanner.png'))
    banner.save(written[-1])

    # Each icon at its own size, the wall never thinner than a pixel. The boundary line is left out:
    # on a shape this small it reads as a halo where the plume fades.
    frames = []
    for size in ICONSIZES:
        frame = render(scene, (size, size), 'vertical', ICONREACH, wallWidth = max(1.0, size / 36.0),
                       boundaryWidth = 0.0, fadeLength = 0.9, margin = 0.03)
        written.append(os.path.join(assetFolder, 'icon', f'icon{size}.png'))
        frame.save(written[-1])
        frames.append(frame)

    # BMP entries rather than PNG, because Tk's own .ico reader parses the bitmap header
    written.append(os.path.join(assetFolder, 'nova.ico'))
    frames[-1].save(written[-1], format = 'ICO', sizes = [(size, size) for size in ICONSIZES],
                    append_images = frames[:-1], bitmap_format = 'bmp')

    print(f'  lip static pressure {scene["lipPressure"]:.0f} Pa, ambient {scene["ambient"]:.0f} Pa '
          f'at lip ratio {LIPRATIO:.2f}')
    print(f'  mass continuity error {scene["drift"]:+.2f} % at {REACH:.0f} lip radii')
    print(f'  Mach {scene["levels"][0]:.2f} to {scene["levels"][-1]:.2f}')
    for path in written:
        with Image.open(path) as image:
            print(f'  wrote {os.path.relpath(path, root)}, {image.size[0]} x {image.size[1]} px')

    return written

if __name__ == '__main__':
    build()
