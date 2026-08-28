.. _mode-mphase:

MPHASE Mode
-----------

Governing Equations
~~~~~~~~~~~~~~~~~~~

The mode ``MPHASE`` solves the two-phase system of water and
supercritical :math:`\mathrm{CO_2}`. It may also be coupled to chemistry
using the ``CHEMISTRY`` keyword and its various associated optional and
required keywords for selecting the primary and secondary aqueous
species and setting up initial and boundary conditions and source/sinks.
``MPHASE`` requires that the species CO2(aq) be used as primary species.
In addition, for pure aqueous and supercritical :math:`\mathrm{CO_2}`
phases, the input to ``MPHASE`` requires specifying the mole fraction of
:math:`\mathrm{CO_2}`. When coupled to chemistry, the
:math:`\mathrm{CO_2}` mole fraction is calculated internally directly
from the aqueous concentrations specified in the ``CONSTRAINT`` keyword.

Local equilibrium is assumed between phases for modeling multiphase
systems with PFLOTRAN. The multiphase partial differential equations for
mass and energy conservation solved by PFLOTRAN have the general form:

.. math::
   :label: mass_conservation_equation
   
   \frac{\partial}{\partial t} \bigg(\porosity \sum_{\alpha}s_{\alpha}^{}\eta_{\alpha}^{} x_i^{\alpha}\bigg)
   + {\boldsymbol{\nabla}}\cdot\sum_{\alpha} {\boldsymbol{F}}_i^{\alpha}= Q_{i},

for the :math:`i`\ th component where the flux
:math:`{\boldsymbol{F}}_i^{\alpha}` is given by

.. math::
   :label: flux-mphase

   {\boldsymbol{F}}_i^{{\alpha}}= {\boldsymbol{q}}_{{\alpha}}^{}\eta_{{\alpha}}^{} x_i^{{\alpha}} - \porosity \saturation_{{\alpha}}^{} D_{{\alpha}}^{} \eta_{{\alpha}}^{} {\boldsymbol{\nabla}}x_i^{{\alpha}},

and

.. math::
   :label: energy_equation
   
   \frac{{{\partial}}}{{{\partial}}t} \bigg(\porosity \sum_{{\alpha}}s_{{\alpha}}\eta_{{\alpha}}U_{{\alpha}}+ (1-\porosity) \density_r c_r T\bigg)
   + {\boldsymbol{\nabla}}\cdot\bigg[\sum_{{\alpha}}{\boldsymbol{q}}_{{\alpha}}\eta_{{\alpha}}H_{{\alpha}}- \kappa{\boldsymbol{\nabla}}T\bigg] = Q_{e},

for energy. In these equations :math:`{{\alpha}}` designates a fluid
phase (:math:`{{\alpha}}=l`, sc) at temperature :math:`T` and pressure
:math:`P_{{\alpha}}` with the sums over all fluid phases present in the
system, and source/sink terms :math:`Q_i` and :math:`Q_e` described in
more detail below. Species are designated by the subscript :math:`i`
(:math:`i=\mathrm{H_2O}`, :math:`\mathrm{CO_2}`); :math:`\porosity`
denotes the porosity of the porous medium; :math:`s_{\alpha}` denotes
the phase saturation state; :math:`x_i^{\alpha}` denotes the mole
fraction of species :math:`i` satisfying

.. math::
   :label: sum_i

   \sum_i x_i^\alpha=1,

which implies

.. math::
   :label: sumxi

   \sum_i {\boldsymbol{F}}_i^\alpha = {\boldsymbol{q}}_\alpha \eta_\alpha.

The quantities :math:`\eta_{{\alpha}}`, :math:`H_{{\alpha}}`,
:math:`U_{{\alpha}}` refer to the molar density, enthalpy, and internal
energy of each fluid phase, respectively; and
:math:`{\boldsymbol{q}}_{{\alpha}}` denotes the Darcy flow rate for
phase :math:`{{\alpha}}` defined by

.. math::
   :label: darcy-mphase

   {\boldsymbol{q}}_{{\alpha}}= -\frac{kk_{{\alpha}}}{\mu_{{\alpha}}} {\boldsymbol{\nabla}}\big(P_{{\alpha}}-\density_{{\alpha}}g {\boldsymbol{z}}\big),

