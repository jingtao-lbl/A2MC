Back to :ref:`card-index`

.. _regression-card:

REGRESSION
==========
Defines the cell IDs and variables for which results are stored for 
regression testing.

Required Cards:
---------------
REGRESSION
 Opens the regression block.

Optional Cards:
---------------
ALL_CELLS
 Prints variables at all cells. Storing variables at a subset of cells
 is preferred to minimize file size.

CELLS_IDS
 Opens a block within which cell IDs may be specified, one per line.

CELLS_PER_PROCESS <integer>
 Specifies the number of cell IDs to be printed per process. The cell IDs
 are sampled evenly on each process.

VARIABLES
 Opens a block for specifying the output :ref:`VARIABLES <output-variables>` 
 to be included. The default variable list from :ref:`output-card` is used 
 if not specified.

Examples
--------
 ::

  REGRESSION
    ALL_CELLS
  END
  
  REGRESSION
    CELLS_PER_PROCESS 2
    CELL_IDS
      29
    /
  END

  REGRESSION
    CELL_IDS
      1
      5
      10
    /
    VARIABLES
       LIQUID_PRESSURE
       GAS_PRESSURE
       GAS_SATURATION
       LIQUID_MOBILITY
       GAS_MOBILITY
    /
  END
