# -- The 40k calorimeter study -- #

'''

Every number and figure in `docs/reports/calorimeter40k_2026-10-04.md`, regenerated.

The case itself, its data, its edge state and its scorecard live in `tests/calorimeter40kCase.py`.
This script runs the comparisons the report quotes, in the order the report takes them, and prints
each as a table of scorecards. Each step is a function so one can be rerun alone.

    phase0    where the models stand: the march and Bartz on RPA's wall, RPA's own prediction, and
              the march on NOVA's own wall under its own near-wall state and under a 1-D one
    phase1a   the contour: wall length to each area ratio on NOVA's wall and RPA's, the measured
              stations' area ratios, and a sweep over RPA's converging-section parameters
    phase1b   the gas properties and the driving potential, the acceleration parameter, and the
              fuel's inlet temperature
    phase1c   the wall temperature: the reduction's own against uniform walls
    phase1d   whether injector or faceplate coolant reaches the barrel
    phase2    the near-wall state through the throat, and the span of the transonic state's taper
    phase3    Ievlev's method against RPA's own output and against the measurement
    phase4    the closure, selected on NASA TN D-2832 and scored on the 40k chamber
    figures   the report's four figures

Every model runs at Test 024's operating point on the hot-wall temperature the test's own data
reduction used, `case.reductionWallTemperature`, unless a step says otherwise. Phases 0 to 2 run
the marched layer under Bartz's thickness interaction exponent of 0.1, which is what the comparison
started from; Phase 4 chooses the exponent.

The NOVA builds take most of a minute each and are cached under `runs/calorimeter40k/`; delete
that folder to rebuild them.

Usage, from the NOVA root:

    python featureShowcase/buildCalorimeter40k.py [phase ...]

With no phase named, every phase runs.

Author: Sean Bowman

'''

import os
import pickle
import sys

import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'tests'))
os.environ.setdefault('NOVA_HEADLESS', '1')

import calorimeter40kCase as case

cacheFolder = os.path.join(root, 'runs', 'calorimeter40k')

# Bartz's thickness interaction exponent, which every phase before the closure is chosen runs on, so
# that the input corrections are measured against the closure the comparison started from
bartzInteraction = 0.1

def baselineMarch(*arguments, **options):

    '''

    The marched layer under Bartz's interaction exponent unless another is named.

    '''

    options.setdefault('thicknessInteractionExponent', bartzInteraction)

    return case.marchedHeatFlux(*arguments, **options)

# The wall RPA's figure was first read from, at 11 points by eye: injector-face location and
# radius [mm]. Kept to show what the dense reading changes.
coarseRpaContour = np.array([(0, 70), (270, 70), (300, 62), (330, 50), (355, 43), (400, 55), (450, 66),
                             (500, 80), (550, 95), (600, 104), (650, 110)], dtype = float)

#----------------------------------------------------------------------#
# -- Shared pieces -- #
#----------------------------------------------------------------------#

# Named NOVA builds: the operating point and the configuration keys each one sets
novaBuilds = {
    'measured':                   ('measured', {}),
    # 400 contour points, so the throat region carries stations 1.6 mm apart rather than 6 mm
    'measuredFine':               ('measured', {'numContourPoints': 400}),
    'measuredFineTransonic':      ('measured', {'numContourPoints': 400, 'nearWallStateModel': 'transonic'}),
    'measuredFineSecondOrder':    ('measured', {'numContourPoints': 400, 'nearWallStateModel': 'transonic',
                                                'transonicModel': 'secondOrder'}),
}

def novaCase(name: str = 'measured'):

    '''

    One of `novaBuilds` as a NOVA nozzle, from the cache when it is there.

    '''

    path = os.path.join(cacheFolder, f'nozzle_{name}.pkl')
    if os.path.exists(path):
        with open(path, 'rb') as handle:
            return pickle.load(handle)

    pointName, overrides = novaBuilds[name]
    nozzle = case.buildNovaCase(pointName, os.path.join(cacheFolder, name),
                                {**overrides, 'filename': f'calorimeter40k_{name}'})
    with open(path, 'wb') as handle:
        pickle.dump(nozzle, handle)

    return nozzle

def novaWall(nozzle) -> tuple:

    '''

    A NOVA nozzle's wall and near-wall state, on the injector-face axis.

    Returns:
    --------
    tuple : (location [m], radius [m], (Mach, temperature, pressure, velocity))

    '''

    x = np.asarray(nozzle.xNozzleWall, dtype = float)
    radius = np.asarray(nozzle.rNozzleWall, dtype = float)
    location = x - x[np.argmin(radius)] + case.throatLocation
    state = tuple(np.asarray(array, dtype = float) for array in
                  (nozzle.nozzleNearWallMachNumber, nozzle.nozzleNearWallTemperature,
                   nozzle.nozzleNearWallPressure, nozzle.nozzleNearWallVelocity))

    return location, radius, state

def consistentProperties(gas: dict) -> dict:

    '''

    The property set Phase 1b adopts: CEA's viscosity, CEA's equilibrium Prandtl number at the
    throat, and the equilibrium enthalpy potential that goes with them.

    Returns:
    --------
    dict : keyword arguments for `case.marchedHeatFlux`

    '''

    return {**case.viscosityFit(gas), 'prandtlNumber': gas['prandtl']['throat'],
            'drivingPotential': 'equilibrium'}

def testWall(location, gas: dict, prandtlModel: str = 'frozen') -> np.ndarray:

    '''

    The hot-wall temperature Test 024's reduction used, at a set of stations [K].

    '''

    return case.reductionWallTemperature(location, gas, prandtlModel)

def show(label: str, location, heatFlux, wallLocation, wallRadius) -> dict:

    '''

    Score a profile, print it and return the scorecard.

    '''

    card = case.scorecard(location, heatFlux, wallLocation, wallRadius)
    print(case.formatScorecard(card, label))

    return card

