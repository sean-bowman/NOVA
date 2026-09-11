# -- NOVA: Radiative Heat Transfer -- #

'''

Radiation between combustion gas, a wall, and whatever the wall sees beyond it.

Two jobs live here, and they share a Stefan-Boltzmann law and nothing else.

The first is a term inside the regeneratively cooled jacket. Combustion products radiate through
the water and carbon dioxide bands, and a wall absorbs some of that and emits back. In a chamber
the wall mostly sees the opposite wall, so the net comes down to the gas-to-wall exchange, and it
runs a few per cent of the convective flux rather than dominating it.

The second is a wall with no coolant behind it at all, which is what a nozzle extension is. There
radiation is the entire heat balance: the wall climbs until what it radiates away matches what the
exhaust puts in. That is a different problem with a different solver, and it lives here too.

The distinction that matters for the first job is that radiation and convection do not share a
driving potential. Convection is driven by the difference between the adiabatic wall temperature
and the wall; radiation by the difference between the fourth powers of the gas and wall
temperatures. Forcing the second onto the first is what makes a radiation term awkward to add to a
resistance network. The way out is exact rather than approximate:

    sigma (T_g^4 - T_w^4) = sigma (T_g + T_w) (T_g^2 + T_w^2) (T_g - T_w)

so the bracket is a coefficient on (T_g - T_w), with no linearisation and no singularity. A network
carrying both then needs one effective coefficient and one effective driving temperature, which is
what `effectiveGasSideDriving` returns.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**The algebra is exact and is tested as an identity, not as an approximation.** The factorisation
above is a difference of two squares applied twice, so `wallRadiationCoefficient` multiplied by
its own temperature difference reproduces the fourth-power law to rounding. The same holds for the
effective coefficient and driving temperature: they reproduce the sum of the convective and
radiative fluxes exactly. tests/testRadiativeCooling.py asserts both and quantifies the residual.

**The grey-gas, grey-wall model is a model.** A real combustion gas radiates in bands rather than
greyly, and a real wall reflects. What is implemented is the one-dimensional grey exchange, which
neglects multiple reflection between the wall and the gas. Hottel's enclosure correction, an
effective wall emissivity of (eps_w + 1)/2, would raise the flux by about twelve per cent at an
emissivity of 0.8; it is not applied, and a result that turns on the difference should not be
taken from here.

**Gas emissivity is supplied, not computed.** NOVA does not yet carry a correlation for the total
emissivity of water vapour and carbon dioxide, so the gas emissivity is an input. Leckner's 1972
correlations are the usual closed form and would slot in as a function returning that input, but
they were not available when this was written and are worth one caution when they are: their
stated accuracy is about ten per cent against the spectral data they were fitted to, and up to
forty per cent against HITEMP-2010. A radiative flux computed through them inherits that.

**Wall emissivity is almost never available.** It is a property of a surface rather than of an
alloy, and `materials.surfaceEmissivity` carries one only for R512E coated columbium. Everything
else supplies it through the configuration. With no emissivity supplied the radiation terms here
return exactly zero and the jacket solve reproduces a run that never had them, to the bit.

All units are mass base SI:
    - Temperature [K]
    - Heat flux   [W/m^2]
    - Coefficient [W/m^2 K]

Author: Sean Bowman

'''

import numpy as np
from scipy.optimize import brentq

from .ablative import STEFANBOLTZMANN
from .utils import ConvergenceFailureError, InvalidInputError

__all__ = [
    'STEFANBOLTZMANN', 'cylinderMeanBeamLength', 'effectiveGasSideDriving', 'meanBeamLength',
    'netWallRadiativeFlux', 'radiationEquilibriumTemperature', 'wallRadiationCoefficient',
]

def meanBeamLength(volume: float, surfaceArea: float, correctionFactor: float = 0.95) -> float:

    '''

    The equivalent path a radiating gas volume presents to the surface bounding it.

    A gas body radiates to a surface along every path through it, and the mean beam length is the
    single path length that reproduces the total. The geometric value is 4 V / A; Hottel's
    correction of about 0.95 accounts for the emissivity not being linear in path length.

    Parameters:
    -----------
    volume : float
        Gas volume [m^3].
    surfaceArea : float
        Area of the surface it radiates to [m^2].
    correctionFactor : float
        Hottel's correction [-]. Values between 0.88 and 0.95 are in use; 0.95 is the common
        default and the one the cylinder shortcut below is consistent with.

    Returns:
    --------
    float
        Mean beam length [m].

    Raises:
    -------
    InvalidInputError
        If the volume or the area is not positive.

    '''

    if volume <= 0.0 or surfaceArea <= 0.0:
        raise InvalidInputError(
            message = 'A mean beam length needs a gas volume and a surface for it to radiate to.',
            parameterName = 'volume/surfaceArea',
            value = (volume, surfaceArea),
            validRange = 'both greater than zero')

    return correctionFactor * 4.0 * volume / surfaceArea

