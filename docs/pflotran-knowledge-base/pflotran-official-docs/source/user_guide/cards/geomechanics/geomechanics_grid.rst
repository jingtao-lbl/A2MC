Back to :ref:`card-index`

.. _geomechanics-grid-card:

GEOMECHANICS_GRID
=================
The grid type and the format for geomechanics is specified here. Only unstructured grids can be read. Even structure grids should be generated as unstructured grids.

Required Cards:
---------------
TYPE <type> <filename>
  Type unstructured should be specified in <type> with <filename> being the filename of the grid.

GRAVITY <# # #>
  Specify gravity vector for geomechanics calculations (Default: 0 0 -9.81 m/s2)

Examples
--------

 ::

  
 
  GEOMECHANICS_GRID
    TYPE unstructured geomech_dat/usg.mesh
    GRAVITY 0.0 0.0 0.0
  END
