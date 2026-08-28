Back to :ref:`card-index`

.. _geomechanics-time-card:

GEOMECHANICS_TIME
===================
Card to enter information regarding geomechanics time.


Required Cards:
---------------
COUPLING_TIMESTEP_SIZE <float>
  Specify the timestep size where information between flow and geomechanics should take place

Examples
--------

 ::


    GEOMECHANICS_TIME
      COUPLING_TIMESTEP_SIZE 0.1 s
    END
