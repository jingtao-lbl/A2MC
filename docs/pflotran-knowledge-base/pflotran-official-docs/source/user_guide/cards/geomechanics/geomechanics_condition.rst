Back to :ref:`card-index`

.. _geomechanics-condition-card:

GEOMECHANICS_CONDITION
======================
Condition coupler between regions and geomechanics boundary conditions. Since the geomechanics is solved in a quasi-steady manner, initial conditions are not needed. Displacement or force conditions can be specified. Note that the values specified for displacement or force conditions will be applied to all the nodes of the region that the condition is coupled to. If one wants to specify a force F on on a face, then the F needs to be distributed based on the area around each node on that face. For example, if the top face has nodes configuration as follows:

1–2–3

l l l

4–5–6

l l l

7–8–9

with x and y in the horizontal and vertical direction, and if a force F on the entire face is applied in the negative z direction, assuming equal spacing in x and y directions, the load distribution will be:

Nodes 1,7,9,3 will get F/16.
Nodes 4,2,6,8 will get F/8.
Node 5 will get F/4.

One will then have to specify three separate regions (one with internal nodes, one with corners and one with boundary nodes that are not corners), and then specify three FORCE_Z boundary conditions.

Sets flow parameters used in setting up flow boundary and initial conditions 
and source/sinks.

Required Cards:
---------------
GEOMECHANICS_CONDITION <string>
 Opens the GEOMECHANICS_CONDITION block, where <string> is the assigned name of the 
 geomechanics condition so that it can be referred to in cards 
 :ref:`geomechanics-boundary-condition-card`

TYPE
 Opens the TYPE sub-block. Within this sub-block, the type of the geomechanics 
 condition is specified. Options for TYPE are 
  
 TYPE [DISPLACEMENT_X {DIRICHLET}, 
      DISPLACEMENT_Y {DIRICHLET}, 
      DISPLACEMENT_Z {DIRICHLET}, 
      FORCE_X {DIRICHLET}, 
      FORCE_Y {DIRICHLET}, 
      FORCE_Z {DIRICHLET}]
   
For each TYPE option specified in the TYPE sub-block described above, a
corresponding type-value card must be included that specifies the
value of the TYPE. The possible type-value cards include:

DISPLACEMENT_X <float>
 The displacement [m] in the x-direction applied at a geomechanics vertex on the boundary.

DISPLACEMENT_Y <float>
 The displacement [m] in the y-direction applied at a geomechanics vertex on the boundary.

DISPLACEMENT_Z <float>
 The displacement [m] in the z-direction applied at a geomechanics vertex on the boundary.

FORCE_X <float>
 The force [N] in the x-direction applied at a geomechanics vertex on the boundary.

FORCE_Y <float>
 The force [N] in the y-direction applied at a geomechanics vertex on the boundary.

FORCE_Z <float>
 The force [N] in the z-direction applied at a geomechanics vertex on the boundary.

Examples
--------

 ::


  GEOMECHANICS_CONDITION west_geomech
    TYPE
      DISPLACEMENT_X DIRICHLET
    END
      DISPLACEMENT_X 0.0
  END

  GEOMECHANICS_CONDITION east_geomech
    TYPE
      DISPLACEMENT_X DIRICHLET
    END
      DISPLACEMENT_X 0.0
  END

  GEOMECHANICS_CONDITION north_geomech
    TYPE
      DISPLACEMENT_Y DIRICHLET
    END
      DISPLACEMENT_Y 0.0
  END

  GEOMECHANICS_CONDITION bottom_geomech
    TYPE
      DISPLACEMENT_Z DIRICHLET
    END
      DISPLACEMENT_Z 0.0
  END

  GEOMECHANICS_CONDITION south_geomech
    TYPE
      DISPLACEMENT_Y DIRICHLET
    END
      DISPLACEMENT_Y 0.0
  END

  GEOMECHANICS_CONDITION top_corner_force
    TYPE
      FORCE_Z DIRICHLET
    END
      FORCE_Z -68832.8125
  END

  GEOMECHANICS_CONDITION top_boundary_force
    TYPE
      FORCE_Z DIRICHLET
    END
      FORCE_Z -137665.625
  END

  GEOMECHANICS_CONDITION top_internal_force
    TYPE
      FORCE_Z DIRICHLET
    END
      FORCE_Z -275331.25
  END



