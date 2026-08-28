Back to :ref:`card-index`

Back to :ref:`subsurface-flow-card`

.. _subsurface-flow-mode-card:

MODE
====
Specifies the flow mode within the :ref:`subsurface-flow-card` block.

Required Cards:
---------------

MODE <string>
 Specifies the flow mode. The options for <string> are shown below:

Options:
--------

:ref:`richards-card`
 Single-phase variably saturated groundwater flow using Richards Equation.

:ref:`general-card`
 Multiphase air-water-energy.

:ref:`hydrate-card`
 Multiphase gas-water-energy including gas hydrate formation/dissociation.

:ref:`wipp-flow-card`
 Immiscible two-phase air-water

:ref:`mphase-card`
 Supercritical CO\ :sub:`2`\-water-energy.

:ref:`th-card`
 Coupled groundwater flow and energy/thermal; TH = "Thermo-Hydro".

:ref:`sco2-card`
 Supercritical CO\ :sub:`2`\-water-salt-energy

**Experimental Flow Modes**

IMS, IMMIS, THS
 Immissible two-phase CO\ :sub:`2`\-water-energy.

MISCIBLE
 Miscible H\ :sub:`2`\O-glycol.

FLASH2
 Supercritical CO\ :sub:`2`\-water-energy

Examples:
---------

::

  SIMULATION
    SIMULATION_TYPE SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_FLOW flow
	MODE RICHARDS
      /
    /
  END
