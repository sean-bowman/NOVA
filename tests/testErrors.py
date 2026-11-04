'''

Tests for the failures NOVA raises on purpose, in errors.py.

Every class shares one base so a caller can catch the family, and each prints a banner naming its
own kind, so a convergence failure in the extension solver does not announce itself as a
geometry error.

Author: Sean Bowman

'''

import pytest

from NOVA.errors import (ConvergenceFailureError, GeometricConstraintError, InvalidInputError,
                         NumericalInstabilityError, PressureDropError, REFPROPError,
                         RegenGeometryError, ThermalConstraintError, VoluteGenerationError)

@pytest.mark.parametrize('errorClass, title', [
    (ConvergenceFailureError, 'CONVERGENCE FAILURE'),
    (GeometricConstraintError, 'GEOMETRIC CONSTRAINT'),
    (ThermalConstraintError, 'THERMAL CONSTRAINT'),
    (PressureDropError, 'PRESSURE DROP'),
    (InvalidInputError, 'INVALID INPUT'),
    (NumericalInstabilityError, 'NUMERICAL INSTABILITY'),
    (REFPROPError, 'REFPROP PROPERTY FAILURE'),
    (VoluteGenerationError, 'VOLUTE GENERATION ERROR'),
])
def testEachFailureNamesItsOwnKind(errorClass, title):

    banner = str(errorClass('what went wrong')).splitlines()[2]

    assert banner == title

def testTheBaseKeepsItsOwnBanner():

    assert str(RegenGeometryError('what went wrong')).splitlines()[2] == 'REGENERATIVE GEOMETRY ERROR'

def testEveryKindIsStillCaughtByTheBase():

    for errorClass in (ConvergenceFailureError, InvalidInputError, VoluteGenerationError):
        with pytest.raises(RegenGeometryError):
            raise errorClass('caught by the family')
