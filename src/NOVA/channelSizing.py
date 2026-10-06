
# -- NOVA: Cooling Channel Sizing -- #

'''

Sizing a cooling channel so the wall it protects runs at the temperature it is allowed to.

The size solved for is the section's radial half-extent: a circle's radius, half a rectangle's
depth. It is not a free choice. At a fixed coolant flow a smaller channel carries the coolant
faster, which cools the wall harder and costs pressure; a larger one costs less pressure and runs
the wall hotter, until it no longer fits between its neighbors or will not print. What sets it
is the hot wall temperature, which is not known until the channel is drawn, the coolant marched
through it and the heat balance solved. So the size is solved for, station by station, marching
from the coolant inlet: the largest channel that holds the wall at its limit, which is also the
one with the least pressure drop.

At each station the loop proposes a size, rebuilds the cross section, runs the thermal model,
reads the hot wall temperature back, and steps again. It is a one-dimensional root find on a
monotone function: a larger channel runs its wall hotter, which tests/testRegenThermal.py holds a
rectangle's depth to. It is written as an adaptive secant with backtracking, overshoot damping
and a step fraction that ramps with the distance from target.

Four things bound the answer. The channel may not exceed the largest that fits between its
neighbors at that station, it may not reach past `maxChannelDepth` out from the wall, and it
may not fall below the minimum the process can build. The two upper bounds are not the same kind
of thing as the lower one. A channel held at an upper bound leaves the wall cooler than its
limit, which is a jacket with margin to spare, so the wall temperature there is whatever it
comes out as. A channel held at the lower bound with the wall still over its limit has nothing
left to try, because only a smaller channel cools harder, so that station stops the run.

The depth bound is the only thing limiting a circle's size apart from its neighbors, and it is
what keeps the search from filling the whole pitch on a wide bell: unset, the aft end of a
large nozzle takes a passage tens of millimeters across carrying coolant at walking pace. The
objective and the wall temperature constraint both improve as a channel grows, so nothing else
in the problem stops it.

What the coolant is worth when it leaves is checked separately, against
`minCoolantExitPressure` and `minCoolantExitTemperature`. A jacket can hold every wall at its
limit and still arrive with no pressure to inject with.

----------------------------------------------------------------------
                            Two ways to size
----------------------------------------------------------------------

The search above is one of two modes, named by `channelSizingMode`:

    thermal   The search. Every station converges its own half-extent against the wall
              temperature limit, at about seven passes of the thermal model per station.

    manual    The half-extent is read off a profile in channelProfile.py and the station is
              marched once. One pass of the thermal model per station, so the wall temperature,
              the pressure drop and the coolant exit state still come out; they are reported
              rather than converged to, and the wall runs wherever the geometry puts it.

The wall temperature limit is a constraint in the first and a yardstick in the second. A search
that cannot hold a station under it has failed at the job it was given and says so; a profile
that puts a station over it is a design decision the reader can see in the summary, which is why
the manual mode reports the margin rather than refusing. The coolant exit limits are checked in
both, because an unusable coolant condition is unusable however the geometry was arrived at.

The two share everything except how the half-extent at a station is arrived at: the same
centerline offset, the same wrap, the same cross sections and the same thermal model. What the
manual mode does not share is the search's tolerance for a bound. A profile is a statement about
geometry, so a station whose requested size will not fit between its neighbors, or falls below
the process minimum, stops the run and names the station rather than quietly building something
else. A channel count too high for its throat stops it too, where the search reduces the count
instead.

Every run records the profile it built, keyed on jacket fraction, so a search can be run once
and its answer replayed as a manual profile for every later run that changes something else.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Not validated, for want of anything to validate it against.** The result is a
converged fixed point of a geometry model and a thermal model, and no published case states a
channel radius distribution alongside the conditions that produced it. What can be said is
internal: the loop converges to the requested wall temperature within its stated tolerance where
the bounds allow, and reports the bound it hit where they do not.

The thermal model it converges against carries its own disclosures, which this inherits in
full. In particular the coolant-side correlation is unvalidated, so a channel sized against it
is sized against an unvalidated number, however tightly the loop converges.

The convergence is a hand-rolled search rather than a bracketed method. It has a fixed
iteration ceiling and a tolerance of one part in ten thousand of the target wall temperature,
and where it exhausts its iterations it says so rather than returning the last iterate
silently.

All units are mass base SI:
    - Length      [m]
    - Temperature [K]
    - Pressure    [Pa]
    - Mass flow   [kg/s]

Author: Sean Bowman

'''

from dataclasses import dataclass, field
from typing import Any

import math

import numpy as np
from scipy.interpolate import interp1d
from tqdm import tqdm

from .geometryTools import DCM, parallelOffset
from .errors import (ConvergenceFailureError, createErrorContext, GeometricConstraintError,
                     InvalidInputError, PressureDropError, ThermalConstraintError)
from .materials import wallMaterialCurves
from .channelGeometry import generateCrossSections as buildCrossSections
from .channelProfile import (CHANNELSIZINGMODES, evaluateProfile, profileConfigurationBlock,
                             profileDocument, readProfile, stationKeys)
from .channelSections import (depthLimitedHalfExtent, helicalSpacing, loxodromeWrap,
                              maxHalfExtent, rectangularWidth, throatChannelCount)
from .figures import regenHeatTransferModelPlots as drawRegenHeatTransfer
from .regenThermal import regenHeatTransferModel as solveRegenHeatTransfer

def _zeroIfUnset(value) -> float:

    '''A value that was never given, as the number zero rather than as an absence.'''

    if value is None:
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0

    return 0.0 if not math.isfinite(number) else number

def drivingTemperatureArray(state):

    """

    The gas temperature the heat flux is driven by, at every trimmed station.

    Two things can supply it, in order of precedence: a film coolant, which lowers it toward
    the coolant temperature over the length the film survives, and the recovery temperature,
    which is the adiabatic wall temperature convection into a wall is actually driven by.

    Parameters:
    -----------
    state : ChannelSizingState

    Returns:
    --------
    numpy.ndarray
        Driving temperature at each trimmed station [K].

    Raises:
    -------
    InvalidInputError
        If the recovery temperature was needed and the run did not produce one.

    """

    if state.regenSectionFilmDrivingTemperatureTrimmed is not None:
        return state.regenSectionFilmDrivingTemperatureTrimmed

    if state.regenSectionNearWallRecoveryTemperatureTrimmed is None:
        raise InvalidInputError(
            message = 'The run did not produce a recovery temperature. It is built alongside '
                      'the other near-wall properties, so a run that reached the jacket should '
                      'carry it.',
            parameterName = 'regenSectionNearWallRecoveryTemperatureTrimmed',
            value = None,
            validRange = 'one value per trimmed station')

    return state.regenSectionNearWallRecoveryTemperatureTrimmed

# The quantities the thermal model returns per station and the sizing loop carries through to the
# figure, each written into the full-length array at the station it was solved for.
THERMALPLOTKEYS = ('temperature', 'pressure', 'wallTemperature', 'velocity', 'machNumber',
                   'heatTransfer', 'density', 'viscosity', 'specificHeat', 'nusseltNumber',
                   'exhaustConvectiveHeatTransferCoef', 'coolantConvectiveHeatTransferCoef',
                   'reynoldsNumber', 'radiativeHeatTransfer', 'drivingTemperature')

