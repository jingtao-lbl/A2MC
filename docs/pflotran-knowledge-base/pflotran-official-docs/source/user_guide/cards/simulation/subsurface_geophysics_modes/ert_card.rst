Back to :ref:`card-index`

Back to :ref:`subsurface-geophysics-card`

Back to :ref:`subsurface-geophysics-mode-card`

.. _ert-card:

ERT
===

Defines options for the ERT geophysics mode

:ref:`ert-simulation-options`

.. _ert-simulation-options:

SIMULATION Options 
------------------
*(under SUBSURFACE_GEOPHYSICS in SIMULATION PROCESS_MODELS block)*

**Basic Settings**

COMPUTE_JACOBIAN
 Toggles on the calculation of the ERT Jacobian (derivatives of ERT measurements with respectd to bulk electrical conductivity).

NO_ANALYTICAL POTENTIAL
 An analytical potential is calculated as the initial guess for the iterative linear solve after calculating an averaged conductvity model. This flag turns the calculation off.

 ..
    To be added later after release of the coupled flow, transport, and ERT capability.

    ARCHIE_CEMENTATION_EXPONENT
     Archie's cementation exponent $\unitless$

    ARCHIE_SATURATION_EXPONENT
     Archie's saturation exponent $\unitless$

    ARCHIE_TORTUOSITY_EXPONENT
     Archie's tortuosity exponent $\unitless$

    CALC_MAX_TRACER_CONCENTRATION
     Causes the maximum tracer concentration (for normalization of solute concentration tracer conductivity calculation) to be calculated based on the initial concentrations specified in the initial and boundary condition and source/sinks.

    CLAY_VOLUME_FACTOR
     Clay voluem factor for Waxman-Smits $\unitless$

    CONDUCTIVITY_MAPPING_LAW
     Approach to calculating bulk electrical conductivity. Options: ARCHIE, WAXMAN_SMITS

    MAX_TRACER_CONCENTRATION
     Specify maximum tracer concentration for normalization of solute concentration tracer conductivity calculation.

    MOBILITY_DATABASE
     Database storing the mobilities $\units{\strarea\,\strelecpotential\inv\,\strinvtime}$ for aqueous species for the species conductivity calculation.

    OUTPUT_ALL_SURVEYS
     Flag that turns on output at all surveys times.

    SURFACE_ELECTRICAL_CONDUCTIVITY
     Surface electrical conductivity contribution to bulk electrical conductivity $\units{\streleccond}$

    SURVEY_TIMES
     A list of times when the ERT surveys will be measured.

    TRACER_CONDUCTIVITY
     Tracer electrical conductivity contribution to bulk electrical conductivity $\units{\streleccond}$

    WATER_CONDUCTIVITY
     Water electrical conductivity contribution to bulk electrical conductivity $\units{\streleccond}$

    WAXMAN_SMITS_CLAY_CONDUCTIVITY
     Clay electrical conductivity used in Waxman-Smiths equations $\units{\streleccond}$

Examples
--------
::

 SIMULATION
   SIMULATION_TYPE SUBSURFACE
   PROCESS_MODELS
     SUBSURFACE_GEOPHYSICS geophysics
       MODE ERT
       OPTIONS
         COMPUTE_JACOBIAN
         NO_ANALYTICAL POTENTIAL
       /
     /
   /
 END

..
   SIMULATION
     SIMULATION_TYPE SUBSURFACE
     PROCESS_MODELS
       SUBSURFACE_GEOPHYSICS geophysics
         MODE ERT
         OPTIONS
           COMPUTE_JACOBIAN
           CALC_MAX_TRACER_CONCENTRATION
           SURVEY_TIMES h 2.7778d-4 6.d0 12.d0 24.d0 # 2.778d-4 ~= 1 second
           OUTPUT_ALL_SURVEYS
           MOBILITY_DATABASE ../../../database/mobilities.dat
           ARCHIE_CEMENTATION_EXPONENT 1.9d0
           ARCHIE_SATURATION_EXPONENT 2.d0
           ARCHIE_TORTUOSITY_CONSTANT 1.d0
           SURFACE_ELECTRICAL_CONDUCTIVITY 0.002d0
           CONDUCTIVITY_MAPPING_LAW WAXMAN_SMITS
           CLAY_VOLUME_FACTOR 0.01d0
           WAXMAN_SMITS_CLAY_CONDUCTIVITY 0.003d0
         /
       /
     /
   END
