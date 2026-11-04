# -- NOVA: Estimated and Delivered Nozzle Performance -- #

'''

What the nozzle was expected to deliver before the solve, and what the solved flow delivers.

Two kinds of number describe a nozzle's performance and they answer different questions.

**The one-dimensional estimate** treats the exit as a single uniform, axial state at the area
ratio. It is what sizes the engine: the requested thrust is turned into a mass flow through CEA's
matched-expansion specific impulse at the area ratio, before any contour exists. It is reported in
two gases. CEA's equilibrium gas is the thermochemistry's own answer. The frozen chamber gas, one
ratio of specific heats from the chamber, is the gas the method of characteristics is solved in,
so it is the like-for-like reference for what the contour delivers.

**The delivered value** is integrated over the solved exit plane, station by station, in the gas
the characteristics carried: a non-uniform, non-axial plane whose momentum and pressure are what
the nozzle actually produces. The plane is integrated once, against no back pressure, and the
coefficient at any ambient follows from it exactly,

    C_F(p_a) = C_F,vac - p_a A_e / (p_c A_t)

which is why each back pressure here is named rather than implied. The solve's own objective, the
plane against `targetExitPressure`, is one of them: with only an area ratio given, that pressure
is the one-dimensional equilibrium exit pressure, which is also the back pressure the requested
thrust was sized at, so the delivered thrust there is the one to set against the request.

The ratio of the delivered vacuum coefficient to the chamber-gas estimate is the nozzle's own
efficiency: divergence and non-uniformity of the exit, with the gas held the same on both sides.
Friction is charged separately, as the wall drag the boundary layer march returns over the throat
force, and both the inviscid and the friction-corrected values are reported.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**The one-dimensional chamber-gas relations are closed form** and are tested as identities: the
coefficient reproduces u_e/c* + eps p_e/p_c, and the specific impulse C_F c*/g.

**The delivered integral is verified against that closed form.** A uniform, axial exit plane at
the one-dimensional Mach number integrates to the one-dimensional vacuum coefficient, which
`tests/testPerformance.py` holds to the quadrature error of the plane's own resolution. The
departure of a solved plane from that reference is the contour's efficiency and is a result, not
an error.

**What is not validated** is the solve itself: the method of characteristics' exit plane is
cross-checked against an inviscid finite-volume solution of the shipped nozzle in
`validation/openFoam`, which is a cross-check rather than a validation. The equilibrium estimate
inherits CEA's validation in `tests/testCeaInterface.py`.

All units are mass base SI:
    - Pressure    [Pa]
    - Temperature [K]
    - Velocity    [m/s]
    - Force       [N]
    - Impulse     [s]

Author: Sean Bowman

'''

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from . import units
from .gasDynamics import machFromAreaRatio
from .validation import specified

__all__ = ['PerformanceSummary', 'chamberGasEstimate', 'summarizePerformance', 'SEALEVELPRESSURE']

SEALEVELPRESSURE = 101325.0                       # [Pa], standard atmosphere at sea level

