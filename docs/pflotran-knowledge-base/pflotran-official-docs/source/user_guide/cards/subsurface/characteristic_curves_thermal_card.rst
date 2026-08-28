Back to :ref:`card-index`

.. _thermal-characteristic-curves-card:

THERMAL_CHARACTERISTIC_CURVES
=============================
This option specifies the thermal characteristic curves (e.g. thermal conductivity and associated parameters) associated with a material property. This expands thermal conductivity as a function of both temperature and saturation (with the exception of the CONSTANT, DEFAULT, and LINEAR thermal conductivity functions). 

The legacy input method of specifying thermal conductivity by :ref:`material-property-card` (i.e. with THERMAL_CONDUCTIVITY_DRY and THERMAL_CONDUCTIVTY_WET) is backwards-compatible, where parameters are adapted to the DEFAULT thermal characteristic curve and functions are numbered in material sequence. However, THERMAL_CHARACTERISTIC_CURVES **cannot** be combined with the legacy convention in the same input file.

Required Blocks and Cards:
**************************
THERMAL_CONDUCTIVITY_FUNCTION <string>
  Opens a thermal conductivity block, where <string> indicates the type of thermal conductivity function to be employed. 

  Supported THERMAL_CONDUCTIVITY_FUNCTIONs (along with their required cards):
  
  .. _tcc-constant-input:
  
  * CONSTANT
    
    + CONSTANT_THERMAL_CONDUCTIVITY

  .. _tcc-default-input:

  * DEFAULT
    
    + THERMAL_CONDUCTIVITY_DRY
    + THERMAL_CONDUCTIVITY_WET

  .. _tcc-linear-input:

  * LINEAR
    
    + THERMAL_CONDUCTIVITY_DRY
    + THERMAL_CONDUCTIVITY_WET

  .. _tcc-power-input:      
      
  * POWER

    + THERMAL_CONDUCTIVITY_DRY
    + THERMAL_CONDUCTIVITY_WET
    + REFERENCE_TEMPERATURE
    + EXPONENT

  .. _tcc-cubic-polynomial-input:

  * CUBIC_POLYNOMIAL

    + THERMAL_CONDUCTIVITY_DRY
    + THERMAL_CONDUCTIVITY_WET
    + REFERENCE_TEMPERATURE
    + CUBIC_POLYNOMIAL_COEFFICIENTS

  .. _tcc-linear-resistivity-input:

  * LINEAR_RESISTIVITY

    + THERMAL_CONDUCTIVITY_DRY
    + THERMAL_CONDUCTIVITY_WET
    + REFERENCE_TEMPERATURE
    + LINEAR_RESISTIVITY_COEFFICIENTS

  .. _tcc-frozen-input:

  * FROZEN

    + THERMAL_CONDUCTIVITY_DRY
    + THERMAL_CONDUCTIVITY_WET
    + KERSTEN_EXPONENT
    + THERMAL_CONDUCTIVITY_FROZEN
    + KERSTEN_EXPONENT_FROZEN
    + ICE_MODEL

  .. _tcc-composite-input:
  
  * COMPOSITE
  
    + COMPOSITE_X
    + COMPOSITE_Y
    + COMPOSITE_Z

  .. _tcc-assembly-axial-input:
  
  * ASM_AXIAL (Assembly axial model)
  
    + THERMAL_CONDUCTIVITY_WATER
    + THERMAL_CONDUCTIVITY_SOLID
    + POROSITY_ASSEMBLY
 
  .. _tcc-assembly-radial-input:
 
  * ASM_RADIAL (Assembly radial model)
  
    + THERMAL_CONDUCTIVITY_WATER
    + THERMAL_CONDUCTIVITY_SOLID
    + POROSITY_ASSEMBLY
    + THERMAL_CONDUCTIVITY_DRY
    + ASM_DRY_COEFFICIENT
    + ASM_DRY_EXPONENT
 
  .. _tcc-assembly-water-input:
 
  * ASM_WATER_FILLED (Standalone model for water-filled assembly)
  
    + THERMAL_CONDUCTIVITY_WATER
    + THERMAL_CONDUCTIVITY_SOLID
    + POROSITY_ASSEMBLY
    + THERMAL_CONDUCTIVITY_DRY (optional)

  .. _tcc-assembly-dry-input:

  * ASM_DRY (Standalone model for dry assembly)
  
    + THERMAL_CONDUCTIVITY_DRY
    + ASM_DRY_COEFFICIENT
    + ASM_DRY_EXPONENT
    + THERMAL_CONDUCTIVITY_WET (optional)

