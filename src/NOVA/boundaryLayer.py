
# -- The Boundary Layer on a Nozzle Wall -- #

'''

Every contour NOVA builds is inviscid. The characteristics solve carries no viscosity, so its
wall is a streamline of a flow without friction, which results in two physical effects not
captured by the inviscid solution. The gas near the wall is slowed, so the wall has to sit
further out than the inviscid solution says to pass the same flow. And the wall is dragged, so
some of the thrust the exit plane reports is spent on the wall instead.

NASA SP-8120 states the reference practice for the first effect: displacement thickness
computed and the wall offset point by point.

What is modeled
---------------

A compressible turbulent boundary layer, integrated along the wall from the first station it is
given, driven by the near-wall state the characteristics solve produces. Two integral equations
are marched: momentum, for the thickness that sets the skin friction and the wall offset, and
energy, for the thickness that sets the heat transfer. The skin friction closure is a
reference-temperature method, which evaluates incompressible relations at a temperature chosen
so that they enclose the compressible answer. The displacement thickness follows from the
compressible shape factor, and the Stanton number from von Karman's Reynolds analogy evaluated
at the energy-thickness Reynolds number. Bartz's thickness interaction factor is available and
off by default: against NASA TN D-2832 the energy-thickness law alone ranks above it.

The march integrates on a refined grid of its own rather than on the contour's stations.
Forward Euler on the reference nozzle's 12 mm spacing thins the momentum thickness through the
throat by 27 percent too much and overstates the drag by 13 percent, because the fractional
thinning rate there reaches 100 per metre. Subdividing each contour interval removes that, and
the subdivision count is an input so the convergence can be re-run.

Two skin-friction closures are carried. One evaluates a power law at Eckert's reference state.
The other is Coles' correlation as Bartz uses it, which is a tabulated relation rather than a
fixed power and which separates from a power law by 21 percent at a Reynolds number of 1e5 and
40 percent at 1e6. Bartz offers two ways of carrying Coles' adiabatic correlation to a cooled
wall and states that the relationship is uncertain for severely cooled layers; both are
available and neither is preferred here.

**Friction is charged as a thrust debit over the diverging section only.** The layer is marched
from the first station given, so the thickness arriving at the throat is the chamber's own
rather than a guess, and the drag taken for the performance debit is integrated from the
minimum radius downstream. Friction on the subsonic chamber wall is a chamber momentum loss
and does not reduce exit plane momentum, so charging it against exit thrust is the wrong
bookkeeping. The whole-wall drag is returned beside it.

What is not modeled
-------------------

**Laminar and transitional running.** The flow is taken as turbulent from the throat. A rocket
throat sits at a Reynolds number where that is nearly always true, and the laminar run is short
enough that its contribution to either thickness or drag is small against the turbulent one.
What it does affect is the starting thickness, which is why that is an input rather than a
constant.

**The effect of wall cooling on transition and on the profile shape.** The reference
temperature carries the first-order effect of a cold wall on the properties. Nothing here
carries the second-order effect on the shape of the profile.

**Any coupling back into the jacket.** `regenThermal` has its own gas-side treatment through
Bartz, with its own boundary-layer correction factor built into that correlation. The two are
not made consistent here and should not be read as one model: this one exists to offset a
contour and debit a thrust, and that one exists to size a cooling channel.

**The displacement effect on the inviscid solution itself.** Offsetting the wall changes the
area the flow sees, which changes the flow, which changes the offset. The outer iteration that
closes that loop lives in the contour solve rather than here.

Sign conventions, because they are the easiest thing to get backwards. Displacement thickness
is positive and the physical wall is offset OUTWARD from the inviscid contour by it, so that
the inviscid flow passing through the reduced area matches the real flow through the real area.
Skin friction is a drag, so the thrust it produces is negative.

Lengths are in meters, not throat radii: this is marched along a real wall against a real
Reynolds number.

Validation status
-----------------

**The incompressible limit reproduces the flat-plate correlations.** This is the strongest
check available. Taking the Mach number to zero and the wall to adiabatic, the reference
temperature becomes the free-stream temperature and the skin friction has to return the
incompressible law it was built from. That is arithmetic and it is in
`tests/testBoundaryLayer.py`.

**The momentum integral is checked against itself.** Momentum thickness growth along the wall
has to equal what the friction and pressure-gradient terms say it does, which is exact and
independent of any closure.

**Against a published friction model the drag runs 29% high.**
NASA RP-1104 charges wall friction over a perfect-bell contour at a Fanning factor of 0.003,
which is the same convention used here, since
`wallShear = cf * 0.5 rho u^2`. The two are therefore directly comparable.

On the worked LOX/LH2 truncated ideal contour, at a wall of 800 K, over the diverging section:

    NOVA effective Fanning factor       0.003854      drag divided by the same integral
    RP-1104 representative factor       0.003000      that RP-1104 multiplies by 0.003
    ratio                               1.29 x

    NOVA drag                           1954 N        1.99 percent of inviscid thrust
    the same integral at cf = 0.003     1521 N        1.55 percent of inviscid thrust

**The second pair is what settles where the difference lives.** Both drags run over the same
wetted area and the same dynamic pressure, so their ratio IS the ratio of friction levels and
nothing else. At RP-1104's own friction factor this contour still returns 1.52 percent, which
is the top of the half to one and a half percent range that general loss budgets quote. So
roughly a third of the apparent discrepancy is the friction level, and the rest is that this
contour belongs at the high end of that range: a 40 to 1 bell of 1.13 square meters wetted area
on a 98 kN engine. RP-1104 states the same thing from the other side, that large high-pressure
nozzles run a little below 0.003 and small low-pressure ones a little above.

Three further things are known about the residual. It is NOT the assumed starting thickness:
changing it by a factor of five hundred moves the drag by four percent, because the momentum
integral forgets its initial condition. A cooled wall genuinely carries more friction than an
adiabatic one, and at 800 K against gas at 3081 K that alone raises the coefficient by about
half again, so a budget quoted for a hotter wall sits lower for that reason. And what is
computed here is friction drag alone, where a performance budget is usually net of the
displacement effect, which gives back some of what friction takes; settling that needs the
outer iteration that is not built yet.

**No coefficient has been tuned to close any of this.** The 1.29 is reported, not removed.

**The march is converged on its own grid, which is why it refines one.** On the reference nozzle
at 32 subdivisions per contour interval the diverging-section drag is within 0.07 percent of the
value at 128 and the throat momentum thickness within 0.8 percent. At one subdivision, which is
the contour's own spacing, the drag is 13 percent high and the throat momentum thickness 27
percent low. Subdividing with a monotone cubic state rather than a linear one moves the drag by
under 0.2 percent at every refinement, so what the refinement removes is integration error and
not state error.

**Coles' correlation is checked against its own published pieces.** Bartz gives it three ways:
a table over the turbulent range and a closed form either side. Solved for the friction
coefficient, the low-Reynolds form returns the table's first row exactly and the logarithmic form
returns its last to 0.4 percent, which are independent statements that have to agree where they
meet. Against the Blasius equation the correlation stays within 5.5 percent between Reynolds
numbers of 400 and 15 000, reproducing Bartz's own statement of 5 percent about his own numbers.

**The gas side is compared against measured heat transfer on two chambers**, in
`docs/reports/calorimeter40k_2026-10-04.md`. The interaction exponent was selected among three
published closures on the station-to-station shape of NASA TN D-2832's correlation constant, where
the energy-thickness law (exponent zero) ranks first, and then tested on Test 024 of the MSFC
40 000 lbf calorimeter chamber: with CEA properties, an equilibrium enthalpy potential, the
hot-wall temperature the test's own reduction used and the transonic near-wall state, the
throat-to-barrel ratio lands 7.5 percent above the measured one, where Bartz's exponent of 0.1
leaves it 32 percent high. The level runs 17 to 23 percent low, and the property set alone moves
it by 18 points, so the level is not validated. The converging slope and the diverging section are
not reproduced. Next to the throat the asymmetry on a NOVA wall comes from the characteristics
edge state rather than from the layer's history.

**Not validated against a measured profile.** No source in this reference set publishes a
boundary-layer survey in a rocket nozzle, so nothing here establishes the velocity profile, the
shape factor, or the transition point. What is established is that the closure reduces
correctly, that the march conserves momentum, and that the answer is the right size.

Author: Sean Bowman

'''

