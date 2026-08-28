Back to :ref:`card-index`

.. _output-card:

OUTPUT
====== 
Defines the type and frequency of output.

Required Cards:
---------------
OUTPUT
 Opens output block. 

Optional Sub-blocks and Cards:
-------------------------------

SNAPSHOT_FILE
 Opens the snapshot output file block. A snapshot file gives the value of 
 specified variables over the entire domain at a single moment in time.

OBSERVATION_FILE
 Opens the observation output file block. An observation file gives the values 
 of specified variables at a point at several moments in time.

MASS_BALANCE_FILE
 Opens the mass balance output file block. Mass balance output will be 
 generated, which includes global mass balance as well as fluxes at all 
 boundaries for water and chemical species specified for output in the 
 :ref:`chemistry-card`. **Note that fluxes across prescribed conditions,
 total energy balance and energy fluxes are not included in 
 mass balance files.**

CONSERVATION_FILE
 Opens the conservation output file block. Total mass and energy
 conservation output will be generated, which includes global mass and
 energy balance as well as mass and energy fluxes at all boundaries,
 prescribed boundaries and source/sinks for fluids and 
 chemical species specified for output in the :ref:`chemistry-card`.
 Note that these files are different from mass balance files to ensure the
 backward compatibility of mass balance files in external workflows.
 **Conservation files will likely be the format of choice for simulation
 mass and energy conservation in the future.**

Within the SNAPSHOT_FILE, OBSERVATION_FILE, MASS_BALANCE_FILE, and 
CONSERVATION_FILE blocks, the following cards can be specified:

 TIMES <string> <float> ... <float>
  Specifies a list of times when output will be generated. <string> indicates 
  the time unit applied to the following <float>s that indicate the times.

 PERIODIC TIMESTEP <int> 
  Generates output every <int> number of timesteps.

 PERIODIC TIME <int or float> <string>
  Generates output at every <int or float> units of time, where <string> defines 
  the units of time.

 NO_PRINT_INITIAL
  If included, the initial state of the system will not be printed to the output 
  file.

 NO_PRINT_FINAL
  If included, the final state of the system will not be printed to the output 
  file.

Within the SNAPSHOT_FILE and OBSERVATION_FILE blocks (but not 
CONSERVATION_FILE or MASS_BALANCE_FILE), the variables to be saved can 
be specified:

