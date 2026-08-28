Back to :ref:`card-index`

Back to :ref:`chemistry-card`

.. _sorption-card:

SORPTION
========
Specifies parameters for sorption reactions.

Required Cards:
---------------

SORPTION
 Opens the sorption reaction block.

Optional Cards:
---------------

..
 DYNAMIC_KD_REACTIONS
  To be documented.

:ref:`ion-exchange-rxn-card`
 Sorption defined through ion exchange reactions.

:ref:`isotherm-reactions-card`
 Sorption reactions defined by isotherms (e.g. linear, Langmuir, Freundlich).

:ref:`surface-complexation-rxn-card`
 Opens surface complexation reaction block.

.. 
 Cards to remain undocumented at this point.
 JUMPSTART_KINETIC_SORPTION
 NO_CHECKPOINT_KINETIC_SORPTION
 NO_RESTART_KINETIC_SORPTION


Examples
--------

 :: 

  SORPTION
    ISOTHERM_REACTIONS
      Tracer
        DISTRIBUTION_COEFFICIENT 0.25d3  
      /
      Tracer2
        DISTRIBUTION_COEFFICIENT 0.5d3
        FREUNDLICH_N 1.67  ! 1/n = 0.6
      /
    /
    SURFACE_COMPLEXATION_RXN
      EQUILIBRIUM
      MINERAL Kaolinite
      SITE >FeOH 0.00636
      COMPLEXES
        >FeOHUO3
        >FeOHUO2++
      /
    /
    ION_EXCHANGE_RXN
      MINERAL Calcite
      CEC 1.e-1
      CATIONS
        Ca++ 1.e-4
        Na+   1.d0
      /
    /
  END
