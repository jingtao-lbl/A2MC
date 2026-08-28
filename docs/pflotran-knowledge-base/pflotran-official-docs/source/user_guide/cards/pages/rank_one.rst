Back to :ref:`card-index`

.. _rank-one:

Rank One Array Specification
============================
A *rank one* array constitutes a dataset with a single value per time.  
Time must be specified in units and the scalar quantity must be in the units 
of the outer keyword.  If TIME_UNITS and/or DATA_UNITS are not specified, SI 
is assumed. 

Optional Cards
--------------
*Optional cards must be placed at top of array.*

CYCLIC
 Cycles a transient data set back to initial value when maximum data set time
 is exceeded, repeatedly cycling through the data.

DATA_UNITS <string>
 Units for the data values listed in the array.

INTERPOLATION <string>
 Interpolation scheme used to calculate transient update, where the options
 for <string> include: [LINEAR, STEP (default)].

TIME_UNITS <string>
 Units for the times listed in the array.


Examples
--------
 ::

  ! Rank 1 Dataset: turns on a 1 cm/yr flux over the second year of a three year simulation.
  TIME_UNITS yr
  DATA_UNITS cm/yr
  ! <time> <value>
  0. 0.
  2. 1. 
  3. 0.
 