.. _tcc-parameter-definitions:

Thermal Characteristic Curves Parameter Definitions
---------------------------------------------------

CONSTANT_THERMAL_CONDUCTIVITY <float>
 Thermal conductivity of porous medium that does not depend on temperature or saturation [W/m-K].

THERMAL_CONDUCTIVTY_WET <float>
 Thermal conductivity of the wet porous medium (:math:`s_l=1`) [W/m-K].

THERMAL_CONDUCTIVITY_DRY <float>
 Thermal conductivity of the dry porous medium (:math:`s_l=0`) [W/m-K].

 In the DEFAULT model, effective thermal conductivity (:math:`\kappa_T`) at the given liquid saturation is computed as :math:`\kappa_T(s_l)=\kappa_T^{dry} + \sqrt{s_l}(\kappa_T^{wet} - \kappa_T^{dry})` [W/m-K]. [1]

 In the LINEAR model, effective thermal conductivity (:math:`\kappa_T`) at the given liquid saturation is computed as :math:`\kappa_T(s_l)=\kappa_T^{dry} + \saturation_l(\kappa_T^{wet} - \kappa_T^{dry})` [W/m-K].

REFERENCE_TEMPERATURE <float>
 This temperature is subtracted from the actual temperature before the calculation (useful for conversion from Celsius to Kelvin, or to shift the zero a polynomial) [°C].

EXPONENT <float>
 In the POWER model, this is the exponent of temperature, called :math:`\gamma` [-].

 Thermal conductivity for the POWER model is computed as :math:`\kappa_T(s_l,T)=\kappa_T(s_l)[(T-T_{ref})/300]^\gamma` [W/m-K].

 The saturation dependence of the POWER model comes from the DEFAULT model, and when using the default :math:`T_{ref}=-273.15\:°C`, THERMAL_CONDUCTIVITY_WET and THERMAL_CONDUCTIVITY_DRY are at 26.85 °C.

CUBIC_POLYNOMIAL_COEFFICIENTS <float> <float> <float>
 Coefficients of a cubic polynomial expression for the temperature-dependence, called :math:`\beta_i`.

 Thermal conductivity for the CUBIC_POLYNOMIAL model is computed as :math:`\kappa_T(s_l,T)=\kappa_T(s_l)[1 + \beta_1 (T-T_{ref}) + \beta_2 (T-T_{ref})^2 + \beta_3 (T-T_{ref})^3]` [W/m-K].

 The saturation dependence of the CUBIC_POLYNOMIAL model comes from the DEFAULT model, and when using the default :math:`T_{ref}=0\:°C`, THERMAL_CONDUCTIVITY_WET and THERMAL_CONDUCTIVITY_DRY are at 0 °C. 
  
LINEAR_RESISTIVITY_COEFFICIENTS <float> <float>
 Coefficients of a linear inverse conductivity (i.e., resistivity), called :math:`a_i`.

 Thermal conductivity for the LINEAR_RESISTIVITY model is computed as :math:`\kappa_T(s_l,T)=\kappa_T(s_l)/[a_1 + a_2 (T - T_{ref})]` [W/m-K], with the default :math:`T_{ref}=0\:°C`.

 The saturation dependence of the LINEAR_RESISTIVITY model comes from the DEFAULT model, and when using the default :math:`T_{ref}=0\:°C`, THERMAL_CONDUCTIVITY_WET and THERMAL_CONDUCTIVITY_DRY are at 0 °C. Typically :math:`a_1=1`.

 Note: this function also implements porosity dependence. See :ref:`tcc-porosity-dependence-definitions` for additional parameters needed to turn on this behavior.