def heading(text: str) -> None:

    print('\n' + '=' * 100 + '\n' + text + '\n' + '=' * 100)

#----------------------------------------------------------------------#
# -- Phases -- #
#----------------------------------------------------------------------#

def phase0() -> dict:

    '''

    Where the models stand before anything changes.

    '''

    heading("PHASE 0: the models as they stand, Test 024, on the reduction's wall temperature")
    gas = case.gasState('measured')
    x, r = case.rpaContour()
    wall = testWall(x, gas)
    measuredX, _ = case.measuredProfile()
    print('  reduction wall temperature [K], frozen and equilibrium Prandtl number in the recovery factor:')
    for station in (0.10, 0.20, 0.25, 0.30, 0.33, 0.345, 0.3556, 0.37, 0.39, 0.42, 0.46):
        print(f'    {1e3*station:6.1f} mm   {float(testWall(station, gas)):5.0f}   '
              f'{float(testWall(station, gas, "equilibrium")):5.0f}')

    cards = {}
    heatFlux, _ = baselineMarch(x, r, gas, wall)
    cards['march'] = show('march, defaults, RPA wall, 1-D edge', x, heatFlux, x, r)
    for uniform in case.uniformWallTemperatures:
        heatFlux, _ = baselineMarch(x, r, gas, uniform)
        cards[f'march{uniform:.0f}'] = show(f'march, defaults, RPA wall, 1-D edge, uniform {uniform:.0f} K', x, heatFlux, x, r)
    for model in ('uniform', 'measured'):
        heatFlux = case.bartzHeatFlux(x, r, gas, wall, model)
        cards[f'bartz_{model}'] = show(f'Bartz {model}, RPA wall, 1-D edge', x, heatFlux, x, r)

    rpaX, rpaQ = case.rpaHeatFlux()
    cards['rpa'] = show("RPA's own prediction", rpaX, rpaQ, x, r)

    # NOVA's wall under its own near-wall state, which is the characteristics solve downstream of
    # the throat, against the same wall under a one-dimensional state
    location, radius, state = novaWall(novaCase('measured'))
    novaWallTemperature = testWall(location, gas)
    heatFlux, _ = baselineMarch(location, radius, gas, novaWallTemperature, edgeState = state)
    cards['novaWallNovaState'] = show("march, defaults, NOVA's wall, NOVA's near-wall state",
                                      location, heatFlux, location, radius)
    heatFlux, _ = baselineMarch(location, radius, gas, novaWallTemperature)
    cards['novaWall1D'] = show("march, defaults, NOVA's wall, 1-D edge", location, heatFlux, location, radius)

    mach1D = case.oneDimensionalEdgeState(location, radius, gas)[0]
    throat = int(np.argmin(radius))
    print(f"\n  NOVA's throat radius {1e3*radius.min():.2f} mm. Wall Mach number, near-wall state against 1-D:")
    for index in range(throat - 4, throat + 10, 2):
        print(f'    {1e3*location[index]:6.1f} mm   {state[0][index]:.3f}   {mach1D[index]:.3f}')

    return cards

def phase1a() -> dict:

    '''

    The contour.

    '''

    heading('PHASE 1a: the contour')
    gas = case.gasState('measured')
    rpaX, rpaR = case.rpaContour()
    location, radius, _ = novaWall(novaCase('measured'))

    def wallToRatio(x, r, targets):
        throat = int(np.argmin(r))
        x, r = x[throat:], r[throat:]
        arc = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(r)))])
        ratio = (r / r[0])**2
        return [float(np.interp(target, ratio, arc)) if target <= ratio.max() else np.nan for target in targets]

    targets = (1.1, 1.2, 1.5, 2.0, 2.5, 2.9)
    nova = wallToRatio(1e3 * location, 1e3 * radius, targets)
    dense = wallToRatio(1e3 * rpaX, 1e3 * rpaR, targets)
    coarse = wallToRatio(coarseRpaContour[:, 0], coarseRpaContour[:, 1], targets)
    print('\n  Wall length from the throat to each area ratio [mm]')
    print(f'  {"ratio":>6} {"NOVA":>8} {"RPA dense":>10} {"RPA coarse":>11} {"NOVA/dense":>11} {"NOVA/coarse":>12}')
    for target, a, b, c in zip(targets, nova, dense, coarse):
        print(f'  {target:6.2f} {a:8.1f} {b:10.1f} {c:11.1f} {a/b:11.2f} {a/c:12.2f}')

    measuredX, _ = case.measuredProfile()
    print('\n  Measured stations past the throat, area ratio through each wall')
    for station in measuredX[measuredX > case.throatLocation][::2]:
        denseRatio = (np.interp(station, rpaX, rpaR) / rpaR.min())**2
        coarseRatio = (np.interp(1e3 * station, coarseRpaContour[:, 0], coarseRpaContour[:, 1]) / 43.0)**2
        print(f'    {1e3*station:6.1f} mm   dense {denseRatio:5.2f}   coarse {coarseRatio:5.2f}')

    print("\n  Converging-section sweep, march with default properties, 1-D edge, reduction wall")
    cards = {}
    variants = [('fitted: CR 2.92, R1 1.15, b 30, R2 1.48', {})]
    variants += [(f'CR {value}', {'contraction': value}) for value in (2.80, 3.04)]
    variants += [(f'R1 {value}', {'inletCurvature': value}) for value in (0.8, 1.5, 2.0)]
    variants += [(f'b {value}', {'convergingAngle': value}) for value in (25.0, 35.0)]
    variants += [(f'R2 {value}', {'filletRadius': value}) for value in (1.0, 2.0)]
    for label, parameters in variants:
        wallX, wallR = case.parametricWall(**parameters)
        heatFlux, _ = baselineMarch(wallX, wallR, gas, testWall(wallX, gas))
        cards[label] = show('  ' + label, wallX, heatFlux, wallX, wallR)

    # NOVA's truncated ideal diverging section behind the fitted converging one
    wallX, wallR = case.parametricWall()
    upstream = wallX <= case.throatLocation
    downstream = location > case.throatLocation
    stitchedX = np.concatenate([wallX[upstream], location[downstream]])
    stitchedR = np.concatenate([wallR[upstream], radius[downstream] * case.throatRadius / radius.min()])
    heatFlux, _ = baselineMarch(stitchedX, stitchedR, gas, testWall(stitchedX, gas))
    cards['novaDiverging'] = show("  NOVA's truncated ideal diverging section", stitchedX, heatFlux, stitchedX, stitchedR)

    return cards

