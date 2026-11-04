# -- NOVA: Turnaround Manifold of a Two-Pass Jacket -- #

'''

The ring manifold where a two-pass jacket's coolant reverses direction.

In a two-pass jacket the coolant runs down one family of channels to the far end of the jacket
and back up the other. The families alternate around the circumference, so at the far end each
down channel empties into the ring beside the up channel it feeds, and the ring carries no net flow
around the nozzle: it is a plenum the coolant turns in, not a duct it travels along. The F-1's
fuel turned this way at the end of its tube bundle, and the J-2's hydrogen at the exit of its
nozzle.

**Sizing.** The ring is a torus of circular section around the jacket's far end. Its section is
set so the coolant turning in one channel pitch of it moves at a set fraction of the channel
velocity: the turning flow of one channel crosses an area of the section's diameter times the
pitch, so

    d = m_c / (rho kappa u_c p)

with m_c the flow of one down channel, u_c its velocity, p the pitch and kappa the velocity ratio,
0.5 by default. A slower ring is larger and heavier for a loss that does not fall below the exit
loss; a faster one turns the flow in a duct rather than a plenum. The ring's section is the same all
the way round, which `Volute` refuses by construction, so it has its own law here.

**Loss.** The coolant leaves the down channel into the plenum and enters the up channel from it.
With the plenum velocity small against the channel's, those are the sudden expansion, which loses
the whole velocity head of the down channel (Borda-Carnot), and the sharp-edged entrance, which
loses half the velocity head of the up channel [Idelchik, Handbook of Hydraulic Resistance,
Diagram 3-1 and 4-1; Crane TP-410]:

    dp = 1.0 (rho u_down^2 / 2) + 0.5 (rho u_up^2 / 2)

The plenum's own velocity head, kappa^2 of the channel's, is left out of both terms.

**Wall.** The ring is a thin cylinder under the coolant pressure, sized on hoop stress against the
jacket alloy's yield strength at the coolant temperature over a factor of safety,
t = p r / (sigma_y / FOS), and never thinner than the jacket's minimum wall.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Closed form, held to its identities.** The loss coefficients are handbook values for a sudden
expansion and a sharp entrance, not a measurement of a rocket turnaround; the true loss of a
compact turn is higher by the interaction of the two, which SP-8087 notes without quantifying.
tests/testTurnaround.py holds the section to the velocity it is sized for, the loss to its closed
form, and the wall to the hoop stress it is sized on. **The turnaround loss is unvalidated against
a rocket manifold.**

All units are mass base SI:
    - Length [m]
    - Pressure [Pa]
    - Mass flow [kg/s]
    - Velocity [m/s]

Author: Sean Bowman

'''

from dataclasses import dataclass

import numpy as np

from .errors import InvalidInputError

__all__ = ['Turnaround', 'TURNAROUNDEXITLOSS', 'TURNAROUNDENTRANCELOSS', 'sizeTurnaround',
           'turnaroundSurface']

TURNAROUNDEXITLOSS = 1.0          # [-], velocity heads of the channel emptying into the plenum
TURNAROUNDENTRANCELOSS = 0.5      # [-], velocity heads of the channel drawing from it
DEFAULTVELOCITYRATIO = 0.5        # [-], ring turning velocity over channel velocity

@dataclass
class Turnaround:

    '''

    A turnaround ring, sized.

    Attributes:
    -----------
    sectionRadius : float
        Radius of the ring's circular section [m].
    ringRadius : float
        Radius of the section's center about the nozzle axis [m].
    axialPosition : float
        Axial position of the ring's center [m].
    wallThickness : float
        Ring wall [m].
    pressureDrop : float
        Coolant pressure lost turning [Pa].
    downVelocity, upVelocity, ringVelocity : float
        Coolant velocity in the down channel, the up channel and turning in the ring [m/s].
    velocityRatio : float
        Ring over down channel velocity, as sized [-].

    '''

    sectionRadius: float
    ringRadius:    float
    axialPosition: float
    wallThickness: float
    pressureDrop:  float
    downVelocity:  float
    upVelocity:    float
    ringVelocity:  float
    velocityRatio: float

    @property
    def flowArea(self) -> float:

        '''Section of the ring [m^2].'''

        return np.pi * self.sectionRadius**2