KERSTEN_EXPONENT <float>
 In :ref:`th-card` mode, this is the exponent (:math:`\alpha_{u}` [-]) of liquid saturation used to derive the Kersten number for unfrozen soil: :math:`Ke_{u}=s^{\alpha_{u}}_{l}` (see :ref:`mode-th-ice-model`).
 
 Outside of :ref:`th-card` mode, only the dry and wet components of the ice model are utilized for FROZEN.

THERMAL_CONDUCTIVITY_FROZEN <float>
  In the FROZEN model, this is the thermal conductivity of frozen soil [W/m-K] (see :ref:`mode-th-ice-model`).

  When this parameter is specified in :ref:`th-card` mode, the FREEZING option (see :ref:`th-simulation-options`) automatically becomes active.
  
KERSTEN_EXPONENT_FROZEN <float>
  In the FROZEN model, this is the exponent (:math:`\alpha_{f}` [-]) of ice saturation used to derive the Kersten number for frozen soil: :math:`Ke_{f}=s^{\alpha_{f}}_{i}` (see :ref:`mode-th-ice-model`).
    
  This parameter must be specified with THERMAL_CONDUCTIVITY_FROZEN.
  
ICE_MODEL 
  Specifies the ice model for the FROZEN model. Options include:
    * PAINTER_EXPLICIT [2]
    * PAINTER_KARRA_IMPLICIT [3]
    * PAINTER_KARRA_EXPLICIT [3]
    * PAINTER_KARRA_EXPLICIT_NOCRYO [3]
    * DALL_AMICO [4,5]
    
  This parameter must be specified with THERMAL_CONDUCTIVITY_FROZEN.

.. _tcc-composite-function:

Composite Function
------------------

In the COMPOSITE function, the following parameters are used to employ previously-defined thermal characteristic curves along certain principal axes (see `example <tcc-example-composite_>`_). `Anisotropy ratios <tcc-anisotropy-parameter-definitions_>`_ can also be specified if needed. 
 
COMPOSITE_X <string>
  Name of the thermal characteristic curve governing conduction in the X direction.

COMPOSITE_Y <string>
  Name of the thermal characteristic curve governing conduction in the Y direction.

COMPOSITE_Z <string>
  Name of the thermal characteristic curve governing conduction in the Z direction.

.. _tcc-assembly-model-definitions:

Assembly Models
---------------
Models are available to describe the conduction of heat in spent nuclear fuel assemblies along both radial and axial directions. 

The radial model (`ASM_RADIAL <tcc-assembly-radial-input_>`_) takes the form of the DEFAULT curve, albeit with a temperature-dependent dry component and a special wet component: :math:`\kappa_{radial}(s_l,T)=\kappa_{d}(T)+[\kappa_{w}^{\prime}-\kappa_{d}(T)\sqrt{s_{l}}]` [W/m-K].

The dry thermal conductivity of the radial model takes the form of a power law with temperature: :math:`\kappa_{d}(T)=\kappa_{d}^{0}+\alpha T^{\beta}` [W/m-K] for :math:`T\ge\:0 °C`.[6] 
  * This model can be used on its own with the `ASM_DRY <tcc-assembly-dry-input_>`_ function.
  * A constant :math:`\kappa_{w}` may be specified to use the saturation dependence of the `DEFAULT <tcc-default-input_>`_ model.

