
# -- Where to Cut an Ideal Contour Against an Ambient -- #

'''

The pressure-cut study of docs/NozzleContourValidation.md: one ideal contour at the shipped nozzle's
design Mach number, cut across a range of area ratios at a sea-level ambient, with the thrust
coefficient integrated over the exit plane at every cut.

A truncated ideal contour delivers its area ratio and its length, and the exit pressure is a
result. This study asks the other question: for a fixed ideal contour and a fixed ambient, which
exit-plane pressure, driven to the ambient, lands the cut at the maximum thrust coefficient. It
compares the wall's static pressure, the mass-averaged and the area-averaged exit pressures against
the maximum the sweep finds.

The thrust coefficient's pressure term is taken against the ambient, so every cut is scored at the
operating point rather than at a design exit pressure. The shipped exit plane, cut at an area ratio
of 40, is printed as well, for the table of exit-plane pressures in the same document.

The exit plane is sampled from a mesh of 50 characteristics, so the thrust coefficient moves in
small steps as the cut crosses mesh lines: about 1e-4 at this resolution, on a curve whose maximum
is flat to that level over an area ratio of about one. The maximum is therefore taken from a
smooth fit through every cut rather than from the single best one, and the fit's residual is
reported as the noise the comparison sits on.

Run from the NOVA root; it solves the shipped nozzle once and then about two hundred cuts, which
takes about an hour. `--reuse` recomputes the summary from the cuts already written:

    python featureShowcase/buildPressureCutStudy.py
    python featureShowcase/buildPressureCutStudy.py --reuse

Writes featureShowcase/pressureCutStudy.json and prints the tables.

Author: Sean Bowman

'''

import json
import os
import sys
import tempfile

import numpy as np
from scipy.optimize import fsolve

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
sys.path.insert(0, os.path.join(root, 'src'))
os.environ.setdefault('NOVA_HEADLESS', '1')

from NOVA import Nozzle
from NOVA.contour import ContourSolution, truncatedIdealContour
from NOVA.characteristics import CharacteristicGas
from NOVA.contourKernel import ThroatGeometry
from NOVA.gasDynamics import machFromAreaRatio

ambientPressure = 101325.0                       # [Pa], sea level
areaRatios = np.round(np.arange(7.0, 18.0001, 0.05), 4)   # [-], cuts of the one ideal contour
outputPath = os.path.join(here, 'pressureCutStudy.json')

def solveShipped() -> Nozzle:

    '''The shipped nozzle, flow only, with its output kept out of the repository's figures.'''

    with open(os.path.join(root, 'src', 'NOVA', 'assets', 'NOVANozzle.json'), encoding = 'utf-8') as handle:
        config = json.load(handle)
    config.pop('_comment', None)
    config.update(filename = 'pressureCutStudy', makeCoolingChannels = False, makeInletVolute = False,
                  makeOutletVolute = False, filmCooling = False, makeRadiativeExtension = False,
                  export = 'off', plotsEnabled = 'off', plumeFieldReach = None)

    scratch = os.path.join(tempfile.gettempdir(), 'novaPressureCutStudy')
    os.makedirs(scratch, exist_ok = True)
    configPath = os.path.join(scratch, 'config.json')
    with open(configPath, 'w', encoding = 'utf-8') as handle:
        json.dump(config, handle, indent = 2)

    Nozzle._getOutputRoot = lambda self: scratch
    nozzle = Nozzle()
    nozzle.generateNozzle(configPath = configPath)

    return nozzle

def designMach(nozzle: Nozzle) -> float:

    '''The design Mach number of the ideal nozzle the shipped contour is cut from, as the design point solves it.'''

    return float(fsolve(nozzle.truncatedIdealContour, x0 = nozzle.idealMachNumber,
                        args = (float(nozzle.lengthFraction), True, False), xtol = 1e-8)[0])

