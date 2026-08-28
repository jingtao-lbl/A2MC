.. _mode-reactive-transport:

Introduction 
++++++++++++

The chemistry algorithm implemented in PFLOTRAN employs a multicomponent formulation of aqueous species, gases and minerals. The traansport equations are formulated in terms
of the total concentration of a chosen set of primary or basis species. 
A feature of the code is that primary species which form the independent variables can be chosen arbitrarily (so long as they form an independent set of aqueous species), and need not reflect the form of the reactions as wwritten in the thermodynamic database. For example, the sets of 
primary species :math:`\{\rm K^+, Al^{3+},SiO_2,H^+\}` and 
:math:`\{\rm K^+, AlOH_4^-,SiO_2,OH^-\}` can be used interchangeably 
giving identical results.

Chemical reactions included in the code are aqueous complexing for both local equilibrium and kintic formulations (however the rate law is restricted to elementary reactions), kinetic reaction of minerals using the usual transition state rate law, gaseous reactions and various formulations of sorption. The Debye-Hueckel activity coefficient algorithm is implemented and can be invoked during various stages of stepping forward in time. 

The reactive transport mode may be used either as a standalone application or sequentially
coupled to a flow mode which can include both mass and heat flow. This latter capability provides feedback between flow, heat
and transport allowing chemical reactions to alter material properties
such as porosity, permeability, and tortuosity thereby altering the flow field. To include temperature effects on chemistry the database must provide log Ks relevant to the system at hand.

Governing Equations
+++++++++++++++++++

The governing mass conservation equations for the geochemical transport
mode for a multiphase system is written in terms of a set of independent
aqueous primary or basis species with the form

.. math::
   :label: rteqn
   
   \frac{\partial}{\partial t}\big(\porosity 
   \sum_{\alpha} \saturation_{\alpha}\Psi_j^{\alpha}\big) +
   \nabla\cdot\sum_{\alpha}{\boldsymbol\Omega}_j^{\alpha}= Q_j - \sum_m\nu_{jm} I_m -\frac{\partial S_j}{\partial t},

and

.. math::
   :label: rteqn2
   
   \frac{{{\partial}}\porosity_m}{{{\partial}}t} = \overline{V}_m I_m,

for minerals with molar volume :math:`\overline{V}_m`, reaction
rate :math:`I_m` and volume fraction :math:`\porosity_m`
referenced to an REV. 
The term involving  :math:`S_j` describes sorptive processes considered in more
detail below.
Sums over :math:`{{\alpha}}` in
Eqn. :eq:`rteqn` are over all fluid phases in the system.
The quantity :math:`\Psi_j^{{\alpha}}` denotes the total concentration
of the :math:`j`\ th primary species :math:`{{\mathcal A}}_j^{\rm pri}`
in the :math:`{{\alpha}}`\ th fluid phase defined by

.. math::
   :label: dummy1
   
   \Psi_j^{{\alpha}}= \delta_{l{{\alpha}}}^{} C_j^l + \sum_{i=1}^{N_{\rm sec}}\nu_{ji}^{{{\alpha}}} C_i^{{\alpha}},

In this equation the index :math:`l` represents the aqueous
electrolyte phase from which the primary species are chosen. The
secondary species concentrations :math:`C_i^{{\alpha}}` are obtained
from mass action equations corresponding to equilibrium conditions of
the reactions

.. math::
   :label: dummy2
   
   \sum_j\nu_{ji}^{{\alpha}}{{\mathcal A}}_j^l {~\rightleftharpoons~}{{\mathcal A}}_i^{{\alpha}},

yielding the mass action equations

.. math::
   :label: mass-action
   
   C_i^{{\alpha}}= \frac{K_i^{{\alpha}}}{\gamma_i^{{\alpha}}} \prod_j \Big(\gamma_j^l C_j^l\Big)^{\nu_{ji}^{{\alpha}}},

with equilibrium constant :math:`K_i^{{\alpha}}`, and activity
coefficients :math:`\gamma_k^{{\alpha}}`. For the molality of the
:math:`k`\ th aqueous species, the extended Debye-Hückel activity coefficient
for an aqueous electrolyte solution with ionic strength :math:`I` is 
given by (Debye and Hückel, 1923)

.. math::
   :label: dummy3
   
   \log_{10} \,\gamma_k = -\frac{z_k^2 A \sqrt{I}}{1 + \stackrel{\circ}{a}_k 
   B \sqrt{I}} + \dot b I,

with valence :math:`z_k`,
ionic radius :math:`\stackrel{\circ}{a}_k` in angstroms,
and where the Debye-Hückel parameters :math:`A`, :math:`B` are 
defined by (Helgeson and Kirkham, 1974)

.. math::
   :label: AB

   A &= \frac{N_A^2 e^3\sqrt{2\pi}}{\ln 10 \sqrt{1000}\big(\epsilon(T,p)RT\big)^{3/2}},\\
   B &= N_A e\sqrt{\frac{8\pi}{1000 \, \epsilon(T,p) RT}} \times 10^{-8}.

The :math:`\dot b` term is from Helgeson (1969) given by

.. math::
   :label: bdot

   \dot b = 15698.4\, T^{-1} + 41.8088 \,\ln(T) - 0.0367626 \,T - 974169.0\, T^{-2} - 268.902,

The quantity :math:`\epsilon(T,p)` is the dielectric constant of pure water which can be found in e.g. Johnson and Norton (1991). 
Ionic strength :math:`I` is defined as

.. math::
   :label: dummy5
   
   I = \frac{1}{2}\sum_{j=1}^{N_c} m_j z_j^2 + \frac{1}{2}\sum_{i=1}^{N_{\rm sec}} m_i z_i^2,

with molality :math:`m_j` and :math:`m_i` of primary and secondary
species, respectively (note:
:math:`C_i^l = \density_l y_w^l m_i \simeq \density_l m_i`, :math:`\density_l` =
fluid density, :math:`y_w^l` = mass fraction of :math:`\mathrm{H_2O}`).

Values in CGS units used for the various constants appearing in the expressions 
for A and B are 
based on the most recent values (2020) for 
Avogrado's number (\ :math:`N_A = 6.0221409 \times 10^{23}` 1/mole),
charge (\ :math:`e = 4.80320425 \times 10^{-10}` esu),
Boltzmann's constant (\ :math:`k_B=1.38064852\times 10^{-16}` erg/K), 
gas constant (\ :math:`R=8.31446261815324 \times 10^7` erg/K/mole = :math:`N_A k_B`) and :math:`\pi=3.14159265359`. Density of pure water is based on the IFC97 EoS.
Debye-Huckel coefficients are calculated at selected temperatures along the saturation curve of pure water and linearly interpolated at intermediate temperatures. 

For high-ionic strength solutions (approximately above 0.1 M) the Pitzer
model should be used. Currently, however, only the Debye-Hückel
algorithm is implemented in PFLOTRAN.


Other forms for activity coefficients exist although not currently implemented. A simplified form is given by the Davies equation

.. math::
   :label: dummy4
   
   \log\,\gamma_k = -\frac{z_k^2}{2}\left[\frac{\sqrt{I}}{1+ \sqrt{I}}-0.3 I\right],

taking :math:`A = 1/2` and :math:`\stackrel{\circ}{a}_k B = 1`, 
and :math:`\dot b = 0.15` in the extended Debye-Hückel equation.

The total flux :math:`{\boldsymbol{\Omega}}_j^{{\alpha}}` for
species-independent diffusion is given by

.. math::
   :label: dummy6
   
   {\boldsymbol{\Omega}}_j^{\alpha}= \big({\boldsymbol{q}}_{\alpha}- \porosity \saturation_{\alpha}{\boldsymbol{D}}_{\alpha} \cdot {\boldsymbol{\nabla}}\big)\Psi_j^{\alpha}.

The diffusion/dispersion tensor :math:`{\boldsymbol{D}}_{\alpha}`
may be different for different phases, e.g. an aqueous electrolyte
solution or gas phase, but is assumed to be species independent.
Dispersivity currently must be described through a diagonal dispersion
tensor.

The Darcy velocity :math:`{\boldsymbol{q}}_{{\alpha}}` for phase
:math:`{{\alpha}}` is given by

.. math::
   :label: dummy7
   
   {\boldsymbol{q}}_a = -\frac{kk_{{\alpha}}}{\mu_{{\alpha}}} {\boldsymbol{\nabla}}\big(p_{{\alpha}}-\density_{{\alpha}}g z\big),

with bulk permeability of the porous medium :math:`k` and relative
permeability :math:`k_{{\alpha}}`, fluid viscosity
:math:`\mu_{{\alpha}}`, pressure :math:`p_{{\alpha}}`, density
:math:`\density_{{\alpha}}`, and acceleration of gravity :math:`g`. The
diffusivity/dispersivity tensor :math:`{\boldsymbol{D}}_{{\alpha}}` is
the sum of contributions from molecular diffusion and dispersion which
for an isotropic medium has the form

.. math::
   :label: dummy8
   
   {\boldsymbol{D}}_{{\alpha}}= {\boldsymbol{\tortuosity}} D_m {\boldsymbol{I}}+ a_T v{\boldsymbol{I}}+ \big(a_L-a_T\big)\frac{{\boldsymbol{v}}{\boldsymbol{v}}}{v},
   

with longitudinal and transverse dispersivity coefficients :math:`a_L`,
:math:`a_T`, respectively, :math:`{\boldsymbol{\tortuosity}}` refers to tortuosity, which can account for diagonal anisotropy, and
:math:`D_m` to the molecular diffusion coefficient. Currently, only
a diagonal dispersion tensor with principal axes aligned with the grid for longitudinal and transverse 
dispersion is implemented in PFLOTRAN.

The porosity may be calculated from the mineral volume fractions
according to the relation

.. math::
   :label: dummy9
   
   \porosity = 1 - \sum_m \porosity_m.

The temperature dependence of the diffusion coefficient is defined
through the relation

