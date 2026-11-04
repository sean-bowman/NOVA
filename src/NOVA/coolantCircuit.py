# -- NOVA: Multi-Pass Coolant Circuits -- #

'''

A jacket whose coolant runs down one family of channels and back up another.

Four ways to carry a jacket's coolant are in use, and the first three are solved here:

| Circuit | Name | Coolant path | Where it fits | Heritage |
| --- | --- | --- | --- | --- |
| `singlePass` | A. Single pass | In at the jacket's aft end, up every channel to the injector | Small chambers, and wherever a manifold at the aft end is acceptable | SSME nozzle tubes, NERVA |
| `oneAndHalfPass` | B. One and a half pass | In at a manifold partway down the bell, down one family to a turnaround at the aft end, up the other to the injector; forward of the manifold every channel runs up | Hydrogen, which must be warmed before it reaches the throat; upper stages | J-2 (180 tubes down, 360 up), RL10 |
| `twoPass` | C. Two pass | In at the injector end, down one family to a turnaround at the aft end, up the other | Large tube-wall boosters, which keep both manifolds forward of the gimbal | F-1 (alternating tubes, 70 percent of the fuel) |

The fourth, a separate circuit over the extension (D), is solved in extensionCircuit.py.

**Two passes in one jacket.** The two families alternate around the circumference, so at each
station the wall's pitch is shared by every channel of both passes and each pass holds its own
share of the hot wall. Each pass is marched by the same sizing march as a single pass, in the
direction its coolant runs, with its own flow per channel; the pitch they share is the bound on
both. The up pass starts where the down pass ends, less the turnaround's loss.

**The rib between them.** Neighbors of the two passes carry coolant at different temperatures,
and the warmer hands heat to the colder through the rib between them,

    G = 1 / (1 / (h_1 a) + t / (k a) + 1 / (h_2 a))

per rib face (regenThermal.ribExchangeConductance). A down channel has two up neighbors; an up
channel has two down neighbors at a 1:1 ratio and one at 1:2, so the faces each channel presents
are counted per pass and the heat the two passes exchange balances. Since each pass's march needs
the other's coolant along the whole wall, the two are solved in turn, each on the other's last
profile, until neither moves by more than a tolerance (Gauss-Seidel, as the Ievlev outer
iteration in regenChannels is solved).

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Unvalidated as a circuit.** Each pass inherits the single-pass march's validation status
(regenThermal.py); no measurement of a two-pass jacket's wall or coolant temperatures is available
here. What tests/testCoolantCircuit.py holds are the identities the coupling rests on: with the
rib exchange switched off the passes are two independent marches; the heat the two coolants take
on together is the heat the wall passes them; the rib heat one pass gains the other loses, to the
iteration tolerance; the turnaround's loss is charged once and its turn keeps the coolant's
enthalpy; and the flow splits between the families in the ratio asked for. The rib conductance
runs 2 to 40 percent above a two-dimensional conduction solve of the web between two circular
channels (validation/coolingCircuits/phase4), the most for large channels at high coolant
coefficients.

All units are mass base SI:
    - Length [m]
    - Pressure [Pa]
    - Temperature [K]
    - Mass flow [kg/s]
    - Power [W]

Author: Sean Bowman

'''

import copy
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .channelSizing import solveChannelRadii
from .errors import ConvergenceFailureError, InvalidInputError, createErrorContext
from .fluidProperties import fluidProps
from .geometryTools import sizedThroatRadius
from .turnaround import DEFAULTVELOCITYRATIO, Turnaround, sizeTurnaround

__all__ = ['COOLANTCIRCUITS', 'PassSolution', 'CircuitSolution', 'passStations', 'passCounts',
           'solveCoolantCircuit']

COOLANTCIRCUITS = ('singlePass', 'oneAndHalfPass', 'twoPass')

# The station arrays a sizing state carries along the jacket, which a pass takes its span of
_STATIONARRAYS = ('xRegenNozzleTrimmed', 'rRegenNozzleTrimmed', 'gammaRegenSectionTrimmed',
                  'molecularWeightRegenSectionTrimmed', 'gasConstantRegenSectionTrimmed',
                  'regenSectionNearWallTemperatureTrimmed',
                  'regenSectionNearWallRecoveryTemperatureTrimmed',
                  'regenSectionFilmDrivingTemperatureTrimmed',
                  'regenSectionNearWallMachNumberTrimmed', 'regenSectionNearWallPressureTrimmed',
                  'gasCoefficientProfile')

