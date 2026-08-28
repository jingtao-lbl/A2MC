Back to :ref:`card-index`

.. _subsurface-geophysics-card:

SUBSURFACE_GEOPHYSICS
=====================

Required Cards
--------------

:ref:`subsurface-geophysics-mode-card` <string>
 Specifies the geophysics mode to be employed.  Follow the links below for a 
 description of each geophysics mode's options. 

Geophysics Modes
++++++++++++++++

 :ref:`ert-card`: electrical resistivity tomography

Optional Cards
--------------

OPTIONS 
 MODE-dependent block for defining options for each geophysics process model. 
 Click on the MODEs above to see MODE-dependent options.

Examples
--------
::

 SIMULATION
   SIMULATION_TYPE SUBSURFACE
   PROCESS_MODELS
     SUBSURFACE_GEOPHYSICS geophysics
       MODE ERT
       OPTIONS
         COMPUTE_JACOBIAN
       /
     /
   /
 END

