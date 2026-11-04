# -- NOVA: A Coolant Circuit of Its Own Over the Nozzle Extension -- #

'''

A second jacket over the nozzle extension, fed and drained apart from the chamber's.

Architecture D. The chamber jacket cools the chamber and the throat with its own coolant, entering
cold where the flux is highest, and a separate circuit takes the extension from the joint to an
area ratio further down the bell. Three engines show the range of what is done with its outlet:

- **Returned to the feed.** The SSME's nozzle circuit ran in parallel with its main chamber circuit
  and returned its hydrogen to the cycle.
- **Dumped as a film.** The Vulcain 2's upper nozzle is cooled by hydrogen that is then injected
  as a film over the lower nozzle, together with the turbine exhaust.
- **Dumped overboard.** The simplest, and the one that charges the engine's specific impulse the
  most, since the flow leaves with little thrust.

The circuit is one pass, coflow from the joint or counterflow from its far end, or two passes
down and back to the joint (the Agena's aft cone). Beyond its far end the extension is radiation
cooled, under the films that run over it.

**Method.** The circuit is the chamber jacket's sizing march run on the extension's own stations:
its wall, its gas, the drive the films ahead of it leave there, with its own coolant, flow, inlet
state and channel count. A two-pass circuit is coolantCircuit's two-pass solve on the same
stations. A dumped film enters the extension film solve as a slot at the circuit's outlet, with
the outlet's coolant, temperature and flow, and the drive past the circuit includes it.

The circuit sees the films that run over the extension ahead of its own outlet, not a film its
own outlet lays over it: with the outlet at the joint (counterflow or two pass) that film would run
over the circuit, and the coupling it makes, the outlet temperature setting the film that sets the
outlet temperature, is left out.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Each pass inherits the single-pass march's status** (regenThermal.py) and the two-pass
coupling's (coolantCircuit.py). What tests/testExtensionCircuit.py holds: a one-pass circuit is the
chamber march run on the extension's stations, station for station; a dumped film starts at the
circuit's outlet state; and the dumped flow enters the engine's flow. No measurement of a
separately cooled extension is available here.

All units are mass base SI:
    - Length [m]
    - Pressure [Pa]
    - Temperature [K]
    - Mass flow [kg/s]

Author: Sean Bowman

'''

import copy
from dataclasses import dataclass
from typing import Any

import numpy as np

from .channelGeometry import ChannelGeometryInputs
from .channelSizing import solveChannelRadii
from .coolantCircuit import solveCoolantCircuit
from .errors import InvalidInputError
from .geometryTools import sizedThroatRadius
from .validation import specified

__all__ = ['EXTENSIONOUTLETS', 'ExtensionCircuitState', 'ExtensionCircuitSolution',
           'extensionCircuitSpan', 'solveExtensionCircuit', 'radiativeRemainder',
           'extensionWallProfile']

EXTENSIONOUTLETS = ('return', 'film', 'overboard')

@dataclass
class ExtensionCircuitState:

    '''

    The extension's stations and the circuit's definition, seeded by name from the Nozzle.

    `channelSizingSolution` is the chamber jacket's solved sizing state, which carries the jacket
    settings the extension circuit shares: wall thicknesses, alloy, sizing mode and wall limit.

    '''

    channelSizingSolution:              Any = None
    numCSPointsChannel:                 Any = None
    xExtension:                         Any = None
    rExtension:                         Any = None
    gammaExtension:                     Any = None
    molecularWeightExtension:           Any = None
    gasConstantExtension:               Any = None
    extensionNearWallTemperature:       Any = None
    extensionNearWallRecoveryTemperature: Any = None
    extensionNearWallMachNumber:        Any = None
    extensionNearWallPressure:          Any = None
    extensionFilmDrivingTemperature:    Any = None
    nozzleScalingFactor:                Any = None
    extensionCircuitEndAreaRatio:       Any = None
    extensionCoolant:                   Any = None
    extensionCoolantMassFlow:           Any = None
    extensionCoolantInitialTemperature: Any = None
    extensionCoolantInitialPressure:    Any = None
    extensionChannelCount:              Any = None
    extensionCircuitPasses:             Any = None
    extensionCircuitDirection:          Any = None
    extensionCircuitOutlet:             Any = None
    material:                           Any = None
    voluteFOS:                          Any = None
    minVoluteWallThickness:             Any = None