@dataclass
class ChannelSizingState:

    '''

    Everything the sizing loop reads, and everything it produces.

    The constructor takes the engine, the coolant and the regen section the channels run along.
    Every output starts as None and is filled in by the solve, so an output still None afterwards
    means that branch was never reached, which is worth keeping rather than hiding behind a zero.

    Parameters:
    -----------
    channelType : str
        Cross-section family, one of channelSections.SECTIONFAMILIES. The sized quantity is the
        section's radial half-extent: a circle's radius, half a rectangle's depth.
    channelSizingMode : str
        'thermal' converges the half-extent against maxWallTemperature at every station.
        'manual' reads it off manualChannelProfile and marches each station once.
    manualChannelProfile : Any
        The profile the manual mode reads: a half-extent [m], a list of [key, half-extent]
        pairs, or a path to a recorded profile document. See channelProfile.
    manualChannelProfileKey : str
        Coordinate the profile's control points are keyed on, one of
        channelProfile.PROFILEKEYS. A recorded profile names its own and that one wins.
    gasSideAxialModel : str
        'uniform', 'measured' or 'ievlev', passed to the thermal model, which decides whether the
        gas-side correlation constant is held along the wall or follows the measured
        distribution. 'ievlev' arrives as `gasCoefficientProfile` instead.
    gasCoefficientProfile : array_like
        Gas-side coefficient at each trimmed station, solved over the whole wall [W/m^2 K]. None
        leaves each station to Bartz.
    nChannel : int
        Channels around the nozzle.
    numCrossSections : int
        Stations along the channel.
    minChannelRadius : float
        Smallest half-extent the process can build [m].
    minChannelWidth : float
        Narrowest rectangle the process can build [m]. The channel count is reduced to hold it
        at the throat.
    channelCornerRadius, maxChannelAspectRatio, maxChannelDepth : float
        A rectangle's corner radius [m], the depth it may reach as a multiple of its width [-],
        and the depth it may reach outright [m].
    channelHelixAngle, channelAspectRatio : float
        A helix's angle from the meridian [deg] and its depth as a multiple of its width [-].
    maxWallTemperature : float
        Hot wall temperature the loop converges to [K].
    minCoolantExitPressure, minCoolantExitTemperature : float
        What the coolant leaving the jacket has to be worth to the rest of the engine [Pa], [K].
        Each is checked after the march where the configuration set one, and ignored where it
        did not.
    hotWallThickness, infillThickness : float
        Wall between coolant and exhaust, and material left between neighbors [m].
    material : str
        Wall alloy, resolved by materials.wallMaterialCurves.
    coolant : str
        Coolant species.
    coolantMassFlow : float
        Total coolant flow through the jacket [kg/s].
    coolantInitialTemperature, coolantInitialPressure : float
        Coolant state at the jacket inlet [K], [Pa].
    chamberPressure : float
        Chamber stagnation pressure [Pa].
    theoreticalCharacteristicVelocity : float
        Characteristic velocity from the thermochemistry [m/s].
    nozzleScalingFactor : float
        Throat radius in real units [m].
    throatInletCurvatureNonDimensional, throatOutletCurvatureNonDimensional : float
        Throat arc radii, as multiples of the throat radius [-].
    xRegenNozzle, rRegenNozzle : Any
        Regen section wall, full [m].
    xRegenNozzleTrimmed, rRegenNozzleTrimmed : Any
        Regen section wall between the volute interfaces [m].
    gammaRegenSectionTrimmed, molecularWeightRegenSectionTrimmed : Any
        Exhaust gas properties at each trimmed station.
    gasConstantRegenSectionTrimmed : Any
        Specific gas constant at each trimmed station [J/kg K].
    regenSectionNearWallTemperatureTrimmed : Any
        Near-wall static exhaust temperature at each trimmed station [K].
    regenSectionNearWallRecoveryTemperatureTrimmed : Any
        Near-wall recovery temperature at each trimmed station [K]. This is the adiabatic
        wall temperature, and it is what the heat flux is actually driven by.
    regenSectionFilmDrivingTemperatureTrimmed : Any
        Driving temperature with a film coolant between the wall and the exhaust [K], or
        None where no film was asked for. When present it supersedes the recovery
        temperature, because it was built from it and is what the wall now sees.
    regenSectionNearWallMachNumberTrimmed : Any
        Near-wall Mach number at each trimmed station [-].
    regenSectionNearWallPressureTrimmed : Any
        Near-wall exhaust pressure at each trimmed station [Pa].
    dcrData : dict
        Working store the loop fills as it goes.

    '''

    # -- What the solve reads -- #
    channelType:                            str   = 'circle'
    channelSizingMode:                      str   = 'thermal'
    manualChannelProfile:                   Any   = None
    manualChannelProfileKey:                str   = 'areaRatio'
    gasSideAxialModel:                      str   = 'uniform'
    coolantGeometryCorrections:             bool  = False
    coolantRoughnessModel:                  str   = 'dippreySabersky'
    coolantPropertyCorrection:              str   = 'none'
    thermalBarrierThickness:                Any   = None
    thermalBarrierConductivity:             Any   = None
    channelSurfaceRoughness:                float = float('nan')
    nChannel:                               int   = 0
    numCrossSections:                       int   = 0
    minChannelRadius:                       float = 0.0
    minChannelWidth:                        float = 1.0e-3
    channelCornerRadius:                    float = 0.0
    maxChannelAspectRatio:                  float = 8.0
    maxChannelDepth:                        float = float('inf')
    channelHelixAngle:                      float = float('nan')
    channelAspectRatio:                     float = 1.0
    maxWallTemperature:                     float = float('nan')
    minCoolantExitPressure:                 Any   = None
    minCoolantExitTemperature:              Any   = None
    hotWallThickness:                       float = 0.0
    infillThickness:                        float = 0.0
    material:                               str   = 'GRCop-42'
    coolant:                                str   = ''
    coolantMassFlow:                        float = float('nan')
    coolantInitialTemperature:              float = float('nan')
    coolantInitialPressure:                 float = float('nan')
    chamberPressure:                        float = float('nan')
    theoreticalCharacteristicVelocity:      float = float('nan')
    nozzleScalingFactor:                    float = float('nan')
    throatInletCurvatureNonDimensional:     float = float('nan')
    throatOutletCurvatureNonDimensional:    float = float('nan')
    xRegenNozzle:                           Any   = None
    rRegenNozzle:                           Any   = None
    xRegenNozzleTrimmed:                    Any   = None
    rRegenNozzleTrimmed:                    Any   = None
    gammaRegenSectionTrimmed:               Any   = None
    molecularWeightRegenSectionTrimmed:     Any   = None
    gasConstantRegenSectionTrimmed:         Any   = None
    regenSectionNearWallTemperatureTrimmed: Any   = None
    regenSectionNearWallRecoveryTemperatureTrimmed: Any = None
    regenSectionFilmDrivingTemperatureTrimmed: Any = None
    regenSectionNearWallMachNumberTrimmed:  Any   = None
    regenSectionNearWallPressureTrimmed:    Any   = None
    # A gas-side coefficient solved over the whole wall, one per trimmed station [W/m^2 K]. Set
    # when the gas-side model carries the wall's history; None leaves each station to Bartz.
    gasCoefficientProfile:                  Any   = None
    dcrData:                                dict  = field(default_factory = dict)

    # -- What the solve produces -- #
    channelRadius:                          Any   = None   # [m], one per station
    channelWidth:                           Any   = None   # [m], one per station, rectangles and helices
    channelRibThickness:                    Any   = None   # [m], one per station, helices only
    channelWallTemperature:                 Any   = None   # [K], hot wall, one per station
    channelProfilePoints:                   Any   = None   # [-], [m], the profile built, keyed on jacket fraction
    coolantExitPressure:                    Any   = None   # [Pa]
    coolantExitTemperature:                 Any   = None   # [K]
    wallMaterialResolved:                   Any   = None   # the alloy actually used
    tempRangeKelvin:                        Any   = None   # [K], the grid the curves are sampled on
    wallThermalConductivityData:            Any   = None   # [W/m K]
    wallThermalConductivityInterpolator:    Any   = None
    wallCTEInterpolator:                    Any   = None
    wallYieldStrengthInterpolator:          Any   = None
    wallFractureStrainInterpolator:         Any   = None

# The outputs a solve hands back. Kept beside the class so that adding a field and forgetting to
# surface it is a one-line fix rather than a silent drop.
channelSizingOutputs = (
    'channelRadius', 'channelRibThickness', 'channelWidth', 'channelWallTemperature',
    'channelProfilePoints', 'nChannel', 'coolantExitPressure', 'coolantExitTemperature',
    'wallMaterialResolved', 'tempRangeKelvin', 'wallThermalConductivityData',
    'wallThermalConductivityInterpolator', 'wallCTEInterpolator',
    'wallYieldStrengthInterpolator', 'wallFractureStrainInterpolator')

def wallTemperatureLimit(state) -> float:

    '''

    The hot wall temperature the jacket is held to, checked before the solve reads it.

    One temperature for the whole jacket, not one per station. The search compares the wall
    against it every iteration and stops when the difference falls inside a tolerance taken
    from it, so a limit that is not a finite number makes every one of those comparisons
    false: the search leaves its first iteration immediately, every station keeps the largest
    channel that fits, and the run reports a jacket that was never checked against anything.
    Nothing in the output would say so, which is why this is checked rather than trusted.

    Parameters:
    -----------
    state : ChannelSizingState

    Returns:
    --------
    float
        The limit [K].

    Raises:
    -------
    InvalidInputError
        If the limit is absent, not a number, not finite, not a scalar, or not above zero.

    '''

    try:
        limit  = np.asarray(state.maxWallTemperature, dtype = float)
        usable = limit.ndim == 0 and bool(np.isfinite(limit)) and float(limit) > 0.0
    except (TypeError, ValueError):
        usable = False

    if not usable:
        raise InvalidInputError(
            message = 'The jacket is sized against one hot wall temperature limit, so '
                      'maxWallTemperature has to be a single finite temperature above zero. '
                      'A limit left unset does not size a jacket conservatively: it stops the '
                      'search from running at all.',
            parameterName = 'maxWallTemperature',
            value = state.maxWallTemperature,
            validRange = 'One finite value greater than 0 [K]')

    return float(limit)

def convergenceFailure(message: str, stationIndex: int, iterations: int, radius: float,
                       wallTemperature: float, targetTemperature: float, tolerance: float,
                       **extra) -> ConvergenceFailureError:

    '''

    The error a station raises when its size will not converge on the wall temperature.

    Built here rather than inline at the two places that raise it, so that the failure path can
    be constructed and tested on its own. Every quantity it reports is a scalar, the limit
    included: subscripting one of them raises from inside the handler and buries the failure it
    was reporting.

    Parameters:
    -----------
    message : str
        What failed, naming the station.
    stationIndex : int
        Station the search gave up at, in march order.
    iterations : int
        Iterations it used.
    radius : float
        Half-extent it ended on [m].
    wallTemperature, targetTemperature : float
        Wall it reached and the limit it was aiming at [K].
    tolerance : float
        Temperature tolerance convergence was judged against [K].
    extra : Any
        Anything else worth reporting from the site that raises, such as the bound it sat on or
        the coolant state it had reached.

    Returns:
    --------
    ConvergenceFailureError
        Ready to raise.

    '''

    residual = abs(float(wallTemperature) - float(targetTemperature))

    return ConvergenceFailureError(
        message = message,
        context = createErrorContext(
            stationIndex      = stationIndex,
            iterationCount    = iterations,
            channelRadius     = float(radius),
            wallTemperature   = float(wallTemperature),
            targetTemperature = float(targetTemperature),
            temperatureError  = residual,
            tempTolerance     = float(tolerance),
            **extra),
        iterations = iterations,
        tolerance  = float(tolerance),
        residual   = residual)

