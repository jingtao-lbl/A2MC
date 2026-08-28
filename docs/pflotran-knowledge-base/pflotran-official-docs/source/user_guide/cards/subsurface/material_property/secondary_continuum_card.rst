Back to :ref:`card-index`

Back to :ref:`material-property-card`

.. _secondary-continuum-card:

SECONDARY_CONTINUUM
===================

Specifies the secondary continuum properties.

The multiple continuum model is :ref:`formally documented here <multiple_continuum>`. Multiple continuum must be set as an option under SIMULATION block to use:

 ::

   SIMULATION
     SIMULATION_TYPE SUBSURFACE
     PROCESS_MODELS
       SUBSURFACE_TRANSPORT transport
         MODE GIRT
	 OPTIONS
	   MULTIPLE_CONTINUUM
	 /
       /
     /
   END

Required Cards
--------------

TYPE <string>
 Secondary continuum geometry, must be specified first. Options include:
 SLAB, NESTED_CUBES, or NESTED_SPHERES.

NUM_CELLS <int>
  Number of cells in secondary continuum per primary cell.

POROSITY <float>
  Porosity of the matrix.

LIQUID_DIFFUSION_COEFFICIENT <float>
  Effective aqueous diffusion coefficient in the matrix, includes tortuosity.

Optional Cards:
---------------

APERTURE <float>
  Half fracture aperture [m]. Can only be specified for SLAB and
  NESTED_CUBES geometry.

EPSILON <float>
  Fracture volume fraction calculated as, :math:`\varepsilon = \frac{b}{b+L}`,
  where :math:`b` is the half fracture aperture and :math:`L` is the matrix length.
  Epsilon can be set to 1.0 to neglect secondary continuum calculation for a specific
  material.

EPSILON DATASET <string>

  Epsilon of secondary continuum specified through dataset.
  
FRACTURE_SPACING <float>
  The size of the matrix block plus the fracture aperture [m]. Can only
  be specified for NESTED_CUBES geometry.

GAS_DIFFUSION_COEFFICIENT <float>
  Effective gas diffusion coefficient in the matrix, includes tortuosity.
  Gas transport must be turned on in reactive transport mode.
  
LENGTH <float>
  Half fracture spacing [m]. Can only be specified for SLAB geometry.

LENGTH DATASET <string>
  Half fracture spacing specified through dataset.

LOG_GRID_SPACING <float>
  Enables log spacing and specifies size of outer spacing [m] with outer
  cell being the secondary cell closest to the primary. Can only be
  specified for SLAB and NESTED_CUBES geometry

MATRIX_BLOCK_SIZE <float>
  Length of largest matrix block size [m]. Can only be specified for
  NESTED_CUBES geometry.

RADIUS <float>
  Length of radius for NESTED_SPHERES geometry [m].

TEMPERATURE <float>
  Temperature of the matrix.

  
Example
-------

::

  MATERIAL_PROPERTY
     ...
     SECONDARY_CONTINUUM
       TYPE SLAB
       LENGTH 1
       NUM_CELLS 5
       EPSILON 0.00005
       LIQUID_DIFFUSION_COEFFICIENT 1.6d-10
       POROSITY 0.01
     /
   END