@dataclass
class PassSolution:

    '''

    One pass of a multi-pass jacket, solved.

    Attributes:
    -----------
    name : str
        'down' or 'up'.
    stations : numpy.ndarray
        The jacket stations the pass covers, in wall order, injector face first.
    channelCount : int
        Channels of this pass.
    channelMassFlow : float
        Flow of one of its channels [kg/s].
    ribFaces : float
        Rib faces each of its channels presents to the other pass [-].
    state : Any
        The solved ChannelSizingState of the pass, its arrays on its own stations.

    '''

    name:            str
    stations:        np.ndarray
    channelCount:    int
    channelMassFlow: float
    ribFaces:        float
    state:           Any

    @property
    def results(self) -> dict:

        '''The pass's station results, wall order on its own stations.'''

        return self.state.channelThermalResults

@dataclass
class CircuitSolution:

    '''

    A multi-pass jacket, solved.

    Attributes:
    -----------
    circuit : str
        'oneAndHalfPass' or 'twoPass'.
    down, up : PassSolution
        The two passes.
    turnaround : Turnaround
        The ring the coolant turns in at the aft end.
    iterations : int
        Passes of the outer iteration.
    history : list
        Largest coolant temperature change at each pass of it [K].

    '''

    circuit:    str
    down:       PassSolution
    up:         PassSolution
    turnaround: Turnaround
    iterations: int
    history:    list = field(default_factory = list)

    @property
    def coolantExitTemperature(self) -> float:

        '''Coolant leaving the jacket at the injector end [K].'''

        return float(self.up.state.coolantExitTemperature)

    @property
    def coolantExitPressure(self) -> float:

        '''Coolant pressure leaving the jacket [Pa].'''

        return float(self.up.state.coolantExitPressure)

    def ribHeatBalance(self) -> tuple:

        '''Rib heat the down pass gains and the up pass gains, over all their channels [W].'''

        down = float(np.sum(self.down.results['ribHeatTransfer'])) * self.down.channelCount
        up = float(np.sum(self.up.results['ribHeatTransfer'])) * self.up.channelCount
        return down, up

    def report(self) -> str:

        '''A short text summary of the two passes and the turnaround.'''

        downDrop = float(self.down.state.coolantInitialPressure - self.down.state.coolantExitPressure)
        upDrop = float(self.up.state.coolantInitialPressure - self.up.state.coolantExitPressure)
        downRib, upRib = self.ribHeatBalance()
        return '\n'.join([
            f'Coolant circuit {self.circuit}, solved in {self.iterations} passes '
            f'(last change {self.history[-1]:.3f} K)',
            f'  down: {self.down.channelCount} channels at {1e3*self.down.channelMassFlow:.2f} g/s each, '
            f'{float(self.down.state.coolantInitialTemperature):.1f} to '
            f'{float(self.down.state.coolantExitTemperature):.1f} K, {1e-6*downDrop:.3f} MPa',
            f'  turnaround: {1e3*self.turnaround.sectionRadius:.1f} mm section radius, '
            f'{1e-3*self.turnaround.pressureDrop:.1f} kPa',
            f'  up: {self.up.channelCount} channels at {1e3*self.up.channelMassFlow:.2f} g/s each, '
            f'{float(self.up.state.coolantInitialTemperature):.1f} to '
            f'{float(self.up.state.coolantExitTemperature):.1f} K, {1e-6*upDrop:.3f} MPa',
            f'  rib exchange: down gains {1e-3*downRib:.2f} kW, up gains {1e-3*upRib:.2f} kW'])

