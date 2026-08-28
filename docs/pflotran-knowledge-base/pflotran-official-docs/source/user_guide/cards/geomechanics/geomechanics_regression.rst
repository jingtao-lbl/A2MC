Back to :ref:`card-index`

.. _geomechanics-regression-card:

GEOMECHANICS_REGRESSION
=======================
Dumps a regression file with data at selected vertices. This can then be used for comparing with a gold file for performing regression tests.

Required Cards:
---------------
VERTICES
 List of vertices where the regression is to be performed.

Option Cards:
-------------
VARIABLES
 Provide a list of variables that will be dumped in the regression output.

Examples
--------


 ::


    GEOMECHANICS_REGRESSION
      VARIABLES
        DISPLACEMENT_Z
        STRAIN_ZZ
        STRESS_ZZ
      /
      VERTICES
        5
        14
        23
        32
        41
        50
        59
        68
        77
        86
        95
        104
      /
    END