The wet thermal conductivity of the radial model takes into account the porosity of the assembly :math:`(\Phi)` and the thermal conductivities of its solid constituents and contained water (:math:`\kappa_{s}` and :math:`\kappa_{l}`): :math:`\kappa_{w}^{\prime}=\kappa_{l}\Bigg[1-\sqrt{1-\Phi}+\frac{\sqrt{1-\Phi}}{1+(\frac{\kappa_{l}}{\kappa_{s}}-1)\sqrt{1-\Phi}}\Bigg]` [W/m-K].[7] 
  * This model can be used on its own with the `ASM_WATER_FILLED <tcc-assembly-water-input_>`_ function.
  * A constant :math:`\kappa_{d}` may be specified to use the saturation dependence of the `DEFAULT <tcc-default-input_>`_ model.

The axial model (`ASM_AXIAL <tcc-assembly-axial-input_>`_) assumes parallel conduction between solid constituents in the assembly and the surrounding water. When applied to an unsaturated system, it assumes that the thermal conductivity of gas is negligible. It differs from the DEFAULT curve by having linear saturation dependence and by using the thermal conductivities of assembly solids and water (as opposed to dry and wet components): :math:`\kappa_{axial}(s_{l})=(1-\Phi)\kappa_{s}+\Phi \saturation_{l}\kappa_{l}` [W/m-K].

THERMAL_CONDUCTIVITY_WATER <float>
 The thermal conductivity of water (:math:`\kappa_{l}` [W/m-K]) contained in the assembly.
   
THERMAL_CONDUCTIVITY_SOLID <float>
 The thermal conductivity of the solid components in the assembly, including rods and baskets (:math:`\kappa_{s}` [W/m-K]).
   
POROSITY_ASSEMBLY <float>
 The porosity of the assembly :math:`(\Phi)`, or the ratio of the volume of void to the total volume. 
   
THERMAL_CONDUCTIVITY_DRY <float>
 For the radial assembly model, the dry thermal conductivity is applied as the zero-order term describing the baseline thermal conductivity of the dry assembly at 0 °C (:math:`\kappa_{d}^{0}` [W/m-K]).
   
ASM_DRY_COEFFICIENT <float>
 For the dry state of the radial assembly model, this is the coefficient for the temperature-dependent term (:math:`\alpha`).
   
ASM_DRY_EXPONENT <float>
 For the dry state of the radial assembly model, this is the exponent of temperature in the temperature-dependent term (:math:`\beta`). Both :math:`\alpha` and :math:`\beta` must be fitted to align with the units of :math:`\kappa_{d}^{0}`. 

Optional Blocks and Cards:
**************************

.. _tcc-anisotropy-parameter-definitions:

Thermal Conductivity Anisotropy Parameter Definitions
-----------------------------------------------------

The following parameters are used to impart a direction-dependent treatment of thermal conductivity for thermal characteristic curves that employ :math:`\kappa_T(s_l)` from the DEFAULT function. The following inputs are ratios that determine what fraction of the user-input values (THERMAL_CONDUCTIVITY_DRY or THERMAL_CONDUCTIVITY_WET) comprise particular components of the thermal conductivity tensor. 

ANISOTROPY_RATIO_X <float>
 The ratio applied to user-input thermal conductivity to derive the :math:`\kappa_{xx}` component of the thermal conductivity tensor. Requires additional input of Y and Z ratios. 
 
ANISOTROPY_RATIO_Y <float>
 The ratio applied to user-input thermal conductivity to derive the :math:`\kappa_{yy}` component of the thermal conductivity tensor. Requires additional input of X and Z ratios. 
  
ANISOTROPY_RATIO_Z <float>
 The ratio applied to user-input thermal conductivity to derive the :math:`\kappa_{zz}` component of the thermal conductivity tensor. Requires additional input of X and Y ratios. 

.. _tcc-porosity-dependence-definitions:

Porosity-Dependent Thermal Conductivity Definition
--------------------------------------------------

The LINEAR_RESISTIVITY thermal conductivity model has three optional parameters. If these parameters are not specified, the model has no variation with porosity (see LINEAR_RESISTIVITY_COEFFICIENTS in :ref:`tcc-parameter-definitions`). All three optional parameters presented below must be specified to turn on this behavior. 

