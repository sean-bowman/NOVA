
# -- Collection of commonly used functions [propulsionDesign] -- #

'''

This utilities python file serves as a function repository that can be added to any python project to
quickly access commonly used functions in propulsionDesign.

These functions are:

--------------------------------------------------------------------------------------------------------------------------------------------
Fluid Property Functions
--------------------------------------------------------------------------------------------------------------------------------------------
> refWrap
    >> Pull fluid thermophysical properties from the REFPROP EOS model
> coolWrap
    >> Pull fluid thermophysical properties from CoolProp (same I/O as refWrap; fallback backend)
> fluidProps
    >> Unified property accessor; dispatches to refWrap (REFPROP) if available, else coolWrap (CoolProp)
> isentropicValues
    >> Calculate stagnation properties given static properties
> CEA
    >> Simple wrapper around rocketCEA to make the interface nicer to work with

--------------------------------------------------------------------------------------------------------------------------------------------
Geometry Generation Tools
--------------------------------------------------------------------------------------------------------------------------------------------
> py2cad
    >> Export a .stl file from a surface mesh
> parallelOffset
    >> Offset a parametric curve the same distance everywhere in the curve normal direction
> intersection
    >> Calculate the (x, y) intersection point of two arbitrary curves
> fillet
    >> Create a fillet of desired radius between two linear segments that share a common point
> nonLinspace
    >> Create a vector of 'n' points between specified starting and ending values that vary nonlinearly (a compliment to np.linspace)
> spline3D
    >> Generate a spline of points evenly spaced about the arclength of a collection of (x, y, z) points in 3D space
> filletCurves
    >> Create a smooth transition between two arbitrary curves
> lineIntersection
    >> Calculate their intersection point of two lines where we know one point on each line and the angle each makes with the X axis
> parallelTruncatedIdealContour
    >> A copy of the truncatedIdealContour function from the Nozzle class that is used to parallelize the calculation of thrust coef
> revolveContour
    >> Revolve a 2D contour about a central axis resulting in a surface mesh
> DCM
    >> Given a set of Euler angles and a matrix of values, perform a rotation described by Direction Cosine Matrices

--------------------------------------------------------------------------------------------------------------------------------------------
Data Manipulation Functions
--------------------------------------------------------------------------------------------------------------------------------------------
> secantSolve
    >> Zero a function (linear/nonlinear) using the Secant Method.
> chunkInterpolate
    >> interpolate data to a not strictly increasing x array
> plotSurface
    >> Wrapper for plotting 3D surfaces
> plot3DLine
    >> Wrapper for plotting 3D curves/lines
> plot2DLine
    >> Wrapper for plotting 2D curves/lines
> plot3DGeometry
    >> Wrapper for plotting 3D surface geometry
> writeFile
    >> Wrapper for writing data to a .csv or .txt format

Author: Sean Bowman
Date:   01/24/2024

'''

import os
import io
import contextlib
import numpy as np
import matplotlib.pyplot as plt
import pickle
from typing import Callable, Optional, Any

from . import units

# Permissive numeric-input alias: these helpers accept arrays, lists, or scalars
# interchangeably. Using this keeps static analysis from flagging valid array-like
# call sites while documenting intent.
ArrayLike = np.ndarray | list | float | int

# -- Weird imports that people might not have -- #

# ctREFPROP (This needs to be a global import instead of a nested local import because refWrap sometimes
# is called within a loop and re-importing this module each time refWrap is called makes it take FOREVER)
try:
    from ctREFPROP.ctREFPROP import REFPROPFunctionLibrary
except:
    print(f'Uh oh, ctREFPROP isn\'t found. You won\'t be able to call REFPROP. You can to pip install that with \'pip install -U ctREFPROP\'')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Fluid Property Functions -- #
