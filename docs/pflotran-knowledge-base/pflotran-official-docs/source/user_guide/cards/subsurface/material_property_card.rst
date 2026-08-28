Back to :ref:`card-index`

.. _material-property-card:

MATERIAL_PROPERTY
=================
Specifies material properties to be associated with a region in the problem domain.

Required Cards:
---------------
MATERIAL_PROPERTY <string>

 Opens the card block.  Can be followed by its name in a string.

NAME <string>

  Name by which material property object may be identified/linked (usually follows MATERIAL_PROPERTY keyword).

ID <int>

  ID by which material property object may be identified/linked.  This is particularly useful when material ids are assigned on a cell by cell basis. **Note that ID = 0 is reserved for inactive grid cells and cannot be used in this block.  To inactivate a material that is assigned to a region, see the INACTIVE card under STRATA.**

POROSITY <float>

  Porosity of material [-].

POROSITY DATASET <string>

 Porosity of material specified through a dataset.

PERMEABILITY <float>

 Permability of material [m\ :sup:`2`\].  See examples below.

 ANISOTROPIC
 
  Toggles on anisotropy.  (This card is required for anisotropic permeability specified through DATASETs too.  In that case, dataset_nameX, dataset_nameY and dataset_nameZ must be defined within the input file where "dataset_name" is the defined through the DATASET keyword.)
  
 FULL_TENSOR
   
   Toggles on full tensor anisotropy. Must be used along with the card ANISOTROPIC. (This card is required for off diagonal permeability component specified through PERMEABILITY_XY, PERMEABILITY_XZ, PERMEABILITY_YZ and DATASETs. In the latter case, dataset_nameXY, dataset_nameXZ and dataset_nameYZ must be defined within the input file where "dataset_name" is the defined through the DATASET keyword)

 ISOTROPIC
 
  Toggle off anisotropy.

 PERM_ISO <float>
 
  Isotropic permeability [m\ :sup:`2`\].

 PERM_HORIZONTAL <float>
 
  Permeability in x- and y-directions. One must include the 
  VERTICAL_ANISOTROPY_RATIO card to define the permeability in the 
  z-direction [m\ :sup:`2`\].

 PERM_X <float>
 
  Permeability in x-direction [m\ :sup:`2`\].

 PERM_Y <float>
 
  Permeability in y-direction [m\ :sup:`2`\].

 PERM_Z <float>
 
  Permeability in z-direction [m\ :sup:`2`\].
  
 PERM_XY <float>
 
  Off-diagonal permeability tensor component in the xy-direction [m\ :sup:`2`\].
  
 PERM_XZ <float>
 
  Off-diagonal permeability tensor component in the xz-direction [m\ :sup:`2`\].
  
 PERM_YZ <float>
 
  Off-diagonal permeability tensor component in the yz-direction [m\ :sup:`2`\].

 PERM_ISO_LOG10 <float>
 
  Log10 of the permeability ([m\ :sup:`2`\]). Applies to all directions.

 PERM_X_LOG10 <float>
 
  Log10 of the permeability ([m\ :sup:`2`\]) in x-direction.

 PERM_Y_LOG10 <float>
 
  Log10 of the permeability ([m\ :sup:`2`\]) in y-direction.

 PERM_Z_LOG10 <float>
 
  Log10 of the permeability ([m\ :sup:`2`\]) in z-direction.
  
 PERM_XY_LOG10 <float>
 
  Log10 of the  off-diagonal permeability tensor component in the xy-direction [m\ :sup:`2`\].
  
 PERM_XZ_LOG10 <float>
 
  Log10 of the off-diagonal permeability tensor component in the xz-direction [m\ :sup:`2`\].
  
 PERM_YZ_LOG10 <float>
 
  Log10 of the off-diagonal permeability tensor component in the yz-direction [m\ :sup:`2`\].

 PERMEABILITY_SCALING_FACTOR <float>
 
  Specifies a value <float> that scales the entire permeability tensor.

 VERTICAL_ANISOTROPY_RATIO <float>
  Sets the horizontal permeability (kx and ky) to the
  value specified by PERM_ISO (in the case of a dataset) or PERM_HORIZONTAL 
  and scales the vertical permeability (kz) by the ratio <float>.

 DATASET <string>
 
  Permeability to be read from a dataset in ASCII or HDF5 (preferred) formatted file named by the string.  For anisotropic permeability, the keyword ANISOTROPIC must be included in the PERMEABILITY block and the datasets must be named *stringX*, *stringY* and *stringZ* in the PFLOTRAN input file.  See example_ below.


