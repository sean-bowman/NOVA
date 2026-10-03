
# -- NOVA: Fluid Thermophysical Properties -- #

'''

One equation-of-state accessor with two backends, so every module that needs a fluid property
calls the same function regardless of what is installed on the machine running it.

'fluidProps' is the entry point the rest of the suite should call. It dispatches to 'refWrap'
(REFPROP) when a REFPROP installation is found, and falls back to 'coolWrap' (CoolProp)
otherwise, so the same call site runs on a machine with or without a REFPROP license. Calling
'refWrap' or 'coolWrap' directly forces a specific backend.

'fluidView' builds carpet-plot sweeps of a property over two independent variables, with
session and multi-user hooks for running a sweep as a background job rather than inline.

Neither backend reports a failure the same way. CoolProp raises. REFPROP returns: it sets an
error code and writes a marker into the output slot it could not fill, and the marker is a
number, around minus ten million, that reads as a property to anything that does not check for
it. 'checkREFPROPResult' is what checks, on every call, so a state REFPROP cannot evaluate stops
the run where it happened instead of propagating a marker into the physics.

Author: Sean Bowman

'''

import os
from typing import Any, Optional

import numpy as np

from .errors import REFPROPError

# What REFPROP writes into an output slot it has no answer for. These are returned in place of a
# property rather than raised, and the first two can arrive with the error code still zero, so a
# caller that reads the output without checking takes roughly minus ten million for a property.
REFPROPMARKERS = {
    -9999990.0: 'no value was calculated for this input',
    -9999970.0: 'the calculation failed',
    -9999950.0: 'the value is stored in another field rather than the output',
}

# Permissive numeric-input alias: these helpers accept arrays, lists, or scalars
# interchangeably. Using this keeps static analysis from flagging valid array-like
# call sites while documenting intent.
ArrayLike = np.ndarray | list | float | int

# ctREFPROP (This needs to be a global import instead of a nested local import because refWrap sometimes
# is called within a loop and re-importing this module each time refWrap is called makes it take FOREVER)
try:
    from ctREFPROP.ctREFPROP import REFPROPFunctionLibrary
except:
    print(f'Uh oh, ctREFPROP isn\'t found. You won\'t be able to call REFPROP. You can to pip install that with \'pip install -U ctREFPROP\'.')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Property accessors -- #
#--------------------------------------------------------------------------------------------------------------------------#

def checkREFPROPResult(result, species: str, inputTypes: str, outputTypes: str,
                       inputTypeFirst: float, inputTypeSecond: float) -> None:

    '''

    Refuse a REFPROP result that does not carry the properties it was asked for.

    Two checks, because REFPROP reports a failure two ways. Its error code is positive on an
    error and negative on a warning, and the message beside it already names the routine and the
    reason, so an error is raised with REFPROP's own words. Separately, an output slot it could
    not fill holds one of the markers in REFPROPMARKERS, which can arrive with the code still
    zero: a property that does not apply at the state asked for comes back that way.

    A phase request is the one case where a marker is the normal answer. REFPROP has no numeric
    phase, so it writes -9999950 into the output and puts the descriptor in the units field,
    which is what `refWrap` returns for that call. The marker check is skipped where the request
    includes a phase, and the error code is still checked.

    Parameters:
    -----------
    result : Any
        What REFPROPdll returned, carrying `Output`, `ierr` and `herr`.
    species : str
        Fluid the call was for.
    inputTypes, outputTypes : str
        The call's input and output type strings.
    inputTypeFirst, inputTypeSecond : float
        The two state values the call was made at.

    Raises:
    -------
    REFPROPError
        If REFPROP set an error code, or returned a marker in place of a property.

    '''

    requested = outputTypes.split(' ')
    state     = f'{inputTypes} = {inputTypeFirst}, {inputTypeSecond}'

    errorCode = int(getattr(result, 'ierr', 0) or 0)
    if errorCode > 0:
        # REFPROP's own message ends with a period of its own more often than not
        message = str(getattr(result, 'herr', '') or '').strip().rstrip('. ')
        raise REFPROPError(
            message = f'REFPROP could not evaluate {outputTypes} for {species} at {state}: '
                      f'{message or "no message given"}.',
            species = species, errorCode = errorCode, requested = outputTypes)

    if 'PHASE' in (name.upper() for name in requested):
        return

    values = list(getattr(result, 'Output', [])[0:len(requested)])
    for name, value in zip(requested, values):
        if float(value) in REFPROPMARKERS:
            raise REFPROPError(
                message = f'REFPROP returned no value for {name} on {species} at {state}: '
                          f'{REFPROPMARKERS[float(value)]}. The marker it returns in that slot '
                          f'reads as a property if it is not checked for.',
                species = species, errorCode = errorCode, requested = outputTypes)

