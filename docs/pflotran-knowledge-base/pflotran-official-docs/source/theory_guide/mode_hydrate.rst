.. _mode-hydrate:

HYDRATE Mode
------------

The gas hydrate, or ``HYDRATE``, mode is designed to model miscible,
non-isothermal subsurface flow of gas, water, and salt considering
gas hydrate phase formation and dissociation. It can model
hydrate-forming CO2 or CH4, and it can be fully implicitly coupled to a
:ref:`well` through the WELL_MODEL block. Coupling to a reactive transport mode
is currently under development.

Governing Equations
~~~~~~~~~~~~~~~~~~~

The ``HYDRATE`` mode involves three components (water, gas, and salt) and
five phases (liquid, gas, hydrate, ice, and salt precipitate) coupled
to energy conservation. Mass conservation equations have the form

.. math::
   :label: mass-conservation-hydrate

   \frac{{{\partial}}}{{{\partial}}t} \porosity \sum_{{{\alpha}}=l,\,g,\,h,\,i,s} \Big(s_{\alpha}^{} \density_{\alpha}^{} x_j^{\alpha} \Big) + {\boldsymbol{\nabla}}\cdot\Big({\boldsymbol{q}}_l^{} \density_l^{} x_j^l + {\boldsymbol{q}}_g \density_g^{} x_j^g -\porosity \saturation_l^{} D_l^{} \density_l^{} {\boldsymbol{\nabla}}x_j^l -\porosity \saturation_g^{} D_g^{} \density_g^{} {\boldsymbol{\nabla}}x_j^g \Big) = Q_j^{},

for liquid, gas, hydrate, ice, and salt precipitate saturations
:math:`s_{l,\,g,\,h,\,i,\,s}^{}`, mobile phase density
:math:`\density_{l,\,g}^{}`, diffusivity :math:`D_{l,\,g}^{}`,
Darcy velocity :math:`{\boldsymbol{q}}_{l,\,g}^{}` and liquid and gas mole
fractions :math:`x_j^{l,\,g}`. Mole fractions of components in the hydrate,
ice, and salt precipitate phases are fixed. The energy conservation
equation can be written in the form

.. math::
   :label: energy-conservation-hydrate

   \sum_{{{\alpha}}=l,\,g,\,h,\,i,\,s}\left\{\frac{{{\partial}}}{{{\partial}}t} \big(\porosity \saturation_{{\alpha}}\density_{{\alpha}}U_{{\alpha}}\big) + {\boldsymbol{\nabla}}\cdot\big({\boldsymbol{q}}_{{\alpha}}\density_{{\alpha}}H_{{\alpha}}\big) \right\} + \frac{{{\partial}}}{{{\partial}}t}\big( (1-\porosity)\density_r C_p T \big) - {\boldsymbol{\nabla}}\cdot (\kappa{\boldsymbol{\nabla}}T) = Q,

as the sum of contributions from liquid and fluid phases and solid hydrate,
ice, salt, and rock phases; with internal energy :math:`U_{{\alpha}}` and enthalpy
:math:`H_{{\alpha}}` of fluid phase :math:`{{\alpha}}`, rock heat
capacity :math:`C_p` and thermal conductivity :math:`\kappa`. Note that

.. math::
   :label: internal-energy-hydrate

   U_{{\alpha}}= H_{{\alpha}}-\frac{P_{{\alpha}}}{\density_{{\alpha}}}.

Thermal conductivity :math:`\kappa` can be determined from :ref:`thermal-characteristic-curves-card`, or through the HYDRATE block in :ref:`hydrate-card` :

.. math::
   :label: cond-hydrate

   \kappa = \kappa_{\rm dry} + {\porosity}\sum_{{{\alpha}}=l,\,g,\,h,\,i}s_{{\alpha}}{\kappa}_{\alpha} ,

where :math:`\kappa_{\rm dry}` is the dry thermal conductivity, an input
parameter equivalent to :math:`(1-\porosity)\kappa_{\rm rock}` and :math:`\kappa_{\rm sat}` are dry and
fully saturated rock thermal conductivities, respectively.

The internal energy of the ice phase is computed by (Fukusako and Yamada, 1993):

