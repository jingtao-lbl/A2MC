Back to :ref:`card-index`

.. _geomechanics-material-property:

GEOMECHANICS_MATERIAL_PROPERTY
==============================
Specifies geomechanics material properties to be associated with a geomechanics
region in the problem domain. The Young’s modulus and Poisson’s ratio (for the linear elastic model), rock density (used in body force calculation), Biot’s coefficient and thermal expansion coefficient can be set here.


Required Cards:
---------------
ID <int>
 Id of the material

YOUNGS_MODULUS <float> [Pa]
  Young's modulus of the material

ROCK_DENSITY <float> [kg/m3]
  Density of the material

BIOT_COEFFICIENT <float>
  Biot coefficient of the material

THERMAL_EXPANSION_COEFFICIENT <float>
  Thermal expansion coefficient of the material

POISSONS_RATIO <float> [Pa/K]
  Poisson's ratio of the material

Examples
--------

 ::

 
  GEOMECHANICS_MATERIAL_PROPERTY soil1
    ID 1
    ROCK_DENSITY 2200.d0
    YOUNGS_MODULUS 1.d10
    POISSONS_RATIO 0.3
    BIOT_COEFFICIENT 1.0
    THERMAL_EXPANSION_COEFFICIENT 1.d-5
  END 