def refWrap(species: str, inputTypes: str, outputTypes: str, inputTypeFirst: float, inputTypeSecond: float, mixtureRatio: list[float] = [1.0], units: bool = False) -> float | list[float] | str | list[str]:

    '''
    
    This function acts as a simple wrapper for REFPROP.

    The function structures the input to the python REFPROP extension in such a
    way that the wrapping function can be easily structured in the following
    format:

    ---------------------------------------------------------------------------
                                    INPUTS
    ---------------------------------------------------------------------------
    - Fluid Species                                   [case insensitive string]

    - Input Types         [case insensitive string of 2 values (no delimiters)]
        Supported Inputs:
        + 'T'                                    specifying fluid [Temperature]
        + 'P'                                       specifying fluid [Pressure]
        + 'D'                                        specifying fluid [Density]
        + 'E'                                specifying fluid [Internal Energy]
        + 'H'                                       specifying fluid [Enthalpy]
        + 'S'                                        specifying fluid [Entropy]
        + 'Q'                                        specifying fluid [Quality]
        i.e. 'TP' specifies [Temperature,Pressure] inputs

    - Output Types                    [space delimited case insensitive string]
        Supported input list can be found in REFPROP DOCUMENTATION (link
        below)
        i.e. 'D Cp Cp/Cv' specifies [density , specific heat , gamma] outputs

    - First Input Type                                           [Mass Base SI]
        i.e. for 'TP' input types, this input will be Temeprature [K]

    - Second Input Type                                          [Mass Base SI]
        i.e. for 'TP' input types, this input will be Pressure [Pa]

    ***NOTE:
    All input types are presented in [Mass Base SI] units i.e. [K , Pa , kg/m^3 , etc]

    ---------------------------------------------------------------------------
                                OPTIONAL INPUTS
    ---------------------------------------------------------------------------
    - Mixture ratio
        + If the fluid species being passed in is a mixture of 2 or more fluids
          the optional input 'mixtureRatio' may be passed in to specify the
          mixture ratio.
    
    - Units
        + If the user wants to return the units of the relevant property instead
          of the value of the property itself the 'units' value can be set to
          the boolean True.

    ---------------------------------------------------------------------------
                                    OUTPUTS
    ---------------------------------------------------------------------------
    refWrap can handle an arbitrary number of outputs, saved in the order that
    the outputs are specified.

    Example function call 1: Thermophysical Properties

    rho, mu, K, Cp = refWrap('O2','TP','D VIS TCX Cp',350,5e6)

    unpacks a REFPROP array for Oxygen at 350 [K] and 5 [MPa] containing:

    - Density [kg/m^3]
    - Dynamic Viscosity [Pa-s]
    - Thermal Conductivity [W/m-K]
    - Const. Pres. Specific Heat [J/kg-K]

    and returns stored variables for each property.

    Example function call 2: Saturation Properties

    T_sat = refWrap('O2','PQ','T',101325,0)

    returns the saturation temperature of Oxygen at 101325 [Pa] assuming the
    fluid is all liquid (i.e. vapor quality = 0).

    ---------------------------------------------------------------------------

    To call the phase of a fluid, simply pass the string 'PHASE' as the output
    type for the call to refWrap. The function will return a 1 x n character
    array specifying the phase of the fluid at the passed in input types.

    *NOTE*: Calling phase as well as other thermophysical properties will
    return the phase as an error message (-9999950) because the Python output
    structure does not store any value for the string output of 'PHASE' in the
    Output field. When calling the phase of a fluid, do so separately from
    other thermophysical property calls.

    ---------------------------------------------------------------------------
    LINK TO REFPROP DOCUMENTATION
    ---------------------------------------------------------------------------
    For information about the unit system, full input list, and REFPROP output array see:
    https://refprop-docs.readthedocs.io/en/latest/DLL/high_level.html#f/_/REFPROPdll

    *NOTE*: REFPROP marks an output slot it cannot fill rather than failing the call,
    with -9999990 where no value was calculated for the input, -9999970 where the
    calculation failed, and -9999950 where the value is stored in another field than
    the Output structure. None of these reaches a caller: 'checkREFPROPResult' raises
    'REFPROPError' on them, and on REFPROP's own error code, before anything is returned.
    The one exception is a phase request, where -9999950 in the output is the normal
    answer and the descriptor is read from hUnits instead.

    '''

    # Define location where REFPROP is stored and let the dll know
    rootUsers                = os.path.expanduser('~') + '\\REFPROP'
    rootProgramFilesx86      = 'C:\\Program Files (x86)\\REFPROP'
    REFPROPinUsers           = os.path.exists(rootUsers)
    REFPROPinProgramFilesx86 = os.path.exists(rootProgramFilesx86)

    if (REFPROPinUsers is False) and (REFPROPinProgramFilesx86 is False):
        raise Exception(f'Uh oh, REFPROP isn\'t found at Users\\%YOURUSERNAME%\\REFPROP or C:\\Program Files (x86)\\REFPROP')

    # Will default to User directory even if both are True because if statements check top-down
    if REFPROPinUsers is True:
        RP = REFPROPFunctionLibrary(rootUsers)
        RP.SETPATHdll(rootUsers)
    elif REFPROPinProgramFilesx86 is True:
        RP = REFPROPFunctionLibrary(rootProgramFilesx86)
        RP.SETPATHdll(rootProgramFilesx86)

    # Separate the outputs and count them
    outputTypesSplit = outputTypes.split(" ")
    numOutputs = len(outputTypesSplit)

    iUnits = RP.GETENUMdll(0,"MASS BASE SI").iEnum # Setting units to Mass Base SI
    iMass = 1                                      # 0: molar fractions; 1: mass fractions (for mixtures)
    iFlag = 0                                      # 0: don't call SATSPLN; 1: call SATSPLN

    # Structure the call to REFPROP
    x = RP.REFPROPdll(species,inputTypes,outputTypes,iUnits,iMass,iFlag,inputTypeFirst,inputTypeSecond,mixtureRatio)

    # REFPROP answers a call it could not make by writing a marker into the output and setting an
    # error code, not by raising, so the result is checked before any of it is returned.
    checkREFPROPResult(x, species, inputTypes, outputTypes, inputTypeFirst, inputTypeSecond)

    # If only one value output is asked for, return it
    if (numOutputs == 1) and (outputTypesSplit[0] != 'PHASE') and (units is False):
        return x.Output[0]
    # If unit output is asked for, or if the only output is the fluid phase, return that instead
    elif ((numOutputs == 1) and (outputTypesSplit[0] != 'PHASE') and (units is True)) or (outputTypes == 'PHASE'):
        return x.hUnits
    # If multiple unit outputs are asked for, warn user that only unit of first output can be returned
    elif (numOutputs > 1) and (outputTypesSplit[0] != 'PHASE') and (units is True):
        print(f'Only first output can return units, sorry. If you want multiple units you have to make multiple calls.')
        return x.hUnits
    # Otherwise, make a list to hold all of the outputs and unpack each one into the subsequent output
    # This is specifically a list so that python doesn't return a generator object but instead the values
    else:
        return list(outputValue for outputValue in x.Output[0:numOutputs])