def phase1b() -> dict:

    '''

    Gas properties and the driving potential.

    '''

    heading("PHASE 1b: gas properties and the driving potential, RPA wall, 1-D edge, reduction wall")
    gas = case.gasState('measured')
    x, r = case.rpaContour()
    wall = testWall(x, gas)
    fit = case.viscosityFit(gas)
    specificHeat = gas['gamma'] * gas['gasConstant'] / (gas['gamma'] - 1.0)
    throatViscosity = fit['viscosityReference'] * (gas['temperature']['throat'] / fit['viscosityTemperature'])**fit['viscosityExponent']
    defaultViscosity = 7.5e-5 * (gas['stagnationTemperature'] / 3000.0)**0.66
    print(f'  CEA viscosity {gas["viscosity"]["chamber"]:.4e} Pa-s at the chamber; default power law {defaultViscosity:.4e}')
    print(f'  fit exponent {fit["viscosityExponent"]:.3f}; throat check {throatViscosity:.4e} against CEA {gas["viscosity"]["throat"]:.4e}')
    print(f'  Prandtl: default {4*gas["gamma"]/(9*gas["gamma"]-5):.3f}, CEA equilibrium {gas["prandtl"]["throat"]:.3f}, '
          f'frozen {gas["prandtlFrozen"]["throat"]:.3f} at the throat')

    # The acceleration parameter K = nu / u^2 du/dx at the edge, against the onset of laminarization
    _, edgeTemperature, edgePressure, edgeVelocity = case.oneDimensionalEdgeState(x, r, gas)
    edgeViscosity = fit['viscosityReference'] * (edgeTemperature / fit['viscosityTemperature'])**fit['viscosityExponent']
    edgeDensity = edgePressure / (gas['gasConstant'] * edgeTemperature)
    acceleration = edgeViscosity / (edgeDensity * edgeVelocity**2) * np.gradient(edgeVelocity, x)
    converging = x < case.throatLocation
    print(f'  acceleration parameter peaks at {acceleration[converging].max():.2e} at '
          f'{1e3*x[converging][np.argmax(acceleration[converging])]:.0f} mm')
    for uniform in (550.0, 800.0):
        equilibrium = gas['chamberEnthalpy'] - case.wallEnthalpy('measured', uniform)
        frozen = gas['chamberEnthalpy'] - case.wallEnthalpy('measured', uniform, True)
        march = specificHeat * (gas['stagnationTemperature'] - uniform)
        print(f'  potential at {uniform:.0f} K: cp (T0 - Tw) {march/1e6:.2f} MJ/kg with cp {specificHeat:.0f}; '
              f'equilibrium {equilibrium/1e6:.2f} ({equilibrium/march:.3f}); frozen {frozen/1e6:.2f} ({frozen/march:.3f})')

    # Bartz's own property group against the same group on CEA's values
    stagnationViscosity = 1.184e-7 * gas['molecularWeight']**0.5 * gas['stagnationTemperature']**0.6
    bartzPrandtl = 4.0 * gas['gamma'] / (9.0 * gas['gamma'] - 5.0)
    effectiveSpecificHeat = (gas['chamberEnthalpy'] - case.wallEnthalpy('measured', 800.0)) / (gas['stagnationTemperature'] - 800.0)
    for label, prandtl in (('frozen', gas['prandtlFrozen']['chamber']), ('equilibrium', gas['prandtl']['chamber'])):
        ratio = (gas['viscosity']['chamber']**0.2 * effectiveSpecificHeat / prandtl**0.6) \
                / (stagnationViscosity**0.2 * specificHeat / bartzPrandtl**0.6)
        print(f'  Bartz group on CEA viscosity, equilibrium enthalpy at 800 K and {label} Pr, over Bartz\'s own: {ratio:.3f}')
    print(f'  Bartz shortcuts against CEA: viscosity {100*(stagnationViscosity/gas["viscosity"]["chamber"]-1):+.0f} %, '
          f'specific heat {100*(specificHeat/effectiveSpecificHeat-1):+.0f} %, '
          f'Prandtl {100*(bartzPrandtl/gas["prandtlFrozen"]["chamber"]-1):+.0f} % against frozen')

    rows = [
        ('defaults, cp (Taw - Tw)', {}),
        ('defaults, equilibrium enthalpy', {'drivingPotential': 'equilibrium'}),
        ('defaults, frozen enthalpy', {'drivingPotential': 'frozen'}),
        ('CEA viscosity', {**fit}),
        ('CEA viscosity, frozen Pr', {**fit, 'prandtlNumber': gas['prandtlFrozen']['throat']}),
        ('CEA viscosity, equilibrium Pr', {**fit, 'prandtlNumber': gas['prandtl']['throat']}),
        ('ADOPTED: CEA viscosity, equilibrium Pr, equilibrium enthalpy', consistentProperties(gas)),
        ('bound: CEA viscosity, frozen Pr, frozen enthalpy',
         {**fit, 'prandtlNumber': gas['prandtlFrozen']['throat'], 'drivingPotential': 'frozen'}),
    ]
    cards = {}
    for label, options in rows:
        heatFlux, _ = baselineMarch(x, r, gas, wall, **options)
        cards[label] = show('  ' + label, x, heatFlux, x, r)

    # The fuel reached the injector warm, through a preburner, at a temperature the chapter does not
    # give; hydrogen fed as gas at 298 K is a sensitivity on the chamber state, not a bound on it
    warm = case.gasState('warmFuel')
    print(f'  hydrogen as gas at 298 K: chamber temperature {warm["stagnationTemperature"]:.0f} K against '
          f'{gas["stagnationTemperature"]:.0f} K, c* {warm["characteristicVelocity"]:.0f} against {gas["characteristicVelocity"]:.0f} m/s')
    heatFlux, _ = baselineMarch(x, r, warm, wall, **consistentProperties(warm))
    cards['warm fuel'] = show('  ADOPTED, hydrogen as gas at 298 K', x, heatFlux, x, r)

    return cards

