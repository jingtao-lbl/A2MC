Back to :ref:`card-index`

.. _wipp-source-sink-card:

WIPP_SOURCE_SINK
================
The WIPP Source Sink Process Model is :ref:`formally documented here <pm_wipp_source_sink>`.

Specifies the WIPP gas/brine generation process model. This process model is
automatically included as an embedded process model within the ``WIPP_FLOW`` 
mode only.
If you do not want to include the WIPP_SOURCE_SINK process model, then the 
block ``WIPP_SOURCE_SINK`` should not be included in the input deck.

   
Required Cards:
---------------

WIPP_SOURCE_SINK
 Opens the WIPP_SOURCE_SINK block. Must have a matching ``END``.
 
 ::
 
   WIPP_SOURCE_SINK
     . . . 
   END
   
Keywords
~~~~~~~~
   
Within the WIPP_SOURCE_SINK block, **the following keywords are required:**
 
BRUCITES <double> -or- BRUCITEC <double> 
 Specifies the MgO inundated hydration rate in Salado brine (``BRUCITES``) or
 Castile brine (``BRUCITEC``) with units of [mol-MgO/kg-MgO/s]. Only one of the two
 need to be specified, not both.
 
 ::
 
   BRUCITES 5.4d-8  ![mol/kg/s]
 
BRUCITEH <double> 
 Specifies the MgO humid hydration rate with units of [mol-MgO/kg-MgO/s].
 
 ::
 
   BRUCITEH 2.d-8   ![mol/kg/s]
 
HYMAGCON <double> 
 Specifies the hydromagnesite to magnesite conversion rate with units of 
 [mol-hydromagnesite/kg-hydromagnesite/s].
 
 ::
 
   HYMAGCON 3.d-10  ![mol/kg/s]
 
GRATMICI <double> 
 Specifies the inundated biodegradation rate in brine with units of 
 [mol-cellulosics/kg-cellulosics/s].
 
 ::
 
   GRATMICI 5.d-9   ![mol/kg/s]
 
GRATMICH <double> 
 Specifies the humid biodegradation rate with units of [mol-cellulosics/kg-cellulosics/s].
 
 ::
 
   GRATMICH 6.d-10  ![mol/kg/s]
 
SAT_WICK <double> 
 Specifies the unitless wicking saturation parameter.
 
 ::
 
   SAT_WICK 0.50d0  ![-]
   
SALT_PERCENT <double>
 Specifies the weight percent of salt in the brine, according to
 100 x [kg-salt/kg-water].
 
 ::
 
  SALT_PERCENT 3.2400d1 ![-]
   
CORRMCO2 <double>
 Specifies the inundated steel corrosion rate with units of [m/s].
 
 ::
 
   CORRMCO2 6.d-15  ![m/s]
   
HUMCORR <double>
 Specifies the humid steel corrosion rate with units of [m/s].
 
 ::
 
   HUMCORR  0.d0    ![m/s]
   
ASDRUM <double>
 Specifies the surface area of corrodable metal per steel drum with units of
 [m2].
 
 ::
 
   ASDRUM  6.d0     ![m2]
   
