Back to :ref:`card-index`

Back to :ref:`subsurface-flow-card`

Back to :ref:`subsurface-flow-mode-card`

.. _sco2-card:

SCO2
=======
Defines options for the SCO2 subsurface flow mode. For more details and governing equations see the Theory Guide.

:ref:`sco2-simulation-options`

:ref:`sco2-timestepper-options`

:ref:`sco2-newton-options`

:ref:`sco2-block-options`

:ref:`sco2-examples`

.. _sco2-simulation-options:

SIMULATION Options
------------------
*(under SUBSURFACE_FLOW in SIMULATION PROCESS_MODELS block)*

.. include:: sim_sco2.tmp

.. _sco2-timestepper-options:

TIMESTEPPER Options
-------------------

.. include:: timestepper_sco2.tmp

.. _sco2-newton-options:

NEWTON_SOLVER Options
---------------------

.. include:: newton_sco2.tmp

.. _sco2-block-options:


.. _sco2-examples:

Examples
--------
::

 SIMULATION
   SIMULATION_TYPE SUBSURFACE
   PROCESS_MODELS
     SUBSURFACE_FLOW flow
       MODE SCO2
       OPTIONS
         ISOTHERMAL_TEMPERATURE 25.d0
       /
     /
   /
 END
 ...
