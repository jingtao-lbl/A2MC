Back to :ref:`card-index`

.. _geomechanics-output-card:

GEOMECHANICS_OUTPUT
====================
This keyword is required for output of geomechanics data. The geomechanics data is saved in separate set of files (unlike flow and transport). The filenames of these files have the word -geomech- included in them. Uses the same keywords as OUTPUT.

Examples
--------

 ::

  
  GEOMECHANICS_OUTPUT
    TIMES  s 1.0 2.0 3.0 4.0 5.0 6.0 7.0 8.0 9.0 10.0
    FORMAT TECPLOT POINT
    FORMAT HDF5
  END 
