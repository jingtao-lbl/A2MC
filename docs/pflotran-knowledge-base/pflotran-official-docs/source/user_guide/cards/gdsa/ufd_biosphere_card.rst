Back to :ref:`card-index`

.. _ufd-biosphere-card:

UFD_BIOSPHERE
=============

Specifies the Example Reference Biosphere (ERB) Model 1, which calculates annual
dose to an individual drinking radioactive water from a well (IAEA 2003).

Under the :ref:`simulation-card` block this process model is included by adding 
the ``UFD_BIOSPHERE`` block:

 ::
 
   SIMULATION
     SIMULATION_TYPE SUBSURFACE
     PROCESS_MODELS
       UFD_BIOSPHERE <name_string>
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

UFD_BIOSPHERE
 Opens the UFD_BIOSPHERE block. Must have a matching END line.
 
ERB_1A/B block
~~~~~~~~~~~~~~

ERB_1A or ERB_1B <name_string>
 Opens the ERB Model block with either the ERB_1A model type or the ERB_1B
 model type. Any number of ERB Models blocks may be specified. ERB_1A is
 used for water that is extracted by a sink (well) in the simulation.
 ERB_1B is used to approximate dose from a hypothetical well not explicitly
 modeled.

**ERB_1A block required cards:**

 REGION <string>
  Specifies the ``REGION`` associated with the ERB_1A model, where <string>
  indicates the name of that region. This region must be associated with a 
  :ref:`source-sink-card` which is located at the screened portion of a pumping 
  water well.
    
  ::
  
    REGION well-45b
  
 INDIVIDUAL_CONSUMPTION_RATE <double> <unit_string>
  Specifies the water consumption rate in units of volume/time that the typical
  person drinks out of the contaminated well.
  
  ::
  
    INDIVIDUAL_CONSUMPTION_RATE 3.4 L/day
    
Optional Cards:

 INCLUDE_UNSUPPORTED_RADS
  If this card is included, then the ERB_1A model will consider both
  supported and unsupported radionuclides in the calculation of dose. 
  Unsupported radionuclides are those which are not explicitly modeled in the
  simulation (e.g. as a source term or in transport) due to short half-lives, 
  but are considered in a dose calculation.

**ERB_1B block required cards:**

 REGION <string>
  Specifies the ``REGION`` associated with the ERB_1B model, where <string>
  indicates the name of that region. This region must NOT be associated with a 
  :ref:`source-sink-card`. Rather, the region is the location of a 
  **potential** pumping water well, at the screened portion of the well.
    
  ::
  
    REGION potential-well-22c
    
 INDIVIDUAL_CONSUMPTION_RATE <double> <unit_string>
  Specifies the water consumption rate in units of volume/time that the typical
  person drinks out of the contaminated well.
  
  ::
  
    INDIVIDUAL_CONSUMPTION_RATE 2.1 L/day
    
 DILUTION_FACTOR <double>
  Specifies a unitless dilution factor that accounts for the dilution of
  radionuclides at the location of the potential well. The dilution factor
  is the user-estimated volumetric ratio of discharged well water to
  captured plume water. This number should be larger than or equal to 1.  
  A value of 1 implies no dilution (e.g., discharged well water = captured 
  plume water).
  
  ::
  
    DILUTION_FACTOR 4.3d0
    
Optional Cards:

 INCLUDE_UNSUPPORTED_RADS
  If this card is included, then the ERB_1B model will consider both
  supported and unsupported radionuclides in the calculation of dose. 
  Unsupported radionuclides are those which are not explicitly modeled in the
  simulation (e.g. as a source or in transport) due to short half-lives, 
  but are considered in a dose calculation.
  
Examples of the ERB_1A/B blocks:
::

  ERB_1A A_model1
    REGION well
    INDIVIDUAL_CONSUMPTION_RATE 5.d0 L/day
    INCLUDE_UNSUPPORTED_RADS
  /
  ERB_1B B_model1
    REGION potential-well-22c
    DILUTION_FACTOR 2.d0
    INDIVIDUAL_CONSUMPTION_RATE 2.d0 L/day
    INCLUDE_UNSUPPORTED_RADS
  /
  ERB_1B B_model2
    REGION potential-well-67f
    DILUTION_FACTOR 1.d0
    INDIVIDUAL_CONSUMPTION_RATE 3.d0 L/day
  /
  
