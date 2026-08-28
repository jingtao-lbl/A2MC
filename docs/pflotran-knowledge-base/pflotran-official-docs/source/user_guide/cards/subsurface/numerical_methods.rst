Back to :ref:`card-index`

.. _numerical-methods-card:

NUMERICAL_METHODS
=================
Specifies numerical methods employed to solve a process model.

Required Cards:
---------------
NUMERICAL_METHODS <string>
 Opens the numerical methods block and specifies the process model for which
 the numerical methods are employed (e.g. FLOW, TRANSPORT).

Optional Cards:
---------------
:ref:`timestepper-card`
 Time integration settings.

:ref:`newton-solver-card`
 Newton solver settings.

:ref:`linear-solver-card`
 Linear solver settings.

Examples
--------
 ::

  NUMERICAL_METHODS FLOW

    TIMESTEPPER
      TIMESTEP_REDUCTION_FACTOR 0.75d0
      TIMESTEP_MAXIMUM_GROWTH_FACTOR 1.9d0
      MAXIMUM_CONSECUTIVE_TS_CUTS 10
      INITIAL_TIMESTEP_SIZE 1.d0 h
      MAXIMUM_TIMESTEP_SIZE 1.d0 y
    /

    NEWTON_SOLVER
      ITOL_UPDATE 1.d0
      RTOL 1.d-20
      MAXIMUM_NUMBER_OF_ITERATIONS 15
      CONVERGENCE_INFO
    /

    LINEAR_SOLVER
      SOLVER DIRECT
    /

  /
