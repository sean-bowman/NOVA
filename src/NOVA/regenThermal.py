# -- NOVA: Regenerative Cooling Heat Transfer -- #

'''

The thermal model of a regeneratively cooled jacket, and the views that present it.

A cooling channel is solved one station at a time, marching from the coolant inlet. At each
station the hot wall temperature is unknown, so it is converged: a guess sets the gas-side
coefficient, the coefficient sets the heat flux, the flux sets a new wall temperature, and the
loop repeats until the two agree. The coolant state is then advanced to the next station through
the heat it absorbed and the pressure it lost.

The model takes its geometry and its gas state through one dictionary and reads nothing off a
Nozzle, so it can be driven directly. What it does need from the run around it -- where to write
figures, which wall alloy, whether to draw anything -- arrives as a RegenThermalContext.

Three channel families are supported and any combination of them may be solved in one pass, which
is what lets the fluted result be plotted against the circular one it replaced:

    circle   Circular channels. Coolant side is Gnielinski with a roughness-corrected friction
             factor.
    fluted   Spirally fluted channels. Coolant side is a fifty-fifty blend of Gnielinski with a
             spirally fluted correlation from Principles of Enhanced Heat Transfer.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Gas side, checked against a published source.** The exhaust-side coefficient is the Bartz
correlation as given in Huzel and Huang, NASA SP-125:

    h_g = (0.026 / D_t^0.2) (mu_0^0.2 c_p0 / Pr_0^0.6) (P_c / c*)^0.8 (D_t / R_c)^0.1 (A_t / A)^0.9 sigma

with the stagnation Prandtl number from 4 gamma / (9 gamma - 5), the stagnation viscosity from the
fit mu_0 = 1.184e-7 M^0.5 T_0^0.6, and sigma the boundary layer correction. That viscosity constant
is the SI form of SP-125's 46.6e-10 M^0.5 T^0.6 in lbm/(in s) with T in Rankine, which converts to
1.18408e-7 in SI. See tests/testRegenThermal.py for the comparison against a worked example.

**Coolant side, not validated.** The circular correlation is Gnielinski, which is published and
whose range of validity is known, but nothing here checks the implementation against a reference
case. The fluted correlation is a fifty-fifty blend of Gnielinski with a spirally fluted
correlation, with a roughness amplification applied to the second term only. No source states that
blend or its range of validity, and no measurement is available to set it against. It is a
correlation of convenience and results that rest on it should be read that way.

**The gas state the model reads is one dimensional.** Every gas-side property comes from CEA at a
one-dimensional station, while the near-wall Mach number the method of characteristics returns
departs from the one-dimensional value by up to 42 per cent near the throat. The two are
inconsistent with each other, and the throat is where the heat flux is highest.

All units are mass base SI:
    - Length      [m]
    - Area        [m^2]
    - Temperature [K]
    - Pressure    [Pa]
    - Mass flow   [kg/s]
    - Heat flux   [W]

Author: Sean Bowman

'''

import math
import os
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from tqdm import tqdm

import matplotlib.pyplot as plt

# Plotly backs the interactive views only. A plotly-free install loses the .html figures and
# nothing else, so the import is defensive and the gate below reports the skip once.
try:
    import plotly.graph_objects as go
    from plotly.offline import plot
    from plotly.subplots import make_subplots
    plotlyAvailable = True
except ImportError:
    go = plot = make_subplots = None
    plotlyAvailable = False

from .utils import (fluidProps, ConvergenceFailureError, InvalidInputError,
                    headlessPlots, showFigure)
from .ablative import blowingCorrection
from .materials import wallMaterialCurves
from .radiativeCooling import effectiveGasSideDriving, wallRadiationCoefficient
from .validation import applyRules, arrayRule, integerRule, numericRule, read, textRule

_plotlyNotices = set()

def _plotlyGate(featureName: str) -> bool:

    '''

    True when plotly is importable. Otherwise note once that an interactive view is being
    skipped and return False, so the caller can carry on without it.

    '''

    if plotlyAvailable:
        return True
    if featureName not in _plotlyNotices:
        _plotlyNotices.add(featureName)
        print(f'plotly is not installed; skipping {featureName}. Install it with "pip install plotly".')
    return False

@dataclass
class RegenThermalContext:

    '''

    Everything the thermal model needs from the run around it.

    This is the whole of the model's coupling to a Nozzle. Nothing here affects a number the
    model computes: it decides where figures are written and whether they are drawn at all, and
    names the wall alloy whose conductivity curve the conduction resistance is taken from.

    Attributes:
    -----------
    material : str
        Wall alloy name, resolved by materials.wallMaterialCurves.
    dataFolder : str
        Directory the figures are written to when export is on.
    plotsAdv : str
        'on' draws the interactive heat transfer view.
    plotsDocs : str
        'on' also writes the Matplotlib version the documentation uses.
    export : str
        'on' writes figures to dataFolder rather than opening them.
    debugMode : bool
        True dumps the local state of a failed station to a file in dataFolder.

    '''

    material:   str  = 'GRCop-42'
    dataFolder: str  = ''
    plotsAdv:   str  = 'off'
    plotsDocs:  str  = 'off'
    export:     str  = 'off'
    debugMode:  bool = False

def bartzHeatTransferCoefficient(nearWallTemperature: float, nearWallMachNumber: float,
                                 exhaustGamma: float, exhaustGasConstant: float,
                                 exhaustMolecularWeight: float, hotWallTemperature: float,
                                 chamberPressure: float, characteristicVelocity: float,
                                 throatDiameter: float, throatRadiusOfCurvature: float,
                                 throatArea: float, localArea: float) -> float:

    '''

    Gas-side convective heat transfer coefficient from the Bartz correlation.

    The form is the one given in Huzel and Huang, NASA SP-125:

        h_g = (0.026 / D_t^0.2) (mu_0^0.2 c_p0 / Pr_0^0.6) (P_c / c*)^0.8
              (D_t / R_c)^0.1 (A_t / A)^0.9 sigma

    The stagnation Prandtl number comes from 4 gamma / (9 gamma - 5) and the stagnation viscosity
    from the fit mu_0 = 1.184e-7 M^0.5 T_0^0.6. That constant is the SI form of SP-125's
    46.6e-10 M^0.5 T^0.6 in lbm/(in s) with T in Rankine.

    The exact conversion is 1.1840811e-7: 46.6e-10 lbm/(in s) is 8.3218128e-8 kg/(m s), and the
    Rankine-to-kelvin change of variable multiplies it by (9/5)^0.6. The coefficient used here is
    that value rounded to four figures, which is 6.8e-5 low. Through mu^0.2 in the Bartz
    expression that reaches the gas-side coefficient as 1.4e-5, well inside the correlation's own
    accuracy, so it is left as the number every recorded result was produced with rather than
    changed for a correction nothing can measure.

    Sigma is the boundary layer correction, which carries the whole dependence on wall
    temperature and is why the caller has to converge the wall rather than solve it directly.

    A near-wall temperature of exactly 300 K is a sentinel for a station that sees no exhaust,
    such as one out on a volute interface, and returns a free-convection estimate for stagnant
    air instead. Nothing in NOVA currently sets that value, so the branch is not reached; it is
    kept because a caller supplying its own station properties may still use it. Being an
    equality test against a float it would also be missed by 300.0000001, which is a reason not
    to rely on it.

    Parameters:
    -----------
    nearWallTemperature : float
        Static gas temperature at the wall [K]
    nearWallMachNumber : float
        Local Mach number [-]
    exhaustGamma : float
        Ratio of specific heats [-]
    exhaustGasConstant : float
        Specific gas constant [J/kg K]
    exhaustMolecularWeight : float
        Molecular weight [kg/kmol]
    hotWallTemperature : float
        Current guess at the gas-side wall temperature [K]
    chamberPressure : float
        Chamber stagnation pressure [Pa]
    characteristicVelocity : float
        Characteristic velocity [m/s]
    throatDiameter : float
        Throat diameter [m]
    throatRadiusOfCurvature : float
        Wall radius of curvature at the throat [m]
    throatArea : float
        Throat area [m^2]
    localArea : float
        Flow area at this station [m^2]

    Returns:
    --------
    float
        Gas-side convective heat transfer coefficient [W/m^2 K]

    '''

    if nearWallTemperature == 300:
        # estimate for HTC for stagnant air
        return 5

    totalTemperature        = nearWallTemperature * (1 + (exhaustGamma - 1)/2 * nearWallMachNumber**2)
    stagnationHeatCapacity  = (exhaustGamma / (exhaustGamma - 1)) * exhaustGasConstant
    stagnationPrandtl       = 4 * exhaustGamma / (9 * exhaustGamma - 5)
    stagnationViscosity     = 1.184e-7 * exhaustMolecularWeight**0.5 * totalTemperature**0.6

    boundaryLayerCorrectionFactor        = (0.5 * (hotWallTemperature / totalTemperature) *                                         (1 + (exhaustGamma - 1)/2 * nearWallMachNumber**2) + 0.5)**-0.68 *                                         ((1 + (exhaustGamma - 1)/2 * nearWallMachNumber**2))**-0.12
    constantBartzPart                    = (0.026 / (throatDiameter**0.2)) *                                         (stagnationViscosity**0.2 * stagnationHeatCapacity / (stagnationPrandtl**0.6)) *                                         (chamberPressure / characteristicVelocity)**0.8 *                                         (throatDiameter / throatRadiusOfCurvature)**0.1

    return (constantBartzPart *             (throatArea / localArea)**0.9 *             boundaryLayerCorrectionFactor)

@dataclass
class StationWallSolution:

    """

    The converged wall state at one station, for one channel cross section.

    Scalars only. The caller owns the arrays, which is what lets the two channel families share
    this solve without either of them learning the other's variable names.

    Attributes:
    -----------
    coolantConvectiveCoefficient : float
        Coolant-side convective coefficient [W/m^2 K].
    exhaustConvectiveCoefficient : float
        Gas-side convective coefficient from Bartz, after any blowing correction [W/m^2 K].
    radiationCoefficient : float
        Gas-to-wall radiative coefficient on the gas-to-wall temperature difference [W/m^2 K].
        Exactly zero when either emissivity is.
    radiativeHeatTransfer : float
        The radiative part of the heat through this station, per channel [W].
    blowingReduction : float
        Factor a film coolant reduced the convective coefficient by [-]. Exactly one with no film.
    wallConductivity : float
        Wall conductivity sampled at the converged hot wall temperature [W/m K].
    heatTransfer : float
        Heat through the wall at this station, per channel [W]. A power, not a flux: the areas
        are already folded into the three resistances.
    hotWallTemperature, coldWallTemperature : float
        The two faces of the wall [K].
    coolantTemperatureRise : float
        Temperature the coolant gains crossing this station [K]. The caller decides which
        station it lands on, because that depends on which way the march runs.
    iterations : int
        Passes the fixed point took.
    residual : float
        Final change in the hot wall temperature between passes [K].
    converged : bool
        False means the iteration ceiling was reached, and the values above are the last iterate.

    """

    coolantConvectiveCoefficient: float
    exhaustConvectiveCoefficient: float
    radiationCoefficient:         float
    radiativeHeatTransfer:        float
    blowingReduction:             float
    wallConductivity:             float
    heatTransfer:                 float
    hotWallTemperature:           float
    coldWallTemperature:          float
    coolantTemperatureRise:       float
    iterations:                   int
    residual:                     float
    converged:                    bool