def wallTemperatureExceeded(stationIndex: int, wallTemperature: float, limit: float,
                            halfExtent: float, tolerance: float) -> ThermalConstraintError:

    '''

    The error a station raises when even its smallest channel leaves the wall over its limit.

    The wall temperature rises with channel size, so the smallest channel the process can build
    is the coolest wall that station can have. A wall over the limit there is not a search that
    needs more iterations: it is a jacket that cannot be built as specified, and the fix is more
    channels, a higher limit, more coolant, or a film.

    Parameters:
    -----------
    stationIndex : int
        Station that cannot be cooled, in march order from the coolant inlet.
    wallTemperature, limit : float
        Wall the smallest channel reached and the limit it had to meet [K].
    halfExtent : float
        Smallest half-extent the process can build at that station [m].
    tolerance : float
        Temperature tolerance the comparison allowed [K].

    Returns:
    --------
    ThermalConstraintError
        Ready to raise.

    '''

    return ThermalConstraintError(
        message = f'Station {stationIndex} reaches {float(wallTemperature):.1f} K at the '
                  f'{1e3*float(halfExtent):.3f} mm half-extent, which is the smallest the '
                  f'process can build, so no channel there holds the wall at its '
                  f'{float(limit):.1f} K limit. A smaller channel would cool harder and there '
                  f'is none to be had: the jacket needs more channels, a higher limit, more '
                  f'coolant flow, or a film over this station.',
        context = createErrorContext(
            stationIndex     = stationIndex,
            wallTemperature  = float(wallTemperature),
            minChannelRadius = float(halfExtent),
            tempTolerance    = float(tolerance)),
        thermalProperty = 'hotWallTemperature',
        value           = float(wallTemperature),
        limit           = float(limit))

def coolantPastWallLimit(stationIndex: int, coolantTemperature: float,
                         limit: float) -> ThermalConstraintError:

    '''

    The error the march raises when the coolant is no colder than the wall is allowed to be.

    The wall sits between the exhaust and the coolant, so it is always hotter than the coolant
    running behind it. Coolant that has reached the wall's temperature limit therefore puts the
    wall over that limit by itself, whatever size the channel is, and no station downstream can
    be cooled either.

    This is the other way a jacket fails the wall temperature limit. The first is geometric: the
    smallest channel the process can build still leaves the wall too hot. This one is thermal,
    and it is what a limit set below the coolant's own temperature produces. Left unchecked the
    march carries on with heat running from the coolant into the wall, which balances the station
    solve and cools the coolant, station after station, until the temperature leaves the range
    any property model can answer for.

    Parameters:
    -----------
    stationIndex : int
        Station whose coolant has reached the limit, in march order from the coolant inlet.
    coolantTemperature, limit : float
        Coolant leaving that station and the wall temperature limit [K].

    Returns:
    --------
    ThermalConstraintError
        Ready to raise.

    '''

    return ThermalConstraintError(
        message = f'The coolant leaves station {stationIndex} at '
                  f'{float(coolantTemperature):.1f} K, at or above the '
                  f'{float(limit):.1f} K the wall is limited to. The wall is always hotter than '
                  f'the coolant behind it, so no channel size holds it under that limit here or '
                  f'anywhere downstream. The limit has to sit above the coolant temperature the '
                  f'jacket reaches, which needs a higher limit, more coolant flow, or a shorter '
                  f'jacket.',
        context = createErrorContext(
            stationIndex           = stationIndex,
            coolantTemperature     = float(coolantTemperature),
            maxWallTemperature     = float(limit)),
        thermalProperty = 'coolantTemperature',
        value           = float(coolantTemperature),
        limit           = float(limit))

def checkCoolantExitState(state) -> None:

    '''

    Hold the coolant leaving the jacket to the pressure and temperature it was promised.

    The sizing solve minimizes the pressure drop subject to the wall temperature limit, so the
    drop is whatever the geometry leaves it as. Nothing in that makes the result usable: a
    jacket can hold every wall at its limit and still arrive at the injector with no pressure to
    inject with. These are the two limits that say what the rest of the engine needs, and each
    is checked only where the configuration set one.

    Parameters:
    -----------
    state : ChannelSizingState
        A solved state, with the coolant exit condition filled in.

    Raises:
    -------
    PressureDropError
        If the coolant leaves below minCoolantExitPressure.
    ThermalConstraintError
        If the coolant leaves below minCoolantExitTemperature.

    '''

    def limitOf(name):

        '''The limit a configuration set, or None where it left it unset.'''

        value = getattr(state, name, None)
        if value is None:
            return None
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None

        return value if np.isfinite(value) else None

    exitPressure    = float(state.coolantExitPressure)
    exitTemperature = float(state.coolantExitTemperature)
    inletPressure   = float(state.coolantInitialPressure)

    pressureLimit = limitOf('minCoolantExitPressure')
    if pressureLimit is not None and exitPressure < pressureLimit:
        raise PressureDropError(
            message = f'The coolant leaves the jacket at {1e-6*exitPressure:.3f} MPa, below the '
                      f'{1e-6*pressureLimit:.3f} MPa the configuration requires. It entered at '
                      f'{1e-6*inletPressure:.3f} MPa, so the jacket spent '
                      f'{1e-6*(inletPressure - exitPressure):.3f} MPa. Fewer channels, a larger '
                      f'maxChannelDepth or a higher inlet pressure buy it back.',
            pressureDrop    = inletPressure - exitPressure,
            exitPressure    = exitPressure,
            minExitPressure = pressureLimit)

    temperatureLimit = limitOf('minCoolantExitTemperature')
    if temperatureLimit is not None and exitTemperature < temperatureLimit:
        raise ThermalConstraintError(
            message = f'The coolant leaves the jacket at {exitTemperature:.1f} K, below the '
                      f'{temperatureLimit:.1f} K the configuration requires. The jacket picked '
                      f'up less heat than the cycle needs, so it wants a hotter wall limit, a '
                      f'longer jacket or less coolant through it.',
            thermalProperty = 'coolantExitTemperature',
            value           = exitTemperature,
            limit           = temperatureLimit)

def reportSizingResult(state, results: dict) -> None:

    '''

    Print what the jacket came out as, and the profile that would rebuild it.

    The summary is the same in both modes, because the same quantities decide whether a jacket
    is usable: the range of channel sizes, the hottest wall and its margin against the limit,
    and what the coolant leaves at. In the manual mode none of them were held, so the margin is
    the only thing that says whether the profile works.

    A thermal solve also prints the profile it converged to, as the configuration entries that
    replay it. That is the whole saving available: the search costs about seven passes of the
    thermal model per station and replaying its answer costs one.

    Parameters:
    -----------
    state : ChannelSizingState
        A solved state, with its profile and wall temperature filled in.
    results : dict
        The per-station thermal results, in nozzle order.

    '''

    wallTemperature = np.asarray(results['wallTemperature'], dtype = float)
    halfExtent      = np.asarray(state.channelRadius, dtype = float)
    limit           = float(np.max(state.maxWallTemperature))
    hottest         = int(np.argmax(wallTemperature))
    pressureDrop    = float(state.coolantInitialPressure) - float(state.coolantExitPressure)

    print(f'\nChannel sizing, {state.channelSizingMode} mode:')
    print(f'  half-extent {1e3*halfExtent.min():.3f} to {1e3*halfExtent.max():.3f} mm over '
          f'{state.numCrossSections} stations, {state.nChannel} channels')
    print(f'  peak hot wall {wallTemperature[hottest]:.1f} K at station {hottest}, '
          f'{wallTemperature[hottest] - limit:+.1f} K against the {limit:.1f} K limit')
    print(f'  coolant exit {float(state.coolantExitTemperature):.1f} K at '
          f'{1e-6*float(state.coolantExitPressure):.3f} MPa, jacket drop '
          f'{1e-6*pressureDrop:.3f} MPa')

    if state.channelSizingMode != 'thermal':
        return

    document = profileDocument(state.channelType, 'jacketFraction',
                               state.channelProfilePoints[:, 0], state.channelProfilePoints[:, 1])

    print('  the profile it converged to, which rebuilds this jacket without the search:')
    print(profileConfigurationBlock(document))

