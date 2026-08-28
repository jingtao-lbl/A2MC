Back to :ref:`card-index`

Back to :ref:`chemistry-card`

.. _reaction-sandbox-card:

REACTION_SANDBOX
================
Specifies parameters for user-defined reactions.

Required Cards:
---------------

REACTION_SANDBOX
 Opens the reaction sandbox block.

Optional Cards:
---------------

:ref:`clm-cn-card`
 Block for specifying CLM-CN reaction parameters
:ref:`bioparticle-card`
 Block for specifying BIOPARTICLE transport using kinetic attachment rates from colloid filtration theory and decay rates from temperature models.


Examples
--------

:: 

  REACTION_SANDBOX
    CLM-CN
      POOLS
        SOM1 12.d0
        Lit1
      /
      REACTION
        UPSTREAM_POOL Lit1
        DOWNSTREAM_POOL SOM1
        TURNOVER_TIME 20. h
        RESPIRATION_FRACTION 0.39d0
        N_INHIBITION 1.d-10
      /
    /
  /


