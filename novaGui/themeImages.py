# -- NOVA GUI Theme Images -- #

'''

The images the rounded ttk elements are built from, drawn with Pillow for one palette mode at the
display's scale.

ttk has no border radius, so a rounded control is an image element: a small picture whose middle
ttk tiles to the widget's size and whose border it keeps intact, the nine-slice scheme. Tiling
only looks right on a flat fill, which is what the Engineering Flat Metal palette asks for anyway:
no gradients, no glows. Each picture is drawn at four times its size and reduced with a box filter
in premultiplied alpha, so its curved edges are antialiased without the ringing a sharper filter
leaves on a flat edge.

Every picture is flattened onto the color of the container it sits on, its ground, so it has no
transparency left. Tk 8.6 on Windows draws a photo image with partial transparency by reading the
screen back and blending it in software, on every expose; an opaque one is a plain copy. On the
Design form that blend was two thirds of the cost of a scroll step. A ground is a fixed color, so
an element that appears on two containers has an image for each, and `theme.py` registers each
under its container prefix ('' on the page, 'Card' on a card, 'Header' on the header).

The pictures behind controls and cards are also drawn wide. ttk fills a widget by tiling the
middle once per middle-width, and each tile is a separate draw: a field one tile wide draws in a
fraction of the time of one five tiles wide. They are widened by stretching the flat middle and
edges of a small drawing (`_widen`), which is exact for a flat fill and avoids supersampling a
large picture.

`buildImages` returns every image a mode needs as Tk PhotoImages, keyed by role. They are kept
referenced on the Tk root, because an image element whose picture is collected draws nothing.

Author: Sean Bowman

'''

import json
import math
import os

from PIL import Image, ImageDraw, ImageTk

supersample = 4

assetFolder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')

#----------------------------------------------------------------------#
# -- Drawing primitives -- #
#----------------------------------------------------------------------#

def _rgba(color: str, alpha: int = 255) -> tuple:

    color = color.lstrip('#')

    return tuple(int(color[index:index + 2], 16) for index in (0, 2, 4)) + (alpha,)

def _flatten(image: Image.Image, ground: str) -> Image.Image:

    '''An image composited onto a solid ground color, with no transparency left.'''

    flat = Image.new('RGBA', image.size, _rgba(ground))
    flat.alpha_composite(image.convert('RGBA'))

    return flat.convert('RGB')

def _widen(image: Image.Image, border, width: int, height: int) -> Image.Image:

    '''

    A nine-slice picture at a larger size: corners kept, edges and middle stretched. Exact for a
    picture whose edges are uniform along their length and whose middle is one color, which every
    flat rounded rectangle here is.

    Parameters:
    -----------
    image : PIL.Image.Image
        The small drawing.
    border : int or tuple
        The nine-slice border, one value or (left, top, right, bottom) [px].
    width, height : int
        The size wanted [px]; a size smaller than the drawing's keeps the drawing's.

    '''

    left, top, right, bottom = (border,) * 4 if isinstance(border, int) else border
    sourceWidth, sourceHeight = image.size
    width, height = max(width, sourceWidth), max(height, sourceHeight)

    columns = ((0, left, 0, left), (left, sourceWidth - right, left, width - right),
               (sourceWidth - right, sourceWidth, width - right, width))
    rows = ((0, top, 0, top), (top, sourceHeight - bottom, top, height - bottom),
            (sourceHeight - bottom, sourceHeight, height - bottom, height))

    wide = Image.new(image.mode, (width, height))
    for sourceLeft, sourceRight, left0, right0 in columns:
        for sourceTop, sourceBottom, top0, bottom0 in rows:
            piece = image.crop((sourceLeft, sourceTop, sourceRight, sourceBottom))
            if piece.size != (right0 - left0, bottom0 - top0):
                piece = piece.resize((right0 - left0, bottom0 - top0), Image.NEAREST)
            wide.paste(piece, (left0, top0))

    return wide

def _reduce(image: Image.Image) -> Image.Image:

    '''Reduce a supersampled drawing to its final size in premultiplied alpha.'''

    return image.convert('RGBa').reduce(supersample).convert('RGBA')