#--------------------------------------------------------------------------------------------------------------------------#

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

    *NOTE*:
    - A value of -9999990 will be returned by REFPROP if no value is calculated
      for a given input.
    - A value of -9999970 will be returned by REFPROP if an error occurs during
      calculation.
    - A value of -9999950 will be returned by REFPROP if no value is stored in
      the Output structure, but does have values stored in other fields (i.e.
      when calling the phase of a fluid, the field hUnits contains the string
      identifier for the phase, but the Output field will return an error).

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
    so the top level of utils.py stays cleanly collapsible into function and class handles.

    '''

    # Lazy import so utils.py still loads on machines without CoolProp installed.
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

def isentropicValues(machNumber: ArrayLike, stagnationTemperature: ArrayLike, stagnationPressure: ArrayLike, gamma: ArrayLike, gasConstant: ArrayLike) -> tuple:

    '''
    
    Returns (in this order):
    - Temperature
    - Pressure
    - Velocity

    Calculate resultant values via isentropic relations given the flow mach number and
    stagnation values of temperature and pressure as well as flow gamma and specific gas constant.
    These flow values can be obtained from the python CEA wrapper.
    
    '''

    temperature = stagnationTemperature / (1 + ((gamma - 1) / 2) * machNumber**2)
    pressure    = stagnationPressure    / (1 + ((gamma - 1) / 2) * machNumber**2)**(gamma / (gamma - 1))
    velocity    = np.sqrt(gamma * gasConstant * temperature) * machNumber

    return temperature, pressure, velocity

def hoopStressCalculator(pressureDifferential: float, diameter: float, thickness: float = None, hoopStress: float = None) -> float:

    '''
    
    This function is a simple wrapper around the calculation of cylindrical hoop stress for convenience of use.

    The form of the equation is:

    sigma_h = dP * D / 2*t
    
    '''

    # Which version of the problem are we solving
    if thickness is not None and hoopStress is None:
        calculateHoopStress = True
        calculateThickness  = False
    if thickness is None and hoopStress is not None:
        calculateThickness  = True
        calculateHoopStress = False

    # -- Depending on which thing we are calculating, calculate it yo -- #

    # Hoop Stress
    if calculateHoopStress:
        hoopStress = (pressureDifferential * diameter) / (2 * thickness)

    # Wall thickness
    if calculateThickness:
        thickness = (pressureDifferential * diameter) / (2 * hoopStress)

    # Return the relevant calculated component
    if calculateThickness:
        return thickness
    elif calculateHoopStress:
        return hoopStress

def convertToSCFM(fluid: str, massFlowrate: float, temperature: float, pressure: float) -> float:

    '''
    
    Standard Cubic Feet per Minute flowrate conversion calculator.

    Input flowrate is in [kg/s]

    I really hate imperial units, like why do I have to write a function to convert to SCFM like just fucking use metric like an adult.
    
    '''

    # Declare constants
    standardTemperatrue = 288.706 # 60 [degF]
    standardPressure    = units.SCFM_STD_PRESSURE

    # Get fluid density with Refprop
    density = fluidProps(fluid, 'TP', 'D', temperature, pressure)

    # Convert kg/s to m^3/s
    volumetricFlowrate = massFlowrate / density

    # Convert m^3 to ft^3
    imperialFlowrate = volumetricFlowrate / units.M3_PER_FT3

    # Convert ft^3 to SCFM (s to min)
    SCFM = imperialFlowrate * 60

    return SCFM



#--------------------------------------------------------------------------------------------------------------------------#
# -- Geometry Generation Tools -- #
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
    from joblib import Parallel, delayed, cpu_count

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
    
def parallelOffset(xCurve: ArrayLike, yCurve: ArrayLike, offsetDistance: ArrayLike, centralDifference: bool = True) -> tuple:

    '''

    This function takes in the X and Y coordinates of a curve and creates a curve that is
    an equal distance to that curve in the curve normal direction. This acts like a curve offset
    in a traditional CAD software. The equations that drive this process are given as:

    x_parallel = x + (-offset_distance)*dy / sqrt(dx^2 + dy^2)
    y_parallel = y - (-offset_distance)*dx / sqrt(dx^2 + dy^2)

    '''

    # If the user has a constant offset distance, make it into an array for the loop
    if isinstance(offsetDistance, float):
        offsetDistance = offsetDistance * np.ones(len(xCurve))

    # Declare empty arrays
    deltaX = np.zeros(len(xCurve))
    deltaY = np.zeros(len(yCurve))
    xCurveParalleloffset = np.zeros(len(xCurve))
    yCurveParalleloffset = np.zeros(len(xCurve))
    
    # Do numerical derivative for passed in curve
    if centralDifference:
        deltaX = np.gradient(xCurve)
        deltaY = np.gradient(yCurve)
    else:
        for i in range(len(xCurve) - 1):
            deltaX[i] = xCurve[i+1] - xCurve[i]
            deltaY[i] = yCurve[i+1] - yCurve[i]
        deltaX[-1] = deltaX[-2]
        deltaY[-1] = deltaY[-2]

    norm = np.sqrt(deltaX**2 + deltaY**2)

    # Calculate points of parallel offset curve
    xCurveParalleloffset = xCurve + -offsetDistance * deltaY / norm
    yCurveParalleloffset = yCurve - -offsetDistance * deltaX / norm

    return xCurveParalleloffset, yCurveParalleloffset

def intersection(xCurve1: ArrayLike, yCurve1: ArrayLike, xCurve2: ArrayLike, yCurve2: ArrayLike) -> tuple:

    r'''

    Given two line segments segment1 and segment2 of curve1 and curve2 with endpoints:

    segment1 endpoints:  (x1[0], y1[0]) and (x1[-1], y1[-1])
    segment2 endpoints:  (x2[0], y2[0]) and (x2[-1], y2[-1])

    we can write four equations with four unknowns and solve them. The
    four unknowns are a, b, x, and y, where (x, y) is the intersection of
    segment1 and segment2. a is the distance from the starting point of segment1 to the
    intersection relative to the length of segment1, and b is the distance from the
    starting point of segment2 to the intersection relative to the length of segment2.
    For this function, we only care about the intersection point: (x, y).

    The four equations are:

    (x1[-1] - x1[0]) * a = x - x1[0]
    (x2[-1] - x2[0]) * b = x - x2[0]
    (y1[-1] - y1[0]) * a = y - y1[0]
    (y2[-1] - y2[0]) * b = y - y2[0]

    Rearranging and writing in matrix form:

    [dx1    0   -1   0      [a      [-x1[0]
      0    dx2  -1   0   *   b   =   -x2[0]
     dy1    0    0  -1       x       -y1[0]
      0    dy2   0  -1]      y]      -y2[0]]

    This is A*z = B. We can solve for z with z = A\B, where A\B is solvable with numpy.linalg.solve(A, B)

    Once we have our solution, z, we just have to look at a and b to determine
    whether segment1 and segment2 intersect.  If 0 <= a <= 1 and 0 <= b <= 1, then the two
    line segments cross and the intersection point is z[3, 4] = (x, y)
    
    '''

    # Helper functions to calculate moving minimum and maximum for passed in curves
    def movingMin(array):
        if len(array) == 2:
            movingMinimum = np.minimum(array[0],array[1])
        else:
            movingMinimum = np.minimum(array[0:-2],array[1:-1])
        return movingMinimum
    def movingMax(array):
        if len(array) == 2:
            movingMaximum = np.maximum(array[0],array[1])
        else:
            movingMaximum = np.maximum(array[0:-2],array[1:-1])
        return movingMaximum

    # If passed in arrays are lists, make them numpy arrays
    if type(xCurve1) is list:
        xCurve1 = np.array(xCurve1)
    if type(xCurve2) is list:
        xCurve2 = np.array(xCurve2)
    if type(yCurve1) is list:
        yCurve1 = np.array(yCurve1)
    if type(yCurve2) is list:
        yCurve2 = np.array(yCurve2)
    
    # If passed in arrays have no second dimension, give them one for convenience
    if len(xCurve1.shape) < 2:
        xCurve1 = xCurve1.reshape(len(xCurve1),1)
        yCurve1 = yCurve1.reshape(len(yCurve1),1)
    if len(xCurve2.shape) < 2:
        xCurve2 = xCurve2.reshape(len(xCurve2),1)
        yCurve2 = yCurve2.reshape(len(yCurve2),1)

    # Concatenate x and y parts of each curve into a single array and take their derivative
    curve1 = np.concatenate((xCurve1, yCurve1), axis = 1)
    curve2 = np.concatenate((xCurve2, yCurve2), axis = 1)
    dydx1 = np.diff(curve1, axis = 0)
    dydx2 = np.diff(curve2, axis = 0)

    # Draw bounding box for intersection
    foundIndex = np.argwhere((movingMin(xCurve1) <= movingMax(xCurve2).T) &
                             (movingMax(xCurve1) >= movingMin(xCurve2).T) & 
                             (movingMin(yCurve1) <= movingMax(yCurve2).T) &
                             (movingMax(yCurve1) >= movingMin(yCurve2).T))
    
    # Special case for when each array is 2 elements long
    if foundIndex.shape == (1, 1):
        foundIndex_int = np.zeros((1,2), dtype = int)
        foundIndex_int[0,0] = foundIndex_int[0,1] = foundIndex[0][0]
        foundIndex = foundIndex_int
    # Special case for when there is no intersection (return an empty element for x and y)
    elif not foundIndex.any():
        xIntersect, yIntersect = [], []
        return xIntersect, yIntersect

    # Count number of intersections and build A, B, and z (output) arrays
    numIntersections = foundIndex.shape[0]
    outputArray = np.zeros((4,numIntersections))
    A = np.zeros((numIntersections,4,4))
    B = np.zeros((4,numIntersections))

    # Build A and B arrays
    A[:, [0, 1], 2] = -1
    A[:, [2, 3], 3] = -1
    A[:, [0, 2], 0] = dydx1[foundIndex[:,0],:]
    A[:, [1, 3], 1] = dydx2[foundIndex[:,1],:]

    B = -np.array([xCurve1[foundIndex[:,0]], xCurve2[foundIndex[:,1]], yCurve1[foundIndex[:,0]], yCurve2[foundIndex[:,1]]]).reshape((4,numIntersections))

    # Perform matrix solve operation to solve for z (outputArray)
    for i in range(numIntersections):
        outputArray[:,i] = np.linalg.solve(A[i,:,:], B[:,i])

    # Find where first two elements of outputArray are between 0 and 1
    inRange = np.argwhere((outputArray[0,:] >= 0) & 
                          (outputArray[0,:] <= 1) &
                          (outputArray[1,:] >= 0) & 
                          (outputArray[1,:] <= 1))

    # Return x and y coordinates of intersection point by sampling out of the 3rd and 4th elements of outputArray
    xIntersect = outputArray[2,inRange][:]
    yIntersect = outputArray[3,inRange][:]

    return xIntersect, yIntersect

def discreteIntersection(xCurve1: ArrayLike, yCurve1: ArrayLike, xCurve2: ArrayLike, yCurve2: ArrayLike, resolution: int = 1000) -> tuple:
    
    '''
    
    Replacement function for testing for curve intersections by checking each curve in discrete steps.

    This function only works in 2D.
    
    '''

    from scipy.interpolate import interp1d
    
    # Create interpolation functions for both curves
    curve1Interpolator = interp1d(xCurve1, yCurve1, kind = 'linear', fill_value = 'extrapolate')
    curve2Interpolator = interp1d(xCurve2, yCurve2, kind = 'linear', fill_value = 'extrapolate')
    
    # Find the overlapping x-range
    xRangeMin = max(min(xCurve1), min(xCurve2))
    xRangeMax = min(max(xCurve1), max(xCurve2))
    
    xRange = np.linspace(xRangeMin, xRangeMax, resolution)

    y1Range = curve1Interpolator(xRange)
    y2Range = curve2Interpolator(xRange)
    
    # Find where the curves cross (sign changes in their difference)
    differences = y1Range - y2Range
    signChanges = np.where(np.diff(np.signbit(differences)))[0]

    if not any(signChanges):
        print('No intersections detected')
        return [], []
    
    # Initialize lists to store caught intersections
    xIntersection, yIntersection = [], []

    for signChange in signChanges:

        # Use linear interpolation between points where sign changes
        xLeft, xRight   = xRange[signChange],  xRange[signChange + 1]
        y1Left, y1Right = y1Range[signChange], y1Range[signChange + 1]
        y2Left, y2Right = y2Range[signChange], y2Range[signChange + 1]
        
        # Find intersection via linear interpolation
        xIntersectionValue = xLeft + (xRight - xLeft) * \
                             (y2Left - y1Left) / ((y1Right - y1Left) - (y2Right - y2Left))
        yIntersectionValue = curve1Interpolator(xIntersectionValue)

        xIntersection.append(xIntersectionValue)
        yIntersection.append(yIntersectionValue)
            
    return xIntersection, yIntersection

def fillet(xCurve1: np.ndarray | list, yCurve1: np.ndarray | list, xCurve2: np.ndarray | list, yCurve2: np.ndarray | list, radiusOfCurvature: float, numPoints: int = 50) -> list[float]:

    '''
    
    This function is intended to be used for filleting two linear segments that are
    joined at a single point (or intersect at a single point that can be used as the join point).
    The two segments can be any length and any separation angle, and may be comprised of as few as 2 points each.

    This function works by first creating parallel offset curves of each of the passed in line segments. These offset
    curves are used to determine the unique solution where a fillet is applicable, which exists in the only intersection
    between the offset curves so long as the offset distance is the radius of curvature specified. If there are no intersections,
    then the fillet radius of curvature is too large to create a fillet between the given line segments.

    The fillet start and end angles are determined by the slope of each line segment at its respective endpoint,
    and a super ugly conditional statement built with trial and error catches all possible orientations of the fillet
    such that the function will work regardless of the orientation of the passed-in lines.

    Future update: Would love to re-orient the lines inside the function so that the fillet always occurs under the same
    spatial coordinates and then transform back to the original reference frame. That will get rid of the ugly
    conditional statement.
    
    '''

    # Find x and y differences for each curve
    dx1 = np.diff(xCurve1)
    dy1 = np.diff(yCurve1)

    dx2 = np.diff(xCurve2)
    dy2 = np.diff(yCurve2)

    # Create parallel offset curves
    xCurve1Offset1, yCurve1Offset1 = parallelOffset(xCurve1, yCurve1, radiusOfCurvature)
    xCurve1Offset2, yCurve1Offset2 = parallelOffset(xCurve1, yCurve1, -radiusOfCurvature)
    xCurve2Offset1, yCurve2Offset1 = parallelOffset(xCurve2, yCurve2, radiusOfCurvature)
    xCurve2Offset2, yCurve2Offset2 = parallelOffset(xCurve2, yCurve2, -radiusOfCurvature)

    # Find intersections between offset curves
    x1CircleIntersect, y1CircleIntersect = intersection(xCurve1Offset1, yCurve1Offset1, xCurve2Offset1, yCurve2Offset1)
    x2CircleIntersect, y2CircleIntersect = intersection(xCurve1Offset1, yCurve1Offset1, xCurve2Offset2, yCurve2Offset2)
    x3CircleIntersect, y3CircleIntersect = intersection(xCurve1Offset2, yCurve1Offset2, xCurve2Offset1, yCurve2Offset1)
    x4CircleIntersect, y3CircleIntersect = intersection(xCurve1Offset2, yCurve1Offset2, xCurve2Offset2, yCurve2Offset2)

    # Store intersection (x, y) pairs
    intersectionPoints    = [0 for x in range(4)]
    intersectionPoints[0] = [x1CircleIntersect, y1CircleIntersect]
    intersectionPoints[1] = [x2CircleIntersect, y2CircleIntersect]
    intersectionPoints[2] = [x3CircleIntersect, y3CircleIntersect]
    intersectionPoints[3] = [x4CircleIntersect, y3CircleIntersect]

    # Check for which of these are empty
    intersectionFlag = [1 for i in range(4)]
    for i in range(4):
        # If the given index is empty, change the 1 in the array to a 0
        if isinstance(intersectionPoints[i][0], list) and len(intersectionPoints[i][0]) == 0:
            intersectionFlag[i] = 0
        elif isinstance(intersectionPoints[i][0], np.ndarray) and intersectionPoints[i][0].size == 0:
            intersectionFlag[i] = 0
    # Find the index of the non-zero element
    intersectionIndex = [i for i, value in enumerate(intersectionFlag) if value != 0]

    # Calculate start and end angles of the fillet
    thetaFillet1 = np.arctan2(dy1[-1], dx1[-1])
    thetaFillet2 = np.arctan2(dy2[-1], dx2[-1])

    # Ugly conditional statement that catches all possible orientations of the fillet
    if ((thetaFillet1 - thetaFillet2) >= np.pi) & (thetaFillet2 < 0):
        thetaFillet2 = abs(thetaFillet2)
        thetaFillet = np.linspace(thetaFillet1, thetaFillet2, numPoints)
    elif (abs(thetaFillet1 - thetaFillet2) >= np.pi) & (thetaFillet1 < 0):
        thetaFillet1 = abs(thetaFillet1)
        thetaFillet = np.linspace(thetaFillet1, thetaFillet2, numPoints) + np.pi
    elif ((thetaFillet1 < 0) & (thetaFillet2 >= 0)) | ((thetaFillet1 <= 0) & (thetaFillet2 > 0)):
        thetaFillet = np.linspace(thetaFillet1, thetaFillet2, numPoints) - np.pi/2
    else:
        thetaFillet = np.linspace(thetaFillet1, thetaFillet2, numPoints) + np.pi/2

    # Draw a circle centered at the intersection location comprised of only the angles required to draw the fillet
    xFillet = intersectionPoints[intersectionIndex[0]][0][0] + radiusOfCurvature * np.cos(thetaFillet)
    yFillet = intersectionPoints[intersectionIndex[0]][1][0] + radiusOfCurvature * np.sin(thetaFillet)

    # Plots for testing
    # plt.style.use('dark_background')
    # fig, ax = plt.subplots(1, 1)
    # plt.plot(xCurve1, yCurve1, 'b')
    # plt.plot(xCurve2, yCurve2, 'r')
    # plt.plot(xCurve1Offset1,yCurve1Offset1,'--w')
    # plt.plot(xCurve1Offset2,yCurve1Offset2,'--w')
    # plt.plot(xCurve2Offset1,yCurve2Offset1,'--w')
    # plt.plot(xCurve2Offset2,yCurve2Offset2,'--w')
    # plt.plot(x1CircleIntersect,y1CircleIntersect,'*m')
    # plt.plot(x2CircleIntersect,y2CircleIntersect,'*m')
    # plt.plot(x3CircleIntersect,y3CircleIntersect,'*m')
    # plt.plot(x4CircleIntersect,y3CircleIntersect,'*m')
    # plt.plot(xFillet,yFillet,'c')
    # ax.set_aspect(aspect = 'equal')
    # plt.show(block = False)
    
    return xFillet, yFillet

def nonLinspace(start: float, end: float, numPoints: int = 100, method: str = 'exp') -> list[float]:

    '''
    
    Create a vector of nonlinearly spaced points from a start, end, and method.

    Available methods:
    - Exponential ['exp']
    - Cosine      ['cos']
    - Logarithmic ['log']
    
    '''

    match method:
        case 'exp':
            expFactor = 20
            nonLinearVector = (end - start) / expFactor * (10**np.linspace(0, np.log10(expFactor), numPoints)) + start
        case 'cos':
            nonLinearVector = (end - start) * (0.5 * (1 - np.cos(np.linspace(0, np.pi, numPoints)))) + start
        case 'log':
            logFactor = 1.5
            nonLinearVector = (end - start) / logFactor * np.log10(np.linspace(0, 10**logFactor - 1, numPoints) + 1) + start

    return nonLinearVector

def arcSpline(xPoints: ArrayLike, yPoints: ArrayLike, zPoints: ArrayLike | None = None, newNumPoints: int = 100) -> tuple:

    '''
    
    This function takes in a collection of 3D points, broken into X, Y, and Z arrays, that are unevenly distributed
    with respect to their arclength. The final input, newNumPoints, specifies the total number of points in the
    final spline that will be evenly distributed with respect to the spline arclength.

    This function has been stolen to be used as an arclength-based spline interpolation tool, the death of the artist is real.
    So now it works with 2D points as well.
    
    '''

    from copy import copy
    import scipy.interpolate as spi
    import scipy.integrate as sps

    if zPoints is None:
        zPoints = np.zeros(len(xPoints))
        is2D = True
        is3D = False
    else:
        is2D = False
        is3D = True

    # Helper functions to handle spline segment integration and event handling for line integration
    def segmentIntegrator(t, y, polyCoefs):
        output = np.zeros(np.size(t))
        for k in range(3):
            output += np.polyval(polyCoefs[k,:], t)**2
        return np.sqrt(output)
    
    def integrationEvents(t, y):
        value = y[0]
        return value
    # scipy solve_ivp requires event functions to be monkey patched with terminal and direction handles
    integrationEvents.terminal  = True
    integrationEvents.direction = 1
    
    # Initialize arrays to hold the newly generated points, as well as reorienting the passed-in points
    newNumPointsArray = np.linspace(0, 1, newNumPoints)
    newPoints = np.zeros((newNumPoints,3))
    oldPoints = np.array([xPoints, yPoints, zPoints]).T

    # Compute linear (chordal) arclength of each curve segment, as well as cumulative arclength
    linearArcLength = np.sqrt(np.sum(np.diff(oldPoints, axis = 0)**2, axis = 1))
    linearArcLengthNormalized = linearArcLength / np.sum(linearArcLength)
    cumulativeLinearArclength = np.cumsum(linearArcLengthNormalized)
    cumulativeLinearArclength = np.insert(cumulativeLinearArclength, 0, 0)

    # Initialize empty arrays to store piecewise cubic splines for each dimension of the old points, as
    # well as the derivative for each spline
    spline, splineDerivative = [[[], [], []] for _ in range(2)]
    # Make a (4, 3) array to be used to take the derivative of each spline (works because each
    # spline segment is by definition a cubic polynomial)
    derivativeArray = np.array([[3, 0, 0], [0, 2, 0], [0, 0, 1], [0, 0, 0]])
    for i in range(3):
        spline[i] = spi.CubicSpline(cumulativeLinearArclength, oldPoints[:,i])
        # Make a copy of the spline object to take the derivative so we don't overwrite the original spline
        # object properties
        splineDerivativeIntermediate = copy(spline[i])
        # Calculate the coefficients of the derivative by differentiating the spline coefficients
        splineDerivativeIntermediate.c = (splineDerivativeIntermediate.c.T @ derivativeArray).T
        splineDerivative[i] = splineDerivativeIntermediate
    
    # Create dummy array to store the coefficients of each spline derivative segment (to be used while integrating)
    polynomialCoefsDerivatives = np.zeros((3, 3))
    # Initialize array to hold integrated spline segment length
    segmentLength = np.zeros(len(xPoints)-1)
    # Set integration option relative tolerance to 1e-9
    integrationOptions = {'rtol': 1e-9}

    # First integration step: Determine the segment lengths of each cubic spline for the original points
    for i in range(len(splineDerivative[i].c[0,:])):

        # Store the coefficients of the polynomials describing the spline derivative for this segment
        for j in range(3):
            polynomialCoefsDerivatives[j,:] = splineDerivative[j].c[:,i]

        # Perform integration along the polynomial over the interval of [0, length of linear normalized spline segments up to this point]
        solution = sps.solve_ivp(lambda t, y: segmentIntegrator(t, y, polynomialCoefsDerivatives), \
                                 [0, linearArcLengthNormalized[i]], [0], **integrationOptions)
        # Store the output solution for cubic spline segment length
        segmentLength[i] = solution.y[0][-1]

    # Calculate total spline length and cumulative spline length for the old spline
    totalSplineLength = np.sum(segmentLength)
    cumulativeSplineLength = np.cumsum(segmentLength)
    cumulativeSplineLength = np.insert(cumulativeSplineLength, 0, 0)

    # Break spline length up over a uniformly spaced array of length newNumPoints
    # and compare the regions where each old point falls relative to the new spacing
    arclengthAlongSpline = newNumPointsArray * totalSplineLength
    bins = np.digitize(arclengthAlongSpline, cumulativeSplineLength) - 1
    bins[-1] = bins[-2]
    newInterpolationPoints = newNumPointsArray

    # Second integration step: Integrate over the newly spaced points and catch "zero-crossing" events,
    # or function events where the sign changes from positive to negative. These are important to track as
    # we re-space the points so that we can specify where the new spline points should land along the integration
    # path. We will be integrating in 't' until the integral crosses the specified value of 'splineSegment', and
    # because we normalized the total length each segment length is also normalized. Importantly, we start
    # the integration at -splineSegment so the event handler for zero-crossings can catch when the function output
    # 'y' reaches 0.
    for i in range(newNumPoints):

        # Define the length of the current spline segment
        splineSegment = arclengthAlongSpline[i] - cumulativeSplineLength[bins[i]]

        # Store the coefficients of the polynomials describing the spline derivative for this segment
        for j in range(3):
            polynomialCoefsDerivatives[j,:] = splineDerivative[j].c[:,bins[i]]

        # Perform aforementioned integration
        try:
            solution = sps.solve_ivp(lambda t, y: segmentIntegrator(t, y, polynomialCoefsDerivatives), \
                                    [0, linearArcLengthNormalized[bins[i]]], [-splineSegment], events = integrationEvents, **integrationOptions)
        except:
            class Solution():
                def __init__(self):
                    self.t_events = [[0]]
            solution = Solution()

        # Scale the new spline sample points by the result of the integration terminated at the zero crossing event
        if any(solution.t_events[0]):
            newInterpolationPoints[i] = solution.t_events[0] + cumulativeLinearArclength[bins[i]]

    # Perform final sampling of the spline at the new interpolation points
    for i in range(3):
        newPoints[:,i] = spline[i](newInterpolationPoints)

    if is3D:
        return newPoints[:,0], newPoints[:,1], newPoints[:,2]
    elif is2D:
        return newPoints[:,0], newPoints[:,1]

def filletCurves (radius: float, x1Points: np.ndarray, y1Points: np.ndarray, x2Points: np.ndarray, y2Points: np.ndarray, n: int) -> tuple:
    
    # Local imports
    from scipy.interpolate import CubicSpline
    from scipy.optimize import root
    
    # Find intersect location using splines
    splineCurve1 = CubicSpline(x1Points, y1Points)
    splineCurve2 = CubicSpline(x2Points, y2Points)

    def intersectFunction(x):
        return splineCurve1(x) - splineCurve2(x)

    xIntersection = secantSolve(intersectFunction, 0.5)
    yIntersection = splineCurve1(xIntersection)

    # Select data sets such that x1 and x2 are in order and the intersect. Location is at the origin
    if x1Points[1] < xIntersection and x2Points[-1] > xIntersection:
        x1Points, x2Points, y1Points,  y2Points = x1Points - xIntersection, x2Points - xIntersection, \
                                                  y1Points - yIntersection, y2Points - yIntersection
        
    elif x2Points[1] < xIntersection and x1Points[-1] > xIntersection:
        xPointA, x1Points =                       x1Points - xIntersection, x2Points - xIntersection
        x2Points =                                xPointA
        yPointA, y1Points =                       y1Points - yIntersection, y2Points - yIntersection
        y2Points =                                yPointA
    
    # Find orientation of bisector and orient problem with the vertical bisector in order to simplify problem to one half of circle formula

    # Slope between endpoints
    slopeEndpoint1, slopeEndpoint2 =   (y1Points[-1] - y1Points[1]) / (x1Points[-1] - x1Points[1]), \
                                       (y2Points[-1] - y2Points[1]) / (x2Points[-1] - x2Points[1])
    # Slope at intersect
    slopeIntersect1, slopeIntersect2 = (y1Points[-1] - y1Points[-2]) / (x1Points[-1] - x1Points[-2]), \
                                       (y2Points[1] - y2Points[0]) / (x2Points[1] - x2Points[0])
    
    # Characteristic slopes (average of slopes)
    characteristicSlope1, characteristicSlope2 = (slopeIntersect1 + slopeEndpoint1) / 2,  \
                                                 (slopeIntersect2 + slopeEndpoint2) / 2
    
    # Find bisector angle from the characteristic angles of both curves 
    characteristicAngle1, characteristicAngle2 = np.arctan2(characteristicSlope1 * x1Points[-1], x1Points[-1]), np.arctan2(characteristicSlope2 * x2Points[-1], x2Points[-1])
    characteristicTotalAngle                   = (characteristicAngle1 + characteristicAngle2) / 2
    
    # Cosine transformation matrix
    transformationMatrix = [[np.cos(np.pi/2 - characteristicTotalAngle), -np.sin(np.pi/2 - characteristicTotalAngle)], \
                            [np.sin(np.pi / 2 - characteristicTotalAngle), np.cos(np.pi / 2 - characteristicTotalAngle)]]
    
    #Orient by cosine transformation matrix 
    for i in range(len(x1Points)):
        x1NewPoints = np.array(transformationMatrix) @ np.array([x1Points[i], y1Points[i]]).T
        x1Points[i] = x1NewPoints[0]
        y1Points[i] = x1NewPoints[1]
    
    for i in range (len(x2Points)):
        x2NewPoints = np.array(transformationMatrix) @ np.array([x2Points[i], y2Points[i]]).T
        x2Points[i] = x2NewPoints[0]
        y2Points[i] = x2NewPoints[1]

    # Trim curves to only segments near fillet
    fitFactor = 2 # number of radii considered in curve fit 
    x1Fit = x1Points[x1Points > -fitFactor * radius]
    y1Fit = y1Points[x1Points > -fitFactor * radius]
    x2Fit = x2Points[x2Points < fitFactor * radius]
    y2Fit = y2Points[x2Points < fitFactor * radius]

    # Generate 4th Order polynomial fit for either dataset
    polynomialFit1 = np.polyfit(x1Fit, y1Fit, 3)
    polynomialFit2 = np.polyfit(x2Fit, y2Fit, 3)

    # Build system of equations to solve
    # f1 - set curve 1 equal to fillet circle at intersect
    # f2 - set curve 2 equal to fillet circle at intersect
    # f3 - set curve 1 slope equal to slope of fillet circle at intersect
    # f4 - set curve 2 slope equal to slope of fillet circle at intersect

    def equations(x): 
        return [(polynomialFit1[0] * x[0]**3 + polynomialFit1[1]   * x[0]**2 + polynomialFit1[2] * x[0] + polynomialFit1[3] - (-np.sqrt(radius**2 - (x[0] - x[2])**2) + x[3])), 
                 polynomialFit2[0] * x[1]**3 + polynomialFit2[1]   * x[1]**2 + polynomialFit2[2] * x[1] + polynomialFit2[3] - (-np.sqrt(radius**2 - (x[1] - x[2])**2) + x[3]),
               3*polynomialFit1[0] * x[0]**1 + 2*polynomialFit1[1] * x[0]    + polynomialFit1[2] - (x[0] - x[2]) / np.sqrt(radius**2 - (x[0] - x[2])**2),
               3*polynomialFit2[0] * x[1]**1 + 2*polynomialFit2[1] * x[1]    + polynomialFit2[2] - (x[1] - x[2]) / np.sqrt(radius**2 - (x[1] - x[2])**2)]

    # Initial guess
    initialGuess = [np.mean(x1Fit), np.mean(x2Fit), 0, radius]

    # Solve system of equations
    systemOfEqSolution = root(equations, initialGuess)

    # Process outputs 
    xOutput1, xOutput2, x0, y0 = np.real(systemOfEqSolution.x[0]), np.real(systemOfEqSolution.x[1]), np.real(systemOfEqSolution.x[2]), \
                                 np.real(systemOfEqSolution.x[3])
    
    # Find angle from fillet origin
    angleFillet1 = np.arctan2((np.polyval(polynomialFit1, xOutput1) - y0), (xOutput1 - x0))
    angleFillet2 = np.arctan2((np.polyval(polynomialFit2, xOutput2) - y0), (xOutput2 - x0))

    # Generate x and y points by linear angular spacing
    angleFillet = np.linspace(angleFillet1, angleFillet2, n)
    xFillet = radius * np.cos(angleFillet) + x0
    yFillet = radius * np.sin(angleFillet) + y0

    # Concatenate Results 
    xOutput = np.concatenate([x1Points[x1Points < xOutput1], xFillet, x2Points[x2Points > xOutput2]])
    yOutput = np.concatenate([y1Points[x1Points < xOutput1], yFillet, y2Points[x2Points > xOutput2]])

    # Post-process Results
    # Cosine Transformation Matrix to reorient results
    cosineTransformationMatrix = [[np.cos(characteristicTotalAngle - np.pi/2), -np.sin(characteristicTotalAngle - np.pi/2)],\
                                  [np.sin(characteristicTotalAngle - np.pi/2), np.cos(characteristicTotalAngle - np.pi/2)]]
    
    # Reorient results
    for i in range(len(xOutput)):
       systemOfEqSolution = np.array(cosineTransformationMatrix) @ np.array([xOutput[i], yOutput[i]]).T
       xOutput[i] = systemOfEqSolution[0] # no se si es 1 o 0 me vuelvo lOCA - c
       yOutput[i] = systemOfEqSolution[1] 

    # Translate results to intial coordinates
    xOutput = xOutput + xIntersection
    yOutput = yOutput + yIntersection

    return xOutput, yOutput

def lineIntersection(point1: ArrayLike, angle1: float, point2: ArrayLike, angle2: float) -> tuple:

    '''
    
    This function takes in, for two different lines, a point on each line and the angle that each 
    line makes with the X axis and calculates the intersection point between the two lines.
    
    '''

    slope1, slope2 = np.tan(angle1), np.tan(angle2)
    yIntercept1, yIntercept2 = point1[1] - slope1 * point1[0], point2[1] - slope2 * point2[0]

    xIntersection = (yIntercept2 - yIntercept1) / (slope1 - slope2)
    yIntersection = (slope1 * xIntersection + yIntercept1 + slope2 * xIntersection + yIntercept2) / 2

    return xIntersection, yIntersection

def revolveContour(xContour: list | np.ndarray, rContour: list | np.ndarray, numSlices: int = 50) -> np.ndarray:

    '''
    
    Given a 2D contour, revolve it about the central axis to create a surface.
    
    '''

    if isinstance(xContour, list):
        xContour  = np.array(xContour)
        rContour  = np.array(rContour)

    zContour       = np.zeros(len(xContour))
    beforeRevolve  = np.zeros((numSlices, 3, len(xContour)))
    afterRevolve   = np.zeros((numSlices, 3, len(xContour)))
    rotationMatrix = np.zeros((numSlices, 3, 3))
    xContourRevolved, yContourRevolved, zContourRevolved = [np.zeros((numSlices, len(xContour))) for _ in range(3)]
    rollAngle      = np.linspace(0, 2 * np.pi, numSlices)

    beforeRevolve = np.array([zContour, rContour, xContour])

    for i in range(numSlices):

        # Create an array to hold the Euler angles for the rotation calculation
        rotationValue = [0, 0, rollAngle[i]]

        # Create the rotation cosine matrices in each cartesian direction
        Rx = np.array([[1, 0, 0],
                [0, np.cos(rotationValue[0]), -np.sin(rotationValue[0])],
                [0, np.sin(rotationValue[0]), np.cos(rotationValue[0])]])
        
        Ry = np.array([[np.cos(rotationValue[1]), 0, np.sin(rotationValue[1])],
                [0, 1, 0],
                [-np.sin(rotationValue[1]), 0, np.cos(rotationValue[1])]])
        
        Rz = np.array([[np.cos(rotationValue[2]), -np.sin(rotationValue[2]), 0],
                [np.sin(rotationValue[2]), np.cos(rotationValue[2]), 0],
                [0, 0, 1]])
        
        # Matrix multiply the rotation matrices to get a single rotation matrix that describes this rotation
        rotationMatrix[i,:,:] = Rz @ Ry @ Rx

        # Apply that rotation matrix to the pre-rotated volute matrix
        afterRevolve[i,:,:] = rotationMatrix[i,:,:] @ beforeRevolve

        # Extract the X, Y, and Z data from the 3D rotated volute matrix
        xContourRevolved[i,:] = afterRevolve[i,0,:]
        yContourRevolved[i,:] = afterRevolve[i,1,:]
        zContourRevolved[i,:] = afterRevolve[i,2,:]

    return xContourRevolved, yContourRevolved, zContourRevolved

def jtan2(theta: np.ndarray | list, exact: bool = False) -> list[float]:

    '''

    Ported from jtan2.m (Sean Bowman, 10/11/2022) 

    This function fixes the discontinuities in atan2.m caused by the traditional range of arctangent.
        in :    janky angles        [1xn] radians
        out:    corrected angles    [1xn] radians
    Angles are corrected by counting the discontiuties with respect to sign and applying a correction
    factor of pi*(number of discontinuities) between discontinuity n and n+1 (or n and end in the
    case of the final discontinuity). If no discontinuities are found, theta is returned unchanged

    Author: Isabella Duprey-Churn
    Date:   7/2/2024

    '''

    n = len(theta)

    # better method for finding discontinuities? {
    c = 1                 # correction accounts for the discrete nature of theta i.e. the magnitude of discntinuity may be < 2*pi
    d = np.pi-c             # discontinuity criteria

    disc = []               # store indicies of discontinuity
    gap = []
    for i in range(n-1):
        if abs(theta[i+1]-theta[i]) >= d:
            gap.append(theta[i+1]-theta[i])
            disc.append(i)
    m = len(disc)
    # }

    if not disc:
        # if no discontinuities found, return theta unchanged:
        thetaCorrected = theta.copy()
    else:
        # preallocate:
        thetaCorrected = theta.copy()
        signDiff = theta[0:m].copy()
        # initalize discontinuity counter:
        count = 0              
        # store sign of discontinuties:
        for i in range(m):
            signDiff[i] = np.sign(theta[disc[i]+1] - theta[disc[i]])
        for p in range(m):          # for all discontinuities
            count += signDiff[p]    # update counter for appropriate correction factor
            if p < m-1:             # not final discountinuity
                for q in range(disc[p]+1,disc[p+1]+1):
                    if not exact:
                        thetaCorrected[q] = theta[q] - (2*np.pi*count)    
                    else:
                        thetaCorrected[q] = theta[q] - (gap[p]*count)
            else:                   # final discontinuity
                for q in range(disc[p]+1,n):
                    if not exact:
                        thetaCorrected[q] = theta[q] - (2*np.pi*count)
                    else:
                        thetaCorrected[q] = theta[q] - (gap[p]*count)

    return thetaCorrected

def DCM(eulerAngles: ArrayLike, valueMatrix: ArrayLike, transpose: bool = False, rotationOrder: str = 'zyx') -> np.ndarray:

    '''
    
    Apply direction cosine matrix transformations to 'valueMatrix' given the angles in 'eulerAngles' and the order specified by 'rotationOrder'.
    
    '''

    # Create the rotation cosine matrices in each cartesian direction
    Rx = np.array([                                                                 \
                [1,             0,                        0           ],            \
                [0,             np.cos(eulerAngles[0]),  -np.sin(eulerAngles[0])],  \
                [0,             np.sin(eulerAngles[0]),   np.cos(eulerAngles[0])]]) # X-Axis rotation

    Ry = np.array([                                                                 \
                [np.cos(eulerAngles[1]),  0,              np.sin(eulerAngles[1])],  \
                [0,                       1,              0                     ],  \
                [-np.sin(eulerAngles[1]), 0,              np.cos(eulerAngles[1])]]) # Y-axis rotation

    Rz = np.array([                                                                 \
                [np.cos(eulerAngles[2]), -np.sin(eulerAngles[2]),   0           ],  \
                [np.sin(eulerAngles[2]),  np.cos(eulerAngles[2]),   0           ],  \
                [0,                       0,                        1           ]]) # Z-axis rotation
    
    # Matrix multiply the rotation matrices to get a single rotation matrix that describes this rotation
    if not transpose:
        match rotationOrder:
            case 'zyx':
                # Default operation order
                rotationMatrix = Rz @ Ry @ Rx
            case 'yzx':
                rotationMatrix = Ry @ Rz @ Rx
            case 'xyz':
                rotationMatrix = Rx @ Ry @ Rz
    elif transpose:
        match rotationOrder:
            case 'zyx':
                rotationMatrix = Rz @ Ry @ Rx . T
            case 'yzx':
                rotationMatrix = Ry @ Rz @ Rx . T
            case 'xyz':
                rotationMatrix = Rx @ Ry @ Rz . T

    # Apply that rotation matrix to the pre-rotated volute matrix
    unCenteredRotatedValueMatrix = rotationMatrix @ valueMatrix

    # Extract the X, Y, and Z data from the 3D rotated volute matrix
    rotatedX = unCenteredRotatedValueMatrix[0]
    rotatedY = unCenteredRotatedValueMatrix[1]
    rotatedZ = unCenteredRotatedValueMatrix[2]

    return rotatedX, rotatedY, rotatedZ

def rescaleData(rawData: np.ndarray | list, newMax: float = None, newMin: float = None) -> np.ndarray | list:

    '''
    
    Rescale data between a new specified max and min while retaining data shape.
    
    '''

    # Handle cases where the user wants only to rescale in one direction
    if not newMax:

        newMax = np.max(rawData)

    if not newMin:

        newMin = np.min(rawData)

    # First, normalize to [0, 1]
    normalizedData = (rawData - np.min(rawData)) / (np.max(rawData) - np.min(rawData))
    
    # Then scale to [new_min, new_max]
    rescaledData = normalizedData * (newMax - newMin) + newMin
    
    return rescaledData

def bezierCurve(p1: float, p4: float, theta_1: float, theta_2: float, magnitude, res):
    
    '''

    Creates a bezier curve using start and end points, start and end angles, and magnitude to control the magnitude of the curve
    
    '''

    # Scale the magnitude to the size of the bezier to make it less dependent on the input points
    length = np.sqrt(((p4[1]-p1[1])**2) + ((p4[0]-p1[0])**2))
    magnitude[0] = magnitude[0]*length
    magnitude[1] = magnitude[1]*length

    # Create control points p2, p3 from given angles and magnitudes
    py2 = magnitude[0]*np.sin(np.radians(theta_1)) # (magnitude[0]-p1[0] - p1[0])*np.tan(np.radians(theta_1)) + p1[1]
    px2 = np.sqrt((magnitude[0]**2)-(py2**2))
    p2 = [px2+p1[0], py2+p1[1]] # magnitude, angle
    py3 = magnitude[1]*np.sin(np.radians(theta_2)) # (p4[0]-magnitude[1] - p4[0])*np.tan(np.radians(theta_2)) + p4[1]
    px3 = np.sqrt((magnitude[1]**2) - (py3**2))
    p3 = [p4[0]-px3, p4[1]-py3] # magnitude, angle

    # Bezier parametric equation
    def eqn(p1, p2, p3, p4, t):
        return (1 - (t**3))*p1 + (3*t*(1-t)**2)*p2 + 3*(t**2)*(1-t)*p3 + (t**3)*p4
    
    # parametric bezier
    t = np.linspace(0, 1, res)
    x = [eqn(0, p2[0]-p1[0], p3[0]-p1[0], p4[0]-p1[0], i)+p1[0] for i in t]
    y = [eqn(0, p2[1]-p1[1], p3[1]-p1[1], p4[1]-p1[1], i)+p1[1] for i in t]

    # Plot Bezier curve for debugging
    # plt.plot(x, y, c='k')
    # plt.plot(p2[0], p2[1], '*')
    # plt.plot(p3[0], p3[1], '*')
    # plt.plot(p1[0], p1[1], '*')
    # plt.plot(p4[0], p4[1], '*')
    # plt.show(block = False)
    
    return [x, y]

#--------------------------------------------------------------------------------------------------------------------------#
# -- Data Manipulation Functions -- #
#--------------------------------------------------------------------------------------------------------------------------#

def secantSolve(function: Callable[...,float], initialGuess: float, lowerBound: float = -np.inf, upperBound: float = np.inf, displayFlag: bool = True) -> float:

    '''
    
    This function approximates the zero of a nonlinear function given a starting point (and optional bounds) using the Secant Method.
    The secant method, while slightly slower to converge than the classic Newton-Raphson method, does not require
    computing the function derivative at each step and is therefore slightly computationally faster when
    calculations are performed in serial. Secant method is a subset of Newton's method where the function derivative is
    approximated as a finite difference. The equation that drives the secant method is given as:

    x_n = x_n-1 - f(x_n-1) * (x_n-1 - x_n-2) / (f(x_n-1) - f(x_n-2))

    The process of finding a zero involves the selection of a starting point and performing subsequent iterations of the
    above equation until either the value of the function falls below the tolerance or the convergence criteria is not met.
    In the latter case, the average of the x values over the last maxIterations number of iterations is returned. This
    assumes that the starting value chosen is at least close to a zero of the function, and this way the function does
    not get trapped in an infinite loop or have nothing to return and break subsequent downstream functionality.

    '''

    # Initialize values
    tolerance = 1e-6
    maxIterations = 30
    iterator = 0
    xStorage = np.zeros(maxIterations)
    xPrevious, xNext = initialGuess, (initialGuess + initialGuess * tolerance)
    functionPrevious = function(xPrevious)
    
    converged = False
    while not converged:

        # Start by checking function value at most recent x value
        functionNext = function(xNext)

        # Check convergence criteria
        if abs(functionNext) <= tolerance:
            # If function value is sufficiently close to zero
            solution = xNext
            converged = True
        else:
            # Otherwise run an iteration of secant method
            xUpdate = xNext - functionNext * (xNext - xPrevious) / (functionNext - functionPrevious)
            xNew = min(upperBound, max(lowerBound, xUpdate))
            xPrevious, xNext, functionPrevious = xNext, xNew, functionNext
        
        # Update storage array for convergence failure and increment iterator
        xStorage[(iterator % maxIterations)] = xPrevious
        iterator += 1

        # If convergence fails, average of x values tried so far and return
        if iterator >= maxIterations:
            if displayFlag is True:
                print(f'Uh oh, secantSolve failed to converge within {maxIterations} iterations,' + \
                      'taking the average of the X values tried and returning that instead.')
            solution = np.mean(xStorage)
            converged = True

        if np.isnan(functionNext):
            solution = np.mean(xStorage)
            converged = True
    
    return solution

def chunkInterpolate(xPoints: ArrayLike, yPoints: ArrayLike, xNewPoints: ArrayLike) -> np.ndarray:

    '''
    
    Interpolate yPoints to a not strictly increasing xPoints.

    Intended for use with similar old and new x arrays i.e. must have the same range
    and total number of inflection points
    
    '''
    
    if len(xPoints) != len(yPoints):
        raise Exception('x and y point arrays must be the same size.')
    
    pointsOfInflection = np.concatenate([[0],np.where(np.diff(np.sign(np.diff(xPoints))) != 0)[0] + 1])
    newPointsOfInflection = np.concatenate([[0],np.where(np.diff(np.sign(np.diff(xNewPoints))) != 0)[0] + 1])
    if 1 in newPointsOfInflection and 1 not in pointsOfInflection:
        newPointsOfInflection = np.delete(newPointsOfInflection,1)

    if len(pointsOfInflection) != len(newPointsOfInflection):
        raise Exception('Old and new x arrays must have the same number of inflection points.')
    
    yNewPoints = np.array([])

    ## 1...n-1 chunks
    for i in range(1,len(pointsOfInflection)):
        
        # chunk

        j = pointsOfInflection[i-1]
        k = pointsOfInflection[i]

        xChunk = xPoints[j:k]
        yChunk = yPoints[j:k]
        
        if sum(np.sign(np.diff(xChunk))) < 0:
            flipFlag = True
        else: 
            flipFlag = False

        if flipFlag:                        
            xChunk = np.flip(xChunk)
            yChunk = np.flip(yChunk)
        
        # interpolate

        m = newPointsOfInflection[i-1]
        n = newPointsOfInflection[i]
        
        if not flipFlag:
            yNewChunk = np.interp(xNewPoints[m:n],xChunk,yChunk)
            yNewPoints = np.append(yNewPoints,yNewChunk)
        elif flipFlag:
            yNewChunk = np.interp(np.flip(xNewPoints[m:n]),xChunk,yChunk)
            yNewPoints = np.append(yNewPoints,np.flip(yNewChunk))

    ## n chunk

    # chunk

    j = pointsOfInflection[-1]

    xChunk = xPoints[j:]
    yChunk = yPoints[j:]
    
    if sum(np.sign(np.diff(xChunk))) < 0:
        flipFlag = True
    else: 
        flipFlag = False

    if flipFlag:                        
        xChunk = np.flip(xChunk)
        yChunk = np.flip(yChunk)
    
    # interpolate

    m = newPointsOfInflection[-1]
    
    if not flipFlag:
        yNewChunk = np.interp(xNewPoints[m:],xChunk,yChunk)
        yNewPoints = np.append(yNewPoints,yNewChunk)
    elif flipFlag:
        yNewChunk = np.interp(np.flip(xNewPoints[m:]),xChunk,yChunk)
        yNewPoints = np.append(yNewPoints,np.flip(yNewChunk))

    return yNewPoints

def plotly3DGeometry(xData: np.ndarray | list, yData: np.ndarray | list, zData: np.ndarray | list, title: str = 'Geometry Plot', xLabel: str = 'X', yLabel: str = 'Y', zLabel: str = 'Z', alpha: float = 1, color: str = 'lightslategray') -> None:

    '''
    
    A wrapper for plotting 3D surfaces that makes the interface a little bit easier to use.
    
    '''

    # Plotly renders in the browser, so the import is deferred to the call that needs it.
    import plotly.graph_objects as go

    # Instantiate a figure container
    fig = go.Figure()

    # Update the figure container with the passed in data
    fig.add_trace(go.Surface(x = xData, y = yData, z = zData, 
                             colorscale = [[0, color], [1,color]],
                             opacity = alpha,
                             showscale = False))

    # Add figure formatting commands
    fig.update_layout(scene = dict(xaxis_title = xLabel,
                                   yaxis_title = yLabel,
                                   zaxis_title = zLabel),
                                   title = {'text': title,
                                            'x': 0.5,
                                            'xanchor': 'center',
                                            'y': 0.9,
                                            'yanchor': 'top'},
                                   scene_aspectmode = 'data',
                                   template = 'plotly_dark')

    # Render the plot
    fig.show()

def plotlySurface(xData: np.ndarray | list, yData: np.ndarray | list, zData: np.ndarray | list, colorMap: str = 'Plasma', alpha = 1, title: str = 'Surface Plot', xLabel: str = 'X', yLabel: str = 'Y', zLabel: str = 'Z') -> None:

    '''
    
    A wrapper for plotting 3D surfaces that makes the interface a little bit easier to use.
    
    '''

    # Plotly renders in the browser, so the import is deferred to the call that needs it.
    import plotly.graph_objects as go

    # Instantiate a figure container
    fig = go.Figure()

    # Update the figure container with the passed in data
    fig.add_trace(go.Surface(x = xData, y = yData, z = zData, 
                             colorscale = colorMap,
                             opacity = alpha))

    # Add figure formatting commands
    fig.update_layout(scene = dict(xaxis_title = xLabel,
                                   yaxis_title = yLabel,
                                   zaxis_title = zLabel),
                                   title = {'text': title,
                                            'x': 0.5,
                                            'xanchor': 'center',
                                            'y': 0.9,
                                            'yanchor': 'top'},
                                   scene_aspectmode = 'data',
                                   template = 'plotly_dark')

    # Render the plot
    fig.show()

def plotly3DLine(xData: np.ndarray | list, yData: np.ndarray | list, zData: np.ndarray | list, title: str = '3D Line Plot', xLabel: str = 'X', yLabel: str = 'Y', zLabel: str = 'Z', color: str | list[float] = [0,1,1], lineWidth: float = 1, lineStyle: str = None, markerStyle: str = None, markerSize: float = 4, label: str = '3D Line') -> None:

    '''
    
    A wrapper for plotting 3D lines that makes the interface a little bit easier to use.
    
    '''

    # Plotly renders in the browser, so the import is deferred to the call that needs it.
    import plotly.graph_objects as go

    # Instantiate a figure container and update the figure container with passed in data
    fig = go.Figure(data = [go.Scatter3d(x = xData, y = yData, z = zData,
                                         mode = 'lines+markers',
                                         marker = dict(
                                             symbol = markerStyle,
                                             size = markerSize,
                                             color = color
                                             ),
                                         line = dict(
                                             dash = lineStyle,
                                             width = lineWidth,
                                             color = color
                                             ),
                                         name = label)])

    # Add figure formatting commands
    fig.update_layout(scene = dict(xaxis_title = xLabel,
                                   yaxis_title = yLabel,
                                   zaxis_title = zLabel),
                                   title = {'text': title,
                                            'x': 0.5,
                                            'xanchor': 'center',
                                            'y': 0.9,
                                            'yanchor': 'top'},
                                   scene_aspectmode = 'data',
                                   template = 'plotly_dark')

    # Render the plot
    fig.show()

def plotly2DLine(xData: np.ndarray | list, yData: np.ndarray | list, title: str = '2D Line Plot', xLabel: str = 'X', yLabel: str = 'Y', color: str = 'cyan', lineWidth: float = 1, lineStyle: str = None, markerStyle: str = None, markerSize: float = 4, fontSize: int = 12, label: str = '2D Line') -> None:

    '''
    
    A wrapper for plotting in 2D that makes the interface a little easier.
    
    '''

    # Plotly renders in the browser, so the import is deferred to the call that needs it.
    import plotly.graph_objects as go

    # Instantiate a figure container and update the figure container with passed in data
    fig = go.Figure(data = [go.Scatter(x = xData, y = yData,
                                         mode = 'lines+markers',
                                         marker = dict(
                                             symbol = markerStyle,
                                             size = markerSize,
                                             color = color
                                             ),
                                         line = dict(
                                             dash = lineStyle,
                                             width = lineWidth,
                                             color = color
                                             ),
                                         name = label)])

    # Add figure formatting commands
    fig.update_layout(scene = dict(xaxis_title = xLabel,
                                   yaxis_title = yLabel),
                                   title = {'text': title,
                                            'x': 0.5,
                                            'xanchor': 'center',
                                            'y': 0.9,
                                            'yanchor': 'top'},
                                   scene_aspectmode = 'data',
                                   template = 'plotly_dark')

    # Render the plot
    fig.show()

def plotLine(xData: np.ndarray | list, yData: np.ndarray | list,
             title: str = '2D Line Plot', xLabel: str = 'X', yLabel: str = 'Y',
             color: str = 'cyan', lineWidth: float = 1, lineStyle: str = None,
             markerStyle: str = None, markerSize: float = 4, fontSize: int = 12, label: str = '2D Line') -> None:

    '''
    
    Wrapper for matplotlib plots bc I'm lazy.
    
    '''
    
    plt.rcParams.update({'font.size': fontSize})
    plt.style.use('dark_background')

    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.plot(xData, yData,
             label = label, color = color,
             lw = lineWidth, ls = lineStyle,
             marker = markerStyle, ms = markerSize)
    
    ax = plt.gca()
    ax.set_xlabel(xLabel)
    ax.set_ylabel(yLabel)
    ax.set_title(title)
    plt.show(block = False)

def plot3DLine(xData: np.ndarray | list, yData: np.ndarray | list, zData: np.ndarray | list,
             title: str = '3D Line Plot', xLabel: str = 'X', yLabel: str = 'Y', zLabel: str = 'Z',
             color: str = 'cyan', lineWidth: float = 1, lineStyle: str = None,
             markerStyle: str = None, markerSize: float = 4, fontSize: int = 12, label: str = '3D Line',
             iterator: int = 0) -> None:

    '''
    
    Wrapper for matplotlib 3D plots bc I'm lazy.
    
    '''
    
    plt.rcParams.update({'font.size': fontSize})
    plt.style.use('dark_background')

    # Handle for random color setting
    if color.lower() == 'random':
        color = np.random.rand(1,3)

    if iterator == 0:
        fig = plt.figure('3D Line Plot')
        ax = fig.add_subplot(111, projection = '3d')
        ax.plot(xData, yData, zData,
                label = label, color = color,
                lw = lineWidth, ls = lineStyle,
                marker = markerStyle, ms = markerSize)
    else:
        plt.gca().plot(xData, yData, zData,
                label = label, color = color,
                lw = lineWidth, ls = lineStyle,
                marker = markerStyle, ms = markerSize)
    
    plt.gca().set_xlabel(xLabel)
    plt.gca().set_ylabel(yLabel)
    plt.gca().set_zlabel(zLabel)
    plt.gca().set_title(title)
    plt.show(block = False)

def indexAnnotatedScatterPlot(x, y):

    '''

    for making scatter plots with index numbers next to points for debug purposes

    Author: Cam'ron Valliere

    '''

    plt.scatter(x, y)
    plt.gca().set_aspect('equal', adjustable='box')
    for i, (xi, yi) in enumerate(zip(x, y)):
        plt.text(xi, yi, str(i), fontsize=9, ha='right', va='bottom')

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
 
def readExcel(fileName: str, sheetName: str):
    
    '''
    
    Wrapper for reading data from an open Excel file using COM.

    Returns a Pandas DataFrame of the selected excel sheet as well as the excel instance for closing later.
 
    '''

    import pandas as pd
    import win32com.client
    from time import sleep
 
    try:
        # Open an instance of excel and open the specified file and sheet
        excelInstance = win32com.client.Dispatch("Excel.Application")
        workbook      = excelInstance.Workbooks.Open(fileName)
        sheet         = workbook.Worksheets(sheetName)
    except:
        # Hilariously scuffed fix here:
        # When running an export process, the last step is to close excel so the config can be copied,
        # but when re-running from the active instance this function throws an error because the requested sheet is closed
        # The above try statement then fails and throws an error, but this catch just waits for 2 seconds and then grabs the newly opened
        # file and it works fine which is amazing and sublimely janky
        sleep(2)
        excelInstance = win32com.client.Dispatch("Excel.Application")
        workbook      = excelInstance.Workbooks.Open(fileName)
        sheet         = workbook.Worksheets(sheetName)
    
    # Get the used range
    usedRange = sheet.UsedRange
    values    = usedRange.Value

    # Convert the COM objects list of lists to a list of lists
    data = [[cell for cell in row] for row in values]

    # Create DataFrame using the first row as headers
    dataFrame = pd.DataFrame(data[1:], columns = data[0])
    
    # Convert 'None' values to numpy 'NaN's
    dataFrame = dataFrame.replace({None: np.nan})
    
    return dataFrame, excelInstance

def stitchPDF(pdfFileList: list) -> io.BytesIO:

    '''
    
    Stitch together multiple PDF files into a single PDF file. Returns a BytesIO object containing the merged PDF.

    This process happens in-memory and does not write any files to disk.
    
    '''

    from pypdf import PdfReader, PdfWriter  # type: ignore[import]  # optional PDF dependency

    writer = PdfWriter()
    
    # Iterate through each uploaded PDF
    for pdfFile in pdfFileList:
        # Read the PDF from the uploaded file
        reader = PdfReader(pdfFile)
        
        # Add all pages from this PDF to the writer
        for page in reader.pages:
            writer.add_page(page)
    
    # Write to a BytesIO object instead of a file
    outputFile = io.BytesIO()
    writer.write(outputFile)
    outputFile.seek(0)  # Reset pointer to beginning


    return outputFile

def pickleObject(obj, filePath: str) -> None:
    
    '''

    This method is responsible for pickling a given object to a specified file path.

    Author: Sean Bowman
    Date:   12/17/2025

    '''

    with open(filePath, 'wb') as file:
        pickle.dump(obj, file)

#--------------------------------------------------------------------------------------------------------------------------#
# -- CEA to REFPROP Species Name Mapping -- #
#--------------------------------------------------------------------------------------------------------------------------#

def getCEAtoREFPROPMapping() -> dict[str, str]:

    '''

    Returns a dictionary mapping CEA species names to REFPROP fluid names.

    This function provides the canonical mapping between NASA CEA propellant
    naming conventions (chemical formulas) and NIST REFPROP fluid database
    names (common names in uppercase).

    Returns:
    --------
    dict[str, str] : Dictionary with CEA names as keys, REFPROP names as values

    Examples:
    ---------
    >>> mapping = getCEAtoREFPROPMapping()
    >>> mapping['CH4']
    'METHANE'
    >>> mapping['LH2']
    'HYDROGEN'

    '''

    # Core mapping dictionary - covers most common propellants
    mapping = {
        # Hydrogen variants (all map to HYDROGEN)
        'H2':               'HYDROGEN',
        'LH2':              'HYDROGEN',
        'GH2':              'HYDROGEN',
        'H2(L)':            'HYDROGEN',
        'H2(G)':            'HYDROGEN',
        'LH2_NASA':         'HYDROGEN',
        'GH2_160':          'HYDROGEN',
        'Liquid Hydrogen':  'HYDROGEN',

        # Oxygen variants (all map to OXYGEN)
        'O2':               'OXYGEN',
        'LO2':              'OXYGEN',
        'LOX':              'OXYGEN',
        'GOX':              'OXYGEN',
        'GO2':              'OXYGEN',
        'O2(L)':            'OXYGEN',
        'O2(G)':            'OXYGEN',
        'LO2_NASA':         'OXYGEN',
        'Liquid Oxygen':    'OXYGEN',

        # Methane variants
        'CH4':          'METHANE',
        'CH4(L)':       'METHANE',
        'GCH4':         'METHANE',
        'CH4(G)':       'METHANE',
        'LCH4_NASA':    'METHANE',
        'Methane':      'METHANE',

        # Propane variants
        'C3H8':     'PROPANE',
        'Propane':  'PROPANE',
        'C3H8(L)':  'PROPANE',

        # Ethane variants
        'C2H6':     'ETHANE',
        'C2H6(L)':  'ETHANE',
        'C2H6_167': 'ETHANE',
        'Ethane':   'ETHANE',

        # Ethanol variants
        'C2H5OH':       'ETHANOL',
        'Ethanol':      'ETHANOL',
        'ETHANOL':      'ETHANOL',
        'C2H5OH(L)':    'ETHANOL',

        # Methanol variants
        'CH3OH':        'METHANOL',
        'Methanol':     'METHANOL',
        'METHANOL':     'METHANOL',
        'CH3OH(L)':     'METHANOL',

        # Water
        'H2O':      'WATER',
        'H2O(L)':   'WATER',

        # Nitrous Oxide
        'N2O':          'N2O',
        'NitrousOxide': 'N2O',
        'N2O_nbp':      'N2O',

        # Ammonia
        'NH3':      'AMMONIA',
        'NH3(L)':   'AMMONIA',

        # Nitrogen
        'N2':       'NITROGEN',
        'N2(L)':    'NITROGEN',

        # Acetylene
        'C2H2':         'ACETYLENE',
        'Acetylene':    'ACETYLENE',

        # Carbon Dioxide
        'CO2':      'CO2',
        'CO2(L)':   'CO2',
    }

    return mapping

def convertCEAtoREFPROP(ceaName: str, raiseOnNotFound: bool = True) -> str:

    '''

    Convert a CEA species name to its REFPROP equivalent.

    This function handles the conversion between NASA CEA propellant naming
    conventions and NIST REFPROP fluid database names. If the species is
    already a REFPROP name, it is returned unchanged.

    Parameters:
    -----------
    ceaName : str
        CEA species name (e.g., 'CH4', 'LH2', 'LOX')
    raiseOnNotFound : bool, optional
        If True, raise InvalidInputError when no mapping exists.
        If False, return the original name unchanged (default).

    Returns:
    --------
    str : REFPROP fluid name (e.g., 'METHANE', 'HYDROGEN', 'OXYGEN')

    Raises:
    -------
    InvalidInputError : If raiseOnNotFound=True and no mapping exists

    Examples:
    ---------
    >>> convertCEAtoREFPROP('CH4')
    'METHANE'
    >>> convertCEAtoREFPROP('METHANE')  # Already REFPROP name
    'METHANE'
    >>> convertCEAtoREFPROP('RP1')
    'RP1'  # No mapping - returns original

    Notes:
    ------
    Species without REFPROP equivalents (RP1, RP_1, Kerosene, MMH, UDMH,
    N2H4, JetA, JP10, etc.) will return the original name unchanged unless
    raiseOnNotFound=True.

    '''

    # Get the mapping dictionary
    mapping = getCEAtoREFPROPMapping()

    # Check if conversion is needed
    if ceaName in mapping:
        return mapping[ceaName]

    # Check if it's already a REFPROP name (case-insensitive check)
    # Get list of available REFPROP fluids
    try:
        fv = fluidView()
        availableFluids = fv.getAvailableFluids()

        # Case-insensitive check
        for fluid in availableFluids:
            if ceaName.upper() == fluid.upper():
                return fluid
    except Exception:
        # If REFPROP check fails, continue with fallback logic
        pass

    # No mapping found
    if raiseOnNotFound:
        raise InvalidInputError(
            inputName='coolant',
            value=ceaName,
            expectedType='REFPROP-compatible species',
            message=f'CEA species \'{ceaName}\' has no REFPROP equivalent. '
                    f'Please select a different coolant or choose a REFPROP fluid directly.'
        )

    # Return original name unchanged
    return ceaName

def isREFPROPCompatible(speciesName: str) -> tuple[bool, str]:

    '''

    Check if a species name is compatible with REFPROP.

    This function checks if a given species name (CEA or REFPROP format)
    can be successfully used with REFPROP's refWrap function.

    Parameters:
    -----------
    speciesName : str
        Species name to check (CEA or REFPROP format)

    Returns:
    --------
    tuple[bool, str] : (is_compatible, refprop_name or error_message)
        - If compatible: (True, 'REFPROP_NAME')
        - If incompatible: (False, 'Error: reason')

    Examples:
    ---------
    >>> isREFPROPCompatible('CH4')
    (True, 'METHANE')
    >>> isREFPROPCompatible('RP1')
    (False, 'Error: No REFPROP equivalent for RP1')

    '''

    # Try to convert
    refpropName = convertCEAtoREFPROP(speciesName, raiseOnNotFound=False)

    # Check if it's in REFPROP library
    try:
        fv = fluidView()
        availableFluids = fv.getAvailableFluids()

        # Case-insensitive check
        for fluid in availableFluids:
            if refpropName.upper() == fluid.upper():
                return (True, fluid)

        # Not found in REFPROP
        return (False, f'Error: No REFPROP equivalent for {speciesName}')

    except Exception as e:
        return (False, f'Error: REFPROP check failed - {e}')

#--------------------------------------------------------------------------------------------------------------------------#
# -- Parallel Processing Utilities -- #
#--------------------------------------------------------------------------------------------------------------------------#

@contextlib.contextmanager
def tqdmJoblib(tqdmObject):

    '''
    Context manager to integrate tqdm progress bars with joblib Parallel operations.

    Temporarily patches joblib's BatchCompletionCallBack to update a tqdm progress
    bar after each batch completes. Automatically restores the original callback
    and closes the progress bar when the context exits.

    Parameters:
    -----------
    tqdmObject : tqdm.tqdm
        A tqdm progress bar instance to update during parallel execution

    Yields:
    -------
    tqdmObject : tqdm.tqdm
        The same progress bar object for use within the context

    Examples:
    ---------
    >>> from joblib import Parallel, delayed
    >>> from tqdm import tqdm
    >>>
    >>> with tqdmJoblib(tqdm(desc='Processing', total=100)) as pbar:
    ...     results = Parallel(n_jobs=-1)(
    ...         delayed(process_item)(item) for item in items
    ...     )

    '''

    import joblib

    class TqdmBatchCompletionCallback(joblib.parallel.BatchCompletionCallBack):
        def __call__(self, *args, **kwargs):
            tqdmObject.update(n=self.batch_size)
            return super().__call__(*args, **kwargs)

    oldBatchCallback = joblib.parallel.BatchCompletionCallBack
    joblib.parallel.BatchCompletionCallBack = TqdmBatchCompletionCallback
    try:
        yield tqdmObject
    finally:
        joblib.parallel.BatchCompletionCallBack = oldBatchCallback
        tqdmObject.close()

#--------------------------------------------------------------------------------------------------------------------------#
# -- Plot Drawing Tools (Primitives Class) -- #
#--------------------------------------------------------------------------------------------------------------------------#

class drawPrimitive():

    def __init__(self):

        a = 1

    def drawPentagon(self, sidestuffidk) -> np.ndarray:

        ...

    def drawEgg(self):

        ...

    def drawFlutedCrossSection(self, radius: float, fluteAmplitudeCoefficient: float = 0.2, numFlutes: int = 6, numPoints: int = 100, plot = True):

        '''
        
        Draw a fluted cooling channel cross section.
        
        '''

        crossSectionAngles = np.linspace(0, 2*np.pi, numPoints)
        fluteAmplitude     = fluteAmplitudeCoefficient * radius

        waveFullyFluted = radius + fluteAmplitude * np.sin(numFlutes * crossSectionAngles)
        xFullyFluted    = -(waveFullyFluted) * np.sin(crossSectionAngles)
        yFullyFluted    = -(waveFullyFluted) * np.cos(crossSectionAngles)

        if plot:
            # Plotting with white background during documentation for moving plot result to docs with transparent background
            plt.plot(xFullyFluted, yFullyFluted, 'k')
            plt.gca().set_aspect('equal')
            plt.show(block = False)

            # Default plot
            # plotLine(xFullyFluted, yFullyFluted)

        return xFullyFluted, yFullyFluted

# Stuff to make
# def csvSwap()

#--------------------------------------------------------------------------------------------------------------------------#
# -- Error Handling Classes -- #
#--------------------------------------------------------------------------------------------------------------------------#

from typing import Dict, Any, Optional

class RegenGeometryError(Exception):

    '''

    Base exception class for regenerative cooling geometry generation errors.

    This is the parent class for all regenerative cooling-related exceptions.
    All custom exceptions inherit from this class to allow for broad exception
    handling when needed.

    Attributes:
        message (str): Human-readable error message
        context (dict): Additional context about the error (station index, variable values, etc.)

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):

        '''

        Initialize the RegenGeometryError exception.

        Args:
            message: Human-readable description of the error
            context: Dictionary containing relevant state information when error occurred

        '''

        self.message = message
        self.context = context if context is not None else {}

        # Build detailed error message
        fullMessage = f'\n{"=" * 80}\n'
        fullMessage += f'REGENERATIVE GEOMETRY ERROR\n'
        fullMessage += f'{"=" * 80}\n'
        fullMessage += f'{message}\n'

        if self.context:
            fullMessage += f'\nError Context:\n'
            fullMessage += f'{"-" * 80}\n'
            for key, value in self.context.items():
                fullMessage += f'  {key}: {value}\n'

        fullMessage += f'{"=" * 80}\n'

        super().__init__(fullMessage)

    def getContext(self) -> Dict[str, Any]:

        '''

        Retrieve the error context dictionary.

        Returns:
            Dictionary containing error context information

        '''

        return self.context

