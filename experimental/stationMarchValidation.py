
# -- The station marcher against NASA TR R-6's tabulated flow field -- #

'''

The interior of the plume held against a published characteristic solution.

Every other check on this solver reads the jet boundary or a conservation residual. Neither tests
the interior, and TR R-6 is explicit that they cannot: its own reason for computing table II was to
assess how much errors near the axis matter, and it concludes that appreciable errors in the
characteristic net near the axis, and therefore in the velocity along the axis, may have negligibly
small effects upon the boundary shape through the maximum value of y/r even for the critical
condition of a sonic exit. A solver validated on its boundary alone is not validated.

Table II is the one interior reference available. Love, Grigsby, Lee and Woodling computed an
exceptionally dense characteristic net for a near-sonic exit at a jet static pressure ratio of 2,
carrying a second approximation at every axis point, and tabulated the expansion portion of the
field: position, flow angle, Mach angle and velocity ratio at each node.

    NASA TR R-6, Experimental and Theoretical Studies of Axisymmetric Free Jets, Langley Research
    Center, 1959, table II, pages 38 to 66. Initial conditions from Owen and Thornhill, reference
    30 of that report.

What is compared here is the center line, because that is where the report concentrates its own
error and what its figure 74 compares. The reference values are transcribed below.

----------------------------------------------------------------------
                            Reading the table
----------------------------------------------------------------------

The columns are `x/r_i`, `y/r_i`, `theta` and `mu` in radians, and `V/V_t`. Two independent checks
fix the reading, and both come from the table itself rather than from an assumption:

    the exit state    `mu` is 1.483530 rad, which is 85.00 degrees and a Mach number of 1.0038,
                      the initial condition the heading states
    the velocity      `V/V_t` is 0.4095466 there, which is `M / sqrt(2/(gamma-1) + M^2)` at gamma
                      1.4 to seven figures, so `V_t` is the limiting velocity and the gas is air

Recomputing `V/V_t` from `mu` reproduces the tabulated value to better than 1e-7 at ten of the
fifteen center-line rows. The other five lost the leading digit of `mu` in the scan, so `V/V_t` is
taken as the authority throughout; its sequence is smooth and strictly increasing across all
fifteen. The first row sits at `x/r` 0.0874887, which is `1 / tan(85 deg)` to six figures: the
point where the leading characteristic from the lip reaches the center line.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

This is a validation and not a cross-check: TR R-6's net was computed independently, in 1959, by a
different method, and nothing in NOVA informs it. What it does not remove is that the reference is
itself a numerical solution rather than a measurement, so it bounds the difference between two
characteristic solutions of the same problem and not the distance from the real jet.

The error is reported three ways, because no single one of them is honest on its own.

Against `V/V_t` it is small by construction: the center line is undisturbed until the leading
characteristic reaches it, and the ratio only moves from 0.4095 to 0.4601 across the whole
tabulated range, so most of the denominator is a state the scheme never had to compute.

Against the local disturbance, `V/V_t` less its undisturbed value, it is large by construction at
the upstream end, where the disturbance is a part in sixty of what it reaches downstream and any
difference divided by it is enormous. That measure overstates the failure as surely as the first
understates it.

Scaled on the largest disturbance in the tabulated range, it is neither. That is the measure to
read first: what fraction of the wave's own amplitude the two solutions differ by.

Run it from the NOVA root:

    python experimental/stationMarchValidation.py

All units are mass base SI, angles in radians.

Author: Sean Bowman

'''

import math
import os
import sys

import numpy as np
from scipy.interpolate import PchipInterpolator

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from NOVA.plume import PlumeFlow
from stationMarch import solveStationMarch, uniformStation

GAMMA = 1.4
GASCONSTANT = 287.0
STAGNATIONTEMPERATURE = 3000.0
STAGNATIONPRESSURE = 2.0e6
EXITMACH = 1.0038
PRESSURERATIO = 2.0

# x/r_i and V/V_t on the center line, TR R-6 table II. Every block of that table is one
# characteristic of the net, and these are the blocks that begin on the axis, which is their first
# row. The undisturbed value is the first entry, at the foot of the leading characteristic.
TABLETWOAXIS = (
    (0.0874887, 0.4095466), (0.1113133, 0.4104199), (0.1359276, 0.4118920),
    (0.1593610, 0.4139017), (0.1845671, 0.4164393), (0.2070903, 0.4193894),
    (0.2318825, 0.4226923), (0.2543535, 0.4262942), (0.2783136, 0.4301322),
    (0.3033430, 0.4342970), (0.3271733, 0.4387635), (0.3530000, 0.4435692),
    (0.3792871, 0.4487588), (0.4055487, 0.4542555), (0.4325213, 0.4600710))

UNDISTURBEDVELOCITYRATIO = TABLETWOAXIS[0][1]

def referenceFlow() -> PlumeFlow:

    '''The gas the table is computed in.'''

    return PlumeFlow(GAMMA, GASCONSTANT, STAGNATIONTEMPERATURE, STAGNATIONPRESSURE)

def tabulatedExitState() -> dict:

    '''

    The two checks that fix how the table is read.

    Both are consequences of the heading rather than of anything assumed here, so they fail loudly
    if the columns are ever misidentified.

    '''

    machAngle = 1.483530
    mach = 1.0/math.sin(machAngle)
    velocityRatio = mach/math.sqrt(2.0/(GAMMA - 1.0) + mach**2)

    return {'machAngleDegrees': math.degrees(machAngle), 'mach': mach,
            'velocityRatio': velocityRatio,
            'velocityRatioError': velocityRatio - UNDISTURBEDVELOCITYRATIO,
            'leadingCharacteristicFoot': 1.0/math.tan(machAngle),
            'firstTabulatedStation': TABLETWOAXIS[0][0]}

