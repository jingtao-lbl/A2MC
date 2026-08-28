.. _well:

WELL Model
------------

The ``WELL`` model is designed to flexibly couple to various flow and
transport modes either sequentially, quasi-implicitly, or fully
implicitly. Depending on coupling and well model type, different
governing equations can be solved. Please see each individual flow mode
for a description of the well model coupling options available. Right
now, well model coupling is available in :ref:`mode-sco2`,
:ref:`mode-hydrate`, and WIPP_FLOW mode.

Structure
~~~~~~~~~~~~~~~~~~~

The ``WELL`` model is a 1-dimensional sub-grid of the primary reservoir
domain. Where the reservoir grid is defined by grid cells, the well
sub-grid is defined by well segments. Well segments are associated with
the reservoir cells through which they pass; mass is exchanged between
well and reservoir through source/sink terms. Multiple well segments
can exist within one reservoir cell, but one well segment cannot span
multiple reservoir cells. The well can have a flexible orientation,
but multiple wells cannot intersect each other. The well solves its own
set of equations governing the distribution of mass along the 1D wellbore.
Those equations are chosen by the user and are restricted based on the flow
mode and coupling style.

Governing Equations
~~~~~~~~~~~~~~~~~~~

FULLY_IMPLICIT Coupling
-----------------------

The FULLY_IMPLICIT coupling option is available in :ref:`mode-sco2`
mode and :ref:`mode-hydrate` mode. With this option, the well model
is embedded as an extra equation in the flow mode Jacobian and residual.

*HYDROSTATIC Well Model*

Currently, the only well model type available for fully implicit coupling
is the HYDROSTATIC well model type. This well model type solves one
conservation equation in the form:

.. math::
   :label: mass-conservation-well

   \sum_{i} \Big(Q_{w,j}^{i}) = q_{w,j},

where :math:`Q_{w,j}^{i}` is the flow rate between well and reservoir of
component j in segment i of well w, and :math:`q_{w,j}` is the
user-defined surface injection rate. For a given well segment i,
:math:`Q_{w,j}` is determined by a well index and a wellbore pressure
vis-a-vis the bottomhole pressure, :math:`P_B`. :math:`P_B` is solved
as a primary variable in the flow mode. Once solved, :math:`P_B` is then
used to compute hydrostatic pressures for all well segments. Those
pressures are then used to compute well-reservoir flow rates in each well
segment.

Well Index
~~~~~~~~~~~~~~~~~~~

The well index is used to compute flow rate into or out of an individual
well segment as a function of the pressure difference between the wellbore
and the reservoir at the well segment centroid. For a given well segment,
:math:`Q_{w,j}` is determined as follows:

.. math::
   :label: flow-rate-well

   Q_{w,j}^{i} = -\frac{WI {\rho}_{j}}{\mu_j} (P_w - (P_r + {\rho}_{j} \boldsymbol{g} z_{w-r})),

where WI is the well index, :math:`P_{w}` is the wellbore pressure at the
well segment centroid, :math:`P_{r}` is the pressure of the reservoir cell
through which the well segment passes, and :math:`P_{r}` is adjusted by
a hydrostatic correction to the location of the well segment centroid.
In 3D, the well index is computed using a generalized Peacemann relationship
using well segment projections (White et al., 2013):

.. math::
   :label: well-index-well

   WI = C \sqrt{WI_{x}^{2} + WI_{y}^{2} + WI_{z}^{2}}

   WI_{x} = \frac{2\pi\sqrt{k_{y}k_{z}}L_{x}}{\ln{\frac{r_{0,x}}{r_{w}}}+s}
   WI_{y} = \frac{2\pi\sqrt{k_{x}k_{z}}L_{y}}{\ln{\frac{r_{0,y}}{r_{w}}}+s}
   WI_{z} = \frac{2\pi\sqrt{k_{x}k_{y}}L_{z}}{\ln{\frac{r_{0,z}}{r_{w}}}+s}

   r_{0,x} = 0.28\frac{({{\frac{k_y}{k_z}}^{0.5}\Delta{z}^{2}+{\frac{k_z}{k_y}}^{0.5}\Delta{y}^{2}})^{0.5}}{{\frac{k_y}{k_z}}^{0.25}+{\frac{k_z}{k_y}}^{0.25}}
   r_{0,y} = 0.28\frac{({{\frac{k_x}{k_z}}^{0.5}\Delta{z}^{2}+{\frac{k_z}{k_x}}^{0.5}\Delta{x}^{2}})^{0.5}}{{\frac{k_x}{k_z}}^{0.25}+{\frac{k_z}{k_x}}^{0.25}}
   r_{0,z} = 0.28\frac{({{\frac{k_x}{k_y}}^{0.5}\Delta{y}^{2}+{\frac{k_y}{k_x}}^{0.5}\Delta{x}^{2}})^{0.5}}{{\frac{k_x}{k_y}}^{0.25}+{\frac{k_y}{k_x}}^{0.25}}

where s is the user-defined skin factor, :math:`r_{w}` is the wellbore radius,
:math:`\Delta{x}`, :math:`\Delta{y}`, and :math:`\Delta{z}` are the reservoir
cell thicknesses in each principal dimension,and :math:`L_{x,y,z}` are the
well segment projections on each principal axis. The well index is scaled by
the casing factor C, where C = 0 for a fully-cased well and C=1 for a fully
uncased well.