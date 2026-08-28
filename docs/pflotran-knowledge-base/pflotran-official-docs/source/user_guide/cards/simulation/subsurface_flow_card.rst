Back to :ref:`card-index`

.. _subsurface-flow-card:

SUBSURFACE_FLOW
===============

Required Cards
--------------

:ref:`subsurface-flow-mode-card` <string>
 Specifies the flow mode to be employed.  Follow the links below for a 
 description of each flow mode's options. 

Flow Modes
++++++++++

 :ref:`richards-card`: single-phase variably saturated flow

 :ref:`th-card`: variably saturated flow and energy (and optional ice phase)

 :ref:`wipp-flow-card`: two-phase immiscible air-water

 :ref:`general-card`: two-phase air-water-energy

 :ref:`mphase-card`: supercritical CO\ :sub:`2`\-water-energy

 IMMIS: immiscible two-phase CO\ :sub:`2`\-water-energy (expert only)

 MISCIBLE: miscible H\ :sub:`2`\O-glycol (expert only)

 FLASH2: supercritical CO\ :sub:`2`\-water-energy (expert only)

Optional Cards
--------------

OPTIONS 
 MODE-dependent block for defining options for each flow process model. Click 
 on the MODEs above to see MODE-dependent options.

Examples
--------
::

 SIMULATION
   SIMULATION_TYPE SUBSURFACE
   PROCESS_MODELS
     SUBSURFACE_FLOW flow
       MODE GENERAL
       OPTIONS
         SKIP_RESTART
         LOGGING_VERBOSITY 1.d0
         ! GENERAL mode specific cards
         ISOTHERMAL
         TWO_PHASE_ENERGY_DOF TEMPERATURE
         GAS_COMPONENT_FORMULA_WEIGHT 2.01588d0
       /
     /
   /
 END
