
# -- NOVA: Film Cooling -- #

'''

A sheet of coolant injected along the wall, and the temperature the wall then sees.

Film cooling does not remove heat from the wall the way a jacket does. It changes the
temperature the wall is driven by. A tangential sheet of cool gas leaving a slot sits between
the exhaust and the wall, mixes with the core as it goes, and warms until it is
indistinguishable from the gas around it. Over the length where it survives, the adiabatic wall
temperature is somewhere between the coolant and the exhaust, and the whole of the model is a
statement of where.

That is expressed as a film cooling effectiveness,

    eta = (T_aw - T_wall,film) / (T_aw - T_coolant)

which is one at the slot and decays to zero far downstream. The driving temperature the thermal
model uses becomes

    T_drive = T_aw - eta (T_aw - T_coolant)

so with no film it is the adiabatic wall temperature and the jacket sees exactly what it saw
before.

Two closures are here and `filmCoolingModel` chooses between them.

`hatchPapell`, the default, is the correlation of Hatch and Papell, NASA TN D-130. It is the
default for one reason: it arrives with a stated accuracy from its own source, five percent on
wall temperature over an effectiveness range of 0.2 to 1.0, and it is the only film cooling
closure found that does. It was fitted on a flat plate in a constant-area duct and can see
neither acceleration nor flow turning.

`sp8124Entrainment` is the gas film model of NASA SP-8124 Appendix A. It treats the film as a
mixing layer that starts holding all the coolant and entrains core flow as it runs. It puts
acceleration and turning into an empirical multiplier that varies with position. That
multiplier is a design-chart recommendation with no stated scatter, so this closure is
calibrated to SP-8124 rather than validated. It knows two things the correlation cannot: the
specific heat of the coolant, which matters enormously for hydrogen, and the mixture ratio of
the gas left at the wall.

**The two closures disagree by a wide margin.** On the LOX/LH2 reference engine with 0.30 kg/s
of hydrogen, the correlation gives a peak driving temperature of 3228 K and the entrainment
model 2548 K. Neither is validated at rocket conditions and the spread between them is a fair
statement of how well film cooling is known here.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**The correlation is implemented as published and validated against its own stated accuracy.**
Hatch and Papell derive it from a heat balance on a discrete coolant layer and then fit two
empirical groups to measurements from the NASA film-cooling facility. tests/testFilmCooling.py
reproduces the equation, its limits and its shape, and checks the velocity-ratio correction is
continuous where its two branches meet.

**The property correction is derived rather than cited.** It is not conservative. Assumption 6
of the source evaluates every property at the mean of the gas and coolant temperatures. A
station carries them at the gas temperature, so `referenceTemperatureCorrection` moves them
with a property ratio rather than a second gas solve, which is the device Bartz uses. Its
exponents are fitted from CEA solves at frozen composition rather than taken from a source, and
the net power reaching the answer stays inside 0.394 to 0.431 across hydrogen, kerosene and
methane at two mixture ratios and two chamber pressures. On a LOX/LH2 case the correction runs
1.26 to 1.30, so it lowers effectiveness. Reading the conductivity alone suggests the opposite
and is wrong: the density and viscosity move Re^0.8 further than the conductivity moves.

**One part of assumption 6 is still outstanding.** The conductivity a station supplies is the
equilibrium value, whose reaction contribution is a factor of 2.7 at 3398 K and 1.4 by 2269 K
and has vanished by the film mean temperature. A Colburn form fitted on non-reacting air
contemplates the molecular conductivity instead. Near a slot in the chamber that difference is
larger than the reference-temperature effect and runs the other way, so effectiveness there is
understated. Removing it needs a frozen-composition solve at every station, which no other
consumer of those arrays wants. It raises the same question for Bartz.

**NOVA uses it far outside the conditions it was fitted to.** That is the dominant uncertainty
here. The data cover a flat plate with a main gas stream from 502 to 1965 degR, which is 279 to
1092 K, at 104 to 1040 ft/s, which is 32 to 317 m/s, with slot heights from 1/16 to 1/2 inch,
and air or helium as the coolant. A rocket nozzle runs at three thousand kelvin and several
times the speed of sound, through a throat where the flow accelerates hard. Every one of those
is an extrapolation. SP-8124 says plainly that acceleration and flow turning are very
significant for film cooling and that accounting for them is the key to predicting coolant
requirements; this correlation accounts for neither.

**What "accounts for neither" does and does not mean.** Acceleration does reach the transfer
group, because the local coefficient carries the local velocity: on the LOX/LH2 reference case
the coefficient rises by a factor of 1.74 over the length the film survives. What has no term
at all is the extra entrainment that a pressure gradient and a curved wall drive beyond what
the local Reynolds number already carries, which is the effect SP-8124 absorbs into its
position-dependent entrainment multiplier. The one term here that could have responded, the
velocity-ratio correction, is arctan-bounded at 1 + 0.4 pi/2 and has already spent 86 percent
of its range at a slot in the chamber, so a doubling of core velocity moves it 3 percent.

Relaminarization is not the mechanism. The acceleration parameter K = (nu/U^2) dU/ds peaks at
1.6e-6 on the reference case against the 3e-6 threshold, on both the 60 and 100 station grids,
and no station exceeds it. Wall curvature is the sharper concern: the throat radius of
curvature is 41 mm, and the film is turned through nine degrees of wall angle over the 43 mm it
survives.

**Below an effectiveness of about 0.3 the correlation is pessimistic**, which its own authors
state: measured effectiveness runs above the equation there. That is the safe direction, and a
design that depends on the difference is a design that has run out of film.

**The two-dimensional effects are absent.** The correlation describes a continuous slot. Real
injection is through a ring of discrete orifices, and SP-8124 recommends spacing no wider than
0.3 inch precisely because a coarser ring leaves the wall between the jets uncooled. Nothing
here knows how many holes there are.

**The entrainment model is calibrated rather than validated.** Its own source names the term
that does it. SP-8124 states that acceleration and flow turning are very significant and that
accounting for them is the key to predicting coolant requirements. It does not model them. It
absorbs them into psi_m, an empirical multiplier of 3 to 4 at injection falling to 1.75 at the
throat and along Figure 17 beyond, read from design charts with no scatter attached. Across the
recommended band alone, 3 to 4, the peak driving temperature on the reference engine moves 96
K. That is the uncertainty the model carries before anything else is considered.

**Its non-reactive branch is exact at both ends.** With no film it
reproduces the station solve's own recovery temperature to the bit; with a wall bathed in pure
coolant it returns the coolant's recovery temperature at the core velocity. Two figures are
digitized rather than transcribed: Figure 17 above, and the branch of Figure A-1 above a
velocity ratio of one, which matters only outside SP-8124's own recommended injection band of
0.9 to 1.15. Figure A-2 prints both of its limits and those are exact; the band between them is
interpolated here and the source gives only a plotted curve to check it against.

**The reactive branch of Appendix A is not implemented.** It reads a temperature off the wall
mixture ratio and the wall enthalpy through an equilibrium solve, which is what would capture a
fuel-rich wall burning cooler than dilution alone predicts. Leaving it out is conservative: the
non-reactive branch returns a hotter wall. The wall mixture ratio is computed and reported
anyway, because a wall running oxidiser-rich is a wall that burns whatever its temperature
says.

**Appendix B, the liquid film model, is not implemented.** Two of its inputs are curves on a
rotated scanned figure, B-1, that cannot be digitized here to an accuracy worth carrying, and
the chain from them to the film length is multiplicative through a Stanton number, a surface
tension, a saturation loop on the coolant partial pressure and a heat-transfer augmentation
factor. Unlike Appendix A, which is dimensionless throughout, Appendix B is an explicitly
dimensional correlation in US customary units with the gravitational constant written into it,
and it states that only the numerical values of those units may be used. Implementing it from a
scan without a worked example to check against would produce a number nothing could verify.

**The blowing correction is off by default, to avoid counting the film twice.** Hatch and
Papell measured the adiabatic wall temperature with a film present, so the film's effect on the
wall is already inside the effectiveness. Applying a transpiration blowing correction to the
gas-side coefficient on top of it would reduce the flux twice for the same physical cause. The
jacket model can take a film mass flux. That path exists for distributed injection and for an
ablative's pyrolysis gas, which are genuinely different.

All units are mass base SI:
    - Length      [m]
    - Temperature [K]
    - Velocity    [m/s]
    - Mass flow   [kg/s]

Author: Sean Bowman

'''