REFERENCE_POROSITY <float>
 Maximum porosity expected (:math:`\porosity_{\mathrm{ref}}`). Value used to normalize porosity values between 0 and 1. If porosity goes above REFERENCE_POROSITY, the normalized value is capped at 1.0.

POROSITY_EXPONENT <float>
 A dimensionless exponent applied to the solid fraction (:math:`\xi`).

INITIAL_LINEAR_COEFFICIENTS <float> <float>
 Two coefficients (:math:`b_1` and :math:`b_2`) used to express linear temperature dependence of the thermal conductivity of the pore space (:math:`b_1 + b_2 T`).

The expression was developed for reconsolidation of granular salt with air-filled porosity (Bollingerfehr et al., 2012; Table B.4, Saltgrus), :math:`\kappa_T(s_l,T,\porosity) = \kappa_T(s_l,T) (1-\frac{\porosity}{\porosity_{\mathrm{ref}}})^\xi + (\frac{\porosity}{\porosity_{\mathrm{ref}}}) \cdot (b_1 + b_2 T)`.

:math:`\kappa_T(s_l,T)` is the LINEAR_RESISTIVITY function presented previously (associated with LINEAR_RESISTIVITY_COEFFICIENTS without porosity variation).

At :math:`\porosity=0`, the thermal conductivity is equal to the LINEAR_RESISTIVITY model without porosity variation. At :math:`\porosity\ge\porosity_\mathrm{ref}` the thermal conductivity has a linear dependence on temperature, given by :math:`b_1` and :math:`b_2`. At porosities between these two endmembers, the porosity is interpolated as a combination of the two.

.. _tcc-test:

Test Thermal Characteristic Curve
---------------------------------
TEST
 Including this keyword will produce output (.dat file) for a thermal characteristic curve that includes: 
  (a) temperature [C] :math:`(T)`,
  (b) liquid saturation [-] :math:`(s_l)`,
  (c) porosity [-] :math:`(\porosity)`
  (d) thermal conductivity [W/m*K] :math:`(\kappa_T)`,
  (e) derivative of thermal conductivity with respect to liquid saturation :math:`(\frac{\partial \kappa_T}{\partial \saturation_l})`,
  (f) derivative of thermal conductivity with respect to temperature :math:`(\frac{\partial \kappa_T}{\partial T})`,
  (g) numerical approximation to (e.),
  (h) numerical approximation to (f.), and
  (i) numerical approximation to derivative of thermal conductivity with respect to porosity :math:`(\frac{\partial \kappa_T}{\partial \porosity})`

 When the `FROZEN <tcc-frozen-input_>`_ model is in use with FREEZING active, there are additional parameters in the output:
   * ice saturation :math:`(s_i)`
   * :math:`\frac{\partial \kappa_T}{\partial \saturation_i}`
   * numerical approximation to :math:`\frac{\partial \kappa_T}{\partial \saturation_i}`

Examples
********

.. _tcc-example-general:

Material with thermal characteristic curve named "cct_power"
------------------------------------------------------------
 ::

  MATERIAL_PROPERTY soil
    ID 1
    CHARACTERISTIC_CURVES cc1
    POROSITY 0.000001
    TORTUOSITY 1.0
    ROCK_DENSITY 2650.0 kg/m^3
    THERMAL_CHARACTERISTIC_CURVES cct_power
    HEAT_CAPACITY 830.0 J/kg-C
    PERMEABILITY
      PERM_ISO 1.d-12
    /
  /

  THERMAL_CHARACTERISTIC_CURVES cct_constant
    THERMAL_CONDUCTIVITY_FUNCTION CONSTANT
      CONSTANT_THERMAL_CONDUCTIVITY 5.5000D+0 W/m-C
    END
    TEST
  END

  THERMAL_CHARACTERISTIC_CURVES cct_default
    THERMAL_CONDUCTIVITY_FUNCTION DEFAULT
      THERMAL_CONDUCTIVITY_DRY 5.5000D+0 W/m-C
      THERMAL_CONDUCTIVITY_WET 7.0000D+0 W/m-C
    END
    TEST
  END

  THERMAL_CHARACTERISTIC_CURVES cct_power
    THERMAL_CONDUCTIVITY_FUNCTION POWER
      THERMAL_CONDUCTIVITY_DRY 5.5000D+0 W/m-C
      THERMAL_CONDUCTIVITY_WET 7.0000D+0 W/m-C
      #REFERENCE_TEMPERATURE -273.15 ! default value
      EXPONENT -1.18D+0 
    END
    TEST
  END

  THERMAL_CHARACTERISTIC_CURVES cct_cubic_polynomial
    THERMAL_CONDUCTIVITY_FUNCTION CUBIC_POLYNOMIAL
      THERMAL_CONDUCTIVITY_DRY 5.5000D+0 W/m-C
      THERMAL_CONDUCTIVITY_WET 7.0000D+0 W/m-C
      #REFERENCE_TEMPERATURE 0.d0 ! default value
      CUBIC_POLYNOMIAL_COEFFICIENTS -4.53398D-3 1.41580D-5 -1.94840D-8
    END
    TEST
  END

  THERMAL_CHARACTERISTIC_CURVES cct_linear_resistivity
    THERMAL_CONDUCTIVITY_FUNCTION LINEAR_RESISTIVITY
      THERMAL_CONDUCTIVITY_DRY 5.5000D+0 W/m-C
      THERMAL_CONDUCTIVITY_WET 7.0000D+0 W/m-C
      #REFERENCE_TEMPERATURE 0.d0 ! default value
      LINEAR_RESISTIVITY_COEFFICIENTS 1.0d0 5.038D-3
    END
    TEST
  END

  THERMAL_CHARACTERISTIC_CURVES cct_frozen
    THERMAL_CONDUCTIVITY_FUNCTION FROZEN
      THERMAL_CONDUCTIVITY_DRY 0.2500D+0 W/m-C
      THERMAL_CONDUCTIVITY_WET 1.3000D+0 W/m-C
      KERSTEN_EXPONENT 0.45
      #THERMAL_CONDUCTIVITY_FROZEN 2.3500D+0 W/m-C
      #KERSTEN_EXPONENT_FROZEN 0.95
      #ICE_MODEL PAINTER_EXPLICIT
    END
    TEST
  END

.. _tcc-example-composite:

Material with composite thermal characteristic curve named "cct_composite"
--------------------------------------------------------------------------
 ::

   MATERIAL_PROPERTY wp
     ID 1
     CHARACTERISTIC_CURVES cc_wp
     POROSITY 0.50
     TORTUOSITY 1.0
     ROCK_DENSITY 5000.0 kg/m^3
     THERMAL_CHARACTERISTIC_CURVES cct_composite
     HEAT_CAPACITY 450.0 J/kg-C
     PERMEABILITY
       PERM_ISO 1.d-16
     /
   /

  THERMAL_CHARACTERISTIC_CURVES cct_axial
    THERMAL_CONDUCTIVITY_FUNCTION ASM_AXIAL
      THERMAL_CONDUCTIVITY_WATER 1.7200D+0 W/m-C
      THERMAL_CONDUCTIVITY_SOLID 1.6700D+1 W/m-C
      POROSITY_ASSEMBLY          5.0000D-1
    END
    TEST
  END
  
  THERMAL_CHARACTERISTIC_CURVES cct_radial
    THERMAL_CONDUCTIVITY_FUNCTION ASM_RADIAL
      THERMAL_CONDUCTIVITY_DRY   0.1430D+0 W/m-C
      THERMAL_CONDUCTIVITY_WATER 1.7200D+0 W/m-C
      THERMAL_CONDUCTIVITY_SOLID 1.6700D+1 W/m-C
      ASM_DRY_COEFFICIENT        3.8300D-5
      ASM_DRY_EXPONENT           1.6700D+0
      POROSITY_ASSEMBLY          5.0000D-1
    END
    TEST
  END
  
  THERMAL_CHARACTERISTIC_CURVES cct_composite
    THERMAL_CONDUCTIVITY_FUNCTION COMPOSITE
      COMPOSITE_X cct_radial
      COMPOSITE_Y cct_radial
      COMPOSITE_Z cct_axial
    END
  END