SUPPORTED_RADIONUCLIDES block
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  
SUPPORTED_RADIONUCLIDES
 Opens the ``SUPPORTED_RADIONUCLIDES`` block which indicates which supported 
 radionuclides are considered in the dose calculations. The following cards
 or sub-blocks are required:

 RADIONUCLIDE <string>
  Specifies a sub-block for each supported radionuclide, where <string> 
  indicates the name of the supported radionuclide. The radionuclide must
  be included as either a primary or secondary species in the 
  :ref:`chemistry-card` block.
  
  ::
  
    RADIONUCLIDE Tc-99
    ...
    /
  
  ELEMENT_KD <double>
   Specifies the elemental Kd value within the material where the screen 
   portion of the well resides. The units can be given in L-water/kg-solid
   or kg-water/m3-bulk, **as long as the units are consistent for all**
   **supported and unsupported radionuclides.**
   
   ::
     
     ELEMENT_KD 3.5d5
   
  DECAY_RATE <double> <unit_string>
   Specifies the decay rate of the supported radionuclide in units of [1/time].
   
   ::
     
     DECAY_RATE 1.29d-13 1/sec 
   
  INGESTION_DOSE_COEF <double> 
   Specifies the ingestion dose coefficient for the supported radionuclide in
   units of Sv/Bq.
   
   ::
   
     INGESTION_DOSE_COEF 1.d-9
   
Examples of a full ``SUPPORTED_RADIONUCLIDES`` block:

::

  SUPPORTED_RADIONUCLIDES
    RADIONUCLIDE Ra-226
      ELEMENT_KD 3.5d5  # at screened part of well
      DECAY_RATE 1.4d-11 1/sec
      INGESTION_DOSE_COEF 2.8d-7 # Sv/Bq
    /
    RADIONUCLIDE Tc-99
      ELEMENT_KD 4.2d5  # at screened part of well
      DECAY_RATE 1.04d-12 1/sec
      INGESTION_DOSE_COEF 1.1d-7 # Sv/Bq
    /
  /
  
UNSUPPORTED_RADIONUCLIDES block
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The concentration [Bq/L] of an unsupported radionuclide in secular equilibrium
with its supported parent is the product of the sorption enhancement factor
of the unsupported radionuclide, the emanation factor of the unsupported
radionuclide, and the concentration [Bq/L] of the supported parent.
  
UNSUPPORTED_RADIONUCLIDES
 Opens the ``UNSUPPORTED_RADIONUCLIDES`` block which indicates which unsupported 
 radionuclides are considered in the dose calculations. These are only included 
 in the calculation for the ERB models that contain the card
 ``INCLUDE_UNSUPPORTED_RADS``. The following cards or sub-blocks are required:
 
 RADIONUCLIDE <string>
  Specifies a sub-block for each unsupported radionuclide, where <string> 
  indicates the name of the unsupported radionuclide. The radionuclide should
  NOT be included as either a primary or secondary species in the 
  :ref:`chemistry-card` block because it is unsupported.
  
  ::
  
    RADIONUCLIDE Bi-210
    ...
    /
  
  ELEMENT_KD <double>
   Specifies the elemental Kd value within the material where the screen 
   portion of the well resides. The units can be given in L-water/kg-solid 
   or kg-water/m3-bulk, **as long as the units are consistent for all**
   **supported and unsupported radionuclides.** Kd is needed to calculate
   the sorption enhancement factor for each unsupported radionuclide. The
   sorption enhancement factor is the ratio of the retardation factor of the
   supported parent to that of the unsupported radionuclide.
   
   ::
     
     ELEMENT_KD 6.5d5
   
  DECAY_RATE <double> <unit_string>
   Specifies the decay rate of the unsupported radionuclide in units of [1/time].
   
   ::
     
     DECAY_RATE 8.9d-11 1/sec 
   
  INGESTION_DOSE_COEF <double> 
   Specifies the ingestion dose coefficient for the unsupported radionuclide in
   units of Sv/Bq.
   
   ::
   
     INGESTION_DOSE_COEF 1.d-7
     
  EMANATION_FACTOR <double>
   Specifies the optional emanation factor in the dose calculation for an
   unsupported radionuclide. The default value is 1.0 if this keyword is 
   omitted.
   
   ::
   
     EMANATION_FACTOR 0.4
   
  SUPPORTED_PARENT <string>
   Indicates the name of the unsupported radionuclide's supported parent 
   radionuclide. The supported parent must be included as a supported
   radionuclide in the ``SUPPORTED_RADIONUCLIDES`` block.
   
   ::
   
     SUPPORTED_PARENT Pb-210
     