@dataclass
class ExtensionCircuitSolution:

    '''

    The extension circuit, solved.

    Attributes:
    -----------
    stations : numpy.ndarray
        The extension stations it covers, from the joint.
    passes : int
        One or two.
    direction : str
        'coflow' or 'counterflow' for one pass; 'twoPass' for two.
    outlet : str
        'return', 'film' or 'overboard'.
    coolant : str
        Its coolant.
    massFlow : float
        Its flow [kg/s].
    sizing : Any
        The solved ChannelSizingState of a one-pass circuit, or the up pass of a two-pass one.
    circuit : Any
        The CircuitSolution of a two-pass circuit, None for one pass.
    outletAreaRatio : float
        Area ratio where the coolant leaves [-].

    '''

    stations:        np.ndarray
    passes:          int
    direction:       str
    outlet:          str
    coolant:         str
    massFlow:        float
    sizing:          Any
    circuit:         Any
    outletAreaRatio: float

    @property
    def outletTemperature(self) -> float:

        '''Coolant leaving the circuit [K].'''

        return float(self.sizing.coolantExitTemperature)

    @property
    def outletPressure(self) -> float:

        '''Coolant pressure leaving the circuit [Pa].'''

        return float(self.sizing.coolantExitPressure)

    @property
    def wallTemperature(self) -> np.ndarray:

        '''Hot wall over the circuit's stations: the hotter family's, for two passes [K].'''

        if self.circuit is None:
            return np.asarray(self.sizing.channelThermalResults['wallTemperature'])
        return np.maximum(np.asarray(self.circuit.down.results['wallTemperature']),
                          np.asarray(self.circuit.up.results['wallTemperature']))

    @property
    def dumpedMassFlow(self) -> float:

        '''Flow that leaves the engine rather than returning to the feed [kg/s].'''

        return 0.0 if self.outlet == 'return' else self.massFlow

    def report(self) -> str:

        '''A short text summary of the circuit.'''

        drop = float(self.sizing.coolantInitialPressure) - self.outletPressure if self.circuit is None \
            else float(self.circuit.down.state.coolantInitialPressure) - self.outletPressure
        inlet = float((self.circuit.down.state if self.circuit else self.sizing).coolantInitialTemperature)
        return (f'Extension circuit: {self.passes} pass{"es" if self.passes > 1 else ""} '
                f'({self.direction}) over {len(self.stations)} stations, {self.massFlow:.3g} kg/s of '
                f'{self.coolant} from {inlet:.0f} to {self.outletTemperature:.0f} K, '
                f'{1e-6*drop:.3f} MPa, outlet {self.outlet} at area ratio {self.outletAreaRatio:.3g}; '
                f'peak hot wall {self.wallTemperature.max():.0f} K')

def extensionCircuitSpan(xExtension, rExtension, nozzleScalingFactor, endAreaRatio: float) -> np.ndarray:

    '''

    The extension stations from the joint to the circuit's far end.

    Raises:
    -------
    InvalidInputError
        If the far end is not on the extension, or leaves the circuit fewer than four stations.

    '''

    rExtension = np.asarray(rExtension, dtype = float)
    areaRatio = (rExtension / sizedThroatRadius(rExtension, nozzleScalingFactor))**2
    if endAreaRatio is None or not np.isfinite(endAreaRatio) or not areaRatio[0] < endAreaRatio <= areaRatio[-1] * (1.0 + 1e-9):
        raise InvalidInputError(
            message = (f'The extension circuit runs from the joint at an area ratio of '
                       f'{areaRatio[0]:.3g} to a far end on the extension, which reaches '
                       f'{areaRatio[-1]:.3g}.'),
            parameterName = 'extensionCircuitEndAreaRatio', value = endAreaRatio,
            validRange = f'above {areaRatio[0]:.3g}, at most {areaRatio[-1]:.3g}')
    end = int(np.flatnonzero(areaRatio >= endAreaRatio * (1.0 - 1e-9))[0])
    if end < 3:
        raise InvalidInputError(
            message = 'The extension circuit covers fewer than four extension stations.',
            parameterName = 'extensionCircuitEndAreaRatio', value = endAreaRatio,
            validRange = 'further from the joint')
    return np.arange(end + 1)

