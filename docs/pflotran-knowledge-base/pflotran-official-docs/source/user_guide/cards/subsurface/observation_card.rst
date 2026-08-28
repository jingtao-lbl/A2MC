Back to :ref:`card-index`

.. _observation-card:

OBSERVATION
===========
Sets up an observation point within the problem domain.  

**Note: Be sure to add the OBSERVATION_FILE card to the** :ref:`output-card` 
**section as this toggles on the printing of observation points to files with** 
**the suffix '*-obs-#.dat' where # is the MPI process rank.**

Required Cards:
---------------
OBSERVATION
 Opens the OBSERVATION block.

:ref:`region-card` <string>
 Specifies the name of the region (i.e. point in space) within the problem domain at which the observation is placed. Only one region may be defined per block.

**Note: One should use the singular COORDINATE keyword to define a point in space when defining the region, not a 2D surface or 3D volume, as observation points will be placed within all grid cells within the surface or volume.**

Optional Cards:
---------------
VELOCITY
 Specifies that cell centered velocities be printed for the cells being 
 observed.

AT_CELL_CENTER
 Observation data sampled at center of cell intersected by observation 
 (default).

AT_COORDINATE
 Observation data interpolated (linearly) from neighboring cell centers to 
 coordinate. **CAUTION: Interpolation of concentrations when nonlinear** 
 **geochemistry is modeled can result in erroneous results.**

AGGREGATE_METRIC
 Opens the AGGREGATE_METRIC block, which produces a separate aggregate metric (
 -agg) output file that:

  -searches the REGION associated with a given OBSERVATION, and computes the 
  aggregate metric (e.g. max value of temperature)

  -reports the location at which that max value occurs as well as all other
  OUTPUT variables of interest, at all observation times

 Currently supported AGGREGATE_METRICs:

  * MAX <string> , where <string> corresponds to the output variable of interest

Examples
--------
 ::

  OBSERVATION
    REGION well-2-9 
    VELOCITY
  /

  OBSERVATION
    REGION observation_point2 
    AT_COORDINATE
  /

  REGION observation_point3
    COORDINATE 6335.2 3992.5 107.3 
  /

  OBSERVATION
    REGION observation_region
    AGGREGATE_METRIC
      MAX TOTAL Tracer
      MAX LIQUID_SATURATION
      MAX TEMPERATURE
    /
  /
