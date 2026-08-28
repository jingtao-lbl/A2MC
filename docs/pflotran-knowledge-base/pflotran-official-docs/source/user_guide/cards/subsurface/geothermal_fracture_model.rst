Back to :ref:`card-index`

.. _geothermal-fracture-model-card:

GEOTHERMAL_FRACTURE_MODEL
=========================
Defines paramters and controls the creation of individual fractures or 
statistical fracture families for thermo-hydro-mechanical-chemical simulations
of flow through an equivalent continuous porous media representation of
discrete fracture networks. 
Note: only :ref:`th-card` Mode is fully tested as a
compatible flow mode, although this process model may also work with 
:ref:`general-card` Mode (use at your own risk with General Mode).

Required Cards:
---------------
GEOTHERMAL_FRACTURE_MODEL
 Opens the geothermal fracture model block. Must be closed with `END` or a 
 forward slash (/).
 
THERMAL_EXPANSION_COEFFICIENT <float>
 Specifies the thermal expansion coefficient [C\ :sup:`-1`\] for the matrix
 rock material. A value typical for granite is 40.6d-6 C\ :sup:`-1`\, 
 however, no default value is provided so this parameter must be specified. This 
 parameter contributes to the calculation of the hydraulic aperture evolution 
 and the resulting changes in fracture permeability.

FRACTURE_INTERSECTION_PERM <string>
 Specifies how the permeability is treated at the intersection of one or more 
 fractures. The options are: `MAXIMUM` (or `MAX`), `SUMMATION` (or `SUM`). If
 `MAXIMUM` is chosen, the maximum permeability of the individual intersecting 
 fractures is assigned at the fracture intersection. If `SUMMATION` is chosen, 
 the sum of the individual intersecting fractures is assigned at the fracture 
 intersection. 
 
FRACTURE
 Opens a FRACTURE block, which defines parameters and controls for individual 
 fractures in the domain. Must be closed with `END` or a forward slash (/).
 
 ID <integer>
  Specifies an identification number for the fracture. 
 
 HYDRAULIC_APERTURE <float>
  Specifies the hydraulic aperture [m] of a fracture. This value is used to 
  calculate the initial permeability, unperturbed by geochemistry or thermal 
  expansion/contraction of the matrix rock. 
 
 CENTER <float> <float> <float> 
  Specifies the x, y, and z coordinates [m] in space for where the center of the 
  fracture plane is located within the domain. 
 
 NORMAL_VECTOR <float> <float> <float> 
  Specifies the x, y, and z components [m] of the vector that is orthogonal, or 
  normal, to the fracture plane. This vector does not need to be a unit vector.
 
 RADIUS_X <float>
  Specifies the maximum extent [m] of the fracture in the x-axis of the domain 
  from the center of the fracture plane. While this is not a true radius, in 
  the traditional definition of a radius, one can think of it in the sense of a 
  radius for a cuboid shape.
 
 RADIUS_Y <float>
  Specifies the maximum extent [m] of the fracture in the y-axis of the domain 
  from the center of the fracture plane. While this is not a true radius, in 
  the traditional definition of a radius, one can think of it in the sense of a 
  radius for a cuboid shape.
 
 RADIUS_Z <float>
  Specifies the maximum extent [m] of the fracture in the z-axis of the domain 
  from the center of the fracture plane. While this is not a true radius, in 
  the traditional definition of a radius, one can think of it in the sense of a 
  radius for a cuboid shape.


