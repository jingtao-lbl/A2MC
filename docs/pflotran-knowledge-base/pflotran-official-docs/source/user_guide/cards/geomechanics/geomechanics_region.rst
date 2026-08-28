Back to :ref:`card-index`

.. _geomechanics-region-card:

GEOMECHANICS_REGION
===================
The GEOMECHANICS_REGION keyword defines a set of geomechanics finite element grid vertices. The GEOMECHANICS_REGION name can then be used to link this set of vertices to geomechanics material properties, strata and boundary conditions. The list of vertices can be read from an ASCII file by using the keyword FILE under the GEOMECHANICS_REGION card.


Required Cards:
---------------
FILE <filename>
  <filename> specifies the file with the list of vertices

Examples
--------

 ::

      
    GEOMECHANICS_REGION all_geomech
      FILE geomech_dat/all.vset
    END

    GEOMECHANICS_REGION north_geomech
      FILE geomech_dat/north.vset
    END

    GEOMECHANICS_REGION south_geomech
      FILE geomech_dat/south.vset
    END

    GEOMECHANICS_REGION east_geomech
      FILE geomech_dat/east.vset
    END

    GEOMECHANICS_REGION west_geomech
      FILE geomech_dat/west.vset
    END

    GEOMECHANICS_REGION top_geomech
      FILE geomech_dat/top.vset
    END

    GEOMECHANICS_REGION bottom_geomech
      FILE geomech_dat/bottom.vset
    END

    GEOMECHANICS_REGION top_boundary
      FILE geomech_dat/top_boundary.vset
    END

    GEOMECHANICS_REGION top_corner
      FILE geomech_dat/top_corner.vset
    END

    GEOMECHANICS_REGION top_internal
      FILE geomech_dat/top_internal.vset
    END 
