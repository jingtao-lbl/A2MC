Back to :ref:`card-index`

.. _timestepper-card:

TIMESTEPPER
===========
Specifies parameters associated with time integration or time stepping.

Required Cards:
---------------
TIMESTEPPER
 Opens the timestepper block.

Optional Cards:
---------------
*Note: See process model cards for additional TIMESTEPPER cards that are process model specific.*

INITIAL_TIMESTEP_SIZE <float> <string>
 Specifies the initial time step size and time units.

MAXIMUM_CONSECUTIVE_TS_CUTS <int>
 Maximum number of consecutive time step cuts before the simulation is 
 terminated with a plot of the current solution saved to the prescribed 
 OUTPUT format(s).

MAXIMUM_NUMBER_OF_TIMESTEPS <int>
 Maximum time step after which the simulation will be terminated (default: 999999). 

MAXIMUM_TIMESTEP_SIZE <float> <string> <optional string> <optional float> <optional string>
 Specifies the maximum time step size and time units.  This maximum time step size can change during the simulation by adding the optional float/string combination as follows:
 ::

  MAXIMUM_TIMESTEP_SIZE <float> <string> at <float> <string>  (See examples below)

 *MAXIMUM_TIMESTEP_SIZE may be specified within either the TIME or TIMESTEPPER block, but not both.*

MAX_NUM_CONTIGUOUS_REVERTS <int>
 When a time step is cut to synchronize with a waypoint, the previous time
 step size is stored and the time step is set back to the previous value 
 afterwards. This setting ensures that the previous time step size is 
 stored for up to MAX_NUM_CONTIGUOUS_REVERTS times before the previous 
 time step size is discarded.

MINIMUM_TIMESTEP_SIZE <float> <string>
 Specifies the minimum time step size and time units. This minimum step size is used to softly exit the simulation when time step sizes are cut below this threshold. If TS_ACCELERATION, the step size will not drop below this threshold.

NUM_STEPS_AFTER_TS_CUT <int>
 Number of time steps after a time step cut that the time step size must be held constant.  Use 0 to ramp up immediately (default: 5).

TIMESTEP_MAXIMUM_GROWTH_FACTOR <float>
 The maximum factor by which the time step can be increased between time steps (default: 2.).

TIMESTEP_OVERSTEP_REL_TOLERANCE <float>
 If a waypoint lies just beyond the end of a time step, the time step size will be increased to match the waypoint time if (waypoint_time <= time + time_step_size * TIMESTEP_OVERSTEP_REL_TOLERANCE). This helps avoid small time steps when synchronizing with waypoints.

TIMESTEP_REDUCTION_FACTOR <float>
 The factor by which the time step will be reduced when it is cut (default: 0.5).

Expert Level
++++++++++++
DT_FACTOR <float array>
 An array of floating point numbers specifying time step growth multipliers 
 as a function of number of Newton iterations in
 consecutive order from 1 Newton iteration to TS_ACCELERATION Newton iterations.

TS_ACCELERATION <int>
 Integer indexing time step acceleration ramp. Use in 
 conjunction with DT_FACTOR (default: 5).

Examples
--------
 ::

  TIMESTEPPER
    TS_ACCELERATION 8
    MAXIMUM_NUMBER_OF_TIMESTEPS 10000 ! terminates simulation after 10,000 time steps
    MAX_TS_CUTS 5                     ! terminates simulation after 5 consecutive time step cuts
  END

  TIMESTEPPER
    TIMESTEP_MAXIMUM_GROWTH_FACTOR 1.250000
    MAXIMUM_CONSECUTIVE_TS_CUTS 30
    TS_ACCELERATION 10
    DT_FACTOR 1.25 1.25 1.25 1.1 1.0 1.0 0.8 0.6 0.4 0.33
  END

  TIMESTEPPER
    INITIAL_TIMESTEP_SIZE 0.1d0 h
    MAXIMUM_TIMESTEP_SIZE 1.d0 h at 0. h
    MAXIMUM_TIMESTEP_SIZE 0.1d0 h at 24. h
    MAXIMUM_TIMESTEP_SIZE 1.d0 h at 34. h
  END