@dataclass
class PerformanceSummary:

    '''

    Estimated and delivered performance of one solved nozzle.

    The one-dimensional estimates carry the suffix `Equilibrium` (CEA's gas) or `ChamberGas` (the
    frozen chamber gas the characteristics are solved in); delivered values carry `Delivered`.
    Thrust coefficients and specific impulses at a back pressure are held in dictionaries keyed by
    the back pressure's name, with the pressures themselves in `backPressures`.

    Attributes:
    -----------
    areaRatio : float
        Exit area over throat area [-].
    backPressures : dict
        Named back pressures [Pa]: 'vacuum', 'seaLevel', 'design' (the solve's
        targetExitPressure) and, when a plume ambient is set, 'ambient'.
    exitMach*, exitPressure*, exitTemperature*, exitVelocity* : float
        Exit state [-], [Pa], [K], [m/s]. Delivered values are mass averages over the plane;
        `exitPressureAreaAveraged` and the `*Wall` values are reported beside them.
    characteristicVelocity* : float
        Characteristic velocity [m/s].
    thrustCoef* : dict
        Thrust coefficient at each named back pressure [-].
    specificImpulse* : dict
        Specific impulse at each named back pressure [s].
    thrustDelivered, thrustDeliveredFrictionCorrected : dict
        Thrust at each named back pressure [N]: the engine's mass flow, which the sized throat
        passes, times the delivered specific impulse. The plane's own impulse is used rather than
        its coefficient on the throat area, so the mass the march loses on the way to the exit
        does not read as lost thrust.
    requestedThrust : float
        The thrust the engine was sized for, at the design back pressure [N].
    nozzleEfficiency : float
        Delivered vacuum coefficient over the chamber-gas estimate [-].
    frictionThrustCoef : float
        Wall drag over the throat force, the coefficient friction costs [-]. Zero when the
        boundary layer march did not run.
    exitMassClosure : float
        Mass through the exit plane over the one-dimensional choked throat flow [-].

    '''

    areaRatio:                      float
    backPressures:                  dict

    exitMachEquilibrium:            float
    exitMachChamberGas:             float
    exitMachDelivered:              float
    exitMachWall:                   float
    exitPressureEquilibrium:        float
    exitPressureChamberGas:         float
    exitPressureDelivered:          float
    exitPressureAreaAveraged:       float
    exitPressureWall:               float
    exitTemperatureEquilibrium:     float
    exitTemperatureChamberGas:      float
    exitTemperatureDelivered:       float
    exitVelocityEquilibrium:        float
    exitVelocityChamberGas:         float
    exitVelocityDelivered:          float

    characteristicVelocityEquilibrium: float
    characteristicVelocityChamberGas:  float

    thrustCoefEquilibrium:          dict = field(default_factory = dict)
    thrustCoefChamberGas:           dict = field(default_factory = dict)
    thrustCoefDelivered:            dict = field(default_factory = dict)
    thrustCoefDeliveredFrictionCorrected: dict = field(default_factory = dict)
    specificImpulseEquilibrium:     dict = field(default_factory = dict)
    specificImpulseChamberGas:      dict = field(default_factory = dict)
    specificImpulseDelivered:       dict = field(default_factory = dict)
    specificImpulseDeliveredFrictionCorrected: dict = field(default_factory = dict)
    thrustDelivered:                dict = field(default_factory = dict)
    thrustDeliveredFrictionCorrected: dict = field(default_factory = dict)

    requestedThrust:                float = float('nan')
    nozzleEfficiency:               float = float('nan')
    frictionThrustCoef:             float = 0.0
    exitMassClosure:                float = float('nan')

    def toDict(self) -> dict:

        '''Every field as plain Python numbers, ready for JSON.'''

        def plain(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: plain(item) for key, item in value.items()}
            if isinstance(value, (np.floating, np.integer)):
                return float(value)
            return value

        return {key: plain(value) for key, value in asdict(self).items()}

    def rows(self) -> list:

        '''

        The summary as table rows: (quantity, unit, equilibrium 1D, chamber gas 1D, delivered).

        A cell is None where the column has no value for that quantity.

        '''

        rows = [
            ('Exit Mach number', '-', self.exitMachEquilibrium, self.exitMachChamberGas,
             self.exitMachDelivered),
            ('Exit Mach number at the wall', '-', None, None, self.exitMachWall),
            ('Exit pressure', 'Pa', self.exitPressureEquilibrium, self.exitPressureChamberGas,
             self.exitPressureDelivered),
            ('Exit pressure, area averaged', 'Pa', None, None, self.exitPressureAreaAveraged),
            ('Exit pressure at the wall', 'Pa', None, None, self.exitPressureWall),
            ('Exit temperature', 'K', self.exitTemperatureEquilibrium,
             self.exitTemperatureChamberGas, self.exitTemperatureDelivered),
            ('Exit velocity', 'm/s', self.exitVelocityEquilibrium, self.exitVelocityChamberGas,
             self.exitVelocityDelivered),
            ('Characteristic velocity', 'm/s', self.characteristicVelocityEquilibrium,
             self.characteristicVelocityChamberGas, None),
        ]
        for name in self.backPressures:
            rows.append((f'Thrust coefficient, {_backPressureLabel(name, self.backPressures)}', '-',
                         self.thrustCoefEquilibrium.get(name), self.thrustCoefChamberGas.get(name),
                         self.thrustCoefDelivered.get(name)))
        for name in self.backPressures:
            rows.append((f'Specific impulse, {_backPressureLabel(name, self.backPressures)}', 's',
                         self.specificImpulseEquilibrium.get(name),
                         self.specificImpulseChamberGas.get(name),
                         self.specificImpulseDelivered.get(name)))
        return rows

    def report(self) -> str:

        '''A plain-text table of the summary, for the run's console output.'''

        def cell(value: Any) -> str:
            if value is None or not np.isfinite(value):
                return f'{"":>12}'
            magnitude = abs(value)
            text = f'{value:.0f}' if magnitude >= 1000.0 else f'{value:.4g}'
            return f'{text:>12}'

        lines = [f'Nozzle performance at an area ratio of {self.areaRatio:.3f}',
                 f'{"":44}{"1D equil.":>12}{"1D chamber":>12}{"delivered":>12}']
        for quantity, unit, equilibrium, chamberGas, delivered in self.rows():
            lines.append(f'  {quantity + " [" + unit + "]":<42}{cell(equilibrium)}{cell(chamberGas)}'
                         f'{cell(delivered)}')
        lines.append(f'  Nozzle efficiency, delivered over 1D chamber gas, vacuum: '
                     f'{self.nozzleEfficiency:.4f}')
        if self.frictionThrustCoef > 0.0:
            design = self.thrustDeliveredFrictionCorrected.get('design', float('nan'))
            lines.append(f'  Friction costs {self.frictionThrustCoef:.4f} of thrust coefficient; '
                         f'delivered thrust after friction at the design back pressure '
                         f'{design:.0f} N')
        lines.append(f'  Requested thrust {self.requestedThrust:.0f} N at the design back pressure; '
                     f'delivered {self.thrustDelivered.get("design", float("nan")):.0f} N inviscid')
        return '\n'.join(lines)

