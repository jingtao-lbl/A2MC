Back to :ref:`card-index`

Back to :ref:`chemistry-card`

Back to :ref:`reaction-sandbox-card`

.. _clm-cn-card:

CLM-CN
======
Specifies parameters for CLM-CN 4.0 reactions.

Required Cards:
---------------
CLM-CN
 Opens the reaction block.

POOLS
 Specifies a list of litter and soil organic matter (SOM) pools to be considered 
 as upstream/downstream carbon/nitrogen pools in CLM-CN reactions.
 ::

   POOLS
     SOM1 12.
     SOM2 12.
     Lit1
     Lit2
   /

 Note:
  * SOM pools listed must be followed by a floating point C/N ratio [g/g] and 
    the SOM pool must be listed as an immobile species in the CHEMISTRY section.
  * Litter pools listed do not provide a C/N ratio as it is variable. Two 
    immobile species must be defined for each litter pool where the name of the 
    species is the name of the pool followed by C and N for carbon and nitrogen, 
    respectively (e.g. Lit1 -> Lit1C and Lit1N).

/

REACTION
 Opens a block that defines a new reaction for decomposition of plant biomass 
 and SOM.

 UPSTREAM_POOL <string>
  Name of the upstream pool as listed in POOLS.

 DOWNSTREAM_POOL <string>
  Name of the downstream pool as listed in POOLS.

 TURNOVER_TIME <float> <optional string>
  The turnover time (e.g. inverse of rate constant) in seconds unless units 
  (e.g. s, min, h, d, w, mo, y) are provided as the optional string.

 RATE_CONSTANT <float> <optional string>
  The rate constant in 1/s unless units (e.g. 1/s, 1/min, 1/h, 1/d,  1/y) are 
  provided as the optional string.

 **Note: TURNOVER_TIME and RATE_CONSTANT may not be present at the same time.**

 RESPIRATION_FRACTION <float>
  Defines the fraction of carbon mineralized.

 N_INHIBITION <float>
  Inhibition constant defines a threshold for nitrogen update. A monod 
  expression is implemented to inhibit nitrogen uptake at concentrations well 
  below N_INHIBITION when nitrogen is a reactant.

/

Examples
--------

Immobile species block
......................
 ::

  IMMOBILE_SPECIES
    N
    C
    SOM1
    SOM2
    SOM3
    SOM4
    Lit1C
    Lit2C
    Lit3C
    Lit1N
    Lit2N
    Lit3N
  /

Reaction sandbox block
......................
 :: 

  REACTION_SANDBOX
    CLM-CN
      POOLS
        SOM1 12.d0
        SOM2 12.d0
        SOM3 10.d0
        SOM4 10.d0
        Lit1
        Lit2
        Lit3
      /
      REACTION
        UPSTREAM_POOL Lit1
        DOWNSTREAM_POOL SOM1
        TURNOVER_TIME 20. h
        RESPIRATION_FRACTION 0.39d0
        N_INHIBITION 1.d-10
      /
      REACTION
        UPSTREAM_POOL Lit2
        DOWNSTREAM_POOL SOM2
        TURNOVER_TIME 14. d
        RESPIRATION_FRACTION 0.55
        N_INHIBITION 1.d-10
      /
      REACTION
        UPSTREAM_POOL Lit3
        DOWNSTREAM_POOL SOM3
        TURNOVER_TIME 71. d
        RESPIRATION_FRACTION 0.29d0
        N_INHIBITION 1.d-10
      /
      REACTION
        UPSTREAM_POOL SOM1
        DOWNSTREAM_POOL SOM2
        TURNOVER_TIME 14. d
        RESPIRATION_FRACTION 0.28d0
        N_INHIBITION 1.d-10
      /
      REACTION
        UPSTREAM_POOL SOM2
        DOWNSTREAM_POOL SOM3
        TURNOVER_TIME 71. d
        RESPIRATION_FRACTION 0.46d0
        N_INHIBITION 1.d-10
      /
      REACTION
        UPSTREAM_POOL SOM3
        DOWNSTREAM_POOL SOM4
        TURNOVER_TIME 2. y
        RESPIRATION_FRACTION 0.55d0
        N_INHIBITION 1.d-10
      /
      REACTION
        UPSTREAM_POOL SOM4
        TURNOVER_TIME 27.4 y
        RESPIRATION_FRACTION 1.d0
        N_INHIBITION 1.d-10
      /
    /
  /

Species constraint block
........................
 :: 

  CONSTRAINT initial
    ...
    IMMOBILE
      N     1.d-6
      C     1.d-20
      SOM1  1.d-20
      SOM2  1.d-20
      SOM3  1.d-20
      SOM4  1.d-20
      Lit1C 0.1852d-3
      Lit2C 0.4578d-3
      Lit3C 0.2662d-3
      Lit1N 0.00508954d-3
      Lit2N 0.01258096d-3
      Lit3N 0.00731553d-3
    /
  /