import math

import numpy as np

def referenceTemperature(edgeTemperature: float, wallTemperature: float, mach: float,
                         gamma: float, recoveryFactor: float = 0.89) -> float:

    '''

    Eckert's reference temperature, the one incompressible relations are evaluated at.

    A compressible boundary layer has properties that vary across it, and the reference
    temperature method is the observation that an incompressible relation evaluated at one
    well-chosen intermediate temperature reproduces the compressible answer closely. Eckert's
    choice weights the edge, the wall and the recovery temperature:

        T* = Te + 0.5 (Tw - Te) + 0.22 (Tr - Te)

    The recovery factor is the cube root of the Prandtl number for a turbulent layer, which for
    combustion gases is near 0.89.

    Parameters:
    -----------
    edgeTemperature : float
        Static temperature just outside the layer [K].
    wallTemperature : float
        Wall temperature [K].
    mach : float
        Edge Mach number [-].
    gamma : float
        Ratio of specific heats [-].
    recoveryFactor : float
        Fraction of the dynamic temperature the wall recovers [-].

    Returns:
    --------
    float : the reference temperature [K]

    '''

    recovery = edgeTemperature * (1.0 + recoveryFactor * 0.5 * (gamma - 1.0) * mach**2)
    return edgeTemperature + 0.5 * (wallTemperature - edgeTemperature) + 0.22 * (recovery - edgeTemperature)

