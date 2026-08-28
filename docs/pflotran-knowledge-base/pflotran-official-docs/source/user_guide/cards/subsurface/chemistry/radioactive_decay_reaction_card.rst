Back to :ref:`card-index`

Back to :ref:`chemistry-card`

.. _radioactive-decay-reaction-card:

RADIOACTIVE_DECAY_REACTION
==========================
Specifies parameters for radioactive decay reaction.  This reaction differs 
from the GENERAL_REACTION in that only one reactant species may be specified 
with a unit stoichiometry (i.e. the rate is always first order) and the reactant 
species is decayed in both the aqueous and sorbed phases.

Required Cards:
---------------
REACTION <string>
 Reaction equation.  Only one reactant species may be listed on the left side of 
 the equation (i.e. or on the right side with a negative stoichiometry). The 
 reactant's stoichiometry is fixed at 1.0. The forward rate is applied to that 
 one species as a first order rate constant.  Multiple species are 
 supported as daughter products on the right hand side and stoichiometries 
 can be specified.

RATE_CONSTANT or HALF_LIFE (but not both):

  RATE_CONSTANT <float> <optional units_string>
    Rate constant for 1st-order decay reaction [1/sec, default units].  
    The rate constant may be calculated from -ln(0.5) / half-life. 
    (default units [1/sec])

  HALF_LIFE <float> <optional units_string>
    Half life of species. (default units [sec])

Examples:
---------

 ::

  RADIOACTIVE_DECAY_REACTION
    REACTION Tracer <-> Tracer2
    RATE_CONSTANT 1.7584d-7 ! half life at 0.125 y
  /

 ::

  CHEMISTRY
    PRIMARY_SPECIES
      A(aq)
      B(aq)
      C(aq)
    /
    ...
    RADIOACTIVE_DECAY_REACTION
      REACTION A(aq) <-> B(aq)
      ! Calculating forward rate from half-life
      ! rate = -ln(0.5) / half-life [1/sec]
      RATE_CONSTANT 1.75836d-9  ! 1/s  half life = 12.5 yrs
    /
    RADIOACTIVE_DECAY_REACTION
      REACTION B(aq) <-> C(aq)
      RATE_CONSTANT 8.7918d-10  ! 1/s  half life = 25. yrs
    /
    RADIOACTIVE_DECAY_REACTION
      ! Note that C(aq) simply decays with no daughter products
      REACTION C(aq) <->
      HALF_LIFE 5. y
    /
    ...
  /
