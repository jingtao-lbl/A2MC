Back to :ref:`card-index`

.. _boundary-condition-card:

BOUNDARY_CONDITION
==================
This card links a particular :ref:`flow-condition-card` and
:ref:`transport-condition-card` to the appropriate :ref:`region-card` to
define a boundary condition.
It is set up similar to the :ref:`initial-condition-card` card,
by first creating a list of flow and/or transport conditions, and then
applying them to appropriate REGIONs using this card.

Required Cards:
---------------
BOUNDARY_CONDITION <optional string>
 Opens the BOUNDARY_CONDITION block, labeling it with the <optional string>. The label is useful for output purposes (e.g. labeling mass flux across the boundary region in the mass balance [\*-mas.dat] file).

FLOW_CONDITION <string>
 Name of the associated :ref:`flow-condition-card`

TRANSPORT_CONDITION <string>
 Name of the associated :ref:`transport-condition-card`

REGION <string>
 Name of the associated :ref:`region-card`

Examples
--------

::

  BOUNDARY_CONDITION
    FLOW_CONDITION left_face
    REGION left_face
  /

  BOUNDARY_CONDITION recharge
    FLOW_CONDITION recharge
    TRANSPORT_CONDITION tracer_recharge
    REGION Top
  /