def roundedRect(width: int, height: int, radius: int, fill: str = None, border: str = None,
                borderWidth: int = 1, inset: tuple = (0, 0, 0, 0)) -> Image.Image:

    '''

    A flat rounded rectangle on a transparent ground.

    Parameters:
    -----------
    width, height : int
        Final size [px].
    radius : int
        Corner radius [px].
    fill, border : str
        Hex colors; None leaves that part transparent.
    borderWidth : int
        Border width [px].
    inset : tuple
        Transparent margin left, top, right, bottom [px], for a shape that must not touch its
        neighbor (scrollbar thumbs, tab pills).

    '''

    size = (width * supersample, height * supersample)
    image = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = (value * supersample for value in inset)
    box = [left, top, size[0] - 1 - right, size[1] - 1 - bottom]
    corner = radius * supersample

    if border is not None:
        draw.rounded_rectangle(box, corner, fill = _rgba(border))
        step = borderWidth * supersample
        box = [box[0] + step, box[1] + step, box[2] - step, box[3] - step]
        corner = max(0, corner - step)
    if fill is not None:
        draw.rounded_rectangle(box, corner, fill = _rgba(fill))
    elif border is not None:
        # A border with no fill: cut the middle back out
        draw.rounded_rectangle(box, corner, fill = (0, 0, 0, 0))

    return _reduce(image)

