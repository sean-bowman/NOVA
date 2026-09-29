# -- Which exit pressure, and how far the march holds against it -- #

'''

The two exit states a truncated contour leaves, and the reach over which the station marcher
conserves mass against the lip one.

A truncated ideal contour does not leave one exit state. The one-dimensional design station and the
lip differ by however much contour was removed, so `Pe/Pa` names two numbers. Correlations are
written in the one-dimensional ratio; the free boundary the station marcher imposes is at the lip.
This prints both, the factor between them, and what that factor does to the `plumeFieldMaxPressureRatio`
gate in `solvePlumeField`, which tests the one-dimensional ratio while the march it guards works at
the lip.

The second table separates discretization error from the scheme's interior defect. Mass flow through
every station must equal mass flow through the exit plane. Holding the lip ratio at 1.5, the worst
departure is measured over four reaches at three station resolutions. A reach whose error falls
under refinement is limited by the mesh; a reach whose error holds or grows is limited by the
scheme, and no refinement will recover it.

Run it from the NOVA root, after `python featureShowcase/runBaseCase.py` has written the pickle:

    python experimental/exitPressureConvention.py

Author: Sean Bowman

'''

import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'experimental'))

from NOVA.plume import (PlumeFlow, plumeCharacteristicSeed, plumeExitLine, solvePlumeStructure,
                        plumeFieldMaxPressureRatio, plumeFieldMaxWallAngle)
import stationMarch as sm

PICKLE = ROOT / 'featureShowcase' / 'showcaseBase.pkl'
LIPRATIO = 1.5                       # [-], lip static pressure over ambient
SAMPLES = (0.5, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0)   # [-], stations sampled, in lip radii
RESOLUTIONS = (81, 161, 321)         # [-], points across the starting station
DESIGNAMBIENT = 5000.0               # [Pa], the ambient the shipped contour is sized at
def loadNozzle():
    '''The shipped nozzle, as the showcase base case writes it.'''
    with open(PICKLE, 'rb') as handle:
        return pickle.load(handle)

def conventions(nozzle):

    '''

    Both exit states and the gate arithmetic between them.

    `solvePlumeStructure` needs an ambient pressure to report a ratio at all, so it is called at the
    lip pressure itself: the reported states do not depend on that choice, only the ratio does.

    '''

    contour = nozzle.plumeContour()
    seed = plumeCharacteristicSeed(contour)
    flow = PlumeFlow(seed['gamma'], seed['gasConstant'], seed['stagnationTemperature'],
                     seed['stagnationPressure'])
    line = plumeExitLine(flow, seed, numPoints = 400)

    # `plumeExitLine` returns its points lip first, descending in radius; `stationFromLine`
    # reverses that so the station runs axis to lip. Reading the lip off the station rather than
    # the raw list is what the march itself does, and the two ends differ by the truncation.
    lipMach = float(sm.stationFromLine(line, 81).mach[-1])
    lipPressure = flow.staticPressure(lipMach)

    structure = solvePlumeStructure(contour, ambientPressure = lipPressure)

    print('exit states on the shipped contour')
    print(f'  lip, from the characteristic mesh   Mach {lipMach:7.3f}   {lipPressure:9.1f} Pa')
    print(f'  one dimensional design station      Mach {structure.exitMach:7.3f}   '
          f'{structure.exitPressure:9.1f} Pa')
    factor = lipPressure / structure.exitPressure
    print(f'  lip over one dimensional            {factor:7.3f}')
    print()
    print('what that does to the envelope gate')
    print(f'  gate refuses one dimensional Pe/Pa above {plumeFieldMaxPressureRatio:.2f}')
    print(f'  which is a lip ratio of                  {plumeFieldMaxPressureRatio*factor:.2f}')
    print(f'  wall angle gate refuses past             {np.degrees(plumeFieldMaxWallAngle):.2f} deg')
    print(f'  this contour diverges at                 '
          f'{np.degrees(abs(structure.lipWallAngle)):.2f} deg')
    print('  so every bell is refused on angle first, and the pressure gap never shows')

    return flow, line, lipPressure

