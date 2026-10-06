# -- Digitizer for the 40k calorimeter figures -- #

'''

Reads the measured heat flux and heat transfer coefficient of the MSFC 40k calorimeter chamber, RPA's
predicted heat flux and RPA's chamber wall off their published figures, and prints the arrays
`tests/calorimeter40kCase.py` carries.

Two sources, each read from the image embedded in its PDF at native resolution:

    Dexter, Fisher, Hulka, Denisov, Shibanov and Agarkov, "Scaling Techniques for Design,
    Development, and Test", Progress in Astronautics and Aeronautics Vol. 200, AIAA, 2004, page
    589: Fig. 11, the heat flux of Test 024, and Fig. 12, its heat transfer coefficient
    A. Ponomarenko, "RPA: Tool for Rocket Propulsion Analysis. Thermal Analysis of Thrust
    Chambers", 2012, page 23: Figure 14, RPA's prediction for the same test and the wall it built

The figures are not reproduced in the repository, only the numbers read off them.

The measurement, Figs. 11 and 12
--------------------------------

A scanned page, 1806 by 2704 pixels. Each figure's markers are filled circles about 14 pixels
across, joined by a line. Dark pixels are opened with a disk of radius 6, which removes the joining
lines, the gridlines and Fig. 12's open circles (the data scaled to another pressure) and keeps the
filled markers. Blobs larger than one marker are touching pairs or triples, split by k-means with as
many centres as their area holds markers. Centroids are mapped to data piecewise-linearly between
the gridlines, which absorbs the scan's distortion.

Fig. 11 returns the 58 markers of the 58 coolant circuits. Fig. 12's filled markers sit at the same
stations, and two annotation arrowheads survive the opening as marker-sized blobs, so each Fig. 11
station takes the Fig. 12 blob nearest it in axial position, choosing between two by which fits the
local ratio of coefficient to flux. The arrowheads are the two left over.

Calibration is good to about one pixel against the gridlines: 0.05 cm axially, 0.1 BTU/s-in^2 of
heat flux and 3e-5 BTU/in^2-s-F of coefficient. The reading agrees with the same measurement as RPA's
paper reproduces it, a smaller scan, to 0.14 cm and 0.27 BTU/s-in^2.

RPA's prediction, Figure 14
---------------------------

A screenshot of RPA's plot, 1024 by 630 pixels, rendered without resampling. The heat flux is pure
red with antialiased edges and the wall is neutral grey to black, so the two separate by colour.
Each column's position is the intensity-weighted centroid of the curve's pixels in it, with the black
dotted major gridlines masked by row and column. Calibration is from the tick marks: 1.2883 pixels per
millimetre axially, 4.99 pixels per MW/m^2 and 0.770 pixels per millimetre of radius. The wall is
fitted with a least-squares cubic spline on knots 6 mm apart, which resolves the throat arc and
removes the staircase of RPA's station polyline: a throat radius of 42.3 mm, a contraction ratio of
2.91 and an expansion ratio of 7.06, against 42.05 mm, 2.92 and 7 for the hardware.

Usage, from the NOVA root:

    python featureShowcase/digitizeCalorimeter40k.py <Dexter chapter PDF> <RPA thermal paper PDF> [overlay dir]

The optional directory receives overlays of every digitized point on its figure.

Author: Sean Bowman

'''

import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.cluster.vq import kmeans2
from scipy.interpolate import LSQUnivariateSpline

# The scanned page, by its native size, and RPA's figure
dexterPageSize      = (1806, 2704)
predictionImageSize = (1024, 630)

# -- Dexter page 589 calibration: gridline pixel against data value -- #
fluxGridX = np.array([(-40, 304.0), (-35, 403.5), (-30, 501.5), (-25, 598.0), (-20, 698.5), (-15, 795.0),
                      (-10, 895.0), (-5, 992.0), (0, 1089.5), (5, 1185.5), (10, 1284.5), (15, 1388.0)])     # [cm], [px]
fluxGridY = np.array([(60, 314.5), (55, 367.0), (50, 421.0), (45, 471.5), (40, 524.5), (35, 577.0), (30, 628.0),
                      (25, 681.5), (20, 733.0), (15, 785.5), (10, 838.0), (5, 888.5), (0, 937.5)])           # [BTU/s-in^2], [px]