Example of a full ``UNSUPPORTED_RADIONUCLIDES`` block:

::

  UNSUPPORTED_RADIONUCLIDES
    RADIONUCLIDE descendant1
      ELEMENT_KD 3.5d5  # at screened part of well
      DECAY_RATE 1.d-14 1/sec
      SUPPORTED_PARENT tracerA
      INGESTION_DOSE_COEF 1.d-10 # Sv/Bq
      EMANATION_FACTOR 0.4d0
    /
    RADIONUCLIDE descendant2
      ELEMENT_KD 4.2d5  # at screened part of well
      DECAY_RATE 1.d-10 1/sec
      SUPPORTED_PARENT tracerA
      INGESTION_DOSE_COEF 1.d-9 # Sv/Bq
    /
    RADIONUCLIDE descendant3
      ELEMENT_KD 2.2d8  # at screened part of well
      DECAY_RATE 1.d-9 1/sec
      SUPPORTED_PARENT tracerB
      INGESTION_DOSE_COEF 1.d-8 # Sv/Bq
      EMANATION_FACTOR 0.4d0
    /
  /
  
Output Control
~~~~~~~~~~~~~~

At each time step, the process model will add dose calculations to an output
file named ``*.bio``. The output includes the total dose from all supported
and unsupported* radionuclides, the annual dose from each radionuclide, as well
as the annual dose from each supported radionuclide and its unsupported 
descendents. The average concentration of each radionuclide in the region 
associated with each ERB model is also reported.

OUTPUT_START_TIME <double> <unit_string>
 If this card is included, the dose calculations will not be printed to the 
 output.bio file until after this point in the simulation time. The default
 start time is 0.d0 seconds (e.g. starting at the first time step).
 
 ::
 
   OUTPUT_START_TIME 5.d0 yr
   
Examples:
---------

::

  UFD_BIOSPHERE
    
    ERB_1A A_model1
      REGION well
      INDIVIDUAL_CONSUMPTION_RATE 5.d0 L/day
      INCLUDE_UNSUPPORTED_RADS
    /
    ERB_1B B_model1
      REGION ERB1B_tester1
      DILUTION_FACTOR 1.d0
      INDIVIDUAL_CONSUMPTION_RATE 2.d0 L/day
      INCLUDE_UNSUPPORTED_RADS
    /
    ERB_1B B_model2
      REGION ERB1B_tester2
      DILUTION_FACTOR 5.d0
      INDIVIDUAL_CONSUMPTION_RATE 3.d0 L/day
    /
    
    SUPPORTED_RADIONUCLIDES
      RADIONUCLIDE tracerA
	ELEMENT_KD 3.5d5  # screened part of well
	DECAY_RATE 1.29d-15 1/sec
	INGESTION_DOSE_COEF 1.d-10 # Sv/Bq
      /
      RADIONUCLIDE tracerB
	ELEMENT_KD 4.2d5  # screened part of well
	DECAY_RATE 1.29d-15 1/sec
	INGESTION_DOSE_COEF 1.d-9 # Sv/Bq
      /
    /
    
    UNSUPPORTED_RADIONUCLIDES
    RADIONUCLIDE descendant1
      ELEMENT_KD 3.5d5  # at screened part of well
      DECAY_RATE 1.d-14 1/sec
      SUPPORTED_PARENT tracerA
      INGESTION_DOSE_COEF 1.d-10 # Sv/Bq
      EMANATION_FACTOR 0.4d0
    /
    RADIONUCLIDE descendant2
      ELEMENT_KD 4.2d5  # at screened part of well
      DECAY_RATE 1.d-10 1/sec
      SUPPORTED_PARENT tracerA
      INGESTION_DOSE_COEF 1.d-9 # Sv/Bq
    /
    RADIONUCLIDE descendant3
      ELEMENT_KD 2.2d8  # at screened part of well
      DECAY_RATE 1.d-9 1/sec
      SUPPORTED_PARENT tracerB
      INGESTION_DOSE_COEF 1.d-8 # Sv/Bq
      EMANATION_FACTOR 0.4d0
    /
  /
    
    OUTPUT_START_TIME 5.d0 yr
    
  END
   
