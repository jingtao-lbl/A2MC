Back to :ref:`card-index`

Back to :ref:`subsurface-transport-card`

Back to :ref:`subsurface-transport-mode-card`

.. _global-implicit-reactive-transport-card:

GIRT (Global Implicit Reactive Transport)
=========================================
 Indicates that the simulation will include the GIRT 
 (Global Implicit Reactive Transport) mode.
 A corresponding :ref:`chemistry-card` card must be included 
 in the SUBSURFACE block.

:ref:`reactive-transport-simulation-options`

:ref:`reactive-transport-timestepper-options`

:ref:`reactive-transport-newton-options`

:ref:`reactive-transport-examples`

.. _reactive-transport-simulation-options:

SIMULATION Options 
------------------
*(under SUBSURFACE_TRANSPORT in SIMULATION PROCESS_MODELS block)*

.. include:: sim_rt.tmp

.. _reactive-transport-timestepper-options:

TIMESTEPPER Options
-------------------

.. include:: timestepper_rt.tmp

.. _reactive-transport-newton-options:

NEWTON_SOLVER Options
---------------------

.. include:: newton_rt.tmp

.. _reactive-transport-examples:

Examples
--------
::

 SIMULATION
   SIMULATION_TYPE SUBSURFACE
   PROCESS_MODELS
     SUBSURFACE_TRANSPORT transport
       MODE GIRT
       OPTIONS
       /
     /
   /
 END
 ...
 SUBSURFACE
   NUMERICAL_METHODS TRANSPORT
     TIMESTEPPER
       TS_ACCELERATION 16
     /
     NEWTON_SOLVER
       ATOL 1.d-8
       RTOL 1.d-8
       STOL 1.d-30
       DTOL 1.d15
       ITOL 1.d-8
       MAXIMUM_NUMBER_OF_ITERATIONS 25
       ITOL_RELATIVE_UPDATE 1.d-8
     /
   /
   ...