def skinFrictionCoefficient(momentumReynolds: float, temperatureRatio: float) -> float:

    '''

    Local skin friction, from an incompressible law evaluated at the reference state.

    The incompressible relation is the standard power law in momentum-thickness Reynolds number,

        cf = 0.026 Re_theta^(-0.25)

    and the compressibility transformation is carried entirely by evaluating the density and
    viscosity in that Reynolds number at the reference temperature rather than at the edge. The
    density ratio enters directly, which is the factor that makes a cold wall carry more friction
    than a hot one at the same edge conditions.

    Parameters:
    -----------
    momentumReynolds : float
        Reynolds number on momentum thickness, evaluated at the reference state [-].
    temperatureRatio : float
        Reference temperature over edge temperature [-].

    Returns:
    --------
    float : skin friction coefficient, referred to edge dynamic pressure [-]

    '''

    momentumReynolds = max(float(momentumReynolds), 1.0)
    incompressible = 0.026 * momentumReynolds ** -0.25
    # Referred back to the edge dynamic pressure: the reference state carries a different density,
    # and the ratio of the two is the inverse of the temperature ratio at constant pressure.
    return float(incompressible / temperatureRatio)

def compressibleShapeFactor(mach: float, gamma: float, temperatureRatio: float,
                            incompressibleShape: float = 1.29) -> float:

    '''

    Displacement thickness over momentum thickness for a compressible turbulent layer.

    The incompressible turbulent shape factor sits near 1.29 for a flat plate at these Reynolds
    numbers. Compressibility thickens the displacement thickness without thickening the momentum
    thickness the same way, and to first order the correction is the one below.

    Parameters:
    -----------
    mach : float
        Edge Mach number [-].
    gamma : float
        Ratio of specific heats [-].
    temperatureRatio : float
        Reference temperature over edge temperature [-].
    incompressibleShape : float
        Shape factor the layer would have at low speed [-].

    Returns:
    --------
    float : the shape factor H = deltaStar / theta [-]

    '''

    return float(incompressibleShape * temperatureRatio
                 + 0.5 * (gamma - 1.0) * mach**2 * (incompressibleShape + 1.0) / 3.0)

def vonKarmanStanton(frictionCoefficient, prandtlNumber: float):

    '''

    Stanton number from a skin-friction coefficient, by von Karman's form of Reynolds analogy.

    JPL Technical Report 32-387 Eq. 46 takes this as the most accurate available relation between
    the two for a flat plate, with the Prandtl number entering as a secondary correction:

        St = (Cf/2) / ( 1 + 5 sqrt(Cf/2) [ (Pr - 1) + ln((5 Pr + 1)/6) ] )

    At a Prandtl number of one the bracket vanishes and the relation returns the bare Reynolds
    analogy, St = Cf/2, which is the limit worth remembering it by.

    **The friction coefficient handed in has to be the one evaluated at the energy-thickness
    Reynolds number**, not the momentum-thickness one. That substitution is the whole mechanism by
    which the thermal and velocity layers are allowed to differ, and JPL is explicit that it is
    a first approximation: the relation is derived for equal thicknesses and then adopted for
    unequal ones, on tube data spanning thickness ratios of 0.3 to 1.0.

    Parameters:
    -----------
    frictionCoefficient : array_like
        Skin-friction coefficient at the energy-thickness Reynolds number [-].
    prandtlNumber : float
        Prandtl number of the gas [-].

    Returns:
    --------
    numpy.ndarray
        Stanton number [-].

    '''

    half = 0.5*np.asarray(frictionCoefficient, dtype = float)
    correction = (prandtlNumber - 1.0) + math.log((5.0*prandtlNumber + 1.0) / 6.0)

    return half / (1.0 + 5.0*np.sqrt(np.maximum(half, 0.0))*correction)

# Bartz NTRS 19650013685 Table A-1, from Coles, Reference 15. Published as the low-speed friction
# coefficient against the product of that coefficient and the low-speed momentum-thickness Reynolds
# number. Dividing the product by the coefficient turns each row into a Reynolds number, which makes
# the table a direct relation and removes the implicit solve the product form would otherwise need.
COLESFRICTIONTABLE = ((2.51, 0.00590), (3.10, 0.00524), (3.97, 0.00464), (4.88, 0.00426),
                      (5.73, 0.00398), (7.41, 0.00363), (8.94, 0.00340), (12.75, 0.00308),
                      (16.36, 0.00290), (23.2, 0.00269), (29.6, 0.00255), (35.9, 0.00246),
                      (41.8, 0.00238), (53.6, 0.00227), (64.8, 0.00219))

