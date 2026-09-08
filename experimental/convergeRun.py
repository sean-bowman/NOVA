'''Grid convergence of the TN D-2327 free-jet characteristic net against the report's cases.'''
import numpy as np, tnd2327 as t

GAMMA = 1.4
gas = t.Gas(GAMMA)

def ambientOverTotal(machJet, staticRatio):
    '''staticRatio is p_j/p_a, the jet static to ambient ratio tabulated in the report.'''
    p0OverPj = (1.0 + 0.5 * (GAMMA - 1.0) * machJet ** 2) ** (GAMMA / (GAMMA - 1.0))
    return 1.0 / (staticRatio * p0OverPj)

cases = [('case2', 5.00, 15.0, 8143.0, 225.0, 1050.0),
         ('case3', 4.79, 26.5, 2926.0, 188.0, 720.0)]

for name, machJet, thetaN, staticRatio, radiusTarget, axialTarget in cases:
    aot = ambientOverTotal(machJet, staticRatio)
    machBoundary = gas.machFromPressureRatio(aot)
    print(f'== {name}: Mj={machJet} thetaN={thetaN} pj/pa={staticRatio:.0f} '
          f'Mb={machBoundary:.3f} | target (r/rj)max={radiusTarget} at x/rj={axialTarget}',
          flush=True)
    for numRays, numLeading in [(30, 400), (45, 600), (60, 800), (90, 1200)]:
        net = t.solveNet(gas, machJet, np.radians(thetaN), 1.0, aot,
                         numRays=numRays, numLeading=numLeading, maxLines=3000)
        bnd = net['boundary']
        radiusMax = max(abs(p.y) for p in bnd)
        axialAt = [p.x for p in bnd if abs(p.y) == radiusMax][0]
        machMax = max(p.mach for ln in net['lines'] for p in ln)
        errR = 100.0 * (radiusMax - radiusTarget) / radiusTarget
        errX = 100.0 * (axialAt - axialTarget) / axialTarget
        print(f'   rays={numRays:4d} lead={numLeading:6d} lines={len(net["lines"]):6d} '
              f'{net["stop"]:20s} Mmax={machMax:8.2f} centre={len(net["centreLine"]):5d} '
              f'shock={len(net["shock"]):4d} '
              f'(r/rj)max={radiusMax:9.2f} ({errR:+7.1f}%) x={axialAt:10.2f} ({errX:+7.1f}%)',
              flush=True)
    print(flush=True)
