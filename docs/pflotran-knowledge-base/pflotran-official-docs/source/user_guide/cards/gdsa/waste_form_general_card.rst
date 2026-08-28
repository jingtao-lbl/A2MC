back to :ref:`card-index`

.. _waste-form-general-card:

WASTE_FORM_GENERAL
==================
The Waste Form Process Model is :ref:`formally documented here <pm_waste_form>`.

Specifies the waste form process model. 
Under the :ref:`simulation-card` block this process model is included by adding 
the ``WASTE_FORM`` block:

 ::
 
   SIMULATION
     SIMULATION_TYPE SUBSURFACE
     PROCESS_MODELS
       WASTE_FORM <name_string>
         TYPE GENERAL
       /
       SUBSURFACE_FLOW flow
         MODE GENERAL
       /
       SUBSURFACE_TRANSPORT transport
         MODE GIRT
       /
     /
   END
   
where <name_string> gives a user-defined name for the process model.

Required Cards:
---------------

WASTE_FORM_GENERAL
 Opens the WASTE_FORM_GENERAL block. Must have a matching END_WASTE_FORM_GENERAL.

.. _waste-form-general-mechanism:

MECHANISM <type_string>

 The mechanism block specifies a waste form mechanism. The mechanism includes the details of the radionuclide
 species, the waste form bulk material details, and the canister that contains the waste form. Several 
 different custom mechanisms can be defined, or chosen from pre-defined options. Each mechanism is given a 
 unique name, and later associated with specific listed waste forms. The following types are currently 
 supported: GLASS, DSNF, FMDM, FMDM_SURROGATE, FMDM_SURROGATE_KNNR, :ref:`WIPP<wipp_waste_form>`, ANALYTICAL,
 and CUSTOM.

 ::

    MECHANISM GLASS
    /

 Within the MECHANISM block, the following sub-blocks and cards must be included
 for any MECHANISM type:
 
 NAME <name_string> (required for all mechanism types)

  Specifies a name for the mechanism. This name should be unique.

  ::

    NAME glass02

.. _waste-form-general-mechanism-species:

 SPECIES sub-block (required for all mechanism types)

  Specifies a list of waste form species, their formula weights (in units of g-species/mol-species), decay 
  constant (in units of 1/sec), initial mass fraction within the waste form matrix (g-species/g-bulk), 
  instant release fraction (a number between 0 and 1), and the name of the species daughter (if it exists).   
  The species listed here must also be listed in the CHEMISTRY block under Primary Species. Isotopes decay
  and ingrowth occurs following a 3-generation analytical solution derived for multiple parents and 
  grandparents and non-zero initial daughter concentrations, or by an implicit solution of the Bateman
  equation.
  
  ::

    SPECIES
     I-129   128.90d0 1.29d-15  2.18d-4  0.7d0
     Am-241  241.06d0 5.08d-11  8.70d-4  0.0d0  Np-237       
     Np-237  237.05d0 1.03d-14  8.59d-4  0.7d0  U-233
     U-233   233.04d0 1.38d-13  9.70d-9  0.0d0  Th-229   
     Th-229  229.03d0 2.78d-12  4.43d-12 0.0d0  
      ...      ...      ...        ...    ...     ...  
    /

 MATRIX_DENSITY <double> <unit_string> (required for all mechanism types)

  Specifies the density of the waste form bulk (or matrix).
  
  ::

    MATRIX_DENSITY 2.0d3 kg/m^3
    
 The following sub-block cards are now separated by MECHANISM type:
 
* **MECHANISM GLASS sub-block cards:**
  
   SPECIFIC_SURFACE_AREA <double> <unit_string> (required for types GLASS, FMDM, FMDM_SURROGATE, FMDM_SURROGATE_KNNR; semi-optional for type 
   CUSTOM; do not include for types DSNF and WIPP)

    Specifies the specific surface area of the waste form bulk (or matrix). 
  
    ::

      SPECIFIC_SURFACE_AREA 2.78d-3 cm^2/g
    
   KIENZLER_DISSOLUTION (optional for type GLASS only)
    
    If chosen, this option will implement the Kienzler (2012) glass dissolution equation. No other
    dissolution parameters are needed (i.e., no other sub-block cards other than SPECIFIC_SURFACE_AREA).
    
    ::
    
      KIENZLER_DISSOLUTION
    
   K0 <double> <unit_string> (optional for GLASS only)
    
    Specifies the intrinsic dissolution rate. If no units are provided, default units are kg/m^2-sec.
    If KIENZLER_DISSOLUTION is chosen, this card should not be given.
    
    ::
    
      K0 580.d0 kg/m^2-day
    
   K_LONG <double> <unit_string> (optional for GLASS only)
   
    Specifies the constant dissolution rate over the long term when the pore fluid solution is at
    saturation with respect to SiO2. If no units are provided, default units are kg/m^2-sec.
    If KIENZLER_DISSOLUTION is chosen, this card should not be given.
    
    ::
    
      K_LONG 46.d0 g/m^2-day
    
   NU <double> (optional for GLASS only)
   
    Specifies the pH dependence parameter. If KIENZLER_DISSOLUTION is chosen, this 
    card should not be given.
    
    ::
    
      NU 3.44d0
    
   EA <double> <unit_string> (optional for GLASS only)
    
    Specifies the effective activation energy. If no units are provided, default 
    units are J/mol. If KIENZLER_DISSOLUTION is chosen, this card should not be given.
    
    :: 
    
      EA 5.83d4 J/mol
    
   Q <double or string> (optional for GLASS only)
    
    Specifies the ion activity product of H4SiO4. If a constant value is desired,
    it should be entered following the Q keyword. Alternatively, Q can be calculated
    within the simulation by specifying the string AS_CALCULATED following the Q 
    keyword. If you specify AS_CALCULATED, then SiO2(aq) must be included as a primary
    or secondary species in the :ref:`chemistry-card` block, and USE_FULL_GEOCHEMISTRY should
    also be specified if full geochemistry is otherwise not being calculated. 
    If KIENZLER_DISSOLUTION is chosen, this card should not be given.
    
    ::
    
      Q 3.4d-8
      
      Q AS_CALCULATED
   
   K <double> (optional for GLASS only)
   
    Specifies the equilibrium constant for the rate limiting step, which is the activity of H4SiO4
    at saturation with the glass. If KIENZLER_DISSOLUTION is chosen, this card should not be given.
   
   V <double> (optional for GLASS only)
   
    Specifies the exponent in the affinity term, as in [1-(Q/K)**(1/V)].
    If KIENZLER_DISSOLUTION is chosen, this card should not be given.
   
   PH <double or string> (optional for GLASS only)
   
    Specifies the pH value at the glass surface. If a constant value is desired,
    it should be entered following the PH keyword. Alternatively, pH can be calculated
    within the simulation by specifying the string AS_CALCULATED following the PH 
    keyword. If you specify AS_CALCULATED, then H+ must be included as a primary
    or secondary species in the :ref:`chemistry-card` block, and USE_FULL_GEOCHEMISTRY should
    also be specified if full geochemistry is otherwise not being calculated. 
    If KIENZLER_DISSOLUTION is chosen, this card should not be given.
    
    ::
    
      PH 6.8d0
      
      PH AS_CALCULATED
    