where :math:`k` refers to the intrinsic permeability,
:math:`k_{{\alpha}}` denotes the relative permeability,
:math:`\mu_{{\alpha}}` denotes the fluid viscosity,
:math:`W_{{\alpha}}^{}` denotes the formula weight, :math:`g` denotes
the acceleration of gravity, and :math:`z` designates the vertical of
the position vector. The mass density :math:`\density_{{\alpha}}` is related
to the molar density by the expression

.. math::
   :label: mass-density-mphase

   \density_{{\alpha}}= W_{{\alpha}}\eta_{{\alpha}},

where the formula weight :math:`W_{{\alpha}}` is a function of
composition according to the relation

.. math::
   :label: formula-weight-mphase

   W_{{\alpha}}= \frac{\density_{{\alpha}}}{\eta_{{\alpha}}} = \sum_i W_i^{} x_i^{{\alpha}}.

The quantities :math:`\density_r`, :math:`c_r`, and :math:`\kappa` refer to
the mass density, heat capacity, and thermal conductivity of the porous
rock.

Source/Sink Terms
~~~~~~~~~~~~~~~~~

The source/sink terms, :math:`Q_i` and :math:`Q_e`, describe injection
and extraction of mass and heat, respectively, for various well models.
Several different well models are available. The simplest is a volume or
mass rate injection/production well given by

.. math::
   :label: source-sink-mphase

   Q_i &= \sum_n\sum_{{\alpha}}q_{{\alpha}}^V \eta_{{\alpha}}x_i^{{\alpha}}\delta({\boldsymbol{r}}-{\boldsymbol{r}}_{n}),\\
       &= \sum_n\sum_{{\alpha}}\frac{\eta_{{\alpha}}}{\density_{{\alpha}}} q_{{\alpha}}^M x_i^{{\alpha}}\delta({\boldsymbol{r}}-{\boldsymbol{r}}_{n}),\\
       &= \sum_n\sum_{{\alpha}}W_{{\alpha}}^{-1} q_{{\alpha}}^M x_i^{{\alpha}}\delta({\boldsymbol{r}}-{\boldsymbol{r}}_{n}),

where :math:`q_{{\alpha}}^V`, :math:`q_{{\alpha}}^M` refer to volume and
mass rates with units m\ :math:`^3`/s, kg/s, respectively, related by
the density

.. math::
   :label: vol-mass-rates-mphase
   
   q_{{\alpha}}^M = \density_{{\alpha}}q_{{\alpha}}^V.

The position vector :math:`{\boldsymbol{r}}_{n}` refers to the location
of the :math:`n`\ th source/sink.

A less simplistic approach is to specify the bottom well pressure to
regulate the flow rate in the well. In this approach the mass flow rate
is determined from the expression

.. math::
   :label: mass-flow-mphase
   
   q_{{\alpha}}^M = \Gamma \density_{{\alpha}}\frac{k_{{\alpha}}}{\mu_{{\alpha}}} \big(p_{{\alpha}}-p_{{\alpha}}^{\rm bw}\big),

with bottom well pressure :math:`p_{{\alpha}}^{\rm bw}`, and where
:math:`\Gamma` denotes the well factor (production index) given by

.. math::
   :label: well-factor-mphase
   
   \Gamma = \frac{2\pi k \Delta z}{\ln\big(r_e/r_w\big) +  \sigma -1/2}.

In this expression :math:`k` denotes the permeability of the porous
medium, :math:`\Delta z` refers to the layer thickness, :math:`r_e`
denotes the grid block radius, :math:`r_w` denotes the well radius, and
:math:`\sigma` refers to the skin thickness factor. For a rectangular
grid block of area :math:`A=\Delta x \Delta y`, :math:`r_e` can be
obtained from the relation

.. math::
   :label: re-mphase

   r_e = \sqrt{A/\pi}.

See Peaceman (1977) and Coats and Ramesh (1982) for more details.

Variable Switching
~~~~~~~~~~~~~~~~~~

In PFLOTRAN a variable switching approach is used to account for phase
changes enforcing local equilibrium. According to the Gibbs phase rule
there are a total of :math:`N_C+1` degrees of freedom where :math:`N_C`
denotes the number of independent components. This can be seen by noting
that the intensive degrees of freedom are equal to
:math:`N_{\rm int}=N_C - N_P +2`, where :math:`N_P` denotes the number
of phases. The extensive degrees of freedom equals
:math:`N_{\rm ext}=N_P-1.` This gives a total number of degrees of
freedom :math:`N_{\rm dof}=N_{\rm int}+N_{\rm ext}=N_C+1`, independent
of the number of phases :math:`N_P` in the system. Primary variables for
liquid, gas and two-phase systems are listed in Table [tvar]. The
conditions for phase changes to occur are considered in detail below.