FRACTURE_FAMILY
 Opens a FRACTURE_FAMILY block, which defines parameters and controls for 
 fracture families that are defined by statistical distributions. Must be 
 closed with `END` or a forward slash (/).
 Currently, the only type of distribution available is a normal Gaussian or a 
 truncated normal Guassian distribution which is defined by a mean value and a
 standard deviation. If truncated, a value for the minimum or maximum value may
 also be provided.
  
 ID <integer>
  Specifies an identification number for the fracture family.
  
 NUMBER_OF_FRACTURES <integer>
  Specifies the total number of individual fractures that are created for the 
  fracture family.
  
 HYDRAULIC_APERTURE
  Opens a HYDRAULIC_APERTURE sub-block, which defines the statistical parameters 
  for the fracture family's hydraulic aperture. Must be closed with `END` or a 
  forward slash (/).
  
  HYDRAULIC_APERTURE_VALUE <float>
   Specifies the mean hydraulic aperture value [m] for the normal Gaussian 
   distribution that is sampled from when generating the fracture family.
  
  HYDRAULIC_APERTURE_STDEV <float>
   Specifies the standard deviation of the hydraulic aperture value [m] for the 
   normal Gaussian distribution that is sampled from when generating an 
   individual fracture's hydraulic aperture in the fracture family.
  
  HYDRAULIC_APERTURE_SEED <integer>
   Specifies the seed which is used to sample randomly from the normal Gaussian 
   distribution when generating the hydraulic aperture for an individual 
   fracture within a fracture family. If you do not like the 
   discrete fracture network that was generated for a certain seed value, you 
   can simply change the seed value in the input deck and generate a new 
   fracture network. Specifying the same seed will ensure that the same fracture 
   network is generated each time the input deck is run.
  
  HYDRAULIC_APERTURE_MAX <float>
   Specifies the maximum value for the hydraulic aperture [m] in a normal 
   Gaussian distribution, therefore making the distribution truncated.
   
 CENTER
  Opens a CENTER sub-block, which defines the statistical parameters 
  for the fracture family's center in space. Must be closed with `END` or a 
  forward slash (/).
  
  COORDINATE <float> <float> <float>
   Specifies the x, y, and z coordinates [m] in space for where the mean center 
   of the fracture family's fracture plane is located within the domain.
  
  XCOORD_STDEV <float>
   Specifies the standard deviation of the x coordinate value [m] for the 
   normal Gaussian distribution that is sampled from when generating an 
   individual fracture's x-coordinate in the fracture family.
   
  YCOORD_STDEV <float>
   Specifies the standard deviation of the y coordinate value [m] for the 
   normal Gaussian distribution that is sampled from when generating an 
   individual fracture's y-coordinate in the fracture family.
   
  ZCOORD_STDEV <float>
   Specifies the standard deviation of the z coordinate value [m] for the 
   normal Gaussian distribution that is sampled from when generating an 
   individual fracture's z-coordinate in the fracture family.
  
  CENTER_SEED <integer>
   Specifies the seed which is used to sample randomly from the normal Gaussian 
   distribution when generating the center x, y, or z coordinate for an 
   individual fracture within a fracture family. If you do not like the 
   discrete fracture network that was generated for a certain seed value, you 
   can simply change the seed value in the input deck and generate a new 
   fracture network. Specifying the same seed will ensure that the same fracture 
   network is generated each time the input deck is run.
   
 NORMAL_VECTOR
  Opens a NORMAL_VECTOR sub-block, which defines the statistical parameters 
  for the fracture family's orientation in space. Must be closed with `END` or a 
  forward slash (/).
  
  VECTOR_COORDINATES <float> <float> <float>
   Specifies the x, y, and z vector coordinates [m] in space for the vector that 
   is orthogonal (or normal) to the fracture family's mean fracture plane. 
  
  XCOORD_STDEV <float>
   Specifies the standard deviation of the x coordinate value [m] for the 
   normal Gaussian distribution that is sampled from when generating an 
   individual fracture's x-component of the normal vector in the fracture 
   family.
   
  YCOORD_STDEV <float>
   Specifies the standard deviation of the y coordinate value [m] for the 
   normal Gaussian distribution that is sampled from when generating an 
   individual fracture's y-component of the normal vector in the fracture 
   family.
   
  ZCOORD_STDEV <float>
   Specifies the standard deviation of the z coordinate value [m] for the 
   normal Gaussian distribution that is sampled from when generating an 
   individual fracture's z-component of the normal vector in the fracture 
   family.
  
  NORMAL_SEED <integer>
   Specifies the seed which is used to sample randomly from the normal Gaussian 
   distribution when generating the normal vector x, y, or z components for an 
   individual fracture within a fracture family. If you do not like the 
   discrete fracture network that was generated for a certain seed value, you 
   can simply change the seed value in the input deck and generate a new 
   fracture network. Specifying the same seed will ensure that the same fracture 
   network is generated each time the input deck is run.
   
 RADIUS
  Opens a RADIUS sub-block, which defines the statistical parameters 
  for the fracture family's extent in space. Must be closed with `END` or a 
  forward slash (/).
  
  RADIUS_XYZ <float> <float> <float>
   Specifies the mean x, y, and z lengths [m] in space for the distance from 
   the mean fracture family center to the end of the fracture plane, in the x, 
   y, and z directions in reference to the coordinate system of the domain. 
  
  RAD_X_STDEV <float>
   Specifies the standard deviation of the mean length in the x direction 
   [m] from the mean fracture family center to the end of the fracture plane in 
   reference to the coordinate system of the domain in the normal Gaussian 
   distribution that is sampled from.
   
  RAD_Y_STDEV <float>
   Specifies the standard deviation of the mean length in the y direction 
   [m] from the mean fracture family center to the end of the fracture plane in 
   reference to the coordinate system of the domain in the normal Gaussian 
   distribution that is sampled from.
   
  RAD_Z_STDEV <float>
   Specifies the standard deviation of the mean length in the z direction 
   [m] from the mean fracture family center to the end of the fracture plane in 
   reference to the coordinate system of the domain in the normal Gaussian 
   distribution that is sampled from.
  
  RADIUS_SEED <integer>
   Specifies the seed which is used to sample randomly from the normal Gaussian 
   distribution when generating the length in the x, y, or z radius directions 
   for an individual fracture within a fracture family. If you do not like the 
   discrete fracture network that was generated for a certain seed value, you 
   can simply change the seed value in the input deck and generate a new 
   fracture network. Specifying the same seed will ensure that the same fracture 
   network is generated each time the input deck is run.


