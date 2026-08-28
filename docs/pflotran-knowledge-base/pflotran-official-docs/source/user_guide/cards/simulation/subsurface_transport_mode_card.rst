Back to :ref:`card-index`

Back to :ref:`subsurface-transport-card`

.. _subsurface-transport-mode-card:

MODE
====
Specifies the transport mode within the :ref:`subsurface-transport-card` block.

Required Cards:
---------------

MODE <string>
 Specifies the transport mode. The options for <string> are shown below:

Options:
--------

:ref:`global-implicit-reactive-transport-card`: Global implicit reactive transport

:ref:`operator-split-reactive-transport-card`: Operator-split reactive transport

:ref:`nuclear-waste-transport-card`: Nuclear waste transport (expert-only)

Examples:
---------

::

  SIMULATION
    SIMULATION_TYPE SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_FLOW flow
	MODE GIRT
        OPTIONS
          ...
        /
      /
    /
  END
