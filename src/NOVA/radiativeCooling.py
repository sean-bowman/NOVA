
# -- NOVA: Radiative Heat Transfer -- #

'''

Radiation between combustion gas, a wall, and whatever the wall sees beyond it.

Two jobs live here. They share a Stefan-Boltzmann law and nothing else.

The first is a term inside the regeneratively cooled jacket. Combustion products radiate
through the water and carbon dioxide bands, and a wall absorbs some of that and emits back. In
a chamber the wall mostly sees the opposite wall, so the net comes down to the gas-to-wall
exchange, which runs a few percent of the convective flux rather than dominating it.

The second is a wall with no coolant behind it at all, which is what a nozzle extension is.
There radiation is the entire heat balance: the wall climbs until what it radiates away matches
what the exhaust puts in. That is a different problem with a different solver. It lives here
too.

The distinction that matters for the first job is that radiation and convection do not share a
driving potential. Convection is driven by the difference between the adiabatic wall
temperature and the wall; radiation by the difference between the fourth powers of the gas and
wall temperatures. Forcing the second onto the first is what makes a radiation term awkward to
add to a resistance network. The way out is exact rather than approximate:

    sigma (T_g^4 - T_w^4) = sigma (T_g + T_w) (T_g^2 + T_w^2) (T_g - T_w)

so the bracket is a coefficient on (T_g - T_w), with no linearization and no singularity. A
network carrying both then needs one effective coefficient and one effective driving
temperature, which is what `effectiveGasSideDriving` returns.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**The algebra is exact and is tested as an identity, not as an approximation.** The
factorization above is a difference of two squares applied twice, so `wallRadiationCoefficient`
multiplied by its own temperature difference reproduces the fourth-power law to rounding. The
same holds for the effective coefficient and driving temperature: they reproduce the sum of the
convective and radiative fluxes exactly. tests/testRadiativeCooling.py asserts both and
quantifies the residual.

**The grey-gas, grey-wall model is a model.** A real combustion gas radiates in bands rather
than greyly, and a real wall reflects. What is implemented is the one-dimensional grey
exchange, which neglects multiple reflection between the wall and the gas. Hottel's enclosure
correction, an effective wall emissivity of (eps_w + 1)/2, would raise the flux by about twelve
percent at an emissivity of 0.8; it is not applied, and a result that turns on the difference
should not be taken from here.

**Gas emissivity is supplied, not computed.** NOVA does not yet carry a correlation for the
total emissivity of water vapour and carbon dioxide, so the gas emissivity is an input.
Leckner's 1972 correlations are the usual closed form and would slot in as a function returning
that input, but they were not available when this was written and are worth one caution when
they
are: their stated accuracy is about ten percent against the spectral data they were fitted to,
and up to forty percent against HITEMP-2010. A radiative flux computed through them inherits
that.

**Wall emissivity is almost never available.** It is a property of a surface rather than of an
alloy, and `materials.surfaceEmissivity` carries one only for R512E coated columbium.
Everything else supplies it through the configuration. With no emissivity supplied the
radiation terms here return exactly zero and the jacket solve reproduces a run that never had
them, to the bit.

**The extension solver is verified, not validated.** Four checks, each against an answer it did
not produce: with conduction switched off it reproduces a scalar root find at every station to
1.4e-12 relative, converging in a single Newton step because the starting guess is then exact;
the conduction operator converges at observed order 2.000 against a manufactured sine solution,
refined four times; the energy balance closes to 7e-12 of the power in, which is what catches
an arc-length or an area error; and halving the emissivity moves the peak wall temperature by
5.9 percent against the 18.9 percent bound it must stay under, because convection holds it
there. The through-thickness drop is reported at every station rather than asserted, and on a
0.5 mm shell of 45 W/m-K it runs a few kelvin against a wall above 2000 K.

**No validation is possible against open data.** The plausibility check below is labeled as
one. A validation would need a measured wall temperature distribution along a fully specified
firing: contour, propellants, chamber pressure, material, coating and its emissivity at
temperature. Published coated-columbium extension temperatures near 1590 K exist as a band
rather than a distribution. Against that band, a 0.5 mm coated shell at an emissivity of 0.7 on
a one megapascal storable apogee thruster running from area ratio 20 comes out at 1544 K at the
joint and 1259 K at the lip, and a 0.7 megapascal reaction control thruster from area ratio 30
comes out at 1372 K. Those sit where the literature puts them, but the engines behind the band
are not specified well enough for the agreement to be an error figure. Closing the gap needs a
test article with thermocouples, or a released firing dataset with the emissivity recorded.

**A high-pressure hydrogen engine is a different problem.** On
NOVA's own 6.9 megapascal LOX/LH2 reference case, a coated C103 shell runs 2763 K starting at
area ratio 3 and still 1921 K starting at area ratio 35, against a vacuum limit of 1673 K. It
fails everywhere on that contour. That is the flux, not the solver: Bartz scales as chamber
pressure to the 0.8, so the same shell on a one megapascal engine sees a fifth of the
coefficient and settles about thirty percent cooler. Reporting the margin rather than the
temperature alone is what makes that conclusion fall out of the solve instead of being left to
the reader.

**Conduction along the shell barely matters.** On a 0.5 mm shell over a
600 mm extension, going from 45 to 400 W/m-K narrows the temperature span by under three per
cent. The conduction length sqrt(k t / h) is about ten millimeters, so the joint with the
jacket influences only the first few stations. That is worth knowing before spending effort on
a two-dimensional wall solve.

All units are mass base SI:
    - Temperature [K]
    - Heat flux   [W/m^2]
    - Coefficient [W/m^2 K]

Author: Sean Bowman

'''

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.linalg import solve_banded
from scipy.optimize import brentq

