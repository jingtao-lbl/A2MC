Back to :ref:`card-index`

Back to :ref:`chemistry-card`

Back to :ref:`sorption-card`

.. _ion-exchange-rxn-card:

ION_EXCHANGE_RXN
================
Specifies parameters for an ion exchange reaction.

Required Cards:
---------------

ION_EXCHANGE_RXN
 Opens the block.

CEC <float>
 Cation exchange capacity in (1) equivalents per volume of mineral 
 [eq/m\ :sup:`3`:sub:`mineral`\] (if a MINERAL card is present) or (2) 
 equivalents per bulk volume [eq/m\ :sup:`3`:sub:`bulk`\] (if a MINERAL card 
 is **not** present)

CATIONS 
 Opens the CATIONS block for listing cations participating in the reaction.

  <Cation species Name> <float> <REFERENCE for reference cation only>
    Name of cation and associated selectivity coefficient.  One must select a 
    reference cation with a selectivity coefficient of 1 and convert all the 
    selectivity coefficients to be relative to the reference species selectivity
    coefficient. The REFERENCE card must be appended to the reference cation
    (see examples).

Optional Cards
--------------

MINERAL <string>
 Name of the mineral to which the cations sorb.

Examples
--------
 ::

  SORPTION
    ION_EXCHANGE_RXN
      MINERAL Halite
      CEC 750.  ! eq/m^3
      CATIONS
        Na+   1.  REFERENCE
        Ca++  0.2953
        Mg++  0.1666
      /
    /
  END

