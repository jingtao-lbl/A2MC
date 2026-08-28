Back to :ref:`card-index`

.. _fluid-property-card:

FLUID_PROPERTY
==============
Defines fluid properties (e.g. diffusion coefficient, etc.). 

Required Cards:
---------------
FLUID_PROPERTY
 Opens the fluid property block.

DIFFUSION_COEFFICIENT <float>
 Molecular diffusion coefficient [m\ :sup:`2`\/s]

Required Cards in GENERAL mode:
-------------------------------
FLUID_PROPERTY
 Opens the fluid property block.

PHASE [LIQUID, GAS]
 Specifies the fluid phase.

DIFFUSION_COEFFICIENT <float>
 Molecular diffusion coefficient [m\ :sup:`2`\/s]

Required for temperature-dependent diffusion:
---------------------------------------------
DIFFUSION_ACTIVATION_ENERGY <float>
 Diffusion activation energy for temperature dependent diffusion calculated
 with the Arrhenius equation. [J/mol]

Examples
--------
 ::

  FLUID_PROPERTY
    DIFFUSION_COEFFICIENT 1.d-9
  /

  FLUID_PROPERTY
    PHASE LIQUID
    DIFFUSION_COEFFICIENT 1.d-9
  /
  FLUID_PROPERTY
    PHASE GAS
    DIFFUSION_COEFFICIENT 2.1d-5
  /

  FLUID_PROPERTY
    DIFFUSION_COEFFICIENT 1.d-9
    DIFFUSION_ACTIVATION_ENERGY 12.6 kJ/mol
  /

