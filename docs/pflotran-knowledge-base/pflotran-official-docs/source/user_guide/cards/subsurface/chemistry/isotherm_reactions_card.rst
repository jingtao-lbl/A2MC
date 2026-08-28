Back to :ref:`card-index`

Back to :ref:`chemistry-card`

Back to :ref:`sorption-card`

.. _isotherm-reactions-card:

ISOTHERM_REACTIONS
==================
Specifies parameters for a sorption reaction defined by an isotherm (e.g. 
linear, Langmuir, Freundlich).

Required Cards:
---------------

ISOTHERM_REACTIONS
 Opens the block.

<Species_Name>
 Name of primary species that sorbs.

DISTRIBUTION_COEFFICIENT <float> <string>
 The value of K\ :sub:`D` \ , where <string> defines the units of K\ :sub:`D` \.
 (Default units [kg\ :sub:`water` \ / m\ :sup:`3` :sub:`bulk`\]).

Optional Cards: 
---------------

TYPE <string>
 Type of isotherm, where the options for <string> include:
 
 - LINEAR : Linear isotherm (KD) -- 
   C\ :sub:`sorb` \ = K\ :sub:`D` \ C\ :sub:`aq`\
 - LANGMUIR : Langmuir isotherm -- 
   C\ :sub:`sorb` \ = K C\ :sub:`aq` \ b / ( 1 + K C\ :sub:`aq`\)
 - FREUNDLICH : Freundlich isotherm -- 
   C\ :sub:`sorb` \ = K\ :sub:`D` \ (C\ :sub:`aq`) :sup:`1/n`\

LANGMUIR_B <float>
 b coefficient for Langmuir isotherm.  Automatically sets the type to LANGMUIR.

FREUNDLICH_N <float>
 n exponent in Freundlich isotherm.  Automatically sets the type to FREUNDLICH.

KD_MINERAL_NAME <string>
 Name of mineral, the volume fraction of which will be used in conjunction with 
 the distribution coefficient to calculate the PFLOTRAN internal distribution 
 coefficient of kg water per cubic meter bulk. Note that the mineral volume
 fraction has no units in this case; it is solely a scaling parameter for varying
 the KD in space.

SEC_CONT_KD <float> <string>
 The value of K\ :sub:`D` \ for the secondary continuum, where <string> defines
 the units of K\ :sub:`D` \. (Default units [kg\ :sub:`water` \ / m\ :sup:`3`
 :sub:`bulk`\]).

Examples
--------
 :: 

  ISOTHERM_REACTIONS
    Tracer
      DISTRIBUTION_COEFFICIENT 0.25d3  
    /
    Tracer2
      DISTRIBUTION_COEFFICIENT 0.5d3
      FREUNDLICH_N 1.67  ! 1/n = 0.6
    /
  END

  ISOTHERM_REACTIONS
    Tracer
      !   Kd units = mL water/kg soil
      ! assuming:
      !   water_density = 1000 kg/m^3
      !   soil particle density = 2500 kg/m^3
      !   porosity = 0.25
      DISTRIBUTION_COEFFICIENT 0.133333 mL/kg
      KD_MINERAL_NAME Calcite  
    /
  END

