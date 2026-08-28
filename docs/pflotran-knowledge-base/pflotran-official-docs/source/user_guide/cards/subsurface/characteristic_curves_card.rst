Back to :ref:`card-index`

.. _characteristic-curves-card:

CHARACTERISTIC_CURVES
=====================
Specifies the characteristic curves (i.e., relative permeability and saturation functions and associated parameters) to be associated with a material property. 
**This card is currently only supported for the GENERAL, HYDRATE, RICHARDS, TH (non-ice) and WIPP_FLOW flow modes. The** :ref:`saturation-function-card` **card should be used in all other flow modes.**

Blocks and Cards:
**************************
SATURATION_FUNCTION <string>
  Opens a saturation function block where <string> indicates the type of saturation function to be employed. Common saturation functions include :ref:`BROOKS_COREY<cc-brooks-corey-card>` and :ref:`VAN_GENUCHTEN<cc-van-genuchten-card>`, but many others are also available.  The available saturation functions are documented in the Theory Guide under 
  :ref:`pc-sat-functions-general`.  

  Supported SATURATION_FUNCTIONs and their associated cards:

  .. _cc-brooks-corey-card:

  * BROOKS_COREY (:ref:`see QA plot <bc-sat-pc>`)

    + ALPHA
    + LAMBDA
    + SMOOTH

  * LINEAR (:ref:`see QA plot <lin-sat-pc>`)

    + ALPHA

  * MODIFIED_KOSUGI (:ref:`see QA plot <mk_sat>`)
    + NPARAM
    + SIGMAZ
    + MUZ
    + RMAX
    + R0

  * PCHIP
    + FILE <string>
    + LIST

  .. _cc-van-genuchten-card:

  * VAN_GENUCHTEN (:ref:`see QA plot <vg-sat-pc>`)
    + ALPHA
    + M

  WIPP-specific SATURATION_FUNCTIONs and associated cards:

  * BRAGFLO_KRP1 (:ref:`see QA plot <krp1-sat-pc>`) 
    Note: If not running in the ``TWOPHASE_MODE``, ``PCT_A`` and ``PCT_EXP`` 
    should be replaced with ``IGNORE_PERMEABILITY`` and ``ALPHA``, where 
    :math:`1/\alpha = P_t = ak^v` where ``ALPHA``:math:`=\alpha`, 
    ``PCT_A``:math:`=a`, and ``PCT_EXP``:math:`=v`.

    + LIQUID_RESIDUAL_SATURATION
    + GAS_RESIDUAL_SATURATION
    + PCT_A 
    + PCT_EXP
    + M
    + KPC

  * BRAGFLO_KRP2 (:ref:`see QA plot <krp2-sat-pc>`) 
    Note: If not running in the ``TWOPHASE_MODE``, ``PCT_A`` and ``PCT_EXP`` 
    should be replaced with ``IGNORE_PERMEABILITY`` and ``ALPHA``, where 
    :math:`1/\alpha = P_t = ak^v` where ``ALPHA``:math:`=\alpha`, 
    ``PCT_A``:math:`=a`, and ``PCT_EXP``:math:`=v`.

    + LIQUID_RESIDUAL_SATURATION
    + PCT_A 
    + PCT_EXP
    + LAMBDA
    + KPC

  * BRAGFLO_KRP3 (:ref:`see QA plot <krp3-sat-pc>`) 
    Note: If not running in the ``TWOPHASE_MODE``, ``PCT_A`` and ``PCT_EXP`` 
    should be replaced with ``IGNORE_PERMEABILITY`` and ``ALPHA``, where 
    :math:`1/\alpha = P_t = ak^v` where ``ALPHA``:math:`=\alpha`, 
    ``PCT_A``:math:`=a`, and ``PCT_EXP``:math:`=v`.

    + LIQUID_RESIDUAL_SATURATION
    + GAS_RESIDUAL_SATURATION
    + PCT_A 
    + PCT_EXP
    + LAMBDA
    + KPC

  * BRAGFLO_KRP4 (:ref:`see QA plot <krp4-sat-pc>`)
    Note: If not running in the ``TWOPHASE_MODE``, ``PCT_A`` and ``PCT_EXP`` 
    should be replaced with ``IGNORE_PERMEABILITY`` and ``ALPHA``, where 
    :math:`1/\alpha = P_t = ak^v` where ``ALPHA``:math:`=\alpha`, 
    ``PCT_A``:math:`=a`, and ``PCT_EXP``:math:`=v`.

    + GAS_RESIDUAL_SATURATION
    + PCT_A 
    + PCT_EXP
    + LAMBDA
    + KPC

  * BRAGFLO_KRP5 (:ref:`see QA plot <krp5-sat-pc>`)
    Note: If not running in the ``TWOPHASE_MODE``, ``PCT_A`` and ``PCT_EXP`` 
    should be replaced with ``IGNORE_PERMEABILITY`` and ``ALPHA``, where 
    :math:`1/\alpha = P_t = ak^v` where ``ALPHA``:math:`=\alpha`, 
    ``PCT_A``:math:`=a`, and ``PCT_EXP``:math:`=v`.

    + LIQUID_RESIDUAL_SATURATION
    + GAS_RESIDUAL_SATURATION
    + PCT_A 
    + PCT_EXP
    + KPC

  * BRAGFLO_KRP8 (:ref:`see QA plot <krp8-sat-pc>`) 
    Note: If not running in the ``TWOPHASE_MODE``, ``PCT_A`` and ``PCT_EXP`` 
    should be replaced with ``IGNORE_PERMEABILITY`` and ``ALPHA``, where 
    :math:`1/\alpha = P_t = ak^v` where ``ALPHA``:math:`=\alpha`, 
    ``PCT_A``:math:`=a`, and ``PCT_EXP``:math:`=v`.

    + LIQUID_RESIDUAL_SATURATION
    + GAS_RESIDUAL_SATURATION
    + PCT_A 
    + PCT_EXP
    + M
    + KPC

  * BRAGFLO_KRP9 (:ref:`see QA plot <krp9-sat-pc>`)

    + LIQUID_RESIDUAL_SATURATION

  * BRAGFLO_KRP11 (:ref:`see QA plot <krp11-sat-pc>`)

    + [no parameters needed]

  * BRAGFLO_KRP12 (:ref:`see QA plot <krp12-sat-pc>`)
    Note: If not running in the ``TWOPHASE_MODE``, ``PCT_A`` and ``PCT_EXP`` 
    should be replaced with ``IGNORE_PERMEABILITY`` and ``ALPHA``, where 
    :math:`1/\alpha = P_t = ak^v` where ``ALPHA``:math:`=\alpha`, 
    ``PCT_A``:math:`=a`, and ``PCT_EXP``:math:`=v`.

    + LIQUID_RESIDUAL_SATURATION
    + PCT_A
    + PCT_EXP
    + LAMBDA
    + S_MIN
    + S_EFFMIN
    + KPC

  The parameters ALPHA, LAMBDA, M, LIQUID_RESIDUAL_SATURATION,
  GAS_RESIDUAL_SATURATION, KPC, S_MIN, S_EFFMIN, NPARAM, SIGMAZ, MUZ, RMAX,
  R0, and SMOOTH are defined below under :ref:`parameter-definitions`.