def phase1c() -> dict:

    '''

    The wall temperature.

    '''

    heading('PHASE 1c: the wall temperature, adopted properties, RPA wall, 1-D edge')
    gas = case.gasState('measured')
    x, r = case.rpaContour()
    options = consistentProperties(gas)
    cards = {}
    for label, wall in (("reduction's wall, frozen Pr recovery", testWall(x, gas)),
                        ("reduction's wall, equilibrium Pr recovery", testWall(x, gas, 'equilibrium')),
                        ('uniform 550 K', 550.0), ('uniform 700 K', 700.0), ('uniform 850 K', 850.0)):
        heatFlux, _ = baselineMarch(x, r, gas, wall, **options)
        cards[label] = show('  ' + label, x, heatFlux, x, r)

    return cards

def phase1d() -> dict:

    '''

    Whether coolant from the faceplate is still at the wall over the barrel.

    A coolant layer still present downstream makes the flux climb along the wall as its effect
    decays. A layer with none under it carries a falling flux, because it thickens.

    '''

    heading('PHASE 1d: the faceplate coolant')
    gas = case.gasState('measured')
    x, r = case.rpaContour()
    heatFlux, _ = baselineMarch(x, r, gas, testWall(x, gas), **consistentProperties(gas))
    measuredX, measuredQ = case.measuredProfile()
    _, measuredH = case.measuredCoefficient()
    window = (measuredX >= 0.120) & (measuredX <= 0.255)
    def change(values):
        slope, intercept = np.polyfit(measuredX[window], values[window], 1)
        return (slope * 0.255 + intercept) / (slope * 0.120 + intercept) - 1.0
    modelChange = np.interp(0.255, x, heatFlux) / np.interp(0.120, x, heatFlux) - 1.0
    print(f'  change from 120 to 255 mm, linear fits over {window.sum()} stations: measured flux {100*change(measuredQ):+.1f} %, '
          f'measured coefficient {100*change(measuredH):+.1f} %; film-free march flux {100*modelChange:+.1f} %')

    return {'measuredChange': change(measuredQ), 'modelChange': modelChange}

def phase2() -> dict:

    '''

    The near-wall state through the throat: NOVA's wall at 400 contour points under each
    near-wall state model, with the adopted properties.

    '''

    heading("PHASE 2: the near-wall state through the throat, NOVA's wall at 400 points, adopted properties")
    gas = case.gasState('measured')
    options = consistentProperties(gas)
    cards = {}
    for name, label in (('measuredFine', 'one-dimensional upstream, characteristics downstream'),
                        ('measuredFineTransonic', 'transonic on the entrant arc, Sauer'),
                        ('measuredFineSecondOrder', 'transonic on the entrant arc, second order')):
        location, radius, state = novaWall(novaCase(name))
        for exponent in (bartzInteraction, 0.0):
            heatFlux, _ = case.marchedHeatFlux(location, radius, gas, testWall(location, gas), edgeState = state,
                                               thicknessInteractionExponent = exponent, **options)
            cards[(name, exponent)] = show(f'  {label}, n = {exponent}', location, heatFlux, location, radius)
        throat = int(np.argmin(radius))
        mach = state[0]
        print('    wall Mach, -9 mm to +5 mm: ' + '  '.join(
            f'{1e3*(location[i]-location[throat]):+.1f}: {mach[i]:.3f}' for i in range(throat - 6, throat + 4)))
        massFlux = state[2] / (gas['gasConstant'] * state[1]) * state[3]
        window = (location > case.throatLocation - 0.03) & (location < case.throatLocation + 0.01)
        print(f'    wall mass flux peaks {1e3*(location[window][np.argmax(massFlux[window])] - case.throatLocation):+.1f} mm from the throat')

    cards.update(taperSensitivity(gas, options))

    return cards