class ConvergenceFailureError(RegenGeometryError):

    '''

    Exception raised when iterative solver fails to converge within iteration limit.

    This error occurs when numerical solvers (temperature convergence, channel radius
    optimization, etc.) cannot find a solution within the maximum allowed iterations.

    Common causes:
        - Incompatible design constraints (conflicting requirements)
        - Poor initial guess leading to oscillation
        - Numerical stiffness in governing equations
        - Step size too large or too small

    Attributes:
        iterations (int): Number of iterations attempted before failure
        tolerance (float): Convergence tolerance that was not met
        residual (float): Final residual/error value

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 iterations: Optional[int] = None, tolerance: Optional[float] = None,
                 residual: Optional[float] = None):

        '''

        Initialize the ConvergenceFailureError exception.

        Args:
            message: Description of the convergence failure
            context: Error context dictionary
            iterations: Number of iterations attempted
            tolerance: Required convergence tolerance
            residual: Final error/residual value

        '''

        if context is None:
            context = {}

        if iterations is not None:
            context['iterations'] = iterations
        if tolerance is not None:
            context['tolerance'] = tolerance
        if residual is not None:
            context['residual'] = residual

        super().__init__(message, context)

class GeometricConstraintError(RegenGeometryError):

    '''

    Exception raised when geometric constraints are violated or impossible to satisfy.

    This error occurs when the requested geometry cannot be physically realized due to
    geometric constraints such as:
        - Channel radius too small (< minimum fabrication limit)
        - Cross-sectional area approaching zero
        - Hydraulic diameter too small for correlation validity
        - Number of channels cannot fit around nozzle circumference
        - Channel path cannot be wrapped without self-intersection

    Attributes:
        constraintType (str): Type of geometric constraint violated
        value (float): Actual value that violated the constraint
        limit (float): Constraint limit that was exceeded

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 constraintType: Optional[str] = None, value: Optional[float] = None,
                 limit: Optional[float] = None):

        '''

        Initialize the GeometricConstraintError exception.

        Args:
            message: Description of the geometric constraint violation
            context: Error context dictionary
            constraintType: Type of constraint (e.g., 'channelRadius', 'CSA', 'hydraulicDiameter')
            value: Actual value that violated constraint
            limit: Constraint boundary value

        '''

        if context is None:
            context = {}

        if constraintType is not None:
            context['constraintType'] = constraintType
        if value is not None:
            context['value'] = value
        if limit is not None:
            context['limit'] = limit

        super().__init__(message, context)

