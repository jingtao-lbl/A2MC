Back to :ref:`card-index`

.. _source-sink-card:

SOURCE_SINK
===========
Specifies coupling between flow and transport conditions and a 
:ref:`region-card` for a source/sink term.

Required Cards:
---------------
SOURCE_SINK <name>
 Indicates the name of the source/sink.

:ref:`flow-condition-card` and/or :ref:`transport-condition-card`:

 :ref:`flow-condition-card` <name>
   Indicates the name of the flow condition.

 :ref:`transport-condition-card` <name>
  Indicates the name of the transport condition.

:ref:`region-card` <name>
 Indicates the name of the region that the set of flow and transport conditions 
 will be applied to.

Examples
--------

 ::

  SOURCE_SINK Well_2-9_1
    FLOW_CONDITION Injection_1
    TRANSPORT_CONDITION Source
    REGION Well_2-9_1
  /
