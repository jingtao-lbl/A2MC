Back to :ref:`card-index`

Back to :ref:`chemistry-card`

.. _override-mineral-mass-action-card:

OVERRIDE_MINERAL_MASS_ACTION
============================

Allows the user to override species and stoichiometries specified 
in the database with a custom formulation. This enables the use of a subset
of species when calculating the mineral saturation index and affinity factor.
One can also override the log Ks specified in the database.

Required Cards:
---------------

OVERRIDE_MINERAL_MASS_ACTION
 Opens the block.

<string>
  Specifies mineral name.

Optional Cards:
---------------

REACTION <string>
 String of characters defining the new mass action equation.

LOGK <float 1> ... <float N>
 Log Ks that correspond to the temperatures in the database. If only one
 log K is specified, it is applied for all temperatures.

Examples
--------

 ::
 
  CHEMISTRY
    ...
    OVERRIDE_MINERAL_MASS_ACTION
      Calcite
        REACTION Calcite + H+ <-> Ca++ + 1. HCO3-
        LOGK 2.2257 1.8487 1.3330 0.7743 0.0999 -0.5838 -1.3262 -2.2154
      /
    /
    ...
  END

  CHEMISTRY
    ...
    OVERRIDE_MINERAL_MASS_ACTION
      Calcite
        REACTION Calcite + H+ <-> Ca++ + 1. HCO3-
      /
    /
    ...
  END

  CHEMISTRY
    ...
    OVERRIDE_MINERAL_MASS_ACTION
      Calcite
        LOGK 1.8487
      /
    /
    ...
  END

.. _Back to Quick Guide: ../QuickGuide
.. _Back to CHEMISTRY: ../Chemistry
