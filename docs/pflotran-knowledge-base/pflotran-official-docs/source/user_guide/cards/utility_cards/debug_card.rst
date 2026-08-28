Back to :ref:`card-index`

.. _debug-card:

DEBUG
===== 
Defines debugging options for writing data to the screen, output file and other 
external files.

Required Cards:
---------------
DEBUG
 Opens the DEBUG block.

Optional Cards:
---------------
PRINT_SOLUTION
 Prints current solution at each Newton iteration (filename = MODExx.dat).

PRINT_RESIDUAL
 Prints current residual at each Newton iteration (filename = MODEresidual.dat).

PRINT_JACOBIAN
 Prints current Jacobian at each Newton iteration (filename = MODEjacobian.dat).

PRINT_JACOBIAN_DETAILED
 Prints current detailed Jacobian at each Newton iteration, splitting out 
 individual contributions (e.g. accumulation, internal fluxes, bc fluxes, 
 src/sinks).  Not supported for all modes.

PRINT_JACOBIAN_NORM
 Prints norm of Jacobian at each Newton iteration.

PRINT_COUPLERS
 Prints each coupler to a file (for checking boundary connections).

.. PRINT_NUMERICAL_DERIVATIVES
 Not yet supported, but when finished, this will print the values of the 
 numerical derivative used to create the Jacobian matrix.

PRINT_WAYPOINTS
 Prints the list of waypoints to the screen and to the pflotran.out file.

FORMAT
 Sets the format for exported PETSc vectors (solution, residual, etc.) and matrices (Jacobian). Supported formats include: 
  * ASCII: [\*.out]
  * BINARY: [\*.bin]
  * MATLAB: [\*.mat]
  * NATIVE: [\*.bin] PETSc parallel layout. Vectors and matrices are printed in their parallel layout and not converted back to natural numbering.

APPEND_COUNTS_TO_FILENAMES
 Appends the cumulative timestep, timestep cut, and Newton iteration counts to the filename.

Examples
--------
::

 DEBUG
   PRINT_SOLUTION
   PRINT_RESIDUAL
   PRINT_JACOBIAN
   FORMAT MATLAB
   APPEND_COUNTS_TO_FILENAMES
 END

