Back to :ref:`card-index`

.. _geomechanics-boundary-condition-card:

GEOMECHANICS_BOUNDARY_CONDITION
===============================
The GEOMECHANICS_BOUNDARY_CONDITION keyword couples condition specified under the GEOMECHANICS_CONDITION keyword to a REGION in the problem domain. The use of this keyword enables the use/reuse of geomechanics conditions and regions within multiple geomechanics boundary conditions the input deck.

Required Cards:
---------------
GEOMECHANICS_BOUNDARY_CONDITION <string>
 Opens the GEOMECHANICS_BOUNDARY CONDITION block, where <string> is the assigned name of the 
 geomechanics boundary condition 

GEOMECHANICS_CONDITION <string>
  Defines the name of the geomechanics condition to be linked to this geomechanics
  boundary condition

GEOMECHANICS_REGION <string>
  Defines the name of the region to which the condition is linked.

Examples
--------

 ::


  GEOMECHANICS_BOUNDARY_CONDITION bottom_geomech
    GEOMECHANICS_CONDITION bottom_geomech
    GEOMECHANICS_REGION bottom
  END