Optional Cards:
---------------
CHARACTERISTIC_CURVES <string>

 Name of characteristic curves block to be associated with material

LONGITUDINAL_DISPERSIVITY <float>

 Longitudinal dispersivity for transport within material [m]
 
TRANSVERSE_DISPERSIVITY_H <float>

 Horizontal transverse dispersivity for transport within material [m]
 
TRANSVERSE_DISPERSIVITY_V <float>

 Vertical transverse dispersivity for transport within material [m]
 
MATERIAL_TRANSFORM <string>

 Name of material transform function to be associated with material.

PERMEABILITY_CRITICAL_POROSITY <float>

 Critical porosity (:math:`\porosity_c`)  in the equation that scales permeability as a function of porosity.  See UPDATE_PERMEABILITY in users manual.

PERMEABILITY_POWER <float>

 Coefficient :math:`n` in the equation that scales permeability as a function of porosity.  See UPDATE_PERMEABILITY in users manual.

PERMEABILITY_MIN_SCALE_FACTOR <float>

 Minimum value by which permeability may be scaled when permeability is calculated as a function of porosity.  See UPDATE_PERMEABILITY in users manual.

POROSITY_COMPRESSIBILITY <float>

 Compressibility :math:`C_{\porosity}` of the void-space volume fraction [1/Pa].  :math:`C_{\porosity} \equiv (\alpha_b - \alpha_p)`, where :math:`\alpha_b` and :math:`\alpha_p` are the bulk volume and pore volume compressibility coefficients  defined in Bear (1972) as :math:`\alpha_b \equiv -\frac{1}{V_b}\frac{\partial V_b}{\partial p}` and :math:`\alpha_p \equiv -\frac{1}{V_p}\frac{\partial V_p}{\partial p}`.  Note that :math:`\alpha_b = (1-\porosity) \alpha_s + \porosity \alpha_p`.  Typically, :math:`\alpha_b` and :math:`\alpha_p` are negative numbers, and the resulting :math:`C_{\porosity}` is a positive number.  If you assume that the solid particles of the porous medium are incompressible (:math:`\alpha_s \approx 0`), then :math:`C_{\porosity} \approx -\frac{(1-\porosity)}{\porosity} \alpha_b`.   Use in conjuction with SOIL_COMPRESSIBILITY_FUNCTION POROSITY_EXPONENTIAL.


ROCK_DENSITY <float>
 Soil particle density of material [kg/m\ :sup:`3`\]

SATURATION_FUNCTION <string>

 Name of saturation function to be associated with material (deprecated for
 most flow modes).

:ref:`secondary-continuum-card`
 Specifies parameters for multiple continuum model

SOIL_COMPRESSIBILITY <float>

 Compressibility :math:`C_{s}` of the soil matrix [1/Pa] (i.e. non-void-space volume fraction).  :math:`C_{s} \equiv (\alpha_s - \alpha_b)`, where :math:`\alpha_s` and :math:`\alpha_b` are the solid volume and bulk volume compressibility coefficients defined in Bear (1972) as :math:`\alpha_s \equiv -\frac{1}{V_s}\frac{\partial V_s}{\partial p}` and :math:`\alpha_b \equiv -\frac{1}{V_b}\frac{\partial V_b}{\partial p}`.  Note that :math:`\alpha_b = (1-\porosity) \alpha_s + \porosity \alpha_p`.  Typically, :math:`\alpha_s` is positive while :math:`\alpha_b` is negative, and the resulting :math:`C_{s}` is a positive number.  If you assume that the solid particles of the porous medium are incompressible (:math:`\alpha_s \approx 0`), then :math:`C_{s} \approx -\alpha_b`.   Use in conjuction with SOIL_COMPRESSIBILITY_FUNCTION LEIJNSE (DEFAULT).

