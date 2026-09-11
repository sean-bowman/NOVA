# -- NOVA: Film Cooling -- #

'''

A sheet of coolant injected along the wall, and what it does to the temperature the wall sees.

Film cooling does not remove heat from the wall the way a jacket does. It changes the temperature
the wall is driven by. A tangential sheet of cool gas leaving a slot sits between the exhaust and
the wall, mixes with the core as it goes, and warms until it is indistinguishable from the gas
around it. Over the length where it survives, the adiabatic wall temperature is somewhere between
the coolant and the exhaust, and the whole of the model is a statement of where.

That is expressed as a film cooling effectiveness,

    eta = (T_aw - T_wall,film) / (T_aw - T_coolant)

which is one at the slot and decays to zero far downstream. The driving temperature the thermal
model uses becomes

    T_drive = T_aw - eta (T_aw - T_coolant)

so with no film it is the adiabatic wall temperature and the jacket sees exactly what it saw
before.

The closure is the correlation of Hatch and Papell, NASA TN D-130. It is here rather than the
entrainment model of NASA SP-8124 for one reason: it arrives with a stated accuracy from its own
source, five per cent on wall temperature over an effectiveness range of 0.2 to 1.0, and that is
the only film cooling closure found that does.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**The correlation is implemented as published and validated against its own stated accuracy.**
Hatch and Papell derive it from a heat balance on a discrete coolant layer and then fit two
empirical groups to measurements from the NASA film-cooling facility. tests/testFilmCooling.py
reproduces the equation, its limits and its shape, and checks the velocity-ratio correction is
continuous where its two branches meet.

**NOVA uses it far outside the conditions it was fitted to, and that is the dominant uncertainty
here.** The data cover a flat plate with a main gas stream from 502 to 1965 degR, which is 279 to
1092 K, at 104 to 1040 ft/s, which is 32 to 317 m/s, with slot heights from 1/16 to 1/2 inch, and
air or helium as the coolant. A rocket nozzle runs at three thousand kelvin and several times the
speed of sound, through a throat where the flow accelerates hard. Every one of those is an
extrapolation. SP-8124 says plainly that acceleration and flow turning are very significant for
film cooling and that accounting for them is the key to predicting coolant requirements; this
correlation accounts for neither.

**Below an effectiveness of about 0.3 the correlation is pessimistic**, which its own authors
state: measured effectiveness runs above the equation there. That is the safe direction, and a
design that depends on the difference is a design that has run out of film.

**The two-dimensional effects are absent.** The correlation describes a continuous slot. Real
injection is through a ring of discrete orifices, and SP-8124 recommends spacing no wider than
0.3 inch precisely because a coarser ring leaves the wall between the jets uncooled. Nothing here
knows how many holes there are.

**The blowing correction is off by default, to avoid counting the film twice.** Hatch and Papell
measured the adiabatic wall temperature with a film present, so the film's effect on the wall is
already inside the effectiveness. Applying a transpiration blowing correction to the gas-side
coefficient on top of it would reduce the flux twice for the same physical cause. The jacket
model can take a film mass flux, and that path exists for distributed injection and for an
ablative's pyrolysis gas, which are genuinely different.

All units are mass base SI:
    - Length      [m]
    - Temperature [K]
    - Velocity    [m/s]
    - Mass flow   [kg/s]

Author: Sean Bowman

'''

from dataclasses import dataclass

import numpy as np

from .utils import InvalidInputError

__all__ = [
    'FilmCoolingResult', 'HATCHPAPELLONSET', 'filmCoolingArrays', 'filmDrivingTemperature',
    'filmTransferCoefficient', 'hatchPapellEffectiveness', 'velocityRatioCorrection',
]

# The correlating group below which the wall has not yet warmed above the coolant, so the
# effectiveness is exactly one. Hatch and Papell's equation (12a), where it comes out of fitting
# the distance the gas travels before heat diffuses through the film.
HATCHPAPELLONSET = 0.04

def filmTransferCoefficient(gasThermalConductivity: float, hydraulicDiameter: float,
                            reynoldsNumber: float, prandtlNumber: float) -> float:

    '''

    The heat transfer coefficient the Hatch and Papell correlating group is built on.

    Their assumption 6: the main gas stream is fully developed turbulent flow, and

        h = 0.0265 (k / D_h) Re^0.8 Pr^0.3

    with every property evaluated at the arithmetic mean of the static gas temperature and the
    coolant slot exit static temperature. That mean matters. Evaluating at the gas temperature
    alone overstates the conductivity across a film whose whole purpose is to be cold.

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
    within a few per cent of one.

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

    Accuracy, from the source: within five per cent on film-cooled wall temperature over an
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
    transferGroup : numpy.ndarray
        The dimensionless group the correlation is written in, h A / (m_dot c_p), accumulated
        from the slot [-]. Worth reading: it says how far through its useful range the film is.
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

    effectiveness:      np.ndarray
    drivingTemperature: np.ndarray
    transferGroup:      np.ndarray
    filmMassFlux:       np.ndarray
    injectionIndex:     int
    survivalLength:     float

def filmCoolingArrays(axialPosition, radius, gasVelocity, recoveryTemperature,
                      meanThermalConductivity, meanDensity, meanViscosity, meanPrandtlNumber,
                      injectionPosition: float, slotHeight: float,
                      coolantMassFlow: float, coolantSpecificHeat: float,
                      coolantTemperature: float, coolantThermalDiffusivity: float,
                      coolantVelocity: float) -> FilmCoolingResult:

    """

    Solve a film along a nozzle contour and return what the thermal model needs from it.

    The correlation is written for a flat plate with one heat transfer coefficient over a cooled
    area L x. A nozzle is neither flat nor of constant coefficient, so the group is accumulated
    instead:

        X(s) = integral of h dA / (m_dot c_p), from the slot to s

    with dA the wall area of each station, 2 pi r ds. On a flat plate of constant h this reduces
    to the published h L x / (m_dot c_p) exactly, which is the sense in which it is the same
    correlation. On a nozzle it is a generalisation, and one the source does not authorise.

    The film marches forward from the slot with the gas. Upstream of it there is no film, and
    those stations come back with the recovery temperature untouched.

    **The properties must be evaluated at the mean of the gas static and coolant temperatures**,
    which is assumption 6 of the source. NOVA's station arrays carry properties at the gas
    temperature instead. Using those overstates the conductivity, overstates the transfer group
    and so understates the effectiveness, which is the safe direction; the size of it has not
    been quantified.

    Parameters:
    -----------
    axialPosition, radius : array_like
        Wall coordinates, ascending in axial position [m].
    gasVelocity : array_like
        Core stream velocity at each station [m/s].
    recoveryTemperature : array_like
        Adiabatic wall temperature with no film [K].
    meanThermalConductivity, meanDensity, meanViscosity : array_like
        Gas properties at the film mean temperature [W/m-K], [kg/m^3], [Pa s].
    meanPrandtlNumber : array_like
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
    recoveryTemperature = np.asarray(recoveryTemperature, dtype = float)
    conductivity = np.asarray(meanThermalConductivity, dtype = float)
    density = np.asarray(meanDensity, dtype = float)
    viscosity = np.asarray(meanViscosity, dtype = float)
    prandtl = np.asarray(meanPrandtlNumber, dtype = float)

    lengths = {array.size for array in (axialPosition, radius, gasVelocity, recoveryTemperature,
                                        conductivity, density, viscosity, prandtl)}
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
            coefficient = filmTransferCoefficient(
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
        filmMassFlux       = np.zeros(stations),
        injectionIndex     = injectionIndex,
        survivalLength     = survivalLength)