ALPHARXN <double>
 Specifies the unitless :math:`\alpha` reaction rate smoothing parameter 
 (see BRAGFLO V6.02 User's Manual Section 14.13.1).
  
 ::
  
   ALPHARXN -1.d3  ![-]

SOCMIN <double>
 Specifies the unitless chemistry cutoff liquid saturation parameter.
 
 ::
 
   SOCMIN  1.5d-2   ![-]

BIOGENFC <double>
 Specifies the unitless probability parameter of attaining sampled microbial
 gas generation rates.
 
 ::
 
   BIOGENFC 0.5d0   ![-]
   
PROBDEG <integer>
 Specifies a flag which controls the inclusion of biodegradation-related
 gas and brine generation rates, with and without plastics and rubbers.
 PROBDEG = 0  => NO BIODEGRADATION;
 PROBDEG = 1  => BIODEGRADATION BUT NO PLASTICS AND RUBBERS;
 PROBDEG = 2  => BIODEGRADATION WITH PLASTICS AND RUBBERS
 
 ::
 
   PROBDEG       2   ![-]
   
STOICHIOMETRIC_MATRIX
 This is a block that gives all of the stoichiometry values for the chemical 
 reactions. It is sized 8x10, for the 8 possible reactions and 10 reactants.
 The values are obtained from the STCO_## parameters and are ordered in the 
 same way. For example, STCO_38 is located in the 3rd row and 8th column of
 the STOICHIOMETRIC_MATRIX block.
 
 Currently STCO_22 and STCO_23, the H2 and H2O coefficients for the microbial 
 gas generation reaction, are not used.  Instead coefficients SMIC_H2 and SMIC_H2O 
 are calculated internally (based on the initial NITRATE and SULFATE inventory) 
 and used instead. 
 
 ::
 
  STOICHIOMETRIC_MATRIX
  # hymag  H2     H2O    Fe     Cell   FeOH2  FeS    MgO    MgOH2  MgCO3 
    0.0d0  1.0d0 -2.0d0 -1.0d0  0.0d0  1.0d0  0.0d0  0.0d0  0.0d0  0.0d0 # anoxic iron corrosion reaction
    0.0d0  0.0d0  0.0d0  0.0d0 -1.0d0  0.0d0  0.0d0  0.0d0  0.0d0  0.0d0 # microbial gas generation reaction
    0.0d0 -1.0d0  2.0d0  0.0d0  0.0d0 -1.0d0  1.0d0  0.0d0  0.0d0  0.0d0 # iron hydroxide sulfidation
    0.0d0  0.0d0  0.0d0 -1.0d0  0.0d0  0.0d0  1.0d0  0.0d0  0.0d0  0.0d0 # metallic iron sulfidation
    0.0d0  0.0d0 -1.0d0  0.0d0  0.0d0  0.0d0  0.0d0 -1.0d0  1.0d0  0.0d0 # MgO hydration
    0.25d0 0.0d0  0.0d0  0.0d0  0.0d0  0.0d0  0.0d0  0.0d0 -1.25d0 0.0d0 # brucite carbonation
    0.0d0  0.0d0  0.0d0  0.0d0  0.0d0  0.0d0  0.0d0 -1.0d0  0.0d0  1.0d0 # MgO carbonation
   -1.0d0  0.0d0  4.0d0  0.0d0  0.0d0  0.0d0  0.0d0  0.0d0  1.0d0  4.0d0 # hydromagnesite conversion
  /
 
   
Inventory Sub-blocks
~~~~~~~~~~~~~~~~~~~~

INVENTORY <name_string>
 Opens the inventory block. This block describes the initial inventory of solids
 and dissolved species within a waste panel. Many inventory blocks can be given
 to describe different initial waste panel inventories, and each should have a
 unique name, indicated with <name_string>. It is also possible to provide a
 single inventory with an associated volume (``VREPOS``) that several waste 
 panels share, where the inventory is scaled to each waste panel by volume.
 Within the inventory block, the following sub-blocks are required:
 
 SOLIDS
  Opens the solids sub-block. The solids sub-block must contain the following
  keywords:
  
  IRONCHW <double> <unit_string>
   Specifies the initial mass of Fe-based material in CH waste in the waste 
   panel with units of mass.
   
   ::
   
     IRONCHW   1.09d7 kg
     
  IRONRHW <double> <unit_string>
   Specifies the initial mass of Fe-based material in RH waste in the waste 
   panel with units of mass.
   
   ::
   
     IRONRHW   1.35d6 kg
     
  IRNCCHW <double> <unit_string>
   Specifies the initial mass of Fe container materials for CH waste in the 
   waste panel with units of mass.
   
   ::
   
     IRNCCHW   3.00d7 kg
  
  IRNCRHW <double> <unit_string>
   Specifies the initial mass of Fe container materials for RH waste in the 
   waste panel with units of mass.
   
   ::
   
     IRNCRHW   6.86d6 kg
       
  CELLCHW <double> <unit_string>
   Specifies the initial mass of cellulosic material in CH waste in the waste 
   panel with units of mass.
   
   ::
   
     CELLCHW   3.55d6 kg
     
  CELLRHW <double> <unit_string>
   Specifies the initial mass of cellulosic material in RH waste in the waste 
   panel with units of mass.
   
   ::
   
     CELLRHW   1.18d5 kg
   
  CELCCHW <double> <unit_string>
   Specifies the initial mass of cellulosics in container materials for 
   CH waste in the waste panel with units of mass.
   
   ::
   
     CELCCHW   7.23d5 kg
  
  CELCRHW <double> <unit_string>
   Specifies the initial mass of cellulosics in container materials for 
   RH waste in the waste panel with units of mass.
   
   ::
   
     CELCRHW   0.d0 kg
     
  CELECHW <double> <unit_string>
   Specifies the initial mass of cellulosics in emplacement materials for 
   CH waste in the waste panel with units of mass.
   
   ::
   
     CELECHW   2.60d5 kg
  
  CELERHW <double> <unit_string>
   Specifies the initial mass of cellulosics in emplacement materials for 
   RH waste in the waste panel with units of mass.
   
   ::
   
     CELERHW   0.d0 kg
     
  RUBBCHW <double> <unit_string>
   Specifies the initial mass of rubber material in CH waste in the waste 
   panel with units of mass.
   
   ::
   
     RUBBCHW   1.09d6 kg
     
  RUBBRHW <double> <unit_string>
   Specifies the initial mass of rubber material in RH waste in the waste 
   panel with units of mass.
   
   ::
   
     RUBBRHW   8.80d4 kg
     
  RUBCCHW <double> <unit_string>
   Specifies the initial mass of rubber in container materials for 
   CH waste in the waste panel with units of mass.
   
   ::
   
     RUBCCHW   6.91d4 kg
     
  RUBCRHW <double> <unit_string>
   Specifies the initial mass of rubber in container materials for 
   RH waste in the waste panel with units of mass.
   
   ::
   
     RUBCRHW   4.18d3 kg
     
  RUBECHW <double> <unit_string>
   Specifies the initial mass of rubber in emplacement materials for 
   CH waste in the waste panel with units of mass.
   
   ::
   
     RUBECHW   0.d0 kg
  
  RUBERHW <double> <unit_string>
   Specifies the initial mass of rubber in emplacement materials for 
   RH waste in the waste panel with units of mass.
   
   ::
   
     RUBERHW   0.d0 kg    
     
  PLASCHW <double> <unit_string>
   Specifies the initial mass of plastic material in CH waste in the waste 
   panel with units of mass.
   
   ::
   
     PLASCHW   5.20d6 kg
     
  PLASRHW <double> <unit_string>
   Specifies the initial mass of plastic material in RH waste in the waste 
   panel with units of mass.
   
   ::
   
     PLASRHW   2.93d5 kg
     
  PLSCCHW <double> <unit_string>
   Specifies the initial mass of plastic in container materials for 
   CH waste in the waste panel with units of mass.
   
   ::
   
     PLSCCHW   2.47d6 kg
     
  PLSCRHW <double> <unit_string>
   Specifies the initial mass of plastic in container materials for 
   RH waste in the waste panel with units of mass.
   
   ::
   
     PLSCRHW   3.01d5 kg
     
  PLSECHW <double> <unit_string>
   Specifies the initial mass of plastic in emplacement materials for 
   CH waste in the waste panel with units of mass.
   
   ::
   
     PLSECHW   1.25d6 kg
  
  PLSERHW <double> <unit_string>
   Specifies the initial mass of plastic in emplacement materials for 
   RH waste in the waste panel with units of mass.
   
   ::
   
     PLSERHW   0.d0 kg     
     
  PLASFAC <double>
   Specifies the unitless mass ratio of plastics to equivalent carbon in the 
   waste panel.
   
   ::
   
     PLASFAC   1.7d0   
     
  MGO_EF <double>
   Specifies the unitless MgO excess factor, which is the ratio of moles of MgO 
   to moles of organic carbon in the waste panel.
   
   ::
   
     MGO_EF    1.2d0 
       
  DRMCONC <double>
   Specifies the number of steel drums per volume in the waste panel in ideal 
   packing, in units of [drums/m3]. Note, this is equivalent to
   DRROOM/VROOM.
   
   ::
   
     DRMCONC   1.866d0  ! [drums/m3]
  
 AQUEOUS
  Opens the aqueous species sub-block. The species within this sub-block are 
  **unrelated** to the primary or secondary species in the :ref:`chemistry-card` 
  block. The aqueous sub-block must contain the following keywords:
    
  NITRATE <double>
   Specifies the initial moles of nitrate in the waste panel. (QINIT[B:32])
   
   ::
   
     NITRATE 2.74d7
     
  SULFATE <double> 
   Specifies the initial moles of sulfate in the waste panel. (QINIT[B:31])
   
   ::
   
     SULFATE 4.91d6
     
 VREPOS <double> <unit_string>
  This is an optional keyword which gives the volume associated with the 
  inventory. If this keyword is given, then several waste panels can be assigned
  the inventory, but the inventory can be scaled to each waste panel according
  to the relative volume (volume-waste-panel/VREPOS).
     
The following is an example of a full ``INVENTORY`` block:

 ::
 
  INVENTORY inv1
    VREPOS     438400.d0 m^3  ! volume for total repository inventory
    SOLIDS
      IRONCHW  1.09d7 kg   ! mass of Fe-based material in CH waste
      IRONRHW  1.35d6 kg   ! mass of Fe-based material in RH waste
      IRNCCHW  3.00d7 kg   ! mass of Fe containers for CH waste
      IRNCRHW  6.86d6 kg   ! mass of Fe containers for RH waste
      CELLCHW  3.55d6 kg   ! mass of cellulosics in CH waste
      CELLRHW  1.18d5 kg   ! mass of cellulosics in RH waste
      CELCCHW  7.23d5 kg   ! mass of cellulosics in container materials for CH waste
      CELCRHW  0.d0   kg   ! mass of cellulosics in container materials for RH waste
      CELECHW  2.60d5 kg   ! mass of cellulosics in emplacement materials for CH waste
      CELERHW  0.d0   kg   ! mass of cellulosics in emplacement materials for RH waste
      RUBBCHW  1.09d6 kg   ! mass of rubber in CH waste
      RUBBRHW  8.80d4 kg   ! mass of rubber in RH waste
      RUBCCHW  6.91d4 kg   ! mass of rubber in container materials for CH waste
      RUBCRHW  4.18d3 kg   ! mass of rubber in container materials for RH waste
      RUBECHW  0.d0   kg   ! mass of rubber in emplacement materials for CH waste
      RUBERHW  0.d0   kg   ! mass of rubber in emplacement materials for RH waste
      PLASCHW  5.20d6 kg   ! mass of plastics in CH waste
      PLASRHW  2.93d5 kg   ! mass of plastics in RH waste
      PLSCCHW  2.47d6 kg   ! mass of plastics in container materials for CH waste
      PLSCRHW  3.01d5 kg   ! mass of plastics in container materials for RH waste
      PLSECHW  1.25d6 kg   ! mass of plastics in emplacement materials for CH waste
      PLSERHW  0.d0   kg   ! mass of plastics in emplacement materials for RH waste
      PLASFAC  1.7d0       ! mass ratio of plastics to equivalent carbon
      MGO_EF   1.2d0       ! MgO excess factor: ratio mol-MgO/mol-Organic-C
      DRMCONC  1.86d0      ! [-/m3] number of metal drums per m3 in a panel in ideal packing (DRROOM/VROOM)
    /
    AQUEOUS 
      NITRATE 2.74d7   ! moles in panel  QINIT[B:32]
      SULFATE 4.91d6   ! moles in panel  QINIT[B:31]
    /
  /
     
Waste Panel Sub-blocks
~~~~~~~~~~~~~~~~~~~~~~

WASTE_PANEL <name_string>
 Opens the waste panel block. This block describes a waste panel, indicating 
 the region it is associated with and the inventory it has. Many waste panel 
 blocks can be given, and each should have a unique name, indicated with 
 <name_string>.
 Within the waste panel block, the following keywords are required:
  
 REGION <name_string>
  Specifies the region that is associated with the waste panel. The 
  <name_string> indicates the name of a region that was previously defined.
  
  ::
  
    REGION waste_panel_9
    
 INVENTORY <name_string>
  Specifies the inventory that is associated with the waste panel. The
  <name_string> indicates the name of an inventory that was previously defined
  within the ``WIPP_SOURCE_SINK`` block.
  
  ::
  
    INVENTORY inv1
    
 SCALE_BY_VOLUME <yes/no_string>
  This keyword is optional to include. If ``YES`` then the waste panel will be
  given a scaled amount of the inventory indicated by ``INVENTORY``, and the 
  inventory must also have the keyword ``VREPOS``. If ``NO``, or completely 
  omitted, the waste panel will recieve the full, non-scaled inventory.
  
  ::
  
    SCALED_BY_VOLUME yes
    
The following is an example of a full ``WASTE_PANEL`` block:

 ::
 
  WASTE_PANEL waste_panel_9
    REGION wp9
    INVENTORY inv1
    SCALE_BY_VOLUME yes
  /
  WASTE_PANEL waste_panel_5
    REGION wp5
    INVENTORY inv88
    SCALE_BY_VOLUME no
  /
  
Borehole Materials Sub-block
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

BOREHOLE_MATERIALS
 Opens the borehole materials block. This block provides a list of material
 names that are considered borehole materials. Gas generation is turned off
 in these materials once borehole intrusion takes place.

The following is an example of a ``BOREHOLE_MATERIALS`` block:

 ::
 
  BOREHOLE_MATERIALS
    BH_OPEN
    BH_SAND
    BH_CREEP
  /


Examples
--------
 
 ::
 
  WIPP_SOURCE_SINK

    BRUCITES  5.2d-8  ![mol/kg/s] MgO inundated hydration rate in Salado brine
    BRUCITEH  2.d-8   ![mol/kg/s] MgO humid hydration rate
    HYMAGCON  3.d-10  ![mol/kg/s] hydromagnesite to magnesite conversion rate
    SAT_WICK  0.50d0  ![-] wicking saturation parameter
    SALT_PERCENT  3.2400d1  ![100*kg salt/kg water] weight percent salt in brine (rxns produce brine, not just water)
    GRATMICI  5.d-9   ![mol/kg/s] inundated biodegradation rate for cellulose
    GRATMICH  6.d-10  ![mol/kg/s] humid biodegradation rate for cellulose
    CORRMCO2  6.d-15  ![m/s] inundated steel corrosion rate without microbial gas generation
    HUMCORR   0.d0    ![m/s] humid steel corrosion rate
    ASDRUM    6.d0    ![m2] surface area of corrodable metal per drum
    ALPHARXN -1.d3    ![-]
    SOCMIN    1.5d-2  ![-]
    BIOGENFC  0.5d0   ![-]
    PROBDEG   2       !flag for biodegradation inclusion
    
    STOICHIOMETRIC_MATRIX
    # hymag  H2     H2O    Fe     Cell   FeOH2  FeS    MgO    MgOH2  MgCO3 
      0.0d0  1.0d0 -2.0d0 -1.0d0  0.0d0  1.0d0  0.0d0  0.0d0  0.0d0  0.0d0 # anoxic iron corrosion reaction
      0.0d0  0.0d0  0.0d0  0.0d0 -1.0d0  0.0d0  0.0d0  0.0d0  0.0d0  0.0d0 # microbial gas generation reaction
      0.0d0 -1.0d0  2.0d0  0.0d0  0.0d0 -1.0d0  1.0d0  0.0d0  0.0d0  0.0d0 # iron hydroxide sulfidation
      0.0d0  0.0d0  0.0d0 -1.0d0  0.0d0  0.0d0  1.0d0  0.0d0  0.0d0  0.0d0 # metallic iron sulfidation
      0.0d0  0.0d0 -1.0d0  0.0d0  0.0d0  0.0d0  0.0d0 -1.0d0  1.0d0  0.0d0 # MgO hydration
      0.25d0 0.0d0  0.0d0  0.0d0  0.0d0  0.0d0  0.0d0  0.0d0 -1.25d0 0.0d0 # brucite carbonation
      0.0d0  0.0d0  0.0d0  0.0d0  0.0d0  0.0d0  0.0d0 -1.0d0  0.0d0  1.0d0 # MgO carbonation
     -1.0d0  0.0d0  4.0d0  0.0d0  0.0d0  0.0d0  0.0d0  0.0d0  1.0d0  4.0d0 # hydromagnesite conversion
    /
    
    # note: multiple inventories may be included, but here there is only one
    INVENTORY inv1
      VREPOS     438406.08 m^3 ! optional - only needed if a WASTE_PANEL including this inventory needs to SCALE_BY_VOLUME
      SOLIDS
	IRONCHW  1.09d7 kg   ! mass of Fe-based material in CH waste
	IRONRHW  1.35d6 kg   ! mass of Fe-based material in RH waste
	IRNCCHW  3.00d7 kg   ! mass of Fe containers for CH waste
	IRNCRHW  6.86d6 kg   ! mass of Fe containers for RH waste
	CELLCHW  3.55d6 kg   ! mass of cellulosics in CH waste
	CELLRHW  1.18d5 kg   ! mass of cellulosics in RH waste
	CELCCHW  7.23d5 kg   ! mass of cellulosics in container materials for CH waste
	CELCRHW  0.d0   kg   ! mass of cellulosics in container materials for RH waste
	CELECHW  2.60d5 kg   ! mass of cellulosics in emplacement materials for CH waste
	CELERHW  0.d0   kg   ! mass of cellulosics in emplacement materials for RH waste
	RUBBCHW  1.09d6 kg   ! mass of rubber in CH waste
	RUBBRHW  8.80d4 kg   ! mass of rubber in RH waste
	RUBCCHW  6.91d4 kg   ! mass of rubber in container materials for CH waste
	RUBCRHW  4.18d3 kg   ! mass of rubber in container materials for RH waste
	RUBECHW  0.d0   kg   ! mass of rubber in emplacement materials for CH waste
	RUBERHW  0.d0   kg   ! mass of rubber in emplacement materials for RH waste
	PLASCHW  5.20d6 kg   ! mass of plastics in CH waste
	PLASRHW  2.93d5 kg   ! mass of plastics in RH waste
	PLSCCHW  2.47d6 kg   ! mass of plastics in container materials for CH waste
	PLSCRHW  3.01d5 kg   ! mass of plastics in container materials for RH waste
	PLSECHW  1.25d6 kg   ! mass of plastics in emplacement materials for CH waste
	PLSERHW  0.d0   kg   ! mass of plastics in emplacement materials for RH waste
	PLASFAC  1.7d0       ! [-] mass ratio of plastics to equivalent carbon
	MGO_EF   1.2d0       ! [-] MgO excess factor: ratio mol-MgO/mol-Organic-C
	DRMCONC  1.8669852   ! [-/m3] number of metal drums per m3 in a panel in ideal packing (DRROOM/VROOM = 6804/3644.378))
      /
      AQUEOUS 
        NITRATE 2.74d7   ! moles in panel  QINIT[B:32]
        SULFATE 4.91d6   ! moles in panel  QINIT[B:31]
      /
    /

    WASTE_PANEL wp1
      REGION panel1
      INVENTORY inv1
      SCALE_BY_VOLUME yes
    /
    WASTE_PANEL wp2
      REGION panel2
      INVENTORY inv1
      SCALE_BY_VOLUME yes
    /
    WASTE_PANEL wp3
      REGION panel3
      INVENTORY inv1
      SCALE_BY_VOLUME yes
    /
    WASTE_PANEL wp4
      REGION panel4
      INVENTORY inv1
      SCALE_BY_VOLUME yes
    /
    WASTE_PANEL wp5
      REGION panel5
      INVENTORY inv1
      SCALE_BY_VOLUME yes
    /
    
  END_WIPP_SOURCE_SINK
  
Note the ``REGION`` s ``panel1`` through ``panel5`` have been previously defined. 
   
   
   
   
   
   
   


