Back to :ref:`card-index`

Back to :ref:`subsurface-flow-card`

Back to :ref:`subsurface-flow-mode-card`

.. _well-model-card:

WELL_MODEL
==========
Defines options for the Well Model.

:ref:`well-simulation-options`

:ref:`wellbore-options`

:ref:`well-model-output-options`

:ref:`well-coupler`

:ref:`well-examples`

.. _well-simulation-options:

SIMULATION Options
~~~~~~~~~~~~~~~~~~~
*(under SUBSURFACE_FLOW in SIMULATION PROCESS_MODELS block)*

FLOW_COUPLING
 Options:
  FULLY_IMPLICIT
    Well model is embedded in the flow Jacobian/residual and fully implicitly coupled.
  QUASI_IMPLICIT
    Well model is run during the source/sink calculation for the flow mode, but
    well primary variables are not solved fully implicitly with the flow mode.
  SEQUENTIAL
    Well model is run after flow, as a child process model.

TYPE
 Options:
  HYDROSTATIC
    Well model solves for bottom-hole pressure as a primary variable, and all well
    segment pressures are computed directly from the bottom-hole pressure through
    a hydrostatic calculation.
  WIPP_DARCY
    Darcy flow is solved throughout the well.


.. _wellbore-options:

WELLBORE_MODEL
~~~~~~~~~~~~~~~~~~~
*(within SUBSURFACE block)*

Required Cards:
---------------
WELLBORE_MODEL <name>
 Specifies the name of the wellbore model and opens the block.

WELL_GRID
 Opens the well grid card. The following is a list of all possible
 options to specify the well grid. Not all are necessary.

  MATCH_RESERVOIR
    Match well segment centers with reservoir cell centers. Can be
    used instead of NUMBER_OF_SEGMENTS

  NUMBER_OF_SEGMENTS
    Number of well segments. Used in conjunction with TOP_OF_HOLE
    and BOTTOM_OF_HOLE to draw a vertical wellbore.

  TOP_OF_HOLE <float> <float> <float>
    <x,y,z> coordinate of the top of the well

  BOTTOM_OF_HOLE <float> <float> <float>
    <x,y,z> coordinate of the bottom of the well

  CASING <float>
    0 = uncased, 1 = cased

  WELL_TRAJECTORY
    Opens the WELL_TRAJECTORY block. This can be used instead of the
    combination <NUMBER_OF_SEGMENTS, TOP_OF_HOLE, BOTTOM_OF_HOLE>
    to model a flexible well trajectory. Keywords within the
    WELL_TRAJECTORY block are read sequentially: sequence matters.
    Currently, the method used to draw a flexible well trajectory
    is slow for large problems. A better algorithm is in development.

    SURFACE_ORIGIN <float> <float> <float>
      <x,y,z> coordinate of the top of the well. This keyword must
      come first in the WELL_TRAJECTORY block. After SURFACE_ORIGIN,
      an arbitrary number of the following keywords can be read.

    SEGMENT_DXYZ <CASED/UNCASED> <float> <float> <float>
      When constructing the well, the <dx,dy,dz> of the line segment
      along which to move from the current location. By default,
      negative is downward in the vertical dimension. For example, if
      this comes after the SURFACE_ORIGIN keyword, the well will
      extend <dx,dy,dz> from the SURFACE_ORIGIN. Keyword CASED or
      UNCASED is required.

    SEGMENT_RADIUS_TO_HORIZONTAL_X <CASED/UNCASED> <float>
      Radius (m) with which to kick off to horizontal from the
      current location to horizontal in the x-direction. For example,
      if this comes after the SEGMENT_DXYZ keyword, the well
      will curve to horizontal starting where SEGMENT_DXYZ ended.

    SEGMENT_RADIUS_TO_HORIZONTAL_X <CASED/UNCASED> <float>
      Radius (m) with which to kick off to horizontal from the
      current location to horizontal in the y-direction. For example,
      if this comes after the SEGMENT_DXYZ keyword, the well
      will curve to horizontal starting where SEGMENT_DXYZ ended.

    SEGMENT_RADIUS_TO_HORIZONTAL_ANGLE <CASED/UNCASED> <float> <float>
      Radius (m) with which to kick off to horizontal from the
      current location to horizontal at an angle between the
      x- and y-axes. For example, if this comes after the SEGMENT_DXYZ
      keyword, the well will curve to horizontal starting where
      SEGMENT_DXYZ ended.

  WELL
    Opens the WELL block, to specify properties of the well itself.

    DIAMETER <float>
      well diameter

    FRICTION_COEFFICIENT <float>
      A friction coefficient of 1.0 adds no friction effects to
      wellbore fluxes.

    SKIN <float>
      A skin factor of 0 adds no skin effects to the well fluxes.

    WELL_INDEX_MODEL <keyword string>
      PEACEMAN_ISO
        A traditional Peaceman equation, most applicable for modeling
        one horizontal dimension.
      PEACEMAN_2D
        A 2D extension of the Peaceman equation, most applicable for a
        vertical wellbore in a 3D structured domain.
      PEACEMAN_3D
        A 3D generalized Peaceman relationship for a well of arbitrary
        orientation in a 3D grid.

  WELL_BOUNDARY_CONDITIONS
    Opens the WELL_BOUNDARY_CONDITIONS block, for directly specifying
    well conditions. This is an expert feature. For most users, it is
    recommended to use the USE_WELL_COUPLER keyword instead.

  USE_WELL_COUPLER
    Links the well model to a WELL_COUPLER.