def taperSensitivity(gas: dict, options: dict) -> dict:

    '''

    The transonic state's taper back to one-dimensional is a closure. Rebuild the Sauer state on
    NOVA's one-dimensional build over the whole entrant arc and over half of it, and march both
    under n = 0. The whole-arc rebuild has to reproduce the transonic build's Mach number.

    '''

    from NOVA.contourKernel import transonicConvergingWallMach

    oneDimensional, transonic = novaCase('measuredFine'), novaCase('measuredFineTransonic')
    location, radius, (mach, temperature, pressure, velocity) = novaWall(oneDimensional)
    builtMach = novaWall(transonic)[2][0]
    throatRadius = radius.min()
    axial = np.asarray(oneDimensional.xNozzleWall, dtype = float) / throatRadius    # NOVA's own throat plane
    gamma, curvature = oneDimensional.chamberGamma, oneDimensional.throatInletCurvatureNonDimensional
    arcStart = -curvature * np.sin(np.radians(oneDimensional.convergingSectionAngle))
    upstream = axial < 0.0

    # Isentropic relations from the one-dimensional inlet state carry a new Mach number to the rest
    # of the near-wall state
    factor = 1.0 + 0.5 * (gamma - 1.0) * mach[0]**2
    stagnationTemperature, stagnationPressure = temperature[0] * factor, pressure[0] * factor**(gamma / (gamma - 1.0))
    gasConstant = velocity[0]**2 / (gamma * temperature[0] * mach[0]**2)

    cards = {}
    for label, start in (('whole arc', arcStart), ('half the arc', 0.5 * arcStart)):
        blended = transonicConvergingWallMach(axial, radius / throatRadius, mach, gamma, curvature, start, 'sauer')
        if label == 'whole arc':
            print(f'  taper rebuilt on the 1-D build reproduces the transonic build to {np.max(np.abs(blended - builtMach)):.1e} in Mach')
        staticTemperature = np.where(upstream, stagnationTemperature / (1.0 + 0.5 * (gamma - 1.0) * blended**2), temperature)
        staticPressure = np.where(upstream, stagnationPressure * (staticTemperature / stagnationTemperature)**(gamma / (gamma - 1.0)), pressure)
        speed = np.where(upstream, blended * np.sqrt(gamma * gasConstant * staticTemperature), velocity)
        heatFlux, _ = case.marchedHeatFlux(location, radius, gas, testWall(location, gas),
                                           edgeState = (blended, staticTemperature, staticPressure, speed),
                                           thicknessInteractionExponent = 0.0, **options)
        cards[('taper', label)] = show(f'  Sauer tapered over {label}, n = 0.0', location, heatFlux, location, radius)

    return cards

def ievlevOnRpaPoint(prandtlModel: str = 'frozen', wall = 550.0) -> tuple:

    '''

    Ievlev's method on RPA's wall as drawn, at Test 024's operating point: RPA's own case.

    Returns:
    --------
    tuple : (location [m], heat flux [W/m^2])

    '''

    from NOVA.ievlevHeatTransfer import ievlevGasProperties, ievlevHeatFlux

    point = case.operatingPoint('rpa')
    properties = ievlevGasProperties(case._ceaSolve(point), point['chamberPressure'], point['mixtureRatio'],
                                     prandtlModel = prandtlModel)
    x, r = case.rpaContour(scaledThroatRadius = None)
    gas = case.gasState('rpa')
    _, _, pressure, velocity = case.oneDimensionalEdgeState(x, r, gas)
    if isinstance(wall, str):
        wall = testWall(x, gas)

    return x, ievlevHeatFlux(x, r, velocity, pressure, wall, properties)['heatFlux']

def holdoutCandidates() -> dict:

    '''

    The gas-side closures Phase 4 chooses between, each as a function of a wall, its gas and its
    wall temperature that returns the wall heat flux. Every one runs on the adopted properties.

    '''

    from NOVA.ievlevHeatTransfer import ievlevGasProperties, ievlevHeatFlux

    def march(exponent):
        def run(location, radius, gas, wall, point):
            heatFlux, _ = case.marchedHeatFlux(location, radius, gas, wall, thicknessInteractionExponent = exponent,
                                               **consistentProperties(gas))
            return heatFlux
        return run

    def ievlev(location, radius, gas, wall, point):
        point = case.operatingPoint(point)
        properties = ievlevGasProperties(case._ceaSolve(point), point['chamberPressure'], point['mixtureRatio'])
        _, _, pressure, velocity = case.oneDimensionalEdgeState(location, radius, gas)
        return ievlevHeatFlux(location, radius, velocity, pressure, wall, properties)['heatFlux']

    return {
        'march, Bartz interaction n = 0.1': march(0.1),
        'march, energy thickness only, n = 0': march(0.0),
        "Ievlev's method": ievlev,
    }

def phase3() -> dict:

    '''

    Ievlev's method against RPA's own output, and against the measurement.

    '''

    heading("PHASE 3: Ievlev's method against RPA's own prediction, RPA's wall as drawn, Test 024")
    rpaX, rpaQ = case.rpaHeatFlux()
    stations = (0.0, 0.10, 0.25, 0.33, 0.355, 0.40, 0.50, 0.60)

    def peak(x, q):
        inside = (x > 0.25) & (x < 0.45)
        return float(np.nanmax(q[inside]))

    print('  location [mm]                    ' + ' '.join(f'{1e3*s:7.0f}' for s in stations) + '   peak/barrel')
    print('  RPA [MW/m^2]                     ' + ' '.join(f'{np.interp(s, rpaX, rpaQ)/1e6:7.1f}' for s in stations)
          + f'   {peak(rpaX, rpaQ)/np.interp(0.25, rpaX, rpaQ):.2f}')
    rows = {}
    for prandtlModel in ('frozen', 'equilibrium'):
        for wall in (550.0, 900.0, 'reduction'):
            x, q = ievlevOnRpaPoint(prandtlModel, wall)
            rows[(prandtlModel, wall)] = (x, q)
            label = f'{wall:.0f} K' if not isinstance(wall, str) else 'reduction'
            print(f'  NOVA, {prandtlModel:11s} Pr, {label:9s} ' + ' '.join(f'{np.interp(s, x, q)/1e6:7.1f}' for s in stations)
                  + f'   {peak(x, q)/np.interp(0.25, x, q):.2f}   barrel {100*(np.interp(0.25, x, q)/np.interp(0.25, rpaX, rpaQ)-1):+.0f} %'
                  + f', peak {100*(peak(x, q)/peak(rpaX, rpaQ)-1):+.0f} %')

    heading("PHASE 3: Ievlev's method against the measurement, RPA wall, 1-D edge, reduction wall")
    candidates = holdoutCandidates()
    gas = case.gasState('measured')
    x, r = case.rpaContour()
    show('  Ievlev, frozen Pr', x, candidates["Ievlev's method"](x, r, gas, testWall(x, gas), 'measured'), x, r)
    show("  RPA's own prediction", rpaX, rpaQ, x, r)

    return rows