Examples
--------
 ::

  GEOTHERMAL_FRACTURE_MODEL
    
    THERMAL_EXPANSION_COEFFICIENT 40.d-6 # [1/C]
    FRACTURE_INTERSECTION_PERM MAXIMUM

    FRACTURE_FAMILY
      ID 1
      NUMBER_OF_FRACTURES 10  # [-]
      HYDRAULIC_APERTURE
        HYDRAULIC_APERTURE_VALUE 5.d-4  # [m]
        HYDRAULIC_APERTURE_STDEV 3.d-4 # [m]
        HYDRAULIC_APERTURE_SEED 105  # [-] must be an integer
        HYDRAULIC_APERTURE_MAX 1.d-2  # [m]
      /
      CENTER 
        COORDINATE 25.d0 0.5d0 15.d0  # [m]
        XCOORD_STDEV 15.5d0  # [m]
        YCOORD_STDEV 1.5d0  # [m]
        ZCOORD_STDEV 1.5d0  # [m]
        CENTER_SEED 19  # [-] must be an integer
      /
      NORMAL_VECTOR 
        VECTOR_COORDINATES -1.0d0 0.d0 -1.d0 # [m]
        XCOORD_STDEV 0.5d0  # [m]
        YCOORD_STDEV 0d0  # [m]
        ZCOORD_STDEV 0.5d0  # [m]
        NORMAL_SEED 29  # [-] must be an integer
      /
      RADIUS 
        RADIUS_XYZ 50.d0 50.d0 100.d0 # [m]
        RAD_X_STDEV 50.0d0  # [m]
        RAD_Y_STDEV 10.0d0  # [m]
        RAD_Z_STDEV 5.0d0  # [m]
        RADIUS_SEED 31  # [-] must be an integer
      /
    /

    FRACTURE_FAMILY
      ID 2
      NUMBER_OF_FRACTURES 6  # [-]
      HYDRAULIC_APERTURE
        HYDRAULIC_APERTURE_VALUE 5.d-3  # [m]
        HYDRAULIC_APERTURE_STDEV 2.d-3 # [m]
        HYDRAULIC_APERTURE_SEED 10  # [-] must be an integer
        HYDRAULIC_APERTURE_MAX 1.d-2  # [m]
      /
      CENTER 
        COORDINATE 25.d0 0.5d0 15.d0  # [m]
        XCOORD_STDEV 8.5d0  # [m]
        YCOORD_STDEV 1.5d0  # [m]
        ZCOORD_STDEV 1.5d0  # [m]
        CENTER_SEED 66  # [-] must be an integer
      /
      NORMAL_VECTOR 
        VECTOR_COORDINATES -1.0d0 0.d0 1.d0 # [m]
        XCOORD_STDEV 0.1d0  # [m]
        YCOORD_STDEV 0.0d0  # [m]
        ZCOORD_STDEV 0.3d0  # [m]
        NORMAL_SEED 7  # [-] must be an integer
      /
      RADIUS 
        RADIUS_XYZ 50.d0 50.d0 5.d0 # [m]
        RAD_X_STDEV 10.0d0  # [m]
        RAD_Y_STDEV 10.0d0  # [m]
        RAD_Z_STDEV 3.0d0  # [m]
        RADIUS_SEED 5  # [-] must be an integer
      /
    /
    
    FRACTURE
      ID 1
      HYDRAULIC_APERTURE 1.d-3 # [m]
      CENTER 25.d0 0.5d0 10.0d0 # [m]
      NORMAL_VECTOR -0.15d0 0.d0 1.d0 # [m]
      RADIUS_X 20.d0 # [m]
      RADIUS_Y 100.d0 # [m]
      RADIUS_Z 100.d0 # [m]
    /

    FRACTURE
      ID 3
      HYDRAULIC_APERTURE 1.d-3 # [m]
      CENTER 25.d0 0.5d0 12.5d0 # [m]
      NORMAL_VECTOR -0.15d0 0.d0 1.d0 # [m]
      RADIUS_X 20.d0 # [m]
      RADIUS_Y 100.d0 # [m]
      RADIUS_Z 100.d0 # [m]
      MAX_DISTANCE 0.1 # [m]
    /
    FRACTURE
      ID 2
      HYDRAULIC_APERTURE 6.d-4 # [m]
      CENTER 25.5d0 0.5d0 11.0d0 # [m]
      NORMAL_VECTOR 0.15d0 0.d0 1.d0 # [m]
      RADIUS_X 20.d0 # [m]
      RADIUS_Y 100.d0 # [m]
      RADIUS_Z 100.d0 # [m]
    /

  /		