+-------------+---------------+---------------+----------------------------+
| State       | :math:`X_1`   | :math:`X_2`   | :math:`X_3`                |
+=============+===============+===============+============================+
| Liquid      | :math:`p_l`   | :math:`T`     | :math:`x_{{\rm CO_2}}^l`   |
+-------------+---------------+---------------+----------------------------+
| Gas         | :math:`p_g`   | :math:`T`     | :math:`x_{{\rm CO_2}}^g`   |
+-------------+---------------+---------------+----------------------------+
| Two-Phase   | :math:`p_g`   | :math:`T`     | :math:`s_g`                |
+-------------+---------------+---------------+----------------------------+

Table: Choice of primary variables.

Gas: :math:`(p_g,\,T,\,x_{{\rm CO_2}}^g)` :math:`\rightarrow` Two-Phase: :math:`(p_g,\,T,\,s_g^{})`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

 

:math:`\bullet` gas :math:`\rightarrow` 2-ph:
:math:`x_{{\rm CO_2}}^g \leq 1-\dfrac{P_{\rm sat}(T)}{p_g}`,  or
equivalently: :math:`x_{{\rm H_2O}}^g \geq \dfrac{P_{\rm sat}(T)}{p_g}`

Liquid: :math:`(p_l,\,T,\,x_{{\rm CO_2}}^l)` :math:`\rightarrow` Two-phase: :math:`(p_g,\,T,\,s_g^{})`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

 

:math:`\bullet` liq :math:`\rightarrow` 2-ph:
:math:`x_{{\rm CO_2}}^l \geq x_{{\rm CO_2}}^{eq}`

The equilibrium mole fraction :math:`x_{{\rm CO_2}}^{eq}` is given by

.. math::
   :label: eq-mole-frac-mphase
   
   x_{{\rm CO_2}}^{eq} = \frac{m_{{\rm CO_2}}}{W_{{\rm H_2O}}^{-1} + m_{{\rm CO_2}}+  \sum_{l\ne {{\rm H_2O}},\,{{\rm CO_2}}} m_l},

where the molality at equilibrium is given by

.. math::
   :label: eq-molality-mphase
   
   m_{{\rm CO_2}}^{eq} = \left(1-\dfrac{P_{\rm sat}(T)}{p}\right)\frac{\porosity_{{\rm CO_2}}p}{K_{{\rm CO_2}}\gamma_{{\rm CO_2}}},

where it is assumed that

.. math::
   :label: y-mphase
   
   y_{{\rm CO_2}}^{} = 1-\dfrac{P_{\rm sat}(T)}{p}.

Two-Phase: :math:`(p_g,\,T,\,s_g)` :math:`\rightarrow` Liquid :math:`(p_l,\,T,\,x_{{\rm CO_2}}^l)` or Gas :math:`(p_g,\,T,\,x_{{\rm CO_2}}^g)`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Equilibrium in a two-phase :math:`{\rm H_2O}`–:math:`{\rm CO_2}`
system is defined as the equality of chemical potentials between the two
phases as expressed by the relation

.. math::
   :label: chem-pot-mphase
   
   f_{{\rm CO_2}}^{} = y_{{\rm CO_2}}^{}\porosity_{{\rm CO_2}}^{} p_g^{} = K_{{\rm CO_2}}^{} \big(\gamma_{{\rm CO_2}}^{} m_{{\rm CO_2}}^{}\big),

where

.. math::
   :label: y2-mphase
   
   y_{{\rm CO_2}}^{} = x_{{\rm CO_2}}^g,

.. math::
   :label: x-mphase
   
   x_{{\rm H_2O}}^g = \frac{P_{\rm sat}(T)}{p_g},

and

.. math::
   :label: y3-mphase
   
   y_{{\rm CO_2}}^{} = 1-x_{{\rm H_2O}}^g = 1-\frac{P_{\rm sat}(T)}{p_g}.

From these equations a Henry coefficient-like relation can be written as

