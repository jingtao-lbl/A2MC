.. _numerical-methods-refactor:

Numerical Methods Refactor
--------------------------
In April 2020, all cards associated with the numerical solution of process model governing equations were centralized within a NUMERICAL_METHODS block within the PFLOTRAN input file. 
The initial implementation applies only to the SUBSURFACE_FLOW (FLOW) and SUBSURFACE_TRANSPORT (TRANSPORT) process models, and the NUMERICAL_METHODS block is to be placed within the SUBSURFACE block in the input file. 
Placement within the process model OPTIONS block within the SIMULATION block was considered, but not chosen in favor of brevity and simplicity within the SIMULATION block.

The new approach involves defining an optional NUMERICAL_METHODS block for FLOW or TRANSPORT with the optional TIMESTEPPER, NEWTON_SOLVER and/or LINEAR_SOLVER blocks placed within. 
The TIMESTEPPER, NEWTON_SOLVER and LINEAR_SOLVER cards no longer require the FLOW or TRANSPORT card appended, as they inherit the process model associated with the outer NUMERICAL_METHODS card. 
All time integration and solver settings that were previously specified within the process model OPTIONS block (within the SIMULATION block) are now placed within their respective block within NUMERICAL_METHODS. 
In general, all parameters altering nonlinear solver convergence criteria (including time step cutting) are placed within the NEWTON_SOLVER block, while parameters affecting time step size (with the exception of time step cutting) are placed within the TIMESTEPPER block.

The below are examples of NUMERICAL_METHODS blocks for FLOW and TRANSPORT.

 ::

  NUMERICAL_METHODS FLOW
    TIMESTEPPER
      INITIAL_TIMESTEP_SIZE 1.d0 h
      MAXIMUM_TIMESTEP_SIZE 1.d0 y
      PRESSURE_CHANGE_GOVERNOR 1.d5
    /
    NEWTON_SOLVER
      ANALYTICAL_JACOBIAN
      ITOL_UPDATE 1.d0
      RTOL 1.d-20
    /
    LINEAR_SOLVER
      SOLVER DIRECT
    /
  END

  NUMERICAL_METHODS TRANSPORT
    TIMESTEPPER
      INITIAL_TIMESTEP_SIZE 1.d0 h
      MAXIMUM_TIMESTEP_SIZE 0.1d0 y
      CFL_GOVERNOR 1.d0

    /
    NEWTON_SOLVER
      ITOL_RELATIVE_UPDATE 1.d-8
      RTOL 1.d-20
    /
    LINEAR_SOLVER
      SOLVER DIRECT
    /
  END

Note several changes in the above:
 * **Time step size criteria can now be specific to each process model.** Although time step size may still be specified through the TIME card, it may not be specified through the (master process model) TIMESTEPPER and TIME cards simultaneously.
 * **All time step size "governors" have been renamed** as follows:

   * MAX_PRESSURE_CHANGE -> PRESSURE_CHANGE_GOVERNOR
   * MAX_SATURATION_CHANGE -> SATURATION_CHANGE_GOVERNOR
   * MAX_TEMPERATURE_CHANGE -> TEMPERATURE_CHANGE_GOVERNOR
   * MAX_CONCENTRATION_CHANGE -> CONCENTRATION_CHANGE_GOVERNOR
   * MAX_VOLUME_FRACTION_CHANGE -> VOLUME_FRACTION_CHANGE_GOVERNOR
   * MAX_CFL -> CFL_GOVERNOR

Several scripts are provided to facilitate migration to the new NUMERICAL_METHODS implementation:
 * PFLOTRAN_DIR/src/python/**refactor_numerical_methods.py**: Recursively searches for input decks and refactors the input decks, placing all TIMESTEPPER, NEWTON_SOLVER, LINEAR_SOLVER and time step / nonlinear solver settings within the process model OPTIONS block within a new NUMERICAL_METHODS block.
   **This script skips input decks with the EXTERNAL_FILE and (linear solver) CPR_OPTIONS cards.**
   ::

    python refactor_numerical_methods.py

 * PFLOTRAN_DIR/src/python/**swap_keyword.py**: Recursively searches for input decks and swaps the first keyword listed on the command line with the second as follows.
   ::

    python swap_keyword.py MAX_PRESSURE_CHANGE PRESSURE_CHANGE_GOVERNOR

Note to Developers
++++++++++++++++++
All process models now have routines for reading process model specific TIMESTEPPER and NEWTON_SOLVER settings. 
These are located in subroutines named *XXXReadTSSelectCase* and *XXXReadNewtonSelectCase* routines that are mapped to the *pm%ReadTSBlock()* and *pm%ReadNewtonBlock()* class methods. 
These read routines are nested, and nesting should be considered when creating new keywords.
For instance, any capability that serves all flow process models should be placed within *pm_subsurface_flow.F90* in order to avoid redundancy in the child flow process models.
