Back to :ref:`card-index`

Back to :ref:`chemistry-card`

.. _microbial-reaction-card:

MICROBIAL_REACTION
==================
Specifies parameters for microbially-mediated reactions. 

By default, all aqueous concentrations are in molarity [mol/L].
The units of concentration in the RATE_CONSTANT, HALF_SATURATION, THRESHOLD_CONCENTRATION and INHIBITION_CONSTANT parameters must be consistent throughout all microbial reactions.

Required Cards:
---------------

REACTION <string>
 Reaction equation.  The rate constant is multiplied by the Monod expressions 
 for electron donor and acceptor for select species on the left side of the 
 equation.  The reaction may be inhibited by any species in the system.

RATE_CONSTANT <float>
 Rate constant for the reaction, where the units are [mol/L-sec] if no biomass, or [mol/(mol biomass-sec)] if biomass. Here, aqueous concentration units are the default [mol/L].

Optional Cards:
---------------

MONOD 
 Specifies the Monod equation for the electron donor or acceptor.

  SPECIES NAME <string>
   Name of the species in Monod expression
   
  HALF_SATURATION_CONSTANT <float>
   Half saturation constant for the Monod expression
   
  THRESHOLD_CONCENTRATION <float>
   Threshold concentration below which the reaction stops

INHIBITION
 Specifies inhibition ($I$) based on species concentration and inhibition 
 constant(s).  Three types of inhibition are currently supported: MONOD, 
 SMOOTHSTEP and THRESHOLD.

 TYPE <string>
  Type of inhibition: MONOD, SMOOTHSTEP or THRESHOLD

  MONOD:

   INHIBIT_ABOVE_THRESHOLD: $I = \frac{C_{th}}{C_{th} + C}$

   INHIBIT_BELOW_THRESHOLD: $I = \frac{C}{C_{th} + C}$

  SMOOTHSTEP:

   $z = max\left(min\left(\frac{log_{10}(C)-log_{10}(C_{th})}{\eta}+0.5,1\right),0\right)$ 
   where $\eta$ is the :math:`\text{log}_{10}` interval

   INHIBIT_ABOVE_THRESHOLD: $I = 1-(3z^2-2z^3)$

   INHIBIT_BELOW_THRESHOLD: $I = 3z^2-2z^3$

  THRESHOLD:

   INHIBIT_ABOVE_THRESHOLD: $I = 0.5 - atan((C-C_{th})*f)/\pi$

   INHIBIT_BELOW_THRESHOLD: $I = 0.5 + atan((C-C_{th})*f)/\pi$

 SPECIES_NAME <string>
  Name of the species in the inhibition term

 THRESHOLD_CONCENTRATION <float>
  Concentration ($C_{th}$) at which the inhibition factor is ${\sim}0.5$

 INHIBIT_ABOVE_THESHOLD or INHIBIT_BELOW_THESHOLD
  Inhibits the rate when the species concentration is above or below $C_{th}$.

 Other required cards

  For SMOOTHSTEP:

   SMOOTHSTEP_INTERVAL <float>
    Interval $\eta$ centered on $C_{th}$ in :math:`\text{log}_{10}` space 
    over which $I$ ranges between 0-1. Default = 3.

  For THRESHOLD:

   SCALING_FACTOR
    Scaling factor $f$. Default = $10^5 / C_{th}$.

BIOMASS 
 Specifies the immobile biomass species to be included in the rate expression.
 
  SPECIES_NAME <string>
   Name of the species
   
  YIELD <float>
   Fraction of energy going towared biomass synthesis.

CONCENTRATION_UNITS <string>
 Options include MOLARITY [mol/L], MOLALITY, [mol/kg water] and ACTIVITY. Default = MOLARITY.

Examples:
---------

 ::

  CHEMISTRY
    PRIMARY_SPECIES
      A(aq)
      B(aq)
      C(aq)
    /
    MICROBIAL_REACTION
      REACTION A(aq) + 2 B(aq) <-> 1.5 C(aq)
      RATE_CONSTANT 1.d-12
      MONOD
        SPECIES_NAME A(aq)     ! A is the donor
        HALF_SATURATION_CONSTANT 1.d-5
      /
      MONOD
        SPECIES_NAME B(aq)     ! B is the acceptor
        HALF_SATURATION_CONSTANT 1.d-4
      /
      INHIBITION ! inhibit at high C(aq) concentration
        SPECIES_NAME C(aq)
        TYPE MONOD
        INHIBIT_ABOVE_THRESHOLD
        THRESHOLD_CONCENTRATION 6.d-4
      /
    /
  ...

 ::

  CHEMISTRY
    PRIMARY_SPECIES
      A(aq)
      B(aq)
      C(aq)
    /
    IMMOBILE_SPECIES
      D(im)
    /
    MICROBIAL_REACTION
      CONCENTRATION_UNITS ACTIVITY
      REACTION A(aq) + 2 B(aq) <-> 1.5 C(aq)
      RATE_CONSTANT 1.d-6
      MONOD
        SPECIES_NAME A(aq)
        HALF_SATURATION_CONSTANT 1.d-5        ! A is the donor
        THRESHOLD_CONCENTRATION 1.d-20
      /
      MONOD
        SPECIES_NAME B(aq)
        HALF_SATURATION_CONSTANT 1.d-4        ! B is the acceptor
        THRESHOLD_CONCENTRATION 1.d-11
      /
      INHIBITION ! inhibit at low A(aq) concentration
        SPECIES_NAME A(aq)
        TYPE SMOOTHSTEP
        SMOOTHSTEP_INTERVAL 1.
        INHIBIT_BELOW_THRESHOLD
        THRESHOLD_CONCENTRATION 1.d-6
      /
      BIOMASS
        SPECIES_NAME D(im)
        YIELD 0.01d0
      /
    /
    IMMOBILE_DECAY_REACTION
      SPECIES_NAME D(im)
      RATE_CONSTANT 1.d-9
    /
    ...
  /