* **MECHANISM DSNF sub-block cards:**
 
   No additional sub-block cards are required. 
 
* **MECHANISM FMDM sub-block cards:**

   For additional inputs required for this mechanism see
   :ref:`FMDM Mechanism`.

   If the FMDM mechanism is used, follow these instructions on how to link the external FMDM: 
   :ref:`running-pflotran-fmdm`.
 
   SPECIFIC_SURFACE_AREA <double> <unit_string> (required for types GLASS, FMDM, FMDM_SURROGATE, FMDM_SURROGATE_KNNR; semi-optional for type 
   CUSTOM; do not include for types DSNF and WIPP)

    Specifies the specific surface area of the waste form bulk (or matrix). 
  
    ::

      SPECIFIC_SURFACE_AREA 2.78d-3 cm^2/g

   BURNUP <double> (required for types FMDM, FMDM_SURROGATE, FMDM_SURROGATE_KNNR; semi-optional for type 
   CUSTOM; do not include for types DSNF and WIPP)

    Specifies the burnup of the waste form bulk (or matrix). 

    ::

      BURNUP 6.0d1 ! GWd/MTHM

* **MECHANISM FMDM_SURROGATE sub-block cards:**

   For additional inputs required for this mechanism see
   :ref:`FMDM Surrogate Mechanism`.
   
	 
   SPECIFIC_SURFACE_AREA <double> <unit_string> (required for types GLASS, FMDM, FMDM_SURROGATE, FMDM_SURROGATE_KNNR; semi-optional for type 
   CUSTOM; do not include for types DSNF and WIPP)

    Specifies the specific surface area of the waste form bulk (or matrix). 
  
    ::

      SPECIFIC_SURFACE_AREA 2.78d-3 cm^2/g

   BURNUP <double> (required for types FMDM, FMDM_SURROGATE, FMDM_SURROGATE_KNNR; semi-optional for type 
   CUSTOM; do not include for types DSNF and WIPP)

    Specifies the burnup of the waste form bulk (or matrix). 

    ::

      BURNUP 6.0d1 ! GWd/MTHM

   DECAY_TIME <double> <unit_string> (required for types FMDM_SURROGATE and FMDM_SURROGATE_KNNR; do not include for types CUSTOM, 
   DSNF, FMDM, and WIPP)

    Specifies the offset for the age of the fuel relative to the beginning of simulation time.

    ::

      DECAY_TIME 1.0d2 year

* **MECHANISM FMDM_SURROGATE_KNNR sub-block cards:**

   For additional inputs required for this mechanism see
   :ref:`FMDM Surrogate Mechanism`.
   
	 
   SPECIFIC_SURFACE_AREA <double> <unit_string> (required for types GLASS, FMDM, FMDM_SURROGATE, FMDM_SURROGATE_KNNR; semi-optional for type 
   CUSTOM; do not include for types DSNF and WIPP)

    Specifies the specific surface area of the waste form bulk (or matrix). 
  
    ::

      SPECIFIC_SURFACE_AREA 2.78d-3 cm^2/g

   BURNUP <double> (required for types FMDM, FMDM_SURROGATE, FMDM_SURROGATE_KNNR; semi-optional for type 
   CUSTOM; do not include for types DSNF and WIPP)

    Specifies the burnup of the waste form bulk (or matrix). 

    ::

      BURNUP 6.0d1 ! GWd/MTHM

   DECAY_TIME <double> <unit_string> (required for types FMDM_SURROGATE and FMDM_SURROGATE_KNNR; do not include for types CUSTOM, 
   DSNF, FMDM, and WIPP)

    Specifies the offset for the age of the fuel relative to the beginning of simulation time.

    ::

      DECAY_TIME 1.0d2 year
 
* **MECHANISM WIPP sub-block cards:**
 
   No additional sub-block cards are required.  **If the WIPP mechanism is used, the**
   **UFD_DECAY process model must also be used or the solubility limit functionality will not work properly.**
   Please read the :ref:`formal documentation here<wipp_waste_form>`.
 
