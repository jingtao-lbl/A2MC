Back to :ref:`card-index`

Back to :ref:`subsurface-flow-card`

Back to :ref:`subsurface-flow-mode-card`

.. _th-card:

TH
==

Defines options for the TH subsurface flow mode. For more details and governing equations see the Theory Guide.

:ref:`th-simulation-options`

:ref:`th-timestepper-options`

:ref:`th-newton-options`

:ref:`th-examples`

.. _th-simulation-options:

SIMULATION Options 
------------------
*(under SUBSURFACE_FLOW in SIMULATION PROCESS_MODELS block)*

.. include:: sim_th.tmp

.. _th-timestepper-options:

TIMESTEPPER Options
-------------------

.. include:: timestepper_th.tmp

.. _th-newton-options:

NEWTON_SOLVER Options
---------------------
 
.. include:: newton_th.tmp

.. _th-examples:

Examples
--------
::

  SIMULATION
    SIMULATION_TYPE SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_FLOW flow
        MODE TH
        OPTIONS
          FREEZING
          ICE_MODEL PAINTER_EXPLICIT
        /
      /
    /
  END
  ...
  SUBSURFACE
    NUMERICAL_METHODS FLOW
      TIMESTEPPER
        TS_ACCELERATION 25
        PRESSURE_CHANGE_GOVERNOR 1.d5
        TEMPERATURE_CHANGE_GOVERNOR 0.1d0
        CONCENTRATION_CHANGE_GOVERNOR 1.d-1
      /
      NEWTON_SOLVER
        ATOL 1.d-12
        RTOL 1.d-8
        STOL 1.d-12
        ITOL 1.d-8
        MAX_NORM 1.d6
        MAXIMUM_NUMBER_OF_ITERATIONS 100
        MAXF 1000
      /
    /
    ...
