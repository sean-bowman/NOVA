'''
Free-jet characteristic net of NASA TN D-2327, under the names this directory's studies use.

The implementation lives in `src/NOVA/Nozzle.py`, beside the plume correlations it
extends and the nozzle-interior solver it continues. This module is the research face of it: the
convergence sweeps and the showcase figures drive the net directly, at operating points well
outside the envelope `Nozzle.plumeField` accepts, which is what a study of where the formulation
breaks down has to do.

One implementation, two sets of names. Nothing here reimplements anything.
'''
import os
import sys

from NOVA.Nozzle import (                                  # noqa: E402
    PlumeGas as Gas,
    PlumeNode as Point,
    freeJetGeneralPoint as generalPoint,
    freeJetBoundaryPoint as boundaryPoint,
    freeJetSameFamilyPoint as sameFamilyPoint,
    freeJetNearAxisPoint as nearAxisPoint,
    freeJetCenterLinePoint as centerLinePoint,
    freeJetCenterLineTarget as centerLineTarget,
    freeJetCrossing as sameFamilyCrossing,
    freeJetLeadingCharacteristic as leadingCharacteristic,
    freeJetCornerRays as cornerRays,
    freeJetRefineLine as refineLine,
    solveFreeJetNet as solveNet,
    _finish,
    _interpolate,
    _lA,
    _mB,
    _thetaC,
    _WC,
    _freeJetCrossed,
)

__all__ = ['Gas', 'Point', 'generalPoint', 'boundaryPoint', 'sameFamilyPoint', 'nearAxisPoint',
           'centerLinePoint', 'centerLineTarget', 'sameFamilyCrossing', 'leadingCharacteristic',
           'cornerRays', 'refineLine', 'solveNet']