from dataclasses import dataclass
from typing import Any

import numpy as np

from .errors import InvalidInputError
from .fluidProperties import fluidProps

__all__ = [
    'FILMCONDUCTIVITYEXPONENT', 'FILMPRANDTLEXPONENT', 'FILMVISCOSITYEXPONENT',
    'FilmCoolantState', 'FilmCoolingResult', 'HATCHPAPELLONSET',
    'SP8124EFFECTIVENESSASYMPTOTE', 'SP8124EFFECTIVENESSONSET',
    'SP8124EXPANSIONMULTIPLIER', 'SP8124INJECTIONMULTIPLIER', 'SP8124THROATMULTIPLIER',
    'SP8124VELOCITYFUNCTION', 'entrainmentAdiabaticWallTemperature',
    'entrainmentEffectiveness', 'entrainmentFilmArrays', 'entrainmentMultiplier',
    'filmCoolantState', 'filmCoolingArrays', 'filmDrivingTemperature',
    'filmTransferCoefficient', 'hatchPapellEffectiveness', 'referenceEntrainmentFraction',
    'referenceTemperatureCorrection', 'velocityRatioCorrection', 'velocityRatioFunction',
    'wallMixtureRatio',
]

# The correlating group below which the wall has not yet warmed above the coolant, so the
# effectiveness is exactly one. Hatch and Papell's equation (12a), where it comes out of fitting
# the distance the gas travels before heat diffuses through the film.
HATCHPAPELLONSET = 0.04

# Transport power laws for a rocket exhaust, k ~ T^a, mu ~ T^b, Pr ~ T^c, used to move the
# correlation's properties from the gas temperature to the film mean temperature.
#
# Fitted over 900 to 3600 K from CEA solves at frozen composition, which sweeps temperature by
# expansion while holding the mixture fixed. Fitting across nozzle stations instead would
# confound the temperature dependence with the composition and pressure changes along the
# contour, which is why the sweep is run separately.
#
#     propellant                a       b       c     net power on h
#     LH2 / LOX, O/F 5.5     1.000   0.816   0.071        -0.431
#     LH2 / LOX, O/F 7.0     1.053   0.813   0.011        -0.394
#     LH2 / LOX, 2 MPa       0.997   0.808   0.065        -0.430
#     RP-1 / LOX, O/F 2.4    0.979   0.739  -0.058        -0.429
#     CH4 / LOX, O/F 3.4     1.030   0.758  -0.068        -0.397
#
# The defaults are the mean of those five. The spread matters less than it looks: the net power
# is what reaches the answer, and across hydrogen, kerosene and methane at two mixture ratios and
# two chamber pressures it stays within 0.394 to 0.431, which is a two percent spread in the
# correction itself. A propellant far outside that set can override the three exponents.
FILMCONDUCTIVITYEXPONENT = 1.01
FILMVISCOSITYEXPONENT    = 0.79
FILMPRANDTLEXPONENT      = 0.00

# -- NASA SP-8124 Appendix A, the entrainment model -- #
#
# Unlike Appendix B, every group here is dimensionless, so the model works in SI directly with no
# unit bookkeeping. Appendix B is an explicitly dimensional correlation in US customary units and
# is not implemented.

# The empirical entrainment fraction multiplier psi_m, which is where SP-8124 puts the effects of
# rocket turbulence, injection configuration, flow turning and acceleration. Section 3.5.2
# recommends 3 to 4 at the injection point, decaying linearly with axial distance through the
# convergent section to about 1.75 at the throat.
SP8124INJECTIONMULTIPLIER = 3.5
SP8124THROATMULTIPLIER    = 1.75

# Figure 17, psi_m against area ratio in the expansion section. The two ends are stated in the
# body text, 1.75 at the throat and roughly 0.35 by area ratio 28; the interior points are read
# off the plotted curve and carry a read error that is not quantified.
SP8124EXPANSIONMULTIPLIER = (
    (1.0, 1.75), (4.0, 1.34), (8.0, 0.95), (12.0, 0.71),
    (16.0, 0.56), (20.0, 0.47), (24.0, 0.40), (28.0, 0.35))

# Figure A-1, the velocity-ratio correlation function f. Below a ratio of one the figure states
# the form exactly, f = (u_c/u_e)^1.5, so only the branch above one is digitized. Design criteria
# 3.5.3 recommends injecting at a coolant-to-core velocity ratio of 0.9 to 1.15, which is inside
# the exact branch or on its edge, so the digitized half matters only for an off-design film.
SP8124VELOCITYFUNCTION = (
    (1.0, 1.00), (1.2, 1.08), (1.5, 1.05), (2.0, 0.85),
    (3.0, 0.65), (5.0, 0.48), (10.0, 0.33))

# Figure A-2, film-coolant effectiveness against entrainment flow ratio. Both limits are printed
# on the figure and are exact; the band between them is a plotted curve with no equation.
SP8124EFFECTIVENESSONSET     = 0.06
SP8124EFFECTIVENESSASYMPTOTE = 1.4

def filmTransferCoefficient(gasThermalConductivity: float, hydraulicDiameter: float,
                            reynoldsNumber: float, prandtlNumber: float) -> float:

    '''

    The heat transfer coefficient the Hatch and Papell correlating group is built on.

    Their assumption 6: the main gas stream is fully developed turbulent flow, and

        h = 0.0265 (k / D_h) Re^0.8 Pr^0.3

    with every property evaluated at the arithmetic mean of the static gas temperature and the
    coolant slot exit static temperature. That mean matters, and not in the direction the colder
    gas suggests. The conductivity does fall, but at fixed pressure the density rises as 1/T and
    the viscosity falls, and together those raise Re^0.8 by more than the conductivity loses. The
    coefficient at the mean is the larger of the two.

    This is not the coefficient that carries heat into the wall. It is the one that carries heat
    from the core into the film, and it appears only inside the correlating group.

    Parameters:
    -----------
    gasThermalConductivity : float
        Conductivity at the mean of the gas and coolant temperatures [W/m-K].
    hydraulicDiameter : float
        Hydraulic diameter of the duct the film runs along [m].
    reynoldsNumber : float
        Reynolds number at the same mean temperature [-].
    prandtlNumber : float
        Prandtl number at the same mean temperature [-].

    Returns:
    --------
    float
        Film-side heat transfer coefficient [W/m^2 K].

    Raises:
    -------
    InvalidInputError
        If the hydraulic diameter is not positive.

    '''

    if hydraulicDiameter <= 0.0:
        raise InvalidInputError(
            message = 'A duct with no hydraulic diameter carries no film.',
            parameterName = 'hydraulicDiameter',
            value = hydraulicDiameter,
            validRange = 'greater than zero')

    return 0.0265 * (gasThermalConductivity / hydraulicDiameter) \
           * reynoldsNumber**0.8 * prandtlNumber**0.3

