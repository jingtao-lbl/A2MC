Back to :ref:`card-index`

.. _initial-condition-card:

INITIAL_CONDITION
=================
This card links a particular :ref:`flow-condition-card` and 
:ref:`transport-condition-card` to the appropriate :ref:`region-card` to
define an initial condition. 
It is set up similar to the :ref:`boundary-condition-card` card, 
by first creating a list of flow and/or transport conditions, and then 
appling them to appropriate REGIONs using this card.

Required Cards:
---------------
INITIAL_CONDITION <optional string>
 Opens the INITIAL_CONDITION block, labeling it with the <optional string>

FLOW_CONDITION <string>
 Name of the associated :ref:`flow-condition-card`

TRANSPORT_CONDITION <string>
 Name of the associated :ref:`transport-condition-card`
  
REGION <string>
 Name of the associated :ref:`region-card`

Examples
--------

 ::

  INITIAL_CONDITION
    FLOW_CONDITION Piezometric_Surface
    TRANSPORT_CONDITION U_source
    REGION all
  /
  
  INITIAL_CONDITION
    FLOW_CONDITION initial
    REGION left_region
  /
  
  INITIAL_CONDITION soilA_layer_initial
    TRANSPORT_CONDITION initial
    REGION soilA_layer
  /