def checkbox(size: int, fill: str, border: str, mark: str = None, dash: bool = False,
             gap: int = 0) -> Image.Image:

    '''

    A rounded square check indicator, with a check mark or a dash, and a transparent gap on its
    right so the label does not touch it.

    '''

    box = roundedRect(size, size, max(2, size // 4), fill, border)
    if mark is not None:
        large = Image.new('RGBA', (size * supersample, size * supersample), (0, 0, 0, 0))
        draw = ImageDraw.Draw(large)
        scale = size * supersample
        width = max(supersample, int(0.13 * scale))
        if dash:
            draw.line([(0.28 * scale, 0.5 * scale), (0.72 * scale, 0.5 * scale)], fill = _rgba(mark), width = width)
        else:
            draw.line([(0.26 * scale, 0.52 * scale), (0.43 * scale, 0.69 * scale), (0.75 * scale, 0.33 * scale)],
                      fill = _rgba(mark), width = width, joint = 'curve')
        box.alpha_composite(_reduce(large))

    if gap:
        padded = Image.new('RGBA', (size + gap, size), (0, 0, 0, 0))
        padded.paste(box, (0, 0))
        return padded

    return box

def chevron(size: int, color: str) -> Image.Image:

    '''A small downward chevron for the combobox and spinbox arrows.'''

    large = Image.new('RGBA', (size * supersample, size * supersample), (0, 0, 0, 0))
    draw = ImageDraw.Draw(large)
    scale = size * supersample
    draw.line([(0.28 * scale, 0.40 * scale), (0.50 * scale, 0.62 * scale), (0.72 * scale, 0.40 * scale)],
              fill = _rgba(color), width = max(supersample, int(0.11 * scale)), joint = 'curve')

    return _reduce(large)

def infoIcon(size: int, color: str) -> Image.Image:

    '''A ringed lowercase i, the field help marker.'''

    large = Image.new('RGBA', (size * supersample, size * supersample), (0, 0, 0, 0))
    draw = ImageDraw.Draw(large)
    scale = size * supersample
    ring = max(supersample, int(0.09 * scale))
    draw.ellipse([ring / 2, ring / 2, scale - 1 - ring / 2, scale - 1 - ring / 2], outline = _rgba(color), width = ring)
    stem = max(supersample, int(0.12 * scale))
    draw.line([(scale / 2, 0.44 * scale), (scale / 2, 0.74 * scale)], fill = _rgba(color), width = stem)
    dot = 0.075 * scale
    draw.ellipse([scale / 2 - dot, 0.27 * scale - dot, scale / 2 + dot, 0.27 * scale + dot], fill = _rgba(color))

    return _reduce(large)

def sunIcon(size: int, color: str) -> Image.Image:

    '''A sun: shown in dark mode, where it offers the light theme.'''

    large = Image.new('RGBA', (size * supersample, size * supersample), (0, 0, 0, 0))
    draw = ImageDraw.Draw(large)
    scale = size * supersample
    center, core = scale / 2, 0.2 * scale
    draw.ellipse([center - core, center - core, center + core, center + core], fill = _rgba(color))
    width = max(supersample, int(0.08 * scale))
    for index in range(8):
        angle = index * math.pi / 4
        inner, outer = 0.31 * scale, 0.45 * scale
        draw.line([(center + inner * math.cos(angle), center + inner * math.sin(angle)),
                   (center + outer * math.cos(angle), center + outer * math.sin(angle))],
                  fill = _rgba(color), width = width)

    return _reduce(large)

def moonIcon(size: int, color: str) -> Image.Image:

    '''A crescent moon: shown in light mode, where it offers the dark theme.'''

    large = Image.new('RGBA', (size * supersample, size * supersample), (0, 0, 0, 0))
    draw = ImageDraw.Draw(large)
    scale = size * supersample
    draw.ellipse([0.14 * scale, 0.14 * scale, 0.86 * scale, 0.86 * scale], fill = _rgba(color))
    draw.ellipse([0.34 * scale, 0.04 * scale, 1.06 * scale, 0.76 * scale], fill = (0, 0, 0, 0))

    return _reduce(large)

#----------------------------------------------------------------------#
# -- The nozzle glyph -- #
#----------------------------------------------------------------------#

def _nozzleOutline() -> tuple:

    '''

    The shipped nozzle's wall as (axial, radial) points, injector face to lip, normalized so the
    lip radius is one and the length runs 0 to 1, with the length in lip radii. Read from the
    outline `buildGuiGraphic.py` writes; a drawn bell stands in when that file is absent.

    Returns:
    --------
    tuple : (points, length in lip radii)

    '''

    path = os.path.join(assetFolder, 'nozzleOutline.json')
    try:
        with open(path, encoding = 'utf-8') as handle:
            data = json.load(handle)
        points = [tuple(point) for point in data['points']]
        if len(points) > 4:
            return points, float(data.get('lengthInLipRadii', 3.6))
    except (OSError, ValueError, KeyError, TypeError):
        pass

    # Chamber, contraction, throat and bell, in the same normalization
    outline = [(0.00, 0.32), (0.12, 0.32), (0.18, 0.24), (0.22, 0.17), (0.25, 0.16)]
    for index in range(1, 13):
        fraction = index / 12
        outline.append((0.25 + 0.75 * fraction, 0.16 + 0.84 * fraction**0.6))

    return outline, 3.6

def nozzleGlyph(size: int, color: str, vertical: bool = False) -> Image.Image:

    '''

    A filled silhouette of the nozzle at its own proportions, the collapsible-section marker: flow
    to the right when a section is closed, flow down when it is open, as a disclosure triangle
    turns. The throat is kept at least half a pixel wide at the final size so it does not pinch
    shut.

    '''

    outline, length = _nozzleOutline()
    large = size * supersample
    margin = 0.04 * large
    span = large - 2 * margin                              # the nozzle's length across the box
    lipRadius = span / max(length, 2.0)                    # one lip radius at the same scale
    minimumHalf = 0.5 * supersample

    upper = [(margin + axial * span, large / 2 - max(radial * lipRadius, minimumHalf)) for axial, radial in outline]
    lower = [(margin + axial * span, large / 2 + max(radial * lipRadius, minimumHalf)) for axial, radial in reversed(outline)]

    image = Image.new('RGBA', (large, large), (0, 0, 0, 0))
    ImageDraw.Draw(image).polygon(upper + lower, fill = _rgba(color))
    if vertical:
        image = image.rotate(-90, resample = Image.BICUBIC)

    return _reduce(image)

#----------------------------------------------------------------------#
# -- One mode's image set -- #
#----------------------------------------------------------------------#

def _mix(first: str, second: str, fraction: float) -> str:

    '''A flat blend of two hex colors, the second weighted by fraction.'''

    a, b = _rgba(first), _rgba(second)

    return '#' + ''.join(f'{round(a[index] + (b[index] - a[index]) * fraction):02X}' for index in range(3))

def _sizes(scale: float) -> dict:

    '''

    The dimensions every image is drawn to at a display scale.

    ttk fills a widget larger than an image element by tiling the image's middle, so a small
    middle makes a large widget slow to draw: a tall card tiled from a two pixel middle is drawn
    from hundreds of thousands of tiles on every expose, which stalls the window. Each image is
    therefore drawn with a generous middle, and the element is given its own small minimum size
    (`elementBorders`), so a control is not held to the size of its picture.

    '''

    def px(value: float) -> int:
        return max(1, int(round(value * scale)))

    control, card = px(6), px(10)

    return {'px': px, 'control': control, 'card': card, 'line': max(1, int(scale)),
            'side': 2 * (control + 1) + px(64), 'cardSide': 2 * (card + 1) + px(160),
            'controlWide': px(560), 'navWide': px(320), 'cardWide': (px(1400), px(480)),
            'tabPadX': px(4), 'tabPadY': px(2), 'barWidth': px(48), 'barHeight': px(8)}

def elementBorders(scale: float) -> dict:

    '''

    The nine-slice border each element is registered with, left, top, right, bottom [px], and the
    smallest size each may take, in step with the sizes `drawImages` draws at the same scale.

    '''

    sizes = _sizes(scale)
    px, corner, cardCorner = sizes['px'], sizes['control'] + 1, sizes['card'] + 1

    return {
        'control':        corner,
        'card':           cardCorner,
        'tab':            (corner + sizes['tabPadX'], corner + sizes['tabPadY'],
                           corner + sizes['tabPadX'], corner + sizes['tabPadY']),
        'bar':            (px(4), px(3), px(4), px(3)),
        'thumb':          px(4),
        'controlMinimum': 2 * corner + 2,
        'cardMinimum':    2 * cardCorner + 2,
        'tabMinimum':     (2 * (corner + sizes['tabPadX']) + 2, 2 * (corner + sizes['tabPadY']) + 2),
    }

def _role(prefix: str, name: str) -> str:

    '''An image role under a container prefix: thumb, cardThumb, headerThumb.'''

    return name if not prefix else prefix + name[0].upper() + name[1:]

def drawImages(colors: dict, scale: float) -> dict:

    '''

    Every image one mode needs, as Pillow images, keyed by role.

    Parameters:
    -----------
    colors : dict
        The mode's palette, as `theme.palettes[mode]`.
    scale : float
        The display scale over 96 dpi.

    Returns:
    --------
    dict : role -> PIL.Image.Image

    '''

    sizes = _sizes(scale)
    px, control, card, line = sizes['px'], sizes['control'], sizes['card'], sizes['line']
    side, cardSide = sizes['side'], sizes['cardSide']
    tabWidth, tabHeight = side + 2 * sizes['tabPadX'], side + 2 * sizes['tabPadY']
    tabInset = (sizes['tabPadX'], sizes['tabPadY'], sizes['tabPadX'], sizes['tabPadY'])
    barWidth, barHeight = sizes['barWidth'], sizes['barHeight']
    hover = _mix(colors['surface2'], colors['text'], 0.08)
    hoverHeader = _mix(colors['surface'], colors['text'], 0.06)

    bg, surface, surface2, edge = colors['bg'], colors['surface'], colors['surface2'], colors['border']
    borders = elementBorders(scale)
    cardWidth, cardHeight = sizes['cardWide']
    wideControl = (sizes['controlWide'], side, borders['control'])
    wideNav = (sizes['navWide'], side, borders['control'])
    wideCard = (cardWidth, cardHeight, borders['card'])

    def rect(fill, outline = None):
        return roundedRect(side, side, control, fill, outline, line)

    def thumb(fill, vertical = True):
        if vertical:
            return roundedRect(px(10), px(18), px(3), fill, None, inset = (px(2), px(1), px(2), px(1)))
        return roundedRect(px(18), px(10), px(3), fill, None, inset = (px(1), px(2), px(1), px(2)))

    def check(fill, outline, mark = None, dash = False):
        return checkbox(px(16), fill, outline, mark, dash = dash, gap = px(6))

    # Each drawing with the ground it is flattened onto (None keeps its transparency) and the size it
    # is widened to (None keeps its own). A family that appears on more than one container is drawn
    # once and flattened onto each.
    entries = []

    buttons = {'': rect(surface2, edge), '.active': rect(hover, edge), '.pressed': rect(edge, edge),
               '.disabled': rect(surface, edge)}
    for state, drawing in buttons.items():
        entries += [('button' + state, drawing, bg, wideControl),
                    ('cardButton' + state, drawing, surface, wideControl)]
    headerButtons = {'': rect(surface, edge), '.active': rect(hoverHeader, edge), '.pressed': rect(edge, edge)}
    for state, drawing in headerButtons.items():
        entries.append(('headerButton' + state, drawing, surface2, wideControl))
    accents = {'': rect(colors['accent'], colors['accent']), '.active': rect(colors['accentDim'], colors['accentDim']),
               '.disabled': rect(surface2, edge)}
    for state, drawing in accents.items():
        entries.append(('accent' + state, drawing, bg, wideControl))

    # Fields: filled with the card color on the page, with the page color on a card. A dropdown
    # arrow sits on the field's fill.
    for role, fill, ground in (('field', surface, bg), ('cardField', bg, surface)):
        entries += [(role, rect(fill, edge), ground, wideControl),
                    (role + '.hover', rect(fill, colors['textDim']), ground, wideControl),
                    (role + '.focus', rect(fill, colors['accent']), ground, wideControl),
                    (role + '.disabled', rect(ground, edge), ground, wideControl)]
    for role, ground in (('arrow', surface), ('cardArrow', bg)):
        entries += [(role, chevron(px(14), colors['textMuted']), ground, None),
                    (role + '.active', chevron(px(14), colors['accent']), ground, None)]

    # Cards on the page, and the inset panel inside a card
    entries += [('card', roundedRect(cardSide, cardSide, card, surface, edge, line), bg, wideCard),
                ('inset', roundedRect(cardSide, cardSide, card, bg, edge, line), surface, wideCard)]

    # Notebook tabs on the page and the View tab's navigation on its card: pills, with gaps around
    # the tabs so neighbors do not touch
    for state, fill in (('', None), ('.active', surface2), ('.selected', colors['accentMuted'])):
        entries += [('tab' + state, roundedRect(tabWidth, tabHeight, control, fill, None, inset = tabInset), bg, None),
                    ('nav' + state, roundedRect(side, side, control, fill, None), surface, wideNav)]

    # Progress bar trough and bar on the run bar, scrollbar thumbs on the page and on cards
    entries += [('trough', roundedRect(barWidth, barHeight, px(4), surface2, None), bg, None),
                ('bar', roundedRect(barWidth, barHeight, px(4), colors['accent'], None), bg, None)]
    for prefix, ground in (('', bg), ('card', surface)):
        for state, fill in (('', edge), ('.active', colors['textDim'])):
            entries += [(_role(prefix, 'thumb') + state, thumb(fill), ground, None),
                        (_role(prefix, 'hthumb') + state, thumb(fill, vertical = False), ground, None)]

    # Check indicators on the page, on cards and on the header
    checks = {'': check(bg, edge), '.active': check(bg, colors['accent']),
              '.selected': check(colors['accent'], colors['accent'], colors.get('onAccent', bg)),
              '.alternate': check(bg, edge, colors['textMuted'], dash = True), '.disabled': check(surface, edge)}
    for prefix, ground in (('', bg), ('card', surface), ('header', surface2)):
        for state, drawing in checks.items():
            entries.append((_role(prefix, 'check') + state, drawing, ground, None))

    # Icons on cards. The theme switch's icon keeps its transparency: it sits on a button whose fill
    # changes under the pointer, and it is one widget outside the form.
    entries += [('info', infoIcon(px(14), colors['textMuted']), surface, None),
                ('info.hover', infoIcon(px(14), colors['accent']), surface, None),
                ('glyph.closed', nozzleGlyph(px(18), colors['accent']), surface, None),
                ('glyph.open', nozzleGlyph(px(18), colors['accent'], vertical = True), surface, None),
                ('sun', sunIcon(px(18), colors['textMuted']), None, None),
                ('moon', moonIcon(px(18), colors['textMuted']), None, None)]

    images = {}
    for role, drawing, ground, wide in entries:
        if wide is not None:
            drawing = _widen(drawing, wide[2], wide[0], wide[1])
        images[role] = drawing if ground is None else _flatten(drawing, ground)

    return images

def buildImages(root, mode: str, colors: dict, scale: float) -> dict:

    '''

    One mode's images as Tk PhotoImages, kept referenced on the root.

    Returns:
    --------
    dict : role -> PhotoImage

    '''

    store = getattr(root, '_novaThemeImages', None)
    if store is None:
        store = {}
        root._novaThemeImages = store

    key = (mode, round(scale, 3))
    if key not in store:
        store[key] = {role: ImageTk.PhotoImage(image, master = root)
                      for role, image in drawImages(colors, scale).items()}

    return store[key]
