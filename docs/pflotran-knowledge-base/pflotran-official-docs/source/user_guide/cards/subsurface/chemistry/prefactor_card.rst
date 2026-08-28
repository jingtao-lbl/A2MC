Back to :ref:`card-index`

Back to :ref:`chemistry-card`

Back to :ref:`mineral-kinetics-card`

.. _prefactor-card:

PREFACTOR
=========
Specifies coefficients for defining prefactors in mineral 
precipitation-dissolution reactions.

.. math::
   {{{\mathcal P}}}_{ml} = \prod_i\dfrac{\big(\gamma_i m_i\big)^{{{\alpha}}_{il}^m}}{1+K_{il}^m\big(\gamma_i m_i\big)^{{{\beta}}_{il}^m} }

Required Cards:
---------------

PREFACTOR_SPECIES <string>
 Name of prefactor species. Appears as subscripts *j* and *i* in above equation corresponding to primary and secondary species.

RATE_CONSTANT <float> <optional units_string>
 Kinetic rate constant associated with prefactor species
 (see :ref:`mineral-kinetics-card`).
 (default units [mol/m\ :sup:`2`\/sec])

Optional Cards:
---------------

ACTIVATION_ENERGY <float>
 Activation energy associated with rate constant :math:`k_{ml}`. [J/mol]

ALPHA <float>
 :math:`\alpha_{il}^m` parameter in above equation.

BETA <float>
 :math:`\beta_{il}^m` parameter in above equation.

ATTENUATION_COEF <float>
 :math:`K_{il}^m` \ in above equation.

Examples (data from Palandri and Kharaka (2004))
------------------------------------------------

 ::
 
  CHEMISTRY
    ...
    MINERAL_KINETICS
      K-Feldspar
        PREFACTOR
          RATE_CONSTANT -12.41d0 mol/m^2-sec
          ACTIVATION_ENERGY 38.d0 kJ/mol
        /
        PREFACTOR
          RATE_CONSTANT -10.06d0 mol/m^2-sec
          ACTIVATION_ENERGY 51.7d0 kJ/mol
          PREFACTOR_SPECIES H+
            ALPHA 0.5d0
          /
        /
        PREFACTOR
          RATE_CONSTANT -21.20 mol/m^2-sec
          ACTIVATION_ENERGY 94.1d0 kJ/mol
          PREFACTOR_SPECIES H+
            ALPHA -0.823d0
          /
        /
      /
    /
    ...
  END
