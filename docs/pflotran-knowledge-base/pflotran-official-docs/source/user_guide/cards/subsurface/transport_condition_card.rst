Back to :ref:`card-index`

.. _transport-condition-card:

TRANSPORT_CONDITION
===================
In setting up transport conditions, first create a list of self-consistent 
solute concentration constraints, and then associate them with various time 
points.

Required Cards:
---------------
TRANSPORT_CONDITION <name>
 Specifies the name of the transport condition and opens the block.

TYPE <string>
  Specifies the type of the transport boundary condition (options for <string>
  include: DIRICHLET, DIRICHLET_ZERO_GRADIENT, NEUMANN, ZERO_GRADIENT, 
  EQUILIBRIUM):  

  DIRICHLET : Specified concentration

  DIRICHLET_ZERO_GRADIENT : Dirichlet (specified concentration) for inflow and 
  zero diffusive gradient for outflow (i.e. only advective transport is 
  considered on outflow).

  MEMBRANE_FILTER : Works like a membrane filter. Water can pass through
  and solutes cannot (e.g., useful for mimicking evaporation at the land 
  surface when modeling single-phase variably saturated flow). The assignment
  of a CONSTRAINT is required, but the concentrations are ignored.

  NEUMANN : Specified solute flux (**not currently implemented**)

  ZERO_GRADIENT : Prescribes a third-type or Robin boundary conditon for inflow
  and zero diffusive gradient for outflow.

  EQUILIBRIUM : Only applicable to the :ref:`source-sink-card` card. 
  Attempts to set the concentrations at cells within the associated 
  region in equilibrium with the constraint concentrations through a 
  rather large, hardwired rate constant. The user should be careful 
  to check that equilibrium is being reached before trusting the code.

:ref:`constraint-card`
 A :ref:`constraint-card` block may be embedded within a 
 TRANSPORT_CONDITION, but the CONSTRAINT may not change over
 time. This is the same as using CONSTRAINT_LIST with a single
 CONSTRAINT starting at time zero.

CONSTRAINT_LIST
 Opens a block for specifying a list of constraints over time.
 Interpolation is not allowed as nonlinear chemistry cannot be 
 accurately calculated with linear interpolation.

Optional Cards:
---------------
TIME_UNITS <string>
 Specifies the units for the times in the constraint list. If not specified, SI (seconds) is assumed.

Examples
--------

 ::


  TRANSPORT_CONDITION Initial
    TYPE DIRICHLET_ZERO_GRADIENT
    CONSTRAINT_LIST
      0.d0 initial
    /
  END

  TRANSPORT_CONDITION U_source
    TYPE DIRICHLET
    TIME_UNITS s
    CONSTRAINT_LIST
      0.d0 U_source
      336000.d0 Initial
    /
  END

  TRANSPORT_CONDITION 3rd_type_bc
    TYPE ZERO_GRADIENT
    CONSTRAINT_LIST
      0.d0 river_water
    /
  END

  TRANSPORT_CONDITION evaporation
    TYPE MEMBRANE_FILTER
    CONSTRAINT_LIST
      0.d0 any_constraint_name
    /
  END

Example of embedding CONSTRAINT "initial" within TRANSPORT_CONDITION "Initial"
 ::

  TRANSPORT_CONDITION Initial
    TYPE DIRICHLET_ZERO_GRADIENT
    CONSTRAINT initial
      CONCENTRATIONS
        H+       7.3              M Calcite
        Ca++     1.20644e-3       T
        Cu++     1.e-8            T
        Mg++     5.09772e-4       M Dolomite
        UO2++    2.4830E-11       T
        K+       1.54789e-4       T
        Na+      1.03498e-3       Z
        HCO3-    -3.5             G  CO2(g)
        Cl-      6.97741e-4       T
        F-       2.09491e-5       T
        HPO4--   1.e-8            M Fluorapatite
        NO3-     4.69979e-4       T
        SO4--    6.37961e-4       T
        Tracer   1.e-7            F
        Tracer2  1.e-7            F
      /
      MINERALS
        Calcite         0.1         1.
        Metatorbernite  0.          1.
      /
    /
  END