FRICTIONCLOSURES = ('referenceTemperature', 'colesAdiabatic', 'colesFilm')

def colesLowSpeedFriction(lowSpeedReynolds: float) -> float:

    '''

    Coles' low-speed skin friction, which is the correlation Bartz's nozzle analysis is built on.

    Coles found that nearly all reliable adiabatic flat-plate friction data, over a wide range of
    Reynolds and Mach number, collapses onto one curve once both axes are transformed to their
    low-speed equivalents. Bartz publishes that curve three ways: Table A-1 over the turbulent
    range, Eq. A-4 above it, and Eq. A-5 below it.

    The relation NOVA's own power law uses is the Blasius form, which Bartz states agrees with
    Coles to within 5 percent between Reynolds numbers of 400 and 15 000. Outside that window it
    does not: Blasius runs 21 percent low at 1e5 and 40 percent low at 1e6, because a fixed
    quarter-power slope cannot follow a logarithmic friction law. A large engine sits in that
    region.

    Parameters:
    -----------
    lowSpeedReynolds : float
        Momentum-thickness Reynolds number transformed to its low-speed equivalent [-].

    Returns:
    --------
    float : the low-speed skin friction coefficient [-]

    '''

    reynolds = max(float(lowSpeedReynolds), 1.0)
    products = np.array([row[0] for row in COLESFRICTIONTABLE], dtype = float)
    frictions = np.array([row[1] for row in COLESFRICTIONTABLE], dtype = float)
    bounds = products / frictions

    if reynolds < bounds[0]:
        # Eq. A-5, Cf = 0.009896 (Cf R)^-0.562, solved for Cf by collecting the two powers.
        return float(0.009896**(1.0/1.562) * reynolds**(-0.562/1.562))

    if reynolds > bounds[-1]:
        # Eq. A-4, a logarithmic law. Written in u = (2/Cf)^(1/2) the coefficient cancels out of
        # the logarithm's argument, leaving a one-dimensional fixed point that converges in a few
        # passes because the logarithm moves so slowly.
        u = 30.0
        for _ in range(100):
            inner = max(3.781 - 25.104 / u, 1e-6)
            updated = 2.44 * math.log(reynolds / inner) + 7.68
            if abs(updated - u) < 1e-12:
                u = updated
                break
            u = updated
        return float(2.0 / u**2)

    # Log-log interpolation across Table A-1, which is how a power-law-like relation should be read
    # between tabulated points.
    return float(np.exp(np.interp(np.log(reynolds), np.log(bounds), np.log(frictions))))

def bartzSkinFriction(edgeReynolds: float, edgeTemperature: float, stagnationTemperature: float,
                      adiabaticWallTemperature: float, wallTemperature: float,
                      viscosityExponent: float = 0.6,
                      wallProperties: str = 'film') -> float:

    '''

    Skin friction after Bartz, from Coles' correlation and a wall-property assumption.

    Three steps. Coles' curve gives the low-speed coefficient at a transformed Reynolds number;
    the transformation needs a sublayer temperature from Eq. A-3, which depends on the coefficient,
    so the two are iterated. Then the coefficient is brought back to the real wall.

    **That last step is where Bartz offers two answers rather than one, and the gap between them is
    the largest open question in the closure.** Assumption 12a (Eq. 31 with Eq. 33) takes the
    coefficient to be the adiabatic one. Assumption 12b (Eq. 36) evaluates properties at the mean
    of the wall and edge temperatures. On a rocket throat with a wall at a sixth of the gas
    temperature the two differ by about half. Bartz carries both because, in his words, the
    relationship for severely cooled turbulent layers is sufficiently uncertain.

    Parameters:
    -----------
    edgeReynolds : float
        Momentum-thickness Reynolds number on edge static properties [-].
    edgeTemperature, stagnationTemperature : float
        Static and stagnation temperature at the layer's edge [K].
    adiabaticWallTemperature, wallTemperature : float
        Recovery temperature and the real wall temperature [K].
    viscosityExponent : float
        Exponent m in a power-law viscosity [-]. Bartz works at 0.6.
    wallProperties : str
        'adiabatic' for Assumption 12a, 'film' for Assumption 12b.

    Returns:
    --------
    float : skin friction coefficient, referred to edge dynamic pressure [-]

    '''

    edge = max(float(edgeTemperature), 1.0)
    recovery = max(float(adiabaticWallTemperature), 1.0)
    stagnationRatio = float(stagnationTemperature) / recovery
    staticRatio = edge / recovery

    # The sublayer temperature of Eq. A-3 depends on the coefficient it is used to find. Starting
    # the sublayer at the recovery temperature makes the first pass the uncorrected transform.
    sublayerRatio = 1.0
    lowSpeed = 0.0
    for _ in range(50):
        lowSpeedReynolds = max(float(edgeReynolds), 1.0) * (edge / (sublayerRatio * recovery)) ** viscosityExponent
        updated = colesLowSpeedFriction(lowSpeedReynolds)
        # Eq. A-3.
        half = 0.5 * updated
        sublayer = (1.0 + 17.2 * (stagnationRatio - 1.0) * math.sqrt(max(half, 0.0))
                    - 305.0 * (stagnationRatio - staticRatio) * half)
        sublayer = min(max(sublayer, 0.1), 10.0)
        if abs(updated - lowSpeed) < 1e-12 and abs(sublayer - sublayerRatio) < 1e-12:
            lowSpeed, sublayerRatio = updated, sublayer
            break
        lowSpeed, sublayerRatio = updated, sublayer

    if wallProperties == 'adiabatic':
        # Eq. 33 with Eq. 31: the real coefficient is taken to be the adiabatic one.
        return float(lowSpeed / ((recovery / edge) * sublayerRatio ** viscosityExponent))

    # Eq. 36: properties at the arithmetic mean of the wall and edge temperatures.
    meanRatio = 0.5 * (float(wallTemperature) / edge + 1.0)
    return float(lowSpeed / max(meanRatio, 1e-6) ** ((3.0 - viscosityExponent) / 4.0))

