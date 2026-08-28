.. _mode-miscible:

Mode: ``MISCIBLE``
------------------

The miscible mode applies to a mixture of water and proplyene glycol
(PPG). In terms of molar density for the mixture :math:`\eta` and mole
fractions :math:`x_i`, :math:`i`\ =1 (water), :math:`i`\ =2 (PPG), the
mass conservation equations have the form

.. math::
   :label: mass-cons-misc
   
   \frac{{{\partial}}}{{{\partial}}t} \porosity \eta x_i + {\boldsymbol{\nabla}}\cdot\left[{\boldsymbol{q}}\eta x_i - \porosity D \eta {\boldsymbol{\nabla}}x_i\right] = Q_i,

with source/sink term :math:`Q_i`. It should be noted that the mass- and
mole-fraction formulations of the conservation equations are not exactly
equivalent. This is due to the diffusion term which gives an extra term
when transformed from the mole-fraction to mass-fraction gradient.

The molar density :math:`\eta` is related to the mass density by

.. math::
   :label: molar-density-misc
   
   \eta = W^{-1} \density,

and

.. math::
   :label: W-misc
   
   W_i\eta x_i = \density y_i.

It follows that

.. math::
   :label: W-misc2
   
   W_i \eta {\boldsymbol{\nabla}}x_i = \density {\boldsymbol{\nabla}}y_i + \density y_i {\boldsymbol{\nabla}}\ln W.

The second term on the right-hand side is ignored.

Simple equations of state are provided for density [g/cm:math:`^3`],
viscosity [Pa s], and diffusivity [m:math:`^2`/s]. The density is a
function of both composition are pressrue with the form

.. math::
   :label: eos-misc

   \density(y_1,\,p) &= \density(y_1,\,p_0) + \left.\frac{{{\partial}}\density}{{{\partial}}p}\right|_{p=p_0} (p-p_0),\\
                 &= \density(y_1,\,p_0) \big(1+\beta (p-p_0)\big),

with the compressibility :math:`\beta(y_1)` given by

.. math::
   :label: comp-misc

   \beta &= \left.\frac{1}{\density}\frac{{{\partial}}\density}{{{\partial}}p}\right|_{p=p_0},\\
         &= 4.49758\times 10^{-10} y_1 + 5\times 10^{-10}(1-y_1),

and the mixture density at the reference pressure :math:`p_0` taken as
atmospheric pressure is given by

.. math::
   :label: mix-density-misc
   
   \density(y_1,\,p_0) = \Big(\big((0.0806 y_1 - 0.203) y_1 + 0.0873\big) y_1 + 1.0341\Big)10^3,

with mass fraction of water :math:`y_1`. The viscosity and diffusivity
have the forms

.. math::
   :label: viscosity-misc
   
   \mu(y_1) = 10^{\big(1.6743 (1-y_1) - 0.0758\big)} 10^{-3},

and

.. math::
   :label: diffusivity-misc
   
   D(y_1) = \Big(\big(((-4.021 y_1 + 9.1181) y_1 - 5.9703) y_1
        + 0.4043\big) y_1 + 0.5687\Big) 10^{-9},

The mass fraction is related to mole fraction according to

.. math::
   :label: mass-frac-misc
   
   y_1 = \frac{x_1 W_{\rm H_2O}}{W},

where the mean formula weight :math:`W` is given by

.. math::
   :label: mean-formula-weight-misc
   
   W = x_1 W_{\rm H_2O} + x_2 W_{\rm PPG},

with formula weights for water and proplyene glycol equal to
:math:`W_{\rm H_2O}` = 18.01534 and :math:`W_{\rm PPG}` = 76.09
[kg/kmol].

Global mass conservation satisfies the relation

.. math::
   :label: global-mass-cons-misc
   
   \frac{d}{dt}M_i = -\int{\boldsymbol{F}}_i\cdot{\boldsymbol{dS}}+ \int Q_i dV,

with

.. math::
   :label: Mi-misc
   
   M_i = \int \porosity \eta x_i dV.

In terms of mass fractions and mass density

.. math::
   :label: Mi2-misc
   
   M_i^m = W_i M_i = \int \porosity \density y_i dV.