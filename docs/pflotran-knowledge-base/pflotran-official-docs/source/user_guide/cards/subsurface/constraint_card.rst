Back to :ref:`card-index`

Back to :ref:`transport-condition-card`

.. _constraint-card:

CONSTRAINT
==========
Creates a set of solute concentration constraints. This card must be included 
with the :ref:`transport-condition-card` card.

Required Cards: 
---------------
CONSTRAINT <name>
 Specifies the name of the constraint and opens the block.

CONCENTRATIONS
 Solute concentrations are provided for the species using the following list
 structure,

  <string> <float> <string> <optional string>

  species_name concentration constraint_type constraint_species

 Constraint type options (Reactive Transport Mode):
  * F = free ion concentration. Default units [mol/L]
  * T = total aqueous component concentration.  Default units [mol/L]
  * P = pH
  * PE = pe (for O2(aq) or H+ only)
  * M = concentration based on equilibrium with specified mineral. The 
    float is an initial guess.  Default units [mol/L]
  * G = concentration based on equilibrium with a gas 
    (partial pressure) [bars]
  * L = Base 10 logarithm of concentration
  * Z = charge balance
  * TOTAL_SORB = total sorbed concentration [mol/m\ :sup:`3`\ :sub:`bulk`\]
  * TOTAL_AQ_PLUS_SORB = total aqueous + total sorbed component concentration 
    [mol/L]. The total sorbed concentration 
    [mol/m\ :sup:`3`\ :sub:`bulk`\] 
    must be converted to molarity [mol/L] 
    by dividing by porosity * saturation * 1000 before being summed.

 Constraint type options (Nuclear Waste Transport Mode):
  * T = total bulk concentration [mol/m\ :sup:`3`\ :sub:`bulk`\]
  * AQ = aqueous concentration [mol/m\ :sup:`3`\ :sub:`water`\]
  * PPT = precipitated concentration [mol/m\ :sup:`3`\ :sub:`bulk`\]
  * VF = precipitated volume fraction [m\ :sup:`3`\ /m\ :sup:`3`\ :sub:`void`\]
  * SB = sorbed concentration [mol/m\ :sup:`3`\ :sub:`bulk`\]

Optional Cards: 
---------------

DATASET
 Couples a cell-indexed dataset to a concentration (initial conditions only)

EQUILIBRATE_AT_EACH_CELL
 Forces re-equilibration of constraints at each cell during setup of initial condition

FREE_ION_GUESS
 Provides an initial guess for the free ion concentrations of the aqueous 
 species and improves convergence of initial speciation calculations, using the
 following list structure,

  <string> <float>

  species_name guess

.. SURFACE_COMPLEXES (advanced capability for specifying initial concentration of kinetic surface complexes. Not currently documented.)
.. COLLOIDS not currently documented.

IMMOBILE
 Concentrations are provided for immobile species using the following list
 structure,

  <string> <float>

  species_name concentration [mol/m\ :sup:`3`\ :sub:`bulk`\]

MINERALS
 Provides mineral concentrations for the minerals using the following list 
 structure,

  <string> <float> <float>
  
  mineral_name volume_fraction specific_surface_area 
  [m\ :sup:`2` \ mineral/m\ :sup:`3` \ bulk]

  Note that specific surface area supports units of area mineral per mass mineral (e.g. [cm\ :sup:`2` \ mineral/g mineral]) where the specific surface area is based on the initial mass of mineral in a cell based on initial volume fraction.

Examples
--------

 ::

  CONSTRAINT initial
    CONCENTRATIONS
      H+     1.d-8      F
      HCO3-  1.d-3      G  CO2(g)
      Ca++   5.d-4      M  Calcite
    /
    MINERALS
      Calcite 1.d-5 1.d0
    /
  END

  CONSTRAINT initial_groundwater
    CONCENTRATIONS
      H+       1.d-7            M Calcite
      Ca++     1.20644e-3       T
      Cu++     1.e-8            T
      Mg++     5.09772e-4       T Dolomite
      UO2++    2.4830E-11       T DATASET initial_U
      K+       1.54789e-4       T
      Na+      1.03498e-3       Z
      HCO3-    2.57305e-3       T
      Cl-      6.97741e-4       T
      F-       2.09491e-5       T
      HPO4--   1.e-8            M Fluorapatite
      NO3-     4.69979e-4       T
      SO4--    6.37961e-4       T
      Tracer   1.e-7            F
      Tracer2  1.e-7            F
    /
    MINERALS
      Calcite DATASET initial_Calcite_vol_frac DATASET initial_Calcite_area
      Metatorbernite 0.    1. cm^2/cm^3
    /
  END

  CONSTRAINT U_source
    CONCENTRATIONS
      H+       7.3              M  Calcite
      Ca++     1.20644e-3       T
      Cu++     1.e-6            T
      Mg++     5.09772e-4       T  Dolomite
      UO2++    2.34845e-7       T      
      K+       1.54789e-4       T
      Na+      1.03498e-3       Z
      HCO3-    2.57305e-3       T
      Cl-      6.97741e-4       T
      F-       2.09491e-5       T
      HPO4--   1.e-6            M  Fluorapatite
      NO3-     4.69979e-4       T
      SO4--    6.37961e-4       T
      Tracer   1.e-7            F
      Tracer2  1.e-7            F
    /
    FREE_ION_GUESS
      H+                    2.7340E-08
      Ca++                  1.1344E-03
      Cu++                  3.4195E-10
      Mg++                  4.6508E-04
      UO2++                 1.0165E-19
      K+                    1.5433E-04
      Na+                   1.3344E-03
      HCO3-                 2.4015E-03
      Cl-                   6.9732E-04
      F-                    2.0709E-05
      HPO4--                8.9094E-10
      NO3-                  4.6803E-04
      SO4--                 5.5862E-04
      Tracer                1.0000E-07
      Tracer2               1.0000E-03 
    /
    MINERALS
      Calcite        0.1    0.18 cm^2/g
      Metatorbernite 0.0    1.
    /
  /

  CONSTRAINT initial
    CONCENTRATIONS
      C5H7O2N(aq) 1.d-5    T
      CH2O(aq)    61.13d-3 T
      CO2(aq)     1.d-3    T
      N2(aq)      1.d-10   T
      NH4+        1.d0     T
      NO2-        1.d-10   T
      NO3-        18.25d-3 T
      O2(aq)      1.d-3    T
    /
    IMMOBILE
      C_consumption 1.d-10
    /
  END