* **MECHANISM CUSTOM sub-block cards:**

   DISSOLUTION_RATE <double> <unit_string> (semi-optional for type CUSTOM; do not include for type GLASS, 
   DSNF, FMDM, FMDM_SURROGATE, FMDM_SURROGATE_KNNR or WIPP)

    Specifies the dissolution rate for the waste form bulk (or matrix), in units of mass per surface area per 
    time. If dissolution rate is given for the CUSTOM mechanism type, the SPECIFIC_SURFACE_AREA must also be 
    specified (see below).

    ::

      DISSOLUTION_RATE 7.8d-8 kg/m^2-day

   FRACTIONAL_DISSOLUTION_RATE <double> <unit_string> (semi-optional for type CUSTOM; do not include for types 
   GLASS, DSNF, FMDM, FMDM_SURROGATE, FMDM_SURROGATE_KNNR or WIPP)

    Specifies the fractional dissolution rate for the waste form bulk (or matrix), in units of fractional 
    volume per time of the remaining volume. The unit string should resemble 1/time. 

    :: 

      FRACTIONAL_DISSOLUTION_RATE 3.4d-8 1/day
      
   FRACTIONAL_DISSOLUTION_RATE_VI <double> <unit_string> (semi-optional for type CUSTOM; do not include for types 
   GLASS, DSNF, FMDM, FMDM_SURROGATE, FMDM_SURROGATE_KNNR or WIPP)

    Specifies the fractional dissolution rate for the waste form bulk (or matrix), in units of fraction of 
    the initial volume per time. The unit string should resemble 1/time. 

    :: 

      FRACTIONAL_DISSOLUTION_RATE_VI 9.1d-5 1/day
    
   SPECIFIC_SURFACE_AREA <double> <unit_string> (required for types GLASS, FMDM, FMDM_SURROGATE, FMDM_SURROGATE_KNNR; semi-optional for type 
   CUSTOM; do not include for types DSNF and WIPP)

    Specifies the specific surface area of the waste form bulk (or matrix). If specific surface area is given 
    for the CUSTOM mechanism type, the DISSOLUTION_RATE keyword must also be specified (see above).
  
    ::

      SPECIFIC_SURFACE_AREA 2.78d-3 cm^2/g
      
* **Optional keywords for ALL MECHANISM types:**      

  SEED <integer>
  
   Specifies a seed number (must be an integer) which seeds the random number 
   generator that selects waste package degradation rates from the truncated
   normal distribution. If this keyword is omitted, the default seed value is 1.
      
* **Optional sub-block for ALL MECHANISM types:**

  CANISTER_DEGRADATION_MODEL sub-block (optional for all mechanism types)

   If this optional block is included, the canister degradation model will be turned on. Currently, this 
   model will keep track of canister vitality, a parameter which controls the time of waste form breach. At 
   the beginning of the simulation, vitality = 1. Waste form breach occurs when the canister vitality falls 
   to zero. The reference vitality degradation rate (Rv0) is either (a) chosen at the beginning of the 
   simulation, for each waste form, based on a normal distribution of degradation rates, (b) specified for 
   each waste form by the user, or (c) ignored if the user specifies a canister breach time for each waste 
   form instead of a rate. The effective vitality degradation rate (Rv) is calculated as an Arrhenius 
   function of temperature, canister material constant (C), and the reference vitality degradation rate: 

   log10(Rv) = log10(Rv0) + C * (1/333.15[K] - 1/T[K])

   If option "a" is desired, the normal distribution for the reference rate is formed by providing the 
   following block keywords:

    VITALITY_LOG10_MEAN

     Specifies the Log(base10) mean vitality degradation rate (in units of log10-1/yr). If this distribution 
     parameter is omitted, then CANISTER_VITALITY_RATE must be included for all waste forms associated with 
     this mechanism.

    VITALITY_LOG10_STDEV

     Specifies the Log(base10) standard deviation of the vitality degradation rate (in units of log10-1/yr). 
     If this distribution parameter is omitted, then CANISTER_VITALITY_RATE must be included for all waste 
     forms associated with this mechanism.

    VITALITY_UPPER_TRUNCATION

     Specifies the Log(base10) upper truncation of the mean vitality degradation rate (in units of 
     log10-1/yr). If this distribution parameter is omitted, then CANISTER_VITALITY_RATE must be included for 
     all waste forms associated with this mechanism.

    CANISTER_MATERIAL_CONSTANT

     Specifies the canister material constant (ex: 1500 for 316L stainless steel).

    ::
       
     CANISTER_DEGRADATION_MODEL
       VITALITY_LOG10_MEAN -4.5
       VITALITY_LOG10_STDEV 0.5
       VITALITY_UPPER_TRUNCATION -3.0
       CANISTER_MATERIAL_CONSTANT 1500
     /
     
    :ref:`buffer-erosion-copper-corrosion-card` (optional)
	 
     Specifies parameters for the buffer erosion/copper corrosion model.

Full examples of the MECHANISM sub-block (note some values may be unrealistic, these are just examples
for form, not parameter values):

