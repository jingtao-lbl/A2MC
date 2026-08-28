
.. _constitutive_relations:

Constitutive Relations
----------------------

Capillary Pressure - Saturation Functions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. _VG-saturation-function-richards:

van Genuchten Saturation Function
+++++++++++++++++++++++++++++++++

Capillary pressure is related to saturation by various phenomenological
relations, one of which is the van Genuchten (1980) relation

.. math::
   :label: seff
   
   \saturation_e = \left[1+\left( \frac{p_c}{p_c^0} \right)^n\right]^{-m},

where :math:`p_c` represents the capillary pressure [Pa], and the
effective saturation :math:`s_e` is defined by

.. math::
   :label: seff_2

   \saturation_e = \frac{s - \saturation_r}{s_0 - \saturation_r},

where :math:`s_r` denotes the residual saturation, and :math:`s_0`
denotes the maximum saturation. The inverse relation is given by

.. math::
   :label: pc-vg

   p_c = p_c^0 \left(s_e^{-1/m}-1\right)^{1/n}.

The quantities :math:`m`, :math:`n` and :math:`p_c^0` are impirical
constants determined by fitting to experimental data.

.. _BC-saturation-function-richards:

Brooks-Corey Saturation Function
++++++++++++++++++++++++++++++++

The Brooks-Corey saturation function is a limiting form of the van
Genuchten relation for :math:`p_c/p_c^0 \gg 1`, with the form

.. math::
   :label: bc-se

   \saturation_e = \left(\frac{p_c}{p_c^0}\right)^{-\lambda},

with :math:`\lambda=mn` and inverse relation

.. math::
   :label: bc-pc

   p_c = p_c^0 \saturation_e^{-1/\lambda}.

   
.. _relative-permeability-functions-richards:
   
Relative Permeability Functions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Two forms of the relative permeability function are implemented based on
the Mualem and Burdine formulations. The quantity :math:`n` is related
to :math:`m` by the expression

.. math::
   :label: lambda_mualem
   
   m = 1-\frac{1}{n}, \ \ \ \ \ n = \frac{1}{1-m},

for the Mualem formulation and by

.. math::
   :label: lambda_burdine
   
   m = 1-\frac{2}{n}, \ \ \ \ \ n = \frac{2}{1-m},

for the Burdine formulation.

Mualem Relative Permeability
++++++++++++++++++++++++++++

For the Mualem relative permeability function based on the van Genuchten
saturation function is given by the expression

.. math::
   :label: krl_mualem_vg
   
   k_{r} = \sqrt{s_e} \left\{1 - \left[1- \left( \saturation_e \right)^{1/m} \right]^m \right\}^2.

The Mualem relative permeability function based on the Brooks-Corey
saturation function is defined by

.. math::
   :label: krl_mualem_bc

   k_r &= \big(s_e\big)^{5/2+2/\lambda} \\
       &=\big(p_c/p_c^0\big)^{-(5\lambda/2+2)}.
       
Burdine Relative Permeability
+++++++++++++++++++++++++++++

For the Burdine relative permeability function based on the van
Genuchten saturation function is given by the expression

.. math::
   :label: krl_burdine_vg
   
   k_{r} = \saturation_e^2 \left\{1 - \left[1- \left( \saturation_e \right)^{1/m} \right]^m \right\}.

The Burdine relative permeability function based on the Brooks-Corey
saturation function has the form

.. math::
   :label: krl_burdine_bc

   k_r &= \big(s_e\big)^{3+2/\lambda} \\
       &= \left(\frac{p_c}{p_c^0}\right)^{-(3+2\lambda)}.

Modified Brooks Corey Relative Permeability
+++++++++++++++++++++++++++++++++++++++++++

The modified Brooks Corey relative permeability function can be associated
with any saturation function. 
The liquid relative permeability is defined as

.. math::
   :label: krl_modified_brooks_corey
   
   \saturation_{el} &= \left(\frac{s_l-s_{rl}}{1-s_{rl}-s_{rg}}\right) \\
   k_{rl} &= k_{rl,\text{max}} \saturation_{el}^{n_l}

The gas phase relative permeability is defined as 

.. math::
   :label: krg_modified_brooks_corey

   \saturation_{eg} &= \left(\frac{1-s_l-s_{rg}}{1-s_{rl}-s_{rg}}\right) \\
   k_{rg} &= k_{rg,\text{max}} \saturation_{eg}^{n_g}

where :math:`k_{r\alpha,\text{max}}`, :math:`n_\alpha` and :math:`s_{e\alpha}` are the maximum relative permeability, modified Brooks Corey exponent and effective saturation for phase :math:`\alpha`.

.. _smoothing-operation:       
       
Smoothing
~~~~~~~~~

At the end points of the saturation and relative permeability functions
it is sometimes necessary to smooth the functions in order for the
Newton-Raphson equations to converge. This is accomplished using a third
order polynomial interpolation by matching the values of the function to
be fit (capillary pressure or relative permeability), and imposing zero
slope at the fully saturated end point and matching the derivative at a
chosen variably saturated point that is close to fully saturated. The
resulting equations for coefficients :math:`a_i`, :math:`i=0-3`, are
given by

.. math::
   :label: smoothing1

   a_0 + a_1 x_1 + a_2 x_1^2 + a_3 x_1^3 &= f_1,\\
   a_0 + a_1 x_2 + a_2 x_2^2 + a_3 x_2^3 &= f_2,\\
         a_1 x_1 + 2a_2 x_1 + 3a_3 x_1^2 &= f_1',\\
         a_1 x_2 + 2a_2 x_2 + 3a_3 x_2^2 &= f_2',

for chosen points :math:`x_1` and :math:`x_2`. In matrix form these
equations become

.. math::
   :label: smoothing2

   \begin{bmatrix}
   1 & x_1 & x_1^2 & x_1^3\\
   1 & x_2 & x_2^2 & x_2^3\\
   0 & 1 & 2x_1 & 3x_1^2\\
   0 & 1 & 2x_2 & 3x_2^2
   \end{bmatrix}
   \begin{bmatrix}
   a_0\\
   a_1\\
   a_2\\
   a_3
   \end{bmatrix}
   = \begin{bmatrix}
   f_1\\
   f_2\\
   f_1'\\
   f_2'
   \end{bmatrix}.

The conditions imposed on the smoothing equations for capillary pressure
:math:`f=s_e(p_c)` are :math:`x_1=2 p_c^0`, :math:`x_2=p_c^0/2`,
:math:`f_1 = (s_e)_1`, :math:`f_2 = 1`, :math:`f_1' = (s_e')_1`,
:math:`f_2' = 0`. For relative permeability :math:`f=k_r(s_e)`,
:math:`x_1 = 1`, :math:`x_2 = 0.99`, :math:`f_1 = 1`,
:math:`f_2 = (k_r)_2`, :math:`f_1' = 0`, :math:`f_2' = (k_r')_2`.