def referenceTemperatureCorrection(gasStaticTemperature: float, coolantTemperature: float,
                                   conductivityExponent: float = FILMCONDUCTIVITYEXPONENT,
                                   viscosityExponent: float = FILMVISCOSITYEXPONENT,
                                   prandtlExponent: float = FILMPRANDTLEXPONENT) -> float:

    '''

    Move the film transfer coefficient from free-stream properties to the film mean temperature.

    Hatch and Papell's assumption 6 evaluates every property at the arithmetic mean of the static
    gas temperature and the coolant slot exit temperature. A station solution carries properties
    at the gas temperature alone, so rather than solve the gas a second time the coefficient is
    scaled by the ratio the property variation implies. That is the same device Bartz uses, whose
    sigma is exactly this factor written for his own grouping.

    With T* the mean, k ~ T^a, mu ~ T^b, Pr ~ T^c and the ideal gas at fixed pressure giving
    rho ~ 1/T, the coefficient 0.0265 (k/D) Re^0.8 Pr^0.3 at the two temperatures is in the ratio

        h* / h = (T*/T)^(a - 0.8 - 0.8 b + 0.3 c)

    The velocity and the diameter are the station's own and cancel. The net power is negative for
    every rocket exhaust measured, so a coolant colder than the gas returns a factor greater than
    one: the correlation wants a larger coefficient than free-stream properties give, a larger
    correlating group, and so a lower effectiveness. Reading the conductivity alone suggests the
    opposite, and it is wrong, because the density and viscosity together move Re^0.8 further
    than the conductivity moves.

    A coolant at the gas temperature is no film at all and returns exactly 1.0, which is the
    identity the caller relies on.

    Parameters:
    -----------
    gasStaticTemperature : float
        Core stream static temperature at this station [K].
    coolantTemperature : float
        Coolant static temperature at the slot exit [K].
    conductivityExponent, viscosityExponent, prandtlExponent : float
        Power laws a, b and c above. The defaults are fitted for a rocket exhaust; see the
        module constants for the propellants they cover.

    Returns:
    --------
    float
        Multiplier on the film transfer coefficient [-].

    Raises:
    -------
    InvalidInputError
        If either temperature is not positive.

    '''

    if gasStaticTemperature <= 0.0 or coolantTemperature <= 0.0:
        raise InvalidInputError(
            message = 'A property ratio needs two absolute temperatures.',
            parameterName = 'gasStaticTemperature/coolantTemperature',
            value = (gasStaticTemperature, coolantTemperature),
            validRange = 'both greater than zero')

    meanTemperature = 0.5 * (gasStaticTemperature + coolantTemperature)
    power = conductivityExponent - 0.8 - 0.8 * viscosityExponent + 0.3 * prandtlExponent

    return (meanTemperature / gasStaticTemperature)**power

def velocityRatioCorrection(gasVelocity: float, coolantVelocity: float) -> float:

    '''

    How much a mismatch in velocity between the core and the film costs.

    A film injected at the core velocity mixes least. Faster or slower, the shear between the two
    streams increases and the film breaks up sooner, so the correction is greater than one on
    both sides of a ratio of one and it always reduces effectiveness. Hatch and Papell fit the two
    branches separately, equations (10) and (11):

        f = 1 + 0.4 arctan(V_g/V_c - 1)          for V_g/V_c >= 1
        f = (V_c/V_g)^(1.5 (V_c/V_g - 1))        for V_g/V_c <= 1

    with the arctangent in radians. The two agree at a ratio of one, where both give exactly one.

    SP-8124's design guidance is consistent with this: it recommends a coolant-to-core velocity
    ratio between 0.9 and 1.15 for gaseous injection, which is the band where this correction is
    within a few percent of one.

    Parameters:
    -----------
    gasVelocity : float
        Core stream velocity [m/s].
    coolantVelocity : float
        Coolant velocity at the slot exit [m/s].

    Returns:
    --------
    float
        Correction factor on the correlating group [-]. One at matched velocities, greater
        either side of it.

    Raises:
    -------
    InvalidInputError
        If either velocity is not positive.

    '''

    if gasVelocity <= 0.0 or coolantVelocity <= 0.0:
        raise InvalidInputError(
            message = 'A velocity ratio needs two moving streams.',
            parameterName = 'gasVelocity/coolantVelocity',
            value = (gasVelocity, coolantVelocity),
            validRange = 'both greater than zero')

    ratio = gasVelocity / coolantVelocity

    if ratio >= 1.0:
        return 1.0 + 0.4 * np.arctan(ratio - 1.0)

    inverse = 1.0 / ratio

    return inverse**(1.5 * (inverse - 1.0))

def hatchPapellEffectiveness(transferGroup: float, slotHeight: float, gasVelocity: float,
                             coolantVelocity: float, coolantThermalDiffusivity: float) -> float:

    '''

    Film cooling effectiveness from the Hatch and Papell correlation, NASA TN D-130 equation (12).

        ln eta = - [ X - 0.04 ] (S V_g / alpha_c)^0.125 f(V_g / V_c)

    where X is the dimensionless transfer group h A / (m_dot c_p) built from the film-side
    coefficient, the cooled area from the slot to the station, and the coolant's heat capacity
    rate. Below X = 0.04 the wall has not yet warmed above the coolant and the effectiveness is
    exactly one.

    The middle group is the ratio of directed molecular velocity to heat-diffusion velocity. A
    narrower slot, a slower coolant or a more diffusive coolant all raise it, and all mean more
    of the coolant's mass is doing the absorbing. Note the source's own substitution: the **gas**
    velocity is used inside it, with the velocity-ratio correction carrying the departure from
    matched velocities separately.

    Accuracy, from the source: within five percent on film-cooled wall temperature over an
    effectiveness range of roughly 0.2 to 1.0. Below about 0.3 the equation is pessimistic, which
    is the safe direction to be wrong in.

    Parameters:
    -----------
    transferGroup : float
        h A / (m_dot c_p) for the coolant, from the slot to this station [-].
    slotHeight : float
        Height of the injection slot [m].
    gasVelocity : float
        Core stream velocity [m/s].
    coolantVelocity : float
        Coolant velocity at the slot exit [m/s].
    coolantThermalDiffusivity : float
        Coolant thermal diffusivity at the slot exit static temperature [m^2/s].

    Returns:
    --------
    float
        Effectiveness [-], between zero and one.

    Raises:
    -------
    InvalidInputError
        If the transfer group is negative, or the slot height or diffusivity is not positive.

    '''

    if transferGroup < 0.0:
        raise InvalidInputError(
            message = 'A negative transfer group describes heat flowing out of the core into the '
                      'film upstream of the slot, which is not a film cooling problem.',
            parameterName = 'transferGroup',
            value = transferGroup,
            validRange = 'zero or greater')

    if slotHeight <= 0.0 or coolantThermalDiffusivity <= 0.0:
        raise InvalidInputError(
            message = 'The diffusion group needs a slot with a height and a coolant that '
                      'conducts.',
            parameterName = 'slotHeight/coolantThermalDiffusivity',
            value = (slotHeight, coolantThermalDiffusivity),
            validRange = 'both greater than zero')

    if transferGroup <= HATCHPAPELLONSET:
        return 1.0

    diffusionGroup = (slotHeight * gasVelocity / coolantThermalDiffusivity)**0.125

    exponent = -(transferGroup - HATCHPAPELLONSET) * diffusionGroup \
               * velocityRatioCorrection(gasVelocity, coolantVelocity)

    return float(np.exp(exponent))