def _backPressureLabel(name: str, backPressures: dict) -> str:

    '''How a named back pressure reads in a table row.'''

    if name == 'vacuum':
        return 'vacuum'
    pressure = backPressures[name]
    words = {'seaLevel': 'sea level', 'design': 'design back pressure', 'ambient': 'plume ambient'}
    return f'{words.get(name, name)} ({pressure / 1e3:.2f} kPa)'

def chamberGasEstimate(areaRatio: float, gamma: float, gasConstant: float,
                       stagnationTemperature: float, chamberPressure: float) -> dict:

    '''

    The one-dimensional exit state and vacuum performance of a frozen, calorically perfect gas.

        M_e from the area-Mach relation,  p_e = p_c (1 + (g-1)/2 M_e^2)^(-g/(g-1))
        c* = sqrt(g R T_0) / (g (2/(g+1))^((g+1)/(2(g-1))))
        C_F,vac = u_e / c* + eps p_e / p_c,     Isp_vac = C_F,vac c* / g_0

    Parameters:
    -----------
    areaRatio : float
        Exit area over throat area [-].
    gamma, gasConstant : float
        Ratio of specific heats [-] and gas constant [J/kg-K].
    stagnationTemperature, chamberPressure : float
        Chamber stagnation state [K], [Pa].

    Returns:
    --------
    dict
        exitMach [-], exitPressure [Pa], exitTemperature [K], exitVelocity [m/s],
        characteristicVelocity [m/s], vacuumThrustCoef [-].

    '''

    exitMach = float(machFromAreaRatio(float(areaRatio), float(gamma), branch = 'supersonic'))
    temperatureRatio = 1.0 + 0.5 * (gamma - 1.0) * exitMach**2
    exitTemperature = stagnationTemperature / temperatureRatio
    exitPressure = chamberPressure * temperatureRatio**(-gamma / (gamma - 1.0))
    exitVelocity = exitMach * np.sqrt(gamma * gasConstant * exitTemperature)
    characteristicVelocity = np.sqrt(gamma * gasConstant * stagnationTemperature) / (
        gamma * (2.0 / (gamma + 1.0))**((gamma + 1.0) / (2.0 * (gamma - 1.0))))
    vacuumThrustCoef = exitVelocity / characteristicVelocity + areaRatio * exitPressure / chamberPressure

    return dict(exitMach = exitMach, exitPressure = float(exitPressure),
                exitTemperature = float(exitTemperature), exitVelocity = float(exitVelocity),
                characteristicVelocity = float(characteristicVelocity),
                vacuumThrustCoef = float(vacuumThrustCoef))

