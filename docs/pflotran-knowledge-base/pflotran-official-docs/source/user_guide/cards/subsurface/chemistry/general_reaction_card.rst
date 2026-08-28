Back to :ref:`card-index`

Back to :ref:`chemistry-card`

.. _general-reaction-card:

GENERAL_REACTION
================
Specifies parameters for general forward/reverse kinetic reaction.

Required Cards:
---------------
REACTION <string>
 Reaction equation. The forward rate is applied to the reaction quotient of 
 species on the left side of the reaction. The reverse or backward rate is 
 applied to the right side.

Optional Cards:
---------------
FORWARD_RATE <float>
 Rate constant for n\ :sup:`th`\ -order forward reaction 
 [kg-water\ :sup:`(n-1)`\ /mol\ :sup:`(n-1)` \-sec]

BACKWARD_RATE <float>
 Rate constant for n\ :sup:`th`\ -order reverse reaction 
 [kg-water\ :sup:`(n-1)`\ /mol\ :sup:`(n-1)` \-sec]

Examples:
---------

 ::

  GENERAL_REACTION
    REACTION Tracer <-> Tracer2
    FORWARD_RATE 1.7584d-7 ! half life at 0.125 y
    BACKWARD_RATE 0.d0
  /

 ::

  CHEMISTRY
    PRIMARY_SPECIES
      A(aq)
      B(aq)
      C(aq)
    /
    ...
    GENERAL_REACTION
      REACTION A(aq) <-> B(aq)
      ! Calculating forward rate from half-life
      ! forward rate = -ln(0.5) / half-life [1/sec]
      FORWARD_RATE 1.75836d-9  ! 1/s  half life = 12.5 yrs
      BACKWARD_RATE 0.d0
    /
    GENERAL_REACTION
      REACTION B(aq) <-> C(aq)
      FORWARD_RATE 8.7918d-10  ! 1/s  half life = 25. yrs
      BACKWARD_RATE 0.d0
    /
    GENERAL_REACTION
      ! Note that C(aq) simply decays with no daugher products
      REACTION C(aq) <->
      FORWARD_RATE 4.3959d-9  ! 1/s  half life = 5. yrs
      BACKWARD_RATE 0.d0
    /
    ...
  /
    
