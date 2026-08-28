Back to :ref:`card-index`

Back to :ref:`chemistry-card`

Back to :ref:`sorption-card`

.. _surface-complexation-rxn-card:

SURFACE_COMPLEXATION_RXN
========================
Specifies parameters for a surface complexation reaction.

Required Cards:
---------------

SURFACE_COMPLEXATION_RXN
 Opens the block.

Optional Cards:
---------------

EQUILIBRIUM
 Specifies equilibrium kinetic sorption.

MULTIRATE_KINETIC
 Specifies multirate kinetic sorption.  Requires RATES and SITE_FRACTION cards.

.. geh: commenting out for now since not functional
.. KINETIC
..  Specifies kinetic sorption.

.. :ref:`complex-kinetics-card`
..  Opens a block specifying forward and backward rate constants.

RATES <float ... float>
 Toggles on multirate kinetic sorption.  Specifies kinetic rates associated 
 with SITE_FRACTIONs. The number of RATES must match the number of SITE_FRACTIONs.

SITE_FRACTION <float ... float>
 Specifies site fractions associated with RATES for multirate kinetic sorption.  
 The number of SITE_FRACTIONs must match the number of RATES.

MINERAL <string>
 The name of the mineral with which the sorption site density is associated.
 The mineral volume fraction $\phi_\text{mnrl}$
 $\units{\frac{\strvolume_\text{mnrl}}{\strvolume_\text{bulk}}}$ 
 scales the site density 
 $\left[\omega=\omega^*\phi_\text{mnrl}\right]$ 
 and the site density $\omega^*$ has units
 $\units{\frac{\text{mol}}{\strvolume_\text{mnrl}}}$.

MULTIRATE_SCALE_FACTOR <float>
 Floating point number that scales all rate constants for multirate kinetic 
 sorption.

COLLOID <string>
 Name of the colloid associated with surface complexation reaction.

ROCK_DENSITY
 A flag which allows the calculation of surface site concentration based on 
 rock density. The rock density $\density_\text{rock}$
 $\units{\frac{\strmass_\text{rock}}{\strvolume_\text{bulk}}}$ 
 scales the site density 
 $\left[\omega=\omega^*(1-\porosity)\density_\text{rock}\right]$ 
 and the site density $\omega^*$ has units
 $\units{\frac{\text{mol}}{\strmass_\text{rock}}}$. 

SITE <string> <float>
 Name of site and site density 
 $\omega \units{\frac{\text{mol}}{\strvolume_\text{bulk}}}$.

COMPLEXES
 Opens a block listing the names of surface complexes associated with the 
 surface complexation reaction and the surface site.  These are provided by 
 the database file.

Examples
--------

 :: 

  SORPTION
    SURFACE_COMPLEXATION_RXN
      MULTIRATE_KINETIC
      SITE_FRACTION \
        0.02 0.02 0.02 0.02 0.02 \
        0.02 0.02 0.02 0.02 0.02 \
        0.02 0.02 0.02 0.02 0.02 \
        0.02 0.02 0.02 0.02 0.02 \
        0.02 0.02 0.02 0.02 0.02 \
        0.02 0.02 0.02 0.02 0.02 \
        0.02 0.02 0.02 0.02 0.02 \
        0.02 0.02 0.02 0.02 0.02 \
        0.02 0.02 0.02 0.02 0.02 \
        0.02 0.02 0.02 0.02 0.02
      RATES \
        2.5722E-11  8.5000E-11  1.5972E-10  2.5139E-10  3.6111E-10 \
        4.9167E-10  6.4167E-10  8.1667E-10  1.0167E-09  1.2472E-09 \
        1.5111E-09  1.8111E-09  2.1528E-09  2.5389E-09  2.9722E-09 \
        3.4722E-09  4.0278E-09  4.6667E-09  5.3889E-09  6.2222E-09 \
        7.1389E-09  8.1944E-09  9.3611E-09  1.0722E-08  1.2278E-08 \
        1.4028E-08  1.6056E-08  1.8389E-08  2.1056E-08  2.4139E-08 \
        2.7750E-08  3.1944E-08  3.6944E-08  4.2778E-08  4.9444E-08 \
        5.7778E-08  6.7778E-08  8.0000E-08  9.5000E-08  1.1389E-07 \
        1.3806E-07  1.6944E-07  2.1111E-07  2.6861E-07  3.5000E-07 \
        4.7778E-07  6.8611E-07  1.0778E-06  2.0278E-06  6.6944E-06
      MULTIRATE_SCALE_FACTOR 1000.d0
      MINERAL Kaolinite
      SITE >SiOH 0.00636
      COMPLEXES
        >SiOUO3H3++
        >SiOUO3H2+
        >SiOUO3H
        >SiOUO3-
        >SiOUO2(OH)2-
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
    SURFACE_COMPLEXATION_RXN
      EQUILIBRIUM
      MINERAL Kaolinite
      SITE >AlOH 0.00636
      COMPLEXES
        >AlOUO2+
      /
    /
  END