def filmDrivingTemperature(adiabaticWallTemperature, effectiveness, coolantTemperature):

    '''

    The temperature the wall is driven by once a film is between it and the exhaust.

        T_drive = T_aw - eta (T_aw - T_coolant)

    which is the definition of effectiveness rearranged. It returns the coolant temperature at an
    effectiveness of one and the adiabatic wall temperature at zero, so a station the film has not
    reached is driven by exactly what it was driven by before, to the bit.

    Parameters:
    -----------
    adiabaticWallTemperature : array_like
        Recovery temperature with no film [K].
    effectiveness : array_like
        Film cooling effectiveness [-].
    coolantTemperature : array_like
        Film coolant temperature [K].

    Returns:
    --------
    numpy.ndarray
        Driving temperature [K].

    '''

    adiabaticWallTemperature = np.asarray(adiabaticWallTemperature, dtype = float)
    effectiveness = np.asarray(effectiveness, dtype = float)
    coolantTemperature = np.asarray(coolantTemperature, dtype = float)

    return adiabaticWallTemperature \
           - effectiveness * (adiabaticWallTemperature - coolantTemperature)

@dataclass
class FilmCoolingResult:

    """

    A film solved along a contour, and the two arrays the thermal model takes from it.

    Attributes:
    -----------
    effectiveness : numpy.ndarray
        Film cooling effectiveness at each station [-]. One from the injection point until the
        wall begins to warm, then decaying. Exactly zero upstream of the slot, where there is no
        film.
    drivingTemperature : numpy.ndarray
        Temperature the wall is driven by [K]. Upstream of the slot this is the recovery
        temperature unchanged, to the bit.
    transferGroup : numpy.ndarray | None
        The dimensionless group the correlation is written in, h A / (m_dot c_p), accumulated
        from the slot [-]. Worth reading: it says how far through its useful range the film is.
        None from the entrainment model, which is not written on that group.
    propertyCorrection : numpy.ndarray | None
        Factor applied to the transfer coefficient at each station to move the gas properties
        from the station temperature to the film mean temperature [-]. One where no film reaches.
        None from the entrainment model, which has no transfer coefficient to correct.
    entrainmentFlowRatio : numpy.ndarray | None
        W_E/W_c, core mass drawn into the mixing layer over film coolant flow [-], from the
        entrainment model. None from Hatch and Papell, which has no entrainment term.
    wallMixtureRatio : numpy.ndarray | None
        Oxidiser to fuel ratio of the gas at the wall [-], from the entrainment model's
        mass-transfer analogy. It falls toward the coolant's own mixture ratio under the
        film, and a wall running oxidiser-rich is a wall that burns whatever its
        temperature says. None from Hatch and Papell.
    entrainmentMultiplier : numpy.ndarray | None
        psi_m at each station [-], the empirical multiplier SP-8124 puts acceleration and
        turning into. Reported because it is the single largest lever in that model and a
        reader should be able to see what it did. None from Hatch and Papell.
    filmMassFlux : numpy.ndarray
        Coolant mass flux at the wall [kg/m^2 s], zero throughout. Slot film cooling puts its
        whole effect into the effectiveness, and blowing the gas-side coefficient as well would
        count the film twice. The array exists so the jacket's interface is the same shape
        whether the film came from a slot or from a transpiring wall.
    injectionIndex : int
        Station the film is injected at.
    survivalLength : float
        Distance from the slot over which the effectiveness stays above 0.3 [m]. Below that the
        correlation is pessimistic by its own authors' account, so it is the honest end of the
        film's useful reach rather than the point it disappears.

    """

    effectiveness:         np.ndarray
    drivingTemperature:    np.ndarray
    filmMassFlux:          np.ndarray
    injectionIndex:        int
    survivalLength:        float
    transferGroup:         Any = None
    propertyCorrection:    Any = None
    entrainmentFlowRatio:  Any = None
    wallMixtureRatio:      Any = None
    entrainmentMultiplier: Any = None