from .ablative import STEFANBOLTZMANN
from .errors import ConvergenceFailureError, InvalidInputError
from .validation import specified

__all__ = [
    'RadiativeExtensionResult', 'RadiativeShell', 'STEFANBOLTZMANN',
    'cylinderMeanBeamLength', 'effectiveGasSideDriving', 'meanBeamLength',
    'netWallRadiativeFlux', 'radiationEquilibriumTemperature', 'radiativeExtensionOutputs',
    'radiativeNozzleExtension', 'wallRadiationCoefficient',
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

    This is an exact rewriting, not a linearization. The fourth-power difference factors as

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
    emissivity raises the wall by about nineteen percent.

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

@dataclass
class RadiativeShell:

    """

    The uncooled shell a nozzle extension is made of, and what it radiates to.

    Attributes:
    -----------
    thermalConductivity : float | callable
        Conductivity of the shell wall [W/m-K], or a callable taking temperature in kelvin and
        returning it. This is an input rather than a store lookup because the materials store
        carries conductivity curves only for the jacket alloys; `wallMaterialCurves` falls back
        to GRCop-42 for a refractory metal, which conducts eight times better and would flatten
        the temperature distribution completely. C103 is near 45 W/m-K, but the number and its
        source belong to the caller.
    thickness : float
        Wall thickness [m]. Enters conduction along the shell and sets the through-thickness
        temperature drop the lumped treatment neglects.
    innerEmissivity : float
        Emissivity of the gas-side surface [-]. Sets how much band radiation the wall absorbs.
    outerEmissivity : float
        Emissivity of the outward-facing surface [-]. This is the one that governs: the wall
        settles where what it radiates out matches what comes in, and equilibrium temperature
        goes as the inverse fourth root of it.
    outerViewFactor : float
        Fraction of the outward emission that reaches the sink [-]. One for a surface looking at
        open space, less where it sees vehicle structure.
    sinkTemperature : float
        Temperature of what the outer surface radiates to [K]. A few kelvin for space, and its
        fourth power is negligible against any wall temperature.
    gasEmissivity : float
        Total emissivity of the exhaust over the mean beam length [-]. Zero makes the gas
        transparent and removes the band radiation term exactly.
    upstreamTemperature : float | None
        Wall temperature at the joint with whatever is upstream [K], usually the regen section's
        exit hot wall temperature. None makes the joint adiabatic, which is the free-standing
        case and the conservative one, because it lets no heat out through the flange.
    material : str | None
        Material name, used only to look up a temperature limit for the margin report. None
        skips the margin.
    atmosphere : str
        Which of the material's limits applies: an extension in vacuum is 'inert', one firing
        at sea level with a silicide coating is 'oxidisingCoated'.

    """

    thermalConductivity: Any
    thickness:           float
    innerEmissivity:     float
    outerEmissivity:     float
    outerViewFactor:     float = 1.0
    sinkTemperature:     float = 0.0
    gasEmissivity:       float = 0.0
    upstreamTemperature: Any = None
    material:            Any = None
    atmosphere:          str = 'inert'

@dataclass
class RadiativeExtensionResult:

    """

    An extension solved along its arc length.

    Attributes:
    -----------
    axialPosition, radius : numpy.ndarray
        The stations the solve was made on [m].
    extensionWallTemperature : numpy.ndarray
        Converged wall temperature at each station [K].
    extensionEquilibriumTemperature : numpy.ndarray
        Pointwise radiation equilibrium with conduction switched off [K]. The solve starts here,
        and the difference between the two is exactly what axial conduction did.
    extensionConvectiveCoefficient : numpy.ndarray
        Bartz coefficient at the converged wall temperature [W/m^2 K].
    extensionConvectiveFlux, extensionGasRadiativeFlux : numpy.ndarray
    extensionEmittedFlux, extensionConductionFlux : numpy.ndarray
        The four terms of the balance at each station [W/m^2], signed as into the wall except
        the emitted flux, which is out. They sum to zero at convergence.
    extensionThroughThicknessDrop : numpy.ndarray
        q t / k at each station [K]. The lumped treatment assumes this is small; the array is
        reported rather than asserted so the assumption can be checked against the answer.
    extensionPeakWallTemperature : float
        Hottest station [K].
    extensionTemperatureLimit : float | None
        The material's limit in the stated atmosphere [K], or None where no material was named.
    extensionTemperatureMargin : float | None
        Limit minus peak [K]. Negative means the extension does not survive.
    extensionEnergyBalanceResidual : float
        Total power in minus total power out, as a fraction of the power in [-]. A closure
        check on the discretization rather than on the physics.
    iterations : int
        Newton iterations taken.
    residual : float
        Largest temperature update of the final iteration [K].
    converged : bool
        Whether the update fell below the tolerance.

    """

    axialPosition:                   np.ndarray
    radius:                          np.ndarray
    extensionWallTemperature:        np.ndarray
    extensionEquilibriumTemperature: np.ndarray
    extensionConvectiveCoefficient:  np.ndarray
    extensionConvectiveFlux:         np.ndarray
    extensionGasRadiativeFlux:       np.ndarray
    extensionEmittedFlux:            np.ndarray
    extensionConductionFlux:         np.ndarray
    extensionThroughThicknessDrop:   np.ndarray
    extensionPeakWallTemperature:    float
    extensionTemperatureLimit:       Any
    extensionTemperatureMargin:      Any
    extensionEnergyBalanceResidual:  float
    iterations:                      int
    residual:                        float
    converged:                       bool

# What `Nozzle.generateRadiativeExtension` copies back off the result.
radiativeExtensionOutputs = (
    'extensionWallTemperature', 'extensionEquilibriumTemperature',
    'extensionConvectiveCoefficient', 'extensionConvectiveFlux', 'extensionGasRadiativeFlux',
    'extensionEmittedFlux', 'extensionConductionFlux', 'extensionThroughThicknessDrop',
    'extensionPeakWallTemperature', 'extensionTemperatureLimit', 'extensionTemperatureMargin',
    'extensionEnergyBalanceResidual')

def _shellConductivity(thermalConductivity, temperature):

    '''Conductivity at a temperature, whether a constant or a curve was supplied.'''

    if callable(thermalConductivity):
        return float(thermalConductivity(temperature))

    return float(thermalConductivity)

def radiativeNozzleExtension(shell: RadiativeShell, axialPosition, radius, machNumber,
                             staticTemperature, recoveryTemperature,
                             chamberPressure: float, characteristicVelocity: float,
                             exhaustGamma, exhaustGasConstant, exhaustMolecularWeight,
                             throatRadius: float, throatRadiusOfCurvature: float,
                             tolerance: float = 1.0e-6,
                             maxIterations: int = 200) -> RadiativeExtensionResult:

    """

    Wall temperature along an uncooled nozzle extension that survives by radiating.

    Past the end of the jacket there is no coolant. The wall takes convection and band radiation
    from the exhaust, conducts along itself, and radiates to space, and it settles wherever those
    balance. Per unit area of a thin shell of arc length s and local radius r,

        (1/r) d/ds [ r k t dT/ds ] + h_g (T_aw - T_w)
            + eps_i eps_g sigma (T_g^4 - T_w^4) - eps_o F_o sigma (T_w^4 - T_sink^4) = 0

    **This does not converge by the successive substitution the jacket uses.** There the only
    wall-temperature dependence is Bartz's sigma, which is weak, so the map contracts. Here
    radiation is the balance itself and its derivative gains 4 eps sigma T^3, which at 1500 K and
    an emissivity of 0.8 is about 150 W/m^2 K, comparable to the convective coefficient. The map
    stops contracting and the problem becomes a nonlinear two-point boundary value problem, solved
    below by damped Newton on a tridiagonal Jacobian.

    **The shell is lumped through its thickness.** Conduction across the wall is not resolved,
    which is right when q t / k is small against the temperature the wall runs at; the array is
    returned so the assumption can be checked rather than assumed. The convective coefficient is
    recomputed at the current wall temperature at every iteration but held fixed inside the
    Jacobian, which costs iterations rather than accuracy because Newton converges to the root of
    whatever residual it is given.

    Both radiation terms are the module's own primitives, so an extension and a jacket radiating
    into the same gas use the same algebra. The inner surface is treated as seeing itself across
    the flow, which is what a closed annulus does.

    **The band term can go either way.** On an extension it usually cools. In a chamber the
    wall is far below the gas and band radiation is a heat source. Here the wall is driven by the
    recovery temperature while the band exchange is written in the static one, and at Mach 3 those
    differ by more than a thousand kelvin. A wall settling above the static gas radiates into it,
    so the gas becomes a second sink alongside space. Which way it runs is a property of the
    station, not an assumption made here.

    Parameters:
    -----------
    shell : RadiativeShell
        The wall and what it radiates to.
    axialPosition, radius : array_like
        Extension stations, ascending in axial position [m].
    machNumber, staticTemperature, recoveryTemperature : array_like
        Exhaust state at each station [-], [K], [K].
    chamberPressure : float
        Stagnation chamber pressure [Pa].
    characteristicVelocity : float
        Characteristic velocity [m/s].
    exhaustGamma, exhaustGasConstant, exhaustMolecularWeight : array_like or float
        Exhaust properties at each station [-], [J/kg-K], [kg/kmol].
    throatRadius : float
        Throat radius [m], for the Bartz area ratio.
    throatRadiusOfCurvature : float
        Radius of curvature at the throat [m].
    tolerance : float
        Convergence on the largest temperature update [K].
    maxIterations : int
        Newton iteration cap.

    Returns:
    --------
    RadiativeExtensionResult

    Raises:
    -------
    InvalidInputError
        If fewer than three stations are supplied, the arrays disagree in length, the thickness
        or conductivity is not positive, or the outer surface radiates nothing.
    ConvergenceFailureError
        If Newton does not reach the tolerance within the iteration cap.

    """

    # Bartz lives in the jacket model, which imports this one. The import is function-local to
    # break the cycle, the same way the ablative liner reaches it.
    from .regenThermal import bartzHeatTransferCoefficient

    axialPosition = np.asarray(axialPosition, dtype = float)
    radius = np.asarray(radius, dtype = float)
    machNumber = np.asarray(machNumber, dtype = float)
    staticTemperature = np.asarray(staticTemperature, dtype = float)
    recoveryTemperature = np.asarray(recoveryTemperature, dtype = float)

    stations = axialPosition.size
    if stations < 3:
        raise InvalidInputError(
            message = 'A boundary value problem needs an interior. Two stations are both '
                      'boundaries.',
            parameterName = 'axialPosition',
            value = stations,
            validRange = 'at least three stations')

    lengths = {array.size for array in (axialPosition, radius, machNumber, staticTemperature,
                                        recoveryTemperature)}
    if len(lengths) != 1:
        raise InvalidInputError(
            message = 'Every station array must describe the same stations.',
            parameterName = 'axialPosition and the exhaust arrays',
            value = sorted(lengths),
            validRange = 'all the same length')

    if shell.thickness <= 0.0:
        raise InvalidInputError(
            message = 'A shell with no thickness conducts nothing along itself.',
            parameterName = 'shell.thickness',
            value = shell.thickness,
            validRange = 'greater than zero')

    if _shellConductivity(shell.thermalConductivity, 1000.0) <= 0.0:
        raise InvalidInputError(
            message = 'A shell with no conductivity cannot spread heat along itself.',
            parameterName = 'shell.thermalConductivity',
            value = shell.thermalConductivity,
            validRange = 'greater than zero')

    if shell.outerEmissivity <= 0.0 or shell.outerViewFactor <= 0.0:
        raise InvalidInputError(
            message = 'An extension that radiates nothing has no equilibrium: it heats until '
                      'something else carries the flux away, which is the case this solver '
                      'cannot describe.',
            parameterName = 'shell.outerEmissivity/shell.outerViewFactor',
            value = (shell.outerEmissivity, shell.outerViewFactor),
            validRange = 'both greater than zero')

    gamma = np.broadcast_to(np.asarray(exhaustGamma, dtype = float), (stations,))
    gasConstant = np.broadcast_to(np.asarray(exhaustGasConstant, dtype = float), (stations,))
    molecularWeight = np.broadcast_to(np.asarray(exhaustMolecularWeight, dtype = float),
                                      (stations,))

    # Arc length along the wall, because the shell conducts along itself rather than along the
    # axis, and a bell's wall is appreciably longer than its axial extent.
    faceSpacing = np.sqrt(np.diff(axialPosition)**2 + np.diff(radius)**2)
    faceRadius = 0.5 * (radius[:-1] + radius[1:])

    # Control volume length: a full cell in the interior, a half cell at each end.
    cellLength = np.zeros(stations)
    cellLength[0] = 0.5 * faceSpacing[0]
    cellLength[-1] = 0.5 * faceSpacing[-1]
    cellLength[1:-1] = 0.5 * (faceSpacing[:-1] + faceSpacing[1:])

    throatArea = np.pi * throatRadius**2
    localArea = np.pi * radius**2
    emissionCoefficient = shell.outerEmissivity * shell.outerViewFactor * STEFANBOLTZMANN

    def convectiveCoefficients(wallTemperature):

        '''Bartz at each station, at the current wall temperature.'''

        return np.array([bartzHeatTransferCoefficient(
            staticTemperature[i], machNumber[i], gamma[i], gasConstant[i], molecularWeight[i],
            wallTemperature[i], chamberPressure, characteristicVelocity,
            2.0 * throatRadius, throatRadiusOfCurvature, throatArea, localArea[i])
            for i in range(stations)])

    def surfaceFluxes(wallTemperature, coefficient):

        '''The three surface terms, signed as they enter the balance.'''

        convective = coefficient * (recoveryTemperature - wallTemperature)
        band = np.array([netWallRadiativeFlux(shell.innerEmissivity, shell.gasEmissivity,
                                              staticTemperature[i], wallTemperature[i])
                         for i in range(stations)])
        emitted = emissionCoefficient * (wallTemperature**4 - shell.sinkTemperature**4)

        return convective, band, emitted

    # Starting guess: the pointwise balance with conduction switched off. It is the answer
    # everywhere the wall is flat, and conduction only redistributes from there.
    #
    # It is iterated to self-consistency rather than evaluated once, because both the Bartz
    # coefficient and the band term depend on the wall temperature being solved for. Successive
    # substitution does contract here, unlike the full problem, because switching conduction off
    # leaves each station a scalar equation whose root find carries the whole quartic. Without
    # this the array would be a starting guess rather than the zero-conduction answer, and the
    # difference between it and the solution would not be conduction alone.
    equilibrium = np.full(stations, 0.5 * float(recoveryTemperature.max()))
    for _ in range(50):
        coefficient = convectiveCoefficients(equilibrium)
        updated = np.array([radiationEquilibriumTemperature(
            coefficient[i], recoveryTemperature[i], shell.outerEmissivity,
            shell.sinkTemperature,
            netWallRadiativeFlux(shell.innerEmissivity, shell.gasEmissivity,
                                 staticTemperature[i], equilibrium[i]),
            shell.outerViewFactor)
            for i in range(stations)])
        shift = float(np.max(np.abs(updated - equilibrium)))
        equilibrium = updated
        if shift < tolerance:
            break

    wallTemperature = equilibrium.copy()

    # A joint temperature reaches here from a configuration, where an unspecified field is NaN
    # rather than None. Both mean the joint was not given, so both take the adiabatic branch; a
    # NaN pinned as a Dirichlet value would poison the whole solve.
    dirichlet = specified(shell, 'upstreamTemperature')
    if dirichlet:
        wallTemperature[0] = float(shell.upstreamTemperature)

    def residualVector(temperature):

        '''Net flux into each control volume, per unit wall area. Zero at the solution.'''

        coefficient = convectiveCoefficients(temperature)
        convective, band, emitted = surfaceFluxes(temperature, coefficient)

        conductivity = np.array([_shellConductivity(shell.thermalConductivity, value)
                                 for value in temperature])
        faceConductivity = 0.5 * (conductivity[:-1] + conductivity[1:])
        faceConductance = faceRadius * faceConductivity * shell.thickness / faceSpacing

        conduction = np.zeros(stations)
        flowing = faceConductance * np.diff(temperature)
        conduction[:-1] += flowing
        conduction[1:] -= flowing
        conduction /= radius * cellLength

        residual = conduction + convective + band - emitted
        if dirichlet:
            residual[0] = float(shell.upstreamTemperature) - temperature[0]

        return residual, coefficient, convective, band, emitted, conduction, faceConductance

    def jacobianBands(temperature, coefficient, faceConductance):

        '''Tridiagonal Jacobian in the banded layout solve_banded wants.'''

        scale = radius * cellLength
        lower = np.zeros(stations)
        diagonal = np.zeros(stations)
        upper = np.zeros(stations)

        lower[:-1] = faceConductance / scale[1:]
        upper[1:] = faceConductance / scale[:-1]
        diagonal[:-1] -= faceConductance / scale[:-1]
        diagonal[1:] -= faceConductance / scale[1:]

        # The surface terms. Bartz's own wall-temperature dependence is left out, which makes
        # this a chord in that one term and costs iterations rather than accuracy.
        diagonal -= coefficient
        diagonal -= 4.0 * shell.innerEmissivity * shell.gasEmissivity * STEFANBOLTZMANN \
                    * temperature**3
        diagonal -= 4.0 * emissionCoefficient * temperature**3

        if dirichlet:
            diagonal[0] = -1.0
            upper[1] = 0.0

        bands = np.zeros((3, stations))
        bands[0, 1:] = upper[1:]
        bands[1, :] = diagonal
        bands[2, :-1] = lower[:-1]

        return bands

    iterations = 0
    update = np.inf
    outcome = residualVector(wallTemperature)

    while iterations < maxIterations and update > tolerance:

        residual, coefficient = outcome[0], outcome[1]

        # A residual already at zero is the answer, and there is no step that reduces it further.
        # Without this the line search below would find no improvement and report a stall on a
        # converged solution, which the zero-conduction case comes close to reaching.
        if np.max(np.abs(residual)) == 0.0:
            update = 0.0
            break

        bands = jacobianBands(wallTemperature, coefficient, outcome[6])
        step = solve_banded((1, 1), bands, -residual)

        # Damped Newton. A full step from a cold guess can overshoot into negative temperature,
        # and the quartic makes the residual there meaningless, so the step is cut until it both
        # stays physical and reduces the residual.
        damping = 1.0
        norm = np.max(np.abs(residual))
        improved = False
        while damping > 1.0e-4:
            trial = wallTemperature + damping * step
            if np.all(trial > 0.0):
                trialOutcome = residualVector(trial)
                if np.max(np.abs(trialOutcome[0])) < norm:
                    improved = True
                    break
            damping *= 0.5

        # A stalled line search is a failure, not an answer. Accepting the last tiny step would
        # drive the update below the tolerance and report convergence on a point that never
        # improved, which is the one way this solver could lie about its own result.
        if not improved:
            raise ConvergenceFailureError(
                message = 'No step along the Newton direction reduces the residual of the '
                          'radiation-cooled extension. The balance has stalled rather than '
                          'settled, so the temperatures reached are not a solution.',
                iterations = iterations,
                residual = float(norm),
                tolerance = tolerance)

        update = float(np.max(np.abs(trial - wallTemperature)))
        wallTemperature = trial
        outcome = trialOutcome
        iterations += 1

    converged = update <= tolerance
    if not converged:
        raise ConvergenceFailureError(
            message = 'The radiation-cooled extension did not settle. The balance is stiffest '
                      'where the emissivity is low and the flux is high, which is the joint '
                      'with the jacket.',
            iterations = iterations,
            residual = update,
            tolerance = tolerance)

    residual, coefficient, convective, band, emitted, conduction, _ = outcome

    # Energy closure over the whole shell, as a fraction of what came in. This catches an area
    # or an arc-length error, which a converged residual on its own would not.
    wallArea = 2.0 * np.pi * radius * cellLength
    powerIn = float(np.sum((convective + band) * wallArea))
    powerOut = float(np.sum(emitted * wallArea))
    jointPower = float(np.sum(conduction * wallArea))
    balance = abs(powerIn - powerOut + jointPower) / abs(powerIn) if powerIn != 0.0 else 0.0

    conductivity = np.array([_shellConductivity(shell.thermalConductivity, value)
                             for value in wallTemperature])
    throughThickness = np.abs(convective + band) * shell.thickness / conductivity

    limit, margin = None, None
    if shell.material is not None:
        from .materials import maxUseTemperature
        limit = maxUseTemperature(shell.material, shell.atmosphere) + 273.15
        margin = limit - float(np.max(wallTemperature))

    return RadiativeExtensionResult(
        axialPosition                   = axialPosition,
        radius                          = radius,
        extensionWallTemperature        = wallTemperature,
        extensionEquilibriumTemperature = equilibrium,
        extensionConvectiveCoefficient  = coefficient,
        extensionConvectiveFlux         = convective,
        extensionGasRadiativeFlux       = band,
        extensionEmittedFlux            = emitted,
        extensionConductionFlux         = conduction,
        extensionThroughThicknessDrop   = throughThickness,
        extensionPeakWallTemperature    = float(np.max(wallTemperature)),
        extensionTemperatureLimit       = limit,
        extensionTemperatureMargin      = margin,
        extensionEnergyBalanceResidual  = balance,
        iterations                      = iterations,
        residual                        = update,
        converged                       = converged)