def thicknessInteractionFactor(thicknessRatio, exponent: float = 0.1):

    '''

    The correction that lets the Stanton closure stand where the two thicknesses are unequal.

    Reynolds analogy in every form was correlated on flows whose energy and momentum thicknesses
    stay near equal along the wall. A nozzle is not one of those. The momentum equation carries a
    pressure-gradient term that thins the momentum thickness hard through a contraction and the
    energy equation carries one of the opposite sign, so the ratio of the two climbs through the
    throat. Bartz reports values as high as 5 there from his own analyses.

    Bartz's accelerating-flow report, NTRS 19650013685, Eq. 42, splits the quarter power of the
    friction law between the two Reynolds
    numbers,

        Ch = const / ( Pr^(2/3) Re_theta^n Re_phi^(1/4 - n) )

    which rearranges to a Stanton number taken at the energy-thickness Reynolds number and then
    multiplied by (phi/theta)^n. An exponent of zero leaves the whole power on the energy
    thickness, a quarter moves it all to the momentum thickness, and 0.1 is what Bartz selects.
    He states that the selection is arbitrary, that it correlates flat-plate and tube-entrance
    data somewhat better than no correction at all, and that the data in hand cannot determine it
    sensitively. His own earlier analyses used 3/28, which is 0.107.

    Parameters:
    -----------
    thicknessRatio : array_like
        Energy thickness over momentum thickness [-].
    exponent : float
        The interaction exponent n [-]. Zero recovers the uncorrected analogy.

    Returns:
    --------
    numpy.ndarray
        The factor the Stanton number is multiplied by [-].

    '''

    return np.maximum(np.asarray(thicknessRatio, dtype = float), 1e-12)**float(exponent)

def solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, gamma: float,
                       gasConstant: float, wallTemperature, viscosityReference: float = 7.5e-5,
                       viscosityTemperature: float = 3000.0, viscosityExponent: float = 0.66,
                       initialMomentumThickness: float = 1.0e-5,
                       initialEnergyThickness: float = 1.0e-5,
                       prandtlNumber: float = None,
                       thicknessInteractionExponent: float = 0.0,
                       frictionClosure: str = 'referenceTemperature',
                       marchSubsteps: int = 32,
                       recoveryFactor: float = 0.89) -> dict:

    '''

    March the momentum integral along a wall and return what the layer does to it.

    The momentum integral for an axisymmetric wall, with the radius term that makes it
    axisymmetric rather than planar:

        d(theta)/dx = cf/2 - theta (2 + H - M^2) (1/ue) due/dx - theta (1/r) dr/dx

    The three terms are the three things that change momentum thickness: friction adds to it, a
    favorable pressure gradient thins it, and a diverging wall stretches it. A rocket nozzle has
    all three working hard and the second is why the layer stays thin despite the length.

    Parameters:
    -----------
    x, radius : array
        The wall, in meters, from the throat outward.
    mach, temperature, pressure, velocity : array
        Near-wall edge state at those stations, from the characteristics solve.
    gamma, gasConstant : float
        Gas properties [-] and [J/kg-K].
    wallTemperature : float | array
        Wall temperature [K]. A scalar is taken as uniform.
    viscosityReference, viscosityTemperature, viscosityExponent : float
        Power-law viscosity: mu = muRef (T / Tref)^n [Pa-s], [K], [-].
    initialMomentumThickness, initialEnergyThickness : float
        The two thicknesses at the first station [m]. The layer does not start from nothing. Over
        a chamber of any length the march forgets both: across the three decades from 0.1 to 100
        micron the throat heat flux moves by about one percent.
    prandtlNumber : float
        Prandtl number of the gas [-]. Unset, it is taken from gamma as 4 g / (9 g - 5).
    thicknessInteractionExponent : float
        Bartz's exponent n on the thickness ratio in the Stanton closure [-]. Zero, the default,
        puts the whole friction-law power on the energy thickness, as Ambrok, Kays and Crawford,
        and Kutateladze and Leont'ev do; it was selected against NASA TN D-2832 over Bartz's 0.1,
        which runs the throat high wherever the thermal layer outgrows the momentum layer.
    frictionClosure : str
        Which skin-friction relation closes both marches. 'referenceTemperature' is the power law
        evaluated at Eckert's reference state; 'colesAdiabatic' and 'colesFilm' are Coles'
        correlation under Bartz's two wall-property assumptions.
    marchSubsteps : int
        Subdivisions of each supplied interval the march integrates on [-]. One marches on the
        stations as given, which is not converged through a throat.
    recoveryFactor : float
        Fraction of the dynamic temperature the wall recovers [-].

    Returns:
    --------
    dict
        The two thicknesses and their ratio, the displacement thickness, the skin friction, the
        Stanton number and gas-side coefficient, the wall shear, and the drag over the whole
        supplied wall, over the diverging section and over everything upstream of it. Every array
        is reported at the stations supplied, whatever the march subdivided them into.

    '''

    x = np.asarray(x, dtype = float)
    radius = np.asarray(radius, dtype = float)
    mach = np.asarray(mach, dtype = float)
    temperature = np.asarray(temperature, dtype = float)
    pressure = np.asarray(pressure, dtype = float)
    velocity = np.asarray(velocity, dtype = float)
    wallTemperature = np.broadcast_to(np.asarray(wallTemperature, dtype = float), x.shape)

    # The march integrates on a refined grid and reports on the one it was handed. Forward Euler
    # at a contour's own spacing is not converged through a throat, where the fractional thinning
    # rate reaches 100 per metre and a 6 mm step takes two thirds of the momentum thickness in
    # one go. Each interval is subdivided linearly, which is enough: a monotone cubic state moves
    # the answer by under 0.2 percent at every refinement, so the error being removed belongs to
    # the integration and not to the state.
    stationCount = x.size
    substeps = max(int(marchSubsteps), 1)
    if substeps > 1 and stationCount > 1:
        coarse = x
        # Built interval by interval, so station i of the input is index i * substeps of the march
        # whatever the input spacing does.
        x = np.concatenate([np.linspace(coarse[index], coarse[index + 1], substeps,
                                        endpoint = False)
                            for index in range(stationCount - 1)] + [coarse[-1:]])
        radius = np.interp(x, coarse, radius)
        mach = np.interp(x, coarse, mach)
        temperature = np.interp(x, coarse, temperature)
        pressure = np.interp(x, coarse, pressure)
        velocity = np.interp(x, coarse, velocity)
        wallTemperature = np.interp(x, coarse, wallTemperature)

    if prandtlNumber is None:
        # The stagnation Prandtl number the gas-side correlation uses, from the same relation
        prandtlNumber = 4.0*gamma / (9.0*gamma - 5.0)
    specificHeat = gamma*gasConstant / (gamma - 1.0)

    # Stagnation and adiabatic wall temperatures, which are the energy equation's potentials
    stagnationTemperature = temperature*(1.0 + 0.5*(gamma - 1.0)*mach**2)
    adiabaticWallTemperature = temperature*(1.0 + recoveryFactor*0.5*(gamma - 1.0)*mach**2)
    edgeDensity = pressure / (gasConstant*temperature)
    massFlux = edgeDensity*velocity
    drivingPotential = stagnationTemperature - wallTemperature

    stations = len(x)
    momentumThickness = np.zeros(stations)
    displacementThickness = np.zeros(stations)
    frictionCoefficient = np.zeros(stations)
    energyThickness = np.zeros(stations)
    thicknessRatio = np.zeros(stations)
    stantonNumber = np.zeros(stations)
    gasSideCoefficient = np.zeros(stations)
    momentumThickness[0] = initialMomentumThickness
    energyThickness[0] = initialEnergyThickness

    for index in range(stations):

        edgeTemperature = temperature[index]
        reference = referenceTemperature(edgeTemperature, wallTemperature[index], mach[index],
                                         gamma, recoveryFactor)
        temperatureRatio = reference / edgeTemperature

        # Properties at the reference state, at the local static pressure.
        referenceDensity = pressure[index] / (gasConstant * reference)
        referenceViscosity = viscosityReference * (reference / viscosityTemperature) ** viscosityExponent

        # Edge-state Reynolds numbers as well as reference-state ones: Coles' correlation is
        # defined on edge static properties and carries the compressibility in its own transform,
        # where the reference-temperature method carries it in the properties instead.
        edgeViscosity = viscosityReference * (edgeTemperature / viscosityTemperature) ** viscosityExponent
        edgeDensityHere = pressure[index] / (gasConstant * edgeTemperature)
        momentumReynolds = (referenceDensity * velocity[index] * max(momentumThickness[index], 1e-12)
                            / referenceViscosity)
        edgeMomentumReynolds = (edgeDensityHere * velocity[index]
                                * max(momentumThickness[index], 1e-12) / edgeViscosity)

        if frictionClosure == 'referenceTemperature':
            frictionCoefficient[index] = skinFrictionCoefficient(momentumReynolds, temperatureRatio)
        else:
            frictionCoefficient[index] = bartzSkinFriction(
                edgeMomentumReynolds, edgeTemperature, stagnationTemperature[index],
                adiabaticWallTemperature[index], wallTemperature[index], viscosityExponent,
                'adiabatic' if frictionClosure == 'colesAdiabatic' else 'film')

        shape = compressibleShapeFactor(mach[index], gamma, temperatureRatio)
        displacementThickness[index] = shape * momentumThickness[index]

        # The friction coefficient the Stanton closure needs is the one at the energy-thickness
        # Reynolds number, not the momentum-thickness one. Where the two thicknesses differ, so
        # do the two coefficients, and that difference is the thermal layer's own history.
        if frictionClosure == 'referenceTemperature':
            energyReynolds = (referenceDensity * velocity[index] * max(energyThickness[index], 1e-12)
                              / referenceViscosity)
            energyFriction = skinFrictionCoefficient(energyReynolds, temperatureRatio)
        else:
            energyReynolds = (edgeDensityHere * velocity[index]
                              * max(energyThickness[index], 1e-12) / edgeViscosity)
            energyFriction = bartzSkinFriction(
                energyReynolds, edgeTemperature, stagnationTemperature[index],
                adiabaticWallTemperature[index], wallTemperature[index], viscosityExponent,
                'adiabatic' if frictionClosure == 'colesAdiabatic' else 'film')
        analogyStanton = float(vonKarmanStanton(energyFriction, prandtlNumber))

        # The analogy was correlated where the two thicknesses are near equal, and a throat drives
        # them apart, so their ratio enters as a power rather than going unacknowledged.
        thicknessRatio[index] = (max(energyThickness[index], 1e-12)
                                 / max(momentumThickness[index], 1e-12))
        stantonNumber[index] = analogyStanton * float(thicknessInteractionFactor(
            thicknessRatio[index], thicknessInteractionExponent))
        gasSideCoefficient[index] = stantonNumber[index] * massFlux[index] * specificHeat

        if index == stations - 1:
            break

        step = x[index + 1] - x[index]
        if step <= 0.0:
            # A repeated station advances neither equation, and both have to be carried across it
            # rather than one of them being left at its allocated zero.
            momentumThickness[index + 1] = momentumThickness[index]
            energyThickness[index + 1] = energyThickness[index]
            continue

        velocityGradient = (velocity[index + 1] - velocity[index]) / step / max(velocity[index], 1e-12)
        radiusGradient = (radius[index + 1] - radius[index]) / step / max(radius[index], 1e-12)

        # Friction and heat act over the wall, which is longer than its axial projection wherever
        # the wall is inclined. Marching axially therefore carries the source terms multiplied by
        # ds/dx, which is JPL 32-387 Eqs. 25 and 30. On a 30 degree converging wall it is 1.15.
        wallSlope = (radius[index + 1] - radius[index]) / step
        inclination = math.sqrt(1.0 + wallSlope**2)

        growth = (0.5 * frictionCoefficient[index] * inclination
                  - momentumThickness[index] * (2.0 + shape - mach[index]**2) * velocityGradient
                  - momentumThickness[index] * radiusGradient)
        momentumThickness[index + 1] = max(momentumThickness[index] + growth * step, 1e-12)

        # Integral energy equation, JPL 32-387 Eq. 28 divided through by r rho U cp (T0 - Tw).
        # The three bracketed terms are what stretches the thermal layer: a diverging wall, a
        # falling mass flux, and a driving potential that changes along the wall.
        potential = max(drivingPotential[index], 1e-6)
        massFluxGradient = (massFlux[index + 1] - massFlux[index]) / step / max(massFlux[index], 1e-12)
        potentialGradient = (drivingPotential[index + 1] - drivingPotential[index]) / step / potential
        energyGrowth = (stantonNumber[index] * inclination
                        * (adiabaticWallTemperature[index] - wallTemperature[index]) / potential
                        - energyThickness[index]
                        * (radiusGradient + massFluxGradient + potentialGradient))
        energyThickness[index + 1] = max(energyThickness[index] + energyGrowth * step, 1e-12)

    # Drag is the wall shear integrated over the wetted area, which for a surface of revolution is
    # 2 pi r ds rather than 2 pi r dx: a steep wall has more area than its axial extent suggests.
    dynamicPressure = 0.5 * (pressure / (gasConstant * temperature)) * velocity**2
    wallShear = frictionCoefficient * dynamicPressure
    arcLength = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(radius)))])
    dragForce = float(np.trapezoid(wallShear * 2.0 * np.pi * radius, arcLength))

    # Split at the minimum radius. Only the diverging section's share is a debit against exit
    # thrust; what the subsonic wall takes is a chamber loss and belongs to the chamber's own
    # bookkeeping. Both are reported so that neither has to be inferred from the other.
    minimum = int(np.argmin(radius))
    shearLoad = wallShear * 2.0 * np.pi * radius
    divergingDragForce = float(np.trapezoid(shearLoad[minimum:], arcLength[minimum:]))
    chamberDragForce = float(np.trapezoid(shearLoad[:minimum + 1], arcLength[:minimum + 1]))

    if substeps > 1 and stationCount > 1:
        # Back to the stations the caller handed in, which is what every array is documented at.
        sample = np.arange(stationCount) * substeps
        momentumThickness = momentumThickness[sample]
        displacementThickness = displacementThickness[sample]
        frictionCoefficient = frictionCoefficient[sample]
        energyThickness = energyThickness[sample]
        thicknessRatio = thicknessRatio[sample]
        stantonNumber = stantonNumber[sample]
        gasSideCoefficient = gasSideCoefficient[sample]
        wallShear = wallShear[sample]

    return {
        'momentumThickness':     momentumThickness,
        'displacementThickness': displacementThickness,
        'frictionCoefficient':   frictionCoefficient,
        'energyThickness':       energyThickness,
        'thicknessRatio':        thicknessRatio,
        'stantonNumber':         stantonNumber,
        'gasSideCoefficient':    gasSideCoefficient,
        'wallShear':             wallShear,
        'dragForce':             dragForce,
        'divergingDragForce':    divergingDragForce,
        'chamberDragForce':      chamberDragForce,
        'exitDisplacement':      float(displacementThickness[-1]),
        'wettedArea':            float(np.trapezoid(2.0 * np.pi * radius, arcLength)),
    }