::

    MECHANISM GLASS
      NAME glass02
      SPECIFIC_SURFACE_AREA 2.78d-3 m^2/kg
      MATRIX_DENSITY 2.0d3 kg/m^3
      KIENZLER_DISSOLUTION
      SPECIES 
       #name,   MW[g/mol],dcy[1/s], initMF, inst_rel_frac,daughter
        I-129   128.90d0  1.29d-15  2.18d-4   0.2d0
        Am-241  241.06d0  5.08d-11  8.70d-4   0.0d0  Np-237       
        Np-237  237.05d0  1.03d-14  8.59d-4   0.2d0  U-233
        U-233   233.04d0  1.38d-13  9.70d-9   0.0d0  Th-229
        Th-229  229.03d0  2.78d-12  4.43d-12  0.0d0
      /
      CANISTER_DEGRADATION_MODEL
        VITALITY_LOG10_MEAN -3.5
        VITALITY_LOG10_STDEV 1.5
        VITALITY_UPPER_TRUNCATION -2.75
        CANISTER_MATERIAL_CONSTANT 1500.0
      /
    /
    
    MECHANISM GLASS 
    NAME glass05
      SPECIFIC_SURFACE_AREA 2.78d-3 m^2/kg
      MATRIX_DENSITY 2.46d3 kg/m^3
      K0 560.d0 kg/m^2-day           #
      K_LONG 400.d0 kg/m^2-day       #
      NU 5.d-2                       #
      EA 60211.58 J/mol              #
      Q 1.d0                         #  Dissolution model parameters
      K 1.d0                         #
      V 1.d0                         #
      PH AS_CALCULATED               #
      SPECIES
       #name,   MW[g/mol],dcy[1/s], initMF, inst_rel_frac, daughter               
        I-129   128.90d0  1.29d-15  2.18d-4   0.2d0
        Am-241  241.06d0  5.08d-11  8.70d-4   0.0d0  Np-237
        Np-237  237.05d0  1.03d-14  8.59d-4   0.2d0  U-233
        U-233   233.04d0  1.38d-13  9.70d-9   0.0d0  Th-229
        Th-229  229.03d0  2.78d-12  4.43d-12  0.0d0  
      /  
      CANISTER_DEGRADATION_MODEL
        CANISTER_MATERIAL_CONSTANT 1500
      /
    /

    MECHANISM DSNF
      NAME dsnf01
      MATRIX_DENSITY 3.56d3 kg/m^3
      SPECIES 
       #name,   MW[g/mol],dcy[1/s], initMF, inst_rel_frac,daughter
        Am-243  243.06d0  2.98d-12  1.12d-5  0.0d0 
        Th-230  230.03d0  2.75d-13  2.45d-8  0.0d0 
      /
      CANISTER_DEGRADATION_MODEL
        VITALITY_LOG10_MEAN -3.2
        VITALITY_LOG10_STDEV 0.75
        VITALITY_UPPER_TRUNCATION -2.0
        CANISTER_MATERIAL_CONSTANT 1200.0
      /
    /
    
    MECHANISM WIPP
      NAME wipp3
      MATRIX_DENSITY 1.d0 g/m^3
      SPECIES 
       #name,    MW[g/mol],dcy[1/s], initMF, inst_rel_frac,daughter
        tracer   100.d0    2.d-15    1.12d0  0.0d0 
        tracer2  200.d0    2.d-15    1.12d0  0.0d0 
      /
    /

    MECHANISM CUSTOM
      NAME custom05
      FRACTIONAL_DISSOLUTION_RATE 2.0d-9 1/day
      MATRIX_DENSITY 2.44d3 kg/m^3
      SPECIES 
       #name,   MW[g/mol],dcy[1/s], initMF, inst_rel_frac,daughter
        Pu-240  240.05d0  3.34d-12  2.84d-3  0.2d0  U-236 
        U-236   236.05d0  9.20d-16  4.33d-3  0.0d0
        Tc-99   98.91d0   1.04d-13  8.87d-4  0.0d0
      /
      CANISTER_DEGRADATION_MODEL
        CANISTER_MATERIAL_CONSTANT 1500.0
      /
    /

    MECHANISM CUSTOM
      NAME custom03
      DISSOLUTION_RATE 4.1d-8 kg/m^2-day
      SPECIFIC_SURFACE_AREA 2.11d-3 m^2/kg
      MATRIX_DENSITY 2.44d3 kg/m^3
      SPECIES 
       #name,   MW[g/mol],dcy[1/s], initMF, inst_rel_frac,daughter
        Pu-240  240.05d0  3.34d-12  2.84d-3  0.2d0  U-236
        U-236   236.05d0  9.20d-16  4.33d-3  0.0d0
        Tc-99   98.91d0   1.04d-13  8.87d-4  0.0d0
      /
      CANISTER_DEGRADATION_MODEL
        VITALITY_LOG10_MEAN -3.5
        VITALITY_LOG10_STDEV 0.5
        VITALITY_UPPER_TRUNCATION -2.75
        CANISTER_MATERIAL_CONSTANT 1500.0
      /
    /

      MECHANISM FMDM
        NAME fmdm02
        MATRIX_DENSITY 10.97d3 kg/m^3
        BURNUP 60 #GWd/MTHM
        SPECIFIC_SURFACE_AREA 0.001 m^2/g
        SPECIES 
         #name,   MW[g/mol],dcy[1/s], initMF, inst_rel_frac,daughter
          Uranium 238.02d0  1.00d-90  0.50d0  0.0d0 
        /
        CANISTER_DEGRADATION_MODEL
          CANISTER_MATERIAL_CONSTANT 1500.0
        /
      /

      MECHANISM FMDM_SURROGATE
        NAME fmdm_surrogate01
        MATRIX_DENSITY 10.97d3 kg/m^3
        BURNUP 60 #GWd/MTHM
        SPECIFIC_SURFACE_AREA 0.001 m^2/g
        DECAY_TIME 100 year
        SPECIES 
         #name,   MW[g/mol],dcy[1/s], initMF, inst_rel_frac,daughter
          Uranium 238.02d0  1.00d-90  0.50d0  0.0d0 
        /
        CANISTER_DEGRADATION_MODEL
          CANISTER_MATERIAL_CONSTANT 1400.0
        /
      /