def coolWrap(species: str, inputTypes: str, outputTypes: str, inputTypeFirst: float, inputTypeSecond: float, mixtureRatio: list[float] = [1.0], units: bool = False) -> float | list[float] | str | list[str]:

    '''

    CoolProp implementation of refWrap, used as a fallback when REFPROP is not
    installed. The signature, unit system (mass-base SI), and return-value behavior mirror refWrap
    exactly, so the two are interchangeable behind the fluidProps dispatcher.

    See refWrap for the full description of inputs and outputs. Differences / limitations:

    - Single-component fluids only. CoolProp's high-level PropsSI cannot take mass-fraction mixtures
      without the REFPROP backend, so a ';'-delimited species (or a mixtureRatio with more than one
      entry) raises NotImplementedError. Install REFPROP if you need mixtures.
    - 'Cp/Cv' is returned as the computed ratio Cpmass / Cvmass.
    - 'PHASE' is returned as a REFPROP-style phase descriptor mapped from CoolProp's PhaseSI.
    - Trivial properties (TCRIT, PCRIT, ...) are evaluated from the fluid name alone.

    The REFPROP <-> CoolProp mapping tables live inside this function (rather than at module scope)
    so the top level of this module stays cleanly collapsible into function and class handles.

    '''

    # Lazy import so this module still loads on machines without CoolProp installed.
    try:
        import CoolProp.CoolProp as CP
    except ImportError:
        raise ImportError('CoolProp isn\'t installed, so coolWrap can\'t run. Install it with \'pip install CoolProp\'.')

    # -- REFPROP -> CoolProp mapping tables -- #

    # refWrap/REFPROP input-pair single-character codes -> CoolProp PropsSI input keys. CoolProp
    # PropsSI is mass-base SI by default (D [kg/m^3], H [J/kg], S [J/kg-K], U [J/kg]), matching the
    # 'MASS BASE SI' unit system refWrap requests from REFPROP, so values are directly interchangeable.
    inputKeys = {
        'T': 'T',   # Temperature        [K]
        'P': 'P',   # Pressure           [Pa]
        'D': 'D',   # Density            [kg/m^3]
        'H': 'H',   # Enthalpy           [J/kg]
        'S': 'S',   # Entropy            [J/kg-K]
        'Q': 'Q',   # Vapor quality      [-]
        'E': 'U',   # Internal energy    [J/kg]  (REFPROP 'E' -> CoolProp 'U')
        'U': 'U',
    }

    # refWrap/REFPROP output codes -> CoolProp PropsSI output key.
    outputKeys = {
        'T':       'T',         # Temperature                 [K]
        'P':       'P',         # Pressure                    [Pa]
        'D':       'D',         # Density                     [kg/m^3]
        'H':       'H',         # Enthalpy                    [J/kg]
        'S':       'S',         # Entropy                     [J/kg-K]
        'E':       'U',         # Internal energy             [J/kg]
        'U':       'U',
        'Cp':      'C',         # Isobaric specific heat      [J/kg-K]
        'Cv':      'O',         # Isochoric specific heat     [J/kg-K]
        'VIS':     'V',         # Dynamic viscosity           [Pa-s]
        'TCX':     'L',         # Thermal conductivity        [W/m-K]
        'W':       'A',         # Speed of sound              [m/s]
        'PRANDTL': 'PRANDTL',   # Prandtl number              [-]
        'Q':       'Q',         # Vapor quality               [-]
    }

    # Trivial (state-independent) outputs that CoolProp evaluates from the fluid name alone.
    trivialKeys = {
        'TCRIT': 'Tcrit',     # Critical temperature  [K]
        'PCRIT': 'pcrit',     # Critical pressure     [Pa]
        'DCRIT': 'rhocrit',   # Critical density      [kg/m^3]
        'TMIN':  'Tmin',      # Minimum temperature   [K]
        'TMAX':  'Tmax',      # Maximum temperature   [K]
        'M':     'molar_mass' # Molar mass            [kg/mol]
    }

    # SI unit strings returned when units = True, keyed by refWrap output code. CoolProp PropsSI is
    # always mass-base SI, so these are fixed rather than queried from the backend.
    unitStrings = {
        'T': 'K', 'P': 'Pa', 'D': 'kg/m^3', 'H': 'J/kg', 'S': 'J/(kg.K)', 'E': 'J/kg', 'U': 'J/kg',
        'Cp': 'J/(kg.K)', 'Cv': 'J/(kg.K)', 'Cp/Cv': '', 'VIS': 'Pa.s', 'TCX': 'W/(m.K)', 'W': 'm/s',
        'PRANDTL': '', 'Q': '', 'TCRIT': 'K', 'PCRIT': 'Pa', 'DCRIT': 'kg/m^3', 'M': 'kg/mol'
    }

    # REFPROP species names CoolProp does not resolve through its own alias table. Most common REFPROP
    # names and chemical formulas (O2, N2, CH4, CO2, N2O, WATER, PARAHYD, ...) are accepted by CoolProp
    # directly, so this map only needs the genuine mismatches.
    refpropToCoolProp = {
        'NITROUS': 'NitrousOxide',
        'R740':    'Argon'
    }

    # CoolProp PhaseSI strings -> the phase descriptors refWrap/REFPROP returns (and that the
    # phase-diagram plotting code downstream compares against).
    phaseMap = {
        'liquid':               'Subcooled liquid',
        'supercritical_liquid': 'Subcooled liquid',
        'gas':                  'Superheated gas',
        'supercritical_gas':    'Superheated gas',
        'supercritical':        'Supercritical',
        'twophase':             'Two-phase'
    }

    # Reject mixtures: the high-level CoolProp interface used here is single-component only.
    if (';' in species) or (len(mixtureRatio) > 1):
        raise NotImplementedError('coolWrap (CoolProp fallback) supports single-component fluids only. Install REFPROP to evaluate mixtures.')

    # Translate the REFPROP species name into a CoolProp-resolvable fluid name
    cleanName = species.strip()
    fluid = refpropToCoolProp.get(cleanName.upper(), cleanName)

    # Separate the outputs and count them (identical convention to refWrap)
    outputTypesSplit = outputTypes.split(' ')
    numOutputs = len(outputTypesSplit)

    # Translate the two input-pair codes into CoolProp keys up front
    in1Key = inputKeys.get(inputTypes[0], inputKeys.get(inputTypes[0].upper()))
    in2Key = inputKeys.get(inputTypes[1], inputKeys.get(inputTypes[1].upper()))
    if (in1Key is None) or (in2Key is None):
        raise KeyError(f'coolWrap has no CoolProp mapping for input types \'{inputTypes}\'.')

    # -- Units request short-circuit -- #
    # refWrap returns the unit string of the (first) output instead of a value when units = True.
    if units and outputTypes != 'PHASE':
        if numOutputs > 1:
            print('Only first output can return units, sorry. If you want multiple units you have to make multiple calls.')
        firstCode = outputTypesSplit[0]
        return unitStrings.get(firstCode, unitStrings.get(firstCode.upper(), ''))

    # Evaluate a single output code at the requested thermodynamic state
    def evaluate(code: str):

        codeUpper = code.upper()

        # Phase: map CoolProp's descriptor onto the REFPROP-style string refWrap returns
        if codeUpper == 'PHASE':
            phase = CP.PhaseSI(in1Key, inputTypeFirst, in2Key, inputTypeSecond, fluid)
            return phaseMap.get(phase, phase)

        # Ratio of specific heats has no direct PropsSI key; compute it
        if codeUpper == 'CP/CV':
            cp = CP.PropsSI('C', in1Key, inputTypeFirst, in2Key, inputTypeSecond, fluid)
            cv = CP.PropsSI('O', in1Key, inputTypeFirst, in2Key, inputTypeSecond, fluid)
            return cp / cv

        # Trivial (state-independent) properties evaluate from the fluid name alone
        if codeUpper in trivialKeys:
            return CP.PropsSI(trivialKeys[codeUpper], fluid)

        # Standard state-dependent property
        cpKey = outputKeys.get(code, outputKeys.get(codeUpper))
        if cpKey is None:
            raise KeyError(f'coolWrap has no CoolProp mapping for output code \'{code}\'. Add it to the outputKeys table or use REFPROP.')
        return CP.PropsSI(cpKey, in1Key, inputTypeFirst, in2Key, inputTypeSecond, fluid)

    # -- Match refWrap's return-shape rules -- #
    # Lone PHASE request -> phase string
    if outputTypes == 'PHASE':
        return evaluate('PHASE')
    # Single value -> scalar float
    if numOutputs == 1:
        return evaluate(outputTypesSplit[0])
    # Multiple values -> list of floats in the requested order
    return [evaluate(code) for code in outputTypesSplit]

