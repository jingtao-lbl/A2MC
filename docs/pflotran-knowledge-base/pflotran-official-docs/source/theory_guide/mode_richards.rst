.. _mode-richards:

RICHARDS Mode
-------------

Governing Equations
~~~~~~~~~~~~~~~~~~~

``RICHARDS`` mode applies to single phase, variably saturated, isothermal
systems. The governing mass conservation equation is given by

.. math::
   :label: mass-conv-richards

   \frac{{{\partial}}}{{{\partial}}t}\left(\porosity s\eta\right) + {\boldsymbol{\nabla}}\cdot\left(\eta{\boldsymbol{q}}\right) = Q_w,

with Darcy flux :math:`{\boldsymbol{q}}` defined as

.. math::
   :label: darcy-richards

   {\boldsymbol{q}} = -\frac{kk_r(s)}{\mu} {\boldsymbol{\nabla}}\left(P-\density gz\right).

Here, 
:math:`\porosity` denotes porosity [-], 
:math:`s` saturation [m\ :math:`^3`  m\ :math:`^{-3}`], 
:math:`\eta` molar water density [kmol m\ :math:`^{-3}`], 
:math:`\density` mass water density [kg m\ :math:`^{-3}`], 
:math:`{\boldsymbol{q}}` Darcy flux [m s\ :math:`^{-1}`], 
:math:`k` intrinsic permeability [m\ :math:`^2`],
:math:`k_r` relative permeability [-], 
:math:`\mu` viscosity [Pa s],
:math:`P` pressure [Pa], 
:math:`{\boldsymbol{g}}` gravity [m s\ :math:`^{-2}`].
Supported
relative permeability functions :math:`k_r` for Richards’ equation
include van Genuchten, Books-Corey and Thomeer-Corey, while the
saturation functions include Burdine and Mualem. Water density and
viscosity are computed as a function of temperature and pressure through
an equation of state for water. The source/sink term :math:`Q_w` [kmol
m\ :math:`^{-3}` s\ :math:`^{-1}`] has the form

.. math::
   :label: source-sink-richards

   Q_w = \frac{q_M}{W_w} \delta({\boldsymbol{r}}-{\boldsymbol{r}}_{ss}),

where :math:`q_M` denotes a mass rate in kg/m\ :math:`^{3}`/s, and
:math:`{\boldsymbol{r}}_{ss}` denotes the location of the source/sink.