.. math::
   :label: dummy10
   
   D_m(T) = D_m^\circ\exp\left[\frac{A_D}{R}\left(\frac{1}{T_0}-\frac{1}{T}\right)\right],

with diffusion activation energy :math:`A_D` in kJ/mol. The quantity
:math:`D_m^\circ` denotes the diffusion coefficient at the reference
temperature :math:`T_0` taken as 25\ :math:`^\circ`\ C and the quantity
:math:`R` denotes the gas constant (:math:`8.317\times 10^{-3}`
kJ/mol/K). The temperature :math:`T` is in Kelvin.

The quantity :math:`Q_j` denotes a source/sink term

.. math::
   :label: dummy11
   
   Q_j = \sum_n\frac{q_M}{\density}\Psi_j \delta({\boldsymbol{r}}-{\boldsymbol{r}}_{n}),

where :math:`q_M` denotes a mass rate in units of kg/s, :math:`\density`
denotes the fluid density in kg/m\ :math:`^3`, and
:math:`{\boldsymbol{r}}_{n}` refers to the location of the :math:`n`\ th
source/sink. The quantity :math:`S_j` represents the sorbed
concentration of the :math:`j`\ th primary species considered in more
detail in the next section.

Molality :math:`m_i` and molarity :math:`C_i` are related by the density
of water :math:`\density_w` according to

.. math::
   :label: dummy12
   
   C_i = \density_w m_i.

The activity of water is calculated from the approximate relation

.. math::
   :label: dummy13
   
   a_{\rm H_2O}^{} = 1 - 0.017 \sum_i m_i.
   
   
.. _transition-state-theory:   

Mineral Precipitation and Dissolution
+++++++++++++++++++++++++++++++++++++

The reaction rate :math:`I_m` is based on transition state theory taken
as positive for precipitation and negative for dissolution, with the
form

.. math::
   :label: Im
   
   I_m = -A_m\Big(\sum_l k_{ml}(T) {{{\mathcal P}}}_{ml}\Big) \Big|1-\big(K_m Q_m\big)^{1/\sigma_m}\Big|^{\beta_m} {\rm sign}(1-K_m Q_m),

where the sum over :math:`l` represents contributions from parallel
reaction mechanisms such as pH dependence etc., and where :math:`K_m`
denotes the equilibrium constant, :math:`\sigma_m` refers to Temkin’s
constant which is defined as the average stoichiometric coefficient of
the overall reaction (Lichtner, 1996b; see also Section
[thermo:database]), :math:`\beta_m` denotes the affinity power,
:math:`A_m` refers to the specific mineral surface area, and the ion
activity product :math:`Q_m` is defined as

.. math::
   :label: dummy14
   
   Q_m = \prod_j \big(\gamma_j m_j\big)^{\nu_{jm}},

with molality :math:`m_j` of the :math:`j`\ th primary species. The rate
constant :math:`k_{ml}` is a function of temperature given by the
Arrhenius relation

.. math::
   :label: dummy15
   
   k_{ml} (T) = k_{ml}^0 \exp\left[\frac{E_{ml}}{R}\Big(\frac{1}{T_0}-\frac{1}{T}\Big)\right],

where :math:`k_{ml}^0` refers to the rate constant at the reference
temperature :math:`T_0` taken as 298.15\ :math:`^\circ`\ K, with :math:`T`
in units of Kelvin, :math:`E_{ml}` denotes the activation energy
(J/mol), and the quantity :math:`{{{\mathcal P}}}_{ml}` denotes the
prefactor for the :math:`l`\ th parallel reaction with the form

.. math::
   :label: prefactor
   
   {{{\mathcal P}}}_{ml} = \prod_i\dfrac{\big(\gamma_i m_i\big)^{{{\alpha}}_{il}^m}}{1+K_{ml}\big(\gamma_i m_i\big)^{{{\beta}}_{il}^m} },

where the product index :math:`i` generally runs over both primary and
secondary species, the quantities :math:`\alpha_{il}^m` and
:math:`\beta_{il}^m` refer to prefactor coefficients, and :math:`K_{ml}`
is an attenuation factor. The quantity :math:`R` denotes the gas
constant (:math:`8.317 \times 10^{-3}` kJ/mol/K).

Rate Limiter
^^^^^^^^^^^^

In the case of precipitation the mineral reaction rate can grow to unreasonable values. In such casesd it may be necessary to limit the rate so that it approaches a constant value as :math:`K_m Q_m \rightarrow\infty`. A rate-limited form of the mineral kinetic rate law can be devised according to the expression

.. math::
   :label: ratemintran
   
   I_m^{\rm RL} = -A_m^{} \Big( \sum_l k_{ml}^{} {\mathcal P}_{ml}^{} \Big) 
   \Bigg|\frac{1-\big(K_m Q_m\big)^{1/\sigma_m}}{1+\dfrac{1}{f_{m}^{\rm lim}}\big(K_m Q_m\big)^{1/\sigma_m}} \Bigg|^{\beta_m} {\rm sign}(1-K_m Q_m),

with rate-limiter :math:`f_{m}^{\rm lim}`. In the limit
:math:`K_m Q_m\rightarrow\infty`, the rate becomes

.. math::
   :label: dummy16
   
   \lim_{K_m Q_m\rightarrow\infty} I_m^{\rm RL} = f_m^{\rm lim} a_m^{}\sum_l k_{ml} {\mathcal P}_{ml}^{}.

Defining the affinity factor

.. math::
   :label: dummy17
   
   \Omega_m = 1-\left(K_m Q_m\right)^{1/\sigma_m},

or

.. math::
   :label: dummy18
   
   K_m Q_m = \Big(1-\Omega_m\Big)^{\sigma_m},

the rate may be expressed alternatively as

.. math::
   :label: dummy19
   
   I_m^{\rm RL} = -A_m^{} \Big(\sum_l k_{ml}^{} {\mathcal P}_{ml}^{} \Big)
   \left|\frac{\Omega_m}{1+\frac{1}{f_m^{\rm lim}} \big(1-\Omega_m\big)}\right|^{\beta_m} {\rm sign}(1-K_m Q_m).

.. _material-property-updates:

Changes in Material Properties
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Permeability, tortuosity and mineral surface area may be
updated optionally due to mineral precipitation and dissolution
reactions through the change in porosity

.. math::
   :label: porosity
   
   \porosity = 1-\sum_m\porosity_m.

In this case, the initial porosity is calculated as

.. math::
   :label: initial_porosity
   
   \porosity_0 = 1-\sum_m\porosity_m^0,

where the super/subscript 0 denotes initial values.

Change in permeability involves a phenomenological relation with porosity

.. math::
   :label: permeability
   
   k = k_0 f(\porosity,\,\porosity_0,\,\porosity_c,\,n),

with

.. math::
   :label: permf
   
   f = \left(\frac{\porosity-\porosity_c}{\porosity_0-\porosity_c}\right)^n,
   
.. math::
   :label: fmin
   
   = f_{\rm min} \ \ \ \text{if} \ \ \ \porosity \leq \porosity_c, 

.. math::
   :label: tortuosity
   
   \tortuosity = \tortuosity_0 \left(\frac{\porosity}{\porosity_0}\right)^b,

and