def _sizingState(state: ExtensionCircuitState, stations: np.ndarray, direction: str):

    '''The chamber jacket's sizing state, moved onto the extension's stations and coolant.'''

    template = state.channelSizingSolution
    if template is None:
        raise InvalidInputError(
            message = 'An extension circuit shares the chamber jacket\'s settings, so the chamber '
                      'must have a jacket. Switch makeCoolingChannels on.',
            parameterName = 'makeCoolingChannels', value = None, validRange = 'on')
    sizing = copy.deepcopy(template)
    drive = (state.extensionFilmDrivingTemperature if state.extensionFilmDrivingTemperature is not None
             else None)
    arrays = {'xRegenNozzleTrimmed': state.xExtension, 'rRegenNozzleTrimmed': state.rExtension,
              'gammaRegenSectionTrimmed': state.gammaExtension,
              'molecularWeightRegenSectionTrimmed': state.molecularWeightExtension,
              'gasConstantRegenSectionTrimmed': state.gasConstantExtension,
              'regenSectionNearWallTemperatureTrimmed': state.extensionNearWallTemperature,
              'regenSectionNearWallRecoveryTemperatureTrimmed': state.extensionNearWallRecoveryTemperature,
              'regenSectionNearWallMachNumberTrimmed': state.extensionNearWallMachNumber,
              'regenSectionNearWallPressureTrimmed': state.extensionNearWallPressure,
              'regenSectionFilmDrivingTemperatureTrimmed': drive}
    for name, values in arrays.items():
        setattr(sizing, name, None if values is None else np.asarray(values, dtype = float)[stations])
    sizing.numCrossSections = len(stations)
    sizing.nChannel = int(state.extensionChannelCount)
    sizing.coolant = state.extensionCoolant
    sizing.coolantMassFlow = float(state.extensionCoolantMassFlow)
    sizing.coolantInitialTemperature = float(state.extensionCoolantInitialTemperature)
    sizing.coolantInitialPressure = float(state.extensionCoolantInitialPressure)
    sizing.jacketFlowDirection = direction
    sizing.gasSideAxialModel = 'uniform'
    sizing.gasCoefficientProfile = None
    sizing.channelSplitAreaRatio = None
    sizing.dcrData = {}
    # The chamber's manual profile is written for the chamber's stations; the extension circuit
    # is sized against the wall limit
    sizing.channelSizingMode = 'thermal'
    sizing.manualChannelProfile = None
    for name in ('pitchChannelCount', 'channelMassFlow', 'neighborCoolantTemperature',
                 'neighborCoolantCoefficient', 'neighborChannelRadius', 'ribFaceCount', 'stationRise'):
        setattr(sizing, name, None)
    return sizing

