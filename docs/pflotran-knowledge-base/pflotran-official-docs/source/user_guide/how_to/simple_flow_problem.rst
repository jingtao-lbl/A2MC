.. _simple-flow-problem:

Simple Flow Problem Example
===========================

This input file will run a vertical 1D column with variable saturated flow using
``RICHARDS`` Mode.

|
| #Description: 1D infiltration
| 
| SIMULATION
|   SIMULATION_TYPE SUBSURFACE
|   PROCESS_MODELS
|     SUBSURFACE_FLOW flow
|       MODE RICHARDS
|     /
|   /
| END
| 
| SUBSURFACE
|
| #=========================== discretization ===================================
| :ref:`grid-card`
|   TYPE structured
|   ORIGIN 0.d0 0.d0 0.d0
|   NXYZ 1 1 10
|   DXYZ 
|     1.d0 
|     1.d0 
|     1.d0 
|   /
| END
| 
| #=========================== material properties ==============================
| :ref:`material-property-card` soil
|   ID 1
|   POROSITY 0.33
|   TORTUOSITY 0.5d0
|   :ref:`characteristic-curves-card` cc1
|   PERMEABILITY
|     PERM_X 1.d-10 ! ~100 m/d
|     PERM_Y 1.d-10
|     PERM_Z 1.d-10
|   /
| /
| 
| #=========================== saturation functions =============================
| :ref:`characteristic-curves-card` cc1
|   SATURATION_FUNCTION VAN_GENUCHTEN
|     LIQUID_RESIDUAL_SATURATION 0.1d0
|     M 0.8d0
|     ALPHA 1.d-4
|   /
|   PERMEABILITY_FUNCTION MUALEM_VG_LIQ
|     LIQUID_RESIDUAL_SATURATION 0.1d0
|     M 0.8d0
|   /
| /
| 
| #=========================== output options ===================================
| :ref:`output-card`
|   FORMAT TECPLOT POINT
| /
| 
| #=========================== times ============================================
| :ref:`time-card`
|   FINAL_TIME 10.d0 y
|   MAXIMUM_TIMESTEP_SIZE 0.1d0 y
| /
| 
| #=========================== regions ==========================================
| :ref:`region-card` all
|   COORDINATES
|     0.d0 0.d0 0.d0
|     1.d0 1.d0 10.d0
|   /
| END
| 
| :ref:`region-card` top
|   COORDINATES
|     0.d0 0.d0 10.d0
|     1.d0 1.d0 10.d0
|   /
|   FACE TOP
| END
| 
| :ref:`region-card` bottom
|   COORDINATES
|     0.d0 0.d0 0.d0
|     1.d0 1.d0 0.d0
|   /
|   FACE BOTTOM
| END
| 
| #=========================== flow conditions ==================================
| :ref:`flow-condition-card` top
|   TYPE
|     LIQUID_FLUX NEUMANN
|   /
|   LIQUID_FLUX 3.171d-10  ! 1 cm/yr
| END
| 
| :ref:`flow-condition-card` initial
|   TYPE
|     LIQUID_PRESSURE HYDROSTATIC
|   /
|   LIQUID_PRESSURE 101325.d0
| END
| 
| #=========================== condition couplers ===============================
| # initial condition
| :ref:`initial-condition-card`
|   :ref:`flow-condition-card` initial
|   :ref:`region-card` all
| END
| 
| # top boundary condition
| :ref:`boundary-condition-card`
|   :ref:`flow-condition-card` top
|   :ref:`region-card` top
| END
| 
| # bottom boundary condition
| :ref:`boundary-condition-card`
|   :ref:`flow-condition-card` initial
|   :ref:`region-card` bottom
| END
| 
| #=========================== stratigraphy couplers ============================
| :ref:`strata-card`
|   :ref:`region-card` all
|   MATERIAL soil
| END
|
| END_SUBSURFACE

