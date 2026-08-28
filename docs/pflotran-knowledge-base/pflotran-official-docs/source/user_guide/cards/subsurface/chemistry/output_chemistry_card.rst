Back to :ref:`card-index`

Back to :ref:`chemistry-card`

.. _output-chemistry-card:

OUTPUT (CHEMISTRY)
==================
Specifies output options for biogeochemical transport.

Required Cards
--------------

OUTPUT
 Opens the OUTPUT block.

Optional Cards:
---------------

<string>
 Name of species (e.g. primary aqueous, secondary aqueuos, mineral, sorbed 
 complexes, etc.) to be printed in output.

OFF
 Geochemical transport output is turned off.

ALL
 All primary species, mineral species, sorbed species (i.e. colloids, 
 surface complexes, surface sites...if applicable) and pH (if applicable) 
 are printed in output.

PRIMARY_SPECIES
 All primary species and pH (if applicable) are printed.

SECONDARY_SPECIES
 All secondary aqueous complexes are printed.

GASES
 Not yet supported.

MINERALS
 All minerals are printed.

IMMOBILE
 All immobile species are printed.

PH
 pH is printed (if applicable--i.e. H+ exists).

AGE
 Groundwater age is printed.

KD
 The KD (ratio of sorbed to aqueous mass) for each primary species is printed.

COLLOIDS
 Colloidal concentrations are printed.

TOTAL
  Total aqueous component concentration of each species is printed.

TOTAL_SORBED
 Total sorbed concentration of each species is printed.

TOTAL_SORBED_MOBILE
 Total sorbed concentration on mobile colloids is printed.

FREE_ION
 Primary species concentrations are printed as free-ion concentrations.  
 By default, primary species concentrations are printed as total component 
 concentrations.

ACTIVITY_COEFFICIENTS
 Activity coefficients are printed for primary species.

MOLARITY
 Printed concentration units are in molarity (M).

MOLALITY
 Printed concentration units are in molality (m).

MINERAL_VOLUME_FRACTION
 Outputs volume fractions for all minerals specified in the OUTPUT block.

MINERAL_RATE
 Outputs rates for all minerals specified in the OUTPUT block.

MINERAL_SATURATION_INDEX
 Outputs saturation indices for all minerals specified in the OUTPUT block 
 (including any equilibrium minerals).

MINERAL_SURFACE_AREA
 Outputs mineral specific surface areas for all minerals specified in OUTPUT block.

SITE_DENSITY
 Free sorption site density is printed.

PRINT_TOTAL_MASS_KG
 Prints total component mass in [kg] for regions specified in the TOTAL_MASS_REGIONS sub-block.

PRINT_VERBOSE_CONSTRAINTS
 For each primary species, the secondary aqueous complexes that make up its
 total component concentration are printed, ordered by descending percent
 contribution to the total.

ELECTRICAL_CONDUCTIVITY
 Prints the fluid electrical conductivity calculated based on the specified
 ELECTRICAL_CONDUCTIVITY_METHOD.

**Notes:**
 - By default, ALL and MINERALS specify that volume fractions and kinetic rates 
   be printed for all kinetic minerals.  To print saturation indices for 
   minerals, including those not listed as kinetic minerals (i.e. mineral names 
   present under MINERAL, but not under MINERAL_KINETICS), simply list the name 
   of each mineral individually.

Examples
--------
::

  CHEMISTRY
    ...
    OUTPUT
      PH
      all
      TOTAL
      Calcite
      CO2(aq)
    /
    ...
  END

To print volume fraction and reaction rate for both Calcite and Gibbsite and 
the saturation index for only Gibbsite:

:: 

  CHEMISTRY
    ...
    MINERALS
      Quartz
      Calcite
      Gibbsite
    /
    MINERAL_KINETICS
      Calcite
        RATE_CONSTANT 1.d-12
      /
    /
    OUTPUT
      ALL
      TOTAL
      Gibbsite
      MINERAL_SATURATION_INDEX
    /
    ...
  END
