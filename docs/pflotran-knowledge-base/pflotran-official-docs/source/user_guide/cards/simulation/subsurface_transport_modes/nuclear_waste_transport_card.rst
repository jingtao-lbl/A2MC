Back to :ref:`card-index`

Back to :ref:`subsurface-transport-card`

Back to :ref:`subsurface-transport-mode-card`

.. _nuclear-waste-transport-card:

NWT
===
 Indicates that the simulation will include the NWT (Nuclear Waste Transport) 
 mode.
 A corresponding :ref:`nuclear-waste-chemistry-card` card must be included 
 in the SUBSURFACE block.

:ref:`nuclear-waste-transport-simulation-options`

:ref:`nuclear-waste-transport-timestepper-options`

:ref:`nuclear-waste-transport-newton-options`

:ref:`nuclear-waste-transport-examples`

.. _nuclear-waste-transport-simulation-options:

SIMULATION Options 
------------------
*(under SUBSURFACE_TRANSPORT in SIMULATION PROCESS_MODELS block)*

.. include:: sim_nwt.tmp

.. _nuclear-waste-transport-timestepper-options:

TIMESTEPPER Options
-------------------

.. include:: timestepper_nwt.tmp

.. _nuclear-waste-transport-newton-options:

NEWTON_SOLVER Options
---------------------

.. include:: newton_nwt.tmp

.. _nuclear-waste-transport-examples:

Examples
--------
::

  SIMULATION
    SIMULATION_TYPE SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_FLOW flow
        MODE WIPP_FLOW
      /
      SUBSURFACE_TRANSPORT transport
        MODE NWT
      /
    /
  END

