Back to :ref:`card-index`

Back to :ref:`subsurface-flow-card`

Back to :ref:`subsurface-flow-mode-card`

.. _general-card:

GENERAL
=======
Defines options for the General subsurface flow mode. For more details and governing equations see the Theory Guide.

:ref:`general-simulation-options`

:ref:`general-timestepper-options`

:ref:`general-newton-options`

:ref:`general-examples`

.. _general-simulation-options:

SIMULATION Options 
------------------
*(under SUBSURFACE_FLOW in SIMULATION PROCESS_MODELS block)*

.. include:: sim_general.tmp

.. _general-timestepper-options:

TIMESTEPPER Options
-------------------

.. include:: timestepper_general.tmp

.. _general-newton-options:

NEWTON_SOLVER Options
---------------------

.. include:: newton_general.tmp

.. _general-examples:

Examples
--------
::

 SIMULATION
   SIMULATION_TYPE SUBSURFACE
   PROCESS_MODELS
     SUBSURFACE_FLOW flow
       MODE GENERAL
       OPTIONS
         #  WINDOW_EPSILON 1.d-4
         ISOTHERMAL
         TWO_PHASE_STATE_ENERGY_DOF TEMPERATURE
         ARITHMETIC_GAS_DIFFUSIVE_DENSITY
         NEWTONTRDC_HOLD_INNER_ITERATIONS
       /
     /
   /
 END
 ...
 SUBSURFACE
   NUMERICAL_METHODS FLOW
     TIMESTEPPER
       TS_ACCELERATION 8
       MAX_TS_CUTS 10
     /
     NEWTON_SOLVER
       ATOL 1.d-8
       RTOL 1.d-8
       STOL 1.d-30
       NO_INFINITY_NORM
       MAXIMUM_NUMBER_OF_ITERATIONS 15
       RESIDUAL_SCALED_INF_TOL 1.d-5
     /
     LINEAR_SOLVER
       SOLVER DIRECT
     /
   /
   ...