def filmCoolingArrays(axialPosition, radius, gasVelocity, gasStaticTemperature,
                      recoveryTemperature, gasThermalConductivity, gasDensity, gasViscosity,
                      gasPrandtlNumber, injectionPosition: float, slotHeight: float,
                      coolantMassFlow: float, coolantSpecificHeat: float,
                      coolantTemperature: float, coolantThermalDiffusivity: float,
                      coolantVelocity: float,
                      conductivityExponent: float = FILMCONDUCTIVITYEXPONENT,
                      viscosityExponent: float = FILMVISCOSITYEXPONENT,
                      prandtlExponent: float = FILMPRANDTLEXPONENT) -> FilmCoolingResult:

    """

    Solve a film along a nozzle contour and return what the thermal model needs from it.

    The correlation is written for a flat plate with one heat transfer coefficient over a cooled
    area L x. A nozzle is neither flat nor of constant coefficient, so the group is accumulated
    instead:

        X(s) = integral of h dA / (m_dot c_p), from the slot to s

    with dA the wall area of each station, 2 pi r ds. On a flat plate of constant h this reduces
    to the published h L x / (m_dot c_p) exactly, which is the sense in which it is the same
    correlation. On a nozzle it is a generalization, and one the source does not authorize.

    The film marches forward from the slot with the gas. Upstream of it there is no film, and
    those stations come back with the recovery temperature untouched.

    **The properties are supplied at the gas temperature and moved to the film mean temperature
    here**, because assumption 6 of the source evaluates every property at the mean of the gas
    static and coolant temperatures. `referenceTemperatureCorrection` does the move as a property
    ratio rather than a second gas solve, the same device as Bartz's sigma. On the LOX/LH2
    reference case it raises the coefficient by 27 to 32 percent, which lowers effectiveness.

    **One part of assumption 6 is still outstanding.** The conductivity a station carries is the
    equilibrium value, whose reaction contribution is a factor of 2.7 at 3398 K and 1.4 by
    2269 K and has vanished by the film mean temperature. A Colburn form fitted on non-reacting
    air has no such term in it, so the molecular conductivity is the one it contemplates. The
    correction above scales whatever conductivity it is given and cannot remove that
    contribution. Near a slot in the chamber it is the larger of the two effects and it runs the
    other way, so effectiveness there is understated. Removing it needs a frozen-composition
    solve at every station, which no other consumer of these arrays currently wants.

    Parameters:
    -----------
    axialPosition, radius : array_like
        Wall coordinates, ascending in axial position [m].
    gasVelocity : array_like
        Core stream velocity at each station [m/s].
    gasStaticTemperature : array_like
        Core stream static temperature at each station [K]. Half of the film mean temperature
        the properties are corrected to.
    recoveryTemperature : array_like
        Adiabatic wall temperature with no film [K].
    gasThermalConductivity, gasDensity, gasViscosity : array_like
        Gas properties at the gas static temperature [W/m-K], [kg/m^3], [Pa s].
    gasPrandtlNumber : array_like
        Prandtl number at the same temperature [-].
    injectionPosition : float
        Axial position of the slot [m]. The nearest station at or after it is the injection
        point.
    slotHeight : float
        Height of the injection slot [m].
    coolantMassFlow : float
        Film coolant flow [kg/s].
    coolantSpecificHeat : float
        Coolant specific heat [J/kg-K].
    coolantTemperature : float
        Coolant temperature at the slot exit [K].
    coolantThermalDiffusivity : float
        Coolant thermal diffusivity at the slot exit static temperature [m^2/s].
    coolantVelocity : float
        Coolant velocity at the slot exit [m/s].
    conductivityExponent, viscosityExponent, prandtlExponent : float
        Transport power laws for the property correction. The defaults cover rocket exhausts;
        see the module constants.

    Returns:
    --------
    FilmCoolingResult

    Raises:
    -------
    InvalidInputError
        If the station arrays disagree in length, the coolant flow is not positive, or the
        injection point lies downstream of the last station.

    """

    axialPosition = np.asarray(axialPosition, dtype = float)
    radius = np.asarray(radius, dtype = float)
    gasVelocity = np.asarray(gasVelocity, dtype = float)
    staticTemperature = np.asarray(gasStaticTemperature, dtype = float)
    recoveryTemperature = np.asarray(recoveryTemperature, dtype = float)
    conductivity = np.asarray(gasThermalConductivity, dtype = float)
    density = np.asarray(gasDensity, dtype = float)
    viscosity = np.asarray(gasViscosity, dtype = float)
    prandtl = np.asarray(gasPrandtlNumber, dtype = float)

    lengths = {array.size for array in (axialPosition, radius, gasVelocity, staticTemperature,
                                        recoveryTemperature, conductivity, density, viscosity,
                                        prandtl)}
    if len(lengths) != 1:
        raise InvalidInputError(
            message = 'Every station array must describe the same stations.',
            parameterName = 'axialPosition and the property arrays',
            value = sorted(lengths),
            validRange = 'all the same length')

    if coolantMassFlow <= 0.0 or coolantSpecificHeat <= 0.0:
        raise InvalidInputError(
            message = 'A film with no mass flow or no heat capacity cools nothing.',
            parameterName = 'coolantMassFlow/coolantSpecificHeat',
            value = (coolantMassFlow, coolantSpecificHeat),
            validRange = 'both greater than zero')

    downstream = np.flatnonzero(axialPosition >= injectionPosition)
    if downstream.size == 0:
        raise InvalidInputError(
            message = 'The injection point is past the end of the contour, so no station sees '
                      'the film.',
            parameterName = 'injectionPosition',
            value = injectionPosition,
            validRange = 'at or before {:.4f} m'.format(float(axialPosition[-1])))
    injectionIndex = int(downstream[0])

    stations = axialPosition.size
    effectiveness = np.zeros(stations)
    transferGroup = np.zeros(stations)
    propertyCorrection = np.ones(stations)

    # Wall area of each station, from the arc length of the contour rather than the axial step,
    # because the converging and diverging walls are steep enough for the difference to matter.
    arcLength = np.zeros(stations)
    arcLength[1:] = np.sqrt(np.diff(axialPosition)**2 + np.diff(radius)**2)

    heatCapacityRate = coolantMassFlow * coolantSpecificHeat
    accumulated = 0.0

    for index in range(injectionIndex, stations):

        if index > injectionIndex:
            hydraulicDiameter = 2.0 * radius[index]
            reynolds = density[index] * gasVelocity[index] * hydraulicDiameter / viscosity[index]

            # The station supplies properties at the gas temperature; the correlation is written
            # at the mean of the gas and the coolant. The ratio does the move.
            propertyCorrection[index] = referenceTemperatureCorrection(
                staticTemperature[index], coolantTemperature,
                conductivityExponent, viscosityExponent, prandtlExponent)
            coefficient = propertyCorrection[index] * filmTransferCoefficient(
                conductivity[index], hydraulicDiameter, reynolds, prandtl[index])
            area = 2.0 * np.pi * radius[index] * arcLength[index]
            accumulated += coefficient * area / heatCapacityRate

        transferGroup[index] = accumulated
        effectiveness[index] = hatchPapellEffectiveness(
            accumulated, slotHeight, gasVelocity[index], coolantVelocity,
            coolantThermalDiffusivity)

    drivingTemperature = filmDrivingTemperature(
        recoveryTemperature, effectiveness, coolantTemperature)

    useful = np.flatnonzero(effectiveness[injectionIndex:] >= 0.3)
    survivalLength = float(axialPosition[injectionIndex + useful[-1]]
                           - axialPosition[injectionIndex]) if useful.size else 0.0

    return FilmCoolingResult(
        effectiveness      = effectiveness,
        drivingTemperature = drivingTemperature,
        transferGroup      = transferGroup,
        propertyCorrection = propertyCorrection,
        filmMassFlux       = np.zeros(stations),
        injectionIndex     = injectionIndex,
        survivalLength     = survivalLength)

@dataclass
class FilmCoolantState:

    """

    The coolant properties the correlation needs, derived rather than asked for.

    Attributes:
    -----------
    density : float
        Coolant density at the slot [kg/m^3].
    specificHeat : float
        Coolant specific heat at the slot [J/kg-K].
    thermalConductivity : float
        Coolant thermal conductivity at the slot [W/m-K].
    viscosity : float
        Coolant dynamic viscosity at the slot [Pa s]. Only the entrainment model reads it,
        for the Reynolds number it builds on the slot height.
    thermalDiffusivity : float
        Coolant thermal diffusivity at the slot [m^2/s], which is what the correlation's
        diffusion group is written in.
    velocity : float
        Coolant velocity leaving the slot [m/s], from the mass flow and the slot area.
    slotArea : float
        Flow area of the annular slot [m^2].

    """

    density:             float
    specificHeat:        float
    thermalConductivity: float
    viscosity:           float
    thermalDiffusivity:  float
    velocity:            float
    slotArea:            float

def filmCoolantState(species: str, temperature: float, pressure: float, massFlow: float,
                     slotHeight: float, slotRadius: float) -> FilmCoolantState:

    """

    Coolant state at the slot, from the species and the geometry it leaves through.

    Three of the five quantities the correlation wants are properties of the coolant at its own
    slot conditions, and the other two follow from the slot area. Asking a user for a thermal
    diffusivity and a slot velocity separately invites the two to disagree with each other and
    with the mass flow; deriving them cannot.

    The slot is taken as an annulus of the given height around the wall, so its area is
    `2 pi r S`. That is the geometry SP-8124 recommends for gaseous injection, a continuous slot
    with ribs no thicker than structure requires.

    Parameters:
    -----------
    species : str
        Coolant name, as `utils.fluidProps` takes it.
    temperature : float
        Coolant temperature at the slot [K].
    pressure : float
        Static pressure at the slot [Pa].
    massFlow : float
        Film coolant flow [kg/s].
    slotHeight : float
        Radial height of the slot [m].
    slotRadius : float
        Wall radius at the slot [m].

    Returns:
    --------
    FilmCoolantState

    Raises:
    -------
    InvalidInputError
        If the slot has no area, the flow is not positive, or the property call returns something
        unusable.

    """

    if slotHeight <= 0.0 or slotRadius <= 0.0:
        raise InvalidInputError(
            message = 'A slot with no height or no radius has no area to inject through.',
            parameterName = 'slotHeight/slotRadius',
            value = (slotHeight, slotRadius),
            validRange = 'both greater than zero')

    if massFlow <= 0.0:
        raise InvalidInputError(
            message = 'A film with no mass flow cools nothing.',
            parameterName = 'massFlow',
            value = massFlow,
            validRange = 'greater than zero')

    density, specificHeat, conductivity, viscosity = fluidProps(
        species, 'TP', 'D Cp TCX VIS', temperature, pressure)

    density = float(np.atleast_1d(density)[0])
    specificHeat = float(np.atleast_1d(specificHeat)[0])
    conductivity = float(np.atleast_1d(conductivity)[0])
    viscosity = float(np.atleast_1d(viscosity)[0])

    if not all(np.isfinite(value) and value > 0.0
               for value in (density, specificHeat, conductivity, viscosity)):
        raise InvalidInputError(
            message = 'The coolant property lookup returned something unusable at {} K and '
                      '{:.0f} Pa. A film coolant has to be a gas at its slot conditions; a '
                      'two-phase or supercritical state is outside what this closure '
                      'describes.'.format(temperature, pressure),
            parameterName = 'species/temperature/pressure',
            value = (species, temperature, pressure),
            validRange = 'a single-phase gas')

    slotArea = 2.0 * np.pi * slotRadius * slotHeight

    return FilmCoolantState(
        density             = density,
        specificHeat        = specificHeat,
        thermalConductivity = conductivity,
        viscosity           = viscosity,
        thermalDiffusivity  = conductivity / (density * specificHeat),
        velocity            = massFlow / (density * slotArea),
        slotArea            = slotArea)