.. math::
   :label: surface_area_vf
   
   A_m = A_m^0 \left(\frac{\porosity_m}{\porosity_m^0}\right)^n  \left(\frac{1-\porosity}{1-\porosity_0}\right)^{n'},

with a typical value
for :math:`n` of :math:`2/3` reflecting the surface to volume ratio.
Note that this relation only applies to primary minerals
:math:`(\porosity_m^0 > 0)`. The quantity :math:`\porosity_c` refers to a
critical porosity below which the permeability is assumed to be constant
with scale factor :math:`f_{\rm min}`.

The two-thirds power arises from the assumption that the number of reacting mineral grains contained in a REV remains constant. To see this consider cubical grains with the length of a side denoted by :math:`\ell_m` (note that spheres could also be used without changing the result). Then the volume and surface area of an individual grain are given by

.. math::
   :label: cubes_vol

   v_m = \ell_m^3,

and

.. math::
   :label: cubes_area

   a_m = 6 \ell_m^2.

The mineral volume fraction can be written in terms of the grain size as

.. math::
   :label: vol_frac_lm

   \porosity_m = \frac{V_m}{V} = \frac{N_m v_m}{V} = \eta_m \ell_m^3,

where the grain density given by

.. math::
   :label: eta_m

   \eta_m = \frac{N_m}{V}

is assumed to be constant.
It follows that solving for :math:`\ell_m` gives

.. math::
   :label: dum0

   \ell_m = \left(\frac{\porosity_m}{\eta_m}\right)^{1/3},

and thus squaring yields

.. math::
   :label: dum1

   \ell_m^2 = \left(\frac{\porosity_m}{\eta_m}\right)^{2/3}.

Therefore the mineral surface area :math:`A_m` is given by

.. math::
   :label: dum2

   A_m = \eta_m a_m = 6 \eta_m \ell_m^{2} = 6 \eta_m \left(\frac{\porosity_m}{\eta_m}\right)^{2/3}
   = 6 \eta_m^{1/3} \porosity_m^{2/3}.

A similar expression can be written for the initial surface area

.. math::
   :label: dum3

   A_m^0 = 6 \eta_m \left(\frac{\porosity_m^0}{\eta_m}\right)^{2/3},

using the same grain density :math:`\eta_m` by assumption. Taking their ratio then gives the desired result

.. math::
   :label: dum4

   A_m = A_m^0 \left(\frac{\porosity_m}{\porosity_m^0}\right)^{2/3},

which is independent of the grain density. It should be noted, however, that this result only applies to primary minerals because of the restriction :math:`\porosity_m^0 > 0`. For secondary minerals, or a primary mineral which has completely dissolved at a grid cell, Eqn. :eq:`dum2` must be used 
(This formulation is currently not implemented in PFLOTRAN).

In PFLOTRAN the solid is represented as an aggregate of minerals
described quantitatively by specifying its porosity :math:`\porosity` and
the volume fraction :math:`\porosity_m = V_m/V` of each primary mineral referenced
to the bulk volume :math:`V` of the porous medium. It is not
necessary that Eqn. :eq:`porosity` relating porosity and
mineral volume fractions holds, and often the porosity is kept constant during the simulation. 

An alternative formulation of the mineral volume fraction is to specify it 
relative to the total mineral volume
rather than the bulk volume

.. math::
   :label: solid_vol

   \hat\porosity_m = \frac{V_m}{V_s} = \frac{V_m}{\sum_{m'} V_{m'}},

with :math:`\sum_m\hat\porosity_m=1`.
The two formulations are related by the porosity as given by

.. math::
   :label: convert

   \porosity_m = (1-\porosity) \hat\porosity_m.


The solid composition may also be specified by giving the mass or 
mole fractions :math:`y_m, x_m` of each
of the primary minerals making up the solid phase. The volume fraction
is related to mole :math:`x_m` and mass :math:`y_m` fractions by the
expressions

.. math::
   :label: dummy20
   
   \porosity_m &= (1-\porosity) \frac{x_m \overline V_m}{\sum_{m'} x_{m'} \overline V_{m'}},\\
   &= (1-\porosity) \frac{y_m^{} \density_m^{-1}}{\sum_{m'} y_{m'}^{} \density_{m'}^{-1}}.

The inverse relation is given by

.. math::
   :label: dummy21
   
   x_m = \frac{\porosity_m}{\overline V_m \eta_s(1-\porosity)},

and similarly for the mass fraction, where

.. math::
   :label: dummy22
   
   \density_m^{} = W_m^{} \overline V_m^{-1},

and the solid molar density :math:`\eta_s` is given by

.. math::
   :label: dummy23
   
   \eta_s = \frac{1}{\sum_m x_m \overline V_m}.

In these relations :math:`W_m` refers to the formula weight and
:math:`\overline V_m` the molar volume of the :math:`m`\ th mineral.
The solid molar density is related to the mass density :math:`\density_s` by

.. math::
   :label: dummy24
   
   \density_s = W_s \eta_s,

with the mean molecular weight :math:`W_s` of the solid phase equal to

.. math::
   :label: dummy25
   
   W_s = \sum_m x_m W_m = \frac{1}{\sum_m W_m^{-1} y_m^{}}.

Mass and mole fractions are related by the expression

.. math::
   :label: dummy26
   
   W_m x_m = W_s y_m.

Variable Surface Area
^^^^^^^^^^^^^^^^^^^^^

An semi-analytical solution can be derived for the mineral volume fraction 
mass balance equation

.. math::
   :label: min_mass_bal

   \frac{\partial\porosity_m}{\partial t} = \overline V_m I_m

for stationary state conditions. The reaction rate :math:`I_m` is assumed to 
have the typical form
based on transition state theory

.. math::
   :label: rate_m

   I_m = - k_m A_m \Omega_m

with affinity factor :math:`\Omega_m = 1-K_m Q_m` assumed to be constant. 
The mineral surface area :math:`A_m` is assumed to be a power law function 
of the mineral volume fraction

.. math::
   :label: var_surf_area

   A_m = A_m^0 \left(\frac{\porosity_m}{\porosity_m^0}\right)^n,

with constant :math:`n`. The affinity factor :math:`\Omega_m` is constant, for example, for a stationary state or at the inlet boundary. The mineral mass balance equation can then be written in the form

.. math::
   :label: min_mass_bal2

   \frac{\partial\zeta_m}{\partial t} = -\alpha_m \zeta_m^n,

where :math:`\zeta_m` is defined as the ratio

.. math::
   :label: zeta

   \zeta_m = \frac{\porosity_m}{\porosity_m^0},

where :math:`\porosity_m^0` refers to the initial mineral volume fraction at :math:`t=0` and :math:`\alpha_m` is given by

.. math::
   :label: alpha

   \alpha_m = \frac{\overline V_m k_m A_m^0 \Omega_m}{\porosity_m^0}.

The equation for :math:`\zeta_m` can be solved analytically with the initial condition :math:`\zeta(0)=1` to give

.. math::
   :label: zeta_of_t

   \zeta_m(t) = \left(1-(1-n) \alpha_m t \right)^{1/(1-n)}, \ \ \ (n\ne 1).

This solution breaks down if :math:`n=1`, in which case one can solve for :math:`\zeta_m` directly to give the exponential relation

.. math::
   :label: expoft

   \zeta_m(t) = {\rm e}^{-\alpha_m t}, \ \ \ (n=1).

Affinity Threshold
^^^^^^^^^^^^^^^^^^

An affinity threshold :math:`f` for precipitation may be introduced
which only allows precipitation to occur if :math:`K_m Q_m > f > 1`.

.. 
 Surface Armoring
 ^^^^^^^^^^^^^^^^

 Surface armoring occurs when one mineral precipitates on top of another
 mineral, blocking that mineral from reacting. Thus suppose mineral
 :math:`{{\mathcal M}}_m` is being replaced by the secondary mineral
 :math:`{{\mathcal M}}_{m'}`. Blocking may be described
 phenomenologically by the surface area relation

 .. math::
    :label: surface_armoring
   
    a_m(t) = a_m^0 \left(\frac{\porosity_m}{\porosity_m^0}\right)^n  \left(\frac{1-\porosity}{1-\porosity_0}\right)^{n'} \left(\frac{\porosity_{m'}^c - \porosity_{m'}}{\porosity_{m'}^c}\right)^{n''},
 
 for :math:`\porosity_{m'} < \porosity_{m'}^c`, and

 .. math::
    :label: dummy27
    
    a_m = 0,
   

 if :math:`\porosity_{m'}(t) \geq \porosity_{m'}^c`, where
 :math:`\porosity_{m'}^c` represents the critical volume fraction necessary
  for complete blocking of the reaction of mineral
 :math:`{{\mathcal M}}_m`.

Sorption
++++++++

Sorption reactions incorporated into PFLOTRAN consist of specifying a sorption
isotherm, ion exchange reactions, and equilibrium and multirate formulations of surface 
complexation reactions. Each of these is dealt with in more detail below.

Sorption Isotherm
^^^^^^^^^^^^^^^^^

The sorption isotherm relates the sorbed concentration at the solid surface to the
aqueous concentration in contact with the solid at constant temperature. 
It is a function of the free ion primary species
concentrations :math:`S_j(c_1,\,\ldots, \,c_{N_c})` (not total conentrations). 
It is a phenomenological formulation as opposed to a mechanisitc one and is
typically not associated with an explicit chemical reaction.
Finally, note that a sorption isotherm
may represent equilibrium or kinetic processes depending on the data used to fit the 
isotherm.

The sorption isotherm appears as a 
source/sink term in the transport equations as given by

.. math::
   :label: isothrm

   \frac{\partial}{\partial t} \porosity \saturation_l \Psi_j + \vec\nabla\cdot\vec\Omega_j = 
   -\frac{\partial S_j}{\partial t},

with saturation :math:`s_l`. Combining time derivative terms the transport equations become

.. math::
   :label: transport_eqn

   \frac{\partial}{\partial t} \big(\porosity \saturation_l\Psi_j + S_j \big) 
   + \vec\nabla\cdot\vec\Omega_j = 0,

This equation can be rewritten as

.. math::
   :label: retardeqn

   \frac{\partial}{\partial t} \Big[\porosity \saturation_l\Psi_j R_j \Big] 
   + \vec\nabla\cdot\vec\Omega_j = 0,
 
where the local retardation factor :math:`R_j` is defined in terms of the distribution coefficient
:math:`K_j^D` as

.. math::
   :label: retard

   R_j &= 1 + K_j^D,\\
   K_j^D &= \frac{S_j}{\porosity \saturation_l\Psi_j}.

For the case when :math:`R_j` = constant, the transport equation 
can be written in the form

.. math::
   :label: reteqn

   \frac{\partial}{\partial t} \Big[\porosity \saturation_l\Psi_j\Big] 
   + \vec\nabla\cdot\frac{1}{R_j}\vec\Omega_j = 0,

resulting in retarded advective and diffusive/dispersive transport. Note that the retardation
varies inversely with the total concentration, not the free ion concentration, and
thus aqueous complexing reactions lead to a reduction in the retardation.
As a consequence strong complexing can reduce significantly the retardation coefficient compared to
the value obtained using the free ion concentration.

The distribution coefficient :math:`\tilde K_j^D` [m\ :math:`^3`
kg\ :math:`^{-1}`] is customarily defined as the ratio of sorbed to
aqueous concentrations with the sorbed concentration referenced to the
mass of solid as given by

.. math::
   :label: dummy71
   
   \tilde K_j^D &= \frac{S_j^M/M_s}{M_j^{\rm aq}/V_l},\\
   &= \frac{N_j^s/M_s}{N_j^{\rm aq}/V_l},\\
   &= \frac{\tilde S_j}{C_j} = \frac{1}{\density_w}\frac{\tilde S_j}{m_j},

where :math:`S_j^M = W_j N_j^s`, :math:`M_j^{\rm aq} = W_j N_j^{\rm aq}`,
refers to the mass and number of moles of sorbed and aqueous solute
related by the formula weight :math:`W_j` of the :math:`j`\ th species,
:math:`M_s` refers to the mass of the solid, :math:`V_l` denotes the
aqueous volume, :math:`\tilde S_j=N_j^s/M_s` [mol kg\ :math:`^{-1}`]
represents the sorbed concentration referenced to the mass of solid,
:math:`C_j=N_j^{\rm aq}/V_l` denotes molarity, and
:math:`m_j=C_j/\density_w` represents molality, where :math:`\density_w` is the
density of pure water.

The distribution coefficient :math:`\tilde K_j^D` may be related to
its dimensionless counterpart :math:`K_j^D` [—] defined by

.. math::
   :label: kdj
   
   K_j^D = \frac{N_j^s}{N_j^{\rm aq}} = \frac{N_j^s/V}{N_j^{\rm aq}/V}= \frac{1}{\porosity \saturation_l}\frac{S_j}{C_j},
   
by writing

.. math::
   :label: dummy72
   
   K_j^D &= \frac{N_j^s}{M_s} \frac{M_s}{V_s} \frac{V_s}{V_p} \frac{V_p}{V_l} \frac{V_l}{N_j^{\rm aq}},\\
   &= \density_s \frac{1-\porosity}{\porosity \saturation_l} \tilde K_j^D = \frac{\density_b}{\porosity \saturation_l} \tilde K_j^D,

with grain density :math:`\density_s=M_s/V_s`, bulk density
:math:`\density_b=(1-\porosity)\density_s`, porosity :math:`\porosity=V_p/V`, and
saturation :math:`s_l=V_l/V_p`.

An alternative definition of the distribution coefficient denoted by
:math:`\hat K_j^D` [kg m\ :math:`^{-3}`] is obtained by using
molality to define the solute concentration and referencing the sorbed
concentration to the bulk volume :math:`V`

.. math::
   :label: dummy73

   \hat K_j^D = \frac{N_j^s/V}{N_j^{\rm aq}/M_w} = \frac{S_j}{m_j}.

The local retardation coefficient :math:`R_j` can be expressed in the alternative forms

.. math::
   :label: dummy76
   
   R_j &= 1 + K_j^D, \ \ \ \ \ \ (\text{dimensionless)},\\
   &= 1+ \frac{\density_b}{\porosity \saturation_l} \tilde K_j^D, \ \ \ \ \ \ (\text{conventional}),\\
   &= 1+ \frac{1}{\porosity \saturation_l \density_w} \hat K_j^D, \ \ \ \ \ \ (\text{molality-based}).

Three distinct models are available for the sorption isotherm
:math:`S_j` in PFLOTRAN:

-  linear :math:`K_D` model:

   .. math::
      :label: linkd
      
      S_j = \porosity \saturation_l K_j^D C_j = \hat K_j^D m_j,

   with distribution coefficient :math:`\hat K_j^D`.

-  Langmuir isotherm:

   .. math::
      :label: Langmuir
      
      S_j= \frac{K_j^L b_j^L C_j/ \density_w}{1+K_j^L C_j/ \density_w} = \frac{K_j^L b_j^L m_j}{1+K_j^L m_j},

   with Langmuir coefficients :math:`K_j^L` and :math:`b_j^L`.

-  Freundlich isotherm:

   .. math::
      :label: Freundlich
      
      S_j = K_j^F \left(\frac{C_j}{\density_w}\right)^{(1/n_j^F)}  = K_j^F \big(m_j\big)^{(1/n_j^F)},

   with coefficient :math:`K_j^F` and inverse power :math:`n_j^F`.

Ion Exchange
^^^^^^^^^^^^

In PFLOTRAN ion exchange reactions are written in terms of a
reference cation denoted by :math:`{\mathcal A}_j^{z_j+}` which appears on the
right-hand side of the reaction

.. math::
   :label: ex1
   
   z_j^{} {\mathcal A}_i^{z_i+} + z_i^{} (\chi_{\alpha})_{z_j} {\mathcal A}_j {~\rightleftharpoons~} z_i^{} {\mathcal A}_j^{z_j+} + z_j^{} (\chi_{\alpha})_{z_i} {\mathcal A}_i,
   

with valencies :math:`z_j`, :math:`z_i` for cations
:math:`{\mathcal A}_j^{z_j+}` and :math:`{\mathcal A}_i^{z_i+}`,
respectively, and exchange site :math:`\chi_{{\alpha}}^-` of type :math:`\alpha` on the solid
surface. The cations :math:`{{\mathcal A}}_i^{z_i+}, \,i\ne j`
represent all other cations besides the reference cation. The
corresponding mass action equation is given by

.. math::
   :label: ionexmassact
   
   K_{ij}^{\alpha}= \left(\frac{\lambda_i^{{\alpha}}X_i^{{\alpha}}}{a_i}\right)^{z_j}
   \left(\frac{a_j}{\lambda_j^{{\alpha}}X_j^{{\alpha}}}\right)^{z_i},

with selectivity coefficient :math:`K_{ij}^{{\alpha}}`, solid phase
activity coefficients :math:`\lambda_l^{{\alpha}}` (taken as unity in
what follows), and mole fraction :math:`X_l^{{\alpha}}` of the
:math:`l`\ th cation on site :math:`{{\alpha}}`. For :math:`N_c` cations
participating in exchange reactions, there are :math:`N_c-1` independent
reactions and thus :math:`N_c-1` independent selectivity coefficients.

The exchange reactions may also be expressed as half reactions in the
form

.. math::
   :label: dummy31
   
   z_j^{} \chi_{\alpha}^- + {\mathcal A}_j^{z_j+} {~\rightleftharpoons~}(\chi_{\alpha})_{z_j} {\mathcal A}_j^{},

with corresponding selectivity coefficient :math:`k_j^{{\alpha}}`. The
half-reaction selectivity coefficients are related to the
:math:`K_{ij}^{{\alpha}}` by

.. math::
   :label: dummy32
   
   \log K_{ij}^{{\alpha}}= z_j^{} \log k_i^{{\alpha}}- z_i^{} \log k_j^{{\alpha}},

or

.. math::
   :label: eqkij
      
   K_{ij}^{\alpha} = \frac{(k_i^{{\alpha}})^{z_j}}{(k_j^{\alpha})^{z_i}}.

This relation is obtained by multiplying the half reaction for cation
:math:`{\mathcal A}_j^{z_j+}` by the valence :math:`z_i` and subtracting from
the half reaction for :math:`{\mathcal A}_i^{z_i+}` multiplied by
:math:`z_j`, resulting in cancelation of the empty site
:math:`\chi_{\alpha}^-`, to obtain the complete exchange reaction
:eq:`ex1`. It should be noted that the coefficients
:math:`k_l^{\alpha}` are not unique since, although there are
:math:`N_c` coefficients in number, only :math:`N_c-1` are independent
and one may be chosen arbitrarily, usually taken as unity. Thus for
:math:`k_j^{\alpha}=1`, Eqn. :eq:`eqkij` yields

.. math::
   :label: dummy33
   
   k_i^{\alpha} = \big(K_{ij}^{\alpha}\big)^{1/z_j}.
   

An alternative form of reactions :eq:`ex1` often found in
the literature is

.. math::
   :label: rxn2
   
   \frac{1}{z_i} \,{\mathcal A}_i^{z_i+} + \frac{1}{z_j}\, (\chi_{\alpha})_{z_j} {\mathcal A}_j {~\rightleftharpoons~}\frac{1}{z_j} \,{\mathcal A}_j^{z_j+} + \frac{1}{z_i}\, (\chi_{\alpha})_{z_i} {\mathcal A}_i,
   

obtained by dividing reaction :eq:`ex1` through by the
product :math:`z_i z_j`. The mass action equations corresponding to
reactions :eq:`rxn2` have the form

.. math::
   :label: dummy34
   
   {\tilde K}_{ij}^{\alpha}= \frac{({\tilde k}_i^{{\alpha}})^{1/z_i}}{({\tilde k}_j^{{\alpha}})^{1/z_j}} = \left(\frac{a_j}{X_j^{\alpha}}\right)^{1/z_j} \left(\frac{X_i^{\alpha}}{a_i}\right)^{1/z_i}.

The selectivity coefficients corresponding to the two forms are related
by the expression

.. math::
   :label: dummy35
   
   {\tilde K}_{ij}^{{\alpha}}= \left(K_{ij}^{{\alpha}}\right)^{1/(z_i z_j)},

and similarly for :math:`k_i^{{\alpha}}`, :math:`k_j^{{\alpha}}`. When
comparing with other formulations it is important that the user
determine which form of the ion exchange reactions are being used and
make the appropriate transformations.

The governing equations incorporating homogeneous aqueous complexing reactions 
combined with ion exchange reactions with reaction rates
:math:`\Gamma_{ji}` and with reference cation :math:`{\mathcal A}_j` have the form

.. math::
   :label: refcat

   \frac{\partial}{\partial t } \porosity \Psi_j + \vec\nabla\cdot\vec\Omega_j &= \sum_{i\ne j} z_i \Gamma_{ji},\\
   \frac{\partial}{\partial t } \porosity \Psi_i + \vec\nabla\cdot\vec\Omega_i &= -z_j \Gamma_{ji},\\
   \frac{\partial S_j}{\partial t} &= -\sum_{i\ne j} z_i \Gamma_{ji},\\
   \frac{\partial S_i}{\partial t} &= z_j \Gamma_{ji}.

The ion exchange reaction rates may be eliminated from the aqueous transport equations to yield

.. math::
   :label: refcateq

   \frac{\partial}{\partial t } \porosity \Psi_j + \vec\nabla\cdot\vec\Omega_j &= -\frac{\partial S_j}{\partial t},\\
   \frac{\partial}{\partial t } \porosity \Psi_i + \vec\nabla\cdot\vec\Omega_i &= -\frac{\partial S_i}{\partial t}.

Assuming conditions of local equilibrium the ion exchange reaction rates may be eliminated and replaced by
isotherms.

It can be easily demonstrated that the governing equations conserve the exchange site density :math:`\omega` given by

.. math::
   :label: siteden

   \omega = z_j S_j + \sum_{i\ne j} z_i S_i,

assuming material properties are not altered by mineral precipitation/dissolution reactions. 
It follows that

.. math::
   :label: sitecon

   \frac{\partial\omega(\vec r, \, t)}{\partial t} &= z_j \sum_{i\ne j} z_i \Gamma_{ji} -
   z_j \sum_{i \ne j} z_i \Gamma_{ji},\\
   &=0.

Since charge is conserved by the ion exchange reactions, 
the transport equations coupled to ion exchange must also
conserve charge and as a result no additional constraints are needed.

Exchange Capacity
^^^^^^^^^^^^^^^^^

Ion exchange reactions may be represented either in terms of bulk- or
mineral-specific rock properties. Changes in bulk sorption properties
can be expected as a result of mineral reactions. However, only the
mineral-based formulation enables these effects to be captured in the
model. The bulk rock sorption site concentration
:math:`\omega_{{\alpha}}`, in units of moles of sites per bulk rock
volume (mol/dm\ :math:`^3`), is related to the bulk cation exchange
capacity :math:`Q_{\alpha}` (mol/kg) by the expression

.. math::
   :label: dummy28
   
   \omega_{{\alpha}}= \frac{N_{\rm site}}{V} = \frac{N_{\rm site}}{M_s} \frac{M_s}{V_s} \frac{V_s}{V} = (1-\porosity) \density_s Q_{{\alpha}},

with solid density :math:`\density_s` and porosity :math:`\porosity`. The
cation exchange capacity associated with the :math:`m`\ th mineral is
defined on a molar basis as

.. math::
   :label: dummy29
   
   \omega_m^{\rm CEC} = \frac{N_m}{V} = \frac{N_m}{M_m} \frac{M_m}{V_m} \frac{V_m}{V} = Q_m^{\rm CEC} \density_m \porosity_m.

The site concentration :math:`\omega_{{\alpha}}` is related to the
sorbed concentrations :math:`S_k^{{\alpha}}` by the expression

.. math::
   :label: dummy30
   
   \omega_{{\alpha}}^{} = \sum_k z_k^{} S_k^{{\alpha}}.
   

Selectivity Coefficient Relations
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The selectivity coefficients satisfy the relations

.. math::
   :label: dummy36
   
   K_{ji}^{{\alpha}}= \big(K_{ij}^{{\alpha}}\big)^{-1},

and from the identity

.. math::
   :label: dummy37
   
   \left(\frac{X_i^{{\alpha}}}{a_i}\right)^{z_j}\left(\frac{a_j}{X_j^{{\alpha}}}\right)^{z_i}
   = \left[
   \left(\frac{X_i^{{\alpha}}}{a_i}\right)^{z_l} \left(\frac{a_l}{X_l^{{\alpha}}}\right)^{z_i}
   \right]^{z_j/z_l}
   \left[
   \left(\frac{X_l^{{\alpha}}}{a_l}\right)^{z_j}\left(\frac{a_j}{X_j^{{\alpha}}}\right)^{z_l}
   \right]^{z_i/z_l},

the following relation is obtained

.. math::
   :label: dummy38
   
   K_{ij}^{{\alpha}}= \big(K_{il}^{{\alpha}}\big)^{z_j/z_l}\big(K_{lj}^{{\alpha}}\big)^{z_i/z_l}.

To see how the selectivity coefficients change when changing the
reference cation from :math:`{{\mathcal A}}_j^{z_j+}` to
:math:`{{\mathcal A}}_k^{z_k+}` note that

.. math::
   :label: dummy39
   
   \tilde K_{jk}^{\alpha} = \big(\tilde K_{kj}^{\alpha}\big)^{-1},

and

.. math::
   :label: dummy40
   
   \tilde K_{ik}^{{\alpha}}= \tilde K_{ij}^{{\alpha}}\, \tilde K_{jk}^{{\alpha}}.

This latter relation follows from adding the two reactions

.. math::
   :label: dummy41
   
   \frac{1}{z_i} \,{\mathcal A}_i + \frac{1}{z_j}\, (\chi_{\alpha})_{z_j} {\mathcal A}_j &{~\rightleftharpoons~}\frac{1}{z_j} \,{\mathcal A}_j + \frac{1}{z_i}\, (\chi_{\alpha})_{z_i} {\mathcal A}_i,\\
   \frac{1}{z_j} \,{\mathcal A}_j + \frac{1}{z_k}\, (\chi_{\alpha})_{z_k} {\mathcal A}_k &{~\rightleftharpoons~}\frac{1}{z_k} \,{\mathcal A}_k + \frac{1}{z_j}\, (\chi_{\alpha})_{z_j} {\mathcal A}_j,

to give

.. math::
   :label: dummy42
   
   \frac{1}{z_i} \,{{\mathcal A}}_i + \frac{1}{z_k}\, (\chi_{{\alpha}})_{z_k} {{\mathcal A}}_k {~\rightleftharpoons~}\frac{1}{z_k} \,{{\mathcal A}}_k + \frac{1}{z_i}\, (\chi_{{\alpha}})_{z_i} {{\mathcal A}}_i,

with :math:`{{\mathcal A}}_k^{z_k+}` as reference cation.

In terms of the selectivity coefficients :math:`K_{ij}^{{\alpha}}` it
follows that

.. math::
   :label: dummy43
   
   \big(K_{ik}^{{\alpha}}\big)^{1/(z_i z_k)} = \big(K_{ij}^{{\alpha}}\big)^{1/(z_i z_j)} \big(K_{jk}^{{\alpha}}\big)^{1/(z_j z_k)},

or

.. math::
   :label: dummy44
   
   K_{ik}^{{\alpha}}= \big(K_{ij}^{{\alpha}}\big)^{z_k /z_j} \big(K_{jk}^{{\alpha}}\big)^{z_i/ z_j}.

In terms of the coefficients :math:`k_i^{\alpha}` and
:math:`\overline k_i^{{\alpha}}` corresponding to reference cation
:math:`{\mathcal A}_k` the transformation becomes

.. math::
   :label: dummy45
   
   \frac{\big(\overline k_i^{{\alpha}}\big)^{z_k}}{\big(\overline k_i^{{\alpha}}\big)^{z_i}} = \left[\frac{\big(k_i^{{\alpha}}\big)^{z_j}}{\big(k_i^{{\alpha}}\big)^{z_j}}\right]^{z_k/z_j}
   \left[\frac{\big(k_j^{{\alpha}}\big)^{z_k}}{\big(k_k^{{\alpha}}\big)^{z_j}}\right]^{z_i/z_j}.

In terms of the coefficients :math:`k_l^{{\alpha}}` the sorbed
concentration for the :math:`i`\ th cation can be expressed as a
function of the reference cation from the mass action equations
according to

.. math::
   :label: dummy46
   
   X_i^{{\alpha}}= k_i^{{\alpha}}a_i^{} \left(\frac{X_j^{{\alpha}}}{k_j^{{\alpha}}a_j^{}}\right)^{z_i/z_j}.

For a given reference cation :math:`{\mathcal A}_{J_0}` the
coefficients :math:`K_{iJ_0}` are uniquely determined. For some other
choice of reference cation, say :math:`{\mathcal A}_{I_0}`, the
coefficients :math:`K_{iI_0}` are related to the original coefficients
by the expressions

.. math::
   :label: dummy47
   
   \log K_{J_0I_0} &= -\log K_{I_0J_0},\\

Taking the reference cation as :math:`{\mathcal A}_j` then
:math:`k_i^{{\alpha}}` is given by

.. math::
   :label: dummy48
   
   k_i^{{\alpha}}&= \big(K_{ij}^{{\alpha}}(k_j^{{\alpha}})^{z_i}\big)^{1/z_j},\\
   &= (K_{ij}^{{\alpha}})^{1/z_j}, \ \ \ \ \ \ \ \ \ \ \ \ (k_j^{{\alpha}}=1),\\
   &= K_{ij}^{{\alpha}}, \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ (z_j=1).

As an example consider the ion-exchange reactions with Ca\ :math:`^{2+}`
as reference cation

.. math::
   :label: dummy49
   
   \rm 2 \, Na^+ + \chi_2 Ca &{~\rightleftharpoons~}\rm Ca^{2+} + 2 \, \chi Na,\\
   \rm Mg^{2+} + \chi_2 Ca &{~\rightleftharpoons~} \rm Ca^{2+} + \chi_2 Mg,

with selectivity coefficients :math:`K_{\rm NaCa}` and
:math:`K_{\rm MgCa}`. Alternatively, using Na\ :math:`^+` as reference
cation gives

.. math::
   :label: dummy50
   
   \rm Ca^{2+} + 2 \, \chi Na &{~\rightleftharpoons~}\rm 2 \, Na^+ + \chi_2 Ca,\\
   \rm Mg^{2+} + 2 \, \chi Na &{~\rightleftharpoons~}\rm 2 \, Na^{+} + \chi_2 Mg,

with selectivity coefficients :math:`K_{\rm CaNa}` and
:math:`K_{\rm MgNa}`. The selectivity coefficients are related by the
equations

.. math::
   :label: dummy51
   
   \log K_{\rm CaNa} & = -\log K_{\rm NaCa},\\
   \log K_{\rm MgNa} &= \frac{1}{2} \, \log K_{\rm MgCa} - \log K_{\rm NaCa}.


Gaines-Thomas Exchange
^^^^^^^^^^^^^^^^^^^^^^

The Gaines-Thomas convention (Gaines and Thomas, 1953), is based on the equi-valent fractions
:math:`X_k^{{\alpha}}` defined by

.. math::
   :label: dummy52
   
   X_k^{{\alpha}}= \frac{z_k S_k^{{\alpha}}}{\displaystyle\sum_l z_l S_l^{{\alpha}}} = \frac{z_k}{\omega_{{\alpha}}}S_k^{{\alpha}},

with

.. math::
   :label: dummy53
   
   \sum_k X_k^{{\alpha}}= 1.

The index :math:`\alpha` refers to distinct exchange sites.

For equi-valent exchange :math:`(z_j=z_i=z)`, an explicit expression
exists for the sorbed concentrations given by

.. math::
   :label: dummy54
   
   S_j^{{\alpha}}= \frac{\omega_{{\alpha}}}{z} \frac{k_j^{{\alpha}}\gamma_j m_j^{}}{\displaystyle\sum_l k_l^{{\alpha}}\gamma_l m_l^{}},

where :math:`m_k` denotes the :math:`k`\ th cation molality. This
expression follows directly from the mass action equations for the
sorbed cations and conservation of exchange sites.

In the more general case :math:`(z_i\ne z_j)` it is necessary to solve
the nonlinear equation

.. math::
   :label: dummy55
   
   X_j^{{\alpha}}+ \sum_{i\ne j} X_i^{{\alpha}}= 1,

for the reference cation mole fraction :math:`X_j`. From the mass action
equation Eqn. :eq:`ionexmassact` it follows that

.. math::
   :label: dummy56
   
   X_i^{{\alpha}}= k_i^{{\alpha}}a_i^{} \left(\frac{X_j^{{\alpha}}}{k_j^{{\alpha}}a_j^{}}\right)^{z_i/z_j}.

Defining the function

.. math::
   :label: dummy57
   
   f(X_j^{{\alpha}}) = X_j^{{\alpha}}+ \sum_{i\ne j}X_i^{{\alpha}}(X_j^{{\alpha}})-1,

its derivative is given by

.. math::
   :label: dummy58
   
   \frac{df}{dX_j^{{\alpha}}} = 1 - \frac{1}{z_j^{} X_j^{{\alpha}}}\sum_{i\ne j} z_i^{} k_i^{{\alpha}}a_i^{} \left(\frac{X_j^{{\alpha}}}{k_j^{{\alpha}}a_j^{}}\right)^{z_i/z_j}.

The reference mole fraction is then obtained by Newton-Raphson iteration

.. math::
   :label: dummy59
   
   (X_j^{{\alpha}})^{k+1} = (X_j^{{\alpha}})^k -\dfrac{f[(X_j^{{\alpha}})^k]}{\dfrac{df[(X_j^{{\alpha}})^k]}{dX_j^{{\alpha}}}}.

The sorbed concentration for the :math:`j`\ th cation appearing in the
accumulation term is given by

.. math::
   :label: dummy60
   
   S_j^{{\alpha}}= \frac{\omega_{{\alpha}}}{z_j} X_j^{{\alpha}},

with the derivatives for :math:`j\ne l`

.. math::
   :label: dummy61
   
   \dfrac{{{\partial}}S_j^{{\alpha}}}{{{\partial}}m_l} &= -\frac{\omega_{{\alpha}}}{m_l} \dfrac{X_j^{{\alpha}}X_l^{{\alpha}}}{\displaystyle\sum_l z_l X_l^{{\alpha}}},\\
   &= -\frac{1}{m_l} \dfrac{z_jz_lS_j^{{\alpha}}S_l^{{\alpha}}}{\displaystyle\sum_l z_l^2 S_l^{{\alpha}}},

and for :math:`j=l`

.. math::
   :label: dummy62
   
   \dfrac{{{\partial}}S_j^{{\alpha}}}{{{\partial}}m_j} &= \frac{\omega_{{\alpha}}X_j^{{\alpha}}}{z_j m_j} \left(1-\dfrac{z_j X_j^{{\alpha}}}{\displaystyle\sum_{l} z_{l} X_{l}^{{\alpha}}}\right),\\
   &= \frac{S_j^{{\alpha}}}{m_j} \left(1-\dfrac{z_j^2 S_j^{{\alpha}}}{\displaystyle\sum_{l} z_{l}^2 S_{l}^{{\alpha}}}\right).
   

Surface Complexation
^^^^^^^^^^^^^^^^^^^^

Surface complexation reactions are assumed to have the form

.. math::
   :label: srfrxn
   
   \nu_{{\alpha}}>\chi_{{\alpha}}+ \sum_j\nu_{ji} {{\mathcal A}}_j {~\rightleftharpoons~}> {{\mathcal S}}_{i{{\alpha}}},

for the :math:`i`\ th surface complex
:math:`>{{\mathcal S}}_{i{{\alpha}}}` on site :math:`{{\alpha}}` and
empty site :math:`>\chi_{{\alpha}}`. As follows from the corresponding
mass action equation the equilibrium sorption concentration
:math:`S_{i{{\alpha}}}^{\rm eq}` is given by

.. math::
   :label: dummy63
   
   S_{i{{\alpha}}}^{\rm eq}= \frac{\omega_{{\alpha}}K_i Q_i}{1+\sum_l K_lQ_l},

and the empty site concentration by

.. math::
   :label: dummy64
   
   S_{{\alpha}}^{\rm eq}= \frac{\omega_{{\alpha}}}{1+\sum_l K_lQ_l},

where the ion activity product :math:`Q_i` is defined by

.. math::
   :label: dummy65
   
   Q_i= \prod_j\big(\gamma_jC_j\big)^{\nu_{ji}}.

The site concentration :math:`\omega_{{\alpha}}` satisfies the relation

.. math::
   :label: totsite
   
   \omega_{{\alpha}}= S_{{\alpha}}+ \sum_i S_{i{{\alpha}}},

and is constant. The equilibrium sorbed concentration
:math:`S_{j{{\alpha}}}^{\rm eq}` is defined as

.. math::
   :label: qeq
   
   S_{j{{\alpha}}}^{\rm eq} = \sum_i \nu_{ji}^{} S_{i{{\alpha}}}^{\rm eq}= \frac{\omega_{{\alpha}}}{1+\sum_l K_lQ_l} \sum_i \nu_{ji}K_i Q_i.

Multirate Sorption
^^^^^^^^^^^^^^^^^^

In the multirate model the rates of sorption reactions are described
through a kinetic relation given by

.. math::
   :label: sorbed
   
   \frac{{{\partial}}S_{i{{\alpha}}}}{{{\partial}}t} = k_{{\alpha}}^{} \big(S_{i{{\alpha}}}^{\rm eq}-S_{i{{\alpha}}}\big),

for surface complexes, and

.. math::
   :label: fsite

   \frac{{{\partial}}S_{{{\alpha}}}}{{{\partial}}t} &= -\sum_i k_{{\alpha}}^{} \big(S_{i{{\alpha}}}^{\rm eq}-S_{i{{\alpha}}}\big),\\
                                                    &= k_{{\alpha}}\big(S_{{\alpha}}^{\rm eq}-S_{{{\alpha}}}\big),

for empty sites, where :math:`S_{{\alpha}}^{\rm eq}` denotes the
equilibrium sorbed concentration. For simplicity, in what follows it is
assumed that :math:`\nu_{{\alpha}}=1`. With each site :math:`{{\alpha}}`
is associated a rate constant :math:`k_{{\alpha}}` and site
concentration :math:`\omega_{{\alpha}}`. These quantities are defined
through a given distribution of sites :math:`\wp({{\alpha}})`, such that

.. math::
   :label: dummy66

   \int_0^\infty \wp(k_{{\alpha}})dk_{{\alpha}}= 1.

The fraction of sites :math:`f_{{\alpha}}` belonging to site
:math:`{{\alpha}}` is determined from the relation

.. math::
   :label: dummy67
   
   f_{{\alpha}}= \int_{k_{{\alpha}}-\Delta k_{{\alpha}}/2}^{k_{{\alpha}}+\Delta k_{{\alpha}}/2} \wp(k_{{\alpha}})dk_{{\alpha}}\simeq \wp(k_{{\alpha}})\Delta k_{{\alpha}},

with the property that

.. math::
   :label: dummy68
   
   \sum_{{\alpha}}f_{{\alpha}}=1.

Given that the total site concentration is :math:`\omega`, then the site
concentration :math:`\omega_{{\alpha}}` associated with site
:math:`{{\alpha}}` is equal to

.. math::
   :label: dummy69
   
   \omega_{{\alpha}}= f_{{\alpha}}\omega.

An alternative form of these equations is obtained by introducing the
total sorbed concentration for the :math:`j`\ th primary species for
each site defined as

.. math::
   :label: dummy70

   S_{j{{\alpha}}}= \sum_i \nu_{ji}S_{i{{\alpha}}}.

Then the transport equations become

.. math::
   :label: totj
   
   \frac{{{\partial}}}{{{\partial}}t}\left(\porosity \Psi_j + \sum_{{{\alpha}}}S_{j{{\alpha}}}\right) + {\boldsymbol{\nabla}}\cdot{\boldsymbol{\Omega}}_j = - \sum_m\nu_{jm}I_m.

The total sorbed concentrations are obtained from the equations

.. math::
   :label: sja
   
   \frac{{{\partial}}S_{j{{\alpha}}}}{{{\partial}}t} = k_{{\alpha}}^{} \big(S_{j{{\alpha}}}^{\rm eq}-S_{j{{\alpha}}}\big).

Aqueous Complexing Reaction Kinetics
++++++++++++++++++++++++++++++++++++

PFLOTRAN allows the user to input kinetic reactions for homogeneous aqueous complexing reactions
through the GENERAL_REACTION keyword. 
The reactions are treated as being elementary reactions with reaction rate expressions
derived from the law of mass action. 
Use the sandbox for more general kinetic rate laws not limited to elementary reactions based on the law of mass action.

To develop the governing equations for this system, reactions are written for intrinsically
fast and slow reactions corresponding to local equilibrium and kinetic
rates of reaction according to

.. math::
   :label: eqlib

   \sum_j \nu_{ji}^{leq} {\mathcal A}_j &\rightleftharpoons {\mathcal A}_i, \ \ \ (\text{fast}),\\
   \emptyset &\rightleftharpoons \sum_j \nu_{jr}^{kin} {\mathcal A}_j, \ \ \ (\text{slow}).

The sums are over a set of independent primary species. 
In the expression for kinetic reactions all species are brought to the right-hand side with reactants
having negative stoichiometric coefficients and products positive coefficients. The reaction rates 
corresponding to fast reactions are eliminated from the transport equations
and replaced by algebraic mass action relations.

The kinetic rate expression is assumed to have the form of the difference 
between forward and backward reaction rates proportional to the product of concentrations of
reactants and products, respectively, raised to the power of their stochiometric coefficients

.. math::
   :label: kinrxn

   \Gamma_r = k_r^+ \prod_{\nu_{jr}^{kin}<0} (a_j)^{-\nu_{jr}^{kin}} - k_r^- \prod_{\nu_{jr}^{kin}>0} (a_j)^{\nu_{jr}^{kin}}.

At equilibrium :math:`\Gamma_r=0` and the equilibrium mass action equation is retrieved

.. math::
   :label:

   K_r = \frac{k_r^+}{k_r^-} = \prod_j a_j^{\nu_{jr}^{kin}},

with the equilibrium constant :math:`K_r` equal to the ratio of the forward to backward rate constants.

With the above reactions the transport equations for primary species have the form (including precipitation/disollution reactions with rates :math:`\Gamma_m`)

.. math::
   :label: genrxn

   \frac{\partial}{\partial t} \porosity \Psi_j + \vec\nabla\cdot\vec\Omega_j = \sum_r \nu_{jr}^{kin} \Gamma_r
   -\sum_m \nu_{jm} \Gamma_m,

where :math:`\Psi_j` and :math:`\vec\Omega_j` are the total concentration and flux, 
respectively, defined as

.. math::
   :label: totc

   \Psi_j = c_j + \sum_i \nu_{ji}^{leq} c_i,\\
   \vec\Omega_j = \vec F_j + \sum_i \nu_{ji}^{leq} \vec F_i,

where :math:`\vec F_k` is the individual species flux consisting of contributions from
advection, diffusion and dispersion, and the secondary species concentrations :math:`c_i` are given by
the mass action law

.. math::
   :label: csec

   c_i = \frac{K_i}{\gamma_i} \prod_j \big(\gamma_j c_j\big)^{\nu_{ji}^{leq}},

relating secondary species concentrations to primary species. Thus in this 
formulation the reaction rates for intrinsically fast reactions are replaced by 
mass action equations thereby reducing the number of partial differential equations that are
necessary to solve.


Colloid-Facilitated Transport
+++++++++++++++++++++++++++++

Colloid-facilitated transport is implemented into PFLOTRAN based on
surface complexation reactions. Competition between mobile and immobile
colloids and stationary mineral surfaces is taken into account. Colloid
filtration processes are not currently implemented into PFLOTRAN. A
colloid is treated as a solid particle suspended in solution or attached
to a mineral surface. Colloids may be generated through nucleation of
minerals in solution, although this effect is not included currently in
the code.

Three separate reactions may take place involving competition between
mobile and immobile colloids and mineral surfaces

.. math::
   :label: dummy77
   
   \mathrm{>} X_k^{{\rm m}}+ \sum_j\nu_{jk}{{\mathcal A}}_j &{~\rightleftharpoons~} \mathrm{>} S_k^{{\rm m}},\\
   \mathrm{>} X_k^{{\rm im}}+ \sum_j\nu_{jk}{{\mathcal A}}_j &{~\rightleftharpoons~} \mathrm{>} S_k^{{\rm im}},\\
   \mathrm{>} X_k^s + \sum_j\nu_{jk}{{\mathcal A}}_j &{~\rightleftharpoons~} \mathrm{>} S_k^s,
   
with corresponding reaction rates :math:`I_k^{{\rm m}}`,
:math:`I_k^{{\rm im}}`, and :math:`I_k^s`, where the superscripts
:math:`s`, :math:`m`, and :math:`im` denote mineral surfaces, and mobile
and immobile colloids, respectively. In addition, reaction with minerals
:math:`{{\mathcal M}}_s` may occur according to the reaction

.. math::
   :label: dummy78
   
   \sum_j\nu_{js}{{\mathcal A}}_j {~\rightleftharpoons~}{{\mathcal M}}_s.

The transport equations for primary species, mobile and immobile
colloids, read

.. math::
   :label: rateform
   
   \frac{{{\partial}}}{{{\partial}}t} \porosity \saturation_l \Psi_j^l + {\boldsymbol{\nabla}}\cdot{\boldsymbol{\Omega}}_j^l = -\sum_k\nu_{jk}\big(I_k^{{\rm m}}+ I_k^{{\rm im}}+ \sum_s I_k^s\big) - \sum_s \nu_{js} I_s,

.. math::
   :label: mobile
   
   \frac{{{\partial}}}{{{\partial}}t} \porosity \saturation_l S_k^{{\rm m}} + {\boldsymbol{\nabla}}\cdot{\boldsymbol{q}}_c S_k^{{\rm m}} = I_k^{{\rm m}},

.. math::
   :label: immobile
   
   \frac{{{\partial}}}{{{\partial}}t} S_k^{{\rm im}} = I_k^{{\rm im}},
   
.. math::
   :label: solid
   
   \frac{{{\partial}}}{{{\partial}}t} S_k^s = I_k^s,
   
where :math:`{\boldsymbol{q}}_c` denotes the colloid Darcy velocity
which may be greater than the fluid velocity :math:`{\boldsymbol{q}}`.
For conditions of local equilibrium the sorption reaction rates may be
eliminated and replaced by algebraic sorption isotherms to yield

.. math::
   :label: eqform
   
   \frac{{{\partial}}}{{{\partial}}t}\Big[ \porosity \saturation_l \Psi_j^l + \sum_k \nu_{jk} \big(\porosity \saturation_l S_k^{{\rm m}}+ S_k^{{\rm im}}+ \sum_s S_k^s\big) \Big] + {\boldsymbol{\nabla}}\cdot\Big({\boldsymbol{\Omega}}_j^l + {\boldsymbol{q}}_c \sum_k \nu_{jk} S_k^{{\rm m}}\Big) = - \sum_s \nu_{js} I_s.

In the kinetic case either form of the primary species transport
equations given by Eqn. :eq:`rateform` or :eq:`eqform` can be used 
provided it is coupled with the appropriate kinetic equations
Eqns. :eq:`mobile` -- :eq:`solid`. The mobile
case leads to additional equations that must be solved simultaneously
with the primary species equations. A typical expression for
:math:`I_k^m` might be

.. math::
   :label: dummy79
   
   I_k^m = k_k\big(S_k^m - S_{km}^{\rm eq}\big),

with rate constant :math:`k_k` and where :math:`S_{km}^{\rm eq}` is a
known function of the solute concentrations. In this case,
Eqn. :eq:`mobile` must be added to the primary species
transport equations. Further reduction of the transport equations for
the case where a flux term is present in the kinetic equation is not
possible in general for complex flux terms.

Tracer Mean Age
+++++++++++++++

PFLOTRAN implements the Eulerian formulation of solute age for a
nonreactive tracer following Goode (1996). PFLOTRAN solves the
advection-diffusion/dispersion equation for the mean age given by

.. math::
   :label: dummy80
   
   \frac{{{\partial}}}{{{\partial}}t} \porosity \saturation AC + {\boldsymbol{\nabla}}\cdot\Big({\boldsymbol{q}}AC - \porosity \saturation D {\boldsymbol{\nabla}}(AC)\Big) = \porosity \saturation C,

where :math:`A` denotes the mean age of the tracer with concentration
:math:`C`. Other quantities appearing in the age equation are identical
to the tracer transport equation for a partially saturated porous medium
with saturation state :math:`s`. The age and tracer transport equations
are solved simultaneously for the age-concentration :math:`\alpha = A C`
and tracer concentration :math:`C`. The age-concentration
:math:`{{\alpha}}` satisfies the usual advection-diffusion-dispersion
equation with a source term on the right-hand side.

The mean tracer age is calculated in PFLOTRAN by adding the species
``Tracer_Age`` together with ``Tracer`` to the list of primary species

::

      PRIMARY_SPECIES
        Tracer
        Tracer_Age
      /

Sorption may be included through a constant :math:`K_d` model if desired.

::

      SORPTION
        ISOTHERM_REACTIONS
          Tracer
            TYPE LINEAR
            DISTRIBUTION_COEFFICIENT 500. ! kg water/m^3 bulk
          /
          Tracer_Age
            TYPE LINEAR
            DISTRIBUTION_COEFFICIENT 500. ! kg water/m^3 bulk
          /
        /
      /

and specifying these species in the initial and boundary ``CONSTRAINT``
condition as e.g.:

::

    CONSTRAINT initial
      CONCENTRATIONS
        Tracer     1.e-8        F
        Tracer_Age 1.e-16       F
      /
    /

Output is given in terms of :math:`\alpha` and :math:`C` from which the
mean age :math:`A` can be obtained as :math:`A= \alpha/C`.

.. _thermodynamic-database:

Thermodynamic Database
++++++++++++++++++++++

Database Structure
^^^^^^^^^^^^^^^^^^

PFLOTRAN reads thermodynamic data from a database file that may be customized
by the user. Reactions included in the database consist of aqueous
complexation, mineral precipitation and dissolution, gaseous reactions,
and surface complexation. Ion exchange reactions and their selectivity
coefficients are entered directly from the input file. A standard
database supplied with the code is referred to as ``hanford.dat`` and is
found in the ``./database`` directory in the PFLOTRAN Git
repository. This database is an ascii text file that can be edited by
any editor and is equivalent to the EQ3/6 database (Delany and Lundeen, 1990):

::

    data0.com.V8.R6
    CII: GEMBOCHS.V2-EQ8-data0.com.V8.R6
    THERMODYNAMIC DATABASE
    generated by GEMBOCHS.V2-Jewel.src.R5 03-dec-1996 14:19:25

The database provides equilibrium constants in the form of log :math:`K`
values at a specified set of temperatures listed in the top line of the
database. A least squares fit is used to interpolate the log :math:`K`
values between the database temperatures using a Maier-Kelly expansion
of the form

.. math::
   :label: mk
   
   \log K = c_{-1} \ln T + c_0 + c_1 T + \frac{c_2}{T} + \frac{c_3}{T^2},

with fit coefficients :math:`c_i`. The thermodynamic database stores all
chemical reaction properties (equilibrium constant :math:`\log K_r`,
reaction stoichiometry :math:`\nu_{ir}`, species valence :math:`z_i`,
Debye parameter :math:`a_i`, mineral molar volume :math:`\overline V_m`,
and formula weight :math:`w_i`) used in PFLOTRAN. The database is
divided into 5 blocks as listed in Table [tdatabase], consisting of
database primary species, aqueous complex reactions, gaseous reactions,
mineral reactions, and surface complexation reactions. Each block is
terminated by a line beginning with ``’null’``. The quantity
:math:`N_{\rm temp}` refers to the number of temperatures at which log
:math:`K` values are stored in the database. In the ``hanford.dat``
database :math:`N_{\rm temp}=8` with equilibrium constants stored at the
temperatures: 0, 25, 60, 100, 150, 200, 250, and 300\ :math:`^\circ`\ C.
The pressure is assumed to lie along the saturation curve of pure water
for temperatures above 25\ :math:`^\circ`\ C and is equal to 1 bar at
lower temperatures. Reactions in the database are assumed to be written
in the form

.. math::
   :label: dummy81
   
   {\mathcal A}_r \rightleftharpoons \sum_{i=1}^{\rm nspec} \nu_{ir}{\mathcal A}_i,

as a dissasociation reaction for species :math:`{\mathcal A}_r`, where ``nspec`` refers to the
number of aqueous or gaseous species :math:`{\mathcal A}_i` on the
right-hand side of the reaction. Redox reactions in the standard
database ``hanford.dat`` are usually written in terms of
O\ :math:`_{2(g)}`. Complexation reactions involving redox sensitive
species are written in such a manner as to preserve the redox state.

+--------------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Primary Species:   | name, :math:`a_0`, :math:`z`, :math:`w`                                                                                                                                               |
+--------------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Secondary Species: | name, nspec, (\ :math:`\nu`\ (n), name(\ :math:`n`), :math:`n`\ =1, nspec), log\ :math:`K`\ (1: :math:`N_{\rm temp}`), :math:`a_0`, :math:`z`, :math:`w`                              |
+--------------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Gaseous Species:   | name, :math:`v`, nspec, (\ :math:`\nu`\ (n), name(\ :math:`n`), :math:`n`\ =1, nspec), log\ :math:`K`\ (1: :math:`N_{\rm temp}`), :math:`w`                                           |
+--------------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Minerals:          | name, :math:`v`, nspec, (\ :math:`\nu`\ (n), name(\ :math:`n`), :math:`n`\ =1, nspec), log\ :math:`K`\ (1: :math:`N_{\rm temp}`), :math:`w`                                           |
+--------------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Surface Complexes: | :math:`>`\ name, nspec, :math:`\nu`, :math:`>`\ site, (\ :math:`\nu`\ (n), name(\ :math:`n`), :math:`n`\ =1, nspec-1), log\ :math:`K`\ (1: :math:`N_{\rm temp}`), :math:`z`, :math:`w`|
+--------------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

The quantities: name, :math:`>`\ name, :math:`a_0`, :math:`z`, :math:`w`, :math:`\nu`, :math:`\log K`, and :math:`v` refer, respectively,
to the aqueous or gas species, mineral or surface complex, Debye-Hueckel radius parameter, charge, formula weight [g/mol], stoichiometric coefficient, 
logarithm of the equilibrium constant to base 10,
and molar volume [cm\ :math:`^3`/mol].

Note that chemical reactions are not unique. For example, given a
particular mineral reaction

.. math::
   :label: dummy82
   
   \sum_j \nu_{jm} {{\mathcal A}}_j {~\rightleftharpoons~}{{\mathcal M}}_m,

an equally acceptable reaction is the scaled reaction

.. math::
   :label: dummy83
   
   \sum_j \lambda_m\nu_{jm} {\mathcal A}_j {~\rightleftharpoons~}\lambda_m {\mathcal M}_m,

with scale factor :math:`\lambda_m` corresponding to a different choice of
formula unit. A different scale factor may be used for each mineral. The
scaled reaction corresponds to

.. math::
   :label: dummy84
   
   \sum_j \nu_{jm}' {\mathcal A}_j {~\rightleftharpoons~} {\mathcal M}_m',

with :math:`{\mathcal M}_m' = \lambda_m{\mathcal M}_m`,
:math:`\nu_{jm}' = \lambda_m\nu_{jm}`. In addition, the mineral molar volume
:math:`\overline V_m`, formula weight :math:`W_m`, and equilibrium constant
:math:`K_m` are scaled according to

.. math::
   :label: dummy85
   
   \overline V_m' &= \lambda_m\overline V_m,\\
   W_m' &= \lambda_m W_m,\\
   \log K_m' &= \lambda_m \log K_m.

The saturation index :math:`{\rm SI}_m` transforms according to

.. math::
   :label: dummy86
   
   {\rm SI}_m' = K_m' Q_m' = \big(K_m Q_m\big)^{\lambda_m} = ({\rm SI}_m)^{\lambda_m}.

Consequently, equilibrium is not affected as is to be expected. However,
a more general form for the reaction rate is needed involving Temkin’s
constant [see Eqn. :eq:`Im`], in order to ensure that the
identical solution to the reactive transport equations is obtained using
the scaled reaction (Lichtner, 2016). Thus it is necessary that the following conditions
hold

.. math::
   :label: dummy87
   
   {\overline V}_m' I_m' &= \overline V_m I_m,\\
   \nu_{jm}' I_m' &= \nu_{jm} I_m.

This requires that the reaction rate :math:`I_m` transform as

.. math::
   :label: dummy88
   
   I_m' = \frac{1}{\lambda_m} I_m,

which guarantees that mineral volume fractions and solute concentrations
are identical to that obtained from solving the reactive transport equations
using the unscaled reaction.

From the above relations it is found that the reaction rate transforms
according to

.. math::
   :label: dummy90
   
   I_m' &= -\frac{k_m A_m}{\lambda_m} \big(1-(K_m'Q_m')^{1/\sigma_m'}\big),\\
   &= -\frac{k_m A_m}{\lambda_m} \big(1-(K_m Q_m)^{1/(\lambda_m \sigma_m)} \big),\\
   &= \frac{1}{\lambda_m} I_m,

where the last result is obtained by scaling Temkin’s constant according
to

.. math::
   :label: dummy91
   
   \sigma_m' = \lambda_m\sigma_m.

It should be noted that the mineral concentration
:math:`(C_m' =({\overline V}_m^{-1})^{'} \porosity_m = \lambda_m^{-1} C_m)`,
differs in the two formulations; however, mass density
:math:`(\density_m = W_m \overline V_m^{-1})` is an invariant, unlike molar
density :math:`(\eta_m=\overline V_m^{-1})`. The scaling factor :math:`\lambda_m`
can be found under MINERAL\_KINETICS with the option MINERAL\_SCALE\_FACTOR.

Eh, pe
^^^^^^

Output for Eh and pe is calculated from the half-cell reaction

.. math::
   :label: redox
   
   \rm 2 \, H_2O - 4 \, H^+ - 4\,e^- \rightleftharpoons \rm O_2,

with the corresponding equilibrium constant fit to the Maier-Kelly
expansion Eqn. :eq:`mk`. The fit coefficients are listed in
Table below.

+------------------+-------------------+
| coefficient      | value             |
+==================+===================+
| :math:`c_{-1}`   | 6.745529048       |
+------------------+-------------------+
| :math:`c_0`      | -48.295936593     |
+------------------+-------------------+
| :math:`c_1`      | -0.000557816      |
+------------------+-------------------+
| :math:`c_2`      | 27780.749538022   |
+------------------+-------------------+
| :math:`c_3`      | 4027.337694858    |
+------------------+-------------------+

Table: Fit coefficients for log :math:`K` of reaction :eq:`redox`.

Python Script to Select Primary and Secondary Species from Thermodynamic Database
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A python script is available to help the user extract secondary species,
gases and minerals from the thermodynamic database for a given set of
primary species. Surface complexation reactions are not included. The
python script can be found in ``./tools/contrib/sec_species/rxn.py`` in
the PFLOTRAN Git repository. The current implementation is based
on the ``hanford.dat`` database. Input files are ``aq_sec.dat``,
``gases.dat`` and ``minerals.dat``. In addition, for each of these files
there is a corresponding file containing a list of species to be
skipped: ``aq_skip.dat``, ``gas_skip.dat`` and ``min.dat``. Before
running the script it is advisable to copy the entire directory
``sec_species`` to the local hard drive to avoid conflicts when updating
the PFLOTRAN repository. To run the script simply type in a terminal
window:

``python rxn.py``

The user has to edit the ``rxn.py`` file to set the list of primary
species. For example,

``pri=[’Fe++’,’Fe+++’,’H+’,’H2O’]``

Note that the species H2O must be include in the list of primary
species. Output appears on the screen and also in the file ``chem.out``,
a listing of which appears below. The number of primary and secondary
species, gases and minerals is printed out at the end of the
``chem.out`` file.

``chem.out``

::

    PRIMARY_SPECIES
    Fe++
    Fe+++
    H+
    H2O
    /
    SECONDARY_SPECIES
    O2(aq)
    H2(aq)
    Fe(OH)2(aq)
    Fe(OH)2+
    Fe(OH)3(aq)
    Fe(OH)3-
    Fe(OH)4-
    Fe(OH)4--
    Fe2(OH)2++++
    Fe3(OH)4(5+)
    FeOH+
    FeOH++
    HO2-
    OH-
    /
    GASES
    H2(g)
    H2O(g)
    O2(g)
    /
    MINERALS
    Fe
    Fe(OH)2
    Fe(OH)3
    FeO
    Ferrihydrite
    Goethite
    Hematite
    Magnetite
    Wustite
    /
    ================================================
    npri =  4  nsec =  14  ngas =  3  nmin =  9

    Finished!


References
++++++++++

Delany, J.M. and S.R. Lundeen, 1990, The LLNL thermochemical database. Lawrence Livermore National Laboratory Report UCRL-21658, 150 p.