def solveStationWallTemperature(drivingTemperature, gasStaticTemperature, gasMachNumber,
                                gasGamma, gasConstant, gasMolecularWeight,
                                coolantTemperature, coolantThermalConductivity,
                                coolantNusseltNumber, coolantSpecificHeat, coolantMassFlow,
                                hydraulicDiameter, coolantWettedArea,
                                hotWallArea, hotWallThickness, wallRadius, pathLength,
                                conductivityInterpolator,
                                chamberPressure, characteristicVelocity, throatDiameter,
                                throatRadiusOfCurvature, throatArea, localArea,
                                filmMassFlux: float = 0.0, blowingFactor: float = 0.5,
                                wallEmissivity: float = 0.0, gasEmissivity: float = 0.0,
                                tolerance: float = 0.01,
                                maximumIterations: int = 50) -> StationWallSolution:

    """

    Converge the hot wall temperature at one station against a three-resistance network.

    The wall temperature is not known in advance and cannot be solved directly, because two of
    the three resistances depend on it: the wall conductivity is a function of temperature, and
    the Bartz boundary layer correction carries the whole of the gas-side dependence on the wall.
    So it is iterated. A guess sets both, the network sets a heat flow, the flow sets a new wall
    temperature, and the pass repeats until the two agree.

    Successive substitution is enough because the map contracts hard: the only wall-temperature
    dependence of the gas-side coefficient is through the boundary layer correction, and it is
    weak. Typical stations converge in a handful of passes.

    The conduction resistance is cylindrical about the **nozzle** axis rather than the channel
    axis, because the assumption of cylindrical symmetry is only true about the nozzle: from
    there heat goes outward in every direction and cooling comes inward from every direction,
    while from a channel axis the heat arrives from one side only.

    Parameters:
    -----------
    drivingTemperature : float
        Gas temperature the heat flows from [K]. This is the quantity a film coolant reduces.
    gasStaticTemperature : float
        Static gas temperature [K], passed to Bartz, which forms its own total temperature and
        writes its boundary layer correction in the static value.
    gasMachNumber : float
        Local Mach number [-].
    gasGamma, gasConstant, gasMolecularWeight : float
        Exhaust ratio of specific heats [-], specific gas constant [J/kg K] and molecular
        weight [kg/kmol].
    coolantTemperature : float
        Bulk coolant temperature entering this station [K].
    coolantThermalConductivity : float
        Coolant conductivity [W/m K].
    coolantNusseltNumber : float
        Coolant-side Nusselt number from whichever correlation the family uses [-].
    coolantSpecificHeat : float
        Coolant specific heat [J/kg K].
    coolantMassFlow : float
        Coolant mass flow through one channel [kg/s].
    hydraulicDiameter : float
        Channel hydraulic diameter [m].
    coolantWettedArea : float
        Coolant-side area of this station, per channel [m^2].
    hotWallArea : float
        Gas-side area of this station, per channel [m^2].
    hotWallThickness : float
        Wall between coolant and exhaust [m].
    wallRadius : float
        Hot wall radius from the nozzle axis [m].
    pathLength : float
        Length of this station along the channel [m].
    conductivityInterpolator : callable
        Wall conductivity against temperature.
    chamberPressure, characteristicVelocity : float
        Chamber stagnation pressure [Pa] and characteristic velocity [m/s].
    throatDiameter, throatRadiusOfCurvature, throatArea : float
        Throat geometry Bartz needs [m], [m], [m^2].
    localArea : float
        Flow area at this station [m^2].
    filmMassFlux : float
        Film coolant leaving the wall here [kg/m^2 s]. Thickens the boundary layer and reduces
        the convective coefficient. Zero leaves the coefficient untouched, to the bit.
    blowingFactor : float
        Lambda in the blowing correlation [-].
    wallEmissivity : float
        Emissivity of the gas-side wall surface [-]. Zero switches radiation off exactly.
    gasEmissivity : float
        Total emissivity of the combustion gas over its mean beam length [-]. Zero switches
        radiation off exactly.
    tolerance : float
        Convergence tolerance on the hot wall temperature [K].
    maximumIterations : int
        Passes allowed before the caller is told it did not converge.

    Returns:
    --------
    StationWallSolution

    Raises:
    -------
    ValueError
        If the wall temperature guess goes NaN, which means an upstream quantity is already bad
        and letting it propagate would bury the cause a hundred stations later.

    """

    hotWallTemperatureGuess = drivingTemperature
    converged = False
    convergenceIteration = 0
    residual = float('nan')

    while not converged and convergenceIteration < maximumIterations:

        convergenceIteration += 1

        if np.isnan(hotWallTemperatureGuess):
            raise ValueError(
                'The hot wall temperature guess went NaN on pass {} of the station solve. The '
                'driving temperature was {}.'.format(convergenceIteration, drivingTemperature))

        wallConductivity = float(conductivityInterpolator(hotWallTemperatureGuess))

        coolantConvectiveCoefficient = coolantThermalConductivity * coolantNusseltNumber \
                                       / hydraulicDiameter
        coolantConvectiveResistance = 1 / (coolantConvectiveCoefficient * coolantWettedArea)

        conductiveResistance = np.log(1 + hotWallThickness / wallRadius) / \
                               (2*np.pi * pathLength * wallConductivity)

        exhaustConvectiveCoefficient = bartzHeatTransferCoefficient(
            gasStaticTemperature, gasMachNumber, gasGamma,
            gasConstant, gasMolecularWeight, hotWallTemperatureGuess,
            chamberPressure, characteristicVelocity, throatDiameter,
            throatRadiusOfCurvature, throatArea, localArea)

        # Film coolant leaving the wall thickens the boundary layer and pushes the temperature
        # gradient away from it. The blowing parameter is formed from the converged coefficient
        # rather than a frozen estimate, which costs one logarithm a pass and removes an
        # approximation. With no film the correction is exactly one and the product is exact.
        blowingReduction = 1.0
        if filmMassFlux != 0.0:
            stagnationSpecificHeat = (gasGamma / (gasGamma - 1.0)) * gasConstant
            blowingReduction = blowingCorrection(
                filmMassFlux * stagnationSpecificHeat / exhaustConvectiveCoefficient,
                blowingFactor)
            exhaustConvectiveCoefficient = exhaustConvectiveCoefficient * blowingReduction

        # Convection and radiation do not share a driving potential, so they are combined into
        # the one coefficient and one temperature that reproduce their sum exactly. With no
        # radiation both come back untouched and the network below is the one it always was.
        radiationCoefficient = wallRadiationCoefficient(
            wallEmissivity, gasEmissivity, gasStaticTemperature, hotWallTemperatureGuess)
        gasSideCoefficient, gasSideTemperature = effectiveGasSideDriving(
            exhaustConvectiveCoefficient, radiationCoefficient,
            drivingTemperature, gasStaticTemperature)

        exhaustConvectiveResistance = 1 / (gasSideCoefficient * hotWallArea)

        heatTransfer = (gasSideTemperature - coolantTemperature) / \
                       (coolantConvectiveResistance + conductiveResistance
                        + exhaustConvectiveResistance)
        hotWallTemperature  = gasSideTemperature - (heatTransfer * exhaustConvectiveResistance)
        coldWallTemperature = coolantTemperature + (heatTransfer * coolantConvectiveResistance)

        residual = abs(hotWallTemperatureGuess - hotWallTemperature)

        if residual < tolerance:
            converged = True
        else:
            hotWallTemperatureGuess = hotWallTemperature

    return StationWallSolution(
        coolantConvectiveCoefficient = coolantConvectiveCoefficient,
        exhaustConvectiveCoefficient = exhaustConvectiveCoefficient,
        radiationCoefficient         = radiationCoefficient,
        radiativeHeatTransfer        = radiationCoefficient * hotWallArea
                                       * (gasStaticTemperature - hotWallTemperature),
        blowingReduction             = blowingReduction,
        wallConductivity             = wallConductivity,
        heatTransfer                 = heatTransfer,
        hotWallTemperature           = hotWallTemperature,
        coldWallTemperature          = coldWallTemperature,
        coolantTemperatureRise       = heatTransfer / (coolantMassFlow * coolantSpecificHeat),
        iterations                   = convergenceIteration,
        residual                     = residual,
        converged                    = converged)

# What the thermal model needs in its input dictionary before it will run. Written as a table
# rather than as branches: see validation.py.
#
# The dictionary carries one entry per station for the distributed quantities and a scalar for the
# rest, and the cross-section arrays that describe a channel family are present only for the
# families being solved. A run must ask for at least one family, which is the one rule the table
# cannot express and that is checked alongside it.

def _hasFlutedSection(inputs):

    '''True when the dictionary carries a fluted cross section to solve.'''

    return read(inputs, 'gausFlutedCSA') is not None and read(inputs, 'gausFlutedSA') is not None

def _hasCircularSection(inputs):

    '''True when the dictionary carries a circular cross section to solve.'''

    return read(inputs, 'circleCSA') is not None and read(inputs, 'circleSA') is not None

def _hasDrivingTemperature(inputs):

    '''True when the caller supplied its own gas-side driving temperature.'''

    return read(inputs, 'drivingTemperature') is not None

def _hasWallRadiation(inputs):

    '''True when a wall emissivity was supplied, which is what switches radiation on.'''

    return read(inputs, 'wallEmissivity') is not None

def _hasFilmCooling(inputs):

    '''True when a film coolant mass flux was supplied.'''

    return read(inputs, 'filmMassFlux') is not None

regenThermalRules = (

    # -- Resolution and the wall the channels sit on -- #
    integerRule('numCrossSections', 'Cross sections', minimum = 1, exclusiveMinimum = False),
    integerRule('nChannel', 'Number of channels', minimum = 1, exclusiveMinimum = False),
    arrayRule('xHotWall3D', 'Hot wall axial coordinate', units = 'm'),
    arrayRule('rHotWall3D', 'Hot wall radius', units = 'm',
              positive = True, sameLengthAs = 'xHotWall3D'),
    numericRule('hotWallThickness', 'Hot wall thickness', units = 'm', minimum = 0),

    # -- The throat the gas-side correlation is scaled from -- #
    numericRule('throatRadiusOfCurvature', 'Throat radius of curvature', units = 'm', minimum = 0),
    numericRule('throatDiameter', 'Throat diameter', units = 'm', minimum = 0),
    numericRule('throatArea', 'Throat area', units = 'm^2', minimum = 0),

    # -- The path the coolant takes -- #
    arrayRule('differentialPathLength', 'Path length per station', units = 'm', positive = True),
    arrayRule('turnAngle', 'Turn angle per station', units = 'rad'),
    arrayRule('radiusOfCurvature', 'Bend radius per station', units = 'm', positive = True),

    # -- The coolant and the chamber it is cooling -- #
    textRule('coolant', 'Coolant species'),
    numericRule('mdot', 'Coolant mass flow per channel', units = 'kg/s', minimum = 0),
    numericRule('coolantInitialTemperature', 'Coolant inlet temperature', units = 'K', minimum = 0),
    numericRule('coolantInitialPressure', 'Coolant inlet pressure', units = 'Pa', minimum = 0),
    numericRule('chamberPressure', 'Chamber pressure', units = 'Pa', minimum = 0),
    numericRule('theoreticalCharVel', 'Characteristic velocity', units = 'm/s', minimum = 0),

    # -- The exhaust state at each station -- #
    arrayRule('gamma', 'Ratio of specific heats', positive = True),
    arrayRule('molecularWeight', 'Molecular weight', units = 'kg/kmol', positive = True),
    arrayRule('gasConstant', 'Specific gas constant', units = 'J/kg K', positive = True),
    arrayRule('nearWallTemperature', 'Near wall temperature', units = 'K', positive = True),
    arrayRule('nearWallMachNumber', 'Near wall Mach number'),

    # -- The cross sections of whichever families are being solved -- #
    arrayRule('gausFlutedCSA', 'Fluted cross-sectional area', units = 'm^2',
              positive = True, sameLengthAs = 'xHotWall3D', when = _hasFlutedSection),
    arrayRule('gausFlutedSA', 'Fluted wetted area', units = 'm^2',
              positive = True, sameLengthAs = 'xHotWall3D', when = _hasFlutedSection),
    arrayRule('fluteAmplitudeGauss', 'Flute amplitude', units = 'm',
              sameLengthAs = 'xHotWall3D', when = _hasFlutedSection),
    arrayRule('flutePitch', 'Flute pitch', units = 'm',
              positive = True, sameLengthAs = 'xHotWall3D', when = _hasFlutedSection),
    arrayRule('isCircle', 'Circular blend fraction',
              sameLengthAs = 'xHotWall3D', when = _hasFlutedSection),
    numericRule('fluteAmplitudeCoef', 'Flute amplitude coefficient',
                minimum = 0, when = _hasFlutedSection),
    numericRule('fluteHelixAngle', 'Flute helix angle', units = 'deg',
                minimum = -90, maximum = 90, when = _hasFlutedSection),

    arrayRule('circleCSA', 'Circular cross-sectional area', units = 'm^2',
              positive = True, sameLengthAs = 'xHotWall3D', when = _hasCircularSection),
    arrayRule('circleSA', 'Circular wetted area', units = 'm^2',
              positive = True, sameLengthAs = 'xHotWall3D', when = _hasCircularSection),

    # -- What the solve can be given, and runs without -- #
    #
    # Every rule here is guarded, because none of these is required. A dictionary that names none
    # of them describes a jacket with no radiation and no film, which is the case the model
    # reproduces bit for bit.
    arrayRule('drivingTemperature', 'Gas-side driving temperature', units = 'K',
              positive = True, sameLengthAs = 'xHotWall3D', when = _hasDrivingTemperature),
    numericRule('wallEmissivity', 'Hot wall surface emissivity',
                minimum = 0, maximum = 1, exclusiveMinimum = False, exclusiveMaximum = False,
                when = _hasWallRadiation,
                note = 'A property of the surface, not of the alloy. Oxide and roughness set it'),
    arrayRule('filmMassFlux', 'Film coolant mass flux at the wall', units = 'kg/m^2 s',
              sameLengthAs = 'xHotWall3D', when = _hasFilmCooling),
)