.. _well-coupler:

WELL_COUPLER
~~~~~~~~~~~~~~~~~~~
*(within SUBSURFACE block)*

This card links a particular :ref:`flow-condition-card` and
:ref:`transport-condition-card` to the appropriate :ref:`well` to
define a well coupler.
It is set up similar to the :ref:`initial-condition-card` card,
by first creating a list of flow and/or transport conditions, and then
applying them to appropriate WELLs using this card.

Required Cards:
---------------
WELL_COUPLER <optional string>
 Opens the WELL_COUPLER block, labeling it with the <optional string>. The label is useful for output purposes.

FLOW_CONDITION <string>
 Name of the associated :ref:`flow-condition-card`

TRANSPORT_CONDITION <string>
 Name of the associated :ref:`transport-condition-card`

WELL <string>
 Name of the associated :ref:`well`

Examples
--------

::

  WELL_COUPLER well1
    FLOW_CONDITION injection_well_1
    WELL well1
  /

  WELL_COUPLER well
    FLOW_CONDITION Injection
    TRANSPORT_CONDITION background
    WELL well1
  /

.. _well-model-output-options:

WELL_MODEL_OUTPUT
~~~~~~~~~~~~~~~~~~~
*(within SUBSURFACE block)*
Opens a block to insert certain well model information into the output
files for the flow mode.

  WELL_LIQ_PRESSURE
    Liquid (aqueous) pressure in the well
  WELL_GAS_PRESSURE
    Gas pressure in the well
  WELL_LIQ_Q
    Liquid flow rate at each segment in the well. Negative is out of the
    well (into the reservoir).
  WELL_GAS_Q
    Gas flow rate at each segment in the well. Negative is out of the
    well (into the reservoir).


.. _well-examples:

Examples
--------
::

  SIMULATION
   SIMULATION_TYPE SUBSURFACE
   PROCESS_MODELS
     SUBSURFACE_FLOW flow
      MODE SCO2
     END
     WELL_MODEL well
      OPTIONS
        FLOW_COUPLING FULLY_IMPLICIT
        TYPE HYDROSTATIC
      END
    END
   END
  END
  ...
  WELLBORE_MODEL well1

   WELL_GRID
    NUMBER_OF_SEGMENTS 4
     WELL_TRAJECTORY
      # Must start from SURFACE_ORIGIN and proceed sequentially.
      # Will populate 1 well segment per reservoir cell occupied
      # Must specify if each segment is CASED or UNCASED
      SURFACE_ORIGIN 15.d0 5.d0 2.d2
      SEGMENT_DXYZ CASED 0.d0 0.d0 -149.d0
      SEGMENT_DXYZ UNCASED 0.d0 0.d0 -51.d0
    /
    /

    WELL
      DIAMETER 0.16d0
      FRICTION_COEFFICIENT 1.d0
      SKIN_FACTOR 0.d0
      WELL_INDEX_MODEL PEACEMAN_3D
    /

    USE_WELL_COUPLER

  END

  WELLBORE_MODEL well2

    WELL_GRID
      NUMBER_OF_SEGMENTS 4
      WELL_TRAJECTORY
        # Must start from SURFACE_ORIGIN and proceed sequentially.
        # Will populate 1 well segment per reservoir cell occupied
        # Must specify if each segment is CASED or UNCASED
        SURFACE_ORIGIN 35.d0 5.d0 2.d2
        SEGMENT_DXYZ CASED 0.d0 0.d0 -149.d0
        SEGMENT_DXYZ UNCASED 0.d0 0.d0 -51.d0
      /
    /

    WELL
      DIAMETER 0.16d0
      FRICTION_COEFFICIENT 1.d0
      SKIN_FACTOR 0.d0
      WELL_INDEX_MODEL PEACEMAN_3D
    /

    USE_WELL_COUPLER

  END
   ...
  WELL_COUPLER well1
    FLOW_CONDITION injection_well_1
    WELL well1
  END

  WELL_COUPLER well2
    FLOW_CONDITION injection_well_2
    WELL well2
  END
  ...