class ThermalConstraintError(RegenGeometryError):

    '''

    Exception raised when thermal constraints cannot be satisfied.

    This error occurs when thermal requirements or limits are violated:
        - Wall temperature exceeds material limit
        - Coolant temperature exceeds decomposition temperature
        - Heat flux exceeds critical heat flux
        - Coolant state calculation failure (RefProp error)
        - Temperature convergence produces physically invalid results

    Attributes:
        thermalProperty (str): Which thermal property violated constraint
        value (float): Actual value of the property
        limit (float): Limit that was exceeded

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 thermalProperty: Optional[str] = None, value: Optional[float] = None,
                 limit: Optional[float] = None):

        '''

        Initialize the ThermalConstraintError exception.

        Args:
            message: Description of the thermal constraint violation
            context: Error context dictionary
            thermalProperty: Property that violated constraint (e.g., 'wallTemperature', 'heatFlux')
            value: Actual value
            limit: Limit value

        '''

        if context is None:
            context = {}

        if thermalProperty is not None:
            context['thermalProperty'] = thermalProperty
        if value is not None:
            context['value'] = value
        if limit is not None:
            context['limit'] = limit

        super().__init__(message, context)

class PressureDropError(RegenGeometryError):

    '''

    Exception raised when pressure drop exceeds allowable limits.

    This error occurs when the coolant pressure drop through the regenerative cooling
    channels exceeds the available pressure margin, or when coolant pressure becomes
    negative or approaches vapor pressure (risk of cavitation/boiling).

    Common causes:
        - Too many channels (high velocity)
        - Channels too small (high friction)
        - Excessive channel length
        - High momentum loss from bends
        - Insufficient inlet pressure

    Attributes:
        pressureDrop (float): Total pressure drop calculated [Pa]
        maxPressureDrop (float): Maximum allowable pressure drop [Pa]
        exitPressure (float): Calculated exit pressure [Pa]
        minExitPressure (float): Minimum required exit pressure [Pa]

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 pressureDrop: Optional[float] = None, maxPressureDrop: Optional[float] = None,
                 exitPressure: Optional[float] = None, minExitPressure: Optional[float] = None):

        '''

        Initialize the PressureDropError exception.

        Args:
            message: Description of the pressure drop error
            context: Error context dictionary
            pressureDrop: Calculated total pressure drop [Pa]
            maxPressureDrop: Maximum allowable pressure drop [Pa]
            exitPressure: Calculated exit pressure [Pa]
            minExitPressure: Minimum required exit pressure [Pa]

        '''

        if context is None:
            context = {}

        if pressureDrop is not None:
            context['pressureDrop'] = pressureDrop
        if maxPressureDrop is not None:
            context['maxPressureDrop'] = maxPressureDrop
        if exitPressure is not None:
            context['exitPressure'] = exitPressure
        if minExitPressure is not None:
            context['minExitPressure'] = minExitPressure

        super().__init__(message, context)

