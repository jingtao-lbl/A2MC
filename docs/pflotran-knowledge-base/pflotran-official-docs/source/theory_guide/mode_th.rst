.. _mode-th:

TH Mode (Thermal-Hydrologic)
----------------------------

Governing Equations
~~~~~~~~~~~~~~~~~~~

The current implementation of the ``TH`` mode applies to mass and energy
conservation equations which are solved fully coupled. The fluid density
only a function of :math:`T` and :math:`P`. Future generalizations of
the ``TH`` mode will include multicomponent variable density fluids. The
TH mode may be coupled to the reactive transport mode.

The ``TH`` mode applies to single phase, variably saturated, nonisothermal
systems with incorporation of density variations coupled to fluid flow.
The governing equations for mass and energy are given by

.. math::
   :label: masseqn

   \frac{{{\partial}}}{{{\partial}}t}\left(\porosity s\eta\right) + {\boldsymbol{\nabla}}\cdot\left(\eta{\boldsymbol{q}}\right) = Q_w,

and

.. math::
   :label: energy-th

   \frac{{{\partial}}}{{{\partial}}t}\big(\porosity s\eta U + (1-\porosity) \density_r c_p T\big) + {\boldsymbol{\nabla}}\cdot\big(\eta {\boldsymbol{q}}H -\kappa {\boldsymbol{\nabla}}T\big) = Q_e,

The Darcy flow velocity :math:`{\boldsymbol{q}}` is given by

.. math::
   :label: darcy-th

   {\boldsymbol{q}}= -\frac{kk_r}{\mu} {\boldsymbol{\nabla}}\left(P-\density gz\right).

Here, :math:`\porosity` denotes porosity, :math:`s` saturation,
:math:`\density`, :math:`\eta` mixture mass and molar density, respectively, of the brine, :math:`{\boldsymbol{q}}`
Darcy flux, :math:`k` intrinsic permeability, :math:`k_r` relative
permeability, :math:`\mu` viscosity, :math:`P` pressure, :math:`g`
gravity, and :math:`z` the vertical component of the position vector.
Supported relative permeability functions :math:`k_r` for Richards’
equation include van Genuchten, Books-Corey and Thomeer-Corey, while the
saturation functions include Burdine and Mualem (see :ref:`mode-richards`). Water density and
viscosity are computed as a function of temperature and pressure through
an equation of state for water. 
The quantity :math:`\density_r` denotes the rock density,
:math:`c_p`, and :math:`\kappa` denote the heat capacity and
thermal conductivity of the porous medium-fluid system. The internal
energy and enthalpy of the fluid, :math:`U` and :math:`H`, are obtained
from an equation of state for pure water. These two quantities are
related by the thermodynamic expression

.. math::
   :label: thermo-th
   
   U = H -\frac{P}{\eta}.

Thermal conductivity is determined from the equation (Somerton et al.,
1974)

.. math::
   :label: cond1

   \kappa = \kappa_{\rm dry} + \sqrt{s_l^{}} (\kappa_{\rm sat} - \kappa_{\rm dry}),

where :math:`\kappa_{\rm dry}` and :math:`\kappa_{\rm sat}` are dry and
fully saturated rock thermal conductivities.

.. _mode-th-ice-model:

Ice Model
~~~~~~~~~

In PFLOTRAN, the formulation used to model ice and water vapor involves
solving a modified Richards equation coupled with an energy balance
equation. This formulation is different from Painter (2011), where a
multiphase approach was used and mass balance for air was also solved
for. In this formulation, the movement of air is not tracked, and hence
the mass balance for air is not considered. The balance equations for
mass and energy involving three phases (liquid, gas, ice) for the water
component are given by

.. math::
   :label: eq:balance_eqns

   {\dfrac{\partial{}}{\partial{t}}} \left[ \porosity \left( \saturation_l \eta_l X_w^l + \saturation_g \eta_g X_w^g + \saturation_i \eta_i X_w^i \right) \right] & + \boldsymbol{\nabla} \cdot \left[X_w^l \boldsymbol{q}_l \eta_l + X_w^g \eta_g \boldsymbol{q}_g \right] \nonumber\\
   - \boldsymbol{\nabla} \cdot \left[\porosity \saturation_g \tortuosity_g  \eta_g D_g \boldsymbol{\nabla} X^g_w \right] = Q_w, \\
   {\dfrac{\partial{}}{\partial{t}}} \left[ \porosity \left( \saturation_l \eta_l U_l + \saturation_g \eta_g U_g + \saturation_i \eta_i U_i \right) + (1- \porosity) \density_r c_r T \right] & + \boldsymbol{\nabla} \cdot \left[ \boldsymbol{q}_l \eta_l  H_l + \boldsymbol{q}_g \eta_g H_g \right] \nonumber\\
   - \boldsymbol{\nabla} \cdot \left[ \kappa \boldsymbol{\nabla} T\right] = Q_e,

