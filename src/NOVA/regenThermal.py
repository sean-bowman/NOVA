
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

One section family is solved per run, named by `channelType` in the input dictionary. The
family's flow area, heated area, hydraulic diameter and rib are computed by `channelSections`
before the model sees them, so the model itself does not branch on geometry. The coolant side
is Gnielinski with a Swamee-Jain friction factor on the hydraulic diameter for every family, and
a rib between channels, where the family has one, is a straight fin cooled on both faces.
Spirally fluted channels, with the blended correlation they were rated by, are kept in
experimental/flutedChannels.py.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Gas side, in `gasSideHeatTransfer`.** The exhaust-side coefficient is not the jacket's: the
ablative liner and the radiation-cooled extension read the same one. It lives in its own module
with its own validation status, which covers the Bartz form against Huzel and Huang, the throat
coefficient running 20 to 40 percent high against the constants measured in NASA TN D-2832, and
what `gasSideAxialModel` does about that.

**Coolant side, compared against hardware, not validated.** The coefficient is Gnielinski on the
hydraulic diameter with a Swamee-Jain friction factor, which is within 2.8 percent of Colebrook
over its range. Against Carlile and Quentmeyer's three copper chambers (NASA TM-105679), solved at
one station with the gas side fixed from their operating point, all 13 measured throat wall
temperatures lie inside the band the unknown coolant state and roughness span. The bands are wider
than the tolerances stated before the comparison, so it is a sensitivity-bounded comparison, not
a validation: docs/reports/carlileQuentmeyer_2026-09-22.md and tests/testRegenValidation.py.

**Roughness is bounded by measurement, and two datasets disagree about where the bound is.**
Roughness raises the friction factor, and the pressure drop with it, under every option in
COOLANTROUGHNESSMODELS. What it may do to the heat transfer is the choice. The default is
Dipprey and Sabersky's measured rough-wall heat transfer, which rises with roughness by less than
the friction does. 'fullCredit' puts the rough friction factor into Gnielinski's smooth-tube form,
which no measurement supports and which was what this model did before the comparisons below.
'frictionOnly' takes the heat transfer on the smooth-wall factor, which is what NASA TN D-7207 did.

The two hardware comparisons pull in opposite directions, which is why the bounded middle is the
default rather than either end. Against Carlile and Quentmeyer's chambers all 13 measured wall
temperatures fall inside the predicted band under the default and under full credit, while
friction only puts 2 of 13 below its band by predicting the wall too hot. Against the hydrogen
coefficients of TN D-7207 the ordering reverses: friction only lands nearest the measurements and
the default runs 1.4 to 1.8 times high. A coefficient that is too high cools the wall, so one
dataset asks for more heat transfer and the other for less.

The Dipprey and Sabersky fit was taken on water at Prandtl numbers of 1.2 to 5.94 in close-packed
sand-grain roughness. Hydrogen in a printed channel is below that Prandtl range and rough in a
different way. The coolant is taken as mixed across a tall channel.

**No wall-to-bulk property ratio correction is applied, and that is a measured choice rather than
an omission.** Taylor's correction (NASA TN D-4332) is implemented behind
`coolantPropertyCorrection` and defaults to off: switching it on puts 0 of Carlile and
Quentmeyer's 13 measured throat wall temperatures inside the predicted band, against 13 of 13
without it. Taylor is fitted on symmetrically heated tubes, and a cooling channel heated hard on
one face is not that geometry.

**The coolant energy balance is exact in enthalpy.** The heat a station passes into the coolant
is added to its specific enthalpy, and the temperature carrying that enthalpy at the downstream
pressure is read back from the property backend. What the wall gives up and what the coolant
takes on therefore agree to the backend's own inversion, about 1e-9 relative, which
tests/testRegenThermal.py holds station by station and over the jacket. A rise taken as
Q / (mdot cp) does not conserve it where cp varies across the station: for hydrogen entering at
30 K and 12 MPa the two differ by 0.7 percent at the first station and by under 0.1 percent once
the coolant is past 60 K.

**Wall conduction, checked in closed form.** Each channel conducts through its own sector of the
wall, r ln(1 + t/r) / (k A_hw), with A_hw the sector's gas-side area. tests/testRegenThermal.py
holds it to the whole shell when the sectors are summed in parallel, to the slab t / (k A_hw)
for a thin wall, and holds the station solve to a wall drop equal to the heat flow times it.
The gas-side area is the wall's, (2 pi r / N) ds_m over the wall's meridional length, so the
sectors tile the wall at any wrap angle and lengthening the channel path leaves it unchanged;
both are tested.

**Over the chamber barrel, the gas state is taken as stagnant.** The barrel's state takes the
chamber pressure as stagnation pressure with no Rayleigh loss. What the gas-side correlation does
over a subsonic barrel is recorded with the correlation, in `gasSideHeatTransfer`.

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
from .errors import ConvergenceFailureError, NumericalInstabilityError, PressureDropError
from .ablative import blowingCorrection
from .channelSections import SECTIONFAMILIES, finEfficiency
from .figures import regenHeatTransferModelPlots
from .gasSideHeatTransfer import (GASSIDEAXIALMODELS, bartzHeatTransferCoefficient,
                                  measuredAxialFactor)
from .materials import wallMaterialCurves
from .radiativeCooling import effectiveGasSideDriving, wallRadiationCoefficient
from .validation import applyRules, arrayRule, choiceRule, integerRule, numericRule, read, textRule

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

# Surface roughness the coolant-side friction factor is built on [m]: a printed GRCop-42 channel,
# from the Velo3D material datasheet
printedSurfaceRoughness = 35e-6

# How a rough wall is allowed to raise the coolant-side Nusselt number.
#
#   'frictionOnly'      roughness raises the friction factor and the pressure drop with it, and
#                       the heat transfer is taken on the smooth-wall friction factor. This is
#                       what NASA TN D-7207 did: friction factors computed with a measured
#                       surface irregularity, and no roughness effects accounted for in the heat
#                       transfer at all.
#   'dippreySabersky'   the measured rough-wall heat transfer of Dipprey and Sabersky, where
#                       roughness raises heat transfer by less than it raises friction.
#   'fullCredit'        the rough-wall friction factor goes straight into Gnielinski's
#                       smooth-tube form, so the Nusselt number rises in proportion to the
#                       friction. Not supported by any measurement; kept so a result recorded
#                       under it can be reproduced.
COOLANTROUGHNESSMODELS = ('frictionOnly', 'dippreySabersky', 'fullCredit')