WASTE_FORM sub-block

 Specifies the details of each waste form. This block should be repeated for each waste form, and can include 
 the following cards:

  COORDINATE <double> <double> <double> -or- REGION <string>

   If COORDINATE, <double> <double> <double> gives the location of each waste form in x, y, z. Waste forms can
   be co-located (i.e., there can be multiple waste forms located at the same coordinate point. If REGION, 
   <string> gives the name of a defined region that the waste form occupies. The source term will be released
   over the cells of the REGION, or the single cell of the COORDINATE. Note that REGION and COORDINATE can't
   be given, only one is allowed.

  EXPOSURE_FACTOR <double> (optional)

   Gives the exposure factor of each waste form, which is a multiplier to the waste form dissolution rate. If 
   this keyword is not specified, the default value is 1.

  VOLUME <double> <unit_string>

   Gives the volume of each waste form.

  MECHANISM_NAME <string>

   Specifies the name of the mechanism associated with the waste form. The mechanism name given here must 
   match one of the mechanisms defined in the MECHANISM sub-block(s).

  CANISTER_VITALITY_RATE <double> <unit_string> (optional)

   Specifies the waste form canister's vitality degradation rate in units of 1/time. If this parameter is 
   specified, the mechanism associated to this waste form must include the CANISTER_DEGRADATION_BLOCK, but 
   *without* the distribution parameters (e.g. VITALITY_LOG10_MEAN, VITALITY_LOG10_STDEV, and  
   VITALITY_UPPER_TRUNCATION). This option cannot be combined with CANISTER_BREACH_TIME for a single waste 
   form, but both CANISTER_BREACH_TIME and CANISTER_VITALITY_RATE can be combined for different waste forms 
   under the same mechanism which omits the distribution parameters.

  CANISTER_BREACH_TIME <double> <unit_string> (optional)

   Specifies the waste form canister's breach time in units of time. The canister will breach during the next 
   timestep where time > CANISTER_BREACH_TIME. If this parameter is specified, the mechanism associated to 
   this waste form must include the CANISTER_DEGRADATION_BLOCK, but *without* the distribution parameters 
   (e.g. VITALITY_LOG10_MEAN, VITALITY_LOG10_STDEV, and VITALITY_UPPER_TRUNCATION). This option cannot be 
   combined with CANISTER_VITALITY_RATE for a single waste form, but both CANISTER_BREACH_TIME and 
   CANISTER_VITALITY_RATE can be combined for different waste forms under the same mechanism which omits the 
   distribution parameters.
  
  DECAY_START_TIME <double> <unit_string> (optional)
  
   Specifies the time that the waste within the waste form will begin to decay.
   If this card is not specified, the default decay start time is 0 seconds
   (e.g. at the first time step of the simulation). This card is useful if you
   have an inventory that is specific to a certain time in the simulation, and
   you don't want to back-calculate what the inventory should have been at
   the beginning of the simulation.

  CRITICALITY_MECHANISM_NAME <string> (optional)
   
   Specifies the name of the associated criticality mechanism defining the criticality event in the waste form. The criticality mechanism name given here must match one of the mechanisms defined in the CRITICALITY_MECH sub-block(s).
   
  SPACER_MECHANISM_NAME <string> (optional)
   
   Specifies the name of the associated spacer grid degradation mechanism in the waste form. The spacer grid degradation mechanism name given here must match one of the mechanisms defined in the SPACER_DEGRADATION_MECHANISM sub-block(s).
   

  ::

    WASTE_FORM
      COORDINATE 0.5d0 4.5d0 0.5d0
      EXPOSURE_FACTOR 4.d0
      VOLUME 1.14d0 m^3
      MECHANISM_NAME glass02
    /

    WASTE_FORM
      REGION WF-a1
      VOLUME 2.1d0 m^3
      CANISTER_BREACH_TIME 250 yr
      MECHANISM_NAME custom01
      CRITICALITY_MECHANISM_NAME crit_01
      SPACER_MECHANISM_NAME spc_01
    /

    WASTE_FORM
      REGION WF-3b
      VOLUME 0.55d0 m^3
      CANISTER_VITALITY_RATE 1.0d-7 1/yr
      MECHANISM_NAME custom01
    /

Optional Cards: 
---------------

PRINT_MASS_BALANCE

 If this option is included, output will be generated at each timestep that the waste form process model is 
 called. The output includes the cumulative mass and instantaneous mass rate for each species in each waste 
 form, the volume, dissolution rate, and the canister vitality of each waste form.
 
IMPLICIT_SOLUTION

 Including this card will solve the decay and ingrowth of the radionuclide
 inventory within the waste form using an implicit approach based on solving
 the Bateman equation using Newton's method. This option should be used if the
 3-generation analytical solution is not appropriate.
 
SPACER_DEGRADATION_MECHANISM
 
 If this optional block is included, a time- and temperature-dependent spacer grid corrosion model will be evaluated as a means of terminating criticality events associated with the waste form. The model becomes active after the canister is breached. When the spacer grids have degraded below 1% of the original total mass, they are assumed to fail, which implies a loss of critical configuration.
 
 The spacer grid vitality :math:`V_{s}` is determined using the corrosion rate :math:`R` and initial spacer thickness :math:`\tortuosity` over time steps :math:`t_{i}` to :math:`t_{i+1}`, where :math:`V_{s,0}=1` until the canister breach time:
 
 :math:`V_{s,i+1}=V_{s,i}-\frac{2R_{i+1}\cdot(t_{i+1}-t_{i})}{\tortuosity}`
 
 The areal weight gain :math:`W` of the oxide layer is governed by a scaling constant :math:`\mathcal{C}` and an Arrhenius term with the average temperature of the waste form :math:`\bar{T}`, the activation energy :math:`Q`, and the ideal gas constant :math:`\mathcal{R}`:
 
 :math:`W_{i+1}=\mathcal{C}\exp{\left(-\frac{Q}{\mathcal{R}\bar{T}_{i+1}}\right)}`
 
 The total corrosion rate :math:`R` is found by including the metal loss ratio :math:`\alpha`, an irradiation factor :math:`\beta`, and a saturation-dependent term :math:`f_{S}(S_{l})`:
 
 :math:`R_{i+1}=f_{S}(S_{l,i+1})\cdot \alpha\cdot\beta\cdot W_{i+1}`
 
 The extent of original metal consumed in the oxide layer formation :math:`\Delta\tortuosity|_{lab}` and the areal weight gain of oxide layer :math:`\Delta W|_{lab}`, as observed in the laboratory, are used to determine the metal loss ratio :math:`\alpha`, which is considered constant. The factor :math:`\beta` is used to adjust the rate based on the effects of prior irradiation.
 
 :math:`\alpha=\frac{\Delta\tortuosity|_{lab}}{\Delta W|_{lab}}`
 
 The saturation-dependent term modifies the corrosion rate depending on an exposure level :math:`S_{l}^{exp}`, which is the saturation for which the spacer grids are considered fully-inundated with water. When the saturation of the waste form is at or above this limit, the corrosion rate is unaffected. Otherwise, the rate is reduced proportionally based on the saturation.  
 
 :math:`f_{S}(S_{l})=\left\{{\begin{array}{cc}
 \frac{S_{l}}{S_{l}^{exp}} & S_{l}<S_{l}^{exp} \\
 1 & S_{l}\geq S_{l}^{exp} \\
 \end{array} }\right.`
 
 NAME <name_string>
 
  Specifies a unique name for the spacer grid degradation model.
 
 METAL_LOSS_RATIO <double> <unit_string>

  The ratio of the extent [m] of original metal that is consumed by corrosion to the areal weight gain :math:`\left[\frac{kg}{m^2}\right]` of the oxide layer, :math:`\alpha\,\left[\frac{m^{3}}{kg}\right]`.

 THICKNESS <double> <unit_string>

  Initial thickness of the spacer grid metallic separators, :math:`\tortuosity` [m] .

 EXPOSURE_LEVEL <double> (optional)

  Threshold saturation :math:`S_{l}^{exp}` for spacer grids to be considered fully-inundated with water. Saturation-dependence can be turned off by setting :math:`S_{l}^{exp}=0` or by not including this entry. 

 C <double> <unit_string>

  Empirical coefficient of the Arrhenius term governing corrosion, :math:`\mathcal{C}\,\,\left[\frac{kg}{m^{2}s}\right]`.

 Q <double> <unit_string>

  Activation energy operating on the reciprocal of temperature within the Arrhenius term governing corrosion, :math:`Q` [J/mol]. 

 RAD_FACTOR <double>

  Factor by which to increase the corrosion rate based on the effect of prior irradiation, :math:`\beta`. This should be set to 1.0 for non-irradiated Zircaloy or a higher value (around 2.0) for spacer grids that have been irradiated. :math:`\beta` cannot be less than or equal to zero.

.. _waste-form-general-criticality-mechanism:

CRITICALITY_MECH
 
 Including this card will define a criticality mechanism that can specified for a waste form containing fissile material.
 
 NAME <name_string>
  
  Specifies a unique name for the criticality mechanism.

.. _waste-form-general-criticality-mechanism-start:

 CRIT_START <double> <unit_string>

  The start time of the criticality event.

.. _waste-form-general-criticality-mechanism-end:

 CRIT_END <double> <unit_string>

  The end time of the criticality event.

 CRITICAL_WATER_SATURATION <double>
  
  This is the liquid saturation below which the criticality event cannot be sustained. There is no heat emission from criticality until the waste form saturation is at or above this level. This is meant to be used for canisters in unsaturated systems and is not a permanent criticality termination mechanism.
 
 CRITICAL_WATER_DENSITY <double> <unit_string>
  
  This the liquid density below which the criticality event cannot be sustained. There is no heat emission from criticality until the waste form liquid density is at or above this level. This is meant to be used for canisters in saturated systems where moderator voiding is a key reactivity feedback mechanism, and it is not a permanent criticality termination mechanism.

.. _waste-form-general-criticality-mechanism-heat:
 
 HEAT_OF_CRITICALITY
  
  This sub-block defines the heat source term from criticality either as a constant (CONSTANT_POWER) or as a value that can obtained from a temperature-based lookup table (DATASET). The average temperature of the waste form and CRIT_START are used for interpolation of the lookup table to provide the power output from the waste form for the duration of the criticality event.
  
  CONSTANT_POWER <double> <unit_string>
  
  DATASET <file_string>
  
    Please refer to the example "crit_heat.txt" provided for the regression test "glass_general.in" for formatting. The data file specified by <file_string> contains the following input segments:
    
    NUM_START_TIMES <integer>
      
      The number of criticality start times provided in START_TIME (see below).
    
    NUM_VALUES_PER_START_TIME <integer>
    
      The number of data values per given criticality start time.
    
    TIME_UNITS <unit_string> (optional)
    
      The units of time provided for the START_TIME values (see below).
    
    POWER_UNITS <unit_string> (optional)
    
      The units of power provided for the POWER values (see below).
    
    START_TIME
    
      The start times of the criticality events relative to the beginning of the PFLOTRAN simulation, which are provided after the keyword as a list of reals. This affects the power output as the quantity of fissile nuclides, precursors, and neutron absorbers forming the source term for sustained chain reactions are affected by the decay period.
    
    TEMPERATURE
    
      The average waste form temperatures determining power output for a given start time, which are provided after the keyword as a list of reals. The temperature affects the power output via reactivity feedback from Doppler broadening, thermal expansion, and moderator voiding. Such phenomena are factored into the original neutronics calculations forming the basis of this surrogate model.
    
    POWER
    
      The waste form power outputs from the criticality event per given average temperature and start time, which are provided after the keyword as a list of reals.
  
 DECAY_HEAT <type_string>
  
  This sub-block defines the heat source term from radioactive decay, which is obtained from a time-dependent lookup table. The types of decay heat treatment include TOTAL, ADDITIONAL, and CYCLIC. By default, when a criticality event is active, the criticality source term is assumed to account for decay heat and this data is ignored.
  
  DATASET <file_string>

.. _waste-form-general-criticality-mechanism-inventory:

 INVENTORY
  
  This sub-block defines the fractional (g/g) nuclide inventory during criticality, which is obtained from a time-dependent lookup table and overrides the implicit calculation with the Bateman equations. The number of data entries in this table must equal the number of species specified in the waste form process model.
  
  DATASET <file_string>
  
    This option allows for the specification of simple lookup table specified by <file_string> where each row has the time of evaluation followed by mass fractions for each nuclide in the waste form listed in the order provided within SPECIES in MECHANISM. The table is linearly interpolated during the simulation and is assumed to correspond to the criticality conditions implied in the CRITICALITY_MECHANISM sub-block. The data table is preceded by the following keywords in the file:

    TIME_UNITS <unit_string> (optional)

      The units of time.

    DATA_UNITS <unit_string> (optional)
    
      The units for the nuclide inventory.

.. _waste-form-general-criticality-mechanism-inventory-expanded:

  EXPANDED_DATASET <file_string>

    This option allows for the specification of an expanded inventory lookup table that can be interpolated in three dimensions for a given criticality start time (:ref:`CRIT_START<waste-form-general-criticality-mechanism-start>`), criticality power output (:ref:`HEAT_OF_CRITICALITY<waste-form-general-criticality-mechanism-heat>`), and a given time during the simulation. These values are used to interpolate a data matrix where the start time and power are pivot variables and the simulation time is the independent variable. Please refer to the example data tables provided for the regression test "glass_criticality_inventory.in" for guidance on formatting. The data file specified by <file_string> contains the following input segments:

    MODE <string> (optional)

      POLYNOMIAL (default)
       The lookup table will be interpolated with Lagrange polynomials.

      LINEAR
        The lookup table will be interpolated using the trilinear method.

    NUM_START_TIMES <integer> (optional)

      Checks the number of criticality start times expected in the START_TIME list.

    NUM_POWERS <integer> (optional)

      Checks the number of powers expected in the POWER list.

    TOTAL_POINTS <integer> (optional)

      Checks the total number of inventory evaluation times expected in the REAL_TIME list. This keyword can be used if the real time arrays for each dataset are of different lengths and cannot be described completely by NUM_REAL_TIMES.

    NUM_REAL_TIMES <integer> (optional)

      Checks the maximum length of an individual real time array expected in the REAL_TIME list. This keyword can be used without TOTAL_POINTS if the real time arrays for each dataset are the same length.

    NUM_SPECIES <integer> (optional)

      Checks the number of INVENTORY blocks expected in the file. This should match the number of :ref:`SPECIES<waste-form-general-mechanism-species>` listed in the :ref:`MECHANISM<waste-form-general-mechanism>` of the waste form using this lookup table.

    TIME_UNITS <unit_string> (optional)

      The units of time for the values in START_TIME and REAL_TIME (used for conversion to internal units).

    POWER_UNITS <unit_string> (optional)

      The units of power for the values in POWERS (used for conversion to internal units).

    DATA_UNITS <unit_string> (optional)

      The units of inventory for the values in each INVENTORY block (used for conversion to internal units).

    START_TIME

      The start times of the criticality events relative to the beginning of the PFLOTRAN simulation, which are provided after the keyword as a list of reals. This is the first pivot variable used to construct the data matrix.

    POWER

      The power outputs of the criticality events, which are provided after the keyword as a list of reals. This is the second pivot variable used to construct the data matrix so the list is not duplicated per START_TIME. Per combination of START_TIME and POWER, there must be a dataset (i.e. no sparse data matrix).

    REAL_TIME

      The arrays of evaluation times for the radionuclide inventory, which are provided after the keyword as a list of reals. These values serve as the independent variables for the data matrix and the arrays have a multiplicity based on START_TIME and POWER. If TOTAL_POINTS is specified, the times must increase monotonically as a means of separating arrays.

    INVENTORY <name_string>

      For each radionuclide in the waste form using this lookup table, an INVENTORY block provides the mass fractions per given value in the REAL_TIME list. The name of the radionuclide is provided as <name_string> and must follow the spellings of :ref:`SPECIES<waste-form-general-mechanism-species>` in the waste form :ref:`MECHANISM<waste-form-general-mechanism>`. However, the INVENTORY blocks do not have to follow the same order as SPECIES. The mass fractions are listed as real numbers after the keyword line.
      
  OPTION (optional)

    This sub-block allows for the specification of options for the INVENTORY block.
    
    USE_LOOKUP_AND_IMPLICIT (optional)

      If :ref:`EXPANDED_DATASET<waste-form-general-criticality-mechanism-inventory-expanded>` is being used, this option allows for the PFLOTRAN implicit solution to be employed (i.e., radionuclide decay with no external sources) if the simulation time exceeds the maximum REAL_TIME in the relevant portion of the lookup table.

    USE_LOOKUP_AND_EXTRAPOLATION (optional)

      If :ref:`EXPANDED_DATASET<waste-form-general-criticality-mechanism-inventory-expanded>` is being used, this option allows for the interpolation subroutine to also be used for extrapolation when the simulation time exceeds the maximum REAL_TIME in the relevant portion of the lookup table.

    USE_LOOKUP_AFTER_CRITICALITY (optional)

      If :ref:`EXPANDED_DATASET<waste-form-general-criticality-mechanism-inventory-expanded>` is being used, this option allows for the lookup table to continue defining radionuclide inventories after the criticality event has ended (see :ref:`CRIT_END<waste-form-general-criticality-mechanism-end>`). Otherwise, the implicit solution (decay-only) is employed when time exceeds CRIT_END.

    LOG10_TIME_INTERPOLATION (optional)

      If :ref:`EXPANDED_DATASET<waste-form-general-criticality-mechanism-inventory-expanded>` is being used, this option allows for REAL_TIME interpolation of the lookup table to be based on the logarithm (base 10) of those values. For instances of :math:`t=0\,[s]` in the lookup table, a substitute value of :math:`t=10^{-20}\,[s]` is used, which may introduce bias depending on the choice of time steps in the simulation and the degree of time fidelity in the table. This option is recommended only if the simulation extends across multiple decades of time and if the time points in the table also extend logarithmically but are sparse.

 ::
 
   WASTE_FORM
     REGION wf
     EXPOSURE_FACTOR 1.d0
     VOLUME 1.5d0 m^3
     MECHANISM_NAME csnf
     CANISTER_BREACH_TIME 2.50d+2 y
     CRITICALITY_MECHANISM_NAME crit_01
     SPACER_MECHANISM_NAME spc_01
   /
   
   CRITICALITY_MECH
     NAME crit_01
     CRIT_START 3.00d+2 y
     CRIT_END   2.00d+3 y
     CRITICAL_WATER_SATURATION    0.700d+0
     CRITICAL_WATER_DENSITY 9.200d+2 kg/m^3
     HEAT_OF_CRITICALITY
       CONSTANT_POWER 4.0d+0 kW
       # DATASET criticality_heat.txt
     /
     DECAY_HEAT TOTAL
       DATASET ./decay_heat.txt
     /
     INVENTORY
       DATASET ./inventory_crit.txt
     /
   /
   
   SPACER_DEGRADATION_MECHANISM
     NAME              spc_01
     METAL_LOSS_RATIO  4.42953d-04  m^3/kg
     THICKNESS         5.00000d-04  m
     EXPOSURE_LEVEL    9.93317d-01
     C                 3.47000d+07  mg/day-dm^2
     Q                 2.27570d+04  cal/mol
     RAD_FACTOR        2.00000d+00
   /


Full Example:
-------------

The following example specifies several waste forms, each associated with one of two particular mechanisms. Output will be generated for each waste form.

::

    WASTE_FORM_GENERAL

      PRINT_MASS_BALANCE
      MECHANISM FMDM
        NAME fmdm01
        MATRIX_DENSITY 10.97d3 kg/m^3
        BURNUP 60 #GWd/MTHM
        SPECIFIC_SURFACE_AREA 0.001 m^2/g
        SPECIES 
         #name,   MW[g/mol],dcy[1/s], initMF, inst_rel_frac,daughter
          Uranium 238.02d0  1.00d-90  0.50d0  0.0d0 
        /
        CANISTER_DEGRADATION_MODEL
          VITALITY_LOG10_MEAN -3.2
          VITALITY_LOG10_STDEV 0.75
          VITALITY_UPPER_TRUNCATION -2.0
          CANISTER_MATERIAL_CONSTANT 1200.0
        /
      /
      MECHANISM CUSTOM
        NAME custom05
        FRACTIONAL_DISSOLUTION_RATE 2.0d-9 1/day
        MATRIX_DENSITY 2.44d3 kg/m^3
        SPECIES 
         #name,   MW[g/mol],dcy[1/s], initMF, inst_rel_frac,daughter
          Pu-240  240.05d0  3.34d-12  2.84d-3  0.2d0   U-236
          U-236   236.05d0  9.20d-16  4.33d-3  0.0d0
          Tc-99   98.91d0   1.04d-13  8.87d-4  0.0d0
        /
        CANISTER_DEGRADATION_MODEL
          CANISTER_MATERIAL_CONSTANT 1500.0
        /
      /
      WASTE_FORM
        REGION WF-custom-1
        EXPOSURE_FACTOR 3.d0
        VOLUME 1.14d0 m^3
        MECHANISM_NAME custom05
        CANISTER_BREACH_TIME 375 yr
      /
      WASTE_FORM
        REGION WF-custom-2
        EXPOSURE_FACTOR 4.d0
        VOLUME 1.14d0 m^3
        MECHANISM_NAME custom05
        CANISTER_VITALITY_RATE 3.d-6 1/day
      /
      WASTE_FORM
        COORDINATE 12.5d0 55.5d0 0.5d0
        VOLUME 1.55d0 m^3
        MECHANISM_NAME fmdm01
      /
      WASTE_FORM
        COORDINATE 5.5d0 4.5d0 0.5d0
        VOLUME 1.55d0 m^3
        MECHANISM_NAME fmdm01
      /

    END_WASTE_FORM_GENERAL
   