def cylinderMeanBeamLength(diameter: float, correctionFactor: float = 0.95) -> float:

    '''

    Mean beam length of a long circular duct radiating to its own wall.

    For a cylinder long against its diameter, 4 V / A reduces to the diameter itself, so the
    corrected length is simply a fraction of it. A nozzle station is locally that: the flow
    diameter changes slowly against the distance the radiation travels across it.

    Parameters:
    -----------
    diameter : float
        Local flow diameter [m].
    correctionFactor : float
        Hottel's correction [-].

    Returns:
    --------
    float
        Mean beam length [m].

    Raises:
    -------
    InvalidInputError
        If the diameter is not positive.

    '''

    if diameter <= 0.0:
        raise InvalidInputError(
            message = 'A duct with no diameter has no beam length.',
            parameterName = 'diameter',
            value = diameter,
            validRange = 'greater than zero')

    return correctionFactor * diameter

def wallRadiationCoefficient(wallEmissivity: float, gasEmissivity: float,
                             gasTemperature: float, wallTemperature: float) -> float:

    '''

    Gas-to-wall radiation, written as a coefficient on the gas-to-wall temperature difference.

    This is an exact rewriting, not a linearisation. The fourth-power difference factors as

        T_g^4 - T_w^4 = (T_g + T_w) (T_g^2 + T_w^2) (T_g - T_w)

    so the product of this coefficient and (T_g - T_w) reproduces the radiative flux to rounding
    at any pair of temperatures, not only near equality. That is what lets radiation join a
    resistance network without the network changing shape, and it is why no singularity guard is
    needed: the coefficient is smooth and finite everywhere, including where the two temperatures
    coincide, at which point the flux it multiplies is zero anyway.

    The form assumes the wall sees the gas and, through it, a surround at its own temperature.
    That is the chamber case: a wall looking across at more wall at much the same temperature. For
    a wall looking at space, use `netWallRadiativeFlux` with a sink temperature.

    Parameters:
    -----------
    wallEmissivity : float
        Total hemispherical emissivity of the wall surface [-]. Zero returns exactly zero.
    gasEmissivity : float
        Total emissivity of the combustion gas over the mean beam length [-]. Zero returns
        exactly zero.
    gasTemperature : float
        Static gas temperature [K]. Emissivity correlations are written in the gas bulk
        temperature, not in a recovery or stagnation temperature.
    wallTemperature : float
        Gas-side wall temperature [K].

    Returns:
    --------
    float
        Radiative coefficient on (gasTemperature - wallTemperature) [W/m^2 K].

    Raises:
    -------
    InvalidInputError
        If either emissivity falls outside zero to one.

    '''

    for name, value in (('wallEmissivity', wallEmissivity), ('gasEmissivity', gasEmissivity)):
        if not 0.0 <= value <= 1.0:
            raise InvalidInputError(
                message = 'An emissivity outside zero to one describes a surface that emits more '
                          'than a black body.',
                parameterName = name,
                value = value,
                validRange = 'zero to one inclusive')

    if wallEmissivity == 0.0 or gasEmissivity == 0.0:
        return 0.0

    return wallEmissivity * gasEmissivity * STEFANBOLTZMANN \
           * (gasTemperature + wallTemperature) \
           * (gasTemperature**2 + wallTemperature**2)

def netWallRadiativeFlux(wallEmissivity: float, gasEmissivity: float, gasTemperature: float,
                         wallTemperature: float, sinkTemperature: float = None) -> float:

    '''

    Net radiative flux into a wall from the gas in front of it and whatever lies beyond.

    The wall receives what the gas emits plus what the surround emits through it, absorbs that in
    proportion to its own emissivity, and emits back:

        q = eps_w sigma (eps_g T_g^4 + (1 - eps_g) T_sink^4 - T_w^4)

    A sink temperature of None means the wall sees itself, which is the chamber case. Substituting
    T_sink = T_w cancels the transmitted term and leaves eps_w eps_g sigma (T_g^4 - T_w^4), the
    form `wallRadiationCoefficient` factors.

    Parameters:
    -----------
    wallEmissivity : float
        Emissivity of the wall surface [-].
    gasEmissivity : float
        Total emissivity of the gas over the mean beam length [-]. Zero makes the gas transparent,
        so the wall exchanges directly with the sink.
    gasTemperature : float
        Static gas temperature [K].
    wallTemperature : float
        Wall temperature [K].
    sinkTemperature : float | None
        Temperature of what lies beyond the gas [K]. None means the wall's own temperature.

    Returns:
    --------
    float
        Net flux into the wall [W/m^2]. Negative when the wall is losing.

    '''

    if wallEmissivity == 0.0:
        return 0.0

    sink = wallTemperature if sinkTemperature is None else sinkTemperature

    return wallEmissivity * STEFANBOLTZMANN * (
        gasEmissivity * gasTemperature**4
        + (1.0 - gasEmissivity) * sink**4
        - wallTemperature**4)

