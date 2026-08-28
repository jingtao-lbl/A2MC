Back to :ref:`card-index`

Back to :ref:`chemistry-card`

Back to :ref:`mineral-kinetics-card`

.. _nucleation-kinetics-card:

NUCLEATION_KINETICS
===================

Defines nucleation reaction type and associated parameters to be coupled
to mineral precipitation-dissolution reactions.

Required Cards:
---------------

NUCLEATION_KINETICS
 Opens the block.

[CLASSICAL,SIMPLIFIED] <string>
  Specifies type [CLASSICIAL,SIMPLIFIED] and name of nucleation reaction.

 CLASSICAL
  *Eq. 3 from Pham et al., 2011*

  :math:`\hspace{1cm}\text{rate} = k_N \exp\left(-\beta N_A f(\theta)\left(\frac{\nu \sigma^{3/2}}{\left(RT\right)^{3/2}\ln\Omega}\right)^2\right)\hspace{1cm}`

  where $\Omega$ is $K_m Q_m$ from :eq:`tst_rate_law`

  RATE_CONSTANT <float>
   Rate constant $k_N$ [mol/sec]

  GEOMETRIC_SHAPE_FACTOR <float>
   Geometric shape factor $\beta$ [-]

  HETEROGENEOUS_CORRECTION_FACTOR <float>
   Correction factor for heterogeneous nucleation $f\left(\theta\right)$ [-]

  SURFACE_TENSION <float>
   Surface tension $\sigma$ [N/m]

 SIMPLIFIED
  *from Eq. 4 from Pham et al., 2011*

  :math:`\hspace{1cm}\text{rate} = k_N \exp\left(-\Gamma \left(\frac{1}{\left(T\right)^{3/2}\ln\Omega}\right)^2\right)\hspace{1cm}` 

  where $\Omega$ is $K_m Q_m$ from :eq:`tst_rate_law`

  RATE_CONSTANT <float>
   Rate constant $k_N$ [mol/sec]

  GAMMA <float>
   Lumped $\Gamma$ parameter [-]

Examples
--------

 ::

  CHEMISTRY
    ...
    MINERAL_KINETICS
      Quartz
        RATE_CONSTANT 2.d-11 mol/m^2-sec
        NUCLEATION_KINETICS classical_eq
        SURFACE_AREA_FUNCTION MINERAL_MASS
        SPECIFIC_SURFACE_AREA 0.041 m^2/g
      /
    /
    NUCLEATION_KINETICS
      SIMPLIFIED simplified_eq
        RATE_CONSTANT 1.d-5
        GAMMA 1.d10
      /
    /
    NUCLEATION_KINETICS
      CLASSICAL classical_eq
        RATE_CONSTANT 1.d-5
        GEOMETRIC_SHAPE_FACTOR 0.65
        HETEROGENEOUS_CORRECTION_FACTOR 0.15
        SURFACE_TENSION 0.685
      /
    /
  END

.. _Back to Quick Guide: ../QuickGuide
.. _Back to CHEMISTRY: ../Chemistry