def entrainmentMultiplier(areaRatio: float, convergentFraction: float = None,
                          injectionMultiplier: float = SP8124INJECTIONMULTIPLIER) -> float:

    '''

    The empirical entrainment fraction multiplier psi_m at one station.

    This is the term SP-8124 says is the key to predicting film coolant requirements, and it is
    where the monograph puts the effects it declines to model directly: rocket turbulence, the
    injection configuration, flow turning and acceleration. It is a recommendation read off a
    design chart, not a measured curve with stated scatter, so a result that depends on it is
    calibrated to SP-8124 rather than validated.

    Through the convergent section it falls linearly with axial distance from the injection value
    to 1.75 at the throat. Downstream it follows Figure 17 against area ratio.

    Parameters:
    -----------
    areaRatio : float
        Local area ratio [-]. Only read downstream of the throat.
    convergentFraction : float | None
        Fraction of the axial distance from the slot to the throat, zero at the slot and one at
        the throat [-]. None means the station is past the throat.
    injectionMultiplier : float
        psi_m at the slot [-]. SP-8124 recommends 3 to 4.

    Returns:
    --------
    float
        Entrainment fraction multiplier [-].

    Raises:
    -------
    InvalidInputError
        If the injection multiplier is not positive.

    '''

    if injectionMultiplier <= 0.0:
        raise InvalidInputError(
            message = 'An entrainment multiplier of zero means a film that never mixes, which is '
                      'not what the model describes.',
            parameterName = 'injectionMultiplier',
            value = injectionMultiplier,
            validRange = 'greater than zero, and 3 to 4 by SP-8124 3.5.2')

    if convergentFraction is not None:
        fraction = min(max(convergentFraction, 0.0), 1.0)
        return injectionMultiplier + fraction * (SP8124THROATMULTIPLIER - injectionMultiplier)

    ratios = [point[0] for point in SP8124EXPANSIONMULTIPLIER]
    values = [point[1] for point in SP8124EXPANSIONMULTIPLIER]

    return float(np.interp(areaRatio, ratios, values))

def velocityRatioFunction(velocityRatio: float) -> float:

    '''

    Figure A-1, the velocity-ratio correlation function f in the reference entrainment fraction.

    Below a matched velocity the figure prints the form, f = (u_c/u_e)^1.5, and that branch is
    exact. Above it the function turns over and falls, and those values are digitized.

    f sits in the denominator of psi_r, so a small f means a large entrainment fraction. A film
    injected much slower than the core has a large velocity difference across its shear layer and
    mixes hard, which is why SP-8124 recommends injecting at a ratio of 0.9 to 1.15.

    Parameters:
    -----------
    velocityRatio : float
        Coolant velocity over core velocity, u_c/u_e [-].

    Returns:
    --------
    float
        Correlation function f [-].

    Raises:
    -------
    InvalidInputError
        If the velocity ratio is not positive.

    '''

    if velocityRatio <= 0.0:
        raise InvalidInputError(
            message = 'A film with no velocity does not leave the slot.',
            parameterName = 'velocityRatio',
            value = velocityRatio,
            validRange = 'greater than zero')

    if velocityRatio <= 1.0:
        return velocityRatio**1.5

    ratios = [point[0] for point in SP8124VELOCITYFUNCTION]
    values = [point[1] for point in SP8124VELOCITYFUNCTION]

    return float(np.interp(velocityRatio, ratios, values))

def referenceEntrainmentFraction(coolantVelocity: float, coreVelocity: float,
                                 coolantDensity: float, coreDensity: float,
                                 coolantViscosity: float, slotHeight: float) -> float:

    '''

    psi_r, the plane unaccelerated continuous-slot entrainment fraction of Appendix A.

        psi_r = 0.1 (u_c/u_e) / [ (rho_c/rho_e)^0.15 (rho_c u_c s_i / mu_c)^0.25 f ]

    Every group is dimensionless, so the expression holds in SI without conversion. All of the
    position dependence in the model is carried by psi_m and by the effective contour distance, so
    this is evaluated once at the injection station and held.

    Parameters:
    -----------
    coolantVelocity, coreVelocity : float
        Velocities at the slot [m/s].
    coolantDensity, coreDensity : float
        Densities at the slot [kg/m^3].
    coolantViscosity : float
        Coolant dynamic viscosity at the slot [Pa s].
    slotHeight : float
        Mixing layer height at injection, which is the slot height [m].

    Returns:
    --------
    float
        Reference entrainment fraction [-].

    Raises:
    -------
    InvalidInputError
        If any input is not positive.

    '''

    values = (coolantVelocity, coreVelocity, coolantDensity, coreDensity, coolantViscosity,
              slotHeight)
    if any(value <= 0.0 for value in values):
        raise InvalidInputError(
            message = 'The reference entrainment fraction needs a real slot with real flow '
                      'through it on both sides.',
            parameterName = 'the slot conditions',
            value = values,
            validRange = 'all greater than zero')

    velocityRatio = coolantVelocity / coreVelocity
    slotReynolds = coolantDensity * coolantVelocity * slotHeight / coolantViscosity

    return 0.1 * velocityRatio / ((coolantDensity / coreDensity)**0.15
                                  * slotReynolds**0.25
                                  * velocityRatioFunction(velocityRatio))

def entrainmentEffectiveness(entrainmentFlowRatio: float) -> float:

    '''

    Figure A-2, film-coolant effectiveness as a function of entrainment flow ratio.

    The figure prints both limits and they are reproduced exactly:

        eta = 1                        for W_E/W_c below 0.06
        eta = 1.32 / (1 + W_E/W_c)     for W_E/W_c above 1.4

    Between them the source gives a plotted curve and no equation. What is used here is a cubic
    Hermite in the logarithm of the abscissa, flat where it leaves one and matching the value and
    slope of the asymptotic form where it joins it. That construction is not the source's, and
    the error against its plotted curve is not quantified. It is bounded: effectiveness in the
    band lies between 0.55 and 1.0, so the driving temperature it produces is bracketed.

    Clipping the asymptotic form at one instead would have been simpler and is wrong in the
    unsafe direction. That form reaches one only at a ratio of 0.32, while the source says
    effectiveness leaves one at 0.06, so the real curve drops earlier than the formula does.

    Parameters:
    -----------
    entrainmentFlowRatio : float
        W_E/W_c, core mass entrained into the mixing layer over film coolant flow [-].

    Returns:
    --------
    float
        Film-coolant effectiveness [-].

    Raises:
    -------
    InvalidInputError
        If the ratio is negative.

    '''

    if entrainmentFlowRatio < 0.0:
        raise InvalidInputError(
            message = 'A negative entrainment flow ratio describes coolant leaving the mixing '
                      'layer, which the model has no branch for.',
            parameterName = 'entrainmentFlowRatio',
            value = entrainmentFlowRatio,
            validRange = 'zero or greater')

    if entrainmentFlowRatio <= SP8124EFFECTIVENESSONSET:
        return 1.0

    if entrainmentFlowRatio >= SP8124EFFECTIVENESSASYMPTOTE:
        return 1.32 / (1.0 + entrainmentFlowRatio)

    lower = np.log10(SP8124EFFECTIVENESSONSET)
    upper = np.log10(SP8124EFFECTIVENESSASYMPTOTE)
    span = upper - lower
    position = (np.log10(entrainmentFlowRatio) - lower) / span

    # Value and slope of the asymptotic form where the interpolation joins it, the slope taken
    # with respect to the same logarithmic abscissa the interpolation runs on.
    joinValue = 1.32 / (1.0 + SP8124EFFECTIVENESSASYMPTOTE)
    joinSlope = -1.32 / (1.0 + SP8124EFFECTIVENESSASYMPTOTE)**2 \
                * SP8124EFFECTIVENESSASYMPTOTE * np.log(10.0)

    return float((2.0 * position**3 - 3.0 * position**2 + 1.0) * 1.0
                 + (-2.0 * position**3 + 3.0 * position**2) * joinValue
                 + (position**3 - position**2) * span * joinSlope)

