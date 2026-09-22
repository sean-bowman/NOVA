
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
characteristics solve returns, and near the throat the two differ by up to 42 percent in Mach
number. A structural analysis reading these files is reading the one-dimensional value.

All units are mass base SI on the object. Contour and geometry files are written in
millimeters, which is the convention CAD packages expect.

Author: Sean Bowman

'''

import os
import pickle

import numpy as np

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

    # Channels
    if cooledGeometry:
        print(f'Writing Channel Centerline to .txt and Surfaces to .stl')
        centerlineArray = np.array([nozzle.zChannelCenterline3D, nozzle.yChannelCenterline3D, nozzle.xChannelCenterline3D]).T
        writeFile(filename[:-4] + 'ChannelCenterline3D.txt', centerlineArray*1e3)
        py2cad(filename[:-4] + 'Channel.stl', nozzle.zChannel, nozzle.yChannel, -nozzle.xChannel)

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

#--------------------------------------------------------------------------------------------------------------------------#
# -- File writers -- #
#--------------------------------------------------------------------------------------------------------------------------#

def py2cad(filename: str, xData: np.ndarray | list, yData: np.ndarray | list, zData: np.ndarray | list) -> None:

    '''

    This function takes in arrays containing spatial coordinates of a surface mesh and exports the surface
    as a .stl file. This is useful for exporting geometry out of python CAD design tools and into CAD
    softwares such as NX.

    ---------------------------------------------------------------------------
                                    INPUTS
    ---------------------------------------------------------------------------
    - Filename                                                         [string]

    - X Data, Y Data, Z Data                  [(m,n) shape numpy array or list]

    ***NOTE:
    Numpy arrays are anticipated by default, however if a list is passed in the
    function will convert the list into a numpy array.

    ---------------------------------------------------------------------------
                                    OUTPUTS
    ---------------------------------------------------------------------------
    py2cad does not return anything, however a .stl file is created and saved
    to the 'filename' location specified.

    '''

    from tqdm import tqdm

    # Helper function to find the facet normal and write the current facet data to the file
    def writeFacet(fileID, point1, point2, point3):

        # Find face normal
        vector1 = point2 - point1
        vector2 = point3 - point1
        vector3 = np.cross(vector1, vector2)
        normal = vector3 / np.sqrt(np.sum(vector3**2))

        # Write data to file, ensure data types are what .stl expects
        fileID.write(np.float32(normal))
        fileID.write(np.float32(point1))
        fileID.write(np.float32(point2))
        fileID.write(np.float32(point3))
        fileID.write(np.int16(0))

        # Declare success flag to count up generated facets
        successFlag = 1

        return successFlag

    # Append file extension if the given name does not contain it
    if '.' not in filename:
        filename += '.stl'

    # Locally re-scope mesh data
    # If passed in arrays are lists, make them numpy arrays
    if type(xData) is list:
        x = np.array(xData)
    else:
        x = xData
    if type(yData) is list:
        y = np.array(yData)
    else:
        y = yData
    if type(zData) is list:
        z = np.array(zData)
    else:
        z = zData

    # Determine the size of the arrays and whether parallel processing is necessary
    # numArrayElements = xData.size

    # Initialize facet counter to 0
    nFacets = 0

    # Open a file for writing in binary mode
    fileID = open(filename, 'wb+')
    # .stl files start with 80 characters of metadata, pre-append a message for our .stl files and fill the rest
    # with spaces to eat up the remaining 80 characters
    metadataString = 'Created by py2cad.py [Sean Bowman]'
    # bytearray() casts the strings as unsigned character bytes so that they can be written to tbe binary file
    metadataTitle = bytearray(b'Created by py2cad.py [Sean Bowman]' + b' '*(80 - len(metadataString)))
    fileID.write(metadataTitle)
    # Placeholder for the number of facets that the model has, cast as a 32-bit integer (0 at the start)
    fileID.write(np.int32(nFacets))

    # Loop over all vertices of the mesh and call write_facet() to write mesh data to the .stl file
    for i in tqdm(range(len(z[:,0]) - 1)):
        for j in range(len(z[0,:]) - 1):

            # Draw a triangle to make a facet
            point1 = np.array([[x[i,j],     y[i,j],     z[i,j]]])
            point2 = np.array([[x[i,j+1],   y[i,j+1],   z[i,j+1]]])
            point3 = np.array([[x[i+1,j+1], y[i+1,j+1], z[i+1,j+1]]])
            # Write that facet to the file
            successFlag = writeFacet(fileID, point1, point2, point3)
            # Count 'em up
            nFacets += successFlag

            # Draw the corresponding triangle to the previous one
            point1 = np.array([[x[i+1,j+1], y[i+1,j+1], z[i+1,j+1]]])
            point2 = np.array([[x[i+1,j],   y[i+1,j],   z[i+1,j]]])
            point3 = np.array([[x[i,j],     y[i,j],     z[i,j]]])
            # Write that facet to the file and count it up
            successFlag = writeFacet(fileID, point1, point2, point3)
            nFacets += successFlag

    # After we've written all the facets, move the pointer in the file back to the beginning
    fileID.seek(0,0)
    # Then move it to the end of the metadata string, now we're at the location we put a placeholder for the number
    # of facets
    fileID.seek(len(metadataTitle),0)
    # Write the actual number of facets to the file
    fileID.write(np.int32(nFacets))
    # Don't forget to close the file
    fileID.close()

def writeFile(filename: str, data: np.ndarray | list, headers: bool = False) -> None:

    '''

    Wrapper for writing .csv and .txt files so that I don't have to remember the 'with open' syntax.

    'filename' input must contain the file extension.

    'data' input is assumed to be a (n,m) matrix.

    Supported filetypes:

    - .csv
    - .txt

    '''

    import csv

    if '.' not in filename:
        raise Exception('You must specify that the written file is either a .txt or a .csv file')

    # Convert the data to a numpy array if it isnt one already
    if isinstance(data, list):
        data = np.array(data)

    whichType = filename[-4:]

    match whichType:

        case '.csv':

            if headers:

                headersRow = ['X', 'Y', 'Z']

            with open(filename, 'w', newline = '') as csvFile:
                writer = csv.writer(csvFile)
                if headers:
                    writer.writerows(headersRow)
                writer.writerows(data)

        case '.txt':

            with open(filename, 'w') as txtFile:
                # Loop over all 'n' rows of the data
                for i, _ in enumerate(data[:,0]):
                    # This looks ridiculous but the list comprehension means the following:
                    # data[each row, all cols] is cast as a list so that the call to 'str()'
                    # doesn't include the array brackets '[]' at the beginning and end of the
                    # array. Next, each value of data[this row, :] is converted to a string individually,
                    # and finally each str converted array element is joined with a 'tab' character.
                    # The line ends with a 'newline' character as well to recreate the (row,col)
                    # appearance of the original data.
                    # In total you get: 'data[this row, first col] \t data[this row, second col] \t ... \n'
                    txtFile.write('\t'.join([str(i) for i in (list(data[i,:]))]) + '\n')

def pickleObject(obj, filePath: str) -> None:

    '''

    This method is responsible for pickling a given object to a specified file path.

    Author: Sean Bowman
    Date:   12/17/2025

    '''

    with open(filePath, 'wb') as file:
        pickle.dump(obj, file)
