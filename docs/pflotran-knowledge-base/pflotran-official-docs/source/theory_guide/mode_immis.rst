.. _mode-immis:

Mode: ``IMMIS``
---------------

The ``IMMIS`` mode applies to multiple completely immiscible phases. The
code PIMS, parallel immiscible multiphase flow simulator, is a
simplified version of the MPHASE mode in which the dependency on
thermodynamic relations have been removed, since for immiscible systems
the solubility is identically zero for each component. In this case the
number of components is equal to the number of phases, or degrees of
freedom associated with each node for an isothermal system. The
immiscible property removes the variable switching strategy used in
MPHASE, which may be the most numerically difficult part of PFLOTRAN,
and may cause problems for multi-level solvers. The governing equations
solved by PIMS are given by

.. math::
   :label:  mass
      
   \frac{{{\partial}}}{{{\partial}}t}\big(\porosity\density_{{\alpha}}^{} \saturation_{{\alpha}}^{}\big) + {\boldsymbol{\nabla}}\cdot \big(\density_{{\alpha}}^{} {\boldsymbol{q}}_{{\alpha}}\big) = Q_{{\alpha}},

where the subscript :math:`{{\alpha}}` denotes an immiscible phase.

In this equation :math:`\porosity` is porosity, :math:`s_{{\alpha}}`,
:math:`\density_{{\alpha}}` refer to the :math:`{{\alpha}}`\ th phase
saturation and density, respectively,
:math:`{\boldsymbol{q}}_{{\alpha}}` is the Darcy velocity of the
:math:`{{\alpha}}`\ th phase given by

.. math::
   :label: darcy-immis
   
   {\boldsymbol{q}}_{{\alpha}}= -\frac{kk_{{\alpha}}}{\mu_{{\alpha}}} \big({\boldsymbol{\nabla}}p-\density_{{\alpha}}g \hat{\boldsymbol{z}}\big),

with permeability :math:`k`, relative permeability :math:`k_{{\alpha}}`,
fluid viscosity :math:`\mu_{{\alpha}}`, and :math:`Q_{{\alpha}}` is the
source/sink term. The selection of primary variables are pressure
:math:`p` and :math:`n-1` independent phase saturation variables
:math:`s_{{\alpha}}, {{\alpha}}=1,...,n-1` with

.. math::
   :label: variables-immis
   
   \sum_{{{\alpha}}=1}^n \saturation_{{\alpha}}= 1.

The mass conservation equations are coupled to the energy balance
equation given by

.. math::
   :label: mass-energy-immis
   
   \frac{{{\partial}}}{{{\partial}}t} \Big(\porosity\sum_{{\alpha}}s_{{\alpha}}\density_{{\alpha}}U_{{\alpha}}+ (1-\porosity) \density_r C_r T\Big) + {\boldsymbol{\nabla}}\cdot\Big(\sum_{{\alpha}}\density_{{\alpha}}{\boldsymbol{q}}_{{\alpha}}H_{{\alpha}}- \kappa{\boldsymbol{\nabla}}T\Big) = Q_e,

where :math:`U_{{\alpha}}`, :math:`H_{{\alpha}}` denote the internal
energy and enthalpy of the :math:`{{\alpha}}`\ th fluid phase,
:math:`\kappa` denotes the thermal conductivity of the bulk porous
medium, :math:`\density_r`, :math:`C_r` denote the rock density and heat
capacity, and :math:`T` refers to the temperature. Thus the number of
equations is equal to number of phases plus one, which is equal to the
number of unknowns: (:math:`p`, :math:`T`, :math:`s_1`, …,
:math:`s_{n-1}`).