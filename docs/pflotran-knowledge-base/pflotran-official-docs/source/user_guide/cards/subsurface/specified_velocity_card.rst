Back to :ref:`card-index`

.. _specified-velocity-card:

SPECIFIED_VELOCITY
==================
Defines Darcy flow velocities to be used when there is no flow process model employed.

Required Cards:
---------------
UNIFORM? <string>
 Specifies whether Darcy velocities are uniform or not.  [YES,NO]

DATASET <string>
 If uniform, the Darcy velocities can be defined with a list, a file or singlely as demonstrated in the examples below.  If non-uniform, the flow velocities must be defined within an HDF5 file.  This non-uniform capability is expert level.  The user must determine the format by studying init_common.F90::InitCommonReadVelocityField(). For gas transport, one must list six velocity components where the first three are for the liquid phase and the last three are gas (lvx, lvy, lvz, gvx, gvy, gvz).

Optional Cards:
---------------
TIME_UNITS
 Units for time [T].

DATA_UNITS
 Units for Darcy velocity [L/T].

INTERPOLATION <string>
 Type of interpolation [LINEAR, STEP].

Examples
--------
 ::

  SPECIFIED_VELOCITY
    UNIFORM? YES
    DATASET 1.d0 0.d0 0.d0 m/yr
  END

  SPECIFIED_VELOCITY
    UNIFORM? YES
    DATASET LIST
      TIME_UNITS yr
      DATA_UNITS m/yr
      0.d0 1.d0 0.d0 0.d0
    /
  END
  
  ! liquid and gas phase transport
  SPECIFIED_VELOCITY
    UNIFORM? YES
    DATASET LIST
      TIME_UNITS yr
      DATA_UNITS m/yr
      INTERPOLATION STEP
      0.d0  1.d0 0.d0 0.d0 0.d0 0.d0 0.d0
      5.d0 -1.d0 0.d0 0.d0 0.d0 0.d0 0.d0
      15.d0 1.d0 0.d0 0.d0 0.d0 0.d0 0.d0
    /
  END

  SPECIFIED_VELOCITY
    UNIFORM? NO
    DATASET <filename>
  END


