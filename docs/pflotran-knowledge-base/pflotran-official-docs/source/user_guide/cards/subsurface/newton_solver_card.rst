Back to :ref:`card-index`

.. _newton-solver-card:

NEWTON_SOLVER
=============
Specifies Newton solver parameters associated with solving the nonlinear system of equations.

Required Cards:
---------------
NEWTON_SOLVER
 Opens the Newton solver block.

Optional Cards:
---------------
*Note: See process model cards for additional NEWTON_SOLVER cards that are process model specific.*

**Note: See the** PETSc_ **users manual for a more definitive explanation of the solver ATOL, DTOL, RTOL and STOL tolerances below.**

.. _PETSc: http://www.mcs.anl.gov/petsc/documentation/index.html

.. include:: ./newton.tmp

Examples
--------
 ::
  
  NEWTON_SOLVER
    ITOL_UPDATE 1.d0
  /

  NEWTON_SOLVER
    PRECONDITIONER_MATRIX_TYPE AIJ
    RTOL 1.d-8
    ATOL 1.d-8
    STOL 1.d-30
    ITOL_UPDATE 1.d0
  /

  NEWTON_SOLVER
    PRECONDITIONER_MATRIX_TYPE AIJ
    RTOL 1.d-12
    ATOL 1.d-12
    STOL 1.d-30
    MAXIMUM_NUMBER_OF_ITERATIONS 10
    NO_INFINITY_NORM
    NO_PRINT_CONVERGENCE
  /

  NEWTON_SOLVER
    CONVERGENCE_INFO
      2R YES
      2X NO
      2U NO
      IR NO
      IU YES
    /
  /

  NEWTON_SOLVER
    MAXIMUM_NUMBER_OF_ITERATIONS  15
    SNES_TYPE NTRDC # ntrdc solver
  /

  NEWTON_SOLVER
    SNES_TYPE NTR # ntr solver
    NTR_OPTIONS
      AUTO_SCALE FALSE # for general mode
      ETA1 0.001 # trust-region parameter
      T1 0.25 # tr shrink factor
      T2 2.00 # tr expansion factor
    END
  /
  