.. _tcc-example-anisotropic:

Material with anisotropic thermal conductivity
----------------------------------------------
 ::

  MATERIAL_PROPERTY soil
    ID 1
    CHARACTERISTIC_CURVES cc1
    POROSITY 0.25
    TORTUOSITY 0.5
    ROCK_DENSITY 2650.0 kg/m^3
    THERMAL_CHARACTERISTIC_CURVES cct_linear_resistivity
    HEAT_CAPACITY 830.0 J/kg-C
    PERMEABILITY
      PERM_ISO 1.d-12
    /
  /

  THERMAL_CHARACTERISTIC_CURVES cct_linear_resistivity
    THERMAL_CONDUCTIVITY_FUNCTION LINEAR_RESISTIVITY
      THERMAL_CONDUCTIVITY_DRY 5.5000D+0 W/m-C
      THERMAL_CONDUCTIVITY_WET 7.0000D+0 W/m-C
      #REFERENCE_TEMPERATURE 0.d0 ! default value
      LINEAR_RESISTIVITY_COEFFICIENTS 1.0d0 5.038D-3
      ANISOTROPY_RATIO_X  1.0000D+0
      ANISOTROPY_RATIO_Y  0.8000D+0
      ANISOTROPY_RATIO_Z  0.5000D+0
    END
    TEST
  END

.. _tcc-references:

References
**********
1. Somerton, W.H., J.A. Keese, and S.L. Chu (1974). Thermal behavior of unconsolidated oil sands. Society of Petroleum Engineers Journal 14(5), 513-521. https://doi.org/10.2118/4506-PA
2. Painter, S.L. (2011). Three-phase numerical model of water migration in partially frozen geological media: model formulation, validation, and applications. Computational Geosciences 15, 69–85. https://doi.org/10.1007/s10596-010-9197-z
3. Painter, S.L., and S. Karra (2014). Constitutive model for unfrozen water content in subfreezing unsaturated soils. Vadose Zone 13(4), 1-8. https://doi.org/10.2136/vzj2013.04.0071
4. Dall'Amico, M. (2010). Coupled  water  and  heat  transfer  in  permafrost modeling. Ph.D. thesis, Institute of Civil and Environmental Engineering, Universita’ degli Studi di Trento, Trento, Italy. http://eprints-phd.biblio.unitn.it/335/
5. Dall'Amico, M., S. Endrizzi, S. Gruber, and R. Rigon (2011). A robust and energy-conserving model of freezing variably-saturated soil. The Cryosphere 5(2), 469-484. https://doi.org/10.5194/tc-5-469-2011
6. TRW Environmental Safety Systems (1996). Spent nuclear fuel effective thermal conductivity report. U.S. Department of Energy, Yucca Mountain Site Characterization Project Office, Las Vegas, NV. MOL.19961202.0030. https://doi.org/10.2172/778872
7. Cheng, P., and C.-T. Hsu (1999). The effective stagnant thermal conductivity of porous media with periodic structures. Journal of Porous Media 2(1), 19-38. https://doi.org/10.1615/JPorMedia.v2.i1.20
8. Bollingerfehr, W., W. Filbert, S. Dorr, P. Herold, C. Lerch, P. Burgwinkel, F. Charlier, B. Thomauske, G. Bracke, R. Kliger (2012). Endlangerauslegung und -optimierung. GRS-281, ISBN 978-3-939355-57-1, Gesellschaft für Anlagen- und Reaktorsicherheit (GRS) gGmbH.