def passStations(circuit: str, xWall, rWall, nozzleScalingFactor, inletAreaRatio = None) -> tuple:

    '''

    The stations each pass covers, wall order, injector face first.

    The up pass runs the whole jacket. The down pass runs it too in a two-pass circuit, and from
    the inlet manifold to the aft end in a one-and-a-half-pass circuit, the manifold sitting
    where the diverging wall reaches `inletAreaRatio`.

    Returns:
    --------
    tuple
        (down stations, up stations), each an integer array.

    Raises:
    -------
    InvalidInputError
        For an unknown circuit, or a one-and-a-half-pass inlet off the diverging jacket.

    '''

    stations = np.arange(len(xWall))
    if circuit == 'twoPass':
        return stations, stations
    if circuit != 'oneAndHalfPass':
        raise InvalidInputError(
            message = 'A multi-pass circuit is one-and-a-half pass or two pass.',
            parameterName = 'coolantCircuit', value = circuit,
            validRange = "'oneAndHalfPass' or 'twoPass'")
    if inletAreaRatio is None or not np.isfinite(inletAreaRatio) or inletAreaRatio <= 1.0:
        raise InvalidInputError(
            message = 'A one-and-a-half-pass circuit takes its coolant in partway down the bell, at '
                      'an area ratio above one.',
            parameterName = 'coolantInletAreaRatio', value = inletAreaRatio, validRange = 'above 1')
    rWall = np.asarray(rWall, dtype = float)
    areaRatio = (rWall / sizedThroatRadius(rWall, nozzleScalingFactor))**2
    throat = int(np.argmin(rWall))
    past = np.flatnonzero((stations > throat) & (areaRatio >= inletAreaRatio))
    if past.size == 0 or past[0] >= len(stations) - 3:
        raise InvalidInputError(
            message = (f'The inlet manifold at an area ratio of {inletAreaRatio:.3g} leaves no jacket '
                       f'for the down pass, which ends at {areaRatio[-1]:.3g}.'),
            parameterName = 'coolantInletAreaRatio', value = inletAreaRatio,
            validRange = f'well below {areaRatio[-1]:.3g}')
    return stations[past[0]:], stations

def passCounts(upChannelCount: int, passChannelRatio: float) -> tuple:

    '''

    Channels of each pass, and the rib faces each channel presents to the other pass.

    `upChannelCount` is the jacket's channel count, the channels reaching the injector. The down
    pass has `passChannelRatio` of them: one for 1:1 alternation (F-1), one half for the J-2's 180
    down to 360 up. Every down channel sits between two up channels; an up channel has two down
    neighbors at 1:1 and one at 1:2.

    Returns:
    --------
    tuple
        (down count, up count, down faces, up faces).

    '''

    if passChannelRatio not in (1.0, 0.5):
        raise InvalidInputError(
            message = 'The passes alternate one down to one up, or one down to two up.',
            parameterName = 'passChannelRatio', value = passChannelRatio, validRange = '1 or 0.5')
    downCount = int(round(upChannelCount * passChannelRatio))
    if downCount * round(1.0 / passChannelRatio) != upChannelCount:
        raise InvalidInputError(
            message = 'At one down to two up the jacket channel count must be even.',
            parameterName = 'nChannel', value = upChannelCount, validRange = 'even')
    return downCount, upChannelCount, 2.0, 2.0 * downCount / upChannelCount

def stationTemperatures(leaving, direction: str, inletTemperature: float) -> tuple:

    '''

    A pass's coolant at the middle of each station, and its rise over the station.

    The march records the coolant leaving each station. What enters a station is what left the one
    before it in the direction the coolant runs, or the inlet for the first.

    Parameters:
    -----------
    leaving : array_like
        Coolant leaving each station, wall order [K].
    direction : str
        'coflow' for a pass running toward the aft end, 'counterflow' toward the injector.
    inletTemperature : float
        Coolant entering the pass [K].

    Returns:
    --------
    tuple
        (mid-temperature, rise), each in wall order [K].

    '''

    leaving = np.asarray(leaving, dtype = float)
    entering = np.empty_like(leaving)
    if direction == 'coflow':
        entering[0], entering[1:] = inletTemperature, leaving[:-1]
    else:
        entering[-1], entering[:-1] = inletTemperature, leaving[1:]
    return 0.5 * (entering + leaving), leaving - entering

def _passState(base, stations, direction: str, channelCount: int, channelMassFlow: float,
               pitchCount, inletTemperature: float, inletPressure: float):

    '''A copy of the jacket's sizing state, cut to a pass's stations and set to its flow.'''

    state = copy.deepcopy(base)
    for name in _STATIONARRAYS:
        values = getattr(state, name, None)
        if values is not None:
            setattr(state, name, np.asarray(values)[stations])
    state.numCrossSections = len(stations)
    state.jacketFlowDirection = direction
    state.nChannel = channelCount
    state.channelMassFlow = channelMassFlow
    state.pitchChannelCount = np.asarray(pitchCount, dtype = float)[stations]
    state.coolantInitialTemperature = inletTemperature
    state.coolantInitialPressure = inletPressure
    state.dcrData = {}
    state.neighborCoolantTemperature = None
    state.neighborCoolantCoefficient = None
    state.neighborChannelRadius = None
    state.stationRise = None
    return state

