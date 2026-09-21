
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

A compressible turbulent boundary layer, integrated along the wall from the throat, driven by
the near-wall state the characteristics solve produces. The momentum integral is marched in
momentum thickness; the skin friction closure is a reference-temperature method, which
evaluates incompressible relations at a temperature chosen so that they enclose the
compressible answer; the displacement thickness follows from the compressible shape factor.

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

**Against a published friction model the drag runs 33% high.**
NASA RP-1104 charges wall friction over a perfect-bell contour at a Fanning factor of 0.003,
which is the same convention used here, since
`wallShear = cf * 0.5 rho u^2`. The two are therefore directly comparable.

On the worked LOX/LH2 truncated ideal contour, at a wall of 800 K:

    NOVA effective Fanning factor       0.003994      drag divided by the same integral
    RP-1104 representative factor       0.003000      that RP-1104 multiplies by 0.003
    ratio                               1.33 x

    NOVA drag                           1998 N        2.03 percent of inviscid thrust
    the same integral at cf = 0.003     1501 N        1.52 percent of inviscid thrust

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

**No coefficient has been tuned to close any of this.** The 1.33 is reported, not removed.

**Not validated against a measured profile.** No source in this reference set publishes a
boundary-layer survey in a rocket nozzle, so nothing here establishes the velocity profile, the
shape factor, or the transition point. What is established is that the closure reduces
correctly, that the march conserves momentum, and that the answer is the right size.

Author: Sean Bowman

'''

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

def solveBoundaryLayer(x, radius, mach, temperature, pressure, velocity, gamma: float,
                       gasConstant: float, wallTemperature, viscosityReference: float = 7.5e-5,
                       viscosityTemperature: float = 3000.0, viscosityExponent: float = 0.66,
                       initialMomentumThickness: float = 1.0e-5,
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
    initialMomentumThickness : float
        Momentum thickness at the throat [m]. The layer does not start from nothing, and what it
        starts from is the converging section this model does not cover.
    recoveryFactor : float
        Fraction of the dynamic temperature the wall recovers [-].

    Returns:
    --------
    dict
        Momentum and displacement thickness along the wall, the skin friction, the drag, and the
        thrust the drag costs as a fraction of the momentum leaving the exit.

    '''

    x = np.asarray(x, dtype = float)
    radius = np.asarray(radius, dtype = float)
    mach = np.asarray(mach, dtype = float)
    temperature = np.asarray(temperature, dtype = float)
    pressure = np.asarray(pressure, dtype = float)
    velocity = np.asarray(velocity, dtype = float)
    wallTemperature = np.broadcast_to(np.asarray(wallTemperature, dtype = float), x.shape)

    stations = len(x)
    momentumThickness = np.zeros(stations)
    displacementThickness = np.zeros(stations)
    frictionCoefficient = np.zeros(stations)
    momentumThickness[0] = initialMomentumThickness

    for index in range(stations):

        edgeTemperature = temperature[index]
        reference = referenceTemperature(edgeTemperature, wallTemperature[index], mach[index],
                                         gamma, recoveryFactor)
        temperatureRatio = reference / edgeTemperature

        # Properties at the reference state, at the local static pressure.
        referenceDensity = pressure[index] / (gasConstant * reference)
        referenceViscosity = viscosityReference * (reference / viscosityTemperature) ** viscosityExponent

        momentumReynolds = (referenceDensity * velocity[index] * max(momentumThickness[index], 1e-12)
                            / referenceViscosity)
        frictionCoefficient[index] = skinFrictionCoefficient(momentumReynolds, temperatureRatio)
        shape = compressibleShapeFactor(mach[index], gamma, temperatureRatio)
        displacementThickness[index] = shape * momentumThickness[index]

        if index == stations - 1:
            break

        step = x[index + 1] - x[index]
        if step <= 0.0:
            momentumThickness[index + 1] = momentumThickness[index]
            continue

        velocityGradient = (velocity[index + 1] - velocity[index]) / step / max(velocity[index], 1e-12)
        radiusGradient = (radius[index + 1] - radius[index]) / step / max(radius[index], 1e-12)

        growth = (0.5 * frictionCoefficient[index]
                  - momentumThickness[index] * (2.0 + shape - mach[index]**2) * velocityGradient
                  - momentumThickness[index] * radiusGradient)
        momentumThickness[index + 1] = max(momentumThickness[index] + growth * step, 1e-12)

    # Drag is the wall shear integrated over the wetted area, which for a surface of revolution is
    # 2 pi r ds rather than 2 pi r dx: a steep wall has more area than its axial extent suggests.
    dynamicPressure = 0.5 * (pressure / (gasConstant * temperature)) * velocity**2
    wallShear = frictionCoefficient * dynamicPressure
    arcLength = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(radius)))])
    dragForce = float(np.trapezoid(wallShear * 2.0 * np.pi * radius, arcLength))

    return {
        'momentumThickness':     momentumThickness,
        'displacementThickness': displacementThickness,
        'frictionCoefficient':   frictionCoefficient,
        'wallShear':             wallShear,
        'dragForce':             dragForce,
        'exitDisplacement':      float(displacementThickness[-1]),
        'wettedArea':            float(np.trapezoid(2.0 * np.pi * radius, arcLength)),
    }

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
