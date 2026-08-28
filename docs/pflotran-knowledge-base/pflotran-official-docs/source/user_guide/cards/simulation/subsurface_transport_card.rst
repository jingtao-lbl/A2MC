Back to :ref:`card-index`

.. _subsurface-transport-card:

SUBSURFACE_TRANSPORT
====================

Required Cards
--------------

:ref:`subsurface-transport-mode-card` <string>
 Specifies the transport mode to be employed.  Follow the links below for a
 description of each transport mode's options.

Transport Modes
+++++++++++++++

 :ref:`global-implicit-reactive-transport-card`: Global implicit reactive transport

 :ref:`operator-split-reactive-transport-card`: Operator-split reactive transport

 :ref:`nuclear-waste-transport-card`: Nuclear waste transport (expert-only)

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
     SUBSURFACE_TRANSPORT transport
       MODE GIRT
       OPTIONS
         TEMPERATURE_DEPENDENT_DIFFUSION
       /
     /
   /
 END

