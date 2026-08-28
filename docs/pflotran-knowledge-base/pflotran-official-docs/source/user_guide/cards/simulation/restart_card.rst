Back to :ref:`card-index`

.. _restart-card:

RESTART
=======
Specifies restart options so one can continue running a simulation where it left off (e.g. due to system failure, :ref:`WALL_CLOCK_STOP<wallclock-stop-card>` shutdown, or :ref:`FINAL_TIME<final-time-card>`).

Required Cards:
---------------
RESTART
 Opens ths RESTART block.

FILENAME <string>
 Specifies the name of the restart file.

Optional Cards:
---------------
RESET_TO_TIME_ZERO
 Resets the simulation to time zero enabling the user to use state variables defined in a checkpoint file as an initial condition.

REALIZATION_DEPENDENT
 Instructs the code to insert the realization ID (R#) into the restart name. "-restart" must be present in the filename, and the code will insert "R#" prior to "-restart".  E.g. pflotran-restart.h5 -> pflotranR1-restart.h5.

Examples
--------
Restart the program running from where it left off when the file 
``pflotran.chk3000`` was printed:
 
::

  SIMULATION
    SIMULATION_TYPE SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_FLOW flow
        ...
      /
      SUBSURFACE_TRANSPORT transport
        ...
      /
    /
    RESTART 
      FILENAME pflotran.chk3000
    /
  END

Restart the simulation from the end of the previous simulation, but set the 
time back to the initial simulation time (time zero):

::

  SIMULATION
    SIMULATION_TYPE SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_FLOW flow
        ...
      /
      SUBSURFACE_TRANSPORT transport
        ...
      /
    /
    RESTART 
      FILENAME restart.h5
      RESET_TO_TIME_ZERO
    /
  END
    