def summarizePerformance(source) -> PerformanceSummary:

    '''

    Build the estimated and delivered performance of a solved nozzle.

    Parameters:
    -----------
    source : Nozzle | Any
        A solved nozzle, read by attribute: the CEA output, the chamber gas, the exit-plane
        fields the contour solve wrote (`vacuumThrustCoef`, `exitPlaneAreaRatio`, the mass
        averages, `exitVacuumSpecificImpulse`), the throat area, the friction drag when the
        boundary layer march ran, and the plume ambient when one is set.

    Returns:
    --------
    PerformanceSummary

    '''

    gravity = units.GRAVITY
    chamberPressure = float(source.chamberPressure)
    throatArea = float(source.throatArea)

    # A solve that reached the end of its characteristic net integrates a closed-form exit rather
    # than a sampled plane and writes no plane fields; its delivered columns are left as NaN
    def read(name: str) -> float:
        value = getattr(source, name, None)
        return float('nan') if value is None else float(value)

    planeAreaRatio = read('exitPlaneAreaRatio')
    areaRatio = (planeAreaRatio if np.isfinite(planeAreaRatio)
                 else float(source.ceaOutput.ceaResults['expansionRatio']))
    cea = source.ceaOutput.ceaResults
    ceaPerformance = source.ceaOutput.nozzlePerformance

    backPressures = {'vacuum': 0.0, 'seaLevel': SEALEVELPRESSURE,
                     'design': float(source.targetExitPressure)}
    if specified(source, 'plumeAmbientPressure'):
        backPressures['ambient'] = float(source.plumeAmbientPressure)

    def atBackPressure(vacuumCoefficient: float, pressure: float) -> float:
        return vacuumCoefficient - pressure * areaRatio / chamberPressure

    # -- One-dimensional, CEA equilibrium -- #
    equilibriumCstar = float(cea['characteristicVelocity'])
    equilibriumVacuum = float(ceaPerformance['vacuumThrustCoef'])
    thrustCoefEquilibrium = {name: atBackPressure(equilibriumVacuum, pressure)
                             for name, pressure in backPressures.items()}
    specificImpulseEquilibrium = {name: coefficient * equilibriumCstar / gravity
                                  for name, coefficient in thrustCoefEquilibrium.items()}

    # -- One-dimensional, frozen chamber gas -- #
    chamberGas = chamberGasEstimate(areaRatio, float(source.chamberGamma),
                                    float(source.chamberRGasConstant),
                                    float(source.chamberStagnationTemperature), chamberPressure)
    thrustCoefChamberGas = {name: atBackPressure(chamberGas['vacuumThrustCoef'], pressure)
                            for name, pressure in backPressures.items()}
    specificImpulseChamberGas = {name: coefficient * chamberGas['characteristicVelocity'] / gravity
                                 for name, coefficient in thrustCoefChamberGas.items()}

    # -- Delivered, from the solved exit plane -- #
    deliveredVacuum = read('vacuumThrustCoef')
    thrustCoefDelivered = {name: atBackPressure(deliveredVacuum, pressure)
                           for name, pressure in backPressures.items()}
    # The plane's own vacuum impulse, scaled to each back pressure by the coefficient: both are the
    # same thrust over the same plane mass flow
    deliveredVacuumImpulse = read('exitVacuumSpecificImpulse')
    specificImpulseDelivered = {name: deliveredVacuumImpulse * coefficient / deliveredVacuum
                                for name, coefficient in thrustCoefDelivered.items()}

    dragForce = getattr(source, 'frictionDragForce', None)
    frictionThrustCoef = (float(dragForce) / (chamberPressure * throatArea)
                          if dragForce is not None and np.isfinite(float(dragForce)) else 0.0)
    thrustCoefFriction = {name: coefficient - frictionThrustCoef
                          for name, coefficient in thrustCoefDelivered.items()}
    specificImpulseFriction = {name: specificImpulseDelivered[name] * coefficient
                               / thrustCoefDelivered[name]
                               for name, coefficient in thrustCoefFriction.items()}

    engineWeightFlow = float(source.engineMassFlow) * gravity             # [N/s]
    planePressure = getattr(source, 'exitPlanePressure', None)
    planeMach = getattr(source, 'exitPlaneMach', None)
    exitPressureWall = float(np.asarray(planePressure)[0]) if planePressure is not None else float('nan')
    exitMachWall = float(np.asarray(planeMach)[0]) if planeMach is not None else float('nan')

    return PerformanceSummary(
        areaRatio                      = areaRatio,
        backPressures                  = backPressures,
        exitMachEquilibrium            = float(cea['exitMach']),
        exitMachChamberGas             = chamberGas['exitMach'],
        exitMachDelivered              = read('exitMassAveragedMach'),
        exitMachWall                   = exitMachWall,
        exitPressureEquilibrium        = float(cea['exitPressure']),
        exitPressureChamberGas         = chamberGas['exitPressure'],
        exitPressureDelivered          = read('exitMassAveragedPressure'),
        exitPressureAreaAveraged       = read('exitAreaAveragedPressure'),
        exitPressureWall               = exitPressureWall,
        exitTemperatureEquilibrium     = float(cea['exitTemperature']),
        exitTemperatureChamberGas      = chamberGas['exitTemperature'],
        exitTemperatureDelivered       = read('exitMassAveragedTemperature'),
        exitVelocityEquilibrium        = float(cea['exitVelocity']),
        exitVelocityChamberGas         = chamberGas['exitVelocity'],
        exitVelocityDelivered          = read('exitMassAveragedVelocity'),
        characteristicVelocityEquilibrium = equilibriumCstar,
        characteristicVelocityChamberGas  = chamberGas['characteristicVelocity'],
        thrustCoefEquilibrium          = thrustCoefEquilibrium,
        thrustCoefChamberGas           = thrustCoefChamberGas,
        thrustCoefDelivered            = thrustCoefDelivered,
        thrustCoefDeliveredFrictionCorrected = thrustCoefFriction,
        specificImpulseEquilibrium     = specificImpulseEquilibrium,
        specificImpulseChamberGas      = specificImpulseChamberGas,
        specificImpulseDelivered       = specificImpulseDelivered,
        specificImpulseDeliveredFrictionCorrected = specificImpulseFriction,
        thrustDelivered                = {name: impulse * engineWeightFlow
                                          for name, impulse in specificImpulseDelivered.items()},
        thrustDeliveredFrictionCorrected = {name: impulse * engineWeightFlow
                                            for name, impulse in specificImpulseFriction.items()},
        requestedThrust                = float(source.thrust),
        nozzleEfficiency               = deliveredVacuum / chamberGas['vacuumThrustCoef'],
        frictionThrustCoef             = frictionThrustCoef,
        exitMassClosure                = read('exitMassClosure'))