def _solvePass(template, geometry, thermal, neighborTemperature, neighborCoefficient,
               neighborRadius, faces, ownRise = None):

    '''Solve one pass on a fresh copy of its state, with the other pass's coolant beside it.'''

    state = copy.deepcopy(template)
    if neighborTemperature is not None:
        state.neighborCoolantTemperature = np.asarray(neighborTemperature, dtype = float)
        state.neighborCoolantCoefficient = np.asarray(neighborCoefficient, dtype = float)
        state.neighborChannelRadius = np.asarray(neighborRadius, dtype = float)
        state.stationRise = None if ownRise is None else np.asarray(ownRise, dtype = float)
    state.ribFaceCount = faces
    passGeometry = copy.deepcopy(geometry)
    passGeometry.numCrossSections = state.numCrossSections
    requested = state.nChannel
    solved = solveChannelRadii(state, passGeometry, thermal)
    if solved.nChannel != requested:
        raise InvalidInputError(
            message = (f'The sizing reduced a pass from {requested} to {solved.nChannel} channels to '
                       f'fit the throat, which would break the alternation of the two passes. Give '
                       f'the jacket fewer channels.'),
            parameterName = 'nChannel', value = requested, validRange = f'at most {solved.nChannel}')
    return solved

def solveCoolantCircuit(base, geometry, thermal, circuit: str, passChannelRatio: float = 1.0,
                        inletAreaRatio: float = None, material = None, factorOfSafety: float = 1.5,
                        minWallThickness: float = 0.0,
                        turnaroundVelocityRatio: float = DEFAULTVELOCITYRATIO,
                        tolerance: float = 0.05, maxIterations: int = 30,
                        ribExchange: bool = True) -> CircuitSolution:

    '''

    Solve a one-and-a-half-pass or two-pass jacket.

    Parameters:
    -----------
    base : ChannelSizingState
        The jacket as a single pass would be sized: its wall, gas, coolant, inlet state, total
        coolant flow `coolantMassFlow` and channel count `nChannel`, the channels that reach the
        injector.
    geometry : ChannelGeometryInputs
        The channel geometry inputs.
    thermal : RegenThermalContext
        The thermal context.
    circuit : str
        'oneAndHalfPass' or 'twoPass'.
    passChannelRatio : float
        Down channels per up channel, 1 or 0.5.
    inletAreaRatio : float | None
        Where a one-and-a-half-pass circuit's inlet manifold sits on the diverging wall.
    material : str | None
        Jacket alloy, for the turnaround's wall.
    factorOfSafety, minWallThickness : float
        For the turnaround's wall [-], [m].
    turnaroundVelocityRatio : float
        Turnaround turning velocity over the down channel velocity [-].
    tolerance : float
        Largest coolant temperature change between passes of the outer iteration [K].
    maxIterations : int
        Passes of the outer iteration.
    ribExchange : bool
        False solves the two passes with no heat between them.

    Returns:
    --------
    CircuitSolution

    Raises:
    -------
    ConvergenceFailureError
        If the outer iteration does not settle.

    '''

    from .nozzleVolutes import voluteYieldStrength

    xWall, rWall = np.asarray(base.xRegenNozzleTrimmed), np.asarray(base.rRegenNozzleTrimmed)
    downStations, upStations = passStations(circuit, xWall, rWall, base.nozzleScalingFactor,
                                            inletAreaRatio)
    downCount, upCount, downFaces, upFaces = passCounts(int(base.nChannel), float(passChannelRatio))
    totalFlow = float(base.coolantMassFlow)

    # Every channel of both passes shares the pitch where both run; forward of a
    # one-and-a-half-pass inlet the up channels have it to themselves
    pitchCount = np.full(len(xWall), float(upCount))
    pitchCount[downStations] = float(upCount + downCount)

    downTemplate = _passState(base, downStations, 'coflow', downCount, totalFlow / downCount,
                              pitchCount, float(base.coolantInitialTemperature),
                              float(base.coolantInitialPressure))

    history, upResults, downState, upState, ring = [], None, None, None, None
    downRise, upRise = None, None
    for iteration in range(1, maxIterations + 1):

        # Down the bell, beside the up pass's last profile
        neighbor = (None, None, None)
        if ribExchange and upResults is not None:
            upMid, upRise = stationTemperatures(upResults['temperature'], 'counterflow',
                                                float(upState.coolantInitialTemperature))
            neighbor = (upMid[downStations],
                        np.asarray(upResults['coolantConvectiveHeatTransferCoef'])[downStations],
                        np.asarray(upState.channelRadius)[downStations])
        downState = _solvePass(downTemplate, geometry, thermal, *neighbor, downFaces, downRise)
        downResults = downState.channelThermalResults
        downMid, downRise = stationTemperatures(downResults['temperature'], 'coflow',
                                                float(downState.coolantInitialTemperature))

        # The turn at the aft end, at the down pass's last station
        endTemperature, endPressure = float(downState.coolantExitTemperature), float(downState.coolantExitPressure)
        density = float(np.atleast_1d(fluidProps(base.coolant, 'TP', 'D', endTemperature, endPressure))[0])
        downRadius = float(np.asarray(downState.channelRadius)[-1])
        wallRadius = float(rWall[-1])
        upRadiusGuess = downRadius if upState is None else float(np.asarray(upState.channelRadius)[-1])
        ring = sizeTurnaround(
            channelMassFlow  = totalFlow / downCount,
            density          = density,
            downFlowArea     = np.pi * downRadius**2,
            upFlowArea       = np.pi * upRadiusGuess**2 * downCount / upCount,
            pitch            = 2.0 * np.pi * (wallRadius + float(base.hotWallThickness)) / (upCount + downCount),
            wallRadius       = wallRadius,
            axialPosition    = float(xWall[-1]),
            channelDepth     = 2.0 * max(downRadius, upRadiusGuess),
            hotWallThickness = float(base.hotWallThickness),
            pressure         = endPressure,
            yieldStrength    = voluteYieldStrength(material, endTemperature),
            factorOfSafety   = factorOfSafety,
            minWallThickness = minWallThickness,
            velocityRatio    = turnaroundVelocityRatio)

        # Back up the whole jacket, beside the down pass where it runs. The turn is adiabatic: the
        # coolant keeps its enthalpy and loses pressure, so it starts the up pass at the
        # temperature that enthalpy has at the lower pressure.
        upPressure = endPressure - ring.pressureDrop
        enthalpy = float(np.atleast_1d(fluidProps(base.coolant, 'TP', 'H', endTemperature, endPressure))[0])
        upTemperature = float(np.atleast_1d(fluidProps(base.coolant, 'PH', 'T', upPressure, enthalpy))[0])
        upTemplate = _passState(base, upStations, 'counterflow', upCount, totalFlow / upCount,
                                pitchCount, upTemperature, upPressure)
        neighborTemperature = np.full(len(xWall), np.nan)
        neighborCoefficient = np.zeros(len(xWall))
        neighborRadius = np.zeros(len(xWall))
        neighborTemperature[downStations] = downMid
        neighborCoefficient[downStations] = np.asarray(downResults['coolantConvectiveHeatTransferCoef'])
        neighborRadius[downStations] = np.asarray(downState.channelRadius)
        previous = None if upResults is None else np.asarray(upResults['temperature']).copy()
        upState = _solvePass(upTemplate, geometry, thermal,
                             neighborTemperature if ribExchange else None, neighborCoefficient,
                             neighborRadius, upFaces, upRise)
        upResults = upState.channelThermalResults

        change = (np.inf if previous is None
                  else float(np.max(np.abs(np.asarray(upResults['temperature']) - previous))))
        history.append(change)
        if not ribExchange or change < tolerance:
            break
    else:
        raise ConvergenceFailureError(
            message = (f'The two passes did not settle in {maxIterations} passes: the up coolant '
                       f'still moved {history[-1]:.3f} K on the last, against {tolerance} K, after '
                       f'{", ".join(f"{change:.3f}" for change in history[-4:])} K on the last four. '
                       f'A strongly coupled pair, a hot up pass beside a cold down pass, settles '
                       f'slowly; more passes or a looser tolerance close it.'),
            context = createErrorContext(circuit = circuit, history = history),
            iterations = maxIterations, tolerance = tolerance, residual = history[-1])

    return CircuitSolution(
        circuit    = circuit,
        down       = PassSolution('down', downStations, downCount, totalFlow / downCount, downFaces, downState),
        up         = PassSolution('up', upStations, upCount, totalFlow / upCount, upFaces, upState),
        turnaround = ring,
        iterations = iteration,
        history    = history)