PERMEABILITY_FUNCTION <string>
  Opens a relative permeability function block where <string> indicates the
  type of liquid or gas relative permeability function. For multiphase flow,
  (e.g. GENERAL MODE) a relative permeability function must be defined for each
  phase. For single-phase variably saturated flow (e.g. RICHARDS MODE), only a liquid phase 
  relative permeability function should be specified.

  The available relative permeability functions are documented in the Theory Guide under
  :ref:`relative-permeability-functions-general`.
  (Note: BC = Brooks-Corey; VG = van Genuchten)

  Supported liquid phase PERMEABILITY_FUNCTIONs and associated cards:
  
  * MUALEM_BC_LIQ (:ref:`see QA plot <bcm-rel-perm>`)
     + LAMBDA
     + LIQUID_RESIDUAL_SATURATION
  * BURDINE_BC_LIQ (:ref:`see QA plot <bcb-rel-perm>`)
     + LAMBDA
     + LIQUID_RESIDUAL_SATURATION
  * MUALEM_LINEAR_LIQ (:ref:`see QA plot <lm-rel-perm>`)
     + ALPHA
     + LIQUID_RESIDUAL_SATURATION
     + MAX_CAPILLARY_PRESSURE
  * BURDINE_LINEAR_LIQ (:ref:`see QA plot <lb-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
  * MUALEM_VG_LIQ (:ref:`see QA plot <vgm-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + M
     + SMOOTH
  * BURDINE_VG_LIQ (:ref:`see QA plot <vgb-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + M
     + SMOOTH
  * MODIFIED_KOSUGI_LIQ (:ref:`see QA plot <mk-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + SIGMAZ
  * MODIFIED_KOSUGI_LIQ (:ref:`see QA plot <mk-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + SIGMAZ
  * MODIFIED_BROOKS_COREY_LIQ
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + KR_MAX
     + N
  * PCHIP_LIQ
    + FILE
    + LIST

  Supported gas phase PERMEABILITY_FUNCTIONs and associated cards:
  
  * MUALEM_BC_GAS (:ref:`see QA plot <bcm-rel-perm>`)
     + GAS_RESIDUAL_SATURATION
     + LIQUID_RESIDUAL_SATURATION
     + LAMBDA
  * BURDINE_BC_GAS (:ref:`see QA plot <bcb-rel-perm>`)
     + GAS_RESIDUAL_SATURATION
     + LIQUID_RESIDUAL_SATURATION
     + LAMBDA
  * MUALEM_LINEAR_GAS (:ref:`see QA plot <lm-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + MAX_CAPILLARY_PRESSURE
     + ALPHA
  * BURDINE_LINEAR_LIQ (:ref:`see QA plot <lb-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
  * MUALEM_VG_GAS (:ref:`see QA plot <vgm-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + M
  * BURDINE_VG_GAS (:ref:`see QA plot <vgb-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + M
  * MODIFIED_KOSUGI_GAS (:ref:`see QA plot <mk-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + SIGMAZ
  * MODIFIED_BROOKS_COREY_GAS
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + KR_MAX
     + N
  * PCHIP_GAS
    + FILE
    + LIST

  WIPP-specific liquid and gas phase PERMEABILITY_FUNCTIONs:

  * BRAGFLO_KRP1_LIQ (:ref:`see QA plot <krp1-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + M
  * BRAGFLO_KRP2_LIQ (:ref:`see QA plot <krp2-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + LAMBDA
  * BRAGFLO_KRP3_LIQ (:ref:`see QA plot <krp3-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + M
  * BRAGFLO_KRP4_LIQ (:ref:`see QA plot <krp4-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + LAMBDA
  * BRAGFLO_KRP5_LIQ (:ref:`see QA plot <krp5-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
  * BRAGFLO_KRP8_LIQ (:ref:`see QA plot <krp8-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + M
  * BRAGFLO_KRP9_LIQ (:ref:`see QA plot <krp9-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
  * BRAGFLO_KRP11_LIQ (:ref:`see QA plot <krp11-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + TOLC
  * BRAGFLO_KRP12_LIQ (:ref:`see QA plot <krp12-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + LAMBDA
  * BRAGFLO_KRP1_GAS (:ref:`see QA plot <krp1-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + M
  * BRAGFLO_KRP2_GAS (:ref:`see QA plot <krp2-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + LAMBDA
  * BRAGFLO_KRP3_GAS (:ref:`see QA plot <krp3-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + LAMBDA
  * BRAGFLO_KRP4_GAS (:ref:`see QA plot <krp4-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + LAMBDA
  * BRAGFLO_KRP5_GAS (:ref:`see QA plot <krp5-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
  * BRAGFLO_KRP8_GAS (:ref:`see QA plot <krp8-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + M
  * BRAGFLO_KRP9_GAS (:ref:`see QA plot <krp9-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
  * BRAGFLO_KRP11_GAS (:ref:`see QA plot <krp11-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + TOLC
  * BRAGFLO_KRP12_GAS (:ref:`see QA plot <krp12-rel-perm>`)
     + LIQUID_RESIDUAL_SATURATION
     + GAS_RESIDUAL_SATURATION
     + LAMBDA

  :ref:`parameter-definitions`.

.. _parameter-definitions:

Parameter Definitions
---------------------
ALPHA <float>
 Inverse of the air entry pressure for saturation function [Pa\ :sup:`-1`\].

FILE <string>
 Filepath to file containing saturation-capillary pressure or saturation-relative permeability pairs. Must be in ascending order of saturation and monotonic.

KPC <integer>
 WIPP-specific flag from BRAGFLO.
 * KPC 1 ignores MAX_CAPILLARY_PRESSURE
 * KPC 2 Flat Set KPC to ``2`` to activate
 * KPC 3-5 Not used
 * KPC 6 Pc Linear extension from SATURATION_JUNCTION_SATURATION to 0.0 LIQUID SATURATION 
 * KPC 7 Pc Exponential extension from SATURATION_JUNCTION_SATURATION to 0.0 LIQUID SATURATION 

KR_MAX <float>
 Modified Brooks Corey relative permeability function maximum 
 relative permeability [-].

LAMBDA <float>
 Brooks-Corey \lambda parameter [-].

LIST
  Opens block to list saturaiton-capillary pressure or saturation-relative permeability value pairs. Must be in ascending order of saturation and monotonic.
M <float>
 Exponential parameter m in van Genuchten models. Parameter n is calculated as follows:

 * For van Genuchten capillary pressure, n=1/(1-m).
 * For van Genuchten relative permeability with Burdine equations, n = ?
 * For van Genuchten relative permeability with Mualem equations, n = ?

N <float>
 Modified Brooks Corey relative permeability exponent "n" [-].

S_MIN <float>
 This is a parameter from BRAGFLO. It is a cutoff in liquid saturation that is
 considered numerically dry, and it is smaller than liquid residual saturation.

S_EFFMIN <float>
 This is a parameter from BRAGFLO. It is the liquid saturation below S_MIN
 at which the Brooks Corey model becomes singular, or the capillary pressure
 is capped. It can also be thought of as a small tolerance which pushes the
 singularity in the capillary pressure to a liquid saturation slightly below
 S_MIN.

SMOOTH
 Applies polynomial smoothing to discontinuities in derivatives for relative 
 permeability or saturation functions.
 The smoothing operation is documented under :ref:`smoothing-operation` in
 the Theory Guide.
 Supported for the following:

  * Brooks Corey (**highly recommended if saturated cells exist**)
  * Burdine (w/ van Genuchten liquid relative permeability)
  * Mualem (w/ van Genuchten liquid relative permeability)

TOLC <float>
 A tolerance interval over which the relative permeability changes linearly
 from zero to one [-].


MODIFIED_KOSUGI model
 This model is based on a truncated lognormal pore-size
 distribution. The distribution is truncated at the higher end only
 (3-parameter version) or higher and lower ends (4-parameter version)
 of the pore-size distribution. The original Kosugi model was for a
 3-parameter moisture retention curve, but only developed a relative
 permeability function in the limit as :math:`\mathrm{R_{MAX}}
 \rightarrow \infty` and :math:`\mathrm{R}_0 \rightarrow 0` (i.e., the
 2-parameter version). PFLOTRAN implements a closed-form approximation
 to the 3-parameter relative permeability function and an extended
 4-parameter moisture retention curve and relative permeability model
 proposed by Malama & Kuhlman
 (2015). http://dx.doi.org/10.1111/gwat.12220

  * SIGMAZ <float> variance of the log pore-size distribution (in m).
    Essentially, this parameter is related to the slope and location of the
    inflection in the moisture retention and relative permeability curves.

  * MUZ <float> mean of the log pore-size distribution (in m). Essentially,
    this parameter is related to the position of the moisture retention curve
    along the capillary pressure axis (i.e., similar to the air-entry pressure).

  * NPARAM <int> number of parameters in the model. Valid values are 3
    (upper-truncated pore-size distribution only) and 4 (upper- and
    lower-truncated pore-size distribution). When this is set to 3 the value
    of R0 is not used, and is not required to be set.

  * RMAX <float> maximum pore size (in m) in lognormal pore-size
    distribution.

  * R0 <float> minimum pore size (in m) in lognormal pore-size
    distribution. Only used if NPARAM=4. The user must ensure
    :math:`\mathrm{R_0}<\mathrm{R_{MAX}}`. Also, if they are too close 
    numerical problems may arise.

Optional Cards under the CHARACTERISTIC_CURVES block:
*****************************************************

DEFAULT
 Sets up dummy saturation and permeability functions for saturated single phase
 flow. If DEFAULT is specified, then the SATURATION_FUNCTION and the
 PERMEABILITY_FUNCTION blocks need not be specified.

TEST
 Including this keyword will produce output (.dat files) which provides (a) the
 capillary pressure for the entire range of liquid saturation, (b) the liquid
 saturation for the entire range of capillary pressures, and (c) the liquid and
 gas relative permeability values for the range of liquid saturation. See
 :ref:`how-to-test-CCs` for detailed instructions on how to use this keyword.


Optional Cards under the SATURATION_FUNCTION or PERMEABILITY_FUNCTION blocks:
*****************************************************************************

GAS_RESIDUAL_SATURATION <float>
 Residual saturation of gas phase [-]. Where used, default 100%.

LIQUID_JUNCTION_SATURATION <float>
 Liquid saturation for UNSATURATED_EXTENSION extrapolations [-]. Default 5% effective saturation (.05*(1-Srg-Srl)+Srl).

LIQUID_RESIDUAL_SATURATION <float>
 Residual saturation of liquid phase [-]. Default 0%.

LOOP_INVARIANT
 Caches calculated intermediate parameters, depending on compiler options, may speed performance. This is a necessary selection to utilize UNSATURATED_EXTENSIONS.

MAX_CAPILLARY_PRESSURE <float>
 Maximum capillary pressure in Pa. Default value is 10^9 Pa.
 Default behaivor truncates capillary pressure to this value near and below residual saturation.
 UNSATURATED_EXTENSIONs set this value at 0 liquid saturation and interpolate.

SPLINE <integer>
 Replace analytic model with Piecewise Cubic Hermite Interpolation Polynomials (PCHIP).
 This may reduce computational time for complex saturation or relative permeability functions.

UNSATURATED_EXTENSION <string>
 Define capillary pressure behaivor near and below residual saturation. Options include:

 * NONE - Asymptotically approach infinity at residual and remain undefined below residual.
 * FCPC - Truncation to MAX_CAPILLARY_PRESSURE and extrapolation to 0 saturation. Default.
 * FNOC - Truncation to value calculated at LIQUID_JUNCTION_SATURATION and extrapolation to 0 saturation.
 * LCPC - Linear interpolation from MAX_CAPILLARY_PRESSURE at 0 to calculated junction.
 * ECPC - Exponential interpolation from MAX_CAPILLARY_PRESSURE at 0 to calculated junction.
 * LNOC - Linear extrapolation from LIQUID_JUNCTION_SATURATION to 0 saturation.
 * ENOC - Exponential extrapolation from LIQUID_JUNCTION_SATURATION to 0 saturation.

Examples
********

RICHARDS mode
-------------
 ::

  ! for saturated flow
  CHARACTERISTIC_CURVES default
    DEFAULT
  END

  ! note: no need to specify phase as Richards is solely water phase
  CHARACTERISTIC_CURVES sf1
    SATURATION_FUNCTION VAN_GENUCHTEN
      M 0.286
      ALPHA  1.9401d-4
      LIQUID_RESIDUAL_SATURATION 0.115
    /
    PERMEABILITY_FUNCTION MUALEM_VG_LIQ
      M 0.286
      LIQUID_RESIDUAL_SATURATION 0.115
    /
  END

  CHARACTERISTIC_CURVES sf2
    SATURATION_FUNCTION BROOKS_COREY
      LIQUID_RESIDUAL_SATURATION 0.115d0
      LAMBDA 0.7d0
      ALPHA 1.3d-6
      MAX_CAPILLARY_PRESSURE 1.d8
      SMOOTH
    /
    PERMEABILITY_FUNCTION MUALEM_BC_LIQ
      LIQUID_RESIDUAL_SATURATION 0.115
      LAMBDA 0.7d0
    /
  END

  CHARACTERISTIC_CURVES hygiene_sandstone_vg
    # Table 1 of van Genuchten (1980)
    SATURATION_FUNCTION VAN_GENUCHTEN
      ALPHA 8.05D-5
      M 9.0385D-1
      LIQUID_RESIDUAL_SATURATION 1.53D-1
    END
    PERMEABILITY_FUNCTION MUALEM_VG_LIQ
      M 9.0385D-1
      LIQUID_RESIDUAL_SATURATION 1.53D-1
    END
  END
  CHARACTERISTIC_CURVES hygiene_sandstone_mk
    # Table 1 of Malama & Kuhlman (2015)
    SATURATION_FUNCTION MODIFIED_KOSUGI
      NPARAM 3
      SIGMAZ 3.36D-1
      MUZ -6.30D0
      RMAX 3.05D-3
      LIQUID_RESIDUAL_SATURATION 1.53D-1
    END
    PERMEABILITY_FUNCTION MODIFIED_KOSUGI_LIQ
      SIGMAZ 3.36D-1
      LIQUID_RESIDUAL_SATURATION 1.53D-1
    END
  END

GENERAL mode
------------
 ::

  CHARACTERISTIC_CURVES cc1
    SATURATION_FUNCTION VAN_GENUCHTEN
      LIQUID_RESIDUAL_SATURATION 0.d0
      M 0.5d0
      ALPHA 1.d-4
      MAX_CAPILLARY_PRESSURE 1.d6
    /
    PERMEABILITY_FUNCTION MUALEM_VG_LIQ
      LIQUID_RESIDUAL_SATURATION 0.d0
      M 0.5d0
    /
    PERMEABILITY_FUNCTION MUALEM_VG_GAS
      LIQUID_RESIDUAL_SATURATION 0.d0
      GAS_RESIDUAL_SATURATION 1.d-40
      M 0.5d0
    /
  /

  CHARACTERISTIC_CURVES cc2
    SATURATION_FUNCTION BROOKS_COREY
      LIQUID_RESIDUAL_SATURATION 0.2d0
      LAMBDA 0.7d0
      ALPHA 9.869d-6
      MAX_CAPILLARY_PRESSURE 1.d8
      SMOOTH
    /
    PERMEABILITY_FUNCTION BURDINE_BC_LIQ
      LIQUID_RESIDUAL_SATURATION 0.2d0
      LAMBDA 0.7d0
      SMOOTH
    /
    PERMEABILITY_FUNCTION BURDINE_BC_GAS
      LIQUID_RESIDUAL_SATURATION 0.2d0
      GAS_RESIDUAL_SATURATION 1.d-5
      LAMBDA 0.7d0
      SMOOTH
    /
  /

  CHARACTERISTIC_CURVES cc3
    SATURATION_FUNCTION LINEAR
      LIQUID_RESIDUAL_SATURATION 0.1d0
    /
    PERMEABILITY_FUNCTION BURDINE_LINEAR_LIQ
      LIQUID_RESIDUAL_SATURATION 0.1d0
    /
    PERMEABILITY_FUNCTION BURDINE_LINEAR_GAS
      LIQUID_RESIDUAL_SATURATION 0.1d0
      GAS_RESIDUAL_SATURATION 0.15d0
    /
  /
