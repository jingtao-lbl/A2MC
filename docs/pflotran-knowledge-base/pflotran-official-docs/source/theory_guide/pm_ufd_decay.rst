.. _pm_ufd_decay:

UFD Decay
=========

The Used Fuel Disposition Decay Process Model performs radionuclide isotope 
decay, ingrowth, and phase partitioning, for the simulation of a nuclear
waste repository. It has been developed under the Generic Disposal Systems 
Analysis (GDSA) work package, which is under the Spent Fuel and Waste 
Disposition Program of the U.S. Department of Energy (DOE) Office of Nuclear 
Energy, as part of the Spent Fuel and Waste Science and Technology (SFWST) 
Campaign. Development of the UFD Decay Process Model is ongoing, and lead by 
Paul Mariner, Glenn Hammond, and Jennifer Frederick, at Sandia National 
Laboratories.

General Algorithmic Design
--------------------------

The UFD Decay process model is called each time step of the simulation. Before
the simulation begins, the process model initializes the sorbed amount of each 
isotope in equilibrium with the user-specified aqueous concentration and the
material-specific, elemental Kd value, according to,

.. math::

   C^{sorb}_i = C^{aq}_i Kd_e 

where :math:`C^{aq}_i` is the user-specified aqueous isotope concentration 
with units of [mol/kg-water], :math:`Kd_e` is the material-specific, elemental 
Kd value with units of [kg-water/m3-bulk], and :math:`C^{sorb}_i` is the sorbed 
concentration of isotope :math:`i` with units of [mol/m3-bulk].

At each time step, the total mass of each isotope [mol] is summed up 
according to,

.. math::

   M^{total}_i = M^{aq}_i + M^{sorb}_i + M^{ppt}_i

where :math:`M^{aq}_i` is the mass of isotope :math:`i` in the aqueous phase,
:math:`M^{sorb}_i` is the mass of isotope :math:`i` in the sorbed phase, and
:math:`M^{ppt}_i` is the mass of isotope :math:`i` in the precipitated phase.
The total mass, :math:`M^{total}_i`, is then allowed to decay according to
the Bateman Equations. These equations are solved according to a 3-generation
analytical solution derived for multiple parents and grandparents with 
non-zero initial daughter concentrations and solved explicitly in time, or a
fully implicit solution for any number of generations can be used instead by 
including the keyword ``IMPLICIT_SOLUTION`` within the ``UFD_DECAY`` block.

Once the isotopes have gone through the decay and ingrowth calculation, the
total mass of each isotope is partitioned back into aqueous, sorbed, and 
precipitated phases. First, mole fractions are calculated to determine the
fraction that each isotope contributes to total element mass,

.. math::

   X_i = \frac {M^{total}_i} {M^{total}_e}

where :math:`X_i` is the mass fraction for isotope :math:`i`, 
:math:`M^{total}_i` is the total mass [mol] for each isotope :math:`i`, and
:math:`M^{total}_e` is the total mass [mol] of the corresponding element
:math:`e`. 

Based on the total element mass and elemetal Kd value, the element aqueous 
concentration is calculated according to,

.. math::

   C^{aq}_e = \frac {M^{total}_e} {1000 \left({1+Kd_e/(\density \porosity S_{l})}\right) V \porosity S_{l} }

where :math:`C^{aq}_e` is the aqueous concentration [mol/L] of each element
:math:`e`, :math:`M^{total}_e` is the total mass [mol] of the element
:math:`e`, :math:`\density` is the water density [kg/m3], :math:`\porosity` is the
material porosity, :math:`S_l` is the pore water saturation, :math:`V` is the
grid cell volume, and :math:`Kd_e` is the material-specific, elemental
Kd value with units of [kg-water/m3-bulk]. If the aqueous concentration of the
element exceeds the elemental solubility limit, then the aqueous elemental
concentration is set equal to the elemental solubility limit. The 
remaining element mass is then partitioned between sorbed and precipitated 
phases, according to

.. math::

   C^{sorb}_e = C^{aq}_e Kd_e