SOIL_COMPRESSIBILITY_FUNCTION <string>

 Name of soil compressibility function [DEFAULT, LEIJNSE, POROSITY_EXPONENTIAL].  Default corresponds to Leijnse. 
 
 The Leijnse function (see Bear and Verruijt 1987 or Leijnse 1992) calculates porosity as :math:`\frac{(1-\porosity)}{(1-\porosity_{ref})} = \exp[-C_s (p-p_{ref})]`, where :math:`C_s \equiv \frac{-1}{(1-\porosity)} \frac{\partial (1-\porosity)}{\partial p}` is assumed constant and is specified using the SOIL_COMPRESSIBILITY card.  :math:`p_{ref}` is specified using the SOIL_REFERENCE_PRESSURE card, and :math:`\porosity_{ref}` corresponds to the porosity defined using the POROSITY card.

 The POROSITY_EXPONENTIAL function calculates porosity as :math:`\frac{\porosity}{\porosity_{ref}} = \exp[+C_{\porosity} (p-p_{ref})]`, where :math:`C_{\porosity} \equiv \frac{1}{\porosity} \frac{\partial \porosity}{\partial p}` is assumed constant and is specified using the POROSITY_COMPRESSIBILITY card.  :math:`p_{ref}` is specified using the SOIL_REFERENCE_PRESSURE card, and :math:`\porosity_{ref}` corresponds to the porosity defined using the POROSITY card.


SOIL_REFERENCE_PRESSURE [<float> or INITIAL_PRESSURE]

 Reference pressure for soil matrix compressibility function [Pa].  INITIAL_PRESSURE specifies that the initial pressure at each grid cell be used instead of the float value.

SPECIFIC_HEAT <float> or HEAT_CAPACITY <float>

 Specific heat capacity of material [J/(kg-K)]
 
TENSORIAL_REL_PERM_EXPONENT <float> <float> <float>

 Specifies the three exponents for tensorial relative permeability, one for
 each principal direction.
 
THERMAL_CHARACTERISTIC_CURVES <string>

  Name of thermal characteristic curve to be associated with material. This replaces THERMAL_CONDUCTIVITY_DRY and THERMAL_CONDUCTIVITY_WET.

THERMAL_CONDUCTIVITY_DRY <float>

 Dry thermal conductivity of material [W/(K-m)]

THERMAL_CONDUCTIVITY_WET <float>

 Wet thermal conductivity of material [W/(K-m)]

THERMAL_EXPANSITIVITY <float>

 Thermal expansitivity of material [?]

TORTUOSITY <float>

 Tortuosity of material (for diffusive solute transport) [-]

TORTUOSITY DATASET <string>

 Tortuosity of material specified through a dataset.

TORTUOSITY_POWER <float>

 Exponent in equation for transient tortuosity.

TORTUOSITY_FUNCTION_OF_POROSITY <float>

 Specifies that tortuosity be calculated as a function of porosity, tor = por\ :sup:`t`, where exponent t [-] is specifed after the card.  Use in place of TORTUOSITY.  Porosity can be specified through a dataset or as a uniform value.

ANISOTROPIC_TORTUOSITY

 Toggles on anisotropic tortuosity (diagonal elements of tensor only)

 TORTUOSITY_X

  Tortuosity in x-direction [-]

 TORTUOSITY_Y

  Tortuosity in y-direction [-]

 TORTUOSITY_Z

  Tortuosity in z-direction [-]
 