.. math::
   :label: ice-int-energy-hydrate

   U_i = L_w + 185T + 3.445(T^2 - 273.15^2 ) , T >= 90K

.. math::
   :label: ice-int-energy-hydrate-2

   U_i = L_w + 4.475(T^2 - 273.15^2 ), T < 90K,

where T is the temperature and :math:`L_w` is the latent heat ofo fusion for
water, set at -6017.1 J/mol.

The enthalpy of the hydrate phase is computed by (Handa, 1998):

.. math::
   :label: hydrate-enthalpy

   H_h = C_{ph}(T-T_f)+H_{h0}/(N_{hyd}+1)

where :math:`H_{h0}` is the hydrate reference enthalpy, set to -54.734 kJ/mol,
:math:`N_{hyd}` is the hydration number (set to 6), :math:`T_{f}` is the
freezing point (0C in the absence of salt), and :math:`C_{ph}` is the heat
capacity of hydrate, computed by:

.. math::
  :label: hydrate-heat-capacity

  C_{ph} = 1620(M_w N_{hyd} + M_m)/1000

where :math:`M_w` is the molecular weight of water and :math:`M_m` is the
molecular weight of methane

Two-phase liquid-gas equilibrium partitioning is computed via Henry's Law
(Carroll and Mather, 1997):

.. math::
   :label: henrys-constant-hydrate

   K_h = 1000e^{5.1345+7837/T - 1.509x10^6/T^2 + 2.06x10^7/T^3}

The liquid - CH4 hydrate phase boundary is computed by (Moridis, 2003):

.. math::
   :label: hydrate-phase-boundary

   P_e = e^{0.0334940999T-8.1938174346}, T < T_f

.. math::
   :label: hydrate-phase-boundary-2

   P_e = e^{0.1100383278T-29.1133440975}, T >= T_f

where :math:`P_e` is the 3-phase equilibrium pressure in MPa.


The Darcy velocity of the :math:`\alpha^{th}` phase is equal to

.. math::
   :label: darcy_velocity_hydrate

   \boldsymbol{q}_\alpha = -\frac{k k^{r}_{\alpha}}{\mu_\alpha} \boldsymbol{\nabla} (p_\alpha - \gamma_\alpha \boldsymbol{g} z), \ \ \ (\alpha=l,g),

where :math:`\boldsymbol{g}` denotes the acceleration of gravity, :math:`k` denotes the saturated
permeability, :math:`k^{r}_{\alpha}` the relative permeability,
:math:`\mu_\alpha` the viscosity, :math:`p_\alpha` the pressure of the
:math:`\alpha^{th}` fluid phase, and

.. math::
   :label: gamma-hydrate

   \gamma_\alpha^{} = W_\alpha^{} \density_\alpha^{},

with :math:`W_\alpha` the gram formula
weight of the :math:`\alpha^{th}` phase

.. math::
   :label: gram-formula-weight-hydrate

   W_\alpha = \sum_{i=w,\,a} W_i^{} x_i^\alpha,

where :math:`W_i` refers to the formula weight of the :math:`i^{th}` component.

.. _pc-sat-functions-hydrate:

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
   :label: liq-sat-hydrate

   \saturation_{l} = \saturation_{el}s_0 - \saturation_{el}s_{rl} + \saturation_{rl},

where :math:`s_{rl}` denotes the liquid residual saturation, and :math:`s_0`
denotes the maximum liquid saturation. The gas saturation can be obtained from
the relation

.. math::
   :label: phase-sum-hydrate

   \saturation_l + \saturation_g = 1

The effective gas saturation :math:`s_{eg}` is defined by the relation

.. math::
   :label: \saturation_eg-hydrate

   \saturation_{eg} = 1 - \frac{s_l-s_{rl}}{1-s_{rl}-s_{rg}}

Additionally, a linear relationship between capillary pressure :math:`p_c` and
effective liquid saturation can be described as

.. math::
   :label: linear_pc_sat-hydrate

   \saturation_{el} = {{p_c-p_c^{max}}\over{\frac{1}{\alpha}-p_c^{max}}}

