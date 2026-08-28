Back to :ref:`card-index`

Back to :ref:`subsurface-flow-card`

Back to :ref:`subsurface-flow-mode-card`

.. _richards-card:

RICHARDS
========

Defines options for the Richards subsurface flow mode.

:ref:`richards-simulation-options`

:ref:`richards-timestepper-options`

:ref:`richards-newton-options`

:ref:`richards-examples`

.. _richards-simulation-options:

SIMULATION Options 
------------------
*(under SUBSURFACE_FLOW in SIMULATION PROCESS_MODELS block)*

.. include:: sim_richards.tmp

.. _richards-timestepper-options:

TIMESTEPPER Options
-------------------

.. include:: timestepper_richards.tmp

.. _richards-newton-options:
 
NEWTON_SOLVER Options 
---------------------

.. include:: newton_richards.tmp

.. _richards-examples:

Examples
--------
::

 SIMULATION
   SIMULATION_TYPE SUBSURFACE
   PROCESS_MODELS
     SUBSURFACE_FLOW flow
       MODE RICHARDS
     /
   /
   ...
 END
 ...
 SUBSURFACE
   NUMERICAL_METHODS FLOW
     NEWTON_SOLVER
       ITOL_UPDATE 1.d0 ! Convergences with max change in pressure is 1 Pa.
     /
   /
   ...
