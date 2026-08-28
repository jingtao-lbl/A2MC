Back to :ref:`card-index`

.. _chemistry-card:

CHEMISTRY
=========
Specifies geochemistry details for multicomponent transport.

For help creating a list of SECONDARY_SPECIES, GAS_SPECIES, and MINERALS given a list of PRIMARY_SPECIES, use the [reaction species finder](https://reactions.gentleplants.com/).

Required Cards:
---------------

PRIMARY_SPECIES
 List of primary aqueous or basis species for which concentrations will be 
 solved.

Optional Cards:
---------------

.. include:: chemistry/chemistry_options.tmp

Examples
--------

 ::

  CHEMISTRY
    PRIMARY_SPECIES
      H+
      HCO3-
      Ca++
    /
    SECONDARY_SPECIES
      OH-
      CO3--
      CO2(aq)
      CaOH+
      CaHCO3+
      CaCO3(aq)
    /
    MINERALS
      Calcite
    /
    MINERAL_KINETICS
      Calcite
        RATE_CONSTANT 1.d-13
      /
    /
    DATABASE ./calcite.dat
    LOG_FORMULATION
    ACTIVITY_COEFFICIENTS TIMESTEP
  END

 ::

  CHEMISTRY
    PRIMARY_SPECIES
      H+
      Ca++
      Cu++
      Mg++
      UO2++
      K+
      Na+
      HCO3-
      Cl-
      F-
      HPO4--
      NO3-
      SO4--
      Tracer
      Tracer2
    /
    SECONDARY_SPECIES
      OH-
      CO3--
      CO2(aq)
      CaCO3(aq)
      CaHCO3+
      CaSO4(aq)
      CaCl+
      CaCl2(aq)
      CaF+
      CaH2PO4+
      CaHPO4(aq)
      CaNO3+
      CaPO4-
      MgCO3(aq)
      MgHCO3+
      MgSO4(aq)
      MgCl+
      MgF+
      UO2(H2PO4)(H3PO4)+
      UO2(H2PO4)2(aq)
      UO2HPO4(aq)
      UO2H2PO4+
      UO2H3PO4++
      UO2PO4-
    /
    GAS_SPECIES
      CO2(g)
    /
    MINERALS
      Calcite
      Magnesite
      Dolomite
      Dolomite-dis
      Dolomite-ord
      Brucite
      Nesquehonite
      Gypsum
      Schoepite
      UO2CO3
      UO2(PO3)2
      (UO2)3(PO4)2
      (UO2)3(PO4)2.4H2O
      CaUO4
      UO2SO4
      UOF4
      UO3.2H2O
      UO3.0.9H2O(alpha)
      Saleeite
      Sylvite
      Metatorbernite
      Whitlockite
      Chalcanthite
      Brochantite
      Tenorite
      Malachite
      Fluorapatite
      Fluorite
      Hydroxylapatite
      Torbernite
    /
  :
    MINERAL_KINETICS
      Calcite 
        RATE_CONSTANT 1.e-12 mol/cm^2-sec
      /
      Metatorbernite 
        RATE_CONSTANT 2.e-17 mol/cm^2-sec
      /
    /
    SORPTION
      JUMPSTART_KINETIC_SORPTION
      SURFACE_COMPLEXATION_RXN
        MINERAL Calcite
        SITE >SOH 15.264 ! 20 m^2/g, por = 0.25
        COMPLEXES
          >SOUO2OH
          >SOHUO2CO3
        /
      /
    /
    DATABASE ../../../hanford.dat
    LOG_FORMULATION
    MAX_RELATIVE_CHANGE_TOLERANCE 1.d-10
    ACTIVITY_COEFFICIENTS NEWTON_ITERATION
    OUTPUT
      UO2++
      Tracer
    /
  END

