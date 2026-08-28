.. _mode-general:

GENERAL Mode
------------

Governing Equations
~~~~~~~~~~~~~~~~~~~

The ``GENERAL`` mode involves two phase liquid water-gas flow coupled
to the reactive transport mode. Mass conservation equations have the
form

.. math::
   :label: mass-conservation-general
   
   \frac{{{\partial}}}{{{\partial}}t} \porosity \Big(s_l^{} \density_l^{} x_i^l + \saturation_g^{} \density_g^{} x_i^g \Big) + {\boldsymbol{\nabla}}\cdot\Big({\boldsymbol{q}}_l^{} \density_l^{} x_i^l + {\boldsymbol{q}}_g \density_g^{} x_i^g -\porosity \saturation_l^{} D_l^{} \density_l^{} {\boldsymbol{\nabla}}x_i^l -\porosity \saturation_g^{} D_g^{} \density_g^{} {\boldsymbol{\nabla}}x_i^g \Big) = Q_i^{},

for liquid and gas saturation :math:`s_{l,\,g}^{}`, density
:math:`\density_{l,\,g}^{}`, diffusivity :math:`D_{l,\,g}^{}`, Darcy
velocity :math:`{\boldsymbol{q}}_{l,\,g}^{}` and mole fraction
:math:`x_i^{l,\,g}`. The energy conservation equation can be written in
the form

.. math::
   :label: energy-conservation-general
   
   \sum_{{{\alpha}}=l,\,g}\left\{\frac{{{\partial}}}{{{\partial}}t} \big(\porosity \saturation_{{\alpha}}\density_{{\alpha}}U_{{\alpha}}\big) + {\boldsymbol{\nabla}}\cdot\big({\boldsymbol{q}}_{{\alpha}}\density_{{\alpha}}H_{{\alpha}}\big) \right\} + \frac{{{\partial}}}{{{\partial}}t}\big( (1-\porosity)\density_r C_p T \big) - {\boldsymbol{\nabla}}\cdot (\kappa{\boldsymbol{\nabla}}T) = Q,

as the sum of contributions from liquid and gas fluid phases and rock,
with internal energy :math:`U_{{\alpha}}` and enthalpy
:math:`H_{{\alpha}}` of fluid phase :math:`{{\alpha}}`, rock heat
capacity :math:`C_p` and thermal conductivity :math:`\kappa`. Note that

.. math::
   :label: internal-energy-general
   
   U_{{\alpha}}= H_{{\alpha}}-\frac{P_{{\alpha}}}{\density_{{\alpha}}}.

Thermal conductivity :math:`\kappa` is determined from :ref:`thermal-characteristic-curves-card`, where the ``DEFAULT`` option uses the equation
from Somerton et al., 1974:

.. math::
   :label: cond
      
   \kappa = \kappa_{\rm dry} + \sqrt{s_l^{}} (\kappa_{\rm sat} - \kappa_{\rm dry}),

where :math:`\kappa_{\rm dry}` and :math:`\kappa_{\rm sat}` are dry and
fully saturated rock thermal conductivities, respectively.

The Darcy velocity of the :math:`\alpha^{th}` phase is equal to

.. math::
   :label: darcy_velocity_general

   \boldsymbol{q}_\alpha = -\frac{k k^{r}_{\alpha}}{\mu_\alpha} \boldsymbol{\nabla} (p_\alpha - \gamma_\alpha \boldsymbol{g} z), \ \ \ (\alpha=l,g),
   
where :math:`\boldsymbol{g}` denotes the acceleration of gravity, :math:`k` denotes the saturated 
permeability, :math:`k^{r}_{\alpha}` the relative permeability, 
:math:`\mu_\alpha` the viscosity, :math:`p_\alpha` the pressure of the 
:math:`\alpha^{th}` fluid phase, and

.. math::
   :label: gamma

   \gamma_\alpha^{} = W_\alpha^{} \density_\alpha^{},