def solveExtensionCircuit(state: ExtensionCircuitState, thermal) -> ExtensionCircuitSolution:

    '''

    Solve the extension's own circuit.

    Parameters:
    -----------
    state : ExtensionCircuitState
        The extension, the circuit's definition and the chamber jacket it shares settings with.
    thermal : RegenThermalContext
        The thermal context.

    Returns:
    --------
    ExtensionCircuitSolution

    Raises:
    -------
    InvalidInputError
        For an incomplete definition, an unknown outlet, direction or pass count.

    '''

    required = ('extensionCircuitEndAreaRatio', 'extensionCoolantMassFlow',
                'extensionCoolantInitialTemperature', 'extensionCoolantInitialPressure',
                'extensionChannelCount')
    missing = [name for name in required if not specified(state, name)]
    if missing or not isinstance(state.extensionCoolant, str):
        raise InvalidInputError(
            message = 'An extension circuit needs a coolant, a flow, an inlet temperature and '
                      'pressure, a channel count and a far end.',
            parameterName = ', '.join(missing + ([] if isinstance(state.extensionCoolant, str)
                                                 else ['extensionCoolant'])),
            value = None, validRange = 'all given')
    outlet = state.extensionCircuitOutlet if isinstance(state.extensionCircuitOutlet, str) else 'return'
    passes = int(state.extensionCircuitPasses) if specified(state, 'extensionCircuitPasses') else 1
    direction = state.extensionCircuitDirection if isinstance(state.extensionCircuitDirection, str) else 'coflow'
    for name, value, valid in (('extensionCircuitOutlet', outlet, EXTENSIONOUTLETS),
                               ('extensionCircuitPasses', passes, (1, 2)),
                               ('extensionCircuitDirection', direction, ('coflow', 'counterflow'))):
        if value not in valid:
            raise InvalidInputError(
                message = 'The extension circuit is one pass, coflow or counterflow, or two; its '
                          'outlet is returned, dumped as a film, or dumped overboard.',
                parameterName = name, value = value, validRange = ' or '.join(map(str, valid)))

    stations = extensionCircuitSpan(state.xExtension, state.rExtension, state.nozzleScalingFactor,
                                    float(state.extensionCircuitEndAreaRatio))
    template = state.channelSizingSolution
    geometry = ChannelGeometryInputs(
        numCrossSections = len(stations), numCSPointsChannel = int(state.numCSPointsChannel or 24),
        nChannel = int(state.extensionChannelCount), channelType = 'circle',
        hotWallThickness = float(template.hotWallThickness), infillThickness = float(template.infillThickness))
    areaRatio = (np.asarray(state.rExtension, dtype = float)
                 / sizedThroatRadius(np.asarray(state.rExtension, dtype = float), state.nozzleScalingFactor))**2

    if passes == 1:
        sizing = solveChannelRadii(_sizingState(state, stations, direction), geometry, thermal)
        circuit = None
        outletStation = stations[-1] if direction == 'coflow' else stations[0]
    else:
        circuit = solveCoolantCircuit(_sizingState(state, stations, 'counterflow'), geometry, thermal,
                                      'twoPass', material = state.material,
                                      factorOfSafety = float(state.voluteFOS) if specified(state, 'voluteFOS') else 1.5,
                                      minWallThickness = (float(state.minVoluteWallThickness)
                                                          if specified(state, 'minVoluteWallThickness') else 0.0))
        sizing = circuit.up.state
        direction, outletStation = 'twoPass', stations[0]

    return ExtensionCircuitSolution(
        stations        = stations,
        passes          = passes,
        direction       = direction,
        outlet          = outlet,
        coolant         = state.extensionCoolant,
        massFlow        = float(state.extensionCoolantMassFlow),
        sizing          = sizing,
        circuit         = circuit,
        outletAreaRatio = float(areaRatio[outletStation]))

def radiativeRemainder(solution, stationCount: int) -> slice:

    '''

    The extension stations the radiative solve covers: all of them without a circuit, and from the
    circuit's far end on with one, the far end shared so the two walls meet.

    '''

    if solution is None:
        return slice(0, stationCount)
    return slice(int(solution.stations[-1]), stationCount)

def extensionWallProfile(xExtension, solution, radiativeTemperature) -> tuple:

    '''

    The extension's solved wall: the circuit's over its span, the radiative shell's beyond it.

    Parameters:
    -----------
    xExtension : array_like
        Extension stations [m].
    solution : ExtensionCircuitSolution | None
        The circuit, if there is one.
    radiativeTemperature : array_like | None
        The radiative shell's wall over its own stations [K], or None where it was not solved.

    Returns:
    --------
    tuple
        (x, wall temperature) for the friction march, or (None, None) with nothing solved.

    '''

    xExtension = None if xExtension is None else np.asarray(xExtension, dtype = float)
    if solution is None:
        if xExtension is None or radiativeTemperature is None:
            return None, None
        return xExtension, np.asarray(radiativeTemperature, dtype = float)
    xCircuit, wallCircuit = xExtension[solution.stations], solution.wallTemperature
    if radiativeTemperature is None:
        return xCircuit, wallCircuit
    remainder = radiativeRemainder(solution, len(xExtension))
    return (np.concatenate([xCircuit[:-1], xExtension[remainder]]),
            np.concatenate([wallCircuit[:-1], np.asarray(radiativeTemperature, dtype = float)]))
