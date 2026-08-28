Back to :ref:`card-index`

.. _rank-three:

Rank Three Array Specification
==============================
A rank three array constitutes a dataset with three values per time.  
Time must be specified in units and the scalar quantity must be in the units 
of the outer keyword. If TIME_UNITS and/or DATA_UNITS are not specified, SI 
is assumed.

Optional Cards
--------------
*Optional cards must be placed at top of array.*

CYCLIC
 Cycles a transient data set back to initial value when maximum data set time
 is exceeded, repeatedly cycling through the data.

DATA_UNITS <string> [...,<string>]
 Units for the data values listed in the array. The user may define a single unit applied to all data values or three units, one for each data column.

INTERPOLATION <string>
 Interpolation scheme used to calculate transient update, where the options
 for <string> include: [LINEAR, STEP (default)].

TIME_UNITS <string>
 Units for the times listed in the array.

Example
-------
 ::

  # Specifies a transient gradient (dz_dx dz_dy dz_dz).
  TIME_UNITS hr
  # <time> <value> <value> <value>
  0.   4.56201E-05   2.50048E-05  0
  1.   4.6121E-05    2.97169E-05  0
  2.   5.55565E-05   3.14973E-05  0
  3.   6.97382E-05   3.06611E-05  0
  4.   8.53995E-05   2.8501E-05   0
  5.   9.94357E-05   2.49889E-05  0
  6.   0.00010842    2.09844E-05  0
  7.   0.000107846   1.68592E-05  0
  8.   9.43216E-05   1.7522E-05   0
  9.   7.70243E-05   1.76242E-05  0
  10.  5.28262E-05   2.02786E-05  0


  # Specifies a transient datum.
  TIME_UNITS hr
  DATA_UNITS m
  # <time> <value> <value> <value>
  0    89.0467313   42.92071714   104.7889681
  1    89.0467313   42.92071714   104.788535
  2    89.0467313   42.92071714   104.7902681
  3    89.0467313   42.92071714   104.7931686
  4    89.0467313   42.92071714   104.796484

  # Specifies multiple data units.
  TIME_UNITS hr
  DATA_UNITS m m m
  # <time> <value> <value> <value>
  0    89.0467313   42.92071714   104.7889681
  1    89.0467313   42.92071714   104.788535
  2    89.0467313   42.92071714   104.7902681