class InvalidInputError(RegenGeometryError):

    '''

    Exception raised when input parameters are invalid or out of acceptable range.

    This error is raised during input validation before expensive calculations begin.
    Catching invalid inputs early prevents wasted computation and provides clear
    feedback about what needs to be corrected.

    Common invalid inputs:
        - Negative values for physical quantities (mass flow, pressure, temperature)
        - Zero or negative channel count
        - Helix angle outside valid range (0°, 90°)
        - Empty or malformed geometry arrays
        - Incompatible parameter combinations

    Attributes:
        parameterName (str): Name of the invalid parameter
        value: Actual value provided
        validRange (str): Description of valid range

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 parameterName: Optional[str] = None, value: Any = None,
                 validRange: Optional[str] = None):

        '''

        Initialize the InvalidInputError exception.

        Args:
            message: Description of the invalid input
            context: Error context dictionary
            parameterName: Name of the parameter that is invalid
            value: The invalid value provided
            validRange: Description of the valid range for this parameter

        '''

        if context is None:
            context = {}

        if parameterName is not None:
            context['parameterName'] = parameterName
        if value is not None:
            context['value'] = value
        if validRange is not None:
            context['validRange'] = validRange

        super().__init__(message, context)

class NumericalInstabilityError(RegenGeometryError):

    '''

    Exception raised when numerical instabilities are detected (NaN, Inf, etc.).

    This error occurs when calculations produce non-finite values (NaN, Inf, -Inf)
    which indicate numerical breakdown. This is typically caused by:
        - Division by zero or near-zero values
        - Domain errors in mathematical functions (sqrt of negative, log of zero)
        - Overflow/underflow in floating point arithmetic
        - Accumulation of rounding errors
        - RefProp calculation failures

    Attributes:
        variableName (str): Name of variable containing non-finite value
        value: The problematic value (NaN, Inf, etc.)
        operation (str): Operation that produced the non-finite value

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 variableName: Optional[str] = None, value: Any = None,
                 operation: Optional[str] = None):

        '''

        Initialize the NumericalInstabilityError exception.

        Args:
            message: Description of the numerical instability
            context: Error context dictionary
            variableName: Name of variable with non-finite value
            value: The non-finite value
            operation: Mathematical operation that caused the issue

        '''

        if context is None:
            context = {}

        if variableName is not None:
            context['variableName'] = variableName
        if value is not None:
            context['value'] = value
        if operation is not None:
            context['operation'] = operation

        super().__init__(message, context)