def validateRegenHeatTransferInputs(inputsDict: dict) -> None:

    """

    Check that the thermal model has what it needs before it starts marching.

    The rules are the table above, checked by `validation.applyRules`, plus the one thing a table
    cannot say: a run has to ask for at least one channel family, or there is nothing to solve.

    Parameters:
    -----------
    inputsDict : dict
        Geometry, gas state and coolant state, one entry per station.

    Raises:
    -------
    InvalidInputError
        On the first rule the dictionary fails.

    """

    if not (_hasFlutedSection(inputsDict) or _hasCircularSection(inputsDict)):
        raise InvalidInputError(
            message = ('No channel cross section was supplied, so there is nothing to solve. '
                       'Provide gausFlutedCSA and gausFlutedSA for a fluted channel, or '
                       'circleCSA and circleSA for a circular one'),
            parameterName = 'gausFlutedCSA, circleCSA',
            value = None,
            validRange = 'At least one channel family')

    applyRules(inputsDict, regenThermalRules)

def regenHeatTransferModel(context, inputsDict: dict, constantColdWallTemperature: float = None,
                           returnDict: bool = False, plots: bool = True, titleFlare: str = '',
                           xReference = [], rReference = []):

    r'''

    -- Regenerative Cooling Channels Heat Transfer Model (Version 2) --

    This function structures the heat transfer model for the Dauntless
    Regenerative Cooling Jacket. The heat transfer model is relatively
    straightforward, however of particularly interesting note is the method by
    which friction factor and Nusselt number (and subsequently heat transfer
    coef.) are calculated for the spirally fluted geometry.
    For more reference see:
    Principles of Enhanced Heat Transfer pp. 271
    for the presentation of friction factor and Nusselt number for spirally
    fluted tubes. This heat transfer correlation is used to determine the heat
    transfer into the oxygen in the cooling jacket as well as subsequent hot
    wall temperature and resultant fluid properties.

    ---------------------------------------------------------------------------
    # Inputs (Editing Config_File.csv)
    ---------------------------------------------------------------------------
    Interfacing with the Regeneratively Cooled Nozzle Design Module is done through editing Config_File.csv

    From the Matlab folder structure, right click the Config_File_RND.csv and select "Open Outside MATLAB".
    Make any changes to the configuration as necessary and, if applicable, change the configuration name to
    make distinct the current function run from other configurations. The configuration name (specified in the
    top right of the config file) names the top directory under the Outputs folder of the current project, and
    all subsequent runs of the function's outputs are stored in a datetime'd folder under the top directory
    specified by the configuration name given in the config file.

    If navigating to the repository through the Windows File Explorer, simply open the Config_File.csv in an
    appropriate .csv editor (such as Microsoft Excel) to make the required configuration changes before a run.

    ---------------------------------------------------------------------------
    ## Geometry Parameters
    ---------------------------------------------------------------------------
    Certain geometric properties of the channels are editable by the user:

    | Variable Description                   |  Units |
    |:--------------------------------------:|-------:|
    | Hot Wall Thickness                     |    [m] |
    | Channel Radius at Regen Inlet          |    [m] |
    | Channel Radius at Regen Throat         |    [m] |
    | Channel Radius at Nozzle Throat Inlet  |    [m] |
    | Channel Radius at Chamber Interface      |    [m] |
    | Channel Radius at Regen Return         |    [m] |
    | Infill Thickness                       |    [m] |
    | Number of Flutes                       |  [int] |
    | Flute Amplitude Coefficient            | [double, % of channel radius] |
    | Flute Helix Angle                      |  [deg] |
    | Channel Number Modifier                | [double, % reduction from 1] |

    ---------------------------------------------------------------------------
    ## Fluid Properties
    ---------------------------------------------------------------------------
    Parameters pertaining to the heat transfer model may also be supplied by
    the user:

    | Variable Description | Units  |
    |:--------------------:|-------:|
    | Coolant Species      | [Case Insensitive String] |
    | Initial Temperature  |    [K] |
    | Initial Pressure     |   [Pa] |
    | Total Mass Flow      | [kg/s] |

    ---------------------------------------------------------------------------
    ## Options
    ---------------------------------------------------------------------------
    Certain functionality of the code can be disabled/enabled by entering either a 0 or a 1
    respectively for the presented options in the config file.

    | Option Functionality                                                                 |   Input Options  |
    |:------------------------------------------------------------------------------------:|-----------------:|
    | Enable/disable gaussian cross section compression                                    | $\epsilon$ [0,1] |
    | Declaring the half compression to be over the entire channel length                  | $\epsilon$ [0,1] |
    | Enable/disable circular inlet and outlet regions of pipe for CAD volute intersection | $\epsilon$ [0,1] |
    | Enable/disable rectangular single-channel cutout generation for CAD                  | $\epsilon$ [0,1] |
    | Enable/disable plotted outputs                                                       | $\epsilon$ [0,1] |
    | Enable/disable command window progress bar                                           | $\epsilon$ [0,1] |
    | Enable/disable exporting geometry of the generated mesh                              | $\epsilon$ [0,1] |
    | Declare export type for geometry exporter                                            | case insensitive string |
    | Integer subdivision of arrays to increase final .stl fidelity (linear increase in array length) | [int] |

    ---------------------------------------------------------------------------
    # Outputs
    ---------------------------------------------------------------------------
    The geometry generator function creates two output arrays, one for the channel geometry and
    one for the nozzle geometry. All outputs are in Mass Base SI Units [m,Pa,K,etc.]:

    - Channel Geometric Parameters (14 x n Array):
        + X coordinates of channel pathline
        + Channel Radius Array
        + Channel Cross Sectional Area Array
        + Channel Surface Area Array
        + Channel Circumference Array
        + Segmented Length of Pathline Array
        + Total Channel Length
        + Channel Radius vs. Flute Amplitude Ratio Array
        + Pitch of the flutes
        + Channel Helix Angle
        + Number of Channels
        + gausFlutedCSA, gausFlutedSA, Circumference of characteristic circular cross sections

    - Nozzle Geometric Parameters (4 x n Array):
        + Nozzle axial coordinates (Inner Nozzle Wall)
        + Nozzle radial coordinates (Inner Nozzle Wall)
        + Nozzle wall offset (parallel offset by wall thickness)
        + Nozzle inner wall circumference

    The heat transfer model outputs only two parameters:

    - Total Pressure Drop
    - Fluid Temperature at Nozzle/Chamber Interface

    # Required code(s):
    All codes required to run the design code are present in the project. When the project file (RegenNozzleDesignModule.prj)
    is opened (initialized) all subfolders in the project are added to the current path, so no additional
    effort is required on behalf of the user. The relevant functions that live in the project subfolders
    that are needed to run this design code are as follows:

    - refWrap.m
    - intersections.m

    Author: Sean Bowman
    Date:   01/17/2023

    '''

    import time
    import traceback

    start_time = time.time()

    # Validate all required inputs before expensive calculations
    validateRegenHeatTransferInputs(inputsDict)

    def dumpDebugInfo(local_vars, iteration, elapsed_time):

        '''

        Dumps all local variables to a CSV file for debugging timeout issues.

        Parameters:
        - local_vars: dict of local variables from locals()
        - iteration: current iteration number (or None if not in loop)
        - elapsed_time: time elapsed since method start

        '''

        try:

            # Determine output folder
            if context.dataFolder:
                output_folder = context.dataFolder
            else:
                output_folder = 'timeout_debug_output'

            # Ensure output folder exists
            os.makedirs(output_folder, exist_ok=True)

            # Create timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{output_folder}\\timeout_debug_regenHeatTransferModel_{timestamp}.csv"

            # Collect debug information
            debug_data = []

            # Add metadata
            debug_data.append({
                'Variable': '__METADATA__',
                'Type': 'metadata',
                'Value': f'Timeout at iteration {iteration}',
                'Shape': '',
                'Dtype': '',
                'Sample': f'Elapsed time: {elapsed_time:.2f}s'
            })

            debug_data.append({
                'Variable': '__STACK_TRACE__',
                'Type': 'traceback',
                'Value': ''.join(traceback.format_stack()),
                'Shape': '',
                'Dtype': '',
                'Sample': ''
            })

            # Process each variable
            for var_name, var_value in local_vars.items():
                # Skip internal variables and large objects
                if var_name.startswith('_') or var_name in ['context', 'dumpDebugInfo', 'check_timeout']:
                    continue

                var_type = type(var_value).__name__

                try:
                    if isinstance(var_value, np.ndarray):
                        # Handle numpy arrays
                        shape_str = str(var_value.shape)
                        dtype_str = str(var_value.dtype)

                        # Sample values (first and last 3 elements for 1D, or summary for larger)
                        if var_value.size > 0:
                            if var_value.ndim == 1:
                                if len(var_value) <= 6:
                                    sample = str(var_value)
                                else:
                                    sample = f"[{var_value[0]}, {var_value[1]}, {var_value[2]}, ..., {var_value[-3]}, {var_value[-2]}, {var_value[-1]}]"
                            else:
                                sample = f"min={np.min(var_value)}, max={np.max(var_value)}, mean={np.mean(var_value)}"
                        else:
                            sample = "empty array"

                        debug_data.append({
                            'Variable': var_name,
                            'Type': var_type,
                            'Value': f'Array shape {shape_str}',
                            'Shape': shape_str,
                            'Dtype': dtype_str,
                            'Sample': sample
                        })
                    elif isinstance(var_value, (int, float, str, bool)):
                        # Handle simple scalar types
                        debug_data.append({
                            'Variable': var_name,
                            'Type': var_type,
                            'Value': str(var_value),
                            'Shape': 'scalar',
                            'Dtype': var_type,
                            'Sample': str(var_value)
                        })
                    elif isinstance(var_value, (list, tuple)):
                        # Handle lists and tuples
                        length = len(var_value)
                        if length <= 6:
                            sample = str(var_value)
                        else:
                            sample = f"[{var_value[0]}, {var_value[1]}, ..., {var_value[-2]}, {var_value[-1]}]"

                        debug_data.append({
                            'Variable': var_name,
                            'Type': var_type,
                            'Value': f'{var_type} of length {length}',
                            'Shape': f'({length},)',
                            'Dtype': var_type,
                            'Sample': sample
                        })
                    else:
                        # Handle other types generically
                        debug_data.append({
                            'Variable': var_name,
                            'Type': var_type,
                            'Value': str(type(var_value)),
                            'Shape': '',
                            'Dtype': '',
                            'Sample': str(var_value)[:100]  # First 100 chars
                        })
                except Exception as e:
                    # If we can't process a variable, record the error
                    debug_data.append({
                        'Variable': var_name,
                        'Type': var_type,
                        'Value': f'ERROR: {str(e)}',
                        'Shape': '',
                        'Dtype': '',
                        'Sample': ''
                    })

            # Create DataFrame and save to CSV
            df = pd.DataFrame(debug_data)
            df.to_csv(filename, index=False)

            return filename

        except Exception as e:
            # If dumping fails, at least print the error
            print(f"ERROR: Failed to dump debug info: {str(e)}")
            return None

    # -- Local Scope the Inputs Dictionary -- #

    # Resolution Options
    numCrossSections          = inputsDict["numCrossSections"]
    if numCrossSections > 1:
        iterationMode         = 'loop'
    elif numCrossSections == 1:
        iterationMode         = 'single'
        plots                 = False
        returnDict            = True
    # Nozzle geometric Properties
    nChannel                  = inputsDict["nChannel"]
    xHotWall3D                = inputsDict["xHotWall3D"]
    rHotWall3D                = inputsDict["rHotWall3D"]
    hotWallThickness          = inputsDict["hotWallThickness"]
    throatRadiusOfCurvature   = inputsDict["throatRadiusOfCurvature"]
    throatDiameter            = inputsDict["throatDiameter"]
    throatArea                = inputsDict["throatArea"]
    # Cross section and centerline geometric properties
    if 'gausFlutedCSA' in inputsDict and 'gausFlutedSA' in inputsDict:
        if inputsDict['gausFlutedCSA'] is not None and inputsDict['gausFlutedSA'] is not None:
            runFluted             = True
            gausFlutedCSA         = inputsDict["gausFlutedCSA"]
            gausFlutedSA          = inputsDict["gausFlutedSA"]
            fluteAmplitudeGauss   = inputsDict["fluteAmplitudeGauss"]
            fluteAmplitudeCoef    = inputsDict["fluteAmplitudeCoef"]
            flutePitch            = inputsDict["flutePitch"]
            fluteHelixAngle       = inputsDict["fluteHelixAngle"]
            isCircle              = inputsDict["isCircle"]
        else:
            runFluted             = False
    else:
        runFluted                 = False
    if 'circleCSA' in inputsDict and 'circleSA' in inputsDict:
        if inputsDict['circleCSA'] is not None and inputsDict['circleSA'] is not None:
            runCircle             = True
            circleCSA             = inputsDict["circleCSA"]
            circleSA              = inputsDict["circleSA"]
        else:
            runCircle             = False
    else:
        runCircle                 = False
    if not runFluted and not runCircle:
        raise Exception('regenHeatTransferModel: Please specify cross sectional area AND surface area'
        'for at least one cross section type.')
    differentialPathLength    = inputsDict["differentialPathLength"]
    turnAngle                 = inputsDict["turnAngle"]
    radiusOfCurvature         = inputsDict["radiusOfCurvature"]
    # Combustion properties
    coolant                   = inputsDict["coolant"]
    mdot                      = inputsDict["mdot"]
    chamberPressure           = inputsDict["chamberPressure"]
    coolantInitialTemperature = inputsDict["coolantInitialTemperature"]
    coolantInitialPressure    = inputsDict["coolantInitialPressure"]
    theoreticalCharVel        = inputsDict["theoreticalCharVel"]
    exhaustGamma              = inputsDict["gamma"]
    exhaustMolecularWeight    = inputsDict["molecularWeight"]
    exhaustGasConstant        = inputsDict["gasConstant"]
    nearWallTemperature       = inputsDict["nearWallTemperature"]
    nearWallMachNumber        = inputsDict["nearWallMachNumber"]

    # Calculated properties
    nozzleAreas             = np.pi * rHotWall3D**2
    nozzleCircumference     = 2 * np.pi * rHotWall3D
    hotWallArea             = (nozzleCircumference / nChannel) * abs(differentialPathLength)

    # -- What the solve is driven by, and the two terms that are absent unless asked for -- #

    def optionalInput(name, default):

        '''One optional entry, per station, with None and NaN both meaning it was not given.'''

        value = inputsDict.get(name)
        if value is None:
            value = default
        array = np.atleast_1d(np.asarray(value, dtype = float))
        array = np.where(np.isnan(array), default, array)

        return array if array.size == numCrossSections \
               else np.full(numCrossSections, array.flat[0])

    def optionalScalar(name, default):

        '''One optional scalar, with None and NaN both meaning it was not given.'''

        value = inputsDict.get(name)

        return default if value is None or np.isnan(value) else float(value)

    # Named for what it is rather than for what produced it. A film coolant writes it, and so
    # does the choice between a static and a recovery temperature; the solve never learns which.
    # Absent, it is *bound* to the near-wall temperature rather than copied, so the subtraction
    # downstream has literally the same operand and a run without it is bit-identical.
    drivingTemperature = inputsDict.get('drivingTemperature')
    if drivingTemperature is None:
        drivingTemperature = nearWallTemperature

    # Both default to zero, and zero is exact here: the radiative coefficient returns exactly 0.0
    # and the blowing correction exactly 1.0, so neither moves a bit of the answer.
    wallEmissivity = optionalScalar('wallEmissivity', 0.0)
    blowingFactor  = optionalScalar('blowingFactor', 0.5)
    gasEmissivity  = optionalInput('gasEmissivity', 0.0)
    filmMassFlux   = optionalInput('filmMassFlux', 0.0)
    if runFluted:
        flutedHydraulicDiameter = np.sqrt(4 * gausFlutedCSA / np.pi)
    if runCircle:
        circleHydraulicDiameter = np.sqrt(4 * circleCSA / np.pi)

    # Temperature-dependent wall thermal conductivity for the selected alloy, sampled from
    # materials.wallMaterialCurves. Legacy 'cu' / 'al' / 'in' keys still resolve.
    wallCurves                          = wallMaterialCurves(context.material)
    wallTemperatureGridKelvin           = wallCurves['temperatureK']
    wallThermalConductivityData         = wallCurves['thermalConductivity']
    wallThermalConductivityInterpolator = np.empty(numCrossSections, dtype=object)
    # Use boundary values instead of extrapolation to avoid negative conductivity
    wallThermalConductivityInterpolator.fill(interp1d(
        wallTemperatureGridKelvin, wallThermalConductivityData, kind='linear',
        bounds_error=False, fill_value=(wallThermalConductivityData[0], wallThermalConductivityData[-1])))

    # Adiabatic cold wall
    if constantColdWallTemperature is not None:
        runAdiabaticColdWall = True
    else:
        runAdiabaticColdWall = False

    # Collapse array initializations
    if True:

        # Fluted Cooling Channel Geometry and Flow Properties
        flutedCoolantTemperature, flutedCoolantPressure, flutedCoolantVelocity, \
        flutedCoolantMachNumber, flutedCoolantReynoldsNumber, flutedCoolantNusseltNumber, \
        flutedCoolantConvectiveHeatTransferCoef, flutedExhaustConvectiveHeatTransferCoef, flutedHeatTransfer, \
        flutedWallConductivity, flutedHotWallTemperature, flutedColdWallTemperature \
        = [np.zeros(numCrossSections) for _ in range(12)]

        flutedCoolantTemperature[-1] = coolantInitialTemperature
        flutedCoolantPressure[-1]    = coolantInitialPressure

        # Fluted Cooling Channel Thermophysical Properties
        flutedCoolantDensity, flutedCoolantViscosity, flutedCoolantSpecificHeat, \
        flutedCoolantGamma, flutedCoolantThermalConductivity, flutedCoolantSpeedOfSound, \
        flutedCoolantEnthalpy, flutedCoolantPrandtlNumber \
        = [np.zeros(numCrossSections) for _ in range(8)]

        flutedCoolantThermalConductivity[-1] = np.mean(wallThermalConductivityData)

        # Radiation is reported separately from the total so a reader can see how
        # much of the flux it actually is, and the blowing factor so a film-cooled run
        # shows how much of the coefficient it removed. Inert values unless asked for.
        flutedRadiativeHeatTransfer = np.zeros(numCrossSections)
        flutedBlowingReduction      = np.ones(numCrossSections)

        # Circular Cooling Channel Geometry and Flow Properties (for comparison)
        circleCoolantTemperature, circleCoolantPressure, circleCoolantVelocity, \
        circleCoolantMachNumber, circleCoolantReynoldsNumber, circleCoolantNusseltNumber, \
        circleCoolantConvectiveHeatTransferCoef, circleExhaustConvectiveHeatTransferCoef, circleHeatTransfer, circleWallConductivity, \
        circleHotWallTemperature, circleColdWallTemperature \
        = [np.zeros(numCrossSections) for _ in range(12)]

        circleCoolantTemperature[-1] = coolantInitialTemperature
        circleCoolantPressure[-1]    = coolantInitialPressure

        # Circle Cooling Channel Thermophysical Properties
        circleCoolantDensity, circleCoolantViscosity, circleCoolantSpecificHeat, \
        circleCoolantGamma, circleCoolantThermalConductivity, circleCoolantSpeedOfSound, \
        circleCoolantEnthalpy, circleCoolantPrandtlNumber \
        = [np.zeros(numCrossSections) for _ in range(8)]

        circleCoolantThermalConductivity[-1] = np.mean(wallThermalConductivityData)

        # Radiation is reported separately from the total so a reader can see how
        # much of the flux it actually is, and the blowing factor so a film-cooled run
        # shows how much of the coefficient it removed. Inert values unless asked for.
        circleRadiativeHeatTransfer = np.zeros(numCrossSections)
        circleBlowingReduction      = np.ones(numCrossSections)

        thermalPerformanceFactor = np.zeros(numCrossSections)

        # Adiabatic Cold Wall Properties
        flutedAdiabaticConvectiveHeatTransferCoef, flutedAdiabaticHeatTransfer, \
        circleAdiabaticConvectiveHeatTransferCoef, circleAdiabaticHeatTransfer, \
        = [np.zeros(numCrossSections) for _ in range(4)]

    # -- Loop over channel sections and calculate heat transfer properties -- #

    def heatTransferModel(iterator: int):

        '''

        Wrapper around heat transfer model to make it easy to compress and debug.

        '''

        i = iterator

        def findKFactor(turnAngle, radiusOfCurvature, hydraulicDiameter):

            '''

            Discretized momentum loss coefficient equation based on effective bend radius and turn angle:

            - turnAngle : angle between the two vectors defined by the three points in focus [rad]
            - L         : total length of segment in focus; distance between point 1 and 2 plus distance between 2 and 3 [m]
            - R         : effective bend radius; radius of circle that passes through the three points in focus [m]

            R = L / (2 * sin(turnAngle / 2))

            - D     : diameter of channel [m]
            - K_90  : K-factor for a 90 deg bend

            K_90 = 0.085 + 0.14 * (R / D)**-3

            0.085 represents a baseline loss for a very long-radius 90deg bend.
            The second term captures the sharp increase in losses as the bend becomes tighter (R/D gets smaller).
            Now we scale for the actual bend angle to get real K-factor:

            K_bend  : K-factor for any turn angle and effective bend radius

            K_bend = K_90 * (2 * turnAngle / pi)

            Expanded out:

            K_bend = (0.085 + 0.14 * (R / D)**-3) * (2 * turnAngle / pi)

            '''

            K_90 = 0.085 + 0.14 * (radiusOfCurvature / hydraulicDiameter)**-3
            K_bend = K_90 * (2 * turnAngle / np.pi)

            return K_bend

        # Fluted Channel Properties
        if runFluted:

            # Pull thermophysical properties at the current (T, P) with RefProp
            flutedCoolantDensity[i], flutedCoolantViscosity[i], flutedCoolantSpecificHeat[i], \
            flutedCoolantGamma[i], flutedCoolantThermalConductivity[i], flutedCoolantSpeedOfSound[i], \
            flutedCoolantEnthalpy[i], flutedCoolantPrandtlNumber[i] \
            = fluidProps(coolant, 'TP', 'D VIS Cp Cp/Cv TCX W H PRANDTL', flutedCoolantTemperature[i], flutedCoolantPressure[i])

            # Calculate dependept flow properties
            flutedCoolantVelocity[i]       = mdot / (flutedCoolantDensity[i] * gausFlutedCSA[i])
            flutedCoolantMachNumber[i]     = flutedCoolantVelocity[i] / flutedCoolantSpeedOfSound[i]
            flutedCoolantReynoldsNumber[i] = flutedCoolantDensity[i] * flutedHydraulicDiameter[i] * flutedCoolantVelocity[i] / flutedCoolantViscosity[i]

            # Calculate Nusselt Number
            # Frankenstein Correlation: Blend between Gnielinski and Spirally Fluted Heat Transfer from Principles of Enhanced Heat Transfer [6]
            surfaceRoughness       = 35e-6 # Velo3D GRCop-42 material datasheet
            frictionGnielinskiPart = 0.25 / (np.log10((surfaceRoughness / flutedHydraulicDiameter[i])/3.7 + 5.74/flutedCoolantReynoldsNumber[i]**0.9))**2
            frictionGnielinskiPart_smooth = (0.79 * np.log(flutedCoolantReynoldsNumber[i]) - 1.64)**-2
            frictionPoEHTPart      = (1.209 * flutedCoolantReynoldsNumber[i]**-0.261 * \
                                    (fluteAmplitudeGauss[i] / flutedHydraulicDiameter[i])**(1.26 - 0.05 * (flutePitch[i] / flutedHydraulicDiameter[i])) * \
                                    (flutePitch[i] / flutedHydraulicDiameter[i])**(-1.66 + 2.033 * (fluteAmplitudeGauss[i] / flutedHydraulicDiameter[i])) * \
                                    (fluteHelixAngle / 90)**(-2.669 + 3.67 * (fluteAmplitudeGauss[i] / flutedHydraulicDiameter[i])))

            nusseltGnielinskiPart  = ((frictionGnielinskiPart / 8) * (flutedCoolantReynoldsNumber[i] - 1000) * flutedCoolantPrandtlNumber[i]) / \
                                    (1 + 12.7 * (frictionGnielinskiPart / 8)**(1/2) * (flutedCoolantPrandtlNumber[i]**(2/3) - 1))
            nusseltGnielinskiPart_smooth  = ((frictionGnielinskiPart_smooth / 8) * (flutedCoolantReynoldsNumber[i] - 1000) * flutedCoolantPrandtlNumber[i]) / \
                                    (1 + 12.7 * (frictionGnielinskiPart_smooth / 8)**(1/2) * (flutedCoolantPrandtlNumber[i]**(2/3) - 1))
            nusseltPoEHTPart       = 0.064 * flutedCoolantReynoldsNumber[i]**0.773 * flutedCoolantPrandtlNumber[i]**0.4 * \
                                    (fluteAmplitudeGauss[i] / flutedHydraulicDiameter[i])**-0.242 * \
                                    (flutePitch[i] / flutedHydraulicDiameter[i])**-0.108 * \
                                    (fluteHelixAngle / 90)**0.599

            frictionRoughnessAmplificationFactor    = frictionGnielinskiPart / frictionGnielinskiPart_smooth
            nusseltRoughnessAmplificationFactor     = nusseltGnielinskiPart / nusseltGnielinskiPart_smooth

            flutedFrictionFactor          = (0.5 * frictionGnielinskiPart + 0.5 * frictionPoEHTPart*frictionRoughnessAmplificationFactor) * (1 - isCircle[i]) + \
                                            frictionGnielinskiPart * isCircle[i]
            flutedCoolantNusseltNumber[i] = (0.5 * nusseltGnielinskiPart + 0.5 * nusseltPoEHTPart*nusseltRoughnessAmplificationFactor) * (1 - isCircle[i]) + \
                                            nusseltGnielinskiPart * isCircle[i]

            # Calculate pressure drop and update downstream pressure for each channel section
            momentumLossCoef = findKFactor(turnAngle[i], radiusOfCurvature[i], flutedHydraulicDiameter[i])

            frictionPressureDrop = differentialPathLength[i] * flutedFrictionFactor * flutedCoolantDensity[i] * flutedCoolantVelocity[i]**2 / (2 * flutedHydraulicDiameter[i])
            momentumPressureDrop = momentumLossCoef * flutedCoolantDensity[i] * flutedCoolantVelocity[i]**2 / 2
            totalPressureDrop    = frictionPressureDrop + momentumPressureDrop

            if i > 0:
                flutedCoolantPressure[i-1] = flutedCoolantPressure[i] - totalPressureDrop
            if iterationMode == 'single':
                flutedCoolantPressure[i] = flutedCoolantPressure[i] - totalPressureDrop

        # Circular Channel Properties
        if runCircle:

            # Pull thermophysical properties at the current (T, P) with RefProp
            circleCoolantDensity[i], circleCoolantViscosity[i], circleCoolantSpecificHeat[i], \
            circleCoolantGamma[i], circleCoolantThermalConductivity[i], circleCoolantSpeedOfSound[i], \
            circleCoolantEnthalpy[i], circleCoolantPrandtlNumber[i] \
            = fluidProps(coolant, 'TP', 'D VIS Cp Cp/Cv TCX W H PRANDTL', circleCoolantTemperature[i], circleCoolantPressure[i])

            # Calculate dependept flow properties
            circleCoolantVelocity[i]       = mdot / (circleCoolantDensity[i] * circleCSA[i])
            circleCoolantMachNumber[i]     = circleCoolantVelocity[i] / circleCoolantSpeedOfSound[i]
            circleCoolantReynoldsNumber[i] = circleCoolantDensity[i] * circleHydraulicDiameter[i] * circleCoolantVelocity[i] / circleCoolantViscosity[i]

            # Calculate Nusselt Number
            # Petukhov friction factor for Gnielinski Nusselt Number for turbulent internal flows for circle channels
            surfaceRoughness       = 35e-6 # Velo3D GRCop-42 material datasheet
            circleFrictionFactor          = 0.25 / (np.log10((surfaceRoughness / circleHydraulicDiameter[i])/3.7 + 5.74/circleCoolantReynoldsNumber[i]**0.9))**2
            circleCoolantNusseltNumber[i] = ((circleFrictionFactor / 8) * (circleCoolantReynoldsNumber[i] - 1000) * circleCoolantPrandtlNumber[i]) / \
                                            (1 + 12.7 * (circleFrictionFactor / 8)**(1/2) * (circleCoolantPrandtlNumber[i]**(2/3) - 1))

            # Calculate pressure drop and update downstream pressure for each channel section
            momentumLossCoef = findKFactor(turnAngle[i], radiusOfCurvature[i], circleHydraulicDiameter[i])

            frictionPressureDrop = differentialPathLength[i] * circleFrictionFactor * circleCoolantDensity[i] * circleCoolantVelocity[i]**2 / (2 * circleHydraulicDiameter[i])
            momentumPressureDrop = momentumLossCoef * circleCoolantDensity[i] * circleCoolantVelocity[i]**2 / 2
            totalPressureDrop    = frictionPressureDrop + momentumPressureDrop

            if i > 0:
                circleCoolantPressure[i-1] = circleCoolantPressure[i] - totalPressureDrop
            if iterationMode == 'single':
                circleCoolantPressure[i] = circleCoolantPressure[i] - totalPressureDrop

        # Calculate thermal performance factor
        if runFluted and runCircle:
            thermalPerformanceFactor[i] = (flutedCoolantNusseltNumber[i] / circleCoolantNusseltNumber[i]) / \
                                        (flutedFrictionFactor / circleFrictionFactor)**(1/3)

        # Check if there are any nans anywhere in here
        if True:
            for name, value in locals().items():
                try:
                    # Check scalars
                    if isinstance(value, (float, int)) and math.isnan(value):
                        print(f"{name} is NaN (scalar)")
                        if context.debugMode:
                            breakpoint()
                        else:
                            raise ValueError(f"{name} is NaN in Nozzle.regenHeatTranferModel.heatTransferModel()")

                    # Check arrays
                    if isinstance(value, np.ndarray) and np.isnan(value).any():
                        print(f"{name} contains NaN (array)")
                        if context.debugMode:
                            breakpoint()
                        else:
                            raise ValueError(f"{name} is NaN in Nozzle.regenHeatTranferModel.heatTransferModel()")
                except:
                    pass  # Ignore variables that can't be NaN

        # Hot wall convergence
        if not runAdiabaticColdWall:

            # -- We don't know hot wall temperature, so converge to the correct hot wall temperature iteratively -- #

            def hotWallConvergenceLoops(throatRadiusOfCurvature):

                # Fluted Hot Wall Temperature Convergence
                if runFluted:

                    # The solve raises on a NaN wall temperature rather than letting one propagate
                    # a hundred stations downstream. Catching it here is what lets the local state
                    # be written out, since the solve sees only the station it was handed.
                    try:
                        solution = solveStationWallTemperature(
                            drivingTemperature         = drivingTemperature[i],
                            gasStaticTemperature       = nearWallTemperature[i],
                            gasMachNumber              = nearWallMachNumber[i],
                            gasGamma                   = exhaustGamma[i],
                            gasConstant                = exhaustGasConstant[i],
                            gasMolecularWeight         = exhaustMolecularWeight[i],
                            coolantTemperature         = flutedCoolantTemperature[i],
                            coolantThermalConductivity = flutedCoolantThermalConductivity[i],
                            coolantNusseltNumber       = flutedCoolantNusseltNumber[i],
                            coolantSpecificHeat        = flutedCoolantSpecificHeat[i],
                            coolantMassFlow            = mdot,
                            hydraulicDiameter          = flutedHydraulicDiameter[i],
                            coolantWettedArea          = gausFlutedSA[i]/2,
                            hotWallArea                = hotWallArea[i],
                            hotWallThickness           = hotWallThickness,
                            wallRadius                 = rHotWall3D[i],
                            pathLength                 = differentialPathLength[i],
                            conductivityInterpolator   = wallThermalConductivityInterpolator[i],
                            chamberPressure            = chamberPressure,
                            characteristicVelocity     = theoreticalCharVel,
                            throatDiameter             = throatDiameter,
                            throatRadiusOfCurvature    = throatRadiusOfCurvature,
                            throatArea                 = throatArea,
                            localArea                  = nozzleAreas[i],
                            filmMassFlux               = filmMassFlux[i],
                            blowingFactor              = blowingFactor,
                            wallEmissivity             = wallEmissivity,
                            gasEmissivity              = gasEmissivity[i],
                            tolerance                  = 0.01)
                    except ValueError as error:
                        debugFile = dumpDebugInfo(locals(), i, time.time() - start_time)
                        raise ValueError('{} Station {}, fluted channel.{}'.format(
                            error, i, ' Local state written to {}.'.format(debugFile)
                            if debugFile else '')) from error

                    flutedWallConductivity[i]                  = solution.wallConductivity
                    flutedCoolantConvectiveHeatTransferCoef[i] = solution.coolantConvectiveCoefficient
                    flutedExhaustConvectiveHeatTransferCoef[i] = solution.exhaustConvectiveCoefficient
                    flutedHeatTransfer[i]                      = solution.heatTransfer
                    flutedHotWallTemperature[i]                = solution.hotWallTemperature
                    flutedColdWallTemperature[i]               = solution.coldWallTemperature
                    flutedRadiativeHeatTransfer[i]             = solution.radiativeHeatTransfer
                    flutedBlowingReduction[i]                  = solution.blowingReduction

                    # The march runs from the coolant inlet toward the chamber, so the heat picked
                    # up here raises the coolant at the next station down the index. A single
                    # station has no next one, so it takes the rise itself.
                    if i > 0:
                        flutedCoolantTemperature[i-1] = flutedCoolantTemperature[i] + solution.coolantTemperatureRise
                    if solution.converged and iterationMode == 'single':
                        flutedCoolantTemperature[i] = flutedCoolantTemperature[i] + solution.coolantTemperatureRise

                    if not solution.converged:
                        raise ConvergenceFailureError(
                            message = 'Fluted hot wall temperature convergence failed at station '
                                      '{} after {} iterations'.format(i, solution.iterations),
                            context = {
                                'stationIndex': i,
                                'iterationCount': solution.iterations,
                                'residual': solution.residual,
                                'tolerance': 0.01,
                                'flutedHotWallTemperature': solution.hotWallTemperature,
                                'flutedColdWallTemperature': solution.coldWallTemperature,
                                'flutedHeatTransfer': solution.heatTransfer,
                                'regenSectionNearWallTemperature': nearWallTemperature[i],
                                'flutedCoolantTemperature': flutedCoolantTemperature[i]
                            },
                            iterations = solution.iterations,
                            tolerance = 0.01,
                            residual = solution.residual)

                # Circle Hot Wall Temperature Convergence
                if runCircle:

                    # The solve raises on a NaN wall temperature rather than letting one propagate
                    # a hundred stations downstream. Catching it here is what lets the local state
                    # be written out, since the solve sees only the station it was handed.
                    try:
                        solution = solveStationWallTemperature(
                            drivingTemperature         = drivingTemperature[i],
                            gasStaticTemperature       = nearWallTemperature[i],
                            gasMachNumber              = nearWallMachNumber[i],
                            gasGamma                   = exhaustGamma[i],
                            gasConstant                = exhaustGasConstant[i],
                            gasMolecularWeight         = exhaustMolecularWeight[i],
                            coolantTemperature         = circleCoolantTemperature[i],
                            coolantThermalConductivity = circleCoolantThermalConductivity[i],
                            coolantNusseltNumber       = circleCoolantNusseltNumber[i],
                            coolantSpecificHeat        = circleCoolantSpecificHeat[i],
                            coolantMassFlow            = mdot,
                            hydraulicDiameter          = circleHydraulicDiameter[i],
                            coolantWettedArea          = circleSA[i]/2,
                            hotWallArea                = hotWallArea[i],
                            hotWallThickness           = hotWallThickness,
                            wallRadius                 = rHotWall3D[i],
                            pathLength                 = differentialPathLength[i],
                            conductivityInterpolator   = wallThermalConductivityInterpolator[i],
                            chamberPressure            = chamberPressure,
                            characteristicVelocity     = theoreticalCharVel,
                            throatDiameter             = throatDiameter,
                            throatRadiusOfCurvature    = throatRadiusOfCurvature,
                            throatArea                 = throatArea,
                            localArea                  = nozzleAreas[i],
                            filmMassFlux               = filmMassFlux[i],
                            blowingFactor              = blowingFactor,
                            wallEmissivity             = wallEmissivity,
                            gasEmissivity              = gasEmissivity[i],
                            tolerance                  = 0.01)
                    except ValueError as error:
                        debugFile = dumpDebugInfo(locals(), i, time.time() - start_time)
                        raise ValueError('{} Station {}, circle channel.{}'.format(
                            error, i, ' Local state written to {}.'.format(debugFile)
                            if debugFile else '')) from error

                    circleWallConductivity[i]                  = solution.wallConductivity
                    circleCoolantConvectiveHeatTransferCoef[i] = solution.coolantConvectiveCoefficient
                    circleExhaustConvectiveHeatTransferCoef[i] = solution.exhaustConvectiveCoefficient
                    circleHeatTransfer[i]                      = solution.heatTransfer
                    circleHotWallTemperature[i]                = solution.hotWallTemperature
                    circleColdWallTemperature[i]               = solution.coldWallTemperature
                    circleRadiativeHeatTransfer[i]             = solution.radiativeHeatTransfer
                    circleBlowingReduction[i]                  = solution.blowingReduction

                    # The march runs from the coolant inlet toward the chamber, so the heat picked
                    # up here raises the coolant at the next station down the index. A single
                    # station has no next one, so it takes the rise itself.
                    if i > 0:
                        circleCoolantTemperature[i-1] = circleCoolantTemperature[i] + solution.coolantTemperatureRise
                    if solution.converged and iterationMode == 'single':
                        circleCoolantTemperature[i] = circleCoolantTemperature[i] + solution.coolantTemperatureRise

                    if not solution.converged:
                        raise ConvergenceFailureError(
                            message = 'Circle hot wall temperature convergence failed at station '
                                      '{} after {} iterations'.format(i, solution.iterations),
                            context = {
                                'stationIndex': i,
                                'iterationCount': solution.iterations,
                                'residual': solution.residual,
                                'tolerance': 0.01,
                                'circleHotWallTemperature': solution.hotWallTemperature,
                                'circleHeatTransfer': solution.heatTransfer,
                                'regenSectionNearWallTemperature': nearWallTemperature[i],
                                'circleCoolantTemperature': circleCoolantTemperature[i]
                            },
                            iterations = solution.iterations,
                            tolerance = 0.01,
                            residual = solution.residual)

            hotWallConvergenceLoops(throatRadiusOfCurvature)

        # Adiabatic cold wall
        else:

            if runFluted:

                flutedAdiabaticConvectiveHeatTransferCoef[i] = flutedCoolantThermalConductivity[i] * flutedCoolantNusseltNumber[i] / \
                                                         flutedHydraulicDiameter[i]
                adiabaticConvectiveResistance = 1 / (flutedAdiabaticConvectiveHeatTransferCoef[i] * gausFlutedCSA[i])

                flutedAdiabaticHeatTransfer[i] = (constantColdWallTemperature - flutedCoolantTemperature[i]) / (adiabaticConvectiveResistance)

                if i > 0:
                    flutedCoolantTemperature[i-1] = flutedCoolantTemperature[i] + (flutedAdiabaticHeatTransfer[i] / (mdot * flutedCoolantSpecificHeat[i]))
                if iterationMode == 'single':
                    flutedCoolantTemperature[i] = flutedCoolantTemperature[i] + (flutedAdiabaticHeatTransfer[i] / (mdot * flutedCoolantSpecificHeat[i]))

            if runCircle:

                circleAdiabaticConvectiveHeatTransferCoef[i] = circleCoolantThermalConductivity[i] * circleCoolantNusseltNumber[i] / \
                                                         circleHydraulicDiameter[i]
                adiabaticConvectiveResistance = 1 / (circleAdiabaticConvectiveHeatTransferCoef[i] * circleCSA[i])

                circleAdiabaticHeatTransfer[i] = (constantColdWallTemperature - circleCoolantTemperature[i]) / (adiabaticConvectiveResistance)

                if i > 0:
                    circleCoolantTemperature[i-1] = circleCoolantTemperature[i] + (circleAdiabaticHeatTransfer[i] / (mdot * circleCoolantSpecificHeat[i]))
                if iterationMode == 'single':
                    circleCoolantTemperature[i] = circleCoolantTemperature[i] + (circleAdiabaticHeatTransfer[i] / (mdot * circleCoolantSpecificHeat[i]))

    if iterationMode == 'loop':

        # -- Loop -- #

        # Loop backwards in X corresponding to regen inlet --> regen outlet (nozzle outlet --> nozzle inlet)
        for i in tqdm(range(numCrossSections-1, 0, -1), desc="Running Regen Jacket Heat Transfer Model", colour="#ABD038"):

            heatTransferModel(i)

        # Calculate final point
        i = 0
        heatTransferModel(i)

    if iterationMode == 'single':

        heatTransferModel(0)

    # -- Finish -- #

    # Collect outputs
    if not runAdiabaticColdWall:
        if runFluted:
            flutedHeatTransferOutputs = {
                'coolantPressure':     flutedCoolantPressure,
                'coolantTemperature':  flutedCoolantTemperature,
                'hotWallTemperature':  flutedHotWallTemperature,
                'coldWallTemperature': flutedColdWallTemperature
            }
            flutedPlotOutputs = {
                'xHotWall3D'                        : xHotWall3D,
                'rHotWall3D'                        : rHotWall3D,
                'temperature'                       : flutedCoolantTemperature,
                'pressure'                          : flutedCoolantPressure,
                'wallTemperature'                   : flutedHotWallTemperature,
                'velocity'                          : flutedCoolantVelocity,
                'machNumber'                        : flutedCoolantMachNumber,
                'heatTransfer'                      : flutedHeatTransfer,
                'density'                           : flutedCoolantDensity,
                'viscosity'                         : flutedCoolantViscosity,
                'specificHeat'                      : flutedCoolantSpecificHeat,
                'nusseltNumber'                     : flutedCoolantNusseltNumber,
                'exhaustConvectiveHeatTransferCoef' : flutedExhaustConvectiveHeatTransferCoef,
                'coolantConvectiveHeatTransferCoef' : flutedCoolantConvectiveHeatTransferCoef,
                'reynoldsNumber'                    : flutedCoolantReynoldsNumber,
                'radiativeHeatTransfer'             : flutedRadiativeHeatTransfer,
                'drivingTemperature'                : drivingTemperature
            }
        else:
            flutedHeatTransferOutputs = {}
            flutedPlotOutputs = {}
        if runCircle:
            circleHeatTransferOutputs = {
                'coolantPressure':     circleCoolantPressure,
                'coolantTemperature':  circleCoolantTemperature,
                'hotWallTemperature':  circleHotWallTemperature,
                'coldWallTemperature': circleColdWallTemperature
            }
            circlePlotOutputs = {
                'xHotWall3D'                        : xHotWall3D,
                'rHotWall3D'                        : rHotWall3D,
                'temperature'                       : circleCoolantTemperature,
                'pressure'                          : circleCoolantPressure,
                'wallTemperature'                   : circleHotWallTemperature,
                'velocity'                          : circleCoolantVelocity,
                'machNumber'                        : circleCoolantMachNumber,
                'heatTransfer'                      : circleHeatTransfer,
                'density'                           : circleCoolantDensity,
                'viscosity'                         : circleCoolantViscosity,
                'specificHeat'                      : circleCoolantSpecificHeat,
                'nusseltNumber'                     : circleCoolantNusseltNumber,
                'exhaustConvectiveHeatTransferCoef' : circleExhaustConvectiveHeatTransferCoef,
                'coolantConvectiveHeatTransferCoef' : circleCoolantConvectiveHeatTransferCoef,
                'reynoldsNumber'                    : circleCoolantReynoldsNumber,
                'radiativeHeatTransfer'             : circleRadiativeHeatTransfer,
                'drivingTemperature'                : drivingTemperature
            }
        else:
            circleHeatTransferOutputs = {}
            circlePlotOutputs = {}

    else:
        if runFluted:
            flutedHeatTransferOutputs = {
                'coolantPressure':     flutedCoolantPressure,
                'coolantTemperature':  flutedCoolantTemperature,
                'hotWallTemperature':  flutedHotWallTemperature,
                'coldWallTemperature': flutedColdWallTemperature
            }
            flutedPlotOutputs = {
                'xHotWall3D'                          : xHotWall3D,
                'rHotWall3D'                          : rHotWall3D,
                'temperature'                         : flutedCoolantTemperature,
                'pressure'                            : flutedCoolantPressure,
                'specificHeat'                        : flutedCoolantSpecificHeat,
                'adiabaticConvectiveHeatTransferCoef' : flutedAdiabaticConvectiveHeatTransferCoef
            }
        else:
            flutedHeatTransferOutputs = {}
            flutedPlotOutputs = {}
        if runCircle:
            circleHeatTransferOutputs = {
                'coolantPressure':     circleCoolantPressure,
                'coolantTemperature':  circleCoolantTemperature,
                'hotWallTemperature':  circleHotWallTemperature,
                'coldWallTemperature': circleColdWallTemperature
            }
            circlePlotOutputs = {
                'xHotWall3D'                          : xHotWall3D,
                'rHotWall3D'                          : rHotWall3D,
                'temperature'                         : circleCoolantTemperature,
                'pressure'                            : circleCoolantPressure,
                'specificHeat'                        : circleCoolantSpecificHeat,
                'adiabaticConvectiveHeatTransferCoef' : circleAdiabaticConvectiveHeatTransferCoef
            }
        else:
            circleHeatTransferOutputs = {}
            circlePlotOutputs = {}

    # Plots
    if plots and context.plotsAdv == 'on' and _plotlyGate('the interactive heat transfer view'):
        if not runAdiabaticColdWall:
            regenHeatTransferModelPlots(context, coolant=coolant, nChannel=nChannel,\
                                             flutedResults=flutedPlotOutputs, circleResults=circlePlotOutputs, titleFlare=titleFlare,
                                             xReference=xReference, rReference=rReference)
        else:
            regenHeatTransferModelPlots(context, coolant=coolant, nChannel=nChannel, adiabatic=True,\
                                             flutedResults=flutedPlotOutputs, circleResults=circlePlotOutputs, titleFlare=titleFlare,
                                             xReference=xReference, rReference=rReference)

    # Return
    if returnDict:
        return flutedHeatTransferOutputs, flutedPlotOutputs, \
                circleHeatTransferOutputs, circlePlotOutputs