def convergence(flow, line, lipPressure):

    '''

    Mass continuity error at fixed stations, at three station resolutions.

    Reported at the station rather than as a running worst. The drift is not monotone: it dips,
    recovers through zero near six lip radii and then runs away, so a running worst reports one
    excursion in every row past it and hides where the error actually is.

    '''

    ambient = lipPressure/LIPRATIO
    profiles = {}
    for points in RESOLUTIONS:
        station = sm.stationFromLine(line, points)
        result = sm.solveStationMarch(flow, station, ambient, maxLength = max(SAMPLES),
                                      maxStations = 400000)
        # Station x is absolute machine coordinate, so the exit plane is subtracted off before
        # scaling: the reach a march covers is measured from the exit plane, not from the origin.
        axial = ((np.array([s.x for s in result['stations']]) - station.x)
                 / station.boundaryRadius)
        drift = np.array(result['massDrift'])
        profiles[points] = (axial, drift, result['stop'])

    print()
    print(f'mass continuity error at station, per cent of exit mass flow, lip ratio {LIPRATIO}')
    print('  the axial coordinate is distance downstream of the exit plane in lip radii')
    header = ' '.join(f'{points:>10d}' for points in RESOLUTIONS)
    print(f'  {"x/rLip":>7} {header}')
    for target in SAMPLES:
        row = []
        for points in RESOLUTIONS:
            axial, drift, _ = profiles[points]
            row.append(f'{np.interp(target, axial, drift):+10.3f}')
        print(f'  {target:7.1f} ' + ' '.join(row))

    print()
    print('  the negative excursion, and where it sits')
    for points in RESOLUTIONS:
        axial, drift, _ = profiles[points]
        index = int(np.argmin(drift))
        print(f'  {points:4d} points  {drift[index]:+7.3f} per cent at x/rLip {axial[index]:.2f}')
    print('  a location that does not move with resolution is a feature of the flow, not the mesh')

    station = sm.stationFromLine(line, RESOLUTIONS[-1])
    result = sm.solveStationMarch(flow, station, ambient, maxLength = max(SAMPLES),
                                  maxStations = 400000)
    axial = ((np.array([s.x for s in result['stations']]) - station.x)/station.boundaryRadius)
    axisMach = np.array([float(s.mach[0]) for s in result['stations']])
    print()
    print('  center-line Mach number, which says when the lip fan arrives')
    for target in (0.0, 2.0, 4.0, 4.4, 5.0, 6.0, 8.0):
        print(f'  x/rLip {target:4.1f}   Mach {np.interp(target, axial, axisMach):.4f}')
    print(f'  flat to four figures until x/rLip 4, so nothing has reached the axis before then')

def atTheDesignAmbient(flow, line, lipPressure):

    '''Worst mass drift at the ambient the nozzle was contoured for, over the same six radii.'''

    station = sm.stationFromLine(line, RESOLUTIONS[1])
    result = sm.solveStationMarch(flow, station, DESIGNAMBIENT, maxLength = 6.0,
                                  maxStations = 400000)
    drift = np.array(result['massDrift'])
    worst = float(drift[np.argmax(np.abs(drift))])
    print()
    print(f'at the design ambient of {DESIGNAMBIENT:.0f} Pa, a lip ratio of '
          f'{lipPressure/DESIGNAMBIENT:.2f}')
    print(f'  worst mass drift within six lip radii  {worst:+.2f} per cent   '
          f'({result["stop"]}, {RESOLUTIONS[1]} points)')
    print('  no window exists at this ratio')

if __name__ == '__main__':
    nozzle = loadNozzle()
    flow, line, lipPressure = conventions(nozzle)
    convergence(flow, line, lipPressure)
    atTheDesignAmbient(flow, line, lipPressure)