with :math:`W_\alpha` the gram formula 
weight of the :math:`\alpha^{th}` phase 

.. math::
   :label: gram-formula-weight
   
   W_\alpha = \sum_{i=w,\,a} W_i^{} x_i^\alpha,

where :math:`W_i` refers to the formula weight of the :math:`i^{th}` component.

.. _pc-sat-functions-general:

Capillary Pressure - Saturation Functions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Capillary pressure is related to effective liquid saturation by the van 
Genuchten and Brooks-Corey relations, as described under the sections
:ref:`VG-saturation-function-richards` and 
:ref:`BC-saturation-function-richards` under :ref:`mode-richards`. Because both 
a liquid (wetting) and gas (non-wetting) phase are considered, the effective 
saturation :math:`s_e` in the van Genuchten and Brooks-Corey relations under 
:ref:`mode-richards` becomes the effective liquid saturation
:math:`s_{el}` in the multiphase formulation. Liquid saturation :math:`s_l` is
obtained from the effective liquid saturation by

.. math::
   :label: liq-sat
   
   \saturation_{l} = \saturation_{el}s_0 - \saturation_{el}s_{rl} + \saturation_{rl},

where :math:`s_{rl}` denotes the liquid residual saturation, and :math:`s_0`
denotes the maximum liquid saturation. The gas saturation can be obtained from
the relation 

.. math::
   :label: phase-sum

   \saturation_l + \saturation_g = 1

The effective gas saturation :math:`s_{eg}` is defined by the relation

.. math::
   :label: \saturation_eg

   \saturation_{eg} = 1 - \frac{s_l-s_{rl}}{1-s_{rl}-s_{rg}}
   
Additionally, a linear relationship between capillary pressure :math:`p_c` and 
effective liquid saturation can be described as

.. math::
   :label: linear_pc_sat
   
   \saturation_{el} = {{p_c-p_c^{max}}\over{\frac{1}{\alpha}-p_c^{max}}}
   
where :math:`\alpha` is a fitting parameter representing the air entry pressure
[Pa]. The inverse relationship for capillary pressure is

.. math::
   :label: linear_sat_pc

   p_c = \left({\frac{1}{\alpha}-p_c^{max}}\right)s_{el} + p_c^{max}
   
.. _relative-permeability-functions-general:
   
Relative Permeability Functions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Two forms of each relative permeability function are implemented based on
the Mualem and Burdine formulations as in :ref:`mode-richards`, but the 
effective liquid saturation :math:`s_{el}` and the effective gas saturation
:math:`s_{eg}` are used. A summary of the relationships used can be found in
Chen et al. (1999), where the tortuosity 
:math:`\eta` is set to :math:`1/2`. The implemented relative permeability 
functions include: Mualem-van Genuchten, Mualem-Brooks-Corey, Mualem-linear,
Burdine-van Genuchten, Burdine-Brooks-Corey, and Burdine-linear. For each 
relationship, the following definitions apply:

.. math::

   S_{el} = \frac{S_{l}-S_{rl}}{1-S_{rl}}
   
   S_{eg} = \frac{S_{l}-S_{rl}}{1-S_{rl}-S_{rg}}

For the Mualem relative permeability function based on the van Genuchten
saturation function, the liquid and gas relative permeability functions are 
given by the expressions

.. math::
   :label: kr_mualem_vg
   
   k^{r}_{l} =& \sqrt{s_{el}} \left\{1 - \left[1- \left( \saturation_{el} \right)^{1/m} \right]^m \right\}^2
   
   k^{r}_{g} =& \sqrt{1-s_{eg}} \left\{1 - \left( \saturation_{eg} \right)^{1/m} \right\}^{2m}.

For the Mualem relative permeability function based on the Brooks-Corey
saturation function, the liquid and gas relative permeability functions are 
given by the expressions

.. math::
   :label: kr_mualem_bc

   k^{r}_{l} =& \big(s_{el}\big)^{5/2+2/\lambda} 

   k^{r}_{g} =& \sqrt{1-s_{eg}}\left({1-s_{eg}^{1+1/\lambda}}\right)^{2}. 
   
