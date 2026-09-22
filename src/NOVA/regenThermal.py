
# -- NOVA: Regenerative Cooling Heat Transfer -- #

'''

The thermal model of a regeneratively cooled jacket.

A cooling channel is solved one station at a time, marching from the coolant inlet. At each
station the hot wall temperature is unknown, so it is converged: a guess sets the gas-side
coefficient, the coefficient sets the heat flux, the flux sets a new wall temperature, and the
loop repeats until the two agree. The coolant state is then advanced to the next station
through the heat it absorbed and the pressure it lost.

The model takes its geometry and its gas state through one dictionary and reads nothing off a
Nozzle, so it can be driven directly. What it does need from the run around it -- where to
write figures, which wall alloy, whether to draw anything -- arrives as a RegenThermalContext.

The channels are circular, and the coolant side is Gnielinski with a roughness-corrected
friction factor. Spirally fluted channels, with the blended correlation they were rated by, are
kept in experimental/flutedChannels.py.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Gas side, checked against a published source.** The exhaust-side coefficient is the Bartz
correlation as given in Huzel and Huang, NASA SP-125:

    h_g = (0.026 / D_t^0.2) (mu_0^0.2 c_p0 / Pr_0^0.6) (P_c / c*)^0.8 (D_t / R_c)^0.1 (A_t / A)^0.9 sigma

with the stagnation Prandtl number from 4 gamma / (9 gamma - 5), the stagnation viscosity from
the fit mu_0 = 1.184e-7 M^0.5 T_0^0.6, and sigma the boundary layer correction. That viscosity
constant is the SI form of SP-125's 46.6e-10 M^0.5 T^0.6 in lbm/(in s) with T in Rankine, which
converts to 1.18408e-7 in SI. See tests/testRegenThermal.py for the comparison against a worked
example.

**Coolant side, not validated.** The correlation is Gnielinski, which is published and whose
range of validity is known, but nothing here checks the implementation against a reference case.

**Wall conduction, checked in closed form.** Each channel conducts through its own sector of the
wall, r ln(1 + t/r) / (k A_hw), with A_hw the sector's gas-side area. tests/testRegenThermal.py
holds it to the whole shell when the sectors are summed in parallel, to the slab t / (k A_hw)
for a thin wall, and holds the station solve to a wall drop equal to the heat flow times it.

**The gas state the model reads is one dimensional.** Every gas-side property comes from CEA at
a one-dimensional station, while the near-wall Mach number the method of characteristics
returns departs from the one-dimensional value by up to 42 percent near the throat. The two are
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

from .fluidProperties import fluidProps
from .errors import ConvergenceFailureError, InvalidInputError
from .ablative import blowingCorrection
from .figures import regenHeatTransferModelPlots
from .materials import wallMaterialCurves
from .radiativeCooling import effectiveGasSideDriving, wallRadiationCoefficient
from .validation import applyRules, arrayRule, integerRule, numericRule, read, textRule

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
    plotsEnabled : str
        'on' draws the interactive heat transfer view.
    export : str
        'on' writes figures to dataFolder rather than opening them.

    '''

    material:     str  = 'GRCop-42'
    dataFolder:   str  = ''
    plotsEnabled: str  = 'off'
    export:       str  = 'off'

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

