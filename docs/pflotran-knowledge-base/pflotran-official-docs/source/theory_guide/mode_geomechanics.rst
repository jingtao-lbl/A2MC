.. _mode-geomechanics:

Geomechanics
------------

In PFLOTRAN, a linear elasticity model is assumed as the constitutive
model for deformation of the rock. Biot’s model is used to incorporate
the effect of flow on geomechanics. In addition, the effect of
temperature on geomechanics is considered via the coefficient of thermal
expansion. The following governing equations are used:

.. math::
   :label: Eq:mom
   
   \nabla \cdot [{\boldsymbol{\sigma}}] + \density {\boldsymbol{b}} = 0 \quad \mathrm{in} \; \Omega, 
   
.. math::
   :label: diri
   
   &{\boldsymbol{\sigma}} = \lambda \text{tr}\left({\boldsymbol{\varepsilon}}\right) + 2\mu {\boldsymbol{\varepsilon}} - \beta p {\boldsymbol{I}} - \alpha T {\boldsymbol{I}}, \\
   &{\boldsymbol{\varepsilon}} = \frac{1}{2} \left(\nabla{\boldsymbol{u}}({\boldsymbol{x}}) + [\nabla {\boldsymbol{u}}({\boldsymbol{x}})]^{T}  \right), \\
   &{\boldsymbol{u}}({\boldsymbol{x}}) = {\boldsymbol{u}}^p({\boldsymbol{x}}) \quad \mathrm{on} \; \Gamma^D,
   
.. math::
   :label: eqn:neu
   
   {\boldsymbol{\sigma}}{\boldsymbol{n}}({\boldsymbol{x}}) = t^p({\boldsymbol{x}}) \quad \mathrm{on} \; \Gamma^N, 
   
where :math:`{\boldsymbol{u}}` is the unknown displacement field,
:math:`{\boldsymbol{\sigma}}` is the Cauchy stress tensor,
:math:`\lambda` is the Lame modulus, :math:`\mu` is the shear modulus,
:math:`{\boldsymbol{b}}` is the specific body force (which is gravity in
most cases), :math:`{\boldsymbol{n}}` is the outward normal to the
boundary :math:`\Gamma^N`. Also, :math:`{\boldsymbol{u}}^p` is the
prescribed values of :math:`{\boldsymbol{u}}` on the Dirichlet part of
the boundary :math:`\Gamma^D`, and :math:`{\boldsymbol{t}}^p` is the
prescribed traction on :math:`\Gamma^N`. Additionally, :math:`\beta` is
the Biot’s coefficient, :math:`\alpha` is the coefficient of thermal
expansion, :math:`p`, :math:`T` are the fluid pressure and temperature,
obtained by solving subsurface flow problem. Also, :math:`p_0` and
:math:`T_0` are set to initial pressure and temperature in the domain,
:math:`{\boldsymbol{\varepsilon}}` is the strain tensor and
:math:`\text{tr}` is the trace of a second order tensor, :math:`\Omega`
is the domain, and :math:`{\boldsymbol{I}}` is the identity tensor. Note
that stress is assumed *positive under tension*. The above equation
also assumes that the resulting stresses and strains are relative to
the undeformed configuration. The effect of
deformation on the pore structure is accounted for via

.. math::
   :label: pore-structure
   
   \porosity = \porosity_0 +  \text{tr}({\boldsymbol{\varepsilon}}).

Given Young's modulus (:math:`{E}`) and the Poissons ratio (:math:`{\nu}`) 
of the material, the shear modulus and the Lame modulus are defined as follows:

.. math::
   :label: eqn:shear_modulus

   \mu = \frac{E}{2(1+\nu)},

and

.. math::
   :label: eqn:lame_modulus

   \lambda = \frac{\nu E}{(1+\nu)(1-2\nu)}.


Note that the above equations are solved using the finite element method
(Galerkin finite element) with the displacements solved for at the
vertices. Since, the flow equations are solved via the finite volume
method with unknowns such as pressure and temperature solved for at the
cell centers, in order to transfer data from the subsurface to
geomechanics grid without interpolation, the geomechanics grid is
constructed such that the vertices of the geomechanics grid coincide
with the cell centers of the subsurface mesh. That is, the dual mesh of
the subsurface mesh is used for the geomechanics solve.

Also, the geomechanics grid must be read in as an unstructured grid.
Even if one needs to work with a structured grid, the grid must be set
up in the unstructured grid format.
