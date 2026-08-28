Back to :ref:`card-index`

.. _overwrite-restart-transport-card:

OVERWRITE_RESTART_TRANSPORT
===========================
Upon restarting a reactive transport simulation, solution concentrations, read
from the restart file, are overwritten with the concentrations specified 
in the transport initial conditions.

Required Cards:
---------------
OVERWRITE_RESTART_TRANSPORT

Examples
--------

See also ``PFLOTRAN_DIR/regression_tests/default/543/543_hanford_overwrite_restart.in``.

::

  SUBSURFACE
    ...
    OVERWRITE_RESTART_TRANSPORT
    ...
  END SUBSURFACE