# Whether the coolant-side correlation is corrected for the property variation between the bulk
# and the wall.
#
#   'none'      every property at the bulk temperature, which is what a smooth-tube correlation
#               is written for and what this model did before the option existed.
#   'taylor'    the surface-to-bulk temperature ratio correction of NASA TN D-4332. **Refuted
#               against the hardware this model is checked on, and kept only so the comparison
#               can be reproduced.** See the validation note on taylorPropertyFactor.
COOLANTPROPERTYCORRECTIONS = ('none', 'taylor')

# Range Taylor's correlation was fitted over, from the summary of NASA TN D-4332. Outside it the
# factor is still returned: the correlation is the best available and refusing a station over a
# flux bound would refuse the throat of most real engines. What the range is for is the report.
taylorTemperatureRatioRange = (1.1, 23.0)       # [-], surface over bulk
taylorDiameterRatioRange    = (2.0, 252.0)      # [-], distance from entrance over diameter
taylorReynoldsRange         = (7.5e3, 1.38e7)   # [-]
taylorHeatFluxRange         = (0.059e6, 45.7e6) # [W/m^2]

def taylorPropertyFactor(surfaceTemperature, bulkTemperature, diametersFromInlet):

    '''

    Taylor's wall-to-bulk property correction on a coolant-side Nusselt number.

    A smooth-tube correlation evaluates every property at the bulk temperature, which is wrong
    where the wall is much hotter than the fluid: the viscosity, conductivity and density in the
    near-wall layer are not the bulk ones. Hydrogen against a hot copper wall is the case this
    matters most for, and it is the case this tool is usually pointed at.

    Taylor correlated 3674 local hydrogen coefficients from ten investigations in symmetrically
    heated straight tubes (NASA TN D-4332, 1968) as

        Nu_b = 0.023 Re_b^0.8 Pr_b^0.4 (T_s / T_b)^-(0.57 - 1.59 D/x)

    and what is returned here is the ratio of that to the same correlation without the
    temperature-ratio term, so it multiplies whichever Nusselt number the roughness model
    produced rather than replacing it.

    **The correction reduces the coolant-side coefficient**, because the surface is hotter than
    the bulk and the exponent is negative, so a jacket solved with it runs a hotter wall.

    **It is refuted against Carlile and Quentmeyer, and the default is off.** Predicting their 13
    measured throat wall temperatures with it on puts 0 of 13 inside the band the unknowns span,
    against 13 of 13 without it, and moves the mean signed error from +18.8 K to +479.5 K.
    Replacing Gnielinski with Taylor's complete correlation rather than multiplying the ratio term
    onto it is worse still, at 0 of 13 and +704.7 K. On the shipped jacket at fixed geometry the
    peak wall goes from 800 K to 1727 K, past the melting point of the alloy it is built from.

    The likely reason is what Taylor's surface temperature means. The fit is on **symmetrically
    heated straight tubes**, where the surface is at one temperature all the way around. A rocket
    cooling channel is heated hard on one face and the other three run far cooler, so handing the
    correlation the hot-face temperature over-applies a correction whose own data never saw a
    perimeter that non-uniform. A perimeter-averaged surface temperature would be the defensible
    way to carry this term, and nothing here computes one.

    Kept rather than deleted so the comparison above can be re-run, which is how
    COOLANTROUGHNESSMODELS treats 'fullCredit' for the same reason.

    The entrance term is the second half of the exponent. Near the inlet the exponent approaches
    zero and the correction vanishes; far downstream it approaches -0.57, which is the asymptotic
    form other tools quote on its own.

    Taylor states the fit does not hold near the critical point: an inlet between 25 K and the
    transposed critical temperature **and** a pressure between the critical pressure and 3.65 MPa
    is the excluded region. Both conditions have to hold, so a jacket entering at 30 K and 12 MPa
    is outside the exclusion on pressure.

    Parameters:
    -----------
    surfaceTemperature : array_like
        Coolant-side wall temperature [K].
    bulkTemperature : array_like
        Coolant bulk temperature [K].
    diametersFromInlet : array_like
        Distance from the channel inlet in hydraulic diameters, x/D [-].

    Returns:
    --------
    numpy.ndarray or float
        Multiplier on the Nusselt number [-].

    '''

    ratio = np.asarray(surfaceTemperature, dtype = float) \
            / np.maximum(np.asarray(bulkTemperature, dtype = float), 1e-6)

    # A surface below the bulk is not what the fit covers, and squaring it into an exponent would
    # raise the coefficient rather than lower it. The correction is held off there.
    ratio = np.maximum(ratio, 1.0)

    # x/D below the fitted floor is the developing length, where the exponent would change sign
    # and invert the correction. It is clamped to the floor instead.
    diameters = np.maximum(np.asarray(diametersFromInlet, dtype = float),
                           taylorDiameterRatioRange[0])

    factor = ratio**(-(0.57 - 1.59/diameters))

    return float(factor) if np.isscalar(surfaceTemperature) and factor.ndim == 0 else factor

def swameeJainFriction(reynoldsNumber, relativeRoughness):

    '''Darcy friction factor from Swamee and Jain's explicit form of Colebrook.'''

    return 0.25 / (np.log10(relativeRoughness/3.7 + 5.74/reynoldsNumber**0.9))**2

def gnielinskiNusselt(frictionFactor, reynoldsNumber, prandtlNumber):

    '''Gnielinski's Nusselt number for turbulent pipe flow, on a supplied friction factor.'''

    return ((frictionFactor / 8) * (reynoldsNumber - 1000) * prandtlNumber) / \
           (1 + 12.7 * (frictionFactor / 8)**(1/2) * (prandtlNumber**(2/3) - 1))

