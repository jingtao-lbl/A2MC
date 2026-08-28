.. _wipp-flow-mode-solution-controls:

WIPP_FLOW Mode Solution Controls
================================

Within the ``OPTIONS`` block of the ``WIPP_FLOW`` Mode, several solution
control parameters can be set. This page describes them all. An example of an
input deck ``SIMULATION`` block that uses and sets some solution control
parameters is shown below:

 ::

  SIMULATION
    SIMULATION_TYPE SUBSURFACE
    PROCESS_MODELS
      SUBSURFACE_FLOW FLOW
        MODE WIPP_FLOW
        OPTIONS
          FIX_UPWIND_DIRECTION
          GAS_COMPONENT_FORMULA_WEIGHT 2.01588D0 ! H2 kg/kmol
          LIQUID_EQUATION_TOLERANCE    1.d-6
          GAS_EQUATION_TOLERANCE       1.d-6
          LIQUID_PRESSURE_TOLERANCE    1.d-5
          GAS_SATURATION_TOLERANCE     1.d-4  ! (same functionality as EPS_SAT)
          PRESSURE_REL_PERTURBATION    1.d-8
          PRESSURE_MIN_PERTURBATION    1.d-2
          SATURATION_REL_PERTURBATION  1.d-8
          SATURATION_MIN_PERTURBATION  1.d-10
          DTIMEMAX   1.25
          SATLIMIT   1.d-3
          DSATLIM    0.20
          DSAT_MAX   1.0d-2
          SATNORM    3.d-1
          TSWITCH    1.d-2
          EPS_PRES   1.d-2  
          EPS_SAT    4      ! (same functionality as GAS_SATURATION_TOLERANCE)
          DPRELIM   -1.d8   ! Pa
          DPRES_MAX  1.d7   ! Pa
          PRESNORM   5.d5   ! Pa
          LSCALE
          DO_NOT_LSCALE
          P_SCALE    1.d7
        END
      END
    END
  END

  
GAS_SATURATION_TOLERANCE (EPS_SAT)
----------------------------------
The maximum relative change in gas saturation allowed in order for the solution 
to be accepted. For example, if ``GAS_SATURATION_TOLERANCE`` is 
:math:`1\times10^{-4}`, then a change in gas saturation over a Newton iteration 
that is larger than :math:`1\times10^{-4}` will force another Newton iteration.
The default value for ``GAS_SATURATION_TOLERANCE`` is :math:`1\times10^{-3}`.
**Currently, the WIPP_FLOW card EPS_SAT implements the** 
**same functionality. If both are specified, the tighter tolerance of the two** 
**will be chosen and assigned.**
  
SATLIMIT
--------
Limit on gas saturation solution beyond which a solution will not be accepted.
This limit is designed to ensure unphysical values for gas saturation are not
accepted as solutions.
If the gas saturation, :math:`S_g`, at the end of a Newton iteration is 
:math:`1.0 + SATLIMIT < S_g` or :math:`S_g < -SATLIMIT`, then another 
Newton iteration will be forced (i.e. the solution is not accepted).
The default value for ``SATLIMIT`` is :math:`1\times10^{-3}`. The value given
must be smaller than ``DSATLIM``.

DSATLIM
-------
Limit allowed on gas saturation outside of the physically realistic range 
between 0.0 and 1.0, and intended to simply reject a solution that is beyond
hope before any more computational effort is expended. If the gas saturation, 
:math:`S_g`, at the end of a Newton iteration is 
:math:`1.0 + DSATLIM < S_g` or :math:`S_g < -DSATLIM`, then the time step 
will be cut according to ``DELTFACTOR`` and the time step will be repeated. 
The default value for ``DSATLIM`` is :math:`0.20`. The value given must be 
larger than ``SATLIMIT``.

