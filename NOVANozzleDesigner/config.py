# -- NOVA: Configuration Reader -- #

'''

Turning a configuration into the state a run works from.

A configuration reaches NOVA three ways, and this module reads all of them onto a nozzle:

    a JSON file      a path ending in .json
    a dictionary     the same fields, already loaded, which is how the GUI supplies them
    a workbook       a path ending in .xlsx, one sheet per group of fields

They are not quite equivalent, and the differences are worth stating rather than discovering.

**Unset is NaN, not None.** A null in JSON, or an empty cell in the workbook, becomes NaN on the
object. That is the convention every downstream module reads, which is why `validation.specified`
treats NaN and None and absent as the same thing.

**Program flags are strings, not booleans.** Every flag is compared against 'on' and 'off'
throughout the tool, but JSON stores them as booleans, and `False == 'on'` is quietly False
rather than an error. Without the normalisation here every plot and every export would be
silently disabled by a configuration that looks correct.

**A literal zero is not the same as unset.** An axial offset of zero is a specified offset. The
readers preserve that distinction and so does everything downstream.

Once the fields are on the object, the thermochemistry is run for the design point, since almost
everything after this needs the chamber state it returns.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Nothing here is a model.** Reading a configuration is bookkeeping, and what it can get wrong is
losing a field, changing its type, or letting the three readers disagree with each other. Those
are what the tests check.

The one place it computes rather than reads is the design point: mass flow from thrust, or thrust
from mass flow, and the CEA call that follows. Those come from `ceaInterface`, which is validated
against CEARun in `tests/testCeaInterface.py`.

All units are mass base SI, as read:
    - Length      [m]
    - Temperature [K]
    - Pressure    [Pa]
    - Mass flow   [kg/s]
    - Thrust      [N]
    - Angle       [deg] as configurations name them

Author: Sean Bowman

'''

import os
import warnings

import numpy as np
import pandas as pd

try:
    from utils import readExcel, InvalidInputError
    from ceaInterface import CEA
except ImportError:
    from .utils import readExcel, InvalidInputError
    from .ceaInterface import CEA

