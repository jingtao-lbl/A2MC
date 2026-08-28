Back to :ref:`card-index`

.. _geomechanics-strata-card:

GEOMECHANICS_STRATA
===================
Couples geomechanics material IDs and/or properties with a geomechanics region
in the problem domain.

Required Cards:
---------------
GEOMECHANICS_MATERIAL <string>
  Name of the geomechanics material property to be associated with the geomechanics region is specified in <string>

GEOMECHANICS_REGION <string>
  Name of the geomechanics region associated with a geomechanics material property

Examples
--------

 ::



    GEOMECHANICS_STRATA
      GEOMECHANICS_REGION all_geomech
      GEOMECHANICS_MATERIAL soil1
    END