def dippreySaberskyNusselt(frictionFactor, reynoldsNumber, prandtlNumber, relativeRoughness):

    '''

    Nusselt number for a rough wall, from Dipprey and Sabersky's measurements.

    Their sand-grain roughened tubes give the heat transfer that goes with a measured friction,

        St = (f/8) / (1 + sqrt(f/8) [5.19 (e+)^0.2 Pr^0.44 - 8.48]),    e+ = (e/D) Re sqrt(f/8)

    which rises with roughness more slowly than the friction does, and reduces to the smooth-wall
    result as the roughness Reynolds number falls. Below a roughness Reynolds number of about 5
    the wall is hydraulically smooth and the smooth-tube form is returned instead, so there is no
    step between the two.

    The fit was taken on water at Prandtl numbers of 1.2 to 5.94 in close-packed sand-grain
    roughness. Hydrogen in a printed channel is below that Prandtl range and is rough in a
    different way, so this is an extrapolation in both, bounded by measurement rather than
    validated by it.

    Parameters:
    -----------
    frictionFactor : array_like
        Darcy friction factor at the wall's own roughness [-].
    reynoldsNumber, prandtlNumber : array_like
        Coolant bulk Reynolds and Prandtl numbers [-].
    relativeRoughness : array_like
        Absolute roughness over hydraulic diameter [-].

    Returns:
    --------
    numpy.ndarray
        Nusselt number [-].

    '''

    frictionGroup = np.sqrt(np.asarray(frictionFactor, dtype = float) / 8)
    roughnessReynolds = np.asarray(relativeRoughness, dtype = float) * reynoldsNumber * frictionGroup

    # The correlation is written for a wall the roughness has already tripped
    roughWall = roughnessReynolds > 5.0
    heatTransferFunction = 5.19 * np.maximum(roughnessReynolds, 1e-12)**0.2 * prandtlNumber**0.44

    stanton = frictionGroup**2 / (1 + frictionGroup*(heatTransferFunction - 8.48))

    return np.where(roughWall, stanton * reynoldsNumber * prandtlNumber,
                    gnielinskiNusselt(swameeJainFriction(reynoldsNumber, 0.0),
                                      reynoldsNumber, prandtlNumber))

def coolantFrictionAndNusselt(reynoldsNumber, prandtlNumber, hydraulicDiameter,
                              surfaceRoughness: float = printedSurfaceRoughness,
                              roughnessModel: str = 'dippreySabersky') -> tuple:

    '''

    Coolant-side Darcy friction factor and Nusselt number on the hydraulic diameter.

    The friction factor is Swamee and Jain's explicit form of Colebrook at the wall's own
    roughness, and it is what the pressure drop is computed from whichever model is selected,

        f = 0.25 / log10(e / (3.7 D_h) + 5.74 / Re^0.9)^2

    What the roughness is allowed to do to the heat transfer is the choice. 'frictionOnly' takes
    Gnielinski's Nusselt number,

        Nu = (f/8)(Re - 1000) Pr / (1 + 12.7 (f/8)^0.5 (Pr^(2/3) - 1))

    on the smooth-wall friction factor, so roughness costs pressure and buys nothing.
    'dippreySabersky' takes the measured rough-wall heat transfer, which buys less than the
    friction it costs. 'fullCredit' puts the rough friction factor into Gnielinski, which buys
    heat transfer in proportion to the friction and is what no measurement supports.

    Every property is at the bulk temperature. A wall-to-bulk property ratio correction is
    available through `coolantPropertyCorrection` and is off by default, because against the
    hardware comparison it makes the predictions much worse rather than better; the note on
    `taylorPropertyFactor` carries the numbers.

    Parameters:
    -----------
    reynoldsNumber, prandtlNumber : float
        Coolant bulk Reynolds and Prandtl numbers [-].
    hydraulicDiameter : float
        Hydraulic diameter of the section [m].
    surfaceRoughness : float
        Absolute roughness of the channel wall [m]. The default is a printed channel.
    roughnessModel : str
        One of COOLANTROUGHNESSMODELS.

    Returns:
    --------
    tuple
        (Darcy friction factor [-], Nusselt number [-]).

    '''

    relativeRoughness = surfaceRoughness / hydraulicDiameter
    frictionFactor    = swameeJainFriction(reynoldsNumber, relativeRoughness)

    if roughnessModel == 'fullCredit':
        nusseltNumber = gnielinskiNusselt(frictionFactor, reynoldsNumber, prandtlNumber)
    elif roughnessModel == 'dippreySabersky':
        nusseltNumber = dippreySaberskyNusselt(frictionFactor, reynoldsNumber, prandtlNumber,
                                               relativeRoughness)
    else:
        nusseltNumber = gnielinskiNusselt(swameeJainFriction(reynoldsNumber, 0.0),
                                          reynoldsNumber, prandtlNumber)

    return frictionFactor, float(nusseltNumber) if np.isscalar(reynoldsNumber) else nusseltNumber

def entranceEnhancementFactor(distanceFromInlet, hydraulicDiameter):

    '''

    Heat transfer enhancement in the developing length after a channel inlet.

    A boundary layer that has not filled the passage transfers more heat than a developed one.
    The fit is Boelter, Young and Iversen's for a 90 degree entrance, as NASA TN D-7207 applies
    it to rocket coolant passages,

        phi_2 = 2.88 / (S/d)^0.325,    never less than 1

    with S the distance along the channel from its inlet manifold. It reaches 1 at S/d near 33,
    so it is a correction to the first stretch of a passage and nothing at all further down.

    Parameters:
    -----------
    distanceFromInlet : array_like
        Distance along the channel from the inlet manifold [m].
    hydraulicDiameter : array_like
        Hydraulic diameter of the section [m].

    Returns:
    --------
    numpy.ndarray
        Multiplier on the coolant-side coefficient [-], one per station.

    '''

    lengthToDiameter = np.asarray(distanceFromInlet, dtype = float) \
                       / np.asarray(hydraulicDiameter, dtype = float)

    # At the inlet itself the fit is unbounded, and a passage has no developing length before it
    lengthToDiameter = np.where(lengthToDiameter > 0, lengthToDiameter, np.inf)

    return np.maximum(2.88 / lengthToDiameter**0.325, 1.0)