def effectiveGasSideDriving(convectiveCoefficient: float, radiationCoefficient: float,
                            drivingTemperature: float, gasTemperature: float) -> tuple:

    '''

    One coefficient and one driving temperature standing for convection and radiation together.

    Convection is driven by the adiabatic wall temperature and radiation by the gas temperature,
    and they are not the same quantity. A resistance network carries one potential, so the two are
    combined into the pair that reproduces their sum exactly:

        h_eff = h_conv + h_rad
        T_eff = (h_conv T_aw + h_rad T_g) / h_eff

    which satisfies h_eff (T_eff - T_w) = h_conv (T_aw - T_w) + h_rad (T_g - T_w) identically, for
    any wall temperature. The network keeps its shape, both wall temperature back-outs stay
    correct rather than merely unchanged, and the energy balance still closes by construction.

    With no radiation the driving temperature is returned unchanged rather than recomputed. That is
    a deliberate branch on exact zero: the algebra would give (h_conv T_aw) / h_conv, which is not
    bitwise equal to T_aw, and a run with radiation switched off has to reproduce one that never
    had it.

    Parameters:
    -----------
    convectiveCoefficient : float
        Gas-side convective coefficient [W/m^2 K].
    radiationCoefficient : float
        Radiative coefficient from `wallRadiationCoefficient` [W/m^2 K].
    drivingTemperature : float
        Adiabatic wall temperature convection is driven by [K].
    gasTemperature : float
        Static gas temperature radiation is driven by [K].

    Returns:
    --------
    tuple
        (effectiveCoefficient [W/m^2 K], effectiveDrivingTemperature [K]).

    '''

    if radiationCoefficient == 0.0:
        return convectiveCoefficient, drivingTemperature

    effectiveCoefficient = convectiveCoefficient + radiationCoefficient
    effectiveTemperature = (convectiveCoefficient * drivingTemperature
                            + radiationCoefficient * gasTemperature) / effectiveCoefficient

    return effectiveCoefficient, effectiveTemperature

def radiationEquilibriumTemperature(convectiveCoefficient: float, drivingTemperature: float,
                                    wallEmissivity: float, sinkTemperature: float = 0.0,
                                    absorbedFlux: float = 0.0, viewFactor: float = 1.0,
                                    upperBound: float = 6000.0) -> float:

    '''

    Temperature an uncooled wall settles at when it radiates away everything it takes in.

    With no coolant and no conduction along the wall, the balance at a point is algebraic:

        h (T_aw - T_w) + q_absorbed = eps F sigma (T_w^4 - T_sink^4)

    This is the zero-conduction limit of a radiation-cooled wall. On a nozzle extension it is both
    a useful answer on its own and the right starting point for the solve that does carry
    conduction, because conduction only redistributes heat along the wall and cannot move the
    average far.

    It also shows why the emissivity matters as much as it does. Ignoring the sink and the
    absorbed flux, the balance gives T_w to the inverse fourth root of emissivity, so halving the
    emissivity raises the wall by about nineteen per cent.

    Parameters:
    -----------
    convectiveCoefficient : float
        Gas-side convective coefficient [W/m^2 K].
    drivingTemperature : float
        Adiabatic wall temperature [K].
    wallEmissivity : float
        Emissivity of the radiating surface [-].
    sinkTemperature : float
        Temperature of what the surface radiates to [K]. Space is a few kelvin, and its fourth
        power is negligible against any wall temperature, so zero is the usual choice.
    absorbedFlux : float
        Any other flux absorbed at the surface, such as gas band radiation [W/m^2].
    viewFactor : float
        Fraction of the emitted radiation that leaves [-]. One for a surface looking at open
        space; less where it sees itself.
    upperBound : float
        Upper bracket for the root find [K].

    Returns:
    --------
    float
        Equilibrium wall temperature [K].

    Raises:
    -------
    InvalidInputError
        If the emissivity or the view factor is zero, in which case nothing is radiated and no
        equilibrium exists.
    ConvergenceFailureError
        If the balance has no root below the upper bound.

    '''

    if wallEmissivity <= 0.0 or viewFactor <= 0.0:
        raise InvalidInputError(
            message = 'A surface that radiates nothing has no radiation equilibrium: it heats '
                      'until something else carries the flux away.',
            parameterName = 'wallEmissivity/viewFactor',
            value = (wallEmissivity, viewFactor),
            validRange = 'both greater than zero')

    def imbalance(wallTemperature):

        '''Flux in minus flux out. Zero at equilibrium, and monotone decreasing in the wall.'''

        return (convectiveCoefficient * (drivingTemperature - wallTemperature) + absorbedFlux
                - wallEmissivity * viewFactor * STEFANBOLTZMANN
                * (wallTemperature**4 - sinkTemperature**4))

    lower = max(sinkTemperature, 1.0)
    if imbalance(lower) <= 0.0:
        return lower

    if imbalance(upperBound) > 0.0:
        raise ConvergenceFailureError(
            message = 'No radiation equilibrium below {:.0f} K: the surface is taking in more '
                      'than it can radiate away at that temperature.'.format(upperBound),
            iterations = 0,
            residual = float(imbalance(upperBound)),
            tolerance = 0.0)

    return float(brentq(imbalance, lower, upperBound, xtol = 1.0e-10, rtol = 1.0e-14))