def solveChannelRadii(state, geometry, thermal):

    '''

    Solve the channel radius distribution along the regen section.

    Marches from the coolant inlet, converging the radius at each station so the hot wall reaches
    the requested temperature, subject to the largest channel that fits there and the smallest the
    process can build.

    Under `channelSizingMode = 'manual'` the radius is read off `manualChannelProfile` instead and
    each station is marched once, and a station the profile's size will not fit at stops the run.

    Parameters:
    -----------
    state : ChannelSizingState
        Engine, coolant and regen section. Its outputs are filled in and returned.
    geometry : ChannelGeometryInputs
        Channel definition the cross sections are rebuilt from at each proposed radius.
    thermal : RegenThermalContext
        Run-level settings the thermal model reads.

    Returns:
    --------
    ChannelSizingState
        The same state, with the radius distribution, the coolant exit condition and the wall
        property curves filled in. An output still None was never reached.

    '''

    # ------------------------------------------------------------------------------------------------------------------------------------ #
    # -- Private Methods -- #
    # ------------------------------------------------------------------------------------------------------------------------------------ #

    def findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i):

        '''

        This method uses the current station's guess for channel radius to find current station's channel centerline's 2D coordinates.
        Returns the current station's 2D channel centerline point (as an (x, r) pair), as well as the previous station's 2D channel
        centerline point (if i > 0) and a guess for the next station's 2D channel centerline point (if i < state.numCrossSections).

        '''

        channelOffsetDistance = state.hotWallThickness + channelRadius[i]

        match i:
            case 0:
                xChannelCenterline2D[:2], rChannelCenterline2D[:2] = parallelOffset(np.flip(xNozzle)[:2], np.flip(rNozzle)[:2], -channelOffsetDistance)
                return xChannelCenterline2D[:2], rChannelCenterline2D[:2]
            case _ if i == state.numCrossSections - 1:
                xChannelCenterline2D_temp, rChannelCenterline2D_temp = parallelOffset(np.flip(xNozzle)[:i+1], np.flip(rNozzle)[:i+1], -channelOffsetDistance)
                xChannelCenterline2D[-1], rChannelCenterline2D[-1] = xChannelCenterline2D_temp[-1], rChannelCenterline2D_temp[-1]
                return xChannelCenterline2D[i-1:i+1], rChannelCenterline2D[i-1:i+1]
            case _:
                xChannelCenterline2D_temp, rChannelCenterline2D_temp = parallelOffset(np.flip(xNozzle)[:i+2], np.flip(rNozzle)[:i+2], -channelOffsetDistance)
                xChannelCenterline2D[i:i+2], rChannelCenterline2D[i:i+2] = xChannelCenterline2D_temp[i:i+2], rChannelCenterline2D_temp[i:i+2]
                return xChannelCenterline2D[i-1:i+2], rChannelCenterline2D[i-1:i+2]

    def kineosAlgorithm_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, i,  findMaxRadius=False):

        '''

        This method generates the pathline angles for wrapping cooling channels around a rocket nozzle. Based on the current
        radius of the channel at the current station compared to the maximum radius the channel could be and still fit given
        an infill thickness and number of channel, a projection angle is calculated which represents the angle the channel
        would have to turn to ensure the circumferential space around the nozzle is filled. If the current channel radius is
        larger than the maximum radius of the channel that would fit, the radius is reduced so that it fits perfectly with no
        projection angle (straight channel).

        A rectangle fills its pitch by construction, so it runs straight: no projection and no
        wrap, and the largest it may be is set by its aspect ratio and depth limits. A helix
        follows the loxodrome laid out before the march, and the largest it may be is the widest
        that leaves the minimum rib in its pass spacing, within the depth limit.

        '''

        if state.channelType == 'helical':
            if findMaxRadius:
                return float(maxHalfExtent('helical', state.dcrData['passSpacing'][i] - state.infillThickness,
                                           state.channelAspectRatio, state.maxChannelDepth))
            state.dcrData['projectionAngle'][i] = np.deg2rad(state.channelHelixAngle)
            helixPath[i] = state.dcrData['helicalWrap'][i]
            if i < state.numCrossSections - 1:
                helixPath[i+1] = state.dcrData['helicalWrap'][i+1]
            state.dcrData['helixPath'][i] = helixPath[i]
            return helixPath, channelRadius

        if state.channelType == 'rectangular':
            if findMaxRadius:
                return float(maxHalfExtent('rectangular', state.dcrData['channelWidth'][i],
                                           state.maxChannelAspectRatio, state.maxChannelDepth))
            state.dcrData['projectionAngle'][i] = 0.0
            state.dcrData['helixPath'][i]       = helixPath[i]
            return helixPath, channelRadius

        def tryMakeFit(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, xPathline2D, rPathline2D, i, nozzleArcSlice):
            # use current arc slice to solve for max channel radius that fits here
            channelArcLength = nozzleArcSlice
            channelDiameter = 8*rPathline2D[1] * np.sin(channelArcLength / (8*rPathline2D[1]))
            channelRadius[i] = channelDiameter / 2
            # recalculate channel 2D centerline point here with new channel radius guess
            xPathline2D, rPathline2D = findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i)
            # rerun first half of the algo
            if i in (0, state.numCrossSections - 1):
                xPathline2D, rPathline2D = [np.concatenate(([0], arr)) for arr in (xPathline2D, rPathline2D)]

            # Calculate the distance between slices along the nozzle axis.
            xNozzleStep = xPathline2D[2] - xPathline2D[1]
            # Calculate the radial distance between slices from the nozzle axis.
            rNozzleStep = rPathline2D[2] - rPathline2D[1]

            # Calculate the arc length of the nozzle region allocated to each channel.
            nozzleArcSlice = 2*np.pi*rPathline2D[1]/nChannel - state.infillThickness

            # Calculate the arc length of the channel.
            channelArcLength = 4* rPathline2D[1] * np.arccos((2 * rPathline2D[1]**2 - (channelDiameter/4)**2) / (2 * rPathline2D[1]**2))

            return xNozzleStep, rNozzleStep, channelRadius[i], nozzleArcSlice, channelArcLength, xPathline2D, rPathline2D

        xPathline2D, rPathline2D = findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i)

        if i in (0, state.numCrossSections - 1):
            xPathline2D, rPathline2D = [np.concatenate(([0], arr)) for arr in (xPathline2D, rPathline2D)]

        # Calculate the distance between slices along the nozzle axis.
        xNozzleStep = xPathline2D[2] - xPathline2D[1]
        # Calculate the radial distance between slices from the nozzle axis.
        rNozzleStep = rPathline2D[2] - rPathline2D[1]

        # Calculate the arc length of the nozzle region allocated to each channel.
        nozzleArcSlice = 2*np.pi*rPathline2D[1]/nChannel - state.infillThickness

        # Calculate the diameter of each channel perpendicular to the pathline.
        channelDiameter = 2 * channelRadius[i]

        # Calculate the arc length of the channel.
        channelArcLength = 4* rPathline2D[1] * np.arccos((2 * rPathline2D[1]**2 - (channelDiameter/4)**2) / (2 * rPathline2D[1]**2))

        # smartRadii
        if findMaxRadius or channelArcLength > nozzleArcSlice:
            tolerance = 1e-9
            negativeTolerance = -1e-10
            maxIter = 50
            iteration = 0

            while True:
                diff = nozzleArcSlice - channelArcLength
                if diff < 0 and diff > negativeTolerance:
                    channelArcLength = nozzleArcSlice
                    diff = 0.0
                if diff < 0 or diff > tolerance:
                    xNozzleStep, rNozzleStep, channelRadius[i], nozzleArcSlice, channelArcLength, xPathline2D, rPathline2D = \
                        tryMakeFit(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, xPathline2D, rPathline2D, i, nozzleArcSlice)
                else:
                    if findMaxRadius:
                        # The room between neighbors is one of two limits on a circle. The other
                        # is the depth limit every family answers to, which is what stops a
                        # circle on a wide bell from filling its whole pitch.
                        return min(channelRadius[i], depthLimitedHalfExtent(state.maxChannelDepth))
                    else:
                        break
                iteration += 1
                if iteration > maxIter:
                    raise ValueError(
                        f"Convergence failed after {maxIter} iterations: "
                        f"nozzleArcSlice = {nozzleArcSlice:.9e}, "
                        f"channelArcLength = {channelArcLength:.9e}, "
                        f"diff = {diff:.3e}"
                    )

        # Calculate the projection angle required to make the channel cross-section
        # equivalent to the region of the nozzle allocated to it.
        projectionAngle = np.real(np.arccos(channelArcLength/nozzleArcSlice))
        state.dcrData['projectionAngle'][i] = projectionAngle

        # Calculate the arc length of channel movement in the x direction projected on the pathline.
        xArc = 2 * rPathline2D[1] * np.arccos((2*rPathline2D[1]**2 - ((xNozzleStep*np.tan(projectionAngle))/2)**2)/ (2 * rPathline2D[1]**2))

        # Calculate the arc length of channel movement in the r direction projected on the pathline.
        rArc = 2 * rPathline2D[1] * np.arccos((2*rPathline2D[1]**2 - ((rNozzleStep/np.tan(np.pi/2-projectionAngle))/2)**2)/ (2 * rPathline2D[1]**2))

        # Calculate the position of each pathline point projected on the nozzle wall in degrees.
        # Project the point from the previous axial slice to the next slice and then add
        # the arc length required to position the channel.

        if i == 0:
            helixPath[i] = 0
        elif i == state.numCrossSections - 1:
            helixPath[i] = ((helixPath[i-1] * rPathline2D[2]) - np.sqrt(xArc**2 + rArc**2)) / rPathline2D[2]
        else:
            helixPath[i] = ((helixPath[i-1] * rPathline2D[0]) - np.sqrt(xArc**2 + rArc**2)) / rPathline2D[0]

        # if 0 < i < state.numCrossSections - 1:
            helixPath[i+1] = ((helixPath[i] * rPathline2D[1]) - np.sqrt(xArc**2 + rArc**2)) / rPathline2D[1]

        state.dcrData['helixPath'][i] = helixPath[i]

        return helixPath, channelRadius

    def wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i):

        '''

        Uses kineosAlgorithm_oneStation() to wrap channel centerline around nozzle.
        Outputs the current station's 3D centerline point and a guess for the next station's 3D centerline point (if i < state.numCrossSections).

        '''

        helixPath, channelRadius = kineosAlgorithm_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, i)
        wrapAngle = helixPath[i]
        valueMatrix = [xChannelCenterline2D[i], rChannelCenterline2D[i], 0]
        eulerAngles = [wrapAngle, 0, 0]
        xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i] = DCM(eulerAngles, valueMatrix)

        state.dcrData['wrapAngles'][i] = wrapAngle

        if i < state.numCrossSections - 1:
            wrapAngle = helixPath[i+1]
            valueMatrix = [xChannelCenterline2D[i+1], rChannelCenterline2D[i+1], 0]
            eulerAngles = [wrapAngle, 0, 0]
            xChannelCenterline3D[i+1], yChannelCenterline3D[i+1], zChannelCenterline3D[i+1] = DCM(eulerAngles, valueMatrix)

            state.dcrData['wrapAngles'][i] = wrapAngle

            return xChannelCenterline3D[i:i+2], yChannelCenterline3D[i:i+2], zChannelCenterline3D[i:i+2], channelRadius

        return xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i], channelRadius

    def dcrGambit(heatTransferDict_i, heatTransferPlots, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, channelRadius, channelType, i):

        '''

        This wrapper functinalizes the process of generating the cross section and running regen heat transfer analysis at one station

        The heat transfer inputs and plots dictionary are taken in and returned updated.
        The hot wall temperature result is also returned as a scalar.

        '''

        # get local combustion properties
        heatTransferDict_i["xHotWall3D"]          = np.array([xNozzle                                     [state.numCrossSections - 1 - i]])
        heatTransferDict_i["rHotWall3D"]          = np.array([rNozzle                                     [state.numCrossSections - 1 - i]])
        heatTransferDict_i["hotWallSegmentLength"] = np.array([wallSegmentLength[i]])
        heatTransferDict_i["gamma"]               = np.array([state.gammaRegenSectionTrimmed               [state.numCrossSections - 1 - i]])
        heatTransferDict_i["molecularWeight"]     = np.array([state.molecularWeightRegenSectionTrimmed     [state.numCrossSections - 1 - i]])
        heatTransferDict_i["gasConstant"]         = np.array([state.gasConstantRegenSectionTrimmed         [state.numCrossSections - 1 - i]])
        heatTransferDict_i["nearWallMachNumber"]  = np.array([state.regenSectionNearWallMachNumberTrimmed  [state.numCrossSections - 1 - i]])
        heatTransferDict_i["nearWallTemperature"] = np.array([state.regenSectionNearWallTemperatureTrimmed [state.numCrossSections - 1 - i]])
        heatTransferDict_i["drivingTemperature"]  = np.array([drivingTemperatureArray(state)      [state.numCrossSections - 1 - i]])
        heatTransferDict_i["nearWallPressure"]    = np.array([state.regenSectionNearWallPressureTrimmed    [state.numCrossSections - 1 - i]])
        if state.gasCoefficientProfile is not None:
            heatTransferDict_i["prescribedGasCoefficient"] = np.array([state.gasCoefficientProfile[state.numCrossSections - 1 - i]])

        # get geometry properties for heat transfer
        # A helix's width follows the depth being tried, and its rib is what the pass spacing leaves
        channelWidth, ribThickness = state.dcrData.get('channelWidth'), None
        if channelType == 'helical':
            channelWidth = 2*channelRadius/state.channelAspectRatio
            ribThickness = state.dcrData['passSpacing'] - channelWidth

        heatTransferDict_iUpdate = \
            buildCrossSections(geometry, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D,
                                       channelRadius, channelType, i, channelWidth = channelWidth,
                                       ribThickness = ribThickness)

        # update local heat transfer dictionary
        heatTransferDict_i = heatTransferDict_i | heatTransferDict_iUpdate

        # run single station regen heat transfer model
        heatTransferOutputs, plotOutputs = solveRegenHeatTransfer(thermal, heatTransferDict_i, returnDict=True)
        # update local heat transfer dictionary
        # A wall limit is a limit on the metal, not on a ceramic coating over it: the point of a
        # barrier coating is that its own surface runs hotter than the metal behind it. Without a
        # coating the two are the same number, so an uncoated jacket converges on exactly what it
        # always did.
        hotWallTemperature                          = heatTransferOutputs.get(
            'metalWallTemperature', heatTransferOutputs['hotWallTemperature'])
        heatTransferDict_i['newCoolantTemperature'] = heatTransferOutputs['coolantTemperature'][0]
        heatTransferDict_i['newCoolantPressure']    = heatTransferOutputs['coolantPressure'][0]
        # update global plot outputs
        for key in THERMALPLOTKEYS:
            heatTransferPlots[key][state.numCrossSections - 1 - i] = plotOutputs[key][0]

        return heatTransferDict_i, heatTransferPlots, hotWallTemperature

    # ------------------------------------------------------------------------------------------------------------------------------------ #
    # -- Do The Thing -- #
    # ------------------------------------------------------------------------------------------------------------------------------------ #

    state.dcrData['projectionAngle'], state.dcrData['helixPath'], state.dcrData['wrapAngles'], \
    state.dcrData['minorLoss'], state.dcrData['frictionLoss'], state.dcrData['Kfactor'] = \
        [np.zeros((state.numCrossSections)) for _ in range(6)]

    # Locally scope nozzle wall values
    xNozzle, rNozzle = state.xRegenNozzleTrimmed, state.rRegenNozzleTrimmed

    # Meridional length of hot wall each station covers, in march order and on the convention
    # the channel path length uses: the segment to the next station, the last one repeated. The
    # gas-side area is taken from this rather than from the channel path, which is longer
    # wherever the channel wraps.
    wallSegmentLength = np.hypot(np.diff(np.flip(xNozzle)), np.diff(np.flip(rNozzle)))
    wallSegmentLength = np.append(wallSegmentLength, wallSegmentLength[-1])

    # Temperature-dependent wall alloy properties, sampled from
    # materials.wallMaterialCurves so the model is not tied to one alloy. The legacy
    # 'cu' / 'al' / 'in' keys still resolve, to GRCop-42 / AlSi10Mg / Inconel 718.
    # Conductivity and CTE are on the thermal-strain solution path; yield strength and
    # elongation are carried for downstream margin checks. Values are clamped at the
    # ends of each property's temperature grid rather than extrapolated.
    if True:
        state.wallThermalConductivityInterpolator = np.empty(state.numCrossSections, dtype=object)

        wallCurves                = wallMaterialCurves(state.material)
        state.wallMaterialResolved = wallCurves['material']
        wallTemperatureGrid       = wallCurves['temperatureK']

        def _clampedCurve(propertyArray):
            return interp1d(wallTemperatureGrid, propertyArray, kind='linear',
                            bounds_error=False, fill_value=(propertyArray[0], propertyArray[-1]))

        state.wallThermalConductivityInterpolator.fill(_clampedCurve(wallCurves['thermalConductivity']))
        state.wallYieldStrengthInterpolator  = _clampedCurve(wallCurves['yieldStrength'])
        state.wallFractureStrainInterpolator = _clampedCurve(wallCurves['elongation'])
        state.wallCTEInterpolator            = _clampedCurve(wallCurves['cte'])

        # Raw arrays retained for callers that plotted them directly.
        state.tempRangeKelvin           = wallTemperatureGrid
        state.wallThermalConductivityData = wallCurves['thermalConductivity']

    def prepareChannelLayout(nChannel):

        '''

        The channel count and the smallest half-extent the process can build, before the march.

        A count too high for the throat cannot be built: its channels there are narrower than the
        process minimum. The thermal mode reduces the count to the most that fit, which is the
        largest jacket it can then size. The manual mode refuses instead, because a profile was
        written against a count and silently changing the count changes the flow each channel
        carries and with it every number the profile was chosen for.

        The two wrapped families have their station geometry laid out here as well, since neither
        depends on the size being solved: a rectangle's width fills the pitch at the cold wall,
        and a helix's loxodrome and pass spacing follow from its angle.

        Parameters:
        -----------
        nChannel : int
            Channels, or helical starts, the configuration asked for.

        Returns:
        --------
        tuple
            The channel count to build with, and the smallest half-extent [m].

        Raises:
        -------
        GeometricConstraintError
            In the manual mode, if the channel count is too high for the throat.

        '''

        # The smallest half-extent the process can build. A helix is bounded by its width
        minHalfExtent = state.minChannelRadius
        if state.channelType == 'helical':
            minHalfExtent = 0.5*state.channelAspectRatio*state.minChannelWidth

        def refuseOrReduce(reason, fitted):

            '''Reduce the channel count to what fits, or refuse where a profile fixed it.'''

            if state.channelSizingMode == 'manual':
                raise GeometricConstraintError(
                    message = f'nChannel is {nChannel} and {reason} A manual profile is built '
                              f'against a fixed channel count, so the count is not reduced for '
                              f'you: {fitted} is the most that fit at the throat.',
                    constraintType = 'nChannel',
                    value = float(nChannel),
                    limit = float(fitted))

            print(f'\nnChannel too high; {reason}')
            state.nChannel = fitted
            print(f'\nnChannel reduced to {fitted}.')

            return fitted

        # first check if nChannel is too high and reduce if so
        if state.channelType == 'helical':
            throatRadius   = min(rNozzle)
            throatSpacing  = helicalSpacing(throatRadius + state.hotWallThickness, nChannel, state.channelHelixAngle)
            if throatSpacing - state.infillThickness < state.minChannelWidth:
                nChannel = refuseOrReduce(
                    'helical passes at the throat will be too narrow.',
                    throatChannelCount('helical', throatRadius, state.hotWallThickness,
                                       state.infillThickness, state.minChannelWidth,
                                       helixAngle = state.channelHelixAngle))

            # The loxodrome and the pass spacing along the cold wall, in march order
            xColdWall, rColdWall = parallelOffset(xNozzle, rNozzle, state.hotWallThickness)
            xColdWall, rColdWall = np.flip(xColdWall), np.flip(rColdWall)
            meridional = np.insert(np.cumsum(np.hypot(np.diff(xColdWall), np.diff(rColdWall))), 0, 0.0)
            state.dcrData['helicalWrap'] = loxodromeWrap(meridional, rColdWall, state.channelHelixAngle)
            state.dcrData['passSpacing'] = helicalSpacing(rColdWall, nChannel, state.channelHelixAngle)
        elif state.channelType == 'rectangular':
            throatRadius = min(rNozzle)
            throatWidth  = rectangularWidth(throatRadius + state.hotWallThickness, nChannel, state.infillThickness)
            if throatWidth < state.minChannelWidth:
                nChannel = refuseOrReduce(
                    'channel width at throat will be too small.',
                    throatChannelCount('rectangular', throatRadius, state.hotWallThickness,
                                       state.infillThickness, state.minChannelWidth))

            # The width at every station fills the pitch at the cold wall, which is the hot wall
            # offset by its thickness, so the rib at its root is the infill thickness. Held in
            # march order, which is the order every station array in the solve is written in.
            _, rColdWall = parallelOffset(xNozzle, rNozzle, state.hotWallThickness)
            state.dcrData['channelWidth'] = np.flip(rectangularWidth(rColdWall, nChannel, state.infillThickness))
        else:
            throatRadius = min(rNozzle)
            offsetHotWallThickness = state.hotWallThickness - state.infillThickness
            arcAngle = 2*np.pi / nChannel
            theta = arcAngle/2
            R = throatRadius + offsetHotWallThickness
            r = R*np.sin(theta) / (1 - np.sin(theta))
            circleChannelThroatRadius = r - state.infillThickness / 2
            if circleChannelThroatRadius < state.minChannelRadius:
                nChannel = refuseOrReduce(
                    'channel radius at throat will be too small.',
                    throatChannelCount(state.channelType, throatRadius, state.hotWallThickness,
                                       state.infillThickness, state.minChannelRadius))

        return nChannel, minHalfExtent

    def initialStationInputs():

        '''

        The run-level thermal inputs, and the arrays every station's result is written into.

        The thermal model is called one station at a time, so the dictionary it reads carries the
        run's scalars and a single station's arrays, and the station's own entries are written
        over it at each call. The plot arrays are full length and in nozzle order, which is the
        order the model's own figure and its coolant exit state are read in.

        Returns:
        --------
        tuple
            The station input dictionary, a copy of it before any station was written, and the
            full-length result arrays.

        '''

        # instantiate base dictionary
        heatTransferDict_i = {}
        # the local dictionary constains scalars and arrays of length 1
        heatTransferDict_i["numCrossSections"]                = 1
        heatTransferDict_i["channelType"]                     = state.channelType
        heatTransferDict_i["gasSideAxialModel"]               = state.gasSideAxialModel
        heatTransferDict_i["coolantGeometryCorrections"]      = state.coolantGeometryCorrections
        heatTransferDict_i["coolantRoughnessModel"]           = state.coolantRoughnessModel
        heatTransferDict_i["coolantPropertyCorrection"]       = state.coolantPropertyCorrection
        # A coating that was not asked for is zero thickness, not an absent number: the thermal
        # model guards its whole input dictionary against NaN, and an unset JSON key arrives here
        # as one.
        heatTransferDict_i["thermalBarrierThickness"]         = _zeroIfUnset(state.thermalBarrierThickness)
        heatTransferDict_i["thermalBarrierConductivity"]      = _zeroIfUnset(state.thermalBarrierConductivity)
        heatTransferDict_i["channelSurfaceRoughness"]         = state.channelSurfaceRoughness
        heatTransferDict_i["nChannel"]                        = state.nChannel
        heatTransferDict_i["hotWallThickness"]                = state.hotWallThickness
        heatTransferDict_i["throatRadiusOfCurvature"]         = (state.throatInletCurvatureNonDimensional*state.nozzleScalingFactor + \
                                                                 state.throatOutletCurvatureNonDimensional*state.nozzleScalingFactor) / 2
        heatTransferDict_i["throatDiameter"]                  = 2 * min(rNozzle)
        heatTransferDict_i["throatArea"]                      = np.pi * (min(rNozzle)**2)
        heatTransferDict_i["coolant"]                         = state.coolant
        heatTransferDict_i["mdot"]                            = state.coolantMassFlow / state.nChannel
        heatTransferDict_i["chamberPressure"]                 = state.chamberPressure
        heatTransferDict_i["coolantInitialTemperature"]       = state.coolantInitialTemperature
        heatTransferDict_i["coolantInitialPressure"]          = state.coolantInitialPressure
        heatTransferDict_i["theoreticalCharVel"]              = state.theoreticalCharacteristicVelocity

        baseHeatTransferDict = heatTransferDict_i.copy()

        # instantiate plot outputs dictionary
        heatTransferPlots = {}
        heatTransferPlots["xHotWall3D"] = xNozzle
        heatTransferPlots["rHotWall3D"] = rNozzle
        for key in THERMALPLOTKEYS:
            heatTransferPlots[key] = np.zeros(state.numCrossSections)

        return heatTransferDict_i, baseHeatTransferDict, heatTransferPlots

    # Create channel radii based on heat transfer
    def dynamicChannelRadii(maxWallTemperature, nChannel):

        '''

        Generate cooling channel radius distribution via heat transfer convergence.

        Marches along the nozzle in the direction of coolant flow, solving for the channel
        radius at each station that achieves the target wall temperature. At each station,
        an iterative convergence loop adjusts channel radius until wall temperature is within
        0.01% of the specified maximum. This approach simultaneously prevents wall overheating
        while minimizing pressure drop by using the largest channel radius that meets thermal
        constraints.

        ### Parameters

        | Parameter | Type | Description |
        |-----------|------|-------------|
        | `maxWallTemperature` | `float` | Hot wall temperature limit for the whole jacket [K] |
        | `nChannel` | `int` | Number of cooling channels |

        ### Returns

        `tuple` - Six-element tuple of arrays (all flipped to nozzle coordinate convention):

        | Element | Type | Description |
        |---------|------|-------------|
        | `channelRadius` | `np.ndarray` | Channel radius at each station [m] |
        | `xChannelCenterline2D` | `np.ndarray` | X coordinates of 2D centerline [m] |
        | `rChannelCenterline2D` | `np.ndarray` | Radial coordinates of 2D centerline [m] |
        | `xChannelCenterline3D` | `np.ndarray` | X coordinates of 3D centerline [m] |
        | `yChannelCenterline3D` | `np.ndarray` | Y coordinates of 3D centerline [m] |
        | `zChannelCenterline3D` | `np.ndarray` | Z coordinates of 3D centerline [m] |

        ### Notes

        - Validates nChannel against throat geometry; reduces automatically in normal mode.
        - Calls `dynamicConvergenceLoop_channelRadius()` at each station for radius optimization.
        - Uses `findChannelCenterline_oneStation()`, `kineosAlgorithm_oneStation()`, and
          `heatTransferModel_oneStation()` for stepwise geometry and thermal calculations.
        - Updates `state.dcrData` with channel heat transfer inputs and centerline coordinates.
        - Sets `state.coolantExitPressure` and `state.coolantExitTemperature`.
        - Generates diagnostic plots when `thermal.plotsEnabled == 'on'`.

        ---

        Author: Cam'ron Valliere
        Date:   2025

        '''

        nChannel, minHalfExtent = prepareChannelLayout(nChannel)

        # initialize arrays and values
        channelRadius = np.zeros(state.numCrossSections)
        xChannelCenterline2D, rChannelCenterline2D = [np.zeros((state.numCrossSections)) for _ in range(2)]
        helixPath = np.zeros(state.numCrossSections)
        xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D = [np.zeros((state.numCrossSections)) for _ in range(3)]

        # --------------------- Dynamic convergence loop for channelRadius --------------------- #
        def dynamicConvergenceLoop_channelRadius(channelRadius, nChannel, minChannelRadius, maxChannelRadius, i, heatTransferDict_i, heatTransferPlots, hotWallTemperature):

            '''

            Iteratively solve for channel radius that achieves target wall temperature at a station.

            Uses an adaptive step-sizing algorithm to find the channel radius that brings wall
            temperature within 0.01% of the target. Step size scales with error magnitude (larger
            steps when far from target, smaller when close). Includes backtracking for non-improving
            moves, overshoot damping when error sign flips, and a confirmation nudge at convergence
            to fine-tune the final value.

            ### Parameters

            | Parameter | Type | Description |
            |-----------|------|-------------|
            | `channelRadius` | `np.ndarray` | Channel radius array (modified in place) [m] |
            | `nChannel` | `int` | Number of cooling channels |
            | `minChannelRadius` | `float` | Minimum allowable channel radius [m] |
            | `maxChannelRadius` | `float` | Maximum allowable channel radius at this station [m] |
            | `i` | `int` | Station index to solve |

            ### Returns

            `int` - Convergence status:

            - Returns 1 on successful convergence (wall temp within 0.01% of target).
            - Returns 0 on failure due to excessive pressure drop, minimum radius reached,
              or iteration limit exceeded.

            ### Notes

            - Modifies `channelRadius[i]` and associated centerline coordinate arrays in place.
            - Updates `channelHeatTransferInputs[i]` with geometry for the converged radius.
            - Direction logic: if too hot, decrease radius; if too cold, increase radius.
            - Step fraction ramps from 0.01% (near target) to 40% (far from target).
            - Backtracking halves step size up to 6 times if error doesn't improve.
            - Overshoot damping halves next step when error sign flips.
            - Confirmation nudge (25% of last step) attempts to fine-tune within tolerance.

            ### Raises

            - `ConvergenceFailureError` - If minimum radius reached without convergence.
            - `ConvergenceFailureError` - If iteration limit exceeded without convergence.

            ---

            Author: Cam'ron Valliere
            Date:   2025

            '''

            # ---------- Dynamic step-sizing settings ---------- #
            targetToleranceFraction = 0.0001    # 0.01%
            tempTolerance = targetToleranceFraction * maxWallTemperature

            # Smooth ramp for step fraction; maps normalized error to change fraction
            minChangeFraction = 0.0001          # 0.01% step when very close to target
            maxChangeFraction = 0.40            # up to 40% when far from target
            maxNormalizedError = 100.0          # >100× tolerance : use max fraction

            # Backtracking & jitter control
            backtrackShrinkFactor = 0.5         # halve step if error did not improve
            maxBacktrackTries = 10
            lastStepConfirmationFraction = 0.25 # extra confirmation nudge size

            # For overshoot damping (reduce next step size after sign-flip)
            nextIterationStepFractionScale = 0.25
            nextIterationOvershootShrinkFactor = 0.25
            lastErrorSign = 0

            iterationsUsed = 0
            maxSolverIterations = 50

            # Start from current values
            currentRadius = channelRadius[i]
            currentWallTemp = hotWallTemperature
            currentError = currentWallTemp - maxWallTemperature

            while abs(currentError) > tempTolerance and iterationsUsed < maxSolverIterations:
                # Compute how many tolerances away we are, then smoothly map to a step fraction
                normalizedErrorMagnitude = abs(currentError) / max(tempTolerance, 1e-12)
                # smooth ramp clamp 0-1
                ramp = max(0.0, min(1.0, normalizedErrorMagnitude / maxNormalizedError))
                baseStepFraction = minChangeFraction + ramp * (maxChangeFraction - minChangeFraction)
                proposedStepFraction = baseStepFraction * nextIterationStepFractionScale

                # Decide direction: if too hot, decrease radius, if too cold, increase radius
                if currentError > 0.0:  # too hot
                    stepSign = -1
                else:  # too cold
                    stepSign = +1

                proposedStep = stepSign * proposedStepFraction * currentRadius
                proposedRadius = currentRadius + proposedStep

                # bounds
                minMaxed = False
                if proposedRadius > maxChannelRadius:
                    proposedRadius = maxChannelRadius
                    minMaxed = True
                if proposedRadius < minChannelRadius:
                    proposedRadius = minChannelRadius
                    minMaxed = True

                channelRadius[i] = proposedRadius

                # Wrap
                if i < state.numCrossSections - 1:
                    xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[0] if i == 0 else arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                    xChannelCenterline3D[i:i+2], yChannelCenterline3D[i:i+2], zChannelCenterline3D[i:i+2], channelRadius = \
                        wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)
                else:
                    xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                    xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i], channelRadius = \
                        wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)

                # if channelRadius was changed by smartRadii, make that the new max
                if channelRadius[i] != proposedRadius:
                    maxChannelRadius = channelRadius[i]
                    proposedRadius = maxChannelRadius

                heatTransferDict_i, heatTransferPlots, hotWallTemperature = \
                    dcrGambit(heatTransferDict_i, heatTransferPlots, \
                              xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, channelRadius, state.channelType, i)

                # Backtracking: if we didn’t improve error, shrink the step and retry from the previous radius
                backtrackCounter = 0
                newWallTemp = hotWallTemperature
                newError = newWallTemp - maxWallTemperature
                while abs(newError) >= abs(currentError) and backtrackCounter < maxBacktrackTries:
                    currentError = newError
                    proposedStep *= backtrackShrinkFactor
                    proposedRadius = currentRadius + proposedStep
                    # bounds
                    minMaxed = False
                    if proposedRadius > maxChannelRadius:
                        proposedRadius = maxChannelRadius
                        minMaxed = True
                    if proposedRadius < minChannelRadius:
                        proposedRadius = minChannelRadius
                        minMaxed = True

                    channelRadius[i] = proposedRadius

                    # Wrap
                    if i < state.numCrossSections - 1:
                        xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[0] if i == 0 else arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                        xChannelCenterline3D[i:i+2], yChannelCenterline3D[i:i+2], zChannelCenterline3D[i:i+2], channelRadius = \
                            wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)
                    else:
                        xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                        xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i], channelRadius = \
                            wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)

                    # if channelRadius was changed by smartRadii, make that the new max
                    if channelRadius[i] != proposedRadius:
                        maxChannelRadius = channelRadius[i]
                        proposedRadius = maxChannelRadius

                    heatTransferDict_i, heatTransferPlots, hotWallTemperature = \
                        dcrGambit(heatTransferDict_i, heatTransferPlots, \
                                  xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, channelRadius, state.channelType, i)

                    newWallTemp = hotWallTemperature
                    newError = newWallTemp - maxWallTemperature
                    backtrackCounter += 1

                    # A bound is the answer only when the wall is still on the far side of the
                    # target there: cold at the largest channel, hot at the smallest. Otherwise
                    # the root lies inside the bounds and the search goes on.
                    #
                    # The two bounds are not symmetric. Cold at the largest channel that fits is
                    # a jacket with margin to spare, which is a usable answer. Hot at the
                    # smallest channel the process can build is a wall over its limit with
                    # nothing left to try, because a smaller channel is the only thing that
                    # would cool it harder. That is refused rather than accepted.
                    atLargest = proposedRadius >= maxChannelRadius
                    if minMaxed and atLargest and newError < 0:
                        newError = 0
                    elif minMaxed and not atLargest and newError > 0:
                        if newError > tempTolerance:
                            raise wallTemperatureExceeded(i, newWallTemp, maxWallTemperature,
                                                          minChannelRadius, tempTolerance)
                        newError = 0

                # Overshoot / jitter damping: if error sign flipped, shrink next step size
                newErrorSign = np.sign(newError)
                if lastErrorSign != 0 and newErrorSign != 0 and newErrorSign != lastErrorSign:
                    nextIterationStepFractionScale *= nextIterationOvershootShrinkFactor
                lastErrorSign = newErrorSign

                # Accept the move
                currentRadius = proposedRadius
                currentWallTemp = newWallTemp
                currentError = newError
                iterationsUsed += 1

                # Early stop if we’re inside tolerance; do the extra confirmation nudge
                if abs(currentError) <= tempTolerance:
                    # Try a tiny additional move in the same helpful direction; keep it only if it improves error
                    confirmationStep = lastStepConfirmationFraction * proposedStep
                    trialRadius = currentRadius + confirmationStep
                    # bounds
                    minMaxed = False
                    if trialRadius > maxChannelRadius:
                        trialRadius = maxChannelRadius
                        minMaxed = True
                    if trialRadius < minChannelRadius:
                        trialRadius = minChannelRadius
                        minMaxed = True

                    channelRadius[i] = trialRadius

                    if i < state.numCrossSections - 1:
                        xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[0] if i == 0 else arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                        xChannelCenterline3D[i:i+2], yChannelCenterline3D[i:i+2], zChannelCenterline3D[i:i+2], channelRadius = \
                            wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)
                    else:
                        xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                        xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i], channelRadius = \
                            wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)

                    # if channelRadius was changed by smartRadii, make that the new max
                    if channelRadius[i] != trialRadius:
                        maxChannelRadius = channelRadius[i]
                        trialRadius = maxChannelRadius

                    heatTransferDict_i, heatTransferPlots, hotWallTemperature = \
                        dcrGambit(heatTransferDict_i, heatTransferPlots, \
                                  xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, channelRadius, state.channelType, i)

                    confirmationError = hotWallTemperature - maxWallTemperature

                    # Keep confirmation move only if it improved error
                    if abs(confirmationError) < abs(currentError):
                        currentRadius = channelRadius[i]
                        currentError = confirmationError
                    else:

                        channelRadius[i] = currentRadius  # revert

                        # rerun algos to get back old geometries and properties
                        if i < state.numCrossSections - 1:
                            xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[0] if i == 0 else arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                            xChannelCenterline3D[i:i+2], yChannelCenterline3D[i:i+2], zChannelCenterline3D[i:i+2], channelRadius = \
                                wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)
                        else:
                            xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                            xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i], channelRadius = \
                                wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)

                        heatTransferDict_i, heatTransferPlots, hotWallTemperature = \
                            dcrGambit(heatTransferDict_i, heatTransferPlots, \
                                      xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, channelRadius, state.channelType, i)

                        break  # done at this station

            # If we exited due to iteration cap and radius is at minimum, terminate with fail state
            if iterationsUsed >= maxSolverIterations and currentRadius <= minChannelRadius:
                raise convergenceFailure(
                    f'Minimum channel radius reached at station {i} without achieving '
                    f'temperature convergence',
                    stationIndex      = i,
                    iterations        = iterationsUsed,
                    radius            = currentRadius,
                    wallTemperature   = hotWallTemperature,
                    targetTemperature = maxWallTemperature,
                    tolerance         = tempTolerance,
                    minChannelRadius  = float(minChannelRadius))

            # If we exited due to iteration cap without convergence, terminate with fail state
            if abs(hotWallTemperature - maxWallTemperature) > tempTolerance and iterationsUsed >= maxSolverIterations and not minMaxed:
                raise convergenceFailure(
                    f'Temperature convergence failed at station {i} after '
                    f'{maxSolverIterations} iterations',
                    stationIndex       = i,
                    iterations         = iterationsUsed,
                    radius             = currentRadius,
                    wallTemperature    = hotWallTemperature,
                    targetTemperature  = maxWallTemperature,
                    tolerance          = tempTolerance,
                    coolantPressure    = heatTransferDict_i['coolantInitialPressure'],
                    coolantTemperature = heatTransferDict_i['coolantInitialTemperature'])

            # Accept new coolant temperature and pressure as next station initial conditions.
            # Coolant that has reached the wall's own limit puts the wall over it by itself, so
            # it is caught here rather than carried into the next station's solve.
            if heatTransferDict_i['newCoolantTemperature'] >= maxWallTemperature:
                raise coolantPastWallLimit(i, heatTransferDict_i['newCoolantTemperature'],
                                           maxWallTemperature)
            heatTransferDict_i['coolantInitialTemperature'] = heatTransferDict_i['newCoolantTemperature']
            heatTransferDict_i['coolantInitialPressure']    = heatTransferDict_i['newCoolantPressure']

            return heatTransferDict_i
        # -------------------------------------------------------------------------------------- #

        heatTransferDict_i, baseHeatTransferDict, heatTransferPlots = initialStationInputs()

        # find max channel radius at each station
        for i in tqdm(range(state.numCrossSections), desc="Solving for channel radii", colour="#ABD038"):

            maxChannelRadius = kineosAlgorithm_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, i, findMaxRadius=True)

            # next station will always start at last station's converged radius
            if i == 0:
                channelRadius[i] = maxChannelRadius
            else:
                channelRadius[i] = channelRadius[i-1]
            if channelRadius[i] > maxChannelRadius:
                channelRadius[i] = maxChannelRadius
            if channelRadius[i] < minHalfExtent:
                channelRadius[i] = minHalfExtent

            # Wrap
            if i < state.numCrossSections - 1:
                xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[0] if i == 0 else arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                xChannelCenterline3D[i:i+2], yChannelCenterline3D[i:i+2], zChannelCenterline3D[i:i+2], channelRadius = \
                    wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)
            else:
                xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i], channelRadius = \
                    wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)

            heatTransferDict_i, heatTransferPlots, hotWallTemperature = \
                dcrGambit(heatTransferDict_i, heatTransferPlots, \
                        xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, channelRadius, state.channelType, i)

            heatTransferDict_i = dynamicConvergenceLoop_channelRadius(channelRadius, nChannel, minHalfExtent, maxChannelRadius, i, heatTransferDict_i, heatTransferPlots, hotWallTemperature)

        # The station loop marches from the coolant inlet, and each station is written
        # into heatTransferPlots reversed, at N - 1 - i. That puts the inlet at the last
        # index and the exit at the first, which is the convention the model's own
        # summary uses when it reports a pressure drop. Reading the last index instead
        # returned the inlet state under the name of the exit state, and the outlet
        # volute is sized from it: the wall thickness comes from the GRCop yield strength
        # at that temperature, and a cryogenic inlet temperature reports a far higher
        # yield strength than the warm exit the volute actually sees.
        state.coolantExitPressure    = heatTransferPlots['pressure'][0]
        state.coolantExitTemperature = heatTransferPlots['temperature'][0]

        return np.flip(channelRadius), np.flip(xChannelCenterline3D), np.flip(yChannelCenterline3D), np.flip(zChannelCenterline3D), \
            heatTransferPlots, baseHeatTransferDict

    # Build the channel at the size a profile already decided
    def manualChannelRadii(maxWallTemperature, halfExtent, profileKey, keyName, nChannel):

        '''

        Lay the channel out at the half-extent a manual profile asks for.

        The same march as the thermal mode, with the search taken out: each station takes its
        size from the profile, is wrapped, and is handed to the thermal model once. Nothing is
        adjusted afterwards, so the wall temperature, the pressure drop and the coolant exit
        state are results rather than targets.

        A station whose requested size will not fit between its neighbors, or falls below the
        smallest the process can build, stops the run. The geometry would otherwise shrink the
        channel to what fits, which is the right answer for a search and the wrong one for a
        profile: it would build a jacket the configuration does not describe.

        Parameters:
        -----------
        maxWallTemperature : float
            The wall temperature limit. Nothing here holds the wall to it, and it is reported
            against rather than converged on. It still bounds the coolant: coolant that reaches
            it puts the wall over it whatever the channel size is.
        halfExtent : np.ndarray
            Radial half-extent the profile asks for at each station, in nozzle order [m].
        profileKey : np.ndarray
            The profile key at each station, in nozzle order, quoted in the message when a
            station's size is refused.
        keyName : str
            Name of that key, for the same message.
        nChannel : int
            Channels around the nozzle.

        Returns:
        --------
        tuple
            The half-extent distribution, the 3D centerline, the per-station thermal results
            and the run-level thermal inputs, on the same convention dynamicChannelRadii uses.

        Raises:
        -------
        GeometricConstraintError
            If the profile asks for a size a station cannot carry.

        '''

        nChannel, minHalfExtent = prepareChannelLayout(nChannel)

        # initialize arrays and values
        channelRadius = np.zeros(state.numCrossSections)
        xChannelCenterline2D, rChannelCenterline2D = [np.zeros((state.numCrossSections)) for _ in range(2)]
        helixPath = np.zeros(state.numCrossSections)
        xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D = [np.zeros((state.numCrossSections)) for _ in range(3)]

        heatTransferDict_i, baseHeatTransferDict, heatTransferPlots = initialStationInputs()

        def refuseStation(station, requested, bound, boundName, reason):

            '''Stop the run, naming the station and the bound the profile ran into.'''

            raise GeometricConstraintError(
                message = f'The manual channel profile asks for a {1e3*requested:.3f} mm '
                          f'half-extent at station {station} of {state.numCrossSections}, '
                          f'x = {1e3*xNozzle[station]:.1f} mm, {keyName} '
                          f'{profileKey[station]:.4g}. {reason} The {boundName} there is '
                          f'{1e3*bound:.3f} mm.',
                constraintType = 'channelRadius',
                value = float(requested),
                limit = float(bound))

        for i in tqdm(range(state.numCrossSections), desc = 'Building channel radii', colour = '#ABD038'):

            # The march runs from the coolant inlet, which is the last station in nozzle order.
            station   = state.numCrossSections - 1 - i
            requested = float(halfExtent[station])

            maxChannelRadius = kineosAlgorithm_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, i, findMaxRadius=True)

            if requested < minHalfExtent:
                refuseStation(station, requested, minHalfExtent, 'smallest the process can build',
                              'That is below the process minimum.')
            if requested > maxChannelRadius:
                refuseStation(station, requested, maxChannelRadius, 'largest that fits',
                              'That does not fit between its neighbors.')

            channelRadius[i] = requested

            # Wrap
            if i < state.numCrossSections - 1:
                xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[0] if i == 0 else arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                xChannelCenterline3D[i:i+2], yChannelCenterline3D[i:i+2], zChannelCenterline3D[i:i+2], channelRadius = \
                    wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)
            else:
                xChannelCenterline2D[i], rChannelCenterline2D[i] = (arr[1] for arr in findChannelCenterline_oneStation(xNozzle, rNozzle, channelRadius, xChannelCenterline2D, rChannelCenterline2D, i))
                xChannelCenterline3D[i], yChannelCenterline3D[i], zChannelCenterline3D[i], channelRadius = \
                    wrapSingleChannel_oneStation(xNozzle, rNozzle, channelRadius, nChannel, helixPath, xChannelCenterline2D, rChannelCenterline2D, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, i)

            # The wrap reduces a circular channel that fills more than its share of the
            # circumference rather than reporting it. The bound above is the fixed point of a
            # separate iteration, so a size right at it can still be nudged here, and a size
            # that moved by more than rounding is one the station will not carry.
            if abs(channelRadius[i] - requested) > 1e-9*requested:
                refuseStation(station, requested, channelRadius[i], 'largest that fits',
                              'The wrap could not lay that size on the wall.')

            heatTransferDict_i, heatTransferPlots, hotWallTemperature = \
                dcrGambit(heatTransferDict_i, heatTransferPlots, \
                          xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, channelRadius, state.channelType, i)

            # Accept new coolant temperature and pressure as next station initial conditions.
            # Coolant that has reached the wall's own limit puts the wall over it by itself, so
            # it is caught here rather than carried into the next station's solve.
            if heatTransferDict_i['newCoolantTemperature'] >= maxWallTemperature:
                raise coolantPastWallLimit(i, heatTransferDict_i['newCoolantTemperature'],
                                           maxWallTemperature)
            heatTransferDict_i['coolantInitialTemperature'] = heatTransferDict_i['newCoolantTemperature']
            heatTransferDict_i['coolantInitialPressure']    = heatTransferDict_i['newCoolantPressure']

        # Nozzle order, so the exit is the first index. See the note in dynamicChannelRadii.
        state.coolantExitPressure    = heatTransferPlots['pressure'][0]
        state.coolantExitTemperature = heatTransferPlots['temperature'][0]

        return np.flip(channelRadius), np.flip(xChannelCenterline3D), np.flip(yChannelCenterline3D), np.flip(zChannelCenterline3D), \
            heatTransferPlots, baseHeatTransferDict

    if state.channelSizingMode not in CHANNELSIZINGMODES:
        raise InvalidInputError(
            message = 'The channel size is either converged against the wall temperature limit '
                      'or read off a profile.',
            parameterName = 'channelSizingMode',
            value = state.channelSizingMode,
            validRange = 'One of ' + ', '.join(repr(mode) for mode in CHANNELSIZINGMODES))

    # Checked in both modes: the search converges against it and the manual mode reports the
    # margin against it, and neither can say anything useful about a limit that is not a number.
    wallLimit = wallTemperatureLimit(state)

    if state.channelSizingMode == 'manual':
        profile     = readProfile(state.manualChannelProfile, state.manualChannelProfileKey,
                                  state.channelType)
        profileKey  = stationKeys(profile.keyName, xNozzle, rNozzle)
        marchResult = manualChannelRadii(wallLimit, evaluateProfile(profile, profileKey),
                                         profileKey, profile.keyName, state.nChannel)
    else:
        marchResult = dynamicChannelRadii(wallLimit, state.nChannel)

    channelRadius, xChannelCenterline3D, yChannelCenterline3D, zChannelCenterline3D, heatTransferPlots, heatTransferDict \
        = marchResult

    state.channelRadius = channelRadius.copy()
    if state.channelType == 'rectangular':
        state.channelWidth = np.flip(state.dcrData['channelWidth'])
    elif state.channelType == 'helical':
        state.channelWidth        = 2*channelRadius/state.channelAspectRatio
        state.channelRibThickness = np.flip(state.dcrData['passSpacing']) - state.channelWidth

    # The wall the jacket held, station by station. In the thermal mode this is the target
    # wherever the search converged and the bound wherever it did not; in the manual mode it is
    # the whole result, since nothing held it anywhere.
    state.channelWallTemperature = heatTransferPlots['wallTemperature'].copy()

    # The profile this run built, keyed on the fraction along the jacket rather than on area
    # ratio: a constant radius barrel holds one area ratio over its whole length, so only the
    # fraction can carry the variation along it. Stations are respaced by arc length before the
    # jacket is laid out, so a profile recorded here replays at any station count.
    state.channelProfilePoints = np.column_stack(
        [stationKeys('jacketFraction', xNozzle, rNozzle), state.channelRadius])

    reportSizingResult(state, heatTransferPlots)

    # Reported first, then checked, so a run that fails on its coolant exit condition still
    # says what jacket it built before it says why that jacket is not usable.
    checkCoolantExitState(state)

    # Heat transfer plots, on the same switch the thermal model's own figures answer to. The
    # title says which mode drew them, because a wall that sits below its limit means a converged
    # bound in one and a profile in the other.
    if thermal.plotsEnabled == 'on' or thermal.export == 'on':
        titleFlare = (', manual profile results' if state.channelSizingMode == 'manual'
                      else ', dcr( ) results')
        drawRegenHeatTransfer(thermal, coolant=state.coolant, nChannel=state.nChannel,
                              results=heatTransferPlots, family=state.channelType,
                              titleFlare=titleFlare, xReference=state.xRegenNozzle, rReference=state.rRegenNozzle,
                              wallTemperatureLimit=state.maxWallTemperature)

    return state