class VoluteGenerationError(RegenGeometryError):

    '''

    Exception raised when volute (inlet/return manifold) generation fails.

    This error occurs when the Volute class cannot generate valid manifold geometry
    for interfacing the cooling channels with external feedlines. Common causes:
        - Invalid scroll geometry parameters
        - Wall thickness too small for structural requirements
        - Insufficient space for volute routing
        - Temperature/pressure outside material property data range
        - Stress exceeds material allowable stress

    Attributes:
        voluteType (str): Type of volute ('inlet' or 'return')
        failureMode (str): Specific failure mode

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 voluteType: Optional[str] = None, failureMode: Optional[str] = None):

        '''

        Initialize the VoluteGenerationError exception.

        Args:
            message: Description of the volute generation failure
            context: Error context dictionary
            voluteType: 'inlet' or 'return'
            failureMode: Specific mode of failure

        '''

        if context is None:
            context = {}

        if voluteType is not None:
            context['voluteType'] = voluteType
        if failureMode is not None:
            context['failureMode'] = failureMode

        super().__init__(message, context)

# Helper function to create error context snapshots
def createErrorContext(stationIndex: Optional[int] = None,
                       iterationCount: Optional[int] = None,
                       **kwargs) -> Dict[str, Any]:

    '''

    Create a standardized error context dictionary.

    This helper function creates a dictionary containing relevant state information
    at the point where an error occurred. This context is attached to exceptions
    to aid in debugging.

    Args:
        stationIndex: Axial station index where error occurred
        iterationCount: Iteration number when error occurred
        **kwargs: Additional key-value pairs to include in context

    Returns:
        Dictionary containing error context information

    Example:
        >>> context = createErrorContext(
        ...     stationIndex=42,
        ...     iterationCount=50,
        ...     channelRadius=0.001,
        ...     wallTemperature=850.0
        ... )

    '''

    context = {}

    if stationIndex is not None:
        context['stationIndex'] = stationIndex

    if iterationCount is not None:
        context['iterationCount'] = iterationCount

    # Add any additional context
    context.update(kwargs)

    return context