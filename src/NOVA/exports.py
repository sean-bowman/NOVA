# -- NOVA: Data Export -- #

'''

Writing a finished nozzle out in the forms other tools read.

Four kinds of thing come out of a run and each has its own consumer:

    contours      Text files of wall coordinates, in millimeters, which is what a CAD package
                  imports as a sketch.
    geometry      STL of the channels, the jacket, the shell and the volutes, for CAD and for
                  print preparation.
    exhaust       Near-wall gas properties along the wall, which is what a structural or thermal
                  analysis reads as a boundary condition.
    the run       The pickled nozzle, so a later session can reopen the result without re-solving.

Everything is written into the run's own output directory, which the nozzle resolves through
`_getOutputRoot`. Nothing is written beside the source.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Nothing here is a model.** Export can lose a field, change its units or write a file the
consumer cannot read; it cannot get physics wrong, because it computes nothing. The unit
conversions are the one thing worth checking and the tests check them: contours are written in
millimeters, the object is meter-based, and the factor between them appears once per array.

The exhaust property export writes what the one-dimensional station properties say, and those
carry the disclosure recorded in `regenStations`: they are not the near-wall state the
characteristics solve returns, and near the throat the two differ by up to 42 per cent in Mach
number. A structural analysis reading these files is reading the one-dimensional value.

All units are mass base SI on the object. Contour and geometry files are written in millimeters,
which is the convention CAD packages expect.

Author: Sean Bowman

'''

import os

import numpy as np

from .utils import py2cad, pickleObject, writeFile

def exportData(nozzle, filename: str = 'default'):

    '''

    Wrapper for exporting generated surface geometry and nozzle data.

    '''

    import __main__
    import shutil

    # Check for default inputs or user defined filenames
    if filename == 'default' and nozzle.filename is None:
        filename = 'default'
    elif nozzle.filename is not None:
        filename = nozzle.filename

    if filename == 'default' and nozzle.filename is None:
        filename = nozzle.dataFolder + '\\default.stl'
    elif nozzle.filename is not None:
        filename = nozzle.dataFolder + '\\' + nozzle.filename + '.stl'

    # Nozzle contours
    print(f'Writing Nozzle Contour(s) and Shell to .txt')
    hotWallRegenArray       = np.array([-nozzle.xRegenNozzle,np.zeros((len(nozzle.xRegenNozzle))),nozzle.rRegenNozzle]).T
    hotWallUntruncatedArray = np.array([-nozzle.xNozzleWall, np.zeros((len(nozzle.xNozzleWall))), nozzle.rNozzleWall ]).T
    writeFile(filename[:-4] + 'HotWallRegenContour.txt',       hotWallRegenArray*1e3)
    writeFile(filename[:-4] + 'HotWallUntruncatedContour.txt', hotWallUntruncatedArray*1e3)
    # The shell and channel geometry only exist when cooling channels were
    # generated, so a hot-wall-only run still produces a usable export.
    cooledGeometry = nozzle.makeCoolingChannels != 'off' and len(nozzle.xNozzleShell) > 0
    if cooledGeometry:
        shellRegenArray = np.array([-nozzle.xNozzleShell,np.zeros((len(nozzle.xNozzleShell))),nozzle.rNozzleShell]).T
        writeFile(filename[:-4] + 'ShellRegenContour.txt', shellRegenArray*1e3)

    # Chamber closure keep-out
    if nozzle.plotKeepOut == 'on' and nozzle.nozzleKeepOut is not None:
        keepOutArray = np.array([-nozzle.nozzleKeepOut.x,
                                 np.zeros(len(nozzle.nozzleKeepOut.x)),
                                 nozzle.nozzleKeepOut.r]).T
        writeFile(filename[:-4] + 'KeepOut.txt', keepOutArray*1e3)

    # Channels
    if cooledGeometry:
        print(f'Writing Channel Centerline to .txt and Surfaces to .stl')
        centerlineArray = np.array([nozzle.zChannelCenterline3D, nozzle.yChannelCenterline3D, nozzle.xChannelCenterline3D]).T
        writeFile(filename[:-4] + 'ChannelCenterline3D.txt', centerlineArray*1e3)
        py2cad(filename[:-4] + 'Channel.stl', nozzle.zChannel, nozzle.yChannel, -nozzle.xChannel)
        if nozzle.channelType == 'fluted':
            py2cad(filename[:-4] + 'DefeaturedChannel.stl', nozzle.zChannelDefeatured, nozzle.yChannelDefeatured, -nozzle.xChannelDefeatured)

    # Volutes
    if nozzle.makeInletVolute == 'on':
        print(f'Exporting Inlet Volute Surface Mesh to .stl')
        py2cad(filename[:-4] + 'InletVolute.stl', nozzle.xInletVolute, nozzle.yInletVolute, nozzle.zInletVolute)
        if nozzle.inletVolute.wallThickness is not None:
            print(f'Exporting Inlet Volute Shell Surface Mesh to .stl')
            py2cad(filename[:-4] + 'InletVoluteShell.stl', nozzle.xInletVoluteShell, nozzle.yInletVoluteShell, nozzle.zInletVoluteShell)
        if nozzle.inletVolute.circlePrintability == 'thick' or nozzle.inletVolute.circlePrintability == 'thin':
            print(f'Exporting Inlet Volute Print Supports to .stl')
            py2cad(filename[:-4] + 'InletVolutePrintSupportsWall.stl', nozzle.xInletVoluteSupportWall, nozzle.yInletVoluteSupportWall, nozzle.zInletVoluteSupportWall)
            py2cad(filename[:-4] + 'InletVolutePrintSupportsUpper.stl', nozzle.xInletVoluteSupportUpper, nozzle.yInletVoluteSupportUpper, nozzle.zInletVoluteSupportUpper)
            if nozzle.inletVolute.circlePrintability == 'thick':
                py2cad(filename[:-4] + 'InletVolutePrintSupportsLower.stl', nozzle.xInletVoluteSupportLower, nozzle.yInletVoluteSupportLower, nozzle.zInletVoluteSupportLower)
    if nozzle.makeReturnVolute == 'on':
        print(f'Exporting Return Volute Surface Mesh to .stl')
        py2cad(filename[:-4] + 'ReturnVolute.stl', nozzle.xReturnVolute, nozzle.yReturnVolute, nozzle.zReturnVolute)
        if nozzle.inletVolute.wallThickness is not None:
            print(f'Exporting Return Volute Shell Surface Mesh to .stl')
            py2cad(filename[:-4] + 'ReturnVoluteShell.stl', nozzle.xReturnVoluteShell, nozzle.yReturnVoluteShell, nozzle.zReturnVoluteShell)
        if nozzle.returnVolute.circlePrintability == 'thick' or nozzle.returnVolute.circlePrintability == 'thin':
            print(f'Exporting Return Volute Print Supports to .stl')
            py2cad(filename[:-4] + 'ReturnVolutePrintSupportsWall.stl', nozzle.xReturnVoluteSupportWall, nozzle.yReturnVoluteSupportWall, nozzle.zReturnVoluteSupportWall)
            py2cad(filename[:-4] + 'ReturnVolutePrintSupportsUpper.stl', nozzle.xReturnVoluteSupportUpper, nozzle.yReturnVoluteSupportUpper, nozzle.zReturnVoluteSupportUpper)
            if nozzle.returnVolute.circlePrintability == 'thick':
                py2cad(filename[:-4] + 'ReturnVolutePrintSupportsLower.stl', nozzle.xReturnVoluteSupportLower, nozzle.yReturnVoluteSupportLower, nozzle.zReturnVoluteSupportLower)

    # Each geometry above is written as its own .stl. A single assembly file would be more
    # convenient to open, but py2cad writes one solid per call and a multi-solid STL needs a
    # writer that concatenates the facet lists under one header.

