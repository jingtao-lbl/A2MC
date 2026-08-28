Back to :ref:`card-index`

.. _wallclock-stop-card:

WALLCLOCK_STOP
==============
Specifies a wall clock stopping criteria. Useful if running simulations on a
remote cluster or supercomputer.

Required Cards:
---------------
WALLCLOCK_STOP <float> <string>
 Specifies a wall-clock time and units at which the simulation will
 shut down gracefully generating a restart file, if specified.  The option
 is especially useful when there is an upper limit of wall clock time 
 you can request on supercomputers, and you are not sure if the run will be 
 completed within the time.

Examples
--------
Stop simulation after 12 hours
::

  SUBSURFACE
    ...
    WALLCLOCK_STOP 12 h
    ...
  END SUBSURFACE


Stop simulatoin after 60 minutes
::

  SUBSURFACE
    ...
    WALLCLOCK_STOP 60 min
    ...
  END SUBSURFACE