coefficientGridX = np.array([(-40, 328.5), (-35, 428.5), (-30, 530.5), (-25, 627.0), (-20, 723.0), (-15, 820.0),
                             (-10, 921.5), (-5, 1018.5), (0, 1117.5), (5, 1215.5), (10, 1319.5), (15, 1420.5)])
coefficientGridY = np.array([(0.020, 1635.5), (0.016, 1769.0), (0.014, 1836.5), (0.012, 1902.5), (0.010, 1968.0),
                             (0.008, 2035.0), (0.006, 2101.0), (0.004, 2168.5), (0.002, 2232.0), (0.0, 2307.0)])  # [BTU/in^2-s-F]
fluxRegion        = (320, 935, 310, 1385)       # rows and columns inside Fig. 11's frame
coefficientRegion = (1640, 2300, 335, 1415)     # and Fig. 12's

# -- Figure 14 calibration, from its tick marks -- #
predictionXPixels      = (109.0, 882.0)       # 0 and 600 mm
predictionFluxPixels   = (542.0, 43.0)        # 0 and 100 000 kW/m^2
predictionRadiusPixels = (542.0, 80.0)        # 0 and 600 mm
predictionMajorGridRows = (43, 143, 243, 342, 442, 542)
predictionMajorGridCols = (109, 238, 367, 495, 624, 753, 882)

