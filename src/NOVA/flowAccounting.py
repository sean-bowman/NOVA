# -- NOVA: Propellant Flow Accounting -- #

'''

Where the engine's propellant goes, and a refusal when a configuration asks for more than there is.

The chamber burns the engine mass flow at the mixture ratio, so its fuel and oxidizer flows are
fixed once the design point is. A regenerative jacket takes its coolant from one of those streams
on the way to the injector, and the injector draws the chamber's film from what reaches it. Both
therefore come out of the chamber's own flow of their propellant, and neither can be larger than
it. A jacket that passes only part of its propellant sends the rest straight to the injector
through a bypass, which is how the F-1 sent 30 percent of its fuel and how the SSME controls its
chamber coolant valve.

Flows that leave the engine without passing through the chamber, a dumped circuit, an extension
film or a gas generator's turbine exhaust, are extra draws on the tanks rather than shares of the
chamber flow. They are accounted where they are introduced and reported as part of the engine's
total propellant flow.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Arithmetic.** The split is the mixture ratio's definition and the checks are comparisons;
tests/testFlowAccounting.py holds both to the identities they rest on.

All units are mass base SI:
    - Mass flow [kg/s]

Author: Sean Bowman

'''

from dataclasses import dataclass

import numpy as np

from .errors import InvalidInputError

__all__ = ['FlowAccount', 'COOLANTCLASSES', 'accountForFlows', 'propellantFlows']

# The propellant stream a jacket draws its coolant from
COOLANTCLASSES = ('fuel', 'oxidizer')

@dataclass
class FlowAccount:

    '''

    The engine's propellant flows and the jacket's share of them.

    Attributes:
    -----------
    fuelMassFlow, oxidizerMassFlow : float
        Chamber flows of each propellant [kg/s].
    coolantMassFlow : float
        Flow through the jacket [kg/s].
    coolantBypassFraction : float
        Fraction of the coolant's propellant that goes around the jacket to the injector [-].
    propellantForCoolant : float
        Chamber flow of the propellant the jacket draws from [kg/s].

    '''

    fuelMassFlow:          float
    oxidizerMassFlow:      float
    coolantMassFlow:       float
    coolantBypassFraction: float
    propellantForCoolant:  float

def propellantFlows(engineMassFlow: float, mixtureRatio: float) -> tuple:

    '''

    The chamber's fuel and oxidizer flows at a mixture ratio.

    Parameters:
    -----------
    engineMassFlow : float
        Total chamber flow [kg/s].
    mixtureRatio : float
        Oxidizer over fuel [-].

    Returns:
    --------
    tuple
        (fuel [kg/s], oxidizer [kg/s]).

    '''

    fuel = float(engineMassFlow) / (1.0 + float(mixtureRatio))
    return fuel, float(engineMassFlow) - fuel

def _unset(value) -> bool:

    return value is None or (isinstance(value, float) and np.isnan(value))

def accountForFlows(engineMassFlow: float, mixtureRatio: float, coolantClass: str,
                    coolantMassFlow = None, coolantBypassFraction = None,
                    filmMassFlow = None, filmDrawsFrom: str = 'fuel') -> FlowAccount:

    '''

    Split the engine's flow and settle the jacket's share of it, refusing what cannot be supplied.

    The jacket flow is either given, in which case the bypass is what is left of the propellant
    over its own flow, or derived from the bypass fraction, zero when unset, as the propellant
    flow less the bypass. Either way it may not exceed the chamber's flow of its propellant. The
    chamber film is drawn by the injector from the same chamber flow and is held to it too.

    Parameters:
    -----------
    engineMassFlow, mixtureRatio : float
        Chamber flow [kg/s] and mixture ratio [-].
    coolantClass : str
        'fuel' or 'oxidizer', the stream the jacket draws from.
    coolantMassFlow : float | None
        Jacket flow [kg/s], or unset to derive it from the bypass.
    coolantBypassFraction : float | None
        Fraction of the propellant sent around the jacket [-]. Read only when the jacket flow is
        unset; a configuration naming both is refused, since the two say the same thing.
    filmMassFlow : float | None
        Chamber film flow [kg/s], or unset where there is no film.
    filmDrawsFrom : str
        The stream the chamber film is drawn from.

    Returns:
    --------
    FlowAccount

    Raises:
    -------
    InvalidInputError
        If the coolant class is not a propellant stream, the bypass is outside zero to one, both
        the jacket flow and the bypass are given, or the jacket or the film asks for more than the
        chamber flow of its propellant.

    '''

    if coolantClass not in COOLANTCLASSES:
        raise InvalidInputError(
            message = 'A jacket draws its coolant from one of the chamber\'s propellant streams.',
            parameterName = 'coolantClass', value = coolantClass,
            validRange = ' or '.join(repr(name) for name in COOLANTCLASSES))

    fuel, oxidizer = propellantFlows(engineMassFlow, mixtureRatio)
    available = {'fuel': fuel, 'oxidizer': oxidizer}
    propellant = available[coolantClass]

    if not _unset(coolantMassFlow) and not _unset(coolantBypassFraction):
        raise InvalidInputError(
            message = 'The jacket flow and the bypass fraction say the same thing: give one and '
                      'the other follows from the chamber\'s flow of the propellant.',
            parameterName = 'coolantMassFlow/coolantBypassFraction',
            value = (coolantMassFlow, coolantBypassFraction),
            validRange = 'one of the two')

    if _unset(coolantMassFlow):
        bypass = 0.0 if _unset(coolantBypassFraction) else float(coolantBypassFraction)
        if not 0.0 <= bypass < 1.0:
            raise InvalidInputError(
                message = 'A bypass fraction is the share of the propellant sent around the '
                          'jacket; all of it would leave the jacket with nothing to carry.',
                parameterName = 'coolantBypassFraction', value = bypass,
                validRange = 'zero up to but not including one')
        jacket = propellant * (1.0 - bypass)
    else:
        jacket = float(coolantMassFlow)
        bypass = 1.0 - jacket / propellant

    # A thousandth of a percent of slack, so a jacket set to exactly the propellant flow is not
    # refused for the rounding of the mixture ratio split
    tolerance = 1.0e-5 * propellant
    if jacket > propellant + tolerance:
        raise InvalidInputError(
            message = (f'The jacket asks for {jacket:.4g} kg/s of {coolantClass}, and the chamber '
                       f'burns {propellant:.4g} kg/s of it at a mixture ratio of '
                       f'{float(mixtureRatio):.3g}. A jacket returned to the injector carries no '
                       f'more than the injector takes.'),
            parameterName = 'coolantMassFlow', value = jacket,
            validRange = f'at most {propellant:.4g} kg/s')

    if not _unset(filmMassFlow) and filmDrawsFrom in available:
        film = float(filmMassFlow)
        if film > available[filmDrawsFrom] + 1.0e-5 * available[filmDrawsFrom]:
            raise InvalidInputError(
                message = (f'The chamber film asks for {film:.4g} kg/s of {filmDrawsFrom}, more '
                           f'than the {available[filmDrawsFrom]:.4g} kg/s the injector receives.'),
                parameterName = 'filmMassFlow', value = film,
                validRange = f'at most {available[filmDrawsFrom]:.4g} kg/s')

    return FlowAccount(fuelMassFlow = fuel, oxidizerMassFlow = oxidizer, coolantMassFlow = jacket,
                       coolantBypassFraction = bypass, propellantForCoolant = propellant)