where :math:`\alpha` is a fitting parameter representing the air entry pressure
[Pa]. The inverse relationship for capillary pressure is

.. math::
   :label: linear_sat_pc-hydrate

   p_c = \left({\frac{1}{\alpha}-p_c^{max}}\right)s_{el} + p_c^{max}

.. _relative-permeability-functions-hydrate:

Relative Permeability Functions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Two forms of each relative permeability function are implemented based on
the Mualem and Burdine formulations as in :ref:`mode-richards`, but the
effective liquid saturation :math:`s_{el}` and the effective gas saturation
:math:`s_{eg}` are used. A summary of the relationships used can be found in
Chen et al. (1999), where the tortuosity
:math:`\eta` is set to :math:`1/2`. If the keyword EFFECTIVE_SATURATION_SCALING
is invoked in the HYDRATE block, then each mobile phase (e.g., liquid or gas)
saturation is scaled by the sum of mobile phase saturations. For example, if
liquid and gas saturations are each 30%, their effective phase satuations each
become 50%. The implemented relative permeability functions include:
Mualem-van Genuchten, Mualem-Brooks-Corey, Mualem-linear,
Burdine-van Genuchten, Burdine-Brooks-Corey, and Burdine-linear. For each
relationship, the following definitions apply:

.. math::

   S_{el} = \frac{S_{l}-S_{rl}}{1-S_{rl}}

   S_{eg} = \frac{S_{l}-S_{rl}}{1-S_{rl}-S_{rg}}

For the Mualem relative permeability function based on the van Genuchten
saturation function, the liquid and gas relative permeability functions are
given by the expressions

.. math::
   :label: kr_mualem_vg-hydrate

   k^{r}_{l} =& \sqrt{s_{el}} \left\{1 - \left[1- \left( \saturation_{el} \right)^{1/m} \right]^m \right\}^2

   k^{r}_{g} =& \sqrt{1-s_{eg}} \left\{1 - \left( \saturation_{eg} \right)^{1/m} \right\}^{2m}.

For the Mualem relative permeability function based on the Brooks-Corey
saturation function, the liquid and gas relative permeability functions are
given by the expressions

.. math::
   :label: kr_mualem_bc-hydrate

   k^{r}_{l} =& \big(s_{el}\big)^{5/2+2/\lambda}

   k^{r}_{g} =& \sqrt{1-s_{eg}}\left({1-s_{eg}^{1+1/\lambda}}\right)^{2}.

For the Mualem relative permeability function based on the linear saturation
functions, the liquid and gas relative permeability functions are given by the
expressions

.. math::
   :label: kr_mualem_lin-hydrate

   k^{r}_{l} =& \sqrt{s_{el}}\frac{\ln\left({p_c/p_c^{max}}\right)}{\ln\left({\frac{1}{\alpha}/p_c^{max}}\right)}

   k^{r}_{g} =& \sqrt{1-s_{eg}}\left({1-\frac{k^{r}_{l}}{\sqrt{s_{eg}}}}\right)

For the Burdine relative permeability function based on the van
Genuchten saturation function, the liquid and gas relative permeability
functions are given by the expressions

.. math::
   :label: kr_burdine_vg-hydrate

   k^{r}_{l} =& \saturation_{el}^2 \left\{1 - \left[1- \left( \saturation_{el} \right)^{1/m} \right]^m \right\}

   k^{r}_{g} =& (1-s_{eg})^2 \left\{1 - \left( \saturation_{eg} \right)^{1/m} \right\}^{m}.

For the Burdine relative permeability function based on the Brooks-Corey
saturation function, the liquid and gas relative permeability functions have the
form

.. math::
   :label: kr_burdine_bc-hydrate

   k^{r}_{l} =& \big(s_{el}\big)^{3+2/\lambda}

   k^{r}_{g} =& (1-s_{eg})^2\left[{1-(s_{eg})^{1+2/\lambda}}\right].

For the Burdine relative permeability function based on the linear saturation
functions, the liquid and gas relative permeability functions are given by the
expressions

.. math::
   :label: kr_burdine_lin-hydrate

   k^{r}_{l} =& \saturation_{el}

   k^{r}_{g} =& 1 - \saturation_{eg}.


