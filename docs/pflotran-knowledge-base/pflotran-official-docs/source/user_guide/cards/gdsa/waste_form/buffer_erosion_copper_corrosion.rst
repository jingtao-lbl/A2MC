Back to :ref:`card-index`

Back to :ref:`waste-form-general-card`

.. _buffer-erosion-copper-corrosion-card:

BUFFER_EROSION_COPPER_CORROSION
===============================

Specifies the properties for the buffer erosion/copper corrosion card.
The model is documented in Park et al. (2024).

The following cards must be specified in the WASTE_FORM block:

FRACTURE_ANGLE <float>
  Angle of largest fracture intersecting borehole.

FRACTURE_APERTURE <float>
  Aperture of largest fracture intersecting borehole.

WATER_VELOCITY <float>
  Water velocity across borehole.

ION_CONCENTRATION <float>
  Salinity of groundwater at borehole location.

Example
-------

::
    
  WASTE_FORM
    REGION wp
    EXPOSURE_FACTOR 1.0d+0
    VOLUME 1.0d+0 m^3
    MECHANISM_NAME csnf
    FRACTURE_ANGLE 1.5708
    FRACTURE_APERTURE 0.0001
    WATER_VELOCITY  41
    ION_CONCENTRATION 1.946
  /
   
Required Cards
--------------

BOREHOLE_RADIUS <float>
  Radius of the borehole.

BUFFER_POROSITY <float>
  Porosity of the buffer.

CANISTER_RADIUS <float>
  Radius of the canister.

CANISTER_WALL_THICKNESS <float>
  Thickness of the canister wall.

REACTANT_CONC_HS <float>
  Reactant concentration.


Optional Cards:
---------------

SMECTITE_PARTICLE_DENSITY <float>
  Buffer grain density. Default value [2700 kg\/m\ :sup:`3`\].

DIFF_COEF_IN_BH <float>
  Diffusion coefficient in borehole. Default value 1d-9 [m\ :sup:`2`\ /s].

SMECTITE_VOL_FRAC_BH_INT <float>
  Smectite volume fraction in borehole initially. Default value 0.574.

SMECTITE_VOL_FRAC_AT_RIM <float>
  Smectite volume fraction at intuding rim. Default value 0.015.

Y0 <float>
  Time-dependent empirical exponent y\ :sub:`0`\  for total buffer extruded over time.
  Default value 93.74.

Y1 <float>
  Time-dependent empirical exponent y\ :sub:`1`\  for total buffer extruded over time.
  Default value -0.0004521.
  
Y2 <float>
  Time-dependent empirical exponent y\ :sub:`2`\  for total buffer extruded over time.
  Default value 2.236d-9.
  
CI_UPPER_BOUND <float>
  Salinity threshold above which no buffer is eroded. Default value 4 mM.

CI_LOWER_BOUND <float>
  Salinity lower bound for smectite diffusivity calculation. Default value 0.1 mM.

SEDIMENT_RELEASE_CONSTANT <float>
  Experimentally determined sedimentation rate. Default value 1000 [kg\/m\ :sup:`3`\].

AGGLOMERATE_FLUID_VISCOSITY <float>
  Viscosity of agglomerate fluid. Default value 0.1 [Pa-s]

AF_DENSITY <float>
  Density of agglomerate fluid. Default value 1017 [kg\/\m :sup:`3`\].

AF_VOL_DEN <float>
  Volume density of agglomerate fluid. Default value

F1 <float>
  Volume multiplier to critical volume of buffer loss to expose copper. Default value 1.

CANISTER_DENSITY <float>
  Density of canister material. Default value 8900 [kg\/m\ :sup:`3`\].

MW_CANISTER_METAL <float>
  Molecular weight of canister material. Default value 63.54 [g/mol].

MW_REACTANT <float>
  Molecular weight of corroding agent. Default value 33.07 [g/mol].

METAL_TO_RECTANT_RATIO
  Stoichiometric ratio of corroding agent to corroding metal. Default value 2.

EXPOSED_SURFACE_MULTIPLIER
  Exposed surface multiplier to area of copper exposed after buffer erosion. Default
  value 1.


Example
-------

::
   
 CANISTER_DEGRADATION_MODEL
   CANISTER_MATERIAL_CONSTANT 1500.
   BUFFER_EROSION_COPPER_CORROSION
     BOREHOLE_RADIUS 0.925
     BUFFER_POROSITY 0.35
     CANISTER_RADIUS 0.525
     CANISTER_DENSITY 8900
     REACTANT_CONC_HS 1.21d-4
   /
 /



   