For the Mualem relative permeability function based on the linear saturation
functions, the liquid and gas relative permeability functions are given by the 
expressions

.. math::
   :label: kr_mualem_lin
   
   k^{r}_{l} =& \sqrt{s_{el}}\frac{\ln\left({p_c/p_c^{max}}\right)}{\ln\left({\frac{1}{\alpha}/p_c^{max}}\right)}
   
   k^{r}_{g} =& \sqrt{1-s_{eg}}\left({1-\frac{k^{r}_{l}}{\sqrt{s_{eg}}}}\right)
   
For the Burdine relative permeability function based on the van
Genuchten saturation function, the liquid and gas relative permeability 
functions are given by the expressions

.. math::
   :label: kr_burdine_vg
   
   k^{r}_{l} =& \saturation_{el}^2 \left\{1 - \left[1- \left( \saturation_{el} \right)^{1/m} \right]^m \right\}
   
   k^{r}_{g} =& (1-s_{eg})^2 \left\{1 - \left( \saturation_{eg} \right)^{1/m} \right\}^{m}.
 
For the Burdine relative permeability function based on the Brooks-Corey
saturation function, the liquid and gas relative permeability functions have the
form

.. math::
   :label: kr_burdine_bc

   k^{r}_{l} =& \big(s_{el}\big)^{3+2/\lambda} 

   k^{r}_{g} =& (1-s_{eg})^2\left[{1-(s_{eg})^{1+2/\lambda}}\right].
   
For the Burdine relative permeability function based on the linear saturation
functions, the liquid and gas relative permeability functions are given by the 
expressions

.. math::
   :label: kr_burdine_lin
   
   k^{r}_{l} =& \saturation_{el}

   k^{r}_{g} =& 1 - \saturation_{eg}.
   
   
Kelvin's Equation for Vapor Pressure Lowering
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Vapor pressure lowering resulting from capillary suction is described by 
Kelvin's equation given by

.. math::
   :label: kelvins_eq
   
   p_v = p_{\rm sat} (T) e^{-p_c/\density_l RT},

where :math:`p_v` represents the vapor pressure, :math:`p_{\rm sat}` the 
saturation pressure of pure water, :math:`p_c` capillary pressure, 
:math:`\density_l` liquid mole density, :math:`T` denotes the temperature, and 
:math:`R` the gas constant. 

Fully Implicit Solute Coupling
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A third mass conservation equation for a solute can additionally be solved:

.. math::
   :label: solute-conservation-general

   \frac{{{\partial}}}{{{\partial}}t} \porosity \Big(s_l \density_l x_i^l + \saturation_p \density_p x_i^p\Big) + {\boldsymbol{\nabla}}\cdot\Big({\boldsymbol{q}}_l\density_l x_i^l -\porosity \saturation_l D_l \density_l {\boldsymbol{\nabla}}x_i^l\Big) = Q_i

for liquid and solid precipitate saturation :math:`s_{l,\,p}`, density
:math:`\density_{l,\,p}`, diffusivity :math:`D_{l}`, Darcy
velocity :math:`{\boldsymbol{q}}_{l}` and mole fraction
:math:`x_i^{l,\,p}`. 

At solute concentrations above solubility, a solid precipitate phase forms. Transport of the solute is only possible through advection or diffusion within the liquid phase.

Alternatively, the rock matrix can be soluble, in which case the mass conservation equation becomes

.. math::
   :label: soluble-matrix-conservation-general

   \frac{{{\partial}}}{{{\partial}}t} \Big(\porosity (s_l \density_l x_i^l)+(1-\porosity)\Big) + {\boldsymbol{\nabla}}\cdot\Big({\boldsymbol{q}}_l \density_l x_i^l -\porosity \saturation_l D_l \density_l {\boldsymbol{\nabla}}x_i^l\Big) = Q_i

