Back to :ref:`card-index`

Back to :ref:`subsurface-flow-card`

Back to :ref:`subsurface-flow-mode-card`

.. _wipp-flow-card:

WIPP_FLOW
=========
Defines options for the WIPP_FLOW subsurface flow mode.

:ref:`wipp-flow-simulation-options`

:ref:`wipp-flow-timestepper-options`

:ref:`wipp-flow-newton-options`

:ref:`wipp-flow-examples`

.. _wipp-flow-simulation-options:

SIMULATION Options 
------------------
*(under SUBSURFACE_FLOW in SIMULATION PROCESS_MODELS block)*

.. include:: sim_wipp_flow.tmp

------------------

**Debugging Options**

RESIDUAL_TEST
 Toggle on printing of residual information at a specific cell. RESIDUAL_TEST_CELL must be defined.

RESIDUAL_TEST_CELL
 Cell at which residual information will be printed when RESIDUAL_TEST is present.

JACOBIAN_TEST
 Toggles on testing of numerical Jacobian usign full residual evaluation.

JACOBIAN_TEST_RDOF
 Residual equation that will be printed for JACOBIAN_TEST (X in dR/dX).

JACOBIAN_TEST_XDOF
 Unknown that will be printed for JACOBIAN_TEST (R in dR/dX).

NO_ACCUMULATION
 Skip accumulation term calculation.

NO_FLUX
 Skip internal flux calculation.

NO_BCFLUX
 Skip boundary flux calculation.

NO_FRACTURE
 Skip fracture.

NO_CREEP_CLOSURE
 Skip creep closure.

NO_GAS_GENERATION
 Skip gas generation.

PRINT_RESIDUAL
 Print the residual to a file *pf_residual.txt* at each Newton iteration.

PRINT_SOLUTION
 Print the solution to a file *pf_solution.txt* at each Newton iteration.

PRINT_UPDATE
 Print the update to a file *pf_update.txt* at each Newton iteration.

DEBUG
 Toggles on increasing verbose output for debugging.

DEBUG_GAS_GENERATION
 Increasingly verbose information for gas generation from pm_wipp_srcsink.

DEBUG_FIRST_ITERATION
 Stops the simulation after the first Newton iteration when debugging is toggled on.
 
DEBUG_OSCILLATORY_BEHAVIOR
 Turns on increasingly verbose information for a cell where the residual is oscilating.

DEBUG_TS_UPDATE
 Prints dtime(1:2) ramping factors used in updating the time step size.

USE_BRAGFLO_CC
 Toggles the use of characteristic curves exactly as coded in BRAGFLO. The code was lifted from BRAGFLO and wrapped for use in PFLOTRAN for debugging purposes.

.. _wipp-flow-timestepper-options:

TIMESTEPPER Options
-------------------

.. include:: timestepper_wipp_flow.tmp

.. _wipp-flow-newton-options:

NEWTON_SOLVER Options
---------------------

.. include:: newton_wipp_flow.tmp

.. _wipp-flow-examples:

Examples
--------
::

 SIMULATION
   ...
   PROCESS_MODELS
     SUBSURFACE_FLOW flow
       MODE WIPP_FLOW
       OPTIONS
         GAS_COMPONENT_FORMULA_WEIGHT 2.01588d0 #hardwired
         2D_FLARED_DIRICHLET_BCS
           EXTERNAL_FILE ../dirichlet_bcs.txt
         /
         ALLOW_NEGATIVE_GAS_PRESSURE
         ALPHA_DATASET alpha
         BRAGFLO_RESIDUAL_UNITS
         DIP_ROTATION_ANGLE 1.d0
         DIP_ROTATION_ORIGIN 23495.7d0 0.d0 378.685d0
         DIP_ROTATION_CEILING 779.69d0
         DIP_ROTATION_BASEMENT 178.07d0
         DIP_ROTATION_REGIONS rSHFTU
       /
     /
   /
 END
 ...
 SUBSURFACE
   NUMERICAL_METHODS FLOW
     TIMESTEPPER
       LIQ_PRES_CHANGE_TS_GOVERNOR 5.d5       ! PRESNORM
       GAS_SAT_CHANGE_TS_GOVERNOR 0.3d0       ! SATNORM
       GAS_SAT_GOV_SWITCH_ABS_TO_REL 1.d0     ! TSWITCH
     /
     NEWTON_SOLVER
       CONVERGENCE_TEST BOTH                  ! ICONVTEST 1
       SCALE_JACOBIAN                         ! LSCALE
       GAS_RESIDUAL_INFINITY_TOL 1.d-2        ! FTOL_PRES
       GAS_SAT_THRESH_FORCE_EXTRA_NI 1.d-3    ! SATLIMIT
       GAS_SAT_THRESH_FORCE_TS_CUT 0.2d0      ! DSATLIM
       LIQUID_RESIDUAL_INFINITY_TOL 1.d-2     ! FTOL_SAT
       MAX_ALLOW_GAS_SAT_CHANGE_TS 1.d0       ! DSAT_MAX
       MAX_ALLOW_LIQ_PRES_CHANGE_TS 1.d7      ! DPRES_MAX
       MAX_ALLOW_REL_GAS_SAT_CHANGE_NI 1.d-3  ! EPS_SAT
       MAX_ALLOW_REL_LIQ_PRES_CHANG_NI 1.d-2  ! EPS_PRES
       MIN_LIQ_PRES_FORCE_TS_CUT -1.d8        ! DPRELIM
       MINIMUM_TIMESTEP_SIZE 8.64d-4          ! DELTMIN
     /
   /
   ...