def centerLineVelocity(count: int, maxLength: float = 1.0) -> dict:

    '''

    March the sonic exit and return the center-line velocity ratio along it.

    The march is run only as far as the table reaches. It survives about 2.3 lip radii at this exit
    Mach number before a station fails, which is well past the 0.43 the table covers.

    '''

    flow = referenceFlow()
    station = uniformStation(flow, EXITMACH, 1.0, count)
    ambient = flow.staticPressure(EXITMACH)/PRESSURERATIO
    result = solveStationMarch(flow, station, ambient, maxLength = maxLength,
                               maxStations = 400000)

    x = np.array([station.x for station in result['stations']])
    mach = np.array([float(station.mach[0]) for station in result['stations']])
    velocityRatio = np.array([flow.velocity(value) for value in mach])/flow.maxVelocity
    drift = np.array(result['massDrift'])

    # A sonic exit takes very short first steps, and two stations closer together than the
    # interpolant's own divided differences can carry send it to infinity.
    advancing = np.concatenate(([True], np.diff(x) > 1e-9))

    return {'x': x[advancing], 'velocityRatio': velocityRatio[advancing],
            'reach': float(x[-1]), 'stop': result['stop'],
            'stations': len(result['stations']),
            'worstDrift': float(drift[np.argmax(np.abs(drift))])}

def compare(count: int) -> dict:

    '''The march sampled at the table's stations, with both error measures.'''

    reference = np.array(TABLETWOAXIS)
    solved = centerLineVelocity(count)
    if solved['reach'] < reference[-1, 0]:
        return {'count': count, 'short': True, **solved}

    sampled = PchipInterpolator(solved['x'], solved['velocityRatio'])(reference[:, 0])
    ratioError = 100.0*(sampled/reference[:, 1] - 1.0)

    disturbance = reference[:, 1] - UNDISTURBEDVELOCITYRATIO
    solvedDisturbance = sampled - UNDISTURBEDVELOCITYRATIO
    peak = np.abs(disturbance).max()
    scaledError = 100.0*(solvedDisturbance - disturbance)/peak

    # The first station is undisturbed by definition and the next few carry a part in sixty of
    # what the wave reaches, so a relative error against them is a small denominator rather than a
    # result. Reported for completeness, read after the scaled one.
    usable = disturbance > 0.05*peak
    relativeError = 100.0*(solvedDisturbance[usable]/disturbance[usable] - 1.0)

    return {'count': count, 'short': False, 'sampled': sampled, 'ratioError': ratioError,
            'scaledError': scaledError, 'relativeError': relativeError,
            'peakDisturbance': peak, **solved}

def report(counts = (81, 161, 321)) -> None:

    '''Print the exit-state checks and the comparison at each resolution.'''

    exit = tabulatedExitState()
    print('TR R-6 table II, near-sonic exit at a jet static pressure ratio of 2')
    print(f'  tabulated mu 1.483530 rad is {exit["machAngleDegrees"]:.4f} deg, '
          f'Mach {exit["mach"]:.4f} against the heading 1.0038')
    print(f'  V/Vt from that Mach is {exit["velocityRatio"]:.7f} against the tabulated '
          f'{UNDISTURBEDVELOCITYRATIO:.7f}, difference {exit["velocityRatioError"]:.1e}')
    print(f'  1/tan(mu) is {exit["leadingCharacteristicFoot"]:.7f} against the first tabulated '
          f'station {exit["firstTabulatedStation"]:.7f}')
    print()
    print('error scaled on the peak disturbance is the one to read; see the module docstring')
    print(f'{"points":>7} {"stations":>9} {"drift %":>9} {"max scaled %":>13} '
          f'{"rms scaled %":>13} {"max V/Vt %":>11} {"rms V/Vt %":>11} {"max rel %":>10}')

    detail = None
    for count in counts:
        result = compare(count)
        if result['short']:
            print(f'{count:7d} {result["stations"]:9d} '
                  f'ended short of the table at {result["reach"]:.3f}, {result["stop"]}')
            continue
        ratio, scaled = result['ratioError'], result['scaledError']
        print(f'{count:7d} {result["stations"]:9d} {result["worstDrift"]:+9.3f} '
              f'{np.abs(scaled).max():13.2f} {np.sqrt((scaled**2).mean()):13.2f} '
              f'{np.abs(ratio).max():11.3f} {np.sqrt((ratio**2).mean()):11.3f} '
              f'{np.abs(result["relativeError"]).max():10.1f}')
        detail = result

    if detail is not None:
        print()
        print(f'  per station at {detail["count"]} points, peak disturbance in V/Vt '
              f'{detail["peakDisturbance"]:.7f}')
        print(f'    {"x/r":>9} {"table":>10} {"march":>10} {"V/Vt %":>8} {"scaled %":>9}')
        for (position, value), got, ratioValue, scaledValue in zip(
                TABLETWOAXIS, detail['sampled'], detail['ratioError'], detail['scaledError']):
            print(f'    {position:9.5f} {value:10.7f} {got:10.7f} {ratioValue:8.3f} '
                  f'{scaledValue:9.2f}')

if __name__ == '__main__':
    report()
