Back to :ref:`card-index`

Back to :ref:`chemistry-card`

Back to :ref:`reaction-sandbox-card`

.. _bioparticle-card:

BIOPARTICLE
===========
Specifies parameters for BIOPARTICLE reactions. 

Required Cards:
---------------
BIOPARTICLE
 Opens the reaction block.

 PARTICLE_NAME_AQ <string>
  Name of the species while suspended in the aqueous mobile phase.

 PARTICLE_NAME_IM <string>
  Name of the species while attached to the solid phase.

 RATE_ATTACHMENT <string>
  Defines how to calculate the attachment rate of particles. 
  Available options are CONSTANT and FILTRATION_MODEL for colloid filtration theory.

 RATE_DETACHMENT <string>
  Defines how to calculate the detachment rate of particles. 
  Currently, only a CONSTANT rate is supported.

 DECAY_AQUEOUS <string>
  Defines how to calculate the inactivation rate of particles while in the mobile phase. 
  It can be a constant rate or derived from a temperature model.

 DECAY_ADSORBED <string>
  Defines how to calculate the inactivation rate of particles while immobilized. 
  It can be a constant rate or derived from a temperature model.

Examples
--------

Chemistry block - BIOPARTICLE with constant rates
...................................................
 ::
  
  CHEMISTRY
   PRIMARY_SPECIES
    Vaq
   /
   IMMOBILE_SPECIES
    Vim
   /
   REACTION_SANDBOX
    BIOPARTICLE
     PARTICLE_NAME_AQ Vaq
     PARTICLE_NAME_IM Vim
     RATE_ATTACHMENT CONSTANT
      VALUE 1.00E-04 1/h
     /
     RATE_DETACHMENT CONSTANT
      VALUE 1.00E-04 1/h
     /
     DECAY_AQUEOUS CONSTANT
      VALUE 1.00E-04 1/h
     /
     DECAY_ADSORBED CONSTANT
      VALUE 1.00E-04 1/h
     /
    /
   /
   LOG_FORMULATION
   TRUNCATE_CONCENTRATION 1.0E-35
   DATABASE rxn_database.dat
   OUTPUT
    TOTAL
    ALL
   /
  END

Chemistry block - BIOPARTICLE with calculated rates
....................................................
 :: 

  CHEMISTRY
   PRIMARY_SPECIES
    Vaq
   /
   IMMOBILE_SPECIES
    Vim
   /
   REACTION_SANDBOX
    BIOPARTICLE
     PARTICLE_NAME_AQ Vaq
     PARTICLE_NAME_IM Vim
     RATE_ATTACHMENT FILTRATION_MODEL
      DIAMETER_COLLECTOR 2.0E-03  !m
      DIAMETER_PARTICLE  1.0E-07  !m
      HAMAKER_CONSTANT   5.0E-21  !J
      DENSITY_PARTICLE   1.1E+03  !kg/m3
      ALPHA_EFFICIENCY   1.0E-03  !-adim-
     /
     RATE_DETACHMENT CONSTANT
      VALUE  1.00E-07 1/s
     /
     DECAY_AQUEOUS TEMPERATURE_MODEL
      TREF    4.0
      ZT      29.1
      N       2.0
      LOGDREF 2.3
     /
     DECAY_ADSORBED TEMPERATURE_MODEL
      TREF    4.0
      ZT      29.1
      N       2.0
      LOGDREF 2.3
     /
    /
   /
   LOG_FORMULATION
   TRUNCATE_CONCENTRATION 1.0E-35
   DATABASE rxn_database.dat
   OUTPUT
    TOTAL
    ALL
   /
  END


**Notes:**
 * FILTRATION_MODEL units are fixed to SI
 * TEMPERATURE_MODEL uses the formulation given in Guillier et al. (2020) `[DOI: 10.1128/AEM.01244-20] <https://aem.asm.org/content/86/18/e01244-20>`_.

