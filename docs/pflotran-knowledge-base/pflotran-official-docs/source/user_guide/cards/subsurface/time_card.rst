Back to :ref:`card-index`

.. _time-card:

TIME
====
Specifies the time step sizes and final simulation time.

Required Cards
--------------

.. _final-time-card:

FINAL_TIME <float> <string>
 Specified the final time of the simulation with units.

Optional Cards:
---------------
STEADY_STATE
 Specifies that the simulation run in steady state mode with no time stepping (**Warning: Experimental**)

INITIAL_TIMESTEP_SIZE <float> <string>
 Specifies the initial time step size

MAXIMUM_TIMESTEP_SIZE <float> <string> <optional string> <optional float> <optional string>
 Specifies the maximum time step size.  This maximum time step size can change during the simulation by adding the optional float/strings as follows:
 ::

  MAXIMUM_TIMESTEP_SIZE <float> at <float> <string>  (See examples below)

 *MAXIMUM_TIMESTEP_SIZE may be specified within either the TIME or TIMESTEPPER block, but not both.*

Examples
--------

 ::

  TIME
    # total simulation length, the unit can be in h or y
    FINAL_TIME 5200.0d0 h 
    # initial time step size, it could be reduced or increased automatically 
    # by the program for accuracy purpose 
    INITIAL_TIMESTEP_SIZE 1.d0 h
    # maximum time step that can not be exceeded
    MAXIMUM_TIMESTEP_SIZE 1.d0 h
  END

  # to specify an initial maximum time step size of 1 hour, decrease the 
  # time step size to 0.1 hours between 24 and 34 hours simulation time, 
  # and revert back to the original time step size afterwards
  TIME
    FINAL_TIME 96.0d0 h
    INITIAL_TIMESTEP_SIZE 0.1d0 h
    MAXIMUM_TIMESTEP_SIZE 1.d0 h at 0. h
    MAXIMUM_TIMESTEP_SIZE 0.1d0 h at 24. h
    MAXIMUM_TIMESTEP_SIZE 1.d0 h at 34. h
  END