.. math::
   :label: y4-mphase
   
   y_{{\rm CO_2}}^{} = \widetilde K_{{\rm CO_2}}^{} x_{{\rm CO_2}}^{},

where

.. math::
   :label: x2-mphase
   
   x_{{\rm CO_2}}^{} = x_{{\rm CO_2}}^l,

.. math::
   :label: K-mphase
   
   \widetilde K_{{\rm CO_2}}^{} = \frac{\gamma_{{\rm CO_2}}^{} K_{{\rm CO_2}}^{}}{\porosity_{{\rm CO_2}}^{} p_g}\frac{m_{{\rm CO_2}}}{x_{{\rm CO_2}}}.

:math:`\bullet` A phase change to single liquid or gas phase occurs if
:math:`s_g \leq 0` or :math:`s_g\geq 1`, respectively.

Conversion relations between mole fraction :math:`(x_i)`, mass fraction
:math:`(w_i)` and molality :math:`(m_i)` are as follows:

Molality–mole fraction:

.. math::
   :label: molal-mol-mphase
   
   m_i = \frac{n_i}{M_{{\rm H_2O}}} = \frac{n_i}{W_{{\rm H_2O}}n_{{\rm H_2O}}} = \frac{x_i}{W_{{\rm H_2O}}x_{{\rm H_2O}}} = \frac{x_i}{W_{{\rm H_2O}}\big(1-\sum_{l\ne{{\rm H_2O}}} x_l\big)}

Mole fraction–molality:

.. math::
   :label: mol-molal-mphase
   
   x_i = \frac{n_i}{N} = \frac{n_i}{M_{{\rm H_2O}}}\frac{M_{{\rm H_2O}}}{N} = \frac{m_i}{\sum m_l} = \frac{W_{{\rm H_2O}}m_i}{1+W_{{\rm H_2O}}\sum_{l\ne{{\rm H_2O}}} m_l}

Mole fraction–mass fraction:

.. math::
   :label: mol-mass-mphase
   
   x_i = \frac{n_i}{N} = \frac{W_i^{-1} W_i n_i}{\sum W_l^{-1} W_l n_l} = \frac{W_i^{-1} w_i}{\sum W_l^{-1} w_l}

Mass fraction–mole fraction:

.. math::
   :label: mass-mol-mphase
   
   w_i = \frac{M_i}{M} = \frac{W_i n_i}{\sum W_l n_l} = \frac{W_i x_i}{\sum W_l x_l}

Sequentially Coupling MPHASE with CHEMISTRY
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MPHASE and CHEMISTRY may be sequentially coupled to one another by
including the CHEMISTRY keyword in the MPHASE input file and adding the
requisite associated keywords. At the end of an MPHASE time step the
quantities :math:`p`, :math:`T`, :math:`s_g`, :math:`q_l` and
:math:`q_g` are passed to the reactive transport equations. These
quantities are interpolated between the current time :math:`t_{\rm MPH}`
and the new time :math:`t_{\rm MPH}+\Delta t_{\rm MPH}`. The reactive
transport equations may need to sub-step the MPHASE time step, i.e.
:math:`\Delta t_{\rm RT} \leq \Delta t_{\rm MPH}`. Coupling also occurs
from the reactive transport equations back to MPHASE. This is through
changes in material properties such as porosity, tortuosity and
permeability caused by mineral precipitation and dissolution reactions
(see §[sec\_mat\_prop]). In addition, coupling occurs through
consumption and production of :math:`\mathrm{H_2O}` and
:math:`\mathrm{CO_2}` by mineral precipitation/dissolution reactions
occurring in the reactive transport equations. This effect is accounted
for by passing the reaction rates :math:`R_{\mathrm{H_2O}}` and
:math:`R_{\mathrm{CO_2}}` given by

.. math::
   :label: Rj-mphase
   
   R_j = -\sum_m\nu_{jm}I_m,
   
back to the MPHASE conservation equations.

A further constraint on the reactive transport equations for aqueous
:math:`\mathrm{CO_2}` is that it must be in equilibrium with
supercritical :math:`\mathrm{CO_2}` in regions where :math:`0< \saturation_g <1`.
This is accomplished by replacing the :math:`\mathrm{CO_2}` mass
conservation equations in those regions with the constraint
:math:`m_{\rm CO_{\rm 2(aq)}} = m_{\rm CO_2}^{\rm eq}`.