def embeddedImage(pdfPath: str, pageIndex: int, size: tuple) -> np.ndarray:

    '''

    The image of a given native size embedded on a page, as a float array.

    Raises:
    -------
    ValueError
        If the page carries no image of that size, which means a different edition or scan.

    '''

    import fitz

    document = fitz.open(pdfPath)
    page = document[pageIndex]
    for info in page.get_images(full = True):
        pixmap = fitz.Pixmap(document, info[0])
        if (pixmap.width, pixmap.height) != size:
            continue
        if pixmap.n not in (1, 3):
            pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
        array = np.frombuffer(pixmap.samples, dtype = np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
        return array.astype(float)
    raise ValueError(f'No {size[0]} by {size[1]} image on page {pageIndex + 1} of {pdfPath}; '
                     'this is not the edition the calibration was read from.')

def mapAxis(pixels, grid: np.ndarray) -> np.ndarray:

    '''

    Pixels to data, piecewise-linearly between the gridlines.

    '''

    order = np.argsort(grid[:, 1])

    return np.interp(pixels, grid[order, 1], grid[order, 0])

def filledMarkers(grey: np.ndarray, region: tuple, radius: int = 6) -> tuple:

    '''

    Centres of the filled circular markers inside a region of a scanned page.

    Returns:
    --------
    tuple : (centres as an (n, 2) array of column and row sorted by column, every blob's area)

    '''

    def disk(size):
        y, x = np.mgrid[-size:size + 1, -size:size + 1]
        return x * x + y * y <= size * size

    rowStart, rowEnd, columnStart, columnEnd = region
    opened = ndimage.binary_opening(grey < 128.0, structure = disk(radius))
    inside = np.zeros_like(opened)
    inside[rowStart:rowEnd, columnStart:columnEnd] = True
    opened &= inside

    labels, count = ndimage.label(opened)
    areas = np.asarray(ndimage.sum(opened, labels, range(1, count + 1)))
    singleArea = float(np.median(areas))
    centres = []
    for label in range(1, count + 1):
        rows, columns = np.nonzero(labels == label)
        points = np.column_stack([columns, rows]).astype(float)
        markers = max(1, int(round(areas[label - 1] / singleArea)))
        if markers == 1:
            centres.append(points.mean(axis = 0))
            continue
        # Seeds spread along the blob, so the split is the same on every run
        order = np.argsort(points[:, 0] + 1e-3 * points[:, 1])
        seeds = np.array([points[order[int((j + 0.5) * len(order) / markers)]] for j in range(markers)])
        split, _ = kmeans2(points, seeds, minit = 'matrix', iter = 50)
        centres.extend(split)

    return np.array(sorted(centres, key = lambda centre: centre[0])), areas

def digitizeMeasurement(page: np.ndarray) -> tuple:

    '''

    Test 024's heat flux and heat transfer coefficient at the 58 coolant circuits.

    Returns:
    --------
    tuple : (data, fluxPixels, coefficientPixels) where data is a (58, 3) array of [cm from the
        throat, BTU/s-in^2, BTU/in^2-s-F]

    '''

    grey = page[..., 0] if page.ndim == 3 else page
    fluxPixels, _ = filledMarkers(grey, fluxRegion)
    coefficientBlobs, _ = filledMarkers(grey, coefficientRegion)

    stations = mapAxis(fluxPixels[:, 0], fluxGridX)
    flux = mapAxis(fluxPixels[:, 1], fluxGridY)
    blobStation = mapAxis(coefficientBlobs[:, 0], coefficientGridX)
    blobCoefficient = mapAxis(coefficientBlobs[:, 1], coefficientGridY)

    # Each station takes the coefficient blob nearest it; where two compete, the one that fits the
    # ratio of coefficient to flux its unambiguous neighbours carry
    candidates = [np.flatnonzero(np.abs(blobStation - station) < 0.4) for station in stations]
    ratio = np.array([blobCoefficient[c[0]] / f if len(c) == 1 else np.nan for c, f in zip(candidates, flux)])
    known = ~np.isnan(ratio)
    chosen = []
    for station, value, candidate in zip(stations, flux, candidates):
        if len(candidate) == 0:
            raise ValueError(f'No Fig. 12 marker at the Fig. 11 station {station:.2f} cm.')
        expected = value * np.interp(station, stations[known], ratio[known])
        chosen.append(int(candidate[np.argmin(np.abs(blobCoefficient[candidate] - expected))]))

    data = np.column_stack([stations, flux, blobCoefficient[chosen]])

    return data, fluxPixels, coefficientBlobs[chosen]

def digitizePrediction(image: np.ndarray) -> tuple:

    '''

    RPA's heat flux and wall from its Figure 14, column by column.

    Returns:
    --------
    tuple : (flux, contour), each an (n, 2) array: [mm from injector, kW/m^2] and
        [mm from injector, mm of radius]

    '''

    red, green, blue = image[..., 0], image[..., 1], image[..., 2]
    rows = np.arange(image.shape[0], dtype = float)

    axialScale  = (predictionXPixels[1] - predictionXPixels[0]) / 600.0
    fluxScale   = (predictionFluxPixels[0] - predictionFluxPixels[1]) / 100000.0
    radiusScale = (predictionRadiusPixels[0] - predictionRadiusPixels[1]) / 600.0

    # Red curve: saturated red with equal green and blue, weighted by distance from white
    isRed = (red > 250.0) & (np.abs(green - blue) < 1.0) & (green < 250.0)
    redWeight = np.where(isRed, 255.0 - green, 0.0)
    redWeight[:36, :] = 0.0
    redWeight[546:, :] = 0.0

    # Wall: neutral grey to black, minus the black dotted major gridlines
    isNeutral = (np.abs(red - green) < 1.0) & (np.abs(green - blue) < 1.0) & (red < 250.0)
    greyWeight = np.where(isNeutral, 255.0 - red, 0.0)
    for row in predictionMajorGridRows:
        greyWeight[row, :] = 0.0
    for column in predictionMajorGridCols:
        greyWeight[:, column] = 0.0
    greyWeight[:430, :] = 0.0
    greyWeight[545:, :] = 0.0

    flux, contour = [], []
    for column in range(111, 950):
        axial = (column - predictionXPixels[0]) / axialScale
        weight = redWeight[:, column]
        if weight.sum() > 0.0:
            row = float((weight * rows).sum() / weight.sum())
            flux.append((axial, (predictionFluxPixels[0] - row) / fluxScale))
        weight = greyWeight[:, column]
        if column not in predictionMajorGridCols and weight.sum() > 0.0:
            row = float((weight * rows).sum() / weight.sum())
            contour.append((axial, (predictionRadiusPixels[0] - row) / radiusScale))

    return np.array(flux), np.array(contour)

def smoothContour(contour: np.ndarray, knotSpacing: float = 6.0) -> LSQUnivariateSpline:

    '''

    Least-squares cubic spline through the digitized wall.

    A global smoothing spline rounds the throat off by more than a millimetre, because the throat
    arc is the shortest feature on the wall. Fixed knots 6 mm apart resolve it and still remove the
    staircase of RPA's station polyline.

    Returns:
    --------
    scipy.interpolate.LSQUnivariateSpline : radius [mm] against axial position [mm]

    '''

    axial, radius = contour[:, 0], contour[:, 1]
    knots = np.arange(axial.min() + knotSpacing, axial.max() - knotSpacing / 2.0, knotSpacing)

    return LSQUnivariateSpline(axial, radius, knots, k = 3)

def formatRows(rows, decimals: tuple, perLine: int = 6) -> str:

    '''

    Rows of numbers as Python tuple literals, several to a line.

    '''

    cells = ['(' + ', '.join(f'{value:.{places}f}' for value, places in zip(row, decimals)) + ')' for row in rows]
    lines = [', '.join(cells[i:i + perLine]) for i in range(0, len(cells), perLine)]

    return ',\n'.join('    ' + line for line in lines)

def writeOverlays(page: np.ndarray, fluxPixels: np.ndarray, coefficientPixels: np.ndarray,
                  predictionImage: np.ndarray, spline: LSQUnivariateSpline, folder: str) -> None:

    '''

    Every digitized point drawn back onto its figure, for checking by eye.

    '''

    os.makedirs(folder, exist_ok = True)

    grey = page[..., 0] if page.ndim == 3 else page
    image = Image.fromarray(grey.astype(np.uint8)).convert('RGB')
    draw = ImageDraw.Draw(image)
    for column, row in np.vstack([fluxPixels, coefficientPixels]):
        draw.ellipse((column - 7, row - 7, column + 7, row + 7), outline = (255, 0, 200), width = 3)
    image.crop((280, 290, 1440, 2330)).save(os.path.join(folder, 'measurementOverlay.png'))

    image = Image.fromarray(predictionImage.astype(np.uint8))
    draw = ImageDraw.Draw(image)
    axialScale  = (predictionXPixels[1] - predictionXPixels[0]) / 600.0
    radiusScale = (predictionRadiusPixels[0] - predictionRadiusPixels[1]) / 600.0
    axial = np.linspace(0.0, 650.0, 3000)
    draw.line([(predictionXPixels[0] + a * axialScale, predictionRadiusPixels[0] - r * radiusScale)
               for a, r in zip(axial, spline(axial))], fill = (0, 160, 255), width = 1)
    crop = image.crop((440, 440, 700, 548))
    crop.resize((crop.width * 6, crop.height * 6), Image.NEAREST).save(os.path.join(folder, 'contourOverlay.png'))

def main(dexterPath: str, rpaPath: str, overlayFolder: str = None) -> None:

    '''

    Digitize the figures and print the arrays the case module carries.

    '''

    page = embeddedImage(dexterPath, 36, dexterPageSize)
    measured, fluxPixels, coefficientPixels = digitizeMeasurement(page)
    prediction = embeddedImage(rpaPath, 22, predictionImageSize)
    flux, contour = digitizePrediction(prediction)
    spline = smoothContour(contour)

    # RPA's flux every 5 mm and its wall every 2.5 mm, from the injector face to the exit. The
    # barrel is flat, so the wall's first point is held back to the face.
    fluxStations = np.arange(0.0, 650.0 + 1e-9, 5.0)
    fluxSampled = np.interp(fluxStations, flux[:, 0], flux[:, 1])
    wallStations = np.arange(0.0, 650.0 + 1e-9, 2.5)
    wallSampled = spline(np.clip(wallStations, contour[0, 0], contour[-1, 0]))

    residual = contour[:, 1] - spline(contour[:, 0])
    fine = np.linspace(contour[0, 0], contour[-1, 0], 4000)
    throat = float(spline(fine).min())
    print(f'# {len(measured)} stations; wall fit {residual.std():.3f} mm RMS; throat {throat:.2f} mm; '
          f'CR {(float(spline(150.0)) / throat)**2:.3f}; ER {(float(spline(fine[-1])) / throat)**2:.3f}')
    print('measuredProfile = (\n' + formatRows(measured, (2, 2, 5), perLine = 4) + ')\n')
    print('rpaFlux = (\n' + formatRows(zip(fluxStations, fluxSampled), (1, 0)) + ')\n')
    print('rpaContour = (\n' + formatRows(zip(wallStations, wallSampled), (1, 2)) + ')')

    if overlayFolder:
        writeOverlays(page, fluxPixels, coefficientPixels, prediction, spline, overlayFolder)

if __name__ == '__main__':

    if len(sys.argv) < 3:
        raise SystemExit('Usage: python featureShowcase/digitizeCalorimeter40k.py <Dexter chapter PDF> '
                         '<RPA thermal paper PDF> [overlay dir]')
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
