Back to :ref:`card-index`

.. _material-transform-card:

MATERIAL_TRANSFORM_GENERAL
##########################
The Material Transform Process Model is documented here.

This option specifies the material transform process model, which is a child of flow and a peer of transport. Under the :ref:`simulation-card` block, the process model is included by adding the MATERIAL_TRANSFORM block:

 ::

   SIMULATION
     SIMULATION_TYPE SUBSURFACE
     PROCESS_MODELS
       SUBSURFACE_FLOW flow
         MODE GENERAL
       /
       SUBSURFACE_TRANSPORT transport
         MODE GIRT
       /
       MATERIAL_TRANSFORM <name_string>
       /
     /
   END

where <name_string> is a user-defined name for the process model. There are currently no additional options for this block. Functionality is currently available for problems utilizing flow modes (such as :ref:`general-card`, :ref:`th-card`, and :ref:`richards-card`) and/or reactive transport with :ref:`ufd-decay-card`.

The details of the process model are included in the MATERIAL_TRANSFORM_GENERAL block, which lists several MATERIAL_TRANSFORM objects that can be associated with a :ref:`material-property-card`.

Supported models that can be included in a MATERIAL_TRANSFORM object include the following:
  * :ref:`mtf-ilt`

.. _mtf-ilt:

ILLITIZATION
============
The illitization function allows for a time- and temperature-dependent change from smectite to illite to be evaluated during the simulation, which in turn can be used to impart a commensurate change in permeability and/or sorption.

.. _mtf-ilt-required-blocks:

Required Blocks and Cards
*************************
ILLITIZATION_FUNCTION <string>
  Opens an illitization block, where <string> indicates the type of illitization model to be employed.

  Supported ILLITIZATION_FUNCTIONs (along with their required cards):

  .. _mtf-ilt-default-input:

  * DEFAULT (HUANG)

    + SMECTITE_INITIAL
    + THRESHOLD_TEMPERATURE
    + SHIFT_PERM
    + SHIFT_KD
    + EA
    + FREQ
    + K_CONC
  
  .. _mtf-ilt-general-input:
  
  * GENERAL (CUADROS_AND_LINARES)

    + SMECTITE_INITIAL
    + SMECTITE_EXPONENT
    + THRESHOLD_TEMPERATURE
    + SHIFT_PERM
    + SHIFT_KD
    + EA
    + FREQ
    + K_CONC
    + K_EXP


.. _mtf-ilt-parameter-definitions:

Illitization Parameter Definitions
**********************************

In the DEFAULT model (ref. 1), for a given time step :math:`i+1`, the time rate of change of smectite :math:`\left(\frac{df_{S}}{dt}\right)` into illite is based on the smectite fraction :math:`f_{S,i}` and potassium cation concentration :math:`[K^{+}]`. It is defined as follows:

:math:`\left.-\frac{df_{S}}{dt}\right|^{i+1}=\left\{{\begin{array}{cc} [K^{+}]\cdot (f_{S}^{i})^{2}\cdot A\exp{\left(-\frac{E_{a}}{\mathcal{R}T^{i+1}}\right)} & T^{i+1}\geq T_{th} \\ 0 & T^{i+1}<T_{th} \\ \end{array} } \right.` [1/s]

where :math:`A` is the frequency term, :math:`E_{a}` is the activation energy, :math:`\mathcal{R}` is the ideal gas constant, :math:`T^{i+1}` is the temperature in Kelvin, and :math:`T_{th}` is the threshold temperature. The value of :math:`[K^{+}]` is currently implemented as a constant.

The time-integrated smectite fraction is evaluated as: 

:math:`f_{S}^{i+1} = \frac{f_{S}^{i}}{1-[K^{+}]\cdot A\exp{\left(-\frac{E_{a}}{\mathcal{R}T^{i+1}}\right)}\cdot (t^{i+1}-t^{i})\cdot f_{S}^{i}}`

The illite fraction is defined as the complement of the smectite fraction:

:math:`f_{I}^{i+1} = 1 - f_{S}^{i+1}`

A scale factor :math:`F` is defined that ranges from 0 to 1 and is based on the relative change in the fraction of illite:

:math:`F^{i+1}= \frac{f_{I}^{i+1}-f_{I}^{0}}{f_{S}^{0}}`