DPRELIM
-------
Lower limit allowed for the liquid pressure (brine), and is intended to simply
reject a solution that is beyond hope before any more computational effort is 
expended. If the liquid pressure, :math:`p_l`, at the end of a Newton iteration 
is negative and :math:`p_l < DPRELIM`, then the time step will be cut according 
to ``DELTFACTOR`` and the time step will be repeated. 
The default value for ``DPRELIM`` is :math:`-1\times10^{8}` Pa. The value
given must be negative.

DSAT_MAX
--------
The maximum absolute change in gas saturation allowed over a time step. If the 
solution has converged, but the absolute change in gas saturation was larger 
than ``DSAT_MAX``, then the time step will be cut according to ``DELTFACTOR``
and the time step is repeated.
The default value of ``DSAT_MAX`` is :math:`1.0`.

DPRES_MAX
---------
The maximum absolute change in liquid pressure (brine) allowed over a time step. 
If the solution has converged, but the absolute change in liquid pressure was 
larger than ``DPRES_MAX``, then the time step will be cut according to 
``DELTFACTOR`` and the time step is repeated.
The default value of ``DPRES_MAX`` is :math:`1\times10^{7}` Pa.

EPS_SAT (GAS_SATURATION_TOLERANCE)
----------------------------------
The digits of accuracy for the maximum absolute change in gas saturation allowed
in order for the solution to be accepted. For example, if ``EPS_SAT`` is 4, then
a change in gas saturation over a Newton iteration that is larger than
:math:`1\times10^{-4}` will force another Newton iteration.
The default value for ``EPS_SAT`` is :math:`3`.
**Currently, the WIPP_FLOW card GAS_SATURATION_TOLERANCE implements the** 
**same functionality. If both are specified, the tighter tolerance of the two** 
**will be chosen and assigned.**

EPS_PRES
--------
The maximum relative change in liquid pressure (brine) allowed over a time step. 
If the solution has converged, but the relative change in liquid pressure was 
larger than ``EPS_PRES``, then an other Newton iteration will be forced. 
The default value of ``EPS_PRES`` is :math:`1\times10^{-3}`.

SATNORM
-------
The largest relative change in gas saturation that is allowed over a time step 
so that the next time step will be the same as the current time step. If the 
largest relative change in gas saturation happens to be larger than ``SATNORM``, 
then the next time step will be reduced according to Section 
:ref:`wipp-ts-controls`. Similarly, if the largest relative change in gas 
saturation happens to be smaller than ``SATNORM``, then the next time step will
be increased, but this increase will be limited by the ramping factor 
given by ``DTIMEMAX``.
The default value for ``SATNORM`` is :math:`0.3`. 

PRESNORM
--------
The largest relative change in liquid pressure that is allowed over a time step 
so that the next time step will be the same as the current time step. If the 
largest relative change in liquid pressure happens to be larger than ``PRESNORM``, 
then the next time step will be reduced according to Section 
:ref:`wipp-ts-controls`. Similarly, if the largest relative change in liquid 
pressure happens to be smaller than ``PRESNORM``, then the next time step will
be increased, but this increase will be limited by the ramping factor 
given by ``DTIMEMAX``.
The default value for ``PRESNORM`` is :math:`5\times10^{5}` Pa.

TSWITCH
-------
The value for gas saturation where ``SATNORM`` will switch between using the 
maximum relative change in gas saturation over a time step or the maximum 
absolute change in gas saturation over a time step to decide on the next time 
step size. If :math:`S_g > TSWITCH`, then the maximum relative change in gas 
saturation will be used. If :math:`S_g < TSWITCH`, then the maximum absolute
change in the gas saturation will be used, so that division by a small number
is avoided. Default value for ``TSWITCH`` is :math:`0.01`.
  