def holdoutShapes(function, wallX, wallR) -> np.ndarray:

    '''

    A closure's C over C in the barrel at the TN D-2832 stations, one row per chamber pressure.

    '''

    import tnd2832Case as tn

    shapes = []
    for pressure in tn.chamberPressures:
        point = {'fuel': 'GH2', 'oxidizer': 'LOX', 'mixtureRatio': tn.mixtureRatio,
                 'chamberPressure': pressure, 'expansionRatio': 4.64}
        pointGas = case.gasState(point)
        mach, temperature, staticPressure, velocity = case.oneDimensionalEdgeState(wallX, wallR, pointGas)
        recovery = case.adiabaticWallTemperature(temperature, mach, pointGas['gamma'])
        coefficient = function(wallX, wallR, pointGas, tn.wallTemperature, point) / (recovery - tn.wallTemperature)
        at = [np.interp(tn.stationLocations(), wallX, array) for array in
              (coefficient, temperature, mach, staticPressure, velocity, wallR)]
        constants = tn.correlationConstant(*at, tn.wallTemperature, pointGas['gamma'], pointGas['gasConstant'],
                                           case.viscosityFit(pointGas), pointGas['prandtl']['throat'])
        shapes.append(constants / constants[0])

    return np.array(shapes)

def phase4() -> dict:

    '''

    The closure, chosen on NASA TN D-2832 and then scored on the 40k chamber.

    The selection metric was fixed before any candidate ran: the RMS of the log ratio of model to
    measured C over C in the barrel, over stations 2 to 5, averaged over 300, 600 and 900 psia. The
    candidate with the smallest is the one carried to the 40k chamber, where it is a validation.

    '''

    import tnd2832Case as tn

    heading('PHASE 4: the closure, selected on TN D-2832 and scored on the 40k chamber')
    candidates = holdoutCandidates()
    wallX, wallR = tn.wall()
    measured = tn.measuredShape()
    print('  TN D-2832, C over C in the barrel, stations 1 to 5; measured ' + ' '.join(f'{v:.3f}' for v in measured))

    errors = {}
    for name, function in candidates.items():
        shapes = holdoutShapes(function, wallX, wallR)
        errors[name] = [tn.shapeError(shape) for shape in shapes]
        for pressure, shape, error in zip(tn.chamberPressures, shapes, errors[name]):
            print(f'    {pressure/6894.757:4.0f} psia  {name:40s} ' + ' '.join(f'{v:.3f}' for v in shape)
                  + f'   rms log error {error:.3f}')
    for model, label in (('uniform', 'Bartz uniform (reference)'), ('measured', 'Bartz measured (calibrated on this chamber)')):
        function = lambda x, r, gas, wall, point, model = model: case.bartzHeatFlux(x, r, gas, wall, model,
                                                                                    throatCurvature = tn.throatCurvature)
        shapes = holdoutShapes(function, wallX, wallR)
        errors[label] = [tn.shapeError(shape) for shape in shapes]
        print(f'     600 psia  {label:40s} ' + ' '.join(f'{v:.3f}' for v in shapes[1]) + f'   rms log error {errors[label][1]:.3f}')

    print('\n  Mean over the three pressures, the selection metric')
    ranked = sorted(candidates, key = lambda name: np.mean(errors[name]))
    for name in errors:
        mark = '  <- selected' if name == ranked[0] else ''
        print(f'    {name:46s} {np.mean(errors[name]):.3f}{mark}')

    heading(f'PHASE 4, validation on the 40k chamber: {ranked[0]} selected on TN D-2832')
    gas = case.gasState('measured')
    x, r = case.rpaContour()
    cards = {}
    for name in ranked:
        heatFlux = candidates[name](x, r, gas, testWall(x, gas), 'measured')
        cards[name] = show(f'  {name}, RPA wall, 1-D edge, reduction wall', x, heatFlux, x, r)

    # The march closures under NOVA's own wall and transonic near-wall state
    location, radius, state = novaWall(novaCase('measuredFineTransonic'))
    for exponent in (0.1, 0.0):
        heatFlux, _ = case.marchedHeatFlux(location, radius, gas, testWall(location, gas), edgeState = state,
                                           thicknessInteractionExponent = exponent, **consistentProperties(gas))
        cards[('nova', exponent)] = show(f"  march n = {exponent}, NOVA's wall, transonic near-wall state, reduction wall",
                                         location, heatFlux, location, radius)

    return {'errors': errors, 'selected': ranked[0], 'cards': cards}

