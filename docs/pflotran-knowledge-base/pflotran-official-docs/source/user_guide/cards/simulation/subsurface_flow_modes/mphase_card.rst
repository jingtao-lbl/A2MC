Back to :ref:`card-index`

Back to :ref:`subsurface-flow-card`

Back to :ref:`subsurface-flow-mode-card`

.. _mphase-card:

MPHASE
======

The MPHASE keyword defines options for the MPHASE supercritical CO\ :math:`_2`\ subsurface flow mode. For more details and governing equations see the Theory Guide.

:ref:`mphase-simulation-options`

:ref:`mphase-timestepper-options`

:ref:`mphase-newton-options`

:ref:`mphase-examples`

.. _mphase-simulation-options:

SIMULATION Options 
------------------
*(under SUBSURFACE_FLOW in SIMULATION PROCESS_MODELS block)*

.. _mphase-timestepper-options:

TIMESTEPPER Options
-------------------

.. include:: timestepper_mphase.tmp

.. _mphase-newton-options:

NEWTON_SOLVER Options
---------------------
 
.. include:: newton_mphase.tmp

.. _mphase-examples:

Examples
--------
::

 SIMULATION
   SIMULATION_TYPE SUBSURFACE
   PROCESS_MODELS
     SUBSURFACE_FLOW flow
       MODE MPHASE
     /
   /
 END
 ... 
 SUBSURFACE
   NUMERICAL_METHODS FLOW
     TIMESTEPPER
       TS_ACCELERATION 8
       PRESSURE_CHANGE_GOVERNOR 5.e4
       TEMPERATURE_CHANGE_GOVERNOR 5.d0
       CONCENTRATION_CHANGE_GOVERNOR 1.e-2
       SATURATION_CHANGE_GOVERNOR 0.025
     /
     NEWTON_SOLVER
       ATOL 1.d-12
       RTOL 1.d-12
       STOL 1.d-30
       DTOL 1.d15
       ITOL 1.d-8
       MAXIMUM_NUMBER_OF_ITERATIONS 25
       MAXF 100
     /
   /
   ...