def cut(nozzle: Nozzle, mach: float, areaRatio: float) -> dict:

    '''

    The ideal contour of design Mach number `mach` cut at `areaRatio`, scored against the ambient.

    The solution is built the way `Nozzle.truncatedIdealContour` builds it, with the ambient in
    place of the design exit pressure so the thrust coefficient's pressure term is the operating
    one.

    '''

    gas = CharacteristicGas(nozzle.chamberGamma, nozzle.chamberRGasConstant, nozzle.chamberStagnationTemperature)
    throat = ThroatGeometry(nozzle.chamberGamma, nozzle.throatRadiusNonDimensional,
                            nozzle.throatInletCurvatureNonDimensional, nozzle.throatOutletCurvatureNonDimensional,
                            transonicModel = getattr(nozzle, 'transonicModel', 'sauer'))
    solution = ContourSolution(
        gas = gas, throat = throat, chamberPressure = nozzle.chamberPressure,
        engineMassFlow = nozzle.engineMassFlow, throatGamma = nozzle.throatGamma,
        idealMachNumber = nozzle.idealMachNumber, targetExitPressure = ambientPressure,
        numContourPoints = nozzle.numContourPoints, requestedAreaRatio = float(areaRatio),
        numCharacteristicsRequested = int(getattr(nozzle, 'numCharacteristicsRequested', 50)),
        ambientSpecificImpulse = nozzle.ceaOutput.nozzlePerformance['ambientISP[s]'])
    solution = truncatedIdealContour(solution, mach, float(nozzle.lengthFraction), truncate = True,
                                     assignOutputsToObject = False)

    return {'areaRatio': float(areaRatio), 'thrustCoefficient': float(solution.thrustCoef),
            'wallPressure': float(solution.exitPlanePressure[0]),
            'massAveragedPressure': float(solution.exitMassAveragedPressure),
            'areaAveragedPressure': float(solution.exitAreaAveragedPressure),
            'massClosure': float(solution.exitMassClosure)}

def crossing(ratios: np.ndarray, pressure: np.ndarray) -> float:

    '''The area ratio at which a falling exit pressure reaches the ambient, linear between cuts.'''

    above = np.flatnonzero(pressure >= ambientPressure)
    if above.size == 0 or above[-1] + 1 >= len(ratios):
        return float('nan')
    k = above[-1]
    fraction = (pressure[k] - ambientPressure) / (pressure[k] - pressure[k + 1])
    return float(ratios[k] + fraction * (ratios[k + 1] - ratios[k]))

def smoothThrust(ratios: np.ndarray, thrust: np.ndarray) -> tuple:

    '''

    The thrust coefficient against area ratio, fitted through every cut by a quintic.

    Returns:
    --------
    tuple : (fit, residual), the fitted polynomial and the root-mean-square residual of the cuts
        about it [-]

    '''

    fit = np.polynomial.Polynomial.fit(ratios, thrust, 5)
    residual = float(np.sqrt(np.mean((thrust - fit(ratios))**2)))
    return fit, residual

def solveCuts() -> dict:

    '''The shipped exit plane and every cut of its ideal contour, solved.'''

    nozzle = solveShipped()

    # -- The shipped exit plane -- #
    gamma = nozzle.chamberGamma
    oneDimensionalMach = machFromAreaRatio(float(nozzle.expansionRatio), gamma)
    oneDimensional = nozzle.chamberPressure * (1.0 + 0.5 * (gamma - 1.0) * oneDimensionalMach**2)**(-gamma / (gamma - 1.0))
    plane = np.asarray(nozzle.exitPlanePressure, dtype = float)
    shipped = {'areaRatio': float(nozzle.expansionRatio), 'wall': float(plane[0]),
               'massAveraged': float(nozzle.exitMassAveragedPressure),
               'areaAveraged': float(nozzle.exitAreaAveragedPressure),
               'oneDimensional': float(oneDimensional), 'oneDimensionalMach': float(oneDimensionalMach),
               'axis': float(plane[-1]), 'ceaExitPressure': float(nozzle.targetExitPressure),
               'ceaExitMach': float(nozzle.exitMachNumber)}

    # -- One ideal contour, cut across area ratio -- #
    mach = designMach(nozzle)
    cuts = []
    for areaRatio in areaRatios:
        cuts.append(cut(nozzle, mach, areaRatio))
        print(f'  area ratio {areaRatio:6.2f}   Cf {cuts[-1]["thrustCoefficient"]:.5f}   '
              f'wall {cuts[-1]["wallPressure"]:9.1f} Pa', flush = True)

    return {'ambientPressure': ambientPressure, 'designMach': mach, 'gamma': gamma,
            'numCharacteristics': int(getattr(nozzle, 'numCharacteristicsRequested', 50)),
            'shippedExitPlane': shipped, 'cuts': cuts}

