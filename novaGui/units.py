# -- NOVA GUI Unit Conversions -- #

'''

Per-field display units for the config form.

Every field is stored and handed to the backend in NOVA's own SI unit; the form shows it in
whatever the field's dropdown is set to. The conversion itself belongs to the package, so this
module is a re-export of `NOVA.units` rather than a second table of factors.

It used to be that table. The factors were hand-copied to match `src/NOVA/units.py` and
`ceaInterface.py`, which is three places for one number to be right in, and the affine
temperature entries were spelled out as (scale, offset) pairs. All of that now comes from the
package's unit registry.

The names here are the ones the widgets already call, so `widgets.py` and `configSchema.py` are
unchanged by the move.

Author: Sean Bowman

'''

from NOVA.units import DIMENSIONS, UNIT_TO_DIMENSION, dimensionForUnit, fromSI, siUnit, toSI, unitsFor

__all__ = ['DIMENSIONS', 'UNIT_TO_DIMENSION',
           'dimensionForUnit', 'unitsFor', 'siUnit', 'toSI', 'fromSI']
