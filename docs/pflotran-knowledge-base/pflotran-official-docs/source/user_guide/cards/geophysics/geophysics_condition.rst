Back to :ref:`card-index`

.. _geophysics-condition-card:

GEOPHYSICS_CONDITION
======================
Sets geophysics boundary conditions. No initial conditions are needed as the geophysics ``ert`` mode is a steady-state problem.  

Required Cards:
---------------
GEOPHYSICS_CONDITION <string>
 Opens the GEOPHYSICS_CONDITION block, where <string> is the assigned name of the 
 geophysics condition so that it can be referred to in card 
 :ref:`boundary-condition-card` or :ref:`initial-condition-card`

TYPE <boundary_condition_type>
 Specifies the type of the geophysical boundary condition. Options for TYPE are 
  
 TYPE [DIRICHLET, ZERO_GRADIENT]

 * DIRICHLET: specifies a zero Dirichlet or zero potential across the entire condition. See Eq. :eq:`ert-eq2` of ``ERT`` mode governing equations for details.
 * ZERO_GRADIENT: specifies a zero Neumann or zero flux across the entire condition. See Eq. :eq:`ert-eq2` of ``ERT`` mode governing equations for details. 


Examples
--------

 ::



  GEOPHYSICS_CONDITION boundary_potential
    TYPE DIRICHLET
  END

  GEOPHYSICS_CONDITION zero_flux
    TYPE ZERO_GRADIENT
  END