def fluidProps(species: str, inputTypes: str, outputTypes: str, inputTypeFirst: ArrayLike, inputTypeSecond: ArrayLike, mixtureRatio: list[float] = [1.0], units: bool = False) -> Any:

    '''

    Unified fluid-property accessor, and the function the rest of the suite should call.

    fluidProps is a thin dispatcher with the exact same I/O contract as refWrap (see refWrap for the
    full input/output description). It routes each call to the best available equation-of-state
    backend:

        1. REFPROP via refWrap   -- used whenever a REFPROP installation is found (highest fidelity,
                                    supports mixtures).
        2. CoolProp via coolWrap -- automatic fallback when REFPROP is not installed (single-
                                    component fluids only).

    This lets the same call site run on machines with or without a REFPROP license. To force a
    specific backend, call refWrap or coolWrap directly.

    The REFPROP-availability check is cached on the function object (fluidProps.refpropAvailable) so
    hot loops (carpet plots, cooling-channel sweeps) don't stat the filesystem on every call.

    ---------------------------------------------------------------------------
                                    EXAMPLE
    ---------------------------------------------------------------------------

    rho, mu, K, Cp = fluidProps('O2', 'TP', 'D VIS TCX Cp', 350, 5e6)

    returns density, dynamic viscosity, thermal conductivity, and isobaric specific heat for Oxygen
    at 350 [K] and 5 [MPa], using REFPROP if present and CoolProp otherwise.

    '''

    # Cache the REFPROP-availability check on the function object on first call
    if not hasattr(fluidProps, 'refpropAvailable'):
        rootUsers           = os.path.expanduser('~') + '\\REFPROP'
        rootProgramFilesx86 = 'C:\\Program Files (x86)\\REFPROP'
        fluidProps.refpropAvailable = os.path.exists(rootUsers) or os.path.exists(rootProgramFilesx86)

    if fluidProps.refpropAvailable:
        return refWrap(species, inputTypes, outputTypes, inputTypeFirst, inputTypeSecond, mixtureRatio = mixtureRatio, units = units)

    return coolWrap(species, inputTypes, outputTypes, inputTypeFirst, inputTypeSecond, mixtureRatio = mixtureRatio, units = units)