where the subscripts :math:`l`, :math:`i`, :math:`g`
denote the liquid, ice and gas phases, respectively; :math:`\porosity` is the
porosity; :math:`s_{\alpha} (\alpha = i, l, g)` is the saturation of the
:math:`\alpha`-th phase; :math:`\eta_{\alpha} (\alpha = i, l, g)` is the
molar density of the :math:`\alpha`-th phase; :math:`\density_g`,
:math:`\density_l` are the mass densities of the gas and liquid phases;
:math:`Q_w` is the mass source of :math:`\mathrm{H_2O}`;
:math:`X_w^{\alpha} (\alpha = i, l, g)` is the mole fraction of
:math:`\mathrm{H_2O}` in the :math:`\alpha`-th phase; :math:`\tortuosity_g` is
the tortuosity of the gas phase; :math:`D_g` is the diffusion
coefficient in the gas phase; :math:`T` is the temperature (assuming all
the phases and the rock are in thermal equilibrium); :math:`c_r` is the
specific heat of the rock; :math:`\density_r` is the density of the rock;
:math:`U_{\alpha} (\alpha = i, l, g)` is the molar internal energy of
the :math:`\alpha`-th phase; :math:`H_{\alpha} (\alpha = l, g)` is the
molar enthalpy of the :math:`\alpha`-the phase; :math:`Q_e` is the heat
source; :math:`\boldsymbol{\nabla}\, (\, )` is the gradient operator;
:math:`\boldsymbol{\nabla}\cdot (\,)` is the divergence operator.

The Darcy velocity for the gas and liquid phases are given as follows:

.. math::
   :label: eq:darcy

   \boldsymbol{q}_g = - \frac{k_{rg}k}{\mu_g} \boldsymbol{\nabla}\left[p_g - \density_g \boldsymbol{g} \right], \\
   \boldsymbol{q}_l = - \frac{k_{rl}k}{\mu_l} \boldsymbol{\nabla}\left[p_l - \density_l \boldsymbol{g} \right],

where :math:`k` is the absolute permeability;
:math:`k_{r \alpha} (\alpha = l, g)` is the relative permeability of the
:math:`\alpha`-th phase; :math:`\mu_{\alpha} (\alpha = l, g)` is the
viscosity of the :math:`\alpha`-th phase;
:math:`p_{\alpha} (\alpha = l, g)` is the partial pressure of the
:math:`\alpha`-th phase; :math:`\boldsymbol{g}` is acceleration due to gravity.

The constraint on the saturations of the various phases of water is
given by

.. math::
   :label: sat-constraint-th

   \saturation_l + \saturation_g + \saturation_i = 1.

Furthermore, neglecting the amount of air in liquid and ice phases, it
follows that

.. math::
   :label: X-th
   
   X_a^l = 0, X_a^i = 0 \Rightarrow X_w^l = 1, X_w^i =1,

and so
Eqns. :eq:`eq:balance_eqns`, :eq:`eq:darcy` based
on the assumption that :math:`p_g` is hydrostatic i.e.,
:math:`{p}_g = {({p}_g)}_0 + \density_g gz`, reduce to [eq:gov]

.. math::
   :label: eq:gov1

   {\dfrac{\partial{}}{\partial{t}}}\left[ \porosity \left( \saturation_g \eta_g X_w^g +s_l \eta_l + \saturation_i \eta_i \right) \right] + \boldsymbol{\nabla} \cdot \left[\boldsymbol{q}_l \eta_l \right] - \boldsymbol{\nabla} \cdot \left[\porosity \saturation_g \tortuosity_g  \eta_g D_g \boldsymbol{\nabla} X^g_w \right] = Q_w, 
   
.. math::
   :label: eq:gov2

   {\dfrac{\partial{}}{\partial{t}}}\left[ \porosity \left( \saturation_l \eta_l U_l + \saturation_g \eta_g U_g + \saturation_i \eta_i U_i \right) + (1- \porosity) \density_r c_r T \right] + \boldsymbol{\nabla} \cdot \left[ \boldsymbol{q}_l \eta_l  H_l \right] - \boldsymbol{\nabla} \cdot \left[ \kappa \boldsymbol{\nabla} T\right] = Q_e, \\
   \boldsymbol{q}_l = - \frac{k_{rl}k}{\mu_l} \left[\boldsymbol{\nabla}p_l - \density_l \boldsymbol{g} \right]. 

In the above formulation, temperature and liquid pressure are chosen to
be primary variables. It is ensured that complete dry-out does not
occur, and that liquid is present at all times. With this approach, it
is not necessary to change the primary variables based on the phases
present.