def exportExhaustPropertiesFEA(nozzle) -> None:

    # -- Placeholder data processing -- #

    # Generate a .csv that encapsulates the exhaust pressure field to be used in FEA

    '''

    Pressure field needs to be in 3D, but I'm making it only vary with nozzle axis.
    Final format needs to be 
    [x1 y1 z1 P1
        x2 y1 z1 P1
        x3 y1 z1 P1
        ...
        x1 y1 zn Pn
        x2 y1 zn Pn
        x3 y1 zn Pn
        ...
        xn yn zn Pn]

    '''

    planarGridSize = 20
    maxRadiusValue = max(nozzle.rNozzleWall) + 25e-3
    xBoundingBox, yBoundingBox = [np.linspace(-maxRadiusValue, maxRadiusValue, planarGridSize) for _ in range(2)]

    truncationValue = 250e-3 # 250mm from beginning of converging section
    truncationIndex = np.argmin(np.abs(nozzle.xNozzleWall - (np.min(nozzle.xNozzleWall) + truncationValue)))

    pressureField = np.zeros((len(nozzle.xNozzleWall[:truncationIndex])*planarGridSize**2,4))

    pressureField[:,0] = np.tile(xBoundingBox,                            len(nozzle.xNozzleWall[:truncationIndex])*planarGridSize)
    pressureField[:,1] = np.tile(np.repeat(yBoundingBox, planarGridSize), len(nozzle.xNozzleWall[:truncationIndex]))
    pressureField[:,2] = np.repeat(-np.flip(nozzle.xNozzleWall[:truncationIndex]), planarGridSize**2)
    pressureField[:,3] = np.repeat(np.flip(nozzle.nozzleNearWallPressure[:truncationIndex]), planarGridSize**2)

    writeFile('LDPRNozzleExhaustPressureFieldTruncated.csv', pressureField)

    debug = 1

def pickleNozzle(nozzle, filename: str):

    '''

    Method for pickling the Nozzle class instance for later retrieval.

    Author: Cam'ron Valliere
    Date:   12/17/2025

    '''

    # Handle file names that do not end in '.pkl'
    if not filename.endswith('.pkl'):
        filename += '.pkl'

    pickleObject(nozzle, filename)