def wallConductionResistance(hotWallThickness: float, wallRadius: float, wallConductivity: float,
                             hotWallArea: float) -> float:

    '''

    Conduction resistance of the wall behind one channel [K/W].

    A channel owns a sector of the cylindrical shell between the hot wall radius r and r + t, and
    `hotWallArea` is the gas-side area of that sector. Radial conduction through it is

        R_k = r ln(1 + t/r) / (k A_hw)

    For a sector of 2 pi / N over a station of length dL that is N ln(1 + t/r) / (2 pi k dL), the
    whole shell's resistance times the number of channels sharing it, and as t/r goes to zero it
    tends to the slab t / (k A_hw). The heat flow it carries is the same per-channel flow the two
    convective resistances carry, so the three are in series on a common basis.

    Parameters:
    -----------
    hotWallThickness : float
        Wall between coolant and exhaust [m].
    wallRadius : float
        Hot wall radius from the nozzle axis [m].
    wallConductivity : float
        Wall conductivity [W/m K].
    hotWallArea : float
        Gas-side area of the sector one channel owns [m^2].

    Returns:
    --------
    float
        Conduction resistance [K/W].

    '''

    return wallRadius * np.log1p(hotWallThickness / wallRadius) / (wallConductivity * hotWallArea)

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
    conductiveResistance : float
        Conduction resistance of the wall behind this channel [K/W].
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
    conductiveResistance:         float
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
    while from a channel axis the heat arrives from one side only. It is the resistance of the
    sector of that shell one channel owns, the same sector whose gas-side area is `hotWallArea`,
    so all three resistances carry the one per-channel heat flow. See
    `wallConductionResistance`.

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

        conductiveResistance = wallConductionResistance(hotWallThickness, wallRadius,
                                                        wallConductivity, hotWallArea)

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
        conductiveResistance         = conductiveResistance,
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
# rest. A run must carry the circular cross section, which is the one rule the table cannot
# express and that is checked alongside it.

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

    # -- The cross section being solved -- #
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
    cannot say: a run has to carry a cross section, or there is nothing to solve.

    Parameters:
    -----------
    inputsDict : dict
        Geometry, gas state and coolant state, one entry per station.

    Raises:
    -------
    InvalidInputError
        On the first rule the dictionary fails.

    """

    if not _hasCircularSection(inputsDict):
        raise InvalidInputError(
            message = ('No channel cross section was supplied, so there is nothing to solve. '
                       'Provide circleCSA and circleSA'),
            parameterName = 'circleCSA, circleSA',
            value = None,
            validRange = 'A circular cross section')

    applyRules(inputsDict, regenThermalRules)

def regenHeatTransferModel(context, inputsDict: dict, constantColdWallTemperature: float = None,
                           returnDict: bool = False, plots: bool = True, titleFlare: str = '',
                           xReference = [], rReference = []):

    r'''

    -- Regenerative Cooling Channels Heat Transfer Model (Version 2) --

    This function structures the heat transfer model for the regenerative
    cooling jacket: the heat transfer into the coolant, the hot wall
    temperature it holds, and the resultant fluid properties.

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
        + Channel Helix Angle
        + Number of Channels

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
    circleCSA                 = inputsDict["circleCSA"]
    circleSA                  = inputsDict["circleSA"]
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

        # Circular Cooling Channel Geometry and Flow Properties
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

        # Adiabatic Cold Wall Properties
        circleAdiabaticConvectiveHeatTransferCoef, circleAdiabaticHeatTransfer, \
        = [np.zeros(numCrossSections) for _ in range(2)]

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

        # Circular Channel Properties

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

        # Check if there are any nans anywhere in here
        if True:
            for name, value in locals().items():
                try:
                    # Check scalars
                    if isinstance(value, (float, int)) and math.isnan(value):
                        print(f"{name} is NaN (scalar)")
                        raise ValueError(f"{name} is NaN in Nozzle.regenHeatTranferModel.heatTransferModel()")

                    # Check arrays
                    if isinstance(value, np.ndarray) and np.isnan(value).any():
                        print(f"{name} contains NaN (array)")
                        raise ValueError(f"{name} is NaN in Nozzle.regenHeatTranferModel.heatTransferModel()")
                except:
                    pass  # Ignore variables that can't be NaN

        # Hot wall convergence
        if not runAdiabaticColdWall:

            # -- We don't know hot wall temperature, so converge to the correct hot wall temperature iteratively -- #

            def hotWallConvergenceLoops(throatRadiusOfCurvature):

                # Circle Hot Wall Temperature Convergence

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
        flutedHeatTransferOutputs = {}
        flutedPlotOutputs = {}
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
        flutedHeatTransferOutputs = {}
        flutedPlotOutputs = {}
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

    # Plots
    if plots and context.plotsEnabled == 'on':
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