def itoCurvatureFactor(reynoldsNumber, sectionRadius, bendRadius):

    '''

    Heat transfer enhancement where a coolant passage follows a bend.

    A curved passage carries a secondary flow, because fluid near the axis is thrown outward
    harder than the slower fluid at the wall. Ito's resistance ratio for turbulent flow in a
    curved pipe,

        phi_1 = lambda / lambda_0 = [Re (R/r)^2]^0.05,    for Re (R/r)^2 > 6

    with R the passage's own cross-sectional radius and r the radius of the bend it follows, is
    what NASA TN D-7207 found gives about the right magnitude for the enhancement measured
    through a throat. Below the threshold the bend does nothing and the factor is 1.

    The factor says nothing about which way the passage bends. Measured enhancement takes a
    distance to build and a further distance to decay, so through a throat, where the wall turns
    one way and then the other within a few diameters, this is an upper bound rather than a
    distribution.

    Parameters:
    -----------
    reynoldsNumber : array_like
        Coolant Reynolds number on the hydraulic diameter [-].
    sectionRadius : array_like
        Cross-sectional radius of the passage [m].
    bendRadius : array_like
        Radius of curvature of the path the passage follows [m]. Infinite where it is straight.

    Returns:
    --------
    numpy.ndarray
        Multiplier on the coolant-side coefficient [-], one per station.

    '''

    reynoldsNumber = np.asarray(reynoldsNumber, dtype = float)
    curvature = np.asarray(sectionRadius, dtype = float) / np.asarray(bendRadius, dtype = float)

    parameter = reynoldsNumber * curvature**2

    return np.where(parameter > 6.0, np.maximum(parameter, 1.0)**0.05, 1.0)

def hotWallSectorArea(wallRadius, nChannel: int, wallSegmentLength):

    '''

    Gas-side area of the wall one channel owns at a station [m^2].

    A channel owns 2 pi r / N of the circumference and the wall's own meridional length of the
    station, so N sectors tile the wall exactly. The channel's path is longer than the wall
    segment wherever it wraps, by 1/cos of its wrap angle, but the exhaust sees the wall rather
    than the path, so the path length does not enter.

    Parameters:
    -----------
    wallRadius : float or np.ndarray
        Hot wall radius from the nozzle axis [m].
    nChannel : int
        Channels around the circumference [-].
    wallSegmentLength : float or np.ndarray
        Meridional length of hot wall the station covers [m].

    Returns:
    --------
    float or np.ndarray
        Gas-side area per channel [m^2].

    '''

    return (2 * np.pi * wallRadius / nChannel) * wallSegmentLength

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
    finEfficiency : float
        Efficiency of the rib as a fin [-]. Exactly one where there is no rib.
    heatTransfer : float
        Heat through the wall at this station, per channel [W]. A power, not a flux: the areas
        are already folded into the three resistances.
    coatingInterfaceTemperature : float
        Temperature of the metal's gas-side face [K]. Equal to `hotWallTemperature` when there is
        no coating, and the temperature a metal wall limit applies to when there is one: the
        point of a barrier coating is that its own surface runs hotter than the metal behind it.
    hotWallTemperature, coldWallTemperature : float
        The two faces of the wall [K].
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
    finEfficiency:                float
    heatTransfer:                 float
    hotWallTemperature:           float
    coldWallTemperature:          float
    coatingInterfaceTemperature:  float
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
                                finHeight: float = 0.0, finThickness: float = 0.0,
                                prescribedGasCoefficient: float = None,
                                gasSideAxialModel: str = 'uniform',
                                propertyCorrection: str = 'none',
                                diametersFromInlet: float = None,
                                coatingThickness: float = 0.0,
                                coatingConductivity: float = 0.0,
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
        Coolant-side area the heat enters through directly, before any fin, per channel [m^2].
    hotWallArea : float
        Gas-side area of this station, per channel [m^2].
    hotWallThickness : float
        Wall between coolant and exhaust [m].
    wallRadius : float
        Hot wall radius from the nozzle axis [m].
    pathLength : float
        Length of this station along the channel, the length the fin faces run [m].
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
    prescribedGasCoefficient : float
        Gas-side convective coefficient to use in place of Bartz [W/m^2 K], held fixed through
        the solve. What a comparison against a measured heat flux supplies; the Bartz inputs are
        then not read.
    gasSideAxialModel : str
        'uniform' carries one correlation constant along the whole wall, which is what Bartz
        assumes. 'measured' scales it by the constants measured along a LOX/GH2 chamber, which
        leaves the barrel alone and takes about 40 percent off the throat. Read only when no
        coefficient is prescribed. 'ievlev' has no station-local form, because it depends on the
        wall upstream, so it arrives only as a prescribed coefficient and is refused without one.
    finHeight, finThickness : float
        The rib between channels, treated as a straight fin cooled on both faces with an
        adiabatic tip [m]. It adds 2 eta H of perimeter to the coolant side, with eta taken at
        the conductivity of the previous pass's cold wall. A height of zero leaves the coolant
        side exactly as `coolantWettedArea` gives it.
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

    hotWallTemperatureGuess  = drivingTemperature
    coldWallTemperatureGuess = coolantTemperature
    coatingInterfaceGuess    = drivingTemperature
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

        # The property correction reads the surface temperature, which is what this loop is
        # converging, so it is applied inside the loop rather than by the caller. At convergence
        # the Nusselt number and the wall it was evaluated against are the same answer.
        correctedNusseltNumber = coolantNusseltNumber
        if propertyCorrection == 'taylor':
            correctedNusseltNumber = coolantNusseltNumber * taylorPropertyFactor(
                coldWallTemperatureGuess, coolantTemperature,
                diametersFromInlet if diametersFromInlet is not None
                else taylorDiameterRatioRange[0])

        coolantConvectiveCoefficient = coolantThermalConductivity * correctedNusseltNumber \
                                       / hydraulicDiameter

        # The rib conducts heat into the coolant through both of its faces, less effectively
        # the further they reach from the wall. Without a rib the area is the one given.
        ribEfficiency = 1.0
        coolantArea   = coolantWettedArea
        if finHeight > 0:
            ribEfficiency = finEfficiency(coolantConvectiveCoefficient,
                                          float(conductivityInterpolator(coldWallTemperatureGuess)),
                                          finThickness, finHeight)
            coolantArea   = coolantWettedArea + 2*ribEfficiency*finHeight*pathLength
        coolantConvectiveResistance = 1 / (coolantConvectiveCoefficient * coolantArea)

        # A thermal barrier coating is a second shell inside the metal one, so it takes the same
        # cylindrical form at the gas-side radius and the metal moves outboard behind it. The
        # metal's conductivity is read at the metal's own hot face rather than at the coating
        # surface, which with a coating are hundreds of kelvin apart.
        coatingResistance = 0.0
        metalRadius = wallRadius
        metalArea   = hotWallArea
        if coatingThickness > 0.0 and coatingConductivity > 0.0:
            coatingResistance = wallConductionResistance(coatingThickness, wallRadius,
                                                         coatingConductivity, hotWallArea)
            metalRadius = wallRadius + coatingThickness
            metalArea   = hotWallArea * metalRadius / wallRadius
            wallConductivity = float(conductivityInterpolator(coatingInterfaceGuess))

        conductiveResistance = coatingResistance                                + wallConductionResistance(hotWallThickness, metalRadius,
                                                          wallConductivity, metalArea)

        if prescribedGasCoefficient is None and gasSideAxialModel == 'ievlev':
            raise ValueError("The 'ievlev' gas side depends on the wall upstream of the station, so "
                             'it has to arrive as a prescribed coefficient solved over the whole '
                             'wall; a station cannot form it alone.')
        if prescribedGasCoefficient is None:
            exhaustConvectiveCoefficient = bartzHeatTransferCoefficient(
                gasStaticTemperature, gasMachNumber, gasGamma,
                gasConstant, gasMolecularWeight, hotWallTemperatureGuess,
                chamberPressure, characteristicVelocity, throatDiameter,
                throatRadiusOfCurvature, throatArea, localArea)
            # One correlation constant along the whole wall is what Bartz assumes and what the
            # measurements contradict, most of all at the throat
            if gasSideAxialModel == 'measured':
                exhaustConvectiveCoefficient *= measuredAxialFactor(localArea / throatArea,
                                                                    gasMachNumber < 1.0)
        else:
            exhaustConvectiveCoefficient = prescribedGasCoefficient

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

        # Without a coating the interface is the hot wall, so every result below is unchanged.
        coatingInterfaceTemperature = hotWallTemperature - heatTransfer*coatingResistance

        residual = abs(hotWallTemperatureGuess - hotWallTemperature)

        if residual < tolerance:
            converged = True
        else:
            hotWallTemperatureGuess  = hotWallTemperature
            coldWallTemperatureGuess = coldWallTemperature
            coatingInterfaceGuess    = coatingInterfaceTemperature

    return StationWallSolution(
        coolantConvectiveCoefficient = coolantConvectiveCoefficient,
        exhaustConvectiveCoefficient = exhaustConvectiveCoefficient,
        radiationCoefficient         = radiationCoefficient,
        radiativeHeatTransfer        = radiationCoefficient * hotWallArea
                                       * (gasStaticTemperature - hotWallTemperature),
        blowingReduction             = blowingReduction,
        wallConductivity             = wallConductivity,
        conductiveResistance         = conductiveResistance,
        finEfficiency                = ribEfficiency,
        heatTransfer                 = heatTransfer,
        hotWallTemperature           = hotWallTemperature,
        coldWallTemperature          = coldWallTemperature,
        coatingInterfaceTemperature  = coatingInterfaceTemperature,
        iterations                   = convergenceIteration,
        residual                     = residual,
        converged                    = converged)