Examples
--------
 ::

  MATERIAL_PROPERTY Hanford
    ID 1
    CHARACTERISTIC_CURVES cc1
    POROSITY 0.2
    TORTUOSITY 0.5
    PERMEABILITY
      PERM_X 7.387d-9
      PERM_Y 7.387d-9
      PERM_Z 7.387d-10
    /
  END

  MATERIAL_PROPERTY Hanford
    ID 1
    CHARACTERISTIC_CURVES cc1
    POROSITY 0.2
    TORTUOSITY 0.5
    PERMEABILITY
      PERM_HORIZONTAL 7.387d-9
      VERTICAL_ANISOTROPY_RATIO 0.1d0
    /
  END

  MATERIAL_PROPERTY soil
    ID 1
    CHARACTERISTIC_CURVES cc1
    POROSITY 0.45
    TORTUOSITY 1.
    ROCK_DENSITY 2650.d0
    THERMAL_CONDUCTIVITY_DRY 0.5
    THERMAL_CONDUCTIVITY_WET 2.
    HEAT_CAPACITY 830.
    SOIL_COMPRESSIBILITY_FUNCTION DEFAULT ! LEIJNSE
    SOIL_COMPRESSIBILITY 1.d-8
    SOIL_REFERENCE_PRESSURE 101325.d0
    PERMEABILITY
      PERM_ISO 1.d-17
    /
  END


Porosity compressibility

 ::

  MATERIAL_PROPERTY rock1
    ID 1
    CHARACTERISTIC_CURVES default
    POROSITY 0.20
    TORTUOSITY 1.
    ROCK_DENSITY 2650.d0
    THERMAL_CONDUCTIVITY_DRY 0.5
    THERMAL_CONDUCTIVITY_WET 2.0
    HEAT_CAPACITY 830.
    SOIL_COMPRESSIBILITY_FUNCTION POROSITY_EXPONENTIAL
    POROSITY_COMPRESSIBILITY 1.d-8
    SOIL_REFERENCE_PRESSURE INITIAL_PRESSURE
    PERMEABILITY
      PERM_ISO 1.d-19
    /
  END


Tortuosity as a function

 ::

  MATERIAL_PROPERTY shale
    ID 1
    CHARACTERISTIC_CURVES default
    POROSITY 0.20
    TORTUOSITY_FUNCTION_OF_POROSITY 1.4 
    ROCK_DENSITY 2700.d0
    THERMAL_CONDUCTIVITY_DRY 1.2
    THERMAL_CONDUCTIVITY_WET 1.2
    HEAT_CAPACITY 830.
    SOIL_COMPRESSIBILITY_FUNCTION DEFAULT ! LEIJNSE
    SOIL_COMPRESSIBILITY 1.6d-8
    SOIL_REFERENCE_PRESSURE 101325.d0
    PERMEABILITY
      PERM_ISO 1.d-19
    /
  END

Anisotropic tortuosity

 ::

  MATERIAL_PROPERTY mat1
    ID 1
    POROSITY 0.3d0
    PERMEABILITY 
      PERM_ISO 1.d-12
    /
    ANISOTROPIC_TORTUOSITY
      TORTUOSITY_X 1.1d0
      TORTUOSITY_Y 0.6d0
      TORTUOSITY_Z 2.d0
    END
    CHARACTERISTIC_CURVES default
  END


Associating datasets with material properties

 ::

  MATERIAL_PROPERTY Hanford
    ID 1
    CHARACTERISTIC_CURVES cc1
    POROSITY DATASET poros
    TORTUOSITY 0.5
    PERMEABILITY
      VERTICAL_ANISOTROPY_RATIO 0.1
      DATASET perm
    /
  END

with

 ::

  DATASET perm
    FILENAME hanford_unit.h5
    REALIZATION_DEPENDENT
  END

  DATASET poros
    FILENAME hanford_unit.h5
    REALIZATION_DEPENDENT
  END

.. _example:

Anisotropic permeability dataset within material properties

 ::

  MATERIAL_PROPERTY Hanford
    ID 1
    CHARACTERISTIC_CURVES cc1
    POROSITY DATASET poros
    TORTUOSITY 0.5
    PERMEABILITY
      ANISOTROPIC
      DATASET perm
    /
  END

with

 ::

  DATASET permX
    FILENAME hanford_unit.h5
    HDF5_DATASET_NAME some_name
  END
  DATASET permY
    FILENAME hanford_unit.h5
    HDF5_DATASET_NAME a_different_name
  END
  DATASET permZ
    FILENAME hanford_unit.h5
    HDF5_DATASET_NAME some_name ! can be the same name.
  END