def sizeTurnaround(channelMassFlow: float, density: float, downFlowArea: float, upFlowArea: float,
                   pitch: float, wallRadius: float, axialPosition: float, channelDepth: float,
                   hotWallThickness: float, pressure: float, yieldStrength: float,
                   factorOfSafety: float = 1.5, minWallThickness: float = 0.0,
                   velocityRatio: float = DEFAULTVELOCITYRATIO) -> Turnaround:

    '''

    Size the ring at the far end of a two-pass jacket and the coolant pressure it costs.

    Parameters:
    -----------
    channelMassFlow : float
        Flow of one down channel, which one up channel takes on [kg/s].
    density : float
        Coolant density at the far end [kg/m^3].
    downFlowArea, upFlowArea : float
        Flow area of the down and up channel at the far end [m^2].
    pitch : float
        Circumferential pitch of one channel at the far end [m].
    wallRadius : float
        Hot wall radius at the far end [m].
    axialPosition : float
        Axial position of the far end [m].
    channelDepth : float
        Radial depth of the channels at the far end [m], so the ring sits outside them.
    hotWallThickness : float
        Hot wall [m].
    pressure : float
        Coolant pressure in the ring [Pa].
    yieldStrength : float
        Ring alloy yield strength at the coolant temperature [Pa].
    factorOfSafety : float
        On yield [-].
    minWallThickness : float
        Thinnest wall the process builds [m].
    velocityRatio : float
        Ring turning velocity over the down channel velocity [-].

    Returns:
    --------
    Turnaround

    Raises:
    -------
    InvalidInputError
        For a non-positive flow, density, area or pitch, or a velocity ratio outside (0, 1].

    '''

    for name, value in (('channelMassFlow', channelMassFlow), ('density', density),
                        ('downFlowArea', downFlowArea), ('upFlowArea', upFlowArea),
                        ('pitch', pitch), ('yieldStrength', yieldStrength)):
        if not (np.isfinite(value) and value > 0.0):
            raise InvalidInputError(
                message = 'A turnaround needs a positive flow, density, channel areas, pitch and '
                          'wall strength to be sized.',
                parameterName = name, value = value, validRange = 'above 0')
    if not 0.0 < velocityRatio <= 1.0:
        raise InvalidInputError(
            message = 'The ring turns the coolant slower than the channel it leaves; a ratio above '
                      'one is a duct, not a plenum.',
            parameterName = 'turnaroundVelocityRatio', value = velocityRatio, validRange = '(0, 1]')

    downVelocity = channelMassFlow / (density * downFlowArea)
    upVelocity = channelMassFlow / (density * upFlowArea)
    ringVelocity = velocityRatio * downVelocity
    sectionDiameter = channelMassFlow / (density * ringVelocity * pitch)
    sectionRadius = 0.5 * sectionDiameter

    allowable = yieldStrength / factorOfSafety
    wallThickness = max(pressure * sectionRadius / allowable, float(minWallThickness))

    pressureDrop = (TURNAROUNDEXITLOSS * 0.5 * density * downVelocity**2
                    + TURNAROUNDENTRANCELOSS * 0.5 * density * upVelocity**2)

    return Turnaround(
        sectionRadius = sectionRadius,
        ringRadius    = wallRadius + hotWallThickness + channelDepth + wallThickness + sectionRadius,
        axialPosition = axialPosition,
        wallThickness = wallThickness,
        pressureDrop  = pressureDrop,
        downVelocity  = downVelocity,
        upVelocity    = upVelocity,
        ringVelocity  = ringVelocity,
        velocityRatio = velocityRatio)

def turnaroundSurface(turnaround: Turnaround, numAround: int = 120, numSection: int = 24) -> tuple:

    '''

    The ring's inner surface as a mesh, for the 3D views and the export.

    Returns:
    --------
    tuple
        (x, y, z) arrays of shape (numSection, numAround), x along the nozzle axis [m].

    '''

    around = np.linspace(0.0, 2.0 * np.pi, numAround)
    section = np.linspace(0.0, 2.0 * np.pi, numSection)[:, None]
    radial = turnaround.ringRadius + turnaround.sectionRadius * np.cos(section)
    x = turnaround.axialPosition + turnaround.sectionRadius * np.sin(section) * np.ones_like(around)
    return x, radial * np.cos(around), radial * np.sin(around)