.. _output-variables:

 VARIABLES
  Opens a block which lists variables to be included in the output file. Options include:

   AIR_PRESSURE - Air partial pressure $\units{\strpressure}$

   ARCHIE_CEMENTATION_EXPONENT - Archie's law cementation exponent $\units{\strnull}$

   ARCHIE_SATURATION_EXPONENT - Archie's law saturation exponent $\units{\strnull}$

   ARCHIE_TORTUOSITY_CONSTANT - Archie's law tortuosity exponent $\units{\strnull}$

   CAPILLARY_PRESSURE - Capillary pressure $\units{\strpressure}$

   COORDINATES - X, Y and Z coordinates $\units{\strlength}$

   EFFECTIVE_POROSITY - Effective porosity $\units{\strporosity}$

   ELECTRICAL_CONDUCTIVITY - Electrical conductivity $\units{\streleccond}$

   ELECTRICAL_POTENTIAL_DIPOLE - Electrical potential dipole $\units{\strelecpotential}$

   ELECTRICAL_POTENTIAL - Electrical potential $\units{\strelecpotential}$

   GAS_DENSITY - Gas phase mass density $\units{\strmassdensity}$

   GAS_DENSITY_MOLAR - Gas phase molar density $\units{\strmoldensity}$

   GAS_ENERGY - Gas phase energy $\units{\strenergy}$

   GAS_ENERGY_PER_VOLUME - Gas phase energy density $\units{\strenergydensity}$

   GAS_MASS_FRACTIONS - Gas phase mass fractions $\units{\strmassfraction{componsnet}{gas}}$

   GAS_MOBILITY - Gas phase mobility $\units{\strnull}$

   GAS_MOLE_FRACTIONS - Gas phase mole fractions $\units{\strmolfraction{component}{gas}}$

   GAS_PRESSURE - Gas phase pressure $\units{\strpressure}$

   GAS_PERMEABILITY - Gas permeability (same as PERMEABILITY) $\units{\strarea}$

   GAS_PERMEABILITY_X - Gas X permeability (same as PERMEABILITY_X) $\units{\strarea}$

   GAS_PERMEABILITY_Y - Gas Y permeability (same as PERMEABILITY_Y) $\units{\strarea}$

   GAS_PERMEABILITY_Z - Gas Z permeability (same as PERMEABILITY_Z) $\units{\strarea}$

   GAS_RELATIVE_PERMEABILITY - Gas phase relative permeability $\units{\strnull}$

   GAS_SATURATION - Gas phase saturation $\units{\strgassaturation}$

   GAS_VISCOSITY - Gas phase viscosity $\units{\strviscosity}$

   HYDRATE_SATURATION - Hydrate phase saturation $\units{\strsaturation{hydrate}}$

   ICE_SATURATION - Ice phase saturation $\units{\strsaturation{ice}}$

   K_ORTHOGONALITY_ERROR - 

   LIQUID_DENSITY - Liquid phase mass density $\units{\strmassdensity}$

   LIQUID_DENSITY_MOLAR - Liquid phase molar density $\units{\strmoldensity}$

   LIQUID_ENERGY - Liquid phase energy $\units{\strenergy}$

   LIQUID_ENERGY_PER_VOLUME - Gas phase energy density $\units{\strenergydensity}$

   LIQUID_HEAD - Liquid phase pressure head $\units{\strlength}$

   LIQUID_MASS_FRACTIONS - Liquid phase mass fractions $\units{\strmassfraction{component}{liquid}}$

   LIQUID_MOBILITY - Liquid phase mobility $\units{\strinvviscosity}$

   LIQUID_MOLE_FRACTIONS - Liquid phase mole fractions $\units{\strmolfraction{component}{liquid}}$

   LIQUID_PRESSURE - Liquid phase pressure $\units{\strpressure}$

   LIQUID_RELATIVE_PERMEABILITY - $\units{\strnull}$

   LIQUID_SATURATION - $\units{\strliquidsaturation}$

   LIQUID_VISCOSITY - $\units{\strviscosity}$

   MINERAL_POROSITY - $\units{\strvolfrac{mineral}{bulk}}$

   MATERIAL_ID - $\units{\strnull}$

   MATERIAL_ID_KLUDGE_FOR_VISIT - $\units{\strnull}$

   MAXIMUM_PRESSURE - $\units{\strpressure}$

   MINERAL_POROSITY - $\units{\strvolfrac{mineral}{bulk}}$

   NATURAL_ID - $\units{\strnull}$

   PERMEABILITY - $\units{\strlength}$

   PERMEABILITY_X - $\units{\strlength}$

   PERMEABILITY_Y - $\units{\strlength}$

   PERMEABILITY_Z - $\units{\strlength}$

   PERMEABILITY_XY - $\units{\strlength}$

   PERMEABILITY_XZ - $\units{\strlength}$

   PERMEABILITY_YZ - $\units{\strlength}$

   POROSITY - $\units{\strporosity}$

   PRECIPITATE_SATURATION - $\units{\strsaturation{precipitate}}$

   PROCESS_ID - $\units{\strnull}$

   RESIDUAL - $\units{???}$

   SALINITY - $\units{???}$

   SATURATION_PRESSURE - $\units{\strpressure}$

   SOIL_COMPRESSIBILITY - $\units{???}$

   SOIL_REFERENCE_PRESSURE - $\units{\strpressure}$

   SOLUTE_CONCENTRATION - $\units{\strinvvolume}$

   SURFACE_ELECTRICAL_CONDUCTIVITY - $\units{\streleccond}$

   TEMPERATURE - $\units{\strtemperature}$

   THERMODYNAMIC_STATE - $\units{\strnull}$

   TORTUOSITY - $\units{\strnull}$

   VAPOR_PRESSURE - $\units{\strpressure}$

   VOLUME - $\units{\strvolume}$

   WAXMAN_SMITS_CLAY_CONDUCTIVITY - $\units{\strnull}$

   WGG - $\units{\strmassfraction{air}{gas}}$

   WGL - $\units{\strmassfraction{air}{liquid}}$

   WLG - $\units{\strmassfraction{water}{gas}}$

   WLL - $\units{\strmassfraction{water}{liquid}}$

   WSL - $\units{\strmassfraction{salt}{gas}}$

   X_COORDINATE - $\units{\strlength}$

   XGG - $\units{\strmolfraction{air}{gas}}$

   XGL - $\units{\strmolfraction{air}{liquid}}$

   XLG - $\units{\strmolfraction{water}{gas}}$

   XLL - $\units{\strmolfraction{water}{liquid}}$

   XSL - $\units{\strmolfraction{salt}{liquid}}$

   Y_COORDINATE - $\units{\strlength}$

   Z_COORDINATE - $\units{\strlength}$

To obtain the most up to date list, look in output.F90:OutputVariableRead().
  If you do not include the ``VARIABLES`` block, then a default list of variables
  will be populated dependent on the flow mode. However, if you prefer no
  default output, you can turn defaults off by including ``NO_FLOW_VARIABLES`` 
  or ``NO_ENERGY_VARIABLES``.
  