This is used to modify the permeability and/or soprtion based on a user-specified function (see SHIFT_PERM and SHIFT_KD below). 

In the GENERAL model (ref. 2), the time rate of change of smectite is defined with the potassium concentration raised to exponent :math:`m` and the smectite fraction raised to exponent :math:`n`, where the temperature-dependent Arrhenius term is simplified as :math:`k(T)`:

:math:`\left.-\frac{df_{S}}{dt}\right|^{i+1}=\left\{{\begin{array}{cc} [K^{+}]^{m}\cdot (f_{S}^{i})^{n}\cdot k(T) & T^{i+1}\geq T_{th} \\ 0 & T^{i+1}<T_{th} \\ \end{array} } \right.` [1/s]

The frequency term :math:`A` in :math:`k(T)` must be defined in units that correspond to the choice of :math:`m` and :math:`n`. The time-integrated smectite fraction is evaluated based on the choice of :math:`n`:

:math:`f_{S}^{i+1}=\left\{{\begin{array}{cc} \left\{[K^{+}]^{m}\cdot k(T)\cdot (n-1)(t^{i+1}-t^{i})+(f_{S}^{i})^{1-n}) \right\}^{\frac{1}{1-n}} & n>1 \\ f_{S}^{i}\cdot \exp{\left\{-k(T)\cdot[K^{+}]^{m}\cdot(t^{i+1}-t^{i})\right\}} & n=1 \\ \end{array} } \right.`

SMECTITE_INITIAL <float>
 The initial fraction of smectite in the material relative to illite, :math:`f_{S}^{0}` (default of 1.0).

SMECTITE_EXP <float>
 The exponent of the smectite fraction, :math:`n`.

THRESHOLD_TEMPERATURE <float>
 The temperature in Celsius at and above which the illitization process occurs, :math:`T_{th}` (default of 0°C).

SHIFT_PERM <string> <float> (optional)
 Factors are provided to modify the original permeability tensor :math:`k_{j}^{0}` based on changes to the smectite/illite composition. This entry consists of the function type <string> and the functional parameters :math:`C_{k}` <float> (see below). Simulations utilizing this feature must have an active flow mode.
   
   DEFAULT/LINEAR - :math:`C_{k,1}`

     :math:`C_{k,1}` is the factor applied to the relative change in the illite fraction :math:`(F)` that is used to isotropically modify the original permeability. The change in a given permeability component :math:`k_{j}^{i+1}` at time step :math:`i+1` as a result of illitization is computed as:

     :math:`k_{j}^{i+1}=k_{j}^{0}\left(1+C_{k,1}\cdot F^{i+1} \right)`

     This suggests that when all of the original smectite is transformed to illite, the permeability has been enhanced by a factor of :math:`1+ C_{k,1}`.
   
   QUADRATIC - :math:`C_{k,1}, C_{k,2}`
   
      :math:`k_{j}^{i+1} = k_{j}^{0}\left[1 + C_{k,1}\cdot F^{i+1} + C_{k,2}\cdot (F^{i+1})^{2}\right]`
   
   POWER - :math:`C_{k,1}, C_{k,2}`
   
      :math:`k_{j}^{i+1} = k_{j}^{0}\left[1 + C_{k,1}\cdot(F^{i+1})^{C_{k,2}}\right]`
   
   EXPONENTIAL - :math:`C_{k,1}`
   
      :math:`k_{j}^{i+1} = k_{j}^{0}\exp{\left(C_{k,1}\cdot F^{i+1}\right)}`

SHIFT_KD (optional)
 For specified elements, factors are provided to modify original sorption distribution coefficients, :math:`K_{d}^{0}`, based on changes to the smectite/illite composition. In this sub-block, one list entry consists of the element :math:`e` <string>, the function type <string>, and the functional parameters :math:`C` <float> (see below). Simulations utilizing this feature must have an active transport mode and elements listed *must* be present in the :ref:`ufd-decay-card` process model.
   
   DEFAULT/LINEAR - :math:`C_{1}`
   
     :math:`K_{d,e}^{i+1} = K_{d,e}^{0}\left(1 + C_{1,e}\cdot F^{i+1}\right)`
   
   QUADRATIC - :math:`C_{1}, C_{2}`
   
     :math:`K_{d,e}^{i+1} = K_{d,e}^{0}\left[1 + C_{1,e}\cdot F^{i+1} + C_{2,e}\cdot (F^{i+1})^{2}\right]`
   
   POWER - :math:`C_{1}, C_{2}`
   
     :math:`K_{d,e}^{i+1} = K_{d,e}^{0}\left[1 + C_{1,e}\cdot(F^{i+1})^{C_{2,e}}\right]`
   
   EXPONENTIAL - :math:`C_{1}`
   
     :math:`K_{d,e}^{i+1} = K_{d,e}^{0}\exp{\left(C_{1,e}\cdot F^{i+1}\right)}`