def regenHeatTransferModelPlots(context, coolant, nChannel, adiabatic = False, \
                                 flutedResults: dict = None, circleResults: dict = None,
                                 titleFlare: str = '', xReference = [], rReference = []):

    # Helper function to add a trace
    def add_trace(row, col, x, y, name, color=None, showlegend=False, dash='solid', secondary_y=False, legendgroup=None, **kwargs):
        '''
        Adds a trace to the specified subplot with optional legend grouping.

        Args:
            row (int): Row number of the subplot.
            col (int): Column number of the subplot.
            x (array-like): x-axis data.
            y (array-like): y-axis data.
            name (str): Name of the trace.
            color (str, optional): Color of the trace. Defaults to None.
            showlegend (bool, optional): Whether to show the legend. Defaults to False.
            dash (str, optional): Line dash style. Defaults to 'solid'.
            secondary_y (bool, optional): Whether to plot on secondary y-axis. Defaults to False.
            legendgroup (str, optional): Legend group for the trace. Defaults to None.
            **kwargs: Additional keyword arguments for go.Scatter.
        '''
        fig.add_trace(
            go.Scatter(x=x, y=y, name=name, line=dict(color=color, dash=dash), showlegend=showlegend, legendgroup=legendgroup, **kwargs),
            row=row, col=col, secondary_y=secondary_y
            )

    maxTemperatureCopper = 800 # Kelvin

    if not adiabatic:

        # -- Local Scope the Inputs Dictionary -- #

        # Fluted
        if flutedResults is not None:
            if len(flutedResults) != 0:
                runFluted                               = True
                xHotWall3D                              = flutedResults["xHotWall3D"]
                rHotWall3D                              = flutedResults["rHotWall3D"]
                flutedCoolantTemperature                = flutedResults["temperature"]
                flutedCoolantPressure                   = flutedResults["pressure"]
                flutedHotWallTemperature                = flutedResults["wallTemperature"]
                flutedCoolantVelocity                   = flutedResults["velocity"]
                flutedCoolantMachNumber                 = flutedResults["machNumber"]
                flutedHeatTransfer                      = flutedResults["heatTransfer"]
                flutedCoolantDensity                    = flutedResults["density"]
                flutedCoolantViscosity                  = flutedResults["viscosity"]
                flutedCoolantSpecificHeat               = flutedResults["specificHeat"]
                flutedCoolantNusseltNumber              = flutedResults["nusseltNumber"]
                flutedExhaustConvectiveHeatTransferCoef = flutedResults["exhaustConvectiveHeatTransferCoef"]
                flutedCoolantConvectiveHeatTransferCoef = flutedResults["coolantConvectiveHeatTransferCoef"]
                flutedCoolantReynoldsNumber             = flutedResults["reynoldsNumber"]
                flutedRadiativeHeatTransfer             = flutedResults["radiativeHeatTransfer"]
                flutedDrivingTemperature                = flutedResults["drivingTemperature"]
            else:
                runFluted = False
        else:
            runFluted = False
        # Circle
        if circleResults is not None:
            if len(circleResults) != 0:
                runCircle                               = True
                xHotWall3D                              = circleResults["xHotWall3D"]
                rHotWall3D                              = circleResults["rHotWall3D"]
                circleCoolantTemperature                = circleResults["temperature"]
                circleCoolantPressure                   = circleResults["pressure"]
                circleHotWallTemperature                = circleResults["wallTemperature"]
                circleCoolantVelocity                   = circleResults["velocity"]
                circleCoolantMachNumber                 = circleResults["machNumber"]
                circleHeatTransfer                      = circleResults["heatTransfer"]
                circleCoolantDensity                    = circleResults["density"]
                circleCoolantViscosity                  = circleResults["viscosity"]
                circleCoolantSpecificHeat               = circleResults["specificHeat"]
                circleCoolantNusseltNumber              = circleResults["nusseltNumber"]
                circleExhaustConvectiveHeatTransferCoef = circleResults["exhaustConvectiveHeatTransferCoef"]
                circleCoolantConvectiveHeatTransferCoef = circleResults["coolantConvectiveHeatTransferCoef"]
                circleCoolantReynoldsNumber             = circleResults["reynoldsNumber"]
                circleRadiativeHeatTransfer             = circleResults["radiativeHeatTransfer"]
                circleDrivingTemperature                = circleResults["drivingTemperature"]
            else:
                runCircle = False
        else:
            runCircle = False

        # -- Process Results -- #

        if runFluted:

            flutedFinalPressure     = flutedCoolantPressure[0]
            flutedCoolantInitialPressure = flutedCoolantPressure[-1]
            flutedTotalPressureDrop = flutedCoolantInitialPressure - flutedFinalPressure

            print(f'Total fluted pressure drop: {flutedTotalPressureDrop/1e6:.4f}(MPa) | Exit Pressure: {flutedFinalPressure/1e6:.4f}(MPa)')

            # -- Store supercritical transition temperature for plotting -- #
            flutedCoolantInitialTemperature = flutedCoolantTemperature[-1]
            flutedCoolantCriticalTemperature = fluidProps(coolant, 'TP', 'TCRIT', flutedCoolantInitialTemperature, flutedCoolantInitialPressure)
            flutedSuperCriticalRange         = flutedCoolantTemperature > flutedCoolantCriticalTemperature

            flutedCoolantSubcriticalTemperature   = flutedCoolantTemperature.copy()
            flutedCoolantSupercriticalTemperature = flutedCoolantTemperature.copy()

            flutedCoolantSubcriticalTemperature[flutedSuperCriticalRange]    = 'NaN'
            flutedCoolantSupercriticalTemperature[~flutedSuperCriticalRange] = 'NaN'

        elif runCircle:

            circleFinalPressure     = circleCoolantPressure[0]
            circleCoolantInitialPressure = circleCoolantPressure[-1]
            circleTotalPressureDrop = circleCoolantInitialPressure - circleFinalPressure

            print(f'Total circle pressure drop: {circleTotalPressureDrop/1e6:.4f}(MPa) | Exit Pressure: {circleFinalPressure/1e6:.4f}(MPa)')

            # -- Store supercritical transition temperature for plotting -- #
            circleCoolantInitialTemperature = circleCoolantTemperature[-1]
            circleCoolantCriticalTemperature = fluidProps(coolant, 'TP', 'TCRIT', circleCoolantInitialTemperature, circleCoolantInitialPressure)
            circleSuperCriticalRange         = circleCoolantTemperature > circleCoolantCriticalTemperature

            circleCoolantSubcriticalTemperature   = circleCoolantTemperature.copy()
            circleCoolantSupercriticalTemperature = circleCoolantTemperature.copy()

            circleCoolantSubcriticalTemperature[circleSuperCriticalRange]    = 'NaN'
            circleCoolantSupercriticalTemperature[~circleSuperCriticalRange] = 'NaN'

        # -- Plotly implementation -- #

        # Instantiate Figure
        fig = make_subplots(rows=4, cols=3, subplot_titles=(
            'Pressure', 'Temperature', 'Wall Temperature',
            'Streamwise Velocity', 'Mach Number', 'Heat Transfer',
            'Density', 'Viscosity', 'Heat Capacity',
            'Nusselt Number', 'Heat Transfer Coef', 'Reynolds Number'),
        horizontal_spacing = 0.05,   #setting spaceing between plots
        vertical_spacing = 0.05,
        specs=[[{"secondary_y": True}, {"secondary_y": True}, {"secondary_y": True}],
            [{"secondary_y": True}, {"secondary_y": True}, {"secondary_y": True}],
            [{"secondary_y": True}, {"secondary_y": True}, {"secondary_y": True}],
            [{"secondary_y": True}, {"secondary_y": True}, {"secondary_y": True}]
            ]
        )

        # Legend
        colors = {
                'Fluted': 'cyan',
                'Supercritical': 'cyan',
                'Subcritical': 'blue',
                'Circular': 'magenta',
                'GRCop Melting Temp': 'red',
                'Nozzle': 'grey'
        }
        for name, color in colors.items():
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=color), name=name, showlegend=True))

        # Nozzle Contours
        for i in [1,2,3]:
            for j in [1,2,3,4]:
                if len(xReference)==0 or len(rReference)==0:
                    add_trace(j, i, xHotWall3D, rHotWall3D, 'Nozzle Radius', color=colors['Nozzle'], dash='dot', showlegend=False, secondary_y=True)
                else:
                    add_trace(j, i, xReference, rReference, 'Nozzle Radius', color=colors['Nozzle'], dash='dot', showlegend=False, secondary_y=True)

        # -- Titles -- #

        # Coolant Pressure
        fig.update_yaxes(title_text=r'$\text {Pressure [MPa]}$', row=1, col=1, secondary_y=False, gridcolor='#4a4a4a')
        # Coolant Temperature
        fig.update_yaxes(title_text=r'$\text {Temperature [K]}$', row=1, col=2, secondary_y=False, gridcolor='#4a4a4a')
        # Wall Temperature
        if len(xReference)==0:
            add_trace(1, 3, xReference, maxTemperatureCopper * np.ones(len(xReference)), 'GRCop Melting Temp', colors['GRCop Melting Temp'], dash='solid')
        else:
            add_trace(1, 3, xHotWall3D, maxTemperatureCopper * np.ones(len(xHotWall3D)), 'GRCop Melting Temp', colors['GRCop Melting Temp'], dash='solid')
        fig.update_yaxes(title_text=r'$\text {Temperature [K]}$', row=1, col=3, secondary_y=False, gridcolor='#4a4a4a')
        # Velocity
        fig.update_yaxes(title_text=r'$\text {Velocity [m/s]}$', row=2, col=1, secondary_y=False, gridcolor='#4a4a4a')
        # Mach
        fig.update_yaxes(title_text=r'$\text {Mach Number [-]}$', row=2, col=2, secondary_y=False, gridcolor='#4a4a4a')
        # Heat Transfer
        fig.update_yaxes(title_text=r'$\text {Heat Transfer [W]}$', row=2, col=3, secondary_y=False, gridcolor='#4a4a4a')
        # Density
        fig.update_yaxes(title_text=r'$\rho \text{ [kg/m}^{3} \text{]}$', row=3, col=1, secondary_y=False, gridcolor='#4a4a4a')
        # Viscosity
        fig.update_yaxes(title_text=r'$\mu \text{ [Pa*s]}$', row=3, col=2, secondary_y=False, gridcolor='#4a4a4a')
        # Specific Heat
        fig.update_yaxes(title_text=r'$\text {C_P [J/kg*K]}$', row=3, col=3, secondary_y=False, gridcolor='#4a4a4a')
        # Nusselt
        fig.update_yaxes(title_text=r'$\text {Nu [-]}$', row=4, col=1, secondary_y=False, gridcolor='#4a4a4a')
        # Heat Transfer Coef
        fig.update_yaxes(title_text=r'$\text{ h [W/(m}^{2}\text{*K)]}$', row=4, col=2, secondary_y=False, gridcolor='#4a4a4a')
        # Reynolds
        fig.update_yaxes(title_text=r'$\text {Re [-]}$', row=4, col=3, secondary_y=False, gridcolor='#4a4a4a')

        # -- Data -- #

        if runFluted:
            # Coolant Pressure
            add_trace(1, 1, xHotWall3D, flutedCoolantPressure/1e6, 'Fluted', colors['Fluted'])
            # Coolant Temperature
            add_trace(1, 2, xHotWall3D, flutedCoolantSupercriticalTemperature, 'Supercritical', colors['Supercritical'])
            add_trace(1, 2, xHotWall3D, flutedCoolantSubcriticalTemperature, 'Subcritical', colors['Subcritical'], mode='markers')
            # Wall Temperature
            add_trace(1, 3, xHotWall3D, flutedHotWallTemperature, 'Fluted', colors['Fluted'])
            # Velocity
            add_trace(2, 1, xHotWall3D, flutedCoolantVelocity, 'Fluted', colors['Fluted'])
            # Mach
            add_trace(2, 2, xHotWall3D, flutedCoolantMachNumber, 'Fluted', colors['Fluted'])
            # Heat Transfer
            add_trace(2, 3, xHotWall3D, flutedHeatTransfer, 'Fluted', colors['Fluted'])
            # Density
            add_trace(3, 1, xHotWall3D, flutedCoolantDensity, 'Fluted', colors['Fluted'])
            # Viscosity
            add_trace(3, 2, xHotWall3D, flutedCoolantViscosity, 'Fluted', colors['Fluted'])
            # Specific Heat
            add_trace(3, 3, xHotWall3D, flutedCoolantSpecificHeat, 'Fluted', colors['Fluted'])
            # Nusselt
            add_trace(4, 1, xHotWall3D, flutedCoolantNusseltNumber, 'Fluted', colors['Fluted'])
            # Heat Transfer Coef
            add_trace(4, 2, xHotWall3D, flutedCoolantConvectiveHeatTransferCoef, 'Coolant - Fluted', colors['Fluted'])
            add_trace(4, 2, xHotWall3D, flutedExhaustConvectiveHeatTransferCoef, 'Exhaust - Fluted', colors['Fluted'], dash='dot')
            # Reynolds
            add_trace(4, 3, xHotWall3D, flutedCoolantReynoldsNumber, 'Fluted', colors['Fluted'])
            # The gas-side driving temperature belongs beside the wall it drives, and the
            # radiative share beside the total it is part of. Neither earns a panel of its own.
            add_trace(1, 3, xHotWall3D, flutedDrivingTemperature, 'Driving gas - Fluted',
                      colors['Fluted'], dash = 'dash')
            if np.any(flutedRadiativeHeatTransfer):
                add_trace(2, 3, xHotWall3D, flutedRadiativeHeatTransfer, 'Radiative - Fluted',
                          colors['Fluted'], dash = 'dot')

        if runCircle:
            # Coolant Pressure
            add_trace(1, 1, xHotWall3D, circleCoolantPressure/1e6, 'Circular', colors['Circular'])
            # Coolant Temperature
            add_trace(1, 2, xHotWall3D, circleCoolantTemperature, 'Circular', colors['Circular'])
            # Wall Temperature
            add_trace(1, 3, xHotWall3D, circleHotWallTemperature, 'Circular', colors['Circular'])
            # Velocity
            add_trace(2, 1, xHotWall3D, circleCoolantVelocity, 'Circular', colors['Circular'])
            # Mach
            add_trace(2, 2, xHotWall3D, circleCoolantMachNumber, 'Circular', colors['Circular'])
            # Heat Transfer
            add_trace(2, 3, xHotWall3D, circleHeatTransfer, 'Circular', colors['Circular'])
            # Density
            add_trace(3, 1, xHotWall3D, circleCoolantDensity, 'Circular', colors['Circular'])
            # Viscosity
            add_trace(3, 2, xHotWall3D, circleCoolantViscosity, 'Circular', colors['Circular'])
            # Specific Heat
            add_trace(3, 3, xHotWall3D, circleCoolantSpecificHeat, 'Circular', colors['Circular'])
            # Nusselt
            add_trace(4, 1, xHotWall3D, circleCoolantNusseltNumber, 'Circular', colors['Circular'])
            # Heat Transfer Coef
            add_trace(4, 2, xHotWall3D, circleCoolantConvectiveHeatTransferCoef, 'Coolant - Circular', colors['Circular'])
            add_trace(4, 2, xHotWall3D, circleExhaustConvectiveHeatTransferCoef, 'Exhaust - Circular', colors['Circular'], dash='dot')
            # Reynolds
            add_trace(4, 3, xHotWall3D, circleCoolantReynoldsNumber, 'Circular', colors['Circular'])
            add_trace(1, 3, xHotWall3D, circleDrivingTemperature, 'Driving gas - Circular',
                      colors['Circular'], dash = 'dash')
            if np.any(circleRadiativeHeatTransfer):
                add_trace(2, 3, xHotWall3D, circleRadiativeHeatTransfer, 'Radiative - Circular',
                          colors['Circular'], dash = 'dot')

        # Update layout for all subplots
        for i in range(1, 13):

            row = (i - 1) // 3 + 1
            col = (i - 1) % 3 + 1

            fig.update_xaxes(title_text=r'$\text {Nozzle Axis [m]}$' if row == 4 else '', row=row, col=col, gridcolor='#4a4a4a', tickfont=dict(color='white' if row == 4 else 'rgba(0,0,0,0)'))

            # Add secondary y-axis for Nozzle Radius only on rightmost plots - OUTSIDE the loop
            fig.update_yaxes(title_text=r'$\text {Nozzle Radius [m]}$' if col == 3 else '', row = row, col = col, secondary_y=True, title_font=dict(color=colors['Nozzle'] if col == 3 else 'rgba(0,0,0,0)'), tickfont=dict(color=colors['Nozzle'] if col == 3 else 'rgba(0,0,0,0)'), showgrid=False)

        # Update overall layout
        fig.update_layout(
            #height=1200,
            #width=1800,
            title_text=f'Regen Channel Properties: {int(nChannel)} Channels{titleFlare}',
            title_x=0.5,  # Center the main title
            autosize=True,
            title_font=dict(size=24),
            plot_bgcolor='black',
            paper_bgcolor='black',
            font=dict(color='white', family = "Computer Modern"),
            legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(size=12))
        )

        if context.export == 'on':

            print(f'Saving Heat Transfer Outputs to .html')

            if context.plotsDocs == 'on':
                # Enlarge for the save at the aspect the figure was drawn at.
                figure = plt.gcf()
                figure.set_size_inches(16, 10)
                figure.tight_layout()

                # Save the final heat transfer figure to the data folder
                plt.savefig(context.dataFolder + '\\heatTransferModelOutput.png', bbox_inches = 'tight')

            plot(fig, filename = context.dataFolder + '\\heatTransferModelOutput.html', auto_open = not headlessPlots())

        else:

            if context.plotsDocs == 'on':
                plt.show(block = False)

            showFigure(fig)

    if adiabatic:

        # -- Local Scope the Inputs Dictionary -- #
        # Fluted
        if flutedResults is not None:
            if len(flutedResults) != 0:
                runFluted                                 = True
                xHotWall3D                                = flutedResults["xHotWall3D"]
                rHotWall3D                                = flutedResults["rHotWall3D"]
                flutedCoolantTemperature                  = flutedResults["temperature"]
                flutedCoolantPressure                     = flutedResults["pressure"]
                flutedCoolantSpecificHeat                 = flutedResults["specificHeat"]
                flutedAdiabaticConvectiveHeatTransferCoef = flutedResults["adiabaticConvectiveHeatTransferCoef"]
            else:
                runFluted = False
        else:
            runFluted = False
        # Circle
        if circleResults is not None:
            if len(circleResults) != 0:
                runCircle                                 = True
                xHotWall3D                                = circleResults["xHotWall3D"]
                rHotWall3D                                = circleResults["rHotWall3D"]
                circleCoolantTemperature                  = circleResults["temperature"]
                circleCoolantPressure                     = circleResults["pressure"]
                circleCoolantSpecificHeat                 = circleResults["specificHeat"]
                circleAdiabaticConvectiveHeatTransferCoef = circleResults["adiabaticConvectiveHeatTransferCoef"]
            else:
                runCircle = False
        else:
            runCircle = False

        # -- Process Results -- #

        if runFluted:

            flutedFinalPressure     = flutedCoolantPressure[0]
            flutedCoolantInitialPressure = flutedCoolantPressure[-1]
            flutedTotalPressureDrop = flutedCoolantInitialPressure - flutedFinalPressure

            print(f'Total fluted pressure drop: {flutedTotalPressureDrop/1e6:.4f}(MPa) | Exit Pressure: {flutedFinalPressure/1e6:.4f}(MPa)')

            # -- Store supercritical transition temperature for plotting -- #
            flutedCoolantInitialTemperature = flutedCoolantTemperature[-1]
            flutedCoolantCriticalTemperature = fluidProps(coolant, 'TP', 'TCRIT', flutedCoolantInitialTemperature, flutedCoolantInitialPressure)
            flutedSuperCriticalRange         = flutedCoolantTemperature > flutedCoolantCriticalTemperature

            flutedCoolantSubcriticalTemperature   = flutedCoolantTemperature.copy()
            flutedCoolantSupercriticalTemperature = flutedCoolantTemperature.copy()

            flutedCoolantSubcriticalTemperature[flutedSuperCriticalRange]    = 'NaN'
            flutedCoolantSupercriticalTemperature[~flutedSuperCriticalRange] = 'NaN'

        elif runCircle:

            circleFinalPressure     = circleCoolantPressure[0]
            circleCoolantInitialPressure = circleCoolantPressure[-1]
            circleTotalPressureDrop = circleCoolantInitialPressure - circleFinalPressure

            print(f'Total circle pressure drop: {circleTotalPressureDrop/1e6:.4f}(MPa) | Exit Pressure: {circleFinalPressure/1e6:.4f}(MPa)')

            # -- Store supercritical transition temperature for plotting -- #
            circleCoolantInitialTemperature = circleCoolantTemperature[-1]
            circleCoolantCriticalTemperature = fluidProps(coolant, 'TP', 'TCRIT', circleCoolantInitialTemperature, circleCoolantInitialPressure)
            circleSuperCriticalRange         = circleCoolantTemperature > circleCoolantCriticalTemperature

            circleCoolantSubcriticalTemperature   = circleCoolantTemperature.copy()
            circleCoolantSupercriticalTemperature = circleCoolantTemperature.copy()

            circleCoolantSubcriticalTemperature[circleSuperCriticalRange]    = 'NaN'
            circleCoolantSupercriticalTemperature[~circleSuperCriticalRange] = 'NaN'

        # -- Plotly implementation -- #

        # Instantiate Figure
        fig = make_subplots(rows=2, cols=2, subplot_titles=(
            'Pressure', 'Temperature',
            'Heat Capacity', 'Heat Transfer Coef'),
        horizontal_spacing = 0.05,   #setting spaceing between plots
        vertical_spacing = 0.05,
        specs=[[{"secondary_y": True}, {"secondary_y": True}],
            [{"secondary_y": True}, {"secondary_y": True}],
            ]
        )

        # Legend
        colors = {
                'Fluted': 'cyan',
                'Supercritical': 'cyan',
                'Subcritical': 'blue',
                'Circular': 'magenta',
                'Nozzle': 'grey'
        }
        for name, color in colors.items():
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=color), name=name, showlegend=True))

        # Nozzle Contours
        for i in [1,2]:
            for j in [1,2]:
                add_trace(j, i, xHotWall3D, rHotWall3D, 'Nozzle Radius', color=colors['Nozzle'], dash='dot', showlegend=False, secondary_y=True)

        # -- Titles -- #

        # Coolant Pressure
        fig.update_yaxes(title_text=r'$\text {Pressure [MPa]}$', row=1, col=1, secondary_y=False, gridcolor='#4a4a4a')
        # Coolant Temperature
        fig.update_yaxes(title_text=r'$\text {Temperature [K]}$', row=1, col=2, secondary_y=False, gridcolor='#4a4a4a')
        # Specific Heat
        fig.update_yaxes(title_text=r'$\text {C_P [J/kg*K]}$', row=2, col=1, secondary_y=False, gridcolor='#4a4a4a')
        # Heat Transfer Coef
        fig.update_yaxes(title_text=r'$\text{ h [W/(m}^{2}\text{*K)]}$', row=2, col=2, secondary_y=False, gridcolor='#4a4a4a')

        # -- Data -- #

        if runFluted:
            # Coolant Pressure
            add_trace(1, 1, xHotWall3D, flutedCoolantPressure/1e6, 'Fluted', colors['Fluted'])
            # Coolant Temperature
            add_trace(1, 2, xHotWall3D, flutedCoolantSupercriticalTemperature, 'Supercritical', colors['Supercritical'])
            add_trace(1, 2, xHotWall3D, flutedCoolantSubcriticalTemperature, 'Subcritical', colors['Subcritical'], mode='markers')
            # Specific Heat
            add_trace(2, 1, xHotWall3D, flutedCoolantSpecificHeat, 'Fluted', colors['Fluted'])
            # Heat Transfer Coef
            add_trace(2, 2, xHotWall3D, flutedAdiabaticConvectiveHeatTransferCoef, 'Fluted', colors['Fluted'])

        if runCircle:
            # Coolant Pressure
            add_trace(1, 1, xHotWall3D, circleCoolantPressure/1e6, 'Circular', colors['Circular'])
            # Coolant Temperature
            add_trace(1, 2, xHotWall3D, circleCoolantTemperature, 'Circular', colors['Circular'])
            # Specific Heat
            add_trace(2, 1, xHotWall3D, circleCoolantSpecificHeat, 'Circular', colors['Circular'])
            # Heat Transfer Coef
            add_trace(2, 2, xHotWall3D, circleAdiabaticConvectiveHeatTransferCoef, 'Circular', colors['Circular'])

        # Update layout for all subplots
        for i in [1,2]:

            fig.update_xaxes(title_text=r'$\text {Nozzle Axis [m]}$', row=2, col=i, gridcolor='#4a4a4a', tickfont=dict(color='white'))
            fig.update_xaxes(title_text= '',                          row=1, col=i, gridcolor='#4a4a4a', tickfont=dict(color='rgba(0,0,0,0)'))

            # Add secondary y-axis for Nozzle Radius only on rightmost plots - OUTSIDE the loop
            fig.update_yaxes(title_text=r'$\text {Nozzle Radius [m]}$', row = i, col = 2, secondary_y=True, title_font=dict(color=colors['Nozzle']), tickfont=dict(color=colors['Nozzle']), showgrid=False)
            fig.update_yaxes(title_text= '',                            row = i, col = 1, secondary_y=True, title_font=dict(color=colors['Nozzle']), tickfont=dict(color='rgba(0,0,0,0)'), showgrid=False)

        # Update overall layout
        fig.update_layout(
            #height=1200,
            #width=1800,
            title_text=f'Regen Channel Properties: {int(nChannel)} Channels{titleFlare}',
            title_x=0.5,  # Center the main title
            autosize=True,
            title_font=dict(size=24),
            plot_bgcolor='black',
            paper_bgcolor='black',
            font=dict(color='white', family = "Computer Modern"),
            legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(size=12))
        )

        if context.export == 'on':

            print(f'Saving Heat Transfer Outputs to .html')

            if context.plotsDocs == 'on':
                # Enlarge for the save at the aspect the figure was drawn at.
                figure = plt.gcf()
                figure.set_size_inches(16, 10)
                figure.tight_layout()

                # Save the final heat transfer figure to the data folder
                plt.savefig(context.dataFolder + '\\heatTransferModelOutput.png', bbox_inches = 'tight')

            plot(fig, filename = context.dataFolder + '\\heatTransferModelOutput.html', auto_open = not headlessPlots())

        else:

            if context.plotsDocs == 'on':
                plt.show(block = False)

            showFigure(fig)
