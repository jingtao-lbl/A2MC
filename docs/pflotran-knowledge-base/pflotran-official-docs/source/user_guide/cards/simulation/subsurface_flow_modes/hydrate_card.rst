Back to :ref:`card-index`

Back to :ref:`subsurface-flow-card`

Back to :ref:`subsurface-flow-mode-card`

.. _hydrate-card:

HYDRATE
=======
Defines options for the Hydrate subsurface flow mode. For more details and governing equations see the Theory Guide.

:ref:`hydrate-simulation-options`

:ref:`hydrate-timestepper-options`

:ref:`hydrate-newton-options`

:ref:`hydrate-block-options`

:ref:`hydrate-examples`

.. _hydrate-simulation-options:

SIMULATION Options
------------------
*(under SUBSURFACE_FLOW in SIMULATION PROCESS_MODELS block)*

.. include:: sim_hydrate.tmp

LEGACY_FLUXES
 Use fluxes from an earlier version of HYDRATE mode, similar to GENERAL mode flux formulation. Default
 is to use fluxes similar to SCO2 mode.

.. _hydrate-timestepper-options:

TIMESTEPPER Options
-------------------

.. include:: timestepper_hydrate.tmp

.. _hydrate-newton-options:

NEWTON_SOLVER Options
---------------------

.. include:: newton_hydrate.tmp

.. _hydrate-block-options:

HYDRATE Block
-------------
*(within SUBSURFACE block)*

GAS <string>
  CO2
    Use CO2 as the working gas
  CH4
    Use CH4 as the working gas (default)
  AIR
    Use air (non hydrate-forming gas) as the working gas.

METHANOGENESIS
 Invokes a methanogenesis source term. Current source implementation (following Malinverno, 2010) requires:
  NAME <string>
    Arbitrary name of the methanogenesis source
  ALPHA <float>
    Seafloor labile organic carbon [wt%]
  LAMBDA <float>
    Methanogenesis reaction rate [1/s]
  V_SED <float>
    Sedimentation rate [m/s]
  SMT_DEPTH <float>
    Depth to the sulfate-methane transition [m]
  K_ALPHA <float>
    Conversion factor from organic carbon to methane (typically 2241)

WITH_SEDIMENTATION
 Turns on sedimentation. Moves immobile pore species at the sedimentation rate specified in the METHANOGENESIS block and in the direction of gravity.

WITH_GIBBS_THOMSON
  Turns on the Gibbs-Thomson effect. Shifts the gas hydrate phase boundary as a function of required subcooling to precipitate hydrate.

GT_3PHASE
  Applies the Gibbs-Thomson effect in 3-phase and 4-phase states.

ADJUST_SOLUBILITY_WITHIN_GHSZ
  Applies a correction to methane solubility within the hydrate stability zone as a function of distance from the phase boundary.

NO_PC
  Turns off capillary pressure.

NO_EFFECTIVE_SATURATION_SCALING
 Turns off scaling of saturations of mobile pore species by the total amount of mobile pore fluids.

NO_ICE_VOLUME_CHANGE
 Turn off volume change due to ice freezing.

NO_SOLID_SATURATION_PERM_SCALING
 Turns off absolute permeability scaling by hydrate saturation.

PERM_SCALING_FUNCTION <string>
 Selects the specific function used for absolute permeability scaling as a function of hydrate saturation. Current options: DAI_AND_SEOL

HYDRATE_PHASE_BOUNDARY <string>
 Sets the gas hydrate phase boundary equation for CH4-hydrate. Default is Kamath, 1984. Current options: MORIDIS, MORIDIS_SIMPLE

HENRYS_CONSTANT <string>
 Set function for Henry's constant for methane. Current default: Carroll and Mather, 1997. Current options: CRAMER

SALINITY <float>
 Set a constant salinity, which shifts the hydrate phase boundary and the freezing point of water.

THERMAL_CONDUCTIVITY <string>
 Set the thermal conductivity model. Default is a phase saturation weighted average. Current options: IGHCC2

BC_REFERENCE_PRESSURE
 Reference pressure for seepage boundary condition.


.. _hydrate-examples:

Examples
--------
::

 SIMULATION
   SIMULATION_TYPE SUBSURFACE
   PROCESS_MODELS
     SUBSURFACE_FLOW flow
       MODE HYDRATE
     /
   /
 END
 ...
 SUBSURFACE
   NUMERICAL_METHODS FLOW
     NEWTON_SOLVER
       USE_INFINITY_NORM_CONVERGENCE
     /
   /
   ...
   HYDRATE
     GAS CH4
     PERM_SCALING_FUNCTION DAI_AND_SEOL
     WITH_GIBBS_THOMSON
     GT_3PHASE
     ADJUST_SOLUBILITY_WITHIN_GHSZ
     WITH_SEDIMENTATION
     METHANOGENESIS
      NAME ss_methanogenesis
      ALPHA 0.005
      K_ALPHA 2241
      LAMBDA 1.d-14
      V_SED 3.17d-11
      SMT_DEPTH 10.d0
     /
   /
   ...
