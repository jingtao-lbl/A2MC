.. _mode-ert:

ERT Mode
--------

Governing Equations
~~~~~~~~~~~~~~~~~~~

The geophyscs ``ERT`` forward modeling mode is governed by the following electrostatic Poisson equation

.. math::
   \pmb{\nabla} \cdot \bulkelectricalconductivity \pmb{\nabla} \electricalpotential = -Q_I,
   :label: ert-eq1

where $\electricalpotential$ electrical potential [V], $\bulkelectricalconductivity$ is bulk electrical conductivity [S m$^{-1}$], and $Q_I$ is electrical current [A] injected through an electrode at a point in space.

If side and bottom boundaries $\partial\Gamma$ of the 3D computational domain $\Gamma$ are located at sufficiently far from the current injection location, the potential and the normal component of the current density $\bulkelectricalconductivity \frac{\partial \electricalpotential}{\partial n}$ asymptotically approach to zero. On the top or surface boundary $\partial\Gamma_\mathrm{S}$, the normal current density $\bulkelectricalconductivity \frac{\partial \electricalpotential}{\partial n}$ is zero as no current flows through the earth surface along the outward normal vector. Consequently, we can impose zero Dirichlet or Neumann boundary conditions at the side boundaries and zero Neumann boundary at the surface boundary

.. math::
   \electricalpotential \vert_{\partial\Gamma} = 0 \quad \mathrm{or} \quad \frac{\partial \electricalpotential}{\partial n} \vert_{\partial\Gamma} = 0, \quad \mathrm{and} \quad \frac{\partial \electricalpotential}{\partial n} \vert_{\partial\Gamma_\mathrm{S}} = 0 \,. 
   :label: ert-eq2

..
  Example of dummy reference to Eq. :eq:`ert-eq1` and :eq:`ert-eq2`


