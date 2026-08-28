Back to :ref:`card-index`

.. _eos-card:

EOS
===
Defines an equation of state for a simulated fluid. 

Required Cards:
---------------
EOS <string>
    Specifies the fluid for which the EOS applies [WATER, GAS].

Optional Cards:
---------------

WATER Phase
***********

DENSITY <string> <optional parameters>
  
 DENSITY CONSTANT <float>
  Units of density should be in kg/m^3.
 
 DENSITY EXPONENTIAL <float> <float> <float> (ref. density [rho0], ref. pressure [p0], compressibility)
  Exponential function: rho0 * exp(compressibility*(pressure - p0))

 DENSITY IF97
  Liquid water density EOS based on International Association for the Properties of Water and Steam Standard IF97

 STEAM_DENSITY IF97
  Superheated vapor density EOS based on International Association for the Properties of Water and Steam Standard IF97

 DENSITY DEFAULT
  Default water EOS based on International Formulation Committee of the Sixth International Conference on Properties of Steam (1967).
  Density is calculated as a function of temperature and pressure.

ENTHALPY <string> <optional parameters>
  
 ENTHALPY CONSTANT <float>
  Units of enthalpy should be in J/kmol.

 ENTHALPY IF97
  Liquid water enthalpy EOS based on International Association for the Properties of Water and Steam Standard IF97

 STEAM_ENTHALPY IF97
  Superheated vapor enthalpy EOS based on International Association for the Properties of Water and Steam Standard IF97

 ENTHALPY DEFAULT
  Default water EOS based on International Formulation Committee of the Sixth International Conference on Properties of Steam (1967).
  Enthalpy is calculated as a function of temperature and pressure.

VISCOSITY <string> <optional parameters>
  
 VISCOSITY CONSTANT <float>
  Units of viscosity should be in Pa-s (dynamic viscosity).

 VISCOSITY DEFAULT
  Default water EOS based on International Formulation Committee of the Sixth International Conference on Properties of Steam (1967).
  Viscosity is calculated as a function of temperature, pressure, and saturation pressure.

TEST <float> <float> <float> <float> <int> <int> <string> <string>
 Tests the equation of state (currently water density only).  The order of the arguments are temperature low [C], temperature high [C], pressure low [Pa], pressure high [Pa], number of temperatures, number of pressures, temperature distribution [uniform,log], pressure distribution [uniform,log]


GAS Phase
***********

DENSITY <string> <optional parameters>
  
 DENSITY CONSTANT <float>
  Units of density should be in kmol/m^3.
 
 DENSITY IDEAL
  Calculate the gas density using the ideal gas law.

 DENSITY DEFAULT
  Calculate the gas density using the ideal gas law.
  
 DENSITY RKS
  Calculate the gas density using the Redlich-Kwong-Soave (RKS) equation of state. 
  Currently, the gas is assumed to behave as a single-component gas (mixture properties are not supported). 
  If none of the following optional subcards are specified, default values for hydrogen gas are employed. 
  Either the long or short keywords can be input.
  
    HYDROGEN | NON-HYDROGEN
      Use a hydrogen-specific, modified correlation (Graboski) to calculate the alpha parameter.
      
    CRITICAL_TEMPERATURE, TC <float>
      Units kelvin.
    
    CRITICAL_PRESSURE, PC <float>
      Units Pa.
    
    ACENTRIC_FACTOR, AC <float>
    
    OMEGAA, A <float>
    
    OMEGAB, B <float>
    

ENTHALPY <string> <optional parameters>
  
 ENTHALPY CONSTANT <float>
  Units of enthalpy should be in J/kmol.
  
 ENTHALPY IDEAL
  Calculate enthalpy using the ideal gas law.

 ENTHALPY DEFAULT
  Calculate enthalpy using the ideal gas law.

VISCOSITY <string> <optional parameters>
  
 VISCOSITY CONSTANT <float>
  Units of viscosity should be in Pa-s (dynamic viscosity).

 VISCOSITY DEFAULT
  Calculate gas viscosity using correlations for water-vapor/air mixutures (Hirschfelder et al.)
  Viscosity is calculated as a function of temperature, pressure, and saturation pressure.

HENRYS_CONSTANT <string> <optional parameters>
  HENRYS_CONSTANT is currently only used in GENERAL mode.
  
  HENRYS_CONSTANT CONSTANT  <float>
    Set Henry's constant (the solubility of gas in liquid) to a fixed value. 
    The units for Henry's constant are [Pa].
    
  HENRYS_CONSTANT DEFAULT
    Calculate Henry's constant using correlations for water-vapor/air mixutures (Fernandez-Prini et al.).
    Henry's constant is calculated as a function of temperature and saturation pressure.

FORMULA_WEIGHT <float> 
  Set the molecular weight for the gas component. Units g/mol.

TEST <float> <float> <float> <float> <int> <int> <string> <string>
 Tests the equation of state (currently gas density only).  The order of the arguments are temperature low [C], temperature high [C], pressure low [Pa], pressure high [Pa], number of temperatures, number of pressures, temperature distribution [uniform,log], pressure distribution [uniform,log]


Examples
--------
 ::

  EOS WATER
    DENSITY EXPONENTIAL 997.16d0 101325.d0 1.d-8
    VISCOSITY CONSTANT 8.904156d-4
  END

 ::

  EOS WATER
    DENSITY CONSTANT 997.16d0 kg/m^3
    ENTHALPY CONSTANT 1.8890d0 J/kmol
    VISCOSITY CONSTANT 8.904156d-4 Pa-s
    TEST 1.d-2 500.d0 1.d-2 5.d8 100 100 uniform uniform
  END

 ::

  EOS GAS
    DENSITY IDEAL
    VISCOSITY CONSTANT 9.0829d-6
    HENRYS_CONSTANT CONSTANT 1.d10
  END

 ::

  EOS GAS
    DENSITY RKS
      HYDROGEN
      TC 41.67
      PC 2.1029d6
      AC 0.00
      A 0.42747
      B 0.08664
    /
    VISCOSITY CONSTANT 9.0829d-6
    FORMULA_WEIGHT 2.01588D0
  END
  