class fluidView():

    '''
    
    This class serves as a simple fluid property viewer that can be used to generate tables for reference in the propulsionDesign Streamlit web app.

    Author: Sean Bowman
    Date:   11/20/2025
    
    '''

    def __init__(self) -> None:

        '''
        
        Initialize the fluidProps class.

        '''

        self.fluid = ''
        self.availableFluids = self.getAvailableFluids()

    def getAvailableFluids(self) -> list[str]:

        '''
        
        Returns a list of available fluids and mixtures in REFPROP.

        '''

        import glob

        # Define location where REFPROP is stored and let the dll know
        rootUsers                = os.path.expanduser('~') + '\\REFPROP'
        rootProgramFilesx86      = 'C:\\Program Files (x86)\\REFPROP'
        REFPROPinUsers           = os.path.exists(rootUsers)
        REFPROPinProgramFilesx86 = os.path.exists(rootProgramFilesx86)

        if (REFPROPinUsers is False) and (REFPROPinProgramFilesx86 is False):
            raise Exception(f'Uh oh, REFPROP isn\'t found at Users\\%YOURUSERNAME%\\REFPROP or C:\\Program Files (x86)\\REFPROP')

        # Will default to User directory even if both are True because if statements check top-down
        if REFPROPinUsers is True:
            fluidsDirectory = rootUsers + '\\FLUIDS\\'
            mixturesDirectory = rootUsers + '\\MIXTURES\\'
        elif REFPROPinProgramFilesx86 is True:
            fluidsDirectory = rootProgramFilesx86 + '\\FLUIDS\\'
            mixturesDirectory = rootProgramFilesx86 + '\\MIXTURES\\'

        fluidFiles = glob.glob(os.path.join(fluidsDirectory, '*.FLD'))

        # Extract fluid names (without path and extension)
        availableFluids = [os.path.splitext(os.path.basename(f))[0] for f in fluidFiles]

        mixtureFiles = glob.glob(os.path.join(mixturesDirectory, '*.MIX'))

        # Extract mixture names (without path and extension)
        availableMixtures = [os.path.splitext(os.path.basename(f))[0] for f in mixtureFiles]

        allFluids = availableFluids + availableMixtures

        # Sort alphabetically
        allFluids.sort()

        return allFluids

    def getAvailableProperties(self) -> list[str]:

        '''
        
        Returns a list of available thermophysical properties in REFPROP.

        '''

        import pandas as pd

        # List of common REFPROP output properties in readable form and their corresponding REFPROP labels
        propertiesTable = pd.read_csv('utilsGUI/REFPROPOutputTypesList.csv')
        readableProperties = propertiesTable['Description'].tolist()
        formattedProperties = propertiesTable['Label'].tolist()

        availableProperties = dict(zip(readableProperties, formattedProperties))

        return availableProperties

    def setInputs(self, userInputs: dict) -> None:

        '''

        Sets the user inputs for the fluidView class.

        ---------------------------------------------------------------------------
                                        INPUTS
        ---------------------------------------------------------------------------
        - userInputs
            + 'fluid' : str
                >> Fluid species to analyze
            + 'inputTypes' : list[str]
                >> List of two REFPROP input type codes (e.g., ['T', 'P'])
            + '{InputType}Range' : dict (for each input type)
                >> Dictionary containing 'lowerValue', 'upperValue', 'incrementValue'
            + 'outputTypes' : str
                >> Space delimited string of output types
            + 'mixtureRatio' : list[float]
                >> List of mixture ratios for fluid components

        ---------------------------------------------------------------------------

        '''

        for key, value in userInputs.items():
            setattr(self, key, value)

        # Format fluids list for passing to fluidProps
        if hasattr(self, 'fluids'):
            self.fluid = ';'.join(self.fluids)

        # Format outputs list for passing to fluidProps
        if hasattr(self, 'outputTypes'):
            self.outputTypes = ' '.join(self.outputTypes)

        if hasattr(self, 'outputStyle'):
            self.outputStyle = self.outputStyle

        # Format bounds for passing to fluidView
        if hasattr(self, 'inputTypes'):

            self.inputTypes = ''.join(self.inputTypes)

            if self.outputStyle == 'Carpet Plot over Two Input Ranges':
                self.firstRange = getattr(self, 'firstRange')
                self.secondRange = getattr(self, 'secondRange')
            elif self.outputStyle == 'Plot over One Range, One Constant':
                self.firstRange = getattr(self, 'firstRange')
                self.secondValue = getattr(self, 'secondValue')
            elif self.outputStyle == 'Single Point Calculation':
                self.firstValue = getattr(self, 'firstValue')
                self.secondValue = getattr(self, 'secondValue')

        if hasattr(self, 'mixtureRatio'):
            self.mixtureRatio = self.mixtureRatio

    def generateCarpetPlot(self, sessionId: Optional[str] = None, allocatedCores: Optional[int] = None) -> None:

        '''

        Generates carpet plots of desired thermophysical properties for the selected fluid over specified input ranges for an arbitrary number of outputs.

        ---------------------------------------------------------------------------
                                        INPUTS
        ---------------------------------------------------------------------------
        - sessionId : str, optional
            >> Unique session identifier for the user (e.g., Streamlit session ID)
            >> If None, uses a default session ID
            >> Used for multi-user resource management (max 2 concurrent users, 1 core each)
        - allocatedCores : int, optional
            >> Number of CPU cores pre-allocated for this job (if already allocated by job manager)
            >> If provided, bypasses resource manager allocation (used by background job processor)

        ---------------------------------------------------------------------------
                                        OUTPUTS
        ---------------------------------------------------------------------------
        This function does not return values, it stores arrays in instance variables:
        - self.inputArray1 : np.array of first input values
        - self.inputArray2 : np.array of second input values
        - self.outputs : 3D array of output values
        - self.outputUnits : list of output unit strings

        ---------------------------------------------------------------------------

        '''

        from tqdm import tqdm
        try:
            # Parallel processing module
            from joblib import Parallel, delayed
            self.parallelBool = True
        except:
            self.parallelBool = False

        # If cores already allocated (e.g., from background job processor), use that value
        if allocatedCores is not None:
            print(f'[fluidView] Using pre-allocated {allocatedCores} CPU cores')
            self.allocatedCores = allocatedCores
            useResourceManager = False
        else:
            # Import CPU resource manager for multi-user support with priority-based allocation
            try:
                from utilsGUI.multiUserManager import getResourceManager  # type: ignore[import]  # optional multi-user support
                resourceManager = getResourceManager()

                # Use sessionId if provided, otherwise use a default
                if sessionId is None:
                    sessionId = f'default_session_{os.getpid()}'

                # Allocate CPU cores for this user based on priority (1st user: 50%, 2nd: 25%, 3+: 1 core)
                allocatedCores = resourceManager.allocateCpuCores(sessionId)
                self.allocatedCores = allocatedCores
                useResourceManager = True
            except Exception as e:
                # Fallback if resource manager is not available
                print(f'Warning: CPU resource manager not available ({e}). Using all cores.')
                allocatedCores = -1  # Use all cores as fallback
                useResourceManager = False

        # Unpack bounds
        # lowerInput1, upperInput1, incrementInput1, lowerInput2, upperInput2, incrementInput2 = self.bounds

        # Separate the outputs and count them
        outputTypesSplit = self.outputTypes.split(' ')
        numOutputs = len(outputTypesSplit)

        # Make arrays that hold all the input values the user asked for
        # self.inputArray1 = np.arange(lowerInput1, upperInput1, incrementInput1)
        # self.inputArray2 = np.arange(lowerInput2, upperInput2, incrementInput2)
        self.inputArray1 = self.firstRange
        self.inputArray2 = self.secondRange
        numRows, numCols = len(self.inputArray1), len(self.inputArray2)

        # List comprehension to make a big empty 3D array to hold all the outputs
        holdOutputs = [[[0 for cols in range(numCols)] for rows in range(numRows)] for sheets in range(numOutputs)]

        # Loop over all combinations of inputs for each output
        if self.parallelBool:
            # Run fluidProps in parallel with CPU resource limiting for multi-user support
            # allocatedCores is either:
            #   - A positive integer representing the number of cores allocated to this user
            #   - -1 to use all available cores (fallback if resource manager unavailable)
            output = Parallel(n_jobs = allocatedCores)(delayed(fluidProps)(self.fluid, self.inputTypes, self.outputTypes, self.inputArray1[i], self.inputArray2[j], self.mixtureRatio) \
                                        for i in tqdm(range(numRows)) for j in range(numCols))
            holdOutputs = np.array(output).T.reshape(numOutputs, numRows, numCols)

            # Release session from resource manager after computation completes
            if useResourceManager:
                try:
                    resourceManager.release_session(sessionId)
                except:
                    pass  # Ignore cleanup errors
        else:
            # Loop over the ranges manually and call fluidProps individually for each input pair
            for col, input2 in tqdm(enumerate(self.inputArray2)):
                for row, input1 in enumerate(self.inputArray1):
                    outputs = fluidProps(self.fluid, self.inputTypes, self.outputTypes, input1, input2, mixtureRatio = self.mixtureRatio)
                    for outputNumber in range(numOutputs):
                        holdOutputs[outputNumber][row][col] = outputs[outputNumber]

        # Create and store the units for each output (useful for Z-axis label of plots)
        outputUnits = [0 for _ in range(numOutputs)]
        for i in range(numOutputs):
            outputUnits[i] = fluidProps(self.fluid, self.inputTypes, self.outputTypes.split(' ')[i], self.inputArray1[0], self.inputArray2[0], mixtureRatio = self.mixtureRatio, units = True)

        self.outputs = holdOutputs
        self.outputUnits = outputUnits

    def generatePhaseDiagram(self, bounds: list[float]) -> None:

        '''
        
        Generates a phase diagram for the selected fluid over specified temperature and pressure ranges.

        ---------------------------------------------------------------------------
                                        INPUTS
        ---------------------------------------------------------------------------
        - Lower Bound Temperature                                               [K]
        - Upper Bound Temperature                                               [K]
        - Temperature Increments                                                [K]
        - Lower Bound Pressure                                                 [Pa]
        - Upper Bound Pressure                                                 [Pa]
        - Pressure Increments                                                  [Pa]

        ---------------------------------------------------------------------------
                                        OUTPUTS
        ---------------------------------------------------------------------------
        This function does not return values, it just makes the phase diagram.

        ---------------------------------------------------------------------------

        '''

        from tqdm import tqdm
        try:
            # Parallel processing module
            from joblib import Parallel, delayed
            self.parallelBool = True
        except:
            self.parallelBool = False

        # Unpack bounds
        lowerTemperature, upperTemperature, temperatureIncrement, lowerPressure, upperPressure, pressureIncrement = bounds

        # Make arrays that hold all the temperature and pressure values the user asked for
        temperatureArray = np.arange(lowerTemperature, upperTemperature, temperatureIncrement)
        pressureArray    = np.arange(lowerPressure, upperPressure, pressureIncrement)
        numRows, numCols = len(temperatureArray), len(pressureArray)

        numOutputs = 1
        outputTypes = 'PHASE'
        holdOutputs = [[[0 for cols in range(numCols)] for rows in range(numRows)] for sheets in range(numOutputs)]
        phaseOutputs = [[0 for cols in range(numCols)] for rows in range(numRows)]

        # Loop over all combinations of T and P for each output
        if self.parallelBool:
            # Run fluidProps in parallel using all of the CPU resources available
            output = Parallel(n_jobs = -1)(delayed(fluidProps)(self.fluid, 'TP', outputTypes, temperatureArray[i], pressureArray[j], self.mixtureRatio) \
                                        for i in tqdm(range(numRows)) for j in range(numCols))
            holdOutputs = np.array(output).T.reshape(numOutputs, numRows, numCols)
        else:
            # Loop over the ranges manually and call fluidProps individually for each (T, P) pair (SLOW AF)
            for col, pressure in tqdm(enumerate(pressureArray)):
                for row , temperature in enumerate(temperatureArray):
                    outputs = fluidProps(self.fluid, 'TP', outputTypes, temperature, pressure, mixtureRatio = self.mixtureRatio)
                    for outputNumber in range(numOutputs):
                        if numOutputs == 1:
                            holdOutputs[outputNumber][row][col] = outputs
                        else:
                            holdOutputs[outputNumber][row][col] = outputs[outputNumber]

        # Assign a numeric value to each phase type to make contour plotting easier
        for i in range(len(holdOutputs[0][:])):
            phaseOutputs[i][:] = [1 if output      == 'Subcooled liquid' \
                                  else 2 if output == 'Superheated gas' \
                                  else 3 if output == 'Supercritical' \
                                  else 4 if output == 'Two-phase'
                                  else 0 for output in holdOutputs[0][i]]

        self.phaseOutputs = phaseOutputs
        self.holdOutputs = holdOutputs

    def generatePlotOverSingleRange(self) -> None:

        '''
        
        Generates plots of desired thermophysical properties for the selected fluid over a specified input range with one constant input.

        ---------------------------------------------------------------------------
                                        INPUTS
        ---------------------------------------------------------------------------

        ---------------------------------------------------------------------------
                                        OUTPUTS
        ---------------------------------------------------------------------------
        This function does not return values, it stores arrays in instance variables:
        - self.inputArray1 : np.array of first input values
        - self.outputs : 2D array of output values
        - self.outputUnits : list of output unit strings

        ---------------------------------------------------------------------------

        '''

        # Separate the outputs and count them
        outputTypesSplit = self.outputTypes.split(' ')
        numOutputs = len(outputTypesSplit)

        # Make arrays that hold all the input values the user asked for
        # self.inputArray1 = np.arange(lowerInput1, upperInput1, incrementInput1)
        # self.inputArray2 = np.arange(lowerInput2, upperInput2, incrementInput2)
        self.inputArray1 = self.firstRange
        self.inputValue2 = self.secondValue
        numRows, numCols = len(self.inputArray1), 1

        # List comprehension to make a big empty 3D array to hold all the outputs
        holdOutputs = [[[0 for cols in range(numCols)] for rows in range(numRows)] for sheets in range(numOutputs)]

        # Loop over the ranges manually and call fluidProps individually for each input pair
        for row, input1 in enumerate(self.inputArray1):
            outputs = fluidProps(self.fluid, self.inputTypes, self.outputTypes, input1, self.inputValue2, mixtureRatio = self.mixtureRatio)
            for outputNumber in range(numOutputs):
                holdOutputs[outputNumber][row][0] = outputs[outputNumber]

        # Create and store the units for each output (useful for Z-axis label of plots)
        outputUnits = [0 for _ in range(numOutputs)]
        for i in range(numOutputs):
            outputUnits[i] = fluidProps(self.fluid, self.inputTypes, self.outputTypes.split(' ')[i], self.inputArray1[0], self.inputValue2, mixtureRatio = self.mixtureRatio, units = True)

        self.outputs = holdOutputs
        self.outputUnits = outputUnits

    def calculateSinglePoint(self) -> list[float]:

        '''
        
        Calculates desired thermophysical properties for the selected fluid at a single point defined by two input values.

        ---------------------------------------------------------------------------
                                        INPUTS
        ---------------------------------------------------------------------------

        ---------------------------------------------------------------------------
                                        OUTPUTS
        ---------------------------------------------------------------------------
        This function returns a list of output values:
        - outputs : list of output values

        ---------------------------------------------------------------------------

        '''

        # Separate the outputs and count them
        outputTypesSplit = self.outputTypes.split(' ')
        numOutputs = len(outputTypesSplit)

        outputs = fluidProps(self.fluid, self.inputTypes, self.outputTypes, self.firstValue, self.secondValue, mixtureRatio = self.mixtureRatio)

        # Create and store the units for each output (useful for Z-axis label of plots)
        outputUnits = [0 for _ in range(numOutputs)]
        for i in range(numOutputs):
            outputUnits[i] = fluidProps(self.fluid, self.inputTypes, self.outputTypes.split(' ')[i], self.firstValue, self.secondValue, mixtureRatio = self.mixtureRatio, units = True)

        self.outputs = outputs
        self.outputUnits = outputUnits

    def propertiesCSVgenerator(self, Species: str, lowerTemperature: float, upperTemperature: float, temperatureIncrement: float,
                               lowerPressure: float, upperPressure: float, pressureIncrement: float, outputproperties: list[str],
                               toggleIsobaric: bool = False, customDirectory: str = None) -> None:
        '''
        This function will generate a CSV file containing thermophysical properties over specified ranges of pressure and temperature. 
        It lives within the fluidView class for easy access to fluidView attributes.
        ---------------------------------------------------------------------------
                                        INPUTS  
        ---------------------------------------------------------------------------
        Species: str
            >> Fluid species to analyze
        lowerTemperature: float
            >> Lower bound temperature [K]
        upperTemperature: float
            >> Upper bound temperature [K]
        temperatureIncrement: float
            >> Temperature increment [K]
        lowerPressure: float
            >> Lower bound pressure [Pa]
        upperPressure: float: float
            >> Upper bound pressure [Pa]
        pressureIncrement: float
            >> Pressure increment [Pa]
        outputproperties: list[str]
            >> List of output properties from which a CSV will be generated for each property
        toggleIsobaric: bool
            >> If True, generates data for density and specific heat at a constant pressure 
            averagePressure = (lowerPressure + upperPressure)/2
        customDirectory: str
            >> If specified, saves the output CSV files to the given directory instead of the current working directory
        
        
        ---------------------------------------------------------------------------
                                        OUTPUTS
            >> CSV file containing thermophysical properties over specified ranges of pressure and temperature
            saved to '{species}_{property}.csv' in {species}_properties folder in current working directory or a specified path.

        '''
        import numpy as np
        import pandas as pd
        import os
        import shutil
        import decimal
        from tqdm import tqdm

        # This is the current working directory
        cwd = os.getcwd()

        # Check is Custom Directory is specified
        if customDirectory is not None:
            cwd = customDirectory

        # This will be used for Cp and density when only dealing with temperature and is taken at the midpoint of pressure range
        pressureMidpoint = (lowerPressure + upperPressure)/2

        # Make a directory where we save new properties
        propertyFolder = Species + '_properties'
        pathPropertyFolder = os.path.join(cwd, propertyFolder)

        # This wall pulled from internet and checks to see if a directory exists, and if it does it deletes it. (https://stackoverflow.com/questions/43765117/how-to-check-existence-of-a-folder-with-python-and-then-remove-it)
        if os.path.exists(pathPropertyFolder) and os.path.isdir(pathPropertyFolder):
            shutil.rmtree(pathPropertyFolder)

            ## NOTE: This does not work until I get on a modern branch that supports exception handling properly
            # try:
            #     shutil.rmtree(pathPropertyFolder)
            # except Exception as e:
            #     raise Exception(f'Could not remove existing directory. Please close any open files in the directory and try again. \n {e}')
            #     # print(f'Excel is open you fucking idiot. Close it before running this function again. \n {e}')

        os.mkdir(pathPropertyFolder)

        # Now we will package temperature and pressure arrays
        temperatureArray = np.arange(lowerTemperature, upperTemperature + temperatureIncrement, temperatureIncrement)
        pressureArray    = np.arange(lowerPressure, upperPressure + pressureIncrement, pressureIncrement)

        # Ensure upper bounds are included in arrays
        if temperatureArray[-1] < upperTemperature:
            temperatureArray = np.append(temperatureArray, upperTemperature)
        if pressureArray[-1] < upperPressure:
            pressureArray = np.append(pressureArray, upperPressure)

        # Now we get length for output property arrays
        numTemperatures = np.size(temperatureArray)
        numPressures    = np.size(pressureArray)

        # Now we check if isobaric toggle is on, and if so we generate CSVs for density and specific heat at constant pressure irregardless of previous CSVs
        if toggleIsobaric:
            # constant pressure so we do not need to loop over pressures, just take the midpoint pressure
            for property in ['D', 'Cp']:
                # Prepare an empty array to hold output property values
                propertyValues = np.zeros((numTemperatures, 1))

                # Now we loop over each temperature and get the property value at midpoint pressure
                for i, T in enumerate(temperatureArray):
                    propertyValues[i, 0] = fluidProps(Species, 'TP', property, T, pressureMidpoint)

                # Now we prepare to save the CSV
                df = pd.DataFrame(propertyValues, index=temperatureArray, columns=[f'{property}'])
                # Now we make the headers in data frame Temperature [K] and Property
                df.index.name = 'Temperature [K]'

                # Save the DataFrame to a CSV file
                csvFilename = f"{Species}_{property}_isobaric.csv"
                csvFilePath = os.path.join(pathPropertyFolder, csvFilename)
                df.to_csv(csvFilePath)

        # Now we loop over each output property and generate a CSV for each and output in form of T, P, propertyValue irregardless of isobaric toggle
        for property in tqdm(outputproperties):
            # Prepare an empty array to hold output property values
            propertyValues = np.zeros((numTemperatures, numPressures))

            # Now we loop over each temperature and pressure and get the property value
            for i, T in enumerate(temperatureArray):
                for j, P in enumerate(pressureArray):
                    propertyValues[i, j] = fluidProps(Species, 'TP', property, T, P)

            # Now we format the DataFrame with repeating pressures and 3 columns (T, P, propertyValue)
            propertyValues = np.reshape(propertyValues,-1, order='F')
            headerProperties = ['Temperature [K]', 'Pressure [Pa]', f'{property}']
            temperatureColumn = np.tile(temperatureArray, numPressures)
            pressureColumn = np.repeat(pressureArray, numTemperatures)
            data = {headerProperties[0]: temperatureColumn, headerProperties[1]: pressureColumn, headerProperties[2]: propertyValues}
            df = pd.DataFrame(data)

            # Save the DataFrame to a CSV file
            csvFilename = f"{Species}_{property}.csv"
            csvFilePath = os.path.join(pathPropertyFolder, csvFilename)
            df.to_csv(csvFilePath, header=True, index=False)
