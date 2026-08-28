Back to :ref:`card-index`

.. _nuclear-waste-chemistry-card:

NUCLEAR_WASTE_CHEMISTRY
=======================
Defines conditions for a transport simulation using the 
NUCLEAR_WASTE_TRANSPORT mode. Note: Do not also use the CHEMISTRY card, which
is only used for SUBSURFACE_TRANSPORT (reactive transport) mode. 

Required Cards:
---------------
SPECIES 
  Opens a SPECIES block. Must have a matching ``END``. There should be one
  SPECIES block for each transported species in the simulation.

 ::
 
   SPECIES
     . . . 
   END

Keywords
~~~~~~~~
   
Within the SPECIES block, **the following keywords are required:**
 
NAME <string> 
  Specifies the name of a transported species.
 
 ::
 
   SPECIES
     NAME  AM241L
     . . . 
   END

SOLUBILITY <double> 
  Specifies the solubility limit of a transported species in mol/m^3-liq.
 
 ::
 
   SPECIES
     . . .
     SOLUBILITY 1.72615583236094d-05    # [mol/m^3-liq]
     . . . 
   END

PRECIPITATE_MOLAR_DENSITY <double> 
  Specifies the precipitated molar density of a transported species in 
  mol/m^3-mineral.
 
 ::
 
   SPECIES
     . . .
     PRECIP_MOLAR_DENSITY 38.61d3 # [mol/m^3-mnrl] (quartz example)
     . . . 
   END

ELEMENTAL_KD <double> 
  Specifies the elemental Kd value of a transported species in 
  m^3-water/m^3-bulk.
 
 ::
 
   SPECIES
     . . .
     ELEMENTAL_KD 0.0d0 # [m^3-water/m^3-bulk]
     . . . 
   END

An example of a full SPECIES block:

 ::
 
   SPECIES
     NAME                      TH230L
     SOLUBILITY                1.10410404254448d-06   # [mol/m^3-liq]
     PRECIPITATE_MOLAR_DENSITY 38.61d3                # [mol/m^3-mnrl] (quartz example)
     ELEMENTAL_KD              0.0d0                  # [m^3-water/m^3-bulk]
   /


Optional Cards:
---------------
RADIOACTIVE_DECAY
  Opens a RADIOACTIVE_DECAY block. Must have a matching ``END``. There should 
  only be one RADIOACTIVE_DECAY block. This block lists all radioactive species
  and their daughter decay products. If there are no radioactive species,
  this block can be omitted.

 ::
 
   RADIOACTIVE_DECAY
     . . . 
   END

  Keywords
  ~~~~~~~~
     
  Within the RADIOACTIVE_DECAY block, **the following keywords are required:**
   
  <double> <string> -> <string> 
    Indicates the decay rate of a radioactive transported species, and its daughter
    product, if there is one. This line should be repeated for each radioactive
    species. If a daughter product does not exist, do not indicate ``->``. If a
    daughter product does exist, but is not radioactive, that daughter must also be
    included in this block and assigned a decay rate of 0. The decay rate unit is
    1/second. Each species listed here must also be assigned its own SPECIES block.

  Examples:
 
   ::
 
     RADIOACTIVE_DECAY
     # [1/sec]
       5.081724d-11  AM241L
       9.127564d-13  PU239L
       2.503240d-10  PU238L -> U234L
       8.983245d-14  U234L -> TH230L
       2.852458d-13  TH230L      
     /

   ::

     RADIOACTIVE_DECAY
     # [1/sec]
       5.081724d-11  AM241L
       9.127564d-13  PU239L
       2.503240d-10  PU238L -> U234L
       8.983245d-14  U234L -> daugh
       0.0d0         daugh      
     /


OUTPUT
  Opens an OUTPUT block. Must have a matching ``END``. This block indicates
  what output is desired. One may specify the following options within the
  OUTPUT block: ALL_SPECIES, ALL_CONCENTRATIONS, TOTAL_BULK_CONCENTRATION,
  AQUEOUS_CONCENTRATION, MINERAL_CONCENTRATION, SORBED_CONCENTRATION, and
  MINERAL_VOLUME_FRACTION.		

  The keyword ALL_CONCENTRATIONS will print all of the concentration output,
  e.g., it is the same as including: TOTAL_BULK_CONCENTRATION,
  AQUEOUS_CONCENTRATION, MINERAL_CONCENTRATION, and SORBED_CONCENTRATION.

  By default, all output is suppressed, unless the OUTPUT block is included.
  Currently, ALL_SPECIES is implied.

  Examples:

 ::

   OUTPUT
     ALL_SPECIES
     ALL_CONCENTRATIONS
     MINERAL_VOLUME_FRACTION
   /

 ::

   OUTPUT
     ALL_SPECIES
     AQUEOUS_CONCENTRATION
     TOTAL_BULK_CONCENTRATION
   /



Examples
--------
 ::

  NUCLEAR_WASTE_CHEMISTRY

    SPECIES
      NAME                      AM241L
      SOLUBILITY                3.08531847680638d-03    # [mol/m^3-liq]
      PRECIPITATE_MOLAR_DENSITY 38.61d3                 # [mol/m^3-mnrl] (quartz example)
      ELEMENTAL_KD              0.0d0                   # [m^3-water/m^3-bulk]
    /
  
    SPECIES
      NAME                      PU239L
      SOLUBILITY                5.94620667361208d-03   # [mol/m^3-liq]
      PRECIPITATE_MOLAR_DENSITY 38.61d3                # [mol/m^3-mnrl] (quartz example)
      ELEMENTAL_KD              0.0d0                  # [m^3-water/m^3-bulk]
    /
  
    SPECIES
      NAME                      PU238L
      SOLUBILITY                1.72615583236094d-05    # [mol/m^3-liq]
      PRECIPITATE_MOLAR_DENSITY 38.61d3                 # [mol/m^3-mnrl] (quartz example)
      ELEMENTAL_KD              0.0d0                   # [m^3-water/m^3-bulk]
    /
  
    SPECIES
      NAME                      U234L
      SOLUBILITY                3.92771529575587d-04   # [mol/m^3-liq]
      PRECIPITATE_MOLAR_DENSITY 38.61d3                # [mol/m^3-mnrl] (quartz example)
      ELEMENTAL_KD              0.0d0                  # [m^3-water/m^3-bulk]
    /
  
    SPECIES
      NAME                      TH230L
      SOLUBILITY                1.10410404254448d-06   # [mol/m^3-liq]
      PRECIPITATE_MOLAR_DENSITY 38.61d3                # [mol/m^3-mnrl] (quartz example)
      ELEMENTAL_KD              0.0d0                  # [m^3-water/m^3-bulk]
    /
  
    RADIOACTIVE_DECAY
    # [1/sec]
      5.081724d-11  AM241L
      9.127564d-13  PU239L
      2.503240d-10  PU238L -> U234L
      8.983245d-14  U234L -> TH230L
      2.852458d-13  TH230L      
    /                       
  
    OUTPUT
      ALL_SPECIES
      ALL_CONCENTRATIONS
      MINERAL_VOLUME_FRACTION
    /
  
  END
  