where :math:`C^{aq}_e` is the aqueous elemental concentration with units of 
[mol/kg-water], :math:`Kd_e` is the material-specific, elemental
Kd value with units of [kg-water/m3-bulk], and :math:`C^{sorb}_e` is the sorbed
concentration of element :math:`e` with units of [mol/m3-bulk]. If the
aqueous element concentration was set to the solubility limit, then the
precipitated phase is calculated according to

.. math::

   M^{ppt}_e =& M^{total}_e - M^{aq}_e - M^{sorb}_e

   C^{ppt}_e =& \frac {M^{ppt}_e V^{mnrl}_e} {V} 

where :math:`M^{ppt}_e` is the precipitated mass [mol] of element :math:`e`,
:math:`M^{total}_e` is the total mass [mol] of the element :math:`e`,
:math:`M^{aq}_e` is the aqueous mass [mol] of element :math:`e`, 
:math:`M^{sorb}_e` is the total sorbed mass [mol] of element :math:`e`, 
:math:`V^{mnrl}_e` is the molar volume [m3/mol] of the precipitated element, and
:math:`V` is the grid cell volume [m3].

The isotope concentrations are calculated from the partitioned elemental
concentrations by multiplying by the isotope mole fractions,

.. math::

   C_i = X_i C_e


3-Generation Explicit Solve
---------------------------
The default routine for solving the decay and ingrowth equations is a 
3-generation analytical solution derived for multiple parents and
grandparents with non-zero initial daughter concentrations. This approach is
documented in Section 3.2.3 of Mariner et al. (2016), SAND2016-9610R.

Mariner, P.E., E.R. Stein, J.M. Frederick, S.D. Sevougian, G.E. Hammond, 
and D.G. Fascitelli (2016), Advances in Geologic Disposal System Modeling and
Application to Crystalline Rock, FCRD-UFD-2016-000440, SAND2016-9610R, 
Sandia National Laboratories, Albuquerque, NM.

Implicit Solve
--------------
The user can specify the keyword ``IMPLICIT_SOLUTION`` to solve for decay and
ingrowth using an implicit, direct solve of the Bateman equations for any
number of generations. The governing equation for isotope decay and ingrowth is,

.. math::

   \frac {d C_i(t)} {d t} = -\lambda_i C_i(t) + \lambda_p S C_p(t) 

which describes the change in isotope concentration over time
(:math:`\frac {d C_i(t)} {d t}`) due to its own decay (if any)
(:math:`-\lambda_i C_i(t)`) plus ingrowth (if any) from the isotope's
parents (:math:`\lambda_p S C_p(t)`), where :math:`\lambda` is the decay 
rate constant [1/sec] and :math:`S` is a stoichiometry coefficient. 
The equation is discretized and rewritten in terms 
of a residual equation as follows,

.. math::

   f\left({c^{k+1,p}}\right) = \frac {c^{k+1,p} - c^{k}} {\Delta t} - R\left({c^{k+1,p}}\right) 

where :math:`f\left({c^{k+1,p}}\right)` is the residual, :math:`c^{k+1,p}` is
the solution for concentration at the :math:`k+1` time step and the 
:math:`p^{th}` iterate, :math:`\frac {c^{k+1,p} - c^{k}} {\Delta t}` is the
discretized accumulation term (e.g., the left hand side of the governing 
equation above), and :math:`R\left({c^{k+1,p}}\right)` is the
source or sink term (e.g., the right hand side of the governing equation above).

A Jacobian matrix is formed according to,

.. math::

   J_{ij} = \frac {\partial f_i(c^{k+1,p})} {\partial c_j^{k+1,p}}

which is a matrix of all the partial derivatives of the solution with respect 
to each unknown variable. Using Newton's method, which solves the following
system,

.. math::

   J \delta c^p = -f(c^{k+1,p})

the concentration can be updated according to,

.. math::

   c^{k+1,p+1} = c^{k+1,p} + \delta c^p

Note: The governing equation is reformuated in terms of isotopes and the 
isotopes' daughter(s) in the source code, rather than the isotopes and 
isotopes' parent(s) formulation shown here. 