def frictionPerformanceDebit(dragForce: float, thrustCoefficient: float, throatArea: float,
                             chamberPressure: float) -> tuple:

    '''

    What the wall's drag costs the thrust coefficient.

    The inviscid solve reports a thrust the wall was never charged for. The drag the momentum
    integral returns is that charge, and as a fraction of the ideal thrust it is

        xi_f = D_friction / (C_f A_t p_c),      C_f delivered = C_f (1 - xi_f)

    which is the form NASA SP-8120's reference practice and RPA both use. It is a debit on the
    coefficient rather than a change to the contour: the displacement thickness that would move
    the wall is returned by `solveBoundaryLayer` and applying it is a separate decision.

    Parameters:
    -----------
    dragForce : float
        Friction drag on the wall [N], from `solveBoundaryLayer`.
    thrustCoefficient : float
        Thrust coefficient the inviscid solve delivered [-].
    throatArea : float
        Throat area [m^2].
    chamberPressure : float
        Chamber stagnation pressure [Pa].

    Returns:
    --------
    tuple
        (friction loss coefficient [-], thrust coefficient after the debit [-]). Both are None
        when the ideal thrust is not a positive finite number, which is the case where there is
        nothing to take a fraction of.

    '''

    idealThrust = float(thrustCoefficient) * float(throatArea) * float(chamberPressure)
    if not np.isfinite(idealThrust) or idealThrust <= 0.0:
        return None, None

    lossCoefficient = float(dragForce) / idealThrust

    return lossCoefficient, float(thrustCoefficient) * (1.0 - lossCoefficient)

def offsetWall(x, radius, displacementThickness) -> tuple:

    '''

    Move a wall outward by its displacement thickness, along the local normal.

    The inviscid contour is where the flow behaves as though the wall were, and the physical wall
    has to sit outside it by the thickness the slowed gas displaces. Offsetting along the normal
    rather than radially matters where the wall is steep: near the throat the two differ by the
    cosine of the wall angle, which at thirty degrees is thirteen percent of the offset.

    Parameters:
    -----------
    x, radius : array
        The inviscid wall.
    displacementThickness : array
        Displacement thickness at each station, same units.

    Returns:
    --------
    tuple : (x, radius) of the physical wall

    '''

    x = np.asarray(x, dtype = float)
    radius = np.asarray(radius, dtype = float)
    displacementThickness = np.asarray(displacementThickness, dtype = float)

    angle = np.arctan2(np.gradient(radius), np.gradient(x))
    return (x - displacementThickness * np.sin(angle),
            radius + displacementThickness * np.cos(angle))