EA <float>
  The activation energy in the temperature-dependent Arrhenius term, :math:`E_{a}` [J/mol].

FREQ <float>
  The frequency term, or coefficient used to scale the temperature-dependent Arrhenius term, :math:`A` [L/mol-s].

K_CONC <float>
  The initial concentration of potassium cation in the material, :math:`[K^{+}]` [M].

K_EXP <float>
  The exponent of the potassium cation concentration, :math:`m`.


Optional Blocks and Cards
*************************

.. _mtf-ilt-test:

Test Illitization Model
-----------------------
TEST
 Including this keyword will produce output (.dat file) for an illitization model that includes:
  (a) initial smectite fraction :math:`(f_{S}^{0})`,
  (b) temperature :math:`(T)`,
  (c) time :math:`(t)`,
  (d) illite fraction :math:`(f_{I})`,
  (e) :math:`\frac{df_{I}}{dT}`,
  (f) scale factor :math:`(F)`

Examples
========

.. _mtf-ilt-example-general:

Material with transform named "mtf_bentonite" containing illitization model
***************************************************************************
 ::

   #================================= subsurface ================================

   ...

   MATERIAL_PROPERTY buffer
     ID 1
     POROSITY 3.5d-1
     TORTUOSITY_FUNCTION_OF_POROSITY 1.4d+0
     SOIL_COMPRESSIBILITY 1.6d-8
     SOIL_COMPRESSIBILITY_FUNCTION LEIJNSE
     SOIL_REFERENCE_PRESSURE 1.01325d+5
     ROCK_DENSITY  2.7d+3
     HEAT_CAPACITY 8.3d+2
     CHARACTERISTIC_CURVES cc_bentonite
     THERMAL_CHARACTERISTIC_CURVES cct_bentonite
     MATERIAL_TRANSFORM mtf_bentonite
     PERMEABILITY
       PERM_ISO  1.0d-20
     /
   /

  ...

  #=========================== pm material transform ============================

  MATERIAL_TRANSFORM_GENERAL

    MATERIAL_TRANSFORM mtf_bentonite
      ILLITIZATION
        ILLITIZATION_FUNCTION DEFAULT
          THRESHOLD_TEMPERATURE 2.50000d+1 C
          EA                    1.17152d+5 J/mol
          FREQ                  8.08000d+4 L/mol-s
          K_CONC                2.16000d-3 M
          SMECTITE_INITIAL      0.95000d+0
          SHIFT_PERM   DEFAULT  9.90000d+2
          SHIFT_KD
            Sr  QUADRATIC   -2.50000d-1 -2.50000d-1 # Sr must be listed in UFD Decay
            Tc  EXPONENTIAL -6.94000d-1             # Tc must be listed in UFD Decay
            Cs  LINEAR      -5.00000d-1             # Cs must be listed in UFD Decay
            Np  POWER       -5.00000d-1  5.00000d-1 # Np must be listed in UFD Decay
          /
        END
        TEST
      END
    END

  END # MATERIAL_TRANSFORM_GENERAL


.. _mtf-ilt-references:

References
==========
1. Huang, W.-L., J. M. Longo, and D. R. Pevear (1993). An experimentally derived kinetic model for smectite-to-illite conversion and its use as a geothermometer. Clays and Clay Minerals 41(2), 162-177. https://doi.org/10.1346/CCMN.1993.0410205

2. Cuadros, J., and Linares, J. (1996). Experimental kinetic study of the smectite-to-illite transformation. Geochimica et Cosmochimica Acta 60(3), 439-453. https://doi.org/10.1016/0016-7037(95)00407-6
