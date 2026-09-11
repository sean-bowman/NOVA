# -- NOVA: Configuration Reader -- #

'''

Turning a configuration into the state a run works from.

A configuration reaches NOVA two ways, and they are the same path:

    a JSON file      a path ending in .json, loaded and then read as a dictionary
    a dictionary     the same fields already loaded, which is how the GUI supplies them

The conventions the fields follow are worth stating rather than discovering.

**Unset is NaN, not None.** A null in JSON becomes NaN on the
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

from .utils import InvalidInputError
from .ceaInterface import CEA

def setInputs(nozzle, inputsPath: str | dict, debugMode: bool = False) -> None:

    '''

    Configure nozzle design parameters from a configuration file or dictionary.

    This method initializes all nozzle design parameters including contour definition,
    regenerative cooling jacket specifications, volute geometry, and program options.

    Parameters:
    -----------
    inputsPath : str | dict
        Configuration source - can be:
        - str: path to a .json configuration
        - dict: the same keys already loaded, which is what the GUI hands over
    debugMode : bool, optional
        True makes a station that fails to converge dump its local state rather than
        raising. It is a solver flag, not an input format. Default is False.

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
        - Contour type selection (contourType: 'trad')
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
    - Some parameters (maxWallTemperature, infillThickness) are broadcast to arrays if scalar

    Raises:
    -------
    InvalidInputError
        If the configuration cannot be read, or its design point cannot be closed.

    '''

    warnings.filterwarnings('ignore')

    # -- Determine input type -- #

    # debugMode is a solver flag rather than an input format: it makes a station that fails
    # to converge dump its local state instead of raising. channelSizing reads it.
    nozzle.debugMode = debugMode

    # Inputs from a JSON config file. generateNozzle() defaults to
    # assets/nozzleConfig.json, so this must be handled before the
    # spreadsheet branch below, which would otherwise hand a .json path to
    # the Excel reader. The keys are identical to the GUI dict form, so the
    # file is simply loaded and allowed to fall through to that branch.
    if isinstance(inputsPath, str) and inputsPath.lower().endswith('.json'):
        import json
        with open(inputsPath, 'r') as configFile:
            inputsPath = json.load(configFile)

    # Inputs from the GUI
    if isinstance(inputsPath, dict):

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
        # Optional, and defaulted to the physically right answer. 'static' reproduces
        # results recorded before the recovery temperature was carried through to the
        # solve, and understates the flux by the whole recovery rise.
        nozzle.drivingTemperatureModel        = inputsPath.get('drivingTemperatureModel',
                                                              'recovery')
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
