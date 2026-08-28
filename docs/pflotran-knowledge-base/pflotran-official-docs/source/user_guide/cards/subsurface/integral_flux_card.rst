Back to :ref:`card-index`

.. _integral-flux-card:

INTEGRAL_FLUX
=============
Sets up a surface through which fluxes of all primary dependent variables can 
be calculated. 

**Note: Be sure to add the PERIODIC_OBSERVATION card to the** 
:ref:`output-card` **card as this toggles on the printing of integral fluxes**
**to a file with the suffix '?-int.dat'.**

Required Cards:
---------------------
INTEGRAL_FLUX <optional string>
 Opens the INTERGAL_FLUX block and provides the name.  
 The name is optional, but if not provided, the name must be specified through 
 the optional NAME card below.

COORDINATES_AND_DIRECTIONS
 Opens a block listing the coordinate (x,y,z) and unit vector (x,y,z) for each face to be summed into the integral flux. The unit vector is in the direction of positive flux.

POLYGON
 Opens a block of coordinates (x,y,z) defining a polygon within which fluxes will be summed.

PLANE
 Opens a block of coordinates (x,y,z) defining a plane along which fluxes will be summed. Only the first three coordinates will be used to define the plane.

VERTICES
 Opens a block listing vertices for each face to be summed into the integral flux. Use right hand rule for positive direction. Only applicable for implicit unstructured (finite element-style) meshes.

CELL_IDS
 Opens a block listing the two cell ids sharing each face to be summed into the integral flux. Positive direction is oriented from the first to the second cell id.

Optional Cards:
--------------------
INVERT_DIRECTION
 Inverts the sign of the flux. For fluxes at upwind boundaries, influx will be negative. This has no impact on the actual flux values other than to flip the sign.

NAME <string>
 Specifies a name that is associated with the integral fluxes in the "?-int.dat" file.  This name will overwrite any name specified with the INTEGRAL_FLUX card 
 that opens the block.
 
FLUXES_OPTION <option>
 Select different way to sum the fluxes.  Options: SIGNED_FLUXES (Default), POSITIVE_FLUXES_ONLY, ABSOLUTE_FLUXES
 
 * SIGNED_FLUXES
   
   Sum every signed fluxes with respect to their orientation (Default).
   
 * POSITIVE_FLUXES_ONLY
   
   Sum only the positive fluxes for each cell according to their orientation. Negative fluxes can be assessed with POSITIVE_FLUXES_ONLY option along with the INVERT_DIRECTION card.
   
 * ABSOLUTE_FLUXES
 
   Sum every absolute value of fluxes though each face, i.e. ignore the orientation. Useful for closed surface.


Examples
--------
 ::

  INTEGRAL_FLUX
    NAME Z3
    POLYGON
      1. 0. 1.
      2. 0. 1.
      2. 2. 1.
      0. 2. 1.
      0. 1. 1.
      1. 1. 1.
    /
  END

  INTEGRAL_FLUX X_at_1
    INVERT_DIRECTION
    PLANE
      1. 0. 0.
      1. 1. 0.
      1. 0. 1.
    /
  END

  INTEGRAL_FLUX
    NAME top_north_east_corner
    COORDINATES_AND_DIRECTIONS
      2. 1.5 1.5 1. 0. 0. 
      1.5 2. 1.5 0. 1. 0. 
      1.5 1.5 2. 0. 0. 1. 
    /
  END

  INTEGRAL_FLUX
    NAME Z_at_0
    VERTICES
      4 5 2 1
      5 6 3 2
      7 8 5 4
      8 9 6 5
    /
  END
  
  INTEGRAL_FLUX
    NAME by_cell_id
    FLUXES_OPTION ABSOLUTE_FLUXES
    CELL_IDS
      1 2
      3 4
    /
  END
      