Within the SNAPSHOT_FILE block only, the following cards can be specified:

 FORMAT <string>
  Specifies the output file type for snapshots in time. Options available include TECPLOT BLOCK, TECPLOT POINT, VTK, HDF5, HDF5 SINGLE_FILE, or HDF5 MULTIPLE_FILES.  The default for HDF5 is SINGLE_FILE. For HDF5 MULTIPLE_FILES, each snapshot will be printed into a new HDF5 file. The optional keyword TIMES_PER_FILE <int> can be included, which will limit the number of snapshots printed to each HDF5 file to <int> number of snapshots.  **The POINT format is not supported in parallel. PFLOTRAN will switch from POINT to BLOCK if the number of cores employed is greater than one.**

 EXTEND_HDF5_TIME_FORMAT
  Extends the time format in group names to 13 digits of precision (default = 6 digits of precision). This greater precision enables the printing of very small time step increments.'

Within the MASS_BALANCE_FILE block only, you can specify the sub-block NO_PRINT_SOURCE_SINK which will not print out source and sinks to the mass ballance file and the sub-block TOTAL_MASS_REGIONS which specifies a list of regions where the total component mass is calculated within the region. The total component mass includes all species in the aqueous, sorbed, and precipitated states is outputted in [mols] (see examples below).

Optional Cards
--------------
The following cards are placed within the OUTPUT block, but outside of the
SNAPSHOT_FILE, OBSERVATION_FILE, MASS_BALANCE_FILE, or CONSERVATION_FILE blocks.

ASCII_DIGITS_OF_PRECISION <int> <optional int>
  Modifies the number of significant digits in double precision data written to
  ASCII formated output files. The first values is the number of digits of
  of precision. The optional value is the number of digits in the exponent (2 or 3).

PERIODIC_OBSERVATION TIME <float> <string> **(DEPRECATED)**
  Generates output for observation points and mass balance at every <float> units of time, where <string> defines the units of time.

PERIODIC_OBSERVATION TIMESTEP <int> **(DEPRECATED)**
  Generates output for observation points and mass balance at every <int> number of timesteps.

TIME_UNITS <string>
 Specifies the time units printed in screen and file output (e.g. s, day, yr)

SCREEN PERIODIC <int>
 Prints output to the screen every <int> time steps.

VARIABLES
 Opens the variables block. Variables listed outside of the ?_FILE blocks will applied to each ?_FILE block that did not specify its own variable list. If no variable list is specified within the ?_FILE blocks or within the OUTPUT block, defaults will be used.
 However, if you prefer no default output, you can turn defaults off by 
 including ``NO_FLOW_VARIABLES`` or ``NO_ENERGY_VARIABLES``.
 
VELOCITY_AT_CENTER / VELOCITY_AT_FACE
 Determines where the velocities that written are calculated (cell vs face center).

Examples
--------
 ::

  OUTPUT
    ASCII_DIGITS_OF_PRECISION 9 3
    TIME_UNITS yr
    SNAPSHOT_FILE
      FORMAT HDF5 MULTIPLE_FILES TIMES_PER_FILE 10 
      NO_PRINT_INITIAL
      PERIODIC TIME 100 day
      VARIABLES
        LIQUID_PRESSURE
        GAS_PRESSURE
        CAPILLARY_PRESSURE
        TEMPERATURE
      /
    /
    OBSERVATION_FILE
      NO_PRINT_INITIAL
      NO_PRINT_FINAL
      TIMES y 0.23d0 9.712d0
      VARIABLES
        TEMPERATURE
        POROSITY
        PERMEABILITY
      /
    /
    MASS_BALANCE_FILE
      PERIODIC TIME 1 w between 1 y and 2 y
      PERIODIC TIMESTEP 5
      TOTAL_MASS_REGIONS
        all
        top
      /
    /
    CONSERVATION_FILE
      PERIODIC TIMESTEP 1
    /
    SCREEN PERIODIC 15
  /

 ::

  OUTPUT
    ASCII_DIGITS_OF_PRECISION 6
    VARIABLES
      LIQUID_PRESSURE
      POROSITY
      TORTUOSITY
    /
    SNAPSHOT_FILE
      FORMAT TECPLOT BLOCK
      PERIODIC TIME 1 y
    /
    OBSERVATION_FILE
      TIMES day 10 20 30
      NO_PRINT_FINAL
    /
  /

 ::

  OUTPUT
    VARIABLES
      NO_FLOW_VARIABLES
      NO_ENERGY_VARIABLES
    /
    SNAPSHOT_FILE
      FORMAT TECPLOT BLOCK
      PERIODIC TIME 1 y
    /
    OBSERVATION_FILE
      TIMES day 10 20 30
      NO_PRINT_FINAL
    /
  /