def figures() -> None:

    '''

    The report's four figures, written beside the report.

    '''

    import matplotlib
    matplotlib.use('Agg', force = True)
    import matplotlib.pyplot as plt
    import tnd2832Case as tn

    folder = os.path.join(root, 'docs', 'reports', 'calorimeter40k_2026-10-04')
    os.makedirs(folder, exist_ok = True)
    background, panel = '#1a1e2a', '#222735'
    copper, green, ink, muted, warn, blue = '#E0975A', '#86C06C', '#E8E6E1', '#8B93A7', '#E8A0A0', '#6BA3D6'
    plt.rcParams.update({'figure.facecolor': background, 'axes.facecolor': panel,
                         'savefig.facecolor': background, 'text.color': ink, 'axes.labelcolor': ink,
                         'axes.edgecolor': muted, 'xtick.color': muted, 'ytick.color': muted,
                         'grid.color': '#333A4D', 'font.size': 9})

    gas = case.gasState('measured')
    options = consistentProperties(gas)
    measuredX, measuredQ = case.measuredProfile()
    rpaX, rpaR = case.rpaContour()
    location, radius, state = novaWall(novaCase('measuredFineTransonic'))
    _, _, baseState = novaWall(novaCase('measuredFine'))

    # -- Figure 1: the profiles -- #
    fig, (axis, wallAxis) = plt.subplots(2, 1, figsize = (11.2, 9.4), sharex = True,
                                         gridspec_kw = {'height_ratios': [3.0, 1.0, ]})
    fig.subplots_adjust(left = 0.09, right = 0.91, top = 0.93, bottom = 0.07, hspace = 0.07)
    rpaWall = testWall(rpaX, gas)
    bartz = case.bartzHeatFlux(rpaX, rpaR, gas, rpaWall)
    baseline, _ = case.marchedHeatFlux(rpaX, rpaR, gas, rpaWall, thicknessInteractionExponent = 0.1)
    band = []
    for prandtlModel in ('frozen', 'equilibrium'):
        heatFlux, _ = case.marchedHeatFlux(location, radius, gas, testWall(location, gas, prandtlModel),
                                           edgeState = state, **options)
        band.append(heatFlux)
    final = band[0]
    ievlev = holdoutCandidates()["Ievlev's method"](rpaX, rpaR, gas, rpaWall, 'measured')
    rpaFluxX, rpaFluxQ = case.rpaHeatFlux()
    axis.plot(1e3*rpaX, bartz/1e6, color = muted, lw = 1.5, label = 'Bartz, one constant')
    axis.plot(1e3*rpaX, baseline/1e6, color = copper, lw = 1.8, ls = '--',
              label = "Marched layer, Bartz's interaction, default properties, 1-D edge")
    axis.plot(1e3*rpaX, ievlev/1e6, color = blue, lw = 1.8, ls = '-.', label = "NOVA's Ievlev")
    axis.plot(1e3*rpaFluxX, rpaFluxQ/1e6, color = blue, lw = 1.0, ls = ':', label = "RPA's own Ievlev")
    axis.fill_between(1e3*location, band[1]/1e6, band[0]/1e6, color = green, alpha = 0.25, lw = 0)
    axis.plot(1e3*location, final/1e6, color = green, lw = 2.4,
              label = 'Marched layer: n = 0, CEA properties, transonic and MOC edge')
    axis.plot(1e3*measuredX, measuredQ/1e6, 'o', color = ink, ms = 4.2, label = 'Measured, Test 024')
    axis.axvline(1e3*case.throatLocation, color = muted, lw = 0.9, ls = ':')
    axis.axvspan(0.0, 1e3*case.filmCooledEnd, color = warn, alpha = 0.08, lw = 0)
    axis.text(6, 128, 'faceplate coolant,\nnot compared', color = warn, fontsize = 8, va = 'top')
    axis.set_ylabel('Wall heat flux [MW/m$^2$]'); axis.set_ylim(0, 135); axis.set_xlim(0, 500)
    axis.grid(True, alpha = 0.35)
    axis.legend(frameon = False, fontsize = 7.8, loc = 'upper left', bbox_to_anchor = (0.0, 0.86))
    axis.set_title("40k calorimeter chamber, Test 024: gas-side models against the measurement\n"
                   "LOX/LH2, 10.87 MPa, O/F 6.0, every model on the hot-wall temperature the test's reduction used",
                   fontsize = 11, color = ink, pad = 10)
    wallAxis.plot(1e3*rpaX, 1e3*rpaR, color = blue, lw = 1.8, label = "RPA's wall, read densely, on the 42.05 mm throat")
    wallAxis.plot(1e3*location, 1e3*radius, color = copper, lw = 1.4, ls = '--', label = "NOVA's wall")
    wallAxis.plot(coarseRpaContour[:, 0], coarseRpaContour[:, 1], color = warn, lw = 1.0, ls = ':', marker = 'x',
                  ms = 4, label = "RPA's wall read at 11 points")
    wallAxis.axvline(1e3*case.throatLocation, color = muted, lw = 0.9, ls = ':')
    wallAxis.set_ylabel('Radius [mm]'); wallAxis.set_ylim(0, 125); wallAxis.grid(True, alpha = 0.35)
    wallAxis.legend(frameon = False, fontsize = 7.8, loc = 'lower left')
    temperatureAxis = wallAxis.twinx()
    temperatureAxis.plot(1e3*measuredX, testWall(measuredX, gas), color = warn, lw = 1.6,
                         label = "hot-wall temperature of the reduction")
    temperatureAxis.set_ylabel('Wall [K]', color = warn); temperatureAxis.set_ylim(0, 1000)
    temperatureAxis.tick_params(axis = 'y', colors = warn)
    temperatureAxis.legend(frameon = False, fontsize = 7.8, loc = 'lower right')
    wallAxis.set_xlabel('Location from the injector face [mm]')
    fig.savefig(os.path.join(folder, 'heatFluxComparison.png'), dpi = 150)
    plt.close(fig)

    # -- Figure 2: the throat region -- #
    fig, (machAxis, fluxAxis) = plt.subplots(2, 1, figsize = (9.0, 7.4), sharex = True)
    fig.subplots_adjust(left = 0.10, right = 0.97, top = 0.91, bottom = 0.09, hspace = 0.08)
    window = (location > 0.29) & (location < 0.42)
    oneDimensional = case.oneDimensionalEdgeState(location, radius, gas)[0]
    machAxis.plot(1e3*location[window], oneDimensional[window], color = muted, lw = 1.2, ls = ':',
                  label = 'one-dimensional throughout')
    machAxis.plot(1e3*location[window], baseState[0][window], color = copper, lw = 1.8,
                  label = 'one-dimensional upstream, characteristics downstream')
    machAxis.plot(1e3*location[window], state[0][window], color = green, lw = 2.2,
                  label = 'transonic on the entrant arc, characteristics downstream')
    machAxis.axhline(1.0, color = muted, lw = 0.8)
    machAxis.axvline(1e3*case.throatLocation, color = muted, lw = 0.9, ls = ':')
    machAxis.set_ylabel('Wall Mach number [-]'); machAxis.grid(True, alpha = 0.35)
    machAxis.legend(frameon = False, fontsize = 8, loc = 'upper left')
    machAxis.set_title("Throat region, NOVA's wall at 400 stations", fontsize = 10.5, color = ink, pad = 8)
    for edge, color, label in ((baseState, copper, 'one-dimensional upstream'), (state, green, 'transonic upstream')):
        heatFlux, _ = case.marchedHeatFlux(location, radius, gas, testWall(location, gas), edgeState = edge, **options)
        fluxAxis.plot(1e3*location[window], heatFlux[window]/1e6, color = color, lw = 2.0, label = f'march n = 0, {label}')
    inside = (measuredX > 0.29) & (measuredX < 0.42)
    fluxAxis.plot(1e3*measuredX[inside], measuredQ[inside]/1e6, 'o', color = ink, ms = 4.2, label = 'measured')
    fluxAxis.axvline(1e3*case.peakPosition(measuredX, measuredQ), color = ink, lw = 0.9, ls = '--')
    fluxAxis.text(1e3*case.peakPosition(measuredX, measuredQ) - 1.0, 12, 'measured peak', color = ink, fontsize = 8,
                  ha = 'right')
    fluxAxis.axvline(1e3*case.throatLocation, color = muted, lw = 0.9, ls = ':')
    fluxAxis.set_xlabel('Location from the injector face [mm]'); fluxAxis.set_ylabel('Wall heat flux [MW/m$^2$]')
    fluxAxis.set_ylim(0, 110); fluxAxis.grid(True, alpha = 0.35)
    fluxAxis.legend(frameon = False, fontsize = 8, loc = 'upper left')
    fig.savefig(os.path.join(folder, 'throatRegion.png'), dpi = 150)
    plt.close(fig)

    # -- Figure 3: the holdout -- #
    fig, axis = plt.subplots(figsize = (8.6, 5.0))
    fig.subplots_adjust(left = 0.10, right = 0.97, top = 0.88, bottom = 0.14)
    numbers = np.arange(1, 6)
    measured = tn.measuredShape()
    scatter = np.array([station[4] for station in tn.stations]) * measured
    axis.errorbar(numbers, measured, yerr = scatter, fmt = 'o', color = ink, ms = 6, capsize = 3,
                  label = 'TN D-2832, with the scatter about each station')
    wallX, wallR = tn.wall()
    colors = {'march, Bartz interaction n = 0.1': copper, 'march, energy thickness only, n = 0': green,
              "Ievlev's method": blue}
    for name, function in holdoutCandidates().items():
        shapes = holdoutShapes(function, wallX, wallR)
        axis.plot(numbers, shapes[1], color = colors[name], lw = 1.8, marker = 's', ms = 4, label = name)
        axis.fill_between(numbers, shapes.min(axis = 0), shapes.max(axis = 0), color = colors[name], alpha = 0.15, lw = 0)
    labels = []
    for number, station in zip(numbers, tn.stations):
        side = 'subsonic' if station[1] < 0 else ('throat' if station[1] == 0 else 'supersonic')
        labels.append(f'{number}\n{station[2]:.2f}, {side}')
    axis.set_xticks(numbers); axis.set_xticklabels(labels)
    axis.set_xlabel('Station and area ratio'); axis.set_ylabel('C over C in the barrel [-]')
    axis.set_ylim(0.4, 1.15); axis.grid(True, alpha = 0.35); axis.legend(frameon = False, fontsize = 8, loc = 'upper right')
    axis.set_title('NASA TN D-2832 chamber: shape of the gas-side constant\n'
                   'models at 600 psia, bands over 300 to 900 psia', fontsize = 10.5, color = ink, pad = 8)
    fig.savefig(os.path.join(folder, 'holdout.png'), dpi = 150)
    plt.close(fig)

    # -- Figure 4: Ievlev against RPA -- #
    fig, axis = plt.subplots(figsize = (9.0, 5.0))
    fig.subplots_adjust(left = 0.09, right = 0.97, top = 0.88, bottom = 0.11)
    axis.plot(1e3*rpaFluxX, rpaFluxQ/1e6, color = blue, lw = 2.2, ls = '--', label = "RPA's own output (its Figure 14)")
    for (prandtlModel, wall), color, style in ((('frozen', 'reduction'), green, '-'), (('frozen', 900.0), green, ':'),
                                               (('equilibrium', 'reduction'), copper, '-'), (('equilibrium', 900.0), copper, ':')):
        x, q = ievlevOnRpaPoint(prandtlModel, wall)
        label = "the reduction's wall" if isinstance(wall, str) else f'a {wall:.0f} K wall'
        axis.plot(1e3*x, q/1e6, color = color, lw = 1.6, ls = style, label = f'NOVA, {prandtlModel} Prandtl number, {label}')
    axis.axvline(1e3*case.throatLocation, color = muted, lw = 0.9, ls = ':')
    axis.set_xlabel('Location from the injector face [mm]'); axis.set_ylabel('Wall heat flux [MW/m$^2$]')
    axis.set_xlim(0, 650); axis.set_ylim(0, 140); axis.grid(True, alpha = 0.35)
    axis.legend(frameon = False, fontsize = 8, loc = 'upper left')
    axis.set_title("Ievlev's method read from the paper, against RPA's own output\n"
                   "RPA's wall as drawn, Test 024: O/F 6.0, 10.87 MPa", fontsize = 10.5, color = ink, pad = 8)
    fig.savefig(os.path.join(folder, 'novaAgainstRpa.png'), dpi = 150)
    plt.close(fig)
    print('  figures written to', folder)

phases = {'0': phase0, '1a': phase1a, '1b': phase1b, '1c': phase1c, '1d': phase1d, '2': phase2, '3': phase3,
          '4': phase4, 'figures': figures}

if __name__ == '__main__':

    requested = sys.argv[1:] or list(phases)
    for name in requested:
        phases[name]()
