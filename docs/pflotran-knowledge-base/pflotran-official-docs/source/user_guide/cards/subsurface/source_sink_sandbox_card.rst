Back to :ref:`card-index`

.. _source-sink-sandbox-card:

SOURCE_SINK_SANDBOX
===================
Specifies parameters for user-defined source/sinks.

Required Cards:
---------------

SOURCE_SINK_SANDBOX
 Opens the source/sink sandbox block.

Optional Cards:
---------------

:ref:`srcsink-sandbox-pressure-card`
 Block for specifying a pressure-based source/sink term where the prescribed
 rate transitions from the maximum rate to zero at the prescribed pressure.

Examples
--------

:: 

  SOURCE_SINK_SANDBOX
    PRESSURE
      CELL_IDS 8 13 18 23
      PHASE LIQUID
      PRESSURE 1.1d6
      SCALE_MAXIMUM_MASS_RATE
      MAXIMUM_MASS_RATE 4.d-4 kg/s
    /
  END