def wallMixtureRatio(effectiveness: float, coreMixtureRatio: float,
                     coolantMixtureRatio: float = 0.0) -> float:

    '''

    Mixture ratio of the gas at the wall, from the mass-transfer analogy of Appendix A.

        (MR)_w = (1 + (MR)_e) / (1 + eta ((1 + (MR)_e)/(1 + (MR)_c) - 1)) - 1

    This is the reason to prefer the entrainment model over a flat-plate correlation. A fuel film
    leaves the wall gas fuel-rich, and a fuel-rich gas has a lower flame temperature, so the
    adiabatic wall temperature falls by more than dilution alone would give. Nothing here uses
    that yet: reading a temperature off the wall mixture ratio is the reactive model, which needs
    an equilibrium solve at a shifted mixture ratio. The ratio is returned so a design can be
    judged on it, because a wall running at an oxidiser-rich local mixture ratio is a wall that
    burns whatever the temperature says.

    Parameters:
    -----------
    effectiveness : float
        Entrainment effectiveness at this station [-].
    coreMixtureRatio : float
        Oxidiser to fuel ratio of the core [-].
    coolantMixtureRatio : float
        Oxidiser to fuel ratio of the film coolant [-]. Zero is a pure fuel film, which is the
        usual case; numpy.inf is a pure oxidiser film and the formula handles it.

    Returns:
    --------
    float
        Mixture ratio at the wall [-].

    Raises:
    -------
    InvalidInputError
        If either mixture ratio is negative or the effectiveness is outside zero to one.

    '''

    if coreMixtureRatio < 0.0 or coolantMixtureRatio < 0.0:
        raise InvalidInputError(
            message = 'A mixture ratio is a mass ratio and cannot be negative.',
            parameterName = 'coreMixtureRatio/coolantMixtureRatio',
            value = (coreMixtureRatio, coolantMixtureRatio),
            validRange = 'zero or greater')

    if not 0.0 <= effectiveness <= 1.0:
        raise InvalidInputError(
            message = 'An effectiveness outside zero to one describes a wall gas that is more '
                      'than pure coolant or less than pure core.',
            parameterName = 'effectiveness',
            value = effectiveness,
            validRange = 'zero to one inclusive')

    coreGroup = 1.0 + coreMixtureRatio
    coolantGroup = 1.0 + coolantMixtureRatio

    return coreGroup / (1.0 + effectiveness * (coreGroup / coolantGroup - 1.0)) - 1.0

def entrainmentAdiabaticWallTemperature(effectiveness: float, totalTemperature: float,
                                        recoveryTemperature: float, coreSpecificHeat: float,
                                        coolantSpecificHeat: float,
                                        coolantTotalTemperature: float) -> float:

    '''

    The non-reactive adiabatic wall temperature of Appendix A.

        T_aw = T_o,e - [ eta C_p,c (T_o,e - T_c) + (1 - Pr^1/3)(H_o,e - H_e) ]
                       / [ eta C_p,c + (1 - eta) C_p,e ]

    written here with the recovery temperature standing in for the enthalpy defect, since
    (1 - Pr^1/3)(H_o,e - H_e) is C_p,e (T_o,e - T_recovery) by definition. That substitution is
    what makes the two limits exact rather than nearly right:

        eta = 0 returns the recovery temperature, to the bit
        eta = 1 returns the coolant's own recovery temperature at the core velocity

    The second limit is why T_c is read as a total temperature rather than a static one. The
    source writes it against H_o,e in a difference of total enthalpies, and only that reading
    makes a wall bathed in pure coolant sit at the coolant's recovery temperature instead of
    below it.

    The reactive model of the source is not implemented. It reads a temperature off the wall
    mixture ratio and the wall enthalpy through an equilibrium solve, and it is the half of
    Appendix A that would capture a fuel-rich wall burning cooler than dilution alone predicts.
    Leaving it out is conservative: it gives a hotter wall than the reactive model would.

    Parameters:
    -----------
    effectiveness : float
        Entrainment effectiveness at this station [-].
    totalTemperature : float
        Local total temperature of the core [K].
    recoveryTemperature : float
        Adiabatic wall temperature with no film [K].
    coreSpecificHeat, coolantSpecificHeat : float
        Specific heats at constant pressure [J/kg-K].
    coolantTotalTemperature : float
        Total temperature of the coolant at the slot [K].

    Returns:
    --------
    float
        Adiabatic wall temperature with the film present [K].

    Raises:
    -------
    InvalidInputError
        If either specific heat is not positive or the effectiveness is outside zero to one.

    '''

    if coreSpecificHeat <= 0.0 or coolantSpecificHeat <= 0.0:
        raise InvalidInputError(
            message = 'A stream with no heat capacity carries no enthalpy, so the mixing balance '
                      'has nothing to balance.',
            parameterName = 'coreSpecificHeat/coolantSpecificHeat',
            value = (coreSpecificHeat, coolantSpecificHeat),
            validRange = 'both greater than zero')

    if not 0.0 <= effectiveness <= 1.0:
        raise InvalidInputError(
            message = 'An effectiveness outside zero to one describes a wall gas that is more '
                      'than pure coolant or less than pure core.',
            parameterName = 'effectiveness',
            value = effectiveness,
            validRange = 'zero to one inclusive')

    denominator = effectiveness * coolantSpecificHeat \
                  + (1.0 - effectiveness) * coreSpecificHeat
    numerator = effectiveness * coolantSpecificHeat \
                * (totalTemperature - coolantTotalTemperature) \
                + coreSpecificHeat * (totalTemperature - recoveryTemperature)

    return totalTemperature - numerator / denominator