DELTFACTOR (TIMESTEP_REDUCTION_FACTOR)
--------------------------------------
The time step reduction factor when non-convergence occurs and the time step 
is reduced and repeated. The equivalent functionality in PFLOTRAN is specified
with the ``TIMESTEP_REDUCTION_FACTOR`` keyword in the ``TIMESTEPPER`` block.
The default value for ``TIMESTEP_REDUCTION_FACTOR`` is :math:`0.5`.
An example of usage is below:

  ::
  
   TIMESTEPPER FLOW
     TIMESTEP_REDUCTION_FACTOR 0.5d0
     MAX_TS_CUTS 8
   END
  
DTIMEMAX
--------
Maximum time step ramping factor for determining the value of the next time step. 
The default value for ``DTIMEMAX`` is :math:`1.25`.

LSCALE
------
Toggles on scaling of Jacobian matrix and residual vector.
The default value for ``LSCALE`` is ``TRUE``.

DO_NOT_LSCALE
-------------
Toggles off scaling of Jacobian matrix and residual vector.
The default value for ``LSCALE`` is ``FALSE``.

P_SCALE
-------
The scaling factor by which the Jacobian matrix and residual vector are scaled.  
For each row of the matrix, the scaling factor is multiplied by the row's 
maximum absolute value.  The row entries and corresponding entry in the residual 
vector are then divided by that value. 
The default value for ``P_SCALE`` is :math:`10^{7}`.

MAXIT (ITMAX)
-------------
Maximum number of Newton iterations per time step.
The default value for ``MAXIT`` is :math:`50` based on PETSc defaults.  
BRAGFLO recommends :math:`10`.

  ::
  
   NEWTON_SOLVER FLOW
     MAXIT 10
   END


MAX_TS_CUTS (IRESETMAX)
-----------------------
Maximum number of time step cuts before PFLOTRAN shuts down due to lack of 
convergence. The default value for ``MAX_TS_CUTS`` is :math:`16`. BRAGFLO 
recomments :math:`40`.

  ::
  
   TIMESTEPPER FLOW
     MAX_TS_CUTS 40
   END
  
PRESSURE_REL_PERTURBATION (DHPRES_REL)
--------------------------------------
Relative change in liquid pressure for Jacobian derivative calculation.
The default value for ``PRESSURE_REL_PERTURBATION`` is :math:`10^{-8}`.

PRESSURE_MIN_PERTURBATION (DHPRES_MIN)
--------------------------------------
Minimum change in liquid pressure for Jacobian derivative calculation.
The default value for ``PRESSURE_MIN_PERTURBATION`` is :math:`10^{-2}`.

SATURATION_REL_PERTURBATION (DHSAT_REL)
---------------------------------------
Relative change in gas saturation Jacobian derivative calculation.
The default value for ``SATURATION_REL_PERTURBATION`` is :math:`10^{-8}`.

SATURATION_MIN_PERTURBATION (DHSAT_MIN)
---------------------------------------
Minimum change in gas saturation Jacobian derivative calculation.
The default value for ``SATURATION_MIN_PERTURBATION`` is :math:`10^{-10}`.

.. _wipp-ts-controls:

Algorithm That Determines Next Time Step Size
---------------------------------------------
The time step ramping factor, ``DTIME``, is automatically calculated in 
PFLOTRAN according to ``DTIME = (2.D0*DELTADEPNORM)/(DELTADEPNORM+DELTAMAX)``. 
The variable ``DELTADEPNORM`` is either ``SATNORM`` or ``PRESNORM``. 
The variable ``DELTAMAX`` is the maximum absolute change in the primary 
dependent variables (gas saturation or liquid pressure), or it is the maximum
relative change in the gas saturation is the current gas saturation value is 
larger than ``TSWITCH``. The value for ``DTIME`` is chosen 
to be the minimum of the value calculated using the gas saturation change and
the value using the liquid pressure change.
The minimum of the calculated value of ``DTIME`` and solution control
parameter ``DTIMEMAX`` is then chosen to multiply the current time step value
to obtain the next time step value. A final check is made to ensure that the
calculated value for the next time step is within the minimum and maximum 
time step sizes indicated in the input deck.