In addition to the previously described mass and energy balance
equations, additional constitutive relations are required to model
non-isothermal, multiphase flow of water. Assuming thermal equilibrium
among the ice, liquid and vapor phases, the mole fraction of water in
vapor phase is given by the relation,

.. math::
   :label: X-w-th

   X_w^g = \frac{p_v}{p_g},

where :math:`p_v` is the vapor pressure, and :math:`p_g` is the gas
pressure (It is assumed that :math:`p_g` = 1 atm throughout the domain).
Vapor pressure is calculated using Kelvin’s relation which includes
vapor pressure lowering due to capillary effects as follows

.. math::
   :label: pv-th
   
   p_v = P_{\text{sat}}(T) \text{exp}\left[\frac{P_{cgl}}{\eta_l R (T + 273.15)} \right],

where :math:`P_{\text{sat}}` is the saturated vapor pressure,
:math:`P_{cgl}` is the liquid-gas capillary pressure, and :math:`R` is
the gas constant. Empirical relations for saturated vapor pressure are
used for both above and below freezing conditions. To calculate the
partition of ice, liquid and vapor phases, at a known temperature and
liquid pressure, the following two relations are used (see Painter,
2011):

.. math::
   :label: sats1
   
   \frac{s_l}{s_l + \saturation_g} = S_{*}\left(P_{cgl}\right), 

.. math::
   :label: sats2
   
   \frac{s_l}{s_l + \saturation_i} = S_{*}\left[\frac{\sigma_{gl}}{\sigma_{il}} P_{cil} \right], 
   
:math:`S_{*}` is the retention curve for unfrozen liquid-gas phases,
:math:`P_{cgl}` is the gas-liquid capillary pressure, :math:`P_{cil}` is
the ice-liquid capillary pressure, :math:`\sigma_{il}` and
:math:`\sigma_{gl}` are the ice-liquid and gas-liquid interfacial
tensions. Also,

.. math::
   :label: pcil-th

   P_{cil} = - {\density}_i h_{iw} \vartheta,

where :math:`h_{iw}^0` is the heat of fusion of ice at 273.15 K,
:math:`{\density}_i` is the mass density of ice,
:math:`\vartheta = \frac{T - T_0}{T_0}` with :math:`T_0 = 273.15` K.

For :math:`S_{*}` the van Genuchten model is used:

.. math::
   :label: sstar-th
   
   S_{*} = \begin{cases}
              \left[ 1 + \left(\alpha {P_c}\right)^\gamma\right]^{-\lambda} , &\quad P_c > 0\\
              1, &\quad P_c \leq 0
               \end{cases}

with the Mualem model implemented for the relative permeability of
liquid water,

.. math::
   :label: krl_mualem-th
   
   k_{rl} = (s_l)^{\frac{1}{2}} \left[1 - \left( 1 - (s_l)^{\frac{1}{\lambda}}\right)^{\lambda} \right]^2,

where :math:`\lambda`, :math:`\alpha` are parameters, with
:math:`\gamma = \frac{1}{1-\lambda}`.

The thermal conductivity for the frozen soil is chosen to be

.. math::
   :label: therm-cond-th
   
   \kappa = Ke_{f} \kappa_{\text{wet},f} + Ke_{u} \kappa_{\text{wet},u} + (1 - Ke_u - Ke_f) \kappa_{\text{dry}},

where :math:`\kappa_{\text{wet},f}`, :math:`\kappa_{\text{wet},u}` are
the liquid- and ice-saturated thermal conductivities,
:math:`\kappa_{\text{dry}}` is the dry thermal conducitivity,
:math:`Ke_f`, :math:`Ke_u` are the Kersten numbers in frozen and
unfrozen conditions and are assumed to be related to the ice and liquid
saturations by power law relations as follows

.. math::
   :label: therm-power-law-th
   
   Ke_f = \left(s_i  \right)^{\alpha_f}, \\
   Ke_u = \left(s_l  \right)^{\alpha_u},

with :math:`\alpha_f`, :math:`\alpha_u` being the power law
coefficients. Care is also taken to ensure that the derivatives of the
Kersten numbers do not blow up when :math:`s_i`, :math:`s_l` go to zero
when :math:`\alpha_f`, :math:`\alpha_u` are less than one.

The gas diffusion coefficient :math:`D_g` is assumed to dependend on
temperature and pressure as follows:

.. math::
   :label: gas-diff-th
   
   D_g = D_g^0 \left( \frac{P_{\text{ref}}}{P}\right) \left( \frac{T}{T_{\text{ref}}}\right)^{1.8},

where :math:`D_g^0` is the reference diffusion coefficient at some
reference temperature, :math:`T_{\text{ref}}`, and pressure
:math:`P_{\text{ref}}`.


