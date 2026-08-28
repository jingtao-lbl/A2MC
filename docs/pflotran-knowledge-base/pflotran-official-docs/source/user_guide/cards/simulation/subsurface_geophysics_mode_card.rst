Back to :ref:`card-index`

Back to :ref:`subsurface-geophysics-card`

.. _subsurface-geophysics-mode-card:

MODE
====
Specifies the  mode within the :ref:`subsurface-geophysics-card` block.

Required Cards:
---------------

MODE <string>
 Specifies the geophysics mode. The options for <string> are shown below:

Options:
--------

:ref:`ert-card`
 Electrical resistivity tomography.

Examples:
---------

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