def summarize(results: dict) -> dict:

    '''

    The maximum of the thrust coefficient and where each exit pressure, driven to the ambient,
    would have cut the contour.

    '''

    cuts = results['cuts']
    ratios = np.array([entry['areaRatio'] for entry in cuts])
    thrust = np.array([entry['thrustCoefficient'] for entry in cuts])
    fit, residual = smoothThrust(ratios, thrust)
    fine = np.linspace(ratios[0], ratios[-1], 20001)
    peakRatio = float(fine[np.argmax(fit(fine))])
    peakThrust = float(fit(peakRatio))

    # The area ratios over which the fitted coefficient is within the cuts' scatter of its maximum
    plateau = fine[fit(fine) >= peakThrust - residual]

    targets = {}
    for name in ('wallPressure', 'massAveragedPressure', 'areaAveragedPressure'):
        pressure = np.array([entry[name] for entry in cuts])
        at = crossing(ratios, pressure)
        coefficient = float(fit(at))
        targets[name] = {'areaRatio': at, 'thrustCoefficient': coefficient,
                         'againstPeak': coefficient / peakThrust - 1.0,
                         'wallPressure': float(np.interp(at, ratios, [entry['wallPressure'] for entry in cuts])),
                         'massAveragedPressure': float(np.interp(at, ratios, [entry['massAveragedPressure'] for entry in cuts]))}
    wallAtPeak = float(np.interp(peakRatio, ratios, [entry['wallPressure'] for entry in cuts]))

    results['peak'] = {'areaRatio': peakRatio, 'thrustCoefficient': peakThrust,
                       'wallPressureRatio': wallAtPeak / ambientPressure, 'fitResidual': residual,
                       'plateau': [float(plateau[0]), float(plateau[-1])]}
    results['targets'] = targets
    return results

def main() -> None:

    if '--reuse' in sys.argv and os.path.isfile(outputPath):
        with open(outputPath, encoding = 'utf-8') as handle:
            results = json.load(handle)
    else:
        results = solveCuts()
    results = summarize(results)
    with open(outputPath, 'w', encoding = 'utf-8', newline = '\n') as handle:
        json.dump(results, handle, indent = 1)

    shipped, targets, peak = results['shippedExitPlane'], results['targets'], results['peak']

    print(f'\nshipped exit plane at area ratio {shipped["areaRatio"]:.1f} [Pa]:')
    for key in ('wall', 'massAveraged', 'areaAveraged', 'oneDimensional', 'axis', 'ceaExitPressure'):
        print(f'  {key:16s} {shipped[key]:10.1f}')
    print(f'  one-dimensional Mach {shipped["oneDimensionalMach"]:.4f}, CEA {shipped["ceaExitMach"]:.4f}')
    print(f'\nideal contour of design Mach {results["designMach"]:.4f}, cut against {ambientPressure:.0f} Pa:')
    print(f'  {"target":24s} {"area ratio":>10s} {"Cf":>9s} {"against peak":>13s}')
    for name, entry in targets.items():
        print(f'  {name:24s} {entry["areaRatio"]:10.2f} {entry["thrustCoefficient"]:9.5f} {100 * entry["againstPeak"]:+12.3f} %')
    print(f'  {"maximum":24s} {peak["areaRatio"]:10.2f} {peak["thrustCoefficient"]:9.5f}   '
          f'(wall at {peak["wallPressureRatio"]:.4f} of ambient)')
    print(f'  cuts scatter {peak["fitResidual"]:.1e} about the fit; within it of the maximum from area ratio '
          f'{peak["plateau"][0]:.2f} to {peak["plateau"][1]:.2f}')
    wall = targets['wallPressure']
    print(f'  mass average over wall at the wall cut: {wall["massAveragedPressure"] / wall["wallPressure"]:.3f}')
    print(f'wrote {os.path.relpath(outputPath, root)}')

if __name__ == '__main__':
    main()