# What the thermal model needs in its input dictionary before it will run. Written as a table
# rather than as branches: see validation.py.
#
# The dictionary carries one entry per station for the distributed quantities and a scalar for the
# rest. The section arrays are the family's, computed by channelSections, so the table checks
# them the same way whatever the family is.

def _hasFin(inputs):

    '''True when the dictionary carries a rib to treat as a fin.'''

    return read(inputs, 'finHeight') is not None

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

    # -- The wall each station covers, and the path the coolant takes across it -- #
    arrayRule('hotWallSegmentLength', 'Hot wall meridional length per station', units = 'm',
              positive = True, sameLengthAs = 'xHotWall3D',
              note = 'The wall the station covers, not the channel path across it'),
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
    choiceRule('channelType', 'Channel cross section', choices = SECTIONFAMILIES),
    choiceRule('gasSideAxialModel', 'Gas-side axial distribution',
               choices = GASSIDEAXIALMODELS, required = False),
    choiceRule('coolantRoughnessModel', 'Coolant roughness model',
               choices = COOLANTROUGHNESSMODELS, required = False),
    numericRule('channelSurfaceRoughness', 'Channel surface roughness', units = 'm',
                minimum = 0, exclusiveMinimum = False, required = False),
    arrayRule('flowArea', 'Channel flow area', units = 'm^2',
              positive = True, sameLengthAs = 'xHotWall3D'),
    arrayRule('heatedArea', 'Coolant-side heated area per station', units = 'm^2',
              positive = True, sameLengthAs = 'xHotWall3D'),
    arrayRule('hydraulicDiameter', 'Channel hydraulic diameter', units = 'm',
              positive = True, sameLengthAs = 'xHotWall3D'),
    arrayRule('finHeight', 'Rib height', units = 'm', sameLengthAs = 'xHotWall3D', when = _hasFin),
    arrayRule('finThickness', 'Rib thickness', units = 'm', sameLengthAs = 'xHotWall3D',
              when = _hasFin),

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

    The rules are the table above, checked by `validation.applyRules`.

    Parameters:
    -----------
    inputsDict : dict
        Geometry, gas state and coolant state, one entry per station.

    Raises:
    -------
    InvalidInputError
        On the first rule the dictionary fails.

    """

    applyRules(inputsDict, regenThermalRules)

def regenHeatTransferModel(context, inputsDict: dict, constantColdWallTemperature: float = None,
                           returnDict: bool = False, plots: bool = True, titleFlare: str = '',
                           xReference = [], rReference = []):

    '''

    Solve the coolant and wall along one channel, marching from the coolant inlet.

    At each station the coolant properties are taken at the local state, the friction factor and
    Nusselt number from Swamee-Jain and Gnielinski on the section's hydraulic diameter, the
    pressure drop from friction and the bend loss, and the hot wall temperature from
    `solveStationWallTemperature`. The heat the station passes raises the coolant for the next.

    Parameters:
    -----------
    context : RegenThermalContext
        Where figures go and which wall alloy the conductivity is read for.
    inputsDict : dict
        Geometry, gas state and coolant state. `regenThermalRules` lists the keys. The station
        arrays are indexed along the nozzle, and the march runs from the last index to the first.
        One station is solved on its own, for the sizing march, when `numCrossSections` is one.
    constantColdWallTemperature : float
        Fixes the cold wall rather than solving for it, which runs the adiabatic comparison [K].
    returnDict : bool
        Return the results rather than only drawing them. Always true for a single station.
    plots : bool
        Draw the result, subject to the context. Always false for a single station.
    titleFlare : str
        Appended to the figure title.
    xReference, rReference : array_like
        Wall contour drawn under the results [m].

    Returns:
    --------
    tuple
        (heatTransferOutputs, plotOutputs) when `returnDict` is set: the coolant pressure and
        temperature and the two wall temperatures, and every per-station quantity the figure
        draws.

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
    hotWallSegmentLength      = inputsDict["hotWallSegmentLength"]
    hotWallThickness          = inputsDict["hotWallThickness"]
    throatRadiusOfCurvature   = inputsDict["throatRadiusOfCurvature"]
    throatDiameter            = inputsDict["throatDiameter"]
    throatArea                = inputsDict["throatArea"]
    # Cross section and centerline geometric properties, computed for the family by channelSections
    channelType               = inputsDict["channelType"]
    flowArea                  = inputsDict["flowArea"]
    heatedArea                = inputsDict["heatedArea"]
    hydraulicDiameter         = inputsDict["hydraulicDiameter"]
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
    hotWallArea             = hotWallSectorArea(rHotWall3D, nChannel, hotWallSegmentLength)

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

    # One correlation constant along the whole wall, or the measured distribution over it
    gasSideAxialModel = inputsDict.get('gasSideAxialModel') or 'uniform'

    # A gas-side coefficient solved over the whole wall rather than at the station, which is how a
    # method that carries the wall's history reaches the station solve. Absent, Bartz runs.
    prescribedGasCoefficient = inputsDict.get('prescribedGasCoefficient')
    if prescribedGasCoefficient is not None:
        prescribedGasCoefficient = np.atleast_1d(np.asarray(prescribedGasCoefficient, dtype = float))

    # The entrance and curvature corrections a coolant correlation written for a straight
    # developed passage needs where the passage is neither. The coolant enters at the last
    # station and marches toward the first, so distance from the inlet accumulates backwards.
    # What a rough wall is allowed to do to the heat transfer, and the roughness itself
    coolantRoughnessModel = inputsDict.get('coolantRoughnessModel') or 'dippreySabersky'
    channelSurfaceRoughness = inputsDict.get('channelSurfaceRoughness')
    if channelSurfaceRoughness is None or np.isnan(channelSurfaceRoughness):
        channelSurfaceRoughness = printedSurfaceRoughness

    coolantGeometryCorrections = bool(inputsDict.get('coolantGeometryCorrections'))
    coolantPropertyCorrection  = inputsDict.get('coolantPropertyCorrection') or 'none'
    thermalBarrierThickness    = float(inputsDict.get('thermalBarrierThickness') or 0.0)
    thermalBarrierConductivity = float(inputsDict.get('thermalBarrierConductivity') or 0.0)
    distanceFromInlet = inputsDict.get('distanceFromInlet')
    if distanceFromInlet is None:
        distanceFromInlet = np.flip(np.cumsum(np.flip(np.asarray(differentialPathLength, dtype = float))))
    distanceFromInlet = np.atleast_1d(np.asarray(distanceFromInlet, dtype = float))

    # Both default to zero, and zero is exact here: the radiative coefficient returns exactly 0.0
    # and the blowing correction exactly 1.0, so neither moves a bit of the answer.
    wallEmissivity = optionalScalar('wallEmissivity', 0.0)
    blowingFactor  = optionalScalar('blowingFactor', 0.5)
    gasEmissivity  = optionalInput('gasEmissivity', 0.0)
    filmMassFlux   = optionalInput('filmMassFlux', 0.0)

    # A family without a rib carries none, and zero height leaves the coolant side untouched.
    finHeight      = optionalInput('finHeight', 0.0)
    finThickness   = optionalInput('finThickness', 0.0)

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

        # Cooling Channel Flow Properties
        coolantTemperature, coolantPressure, coolantVelocity, \
        coolantMachNumber, coolantReynoldsNumber, coolantNusseltNumber, \
        coolantConvectiveHeatTransferCoef, exhaustConvectiveHeatTransferCoef, heatTransfer, wallConductivity, \
        hotWallTemperature, coldWallTemperature \
        = [np.zeros(numCrossSections) for _ in range(12)]

        coolantTemperature[-1] = coolantInitialTemperature
        coolantPressure[-1]    = coolantInitialPressure

        # Cooling Channel Thermophysical Properties
        coolantDensity, coolantViscosity, coolantSpecificHeat, \
        coolantGamma, coolantThermalConductivity, coolantSpeedOfSound, \
        coolantEnthalpy, coolantPrandtlNumber \
        = [np.zeros(numCrossSections) for _ in range(8)]

        coolantThermalConductivity[-1] = np.mean(wallThermalConductivityData)

        # Radiation is reported separately from the total so a reader can see how
        # much of the flux it actually is, and the blowing factor so a film-cooled run
        # shows how much of the coefficient it removed. Inert values unless asked for.
        radiativeHeatTransfer = np.zeros(numCrossSections)
        blowingReduction      = np.ones(numCrossSections)

        # Adiabatic Cold Wall Properties
        adiabaticConvectiveHeatTransferCoef, adiabaticHeatTransfer, \
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

        def downstreamTemperature(stationEnthalpy, heat, downstreamPressure):

            '''

            Temperature the coolant reaches once the station's heat has gone into it.

            The step is taken on enthalpy rather than as heat / (mdot cp), because cp is not
            constant across a station: near hydrogen's pseudo-critical line it swings by a
            factor of several over a few kelvin, and a rise taken at the station's own cp would
            not conserve the heat the wall put in. Enthalpy conserves it by construction, and
            the property backend inverts to the temperature that carries it.

            Parameters:
            -----------
            stationEnthalpy : float
                Specific enthalpy of the coolant entering the station [J/kg].
            heat : float
                Heat into this channel at this station [W].
            downstreamPressure : float
                Coolant pressure at the station the temperature lands on [Pa].

            Returns:
            --------
            float
                Coolant temperature at that station [K].

            '''

            return float(fluidProps(coolant, 'PH', 'T', downstreamPressure,
                                    stationEnthalpy + heat/mdot))

        # Channel Properties

        # Pull thermophysical properties at the current (T, P) with RefProp
        coolantDensity[i], coolantViscosity[i], coolantSpecificHeat[i], \
        coolantGamma[i], coolantThermalConductivity[i], coolantSpeedOfSound[i], \
        coolantEnthalpy[i], coolantPrandtlNumber[i] \
        = fluidProps(coolant, 'TP', 'D VIS Cp Cp/Cv TCX W H PRANDTL', coolantTemperature[i], coolantPressure[i])

        # Calculate dependept flow properties
        coolantVelocity[i]       = mdot / (coolantDensity[i] * flowArea[i])
        coolantMachNumber[i]     = coolantVelocity[i] / coolantSpeedOfSound[i]
        coolantReynoldsNumber[i] = coolantDensity[i] * hydraulicDiameter[i] * coolantVelocity[i] / coolantViscosity[i]

        # Calculate Nusselt Number
        # Swamee-Jain friction factor for the Gnielinski Nusselt number, on the hydraulic diameter
        frictionFactor, coolantNusseltNumber[i] = coolantFrictionAndNusselt(
            coolantReynoldsNumber[i], coolantPrandtlNumber[i], hydraulicDiameter[i],
            surfaceRoughness = channelSurfaceRoughness, roughnessModel = coolantRoughnessModel)

        # A developing boundary layer after the inlet and the secondary flow through a bend both
        # carry more heat than the straight developed passage the correlation is written for
        if coolantGeometryCorrections:
            coolantNusseltNumber[i] *= float(
                entranceEnhancementFactor(distanceFromInlet[i], hydraulicDiameter[i])
                * itoCurvatureFactor(coolantReynoldsNumber[i], 0.5*hydraulicDiameter[i],
                                     radiusOfCurvature[i]))

        # Calculate pressure drop and update downstream pressure for each channel section
        momentumLossCoef = findKFactor(turnAngle[i], radiusOfCurvature[i], hydraulicDiameter[i])

        frictionPressureDrop = differentialPathLength[i] * frictionFactor * coolantDensity[i] * coolantVelocity[i]**2 / (2 * hydraulicDiameter[i])
        momentumPressureDrop = momentumLossCoef * coolantDensity[i] * coolantVelocity[i]**2 / 2
        totalPressureDrop    = frictionPressureDrop + momentumPressureDrop

        # A jacket can spend more pressure than it has, and nothing downstream of that is
        # meaningful: the station's own property calls are made at the pressure computed here,
        # and a pressure at or below zero is not a state any equation of state answers for. It is
        # caught here, while the drop that caused it is still in hand to report.
        enteringPressure   = coolantPressure[i]
        downstreamPressure = enteringPressure - totalPressureDrop

        if downstreamPressure <= 0.0:
            raise PressureDropError(
                message = f'The coolant runs out of pressure at x = '
                          f'{1e3*float(xHotWall3D[i]):.1f} mm. It arrives at '
                          f'{1e-6*float(enteringPressure):.3f} MPa and the station spends '
                          f'{1e-6*float(totalPressureDrop):.3f} MPa, of which '
                          f'{1e-6*float(frictionPressureDrop):.3f} MPa is friction and '
                          f'{1e-6*float(momentumPressureDrop):.3f} MPa is turning. The channel '
                          f'there is too small for the flow it carries: fewer channels, a larger '
                          f'maxChannelDepth or a higher inlet pressure give it room.',
                pressureDrop = float(totalPressureDrop),
                exitPressure = float(downstreamPressure))

        if i > 0:
            coolantPressure[i-1] = downstreamPressure
        if iterationMode == 'single':
            coolantPressure[i] = downstreamPressure

        # A NaN anywhere in the station's state means an upstream quantity is already bad, and
        # carrying on would bury the cause stations later. Object arrays hold the conductivity
        # interpolators and have no NaN to find.
        for name, value in locals().items():
            if isinstance(value, float):
                isBad = math.isnan(value)
            elif isinstance(value, np.ndarray) and np.issubdtype(value.dtype, np.number):
                isBad = bool(np.isnan(value).any())
            else:
                isBad = False
            if isBad:
                raise NumericalInstabilityError(
                    message = f'{name} is NaN at station {i} of the regen thermal model',
                    variableName = name,
                    value = value,
                    operation = f'regenHeatTransferModel station {i}')

        # Hot wall convergence
        if not runAdiabaticColdWall:

            # -- We don't know hot wall temperature, so converge to the correct hot wall temperature iteratively -- #

            def hotWallConvergenceLoops(throatRadiusOfCurvature):

                # Hot Wall Temperature Convergence

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
                        coolantTemperature         = coolantTemperature[i],
                        coolantThermalConductivity = coolantThermalConductivity[i],
                        coolantNusseltNumber       = coolantNusseltNumber[i],
                        propertyCorrection         = coolantPropertyCorrection,
                        coatingThickness           = thermalBarrierThickness,
                        coatingConductivity        = thermalBarrierConductivity,
                        diametersFromInlet         = float(distanceFromInlet[i]
                                                           / hydraulicDiameter[i]),
                        coolantSpecificHeat        = coolantSpecificHeat[i],
                        coolantMassFlow            = mdot,
                        hydraulicDiameter          = hydraulicDiameter[i],
                        coolantWettedArea          = heatedArea[i],
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
                        gasSideAxialModel          = gasSideAxialModel,
                        prescribedGasCoefficient   = (None if prescribedGasCoefficient is None
                                                      else float(prescribedGasCoefficient[i])),
                        finHeight                  = finHeight[i],
                        finThickness               = finThickness[i],
                        tolerance                  = 0.01)
                except ValueError as error:
                    debugFile = dumpDebugInfo(locals(), i, time.time() - start_time)
                    raise ValueError('{} Station {}, {} channel.{}'.format(
                        error, i, channelType, ' Local state written to {}.'.format(debugFile)
                        if debugFile else '')) from error

                wallConductivity[i]                  = solution.wallConductivity
                coolantConvectiveHeatTransferCoef[i] = solution.coolantConvectiveCoefficient
                exhaustConvectiveHeatTransferCoef[i] = solution.exhaustConvectiveCoefficient
                heatTransfer[i]                      = solution.heatTransfer
                hotWallTemperature[i]                = solution.hotWallTemperature
                coldWallTemperature[i]               = solution.coldWallTemperature
                radiativeHeatTransfer[i]             = solution.radiativeHeatTransfer
                blowingReduction[i]                  = solution.blowingReduction

                # The march runs from the coolant inlet toward the chamber, so the heat picked
                # up here raises the coolant at the next station down the index. A single
                # station has no next one, so it takes the rise itself.
                if i > 0:
                    coolantTemperature[i-1] = downstreamTemperature(coolantEnthalpy[i],
                                                                    solution.heatTransfer,
                                                                    coolantPressure[i-1])
                if solution.converged and iterationMode == 'single':
                    coolantTemperature[i] = downstreamTemperature(coolantEnthalpy[i],
                                                                  solution.heatTransfer,
                                                                  coolantPressure[i])

                if not solution.converged:
                    raise ConvergenceFailureError(
                        message = 'Hot wall temperature convergence failed at station '
                                  '{} after {} iterations'.format(i, solution.iterations),
                        context = {
                            'stationIndex': i,
                            'iterationCount': solution.iterations,
                            'residual': solution.residual,
                            'tolerance': 0.01,
                            'hotWallTemperature': solution.hotWallTemperature,
                            'metalWallTemperature': solution.coatingInterfaceTemperature,
                            'heatTransfer': solution.heatTransfer,
                            'regenSectionNearWallTemperature': nearWallTemperature[i],
                            'coolantTemperature': coolantTemperature[i]
                        },
                        iterations = solution.iterations,
                        tolerance = 0.01,
                        residual = solution.residual)

            hotWallConvergenceLoops(throatRadiusOfCurvature)

        # Adiabatic cold wall
        else:

            adiabaticConvectiveHeatTransferCoef[i] = coolantThermalConductivity[i] * coolantNusseltNumber[i] / \
                                                     hydraulicDiameter[i]
            adiabaticConvectiveResistance = 1 / (adiabaticConvectiveHeatTransferCoef[i] * heatedArea[i])

            adiabaticHeatTransfer[i] = (constantColdWallTemperature - coolantTemperature[i]) / (adiabaticConvectiveResistance)

            if i > 0:
                coolantTemperature[i-1] = downstreamTemperature(coolantEnthalpy[i],
                                                                adiabaticHeatTransfer[i],
                                                                coolantPressure[i-1])
            if iterationMode == 'single':
                coolantTemperature[i] = downstreamTemperature(coolantEnthalpy[i],
                                                              adiabaticHeatTransfer[i],
                                                              coolantPressure[i])

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
        heatTransferOutputs = {
            'coolantPressure':     coolantPressure,
            'coolantTemperature':  coolantTemperature,
            'hotWallTemperature':  hotWallTemperature,
            'coldWallTemperature': coldWallTemperature
        }
        plotOutputs = {
            'xHotWall3D'                        : xHotWall3D,
            'rHotWall3D'                        : rHotWall3D,
            'temperature'                       : coolantTemperature,
            'pressure'                          : coolantPressure,
            'wallTemperature'                   : hotWallTemperature,
            'velocity'                          : coolantVelocity,
            'machNumber'                        : coolantMachNumber,
            'heatTransfer'                      : heatTransfer,
            'density'                           : coolantDensity,
            'viscosity'                         : coolantViscosity,
            'specificHeat'                      : coolantSpecificHeat,
            'nusseltNumber'                     : coolantNusseltNumber,
            'exhaustConvectiveHeatTransferCoef' : exhaustConvectiveHeatTransferCoef,
            'coolantConvectiveHeatTransferCoef' : coolantConvectiveHeatTransferCoef,
            'reynoldsNumber'                    : coolantReynoldsNumber,
            'radiativeHeatTransfer'             : radiativeHeatTransfer,
            'drivingTemperature'                : drivingTemperature
        }

    else:
        heatTransferOutputs = {
            'coolantPressure':     coolantPressure,
            'coolantTemperature':  coolantTemperature,
            'hotWallTemperature':  hotWallTemperature,
            'coldWallTemperature': coldWallTemperature
        }
        plotOutputs = {
            'xHotWall3D'                          : xHotWall3D,
            'rHotWall3D'                          : rHotWall3D,
            'temperature'                         : coolantTemperature,
            'pressure'                            : coolantPressure,
            'specificHeat'                        : coolantSpecificHeat,
            'adiabaticConvectiveHeatTransferCoef' : adiabaticConvectiveHeatTransferCoef
        }

    # Plots
    if plots and context.plotsEnabled == 'on':
        if not runAdiabaticColdWall:
            regenHeatTransferModelPlots(context, coolant=coolant, nChannel=nChannel,
                                        results=plotOutputs, family=channelType, titleFlare=titleFlare,
                                        xReference=xReference, rReference=rReference)
        else:
            regenHeatTransferModelPlots(context, coolant=coolant, nChannel=nChannel, adiabatic=True,
                                        results=plotOutputs, family=channelType, titleFlare=titleFlare,
                                        xReference=xReference, rReference=rReference)

    # Return
    if returnDict:
        return heatTransferOutputs, plotOutputs