def setInputs(nozzle, inputsPath: str | dict, debugMode: bool = False) -> None:

    '''

    Configure nozzle design parameters from a configuration file or dictionary.

    This method initializes all nozzle design parameters including contour definition,
    regenerative cooling jacket specifications, volute geometry, and program options.
    Supports three input modes: GUI dictionary input, debug CSV input, and Excel config file.

    Parameters:
    -----------
    inputsPath : str | dict
        Configuration source - can be:
        - dict: Dictionary of parameter key-value pairs (typical GUI usage)
        - str (debugMode=True): Path to CSV file with 'Key' and 'Value' columns
        - str (debugMode=False): Path to Excel config file with multiple sheets
    debugMode : bool, optional
        If True, expects inputsPath to be a CSV file path. If False and inputsPath
        is a string, expects an Excel config file. Default is False.

    Returns:
    --------
    None : Sets instance attributes directly

    Configuration Categories:
    -------------------------
    Contour Definition:
        - Propellant properties (Fuel, Oxidizer, OFRatio, initial temperatures)
        - Chamber conditions (chamberPressure)
        - Performance constraints (thrust, engineMassFlow, targetExitPressure, expansionRatio)
        - Geometry parameters (lengthFraction, conicalHalfAngle, numContourPoints)
        - Contour type selection (contourType: 'trad' or 'sunk')
        - Sunken nozzle parameters (throatEntryLength, throatEccentricity, etc.)
        - Chamber sizing (Lstar, contractionAreaRatio)

    Regenerative Cooling Jacket:
        - Wall dimensions (hotWallThickness, shellThickness)
        - Channel geometry (channelType, nChannel, numCSPointsChannel, numCrossSections)
        - Thermal constraints (maxWallTemperature, minCoolantExitTemperature)
        - Optimization bounds (nChannelUpperBound, nChannelLowerBound, etc.)
        - Coolant properties (coolant, coolantChoice, coolantInitialTemperature, etc.)
        - Advanced features (numFlutes, fluteAmplitudeCoef, fluteHelixAngle, swirlPercent)
        - Manufacturing constraints (printabilityCheck, printDirection, maxOverhangAngle)

    Regen Volutes:
        - Inlet volute (makeInletVolute, inletVoluteCrossSection, inletVoluteAlignment, etc.)
        - Return volute (makeReturnVolute, returnVoluteCrossSection, returnVoluteAlignment, etc.)
        - Keep-out envelope (plotKeepOut, keepOutAxialOffset, keepOutRadius,
          keepOutDepth, keepOutHubRadius)
        - Grayloc fittings (inletGraylocDiameter, returnGraylocDiameter)

    Program Options:
        - Plotting controls (plotsBasic, plotsAdv, plotJacket, plotsDebug)
        - Export settings (export, filename)

    Notes:
    ------
    - None/NaN values in dict input are automatically converted to np.nan for compatibility
    - CSV debug mode automatically converts string values to appropriate types (bool, int, float)
    - Excel mode uses named sheets: 'Contour Definition', 'Regenerative Cooling', etc.
    - Some parameters (maxWallTemperature, infillThickness) are broadcast to arrays if scalar
    - Sunken nozzle parameters are only loaded when contourType == 'sunk'

    Raises:
    -------
    ValueError
        If debugMode is True but inputsPath is not a string

    '''

    warnings.filterwarnings('ignore')

    # -- Determine input type -- #

    if debugMode:
        nozzle.debugMode = True
        # Inputs from the GUI-generated csv
        if isinstance(inputsPath, str):

            GUIFlag = True

            # -- Read csv and assign values -- #

            df = pd.read_csv(inputsPath)

            # convert key and value columns to dict
            rawDict = dict(zip(df["Key"], df["Value"]))

            inputDict = {}

            # Convert string values to appropriate types
            for k, v in rawDict.items():
                if isinstance(v, str):
                    # try converting to bool
                    if v.lower() in ['true', 'false']:
                        inputDict[k] = v.lower() == 'true'
                        continue
                    # try converting to int
                    if v.isdigit() or (v.startswith('-') and v[1:].isdigit()):
                        inputDict[k] = int(v)
                        continue
                    # try converting to float
                    try:
                        inputDict[k] = float(v)
                        continue
                    except ValueError:
                        pass
                # keep as original type (string or whatever pandas read)
                inputDict[k] = v

            # -- Read dict and assign values -- #

            # -- Contour Definition Inputs -- #

            nozzle.visualizeContour           = inputDict['visualizeContour']
            nozzle.numContourPoints           = inputDict['numContourPoints']

            # Converging Section
            nozzle.contourType                = inputDict['contourType']
            nozzle.chamberDiameter                 = inputDict['chamberDiameter']
            nozzle.raoThroatAngle             = inputDict['raoThroatAngle']
            nozzle.chamberInterfaceAngle        = inputDict['chamberInterfaceAngle']
            nozzle.Lstar                      = inputDict['Lstar']
            nozzle.chamberLength              = inputDict['chamberLength']
            # Sunken Nozzle Parameters
            if nozzle.contourType == 'sunk':
                nozzle.throatEntryLength          = inputDict['throatEntryLength']
                nozzle.throatEccentricity         = inputDict['throatEccentricity']
                nozzle.throatBackWallPitch        = inputDict['throatBackWallPitch']
                nozzle.throatGapThickness         = inputDict['throatGapThickness']
                nozzle.conicDepthModifier         = inputDict['conicDepthModifier']
                nozzle.conicPinchModifier         = inputDict['conicPinchModifier']

            # Diverging Section
            nozzle.divergingSectionType       = inputDict['divergingSectionType']
            nozzle.Fuel                       = inputDict['Fuel']
            nozzle.Oxidizer                   = inputDict['Oxidizer']
            nozzle.OFRatio                    = inputDict['OFRatio']
            nozzle.fuelInitialTemperature     = inputDict['fuelInitialTemperature']
            nozzle.oxidizerInitialTemperature = inputDict['oxidizerInitialTemperature']
            nozzle.chamberPressure            = inputDict['chamberPressure']
            nozzle.engineMassFlow             = inputDict['engineMassFlow']
            nozzle.thrust                     = inputDict['thrust']
            nozzle.targetExitPressure         = inputDict['targetExitPressure']
            nozzle.plumeAmbientPressure       = inputDict['plumeAmbientPressure']
            nozzle.lengthFraction             = inputDict['lengthFraction']
            nozzle.conicalHalfAngle           = inputDict['conicalHalfAngle']
            nozzle.truncationMethod           = inputDict['truncationMethod']
            nozzle.expansionRatio             = inputDict['expansionRatio']
            nozzle.truncateOn                 = inputDict.get('truncateOn', 'areaRatio')
            nozzle.numCharacteristicsRequested = inputDict.get('numCharacteristics', 50)

            # -- Regenerative Cooling Jacket Inputs -- #
            nozzle.makeCoolingChannels            = inputDict['makeCoolingChannels']
            nozzle.numCrossSections               = inputDict['numCrossSections']
            nozzle.numCSPointsChannel             = inputDict['numCSPointsChannel']
            nozzle.hotWallThickness               = inputDict['hotWallThickness']
            nozzle.shellThickness                 = inputDict['shellThickness']
            nozzle.infillThickness                = inputDict['infillThickness']
            nozzle.material                       = inputDict['material']
            nozzle.nChannel                       = inputDict['nChannel']
            nozzle.channelType                    = inputDict['channelType']
            nozzle.minCoolantExitPressure         = inputDict['minCoolantExitPressure']
            nozzle.minCoolantExitTemperature      = inputDict['minCoolantExitTemperature']
            nozzle.maxWallTempUpperBound          = inputDict['maxWallTempUpperBound']
            nozzle.maxWallTempLowerBound          = inputDict['maxWallTempLowerBound']
            nozzle.nChannelUpperBound             = inputDict['nChannelUpperBound']
            nozzle.nChannelLowerBound             = inputDict['nChannelLowerBound']
            nozzle.maxWallTemperature             = inputDict['maxWallTemperature']
            nozzle.numFlutes                      = inputDict['numFlutes']
            nozzle.fluteAmplitudeCoef             = inputDict['fluteAmplitudeCoef']
            nozzle.fluteHelixAngle                = inputDict['fluteHelixAngle']
            nozzle.interfaceLength                = inputDict['interfaceLength']
            nozzle.coolantClass                   = inputDict['coolantClass']
            nozzle.coolant                        = inputDict['coolant']
            nozzle.coolantInitialTemperature      = inputDict['coolantInitialTemperature']
            nozzle.coolantInitialPressure         = inputDict['coolantInitialPressure']
            nozzle.coolantMassFlow                = inputDict['coolantMassFlow']
            nozzle.printabilityCheck              = inputDict['printabilityCheck']
            nozzle.printDirection                 = inputDict['printDirection']
            nozzle.maxOverhangAngle               = inputDict['maxOverhangAngle']

            # -- Regen Volute Inputs -- #
            nozzle.makeInletVolute                = inputDict['makeInletVolute']
            nozzle.makeReturnVolute               = inputDict['makeReturnVolute']
            nozzle.numCSVolute                    = inputDict['numCSVolute']
            nozzle.numCSPointsVolute              = inputDict['numCSPointsVolute']
            nozzle.voluteRelativeRoll             = inputDict['voluteRelativeRoll']
            nozzle.plotKeepOut                    = inputDict['plotKeepOut']
            nozzle.keepOutAxialOffset             = inputDict['keepOutAxialOffset']
            nozzle.keepOutRadius                  = inputDict['keepOutRadius']
            nozzle.keepOutDepth                   = inputDict['keepOutDepth']
            nozzle.keepOutHubRadius               = inputDict['keepOutHubRadius']
            nozzle.inletVoluteCrossSection        = inputDict['inletVoluteCrossSection']
            nozzle.inletVoluteAlignment           = inputDict['inletVoluteAlignment']
            nozzle.inletVolutePrintability        = inputDict['inletVolutePrintability']
            nozzle.inletVoluteTilt                = inputDict['inletVoluteTilt']
            nozzle.inletGraylocDiameter           = inputDict['inletGraylocDiameter']
            nozzle.inletVoluteAxialOffset         = inputDict['inletVoluteAxialOffset']
            nozzle.inletVoluteFlareRoverD         = inputDict['inletVoluteFlareRoverD']
            nozzle.inletVoluteFlareLength         = inputDict['inletVoluteFlareLength']
            nozzle.returnVoluteCrossSection       = inputDict['returnVoluteCrossSection']
            nozzle.returnVoluteAlignment          = inputDict['returnVoluteAlignment']
            nozzle.returnVolutePrintability       = inputDict['returnVolutePrintability']
            nozzle.returnVoluteTilt               = inputDict['returnVoluteTilt']
            nozzle.returnGraylocDiameter          = inputDict['returnGraylocDiameter']
            nozzle.returnVoluteAxialOffset        = inputDict['returnVoluteAxialOffset']
            nozzle.returnVoluteRadialOffset       = inputDict['returnVoluteRadialOffset']
            nozzle.returnVoluteFlareRoverD        = inputDict['returnVoluteFlareRoverD']
            nozzle.returnVoluteReturnAngle        = inputDict['returnVoluteReturnAngle']
            nozzle.returnVoluteFlareLen           = inputDict['returnVoluteFlareLen']

            # -- Program Options -- #
            nozzle.plotsBasic                     = inputDict['plotsBasic']
            nozzle.plotsAdv                       = inputDict['plotsAdv']
            nozzle.plotJacket                     = inputDict['plotJacket']
            nozzle.plotsDebug                     = inputDict['plotsDebug']
            nozzle.export                         = inputDict['export']
            nozzle.filename                       = inputDict['filename']

        else:
            raise ValueError("We're in debug mode so inputsPath should be a string containing the input file csv file path.")

    # Inputs from a JSON config file. generateNozzle() defaults to
    # assets/nozzleConfig.json, so this must be handled before the
    # spreadsheet branch below, which would otherwise hand a .json path to
    # the Excel reader. The keys are identical to the GUI dict form, so the
    # file is simply loaded and allowed to fall through to that branch.
    if isinstance(inputsPath, str) and inputsPath.lower().endswith('.json') and not debugMode:
        import json
        with open(inputsPath, 'r') as configFile:
            inputsPath = json.load(configFile)

    # Inputs from the GUI
    if isinstance(inputsPath, dict):

        GUIFlag = True

        # Converging-section keys were renamed away from solid-motor language. Catch a
        # pre-rename config here rather than letting it surface as a bare KeyError three
        # hundred lines further down.
        renamedKeys = {
            'grainMaxOD':          'chamberDiameter',
            'grainInterfaceAngle': 'chamberInterfaceAngle',
        }
        stale = {old: new for old, new in renamedKeys.items() if old in inputsPath}
        if stale:
            raise InvalidInputError(
                message=('Config uses renamed keys: '
                         + ', '.join(f'{old!r} is now {new!r}' for old, new in stale.items())
                         + '. Rename them and re-run.'),
                parameterName=', '.join(stale),
                value=list(stale),
                validRange=', '.join(stale.values()),
            )

        # Convert None values to np.nan for compatibility with np.isnan() logic
        # (CSV reader converts None to np.nan, so we do the same for direct dict input)
        for key, value in inputsPath.items():
            if value is None:
                inputsPath[key] = np.nan

        # Program option flags are compared against the strings 'on'/'off'
        # throughout this class, but JSON stores them as booleans, and
        # `False == 'on'` is silently False rather than an error. Without
        # this normalization every plot and export is quietly disabled.
        for key in ('visualizeContour', 'plotsBasic', 'plotsAdv', 'plotJacket',
                    'plotsDebug', 'export', 'printabilityCheck',
                    'makeCoolingChannels', 'makeInletVolute', 'makeReturnVolute',
                    'plotKeepOut', 'inletVolutePrintability', 'returnVolutePrintability'):
            if isinstance(inputsPath.get(key), bool):
                inputsPath[key] = 'on' if inputsPath[key] else 'off'

        # -- Read dict and assign values -- #

        # -- Contour Definition Inputs -- #

        nozzle.visualizeContour           = inputsPath['visualizeContour']
        nozzle.numContourPoints           = inputsPath['numContourPoints']

        # Converging Section
        nozzle.contourType                = inputsPath['contourType']
        nozzle.chamberDiameter                 = inputsPath['chamberDiameter']
        nozzle.raoThroatAngle             = inputsPath['raoThroatAngle']
        nozzle.chamberInterfaceAngle        = inputsPath['chamberInterfaceAngle']
        nozzle.Lstar                      = inputsPath['Lstar']
        nozzle.chamberLength              = inputsPath['chamberLength']
        # Sunken Nozzle Parameters
        if nozzle.contourType == 'sunk':
            nozzle.throatEntryLength          = inputsPath['throatEntryLength']
            nozzle.throatEccentricity         = inputsPath['throatEccentricity']
            nozzle.throatBackWallPitch        = inputsPath['throatBackWallPitch']
            nozzle.throatGapThickness         = inputsPath['throatGapThickness']
            nozzle.conicDepthModifier         = inputsPath['conicDepthModifier']
            nozzle.conicPinchModifier         = inputsPath['conicPinchModifier']

        # Diverging Section
        nozzle.divergingSectionType       = inputsPath['divergingSectionType']
        nozzle.Fuel                       = inputsPath['Fuel']
        nozzle.Oxidizer                   = inputsPath['Oxidizer']
        nozzle.OFRatio                    = inputsPath['OFRatio']
        nozzle.fuelInitialTemperature     = inputsPath['fuelInitialTemperature']
        nozzle.oxidizerInitialTemperature = inputsPath['oxidizerInitialTemperature']
        nozzle.chamberPressure            = inputsPath['chamberPressure']
        nozzle.engineMassFlow             = inputsPath['engineMassFlow']
        nozzle.thrust                     = inputsPath['thrust']
        nozzle.targetExitPressure         = inputsPath['targetExitPressure']
        nozzle.plumeAmbientPressure       = inputsPath['plumeAmbientPressure']
        nozzle.lengthFraction             = inputsPath['lengthFraction']
        nozzle.conicalHalfAngle           = inputsPath['conicalHalfAngle']
        nozzle.truncationMethod           = inputsPath['truncationMethod']
        nozzle.expansionRatio             = inputsPath['expansionRatio']
        nozzle.truncateOn                 = inputsPath.get('truncateOn', 'areaRatio')
        nozzle.numCharacteristicsRequested = inputsPath.get('numCharacteristics', 50)

        # -- Regenerative Cooling Jacket Inputs -- #
        nozzle.makeCoolingChannels            = inputsPath['makeCoolingChannels']
        nozzle.numCrossSections               = inputsPath['numCrossSections']
        nozzle.numCSPointsChannel             = inputsPath['numCSPointsChannel']
        nozzle.hotWallThickness               = inputsPath['hotWallThickness']
        nozzle.shellThickness                 = inputsPath['shellThickness']
        nozzle.infillThickness                = inputsPath['infillThickness']
        nozzle.material                       = inputsPath['material']
        nozzle.nChannel                       = inputsPath['nChannel']
        nozzle.channelType                    = inputsPath['channelType']
        nozzle.minCoolantExitPressure         = inputsPath['minCoolantExitPressure']
        nozzle.minCoolantExitTemperature      = inputsPath['minCoolantExitTemperature']
        nozzle.maxWallTempUpperBound          = inputsPath['maxWallTempUpperBound']
        nozzle.maxWallTempLowerBound          = inputsPath['maxWallTempLowerBound']
        nozzle.nChannelUpperBound             = inputsPath['nChannelUpperBound']
        nozzle.nChannelLowerBound             = inputsPath['nChannelLowerBound']
        nozzle.maxWallTemperature             = inputsPath['maxWallTemperature']
        nozzle.numFlutes                      = inputsPath['numFlutes']
        nozzle.fluteAmplitudeCoef             = inputsPath['fluteAmplitudeCoef']
        nozzle.fluteHelixAngle                = inputsPath['fluteHelixAngle']
        nozzle.interfaceLength                = inputsPath['interfaceLength']
        nozzle.coolantClass                   = inputsPath['coolantClass']
        nozzle.coolant                        = inputsPath['coolant']
        nozzle.coolantInitialTemperature      = inputsPath['coolantInitialTemperature']
        nozzle.coolantInitialPressure         = inputsPath['coolantInitialPressure']
        nozzle.coolantMassFlow                = inputsPath['coolantMassFlow']
        nozzle.printabilityCheck              = inputsPath['printabilityCheck']
        nozzle.printDirection                 = inputsPath['printDirection']
        nozzle.maxOverhangAngle               = inputsPath['maxOverhangAngle']

        # -- Regen Volute Inputs -- #
        nozzle.makeInletVolute                = inputsPath['makeInletVolute']
        nozzle.makeReturnVolute               = inputsPath['makeReturnVolute']
        nozzle.numCSVolute                    = inputsPath['numCSVolute']
        nozzle.numCSPointsVolute              = inputsPath['numCSPointsVolute']
        nozzle.voluteRelativeRoll             = inputsPath['voluteRelativeRoll']
        nozzle.plotKeepOut                    = inputsPath['plotKeepOut']
        nozzle.keepOutAxialOffset             = inputsPath['keepOutAxialOffset']
        nozzle.keepOutRadius                  = inputsPath['keepOutRadius']
        nozzle.keepOutDepth                   = inputsPath['keepOutDepth']
        nozzle.keepOutHubRadius               = inputsPath['keepOutHubRadius']
        nozzle.inletVoluteCrossSection        = inputsPath['inletVoluteCrossSection']
        nozzle.inletVoluteAlignment           = inputsPath['inletVoluteAlignment']
        nozzle.inletVolutePrintability        = inputsPath['inletVolutePrintability']
        nozzle.inletVoluteTilt                = inputsPath['inletVoluteTilt']
        nozzle.inletGraylocDiameter           = inputsPath['inletGraylocDiameter']
        nozzle.inletVoluteAxialOffset         = inputsPath['inletVoluteAxialOffset']
        nozzle.inletVoluteFlareRoverD         = inputsPath['inletVoluteFlareRoverD']
        nozzle.inletVoluteFlareLength         = inputsPath['inletVoluteFlareLength']
        nozzle.returnVoluteCrossSection       = inputsPath['returnVoluteCrossSection']
        nozzle.returnVoluteAlignment          = inputsPath['returnVoluteAlignment']
        nozzle.returnVolutePrintability       = inputsPath['returnVolutePrintability']
        nozzle.returnVoluteTilt               = inputsPath['returnVoluteTilt']
        nozzle.returnGraylocDiameter          = inputsPath['returnGraylocDiameter']
        nozzle.returnVoluteAxialOffset        = inputsPath['returnVoluteAxialOffset']
        nozzle.returnVoluteRadialOffset       = inputsPath['returnVoluteRadialOffset']
        nozzle.returnVoluteFlareRoverD        = inputsPath['returnVoluteFlareRoverD']
        nozzle.returnVoluteReturnAngle        = inputsPath['returnVoluteReturnAngle']
        nozzle.returnVoluteFlareLen           = inputsPath['returnVoluteFlareLen']

        # -- Program Options -- #
        nozzle.plotsBasic                     = inputsPath['plotsBasic']
        nozzle.plotsAdv                       = inputsPath['plotsAdv']
        nozzle.plotJacket                     = inputsPath['plotJacket']
        nozzle.plotsDebug                     = inputsPath['plotsDebug']
        nozzle.export                         = inputsPath['export']
        nozzle.filename                       = inputsPath['filename']

    # Inputs from the config file
    elif isinstance(inputsPath, str) and not debugMode:

        GUIFlag = False

        # -- Read each sheet and assign values -- # 

        contourDefinitionInputs, _ = readExcel(inputsPath, sheetName = "Contour Definition")
        for i, _ in enumerate(contourDefinitionInputs.values):
            match contourDefinitionInputs.values[i][0]:

                # Primary Parameters
                case 'Fuel':
                    nozzle.Fuel                       = contourDefinitionInputs.values[i][1]
                case 'Oxidizer':
                    nozzle.Oxidizer                   = contourDefinitionInputs.values[i][1]
                case 'Chamber Pressure':
                    nozzle.chamberPressure            = float(contourDefinitionInputs.values[i][1])

                # Specify one - Calculate other: Engine Design Constraints
                # Set 1:
                case 'Thrust':
                    nozzle.thrust                     = float(contourDefinitionInputs.values[i][1])
                case 'Total Engine Mass Flow (Fuel + Oxidizer)':
                    nozzle.engineMassFlow             = float(contourDefinitionInputs.values[i][1])
                # Set 2:
                case 'Target Nozzle Exit Pressure':
                    nozzle.targetExitPressure         = float(contourDefinitionInputs.values[i][1])
                case 'Nozzle Expansion Ratio':
                    nozzle.expansionRatio             = float(contourDefinitionInputs.values[i][1])

                # Optional Prameters
                case 'Make Contour Plots?':
                    nozzle.visualizeContour           = contourDefinitionInputs.values[i][1]
                case 'Nozzle Length Fraction':
                    nozzle.lengthFraction             = float(contourDefinitionInputs.values[i][1]) if not isinstance(contourDefinitionInputs.values[i][1], str) else contourDefinitionInputs.values[i][1]
                case 'OF Ratio':
                    if isinstance(contourDefinitionInputs.values[i][1], str) or contourDefinitionInputs.values[i][1] is None:
                        nozzle.OFRatio                = 'maxisp'
                    else:
                        nozzle.OFRatio                = float(contourDefinitionInputs.values[i][1])
                case 'Fuel Initial Temperature':
                    nozzle.fuelInitialTemperature     = float(contourDefinitionInputs.values[i][1])
                case 'Oxidizer Initial Temperature':
                    nozzle.oxidizerInitialTemperature = float(contourDefinitionInputs.values[i][1])
                case 'Total Number of Contour Points':
                    nozzle.numContourPoints           = int(contourDefinitionInputs.values[i][1])
                case 'Contour Type':
                    nozzle.contourType                = contourDefinitionInputs.values[i][1]
                case 'Rao Throat Angle':
                    nozzle.raoThroatAngle             = float(contourDefinitionInputs.values[i][1])

                # Diverging Section Parameters
                case 'Diverging Section Type':
                    nozzle.divergingSectionType       = contourDefinitionInputs.values[i][1]
                case 'Conical Half Angle':
                    nozzle.conicalHalfAngle           = float(contourDefinitionInputs.values[i][1])
                case 'Regen Nozzle Truncation Method':
                    nozzle.truncationMethod           = contourDefinitionInputs.values[i][1]
                case 'Binding Constraint':
                    nozzle.truncateOn                 = contourDefinitionInputs.values[i][1]
                case 'Number of Characteristics':
                    nozzle.numCharacteristicsRequested = int(contourDefinitionInputs.values[i][1])

                # Traditional Converging Section Parameters
                case 'Chamber Interface Angle':
                    nozzle.chamberInterfaceAngle        = float(contourDefinitionInputs.values[i][1])
                case 'Chamber Diameter':
                    nozzle.chamberDiameter                 = float(contourDefinitionInputs.values[i][1])
                case 'L*':
                    nozzle.Lstar                      = float(contourDefinitionInputs.values[i][1])
                case 'Contraction Area Ratio':
                    nozzle.contractionAreaRatio       = float(contourDefinitionInputs.values[i][1])

                # Sunken Converging Section Paramters
                case 'Throat Entry Length':
                    nozzle.throatEntryLength          = float(contourDefinitionInputs.values[i][1])
                case 'Throat Eccentricity':
                    nozzle.throatEccentricity          = float(contourDefinitionInputs.values[i][1])
                case 'Throat Back Wall Pitch':
                    nozzle.throatBackWallPitch        = float(contourDefinitionInputs.values[i][1])
                case 'Gap Thickness':
                    nozzle.throatGapThickness         = float(contourDefinitionInputs.values[i][1])
                case 'Conic Depth Modifier':
                    nozzle.conicDepthModifier         = float(contourDefinitionInputs.values[i][1])
                case 'Conic Pinch Modifier':
                    nozzle.conicPinchModifier         = float(contourDefinitionInputs.values[i][1])

        regenJacketInputs, _ = readExcel(inputsPath, sheetName = "Regen Jacket")
        for i, _ in enumerate(regenJacketInputs.values):
            match regenJacketInputs.values[i][0]:

                # Options
                case 'Generate Cooling Channels?':
                    nozzle.makeCoolingChannels                = regenJacketInputs.values[i][1]

                # Wall Properties
                case 'Hot Wall Thickness':
                    nozzle.hotWallThickness           = float(regenJacketInputs.values[i][1])
                case 'Cold Wall Thickness':
                    nozzle.shellThickness             = float(regenJacketInputs.values[i][1])
                case 'Material':
                    nozzle.material                   = regenJacketInputs.values[i][1]

                # Channel Properties
                case 'Channel Type':
                    nozzle.channelType                = regenJacketInputs.values[i][1]
                case 'Maximum Hot Wall Temperature':
                    nozzle.maxWallTemperature         = float(regenJacketInputs.values[i][1])
                case 'Number of Channels':
                    nozzle.nChannel                   = int(regenJacketInputs.values[i][1])
                case 'Number of Channel Cross Section Points':
                    nozzle.numCSPointsChannel         = int(regenJacketInputs.values[i][1])
                case 'Number of Channel Cross Sections':
                    nozzle.numCrossSections           = int(regenJacketInputs.values[i][1])
                case 'Infill Thickness':
                    nozzle.infillThickness            = float(regenJacketInputs.values[i][1])
                case 'Number of Flutes':
                    nozzle.numFlutes                  = int(regenJacketInputs.values[i][1])
                case 'Flute Amplitude Coefficient':
                    nozzle.fluteAmplitudeCoef         = float(regenJacketInputs.values[i][1])
                case 'Flute Helix Angle':
                    nozzle.fluteHelixAngle            = float(regenJacketInputs.values[i][1])
                case 'Circular Interface Length':
                    nozzle.interfaceLength            = float(regenJacketInputs.values[i][1])

                # Heat Transfer Model Properties
                case 'Coolant Class':
                    nozzle.coolantClass               = regenJacketInputs.values[i][1]
                case 'Coolant Species':
                    nozzle.coolant                    = regenJacketInputs.values[i][1]
                case 'Initial Temperature':
                    nozzle.coolantInitialTemperature  = float(regenJacketInputs.values[i][1])
                case 'Initial Pressure':
                    nozzle.coolantInitialPressure     = float(regenJacketInputs.values[i][1])
                case 'Total Coolant Mass Flow':
                    nozzle.coolantMassFlow            = float(regenJacketInputs.values[i][1])                
                case 'Swirl Percent':
                    nozzle.swirlPercent               = float(regenJacketInputs.values[i][1])                

                # Printability Opeions
                case 'Check for printability?':
                    nozzle.printabilityCheck          = regenJacketInputs.values[i][1]
                case 'Print direction':
                    nozzle.printDirection             = regenJacketInputs.values[i][1]
                case 'Max Overhang Angle':
                    nozzle.maxOverhangAngle           = float(regenJacketInputs.values[i][1])

        regenVoluteInputs, _ = readExcel(inputsPath, sheetName = "Regen Volutes")
        for i, _ in enumerate(regenVoluteInputs.values):
            match regenVoluteInputs.values[i][0]:

                # Options
                case 'Generate Inlet Volute?':
                    nozzle.makeInletVolute            = regenVoluteInputs.values[i][1]
                case 'Generate Return Volute?':
                    nozzle.makeReturnVolute           = regenVoluteInputs.values[i][1]
                case 'Volute Relative Roll':
                    nozzle.voluteRelativeRoll         = float(regenVoluteInputs.values[i][1])
                case 'Number of Volute Cross Section Points':
                    nozzle.numCSPointsVolute          = int(regenVoluteInputs.values[i][1])
                case 'Number of Volute Cross Sections':
                    nozzle.numCSVolute                = int(regenVoluteInputs.values[i][1])
                case 'Plot Keep Out?':
                    nozzle.plotKeepOut                = regenVoluteInputs.values[i][1]
                case 'Keep Out Axial Offset':
                    nozzle.keepOutAxialOffset         = float(regenVoluteInputs.values[i][1])
                case 'Keep Out Radius':
                    nozzle.keepOutRadius              = float(regenVoluteInputs.values[i][1])
                case 'Keep Out Depth':
                    nozzle.keepOutDepth               = float(regenVoluteInputs.values[i][1])
                case 'Keep Out Hub Radius':
                    nozzle.keepOutHubRadius           = float(regenVoluteInputs.values[i][1])
                case 'Volute Factor of Safety':
                    nozzle.voluteFOS                  = float(regenVoluteInputs.values[i][1])

                # Inlet Volute Geometry
                case 'Inlet Cross Section Type':
                    nozzle.inletVoluteCrossSection    = (regenVoluteInputs.values[i][1])
                case 'Inlet Cross Section Alignment':
                    nozzle.inletVoluteAlignment       = (regenVoluteInputs.values[i][1])
                case 'Inlet Circle Printability':
                    nozzle.inletVolutePrintability    = (regenVoluteInputs.values[i][1])
                case 'Inlet Volute Cross Section Tilt Angle':
                    nozzle.inletVoluteTilt            = float(regenVoluteInputs.values[i][1])
                case 'Inlet Grayloc Seal Ring ID':
                    nozzle.inletGraylocDiameter       = float(regenVoluteInputs.values[i][1])
                case 'Inlet Volute Turnaround Axial Offset':
                    nozzle.inletVoluteAxialOffset     = float(regenVoluteInputs.values[i][1])
                case 'Inlet Channel Flare R/D':
                    nozzle.inletVoluteFlareRoverD     = float(regenVoluteInputs.values[i][1])
                case 'Inlet Channel Flare Extension Length':
                    nozzle.inletVoluteFlareLength     = float(regenVoluteInputs.values[i][1])

                # Return Volute Geometry
                case 'Return Cross Section Type':
                    nozzle.returnVoluteCrossSection   = (regenVoluteInputs.values[i][1])
                case 'Return Cross Section Alignment':
                    nozzle.returnVoluteAlignment      = (regenVoluteInputs.values[i][1])
                case 'Return Circle Printability':
                    nozzle.returnVolutePrintability   = (regenVoluteInputs.values[i][1])
                case 'Return Volute Cross Section Tilt Angle':
                    nozzle.returnVoluteTilt           = float(regenVoluteInputs.values[i][1])
                case 'Return Grayloc Seal Ring ID':
                    nozzle.returnGraylocDiameter      = float(regenVoluteInputs.values[i][1])
                case 'Return Volute Turnaround Axial Offset':
                    nozzle.returnVoluteAxialOffset    = float(regenVoluteInputs.values[i][1])
                case 'Return Volute Turnaround Radial Offset':
                    nozzle.returnVoluteRadialOffset   = float(regenVoluteInputs.values[i][1])
                case 'Return Channel Flare R/D':
                    nozzle.returnVoluteFlareRoverD    = float(regenVoluteInputs.values[i][1])
                case 'Return Channel Return Angle':
                    nozzle.returnVoluteReturnAngle    = float(regenVoluteInputs.values[i][1])
                case 'Return Channel Flare Extension Length':
                    nozzle.returnVoluteFlareLen       = float(regenVoluteInputs.values[i][1])

        programOptionInputs, excelInstance = readExcel(inputsPath, sheetName = "Program Options")
        for i, _ in enumerate(programOptionInputs.values):
            match programOptionInputs.values[i][0]:

                # Plot Options
                case 'Basic Plot Outputs?':
                    nozzle.plotsBasic                 = programOptionInputs.values[i][1]
                case 'Advanced Plot Outputs?':
                    nozzle.plotsAdv                   = programOptionInputs.values[i][1]
                case 'Plot Full Regen Jacket?':
                    nozzle.plotJacket                 = programOptionInputs.values[i][1]
                case 'Debug Plot Outputs?':
                    nozzle.plotsDebug                 = programOptionInputs.values[i][1]

                # Export Options
                case 'Export Data?':
                    nozzle.export                     = programOptionInputs.values[i][1]
                case 'Export File Name':
                    nozzle.filename                   = programOptionInputs.values[i][1]

    # If exporting is on, make the export directory
    if nozzle.export == 'on':
        # Every run of this name writes into one directory under the output root.
        topLevelDirectory = nozzle._getOutputRoot()

        # Ensure filename is not None or empty
        if not nozzle.filename:
            nozzle.filename = 'nozzle_output'

        nozzle.dataFolder = os.path.join(topLevelDirectory, f'{nozzle.filename}Outputs')

        os.makedirs(nozzle.dataFolder, exist_ok = True)

    # Store the repository root for consistency
    nozzle.topLevelDirectory = nozzle._getRepositoryRoot()

    # Run CEA after all values have been read in
    if not np.isnan(nozzle.targetExitPressure):
        ceaOutput = CEA(fuelName = nozzle.Fuel, # fuelTemperature = nozzle.fuelInitialTemperature,
                    oxidizerName = nozzle.Oxidizer, oxidizerInitialTemperature = nozzle.oxidizerInitialTemperature,
                    chamberPressure = nozzle.chamberPressure, nozzleExitPressure = nozzle.targetExitPressure,
                    pressureUnits = 'Pa', OFRatio = nozzle.OFRatio)
    elif not np.isnan(nozzle.expansionRatio):
        ceaOutput = CEA(fuelName = nozzle.Fuel, # fuelTemperature = nozzle.fuelInitialTemperature,
                    oxidizerName = nozzle.Oxidizer, oxidizerInitialTemperature = nozzle.oxidizerInitialTemperature,
                    chamberPressure = nozzle.chamberPressure, expansionRatio = nozzle.expansionRatio,
                    pressureUnits = 'Pa', OFRatio = nozzle.OFRatio)

    # Copy all CEA Outputs to the object in case user wants them for some reason
    nozzle.ceaOutput = ceaOutput
    nozzle.excelInstance = False if GUIFlag else excelInstance
    # Where the workbook was read from, so the export can keep a copy of it beside the run.
    nozzle.configWorkbookPath = inputsPath if (isinstance(inputsPath, str)
                                            and inputsPath.lower().endswith('.xlsx')) else ''

    # -- Assign important calculated values to object -- #

    # Reassign OF Ratio based on ISP optimized OF if that was the type the user wanted
    if nozzle.OFRatio == 'maxisp':
        nozzle.OFRatio = ceaOutput.OFRatio

    # Calculate dependent properties in chamber
    # Thrust or Engine Mass Flow
    if not (np.isnan(nozzle.thrust)) and not (np.isnan(nozzle.engineMassFlow)):
        raise ValueError('You cannot specify both thrust and engine mass flow, specify one or the other')
    if np.isnan(nozzle.thrust):
        nozzle.thrust                   = nozzle.ceaOutput.nozzlePerformance['ambientISP[s]'] * 9.81 * nozzle.engineMassFlow
    elif np.isnan(nozzle.engineMassFlow):
        nozzle.engineMassFlow           = nozzle.thrust / (nozzle.ceaOutput.nozzlePerformance['idealISP[s]'] * 9.81)
    # Exit Pressure or Expansion Ratio
    if not (np.isnan(nozzle.targetExitPressure)) and not (np.isnan(nozzle.expansionRatio)):
        raise ValueError('You cannot specify both nozzle exit pressure and expansion ratio, specify one or the other')
    if np.isnan(nozzle.targetExitPressure):
        nozzle.targetExitPressure       = nozzle.ceaOutput.ceaResults['exitPressure']
    elif np.isnan(nozzle.expansionRatio):
        nozzle.expansionRatio           = nozzle.ceaOutput.ceaResults['expansionRatio']

    # Which requested quantity binds the geometry. 'areaRatio' cuts the wall at the requested
    # expansion ratio and reports the length that follows, which is the method NASA SP-8120
    # attributes to Ahlberg et al. 'length' cuts at the requested fraction of the conical
    # reference instead and reports whatever area ratio it lands on. A design cannot deliver
    # both, so which one binds has to be said rather than inferred.
    if not isinstance(getattr(nozzle, 'truncateOn', None), str):
        nozzle.truncateOn = 'areaRatio'
    if nozzle.truncateOn not in ('areaRatio', 'wallPressure', 'length'):
        raise ValueError(f"truncateOn must be 'areaRatio', 'wallPressure' or 'length', not "
                         f"'{nozzle.truncateOn}'")

    # Characteristics launched from the throat arc. Everything the contour delivers converges
    # with this; see docs/NozzleContourValidation.md for how much is left at the default.
    requested = getattr(nozzle, 'numCharacteristicsRequested', None)
    nozzle.numCharacteristicsRequested = 50 if requested in (None, [], '') else int(requested)
    nozzle.chamberRGasConstant          = 8314 / nozzle.ceaOutput.ceaResults['combustionChamberMolecularWeight']
    nozzle.chamberGamma                 = nozzle.ceaOutput.ceaResults['combustionChamberGamma']
    nozzle.throatGamma                  = nozzle.ceaOutput.ceaResults['throatGamma']
    nozzle.chamberStagnationTemperature = nozzle.ceaOutput.ceaResults['combustionChamberTemperature']
    nozzle.maxAdiabaticVelocity         = np.sqrt(nozzle.chamberGamma * nozzle.chamberRGasConstant) * \
                                        np.sqrt(2 * nozzle.chamberStagnationTemperature / (nozzle.chamberGamma - 1))
    nozzle.exitMachNumber               = nozzle.ceaOutput.ceaResults['exitMach']
    nozzle.idealMachNumber              = np.sqrt(2/(nozzle.chamberGamma - 1) * ((nozzle.chamberPressure / nozzle.targetExitPressure)** \
                                                                                ((nozzle.chamberGamma - 1) / nozzle.chamberGamma) - 1))
    nozzle.epsilonSauer                 = (nozzle.throatRadiusNonDimensional / 8) * np.sqrt(2 * (nozzle.chamberGamma + 1) * \
                                            nozzle.throatRadiusNonDimensional / nozzle.throatInletCurvatureNonDimensional)
    nozzle.flowParameterSauer           = np.sqrt(2 / ((nozzle.chamberGamma + 1) * nozzle.throatRadiusNonDimensional * nozzle.throatInletCurvatureNonDimensional))

    # Derive optional inputs from config file
    if isinstance(inputsPath, str) and not debugMode:
        if np.isnan(nozzle.coolantClass):
            nozzle.coolantClass = 'oxidizer'
        if np.isnan(nozzle.coolant):
            # Get coolant species from coolant selection
            if nozzle.coolantClass == 'fuel':
                nozzle.coolant = nozzle.Fuel
            elif nozzle.coolantClass == 'oxidizer':
                nozzle.coolant = nozzle.Oxidizer
        if np.isnan(nozzle.coolantMassFlow):
            # Get coolant mass flow rate from O/F            
            if nozzle.coolantClass == 'fuel':
                nozzle.coolantMassFlow = nozzle.engineMassFlow / (1 + nozzle.OFRatio)
            elif nozzle.coolantClass == 'oxidizer':
                nozzle.coolantMassFlow = nozzle.engineMassFlow / (1 + 1 / nozzle.OFRatio)
        if type(nozzle.truncationMethod) != str:
            # Assume untruncated
            nozzle.truncationMethod = 'none'
        if not hasattr(nozzle, 'material') or type(nozzle.material) != str:
            # Assume untruncated
            nozzle.material = 'cu'