def entrainmentFilmArrays(axialPosition, radius, gasVelocity, gasDensity, totalTemperature,
                          recoveryTemperature, coreSpecificHeat, massFluxRatio,
                          injectionPosition: float, slotHeight: float,
                          coreMassFlow: float, coolantMassFlow: float,
                          coolantDensity: float, coolantVelocity: float,
                          coolantViscosity: float, coolantSpecificHeat: float,
                          coolantTotalTemperature: float,
                          coreMixtureRatio: float, coolantMixtureRatio: float = 0.0,
                          injectionMultiplier: float = SP8124INJECTIONMULTIPLIER
                          ) -> FilmCoolingResult:

    """

    Solve a gaseous film along a nozzle contour by the entrainment model of SP-8124 Appendix A.

    The film is treated as a mixing layer that starts holding all of the coolant and entrains core
    flow as it runs. What sets the wall temperature is how much core has been drawn in, so the
    march accumulates an effective contour distance

        xbar(s) = integral of (r_i/r) ((rho_e u_e)_2D / (rho_e u_e)_1D) psi_m ds

    from the slot, and the entrained fraction of the core follows

        W_E/W_c = ((W - W_c)/W_c) [ 2 z - z^2 ],   z = psi_r xbar / (r_i - s_i)

    The bracket is the fraction of the core the mixing layer has swallowed, and it reaches one at
    z = 1, where the layer has grown to the axis. Beyond that the parabola turns over, which would
    say a film entrains less the further it goes, so z is held at one. The source does not say to
    do this; it is what the expression means.

    **This model exists because Hatch and Papell cannot see acceleration or turning.** SP-8124
    does not model them either. It absorbs them into psi_m, an empirical multiplier that varies
    with position precisely because acceleration and turning do. Choosing this closure trades a
    stated accuracy for a design chart, so its results are calibrated to SP-8124's recommendation
    rather than validated.

    Parameters:
    -----------
    axialPosition, radius : array_like
        Wall coordinates, ascending in axial position [m].
    gasVelocity, gasDensity : array_like
        Core stream velocity [m/s] and density [kg/m^3] at each station.
    totalTemperature, recoveryTemperature : array_like
        Local total temperature and film-free adiabatic wall temperature at each station [K].
        Build the first the same way the second was built, or the zero-effectiveness limit stops
        being exact.
    coreSpecificHeat : array_like
        Core specific heat at constant pressure at each station [J/kg-K].
    massFluxRatio : array_like
        Two-dimensional over one-dimensional core mass flux at each station [-]. SP-8124 carries
        this because entrainment follows the real near-wall mass flux rather than the nominal
        one, and on a nozzle the two differ by tens of percent.
    injectionPosition : float
        Axial position of the slot [m].
    slotHeight : float
        Mixing layer height at injection, which is the slot height [m].
    coreMassFlow, coolantMassFlow : float
        Core flow past the film and film coolant flow [kg/s]. The source writes the first as
        W - W_c; passing it directly avoids any question of whether the film is inside W.
    coolantDensity, coolantVelocity, coolantViscosity, coolantSpecificHeat : float
        Coolant properties at the slot [kg/m^3], [m/s], [Pa s], [J/kg-K].
    coolantTotalTemperature : float
        Coolant total temperature at the slot [K].
    coreMixtureRatio, coolantMixtureRatio : float
        Oxidiser to fuel ratios [-]. Zero coolant mixture ratio is a pure fuel film.
    injectionMultiplier : float
        psi_m at the slot [-]. SP-8124 recommends 3 to 4, and it is the single largest lever in
        the model.

    Returns:
    --------
    FilmCoolingResult
        With `entrainmentFlowRatio` and `wallMixtureRatio` filled and `transferGroup` and
        `propertyCorrection` left as None, both being Hatch and Papell quantities.

    Raises:
    -------
    InvalidInputError
        If the station arrays disagree in length, either flow is not positive, or the injection
        point lies downstream of the last station.

    """

    axialPosition = np.asarray(axialPosition, dtype = float)
    radius = np.asarray(radius, dtype = float)
    velocity = np.asarray(gasVelocity, dtype = float)
    density = np.asarray(gasDensity, dtype = float)
    total = np.asarray(totalTemperature, dtype = float)
    recovery = np.asarray(recoveryTemperature, dtype = float)
    specificHeat = np.asarray(coreSpecificHeat, dtype = float)
    fluxRatio = np.asarray(massFluxRatio, dtype = float)

    lengths = {array.size for array in (axialPosition, radius, velocity, density, total,
                                        recovery, specificHeat, fluxRatio)}
    if len(lengths) != 1:
        raise InvalidInputError(
            message = 'Every station array must describe the same stations.',
            parameterName = 'axialPosition and the station arrays',
            value = sorted(lengths),
            validRange = 'all the same length')

    if coolantMassFlow <= 0.0 or coreMassFlow <= 0.0:
        raise InvalidInputError(
            message = 'The entrainment ratio is written on the flow of both streams, so neither '
                      'can be absent.',
            parameterName = 'coreMassFlow/coolantMassFlow',
            value = (coreMassFlow, coolantMassFlow),
            validRange = 'both greater than zero')

    downstream = np.flatnonzero(axialPosition >= injectionPosition)
    if downstream.size == 0:
        raise InvalidInputError(
            message = 'The injection point is past the end of the contour, so no station sees '
                      'the film.',
            parameterName = 'injectionPosition',
            value = injectionPosition,
            validRange = 'at or before {:.4f} m'.format(float(axialPosition[-1])))
    injectionIndex = int(downstream[0])

    if slotHeight >= radius[injectionIndex]:
        raise InvalidInputError(
            message = 'A mixing layer as tall as the chamber radius leaves no core for the film '
                      'to sit against, and the model divides by what is left.',
            parameterName = 'slotHeight',
            value = slotHeight,
            validRange = 'less than {:.4f} m at the slot'.format(float(radius[injectionIndex])))

    stations = axialPosition.size
    throatIndex = int(np.argmin(radius))
    throatRadius = float(radius[throatIndex])
    areaRatio = (radius / throatRadius)**2

    arcLength = np.zeros(stations)
    arcLength[1:] = np.sqrt(np.diff(axialPosition)**2 + np.diff(radius)**2)

    referenceFraction = referenceEntrainmentFraction(
        coolantVelocity, float(velocity[injectionIndex]), coolantDensity,
        float(density[injectionIndex]), coolantViscosity, slotHeight)

    effectiveness = np.zeros(stations)
    flowRatio = np.zeros(stations)
    multiplier = np.zeros(stations)
    adiabaticWall = recovery.copy()
    mixtureRatio = np.full(stations, coreMixtureRatio)

    coreRatio = coreMassFlow / coolantMassFlow
    slotRadius = float(radius[injectionIndex])
    accumulated = 0.0

    for index in range(injectionIndex, stations):

        # psi_m falls linearly to the throat and then follows figure 17. A slot at or past the
        # throat gets the expansion curve alone: the 3-to-4 injection value is written for a
        # chamber slot and there is no convergent section left for it to decay over.
        if index < throatIndex and injectionIndex < throatIndex:
            fraction = (axialPosition[index] - axialPosition[injectionIndex]) \
                       / (axialPosition[throatIndex] - axialPosition[injectionIndex])
            multiplier[index] = entrainmentMultiplier(areaRatio[index], fraction,
                                                      injectionMultiplier)
        else:
            multiplier[index] = entrainmentMultiplier(areaRatio[index], None, injectionMultiplier)

        if index > injectionIndex:
            accumulated += (slotRadius / radius[index]) * fluxRatio[index] \
                           * multiplier[index] * arcLength[index]

        reach = min(referenceFraction * accumulated / (slotRadius - slotHeight), 1.0)
        flowRatio[index] = coreRatio * (2.0 * reach - reach**2)
        effectiveness[index] = entrainmentEffectiveness(flowRatio[index])
        mixtureRatio[index] = wallMixtureRatio(effectiveness[index], coreMixtureRatio,
                                               coolantMixtureRatio)
        adiabaticWall[index] = entrainmentAdiabaticWallTemperature(
            effectiveness[index], float(total[index]), float(recovery[index]),
            float(specificHeat[index]), coolantSpecificHeat, coolantTotalTemperature)

    useful = np.flatnonzero(effectiveness[injectionIndex:] >= 0.3)
    survivalLength = float(axialPosition[injectionIndex + useful[-1]]
                           - axialPosition[injectionIndex]) if useful.size else 0.0

    return FilmCoolingResult(
        effectiveness        = effectiveness,
        drivingTemperature   = adiabaticWall,
        transferGroup        = None,
        propertyCorrection   = None,
        entrainmentFlowRatio = flowRatio,
        wallMixtureRatio     = mixtureRatio,
        entrainmentMultiplier = multiplier,
        filmMassFlux         = np.zeros(stations),
        injectionIndex       = injectionIndex,
        survivalLength       = survivalLength)
